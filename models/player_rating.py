"""
player_rating.py — Calcula ratings de jugadores en escala 1-10.

Rating base: 6.0
Componentes:
  - Goles: +1.5 por gol
  - Asistencias: +0.8 por asistencia
  - Precision de pase: bonus/penalidad vs promedio por posicion
  - Tackles/intercepciones (DEF/MID): bonus
  - Ratio de tiros al arco
  - Tarjeta amarilla: -0.3, Roja: -2.0
  - Factor de minutos jugados
  - Pesos especificos por posicion
  - GK: criterios distintos

Tambien computa:
  - club_form_rating  — promedio ponderado ultimos 20 partidos en club
  - nat_form_rating   — promedio ponderado ultimos 10 partidos en seleccion
  - consistency_delta — diferencia club vs seleccion
"""
import json
import math
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Position averages for pass accuracy benchmark
POSITION_PASS_AVG = {
    "GK":  72.0,
    "DEF": 82.0,
    "MID": 85.0,
    "FWD": 78.0,
}

# Base weights per position (sum to 1.0)
POSITION_WEIGHTS = {
    "GK": {
        "saves":         0.35,
        "pass_accuracy": 0.20,
        "distribution":  0.15,
        "goals_conceded":0.20,
        "yellow_card":   0.10,
    },
    "DEF": {
        "goals":         0.10,
        "assists":       0.08,
        "pass_accuracy": 0.18,
        "tackles":       0.25,
        "interceptions": 0.20,
        "dribbles":      0.09,
        "yellow_card":   0.10,
    },
    "MID": {
        "goals":         0.20,
        "assists":       0.18,
        "pass_accuracy": 0.22,
        "tackles":       0.15,
        "interceptions": 0.12,
        "dribbles":      0.08,
        "yellow_card":   0.05,
    },
    "FWD": {
        "goals":         0.35,
        "assists":       0.20,
        "pass_accuracy": 0.12,
        "shots_on_target":0.18,
        "dribbles":      0.10,
        "yellow_card":   0.05,
    },
}


@dataclass
class ClubMatchStats:
    goals: int = 0
    assists: int = 0
    shots_on_target: int = 0
    shots_total: int = 0
    pass_accuracy: float = 0.0
    dribbles_completed: int = 0
    tackles: int = 0
    interceptions: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    minutes: int = 90
    saves: int = 0              # GK only
    goals_conceded: int = 0     # GK only


@dataclass
class RatingComponents:
    base: float = 6.0
    goal_bonus: float = 0.0
    assist_bonus: float = 0.0
    pass_bonus: float = 0.0
    defensive_bonus: float = 0.0
    attack_bonus: float = 0.0
    card_penalty: float = 0.0
    minutes_factor: float = 1.0
    final_rating: float = 6.0


def minutes_factor(minutes_played: int) -> float:
    """Scale rating by minutes played. <45 min = partial credit."""
    if minutes_played <= 0:
        return 0.0
    if minutes_played < 45:
        return 0.5 + (minutes_played / 45) * 0.3  # 0.5 to 0.8
    if minutes_played < 60:
        return 0.85
    if minutes_played < 75:
        return 0.92
    return 1.0


def compute_player_rating(
    stats: ClubMatchStats,
    position: str,
    context: str = "club"
) -> RatingComponents:
    """
    Compute a single-match rating for a player.
    Returns a RatingComponents object with all breakdown.
    """
    pos = position.upper() if position else "MID"
    if pos not in POSITION_WEIGHTS:
        pos = "MID"

    rc = RatingComponents()
    rc.base = 6.0

    # --- Goals ---
    rc.goal_bonus = stats.goals * 1.5
    if pos == "DEF":
        rc.goal_bonus = stats.goals * 1.8  # defender goals = more impactful
    elif pos == "GK":
        rc.goal_bonus = 0.0

    # --- Assists ---
    rc.assist_bonus = stats.assists * 0.8

    # --- Pass accuracy vs position benchmark ---
    avg_pass = POSITION_PASS_AVG.get(pos, 80.0)
    if stats.pass_accuracy > 0:
        pass_diff = (stats.pass_accuracy - avg_pass) / 10.0  # 10pp = 1 rating pt
        rc.pass_bonus = max(-1.5, min(1.5, pass_diff))

    # --- Defensive contributions (DEF and MID) ---
    if pos in ("DEF", "MID"):
        tackle_bonus = min(1.2, stats.tackles * 0.15 + stats.interceptions * 0.18)
        rc.defensive_bonus = tackle_bonus

    # --- GK specific ---
    if pos == "GK":
        # Saves
        rc.defensive_bonus = min(2.0, stats.saves * 0.25)
        # Goals conceded penalty
        conceded_penalty = stats.goals_conceded * 0.4
        rc.defensive_bonus -= conceded_penalty
        rc.goal_bonus = 0.0
        rc.assist_bonus = 0.0

    # --- Attack (FWD / MID): shots on target ---
    if pos in ("FWD", "MID") and stats.shots_total > 0:
        shot_ratio = stats.shots_on_target / stats.shots_total
        rc.attack_bonus = min(0.8, (shot_ratio - 0.3) * 1.0)

    # --- Dribbles ---
    dribble_bonus = min(0.5, stats.dribbles_completed * 0.1)

    # --- Cards ---
    rc.card_penalty = -(stats.yellow_cards * 0.3 + stats.red_cards * 2.0)

    # --- Minutes factor ---
    rc.minutes_factor = minutes_factor(stats.minutes)

    # --- Compute final rating ---
    raw = (
        rc.base
        + rc.goal_bonus
        + rc.assist_bonus
        + rc.pass_bonus
        + rc.defensive_bonus
        + rc.attack_bonus
        + dribble_bonus
        + rc.card_penalty
    )

    # Apply minutes factor (less playing time = regression toward 5.5)
    if rc.minutes_factor < 1.0:
        raw = 5.5 + (raw - 5.5) * rc.minutes_factor

    rc.final_rating = round(max(1.0, min(10.0, raw)), 2)
    return rc


