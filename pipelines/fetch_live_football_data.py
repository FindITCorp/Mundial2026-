"""
fetch_live_football_data.py — "Free API Live Football Data" (RapidAPI, $9.99/mo)

Host: free-api-live-football-data.p.rapidapi.com
Key:  APIFOOT env var (same key as football-prediction-api)

Endpoints used:
  /football-get-fixtures-scores-by-date?date=YYYY-MM-DD  → schedule + live scores
  /football-get-all-livescores                            → live matches right now
  /football-get-match-info?MatchID=X                     → full match detail
  /football-search-players?searchQuery=NAME               → player lookup
  /football-get-team-info?TeamID=X                        → team detail
  /football-get-all-leagues                               → league catalog

Run via GitHub Actions (APIFOOT blocks container IPs locally).
"""
import os
import sqlite3
import json
import time
from datetime import datetime, timedelta
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


def _get(endpoint: str, params: dict = None, retries=2) -> dict | None:
    import urllib.request
    import urllib.parse

    url = f"{BASE_URL}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return data
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                print(f"  [live_football] {endpoint} failed: {e}")
                return None


# ── Fixtures / Scores by date ─────────────────────────────────────────────────

def fetch_fixtures_by_date(date_str: str) -> list[dict]:
    """Returns list of match fixtures/scores for a given date (YYYY-MM-DD)."""
    data = _get("/football-get-fixtures-scores-by-date", {"date": date_str})
    if not data:
        return []
    # Response structure varies — try common keys
    for key in ("response", "data", "fixtures", "matches", "results"):
        if isinstance(data.get(key), list):
            return data[key]
    if isinstance(data, list):
        return data
    print(f"  [live_football] fixtures response keys: {list(data.keys())}")
    return []


def fetch_livescores() -> list[dict]:
    """Returns currently live matches."""
    data = _get("/football-get-all-livescores")
    if not data:
        return []
    for key in ("response", "data", "livescores", "matches"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def fetch_match_info(match_id) -> dict | None:
    """Full match detail including lineups, events, stats."""
    return _get("/football-get-match-info", {"MatchID": str(match_id)})


def fetch_leagues() -> list[dict]:
    """All available leagues."""
    data = _get("/football-get-all-leagues")
    if not data:
        return []
    for key in ("response", "data", "leagues"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def fetch_team_info(team_id) -> dict | None:
    return _get("/football-get-team-info", {"TeamID": str(team_id)})


def search_player(name: str) -> list[dict]:
    data = _get("/football-search-players", {"searchQuery": name})
    if not data:
        return []
    for key in ("response", "data", "players", "results"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


# ── Save results to DB ────────────────────────────────────────────────────────

def _ensure_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS live_fixtures (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at      TEXT NOT NULL,
            match_date      TEXT,
            api_match_id    TEXT,
            home_team       TEXT,
            away_team       TEXT,
            home_score      INTEGER,
            away_score      INTEGER,
            status          TEXT,
            league_name     TEXT,
            raw_json        TEXT,
            UNIQUE(api_match_id)
        );

        CREATE TABLE IF NOT EXISTS live_football_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at  TEXT NOT NULL,
            event_type TEXT,
            payload    TEXT
        );
    """)
    conn.commit()


def save_fixtures(fixtures: list[dict], match_date: str, db_path=DB) -> int:
    conn = sqlite3.connect(str(db_path))
    _ensure_tables(conn)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    saved = 0

    for f in fixtures:
        # Normalize field names (API may use different casing/keys)
        mid = (f.get("MatchID") or f.get("id") or f.get("fixture_id") or
               f.get("match_id") or "")
        home = (f.get("HomeTeam") or f.get("home_team") or
                f.get("localteam_name") or "")
        away = (f.get("AwayTeam") or f.get("away_team") or
                f.get("visitorteam_name") or "")
        hs = f.get("HomeScore") or f.get("home_score") or f.get("localteam_score")
        as_ = f.get("AwayScore") or f.get("away_score") or f.get("visitorteam_score")
        status = (f.get("Status") or f.get("status") or f.get("time", {}).get("status") or "")
        league = (f.get("LeagueName") or f.get("league_name") or
                  f.get("league", {}).get("name") if isinstance(f.get("league"), dict) else
                  f.get("league") or "")

        try:
            conn.execute("""
                INSERT OR REPLACE INTO live_fixtures
                  (fetched_at, match_date, api_match_id, home_team, away_team,
                   home_score, away_score, status, league_name, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (now, match_date, str(mid), home, away,
                  _int_or_none(hs), _int_or_none(as_), status, str(league),
                  json.dumps(f)))
            saved += 1
        except Exception as e:
            print(f"  [live_football] insert error: {e}")

    conn.commit()
    conn.close()
    return saved


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ── Cross-match with wc_matches ───────────────────────────────────────────────

def update_wc_results_from_live(db_path=DB) -> int:
    """
    Tries to match live_fixtures with wc_matches by team name + date,
    and updates score_home/score_away where missing.
    Returns number of wc_matches updated.
    """
    conn = sqlite3.connect(str(db_path))
    _ensure_tables(conn)

    live = conn.execute("""
        SELECT home_team, away_team, home_score, away_score, match_date
        FROM live_fixtures
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
    """).fetchall()

    updated = 0
    for (ht, at, hs, as_, mdate) in live:
        rows = conn.execute("""
            SELECT id FROM wc_matches
            WHERE date = ?
              AND score_home IS NULL
              AND (
                (home_team_name LIKE ? AND away_team_name LIKE ?)
                OR (home_team_name LIKE ? AND away_team_name LIKE ?)
              )
        """, (mdate,
              f"%{ht[:5]}%", f"%{at[:5]}%",
              f"%{at[:5]}%", f"%{ht[:5]}%")).fetchall()
        for (wid,) in rows:
            conn.execute("""
                UPDATE wc_matches SET score_home=?, score_away=?, played=1
                WHERE id=?
            """, (hs, as_, wid))
            updated += 1

    conn.commit()
    conn.close()
    return updated


# ── Main: fetch today + tomorrow ─────────────────────────────────────────────

def run(days_ahead=2, db_path=DB):
    if not API_KEY:
        print("[live_football] APIFOOT not set — skipping")
        return

    today = datetime.utcnow()
    total_saved = 0

    # 1. Livescores
    live = fetch_livescores()
    if live:
        saved = save_fixtures(live, today.strftime("%Y-%m-%d"), db_path)
        print(f"[live_football] livescores: {len(live)} matches, {saved} saved")
        total_saved += saved

    # 2. Fixtures by date
    for d in range(days_ahead + 1):
        date_str = (today + timedelta(days=d - 1)).strftime("%Y-%m-%d")
        fixtures = fetch_fixtures_by_date(date_str)
        if fixtures:
            saved = save_fixtures(fixtures, date_str, db_path)
            print(f"[live_football] {date_str}: {len(fixtures)} fixtures, {saved} saved")
            total_saved += saved
        else:
            print(f"[live_football] {date_str}: no data")
        time.sleep(0.5)

    # 3. Try to update wc_matches with live scores
    updated = update_wc_results_from_live(db_path)
    if updated:
        print(f"[live_football] Updated {updated} wc_matches from live data")

    print(f"[live_football] Total saved: {total_saved}")
    return total_saved


if __name__ == "__main__":
    run()
