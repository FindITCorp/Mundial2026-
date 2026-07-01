"""
live_winprob.py — Probabilidad de resultado/avance EN VIVO (idea autónoma #4).

Motivación: mi lectura en vivo de CIV-Noruega al descanso (Noruega ~57%) le GANÓ a mi
sello prepartido. Con el marcador y el minuto actuales, un modelo Poisson sobre el tiempo
RESTANTE actualiza las probabilidades — course-correction sobre la marcha.

λ por equipo = (goles-a-favor/p propios + goles-en-contra/p del rival)/2, escalado por el
tiempo que queda. Convoluciona los goles restantes con el marcador actual. En knockout, el
empate a 90' se resuelve como ~moneda al aire (tope de tanda, coherente con predict_ensemble).

Uso:
    python scripts/live_winprob.py "Ivory Coast" "Norway" --match 400021514   # auto-live
    python scripts/live_winprob.py "Mexico" "Ecuador" --score 1 1 --minute 70 # manual
"""
import json
import math
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def _rate(conn, tid):
    """(goles_favor/p, goles_contra/p) en fase de grupos del Mundial."""
    gf = ga = n = 0
    for sh, sa, h in conn.execute(
            "SELECT score_home,score_away,home_team_id FROM wc_matches "
            "WHERE (home_team_id=? OR away_team_id=?) AND played=1 AND stage='group'", (tid, tid)):
        if h == tid:
            gf += sh; ga += sa
        else:
            gf += sa; ga += sh
        n += 1
    return (gf / n, ga / n) if n else (1.2, 1.2)


def _live(match, stage="289287"):
    url = f"https://api.fifa.com/api/v3/live/football/17/285023/{stage}/{match}"
    d = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read())
    sh = d.get("HomeTeam", {}).get("Score") or 0
    sa = d.get("AwayTeam", {}).get("Score") or 0
    mt = d.get("MatchTime") or "0'"
    m = re.findall(r"\d+", mt)
    minute = int(m[0]) if m else 0
    return sh, sa, minute, d.get("MatchStatus")


def _pois(l, k):
    return math.exp(-l) * l ** k / math.factorial(k)


def live_probs(conn, a, b, sh, sa, minute, knockout=True):
    aid = conn.execute("SELECT id FROM teams WHERE name=?", (a,)).fetchone()[0]
    bid = conn.execute("SELECT id FROM teams WHERE name=?", (b,)).fetchone()[0]
    afa, aga = _rate(conn, aid)
    bfa, bga = _rate(conn, bid)
    la90 = (afa + bga) / 2
    lb90 = (bfa + aga) / 2
    rem = max(0.0, 90 - minute) / 90.0
    la, lb = la90 * rem, lb90 * rem
    ph = pd = pa = 0.0
    for ga_ in range(8):
        for gb_ in range(8):
            p = _pois(la, ga_) * _pois(lb, gb_)
            fa, fb = sh + ga_, sa + gb_
            if fa > fb: ph += p
            elif fb > fa: pa += p
            else: pd += p
    out = {"a": a, "b": b, "score": f"{sh}-{sa}", "minute": minute,
           "ph": ph, "pd": pd, "pa": pa}
    if knockout:                      # empate a 90' → ~moneda al aire (tope de tanda)
        out["adv_a"] = ph + pd * 0.5
        out["adv_b"] = pa + pd * 0.5
    return out


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(0)
    a, b = args[0], args[1]
    if "--match" in sys.argv:
        mid = sys.argv[sys.argv.index("--match") + 1]
        sh, sa, minute, st = _live(mid)
    elif "--score" in sys.argv:
        i = sys.argv.index("--score"); sh, sa = int(sys.argv[i+1]), int(sys.argv[i+2])
        minute = int(sys.argv[sys.argv.index("--minute")+1]) if "--minute" in sys.argv else 45
    else:
        print("Falta --match ID o --score H A --minute M"); sys.exit(1)
    r = live_probs(conn, a, b, sh, sa, minute)
    print(f"EN VIVO {r['a']} {r['score']} {r['b']}  (min {r['minute']})")
    print(f"  Resultado 90': {r['a']} {r['ph']*100:.0f}% / empate {r['pd']*100:.0f}% / {r['b']} {r['pa']*100:.0f}%")
    print(f"  AVANCE (empate→tanda 50/50): {r['a']} {r['adv_a']*100:.0f}%  |  {r['b']} {r['adv_b']*100:.0f}%")
    conn.close()
