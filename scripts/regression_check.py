"""
regression_check.py — CHECK de disciplina (no oráculo) contra mis sesgos de análisis.

Señal: diferencia de REMATES A PUERTA por partido (SOT-dif) de los partidos PREVIOS.
SOT a favor = paradas del rival + goles propios; SOT en contra = paradas propias +
goles del rival (desde fifa_match_events, play-by-play FIFA).

⚠️ HONESTIDAD (validación 30-jun, NO complaciente):
  • Fuera de muestra (SOT-dif de GRUPOS → avance en octavos): **5/6**. El único fallo
    fue Alemania-Paraguay, decidido en PENALES (moneda al aire, impredecible por juego).
  • Le ACERTÓ a un override experto que yo fallé (CIV-Noruega: mi sello CIV, SOT decía
    Noruega → ganó Noruega). Ese es su valor real: corregir excesos de análisis.
  • DESCARTADO el "91% intra-partido": es circular (los remates a puerta INCLUYEN goles).
  • n pequeño (6), se solapa con calidad/Elo (quizá solo re-mide al mejor equipo), y NO
    está probado que le gane al modelo base. La narrativa de "regresa al alza" está
    sobrevendida: lo validado es "el que dominó tiros a puerta antes, avanza".
  → USAR COMO ALARMA/desempate, no como predicción autónoma.

Uso:
    python scripts/regression_check.py "Mexico" "Ecuador"   # señal para un cruce
    python scripts/regression_check.py --table              # mapa over/infra-rinde
    python scripts/regression_check.py "A" "B" --groups-only # solo grupos (repro OOS)
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
R32_STAGE = "289287"


def _profiles(conn, groups_only=False):
    """{team_id: {'sf','sa','gf','ga','n'}} de remates a puerta y goles por partido."""
    ev = defaultdict(lambda: defaultdict(lambda: {"saves": 0, "goals": 0}))
    stage = {}
    for fmid, tc, dbt, stg in conn.execute(
            "SELECT fifa_match_id, type_code, db_team_id, stage_id FROM fifa_match_events "
            "WHERE db_team_id IS NOT NULL AND type_code IN (57,0,41)"):
        stage[fmid] = stg
        ev[fmid][dbt]["saves" if tc == 57 else "goals"] += 1
    prof = defaultdict(lambda: {"sf": 0, "sa": 0, "gf": 0, "ga": 0, "n": 0})
    for m, teams in ev.items():
        if groups_only and stage.get(m) == R32_STAGE:
            continue
        if len(teams) != 2:
            continue
        a, b = list(teams.keys())
        for t, o in [(a, b), (b, a)]:
            prof[t]["sf"] += teams[o]["saves"] + teams[t]["goals"]
            prof[t]["sa"] += teams[t]["saves"] + teams[o]["goals"]
            prof[t]["gf"] += teams[t]["goals"]
            prof[t]["ga"] += teams[o]["goals"]
            prof[t]["n"] += 1
    return prof


def sot_diff(conn, team, groups_only=False):
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
    if not tid:
        return None
    d = _profiles(conn, groups_only).get(tid[0])
    return (d["sf"] - d["sa"]) / d["n"] if d and d["n"] else None


def check(conn, a, b, groups_only=False):
    da, db = sot_diff(conn, a, groups_only), sot_diff(conn, b, groups_only)
    if da is None or db is None:
        return None
    fav = a if da > db else (b if db > da else "parejo")
    return {"a": a, "da": da, "b": b, "db": db, "fav": fav, "gap": abs(da - db)}


CAVEAT = ("  (check anti-sesgo, NO oráculo: 5/6 fuera de muestra, n chico, se solapa "
          "con calidad; úsalo como alarma si contradice tu sello)")


def _table(conn):
    prof = _profiles(conn)
    name = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM teams")}
    rows = []
    for t, d in prof.items():
        if d["n"] < 3:
            continue
        sd = (d["sf"] - d["sa"]) / d["n"]
        gd = (d["gf"] - d["ga"]) / d["n"]
        rows.append((name.get(t, t), sd, gd, sd - gd))  # sd-gd alto = infra-rinde
    print(f"{'EQUIPO':16}{'SOTdif/p':>9}{'GOLdif/p':>9}{'brecha':>8}")
    print("-- INFRA-RINDEN (dominan tiros, no marcan → ojo, pueden estallar) --")
    for r in sorted(rows, key=lambda x: -x[3])[:6]:
        print(f"{r[0]:16}{r[1]:+9.1f}{r[2]:+9.1f}{r[3]:+8.1f}")
    print("-- SOBRE-RINDEN (ganan/marcan más que sus tiros → frágiles) --")
    for r in sorted(rows, key=lambda x: x[3])[:6]:
        print(f"{r[0]:16}{r[1]:+9.1f}{r[2]:+9.1f}{r[3]:+8.1f}")
    print(CAVEAT)


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    go = "--groups-only" in sys.argv
    if "--table" in sys.argv:
        _table(conn)
    elif len(args) >= 2:
        r = check(conn, args[0], args[1], go)
        if not r:
            print("sin datos suficientes")
        else:
            print(f"SOT-dif previo{' (grupos)' if go else ''}: "
                  f"{r['a']} {r['da']:+.1f}  vs  {r['b']} {r['db']:+.1f}")
            print(f"→ la señal favorece a: {r['fav']} (brecha {r['gap']:.1f})")
            print(CAVEAT)
    else:
        print(__doc__)
    conn.close()
