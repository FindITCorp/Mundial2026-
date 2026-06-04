"""
models/match_predictor.py — Motor principal de predicción WC2026.

Factores ponderados:
  30% Diferencia de Elo
  25% xG for/against últimos 10 partidos
  15% Forma reciente ponderada (5 partidos)
  12% Rating promedio XI titular
  10% Set pieces & corners efficiency
   8% Posesión proyectada / pressing matchup

Uso:
    from models.match_predictor import predict_match
    r = predict_match(home_id, away_id, neutral=True)
    print(r)
"""

import sqlite3
import math
import logging
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
log = logging.getLogger("predictor")


def _name_key(name: str) -> str:
    """Clave de identidad por APELLIDO normalizado (sin acentos, minúsculas).
    Permite cruzar 'Edson Álvarez', 'Edson Alvarez' y 'E. Álvarez' como la misma
    persona aunque tengan player_id distintos por duplicados de ingesta."""
    s = unicodedata.normalize("NFD", (name or "").lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    parts = [p for p in s.replace(".", " ").split() if len(p) > 1]
    return parts[-1] if parts else s  # apellido (última palabra significativa)

# Pesos del modelo
WEIGHTS = {
    "elo":        0.30,
    "xg":         0.25,
    "form":       0.15,
    "xi_rating":  0.18,
    "set_pieces": 0.10,
    "possession": 0.08,
}

# ── Parámetros Dixon-Coles (calibración dinámica) ─────────────────────────────
# Nro mínimo de partidos competitivos para confiar en el historial del equipo
MIN_COMP_MATCHES = 5
# Competiciones de alto peso para el cálculo HAS/HDS/AAS/ADS
COMP_KEYWORDS = ("world cup", "copa america", "euro", "nations league",
                 "qualifier", "wcq", "gold cup", "afcon", "asian cup",
                 "confederation")

# ── Importancia de la competición para el cálculo de FORMA ───────────────────
# Un amistoso informa menos sobre la forma real que una eliminatoria o un torneo
# mayor: hay rotaciones, experimentos y menos intensidad competitiva. Estos pesos
# escalan cuánto aporta CADA partido al form_score (datos reales: columna
# team_matches.competition). Regla del proyecto: no recalibra resultados, solo
# pondera la SEÑAL de cada partido según su naturaleza conocida.
COMP_IMPORTANCE = (
    ("world cup qualification", 0.88), ("world cup qualifier", 0.88),
    ("euro qualification", 0.85),      ("euro qualifier", 0.85),
    ("qualification", 0.84),           ("qualifier", 0.84),
    ("world cup", 1.00),
    ("euro", 1.00),
    ("copa américa", 1.00),            ("copa america", 1.00),
    ("nations league", 0.90),
    ("african cup of nations", 0.95),  ("afcon", 0.95),
    ("asian cup", 0.92),
    ("gold cup", 0.90),
    ("concacaf championship", 0.88),   ("concacaf nations", 0.85),
    ("confederations cup", 0.90),      ("confederation", 0.88),
    ("gulf cup", 0.70),                ("arab cup", 0.70),
    ("nordic championship", 0.55),
    ("friendly", 0.45),
)


def _comp_importance(competition: str) -> float:
    """Peso de señal por tipo de competición (amistoso ≪ eliminatoria < torneo)."""
    if not competition:
        return 0.60
    c = competition.lower()
    for kw, w in COMP_IMPORTANCE:
        if kw in c:
            return w
    return 0.65  # competición desconocida → señal media


def _lineup_strength_factor(conn, team_id: int, match_date: str):
    """Fuerza relativa del XI que REALMENTE jugó ese partido vs el equipo que
    irá al Mundial (los 26 convocados oficiales). >1 → jugó el equipo A;
    <1 → equipo rotado/B; ≈0.40 → equipo juvenil/amateur (casi nadie del XI
    está entre los convocados).

    Empatar/ganar con el equipo B no informa lo mismo sobre la forma del XI
    titular del Mundial. Usa datos reales: solapamiento del XI con los 26
    convocados (projected_lineups) + ratio de ratings cuando hay rating 'nat'.
    Devuelve None si no hay alineación real registrada (no inventa datos).
    """
    if not match_date:
        return None
    try:
        starters = conn.execute("""
            SELECT p.name AS name
            FROM player_match_usage pmu
            JOIN players p ON p.id = pmu.player_id
            WHERE pmu.team_id=? AND pmu.is_starter=1
              AND substr(pmu.match_date,1,10)=substr(?,1,10)
        """, (team_id, match_date)).fetchall()
    except sqlite3.OperationalError:
        return None  # tabla aún no poblada (la crea el pipeline de alineaciones)
    if len(starters) < 7:
        return None  # sin alineación real suficiente → no aplicar

    # El mismo jugador puede existir con varios player_id ("Edson Alvarez" vs
    # "Edson Álvarez"), así que el solapamiento con los 26 convocados se mide por
    # NOMBRE NORMALIZADO (apellido), no por id — robusto a duplicados de ingesta.
    squad_names = conn.execute("""
        SELECT p.name FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        WHERE pl.team_id=?
    """, (team_id,)).fetchall()
    squad_keys = {_name_key(r["name"]) for r in squad_names}
    if not squad_keys:
        return None  # sin convocados oficiales → no podemos juzgar la alineación

    hits = sum(1 for s in starters if _name_key(s["name"]) in squad_keys)
    overlap = hits / len(starters)   # 0 = nadie del Mundial jugó; 1 = XI íntegro

    # Solapamiento → factor: 0% convocados ≈ 0.40 (juvenil/B);
    # 100% convocados ≈ 1.00 (equipo A). Lineal y acotado.
    return max(0.40, min(1.10, 0.40 + 0.60 * overlap))


MINNOWS = {
    # Europa
    "Liechtenstein", "Gibraltar", "Faroe Islands", "San Marino", "Andorra",
    "Malta", "Luxembourg", "Latvia", "Estonia", "Kosovo", "Moldova",
    # CONCACAF/Caribbean
    "Montserrat", "Curacao", "Haiti", "Belize", "Barbados", "Bahamas",
    "Cayman Islands", "Puerto Rico", "Antigua and Barbuda", "Grenada",
    "Saint Kitts and Nevis", "Turks and Caicos", "Aruba", "Bermuda",
    # CONCACAF — no clasificaron al WC2026 (FIFA rank >130)
    "Guatemala", "Nicaragua", "El Salvador", "Belize", "Cuba",
    "Dominican Republic", "Trinidad and Tobago", "Suriname",
    # Africa (FIFA rank <120 approx)
    "Zambia", "Mauritania", "Angola", "Djibouti", "Eritrea", "Seychelles",
    "Somalia", "Comoros", "Eswatini", "Lesotho", "South Sudan",
    "Madagascar", "Mozambique", "Rwanda", "Burundi", "Chad",
    # Asia
    "Bhutan", "Timor-Leste", "Macau", "Mongolia", "Guam",
    "Bangladesh", "Pakistan", "Afghanistan", "Nepal", "Maldives",
    "Sri Lanka", "Cambodia", "Laos",
}

HOME_ADV_LAMBDA = 0.08   # +8% goles para el local
BASE_GOALS = 1.22         # referencia goles/partido neutral — calibrado 2026-06-02 (Over2.5 real=53% vs pred=60%)

# ── Goal Timing factors ───────────────────────────────────────────────────────
# fatigue_conceded > 1.3 → equipo vulnerable en 2ª mitad → rival marca más
# Escala: fatigue_conceded 1.0 → factor 1.0; 2.0 → factor 1.08 (max ±10%)
_TIMING_MAX_BOOST = 0.10   # boost máximo al λ rival cuando equipo colapsa tarde


def _get_timing_factor(team_name: str, conn: sqlite3.Connection) -> dict:
    """Retorna fatigue_conceded y fatigue_scored del equipo desde team_goal_timing."""
    row = conn.execute(
        "SELECT fatigue_conceded, fatigue_scored, late_collapse FROM team_goal_timing WHERE team_name=?",
        (team_name,)
    ).fetchone()
    if row:
        return {"fatigue_conceded": row[0], "fatigue_scored": row[1], "late_collapse": bool(row[2])}
    # Sin datos: neutral
    return {"fatigue_conceded": 1.0, "fatigue_scored": 1.0, "late_collapse": False}


def _timing_lambda_boost(defender_timing: dict) -> float:
    """
    Cuánto aumenta λ del atacante por la vulnerabilidad tardía del defensor.
    fatigue_conceded=1.0 → 1.0 (neutro)
    fatigue_conceded=2.0 → 1.08 (+8%)
    Sólo aplica si fatigue_conceded > 1.0 (no penaliza equipos sólidos extra).
    """
    fc = defender_timing["fatigue_conceded"]
    if fc <= 1.0:
        return 1.0
    boost = min(_TIMING_MAX_BOOST, (fc - 1.0) * 0.08)
    return 1.0 + boost


# ── Helpers ───────────────────────────────────────────────────────────────────

def _poisson(lam: float, k: int) -> float:
    return (lam ** k * math.exp(-lam)) / math.factorial(k)


def _get_elo(conn, team_id: int) -> float:
    row = conn.execute(
        "SELECT elo FROM team_elo WHERE team_id=?", (team_id,)
    ).fetchone()
    return row["elo"] if row else 1500.0


# Strength-of-schedule: Elo asumido para rivales que no clasificaron al Mundial
# (no tienen fila en team_elo) — se asume nivel débil-medio.
SOS_DEFAULT_ELO = 1430.0
SOS_PIVOT       = 1550.0   # Elo de rival "neutro"
SOS_EXP         = 1.5      # calibrado 04-jun-2026: reducido de 2.0 → más crédito al ritmo
                            # vs rivales débiles (evidencia: Mexico 4W 2D 0L vs WC sin inflar)
# Regularización bayesiana: prior que regresa los promedios hacia la media
PRIOR_N         = 3.0      # reducido 4.0→3.0: confiar más en forma reciente real
PRIOR_GF        = 1.35
PRIOR_GA        = 1.20


def _is_competitive(competition: str) -> bool:
    if not competition:
        return False
    c = competition.lower()
    return any(kw in c for kw in COMP_KEYWORDS)


def _get_global_goal_averages(conn) -> dict:
    """
    Promedio global de goles marcados/concedidos en partidos competitivos,
    separado por local/visitante. Sirve como denominador en HAS/HDS/AAS/ADS.
    Equivalente al avg_home_scored / avg_away_scored del repo Football_matches.
    """
    rows = conn.execute("""
        SELECT team_id, goals_for, goals_against, venue, competition
        FROM team_matches
        WHERE goals_for IS NOT NULL AND opponent_id IS NOT NULL
    """).fetchall()

    comp = [r for r in rows if _is_competitive(r["competition"])]
    if len(comp) < 200:   # fallback si hay pocos datos competitivos
        comp = list(rows)

    home_gf = [r["goals_for"]  for r in comp if r["venue"] == "home"]
    away_gf = [r["goals_for"]  for r in comp if r["venue"] == "away"]
    neut_gf = [r["goals_for"]  for r in comp if r["venue"] not in ("home", "away")]

    avg_h = sum(home_gf) / len(home_gf) if home_gf else 1.45
    avg_a = sum(away_gf) / len(away_gf) if away_gf else 1.10
    avg_n = sum(neut_gf) / len(neut_gf) if neut_gf else 1.25
    return {"avg_h": avg_h, "avg_a": avg_a, "avg_n": avg_n}


_GLOBAL_AVG_CACHE: dict = {}   # cache por db_path string


def _cached_global_avg(conn, db_key: str) -> dict:
    if db_key not in _GLOBAL_AVG_CACHE:
        _GLOBAL_AVG_CACHE[db_key] = _get_global_goal_averages(conn)
    return _GLOBAL_AVG_CACHE[db_key]


def _get_attack_defense_strength(conn, team_id: int, db_key: str) -> dict:
    """
    Calcula HAS / HDS / AAS / ADS al estilo del repo Football_matches:

      HAS (Home Attacking Strength)  = avg_gf_home / global_avg_home_gf
      HDS (Home Defensive Strength)  = avg_ga_home / global_avg_home_ga
      AAS (Away Attacking Strength)  = avg_gf_away / global_avg_away_gf
      ADS (Away Defensive Strength)  = avg_ga_away / global_avg_away_ga

    Valores > 1 → mejor que la media;  < 1 → peor que la media.
    Incluye regularización bayesiana y SOS weighting por Elo del rival.
    La forma reciente ya está capturada en _get_form (recency-weighted).
    """
    rows = conn.execute("""
        SELECT tm.goals_for, tm.goals_against, tm.venue, tm.competition,
               te.elo AS opp_elo
        FROM team_matches tm
        LEFT JOIN teams opp ON opp.id = tm.opponent_id
        LEFT JOIN team_elo te ON te.team_id = tm.opponent_id
        WHERE tm.team_id=? AND tm.goals_for IS NOT NULL AND tm.opponent_id IS NOT NULL
        ORDER BY tm.date DESC LIMIT 60
    """, (team_id,)).fetchall()

    comp = [r for r in rows if _is_competitive(r["competition"])]
    if len(comp) < MIN_COMP_MATCHES:
        comp = list(rows[:20])

    def _sos_weight(opp_elo):
        elo = opp_elo if opp_elo else SOS_DEFAULT_ELO
        return min(1.5, max(0.4, (elo / SOS_PIVOT) ** 1.0))

    def _weighted_goals(rows_list):
        result = []
        for r in rows_list:
            w = _sos_weight(r["opp_elo"])
            result.append(r["goals_for"] * w)
        return result

    def _weighted_ga(rows_list):
        result = []
        for r in rows_list:
            w = _sos_weight(r["opp_elo"])
            result.append(r["goals_against"] * w)
        return result

    home_matches = [r for r in comp if r["venue"] == "home"]
    away_matches  = [r for r in comp if r["venue"] == "away"]
    neut_matches  = [r for r in comp if r["venue"] not in ("home","away")]

    home_gf = _weighted_goals(home_matches)
    home_ga = _weighted_ga(home_matches)
    away_gf = _weighted_goals(away_matches)
    away_ga = _weighted_ga(away_matches)
    neut_gf = _weighted_goals(neut_matches)
    neut_ga = _weighted_ga(neut_matches)

    g = _cached_global_avg(conn, db_key)

    def _norm_att(vals, global_avg, prior_gf=PRIOR_GF):
        n = len(vals)
        if n == 0:
            return 1.0
        raw = (sum(vals) / n * n + prior_gf * PRIOR_N) / (n + PRIOR_N)
        return raw / global_avg if global_avg else 1.0

    def _norm_def(vals, global_avg, prior_ga=PRIOR_GA):
        n = len(vals)
        if n == 0:
            return 1.0
        raw = (sum(vals) / n * n + prior_ga * PRIOR_N) / (n + PRIOR_N)
        return raw / global_avg if global_avg else 1.0

    # Combinar neutral con home/away (neutral cuenta como ~0.5 de cada uno)
    all_gf = home_gf + neut_gf * 1 + away_gf
    all_ga = home_ga + neut_ga * 1 + away_ga

    HAS = _norm_att(home_gf + neut_gf, g["avg_h"])
    HDS = _norm_def(home_ga + neut_ga, g["avg_a"])
    AAS = _norm_att(away_gf + neut_gf, g["avg_a"])
    ADS = _norm_def(away_ga + neut_ga, g["avg_h"])
    # General (neutral, por si acaso)
    GAS = _norm_att(all_gf, g["avg_n"])
    GDS = _norm_def(all_ga, g["avg_n"])

    # Shots-on-target ratio desde player_club_stats (proxy de presión ofensiva)
    sot_rows = conn.execute("""
        SELECT AVG(pcs.shots_on_target) AS avg_sot
        FROM projected_lineups pl
        JOIN player_club_stats pcs ON pcs.player_id = pl.player_id
            AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchone()
    avg_sot = sot_rows["avg_sot"] if sot_rows and sot_rows["avg_sot"] else 2.5
    # Normalizar: media ~2.5 SOT/jugador/X partidos → factor 0.95–1.05
    sot_factor = max(0.93, min(1.07, avg_sot / 2.5))

    return {
        "HAS": round(HAS, 4), "HDS": round(HDS, 4),
        "AAS": round(AAS, 4), "ADS": round(ADS, 4),
        "GAS": round(GAS, 4), "GDS": round(GDS, 4),
        "sot_factor": round(sot_factor, 4),
        "n_home": len(home_gf), "n_away": len(away_gf),
    }


def _get_form(conn, team_id: int, n: int = 10) -> dict:
    rows = conn.execute("""
        SELECT tm.goals_for gf, tm.goals_against ga, tm.result,
               tm.opponent_name, tm.competition, tm.date AS mdate,
               te.elo AS opp_elo
        FROM team_matches tm
        LEFT JOIN team_elo te ON te.team_id = tm.opponent_id
        WHERE tm.team_id=? AND tm.goals_for IS NOT NULL
        ORDER BY tm.date DESC LIMIT 30
    """, (team_id,)).fetchall()
    filtered = [r for r in rows if r["opponent_name"] not in MINNOWS][:n]
    if not filtered:
        filtered = list(rows[:n])
    if not filtered:
        return {"avg_gf": 1.1, "avg_ga": 1.1, "form_score": 0.40,
                "last5": [], "gp": 0, "wins": 0, "draws": 0, "losses": 0}

    # Peso de SEÑAL por partido: importancia de competición × fuerza del XI real.
    # Amistoso con equipo B aporta poco; eliminatoria con equipo A aporta pleno.
    sig = {}
    for r in filtered:
        ci = _comp_importance(r["competition"])
        lf = _lineup_strength_factor(conn, team_id, r["mdate"])
        sig[id(r)] = ci * (lf if lf is not None else 1.0)

    # ── Strength-of-schedule: ponderar goles por fuerza del rival × señal ─────
    # Marcar/conceder frente a rivales fuertes pesa más que frente a débiles.
    num_gf = num_ga = denom = 0.0
    for r in filtered:
        opp_elo = r["opp_elo"] if r["opp_elo"] is not None else SOS_DEFAULT_ELO
        w = (opp_elo / SOS_PIVOT) ** SOS_EXP * sig[id(r)]
        num_gf += r["gf"] * w
        num_ga += r["ga"] * w
        denom  += w
    w_gf = num_gf / denom if denom else 1.3
    w_ga = num_ga / denom if denom else 1.2

    # ── Regularización bayesiana hacia la media (amortigua extremos) ─────────
    k = len(filtered)
    avg_gf = (w_gf * k + PRIOR_GF * PRIOR_N) / (k + PRIOR_N)
    avg_ga = (w_ga * k + PRIOR_GA * PRIOR_N) / (k + PRIOR_N)

    wins  = sum(1 for r in filtered if r["result"] == "W")
    draws = sum(1 for r in filtered if r["result"] == "D")

    # Ponderación temporal × calidad del rival (SOS-adjusted form_score)
    # Ganar vs rival fuerte vale más; perder vs rival fuerte penaliza menos
    w_pts = 0.0
    max_pts = 0.0
    for i, r in enumerate(reversed(filtered)):
        opp_elo = r["opp_elo"] if r["opp_elo"] is not None else SOS_DEFAULT_ELO
        recency = 1 + i * 0.07
        s = sig[id(r)]                       # señal: competición × fuerza XI real
        opp_factor = (opp_elo / SOS_PIVOT) ** 0.75   # más sensible a calidad rival
        if r["result"] == "W":
            pts = 1.5 * opp_factor          # ganar vs fuerte vale más
        elif r["result"] == "D":
            pts = 0.5 * opp_factor          # empate vs fuerte también vale más
        else:
            # Perder vs rival mucho más fuerte: crédito proporcional a la brecha
            pts = max(0.0, 0.40 * (opp_elo - SOS_PIVOT) / 300)
        w_pts   += pts * recency * s
        max_pts += 1.5 * recency * s        # máximo sigue siendo ganar todo
    # Racha ganadora: boost si los últimos N partidos son todos victorias
    recent = filtered[:5]
    win_streak = 0
    for r in recent:
        if r["result"] == "W":
            win_streak += 1
        else:
            break
    streak_bonus = min(0.12, win_streak * 0.025)   # +2.5% por cada victoria consecutiva, máx +12%
    base_score = w_pts / max_pts if max_pts else 0.40
    form_score = min(1.0, base_score + streak_bonus)

    return {
        "avg_gf":     avg_gf,
        "avg_ga":     avg_ga,
        "form_score": form_score,
        "win_streak": win_streak,
        "last5":      [f'{r["result"]}({r["gf"]}-{r["ga"]})' for r in filtered[:5]],
        "gp": len(filtered), "wins": wins, "draws": draws,
        "losses": len(filtered) - wins - draws,
    }


def _get_xi_rating(conn, team_id: int) -> float:
    """
    Puntuación compuesta del XI titular (0–1) — métricas posicionalmente neutras.

    Pesos:
      rating(30%) + xG(20%) + key_passes(15%) + progressive_carries(15%)
      + pressures(10%) + caps(10%)

    key_passes y progressive_carries capturan la calidad de mediocampistas
    y defensores que xG solo no refleja (Modrić, Gvardiol, Amrabat, etc.)
    Datos reales: StatsBomb WC 2022 (64 partidos, 682 jugadores).
    """
    rows = conn.execute("""
        SELECT p.caps, p.position, p.club_league,
               pr.rating,
               pcs.xg,
               pcs.shots_on_target,
               pcs.key_passes,
               pcs.progressive_carries,
               pcs.pressures,
               pcs.matches,
               pcs.sb_matches
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_ratings pr ON pr.player_id = pl.player_id AND pr.context = 'nat'
        LEFT JOIN player_club_stats pcs ON pcs.player_id = pl.player_id AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    if not rows:
        return 0.40

    # Maximos observados en WC2022 por partido
    RATING_MAX       = 8.0
    XG_PER_GAME_MAX  = 1.20   # Messi ~7.6xG / 7 games
    KP_PER_GAME_MAX  = 3.0    # Griezmann ~2.9kp/game
    PC_PER_GAME_MAX  = 11.0   # Rodrigo ~10.4pc/game
    PRESS_PER_GAME_MAX = 20.0 # Kovacic ~19.4/game
    CAPS_MAX         = 150.0

    # Importar LEAGUE_QUALITY para ajuste por liga
    try:
        from models.player_rating import LEAGUE_QUALITY
    except ImportError:
        LEAGUE_QUALITY = {}

    scores = []
    for r in rows:
        wc_m    = max(1, r["sb_matches"] or 0)
        club_m  = max(1, r["matches"] or 1)
        has_wc  = (r["sb_matches"] or 0) > 0
        has_xg  = r["xg"] is not None and r["xg"] > 0

        # Factor de liga — no es lo mismo 10 goles en la Botola que en la PL
        league_raw = (r["club_league"] or "").lower().strip()
        lq = 1.0
        for key, val in LEAGUE_QUALITY.items():
            if key in league_raw:
                lq = val
                break

        rating_n = min(1.0, r["rating"] / RATING_MAX) if r["rating"] else None
        # xG ajustado por calidad de liga — 0.5 xG/p en PL vale más que en liga panameña
        xg_n     = min(1.0, (r["xg"] or 0.0) * lq / club_m / XG_PER_GAME_MAX)
        caps_n   = min(1.0, (r["caps"] or 0) / CAPS_MAX)

        if has_wc:
            kp_n    = min(1.0, (r["key_passes"] or 0) / wc_m / KP_PER_GAME_MAX)
            pc_n    = min(1.0, (r["progressive_carries"] or 0) / wc_m / PC_PER_GAME_MAX)
            press_n = min(1.0, (r["pressures"] or 0) / wc_m / PRESS_PER_GAME_MAX)
        else:
            kp_n = pc_n = press_n = 0.0

        has_perf = has_wc or has_xg

        if has_wc and rating_n is not None:
            # Full data: WC2022 events + club xG + rating
            score = (0.28 * rating_n
                     + 0.18 * xg_n
                     + 0.18 * kp_n
                     + 0.18 * pc_n
                     + 0.08 * press_n
                     + 0.10 * caps_n)
        elif has_wc:
            # WC2022 events only (no separate rating)
            score = (0.22 * xg_n + 0.22 * kp_n + 0.22 * pc_n
                     + 0.12 * press_n + 0.22 * caps_n)
        elif has_xg and rating_n is not None:
            # Club xG + rating, no WC data (e.g. Italy 2022)
            score = 0.40 * rating_n + 0.40 * xg_n + 0.20 * caps_n
        elif has_xg:
            # Club xG only
            score = 0.65 * xg_n + 0.35 * caps_n
        elif rating_n is not None:
            # Rating only — neutral baseline to avoid inflating weak teams
            score = 0.40 * rating_n + 0.30 * caps_n + 0.30 * 0.22
        else:
            score = 0.40 * caps_n + 0.35 * 0.22

        scores.append(min(1.0, score))

    xi = sum(scores) / len(scores) if scores else 0.40

    # If no starter has tournament event data (sb_matches=0 for all),
    # cap xi — club stats alone (e.g. Haaland's 18xG) don't reflect
    # how a team performs in international tournaments.
    any_tournament = any((r["sb_matches"] or 0) > 0 for r in rows)
    any_club_xg    = any((r["xg"] or 0) > 0 for r in rows)
    if not any_tournament:
        xi = min(xi, 0.62 if any_club_xg else 0.360)

    return xi


def _get_defensive_xi(conn, team_id: int) -> dict:
    """
    Calidad defensiva real del XI basada en métricas StatsBomb por jugador.
    Devuelve índices normalizados de solidez defensiva y presión colectiva.

    Métricas usadas (todas por partido para neutralizar diferencias de muestra):
      - pressures/game  → intensidad de presión colectiva
      - blocks/game     → bloqueos de tiro/pase
      - clearances/game → despejes en zona propia
      - tackles_won/game→ duelos ganados
    """
    rows = conn.execute("""
        SELECT pcs.pressures, pcs.blocks, pcs.clearances,
               pcs.tackles_won, pcs.interceptions, pcs.sb_matches,
               pl.formation_slot
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_club_stats pcs ON pcs.player_id = pl.player_id
            AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    # Máximos de referencia WC2022 por partido
    PRESS_MAX  = 20.0   # Kovacic ~19/game
    BLOCK_MAX  =  2.5   # defender élite
    CLR_MAX    =  6.0   # CB top
    TKL_MAX    =  2.0   # midfielder top
    INTER_MAX  =  2.5

    press_scores, def_scores = [], []
    players_with_data = 0
    for r in rows:
        sb = r["sb_matches"] or 0
        if sb <= 0:
            continue   # skip players with no StatsBomb tournament data
        players_with_data += 1
        m = sb
        press = min(1.0, (r["pressures"] or 0) / m / PRESS_MAX)
        blk   = min(1.0, (r["blocks"]    or 0) / m / BLOCK_MAX)
        clr   = min(1.0, (r["clearances"] or 0) / m / CLR_MAX)
        tkl   = min(1.0, (r["tackles_won"] or 0) / m / TKL_MAX)
        inter = min(1.0, (r["interceptions"] or 0) / m / INTER_MAX)
        press_scores.append(press)
        def_scores.append(0.35 * blk + 0.30 * clr + 0.20 * tkl + 0.15 * inter)

    # If fewer than 3 starters have tournament data, don't apply defensive factor
    # (insufficient sample → use neutral 1.0 to avoid phantom reductions)
    has_data = players_with_data >= 3
    avg_press = sum(press_scores) / len(press_scores) if press_scores else 0.40
    avg_def   = sum(def_scores)   / len(def_scores)   if def_scores   else 0.30

    if has_data:
        press_f = max(0.88, min(1.12, 0.90 + avg_press * 0.40))
        def_f   = max(0.88, min(1.12, 0.90 + avg_def   * 0.60))
        combined = press_f * 0.45 + def_f * 0.55
    else:
        press_f = def_f = combined = 1.0   # neutral — no tournament data to evaluate

    return {
        "press_score": round(avg_press, 3),
        "def_score":   round(avg_def,   3),
        "press_f":     round(press_f,   3),
        "def_f":       round(def_f,     3),
        "combined":    round(combined,  3),   # multiplicador directo sobre lambda rival
        "has_data":    has_data,
    }


def _get_creative_xi(conn, team_id: int) -> dict:
    """
    Capacidad creativa real del XI — qué tan bien genera oportunidades.
    Basada en key_passes + progressive_carries por partido (StatsBomb).

    Diferencia a _get_xi_rating: se enfoca exclusivamente en la
    capacidad de crear oportunidades, no en la calidad general del jugador.
    Permite comparar el ataque de A contra la defensa de B (ver _xi_matchup).
    """
    rows = conn.execute("""
        SELECT pcs.key_passes, pcs.progressive_carries, pcs.xg,
               pcs.shots_on_target, pcs.sb_matches, pcs.matches
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_club_stats pcs ON pcs.player_id = pl.player_id
            AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    KP_MAX = 3.0    # Griezmann ~2.9 kp/game
    PC_MAX = 11.0   # Rodrigo ~10.4 pc/game
    XG_MAX =  1.20  # Messi  ~1.1 xg/game

    kp_scores, pc_scores, xg_scores = [], [], []
    players_with_sb = 0
    for r in rows:
        m_sb  = r["sb_matches"] or 0
        m_club = max(1, r["matches"] or 1)
        if m_sb > 0:
            players_with_sb += 1
            kp_scores.append(min(1.0, (r["key_passes"] or 0) / m_sb / KP_MAX))
            pc_scores.append(min(1.0, (r["progressive_carries"] or 0) / m_sb / PC_MAX))
        if r["xg"] and r["xg"] > 0:
            xg_scores.append(min(1.0, r["xg"] / m_club / XG_MAX))

    has_data = players_with_sb >= 3
    avg_kp  = sum(kp_scores) / len(kp_scores) if kp_scores else 0.20
    avg_pc  = sum(pc_scores) / len(pc_scores) if pc_scores else 0.25
    avg_xg  = sum(xg_scores) / len(xg_scores) if xg_scores else 0.15

    # Índice creativo compuesto (0–1)
    creative_idx = 0.40 * avg_kp + 0.35 * avg_pc + 0.25 * avg_xg
    # Factor multiplicador: only boost/penalize if we have real tournament data
    if has_data:
        creative_f = max(0.92, min(1.10, 0.92 + creative_idx * 0.50))
    else:
        creative_f = 1.0   # neutral — no tournament data

    return {
        "kp_score":     round(avg_kp,       3),
        "pc_score":     round(avg_pc,       3),
        "xg_score":     round(avg_xg,       3),
        "creative_idx": round(creative_idx, 3),
        "creative_f":   round(creative_f,   3),  # boost al lambda propio
        "has_data":     has_data,
    }


def _xi_matchup(att_creative: dict, def_defensive: dict) -> float:
    """
    Compara el índice creativo del atacante vs el índice defensivo del defensor.
    Solo activo cuando ambos equipos tienen datos de torneo StatsBomb (>=3 jugadores).
    Devuelve 1.0 (neutral) cuando falta datos para evitar reducciones fantasma.

    Rango activo: 0.92–1.08
    """
    if not att_creative.get("has_data") or not def_defensive.get("has_data"):
        return 1.0   # no datos suficientes → neutral

    att_idx = att_creative["creative_idx"]
    raw = att_idx - (def_defensive["def_score"] * 0.6 + def_defensive["press_score"] * 0.4)
    return max(0.92, min(1.08, 1.0 + raw * 0.08))


def _get_star_factor(conn, team_id: int) -> float:
    """Factor multiplicador por presencia de jugadores élite en el XI (rating >= 8.5/10)."""
    rows = conn.execute("""
        SELECT pr.rating FROM projected_lineups pl
        LEFT JOIN player_ratings pr ON pr.player_id = pl.player_id AND pr.context = 'nat'
        WHERE pl.team_id = ? AND pl.is_starter = 1 AND pr.rating IS NOT NULL
    """, (team_id,)).fetchall()
    if not rows:
        return 1.0
    stars = sum(1 for r in rows if r["rating"] >= 8.5)
    elite = sum(1 for r in rows if r["rating"] >= 9.0)
    # Cada estrella suma 1.5%, cada élite suma 2.5% extra
    bonus = stars * 0.015 + elite * 0.025
    return min(1.12, 1.0 + bonus)


def _get_club_metrics(conn, team_id: int) -> dict:
    """Métricas del XI desde player_club_stats 2024/25.

    xG se normaliza por partidos jugados (per-game) antes de sumar para evitar
    que jugadores en ligas con más partidos (A-League, MLS) inflen el total.
    Cap por jugador: 0.55 xG/game (striker élite ~0.5/game en top liga).
    """
    rows = conn.execute("""
        SELECT pcs.pass_accuracy, pcs.shots_on_target, pcs.xg, pcs.xa,
               pcs.tackles, pcs.interceptions, pcs.dribbles_completed,
               pcs.matches, pcs.league
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_club_stats pcs ON pcs.player_id = pl.player_id
            AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    # Referencia: 22 partidos (temporada estándar corta / selecciones)
    SEASON_REF = 22.0
    XG_PER_GAME_CAP = 0.55   # cap individual: evita A-League/MLS inflating

    # Descuento por calidad de liga — evita que EST/A-League/MLS inflen xG
    LEAGUE_DISCOUNT = {
        "Premier League": 1.00, "La Liga": 1.00, "Bundesliga": 1.00,
        "Serie A": 1.00, "Ligue 1": 1.00,
        "Eredivisie": 0.87, "Primeira Liga": 0.87, "Championship": 0.80,
        "Scottish Prem": 0.78, "Süper Lig": 0.72, "Czech First League": 0.72,
        "Allsvenskan": 0.70, "Ekstraklasa": 0.70,
        "MLS": 0.68, "Saudi Pro League": 0.68, "Qatar Stars": 0.62,
        "Premier Soccer League": 0.60, "Uzbek League": 0.60,
        "Pro League": 0.78, "WC2022": 0.95,
        "EST": 0.50,      # stats estimadas/generadas — baja confianza
        "Unknown": 0.55,
    }

    m = {k: [] for k in ["pa", "sot", "xg", "xa", "tkl", "inter", "drib"]}
    for r in rows:
        league_q = LEAGUE_DISCOUNT.get(r["league"] or "Unknown", 0.65)
        if r["pass_accuracy"]:  m["pa"].append(r["pass_accuracy"])
        if r["shots_on_target"]: m["sot"].append(r["shots_on_target"])
        if r["xg"] is not None:
            matches = max(1, r["matches"] or 1)
            xg_per_game = min(XG_PER_GAME_CAP, r["xg"] / matches)
            m["xg"].append(xg_per_game * SEASON_REF * league_q)
        if r["xa"] is not None: m["xa"].append(r["xa"])
        if r["tackles"]:        m["tkl"].append(r["tackles"])
        if r["interceptions"]:  m["inter"].append(r["interceptions"])
        if r["dribbles_completed"]: m["drib"].append(r["dribbles_completed"])

    avg = lambda lst, d: sum(lst) / len(lst) if lst else d
    pa   = avg(m["pa"], 75.0)
    club_xg = sum(m["xg"]) if m["xg"] else 0.0

    xg = club_xg   # will be blended with form avg_gf in predict_match
    xa   = sum(m["xa"]) if m["xa"] else 0.0
    sot  = sum(m["sot"]) if m["sot"] else 3.0
    tkl  = avg(m["tkl"], 30.0)
    inter = avg(m["inter"], 25.0)

    # Posesión proxy (pass_accuracy correlaciona con posesión)
    poss = min(72.0, max(38.0, (pa - 70) * 2.5 + 50))
    # Córners proxy
    corners = 3.0 + (xg / 15) * 4.0 + (sot / 60) * 2.0
    # Set pieces: córners + xA (asistencias incluyen centros de BP)
    set_piece_idx = min(9.0, max(2.0, corners * 0.35 + (xa / 8) * 2.0 + 1.5))

    return {
        "pass_acc": round(pa, 1),
        "xg":       round(xg, 3),
        "xa":       round(xa, 3),
        "shots_on": round(sot, 1),
        "possession": round(poss, 1),
        "corners":  round(corners, 2),
        "set_piece_idx": round(set_piece_idx, 2),
        "def_pressure": min(1.0, (tkl + inter) / 120),
    }


def _get_tactics(conn, team_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM team_tactics WHERE team_id=?", (team_id,)
    ).fetchone()
    if row:
        return dict(row)
    return {"formation": "4-4-2", "pressing_intensity": 0.50,
            "defensive_line": "mid", "build_up_style": "mixed"}


def _tactical_matchup(att: dict, def_: dict) -> float:
    """
    Retorna un multiplicador para el lambda del equipo ATACANTE según cómo
    su estilo interactúa con el estilo DEFENSIVO del rival.

    Modela 5 interacciones reales del fútbol:
      1. Bloque bajo vs posesión         → penaliza al equipo de posesión
      2. Línea alta vs juego directo     → favorece al equipo con profundidad
      3. Pressing alto vs build-up corto → el press atrapa al equipo que sale jugando
      4. Juego directo anula el press    → direct bypasses pressing trap
      5. Velocidad de transición        → equipos rápidos en transición explotan espacios

    Rango: 0.80 – 1.20 (cap ±20% para no sobrepasar Elo/forma)
    """
    att_press = att.get("pressing_intensity", 0.60)
    att_line  = att.get("defensive_line", "mid")
    att_build = att.get("build_up_style", "mixed")
    att_trans = att.get("transition_speed", "mid")
    att_aerial = float(att.get("aerial_threat", 0.50) or 0.50)

    def_press  = def_.get("pressing_intensity", 0.60)
    def_line   = def_.get("defensive_line", "mid")
    def_build  = def_.get("build_up_style", "mixed")
    def_block  = def_.get("block_depth", def_line)   # fallback a defensive_line
    def_aerial = float(def_.get("aerial_threat", 0.50) or 0.50)

    m = 1.0

    # ── 1. Bloque bajo (def) vs posesión (att) ──────────────────────────────
    # Equipos que defienden profundo anulan el juego asociativo:
    # Marruecos vs España, Costa Rica vs cualquier top, Uruguay vs Brasil.
    if def_block == "low":
        m *= 0.91                          # baseline: cualquier equipo vs bloque bajo
        if att_build == "short":
            m *= 0.95                      # posesión sufre más: pases laterales sin penetrar
        if att_build == "direct":
            m *= 1.07                      # pelotazos superan el bloque

    # ── 2. Línea alta (def) vs velocidad de transición / juego directo (att) ──
    # Línea alta = espacio detrás. Equipos con transición rápida la explotan.
    # Alemania línea alta vs Francia Mbappé / Brasil Vinicius.
    if def_line == "high":
        if att_trans == "high":
            m *= 1.11                      # contraataque letal contra línea alta
        elif att_trans == "mid":
            m *= 1.05
        if att_build == "direct":
            m *= 1.07                      # pelotazo sobre la línea alta

    # ── 3. Pressing alto (def) atrapa build-up corto (att) ─────────────────
    # Press intenso roba balón en zona peligrosa cuando el rival sale jugando.
    # España press 0.85 vs equipos que intentan salir corto.
    if def_press >= 0.72 and att_build == "short":
        m *= 0.91                          # el press les corta la salida
    elif def_press >= 0.72 and att_build == "direct":
        m *= 1.03                          # juego largo pasa por encima del press

    # ── 4. Press propio del atacante roba balón si rival sale corto (def) ──
    # Cuando YO presiono alto y el RIVAL intenta salir jugando: gano balón alto.
    if att_press >= 0.72 and def_build == "short":
        m *= 1.08                          # presión propia genera oportunidades
    elif att_press >= 0.72 and def_build == "direct":
        m *= 0.97                          # el rival sortea mi press con pelotazos

    # ── 5. Amenaza aérea del atacante vs bloque defensivo ──────────────────
    # Equipos físicos/aéreos son más peligrosos contra bloques bajos (corners,
    # free kicks). Marruecos, Norway, Uruguay explotan set pieces de esta forma.
    if att_aerial >= 0.65 and def_block == "low":
        m *= 1.06                          # más corners + free kicks en bloque bajo
    if att_aerial >= 0.65 and def_block == "high":
        m *= 0.97                          # rival ocupa bien el área, menos espacio aéreo

    # ── 6. Velocidad de transición del atacante vs defensa desorganizada ────
    # Equipos de contraataque son más letales cuando el rival ataca y deja espacio.
    # Proxy: rival pressing > 0.68 = sube mucho = deja espacio atrás.
    if att_trans == "high" and def_press >= 0.68:
        m *= 1.05                          # rival sube mucho → contraataque

    # ── Cap ─────────────────────────────────────────────────────────────────
    return max(0.80, min(1.20, m))


def _get_h2h(conn, tid1: int, tid2: int, n: int = 8) -> dict:
    # Solo últimos 6 años: el squad cambia completamente. H2H de 2015 no es útil para 2026.
    rows = conn.execute("""
        SELECT goals_for gf, goals_against ga, result
        FROM team_matches
        WHERE team_id=? AND opponent_id=? AND date >= '2019-01-01'
        ORDER BY date DESC LIMIT ?
    """, (tid1, tid2, n)).fetchall()
    if not rows:
        return {"hw": 0, "aw": 0, "d": 0, "gp": 0}
    return {
        "hw":  sum(1 for r in rows if r["result"] == "W"),
        "aw":  sum(1 for r in rows if r["result"] == "L"),
        "d":   sum(1 for r in rows if r["result"] == "D"),
        "gp":  len(rows),
    }


# ── Motor principal ────────────────────────────────────────────────────────────

def predict_match(
    home_id: int,
    away_id: int,
    neutral: bool = True,
    home_absence: float = 0.0,   # 0–0.3: penalización por bajas clave
    away_absence: float = 0.0,
    db_path: str | Path = DB_PATH,
    use_strength: bool = True,   # activar mejora HAS/HDS/AAS/ADS
) -> dict:
    """
    Retorna un dict completo con predicción, probabilidades, métricas y breakdown.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # ── 1. Recopilar datos ────────────────────────────────────────────────
    db_key    = str(db_path)
    home_elo  = _get_elo(conn, home_id)
    away_elo  = _get_elo(conn, away_id)
    home_form = _get_form(conn, home_id)
    away_form = _get_form(conn, away_id)
    home_xi   = _get_xi_rating(conn, home_id)
    away_xi   = _get_xi_rating(conn, away_id)
    home_club = _get_club_metrics(conn, home_id)
    away_club   = _get_club_metrics(conn, away_id)
    home_tac    = _get_tactics(conn, home_id)
    away_tac    = _get_tactics(conn, away_id)
    h2h         = _get_h2h(conn, home_id, away_id)
    # Rendimiento real del XI — métricas defensivas y creativas StatsBomb
    h_def_xi  = _get_defensive_xi(conn, home_id)
    a_def_xi  = _get_defensive_xi(conn, away_id)
    h_cre_xi  = _get_creative_xi(conn, home_id)
    a_cre_xi  = _get_creative_xi(conn, away_id)
    # Matchup creativo vs defensivo: ataque A vs defensa B y viceversa
    h_xi_matchup = _xi_matchup(h_cre_xi, a_def_xi)   # cuánto crea local vs defensa rival
    a_xi_matchup = _xi_matchup(a_cre_xi, h_def_xi)   # cuánto crea visitante vs defensa local
    # Nuevas métricas Dixon-Coles (repo Football_matches)
    if use_strength:
        h_str = _get_attack_defense_strength(conn, home_id, db_key)
        a_str = _get_attack_defense_strength(conn, away_id, db_key)

    home_name = conn.execute("SELECT name FROM teams WHERE id=?", (home_id,)).fetchone()["name"]
    away_name = conn.execute("SELECT name FROM teams WHERE id=?", (away_id,)).fetchone()["name"]

    # Timing profiles (fatiga defensiva/ofensiva por franja de 15 minutos)
    h_timing = _get_timing_factor(home_name, conn)
    a_timing = _get_timing_factor(away_name, conn)
    conn.close()

    # ── 2. Factor Elo (30%) ───────────────────────────────────────────────
    elo_diff  = home_elo - away_elo
    elo_adj   = 0 if neutral else 50
    e_home    = 1.0 / (1.0 + 10 ** (-(elo_diff + elo_adj) / 400))
    elo_lambda_h = BASE_GOALS * (0.60 + e_home * 0.80)    # 0.60–1.40 escala ampliada
    elo_lambda_a = BASE_GOALS * (0.60 + (1 - e_home) * 0.80)

    # ── 3. Factor xG / forma (25% + 15%) ─────────────────────────────────
    h_att_form = min(1.70, home_form["avg_gf"] / BASE_GOALS)
    a_att_form = min(1.70, away_form["avg_gf"] / BASE_GOALS)
    h_att_elo  = (home_elo / 1550.0)
    a_att_elo  = (away_elo / 1550.0)
    h_att = (h_att_form ** 0.55) * (h_att_elo ** 0.45)
    a_att = (a_att_form ** 0.55) * (a_att_elo ** 0.45)
    # h_def = susceptibilidad defensiva del local. Alto → fácil de anotar contra él.
    # Equipos que conceden poco (avg_ga bajo) tienen h_def bajo → reducen goles del rival. ✓
    h_def = max(0.45, min(1.60, home_form["avg_ga"] / BASE_GOALS)) ** 0.70
    a_def = max(0.45, min(1.60, away_form["avg_ga"] / BASE_GOALS)) ** 0.70

    # ── 3b. Fuerza histórica normalizada — Dixon-Coles ───────────────────────
    # GAS/GDS son susceptibilidades normalizadas (< 1.0 = mejor que media).
    # lh (goles local) = GAS_H × GDS_A (cuánto concede el RIVAL al atacante)
    # la (goles visitante) = GAS_A × GDS_H
    # IMPORTANTE: se usan directamente, NO invertidos con 1/GDS.
    if use_strength:
        if neutral:
            h_dc_att = h_str["GAS"]          # ataque local
            a_dc_def = a_str["GDS"]          # susceptibilidad defensiva del RIVAL (afecta lh)
            a_dc_att = a_str["GAS"]          # ataque visitante
            h_dc_def = h_str["GDS"]          # susceptibilidad defensiva del LOCAL (afecta la)
        else:
            h_dc_att = h_str["HAS"]
            a_dc_def = a_str["ADS"]          # away defensive susceptibility (afecta lh)
            a_dc_att = a_str["AAS"]
            h_dc_def = h_str["HDS"]          # home defensive susceptibility (afecta la)
        h_sot_f = h_str["sot_factor"]
        a_sot_f = a_str["sot_factor"]
        # Cap: ataque máx ±40%, defensa susceptibilidad máx ±35%
        h_dc_att = max(0.75, min(1.40, h_dc_att))
        a_dc_att = max(0.75, min(1.40, a_dc_att))
        h_dc_def = max(0.65, min(1.35, h_dc_def))
        a_dc_def = max(0.65, min(1.35, a_dc_def))
    else:
        h_dc_att = a_dc_att = h_dc_def = a_dc_def = 1.0
        h_sot_f = a_sot_f = 1.0

    # ── xG factor: blend 40% club individual + 60% national team form avg_gf ──
    # Usa home_form["avg_gf"] que ya filtra minnows y partidos irrelevantes.
    # Esto captura el estilo del equipo (España sistema vs Argentina contragolpe)
    # sin distorsionar por ligas débiles (MLS Messi) ni posición (Pedri 0.089 xG/g).
    SEASON_REF_XG = 22.0
    def _blend_xg(club_xg, form_avg_gf):
        team_xg = form_avg_gf * 0.85 * SEASON_REF_XG   # goles → escala xG
        return 0.40 * club_xg + 0.60 * team_xg

    h_xg_blend = _blend_xg(home_club["xg"], home_form["avg_gf"])
    a_xg_blend = _blend_xg(away_club["xg"], away_form["avg_gf"])

    # Mediana WC-qualified teams = 22.9. Cap ±15%: diferencia elite de promedio,
    # no intenta separar Argentina de España (eso lo hacen Elo + HAS/AAS).
    # Fix clave: España pasa de 0.88 (penalizado) a 1.15 (elite) gracias al blend.
    xg_ref   = 23.0
    h_xg_f   = max(0.86, min(1.15, h_xg_blend / xg_ref)) if h_xg_blend > 0 else 1.0
    a_xg_f   = max(0.86, min(1.15, a_xg_blend / xg_ref)) if a_xg_blend > 0 else 1.0

    h_form_f = 0.80 + 0.40 * home_form["form_score"]
    a_form_f = 0.80 + 0.40 * away_form["form_score"]

    # ── 4. Rating XI (12%) ────────────────────────────────────────────────
    # Factor XI: normalizado contra la media real de todos los equipos WC (0.265)
    # Equipos sobre la media reciben bonus, bajo la media reciben penalización
    # Cap 0.75–1.40 para evitar distorsiones por cobertura incompleta de datos
    XI_PIVOT   = 0.312  # media real del score XI entre equipos WC (WC2022 + Euro2024 + CA2024 + WC2018)
    h_xi_f     = min(1.40, max(0.75, home_xi / XI_PIVOT))
    a_xi_f     = min(1.40, max(0.75, away_xi / XI_PIVOT))

    # ── 5. Set pieces (10%) ───────────────────────────────────────────────
    avg_sp    = (home_club["set_piece_idx"] + away_club["set_piece_idx"]) / 2 or 3.5
    h_sp_f    = 1.0 + (home_club["set_piece_idx"] - avg_sp) / avg_sp * 0.10
    a_sp_f    = 1.0 + (away_club["set_piece_idx"] - avg_sp) / avg_sp * 0.10

    # ── 6. Interacción táctica completa ───────────────────────────────────
    # _tactical_matchup(atacante, defensor) → multiplicador del lambda atacante.
    # Modela: bloque bajo vs posesión, línea alta vs transición,
    # pressing trap, amenaza aérea, velocidad de contraataque.
    h_tac_f = _tactical_matchup(home_tac, away_tac)   # cómo ataca local vs defensa rival
    a_tac_f = _tactical_matchup(away_tac, home_tac)   # cómo ataca visitante vs defensa local

    # Pressing diferencial — captura ventaja de intensidad (conservado, peso reducido)
    press_diff = home_tac["pressing_intensity"] - away_tac["pressing_intensity"]
    h_press_f  = 1.0 + press_diff * 0.04
    a_press_f  = 1.0 - press_diff * 0.04

    # ── 7. H2H ────────────────────────────────────────────────────────────
    h2h_hf = 1.0; h2h_af = 1.0
    if h2h["gp"] >= 4:
        t = h2h["gp"]
        h2h_hf = 0.85 + 0.30 * (h2h["hw"] / t)
        h2h_af = 0.85 + 0.30 * (h2h["aw"] / t)

    # ── 8. Venue ──────────────────────────────────────────────────────────
    venue_h = 1.0 if neutral else (1.0 + HOME_ADV_LAMBDA)
    venue_a = 1.0 if neutral else (1.0 - HOME_ADV_LAMBDA * 0.7)

    # ── 9. Combinar con pesos ─────────────────────────────────────────────
    w = WEIGHTS
    ELO_LAMBDA_EXP = 1.10
    DC_EXP = 0.40
    lh_raw = (
        BASE_GOALS
        * h_att * a_def                              # ataque vs defensa (forma)
        * (h_dc_att * a_dc_def) ** DC_EXP           # HAS × ADS (Dixon-Coles)
        * (elo_lambda_h / BASE_GOALS) ** ELO_LAMBDA_EXP
        * h_xg_f    ** (w["xg"] * 2)
        * h_form_f  ** (w["form"] * 2)
        * h_xi_f    ** (w["xi_rating"] * 2)
        * h_sp_f    ** (w["set_pieces"] * 2)
        * h_press_f ** (w["possession"] * 2)
        * h_sot_f ** 0.5
        * h_tac_f                                    # interacción táctica (estilo)
        * h_xi_matchup                               # creación real local vs defensa rival (1.0 si sin datos)
        * (1.0 / max(0.88, a_def_xi["combined"]) if a_def_xi["has_data"] else 1.0)
        * h2h_hf
        * venue_h
        * (1 - home_absence)
    )
    la_raw = (
        BASE_GOALS
        * a_att * h_def
        * (a_dc_att * h_dc_def) ** DC_EXP
        * (elo_lambda_a / BASE_GOALS) ** ELO_LAMBDA_EXP
        * a_xg_f    ** (w["xg"] * 2)
        * a_form_f  ** (w["form"] * 2)
        * a_xi_f    ** (w["xi_rating"] * 2)
        * a_sp_f    ** (w["set_pieces"] * 2)
        * a_press_f ** (w["possession"] * 2)
        * a_sot_f ** 0.5
        * a_tac_f                                    # interacción táctica (estilo)
        * a_xi_matchup                               # creación real visitante vs defensa local (1.0 si sin datos)
        * (1.0 / max(0.88, h_def_xi["combined"]) if h_def_xi["has_data"] else 1.0)
        * h2h_af
        * venue_a
        * (1 - away_absence)
    )

    # ── 9b. Ajuste por timing defensivo (fatiga en 2ª mitad) ─────────────────
    # Si el equipo defensor colapsa tarde, el atacante marca un poco más de lo
    # que indican forma + Elo solos → convierte "2-0 probable" en "2-1 probable"
    h_timing_boost = _timing_lambda_boost(a_timing)   # local ataca vs defensa visitante
    a_timing_boost = _timing_lambda_boost(h_timing)   # visitante ataca vs defensa local
    lh = min(max(lh_raw * h_timing_boost, 0.20), 3.50)
    la = min(max(la_raw * a_timing_boost, 0.20), 3.50)

    # ── 10. Distribución Poisson ──────────────────────────────────────────
    probs = {}
    ph = pd = pa = 0.0
    for i in range(8):
        for j in range(8):
            p = _poisson(lh, i) * _poisson(la, j)
            probs[(i, j)] = p
            if i > j:   ph += p
            elif i == j: pd += p
            else:        pa += p
    total = sum(probs.values())
    ph /= total; pd /= total; pa /= total

    # ── 10b. Rebalanceo de empates — calibrado 04-jun-2026 ───────────────
    # Evidencia: 4/4 empates predichos el 02-jun resultaron ganador claro.
    # Reducción total ~50% respecto a versión anterior.
    # Criterio: solo aplicar boost cuando HAY señal fuerte y múltiple.
    draw_boost = 0.0

    # Señal 1: Elo muy parejo (reducido: solo gap < 25 activa boost significativo)
    elo_gap = abs(elo_diff)
    if elo_gap < 25:
        draw_boost += 0.015
    elif elo_gap < 50:
        draw_boost += 0.008
    elif elo_gap < 80:
        draw_boost += 0.003

    # Señal 2: Forma reciente casi idéntica (umbral más estricto)
    form_gap = abs(home_form["form_score"] - away_form["form_score"])
    if form_gap < 0.04:
        draw_boost += 0.008
    elif form_gap < 0.08:
        draw_boost += 0.003

    # Señal 3: H2H con historial de empates (solo si dato robusto)
    if h2h["gp"] >= 5:
        draw_rate = h2h["d"] / h2h["gp"]
        if draw_rate >= 0.45:
            draw_boost += 0.010
        elif draw_rate >= 0.35:
            draw_boost += 0.004

    # Señal 4: Lambdas muy similares (solo si ratio > 0.94 — muy equilibrado)
    lambda_ratio = min(lh, la) / max(lh, la) if max(lh, la) > 0 else 1.0
    if lambda_ratio > 0.94:
        draw_boost += 0.008
    elif lambda_ratio > 0.88:
        draw_boost += 0.003

    # Señal 5: Neutral + Elo muy parejo (solo gap < 40)
    if neutral and elo_gap < 40:
        draw_boost += 0.003

    # Cap: máximo boost de +3.5pp (antes 5pp)
    draw_boost = min(draw_boost, 0.035)

    # Redistribuir proporcionalmente de p_home y p_away
    if draw_boost > 0.001:
        steal_h = draw_boost * (ph / (ph + pa)) if (ph + pa) > 0 else draw_boost / 2
        steal_a = draw_boost * (pa / (ph + pa)) if (ph + pa) > 0 else draw_boost / 2
        ph = max(0.05, ph - steal_h)
        pa = max(0.05, pa - steal_a)
        pd = min(0.55, pd + draw_boost)
        # Renormalizar
        _t = ph + pd + pa
        ph /= _t; pd /= _t; pa /= _t

    top_scores = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:8]
    # Re-normalizar probs dict para que top_scores use escala consistente
    prob_total_raw = sum(probs.values())

    # ── 11. Posesión proyectada ───────────────────────────────────────────
    h_poss_raw = home_club["possession"] + (home_xi - away_xi) * 10 \
                 + (home_tac["pressing_intensity"] - 0.5) * 8
    a_poss_raw = away_club["possession"] + (away_xi - home_xi) * 10 \
                 + (away_tac["pressing_intensity"] - 0.5) * 8
    t_poss = h_poss_raw + a_poss_raw
    h_poss = round(h_poss_raw / t_poss * 100, 1) if t_poss else 50.0
    a_poss = round(100 - h_poss, 1)

    # ── 12. Córners proyectados ───────────────────────────────────────────
    tc = home_club["corners"] + away_club["corners"]
    h_corners = round(home_club["corners"] / tc * 9.5, 1) if tc else 4.8
    a_corners = round(9.5 - h_corners, 1)

    # ── 13. Goles de balón parado ─────────────────────────────────────────
    h_sp_goals = round(lh * 0.27, 2)
    a_sp_goals = round(la * 0.27, 2)

    # ── 14. Confianza del modelo ──────────────────────────────────────────
    elo_conf   = min(1.0, abs(elo_diff) / 300)
    form_conf  = abs(home_form["form_score"] - away_form["form_score"])
    h2h_conf   = (max(h2h["hw"], h2h["aw"]) / h2h["gp"]) if h2h["gp"] >= 4 else 0.0
    confidence = round((elo_conf * 0.4 + form_conf * 0.35 + h2h_conf * 0.25), 3)

    # Predicción final — calibrado 04-jun-2026:
    # Evidencia: umbral anterior (pd>=20% + gap<15pp) generó 4/4 falsos empates.
    # Nuevo criterio más estricto: pd debe ser la prob MÁS ALTA y gap < 10pp.
    draw_gap = abs(ph - pa)
    if pd > ph and pd > pa and draw_gap < 0.10:
        winner = "DRAW"
    elif ph >= pa:
        winner = home_name
    else:
        winner = away_name
    pred = top_scores[0][0]

    # ── Goleada band: cuando la diferencia Elo es extrema (>350) ─────────────
    # En vez de reportar un solo marcador, se reporta la banda de goleada más probable
    elo_diff_abs = abs(elo_diff)
    goleada_band = None
    dominant = home_name if lh > la else away_name
    dominant_lambda = max(lh, la)
    weak_lambda = min(lh, la)
    if elo_diff_abs > 350 and dominant_lambda > 2.5:
        # Acumular probabilidad de marcadores con ≥3 goles del dominante y ≤1 del débil
        goleada_probs = {}
        for (h, a), p in probs.items():
            dom_g = h if lh > la else a
            weak_g = a if lh > la else h
            if dom_g >= 3 and weak_g <= 1:
                s = f"{h}-{a}" if lh > la else f"{h}-{a}"
                goleada_probs[(h, a)] = p
        if goleada_probs:
            goleada_total = sum(goleada_probs.values()) / prob_total_raw * 100
            goleada_top = sorted(goleada_probs.items(), key=lambda x: -x[1])[:3]
            goleada_band = {
                "dominant": dominant,
                "prob_pct": round(goleada_total, 1),
                "top_scores": [(f"{h}-{a}", round(p/prob_total_raw*100, 1))
                               for (h, a), p in goleada_top],
            }

    return {
        # Identidad
        "home": home_name,
        "away": away_name,
        # Predicción principal
        "predicted_score": f"{pred[0]}-{pred[1]}",
        "winner":           winner,
        "confidence":       confidence,
        "goleada_band":     goleada_band,   # None si elo_diff <= 350; dict si goleada probable
        # Probabilidades (rebalanceadas por W-5 draw boost)
        "prob_home_win":   round(ph * 100, 1),
        "prob_draw":       round(pd * 100, 1),
        "prob_away_win":   round(pa * 100, 1),
        "draw_boost":      round(draw_boost * 100, 1),   # cuánto se boosteó el empate
        # Goles esperados
        "lambda_home":     round(lh, 3),
        "lambda_away":     round(la, 3),
        # Timing / fatiga por franjas
        "timing_home_fatigue_def":  round(h_timing["fatigue_conceded"], 2),
        "timing_away_fatigue_def":  round(a_timing["fatigue_conceded"], 2),
        "timing_home_late_collapse": h_timing["late_collapse"],
        "timing_away_late_collapse": a_timing["late_collapse"],
        # Métricas de dominio
        "possession_home": h_poss,
        "possession_away": a_poss,
        "corners_home":    h_corners,
        "corners_away":    a_corners,
        "set_piece_goals_home": h_sp_goals,
        "set_piece_goals_away": a_sp_goals,
        # XI rating (top-level para compatibilidad con predict_match.py)
        "xi_home":         round(home_xi, 3),
        "xi_away":         round(away_xi, 3),
        # Elo
        "elo_home":        round(home_elo, 1),
        "elo_away":        round(away_elo, 1),
        # Tácticas
        "formation_home":  home_tac["formation"],
        "formation_away":  away_tac["formation"],
        "pressing_home":   round(home_tac["pressing_intensity"], 2),
        "pressing_away":   round(away_tac["pressing_intensity"], 2),
        "tac_matchup_home": round(h_tac_f, 3),   # ventaja/desventaja táctica del local
        "tac_matchup_away": round(a_tac_f, 3),   # ventaja/desventaja táctica del visitante
        # Top marcadores
        "top_scores":      [(f"{s[0]}-{s[1]}", round(p / prob_total_raw * 100, 1))
                            for s, p in top_scores[:6]],
        # Breakdown por factor
        "_factors": {
            "elo_diff":       round(elo_diff, 1),
            "form_home":      round(home_form["form_score"], 3),
            "form_away":      round(away_form["form_score"], 3),
            "xi_home":        round(home_xi, 3),
            "xi_away":        round(away_xi, 3),
            "xg_home":        home_club["xg"],
            "xg_away":        away_club["xg"],
            "sp_idx_home":    home_club["set_piece_idx"],
            "sp_idx_away":    away_club["set_piece_idx"],
            # Dixon-Coles (nuevo)
            "HAS": h_str["HAS"] if use_strength else None,
            "AAS": a_str["AAS"] if use_strength else None,
            "HDS": h_str["HDS"] if use_strength else None,
            "ADS": a_str["ADS"] if use_strength else None,
            "sot_h": h_str["sot_factor"] if use_strength else None,
            "sot_a": a_str["sot_factor"] if use_strength else None,
            # Interacción táctica — estilo de juego
            "tac_h": round(h_tac_f, 3),
            "tac_a": round(a_tac_f, 3),
            # Rendimiento real del XI — StatsBomb
            "def_xi_home":      h_def_xi,
            "def_xi_away":      a_def_xi,
            "cre_xi_home":      h_cre_xi,
            "cre_xi_away":      a_cre_xi,
            "xi_matchup_home":  round(h_xi_matchup, 3),
            "xi_matchup_away":  round(a_xi_matchup, 3),
        },
        # Forma reciente
        "form_home":       home_form["last5"],
        "form_away":       away_form["last5"],
        "h2h":             h2h,
    }


def _get_xi_starters(team_name: str, db_path: Path) -> list[dict]:
    """Returns projected starters with name, position and best available rating."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT p.name, p.position,
                   COALESCE(
                       (SELECT rating FROM player_ratings WHERE player_id=p.id AND context='nat'),
                       (SELECT rating FROM player_ratings WHERE player_id=p.id AND context='club')
                   ) AS rating
            FROM projected_lineups pl
            JOIN players p ON p.id = pl.player_id
            JOIN teams t ON t.id = pl.team_id
            WHERE t.name = ? AND pl.is_starter = 1
            ORDER BY CASE p.position
                WHEN 'GK' THEN 1 WHEN 'DEF' THEN 2 WHEN 'CB' THEN 2 WHEN 'LB' THEN 2
                WHEN 'RB' THEN 2 WHEN 'FB' THEN 2 WHEN 'DM' THEN 3 WHEN 'MID' THEN 3
                WHEN 'CM' THEN 3 WHEN 'AM' THEN 4 WHEN 'FWD' THEN 5 WHEN 'ST' THEN 5
                WHEN 'CF' THEN 5 WHEN 'LW' THEN 5 WHEN 'RW' THEN 5 ELSE 3 END,
                COALESCE(rating, 0) DESC
        """, (team_name,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def format_prediction(r: dict, db_path: Path | str = DB_PATH) -> str:
    """
    Reporte completo de predicción — todos los mercados proyectados.
    Cubre: resultado, marcador exacto, goles esperados, xG, posesión,
    tiros, corners, balón parado, contexto táctico, forma y H2H.
    """
    W = 68
    sep  = "═" * W
    thin = "─" * W
    f    = r["_factors"]
    h2h  = r["h2h"]
    hn   = r["home"]
    an   = r["away"]
    db_path = Path(db_path)

    # ── métricas derivadas ──────────────────────────────────────────────────
    lh, la   = r["lambda_home"], r["lambda_away"]
    # Tiros totales proyectados (xG / conversion rate ~11%)
    shots_h  = round(lh / 0.11)
    shots_a  = round(la / 0.11)
    # Tiros a puerta (≈45% de tiros totales en elite)
    sot_h    = round(shots_h * 0.45)
    sot_a    = round(shots_a * 0.45)
    # Over/under lines
    ou25     = 0.0; ou35 = 0.0; btts = 0.0
    import math
    def _pois(l, k): return (l**k * math.exp(-l)) / math.factorial(k)
    for i in range(10):
        for j in range(10):
            p = _pois(lh, i) * _pois(la, j)
            tot = i + j
            if tot > 2.5: ou25 += p
            if tot > 3.5: ou35 += p
            if i >= 1 and j >= 1: btts += p
    # Fouls proyectados (inverso de pressing — más press = más falta)
    fouls_h  = round(10 + (1 - r["pressing_home"]) * 6)
    fouls_a  = round(10 + (1 - r["pressing_away"]) * 6)
    # Tarjetas amarillas proxy
    yc_h     = round(fouls_h * 0.22)
    yc_a     = round(fouls_a * 0.22)
    # Tiro libre / penalti xG desde set pieces
    sp_xg_h  = r["set_piece_goals_home"]
    sp_xg_a  = r["set_piece_goals_away"]
    # Matchup táctico — descripción
    tac_h    = r.get("tac_matchup_home", 1.0)
    tac_a    = r.get("tac_matchup_away", 1.0)
    def tac_label(v):
        if v >= 1.10: return "VENTAJA TÁCTICA  ▲"
        if v >= 1.04: return "Leve ventaja     ▲"
        if v <= 0.90: return "DESVENTAJA TÁCT  ▼"
        if v <= 0.96: return "Leve desventaja  ▼"
        return "Neutro           –"

    lines = [
        f"\n{sep}",
        f"  {hn.upper():<28}  vs  {an.upper()}",
        f"  {r['formation_home']:<28}       {r['formation_away']}",
        thin,
        # Forma reciente
        f"  FORMA (últimos 5)   {hn[:14]:14}  {'  '.join(r['form_home'][:5])}",
        f"                      {an[:14]:14}  {'  '.join(r['form_away'][:5])}",
    ]
    if h2h["gp"]:
        lines.append(
            f"  H2H (desde 2019)    {hn[:10]} {h2h['hw']}G  /  Empate {h2h['d']}  /  {an[:10]} {h2h['aw']}G  ({h2h['gp']} partidos)"
        )
    lines += [
        thin,
        f"  {'INDICADOR':<28} {'LOCAL':>10}  {'VISITANTE':>10}",
        thin,
        f"  {'ELO FIFA':<28} {r['elo_home']:>10.0f}  {r['elo_away']:>10.0f}",
        f"  {'XI Rating (0–1)':<28} {f['xi_home']:>10.3f}  {f['xi_away']:>10.3f}",
        f"  {'xG acum. plantilla':<28} {f['xg_home']:>10.2f}  {f['xg_away']:>10.2f}",
        f"  {'Set piece index':<28} {f['sp_idx_home']:>10.2f}  {f['sp_idx_away']:>10.2f}",
        f"  {'Pressing intensity':<28} {r['pressing_home']:>10.2f}  {r['pressing_away']:>10.2f}",
        f"  {'Matchup táctico':<28} {tac_h:>10.3f}  {tac_a:>10.3f}",
        thin,
        f"  PROYECCIONES DEL PARTIDO",
        thin,
        f"  {'λ goles esperados':<28} {lh:>10.3f}  {la:>10.3f}",
        f"  {'Tiros totales':<28} {shots_h:>10}  {shots_a:>10}",
        f"  {'Tiros a puerta':<28} {sot_h:>10}  {sot_a:>10}",
        f"  {'Córners':<28} {r['corners_home']:>10}  {r['corners_away']:>10}",
        f"  {'xG balón parado':<28} {sp_xg_h:>10.2f}  {sp_xg_a:>10.2f}",
        f"  {'Faltas proyectadas':<28} {fouls_h:>10}  {fouls_a:>10}",
        f"  {'Tarjetas amarillas':<28} {yc_h:>10}  {yc_a:>10}",
    ]
    # Posesión barra visual
    bar = int(r["possession_home"] / 2)
    lines += [
        thin,
        f"  POSESIÓN  {r['possession_home']}%  {'█'*bar}{'░'*(50-bar)}  {r['possession_away']}%",
        thin,
        f"  MERCADOS",
        f"  1X2           {hn[:12]} {r['prob_home_win']:>5.1f}%  |  Empate {r['prob_draw']:>5.1f}%  |  {an[:12]} {r['prob_away_win']:>5.1f}%",
        f"  Over 2.5      {ou25*100:>5.1f}%        Over 3.5     {ou35*100:>5.1f}%",
        f"  Ambos marcan  {btts*100:>5.1f}%",
        thin,
        f"  MARCADORES MÁS PROBABLES",
    ]
    for score, prob in r["top_scores"]:
        tag = " ◄" if score == r["predicted_score"] else "  "
        lines.append(f"    {hn[:10]:10} {score:5} {an[:10]:10}   {prob:>4.1f}%{tag}")
    lines += [
        thin,
        f"  CONTEXTO TÁCTICO",
        f"  {hn[:16]:16}  {tac_label(tac_h)}  ({tac_h:.3f})",
        f"  {an[:16]:16}  {tac_label(tac_a)}  ({tac_a:.3f})",
        thin,
        f"  RESULTADO PREDICHO:  {hn} {r['predicted_score']} {an}",
        f"  GANADOR:             {r['winner']}",
        f"  CONFIANZA MODELO:    {r['confidence']:.2f} / 1.00",
        f"  Draw boost aplicado: +{r.get('draw_boost', 0):.1f}%",
    ]
    # Goleada band — cuando la diferencia Elo es extrema
    gb = r.get("goleada_band")
    if gb:
        top_gb = "  |  ".join(f"{s} ({p:.0f}%)" for s, p in gb["top_scores"])
        lines += [
            thin,
            f"  ⚠  GOLEADA PROBABLE — Elo diff > 350",
            f"  {gb['dominant']} domina: {gb['prob_pct']:.0f}% de terminar 3-0 o más",
            f"  Marcadores banda: {top_gb}",
        ]
    # Absence / injuries block
    absence = r.get("absence_summary", "")
    if absence:
        lines += [thin, "  BAJAS / TARJETAS", thin]
        for line in absence.splitlines():
            lines.append(f"  {line}")

    # Timing / fatigue block
    tf_h = r.get("timing_home_fatigue_def", 1.0)
    tf_a = r.get("timing_away_fatigue_def", 1.0)
    lc_h = r.get("timing_home_late_collapse", False)
    lc_a = r.get("timing_away_late_collapse", False)
    if tf_h != 1.0 or tf_a != 1.0 or lc_h or lc_a:
        lines += [thin, "  PATRÓN TEMPORAL (goles por franja)"]
        if tf_h > 1.05:
            lines.append(f"  ⚠ {hn[:20]} tiende a recibir goles en 2ª parte (fatiga ×{tf_h:.2f})")
        if lc_h:
            lines.append(f"  ⚠ {hn[:20]} colapsa en los últimos 15'")
        if tf_a > 1.05:
            lines.append(f"  ⚠ {an[:20]} tiende a recibir goles en 2ª parte (fatiga ×{tf_a:.2f})")
        if lc_a:
            lines.append(f"  ⚠ {an[:20]} colapsa en los últimos 15'")

    # Projected XI
    h_xi = _get_xi_starters(hn, db_path)
    a_xi = _get_xi_starters(an, db_path)
    if h_xi or a_xi:
        def fmt_player(p):
            pos  = (p["position"] or "?")[:3]
            name = p["name"][:20]
            rat  = f"{p['rating']:.1f}" if p.get("rating") else "  – "
            return f"{pos:<3} {name:<21} {rat:>4}"

        lines += [thin, f"  XI PROBABLES"]
        lines.append(f"  {'LOCAL':<32}  {'VISITANTE'}")
        lines.append(f"  {'─'*32}  {'─'*32}")
        for i in range(max(len(h_xi), len(a_xi))):
            lp = fmt_player(h_xi[i]) if i < len(h_xi) else " " * 29
            rp = fmt_player(a_xi[i]) if i < len(a_xi) else ""
            lines.append(f"  {lp}  {rp}")

    lines += [sep]
    return "\n".join(lines)


def predict_by_name(
    home: str,
    away: str,
    neutral: bool = True,
    home_absence: float = 0.0,
    away_absence: float = 0.0,
    home_events: list | None = None,
    away_events: list | None = None,
    db_path: str | Path = DB_PATH,
) -> dict:
    """
    home_events / away_events: lista de ausencias/expulsiones que afectan el partido.
    Formato: [{"player": "Messi", "reason": "injury"}]
             [{"player": "De Paul", "reason": "red_card", "minute": 67}]
             [{"player": "Busquets", "reason": "suspension"}]
    Si se pasan eventos, sobreescribe home_absence/away_absence calculándolos
    automáticamente desde posición y rating de cada jugador ausente.
    """
    """
    Wrapper de predict_match() que acepta nombres en lugar de IDs.
    - Resuelve aliases (ej: 'United States' → 'USA')
    - Si un equipo no está en la DB, lo registra automáticamente via repair_coverage
    - Nunca improvisa fórmulas manuales — siempre usa el motor completo
    """
    import json
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Cargar aliases
    aliases_path = db_path.parent / "team_name_aliases.json"
    aliases = {}
    if aliases_path.exists():
        raw = json.loads(aliases_path.read_text())
        aliases = {k: v for k, v in raw.items() if not k.startswith("_")}

    def resolve(name: str) -> int | None:
        canon = aliases.get(name, name)
        row = conn.execute("SELECT id FROM teams WHERE name=?", (canon,)).fetchone()
        return row["id"] if row else None

    home_id = resolve(home)
    away_id = resolve(away)
    conn.close()

    # Si algún equipo no tiene ID → ejecutar repair automático
    if home_id is None or away_id is None:
        missing = [t for t, i in [(home, home_id), (away, away_id)] if i is None]
        log.warning("Equipos no encontrados: %s — ejecutando repair_coverage", missing)
        import subprocess
        subprocess.run(
            ["python3", str(db_path.parent.parent / "scripts" / "repair_coverage.py"), "--repair"],
            capture_output=True
        )
        # Reintentar resolución
        conn2 = sqlite3.connect(str(db_path))
        conn2.row_factory = sqlite3.Row
        if home_id is None:
            r = conn2.execute("SELECT id FROM teams WHERE name=?", (aliases.get(home, home),)).fetchone()
            home_id = r["id"] if r else None
        if away_id is None:
            r = conn2.execute("SELECT id FROM teams WHERE name=?", (aliases.get(away, away),)).fetchone()
            away_id = r["id"] if r else None
        conn2.close()

    if home_id is None or away_id is None:
        raise ValueError(
            f"No se pudo resolver: {[t for t, i in [(home, home_id), (away, away_id)] if i is None]}"
        )

    # Calcular ausencias automáticamente desde eventos si se proporcionaron
    absence_summary = ""
    if home_events or away_events:
        try:
            from models.absence_calculator import absence_from_events
            h_abs, a_abs, absence_summary = absence_from_events(
                home_id, away_id,
                home_events=home_events,
                away_events=away_events,
                db_path=Path(db_path),
            )
            home_absence = h_abs
            away_absence = a_abs
        except Exception as e:
            log.warning("absence_calculator error: %s", e)

    result = predict_match(home_id, away_id, neutral=neutral,
                           home_absence=home_absence, away_absence=away_absence,
                           db_path=db_path)
    if absence_summary:
        result["absence_summary"] = absence_summary
    return result


if __name__ == "__main__":
    import sys
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    def tid(name):
        r = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        return r["id"] if r else None

    # Demo: Partidos del fin de semana + clásico del mundial
    matches = [
        ("Brazil",    "Panama",     True,  0.08, 0.10),  # sin Neymar, sin Carrasquilla
        ("Germany",   "Colombia",   True,  0.00, 0.00),
        ("Colombia",  "Costa Rica", True,  0.00, 0.00),
        ("Belgium",   "Croatia",    True,  0.00, 0.00),
        ("Spain",     "France",     True,  0.00, 0.00),  # clásico hipotético WC
        ("Argentina", "England",    True,  0.00, 0.00),
    ]

    for home, away, neutral, ha, aa in matches:
        h_id = tid(home); a_id = tid(away)
        if not h_id or not a_id:
            print(f"  ⚠ No encontrado: {home} o {away}")
            continue
        r = predict_match(h_id, a_id, neutral=neutral,
                          home_absence=ha, away_absence=aa)
        print(format_prediction(r))
