"""
rebuild_squads.py — Reconstruye wc26_squad y projected_lineups a partir de los datos
actuales en la DB. Se ejecuta como paso final en el pipeline de actualización de datos,
después de que fetch_players / fetch_nat_stats actualicen players y squad_selections.

Tablas que genera / reemplaza:
  wc26_squad        — squad de 26 por equipo, rankeado por rating
  projected_lineups — XI titular proyectado + banca para los 48 equipos

Uso:
  python pipelines/rebuild_squads.py
  python pipelines/rebuild_squads.py --team "France" "Brazil"
"""
import sys
import argparse
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DB_PATH = BASE_DIR / "data" / "mundial2026.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rebuild_squads")

# Composición estándar de convocatoria WC (26 jugadores)
WC_SQUAD_COMP = {"GK": 3, "DEF": 8, "MID": 8, "FWD": 7}


def parse_formation(f: str) -> dict:
    """'4-3-3' → {'GK':1,'DEF':4,'MID':3,'FWD':3}"""
    parts = [int(x) for x in f.strip().split("-")]
    if len(parts) == 3:
        return {"GK": 1, "DEF": parts[0], "MID": parts[1], "FWD": parts[2]}
    elif len(parts) >= 4:
        return {"GK": 1, "DEF": parts[0], "MID": sum(parts[1:-1]), "FWD": parts[-1]}
    return {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2}


def rebuild(team_filter: list[str] | None = None) -> dict:
    """
    Reconstruye wc26_squad y projected_lineups.
    Devuelve stats: {teams, starters, bench, squads}
    """
    from models.player_rating import PlayerRater

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rater = PlayerRater()

    if team_filter:
        teams = conn.execute(
            "SELECT * FROM teams WHERE name IN ({})".format(
                ",".join("?" * len(team_filter))
            ),
            team_filter,
        ).fetchall()
        # Solo borrar las filas de estos equipos
        for t in teams:
            conn.execute("DELETE FROM wc26_squad WHERE team_id=?", (t["id"],))
            conn.execute("DELETE FROM projected_lineups WHERE team_id=?", (t["id"],))
    else:
        teams = conn.execute("SELECT * FROM teams ORDER BY id").fetchall()
        conn.execute("DELETE FROM wc26_squad")
        conn.execute("DELETE FROM projected_lineups")

    stats = {"teams": 0, "squads": 0, "starters": 0, "bench": 0, "warnings": []}

    for team in teams:
        tid = team["id"]
        tname = team["name"]
        formation_str = team["formation"] or "4-3-3"
        def_count = parse_formation(formation_str)["DEF"]
        attack_count = 10 - def_count

        players_raw = conn.execute(
            """SELECT p.* FROM players p
               JOIN squad_selections ss ON ss.player_id=p.id
               WHERE p.team_id=? AND ss.confirmed=1""",
            (tid,),
        ).fetchall()

        if not players_raw:
            stats["warnings"].append(f"{tname}: sin jugadores confirmed=1")
            continue

        # Calcular ratings
        rated = [
            {"player": dict(p), "rating": rater.estimate_rating_from_profile(dict(p))}
            for p in players_raw
        ]

        by_pos: dict[str, list] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
        for r in rated:
            pos = r["player"]["position"]
            if pos in by_pos:
                by_pos[pos].append(r)
        for pos in by_pos:
            by_pos[pos].sort(key=lambda x: x["rating"], reverse=True)

        # ── Squad de 26 ───────────────────────────────────────────────
        squad_26: list = []
        for pos, target in WC_SQUAD_COMP.items():
            available = by_pos[pos]
            squad_26.extend(available[:target])
            if len(available) < target:
                stats["warnings"].append(
                    f"{tname}: {pos} {len(available)}/{target}"
                )

        in_squad_ids = {x["player"]["id"] for x in squad_26}
        extras = sorted(
            [r for r in rated if r["player"]["id"] not in in_squad_ids],
            key=lambda x: x["rating"],
            reverse=True,
        )
        for ex in extras:
            if len(squad_26) >= 26:
                break
            squad_26.append(ex)
            in_squad_ids.add(ex["player"]["id"])

        squad_26.sort(key=lambda x: x["rating"], reverse=True)

        for rank, item in enumerate(squad_26, 1):
            conn.execute(
                "INSERT OR IGNORE INTO wc26_squad (team_id,player_id,squad_rank) VALUES (?,?,?)",
                (tid, item["player"]["id"], rank),
            )

        # ── XI titular proyectado ─────────────────────────────────────
        # 1 GK + DEF_count mejores defensas + (10-DEF_count) mejores MID+FWD combinados
        gk_pick = [x for x in by_pos["GK"] if x["player"]["id"] in in_squad_ids][:1]
        def_pick = [x for x in by_pos["DEF"] if x["player"]["id"] in in_squad_ids][:def_count]
        attack_pool = sorted(
            [
                x
                for x in by_pos["MID"] + by_pos["FWD"]
                if x["player"]["id"] in in_squad_ids
            ],
            key=lambda x: x["rating"],
            reverse=True,
        )[:attack_count]

        starters = gk_pick + def_pick + attack_pool
        starter_ids = {x["player"]["id"] for x in starters}

        for i, x in enumerate(gk_pick, 1):
            conn.execute(
                "INSERT OR IGNORE INTO projected_lineups VALUES (NULL,?,?,1,?)",
                (tid, x["player"]["id"], f"GK{i}"),
            )
        for i, x in enumerate(def_pick, 1):
            conn.execute(
                "INSERT OR IGNORE INTO projected_lineups VALUES (NULL,?,?,1,?)",
                (tid, x["player"]["id"], f"DEF{i}"),
            )
        for i, x in enumerate(attack_pool, 1):
            pos_lbl = x["player"]["position"]
            conn.execute(
                "INSERT OR IGNORE INTO projected_lineups VALUES (NULL,?,?,1,?)",
                (tid, x["player"]["id"], f"{pos_lbl}{i}"),
            )
        for x in squad_26:
            if x["player"]["id"] not in starter_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO projected_lineups VALUES (NULL,?,?,0,'BENCH')",
                    (tid, x["player"]["id"]),
                )

        stats["teams"] += 1
        stats["squads"] += len(squad_26)
        stats["starters"] += len(starters)
        stats["bench"] += len(squad_26) - len(starters)

    conn.commit()
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Rebuild wc26_squad + projected_lineups")
    parser.add_argument("--team", nargs="+", help="Equipos específicos (default: todos)")
    args = parser.parse_args()

    log.info("Iniciando rebuild de squads y lineups proyectados...")
    start = datetime.now()
    stats = rebuild(team_filter=args.team)
    elapsed = (datetime.now() - start).total_seconds()

    log.info(
        f"✅ Completado en {elapsed:.1f}s: "
        f"{stats['teams']} equipos | "
        f"{stats['squads']} squad-slots | "
        f"{stats['starters']} titulares | "
        f"{stats['bench']} suplentes"
    )
    if stats["warnings"]:
        log.warning(f"{len(stats['warnings'])} advertencias de datos:")
        for w in stats["warnings"][:10]:
            log.warning(f"  {w}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
