"""
Refresca teams.possession_avg / goals_scored_avg / goals_conceded_avg
a partir de match_team_stats (stats reales de Sofascore).
Blend: más partidos disponibles → más peso a datos reales.
"""
import sqlite3, sys
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"

def refresh(db_path=DB):
    conn = sqlite3.connect(db_path)
    updated = []
    for (tid,) in conn.execute("SELECT DISTINCT team_id FROM match_team_stats").fetchall():
        rows = conn.execute("""
            SELECT mts.possession, mts.xg, wm.score_home, wm.score_away, mts.is_home
            FROM match_team_stats mts
            JOIN wc_matches wm ON wm.id = mts.match_id
            WHERE mts.team_id = ?
            ORDER BY wm.date DESC LIMIT 10
        """, (tid,)).fetchall()
        if not rows:
            continue
        avg_poss = sum(r[0] for r in rows if r[0]) / len(rows)
        goals_for, goals_ag = [], []
        for _, _, sh, sa, is_home in rows:
            goals_for.append((sh if is_home else sa) or 0)
            goals_ag.append((sa if is_home else sh) or 0)
        avg_gf = sum(goals_for) / len(goals_for)
        avg_ga = sum(goals_ag)  / len(goals_ag)
        ex = conn.execute("SELECT possession_avg, goals_scored_avg, goals_conceded_avg FROM teams WHERE id=?", (tid,)).fetchone()
        if not ex:
            continue
        ex_poss, ex_gf, ex_ga = ex
        n = len(rows)
        w = min(0.30 + n * 0.07, 0.85)
        conn.execute("UPDATE teams SET possession_avg=?, goals_scored_avg=?, goals_conceded_avg=? WHERE id=?", (
            round(w * avg_poss + (1-w) * (ex_poss or 50.0), 1),
            round(w * avg_gf   + (1-w) * (ex_gf or 1.5),   2),
            round(w * avg_ga   + (1-w) * (ex_ga or 1.2),   2),
            tid,
        ))
        name = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()[0]
        updated.append(name)
    conn.commit()
    conn.close()
    print(f"[refresh_team_avgs] {len(updated)} equipos actualizados: {', '.join(updated)}")
    return updated

if __name__ == "__main__":
    refresh()
