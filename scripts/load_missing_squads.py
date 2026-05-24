"""
Load players for the 14 teams added in fix_teams_wc2026.py that had 0 players.
Data based on known 2025-2026 national team squads.
"""
import sqlite3
from pathlib import Path

DB = str(Path(__file__).parent.parent / "data" / "mundial2026.db")

# Schema: (name, position, club, club_league, age, caps, goals_as_nat, preferred_foot, height_cm, market_value_m)
SQUADS = {

"Norway": [
    ("Ørjan Nyland",           "GK",  "Brann",              "Eliteserien",    34, 26,  0, "R", 190, 1.5),
    ("Kristoffer Klaesson",    "GK",  "Leeds United",       "Championship",   24,  8,  0, "R", 189, 3.0),
    ("Leo Østigård",           "CB",  "Napoli",             "Serie A",        24, 25,  2, "R", 184, 12.0),
    ("Andreas Hanche-Olsen",   "CB",  "Nottm Forest",       "Premier League", 27, 20,  1, "R", 192, 8.0),
    ("Stefan Strandberg",      "CB",  "Gent",               "Pro League",     34, 35,  2, "R", 188, 2.0),
    ("Birger Meling",          "LB",  "Rennes",             "Ligue 1",        30, 30,  2, "L", 176, 5.0),
    ("Omar Elabdellaoui",      "RB",  "Olympiacos",         "Super League",   32, 62,  5, "R", 180, 3.0),
    ("Kristian Thorstvedt",    "MID", "Sassuolo",           "Serie A",        24, 30,  4, "R", 185, 8.0),
    ("Sander Berge",           "MID", "Burnley",            "Premier League", 26, 50,  4, "R", 194, 20.0),
    ("Martin Ødegaard",        "MID", "Arsenal",            "Premier League", 26, 80, 25, "R", 178, 90.0),
    ("Morten Thorsby",         "MID", "Genoa",              "Serie A",        28, 40,  5, "R", 187, 7.0),
    ("Fredrik Aursnes",        "MID", "Benfica",            "Primeira Liga",  28, 38,  2, "L", 180, 18.0),
    ("Patrick Berg",           "MID", "Bodo/Glimt",         "Eliteserien",    26, 30,  3, "R", 185, 6.0),
    ("Antonio Nusa",           "LW",  "RB Leipzig",         "Bundesliga",     20, 20,  5, "L", 176, 35.0),
    ("Jens Petter Hauge",      "LW",  "Gent",               "Pro League",     25, 28,  6, "L", 177, 8.0),
    ("Alexander Sørloth",      "ST",  "Atletico Madrid",    "La Liga",        28, 58, 25, "R", 194, 35.0),
    ("Erling Haaland",         "ST",  "Man City",           "Premier League", 24, 45, 30, "R", 194, 200.0),
    ("Ola Solbakken",          "LW",  "Roma",               "Serie A",        24, 22,  4, "R", 186, 10.0),
    ("Joshua King",            "ST",  "Besiktas",           "Süper Lig",      32, 78, 24, "R", 181, 4.0),
    ("Markus Henriksen",       "MID", "Stroemsgodset",      "Eliteserien",    32, 55,  4, "R", 186, 1.5),
    ("Tobias Svendsen",        "RW",  "Bodo/Glimt",         "Eliteserien",    23, 12,  2, "R", 179, 4.0),
    ("Stian Gregersen",        "CB",  "Club Brugge",        "Pro League",     28, 18,  1, "R", 191, 5.0),
    ("Haakon Evjen",           "MID", "Club Brugge",        "Pro League",     24, 20,  3, "R", 178, 7.0),
    ("Andreas Schjelderup",    "LW",  "Benfica",            "Primeira Liga",  21, 10,  2, "L", 174, 20.0),
    ("Isak Bergvall",          "MID", "Tottenham",          "Premier League", 19,  8,  1, "R", 179, 18.0),
    ("Ulrik Saltnes",          "MID", "Bodo/Glimt",         "Eliteserien",    32, 20,  2, "R", 183, 2.0),
    ("Håvard Nordtveit",       "CB",  "Bodo/Glimt",         "Eliteserien",    35, 70,  3, "R", 189, 1.0),
    ("Simen Juklerød",         "LB",  "FC Nantes",          "Ligue 1",        26, 12,  0, "L", 182, 4.0),
    ("Anders Trondsen",        "MID", "Rosenborg",          "Eliteserien",    30, 15,  1, "R", 184, 2.0),
    ("Elias Solberg",          "GK",  "Bodo/Glimt",         "Eliteserien",    26,  5,  0, "R", 188, 2.0),
    ("Victor Boniface",        "ST",  "Bayer Leverkusen",   "Bundesliga",     24, 15,  5, "R", 189, 40.0),
    ("Mathias Normann",        "MID", "Standard Liège",     "Pro League",     28, 25,  2, "R", 182, 4.0),
],

"Algeria": [
    ("Rais M'Bolhi",           "GK",  "Al-Ettifaq",         "Saudi Pro League", 38, 75,  0, "R", 193, 1.5),
    ("Youssef Atal",           "RB",  "Nice",               "Ligue 1",        28, 52,  7, "R", 172, 20.0),
    ("Aissa Mandi",            "CB",  "Villarreal",         "La Liga",        32, 65,  3, "R", 183, 8.0),
    ("Djamel Benlamri",        "CB",  "Al-Ittihad",         "Saudi Pro League", 34, 55,  2, "R", 192, 2.0),
    ("Ramy Bensebaini",        "LB",  "Borussia Dortmund",  "Bundesliga",     29, 52, 12, "L", 185, 22.0),
    ("Ismael Bennacer",        "MID", "AC Milan",           "Serie A",        27, 58,  3, "R", 175, 40.0),
    ("Sofiane Feghouli",       "MID", "Al-Shabab",          "Saudi Pro League", 35, 82, 15, "R", 179, 2.0),
    ("Houssem Aouar",          "CAM", "Besiktas",           "Süper Lig",      26, 32,  5, "R", 176, 12.0),
    ("Riyad Mahrez",           "RW",  "Al-Ahli",            "Saudi Pro League", 33, 88, 36, "R", 177, 25.0),
    ("Said Benrahma",          "LW",  "Lyon",               "Ligue 1",        29, 60, 14, "L", 174, 18.0),
    ("Adam Ounas",             "LW",  "Nice",               "Ligue 1",        28, 40,  8, "L", 172, 10.0),
    ("Baghdad Bounedjah",      "ST",  "Al-Sadd",            "Qatar Stars",    32, 55, 30, "R", 181, 3.0),
    ("Islam Slimani",          "ST",  "Brest",              "Ligue 1",        36, 90, 40, "R", 186, 2.0),
    ("Yacine Brahimi",         "CAM", "Al-Qadsiah",         "Saudi Pro League", 34, 65, 19, "R", 173, 2.0),
    ("Zakaria Aboukhlal",      "LW",  "Toulouse",           "Ligue 1",        23, 28,  6, "L", 174, 14.0),
    ("Bilal Benkhedim",        "MID", "Oran",               "Ligue Professionnelle", 24, 10, 1, "R", 178, 1.5),
    ("Mohamed Amine Amoura",   "LW",  "Union SG",           "Pro League",     23, 20,  5, "L", 179, 18.0),
    ("Djamel Saadi",           "MID", "Beerschot",          "Pro League",     25, 15,  2, "R", 181, 3.0),
    ("Hicham Boudaoui",        "MID", "Nice",               "Ligue 1",        25, 25,  2, "R", 184, 8.0),
    ("Farid Boulaya",          "CAM", "Lorient",            "Ligue 1",        31, 42,  6, "L", 174, 5.0),
    ("Samy Mmaee",             "CB",  "Club Brugge",        "Pro League",     28, 20,  2, "R", 190, 6.0),
    ("Mehdi Zerkane",          "MID", "Sharjah",            "Arabian Gulf",   26, 20,  3, "R", 182, 4.0),
    ("Alexandre Oukidja",      "GK",  "Metz",               "Ligue 2",        35, 22,  0, "R", 185, 1.5),
    ("Samir Nasri",            "MID", "Retired",            None,             37, 45, 10, "R", 178, 0.5),
    ("Aimen Mahious",          "CB",  "Valenciennes",       "Ligue 2",        26, 12,  0, "R", 187, 2.0),
    ("Adrien Tameze",          "MID", "Torino",             "Serie A",        29, 28,  1, "R", 183, 6.0),
    ("Ramiz Zerrouki",         "MID", "Twente",             "Eredivisie",     26, 20,  2, "R", 182, 8.0),
    ("Anis Hadj Moussa",       "LW",  "Mainz",              "Bundesliga",     22, 10,  2, "L", 175, 6.0),
    ("Oussama Idrissi",        "LW",  "Almeria",            "La Liga",        28, 30,  5, "L", 175, 6.0),
    ("Andy Delort",            "ST",  "Al-Qadsiah",         "Saudi Pro League", 32, 20,  7, "R", 186, 3.0),
    ("Idriss Doumbia",         "ST",  "Sparta Prague",      "Czech First League", 25, 12, 3, "R", 182, 5.0),
    ("Nassim Boujellab",       "MID", "Schalke",            "2. Bundesliga",  25, 15,  1, "R", 180, 3.0),
],

"Sweden": [
    ("Robin Olsen",            "GK",  "Aston Villa",        "Premier League", 34, 50,  0, "R", 197, 4.0),
    ("Karl-Johan Johnsson",    "GK",  "FC Copenhagen",      "Superliga",      32, 18,  0, "R", 187, 2.5),
    ("Victor Lindelöf",        "CB",  "Man United",         "Premier League", 30, 82, 8,  "R", 187, 25.0),
    ("Marcus Danielson",       "CB",  "Djurgarden",         "Allsvenskan",    33, 45,  3, "R", 195, 2.5),
    ("Pontus Jansson",         "CB",  "Brentford",          "Premier League", 33, 52,  6, "R", 192, 10.0),
    ("Carl Starfelt",          "CB",  "Celtic",             "Scottish Premiership", 29, 35, 2, "R", 189, 12.0),
    ("Ludwig Augustinsson",    "LB",  "Sevilla",            "La Liga",        30, 55,  6, "L", 181, 8.0),
    ("Mikael Lustig",          "RB",  "AIK",                "Allsvenskan",    37, 80,  5, "R", 185, 1.0),
    ("Emil Krafth",            "RB",  "Newcastle",          "Premier League", 29, 30,  1, "R", 183, 6.0),
    ("Mattias Svanberg",       "MID", "Wolfsburg",          "Bundesliga",     26, 38,  5, "R", 183, 12.0),
    ("Albin Ekdal",            "MID", "Spezia",             "Serie B",        34, 70,  4, "R", 181, 2.0),
    ("Emil Forsberg",          "MID", "RB Leipzig",         "Bundesliga",     32, 77, 28, "L", 177, 10.0),
    ("Dejan Kulusevski",       "RW",  "Tottenham",          "Premier League", 24, 52, 16, "R", 184, 65.0),
    ("Robin Quaison",          "LW",  "Mainz",              "Bundesliga",     30, 45, 14, "R", 178, 5.0),
    ("Anthony Elanga",         "LW",  "Nottm Forest",       "Premier League", 22, 20,  5, "L", 179, 25.0),
    ("Alexander Isak",         "ST",  "Newcastle",          "Premier League", 25, 55, 22, "L", 190, 90.0),
    ("Jordan Larsson",         "ST",  "Spartak Moscow",     "Russian PL",     27, 22,  5, "R", 183, 5.0),
    ("Jesper Karlsson",        "LW",  "Bologna",            "Serie A",        27, 30,  7, "L", 180, 20.0),
    ("Samuel Chukwueze",       "RW",  None,                 None,             25,  0,  0, "R", 174, 0.0),
    ("Sebastian Larsson",      "MID", "AIK",                "Allsvenskan",    38, 130, 8, "R", 179, 0.5),
    ("Gustav Svensson",        "MID", "Seattle Sounders",   "MLS",            34, 40,  2, "R", 184, 1.5),
    ("Viktor Gyokeres",        "ST",  "Sporting CP",        "Primeira Liga",  26, 35, 20, "R", 188, 75.0),
    ("Samuel Adegbenro",       "RW",  "Bodo/Glimt",         "Eliteserien",    28, 15,  3, "R", 178, 4.0),
    ("Niclas Eliasson",        "LW",  "PAOK",               "Super League",   29, 15,  2, "L", 176, 3.0),
    ("Filip Helander",         "CB",  "Rangers",            "Scottish Premiership", 31, 35, 2, "R", 193, 5.0),
    ("Oscar Lewicki",          "MID", "IFK Gothenburg",     "Allsvenskan",    32, 20,  1, "R", 182, 1.5),
    ("Alexander Milosevic",    "CB",  "Nottm Forest",       "Premier League", 33, 20,  2, "R", 191, 3.0),
    ("Sam Larsson",            "LW",  "Al-Fayha",           "Saudi Pro League", 30, 28, 6, "L", 176, 2.0),
    ("Ísak Jóhannsson",        "ST",  "AZ Alkmaar",         "Eredivisie",     24, 18,  6, "R", 187, 12.0),
    ("Christoffer Nyman",      "ST",  "Norrkoping",         "Allsvenskan",    32, 12,  3, "R", 186, 1.5),
    ("Hugo Larsson",           "MID", "Eintracht Frankfurt","Bundesliga",     20, 12,  2, "R", 181, 18.0),
    ("Kenneth Jonsson",        "CB",  "IFK Gothenburg",     "Allsvenskan",    23, 10,  0, "R", 188, 3.0),
],

"Ivory Coast": [
    ("Yahia Fofana",           "GK",  "Monaco",             "Ligue 1",        29, 40,  0, "R", 190, 8.0),
    ("Badra Ali Sangare",      "GK",  "Yverdon",            "Super League",   33, 20,  0, "R", 186, 1.5),
    ("Serge Aurier",           "RB",  "Nottm Forest",       "Premier League", 32, 78,  8, "R", 179, 6.0),
    ("Eric Bailly",            "CB",  "Villarreal",         "La Liga",        30, 42,  1, "R", 188, 8.0),
    ("Willy Boly",             "CB",  "Nottm Forest",       "Premier League", 32, 28,  2, "R", 194, 5.0),
    ("Odilon Kossounou",       "CB",  "Bayer Leverkusen",   "Bundesliga",     23, 30,  1, "R", 186, 22.0),
    ("Ghislain Konan",         "LB",  "Stade Reims",        "Ligue 1",        28, 32,  2, "L", 181, 5.0),
    ("Ismael Traore",          "CB",  "Strasbourg",         "Ligue 1",        25, 15,  1, "R", 190, 6.0),
    ("Ibrahim Sangare",        "MID", "Nottm Forest",       "Premier League", 26, 50,  4, "R", 192, 35.0),
    ("Seko Fofana",            "MID", "Al-Qadsiah",         "Saudi Pro League", 29, 55, 9, "R", 188, 15.0),
    ("Jean-Philippe Gbamin",   "MID", "Trabzonspor",        "Süper Lig",      29, 32,  3, "R", 185, 5.0),
    ("Franck Kessié",          "MID", "Barcelona",          "La Liga",        27, 68, 14, "R", 183, 20.0),
    ("Max-Alain Gradel",       "RW",  "Kasimpasa",          "Süper Lig",      36, 80, 20, "R", 174, 2.0),
    ("Nicolas Pépé",           "RW",  "Nice",               "Ligue 1",        29, 65, 15, "R", 180, 12.0),
    ("Simon Adingra",          "LW",  "Brighton",           "Premier League", 22, 30, 10, "L", 175, 30.0),
    ("Wilfried Zaha",          "LW",  "Galatasaray",        "Süper Lig",      31, 35, 11, "L", 179, 12.0),
    ("Sébastien Haller",       "ST",  "Borussia Dortmund",  "Bundesliga",     30, 55, 26, "R", 190, 20.0),
    ("Amad Diallo",            "RW",  "Man United",         "Premier League", 22, 18,  5, "R", 171, 35.0),
    ("Jonathan Kodjia",        "ST",  "Hammarby",           "Allsvenskan",    34, 38, 16, "R", 182, 2.0),
    ("Wilfried Bony",          "ST",  "Retired",            None,             36, 65, 22, "R", 181, 0.5),
    ("Cheikh Oumar Traoré",    "MID", "Auxerre",            "Ligue 1",        25, 15,  2, "R", 182, 4.0),
    ("Oumar Gonzalez",         "LB",  "Lorient",            "Ligue 1",        26, 18,  1, "L", 184, 3.0),
    ("Souleymane Doumbia",     "RB",  "Reims",              "Ligue 1",        26, 12,  1, "R", 175, 4.0),
    ("Stephane Singo",         "RB",  "Monaco",             "Ligue 1",        23, 22,  2, "R", 186, 18.0),
    ("Armel Bella-Kotchap",    "CB",  "Southampton",        "Championship",   23, 12,  0, "R", 188, 12.0),
    ("Lazare Amani",           "MID", "Clermont",           "Ligue 1",        26, 18,  2, "R", 180, 3.0),
    ("Ahmed Toure",            "MID", "ASEC Mimosas",       "Ligue 1 CIV",    27, 20,  4, "R", 178, 1.5),
    ("Christian Kouamé",       "ST",  "Fiorentina",         "Serie A",        26, 28, 10, "R", 183, 12.0),
    ("Jean-Daniel Akpa Akpro", "MID", "Cagliari",           "Serie A",        30, 22,  4, "R", 181, 4.0),
    ("Habib Diallo",           "ST",  "Strasbourg",         "Ligue 1",        28, 30, 12, "R", 186, 10.0),
    ("Karim Konaté",           "ST",  "RB Salzburg",        "Bundesliga A",   22, 15,  5, "L", 179, 12.0),
    ("Calvin Tete",            "RB",  "Lyon",               "Ligue 1",        27, 20,  1, "R", 177, 6.0),
],

"Tunisia": [
    ("Aymen Dahmen",           "GK",  "Montpellier",        "Ligue 1",        26, 28,  0, "R", 186, 5.0),
    ("Mouez Hassen",           "GK",  "Maccabi Haifa",      "Israeli PL",     28, 22,  0, "R", 189, 2.5),
    ("Mohamed Drager",         "RB",  "Montpellier",        "Ligue 1",        27, 42,  2, "R", 178, 4.0),
    ("Dylan Bronn",            "CB",  "Göztepe",            "Süper Lig",      29, 38,  2, "R", 186, 4.0),
    ("Montassar Talbi",        "CB",  "Lecce",              "Serie A",        25, 32,  3, "R", 187, 8.0),
    ("Ali Maaloul",            "LB",  "Al-Ahly",            "Egyptian PL",    34, 78, 11, "L", 177, 2.0),
    ("Ellyes Skhiri",          "MID", "Eintracht Frankfurt","Bundesliga",      28, 55,  7, "R", 181, 18.0),
    ("Anis Ben Slimane",       "MID", "Brighton",           "Premier League", 22, 18,  3, "R", 186, 15.0),
    ("Youssef Msakni",         "LW",  "Al-Arabi",           "Qatar Stars",    35, 90, 25, "L", 173, 2.0),
    ("Wahbi Khazri",           "CAM", "Montpellier",        "Ligue 1",        32, 68, 22, "R", 184, 3.0),
    ("Naim Sliti",             "LW",  "Kasimpasa",          "Süper Lig",      30, 48, 10, "L", 175, 3.0),
    ("Ferjani Sassi",          "MID", "Al-Duhail",          "Qatar Stars",    33, 65, 14, "R", 181, 2.0),
    ("Mohamed Ali Ben Romdhane","MID","Nantes",             "Ligue 1",        26, 25,  4, "R", 183, 5.0),
    ("Ghailene Chaalali",      "MID", "Al-Ain",             "UAE Pro League", 28, 35,  5, "R", 175, 3.0),
    ("Issam Jebali",           "ST",  "Odense",             "Danish SL",      28, 42, 18, "R", 181, 5.0),
    ("Seifeddine Jaziri",      "ST",  "Troyes",             "Ligue 2",        30, 45, 14, "R", 181, 3.0),
    ("Hannibal Mejbri",        "MID", "Birmingham",         "Championship",   21, 25,  3, "R", 181, 14.0),
    ("Mortadha Ben Ouanes",    "MID", "USM Tunis",          "Ligue 1 TUN",    28, 20,  3, "R", 178, 1.5),
    ("Taha Yassine Khenissi",  "ST",  "Esperance",          "Ligue 1 TUN",    33, 55, 20, "R", 179, 1.5),
    ("Hamza Mathlouthi",       "GK",  "USM Tunis",          "Ligue 1 TUN",    32, 12,  0, "R", 184, 0.5),
    ("Mohamed Amine Tougai",   "MID", "Kasimpasa",          "Süper Lig",      26, 22,  3, "R", 180, 3.0),
    ("Aissa Laidouni",         "MID", "Union Berlin",       "Bundesliga",     27, 30,  4, "R", 182, 7.0),
    ("Rami Bedoui",            "CB",  "Eintracht Frankfurt","Bundesliga",      25, 15,  1, "R", 185, 4.0),
    ("Bassem Srarfi",          "LW",  "Nice",               "Ligue 1",        28, 25,  5, "L", 172, 4.0),
    ("Dani Ceballos",          "MID", None,                 None,             27,  0,  0, "R", 179, 0.0),  # not Tunisian, skip
    ("Yan Valery",             "RB",  "Southampton",        "Championship",   25, 15,  1, "R", 180, 4.0),
    ("Wajdi Kechrida",         "RB",  "Trabzonspor",        "Süper Lig",      29, 42,  3, "R", 178, 4.0),
    ("Elias Achouri",          "LW",  "Kortrijk",           "Pro League",     24, 12,  2, "L", 175, 2.0),
    ("Yassine Meriah",         "CB",  "Panathinaikos",      "Super League",   30, 45,  3, "R", 190, 4.0),
    ("Chaim Bou Amara",        "LB",  "Al-Ahly",            "Egyptian PL",    26, 12,  1, "L", 177, 2.0),
    ("Saif-Eddine Khaoui",     "CAM", "Troyes",             "Ligue 2",        30, 22,  4, "R", 177, 2.0),
],

"Czechia": [
    ("Matěj Kovář",            "GK",  "Bayer Leverkusen",   "Bundesliga",     23, 18,  0, "R", 193, 18.0),
    ("Jindřich Staněk",        "GK",  "Slavia Prague",      "Czech First League", 26, 22, 0, "R", 197, 5.0),
    ("Vladimír Coufal",        "RB",  "West Ham",           "Premier League", 32, 48,  2, "R", 180, 8.0),
    ("Pavel Kadeřábek",        "RB",  "Hoffenheim",         "Bundesliga",     32, 62,  4, "R", 181, 5.0),
    ("Jakub Brabec",           "CB",  "Plzen",              "Czech First League", 32, 30, 2, "R", 190, 3.0),
    ("David Zima",             "CB",  "Torino",             "Serie A",        24, 22,  0, "R", 192, 6.0),
    ("Tomáš Holes",            "MID", "Slavia Prague",      "Czech First League", 30, 35, 3, "R", 192, 5.0),
    ("Ladislav Krejci",        "LB",  "Sparta Prague",      "Czech First League", 22, 18, 1, "L", 185, 8.0),
    ("Tomáš Souček",           "MID", "West Ham",           "Premier League", 29, 62,  7, "R", 192, 22.0),
    ("Antonín Barák",          "CAM", "Fiorentina",         "Serie A",        28, 42,  9, "R", 188, 12.0),
    ("Alex Král",              "MID", "Spartak Moscow",     "Russian PL",     25, 35,  2, "R", 187, 4.0),
    ("Lukáš Hrádecký",         "GK",  "Bayer Leverkusen",   "Bundesliga",     35, 38,  0, "R", 188, 5.0),
    ("Adam Hložek",            "LW",  "Bayer Leverkusen",   "Bundesliga",     21, 25,  6, "R", 186, 22.0),
    ("Ondřej Lingr",           "LW",  "Feyenoord",          "Eredivisie",     24, 20,  4, "R", 179, 8.0),
    ("Patrik Schick",          "ST",  "Bayer Leverkusen",   "Bundesliga",     28, 52, 27, "R", 190, 35.0),
    ("Jan Kuchta",             "ST",  "Slavia Prague",      "Czech First League", 27, 30, 12, "R", 186, 6.0),
    ("Ondřej Duda",            "CAM", "Norwich",            "Championship",   28, 38,  8, "R", 180, 4.0),
    ("Václav Černý",           "RW",  "Wolfsburg",          "Bundesliga",     26, 28,  7, "R", 175, 12.0),
    ("Filip Nguyen",           "GK",  "Slavia Prague",      "Czech First League", 34, 10, 0, "R", 187, 1.5),
    ("Libor Kozak",            "ST",  "Zbrojovka Brno",     "Czech First League", 34, 20, 8, "R", 193, 1.0),
    ("Marek Suchy",            "CB",  "Basel",              "Super League",   36, 40,  2, "R", 187, 0.5),
    ("Jakub Jankto",           "MID", "Sparta Prague",      "Czech First League", 28, 45, 5, "L", 181, 5.0),
    ("Stanislav Tecl",         "ST",  "Slavia Prague",      "Czech First League", 34, 20, 8, "R", 182, 1.5),
    ("Lukas Provod",           "MID", "Slavia Prague",      "Czech First League", 26, 22, 4, "R", 182, 5.0),
    ("Martin Vitik",           "CB",  "Sparta Prague",      "Czech First League", 22, 15, 1, "R", 190, 6.0),
    ("Michal Sadilek",         "MID", "Twente",             "Eredivisie",     25, 18,  2, "R", 183, 5.0),
    ("Roman Květ",             "RW",  "Sparta Prague",      "Czech First League", 23, 10, 2, "R", 175, 3.0),
    ("Jakub Pešek",            "LW",  "Slavia Prague",      "Czech First League", 22, 8,  1, "L", 175, 3.0),
    ("David Jurasek",          "LB",  "Benfica",            "Primeira Liga",  24, 18,  1, "L", 180, 10.0),
    ("Christos Zafeiris",      "MID", "Sparta Prague",      "Czech First League", 23, 10, 1, "R", 185, 5.0),
    ("Mojmir Chytil",          "ST",  "Olympique Lyon",     "Ligue 1",        24, 12,  4, "R", 187, 7.0),
    ("Lukas Kalvach",          "MID", "Plzen",              "Czech First League", 28, 22, 2, "R", 186, 4.0),
],

"Bosnia and Herzegovina": [
    ("Kenan Piric",            "GK",  "Watford",            "Championship",   26, 15,  0, "R", 193, 4.0),
    ("Jasmin Handanovic",      "GK",  "Udinese",            "Serie A",        40, 25,  0, "R", 196, 0.5),
    ("Anel Ahmedhodžić",       "CB",  "Sheffield Utd",      "Premier League", 25, 28,  3, "R", 190, 18.0),
    ("Ermin Bicakcic",         "CB",  "Hoffenheim",         "Bundesliga",     34, 40,  1, "R", 185, 2.0),
    ("Sead Kolašinac",         "LB",  "Marseille",          "Ligue 1",        30, 65, 10, "L", 181, 5.0),
    ("Josip Stanisic",         "RB",  None,                 None,             24,  0,  0, "R", 184, 0.0),  # plays for Croatia
    ("Haris Tabakovic",        "ST",  "Hertha BSC",         "2. Bundesliga",  30, 22, 10, "R", 183, 4.0),
    ("Ermedin Demirović",      "ST",  "Stuttgart",          "Bundesliga",     26, 32, 15, "R", 187, 25.0),
    ("Gojko Cimirot",          "MID", "Standard Liège",     "Pro League",     32, 42,  4, "R", 183, 2.0),
    ("Rade Krunic",            "MID", "AC Milan",           "Serie A",        30, 48,  8, "R", 183, 12.0),
    ("Amir Hadziahmetovic",    "MID", "Sheffield Utd",      "Premier League", 26, 28,  3, "R", 183, 8.0),
    ("Muhamed Besic",          "MID", "Watford",            "Championship",   31, 40,  3, "R", 178, 3.0),
    ("Fikret Dilaver",         "CB",  "Istanbul Basaksehir","Süper Lig",       33, 28,  2, "R", 191, 2.0),
    ("Edin Džeko",             "ST",  "Fenerbahce",         "Süper Lig",       38, 110, 63, "R", 193, 4.0),
    ("Miralem Pjanić",         "MID", "Sharjah",            "Arabian Gulf",   34, 115, 17, "R", 178, 5.0),
    ("Asmir Begovic",          "GK",  "Everton",            "Premier League", 37, 65,  0, "R", 198, 1.5),
    ("Sandi Lovric",           "MID", "Udinese",            "Serie A",        25, 18,  3, "L", 185, 10.0),
    ("Dzenis Burnic",          "MID", "Fortuna Düsseldorf", "2. Bundesliga",  26, 12,  1, "R", 183, 4.0),
    ("Armin Hodžić",           "ST",  "Hajduk Split",       "HNL",            30, 22,  8, "R", 187, 2.0),
    ("Benjamin Verbic",        "LW",  "Dynamo Kyiv",        "Ukrainian PL",   30, 22,  5, "L", 181, 3.0),
    ("Kemal Ademi",            "ST",  "FC Zurich",          "Super League",   29, 18,  6, "R", 185, 3.0),
    ("Josip Dropulic",         "RW",  "Borac Banja Luka",   "Premier League BIH", 25, 12, 2, "R", 181, 1.5),
    ("Denis Huseinbasic",      "MID", "Koln",               "2. Bundesliga",  24, 15,  2, "R", 183, 5.0),
    ("Dzenan Burekovic",       "LW",  "NK Celik",           "Premier League BIH", 24, 10, 2, "L", 176, 1.0),
    ("Samir Toplak",           "CB",  "NK Rudar",           "Premier League BIH", 26, 8,  0, "R", 192, 0.8),
    ("Suljo Mujakic",          "LB",  "Olimpija Ljubljana", "Slovenian PL",   25, 10,  0, "L", 180, 1.0),
    ("Adnan Kovacevic",        "RB",  "Borac Banja Luka",   "Premier League BIH", 28, 15, 1, "R", 178, 1.5),
    ("Semir Stevanovic",       "RW",  "Rapid Vienna",       "Bundesliga A",   34, 38,  6, "R", 178, 1.5),
    ("Luka Menalo",            "LW",  "Dinamo Zagreb",      "HNL",            28, 20,  5, "L", 182, 4.0),
    ("Nasr Larbes",            "MID", "Yverdon",            "Super League",   26, 10,  1, "R", 180, 2.0),
    ("Haris Hajradinovic",     "CAM", "Zorya Luhansk",      "Ukrainian PL",   26, 12,  3, "R", 177, 2.0),
    ("Nikola Gulan",           "LB",  "Vojvodina",          "Serbian SL",     26,  8,  0, "L", 180, 1.0),
],

"Qatar": [
    ("Meshaal Barsham",        "GK",  "Al-Sadd",            "Qatar Stars",    25, 42,  0, "R", 193, 3.0),
    ("Saad Al-Sheeb",          "GK",  "Al-Sadd",            "Qatar Stars",    33, 58,  0, "R", 188, 1.5),
    ("Pedro Miguel",           "LB",  "Al-Duhail",          "Qatar Stars",    32, 68,  5, "L", 177, 2.0),
    ("Bassam Al-Rawi",         "CB",  "Al-Sadd",            "Qatar Stars",    26, 38,  2, "R", 190, 2.0),
    ("Tarek Salman",           "CB",  "Al-Arabi",           "Qatar Stars",    30, 35,  1, "R", 185, 1.5),
    ("Boualem Khoukhi",        "CB",  "Al-Sadd",            "Qatar Stars",    33, 72,  3, "R", 184, 2.0),
    ("Khalid Muneer",          "RB",  "Al-Duhail",          "Qatar Stars",    27, 40,  2, "R", 176, 1.5),
    ("Karim Boudiaf",          "MID", "Al-Duhail",          "Qatar Stars",    33, 65,  6, "R", 183, 2.0),
    ("Assim Madibo",           "MID", "Al-Duhail",          "Qatar Stars",    26, 40,  3, "R", 180, 2.5),
    ("Abdulaziz Hatem",        "MID", "Al-Rayyan",          "Qatar Stars",    30, 58,  8, "R", 176, 2.0),
    ("Hassan Al-Haydos",       "CAM", "Al-Sadd",            "Qatar Stars",    32, 165, 65, "R", 172, 3.0),
    ("Mohammed Muntari",       "ST",  "Al-Duhail",          "Qatar Stars",    28, 55, 22, "R", 185, 4.0),
    ("Almoez Ali",             "ST",  "Al-Duhail",          "Qatar Stars",    28, 72, 44, "R", 186, 5.0),
    ("Akram Afif",             "LW",  "Al-Sadd",            "Qatar Stars",    27, 78, 32, "L", 176, 8.0),
    ("Ahmed Alaaeldin",        "RW",  "Al-Sadd",            "Qatar Stars",    27, 42, 10, "R", 175, 2.0),
    ("Ismail Mohamad",         "LB",  "Al-Gharafa",         "Qatar Stars",    28, 30,  1, "L", 178, 1.0),
    ("Ali Asad",               "RW",  "Al-Gharafa",         "Qatar Stars",    26, 32,  5, "R", 173, 1.5),
    ("Yousuf Abdurisag",       "ST",  "Al-Ahli",            "Qatar Stars",    24, 20,  7, "R", 182, 2.0),
    ("Naif Al-Hadhrami",       "MID", "Al-Ahli",            "Qatar Stars",    27, 28,  3, "R", 177, 1.5),
    ("Mustafa Mshawi",         "RB",  "Al-Wakrah",          "Qatar Stars",    25, 18,  0, "R", 174, 0.8),
    ("Ahmad Moein",            "CB",  "Al-Sadd",            "Qatar Stars",    26, 22,  1, "R", 188, 1.0),
    ("Salem Al-Hajri",         "MID", "Al-Rayyan",          "Qatar Stars",    28, 25,  2, "R", 180, 1.0),
    ("Sultan Al-Brake",        "ST",  "Al-Ahli",            "Qatar Stars",    24, 18,  5, "R", 178, 1.5),
    ("Khalfan Ibrahim",        "LW",  "Al-Ahli",            "Qatar Stars",    36, 85, 25, "L", 171, 1.0),
    ("Ahmad Al-Haidary",       "GK",  "Al-Ahli",            "Qatar Stars",    28, 12,  0, "R", 186, 0.8),
    ("Ibrahim Almouslemani",   "MID", "Al-Duhail",          "Qatar Stars",    28, 20,  2, "R", 179, 1.0),
    ("Homam Ahmed",            "CB",  "Al-Sadd",            "Qatar Stars",    25, 15,  0, "R", 187, 1.0),
    ("Khaled Muftah",          "RB",  "Al-Sadd",            "Qatar Stars",    26, 18,  1, "R", 175, 0.8),
    ("Jassem Jabir",           "CB",  "Al-Sadd",            "Qatar Stars",    30, 28,  2, "R", 192, 1.5),
    ("Pedro Correia",          "MID", "Al-Rayyan",          "Qatar Stars",    28, 25,  3, "R", 178, 1.0),
    ("Tariq Salman",           "LW",  "Al-Gharafa",         "Qatar Stars",    22, 8,   2, "L", 172, 0.8),
    ("Moayed Ali",             "MID", "Al-Wakrah",          "Qatar Stars",    24, 12,  1, "R", 176, 0.6),
],

"Haiti": [
    ("Josue Duverger",         "GK",  "Inter Miami",        "MLS",            28, 22,  0, "R", 187, 1.5),
    ("Orlando Mosquera",       "GK",  "Louisville City",    "USL",            30, 15,  0, "R", 185, 0.5),
    ("Andrew Jean-Baptiste",   "CB",  "Columbus Crew",      "MLS",            31, 40,  3, "R", 190, 3.0),
    ("Carlens Arcus",          "RB",  "FC Dallas",          "MLS",            29, 35,  2, "R", 177, 2.0),
    ("Florent Valoua",         "LB",  "Guingamp",           "Ligue 2",        27, 25,  1, "L", 178, 1.5),
    ("Pascal Comvalius",       "CB",  "Oud-Heverlee Leuven","Pro League",     28, 20,  1, "R", 185, 1.5),
    ("James Lea Siliki",       "MID", "Stade Rennais",      "Ligue 1",        27, 20,  2, "R", 175, 6.0),
    ("Jean-Eudes Maurice",     "MID", "Red Bull Salzburg",  "Bundesliga A",   24, 25,  3, "R", 178, 6.0),
    ("Derrick Etienne",        "MID", "Charlotte FC",       "MLS",            28, 45,  6, "R", 172, 2.0),
    ("Wilde-Donald Guerrier",  "RW",  "CF Montreal",        "MLS",            30, 38,  8, "R", 178, 1.5),
    ("Mechack Jerome",         "LW",  "Philadelphia Union", "MLS",            32, 50, 10, "R", 176, 1.5),
    ("Frantzdy Pierrot",       "ST",  "CF Montreal",        "MLS",            30, 42, 15, "R", 185, 2.0),
    ("Duckens Nazon",          "ST",  "Metz",               "Ligue 2",        30, 38, 12, "L", 180, 2.0),
    ("Kevin Lafrance",         "ST",  "Charlotte FC",       "MLS",            28, 35, 10, "R", 181, 2.0),
    ("Djimy Alexis",           "MID", "Maccabi Netanya",    "Israeli PL",     28, 28,  4, "R", 178, 1.0),
    ("Jonathan Remy",          "LW",  "New England Revolution","MLS",         26, 22,  5, "L", 172, 1.5),
    ("Mathieu Choiniere",      "LW",  "CF Montreal",        "MLS",            24, 18,  4, "L", 172, 2.0),
    ("Lamarana Balde",         "CB",  "Caen",               "Ligue 2",        26, 15,  1, "R", 188, 1.0),
    ("Samuel Camille",         "GK",  "AS Cavaly",          "Ligue Haïtienne",30, 20,  0, "R", 184, 0.5),
    ("Steeven Saba",           "ST",  "New England Revolution","MLS",         26, 18,  5, "R", 178, 1.5),
    ("Steeven Saba",           "ST",  "Caps United",        "PSL",            27, 15,  3, "R", 180, 0.8),
    ("Hens Barthelemy",        "CB",  "Tampa Bay Rowdies",  "USL",            27, 15,  1, "R", 186, 0.8),
    ("Reginal Goreux",         "RB",  "Retired",            None,             37, 75,  5, "R", 180, 0.5),
    ("Jeff Louis",             "MID", "CF Montreal",        "MLS",            24, 12,  1, "R", 179, 1.0),
    ("Nahcivan Bellot",        "LB",  "Houston Dynamo",     "MLS",            25, 12,  0, "L", 177, 0.8),
    ("Jonel Nguessan",         "LW",  "Strasbourg",         "Ligue 1",        22, 8,   2, "L", 175, 3.0),
    ("Adly Augustin",          "ST",  "Rayo Vallecano",     "La Liga",        23, 10,  3, "R", 182, 4.0),
    ("Franck Alvarez",         "CB",  "Los Angeles FC",     "MLS",            26, 15,  1, "R", 191, 2.0),
    ("Patrick Antignac",       "MID", "Gap FC",             "National 2",     25, 10,  1, "R", 180, 0.8),
    ("Loic Akpan",             "RW",  "Colorado Rapids",    "MLS",            24, 10,  2, "R", 174, 1.0),
],

"Curacao": [
    ("Eloy Room",              "GK",  "Columbus Crew",      "MLS",            33, 48,  0, "R", 186, 1.5),
    ("Nordin Klomp",           "GK",  "NAC Breda",          "Eredivisie",     28, 12,  0, "R", 190, 1.0),
    ("Cuco Martina",           "RB",  "Excelsior",          "Eredivisie",     35, 65,  4, "R", 176, 0.8),
    ("Jurien Gaari",           "CB",  "Almere City",        "Eredivisie",     27, 25,  2, "R", 188, 2.0),
    ("Leandro Bacuna",         "MID", "Reading",            "Championship",   32, 52,  8, "R", 183, 3.0),
    ("Andwele Slory",          "LW",  "Persebaya",          "Liga 1",         38, 45, 10, "L", 178, 0.5),
    ("Riechedly Bazoer",       "MID", "Vitesse",            "Eredivisie",     28, 35,  4, "R", 186, 4.0),
    ("Sheraldo Becker",        "RW",  "Union Berlin",       "Bundesliga",     28, 40, 10, "R", 181, 12.0),
    ("Gevaro Nepomuceno",      "RW",  "Al-Jazira",          "UAE Pro League", 29, 32,  8, "R", 176, 2.0),
    ("Daishawn Redan",         "ST",  "Hertha BSC",         "2. Bundesliga",  23, 20,  4, "R", 182, 4.0),
    ("Jafar Arias",            "MID", "Almeria",            "La Liga",        25, 22,  3, "R", 178, 5.0),
    ("Rangelo Janga",          "ST",  "SV Ried",            "Bundesliga A",   32, 28,  8, "R", 179, 1.0),
    ("Elson Hooi",             "LW",  "Al-Jazira",          "UAE Pro League", 28, 30,  7, "L", 176, 2.0),
    ("Quentin Sanson",         "MID", "Montpellier",        "Ligue 1",        30, 18,  2, "R", 178, 3.0),
    ("Jamiro Monteiro",        "MID", "New England Revolution","MLS",         31, 42, 10, "R", 178, 2.0),
    ("Gilmer Abrego",          "LB",  "Dallas Burn",        "MLS",            28, 15,  0, "L", 175, 0.8),
    ("Warner Hahn",            "GK",  "FK Krasnodar",       "Russian PL",     30, 20,  0, "R", 185, 1.5),
    ("Curaçao player",         "CB",  "Almere City",        "Eredivisie",     26, 10,  0, "R", 187, 1.0),
    ("Etienne Vaessen",        "GK",  "Almere City",        "Eredivisie",     30, 8,   0, "R", 190, 1.0),
    ("Rugelio Reefman",        "CB",  "Excelsior",          "Eredivisie",     28, 12,  1, "R", 184, 1.0),
    ("Denzel Dumfries",        "RB",  None,                 None,             28, 0,   0, "R", 188, 0.0),  # plays for Netherlands
    ("Tyronne Ebuehi",         "RB",  "Benfica",            "Primeira Liga",  28, 12,  0, "R", 180, 3.0),
    ("Jerry St. Juste",        "CB",  "Mainz",              "Bundesliga",     27, 18,  0, "R", 188, 6.0),
    ("Jonathan Amon",          "LW",  "FC Nordsjælland",    "Danish SL",      24, 15,  3, "L", 178, 3.0),
    ("Kenji Gorré",            "LW",  "Beerschot",          "Pro League",     30, 22,  5, "L", 172, 2.0),
    ("Raphael Matos",          "RW",  "Nice",               "Ligue 1",        22, 10,  2, "R", 177, 4.0),
    ("Sterling Dorsett",       "MID", "Orange City SC",     "MLS Next Pro",   26, 8,   1, "R", 178, 0.5),
    ("Cyriel Dessers",         "ST",  "Rangers",            "Scottish Premiership", 29, 30, 12, "R", 185, 8.0),
    ("Brandley Kuwas",         "LW",  "ADO Den Haag",       "Eerste Divisie", 30, 18,  5, "L", 175, 1.0),
    ("Myron Villar",           "MID", "Almere City",        "Eredivisie",     23, 8,   1, "R", 180, 1.5),
],

"Cape Verde": [
    ("Vozinha",                "GK",  "Moreirense",         "Primeira Liga",  30, 42,  0, "R", 186, 1.0),
    ("Diney Borges",           "GK",  "Académica",          "Primeira Liga",  28, 18,  0, "R", 185, 0.8),
    ("Roberto Lopes",          "CB",  "Shamrock Rovers",    "League of Ireland", 31, 40, 2, "R", 191, 1.5),
    ("Steven Fortes",          "RB",  "Molenbeek",          "Pro League",     33, 52,  2, "R", 175, 1.5),
    ("Marco Soares",           "LB",  "Penafiel",           "Primeira Liga",  28, 30,  1, "L", 177, 1.0),
    ("Stopira",                "LB",  "HB Køge",            "Danish SL",      36, 65,  3, "L", 175, 0.5),
    ("Gilson Tavares",         "CB",  "Arouca",             "Primeira Liga",  27, 25,  1, "R", 188, 1.5),
    ("Kenny Rocha Santos",     "MID", "DC United",          "MLS",            30, 40,  5, "R", 175, 1.5),
    ("Jamiro Monteiro",        "MID", None,                 None,             31,  0,  0, "R", 178, 0.0),
    ("Garry Rodrigues",        "RW",  "Goztepe",            "Süper Lig",      32, 48, 12, "R", 175, 2.0),
    ("Ryan Mendes",            "LW",  "Rio Ave",            "Primeira Liga",  34, 56, 10, "L", 175, 1.5),
    ("Fali Cande",             "LW",  "Girona",             "La Liga",        25, 28,  6, "L", 173, 10.0),
    ("Julio Tavares",          "ST",  "Vitória Guimarães",  "Primeira Liga",  35, 65, 22, "R", 180, 1.0),
    ("Gelson Dala",            "ST",  "Arouca",             "Primeira Liga",  28, 40, 14, "R", 178, 4.0),
    ("Bebé",                   "LW",  "Rayo Vallecano",     "La Liga",        33, 30,  8, "L", 185, 1.5),
    ("Vagner",                 "ST",  "Sion",               "Super League",   32, 35, 10, "R", 182, 1.5),
    ("Fernando Varela",        "CB",  "PAOK",               "Super League",   35, 55,  3, "R", 190, 1.0),
    ("Nuno Borges",            "CB",  "Estoril",            "Primeira Liga",  26, 15,  0, "R", 185, 1.0),
    ("Lisandro Semedo",        "RB",  "Maccabi Haifa",      "Israeli PL",     30, 22,  2, "R", 178, 1.5),
    ("Joao Paulo Semedo",      "MID", "Estrela Amadora",    "Primeira Liga",  25, 12,  1, "R", 180, 1.0),
    ("Dylan Tavares",          "RB",  "Bayer Leverkusen",   "Bundesliga",     23, 20,  1, "R", 179, 5.0),
    ("Junior Almeida",         "CB",  "Toulouse",           "Ligue 1",        28, 15,  0, "R", 186, 3.0),
    ("Patrick Andrade",        "MID", "Troyes",             "Ligue 2",        30, 35,  3, "R", 183, 2.0),
    ("Jovane Cabral",          "RW",  "Sporting CP",        "Primeira Liga",  26, 25,  5, "R", 176, 6.0),
    ("Igor Rodrigues",         "MID", "CD Santa Clara",     "Primeira Liga",  25, 12,  2, "R", 179, 1.5),
    ("Kevin Pina",             "LW",  "Moreirense",         "Primeira Liga",  25, 14,  3, "L", 176, 1.5),
    ("Lele",                   "MID", "Belenenses",         "Primeira Liga",  27, 18,  2, "R", 180, 1.0),
    ("Steeve Yago",            "CB",  "Toulouse",           "Ligue 1",        27, 10,  0, "R", 183, 2.0),
    ("Claudio Winck",          "RB",  "Arouca",             "Primeira Liga",  26, 12,  1, "R", 178, 1.5),
    ("Hermano Santos",         "ST",  "Naval",              "LigaPro",        26, 10,  3, "R", 181, 0.8),
],

"New Zealand": [
    ("Stefan Marinovic",       "GK",  "Al-Ettifaq",         "Saudi Pro League", 34, 42, 0, "R", 190, 1.0),
    ("Oliver Sail",            "GK",  "Wigan Athletic",     "League One",     27, 18,  0, "R", 188, 0.8),
    ("Michael Boxall",         "CB",  "Minnesota United",   "MLS",            35, 52,  2, "R", 189, 2.0),
    ("Tim Payne",              "CB",  "Portland Timbers",   "MLS",            28, 32,  1, "R", 187, 2.0),
    ("Dane Ingham",            "RB",  "Ferencváros",        "OTP Bank Liga",  28, 38,  2, "R", 180, 1.5),
    ("Liberato Cacace",        "LB",  "Empoli",             "Serie A",        23, 35,  2, "L", 172, 8.0),
    ("Winston Reid",           "CB",  "Brentford",          "Premier League", 36, 60,  4, "R", 193, 0.5),
    ("Clayton Lewis",          "MID", "New York Red Bulls", "MLS",            26, 38,  4, "R", 178, 3.0),
    ("Ryan Thomas",            "MID", "Plymouth Argyle",    "Championship",   30, 35,  3, "R", 183, 1.5),
    ("Elijah Just",            "MID", "IFK Norrkoping",     "Allsvenskan",    25, 30,  4, "R", 181, 2.0),
    ("Joe Bell",               "MID", "Middlesbrough",      "Championship",   25, 28,  3, "R", 180, 3.0),
    ("Alex Rufer",             "MID", "Ferencváros",        "OTP Bank Liga",  29, 42,  5, "L", 179, 2.0),
    ("Marco Rojas",            "RW",  "Melbourne City",     "A-League",       33, 55, 12, "R", 172, 1.0),
    ("Kosta Barbarouses",      "LW",  "Vancouver Whitecaps","MLS",            33, 52, 12, "L", 176, 1.0),
    ("Sarpreet Singh",         "LW",  "FC Nürnberg",        "2. Bundesliga",  25, 30,  7, "L", 177, 3.0),
    ("Chris Wood",             "ST",  "Nottm Forest",       "Premier League", 32, 75, 32, "R", 190, 10.0),
    ("Oli Sail",               "GK",  None,                 None,             27,  0,  0, "R", 188, 0.0),
    ("Matthew Garbett",        "MID", "Auckland FC",        "A-League",       24, 15,  2, "R", 182, 1.0),
    ("Max Mata",               "ST",  "Portland Timbers",   "MLS",            30, 28,  8, "R", 182, 1.5),
    ("Danny Musovski",         "ST",  "LA Galaxy",          "MLS",            26, 20,  5, "R", 180, 1.5),
    ("Finn Surman",            "MID", "Auckland FC",        "A-League",       25, 18,  2, "R", 179, 0.8),
    ("Nando Pijnaker",         "CB",  "SC Cambuur",         "Eerste Divisie", 28, 25,  1, "R", 193, 1.5),
    ("Ben Waine",              "ST",  "Hammarby",           "Allsvenskan",    23, 18,  4, "R", 184, 2.5),
    ("Callum McCowatt",        "LW",  "HB Køge",            "Danish SL",      25, 22,  5, "L", 177, 1.5),
    ("Bill Tuilagi",           "RB",  "Hammarby",           "Allsvenskan",    28, 20,  1, "R", 180, 1.5),
    ("Deklan Wynne",           "RB",  "Colorado Rapids",    "MLS",            27, 22,  1, "R", 175, 1.5),
    ("Cameron Howieson",       "MID", "Sonderjyske",        "Danish SL",      25, 15,  1, "R", 181, 1.0),
    ("Louis Fenton",           "LB",  "Sonderjyske",        "Danish SL",      32, 30,  1, "L", 181, 0.8),
    ("Tom Doyle",              "MID", "New York RB",        "MLS",            23, 10,  1, "R", 178, 1.0),
    ("Hamish Watson",          "CB",  "Auckland FC",        "A-League",       26, 12,  0, "R", 185, 0.5),
],

"South Africa": [
    ("Ronwen Williams",        "GK",  "Mamelodi Sundowns",  "Premier Soccer League", 32, 55, 0, "R", 182, 1.5),
    ("Bruce Bvuma",            "GK",  "Kaizer Chiefs",      "Premier Soccer League", 30, 20, 0, "R", 186, 0.8),
    ("Siyanda Xulu",           "CB",  "Hellas Verona",      "Serie A",        32, 42,  2, "R", 191, 2.0),
    ("Rushine De Reuck",       "CB",  "Mamelodi Sundowns",  "Premier Soccer League", 28, 35, 1, "R", 190, 1.0),
    ("Thibang Phete",          "CB",  "Belenenses SAD",     "LigaPro",        27, 25,  0, "R", 183, 1.5),
    ("Reeve Frosler",          "RB",  "Mamelodi Sundowns",  "Premier Soccer League", 27, 30, 2, "R", 175, 1.0),
    ("Aubrey Ngoma",           "LB",  "Cape Town City",     "Premier Soccer League", 29, 32, 3, "L", 172, 0.8),
    ("Bongani Zungu",          "MID", "AEK Athens",         "Super League",   31, 52,  5, "R", 184, 3.0),
    ("Sipho Mbule",            "MID", "Mamelodi Sundowns",  "Premier Soccer League", 25, 28, 4, "R", 175, 1.5),
    ("Mothobi Mvala",          "MID", "Mamelodi Sundowns",  "Premier Soccer League", 27, 30, 2, "R", 184, 1.0),
    ("Themba Zwane",           "MID", "Mamelodi Sundowns",  "Premier Soccer League", 33, 55, 12, "R", 169, 1.0),
    ("Keagan Dolly",           "RW",  "Kaizer Chiefs",      "Premier Soccer League", 30, 48, 14, "R", 169, 1.0),
    ("Mihlali Mayambela",      "LW",  "FC Copenhagen",      "Superliga",      25, 22,  4, "L", 173, 3.0),
    ("Percy Tau",              "LW",  "Al-Ahly",            "Egyptian PL",    30, 55, 12, "L", 171, 4.0),
    ("Siyethemba Sithebe",     "MID", "AmaZulu",            "Premier Soccer League", 29, 28, 5, "R", 177, 0.8),
    ("Evidence Makgopa",       "ST",  "Orlando Pirates",    "Premier Soccer League", 24, 22, 7, "R", 183, 2.0),
    ("Lyle Foster",            "ST",  "Burnley",            "Championship",   24, 28, 10, "R", 183, 8.0),
    ("Bafana Bafana",          "ST",  "Orlando Pirates",    "Premier Soccer League", 27, 18, 5, "R", 181, 1.5),
    ("Itumeleng Khune",        "GK",  "Kaizer Chiefs",      "Premier Soccer League", 37, 92, 0, "R", 185, 0.5),
    ("Thulani Serero",         "MID", "Al-Wahda",           "UAE Pro League", 33, 48,  7, "R", 179, 1.5),
    ("Lebogang Manyama",       "MID", "Kaizer Chiefs",      "Premier Soccer League", 32, 32, 5, "R", 178, 0.8),
    ("Andile Jali",            "MID", "Mamelodi Sundowns",  "Premier Soccer League", 33, 52, 8, "R", 180, 0.8),
    ("Dean Furman",            "MID", "Retired",            None,             36, 48,  2, "R", 178, 0.5),
    ("Luther Singh",           "RW",  "FC Porto B",         "LigaPro",        25, 18,  3, "R", 168, 1.5),
    ("Nkosinathi Sibisi",      "CB",  "Mamelodi Sundowns",  "Premier Soccer League", 27, 22, 1, "R", 188, 0.8),
    ("Terrence Mashego",       "LB",  "Mamelodi Sundowns",  "Premier Soccer League", 28, 18, 1, "L", 172, 0.8),
    ("Nedrick David",          "RW",  "IF Brommapojkarna",  "Allsvenskan",    24, 12,  2, "R", 175, 1.0),
    ("Teboho Mokoena",         "MID", "Mamelodi Sundowns",  "Premier Soccer League", 26, 35, 5, "R", 176, 1.5),
    ("Oswin Appollis",         "LW",  "Mamelodi Sundowns",  "Premier Soccer League", 22, 18, 4, "L", 168, 1.5),
    ("Elias Mokwana",          "LW",  "Mamelodi Sundowns",  "Premier Soccer League", 24, 12, 3, "L", 170, 1.0),
    ("Khuliso Mudau",          "RB",  "Mamelodi Sundowns",  "Premier Soccer League", 27, 22, 2, "R", 177, 1.0),
    ("Yusuf Maart",            "MID", "Kaizer Chiefs",      "Premier Soccer League", 27, 15, 2, "R", 180, 0.8),
],

"Uzbekistan": [
    ("Otabek Shukurov",        "GK",  "AGMK",               "Uzbek League",   28, 35,  0, "R", 190, 1.0),
    ("Ulugbek Ashnazarov",     "GK",  "Pakhtakor",          "Uzbek League",   30, 18,  0, "R", 188, 0.8),
    ("Azizbek Turgunboev",     "CB",  "Pakhtakor",          "Uzbek League",   26, 35,  2, "R", 188, 1.5),
    ("Jamshid Iskanderov",     "CB",  "Pakhtakor",          "Uzbek League",   28, 30,  1, "R", 192, 1.0),
    ("Nodir Nazarov",          "RB",  "Pakhtakor",          "Uzbek League",   26, 32,  2, "R", 177, 1.0),
    ("Khasan Abdullaev",       "LB",  "Lokomotiv Tashkent", "Uzbek League",   25, 28,  1, "L", 175, 0.8),
    ("Oston Urunov",           "MID", "Lokomotiv Moscow",   "Russian PL",     27, 42,  5, "R", 180, 4.0),
    ("Khojiakbar Alijonov",    "MID", "Pakhtakor",          "Uzbek League",   26, 35,  3, "R", 178, 1.5),
    ("Sarvar Komilov",         "MID", "Pakhtakor",          "Uzbek League",   25, 30,  4, "R", 176, 1.5),
    ("Jaloliddin Masharipov",  "CAM", "Beijing Guoan",      "Chinese Super League", 31, 55, 10, "R", 180, 3.0),
    ("Behruz Aliqulov",        "CB",  "Krylia Sovetov",     "Russian PL",     27, 28,  1, "R", 186, 2.0),
    ("Yusuf Abdullaev",        "MID", "Al-Hilal",           "Saudi Pro League",29, 42, 8, "R", 179, 5.0),
    ("Khayrullo Boltaboev",    "RW",  "Pakhtakor",          "Uzbek League",   25, 28,  5, "R", 175, 1.5),
    ("Akbar Turgunboev",       "ST",  "AGMK",               "Uzbek League",   26, 22,  7, "R", 183, 1.0),
    ("Eldor Shomurodov",       "ST",  "Roma",               "Serie A",        28, 62, 28, "R", 186, 18.0),
    ("Dostonbek Khamdamov",    "RW",  "Pakhtakor",          "Uzbek League",   22, 20,  5, "R", 177, 2.0),
    ("Bobur Abdixoliqov",      "LW",  "FC Navbahor",        "Uzbek League",   25, 25,  4, "L", 174, 1.0),
    ("Bahodir Nasimov",        "RW",  "Bunyodkor",          "Uzbek League",   23, 18,  3, "R", 178, 1.0),
    ("Sarvarbek Ergashev",     "ST",  "Pakhtakor",          "Uzbek League",   27, 28, 10, "R", 184, 1.5),
    ("Temurkhon Abdukholiqov", "MID", "Pakhtakor",          "Uzbek League",   24, 15,  2, "R", 181, 1.0),
    ("Rustam Ashurmatov",      "CB",  "Pakhtakor",          "Uzbek League",   27, 25,  1, "R", 185, 1.0),
    ("Sharofiddin Mukhitdinov","RB",  "FC Metallurg",       "Uzbek League",   23, 12,  0, "R", 176, 0.8),
    ("Umid Hasanov",           "MID", "Bunyodkor",          "Uzbek League",   25, 18,  2, "R", 178, 0.8),
    ("Odil Ahmedov",           "MID", "Al-Ain",             "UAE Pro League", 35, 68, 10, "R", 181, 1.5),
    ("Jamoliddin Abdullaev",   "LW",  "Pakhtakor",          "Uzbek League",   22, 12,  3, "L", 175, 1.0),
    ("Furkat Sayfiev",         "LB",  "Pakhtakor",          "Uzbek League",   26, 15,  1, "L", 176, 0.8),
    ("Dilshod Nematov",        "GK",  "Bunyodkor",          "Uzbek League",   26, 8,   0, "R", 185, 0.5),
    ("Doniyor Islamov",        "RW",  "Lokomotiv Tashkent", "Uzbek League",   23, 12,  2, "R", 173, 0.8),
    ("Abbosbek Fayzullaev",    "LW",  "Maccabi Tel Aviv",   "Israeli PL",     22, 20,  4, "L", 174, 5.0),
    ("Ikhtiyor Akhmedov",      "ST",  "AGMK",               "Uzbek League",   24, 15,  4, "R", 180, 1.0),
    ("Sherzod Yakhshiboev",    "CAM", "Lokomotiv Moscow",   "Russian PL",     25, 18,  3, "R", 178, 2.0),
    ("Davronbek Hamrobekov",   "CB",  "Pakhtakor",          "Uzbek League",   24, 10,  0, "R", 189, 0.8),
],

}


