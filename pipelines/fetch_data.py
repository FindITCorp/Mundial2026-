"""
Fetches team stats, H2H history, and player data from football-data.org and API-Football.
Run: python pipelines/fetch_data.py
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

HEADERS_FD = {"X-Auth-Token": os.getenv("FOOTBALL_DATA_API_KEY", "")}
HEADERS_AF = {
    "x-rapidapi-host": "v3.football.api-sports.io",
    "x-rapidapi-key": os.getenv("API_FOOTBALL_KEY", ""),
}

WORLD_CUP_2026_ID = 1  # football-data.org competition ID (actualizar cuando esté disponible)
WC_2026_AF_ID = 1      # api-football ID del Mundial 2026 (actualizar)


def save(name: str, data: dict):
    path = RAW_DIR / f"{name}_{datetime.now().strftime('%Y%m%d')}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Guardado: {path}")
    return data


def fetch_wc_teams():
    """Equipos clasificados al Mundial 2026 con estadísticas."""
    print("Fetching equipos clasificados...")
    # football-data.org — equipos del torneo
    r = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/WC/teams", headers=HEADERS_FD, timeout=10)
    if r.status_code == 200:
        save("wc_teams", r.json())
        return r.json()
    print(f"  Error {r.status_code}: {r.text[:200]}")
    return {}


def fetch_team_matches(team_id: int, team_name: str):
    """Últimos 20 partidos de una selección."""
    print(f"Fetching historial {team_name}...")
    params = {"teams": team_id, "limit": 20}
    r = requests.get(f"{FOOTBALL_DATA_BASE}/matches", headers=HEADERS_FD, params=params, timeout=10)
    if r.status_code == 200:
        save(f"matches_{team_name.lower().replace(' ', '_')}", r.json())
        return r.json()
    print(f"  Error {r.status_code}")
    return {}


def fetch_h2h(team1_id: int, team2_id: int, label: str):
    """Historial de encuentros directos entre dos selecciones."""
    print(f"Fetching H2H {label}...")
    params = {"competitions": "WC,EC,CA,CN,WCQ", "limit": 10}
    r = requests.get(
        f"{FOOTBALL_DATA_BASE}/teams/{team1_id}/matches",
        headers=HEADERS_FD, params=params, timeout=10
    )
    if r.status_code == 200:
        matches = r.json().get("matches", [])
        h2h = [m for m in matches if str(team2_id) in [
            str(m.get("homeTeam", {}).get("id")),
            str(m.get("awayTeam", {}).get("id"))
        ]]
        save(f"h2h_{label}", {"matches": h2h})
        return h2h
    return []


def fetch_players_stats(team_id: int, team_name: str):
    """Estadísticas por jugador vía API-Football."""
    print(f"Fetching jugadores {team_name}...")
    params = {"team": team_id, "season": 2025, "league": WC_2026_AF_ID}
    r = requests.get(f"{API_FOOTBALL_BASE}/players", headers=HEADERS_AF, params=params, timeout=10)
    if r.status_code == 200:
        save(f"players_{team_name.lower().replace(' ', '_')}", r.json())
        return r.json()
    print(f"  Error {r.status_code}")
    return {}


def fetch_news(query: str):
    """Noticias recientes sobre una selección o partido."""
    print(f"Fetching noticias: {query}...")
    NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
    if not NEWS_API_KEY:
        print("  Sin NEWS_API_KEY, saltando noticias.")
        return {}
    r = requests.get(
        "https://newsapi.org/v2/everything",
        params={"q": query, "language": "es", "sortBy": "publishedAt", "pageSize": 20, "apiKey": NEWS_API_KEY},
        timeout=10
    )
    if r.status_code == 200:
        save(f"news_{query.lower().replace(' ', '_')[:30]}", r.json())
        return r.json()
    return {}


if __name__ == "__main__":
    print("=== Actualizando datos Mundial 2026 ===\n")
    fetch_wc_teams()
    # fetch_news("mundial 2026 selecciones")
    print("\nListo. Datos guardados en data/raw/")
