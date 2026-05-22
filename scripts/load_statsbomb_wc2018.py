#!/usr/bin/env python3
"""
Load StatsBomb open data for WC 2018 into match_players table.
WC 2022 (competition_id=43, season_id=106) is handled by another process — DO NOT touch.
WC 2014 is NOT available in StatsBomb open data.
WC 2018: competition_id=43, season_id=3
"""

import json
import sqlite3
import time
import sys
import urllib.request
from pathlib import Path

DB = Path("/home/user/mundial2026/data/mundial2026.db")
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

REQUEST_DELAY = 0.1  # seconds between requests to be polite

def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            print(f"  [attempt {attempt+1}] Error fetching {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None

# ---------------------------------------------------------------------------
# Position mapping
# ---------------------------------------------------------------------------
POSITION_MAP = {
    'Goalkeeper': 'GK',
    'Center Back': 'DEF',
    'Left Back': 'DEF',
    'Right Back': 'DEF',
    'Left Wing Back': 'DEF',
    'Right Wing Back': 'DEF',
    # Additional StatsBomb specific positions
    'Left Center Back': 'DEF',
    'Right Center Back': 'DEF',
    'Central Midfield': 'MID',
    'Defensive Midfield': 'MID',
    'Attacking Midfield': 'MID',
    'Left Midfield': 'MID',
    'Right Midfield': 'MID',
    'Left Center Midfield': 'MID',
    'Right Center Midfield': 'MID',
    'Center Defensive Midfield': 'MID',
    'Left Attacking Midfield': 'MID',
    'Right Attacking Midfield': 'MID',
    'Center Attacking Midfield': 'MID',
    'Center Forward': 'FWD',
    'Left Wing': 'FWD',
    'Right Wing': 'FWD',
    'Secondary Striker': 'FWD',
    'Left Center Forward': 'FWD',
    'Right Center Forward': 'FWD',
}

def map_position(sb_position):
    return POSITION_MAP.get(sb_position, 'MID')  # default to MID if unknown

# ---------------------------------------------------------------------------
# Team and player lookup maps from DB
# ---------------------------------------------------------------------------
def load_maps(conn):
    team_map = {}
    for row in conn.execute("SELECT id, name FROM teams").fetchall():
        team_map[row[1].lower().strip()] = row[0]  # name -> id

    player_map = {}
    for row in conn.execute("SELECT id, name, team_id FROM players").fetchall():
        player_map[row[1].lower().strip()] = row[0]

    return team_map, player_map

# Team name aliases (StatsBomb name -> DB name)
TEAM_ALIASES = {
    'iran': 'iran',
    'korea republic': 'south korea',
    'republic of korea': 'south korea',
    'usa': 'usa',
    'united states': 'usa',
    "côte d'ivoire": 'ivory coast',
    "cote d'ivoire": 'ivory coast',
    'ivory coast': 'ivory coast',
    'england': 'england',
    'russia': 'russia',
    'saudi arabia': 'saudi arabia',
    'egypt': 'egypt',
    'morocco': 'morocco',
    'nigeria': 'nigeria',
    'senegal': 'senegal',
    'tunisia': 'tunisia',
    'costa rica': 'costa rica',
    'panama': 'panama',
    'mexico': 'mexico',
    'colombia': 'colombia',
    'peru': 'peru',
    'uruguay': 'uruguay',
    'argentina': 'argentina',
    'brazil': 'brazil',
    'australia': 'australia',
    'japan': 'japan',
    'south korea': 'south korea',
    'denmark': 'denmark',
    'france': 'france',
    'germany': 'germany',
    'spain': 'spain',
    'portugal': 'portugal',
    'belgium': 'belgium',
    'croatia': 'croatia',
    'switzerland': 'switzerland',
    'sweden': 'sweden',
    'poland': 'poland',
    'iceland': 'iceland',
    'serbia': 'serbia',
}

def find_team(name, team_map):
    n = name.lower().strip()
    if n in team_map:
        return team_map[n]
    n2 = TEAM_ALIASES.get(n, n)
    if n2 in team_map:
        return team_map[n2]
    for k, v in team_map.items():
        if n in k or k in n:
            return v
    return None

def find_player(name, player_map):
    n = name.lower().strip()
    if n in player_map:
        return player_map[n]
    parts = n.split()
    if parts:
        last = parts[-1]
        candidates = [v for k, v in player_map.items() if k.split() and k.split()[-1] == last]
        if len(candidates) == 1:
            return candidates[0]
    return None

# ---------------------------------------------------------------------------
# Process a single match — returns list of row tuples ready for INSERT
# ---------------------------------------------------------------------------
def process_match(match, competition_label, season_year, team_map, player_map):
    match_id = match['match_id']
    fixture_api_id = -match_id
    match_date = match.get('match_date', '')

    # Fetch lineups
    lineups_url = f"{BASE}/lineups/{match_id}.json"
    lineups_data = fetch_json(lineups_url)
    time.sleep(REQUEST_DELAY)
    if not lineups_data:
        print(f"  Skipping match {match_id}: could not fetch lineups")
        return []

    # Fetch events
    events_url = f"{BASE}/events/{match_id}.json"
    events_data = fetch_json(events_url)
    time.sleep(REQUEST_DELAY)
    if not events_data:
        print(f"  Skipping match {match_id}: could not fetch events")
        return []

    # Build player stats dict keyed by (team_name, sb_player_id)
    team_players = {}

    for team_lineup in lineups_data:
        team_name = team_lineup.get('team_name', '')
        for p in team_lineup.get('lineup', []):
            sb_player_id = p.get('player_id')
            player_name = p.get('player_name', '')
            positions = p.get('positions', [])

            started = 0
            position_str = 'MID'

            if positions:
                for pos_entry in positions:
                    start_reason = pos_entry.get('start_reason', '')
                    pos_name = pos_entry.get('position', '')
                    if isinstance(pos_name, dict):
                        pos_name = pos_name.get('name', 'Central Midfield')

                    if start_reason == 'Starting XI':
                        started = 1
                        position_str = map_position(pos_name)
                        break
                    elif start_reason in ('Substitution', 'Player On'):
                        position_str = map_position(pos_name)

            key = (team_name, sb_player_id)
            team_players[key] = {
                'player_name': player_name,
                'position': position_str,
                'started': started,
                'sub_off_min': None,
                'sub_on_min': None,
                'goals': 0,
                'assists': 0,
                'yellow_cards': 0,
                'red_cards': 0,
                'shots_total': 0,
                'shots_on': 0,
                'passes_total': 0,
                'key_passes': 0,
                'tackles': 0,
                'interceptions': 0,
                'team_name': team_name,
                'sb_player_id': sb_player_id,
            }

    # Process events
    max_minute = 90

    for event in events_data:
        minute = event.get('minute', 0)
        if minute > max_minute:
            max_minute = minute

        t = event.get('type', {}).get('name', '')
        player_info = event.get('player', {})
        sb_player_id = player_info.get('id')
        player_name = player_info.get('name', '')
        team_name = event.get('team', {}).get('name', '')
        key = (team_name, sb_player_id)

        # Ensure player exists in dict
        if key not in team_players and sb_player_id:
            team_players[key] = {
                'player_name': player_name,
                'position': 'MID',
                'started': 0,
                'sub_off_min': None,
                'sub_on_min': None,
                'goals': 0,
                'assists': 0,
                'yellow_cards': 0,
                'red_cards': 0,
                'shots_total': 0,
                'shots_on': 0,
                'passes_total': 0,
                'key_passes': 0,
                'tackles': 0,
                'interceptions': 0,
                'team_name': team_name,
                'sb_player_id': sb_player_id,
            }

        p = team_players.get(key)

        if t == 'Substitution':
            sub_info = event.get('substitution', {})
            replacement = sub_info.get('replacement', {})
            replacement_id = replacement.get('id')
            if p:
                p['sub_off_min'] = minute
            if replacement_id:
                rep_key = (team_name, replacement_id)
                if rep_key in team_players:
                    team_players[rep_key]['sub_on_min'] = minute

        elif t == 'Shot' and p:
            shot = event.get('shot', {})
            outcome = shot.get('outcome', {}).get('name', '')
            shot_type = shot.get('type', {}).get('name', '')
            p['shots_total'] += 1
            if outcome in ('Goal', 'Saved', 'Saved To Post', 'Saved to Post'):
                p['shots_on'] += 1
            if outcome == 'Goal' and shot_type != 'Own Goal':
                p['goals'] += 1

        elif t == 'Pass' and p:
            p['passes_total'] += 1
            pass_data = event.get('pass', {})
            if pass_data.get('goal_assist'):
                p['assists'] += 1
            if pass_data.get('shot_assist') or pass_data.get('key_pass_id'):
                p['key_passes'] += 1

        elif t == 'Bad Behaviour' and p:
            card = event.get('bad_behaviour', {}).get('card', {}).get('name', '')
            if 'Yellow' in card and 'Second' not in card:
                p['yellow_cards'] += 1
            if 'Red' in card or 'Second Yellow' in card:
                p['red_cards'] += 1

        elif t == 'Duel' and p:
            duel = event.get('duel', {})
            if duel.get('type', {}).get('name') == 'Tackle':
                p['tackles'] += 1

        elif t == 'Interception' and p:
            p['interceptions'] += 1

    # Calculate minutes played
    effective_max = max(90, max_minute)
    for key, p in team_players.items():
        if p['started']:
            p['minutes_played'] = p['sub_off_min'] if p['sub_off_min'] is not None else effective_max
        else:
            p['minutes_played'] = max(1, effective_max - p['sub_on_min']) if p['sub_on_min'] is not None else 0

    # Build rows
    rows = []
    for key, p in team_players.items():
        if p['minutes_played'] == 0 and not p['started']:
            continue  # skip unused subs

        tid = find_team(p['team_name'], team_map)
        pid = find_player(p['player_name'], player_map)
        sb_pid = p['sb_player_id']

        rows.append((
            fixture_api_id,
            tid,
            pid,
            sb_pid,
            p['player_name'],
            p['position'],
            p['started'],
            p['minutes_played'],
            p['goals'],
            p['assists'],
            p['yellow_cards'],
            p['red_cards'],
            None,  # rating
            p['shots_total'],
            p['shots_on'],
            p['passes_total'],
            p['key_passes'],
            p['tackles'],
            p['interceptions'],
            match_date,
            competition_label,
            season_year,
        ))

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    total_inserted = 0
    matches_processed = 0

    competitions_to_load = [
        # (competition_id, season_id, label, year)
        (43, 3, 'FIFA World Cup', 2018),
        # WC 2014 is NOT available in StatsBomb open data
        # WC 2022 (competition_id=43, season_id=106) handled by another process — DO NOT touch
    ]

    # Open fresh connection (no row_factory to avoid any issues)
    conn = sqlite3.connect(str(DB))
    # Use isolation_level=None for autocommit, we'll commit manually
    conn.isolation_level = None

    team_map, player_map = load_maps(conn)
    print(f"Loaded {len(team_map)} teams, {len(player_map)} players from DB")

    for comp_id, season_id, label, year in competitions_to_load:
        print(f"\n{'='*60}")
        print(f"Loading {label} {year} (competition_id={comp_id}, season_id={season_id})")
        print(f"{'='*60}")

        matches_url = f"{BASE}/matches/{comp_id}/{season_id}.json"
        matches = fetch_json(matches_url)
        if not matches:
            print(f"ERROR: Could not fetch matches for {label} {year}")
            continue

        print(f"Found {len(matches)} matches")

        conn.execute("BEGIN")
        batch_inserted = 0

        for i, match in enumerate(matches):
            match_id = match['match_id']
            home = match.get('home_team', {}).get('home_team_name', '?')
            away = match.get('away_team', {}).get('away_team_name', '?')
            match_date = match.get('match_date', '?')
            print(f"  [{i+1:2d}/{len(matches)}] Match {match_id}: {home} vs {away} ({match_date})", end=' ... ')
            sys.stdout.flush()

            rows = process_match(match, label, year, team_map, player_map)
            n = 0
            for row in rows:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO match_players
                        (fixture_api_id, team_id, player_id, player_api_id, player_name,
                         position, started, minutes_played, goals, assists,
                         yellow_cards, red_cards, rating,
                         shots_total, shots_on, passes_total, key_passes,
                         tackles, interceptions, match_date, competition, season)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, row)
                    n += conn.execute("SELECT changes()").fetchone()[0]
                except Exception as e:
                    print(f"\n    DB error: {e} | row: {row[:5]}")

            batch_inserted += n
            total_inserted += n
            matches_processed += 1
            print(f"inserted {n} rows")

        conn.execute("COMMIT")
        print(f"\n  Batch committed: {batch_inserted} rows for {label} {year}")

    # Final summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Matches processed: {matches_processed}")
    print(f"Total rows inserted: {total_inserted}")

    total_in_db = conn.execute("SELECT COUNT(*) FROM match_players").fetchone()[0]
    by_season = conn.execute(
        "SELECT competition, season, COUNT(*) FROM match_players GROUP BY competition, season"
    ).fetchall()
    print(f"Total rows in match_players: {total_in_db}")
    print("Breakdown by competition/season:")
    for row in by_season:
        print(f"  {row[0]} {row[1]}: {row[2]} rows")

    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
