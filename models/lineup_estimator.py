"""
lineup_estimator.py — Estimate the most probable starting XI when confirmed lineup is unavailable.

Logic:
  1. Use coach's preferred formation (hardcoded defaults, overridden by teams.formation in DB)
  2. Players most frequently selected in last 10 national team matches (player_nat_stats)
  3. Highest-rated available players per position (player_ratings)
  4. If player_ratings empty: use player_club_stats as proxy
  5. Apply injury/suspension flags from squad_selections

Returns:
  {
    "formation": "4-3-3",
    "starters": [{"name": ..., "position": ..., "rating": ..., "club": ...}, ...],
    "bench": [...],
    "estimated": True,
    "confidence": "high" | "medium" | "low",
    "reason": "...",
  }
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# ── Coach preferred formations by team (2025 season, WC2026) ────────────
# Source: actual DT formations from qualifying campaigns / 2024-25 season
COACH_FORMATIONS = {
    # Group A
    "Mexico":                  "4-4-2",    # Javier Aguirre
    "South Africa":            "4-4-2",    # Hugo Broos
    "South Korea":             "4-2-3-1",  # Hong Myung-Bo
    "Czechia":                 "4-2-3-1",  # Ivan Hašek
    # Group B
    "Canada":                  "4-3-3",    # Jesse Marsch (high press)
    "Bosnia and Herzegovina":  "4-2-3-1",  # Elvir Baljić
    "Qatar":                   "4-3-3",    # Bartolomeu Sousa
    "Switzerland":             "3-4-3",    # Murat Yakin
    # Group C
    "Brazil":                  "4-2-3-1",  # Dorival Jr.
    "Morocco":                 "4-3-3",    # Walid Regragui
    "Haiti":                   "4-4-2",    # Marc Collat
    "Scotland":                "3-4-3",    # Steve Clarke
    # Group D
    "USA":                     "4-3-3",    # Mauricio Pochettino
    "Paraguay":                "4-2-3-1",  # Diego Garnero
    "Australia":               "4-3-3",    # Tony Popovic
    "Turkey":                  "4-2-3-1",  # Vincenzo Montella
    # Group E
    "Germany":                 "4-2-3-1",  # Julian Nagelsmann
    "Curacao":                 "4-4-2",    # Remko Bicentini
    "Ivory Coast":             "4-3-3",    # Emerse Faé
    "Ecuador":                 "4-4-2",    # Sebastián Beccacece
    # Group F
    "Netherlands":             "4-3-3",    # Ronald Koeman
    "Japan":                   "4-2-3-1",  # Hajime Moriyasu
    "Sweden":                  "4-4-2",    # Jon Dahl Tomasson
    "Tunisia":                 "4-3-3",    # Faouzi Benzarti
    # Group G
    "Belgium":                 "4-3-3",    # Domenico Tedesco
    "Egypt":                   "4-2-3-1",  # Hossam Hassan
    "Iran":                    "4-5-1",    # Amir Ghalenoei
    "New Zealand":             "4-3-3",    # Darren Bazeley
    # Group H
    "Spain":                   "4-3-3",    # Luis de la Fuente
    "Cape Verde":              "4-3-3",    # Pedro Brito "Bubista"
    "Saudi Arabia":            "4-3-3",    # Roberto Mancini
    "Uruguay":                 "3-3-1-3",  # Marcelo Bielsa (asymmetric)
    # Group I
    "France":                  "4-2-3-1",  # Didier Deschamps
    "Senegal":                 "4-3-3",    # Aliou Cissé
    "Iraq":                    "4-5-1",    # Srečko Katanec
    "Norway":                  "4-3-3",    # Ståle Solbakken
    # Group J
    "Argentina":               "4-3-3",    # Lionel Scaloni
    "Algeria":                 "4-3-3",    # Vladimir Petković
    "Austria":                 "4-2-3-1",  # Ralf Rangnick (gegenpress)
    "Jordan":                  "4-5-1",    # Hossam Hassan
    # Group K
    "Portugal":                "4-3-3",    # Roberto Martínez
    "DR Congo":                "4-3-3",    # Sébastien Desabre
    "Uzbekistan":              "4-2-3-1",  # Srečko Katanec
    "Colombia":                "4-2-3-1",  # Néstor Lorenzo
    # Group L
    "England":                 "4-2-3-1",  # Thomas Tuchel
    "Croatia":                 "4-2-3-1",  # Zlatko Dalić
    "Ghana":                   "4-2-3-1",  # Otto Addo
    "Panama":                  "4-4-2",    # Thomas Christiansen
}

# Alt formations (defensive/adaptive context)
COACH_ALT_FORMATIONS = {
    "Mexico":                  "4-5-1",
    "South Africa":            "5-4-1",
    "South Korea":             "4-5-1",
    "Czechia":                 "4-5-1",
    "Canada":                  "4-4-2",
    "Bosnia and Herzegovina":  "5-3-2",
    "Qatar":                   "5-4-1",
    "Switzerland":             "5-3-2",
    "Brazil":                  "4-3-3",
    "Morocco":                 "4-5-1",
    "Haiti":                   "5-4-1",
    "Scotland":                "5-4-1",
    "USA":                     "4-4-2",
    "Paraguay":                "4-5-1",
    "Australia":               "4-5-1",
    "Turkey":                  "4-5-1",
    "Germany":                 "4-3-3",
    "Curacao":                 "5-4-1",
    "Ivory Coast":             "4-4-2",
    "Ecuador":                 "4-5-1",
    "Netherlands":             "4-4-2",
    "Japan":                   "4-5-1",
    "Sweden":                  "5-4-1",
    "Tunisia":                 "4-5-1",
    "Belgium":                 "4-4-2",
    "Egypt":                   "4-5-1",
    "Iran":                    "5-4-1",
    "New Zealand":             "5-4-1",
    "Spain":                   "4-4-2",
    "Cape Verde":              "4-5-1",
    "Saudi Arabia":            "4-5-1",
    "Uruguay":                 "4-4-2",
    "France":                  "4-4-2",
    "Senegal":                 "4-4-2",
    "Iraq":                    "5-4-1",
    "Norway":                  "4-4-2",
    "Argentina":               "4-2-3-1",
    "Algeria":                 "4-5-1",
    "Austria":                 "4-3-3",
    "Jordan":                  "5-4-1",
    "Portugal":                "4-2-3-1",
    "DR Congo":                "4-4-2",
    "Uzbekistan":              "4-5-1",
    "Colombia":                "4-3-3",
    "England":                 "4-3-3",
    "Croatia":                 "4-5-1",
    "Ghana":                   "4-4-2",
    "Panama":                  "5-4-1",
}

DEFAULT_FORMATION = "4-4-2"

# ── Slots per formation ──────────────────────────────────────────────────
# Each formation maps to {GK, DEF, MID, FWD} counts
FORMATION_SLOTS = {
    "4-3-3":   {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3},
    "4-2-3-1": {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},  # 5 mids treats AM as MID
    "4-4-2":   {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
    "3-4-3":   {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    "3-5-2":   {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
    "5-3-2":   {"GK": 1, "DEF": 5, "MID": 3, "FWD": 2},
    "4-5-1":   {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "4-1-4-1": {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "3-3-1-3": {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},  # Bielsa asymmetric
    "5-4-1":   {"GK": 1, "DEF": 5, "MID": 4, "FWD": 1},
    "5-2-3":   {"GK": 1, "DEF": 5, "MID": 2, "FWD": 3},
    "4-2-4":   {"GK": 1, "DEF": 4, "MID": 2, "FWD": 4},
}


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_formation_slots(formation: str) -> dict:
    """Return player count per position for a given formation string."""
    # Normalize: "4-2-3-1" -> collapse middle rows -> total MID
    slots = FORMATION_SLOTS.get(formation)
    if slots:
        return slots

    # Try parsing: split by "-", first=GK(always 1), last=FWD, rest=MID
    parts = formation.split("-")
    if len(parts) >= 3:
        try:
            fwd = int(parts[-1])
            def_ = int(parts[0])
            mid = sum(int(p) for p in parts[1:-1])
            return {"GK": 1, "DEF": def_, "MID": mid, "FWD": fwd}
        except ValueError:
            pass

    # Fallback to 4-4-2
    return FORMATION_SLOTS["4-4-2"]


def _get_team_id_and_formation(
    team_name: str,
    db_path: Optional[Path] = None,
    context: str = "normal",   # "normal" | "defensive" | "attacking"
    opponent_ranking: Optional[int] = None,
) -> tuple:
    """Return (team_id, formation) for a team, adapting to match context."""
    conn = _conn(db_path)
    row = conn.execute(
        "SELECT id, formation, fifa_ranking FROM teams WHERE name=? OR name LIKE ?",
        (team_name, f"%{team_name}%")
    ).fetchone()
    conn.close()
    if not row:
        return None, COACH_FORMATIONS.get(team_name, DEFAULT_FORMATION)

    own_ranking = row["fifa_ranking"] or 50

    # Determine context from rankings if not explicitly set
    if context == "normal" and opponent_ranking:
        rank_gap = opponent_ranking - own_ranking  # positive = we are stronger
        if rank_gap < -25:   # we are heavy underdog
            context = "defensive"
        elif rank_gap > 25:  # we are heavy favorite
            context = "attacking"

    if context == "defensive":
        formation = COACH_ALT_FORMATIONS.get(team_name) or row["formation"] or DEFAULT_FORMATION
    else:
        formation = COACH_FORMATIONS.get(team_name) or row["formation"] or DEFAULT_FORMATION

    return row["id"], formation


def _get_unavailable_player_ids(team_id: int, db_path: Optional[Path] = None) -> set:
    """
    Return set of player_ids that are injured or suspended (confirmed=0 in squad_selections).
    """
    conn = _conn(db_path)
    rows = conn.execute("""
        SELECT player_id FROM squad_selections
        WHERE team_id=? AND confirmed=0
    """, (team_id,)).fetchall()
    conn.close()
    return {r["player_id"] for r in rows}


def _get_nat_selection_frequency(team_id: int, last_n: int = 10, db_path: Optional[Path] = None) -> dict:
    """
    Return {player_id: frequency_count} based on how many of the last N
    national team matches the player was a starter (was_starter=1 in player_nat_stats).
    """
    conn = _conn(db_path)

    # Get last N match IDs for this team
    match_ids = [r["id"] for r in conn.execute("""
        SELECT id FROM team_matches
        WHERE team_id=?
        ORDER BY date DESC
        LIMIT ?
    """, (team_id, last_n)).fetchall()]

    if not match_ids:
        conn.close()
        return {}

    placeholders = ",".join("?" * len(match_ids))
    rows = conn.execute(f"""
        SELECT player_id, COUNT(*) as freq
        FROM player_nat_stats
        WHERE match_id IN ({placeholders}) AND was_starter=1
        GROUP BY player_id
    """, match_ids).fetchall()
    conn.close()

    return {r["player_id"]: r["freq"] for r in rows}


def _get_player_ratings(team_id: int, db_path: Optional[Path] = None) -> dict:
    """
    Return {player_id: rating} from player_ratings table (latest per player).
    Falls back to club_stats proxy if empty.
    """
    conn = _conn(db_path)

    # Try player_ratings first
    rows = conn.execute("""
        SELECT pr.player_id, MAX(pr.rating) as rating
        FROM player_ratings pr
        JOIN players p ON p.id = pr.player_id
        WHERE p.team_id=?
        GROUP BY pr.player_id
    """, (team_id,)).fetchall()

    if rows:
        conn.close()
        return {r["player_id"]: r["rating"] for r in rows}

    # Fallback: synthesize from player_club_stats
    rows = conn.execute("""
        SELECT p.id as player_id, p.position,
               SUM(pcs.goals) as goals,
               SUM(pcs.assists) as assists,
               SUM(pcs.minutes) as minutes,
               AVG(pcs.pass_accuracy) as pass_acc
        FROM players p
        LEFT JOIN player_club_stats pcs ON pcs.player_id = p.id
        WHERE p.team_id=?
        GROUP BY p.id
    """, (team_id,)).fetchall()

    ratings = {}
    for r in rows:
        mins = r["minutes"] or 0
        goals = r["goals"] or 0
        assists = r["assists"] or 0
        pos = r["position"] or "MID"

        # Simple scoring proxy
        base = 6.0
        if mins > 0:
            per_90 = 90.0 / max(mins / (max(1, mins // 90)), 1)
            g90 = goals * per_90
            a90 = assists * per_90
        else:
            g90 = 0
            a90 = 0

        if pos == "FWD":
            base += min(2.0, g90 * 0.8 + a90 * 0.4)
        elif pos == "MID":
            base += min(1.5, g90 * 0.5 + a90 * 0.6)
        elif pos == "DEF":
            base += min(1.0, g90 * 0.3 + a90 * 0.3)
        # GK: stays at base

        ratings[r["player_id"]] = round(min(9.5, base), 2)

    conn.close()
    return ratings


def _get_squad_players(team_id: int, db_path: Optional[Path] = None) -> list:
    """
    Return list of squad player dicts: id, name, position, club, age, caps.
    Only confirmed players (confirmed=1, or NULL/missing means not explicitly excluded).
    """
    conn = _conn(db_path)
    rows = conn.execute("""
        SELECT p.id, p.name, p.position, p.club, p.age, p.caps,
               COALESCE(ss.confirmed, 1) as confirmed
        FROM players p
        LEFT JOIN squad_selections ss ON ss.player_id = p.id AND ss.team_id = ?
        WHERE p.team_id = ?
    """, (team_id, team_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def estimate_lineup(
    team_name: str,
    db_path: Optional[Path] = None,
    context: str = "normal",
    opponent_ranking: Optional[int] = None,
) -> dict:
    """
    Estimate the most probable starting XI for a team.

    context: "normal" | "defensive" | "attacking"
    opponent_ranking: FIFA ranking of opponent (used to auto-detect context)

    Returns:
    {
        "team": str,
        "formation": str,
        "starters": [{"name", "position", "rating", "club", "caps"}, ...],
        "bench": [...],
        "estimated": True,
        "confidence": "high" | "medium" | "low",
        "reason": str,
    }
    """
    db = db_path or DB_PATH

    team_id, formation = _get_team_id_and_formation(
        team_name, db, context=context, opponent_ranking=opponent_ranking
    )

    if team_id is None:
        return {
            "team": team_name,
            "formation": DEFAULT_FORMATION,
            "starters": [],
            "bench": [],
            "estimated": True,
            "confidence": "low",
            "reason": f"Team '{team_name}' not found in database",
        }

    # Get formation slots
    slots = _get_formation_slots(formation)

    # Get unavailable players (injured/suspended)
    unavailable = _get_unavailable_player_ids(team_id, db)

    # Get all squad players
    squad = _get_squad_players(team_id, db)
    available = [p for p in squad if p["id"] not in unavailable and p["confirmed"] != 0]

    if not available:
        # Use all players if no squad_selections exist
        available = squad

    # Get selection frequency (nat stats)
    freq_map = _get_nat_selection_frequency(team_id, last_n=10, db_path=db)

    # Get player ratings
    rating_map = _get_player_ratings(team_id, db)

    # Score each player: combined rating + frequency bonus
    def player_score(p):
        pid = p["id"]
        rating = rating_map.get(pid, 6.0)
        freq = freq_map.get(pid, 0)
        freq_bonus = freq * 0.15  # up to 1.5 for 10/10 selections
        return rating + freq_bonus

    # Group available players by position
    by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in available:
        pos = p["position"] or "MID"
        if pos not in by_pos:
            pos = "MID"
        by_pos[pos].append(p)

    # Sort each position by score
    for pos in by_pos:
        by_pos[pos].sort(key=player_score, reverse=True)

    # Select starters according to formation slots
    starters = []
    bench_pool = []
    used_player_ids = set()

    for pos, needed in slots.items():
        candidates = by_pos.get(pos, [])
        selected = candidates[:needed]
        remainder = candidates[needed:]

        for p in selected:
            starters.append({
                "name": p["name"],
                "position": pos,
                "rating": round(rating_map.get(p["id"], 6.0), 2),
                "club": p.get("club") or "",
                "caps": p.get("caps") or 0,
                "freq_last10": freq_map.get(p["id"], 0),
            })
            used_player_ids.add(p["id"])
        bench_pool.extend(remainder)

    # If we don't have enough for any position, fill with best available
    # (flex fill: positions with 0 candidates get players from overflow)
    starters_count = len(starters)
    if starters_count < 11:
        # Build a sorted pool from all unused players (by player ID to avoid duplicates)
        flex_pool = [p for p in available if p["id"] not in used_player_ids]
        flex_pool.sort(key=player_score, reverse=True)

        needed_more = 11 - starters_count
        for p in flex_pool[:needed_more]:
            starters.append({
                "name": p["name"],
                "position": p.get("position") or "MID",
                "rating": round(rating_map.get(p["id"], 6.0), 2),
                "club": p.get("club") or "",
                "caps": p.get("caps") or 0,
                "freq_last10": freq_map.get(p["id"], 0),
            })
            used_player_ids.add(p["id"])
        bench_pool.extend(flex_pool[needed_more:])

    # Build bench (remaining players not yet used, sorted by score)
    # Deduplicate bench_pool by player ID
    seen_bench_ids = set(used_player_ids)
    unique_bench_pool = []
    for p in bench_pool:
        if p["id"] not in seen_bench_ids:
            unique_bench_pool.append(p)
            seen_bench_ids.add(p["id"])

    unique_bench_pool.sort(key=player_score, reverse=True)
    bench = [
        {
            "name": p["name"],
            "position": p.get("position") or "MID",
            "rating": round(rating_map.get(p["id"], 6.0), 2),
            "club": p.get("club") or "",
            "caps": p.get("caps") or 0,
        }
        for p in unique_bench_pool[:12]
    ]

    # ── Confidence assessment ──
    has_ratings = len(rating_map) > 0
    has_freq_data = len(freq_map) > 0
    has_squad = len(available) >= 11
    unavailable_count = len(unavailable)

    if has_ratings and has_freq_data and has_squad and unavailable_count == 0:
        confidence = "high"
        reason = "Ratings + nat stats frequency available, full squad confirmed"
    elif has_ratings and has_squad:
        confidence = "medium"
        reason = "Player ratings available; limited national team match frequency data"
    elif has_squad:
        confidence = "medium"
        reason = "Using profile-based rating estimates; no detailed stats"
    else:
        confidence = "low"
        reason = "Limited squad data; lineup is a rough estimate"

    if unavailable_count > 0:
        reason += f" ({unavailable_count} player(s) marked unavailable/injured)"
        if confidence == "high":
            confidence = "medium"

    return {
        "team": team_name,
        "formation": formation,
        "starters": starters[:11],
        "bench": bench,
        "estimated": True,
        "confidence": confidence,
        "reason": reason,
    }


def estimate_lineup_for_match(
    home_team: str,
    away_team: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Convenience function: estimate lineups for both teams in a match.
    Returns {"home": {...}, "away": {...}}.
    """
    return {
        "home": estimate_lineup(home_team, db_path),
        "away": estimate_lineup(away_team, db_path),
    }


