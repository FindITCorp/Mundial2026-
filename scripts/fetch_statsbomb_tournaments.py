#!/usr/bin/env python3
"""
Fetch player stats from multiple StatsBomb tournaments:
  - Copa America 2024  (comp_id=223, season_id=282)
  - UEFA Euro 2024     (comp_id=55,  season_id=282)
  - FIFA WC 2018       (comp_id=43,  season_id=3)
  - AFCON 2023         (comp_id=3,   season_id=?)  — probe first

Per-player aggregates: key_passes, progressive_carries, pressures,
blocks, clearances, xG, goals, shots_on_target, matches.

Results saved per tournament and merged into DB.
"""

import requests
import json
import sqlite3
import time
import unicodedata
import re
from collections import defaultdict
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
DB_PATH  = "/home/user/mundial2026/data/mundial2026.db"
OUT_DIR  = Path("/home/user/mundial2026/data/processed")

TOURNAMENTS = [
    {"name": "Copa America 2024",  "comp_id": 223, "season_id": 282, "tag": "ca2024"},
    {"name": "UEFA Euro 2024",     "comp_id": 55,  "season_id": 282, "tag": "euro2024"},
    {"name": "FIFA WC 2018",       "comp_id": 43,  "season_id": 3,   "tag": "wc2018"},
    {"name": "AFCON 2023",         "comp_id": 464, "season_id": 282, "tag": "afcon2023"},  # will probe
]


def normalize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", ascii_.lower()).strip()


def is_progressive_carry(start, end) -> bool:
    """Ball advances 10+ units toward goal (x=120 in StatsBomb coords)."""
    if not start or not end:
        return False
    return (end[0] - start[0]) >= 10.0 and end[0] > start[0]


def is_key_pass(pass_data: dict) -> bool:
    return bool(pass_data.get("shot_assist") or pass_data.get("goal_assist"))


def process_events(events: list, player_stats: dict, match_id: int, player_matches: dict):
    for e in events:
        player = e.get("player")
        if not player:
            continue
        pid  = player["id"]
        pname = player["name"]
        team  = e.get("team", {}).get("name", "")
        etype = e["type"]["name"]
        pos   = e.get("position", {}).get("name", "")

        key = (pid, pname, team)
        s = player_stats[key]
        if not s.get("position"):
            s["position"] = pos
        s["team"] = team

        if etype == "Pass":
            pd = e.get("pass", {})
            s["passes"] = s.get("passes", 0) + 1
            if is_key_pass(pd):
                s["key_passes"] = s.get("key_passes", 0) + 1
            outcome = pd.get("outcome", {}).get("name", "")
            if outcome not in ("Incomplete", "Out", "Pass Offside", "Unknown"):
                s["passes_completed"] = s.get("passes_completed", 0) + 1

        elif etype == "Carry":
            start = e.get("location")
            end   = e.get("carry", {}).get("end_location")
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

        elif etype == "Duel":
            duel = e.get("duel", {})
            if duel.get("type", {}).get("name") == "Tackle":
                s["tackles"] = s.get("tackles", 0) + 1
                outcome = duel.get("outcome", {}).get("name", "")
                if outcome in ("Won", "Success", "Success In Play", "Success Out"):
                    s["tackles_won"] = s.get("tackles_won", 0) + 1

        elif etype == "Shot":
            shot = e.get("shot", {})
            s["shots"] = s.get("shots", 0) + 1
            s["xg_total"] = s.get("xg_total", 0.0) + (shot.get("statsbomb_xg") or 0.0)
            outcome_name = shot.get("outcome", {}).get("name", "")
            if outcome_name == "Goal":
                s["goals"] = s.get("goals", 0) + 1
            if outcome_name in ("Goal", "Saved", "Saved To Post"):
                s["shots_on_target"] = s.get("shots_on_target", 0) + 1

        # Track match appearances via Starting XI + substitutions
        player_matches[key].add(match_id)


