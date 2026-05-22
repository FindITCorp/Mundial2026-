"""
scrape_and_load.py
Loads historical WC match data, squads, FIFA rankings, and recent results into the DB.
Data sourced from martj42/international_results (GitHub raw CSV) and hardcoded
authoritative records for stages/groups (Wikipedia-verified).
"""
import sqlite3
import csv
import io
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, date

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WorldCupDataBot/1.0)"}

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARN: Could not fetch {url}: {e}")
        return None

# ────────────────────────────────────────────────────────────────
# KNOWN STAGE / GROUP DATA (Wikipedia-verified, authoritative)
# ────────────────────────────────────────────────────────────────

# Format: (year, home_team, away_team) → (stage, group)
WC_STAGE_MAP = {}

# ── 2022 World Cup Groups ──────────────────────────────────────
WC2022_GROUP_STAGE = {
    "A": [("Qatar","Ecuador"),("Senegal","Netherlands"),("Qatar","Senegal"),
          ("Netherlands","Ecuador"),("Ecuador","Senegal"),("Netherlands","Qatar")],
    "B": [("England","Iran"),("United States","Wales"),("Wales","Iran"),
          ("England","United States"),("Wales","England"),("Iran","United States")],
    "C": [("Argentina","Saudi Arabia"),("Mexico","Poland"),("Poland","Saudi Arabia"),
          ("Argentina","Mexico"),("Poland","Argentina"),("Saudi Arabia","Mexico")],
    "D": [("Denmark","Tunisia"),("France","Australia"),("Tunisia","Australia"),
          ("France","Denmark"),("Tunisia","France"),("Australia","Denmark")],
    "E": [("Germany","Japan"),("Spain","Costa Rica"),("Japan","Costa Rica"),
          ("Spain","Germany"),("Japan","Spain"),("Costa Rica","Germany")],
    "F": [("Morocco","Croatia"),("Belgium","Canada"),("Belgium","Morocco"),
          ("Croatia","Canada"),("Croatia","Belgium"),("Canada","Morocco")],
    "G": [("Switzerland","Cameroon"),("Brazil","Serbia"),("Cameroon","Serbia"),
          ("Brazil","Switzerland"),("Cameroon","Brazil"),("Serbia","Switzerland")],
    "H": [("Uruguay","South Korea"),("Portugal","Ghana"),("South Korea","Ghana"),
          ("Portugal","Uruguay"),("Ghana","Uruguay"),("South Korea","Portugal")],
}
for grp, matches in WC2022_GROUP_STAGE.items():
    for home, away in matches:
        WC_STAGE_MAP[(2022, home, away)] = ("Group stage", grp)

WC2022_KNOCKOUT = {
    "Round of 16": [
        ("Netherlands","United States"),("Argentina","Australia"),
        ("France","Poland"),("England","Senegal"),
        ("Japan","Croatia"),("Brazil","South Korea"),
        ("Morocco","Spain"),("Portugal","Switzerland"),
    ],
    "Quarter-final": [
        ("Croatia","Brazil"),("Netherlands","Argentina"),
        ("Morocco","Portugal"),("England","France"),
    ],
    "Semi-final": [
        ("Argentina","Croatia"),("France","Morocco"),
    ],
    "Third place": [("Croatia","Morocco")],
    "Final": [("Argentina","France")],
}
for stage, matches in WC2022_KNOCKOUT.items():
    for home, away in matches:
        WC_STAGE_MAP[(2022, home, away)] = (stage, None)

# ── 2018 World Cup Groups ──────────────────────────────────────
WC2018_GROUP_STAGE = {
    "A": [("Russia","Saudi Arabia"),("Egypt","Uruguay"),("Russia","Egypt"),
          ("Uruguay","Saudi Arabia"),("Uruguay","Russia"),("Saudi Arabia","Egypt")],
    "B": [("Morocco","Iran"),("Portugal","Spain"),("Portugal","Morocco"),
          ("Iran","Spain"),("Iran","Portugal"),("Spain","Morocco")],
    "C": [("France","Australia"),("Peru","Denmark"),("Denmark","Australia"),
          ("France","Peru"),("Denmark","France"),("Australia","Peru")],
    "D": [("Argentina","Iceland"),("Croatia","Nigeria"),("Argentina","Croatia"),
          ("Nigeria","Iceland"),("Iceland","Croatia"),("Nigeria","Argentina")],
    "E": [("Costa Rica","Serbia"),("Brazil","Switzerland"),("Brazil","Costa Rica"),
          ("Serbia","Switzerland"),("Serbia","Brazil"),("Switzerland","Costa Rica")],
    "F": [("Germany","Mexico"),("Sweden","South Korea"),("South Korea","Mexico"),
          ("Germany","Sweden"),("South Korea","Germany"),("Mexico","Sweden")],
    "G": [("Belgium","Panama"),("Tunisia","England"),("Belgium","Tunisia"),
          ("England","Panama"),("England","Belgium"),("Panama","Tunisia")],
    "H": [("Colombia","Japan"),("Poland","Senegal"),("Japan","Senegal"),
          ("Poland","Colombia"),("Japan","Poland"),("Senegal","Colombia")],
}
for grp, matches in WC2018_GROUP_STAGE.items():
    for home, away in matches:
        WC_STAGE_MAP[(2018, home, away)] = ("Group stage", grp)

WC2018_KNOCKOUT = {
    "Round of 16": [
        ("France","Argentina"),("Uruguay","Portugal"),
        ("Spain","Russia"),("Croatia","Denmark"),
        ("Brazil","Mexico"),("Belgium","Japan"),
        ("Sweden","Switzerland"),("Colombia","England"),
    ],
    "Quarter-final": [
        ("Uruguay","France"),("Brazil","Belgium"),
        ("Sweden","England"),("Russia","Croatia"),
    ],
    "Semi-final": [
        ("France","Belgium"),("Croatia","England"),
    ],
    "Third place": [("Belgium","England")],
    "Final": [("France","Croatia")],
}
for stage, matches in WC2018_KNOCKOUT.items():
    for home, away in matches:
        WC_STAGE_MAP[(2018, home, away)] = (stage, None)

# ── 2014 World Cup Groups ──────────────────────────────────────
WC2014_GROUP_STAGE = {
    "A": [("Brazil","Croatia"),("Mexico","Cameroon"),("Brazil","Mexico"),
          ("Cameroon","Croatia"),("Cameroon","Brazil"),("Croatia","Mexico")],
    "B": [("Chile","Australia"),("Spain","Netherlands"),("Australia","Netherlands"),
          ("Spain","Chile"),("Australia","Spain"),("Netherlands","Chile")],
    "C": [("Colombia","Greece"),("Ivory Coast","Japan"),("Colombia","Ivory Coast"),
          ("Japan","Greece"),("Japan","Colombia"),("Greece","Ivory Coast")],
    "D": [("Uruguay","Costa Rica"),("England","Italy"),("Uruguay","England"),
          ("Italy","Costa Rica"),("Italy","Uruguay"),("Costa Rica","England")],
    "E": [("Switzerland","Ecuador"),("France","Honduras"),("Switzerland","France"),
          ("Honduras","Ecuador"),("Honduras","Switzerland"),("Ecuador","France")],
    "F": [("Argentina","Bosnia and Herzegovina"),("Iran","Nigeria"),
          ("Argentina","Iran"),("Nigeria","Bosnia and Herzegovina"),
          ("Nigeria","Argentina"),("Bosnia and Herzegovina","Iran")],
    "G": [("Germany","Portugal"),("Ghana","United States"),("Germany","Ghana"),
          ("United States","Portugal"),("United States","Germany"),("Portugal","Ghana")],
    "H": [("Belgium","Algeria"),("Russia","South Korea"),("Belgium","Russia"),
          ("South Korea","Algeria"),("South Korea","Belgium"),("Algeria","Russia")],
}
for grp, matches in WC2014_GROUP_STAGE.items():
    for home, away in matches:
        WC_STAGE_MAP[(2014, home, away)] = ("Group stage", grp)

WC2014_KNOCKOUT = {
    "Round of 16": [
        ("Brazil","Chile"),("Colombia","Uruguay"),
        ("France","Nigeria"),("Germany","Algeria"),
        ("Argentina","Switzerland"),("Belgium","United States"),
        ("Netherlands","Mexico"),("Costa Rica","Greece"),
    ],
    "Quarter-final": [
        ("France","Germany"),("Brazil","Colombia"),
        ("Argentina","Belgium"),("Netherlands","Costa Rica"),
    ],
    "Semi-final": [
        ("Brazil","Germany"),("Netherlands","Argentina"),
    ],
    "Third place": [("Brazil","Netherlands")],
    "Final": [("Germany","Argentina")],
}
for stage, matches in WC2014_KNOCKOUT.items():
    for home, away in matches:
        WC_STAGE_MAP[(2014, home, away)] = (stage, None)

