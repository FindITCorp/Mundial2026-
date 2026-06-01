#!/usr/bin/env python3
"""
Import WC2022 advanced stats into player_club_stats.
Adds: key_passes, progressive_carries, pressures, blocks, clearances columns.
Matches players by fuzzy name (normalized, accent-stripped).
"""

import json
import sqlite3
import unicodedata
import re

DB_PATH = "/home/user/mundial2026/data/mundial2026.db"
STATS_PATH = "/home/user/mundial2026/data/processed/wc2022_player_stats.json"


def normalize(name: str) -> str:
    """Normalize name: lowercase, strip accents, keep only letters/spaces."""
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = nfkd.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z ]', '', ascii_name.lower()).strip()


def get_last_first(name: str) -> str:
    """Extract last word (likely last name) for secondary matching."""
    parts = name.strip().split()
    return parts[-1].lower() if parts else ''


def main():
    with open(STATS_PATH) as f:
        sb_players = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Add columns if missing
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(player_club_stats)")}
    new_cols = ['key_passes', 'progressive_carries', 'pressures', 'blocks', 'clearances']
    for col in new_cols:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE player_club_stats ADD COLUMN {col} INTEGER DEFAULT 0")
            print(f"  Added column: {col}")

    conn.commit()

    # Also add to players table: sb_player_id for direct reference later
    player_cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    if 'sb_player_id' not in player_cols:
        conn.execute("ALTER TABLE players ADD COLUMN sb_player_id INTEGER")
        print("  Added column: players.sb_player_id")
    conn.commit()

    # Load all DB players (with projected lineups preference)
    db_players = conn.execute("""
        SELECT DISTINCT p.id, p.name, p.caps
        FROM players p
        JOIN projected_lineups pl ON pl.player_id = p.id
    """).fetchall()

    db_all = conn.execute("SELECT id, name FROM players").fetchall()

    # Build lookup: normalized name → player_id
    db_lookup = {}
    for row in db_all:
        key = normalize(row['name'])
        db_lookup[key] = row['id']
        # Also index by last name
        last = get_last_first(normalize(row['name']))
        if last not in db_lookup:
            db_lookup[last] = row['id']  # only if unique

    print(f"DB players indexed: {len(db_lookup)}")
    print(f"SB players to import: {len(sb_players)}")

    matched = 0
    unmatched = []

    for sp in sb_players:
        sb_name = sp['name']
        sb_norm = normalize(sb_name)
        sb_id = sp['sb_player_id']

        # Try exact normalized match first
        pid = db_lookup.get(sb_norm)

        # Try last name match
        if pid is None:
            sb_last = get_last_first(sb_norm)
            pid = db_lookup.get(sb_last)

        # Try partial: any DB name contains all words of SB name
        if pid is None:
            sb_parts = set(sb_norm.split())
            for dname, did in [(normalize(r['name']), r['id']) for r in db_all]:
                d_parts = set(dname.split())
                # If 2+ word overlap
                overlap = sb_parts & d_parts
                if len(overlap) >= 2:
                    pid = did
                    break

        if pid is None:
            unmatched.append(sb_name)
            continue

        # Upsert sb_player_id on players table
        conn.execute("UPDATE players SET sb_player_id = ? WHERE id = ?", (sb_id, pid))

        # Check if player has 2024/25 stats row
        existing = conn.execute(
            "SELECT id FROM player_club_stats WHERE player_id=? AND season='2024/25'",
            (pid,)
        ).fetchone()

        kp = sp.get('key_passes', 0) or 0
        pc = sp.get('progressive_carries', 0) or 0
        press = sp.get('pressures', 0) or 0
        blk = sp.get('blocks', 0) or 0
        clr = sp.get('clearances', 0) or 0
        xg = sp.get('xg_total', 0.0) or 0.0
        sot = sp.get('shots_on_target', 0) or 0
        goals = sp.get('goals', 0) or 0
        assists = 0  # StatsBomb doesn't aggregate this easily
        matches = sp.get('matches', 0) or 0

        if existing:
            conn.execute("""
                UPDATE player_club_stats SET
                    key_passes = ?,
                    progressive_carries = ?,
                    pressures = ?,
                    blocks = ?,
                    clearances = ?,
                    xg = CASE WHEN xg = 0 OR xg IS NULL THEN ? ELSE xg END,
                    shots_on_target = CASE WHEN shots_on_target = 0 THEN ? ELSE shots_on_target END
                WHERE player_id=? AND season='2024/25'
            """, (kp, pc, press, blk, clr, xg, sot, pid))
        else:
            conn.execute("""
                INSERT INTO player_club_stats
                    (player_id, season, league, club, matches, goals, shots_on_target,
                     xg, key_passes, progressive_carries, pressures, blocks, clearances)
                VALUES (?, '2024/25', 'WC2022', 'WC2022', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pid, matches, goals, sot, xg, kp, pc, press, blk, clr))

        matched += 1

    conn.commit()
    print(f"\nMatched & updated: {matched}/{len(sb_players)}")
    print(f"Unmatched: {len(unmatched)}")
    if unmatched[:20]:
        print("Sample unmatched:", unmatched[:20])

    # Verify key players
    print("\nVerification — key players:")
    for name in ['Luka Modrić', 'Luka Modric', 'Joško Gvardiol', 'Josko Gvardiol',
                 'Antoine Griezmann', 'Lionel Messi', 'Sofyan Amrabat', 'Rodrigo Hernandez',
                 'Takumi Minamino', 'Takehiro Tomiyasu']:
        row = conn.execute("""
            SELECT p.name, pcs.key_passes, pcs.progressive_carries, pcs.pressures, pcs.xg
            FROM players p
            JOIN player_club_stats pcs ON pcs.player_id=p.id
            WHERE p.name LIKE ? AND pcs.season='2024/25'
            LIMIT 1
        """, (f'%{name.split()[0]}%',)).fetchone()
        if row:
            print(f"  {row[0]}: kp={row[1]} pc={row[2]} press={row[3]} xg={row[4]:.2f}")


if __name__ == '__main__':
    main()
