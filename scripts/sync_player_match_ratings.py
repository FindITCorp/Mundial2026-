#!/usr/bin/env python3
"""
sync_player_match_ratings.py — match_player_stats → player_ratings (context='nat').

Reclamo del usuario (11-jun-2026): "yo te cargué los stats de los jugadores de
México y no los tienes en consideración". Tenía razón: los stats por partido
(con rating Sofascore) entraban a match_player_stats, pero el factor XI lee
player_ratings — y nada conectaba las dos tablas. Además los nombres venían
sin player_id (solo player_name + team_id) y hay jugadores duplicados
('Johan Vasquez' id=136 vs 'Johan Vásquez' id=12149).

Mejora (15-jun-2026) — RATING CONSCIENTE DEL RESULTADO:
  Problema detectado: el rating Sofascore mide acciones INDIVIDUALES y casi nunca
  baja de 6.0. Un central que encaja 5 goles puede salir con 7.0. Cuando ese
  número alimenta la FUERZA DE EQUIPO (_get_xi_rating, 18% del modelo) infla a
  selecciones que fueron goleadas. Caso real: Túnez 5-1 → factor XI 1.31 (¡31%
  SOBRE la media, más que Alemania!). "Un 7.3 al recibir 5 goles no tiene sentido."

  Solución: match_player_stats.rating se mantiene CRUDO (fuente de verdad). Pero
  el valor que entra a player_ratings(nat) —usado como proxy de fuerza de equipo—
  se ajusta por el RESULTADO REAL del partido, ponderado por posición:
    · GK/DEF penalizados por goles encajados, premiados por valla invicta
    · FWD premiado por goles marcados, penalizado si el equipo no marcó
    · MID sensibilidad intermedia
  El ajuste es ACOTADO (downside −0.85, upside +0.55: un colapso defensivo informa
  más sobre debilidad real que una goleada a un minnow sobre fortaleza) y guarda
  raw+adj en components para trazabilidad total. No fuerza resultados: corrige una
  ceguera conocida del dato Sofascore (es scoreline-blind).

Qué hace:
1. Toma cada fila de match_player_stats con rating NOT NULL.
2. Resuelve player_id por nombre normalizado (sin acentos, sin orden):
   - prefiere ids presentes en projected_lineups del equipo (convocados),
   - luego cualquier jugador del equipo.
3. Resuelve el RESULTADO del partido (wc_matches por fecha+equipos; fallback
   team_matches) y aplica el ajuste consciente del resultado por posición.
4. Inserta en player_ratings (context='nat', computed_at=fecha del partido).
   Idempotente: no duplica (player_id, fecha).

Modos:
  (sin args)   sync incremental — solo inserta ratings nuevos
  --rebuild    borra los nat sourced de match_player_stats y los reconstruye
               con el ajuste consciente del resultado (necesario tras cambiar
               la fórmula de ajuste)

Correr tras cargar stats de un partido. El workflow diario lo corre solo.
"""
import sqlite3
import json
import unicodedata
import argparse
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


def _norm_pos(position: str) -> str:
    """Normaliza códigos de posición variados a {GK, DEF, MID, FWD}.
    Sofascore/intake usan G/D/M/F, GK/DEF/MID/FWD y FW/MF/DF indistintamente."""
    p = (position or "").strip().upper()
    if p in ("G", "GK"):                 return "GK"
    if p in ("D", "DEF", "DF"):          return "DEF"
    if p in ("M", "MID", "MF"):          return "MID"
    if p in ("F", "FWD", "FW", "ST"):    return "FWD"
    return "MID"  # desconocido → sensibilidad intermedia (neutro)


# Sensibilidad (defensa, ataque) por posición: cuánto refleja el resultado del
# equipo sobre la valoración de fuerza de ESTE jugador.
_POS_SENSITIVITY = {
    "GK":  (1.30, 0.00),
    "DEF": (1.00, 0.20),
    "MID": (0.50, 0.50),
    "FWD": (0.20, 1.00),
}

# Magnitudes del ajuste (puntos de rating Sofascore). Calibrado conservador.
_CONCEDE_PEN   = 0.11   # por gol encajado más allá de 1
_CLEAN_BONUS   = 0.16   # valla invicta
_SCORE_BONUS   = 0.09   # por gol marcado más allá de 1
_SHUTOUT_PEN   = 0.10   # el equipo no marcó
_ADJ_FLOOR     = -0.85  # downside mayor: un colapso defensivo pesa más
_ADJ_CEIL      = 0.55   # upside menor: golear minnows infla poco la fuerza real


