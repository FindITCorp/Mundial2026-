"""
update_wc.py — Update WC2026 match results, lineups, and ratings during tournament.

Run after each matchday to keep predictions fresh.
Usage:
  python pipelines/update_wc.py                    # update all pending
  python pipelines/update_wc.py --match-id 5       # update specific match
  python pipelines/update_wc.py --stage group      # update group stage only
"""
import os
import json
import time
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "wc_results"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

AF_BASE = "https://v3.football.api-sports.io"
AF_KEY        = os.getenv("APIFOOT", "")
APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")

def _af_headers() -> dict:
    if APISPORTS_KEY:
        return {"x-apisports-key": APISPORTS_KEY}
    return {"x-rapidapi-host": "v3.football.api-sports.io", "x-rapidapi-key": AF_KEY}
WC2026_AF_LEAGUE_ID = 1  # Update with actual ID when tournament starts


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def update_match_result(
    match_id: int,
    score_home: int,
    score_away: int,
    played: bool = True
) -> bool:
    """Update a WC match result in the DB."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE wc_matches
        SET score_home=?, score_away=?, played=?
        WHERE id=?
    """, (score_home, score_away, int(played), match_id))

    success = cur.rowcount > 0
    conn.commit()
    conn.close()

    if success:
        print(f"  Match {match_id} updated: {score_home}-{score_away}")
    return success


def update_lineup_from_file(match_id: int, lineup_file: str) -> bool:
    """
    Load a lineup from JSON file and save to match_lineups table.
    lineup_file: path to JSON with {home: [...players...], away: [...players...]}
    """
    p = Path(lineup_file)
    if not p.exists():
        print(f"  Lineup file not found: {lineup_file}")
        return False

    with open(p) as f:
        lineup_data = json.load(f)

    conn = get_connection()
    cur = conn.cursor()

    # Get match info
    match = cur.execute(
        "SELECT home_team_id, away_team_id FROM wc_matches WHERE id=?",
        (match_id,)
    ).fetchone()

    if not match:
        conn.close()
        return False

    for side, team_id in [("home", match["home_team_id"]), ("away", match["away_team_id"])]:
        side_players = lineup_data.get(side, {}).get("players", [])
        for player_info in side_players:
            player_name = player_info.get("name", "")
            player_row = cur.execute(
                "SELECT id FROM players WHERE name=? AND team_id=?",
                (player_name, team_id)
            ).fetchone()

            if player_row:
                cur.execute("""
                    INSERT OR REPLACE INTO match_lineups
                        (match_id, team_id, player_id, position, starter)
                    VALUES (?,?,?,?,?)
                """, (
                    match_id, team_id, player_row["id"],
                    player_info.get("position", ""),
                    int(player_info.get("starter", True))
                ))

    conn.commit()
    conn.close()
    print(f"  Lineup updated for match {match_id}")
    return True


