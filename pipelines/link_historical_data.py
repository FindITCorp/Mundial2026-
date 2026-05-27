"""
link_historical_data.py — Fix data linkage gaps across historical tables.

Three parts:
  A. Fix opponent_id NULLs in team_matches by resolving opponent names to team IDs
     via exact match, alias lookup, slug match, or partial match.
  B. Link player_nat_stats.match_id to team_matches.id using player's team + date.
  C. Add team_match_id column to match_lineups and populate it from match_players
     (starters only), joining on team_id + match_date to find the team_matches row.

Usage:
    python -m pipelines.link_historical_data          # run all three parts
    python -m pipelines.link_historical_data A        # run only Part A
    python -m pipelines.link_historical_data B C      # run Parts B and C
"""

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# ---------------------------------------------------------------------------
# Alias table: maps non-canonical name variants to the canonical team name
# used in the `teams` table.
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # Bosnia variants
    "Bosnia":                        "Bosnia and Herzegovina",
    "Bosnia-Herzegovina":            "Bosnia and Herzegovina",
    "Bosnia & Herzegovina":          "Bosnia and Herzegovina",
    # Ivory Coast variants
    "Côte d'Ivoire":                 "Ivory Coast",
    "Cote d'Ivoire":                 "Ivory Coast",
    "Cote d Ivoire":                 "Ivory Coast",
    "MTN Ligue 1":                   "Ivory Coast",
    # Czech Republic
    "Czech Republic":                "Czechia",
    "Czech":                         "Czechia",
    # South Korea variants
    "Korea Republic":                "South Korea",
    "Republic of Korea":             "South Korea",
    "Korea, Republic of":            "South Korea",
    "Korea":                         "South Korea",
    # Iran variants
    "IR Iran":                       "Iran",
    "Islamic Republic of Iran":      "Iran",
    # USA variants
    "United States":                 "USA",
    "United States of America":      "USA",
    "US":                            "USA",
    # DR Congo variants
    "DR Congo":                      "DR Congo",
    "Congo DR":                      "DR Congo",
    "Democratic Republic of Congo":  "DR Congo",
    "Congo, DR":                     "DR Congo",
    "Congo DR (DRC)":                "DR Congo",
    # Saudi Arabia variants
    "Saudi Arabia":                  "Saudi Arabia",
    "KSA":                           "Saudi Arabia",
    "Kingdom of Saudi Arabia":       "Saudi Arabia",
    # Trinidad & Tobago
    "Trinidad & Tobago":             "Trinidad and Tobago",
    "Trinidad and Tobago":           "Trinidad and Tobago",
    # Ireland variants
    "Republic of Ireland":           "Ireland",
    "Rep of Ireland":                "Ireland",
    # China variants
    "China PR":                      "China",
    "People's Republic of China":    "China",
    "PR China":                      "China",
    # North Korea
    "Korea DPR":                     "North Korea",
    "DPR Korea":                     "North Korea",
    "Democratic People's Republic of Korea": "North Korea",
    # North Macedonia
    "Macedonia":                     "North Macedonia",
    "FYR Macedonia":                 "North Macedonia",
    "Republic of North Macedonia":   "North Macedonia",
    # Netherlands
    "Holland":                       "Netherlands",
    # Kyrgyz Republic
    "Kyrgyz Republic":               "Kyrgyzstan",
    # Other common alternates
    "Russian Federation":            "Russia",
    "Slovak Republic":               "Slovakia",
    "Chinese Taipei":                "Taiwan",
    "Cabo Verde":                    "Cape Verde",
}


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Part A — Fix opponent_id in team_matches
# ---------------------------------------------------------------------------

def _build_lookup_maps(cur: sqlite3.Cursor) -> tuple[dict, dict, dict]:
    """
    Build three lookup dicts for the teams table:
      - name_to_id:  {lower(name) -> id}
      - slug_to_id:  {slug -> id}
      - id_to_name:  {id -> name}  (for reporting)
    """
    rows = cur.execute("SELECT id, name, slug FROM teams").fetchall()
    name_to_id = {r["name"].lower(): r["id"] for r in rows}
    slug_to_id = {r["slug"]: r["id"] for r in rows}
    id_to_name = {r["id"]: r["name"] for r in rows}
    return name_to_id, slug_to_id, id_to_name


def resolve_opponent_id(
    opponent_name: str,
    name_to_id: dict,
    slug_to_id: dict,
) -> Optional[int]:
    """
    Try multiple strategies to resolve an opponent_name to a team id.
    Returns None if no match found.
    """
    if not opponent_name:
        return None

    # 1. Exact name match (case-insensitive)
    key = opponent_name.strip().lower()
    if key in name_to_id:
        return name_to_id[key]

    # 2. Alias lookup
    canonical = ALIASES.get(opponent_name.strip()) or ALIASES.get(opponent_name.strip().title())
    if canonical:
        ckey = canonical.lower()
        if ckey in name_to_id:
            return name_to_id[ckey]

    # 3. Slug match: derive slug the same way teams table does
    slug = opponent_name.strip().lower().replace(" ", "_").replace(".", "").replace("'", "")
    if slug in slug_to_id:
        return slug_to_id[slug]

    # 4. Partial match: opponent_name is a substring of a team name or vice-versa
    for team_name_lower, tid in name_to_id.items():
        if key in team_name_lower or team_name_lower in key:
            return tid

    return None


