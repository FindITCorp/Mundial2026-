"""
fetch_football_data_org.py — Pipeline using football-data.org API (v4).

Endpoints:
  - WC2026 match schedule
  - National team results (last 3 years)
  - Group standings

Cache: data/cache/football_data_org/ (24h TTL)
API base: https://api.football-data.org/v4
Header: X-Auth-Token from env FOOTBALL_DATA_KEY

Usage:
  python pipelines/fetch_football_data_org.py --schedule
  python pipelines/fetch_football_data_org.py --history "Panama"
  python pipelines/fetch_football_data_org.py --standings
  python pipelines/fetch_football_data_org.py --all
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
CACHE_DIR  = BASE_DIR / "data" / "cache" / "football_data_org"
DB_PATH    = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://api.football-data.org/v4"
FD_KEY   = os.getenv("FOOTBALL_DATA_KEY", "")

# ── Team code mapping: our team names → football-data.org team codes ─────────
TEAM_CODES = {
    "Argentina":    "ARG",
    "France":       "FRA",
    "Brazil":       "BRA",
    "Germany":      "GER",
    "Spain":        "ESP",
    "England":      "ENG",
    "Portugal":     "POR",
    "Netherlands":  "NED",
    "Mexico":       "MEX",
    "USA":          "USA",
    "Croatia":      "CRO",
    "Panama":       "PAN",
    "Morocco":      "MAR",
    "Japan":        "JPN",
    "Senegal":      "SEN",
    "Belgium":      "BEL",
    "Switzerland":  "SUI",
    "Colombia":     "COL",
    "Uruguay":      "URU",
    "Italy":        "ITA",
    "Denmark":      "DEN",
    "South Korea":  "KOR",
    "Canada":       "CAN",
    "Ecuador":      "ECU",
    "Australia":    "AUS",
    "Poland":       "POL",
    "Serbia":       "SRB",
    "Nigeria":      "NGA",
    "Turkey":       "TUR",
    "Saudi Arabia": "KSA",
    "Egypt":        "EGY",
    "Austria":      "AUT",
    "Honduras":     "HON",
    "Jamaica":      "JAM",
    "Bolivia":      "BOL",
    "Paraguay":     "PAR",
    "Venezuela":    "VEN",
    "Ghana":        "GHA",
    "Hungary":      "HUN",
    "Scotland":     "SCO",
    "Romania":      "ROU",
    "DR Congo":     "COD",
    "Cameroon":     "CMR",
    "Slovenia":     "SVN",
    "Costa Rica":   "CRC",
    "Jordan":       "JOR",
    "Iraq":         "IRQ",
    "New Zealand":  "NZL",
    "Chile":        "CHI",
    "Peru":         "PER",
    "Algeria":      "ALG",
    "Mali":         "MLI",
    "Ivory Coast":  "CIV",
    "Qatar":        "QAT",
    "South Africa": "RSA",
    "Tunisia":      "TUN",
}

# football-data.org team IDs for national teams
TEAM_FD_IDS = {
    "England":      66,
    "Germany":      759,
    "Spain":        760,
    "France":       773,
    "Brazil":       764,
    "Argentina":    762,
    "Portugal":     765,
    "Netherlands":  806,
    "Belgium":      805,
    "Croatia":      799,
    "Switzerland":  788,
    "Mexico":       972,
    "Uruguay":      769,
    "Colombia":     771,
    "Italy":        784,
    "Denmark":      782,
    "Japan":        819,
    "South Korea":  732,
    "Morocco":      1978,
    "USA":          762,
    "Poland":       794,
    "Serbia":       1961,
    "Ecuador":      1920,
    "Senegal":      1960,
    "Australia":    780,
    "Canada":       768,
    "Saudi Arabia": 1949,
}

# WC2026 competition code on football-data.org
WC2026_CODE = "WC"


# ── Cache management ──────────────────────────────────────────────────────────

def _cache_file(key: str) -> Path:
    safe = key.replace("/", "_").replace(" ", "_").replace("?", "_")
    return CACHE_DIR / f"{safe}.json"


def _cache_valid(key: str, max_age_hours: float = 24.0) -> bool:
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

def _api_get(path: str, params: Optional[dict] = None,
             cache_key: Optional[str] = None,
             max_age_hours: float = 24.0) -> Optional[dict]:
    """
    Make a football-data.org GET request with caching.
    Returns JSON dict or None on error.
    """
    ck = cache_key or path.replace("/", "_")

    if _cache_valid(ck, max_age_hours):
        cached = _load_cache(ck)
        if cached is not None:
            return cached

    if not FD_KEY:
        print(f"  [FD] Sin FOOTBALL_DATA_KEY — saltando {path}")
        return None

    url = f"{API_BASE}/{path.lstrip('/')}"
    headers = {"X-Auth-Token": FD_KEY}

    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=15)

        if r.status_code == 200:
            data = r.json()
            _save_cache(ck, data)
            print(f"  [FD] {path}: OK")
            return data
        elif r.status_code == 429:
            # Rate limited — football-data.org allows 10 req/min on free tier
            print(f"  [FD] Rate limited. Waiting 65s...")
            time.sleep(65)
            # Retry once
            r2 = requests.get(url, headers=headers, params=params or {}, timeout=15)
            if r2.status_code == 200:
                data = r2.json()
                _save_cache(ck, data)
                return data
        elif r.status_code == 403:
            print(f"  [FD] 403 Forbidden — check your API tier for {path}")
        elif r.status_code == 404:
            print(f"  [FD] 404 Not Found: {path}")
        else:
            print(f"  [FD] Error {r.status_code}: {r.text[:200]}")

    except Exception as e:
        print(f"  [FD] Exception on {path}: {e}")

    return None


# ── Public functions ──────────────────────────────────────────────────────────

def fetch_wc_schedule() -> Optional[list]:
    """
    Fetch WC2026 match schedule from football-data.org.

    Returns:
        List of match dicts or None
    """
    print("\n  Fetching WC2026 schedule...")
    data = _api_get(
        f"competitions/{WC2026_CODE}/matches",
        cache_key="fd_wc2026_schedule",
        max_age_hours=6.0,  # Refresh schedule more frequently during tournament
    )

    if not data:
        return None

    matches = []
    for m in data.get("matches", []):
        home = m.get("homeTeam", {})
        away = m.get("awayTeam", {})
        score = m.get("score", {})
        ft = score.get("fullTime", {})

        match_date = m.get("utcDate", "")[:10]
        match_time = m.get("utcDate", "")[11:16] if len(m.get("utcDate", "")) > 10 else ""

        home_goals = ft.get("home")
        away_goals = ft.get("away")
        played = (home_goals is not None and away_goals is not None)

        matches.append({
            "id": m.get("id"),
            "date": match_date,
            "time": match_time,
            "stage": m.get("stage", "").lower().replace(" ", "_"),
            "group": m.get("group"),
            "home_team": home.get("name", ""),
            "away_team": away.get("name", ""),
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "played": played,
            "status": m.get("status", ""),
            "venue": m.get("venue", ""),
        })

    print(f"  WC schedule: {len(matches)} matches fetched")
    return matches


def fetch_team_history(team_code: str, years_back: int = 3) -> Optional[list]:
    """
    Fetch last N years of national team results.

    Args:
        team_code: Team code (e.g., "PAN", "CRO") or team name
        years_back: Number of years of history to fetch

    Returns:
        List of match dicts or None
    """
    # Resolve team code
    if len(team_code) > 3:
        # It's a team name, convert to code
        code = TEAM_CODES.get(team_code)
        team_name = team_code
        if not code:
            print(f"  [FD] Team '{team_code}' not found in TEAM_CODES")
            return None
    else:
        code = team_code.upper()
        # Find team name
        team_name = next((k for k, v in TEAM_CODES.items() if v == code), code)

    # Try to get team ID
    fd_id = TEAM_FD_IDS.get(team_name)

    if fd_id:
        # Fetch recent matches via team endpoint
        date_from = (datetime.now() - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")
        cache_key = f"fd_team_{fd_id}_matches_{date_from}"
        data = _api_get(
            f"teams/{fd_id}/matches",
            params={"dateFrom": date_from, "competitions": "WCQ,WC,NL,EC,CA"},
            cache_key=cache_key,
        )

        if data:
            matches = []
            for m in data.get("matches", []):
                home = m.get("homeTeam", {})
                away = m.get("awayTeam", {})
                score = m.get("score", {})
                ft = score.get("fullTime", {})

                match_date = m.get("utcDate", "")[:10]
                is_home = (home.get("id") == fd_id)
                home_goals = ft.get("home") if ft.get("home") is not None else 0
                away_goals = ft.get("away") if ft.get("away") is not None else 0
                gf = home_goals if is_home else away_goals
                ga = away_goals if is_home else home_goals

                if gf > ga:
                    result = "W"
                elif gf < ga:
                    result = "L"
                else:
                    result = "D"

                opp_name = (away.get("name", "") if is_home else home.get("name", ""))
                matches.append({
                    "date": match_date,
                    "competition": m.get("competition", {}).get("name", ""),
                    "opponent": opp_name,
                    "goals_for": gf,
                    "goals_against": ga,
                    "result": result,
                    "venue": "home" if is_home else "away",
                    "status": m.get("status", ""),
                })

            print(f"  {team_name}: {len(matches)} matches fetched")
            return matches

    # Fallback: try competition-based search
    print(f"  [FD] No team ID for '{team_name}'. Trying competition search...")
    return None


def fetch_standings() -> Optional[list]:
    """
    Fetch current WC2026 group standings.

    Returns:
        List of standing group dicts or None
    """
    print("\n  Fetching WC2026 standings...")
    data = _api_get(
        f"competitions/{WC2026_CODE}/standings",
        cache_key="fd_wc2026_standings",
        max_age_hours=2.0,  # Refresh standings frequently during tournament
    )

    if not data:
        return None

    standings = []
    for group_data in data.get("standings", []):
        group_name = group_data.get("group", "")
        group_type = group_data.get("type", "")

        if group_type != "TOTAL":
            continue

        group = {
            "group": group_name,
            "table": [],
        }

        for entry in group_data.get("table", []):
            team = entry.get("team", {})
            group["table"].append({
                "position": entry.get("position", 0),
                "team_name": team.get("name", ""),
                "team_id": team.get("id"),
                "played": entry.get("playedGames", 0),
                "won": entry.get("won", 0),
                "draw": entry.get("draw", 0),
                "lost": entry.get("lost", 0),
                "goals_for": entry.get("goalsFor", 0),
                "goals_against": entry.get("goalsAgainst", 0),
                "goal_diff": entry.get("goalDifference", 0),
                "points": entry.get("points", 0),
            })

        standings.append(group)

    print(f"  Standings: {len(standings)} groups fetched")
    return standings


# ── DB Save helpers ───────────────────────────────────────────────────────────

def _save_schedule_to_db(matches: list) -> int:
    """Save WC2026 schedule to wc_matches table."""
    if not matches:
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Build name→id map
    team_map = {}
    for row in cur.execute("SELECT id, name FROM teams"):
        team_map[row["name"]] = row["id"]

    def find_team_id(name: str) -> Optional[int]:
        if name in team_map:
            return team_map[name]
        for k, v in team_map.items():
            if name.lower() in k.lower() or k.lower() in name.lower():
                return v
        return None

    updated = 0
    inserted = 0

    for m in matches:
        home_id = find_team_id(m.get("home_team", ""))
        away_id = find_team_id(m.get("away_team", ""))

        # Update existing match if result is available
        if m.get("played") and m.get("id"):
            cur.execute("""
                UPDATE wc_matches
                SET score_home=?, score_away=?, played=1
                WHERE id=?
            """, (m["home_goals"], m["away_goals"], m["id"]))
            if cur.rowcount:
                updated += 1

        # Try to insert new match
        cur.execute("""
            INSERT OR IGNORE INTO wc_matches
                (id, date, time, home_team_id, away_team_id,
                 home_team_name, away_team_name, wc_group, stage,
                 score_home, score_away, played)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            m.get("id"), m.get("date"), m.get("time"),
            home_id, away_id,
            m.get("home_team", ""), m.get("away_team", ""),
            m.get("group"), m.get("stage", "group"),
            m.get("home_goals"), m.get("away_goals"),
            1 if m.get("played") else 0,
        ))
        if cur.rowcount:
            inserted += 1

    conn.commit()
    conn.close()
    print(f"  Schedule saved: {inserted} inserted, {updated} updated")
    return inserted + updated


