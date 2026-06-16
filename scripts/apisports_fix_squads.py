"""
apisports_fix_squads.py — Completa convocados de equipos WC con < 23 jugadores.
Usa api-sports /players/squads
"""
import os, sys, sqlite3, time, requests
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"
KEY     = os.getenv("APISPORTS_KEY", "")
BASE    = "https://v3.football.api-sports.io"
MAX_REQ = 80

NAME_MAP = {
    "United States": "USA", "Korea Republic": "South Korea",
    "Cote d'Ivoire": "Ivory Coast", "Cabo Verde": "Cape Verde",
    "Bosnia": "Bosnia and Herzegovina", "Czech Republic": "Czechia",
    "Congo DR": "DR Congo",
}

_reqs = [0]

def api_get(path, params):
    if _reqs[0] >= MAX_REQ:
        return None
    h = {"x-apisports-key": KEY}
    try:
        r = requests.get(f"{BASE}{path}", headers=h, params=params, timeout=20)
        _reqs[0] += 1
        print(f"  [{_reqs[0]}] {path} {params} -> {r.status_code}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  error: {e}")
    return None

def run():
    if not KEY:
        print("APISPORTS_KEY no configurada.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    incomplete = conn.execute("""
        SELECT t.id, t.name, COUNT(pl.player_id) as n
        FROM teams t
        LEFT JOIN projected_lineups pl ON pl.team_id = t.id
        WHERE t.id IN (
            SELECT home_team_id FROM wc_matches WHERE date >= '2026-06-11'
            UNION
            SELECT away_team_id FROM wc_matches WHERE date >= '2026-06-11'
        )
        GROUP BY t.id, t.name
        HAVING n < 23
        ORDER BY n
    """).fetchall()

    if not incomplete:
        print("Todos los equipos tienen 23+ convocados.")
        conn.close()
        return

    print(f"Equipos incompletos: {len(incomplete)}")
    for row in incomplete:
        print(f"  {row['name']}: {row['n']}")

    POS_MAP = {"Goalkeeper": "GK", "Defender": "DEF", "Midfielder": "MID", "Attacker": "FWD"}

    for team_row in incomplete:
        team_name  = team_row["name"]
        team_db_id = team_row["id"]
        print(f"\nFetcheando squad: {team_name}")

        data = api_get("/teams", {"name": team_name})
        if not data or not data.get("response"):
            alt = {v: k for k, v in NAME_MAP.items()}.get(team_name, team_name)
            data = api_get("/teams", {"name": alt})
        if not data or not data.get("response"):
            print(f"  No encontrado en api-sports: {team_name}")
            continue

        api_team_id = data["response"][0]["team"]["id"]
        time.sleep(0.5)

        squad_data = api_get("/players/squads", {"team": api_team_id})
        if not squad_data or not squad_data.get("response"):
            print(f"  Sin squad para {team_name} (id={api_team_id})")
            continue

        players = squad_data["response"][0].get("players", []) if squad_data["response"] else []
        print(f"  {len(players)} jugadores en api-sports")

        inserted = 0
        for p in players:
            name   = p.get("name", "")
            pos    = POS_MAP.get(p.get("position", ""), p.get("position", "")[:3])
            number = p.get("number")

            conn.execute(
                "INSERT OR IGNORE INTO players (name, nationality, position) VALUES (?,?,?)",
                (name, team_name, pos)
            )
            local = conn.execute(
                "SELECT id FROM players WHERE name=? AND nationality=?", (name, team_name)
            ).fetchone()
            if not local:
                continue

            conn.execute(
                "INSERT OR IGNORE INTO projected_lineups (team_id, player_id, role, jersey_number) VALUES (?,?,'bench',?)",
                (team_db_id, local[0], number)
            )
            inserted += 1

        conn.commit()
        final = conn.execute(
            "SELECT COUNT(*) FROM projected_lineups WHERE team_id=?", (team_db_id,)
        ).fetchone()[0]
        print(f"  {inserted} insertados -> total: {final}")
        time.sleep(1)

    conn.close()
    print(f"\nRequests usadas: {_reqs[0]}")

if __name__ == "__main__":
    run()
