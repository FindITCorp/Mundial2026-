"""
setup_db.py — Crea y pobla la base de datos SQLite para el sistema de prediccion Mundial 2026.

Uso:
  python scripts/setup_db.py
  python scripts/setup_db.py --reset  (borra y recrea todo)
"""
import sqlite3
import json
import argparse
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
STATIC_DIR = Path(__file__).parent.parent / "data" / "static"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def create_tables(conn: sqlite3.Connection):
    cur = conn.cursor()

    # --- teams ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        id               INTEGER PRIMARY KEY,
        name             TEXT    NOT NULL UNIQUE,
        slug             TEXT    NOT NULL UNIQUE,
        confederation    TEXT    NOT NULL,
        fifa_ranking     INTEGER,
        wc_group         TEXT,
        seed             INTEGER DEFAULT 0,
        goals_scored_avg REAL    DEFAULT 1.5,
        goals_conceded_avg REAL  DEFAULT 1.2,
        possession_avg   REAL    DEFAULT 50.0,
        formation        TEXT    DEFAULT '4-3-3',
        pressing_intensity REAL  DEFAULT 5.0,
        defensive_line   TEXT    DEFAULT 'medium',
        tactical_style   TEXT    DEFAULT 'balanced'
    )""")

    # --- team_matches ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS team_matches (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id         INTEGER NOT NULL REFERENCES teams(id),
        opponent_id     INTEGER REFERENCES teams(id),
        opponent_name   TEXT    NOT NULL,
        date            TEXT    NOT NULL,
        competition     TEXT,
        goals_for       INTEGER DEFAULT 0,
        goals_against   INTEGER DEFAULT 0,
        result          TEXT    CHECK(result IN ('W','D','L')),
        venue           TEXT    CHECK(venue IN ('home','away','neutral')),
        wc_edition      INTEGER
    )""")

    # --- wc_history ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wc_history (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id             INTEGER NOT NULL REFERENCES teams(id),
        year                INTEGER NOT NULL,
        wc_group            TEXT,
        group_stage_result  TEXT,
        round_reached       TEXT,
        goals_scored        INTEGER DEFAULT 0,
        goals_conceded      INTEGER DEFAULT 0,
        matches_played      INTEGER DEFAULT 0,
        UNIQUE(team_id, year)
    )""")

    # --- players ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        team_id         INTEGER NOT NULL REFERENCES teams(id),
        position        TEXT    CHECK(position IN ('GK','DEF','MID','FWD')),
        club            TEXT,
        club_league     TEXT,
        age             INTEGER,
        caps            INTEGER DEFAULT 0,
        goals_as_nat    INTEGER DEFAULT 0,
        preferred_foot  TEXT,
        height_cm       INTEGER,
        market_value_m  REAL,
        UNIQUE(name, team_id)
    )""")

    # --- player_club_stats ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_club_stats (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id           INTEGER NOT NULL REFERENCES players(id),
        season              TEXT    NOT NULL,
        league              TEXT,
        club                TEXT,
        matches             INTEGER DEFAULT 0,
        minutes             INTEGER DEFAULT 0,
        goals               INTEGER DEFAULT 0,
        assists             INTEGER DEFAULT 0,
        shots_on_target     INTEGER DEFAULT 0,
        pass_accuracy       REAL    DEFAULT 0.0,
        dribbles_completed  INTEGER DEFAULT 0,
        tackles             INTEGER DEFAULT 0,
        interceptions       INTEGER DEFAULT 0,
        yellow_cards        INTEGER DEFAULT 0,
        red_cards           INTEGER DEFAULT 0,
        xg                  REAL    DEFAULT 0.0,
        xa                  REAL    DEFAULT 0.0,
        UNIQUE(player_id, season, club)
    )""")

    # --- player_nat_stats ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_nat_stats (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id   INTEGER NOT NULL REFERENCES players(id),
        match_id    INTEGER REFERENCES team_matches(id),
        match_date  TEXT,
        opponent    TEXT,
        minutes     INTEGER DEFAULT 0,
        goals       INTEGER DEFAULT 0,
        assists     INTEGER DEFAULT 0,
        rating      REAL,
        was_starter INTEGER DEFAULT 0
    )""")

    # --- player_ratings ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS player_ratings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id   INTEGER NOT NULL REFERENCES players(id),
        match_id    INTEGER,
        context     TEXT    CHECK(context IN ('club','nat')),
        rating      REAL    CHECK(rating BETWEEN 0 AND 10),
        components  TEXT,   -- JSON blob
        computed_at TEXT    DEFAULT (datetime('now'))
    )""")

    # --- squad_selections ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS squad_selections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id     INTEGER NOT NULL REFERENCES teams(id),
        player_id   INTEGER NOT NULL REFERENCES players(id),
        confirmed   INTEGER DEFAULT 1,
        shirt_number INTEGER,
        UNIQUE(team_id, player_id)
    )""")

    # --- match_lineups ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS match_lineups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id    INTEGER NOT NULL REFERENCES wc_matches(id),
        team_id     INTEGER NOT NULL REFERENCES teams(id),
        player_id   INTEGER NOT NULL REFERENCES players(id),
        position    TEXT,
        starter     INTEGER DEFAULT 1
    )""")

    # --- wc_matches ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wc_matches (
        id              INTEGER PRIMARY KEY,
        date            TEXT,
        time            TEXT,
        home_team_id    INTEGER REFERENCES teams(id),
        away_team_id    INTEGER REFERENCES teams(id),
        home_team_name  TEXT,
        away_team_name  TEXT,
        venue           TEXT,
        city            TEXT,
        wc_group        TEXT,
        stage           TEXT,
        score_home      INTEGER,
        score_away      INTEGER,
        played          INTEGER DEFAULT 0
    )""")

    conn.commit()
    print("  Tablas creadas correctamente.")


def seed_teams(conn: sqlite3.Connection):
    teams_path = STATIC_DIR / "teams_wc2026.json"
    if not teams_path.exists():
        print("  Advertencia: teams_wc2026.json no encontrado. Saltando seed de equipos.")
        return

    with open(teams_path) as f:
        data = json.load(f)

    # Default team attributes based on confederation and ranking
    style_map = {
        "CONMEBOL": ("high", "attacking", 6.5, "4-3-3"),
        "UEFA": ("medium", "possession", 6.0, "4-2-3-1"),
        "CONCACAF": ("medium", "counter", 5.5, "4-4-2"),
        "CAF": ("high", "physical", 5.5, "4-3-3"),
        "AFC": ("medium", "disciplined", 5.0, "4-5-1"),
        "OFC": ("low", "defensive", 4.5, "4-4-2"),
    }

    cur = conn.cursor()
    inserted = 0
    for t in data["teams"]:
        conf = t.get("confederation", "UEFA")
        ranking = t.get("fifa_ranking", 50)
        d_line, style, pressing, formation = style_map.get(conf, ("medium", "balanced", 5.0, "4-3-3"))

        # Adjust goals avg by ranking
        goals_avg = max(0.8, 2.0 - (ranking - 1) * 0.012)
        conceded_avg = min(2.5, 0.8 + (ranking - 1) * 0.015)
        poss_avg = max(38.0, 58.0 - (ranking - 1) * 0.2)

        cur.execute("""
            INSERT OR IGNORE INTO teams
                (id, name, slug, confederation, fifa_ranking, wc_group, seed,
                 goals_scored_avg, goals_conceded_avg, possession_avg,
                 formation, pressing_intensity, defensive_line, tactical_style)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t["id"], t["name"], t["slug"], conf,
            ranking, t.get("group"), int(t.get("seed", False)),
            round(goals_avg, 2), round(conceded_avg, 2), round(poss_avg, 1),
            formation, pressing, d_line, style
        ))
        inserted += cur.rowcount

    conn.commit()
    print(f"  Equipos sembrados: {inserted} insertados.")


def seed_wc_history(conn: sqlite3.Connection):
    hist_path = STATIC_DIR / "wc_history.json"
    if not hist_path.exists():
        print("  Advertencia: wc_history.json no encontrado.")
        return

    with open(hist_path) as f:
        data = json.load(f)

    cur = conn.cursor()
    inserted = 0
    for entry in data["history"]:
        # Get team_id
        row = cur.execute("SELECT id FROM teams WHERE slug=?", (entry["slug"],)).fetchone()
        if not row:
            continue
        team_id = row["id"]

        for ed in entry["editions"]:
            cur.execute("""
                INSERT OR IGNORE INTO wc_history
                    (team_id, year, wc_group, group_stage_result, round_reached,
                     goals_scored, goals_conceded, matches_played)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                team_id, ed["year"], ed.get("group"), ed.get("group_stage_result"),
                ed.get("round_reached"), ed.get("goals_scored", 0),
                ed.get("goals_conceded", 0), ed.get("matches_played", 0)
            ))
            inserted += cur.rowcount

    conn.commit()
    print(f"  Historial WC sembrado: {inserted} registros.")


