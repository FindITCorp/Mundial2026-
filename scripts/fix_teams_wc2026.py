"""
fix_teams_wc2026.py — Corrects the 48 qualified teams for WC 2026.

Removes 14 teams that didn't qualify, adds 14 that did.
Updates group assignments and FIFA rankings (April 2026).
Adds win_prob_pct and odds_american columns with bookmaker data.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# ─── Official 48 teams with correct groups (from FIFA official draw) ──────────
OFFICIAL_GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# ─── Teams that did NOT qualify (must be removed) ────────────────────────────
TEAMS_TO_REMOVE = [
    "Honduras", "Cameroon", "Venezuela", "Romania", "Costa Rica",
    "Poland", "Jamaica", "Serbia", "Nigeria", "Hungary",
    "Bolivia", "Slovenia", "Denmark", "Italy",
]

# ─── New teams to add (not previously in DB) ─────────────────────────────────
# (name, slug, confederation, fifa_ranking, group)
NEW_TEAMS = [
    ("South Africa",          "south_africa",          "CAF",      60,  "A"),
    ("Czechia",               "czechia",               "UEFA",     41,  "A"),
    ("Bosnia and Herzegovina","bosnia_and_herzegovina","UEFA",     65,  "B"),
    ("Qatar",                 "qatar",                 "AFC",      55,  "B"),
    ("Haiti",                 "haiti",                 "CONCACAF", 83,  "C"),
    ("Curacao",               "curacao",               "CONCACAF", 82,  "E"),
    ("Ivory Coast",           "ivory_coast",           "CAF",      34,  "E"),
    ("Sweden",                "sweden",                "UEFA",     38,  "F"),
    ("Tunisia",               "tunisia",               "CAF",      44,  "F"),
    ("New Zealand",           "new_zealand",           "OFC",      85,  "G"),
    ("Cape Verde",            "cape_verde",            "CAF",      69,  "H"),
    ("Norway",                "norway",                "UEFA",     31,  "I"),
    ("Algeria",               "algeria",               "CAF",      28,  "J"),
    ("Uzbekistan",            "uzbekistan",            "AFC",      50,  "K"),
]

# ─── Updated FIFA rankings (April 2026 official) ─────────────────────────────
UPDATED_RANKINGS = {
    "France":       1,
    "Spain":        2,
    "Argentina":    3,
    "England":      4,
    "Portugal":     5,
    "Brazil":       6,
    "Netherlands":  7,
    "Morocco":      8,
    "Belgium":      9,
    "Germany":      10,
    "USA":          11,
    "Japan":        12,
    "Croatia":      13,
    "Colombia":     14,
    "Mexico":       15,
    "Uruguay":      16,
    "Switzerland":  17,
    "South Korea":  18,
    "Ecuador":      19,
    "Senegal":      20,
    "Iran":         21,
    "Denmark":      22,  # won't be in DB but listed for reference
    "Austria":      23,
    "Turkey":       24,
    "Iraq":         25,
    "Saudi Arabia": 26,
    "Australia":    27,
    "Algeria":      28,
    "Scotland":     29,
    "Paraguay":     30,
    "Norway":       31,
    "Ghana":        32,
    "Ivory Coast":  34,
    "Egypt":        35,
    "Sweden":       38,
    "Czechia":      41,
    "Tunisia":      44,
    "DR Congo":     47,
    "Uzbekistan":   50,
    "Jordan":       49,
    "Qatar":        55,
    "South Africa": 60,
    "Cape Verde":   69,
    "Bosnia and Herzegovina": 65,
    "Canada":       48,
    "Panama":       44,
    "Curacao":      82,
    "Haiti":        83,
    "New Zealand":  85,
}

# ─── Bookmaker odds & Opta win probability for tournament ────────────────────
# odds_american: American format (+450 means bet 100 to win 450)
# win_prob_opta: Opta supercomputer % | win_prob_book: bookmaker implied %
BETTING_DATA = {
    "France":       {"odds": 450,   "prob_opta": 12.8, "prob_book": 18.2},
    "Spain":        {"odds": 475,   "prob_opta": 17.0, "prob_book": 17.4},
    "England":      {"odds": 625,   "prob_opta": 11.0, "prob_book": 13.8},
    "Brazil":       {"odds": 800,   "prob_opta": 7.5,  "prob_book": 11.1},
    "Argentina":    {"odds": 800,   "prob_opta": 8.7,  "prob_book": 11.1},
    "Portugal":     {"odds": 1000,  "prob_opta": 6.9,  "prob_book": 9.1},
    "Germany":      {"odds": 1400,  "prob_opta": 7.1,  "prob_book": 6.7},
    "Netherlands":  {"odds": 2000,  "prob_opta": 4.0,  "prob_book": 4.8},
    "Belgium":      {"odds": 2500,  "prob_opta": 3.5,  "prob_book": 3.8},
    "Mexico":       {"odds": 2500,  "prob_opta": 2.5,  "prob_book": 3.8},
    "Colombia":     {"odds": 3000,  "prob_opta": 2.0,  "prob_book": 3.2},
    "USA":          {"odds": 4000,  "prob_opta": 0.9,  "prob_book": 2.4},
    "Morocco":      {"odds": 4000,  "prob_opta": 3.0,  "prob_book": 2.4},
    "Japan":        {"odds": 4000,  "prob_opta": 1.5,  "prob_book": 2.4},
    "Uruguay":      {"odds": 4000,  "prob_opta": 1.8,  "prob_book": 2.4},
    "Senegal":      {"odds": 5000,  "prob_opta": 1.2,  "prob_book": 2.0},
    "South Korea":  {"odds": 5000,  "prob_opta": 0.8,  "prob_book": 2.0},
    "Switzerland":  {"odds": 5000,  "prob_opta": 1.0,  "prob_book": 2.0},
    "Norway":       {"odds": 5000,  "prob_opta": 1.5,  "prob_book": 2.0},
    "Algeria":      {"odds": 5000,  "prob_opta": 1.0,  "prob_book": 2.0},
    "Croatia":      {"odds": 8000,  "prob_opta": 0.8,  "prob_book": 1.2},
    "Austria":      {"odds": 7000,  "prob_opta": 0.7,  "prob_book": 1.4},
    "Ecuador":      {"odds": 7000,  "prob_opta": 0.6,  "prob_book": 1.4},
    "Ivory Coast":  {"odds": 7000,  "prob_opta": 0.8,  "prob_book": 1.4},
    "Czechia":      {"odds": 7000,  "prob_opta": 0.5,  "prob_book": 1.4},
    "Sweden":       {"odds": 7500,  "prob_opta": 0.7,  "prob_book": 1.3},
    "Australia":    {"odds": 8000,  "prob_opta": 0.3,  "prob_book": 1.2},
    "Scotland":     {"odds": 10000, "prob_opta": 0.3,  "prob_book": 1.0},
    "Tunisia":      {"odds": 10000, "prob_opta": 0.3,  "prob_book": 1.0},
    "Ghana":        {"odds": 10000, "prob_opta": 0.2,  "prob_book": 1.0},
    "Paraguay":     {"odds": 10000, "prob_opta": 0.2,  "prob_book": 1.0},
    "Turkey":       {"odds": 10000, "prob_opta": 0.5,  "prob_book": 1.0},
    "Iraq":         {"odds": 12000, "prob_opta": 0.1,  "prob_book": 0.8},
    "Jordan":       {"odds": 15000, "prob_opta": 0.04, "prob_book": 0.7},
    "Canada":       {"odds": 12000, "prob_opta": 0.3,  "prob_book": 0.8},
    "Bosnia and Herzegovina": {"odds": 15000, "prob_opta": 0.2, "prob_book": 0.7},
    "Iran":         {"odds": 15000, "prob_opta": 0.2,  "prob_book": 0.7},
    "Egypt":        {"odds": 12000, "prob_opta": 0.3,  "prob_book": 0.8},
    "DR Congo":     {"odds": 20000, "prob_opta": 0.1,  "prob_book": 0.5},
    "Cape Verde":   {"odds": 20000, "prob_opta": 0.1,  "prob_book": 0.5},
    "Saudi Arabia": {"odds": 15000, "prob_opta": 0.1,  "prob_book": 0.7},
    "South Africa": {"odds": 20000, "prob_opta": 0.1,  "prob_book": 0.5},
    "Qatar":        {"odds": 25000, "prob_opta": 0.04, "prob_book": 0.4},
    "Uzbekistan":   {"odds": 50000, "prob_opta": 0.2,  "prob_book": 0.2},
    "New Zealand":  {"odds": 50000, "prob_opta": 0.1,  "prob_book": 0.2},
    "Haiti":        {"odds": 50000, "prob_opta": 0.05, "prob_book": 0.2},
    "Curacao":      {"odds": 100000,"prob_opta": 0.04, "prob_book": 0.1},
    "Panama":       {"odds": 22000, "prob_opta": 0.1,  "prob_book": 0.45},
}

# ─── Default tactical profiles by confederation ──────────────────────────────
STYLE_MAP = {
    "CONMEBOL": ("high",   "attacking",  6.5, "4-3-3"),
    "UEFA":     ("medium", "possession", 6.0, "4-2-3-1"),
    "CONCACAF": ("medium", "counter",    5.5, "4-4-2"),
    "CAF":      ("high",   "physical",   5.5, "4-3-3"),
    "AFC":      ("medium", "disciplined",5.0, "4-5-1"),
    "OFC":      ("low",    "defensive",  4.5, "4-4-2"),
}


def run():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")  # disable FK during cleanup
    cur = conn.cursor()

    # 1. Add new columns if missing
    existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(teams)")]
    for col, coltype in [("win_prob_opta", "REAL"), ("win_prob_book", "REAL"),
                         ("odds_american", "INTEGER")]:
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE teams ADD COLUMN {col} {coltype}")
            print(f"  Added column: teams.{col}")
    conn.commit()

    # 2. Remove teams that didn't qualify + cascade their data
    removed = 0
    for name in TEAMS_TO_REMOVE:
        row = cur.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        if not row:
            print(f"  SKIP (not found): {name}")
            continue
        tid = row[0]
        for tbl in ["player_club_stats", "player_nat_stats", "player_ratings",
                    "squad_selections", "match_players"]:
            try:
                cur.execute(f"""
                    DELETE FROM {tbl} WHERE player_id IN
                    (SELECT id FROM players WHERE team_id=?)
                """, (tid,))
            except Exception:
                pass
        cur.execute("DELETE FROM players WHERE team_id=?", (tid,))
        cur.execute("DELETE FROM team_matches WHERE team_id=?", (tid,))
        cur.execute("DELETE FROM wc_history WHERE team_id=?", (tid,))
        cur.execute("DELETE FROM squad_selections WHERE team_id=?", (tid,))
        cur.execute("DELETE FROM teams WHERE id=?", (tid,))
        print(f"  REMOVED: {name}")
        removed += 1
    conn.commit()
    print(f"\n  Removed {removed} teams.")

    # 3. Add new qualified teams
    added = 0
    for name, slug, conf, ranking, group in NEW_TEAMS:
        exists = cur.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        if exists:
            print(f"  EXISTS (skip add): {name}")
            continue

        d_line, style, pressing, formation = STYLE_MAP.get(conf, ("medium","balanced",5.0,"4-3-3"))
        goals_avg    = max(0.8, 2.0 - (ranking - 1) * 0.012)
        conceded_avg = min(2.5, 0.8 + (ranking - 1) * 0.015)
        poss_avg     = max(38.0, 58.0 - (ranking - 1) * 0.2)

        bet = BETTING_DATA.get(name, {})
        cur.execute("""
            INSERT INTO teams
                (name, slug, confederation, fifa_ranking, wc_group,
                 goals_scored_avg, goals_conceded_avg, possession_avg,
                 formation, pressing_intensity, defensive_line, tactical_style,
                 win_prob_opta, win_prob_book, odds_american)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            name, slug, conf, ranking, group,
            round(goals_avg, 2), round(conceded_avg, 2), round(poss_avg, 1),
            formation, pressing, d_line, style,
            bet.get("prob_opta"), bet.get("prob_book"), bet.get("odds"),
        ))
        print(f"  ADDED: {name} (#{ranking}, Group {group})")
        added += 1
    conn.commit()
    print(f"\n  Added {added} new teams.")

    # 4. Update group assignments for all teams
    group_map = {}
    for grp, teams in OFFICIAL_GROUPS.items():
        for t in teams:
            group_map[t] = grp

    # Name aliases (our DB name → official name)
    ALIASES = {"Turkey": "Turkey", "South Korea": "South Korea"}

    updated_groups = 0
    for db_name, official_name in {**{t: t for grp in OFFICIAL_GROUPS.values() for t in grp},
                                    "Turkey": "Turkey", "South Korea": "South Korea"}.items():
        grp = group_map.get(db_name) or group_map.get(official_name)
        if not grp:
            continue
        r = cur.execute("UPDATE teams SET wc_group=? WHERE name=?", (grp, db_name))
        if r.rowcount:
            updated_groups += 1
    conn.commit()
    print(f"\n  Updated {updated_groups} group assignments.")

    # 5. Update FIFA rankings (April 2026)
    updated_rankings = 0
    for name, rank in UPDATED_RANKINGS.items():
        r = cur.execute("UPDATE teams SET fifa_ranking=? WHERE name=?", (rank, name))
        if r.rowcount:
            updated_rankings += 1
    conn.commit()
    print(f"  Updated {updated_rankings} FIFA rankings.")

    # 6. Add betting data to existing teams
    updated_odds = 0
    for name, bet in BETTING_DATA.items():
        r = cur.execute("""
            UPDATE teams SET
                win_prob_opta=?, win_prob_book=?, odds_american=?
            WHERE name=?
        """, (bet["prob_opta"], bet["prob_book"], bet["odds"], name))
        if r.rowcount:
            updated_odds += 1
    conn.commit()
    print(f"  Updated {updated_odds} teams with betting odds.")

    # 7. Fix opponent_name references in team_matches for removed teams
    # (just leave them as they are — historical records are still valid data)

    # Summary
    print("\n=== FINAL DB STATE ===")
    teams = cur.execute("""
        SELECT confederation, COUNT(*) FROM teams GROUP BY confederation ORDER BY confederation
    """).fetchall()
    total = cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    print(f"  Total teams: {total}")
    for conf, n in teams:
        print(f"  {conf:<10}: {n}")

    print("\n  Groups:")
    for grp in "ABCDEFGHIJKL":
        rows = cur.execute(
            "SELECT name FROM teams WHERE wc_group=? ORDER BY fifa_ranking",
            (grp,)
        ).fetchall()
        names = " / ".join(r[0] for r in rows)
        print(f"  Group {grp}: {names}")

    print("\n  Top 10 by win_prob_book:")
    top = cur.execute("""
        SELECT name, fifa_ranking, win_prob_opta, win_prob_book, odds_american
        FROM teams WHERE win_prob_book IS NOT NULL
        ORDER BY win_prob_book DESC LIMIT 10
    """).fetchall()
    for r in top:
        print(f"  {r[0]:<28} FIFA#{r[1]:<4} Opta:{r[2]:.1f}% Book:{r[3]:.1f}% +{r[4]}")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    run()
