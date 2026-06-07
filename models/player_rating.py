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

# ---------------------------------------------------------------------------
# League quality multiplier
# Applies to the BONUS above base rating — same stats in a weaker league
# are worth less than the same stats in a top league.
#
# Formula: final = BASE + (raw_bonus) * LEAGUE_QUALITY[league]
# Premier League (1.00) → full value
# Liga Panameña  (0.55) → 55% of the bonus
# ---------------------------------------------------------------------------
LEAGUE_QUALITY: dict[str, float] = {
    # ── Tier 1: Elite (1.00) ──────────────────────────────────────
    "premier league":          1.00,
    "la liga":                 1.00,
    "bundesliga":              1.00,
    "serie a":                 1.00,
    "ligue 1":                 1.00,
    "champions league":        1.05,  # CL level
    "europa league":           0.98,
    # ── Tier 2: Very high (0.92) ──────────────────────────────────
    "eredivisie":              0.92,
    "primeira liga":           0.92,
    "primeira":                0.92,
    "pro league":              0.92,  # Belgium
    "ligue pro":               0.92,  # Belgian Pro League variant
    "first division a":        0.92,  # Belgium alias
    "scottish prem":           0.88,
    "scottish premiership":    0.88,
    "spl":                     0.88,
    "russian premier league":  0.88,
    "rpl":                     0.88,
    # ── Tier 3: High (0.84) ───────────────────────────────────────
    "championship":            0.84,
    "bundesliga 2":            0.84,
    "2. bundesliga":           0.84,
    "serie b":                 0.82,
    "ligue 2":                 0.82,
    "ligue 2 fr":              0.82,
    "süper lig":               0.84,
    "super lig":               0.84,
    "turkish süper lig":       0.84,
    "türkiye süper lig":       0.84,
    "türkiye 1.":              0.84,   # Turkish Süper Lig variant
    "mls":                     0.82,
    "brasileirao":             0.82,
    "brasileirao a":           0.82,
    "liga mx":                 0.82,
    "liga betplay colombia":   0.78,
    "superliga argentina":     0.78,
    "primera division":        0.78,
    "primera division uruguay":0.78,
    "uruguayan primera":       0.78,
    # ── Tier 4: Above average (0.76) ──────────────────────────────
    "k league 1":              0.76,
    "j1 league":               0.76,
    "j-league":                0.76,
    "j league":                0.76,
    "saudi pro league":        0.74,
    "saudi pro":               0.74,
    "allsvenskan":             0.76,
    "superliga":               0.76,   # Denmark / Argentina
    "liga pro arg":            0.76,   # Argentina (variant name)
    "czech liga":              0.76,
    "czech first league":      0.76,
    "austrian bundesliga":     0.76,
    "swiss super league":      0.76,
    "swiss sl":                0.76,
    "ukrainian premier league":0.74,
    "ukrainian":               0.74,
    "a-league":                0.72,
    "eliteserien":             0.74,
    "otb bank liga":           0.74,
    "otp bank":                0.74,
    "otp bank liga":           0.74,
    "hnl":                     0.74,   # Croatia
    "liganet":                 0.74,
    # ── Tier 5: Average (0.68) ────────────────────────────────────
    "psl":                     0.68,   # South Africa Premier Soccer League
    "south african prem":      0.68,
    "qsl":                     0.68,   # Qatar
    "qatar stars league":      0.68,
    "egyptian premier league": 0.68,
    "egypt prem":              0.68,
    "botola pro":              0.68,   # Morocco
    "botola":                  0.68,
    "mtn ligue 1":             0.68,   # Ivory Coast
    "super league":            0.72,   # Greece
    "super league greece":     0.72,
    "ligat":                   0.68,   # Israel
    "k league 2":              0.68,
    "j2 league":               0.68,
    "eerste divisie":          0.70,   # Netherlands second
    "eerste":                  0.70,
    "league one":              0.72,
    "serie a ecuador":         0.65,
    "ligapro ecuador":         0.65,
    "ligapro":                 0.65,
    "division profesional":    0.65,
    "paraguayan primera":      0.65,
    "división pro":            0.65,
    # ── Explicit overrides (prevent substring false-positives) ────
    "serie a brasil":          0.82,  # Brazil Serie A ≠ Italian Serie A
    "campeonato brasileiro":   0.82,
    "campeonato":              0.76,  # Campeonato Mineiro/etc
    "bundesliga at":           0.76,  # Austrian Bundesliga ≠ German
    "bundesliga austria":      0.76,
    "austria bundesliga":      0.76,
    "iran pro league":         0.64,
    "iranian pro league":      0.64,
    "iran premier":            0.64,
    "iraq star league":        0.58,
    "iraq premier":            0.58,
    "jordan league":           0.58,
    "jordan premier":          0.58,
    "liga venezuela":          0.60,
    "liga panama":             0.58,
    "liga bolivia":            0.58,
    "liga uruguay":            0.72,
    "liga colombia":           0.72,
    "liga costa rica":         0.60,
    "liga honduras":           0.60,
    "liga chile":              0.74,
    "primera division chile":  0.74,
    "liga peru":               0.62,
    "liga argentina":          0.78,
    "primera argentina":       0.78,
    "primera division argentina": 0.78,
    "slovenian prvaliga":      0.66,
    "hnk":                     0.66,
    "ekstraklasa":             0.74,
    "polish ekstraklasa":      0.74,
    "ghana premier":           0.56,
    "npfl":                    0.56,  # Nigerian
    "botola pro":              0.64,  # Morocco
    "super league ch":         0.72,  # Swiss Super League
    "super league switzerland":0.72,
    "uae league":              0.62,
    "uae pro league":          0.62,
    "israel premier":          0.66,
    "ligat ha al":             0.66,
    "liga 1 romania":          0.70,
    "liga 1 peru":             0.62,
    "liga 1":                  0.66,  # Romania or Peru
    "superettan":              0.70,
    "allsvenskan":             0.74,
    "belarusian":              0.60,
    "bulgarian pro league":    0.66,
    "bulgarian":               0.66,
    "azerbaijani premier league": 0.62,
    "azerbaijan":              0.62,
    "moldovan premier league": 0.58,
    "chinese super league":    0.68,
    "ipl":                     0.65,
    # ── Tier 6: Below average (0.60) ──────────────────────────────
    "uae pro league":          0.63,
    "uae pro":                 0.63,
    "upl":                     0.60,   # Uzbekistan
    "uzbekistan super league": 0.60,
    "saudi first division":    0.62,
    "jordan pro":              0.58,
    "jordan premier league":   0.58,
    "iraq stars":              0.58,
    "iraqi stars league":      0.58,
    "league of ireland":       0.62,
    "loi":                     0.62,
    "cpl":                     0.62,   # Canadian Premier League
    "primera b":               0.65,
    "primera b colombia":      0.65,
    "liga 3 por":              0.60,
    "segunda federacion":      0.58,
    "segunda division":        0.62,
    "serie b ecuador":         0.60,
    "russian first":           0.70,
    "premier bih":             0.60,
    "Lebanese premier league": 0.55,
    "football league greece":  0.62,
    "first league":            0.64,
    "cypriot first division":  0.64,
    "cyprus first division":   0.64,
    # ── Tier 7: Low (0.55) ────────────────────────────────────────
    "usl":                     0.60,
    "usl championship":        0.60,
    "usl2":                    0.55,
    "haiti nf":                0.50,
    "guadeloupe":              0.50,
    "venezolana":              0.52,
    "venezuelan":              0.52,
    "free":                    0.50,   # Unattached
    "unattached":              0.50,
    "caf":                     0.65,   # CAF club competition
}

