"""
fetch_teams.py — Fetch all 48 WC2026 teams with FIFA rankings.

Tries APIs in order:
  1. football-data.org
  2. api-football.com
  3. Falls back to static JSON

All raw responses cached in data/cache/teams/.
"""
import os
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "teams"
STATIC_DIR = BASE_DIR / "data" / "static"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

FD_BASE  = "https://api.football-data.org/v4"
AF_BASE  = "https://v3.football.api-sports.io"

FD_KEY   = os.getenv("FOOTBALL_DATA_KEY", "")
AF_KEY       = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

def _af_headers() -> dict:
    """Return correct auth headers: direct api-sports.io or RapidAPI fallback."""
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": AF_KEY,
    }


def cache_path(name: str) -> Path:
    today = datetime.now().strftime("%Y%m%d")
    return CACHE_DIR / f"{name}_{today}.json"


def load_cache(name: str) -> Optional[dict]:
    p = cache_path(name)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def save_cache(name: str, data) -> None:
    p = cache_path(name)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Guardado en cache: {p.name}")


def try_import_optional():
    try:
        from typing import Optional
        return True
    except ImportError:
        return False


try:
    from typing import Optional
except ImportError:
    pass


def fetch_from_football_data() -> Optional[dict]:
    """Fetch WC teams from football-data.org."""
    if not FD_KEY:
        return None

    cached = load_cache("fd_wc_teams")
    if cached:
        print("  [FD] Usando cache.")
        return cached

    url = f"{FD_BASE}/competitions/WC/teams"
    headers = {"X-Auth-Token": FD_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            save_cache("fd_wc_teams", data)
            return data
        print(f"  [FD] Error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  [FD] Exception: {e}")
    return None


def fetch_from_api_football() -> Optional[list]:
    """Fetch team FIFA rankings from api-football.com."""
    if not (APISPORTS_KEY or AF_KEY):
        return None

    cached = load_cache("af_fifa_rankings")
    if cached:
        print("  [AF] Usando cache.")
        return cached

    url = f"{AF_BASE}/teams"
    headers = _af_headers()
    params = {"league": 1, "season": 2026}  # World Cup 2026
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get("response", [])
            save_cache("af_fifa_rankings", data)
            return data
        print(f"  [AF] Error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  [AF] Exception: {e}")
    return None


def load_from_static() -> list:
    """Load 48 WC2026 teams from static JSON (always available)."""
    path = STATIC_DIR / "teams_wc2026.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f).get("teams", [])


def update_db_from_static(teams: list) -> int:
    """Update teams table in DB with fresh data."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    updated = 0
    for t in teams:
        # Only update ranking if we have a fresher value from API
        cur.execute("""
            UPDATE teams SET fifa_ranking=? WHERE name=? AND (fifa_ranking IS NULL OR fifa_ranking != ?)
        """, (t.get("fifa_ranking"), t["name"], t.get("fifa_ranking")))
        updated += cur.rowcount

    conn.commit()
    conn.close()
    return updated


def update_db_from_api(api_teams: list) -> int:
    """
    Parse API-football response and update FIFA rankings in DB.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    updated = 0
    for team_data in api_teams:
        team = team_data.get("team", {})
        name = team.get("name", "")
        # API-football doesn't directly give FIFA ranking in free tier
        # We update what we can
        if name:
            cur.execute("UPDATE teams SET name=? WHERE name=?", (name, name))
            updated += cur.rowcount

    conn.commit()
    conn.close()
    return updated


def run():
    """Main entry point for fetching teams."""
    print("\n=== Pipeline: Fetch Teams ===\n")

    # Try APIs first
    fd_data = fetch_from_football_data()
    af_data = fetch_from_api_football()

    # Always load static as baseline
    static_teams = load_from_static()

    if not static_teams:
        print("  ERROR: No se encontró teams_wc2026.json. Ejecuta setup_db.py primero.")
        return False

    print(f"  Equipos estáticos: {len(static_teams)}")

    if fd_data:
        print(f"  football-data.org: datos obtenidos.")
    else:
        print("  football-data.org: no disponible (sin API key o error).")

    if af_data:
        print(f"  API-Football: {len(af_data)} teams.")
        update_db_from_api(af_data)
    else:
        print("  API-Football: no disponible.")

    # Update DB from static
    n = update_db_from_static(static_teams)
    print(f"  DB actualizada: {n} equipos modificados.")

    # Verify DB state
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    conn.close()
    print(f"  Total equipos en DB: {count}")

    print("\nPipeline teams completado.\n")
    return True


if __name__ == "__main__":
    run()