def _result_adjustment(position: str, gf: int, ga: int) -> float:
    """Ajuste (puntos de rating) que hace el rating CONSCIENTE del resultado.
    gf=goles a favor del equipo del jugador, ga=goles en contra.
    Acotado a [_ADJ_FLOOR, _ADJ_CEIL]. Devuelve 0.0 si no hay contexto."""
    if gf is None or ga is None:
        return 0.0
    dw, aw = _POS_SENSITIVITY[_norm_pos(position)]
    concede_excess = max(0, ga - 1)
    score_excess   = max(0, gf - 1)
    clean_sheet    = 1 if ga == 0 else 0
    shutout        = 1 if gf == 0 else 0

    defense_term = (-_CONCEDE_PEN * concede_excess + _CLEAN_BONUS * clean_sheet) * dw
    attack_term  = (+_SCORE_BONUS * score_excess  - _SHUTOUT_PEN * shutout)     * aw
    adj = defense_term + attack_term
    return max(_ADJ_FLOOR, min(_ADJ_CEIL, adj))


def _match_result_for(conn, mdate, home_id, away_id, team_id):
    """Devuelve (gf, ga) para team_id en el partido (mdate, home_id, away_id).
    Busca primero wc_matches; fallback team_matches. None si no se resuelve."""
    if home_id and away_id:
        wm = conn.execute("""
            SELECT score_home, score_away FROM wc_matches
            WHERE date=? AND home_team_id=? AND away_team_id=?
              AND score_home IS NOT NULL
        """, (mdate, home_id, away_id)).fetchone()
        if wm:
            sh, sa = wm
            return (sh, sa) if team_id == home_id else (sa, sh)
    # Fallback: team_matches (amistosos Sofascore) — perspectiva ya es del equipo
    tm = conn.execute("""
        SELECT goals_for, goals_against FROM team_matches
        WHERE date=? AND team_id=? AND goals_for IS NOT NULL
        LIMIT 1
    """, (mdate, team_id)).fetchone()
    if tm:
        return (tm[0], tm[1])
    return (None, None)


def sync(conn, rebuild: bool = False) -> int:
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
        SELECT team_id, home_team_id, away_team_id, player_name, position,
               rating, match_date
        FROM match_player_stats
        WHERE rating IS NOT NULL AND player_name IS NOT NULL
    """).fetchall()

    # En --rebuild, borrar exactamente los nat creados por este script
    # (match_id IS NULL) que correspondan a (player_id, match_date) de stats.
    if rebuild:
        pairs = set()
        for tid, h_id, a_id, pname, pos, rating, mdate in rows:
            idx = by_team.get(tid, {})
            pid = next((idx[k] for k in _keys(pname) if k in idx), None)
            if pid is not None:
                pairs.add((pid, mdate))
        deleted = 0
        for pid, mdate in pairs:
            cur = conn.execute("""
                DELETE FROM player_ratings
                WHERE player_id=? AND context='nat' AND match_id IS NULL AND computed_at=?
            """, (pid, mdate))
            deleted += cur.rowcount
        print(f"[sync_player_match_ratings] --rebuild: {deleted} nat de stats borrados")

    inserted = skipped = unmatched = adjusted = 0
    for tid, h_id, a_id, pname, pos, rating, mdate in rows:
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

        # Ajuste consciente del resultado (proxy de fuerza de equipo)
        gf, ga = _match_result_for(conn, mdate, h_id, a_id, tid)
        adj = _result_adjustment(pos, gf, ga)
        stored = round(max(4.0, min(9.5, rating + adj)), 2)
        if abs(adj) > 1e-9:
            adjusted += 1
        components = json.dumps({
            "raw": rating, "adj": round(adj, 3),
            "gf": gf, "ga": ga, "pos": _norm_pos(pos), "src": "match_player_stats",
        })

        conn.execute("""
            INSERT INTO player_ratings (player_id, match_id, context, rating, components, computed_at)
            VALUES (?, NULL, 'nat', ?, ?, ?)
        """, (pid, stored, components, mdate))
        inserted += 1

    print(f"[sync_player_match_ratings] +{inserted} ratings nuevos "
          f"({adjusted} con ajuste por resultado), "
          f"{skipped} ya existían, {unmatched} sin match de nombre")
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="Borra y reconstruye los nat de match_player_stats con "
                         "el ajuste consciente del resultado (tras cambiar la fórmula)")
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB))
    sync(conn, rebuild=args.rebuild)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