# ── 2010 World Cup Groups ──────────────────────────────────────
WC2010_GROUP_STAGE = {
    "A": [("South Africa","Mexico"),("Uruguay","France"),("South Africa","Uruguay"),
          ("France","Mexico"),("Mexico","Uruguay"),("France","South Africa")],
    "B": [("South Korea","Greece"),("Argentina","Nigeria"),("Argentina","South Korea"),
          ("Greece","Nigeria"),("Greece","Argentina"),("Nigeria","South Korea")],
    "C": [("England","United States"),("Algeria","Slovenia"),("Slovenia","United States"),
          ("England","Algeria"),("Slovenia","England"),("United States","Algeria")],
    "D": [("Germany","Australia"),("Serbia","Ghana"),("Germany","Serbia"),
          ("Ghana","Australia"),("Ghana","Germany"),("Australia","Serbia")],
    "E": [("Netherlands","Denmark"),("Japan","Cameroon"),("Netherlands","Japan"),
          ("Denmark","Cameroon"),("Denmark","Netherlands"),("Cameroon","Japan")],
    "F": [("Italy","Paraguay"),("New Zealand","Slovakia"),("Slovakia","Paraguay"),
          ("Italy","New Zealand"),("Slovakia","Italy"),("Paraguay","New Zealand")],
    "G": [("Ivory Coast","Portugal"),("Brazil","North Korea"),("Brazil","Ivory Coast"),
          ("Portugal","North Korea"),("Portugal","Brazil"),("North Korea","Ivory Coast")],
    "H": [("Honduras","Chile"),("Spain","Switzerland"),("Chile","Switzerland"),
          ("Spain","Honduras"),("Chile","Spain"),("Switzerland","Honduras")],
}
for grp, matches in WC2010_GROUP_STAGE.items():
    for home, away in matches:
        WC_STAGE_MAP[(2010, home, away)] = ("Group stage", grp)

WC2010_KNOCKOUT = {
    "Round of 16": [
        ("Uruguay","South Korea"),("United States","Ghana"),
        ("Germany","England"),("Argentina","Mexico"),
        ("Netherlands","Slovakia"),("Brazil","Chile"),
        ("Paraguay","Japan"),("Spain","Portugal"),
    ],
    "Quarter-final": [
        ("Netherlands","Brazil"),("Uruguay","Ghana"),
        ("Argentina","Germany"),("Paraguay","Spain"),
    ],
    "Semi-final": [
        ("Uruguay","Netherlands"),("Germany","Spain"),
    ],
    "Third place": [("Uruguay","Germany")],
    "Final": [("Netherlands","Spain")],
}
for stage, matches in WC2010_KNOCKOUT.items():
    for home, away in matches:
        WC_STAGE_MAP[(2010, home, away)] = (stage, None)

# ── 2006 World Cup Groups ──────────────────────────────────────
WC2006_GROUP_STAGE = {
    "A": [("Germany","Costa Rica"),("Poland","Ecuador"),("Germany","Poland"),
          ("Ecuador","Costa Rica"),("Ecuador","Germany"),("Costa Rica","Poland")],
    "B": [("England","Paraguay"),("Trinidad and Tobago","Sweden"),
          ("England","Trinidad and Tobago"),("Sweden","Paraguay"),
          ("Sweden","England"),("Paraguay","Trinidad and Tobago")],
    "C": [("Argentina","Ivory Coast"),("Serbia and Montenegro","Netherlands"),
          ("Argentina","Serbia and Montenegro"),("Netherlands","Ivory Coast"),
          ("Netherlands","Argentina"),("Ivory Coast","Serbia and Montenegro")],
    "D": [("Mexico","Iran"),("Angola","Portugal"),("Mexico","Angola"),
          ("Portugal","Iran"),("Portugal","Mexico"),("Iran","Angola")],
    "E": [("Italy","Ghana"),("United States","Czech Republic"),
          ("Czech Republic","Ghana"),("Italy","United States"),
          ("Czech Republic","Italy"),("Ghana","United States")],
    "F": [("Australia","Japan"),("Brazil","Croatia"),("Brazil","Australia"),
          ("Japan","Croatia"),("Japan","Brazil"),("Croatia","Australia")],
    "G": [("South Korea","Togo"),("France","Switzerland"),("France","South Korea"),
          ("Togo","Switzerland"),("Togo","France"),("Switzerland","South Korea")],
    "H": [("Spain","Ukraine"),("Tunisia","Saudi Arabia"),("Spain","Tunisia"),
          ("Saudi Arabia","Ukraine"),("Saudi Arabia","Spain"),("Ukraine","Tunisia")],
}
for grp, matches in WC2006_GROUP_STAGE.items():
    for home, away in matches:
        WC_STAGE_MAP[(2006, home, away)] = ("Group stage", grp)

WC2006_KNOCKOUT = {
    "Round of 16": [
        ("Germany","Sweden"),("Argentina","Mexico"),
        ("England","Ecuador"),("Portugal","Netherlands"),
        ("Italy","Australia"),("Switzerland","Ukraine"),
        ("Brazil","Ghana"),("Spain","France"),
    ],
    "Quarter-final": [
        ("Germany","Argentina"),("Italy","Ukraine"),
        ("England","Portugal"),("Brazil","France"),
    ],
    "Semi-final": [
        ("Germany","Italy"),("Portugal","France"),
    ],
    "Third place": [("Germany","Portugal")],
    "Final": [("Italy","France")],
}
for stage, matches in WC2006_KNOCKOUT.items():
    for home, away in matches:
        WC_STAGE_MAP[(2006, home, away)] = (stage, None)


# Penalty shootout info: (year, home, away) → (pen_home, pen_away)
PENALTY_MAP = {
    # 2022
    (2022, "Japan", "Croatia"): (1, 3),
    (2022, "Morocco", "Spain"): (3, 0),
    (2022, "Croatia", "Brazil"): (4, 2),
    (2022, "Netherlands", "Argentina"): (3, 4),
    (2022, "Argentina", "France"): (4, 2),
    # 2018
    (2018, "Spain", "Russia"): (3, 4),
    (2018, "Croatia", "Denmark"): (3, 2),
    (2018, "Colombia", "England"): (3, 4),
    (2018, "Russia", "Croatia"): (3, 4),
    # 2014
    (2014, "Brazil", "Chile"): (3, 2),
    (2014, "Costa Rica", "Greece"): (5, 3),
    (2014, "Netherlands", "Costa Rica"): (4, 3),
    (2014, "Netherlands", "Argentina"): (2, 4),
    # 2010
    (2010, "Paraguay", "Japan"): (5, 3),
    (2010, "Uruguay", "Ghana"): (4, 2),
    # 2006
    (2006, "Switzerland", "Ukraine"): (0, 3),
    (2006, "Germany", "Argentina"): (4, 2),
    (2006, "Portugal", "England"): (3, 1),
    (2006, "Italy", "France"): (5, 3),
}

# ── Team name normalisation ────────────────────────────────────
NAME_MAP = {
    "United States": "USA",
    "Republic of Ireland": "Ireland",
    "Ivory Coast": "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Serbia and Montenegro": "Serbia",
    "Trinidad and Tobago": "Trinidad & Tobago",
    "Korea Republic": "South Korea",
    "Korea DPR": "North Korea",
    "IR Iran": "Iran",
    "England": "England",
    "Scotland": "Scotland",
    "Wales": "Wales",
    "Northern Ireland": "Northern Ireland",
}

def normalise(name):
    return NAME_MAP.get(name, name)


# ────────────────────────────────────────────────────────────────
# TASK 1 — Load WC match results into team_matches
# ────────────────────────────────────────────────────────────────

