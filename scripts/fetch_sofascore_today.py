"""
fetch_sofascore_today.py — Extrae lineups + ratings de jugadores de Sofascore
para partidos del día con equipos WC2026. Sin API key — endpoints públicos.

Endpoints:
  /sport/football/scheduled-events/{date}  → lista de partidos del día
  /event/{id}/lineups                       → formación + jugadores con rating
"""
import json, time, sqlite3, sys
from datetime import date
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
OUT_DIR  = BASE_DIR / "data" / "lineups"

BASE = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "Cache-Control": "no-cache",
}

WC_TEAMS = {
    "Algeria","Argentina","Australia","Austria","Belgium","Bolivia",
    "Bosnia and Herzegovina","Brazil","Cameroon","Canada","Cape Verde",
    "Colombia","Costa Rica","Croatia","Curacao","Czechia","Czech Republic",
    "DR Congo","Denmark","Ecuador","Egypt","England","France","Germany",
    "Ghana","Haiti","Honduras","Hungary","Iran","Iraq","Ivory Coast",
    "Jamaica","Japan","Jordan","Mexico","Morocco","Netherlands",
    "New Zealand","Nigeria","Norway","Panama","Paraguay","Portugal",
    "Qatar","Romania","Saudi Arabia","Scotland","Senegal","Serbia",
    "Slovenia","South Africa","South Korea","Spain","Sweden","Switzerland",
    "Tunisia","Turkey","USA","United States","Uruguay","Uzbekistan","Venezuela",
}

NAME_MAP = {
    "United States": "USA", "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey", "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Czech Republic": "Czechia", "Congo DR": "DR Congo",
    "Cabo Verde": "Cape Verde", "Republic of Ireland": "Ireland",
}

def _get(path, retries=3):
    for i in range(retries):
        try:
            r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(5 * (i+1))
        except Exception as e:
            time.sleep(2)
    return None

def _resolve(name):
    return NAME_MAP.get(name, name)

def _is_wc(name):
    return _resolve(name) in WC_TEAMS

def get_team_id(conn, name):
    n = _resolve(name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
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

def fetch_day(target_date=None):
    day = target_date or date.today().isoformat()
    print(f"\n=== Sofascore — {day} ===")

    data = _get(f"/sport/football/scheduled-events/{day}")
    if not data:
        print("  Sin respuesta de Sofascore"); return [], day

    events = data.get("events", [])
    print(f"  {len(events)} eventos totales en Sofascore")

    wc_events = []
    for ev in events:
        status = ev.get("status", {}).get("type", "")
        if status not in ("finished", "inprogress"): continue
        home = ev.get("homeTeam", {}).get("name", "")
        away = ev.get("awayTeam", {}).get("name", "")
        if not (_is_wc(home) or _is_wc(away)): continue
        ev_id = ev.get("id")
        score = ev.get("homeScore", {}); score_a = ev.get("awayScore", {})
        wc_events.append({
            "id":       ev_id,
            "home":     home, "away": away,
            "home_db":  _resolve(home), "away_db": _resolve(away),
            "status":   status,
            "score_h":  score.get("current"), "score_a": score_a.get("current"),
            "tournament": ev.get("tournament", {}).get("name", ""),
        })
        print(f"  ★ {home} vs {away} [{status}] {score.get('current','?')}-{score_a.get('current','?')} (id={ev_id})")

    return wc_events, day



def fetch_lineups(ev_id):
    data = _get(f"/event/{ev_id}/lineups")
    if not data: return None
    return data

def store_event(conn, ev, lineups_data, date_str):
    htid = get_team_id(conn, ev["home_db"])
    atid = get_team_id(conn, ev["away_db"])
    if not htid or not atid:
        print(f"    skip: {ev['home_db']} o {ev['away_db']} no en DB")
        return 0, 0

    match_id = get_or_create_match(conn, htid, atid, date_str, ev["score_h"], ev["score_a"])
    ins_lu = ins_ns = 0

    if not lineups_data: return 0, 0

    for team_key in ("home", "away"):
        team_data = lineups_data.get(team_key, {})
        team_name = team_data.get("team", {}).get("name", "")
        tid = get_team_id(conn, team_name) or (htid if team_key=="home" else atid)
        opp_name = ev["away_db"] if team_key=="home" else ev["home_db"]
        formation = team_data.get("formation", "")

        players = team_data.get("players", [])
        for pdata in players:
            p = pdata.get("player", {})
            stats = pdata.get("statistics", {})
            name = p.get("name", "")
            if not name: continue

            minutes = stats.get("minutesPlayed") or pdata.get("minutes", 0) or 0
            rating  = stats.get("rating") or pdata.get("rating")
            goals   = stats.get("goals") or 0
            assists = stats.get("goalAssist") or 0
            starter = pdata.get("position") not in ("S", "SUB", None) or pdata.get("substitute") == False

            # Insertar lineup
            plid = get_player_id(conn, tid, name)
            if plid:
                if not conn.execute("SELECT 1 FROM match_lineups WHERE match_id=? AND player_id=?",
                                    (match_id, plid)).fetchone():
                    conn.execute("INSERT OR IGNORE INTO match_lineups "
                                 "(match_id,team_id,player_id,position,starter) VALUES (?,?,?,?,?)",
                                 (match_id, tid, plid, pdata.get("pos","UNK"), 1 if starter else 0))
                    ins_lu += 1

                # Insertar nat stats
                if not conn.execute("SELECT 1 FROM player_nat_stats WHERE player_id=? AND match_id=?",
                                    (plid, match_id)).fetchone():
                    conn.execute("INSERT OR IGNORE INTO player_nat_stats "
                                 "(player_id,match_id,match_date,opponent,minutes,goals,assists,rating,was_starter) "
                                 "VALUES (?,?,?,?,?,?,?,?,?)",
                                 (plid, match_id, date_str, opp_name,
                                  minutes, goals, assists,
                                  float(rating) if rating else None, 1 if starter else 0))
                    ins_ns += 1

    return ins_lu, ins_ns

def run(target_date=None):
    conn = sqlite3.connect(str(DB_PATH))
    result, day = fetch_day(target_date)

    total_lu = total_ns = total_events = 0
    output = {"date": day, "source": "sofascore", "events": []}

    for ev in result:
        print(f"\n  Fetching lineups: {ev['home']} vs {ev['away']} (id={ev['id']})...")
        time.sleep(0.8)
        lu = fetch_lineups(ev["id"])

        lu_count = 0
        ns_count = 0
        if lu:
            lu_count, ns_count = store_event(conn, ev, lu, day)
            total_lu += lu_count; total_ns += ns_count; total_events += 1
            print(f"    → lineups +{lu_count}  player_stats +{ns_count}")
        else:
            print(f"    → sin lineups")

        output["events"].append({
            "id": ev["id"], "home": ev["home_db"], "away": ev["away_db"],
            "score": f"{ev['score_h']}-{ev['score_a']}",
            "lineups": lu_count, "player_stats": ns_count,
        })

    conn.commit()
    conn.close()

    out_file = OUT_DIR / f"sofascore_{day}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))

    print(f"\n{'='*55}")
    print(f"SOFASCORE — {day}")
    print(f"  Eventos WC procesados: {total_events}")
    print(f"  match_lineups:         +{total_lu}")
    print(f"  player_nat_stats:      +{total_ns}")
    print(f"  Guardado en:           {out_file}")
    return output

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Fecha YYYY-MM-DD (default: hoy)")
    args = parser.parse_args()
    run(target_date=args.date)
