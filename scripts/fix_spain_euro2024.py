#!/usr/bin/env python3
"""
Fix Spain Euro 2024 player data gaps.
Maps StatsBomb Euro 2024 player IDs to DB projected_lineup player IDs.
"""
import json
import sqlite3

DB_PATH = "/home/user/mundial2026/data/mundial2026.db"

# db_player_id → sb_player_id (from Euro 2024 JSON)
# Also covers other missing players from projected lineups
MANUAL_LINKS = {
    61:   6765,    # Rodri → Rodrigo Hernández Cascante
    66:   68574,   # Nico Williams → Nicholas Williams Arthuer
    1175: 16532,   # Dani Olmo → Daniel Olmo Carvajal
    10371: 11748,  # Unai Simón → Unai Simón Mendibil
    # Pau Cubarsi (58) — debuted 2024/25, not in Euro 2024
    # Marcos Llorente (1171) — not in Euro 2024 squad
}

# Manual links for other teams' missing starters (from Euro/Copa/WC data)
OTHER_LINKS = {
    # Portugal
    # France
    # Brazil
}


def main():
    with open("/home/user/mundial2026/data/processed/statsbomb_euro2024.json") as f:
        euro = json.load(f)

    # Build sb_id → player data lookup
    euro_by_id = {p["sb_player_id"]: p for p in euro}
    euro_by_name = {p["name"]: p for p in euro}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find Pau Cubarsi and Marcos Llorente sb_ids in Euro 2024
    for name_frag, db_id in [("Cubarsí", 58), ("Cubarsi", 58), ("Llorente", 1171),
                              ("Grimaldo", 10373), ("Zubimendi", 10380)]:
        matches = [p for p in euro if name_frag.lower() in p["name"].lower() and p.get("team") == "Spain"]
        for m in matches:
            print(f"Found: {m['name']} (sb={m['sb_player_id']}) → db_id={db_id}")
            if db_id not in MANUAL_LINKS or MANUAL_LINKS[db_id] is None:
                MANUAL_LINKS[db_id] = m["sb_player_id"]

    # Also check Copa America for any missing
    with open("/home/user/mundial2026/data/processed/statsbomb_ca2024.json") as f:
        copa = json.load(f)
    copa_by_id = {p["sb_player_id"]: p for p in copa}

    # WC 2018 for players who played then
    with open("/home/user/mundial2026/data/processed/statsbomb_wc2018.json") as f:
        wc18 = json.load(f)
    wc18_by_id = {p["sb_player_id"]: p for p in wc18}

    print(f"\nManual links to apply: {MANUAL_LINKS}")

    updated = 0
    for db_id, sb_id in MANUAL_LINKS.items():
        if sb_id is None:
            continue

        # Get best stats from any available tournament
        sources = []
        if sb_id in euro_by_id:  sources.append(euro_by_id[sb_id])
        if sb_id in copa_by_id:  sources.append(copa_by_id[sb_id])
        if sb_id in wc18_by_id:  sources.append(wc18_by_id[sb_id])

        if not sources:
            print(f"  db_id={db_id} sb_id={sb_id}: not found in any tournament JSON")
            continue

        # Take MAX across all sources for each stat
        kp    = max(s.get("key_passes", 0) or 0 for s in sources)
        pc    = max(s.get("progressive_carries", 0) or 0 for s in sources)
        press = max(s.get("pressures", 0) or 0 for s in sources)
        blk   = max(s.get("blocks", 0) or 0 for s in sources)
        clr   = max(s.get("clearances", 0) or 0 for s in sources)
        xg    = max(s.get("xg_total", 0.0) or 0.0 for s in sources)
        sot   = max(s.get("shots_on_target", 0) or 0 for s in sources)
        goals = max(s.get("goals", 0) or 0 for s in sources)
        sbm   = max(s.get("matches", 0) or 0 for s in sources)
        name  = sources[0]["name"]

        print(f"  Updating db_id={db_id} ({name}): kp={kp} pc={pc} press={press} xg={xg:.2f} sbm={sbm}")

        # Update sb_player_id on players table
        conn.execute("UPDATE players SET sb_player_id=? WHERE id=?", (sb_id, db_id))

        # Check existing club stats row
        existing = conn.execute(
            "SELECT id, key_passes, progressive_carries, pressures, sb_matches FROM player_club_stats WHERE player_id=? AND season='2024/25'",
            (db_id,)
        ).fetchone()

        if existing:
            new_kp    = max(existing["key_passes"] or 0, kp)
            new_pc    = max(existing["progressive_carries"] or 0, pc)
            new_press = max(existing["pressures"] or 0, press)
            new_sbm   = max(existing["sb_matches"] or 0, sbm)
            conn.execute("""
                UPDATE player_club_stats SET
                    key_passes=?, progressive_carries=?, pressures=?,
                    blocks=?, clearances=?, sb_matches=?,
                    xg = CASE WHEN xg IS NULL OR xg=0 THEN ? ELSE xg END,
                    shots_on_target = CASE WHEN shots_on_target IS NULL OR shots_on_target=0 THEN ? ELSE shots_on_target END
                WHERE player_id=? AND season='2024/25'
            """, (new_kp, new_pc, new_press, blk, clr, new_sbm, xg, sot, db_id))
        else:
            conn.execute("""
                INSERT INTO player_club_stats
                    (player_id, season, league, club, matches, goals, shots_on_target,
                     xg, key_passes, progressive_carries, pressures, blocks, clearances, sb_matches)
                VALUES (?, '2024/25', 'Euro2024', 'Euro2024', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (db_id, sbm, goals, sot, xg, kp, pc, press, blk, clr, sbm))

        updated += 1

    conn.commit()
    print(f"\nUpdated {updated} players")

    # Verify Spain
    print("\nSpain XI verification:")
    rows = conn.execute("""
        SELECT p.name, pcs.key_passes, pcs.progressive_carries, pcs.pressures, pcs.xg, pcs.sb_matches
        FROM projected_lineups pl
        JOIN players p ON p.id=pl.player_id
        LEFT JOIN player_club_stats pcs ON pcs.player_id=p.id AND pcs.season='2024/25'
        JOIN teams t ON t.id=pl.team_id
        WHERE t.name='Spain' AND pl.is_starter=1
        ORDER BY pcs.sb_matches DESC NULLS LAST
    """).fetchall()
    for r in rows:
        print(f"  {r['name']}: kp={r['key_passes']} pc={r['progressive_carries']} press={r['pressures']} xg={r['xg'] or 0:.2f} sbm={r['sb_matches']}")

    conn.close()


if __name__ == "__main__":
    main()
