"""
scripts/map_wc_fixtures.py — Mapea api_fixture_id de API-Football a wc_matches.
Debe correr desde GitHub Actions donde la API está permitida.

Uso:
  python scripts/map_wc_fixtures.py
  python scripts/map_wc_fixtures.py --dry-run
"""
import os
import sys
import time
import sqlite3
import unicodedata
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DB = BASE / "data" / "mundial2026.db"

# API-Football competition IDs para buscar
# 1 = FIFA World Cup (principal), 777 = WC 2026 qualifier (fallback), 9 = Copa del Mundo alternativo
WC_LEAGUE_IDS = [1, 777, 9]
WC_SEASON     = 2026
WC_DATE_FROM  = "2026-06-11"
WC_DATE_TO    = "2026-07-20"


def _norm(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower().strip())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return n


# Mapa de nombres API-Football → nombres en nuestra DB
API_NAME_MAP = {
    "south korea":          "south korea",
    "korea republic":       "south korea",
    "republic of korea":    "south korea",
    "usa":                  "usa",
    "united states":        "usa",
    "ivory coast":          "ivory coast",
    "cote d'ivoire":        "ivory coast",
    "cape verde":           "cape verde",
    "cape verde islands":   "cape verde",
    "new zealand":          "new zealand",
    "bosnia":               "bosnia and herzegovina",
    "bosnia & herzegovina": "bosnia and herzegovina",
    "czechia":              "czechia",
    "czech republic":       "czechia",
}


def _resolve_team(api_name: str, our_teams: dict) -> str | None:
    n = _norm(api_name)
    if n in API_NAME_MAP:
        n = API_NAME_MAP[n]
    if n in our_teams:
        return our_teams[n]
    # Partial match
    for k, v in our_teams.items():
        if n in k or k in n:
            return v
    return None


def fetch_fixtures(key: str, use_rapidapi: bool = False) -> list:
    import requests

    if use_rapidapi:
        url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
        headers = {
            "x-rapidapi-key": key,
            "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
        }
    else:
        url = "https://v3.football.api-sports.io/fixtures"
        headers = {"x-apisports-key": key}

    all_fixtures = []
    seen_ids = set()

    # Estrategia 1: buscar por league_id + season
    for league_id in WC_LEAGUE_IDS:
        params = {"league": league_id, "season": WC_SEASON}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code != 200:
                print(f"  API error {r.status_code} league {league_id}: {r.text[:80]}")
                continue
            fixtures = r.json().get("response", [])
            new = [f for f in fixtures if f["fixture"]["id"] not in seen_ids]
            seen_ids.update(f["fixture"]["id"] for f in new)
            all_fixtures.extend(new)
            print(f"  League {league_id} season {WC_SEASON}: {len(fixtures)} fixtures ({len(new)} nuevos)")
            time.sleep(1)
        except Exception as e:
            print(f"  Error league {league_id}: {e}")

    # Estrategia 2: si no encontramos nada, buscar por rango de fechas
    if len(all_fixtures) < 10:
        print(f"  Pocos fixtures por league_id — buscando por fechas {WC_DATE_FROM}→{WC_DATE_TO}...")
        params = {"from": WC_DATE_FROM, "to": WC_DATE_TO, "season": WC_SEASON}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                fixtures = r.json().get("response", [])
                new = [f for f in fixtures if f["fixture"]["id"] not in seen_ids]
                seen_ids.update(f["fixture"]["id"] for f in new)
                all_fixtures.extend(new)
                print(f"  Por fechas: {len(fixtures)} fixtures ({len(new)} nuevos)")
        except Exception as e:
            print(f"  Error búsqueda por fechas: {e}")
        time.sleep(1)

    # Estrategia 3: buscar por timezone y filtrar por equipos WC conocidos
    if len(all_fixtures) < 10:
        print("  Intentando búsqueda directa por equipos WC (muestreo)...")
        # Buscar fixtures de equipos conocidos en junio 2026
        sample_teams_api = [6, 26, 9, 10, 2, 1, 7, 8]  # IDs comunes FIFA WC teams en API-Football
        for team_id in sample_teams_api[:3]:
            params = {"team": team_id, "season": WC_SEASON}
            try:
                r = requests.get(url, headers=headers, params=params, timeout=20)
                if r.status_code == 200:
                    fixtures = r.json().get("response", [])
                    new = [f for f in fixtures if f["fixture"]["id"] not in seen_ids
                           and WC_DATE_FROM <= f["fixture"]["date"][:10] <= WC_DATE_TO]
                    seen_ids.update(f["fixture"]["id"] for f in new)
                    all_fixtures.extend(new)
                    if new:
                        print(f"  Team {team_id}: {len(new)} fixtures WC encontrados")
            except Exception as e:
                print(f"  Error team {team_id}: {e}")
            time.sleep(1)

    return all_fixtures


