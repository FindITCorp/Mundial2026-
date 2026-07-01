"""
simulate_match.py — ANÁLISIS INTEGRAL OBLIGATORIO por partido (forense + ventanas + Monte Carlo).

Origen (01-jul): el dueño, con razón, se frustró — tengo goles con minuto, rivales, quién
marcó, cuándo se rompe cada equipo, y daba "gana el favorito". Esto FUERZA usar todo:
  1. GOL POR GOL: cada gol a favor/en contra con minuto, autor y CONTRA QUIÉN.
  2. VENTANAS: en qué franja marca y en qué franja se rompe cada equipo (choque).
  3. MONTE CARLO (40k sims, con sobredispersión para feast/famine): 1X2, over2.5, ambos
     marcan, marcadores más probables, prob de AVANCE. TODOS los escenarios, no un punto.

Uso:  python scripts/simulate_match.py "Belgium" "Senegal"
"""
import random
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
BUCKETS = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 91), (92, 130)]
LBL = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90", "90+"]


def _bucket(m):
    for i, (lo, hi) in enumerate(BUCKETS):
        if m is not None and lo <= m <= hi:
            return i
    return None


def forensics(conn, team):
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()[0]
    name = {r[0]: r[1] for r in conn.execute("SELECT id,name FROM teams")}
    goals = defaultdict(list); teams_in = defaultdict(set)
    for fmid, mn, dbt, pn in conn.execute(
            "SELECT fifa_match_id,minute_num,db_team_id,player_name FROM fifa_match_events "
            "WHERE type_code IN (0,41) AND db_team_id IS NOT NULL"):
        goals[fmid].append((mn, dbt, pn))
    for fmid, dbt in conn.execute("SELECT DISTINCT fifa_match_id,db_team_id FROM fifa_match_events WHERE db_team_id IS NOT NULL"):
        teams_in[fmid].add(dbt)
    lines = []; att = [0]*7; conc = [0]*7
    for fmid, gs in goals.items():
        if tid not in teams_in[fmid] or len(teams_in[fmid]) != 2:
            continue
        opp = [t for t in teams_in[fmid] if t != tid][0]
        gf = sorted([(m, pn) for m, d, pn in gs if d == tid])
        ga = sorted([(m, pn) for m, d, pn in gs if d == opp])
        for m, _ in gf:
            b = _bucket(m); att[b] += 1 if b is not None else 0
        for m, _ in ga:
            b = _bucket(m); conc[b] += 1 if b is not None else 0
        lines.append((name.get(opp, opp), len(gf), len(ga), gf, ga))
    return lines, att, conc


def _rate(conn, team):
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()[0]
    gf = ga = n = 0
    for h, a, sh, sa, hid in conn.execute(
            "SELECT home_team_name,away_team_name,score_home,score_away,home_team_id FROM wc_matches "
            "WHERE (home_team_id=? OR away_team_id=?) AND played=1 AND stage='group'", (tid, tid)):
        f, cc = (sh, sa) if hid == tid else (sa, sh); gf += f; ga += cc; n += 1
    return (gf/n, ga/n) if n else (1.2, 1.2)


def _draw(l, r=3.0):
    lam = random.gammavariate(r, l/r)
    k = 0; p = math.exp(-lam); cum = p; u = random.random()
    while u > cum and k < 12:
        k += 1; p *= lam/k; cum += p
    return k


def simulate(conn, a, b, n=40000):
    agf, aga = _rate(conn, a); bgf, bga = _rate(conn, b)
    la, lb = (agf+bga)/2, (bgf+aga)/2
    res = Counter(); out = Counter(); over = bts = 0
    for _ in range(n):
        ga_, gb_ = _draw(la), _draw(lb)
        res[(ga_, gb_)] += 1
        out['A' if ga_ > gb_ else ('B' if gb_ > ga_ else 'D')] += 1
        if ga_+gb_ > 2.5: over += 1
        if ga_ and gb_: bts += 1
    return {"la": la, "lb": lb, "res": res, "out": out, "over": over/n, "bts": bts/n, "n": n,
            "agf": agf, "aga": aga, "bgf": bgf, "bga": bga}


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    a, b = sys.argv[1], sys.argv[2]
    for tm in (a, b):
        lines, att, conc = forensics(conn, tm)
        print(f"\n===== {tm} — GOL POR GOL =====")
        for opp, gf, ga, gfl, gal in lines:
            print(f"  vs {opp:14} {gf}-{ga}"
                  + (f"  | marca {[m for m,_ in gfl]}" if gfl else "")
                  + (f"  encaja {[m for m,_ in gal]}" if gal else ""))
        print(f"  franja que MARCA:   " + " ".join(f"{LBL[i]}:{att[i]}" for i in range(7)))
        print(f"  franja que ENCAJA:  " + " ".join(f"{LBL[i]}:{conc[i]}" for i in range(7)))
    s = simulate(conn, a, b)
    N = s["n"]
    print(f"\n===== MONTE CARLO ({N} sims) — λ {a} {s['la']:.2f} / {b} {s['lb']:.2f} =====")
    print(f"  1X2: {a} {100*s['out']['A']/N:.0f}% / empate {100*s['out']['D']/N:.0f}% / {b} {100*s['out']['B']/N:.0f}%")
    print(f"  Over 2.5: {100*s['over']:.0f}%  |  ambos marcan: {100*s['bts']:.0f}%")
    print("  marcadores más probables: " + ", ".join(f"{x}-{y} {100*ct/N:.0f}%" for (x, y), ct in s['res'].most_common(6)))
    adv_a = s['out']['A']/N + (s['out']['D']/N)*0.5
    print(f"  AVANCE (empate→~50/50): {a} {100*adv_a:.0f}%  {b} {100*(1-adv_a):.0f}%")
    conn.close()
