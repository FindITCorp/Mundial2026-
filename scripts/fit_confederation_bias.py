#!/usr/bin/env python3
"""
fit_confederation_bias.py — Ajuste de Elo por confederación (inter-confed).

Problema detectado (10-jun-2026, fallo Irak 0-2 Venezuela): el Elo se acumula
en pools casi cerrados por confederación. Equipos AFC suman Elo contra rivales
asiáticos débiles; equipos CONMEBOL lo pierden contra la élite sudamericana.
Al cruzarse las confederaciones (TODO el Mundial), el Elo miente:
CONMEBOL rendía +0.097 pts/partido sobre su expectativa Elo (n=165 desde 2023)
→ ~+67 Elo de subvaloración. Irak-Venezuela: gap real ~+62, no +137.

Método:
1. Todos los team_matches inter-confederación desde 2023.
2. delta = (puntos reales - puntos esperados por Elo) / n  por confederación.
3. offset_elo = delta / 0.00144 (pendiente de la curva Elo en p=0.5),
   con shrinkage n/(n+50) y cap ±60. Mínimo 20 partidos, si no → 0.
4. Escribe tabla confed_elo_offset; match_predictor la aplica al Elo efectivo
   SOLO de forma relativa (mismo confed → se cancela solo).

Re-fittear tras cada tanda de partidos del Mundial:
    python3 scripts/fit_confederation_bias.py
"""
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

SINCE = "2023-01-01"
SHRINK_N = 50          # offset * n/(n+SHRINK_N)
CAP = 60.0             # |offset| máximo en puntos Elo
MIN_N = 20             # bajo esto, offset = 0
ELO_SLOPE = 0.00144    # d(prob)/d(elo) en p=0.5: ln(10)/400 * 0.25


def fit(conn) -> dict[str, tuple[float, int]]:
    elo = {r[0]: r[1] for r in conn.execute("SELECT team_id, elo FROM team_elo")}
    confed = {r[0]: r[1] for r in conn.execute("SELECT id, confederation FROM teams")}

    agg = defaultdict(lambda: [0.0, 0.0, 0])   # confed → [real, esperado, n]
    rows = conn.execute("""
        SELECT team_id, opponent_id, goals_for, goals_against
        FROM team_matches WHERE date >= ? AND opponent_id IS NOT NULL
    """, (SINCE,)).fetchall()
    for tid, oid, gf, ga in rows:
        c1, c2 = confed.get(tid), confed.get(oid)
        if not c1 or not c2 or c1 == c2 or c1 == "UNK" or c2 == "UNK":
            continue
        e1, e2 = elo.get(tid), elo.get(oid)
        if e1 is None or e2 is None:
            continue
        exp = 1.0 / (1.0 + 10 ** (-(e1 - e2) / 400.0))
        act = 1.0 if gf > ga else (0.5 if gf == ga else 0.0)
        agg[c1][0] += act
        agg[c1][1] += exp
        agg[c1][2] += 1

    out = {}
    for c, (act, exp, n) in agg.items():
        if n < MIN_N:
            out[c] = (0.0, n)
            continue
        delta = (act - exp) / n
        off = delta / ELO_SLOPE * (n / (n + SHRINK_N))
        off = max(-CAP, min(CAP, off))
        out[c] = (round(off, 1), n)
    return out


def main() -> None:
    conn = sqlite3.connect(str(DB))
    offsets = fit(conn)

    conn.execute("""CREATE TABLE IF NOT EXISTS confed_elo_offset (
        confederation TEXT PRIMARY KEY,
        offset REAL NOT NULL,
        n INTEGER NOT NULL,
        fitted_at TEXT NOT NULL
    )""")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    conn.execute("DELETE FROM confed_elo_offset")
    conn.executemany(
        "INSERT INTO confed_elo_offset (confederation, offset, n, fitted_at) VALUES (?,?,?,?)",
        [(c, off, n, now) for c, (off, n) in offsets.items()])
    conn.commit()

    print(f"✅ confed_elo_offset actualizada ({now} UTC, partidos desde {SINCE}):")
    for c, (off, n) in sorted(offsets.items(), key=lambda x: -x[1][0]):
        print(f"   {c:10s} {off:+6.1f} Elo  (n={n})")
    conn.close()


if __name__ == "__main__":
    main()
