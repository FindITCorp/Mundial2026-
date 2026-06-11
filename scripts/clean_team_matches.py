#!/usr/bin/env python3
"""
clean_team_matches.py — Purga fixtures fabricados y duplicados conflictivos.

Hallazgo (10-jun-2026): team_matches mezcla 3 lotes de carga:
  - id < 1000   : lote semilla con fixtures INVENTADOS desde 2023
                  (England vs Croatia/France jun-2025 que no existieron,
                   "Argentina 3-0 Chile" repetido en 3 fechas, etc.)
  - id 1000-1999: lote real verificado (Colombia 2-1 Argentina, Uruguay 4-0
                  México, Finland 0-2 England... todos confirmados)
  - id >= 20000 : cargas posteriores, mayormente buenas con algunos dups malos
                  (Brazil "4-1 Paraguay" sep-2024 cuando fue 0-1).

Esto contamina el factor FORMA del modelo (últimos 5 partidos) y el fit del
sesgo de confederación. Solo se toca date >= 2023-01-01 (ventana que usan
los factores); lo histórico anterior no afecta el modelo.

Reglas de resolución, en orden de confianza:
  1. wc_matches con resultado → la verdad para ese fixture.
  2. Perspectiva recíproca (fila del rival con marcador espejo) → corrobora.
  3. Lote 1000-1999 > otros lotes cuando no hay corroboración.
  4. Conflicto de fecha (mismo equipo, misma fecha, rivales distintos):
     gana la fila corroborada; si ninguna y una es id<1000 → fuera la <1000;
     si ambas <1000 → fuera ambas (lote fabricado).

Uso:
    python3 scripts/clean_team_matches.py            # dry-run (solo reporte)
    python3 scripts/clean_team_matches.py --apply    # ejecuta borrado
"""
import argparse
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

SINCE = "2023-01-01"
FAB_MAX = 100              # ids 1-100: bloques fabricados de 10 filas/equipo
                           # (Argentina 1-10, France 11-20 ... USA 91-100)
TRUSTED_LO, TRUSTED_HI = 101, 1999   # ids 101-1999: lotes reales verificados


def _wc_truth(conn, team_id, opp_id, mdate):
    """Resultado sellado en wc_matches para este cruce (±1 día), si existe."""
    row = conn.execute("""
        SELECT home_team_id, score_home, score_away FROM wc_matches
        WHERE score_home IS NOT NULL
          AND abs(julianday(date) - julianday(?)) <= 1
          AND ((home_team_id=? AND away_team_id=?) OR (home_team_id=? AND away_team_id=?))
    """, (mdate, team_id, opp_id, opp_id, team_id)).fetchone()
    if row is None:
        return None
    h_id, sh, sa = row
    return (int(sh), int(sa)) if h_id == team_id else (int(sa), int(sh))


def _reciprocal(conn, team_id, opp_id, mdate, gf, ga):
    """¿Existe la fila espejo en la perspectiva del rival?
    Solo cuenta si el espejo NO es del lote fabricado (id<=100) — dos filas
    inventadas se corroboran entre sí (England-France 15-jun-2025)."""
    return conn.execute("""
        SELECT 1 FROM team_matches
        WHERE team_id=? AND opponent_id=?
          AND abs(julianday(date) - julianday(?)) <= 1
          AND goals_for=? AND goals_against=? AND id > ?
    """, (opp_id, team_id, mdate, ga, gf, FAB_MAX)).fetchone() is not None


def _twin_other_date(conn, row_id, team_id, opp_id, mdate, gf, ga):
    """¿Existe el mismo fixture (equipo, rival, marcador) en OTRA fecha (2-4
    días)? Señal de copia mal fechada — p.ej. 'Finland 2-0' el 07-sep cuando
    el partido real fue el 10-sep."""
    return conn.execute("""
        SELECT 1 FROM team_matches
        WHERE id != ? AND team_id=? AND opponent_id=?
          AND goals_for=? AND goals_against=?
          AND abs(julianday(date) - julianday(?)) BETWEEN 2 AND 4
    """, (row_id, team_id, opp_id, gf, ga, mdate)).fetchone() is not None


def _trust(conn, row_id, team_id, opp_id, mdate, gf, ga):
    """Puntaje de confianza de una fila. Mayor = más confiable."""
    truth = _wc_truth(conn, team_id, opp_id, mdate)
    if truth is not None:
        return 100 if truth == (gf, ga) else -100
    score = 0
    if _reciprocal(conn, team_id, opp_id, mdate, gf, ga):
        score += 10
    if TRUSTED_LO <= row_id <= TRUSTED_HI:
        score += 5
    elif row_id <= FAB_MAX:
        score -= 5
    if _twin_other_date(conn, row_id, team_id, opp_id, mdate, gf, ga):
        score -= 3   # probable copia mal fechada de otro fixture real
    return score