def fix_opponent_ids(cur: sqlite3.Cursor) -> int:
    """
    Find all team_matches rows where opponent_id IS NULL and try to resolve
    the opponent_name to a team id. Updates opponent_id in place.

    Returns the count of rows updated.
    """
    name_to_id, slug_to_id, id_to_name = _build_lookup_maps(cur)

    rows = cur.execute(
        "SELECT id, opponent_name FROM team_matches WHERE opponent_id IS NULL"
    ).fetchall()
    print(f"  Found {len(rows)} team_matches rows with NULL opponent_id")

    updated = 0
    unresolved_names: set[str] = set()

    for row in rows:
        opp_name = row["opponent_name"]
        opp_id = resolve_opponent_id(opp_name, name_to_id, slug_to_id)
        if opp_id is not None:
            cur.execute(
                "UPDATE team_matches SET opponent_id=? WHERE id=?",
                (opp_id, row["id"]),
            )
            updated += 1
        else:
            unresolved_names.add(opp_name or "(NULL)")

    print(f"  Updated {updated} rows")
    if unresolved_names:
        sorted_names = sorted(unresolved_names)
        print(f"  Could not resolve {len(unresolved_names)} distinct opponent names:")
        for n in sorted_names[:30]:
            print(f"    - {n!r}")
        if len(sorted_names) > 30:
            print(f"    ... and {len(sorted_names) - 30} more")

    return updated


# ---------------------------------------------------------------------------
# Part B — Link player_nat_stats to team_matches
# ---------------------------------------------------------------------------

def link_nat_stats_to_matches(cur: sqlite3.Cursor) -> int:
    """
    For each player_nat_stats record with match_id=NULL:
      1. Get the player's team_id from the players table.
      2. Find team_matches rows with the same team_id and match date.
      3. If exactly 1 match found, set match_id and opponent.

    Returns count of rows updated.
    """
    rows = cur.execute(
        "SELECT id, player_id, match_date FROM player_nat_stats WHERE match_id IS NULL"
    ).fetchall()
    print(f"  Found {len(rows)} player_nat_stats rows with NULL match_id")

    updated = 0
    ambiguous = 0
    no_match = 0

    for row in rows:
        player_id = row["player_id"]
        match_date = row["match_date"]

        if not match_date:
            no_match += 1
            continue

        # Get player's team_id
        player = cur.execute(
            "SELECT team_id FROM players WHERE id=?", (player_id,)
        ).fetchone()
        if not player or not player["team_id"]:
            no_match += 1
            continue

        team_id = player["team_id"]

        # Find team_match(es) with same team + date
        matches = cur.execute(
            """
            SELECT id, opponent_name FROM team_matches
            WHERE team_id=? AND date=?
            ORDER BY id ASC
            """,
            (team_id, match_date),
        ).fetchall()

        if len(matches) >= 1:
            # If duplicates exist (same match stored twice), take the lowest-id row
            tm = matches[0]
            cur.execute(
                """
                UPDATE player_nat_stats
                SET match_id=?, opponent=?
                WHERE id=?
                """,
                (tm["id"], tm["opponent_name"], row["id"]),
            )
            updated += 1
        else:
            no_match += 1

    print(f"  Updated {updated} rows")
    if ambiguous:
        print(f"  Skipped {ambiguous} ambiguous rows (multiple matches same date/team)")
    if no_match:
        print(f"  Could not resolve {no_match} rows (no team_matches found)")

    return updated


# ---------------------------------------------------------------------------
# Part C — Populate match_lineups from match_players
# ---------------------------------------------------------------------------

