#!/usr/bin/env python3
"""
sync_player_match_ratings.py — match_player_stats → player_ratings (context='nat').

Reclamo del usuario (11-jun-2026): "yo te cargué los stats de los jugadores de
México y no los tienes en consideración". Tenía razón: los stats por partido
(con rating Sofascore) entraban a match_player_stats, pero el factor XI lee
player_ratings — y nada conectaba las dos tablas. Además los nombres venían
sin player_id (solo player_name + team_id) y hay jugadores duplicados
('Johan Vasquez' id=136 vs 'Johan Vásquez' id=12149).

Qué hace:
1. Toma cada fila de match_player_stats con rating NOT NULL.
2. Resuelve player_id por nombre normalizado (sin acentes, sin orden):
   - prefiere ids presentes en projected_lineups del equipo (convocados),
   - luego cualquier jugador del equipo.
3. Inserta en player_ratings (context='nat', computed_at=fecha del partido).
   Idempotente: no duplica (player_id, fecha).

Correr tras cargar stats de un partido. El workflow diario lo corre solo.
"""
import sqlite3
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def _keys(name: str) -> list[str]:
    """Claves de matching tolerantes: acentos, guiones, orden de palabras.
    'Jo Hyeonwoo' ↔ 'Jo Hyeon-woo' ↔ 'Hyeon-woo Jo' deben colisionar."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    words = s.replace("-", " ").split()
    return [
        " ".join(sorted(words)),          # palabras ordenadas
        "".join(sorted(words)),           # ordenadas y pegadas (guiones coreanos)
        "".join(s.split()).replace("-", ""),  # squash total en orden original
    ]


def sync(conn) -> int:
    # Índice nombre→player_id por equipo; preferencia: convocados (projected_lineups)
    squad_ids = {r[0] for r in conn.execute(
        "SELECT DISTINCT player_id FROM projected_lineups")}
    by_team: dict[int, dict[str, int]] = {}
    for pid, tid, name in conn.execute(
            "SELECT id, team_id, name FROM players WHERE team_id IS NOT NULL"):
        idx = by_team.setdefault(tid, {})
        for key in _keys(name):
            # convocado pisa a no-convocado; entre iguales gana el primero
            if key not in idx or (pid in squad_ids and idx[key] not in squad_ids):
                idx[key] = pid

    rows = conn.execute("""
        SELECT team_id, player_name, rating, match_date
        FROM match_player_stats
        WHERE rating IS NOT NULL AND player_name IS NOT NULL
    """).fetchall()

    inserted = skipped = unmatched = 0
    for tid, pname, rating, mdate in rows:
        idx = by_team.get(tid, {})
        pid = next((idx[k] for k in _keys(pname) if k in idx), None)
        if pid is None:
            unmatched += 1
            continue
        exists = conn.execute("""
            SELECT 1 FROM player_ratings
            WHERE player_id=? AND context='nat' AND computed_at=?
        """, (pid, mdate)).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO player_ratings (player_id, match_id, context, rating, computed_at)
            VALUES (?, NULL, 'nat', ?, ?)
        """, (pid, rating, mdate))
        inserted += 1

    print(f"[sync_player_match_ratings] +{inserted} ratings nuevos, "
          f"{skipped} ya existían, {unmatched} sin match de nombre")
    return inserted


def main() -> None:
    conn = sqlite3.connect(str(DB))
    sync(conn)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
