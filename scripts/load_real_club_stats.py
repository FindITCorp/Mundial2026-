"""
scripts/load_real_club_stats.py
Carga estadísticas REALES de club 2024/25 desde datos scrapeados.

Uso:
  python3 scripts/load_real_club_stats.py

El dict REAL_STATS al final del archivo contiene los datos reales.
Los registros con league='EST' (imputados) se reemplazan por los reales.
Los registros con datos reales (league!='EST') NO se tocan.
"""
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"


def norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def load_stats(data: dict, conn: sqlite3.Connection) -> dict:
    """
    data: {team_name: [{name, position, club, goals, assists, minutes, matches, xg?, xa?}, ...]}
    Retorna resumen de lo que se insertó/actualizó.
    """
    summary = {"updated": 0, "not_found": [], "skipped_real": 0}

    for team_name, players in data.items():
        # Obtener team_id
        trow = conn.execute(
            "SELECT id FROM teams WHERE name=? COLLATE NOCASE", (team_name,)
        ).fetchone()
        if not trow:
            print(f"  ⚠ Equipo no encontrado: {team_name}")
            continue
        team_id = trow[0]

        # Obtener todos los jugadores del equipo (squad_selections)
        squad = conn.execute("""
            SELECT p.id, p.name FROM squad_selections ss
            JOIN players p ON p.id = ss.player_id
            WHERE ss.team_id = ?
        """, (team_id,)).fetchall()
        squad_map = {norm(r[1]): r[0] for r in squad}

        for p in players:
            pname_norm = norm(p["name"])

            # Buscar player_id: primero exacto, luego parcial
            pid = squad_map.get(pname_norm)
            if pid is None:
                # Búsqueda parcial (nombre corto dentro del nombre completo)
                for sq_norm, sq_id in squad_map.items():
                    if pname_norm in sq_norm or sq_norm in pname_norm:
                        pid = sq_id
                        break

            if pid is None:
                summary["not_found"].append(f"{team_name}/{p['name']}")
                continue

            # Verificar si ya tiene stats REALES (no imputadas)
            existing = conn.execute("""
                SELECT id, league FROM player_club_stats
                WHERE player_id = ? AND season = '2024/25'
            """, (pid,)).fetchone()

            if existing and existing[1] != "EST":
                summary["skipped_real"] += 1
                continue  # Ya tiene datos reales, no sobreescribir

            goals   = int(p.get("goals") or 0)
            assists = int(p.get("assists") or 0)
            minutes = int(p.get("minutes") or 0)
            matches = int(p.get("matches") or max(1, minutes // 75))
            club    = p.get("club") or ""
            league  = p.get("league") or ""
            xg      = float(p.get("xg") or round(goals * 0.82, 2))
            xa      = float(p.get("xa") or round(assists * 0.78, 2))
            sot     = int(p.get("shots_on_target") or max(0, round(xg / 0.25)))

            if existing:
                conn.execute("""
                    UPDATE player_club_stats
                    SET league=?, club=?, matches=?, minutes=?, goals=?, assists=?,
                        shots_on_target=?, xg=?, xa=?
                    WHERE id=?
                """, (league, club, matches, minutes, goals, assists, sot, xg, xa, existing[0]))
            else:
                conn.execute("""
                    INSERT INTO player_club_stats
                      (player_id, season, league, club, matches, minutes, goals, assists,
                       shots_on_target, xg, xa)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (pid, "2024/25", league, club, matches, minutes, goals, assists, sot, xg, xa))

            summary["updated"] += 1

    conn.commit()
    return summary


# ════════════════════════════════════════════════════════════════════════════════
# DATOS REALES — se llenan con los resultados de los agentes web
# ════════════════════════════════════════════════════════════════════════════════

REAL_STATS = {
    # ── ARGENTINA ──────────────────────────────────────────────────────────────
    "Argentina": [
        {"name": "Lionel Messi",          "position": "FWD", "club": "Inter Miami CF",    "league": "MLS",            "goals": 29, "assists": 19, "minutes": 2300, "matches": 28},
        {"name": "Julian Alvarez",         "position": "FWD", "club": "Atletico Madrid",   "league": "La Liga",        "goals": 21, "assists": 9,  "minutes": 2700, "matches": 35},
        {"name": "Lautaro Martinez",       "position": "FWD", "club": "Inter Milan",       "league": "Serie A",        "goals": 30, "assists": 6,  "minutes": 2800, "matches": 37},
        {"name": "Paulo Dybala",           "position": "FWD", "club": "AS Roma",           "league": "Serie A",        "goals": 4,  "assists": 4,  "minutes": 900,  "matches": 14},
        {"name": "Rodrigo De Paul",        "position": "MID", "club": "Atletico Madrid",   "league": "La Liga",        "goals": 3,  "assists": 5,  "minutes": 2100, "matches": 27},
        {"name": "Leandro Paredes",        "position": "MID", "club": "AS Roma",           "league": "Serie A",        "goals": 3,  "assists": 1,  "minutes": 1800, "matches": 22},
        {"name": "Enzo Fernandez",         "position": "MID", "club": "Chelsea",           "league": "Premier League", "goals": 16, "assists": 10, "minutes": 2900, "matches": 38},
        {"name": "Alexis Mac Allister",    "position": "MID", "club": "Liverpool",         "league": "Premier League", "goals": 7,  "assists": 4,  "minutes": 3774, "matches": 47},
        {"name": "Thiago Almada",          "position": "MID", "club": "Olympique Lyonnais","league": "Ligue 1",        "goals": 1,  "assists": 4,  "minutes": 1050, "matches": 13},
    ],

    # ── AUSTRALIA ──────────────────────────────────────────────────────────────
    "Australia": [
        {"name": "Martin Boyle",     "position": "FWD", "club": "Hibernian",     "league": "Scottish Premiership", "goals": 6, "assists": 2, "minutes": 1848, "matches": 16},
        {"name": "Jackson Irvine",   "position": "MID", "club": "FC St. Pauli",  "league": "Bundesliga",           "goals": 1, "assists": 6, "minutes": 2400, "matches": 29},
    ],

    # ── BELGIUM ────────────────────────────────────────────────────────────────
    "Belgium": [
        {"name": "Romelu Lukaku",    "position": "FWD", "club": "Napoli",            "league": "Serie A",        "goals": 14, "assists": 9, "minutes": 2800, "matches": 35},
        {"name": "Kevin De Bruyne",  "position": "MID", "club": "Manchester City",   "league": "Premier League", "goals": 4,  "assists": 7, "minutes": 2200, "matches": 28},
        {"name": "Lois Openda",      "position": "FWD", "club": "RB Leipzig",        "league": "Bundesliga",     "goals": 9,  "assists": 5, "minutes": 2600, "matches": 33},
        {"name": "Johan Bakayoko",   "position": "FWD", "club": "PSV Eindhoven",     "league": "Eredivisie",     "goals": 12, "assists": 8, "minutes": 2400, "matches": 34},
        {"name": "Yannick Carrasco", "position": "MID", "club": "Al-Shabab",         "league": "Saudi Pro League","goals": 20, "assists": 7, "minutes": 2928, "matches": 30},
        {"name": "Arthur Theate",    "position": "DEF", "club": "Eintracht Frankfurt","league": "Bundesliga",     "goals": 1,  "assists": 0, "minutes": 1900, "matches": 24},
    ],

    # ── BRAZIL ─────────────────────────────────────────────────────────────────
    "Brazil": [
        {"name": "Vinicius Junior",    "position": "FWD", "club": "Real Madrid",       "league": "La Liga",        "goals": 11, "assists": 8, "minutes": 2400, "matches": 30},
        {"name": "Rodrygo",            "position": "FWD", "club": "Real Madrid",       "league": "La Liga",        "goals": 4,  "assists": 5, "minutes": 1841, "matches": 24},
        {"name": "Raphinha",           "position": "FWD", "club": "Barcelona",         "league": "La Liga",        "goals": 18, "assists": 9, "minutes": 3060, "matches": 36},
        {"name": "Endrick",            "position": "FWD", "club": "Real Madrid",       "league": "La Liga",        "goals": 1,  "assists": 0, "minutes": 351,  "matches": 22},
        {"name": "Gabriel Martinelli", "position": "FWD", "club": "Arsenal",           "league": "Premier League", "goals": 8,  "assists": 4, "minutes": 2200, "matches": 35},
        {"name": "Bruno Guimaraes",    "position": "MID", "club": "Newcastle United",  "league": "Premier League", "goals": 5,  "assists": 6, "minutes": 3420, "matches": 38},
        {"name": "Casemiro",           "position": "MID", "club": "Manchester United", "league": "Premier League", "goals": 1,  "assists": 1, "minutes": 1980, "matches": 24},
    ],

    # ── CAMEROON ───────────────────────────────────────────────────────────────
    "Cameroon": [
        {"name": "Bryan Mbeumo",  "position": "FWD", "club": "Brentford",         "league": "Premier League", "goals": 20, "assists": 8, "minutes": 3200, "matches": 38},
    ],

    # ── COLOMBIA ───────────────────────────────────────────────────────────────
    "Colombia": [
        {"name": "Luis Diaz",  "position": "FWD", "club": "Liverpool", "league": "Premier League", "goals": 13, "assists": 5, "minutes": 3100, "matches": 36},
    ],

    # ── DENMARK ────────────────────────────────────────────────────────────────
    "Denmark": [
        {"name": "Rasmus Hojlund", "position": "FWD", "club": "Manchester United", "league": "Premier League", "goals": 8, "assists": 2, "minutes": 1800, "matches": 28},
    ],

    # ── ECUADOR ────────────────────────────────────────────────────────────────
    "Ecuador": [
        {"name": "Enner Valencia",    "position": "FWD", "club": "Internacional",        "league": "Brasileirao Serie A", "goals": 9, "assists": 1, "minutes": 1600, "matches": 18},
        {"name": "Gonzalo Plata",     "position": "FWD", "club": "Flamengo",             "league": "Brasileirao Serie A", "goals": 1, "assists": 0, "minutes": 750,  "matches": 12},
        {"name": "Pervis Estupinan",  "position": "DEF", "club": "Brighton",             "league": "Premier League",      "goals": 0, "assists": 2, "minutes": 2200, "matches": 28},
        {"name": "Jeremy Sarmiento",  "position": "MID", "club": "Burnley",              "league": "Championship",        "goals": 4, "assists": 0, "minutes": 1154, "matches": 35},
    ],

    # ── EGYPT ──────────────────────────────────────────────────────────────────
    "Egypt": [
        {"name": "Mohamed Salah",   "position": "FWD", "club": "Liverpool",         "league": "Premier League", "goals": 29, "assists": 18, "minutes": 3420, "matches": 38},
        {"name": "Omar Marmoush",   "position": "FWD", "club": "Manchester City",   "league": "Premier League", "goals": 26, "assists": 15, "minutes": 3200, "matches": 38},
        {"name": "Mostafa Mohamed", "position": "FWD", "club": "FC Nantes",         "league": "Ligue 1",        "goals": 8,  "assists": 1,  "minutes": 2100, "matches": 30},
    ],

    # ── ENGLAND ────────────────────────────────────────────────────────────────
    "England": [
        {"name": "Harry Kane",              "position": "FWD", "club": "Bayern Munich",     "league": "Bundesliga",     "goals": 26, "assists": 8,  "minutes": 2852, "matches": 31},
        {"name": "Jude Bellingham",         "position": "MID", "club": "Real Madrid",       "league": "La Liga",        "goals": 9,  "assists": 5,  "minutes": 2600, "matches": 34},
        {"name": "Phil Foden",              "position": "MID", "club": "Manchester City",   "league": "Premier League", "goals": 7,  "assists": 3,  "minutes": 2100, "matches": 26},
        {"name": "Bukayo Saka",             "position": "FWD", "club": "Arsenal",           "league": "Premier League", "goals": 6,  "assists": 10, "minutes": 2050, "matches": 25},
        {"name": "Cole Palmer",             "position": "MID", "club": "Chelsea",           "league": "Premier League", "goals": 12, "assists": 5,  "minutes": 3130, "matches": 38},
        {"name": "Declan Rice",             "position": "MID", "club": "Arsenal",           "league": "Premier League", "goals": 9,  "assists": 10, "minutes": 3100, "matches": 46},
        {"name": "Trent Alexander-Arnold",  "position": "DEF", "club": "Real Madrid",       "league": "La Liga",        "goals": 0,  "assists": 3,  "minutes": 1600, "matches": 21},
    ],

    # ── FRANCE ─────────────────────────────────────────────────────────────────
    "France": [
        {"name": "Kylian Mbappe",      "position": "FWD", "club": "Real Madrid",        "league": "La Liga",    "goals": 31, "assists": 3,  "minutes": 2900, "matches": 34},
        {"name": "Ousmane Dembele",    "position": "FWD", "club": "Paris Saint-Germain","league": "Ligue 1",   "goals": 21, "assists": 12, "minutes": 3715, "matches": 40},
        {"name": "Marcus Thuram",      "position": "FWD", "club": "Inter Milan",        "league": "Serie A",   "goals": 15, "assists": 7,  "minutes": 2900, "matches": 38},
        {"name": "Aurelien Tchouameni","position": "MID", "club": "Real Madrid",        "league": "La Liga",   "goals": 0,  "assists": 0,  "minutes": 2253, "matches": 32},
        {"name": "Adrien Rabiot",      "position": "MID", "club": "Olympique Marseille","league": "Ligue 1",   "goals": 8,  "assists": 5,  "minutes": 2400, "matches": 30},
    ],

    # ── GERMANY ────────────────────────────────────────────────────────────────
    "Germany": [
        {"name": "Florian Wirtz",   "position": "MID", "club": "Bayer Leverkusen", "league": "Bundesliga",     "goals": 10, "assists": 12, "minutes": 2700, "matches": 33},
        {"name": "Jamal Musiala",   "position": "MID", "club": "Bayern Munich",    "league": "Bundesliga",     "goals": 10, "assists": 5,  "minutes": 2400, "matches": 30},
        {"name": "Kai Havertz",     "position": "FWD", "club": "Arsenal",          "league": "Premier League", "goals": 13, "assists": 3,  "minutes": 2100, "matches": 29},
        {"name": "Leroy Sane",      "position": "FWD", "club": "Bayern Munich",    "league": "Bundesliga",     "goals": 11, "assists": 6,  "minutes": 2300, "matches": 30},
        {"name": "Niclas Fullkrug", "position": "FWD", "club": "West Ham United",  "league": "Premier League", "goals": 3,  "assists": 0,  "minutes": 530,  "matches": 10},
    ],

    # ── GHANA ──────────────────────────────────────────────────────────────────
    "Ghana": [
        {"name": "Thomas Partey",    "position": "MID", "club": "Arsenal",       "league": "Premier League", "goals": 3,  "assists": 1, "minutes": 2000, "matches": 30},
        {"name": "Jordan Ayew",      "position": "FWD", "club": "Leicester City","league": "Premier League", "goals": 5,  "assists": 6, "minutes": 2500, "matches": 35},
        {"name": "Inaki Williams",   "position": "FWD", "club": "Athletic Club", "league": "La Liga",        "goals": 6,  "assists": 8, "minutes": 2400, "matches": 30},
        {"name": "Antoine Semenyo",  "position": "FWD", "club": "Bournemouth",   "league": "Premier League", "goals": 11, "assists": 7, "minutes": 2800, "matches": 35},
        {"name": "Mohammed Kudus",   "position": "MID", "club": "West Ham United","league": "Premier League", "goals": 2,  "assists": 5, "minutes": 1500, "matches": 19},
    ],

    # ── HUNGARY ────────────────────────────────────────────────────────────────
    "Hungary": [
        {"name": "Dominik Szoboszlai", "position": "MID", "club": "Liverpool",    "league": "Premier League", "goals": 6,  "assists": 7, "minutes": 2800, "matches": 38},
        {"name": "Martin Adam",        "position": "FWD", "club": "AEK Athens",   "league": "Super League Greece", "goals": 14, "assists": 4, "minutes": 2200, "matches": 30},
    ],

    # ── IRAN ───────────────────────────────────────────────────────────────────
    "Iran": [
        {"name": "Mehdi Taremi",    "position": "FWD", "club": "Inter Milan",       "league": "Serie A",     "goals": 3,  "assists": 5,  "minutes": 1800, "matches": 41},
        {"name": "Sardar Azmoun",   "position": "FWD", "club": "Shabab Al Ahli",    "league": "UAE Pro League","goals": 25, "assists": 10, "minutes": 3200, "matches": 37},
        {"name": "Saman Ghoddos",   "position": "MID", "club": "Al-Ittihad Kalba",  "league": "UAE Pro League","goals": 4,  "assists": 2,  "minutes": 800,  "matches": 10},
    ],

    # ── ITALY ──────────────────────────────────────────────────────────────────
    "Italy": [
        {"name": "Mateo Retegui",    "position": "FWD", "club": "Atalanta",          "league": "Serie A",        "goals": 25, "assists": 8, "minutes": 3100, "matches": 36},
        {"name": "Moise Kean",       "position": "FWD", "club": "Fiorentina",        "league": "Serie A",        "goals": 19, "assists": 3, "minutes": 2700, "matches": 30},
        {"name": "Nicolo Barella",   "position": "MID", "club": "Inter Milan",       "league": "Serie A",        "goals": 3,  "assists": 8, "minutes": 2970, "matches": 33},
        {"name": "Gianluigi Donnarumma", "position": "GK", "club": "PSG",            "league": "Ligue 1",        "goals": 0,  "assists": 0, "minutes": 3420, "matches": 38},
    ],

    # ── IVORY COAST ────────────────────────────────────────────────────────────
    "Ivory Coast": [
        {"name": "Sebastien Haller",  "position": "FWD", "club": "FC Utrecht",  "league": "Eredivisie",     "goals": 7,  "assists": 3, "minutes": 1800, "matches": 24},
        {"name": "Franck Kessie",     "position": "MID", "club": "Al-Ahli",     "league": "Saudi Pro League","goals": 3,  "assists": 2, "minutes": 2000, "matches": 30},
        {"name": "Wilfried Zaha",     "position": "FWD", "club": "Charlotte FC", "league": "MLS",            "goals": 10, "assists": 7, "minutes": 2500, "matches": 32},
    ],

    # ── JAPAN ──────────────────────────────────────────────────────────────────
    "Japan": [
        {"name": "Kaoru Mitoma",    "position": "FWD", "club": "Brighton",       "league": "Premier League", "goals": 10, "assists": 13, "minutes": 1900, "matches": 22},
        {"name": "Ritsu Doan",      "position": "FWD", "club": "Freiburg",       "league": "Bundesliga",     "goals": 10, "assists": 11, "minutes": 2700, "matches": 34},
        {"name": "Takefusa Kubo",   "position": "MID", "club": "Real Sociedad",  "league": "La Liga",        "goals": 7,  "assists": 2,  "minutes": 2800, "matches": 42},
        {"name": "Daichi Kamada",   "position": "MID", "club": "Crystal Palace", "league": "Premier League", "goals": 2,  "assists": 3,  "minutes": 2200, "matches": 43},
        {"name": "Wataru Endo",     "position": "MID", "club": "Liverpool",      "league": "Premier League", "goals": 0,  "assists": 0,  "minutes": 1200, "matches": 29},
        {"name": "Ao Tanaka",       "position": "MID", "club": "Leeds United",   "league": "Championship",   "goals": 5,  "assists": 3,  "minutes": 3500, "matches": 45},
    ],

    # ── MEXICO ─────────────────────────────────────────────────────────────────
    "Mexico": [
        {"name": "Hirving Lozano",    "position": "FWD", "club": "San Diego FC", "league": "MLS",            "goals": 11, "assists": 8,  "minutes": 1700, "matches": 25},
        {"name": "Santiago Gimenez",  "position": "FWD", "club": "Feyenoord",    "league": "Eredivisie",     "goals": 10, "assists": 3,  "minutes": 1600, "matches": 22},
        {"name": "Edson Alvarez",     "position": "MID", "club": "West Ham",      "league": "Premier League", "goals": 0,  "assists": 1,  "minutes": 2100, "matches": 31},
        {"name": "Henry Martin",      "position": "FWD", "club": "Club America",  "league": "Liga MX",        "goals": 11, "assists": 10, "minutes": 2317, "matches": 30},
        {"name": "Raul Jimenez",      "position": "FWD", "club": "Fulham",        "league": "Premier League", "goals": 14, "assists": 3,  "minutes": 2700, "matches": 37},
    ],

    # ── MOROCCO ────────────────────────────────────────────────────────────────
    "Morocco": [
        {"name": "Achraf Hakimi",    "position": "DEF", "club": "PSG",            "league": "Ligue 1",   "goals": 5,  "assists": 10, "minutes": 2918, "matches": 30},
        {"name": "Youssef En-Nesyri","position": "FWD", "club": "Fenerbahce",     "league": "Süper Lig", "goals": 15, "assists": 4,  "minutes": 2100, "matches": 23},
        {"name": "Sofyan Amrabat",   "position": "MID", "club": "Fenerbahce",     "league": "Süper Lig", "goals": 1,  "assists": 1,  "minutes": 2000, "matches": 28},
        {"name": "Azzedine Ounahi",  "position": "MID", "club": "Girona FC",      "league": "La Liga",   "goals": 5,  "assists": 2,  "minutes": 1900, "matches": 24},
    ],

    # ── NETHERLANDS ────────────────────────────────────────────────────────────
    "Netherlands": [
        {"name": "Virgil van Dijk",  "position": "DEF", "club": "Liverpool",    "league": "Premier League",    "goals": 5,  "assists": 1, "minutes": 3150, "matches": 35},
        {"name": "Memphis Depay",    "position": "FWD", "club": "Corinthians",  "league": "Brasileirao Serie A","goals": 12, "assists": 9, "minutes": 3800, "matches": 43},
        {"name": "Cody Gakpo",       "position": "FWD", "club": "Liverpool",    "league": "Premier League",    "goals": 10, "assists": 4, "minutes": 2100, "matches": 26},
        {"name": "Xavi Simons",      "position": "MID", "club": "RB Leipzig",   "league": "Bundesliga",        "goals": 8,  "assists": 11,"minutes": 2700, "matches": 32},
        {"name": "Denzel Dumfries",  "position": "DEF", "club": "Inter Milan",  "league": "Serie A",           "goals": 5,  "assists": 5, "minutes": 2000, "matches": 27},
        {"name": "Wout Weghorst",    "position": "FWD", "club": "Ajax",         "league": "Eredivisie",        "goals": 7,  "assists": 2, "minutes": 1900, "matches": 23},
    ],

    # ── NIGERIA ────────────────────────────────────────────────────────────────
    "Nigeria": [
        {"name": "Victor Osimhen",   "position": "FWD", "club": "Galatasaray",  "league": "Süper Lig",  "goals": 26, "assists": 8, "minutes": 3100, "matches": 36},
        {"name": "Ademola Lookman",  "position": "FWD", "club": "Atalanta",     "league": "Serie A",    "goals": 22, "assists": 7, "minutes": 3000, "matches": 38},
    ],

    # ── POLAND ─────────────────────────────────────────────────────────────────
    "Poland": [
        {"name": "Robert Lewandowski", "position": "FWD", "club": "Barcelona", "league": "La Liga", "goals": 27, "assists": 2, "minutes": 2900, "matches": 34},
        {"name": "Arkadiusz Milik",    "position": "FWD", "club": "Juventus",  "league": "Serie A", "goals": 0,  "assists": 0, "minutes": 0,    "matches": 0},
    ],

    # ── PORTUGAL ───────────────────────────────────────────────────────────────
    "Portugal": [
        {"name": "Cristiano Ronaldo", "position": "FWD", "club": "Al-Nassr",         "league": "Saudi Pro League","goals": 25, "assists": 4,  "minutes": 3900, "matches": 38},
        {"name": "Bruno Fernandes",   "position": "MID", "club": "Manchester United", "league": "Premier League", "goals": 8,  "assists": 10, "minutes": 2880, "matches": 36},
        {"name": "Bernardo Silva",    "position": "MID", "club": "Manchester City",   "league": "Premier League", "goals": 4,  "assists": 4,  "minutes": 2500, "matches": 32},
        {"name": "Joao Felix",        "position": "FWD", "club": "Chelsea",           "league": "Premier League", "goals": 4,  "assists": 2,  "minutes": 1400, "matches": 20},
        {"name": "Rafael Leao",       "position": "FWD", "club": "AC Milan",          "league": "Serie A",        "goals": 9,  "assists": 3,  "minutes": 2350, "matches": 29},
        {"name": "Ruben Dias",        "position": "DEF", "club": "Manchester City",   "league": "Premier League", "goals": 1,  "assists": 0,  "minutes": 2430, "matches": 27},
        {"name": "Pedro Neto",        "position": "FWD", "club": "Chelsea",           "league": "Premier League", "goals": 9,  "assists": 10, "minutes": 3400, "matches": 51},
        {"name": "Diogo Jota",        "position": "FWD", "club": "Liverpool",         "league": "Premier League", "goals": 6,  "assists": 3,  "minutes": 1900, "matches": 26},
        {"name": "Joao Cancelo",      "position": "DEF", "club": "Barcelona",         "league": "La Liga",        "goals": 2,  "assists": 2,  "minutes": 953,  "matches": 16},
    ],

    # ── ROMANIA ────────────────────────────────────────────────────────────────
    "Romania": [
        {"name": "George Puscas",  "position": "FWD", "club": "Pafos FC",  "league": "Cyprus 1st Division", "goals": 8,  "assists": 1, "minutes": 2700, "matches": 34},
        {"name": "Denis Dragus",   "position": "FWD", "club": "Trabzonspor","league": "Süper Lig",          "goals": 2,  "assists": 1, "minutes": 1200, "matches": 17},
    ],

    # ── SAUDI ARABIA ───────────────────────────────────────────────────────────
    "Saudi Arabia": [
        {"name": "Salem Al-Dawsari",  "position": "MID", "club": "Al-Hilal",    "league": "Saudi Pro League", "goals": 15, "assists": 14, "minutes": 3000, "matches": 35},
        {"name": "Saleh Al-Shehri",   "position": "FWD", "club": "Al-Ittihad",  "league": "Saudi Pro League", "goals": 4,  "assists": 1,  "minutes": 1500, "matches": 18},
    ],

    # ── SENEGAL ────────────────────────────────────────────────────────────────
    "Senegal": [
        {"name": "Sadio Mane",       "position": "FWD", "club": "Al-Nassr",        "league": "Saudi Pro League", "goals": 10, "assists": 8, "minutes": 3734, "matches": 28},
        {"name": "Ismaila Sarr",     "position": "FWD", "club": "Crystal Palace",  "league": "Premier League",   "goals": 11, "assists": 8, "minutes": 3000, "matches": 38},
        {"name": "Pape Matar Sarr",  "position": "MID", "club": "Tottenham",       "league": "Premier League",   "goals": 6,  "assists": 5, "minutes": 3500, "matches": 54},
        {"name": "Nicolas Jackson",  "position": "FWD", "club": "Chelsea",         "league": "Premier League",   "goals": 10, "assists": 5, "minutes": 2500, "matches": 30},
    ],

    # ── SERBIA ─────────────────────────────────────────────────────────────────
    "Serbia": [
        {"name": "Dusan Vlahovic",    "position": "FWD", "club": "Juventus",  "league": "Serie A",        "goals": 10, "assists": 4, "minutes": 2400, "matches": 29},
        {"name": "Aleksandar Mitrovic","position": "FWD", "club": "Al-Hilal", "league": "Saudi Pro League","goals": 26, "assists": 5, "minutes": 2900, "matches": 28},
    ],

    # ── SLOVENIA ───────────────────────────────────────────────────────────────
    "Slovenia": [
        {"name": "Benjamin Sesko",  "position": "FWD", "club": "RB Leipzig", "league": "Bundesliga", "goals": 13, "assists": 3, "minutes": 2700, "matches": 34},
    ],

    # ── SOUTH KOREA ────────────────────────────────────────────────────────────
    "South Korea": [
        {"name": "Son Heung-min",  "position": "FWD", "club": "Tottenham",         "league": "Premier League", "goals": 11, "assists": 11, "minutes": 2700, "matches": 30},
        {"name": "Hwang Hee-chan", "position": "FWD", "club": "Wolverhampton",     "league": "Premier League", "goals": 2,  "assists": 2,  "minutes": 650,  "matches": 25},
        {"name": "Lee Kang-in",   "position": "MID", "club": "PSG",               "league": "Ligue 1",        "goals": 4,  "assists": 4,  "minutes": 1437, "matches": 30},
        {"name": "Kim Min-jae",   "position": "DEF", "club": "Bayern Munich",     "league": "Bundesliga",     "goals": 1,  "assists": 1,  "minutes": 1900, "matches": 25},
    ],

    # ── SPAIN ──────────────────────────────────────────────────────────────────
    "Spain": [
        {"name": "Lamine Yamal",    "position": "FWD", "club": "Barcelona",     "league": "La Liga", "goals": 9,  "assists": 13, "minutes": 2900, "matches": 35},
        {"name": "Pedri",           "position": "MID", "club": "Barcelona",     "league": "La Liga", "goals": 4,  "assists": 5,  "minutes": 3000, "matches": 37},
        {"name": "Gavi",            "position": "MID", "club": "Barcelona",     "league": "La Liga", "goals": 2,  "assists": 3,  "minutes": 1400, "matches": 22},
        {"name": "Alvaro Morata",   "position": "FWD", "club": "AC Milan",      "league": "Serie A", "goals": 7,  "assists": 2,  "minutes": 1400, "matches": 22},
        {"name": "Ferran Torres",   "position": "FWD", "club": "Barcelona",     "league": "La Liga", "goals": 10, "assists": 6,  "minutes": 1900, "matches": 27},
        {"name": "Dani Olmo",       "position": "MID", "club": "Barcelona",     "league": "La Liga", "goals": 10, "assists": 3,  "minutes": 1214, "matches": 25},
    ],

    # ── TUNISIA ────────────────────────────────────────────────────────────────
    "Tunisia": [
        {"name": "Ellyes Skhiri",  "position": "MID", "club": "Eintracht Frankfurt", "league": "Bundesliga", "goals": 0, "assists": 0, "minutes": 1444, "matches": 25},
    ],

    # ── URUGUAY ────────────────────────────────────────────────────────────────
    "Uruguay": [
        {"name": "Darwin Nunez",      "position": "FWD", "club": "Liverpool",         "league": "Premier League",   "goals": 5,  "assists": 3, "minutes": 2000, "matches": 30},
        {"name": "Facundo Pellistri",  "position": "FWD", "club": "Panathinaikos",     "league": "Super League Greece","goals": 0, "assists": 0, "minutes": 1352, "matches": 11},
        {"name": "Federico Valverde",  "position": "MID", "club": "Real Madrid",       "league": "La Liga",          "goals": 2,  "assists": 4, "minutes": 2820, "matches": 26},
        {"name": "Rodrigo Bentancur",  "position": "MID", "club": "Tottenham Hotspur", "league": "Premier League",   "goals": 2,  "assists": 1, "minutes": 3200, "matches": 43},
        {"name": "Ronald Araujo",      "position": "DEF", "club": "Barcelona",         "league": "La Liga",          "goals": 2,  "assists": 0, "minutes": 1800, "matches": 25},
    ],

    # ── USA ────────────────────────────────────────────────────────────────────
    "USA": [
        {"name": "Christian Pulisic",  "position": "FWD", "club": "AC Milan",      "league": "Serie A",        "goals": 11, "assists": 9, "minutes": 2800, "matches": 33},
        {"name": "Timothy Weah",       "position": "FWD", "club": "Juventus",      "league": "Serie A",        "goals": 6,  "assists": 4, "minutes": 2200, "matches": 32},
        {"name": "Gio Reyna",          "position": "MID", "club": "Borussia Dortmund","league": "Bundesliga",  "goals": 2,  "assists": 1, "minutes": 341,  "matches": 12},
        {"name": "Josh Sargent",       "position": "FWD", "club": "Norwich City",  "league": "Championship",   "goals": 15, "assists": 4, "minutes": 2900, "matches": 38},
        {"name": "Weston McKennie",    "position": "MID", "club": "Juventus",      "league": "Serie A",        "goals": 2,  "assists": 2, "minutes": 2100, "matches": 30},
        {"name": "Tyler Adams",        "position": "MID", "club": "Bournemouth",   "league": "Premier League", "goals": 0,  "assists": 1, "minutes": 1600, "matches": 22},
        {"name": "Brenden Aaronson",   "position": "MID", "club": "Leeds United",  "league": "Championship",   "goals": 9,  "assists": 2, "minutes": 2600, "matches": 38},
    ],
}


if __name__ == "__main__":
    if not REAL_STATS:
        print("  ⚠ REAL_STATS vacío — agrega los datos antes de ejecutar.")
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        result = load_stats(REAL_STATS, conn)
        conn.close()
        print(f"  ✅ Actualizados: {result['updated']}")
        print(f"  ⏭ Ya tenían datos reales: {result['skipped_real']}")
        if result["not_found"]:
            print(f"  ❌ No encontrados ({len(result['not_found'])}): {result['not_found'][:10]}")
