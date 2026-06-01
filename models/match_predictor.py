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
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
log = logging.getLogger("predictor")

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

MINNOWS = {
    # Europa
    "Liechtenstein", "Gibraltar", "Faroe Islands", "San Marino", "Andorra",
    "Malta", "Luxembourg", "Latvia", "Estonia", "Kosovo", "Moldova",
    # CONCACAF/Caribbean
    "Montserrat", "Curacao", "Haiti", "Belize", "Barbados", "Bahamas",
    "Cayman Islands", "Puerto Rico", "Antigua and Barbuda", "Grenada",
    "Saint Kitts and Nevis", "Turks and Caicos", "Aruba", "Bermuda",
    # Africa (FIFA rank <120 approx)
    "Zambia", "Mauritania", "Angola", "Djibouti", "Eritrea", "Seychelles",
    "Somalia", "Comoros", "Eswatini", "Lesotho", "South Sudan",
    # Asia
    "Bhutan", "Timor-Leste", "Macau", "Mongolia", "Guam",
}

HOME_ADV_LAMBDA = 0.08   # +8% goles para el local
BASE_GOALS = 1.22         # referencia goles/partido neutral — calibrado 2026-06-02 (Over2.5 real=53% vs pred=60%)


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
SOS_EXP         = 2.0      # sensibilidad del peso a la fuerza del rival
# Regularización bayesiana: prior que regresa los promedios hacia la media
PRIOR_N         = 4.0
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
               tm.opponent_name, tm.competition, te.elo AS opp_elo
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

    # ── Strength-of-schedule: ponderar goles por fuerza del rival ────────────
    # Marcar/conceder frente a rivales fuertes pesa más que frente a débiles.
    num_gf = num_ga = denom = 0.0
    for r in filtered:
        opp_elo = r["opp_elo"] if r["opp_elo"] is not None else SOS_DEFAULT_ELO
        w = (opp_elo / SOS_PIVOT) ** SOS_EXP
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
        opp_factor = (opp_elo / SOS_PIVOT) ** 0.75   # más sensible a calidad rival
        if r["result"] == "W":
            pts = 1.5 * opp_factor          # ganar vs fuerte vale más
        elif r["result"] == "D":
            pts = 0.5 * opp_factor          # empate vs fuerte también vale más
        else:
            # Perder vs rival mucho más fuerte: crédito proporcional a la brecha
            pts = max(0.0, 0.40 * (opp_elo - SOS_PIVOT) / 300)
        w_pts   += pts * recency
        max_pts += 1.5 * recency            # máximo sigue siendo ganar todo
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
        SELECT p.caps,
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

    scores = []
    for r in rows:
        # Use WC2022 match count for WC-derived metrics, club count for xG
        wc_m    = max(1, r["sb_matches"] or 0)
        club_m  = max(1, r["matches"] or 1)
        has_wc  = (r["sb_matches"] or 0) > 0
        has_xg  = r["xg"] is not None and r["xg"] > 0

        rating_n = min(1.0, r["rating"] / RATING_MAX) if r["rating"] else None
        xg_n     = min(1.0, (r["xg"] or 0.0) / club_m / XG_PER_GAME_MAX)
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
    if not any_tournament:
        xi = min(xi, 0.360)

    return xi


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
    # Nuevas métricas Dixon-Coles (repo Football_matches)
    if use_strength:
        h_str = _get_attack_defense_strength(conn, home_id, db_key)
        a_str = _get_attack_defense_strength(conn, away_id, db_key)

    home_name = conn.execute("SELECT name FROM teams WHERE id=?", (home_id,)).fetchone()["name"]
    away_name = conn.execute("SELECT name FROM teams WHERE id=?", (away_id,)).fetchone()["name"]
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
        * h_tac_f                                    # interacción táctica completa
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
        * a_tac_f                                    # interacción táctica completa
        * h2h_af
        * venue_a
        * (1 - away_absence)
    )

    lh = min(max(lh_raw, 0.20), 3.50)
    la = min(max(la_raw, 0.20), 3.50)

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

    # ── 10b. Rebalanceo de empates/sorpresas — W-5 Framework ─────────────
    # Poisson tiende a subestimar empates en partidos muy parejos.
    # Calibrado 31-mayo-2026: reducido ~40% tras 0/6 empates reales vs muchos predichos.
    draw_boost = 0.0

    # Señal 1: Elo muy parejo
    elo_gap = abs(elo_diff)
    if elo_gap < 30:
        draw_boost += 0.025
    elif elo_gap < 60:
        draw_boost += 0.014
    elif elo_gap < 100:
        draw_boost += 0.006

    # Señal 2: Forma reciente casi idéntica
    form_gap = abs(home_form["form_score"] - away_form["form_score"])
    if form_gap < 0.05:
        draw_boost += 0.014
    elif form_gap < 0.10:
        draw_boost += 0.006

    # Señal 3: H2H con historial de empates
    if h2h["gp"] >= 4:
        draw_rate = h2h["d"] / h2h["gp"]
        if draw_rate >= 0.40:
            draw_boost += 0.014
        elif draw_rate >= 0.30:
            draw_boost += 0.007

    # Señal 4: Lambdas muy similares (partido equilibrado proyectado)
    lambda_ratio = min(lh, la) / max(lh, la) if max(lh, la) > 0 else 1.0
    if lambda_ratio > 0.92:
        draw_boost += 0.012
    elif lambda_ratio > 0.85:
        draw_boost += 0.005

    # Señal 5: Neutral + Elo muy parejo
    if neutral and elo_gap < 60:
        draw_boost += 0.005

    # Cap: máximo boost de +5pp
    draw_boost = min(draw_boost, 0.050)

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

    # Predicción final — ganador según max probabilidad rebalanceada
    if ph >= pd and ph >= pa:
        winner = home_name
    elif pa >= ph and pa >= pd:
        winner = away_name
    else:
        winner = "DRAW"
    pred = top_scores[0][0]

    return {
        # Identidad
        "home": home_name,
        "away": away_name,
        # Predicción principal
        "predicted_score": f"{pred[0]}-{pred[1]}",
        "winner":           winner,
        "confidence":       confidence,
        # Probabilidades (rebalanceadas por W-5 draw boost)
        "prob_home_win":   round(ph * 100, 1),
        "prob_draw":       round(pd * 100, 1),
        "prob_away_win":   round(pa * 100, 1),
        "draw_boost":      round(draw_boost * 100, 1),   # cuánto se boosteó el empate
        # Goles esperados
        "lambda_home":     round(lh, 3),
        "lambda_away":     round(la, 3),
        # Métricas de dominio
        "possession_home": h_poss,
        "possession_away": a_poss,
        "corners_home":    h_corners,
        "corners_away":    a_corners,
        "set_piece_goals_home": h_sp_goals,
        "set_piece_goals_away": a_sp_goals,
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
            # Interacción táctica — cuánto afecta el estilo de juego al lambda
            "tac_h": round(h_tac_f, 3),
            "tac_a": round(a_tac_f, 3),
        },
        # Forma reciente
        "form_home":       home_form["last5"],
        "form_away":       away_form["last5"],
        "h2h":             h2h,
    }


def format_prediction(r: dict) -> str:
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
        sep,
    ]
    return "\n".join(lines)


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
