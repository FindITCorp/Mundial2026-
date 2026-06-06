"""
fetch_apisports_range.py — Extrae datos de jugadores via api-sports.io FREE
para múltiples fechas históricas de amistosos WC.

Respeta el límite de 100 req/día. Procesa fechas en orden hasta llegar al tope.

Uso:
  python scripts/fetch_apisports_range.py                         # fechas WC mayo-junio por defecto
  python scripts/fetch_apisports_range.py --dates 2026-05-31,2026-06-01
  python scripts/fetch_apisports_range.py --max-req 60            # límite de requests
"""
import argparse
import json
import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
OUT_DIR  = BASE_DIR / "data" / "lineups"

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

# Mapas de nombre API → nombre en DB
NAME_MAP = {
    "United States": "USA", "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Cape Verde Islands": "Cape Verde", "Cabo Verde": "Cape Verde",
    "Bosnia": "Bosnia and Herzegovina",
    "Czech Republic": "Czechia",
    "Congo DR": "DR Congo",
}

req_count = 0

def _get(path, params, max_req):
    global req_count
    if not KEY or req_count >= max_req:
        return None
    h = {"x-apisports-key": KEY}
    try:
        r = requests.get(f"{BASE}{path}", headers=h, params=params, timeout=20)
        req_count += 1
        print(f"  [{req_count}/{max_req}] GET {path} {params} → {r.status_code}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  error: {e}")
    return None


def _resolve(name):
    return NAME_MAP.get(name, name)


def _is_wc(name):
    return _resolve(name) in WC_TEAMS