def fetch_tournament(comp_id: int, season_id: int, name: str) -> list | None:
    """Fetch and aggregate all events in a tournament. Returns list of player dicts."""
    url = f"{BASE_URL}/matches/{comp_id}/{season_id}.json"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        print(f"  ✗ {name}: matches not found (HTTP {r.status_code})")
        return None

    matches = r.json()
    print(f"  {name}: {len(matches)} partidos")

    player_stats   = defaultdict(dict)
    player_matches = defaultdict(set)

    for i, match in enumerate(matches):
        mid  = match["match_id"]
        home = match["home_team"]["home_team_name"]
        away = match["away_team"]["away_team_name"]
        print(f"    [{i+1}/{len(matches)}] {home} vs {away}")

        try:
            ev_r = requests.get(f"{BASE_URL}/events/{mid}.json", timeout=30)
            if ev_r.status_code != 200:
                continue
            events = ev_r.json()
            process_events(events, player_stats, mid, player_matches)
        except Exception as ex:
            print(f"    ERROR match {mid}: {ex}")

        time.sleep(0.15)

    # Set match counts
    for key, mids in player_matches.items():
        player_stats[key]["matches"] = len(mids)

    output = []
    for (pid, pname, team), stats in player_stats.items():
        stats["sb_player_id"] = pid
        stats["name"]         = pname
        stats["team"]         = team
        output.append(stats)

    return output