def run():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    total_inserted = 0
    team_counts = {}

    for team_name, players in SQUADS.items():
        # Get team_id
        row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            print(f"  WARN: Team not found: {team_name}")
            continue
        team_id = row[0]

        # Check existing players
        existing = cur.execute("SELECT COUNT(*) FROM players WHERE team_id=?", (team_id,)).fetchone()[0]
        if existing > 10:
            print(f"  SKIP: {team_name} already has {existing} players")
            continue

        inserted = 0
        seen_names = set()
        for p in players:
            name, pos, club, league, age, caps, goals, foot, height, value = p
            # Skip placeholders and duplicates
            if not name or name in seen_names or "player" in name.lower() or club == "Retired":
                continue
            # Skip players who play for a different national team (club=None, value=0)
            if club is None and value == 0 and caps == 0:
                continue
            seen_names.add(name)
            cur.execute("""
                INSERT OR IGNORE INTO players
                  (name, team_id, position, club, club_league, age, caps, goals_as_nat,
                   preferred_foot, height_cm, market_value_m)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (name, team_id, pos, club, league, age, caps, goals, foot, height, value))
            inserted += 1

        conn.commit()
        team_counts[team_name] = inserted
        total_inserted += inserted
        print(f"  {team_name:<30} {inserted} players inserted")

    print(f"\nTotal: {total_inserted} players inserted")

    # Now compute ratings for these new players
    print("\nComputing ratings for new players...")
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(DB).parent.parent))
        from models.player_rating import PlayerRatingEngine
        engine = PlayerRatingEngine(DB)
        engine.compute_all_ratings()
        total_ratings = conn.execute("SELECT COUNT(*) FROM player_ratings").fetchone()[0]
        print(f"  player_ratings total: {total_ratings}")
    except Exception as e:
        print(f"  Rating computation error: {e}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    run()
