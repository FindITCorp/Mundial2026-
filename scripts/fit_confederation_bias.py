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

# Nivel equipo (11-jun-2026): el offset de pool castiga al mejor equipo del
# pool por los pecados del resto (México pagaba la tarifa CONCACAF -29 con
# récord inter-confed de élite: 5-1 Serbia, 1-1 Bélgica, 0-0 Portugal).
# Blend: w = n_team/(n_team+TEAM_K) → con muestra propia domina su señal;
# con poca muestra hereda el offset de su confederación.
TEAM_K = 30
TEAM_CAP = 75.0
TEAM_MIN_N = 5         # bajo esto, hereda 100% el offset de confederación


def fit(conn):
    elo = {r[0]: r[1] for r in conn.execute("SELECT team_id, elo FROM team_elo")}
    confed = {r[0]: r[1] for r in conn.execute("SELECT id, confederation FROM teams")}

    agg = defaultdict(lambda: [0.0, 0.0, 0])   # confed → [real, esperado, n]
    inter = []                                  # (team_id, act, exp) inter-confed
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
        inter.append((tid, act, exp))

    out = {}
    for c, (act, exp, n) in agg.items():
        if n < MIN_N:
            out[c] = (0.0, n)
            continue
        delta = (act - exp) / n
        off = delta / ELO_SLOPE * (n / (n + SHRINK_N))
        off = max(-CAP, min(CAP, off))
        out[c] = (round(off, 1), n)
    return out, inter, confed


def fit_teams(inter, confed, confed_offsets) -> dict[int, tuple[float, int]]:
    """Offset por equipo: blend señal propia ↔ offset de su confederación."""
    agg = defaultdict(lambda: [0.0, 0.0, 0])   # team_id → [real, esperado, n]
    for tid, act, exp in inter:
        agg[tid][0] += act
        agg[tid][1] += exp
        agg[tid][2] += 1

    out = {}
    for tid, (act, exp, n) in agg.items():
        c_off = confed_offsets.get(confed.get(tid), (0.0, 0))[0]
        if n < TEAM_MIN_N:
            out[tid] = (round(c_off, 1), n)
            continue
        delta = (act - exp) / n
        raw = delta / ELO_SLOPE
        w = n / (n + TEAM_K)
        off = w * raw + (1 - w) * c_off
        off = max(-TEAM_CAP, min(TEAM_CAP, off))
        out[tid] = (round(off, 1), n)
    return out


def main() -> None:
    conn = sqlite3.connect(str(DB))
    offsets, inter, confed = fit(conn)
    team_offsets = fit_teams(inter, confed, offsets)

    conn.execute("""CREATE TABLE IF NOT EXISTS confed_elo_offset (
        confederation TEXT PRIMARY KEY,
        offset REAL NOT NULL,
        n INTEGER NOT NULL,
        fitted_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS team_elo_offset (
        team_id INTEGER PRIMARY KEY,
        offset REAL NOT NULL,
        n INTEGER NOT NULL,
        fitted_at TEXT NOT NULL
    )""")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    conn.execute("DELETE FROM confed_elo_offset")
    conn.executemany(
        "INSERT INTO confed_elo_offset (confederation, offset, n, fitted_at) VALUES (?,?,?,?)",
        [(c, off, n, now) for c, (off, n) in offsets.items()])
    conn.execute("DELETE FROM team_elo_offset")
    conn.executemany(
        "INSERT INTO team_elo_offset (team_id, offset, n, fitted_at) VALUES (?,?,?,?)",
        [(t, off, n, now) for t, (off, n) in team_offsets.items()])
    conn.commit()

    print(f"✅ confed_elo_offset actualizada ({now} UTC, partidos desde {SINCE}):")
    for c, (off, n) in sorted(offsets.items(), key=lambda x: -x[1][0]):
        print(f"   {c:10s} {off:+6.1f} Elo  (n={n})")

    print(f"✅ team_elo_offset: {len(team_offsets)} equipos. Muestra (WC relevantes):")
    sample = conn.execute("""
        SELECT t.name, o.offset, o.n FROM team_elo_offset o
        JOIN teams t ON t.id = o.team_id
        WHERE t.name IN ('Mexico','USA','Canada','Venezuela','Iraq','Morocco',
                         'Brazil','Argentina','South Africa','South Korea','Japan')
        ORDER BY o.offset DESC
    """).fetchall()
    for name, off, n in sample:
        print(f"   {name:14s} {off:+6.1f} Elo  (n={n})")
    conn.close()


if __name__ == "__main__":
    main()
