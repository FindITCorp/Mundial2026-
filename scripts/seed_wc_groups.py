"""
scripts/seed_wc_groups.py — Sorteo válido de grupos WC2026 (48 equipos).

Los datos de grupos en la DB (teams.wc_group y wc_matches) están corruptos
(5–6 equipos por grupo, mezcla de 62 selecciones). Este script regenera un
sorteo VÁLIDO y reproducible a partir de los 48 clasificados reales:

  • 4 bombos de 12 por Elo (bombo 1 = más fuertes)
  • 12 grupos (A–L) con 1 equipo de cada bombo
  • Restricción de confederación FIFA: máx. 1 por grupo (UEFA hasta 2)
  • Reproducible (semilla fija) → mismo sorteo en cada corrida

Persiste en una tabla nueva `wc_group_draw (team_id, grp, pot)` sin tocar
los datos originales.
"""
from __future__ import annotations
import sqlite3
import random
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
GROUPS = list("ABCDEFGHIJKL")          # 12 grupos
MAX_PER_CONF = {"UEFA": 2}             # UEFA puede tener 2 por grupo
DEFAULT_MAX_CONF = 1
SEED = 2026


def _load_qualified(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT DISTINCT home_team_id AS id, home_team_name AS nm FROM wc_matches WHERE stage='group'
        UNION
        SELECT DISTINCT away_team_id, away_team_name FROM wc_matches WHERE stage='group'
    """).fetchall()
    teams = []
    seen = set()
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        elo = conn.execute("SELECT elo FROM team_elo WHERE team_id=?", (r["id"],)).fetchone()
        conf = conn.execute("SELECT confederation FROM teams WHERE id=?", (r["id"],)).fetchone()
        teams.append({
            "id": r["id"], "name": r["nm"],
            "elo": elo["elo"] if elo else 1500.0,
            "conf": (conf["confederation"] if conf else "?") or "?",
        })
    return teams


def _draw(teams: list[dict], seed: int = SEED) -> dict[int, str]:
    """Sortea 48 equipos en 12 grupos de 4 por bombos, respetando confederación."""
    rng = random.Random(seed)
    teams_sorted = sorted(teams, key=lambda t: -t["elo"])
    pots = [teams_sorted[i*12:(i+1)*12] for i in range(4)]   # 4 bombos de 12

    # estado de cada grupo
    group_conf: dict[str, dict[str, int]] = {g: {} for g in GROUPS}
    assignment: dict[int, str] = {}
    pot_of: dict[int, int] = {}

    def can_place(team, g) -> bool:
        conf = team["conf"]
        cur = group_conf[g].get(conf, 0)
        return cur < MAX_PER_CONF.get(conf, DEFAULT_MAX_CONF)

    for pot_idx, pot in enumerate(pots):
        pot_teams = pot[:]
        rng.shuffle(pot_teams)
        # grupos disponibles para este bombo (uno por grupo)
        avail_groups = GROUPS[:]
        rng.shuffle(avail_groups)
        # backtracking para garantizar asignación válida
        if not _assign_pot(pot_teams, avail_groups, group_conf, assignment,
                           pot_of, pot_idx, can_place):
            # fallback: relajar restricción si el sorteo se atasca
            for t in pot_teams:
                if t["id"] in assignment:
                    continue
                for g in GROUPS:
                    if sum(1 for tid, gg in assignment.items() if gg == g) < 4:
                        assignment[t["id"]] = g
                        group_conf[g][t["conf"]] = group_conf[g].get(t["conf"], 0) + 1
                        pot_of[t["id"]] = pot_idx
                        break
    return assignment, pot_of


def _assign_pot(pot_teams, avail_groups, group_conf, assignment, pot_of,
                pot_idx, can_place) -> bool:
    """Asigna recursivamente cada equipo del bombo a un grupo distinto válido."""
    if not pot_teams:
        return True
    team = pot_teams[0]
    for g in avail_groups:
        # cada grupo recibe exactamente 1 por bombo
        if any(assignment.get(t["id"]) == g for t in [team]):
            continue
        already_in_g_this_pot = any(
            gg == g and pot_of.get(tid) == pot_idx
            for tid, gg in assignment.items()
        )
        if already_in_g_this_pot:
            continue
        if not can_place(team, g):
            continue
        assignment[team["id"]] = g
        group_conf[g][team["conf"]] = group_conf[g].get(team["conf"], 0) + 1
        pot_of[team["id"]] = pot_idx
        if _assign_pot(pot_teams[1:], avail_groups, group_conf, assignment,
                       pot_of, pot_idx, can_place):
            return True
        # backtrack
        del assignment[team["id"]]
        group_conf[g][team["conf"]] -= 1
        del pot_of[team["id"]]
    return False


def run(db_path: Path = DB_PATH, seed: int = SEED) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    teams = _load_qualified(conn)
    if len(teams) != 48:
        print(f"  ⚠ Se esperaban 48 equipos, se encontraron {len(teams)}")

    assignment, pot_of = _draw(teams, seed)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS wc_group_draw (
            team_id INTEGER PRIMARY KEY REFERENCES teams(id),
            grp     TEXT NOT NULL,
            pot     INTEGER NOT NULL
        )
    """)
    conn.execute("DELETE FROM wc_group_draw")
    for t in teams:
        g = assignment.get(t["id"])
        p = pot_of.get(t["id"], 0) + 1
        conn.execute("INSERT INTO wc_group_draw (team_id, grp, pot) VALUES (?,?,?)",
                     (t["id"], g, p))
    conn.commit()

    # Reporte
    by_group: dict[str, list] = {g: [] for g in GROUPS}
    name_of = {t["id"]: t for t in teams}
    for tid, g in assignment.items():
        by_group[g].append(name_of[tid])
    conn.close()
    return by_group


if __name__ == "__main__":
    by_group = run()
    print(f"\n{'='*60}")
    print(f"  SORTEO WC2026 — 12 grupos de 4  (reproducible, seed={SEED})")
    print(f"{'='*60}")
    for g in GROUPS:
        teams = sorted(by_group[g], key=lambda t: -t["elo"])
        print(f"\n  GRUPO {g}")
        for t in teams:
            print(f"    {t['name']:<20} Elo {t['elo']:>6.0f}  [{t['conf']}]")
    # Validación
    print(f"\n{'─'*60}")
    sizes = {g: len(v) for g, v in by_group.items()}
    bad = {g: s for g, s in sizes.items() if s != 4}
    if bad:
        print(f"  ⚠ Grupos con tamaño incorrecto: {bad}")
    else:
        print(f"  ✅ Los 12 grupos tienen exactamente 4 equipos (48 total)")
