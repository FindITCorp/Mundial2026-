"""
fetch_team_matches.py — Fetch last 3 years of national team results per team.

Data sources:
  1. football-data.org (free: last 20 matches per team)
  2. api-football.com (fixtures endpoint)
  3. Falls back to existing DB data

Fetches for ALL 48 WC2026 teams.
Results stored in: DB table team_matches + cache files.
"""
import os
import json
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "matches"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

FD_BASE = "https://api.football-data.org/v4"
AF_BASE = "https://v3.football.api-sports.io"
FD_KEY  = os.getenv("FOOTBALL_DATA_KEY", "")
AF_KEY        = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

def _af_headers() -> dict:
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {"x-rapidapi-host": "v3.football.api-sports.io", "x-rapidapi-key": AF_KEY}

# Mapping team name -> football-data.org team ID
# These IDs are approximate; update with actual API lookup
TEAM_FD_IDS = {
    "Argentina": 762, "France": 773, "Brazil": 764, "England": 66,
    "Portugal": 765, "Belgium": 805, "Spain": 760, "Netherlands": 806,
    "Germany": 759, "Croatia": 799, "Switzerland": 788, "Mexico": 972,
    "Uruguay": 769, "Colombia": 771, "Italy": 784, "Denmark": 782,
    "Morocco": 1031, "Japan": 827, "USA": 768, "South Korea": 827,
    "Canada": 769, "Ecuador": 780, "Senegal": 907, "Australia": 834,
    "Poland": 794, "Serbia": 795, "Nigeria": 910, "Turkey": 802,
    "Saudi Arabia": 856, "Egypt": 904, "Austria": 816, "Panama": 977,
}

# Mapping team name -> api-football team ID (approximate)
TEAM_AF_IDS = {
    "Argentina": 26, "France": 2, "Brazil": 6, "England": 10,
    "Portugal": 27, "Belgium": 1, "Spain": 9, "Netherlands": 3,
    "Germany": 25, "Croatia": 1036, "Switzerland": 15, "Mexico": 16,
    "Uruguay": 26, "Colombia": 30, "Italy": 768, "Denmark": 21,
    "Morocco": 38, "Japan": 21, "USA": 2, "South Korea": 36,
    "Canada": 3, "Ecuador": 101, "Senegal": 34, "Australia": 25,
    "Poland": 24, "Serbia": 14, "Nigeria": 34, "Turkey": 29,
    "Saudi Arabia": 36, "Egypt": 34, "Austria": 11, "Panama": 15,
}


def get_cache_path(team_slug: str) -> Path:
    today = datetime.now().strftime("%Y%m%d")
    return CACHE_DIR / f"matches_{team_slug}_{today}.json"


def load_cache(team_slug: str) -> Optional[list]:
    p = get_cache_path(team_slug)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def save_cache(team_slug: str, data: list) -> None:
    p = get_cache_path(team_slug)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_matches_football_data(team_name: str, team_fd_id: int) -> Optional[list]:
    """Fetch team's recent matches from football-data.org."""
    if not FD_KEY or not team_fd_id:
        return None

    url = f"{FD_BASE}/teams/{team_fd_id}/matches"
    date_from = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    params = {"status": "FINISHED", "dateFrom": date_from, "limit": 50}
    headers = {"X-Auth-Token": FD_KEY}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            matches_raw = r.json().get("matches", [])
            return parse_fd_matches(matches_raw, team_name)
        elif r.status_code == 429:
            print(f"  [FD] Rate limit exceeded. Waiting...")
            time.sleep(60)
        else:
            print(f"  [FD] {team_name}: Error {r.status_code}")
    except Exception as e:
        print(f"  [FD] {team_name}: Exception {e}")
    return None


def parse_fd_matches(matches_raw: list, team_name: str) -> list:
    """Parse football-data.org match format into standard format."""
    result = []
    for m in matches_raw:
        home = m.get("homeTeam", {}).get("name", "")
        away = m.get("awayTeam", {}).get("name", "")
        score = m.get("score", {}).get("fullTime", {})
        home_score = score.get("home")
        away_score = score.get("away")

        if home_score is None or away_score is None:
            continue

        is_home = home.lower() == team_name.lower()
        opponent = away if is_home else home
        gf = home_score if is_home else away_score
        ga = away_score if is_home else home_score
        venue = "home" if is_home else "away"

        if gf > ga:
            res = "W"
        elif gf == ga:
            res = "D"
        else:
            res = "L"

        result.append({
            "opponent_name": opponent,
            "date": m.get("utcDate", "")[:10],
            "competition": m.get("competition", {}).get("name", "Unknown"),
            "goals_for": int(gf),
            "goals_against": int(ga),
            "result": res,
            "venue": venue,
        })

    return result


