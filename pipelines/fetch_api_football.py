"""
fetch_api_football.py — Complete pipeline using API-Football (RapidAPI).

Handles 100 req/day free tier with smart rate limiting and caching.
All responses cached to data/cache/ (skipped if cache < 24h old).

Usage:
  python pipelines/fetch_api_football.py --squad "Panama"
  python pipelines/fetch_api_football.py --player-stats 622 2025 140
  python pipelines/fetch_api_football.py --fixtures 1887
  python pipelines/fetch_api_football.py --h2h 1887 3
  python pipelines/fetch_api_football.py --lineup 1001
"""
import os
import json
import time
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR   = Path(__file__).parent.parent
CACHE_DIR  = BASE_DIR / "data" / "cache" / "api_football"
DB_PATH    = BASE_DIR / "data" / "mundial2026.db"
LOG_PATH   = BASE_DIR / "data" / "cache" / "api_calls_log.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

AF_KEY       = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

# Use api-sports.io direct endpoint when APISPORTS_KEY is set; fall back to RapidAPI
AF_BASE  = "https://v3.football.api-sports.io"
AF_BASE_RAPID = "https://api-football-v1.p.rapidapi.com/v3"
AF_HOST  = "api-football-v1.p.rapidapi.com"

# Active API base URL depends on which key is available
API_BASE = AF_BASE if APISPORTS_KEY else AF_BASE_RAPID


def _af_headers() -> dict:
    """Return correct auth headers: direct api-sports.io or RapidAPI fallback."""
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {
        "x-rapidapi-host": AF_HOST,
        "x-rapidapi-key": AF_KEY,
    }


def _has_api_key() -> bool:
    """Return True if at least one API key is configured."""
    return bool(APISPORTS_KEY or AF_KEY)

DAILY_LIMIT = 100  # Free tier limit

# ── Team ID mapping: our team names → API-Football team IDs ─────────────────
TEAM_API_IDS = {
    "Argentina":    26,
    "France":       2,
    "Brazil":       6,
    "Germany":      25,
    "Spain":        9,
    "England":      10,
    "Portugal":     27,
    "Netherlands":  1118,
    "Mexico":       16,
    "USA":          2,        # Note: USA shares ID 2 with France in some contexts
    "Croatia":      3,
    "Panama":       1887,
    "Morocco":      1947,
    "Japan":        23,
    "Senegal":      38,
    "Belgium":      1,
    "Switzerland":  15,
    "Colombia":     30,
    "Uruguay":      26,
    "Italy":        768,
    "Denmark":      21,
    "South Korea":  36,
    "Canada":       94,
    "Ecuador":      101,
    "Australia":    25,
    "Poland":       24,
    "Serbia":       14,
    "Nigeria":      34,
    "Turkey":       29,
    "Saudi Arabia": 36,
    "Egypt":        34,
    "Austria":      11,
    "Honduras":     63,
    "Jamaica":      69,
    "Bolivia":      701,
    "Paraguay":     678,
    "Venezuela":    18,
    "Ghana":        640,
    "Hungary":      769,
    "Scotland":     1108,
    "Romania":      774,
    "DR Congo":     640,
    "Cameroon":     1039,
    "Slovenia":     1091,
    "Costa Rica":   65,
    "Jordan":       845,
    "Iraq":         3027,
    "New Zealand":  826,
    "Algeria":      1569,
    "Mali":         1572,
    "Ivory Coast":  1567,
    "Chile":        21,
    "Peru":         19,
    "Cuba":         1925,
    "Guatemala":    1937,
    "Trinidad & Tobago": 1912,
    "El Salvador":  1904,
    "Qatar":        55,
    "South Africa": 664,
    "Tunisia":      1585,
    "Burkina Faso": 1578,
    "Zambia":       1636,
    "Mozambique":   1625,
    "Uzbekistan":   1566,
    "Indonesia":    1350,
    "Philippines":  1393,
    "China":        1029,
    "Bahrain":      1339,
    "Kuwait":       1363,
    "Oman":         1378,
    "Palestine":    1382,
    "Thailand":     1402,
}


