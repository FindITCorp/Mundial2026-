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
    "xi_rating":  0.12,
    "set_pieces": 0.10,
    "possession": 0.08,
}

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
BASE_GOALS = 1.30         # referencia goles/partido neutral


# ── Helpers ───────────────────────────────────────────────────────────────────

def _poisson(lam: float, k: int) -> float:
    return (lam ** k * math.exp(-lam)) / math.factorial(k)


def _get_elo(conn, team_id: int) -> float:
    row = conn.execute(
        "SELECT elo FROM team_elo WHERE team_id=?", (team_id,)
    ).fetchone()
    return row["elo"] if row else 1500.0


def _get_form(conn, team_id: int, n: int = 10) -> dict:
    rows = conn.execute("""
        SELECT goals_for gf, goals_against ga, result, opponent_name, competition
        FROM team_matches
        WHERE team_id=? AND goals_for IS NOT NULL
        ORDER BY date DESC LIMIT 30
    """, (team_id,)).fetchall()
    filtered = [r for r in rows if r["opponent_name"] not in MINNOWS][:n]
    if not filtered:
        filtered = list(rows[:n])
    if not filtered:
        return {"avg_gf": 1.1, "avg_ga": 1.1, "form_score": 0.40,
                "last5": [], "gp": 0, "wins": 0, "draws": 0, "losses": 0}
    gf = [r["gf"] for r in filtered]
    ga = [r["ga"] for r in filtered]
    wins  = sum(1 for r in filtered if r["result"] == "W")
    draws = sum(1 for r in filtered if r["result"] == "D")
    # Ponderación temporal (recientes pesan más)
    w_pts = sum(
        (1.5 if r["result"] == "W" else 0.5 if r["result"] == "D" else 0)
        * (1 + i * 0.07)
        for i, r in enumerate(reversed(filtered))
    )
    max_pts = sum(1.5 * (1 + i * 0.07) for i in range(len(filtered)))
    return {
        "avg_gf":     sum(gf) / len(gf),
        "avg_ga":     sum(ga) / len(ga),
        "form_score": w_pts / max_pts if max_pts else 0.40,
        "last5":      [f'{r["result"]}({r["gf"]}-{r["ga"]})' for r in filtered[:5]],
        "gp": len(filtered), "wins": wins, "draws": draws,
        "losses": len(filtered) - wins - draws,
    }


