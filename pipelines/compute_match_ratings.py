"""
compute_match_ratings.py — Compute per-match player ratings from match_players data
                           and aggregate into a WC form rating per player.

Pipeline steps:
  1. Read all records from match_players (WC2018 + WC2022 data)
  2. For each player-match record, compute a match rating via compute_player_rating()
  3. Store each per-match rating in player_ratings (context='nat', match_id=fixture_api_id)
  4. Per player, compute a WC form rating: exponential-decay weighted average of all
     their match ratings, with WC2022 matches having a season weight of 1.0 and
     WC2018 matches having a season weight of 0.6 (recency of edition).
  5. Upsert the WC form rating as the authoritative 'nat' rating (match_id=NULL)
     in player_ratings — replacing any prior profile-based nat estimate.

Usage:
    python -m pipelines.compute_match_ratings
    python -m pipelines.compute_match_ratings Brazil Argentina
"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Season weight: how much each WC edition contributes to the form aggregate.
# Most recent WC (2022) is full weight; older WC (2018) is discounted.
SEASON_WEIGHT = {
    2022: 1.0,
    2018: 0.6,
}
DEFAULT_SEASON_WEIGHT = 0.5  # fallback for any unexpected season value

# Exponential decay applied *within* a season, match-by-match (most recent first)
WITHIN_SEASON_DECAY = 0.92


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _build_stats(row: sqlite3.Row):
    """
    Convert a match_players row into a ClubMatchStats object.
    Imports are deferred so the module is usable even if models/ not yet on path.
    """
    from models.player_rating import ClubMatchStats

    passes = row["passes_total"] or 0
    shots_total = max(1, row["shots_total"] or 0)

    # pass_accuracy is not stored directly; estimate based on the fact that
    # typical WC pass completion sits around 78-88%.  We use 82% as a neutral
    # anchor — the per-position benchmarks inside compute_player_rating() will
    # then produce a small bonus/penalty relative to that anchor.
    estimated_pass_acc = 82.0 if passes == 0 else min(95.0, 82.0)

    return ClubMatchStats(
        goals=row["goals"] or 0,
        assists=row["assists"] or 0,
        shots_on_target=row["shots_on"] or 0,
        shots_total=shots_total,
        pass_accuracy=estimated_pass_acc,
        dribbles_completed=0,        # not stored in match_players
        tackles=row["tackles"] or 0,
        interceptions=row["interceptions"] or 0,
        yellow_cards=row["yellow_cards"] or 0,
        red_cards=row["red_cards"] or 0,
        minutes=row["minutes_played"] or 0,
        saves=0,
        goals_conceded=0,
    )


def compute_and_store_match_ratings(
    cur: sqlite3.Cursor,
    team_filter: Optional[list[int]] = None,
) -> dict[int, list[tuple[float, int]]]:
    """
    For every record in match_players (optionally filtered by team_id),
    compute a per-match rating and upsert it into player_ratings.

    Returns a dict: player_id -> [(match_rating, season), ...] sorted
    by (season DESC, match_date DESC) — ready for form aggregation.
    """
    from models.player_rating import compute_player_rating

    if team_filter:
        placeholders = ",".join("?" * len(team_filter))
        rows = cur.execute(
            f"""
            SELECT * FROM match_players
            WHERE team_id IN ({placeholders})
              AND player_id IS NOT NULL
            ORDER BY player_id, season DESC, match_date DESC
            """,
            team_filter,
        ).fetchall()
    else:
        rows = cur.execute(
            """
            SELECT * FROM match_players
            WHERE player_id IS NOT NULL
            ORDER BY player_id, season DESC, match_date DESC
            """
        ).fetchall()

    print(f"  Processing {len(rows)} match_players records ...")

    # player_id -> list of (match_rating, season) in the order returned
    player_match_ratings: dict[int, list[tuple[float, int]]] = {}

    inserted = 0
    skipped = 0

    for row in rows:
        player_id = row["player_id"]
        position = row["position"] or "MID"
        season = row["season"] or 0
        fixture_api_id = row["fixture_api_id"]

        stats = _build_stats(row)

        try:
            rc = compute_player_rating(stats, position, "nat")
        except Exception as exc:
            print(f"    [WARN] compute_player_rating failed for player_id={player_id}: {exc}")
            skipped += 1
            continue

        match_rating = rc.final_rating
        components_json = json.dumps(asdict(rc))

        # Upsert: if a rating for this (player_id, fixture_api_id, 'nat') exists,
        # replace it.  We use fixture_api_id stored in match_id column as a reference.
        cur.execute(
            """
            INSERT OR REPLACE INTO player_ratings
                (player_id, match_id, context, rating, components)
            VALUES (?, ?, 'nat', ?, ?)
            """,
            (player_id, fixture_api_id, match_rating, components_json),
        )
        inserted += 1

        if player_id not in player_match_ratings:
            player_match_ratings[player_id] = []
        player_match_ratings[player_id].append((match_rating, season))

    print(f"  Per-match ratings: {inserted} inserted/replaced, {skipped} skipped")
    return player_match_ratings


def compute_and_store_form_ratings(
    cur: sqlite3.Cursor,
    player_match_ratings: dict[int, list[tuple[float, int]]],
) -> int:
    """
    For each player, compute a WC form rating from their per-match ratings and
    upsert it as the 'nat' rating with match_id=NULL in player_ratings.

    The weighting scheme:
      - Matches are already sorted most-recent first (within a season).
      - Each match i (0-indexed, 0=most recent within its season) gets:
          weight = season_weight(season) * WITHIN_SEASON_DECAY^i
      - WC2022 matches are processed first (highest recency), then WC2018.

    Returns count of players updated.
    """
    from models.player_rating import compute_form_rating

    updated = 0

    for player_id, match_list in player_match_ratings.items():
        if not match_list:
            continue

        # Separate by season and sort: 2022 first, then 2018
        by_season: dict[int, list[float]] = {}
        for rating, season in match_list:
            by_season.setdefault(season, []).append(rating)

        # Build a combined weighted list: flatten in season order (newest first)
        # Each entry is (weight, rating)
        weighted_pairs: list[tuple[float, float]] = []

        for season in sorted(by_season.keys(), reverse=True):
            season_w = SEASON_WEIGHT.get(season, DEFAULT_SEASON_WEIGHT)
            ratings_in_season = by_season[season]
            for i, r in enumerate(ratings_in_season):  # already desc by match_date
                w = season_w * (WITHIN_SEASON_DECAY ** i)
                weighted_pairs.append((w, r))

        if not weighted_pairs:
            continue

        total_weight = sum(w for w, _ in weighted_pairs)
        form_rating = sum(w * r for w, r in weighted_pairs) / total_weight
        form_rating = round(max(1.0, min(10.0, form_rating)), 3)

        # Upsert the aggregate nat form rating (match_id=NULL)
        # Delete any existing null-match_id nat rating first to avoid duplicates
        cur.execute(
            """
            DELETE FROM player_ratings
            WHERE player_id=? AND context='nat' AND match_id IS NULL
            """,
            (player_id,),
        )
        cur.execute(
            """
            INSERT INTO player_ratings (player_id, match_id, context, rating, components)
            VALUES (?, NULL, 'nat', ?, ?)
            """,
            (
                player_id,
                form_rating,
                json.dumps({
                    "source": "wc_form",
                    "matches_2022": len(by_season.get(2022, [])),
                    "matches_2018": len(by_season.get(2018, [])),
                    "raw_avg": round(
                        sum(r for _, r in weighted_pairs) / len(weighted_pairs), 3
                    ),
                }),
            ),
        )
        updated += 1

    print(f"  Form ratings upserted for {updated} players")
    return updated


def run(teams: Optional[list[str]] = None, db_path: Optional[Path] = None) -> None:
    """
    Main entry point.

    Args:
        teams: Optional list of team names to restrict processing to.
               If None, processes all teams.
        db_path: Optional path to the SQLite database.
    """
    db = db_path or DB_PATH
    conn = _conn(db)
    cur = conn.cursor()

    team_ids: Optional[list[int]] = None
    if teams:
        placeholders = ",".join("?" * len(teams))
        rows = cur.execute(
            f"SELECT id, name FROM teams WHERE name IN ({placeholders})", teams
        ).fetchall()
        found = {r["name"] for r in rows}
        missing = set(teams) - found
        if missing:
            print(f"  [WARN] Teams not found in DB: {', '.join(sorted(missing))}")
        team_ids = [r["id"] for r in rows]
        if not team_ids:
            print("  No matching teams found — nothing to do.")
            conn.close()
            return
        print(f"  Filtering to teams: {', '.join(found)}")

    print("\n=== Step 1: Computing per-match ratings ===")
    player_match_ratings = compute_and_store_match_ratings(cur, team_filter=team_ids)

    print(f"\n=== Step 2: Computing WC form ratings for {len(player_match_ratings)} players ===")
    compute_and_store_form_ratings(cur, player_match_ratings)

    conn.commit()
    conn.close()
    print("\nDone. All ratings committed to DB.")


if __name__ == "__main__":
    import sys

    team_args = sys.argv[1:] if len(sys.argv) > 1 else None
    if team_args:
        print(f"Running for teams: {team_args}")
    else:
        print("Running for ALL teams in match_players ...")
    run(teams=team_args)