# ── API call log management ──────────────────────────────────────────────────

def _load_call_log() -> dict:
    """Load or initialize API call log."""
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"calls": [], "total_today": 0, "last_reset": datetime.now().strftime("%Y-%m-%d")}


def _save_call_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def _get_calls_today() -> int:
    """Return number of API calls made today."""
    log = _load_call_log()
    today = datetime.now().strftime("%Y-%m-%d")
    # Reset if new day
    if log.get("last_reset") != today:
        log["calls"] = []
        log["total_today"] = 0
        log["last_reset"] = today
        _save_call_log(log)
        return 0
    return log.get("total_today", 0)


def _record_call(endpoint: str) -> None:
    """Record an API call in the log."""
    log = _load_call_log()
    today = datetime.now().strftime("%Y-%m-%d")
    if log.get("last_reset") != today:
        log["calls"] = []
        log["total_today"] = 0
        log["last_reset"] = today
    log["calls"].append({
        "endpoint": endpoint,
        "timestamp": datetime.now().isoformat(),
    })
    log["total_today"] = len(log["calls"])
    _save_call_log(log)


def _can_make_call(reserve: int = 5) -> bool:
    """Check if we can make another API call (respects daily limit)."""
    used = _get_calls_today()
    remaining = DAILY_LIMIT - used - reserve
    if remaining <= 0:
        print(f"  [AF] LIMITE DIARIO ALCANZADO: {used}/{DAILY_LIMIT} llamadas usadas hoy.")
        return False
    return True


# ── Cache management ─────────────────────────────────────────────────────────

def _cache_file(key: str) -> Path:
    """Return cache file path for a given key."""
    safe_key = key.replace("/", "_").replace(" ", "_").replace("?", "_")
    return CACHE_DIR / f"{safe_key}.json"


def _cache_valid(key: str, max_age_hours: float = 24.0) -> bool:
    """Check if cache exists and is fresh enough."""
    p = _cache_file(key)
    if not p.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age < timedelta(hours=max_age_hours)


def _load_cache(key: str) -> Optional[dict]:
    p = _cache_file(key)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_cache(key: str, data) -> None:
    p = _cache_file(key)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Core HTTP request ─────────────────────────────────────────────────────────

def _api_get(endpoint: str, params: dict, cache_key: str,
             max_age_hours: float = 24.0) -> Optional[dict]:
    """
    Make an API-Football GET request with caching and rate limiting.
    Returns the full JSON response or None on error.
    """
    # Check cache first
    if _cache_valid(cache_key, max_age_hours):
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached

    # Check API key availability
    if not _has_api_key():
        print(f"  [AF] Sin API key (APISPORTS_KEY y APIFOOT no configurados)")
        return None

    if not _can_make_call():
        return None

    url = f"{API_BASE}/{endpoint}"
    headers = _af_headers()

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        _record_call(endpoint)

        if r.status_code == 200:
            data = r.json()
            _save_cache(cache_key, data)
            # api-sports.io uses x-ratelimit-requests-remaining; RapidAPI uses X-RateLimit-Requests-Remaining
            remaining_calls = (
                r.headers.get("x-ratelimit-requests-remaining")
                or r.headers.get("X-RateLimit-Requests-Remaining", "?")
            )
            print(f"  [AF] {endpoint}: OK (calls remaining today: {remaining_calls})")
            return data
        elif r.status_code == 429:
            print(f"  [AF] Rate limit hit. Waiting 60s...")
            time.sleep(60)
        else:
            print(f"  [AF] Error {r.status_code} for {endpoint}: {r.text[:200]}")
    except Exception as e:
        print(f"  [AF] Exception calling {endpoint}: {e}")

    return None


