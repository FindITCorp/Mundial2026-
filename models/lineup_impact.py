"""
lineup_impact.py — Analyze how lineup composition correlates with match outcomes.

All functions use historical match data from:
  - match_lineups (populated by link_historical_data.py, Part C)
  - match_players  (per-match WC stats)
  - team_matches   (results)
  - player_ratings (computed ratings)
  - teams          (tactical metadata)

Key functions:
  lineup_win_rates()          — Per-player win% when in the starting XI
  h2h_lineup_analysis()       — Lineup patterns in W/D/L for a pair of teams
  player_vs_opponent_type()   — Player performance vs a given tactical style
  starting_xi_strength()      — Evaluate a proposed starting XI
"""

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_team_id(cur: sqlite3.Cursor, team_name: str) -> Optional[int]:
    """Return team id for team_name, trying exact name, slug, and partial match."""
    row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if row:
        return row["id"]
    slug = team_name.lower().replace(" ", "_").replace(".", "")
    row = cur.execute("SELECT id FROM teams WHERE slug=?", (slug,)).fetchone()
    if row:
        return row["id"]
    row = cur.execute(
        "SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",)
    ).fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# 1. lineup_win_rates
# ---------------------------------------------------------------------------

def lineup_win_rates(
    team_name: str,
    db_path: Optional[Path] = None,
) -> dict[str, dict]:
    """
    For a team, compute per-player win rates: when player X starts, what
    fraction of matches does the team win?

    Uses match_lineups (which stores starter=1 rows linked via team_match_id
    to team_matches) and match_players as a fallback when match_lineups is
    sparse.

    Returns:
        {
          player_name: {
              "win_pct": float,       # 0.0–1.0
              "draw_pct": float,
              "loss_pct": float,
              "matches": int,         # total matches started
              "wins": int,
              "goals_for": float,     # avg per match started
              "goals_against": float, # avg per match started
          }
        }
    """
    conn = _conn(db_path)
    cur = conn.cursor()

    team_id = _resolve_team_id(cur, team_name)
    if team_id is None:
        conn.close()
        return {}

    # Strategy: join match_players (starters) with team_matches via team_id + date
    # This is the most complete path since match_lineups may be partially populated.
    rows = cur.execute(
        """
        SELECT
            mp.player_name,
            mp.player_id,
            tm.result,
            tm.goals_for,
            tm.goals_against
        FROM match_players mp
        JOIN team_matches tm
            ON tm.team_id = mp.team_id
           AND tm.date    = mp.match_date
        WHERE mp.team_id = ?
          AND mp.started = 1
        """,
        (team_id,),
    ).fetchall()

    if not rows:
        conn.close()
        return {}

    # Aggregate per player
    stats: dict[str, dict] = {}
    for row in rows:
        name = row["player_name"] or f"player_{row['player_id']}"
        if name not in stats:
            stats[name] = {
                "matches": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goals_for_sum": 0,
                "goals_against_sum": 0,
            }
        s = stats[name]
        s["matches"] += 1
        result = row["result"]
        if result == "W":
            s["wins"] += 1
        elif result == "D":
            s["draws"] += 1
        else:
            s["losses"] += 1
        s["goals_for_sum"] += row["goals_for"] or 0
        s["goals_against_sum"] += row["goals_against"] or 0

    # Build final output
    result_dict: dict[str, dict] = {}
    for name, s in stats.items():
        n = s["matches"]
        if n == 0:
            continue
        result_dict[name] = {
            "win_pct": round(s["wins"] / n, 4),
            "draw_pct": round(s["draws"] / n, 4),
            "loss_pct": round(s["losses"] / n, 4),
            "matches": n,
            "wins": s["wins"],
            "goals_for": round(s["goals_for_sum"] / n, 2),
            "goals_against": round(s["goals_against_sum"] / n, 2),
        }

    # Sort by win_pct descending
    result_dict = dict(
        sorted(result_dict.items(), key=lambda x: x[1]["win_pct"], reverse=True)
    )

    conn.close()
    return result_dict