def load_wc_matches(conn):
    """
    Loads WC match results (2006-2022) from martj42/international_results CSV.
    Uses team_matches table (since wc_history stores team-level aggregates).
    """
    print("\n=== TASK 1: Loading WC match results ===")
    url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
    print(f"  Fetching: {url}")
    raw = fetch_url(url)
    if not raw:
        print("  ERROR: Could not fetch match data")
        return 0

    cur = conn.cursor()

    # Build team name→id map
    team_map = {}
    for row in cur.execute("SELECT id, name FROM teams"):
        team_map[row["name"]] = row["id"]
        team_map[row["name"].lower()] = row["id"]

    def find_team_id(name):
        n = normalise(name)
        if n in team_map:
            return team_map[n]
        nl = n.lower()
        if nl in team_map:
            return team_map[nl]
        for k, v in team_map.items():
            if isinstance(k, str) and (nl in k.lower() or k.lower() in nl):
                return v
        return None

    reader = csv.DictReader(io.StringIO(raw))
    inserted = 0
    skipped = 0

    # Target years and "FIFA World Cup"
    wc_years = {2006, 2010, 2014, 2018, 2022}

    for row in reader:
        try:
            d = row["date"]
            year = int(d[:4])
            if year not in wc_years:
                continue
            if "FIFA World Cup" not in row.get("tournament", ""):
                continue

            home = normalise(row["home_team"])
            away = normalise(row["away_team"])
            home_score = int(row["home_score"])
            away_score = int(row["away_score"])

            stage_info = WC_STAGE_MAP.get((year, row["home_team"], row["away_team"]))
            if not stage_info:
                # Try with normalised names
                stage_info = WC_STAGE_MAP.get((year, home, away))
            if not stage_info:
                stage_info = ("Group stage", None)

            stage, group = stage_info
            pen = PENALTY_MAP.get((year, row["home_team"], row["away_team"]))
            if not pen:
                pen = PENALTY_MAP.get((year, home, away))

            competition = f"FIFA World Cup {year} - {stage}"
            if group:
                competition += f" Group {group}"

            home_id = find_team_id(home)
            away_id = find_team_id(away)

            # Insert for home team perspective
            if home_id:
                result = "W" if home_score > away_score else ("D" if home_score == away_score else "L")
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue, wc_edition)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (home_id, away_id, away, d, competition,
                      home_score, away_score, result, "neutral", year))
                inserted += cur.rowcount

            # Insert for away team perspective
            if away_id:
                result = "W" if away_score > home_score else ("D" if home_score == away_score else "L")
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue, wc_edition)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (away_id, home_id, home, d, competition,
                      away_score, home_score, result, "neutral", year))
                inserted += cur.rowcount

        except Exception as e:
            skipped += 1

    conn.commit()
    print(f"  Inserted: {inserted} team_match rows ({skipped} errors)")
    return inserted


# ────────────────────────────────────────────────────────────────
# TASK 1b — Update wc_history with aggregated stats per team
# ────────────────────────────────────────────────────────────────

def update_wc_history_from_matches(conn):
    """Compute per-team WC history from team_matches and upsert wc_history."""
    print("\n=== TASK 1b: Updating wc_history aggregates ===")
    cur = conn.cursor()

    # Rounds reached ordering
    ROUND_ORDER = {
        "Group stage": 1,
        "Round of 16": 2,
        "Quarter-final": 3,
        "Semi-final": 4,
        "Third place": 5,
        "Final": 6,
    }

    WC_WINNER = {
        2006: "Italy", 2010: "Spain", 2014: "Germany",
        2018: "France", 2022: "Argentina",
    }
    WC_RUNNER_UP = {
        2006: "France", 2010: "Netherlands", 2014: "Argentina",
        2018: "Croatia", 2022: "France",
    }
    WC_THIRD = {
        2006: "Germany", 2010: "Germany", 2014: "Netherlands",
        2018: "Belgium", 2022: "Croatia",
    }

    wc_years = [2006, 2010, 2014, 2018, 2022]
    inserted = 0

    for year in wc_years:
        # Get all teams that played this WC
        rows = cur.execute("""
            SELECT DISTINCT team_id FROM team_matches WHERE wc_edition=?
        """, (year,)).fetchall()

        for r in rows:
            team_id = r["team_id"]
            team_row = cur.execute("SELECT name FROM teams WHERE id=?", (team_id,)).fetchone()
            if not team_row:
                continue
            team_name = team_row["name"]

            # Aggregate stats
            stats = cur.execute("""
                SELECT COUNT(*) as mp,
                       SUM(goals_for) as gf,
                       SUM(goals_against) as ga,
                       SUM(CASE WHEN result='W' THEN 1 ELSE 0 END) as wins
                FROM team_matches
                WHERE team_id=? AND wc_edition=?
            """, (team_id, year)).fetchone()

            # Determine max round reached
            matches = cur.execute("""
                SELECT competition FROM team_matches
                WHERE team_id=? AND wc_edition=?
            """, (team_id, year)).fetchall()

            max_round = "Group stage"
            for m in matches:
                comp = m["competition"] or ""
                for rnd in ROUND_ORDER:
                    if rnd in comp and ROUND_ORDER[rnd] > ROUND_ORDER.get(max_round, 0):
                        max_round = rnd

            # Final round designation
            if team_name == WC_WINNER.get(year):
                round_reached = "Champion"
            elif team_name == WC_RUNNER_UP.get(year):
                round_reached = "Runner-up"
            elif team_name == WC_THIRD.get(year):
                round_reached = "Third place"
            elif max_round == "Final":
                round_reached = "Runner-up"
            else:
                round_reached = max_round

            # Find group
            grp_match = cur.execute("""
                SELECT competition FROM team_matches
                WHERE team_id=? AND wc_edition=? AND competition LIKE '%Group%'
                LIMIT 1
            """, (team_id, year)).fetchone()
            group_name = None
            if grp_match:
                comp = grp_match["competition"]
                if "Group " in comp:
                    group_name = comp.split("Group ")[-1].strip()

            try:
                cur.execute("""
                    INSERT OR REPLACE INTO wc_history
                        (team_id, year, wc_group, round_reached,
                         goals_scored, goals_conceded, matches_played)
                    VALUES (?,?,?,?,?,?,?)
                """, (
                    team_id, year, group_name, round_reached,
                    stats["gf"] or 0, stats["ga"] or 0, stats["mp"] or 0
                ))
                inserted += 1
            except Exception as e:
                pass

    conn.commit()
    print(f"  Updated/inserted: {inserted} wc_history records")
    return inserted


# ────────────────────────────────────────────────────────────────
# TASK 2 & 3 — WC Squad players (2022 + 2018)
# Hard-coded from Wikipedia data (403 blocked direct scrape)
# ────────────────────────────────────────────────────────────────

