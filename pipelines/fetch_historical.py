"""
fetch_historical.py — Historical national team match data for WC2026 predictions.

Fetches (in priority order):
  1. WC 2022 fixtures + player stats per match (api-sports.io league=1)
  2. WC 2018 fixtures + player stats
  3. WC 2014 fixtures + player stats
  4. Recent qualifiers per team (2022-2026)
  5. Recent friendlies per team (2023-2026)

Source: api-sports.io direct (APISPORTS_KEY) with RapidAPI fallback (APIFOOT)
Rate limit: stays within 90 calls/run to respect 100 req/day free tier.
Progress: saved in data/cache/historical_progress.json — resumes across runs.
"""
import os
import json
import time
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "historical"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── API configuration (same pattern as fetch_api_football.py) ─────────────────
AF_KEY        = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

AF_BASE       = "https://v3.football.api-sports.io"
AF_BASE_RAPID = "https://api-football-v1.p.rapidapi.com/v3"
AF_HOST       = "api-football-v1.p.rapidapi.com"

API_BASE = AF_BASE if APISPORTS_KEY else AF_BASE_RAPID

PROGRESS_FILE    = BASE_DIR / "data" / "cache" / "historical_progress.json"
CALLS_TODAY      = 0
MAX_CALLS_PER_RUN = 90

# WC league ID in api-sports.io
WC_LEAGUE_ID = 1
WC_SEASONS   = [2022, 2018, 2014]

# Qualifier league IDs per confederation (api-sports.io)
QUALIFIER_LEAGUES = {
    "CONMEBOL": 29,   # CONMEBOL WC Qualifiers
    "UEFA": 4,        # UEFA WC Qualifiers
    "CONCACAF": 31,   # CONCACAF Nations League / WCQ
    "CAF": 6,         # CAF WC Qualifiers
    "AFC": 8,         # AFC WC Qualifiers
}

# National team IDs in api-sports.io
NAT_TEAM_IDS = {
    "Argentina":    26,
    "France":       2,
    "Brazil":       6,
    "Germany":      25,
    "Spain":        9,
    "England":      10,
    "Portugal":     27,
    "Netherlands":  1118,
    "Croatia":      3,
    "Switzerland":  15,
    "Morocco":      1947,
    "USA":          1,
    "Mexico":       16,
    "Canada":       94,
    "Panama":       1887,
    "Japan":        23,
    "South Korea":  36,
    "Australia":    25,
    "Iran":         28,
    "Senegal":      38,
    "Nigeria":      34,
    "Ghana":        640,
    "Egypt":        34,
    "Cameroon":     1039,
    "Colombia":     30,
    "Uruguay":      26,
    "Ecuador":      101,
    "Chile":        21,
    "Bolivia":      701,
    "Venezuela":    18,
    "Paraguay":     678,
    "Saudi Arabia": 36,
    "Qatar":        55,
    "Poland":       24,
    "Denmark":      21,
    "Turkey":       29,
    "Serbia":       14,
    "Austria":      11,
    "Belgium":      1,
    "Italy":        768,
    "Scotland":     1108,
    "Slovakia":     774,
    "Romania":      774,
    "Slovenia":     1091,
    "Ukraine":      1881,
    "Georgia":      1882,
    "Albania":      1485,
    "New Zealand":  826,
    "Indonesia":    1350,
    "DR Congo":     640,
    "Mali":         1572,
    "South Africa": 664,
    "Costa Rica":   65,
    "Honduras":     63,
    "Jamaica":      69,
    "Iraq":         3027,
    "Jordan":       845,
}