def get_team_id(conn, name):
    n = _resolve(name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
    if r: return r[0]
    # intento insensible a mayúsculas
    r = conn.execute("SELECT id FROM teams WHERE LOWER(name)=LOWER(?)", (n,)).fetchone()
    return r[0] if r else None


def get_player_id(conn, team_id, name):
    r = conn.execute("SELECT id FROM players WHERE team_id=? AND name=?", (team_id, name)).fetchone()
    if r: return r[0]
    parts = name.strip().split()
    if len(parts) >= 2:
        r = conn.execute("SELECT id FROM players WHERE team_id=? AND name LIKE ?",
                         (team_id, f"%{parts[-1]}%")).fetchone()
        if r: return r[0]
    return None


def get_or_create_match(conn, htid, atid, date_str, score_h=None, score_a=None):
    r = conn.execute("SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND date=?",
                     (htid, atid, date_str)).fetchone()
    if r: return r[0]
    hn = conn.execute("SELECT name FROM teams WHERE id=?", (htid,)).fetchone()[0]
    an = conn.execute("SELECT name FROM teams WHERE id=?", (atid,)).fetchone()[0]
    conn.execute("INSERT INTO wc_matches (home_team_id,away_team_id,date,home_team_name,"
                 "away_team_name,score_home,score_away,stage,played) VALUES (?,?,?,?,?,?,?,'Friendly',1)",
                 (htid, atid, date_str, hn, an, score_h, score_a))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def process_date(conn, target_date, max_req):
    global req_count
    print(f"\n{'─'*55}")
    print(f"  Fecha: {target_date}")
    print(f"{'─'*55}")

    data = _get("/fixtures", {"date": target_date, "timezone": "UTC"}, max_req)
    if not data:
        print(f"  Sin respuesta (req={req_count}/{max_req})")
        return {"date": target_date, "fixtures": 0, "lineups": 0, "nat_stats": 0}

    fixtures_raw = data.get("response", [])
    print(f"  {len(fixtures_raw)} fixtures totales")

    # Filtrar partidos con equipos WC
    wc_fixtures = []
    for f in fixtures_raw:
        home = f.get("teams", {}).get("home", {}).get("name", "")
        away = f.get("teams", {}).get("away", {}).get("name", "")
        if not (_is_wc(home) or _is_wc(away)):
            continue
        fid = f.get("fixture", {}).get("id")
        status = f.get("fixture", {}).get("status", {}).get("short", "")
        goals_h = f.get("goals", {}).get("home")
        goals_a = f.get("goals", {}).get("away")
        wc_fixtures.append({
            "id": fid, "home": home, "away": away, "status": status,
            "score_h": goals_h, "score_a": goals_a,
        })
        print(f"  ★ {_resolve(home)} vs {_resolve(away)} | {goals_h}-{goals_a} id={fid}")

    total_lu = total_ns = 0

    for fix in wc_fixtures:
        fid = fix["id"]
        if not fid or req_count >= max_req - 2:
            break

        home_db = _resolve(fix["home"])
        away_db = _resolve(fix["away"])
        htid = get_team_id(conn, home_db)
        atid = get_team_id(conn, away_db)
        if not htid or not atid:
            print(f"    skip: {home_db} o {away_db} no en DB")
            continue

        match_id = get_or_create_match(conn, htid, atid, target_date, fix["score_h"], fix["score_a"])

        # Lineups
        time.sleep(0.5)
        lu = _get("/fixtures/lineups", {"fixture": fid}, max_req)
        if lu and lu.get("response"):
            for team_lu in lu["response"]:
                team_name = team_lu.get("team", {}).get("name", "")
                tid = get_team_id(conn, team_name) or (htid if _resolve(team_name)==home_db else atid)
                opp = away_db if tid == htid else home_db
                starters = team_lu.get("startXI", [])
                subs     = team_lu.get("substitutes", [])
                for pdata in starters + subs:
                    p    = pdata.get("player", {})
                    name = p.get("name", "")
                    pos  = p.get("pos", "UNK")
                    starter = pdata in starters
                    plid = get_player_id(conn, tid, name)
                    if plid:
                        if not conn.execute("SELECT 1 FROM match_lineups WHERE match_id=? AND player_id=?",
                                            (match_id, plid)).fetchone():
                            conn.execute("INSERT OR IGNORE INTO match_lineups "
                                         "(match_id,team_id,player_id,position,starter) VALUES (?,?,?,?,?)",
                                         (match_id, tid, plid, pos, 1 if starter else 0))
                            total_lu += 1

        # Player stats
        time.sleep(0.5)
        if req_count < max_req - 1:
            pl = _get("/fixtures/players", {"fixture": fid}, max_req)
            if pl and pl.get("response"):
                for team_pl in pl["response"]:
                    team_name = team_pl.get("team", {}).get("name", "")
                    tid = get_team_id(conn, team_name) or (htid if _resolve(team_name)==home_db else atid)
                    opp = away_db if tid == htid else home_db
                    for p in team_pl.get("players", []):
                        stats  = (p.get("statistics") or [{}])[0]
                        games  = stats.get("games", {})
                        name   = p.get("player", {}).get("name", "")
                        plid   = get_player_id(conn, tid, name)
                        if not plid: continue
                        minutes = games.get("minutes") or 0
                        rating  = games.get("rating")
                        goals   = (stats.get("goals") or {}).get("total") or 0
                        assists = (stats.get("goals") or {}).get("assists") or 0
                        starter = (games.get("position") or "") not in ("", None)
                        if not conn.execute("SELECT 1 FROM player_nat_stats WHERE player_id=? AND match_id=?",
                                            (plid, match_id)).fetchone():
                            conn.execute("INSERT OR IGNORE INTO player_nat_stats "
                                         "(player_id,match_id,match_date,opponent,minutes,goals,assists,rating,was_starter) "
                                         "VALUES (?,?,?,?,?,?,?,?,?)",
                                         (plid, match_id, target_date, opp,
                                          minutes, goals, assists,
                                          float(rating) if rating else None, 1 if starter else 0))
                            total_ns += 1

        time.sleep(0.3)

    conn.commit()
    print(f"  → match_lineups +{total_lu}  player_nat_stats +{total_ns}  req_used={req_count}")
    return {"date": target_date, "fixtures": len(wc_fixtures), "lineups": total_lu, "nat_stats": total_ns}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", default=None, help="Fechas separadas por coma")
    parser.add_argument("--max-req", type=int, default=90, help="Límite de requests (default 90)")
    args = parser.parse_args()

    if args.dates:
        dates = [d.strip() for d in args.dates.split(",")]
    else:
        # Fechas WC mayo-junio 2026 con amistosos
        dates = [
            "2026-05-22",
            "2026-05-30",
            "2026-05-31",
            "2026-06-01",
            "2026-06-02",
            "2026-06-04",
            "2026-06-05",
            "2026-06-06",
        ]
        print(f"Usando fechas WC mayo-junio por defecto: {dates}")

    max_req = args.max_req
    print(f"Límite requests: {max_req}")
    print(f"APISPORTS_KEY: {'✅' if KEY else '❌ no configurada'}")

    conn = sqlite3.connect(str(DB_PATH))
    results = []

    for d in dates:
        if req_count >= max_req:
            print(f"\n⚠️  Límite de {max_req} requests alcanzado. Fechas restantes no procesadas.")
            break
        r = process_date(conn, d, max_req)
        results.append(r)
        time.sleep(1)

    conn.close()

    # Guardar resumen
    out = OUT_DIR / "apisports_range_summary.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "requests_used": req_count,
        "max_req": max_req,
        "dates_processed": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2))

    print(f"\n{'='*55}")
    print(f"RESUMEN FINAL")
    print(f"  Requests usados: {req_count}/{max_req}")
    print(f"  Fechas procesadas: {len(results)}")
    for r in results:
        print(f"  {r['date']}: {r['fixtures']} partidos | +{r['lineups']} lineups | +{r['nat_stats']} player_stats")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