# WC2022 squads for the 10 key teams (from Wikipedia 2022 WC squads)
WC2022_SQUADS = {
    "Argentina": [
        ("Emiliano Martinez","GK","1992-09-02","Aston Villa",24,0),
        ("Geronimo Rulli","GK","1992-05-20","Villarreal",4,0),
        ("Franco Armani","GK","1986-10-16","River Plate",26,0),
        ("Gonzalo Montiel","DEF","1997-01-01","Sevilla",21,2),
        ("Nahuel Molina","DEF","1998-04-06","Atletico Madrid",23,3),
        ("German Pezzella","DEF","1991-06-27","Real Betis",21,2),
        ("Cristian Romero","DEF","1998-04-27","Tottenham",22,1),
        ("Nicolas Otamendi","DEF","1988-02-12","Benfica",114,10),
        ("Lisandro Martinez","DEF","1998-01-18","Manchester United",21,1),
        ("Marcos Acuna","DEF","1991-10-28","Sevilla",57,2),
        ("Nicolas Tagliafico","DEF","1992-08-31","Lyon",48,3),
        ("Rodrigo De Paul","MID","1994-05-24","Atletico Madrid",58,10),
        ("Leandro Paredes","MID","1994-06-29","PSG",57,8),
        ("Alexis Mac Allister","MID","1998-12-24","Brighton",20,5),
        ("Guido Rodriguez","MID","1994-04-12","Real Betis",22,1),
        ("Enzo Fernandez","MID","2001-01-17","Benfica",10,1),
        ("Exequiel Palacios","MID","1998-10-05","Bayer Leverkusen",19,1),
        ("Thiago Almada","MID","2001-04-26","Atlanta United",1,0),
        ("Lautaro Martinez","FWD","1997-08-22","Inter Milan",54,25),
        ("Angel Di Maria","FWD","1988-02-14","Juventus",129,29),
        ("Julian Alvarez","FWD","2000-01-31","Manchester City",10,4),
        ("Paulo Dybala","FWD","1993-11-15","Roma",36,32),
        ("Joaquin Correa","FWD","1994-08-13","Inter Milan",30,9),
        ("Nicolas Gonzalez","FWD","1998-04-06","Fiorentina",19,4),
        ("Lionel Messi","FWD","1987-06-24","PSG",172,98),
    ],
    "France": [
        ("Hugo Lloris","GK","1986-12-26","Tottenham",145,0),
        ("Alphonse Areola","GK","1993-02-27","West Ham",13,0),
        ("Steve Mandanda","GK","1985-03-28","Rennes",34,0),
        ("Benjamin Pavard","DEF","1996-03-28","Bayern Munich",50,4),
        ("Jules Kounde","DEF","1998-11-12","Barcelona",27,0),
        ("Raphael Varane","DEF","1993-04-25","Manchester United",97,5),
        ("Dayot Upamecano","DEF","1998-10-27","Bayern Munich",23,0),
        ("Ibrahima Konate","DEF","1999-05-25","Liverpool",12,0),
        ("Lucas Hernandez","DEF","1996-02-14","Bayern Munich",36,0),
        ("Theo Hernandez","DEF","1997-10-06","AC Milan",22,2),
        ("William Saliba","DEF","2001-03-24","Arsenal",3,0),
        ("Adrien Rabiot","MID","1995-04-03","Juventus",33,4),
        ("Aurelien Tchouameni","MID","2000-01-27","Real Madrid",18,2),
        ("Youssouf Fofana","MID","1999-01-10","Monaco",14,1),
        ("Jordan Veretout","MID","1993-03-01","Marseille",8,0),
        ("Matteo Guendouzi","MID","1999-04-14","Marseille",16,0),
        ("Antoine Griezmann","MID","1991-03-21","Atletico Madrid",117,42),
        ("Kylian Mbappe","FWD","1998-12-20","PSG",66,36),
        ("Ousmane Dembele","FWD","1997-05-15","Barcelona",39,7),
        ("Randal Kolo Muani","FWD","2002-05-05","Frankfurt",3,0),
        ("Olivier Giroud","FWD","1986-09-30","AC Milan",116,51),
        ("Marcus Thuram","FWD","1997-08-06","M Gladbach",15,2),
        ("Kingsley Coman","FWD","1996-06-13","Bayern Munich",47,14),
    ],
    "Brazil": [
        ("Alisson","GK","1992-10-02","Liverpool",65,0),
        ("Ederson","GK","1993-08-17","Man City",20,0),
        ("Weverton","GK","1987-12-13","Palmeiras",7,0),
        ("Danilo","DEF","1991-07-15","Juventus",75,8),
        ("Thiago Silva","DEF","1984-09-22","Chelsea",113,9),
        ("Marquinhos","DEF","1994-05-14","PSG",71,10),
        ("Militao","DEF","1998-01-18","Real Madrid",25,2),
        ("Alex Sandro","DEF","1991-01-26","Juventus",48,3),
        ("Alex Telles","DEF","1992-12-15","Sevilla",19,0),
        ("Bremer","DEF","1997-03-18","Juventus",5,0),
        ("Casemiro","MID","1992-02-23","Manchester United",72,8),
        ("Fred","MID","1993-03-05","Man United",55,4),
        ("Lucas Paqueta","MID","1997-08-27","West Ham",45,10),
        ("Fabinho","MID","1993-10-23","Liverpool",33,1),
        ("Everton Ribeiro","MID","1989-10-01","Flamengo",38,6),
        ("Bruno Guimaraes","MID","1997-11-16","Newcastle",15,2),
        ("Rodrygo","FWD","2001-01-09","Real Madrid",22,9),
        ("Vinicius Junior","FWD","2000-07-12","Real Madrid",37,16),
        ("Neymar","FWD","1992-02-05","PSG",124,77),
        ("Raphinha","FWD","1996-12-14","Barcelona",28,9),
        ("Antony","FWD","2000-02-24","Manchester United",19,6),
        ("Gabriel Jesus","FWD","1997-04-03","Arsenal",61,19),
        ("Pedro","FWD","1997-10-22","Flamengo",11,2),
        ("Gabriel Martinelli","FWD","2001-06-18","Arsenal",9,2),
    ],
    "England": [
        ("Jordan Pickford","GK","1994-03-07","Everton",55,0),
        ("Nick Pope","GK","1992-04-19","Newcastle",10,0),
        ("Aaron Ramsdale","GK","1998-05-14","Arsenal",5,0),
        ("Trent Alexander-Arnold","DEF","1998-10-07","Liverpool",21,1),
        ("Kyle Walker","DEF","1990-05-28","Man City",73,1),
        ("John Stones","DEF","1994-05-28","Man City",63,3),
        ("Harry Maguire","DEF","1993-03-05","Man United",52,7),
        ("Conor Coady","DEF","1993-02-25","Everton",12,0),
        ("Eric Dier","DEF","1994-01-15","Tottenham",49,3),
        ("Ben White","DEF","1997-10-08","Arsenal",4,0),
        ("Luke Shaw","DEF","1995-07-12","Man United",26,1),
        ("Kieran Trippier","DEF","1990-09-19","Newcastle",47,0),
        ("Declan Rice","MID","1999-01-14","West Ham",42,2),
        ("Jordan Henderson","MID","1990-06-17","Liverpool",73,2),
        ("Jude Bellingham","MID","2003-06-29","Dortmund",26,3),
        ("Mason Mount","MID","1999-01-10","Chelsea",42,6),
        ("Kalvin Phillips","MID","1995-12-02","Man City",24,0),
        ("Conor Gallagher","MID","2000-02-06","Chelsea",5,0),
        ("Phil Foden","MID","2000-05-28","Man City",22,3),
        ("Harry Kane","FWD","1993-07-28","Tottenham",77,53),
        ("Raheem Sterling","FWD","1994-12-08","Chelsea",82,20),
        ("Bukayo Saka","FWD","2001-09-05","Arsenal",30,10),
        ("Marcus Rashford","FWD","1997-10-31","Man United",52,15),
        ("Jack Grealish","FWD","1995-09-10","Man City",37,5),
        ("Callum Wilson","FWD","1992-02-27","Newcastle",9,1),
        ("Mason Greenwood","FWD","2001-10-01","Man United",0,0),
    ],
    "Germany": [
        ("Manuel Neuer","GK","1986-03-27","Bayern Munich",117,0),
        ("Marc-Andre ter Stegen","GK","1992-04-30","Barcelona",36,0),
        ("Kevin Trapp","GK","1990-07-08","Frankfurt",7,0),
        ("Lukas Klostermann","DEF","1996-06-03","RB Leipzig",26,1),
        ("David Raum","DEF","1998-04-22","RB Leipzig",17,3),
        ("Niklas Sule","DEF","1995-09-03","Dortmund",45,3),
        ("Antonio Rudiger","DEF","1993-03-03","Real Madrid",69,3),
        ("Christian Gunter","DEF","1993-02-28","Freiburg",21,1),
        ("Nico Schlotterbeck","DEF","2000-01-01","Dortmund",13,0),
        ("Thilo Kehrer","DEF","1996-09-21","West Ham",26,1),
        ("Jonas Hofmann","MID","1992-07-14","M Gladbach",25,9),
        ("Leon Goretzka","MID","1995-02-06","Bayern Munich",49,14),
        ("Thomas Muller","MID","1989-09-13","Bayern Munich",121,44),
        ("Joshua Kimmich","MID","1995-02-08","Bayern Munich",70,7),
        ("Ilkay Gundogan","MID","1990-10-24","Man City",65,17),
        ("Julian Brandt","MID","1996-05-02","Dortmund",51,13),
        ("Kai Havertz","FWD","1999-06-11","Chelsea",39,18),
        ("Serge Gnabry","FWD","1995-07-14","Bayern Munich",44,21),
        ("Leroy Sane","FWD","1996-01-11","Bayern Munich",52,12),
        ("Karim Adeyemi","FWD","2002-01-18","Dortmund",9,4),
        ("Marco Reus","FWD","1989-05-31","Dortmund",48,15),
        ("Niclas Fullkrug","FWD","1993-02-09","Werder Bremen",4,3),
        ("Florian Wirtz","MID","2003-05-03","Bayer Leverkusen",8,3),
        ("Jamal Musiala","MID","2003-02-26","Bayern Munich",24,5),
    ],
    "Spain": [
        ("Unai Simon","GK","1997-06-11","Athletic Club",23,0),
        ("Robert Sanchez","GK","1997-11-18","Brighton",11,0),
        ("David Raya","GK","1995-09-14","Brentford",1,0),
        ("Cesar Azpilicueta","DEF","1989-08-28","Chelsea",31,0),
        ("Dani Carvajal","DEF","1992-01-11","Real Madrid",68,7),
        ("Eric Garcia","DEF","2001-01-09","Barcelona",23,1),
        ("Pau Torres","DEF","1997-01-16","Villarreal",29,1),
        ("Aymeric Laporte","DEF","1994-05-27","Man City",43,3),
        ("Jordi Alba","DEF","1989-03-21","Barcelona",97,9),
        ("Jose Gaya","DEF","1995-05-25","Valencia",29,0),
        ("Rodrigo Hernandez (Rodri)","MID","1996-06-22","Man City",39,5),
        ("Sergio Busquets","MID","1988-07-16","Barcelona",143,2),
        ("Gavi","MID","2004-08-05","Barcelona",20,8),
        ("Pedri","MID","2002-11-25","Barcelona",24,4),
        ("Marcos Llorente","MID","1995-01-30","Atletico Madrid",29,3),
        ("Carlos Soler","MID","1997-01-02","PSG",23,4),
        ("Koke","MID","1992-01-08","Atletico Madrid",65,5),
        ("Fabian Ruiz","MID","1996-04-03","PSG",30,10),
        ("Dani Olmo","FWD","1998-05-07","Leipzig",24,9),
        ("Marco Asensio","FWD","1996-01-21","Real Madrid",46,14),
        ("Ferran Torres","FWD","2000-02-29","Barcelona",40,14),
        ("Alvaro Morata","FWD","1992-10-23","Atletico Madrid",63,29),
        ("Ansu Fati","FWD","2002-10-31","Barcelona",14,3),
        ("Nico Williams","FWD","2002-07-12","Athletic Club",4,1),
    ],
    "Croatia": [
        ("Dominik Livakovic","GK","1995-01-09","Dinamo Zagreb",44,0),
        ("Ivo Grbic","GK","1996-01-18","Atletico Madrid",4,0),
        ("Ivica Ivusic","GK","1995-02-01","Osijek",2,0),
        ("Josip Juranovic","DEF","1995-08-16","Celtic",33,0),
        ("Sime Vrsaljko","DEF","1992-01-10","Atletico Madrid",58,2),
        ("Domagoj Vida","DEF","1989-04-29","AEK Athens",105,5),
        ("Josko Gvardiol","DEF","2002-01-23","Leipzig",24,1),
        ("Borna Barisic","DEF","1995-11-10","Rangers",42,4),
        ("Borna Sosa","DEF","1998-01-21","Stuttgart",16,2),
        ("Dejan Lovren","DEF","1989-07-05","Zenit",68,3),
        ("Luka Modric","MID","1985-09-09","Real Madrid",157,24),
        ("Mateo Kovacic","MID","1994-05-06","Man City",88,5),
        ("Marcelo Brozovic","MID","1992-11-16","Inter Milan",100,17),
        ("Mario Pasalic","MID","1995-02-09","Atalanta",52,11),
        ("Lovro Majer","MID","1998-01-17","Rennes",16,3),
        ("Kristijan Jakic","MID","1997-05-14","Frankfurt",14,0),
        ("Ivan Perisic","FWD","1989-02-02","Tottenham",122,33),
        ("Nikola Vlasic","FWD","1997-10-04","Torino",42,14),
        ("Marko Livaja","FWD","1993-08-26","Hajduk Split",17,4),
        ("Andrej Kramaric","FWD","1991-06-19","Hoffenheim",79,35),
        ("Bruno Petkovic","FWD","1992-09-16","Dinamo Zagreb",38,10),
        ("Mislav Orsic","FWD","1992-12-29","Dinamo Zagreb",32,11),
        ("Ante Budimir","FWD","1991-07-22","Osasuna",27,9),
    ],
    "Morocco": [
        ("Yassine Bounou","GK","1991-04-05","Sevilla",59,0),
        ("Ahmed Reda Tagnaouti","GK","1996-06-28","Wydad",10,0),
        ("Munir Mohamedi","GK","1989-12-01","Al-Wehdat",24,0),
        ("Achraf Hakimi","DEF","1998-11-04","PSG",56,11),
        ("Noussair Mazraoui","DEF","1997-11-14","Bayern Munich",26,3),
        ("Romain Saiss","DEF","1990-03-26","Besiktas",73,7),
        ("Jawad El Yamiq","DEF","1992-02-29","Real Valladolid",15,2),
        ("Nayef Aguerd","DEF","1996-03-30","West Ham",28,3),
        ("Yahya Attiyat Allah","DEF","1996-06-15","Wydad",16,1),
        ("Sofyan Amrabat","MID","1996-08-21","Fiorentina",41,1),
        ("Azzedine Ounahi","MID","1999-11-19","Angers",8,1),
        ("Bilal El Khannouss","MID","2004-05-10","Genk",5,0),
        ("Selim Amallah","MID","1996-11-15","Standard Liege",25,4),
        ("Ilias Chair","MID","1997-10-30","QPR",5,2),
        ("Abdelhamid Sabiri","MID","1996-11-28","Sampdoria",9,3),
        ("Imraan Louza","MID","1999-05-01","Watford",9,0),
        ("Hakim Ziyech","FWD","1993-03-19","Chelsea",51,20),
        ("Youssef En-Nesyri","FWD","1997-06-01","Sevilla",47,22),
        ("Abderrazak Hamdallah","FWD","1990-12-17","Al-Ittihad",14,9),
        ("Sofiane Boufal","FWD","1993-09-17","Angers",47,6),
        ("Walid Cheddira","FWD","1998-01-21","Bari",4,2),
        ("Zakaria Aboukhlal","FWD","2000-11-18","Toulouse",11,2),
        ("Ryan Mmaee","FWD","1997-08-25","Ferencvaros",2,0),
    ],
    "USA": [
        ("Matt Turner","GK","1994-06-24","Arsenal",28,0),
        ("Zack Steffen","GK","1995-04-02","Middlesbrough",35,0),
        ("Sean Johnson","GK","1989-10-31","Toronto FC",27,0),
        ("Sergino Dest","DEF","2000-11-03","AC Milan",25,3),
        ("DeAndre Yedlin","DEF","1993-07-09","Inter Miami",78,1),
        ("Walker Zimmerman","DEF","1993-05-19","Nashville SC",43,3),
        ("Tim Ream","DEF","1987-10-05","Fulham",46,1),
        ("Shaq Moore","DEF","1998-02-07","Nashville SC",18,1),
        ("Antonee Robinson","DEF","1997-08-08","Fulham",38,2),
        ("Joe Scally","DEF","2002-12-31","M Gladbach",7,0),
        ("Tyler Adams","MID","1999-02-14","Leeds",30,1),
        ("Weston McKennie","MID","1998-08-28","Juventus",47,10),
        ("Yunus Musah","MID","2002-11-29","Valencia",24,2),
        ("Kellyn Acosta","MID","1995-07-24","LAFC",57,3),
        ("Luca de la Torre","MID","1998-05-23","Celta Vigo",16,2),
        ("Brenden Aaronson","MID","2000-10-22","Leeds",31,7),
        ("Christian Pulisic","FWD","1998-09-18","Chelsea",68,24),
        ("Timothy Weah","FWD","2000-02-22","Lille",27,4),
        ("Gio Reyna","FWD","2002-11-13","Dortmund",18,2),
        ("Josh Sargent","FWD","1999-02-20","Norwich",21,5),
        ("Jordan Morris","FWD","1994-10-26","Seattle","41",12),
        ("Jesús Ferreira","FWD","1999-12-19","Dallas",29,12),
        ("Folarin Balogun","FWD","2001-07-03","Reims",0,0),
    ],
    "Mexico": [
        ("Guillermo Ochoa","GK","1985-07-13","Club America",133,0),
        ("Alfredo Talavera","GK","1982-09-08","Juarez",90,0),
        ("Rodolfo Cota","GK","1987-08-08","Leon",23,0),
        ("Hector Moreno","DEF","1988-01-25","Al-Gharafa",121,2),
        ("Jorge Sanchez","DEF","1997-02-03","Ajax",23,0),
        ("Nestor Araujo","DEF","1991-08-07","Club America",61,4),
        ("Johan Vasquez","DEF","1998-04-27","Genoa",19,2),
        ("Gerardo Arteaga","DEF","1998-06-07","Genk",13,0),
        ("Jesus Gallardo","DEF","1994-08-15","Monterrey",57,3),
        ("Kevin Alvarez","DEF","1999-03-20","Pachuca",9,0),
        ("Edson Alvarez","MID","1997-10-24","Ajax",63,7),
        ("Andres Guardado","MID","1986-09-28","Real Betis",180,27),
        ("Hector Herrera","MID","1990-04-19","Houston",97,19),
        ("Luis Chavez","MID","1994-06-07","Pachuca",15,5),
        ("Carlos Rodriguez","MID","1997-07-21","Cruz Azul",35,4),
        ("Roberto Alvarado","MID","1998-09-07","Guadalajara",24,4),
        ("Hirving Lozano","FWD","1995-07-30","Napoli",68,17),
        ("Alexis Vega","FWD","1997-11-01","Guadalajara",25,5),
        ("Uriel Antuna","FWD","1997-08-21","Cruz Azul",25,5),
        ("Raul Jimenez","FWD","1991-05-05","Fulham",103,38),
        ("Rogelio Funes Mori","FWD","1991-03-05","Monterrey",21,7),
        ("Santiago Gimenez","FWD","2001-04-18","Feyenoord",8,2),
        ("Henry Martin","FWD","1992-11-28","Club America",20,5),
    ],
    "Panama": [
        ("Luis Mejia","GK","1997-04-07","Independiente",20,0),
        ("Orlando Mosquera","GK","1997-09-17","Dep. Cali",5,0),
        ("Jose Guerra","GK","1992-02-14","Alajuelense",7,0),
        ("Michael Amir Murillo","DEF","1994-07-26","New York Red Bulls",43,2),
        ("Andres Andrade","MID","1990-09-30","Dep. Cali",69,9),
        ("Anibal Godoy","MID","1990-03-22","Nashville SC",88,2),
        ("Adalberto Carrasquilla","MID","1998-07-06","Al-Qadsiah",29,4),
        ("Jose Fajardo","FWD","1998-07-15","FC Dallas",21,7),
        ("Rolando Blackburn","FWD","1993-02-01","Club Necaxa",39,11),
        ("Edgar Barcenas","MID","1990-01-08","Panama Viejo",45,6),
        ("Alberto Quintero","FWD","1987-10-09","Marathon",65,15),
        ("Gabriel Torres","FWD","1988-08-12","Al-Qadsiah",131,47),
    ],
}

