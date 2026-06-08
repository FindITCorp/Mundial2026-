"""
fetch_live_football_data.py — "Free API Live Football Data" (RapidAPI, $9.99/mo)

Estado confirmado (Jun 2026):
  ✓ /football-get-all-leagues → devuelve catálogo de ligas con IDs
  ✗ Todos los endpoints de partidos/scores/players → 404 o "Request Failed"

IDs de ligas relevantes (para usar con otras APIs):
  77  = World Cup (FIFA WC 2026)
  114 = Friendlies (partidos de preparación)
  44  = Copa America
  50  = EURO
  42  = Champions League
  298 = CONCACAF Gold Cup

Para datos de partidos usamos api-sports.io (APISPORTS_KEY).
"""
import os
import sqlite3
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

_raw = os.environ.get("APIFOOT", "")
API_KEY = _raw.strip()
if "\n" in API_KEY or "=" in API_KEY:
    for _line in API_KEY.splitlines():
        _line = _line.strip()
        if "API_FOOTBALL_KEY" in _line or "APIFOOT" in _line:
            API_KEY = _line.split("=", 1)[-1].strip()
            break

API_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}"
HEADERS = {
    "x-rapidapi-host": API_HOST,
    "x-rapidapi-key": API_KEY,
}

# IDs de ligas internacionales confirmados (extraídos del endpoint de ligas)
LEAGUE_IDS = {
    "world_cup": 77,
    "friendlies": 114,
    "copa_america": 44,
    "euro": 50,
    "champions_league": 42,
    "concacaf_gold_cup": 298,
    "concacaf_nations_league": 9821,
    "africa_cup": 289,
    "asian_cup": 290,
}


def get_leagues(db_path=DB) -> list:
    """Único endpoint funcional: catálogo de ligas con IDs."""
    import urllib.request
    import urllib.parse
    try:
        url = f"{BASE_URL}/football-get-all-leagues"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
            leagues = data.get("response", {}).get("leagues", [])
            print(f"[live_football] leagues: {len(leagues)} returned")
            return leagues
    except Exception as e:
        print(f"[live_football] get_leagues failed: {e}")
        return []


def run(days_ahead=2, db_path=DB):
    """
    Nota: esta API solo tiene el endpoint de ligas funcionando.
    Los datos de partidos/scores vienen de api-sports.io (update_wc.py).
    """
    if not API_KEY:
        print("[live_football] APIFOOT not set — skipping")
        return 0
    print("[live_football] API solo tiene catálogo de ligas. Partidos → api-sports.io")
    return 0


if __name__ == "__main__":
    run()
