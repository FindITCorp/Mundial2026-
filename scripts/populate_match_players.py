#!/usr/bin/env python3
"""
Populate match_players table with StatsBomb WC 2022 open data.
Competition ID: 43, Season ID: 3
"""

import json
import sqlite3
import time
import re
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DB = Path("/home/user/mundial2026/data/mundial2026.db")
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# --- Fetch helpers -----------------------------------------------------------

def fetch_json(url, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (URLError, HTTPError) as e:
            print(f"  [!] Attempt {attempt+1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
        except Exception as e:
            print(f"  [!] Unexpected error fetching {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None

# --- Position mapping --------------------------------------------------------

POSITION_MAP = {
    "Goalkeeper": "GK",
    "Center Back": "DEF",
    "Left Back": "DEF",
    "Right Back": "DEF",
    "Left Wing Back": "DEF",
    "Right Wing Back": "DEF",
    "Central Midfield": "MID",
    "Defensive Midfield": "MID",
    "Attacking Midfield": "MID",
    "Left Midfield": "MID",
    "Right Midfield": "MID",
    "Center Forward": "FWD",
    "Left Wing": "FWD",
    "Right Wing": "FWD",
    "Secondary Striker": "FWD",
    # Extra ones that might appear
    "Left Center Back": "DEF",
    "Right Center Back": "DEF",
    "Left Center Forward": "FWD",
    "Right Center Forward": "FWD",
    "Left Defensive Midfield": "MID",
    "Right Defensive Midfield": "MID",
    "Left Attacking Midfield": "MID",
    "Right Attacking Midfield": "MID",
    "Left Center Midfield": "MID",
    "Right Center Midfield": "MID",
    "Striker": "FWD",
    "Forward": "FWD",
    "Midfielder": "MID",
    "Defender": "DEF",
}

def map_position(pos_name):
    if not pos_name:
        return "MID"
    return POSITION_MAP.get(pos_name, "MID")

# --- Name normalization helpers ----------------------------------------------

def normalize(name):
    """Lowercase, strip accents roughly, strip extra spaces."""
    if not name:
        return ""
    n = name.lower().strip()
    # Basic accent normalization
    replacements = {
        "á": "a", "à": "a", "ä": "a", "â": "a", "ã": "a",
        "é": "e", "è": "e", "ë": "e", "ê": "e",
        "í": "i", "ì": "i", "ï": "i", "î": "i",
        "ó": "o", "ò": "o", "ö": "o", "ô": "o", "õ": "o",
        "ú": "u", "ù": "u", "ü": "u", "û": "u",
        "ý": "y", "ÿ": "y",
        "ñ": "n", "ç": "c",
        "ß": "ss",
    }
    for acc, plain in replacements.items():
        n = n.replace(acc, plain)
    return n

def name_tokens(name):
    return set(normalize(name).split())

def find_team_id(team_name, team_map, team_alias_map):
    n = normalize(team_name)
    if n in team_map:
        return team_map[n]
    if n in team_alias_map:
        return team_alias_map[n]
    # Partial match
    for k, v in team_map.items():
        if n in k or k in n:
            return v
    return None

def find_player_id(sb_name, team_id, player_map_by_team, player_map_global):
    """Try to match StatsBomb player name to our players table."""
    n = normalize(sb_name)

    # Exact match global
    if n in player_map_global:
        return player_map_global[n]

    # Exact match within team
    if team_id and team_id in player_map_by_team:
        tmap = player_map_by_team[team_id]
        if n in tmap:
            return tmap[n]
        # Token match within team
        tokens = name_tokens(sb_name)
        for k, pid in tmap.items():
            k_tokens = set(k.split())
            # Match if last token matches or all tokens overlap significantly
            if tokens and list(tokens)[-1] in k_tokens:
                return pid
            if len(tokens & k_tokens) >= max(1, min(len(tokens), len(k_tokens)) - 1):
                return pid

    # Last-name match globally (less reliable)
    parts = normalize(sb_name).split()
    if parts:
        last = parts[-1]
        candidates = []
        for k, pid in player_map_global.items():
            k_parts = k.split()
            if k_parts and k_parts[-1] == last:
                candidates.append((k, pid))
        if len(candidates) == 1:
            return candidates[0][1]
        # If team_id matches, prefer team candidate
        if team_id and len(candidates) > 1:
            for k, pid in candidates:
                if team_id in player_map_by_team and k in player_map_by_team[team_id]:
                    return pid

    return None

# --- Main processing ---------------------------------------------------------

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Build team lookup maps
    print("Loading teams...")
    team_map = {}  # normalized name -> id
    for r in conn.execute("SELECT id, name FROM teams").fetchall():
        team_map[normalize(r["name"])] = r["id"]

    # Extra aliases for StatsBomb vs our DB name differences
    # Map: statsbomb_name_normalized -> our_db_name_normalized
    TEAM_ALIASES = {
        "united states": "usa",
        "south korea": "south korea",  # our DB has "South Korea"
        "korea republic": "south korea",
        "ir iran": "iran",
        "côte d'ivoire": "ivory coast",
        "cote d'ivoire": "ivory coast",
        "democratic republic of congo": "dr congo",
    }
    team_alias_map = {}
    for alias, canonical in TEAM_ALIASES.items():
        na = normalize(alias)
        nc = normalize(canonical)
        if nc in team_map:
            team_alias_map[na] = team_map[nc]
        elif na in team_map:
            team_alias_map[normalize(alias)] = team_map[na]

    # Build player lookup maps
    print("Loading players...")
    player_map_global = {}   # normalized name -> player_id
    player_map_by_team = {}  # team_id -> {normalized name -> player_id}
    for r in conn.execute("SELECT id, name, team_id FROM players").fetchall():
        n = normalize(r["name"])
        player_map_global[n] = r["id"]
        tid = r["team_id"]
        if tid not in player_map_by_team:
            player_map_by_team[tid] = {}
        player_map_by_team[tid][n] = r["id"]

    print(f"  Teams: {len(team_map)}, Players: {len(player_map_global)}")

    # Fetch match list
    # WC 2022 (Qatar): competition_id=43, season_id=106
    print("\nFetching WC 2022 match list...")
    matches_url = f"{BASE}/matches/43/106.json"
    matches = fetch_json(matches_url)
    if not matches:
        print("FATAL: Could not fetch match list")
        sys.exit(1)
    print(f"  Found {len(matches)} matches")

    total_inserted = 0
    total_skipped = 0
    total_updated = 0
    unmatched_teams = set()
    unmatched_players = []

    for match_idx, match in enumerate(matches):
        match_id = match["match_id"]
        match_date = match.get("match_date", "")
        home_team_name = match.get("home_team", {}).get("home_team_name", "")
        away_team_name = match.get("away_team", {}).get("away_team_name", "")
        fixture_api_id = -match_id  # negative to avoid collision

        print(f"\n[{match_idx+1}/{len(matches)}] Match {match_id}: {home_team_name} vs {away_team_name} ({match_date})")

        # Find team IDs
        home_team_id = find_team_id(home_team_name, team_map, team_alias_map)
        away_team_id = find_team_id(away_team_name, team_map, team_alias_map)

        if not home_team_id:
            unmatched_teams.add(home_team_name)
            print(f"  [!] Could not match team: {home_team_name}")
        if not away_team_id:
            unmatched_teams.add(away_team_name)
            print(f"  [!] Could not match team: {away_team_name}")

        # Map sb_team_id -> our team_id
        sb_home_id = match.get("home_team", {}).get("home_team_id")
        sb_away_id = match.get("away_team", {}).get("away_team_id")
        sb_team_to_ours = {}
        if sb_home_id:
            sb_team_to_ours[sb_home_id] = (home_team_id, home_team_name)
        if sb_away_id:
            sb_team_to_ours[sb_away_id] = (away_team_id, away_team_name)

        # Fetch lineups
        lineups_url = f"{BASE}/lineups/{match_id}.json"
        lineups_data = fetch_json(lineups_url)
        if not lineups_data:
            print(f"  [!] No lineups for match {match_id}, skipping")
            continue

        # Parse lineups: build player info dict
        # player_sb_id -> {name, position, jersey, team_id(ours), team_sb_id, started}
        players_info = {}  # sb_player_id -> info dict
        sb_team_name_map = {}  # sb_team_id -> sb_team_name

        for lineup in lineups_data:
            sb_tid = lineup.get("team_id")
            sb_tname = lineup.get("team_name", "")
            sb_team_name_map[sb_tid] = sb_tname
            our_tid, _ = sb_team_to_ours.get(sb_tid, (None, sb_tname))

            if not our_tid:
                # Try to find by name
                our_tid = find_team_id(sb_tname, team_map, team_alias_map)
                sb_team_to_ours[sb_tid] = (our_tid, sb_tname)

            for p in lineup.get("lineup", []):
                sb_pid = p.get("player_id")
                sb_pname = p.get("player_name", "")
                jersey = p.get("jersey_number")

                # Get position from positions list
                positions = p.get("positions", [])
                pos_name = None
                started = 0
                for pos_entry in positions:
                    if pos_entry.get("start_reason") == "Starting XI":
                        pos_name = pos_entry.get("position")
                        started = 1
                        break
                if not pos_name and positions:
                    pos_name = positions[0].get("position")
                    if positions[0].get("start_reason") in ("Substitution", "Tactical Shift"):
                        started = 0

                mapped_pos = map_position(pos_name)
                players_info[sb_pid] = {
                    "name": sb_pname,
                    "position": mapped_pos,
                    "jersey": jersey,
                    "team_id": our_tid,
                    "team_sb_id": sb_tid,
                    "team_name": sb_tname,
                    "started": started,
                    "minutes_played": 0,
                    "goals": 0,
                    "assists": 0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                    "shots_total": 0,
                    "shots_on": 0,
                    "passes_total": 0,
                    "key_passes": 0,
                    "tackles": 0,
                    "interceptions": 0,
                }

        # Fetch events
        events_url = f"{BASE}/events/{match_id}.json"
        events_data = fetch_json(events_url)
        if not events_data:
            print(f"  [!] No events for match {match_id}")
            events_data = []

        # Determine if match went to extra time
        max_minute = 0
        for ev in events_data:
            m = ev.get("minute", 0)
            if m and m > max_minute:
                max_minute = m
        has_extra_time = max_minute > 95
        full_time = 120 if has_extra_time else 90

        # Track substitutions: sb_player_id -> minute (when they left or entered)
        sub_out = {}   # sb_player_id -> minute they were subbed out
        sub_in = {}    # sb_player_id -> minute they came on

        # Build pass lookup for assist detection: pass_id -> player_id
        pass_to_player = {}  # event_id -> sb_player_id

        # First pass: build pass map and substitution info
        for ev in events_data:
            etype = ev.get("type", {}).get("name", "")
            sb_pid = ev.get("player", {}).get("id")
            ev_id = ev.get("id")
            minute = ev.get("minute", 0)

            if etype == "Pass" and sb_pid and ev_id:
                pass_to_player[ev_id] = sb_pid

            if etype == "Substitution" and sb_pid:
                sub_out[sb_pid] = minute
                # The replacement player
                replacement = ev.get("substitution", {}).get("replacement", {})
                rep_id = replacement.get("id")
                if rep_id:
                    sub_in[rep_id] = minute

        # Calculate minutes played for starters
        for sb_pid, info in players_info.items():
            if info["started"] == 1:
                if sb_pid in sub_out:
                    info["minutes_played"] = sub_out[sb_pid]
                else:
                    info["minutes_played"] = full_time
            else:
                if sb_pid in sub_in:
                    info["minutes_played"] = max(0, full_time - sub_in[sb_pid])
                # else: they didn't play (listed but never subbed in)

        # Second pass: count stats from events
        for ev in events_data:
            etype = ev.get("type", {}).get("name", "")
            sb_pid = ev.get("player", {}).get("id")
            if not sb_pid or sb_pid not in players_info:
                continue

            info = players_info[sb_pid]

            if etype == "Shot":
                info["shots_total"] += 1
                shot = ev.get("shot", {})
                outcome = shot.get("outcome", {}).get("name", "")
                if outcome == "Goal":
                    # Check it's not an own goal
                    # Own goals are usually marked differently — check for own_goal flag
                    if not shot.get("type", {}).get("name", "") == "Own Goal":
                        info["goals"] += 1
                if shot.get("on_target"):
                    info["shots_on"] += 1
                elif outcome in ("Goal", "Saved", "Saved to Post"):
                    info["shots_on"] += 1

            elif etype == "Own Goal For":
                # Don't count as goal for player
                pass

            elif etype == "Pass":
                info["passes_total"] += 1
                pass_data = ev.get("pass", {})
                if pass_data.get("goal_assist"):
                    info["assists"] += 1
                if pass_data.get("shot_assist"):
                    info["key_passes"] += 1

            elif etype == "Yellow Card":
                info["yellow_cards"] += 1

            elif etype in ("Red Card", "Second Yellow"):
                info["red_cards"] += 1

            elif etype == "Tackle":
                info["tackles"] += 1

            elif etype == "Interception":
                info["interceptions"] += 1

        # Insert into match_players
        inserted_this_match = 0
        for sb_pid, info in players_info.items():
            # Only insert players who actually played (starters or subbed in)
            if info["minutes_played"] == 0 and info["started"] == 0:
                continue

            # Find our player_id
            our_pid = find_player_id(info["name"], info["team_id"], player_map_by_team, player_map_global)

            if not our_pid:
                unmatched_players.append((info["name"], info["team_name"]))

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO match_players
                    (fixture_api_id, team_id, player_id, player_api_id, player_name,
                     position, started, minutes_played, goals, assists,
                     yellow_cards, red_cards, rating, shots_total, shots_on,
                     passes_total, key_passes, tackles, interceptions,
                     match_date, competition, season)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fixture_api_id,
                    info["team_id"],
                    our_pid,
                    sb_pid,
                    info["name"],
                    info["position"],
                    info["started"],
                    info["minutes_played"],
                    info["goals"],
                    info["assists"],
                    info["yellow_cards"],
                    info["red_cards"],
                    0.0,  # rating — not available from StatsBomb open data
                    info["shots_total"],
                    info["shots_on"],
                    info["passes_total"],
                    info["key_passes"],
                    info["tackles"],
                    info["interceptions"],
                    match_date,
                    "WC",
                    2022,
                ))
                inserted_this_match += 1
            except sqlite3.IntegrityError as e:
                total_skipped += 1

        conn.commit()
        print(f"  -> Inserted {inserted_this_match} player rows")
        total_inserted += inserted_this_match

        # Small delay to be polite to GitHub raw servers
        time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"DONE. Total rows inserted: {total_inserted}")
    print(f"Skipped (duplicates): {total_skipped}")

    if unmatched_teams:
        print(f"\nUnmatched teams ({len(unmatched_teams)}):")
        for t in sorted(unmatched_teams):
            print(f"  - {t}")

    # Deduplicate unmatched players report
    unique_unmatched = list(set(unmatched_players))
    print(f"\nPlayers with no DB match: {len(unique_unmatched)} (out of {total_inserted + len(unique_unmatched)} total)")
    if unique_unmatched[:20]:
        print("Sample unmatched:")
        for name, team in sorted(unique_unmatched)[:20]:
            print(f"  - {name} ({team})")

    # Update player_nat_stats from match_players
    print("\nUpdating player_nat_stats...")
    # The player_nat_stats schema is per-match (has match_id column), not aggregate
    # Insert one row per player per match where we have a player_id
    conn.execute("""
        INSERT OR IGNORE INTO player_nat_stats
        (player_id, match_id, match_date, opponent, minutes, goals, assists, rating, was_starter)
        SELECT
            mp.player_id,
            NULL as match_id,
            mp.match_date,
            NULL as opponent,
            mp.minutes_played,
            mp.goals,
            mp.assists,
            NULLIF(mp.rating, 0.0) as rating,
            mp.started
        FROM match_players mp
        WHERE mp.player_id IS NOT NULL
          AND mp.competition = 'WC'
          AND mp.season = 2022
    """)
    conn.commit()
    pns_count = conn.execute("SELECT COUNT(*) FROM player_nat_stats").fetchone()[0]
    print(f"  player_nat_stats rows now: {pns_count}")

    # Final summary
    mp_count = conn.execute("SELECT COUNT(*) FROM match_players").fetchone()[0]
    mp_with_pid = conn.execute("SELECT COUNT(*) FROM match_players WHERE player_id IS NOT NULL").fetchone()[0]
    print(f"\nFinal match_players count: {mp_count}")
    print(f"Rows with matched player_id: {mp_with_pid} ({100*mp_with_pid//mp_count if mp_count else 0}%)")

    # Print top scorers as sanity check
    print("\nTop scorers in match_players (WC 2022):")
    rows = conn.execute("""
        SELECT player_name, SUM(goals) as g, SUM(assists) as a, COUNT(*) as apps
        FROM match_players
        WHERE competition='WC' AND season=2022
        GROUP BY player_api_id
        ORDER BY g DESC
        LIMIT 15
    """).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}G {r[2]}A in {r[3]} apps")

    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