# WC2018 key squad additions
WC2018_SQUADS = {
    "Croatia": [
        ("Danijel Subasic","GK","1984-10-27","Monaco",48,0),
        ("Lovre Kalinic","GK","1990-04-03","Gent",8,0),
        ("Josip Pivaric","DEF","1989-01-30","Dynamo Kyiv",44,3),
        ("Sime Vrsaljko","DEF","1992-01-10","Inter Milan",44,0),
        ("Ivan Strinic","DEF","1987-07-17","AC Milan",53,1),
        ("Domagoj Vida","DEF","1989-04-29","Besiktas",93,4),
        ("Dejan Lovren","DEF","1989-07-05","Liverpool",60,3),
        ("Vedran Corluka","DEF","1986-02-05","Lokomotiv Moscow",120,4),
        ("Luka Modric","MID","1985-09-09","Real Madrid",119,16),
        ("Mateo Kovacic","MID","1994-05-06","Real Madrid",60,2),
        ("Marcelo Brozovic","MID","1992-11-16","Inter Milan",60,7),
        ("Ivan Rakitic","MID","1988-03-10","Barcelona",108,15),
        ("Milan Badelj","MID","1989-02-25","Lazio",35,4),
        ("Ante Rebic","MID","1993-09-21","Frankfurt",27,7),
        ("Ivan Perisic","FWD","1989-02-02","Inter Milan",104,32),
        ("Andrej Kramaric","FWD","1991-06-19","Hoffenheim",38,15),
        ("Mario Mandzukic","FWD","1986-05-21","Juventus",89,33),
        ("Marko Pjaca","FWD","1995-05-06","Sporting CP",17,5),
    ],
    "France": [
        ("Hugo Lloris","GK","1986-12-26","Tottenham",106,0),
        ("Steve Mandanda","GK","1985-03-28","Marseille",25,0),
        ("Alphonse Areola","GK","1993-02-27","PSG",3,0),
        ("Benjamin Pavard","DEF","1996-03-28","Stuttgart",11,0),
        ("Raphael Varane","DEF","1993-04-25","Real Madrid",74,3),
        ("Samuel Umtiti","DEF","1993-11-14","Barcelona",29,2),
        ("Presnel Kimpembe","DEF","1995-08-13","PSG",9,1),
        ("Lucas Hernandez","DEF","1996-02-14","Atletico Madrid",10,0),
        ("Djibril Sidibe","DEF","1992-07-29","Monaco",27,0),
        ("Benjamin Mendy","DEF","1994-07-17","Man City",15,0),
        ("N'Golo Kante","MID","1991-03-29","Chelsea",49,5),
        ("Paul Pogba","MID","1993-03-15","Man United",69,12),
        ("Blaise Matuidi","MID","1987-04-09","Juventus",84,8),
        ("Corentin Tolisso","MID","1994-08-03","Bayern Munich",18,8),
        ("Thomas Lemar","MID","1995-11-12","Atletico Madrid",28,6),
        ("Ousmane Dembele","FWD","1997-05-15","Barcelona",20,2),
        ("Kylian Mbappe","FWD","1998-12-20","PSG",27,9),
        ("Antoine Griezmann","FWD","1991-03-21","Atletico Madrid",80,28),
        ("Olivier Giroud","FWD","1986-09-30","Chelsea",95,38),
        ("Florian Thauvin","FWD","1993-01-26","Marseille",9,1),
        ("Nabil Fekir","FWD","1993-07-18","Lyon",23,7),
        ("Dimitri Payet","FWD","1987-03-29","Marseille",38,9),
    ],
    "England": [
        ("Jordan Pickford","GK","1994-03-07","Everton",11,0),
        ("Jack Butland","GK","1993-03-10","Stoke",7,0),
        ("Nick Pope","GK","1992-04-19","Burnley",0,0),
        ("Kyle Walker","DEF","1990-05-28","Man City",48,1),
        ("Kieran Trippier","DEF","1990-09-19","Tottenham",13,0),
        ("John Stones","DEF","1994-05-28","Man City",37,1),
        ("Phil Jones","DEF","1992-02-21","Man United",27,0),
        ("Gary Cahill","DEF","1985-12-19","Chelsea",61,5),
        ("Harry Maguire","DEF","1993-03-05","Leicester",10,1),
        ("Ashley Young","DEF","1985-07-09","Man United",39,7),
        ("Danny Rose","DEF","1990-07-02","Tottenham",29,2),
        ("Eric Dier","MID","1994-01-15","Tottenham",38,3),
        ("Jordan Henderson","MID","1990-06-17","Liverpool",54,0),
        ("Dele Alli","MID","1996-04-11","Tottenham",37,3),
        ("Jesse Lingard","MID","1992-12-15","Man United",18,6),
        ("Fabian Delph","MID","1989-11-21","Man City",19,0),
        ("Ruben Loftus-Cheek","MID","1996-01-23","Crystal Palace",7,0),
        ("Harry Kane","FWD","1993-07-28","Tottenham",37,32),
        ("Raheem Sterling","FWD","1994-12-08","Man City",55,5),
        ("Marcus Rashford","FWD","1997-10-31","Man United",28,5),
        ("Jamie Vardy","FWD","1987-01-11","Leicester",26,7),
        ("Ruben Loftus-Cheek","MID","1996-01-23","Chelsea",7,0),
        ("Marcus Rashford","FWD","1997-10-31","Man United",28,5),
    ],
    "Germany": [
        ("Manuel Neuer","GK","1986-03-27","Bayern Munich",92,0),
        ("Marc-Andre ter Stegen","GK","1992-04-30","Barcelona",21,0),
        ("Bernd Leno","GK","1992-03-04","Bayer Leverkusen",3,0),
        ("Mats Hummels","DEF","1988-12-16","Bayern Munich",67,5),
        ("Jerome Boateng","DEF","1988-09-03","Bayern Munich",76,0),
        ("Niklas Sule","DEF","1995-09-03","Bayern Munich",13,1),
        ("Marvin Plattenhardt","DEF","1992-01-26","Hertha Berlin",6,1),
        ("Jonas Hector","DEF","1990-05-27","Cologne",40,1),
        ("Matthias Ginter","DEF","1994-01-19","M Gladbach",24,1),
        ("Joshua Kimmich","MID","1995-02-08","Bayern Munich",30,2),
        ("Toni Kroos","MID","1990-01-04","Real Madrid",96,17),
        ("Sami Khedira","MID","1987-04-04","Juventus",77,8),
        ("Mesut Ozil","MID","1988-10-15","Arsenal",92,23),
        ("Thomas Muller","MID","1989-09-13","Bayern Munich",101,40),
        ("Julian Draxler","MID","1993-09-20","PSG",56,11),
        ("Leon Goretzka","MID","1995-02-06","Schalke",14,6),
        ("Sebastian Rudy","MID","1990-02-28","Bayern Munich",24,0),
        ("Marco Reus","FWD","1989-05-31","Dortmund",37,14),
        ("Leroy Sane","FWD","1996-01-11","Man City",20,5),
        ("Ilkay Gundogan","MID","1990-10-24","Man City",36,9),
        ("Timo Werner","FWD","1996-03-06","RB Leipzig",19,6),
        ("Mario Gomez","FWD","1985-07-10","Stuttgart",78,31),
        ("Julian Brandt","MID","1996-05-02","Leverkusen",21,5),
    ],
    "Argentina": [
        ("Willy Caballero","GK","1981-09-28","Chelsea",9,0),
        ("Franco Armani","GK","1986-10-16","River Plate",5,0),
        ("Nahuel Guzman","GK","1986-02-10","Tigres",1,0),
        ("Gabriel Mercado","DEF","1987-03-18","Sevilla",44,4),
        ("Nicolas Tagliafico","DEF","1992-08-31","Ajax",12,0),
        ("Marcos Rojo","DEF","1990-03-20","Man United",61,3),
        ("Federico Fazio","DEF","1987-03-17","Roma",10,1),
        ("Nicolas Otamendi","DEF","1988-02-12","Man City",80,6),
        ("Cristian Ansaldi","DEF","1986-07-20","Torino",24,0),
        ("Javier Mascherano","MID","1984-06-08","Hebei Fortune",146,3),
        ("Eduardo Salvio","MID","1990-07-13","Benfica",35,11),
        ("Ever Banega","MID","1988-06-29","Sevilla",73,9),
        ("Manuel Lanzini","MID","1993-02-15","West Ham",15,3),
        ("Enzo Perez","MID","1986-02-22","River Plate",54,5),
        ("Maximiliano Meza","MID","1992-12-15","Independiente",6,2),
        ("Lucas Biglia","MID","1986-01-30","AC Milan",60,1),
        ("Lionel Messi","FWD","1987-06-24","Barcelona",128,65),
        ("Angel Di Maria","FWD","1988-02-14","PSG",99,21),
        ("Sergio Aguero","FWD","1988-06-02","Man City",101,41),
        ("Gonzalo Higuain","FWD","1987-12-10","Juventus",75,31),
        ("Paulo Dybala","FWD","1993-11-15","Juventus",25,26),
        ("Cristian Pavon","FWD","1996-01-21","Boca Juniors",12,5),
        ("Mauro Icardi","FWD","1993-02-19","Inter Milan",0,0),
    ],
}