def fetch_fixtures_football_data(key: str) -> list:
    """Obtiene fixtures del WC2026 desde football-data.org (competition code WC, season 2026)."""
    import requests

    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = {"X-Auth-Token": key}
    params  = {"season": WC_SEASON}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        print(f"  football-data.org status: {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text[:100]}")
            return []
        data = r.json()
        matches = data.get("matches", [])
        print(f"  football-data.org: {len(matches)} partidos encontrados")
        # Normalizar al mismo formato que API-Football
        result = []
        for m in matches:
            result.append({
                "fixture": {
                    "id":   m["id"],
                    "date": m.get("utcDate", "")[:10],
                },
                "teams": {
                    "home": {"name": m["homeTeam"]["name"], "id": m["homeTeam"]["id"]},
                    "away": {"name": m["awayTeam"]["name"], "id": m["awayTeam"]["id"]},
                },
                "league": {"id": "FD-WC"},
                "_source": "football-data.org",
            })
        return result
    except Exception as e:
        print(f"  football-data.org error: {e}")
        return []


def map_fixtures(dry_run: bool = False):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Cargar partidos WC sin fixture_id
    pending = conn.execute("""
        SELECT id, date, home_team_name, away_team_name
        FROM wc_matches
        WHERE api_fixture_id IS NULL
        ORDER BY date
    """).fetchall()

    print(f"Partidos sin api_fixture_id: {len(pending)}")
    if not pending:
        conn.close()
        return

    # Índice de equipos normalizados
    all_teams = conn.execute("SELECT name FROM teams").fetchall()
    our_teams = {_norm(r["name"]): r["name"] for r in all_teams}

    api_key     = os.environ.get("APISPORTS_KEY", "")
    rapid_key   = os.environ.get("APIFOOT", "")
    fd_key      = os.environ.get("FOOTBALL_DATA_KEY", "")
    use_rapid   = bool(rapid_key and not api_key)

    fixtures = []

    # Fuente 1: football-data.org (más fiable para WC2026 pre-torneo)
    if fd_key:
        print("Fetcheando fixtures desde football-data.org...")
        fixtures = fetch_fixtures_football_data(fd_key)

    # Fuente 2: API-Football como fallback
    if len(fixtures) < 10 and (api_key or rapid_key):
        key = api_key or rapid_key
        print(f"Fetcheando fixtures de API-Football (season {WC_SEASON})...")
        fixtures += fetch_fixtures(key, use_rapidapi=use_rapid)

    if not fixtures:
        print("Sin API key disponible o sin fixtures encontrados")
        conn.close()
        return

    if not fixtures:
        print("Sin fixtures obtenidos")
        conn.close()
        return

    print(f"Total fixtures obtenidos: {len(fixtures)}")

    # Debug: mostrar muestra de lo que devolvió la API
    if fixtures:
        sample = fixtures[:3]
        for f in sample:
            print(f"  Sample: {f['fixture']['id']} | {f['teams']['home']['name']} vs {f['teams']['away']['name']} | {f['fixture']['date'][:10]} | league {f['league']['id']}")

    # Indexar fixtures API por (home_norm, away_norm, date)
    api_index = {}
    for f in fixtures:
        fixture_id  = f["fixture"]["id"]
        date        = f["fixture"]["date"][:10]  # YYYY-MM-DD
        home_api    = f["teams"]["home"]["name"]
        away_api    = f["teams"]["away"]["name"]

        home_our = _resolve_team(home_api, our_teams)
        away_our = _resolve_team(away_api, our_teams)

        if home_our and away_our:
            key_exact = (home_our, away_our, date)
            api_index[key_exact] = fixture_id

    # Mapear cada partido pendiente
    matched = 0
    unmatched = []
    for m in pending:
        key_try = (m["home_team_name"], m["away_team_name"], m["date"])
        fid = api_index.get(key_try)

        if fid:
            if not dry_run:
                conn.execute(
                    "UPDATE wc_matches SET api_fixture_id=? WHERE id=?",
                    (fid, m["id"])
                )
            matched += 1
            print(f"  ✅ {m['home_team_name']} vs {m['away_team_name']} {m['date']} → fixture {fid}")
        else:
            unmatched.append(m)

    if not dry_run:
        conn.commit()

    print(f"\nMapeados: {matched}/{len(pending)}")
    if unmatched:
        print(f"Sin mapear ({len(unmatched)}):")
        for m in unmatched:
            print(f"  ❌ {m['home_team_name']} vs {m['away_team_name']} {m['date']}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    map_fixtures(dry_run=args.dry_run)
