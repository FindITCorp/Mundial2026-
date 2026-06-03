#!/usr/bin/env python3
"""
Fetch AFCON 2023 player stats via statsbombpy (open data).
competition_id=1267, season_id=107 → 52 matches, 24 African teams.
"""

import json
import warnings
import time
from collections import defaultdict

import pandas as pd
warnings.filterwarnings('ignore')

from statsbombpy import sb

COMPETITION_ID = 1267
SEASON_ID = 107
OUTPUT = "/home/user/mundial2026/data/processed/statsbomb_afcon2023.json"


def is_progressive_carry(start, end):
    if not start or not end:
        return False
    try:
        dx = end[0] - start[0]
        return dx >= 10.0 and end[0] > start[0]
    except (IndexError, TypeError):
        return False


def process_match(events, player_stats, player_matches, match_id):
    for _, e in events.iterrows():
        pid = e.get("player_id")
        pname = e.get("player")
        etype = e.get("type")
        team = e.get("team")

        if not pd.notna(pid) or pd.isna(pname) or pd.isna(etype):
            continue

        key = (int(pid), str(pname), str(team))
        s = player_stats[key]
        s.setdefault("position", e.get("position") or "")
        s["team"] = team

        under_press = bool(e.get("under_pressure"))

        if etype == "Pass":
            s["passes"] = s.get("passes", 0) + 1
            # Key pass: directly creates a shot
            if e.get("pass_shot_assist") is True:
                s["key_passes"] = s.get("key_passes", 0) + 1
            outcome = e.get("pass_outcome")
            if outcome not in ["Incomplete", "Out", "Pass Offside"]:
                s["passes_completed"] = s.get("passes_completed", 0) + 1

        elif etype == "Carry":
            start = e.get("location")
            end = e.get("carry_end_location")
            if is_progressive_carry(start, end):
                s["progressive_carries"] = s.get("progressive_carries", 0) + 1

        elif etype == "Pressure":
            s["pressures"] = s.get("pressures", 0) + 1

        elif etype == "Interception":
            s["interceptions"] = s.get("interceptions", 0) + 1

        elif etype == "Block":
            s["blocks"] = s.get("blocks", 0) + 1

        elif etype == "Clearance":
            s["clearances"] = s.get("clearances", 0) + 1

        elif etype == "Shot":
            s["shots"] = s.get("shots", 0) + 1
            xg = e.get("shot_statsbomb_xg") or 0.0
            s["xg_total"] = s.get("xg_total", 0.0) + float(xg)
            outcome = e.get("shot_outcome")
            if outcome == "Goal":
                s["goals"] = s.get("goals", 0) + 1
            if outcome in ["Goal", "Saved", "Saved To Post"]:
                s["shots_on_target"] = s.get("shots_on_target", 0) + 1

        elif etype == "Duel":
            duel_type = e.get("duel_type")
            if duel_type == "Tackle":
                outcome = e.get("duel_outcome") or ""
                if outcome in ["Won", "Success", "Success In Play", "Success Out"]:
                    s["tackles_won"] = s.get("tackles_won", 0) + 1
                s["tackles"] = s.get("tackles", 0) + 1

    # Count match appearances
    for _, e in events[events["type"] == "Starting XI"].iterrows():
        lineup = e.get("tactics", {})
        if isinstance(lineup, dict):
            team = e.get("team")
            for p in lineup.get("lineup", []):
                p_id = p.get("player", {}).get("id")
                p_name = p.get("player", {}).get("name")
                if p_id and p_name:
                    player_matches[(int(p_id), str(p_name), str(team))].add(match_id)

    # Count substitutes (statsbombpy returns name as string, id as separate col)
    subs = events[events["type"] == "Substitution"]
    for _, e in subs.iterrows():
        p_name = e.get("substitution_replacement")
        p_id = e.get("substitution_replacement_id")
        team = e.get("team")
        if p_id and pd.notna(p_id) and p_name and pd.notna(p_name):
            player_matches[(int(p_id), str(p_name), str(team))].add(match_id)


def main():
    print(f"Fetching AFCON 2023 (comp={COMPETITION_ID}, season={SEASON_ID})...")
    matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID)
    print(f"Total matches: {len(matches)}")

    player_stats = defaultdict(dict)
    player_matches = defaultdict(set)

    for i, (_, match) in enumerate(matches.iterrows()):
        mid = int(match["match_id"])
        home = match["home_team"]
        away = match["away_team"]
        print(f"  [{i+1}/{len(matches)}] {home} vs {away} (id={mid})")

        try:
            events = sb.events(match_id=mid)
            process_match(events, player_stats, player_matches, mid)
        except Exception as ex:
            print(f"    ERROR: {ex}")

        time.sleep(0.15)

    # Set match counts
    for key, mids in player_matches.items():
        player_stats[key]["matches"] = len(mids)

    print(f"\nTotal players tracked: {len(player_stats)}")

    output = []
    for (pid, pname, team), stats in player_stats.items():
        stats["sb_player_id"] = pid
        stats["name"] = pname
        stats["team"] = team
        output.append(stats)

    output.sort(key=lambda x: x.get("key_passes", 0) + x.get("progressive_carries", 0), reverse=True)

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved to {OUTPUT}")
    print("\nTop 15 by key_passes + progressive_carries:")
    for p in output[:15]:
        print(f"  {p['name']} ({p['team']}): kp={p.get('key_passes',0)} pc={p.get('progressive_carries',0)} "
              f"press={p.get('pressures',0)} xg={p.get('xg_total',0.0):.2f} matches={p.get('matches',0)}")


if __name__ == "__main__":
    main()
