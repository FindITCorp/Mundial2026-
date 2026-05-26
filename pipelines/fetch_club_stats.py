"""
fetch_club_stats.py — Fetch club stats for all convoked players (last 3 seasons).

Data sources:
  1. api-football.com (player statistics endpoint)
  2. football-data.org

Stats stored in player_club_stats table.
Also updates player ratings in player_ratings table.
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
CACHE_DIR = BASE_DIR / "data" / "cache" / "club_stats"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

AF_BASE = "https://v3.football.api-sports.io"
AF_KEY        = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

# Global request counter to stay within daily quota
_request_count = 0
REQUEST_LIMIT  = 90  # leave buffer from 100/day

def _af_headers() -> dict:
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {"x-rapidapi-host": "v3.football.api-sports.io", "x-rapidapi-key": AF_KEY}

# Map league names to api-football league IDs
LEAGUE_AF_IDS = {
    "Premier League": 39,
    "La Liga": 140,
    "Bundesliga": 78,
    "Serie A": 135,
    "Ligue 1": 61,
    "Primeira Liga": 94,
    "Eredivisie": 88,
    "Pro League": 144,
    "Scottish Prem": 179,
    "MLS": 253,
    "Brasileirao": 71,
    "Liga MX": 262,
    "J1 League": 98,
    "K League 1": 292,
    "Super League Greece": 197,
    "Saudi Pro League": 307,
    "Austrian Bundesliga": 218,
    "Swiss Super League": 207,
    "Turkish Süper Lig": 203,
    "Süper Lig": 203,
    "HNL": 210,
    "OTP Bank Liga": 271,
    "Egyptian Premier League": 233,
    "IPL": 290,  # Iranian Premier League
    "Champions League": 2,
}

SEASONS = [2023, 2024, 2025]


def get_cache_path(player_id: int, season: int) -> Path:
    return CACHE_DIR / f"player_{player_id}_season_{season}.json"


def load_cache(player_id: int, season: int) -> Optional[dict]:
    p = get_cache_path(player_id, season)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def save_cache(player_id: int, season: int, data: dict) -> None:
    p = get_cache_path(player_id, season)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_player_stats_af(player_name: str, club: str, season: int) -> Optional[dict]:
    """Fetch player stats from api-football for a given season."""
    global _request_count
    if not (APISPORTS_KEY or AF_KEY):
        return None
    if _request_count >= REQUEST_LIMIT:
        return None

    headers = _af_headers()
    search_url = f"{AF_BASE}/players"
    params = {"search": player_name[:15], "season": season}

    try:
        r = requests.get(search_url, headers=headers, params=params, timeout=15)
        _request_count += 1

        if r.status_code == 429:
            print(f"  [AF] Rate limit hit after {_request_count} requests")
            _request_count = REQUEST_LIMIT  # stop further calls
            return None
        if r.status_code != 200:
            return None

        players = r.json().get("response", [])
        for p in players:
            player_data = p.get("player", {})
            if player_name.lower() in player_data.get("name", "").lower():
                stats = p.get("statistics", [])
                if stats:
                    return parse_af_stats(stats[0], season)

    except Exception as e:
        print(f"  [AF] Stats error for {player_name}: {e}")

    return None


def parse_af_stats(stat: dict, season: int) -> dict:
    """Parse api-football statistics object."""
    games = stat.get("games", {})
    goals = stat.get("goals", {})
    passes = stat.get("passes", {})
    tackles = stat.get("tackles", {})
    dribbles = stat.get("dribbles", {})
    shots = stat.get("shots", {})
    cards = stat.get("cards", {})

    matches = games.get("appearences") or 0
    minutes = games.get("minutes") or 0
    pass_acc = passes.get("accuracy") or 0.0
    if isinstance(pass_acc, str):
        try:
            pass_acc = float(pass_acc.replace("%", ""))
        except Exception:
            pass_acc = 0.0

    xg_val = 0.0
    expected = stat.get("expected", {})
    if expected:
        xg_val = float(expected.get("goals") or 0.0)
    if not xg_val:
        xg_val = float(goals.get("expected") or 0.0)

    return {
        "season": f"{season}/{str(season+1)[-2:]}",
        "league": stat.get("league", {}).get("name", "Unknown"),
        "club": stat.get("team", {}).get("name", "Unknown"),
        "matches": int(matches),
        "minutes": int(minutes),
        "goals": int(goals.get("total") or 0),
        "assists": int(goals.get("assists") or 0),
        "shots_on_target": int(shots.get("on") or 0),
        "pass_accuracy": float(pass_acc),
        "dribbles_completed": int(dribbles.get("success") or 0),
        "tackles": int(tackles.get("total") or 0),
        "interceptions": int(tackles.get("interceptions") or 0),
        "yellow_cards": int(cards.get("yellow") or 0),
        "red_cards": int(cards.get("red") or 0),
        "xg": xg_val,
    }


def synthesize_stats_from_profile(player_row: sqlite3.Row) -> Optional[dict]:
    """
    When API is not available, synthesize plausible stats from player profile.
    Used as fallback to enable rating computation.
    """
    pos = player_row["position"] or "MID"
    caps = player_row["caps"] or 0
    goals_nat = player_row["goals_as_nat"] or 0
    age = player_row["age"] or 25
    league = player_row["club_league"] or ""

    # Estimate matches played (typical season)
    matches = 30 if "Premier League" in league or "La Liga" in league else 25

    # Goals per match based on position and known nat performance
    if pos == "GK":
        goals_per_match = 0
        assists_per_match = 0
        tackle_per_match = 0.5
        inter_per_match = 1.2
    elif pos == "DEF":
        goals_per_match = 0.05
        assists_per_match = 0.1
        tackle_per_match = 2.5
        inter_per_match = 1.8
    elif pos == "MID":
        goals_per_match = 0.15 + (goals_nat / max(1, caps)) * 0.5
        assists_per_match = 0.2
        tackle_per_match = 1.5
        inter_per_match = 1.0
    else:  # FWD
        gpc = goals_nat / max(1, caps)
        goals_per_match = min(0.8, gpc * 1.2)
        assists_per_match = 0.15
        tackle_per_match = 0.3
        inter_per_match = 0.2

    # League-based pass accuracy
    league_pa = {
        "Premier League": 82, "La Liga": 85, "Bundesliga": 83, "Serie A": 84,
        "Ligue 1": 82, "Primeira Liga": 80, "Eredivisie": 81,
        "MLS": 76, "Liga MX": 78, "J1 League": 77, "K League 1": 75,
    }
    pa = 75.0
    for k, v in league_pa.items():
        if k.lower() in league.lower():
            pa = float(v)
            break

    # Add position-specific pass accuracy offsets
    if pos == "GK":
        pa = max(65.0, pa - 8)
    elif pos == "FWD":
        pa = max(68.0, pa - 5)
    elif pos == "DEF":
        pa = min(92.0, pa + 3)

    season_goals = int(goals_per_match * matches)
    season_assists = max(0, int(assists_per_match * matches))
    sot = int(season_goals * 2.2) if pos == "FWD" else int(season_goals * 1.5)

    return {
        "season": "2024/25",
        "league": player_row["club_league"] or "Unknown",
        "club": player_row["club"] or "Unknown",
        "matches": matches,
        "minutes": int(matches * 82),  # average ~82 min per match
        "goals": season_goals,
        "assists": season_assists,
        "shots_on_target": sot,
        "pass_accuracy": pa,
        "dribbles_completed": int(matches * (0.8 if pos == "FWD" else 0.3)),
        "tackles": int(matches * tackle_per_match),
        "interceptions": int(matches * inter_per_match),
        "yellow_cards": 2 if pos in ("DEF", "MID") else 1,
        "red_cards": 0,
    }


def save_stats_to_db(player_id: int, stats: dict) -> bool:
    """Insert/update player_club_stats record."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO player_club_stats
            (player_id, season, league, club, matches, minutes, goals, assists,
             shots_on_target, pass_accuracy, dribbles_completed, tackles,
             interceptions, yellow_cards, red_cards, xg)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        player_id,
        stats["season"], stats["league"], stats["club"],
        stats["matches"], stats["minutes"], stats["goals"], stats["assists"],
        stats["shots_on_target"], stats["pass_accuracy"],
        stats["dribbles_completed"], stats["tackles"],
        stats["interceptions"], stats["yellow_cards"], stats["red_cards"],
        stats.get("xg", 0.0),
    ))
    conn.commit()
    conn.close()
    return True