# Setup logger
logging.basicConfig(
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("fetch_historical")


# ── API auth headers (same pattern as fetch_api_football.py) ──────────────────

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


# ── Progress tracking ─────────────────────────────────────────────────────────

def _load_progress() -> dict:
    """Load progress from JSON file. Returns a fresh dict if not found."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as f:
                data = json.load(f)
                # Ensure all required keys exist (forward-compatible)
                data.setdefault("wc_fixtures_fetched", [])
                data.setdefault("processed_fixtures", [])
                data.setdefault("team_fixtures_fetched", {})
                data.setdefault("last_run", "")
                data.setdefault("total_fixtures_processed", 0)
                return data
        except Exception as e:
            logger.warning(f"Could not load progress file: {e}. Starting fresh.")
    return {
        "wc_fixtures_fetched": [],
        "processed_fixtures": [],
        "team_fixtures_fetched": {},
        "last_run": "",
        "total_fixtures_processed": 0,
    }


def _save_progress(progress: dict) -> None:
    """Save progress to JSON file."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["last_run"] = datetime.now().isoformat()
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(cache_key: str) -> Path:
    """Return cache file path for a given key."""
    safe = cache_key.replace("/", "_").replace(" ", "_").replace("?", "_")
    return CACHE_DIR / f"{safe}.json"


def _cache_valid(cache_key: str, max_age_hours: float = 168.0) -> bool:
    """Check if cache exists and is fresh (default 7 days for historical data)."""
    p = _cache_path(cache_key)
    if not p.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age < timedelta(hours=max_age_hours)


def _load_cache(cache_key: str) -> Optional[dict]:
    p = _cache_path(cache_key)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_cache(cache_key: str, data: dict) -> None:
    p = _cache_path(cache_key)
    try:
        with open(p, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write cache {cache_key}: {e}")


# ── Core API GET with caching and rate limiting ───────────────────────────────

def _api_get(endpoint: str, params: dict, cache_key: str,
             max_age_hours: float = 168.0) -> Optional[dict]:
    """
    Make an API GET request with caching and rate limit tracking.
    Returns the full JSON response or None if limit reached or error.
    """
    global CALLS_TODAY

    # Check cache first
    if _cache_valid(cache_key, max_age_hours):
        cached = _load_cache(cache_key)
        if cached is not None:
            logger.debug(f"  [cache] {endpoint} ({cache_key})")
            return cached

    # Guard: API key required
    if not _has_api_key():
        logger.warning(f"  [historical] No API key configured (APISPORTS_KEY / APIFOOT)")
        return None

    # Guard: rate limit
    if CALLS_TODAY >= MAX_CALLS_PER_RUN:
        logger.info(f"  [historical] Rate limit reached ({CALLS_TODAY}/{MAX_CALLS_PER_RUN}). Stopping.")
        return None

    url = f"{API_BASE}/{endpoint}"
    headers = _af_headers()

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        CALLS_TODAY += 1

        if r.status_code == 200:
            data = r.json()
            _save_cache(cache_key, data)
            remaining = (
                r.headers.get("x-ratelimit-requests-remaining")
                or r.headers.get("X-RateLimit-Requests-Remaining", "?")
            )
            results_count = len(data.get("response", []))
            logger.info(
                f"  [API] {endpoint} params={params} -> {results_count} results "
                f"(calls this run: {CALLS_TODAY}, API remaining: {remaining})"
            )
            return data

        elif r.status_code == 429:
            logger.warning(f"  [historical] HTTP 429 rate limit — waiting 60s...")
            time.sleep(60)
            return None

        else:
            logger.error(f"  [historical] HTTP {r.status_code} for {endpoint}: {r.text[:300]}")
            return None

    except requests.exceptions.Timeout:
        logger.error(f"  [historical] Timeout calling {endpoint}")
        return None
    except Exception as e:
        logger.error(f"  [historical] Exception calling {endpoint}: {e}")
        return None


# ── Fetch functions ───────────────────────────────────────────────────────────

def fetch_wc_fixtures(season: int) -> list:
    """
    Fetch all WC fixtures for a given season year.
    Returns list of fixture response dicts from the API.
    """
    data = _api_get(
        "fixtures",
        {"league": WC_LEAGUE_ID, "season": season},
        f"wc_fixtures_{season}",
    )
    if not data:
        return []
    return data.get("response", [])


def fetch_fixture_players(fixture_id: int) -> list:
    """
    Fetch player stats for a specific fixture.
    Returns list of team dicts, each containing players with statistics.
    """
    data = _api_get(
        "fixtures/players",
        {"fixture": fixture_id},
        f"fixture_players_{fixture_id}",
        max_age_hours=720.0,  # Historical data — cache for 30 days
    )
    if not data:
        return []
    return data.get("response", [])


def fetch_team_recent_fixtures(team_name: str, af_team_id: int, season: int) -> list:
    """
    Fetch recent fixtures for a national team in a specific season.
    Returns list of fixture response dicts.
    """
    cache_key = f"team_fixtures_{af_team_id}_{season}"
    data = _api_get(
        "fixtures",
        {"team": af_team_id, "season": season, "last": 30},
        cache_key,
        max_age_hours=48.0,
    )
    if not data:
        return []
    return data.get("response", [])


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_connection() -> sqlite3.Connection:
    """Open DB connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _find_team_id(cur: sqlite3.Cursor, api_team_id: int, team_name: str) -> Optional[int]:
    """
    Try to resolve our internal team_id from API team_id or name.
    Checks teams table by name match (exact then fuzzy).
    """
    # Try by name exact
    row = cur.execute(
        "SELECT id FROM teams WHERE name=? COLLATE NOCASE", (team_name,)
    ).fetchone()
    if row:
        return row["id"]

    # Try fuzzy match (API names vary: "Korea Republic" vs "South Korea")
    row = cur.execute(
        "SELECT id FROM teams WHERE name LIKE ? OR name LIKE ?",
        (f"%{team_name}%", f"{team_name[:4]}%"),
    ).fetchone()
    if row:
        return row["id"]

    return None


def _find_player_id(cur: sqlite3.Cursor, player_name: str, team_id: Optional[int],
                    player_api_id: int) -> Optional[int]:
    """
    Try to match an API player to our players table.
    Tries: exact name + team, then exact name only.
    """
    if team_id:
        row = cur.execute(
            "SELECT id FROM players WHERE name=? AND team_id=? COLLATE NOCASE",
            (player_name, team_id),
        ).fetchone()
        if row:
            return row["id"]

    # Fuzzy: last name match within team
    parts = player_name.split()
    if len(parts) >= 2 and team_id:
        last = parts[-1]
        row = cur.execute(
            "SELECT id FROM players WHERE name LIKE ? AND team_id=?",
            (f"%{last}%", team_id),
        ).fetchone()
        if row:
            return row["id"]

    # Last resort: name only across all teams
    row = cur.execute(
        "SELECT id FROM players WHERE name=? COLLATE NOCASE", (player_name,)
    ).fetchone()
    if row:
        return row["id"]

    return None


def save_wc_fixture_to_db(conn: sqlite3.Connection, fixture: dict, season: int) -> int:
    """
    Save a WC fixture result to the wc_history table.
    Also saves to team_matches if team is in our DB.
    Returns the fixture_api_id.
    """
    cur = conn.cursor()

    fix_data  = fixture.get("fixture", {})
    teams     = fixture.get("teams", {})
    goals     = fixture.get("goals", {})
    league    = fixture.get("league", {})
    score     = fixture.get("score", {})

    fixture_api_id = fix_data.get("id")
    if not fixture_api_id:
        return 0

    match_date  = (fix_data.get("date") or "")[:10]
    home_name   = teams.get("home", {}).get("name", "")
    away_name   = teams.get("away", {}).get("name", "")
    home_api_id = teams.get("home", {}).get("id")
    away_api_id = teams.get("away", {}).get("id")
    home_goals  = goals.get("home") if goals.get("home") is not None else 0
    away_goals  = goals.get("away") if goals.get("away") is not None else 0
    round_name  = league.get("round", "")
    status      = fix_data.get("status", {}).get("short", "")

    # Only save finished matches
    if status not in ("FT", "AET", "PEN", "FT_PEN"):
        return fixture_api_id

    # Save as team_matches for both home and away teams
    for team_name, opp_name, gf, ga, venue_side in [
        (home_name, away_name, home_goals, away_goals, "home"),
        (away_name, home_name, away_goals, home_goals, "away"),
    ]:
        team_id = _find_team_id(cur, 0, team_name)
        if not team_id:
            continue

        opp_id = _find_team_id(cur, 0, opp_name)

        if gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"

        # Determine WC edition year from season
        wc_year = season

        cur.execute("""
            INSERT OR IGNORE INTO team_matches
                (team_id, opponent_id, opponent_name, date, competition,
                 goals_for, goals_against, result, venue, wc_edition)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            team_id, opp_id, opp_name, match_date,
            f"FIFA World Cup {season}", gf, ga, result, venue_side, wc_year,
        ))

        # Update wc_history with api_fixture_id reference
        cur.execute("""
            INSERT OR IGNORE INTO wc_history
                (team_id, year, round_reached, goals_scored, goals_conceded,
                 matches_played, api_fixture_id)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(team_id, year) DO UPDATE SET
                api_fixture_id = COALESCE(api_fixture_id, excluded.api_fixture_id)
        """, (team_id, season, round_name, gf, ga, 1, fixture_api_id))

    conn.commit()
    return fixture_api_id