def fetch_wc_results_from_api() -> list:
    """Fetch completed WC2026 matches from api-football."""
    if not (APISPORTS_KEY or AF_KEY):
        return []

    cache_file = CACHE_DIR / f"wc_results_{datetime.now().strftime('%Y%m%d')}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    url = f"{AF_BASE}/fixtures"
    headers = _af_headers()
    params = {
        "league": WC2026_AF_LEAGUE_ID,
        "season": 2026,
        "status": "FT",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            results = r.json().get("response", [])
            with open(cache_file, "w") as f:
                json.dump(results, f)
            return results
        print(f"  [AF] Error {r.status_code}")
    except Exception as e:
        print(f"  [AF] Exception: {e}")

    return []


def auto_update_from_api() -> int:
    """Pull results from API and update DB."""
    print("  Fetching WC results from API...")
    results = fetch_wc_results_from_api()

    if not results:
        print("  No API data available.")
        return 0

    conn = get_connection()
    cur = conn.cursor()
    updated = 0

    for fixture in results:
        # Match fixture to our wc_matches by team names and date
        home_name = fixture.get("teams", {}).get("home", {}).get("name", "")
        away_name = fixture.get("teams", {}).get("away", {}).get("name", "")
        date = fixture.get("fixture", {}).get("date", "")[:10]
        goals = fixture.get("goals", {})
        score_home = goals.get("home")
        score_away = goals.get("away")

        if score_home is None or score_away is None:
            continue

        # Find matching wc_match
        wc_match = cur.execute("""
            SELECT id FROM wc_matches
            WHERE (home_team_name LIKE ? OR home_team_name LIKE ?)
              AND date=? AND played=0
        """, (f"%{home_name[:10]}%", f"%{home_name[:6]}%", date)).fetchone()

        if wc_match:
            cur.execute("""
                UPDATE wc_matches SET score_home=?, score_away=?, played=1
                WHERE id=?
            """, (score_home, score_away, wc_match["id"]))
            updated += cur.rowcount

    conn.commit()
    conn.close()
    return updated


def recompute_player_ratings_after_match(match_id: int) -> int:
    """
    After a WC match, recompute player ratings based on actual performance.
    In practice this would parse minute-by-minute events from the API.
    For now, updates based on match result and lineup starters.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    match = cur.execute(
        "SELECT * FROM wc_matches WHERE id=?", (match_id,)
    ).fetchone()

    if not match or not match["played"]:
        conn.close()
        return 0

    lineups = cur.execute(
        "SELECT * FROM match_lineups WHERE match_id=?", (match_id,)
    ).fetchall()

    if not lineups:
        conn.close()
        return 0

    updated = 0
    for lineup in lineups:
        player_id = lineup["player_id"]
        team_id = lineup["team_id"]
        starter = lineup["starter"]

        # Determine if team won/lost
        if team_id == match["home_team_id"]:
            gf = match["score_home"] or 0
            ga = match["score_away"] or 0
        else:
            gf = match["score_away"] or 0
            ga = match["score_home"] or 0

        # Base rating from result
        if gf > ga:
            base_nat = 6.8
        elif gf == ga:
            base_nat = 6.3
        else:
            base_nat = 5.8

        # Reduce for subs
        if not starter:
            base_nat -= 0.3

        cur.execute("""
            INSERT INTO player_ratings (player_id, match_id, context, rating, components)
            VALUES (?,?,'nat',?,?)
        """, (player_id, match_id, round(base_nat, 2), json.dumps({"wc_match": match_id})))
        updated += 1

    conn.commit()
    conn.close()
    return updated


def show_upcoming_matches(days: int = 7) -> None:
    """Show upcoming WC matches in the next N days."""
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (datetime.now() + __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")

    matches = conn.execute("""
        SELECT id, date, time, home_team_name, away_team_name, venue, wc_group, stage
        FROM wc_matches
        WHERE date BETWEEN ? AND ? AND played=0
        ORDER BY date, time
    """, (today, cutoff)).fetchall()

    if not matches:
        print(f"  No upcoming matches in next {days} days.")
        conn.close()
        return

    print(f"\n  Proximos partidos (siguientes {days} dias):\n")
    for m in matches:
        print(f"    [{m['id']:3d}] {m['date']} {m['time']}  "
              f"{m['home_team_name']:<20} vs {m['away_team_name']:<20}  "
              f"({m['venue']})  [{m['stage'].upper()}]")
    conn.close()


def run(match_id: Optional[int] = None, stage: Optional[str] = None):
    """Main pipeline entry point."""
    print("\n=== Pipeline: Update WC Results ===\n")

    if match_id:
        print(f"  Modo: match especifico ID={match_id}")
        n = recompute_player_ratings_after_match(match_id)
        print(f"  {n} ratings actualizados para match {match_id}")
    else:
        print("  Modo: actualizacion automatica desde API")
        n = auto_update_from_api()
        print(f"  {n} partidos actualizados en DB")

    # Show summary
    conn = get_connection()
    played = conn.execute("SELECT COUNT(*) FROM wc_matches WHERE played=1").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM wc_matches WHERE played=0").fetchone()[0]
    conn.close()

    print(f"\n  Partidos jugados: {played}")
    print(f"  Partidos pendientes: {pending}")

    show_upcoming_matches(7)
    print("\nPipeline update_wc completado.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update WC2026 results")
    parser.add_argument("--match-id", type=int, help="Update specific match ID")
    parser.add_argument("--stage", type=str, help="Filter by stage: group|r16|qf|sf|final")
    parser.add_argument("--result", nargs=3, metavar=("MATCH_ID", "HOME_SCORE", "AWAY_SCORE"),
                        help="Manually set result: --result 5 2 1")
    parser.add_argument("--upcoming", action="store_true", help="Show upcoming matches")
    args = parser.parse_args()

    if args.upcoming:
        show_upcoming_matches(14)
    elif args.result:
        mid, sh, sa = int(args.result[0]), int(args.result[1]), int(args.result[2])
        update_match_result(mid, sh, sa)
    else:
        run(match_id=args.match_id, stage=args.stage)