def clean(conn, apply: bool) -> tuple[int, int]:
    to_delete: set[int] = set()

    # ── Caso A: mismo equipo + mismo rival, dup ±1 día o copia ±4 días ───────
    # ±1 día con cualquier marcador = duplicado/conflicto del mismo partido.
    # 2-4 días SOLO con marcador idéntico = copia mal fechada (los cruces
    # ida/vuelta reales a 2-4 días tienen marcadores distintos y se respetan).
    pairs_a = conn.execute("""
        SELECT a.id, b.id, a.team_id, a.opponent_id,
               a.date, a.goals_for, a.goals_against,
               b.date, b.goals_for, b.goals_against
        FROM team_matches a
        JOIN team_matches b ON b.team_id=a.team_id AND b.opponent_id=a.opponent_id
            AND b.id > a.id AND abs(julianday(b.date) - julianday(a.date)) <= 4
        WHERE a.date >= ?
    """, (SINCE,)).fetchall()

    n_a = 0
    for (ida, idb, tid, oid, da, gfa, gaa, db_, gfb, gab) in pairs_a:
        if ida in to_delete or idb in to_delete:
            continue
        from datetime import date as _d
        gap = abs((_d.fromisoformat(db_[:10]) - _d.fromisoformat(da[:10])).days)
        if gap > 1 and (gfa, gaa) != (gfb, gab):
            continue   # ida/vuelta legítima (2-4 días, marcador distinto)
        ta = _trust(conn, ida, tid, oid, da, gfa, gaa)
        tb = _trust(conn, idb, tid, oid, db_, gfb, gab)
        # Duplicado exacto (mismo marcador): conservar uno (el de mejor trust)
        loser = idb if ta >= tb else ida
        to_delete.add(loser)
        n_a += 1
        tname = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()[0]
        oname = conn.execute("SELECT name FROM teams WHERE id=?", (oid,)).fetchone()
        oname = oname[0] if oname else "?"
        keep = ida if loser == idb else idb
        print(f"  A: {tname} vs {oname} {da}: borra id={loser}, conserva id={keep} "
              f"(trust {ta} vs {tb}) [{gfa}-{gaa} | {gfb}-{gab}]")

    # ── Caso B: mismo equipo + misma fecha + rival DISTINTO ──────────────────
    pairs_b = conn.execute("""
        SELECT a.id, b.id, a.team_id, a.opponent_id, b.opponent_id,
               a.date, a.goals_for, a.goals_against, b.goals_for, b.goals_against,
               a.opponent_name, b.opponent_name
        FROM team_matches a
        JOIN team_matches b ON b.team_id=a.team_id AND b.date=a.date AND b.id>a.id
            AND (b.opponent_id IS NULL OR a.opponent_id IS NULL
                 OR b.opponent_id != a.opponent_id)
        WHERE a.date >= ?
    """, (SINCE,)).fetchall()

    n_b = 0
    for (ida, idb, tid, oa, ob, mdate, gfa, gaa, gfb, gab, na, nb) in pairs_b:
        if ida in to_delete or idb in to_delete:
            continue
        ta = _trust(conn, ida, tid, oa, mdate, gfa, gaa) if oa else -5
        tb = _trust(conn, idb, tid, ob, mdate, gfb, gab) if ob else -5
        tname = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()[0]
        if ta <= -5 and tb <= -5 and ida < TRUSTED_LO and idb < TRUSTED_LO:
            # ambas del lote fabricado y sin corroboración → fuera las dos
            to_delete.update((ida, idb))
            print(f"  B: {tname} {mdate}: borra AMBAS id={ida},{idb} "
                  f"(vs {na} {gfa}-{gaa} | vs {nb} {gfb}-{gab}) — lote fabricado")
        else:
            loser = idb if ta > tb else ida
            keep = ida if loser == idb else idb
            to_delete.add(loser)
            print(f"  B: {tname} {mdate}: borra id={loser}, conserva id={keep} "
                  f"(trust {ta} vs {tb}) (vs {na} {gfa}-{gaa} | vs {nb} {gfb}-{gab})")
        n_b += 1

    # ── Caso C: purga del lote fabricado (ids 1-100, >=2023) ─────────────────
    # Evidencia 10-jun-2026: ids 1-100 son bloques sintéticos de 10 filas por
    # equipo con fixtures inventados (England-Italy 11-jun-25, Germany-USA
    # 19-jun-25, Brazil-Argentina "1-1" cuando fue 1-4...). Los ids 800-1999
    # son datos REALES verificados — NO se tocan. Una fila 1-100 solo
    # sobrevive si wc_matches la confirma.
    n_c = 0
    low_rows = conn.execute("""
        SELECT id, team_id, opponent_id, date, goals_for, goals_against,
               (SELECT name FROM teams WHERE id=team_matches.team_id),
               opponent_name
        FROM team_matches WHERE id <= ? AND date >= ?
    """, (FAB_MAX, SINCE)).fetchall()
    for (rid, tid, oid, mdate, gf, ga, tname, oname) in low_rows:
        if rid in to_delete:
            continue
        truth = _wc_truth(conn, tid, oid, mdate) if oid else None
        if truth == (gf, ga):
            continue                      # confirmado por wc_matches
        to_delete.add(rid)                # lote fabricado sin corroboración
        n_c += 1
        print(f"  C: purga id={rid}: {tname} {mdate} vs {oname} {gf}-{ga}")

    print(f"\n  Caso A resueltos: {n_a} | Caso B resueltos: {n_b} "
          f"| Caso C purgados: {n_c} | filas a borrar: {len(to_delete)}")

    if apply and to_delete:
        conn.executemany("DELETE FROM team_matches WHERE id=?",
                         [(i,) for i in to_delete])
        conn.commit()
        print(f"  🗑️  {len(to_delete)} filas borradas de team_matches")
    elif not apply:
        print("  (dry-run — usa --apply para ejecutar)")
    return n_a + n_b, len(to_delete)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ejecuta el borrado")
    args = ap.parse_args()
    conn = sqlite3.connect(str(DB))
    clean(conn, apply=args.apply)
    conn.close()


if __name__ == "__main__":
    main()
