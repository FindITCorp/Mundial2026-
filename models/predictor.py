"""
predictor.py — Motor de prediccion avanzado para partidos del Mundial 2026.

Flujo para "Panama vs Croatia":
1. Cargar convocados y alineacion probable de ambos equipos
2. Comparar jugador por jugador por linea:
   - Duelo de porteros
   - Linea defensiva
   - Linea de mediocampo
   - Linea de ataque
3. Calcular forma del equipo (ultimos 10 partidos, ponderado reciente)
4. Calcular H2H (partidos directos ultimos 10 anos)
5. Si no hay H2H: usar similitud de equipos para proxy
6. Factor historial en Mundiales
7. Output completo con probabilidades, marcador probable, analisis linea a linea
"""
import math
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, NamedTuple

from models.player_rating import rate_squad_from_profiles
from models.team_similarity import find_similar_teams, find_proxy_h2h

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Round value in points for WC history factor
WC_ROUND_POINTS = {
    "Did not qualify": 0,
    "Group Stage": 1,
    "Round of 16": 2,
    "Quarter-final": 3,
    "4th place": 4,
    "3rd place": 5,
    "Runner-up": 6,
    "Champion": 7,
}

# Competition quality multiplier applied to each match in form_score.
# More specific patterns MUST appear before broader ones (first match wins).
# Keys matched against competition.lower() with accent-stripped normalization.
_COMP_WEIGHT: list[tuple[str, float]] = [
    # Qualification rounds — BEFORE the broader "fifa world cup" match
    ("world cup qualification", 1.20),
    ("wcq", 1.20),
    ("african cup of nations qualification", 1.10),
    ("africa cup of nations qualification", 1.10),
    ("uefa euro qualification", 1.10),
    ("afc asian cup qualification", 1.05),
    ("copa america qualification", 1.05),
    ("copa americana qualification", 1.05),
    # WC final tournament
    ("fifa world cup", 1.50),
    ("world cup", 1.50),
    # Major continental finals
    ("copa america", 1.40),
    ("copa americana", 1.40),
    ("uefa euro", 1.40),
    ("african cup of nations", 1.30),
    ("africa cup of nations", 1.30),
    ("afc asian cup", 1.25),
    ("gold cup", 1.20),
    ("concacaf gold cup", 1.20),
    ("oceania nations cup", 1.15),
    # Secondary competitive tournaments
    ("nations league", 1.15),
    ("concacaf nations league", 1.15),
    ("gulf cup", 1.10),
    ("arab cup", 1.05),
    ("kirin cup", 1.00),
    # FIFA series / test events
    ("fifa series", 0.90),
    # Friendlies
    ("friendly", 0.80),
]

_FRIENDLY_DEFAULT_WEIGHT = 0.80

_ACCENT_MAP = str.maketrans("áéíóúàèìòùãõâêîôûäëïöü", "aeiouaeiouaoaeiouaeiou")


def _competition_weight(competition: str) -> float:
    """Return the competitive weight for a given competition name."""
    if not competition:
        return _FRIENDLY_DEFAULT_WEIGHT
    # Normalize: lowercase + strip accents for reliable substring matching
    comp_norm = competition.lower().translate(_ACCENT_MAP)
    for keyword, weight in _COMP_WEIGHT:
        if keyword in comp_norm:
            return weight
    return 1.00  # unknown competition treated as neutral


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────

