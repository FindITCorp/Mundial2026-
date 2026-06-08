"""
auto_calibrate_wc.py — Calibración automática post-partido del Mundial.

Ejecutar después de guardar cada resultado WC en wc_matches:
    python3 scripts/auto_calibrate_wc.py

Hace tres cosas:
1. Actualiza goals_scored_avg / goals_conceded_avg con resultados WC (peso 1.6x)
2. Recalcula Elo dinámico post-partido (K=32 para WC)
3. Ajusta possession_avg con datos de match_team_stats WC

Diseño: blend progresivo — cuantos más partidos WC hay, más pesan.
"""

import sqlite3
import math
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

WC_GOAL_WEIGHT = 2.0    # cada partido WC cuenta como 2.0 partidos históricos
WC_ELO_K      = 32      # K de Elo para WC (mayor que amistosos = 24, menor que WCF = 40)
WC_ELO_K_QF   = 40      # K mayor para cuartos en adelante
ELO_BASE      = 1500.0


def _expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _result_score(gf: int, ga: int) -> float:
    if gf > ga: return 1.0
    if gf == ga: return 0.5
    return 0.0


def calibrate_team_goals(conn, team_id: int, n_wc_matches: int):
    """Actualiza goals_scored_avg y goals_conceded_avg con los partidos WC."""
    # Promedio histórico actual
    row = conn.execute(
        "SELECT goals_scored_avg, goals_conceded_avg FROM teams WHERE id=?", (team_id,)
    ).fetchone()
    if not row:
        return
    hist_gf, hist_ga = row[0] or 1.2, row[1] or 1.2

    # Resultados WC ya jugados
    wc_rows = conn.execute("""
        SELECT w.score_home, w.score_away, w.home_team_id, w.away_team_id
        FROM wc_matches w
        WHERE (w.home_team_id=? OR w.away_team_id=?) 
          AND w.played=1 AND w.stage NOT LIKE '%Friendly%'
          AND w.id < 105
    """, (team_id, team_id)).fetchall()

    if not wc_rows:
        return

    wc_gf_list, wc_ga_list = [], []
    for sh, sa, htid, atid in wc_rows:
        if htid == team_id:
            wc_gf_list.append(sh); wc_ga_list.append(sa)
        else:
            wc_gf_list.append(sa); wc_ga_list.append(sh)

    n_wc = len(wc_gf_list)
    wc_gf = sum(wc_gf_list) / n_wc
    wc_ga = sum(wc_ga_list) / n_wc

    # Peso progresivo: empieza en 30% WC, sube 15% por partido adicional, máx 80%
    wc_weight = min(0.80, 0.30 + (n_wc - 1) * 0.15)
    hist_weight = 1.0 - wc_weight

    new_gf = hist_weight * hist_gf + wc_weight * wc_gf
    new_ga = hist_weight * hist_ga + wc_weight * wc_ga

    conn.execute(
        "UPDATE teams SET goals_scored_avg=?, goals_conceded_avg=? WHERE id=?",
        (round(new_gf, 3), round(new_ga, 3), team_id)
    )


def update_elo_after_match(conn, match_id: int):
    """Recalcula Elo para los dos equipos tras un partido WC."""
    row = conn.execute("""
        SELECT home_team_id, away_team_id, score_home, score_away, stage
        FROM wc_matches WHERE id=? AND played=1
    """, (match_id,)).fetchone()
    if not row:
        return

    htid, atid, sh, sa, stage = row
    stage = (stage or "").lower()

    # K factor según ronda
    K = WC_ELO_K_QF if any(x in stage for x in ("quarter","semi","final","round of 16")) else WC_ELO_K

    # Elo actual
    def get_elo(tid):
        r = conn.execute("SELECT elo FROM team_elo WHERE team_id=?", (tid,)).fetchone()
        return r[0] if r else ELO_BASE

    ra = get_elo(htid)
    rb = get_elo(atid)

    ea = _expected(ra, rb)
    sa_score = _result_score(sh, sa)
    sb_score = 1.0 - sa_score

    new_ra = ra + K * (sa_score - ea)
    new_rb = rb + K * (sb_score - (1.0 - ea))

    for tid, new_elo in [(htid, new_ra), (atid, new_rb)]:
        existing = conn.execute("SELECT 1 FROM team_elo WHERE team_id=?", (tid,)).fetchone()
        if existing:
            conn.execute("UPDATE team_elo SET elo=? WHERE team_id=?", (round(new_elo, 1), tid))
        else:
            conn.execute("INSERT INTO team_elo (team_id, elo) VALUES (?,?)", (tid, round(new_elo, 1)))

    conn.commit()
    print(f"  Elo: team {htid}: {ra:.0f}→{new_ra:.0f} | team {atid}: {rb:.0f}→{new_rb:.0f}")


def update_possession_from_stats(conn, team_id: int):
    """Actualiza possession_avg con datos reales de match_team_stats WC."""
    rows = conn.execute("""
        SELECT mts.possession FROM match_team_stats mts
        JOIN wc_matches w ON w.id = mts.match_id
        WHERE mts.team_id=? AND w.played=1 
          AND w.stage NOT LIKE '%Friendly%' AND w.id < 105
        ORDER BY w.date DESC LIMIT 5
    """, (team_id,)).fetchall()

    if not rows:
        return
    wc_poss = sum(r[0] for r in rows) / len(rows)

    cur = conn.execute("SELECT possession_avg FROM teams WHERE id=?", (team_id,)).fetchone()
    if not cur:
        return
    hist_poss = cur[0] or 50.0

    # Blend: 40% WC, 60% histórico (posesión es más estable)
    new_poss = 0.60 * hist_poss + 0.40 * wc_poss
    conn.execute("UPDATE teams SET possession_avg=? WHERE id=?",
                 (round(new_poss, 1), team_id))


def run_full_calibration(db_path=DB_PATH, verbose=True):
    """Calibración completa: todos los equipos con partidos WC jugados."""
    conn = sqlite3.connect(db_path)

    # Equipos que ya tienen resultado WC real (no amistosos)
    played_teams = conn.execute("""
        SELECT DISTINCT team_id FROM (
            SELECT home_team_id AS team_id FROM wc_matches 
            WHERE played=1 AND stage NOT LIKE '%Friendly%' AND id < 105
            UNION
            SELECT away_team_id FROM wc_matches 
            WHERE played=1 AND stage NOT LIKE '%Friendly%' AND id < 105
        )
    """).fetchall()

    if not played_teams:
        if verbose:
            print("Sin partidos WC reales todavía. Ejecutar cuando empiece el torneo (11 jun).")
        conn.close()
        return

    for (tid,) in played_teams:
        n_matches = conn.execute("""
            SELECT COUNT(*) FROM wc_matches 
            WHERE (home_team_id=? OR away_team_id=?) AND played=1 
              AND stage NOT LIKE '%Friendly%' AND id < 105
        """, (tid, tid)).fetchone()[0]
        calibrate_team_goals(conn, tid, n_matches)
        update_possession_from_stats(conn, tid)

    # Elo: recalcular para partidos WC que no hayan sido procesados aún
    played_matches = conn.execute("""
        SELECT id FROM wc_matches 
        WHERE played=1 AND stage NOT LIKE '%Friendly%' AND id < 105
        ORDER BY date
    """).fetchall()
    for (mid,) in played_matches:
        if verbose:
            print(f"Actualizando Elo match {mid}...")
        update_elo_after_match(conn, mid)

    conn.commit()
    conn.close()
    if verbose:
        print("Calibración WC completada.")


if __name__ == "__main__":
    run_full_calibration()