# ── Public functions ──────────────────────────────────────────────────────────

def fetch_squad(team_id: int, season: int = 2026) -> Optional[list]:
    """
    Fetch official squad/convocados for a team.

    Args:
        team_id: API-Football team ID
        season: Year (default 2026 for WC)

    Returns:
        List of player dicts or None if unavailable
    """
    cache_key = f"squad_{team_id}_{season}"
    data = _api_get("players/squads", {"team": team_id}, cache_key)
    if not data:
        return None

    response = data.get("response", [])
    if not response:
        return None

    players = []
    for entry in response:
        for p in entry.get("players", []):
            pos_raw = p.get("position", "Midfielder")
            position = {
                "Goalkeeper": "GK",
                "Defender": "DEF",
                "Midfielder": "MID",
                "Attacker": "FWD",
                "Forward": "FWD",
            }.get(pos_raw, "MID")

            age = p.get("age", 0)
            if not age and p.get("birth", {}).get("date"):
                try:
                    age = datetime.now().year - int(p["birth"]["date"][:4])
                except Exception:
                    age = 0

            players.append({
                "api_id": p.get("id"),
                "name": p.get("name", ""),
                "position": position,
                "age": age,
                "number": p.get("number", 0),
                "nationality": p.get("nationality", ""),
                "height": p.get("height", ""),
                "weight": p.get("weight", ""),
            })

    return players


def fetch_player_stats(player_id: int, season: int, league_id: int) -> Optional[dict]:
    """
    Fetch club stats for a single player in a given season/league.

    Args:
        player_id: API-Football player ID
        season: Season year (e.g., 2024 = 2024/25)
        league_id: API-Football league ID

    Returns:
        Dict with stats or None
    """
    cache_key = f"player_stats_{player_id}_{season}_{league_id}"
    data = _api_get(
        "players",
        {"id": player_id, "season": season, "league": league_id},
        cache_key,
    )
    if not data:
        return None

    response = data.get("response", [])
    if not response:
        return None

    entry = response[0]
    player = entry.get("player", {})
    stats_list = entry.get("statistics", [{}])
    stats = stats_list[0] if stats_list else {}

    games = stats.get("games", {})
    goals = stats.get("goals", {})
    passes = stats.get("passes", {})
    tackles = stats.get("tackles", {})
    shots = stats.get("shots", {})

    return {
        "player_id": player_id,
        "player_name": player.get("name", ""),
        "season": season,
        "league_id": league_id,
        "matches": games.get("appearences", 0) or 0,
        "minutes": games.get("minutes", 0) or 0,
        "goals": goals.get("total", 0) or 0,
        "assists": goals.get("assists", 0) or 0,
        "shots_on_target": shots.get("on", 0) or 0,
        "pass_accuracy": passes.get("accuracy", 0.0) or 0.0,
        "tackles": (tackles.get("total", 0) or 0),
        "interceptions": (tackles.get("interceptions", 0) or 0),
        "yellow_cards": (stats.get("cards", {}).get("yellow", 0) or 0),
        "red_cards": (stats.get("cards", {}).get("red", 0) or 0),
        "rating": float(games.get("rating", 0) or 0),
    }


def fetch_team_fixtures(team_id: int, last: int = 20) -> Optional[list]:
    """
    Fetch last N national team matches.

    Args:
        team_id: API-Football team ID
        last: Number of recent fixtures to fetch (default 20)

    Returns:
        List of match dicts or None
    """
    cache_key = f"fixtures_team_{team_id}_last{last}"
    data = _api_get(
        "fixtures",
        {"team": team_id, "last": last},
        cache_key,
    )
    if not data:
        return None

    matches = []
    for f in data.get("response", []):
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        league = f.get("league", {})

        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0

        is_home = (home_id == team_id)
        goals_for = home_goals if is_home else away_goals
        goals_against = away_goals if is_home else home_goals
        opponent_id = away_id if is_home else home_id
        opponent_name = (teams.get("away", {}).get("name", "") if is_home
                         else teams.get("home", {}).get("name", ""))

        result = "D"
        if goals_for > goals_against:
            result = "W"
        elif goals_for < goals_against:
            result = "L"

        matches.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date", "")[:10],
            "competition": league.get("name", ""),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "opponent_id": opponent_id,
            "opponent_name": opponent_name,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "result": result,
            "venue": "home" if is_home else "away",
            "status": fixture.get("status", {}).get("short", ""),
        })

    return matches