# Baseline quality factor when league is unknown or not mapped
_DEFAULT_LEAGUE_QUALITY = 0.70

# ---------------------------------------------------------------------------
# Opponent quality weight for national team match stats.
#
# Same stats (goals, tackles, passes) are worth more against a stronger rival.
# Based on FIFA ranking: rank 1 (France) ≈ 1.30x, rank 50 ≈ 1.00x, rank 120+ ≈ 0.70x
#
# Formula: 1.0 + (REF_RANK - opp_rank) * 0.005, clamped to [0.70, 1.35]
# REF_RANK = 50 (median WC qualifier strength)
# ---------------------------------------------------------------------------
_OPP_REF_RANK = 50
_OPP_SCALE    = 0.005
_OPP_MIN      = 0.70
_OPP_MAX      = 1.35

# FIFA rankings for opponents not in the 48-team WC table (April 2026 reference)
_EXTRA_OPP_RANKS: dict[str, int] = {
    "Wales": 47, "Scotland": 29, "Finland": 55, "Hungary": 31,
    "Sweden": 38, "Norway": 31, "Denmark": 22, "Austria": 23,
    "Switzerland": 17, "Belgium": 9, "Netherlands": 7, "Italy": 9,
    "Portugal": 5, "Spain": 2, "France": 1, "Germany": 10,
    "England": 4, "Croatia": 13, "Serbia": 33, "Romania": 46,
    "Czechia": 41, "Czech Republic": 41, "Slovakia": 45,
    "Poland": 27, "Slovenia": 57, "Greece": 49,
    "Turkey": 24, "Ukraine": 22, "Russia": 35,
    "Republic of Ireland": 62, "Ireland": 62,
    "Northern Ireland": 72, "Iceland": 63, "Albania": 66,
    "Bulgaria": 78, "North Macedonia": 67, "Bosnia and Herzegovina": 65,
    "Montenegro": 74, "Kosovo": 112, "Armenia": 88,
    "Georgia": 52, "Azerbaijan": 108, "Moldova": 130,
    "Belarus": 90, "Estonia": 100, "Latvia": 118, "Lithuania": 125,
    "Kazakhstan": 115, "Kyrgyzstan": 105, "Tajikistan": 110,
    "Turkmenistan": 120, "Uzbekistan": 50,
    "Japan": 12, "South Korea": 18, "Australia": 27,
    "China PR": 87, "Iran": 21, "Saudi Arabia": 26,
    "Iraq": 25, "Jordan": 49, "Syria": 96, "Palestine": 98,
    "Kuwait": 146, "Bahrain": 86, "Oman": 82, "Lebanon": 107,
    "India": 125, "Vietnam": 116, "Thailand": 97, "Malaysia": 130,
    "Indonesia": 130, "Philippines": 140, "Singapore": 160,
    "North Korea": 110,
    "Morocco": 8, "Senegal": 20, "Ghana": 32, "Algeria": 28,
    "Ivory Coast": 34, "Nigeria": 38, "Cameroon": 51, "Egypt": 35,
    "Tunisia": 44, "DR Congo": 47, "Cape Verde": 69,
    "South Africa": 60, "Burkina Faso": 66, "Mali": 56,
    "Benin": 71, "Uganda": 85, "Angola": 92, "Zambia": 97,
    "Tanzania": 120, "Mozambique": 115, "Rwanda": 130,
    "Gambia": 88, "Mauritania": 75, "Ethiopia": 140,
    "Zimbabwe": 110, "Kenya": 105, "Guinea": 78,
    "Equatorial Guinea": 95, "Sudan": 145, "Libya": 140,
    "Madagascar": 150, "Central African Republic": 160,
    "Chad": 165, "Niger": 168, "Malawi": 125, "Togo": 125,
    "Gabon": 85, "Eswatini": 140, "Botswana": 130,
    "Namibia": 120, "Lesotho": 155, "Comoros": 102,
    "Somalia": 190, "São Tomé and Príncipe": 195, "Djibouti": 200,
    "Mexico": 15, "USA": 11, "United States": 11, "Canada": 48,
    "Costa Rica": 64, "Panama": 44, "Honduras": 85, "Jamaica": 50,
    "Haiti": 83, "El Salvador": 77, "Guatemala": 96, "Nicaragua": 135,
    "Cuba": 145, "Dominican Republic": 152, "Trinidad and Tobago": 105,
    "Guadeloupe": 999, "Martinique": 999, "Puerto Rico": 150,
    "Curacao": 82, "Curaçao": 82, "Aruba": 175, "Bermuda": 165,
    "Saint Kitts and Nevis": 180, "Saint Lucia": 185,
    "Suriname": 145, "Grenada": 155, "Guyana": 165, "Barbados": 175,
    "Saint Martin": 190, "Montserrat": 195, "Belize": 185,
    "Argentina": 3, "Brazil": 6, "Colombia": 14, "Uruguay": 16,
    "Ecuador": 19, "Chile": 36, "Paraguay": 30, "Venezuela": 55,
    "Bolivia": 92, "Peru": 68,
    "New Zealand": 85, "Australia": 27, "Fiji": 160,
    "Solomon Islands": 165, "Vanuatu": 170, "Tahiti": 175,
    "New Caledonia": 170, "Samoa": 180,
    "Qatar": 55, "United Arab Emirates": 68, "Kuwait": 146,
    "Bahrain": 86, "Oman": 82,
    "Israel": 86, "Hong Kong": 147, "Bangladesh": 188, "Myanmar": 155,
    "Afghanistan": 206, "Pakistan": 200, "Seychelles": 195,
    "Mauritius": 172, "Liberia": 160, "Bahamas": 190,
    "Guadeloupe": 120, "Martinique": 120,
    "Liechtenstein": 200, "Andorra": 205, "San Marino": 210,
    "Gibraltar": 208, "Faroe Islands": 115, "Malta": 175,
    "Luxembourg": 95, "Cyprus": 92,
}