# ---------------------------------------------------------------------------
# 2. h2h_lineup_analysis
# ---------------------------------------------------------------------------

def h2h_lineup_analysis(
    team_a: str,
    team_b: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Analyze direct matches between two teams from historical data.

    For each match found:
      - Which players started for each team?
      - What was the result?
    Then aggregate: which players appear most in wins vs losses?

    Returns:
        {
          "team_a": team_a,
          "team_b": team_b,
          "total_h2h_matches": int,
          "summary": {
              team_a: {"wins": int, "draws": int, "losses": int},
              team_b: {"wins": int, "draws": int, "losses": int},
          },
          "matches": [
              {
                "date": str,
                "competition": str,
                "result_for_a": "W"|"D"|"L",
                "score": "X-Y",
                "lineup_a": [player_name, ...],  # starters
                "lineup_b": [player_name, ...],
              },
              ...
          ],
          "player_patterns": {
              team_a: {
                  "always_in_wins": [player_name, ...],
                  "never_in_losses": [player_name, ...],
                  "win_presence": {player_name: {"pct": float, "matches": int}},
              },
              team_b: { ... same structure ... },
          },
        }
    """
    conn = _conn(db_path)
    cur = conn.cursor()

    a_id = _resolve_team_id(cur, team_a)
    b_id = _resolve_team_id(cur, team_b)

    if a_id is None or b_id is None:
        conn.close()
        return {
            "team_a": team_a,
            "team_b": team_b,
            "error": f"Team not found: {team_a if a_id is None else team_b}",
        }

    # Find all H2H matches from team_matches where team_a played team_b
    # (either direction)
    tm_rows = cur.execute(
        """
        SELECT id, team_id, opponent_id, opponent_name, date, competition,
               goals_for, goals_against, result
        FROM team_matches
        WHERE (team_id=? AND opponent_id=?)
           OR (team_id=? AND opponent_id=?)
        ORDER BY date DESC
        """,
        (a_id, b_id, b_id, a_id),
    ).fetchall()

    if not tm_rows:
        conn.close()
        return {
            "team_a": team_a,
            "team_b": team_b,
            "total_h2h_matches": 0,
            "matches": [],
            "summary": {},
            "player_patterns": {},
            "note": "No direct H2H matches found in team_matches.",
        }

    # For each match, collect starters from match_players
    matches_out = []
    # Track per-player presence in each result category per team
    presence: dict[int, dict[str, dict[str, int]]] = {
        a_id: {"W": {}, "D": {}, "L": {}},
        b_id: {"W": {}, "D": {}, "L": {}},
    }
    result_counts: dict[int, dict[str, int]] = {
        a_id: {"W": 0, "D": 0, "L": 0},
        b_id: {"W": 0, "D": 0, "L": 0},
    }

    for tm in tm_rows:
        match_team_id = tm["team_id"]
        opponent_team_id = tm["opponent_id"]

        # Normalize to always express from team_a's perspective
        if match_team_id == a_id:
            result_for_a = tm["result"]
            score = f"{tm['goals_for']}-{tm['goals_against']}"
        else:
            # This row is from team_b's perspective; flip
            flip = {"W": "L", "L": "W", "D": "D"}
            result_for_a = flip.get(tm["result"], "D")
            score = f"{tm['goals_against']}-{tm['goals_for']}"

        # Result for b is inverse of a
        result_for_b = {"W": "L", "L": "W", "D": "D"}.get(result_for_a, "D")

        # Get starters for both teams on this match date
        starters_a = cur.execute(
            """
            SELECT DISTINCT player_name FROM match_players
            WHERE team_id=? AND match_date=? AND started=1
            """,
            (a_id, tm["date"]),
        ).fetchall()
        starters_b = cur.execute(
            """
            SELECT DISTINCT player_name FROM match_players
            WHERE team_id=? AND match_date=? AND started=1
            """,
            (b_id, tm["date"]),
        ).fetchall()

        lineup_a = [r["player_name"] for r in starters_a if r["player_name"]]
        lineup_b = [r["player_name"] for r in starters_b if r["player_name"]]

        matches_out.append({
            "date": tm["date"],
            "competition": tm["competition"],
            "result_for_a": result_for_a,
            "score": score,
            "lineup_a": lineup_a,
            "lineup_b": lineup_b,
        })

        # Update presence counters
        result_counts[a_id][result_for_a] += 1
        result_counts[b_id][result_for_b] += 1

        for pname in lineup_a:
            presence[a_id][result_for_a][pname] = presence[a_id][result_for_a].get(pname, 0) + 1
        for pname in lineup_b:
            presence[b_id][result_for_b][pname] = presence[b_id][result_for_b].get(pname, 0) + 1

    # Build summary
    summary = {
        team_a: result_counts[a_id],
        team_b: result_counts[b_id],
    }

    # Build player patterns per team
    def _build_patterns(tid: int, team_label: str) -> dict:
        wins = result_counts[tid]["W"]
        losses = result_counts[tid]["L"]
        win_presence = presence[tid]["W"]
        loss_presence = presence[tid]["L"]

        # Players who started in ALL wins (and wins > 0)
        always_in_wins = []
        if wins > 0:
            always_in_wins = [p for p, cnt in win_presence.items() if cnt == wins]

        # Players who NEVER started in a loss (appeared in at least 1 win)
        never_in_losses = []
        if losses > 0 and wins > 0:
            never_in_losses = [
                p for p in win_presence
                if loss_presence.get(p, 0) == 0 and win_presence[p] >= 1
            ]

        # Win presence percentage for all players who appeared in any match
        all_players_this_team: set[str] = set()
        for bucket in presence[tid].values():
            all_players_this_team.update(bucket.keys())

        total_matches = sum(result_counts[tid].values())

        win_presence_pct = {}
        for p in all_players_this_team:
            p_wins = win_presence.get(p, 0)
            p_total = sum(presence[tid][r].get(p, 0) for r in ["W", "D", "L"])
            win_presence_pct[p] = {
                "win_pct": round(p_wins / p_total, 4) if p_total > 0 else 0.0,
                "matches_started": p_total,
                "matches_in_wins": p_wins,
            }

        # Sort by win_pct desc
        win_presence_pct = dict(
            sorted(win_presence_pct.items(), key=lambda x: x[1]["win_pct"], reverse=True)
        )

        return {
            "always_in_wins": sorted(always_in_wins),
            "never_in_losses": sorted(never_in_losses),
            "win_presence": win_presence_pct,
        }

    player_patterns = {
        team_a: _build_patterns(a_id, team_a),
        team_b: _build_patterns(b_id, team_b),
    }

    conn.close()
    return {
        "team_a": team_a,
        "team_b": team_b,
        "total_h2h_matches": len(matches_out),
        "summary": summary,
        "matches": matches_out,
        "player_patterns": player_patterns,
    }


# ---------------------------------------------------------------------------
# 3. player_vs_opponent_type
# ---------------------------------------------------------------------------

def player_vs_opponent_type(
    player_name: str,
    opponent_style: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Analyze how a player performs against teams of a certain tactical_style.

    Joins match_players (player's stats per match) with teams (opponent
    tactical_style) via team_matches (to identify the opponent team).

    Args:
        player_name:    Exact or partial player name.
        opponent_style: Tactical style string to filter on, e.g. "pressing",
                        "counter", "possession".  Case-insensitive substring
                        match against teams.tactical_style.

    Returns:
        {
          "player_name": str,
          "opponent_style": str,
          "matches_found": int,
          "avg_rating": float,
          "avg_goals": float,
          "avg_assists": float,
          "avg_minutes": float,
          "matches": [
              {
                "date": str,
                "opponent": str,
                "opponent_style": str,
                "result": str,
                "goals": int,
                "assists": int,
                "rating": float,  # computed rating
                "minutes": int,
              }
          ]
        }
    """
    conn = _conn(db_path)
    cur = conn.cursor()

    # Find player records in match_players
    mp_rows = cur.execute(
        """
        SELECT mp.*, tm.opponent_id, tm.opponent_name, tm.result, tm.goals_for, tm.goals_against
        FROM match_players mp
        JOIN team_matches tm
            ON tm.team_id = mp.team_id
           AND tm.date    = mp.match_date
        WHERE (LOWER(mp.player_name) LIKE LOWER(?) OR LOWER(mp.player_name) = LOWER(?))
        ORDER BY mp.match_date DESC
        """,
        (f"%{player_name}%", player_name),
    ).fetchall()

    if not mp_rows:
        conn.close()
        return {
            "player_name": player_name,
            "opponent_style": opponent_style,
            "matches_found": 0,
            "avg_rating": 0.0,
            "note": "No match_players records found for this player name.",
        }

    # Build opponent style lookup: team_id -> tactical_style
    opp_style_map: dict[int, Optional[str]] = {}
    all_team_rows = cur.execute("SELECT id, tactical_style FROM teams").fetchall()
    for tr in all_team_rows:
        opp_style_map[tr["id"]] = tr["tactical_style"]

    style_lower = opponent_style.strip().lower()

    # Import here to avoid circular dependency at module load time
    from models.player_rating import compute_player_rating, ClubMatchStats

    filtered_matches = []
    for row in mp_rows:
        opp_id = row["opponent_id"]
        opp_style_raw = opp_style_map.get(opp_id) if opp_id else None

        # Check style match
        if opp_style_raw and style_lower in opp_style_raw.lower():
            # Compute rating for this match
            shots_total = max(1, row["shots_total"] or 0)
            stats = ClubMatchStats(
                goals=row["goals"] or 0,
                assists=row["assists"] or 0,
                shots_on_target=row["shots_on"] or 0,
                shots_total=shots_total,
                pass_accuracy=82.0,
                dribbles_completed=0,
                tackles=row["tackles"] or 0,
                interceptions=row["interceptions"] or 0,
                yellow_cards=row["yellow_cards"] or 0,
                red_cards=row["red_cards"] or 0,
                minutes=row["minutes_played"] or 0,
            )
            rc = compute_player_rating(stats, row["position"] or "MID", "nat")

            filtered_matches.append({
                "date": row["match_date"],
                "opponent": row["opponent_name"],
                "opponent_style": opp_style_raw,
                "result": row["result"],
                "goals": row["goals"] or 0,
                "assists": row["assists"] or 0,
                "rating": rc.final_rating,
                "minutes": row["minutes_played"] or 0,
            })

    if not filtered_matches:
        conn.close()
        return {
            "player_name": player_name,
            "opponent_style": opponent_style,
            "matches_found": 0,
            "avg_rating": 0.0,
            "note": f"No matches found against teams with style containing '{opponent_style}'.",
        }

    n = len(filtered_matches)
    avg_rating = round(sum(m["rating"] for m in filtered_matches) / n, 3)
    avg_goals = round(sum(m["goals"] for m in filtered_matches) / n, 3)
    avg_assists = round(sum(m["assists"] for m in filtered_matches) / n, 3)
    avg_minutes = round(sum(m["minutes"] for m in filtered_matches) / n, 1)

    conn.close()
    return {
        "player_name": player_name,
        "opponent_style": opponent_style,
        "matches_found": n,
        "avg_rating": avg_rating,
        "avg_goals": avg_goals,
        "avg_assists": avg_assists,
        "avg_minutes": avg_minutes,
        "matches": filtered_matches,
    }


# ---------------------------------------------------------------------------
# 4. starting_xi_strength
# ---------------------------------------------------------------------------

def starting_xi_strength(
    team_name: str,
    players: list[str],
    db_path: Optional[Path] = None,
) -> dict:
    """
    Evaluate a proposed starting XI.

    For each player in `players`:
      - Look up their most recent 'nat' rating in player_ratings.
        Fallback: compute from match_players data on the fly.
      - Compute the average rating of the proposed lineup.
      - Look up the historical win rate when that player started (from match_players).
      - Identify "key players": those whose presence correlates with above-average
        win rates.

    Args:
        team_name: The team this lineup is for.
        players:   List of player names (can be partial matches).

    Returns:
        {
          "team": str,
          "lineup": [
              {
                "name": str,
                "resolved_name": str,   # canonical name from DB
                "position": str,
                "rating": float,
                "win_pct_when_starting": float,
                "matches_with_data": int,
              }
          ],
          "avg_rating": float,
          "historical_win_rate": float,   # average win_pct across proposed lineup
          "key_players": [str],           # players with win_pct above team avg
          "missing_players": [str],       # names that could not be resolved
        }
    """
    conn = _conn(db_path)
    cur = conn.cursor()

    team_id = _resolve_team_id(cur, team_name)
    if team_id is None:
        conn.close()
        return {"team": team_name, "error": "Team not found"}

    # Precompute win rates for all players in this team (from match_players)
    win_rate_cache: dict[str, dict] = {}
    wp_rows = cur.execute(
        """
        SELECT mp.player_name, tm.result, COUNT(*) as cnt
        FROM match_players mp
        JOIN team_matches tm
            ON tm.team_id = mp.team_id
           AND tm.date    = mp.match_date
        WHERE mp.team_id=? AND mp.started=1
        GROUP BY mp.player_name, tm.result
        """,
        (team_id,),
    ).fetchall()

    for row in wp_rows:
        pname = row["player_name"]
        if pname not in win_rate_cache:
            win_rate_cache[pname] = {"W": 0, "D": 0, "L": 0}
        win_rate_cache[pname][row["result"]] = row["cnt"]

    def _win_pct(pname: str) -> tuple[float, int]:
        d = win_rate_cache.get(pname, {})
        total = d.get("W", 0) + d.get("D", 0) + d.get("L", 0)
        if total == 0:
            return 0.0, 0
        return round(d.get("W", 0) / total, 4), total

    # Rating lookup: prefer player_ratings (nat, match_id=NULL), fallback to
    # most recent nat rating with a match_id, then estimate from profile
    def _get_rating(player_id: int, position: str) -> float:
        # 1. Aggregate nat rating
        r = cur.execute(
            """
            SELECT rating FROM player_ratings
            WHERE player_id=? AND context='nat' AND match_id IS NULL
            ORDER BY computed_at DESC LIMIT 1
            """,
            (player_id,),
        ).fetchone()
        if r:
            return r["rating"]
        # 2. Most recent per-match nat rating
        r = cur.execute(
            """
            SELECT rating FROM player_ratings
            WHERE player_id=? AND context='nat'
            ORDER BY computed_at DESC LIMIT 1
            """,
            (player_id,),
        ).fetchone()
        if r:
            return r["rating"]
        # 3. Club rating
        r = cur.execute(
            """
            SELECT rating FROM player_ratings
            WHERE player_id=? AND context='club'
            ORDER BY computed_at DESC LIMIT 1
            """,
            (player_id,),
        ).fetchone()
        if r:
            return r["rating"]
        return 6.0  # neutral default

    # Resolve each player name to a DB record
    lineup_out = []
    missing_players = []

    for pname in players:
        # Try exact match in players table for this team first
        p_row = cur.execute(
            "SELECT * FROM players WHERE team_id=? AND LOWER(name)=LOWER(?)",
            (team_id, pname),
        ).fetchone()

        if not p_row:
            # Try partial match within team
            p_row = cur.execute(
                "SELECT * FROM players WHERE team_id=? AND LOWER(name) LIKE LOWER(?)",
                (team_id, f"%{pname}%"),
            ).fetchone()

        if not p_row:
            # Try any team (player may have been transferred / squad updated)
            p_row = cur.execute(
                "SELECT * FROM players WHERE LOWER(name) LIKE LOWER(?)",
                (f"%{pname}%",),
            ).fetchone()

        if not p_row:
            # Fall back: look in match_players for this team
            mp_row = cur.execute(
                """
                SELECT DISTINCT player_name, player_id, position
                FROM match_players
                WHERE team_id=? AND LOWER(player_name) LIKE LOWER(?)
                LIMIT 1
                """,
                (team_id, f"%{pname}%"),
            ).fetchone()

            if mp_row:
                resolved_name = mp_row["player_name"]
                position = mp_row["position"] or "MID"
                rating = 6.0  # no players table entry
                wp, n_matches = _win_pct(resolved_name)
                lineup_out.append({
                    "name": pname,
                    "resolved_name": resolved_name,
                    "position": position,
                    "rating": rating,
                    "win_pct_when_starting": wp,
                    "matches_with_data": n_matches,
                })
            else:
                missing_players.append(pname)
            continue

        resolved_name = p_row["name"]
        position = p_row["position"] or "MID"
        rating = _get_rating(p_row["id"], position)
        wp, n_matches = _win_pct(resolved_name)

        lineup_out.append({
            "name": pname,
            "resolved_name": resolved_name,
            "position": position,
            "rating": rating,
            "win_pct_when_starting": wp,
            "matches_with_data": n_matches,
        })

    conn.close()

    if not lineup_out:
        return {
            "team": team_name,
            "lineup": [],
            "avg_rating": 0.0,
            "historical_win_rate": 0.0,
            "key_players": [],
            "missing_players": missing_players,
        }

    avg_rating = round(
        sum(p["rating"] for p in lineup_out) / len(lineup_out), 3
    )

    # Historical win rate: average of per-player win_pct (only for players
    # where we have historical data)
    players_with_data = [p for p in lineup_out if p["matches_with_data"] > 0]
    if players_with_data:
        historical_win_rate = round(
            sum(p["win_pct_when_starting"] for p in players_with_data)
            / len(players_with_data),
            4,
        )
    else:
        historical_win_rate = 0.0

    # Key players: those with win_pct above the lineup average and at least
    # 2 historical matches
    key_players = [
        p["resolved_name"]
        for p in lineup_out
        if p["matches_with_data"] >= 2
        and p["win_pct_when_starting"] > historical_win_rate
    ]

    return {
        "team": team_name,
        "lineup": lineup_out,
        "avg_rating": avg_rating,
        "historical_win_rate": historical_win_rate,
        "key_players": sorted(key_players),
        "missing_players": missing_players,
    }


# ---------------------------------------------------------------------------
# Direct execution helper
# ---------------------------------------------------------------------------

def run(db_path: Optional[Path] = None) -> None:
    """
    Demo run: show lineup win rates and a sample starting XI strength
    for Panama (the project's home team).
    """
    print("\n=== lineup_win_rates: Panama ===")
    rates = lineup_win_rates("Panama", db_path=db_path)
    if rates:
        for pname, data in list(rates.items())[:10]:
            print(
                f"  {pname:<30} win%={data['win_pct']:.1%}  "
                f"matches={data['matches']}  "
                f"gf={data['goals_for']:.1f}  ga={data['goals_against']:.1f}"
            )
    else:
        print("  No data found.")

    print("\n=== h2h_lineup_analysis: Argentina vs France ===")
    h2h = h2h_lineup_analysis("Argentina", "France", db_path=db_path)
    print(f"  H2H matches found: {h2h.get('total_h2h_matches', 0)}")
    if h2h.get("summary"):
        for team, s in h2h["summary"].items():
            print(f"  {team}: W={s.get('W',0)} D={s.get('D',0)} L={s.get('L',0)}")

    print("\n=== player_vs_opponent_type: Messi vs possession ===")
    pvs = player_vs_opponent_type("Messi", "possession", db_path=db_path)
    print(f"  Matches: {pvs.get('matches_found', 0)}")
    print(f"  Avg rating: {pvs.get('avg_rating', 0):.2f}  Avg goals: {pvs.get('avg_goals', 0):.2f}")


if __name__ == "__main__":
    import sys
    db_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run(db_path=db_arg)