def load_team(name: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Load a team record from DB. Tries name then slug."""
    conn = _conn(db_path)
    row = conn.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone()
    if not row:
        slug = name.lower().replace(" ", "_").replace(".", "")
        row = conn.execute("SELECT * FROM teams WHERE slug=?", (slug,)).fetchone()
    if not row:
        # Partial match
        row = conn.execute(
            "SELECT * FROM teams WHERE name LIKE ?", (f"%{name}%",)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def load_squad_ratings(team_name: str, db_path: Optional[Path] = None) -> dict:
    """
    Load squad with ratings per position.
    Returns {GK: [...], DEF: [...], MID: [...], FWD: [...]}
    """
    return rate_squad_from_profiles(team_name, db_path)


def load_recent_form(team_name: str, last_n: int = 15, db_path: Optional[Path] = None) -> list[dict]:
    """Load last N matches for a team from DB."""
    conn = _conn(db_path)
    team_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        slug = team_name.lower().replace(" ", "_")
        team_row = conn.execute("SELECT id FROM teams WHERE slug=?", (slug,)).fetchone()
    if not team_row:
        conn.close()
        return []

    matches = conn.execute("""
        SELECT tm.opponent_name, tm.date, tm.competition, tm.goals_for, tm.goals_against,
               tm.result, tm.venue, t.fifa_ranking as opp_ranking
        FROM team_matches tm
        LEFT JOIN teams t ON t.id = tm.opponent_id
        WHERE tm.team_id=?
        ORDER BY tm.date DESC
        LIMIT ?
    """, (team_row["id"], last_n)).fetchall()
    conn.close()
    return [dict(m) for m in matches]


def load_h2h(team_a: str, team_b: str, last_n: int = 10, db_path: Optional[Path] = None) -> list[dict]:
    """Load direct H2H matches between two teams (last N years)."""
    conn = _conn(db_path)

    a_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_a,)).fetchone()
    b_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_b,)).fetchone()

    if not a_row or not b_row:
        conn.close()
        return []

    a_id, b_id = a_row["id"], b_row["id"]

    matches = conn.execute("""
        SELECT team_id, opponent_id, opponent_name, date, competition,
               goals_for, goals_against, result, venue
        FROM team_matches
        WHERE (team_id=? AND opponent_id=?)
           OR (team_id=? AND opponent_id=?)
        ORDER BY date DESC
        LIMIT ?
    """, (a_id, b_id, b_id, a_id, last_n)).fetchall()

    conn.close()
    return [dict(m) for m in matches]


def load_wc_history(team_name: str, db_path: Optional[Path] = None) -> list[dict]:
    """Load WC history entries for a team."""
    conn = _conn(db_path)
    team_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        conn.close()
        return []

    rows = conn.execute("""
        SELECT year, wc_group, group_stage_result, round_reached,
               goals_scored, goals_conceded, matches_played
        FROM wc_history
        WHERE team_id=?
        ORDER BY year DESC
    """, (team_row["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────
# Scoring sub-functions
# ─────────────────────────────────────────────────────────────────

def form_score(matches: list[dict], team_name: str = "", decay: float = 0.88) -> float:
    """
    Convert recent form into a score [0,1].
    Blends outcome + dominance (goal difference), applies strength-of-schedule
    weighting, and applies a momentum trend multiplier.
    More recent = more weight. Uses exponential decay.
    """
    if not matches:
        return 0.50

    def _score_matches(match_list: list[dict]) -> float:
        """Compute weighted score for a list of matches (no trend)."""
        if not match_list:
            return 0.50
        weights = [decay ** i for i in range(len(match_list))]
        total_weight = 0.0
        score = 0.0
        for i, m in enumerate(match_list):
            result = m.get("result", "D")
            gf = m.get("goals_for", 0) or 0
            ga = m.get("goals_against", 0) or 0
            dominance_ratio = gf / (gf + ga) if (gf + ga) > 0 else 0.5

            # Opponent strength weight: rival FIFA #1 → 1.40, #40 → 1.00, #100 → 0.65
            opp_ranking = m.get("opp_ranking")
            if opp_ranking and opp_ranking < 900:
                opp_w = 1.0 + (40 - opp_ranking) / 90.0
                opp_w = max(0.60, min(1.45, opp_w))
            else:
                opp_w = 1.0

            # Resultado ajustado por calidad del rival:
            # - Perder vs Brasil (FIFA #6) no debe pesar igual que perder vs Costa Rica
            # - La derrota "esperada" vs un rival top no destruye la forma
            if result == "W":
                outcome_pts = 1.0
            elif result == "D":
                # Empate vs rival fuerte = casi una victoria; vs débil = casi una derrota
                outcome_pts = 0.5
            else:  # L
                # Pérdida vs rival top: pena reducida (perder vs Brasil ≠ perder vs Ecuador)
                # vs FIFA #1  → outcome_pts = 0.24 (casi moral, apenas pena)
                # vs FIFA #20 → outcome_pts = 0.12
                # vs FIFA #40 → outcome_pts = 0.0  (derrota esperada/neutra)
                # vs FIFA #80 → outcome_pts = 0.0  (sin crédito por perder con débil)
                if opp_ranking and opp_ranking < 40:
                    outcome_pts = (40 - opp_ranking) / 160.0
                else:
                    outcome_pts = 0.0

            pts = 0.6 * outcome_pts + 0.4 * dominance_ratio

            comp_w = _competition_weight(m.get("competition", ""))

            score += pts * weights[i] * opp_w * comp_w
            total_weight += weights[i] * opp_w * comp_w
        return score / total_weight if total_weight > 0 else 0.50

    score = _score_matches(matches)

    # Momentum direction: compare first half (most recent) vs second half
    mid = max(1, len(matches) // 2)
    recent_score = _score_matches(matches[:mid])
    older_score = _score_matches(matches[mid:]) if len(matches) > mid else recent_score

    trend_mult = 0.95 + 0.10 * (recent_score / max(0.01, older_score))
    trend_mult = max(0.90, min(1.12, trend_mult))

    return max(0.0, min(1.0, score * trend_mult))


def h2h_score(h2h_matches: list[dict], team_id: int) -> float:
    """
    H2H score [0,1] for a specific team with recency decay.
    Applies two independent decay factors:
      1. Match-order decay (0.85 per match) — penalizes older matches in sequence
      2. Time-based decay (year-based) — matches > 4 years old get a steep discount
         so a squad that has completely changed is not penalized/rewarded for history
    """
    if not h2h_matches:
        return 0.50

    import datetime
    current_year = datetime.date.today().year

    total_weight = 0.0
    weighted_score = 0.0
    sequence_decay = 0.85

    for i, m in enumerate(h2h_matches):
        # Sequence decay
        seq_w = sequence_decay ** i

        # Time-based decay: each year older than 2 years → -20% weight
        match_year = int((m.get("date") or "2020-01-01")[:4])
        years_ago = max(0, current_year - match_year)
        if years_ago <= 2:
            time_w = 1.0
        elif years_ago <= 4:
            time_w = 1.0 - (years_ago - 2) * 0.20  # -20%/yr from 3rd year
        else:
            time_w = max(0.10, 1.0 - (years_ago - 2) * 0.25)  # steep after 4 yrs

        w = seq_w * time_w

        if m.get("team_id") == team_id:
            pts = {"W": 1.0, "D": 0.5, "L": 0.0}.get(m.get("result", "D"), 0.5)
        else:
            flip = {"W": 0.0, "L": 1.0, "D": 0.5}
            pts = flip.get(m.get("result", "D"), 0.5)

        weighted_score += pts * w
        total_weight += w

    return round(weighted_score / total_weight, 4) if total_weight > 0 else 0.50


def wc_history_score(history: list[dict]) -> float:
    """
    Score [0,1] based on WC historical performance.
    Weights recent editions more. Returns 0.5 for teams with no WC history.
    """
    if not history:
        return 0.40  # No WC history = below average assumption

    max_points = WC_ROUND_POINTS.get("Champion", 7)
    decay = 0.75  # older editions less important

    total_weight = 0.0
    weighted_pts = 0.0

    for i, ed in enumerate(history):  # already sorted by year DESC
        rnd = ed.get("round_reached", "Did not qualify")
        pts = WC_ROUND_POINTS.get(rnd, 0)
        w = decay ** i
        weighted_pts += pts * w
        total_weight += max_points * w

    if total_weight == 0:
        return 0.40

    return round(weighted_pts / total_weight, 4)


def ranking_factor(ranking: Optional[int], ranking_trend: int = 0) -> float:
    """
    FIFA ranking → score [0,1].
    Uses a calibrated curve based on actual WC win-rate data.
    ranking_trend: positive = improving (moved up), negative = declining.
    """
    if not ranking:
        return 0.50
    # Calibrated sigmoid-like curve: rank 1→0.97, rank 10→0.82, rank 30→0.65,
    # rank 60→0.50, rank 100→0.38, rank 200→0.22
    score = 1.0 / (1.0 + (ranking / 35.0) ** 0.75)
    # Trend bonus: ±2% per 10 positions improved/declined
    if ranking_trend:
        trend_bonus = ranking_trend / 10 * 0.02
        score += trend_bonus
    return round(max(0.15, min(0.97, score)), 4)


def line_rating(players: list[dict]) -> float:
    """Average rating of a line of players (top N used)."""
    if not players:
        return 6.0
    # Use top 3-4 players for each line
    top = sorted(players, key=lambda p: p.get("rating", 6.0), reverse=True)
    n = min(len(top), 4)
    return round(sum(p["rating"] for p in top[:n]) / n, 3)


def gk_rating(gk_players: list[dict]) -> float:
    """Get the starting GK rating (or average if multiple)."""
    if not gk_players:
        return 6.0
    return gk_players[0].get("rating", 6.0)


def scoreline_estimate(
    home_strength: float,
    away_strength: float,
    home_goals_avg: float,
    away_goals_avg: float,
    home_conceded_avg: float,
    away_conceded_avg: float,
) -> tuple[int, int]:
    """
    Estimate the most likely scoreline using Dixon-Coles style attack/defense model.

    Strategy:
    1. Compute Poisson lambdas from attack/defense stats and team strength.
    2. Determine the most probable OUTCOME (home win / draw / away win) by summing
       joint probabilities — avoids the argmax-is-always-draw trap when lambdas ≈ 1.
    3. Return the most probable scoreline *within* that winning outcome.

    home_strength, away_strength: relative team strengths [0.2, 1.2]
    """
    # Attack rating factor — defense multiplier is direct (not inverted).
    # away_conceded_avg / 1.5 < 1.0 means tight defense → attacker scores fewer goals.
    home_attack = (home_goals_avg * home_strength) * max(0.30, away_conceded_avg / 1.5)
    away_attack = (away_goals_avg * away_strength) * max(0.30, home_conceded_avg / 1.5)

    home_lambda = round(max(0.3, min(3.5, home_attack)), 2)
    away_lambda = round(max(0.3, min(3.5, away_attack)), 2)

    # Pre-compute Poisson PMF table (0..6 goals)
    def pmf(lam: float, k: int) -> float:
        return (math.e ** -lam * lam ** k) / math.factorial(k)

    home_pmf = [pmf(home_lambda, k) for k in range(7)]
    away_pmf = [pmf(away_lambda, k) for k in range(7)]

    # Integrate outcome probabilities across the joint distribution
    p_home_win = p_draw = p_away_win = 0.0
    best: dict[str, tuple[int, int, float]] = {
        "home_win": (1, 0, -1.0),
        "draw":     (1, 1, -1.0),
        "away_win": (0, 1, -1.0),
    }
    for h in range(7):
        for a in range(7):
            p = home_pmf[h] * away_pmf[a]
            if h > a:
                p_home_win += p
                if p > best["home_win"][2]:
                    best["home_win"] = (h, a, p)
            elif h == a:
                p_draw += p
                if p > best["draw"][2]:
                    best["draw"] = (h, a, p)
            else:
                p_away_win += p
                if p > best["away_win"][2]:
                    best["away_win"] = (h, a, p)

    # Pick outcome. When the leading outcome dominates by >=8pp, use it.
    # In close matches (margin < 8pp) fall back to joint-argmax, which naturally
    # picks the most probable single scoreline (often a 1-1 draw when λs ≈ 1).
    outcomes = sorted(
        [("home_win", p_home_win), ("draw", p_draw), ("away_win", p_away_win)],
        key=lambda x: x[1], reverse=True
    )
    winner_name, winner_prob = outcomes[0]
    runner_name, runner_prob = outcomes[1]

    if winner_prob - runner_prob >= 0.08:  # clear winner — use outcome-based scoreline
        h, a, _ = best[winner_name]
    else:
        # Close match — find joint argmax (naturally lands on draws when λs ≈ 1)
        best_p = -1.0
        h, a = 1, 1
        for hg in range(7):
            for ag in range(7):
                p = home_pmf[hg] * away_pmf[ag]
                if p > best_p:
                    best_p = p
                    h, a = hg, ag

    return (h, a)


def confidence_level(
    probs: dict,
    data_quality: float = 1.0
) -> tuple[str, float]:
    """
    Compute confidence level of the prediction.
    data_quality: 0-1 (1 = full squad data, 0 = defaults only)
    """
    max_prob = max(probs.values())
    margin = max_prob - sorted(probs.values())[-2]

    raw_confidence = (max_prob * 0.6 + margin * 0.4) * data_quality

    if raw_confidence >= 0.45:
        label = "ALTA"
    elif raw_confidence >= 0.30:
        label = "MEDIA"
    else:
        label = "BAJA"

    return label, round(raw_confidence * 100, 1)


# ─────────────────────────────────────────────────────────────────
# Key matchup analysis
# ─────────────────────────────────────────────────────────────────

def key_matchups(squad_a: dict, squad_b: dict, team_a: str, team_b: str) -> list[dict]:
    """Identify the most interesting player vs player matchups."""
    matchups = []

    # GK vs top FWD
    if squad_a.get("GK") and squad_b.get("FWD"):
        gk = squad_a["GK"][0]
        fwd = squad_b["FWD"][0]
        matchups.append({
            "type": f"{team_b} Attack vs {team_a} GK",
            "player_a": gk["name"],
            "rating_a": gk["rating"],
            "player_b": fwd["name"],
            "rating_b": fwd["rating"],
            "advantage": team_a if gk["rating"] > fwd["rating"] - 0.5 else team_b,
            "margin": round(abs(gk["rating"] - fwd["rating"]), 2),
        })

    if squad_b.get("GK") and squad_a.get("FWD"):
        gk = squad_b["GK"][0]
        fwd = squad_a["FWD"][0]
        matchups.append({
            "type": f"{team_a} Attack vs {team_b} GK",
            "player_a": fwd["name"],
            "rating_a": fwd["rating"],
            "player_b": gk["name"],
            "rating_b": gk["rating"],
            "advantage": team_b if gk["rating"] > fwd["rating"] - 0.5 else team_a,
            "margin": round(abs(fwd["rating"] - gk["rating"]), 2),
        })

    # MID battle
    if squad_a.get("MID") and squad_b.get("MID"):
        mid_a = squad_a["MID"][0]
        mid_b = squad_b["MID"][0]
        matchups.append({
            "type": "Midfield Battle",
            "player_a": mid_a["name"],
            "rating_a": mid_a["rating"],
            "player_b": mid_b["name"],
            "rating_b": mid_b["rating"],
            "advantage": team_a if mid_a["rating"] > mid_b["rating"] else team_b,
            "margin": round(abs(mid_a["rating"] - mid_b["rating"]), 2),
        })

    # Best DEF vs best FWD
    if squad_a.get("DEF") and squad_b.get("FWD"):
        def_a = squad_a["DEF"][0]
        fwd_b = squad_b["FWD"][0]
        matchups.append({
            "type": f"{team_b} Top Forward vs {team_a} Defense",
            "player_a": def_a["name"],
            "rating_a": def_a["rating"],
            "player_b": fwd_b["name"],
            "rating_b": fwd_b["rating"],
            "advantage": team_a if def_a["rating"] >= fwd_b["rating"] else team_b,
            "margin": round(abs(def_a["rating"] - fwd_b["rating"]), 2),
        })

    return matchups


def _adaptive_weights(h2h_available: bool, wc_hist_available: bool) -> dict:
    """Redistribute weights when data is missing."""
    W = {"players": 0.32, "form": 0.25, "h2h": 0.18, "ranking": 0.15, "wc_hist": 0.10}
    if not h2h_available:
        # No direct H2H: redistribute to form (60%) and players (40%)
        freed = W["h2h"]
        W["form"]    += freed * 0.60
        W["players"] += freed * 0.40
        W["h2h"]      = 0.0
    if not wc_hist_available:
        # Debutant or no WC history: redistribute to form (70%) and players (30%)
        freed = W["wc_hist"]
        W["form"]    += freed * 0.70
        W["players"] += freed * 0.30
        W["wc_hist"]  = 0.0
    return W


# ─────────────────────────────────────────────────────────────────
# Main prediction function
# ─────────────────────────────────────────────────────────────────

def predict_match(
    home_name: str,
    away_name: str,
    neutral: bool = True,
    db_path: Optional[Path] = None,
    verbose: bool = False,
    venue: str = "",
) -> dict:
    """
    Full match prediction with line-by-line analysis.

    Returns comprehensive dict with:
      - win/draw/loss probabilities
      - predicted scoreline
      - line-by-line advantage
      - key matchups
      - form analysis
      - H2H or proxy
      - WC history
      - confidence level
    """
    db = db_path or DB_PATH

    # ── 1. Load team records ──
    home_team = load_team(home_name, db)
    away_team = load_team(away_name, db)

    if not home_team:
        raise ValueError(f"Team not found: {home_name}")
    if not away_team:
        raise ValueError(f"Team not found: {away_name}")

    # Resolve actual names from DB
    home_name = home_team["name"]
    away_name = away_team["name"]

    # ── 2. Load squads and rate players ──
    home_squad = load_squad_ratings(home_name, db)
    away_squad = load_squad_ratings(away_name, db)

    home_has_squad = any(home_squad[k] for k in home_squad)
    away_has_squad = any(away_squad[k] for k in away_squad)

    def _squad_coverage(squad: dict) -> float:
        """Fraction of players with ratings above default (6.0)."""
        all_players = [p for pos_list in squad.values() for p in pos_list]
        if not all_players:
            return 0.0
        rated = sum(1 for p in all_players if p.get("rating", 6.0) > 6.5)
        return rated / len(all_players)

    home_coverage = _squad_coverage(home_squad)
    away_coverage = _squad_coverage(away_squad)

    # ── 3. Line ratings ──
    home_gk    = gk_rating(home_squad.get("GK", []))
    home_def   = line_rating(home_squad.get("DEF", []))
    home_mid   = line_rating(home_squad.get("MID", []))
    home_fwd   = line_rating(home_squad.get("FWD", []))
    home_overall = (home_gk * 0.15 + home_def * 0.25 + home_mid * 0.30 + home_fwd * 0.30)

    away_gk    = gk_rating(away_squad.get("GK", []))
    away_def   = line_rating(away_squad.get("DEF", []))
    away_mid   = line_rating(away_squad.get("MID", []))
    away_fwd   = line_rating(away_squad.get("FWD", []))
    away_overall = (away_gk * 0.15 + away_def * 0.25 + away_mid * 0.30 + away_fwd * 0.30)

    # Normalize to [0,1]
    def normalize_rating(r):
        return max(0.1, min(1.0, (r - 4.5) / 5.0))

    home_player_score = normalize_rating(home_overall)
    away_player_score = normalize_rating(away_overall)

    # ── 4. Recent form ──
    home_form_matches = load_recent_form(home_name, 15, db)
    away_form_matches = load_recent_form(away_name, 15, db)

    home_form = form_score(home_form_matches)
    away_form = form_score(away_form_matches)

    # ── 5. H2H ──
    h2h_matches = load_h2h(home_name, away_name, 10, db)
    h2h_available = len(h2h_matches) > 0

    home_team_id = home_team.get("id")
    away_team_id = away_team.get("id")

    if h2h_available:
        home_h2h = h2h_score(h2h_matches, home_team_id)
        away_h2h = h2h_score(h2h_matches, away_team_id)
        h2h_source = "direct"
    else:
        # Use proxy
        proxy = find_proxy_h2h(home_name, away_name, db)
        if proxy.get("available"):
            home_h2h = proxy["win_pct"] / 100.0
            away_h2h = proxy["loss_pct"] / 100.0
            h2h_source = "proxy"
        else:
            home_h2h = 0.50
            away_h2h = 0.50
            h2h_source = "none"
            proxy = None

    # ── 5b. Data quality (requires h2h_available) ──
    h2h_bonus = 0.05 if h2h_available else 0.0
    data_quality = 0.60 + 0.35 * min(home_coverage, away_coverage) + h2h_bonus
    data_quality = round(min(1.0, data_quality), 3)

    # ── 6. WC history ──
    home_wc = load_wc_history(home_name, db)
    away_wc = load_wc_history(away_name, db)

    home_wc_score = wc_history_score(home_wc)
    away_wc_score = wc_history_score(away_wc)

    # ── 7. Ranking factor ──
    home_rank = ranking_factor(home_team.get("fifa_ranking"))
    away_rank = ranking_factor(away_team.get("fifa_ranking"))

    # ── 8. Composite strength score ──
    # Adaptive weights based on data availability
    W = _adaptive_weights(
        h2h_available=h2h_available,
        wc_hist_available=(len(home_wc) > 0 or len(away_wc) > 0),
    )

    home_strength = (
        W["players"]  * home_player_score +
        W["form"]     * home_form +
        W["h2h"]      * home_h2h +
        W["ranking"]  * home_rank +
        W["wc_hist"]  * home_wc_score
    )

    away_strength = (
        W["players"]  * away_player_score +
        W["form"]     * away_form +
        W["h2h"]      * away_h2h +
        W["ranking"]  * away_rank +
        W["wc_hist"]  * away_wc_score
    )

    # Home advantage (in WC all venues are neutral, but some teams can have nearby support)
    home_venue_bonus = 0.0 if neutral else 0.06

    home_strength_adj = home_strength * (1 + home_venue_bonus)

    # ── 9. Probabilities ──
    total_str = home_strength_adj + away_strength
    raw_home = home_strength_adj / total_str
    raw_away = away_strength / total_str

    # Draw probability: higher when teams are balanced (adapted from actual WC stats)
    balance = 1.0 - abs(raw_home - raw_away)
    draw_base = 0.245  # WC average draw rate ~24-25%
    draw_prob = draw_base * balance * (1.0 + 0.1 * balance)  # slight bonus for tight games

    home_win_prob = raw_home * (1.0 - draw_prob / 1.8)
    away_win_prob = raw_away * (1.0 - draw_prob / 1.8)

    # Normalize
    total_p = home_win_prob + draw_prob + away_win_prob
    home_win_prob /= total_p
    draw_prob     /= total_p
    away_win_prob /= total_p

    probs = {
        "home_win": round(home_win_prob, 4),
        "draw":     round(draw_prob,     4),
        "away_win": round(away_win_prob, 4),
    }

    # Most likely outcome
    best_outcome = max(probs, key=probs.get)
    outcome_labels = {
        "home_win": f"Victoria {home_name}",
        "draw":     "Empate",
        "away_win": f"Victoria {away_name}",
    }

    # ── 10. Predicted scoreline ──
    score_h, score_a = scoreline_estimate(
        home_strength=home_strength_adj / 0.6,
        away_strength=away_strength / 0.6,
        home_goals_avg=home_team.get("goals_scored_avg", 1.5),
        away_goals_avg=away_team.get("goals_scored_avg", 1.5),
        home_conceded_avg=home_team.get("goals_conceded_avg", 1.2),
        away_conceded_avg=away_team.get("goals_conceded_avg", 1.2),
    )

    # ── 11. Line-by-line advantage ──
    def advantage(a, b, team_a, team_b):
        if abs(a - b) < 0.15:
            return {"team": "Equal", "margin": 0, "margin_label": "Equilibrado"}
        winner = team_a if a > b else team_b
        return {
            "team": winner,
            "margin": round(abs(a - b), 2),
            "margin_label": "leve" if abs(a - b) < 0.4 else "clara" if abs(a - b) < 0.8 else "contundente",
        }

    line_analysis = {
        "GK": {
            home_name: round(home_gk, 2),
            away_name: round(away_gk, 2),
            "advantage": advantage(home_gk, away_gk, home_name, away_name),
        },
        "DEF": {
            home_name: round(home_def, 2),
            away_name: round(away_def, 2),
            "advantage": advantage(home_def, away_def, home_name, away_name),
        },
        "MID": {
            home_name: round(home_mid, 2),
            away_name: round(away_mid, 2),
            "advantage": advantage(home_mid, away_mid, home_name, away_name),
        },
        "FWD": {
            home_name: round(home_fwd, 2),
            away_name: round(away_fwd, 2),
            "advantage": advantage(home_fwd, away_fwd, home_name, away_name),
        },
        "Overall": {
            home_name: round(home_overall, 2),
            away_name: round(away_overall, 2),
            "advantage": advantage(home_overall, away_overall, home_name, away_name),
        },
    }

    # ── 12. Key matchups ──
    matchups = key_matchups(home_squad, away_squad, home_name, away_name)

    # ── 13. Confidence ──
    conf_label, conf_pct = confidence_level(probs, data_quality)

    # ── 14. Similar teams (context) ──
    similar_to_home = find_similar_teams(home_name, db, top_n=3, exclude=[away_name])
    similar_to_away = find_similar_teams(away_name, db, top_n=3, exclude=[home_name])

    # ── 15. DNA tactical identity & matchup analysis ──
    home_matchup_analysis = ""
    away_matchup_analysis = ""
    try:
        from models.team_dna import get_team_dna, matchup_xg_factor, format_matchup_analysis
        h_dna = get_team_dna(home_name)
        a_dna = get_team_dna(away_name)
        if h_dna and a_dna:
            home_matchup_analysis = format_matchup_analysis(home_name, away_name, h_dna, a_dna)
            away_matchup_analysis = format_matchup_analysis(away_name, home_name, a_dna, h_dna)
    except Exception:
        pass

    # ── Assemble full result ──
    result = {
        "match": f"{home_name} vs {away_name}",
        "home": home_name,
        "away": away_name,
        "neutral_venue": neutral,
        "venue": venue,

        # Core prediction
        "prediction": outcome_labels[best_outcome],
        "predicted_scoreline": f"{score_h}-{score_a}",
        "probabilities": {
            outcome_labels["home_win"]: round(home_win_prob * 100, 1),
            "Empate": round(draw_prob * 100, 1),
            outcome_labels["away_win"]: round(away_win_prob * 100, 1),
        },
        "confidence": {"level": conf_label, "pct": conf_pct},

        # Line analysis
        "line_analysis": line_analysis,

        # Player ratings summary
        "squad_ratings": {
            home_name: {
                "GK": round(home_gk, 2),
                "DEF": round(home_def, 2),
                "MID": round(home_mid, 2),
                "FWD": round(home_fwd, 2),
                "Overall": round(home_overall, 2),
                "top_players": {
                    pos: [{"name": p["name"], "rating": p["rating"], "club": p.get("club","")}
                          for p in home_squad.get(pos, [])[:3]]
                    for pos in ["GK", "DEF", "MID", "FWD"]
                },
            },
            away_name: {
                "GK": round(away_gk, 2),
                "DEF": round(away_def, 2),
                "MID": round(away_mid, 2),
                "FWD": round(away_fwd, 2),
                "Overall": round(away_overall, 2),
                "top_players": {
                    pos: [{"name": p["name"], "rating": p["rating"], "club": p.get("club","")}
                          for p in away_squad.get(pos, [])[:3]]
                    for pos in ["GK", "DEF", "MID", "FWD"]
                },
            },
        },

        # Form analysis
        "form_analysis": {
            home_name: {
                "score": round(home_form * 100, 1),
                "last_10": [
                    {"opponent": m["opponent_name"], "result": m["result"],
                     "score": f"{m['goals_for']}-{m['goals_against']}", "comp": m["competition"]}
                    for m in home_form_matches[:5]
                ],
            },
            away_name: {
                "score": round(away_form * 100, 1),
                "last_10": [
                    {"opponent": m["opponent_name"], "result": m["result"],
                     "score": f"{m['goals_for']}-{m['goals_against']}", "comp": m["competition"]}
                    for m in away_form_matches[:5]
                ],
            },
        },

        # H2H
        "h2h": {
            "source": h2h_source,
            "matches": h2h_matches[:5] if h2h_available else [],
            "summary": {
                home_name: {"wins": sum(1 for m in h2h_matches if m.get("team_id") == home_team_id and m.get("result") == "W"),
                            "h2h_score": round(home_h2h * 100, 1)},
                away_name: {"wins": sum(1 for m in h2h_matches if m.get("team_id") == away_team_id and m.get("result") == "W"),
                            "h2h_score": round(away_h2h * 100, 1)},
                "draws": sum(1 for m in h2h_matches if m.get("result") == "D"),
                "total": len(h2h_matches),
            } if h2h_available else {},
            "proxy": proxy if not h2h_available and proxy else None,
        },

        # WC history
        "wc_history": {
            home_name: {
                "score": round(home_wc_score, 3),
                "editions": home_wc,
            },
            away_name: {
                "score": round(away_wc_score, 3),
                "editions": away_wc,
            },
        },

        # Component breakdown
        "component_scores": {
            home_name: {
                "players": round(home_player_score, 3),
                "form": round(home_form, 3),
                "h2h": round(home_h2h, 3),
                "ranking": round(home_rank, 3),
                "wc_history": round(home_wc_score, 3),
                "composite": round(home_strength_adj, 4),
            },
            away_name: {
                "players": round(away_player_score, 3),
                "form": round(away_form, 3),
                "h2h": round(away_h2h, 3),
                "ranking": round(away_rank, 3),
                "wc_history": round(away_wc_score, 3),
                "composite": round(away_strength, 4),
            },
        },

        # Key matchups
        "key_matchups": matchups,

        # Context
        "team_info": {
            home_name: {
                "fifa_ranking": home_team.get("fifa_ranking"),
                "confederation": home_team.get("confederation"),
                "group": home_team.get("wc_group"),
                "formation": home_team.get("formation"),
                "tactical_style": home_team.get("tactical_style"),
            },
            away_name: {
                "fifa_ranking": away_team.get("fifa_ranking"),
                "confederation": away_team.get("confederation"),
                "group": away_team.get("wc_group"),
                "formation": away_team.get("formation"),
                "tactical_style": away_team.get("tactical_style"),
            },
        },

        "similar_teams": {
            home_name: [f"{t['team_name']} ({t['similarity_score']:.2f})" for t in similar_to_home],
            away_name: [f"{t['team_name']} ({t['similarity_score']:.2f})" for t in similar_to_away],
        },

        # DNA tactical matchup analysis
        "home_matchup_analysis": home_matchup_analysis,
        "away_matchup_analysis": away_matchup_analysis,
    }

    return result


# ─────────────────────────────────────────────────────────────────
# Legacy compatibility (TeamSnapshot API)
# ─────────────────────────────────────────────────────────────────

from dataclasses import dataclass

@dataclass
class TeamSnapshot:
    name: str
    recent_form: list = field(default_factory=list)
    h2h_record: list = field(default_factory=list)
    key_players_available: list = field(default_factory=list)
    key_players_missing: list = field(default_factory=list)
    formation: str = "4-3-3"
    ranking_fifa: Optional[int] = None
    goals_scored_avg: float = 0.0
    goals_conceded_avg: float = 0.0
    possession_avg: float = 50.0