def import_to_db(player_list: list, tournament_tag: str, conn: sqlite3.Connection):
    """
    Upsert player stats into player_club_stats.
    Uses tournament_tag as 'league' and '2024/25' as season
    (or '2023/24' for WC2018 data which uses older players).
    Maps players by sb_player_id first, then normalized name.
    """
    # Build DB lookup: sb_player_id → player_id
    id_map = {}
    rows = conn.execute("SELECT id, sb_player_id FROM players WHERE sb_player_id IS NOT NULL").fetchall()
    for r in rows:
        id_map[r["sb_player_id"]] = r["id"]

    # Also name → player_id fallback
    name_map = {}
    for r in conn.execute("SELECT id, name FROM players").fetchall():
        name_map[normalize(r["name"])] = r["id"]

    season = "2024/25"

    matched = updated = inserted = 0
    unmatched = []

    for sp in player_list:
        sb_id = sp.get("sb_player_id")
        pid   = id_map.get(sb_id)

        if pid is None:
            # Try name match
            sb_norm = normalize(sp["name"])
            pid = name_map.get(sb_norm)

            # Partial: 2+ word overlap
            if pid is None:
                sb_parts = set(sb_norm.split())
                for dname, did in name_map.items():
                    if len(sb_parts & set(dname.split())) >= 2:
                        pid = did
                        break

        if pid is None:
            unmatched.append(sp["name"])
            continue

        # Update sb_player_id if not set
        conn.execute("UPDATE players SET sb_player_id=? WHERE id=? AND sb_player_id IS NULL",
                     (sb_id, pid))
        # Update name_map for future lookups
        id_map[sb_id] = pid

        kp    = sp.get("key_passes",          0) or 0
        pc    = sp.get("progressive_carries",  0) or 0
        press = sp.get("pressures",            0) or 0
        blk   = sp.get("blocks",               0) or 0
        clr   = sp.get("clearances",           0) or 0
        xg    = sp.get("xg_total",           0.0) or 0.0
        sot   = sp.get("shots_on_target",      0) or 0
        goals = sp.get("goals",                0) or 0
        wc_m  = sp.get("matches",              0) or 0

        existing = conn.execute(
            "SELECT id, key_passes, progressive_carries, pressures, sb_matches "
            "FROM player_club_stats WHERE player_id=? AND season=?", (pid, season)
        ).fetchone()

        if existing:
            # Merge: take MAX per metric across all tournaments
            new_kp    = max(existing["key_passes"]          or 0, kp)
            new_pc    = max(existing["progressive_carries"] or 0, pc)
            new_press = max(existing["pressures"]           or 0, press)
            new_wc_m  = max(existing["sb_matches"]          or 0, wc_m)
            conn.execute("""
                UPDATE player_club_stats SET
                    key_passes          = ?,
                    progressive_carries = ?,
                    pressures           = ?,
                    blocks = MAX(COALESCE(blocks, 0), ?),
                    clearances = MAX(COALESCE(clearances, 0), ?),
                    xg = CASE WHEN (xg IS NULL OR xg = 0) THEN ? ELSE MAX(xg, ?) END,
                    shots_on_target = CASE WHEN shots_on_target = 0 THEN ? ELSE shots_on_target END,
                    sb_matches = ?
                WHERE player_id=? AND season=?
            """, (new_kp, new_pc, new_press, blk, clr, xg, xg, sot, new_wc_m, pid, season))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO player_club_stats
                    (player_id, season, league, club, matches, goals, shots_on_target,
                     xg, key_passes, progressive_carries, pressures, blocks, clearances, sb_matches)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pid, season, tournament_tag, tournament_tag, wc_m, goals, sot,
                  xg, kp, pc, press, blk, clr, wc_m))
            inserted += 1
        matched += 1

    print(f"    matched={matched}  updated={updated}  inserted={inserted}  "
          f"unmatched={len(unmatched)}")
    if unmatched[:10]:
        print(f"    Unmatched sample: {unmatched[:10]}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Check AFCON 2023 competition id — probe multiple
    print("Probing AFCON 2023...")
    for comp_id in [464, 9, 6, 368, 4, 17]:
        for season_id in [282, 281, 235, 315, 43]:
            r = requests.get(f"{BASE_URL}/matches/{comp_id}/{season_id}.json", timeout=10)
            if r.status_code == 200:
                matches = r.json()
                if matches and any('Africa' in str(m) or 'Morocco' in str(m['home_team']) or
                                   'Senegal' in str(m['home_team'])
                                   for m in matches[:3]):
                    print(f"  Found AFCON: comp_id={comp_id} season_id={season_id} ({len(matches)} matches)")
                    TOURNAMENTS[-1]["comp_id"]   = comp_id
                    TOURNAMENTS[-1]["season_id"] = season_id
                    break
        else:
            continue
        break

    all_stats = {}
    for t in TOURNAMENTS:
        print(f"\n{'='*60}")
        print(f"Processing: {t['name']}")
        stats = fetch_tournament(t["comp_id"], t["season_id"], t["name"])
        if stats:
            out_file = OUT_DIR / f"statsbomb_{t['tag']}.json"
            with open(out_file, "w") as f:
                json.dump(stats, f, indent=2)
            print(f"  Saved {len(stats)} players → {out_file}")

            print(f"  Importing to DB...")
            import_to_db(stats, t["tag"], conn)
            conn.commit()
            all_stats[t["tag"]] = stats

    print("\n\n=== VERIFICATION ===")
    for name in ["Luka Modrić", "Virgil van Dijk", "Rodri", "Pedri", "Lionel Messi",
                 "Sofyan Amrabat", "Achraf Hakimi", "Nicolo Barella", "Kylian Mbappé",
                 "Jude Bellingham", "Vinicius Junior", "Alexis Mac Allister"]:
        row = conn.execute("""
            SELECT p.name, pcs.key_passes, pcs.progressive_carries, pcs.pressures,
                   pcs.xg, pcs.sb_matches, pcs.league
            FROM players p JOIN player_club_stats pcs ON pcs.player_id=p.id
            WHERE p.name LIKE ? AND pcs.season='2024/25'
            LIMIT 1
        """, (f"%{name.split()[0]}%",)).fetchone()
        if row:
            print(f"  {row['name']}: kp={row['key_passes']} pc={row['progressive_carries']} "
                  f"press={row['pressures']} xg={row['xg']:.2f} wc_m={row['sb_matches']}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
