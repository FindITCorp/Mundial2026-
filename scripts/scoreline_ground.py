"""
scoreline_ground.py — Fundamenta el MARCADOR en registros REALES, no en la λ cruda.

Origen (01-jul): el dueño cuestionó "¿por qué England le mete 2 a Congo DR?" cuando Congo
DR concede EXACTAMENTE 1/partido en el torneo (a Portugal, Colombia, Uzbekistán). Mi 2-0
era output del modelo, sin fundamento. Regla nueva: antes de sellar un marcador, cruzar lo
que A marca vs lo que B CONCEDE de verdad (y viceversa), con máximos y contra quién.

Da, por cada lado:
  • goles marcados/p (y máximo) del atacante
  • goles concedidos/p (y máximo, y contra quién) del defensor  ← el ancla
  • remates a puerta concedidos/p (proceso defensivo)
  • sugerencia de goles = mezcla del ataque de A y la concesión de B, anclada al MÁXIMO
    que el defensor ha permitido (no inventar goles por encima de su patrón real).

Uso:  python scripts/scoreline_ground.py "England" "DR Congo"
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def _record(conn, tid):
    """goles marcados/concedidos por partido de grupo + detalle de concesión."""
    gf = ga = n = 0
    conceded = []   # (goles_encajados, rival)
    scored = []
    for h, a, sh, sa, hid in conn.execute(
            "SELECT home_team_name,away_team_name,score_home,score_away,home_team_id "
            "FROM wc_matches WHERE (home_team_id=? OR away_team_id=?) AND played=1 AND stage='group'",
            (tid, tid)):
        if hid == tid:
            rival, f, c = a, sh, sa
        else:
            rival, f, c = h, sa, sh
        gf += f; ga += c; n += 1
        conceded.append((c, rival)); scored.append((f, rival))
    if not n:
        return None
    return {"gf": gf / n, "ga": ga / n, "n": n,
            "max_conc": max(conceded), "max_scored": max(scored), "conceded": conceded}


def _sot_conceded(conn, tid):
    ev = defaultdict(lambda: defaultdict(lambda: {"saves": 0, "goals": 0}))
    for fmid, tc, dbt in conn.execute(
            "SELECT fifa_match_id,type_code,db_team_id FROM fifa_match_events "
            "WHERE db_team_id IS NOT NULL AND type_code IN (57,0,41)"):
        ev[fmid][dbt]["saves" if tc == 57 else "goals"] += 1
    tot = mm = 0
    for m, teams in ev.items():
        if tid in teams and len(teams) == 2:
            opp = [t for t in teams if t != tid][0]
            tot += teams[tid]["saves"] + teams[opp]["goals"]; mm += 1
    return tot / mm if mm else None


def ground(conn, a, b):
    aid = conn.execute("SELECT id FROM teams WHERE name=?", (a,)).fetchone()
    bid = conn.execute("SELECT id FROM teams WHERE name=?", (b,)).fetchone()
    if not aid or not bid:
        return None
    ra, rb = _record(conn, aid[0]), _record(conn, bid[0])
    if not ra or not rb:
        return None
    # goles sugeridos para A: mezcla ataque de A + concesión de B, TOPADO al máximo que B ha permitido
    def suggest(att, deff):
        raw = (att["gf"] + deff["ga"]) / 2
        cap = deff["max_conc"][0] + 0.5           # no superar mucho su peor partido
        return min(raw, cap)
    return {"a": a, "b": b, "ra": ra, "rb": rb,
            "a_goals": suggest(ra, rb), "b_goals": suggest(rb, ra),
            "a_sot_conc": _sot_conceded(conn, aid[0]), "b_sot_conc": _sot_conceded(conn, bid[0])}


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    g = ground(conn, sys.argv[1], sys.argv[2])
    if not g:
        print("sin datos"); sys.exit(0)
    a, b, ra, rb = g["a"], g["b"], g["ra"], g["rb"]
    print(f"=== FUNDAMENTO DE MARCADOR — {a} vs {b} ===")
    print(f"{a}: marca {ra['gf']:.2f}/p (máx {ra['max_scored'][0]} vs {ra['max_scored'][1]}) · "
          f"concede {ra['ga']:.2f}/p (máx {ra['max_conc'][0]} vs {ra['max_conc'][1]}) · "
          f"SOT concedidos {g['a_sot_conc']:.1f}/p")
    print(f"{b}: marca {rb['gf']:.2f}/p (máx {rb['max_scored'][0]} vs {rb['max_scored'][1]}) · "
          f"concede {rb['ga']:.2f}/p (máx {rb['max_conc'][0]} vs {rb['max_conc'][1]}) · "
          f"SOT concedidos {g['b_sot_conc']:.1f}/p")
    print(f"→ {b} concede como máx {rb['max_conc'][0]} en un partido → NO sellar a {a} por encima sin razón fuerte")
    print(f"→ MARCADOR FUNDAMENTADO ≈ {a} {round(g['a_goals'])}-{round(g['b_goals'])} {b}")
    conn.close()
