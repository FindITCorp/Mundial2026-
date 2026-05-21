"""
fetch_players.py — Fetch squad lists and player profiles per team.

Data sources:
  1. api-football.com (squad endpoint)
  2. football-data.org (squad endpoint)
  3. Falls back to existing DB data (seeded in setup_db.py)

All results saved to DB (players table + squad_selections).
"""
import os
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "players"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

AF_BASE = "https://v3.football.api-sports.io"
FD_BASE = "https://api.football-data.org/v4"
AF_KEY  = os.getenv("API_FOOTBALL_KEY", "")
FD_KEY  = os.getenv("FOOTBALL_DATA_API_KEY", "")

# AF team IDs for national teams
TEAM_AF_IDS = {
    "Argentina": 26, "France": 2, "Brazil": 6, "England": 10,
    "Portugal": 27, "Belgium": 1, "Spain": 9, "Netherlands": 3,
    "Germany": 25, "Croatia": 1036, "Switzerland": 15, "Mexico": 16,
    "Uruguay": 26, "Colombia": 30, "Italy": 768, "Denmark": 21,
    "Morocco": 38, "Japan": 21, "USA": 2, "South Korea": 36,
    "Canada": 3, "Ecuador": 101, "Senegal": 34, "Australia": 25,
    "Poland": 24, "Serbia": 14, "Nigeria": 34, "Turkey": 29,
    "Saudi Arabia": 36, "Egypt": 34, "Austria": 11, "Panama": 15,
    "Panama": 69, "Honduras": 63, "Jamaica": 69, "Bolivia": 701,
    "Paraguay": 678, "Venezuela": 18, "Ghana": 640, "Hungary": 769,
    "Scotland": 1108, "Romania": 774, "DR Congo": 640, "Cameroon": 1039,
    "Slovenia": 1091, "Costa Rica": 65, "Jordan": 845, "Iraq": 845,
}

FD_TEAM_IDS = {
    "England": 66, "Germany": 759, "Spain": 760, "France": 773,
    "Brazil": 764, "Argentina": 762, "Portugal": 765, "Netherlands": 806,
    "Belgium": 805, "Croatia": 799, "Switzerland": 788, "Mexico": 972,
    "Uruguay": 769, "Colombia": 771, "Italy": 784, "Denmark": 782,
}

POSITION_MAP = {
    "Goalkeeper": "GK",
    "Defender": "DEF",
    "Midfielder": "MID",
    "Attacker": "FWD",
    "Forward": "FWD",
    "G": "GK", "D": "DEF", "M": "MID", "F": "FWD",
}


def cache_path(name: str) -> Path:
    today = datetime.now().strftime("%Y%m%d")
    return CACHE_DIR / f"{name}_{today}.json"


def load_cache(name: str) -> Optional[list]:
    p = cache_path(name)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def save_cache(name: str, data) -> None:
    p = cache_path(name)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_squad_api_football(team_name: str, af_id: int) -> Optional[list]:
    """Fetch squad from api-football.com."""
    if not AF_KEY:
        return None

    cache_key = f"squad_af_{team_name.lower().replace(' ', '_')}"
    cached = load_cache(cache_key)
    if cached:
        return cached

    url = f"{AF_BASE}/players/squads"
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": AF_KEY,
    }
    params = {"team": af_id}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            resp = r.json().get("response", [])
            if resp:
                players = resp[0].get("players", [])
                save_cache(cache_key, players)
                return players
        print(f"  [AF] {team_name}: squad error {r.status_code}")
    except Exception as e:
        print(f"  [AF] {team_name}: {e}")
    return None


def fetch_squad_football_data(team_name: str, fd_id: int) -> Optional[list]:
    """Fetch squad from football-data.org."""
    if not FD_KEY:
        return None

    cache_key = f"squad_fd_{team_name.lower().replace(' ', '_')}"
    cached = load_cache(cache_key)
    if cached:
        return cached

    url = f"{FD_BASE}/teams/{fd_id}"
    headers = {"X-Auth-Token": FD_KEY}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            squad = r.json().get("squad", [])
            save_cache(cache_key, squad)
            return squad
        print(f"  [FD] {team_name}: squad error {r.status_code}")
    except Exception as e:
        print(f"  [FD] {team_name}: {e}")
    return None