def fetch_head_to_head(team1_id: int, team2_id: int, last: int = 15) -> Optional[list]:
    """
    Fetch head-to-head history between two teams.

    Args:
        team1_id: First team API-Football ID
        team2_id: Second team API-Football ID
        last: Max number of H2H matches to fetch

    Returns:
        List of match dicts or None
    """
    cache_key = f"h2h_{min(team1_id,team2_id)}_{max(team1_id,team2_id)}_last{last}"
    data = _api_get(
        "fixtures/headtohead",
        {"h2h": f"{team1_id}-{team2_id}", "last": last},
        cache_key,
    )
    if not data:
        return None

    matches = []
    for f in data.get("response", []):
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        league = f.get("league", {})

        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0

        is_t1_home = (home_id == team1_id)
        t1_goals = home_goals if is_t1_home else away_goals
        t2_goals = away_goals if is_t1_home else home_goals

        if t1_goals > t2_goals:
            result = "W"  # team1 wins
        elif t1_goals < t2_goals:
            result = "L"  # team1 loses
        else:
            result = "D"

        matches.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date", "")[:10],
            "competition": league.get("name", ""),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "team1_goals": t1_goals,
            "team2_goals": t2_goals,
            "result_for_team1": result,
            "status": fixture.get("status", {}).get("short", ""),
        })

    return matches


def fetch_live_lineups(fixture_id: int) -> Optional[dict]:
    """
    Fetch confirmed lineup for a WC match.
    Best called after kickoff when lineups are officially published.

    Args:
        fixture_id: API-Football fixture ID

    Returns:
        Dict with home/away lineups or None
    """
    # Live lineups should be refreshed more frequently (2h cache)
    cache_key = f"lineups_{fixture_id}"
    data = _api_get(
        "fixtures/lineups",
        {"fixture": fixture_id},
        cache_key,
        max_age_hours=2.0,  # Refresh every 2h for live data
    )
    if not data:
        return None

    response = data.get("response", [])
    if not response:
        return None

    result = {}
    for team_lineup in response:
        team = team_lineup.get("team", {})
        team_id = team.get("id")
        team_name = team.get("name", "")
        formation = team_lineup.get("formation", "")

        starters = []
        bench = []
        for p in team_lineup.get("startXI", []):
            player_info = p.get("player", {})
            starters.append({
                "player_id": player_info.get("id"),
                "name": player_info.get("name", ""),
                "number": player_info.get("number", 0),
                "pos": player_info.get("pos", ""),
                "grid": player_info.get("grid", ""),
            })

        for p in team_lineup.get("substitutes", []):
            player_info = p.get("player", {})
            bench.append({
                "player_id": player_info.get("id"),
                "name": player_info.get("name", ""),
                "number": player_info.get("number", 0),
                "pos": player_info.get("pos", ""),
            })

        result[team_name] = {
            "team_id": team_id,
            "team_name": team_name,
            "formation": formation,
            "starters": starters,
            "bench": bench,
            "coach": team_lineup.get("coach", {}).get("name", ""),
        }

    return result if result else None


# ── DB Save helpers ───────────────────────────────────────────────────────────

