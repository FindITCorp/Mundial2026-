#!/usr/bin/env python3
"""
Import AFCON 2023 player stats into the DB from pre-fetched JSON.
Uses MAX-merge to avoid overwriting better data from other tournaments.
"""

import json
import sqlite3
import unicodedata
import re

DB_PATH = "/home/user/mundial2026/data/mundial2026.db"
STATS_PATH = "/home/user/mundial2026/data/processed/statsbomb_afcon2023.json"

MANUAL_MAP = {
    # sb_player_id → db player name fragment for direct lookup
    66878: "Achraf Hakimi",
    6998:  "Sofyan Amrabat",
    37760: "Sadio Mané",
    11277: "Victor Osimhen",   # "Victor James Osimhen" in StatsBomb
    8206:  "Hakim Ziyech",
    5582:  "Kalidou Koulibaly",
}


def normalize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", ascii_.lower()).strip()


def main():
    with open(STATS_PATH) as f:
        sb_players = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Ensure sb_matches column exists
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(player_club_stats)")}
    if "sb_matches" not in existing_cols:
        conn.execute("ALTER TABLE player_club_stats ADD COLUMN sb_matches INTEGER DEFAULT 0")
        conn.commit()
        print("  Added column: sb_matches")

    db_all = conn.execute("SELECT id, name FROM players").fetchall()

    # Build normalized lookup
    db_lookup = {}
    for row in db_all:
        key = normalize(row["name"])
        db_lookup[key] = row["id"]
        parts = normalize(row["name"]).split()
        if parts:
            last = parts[-1]
            if last not in db_lookup:
                db_lookup[last] = row["id"]

    # Build sb_player_id → db_id map from existing players table
    sb_id_map = {}
    for row in conn.execute("SELECT id, sb_player_id FROM players WHERE sb_player_id IS NOT NULL"):
        sb_id_map[row["sb_player_id"]] = row["id"]

    print(f"DB players indexed: {len(db_lookup)}")
    print(f"AFCON players to import: {len(sb_players)}")

    matched = 0
    unmatched = []

    for sp in sb_players:
        sb_name = sp["name"]
        sb_norm = normalize(sb_name)
        sb_id = sp["sb_player_id"]

        pid = None

        # 1. Manual map takes priority (corrects wrong sb_id mappings)
        if sb_id in MANUAL_MAP:
            hint = normalize(MANUAL_MAP[sb_id])
            # Try exact normalized match first, then partial
            pid = db_lookup.get(hint)
            if pid is None:
                for row in db_all:
                    if normalize(row["name"]) == hint:
                        pid = row["id"]
                        break
            if pid is None:
                hint_parts = set(hint.split())
                for row in db_all:
                    if hint_parts <= set(normalize(row["name"]).split()):
                        pid = row["id"]
                        break

        # 2. Try existing sb_player_id mapping
        if pid is None:
            pid = sb_id_map.get(sb_id)

        # 3. Exact normalized name
        if pid is None:
            pid = db_lookup.get(sb_norm)

        # 4. Last name
        if pid is None:
            parts = sb_norm.split()
            if parts:
                pid = db_lookup.get(parts[-1])

        # 5. Multi-word overlap
        if pid is None:
            sb_parts = set(sb_norm.split())
            if len(sb_parts) >= 2:
                for row in db_all:
                    d_parts = set(normalize(row["name"]).split())
                    if len(sb_parts & d_parts) >= 2:
                        pid = row["id"]
                        break

        if pid is None:
            unmatched.append(sb_name)
            continue

        # Store sb_player_id if not already set
        conn.execute(
            "UPDATE players SET sb_player_id = ? WHERE id = ? AND sb_player_id IS NULL",
            (sb_id, pid)
        )

        kp    = sp.get("key_passes", 0) or 0
        pc    = sp.get("progressive_carries", 0) or 0
        press = sp.get("pressures", 0) or 0
        blk   = sp.get("blocks", 0) or 0
        clr   = sp.get("clearances", 0) or 0
        xg    = sp.get("xg_total", 0.0) or 0.0
        sot   = sp.get("shots_on_target", 0) or 0
        goals = sp.get("goals", 0) or 0
        m     = sp.get("matches", 0) or 0

        existing = conn.execute(
            "SELECT id, key_passes, progressive_carries, pressures, blocks, clearances, sb_matches FROM player_club_stats WHERE player_id=? AND season='2024/25'",
            (pid,)
        ).fetchone()

        if existing:
            new_kp    = max(existing["key_passes"] or 0, kp)
            new_pc    = max(existing["progressive_carries"] or 0, pc)
            new_press = max(existing["pressures"] or 0, press)
            new_blk   = max(existing["blocks"] or 0, blk)
            new_clr   = max(existing["clearances"] or 0, clr)
            new_sbm   = max(existing["sb_matches"] or 0, m)
            conn.execute("""
                UPDATE player_club_stats SET
                    key_passes=?, progressive_carries=?, pressures=?,
                    blocks=?, clearances=?, sb_matches=?,
                    xg = CASE WHEN xg=0 OR xg IS NULL THEN ? ELSE xg END,
                    shots_on_target = CASE WHEN shots_on_target=0 THEN ? ELSE shots_on_target END
                WHERE player_id=? AND season='2024/25'
            """, (new_kp, new_pc, new_press, new_blk, new_clr, new_sbm, xg, sot, pid))
        else:
            conn.execute("""
                INSERT INTO player_club_stats
                    (player_id, season, league, club, matches, goals, shots_on_target,
                     xg, key_passes, progressive_carries, pressures, blocks, clearances, sb_matches)
                VALUES (?, '2024/25', 'AFCON2023', 'AFCON2023', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pid, m, goals, sot, xg, kp, pc, press, blk, clr, m))

        matched += 1

    conn.commit()
    print(f"\nMatched & updated: {matched}/{len(sb_players)}")
    print(f"Unmatched: {len(unmatched)}")
    if unmatched[:20]:
        print("Sample unmatched:", unmatched[:20])

    print("\nVerification — African WC2026 players:")
    for name in ["Achraf Hakimi", "Sofyan Amrabat", "Hakim Ziyech", "Sadio Mané",
                 "Victor Osimhen", "Kalidou Koulibaly", "Chancel Mbemba"]:
        row = conn.execute("""
            SELECT p.name, pcs.key_passes, pcs.progressive_carries, pcs.pressures, pcs.sb_matches
            FROM players p
            JOIN player_club_stats pcs ON pcs.player_id=p.id
            WHERE p.name LIKE ? AND pcs.season='2024/25'
            LIMIT 1
        """, (f"%{name.split()[0]}%",)).fetchone()
        if row:
            print(f"  {row[0]}: kp={row[1]} pc={row[2]} press={row[3]} sb_m={row[4]}")
        else:
            print(f"  {name}: NOT FOUND in DB")

    conn.close()


if __name__ == "__main__":
    main()