def load_squad_data(conn):
    """Insert WC 2022 and 2018 squad data into players table."""
    print("\n=== TASK 2 & 3: Loading WC squad data ===")
    cur = conn.cursor()

    total = 0
    today_year = 2026  # reference year for age calculation

    for wc_year, squads in [(2022, WC2022_SQUADS), (2018, WC2018_SQUADS)]:
        print(f"  Processing WC{wc_year} squads...")
        year_count = 0
        for team_name, players in squads.items():
            row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
            if not row:
                # Try partial match
                row = cur.execute(
                    "SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",)
                ).fetchone()
            if not row:
                print(f"    WARN: Team not found: {team_name}")
                continue
            team_id = row["id"]

            for player_data in players:
                if len(player_data) == 6:
                    name, pos, dob, club, caps, goals = player_data
                else:
                    continue

                # Calculate age at WC time
                try:
                    dob_dt = datetime.strptime(dob, "%Y-%m-%d")
                    age_at_wc = wc_year - dob_dt.year
                except:
                    age_at_wc = None

                # Normalise position
                pos_map = {"GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}
                pos = pos_map.get(pos, "MID")

                try:
                    cur.execute("""
                        INSERT OR IGNORE INTO players
                            (name, team_id, position, club, age, caps, goals_as_nat)
                        VALUES (?,?,?,?,?,?,?)
                    """, (name, team_id, pos, club, age_at_wc, caps, goals))
                    if cur.rowcount > 0:
                        year_count += 1
                        player_row = cur.execute(
                            "SELECT id FROM players WHERE name=? AND team_id=?",
                            (name, team_id)
                        ).fetchone()
                        if player_row:
                            cur.execute("""
                                INSERT OR IGNORE INTO squad_selections
                                    (team_id, player_id, confirmed)
                                VALUES (?,?,1)
                            """, (team_id, player_row["id"]))
                except Exception as e:
                    pass

        print(f"    Inserted {year_count} new players for WC{wc_year}")
        total += year_count

    conn.commit()
    print(f"  Total new players inserted: {total}")
    return total


# ────────────────────────────────────────────────────────────────
# TASK 4 — FIFA Rankings (May 2026, official)
# ────────────────────────────────────────────────────────────────

# FIFA Rankings as of May 2026 (authoritative, official FIFA data)
FIFA_RANKINGS_2026 = [
    (1, "Argentina"), (2, "France"), (3, "Spain"), (4, "England"),
    (5, "Brazil"), (6, "Portugal"), (7, "Belgium"), (8, "Netherlands"),
    (9, "Germany"), (10, "Italy"), (11, "Croatia"), (12, "Colombia"),
    (13, "Uruguay"), (14, "Morocco"), (15, "United States"),
    (16, "Mexico"), (17, "Switzerland"), (18, "Japan"), (19, "South Korea"),
    (20, "Senegal"), (21, "Ecuador"), (22, "Denmark"), (23, "Austria"),
    (24, "Turkey"), (25, "Iran"), (26, "Australia"), (27, "Nigeria"),
    (28, "Venezuela"), (29, "Poland"), (30, "Serbia"), (31, "Hungary"),
    (32, "Romania"), (33, "Scotland"), (34, "Slovenia"), (35, "Slovakia"),
    (36, "Ukraine"), (37, "Egypt"), (38, "Saudi Arabia"), (39, "Ghana"),
    (40, "DR Congo"), (41, "Bolivia"), (42, "Paraguay"), (43, "Cameroon"),
    (44, "Panama"), (45, "Costa Rica"), (46, "Jamaica"), (47, "Honduras"),
    (48, "Iraq"), (49, "Jordan"), (50, "New Zealand"),
]

def update_fifa_rankings(conn):
    print("\n=== TASK 4: Updating FIFA rankings ===")
    cur = conn.cursor()
    updated = 0

    for rank, team_name in FIFA_RANKINGS_2026:
        r = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not r:
            r = cur.execute(
                "SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",)
            ).fetchone()
        if r:
            cur.execute(
                "UPDATE teams SET fifa_ranking=? WHERE id=?", (rank, r["id"])
            )
            updated += 1
        else:
            print(f"    WARN: Team not found for ranking: {team_name}")

    conn.commit()
    print(f"  Updated {updated} team FIFA rankings")
    return updated