def _save_fixtures_to_db(team_name: str, fixtures: list) -> int:
    """Save team fixtures to team_matches table."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    team_row = cur.execute("SELECT id FROM teams WHERE name=? OR name LIKE ?",
                            (team_name, f"%{team_name}%")).fetchone()
    if not team_row:
        conn.close()
        return 0

    team_id = team_row["id"]
    inserted = 0

    for m in fixtures:
        if not m.get("date"):
            continue
        opp_name = m.get("opponent_name", "")
        opp_row = cur.execute("SELECT id FROM teams WHERE name=? OR name LIKE ?",
                               (opp_name, f"%{opp_name}%")).fetchone()
        opp_id = opp_row["id"] if opp_row else None

        cur.execute("""
            INSERT OR IGNORE INTO team_matches
                (team_id, opponent_id, opponent_name, date, competition,
                 goals_for, goals_against, result, venue)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            team_id, opp_id, opp_name,
            m["date"], m.get("competition", ""),
            m.get("goals_for", 0), m.get("goals_against", 0),
            m.get("result", "D"), m.get("venue", "neutral"),
        ))
        inserted += cur.rowcount

    conn.commit()
    conn.close()
    return inserted


def _save_player_stats_to_db(team_name: str, stats: dict) -> bool:
    """Save player stats to player_club_stats table."""
    if not stats:
        return False

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    team_row = cur.execute("SELECT id FROM teams WHERE name=? OR name LIKE ?",
                            (team_name, f"%{team_name}%")).fetchone()
    if not team_row:
        conn.close()
        return False

    team_id = team_row["id"]
    player_name = stats.get("player_name", "")
    if not player_name:
        conn.close()
        return False

    player_row = cur.execute("""
        SELECT id FROM players WHERE name=? AND team_id=?
    """, (player_name, team_id)).fetchone()

    if not player_row:
        conn.close()
        return False

    player_id = player_row["id"]
    season_str = str(stats.get("season", ""))

    cur.execute("""
        INSERT OR REPLACE INTO player_club_stats
            (player_id, season, league, matches, minutes, goals, assists,
             shots_on_target, pass_accuracy, tackles, interceptions,
             yellow_cards, red_cards)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        player_id, season_str, str(stats.get("league_id", "")),
        stats.get("matches", 0), stats.get("minutes", 0),
        stats.get("goals", 0), stats.get("assists", 0),
        stats.get("shots_on_target", 0), stats.get("pass_accuracy", 0.0),
        stats.get("tackles", 0), stats.get("interceptions", 0),
        stats.get("yellow_cards", 0), stats.get("red_cards", 0),
    ))

    # Also save rating if available
    if stats.get("rating", 0):
        cur.execute("""
            INSERT INTO player_ratings (player_id, context, rating, computed_at)
            VALUES (?,?,?,?)
        """, (player_id, "club", stats["rating"], datetime.now().isoformat()))

    conn.commit()
    conn.close()
    return True


def _save_lineups_to_db(fixture_id: int, lineups: dict) -> int:
    """Save confirmed lineups to match_lineups table."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Map fixture_id to wc_matches.id (they might be different)
    match_row = cur.execute("""
        SELECT id FROM wc_matches WHERE id=?
    """, (fixture_id,)).fetchone()

    if not match_row:
        conn.close()
        return 0

    match_id = match_row["id"]
    inserted = 0

    for team_name, lineup_data in lineups.items():
        team_row = cur.execute("SELECT id FROM teams WHERE name=? OR name LIKE ?",
                                (team_name, f"%{team_name}%")).fetchone()
        if not team_row:
            continue
        team_id = team_row["id"]

        all_players = (
            [(p, 1) for p in lineup_data.get("starters", [])] +
            [(p, 0) for p in lineup_data.get("bench", [])]
        )

        for player_data, is_starter in all_players:
            player_name = player_data.get("name", "")
            if not player_name:
                continue

            player_row = cur.execute("""
                SELECT id FROM players WHERE name=? AND team_id=?
            """, (player_name, team_id)).fetchone()

            player_id = player_row["id"] if player_row else None

            cur.execute("""
                INSERT OR IGNORE INTO match_lineups
                    (match_id, team_id, player_id, position, starter)
                VALUES (?,?,?,?,?)
            """, (
                match_id, team_id, player_id,
                player_data.get("pos", ""),
                is_starter,
            ))
            inserted += cur.rowcount

    conn.commit()
    conn.close()
    return inserted


# ── High-level pipeline functions ─────────────────────────────────────────────

def run_fetch_all_squads(teams: Optional[list] = None, season: int = 2026,
                          delay_secs: float = 2.0) -> dict:
    """
    Fetch official squads for all 48 teams (or a subset).
    Returns summary dict.
    """
    print(f"\n=== Fetch All Squads (API-Football) ===\n")
    print(f"  Budget remaining: {DAILY_LIMIT - _get_calls_today()} calls")

    if not _has_api_key():
        print("  Sin API key — saltando fetch de squads")
        return {"teams_fetched": 0, "players_found": 0}

    if teams is None:
        teams = list(TEAM_API_IDS.keys())

    fetched = 0
    total_players = 0

    for team_name in teams:
        api_id = TEAM_API_IDS.get(team_name)
        if not api_id:
            print(f"  {team_name}: sin ID en TEAM_API_IDS, saltando")
            continue

        if not _can_make_call(reserve=3):
            print(f"  Presupuesto agotado. Deteniendo en {team_name}.")
            break

        print(f"  Fetching squad: {team_name} (ID={api_id})")
        players = fetch_squad(api_id, season)

        if players:
            total_players += len(players)
            fetched += 1
            print(f"    -> {len(players)} jugadores obtenidos")
        else:
            print(f"    -> Sin datos (cache o sin respuesta)")

        time.sleep(delay_secs)

    print(f"\nSquads obtenidos: {fetched} equipos, {total_players} jugadores")
    return {"teams_fetched": fetched, "players_found": total_players}


def run_fetch_team_form(teams: Optional[list] = None, last: int = 20,
                         delay_secs: float = 2.0) -> dict:
    """
    Fetch last N matches for all teams to compute form.
    Returns summary dict.
    """
    print(f"\n=== Fetch Team Form (API-Football) ===\n")
    print(f"  Budget remaining: {DAILY_LIMIT - _get_calls_today()} calls")

    if not _has_api_key():
        print("  Sin API key — saltando fetch de forma")
        return {"teams_fetched": 0, "matches_saved": 0}

    if teams is None:
        teams = list(TEAM_API_IDS.keys())

    fetched = 0
    total_matches = 0

    for team_name in teams:
        api_id = TEAM_API_IDS.get(team_name)
        if not api_id:
            continue

        if not _can_make_call(reserve=3):
            print(f"  Presupuesto agotado. Deteniendo en {team_name}.")
            break

        print(f"  Fetching form: {team_name} (last {last})")
        fixtures = fetch_team_fixtures(api_id, last=last)

        if fixtures:
            saved = _save_fixtures_to_db(team_name, fixtures)
            total_matches += saved
            fetched += 1
            print(f"    -> {len(fixtures)} partidos obtenidos, {saved} guardados en DB")

        time.sleep(delay_secs)

    print(f"\nForma obtenida: {fetched} equipos, {total_matches} partidos guardados")
    return {"teams_fetched": fetched, "matches_saved": total_matches}


# ── Status / Debug ────────────────────────────────────────────────────────────

def show_api_status():
    """Print current API usage status."""
    calls_today = _get_calls_today()
    remaining = DAILY_LIMIT - calls_today
    log = _load_call_log()

    print(f"\n=== API-Football Status ===")
    print(f"  Calls today: {calls_today}/{DAILY_LIMIT}")
    print(f"  Remaining: {remaining}")
    print(f"  Last reset: {log.get('last_reset', 'unknown')}")
    if APISPORTS_KEY:
        print(f"  Active key: APISPORTS_KEY (api-sports.io direct) — base: {AF_BASE}")
    elif AF_KEY:
        print(f"  Active key: APIFOOT (RapidAPI) — base: {AF_BASE_RAPID}")
    else:
        print(f"  API Key configured: NO")

    recent = log.get("calls", [])[-5:]
    if recent:
        print(f"  Last 5 calls:")
        for c in recent:
            print(f"    [{c.get('timestamp', '?')[:19]}] {c.get('endpoint', '?')}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="API-Football pipeline")
    parser.add_argument("--status", action="store_true", help="Show API call status")
    parser.add_argument("--squad", type=str, help="Fetch squad for a team: --squad 'Panama'")
    parser.add_argument("--player-stats", nargs=3, type=int,
                        metavar=("PLAYER_ID", "SEASON", "LEAGUE_ID"),
                        help="Fetch player stats: --player-stats 622 2024 140")
    parser.add_argument("--fixtures", type=int, metavar="TEAM_ID",
                        help="Fetch last 20 fixtures for team: --fixtures 1887")
    parser.add_argument("--h2h", nargs=2, type=int, metavar=("TEAM1_ID", "TEAM2_ID"),
                        help="Fetch H2H: --h2h 1887 3")
    parser.add_argument("--lineup", type=int, metavar="FIXTURE_ID",
                        help="Fetch confirmed lineup: --lineup 1234567")
    parser.add_argument("--all-squads", action="store_true", help="Fetch all 48 team squads")
    parser.add_argument("--all-form", action="store_true", help="Fetch form for all teams")
    parser.add_argument("--last", type=int, default=20, help="Number of fixtures to fetch (default: 20)")
    args = parser.parse_args()

    if args.status:
        show_api_status()

    elif args.squad:
        team_name = args.squad
        api_id = TEAM_API_IDS.get(team_name)
        if not api_id:
            print(f"Team '{team_name}' not found in TEAM_API_IDS")
        else:
            players = fetch_squad(api_id)
            if players:
                print(f"\nSquad for {team_name} ({len(players)} players):")
                for p in players:
                    print(f"  #{p.get('number',0):2} {p.get('position','?'):3} {p.get('name','')}")
            else:
                print("No squad data returned")

    elif args.player_stats:
        pid, season, lid = args.player_stats
        stats = fetch_player_stats(pid, season, lid)
        if stats:
            print(json.dumps(stats, indent=2))
        else:
            print("No stats returned")

    elif args.fixtures:
        fixtures = fetch_team_fixtures(args.fixtures, last=args.last)
        if fixtures:
            print(f"\nLast {len(fixtures)} matches (team ID {args.fixtures}):")
            for m in fixtures:
                print(f"  {m['date']} vs {m['opponent_name']}: {m['goals_for']}-{m['goals_against']} [{m['result']}]")
        else:
            print("No fixtures returned")

    elif args.h2h:
        t1, t2 = args.h2h
        h2h = fetch_head_to_head(t1, t2)
        if h2h:
            print(f"\nH2H (team {t1} vs {t2}) — {len(h2h)} matches:")
            for m in h2h:
                print(f"  {m['date']} {m['team1_goals']}-{m['team2_goals']} [{m['result_for_team1']}]")
        else:
            print("No H2H data returned")

    elif args.lineup:
        lineup = fetch_live_lineups(args.lineup)
        if lineup:
            for team_name, data in lineup.items():
                print(f"\n[{team_name}] Formation: {data['formation']}")
                print("  Starters:")
                for p in data.get("starters", []):
                    print(f"    #{p.get('number',0):2} {p.get('pos','?'):3} {p.get('name','')}")
        else:
            print("No lineup data returned")

    elif args.all_squads:
        run_fetch_all_squads(delay_secs=2.0)

    elif args.all_form:
        run_fetch_team_form(last=args.last, delay_secs=2.0)

    else:
        parser.print_help()
        show_api_status()
