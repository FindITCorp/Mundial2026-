"""
full_update.py — Master pipeline that runs all pipelines in correct order.

Usage:
  python pipelines/full_update.py               # full refresh
  python pipelines/full_update.py --quick       # skip slow API calls
  python pipelines/full_update.py --teams "Panama" "Croatia"  # specific teams only
  python pipelines/full_update.py --stage wc    # only WC results (during tournament)
"""
import sys
import time
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"


def ensure_db_exists():
    """Run setup_db.py if DB doesn't exist."""
    if not DB_PATH.exists():
        print("  Base de datos no encontrada. Ejecutando setup_db.py...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "scripts" / "setup_db.py")],
            capture_output=False
        )
        return result.returncode == 0
    return True


def step(name: str, fn, *args, **kwargs):
    """Run a pipeline step with timing and error handling."""
    print(f"\n{'='*60}")
    print(f"PASO: {name}")
    print(f"{'='*60}")
    start = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - start
        print(f"  Completado en {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ERROR despues de {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_full_pipeline(
    teams=None,
    quick=False,
    only_wc=False,
    skip_club_stats=False,
):
    """
    Run all pipelines in sequence.

    Order:
    1. Setup DB (if needed)
    2. Fetch teams (update rankings)
    3. Fetch team matches (form data)
    4. Fetch players (squad data)
    5. Fetch club stats (player ratings)
    6. Fetch nat stats (synthesize)
    7. Update WC results (during tournament)
    """
    start_total = time.time()
    print(f"\n{'='*60}")
    print(f"FULL UPDATE PIPELINE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Teams: {teams or 'ALL'}")
    print(f"Quick: {quick}")
    print(f"{'='*60}")

    # Step 0: Ensure DB
    if not ensure_db_exists():
        print("ERROR: No se pudo crear la base de datos. Abortando.")
        return False

    if only_wc:
        # During tournament: just update results
        from pipelines.update_wc import run as update_wc_run
        step("Update WC Results", update_wc_run)
        return True

    # Step 1: Fetch teams
    from pipelines.fetch_teams import run as fetch_teams_run
    step("Fetch Teams (FIFA Rankings)", fetch_teams_run)

    # Step 2: Fetch team matches
    if not quick:
        from pipelines.fetch_team_matches import run as fetch_matches_run
        delay = 0.5 if quick else 2.0
        step("Fetch Team Matches (Last 3 Years)",
             fetch_matches_run, teams=teams, delay_secs=delay)
    else:
        print("\nSaltando fetch_team_matches (modo quick)")

    # Step 3: Fetch players
    from pipelines.fetch_players import run as fetch_players_run
    step("Fetch Players (Squad Lists)", fetch_players_run, teams=teams)

    # Step 4: Fetch club stats
    if not skip_club_stats and not quick:
        from pipelines.fetch_club_stats import run as fetch_club_run
        step("Fetch Club Stats", fetch_club_run, teams=teams)
    else:
        print("\nSaltando fetch_club_stats")

    # Step 5: Fetch nat stats
    from pipelines.fetch_nat_stats import run as fetch_nat_run
    step("Synthesize Nat Stats", fetch_nat_run, teams=teams)

    # Step 6: Update WC results (even before tournament = setup wc_matches)
    from pipelines.update_wc import run as update_wc_run
    step("Update WC Schedule/Results", update_wc_run)

    total_elapsed = time.time() - start_total

    # Final summary
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETADO en {total_elapsed:.0f}s")
    print(f"{'='*60}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tables = ["teams", "players", "team_matches", "wc_matches",
              "wc_history", "player_club_stats", "player_nat_stats",
              "player_ratings", "squad_selections"]

    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:<25}: {count:>6} registros")
        except Exception:
            pass

    conn.close()
    print()

    return True


def run_quick_teams(teams: list):
    """Quick update for specific teams only."""
    print(f"\nActualizacion rapida para: {', '.join(teams)}\n")
    run_full_pipeline(teams=teams, quick=True, skip_club_stats=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master pipeline — Mundial 2026")
    parser.add_argument("--quick", action="store_true",
                        help="Omit slow API calls (skip team_matches)")
    parser.add_argument("--teams", nargs="+",
                        help="Only update specific teams: --teams Panama Croatia")
    parser.add_argument("--wc-only", action="store_true",
                        help="Only update WC results (for use during tournament)")
    parser.add_argument("--skip-club-stats", action="store_true",
                        help="Skip fetching club stats")
    args = parser.parse_args()

    run_full_pipeline(
        teams=args.teams,
        quick=args.quick,
        only_wc=args.wc_only,
        skip_club_stats=args.skip_club_stats,
    )
