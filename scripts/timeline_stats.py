"""
timeline_stats.py — Proceso minuto a minuto desde fifa_match_events (play-by-play FIFA).

Lo que añade sobre match_team_stats: el MINUTO de cada remate y cada parada (no solo
de los goles, que son escasos). Permite un 'choque de ventanas' de OCASIONES (denso),
y una medida de portería sin xG (paradas = Goal Prevention).

Convención de atribución (verificada): un evento Goal Prevention (Type 57) con team=X
es una PARADA del portero de X => un remate A PUERTA del rival de X. Por eso:
  remates_a_puerta_a_favor(T) = paradas_del_rival + goles_de_T

Uso:
    from timeline_stats import team_timeline
    python scripts/timeline_stats.py "Brazil"
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

BUCKETS = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90), (91, 130)]
BUCKET_LBL = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90", "90+"]


def _bucket(m):
    if m is None:
        return None
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= m <= hi:
            return i
    return None


def _tid(conn, team):
    r = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
    return r[0] if r else None


def team_timeline(conn, team):
    """Promedios por partido del Mundial + distribución de remates por franja.
    Devuelve None si el equipo no tiene eventos."""
    tid = _tid(conn, team)
    if tid is None:
        return None
    # partidos del equipo en fifa_match_events
    mids = [r[0] for r in conn.execute(
        "SELECT DISTINCT fifa_match_id FROM fifa_match_events WHERE db_team_id=?", (tid,))]
    if not mids:
        return None
    n = len(mids)
    qmarks = ",".join("?" * len(mids))

    def cnt(where, params):
        return conn.execute(
            f"SELECT COUNT(*) FROM fifa_match_events WHERE fifa_match_id IN ({qmarks}) {where}",
            (*mids, *params)).fetchone()[0]

    shots_for = cnt("AND type_code=12 AND db_team_id=?", (tid,))
    shots_against = cnt("AND type_code=12 AND db_team_id IS NOT NULL AND db_team_id!=?", (tid,))
    saves_made = cnt("AND type_code=57 AND db_team_id=?", (tid,))       # paradas del portero propio
    saves_opp = cnt("AND type_code=57 AND db_team_id IS NOT NULL AND db_team_id!=?", (tid,))  # rival paró => SOT propio
    goals_for = cnt("AND type_code IN (0,41) AND db_team_id=?", (tid,))
    corners_for = cnt("AND type_code=16 AND db_team_id=?", (tid,))
    corners_against = cnt("AND type_code=16 AND db_team_id IS NOT NULL AND db_team_id!=?", (tid,))
    fouls_for = cnt("AND type_code=18 AND db_team_id=?", (tid,))
    offside_for = cnt("AND type_code=15 AND db_team_id=?", (tid,))

    sot_for = saves_opp + goals_for                 # remates a puerta a favor
    sot_against = saves_made + cnt("AND type_code IN (0,41) AND db_team_id IS NOT NULL AND db_team_id!=?", (tid,))

    # distribución de remates por franja (a favor y en contra)
    shot_for_b = [0] * 7
    shot_ag_b = [0] * 7
    for mn, dbt in conn.execute(
            f"SELECT minute_num, db_team_id FROM fifa_match_events "
            f"WHERE fifa_match_id IN ({qmarks}) AND type_code=12", mids):
        b = _bucket(mn)
        if b is None or dbt is None:
            continue
        if dbt == tid:
            shot_for_b[b] += 1
        else:
            shot_ag_b[b] += 1

    return {
        "team": team, "n": n,
        "shots_for": shots_for / n, "shots_against": shots_against / n,
        "sot_for": sot_for / n, "sot_against": sot_against / n,
        "saves_made": saves_made / n,
        "goals_for": goals_for / n,
        "corners_for": corners_for / n, "corners_against": corners_against / n,
        "fouls_for": fouls_for / n, "offside_for": offside_for / n,
        "shot_acc": (sot_for / shots_for) if shots_for else 0,
        "shot_for_b": shot_for_b, "shot_ag_b": shot_ag_b,
        # franja pico (donde más remata) y franja-colador (donde más le rematan)
        "peak_attack": BUCKET_LBL[shot_for_b.index(max(shot_for_b))] if any(shot_for_b) else "-",
        "peak_concede": BUCKET_LBL[shot_ag_b.index(max(shot_ag_b))] if any(shot_ag_b) else "-",
    }


def _fmt_dist(b):
    tot = sum(b) or 1
    return " ".join(f"{BUCKET_LBL[i]}:{b[i]}" for i in range(7))


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    t = team_timeline(conn, sys.argv[1])
    if not t:
        print("sin datos de timeline para", sys.argv[1]); sys.exit(0)
    print(f"=== {t['team']} (play-by-play FIFA, {t['n']} partidos WC) ===")
    print(f"  Remates a favor {t['shots_for']:.1f}/p (a puerta {t['sot_for']:.1f}, precisión {t['shot_acc']*100:.0f}%) "
          f"· goles {t['goals_for']:.2f}/p")
    print(f"  Remates en contra {t['shots_against']:.1f}/p (a puerta {t['sot_against']:.1f}) · paradas portero {t['saves_made']:.1f}/p")
    print(f"  Córners {t['corners_for']:.1f} (concede {t['corners_against']:.1f}) · faltas {t['fouls_for']:.1f} · fuera de juego {t['offside_for']:.1f}")
    print(f"  Remates A FAVOR por franja:   {_fmt_dist(t['shot_for_b'])}   -> pico {t['peak_attack']}")
    print(f"  Remates EN CONTRA por franja: {_fmt_dist(t['shot_ag_b'])}   -> colador {t['peak_concede']}")
    conn.close()