def get_opponent_rank(opponent_name: str, conn: sqlite3.Connection) -> int:
    """Look up FIFA ranking for an opponent by name. Returns rank integer."""
    if not opponent_name:
        return _OPP_REF_RANK
    # 1. WC teams table
    row = conn.execute(
        "SELECT fifa_ranking FROM teams WHERE name=? OR LOWER(name)=LOWER(?)",
        (opponent_name, opponent_name)
    ).fetchone()
    if row and row[0] and row[0] < 999:
        return row[0]
    # 2. Extended dict
    rank = _EXTRA_OPP_RANKS.get(opponent_name) or _EXTRA_OPP_RANKS.get(opponent_name.title())
    if rank and rank < 999:
        return rank
    # 3. Partial match in dict (e.g. "Republic of Ireland" vs "Ireland")
    opp_lower = opponent_name.lower()
    for key, r in _EXTRA_OPP_RANKS.items():
        if key.lower() in opp_lower or opp_lower in key.lower():
            if r < 999:
                return r
    return 85  # default: treat unknown as a mid-tier team


def opponent_quality_factor(opponent_name: str, conn: sqlite3.Connection) -> float:
    """
    Returns a weight [0.70, 1.35] based on the opponent team's FIFA ranking.
    Stronger opponent → higher factor → stats in that match are worth more.
    """
    rank = get_opponent_rank(opponent_name, conn)
    factor = 1.0 + (_OPP_REF_RANK - rank) * _OPP_SCALE
    return round(max(_OPP_MIN, min(_OPP_MAX, factor)), 3)