def seed_wc_matches(conn: sqlite3.Connection):
    sched_path = STATIC_DIR / "schedule_wc2026.json"
    if not sched_path.exists():
        print("  Advertencia: schedule_wc2026.json no encontrado.")
        return

    with open(sched_path) as f:
        data = json.load(f)

    cur = conn.cursor()

    # Build name->id map
    team_map = {}
    for row in cur.execute("SELECT id, name FROM teams"):
        team_map[row["name"]] = row["id"]

    def find_team_id(name):
        if name in team_map:
            return team_map[name]
        # fuzzy match
        for k, v in team_map.items():
            if name.lower() in k.lower() or k.lower() in name.lower():
                return v
        return None

    inserted = 0
    all_matches = []

    # Collect from group_stage
    if "group_stage" in data:
        all_matches.extend(data["group_stage"].get("matches", []))
    # Collect from knockout stages
    for stage_key in ["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "third_place", "final"]:
        if stage_key in data:
            all_matches.extend(data[stage_key].get("matches", []))

    for m in all_matches:
        home_id = find_team_id(m.get("home", ""))
        away_id = find_team_id(m.get("away", ""))
        cur.execute("""
            INSERT OR IGNORE INTO wc_matches
                (id, date, time, home_team_id, away_team_id, home_team_name, away_team_name,
                 venue, city, wc_group, stage, played)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,0)
        """, (
            m["id"], m.get("date"), m.get("time"),
            home_id, away_id,
            m.get("home"), m.get("away"),
            m.get("venue"), m.get("city"),
            m.get("group"), m.get("stage", "group")
        ))
        inserted += cur.rowcount

    conn.commit()
    print(f"  Partidos WC2026 sembrados: {inserted} registros.")


def seed_sample_players(conn: sqlite3.Connection):
    """Seed representative squad data for all 48 teams."""
    cur = conn.cursor()

    # Key players per team: (name, position, club, league, age, caps, goals)
    team_squads = {
        "Argentina": [
            ("Emiliano Martinez", "GK", "Aston Villa", "Premier League", 32, 45, 0),
            ("Nahuel Molina", "DEF", "Atletico Madrid", "La Liga", 27, 45, 5),
            ("Cristian Romero", "DEF", "Tottenham", "Premier League", 26, 35, 3),
            ("Nicolas Otamendi", "DEF", "Benfica", "Primeira Liga", 37, 105, 8),
            ("Marcos Acuna", "DEF", "Sevilla", "La Liga", 33, 65, 3),
            ("Rodrigo De Paul", "MID", "Atletico Madrid", "La Liga", 31, 72, 13),
            ("Alexis Mac Allister", "MID", "Liverpool", "Premier League", 26, 42, 10),
            ("Enzo Fernandez", "MID", "Chelsea", "Premier League", 24, 35, 5),
            ("Angel Di Maria", "MID", "Benfica", "Primeira Liga", 37, 145, 31),
            ("Julian Alvarez", "FWD", "Atletico Madrid", "La Liga", 25, 45, 22),
            ("Lautaro Martinez", "FWD", "Inter Milan", "Serie A", 27, 65, 30),
        ],
        "France": [
            ("Mike Maignan", "GK", "AC Milan", "Serie A", 29, 25, 0),
            ("Jules Kounde", "DEF", "Barcelona", "La Liga", 26, 42, 1),
            ("Dayot Upamecano", "DEF", "Bayern Munich", "Bundesliga", 26, 42, 2),
            ("William Saliba", "DEF", "Arsenal", "Premier League", 23, 25, 1),
            ("Theo Hernandez", "DEF", "AC Milan", "Serie A", 27, 38, 5),
            ("Aurelien Tchouameni", "MID", "Real Madrid", "La Liga", 24, 38, 4),
            ("Adrien Rabiot", "MID", "Juventus", "Serie A", 29, 45, 12),
            ("Antoine Griezmann", "MID", "Atletico Madrid", "La Liga", 33, 132, 44),
            ("Ousmane Dembele", "FWD", "PSG", "Ligue 1", 27, 45, 12),
            ("Kylian Mbappe", "FWD", "Real Madrid", "La Liga", 27, 82, 48),
            ("Marcus Thuram", "FWD", "Inter Milan", "Serie A", 27, 35, 12),
        ],
        "Brazil": [
            ("Alisson", "GK", "Liverpool", "Premier League", 32, 78, 0),
            ("Danilo", "DEF", "Juventus", "Serie A", 33, 85, 8),
            ("Marquinhos", "DEF", "PSG", "Ligue 1", 30, 82, 12),
            ("Gabriel Magalhaes", "DEF", "Arsenal", "Premier League", 27, 35, 5),
            ("Renan Lodi", "DEF", "Nottm Forest", "Premier League", 26, 25, 2),
            ("Bruno Guimaraes", "MID", "Newcastle", "Premier League", 27, 42, 8),
            ("Lucas Paqueta", "MID", "West Ham", "Premier League", 27, 55, 12),
            ("Casemiro", "MID", "Man United", "Premier League", 32, 85, 9),
            ("Rodrygo", "FWD", "Real Madrid", "La Liga", 24, 38, 15),
            ("Vinicius Junior", "FWD", "Real Madrid", "La Liga", 24, 55, 22),
            ("Gabriel Martinelli", "FWD", "Arsenal", "Premier League", 23, 32, 8),
        ],
        "England": [
            ("Jordan Pickford", "GK", "Everton", "Premier League", 30, 65, 0),
            ("Kyle Walker", "DEF", "Man City", "Premier League", 34, 82, 1),
            ("John Stones", "DEF", "Man City", "Premier League", 30, 70, 3),
            ("Harry Maguire", "DEF", "Man United", "Premier League", 31, 65, 7),
            ("Luke Shaw", "DEF", "Man United", "Premier League", 29, 35, 3),
            ("Declan Rice", "MID", "Arsenal", "Premier League", 26, 55, 5),
            ("Jude Bellingham", "MID", "Real Madrid", "La Liga", 21, 45, 15),
            ("Phil Foden", "MID", "Man City", "Premier League", 24, 42, 10),
            ("Bukayo Saka", "FWD", "Arsenal", "Premier League", 23, 42, 12),
            ("Harry Kane", "FWD", "Bayern Munich", "Bundesliga", 31, 95, 68),
            ("Marcus Rashford", "FWD", "Man United", "Premier League", 27, 62, 17),
        ],
        "Germany": [
            ("Manuel Neuer", "GK", "Bayern Munich", "Bundesliga", 39, 120, 1),
            ("Benjamin Pavard", "DEF", "Inter Milan", "Serie A", 28, 52, 4),
            ("Antonio Rudiger", "DEF", "Real Madrid", "La Liga", 31, 75, 3),
            ("Jonathan Tah", "DEF", "Bayer Leverkusen", "Bundesliga", 28, 30, 2),
            ("David Raum", "DEF", "RB Leipzig", "Bundesliga", 26, 30, 5),
            ("Leon Goretzka", "MID", "Bayern Munich", "Bundesliga", 29, 55, 15),
            ("Florian Wirtz", "MID", "Bayer Leverkusen", "Bundesliga", 21, 25, 8),
            ("Jamal Musiala", "MID", "Bayern Munich", "Bundesliga", 22, 35, 12),
            ("Leroy Sane", "FWD", "Bayern Munich", "Bundesliga", 29, 60, 15),
            ("Niclas Fullkrug", "FWD", "West Ham", "Premier League", 31, 25, 12),
            ("Kai Havertz", "FWD", "Arsenal", "Premier League", 25, 55, 22),
        ],
        "Spain": [
            ("David Raya", "GK", "Arsenal", "Premier League", 29, 18, 0),
            ("Dani Carvajal", "DEF", "Real Madrid", "La Liga", 32, 70, 6),
            ("Pau Cubarsi", "DEF", "Barcelona", "La Liga", 18, 10, 0),
            ("Aymeric Laporte", "DEF", "Al-Nassr", "Saudi Pro League", 30, 42, 2),
            ("Marc Cucurella", "DEF", "Chelsea", "Premier League", 26, 30, 2),
            ("Rodri", "MID", "Man City", "Premier League", 28, 55, 7),
            ("Pedri", "MID", "Barcelona", "La Liga", 22, 35, 6),
            ("Fabian Ruiz", "MID", "PSG", "Ligue 1", 28, 38, 12),
            ("Lamine Yamal", "FWD", "Barcelona", "La Liga", 17, 20, 7),
            ("Alvaro Morata", "FWD", "AC Milan", "Serie A", 32, 75, 36),
            ("Nico Williams", "FWD", "Athletic Club", "La Liga", 22, 22, 5),
        ],
        "Portugal": [
            ("Diogo Costa", "GK", "Porto", "Primeira Liga", 25, 25, 0),
            ("Joao Cancelo", "DEF", "Barcelona", "La Liga", 30, 62, 4),
            ("Ruben Dias", "DEF", "Man City", "Premier League", 27, 55, 3),
            ("Pepe", "DEF", "Porto", "Primeira Liga", 41, 142, 8),
            ("Nuno Mendes", "DEF", "PSG", "Ligue 1", 22, 28, 2),
            ("Bernardo Silva", "MID", "Man City", "Premier League", 30, 82, 22),
            ("Bruno Fernandes", "MID", "Man United", "Premier League", 30, 82, 32),
            ("Joao Neves", "MID", "PSG", "Ligue 1", 20, 18, 3),
            ("Rafael Leao", "FWD", "AC Milan", "Serie A", 25, 38, 8),
            ("Cristiano Ronaldo", "FWD", "Al-Nassr", "Saudi Pro League", 41, 215, 130),
            ("Gonçalo Ramos", "FWD", "PSG", "Ligue 1", 23, 22, 8),
        ],
        "Netherlands": [
            ("Bart Verbruggen", "GK", "Brighton", "Premier League", 22, 18, 0),
            ("Denzel Dumfries", "DEF", "Inter Milan", "Serie A", 28, 55, 12),
            ("Virgil van Dijk", "DEF", "Liverpool", "Premier League", 33, 75, 8),
            ("Nathan Ake", "DEF", "Man City", "Premier League", 30, 45, 4),
            ("Jorrel Hato", "DEF", "Ajax", "Eredivisie", 18, 8, 0),
            ("Ryan Gravenberch", "MID", "Liverpool", "Premier League", 22, 28, 3),
            ("Tijjani Reijnders", "MID", "AC Milan", "Serie A", 26, 22, 5),
            ("Teun Koopmeiners", "MID", "Juventus", "Serie A", 26, 30, 10),
            ("Xavi Simons", "FWD", "PSG", "Ligue 1", 22, 22, 8),
            ("Memphis Depay", "FWD", "Atletico Madrid", "La Liga", 30, 88, 46),
            ("Cody Gakpo", "FWD", "Liverpool", "Premier League", 25, 40, 15),
        ],
        "Croatia": [
            ("Dominik Livakovic", "GK", "Fenerbahce", "Süper Lig", 29, 48, 0),
            ("Josip Stanisic", "DEF", "Bayer Leverkusen", "Bundesliga", 24, 22, 1),
            ("Josko Gvardiol", "DEF", "Man City", "Premier League", 22, 38, 3),
            ("Duje Caleta-Car", "DEF", "Lyon", "Ligue 1", 28, 45, 2),
            ("Borna Sosa", "DEF", "Ajax", "Eredivisie", 26, 38, 5),
            ("Luka Modric", "MID", "Real Madrid", "La Liga", 39, 172, 25),
            ("Mateo Kovacic", "MID", "Man City", "Premier League", 30, 95, 7),
            ("Marcelo Brozovic", "MID", "Al-Nassr", "Saudi Pro League", 32, 105, 17),
            ("Ivan Perisic", "FWD", "Hajduk Split", "HNL", 35, 128, 33),
            ("Andrej Kramaric", "FWD", "Hoffenheim", "Bundesliga", 33, 85, 36),
            ("Bruno Petkovic", "FWD", "Dinamo Zagreb", "HNL", 31, 42, 12),
        ],
        "Morocco": [
            ("Yassine Bounou", "GK", "Al-Hilal", "Saudi Pro League", 33, 65, 0),
            ("Achraf Hakimi", "DEF", "PSG", "Ligue 1", 26, 62, 12),
            ("Romain Saiss", "DEF", "Besiktas", "Süper Lig", 34, 75, 8),
            ("Nayef Aguerd", "DEF", "West Ham", "Premier League", 28, 42, 5),
            ("Noussair Mazraoui", "DEF", "Man United", "Premier League", 26, 38, 5),
            ("Sofyan Amrabat", "MID", "Man United", "Premier League", 28, 48, 3),
            ("Azzedine Ounahi", "MID", "Marseille", "Ligue 1", 24, 32, 5),
            ("Bilal El Khannouss", "MID", "Leicester", "Championship", 21, 22, 5),
            ("Hakim Ziyech", "FWD", "Galatasaray", "Süper Lig", 32, 62, 22),
            ("Youssef En-Nesyri", "FWD", "Fenerbahce", "Süper Lig", 27, 58, 25),
            ("Sofiane Boufal", "FWD", "Al-Qadsiah", "Saudi Pro League", 31, 45, 12),
        ],
        "Japan": [
            ("Shuichi Gonda", "GK", "Shimizu S-Pulse", "J1 League", 35, 48, 0),
            ("Hiroki Sakai", "DEF", "Urawa Reds", "J1 League", 34, 72, 5),
            ("Ko Itakura", "DEF", "Borussia M'gladbach", "Bundesliga", 27, 32, 3),
            ("Takehiro Tomiyasu", "DEF", "Arsenal", "Premier League", 26, 45, 1),
            ("Yuto Nagatomo", "DEF", "Tokyo FC", "J1 League", 38, 142, 8),
            ("Wataru Endo", "MID", "Liverpool", "Premier League", 31, 55, 12),
            ("Hidemasa Morita", "MID", "Sporting CP", "Primeira Liga", 29, 38, 5),
            ("Gaku Shibasaki", "MID", "Leganes", "La Liga", 32, 52, 8),
            ("Kaoru Mitoma", "FWD", "Brighton", "Premier League", 27, 42, 15),
            ("Takumi Minamino", "FWD", "AS Monaco", "Ligue 1", 30, 72, 25),
            ("Ayase Ueda", "FWD", "Feyenoord", "Eredivisie", 26, 28, 12),
        ],
        "USA": [
            ("Matt Turner", "GK", "Nottm Forest", "Premier League", 30, 38, 0),
            ("Sergino Dest", "DEF", "PSV Eindhoven", "Eredivisie", 24, 35, 5),
            ("Tim Ream", "DEF", "Fulham", "Premier League", 37, 72, 2),
            ("Chris Richards", "DEF", "Crystal Palace", "Premier League", 25, 22, 1),
            ("Antonee Robinson", "DEF", "Fulham", "Premier League", 27, 45, 3),
            ("Tyler Adams", "MID", "Bournemouth", "Premier League", 26, 55, 2),
            ("Weston McKennie", "MID", "Juventus", "Serie A", 26, 62, 12),
            ("Yunus Musah", "MID", "AC Milan", "Serie A", 22, 42, 4),
            ("Christian Pulisic", "FWD", "AC Milan", "Serie A", 26, 82, 27),
            ("Folarin Balogun", "FWD", "Monaco", "Ligue 1", 23, 28, 8),
            ("Josh Sargent", "FWD", "Norwich", "Championship", 24, 38, 10),
        ],
        "Mexico": [
            ("Guillermo Ochoa", "GK", "Club America", "Liga MX", 39, 145, 0),
            ("Jorge Sanchez", "DEF", "Ajax", "Eredivisie", 26, 38, 2),
            ("Nestor Araujo", "DEF", "Club America", "Liga MX", 33, 72, 4),
            ("Johan Vasquez", "DEF", "Genoa", "Serie A", 26, 32, 3),
            ("Jesus Gallardo", "DEF", "Monterrey", "Liga MX", 30, 65, 4),
            ("Edson Alvarez", "MID", "West Ham", "Premier League", 27, 72, 8),
            ("Carlos Rodriguez", "MID", "Cruz Azul", "Liga MX", 27, 42, 5),
            ("Andres Guardado", "MID", "Real Betis", "La Liga", 38, 182, 28),
            ("Hirving Lozano", "FWD", "PSV Eindhoven", "Eredivisie", 29, 82, 29),
            ("Raul Jimenez", "FWD", "Fulham", "Premier League", 33, 105, 40),
            ("Santiago Gimenez", "FWD", "AC Milan", "Serie A", 23, 28, 12),
        ],
        "Panama": [
            ("Luis Mejia", "GK", "Independiente", "Primera Division", 27, 38, 0),
            ("Michael Amir Murillo", "DEF", "Marseille", "Ligue 1", 28, 55, 2),
            ("Fidel Escobar", "DEF", "New York Red Bulls", "MLS", 27, 45, 3),
            ("Harold Cummings", "DEF", "Santos Laguna", "Liga MX", 32, 72, 5),
            ("Roderick Miller", "DEF", "CD Tenerife", "La Liga 2", 31, 65, 2),
            ("Adalberto Carrasquilla", "MID", "Hajduk Split", "HNL", 25, 48, 5),
            ("Andres Andrade", "MID", "Houston Dynamo", "MLS", 33, 75, 10),
            ("Anibal Godoy", "MID", "Nashville SC", "MLS", 36, 95, 5),
            ("Rolando Blackburn", "FWD", "Club Necaxa", "Liga MX", 30, 45, 12),
            ("Ismael Diaz", "FWD", "Lille", "Ligue 1", 22, 22, 5),
            ("Jose Fajardo", "FWD", "FC Dallas", "MLS", 25, 35, 8),
        ],
        "Colombia": [
            ("David Ospina", "GK", "Al-Qadsiah", "Saudi Pro League", 35, 125, 0),
            ("Daniel Munoz", "DEF", "Crystal Palace", "Premier League", 28, 38, 5),
            ("Davinson Sanchez", "DEF", "Galatasaray", "Süper Lig", 28, 65, 3),
            ("Yerry Mina", "DEF", "Fiorentina", "Serie A", 29, 72, 11),
            ("Johan Mojica", "DEF", "Villarreal", "La Liga", 31, 45, 3),
            ("Richard Rios", "MID", "Palmeiras", "Brasileirao", 24, 28, 5),
            ("Jhon Arias", "MID", "Fluminense", "Brasileirao", 27, 32, 8),
            ("Juan Cuadrado", "MID", "Inter Milan", "Serie A", 36, 115, 24),
            ("Luis Diaz", "FWD", "Liverpool", "Premier League", 27, 55, 18),
            ("James Rodriguez", "FWD", "Rayo Vallecano", "La Liga", 33, 102, 29),
            ("Jhon Duran", "FWD", "Aston Villa", "Premier League", 21, 18, 5),
        ],
        "Uruguay": [
            ("Sergio Rochet", "GK", "Nacional", "Primera Division", 30, 38, 0),
            ("Nahitan Nandez", "DEF", "Cagliari", "Serie A", 28, 52, 4),
            ("Diego Godin", "DEF", "Nacional", "Primera Division", 38, 165, 17),
            ("Sebastian Caceres", "DEF", "Club America", "Liga MX", 26, 32, 3),
            ("Matias Vina", "DEF", "AS Roma", "Serie A", 27, 42, 3),
            ("Federico Valverde", "MID", "Real Madrid", "La Liga", 26, 58, 12),
            ("Rodrigo Bentancur", "MID", "Tottenham", "Premier League", 27, 58, 8),
            ("Lucas Torreira", "MID", "Galatasaray", "Süper Lig", 28, 65, 8),
            ("Facundo Pellistri", "FWD", "Man United", "Premier League", 23, 28, 5),
            ("Darwin Nunez", "FWD", "Liverpool", "Premier League", 25, 48, 18),
            ("Luis Suarez", "FWD", "River Plate", "Primera Division", 37, 142, 68),
        ],
        "Senegal": [
            ("Edouard Mendy", "GK", "Al-Ahli", "Saudi Pro League", 32, 45, 0),
            ("Youcef Sabaly", "DEF", "Real Betis", "La Liga", 32, 42, 2),
            ("Kalidou Koulibaly", "DEF", "Al-Hilal", "Saudi Pro League", 33, 80, 6),
            ("Abdou Diallo", "DEF", "RB Leipzig", "Bundesliga", 27, 45, 4),
            ("Ismail Jakobs", "DEF", "Monaco", "Ligue 1", 25, 28, 3),
            ("Idrissa Gueye", "MID", "Everton", "Premier League", 35, 92, 5),
            ("Nampalys Mendy", "MID", "Leicester", "Championship", 33, 52, 2),
            ("Pape Matar Sarr", "MID", "Tottenham", "Premier League", 22, 28, 5),
            ("Sadio Mane", "FWD", "Al-Nassr", "Saudi Pro League", 32, 105, 38),
            ("Ismaila Sarr", "FWD", "Crystal Palace", "Premier League", 26, 55, 22),
            ("Habib Diallo", "FWD", "Strasbourg", "Ligue 1", 28, 38, 15),
        ],
        "Switzerland": [
            ("Yann Sommer", "GK", "Inter Milan", "Serie A", 35, 95, 0),
            ("Silvan Widmer", "DEF", "Mainz", "Bundesliga", 31, 42, 5),
            ("Manuel Akanji", "DEF", "Man City", "Premier League", 29, 62, 4),
            ("Fabian Schar", "DEF", "Newcastle", "Premier League", 32, 68, 8),
            ("Ricardo Rodriguez", "DEF", "Torino", "Serie A", 32, 95, 12),
            ("Granit Xhaka", "MID", "Bayer Leverkusen", "Bundesliga", 31, 118, 22),
            ("Remo Freuler", "MID", "Nottm Forest", "Premier League", 32, 65, 8),
            ("Denis Zakaria", "MID", "Monaco", "Ligue 1", 27, 38, 5),
            ("Xherdan Shaqiri", "FWD", "Chicago Fire", "MLS", 32, 105, 32),
            ("Breel Embolo", "FWD", "Monaco", "Ligue 1", 27, 62, 18),
            ("Ruben Vargas", "FWD", "Augsburg", "Bundesliga", 25, 35, 10),
        ],
        "South Korea": [
            ("Kim Seung-gyu", "GK", "Vissel Kobe", "J1 League", 33, 65, 0),
            ("Kim Moon-hwan", "DEF", "Jeonbuk", "K League 1", 29, 35, 2),
            ("Kim Min-jae", "DEF", "Bayern Munich", "Bundesliga", 28, 65, 6),
            ("Jung Seung-hyun", "DEF", "Al-Shabab", "Saudi Pro League", 30, 42, 2),
            ("Kim Jin-su", "DEF", "Jeonbuk", "K League 1", 31, 55, 3),
            ("Jung Woo-young", "MID", "Al-Qadsiah", "Saudi Pro League", 33, 72, 2),
            ("Hwang In-beom", "MID", "Feyenoord", "Eredivisie", 28, 55, 8),
            ("Lee Jae-sung", "MID", "Mainz", "Bundesliga", 32, 65, 12),
            ("Son Heung-min", "FWD", "Tottenham", "Premier League", 32, 125, 40),
            ("Hwang Hee-chan", "FWD", "Wolverhampton", "Premier League", 28, 62, 18),
            ("Cho Gue-sung", "FWD", "Celta Vigo", "La Liga", 26, 35, 10),
        ],
        "Ecuador": [
            ("Hernan Galindez", "GK", "Aucas", "Serie A Ecuador", 36, 42, 0),
            ("Angelo Preciado", "DEF", "Genk", "Pro League", 25, 38, 3),
            ("Piero Hincapie", "DEF", "Bayer Leverkusen", "Bundesliga", 22, 38, 2),
            ("Felix Torres", "DEF", "Santos Laguna", "Liga MX", 27, 42, 3),
            ("Pervis Estupinan", "DEF", "Brighton", "Premier League", 26, 48, 5),
            ("Carlos Gruezo", "MID", "FC Augsburg", "Bundesliga", 30, 62, 3),
            ("Jhegson Mendez", "MID", "LA Galaxy", "MLS", 27, 42, 5),
            ("Moises Caicedo", "MID", "Chelsea", "Premier League", 23, 42, 4),
            ("Jeremy Sarmiento", "FWD", "Brighton", "Premier League", 22, 25, 5),
            ("Enner Valencia", "FWD", "Internacional", "Brasileirao", 34, 82, 38),
            ("Leonardo Campana", "FWD", "Inter Miami", "MLS", 24, 32, 10),
        ],
        "Australia": [
            ("Mat Ryan", "GK", "Real Sociedad", "La Liga", 32, 78, 0),
            ("Nathaniel Atkinson", "DEF", "Hearts", "Scottish Prem", 24, 22, 2),
            ("Harry Souttar", "DEF", "Leicester", "Championship", 25, 32, 5),
            ("Kye Rowles", "DEF", "Hearts", "Scottish Prem", 26, 22, 2),
            ("Aziz Behich", "DEF", "Dundee United", "Scottish Prem", 32, 55, 3),
            ("Jackson Irvine", "MID", "St. Pauli", "Bundesliga", 31, 68, 10),
            ("Riley McGree", "MID", "Middlesbrough", "Championship", 25, 28, 5),
            ("Massimo Luongo", "MID", "Ipswich", "Championship", 32, 68, 5),
            ("Mathew Leckie", "FWD", "Melbourne City", "A-League", 33, 85, 15),
            ("Mitchell Duke", "FWD", "Fagiano Okayama", "J2 League", 33, 38, 12),
            ("Martin Boyle", "FWD", "Al-Faisaly", "Saudi First Division", 31, 42, 12),
        ],
        "Poland": [
            ("Wojciech Szczesny", "GK", "Barcelona", "La Liga", 34, 85, 0),
            ("Bartosz Bereszynski", "DEF", "Sampdoria", "Serie B", 31, 52, 2),
            ("Kamil Glik", "DEF", "Benevento", "Serie B", 36, 98, 8),
            ("Jan Bednarek", "DEF", "Southampton", "Championship", 28, 55, 5),
            ("Tymoteusz Puchacz", "DEF", "Kaiserslautern", "2. Bundesliga", 25, 28, 2),
            ("Krystian Bielik", "MID", "Birmingham", "Championship", 26, 28, 3),
            ("Grzegorz Krychowiak", "MID", "Al-Shabab", "Saudi Pro League", 34, 102, 5),
            ("Piotr Zielinski", "MID", "Inter Milan", "Serie A", 30, 85, 22),
            ("Kamil Grosicki", "FWD", "Pogoń Szczecin", "Ekstraklasa", 36, 88, 18),
            ("Robert Lewandowski", "FWD", "Barcelona", "La Liga", 36, 148, 82),
            ("Arkadiusz Milik", "FWD", "Juventus", "Serie A", 30, 72, 36),
        ],
        "Serbia": [
            ("Predrag Rajkovic", "GK", "Real Mallorca", "La Liga", 29, 42, 0),
            ("Strahinja Pavlovic", "DEF", "RB Salzburg", "Austrian Bundesliga", 23, 28, 3),
            ("Nikola Milenkovic", "DEF", "Nottm Forest", "Premier League", 26, 52, 5),
            ("Milos Veljkovic", "DEF", "Werder Bremen", "Bundesliga", 29, 35, 2),
            ("Filip Kostic", "DEF", "Juventus", "Serie A", 31, 68, 12),
            ("Sergej Milinkovic-Savic", "MID", "Al-Hilal", "Saudi Pro League", 29, 62, 18),
            ("Nemanja Matic", "MID", "Rennes", "Ligue 1", 36, 98, 8),
            ("Sasa Lukic", "MID", "Fulham", "Premier League", 28, 38, 5),
            ("Andrija Zivkovic", "FWD", "PAOK", "Super League Greece", 28, 45, 10),
            ("Aleksandar Mitrovic", "FWD", "Al-Hilal", "Saudi Pro League", 29, 82, 55),
            ("Dusan Vlahovic", "FWD", "Juventus", "Serie A", 24, 38, 22),
        ],
        "Nigeria": [
            ("Francis Uzoho", "GK", "Omonia", "Cyta Championship", 26, 25, 0),
            ("Ola Aina", "DEF", "Nottm Forest", "Premier League", 28, 48, 3),
            ("William Troost-Ekong", "DEF", "Watford", "Championship", 31, 68, 8),
            ("Leon Balogun", "DEF", "Rangers", "Scottish Prem", 35, 68, 2),
            ("Zaidu Sanusi", "DEF", "Porto", "Primeira Liga", 26, 32, 2),
            ("Wilfred Ndidi", "MID", "Leicester", "Championship", 27, 72, 5),
            ("Frank Onyeka", "MID", "Brentford", "Premier League", 26, 28, 3),
            ("Alex Iwobi", "MID", "Fulham", "Premier League", 28, 72, 10),
            ("Samuel Chukwueze", "FWD", "AC Milan", "Serie A", 25, 52, 12),
            ("Victor Osimhen", "FWD", "Napoli", "Serie A", 25, 48, 22),
            ("Ademola Lookman", "FWD", "Atalanta", "Serie A", 26, 28, 8),
        ],
        "Turkey": [
            ("Altay Bayindir", "GK", "Man United", "Premier League", 26, 18, 0),
            ("Zeki Celik", "DEF", "AS Roma", "Serie A", 27, 42, 2),
            ("Merih Demiral", "DEF", "Al-Qadsiah", "Saudi Pro League", 26, 42, 5),
            ("Abdulkerim Bardakci", "DEF", "Galatasaray", "Süper Lig", 27, 28, 2),
            ("Ferdi Kadioglu", "DEF", "Fenerbahce", "Süper Lig", 24, 28, 3),
            ("Salih Ozcan", "MID", "Borussia Dortmund", "Bundesliga", 26, 22, 3),
            ("Hakan Calhanoglu", "MID", "Inter Milan", "Serie A", 30, 78, 22),
            ("Okay Yokuslu", "MID", "West Brom", "Championship", 30, 55, 3),
            ("Kerem Akturkoglu", "FWD", "Galatasaray", "Süper Lig", 25, 32, 10),
            ("Baris Yilmaz", "FWD", "Galatasaray", "Süper Lig", 24, 18, 5),
            ("Cenk Tosun", "FWD", "Besiktas", "Süper Lig", 33, 52, 28),
        ],
        "Belgium": [
            ("Koen Casteels", "GK", "Wolfsburg", "Bundesliga", 32, 42, 0),
            ("Timothy Castagne", "DEF", "Fulham", "Premier League", 28, 52, 4),
            ("Wout Faes", "DEF", "Leicester", "Championship", 26, 22, 2),
            ("Jan Vertonghen", "DEF", "Anderlecht", "First Division A", 37, 148, 10),
            ("Yannick Carrasco", "DEF", "Al-Qadsiah", "Saudi Pro League", 31, 78, 16),
            ("Amadou Onana", "MID", "Aston Villa", "Premier League", 23, 25, 2),
            ("Kevin De Bruyne", "MID", "Man City", "Premier League", 33, 105, 26),
            ("Axel Witsel", "MID", "Atletico Madrid", "La Liga", 35, 135, 12),
            ("Dries Mertens", "FWD", "Galatasaray", "Süper Lig", 37, 112, 21),
            ("Romelu Lukaku", "FWD", "AS Roma", "Serie A", 31, 112, 77),
            ("Leandro Trossard", "FWD", "Arsenal", "Premier League", 29, 28, 8),
        ],
        "Italy": [
            ("Gianluigi Donnarumma", "GK", "PSG", "Ligue 1", 26, 62, 0),
            ("Giovanni Di Lorenzo", "DEF", "Napoli", "Serie A", 30, 42, 3),
            ("Alessandro Bastoni", "DEF", "Inter Milan", "Serie A", 25, 38, 2),
            ("Gianluca Mancini", "DEF", "AS Roma", "Serie A", 28, 22, 3),
            ("Federico Dimarco", "DEF", "Inter Milan", "Serie A", 26, 30, 5),
            ("Nicolo Barella", "MID", "Inter Milan", "Serie A", 27, 62, 8),
            ("Marco Verratti", "MID", "Al-Arabi", "QSL", 32, 116, 8),
            ("Davide Frattesi", "MID", "Inter Milan", "Serie A", 24, 22, 5),
            ("Federico Chiesa", "FWD", "Liverpool", "Premier League", 26, 45, 15),
            ("Giacomo Raspadori", "FWD", "Napoli", "Serie A", 24, 22, 8),
            ("Ciro Immobile", "FWD", "Besiktas", "Süper Lig", 34, 68, 20),
        ],
        "Denmark": [
            ("Kasper Schmeichel", "GK", "Nice", "Ligue 1", 37, 112, 1),
            ("Daniel Wass", "DEF", "Club Brugge", "Pro League", 34, 72, 5),
            ("Simon Kjaer", "DEF", "AC Milan", "Serie A", 35, 112, 10),
            ("Andreas Christensen", "DEF", "Barcelona", "La Liga", 28, 68, 3),
            ("Joakim Maehle", "DEF", "Atalanta", "Serie A", 27, 45, 8),
            ("Pierre-Emile Hojbjerg", "MID", "Atletico Madrid", "La Liga", 28, 72, 12),
            ("Thomas Delaney", "MID", "Anderlecht", "First Division A", 32, 78, 5),
            ("Christian Eriksen", "MID", "Man United", "Premier League", 32, 122, 38),
            ("Andreas Cornelius", "FWD", "FC Copenhagen", "Superliga", 31, 45, 18),
            ("Rasmus Hojlund", "FWD", "Man United", "Premier League", 21, 20, 8),
            ("Jonas Wind", "FWD", "Wolfsburg", "Bundesliga", 25, 28, 10),
        ],
        "Austria": [
            ("Patrick Pentz", "GK", "Stade Reims", "Ligue 1", 27, 12, 0),
            ("Stefan Posch", "DEF", "Bologna", "Serie A", 27, 25, 2),
            ("Nicolas Seiwald", "DEF", "RB Leipzig", "Bundesliga", 23, 22, 3),
            ("Kevin Danso", "DEF", "Lens", "Ligue 1", 25, 22, 2),
            ("Philipp Mwene", "DEF", "PSV Eindhoven", "Eredivisie", 30, 35, 2),
            ("Florian Grillitsch", "MID", "Ajax", "Eredivisie", 28, 42, 3),
            ("Xaver Schlager", "MID", "RB Leipzig", "Bundesliga", 26, 42, 5),
            ("Konrad Laimer", "MID", "Bayern Munich", "Bundesliga", 26, 38, 5),
            ("Michael Gregoritsch", "FWD", "SC Freiburg", "Bundesliga", 29, 48, 18),
            ("Marcel Sabitzer", "FWD", "Borussia Dortmund", "Bundesliga", 30, 65, 18),
            ("Christoph Baumgartner", "FWD", "RB Leipzig", "Bundesliga", 24, 35, 12),
        ],
        "Ghana": [
            ("Lawrence Ati-Zigi", "GK", "St. Gallen", "Swiss Super League", 28, 32, 0),
            ("Tariq Lamptey", "DEF", "Brighton", "Premier League", 23, 22, 2),
            ("Daniel Amartey", "DEF", "Leicester", "Championship", 29, 42, 3),
            ("Alexander Djiku", "DEF", "Fenerbahce", "Süper Lig", 29, 38, 3),
            ("Gideon Mensah", "DEF", "Bordeaux", "Ligue 2", 25, 28, 2),
            ("Thomas Partey", "MID", "Arsenal", "Premier League", 31, 42, 12),
            ("Iddrisu Baba", "MID", "Real Mallorca", "La Liga", 28, 32, 2),
            ("Daniel-Kofi Kyereh", "MID", "St. Pauli", "Bundesliga", 28, 25, 5),
            ("Jordan Ayew", "FWD", "Crystal Palace", "Premier League", 32, 105, 22),
            ("Mohammed Kudus", "FWD", "West Ham", "Premier League", 23, 32, 10),
            ("Antoine Semenyo", "FWD", "Bournemouth", "Premier League", 24, 18, 5),
        ],
        "Hungary": [
            ("Peter Gulacsi", "GK", "RB Leipzig", "Bundesliga", 34, 98, 0),
            ("Adam Lang", "DEF", "Omonia", "Cyta Championship", 31, 42, 2),
            ("Endre Botka", "DEF", "Ferencvaros", "OTP Bank Liga", 30, 38, 2),
            ("Attila Szalai", "DEF", "Fenerbahce", "Süper Lig", 27, 42, 8),
            ("Loic Nego", "DEF", "Le Havre", "Ligue 1", 33, 35, 5),
            ("Adam Nagy", "MID", "Pisa", "Serie B", 29, 72, 5),
            ("Laszlo Kleinheisler", "MID", "Trabzonspor", "Süper Lig", 30, 45, 8),
            ("Dominik Szoboszlai", "MID", "Liverpool", "Premier League", 23, 42, 15),
            ("Roland Sallai", "FWD", "SC Freiburg", "Bundesliga", 27, 42, 12),
            ("Adam Szalai", "FWD", "Mainz", "Bundesliga", 36, 82, 28),
            ("Kevin Csoboth", "FWD", "Ujpest", "OTP Bank Liga", 25, 15, 5),
        ],
        "Scotland": [
            ("Angus Gunn", "GK", "Norwich", "Championship", 28, 18, 0),
            ("Aaron Hickey", "DEF", "Brentford", "Premier League", 22, 18, 2),
            ("John Souttar", "DEF", "Rangers", "Scottish Prem", 27, 25, 3),
            ("Grant Hanley", "DEF", "Norwich", "Championship", 32, 52, 2),
            ("Andrew Robertson", "DEF", "Liverpool", "Premier League", 30, 75, 11),
            ("John McGinn", "MID", "Aston Villa", "Premier League", 30, 68, 12),
            ("Callum McGregor", "MID", "Celtic", "Scottish Prem", 30, 55, 8),
            ("Billy Gilmour", "MID", "Brighton", "Premier League", 23, 22, 2),
            ("Ryan Christie", "FWD", "Bournemouth", "Premier League", 29, 48, 12),
            ("Che Adams", "FWD", "Southampton", "Championship", 28, 38, 8),
            ("Lawrence Shankland", "FWD", "Hearts", "Scottish Prem", 28, 18, 8),
        ],
        "Romania": [
            ("Florin Nita", "GK", "Stade Brest", "Ligue 1", 35, 38, 0),
            ("Andrei Ratiu", "DEF", "Villarreal", "La Liga", 26, 22, 2),
            ("Adrian Rus", "DEF", "Pisa", "Serie B", 28, 25, 2),
            ("Radu Dragusin", "DEF", "Tottenham", "Premier League", 22, 18, 2),
            ("Nicusor Bancu", "DEF", "Universitatea Craiova", "Liga 1", 31, 38, 3),
            ("Mihai Marin", "MID", "FC Paderborn", "2. Bundesliga", 26, 22, 2),
            ("Nicolae Stanciu", "MID", "Wuhan Three Towns", "CSL", 31, 68, 18),
            ("Razvan Marin", "MID", "Cagliari", "Serie A", 28, 48, 5),
            ("Valentin Mihaila", "FWD", "Parma", "Serie A", 25, 28, 8),
            ("Florin Tanase", "FWD", "Al-Akhdoud", "Saudi First Division", 29, 38, 15),
            ("Denis Alibec", "FWD", "Maccabi Tel Aviv", "Israeli Premier League", 33, 38, 10),
        ],
        "Venezuela": [
            ("Wuilker Farinez", "GK", "Millwall", "Championship", 26, 38, 0),
            ("Ronald Hernandez", "DEF", "Atalanta", "Serie A", 26, 28, 2),
            ("Yordan Osorio", "DEF", "Rayo Vallecano", "La Liga", 27, 32, 2),
            ("Nahuel Ferraresi", "DEF", "Sassuolo", "Serie B", 24, 22, 2),
            ("Jose Martinez", "DEF", "Philadelphia Union", "MLS", 29, 38, 3),
            ("Yangel Herrera", "MID", "Girona", "La Liga", 26, 48, 8),
            ("Jefferson Savarino", "MID", "Real Salt Lake", "MLS", 27, 52, 12),
            ("Junior Moreno", "MID", "DC United", "MLS", 33, 45, 3),
            ("Edson Castillo", "FWD", "Detroit City", "MLS", 28, 32, 5),
            ("Salomon Rondon", "FWD", "Al-Qadsiah", "Saudi Pro League", 34, 105, 42),
            ("Darwin Machis", "FWD", "Udinese", "Serie A", 31, 62, 18),
        ],
        "DR Congo": [
            ("Lionel Mpasi", "GK", "Guingamp", "Ligue 2", 26, 18, 0),
            ("Chancel Mbemba", "DEF", "Marseille", "Ligue 1", 30, 62, 3),
            ("Merveille Bope", "DEF", "Gent", "Pro League", 25, 22, 2),
            ("Joris Kayembe", "DEF", "Charleroi", "Pro League", 28, 28, 2),
            ("Marcel Tisserand", "DEF", "Kasimpasa", "Süper Lig", 32, 45, 3),
            ("Yannick Bolasie", "MID", "Aris Limassol", "Cyprus First Division", 34, 78, 12),
            ("Papy Djilobodji", "MID", "Reims", "Ligue 1", 35, 32, 2),
            ("Yannick Carrasco", "MID", "Al-Qadsiah", "Saudi Pro League", 31, 25, 5),
            ("Jonathan David", "FWD", "Lille", "Ligue 1", 24, 28, 12),
            ("Cedric Bakambu", "FWD", "Marseille", "Ligue 1", 33, 65, 32),
            ("Dieumerci Mbokani", "FWD", "Dynamo Kyiv", "Ukrainian Premier League", 37, 72, 35),
        ],
        "Cameroon": [
            ("Devis Epassy", "GK", "Abha", "Saudi First Division", 31, 22, 0),
            ("Nouhou Tolo", "DEF", "Seattle Sounders", "MLS", 27, 32, 2),
            ("Christopher Wooh", "DEF", "Rennes", "Ligue 1", 22, 18, 1),
            ("Michael Ngadeu", "DEF", "Gent", "Pro League", 32, 55, 3),
            ("Collins Fai", "DEF", "Standard Liege", "Pro League", 32, 48, 2),
            ("Andre-Frank Zambo Anguissa", "MID", "Napoli", "Serie A", 28, 55, 5),
            ("Jean Onana", "MID", "Everton", "Premier League", 24, 22, 2),
            ("Pierre Kunde", "MID", "Mainz", "Bundesliga", 28, 38, 5),
            ("Eric Maxim Choupo-Moting", "FWD", "Bayern Munich", "Bundesliga", 34, 78, 32),
            ("Vincent Aboubakar", "FWD", "Besiktas", "Süper Lig", 32, 92, 42),
            ("Karl Toko Ekambi", "FWD", "Lyon", "Ligue 1", 31, 68, 28),
        ],
        "Slovenia": [
            ("Jan Oblak", "GK", "Atletico Madrid", "La Liga", 31, 75, 0),
            ("Jure Balkovec", "DEF", "NK Maribor", "PrvaLiga", 30, 28, 2),
            ("Miha Blazic", "DEF", "Ferencvaros", "OTP Bank Liga", 28, 32, 3),
            ("Jaka Bijol", "DEF", "Udinese", "Serie A", 26, 28, 3),
            ("Jan Mlakar", "DEF", "Hajduk Split", "HNL", 26, 22, 3),
            ("Adam Cerin", "MID", "NK Olimpija", "PrvaLiga", 26, 22, 2),
            ("Sandi Lovric", "MID", "Udinese", "Serie A", 25, 22, 3),
            ("Timi Max Elsnik", "MID", "Birmingham", "Championship", 25, 18, 3),
            ("Jon Gorenc Stankovic", "FWD", "Huddersfield", "Championship", 28, 35, 5),
            ("Andraz Sporar", "FWD", "Sporting CP", "Primeira Liga", 28, 35, 10),
            ("Benjamin Sesko", "FWD", "RB Leipzig", "Bundesliga", 21, 22, 8),
        ],
        "Costa Rica": [
            ("Keylor Navas", "GK", "PSG", "Ligue 1", 37, 115, 0),
            ("Bryan Oviedo", "DEF", "Real Salt Lake", "MLS", 33, 75, 5),
            ("Oscar Duarte", "DEF", "Al-Qadsiah", "Saudi First Division", 35, 72, 5),
            ("Kendall Waston", "DEF", "Herediano", "Liga Promerica", 36, 45, 5),
            ("Ronald Matarrita", "DEF", "FC Cincinnati", "MLS", 29, 55, 3),
            ("Celso Borges", "MID", "Alajuelense", "Liga Promerica", 35, 115, 15),
            ("Yeltsin Tejeda", "MID", "San Jose Earthquakes", "MLS", 30, 72, 8),
            ("Gerson Torres", "MID", "San Jose Earthquakes", "MLS", 25, 28, 5),
            ("Johan Venegas", "FWD", "Alajuelense", "Liga Promerica", 33, 55, 18),
            ("Joel Campbell", "FWD", "Atletico Nacional", "Liga Aguila", 32, 112, 26),
            ("Anthony Contreras", "FWD", "Herediano", "Liga Promerica", 23, 15, 5),
        ],
        "Jamaica": [
            ("Andre Blake", "GK", "Philadelphia Union", "MLS", 32, 62, 0),
            ("DeJuan Jones", "DEF", "New England Revolution", "MLS", 28, 32, 2),
            ("Adrian Mariappa", "DEF", "AD Alcorcon", "La Liga 2", 37, 72, 2),
            ("Damion Lowe", "DEF", "Hammarby", "Allsvenskan", 35, 45, 3),
            ("Gregory Leigh", "DEF", "Morecambe", "League One", 30, 32, 2),
            ("Kasey Palmer", "MID", "Coventry", "Championship", 27, 28, 5),
            ("Javain Brown", "MID", "Vancouver Whitecaps", "MLS", 25, 25, 2),
            ("Devon Williams", "MID", "Atlanta United", "MLS", 23, 15, 2),
            ("Shamar Nicholson", "FWD", "Charlton Athletic", "League One", 27, 42, 15),
            ("Leon Bailey", "FWD", "Aston Villa", "Premier League", 27, 45, 18),
            ("Michail Antonio", "FWD", "West Ham", "Premier League", 34, 22, 5),
        ],
        "Saudi Arabia": [
            ("Mohammed Al-Owais", "GK", "Al-Hilal", "Saudi Pro League", 32, 55, 0),
            ("Sultan Al-Ghannam", "DEF", "Al-Ittihad", "Saudi Pro League", 27, 32, 2),
            ("Ali Al-Bulaihi", "DEF", "Al-Hilal", "Saudi Pro League", 32, 65, 5),
            ("Abdulelah Al-Amri", "DEF", "Al-Ahli", "Saudi Pro League", 25, 22, 2),
            ("Yasir Al-Shahrani", "DEF", "Al-Hilal", "Saudi Pro League", 30, 52, 3),
            ("Mohammed Kanno", "MID", "Al-Hilal", "Saudi Pro League", 27, 42, 5),
            ("Salem Al-Dawsari", "MID", "Al-Hilal", "Saudi Pro League", 32, 82, 22),
            ("Riyadh Mahrez", "MID", "Al-Ahli", "Saudi Pro League", 33, 0, 0),
            ("Ali Al-Hassan", "FWD", "Al-Qadsiah", "Saudi Pro League", 24, 18, 5),
            ("Firas Al-Buraikan", "FWD", "Al-Fateh", "Saudi Pro League", 23, 22, 8),
            ("Saleh Al-Shehri", "FWD", "Al-Hilal", "Saudi Pro League", 31, 38, 12),
        ],
        "Egypt": [
            ("Mohamed El-Shenawy", "GK", "Al-Ahly", "Egyptian Premier League", 35, 48, 0),
            ("Akram Tawfik", "DEF", "Al-Ahly", "Egyptian Premier League", 28, 32, 2),
            ("Ahmed Hegazi", "DEF", "Al-Ittihad", "Saudi Pro League", 33, 75, 6),
            ("Omar Kamal", "DEF", "Zamalek", "Egyptian Premier League", 27, 28, 2),
            ("Omar Gaber", "DEF", "Al-Ahly", "Egyptian Premier League", 30, 52, 3),
            ("Tarek Hamed", "MID", "Zamalek", "Egyptian Premier League", 35, 52, 3),
            ("Hamdi Fathi", "MID", "Al-Ahly", "Egyptian Premier League", 28, 38, 5),
            ("Emam Ashour", "MID", "Zamalek", "Egyptian Premier League", 28, 35, 8),
            ("Amr El-Sulaya", "FWD", "Al-Ittihad", "Saudi Pro League", 29, 38, 12),
            ("Mohamed Salah", "FWD", "Liverpool", "Premier League", 32, 98, 55),
            ("Mostafa Mohamed", "FWD", "Galatasaray", "Süper Lig", 26, 42, 18),
        ],
        "Iran": [
            ("Alireza Beiranvand", "GK", "Anderlecht", "First Division A", 32, 55, 0),
            ("Sadegh Moharrami", "DEF", "Dinamo Zagreb", "HNL", 28, 35, 2),
            ("Majid Hosseini", "DEF", "Kasimpasa", "Süper Lig", 26, 32, 2),
            ("Shoja Khalilzadeh", "DEF", "Foolad", "IPL", 34, 55, 3),
            ("Ehsan Hajsafi", "DEF", "Panachaiki", "Football League Greece", 34, 112, 5),
            ("Ahmad Nourollahi", "MID", "Esteghlal", "IPL", 30, 48, 5),
            ("Ali Gholizadeh", "MID", "Charleroi", "Pro League", 26, 38, 8),
            ("Saman Ghoddos", "MID", "Brentford", "Premier League", 30, 58, 12),
            ("Alireza Jahanbakhsh", "FWD", "Feyenoord", "Eredivisie", 30, 88, 28),
            ("Sardar Azmoun", "FWD", "AS Roma", "Serie A", 29, 75, 42),
            ("Mehdi Taremi", "FWD", "Inter Milan", "Serie A", 32, 92, 42),
        ],
        "Iraq": [
            ("Jalal Hassan", "GK", "Al-Zawra", "Iraqi Stars League", 30, 45, 0),
            ("Ahmed Ibrahim", "DEF", "Al-Shorta", "Iraqi Stars League", 28, 38, 2),
            ("Ali Adnan", "DEF", "Umm Salal", "QSL", 31, 72, 5),
            ("Rebin Sulaka", "DEF", "Hammarby", "Allsvenskan", 26, 28, 2),
            ("Saman Nasreen", "DEF", "Ostersunds FK", "Superettan", 30, 32, 2),
            ("Amjad Attwan", "MID", "Al-Quwa Al-Jawiya", "Iraqi Stars League", 29, 42, 5),
            ("Humam Tariq", "MID", "Al-Shorta", "Iraqi Stars League", 24, 25, 3),
            ("Aymen Hussein", "MID", "Al-Quwa Al-Jawiya", "Iraqi Stars League", 27, 38, 8),
            ("Mohanad Abdulraheem", "FWD", "Al-Quwa Al-Jawiya", "Iraqi Stars League", 29, 42, 15),
            ("Alaa Abdul Zahra", "FWD", "Al-Naft", "Iraqi Stars League", 28, 35, 12),
            ("Osama Rashid", "FWD", "Pas Hamedan", "IPL", 25, 28, 8),
        ],
        "Honduras": [
            ("Luis Lopez", "GK", "Santos Laguna", "Liga MX", 26, 28, 0),
            ("Denil Maldonado", "DEF", "Miami FC", "USL Championship", 27, 38, 2),
            ("Marcelo Pereira", "DEF", "Olimpia", "Liga Nacional", 29, 42, 2),
            ("Ever Alvarado", "DEF", "Olimpia", "Liga Nacional", 32, 55, 2),
            ("Omar Elvir", "DEF", "Club America", "Liga MX", 25, 22, 2),
            ("Deybi Flores", "MID", "Olimpia", "Liga Nacional", 26, 35, 5),
            ("Jorge Alvarez", "MID", "Real Espana", "Liga Nacional", 24, 25, 3),
            ("Kervin Arriaga", "MID", "Red Bull Bragantino", "Brasileirao", 23, 22, 5),
            ("Luis Palma", "FWD", "Celtic", "Scottish Prem", 24, 28, 8),
            ("Anthony Lozano", "FWD", "Cadiz", "La Liga", 30, 55, 18),
            ("Romell Quioto", "FWD", "Club Olimpia", "Liga Nacional", 32, 65, 15),
        ],
        "Bolivia": [
            ("Carlos Lampe", "GK", "Strongest", "Division Profesional", 36, 72, 0),
            ("Luis Haquín", "DEF", "Always Ready", "Division Profesional", 26, 28, 2),
            ("Diego Bejarano", "DEF", "Bolivar", "Division Profesional", 31, 42, 3),
            ("Jose Sagredo", "DEF", "The Strongest", "Division Profesional", 29, 35, 2),
            ("Marvin Bejarano", "DEF", "Oriente Petrolero", "Division Profesional", 28, 28, 2),
            ("Moises Paniagua", "MID", "Bolivar", "Division Profesional", 27, 32, 5),
            ("Roberto Fernandez", "MID", "Nacional Potosi", "Division Profesional", 31, 45, 5),
            ("Erwin Saavedra", "MID", "Oriente Petrolero", "Division Profesional", 29, 38, 5),
            ("Bruno Miranda", "FWD", "Club Guarani", "Division de Honor Paraguay", 30, 48, 18),
            ("Rodrigo Ramallo", "FWD", "Bolivar", "Division Profesional", 30, 48, 22),
            ("Marcelo Moreno Martins", "FWD", "Strongest", "Division Profesional", 37, 112, 38),
        ],
        "Paraguay": [
            ("Anthony Silva", "GK", "Olimpia", "Division Profesional", 34, 55, 0),
            ("Ivan Ramirez", "DEF", "Nacional", "Primera Division Uruguay", 25, 22, 2),
            ("Junior Alonso", "DEF", "Atletico Mineiro", "Brasileirao", 30, 55, 5),
            ("Fabian Balbuena", "DEF", "Dinamo Moscow", "Russian Premier League", 32, 68, 5),
            ("Santiago Arzamendia", "DEF", "Atletico Mineiro", "Brasileirao", 25, 28, 3),
            ("Mathias Villasanti", "MID", "Gremio", "Brasileirao", 26, 32, 5),
            ("Miguel Almiron", "MID", "Newcastle", "Premier League", 30, 68, 18),
            ("Andres Cubas", "MID", "Frosinone", "Serie B", 27, 32, 3),
            ("Gabriel Avalos", "FWD", "Cerro Porteno", "Division Profesional", 31, 35, 12),
            ("Antonio Sanabria", "FWD", "Torino", "Serie A", 27, 42, 12),
            ("Oscar Ruiz", "FWD", "Olimpia", "Division Profesional", 27, 28, 8),
        ],
        "New Zealand": [
            ("Stefan Marinovic", "GK", "New Mexico United", "USL Championship", 34, 38, 0),
            ("Michael Boxall", "DEF", "Minnesota United", "MLS", 36, 55, 3),
            ("Winston Reid", "DEF", "Brentford", "Premier League", 35, 48, 4),
            ("Nando Pijnaker", "DEF", "FC Dordrecht", "Eerste Divisie", 27, 22, 2),
            ("Liberato Cacace", "DEF", "Empoli", "Serie A", 23, 18, 2),
            ("Callum McCowatt", "MID", "Eastern Suburbs", "NRFL", 27, 22, 5),
            ("Marko Stamenic", "MID", "Club Brugge", "Pro League", 22, 18, 3),
            ("Tim Payne", "MID", "Chicago Fire", "MLS", 26, 18, 3),
            ("Chris Wood", "FWD", "Nottm Forest", "Premier League", 32, 82, 32),
            ("Matt Garbett", "FWD", "Portland Timbers", "MLS", 26, 22, 5),
            ("Kosta Barbarouses", "FWD", "Toronto FC", "MLS", 34, 35, 12),
        ],
        "Jordan": [
            ("Yazeed Abdelhamid", "GK", "Al-Wehdat", "Jordan Premier League", 32, 42, 0),
            ("Baha Abdel-Rahman", "DEF", "Al-Faisaly", "Jordan Premier League", 29, 38, 2),
            ("Musa Al-Taamari", "DEF", "Montpellier", "Ligue 1", 26, 28, 5),
            ("Mohammad Al-Dmeiri", "DEF", "Al-Wehdat", "Jordan Premier League", 28, 32, 2),
            ("Anas Bani Yaseen", "DEF", "Khorfakkan", "UAE Pro League", 30, 35, 2),
            ("Ahmad Bahjat", "MID", "Al-Faisaly", "Jordan Premier League", 26, 28, 5),
            ("Saeed Al-Murjan", "MID", "Al-Qadsiah", "Saudi First Division", 27, 32, 5),
            ("Abdullah Nasib", "MID", "Nejmeh SC", "Lebanese Premier League", 25, 22, 3),
            ("Al-Hassan Saleh", "FWD", "Al-Ramtha", "Jordan Premier League", 28, 38, 12),
            ("Musa Suleiman", "FWD", "Rayo Majadahonda", "Segunda Federacion", 24, 22, 8),
            ("Zaid Al-Rubaie", "FWD", "Shabab Al-Ordon", "Jordan Premier League", 23, 18, 5),
        ],
    }

    inserted = 0
    for team_name, squad in team_squads.items():
        row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            continue
        team_id = row["id"]

        for name, position, club, league, age, caps, goals in squad:
            cur.execute("""
                INSERT OR IGNORE INTO players
                    (name, team_id, position, club, club_league, age, caps, goals_as_nat)
                VALUES (?,?,?,?,?,?,?,?)
            """, (name, team_id, position, club, league, age, caps, goals))
            # Always look up the player_id (handles both INSERT and IGNORE cases)
            player_row = cur.execute(
                "SELECT id FROM players WHERE name=? AND team_id=?", (name, team_id)
            ).fetchone()
            if player_row:
                player_id = player_row["id"]
                # Add to squad selections (IGNORE if already exists)
                cur.execute("""
                    INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed)
                    VALUES (?,?,1)
                """, (team_id, player_id))
                inserted += 1

    conn.commit()
    print(f"  Jugadores sembrados: {inserted} insertados.")


def seed_sample_match_history(conn: sqlite3.Connection):
    """Seed representative recent match results for key teams."""
    cur = conn.cursor()

    team_matches_data = {
        "Argentina": [
            ("Bolivia", "2024-09-05", "WCQ CONMEBOL", 3, 0, "W", "home"),
            ("Chile", "2024-09-10", "WCQ CONMEBOL", 3, 0, "W", "away"),
            ("Venezuela", "2024-10-10", "WCQ CONMEBOL", 6, 0, "W", "home"),
            ("Bolivia", "2024-10-15", "WCQ CONMEBOL", 6, 0, "W", "neutral"),
            ("Uruguay", "2024-11-15", "WCQ CONMEBOL", 1, 0, "W", "home"),
            ("Brazil", "2024-11-19", "WCQ CONMEBOL", 1, 0, "W", "away"),
            ("Colombia", "2024-09-09", "WCQ CONMEBOL", 2, 1, "W", "home"),
            ("Chile", "2024-10-09", "WCQ CONMEBOL", 3, 0, "W", "neutral"),
            ("Peru", "2024-11-12", "WCQ CONMEBOL", 1, 0, "W", "neutral"),
            ("Ecuador", "2024-11-16", "WCQ CONMEBOL", 1, 0, "W", "neutral"),
        ],
        "France": [
            ("Luxembourg", "2024-09-05", "UEFA Nations League", 3, 0, "W", "home"),
            ("Italy", "2024-09-06", "UEFA Nations League", 1, 3, "L", "away"),
            ("Belgium", "2024-10-14", "UEFA Nations League", 2, 1, "W", "home"),
            ("Israel", "2024-10-17", "UEFA Nations League", 4, 1, "W", "neutral"),
            ("Italy", "2024-11-17", "UEFA Nations League", 1, 3, "L", "home"),
            ("Belgium", "2024-11-18", "UEFA Nations League", 2, 3, "L", "away"),
            ("Germany", "2025-03-22", "Friendly", 0, 2, "L", "away"),
            ("Croatia", "2025-03-25", "Friendly", 2, 0, "W", "home"),
            ("Spain", "2025-06-08", "Friendly", 1, 2, "L", "neutral"),
            ("England", "2025-06-15", "Friendly", 2, 1, "W", "home"),
        ],
        "Brazil": [
            ("Ecuador", "2024-09-06", "WCQ CONMEBOL", 1, 0, "W", "home"),
            ("Paraguay", "2024-09-10", "WCQ CONMEBOL", 4, 1, "W", "neutral"),
            ("Chile", "2024-10-10", "WCQ CONMEBOL", 1, 1, "D", "away"),
            ("Peru", "2024-10-15", "WCQ CONMEBOL", 4, 0, "W", "home"),
            ("Venezuela", "2024-11-14", "WCQ CONMEBOL", 1, 0, "W", "away"),
            ("Uruguay", "2024-11-19", "WCQ CONMEBOL", 0, 1, "L", "home"),
            ("Colombia", "2025-03-22", "Friendly", 1, 2, "L", "neutral"),
            ("Argentina", "2025-03-26", "Friendly", 1, 1, "D", "neutral"),
            ("Germany", "2025-03-29", "Friendly", 0, 1, "L", "neutral"),
            ("Chile", "2025-06-06", "Friendly", 3, 0, "W", "home"),
        ],
        "Croatia": [
            ("Poland", "2024-09-07", "UEFA Nations League", 2, 0, "W", "home"),
            ("Portugal", "2024-09-10", "UEFA Nations League", 1, 2, "L", "away"),
            ("Scotland", "2024-10-12", "UEFA Nations League", 2, 1, "W", "away"),
            ("Poland", "2024-10-15", "UEFA Nations League", 1, 0, "W", "away"),
            ("Portugal", "2024-11-18", "UEFA Nations League", 1, 5, "L", "home"),
            ("Scotland", "2024-11-19", "UEFA Nations League", 2, 0, "W", "home"),
            ("Netherlands", "2025-03-20", "Friendly", 2, 4, "L", "away"),
            ("Belgium", "2025-03-23", "Friendly", 1, 1, "D", "neutral"),
            ("Morocco", "2025-06-06", "Friendly", 1, 2, "L", "neutral"),
            ("Austria", "2025-06-10", "Friendly", 2, 1, "W", "home"),
        ],
        "Panama": [
            ("Cuba", "2024-03-22", "CONCACAF Nations League", 5, 0, "W", "home"),
            ("Guatemala", "2024-03-25", "CONCACAF Nations League", 2, 0, "W", "away"),
            ("Jamaica", "2024-06-07", "CONCACAF Nations League", 3, 1, "W", "home"),
            ("Canada", "2024-06-10", "CONCACAF Nations League", 1, 4, "L", "away"),
            ("USA", "2024-09-07", "CONCACAF Nations League", 1, 1, "D", "neutral"),
            ("Honduras", "2024-09-10", "CONCACAF Nations League", 2, 0, "W", "home"),
            ("Costa Rica", "2024-10-12", "Friendly", 1, 1, "D", "neutral"),
            ("Trinidad & Tobago", "2024-10-15", "Friendly", 2, 0, "W", "home"),
            ("Mexico", "2024-11-15", "Friendly", 0, 1, "L", "away"),
            ("Colombia", "2024-11-19", "Friendly", 0, 3, "L", "neutral"),
        ],
        "Germany": [
            ("Netherlands", "2024-09-10", "UEFA Nations League", 2, 2, "D", "away"),
            ("Bosnia", "2024-10-14", "UEFA Nations League", 2, 1, "W", "home"),
            ("Netherlands", "2024-11-16", "UEFA Nations League", 1, 0, "W", "home"),
            ("Hungary", "2024-11-19", "UEFA Nations League", 5, 0, "W", "away"),
            ("France", "2025-03-22", "Friendly", 2, 0, "W", "home"),
            ("Italy", "2025-03-25", "Friendly", 2, 0, "W", "neutral"),
            ("England", "2025-06-07", "Friendly", 1, 0, "W", "home"),
            ("Spain", "2025-06-11", "Friendly", 2, 2, "D", "neutral"),
            ("Mexico", "2025-06-15", "Friendly", 2, 1, "W", "neutral"),
            ("USA", "2025-06-19", "Friendly", 2, 0, "W", "neutral"),
        ],
        "Spain": [
            ("Serbia", "2024-09-07", "UEFA Nations League", 3, 0, "W", "home"),
            ("Denmark", "2024-09-10", "UEFA Nations League", 1, 0, "W", "away"),
            ("Serbia", "2024-10-12", "UEFA Nations League", 3, 0, "W", "away"),
            ("Switzerland", "2024-10-15", "UEFA Nations League", 1, 2, "L", "home"),
            ("Denmark", "2024-11-16", "UEFA Nations League", 2, 1, "W", "home"),
            ("Switzerland", "2024-11-19", "UEFA Nations League", 3, 2, "W", "away"),
            ("Netherlands", "2024-12-08", "UEFA NL Final", 3, 0, "W", "neutral"),
            ("France", "2025-03-22", "Friendly", 2, 1, "W", "neutral"),
            ("Italy", "2025-03-26", "Friendly", 2, 1, "W", "home"),
            ("Germany", "2025-06-11", "Friendly", 2, 2, "D", "neutral"),
        ],
        "England": [
            ("Finland", "2024-09-07", "UEFA Nations League", 2, 0, "W", "home"),
            ("Greece", "2024-09-10", "UEFA Nations League", 2, 1, "W", "away"),
            ("Republic of Ireland", "2024-10-12", "UEFA Nations League", 5, 0, "W", "home"),
            ("Greece", "2024-10-15", "UEFA Nations League", 3, 2, "W", "home"),
            ("Republic of Ireland", "2024-11-16", "UEFA Nations League", 2, 0, "W", "away"),
            ("Finland", "2024-11-19", "UEFA Nations League", 2, 0, "W", "home"),
            ("Germany", "2025-06-07", "Friendly", 0, 1, "L", "away"),
            ("Italy", "2025-06-11", "Friendly", 2, 0, "W", "home"),
            ("Croatia", "2025-06-15", "Friendly", 3, 0, "W", "neutral"),
            ("France", "2025-06-15", "Friendly", 1, 2, "L", "away"),
        ],
        "Mexico": [
            ("USA", "2024-03-23", "CONCACAF Nations League", 0, 2, "L", "neutral"),
            ("Jamaica", "2024-06-05", "Copa America", 1, 0, "W", "neutral"),
            ("Ecuador", "2024-06-09", "Copa America", 0, 0, "D", "neutral"),
            ("Venezuela", "2024-06-15", "Copa America", 1, 2, "L", "neutral"),
            ("Honduras", "2024-09-07", "Friendly", 3, 0, "W", "home"),
            ("Costa Rica", "2024-09-10", "Friendly", 2, 0, "W", "neutral"),
            ("Colombia", "2024-10-12", "Friendly", 0, 1, "L", "neutral"),
            ("Argentina", "2024-10-15", "Friendly", 0, 3, "L", "neutral"),
            ("Uruguay", "2024-11-15", "Friendly", 2, 1, "W", "home"),
            ("Bolivia", "2024-11-19", "Friendly", 3, 1, "W", "home"),
        ],
        "USA": [
            ("Canada", "2024-03-24", "CONCACAF Nations League", 2, 1, "W", "neutral"),
            ("Mexico", "2024-03-23", "CONCACAF Nations League", 2, 0, "W", "neutral"),
            ("Bolivia", "2024-06-05", "Copa America", 2, 0, "W", "neutral"),
            ("Panama", "2024-06-09", "Copa America", 1, 1, "D", "neutral"),
            ("Uruguay", "2024-06-15", "Copa America", 0, 1, "L", "neutral"),
            ("Panama", "2024-09-07", "CONCACAF Nations League", 1, 1, "D", "neutral"),
            ("Venezuela", "2024-09-10", "Friendly", 3, 0, "W", "home"),
            ("Mexico", "2024-10-12", "Friendly", 2, 0, "W", "neutral"),
            ("Jamaica", "2024-10-15", "Friendly", 3, 1, "W", "home"),
            ("New Zealand", "2024-11-16", "Friendly", 4, 1, "W", "home"),
        ],
    }

    inserted = 0
    for team_name, matches in team_matches_data.items():
        row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            continue
        team_id = row["id"]

        for opp, date, comp, gf, ga, result, venue in matches:
            # Try to find opponent id
            opp_row = cur.execute("SELECT id FROM teams WHERE name=?", (opp,)).fetchone()
            opp_id = opp_row["id"] if opp_row else None

            cur.execute("""
                INSERT INTO team_matches
                    (team_id, opponent_id, opponent_name, date, competition,
                     goals_for, goals_against, result, venue)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (team_id, opp_id, opp, date, comp, gf, ga, result, venue))
            inserted += 1

    conn.commit()
    print(f"  Historial de partidos sembrado: {inserted} registros.")


def reset_db():
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"  Base de datos borrada: {DB_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Setup DB Mundial 2026")
    parser.add_argument("--reset", action="store_true", help="Borrar y recrear la BD")
    args = parser.parse_args()

    if args.reset:
        reset_db()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()

    print("\n=== Creando tablas ===")
    create_tables(conn)

    print("\n=== Sembrando equipos ===")
    seed_teams(conn)

    print("\n=== Sembrando historial WC ===")
    seed_wc_history(conn)

    print("\n=== Sembrando partidos WC2026 ===")
    seed_wc_matches(conn)

    print("\n=== Sembrando jugadores ===")
    seed_sample_players(conn)

    print("\n=== Sembrando historial de partidos ===")
    seed_sample_match_history(conn)

    # Summary
    cur = conn.cursor()
    counts = {
        "teams": cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0],
        "players": cur.execute("SELECT COUNT(*) FROM players").fetchone()[0],
        "wc_matches": cur.execute("SELECT COUNT(*) FROM wc_matches").fetchone()[0],
        "wc_history": cur.execute("SELECT COUNT(*) FROM wc_history").fetchone()[0],
        "team_matches": cur.execute("SELECT COUNT(*) FROM team_matches").fetchone()[0],
    }
    print("\n=== Resumen ===")
    for table, count in counts.items():
        print(f"  {table}: {count} registros")

    conn.close()
    print(f"\nBase de datos lista: {DB_PATH}\n")


if __name__ == "__main__":
    main()