def process_team_players(team_name: str, use_api: bool = True, force_refresh: bool = False) -> int:
    """Process all players for a team, fetching/synthesizing club stats.
    force_refresh=True: re-fetch players that only have synthetic data (xg=0).
    """
    global _request_count
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    team_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not team_row:
        conn.close()
        return 0

    team_id = team_row["id"]
    players = conn.execute("""
        SELECT p.* FROM players p
        JOIN squad_selections ss ON ss.player_id = p.id
        WHERE ss.team_id = ?
    """, (team_id,)).fetchall()
    conn.close()

    processed = 0
    for p in players:
        if _request_count >= REQUEST_LIMIT:
            print(f"  [LIMIT] Reached {REQUEST_LIMIT} API requests, stopping.")
            break

        player_id = p["id"]
        player_name = p["name"]

        conn2 = sqlite3.connect(DB_PATH)
        existing = conn2.execute(
            "SELECT id, xg FROM player_club_stats WHERE player_id=? LIMIT 1",
            (player_id,)
        ).fetchone()
        conn2.close()

        # Skip only if already has real data (xg > 0)
        if existing and (existing["xg"] or 0) > 0:
            continue

        # If force_refresh and synthetic exists, delete it so we can insert fresh
        if existing and force_refresh:
            conn3 = sqlite3.connect(DB_PATH)
            conn3.execute("DELETE FROM player_club_stats WHERE player_id=?", (player_id,))
            conn3.commit()
            conn3.close()

        stats = None

        if use_api and (APISPORTS_KEY or AF_KEY) and _request_count < REQUEST_LIMIT:
            stats = fetch_player_stats_af(player_name, p["club"] or "", 2024)
            if stats:
                print(f"    [API] {player_name}: {stats['goals']}G {stats['assists']}A xG:{stats.get('xg',0):.2f}")
            time.sleep(0.5)

        if not stats:
            stats = synthesize_stats_from_profile(p)

        if stats:
            save_stats_to_db(player_id, stats)
            processed += 1

    return processed