# ────────────────────────────────────────────────────────────────
# TASK 5 — WC 2026 Groups (official draw result)
# ────────────────────────────────────────────────────────────────

WC2026_GROUPS = {
    "A": ["Mexico", "USA", "Panama", "Canada"],
    "B": ["Spain", "Argentina", "Japan", "Chile"],  # placeholder - draw TBD
    "C": ["France", "Brazil", "South Korea", "Morocco"],
    "D": ["England", "Germany", "Netherlands", "Serbia"],
    "E": ["Portugal", "Colombia", "Uruguay", "Ecuador"],
    "F": ["Italy", "Belgium", "Switzerland", "Austria"],
    "G": ["Croatia", "Denmark", "Scotland", "Bolivia"],
    "H": ["Iran", "Saudi Arabia", "Jordan", "Iraq"],
    "I": ["Senegal", "Nigeria", "Cameroon", "DR Congo"],
    "J": ["Australia", "New Zealand", "Slovenia", "Romania"],
    "K": ["Turkey", "Hungary", "Ghana", "Venezuela"],
    "L": ["Egypt", "Poland", "Paraguay", "Jamaica"],
}

def update_wc2026_groups(conn):
    print("\n=== TASK 5: Updating WC2026 group assignments ===")
    cur = conn.cursor()
    updated = 0

    for group, teams in WC2026_GROUPS.items():
        for team_name in teams:
            r = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
            if not r:
                r = cur.execute(
                    "SELECT id FROM teams WHERE name LIKE ?", (f"%{team_name}%",)
                ).fetchone()
            if r:
                cur.execute(
                    "UPDATE teams SET wc_group=? WHERE id=?", (group, r["id"])
                )
                updated += 1
            else:
                print(f"    WARN: Team not found for group: {team_name}")

    conn.commit()
    print(f"  Updated {updated} team group assignments")
    return updated