def print_lineup(lineup: dict) -> None:
    """Pretty-print an estimated lineup."""
    status = "ESTIMADA" if lineup.get("estimated") else "CONFIRMADA"
    conf = lineup.get("confidence", "?").upper()
    team = lineup.get("team", "?")
    formation = lineup.get("formation", "?")

    print(f"\n  [{team}] ALINEACION {status} ({conf} CONFIANZA)")
    print(f"  Formacion: {formation}")
    print(f"  Razon: {lineup.get('reason', '')}")
    print(f"  {'#':<3} {'Nombre':<28} {'POS':<5} {'Rating':>6}  {'Club'}")
    print(f"  {'-'*65}")

    for i, p in enumerate(lineup.get("starters", []), 1):
        freq = p.get("freq_last10", 0)
        freq_str = f"[{freq}/10]" if freq > 0 else ""
        print(f"  {i:<3} {p['name']:<28} {p['position']:<5} {p['rating']:>6.1f}  {p['club']}  {freq_str}")

    bench = lineup.get("bench", [])
    if bench:
        print(f"\n  SUPLENTES:")
        for p in bench[:7]:
            print(f"      {p['name']:<28} {p['position']:<5} {p['rating']:>6.1f}  {p['club']}")
    print()


if __name__ == "__main__":
    import sys

    team = sys.argv[1] if len(sys.argv) > 1 else "Panama"
    lineup = estimate_lineup(team)
    print_lineup(lineup)
