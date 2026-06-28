"""
analyze_match.py — Análisis exhaustivo de un partido, estilo analista experto.

Objetivo: que NINGÚN factor relevante se pase por alto y que el análisis sea
consistente y repetible para CADA partido (no ad-hoc). Combina:

  • Ataque    : goles, xG, tiros, % acierto, conversión (gol/xG), ocasiones
                claras, toques en área, eficacia de ataque
  • Defensa   : goles concedidos, xG concedido, entradas, intercepciones,
                despejes, % duelos ganados
  • Portería  : paradas, % paradas, goles evitados (shot-stopping) — capta al
                portero en racha (problema Eloy Room) sin depender del rating
  • Tempo     : ventanas de gol por minuto (cuándo marca/concede), fatiga,
                peligro tardío, colapso tardío
  • Estilo    : posesión, % pase, centros, balón parado
  • Banderas  : "crisis de definición", "portero en racha", "letal tarde",
                "filtra tarde", "crea y no convierte", etc.

Degrada con elegancia: usa los stats que estén cargados y marca los que falten.
Pensado para correrse en cada análisis de partido y como base de la evaluación
de predicciones.

Uso:
    python scripts/analyze_match.py "Ecuador" "Germany"
    from analyze_match import analyze, team_profile
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

NAME = {
    "Turkiye": "Turkey", "Cabo Verde": "Cape Verde", "United States": "USA",
    "Korea Republic": "South Korea", "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Cote d'Ivoire": "Ivory Coast", "Czech Republic": "Czechia", "Curaçao": "Curacao",
}


def _tid(conn, name):
    n = NAME.get(name, name)
    r = conn.execute("SELECT id, name FROM teams WHERE name=? OR name LIKE ?",
                     (n, f"%{name}%")).fetchone()
    return (r[0], r[1]) if r else (None, None)


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def team_profile(conn, team_id, stage="group"):
    """Agrega TODOS los stats disponibles del equipo en sus partidos jugados."""
    rows = conn.execute("""
        SELECT w.home_team_id, w.away_team_id, w.score_home, w.score_away,
               w.home_team_name, w.away_team_name,
               mts.possession, mts.xg, mts.shots_total, mts.shots_on_target,
               mts.shots_inside_box, mts.clear_chances, mts.touches_box,
               mts.saves, mts.big_saves, mts.tackles_total, mts.interceptions,
               mts.clearances, mts.recoveries, mts.duels_total, mts.duels_won,
               mts.passes_pct, mts.crosses_total, mts.corners
        FROM match_team_stats mts JOIN wc_matches w ON w.id = mts.match_id
        WHERE mts.team_id=? AND w.stage=? AND w.played=1
        ORDER BY w.date
    """, (team_id, stage)).fetchall()

    n = len(rows)
    p = {"matches": n}
    if n == 0:
        return p

    gf = ga = 0
    opp_xg = []
    for r in rows:
        ishome = r["home_team_id"] == team_id
        gf += (r["score_home"] if ishome else r["score_away"]) or 0
        ga += (r["score_away"] if ishome else r["score_home"]) or 0
    # xG concedido: xG del rival en cada partido
    for r in rows:
        ishome = r["home_team_id"] == team_id
        opp_id = r["away_team_id"] if ishome else r["home_team_id"]
        oxg = conn.execute("""SELECT mts.xg FROM match_team_stats mts JOIN wc_matches w ON w.id=mts.match_id
            WHERE mts.team_id=? AND ((w.home_team_id=? AND w.away_team_id=?) OR (w.home_team_id=? AND w.away_team_id=?))
            ORDER BY w.date LIMIT 1""",
            (opp_id, r["home_team_id"], r["away_team_id"], r["away_team_id"], r["home_team_id"])).fetchone()
        if oxg:
            opp_xg.append(oxg[0])

    p["gf"], p["ga"] = gf, ga
    p["xg"] = _avg([r["xg"] for r in rows])
    p["xga"] = _avg(opp_xg)
    p["shots"] = _avg([r["shots_total"] for r in rows])
    p["sot"] = _avg([r["shots_on_target"] for r in rows])
    p["shots_box"] = _avg([r["shots_inside_box"] for r in rows])
    p["big_chances"] = _avg([r["clear_chances"] for r in rows])
    p["touches_box"] = _avg([r["touches_box"] for r in rows])
    p["possession"] = _avg([r["possession"] for r in rows])
    p["pass_pct"] = _avg([r["passes_pct"] for r in rows])
    p["saves"] = _avg([r["saves"] for r in rows])
    p["tackles"] = _avg([r["tackles_total"] for r in rows])
    p["interceptions"] = _avg([r["interceptions"] for r in rows])
    p["clearances"] = _avg([r["clearances"] for r in rows])
    dt = _avg([r["duels_total"] for r in rows]); dw = _avg([r["duels_won"] for r in rows])
    p["duel_win_pct"] = round(100 * dw / dt, 1) if dt and dw else None

    # Córners a favor / concedidos. Validado 26-jun: los córners NO correlacionan con
    # goles (r=0.23) pero sí con xG (r=0.55) → miden ASEDIO/dominio territorial, no
    # eficacia. Muchos córners + baja conversión = chocar con un bloque bajo (crea y no
    # convierte). corners_against alto + pocos goles concedidos = bloque que ABSORBE.
    p["corners_for"] = _avg([r["corners"] for r in rows])
    opp_corners = []
    for r in rows:
        ishome = r["home_team_id"] == team_id
        opp_id = r["away_team_id"] if ishome else r["home_team_id"]
        oc = conn.execute("""SELECT mts.corners FROM match_team_stats mts JOIN wc_matches w ON w.id=mts.match_id
            WHERE mts.team_id=? AND ((w.home_team_id=? AND w.away_team_id=?) OR (w.home_team_id=? AND w.away_team_id=?))
            ORDER BY w.date LIMIT 1""",
            (opp_id, r["home_team_id"], r["away_team_id"], r["away_team_id"], r["home_team_id"])).fetchone()
        if oc and oc[0] is not None:
            opp_corners.append(oc[0])
    p["corners_against"] = _avg(opp_corners)

    # Métricas DERIVADAS (lo que hace un analista)
    tot_xg = sum((r["xg"] or 0) for r in rows)
    p["conversion"] = round(gf / tot_xg, 2) if tot_xg else None         # gol/xG: >1 clínico, <1 falla
    p["finishing_gap"] = round(gf - tot_xg, 2)                          # goles - xG esperados
    p["shot_accuracy"] = round(100 * (p["sot"] or 0) / p["shots"], 1) if p["shots"] else None
    # % paradas del portero: saves / (saves + goles concedidos)  → shot-stopping
    sv = sum((r["saves"] or 0) for r in rows)
    p["save_pct"] = round(100 * sv / (sv + ga), 1) if (sv + ga) > 0 and sv else None

    # Timing histórico (cuándo marca/concede)
    tg = conn.execute("SELECT * FROM team_goal_timing WHERE team_name=?",
                      (rows[0]["home_team_name"] if rows[0]["home_team_id"] == team_id
                       else rows[0]["away_team_name"],)).fetchone()
    # nombre canónico
    nm = conn.execute("SELECT name FROM teams WHERE id=?", (team_id,)).fetchone()[0]
    tg = conn.execute("SELECT * FROM team_goal_timing WHERE team_name=?", (nm,)).fetchone()
    if tg:
        p["scored_late"] = tg["scored_76_90"]
        p["conceded_late"] = tg["conceded_76_90"]
        p["fatigue_conceded"] = tg["fatigue_conceded"]
        p["late_collapse"] = tg["late_collapse"]
        _W = ["1_15", "16_30", "31_45", "46_60", "61_75", "76_90"]
        p["hist_scored"] = [tg[f"scored_{w}"] for w in _W]
        p["hist_conceded"] = [tg[f"conceded_{w}"] for w in _W]

    # Timing REAL de este Mundial (fifa_match_goals) — prioritario si hay datos.
    # Captura la forma actual (Alemania concede temprano HOY aunque el histórico
    # diga otra cosa). Sample chico → se usa como señal, no como verdad absoluta.
    wc = conn.execute("SELECT * FROM wc_goal_timing WHERE team_id=?", (team_id,)).fetchone()
    if wc and wc["matches"]:
        s = [wc[f"s{i}"] for i in range(6)]
        c = [wc[f"c{i}"] for i in range(6)]
        LAB = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90"]
        p["wc_scored"] = s
        p["wc_conceded"] = c
        if sum(s):
            p["wc_peak_scored"] = LAB[s.index(max(s))]
        if sum(c):
            p["wc_peak_conceded"] = LAB[c.index(max(c))]

    # Forma reciente INCLUYENDO amistosos (team_matches) — muestra más amplia que el
    # Mundial solo. Pedido del dueño 26-jun: "siempre incluir amistosos". Resultados
    # (no hay tiros/xG de amistosos en la DB), pero da ritmo real de marcar/encajar.
    rec = conn.execute("""
        SELECT opponent_name, goals_for, goals_against, result, competition, date
        FROM team_matches WHERE team_id=? AND date >= date('now','-12 months')
        ORDER BY date DESC LIMIT 8
    """, (team_id,)).fetchall()
    if rec:
        w = sum(1 for r in rec if r["result"] == "W")
        d = sum(1 for r in rec if r["result"] == "D")
        l = sum(1 for r in rec if r["result"] == "L")
        gf_r = sum((r["goals_for"] or 0) for r in rec)
        ga_r = sum((r["goals_against"] or 0) for r in rec)
        n = len(rec)
        p["recent_form"] = {
            "n": n, "w": w, "d": d, "l": l,
            "gf_avg": round(gf_r / n, 2), "ga_avg": round(ga_r / n, 2),
            "last5": [f"{r['goals_for']}-{r['goals_against']}{r['result']}" for r in rec[:5]],
        }

    _player_profile(conn, team_id, p)
    er = conn.execute("SELECT elo FROM team_elo WHERE team_id=?", (team_id,)).fetchone()
    if er:
        p["elo"] = er[0]
    return p


# Rendimiento INDIVIDUAL en este Mundial — VALIDADO 27-jun por backtest de G/H/I:
# integrar el desempeño de jugadores acercó los marcadores reales (error de marcador
# ~se redujo a la mitad, 12→~5-6 en 6 partidos), acertando los DOS empates que el
# pronóstico de equipo falló (Egipto 1-1 por Beiranvand, Cabo Verde 0-0 por dos GKs
# sin delanteros) y los totales goleadores (Bélgica 0→5, Francia 1-4). El valor está
# en SEÑALES ESTRUCTURALES, no en varianza pura (no predijo el 5-0 de Senegal). Tres
# señales validadas:
#   1) KILLER ENCHUFADO  — un crack con rating alto Y goles sube el techo goleador
#      (Messi 9.6/5G, Mbappé 8.65/4G, Haaland 8.25/4G).
#   2) PORTERO EN FORMA  — GK con rating alto baja el marcador hacia empate/mínimo
#      margen (Beiranvand 8.1, Vozinha 7.8 + Al-Owais 7.35 → 0-0).
#   3) CALIDAD A DEBER   — ratings individuales altos pero el equipo NO marca = "a
#      deber", regresa al alza y explota (Bélgica ratings ~7.5 con 0 goles → 5).
def _player_profile(conn, team_id, p):
    WC = ("competition IN ('World Cup','FIFA World Cup 2026','WC2026') "
          "AND match_date >= '2026-06-01'")
    rows = conn.execute(f"""
        SELECT player_name, position, COUNT(*) mp, SUM(minutes) mins,
               ROUND(AVG(rating), 2) ar, SUM(goals) g, SUM(assists) a
        FROM match_player_stats
        WHERE team_id=? AND {WC} AND rating IS NOT NULL
        GROUP BY player_name HAVING SUM(minutes) >= 60
        ORDER BY ar DESC
    """, (team_id,)).fetchall()
    if not rows:
        return
    # Top performers de campo (excluye porteros para el techo goleador)
    GK_POS = {"G", "GK"}
    outfield = [r for r in rows if (r["position"] or "") not in GK_POS]
    p["players_top"] = [(r["player_name"], r["ar"], r["g"] or 0, r["a"] or 0)
                        for r in outfield[:4]]
    # 1) KILLER ENCHUFADO: rating alto + goles reales
    for r in outfield:
        if r["ar"] is not None and r["ar"] >= 7.6 and (r["g"] or 0) >= 2:
            p["star_scorer"] = (r["player_name"], r["ar"], r["g"])
            break
    # 2) PORTERO EN FORMA (por rating, complementa el save_pct de equipo)
    gks = [r for r in rows if (r["position"] or "") in GK_POS]
    if gks:
        g0 = max(gks, key=lambda r: r["ar"] or 0)
        if g0["ar"] is not None and g0["ar"] >= 7.5:
            p["gk_form"] = (g0["player_name"], g0["ar"])
    # 3) CALIDAD A DEBER: top-6 con rating alto pero el equipo casi no marca
    top6 = [r["ar"] for r in outfield[:6] if r["ar"] is not None]
    mt = p.get("matches") or 0
    if top6 and mt:
        squad_q = round(sum(top6) / len(top6), 2)
        p["squad_quality"] = squad_q
        gpm = (p.get("gf") or 0) / mt
        if squad_q >= 7.3 and gpm < 1.2:
            p["quality_owed"] = (squad_q, round(gpm, 2))


def _flags(p):
    f = []
    if p.get("conversion") is not None:
        if p["conversion"] < 0.6 and (p.get("xg") or 0) > 1.2:
            f.append("CRISIS DE DEFINICIÓN (crea mucho, no convierte)")
        elif p["conversion"] > 1.3:
            f.append("FINALIZACIÓN CLÍNICA (convierte por encima de xG)")
    if p.get("save_pct") is not None and p["save_pct"] >= 75:
        f.append(f"PORTERO EN RACHA ({p['save_pct']}% paradas)")
    if p.get("scored_late") is not None and p["scored_late"] >= 0.5:
        f.append(f"LETAL TARDE (marca {p['scored_late']} en 76-90)")
    if p.get("conceded_late") is not None and p["conceded_late"] >= 0.3:
        f.append(f"FILTRA TARDE (concede {p['conceded_late']} en 76-90)")
    if p.get("late_collapse"):
        f.append("RIESGO DE COLAPSO TARDÍO")
    if p.get("possession") is not None and p["possession"] < 38:
        f.append("JUEGA AL CONTRAGOLPE (baja posesión)")
    # Córners / asedio — patrón validado 26-jun (n=11 favoritos): el que asedia (7+
    # córners/p) con conversión <1.0 crea contra un bloque bajo pero NO convierte; es
    # señal de VARIANZA (goleada o 0-0), no de nivel — se quedó en blanco 27% vs 4%.
    cf = p.get("corners_for"); conv = p.get("conversion")
    if cf is not None and cf >= 7 and conv is not None and conv < 1.0:
        f.append(f"ASEDIO ESTÉRIL ({cf:.0f} córners/p, conversión {conv}: crea vs bloque bajo "
                 f"pero no convierte → varianza alta, no fiar goleada)")
    ca = p.get("corners_against"); mt = p.get("matches") or 0
    if ca is not None and ca >= 7 and mt and p.get("ga") is not None and (p["ga"] / mt) <= 1.0:
        f.append(f"BLOQUE QUE ABSORBE (concede {ca:.0f} córners/p pero solo "
                 f"{p['ga']/mt:.1f} goles/p — defensa que aguanta el asedio)")
    # Señales de JUGADOR validadas 27-jun (backtest G/H/I) — ver _player_profile
    if p.get("star_scorer"):
        nm_, rt_, g_ = p["star_scorer"]
        f.append(f"KILLER ENCHUFADO ({nm_} {rt_}, {g_}G → sube el techo goleador)")
    if p.get("gk_form"):
        nm_, rt_ = p["gk_form"]
        f.append(f"PORTERO EN FORMA ({nm_} rating {rt_} → baja el marcador rival)")
    if p.get("quality_owed"):
        q_, gpm_ = p["quality_owed"]
        f.append(f"CALIDAD A DEBER (top6 rating {q_} pero {gpm_} goles/p → 'a deber', "
                 f"regresa al alza: riesgo de explosión goleadora)")
    # Patrones del MUNDIAL real (fifa_match_goals) — corrigen al histórico
    s = p.get("wc_scored"); c = p.get("wc_conceded")
    if s and sum(s) and (s[3] + s[4] + s[5]) > (s[0] + s[1] + s[2]):
        f.append(f"WC: marca más en 2ª mitad (pico {p.get('wc_peak_scored')})")
    if c and sum(c):
        if (c[0] + c[1]) >= max(2, 0.5 * sum(c)):
            f.append(f"WC: concede TEMPRANO (1-30) — vulnerable al inicio")
        elif c[5] >= max(2, 0.4 * sum(c)):
            f.append(f"WC: filtra TARDE (76-90)")
    return f


def _fmt(p):
    g = lambda k, d="—": (p.get(k) if p.get(k) is not None else d)
    return (
        f"  {p['matches']} partidos | GF {g('gf')}  GA {g('ga')}\n"
        f"  ATAQUE   xG {g('xg')}/p · tiros {g('shots')} (a puerta {g('sot')}, "
        f"precisión {g('shot_accuracy')}%) · ocas {g('big_chances')} · conversión {g('conversion')} (gol/xG)\n"
        f"  DEFENSA  xG concedido {g('xga')}/p · entradas {g('tackles')} · intercep {g('interceptions')} · "
        f"despejes {g('clearances')} · duelos ganados {g('duel_win_pct')}%\n"
        f"  PORTERO  paradas {g('saves')}/p · % paradas {g('save_pct')}%\n"
        f"  ESTILO   posesión {g('possession')}% · pase {g('pass_pct')}% · "
        f"córners {g('corners_for')}/p (concede {g('corners_against')}/p)\n"
        f"  TIMING   marca tarde(76-90) {g('scored_late')} · concede tarde {g('conceded_late')} · "
        f"fatiga_concede {g('fatigue_conceded')}"
        + (_fmt_players(p))
        + (_fmt_form(p.get("recent_form")))
    )


def _fmt_players(p):
    top = p.get("players_top")
    if not top:
        return ""
    js = " · ".join(f"{n} {r}{f' {g}G' if g else ''}{f' {a}A' if a else ''}"
                    for n, r, g, a in top)
    return f"\n  JUGADORES {js}"


def _fmt_form(rf):
    if not rf:
        return ""
    return (f"\n  FORMA    últimos {rf['n']} (incl. amistosos): {rf['w']}V-{rf['d']}E-{rf['l']}D · "
            f"marca {rf['gf_avg']}/p · encaja {rf['ga_avg']}/p · "
            f"[{' '.join(rf['last5'])}]")


def analyze(team_a, team_b, db_path=DB, verbose=True):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    aid, an = _tid(conn, team_a); bid, bn = _tid(conn, team_b)
    if not aid or not bid:
        print(f"No encontré equipo: {team_a if not aid else ''} {team_b if not bid else ''}")
        return
    pa = team_profile(conn, aid); pb = team_profile(conn, bid)
    fa = _flags(pa); fb = _flags(pb)
    # FASE FINAL — desempate (resistencia/portero/pateadores) si ambos califican
    ko = None
    try:
        from knockout_tiebreaker import ratings as _ko_ratings
        _kr = _ko_ratings(conn)
        if an in _kr and bn in _kr:
            ko = (_kr[an], _kr[bn])
    except Exception:
        ko = None
    conn.close()
    if verbose:
        print("=" * 78)
        print(f"ANÁLISIS EXHAUSTIVO — {an} vs {bn}")
        print("=" * 78)
        print(f"\n[{an}]"); print(_fmt(pa))
        if fa: print("  ⚑ " + " | ".join(fa))
        print(f"\n[{bn}]"); print(_fmt(pb))
        if fb: print("  ⚑ " + " | ".join(fb))
        print("\n" + "-" * 78)
        print("PUNTOS CLAVE DEL CRUCE:")
        for line in _matchup_notes(an, pa, fa, bn, pb, fb):
            print("  • " + line)
        if ko:
            ka, kb = ko
            sh = ka["tie"] / (ka["tie"] + kb["tie"]) if (ka["tie"] + kb["tie"]) else 0.5
            fav, fav_sh = (an, sh) if sh >= 0.5 else (bn, 1 - sh)
            print("\nFASE FINAL — si va a penales/prórroga (resistencia·portero·pateadores):")
            print(f"  {an}: desempate {ka['tie']*100:.0f}% (resist {ka['resist']*100:.0f}/GK {ka['gk']*100:.0f}/pat {ka['pat']*100:.0f})")
            print(f"  {bn}: desempate {kb['tie']*100:.0f}% (resist {kb['resist']*100:.0f}/GK {kb['gk']*100:.0f}/pat {kb['pat']*100:.0f})")
            print(f"  → favorito en el desempate: {fav} ({fav_sh*100:.0f}%)")
    return {"a": (an, pa, fa), "b": (bn, pb, fb), "ko": ko}


_LAB = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90"]


def _share(arr):
    s = sum(arr) if arr else 0
    return [x / s for x in arr] if s else None


def _window_clash(att_name, att_p, def_name, def_p):
    """Analiza si las ventanas de ATAQUE del atacante coinciden con las de
    FRAGILIDAD del defensor. Esto es el corazón del análisis: NO basta con quién
    crea más, sino CUÁNDO ataca uno vs CUÁNDO se rompe el otro."""
    a = _share(att_p.get("hist_scored"))
    d = _share(def_p.get("hist_conceded"))
    if not a or not d:
        return None
    # Guarda por VOLUMEN: un ataque ínfimo (xG bajo) no es amenaza aunque su
    # share caiga en la franja floja del rival (ej. Túnez 0.17 xG/p).
    axg = att_p.get("xg")
    if axg is not None and axg < 0.70:
        return (f"~ {att_name} casi no genera ({axg:.2f} xG/p) → su 'pico' por "
                f"minuto es irrelevante; sin amenaza real pese a la franja")
    apeak = a.index(max(a))                       # ventana donde más ataca
    danger = [a[i] * d[i] for i in range(6)]       # ataque × fragilidad
    best = danger.index(max(danger))
    avg_d = sum(d) / 6
    aligned = d[apeak] >= avg_d * 1.05             # ¿el defensor es débil donde ataca el atacante?
    if aligned:
        return (f"✓ {att_name} ataca más en min {_LAB[apeak]} y {def_name} es "
                f"vulnerable ahí → AMENAZA REAL (pico de peligro: {_LAB[best]})")
    return (f"✗ {att_name} ataca en min {_LAB[apeak]} pero {def_name} aguanta bien "
            f"esa franja → ventana NEUTRALIZADA (las ventanas NO coinciden)")


def _matchup_notes(an, pa, fa, bn, pb, fb):
    notes = []
    if pa.get("xg") and pb.get("xga"):
        notes.append(f"Ataque {an} ({pa['xg']:.2f} xG/p) vs defensa {bn} (concede {pb['xga']:.2f} xG/p)")
    if pb.get("xg") and pa.get("xga"):
        notes.append(f"Ataque {bn} ({pb['xg']:.2f} xG/p) vs defensa {an} (concede {pa['xga']:.2f} xG/p)")
    # CHOQUE DE VENTANAS (cuándo ataca uno vs cuándo se rompe el otro) — clave
    for att_n, att_p, def_n, def_p in [(an, pa, bn, pb), (bn, pb, an, pa)]:
        clash = _window_clash(att_n, att_p, def_n, def_p)
        if clash:
            notes.append(clash)
    # portero en racha
    for p, n, o in [(pa, an, bn), (pb, bn, an)]:
        if p.get("save_pct") and p["save_pct"] >= 75:
            notes.append(f"{n} tiene portero en racha ({p['save_pct']}% paradas) → baja el marcador de {o}")
    # Señales de JUGADOR (validadas 27-jun): killer enchufado, GK en forma, calidad a deber
    for p, n, o in [(pa, an, bn), (pb, bn, an)]:
        if p.get("star_scorer"):
            nm_, rt_, g_ = p["star_scorer"]
            notes.append(f"{n} tiene KILLER enchufado ({nm_} {rt_}, {g_}G) → su techo goleador sube; ojo si descansa/rota")
        if p.get("gk_form"):
            nm_, rt_ = p["gk_form"]
            notes.append(f"GK {nm_} de {n} en forma (rating {rt_}) → tiende a bajar el marcador de {o}")
        if p.get("quality_owed"):
            q_, gpm_ = p["quality_owed"]
            notes.append(f"⚠ {n} con CALIDAD A DEBER (top6 {q_}, {gpm_} goles/p) → regresión al alza, riesgo de explosión goleadora")
    # corrección por timing REAL del Mundial (si contradice al histórico)
    for n, p in [(an, pa), (bn, pb)]:
        c = p.get("wc_conceded")
        if c and sum(c) and (c[0] + c[1]) >= max(2, 0.5 * sum(c)):
            notes.append(f"⚠ {n}: en ESTE Mundial concede TEMPRANO (1-30), corrige su histórico")
    # ALERTA EMPATE — validado 27-jun (backtest 72 grupos): el EMPATE es el error
    # sistemático #1 (24.5% de empates no predichos). La señal PREDICTIVA es la
    # PAREJURA por Elo, NO el portero en forma (ese backtest salió NULO: la forma
    # previa del GK no predice; el "empate-candado" es varianza intra-partido). En
    # duelos parejos (|Elo|<50) el 41% terminó en empate (vs 22% en los disparejos)
    # → no sobre-favorecer a un lado. Es DISPLAY; el sesgo pro-empate en el modelo
    # queda pendiente de A/B en el backtest de 535 partidos.
    ea, eb = pa.get("elo"), pb.get("elo")
    if ea is not None and eb is not None:
        gap = abs(ea - eb)
        if gap < 50:
            notes.append(f"⚖ PARTIDO PAREJO (Elo {ea:.0f} vs {eb:.0f}, brecha {gap:.0f}) → "
                         f"ALERTA EMPATE: el 41% de los duelos parejos del torneo terminó "
                         f"en empate; no sobre-favorecer a un lado")
    return notes


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    analyze(sys.argv[1], sys.argv[2])