def save_match_players_to_db(conn: sqlite3.Connection, fixture_api_id: int,
                              players_response: list, match_date: str,
                              competition: str, season: int) -> int:
    """
    Save player stats from a fixture to the match_players table.
    Returns number of rows inserted/replaced.
    """
    cur = conn.cursor()
    saved = 0

    for team_data in players_response:
        team_info   = team_data.get("team", {})
        api_team_id = team_info.get("id")
        team_name   = team_info.get("name", "")

        # Resolve our internal team_id
        internal_team_id = _find_team_id(cur, api_team_id, team_name)

        players_list = team_data.get("players", [])
        for p_entry in players_list:
            player_info = p_entry.get("player", {})
            stats_list  = p_entry.get("statistics", [{}])
            stats       = stats_list[0] if stats_list else {}

            player_api_id = player_info.get("id")
            player_name   = player_info.get("name", "")

            if not player_api_id or not player_name:
                continue

            # Resolve our internal player_id
            internal_player_id = _find_player_id(
                cur, player_name, internal_team_id, player_api_id
            )

            # Extract stats safely
            games    = stats.get("games", {}) or {}
            goals_s  = stats.get("goals", {}) or {}
            shots_s  = stats.get("shots", {}) or {}
            passes_s = stats.get("passes", {}) or {}
            tackles_s = stats.get("tackles", {}) or {}
            cards_s  = stats.get("cards", {}) or {}

            position      = games.get("position") or ""
            started_val   = games.get("lineupPosition") or games.get("captain")
            # "lineupPosition" present means started; also check minutesPlayed
            minutes_raw   = games.get("minutes")
            minutes_played = int(minutes_raw) if minutes_raw is not None else 0
            started        = 1 if minutes_played >= 45 else 0

            goals_val      = int(goals_s.get("total") or 0)
            assists_val    = int(goals_s.get("assists") or 0)
            yellow_val     = int(cards_s.get("yellow") or 0)
            red_val        = int(cards_s.get("red") or 0)
            rating_raw     = games.get("rating")
            rating_val     = float(rating_raw) if rating_raw else 0.0
            shots_total    = int((shots_s.get("total") or 0))
            shots_on_val   = int((shots_s.get("on") or 0))
            passes_total   = int((passes_s.get("total") or 0))
            key_passes_val = int((passes_s.get("key") or 0))
            tackles_val    = int((tackles_s.get("total") or 0))
            interceptions_val = int((tackles_s.get("interceptions") or 0))

            # Normalise position string to our GK/DEF/MID/FWD scheme
            pos_map = {
                "G": "GK", "Goalkeeper": "GK",
                "D": "DEF", "Defender": "DEF",
                "M": "MID", "Midfielder": "MID",
                "F": "FWD", "Attacker": "FWD", "Forward": "FWD",
            }
            norm_pos = pos_map.get(position, position[:3].upper() if position else "")

            try:
                cur.execute("""
                    INSERT OR REPLACE INTO match_players
                        (fixture_api_id, team_id, player_id, player_api_id,
                         player_name, position, started, minutes_played,
                         goals, assists, yellow_cards, red_cards, rating,
                         shots_total, shots_on, passes_total, key_passes,
                         tackles, interceptions, match_date, competition, season)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    fixture_api_id,
                    internal_team_id,
                    internal_player_id,
                    player_api_id,
                    player_name,
                    norm_pos,
                    started,
                    minutes_played,
                    goals_val,
                    assists_val,
                    yellow_val,
                    red_val,
                    rating_val,
                    shots_total,
                    shots_on_val,
                    passes_total,
                    key_passes_val,
                    tackles_val,
                    interceptions_val,
                    match_date,
                    competition,
                    season,
                ))
                saved += cur.rowcount
            except sqlite3.Error as e:
                logger.debug(f"    DB error for player {player_name}: {e}")

    conn.commit()
    return saved


def update_nat_stats_from_match_players(conn: sqlite3.Connection) -> int:
    """
    Aggregate match_players data into player_nat_stats and update player profiles.

    For each player in match_players who has an internal player_id:
    - Creates/updates player_nat_stats records
    - Updates players.caps and players.goals_as_nat

    Returns number of player records updated.
    """
    cur = conn.cursor()
    updated = 0

    # Fetch aggregated stats per player from match_players
    rows = cur.execute("""
        SELECT
            player_id,
            player_api_id,
            player_name,
            team_id,
            COUNT(DISTINCT fixture_api_id)  AS total_matches,
            SUM(goals)                       AS total_goals,
            SUM(assists)                     AS total_assists,
            SUM(minutes_played)              AS total_minutes,
            AVG(CASE WHEN rating > 0 THEN rating END) AS avg_rating,
            MAX(match_date)                  AS last_match_date
        FROM match_players
        WHERE player_id IS NOT NULL
        GROUP BY player_id
    """).fetchall()

    for row in rows:
        player_id    = row["player_id"]
        total_matches = row["total_matches"] or 0
        total_goals   = row["total_goals"] or 0
        total_assists  = row["total_assists"] or 0
        total_minutes  = row["total_minutes"] or 0
        avg_rating     = round(float(row["avg_rating"] or 0.0), 2)

        # Update players table: caps and goals_as_nat (use MAX to avoid lowering seeded values)
        cur.execute("""
            UPDATE players
            SET caps         = MAX(caps, ?),
                goals_as_nat = MAX(goals_as_nat, ?)
            WHERE id = ?
        """, (total_matches, total_goals, player_id))

        if cur.rowcount > 0:
            updated += 1

        # Create player_nat_stats records per fixture for this player
        # (only for fixtures not yet in player_nat_stats)
        fixture_rows = cur.execute("""
            SELECT
                mp.fixture_api_id,
                mp.match_date,
                mp.team_id,
                mp.minutes_played,
                mp.goals,
                mp.assists,
                mp.rating,
                mp.started,
                mp.competition,
                tm.opponent_name
            FROM match_players mp
            LEFT JOIN team_matches tm
                ON tm.team_id = mp.team_id
                AND tm.date   = mp.match_date
                AND tm.competition LIKE '%' || mp.competition || '%'
            WHERE mp.player_id = ?
            ORDER BY mp.match_date
        """, (player_id,)).fetchall()

        for fr in fixture_rows:
            # Check if already exists in player_nat_stats
            existing = cur.execute("""
                SELECT id FROM player_nat_stats
                WHERE player_id = ? AND match_date = ?
                LIMIT 1
            """, (player_id, fr["match_date"])).fetchone()

            if not existing:
                opponent = fr["opponent_name"] or fr["competition"] or ""
                cur.execute("""
                    INSERT OR IGNORE INTO player_nat_stats
                        (player_id, match_date, opponent, minutes,
                         goals, assists, rating, was_starter)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    player_id,
                    fr["match_date"],
                    opponent,
                    fr["minutes_played"] or 0,
                    fr["goals"] or 0,
                    fr["assists"] or 0,
                    fr["rating"] or None,
                    fr["started"] or 0,
                ))

    conn.commit()
    logger.info(f"  update_nat_stats_from_match_players: {updated} players updated")
    return updated


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run():
    """
    Main pipeline — runs incrementally, respects rate limits.

    Priority order:
    1. WC seasons [2022, 2018, 2014]: fetch fixture list, then player stats per fixture
    2. Recent team fixtures (qualifiers + friendlies) for [2024, 2025, 2026]
    3. Aggregate match_players → player_nat_stats / player profiles
    """
    global CALLS_TODAY

    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE: fetch_historical — Historical WC + Qualifier Data")
    logger.info("=" * 60)

    if not _has_api_key():
        logger.warning(
            "No API key configured (APISPORTS_KEY or APIFOOT). "
            "Historical fetch skipped."
        )
        return

    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}. Run setup_db.py first.")
        return

    conn   = _get_connection()
    progress = _load_progress()

    fixtures_this_run  = 0
    players_this_run   = 0
    wc_done_all = True  # will be set False if any WC season is incomplete

    # ── PHASE 1: WC fixtures and per-fixture player stats ─────────────────────
    logger.info("\n--- Phase 1: WC Historical Fixtures ---")

    for season in WC_SEASONS:
        if CALLS_TODAY >= MAX_CALLS_PER_RUN:
            logger.info(f"  Rate limit reached before completing WC {season}. Will resume next run.")
            _save_progress(progress)
            conn.close()
            return

        # Step 1a: Fetch fixture list for this WC season
        if season not in progress["wc_fixtures_fetched"]:
            logger.info(f"  Fetching WC {season} fixture list...")
            fixtures = fetch_wc_fixtures(season)

            if CALLS_TODAY >= MAX_CALLS_PER_RUN:
                logger.info("  Rate limit hit fetching fixture list. Resuming next run.")
                _save_progress(progress)
                conn.close()
                return

            if fixtures:
                logger.info(f"  WC {season}: {len(fixtures)} fixtures found")
                # Save finished fixtures to DB immediately
                for fx in fixtures:
                    save_wc_fixture_to_db(conn, fx, season)
                    fixtures_this_run += 1
                progress["wc_fixtures_fetched"].append(season)
                _save_progress(progress)
            else:
                logger.warning(f"  WC {season}: no fixture data from API")
                # Mark as fetched anyway to avoid burning calls on empty endpoint
                progress["wc_fixtures_fetched"].append(season)
                _save_progress(progress)
                continue
        else:
            logger.info(f"  WC {season}: fixture list already fetched (cached)")

        # Step 1b: Fetch player stats for each fixture in this WC season
        # Re-read fixtures from cache to get fixture IDs
        cached = _load_cache(f"wc_fixtures_{season}")
        if not cached:
            logger.warning(f"  WC {season}: cache missing, cannot process per-fixture players")
            wc_done_all = False
            continue

        all_fixtures = cached.get("response", [])
        finished_ids = []
        for fx in all_fixtures:
            status_short = fx.get("fixture", {}).get("status", {}).get("short", "")
            if status_short in ("FT", "AET", "PEN", "FT_PEN"):
                finished_ids.append(fx.get("fixture", {}).get("id"))

        pending = [fid for fid in finished_ids
                   if fid and fid not in progress["processed_fixtures"]]

        logger.info(
            f"  WC {season}: {len(finished_ids)} finished, "
            f"{len(pending)} need player stats"
        )

        for fixture_id in pending:
            if CALLS_TODAY >= MAX_CALLS_PER_RUN:
                logger.info(
                    f"  Rate limit reached mid-WC-{season}. "
                    f"Progress saved. Resume next run."
                )
                _save_progress(progress)
                conn.close()
                return

            logger.info(f"    Fetching player stats: fixture {fixture_id} (WC {season})")
            players_resp = fetch_fixture_players(fixture_id)

            if players_resp:
                # Determine match_date from the fixture data
                match_date = ""
                for fx in all_fixtures:
                    if fx.get("fixture", {}).get("id") == fixture_id:
                        match_date = (fx.get("fixture", {}).get("date") or "")[:10]
                        break

                n = save_match_players_to_db(
                    conn, fixture_id, players_resp,
                    match_date=match_date,
                    competition=f"FIFA World Cup {season}",
                    season=season,
                )
                players_this_run += n
                logger.info(f"    -> {n} player-match records saved")
            else:
                logger.debug(f"    -> No player data for fixture {fixture_id}")

            progress["processed_fixtures"].append(fixture_id)
            progress["total_fixtures_processed"] += 1

            # Save progress after every fixture
            _save_progress(progress)

            # Brief pause to be respectful to the API
            time.sleep(0.5)

        # Check if all WC fixtures for this season are done
        remaining = [fid for fid in finished_ids
                     if fid and fid not in progress["processed_fixtures"]]
        if remaining:
            wc_done_all = False

    # ── PHASE 2: Recent team fixtures (qualifiers + friendlies) ───────────────
    # Only run phase 2 if all WC phases are complete (saves calls for higher priority data)
    if not wc_done_all:
        logger.info("\n--- Phase 2: Skipped (WC phases not complete yet) ---")
        _save_progress(progress)
        conn.close()
        _print_run_summary(progress, fixtures_this_run, players_this_run)
        return

    logger.info("\n--- Phase 2: Recent Team Fixtures (2024-2026) ---")

    recent_seasons = [2024, 2025, 2026]

    for team_name, af_team_id in NAT_TEAM_IDS.items():
        for season in recent_seasons:
            if CALLS_TODAY >= MAX_CALLS_PER_RUN:
                logger.info(
                    f"  Rate limit reached in Phase 2 "
                    f"(team={team_name}, season={season}). Saving progress."
                )
                _save_progress(progress)
                conn.close()
                _print_run_summary(progress, fixtures_this_run, players_this_run)
                return

            key = f"{team_name}_{season}"
            if progress["team_fixtures_fetched"].get(key):
                continue

            logger.info(f"  Fetching fixtures: {team_name} {season}...")
            team_fixtures = fetch_team_recent_fixtures(team_name, af_team_id, season)
            progress["team_fixtures_fetched"][key] = True
            _save_progress(progress)

            if not team_fixtures:
                logger.debug(f"  {team_name} {season}: no fixtures")
                continue

            logger.info(f"  {team_name} {season}: {len(team_fixtures)} fixtures")

            # Save fixture results to team_matches
            _save_team_fixtures_to_db(conn, team_name, team_fixtures)

            # Fetch player stats for unprocessed fixtures
            for fx in team_fixtures:
                fx_data    = fx.get("fixture", {})
                fixture_id = fx_data.get("id")
                status     = fx_data.get("status", {}).get("short", "")

                if not fixture_id:
                    continue
                if status not in ("FT", "AET", "PEN", "FT_PEN"):
                    continue
                if fixture_id in progress["processed_fixtures"]:
                    continue

                if CALLS_TODAY >= MAX_CALLS_PER_RUN:
                    logger.info("  Rate limit reached fetching team fixture players.")
                    _save_progress(progress)
                    conn.close()
                    _print_run_summary(progress, fixtures_this_run, players_this_run)
                    return

                league    = fx.get("league", {})
                match_date = (fx_data.get("date") or "")[:10]
                comp_name  = league.get("name", "Friendly")

                logger.info(f"    Player stats: fixture {fixture_id} ({team_name} vs ...)")
                players_resp = fetch_fixture_players(fixture_id)

                if players_resp:
                    n = save_match_players_to_db(
                        conn, fixture_id, players_resp,
                        match_date=match_date,
                        competition=comp_name,
                        season=season,
                    )
                    players_this_run += n
                    logger.info(f"    -> {n} player-match records saved")

                progress["processed_fixtures"].append(fixture_id)
                progress["total_fixtures_processed"] += 1
                _save_progress(progress)

                time.sleep(0.5)

    # ── PHASE 3: Aggregate into nat_stats / player profiles ───────────────────
    logger.info("\n--- Phase 3: Aggregating match_players → player_nat_stats ---")
    updated = update_nat_stats_from_match_players(conn)
    logger.info(f"  {updated} player profiles updated from historical data")

    _save_progress(progress)
    conn.close()
    _print_run_summary(progress, fixtures_this_run, players_this_run)