def parse_af_player(p: dict) -> dict:
    """Parse api-football player object."""
    pos_raw = p.get("position", "Midfielder")
    position = POSITION_MAP.get(pos_raw, "MID")
    age = p.get("age") or 0
    if not age and p.get("birth"):
        birth_year = int(p["birth"].get("date", "2000-01-01")[:4])
        age = datetime.now().year - birth_year

    return {
        "name": p.get("name", ""),
        "position": position,
        "age": age,
        "club": p.get("club", "") or "",
        "number": p.get("number") or 0,
    }


def parse_fd_player(p: dict) -> dict:
    """Parse football-data.org player object."""
    pos_raw = p.get("position", "Midfielder")
    position = POSITION_MAP.get(pos_raw, "MID")
    dob = p.get("dateOfBirth", "")
    age = 0
    if dob:
        try:
            age = datetime.now().year - int(dob[:4])
        except Exception:
            pass

    return {
        "name": p.get("name", ""),
        "position": position,
        "age": age,
        "club": p.get("currentTeam", {}).get("name", "") if isinstance(p.get("currentTeam"), dict) else "",
        "number": p.get("shirtNumber") or 0,
    }


def save_players_to_db(team_name: str, players: list) -> tuple[int, int]:
    """
    Save players to DB. Returns (inserted, updated) counts.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    team_row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        conn.close()
        return 0, 0

    team_id = team_row["id"]
    inserted = 0
    updated = 0

    for p in players:
        name = p.get("name", "").strip()
        if not name:
            continue

        position = p.get("position", "MID")
        age = p.get("age", 0)
        club = p.get("club", "")

        # Check if player exists
        existing = cur.execute("""
            SELECT id FROM players WHERE name=? AND team_id=?
        """, (name, team_id)).fetchone()

        if existing:
            cur.execute("""
                UPDATE players SET position=?, age=?, club=?
                WHERE id=?
            """, (position, age, club, existing["id"]))
            player_id = existing["id"]
            updated += 1
        else:
            cur.execute("""
                INSERT INTO players (name, team_id, position, age, club)
                VALUES (?,?,?,?,?)
            """, (name, team_id, position, age, club))
            player_id = cur.lastrowid
            inserted += 1

        # Add to squad selections
        cur.execute("""
            INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed, shirt_number)
            VALUES (?,?,1,?)
        """, (team_id, player_id, p.get("number", 0)))

    conn.commit()
    conn.close()
    return inserted, updated


def fetch_team_squad(team_name: str) -> list:
    """
    Try to fetch squad from APIs, return list of player dicts.
    """
    players = []

    # Try api-football first
    af_id = TEAM_AF_IDS.get(team_name)
    if af_id and AF_KEY:
        raw = fetch_squad_api_football(team_name, af_id)
        if raw:
            players = [parse_af_player(p) for p in raw]
            print(f"  {team_name}: {len(players)} jugadores (api-football)")
            return players
        time.sleep(1)

    # Try football-data
    fd_id = FD_TEAM_IDS.get(team_name)
    if fd_id and FD_KEY:
        raw = fetch_squad_football_data(team_name, fd_id)
        if raw:
            players = [parse_fd_player(p) for p in raw]
            print(f"  {team_name}: {len(players)} jugadores (football-data.org)")
            return players

    print(f"  {team_name}: sin API disponible, usando datos del DB")
    return []


def run(teams: Optional[list] = None, delay_secs: float = 1.5):
    """Main pipeline entry point."""
    print("\n=== Pipeline: Fetch Players ===\n")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if teams:
        db_teams = [{"name": t} for t in teams]
    else:
        rows = conn.execute("SELECT name FROM teams ORDER BY fifa_ranking").fetchall()
        db_teams = [{"name": r["name"]} for r in rows]
    conn.close()

    total_inserted = 0
    total_updated = 0

    for i, t in enumerate(db_teams, 1):
        print(f"[{i}/{len(db_teams)}] {t['name']}")
        players = fetch_team_squad(t["name"])

        if players:
            ins, upd = save_players_to_db(t["name"], players)
            total_inserted += ins
            total_updated += upd
            print(f"    -> {ins} nuevos, {upd} actualizados")

        if AF_KEY or FD_KEY:
            time.sleep(delay_secs)

    # Summary
    conn = sqlite3.connect(DB_PATH)
    player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    squad_count = conn.execute("SELECT COUNT(*) FROM squad_selections").fetchone()[0]
    conn.close()

    print(f"\nTotal jugadores insertados: {total_inserted}")
    print(f"Total actualizados: {total_updated}")
    print(f"Total en DB: {player_count} jugadores, {squad_count} convocatorias")
    print("Pipeline players completado.\n")
    return total_inserted


if __name__ == "__main__":
    import sys
    teams_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    run(teams=teams_arg)
