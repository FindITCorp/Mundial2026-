"""
rebuild_wc_timing.py — Calcula el goal-timing REAL del Mundial 2026 por equipo
desde fifa_match_goals (161 goles con minuto) y lo guarda en wc_goal_timing.

Complementa team_goal_timing (que es histórico 2018+): esta tabla es SOLO de este
torneo, así que captura la forma actual (quién marca/concede temprano o tarde HOY).
El análisis prioriza WC-timing cuando hay >=2 partidos.

Uso: python scripts/rebuild_wc_timing.py
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "mundial2026.db"
LABELS = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90"]


def _win(m):
    return min(5, (m - 1) // 15) if m and m > 0 else 0


def rebuild(db_path=DB, verbose=True):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS wc_goal_timing (
        team_id INTEGER PRIMARY KEY, matches INTEGER,
        s0 INTEGER, s1 INTEGER, s2 INTEGER, s3 INTEGER, s4 INTEGER, s5 INTEGER,
        c0 INTEGER, c1 INTEGER, c2 INTEGER, c3 INTEGER, c4 INTEGER, c5 INTEGER)""")
    conn.execute("DELETE FROM wc_goal_timing")

    # partidos jugados por equipo
    teams = {}
    for r in conn.execute("""SELECT home_team_id h, away_team_id a, id FROM wc_matches
                             WHERE stage IN ('group','R32') AND played=1"""):
        teams.setdefault(r["h"], set()).add(r["id"])
        teams.setdefault(r["a"], set()).add(r["id"])

    for tid, mids in teams.items():
        scored = [0] * 6
        conceded = [0] * 6
        for g in conn.execute("""SELECT g.team_id, g.minute, g.match_id FROM fifa_match_goals g
                                 WHERE g.match_id IN (%s)""" % ",".join("?" * len(mids)),
                              tuple(mids)):
            w = _win(g["minute"])
            if g["team_id"] == tid:
                scored[w] += 1
            else:
                conceded[w] += 1
        conn.execute(
            "INSERT INTO wc_goal_timing (team_id,matches,s0,s1,s2,s3,s4,s5,c0,c1,c2,c3,c4,c5) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, len(mids), *scored, *conceded))
    conn.commit()

    if verbose:
        n = conn.execute("SELECT COUNT(*) FROM wc_goal_timing").fetchone()[0]
        print(f"wc_goal_timing reconstruida: {n} equipos")
    conn.close()


def patterns(team_id, db_path=DB):
    """Devuelve patrones de timing del equipo en este Mundial."""
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM wc_goal_timing WHERE team_id=?", (team_id,)).fetchone()
    conn.close()
    if not r:
        return None
    s = [r[f"s{i}"] for i in range(6)]
    c = [r[f"c{i}"] for i in range(6)]
    out = {"matches": r["matches"], "scored": s, "conceded": c,
           "gf": sum(s), "ga": sum(c), "flags": []}
    if sum(s):
        out["peak_scored"] = LABELS[s.index(max(s))]
        if (s[3] + s[4] + s[5]) > (s[0] + s[1] + s[2]):
            out["flags"].append("marca más en 2ª mitad")
        if s[5] >= max(2, 0.35 * sum(s)):
            out["flags"].append(f"LETAL TARDE ({s[5]} goles en 76-90)")
    if sum(c):
        out["peak_conceded"] = LABELS[c.index(max(c))]
        if c[5] >= max(2, 0.35 * sum(c)):
            out["flags"].append(f"FILTRA TARDE ({c[5]} en 76-90)")
        if (c[0] + c[1]) >= max(2, 0.4 * sum(c)):
            out["flags"].append("VULNERABLE TEMPRANO (concede en 1-30)")
    return out


if __name__ == "__main__":
    rebuild()
