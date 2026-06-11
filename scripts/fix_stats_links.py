#!/usr/bin/env python3
"""
fix_stats_links.py — Re-enlaza estadísticas huérfanas al espacio de ids correcto.

Bug encontrado (11-jun-2026, reclamo del usuario "cargué México-Paraguay y no
aparece del lado de Paraguay"): un loader antiguo guardó match_team_stats con
match_id apuntando a TEAM_MATCHES.id, pero el modelo (xG factor, perfiles) lee
vía WC_MATCHES.id. Dos espacios de ids en la misma columna → 52 match_ids
huérfanos invisibles para el modelo (USA vs Portugal xG 1.66, SK vs Paraguay,
México vs Paraguay completos...).

Qué hace (idempotente):
1. match_team_stats huérfanos resolubles: localiza el fixture en team_matches
   por id, busca/crea la fila wc_matches y re-apunta match_id.
2. Huérfanos de 2 filas sin team_matches: resuelve por el par de equipos
   (fecha más cercana en team_matches entre ambos).
3. Huérfanos restantes: si duplican (team, xg, possession) de una fila ya
   enlazada → se borran; si no, se reportan (no se borra data única).
4. match_player_stats: para cada fixture (fecha, local, visita) sin wc_matches,
   lo crea desde el resultado de team_matches. Fixtures duplicados ±1 día con
   los mismos jugadores → conserva la fecha canónica de team_matches.

Uso:  python3 scripts/fix_stats_links.py [--dry-run]
"""
import argparse
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def _find_or_create_wc(conn, t1, t2, date, gf_t1=None, ga_t1=None, home_id=None,
                       stage="Friendly", apply=True):
    """Busca wc_matches por par±1 día (cualquier orientación); crea si falta."""
    row = conn.execute("""
        SELECT id FROM wc_matches
        WHERE abs(julianday(date) - julianday(?)) <= 1
          AND ((home_team_id=? AND away_team_id=?) OR (home_team_id=? AND away_team_id=?))
    """, (date, t1, t2, t2, t1)).fetchone()
    if row:
        return row[0], False
    if not apply:
        return None, True
    h = home_id if home_id is not None else t1
    a = t2 if h == t1 else t1
    hn = conn.execute("SELECT name FROM teams WHERE id=?", (h,)).fetchone()
    an = conn.execute("SELECT name FROM teams WHERE id=?", (a,)).fetchone()
    if not hn or not an:
        return None, False
    sh = sa = None
    if gf_t1 is not None:
        sh, sa = (gf_t1, ga_t1) if h == t1 else (ga_t1, gf_t1)
    cur = conn.execute("""
        INSERT INTO wc_matches (date, home_team_id, away_team_id, home_team_name,
                                away_team_name, stage, score_home, score_away, played)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (date, h, a, hn[0], an[0], stage,
          sh, sa, 1 if sh is not None else 0))
    return cur.lastrowid, True


def fix_team_stats(conn, apply: bool) -> tuple[int, int, int]:
    orphans = conn.execute("""
        SELECT DISTINCT mts.match_id FROM match_team_stats mts
        LEFT JOIN wc_matches wm ON wm.id = mts.match_id
        WHERE wm.id IS NULL
    """).fetchall()
    remapped = deleted = left = 0
    for (oid,) in orphans:
        rows = conn.execute(
            "SELECT id, team_id, xg, possession FROM match_team_stats WHERE match_id=?",
            (oid,)).fetchall()
        tm = conn.execute("""
            SELECT team_id, opponent_id, date, goals_for, goals_against, venue, competition
            FROM team_matches WHERE id=?
        """, (oid,)).fetchone()
        wc_id = None
        if tm and tm[1] is not None:
            t1, t2, d, gf, ga, venue, comp = tm
            home = t1 if (venue or "home") != "away" else t2
            stage = "Friendly" if "riendly" in (comp or "Friendly") else "WC Qualifier"
            wc_id, _ = _find_or_create_wc(conn, t1, t2, d, gf, ga, home, stage, apply)
        elif len(rows) == 2:
            # par de equipos conocido → fixture más cercano en team_matches
            ta, tb = rows[0][1], rows[1][1]
            cand = conn.execute("""
                SELECT team_id, opponent_id, date, goals_for, goals_against, venue
                FROM team_matches WHERE team_id=? AND opponent_id=?
                ORDER BY date DESC LIMIT 1
            """, (ta, tb)).fetchone()
            if cand:
                t1, t2, d, gf, ga, venue = cand
                home = t1 if (venue or "home") != "away" else t2
                wc_id, _ = _find_or_create_wc(conn, t1, t2, d, gf, ga, home, apply=apply)
        if wc_id:
            if apply:
                # merge por fila: puede existir ya una fila (wc_id, team) cargada
                # manualmente — conservar la más completa (más campos no nulos)
                def _nn(row_id):
                    r = conn.execute("SELECT * FROM match_team_stats WHERE id=?",
                                     (row_id,)).fetchone()
                    return sum(1 for v in r if v is not None)
                for rid, tid, _, _ in rows:
                    clash = conn.execute("""SELECT id FROM match_team_stats
                        WHERE match_id=? AND team_id=?""", (wc_id, tid)).fetchone()
                    if clash:
                        if _nn(rid) > _nn(clash[0]):
                            conn.execute("DELETE FROM match_team_stats WHERE id=?",
                                         (clash[0],))
                            conn.execute("UPDATE match_team_stats SET match_id=? WHERE id=?",
                                         (wc_id, rid))
                        else:
                            conn.execute("DELETE FROM match_team_stats WHERE id=?", (rid,))
                    else:
                        conn.execute("UPDATE match_team_stats SET match_id=? WHERE id=?",
                                     (wc_id, rid))
            print(f"  ↪ remap match_id {oid} → wc {wc_id}")
            remapped += 1
            continue
        # sin fixture: ¿duplica una fila ya enlazada? (mismo team+xg+poss)
        all_dup = True
        for rid, tid, xg, poss in rows:
            dup = conn.execute("""
                SELECT 1 FROM match_team_stats m2
                JOIN wc_matches wm ON wm.id = m2.match_id
                WHERE m2.team_id=? AND m2.id != ?
                  AND ifnull(m2.xg,-1)=ifnull(?,-1)
                  AND ifnull(m2.possession,-1)=ifnull(?,-1)
            """, (tid, rid, xg, poss)).fetchone()
            if dup:
                if apply:
                    conn.execute("DELETE FROM match_team_stats WHERE id=?", (rid,))
                deleted += 1
            else:
                all_dup = False
        if not all_dup:
            tname = conn.execute("SELECT name FROM teams WHERE id=?",
                                 (rows[0][1],)).fetchone()
            print(f"  ⚠ irresoluble: match_id={oid} ({tname[0] if tname else '?'}, "
                  f"xg={rows[0][2]}) — conservado huérfano")
            left += 1
    return remapped, deleted, left


def fix_player_stats(conn, apply: bool) -> tuple[int, int]:
    fixtures = conn.execute("""
        SELECT DISTINCT mps.match_date, mps.home_team_id, mps.away_team_id
        FROM match_player_stats mps
        WHERE mps.home_team_id IS NOT NULL AND mps.away_team_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM wc_matches wm
              WHERE abs(julianday(wm.date) - julianday(mps.match_date)) <= 1
                AND ((wm.home_team_id=mps.home_team_id AND wm.away_team_id=mps.away_team_id)
                  OR (wm.home_team_id=mps.away_team_id AND wm.away_team_id=mps.home_team_id)))
    """).fetchall()
    created = dedup = 0
    for (d, h, a) in fixtures:
        # fecha canónica + resultado desde team_matches (±1 día)
        tm = conn.execute("""
            SELECT date, goals_for, goals_against FROM team_matches
            WHERE team_id=? AND opponent_id=?
              AND abs(julianday(date) - julianday(?)) <= 1
            ORDER BY abs(julianday(date) - julianday(?)) LIMIT 1
        """, (h, a, d, d)).fetchone()
        if tm:
            cd, gf, ga = tm
            # rows en fecha NO canónica que duplican otra fecha del mismo fixture
            if cd != d and conn.execute("""
                SELECT 1 FROM match_player_stats WHERE match_date=? AND home_team_id=?
                  AND away_team_id=?""", (cd, h, a)).fetchone():
                n = conn.execute("""SELECT count(*) FROM match_player_stats
                    WHERE match_date=? AND home_team_id=? AND away_team_id=?""",
                    (d, h, a)).fetchone()[0]
                if apply:
                    conn.execute("""DELETE FROM match_player_stats
                        WHERE match_date=? AND home_team_id=? AND away_team_id=?""",
                        (d, h, a))
                print(f"  🗑 {n} filas duplicadas {d} (canónica {cd})")
                dedup += n
                continue
            wc_id, was_new = _find_or_create_wc(conn, h, a, cd, gf, ga, h, apply=apply)
            if was_new and wc_id:
                hn = conn.execute("SELECT name FROM teams WHERE id=?", (h,)).fetchone()[0]
                an = conn.execute("SELECT name FROM teams WHERE id=?", (a,)).fetchone()[0]
                print(f"  + wc_matches creado: {hn} {gf}-{ga} {an} ({cd})")
                created += 1
        else:
            hn = conn.execute("SELECT name FROM teams WHERE id=?", (h,)).fetchone()
            an = conn.execute("SELECT name FROM teams WHERE id=?", (a,)).fetchone()
            print(f"  ⚠ sin resultado en team_matches: {hn[0] if hn else h} vs "
                  f"{an[0] if an else a} ({d}) — no se crea wc_matches")
    return created, dedup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = not args.dry_run
    conn = sqlite3.connect(str(DB))

    print("── match_team_stats huérfanos ──")
    r, dd, lf = fix_team_stats(conn, apply)
    print(f"\n── match_player_stats sin wc_matches ──")
    c, dp = fix_player_stats(conn, apply)
    if apply:
        conn.commit()
    print(f"\n✅ remapeados={r}, stats-dup borrados={dd}, irresolubles={lf}, "
          f"wc creados={c}, player-dup borrados={dp}"
          + ("  (DRY-RUN)" if not apply else ""))
    conn.close()


if __name__ == "__main__":
    main()
