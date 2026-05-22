#!/usr/bin/env python3
"""Step 1: Load goalscorers CSV and add players to DB."""
import csv, io, sqlite3, urllib.request
from pathlib import Path

DB = Path("/home/user/mundial2026/data/mundial2026.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

teams = {r['name']: r['id'] for r in conn.execute("SELECT id, name FROM teams").fetchall()}
existing_players = set()
for r in conn.execute("SELECT LOWER(name), team_id FROM players").fetchall():
    existing_players.add((r[0], r[1]))

ALIASES = {
    "united states": "USA",
    "korea republic": "South Korea",
    "republic of ireland": "Ireland",
    "ir iran": "Iran",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "cape verde islands": "Cape Verde",
    "guinea bissau": "Guinea-Bissau",
    "trinidad & tobago": "Trinidad and Tobago",
    "chinese taipei": "Taiwan",
    "hong kong": "Hong Kong",
    "north macedonia": "North Macedonia",
    "czech republic": "Czech Republic",
    "central african rep.": "Central African Republic",
    "st. kitts & nevis": "Saint Kitts and Nevis",
    "antigua & barbuda": "Antigua and Barbuda",
    "st. lucia": "Saint Lucia",
    "st. vincent / grenadines": "Saint Vincent and the Grenadines",
    "turks & caicos islands": "Turks and Caicos Islands",
    "u.s. virgin islands": "US Virgin Islands",
    "british virgin islands": "British Virgin Islands",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "dpr korea": "North Korea",
    "congo dr": "DR Congo",
    "congo": "Congo",
}

def find_team_id(name):
    n = name.strip()
    if n in teams: return teams[n]
    n2 = ALIASES.get(n.lower())
    if n2 and n2 in teams: return teams[n2]
    for k, v in teams.items():
        if n.lower() == k.lower(): return v
    for k, v in teams.items():
        if n.lower() in k.lower() or k.lower() in n.lower(): return v
    return None

def add_player(team_id, name, position='MID', club='', league='', age=None, caps=0, goals=0):
    name = name.strip()
    if not name or len(name) < 3: return False
    pos_map = {
        'GK': 'GK', 'DF': 'DEF', 'MF': 'MID', 'FW': 'FWD',
        'DEF': 'DEF', 'MID': 'MID', 'FWD': 'FWD',
        'CB': 'DEF', 'LB': 'DEF', 'RB': 'DEF', 'LWB': 'DEF', 'RWB': 'DEF',
        'CM': 'MID', 'DM': 'MID', 'AM': 'MID', 'LM': 'MID', 'RM': 'MID',
        'CF': 'FWD', 'SS': 'FWD', 'LW': 'FWD', 'RW': 'FWD', 'ST': 'FWD',
        'ATT': 'FWD', 'FOR': 'FWD',
    }
    pos = pos_map.get(position.upper()[:3], 'MID')
    if (name.lower(), team_id) in existing_players: return False
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO players (name, team_id, position, club, club_league, age, caps, goals_as_nat)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, team_id, pos, club or '', league or '', age, caps or 0, goals or 0))
        if cur.rowcount:
            pid = cur.lastrowid
            conn.execute("INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed) VALUES (?,?,1)",
                        (team_id, pid))
            existing_players.add((name.lower(), team_id))
            return True
    except Exception as e:
        print(f"  Error adding {name}: {e}")
    return False

total_added = 0

print("Loading goalscorers CSV...")
url = "https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        content = r.read().decode('utf-8')
    print(f"  Downloaded {len(content)} bytes")
except Exception as e:
    print(f"  Failed to download: {e}")
    exit(1)

reader = csv.DictReader(io.StringIO(content))
player_goals = {}
player_teams = {}
for row in reader:
    if row.get('date', '') < '2018-01-01': continue
    if row.get('own_goal', '').strip().upper() == 'TRUE': continue
    team = row.get('team', '').strip()
    scorer = row.get('scorer', '').strip()
    if team and scorer:
        key = (team, scorer)
        player_goals[key] = player_goals.get(key, 0) + 1

print(f"  Found {len(player_goals)} unique scorers since 2018")

for (team_name, player_name), goals in sorted(player_goals.items(), key=lambda x: -x[1]):
    tid = find_team_id(team_name)
    if not tid: continue
    added = add_player(tid, player_name, 'MID', goals=goals)
    if added: total_added += 1

conn.commit()
print(f"Added {total_added} players from goalscorers CSV")

# Report
print("\nPlayer counts after step 1:")
rows = conn.execute("""
    SELECT t.name, COUNT(p.id) as cnt
    FROM teams t LEFT JOIN players p ON t.id = p.team_id
    GROUP BY t.id ORDER BY cnt ASC
""").fetchall()
for r in rows:
    print(f"  {r[1]:3d}  {r[0]}")
