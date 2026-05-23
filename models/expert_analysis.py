"""
Expert-style match analysis — produces a concrete result ("Croatia 2-1 Panama"),
not probability tables. Reads from the local SQLite DB.

Usage:
    python models/expert_analysis.py "Panama" "Croatia"
    from models.expert_analysis import analyze_match
    print(analyze_match("Panama", "Croatia"))
"""

import math
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_DEFAULT = str(BASE_DIR / "data" / "mundial2026.db")

# ── League tiers ──────────────────────────────────────────────────────────────
TIER1 = {
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "English Premier League", "Spanish La Liga", "German Bundesliga",
    "Italian Serie A", "French Ligue 1",
}
TIER2 = {
    "Eredivisie", "Liga Portuguesa", "Primeira Liga", "MLS", "Liga MX",
    "Saudi Pro League", "Pro League Saudi", "Süper Lig", "Liga Portugal",
    "Scottish Premiership", "Belgian Pro League", "Russian Premier League",
    "Brazilian Serie A", "Argentine Primera Division", "Copa Liga Profesional",
    "Liga Argentina", "Campeonato Brasileiro",
}
TIER4_KEYWORDS = {
    "Primera Division", "primera division", "Liga Nacional", "liga nacional",
    "HNL", "K League", "Eliteserien",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _league_bonus(league: str | None) -> float:
    if not league:
        return 0.0
    if league in TIER1:
        return 0.6
    if league in TIER2:
        return 0.3
    for kw in TIER4_KEYWORDS:
        if kw in (league or ""):
            return -0.3
    return 0.0


def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _most_likely_score(xg_a: float, xg_b: float, max_goals: int = 6) -> tuple[int, int]:
    best_prob = -1.0
    best = (1, 1)
    for g_a in range(max_goals + 1):
        for g_b in range(max_goals + 1):
            p = _poisson_pmf(xg_a, g_a) * _poisson_pmf(xg_b, g_b)
            if p > best_prob:
                best_prob = p
                best = (g_a, g_b)
    return best


def _winner_from_score(score_a: int, score_b: int, name_a: str, name_b: str) -> str:
    if score_a > score_b:
        return name_a
    if score_b > score_a:
        return name_b
    return "Empate"


# ── DB queries ────────────────────────────────────────────────────────────────

def _load_team(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute(
        """SELECT id, name, fifa_ranking, fifa_rank, goals_scored_avg, goals_conceded_avg,
                  win_prob_opta, win_prob_book, odds_american, wc_group
           FROM teams WHERE LOWER(name)=LOWER(?)""",
        (name,),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def _recent_form(conn: sqlite3.Connection, team_id: int, last_n: int = 10) -> list[dict]:
    rows = conn.execute(
        """SELECT date, opponent_name, goals_for, goals_against, result
           FROM team_matches WHERE team_id=? ORDER BY date DESC LIMIT ?""",
        (team_id, last_n),
    ).fetchall()
    return [dict(r) for r in rows]


def _form_score(matches: list[dict]) -> float:
    """Returns 0-1 form score from recent matches (W=1, D=0.5, L=0)."""
    if not matches:
        return 0.5
    points = sum(1.0 if m["result"] == "W" else 0.5 if m["result"] == "D" else 0.0 for m in matches)
    return points / len(matches)


def _form_string(matches: list[dict]) -> str:
    """Returns last 5 results as W/D/L string and streak description."""
    last5 = matches[:5]
    symbols = " ".join(m["result"] for m in last5)

    # streak
    streak_val = last5[0]["result"] if last5 else None
    streak_count = 0
    for m in last5:
        if m["result"] == streak_val:
            streak_count += 1
        else:
            break

    streak_map = {"W": "victorias", "D": "empates", "L": "derrotas"}
    if streak_count >= 2:
        streak_desc = f"{streak_count} {streak_map.get(streak_val, '')} consecutivas"
    else:
        streak_desc = ""

    return symbols, streak_desc


def _avg_goals(matches: list[dict]) -> tuple[float, float]:
    if not matches:
        return 1.2, 1.2
    gf = sum(m["goals_for"] for m in matches) / len(matches)
    ga = sum(m["goals_against"] for m in matches) / len(matches)
    return gf, ga


def _defenders(conn: sqlite3.Connection, team_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT p.name, p.club, p.club_league, p.market_value_m, MAX(pr.rating) as rating
           FROM players p
           LEFT JOIN player_ratings pr ON pr.player_id=p.id AND pr.context='nat'
           WHERE p.team_id=? AND p.position IN ('CB','LB','RB','LWB','RWB','DEF')
           GROUP BY p.id
           ORDER BY rating DESC NULLS LAST LIMIT 5""",
        (team_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _attackers(conn: sqlite3.Connection, team_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT p.name, p.club, p.club_league, p.goals_as_nat, p.caps, p.market_value_m,
                  MAX(pr.rating) as rating
           FROM players p
           LEFT JOIN player_ratings pr ON pr.player_id=p.id AND pr.context='nat'
           WHERE p.team_id=? AND p.position IN ('ST','CF','LW','RW','FWD','CAM','SS')
           GROUP BY p.id
           ORDER BY p.goals_as_nat DESC NULLS LAST LIMIT 5""",
        (team_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _h2h(conn: sqlite3.Connection, team_id_a: int, team_id_b: int) -> list[dict]:
    name_a = conn.execute("SELECT name FROM teams WHERE id=?", (team_id_a,)).fetchone()["name"]
    name_b = conn.execute("SELECT name FROM teams WHERE id=?", (team_id_b,)).fetchone()["name"]
    # Only team_a perspective to avoid mirror duplicates
    rows = conn.execute(
        """SELECT tm.date, tm.goals_for, tm.goals_against, tm.result, tm.opponent_name,
                  t.name AS team_name
           FROM team_matches tm JOIN teams t ON tm.team_id=t.id
           WHERE tm.team_id=? AND (tm.opponent_id=? OR tm.opponent_name=?)
           GROUP BY tm.date
           ORDER BY tm.date DESC LIMIT 8""",
        (team_id_a, team_id_b, name_b),
    ).fetchall()
    if not rows:
        # Try from team_b perspective if no data from team_a
        rows = conn.execute(
            """SELECT tm.date, tm.goals_against AS goals_for, tm.goals_for AS goals_against,
                      CASE tm.result WHEN 'W' THEN 'L' WHEN 'L' THEN 'W' ELSE 'D' END AS result,
                      t.name AS opponent_name, ? AS team_name
               FROM team_matches tm JOIN teams t ON tm.team_id=t.id
               WHERE tm.team_id=? AND (tm.opponent_id=? OR tm.opponent_name=?)
               GROUP BY tm.date
               ORDER BY tm.date DESC LIMIT 8""",
            (name_a, team_id_b, team_id_a, name_a),
        ).fetchall()
    return [dict(r) for r in rows]


def _def_quality_score(defenders: list[dict]) -> float:
    """Returns 0-10 defensive quality score for the team."""
    if not defenders:
        return 5.0
    scores = []
    for d in defenders:
        base = float(d["rating"] or 5.5)
        bonus = _league_bonus(d["club_league"])
        val_bonus = 0.5 if (d["market_value_m"] or 0) > 50 else 0.0
        scores.append(min(10.0, base + bonus + val_bonus))
    return sum(scores) / len(scores)


def _att_quality_score(attackers: list[dict]) -> float:
    """Returns 0-10 attacking quality score."""
    if not attackers:
        return 5.0
    scores = []
    for a in attackers:
        base = float(a["rating"] or 5.5)
        # goals/caps bonus (up to +1.2)
        goals = a["goals_as_nat"] or 0
        caps = a["caps"] or 1
        ratio = goals / max(caps, 1)
        goals_bonus = min(1.2, ratio * 4.0)
        league_bonus = _league_bonus(a["club_league"])
        val_bonus = 0.5 if (a["market_value_m"] or 0) > 50 else 0.0
        scores.append(min(10.0, base + goals_bonus + league_bonus + val_bonus))
    return sum(scores) / len(scores)


def _h2h_factor(h2h: list[dict], team_id_a: int) -> float:
    """Returns +0.12 if team_a dominated H2H, -0.12 if dominated by team_b, 0 otherwise."""
    if not h2h:
        return 0.0
    wins_a = sum(1 for m in h2h if m["team_name"] != "" and
                 ((conn_team_id_match(m, team_id_a) and m["result"] == "W")))
    # Simpler: count results from perspective of team_a appearances
    wins_a = 0
    wins_b = 0
    draws = 0
    # Normalize: find which rows are from team_a perspective
    for m in h2h:
        # We can't reliably know team_id from dict here without extra query
        # Use: if result W and team_name is team_a's name → team_a won
        # We'll handle via caller passing team names
        pass
    return 0.0


def _h2h_factor_by_name(h2h: list[dict], name_a: str, name_b: str) -> tuple[float, str]:
    """Returns (factor, summary_string)."""
    wins_a = wins_b = draws = 0
    for m in h2h:
        if m["team_name"] == name_a:
            if m["result"] == "W":
                wins_a += 1
            elif m["result"] == "D":
                draws += 1
            else:
                wins_b += 1
        elif m["team_name"] == name_b:
            if m["result"] == "W":
                wins_b += 1
            elif m["result"] == "D":
                draws += 1
            else:
                wins_a += 1

    total = wins_a + wins_b + draws
    if total == 0:
        return 0.0, "Sin antecedentes directos"

    summary = f"{name_a} {wins_a}G – {draws}E – {wins_b}G {name_b} (últimos {total} partidos)"

    if wins_a > wins_b * 1.5 and wins_a >= 2:
        return 0.12, summary
    if wins_b > wins_a * 1.5 and wins_b >= 2:
        return -0.12, summary
    return 0.0, summary


def conn_team_id_match(m: dict, team_id: int) -> bool:
    return False  # placeholder, not used


# ── Odds formatting ───────────────────────────────────────────────────────────

def _format_odds(odds_american: int | None) -> str:
    if not odds_american:
        return "N/A"
    if odds_american > 0:
        return f"+{odds_american}"
    return str(odds_american)


def _odds_to_implied(odds_american: int | None) -> float:
    """Returns implied probability from American odds."""
    if not odds_american:
        return 0.0
    if odds_american > 0:
        return 100.0 / (odds_american + 100.0)
    return abs(odds_american) / (abs(odds_american) + 100.0)


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze_match(team_a_name: str, team_b_name: str, db_path: str | None = None) -> str:
    db_path = db_path or DB_DEFAULT
    conn = _conn(db_path)

    team_a = _load_team(conn, team_a_name)
    team_b = _load_team(conn, team_b_name)

    if not team_a:
        return f"⚠ Equipo no encontrado: {team_a_name}"
    if not team_b:
        return f"⚠ Equipo no encontrado: {team_b_name}"

    id_a, id_b = team_a["id"], team_b["id"]
    name_a, name_b = team_a["name"], team_b["name"]

    # --- Form data ---
    matches_a = _recent_form(conn, id_a, last_n=20)
    matches_b = _recent_form(conn, id_b, last_n=20)

    form_score_a = _form_score(matches_a[:10])
    form_score_b = _form_score(matches_b[:10])

    symbols_a, streak_a = _form_string(matches_a)
    symbols_b, streak_b = _form_string(matches_b)

    # avg goals from last 20 matches
    base_gf_a, base_ga_a = _avg_goals(matches_a)
    base_gf_b, base_ga_b = _avg_goals(matches_b)

    # Fall back to teams table if no match history
    if not matches_a:
        base_gf_a = team_a.get("goals_scored_avg") or 1.2
        base_ga_a = team_a.get("goals_conceded_avg") or 1.2
    if not matches_b:
        base_gf_b = team_b.get("goals_scored_avg") or 1.2
        base_ga_b = team_b.get("goals_conceded_avg") or 1.2

    # --- Player quality ---
    defs_a = _defenders(conn, id_a)
    defs_b = _defenders(conn, id_b)
    atts_a = _attackers(conn, id_a)
    atts_b = _attackers(conn, id_b)

    def_score_a = _def_quality_score(defs_a)
    def_score_b = _def_quality_score(defs_b)
    att_score_a = _att_quality_score(atts_a)
    att_score_b = _att_quality_score(atts_b)

    # --- H2H ---
    h2h = _h2h(conn, id_a, id_b)
    h2h_factor_a, h2h_summary = _h2h_factor_by_name(h2h, name_a, name_b)
    h2h_factor_b = -h2h_factor_a

    # --- xG calculation ---
    # xg_a: team_a's expected goals
    def_mod_b = 1.0 - (def_score_b - 5.0) * 0.04   # strong defense_b → lower xg_a
    att_mod_a = 1.0 + (att_score_a - 5.0) * 0.035  # strong attack_a → higher xg_a
    form_mod_a = 1.0 + (form_score_a - 0.5) * 0.25
    h2h_mult_a = 1.0 + h2h_factor_a
    xg_a = base_gf_a * def_mod_b * att_mod_a * form_mod_a * h2h_mult_a

    def_mod_a = 1.0 - (def_score_a - 5.0) * 0.04
    att_mod_b = 1.0 + (att_score_b - 5.0) * 0.035
    form_mod_b = 1.0 + (form_score_b - 0.5) * 0.25
    h2h_mult_b = 1.0 + h2h_factor_b
    xg_b = base_gf_b * def_mod_a * att_mod_b * form_mod_b * h2h_mult_b

    # clamp to sane range
    xg_a = max(0.3, min(4.0, xg_a))
    xg_b = max(0.3, min(4.0, xg_b))

    score_a, score_b = _most_likely_score(xg_a, xg_b)
    winner = _winner_from_score(score_a, score_b, name_a, name_b)

    # --- Favorite determination ---
    prob_a_book = (team_a.get("win_prob_book") or 0.0) / 100.0
    prob_b_book = (team_b.get("win_prob_book") or 0.0) / 100.0

    if prob_a_book > prob_b_book * 1.15:
        fav = name_a
        fav_odds = _format_odds(team_a.get("odds_american"))
        fav_opta = team_a.get("win_prob_opta") or 0.0
    elif prob_b_book > prob_a_book * 1.15:
        fav = name_b
        fav_odds = _format_odds(team_b.get("odds_american"))
        fav_opta = team_b.get("win_prob_opta") or 0.0
    else:
        fav = "Paridad"
        fav_odds = ""
        fav_opta = 0.0

    # --- Build top scorers text ---
    def _scorer_line(a: dict) -> str:
        g = a["goals_as_nat"] or 0
        c = a["caps"] or 1
        league = a["club_league"] or "—"
        return f"{a['name']} ({a['club'] or '—'} · {league}) — {g}G en {c} caps"

    def _def_line(d: dict) -> str:
        score = (d["rating"] or 5.5) + _league_bonus(d["club_league"])
        score_str = f"{min(10.0, score):.1f}/10"
        return f"{d['name']} ({d['club'] or '—'} · {d['club_league'] or '—'}) → calidad def. {score_str}"

    # --- Format report ---
    width = 72
    sep = "─" * width

    def box(title: str) -> str:
        return f"┌{sep}┐\n│  {title:<{width-3}}│\n└{sep}┘"

    def section(title: str) -> str:
        return f"\n{'▌ ' + title}"

    lines = []
    lines.append(f"╔{'═'*width}╗")
    lines.append(f"║{'ANÁLISIS EXPERTO — MUNDIAL 2026':^{width}}║")
    lines.append(f"║{f'{name_a}  vs  {name_b}':^{width}}║")
    lines.append(f"╚{'═'*width}╝")

    # Result
    lines.append("")
    lines.append(f"  🏆  RESULTADO PROYECTADO:  {name_a} {score_a}-{score_b} {name_b}")
    if winner != "Empate":
        lines.append(f"       Ganador esperado: {winner}")
    else:
        lines.append(f"       Resultado: Empate")
    lines.append("")

    # Favorite
    lines.append(f"  📊  FAVORITO DE MERCADO: {fav}", )
    if fav_odds:
        lines.append(f"       Odds apuestas: {fav_odds} | Opta probabilidad campeonato: {fav_opta:.1f}%")
    lines.append("")
    lines.append(f"  {'─'*68}")

    # Team A section
    lines.append(section(f"ANÁLISIS — {name_a.upper()}"))
    lines.append(f"   FIFA Ranking: #{team_a.get('fifa_ranking') or team_a.get('fifa_rank') or '?'}")
    lines.append(f"   Promedio goles anotados: {base_gf_a:.2f}/partido  |  Concedidos: {base_ga_a:.2f}/partido")
    lines.append(f"   Forma reciente (últimos 5): {symbols_a}  {streak_a}")

    lines.append(f"")
    lines.append(f"   DEFENSA (calidad individual — score {def_score_a:.1f}/10):")
    for d in defs_a[:3]:
        lines.append(f"     • {_def_line(d)}")
    if not defs_a:
        lines.append(f"     • Sin datos individuales")

    lines.append(f"")
    lines.append(f"   ATAQUE (score {att_score_a:.1f}/10 — referentes goleadores):")
    for a in atts_a[:3]:
        lines.append(f"     • {_scorer_line(a)}")
    if not atts_a:
        lines.append(f"     • Sin datos de goleadores")

    lines.append(f"")
    lines.append(f"   xG interno calculado: {xg_a:.2f}")
    lines.append(f"   (base {base_gf_a:.2f} × def rival {def_mod_b:.2f} × ataque {att_mod_a:.2f} × forma {form_mod_a:.2f})")

    lines.append(f"")
    lines.append(f"  {'─'*68}")

    # Team B section
    lines.append(section(f"ANÁLISIS — {name_b.upper()}"))
    lines.append(f"   FIFA Ranking: #{team_b.get('fifa_ranking') or team_b.get('fifa_rank') or '?'}")
    lines.append(f"   Promedio goles anotados: {base_gf_b:.2f}/partido  |  Concedidos: {base_ga_b:.2f}/partido")
    lines.append(f"   Forma reciente (últimos 5): {symbols_b}  {streak_b}")

    lines.append(f"")
    lines.append(f"   DEFENSA (calidad individual — score {def_score_b:.1f}/10):")
    for d in defs_b[:3]:
        lines.append(f"     • {_def_line(d)}")
    if not defs_b:
        lines.append(f"     • Sin datos individuales")

    lines.append(f"")
    lines.append(f"   ATAQUE (score {att_score_b:.1f}/10 — referentes goleadores):")
    for a in atts_b[:3]:
        lines.append(f"     • {_scorer_line(a)}")
    if not atts_b:
        lines.append(f"     • Sin datos de goleadores")

    lines.append(f"")
    lines.append(f"   xG interno calculado: {xg_b:.2f}")
    lines.append(f"   (base {base_gf_b:.2f} × def rival {def_mod_a:.2f} × ataque {att_mod_b:.2f} × forma {form_mod_b:.2f})")

    lines.append(f"")
    lines.append(f"  {'─'*68}")

    # H2H
    lines.append(section("HISTORIAL DIRECTO (H2H)"))
    lines.append(f"   {h2h_summary}")
    for m in h2h[:5]:
        lines.append(f"     {m['date']}  {m['team_name']} vs {m['opponent_name']}: {m['goals_for']}-{m['goals_against']} ({m['result']})")
    if not h2h:
        lines.append(f"     Sin partidos registrados entre ambos")

    lines.append(f"")
    lines.append(f"  {'─'*68}")

    # Narrative
    lines.append(section("NARRATIVA"))
    narrative = _build_narrative(
        name_a, name_b, score_a, score_b, winner, fav,
        base_gf_a, base_ga_a, base_gf_b, base_ga_b,
        def_score_a, def_score_b, att_score_a, att_score_b,
        form_score_a, form_score_b, streak_a, streak_b,
        xg_a, xg_b, h2h_summary,
        team_a.get("fifa_ranking") or team_a.get("fifa_rank"),
        team_b.get("fifa_ranking") or team_b.get("fifa_rank"),
        atts_a[:1], atts_b[:1],
    )
    for line in narrative.split("\n"):
        lines.append(f"   {line}")

    lines.append(f"")
    lines.append(f"╔{'═'*width}╗")
    lines.append(f"║{'MARCADOR FINAL ESPERADO':^{width}}║")
    lines.append(f"║{f'{name_a}  {score_a} - {score_b}  {name_b}':^{width}}║")
    lines.append(f"╚{'═'*width}╝")

    return "\n".join(lines)


def _build_narrative(
    name_a: str, name_b: str,
    score_a: int, score_b: int,
    winner: str, fav: str,
    gf_a: float, ga_a: float,
    gf_b: float, ga_b: float,
    def_score_a: float, def_score_b: float,
    att_score_a: float, att_score_b: float,
    form_a: float, form_b: float,
    streak_a: str, streak_b: str,
    xg_a: float, xg_b: float,
    h2h: str,
    rank_a, rank_b,
    top_att_a: list, top_att_b: list,
) -> str:
    parts = []

    # FIFA ranking context
    if rank_a and rank_b:
        if rank_a < rank_b:
            parts.append(
                f"{name_a} (FIFA #{rank_a}) parte como el combinado de mayor jerarquía "
                f"frente a {name_b} (#{rank_b})."
            )
        else:
            parts.append(
                f"{name_b} (FIFA #{rank_b}) es el equipo de mayor rango, "
                f"pero {name_a} (#{rank_a}) no llegará sin argumentos."
            )

    # Defensive narrative
    ga_diff = ga_a - ga_b
    if abs(ga_diff) > 0.3:
        stronger_def = name_b if ga_a > ga_b else name_a
        weaker_def = name_a if ga_a > ga_b else name_b
        ga_weak = ga_a if ga_a > ga_b else ga_b
        parts.append(
            f"La defensa de {weaker_def} es el punto débil del análisis: "
            f"concede {ga_weak:.1f} goles por partido en promedio, "
            f"una cifra que {stronger_def} tiene capacidad de explotar."
        )
    else:
        parts.append(
            f"Defensivamente, ambos equipos muestran cifras similares "
            f"({ga_a:.1f} vs {ga_b:.1f} goles concedidos), lo que apunta a un partido equilibrado."
        )

    # Attacking narrative
    if top_att_a:
        a = top_att_a[0]
        ratio = (a["goals_as_nat"] or 0) / max(a["caps"] or 1, 1)
        if ratio > 0.3:
            parts.append(
                f"El arma principal de {name_a} es {a['name']} ({a['goals_as_nat']}G en {a['caps']} caps), "
                f"con una efectividad del {ratio*100:.0f}% que lo convierte en amenaza constante."
            )
    if top_att_b:
        b = top_att_b[0]
        ratio = (b["goals_as_nat"] or 0) / max(b["caps"] or 1, 1)
        if ratio > 0.3:
            parts.append(
                f"Por {name_b}, {b['name']} ({b['goals_as_nat']}G en {b['caps']} caps) "
                f"es el máximo peligro frente a la portería."
            )

    # Form narrative
    if form_a > 0.65 and streak_a:
        parts.append(f"{name_a} llega en estado de gracia: {streak_a}, un factor psicológico no menor.")
    elif form_a < 0.35 and streak_a:
        parts.append(f"{name_a} preocupa por su momento: {streak_a}, una racha que genera dudas.")

    if form_b > 0.65 and streak_b:
        parts.append(f"{name_b} llega con confianza: {streak_b}.")
    elif form_b < 0.35 and streak_b:
        parts.append(f"{name_b} llega con el ánimo bajo: {streak_b}.")

    # H2H
    if "Sin antecedentes" not in h2h:
        parts.append(f"En el historial directo: {h2h}.")

    # Favorite vs underdog
    if fav != "Paridad" and fav != name_a and fav != name_b:
        pass
    elif fav == "Paridad":
        parts.append("El mercado no da favorito claro — el análisis de datos tampoco.")
    else:
        underdog = name_b if fav == name_a else name_a
        if winner == underdog:
            parts.append(
                f"Aunque {fav} es el favorito de las casas de apuestas, "
                f"los datos apuntan a una sorpresa: {underdog} tiene margen real para ganar."
            )
        elif winner == fav:
            parts.append(
                f"{fav} es favorito y el análisis lo confirma: "
                f"el xG interno ({xg_a:.2f}-{xg_b:.2f}) respalda esa condición."
            )

    # Scoreline justification
    if score_a == score_b:
        parts.append(
            f"El equilibrio de fuerzas se traduce en un empate {score_a}-{score_b}, "
            f"el resultado más probable según el modelo Poisson con xG {xg_a:.2f}-{xg_b:.2f}."
        )
    else:
        parts.append(
            f"El marcador {score_a}-{score_b} emerge como el resultado más probable "
            f"del modelo (xG {xg_a:.2f}-{xg_b:.2f}), combinando forma, calidad individual y contexto."
        )

    return "\n".join(parts)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python models/expert_analysis.py 'Team A' 'Team B'")
        sys.exit(1)
    team_a_arg = sys.argv[1]
    team_b_arg = sys.argv[2]
    db = sys.argv[3] if len(sys.argv) > 3 else DB_DEFAULT
    print(analyze_match(team_a_arg, team_b_arg, db))
