"""
seed_new_teams.py — Seeds squads for the 14 new WC2026 teams.
Run once after fix_teams_wc2026.py to populate players for the new qualified teams.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# (name, position, club, league, age, caps, goals)
SQUADS = {
    "South Africa": [
        ("Ronwen Williams",     "GK",  "Mamelodi Sundowns",   "PSL",            32, 72, 0),
        ("Siyanda Xulu",        "DEF", "Mamelodi Sundowns",   "PSL",            32, 45, 1),
        ("Rushine De Reuck",    "DEF", "Mamelodi Sundowns",   "PSL",            28, 35, 2),
        ("Nyiko Mobbie",        "DEF", "Mamelodi Sundowns",   "PSL",            26, 28, 0),
        ("Thibang Phete",       "DEF", "Sekhukhune United",   "PSL",            25, 22, 0),
        ("Teboho Mokoena",      "MID", "Mamelodi Sundowns",   "PSL",            27, 55, 8),
        ("Themba Zwane",        "MID", "Mamelodi Sundowns",   "PSL",            33, 68, 12),
        ("Yusuf Maart",         "MID", "Kaizer Chiefs",       "PSL",            28, 32, 5),
        ("Bongani Zungu",       "MID", "Mamelodi Sundowns",   "PSL",            32, 45, 4),
        ("Percy Tau",           "FWD", "Al Ahly",             "Egyptian Premier League", 30, 62, 18),
        ("Evidence Makgopa",    "FWD", "Bayer Leverkusen",    "Bundesliga",     24, 28, 12),
        ("Lyle Foster",         "FWD", "Burnley",             "Premier League", 24, 22, 8),
    ],
    "Czechia": [
        ("Jindrich Stanek",     "GK",  "Fiorentina",          "Serie A",        28, 32, 0),
        ("Ladislav Krejci",     "DEF", "Bologna",             "Serie A",        25, 28, 1),
        ("Tomas Holes",         "DEF", "Slavia Prague",       "Czech First League", 31, 42, 3),
        ("Vladimir Coufal",     "DEF", "West Ham",            "Premier League", 32, 45, 2),
        ("David Jurasek",       "DEF", "Benfica",             "Primeira Liga",  24, 22, 1),
        ("Tomas Soucek",        "MID", "West Ham",            "Premier League", 29, 68, 18),
        ("Lukas Provod",        "MID", "Slavia Prague",       "Czech First League", 27, 32, 5),
        ("Ondrej Lingr",        "MID", "Fiorentina",          "Serie A",        26, 25, 4),
        ("Patrik Schick",       "FWD", "Bayer Leverkusen",    "Bundesliga",     29, 55, 25),
        ("Adam Hlozek",         "FWD", "Bayer Leverkusen",    "Bundesliga",     23, 32, 10),
        ("Jakub Pesek",         "FWD", "Slavia Prague",       "Czech First League", 26, 20, 6),
    ],
    "Bosnia and Herzegovina": [
        ("Kenan Piric",         "GK",  "AIK",                 "Allsvenskan",    29, 28, 0),
        ("Sead Kolasinac",      "DEF", "Atalanta",            "Serie A",        31, 62, 3),
        ("Ermedin Demirovic",   "DEF", "Stuttgarter Kickers", "Bundesliga",     26, 30, 1),
        ("Anel Ahmedhodzic",    "DEF", "Sheffield United",    "Championship",   26, 38, 5),
        ("Dario Simic",         "DEF", "Dinamo Zagreb",       "HNL",            22, 18, 0),
        ("Miralem Pjanic",      "MID", "Sharjah FC",          "UAE Pro League", 34, 105, 18),
        ("Sasa Lukic",          "MID", "Fulham",              "Premier League", 28, 42, 8),
        ("Amer Gojak",          "MID", "Dynamo Kyiv",         "Ukrainian Premier League", 28, 32, 5),
        ("Edin Dzeko",          "FWD", "Fenerbahce",          "Turkish Süper Lig", 39, 120, 65),
        ("Haris Hajradinovic",  "FWD", "Konyaspor",           "Turkish Süper Lig", 26, 20, 7),
        ("Amar Rahimic",        "FWD", "Fenerbahce",          "Turkish Süper Lig", 24, 15, 4),
    ],
    "Qatar": [
        ("Meshaal Barsham",     "GK",  "Al-Sadd",             "Qatar Stars League", 26, 35, 0),
        ("Pedro Miguel",        "DEF", "Al-Gharafa",          "Qatar Stars League", 31, 42, 2),
        ("Tarek Salman",        "DEF", "Al-Duhail",           "Qatar Stars League", 27, 30, 1),
        ("Bassam Al-Rawi",      "DEF", "Al-Wakrah",           "Qatar Stars League", 28, 25, 0),
        ("Hassan Al-Haydos",    "MID", "Al-Sadd",             "Qatar Stars League", 33, 82, 22),
        ("Abdulaziz Hatem",     "MID", "Al-Rayyan",           "Qatar Stars League", 32, 55, 8),
        ("Assim Madibo",        "MID", "D.C. United",         "MLS",            26, 28, 3),
        ("Karim Boudiaf",       "MID", "Al-Sadd",             "Qatar Stars League", 33, 65, 8),
        ("Akram Afif",          "FWD", "Al-Sadd",             "Qatar Stars League", 27, 55, 22),
        ("Almoez Ali",          "FWD", "Al-Duhail",           "Qatar Stars League", 28, 58, 28),
        ("Mohammed Muntari",    "FWD", "Al-Duhail",           "Qatar Stars League", 30, 42, 12),
    ],
    "Haiti": [
        ("Johny Placide",       "GK",  "Grenoble",            "Ligue 2",        37, 42, 0),
        ("Andrew Djiku",        "DEF", "Strasbourg",          "Ligue 1",        30, 38, 2),
        ("Florent Viltard",     "DEF", "Grenoble",            "Ligue 2",        29, 22, 0),
        ("Quentin Thurotte",    "DEF", "Laval",               "Ligue 2",        28, 18, 0),
        ("Damien Perinelle",    "DEF", "Paris FC",            "Ligue 2",        35, 30, 1),
        ("Frantzdy Pierrot",    "MID", "FC Emmen",            "Eredivisie",     28, 35, 4),
        ("Stephane Suk",        "MID", "Seoul E-Land",        "K League 2",     25, 20, 2),
        ("James Lea Siliki",    "MID", "Stade Rennais",       "Ligue 1",        28, 32, 5),
        ("Duckens Nazon",       "FWD", "Valenciennes",        "Ligue 2",        31, 40, 12),
        ("Gauthier Obiora",     "FWD", "Angers",              "Ligue 1",        23, 18, 5),
        ("Mechack Jerome",      "FWD", "Vasas FC",            "OTP Bank Liga",  28, 38, 8),
    ],
    "Curacao": [
        ("Eloy Room",           "GK",  "CF Montréal",         "MLS",            33, 38, 0),
        ("Ethan Gorré",         "DEF", "Vitesse",             "Eredivisie",     31, 25, 1),
        ("Brendan Hines-Ike",   "DEF", "Girondins Bordeaux",  "Ligue 2",        29, 22, 2),
        ("Leandro Bacuna",      "DEF", "Cardiff City",        "Championship",   33, 42, 4),
        ("Cuco Martina",        "DEF", "Reims",               "Ligue 1",        34, 55, 2),
        ("Rurickson Libregts",  "MID", "NAC Breda",           "Eredivisie",     27, 18, 2),
        ("Gilmar Sturm",        "MID", "FC Emmen",            "Eredivisie",     28, 22, 4),
        ("Jurien Smit",         "MID", "Almere City",         "Eredivisie",     26, 15, 3),
        ("Ke-Ron Cornet",       "FWD", "Twente",              "Eredivisie",     28, 30, 8),
        ("Rangelo Janga",       "FWD", "Go Ahead Eagles",     "Eredivisie",     30, 25, 10),
        ("Nigel Thomas",        "FWD", "Emmen",               "Eredivisie",     23, 12, 5),
    ],
    "Ivory Coast": [
        ("Yahia Fofana",        "GK",  "AS Monaco",           "Ligue 1",        28, 22, 0),
        ("Odilon Kossounou",    "DEF", "Bayer Leverkusen",    "Bundesliga",     24, 30, 1),
        ("Jean-Louis Gbamin",   "DEF", "Trabzonspor",         "Turkish Süper Lig", 29, 22, 0),
        ("Eric Bailly",         "DEF", "Nottm Forest",        "Premier League", 30, 45, 2),
        ("Willy Boly",          "DEF", "Nottm Forest",        "Premier League", 33, 38, 3),
        ("Franck Kessie",       "MID", "Al-Ahli",             "Saudi Pro League", 28, 68, 18),
        ("Seko Fofana",         "MID", "Al-Nassr",            "Saudi Pro League", 29, 42, 8),
        ("Ibrahim Sangare",     "MID", "Nottm Forest",        "Premier League", 27, 28, 4),
        ("Simon Adingra",       "FWD", "Brighton",            "Premier League", 24, 22, 8),
        ("Sebastien Haller",    "FWD", "Borussia Dortmund",   "Bundesliga",     30, 45, 22),
        ("Jonathan Bamba",      "FWD", "Club Brugge",         "Pro League",     28, 32, 10),
    ],
    "Sweden": [
        ("Robin Olsen",         "GK",  "Aston Villa",         "Premier League", 34, 65, 0),
        ("Victor Lindelof",     "DEF", "Man United",          "Premier League", 30, 68, 3),
        ("Isak Hien",           "DEF", "Atalanta",            "Serie A",        25, 22, 1),
        ("Ludwig Augustinsson", "DEF", "Sevilla",             "La Liga",        30, 55, 3),
        ("Carl Starfelt",       "DEF", "Celta Vigo",          "La Liga",        29, 38, 2),
        ("Emil Forsberg",       "MID", "RB Leipzig",          "Bundesliga",     33, 82, 25),
        ("Mattias Svanberg",    "MID", "Wolfsburg",           "Bundesliga",     26, 35, 5),
        ("Dejan Kulusevski",    "MID", "Tottenham",           "Premier League", 25, 48, 12),
        ("Viktor Gyokeres",     "FWD", "Arsenal",             "Premier League", 27, 38, 20),
        ("Alexander Isak",      "FWD", "Newcastle",           "Premier League", 25, 48, 18),
        ("Anthony Elanga",      "FWD", "Nottm Forest",        "Premier League", 23, 22, 5),
    ],
    "Tunisia": [
        ("Aymen Dahmen",        "GK",  "Montpellier",         "Ligue 1",        28, 32, 0),
        ("Montassar Talbi",     "DEF", "Lorient",             "Ligue 1",        26, 28, 1),
        ("Dylan Bronn",         "DEF", "Salernitana",         "Serie A",        28, 35, 2),
        ("Nader Ghandri",       "DEF", "Genoa",               "Serie A",        28, 30, 1),
        ("Mohamed Drager",      "DEF", "Galatasaray",         "Turkish Süper Lig", 28, 32, 2),
        ("Hannibal Mejbri",     "MID", "Burnley",             "Premier League", 22, 22, 3),
        ("Ellyes Skhiri",       "MID", "Frankfurt",           "Bundesliga",     29, 55, 8),
        ("Anis Ben Slimane",    "MID", "Brondby",             "Superliga",      23, 18, 4),
        ("Wahbi Khazri",        "FWD", "Samsunspor",          "Turkish Süper Lig", 34, 65, 25),
        ("Naim Sliti",          "FWD", "Valenciennes",        "Ligue 2",        30, 45, 12),
        ("Seifeddine Jaziri",   "FWD", "Kasimpasa",           "Turkish Süper Lig", 27, 35, 10),
    ],
    "Cape Verde": [
        ("Vozinha",             "GK",  "Spartak Moscow",      "Russian Premier League", 30, 38, 0),
        ("Stopira",             "DEF", "Getafe",              "La Liga",        35, 55, 2),
        ("Roberto Lopes",       "DEF", "Shamrock Rovers",     "League of Ireland", 30, 32, 3),
        ("Kenny Rocha",         "DEF", "Sion",                "Swiss Super League", 31, 28, 1),
        ("Garry Rodrigues",     "MID", "Fenerbahce",          "Turkish Süper Lig", 33, 48, 10),
        ("Nando",               "MID", "Maccabi Haifa",       "Israeli Premier League", 28, 25, 4),
        ("Josimar Dias",        "MID", "Pacos de Ferreira",   "Primeira Liga",  25, 18, 3),
        ("Ryan Mendes",         "FWD", "Sivasspor",           "Turkish Süper Lig", 33, 52, 12),
        ("Djaniny",             "FWD", "Al-Ahli Jeddah",     "Saudi Pro League", 32, 45, 18),
        ("Joaozinho",           "FWD", "APOEL",               "Cypriot First Division", 29, 35, 10),
        ("Steven Fortes",       "FWD", "Midtjylland",         "Superliga",      30, 28, 6),
    ],
    "Norway": [
        ("Orjan Nyland",        "GK",  "Internazionale",      "Serie A",        34, 42, 0),
        ("Leo Ostigard",        "DEF", "SSC Napoli",          "Serie A",        25, 28, 2),
        ("Stian Gregersen",     "DEF", "Brest",               "Ligue 1",        28, 22, 1),
        ("Andreas Hanche-Olsen","DEF", "Gent",                "Pro League",     26, 18, 1),
        ("Birger Meling",       "DEF", "Rennes",              "Ligue 1",        30, 32, 2),
        ("Martin Odegaard",     "MID", "Arsenal",             "Premier League", 26, 75, 25),
        ("Sander Berge",        "MID", "Fulham",              "Premier League", 27, 48, 8),
        ("Kristian Thorstvedt", "MID", "Sassuolo",            "Serie A",        25, 22, 4),
        ("Erling Haaland",      "FWD", "Man City",            "Premier League", 25, 38, 30),
        ("Alexander Sorloth",   "FWD", "Atletico Madrid",     "La Liga",        29, 55, 22),
        ("Mohamed Elyounoussi", "FWD", "Southampton",         "Championship",   30, 62, 18),
    ],
    "Algeria": [
        ("Rais M'Bolhi",        "GK",  "LAFC",                "MLS",            38, 88, 0),
        ("Ramy Bensebaini",     "DEF", "Borussia Dortmund",   "Bundesliga",     29, 42, 8),
        ("Aissa Mandi",         "DEF", "Villarreal",          "La Liga",        33, 55, 3),
        ("Djamel Benlamri",     "DEF", "Lorient",             "Ligue 1",        34, 42, 2),
        ("Mehdi Zeffane",       "DEF", "Rennes",              "Ligue 1",        32, 32, 1),
        ("Sofiane Feghouli",    "MID", "Al-Ittihad",          "Saudi Pro League", 35, 82, 18),
        ("Hichem Boudaoui",     "MID", "OGC Nice",            "Ligue 1",        27, 32, 5),
        ("Ramiz Zerrouki",      "MID", "Twente",              "Eredivisie",     26, 25, 4),
        ("Youcef Belaili",      "FWD", "Club Africain",       "Tunisian Ligue 1", 32, 55, 20),
        ("Baghdad Bounedjah",   "FWD", "Al-Sadd",             "Qatar Stars League", 33, 62, 32),
        ("Islam Slimani",       "FWD", "Brest",               "Ligue 1",        36, 98, 42),
    ],
    "Uzbekistan": [
        ("Otajon Ismoilov",     "GK",  "AGMK FK",             "Uzbekistan Super League", 26, 25, 0),
        ("Dostonbek Khamdamov", "DEF", "Pakhtakor",           "Uzbekistan Super League", 24, 22, 0),
        ("Khojiakbar Alijonov", "DEF", "Pakhtakor",           "Uzbekistan Super League", 26, 25, 1),
        ("Islom Tukhtaev",      "DEF", "Lokomotiv Tashkent",  "Uzbekistan Super League", 28, 22, 0),
        ("Husayn Norchaev",     "DEF", "Pakhtakor",           "Uzbekistan Super League", 25, 20, 1),
        ("Abbosbek Fayzullayev","MID", "Crystal Palace",      "Premier League", 23, 32, 5),
        ("Jasur Yakhshiboev",   "MID", "Pakhtakor",           "Uzbekistan Super League", 28, 28, 4),
        ("Otabek Shukurov",     "MID", "Pakhtakor",           "Uzbekistan Super League", 26, 25, 3),
        ("Eldor Shomurodov",    "FWD", "AS Roma",             "Serie A",        29, 48, 22),
        ("Javokhir Sidikov",    "FWD", "Pakhtakor",           "Uzbekistan Super League", 25, 22, 8),
        ("Islombek Kobilov",    "FWD", "FC Neftchi",          "Uzbekistan Super League", 24, 18, 6),
    ],
}


def run():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = 0
    for team_name, squad in SQUADS.items():
        row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            print(f"  SKIP (team not found): {team_name}")
            continue
        team_id = row["id"]

        existing = cur.execute("SELECT COUNT(*) FROM players WHERE team_id=?", (team_id,)).fetchone()[0]
        if existing > 0:
            print(f"  SKIP (already has {existing} players): {team_name}")
            continue

        inserted = 0
        for name, position, club, league, age, caps, goals in squad:
            cur.execute("""
                INSERT OR IGNORE INTO players
                    (name, team_id, position, club, club_league, age, caps, goals_as_nat)
                VALUES (?,?,?,?,?,?,?,?)
            """, (name, team_id, position, club, league, age, caps, goals))
            player_row = cur.execute(
                "SELECT id FROM players WHERE name=? AND team_id=?", (name, team_id)
            ).fetchone()
            if player_row:
                cur.execute("""
                    INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed)
                    VALUES (?,?,1)
                """, (team_id, player_row["id"]))
                inserted += 1
        conn.commit()
        print(f"  {team_name}: {inserted} players seeded")
        total += inserted

    final = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"\nTotal inserted: {total} | DB total players: {final}")
    conn.close()


if __name__ == "__main__":
    run()
