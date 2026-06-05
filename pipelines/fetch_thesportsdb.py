"""
fetch_thesportsdb.py — Sincroniza resultados de amistosos internacionales
desde TheSportsDB (gratuito, sin key) hacia team_matches.

PROTECCIONES:
  1. Mapping EXPLÍCITO TheSportsDB-name → DB-name para los 62 equipos WC2026.
     Si un nombre no está en el mapa → skip (nunca fuzzy-match).
  2. Deduplicación estricta: (team_id, date, opponent_name) UNIQUE.
  3. Modo --dry-run: muestra qué insertaría sin tocar la DB.
  4. Solo inserta partidos con ambos equipos en el mapa (si uno es desconocido
     se registra solo el equipo conocido contra el nombre literal de TSDB).

Uso:
    python pipelines/fetch_thesportsdb.py            # inserta
    python pipelines/fetch_thesportsdb.py --dry-run  # solo muestra
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"

# ── Mapping EXPLÍCITO TheSportsDB → nombre en nuestra DB ─────────────────────
# Solo los equipos que pueden aparecer en amistosos internacionales relevantes.
# Añadir entradas aquí si TheSportsDB usa un nombre diferente al nuestro.
TSDB_TO_DB: dict[str, str] = {
    # Nombre exacto TSDB          → nombre exacto en teams.name
    "Algeria":                      "Algeria",
    "Argentina":                    "Argentina",
    "Australia":                    "Australia",
    "Austria":                      "Austria",
    "Belgium":                      "Belgium",
    "Bolivia":                      "Bolivia",
    "Bosnia and Herzegovina":       "Bosnia and Herzegovina",
    "Bosnia-Herzegovina":           "Bosnia and Herzegovina",
    "Brazil":                       "Brazil",
    "Cameroon":                     "Cameroon",
    "Canada":                       "Canada",
    "Cape Verde":                   "Cape Verde",
    "Cabo Verde":                   "Cape Verde",
    "Colombia":                     "Colombia",
    "Costa Rica":                   "Costa Rica",
    "Croatia":                      "Croatia",
    "Curacao":                      "Curacao",
    "Czech Republic":               "Czechia",
    "Czechia":                      "Czechia",
    "DR Congo":                     "DR Congo",
    "Congo DR":                     "DR Congo",
    "Democratic Republic of Congo": "DR Congo",
    "Denmark":                      "Denmark",
    "Ecuador":                      "Ecuador",
    "Egypt":                        "Egypt",
    "England":                      "England",
    "France":                       "France",
    "Germany":                      "Germany",
    "Ghana":                        "Ghana",
    "Haiti":                        "Haiti",
    "Honduras":                     "Honduras",
    "Hungary":                      "Hungary",
    "Iran":                         "Iran",
    "Iraq":                         "Iraq",
    "Italy":                        "Italy",
    "Ivory Coast":                  "Ivory Coast",
    "Côte d'Ivoire":                "Ivory Coast",
    "Cote d'Ivoire":                "Ivory Coast",
    "Jamaica":                      "Jamaica",
    "Japan":                        "Japan",
    "Jordan":                       "Jordan",
    "Mexico":                       "Mexico",
    "Morocco":                      "Morocco",
    "Netherlands":                  "Netherlands",
    "New Zealand":                  "New Zealand",
    "Nigeria":                      "Nigeria",
    "Norway":                       "Norway",
    "Panama":                       "Panama",
    "Paraguay":                     "Paraguay",
    "Poland":                       "Poland",
    "Portugal":                     "Portugal",
    "Qatar":                        "Qatar",
    "Romania":                      "Romania",
    "Saudi Arabia":                 "Saudi Arabia",
    "Scotland":                     "Scotland",
    "Senegal":                      "Senegal",
    "Serbia":                       "Serbia",
    "Slovenia":                     "Slovenia",
    "South Africa":                 "South Africa",
    "Korea Republic":               "South Korea",
    "South Korea":                  "South Korea",
    "Spain":                        "Spain",
    "Sweden":                       "Sweden",
    "Switzerland":                  "Switzerland",
    "Tunisia":                      "Tunisia",
    "Turkey":                       "Turkey",
    "Türkiye":                      "Turkey",
    "USA":                          "USA",
    "United States":                "USA",
    "Uruguay":                      "Uruguay",
    "Uzbekistan":                   "Uzbekistan",
    "Venezuela":                    "Venezuela",
    # Equipos que aparecen como rivales frecuentes (no WC pero útiles)
    "China":                        "China PR",
    "China PR":                     "China PR",
    "Georgia":                      "Georgia",
    "Indonesia":                    "Indonesia",
    "Bahrain":                      "Bahrain",
    "Tajikistan":                   "Tajikistan",
    "India":                        "India",
    "Slovakia":                     "Slovakia",
    "Oman":                         "Oman",
    "Singapore":                    "Singapore",
    "Finland":                      "Finland",
    "Iraq":                         "Iraq",
    "Peru":                         "Peru",
    "Nicaragua":                    "Nicaragua",
    "Ireland":                      "Republic of Ireland",
    "Republic of Ireland":          "Republic of Ireland",
}

BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"


def _get(path: str, params: dict) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [tsdb] error {path}: {e}")
    return None


def _resolve(tsdb_name: str) -> str | None:
    """Devuelve el nombre en nuestra DB o None si no está en el mapa."""
    return TSDB_TO_DB.get(tsdb_name)


def _team_id(conn: sqlite3.Connection, db_name: str) -> int | None:
    row = conn.execute("SELECT id FROM teams WHERE name = ?", (db_name,)).fetchone()
    return row[0] if row else None


def _already_exists(conn: sqlite3.Connection, team_id: int,
                    match_date: str, opponent_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM team_matches WHERE team_id=? AND date=? AND opponent_name=?",
        (team_id, match_date, opponent_name)
    ).fetchone()
    return row is not None


def _insert(conn: sqlite3.Connection, team_id: int, opponent_id: int | None,
            opponent_name: str, match_date: str, gf: int, ga: int,
            competition: str, dry_run: bool) -> bool:
    if _already_exists(conn, team_id, match_date, opponent_name):
        return False
    result = "W" if gf > ga else ("D" if gf == ga else "L")
    if dry_run:
        print(f"    [DRY] INSERT team_id={team_id} vs {opponent_name} {gf}-{ga} {match_date} ({result})")
        return True
    conn.execute(
        """INSERT OR IGNORE INTO team_matches
           (team_id, opponent_id, opponent_name, date, competition, goals_for, goals_against, result)
           VALUES (?,?,?,?,?,?,?,?)""",
        (team_id, opponent_id, opponent_name, match_date, competition, gf, ga, result)
    )
    return True


def fetch_events_for_team(tsdb_team_id: str, last_n: int = 15) -> list[dict]:
    """Últimos N eventos de un equipo en TheSportsDB."""
    d = _get("/eventslast.php", {"id": tsdb_team_id})
    if not d:
        return []
    events = d.get("results") or []
    time.sleep(0.3)
    return events[:last_n]


def search_team_id(tsdb_name: str) -> str | None:
    """Busca el idTeam de TheSportsDB por nombre exacto."""
    d = _get("/searchteams.php", {"t": tsdb_name})
    if not d or not d.get("teams"):
        return None
    # Solo aceptar match exacto (case-insensitive)
    for t in d["teams"]:
        if t.get("strTeam", "").lower() == tsdb_name.lower():
            time.sleep(0.3)
            return t["idTeam"]
    return None


def run(days_back: int = 14, dry_run: bool = False):
    conn = sqlite3.connect(DB_PATH)
    today = date.today()
    cutoff = (today - timedelta(days=days_back)).isoformat()

    inserted = 0
    skipped_no_map = []
    skipped_dup = 0
    skipped_no_score = 0

    # Para cada equipo WC2026 con nombre en TSDB_TO_DB (inverso del mapa)
    # Construimos el mapa DB-name → TSDB-name para buscar
    # Usamos los "last events" de cada equipo directamente

    # Primero: obtener todos los equipos WC2026 de la DB
    wc_teams = conn.execute(
        "SELECT id, name FROM teams WHERE wc_group IS NOT NULL ORDER BY name"
    ).fetchall()

    print(f"Procesando {len(wc_teams)} equipos WC2026 (últimos {days_back} días)...")

    for db_id, db_name in wc_teams:
        # ¿Sabemos cómo se llama en TSDB? Buscar nombre TSDB que mapea a este equipo
        tsdb_names = [k for k, v in TSDB_TO_DB.items() if v == db_name]
        if not tsdb_names:
            print(f"  ⚠️  Sin nombre TSDB para: {db_name}")
            continue

        # Buscar idTeam en TSDB con el primer nombre conocido
        tsdb_search_name = tsdb_names[0]
        tsdb_id = search_team_id(tsdb_search_name)
        if not tsdb_id:
            print(f"  ⚠️  No encontrado en TSDB: {tsdb_search_name}")
            continue

        events = fetch_events_for_team(tsdb_id)
        team_inserted = 0

        for ev in events:
            ev_date = ev.get("dateEvent", "")
            if not ev_date or ev_date < cutoff:
                continue

            # Solo amistosos internacionales
            league = ev.get("strLeague", "")
            if "friendly" not in league.lower() and "international" not in league.lower():
                continue

            home_tsdb = ev.get("strHomeTeam", "")
            away_tsdb = ev.get("strAwayTeam", "")
            score_h = ev.get("intHomeScore")
            score_a = ev.get("intAwayScore")

            # Sin marcador → skip
            if score_h is None or score_a is None:
                skipped_no_score += 1
                continue

            try:
                gf_h, ga_h = int(score_h), int(score_a)
            except (ValueError, TypeError):
                skipped_no_score += 1
                continue

            # Resolver ambos equipos
            home_db = _resolve(home_tsdb)
            away_db = _resolve(away_tsdb)

            if home_db is None:
                skipped_no_map.append(home_tsdb)
            if away_db is None:
                skipped_no_map.append(away_tsdb)

            # Insertar para cada equipo que conozcamos
            for (our_name, our_gf, our_ga, opp_tsdb, opp_db) in [
                (home_db, gf_h, ga_h, away_tsdb, away_db),
                (away_db, ga_h, gf_h, home_tsdb, home_db),
            ]:
                if our_name is None:
                    continue
                our_id = _team_id(conn, our_name)
                if our_id is None:
                    continue
                opp_id = _team_id(conn, opp_db) if opp_db else None
                opp_name_final = opp_db or opp_tsdb  # si no mapeamos rival, guardamos nombre TSDB literal

                ok = _insert(conn, our_id, opp_id, opp_name_final,
                             ev_date, our_gf, our_ga, "Friendly", dry_run)
                if ok:
                    inserted += 1
                    team_inserted += 1
                else:
                    skipped_dup += 1

        if team_inserted:
            print(f"  ✅ {db_name}: +{team_inserted} partidos")

    if not dry_run:
        conn.commit()
    conn.close()

    # Resumen
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Resumen:")
    print(f"  Insertados:       {inserted}")
    print(f"  Duplicados skip:  {skipped_dup}")
    print(f"  Sin marcador:     {skipped_no_score}")
    if skipped_no_map:
        unique_unknown = sorted(set(skipped_no_map))
        print(f"  Nombres sin mapa ({len(unique_unknown)}): {unique_unknown}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    run(days_back=args.days, dry_run=args.dry_run)
