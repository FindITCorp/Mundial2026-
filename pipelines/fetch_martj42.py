"""
fetch_martj42.py — Importa datos de partidos y goleadores internacionales
desde el repositorio público martj42/international_results (GitHub CSV).

Fuente: https://github.com/martj42/international_results
  - results.csv      : 49K+ partidos internacionales, hasta fecha actual
  - goalscorers.csv  : 47K+ registros de goleadores

Tablas que actualiza:
  team_matches      — nuevos partidos internacionales (ON CONFLICT IGNORE)
  player_nat_stats  — goals por jugador en partidos internacionales recientes

Uso:
  python pipelines/fetch_martj42.py
  python pipelines/fetch_martj42.py --since 2024-01-01
  python pipelines/fetch_martj42.py --team "Spain" "France"
"""
import sys
import csv
import io
import argparse
import sqlite3
import logging
import urllib.request
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DB_PATH = BASE_DIR / "data" / "mundial2026.db"

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
GOALSCORERS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv"

# Mapeo de nombres en martj42 → nombres en nuestra DB
NAME_MAP = {
    "United States": "USA",
    "Czech Republic": "Czechia",
    "Curaçao": "Curacao",
    "Republic of Ireland": "Ireland",
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Türkiye": "Turkey",
    "DR Congo": "DR Congo",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch_martj42")

TIMEOUT = 30


def fetch_csv(url: str) -> list[dict]:
    log.info(f"Descargando {url.split('/')[-1]}...")
    req = urllib.request.urlopen(url, timeout=TIMEOUT)
    data = req.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(data)))


def normalize_name(name: str) -> str:
    return NAME_MAP.get(name, name)


def load_team_map(conn) -> dict[str, int]:
    """Retorna {team_name: team_id}."""
    rows = conn.execute("SELECT id, name FROM teams").fetchall()
    return {r["name"]: r["id"] for r in rows}


def import_matches(conn, rows: list[dict], team_map: dict, since: str) -> dict:
    stats = {"inserted": 0, "skipped": 0, "unknown_teams": set()}

    for row in rows:
        date = row["date"]
        if date < since:
            continue
        if row["home_score"] == "NA" or row["away_score"] == "NA":
            continue  # Partido no jugado aún

        home = normalize_name(row["home_team"])
        away = normalize_name(row["away_team"])

        home_id = team_map.get(home)
        away_id = team_map.get(away)

        if home_id is None:
            stats["unknown_teams"].add(home)
        if away_id is None:
            stats["unknown_teams"].add(away)

        # Solo insertar si al menos uno de los equipos está en nuestra DB
        if home_id is None and away_id is None:
            continue

        home_score = int(row["home_score"])
        away_score = int(row["away_score"])
        tournament = row["tournament"]

        # Insertar para equipo local
        if home_id is not None:
            result = "W" if home_score > away_score else ("L" if home_score < away_score else "D")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO team_matches
                       (team_id, opponent_id, opponent_name, date, competition,
                        goals_for, goals_against, result, venue)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (home_id, away_id, away if away_id is None else None,
                     date, tournament, home_score, away_score, result, "home"),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                stats["skipped"] += 1

        # Insertar para equipo visitante
        if away_id is not None:
            result = "W" if away_score > home_score else ("L" if away_score < home_score else "D")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO team_matches
                       (team_id, opponent_id, opponent_name, date, competition,
                        goals_for, goals_against, result, venue)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (away_id, home_id, home if home_id is None else None,
                     date, tournament, away_score, home_score, result, "away"),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                stats["skipped"] += 1

    return stats


