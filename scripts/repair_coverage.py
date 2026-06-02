#!/usr/bin/env python3
"""
scripts/repair_coverage.py — Auditoría y reparación de cobertura del modelo.

PROBLEMA QUE RESUELVE:
  predict_match() sólo funciona con equipos registrados en `teams`. Cuando un
  fixture incluye un equipo sin registro (Georgia, Madagascar, Wales, etc.) se
  improvisaban fórmulas que se saltaban Elo, Dixon-Coles y timing → predicciones
  malas (ej: Marruecos 1-0 Madagascar en vez del real 3-0).

  Además, el 44% de los partidos en team_matches no tenían opponent_id, por lo
  que se excluían del cálculo de Elo, perdiendo señal histórica.

QUÉ HACE:
  1. AUDIT  — reporta qué equipos con historial NO están en teams/elo/timing
  2. REPAIR — registra los equipos faltantes (con >= MIN_MATCHES partidos),
              enlaza opponent_id en todos los partidos resolubles por nombre,
              y reconstruye Elo desde el historial completo.

Uso:
  python3 scripts/repair_coverage.py --audit            # sólo diagnóstico
  python3 scripts/repair_coverage.py --repair           # registra + enlaza + rebuild Elo
  python3 scripts/repair_coverage.py --check "Wales" "Ghana"   # ¿predecibles?
"""

import argparse
import json
import sqlite3
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
DB_PATH = BASE_DIR / "data" / "mundial2026.db"
ALIASES_PATH = BASE_DIR / "data" / "team_name_aliases.json"

# Mínimo de partidos para considerar un equipo predecible con confianza
MIN_MATCHES = 8

# Equipos extintos / disueltos / sancionados — NO registrar como activos
DEFUNCT = {
    "Czechoslovakia", "Yugoslavia", "Soviet Union", "USSR", "German DR",
    "East Germany", "Serbia and Montenegro", "Netherlands Antilles",
    "Zaire", "Dutch East Indies", "Saar", "Basque Country", "Catalonia",
    "Russia",  # sancionada por FIFA/UEFA — fuera de competiciones oficiales
}


def load_aliases() -> dict:
    """Carga mapeo nombre externo → nombre canónico interno."""
    if ALIASES_PATH.exists():
        data = json.loads(ALIASES_PATH.read_text())
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


def canon(name: str, aliases: dict) -> str:
    """Devuelve el nombre canónico de un equipo (resuelve alias)."""
    return aliases.get(name, name)


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _confederation_guess(name: str) -> str:
    """Heurística simple — sólo informativa, no afecta el cálculo."""
    return "UNK"


def load_team_names(conn) -> set:
    return set(r[0] for r in conn.execute("SELECT name FROM teams").fetchall())


def audit(conn):
    """Reporta brechas de cobertura."""
    teams = load_team_names(conn)
    opps = set(r[0] for r in conn.execute(
        "SELECT DISTINCT opponent_name FROM team_matches WHERE opponent_name IS NOT NULL"
    ).fetchall())
    missing = sorted(opps - teams)

    # Partidos sin opponent_id
    total = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
    null_oid = conn.execute(
        "SELECT COUNT(*) FROM team_matches WHERE opponent_id IS NULL"
    ).fetchone()[0]
    recoverable = conn.execute("""
        SELECT COUNT(*) FROM team_matches tm
        WHERE tm.opponent_id IS NULL
          AND tm.opponent_name IN (SELECT name FROM teams)
    """).fetchone()[0]

    print("=" * 60)
    print("  AUDITORÍA DE COBERTURA")
    print("=" * 60)
    print(f"  Equipos en `teams`/`team_elo`:        {len(teams)}")
    print(f"  Oponentes distintos en historial:     {len(opps)}")
    print(f"  Equipos con historial SIN registro:   {len(missing)}")
    print()
    print(f"  Partidos totales:                     {total}")
    print(f"  Partidos sin opponent_id (perdidos):  {null_oid} ({100*null_oid/total:.0f}%)")
    print(f"  Recuperables ahora mismo:             {recoverable}")
    print()

    # Equipos faltantes con suficientes partidos = candidatos críticos
    candidates = []
    for m in missing:
        n = conn.execute(
            "SELECT COUNT(*) FROM team_matches WHERE opponent_name=?", (m,)
        ).fetchone()[0]
        if n >= MIN_MATCHES:
            candidates.append((m, n))
    candidates.sort(key=lambda x: -x[1])
    print(f"  Equipos faltantes con >= {MIN_MATCHES} partidos (deben registrarse): {len(candidates)}")
    for name, n in candidates[:30]:
        print(f"    {name:<28} {n:>4} partidos")
    if len(candidates) > 30:
        print(f"    ... y {len(candidates)-30} más")
    return candidates


