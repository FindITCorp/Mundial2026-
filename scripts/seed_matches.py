"""
seed_matches.py
Populates team_matches (and optionally updates teams.fifa_rank) from:
  1. martj42/international_results CSV  →  WC 2014 / 2018 / 2022 + recent form
  2. A hand-coded FIFA ranking list     →  fifa_rank column

Real columns in team_matches (from setup_db.py):
    id, team_id, opponent_id, opponent_name, date, competition,
    goals_for, goals_against, result, venue, wc_edition
"""

import sqlite3
import csv
import io
import urllib.request
from pathlib import Path

DB = Path("/home/user/mundial2026/data/mundial2026.db")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def fetch_csv(url: str) -> str:
    """Fetch a URL with a browser-like UA."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


ALIASES: dict[str, str] = {
    # CSV name → DB name (lowercase)
    "south korea": "south korea",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "iran": "iran",
    "ir iran": "iran",
    "islamic republic of iran": "iran",
    "united states": "usa",
    "usa": "usa",
    "us": "usa",
    "côte d'ivoire": "ivory coast",
    "cote d'ivoire": "ivory coast",
    "ivory coast": "ivory coast",
    "republic of ireland": "republic of ireland",
    "czech republic": "czech republic",
    "czechia": "czech republic",
    "bosnia and herzegovina": "bosnia and herzegovina",
    "bosnia & herzegovina": "bosnia and herzegovina",
    "trinidad and tobago": "trinidad and tobago",
    "trinidad & tobago": "trinidad and tobago",
    "guinea-bissau": "guinea-bissau",
    "guinea bissau": "guinea-bissau",
    "dr congo": "dr congo",
    "democratic republic of the congo": "dr congo",
    "congo dr": "dr congo",
    "northern ireland": "northern ireland",
    "chinese taipei": "chinese taipei",
    "new zealand": "new zealand",
    "new caledonia": "new caledonia",
    "cape verde": "cape verde",
    "cape verde islands": "cape verde",
}


def normalize(name: str) -> str:
    n = name.strip().lower()
    return ALIASES.get(n, n)


def build_team_index(conn: sqlite3.Connection) -> dict[str, int]:
    """Return mapping  lowercase_name → team_id  for all DB teams."""
    rows = conn.execute("SELECT id, name FROM teams").fetchall()
    idx: dict[str, int] = {}
    for tid, tname in rows:
        idx[normalize(tname)] = tid
    return idx


def find_team_id(name: str, idx: dict[str, int]) -> int | None:
    key = normalize(name)
    if key in idx:
        return idx[key]
    # partial substring match
    for db_key, tid in idx.items():
        if key in db_key or db_key in key:
            return tid
    return None


def wc_edition_from_competition(comp: str, date: str) -> int | None:
    comp_lower = comp.lower()
    if "world cup" in comp_lower:
        year = int(date[:4])
        # Map to nearest WC year
        if year >= 2022:
            return 2022
        if year >= 2018:
            return 2018
        if year >= 2014:
            return 2014
        if year >= 2010:
            return 2010
        if year >= 2006:
            return 2006
    return None


def map_competition(comp: str) -> str:
    """Normalise competition name for our DB."""
    c = comp.strip()
    return c


def venue_from_neutral(home_team: str, neutral: str, team_name: str) -> str:
    if neutral.strip().upper() == "TRUE":
        return "neutral"
    if normalize(home_team) == normalize(team_name):
        return "home"
    return "away"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure fifa_rank column exists
    cols = [r[1] for r in conn.execute("PRAGMA table_info(teams)").fetchall()]
    if "fifa_rank" not in cols:
        conn.execute("ALTER TABLE teams ADD COLUMN fifa_rank INTEGER DEFAULT 0")
        conn.commit()
        print("Added fifa_rank column to teams")

    team_idx = build_team_index(conn)
    print(f"Loaded {len(team_idx)} teams from DB")

    # ------------------------------------------------------------------
    # STEP 1: Load CSV  (already downloaded to /tmp/international_results.csv)
    # ------------------------------------------------------------------
    csv_path = Path("/tmp/international_results.csv")
    if not csv_path.exists():
        print("Downloading international_results.csv …")
        raw = fetch_csv(
            "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
        )
        csv_path.write_text(raw, encoding="utf-8")
    else:
        print(f"Using cached {csv_path}")

    rows_all = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_all.append(row)

    print(f"CSV rows: {len(rows_all)}")

    # ------------------------------------------------------------------
    # STEP 2: Define which matches to import
    # ------------------------------------------------------------------
    # We want:
    #   A) All FIFA World Cup matches (all years) where at least one team is in our DB
    #   B) All matches 2014-01-01 onwards for any team in our DB
    #      (captures qualifiers, friendlies, Nations League, etc.)
    #   C) Specifically for Panama + Croatia: everything 2022+

    inserted = 0
    skipped_score = 0
    skipped_no_team = 0

    def insert_match(team_id: int, opp_id: int | None, opp_name: str,
                     date: str, comp: str, goals_for: int, goals_against: int,
                     venue: str, wc_ed: int | None):
        nonlocal inserted
        result = "W" if goals_for > goals_against else ("D" if goals_for == goals_against else "L")
        try:
            conn.execute("""
                INSERT OR IGNORE INTO team_matches
                    (team_id, opponent_id, opponent_name, date, competition,
                     goals_for, goals_against, result, venue, wc_edition)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (team_id, opp_id, opp_name, date, comp,
                  goals_for, goals_against, result, venue, wc_ed))
            inserted += 1
        except Exception as e:
            print(f"  Insert error: {e}")

    for row in rows_all:
        date       = row["date"]
        home_team  = row["home_team"]
        away_team  = row["away_team"]
        home_score = row["home_score"]
        away_score = row["away_score"]
        comp       = row["tournament"]
        neutral    = row["neutral"]

        # Skip future / unplayed matches (NA scores)
        if home_score in ("", "NA") or away_score in ("", "NA"):
            skipped_score += 1
            continue

        try:
            hs = int(home_score)
            as_ = int(away_score)
        except ValueError:
            skipped_score += 1
            continue

        year = int(date[:4])

        # Decide if we care about this match:
        # WC matches: all years.  All others: from 2014 onwards.
        is_wc = "FIFA World Cup" in comp and "qualification" not in comp
        if not is_wc and year < 2014:
            continue

        home_id = find_team_id(home_team, team_idx)
        away_id = find_team_id(away_team, team_idx)

        if home_id is None and away_id is None:
            skipped_no_team += 1
            continue

        comp_norm = map_competition(comp)
        wc_ed     = wc_edition_from_competition(comp, date)

        if home_id is not None:
            v = venue_from_neutral(home_team, neutral, home_team)
            insert_match(home_id, away_id, away_team, date, comp_norm,
                         hs, as_, v, wc_ed)

        if away_id is not None:
            v = venue_from_neutral(home_team, neutral, away_team)
            insert_match(away_id, home_id, home_team, date, comp_norm,
                         as_, hs, v, wc_ed)

    conn.commit()
    print(f"\nInserted {inserted} rows  |  skipped_score={skipped_score}  skipped_no_team={skipped_no_team}")

    # ------------------------------------------------------------------
    # STEP 3: FIFA rankings (hand-coded, current ~May 2026)
    # Based on public FIFA ranking lists (March 2026 release)
    # ------------------------------------------------------------------
    rankings = {
        # name (lowercase) → rank
        "argentina":    1,
        "spain":        2,
        "france":       3,
        "england":      4,
        "brazil":       5,
        "portugal":     6,
        "netherlands":  7,
        "belgium":      8,
        "italy":        9,
        "germany":      10,
        "croatia":      11,
        "colombia":     12,
        "morocco":      13,
        "usa":          14,
        "senegal":      15,
        "japan":        16,
        "mexico":       17,
        "switzerland":  18,
        "denmark":      19,
        "south korea":  20,
        "uruguay":      21,
        "canada":       22,
        "turkey":       23,
        "austria":      24,
        "nigeria":      25,
        "iran":         26,
        "scotland":     27,
        "australia":    28,
        "ecuador":      29,
        "poland":       30,
        "serbia":       31,
        "hungary":      32,
        "egypt":        33,
        "ghana":        34,
        "venezuela":    35,
        "bolivia":      36,
        "romania":      37,
        "slovakia":     38,
        "iraq":         39,
        "cameroon":     40,
        "saudi arabia": 41,
        "slovenia":     42,
        "dr congo":     43,
        "panama":       44,
        "jamaica":      45,
        "costa rica":   46,
        "paraguay":     47,
        "jordan":       48,
        "honduras":     49,
    }

    rank_updated = 0
    for team_name_lower, rank in rankings.items():
        tid = find_team_id(team_name_lower, team_idx)
        if tid:
            conn.execute("UPDATE teams SET fifa_rank=? WHERE id=?", (rank, tid))
            rank_updated += 1

    conn.commit()
    print(f"Updated fifa_rank for {rank_updated} teams")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n=== DB SUMMARY ===")
    total = conn.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0]
    print(f"team_matches total: {total} rows")

    print("\nBy competition (top 20):")
    rows_comp = conn.execute("""
        SELECT competition, COUNT(*) as cnt
        FROM team_matches
        GROUP BY competition
        ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()
    for r in rows_comp:
        print(f"  {r[0]:50s} {r[1]}")

    print("\nBy WC edition:")
    rows_wc = conn.execute("""
        SELECT wc_edition, COUNT(*) as cnt
        FROM team_matches
        WHERE wc_edition IS NOT NULL
        GROUP BY wc_edition
        ORDER BY wc_edition
    """).fetchall()
    for r in rows_wc:
        print(f"  WC {r[0]}: {r[1]} rows")

    print("\nRows per team (top 20):")
    rows_team = conn.execute("""
        SELECT t.name, COUNT(*) as cnt
        FROM team_matches tm
        JOIN teams t ON t.id = tm.team_id
        GROUP BY t.id
        ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()
    for r in rows_team:
        print(f"  {r[0]:30s} {r[1]}")

    print("\nPanama last 10 matches:")
    panama = conn.execute("""
        SELECT tm.date, tm.opponent_name, tm.goals_for, tm.goals_against,
               tm.result, tm.competition
        FROM team_matches tm
        JOIN teams t ON t.id = tm.team_id
        WHERE t.name = 'Panama'
        ORDER BY tm.date DESC
        LIMIT 10
    """).fetchall()
    for r in panama:
        print(f"  {r[0]}  vs {r[1]:25s} {r[2]}-{r[3]} {r[4]}  ({r[5]})")

    print("\nCroatia last 10 matches:")
    croatia = conn.execute("""
        SELECT tm.date, tm.opponent_name, tm.goals_for, tm.goals_against,
               tm.result, tm.competition
        FROM team_matches tm
        JOIN teams t ON t.id = tm.team_id
        WHERE t.name = 'Croatia'
        ORDER BY tm.date DESC
        LIMIT 10
    """).fetchall()
    for r in croatia:
        print(f"  {r[0]}  vs {r[1]:25s} {r[2]}-{r[3]} {r[4]}  ({r[5]})")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