def import_goalscorers(conn, rows: list[dict], team_map: dict, since: str) -> dict:
    """
    Actualiza player_nat_stats con goles de partidos internacionales recientes.
    Busca jugadores por nombre (fuzzy: comparación case-insensitive).
    """
    stats = {"goals_linked": 0, "goals_unlinked": 0}

    # Construir mapa nombre→player_id para búsqueda rápida
    players = conn.execute(
        "SELECT id, name, team_id FROM players"
    ).fetchall()

    # Índice: (nombre_normalizado, team_id) → player_id
    name_team_idx: dict[tuple, int] = {}
    name_idx: dict[str, list[int]] = {}
    for p in players:
        key = p["name"].lower().strip()
        name_team_idx[(key, p["team_id"])] = p["id"]
        name_idx.setdefault(key, []).append(p["id"])

    for row in rows:
        date = row["date"]
        if date < since:
            continue
        if row["own_goal"] == "TRUE":
            continue  # Ignorar autogoles

        team_name = normalize_name(row["team"])
        scorer_name = row["scorer"].strip()
        opponent_name = normalize_name(
            row["away_team"] if row["team"] == row["home_team"] else row["home_team"]
        )

        team_id = team_map.get(team_name)
        if team_id is None:
            stats["goals_unlinked"] += 1
            continue

        # Buscar jugador
        key = scorer_name.lower()
        pid = name_team_idx.get((key, team_id))
        if pid is None:
            # Busca solo por nombre sin team_id
            candidates = name_idx.get(key, [])
            if len(candidates) == 1:
                pid = candidates[0]

        if pid is None:
            stats["goals_unlinked"] += 1
            continue

        # Buscar match_id en team_matches
        match = conn.execute(
            """SELECT id FROM team_matches
               WHERE team_id=? AND date=? AND opponent_name=?
               LIMIT 1""",
            (team_id, date, opponent_name),
        ).fetchone()
        if match is None:
            match = conn.execute(
                """SELECT id FROM team_matches
                   WHERE team_id=? AND date=?
                   LIMIT 1""",
                (team_id, date),
            ).fetchone()

        match_id = match["id"] if match else None

        # Insertar o actualizar player_nat_stats
        existing = conn.execute(
            "SELECT id, goals FROM player_nat_stats WHERE player_id=? AND match_date=?",
            (pid, date),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE player_nat_stats SET goals=goals+1 WHERE id=?",
                (existing["id"],),
            )
        else:
            conn.execute(
                """INSERT OR IGNORE INTO player_nat_stats
                   (player_id, match_id, match_date, opponent, goals, assists, was_starter)
                   VALUES (?,?,?,?,1,0,1)""",
                (pid, match_id, date, opponent_name),
            )

        stats["goals_linked"] += 1

    return stats


def run(since: str = "2024-01-01", team_filter: list | None = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    team_map = load_team_map(conn)

    if team_filter:
        # Filtrar team_map a solo los equipos pedidos
        team_map = {k: v for k, v in team_map.items() if k in team_filter}

    total_stats: dict = {}

    # 1. Partidos
    results_rows = fetch_csv(RESULTS_URL)
    m_stats = import_matches(conn, results_rows, team_map, since)
    total_stats["matches_inserted"] = m_stats["inserted"]
    total_stats["matches_skipped"] = m_stats["skipped"]
    unknown = m_stats["unknown_teams"]
    if unknown:
        log.debug(f"Equipos sin mapear: {len(unknown)} (ej: {list(unknown)[:5]})")
    log.info(
        f"  Partidos: {m_stats['inserted']} nuevos insertados, {m_stats['skipped']} ya existían"
    )

    # 2. Goleadores
    goal_rows = fetch_csv(GOALSCORERS_URL)
    g_stats = import_goalscorers(conn, goal_rows, team_map, since)
    total_stats["goals_linked"] = g_stats["goals_linked"]
    total_stats["goals_unlinked"] = g_stats["goals_unlinked"]
    log.info(
        f"  Goles nat vinculados: {g_stats['goals_linked']} "
        f"(no vinculados: {g_stats['goals_unlinked']})"
    )

    conn.commit()
    conn.close()
    return total_stats


def main():
    parser = argparse.ArgumentParser(description="Import martj42 international results")
    parser.add_argument("--since", default="2023-01-01", help="Fecha mínima (YYYY-MM-DD)")
    parser.add_argument("--team", nargs="+", help="Filtrar a equipos específicos")
    args = parser.parse_args()

    log.info(f"Iniciando import martj42 desde {args.since}...")
    start = datetime.now()
    stats = run(since=args.since, team_filter=args.team)
    elapsed = (datetime.now() - start).total_seconds()
    log.info(
        f"✅ Completado en {elapsed:.1f}s — "
        f"partidos: +{stats['matches_inserted']} | "
        f"goles vinculados: {stats['goals_linked']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
