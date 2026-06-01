#!/usr/bin/env python3
"""
Fetch WC 2022 player stats from StatsBomb open data.
Calculates per-player: key_passes, progressive_carries, pressures,
interceptions, blocks, and position.
"""

import requests
import json
import sqlite3
import time
import math
from collections import defaultdict

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
DB_PATH = "/home/user/mundial2026/data/mundial2026.db"


def get_matches():
    r = requests.get(f"{BASE_URL}/matches/43/106.json", timeout=30)
    return r.json()


def get_events(match_id):
    r = requests.get(f"{BASE_URL}/events/{match_id}.json", timeout=30)
    return r.json()


def is_progressive_carry(start, end):
    """A carry is progressive if it moves ball 10+ yards toward goal (towards x=120)."""
    if not start or not end:
        return False
    # StatsBomb pitch: 120x80. Goal at x=120
    dx = end[0] - start[0]
    # Must move forward AND advance at least 10 units toward opponent goal
    return dx >= 10.0 and end[0] > start[0]


def is_key_pass(pass_data):
    """Key pass: directly leads to a shot (shot_assist or goal_assist)."""
    return bool(pass_data.get('shot_assist') or pass_data.get('goal_assist'))


def process_match(events, player_stats):
    """Aggregate stats per player from a single match's events."""
    for e in events:
        player = e.get('player')
        if not player:
            continue
        pid = player['id']
        pname = player['name']
        etype = e['type']['name']
        position = e.get('position', {}).get('name', '')
        team = e.get('team', {}).get('name', '')

        key = (pid, pname, team)
        s = player_stats[key]
        s['position'] = position or s.get('position', '')
        s['team'] = team

        if etype == 'Pass':
            pass_data = e.get('pass', {})
            s['passes'] = s.get('passes', 0) + 1
            if is_key_pass(pass_data):
                s['key_passes'] = s.get('key_passes', 0) + 1
            if pass_data.get('outcome', {}).get('name') not in ['Incomplete', 'Out', 'Pass Offside']:
                s['passes_completed'] = s.get('passes_completed', 0) + 1

        elif etype == 'Carry':
            carry = e.get('carry', {})
            start = e.get('location')
            end = carry.get('end_location')
            if is_progressive_carry(start, end):
                s['progressive_carries'] = s.get('progressive_carries', 0) + 1

        elif etype == 'Pressure':
            s['pressures'] = s.get('pressures', 0) + 1

        elif etype == 'Interception':
            s['interceptions'] = s.get('interceptions', 0) + 1

        elif etype == 'Block':
            s['blocks'] = s.get('blocks', 0) + 1

        elif etype == 'Duel':
            duel = e.get('duel', {})
            if duel.get('type', {}).get('name') == 'Tackle':
                outcome = duel.get('outcome', {}).get('name', '')
                if outcome in ['Won', 'Success', 'Success In Play', 'Success Out']:
                    s['tackles_won'] = s.get('tackles_won', 0) + 1
                s['tackles'] = s.get('tackles', 0) + 1

        elif etype == 'Shot':
            shot = e.get('shot', {})
            s['shots'] = s.get('shots', 0) + 1
            s['xg_total'] = s.get('xg_total', 0.0) + (shot.get('statsbomb_xg') or 0.0)
            if shot.get('outcome', {}).get('name') == 'Goal':
                s['goals'] = s.get('goals', 0) + 1
            if shot.get('outcome', {}).get('name') in ['Goal', 'Saved', 'Saved To Post']:
                s['shots_on_target'] = s.get('shots_on_target', 0) + 1

        elif etype == 'Clearance':
            s['clearances'] = s.get('clearances', 0) + 1

        # Count appearances
        s['matches'] = s.get('matches', 0)  # updated separately


def main():
    print("Fetching WC 2022 matches from StatsBomb...")
    matches = get_matches()
    print(f"Total matches: {len(matches)}")

    player_stats = defaultdict(dict)
    player_matches = defaultdict(set)  # track unique matches per player

    for i, match in enumerate(matches):
        mid = match['match_id']
        home = match['home_team']['home_team_name']
        away = match['away_team']['away_team_name']
        print(f"  [{i+1}/{len(matches)}] {home} vs {away} (id={mid})")

        try:
            events = get_events(mid)
            process_match(events, player_stats)
            # Count match appearances via Starting XI
            for e in events:
                if e['type']['name'] == 'Starting XI':
                    lineup = e.get('tactics', {}).get('lineup', [])
                    team = e.get('team', {}).get('name', '')
                    for p in lineup:
                        pid = p['player']['id']
                        pname = p['player']['name']
                        player_matches[(pid, pname, team)].add(mid)
            # Also count subs
            for e in events:
                if e['type']['name'] == 'Substitution':
                    sub = e.get('substitution', {})
                    sub_player = sub.get('replacement', {})
                    if sub_player:
                        pid = sub_player['id']
                        pname = sub_player['name']
                        team = e.get('team', {}).get('name', '')
                        player_matches[(pid, pname, team)].add(mid)
        except Exception as ex:
            print(f"    ERROR: {ex}")

        time.sleep(0.2)

    # Set match counts
    for key, mids in player_matches.items():
        player_stats[key]['matches'] = len(mids)

    print(f"\nTotal players tracked: {len(player_stats)}")

    # Save to JSON for inspection
    output = []
    for (pid, pname, team), stats in player_stats.items():
        stats['sb_player_id'] = pid
        stats['name'] = pname
        stats['team'] = team
        output.append(stats)

    output.sort(key=lambda x: x.get('key_passes', 0) + x.get('progressive_carries', 0), reverse=True)

    with open('/home/user/mundial2026/data/processed/wc2022_player_stats.json', 'w') as f:
        json.dump(output, f, indent=2)

    print("Saved to data/processed/wc2022_player_stats.json")
    print("\nTop 15 by key_passes + progressive_carries:")
    for p in output[:15]:
        print(f"  {p['name']} ({p['team']}): kp={p.get('key_passes',0)} pc={p.get('progressive_carries',0)} "
              f"press={p.get('pressures',0)} int={p.get('interceptions',0)} xg={p.get('xg_total',0.0):.2f}")


if __name__ == '__main__':
    main()