def compute_form_rating(match_ratings: list[float], decay: float = 0.92) -> float:
    """
    Compute weighted average of match ratings.
    Most recent match has highest weight.
    decay: exponential decay factor (0.92 = 8% decay per match going back).
    """
    if not match_ratings:
        return 6.0

    weights = [decay ** i for i in range(len(match_ratings))]
    # most recent first
    total = sum(w * r for w, r in zip(weights, match_ratings))
    weight_sum = sum(weights)
    return round(total / weight_sum, 3)


def compute_consistency_delta(club_rating: float, nat_rating: float) -> float:
    """
    Positive = performs better for national team.
    Negative = underperforms for national team vs club.
    """
    return round(nat_rating - club_rating, 3)


class PlayerRatingEngine:
    """High-level API to compute and store player ratings using the DB."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def rate_from_club_stats(self, player_id: int, season: str = "2024/25") -> Optional[float]:
        """
        Compute and store a rating from aggregated club season stats.
        Returns the rating value.
        """
        conn = self._conn()
        cur = conn.cursor()

        player = cur.execute(
            "SELECT id, position FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if not player:
            conn.close()
            return None

        stats_row = cur.execute("""
            SELECT * FROM player_club_stats
            WHERE player_id=? AND season=?
            ORDER BY rowid DESC LIMIT 1
        """, (player_id, season)).fetchone()

        if not stats_row:
            conn.close()
            return None

        # Per-match averages
        matches = max(1, stats_row["matches"])
        avg = ClubMatchStats(
            goals=stats_row["goals"] / matches,
            assists=stats_row["assists"] / matches,
            shots_on_target=stats_row["shots_on_target"] / matches,
            shots_total=max(1, stats_row["shots_on_target"] / 0.4) if stats_row["shots_on_target"] else 0,
            pass_accuracy=stats_row["pass_accuracy"],
            dribbles_completed=stats_row["dribbles_completed"] / matches,
            tackles=stats_row["tackles"] / matches,
            interceptions=stats_row["interceptions"] / matches,
            yellow_cards=stats_row["yellow_cards"] / matches,
            red_cards=stats_row["red_cards"] / matches,
            minutes=int(stats_row["minutes"] / matches),
        )

        rc = compute_player_rating(avg, player["position"], context="club")
        components_json = json.dumps(asdict(rc))

        # Store in player_ratings
        cur.execute("""
            INSERT OR REPLACE INTO player_ratings
                (player_id, match_id, context, rating, components)
            VALUES (?,NULL,'club',?,?)
        """, (player_id, rc.final_rating, components_json))
        conn.commit()
        conn.close()
        return rc.final_rating

    def get_player_form(self, player_id: int, context: str = "club", last_n: int = 20) -> dict:
        """
        Get form rating and breakdown for a player.
        Returns dict with club_form, nat_form, consistency_delta.
        """
        conn = self._conn()
        cur = conn.cursor()

        player = cur.execute(
            "SELECT id, name, position FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if not player:
            conn.close()
            return {}

        # Club ratings
        club_ratings = [
            r["rating"] for r in cur.execute("""
                SELECT rating FROM player_ratings
                WHERE player_id=? AND context='club'
                ORDER BY rowid DESC LIMIT ?
            """, (player_id, last_n)).fetchall()
        ]

        # Nat ratings
        nat_ratings = [
            r["rating"] for r in cur.execute("""
                SELECT rating FROM player_ratings
                WHERE player_id=? AND context='nat'
                ORDER BY rowid DESC LIMIT ?
            """, (player_id, 10)).fetchall()
        ]

        # If no stored ratings, estimate from aggregate stats
        if not club_ratings:
            # Try to synthesize from club season stats
            stats_row = cur.execute("""
                SELECT * FROM player_club_stats WHERE player_id=?
                ORDER BY season DESC LIMIT 1
            """, (player_id,)).fetchone()
            if stats_row:
                matches = max(1, stats_row["matches"])
                avg = ClubMatchStats(
                    goals=stats_row["goals"] / matches,
                    assists=stats_row["assists"] / matches,
                    shots_on_target=stats_row["shots_on_target"] / matches,
                    pass_accuracy=stats_row["pass_accuracy"],
                    dribbles_completed=stats_row["dribbles_completed"] / matches,
                    tackles=stats_row["tackles"] / matches,
                    interceptions=stats_row["interceptions"] / matches,
                    yellow_cards=stats_row["yellow_cards"] / matches,
                    red_cards=stats_row["red_cards"] / matches,
                    minutes=int(stats_row["minutes"] / matches),
                )
                rc = compute_player_rating(avg, player["position"], "club")
                club_ratings = [rc.final_rating]

        # Use nat stats
        if not nat_ratings:
            nat_stats = cur.execute("""
                SELECT goals, assists, minutes, rating FROM player_nat_stats
                WHERE player_id=?
                ORDER BY rowid DESC LIMIT 10
            """, (player_id,)).fetchall()
            for ns in nat_stats:
                if ns["rating"]:
                    nat_ratings.append(ns["rating"])
                else:
                    # synthesize quick rating
                    ms = ClubMatchStats(
                        goals=ns["goals"],
                        assists=ns["assists"],
                        minutes=ns["minutes"]
                    )
                    rc = compute_player_rating(ms, player["position"], "nat")
                    nat_ratings.append(rc.final_rating)

        club_form = compute_form_rating(club_ratings)
        nat_form = compute_form_rating(nat_ratings) if nat_ratings else club_form
        delta = compute_consistency_delta(club_form, nat_form)

        conn.close()
        return {
            "player_id": player_id,
            "player_name": player["name"],
            "position": player["position"],
            "club_form_rating": club_form,
            "nat_form_rating": nat_form,
            "consistency_delta": delta,
            "club_samples": len(club_ratings),
            "nat_samples": len(nat_ratings),
        }

    def estimate_rating_from_profile(self, player_row: sqlite3.Row) -> float:
        """
        Estimate a player's current rating from their profile data
        (when no detailed match stats are available).
        Uses caps, goals, age and league quality as proxies.
        """
        pos = player_row["position"] or "MID"
        caps = player_row["caps"] or 0
        goals = player_row["goals_as_nat"] or 0
        age = player_row["age"] or 25
        league = player_row["club_league"] or ""

        # League quality bonus (rough tiers)
        league_bonus = 0.0
        tier1 = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "Champions League"]
        tier2 = ["Primeira Liga", "Eredivisie", "Pro League", "Scottish Prem", "MLS", "Brasileirao"]
        for t in tier1:
            if t.lower() in league.lower():
                league_bonus = 0.5
                break
        else:
            for t in tier2:
                if t.lower() in league.lower():
                    league_bonus = 0.2
                    break

        # Experience bonus
        exp_bonus = min(0.5, caps * 0.003)

        # Goals per cap ratio (for forwards)
        base = 6.0
        if pos in ("FWD", "MID") and caps > 5:
            gpc = goals / max(1, caps)
            goal_bonus = min(1.2, gpc * 3.0)
            base += goal_bonus

        # Age factor: prime 24-30
        if 24 <= age <= 30:
            age_factor = 1.0
        elif 21 <= age <= 33:
            age_factor = 0.95
        else:
            age_factor = 0.88

        raw = (base + league_bonus + exp_bonus) * age_factor
        return round(max(4.5, min(9.5, raw)), 2)


def rate_squad_from_profiles(team_name: str, db_path: Optional[Path] = None) -> dict:
    """
    Rate all players in a team's squad based on their profile data.
    Returns dict of position -> list of (player_name, rating).
    """
    engine = PlayerRatingEngine(db_path)
    conn = engine._conn()
    cur = conn.cursor()

    team_row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        conn.close()
        return {}

    team_id = team_row["id"]
    players = cur.execute("""
        SELECT p.* FROM players p
        JOIN squad_selections ss ON ss.player_id = p.id
        WHERE ss.team_id = ? AND ss.confirmed = 1
    """, (team_id,)).fetchall()

    result = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        rating = engine.estimate_rating_from_profile(p)
        pos = p["position"] or "MID"
        if pos not in result:
            pos = "MID"
        result[pos].append({
            "player_id": p["id"],
            "name": p["name"],
            "club": p["club"],
            "league": p["club_league"],
            "age": p["age"],
            "caps": p["caps"],
            "rating": rating,
        })

    # Sort by rating descending within each position
    for pos in result:
        result[pos].sort(key=lambda x: x["rating"], reverse=True)

    conn.close()
    return result


if __name__ == "__main__":
    import sys

    team = sys.argv[1] if len(sys.argv) > 1 else "Panama"
    print(f"\n=== Ratings de plantilla: {team} ===\n")

    ratings = rate_squad_from_profiles(team)
    for pos, players in ratings.items():
        if players:
            print(f"  {pos}:")
            for p in players:
                print(f"    {p['name']:<28} {p['rating']:>4.1f}  {p['club']} ({p['league']})")
    print()