def _save_team_fixtures_to_db(conn: sqlite3.Connection, team_name: str,
                               fixtures: list) -> int:
    """
    Save recent team fixtures (from Phase 2) to team_matches table.
    Returns number of rows inserted.
    """
    cur = conn.cursor()
    team_id = _find_team_id(cur, 0, team_name)
    if not team_id:
        return 0

    inserted = 0
    for fx in fixtures:
        fx_data  = fx.get("fixture", {})
        teams    = fx.get("teams", {})
        goals    = fx.get("goals", {})
        league   = fx.get("league", {})

        status = fx_data.get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN", "FT_PEN"):
            continue

        match_date  = (fx_data.get("date") or "")[:10]
        if not match_date:
            continue

        home_id   = teams.get("home", {}).get("id")
        away_id   = teams.get("away", {}).get("id")
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        home_goals = goals.get("home") or 0
        away_goals = goals.get("away") or 0

        # Determine perspective for this team
        is_home = (home_name.lower() == team_name.lower() or
                   team_name.lower() in home_name.lower())
        # Fallback: check by common name fragments
        if not is_home and not (
            away_name.lower() == team_name.lower() or
            team_name.lower() in away_name.lower()
        ):
            # Cannot determine perspective; skip
            continue

        if is_home:
            gf, ga   = home_goals, away_goals
            opp_name = away_name
        else:
            gf, ga   = away_goals, home_goals
            opp_name = home_name

        if gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"

        opp_id     = _find_team_id(cur, 0, opp_name)
        comp_name  = league.get("name", "Friendly")
        venue_side = "home" if is_home else "away"

        cur.execute("""
            INSERT OR IGNORE INTO team_matches
                (team_id, opponent_id, opponent_name, date, competition,
                 goals_for, goals_against, result, venue)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            team_id, opp_id, opp_name, match_date,
            comp_name, gf, ga, result, venue_side,
        ))
        inserted += cur.rowcount

    conn.commit()
    return inserted


def _print_run_summary(progress: dict, fixtures_processed: int, players_saved: int) -> None:
    """Print a summary of what was fetched this run."""
    logger.info("\n" + "=" * 60)
    logger.info("FETCH HISTORICAL — RUN SUMMARY")
    logger.info(f"  API calls this run          : {CALLS_TODAY}")
    logger.info(f"  WC seasons with fixture list: {progress['wc_fixtures_fetched']}")
    logger.info(f"  Total fixtures processed     : {progress['total_fixtures_processed']}")
    logger.info(f"  Fixture results saved (run)  : {fixtures_processed}")
    logger.info(f"  Player-match records (run)   : {players_saved}")
    logger.info(f"  Team-season combos fetched   : {len(progress['team_fixtures_fetched'])}")
    logger.info(f"  Progress file               : {PROGRESS_FILE}")
    logger.info("=" * 60 + "\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