def _ensure_team_match_id_column(cur: sqlite3.Cursor) -> None:
    """
    Ensure match_lineups has team_match_id column and that match_id is nullable.

    SQLite cannot ALTER COLUMN to drop NOT NULL, so we recreate the table when
    needed (copying any existing rows) and add team_match_id in one pass.
    """
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(match_lineups)").fetchall()}

    needs_recreate = "team_match_id" not in cols

    # Also check if match_id is nullable (notnull=0 in PRAGMA table_info)
    col_info = {r["name"]: r["notnull"] for r in cur.execute("PRAGMA table_info(match_lineups)").fetchall()}
    if col_info.get("match_id", 1) != 0:
        needs_recreate = True  # match_id is still NOT NULL — recreate

    if not needs_recreate:
        print("  match_lineups schema already up-to-date")
        return

    print("  Recreating match_lineups to make match_id nullable and add team_match_id ...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS match_lineups_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER REFERENCES wc_matches(id),
            team_id         INTEGER NOT NULL REFERENCES teams(id),
            player_id       INTEGER NOT NULL REFERENCES players(id),
            position        TEXT,
            starter         INTEGER DEFAULT 1,
            team_match_id   INTEGER REFERENCES team_matches(id)
        )
    """)
    # Copy existing rows (all existing rows reference wc_matches so match_id is set)
    cur.execute("""
        INSERT INTO match_lineups_new (id, match_id, team_id, player_id, position, starter)
        SELECT id, match_id, team_id, player_id, position, starter
        FROM match_lineups
    """)
    cur.execute("DROP TABLE match_lineups")
    cur.execute("ALTER TABLE match_lineups_new RENAME TO match_lineups")
    print("  match_lineups recreated successfully")


def populate_match_lineups(cur: sqlite3.Cursor) -> int:
    """
    For each started=1 record in match_players:
      1. Look up the team_match by team_id + match_date in team_matches.
      2. If exactly 1 team_match found and player_id exists in players table,
         insert into match_lineups (skipping duplicates).

    Returns count of rows inserted.
    """
    # Fetch all started players from match_players that have a valid player_id
    rows = cur.execute(
        """
        SELECT mp.player_id, mp.team_id, mp.match_date, mp.position,
               mp.started, mp.fixture_api_id
        FROM match_players mp
        WHERE mp.started = 1
          AND mp.player_id IS NOT NULL
          AND mp.player_id IN (SELECT id FROM players)
        ORDER BY mp.team_id, mp.match_date
        """
    ).fetchall()
    print(f"  Found {len(rows)} started match_players records with valid player_id")

    # Pre-build a lookup: (team_id, date) -> team_matches.id
    # There may be multiple team_matches for same team+date (theoretically shouldn't happen,
    # but guard against it).
    tm_rows = cur.execute(
        "SELECT id, team_id, date FROM team_matches"
    ).fetchall()
    team_date_to_tm: dict[tuple, list[int]] = {}
    for tm in tm_rows:
        key = (tm["team_id"], tm["date"])
        team_date_to_tm.setdefault(key, []).append(tm["id"])

    # Track existing lineups to avoid re-inserting
    existing = set()
    for ex in cur.execute(
        "SELECT team_match_id, team_id, player_id FROM match_lineups WHERE team_match_id IS NOT NULL"
    ).fetchall():
        existing.add((ex["team_match_id"], ex["team_id"], ex["player_id"]))

    inserted = 0
    skipped_no_tm = 0
    skipped_ambiguous = 0
    skipped_duplicate = 0

    for row in rows:
        key = (row["team_id"], row["match_date"])
        tm_ids = team_date_to_tm.get(key)

        if not tm_ids:
            skipped_no_tm += 1
            continue

        # If duplicates exist, take the lowest-id team_match
        tm_id = min(tm_ids)
        dedup_key = (tm_id, row["team_id"], row["player_id"])
        if dedup_key in existing:
            skipped_duplicate += 1
            continue

        cur.execute(
            """
            INSERT INTO match_lineups (match_id, team_id, player_id, position, starter, team_match_id)
            VALUES (NULL, ?, ?, ?, ?, ?)
            """,
            (
                row["team_id"],
                row["player_id"],
                row["position"],
                row["started"],
                tm_id,
            ),
        )
        existing.add(dedup_key)
        inserted += 1

    print(f"  Inserted {inserted} rows into match_lineups")
    if skipped_no_tm:
        print(f"  Skipped {skipped_no_tm} rows (no matching team_match by team+date)")
    if skipped_ambiguous:
        print(f"  Skipped {skipped_ambiguous} rows (ambiguous team_match — multiple on same date)")
    if skipped_duplicate:
        print(f"  Skipped {skipped_duplicate} duplicate rows")

    return inserted


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(parts: Optional[list[str]] = None, db_path: Optional[Path] = None) -> None:
    """
    Run the linkage pipeline.

    Args:
        parts: List of parts to run, e.g. ['A', 'B', 'C'].
               Defaults to all three parts.
        db_path: Optional path to the SQLite DB.
    """
    db = db_path or DB_PATH
    conn = _conn(db)
    cur = conn.cursor()

    run_all = not parts
    parts_set = {p.upper() for p in (parts or [])}

    if run_all or "A" in parts_set:
        print("\n=== Part A: Fix opponent_id in team_matches ===")
        fix_opponent_ids(cur)
        conn.commit()

    if run_all or "B" in parts_set:
        print("\n=== Part B: Link player_nat_stats to team_matches ===")
        link_nat_stats_to_matches(cur)
        conn.commit()

    if run_all or "C" in parts_set:
        print("\n=== Part C: Populate match_lineups from match_players ===")
        _ensure_team_match_id_column(cur)
        populate_match_lineups(cur)
        conn.commit()

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    import sys

    requested_parts = [a.upper() for a in sys.argv[1:] if a.upper() in ("A", "B", "C")]
    if requested_parts:
        print(f"Running parts: {', '.join(requested_parts)}")
    else:
        print("Running all parts (A, B, C) ...")
    run(parts=requested_parts or None)
