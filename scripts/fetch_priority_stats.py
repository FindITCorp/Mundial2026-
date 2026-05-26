"""
Fetch real club stats for priority teams (first-match teams).
Run from repo root: python scripts/fetch_priority_stats.py [team1,team2,...]
"""
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

DEFAULT_PRIORITY = [
    'Mexico', 'Argentina',
    'France', 'Colombia',
    'England', 'Uruguay',
    'Brazil', 'Croatia',
    'Portugal', 'Switzerland',
    'Germany',
    'Belgium', 'Ecuador',
    'Netherlands', 'South Korea',
    'Spain', 'Senegal',
    'Ghana', 'Turkey',
]


def main():
    print("=== fetch_priority_stats.py starting ===")
    print(f"Python: {sys.version}")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"DB exists: {(BASE_DIR / 'data' / 'mundial2026.db').exists()}")

    # Determine teams from env or args
    custom = os.getenv('INPUT_TEAMS', '').strip()
    if custom:
        teams = [t.strip() for t in custom.split(',') if t.strip()]
    elif len(sys.argv) > 1:
        teams = [t.strip() for t in sys.argv[1].split(',') if t.strip()]
    else:
        teams = DEFAULT_PRIORITY

    print(f"Teams to process ({len(teams)}): {teams}")
    print()

    from pipelines.fetch_club_stats import run as run_club_stats
    run_club_stats(teams=teams, force_refresh=True)


if __name__ == '__main__':
    main()