# ---------------------------------------------------------------------------
# National team performance normalization by position
# Reference goals-per-cap ratios in WC-level competition
# ---------------------------------------------------------------------------
# FWD baseline lowered from 0.28 → 0.22: the average international FWD scores
# roughly 0.22 goals/cap; 0.28+ is already world-class territory and should
# generate a positive nat_f bonus (as it does for Mbappe, Kane, Lukaku).
_NAT_GPC_BASELINE = {"GK": 0.00, "DEF": 0.04, "MID": 0.10, "FWD": 0.22}
_NAT_GPC_SCALE    = {"GK": 0.00, "DEF": 6.00, "MID": 4.00, "FWD": 2.50}
_NAT_CAPS_WEIGHT  = {0: 0.0, 5: 0.3, 10: 0.5, 20: 0.7, 35: 0.85, 50: 1.0}


def get_league_quality(league: str) -> float:
    """Return quality multiplier [0.50–1.05] for a given league name."""
    if not league:
        return _DEFAULT_LEAGUE_QUALITY
    key = league.strip().lower()
    # Exact match first
    if key in LEAGUE_QUALITY:
        return LEAGUE_QUALITY[key]
    # Substring match (handles "Premier" → "Premier League", etc.)
    for name, q in LEAGUE_QUALITY.items():
        if name in key or key in name:
            return q
    return _DEFAULT_LEAGUE_QUALITY


# Peak age ranges by position — GKs and CBs peak later, FWDs earlier
_PEAK_AGE_START = {"GK": 27, "DEF": 26, "MID": 25, "FWD": 24}
_PEAK_AGE_END   = {"GK": 35, "DEF": 32, "MID": 30, "FWD": 29}


