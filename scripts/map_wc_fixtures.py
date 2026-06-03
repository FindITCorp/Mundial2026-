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
WC_LEAGUE_IDS = [1]   # 1 = FIFA World Cup en API-Football
WC_SEASON     = 2026


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
    for league_id in WC_LEAGUE_IDS:
        params = {"league": league_id, "season": WC_SEASON}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code != 200:
                print(f"  API error {r.status_code} for league {league_id}: {r.text[:100]}")
                continue
            fixtures = r.json().get("response", [])
            all_fixtures.extend(fixtures)
            print(f"  League {league_id}: {len(fixtures)} fixtures")
            time.sleep(1)
        except Exception as e:
            print(f"  Error: {e}")

    return all_fixtures


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

    # Obtener API key
    api_key  = os.environ.get("APISPORTS_KEY", "")
    rapid_key = os.environ.get("APIFOOT", "")
    key = api_key or rapid_key
    use_rapid = bool(rapid_key and not api_key)

    if not key:
        print("Sin API key disponible")
        conn.close()
        return

    print(f"Fetcheando fixtures de API-Football (season {WC_SEASON})...")
    fixtures = fetch_fixtures(key, use_rapidapi=use_rapid)

    if not fixtures:
        print("Sin fixtures obtenidos")
        conn.close()
        return

    print(f"Total fixtures obtenidos: {len(fixtures)}")

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
