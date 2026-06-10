#!/usr/bin/env python3
"""
sync_confirmed_xi.py — Alineación confirmada → projected_lineups (factor XI).

Eslabón faltante detectado 10-jun-2026: store_apisports_today.py guarda la
alineación CONFIRMADA en match_lineups, pero el factor XI del modelo (18%) lee
projected_lineups — que se quedaba con la proyección vieja. Este script copia
el XI confirmado de partidos recientes/próximos a projected_lineups, de modo
que predicciones y re-predicciones del día usen el once real.

Reglas de seguridad:
- Solo partidos con fecha en [hoy-1, hoy+2].
- Solo equipos con >=10 titulares confirmados mapeados a player_id conocido
  (si la API no mapeó bien los nombres, NO tocar la proyección).
- Titular confirmado sin fila en projected_lineups → se inserta (convocado nuevo).

Uso:
    python3 scripts/sync_confirmed_xi.py            # ventana automática
    python3 scripts/sync_confirmed_xi.py --days 7   # ventana ampliada
"""
import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

MIN_MAPPED_STARTERS = 10


def sync(conn, days_back: int = 1, days_fwd: int = 2) -> int:
    d0 = (date.today() - timedelta(days=days_back)).isoformat()
    d1 = (date.today() + timedelta(days=days_fwd)).isoformat()

    matches = conn.execute("""
        SELECT id, date, home_team_id, away_team_id, home_team_name, away_team_name
        FROM wc_matches WHERE date BETWEEN ? AND ?
    """, (d0, d1)).fetchall()

    teams_updated = 0
    for mid, mdate, h_id, a_id, h_name, a_name in matches:
        for tid, tname in [(h_id, h_name), (a_id, a_name)]:
            if tid is None:
                continue
            starters = [r[0] for r in conn.execute("""
                SELECT player_id FROM match_lineups
                WHERE match_id=? AND team_id=? AND starter=1 AND player_id IS NOT NULL
            """, (mid, tid))]
            if len(starters) < MIN_MAPPED_STARTERS:
                continue

            conn.execute("UPDATE projected_lineups SET is_starter=0 WHERE team_id=?", (tid,))
            for pid in starters:
                cur = conn.execute("""
                    UPDATE projected_lineups SET is_starter=1
                    WHERE team_id=? AND player_id=?
                """, (tid, pid))
                if cur.rowcount == 0:
                    conn.execute("""
                        INSERT INTO projected_lineups (team_id, player_id, is_starter)
                        VALUES (?,?,1)
                    """, (tid, pid))
            teams_updated += 1
            print(f"  ✅ XI confirmado aplicado: {tname} ({len(starters)} titulares, partido {mid} {mdate})")
    return teams_updated


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2, help="días hacia adelante (default 2)")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB))
    n = sync(conn, days_fwd=args.days)
    conn.commit()
    conn.close()
    print(f"[sync_confirmed_xi] {n} equipos actualizados con XI confirmado")


if __name__ == "__main__":
    main()
