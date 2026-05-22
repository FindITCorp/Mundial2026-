"""
fetch_daily_form.py — Daily match data update for all 48 WC2026 teams.

Sources (in order):
  1. martj42/international_results GitHub CSV  — free, all teams, ~2 week lag
  2. football-data.org API                     — free tier, recent competitions
  3. api-sports.io                             — 100 req/day, most recent fixtures

Run daily via GitHub Actions. Inserts only rows newer than what we already have.
"""
import csv
import io
import json
import os
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"
CACHE_DIR = BASE_DIR / "data" / "cache" / "daily_form"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FD_KEY        = os.getenv("FOOTBALL_DATA_KEY", "")
AF_KEY        = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

MARTJ42_URL = (
    "https://raw.githubusercontent.com/martj42/international_results"
    "/master/results.csv"
)

# ── team name aliases ──────────────────────────────────────────────────────────
ALIASES = {
    "united states":       "usa",
    "u.s.":                "usa",
    "korea republic":      "south korea",
    "republic of korea":   "south korea",
    "ir iran":             "iran",
    "islamic republic of iran": "iran",
    "côte d'ivoire":       "ivory coast",
    "cote d'ivoire":       "ivory coast",
    "republic of ireland": "ireland",
    "northern ireland":    "northern ireland",
    "czech republic":      "czechia",
    "cape verde":          "cape verde islands",
    "trinidad & tobago":   "trinidad and tobago",
    "saint kitts & nevis": "saint kitts and nevis",
    "hong kong":           "hong kong",
    "chinese taipei":      "taiwan",
    "north macedonia":     "north macedonia",
    "republic of north macedonia": "north macedonia",
}


def _normalise(name: str) -> str:
    n = name.lower().strip()
    return ALIASES.get(n, n)


def _load_teams(conn: sqlite3.Connection) -> dict:
    """Return {normalised_name: team_id} for all teams in DB."""
    rows = conn.execute("SELECT id, name FROM teams").fetchall()
    result = {}
    for tid, tname in rows:
        result[_normalise(tname)] = tid
        result[tname.lower()] = tid
    return result


def _find_team(name: str, team_map: dict) -> Optional[int]:
    """Fuzzy-match a team name to a DB team_id."""
    n = _normalise(name)
    if n in team_map:
        return team_map[n]
    # substring match
    for key, tid in team_map.items():
        if n in key or key in n:
            return tid
    return None


def _get_latest_date(conn: sqlite3.Connection, team_id: int) -> str:
    """Return the most recent match date for a team (or '1900-01-01')."""
    row = conn.execute(
        "SELECT MAX(date) FROM team_matches WHERE team_id=?", (team_id,)
    ).fetchone()
    return row[0] or "1900-01-01"


def _insert_match(conn: sqlite3.Connection, team_id: int, opp_id: Optional[int],
                  opp_name: str, date: str, competition: str,
                  gf: int, ga: int, venue: str) -> bool:
    result = "W" if gf > ga else ("D" if gf == ga else "L")
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO team_matches
                (team_id, opponent_id, opponent_name, date, competition,
                 goals_for, goals_against, result, venue)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (team_id, opp_id, opp_name, date, competition, gf, ga, result, venue))
        return cur.rowcount > 0
    except sqlite3.Error:
        return False


# ── Source 1: martj42 CSV ─────────────────────────────────────────────────────