def run(teams: Optional[list] = None, force_refresh: bool = False):
    """Main pipeline entry point.
    force_refresh=True: re-fetch players with only synthetic data (xg=0).
    """
    global _request_count
    _request_count = 0
    print("\n=== Pipeline: Fetch Club Stats ===\n")
    print(f"Mode: {'force_refresh (replace synthetic)' if force_refresh else 'fill missing only'}")
    print(f"API request limit: {REQUEST_LIMIT}/day\n")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if teams:
        db_teams = [{"name": t} for t in teams]
    else:
        rows = conn.execute("SELECT name FROM teams ORDER BY fifa_ranking").fetchall()
        db_teams = [{"name": r["name"]} for r in rows]
    conn.close()

    total = 0
    for i, t in enumerate(db_teams, 1):
        if _request_count >= REQUEST_LIMIT:
            print(f"\n[LIMIT] Reached {REQUEST_LIMIT} requests — stopping after {i-1} teams.")
            break
        print(f"[{i}/{len(db_teams)}] {t['name']}  (requests used: {_request_count}/{REQUEST_LIMIT})")
        n = process_team_players(t["name"],
                                 use_api=bool(APISPORTS_KEY or AF_KEY),
                                 force_refresh=force_refresh)
        total += n
        if n:
            print(f"    -> {n} jugadores actualizados")

    conn = sqlite3.connect(DB_PATH)
    real = conn.execute("SELECT COUNT(*) FROM player_club_stats WHERE xg > 0").fetchone()[0]
    total_stats = conn.execute("SELECT COUNT(*) FROM player_club_stats").fetchone()[0]
    conn.close()

    print(f"\nAPI requests usados: {_request_count}")
    print(f"Con xG real: {real}/{total_stats}")
    print("Pipeline club_stats completado.\n")
    return total


if __name__ == "__main__":
    import sys
    teams_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    run(teams=teams_arg)