def _save_team_history_to_db(team_name: str, matches: list) -> int:
    """Save team match history to team_matches table."""
    if not matches:
        return 0

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

    for m in matches:
        if not m.get("date") or m.get("status") not in ("FINISHED", ""):
            continue

        opp_name = m.get("opponent", "")
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


def _save_standings_to_db(standings: list) -> int:
    """
    Update wc_group field in teams table based on WC standings.
    """
    if not standings:
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    updated = 0
    for group_data in standings:
        group_name = group_data.get("group", "")
        # Extract letter: "GROUP_A" -> "A"
        if "_" in group_name:
            group_letter = group_name.split("_")[-1]
        else:
            group_letter = group_name

        for entry in group_data.get("table", []):
            team_name = entry.get("team_name", "")
            if not team_name:
                continue
            cur.execute("""
                UPDATE teams SET wc_group=? WHERE name=? OR name LIKE ?
            """, (group_letter, team_name, f"%{team_name}%"))
            updated += cur.rowcount

    conn.commit()
    conn.close()
    return updated


# ── High-level pipeline ───────────────────────────────────────────────────────

def run_full_fetch(teams: Optional[list] = None, delay_secs: float = 3.0) -> dict:
    """
    Run complete football-data.org data fetch.
    Fetches: schedule, team histories, standings.

    Returns summary dict.
    """
    print("\n=== football-data.org Full Fetch ===\n")

    if not FD_KEY:
        print("  Sin FOOTBALL_DATA_KEY — saltando fetch")
        return {"schedule": 0, "histories": 0, "standings": 0}

    # 1. Schedule
    schedule = fetch_wc_schedule()
    schedule_saved = _save_schedule_to_db(schedule) if schedule else 0
    time.sleep(delay_secs)

    # 2. Standings
    standings = fetch_standings()
    standings_saved = _save_standings_to_db(standings) if standings else 0
    time.sleep(delay_secs)

    # 3. Team histories
    team_list = teams or list(TEAM_FD_IDS.keys())
    histories_total = 0

    for team_name in team_list:
        if not FD_KEY:
            break
        print(f"  Fetching history: {team_name}")
        history = fetch_team_history(team_name, years_back=3)
        if history:
            saved = _save_team_history_to_db(team_name, history)
            histories_total += saved
            print(f"    -> {saved} matches saved")
        time.sleep(delay_secs)

    print(f"\nfootball-data.org fetch complete:")
    print(f"  Schedule: {schedule_saved} records")
    print(f"  Standings: {standings_saved} updates")
    print(f"  Team histories: {histories_total} matches")

    return {
        "schedule": schedule_saved,
        "histories": histories_total,
        "standings": standings_saved,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="football-data.org pipeline")
    parser.add_argument("--schedule", action="store_true",
                        help="Fetch WC2026 match schedule")
    parser.add_argument("--history", type=str, metavar="TEAM",
                        help="Fetch team history: --history 'Panama'")
    parser.add_argument("--standings", action="store_true",
                        help="Fetch current WC2026 group standings")
    parser.add_argument("--all", action="store_true",
                        help="Run full fetch (schedule + histories + standings)")
    parser.add_argument("--save", action="store_true",
                        help="Save fetched data to DB (default: just print)")
    args = parser.parse_args()

    if args.schedule:
        matches = fetch_wc_schedule()
        if matches:
            print(f"\nWC2026 Schedule ({len(matches)} matches):")
            for m in matches[:10]:
                played_str = f" [{m['home_goals']}-{m['away_goals']}]" if m["played"] else ""
                print(f"  {m['date']} | {m['home_team']:<22} vs {m['away_team']:<22}{played_str}")
            if len(matches) > 10:
                print(f"  ... and {len(matches)-10} more")
        if args.save and matches:
            n = _save_schedule_to_db(matches)
            print(f"  Saved {n} records to DB")

    elif args.history:
        matches = fetch_team_history(args.history, years_back=3)
        if matches:
            print(f"\n{args.history} history ({len(matches)} matches):")
            for m in matches[:10]:
                print(f"  {m['date']} vs {m['opponent']:<22} {m['goals_for']}-{m['goals_against']} [{m['result']}] | {m['competition']}")
        if args.save and matches:
            n = _save_team_history_to_db(args.history, matches)
            print(f"  Saved {n} records to DB")

    elif args.standings:
        standings = fetch_standings()
        if standings:
            for group_data in standings:
                print(f"\nGroup {group_data['group']}:")
                for entry in group_data["table"]:
                    print(f"  {entry['position']}. {entry['team_name']:<22} "
                          f"P{entry['played']} W{entry['won']} D{entry['draw']} L{entry['lost']} "
                          f"GF{entry['goals_for']} GA{entry['goals_against']} +{entry['goal_diff']} "
                          f"Pts:{entry['points']}")
        if args.save and standings:
            n = _save_standings_to_db(standings)
            print(f"  Updated {n} team groups")

    elif args.all:
        run_full_fetch()

    else:
        parser.print_help()
        print(f"\n  API Key configured: {'YES' if FD_KEY else 'NO (set FOOTBALL_DATA_KEY)'}")