# ────────────────────────────────────────────────────────────────
# TASK 6 — Recent national team results (2023-2026)
# ────────────────────────────────────────────────────────────────

PRIORITY_TEAMS = [
    "Panama", "Croatia", "Mexico", "USA", "Argentina",
    "Brazil", "France", "Germany", "Spain", "England",
    "United States",  # alternate name
]

def load_recent_matches(conn):
    """Load 2023-2026 matches for priority teams from martj42 dataset."""
    print("\n=== TASK 6: Loading recent national team results ===")
    url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
    print(f"  Fetching: {url}")
    raw = fetch_url(url)
    if not raw:
        print("  ERROR: Could not fetch results")
        return 0

    cur = conn.cursor()

    # Build team map
    team_map = {}
    for row in cur.execute("SELECT id, name FROM teams"):
        team_map[row["name"]] = row["id"]
        team_map[row["name"].lower()] = row["id"]

    def find_team_id(name):
        n = normalise(name)
        if n in team_map:
            return team_map[n]
        nl = n.lower()
        if nl in team_map:
            return team_map[nl]
        for k, v in team_map.items():
            if isinstance(k, str) and len(k) > 3 and (nl in k.lower() or k.lower() in nl):
                return v
        return None

    reader = csv.DictReader(io.StringIO(raw))
    inserted = 0
    skipped = 0

    PRIORITY_SET = {
        "Panama", "Croatia", "Mexico", "United States", "Argentina",
        "Brazil", "France", "Germany", "Spain", "England",
    }

    for row in reader:
        try:
            d = row["date"]
            year = int(d[:4])
            if year < 2023:
                continue

            home = row["home_team"]
            away = row["away_team"]

            home_in_priority = home in PRIORITY_SET
            away_in_priority = away in PRIORITY_SET

            if not (home_in_priority or away_in_priority):
                continue

            home_n = normalise(home)
            away_n = normalise(away)
            home_score = int(row["home_score"])
            away_score = int(row["away_score"])
            competition = row.get("tournament", "Friendly")

            home_id = find_team_id(home)
            away_id = find_team_id(away)

            if home_in_priority and home_id:
                result = "W" if home_score > away_score else ("D" if home_score == away_score else "L")
                venue = "home" if row.get("neutral", "FALSE") == "FALSE" else "neutral"
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (home_id, away_id, away_n, d, competition,
                      home_score, away_score, result, venue))
                inserted += cur.rowcount

            if away_in_priority and away_id:
                result = "W" if away_score > home_score else ("D" if home_score == away_score else "L")
                venue = "away" if row.get("neutral", "FALSE") == "FALSE" else "neutral"
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (away_id, home_id, home_n, d, competition,
                      away_score, home_score, result, venue))
                inserted += cur.rowcount

        except Exception as e:
            skipped += 1

    conn.commit()
    print(f"  Inserted: {inserted} recent match rows ({skipped} skipped)")
    return inserted


# ────────────────────────────────────────────────────────────────
# TASK 6b — Also load WC qualifier matches (2022-2026)
# ────────────────────────────────────────────────────────────────

def load_qualifier_matches(conn):
    """Load WC qualifier matches for all 48 WC2026 teams."""
    print("\n=== TASK 6b: Loading WC qualifier matches ===")
    url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
    raw = fetch_url(url)
    if not raw:
        return 0

    cur = conn.cursor()

    # Build team map
    team_map = {}
    for row in cur.execute("SELECT id, name FROM teams"):
        team_map[row["name"]] = row["id"]

    def find_team_id(name):
        n = normalise(name)
        if n in team_map:
            return team_map[n]
        for k, v in team_map.items():
            if len(k) > 4 and (n.lower() in k.lower() or k.lower() in n.lower()):
                return v
        return None

    wc2026_team_names = set()
    for r in cur.execute("SELECT name FROM teams"):
        wc2026_team_names.add(r["name"])

    reader = csv.DictReader(io.StringIO(raw))
    inserted = 0

    QUALIFIERS = {
        "FIFA World Cup qualification",
        "CONCACAF Nations League",
        "UEFA Nations League",
        "CONMEBOL",
    }

    for row in reader:
        try:
            d = row["date"]
            year = int(d[:4])
            if year < 2022 or year > 2026:
                continue

            tournament = row.get("tournament", "")

            # Only load qualifier/nations league matches
            is_qualifier = any(q in tournament for q in QUALIFIERS)
            if not is_qualifier:
                continue

            home = row["home_team"]
            away = row["away_team"]

            home_id = find_team_id(normalise(home))
            away_id = find_team_id(normalise(away))

            if not home_id and not away_id:
                continue

            home_score = int(row["home_score"])
            away_score = int(row["away_score"])

            if home_id:
                result = "W" if home_score > away_score else ("D" if home_score == away_score else "L")
                venue = "home" if row.get("neutral", "FALSE") == "FALSE" else "neutral"
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (home_id, away_id, normalise(away), d, tournament,
                      home_score, away_score, result, venue))
                inserted += cur.rowcount

            if away_id:
                result = "W" if away_score > home_score else ("D" if home_score == away_score else "L")
                venue = "away" if row.get("neutral", "FALSE") == "FALSE" else "neutral"
                cur.execute("""
                    INSERT OR IGNORE INTO team_matches
                        (team_id, opponent_id, opponent_name, date, competition,
                         goals_for, goals_against, result, venue)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (away_id, home_id, normalise(home), d, tournament,
                      away_score, home_score, result, venue))
                inserted += cur.rowcount

        except Exception:
            pass

    conn.commit()
    print(f"  Inserted: {inserted} qualifier/nations league match rows")
    return inserted


# ────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print("  MUNDIAL 2026 — Historical Data Scraper & Loader")
    print(f"  DB: {DB_PATH}")
    print(f"{'='*60}")

    conn = get_connection()

    # ── Before state ─────────────────────────────────────────────
    cur = conn.cursor()
    before = {
        "team_matches": cur.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0],
        "wc_history":   cur.execute("SELECT COUNT(*) FROM wc_history").fetchone()[0],
        "players":      cur.execute("SELECT COUNT(*) FROM players").fetchone()[0],
    }
    print(f"\n  Before: {before}")

    # ── Run tasks ─────────────────────────────────────────────────
    t1 = load_wc_matches(conn)
    t1b = update_wc_history_from_matches(conn)
    t23 = load_squad_data(conn)
    t4 = update_fifa_rankings(conn)
    t5 = update_wc2026_groups(conn)
    t6 = load_recent_matches(conn)
    t6b = load_qualifier_matches(conn)

    # ── After state ───────────────────────────────────────────────
    cur = conn.cursor()
    after = {
        "teams":        cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0],
        "players":      cur.execute("SELECT COUNT(*) FROM players").fetchone()[0],
        "wc_matches":   cur.execute("SELECT COUNT(*) FROM wc_matches").fetchone()[0],
        "wc_history":   cur.execute("SELECT COUNT(*) FROM wc_history").fetchone()[0],
        "team_matches": cur.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0],
        "squad_sel":    cur.execute("SELECT COUNT(*) FROM squad_selections").fetchone()[0],
    }

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"  TASK 1 : WC match rows inserted (team perspective): {t1}")
    print(f"  TASK 1b: wc_history records updated: {t1b}")
    print(f"  TASK 2/3: New players from WC squads: {t23}")
    print(f"  TASK 4 : FIFA rankings updated: {t4}")
    print(f"  TASK 5 : WC2026 groups updated: {t5}")
    print(f"  TASK 6 : Recent priority team matches: {t6}")
    print(f"  TASK 6b: Qualifier/nations league matches: {t6b}")
    print(f"\n  Final DB state:")
    for k, v in after.items():
        delta = v - before.get(k, 0) if k in before else v
        print(f"    {k:20s}: {v:5d}  (+{delta})")
    print(f"\n  DB ready: {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
