"""
Fetch automático de alineaciones confirmadas via API-Football.
Se ejecuta desde match_day.yml cada 30min.

Para cada partido próximo (WC o amistoso):
  1. Obtiene el XI titular vía API
  2. Guarda en match_lineups
  3. Calcula squad_weight = fracción de titulares que están en squad_selections
  4. Actualiza squad_weight en team_matches del día
"""
import os
import sys
import time
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DB = BASE / "data" / "mundial2026.db"

APISPORTS_KEY = os.environ.get("APISPORTS_KEY", "")
APIFOOT_KEY   = os.environ.get("APIFOOT", "")


def _normalize(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return n.split()[-1]  # apellido


def compute_squad_weight(conn, team_id: int, starter_names: list[str]) -> float:
    """
    Calcula qué fracción de los 11 titulares están en la convocatoria WC confirmada.
    squad_selections.confirmed=1 → convocado oficial.
    """
    confirmed = conn.execute("""
        SELECT p.name FROM squad_selections ss
        JOIN players p ON p.id = ss.player_id
        WHERE ss.team_id = ? AND ss.confirmed = 1
    """, (team_id,)).fetchall()

    confirmed_norms = {_normalize(r[0]) for r in confirmed}
    if not confirmed_norms:
        return 1.0  # sin datos de convocatoria → peso neutro

    hits = sum(1 for name in starter_names if _normalize(name) in confirmed_norms)
    n = max(len(starter_names), 1)
    return round(hits / n, 3)


def fetch_lineup_apifootball(fixture_id: int) -> dict | None:
    """Llama a API-Football para obtener el XI titular."""
    import requests
    key = APIFOOT_KEY or APISPORTS_KEY
    if not key:
        return None

    url = "https://v3.football.api-sports.io/fixtures/lineups"
    headers = {"x-apisports-key": key}
    try:
        r = requests.get(url, headers=headers, params={"fixture": fixture_id}, timeout=15)
        data = r.json().get("response", [])
    except Exception as e:
        print(f"  API error: {e}")
        return None

    if not data:
        return None

    result = {}
    for entry in data:
        team_name = entry["team"]["name"]
        starters = [p["player"]["name"] for p in entry.get("startXI", [])]
        result[team_name] = starters
    return result


def save_lineup_and_weight(conn, match_id: int, date: str, lineups: dict):
    """
    Guarda lineups en match_lineups y actualiza squad_weight en team_matches.
    """
    for team_name, starters in lineups.items():
        team_row = conn.execute(
            "SELECT id FROM teams WHERE name=? OR name LIKE ?",
            (team_name, f"%{team_name}%")
        ).fetchone()
        if not team_row:
            print(f"  Equipo no encontrado: {team_name}")
            continue
        team_id = team_row[0]

        # Guardar en match_lineups
        for name in starters:
            p = conn.execute(
                "SELECT id FROM players WHERE team_id=? AND name=?",
                (team_id, name)
            ).fetchone()
            player_id = p[0] if p else None
            conn.execute("""
                INSERT OR IGNORE INTO match_lineups (match_id, team_id, player_id, starter)
                VALUES (?,?,?,1)
            """, (match_id, team_id, player_id))

        # Calcular squad_weight
        weight = compute_squad_weight(conn, team_id, starters)
        print(f"  {team_name}: {len(starters)} titulares → squad_weight={weight:.2f}")

        # Actualizar team_matches del día
        conn.execute("""
            UPDATE team_matches SET squad_weight=?
            WHERE team_id=? AND date=? AND squad_weight IS NULL OR squad_weight=1.0
        """, (weight, team_id, date))

    conn.commit()


def run(date_str: str | None = None):
    if not DB.exists():
        print("DB no encontrada"); return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    today = date_str or datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    # Buscar partidos WC del día con api_fixture_id
    matches = conn.execute("""
        SELECT id, date, home_team_name, away_team_name, api_fixture_id
        FROM wc_matches
        WHERE date BETWEEN ? AND ? AND played=0 AND api_fixture_id IS NOT NULL
        ORDER BY date, time
    """, (today, tomorrow)).fetchall()

    if not matches:
        print(f"Sin partidos WC con fixture_id para {today}")
    else:
        for m in matches:
            print(f"\nFetcheando lineup: {m['home_team_name']} vs {m['away_team_name']}")
            lineups = fetch_lineup_apifootball(m["api_fixture_id"])
            if lineups:
                save_lineup_and_weight(conn, m["id"], m["date"], lineups)
            else:
                print("  Lineup no disponible aún")
            time.sleep(2)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Fecha YYYY-MM-DD (default: hoy UTC)")
    args = p.parse_args()
    run(args.date)