def _age_factor(age: Optional[int], position: str = "MID") -> float:
    """
    Continuous age factor by position.
    Returns multiplier in [0.60, 1.00].
    - Pre-peak: gradual growth (+3%/yr off peak)
    - Peak window: 1.00
    - Post-peak: gradual decline, accelerating past 36
      GK/DEF: -3%/yr to 36, then -5%/yr; MID/FWD: -4%/yr to 36, then -7%/yr
    """
    if age is None:
        return 0.96  # unknown age: slight default penalty

    pos = position if position in _PEAK_AGE_START else "MID"
    peak_start = _PEAK_AGE_START[pos]
    peak_end   = _PEAK_AGE_END[pos]
    steep_age  = 36  # age at which decline accelerates

    if peak_start <= age <= peak_end:
        return 1.00
    elif age < peak_start:
        years_off = peak_start - age
        return max(0.82, 1.00 - years_off * 0.03)
    else:
        years_off_peak = age - peak_end
        base_rate   = 0.03 if pos in ("GK", "DEF") else 0.04
        steep_rate  = 0.05 if pos in ("GK", "DEF") else 0.07

        if age <= steep_age:
            factor = 1.00 - years_off_peak * base_rate
        else:
            # Phase 1: peak_end → steep_age
            phase1 = (steep_age - peak_end) * base_rate
            # Phase 2: steep_age → age (steeper)
            phase2 = (age - steep_age) * steep_rate
            factor = 1.00 - phase1 - phase2

        return round(max(0.60, factor), 3)


def _recency_weight(age: Optional[int], caps: int) -> float:
    """Downweight career stats for older players (stale data)."""
    if age is None or caps == 0:
        return 1.0
    if age <= 32:
        return 1.0
    # Post-32: each year reduces relevance by 8%, min 0.60
    years_past_32 = age - 32
    return max(0.60, 1.0 - years_past_32 * 0.08)


