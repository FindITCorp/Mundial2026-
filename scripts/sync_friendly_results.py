#!/usr/bin/env python3
"""
sync_friendly_results.py — Cierra el eslabón faltante del ciclo de calibración.

Problema: los workflows de fetch escriben resultados en team_matches, pero
evaluate_model.py lee wc_matches (score_home/score_away). Los amistosos
quedaban sin evaluar porque nadie copiaba el resultado de una tabla a la otra.

Qué hace:
1. --sync (default): para cada wc_matches sin resultado y fecha <= hoy, busca
   el resultado en team_matches (±1 día, ambas perspectivas) y lo copia.
2. --set MATCH_ID H-A: carga un resultado manual (cuando el usuario lo pega),
   actualiza wc_matches Y team_matches (ambas perspectivas) para que el
   factor de forma también lo vea.

Tras sincronizar, correr: python3 scripts/evaluate_model.py
"""
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def sync(conn) -> int:
    today = date.today().isoformat()
    pending = conn.execute("""
        SELECT id, date, home_team_id, away_team_id, home_team_name, away_team_name
        FROM wc_matches
        WHERE (score_home IS NULL OR played = 0) AND date <= ?
    """, (today,)).fetchall()

    updated = 0
    for mid, mdate, h_id, a_id, h_name, a_name in pending:
        row = conn.execute("""
            SELECT goals_for, goals_against FROM team_matches
            WHERE team_id=? AND opponent_id=?
              AND abs(julianday(date) - julianday(?)) <= 1
            ORDER BY abs(julianday(date) - julianday(?)) LIMIT 1
        """, (h_id, a_id, mdate, mdate)).fetchone()
        if row is None:
            rev = conn.execute("""
                SELECT goals_against, goals_for FROM team_matches
                WHERE team_id=? AND opponent_id=?
                  AND abs(julianday(date) - julianday(?)) <= 1
                ORDER BY abs(julianday(date) - julianday(?)) LIMIT 1
            """, (a_id, h_id, mdate, mdate)).fetchone()
            row = rev
        if row is None:
            continue
        gh, ga = int(row[0]), int(row[1])
        conn.execute("UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
                     (gh, ga, mid))
        print(f"  ✅ {h_name} {gh}-{ga} {a_name} ({mdate}) ← team_matches")
        updated += 1
    return updated


def set_manual(conn, match_id: int, score: str) -> None:
    gh, ga = (int(x) for x in score.split("-"))
    m = conn.execute("""
        SELECT date, home_team_id, away_team_id, home_team_name, away_team_name
        FROM wc_matches WHERE id=?
    """, (match_id,)).fetchone()
    if m is None:
        raise SystemExit(f"❌ match_id {match_id} no existe en wc_matches")
    mdate, h_id, a_id, h_name, a_name = m

    conn.execute("UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
                 (gh, ga, match_id))

    # Propagar a team_matches (ambas perspectivas) para que forma/xG lo vean.
    def _res(gf, gc): return "W" if gf > gc else ("L" if gf < gc else "D")
    for tid, oid, oname, gf, gc in [(h_id, a_id, a_name, gh, ga), (a_id, h_id, h_name, ga, gh)]:
        exists = conn.execute("""
            SELECT 1 FROM team_matches
            WHERE team_id=? AND opponent_id=? AND abs(julianday(date)-julianday(?)) <= 1
        """, (tid, oid, mdate)).fetchone()
        if not exists:
            conn.execute("""
                INSERT INTO team_matches (team_id, opponent_id, opponent_name, date,
                                          competition, goals_for, goals_against, result, venue)
                VALUES (?,?,?,?,'Friendly',?,?,?,'neutral')
            """, (tid, oid, oname, mdate, gf, gc, _res(gf, gc)))
    print(f"  ✅ Manual: {h_name} {gh}-{ga} {a_name} → wc_matches + team_matches")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", nargs=2, metavar=("MATCH_ID", "H-A"),
                    help="Cargar resultado manual: --set 147 2-1")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB))
    if args.set:
        set_manual(conn, int(args.set[0]), args.set[1])
    else:
        n = sync(conn)
        print(f"[sync_friendly_results] {n} resultados sincronizados a wc_matches")
        if n:
            print("→ Ahora correr: python3 scripts/evaluate_model.py")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
