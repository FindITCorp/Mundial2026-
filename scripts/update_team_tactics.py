"""
update_team_tactics.py — Update all 48 WC2026 teams with accurate 2025-season
formation data based on their actual coaches and tactical styles.

Adds columns `coach` and `alt_formation` if not present, then updates every
team with formation, pressing_intensity, defensive_line, tactical_style, coach,
and alt_formation.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# (name, formation, pressing_intensity, defensive_line, tactical_style, coach, alt_formation)
TEAM_TACTICS: list[tuple] = [
    ("Mexico",                 "4-4-2",   5.5, "medium",    "counter",     "Javier Aguirre",             "5-4-1"),
    ("South Africa",           "4-4-2",   5.0, "medium",    "physical",    "Hugo Broos",                 "5-4-1"),
    ("South Korea",            "4-2-3-1", 6.0, "medium",    "disciplined", "Hong Myung-Bo",              "5-3-2"),
    ("Czechia",                "4-2-3-1", 6.0, "medium",    "possession",  "Ivan Hašek",                 "5-3-2"),
    ("Canada",                 "4-3-3",   7.0, "high",      "pressing",    "Jesse Marsch",               "5-4-1"),
    ("Bosnia and Herzegovina", "4-2-3-1", 5.5, "medium",    "balanced",    "Elvir Baljić",               "5-3-2"),
    ("Qatar",                  "4-3-3",   5.5, "medium",    "possession",  "Bartolomeu Sousa",           "4-5-1"),
    ("Switzerland",            "3-4-3",   6.0, "medium",    "possession",  "Murat Yakin",                "5-4-1"),
    ("Brazil",                 "4-2-3-1", 6.5, "high",      "attacking",   "Dorival Jr.",                "5-3-2"),
    ("Morocco",                "4-3-3",   6.5, "high",      "pressing",    "Walid Regragui",             "5-4-1"),
    ("Haiti",                  "4-4-2",   5.0, "low",       "defensive",   "Marc Collat",                "5-4-1"),
    ("Scotland",               "3-4-3",   6.0, "medium",    "physical",    "Steve Clarke",               "5-4-1"),
    ("USA",                    "4-3-3",   6.5, "high",      "pressing",    "Mauricio Pochettino",        "5-4-1"),
    ("Paraguay",               "4-2-3-1", 5.5, "medium",    "counter",     "Diego Garnero",              "5-3-2"),
    ("Australia",              "4-3-3",   6.0, "medium",    "physical",    "Tony Popovic",               "5-4-1"),
    ("Turkey",                 "4-2-3-1", 5.5, "medium",    "balanced",    "Vincenzo Montella",          "5-3-2"),
    ("Germany",                "4-2-3-1", 7.0, "high",      "pressing",    "Julian Nagelsmann",          "5-3-2"),
    ("Curacao",                "4-4-2",   5.0, "medium",    "counter",     "Remko Bicentini",            "5-4-1"),
    ("Ivory Coast",            "4-3-3",   6.0, "high",      "attacking",   "Emerse Faé",                 "5-4-1"),
    ("Ecuador",                "4-4-2",   5.5, "medium",    "physical",    "Sebastián Beccacece",        "5-4-1"),
    ("Netherlands",            "4-3-3",   6.5, "high",      "attacking",   "Ronald Koeman",              "5-4-1"),
    ("Japan",                  "4-2-3-1", 6.5, "high",      "pressing",    "Hajime Moriyasu",            "5-3-2"),
    ("Sweden",                 "4-4-2",   5.5, "medium",    "physical",    "Jon Dahl Tomasson",          "5-4-1"),
    ("Tunisia",                "4-3-3",   5.5, "medium",    "physical",    "Faouzi Benzarti",            "4-5-1"),
    ("Belgium",                "4-3-3",   6.0, "medium",    "possession",  "Domenico Tedesco",           "5-4-1"),
    ("Egypt",                  "4-2-3-1", 5.5, "medium",    "counter",     "Hossam Hassan",              "5-3-2"),
    ("Iran",                   "4-5-1",   5.0, "low",       "defensive",   "Amir Ghalenoei",             "5-4-1"),
    ("New Zealand",            "4-3-3",   5.0, "medium",    "balanced",    "Darren Bazeley",             "4-5-1"),
    ("Spain",                  "4-3-3",   7.0, "high",      "pressing",    "Luis de la Fuente",          "5-4-1"),
    ("Cape Verde",             "4-3-3",   5.5, "medium",    "physical",    'Pedro Brito "Bubista"',      "4-5-1"),
    ("Saudi Arabia",           "4-3-3",   5.5, "medium",    "balanced",    "Roberto Mancini",            "4-5-1"),
    ("Uruguay",                "3-3-1-3", 7.0, "high",      "pressing",    "Marcelo Bielsa",             "5-4-1"),
    ("France",                 "4-2-3-1", 6.0, "medium",    "balanced",    "Didier Deschamps",           "5-3-2"),
    ("Senegal",                "4-3-3",   6.0, "high",      "physical",    "Aliou Cissé",                "5-4-1"),
    ("Iraq",                   "4-5-1",   5.0, "low",       "defensive",   "Srečko Katanec",             "5-4-1"),
    ("Norway",                 "4-3-3",   6.0, "medium",    "counter",     "Ståle Solbakken",            "4-5-1"),
    ("Argentina",              "4-3-3",   6.5, "high",      "attacking",   "Lionel Scaloni",             "5-4-1"),
    ("Algeria",                "4-3-3",   5.5, "medium",    "balanced",    "Vladimir Petković",          "4-5-1"),
    ("Austria",                "4-2-3-1", 7.5, "very_high", "pressing",    "Ralf Rangnick",              "5-3-2"),
    ("Jordan",                 "4-5-1",   4.5, "low",       "defensive",   "Hossam Hassan",              "5-4-1"),
    ("Portugal",               "4-3-3",   6.0, "high",      "attacking",   "Roberto Martínez",           "5-4-1"),
    ("DR Congo",               "4-3-3",   5.5, "medium",    "physical",    "Sébastien Desabre",          "5-4-1"),
    ("Uzbekistan",             "4-2-3-1", 5.0, "medium",    "disciplined", "Srecko Katanec",             "5-3-2"),
    ("Colombia",               "4-2-3-1", 6.0, "medium",    "possession",  "Néstor Lorenzo",             "5-3-2"),
    ("England",                "4-2-3-1", 6.5, "high",      "pressing",    "Thomas Tuchel",              "5-3-2"),
    ("Croatia",                "4-2-3-1", 5.5, "medium",    "possession",  "Zlatko Dalić",               "5-3-2"),
    ("Ghana",                  "4-2-3-1", 5.5, "medium",    "counter",     "Otto Addo",                  "5-3-2"),
    ("Panama",                 "4-4-2",   5.0, "medium",    "defensive",   "Thomas Christiansen",        "5-4-1"),
]


def _add_columns_if_missing(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(teams)").fetchall()}
    for col, definition in [("coach", "TEXT"), ("alt_formation", "TEXT")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE teams ADD COLUMN {col} {definition}")
            print(f"  Added column: {col}")


def run(db_path: Path = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    _add_columns_if_missing(conn)

    updated = 0
    not_found = []

    for row in TEAM_TACTICS:
        name, formation, pressing, def_line, style, coach, alt_form = row
        cursor = conn.execute("""
            UPDATE teams
            SET
                formation          = ?,
                pressing_intensity = ?,
                defensive_line     = ?,
                tactical_style     = ?,
                coach              = ?,
                alt_formation      = ?
            WHERE name = ?
        """, (formation, pressing, def_line, style, coach, alt_form, name))

        if cursor.rowcount == 1:
            updated += 1
        else:
            not_found.append(name)

    conn.commit()
    conn.close()

    print(f"\nTeam tactics update complete.")
    print(f"  Teams updated : {updated}")
    if not_found:
        print(f"  Not found in DB ({len(not_found)}): {', '.join(not_found)}")
    else:
        print(f"  All {updated} teams found and updated.")

    return updated


if __name__ == "__main__":
    run()