def repair(conn, dry_run=False):
    """Registra equipos faltantes, enlaza opponent_id, reconstruye Elo."""
    aliases = load_aliases()
    teams = load_team_names(conn)
    opps = set(r[0] for r in conn.execute(
        "SELECT DISTINCT opponent_name FROM team_matches WHERE opponent_name IS NOT NULL"
    ).fetchall())

    # 1. Registrar equipos faltantes con >= MIN_MATCHES partidos
    #    - resolver alias: si el nombre apunta a un equipo ya registrado, NO crear duplicado
    #    - saltar equipos extintos/sancionados
    to_add = set()
    for raw in opps:
        c = canon(raw, aliases)
        if c in teams or c in DEFUNCT or raw in DEFUNCT:
            continue
        # contar partidos sumando todas las variantes que canonizan a c
        n = conn.execute(
            "SELECT COUNT(*) FROM team_matches WHERE opponent_name=?", (raw,)
        ).fetchone()[0]
        if n >= MIN_MATCHES:
            to_add.add(c)

    print(f"\n[1/3] Registrando {len(to_add)} equipos faltantes en `teams` "
          f"(alias resueltos, {len(DEFUNCT)} extintos omitidos)...")
    added = 0
    for name in sorted(to_add):
        if dry_run:
            continue
        try:
            conn.execute("""
                INSERT INTO teams (name, slug, confederation, fifa_ranking)
                VALUES (?, ?, ?, ?)
            """, (name, _slug(name), _confederation_guess(name), 999))
            added += 1
        except sqlite3.IntegrityError:
            pass
    if not dry_run:
        conn.commit()
    print(f"      {added} equipos registrados")

    # 2. Enlazar opponent_id en todos los partidos resolubles (vía alias)
    print("\n[2/3] Enlazando opponent_id por nombre (con alias)...")
    name_to_id = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM teams").fetchall()}
    rows = conn.execute("""
        SELECT id, opponent_name FROM team_matches
        WHERE opponent_id IS NULL AND opponent_name IS NOT NULL
    """).fetchall()
    linked = 0
    for r in rows:
        oid = name_to_id.get(canon(r[1], aliases))
        if oid:
            if not dry_run:
                conn.execute("UPDATE team_matches SET opponent_id=? WHERE id=?", (oid, r[0]))
            linked += 1
    if not dry_run:
        conn.commit()
    print(f"      {linked} partidos enlazados")

    # 3. Reconstruir Elo desde el historial ahora completo
    print("\n[3/3] Reconstruyendo Elo desde historial completo...")
    if not dry_run:
        from models.elo import EloSystem
        elo = EloSystem(db_path=str(DB_PATH))
        elo.build_from_history()
        n_elo = conn.execute("SELECT COUNT(*) FROM team_elo").fetchone()[0]
        with_oid = conn.execute(
            "SELECT COUNT(*) FROM team_matches WHERE opponent_id IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
        print(f"      Elo recalculado para {n_elo} equipos")
        print(f"      Partidos con opponent_id ahora: {with_oid}/{total} ({100*with_oid/total:.0f}%)")

    print("\n✅ Reparación completa")


def check_predictable(conn, names):
    """Verifica si un conjunto de equipos puede predecirse completo."""
    print("=" * 60)
    print("  VERIFICACIÓN DE PREDICTIBILIDAD")
    print("=" * 60)
    for name in names:
        trow = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        in_teams = trow is not None
        elo = timing = matches = None
        if in_teams:
            tid = trow[0]
            er = conn.execute("SELECT elo, matches FROM team_elo WHERE team_id=?", (tid,)).fetchone()
            elo = er[0] if er else None
            matches = er[1] if er else 0
        tm = conn.execute("SELECT 1 FROM team_goal_timing WHERE team_name=?", (name,)).fetchone()
        timing = tm is not None
        status = "✅ PREDECIBLE" if (in_teams and elo is not None) else "❌ INCOMPLETO"
        print(f"  {name:<20} teams={'sí' if in_teams else 'NO':<3} "
              f"elo={elo if elo else '—':<8} timing={'sí' if timing else 'no':<3} "
              f"part={matches or 0:<4} {status}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audit", action="store_true", help="Sólo diagnóstico")
    p.add_argument("--repair", action="store_true", help="Registrar + enlazar + rebuild Elo")
    p.add_argument("--dry-run", action="store_true", help="Simular reparación sin escribir")
    p.add_argument("--check", nargs="+", help="Verificar predictibilidad de equipos")
    args = p.parse_args()

    conn = sqlite3.connect(str(DB_PATH))

    if args.check:
        check_predictable(conn, args.check)
    elif args.repair:
        repair(conn, dry_run=args.dry_run)
    else:
        audit(conn)

    conn.close()


if __name__ == "__main__":
    main()
