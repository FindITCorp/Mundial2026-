"""
fetch_apisports_today.py — Extrae fixtures + lineups + players del día actual
desde api-sports.io (FREE plan, 100 req/día).

Busca por fecha directa (no por season) para evitar el bloqueo de 2026.
Guarda los datos en data/lineups/apisports_today.json para inspección.
"""
import json
import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
OUT      = BASE_DIR / "data" / "lineups" / "apisports_today.json"

KEY  = os.getenv("APISPORTS_KEY", "")
BASE = "https://v3.football.api-sports.io"

WC_TEAMS = {
    "Algeria","Argentina","Australia","Austria","Belgium","Bolivia",
    "Bosnia and Herzegovina","Bosnia","Brazil","Cameroon","Canada",
    "Cape Verde","Colombia","Costa Rica","Croatia","Curacao","Czechia",
    "Czech Republic","DR Congo","Denmark","Ecuador","Egypt","England",
    "France","Germany","Ghana","Haiti","Honduras","Hungary","Iran","Iraq",
    "Italy","Ivory Coast","Jamaica","Japan","Jordan","Mexico","Morocco",
    "Netherlands","New Zealand","Nigeria","Norway","Panama","Paraguay",
    "Poland","Portugal","Qatar","Romania","Saudi Arabia","Scotland",
    "Senegal","Serbia","Slovenia","South Africa","South Korea","Korea Republic",
    "Spain","Sweden","Switzerland","Tunisia","Turkey","USA","United States",
    "Uruguay","Uzbekistan","Venezuela",
}

req_count = 0

def _get(path, params):
    global req_count
    if not KEY:
        return None
    h = {"x-apisports-key": KEY}
    try:
        r = requests.get(f"{BASE}{path}", headers=h, params=params, timeout=20)
        req_count += 1
        print(f"  [{req_count}] GET {path} {params} → {r.status_code}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  error: {e}")
    return None


def _is_wc(name):
    return (name or "") in WC_TEAMS


def run():
    today = date.today().isoformat()
    output = {
        "date": today,
        "key_configured": bool(KEY),
        "fixtures": [],
        "requests_used": 0,
    }

    if not KEY:
        output["error"] = "APISPORTS_KEY no configurada"
        return output

    # 1. Fixtures de hoy por fecha (sin season — evita el bloqueo)
    data = _get("/fixtures", {"date": today, "timezone": "UTC"})
    if not data:
        output["error"] = "Sin respuesta de /fixtures"
        return output

    errors = data.get("errors", {})
    output["api_errors"] = errors
    output["api_results_count"] = data.get("results", 0)

    fixtures_raw = data.get("response", [])
    print(f"  → {len(fixtures_raw)} fixtures totales para {today}")

    # Filtrar: al menos un equipo WC2026
    wc_fixtures = []
    for f in fixtures_raw:
        home = f.get("teams", {}).get("home", {}).get("name", "")
        away = f.get("teams", {}).get("away", {}).get("name", "")
        league = f.get("league", {}).get("name", "")
        if not (_is_wc(home) or _is_wc(away)):
            continue
        fid = f.get("fixture", {}).get("id")
        status = f.get("fixture", {}).get("status", {}).get("short", "")
        wc_fixtures.append({
            "id": fid,
            "home": home, "away": away,
            "league": league,
            "status": status,
            "score": f"{f.get('goals',{}).get('home')}-{f.get('goals',{}).get('away')}",
            "home_wc": _is_wc(home), "away_wc": _is_wc(away),
        })
        print(f"  ★ {home} vs {away} [{league}] id={fid} status={status}")

    output["wc_fixtures_count"] = len(wc_fixtures)
    output["wc_fixtures"] = wc_fixtures

    # 2. Para cada fixture WC, obtener lineups + players
    # Priorizar los que tienen status FT (terminados) o IN (en juego)
    priority = [f for f in wc_fixtures if f["status"] in ("FT","AET","PEN","1H","2H","HT","LIVE")]
    rest     = [f for f in wc_fixtures if f not in priority]
    ordered  = priority + rest

    for fix in ordered:
        fid = fix["id"]
        if not fid:
            continue
        if req_count >= 80:  # conservar margen
            print(f"  ⚠️ Límite de requests alcanzado ({req_count}), deteniendo")
            break

        fix_detail = {"fixture_id": fid, "home": fix["home"], "away": fix["away"],
                      "status": fix["status"], "score": fix["score"]}

        # Lineups
        time.sleep(0.5)
        lu = _get("/fixtures/lineups", {"fixture": fid})
        if lu and lu.get("response"):
            lineups = lu["response"]
            fix_detail["lineups_count"] = len(lineups)
            fix_detail["lineups"] = []
            for team_lu in lineups:
                team_name = team_lu.get("team", {}).get("name", "")
                formation = team_lu.get("formation", "")
                starters  = [p.get("player", {}).get("name") for p in team_lu.get("startXI", [])]
                subs      = [p.get("player", {}).get("name") for p in team_lu.get("substitutes", [])]
                fix_detail["lineups"].append({
                    "team": team_name, "formation": formation,
                    "starters": starters, "subs": subs,
                })
                print(f"    Lineup {team_name} ({formation}): {starters[:3]}...")
        else:
            fix_detail["lineups_count"] = 0
            fix_detail["lineups_error"] = lu.get("errors") if lu else "no response"

        # Players stats (minutos, rating, goles, asistencias)
        time.sleep(0.5)
        if req_count < 80:
            pl = _get("/fixtures/players", {"fixture": fid})
            if pl and pl.get("response"):
                players_data = pl["response"]
                fix_detail["players_teams"] = len(players_data)
                fix_detail["players"] = []
                for team_pl in players_data:
                    team_name = team_pl.get("team", {}).get("name", "")
                    players_list = []
                    for p in team_pl.get("players", []):
                        stats = (p.get("statistics") or [{}])[0]
                        games = stats.get("games", {})
                        players_list.append({
                            "name":    p.get("player", {}).get("name"),
                            "minutes": games.get("minutes"),
                            "rating":  games.get("rating"),
                            "position": games.get("position"),
                            "goals":   stats.get("goals", {}).get("total"),
                            "assists": stats.get("goals", {}).get("assists"),
                        })
                    fix_detail["players"].append({
                        "team": team_name, "players": players_list
                    })
                # Muestra primer jugador como sample
                if players_data and players_data[0].get("players"):
                    p0 = players_data[0]["players"][0]
                    s0 = (p0.get("statistics") or [{}])[0]
                    print(f"    Sample player: {p0.get('player',{}).get('name')} "
                          f"min={s0.get('games',{}).get('minutes')} "
                          f"rating={s0.get('games',{}).get('rating')}")
            else:
                fix_detail["players_error"] = pl.get("errors") if pl else "no response"
                print(f"    players error: {fix_detail['players_error']}")

        output["fixtures"].append(fix_detail)
        time.sleep(0.3)

    output["requests_used"] = req_count
    return output


if __name__ == "__main__":
    result = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nRequests usados: {result['requests_used']}/100")
    print(f"Fixtures WC encontrados: {result.get('wc_fixtures_count', 0)}")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