def national_team_factor(caps: int, goals_as_nat: int, position: str, age: Optional[int] = None) -> float:
    """
    Compute an adjustment factor based on national team performance.

    Returns a float centered on 1.0:
    - 1.0 = average international
    - > 1.0 = outstanding nat team performer (e.g. striker with >0.4 goals/cap)
    - < 1.0 = underperforms at national level

    Caps weight: players with <10 caps get a muted factor (small sample size).
    Age-based recency weight: downweights career totals for older players.
    """
    pos = (position or "MID").upper()
    if pos not in _NAT_GPC_BASELINE:
        pos = "MID"

    # Caps experience weight — low caps = small sample → stay near 1.0
    if caps <= 0:
        return 1.0

    # Recency heuristic: downweight career stats for older players
    recency_w = _recency_weight(age, caps)
    effective_goals = goals_as_nat * recency_w
    effective_caps = caps * recency_w

    # caps_w uses effective_caps so older players also lose experience weight
    caps_w = 0.0
    for threshold, weight in sorted(_NAT_CAPS_WEIGHT.items()):
        if effective_caps >= threshold:
            caps_w = weight

    gpc = effective_goals / max(1, effective_caps)
    baseline = _NAT_GPC_BASELINE[pos]
    scale = _NAT_GPC_SCALE[pos]

    # Raw delta from baseline, scaled to ±0.5 range
    raw_delta = (gpc - baseline) * scale
    capped_delta = max(-0.40, min(0.50, raw_delta))

    # Apply caps weight — less experienced players get factor closer to 1.0
    return round(1.0 + capped_delta * caps_w, 4)
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
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
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

        # Per-match averages — proteger contra None en columnas opcionales
        matches = max(1, stats_row["matches"] or 1)
        def _s(v): return v or 0  # None → 0
        avg = ClubMatchStats(
            goals=_s(stats_row["goals"]) / matches,
            assists=_s(stats_row["assists"]) / matches,
            shots_on_target=_s(stats_row["shots_on_target"]) / matches,
            shots_total=max(1, _s(stats_row["shots_on_target"]) / 0.4) if stats_row["shots_on_target"] else 0,
            pass_accuracy=_s(stats_row["pass_accuracy"]),
            dribbles_completed=_s(stats_row["dribbles_completed"]) / matches,
            tackles=_s(stats_row["tackles"]) / matches,
            interceptions=_s(stats_row["interceptions"]) / matches,
            yellow_cards=_s(stats_row["yellow_cards"]) / matches,
            red_cards=_s(stats_row["red_cards"]) / matches,
            minutes=int(_s(stats_row["minutes"]) / matches),
        )

        rc = compute_player_rating(avg, player["position"], context="club")

        # Apply league quality multiplier to bonus above base
        league = stats_row["league"] or ""
        lq = get_league_quality(league)
        base = rc.base  # 6.0
        bonus = rc.final_rating - base
        league_adjusted = round(max(1.0, min(10.0, base + bonus * lq)), 2)
        rc.final_rating = league_adjusted

        # Apply national team factor from player profile
        full_player = cur.execute(
            "SELECT caps, goals_as_nat, position FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if full_player:
            full_player_age = cur.execute(
                "SELECT age FROM players WHERE id=?", (player_id,)
            ).fetchone()
            nat_f = national_team_factor(
                full_player["caps"] or 0,
                full_player["goals_as_nat"] or 0,
                full_player["position"] or "MID",
                age=full_player_age["age"] if full_player_age else None,
            )
            # Nat factor applied with 30% weight to league-adjusted rating
            nat_blend = round(max(1.0, min(10.0, league_adjusted * (0.70 + 0.30 * nat_f))), 2)
            rc.final_rating = nat_blend

        components_json = json.dumps(asdict(rc))
        final_rating = rc.final_rating

        # Write rating using a separate short-lived connection to avoid
        # deadlock when called from rate_team() which holds its own connection.
        try:
            wconn = sqlite3.connect(self.db_path, timeout=30)
            wconn.execute("PRAGMA busy_timeout=30000")
            wconn.execute("""
                INSERT OR REPLACE INTO player_ratings
                    (player_id, match_id, context, rating, components)
                VALUES (?,NULL,'club',?,?)
            """, (player_id, final_rating, components_json))
            wconn.commit()
            wconn.close()
        except Exception:
            pass   # rating will be written by rate_team's conn if needed

        conn.close()
        return final_rating

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
                def _s(v): return v or 0
                matches = max(1, stats_row["matches"] or 1)
                avg = ClubMatchStats(
                    goals=_s(stats_row["goals"]) / matches,
                    assists=_s(stats_row["assists"]) / matches,
                    shots_on_target=_s(stats_row["shots_on_target"]) / matches,
                    pass_accuracy=_s(stats_row["pass_accuracy"]),
                    dribbles_completed=_s(stats_row["dribbles_completed"]) / matches,
                    tackles=_s(stats_row["tackles"]) / matches,
                    interceptions=_s(stats_row["interceptions"]) / matches,
                    yellow_cards=_s(stats_row["yellow_cards"]) / matches,
                    red_cards=_s(stats_row["red_cards"]) / matches,
                    minutes=int(_s(stats_row["minutes"]) / matches),
                )
                rc = compute_player_rating(avg, player["position"], "club")
                club_ratings = [rc.final_rating]

        # Use nat stats
        if not nat_ratings:
            nat_stats = cur.execute("""
                SELECT goals, assists, minutes, rating, opponent
                FROM player_nat_stats
                WHERE player_id=?
                ORDER BY rowid DESC LIMIT 10
            """, (player_id,)).fetchall()
            for ns in nat_stats:
                opp_w = opponent_quality_factor(ns["opponent"] or "", conn)
                if ns["rating"]:
                    # Sofascore rating: adjust bonus above neutral baseline (6.5)
                    base_line = 6.5
                    adjusted = base_line + (ns["rating"] - base_line) * opp_w
                    nat_ratings.append(round(max(1.0, min(10.0, adjusted)), 2))
                else:
                    ms = ClubMatchStats(
                        goals=ns["goals"],
                        assists=ns["assists"],
                        minutes=ns["minutes"]
                    )
                    rc = compute_player_rating(ms, player["position"], "nat")
                    # Apply opponent quality to bonus above base (6.0)
                    adjusted = 6.0 + (rc.final_rating - 6.0) * opp_w
                    nat_ratings.append(round(max(1.0, min(10.0, adjusted)), 2))

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
        Estimate a player's rating combining club league quality + national team performance.

        Formula:
          base = 6.0
          raw_bonus = stats-based bonus (goals/caps, experience, age)
          league_factor = quality multiplier from LEAGUE_QUALITY [0.50–1.05]
          nat_factor = national team performance adjustment [0.60–1.50]
          final = base + raw_bonus * league_factor * nat_factor
        """
        pos    = (player_row["position"] or "MID").upper()
        caps   = player_row["caps"] or 0
        goals  = player_row["goals_as_nat"] or 0
        age    = player_row["age"] or 25
        league = player_row["club_league"] or ""

        # ── 1. League quality multiplier ─────────────────────────────
        lq = get_league_quality(league)

        # ── 2. Experience (caps) bonus — with diminishing returns past 80 ──
        # Prevents retired/senior players from saturating the formula with
        # career-accumulated caps. 80 caps → 0.48, 150 caps → 0.55 (not 0.90).
        if caps <= 80:
            exp_bonus = caps * 0.006
        else:
            exp_bonus = 0.48 + (caps - 80) * 0.001  # much slower past 80 caps
        exp_bonus = min(0.60, exp_bonus)

        # ── 3. Performance bonus (position-specific) ──────────────────
        base = 6.0
        perf_bonus = 0.0
        # Caps contribution also has diminishing returns past 80
        caps_contrib = min(80, caps) * 0.005 + max(0, caps - 80) * 0.001
        if pos == "GK":
            perf_bonus = min(1.0, caps * 0.008)
        elif pos == "DEF":
            if caps > 3:
                gpc = goals / max(1, caps)
                perf_bonus = min(1.0, gpc * 8.0 + caps_contrib)
        elif pos == "MID":
            if caps > 3:
                gpc = goals / max(1, caps)
                perf_bonus = min(1.5, gpc * 4.0 + caps_contrib)
        else:  # FWD
            if caps > 3:
                gpc = goals / max(1, caps)
                perf_bonus = min(2.0, gpc * 3.0 + caps_contrib)

        # ── 4. Age factor (continuous, position-aware) ────────────────
        age_factor = _age_factor(age if player_row["age"] is not None else None, pos)

        # ── 5. National team performance factor ───────────────────────
        nat_f = national_team_factor(caps, goals, pos, age=age if player_row["age"] is not None else None)

        # ── 6. Combine: league quality multiplies the bonus above base ─
        raw_bonus = (perf_bonus + exp_bonus) * lq * nat_f * age_factor
        final = base + raw_bonus

        # ── 7. Elite-league floor: top-5 league starters deserve minimum ──
        # Defenders/GKs/MIDs don't score goals but elite clubs only pick the best.
        # Progressive cap-based floors prevent defensive/creative MIDs from being
        # undervalued purely because they lack a scorer's goals/cap ratio.
        _ELITE_FLOOR = {
            "GK":  7.00,
            "DEF": 7.20,
            "MID": 6.90,
            "FWD": 6.80,
        }
        if lq >= 1.00 and caps >= 15:
            floor = _ELITE_FLOOR.get(pos, 6.80)
            # MID floor: raise to 7.20 — DMs/playmakers with few goals but elite caps
            # deserve parity with DEF floor (7.20). Formula's goal-dependency
            # systematically undervalues holders and box-to-box players.
            if pos == "MID":
                floor = max(7.20, floor)
                # 50+ caps at Tier-1 league = long-term proven starter
                if caps >= 50:
                    floor = max(7.40, floor)
            # Young elite bonus: ≤24, Tier-1 club, 30+ caps = exceptional talent
            # (Bellingham, Gavi, Pedri, Musiala, Camavinga tier)
            if age <= 24 and caps >= 30:
                floor = max(7.50, floor)
            final = max(floor, final)
        elif lq >= 0.92 and caps >= 20:
            final = max(6.50, final)

        # ── 8. Recent nat-team form blend (from player_nat_stats) ────────
        # If we have match ratings in player_nat_stats, use a weighted average
        # of the last 5 matches to slightly adjust the profile-based rating.
        # Effect is intentionally small (±0.3 max) so it doesn't override
        # the structural quality signal.
        try:
            conn_form = self._conn()
            nat_rows = conn_form.execute("""
                SELECT pns.rating, pns.goals, pns.assists, pns.minutes, pns.opponent
                FROM player_nat_stats pns
                WHERE pns.player_id=?
                ORDER BY pns.match_date DESC, pns.rowid DESC
                LIMIT 5
            """, (player_row["id"],)).fetchall()
            conn_form.close()

            if nat_rows:
                pos = (player_row["position"] or "MID").upper()
                adj_ratings = []
                for r in nat_rows:
                    opp_w = opponent_quality_factor(r["opponent"] or "", self._conn())
                    if r["rating"] is not None:
                        base_line = 6.5
                        adj = base_line + (r["rating"] - base_line) * opp_w
                    else:
                        ms = ClubMatchStats(
                            goals=r["goals"] or 0,
                            assists=r["assists"] or 0,
                            minutes=r["minutes"] or 0,
                        )
                        rc = compute_player_rating(ms, pos, "nat")
                        adj = 6.0 + (rc.final_rating - 6.0) * opp_w
                    adj_ratings.append(round(max(1.0, min(10.0, adj)), 2))

                weights = [0.5 ** i for i in range(len(adj_ratings))]
                w_sum = sum(weights)
                nat_form_avg = sum(v * w for v, w in zip(adj_ratings, weights)) / w_sum
                # Blend: 85% structural, 15% nat-form signal, clamped ±0.3
                nat_adj = max(-0.30, min(0.30, (nat_form_avg - final) * 0.15))
                final = round(final + nat_adj, 2)
        except Exception:
            pass  # form data is non-critical

        return round(max(4.5, min(9.8, final)), 2)

    def rate_team(self, team_id: int) -> int:
        """Rate all players in a team; store results in player_ratings. Returns count."""
        conn = self._conn()
        cur  = conn.cursor()
        players = cur.execute(
            "SELECT * FROM players WHERE team_id=?", (team_id,)
        ).fetchall()
        rated = 0
        for p in players:
            season_rating = self.rate_from_club_stats(p["id"])
            if season_rating is None:
                season_rating = self.estimate_rating_from_profile(p)
            if season_rating is None:
                continue
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO player_ratings
                        (player_id, match_id, context, rating, components)
                    VALUES (?,NULL,'nat',?,'{}')
                """, (p["id"], season_rating))
                rated += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return rated


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
        SELECT p.*, ss.confirmed as confirmed
        FROM players p
        LEFT JOIN squad_selections ss ON ss.player_id = p.id AND ss.team_id = p.team_id
        WHERE p.team_id = ?
    """, (team_id,)).fetchall()

    result = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        rating = engine.estimate_rating_from_profile(p)
        pos = p["position"] or "MID"
        if pos not in result:
            pos = "MID"

        # Availability: confirmed=0 means major doubt → penalize rating
        confirmed = p["confirmed"] if "confirmed" in p.keys() else None
        if confirmed == 0:
            rating = round(rating * 0.75, 2)
            availability = "doubt"
        else:
            availability = "available"

        result[pos].append({
            "player_id": p["id"],
            "name": p["name"],
            "club": p["club"],
            "league": p["club_league"],
            "age": p["age"],
            "caps": p["caps"],
            "rating": rating,
            "availability": availability,
        })

    # Sort by rating descending within each position
    for pos in result:
        result[pos].sort(key=lambda x: x["rating"], reverse=True)

    conn.close()
    return result


def compute_all_ratings(teams=None, db_path=None) -> int:
    """Rate all players for all teams (or specific teams). Returns total rated."""
    engine = PlayerRatingEngine(db_path)
    conn = engine._conn()
    if teams:
        placeholders = ",".join("?" * len(teams))
        rows = conn.execute(
            f"SELECT id FROM teams WHERE name IN ({placeholders})", teams
        ).fetchall()
    else:
        rows = conn.execute("SELECT id FROM teams").fetchall()
    conn.close()
    total = 0
    for row in rows:
        total += engine.rate_team(row["id"])
    return total


# Backward-compat alias used by full_update.py
PlayerRater = PlayerRatingEngine


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


def fill_opponent_ranks(db_path=None) -> int:
    """
    Populate opponent_rank for all player_nat_stats rows where it is NULL.
    Looks up FIFA ranking from teams table + _EXTRA_OPP_RANKS dict.
    Returns number of rows updated.
    """
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    opponents = conn.execute(
        "SELECT DISTINCT opponent FROM player_nat_stats WHERE opponent IS NOT NULL AND opponent_rank IS NULL"
    ).fetchall()
    updated = 0
    for (opp,) in opponents:
        rank = get_opponent_rank(opp, conn)
        n = conn.execute(
            "UPDATE player_nat_stats SET opponent_rank=? WHERE opponent=? AND opponent_rank IS NULL",
            (rank, opp)
        ).rowcount
        updated += n
    conn.commit()
    conn.close()
    return updated