def _download_martj42() -> list[dict]:
    """Download the full CSV and return list of row dicts."""
    today = datetime.now().strftime("%Y%m%d")
    cache = CACHE_DIR / f"martj42_{today}.csv"

    if cache.exists():
        print("  [martj42] Using cached CSV")
        raw = cache.read_text(encoding="utf-8")
    else:
        print("  [martj42] Downloading CSV...")
        try:
            with urllib.request.urlopen(MARTJ42_URL, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
            cache.write_text(raw, encoding="utf-8")
        except Exception as e:
            print(f"  [martj42] Download error: {e}")
            # Try yesterday's cache
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            old = CACHE_DIR / f"martj42_{yesterday}.csv"
            if old.exists():
                print("  [martj42] Using yesterday's cache")
                raw = old.read_text(encoding="utf-8")
            else:
                return []

    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def update_from_martj42(conn: sqlite3.Connection) -> int:
    """
    Download full martj42 CSV and insert any rows newer than what we have per team.
    Returns total new rows inserted.
    """
    rows = _download_martj42()
    if not rows:
        print("  [martj42] No data")
        return 0

    team_map = _load_teams(conn)
    inserted_total = 0
    skipped_no_score = 0
    skipped_old = 0

    # Build per-team latest date cache
    latest: dict[int, str] = {}

    for row in rows:
        home = row.get("home_team", "").strip()
        away = row.get("away_team", "").strip()
        date = (row.get("date") or "").strip()
        hs   = row.get("home_score", "").strip()
        as_  = row.get("away_score", "").strip()
        tournament = row.get("tournament", "Friendly").strip()
        neutral = row.get("neutral", "FALSE").strip().upper() == "TRUE"

        # Skip future/unplayed matches
        if not hs or hs == "NA" or not as_ or as_ == "NA":
            skipped_no_score += 1
            continue
        try:
            gf_home, gf_away = int(hs), int(as_)
        except ValueError:
            continue

        home_id = _find_team(home, team_map)
        away_id = _find_team(away, team_map)

        if not home_id and not away_id:
            continue

        # Insert from home team's perspective
        if home_id:
            if home_id not in latest:
                latest[home_id] = _get_latest_date(conn, home_id)
            if date > latest[home_id]:
                venue = "neutral" if neutral else "home"
                ok = _insert_match(conn, home_id, away_id, away, date,
                                   tournament, gf_home, gf_away, venue)
                if ok:
                    inserted_total += 1
                    if date > latest[home_id]:
                        latest[home_id] = date
            else:
                skipped_old += 1

        # Insert from away team's perspective
        if away_id:
            if away_id not in latest:
                latest[away_id] = _get_latest_date(conn, away_id)
            if date > latest[away_id]:
                venue = "neutral" if neutral else "away"
                ok = _insert_match(conn, away_id, home_id, home, date,
                                   tournament, gf_away, gf_home, venue)
                if ok:
                    inserted_total += 1
                    if date > latest[away_id]:
                        latest[away_id] = date
            else:
                skipped_old += 1

    conn.commit()
    print(f"  [martj42] +{inserted_total} new rows "
          f"({skipped_old} already present, {skipped_no_score} unplayed skipped)")
    return inserted_total


# ── Source 2: football-data.org ───────────────────────────────────────────────

FD_BASE = "https://api.football-data.org/v4"

# Competitions available on free tier that are relevant
FD_COMPETITIONS = [
    ("WC",   "FIFA World Cup"),
    ("CL",   "UEFA Champions League"),     # not national but tests key
    ("EC",   "UEFA Euro"),
    ("EURO_QUAL", "UEFA Euro Qualification"),
    ("WCQ",  "WC Qualification"),
]


def _fd_get(path: str) -> Optional[dict]:
    if not FD_KEY:
        return None
    url = f"{FD_BASE}/{path}"
    try:
        r = requests.get(url, headers={"X-Auth-Token": FD_KEY}, timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            print(f"  [FD] Rate limited on {path}")
        return None
    except Exception as e:
        print(f"  [FD] Error {path}: {e}")
        return None


def update_from_football_data_org(conn: sqlite3.Connection,
                                  days_back: int = 30) -> int:
    """Fetch recent national-team matches from football-data.org free tier."""
    if not FD_KEY:
        print("  [FD] No FOOTBALL_DATA_KEY — skipping")
        return 0

    team_map = _load_teams(conn)
    since    = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    today    = datetime.now().strftime("%Y-%m-%d")
    inserted = 0

    # Fetch the WC 2026 matches (competition code WC, season 2026)
    for code, label in [("WC", "FIFA World Cup 2026")]:
        data = _fd_get(f"competitions/{code}/matches?dateFrom={since}&dateTo={today}")
        if not data:
            continue
        matches = data.get("matches", [])
        print(f"  [FD] {label}: {len(matches)} recent matches")
        for m in matches:
            home_name = m.get("homeTeam", {}).get("name", "")
            away_name = m.get("awayTeam", {}).get("name", "")
            date_raw  = (m.get("utcDate") or "")[:10]
            score     = m.get("score", {})
            ft        = score.get("fullTime", {})
            hs        = ft.get("home")
            as_       = ft.get("away")
            if hs is None or as_ is None:
                continue
            home_id = _find_team(home_name, team_map)
            away_id = _find_team(away_name, team_map)
            if home_id:
                ok = _insert_match(conn, home_id, away_id, away_name,
                                   date_raw, label, hs, as_, "neutral")
                inserted += ok
            if away_id:
                ok = _insert_match(conn, away_id, home_id, home_name,
                                   date_raw, label, as_, hs, "neutral")
                inserted += ok
        time.sleep(0.5)

    conn.commit()
    print(f"  [FD] +{inserted} new rows")
    return inserted


# ── Source 3: api-sports.io (recent fixtures per team) ───────────────────────

def _af_headers() -> dict:
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {"x-rapidapi-host": "api-football-v1.p.rapidapi.com",
            "x-rapidapi-key": AF_KEY}


def _has_api_key() -> bool:
    return bool(APISPORTS_KEY or AF_KEY)


AF_API_BASE = ("https://v3.football.api-sports.io"
               if APISPORTS_KEY else
               "https://api-football-v1.p.rapidapi.com/v3")

# api-sports.io national team IDs for WC2026 qualified teams
AF_NAT_IDS = {
    "Argentina": 26,   "France": 2,      "Brazil": 6,     "Germany": 25,
    "Spain": 9,        "England": 10,    "Portugal": 27,  "Netherlands": 3,
    "Croatia": 1036,   "Switzerland": 15,"Morocco": 1947, "USA": 2,
    "Mexico": 16,      "Canada": 1620,   "Panama": 1887,  "Japan": 23,
    "South Korea": 4,  "Australia": 24,  "Iran": 28,      "Senegal": 1963,
    "Nigeria": 39,     "Ghana": 1492,    "Egypt": 17,     "Cameroon": 1489,
    "Colombia": 19,    "Uruguay": 31,    "Ecuador": 55,   "Chile": 21,
    "Bolivia": 18,     "Venezuela": 17,  "Paraguay": 678, "Saudi Arabia": 36,
    "Qatar": 1450,     "Poland": 5,      "Denmark": 21,   "Turkey": 29,
    "Serbia": 14,      "Austria": 6,     "Belgium": 1,    "Italy": 768,
    "Scotland": 1108,  "Slovakia": 8,    "Romania": 13,   "Slovenia": 36,
    "Ukraine": 1881,   "Georgia": 1882,  "Albania": 1485,
    "Costa Rica": 69,  "Honduras": 63,   "Jamaica": 65,
    "DR Congo": 1493,  "Mali": 1495,     "South Africa": 1497,
    "New Zealand": 1498,"Indonesia": 1350,"Iraq": 1490,   "Jordan": 845,
}

CALLS_MADE = 0
MAX_CALLS   = 80   # stay under 100/day limit, leave buffer


def _af_get(endpoint: str, params: dict, cache_key: str,
            cache_hours: int = 6) -> Optional[dict]:
    global CALLS_MADE
    if CALLS_MADE >= MAX_CALLS:
        return None

    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        age = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
        if age < cache_hours:
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                pass

    if not _has_api_key():
        return None

    url = f"{AF_API_BASE}/{endpoint}"
    try:
        r = requests.get(url, headers=_af_headers(), params=params, timeout=15)
        CALLS_MADE += 1
        if r.status_code == 200:
            data = r.json()
            cache_file.write_text(json.dumps(data))
            remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
            print(f"  [AF] {endpoint} ({list(params.values())}): "
                  f"OK (remaining={remaining}, calls_this_run={CALLS_MADE})")
            return data
        print(f"  [AF] {endpoint}: HTTP {r.status_code}")
    except Exception as e:
        print(f"  [AF] {endpoint} error: {e}")
    return None


def update_from_apisports(conn: sqlite3.Connection, last_n: int = 5) -> int:
    """
    Fetch the most recent N fixtures for each team from api-sports.io.
    Prioritises teams whose last match is oldest.
    Uses at most MAX_CALLS API calls total.
    """
    if not _has_api_key():
        print("  [AF] No API key — skipping")
        return 0

    team_map   = _load_teams(conn)
    inserted   = 0

    # Sort teams by their oldest last-match date (fetch stale teams first)
    team_dates = []
    for name, af_id in AF_NAT_IDS.items():
        tid = _find_team(name, team_map)
        if not tid:
            continue
        last = _get_latest_date(conn, tid)
        team_dates.append((last, name, af_id, tid))
    team_dates.sort()   # oldest first

    for last_date, name, af_id, tid in team_dates:
        if CALLS_MADE >= MAX_CALLS:
            print(f"  [AF] Call budget exhausted ({CALLS_MADE}/{MAX_CALLS})")
            break

        cache_key = f"af_last{last_n}_{af_id}"
        data = _af_get("fixtures", {"team": af_id, "last": last_n},
                       cache_key, cache_hours=6)
        if not data:
            continue

        fixtures = data.get("response", [])
        new_for_team = 0
        for fx in fixtures:
            fix   = fx.get("fixture", {})
            teams = fx.get("teams", {})
            goals = fx.get("goals", {})

            date_raw = (fix.get("date") or "")[:10]
            if not date_raw or date_raw <= last_date:
                continue

            status = fix.get("status", {}).get("short", "")
            if status not in ("FT", "AET", "PEN"):
                continue   # not finished

            home_name = teams.get("home", {}).get("name", "")
            away_name = teams.get("away", {}).get("name", "")
            gf_home   = goals.get("home") or 0
            gf_away   = goals.get("away") or 0
            league    = fx.get("league", {}).get("name", "Friendly")
            venue_raw = fix.get("venue", {}).get("city", "")

            home_id = _find_team(home_name, team_map)
            away_id = _find_team(away_name, team_map)

            is_home   = (home_id == tid)
            my_goals  = gf_home if is_home else gf_away
            opp_goals = gf_away if is_home else gf_home
            opp_name  = away_name if is_home else home_name
            opp_id    = away_id  if is_home else home_id
            venue_str = "home" if is_home else "away"

            ok = _insert_match(conn, tid, opp_id, opp_name, date_raw,
                               league, my_goals, opp_goals, venue_str)
            if ok:
                inserted  += 1
                new_for_team += 1

        if new_for_team:
            print(f"  [AF] {name}: +{new_for_team} new fixtures")

        time.sleep(1.2)   # respect rate limit

    conn.commit()
    print(f"  [AF] Total +{inserted} new rows ({CALLS_MADE} API calls used)")
    return inserted


# ── Coverage report ───────────────────────────────────────────────────────────

def print_coverage(conn: sqlite3.Connection) -> None:
    """Print per-team match counts and latest date."""
    print("\n=== Team Match Coverage ===")
    rows = conn.execute("""
        SELECT t.name, COUNT(tm.id) as n, MAX(tm.date) as latest
        FROM teams t
        LEFT JOIN team_matches tm ON t.id = tm.team_id
        GROUP BY t.id, t.name
        ORDER BY latest ASC NULLS FIRST
    """).fetchall()
    total = 0
    for name, n, latest in rows:
        flag = " ⚠" if (n < 10 or (latest or "") < "2025-01-01") else ""
        print(f"  {name:<25}: {n:>4} matches, last={latest or 'never'}{flag}")
        total += n
    print(f"\n  TOTAL: {total} match rows across {len(rows)} teams")


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    print("\n=== Daily Form Update — All 48 Teams ===\n")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    before = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]

    # 1. Free bulk source — covers all teams, all competitions
    print("--- Source 1: martj42 international results ---")
    n1 = update_from_martj42(conn)

    # 2. football-data.org — WC 2026 matches as they happen (tournament only)
    print("\n--- Source 2: football-data.org (recent WC matches) ---")
    n2 = update_from_football_data_org(conn, days_back=14)

    # 3. api-sports.io — fill gaps with most recent fixtures per team
    print("\n--- Source 3: api-sports.io (fill gaps) ---")
    n3 = update_from_apisports(conn, last_n=5)

    after = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
    print(f"\n=== Summary: {before} → {after} rows (+{after - before} new) ===")

    print_coverage(conn)
    conn.close()


if __name__ == "__main__":
    run()