def fetch_matches_api_football(team_name: str, af_id: int) -> Optional[list]:
    """Fetch from api-football.com."""
    if not AF_KEY or not af_id:
        return None

    url = f"{AF_BASE}/fixtures"
    date_from = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    params = {
        "team": af_id,
        "from": date_from,
        "to": datetime.now().strftime("%Y-%m-%d"),
        "status": "FT",
    }
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": AF_KEY,
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            fixtures = r.json().get("response", [])
            return parse_af_matches(fixtures, team_name, af_id)
        print(f"  [AF] {team_name}: Error {r.status_code}")
    except Exception as e:
        print(f"  [AF] {team_name}: Exception {e}")
    return None


def parse_af_matches(fixtures: list, team_name: str, team_af_id: int) -> list:
    """Parse api-football.com fixture format."""
    result = []
    for f in fixtures:
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})

        home_team = teams.get("home", {})
        away_team = teams.get("away", {})
        is_home = home_team.get("id") == team_af_id

        opponent = away_team.get("name", "") if is_home else home_team.get("name", "")
        gf = goals.get("home") if is_home else goals.get("away")
        ga = goals.get("away") if is_home else goals.get("home")

        if gf is None or ga is None:
            continue

        if gf > ga:
            res = "W"
        elif gf == ga:
            res = "D"
        else:
            res = "L"

        result.append({
            "opponent_name": opponent,
            "date": fixture.get("date", "")[:10],
            "competition": f.get("league", {}).get("name", "Unknown"),
            "goals_for": int(gf),
            "goals_against": int(ga),
            "result": res,
            "venue": "home" if is_home else "away",
        })

    return result


def save_to_db(team_name: str, matches: list) -> int:
    """Insert match records into team_matches table."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    team_row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        conn.close()
        return 0

    team_id = team_row["id"]
    inserted = 0

    for m in matches:
        # Find opponent id
        opp_row = cur.execute(
            "SELECT id FROM teams WHERE name LIKE ?", (f"%{m['opponent_name'][:10]}%",)
        ).fetchone()
        opp_id = opp_row["id"] if opp_row else None

        # Avoid duplicates
        existing = cur.execute("""
            SELECT id FROM team_matches
            WHERE team_id=? AND opponent_name=? AND date=?
        """, (team_id, m["opponent_name"], m["date"])).fetchone()

        if not existing:
            cur.execute("""
                INSERT INTO team_matches
                    (team_id, opponent_id, opponent_name, date, competition,
                     goals_for, goals_against, result, venue)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                team_id, opp_id, m["opponent_name"], m["date"],
                m.get("competition", ""), m["goals_for"], m["goals_against"],
                m["result"], m.get("venue", "neutral")
            ))
            inserted += cur.rowcount

    conn.commit()
    conn.close()
    return inserted


def fetch_team_matches(team_name: str, team_slug: str) -> list:
    """
    Fetch match history for one team.
    Returns list of match dicts.
    """
    # Check cache first
    cached = load_cache(team_slug)
    if cached:
        print(f"  {team_name}: {len(cached)} matches (cache)")
        return cached

    matches = None

    # Try football-data.org
    fd_id = TEAM_FD_IDS.get(team_name)
    if fd_id and FD_KEY:
        matches = fetch_matches_football_data(team_name, fd_id)
        if matches:
            print(f"  {team_name}: {len(matches)} matches (football-data.org)")

    # Try api-football
    if not matches:
        af_id = TEAM_AF_IDS.get(team_name)
        if af_id and AF_KEY:
            matches = fetch_matches_api_football(team_name, af_id)
            if matches:
                print(f"  {team_name}: {len(matches)} matches (api-football)")

    if not matches:
        print(f"  {team_name}: no API data, using DB data only")
        return []

    save_cache(team_slug, matches)
    return matches


def run(teams: Optional[list] = None, delay_secs: float = 2.0):
    """
    Main pipeline entry point.
    If teams is None, fetch all teams from DB.
    """
    print("\n=== Pipeline: Fetch Team Matches ===\n")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if teams:
        db_teams = [{"name": t, "slug": t.lower().replace(" ", "_")} for t in teams]
    else:
        rows = conn.execute("SELECT name, slug FROM teams ORDER BY fifa_ranking").fetchall()
        db_teams = [{"name": r["name"], "slug": r["slug"]} for r in rows]

    conn.close()

    total_inserted = 0
    for i, t in enumerate(db_teams, 1):
        print(f"[{i}/{len(db_teams)}] {t['name']}")
        matches = fetch_team_matches(t["name"], t["slug"])
        if matches:
            n = save_to_db(t["name"], matches)
            total_inserted += n
            if n:
                print(f"    -> {n} nuevos partidos en DB")

        if FD_KEY or AF_KEY:
            time.sleep(delay_secs)  # rate limiting

    print(f"\nTotal partidos insertados: {total_inserted}")
    print("Pipeline team_matches completado.\n")
    return total_inserted


if __name__ == "__main__":
    import sys
    teams_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    run(teams=teams_arg)
