"""
formation_matchup.py — Lectura ESTRATÉGICA por choque de formaciones.

Pedido del dueño 28-jun: ver cómo le fue a cada equipo según la formación que jugó
(p.ej. 4-4-2 vs 5-4-1) para que, al tener las alineaciones reales (que traen la
formación), podamos leer si el cruce táctico anticipa el resultado.

Fuente: formación REAL por partido del crudo de Sofascore (lineups.json → home/away
formation), que es el único sitio con la formación efectivamente desplegada. Persiste
en la tabla match_formations y expone:
  • formation_strength(f)  → récord global de quien usa la formación f
  • matchup(fa, fb)        → récord histórico de fa (local) vs fb

Hallazgo 28-jun (60 partidos): 4-3-3 y 4-4-2 dominan (2.0 pts/p); el bloque bajo
5-4-1 fracasa (0V-3E-7L, 0.20 goles/p) — meterse atrás no gana ni marca. 4-3-3
vence al 5-4-1 (2-0); 4-2-3-1 arrasa al 3-4-2-1 (4-0).

Uso:
    python scripts/formation_matchup.py                 # tabla de récords
    python scripts/formation_matchup.py "4-3-3" "5-4-1" # choque concreto
    python scripts/formation_matchup.py --rebuild       # re-extrae del crudo
"""
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
RAW = BASE_DIR / "data" / "sofascore_raw"


def rebuild(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS match_formations (
        event_id TEXT PRIMARY KEY, home TEXT, home_formation TEXT, home_score INTEGER,
        away_score INTEGER, away TEXT, away_formation TEXT)""")
    conn.execute("DELETE FROM match_formations")
    n = 0
    for d in os.listdir(RAW):
        try:
            ev = json.loads((RAW / d / "event.json").read_text(encoding="utf-8"))
            e = ev.get("event", ev)
            ln = json.loads((RAW / d / "lineups.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        hf = ln.get("home", {}).get("formation")
        af = ln.get("away", {}).get("formation")
        hs = e.get("homeScore", {}).get("current")
        as_ = e.get("awayScore", {}).get("current")
        if not hf or not af or hs is None:
            continue
        conn.execute("INSERT OR REPLACE INTO match_formations VALUES (?,?,?,?,?,?,?)",
                     (d, e["homeTeam"]["name"], hf, hs, as_, e["awayTeam"]["name"], af))
        n += 1
    conn.commit()
    return n


def _rows(conn):
    return conn.execute("SELECT home_formation, home_score, away_score, away_formation "
                        "FROM match_formations").fetchall()


def formation_strength(conn):
    fr = defaultdict(lambda: [0, 0, 0, 0, 0])  # W,D,L,GF,GA
    for hf, hs, as_, af in _rows(conn):
        for f, gf, ga in ((hf, hs, as_), (af, as_, hs)):
            r = fr[f]; r[3] += gf; r[4] += ga
            r[0 if gf > ga else (1 if gf == ga else 2)] += 1
    return fr


def matchup(conn, fa, fb):
    """Récord de fa contra fb (suma ambas orientaciones, perspectiva de fa)."""
    w = d = l = gf = ga = 0
    for hf, hs, as_, af in _rows(conn):
        if hf == fa and af == fb:
            gf += hs; ga += as_; w += hs > as_; d += hs == as_; l += hs < as_
        elif hf == fb and af == fa:
            gf += as_; ga += hs; w += as_ > hs; d += as_ == hs; l += as_ < hs
    n = w + d + l
    return {"n": n, "w": w, "d": d, "l": l, "gf": gf, "ga": ga} if n else None


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if "--rebuild" in sys.argv or not conn.execute(
            "SELECT name FROM sqlite_master WHERE name='match_formations'").fetchone():
        print(f"Reconstruido: {rebuild(conn)} partidos con formación real.")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) >= 2:
        fa, fb = args[0], args[1]
        fr = formation_strength(conn)
        for f in (fa, fb):
            r = fr.get(f)
            if r:
                n = sum(r[:3])
                print(f"{f}: {r[0]}V-{r[1]}E-{r[2]}D · {r[3]/n:.2f} GF/p · {r[4]/n:.2f} GA/p · "
                      f"{(3*r[0]+r[1])/n:.2f} pts/p (n={n})")
        m = matchup(conn, fa, fb)
        if m:
            print(f"\nCHOQUE {fa} vs {fb} (n={m['n']}): {m['w']}V-{m['d']}E-{m['l']}D para {fa}, "
                  f"goles {m['gf']}-{m['ga']}")
        else:
            print(f"\nSin precedentes directos {fa} vs {fb} en el torneo.")
    else:
        fr = formation_strength(conn)
        print(f"{'FORMACIÓN':10} {'V':>3} {'E':>3} {'D':>3} {'GF/p':>6} {'GA/p':>6} {'pts/p':>6}")
        for f, r in sorted(fr.items(), key=lambda x: -(3 * x[1][0] + x[1][1]) / max(sum(x[1][:3]), 1)):
            n = sum(r[:3])
            if n < 2:
                continue
            print(f"{f:10} {r[0]:3} {r[1]:3} {r[2]:3} {r[3]/n:6.2f} {r[4]/n:6.2f} {(3*r[0]+r[1])/n:6.2f}")
    conn.close()
