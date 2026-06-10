#!/usr/bin/env python3
"""
sync_wc_group_draw.py — Deriva wc_group_draw del calendario REAL.

models/tournament.py necesita la tabla wc_group_draw (team_id, grp, pot), que
no existía en esta DB. A diferencia de seed_wc_groups.py (sorteo SINTÉTICO
aleatorio, anterior al sorteo oficial), este script deriva los grupos del
calendario real ya cargado en wc_matches (stage='group') y asigna el bombo
por ranking Elo dentro de los 48 (12 por bombo), solo como dato informativo.

Uso:
    python3 scripts/sync_wc_group_draw.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT home_team_id AS tid, wc_group AS grp FROM wc_matches WHERE stage='group'
        UNION
        SELECT away_team_id, wc_group FROM wc_matches WHERE stage='group'
    """).fetchall()

    draw: dict[int, str] = {}
    for r in rows:
        if r["tid"] in draw and draw[r["tid"]] != r["grp"]:
            raise SystemExit(f"❌ team_id {r['tid']} aparece en dos grupos: {draw[r['tid']]} y {r['grp']}")
        draw[r["tid"]] = r["grp"]

    if len(draw) != 48:
        raise SystemExit(f"❌ {len(draw)} equipos en fixtures de grupos, esperaba 48")
    from collections import Counter
    sizes = Counter(draw.values())
    if sorted(sizes.values()) != [4] * 12:
        raise SystemExit(f"❌ Grupos sin 4 equipos: {dict(sizes)}")

    # Bombos informativos por Elo (12 por bombo)
    elos = {r["team_id"]: r["elo"] for r in conn.execute("SELECT team_id, elo FROM team_elo")}
    ranked = sorted(draw, key=lambda t: -(elos.get(t) or 1500.0))
    pot = {tid: i // 12 + 1 for i, tid in enumerate(ranked)}

    conn.execute("""CREATE TABLE IF NOT EXISTS wc_group_draw (
        team_id INTEGER PRIMARY KEY,
        grp TEXT NOT NULL,
        pot INTEGER
    )""")
    conn.execute("DELETE FROM wc_group_draw")
    conn.executemany("INSERT INTO wc_group_draw (team_id, grp, pot) VALUES (?,?,?)",
                     [(tid, grp, pot[tid]) for tid, grp in draw.items()])
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM wc_group_draw").fetchone()[0]
    print(f"✅ wc_group_draw sincronizada con el calendario real: {n} equipos, 12 grupos de 4")
    for grp in "ABCDEFGHIJKL":
        names = [r[0] for r in conn.execute("""
            SELECT t.name FROM wc_group_draw d JOIN teams t ON t.id = d.team_id
            WHERE d.grp=? ORDER BY t.name""", (grp,))]
        print(f"   {grp}: {', '.join(names)}")


if __name__ == "__main__":
    main()