def _get_xi_rating(conn, team_id: int) -> float:
    """Rating promedio del XI titular (0–1)."""
    rows = conn.execute("""
        SELECT pr.rating
        FROM projected_lineups pl
        LEFT JOIN player_ratings pr ON pr.player_id = pl.player_id AND pr.context = 'nat'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()
    ratings = [r["rating"] for r in rows if r["rating"]]
    if not ratings:
        caps = conn.execute("""
            SELECT AVG(p.caps) FROM projected_lineups pl
            JOIN players p ON p.id = pl.player_id
            WHERE pl.team_id = ? AND pl.is_starter = 1
        """, (team_id,)).fetchone()[0] or 30
        return min(0.65, caps / 120 * 0.65)
    return sum(ratings) / len(ratings) / 10.0


def _get_club_metrics(conn, team_id: int) -> dict:
    """Métricas del XI desde player_club_stats 2024/25."""
    rows = conn.execute("""
        SELECT pcs.pass_accuracy, pcs.shots_on_target, pcs.xg, pcs.xa,
               pcs.tackles, pcs.interceptions, pcs.dribbles_completed
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_club_stats pcs ON pcs.player_id = pl.player_id
            AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    m = {k: [] for k in ["pa", "sot", "xg", "xa", "tkl", "inter", "drib"]}
    for r in rows:
        if r["pass_accuracy"]:  m["pa"].append(r["pass_accuracy"])
        if r["shots_on_target"]: m["sot"].append(r["shots_on_target"])
        if r["xg"] is not None: m["xg"].append(r["xg"])
        if r["xa"] is not None: m["xa"].append(r["xa"])
        if r["tackles"]:        m["tkl"].append(r["tackles"])
        if r["interceptions"]:  m["inter"].append(r["interceptions"])
        if r["dribbles_completed"]: m["drib"].append(r["dribbles_completed"])

    avg = lambda lst, d: sum(lst) / len(lst) if lst else d
    pa   = avg(m["pa"], 75.0)
    xg   = sum(m["xg"]) if m["xg"] else 0.0
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


def _get_h2h(conn, tid1: int, tid2: int, n: int = 8) -> dict:
    rows = conn.execute("""
        SELECT goals_for gf, goals_against ga, result
        FROM team_matches
        WHERE team_id=? AND opponent_id=? ORDER BY date DESC LIMIT ?
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
) -> dict:
    """
    Retorna un dict completo con predicción, probabilidades, métricas y breakdown.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # ── 1. Recopilar datos ────────────────────────────────────────────────
    home_elo  = _get_elo(conn, home_id)
    away_elo  = _get_elo(conn, away_id)
    home_form = _get_form(conn, home_id)
    away_form = _get_form(conn, away_id)
    home_xi   = _get_xi_rating(conn, home_id)
    away_xi   = _get_xi_rating(conn, away_id)
    home_club = _get_club_metrics(conn, home_id)
    away_club = _get_club_metrics(conn, away_id)
    home_tac  = _get_tactics(conn, home_id)
    away_tac  = _get_tactics(conn, away_id)
    h2h       = _get_h2h(conn, home_id, away_id)

    home_name = conn.execute("SELECT name FROM teams WHERE id=?", (home_id,)).fetchone()["name"]
    away_name = conn.execute("SELECT name FROM teams WHERE id=?", (away_id,)).fetchone()["name"]
    conn.close()

    # ── 2. Factor Elo (30%) ───────────────────────────────────────────────
    elo_diff  = home_elo - away_elo
    elo_adj   = 0 if neutral else 50
    e_home    = 1.0 / (1.0 + 10 ** (-(elo_diff + elo_adj) / 400))
    elo_lambda_h = BASE_GOALS * (0.7 + e_home * 0.6)     # 0.7–1.3 escala
    elo_lambda_a = BASE_GOALS * (0.7 + (1 - e_home) * 0.6)

    # ── 3. Factor xG / forma (25% + 15%) ─────────────────────────────────
    # Cap att/def ratios to prevent extreme inflation
    h_att = min(1.85, home_form["avg_gf"] / BASE_GOALS)
    a_att = min(1.85, away_form["avg_gf"] / BASE_GOALS)
    # Raíz cuadrada para suavizar el efecto de defensas muy sólidas
    h_def = (1.0 / max(0.60, home_form["avg_ga"] / BASE_GOALS)) ** 0.55
    a_def = (1.0 / max(0.60, away_form["avg_ga"] / BASE_GOALS)) ** 0.55

    xg_ref   = 1.4 * 11
    h_xg_f   = max(0.88, min(1.15, home_club["xg"] / xg_ref)) if home_club["xg"] > 0 else 1.0
    a_xg_f   = max(0.88, min(1.15, away_club["xg"] / xg_ref)) if away_club["xg"] > 0 else 1.0

    h_form_f = 0.80 + 0.40 * home_form["form_score"]
    a_form_f = 0.80 + 0.40 * away_form["form_score"]

    # ── 4. Rating XI (12%) ────────────────────────────────────────────────
    xi_diff   = away_xi - home_xi
    h_xi_f    = max(0.65, 1.0 - xi_diff * 0.35)
    a_xi_f    = max(0.65, 1.0 + xi_diff * 0.35)

    # ── 5. Set pieces (10%) ───────────────────────────────────────────────
    avg_sp    = (home_club["set_piece_idx"] + away_club["set_piece_idx"]) / 2 or 3.5
    h_sp_f    = 1.0 + (home_club["set_piece_idx"] - avg_sp) / avg_sp * 0.10
    a_sp_f    = 1.0 + (away_club["set_piece_idx"] - avg_sp) / avg_sp * 0.10

    # ── 6. Posesión / pressing matchup (8%) ───────────────────────────────
    press_diff = home_tac["pressing_intensity"] - away_tac["pressing_intensity"]
    h_press_f  = 1.0 + press_diff * 0.08
    a_press_f  = 1.0 - press_diff * 0.08

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
    # Lambda combinado como promedio ponderado de los factores
    w = WEIGHTS
    lh_raw = (
        BASE_GOALS
        * h_att * a_def                              # ataque vs defensa rival
        * (elo_lambda_h / BASE_GOALS) ** (w["elo"] * 2)
        * h_xg_f   ** (w["xg"] * 2)
        * h_form_f ** (w["form"] * 2)
        * h_xi_f   ** (w["xi_rating"] * 2)
        * h_sp_f   ** (w["set_pieces"] * 2)
        * h_press_f ** (w["possession"] * 2)
        * h2h_hf
        * venue_h
        * (1 - home_absence)
    )
    la_raw = (
        BASE_GOALS
        * a_att * h_def
        * (elo_lambda_a / BASE_GOALS) ** (w["elo"] * 2)
        * a_xg_f   ** (w["xg"] * 2)
        * a_form_f ** (w["form"] * 2)
        * a_xi_f   ** (w["xi_rating"] * 2)
        * a_sp_f   ** (w["set_pieces"] * 2)
        * a_press_f ** (w["possession"] * 2)
        * h2h_af
        * venue_a
        * (1 - away_absence)
    )

    # Cap realista (máximo ~3 goles esperados en partido entre selecciones)
    lh = min(max(lh_raw, 0.30), 3.20)
    la = min(max(la_raw, 0.30), 3.20)

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
    top_scores = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:8]

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
    # Mayor confianza si: Elo muy diferente, forma clara, H2H claro
    elo_conf   = min(1.0, abs(elo_diff) / 300)
    form_conf  = abs(home_form["form_score"] - away_form["form_score"])
    h2h_conf   = (max(h2h["hw"], h2h["aw"]) / h2h["gp"]) if h2h["gp"] >= 4 else 0.0
    confidence = round((elo_conf * 0.4 + form_conf * 0.35 + h2h_conf * 0.25), 3)

    # Predicción final
    pred = top_scores[0][0]
    winner = home_name if pred[0] > pred[1] else (away_name if pred[1] > pred[0] else "DRAW")

    return {
        # Identidad
        "home": home_name,
        "away": away_name,
        # Predicción principal
        "predicted_score": f"{pred[0]}-{pred[1]}",
        "winner":           winner,
        "confidence":       confidence,
        # Probabilidades
        "prob_home_win":   round(ph / total * 100, 1),
        "prob_draw":       round(pd / total * 100, 1),
        "prob_away_win":   round(pa / total * 100, 1),
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
        # Top marcadores
        "top_scores":      [(f"{s[0]}-{s[1]}", round(p / total * 100, 1))
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
        },
        # Forma reciente
        "form_home":       home_form["last5"],
        "form_away":       away_form["last5"],
        "h2h":             h2h,
    }


def format_prediction(r: dict) -> str:
    """Pretty-print de una predicción."""
    sep = "═" * 64
    lines = [
        f"\n{sep}",
        f"  {r['home'].upper()} vs {r['away'].upper()}",
        f"  Formaciones: {r['formation_home']} vs {r['formation_away']}",
        f"{'─'*64}",
        f"  📊 Forma  {r['home'][:12]:12}  {'  '.join(r['form_home'][:5])}",
        f"            {r['away'][:12]:12}  {'  '.join(r['form_away'][:5])}",
    ]
    h2h = r["h2h"]
    if h2h["gp"]:
        lines.append(f"  🔁 H2H {r['home'][:10]} {h2h['hw']}V / Draw {h2h['d']} / {r['away'][:10]} {h2h['aw']}V")
    lines += [
        f"{'─'*64}",
        f"  ⚡ ELO          {r['home'][:14]:14} {r['elo_home']:>7.0f}    {r['away'][:14]:14} {r['elo_away']:>7.0f}",
        f"  ⚽ MÉTRICAS            {r['home'][:12]:>14}    {r['away'][:12]:>14}",
        f"  XI Rating              {'%.3f'%r['_factors']['xi_home']:>14}    {'%.3f'%r['_factors']['xi_away']:>14}",
        f"  xG acum. XI            {'%.2f'%r['_factors']['xg_home']:>14}    {'%.2f'%r['_factors']['xg_away']:>14}",
        f"  Set Piece idx          {'%.2f'%r['_factors']['sp_idx_home']:>14}    {'%.2f'%r['_factors']['sp_idx_away']:>14}",
        f"  Pressing               {'%.2f'%r['pressing_home']:>14}    {'%.2f'%r['pressing_away']:>14}",
        f"  λ goles esperados      {'%.3f'%r['lambda_home']:>14}    {'%.3f'%r['lambda_away']:>14}",
        f"{'─'*64}",
        f"  🏃 DOMINIO",
    ]
    bar = int(r["possession_home"] / 2)
    lines.append(f"  Posesión  {'█'*bar}{'░'*(50-bar)}  {r['possession_home']}% vs {r['possession_away']}%")
    lines += [
        f"  Córners    {r['home'][:10]}: {r['corners_home']}    {r['away'][:10]}: {r['corners_away']}",
        f"  Goles BP   {r['home'][:10]}: {r['set_piece_goals_home']}    {r['away'][:10]}: {r['set_piece_goals_away']}",
        f"{'─'*64}",
        f"  📈 1X2: {r['home'][:10]} {r['prob_home_win']}%  |  Empate {r['prob_draw']}%  |  {r['away'][:10]} {r['prob_away_win']}%",
        f"  🎯 TOP MARCADORES:",
    ]
    for score, prob in r["top_scores"]:
        tag = " ◄ PREDICCIÓN" if score == r["predicted_score"] else ""
        lines.append(f"     {r['home'][:8]} {score} {r['away'][:8]}   {prob}%{tag}")
    lines += [
        f"{'═'*64}",
        f"  ✅ {r['home']} {r['predicted_score']} {r['away']}",
        f"  🏆 {r['winner']}   (confianza modelo: {r['confidence']:.2f})",
        f"{sep}",
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
