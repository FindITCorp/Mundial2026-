"""
fetch_fifa_timeline.py — Play-by-play de FIFA (timeline de eventos) para TODO el Mundial.

La cobertura en vivo de FIFA expone un timeline COMPLETO sin anti-bot:
  https://api.fifa.com/api/v3/timelines/17/285023/{stage}/{match}
Cada evento trae minuto, periodo, tipo, equipo (IdTeam), jugador, marcador corrido
y coordenadas del remate. Cubre lo que hoy nos falta en partidos FIFA-only:
remates (Type 12), paradas/Goal Prevention (57 = proxy de goals_prevented sin xG),
goles (0), córners (16), faltas (18), fueras de juego (15), asistencias (1),
tarjetas (2 amarilla / 3 roja), sustituciones (5).

Persiste en `fifa_match_events`. Idempotente (PK fifa_match_id+event_id).
Atribuye cada evento al home/away por IdTeam contra el calendario (no parsea texto).

Uso:
    python scripts/fetch_fifa_timeline.py              # todos los jugados (status 0)
    python scripts/fetch_fifa_timeline.py 400021516    # un fifa_match_id concreto
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
COMP, SEASON = "17", "285023"

# FIFA (calendario) -> nombre canónico en teams.name
NAME = {
    "Turkiye": "Turkey", "Türkiye": "Turkey", "Cabo Verde": "Cape Verde",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "Congo DR": "DR Congo", "IR Iran": "Iran", "Korea Republic": "South Korea",
    "Curaçao": "Curacao", "United States": "USA", "Czech Republic": "Czechia",
}

TYPE_NAMES = {
    0: "Goal", 1: "Assist", 2: "Yellow card", 3: "Red card", 5: "Substitution",
    7: "Start Time", 8: "End Time", 12: "Attempt at Goal", 15: "Offside",
    16: "Corner", 18: "Foul", 26: "Match end", 57: "Goal Prevention",
    79: "Coin Toss", 83: "Delay", 78: "Resume",
    34: "Own goal", 41: "Penalty scored", 71: "Red card given",
    80: "Coin Toss side", 85: "Weather pause",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _minute_num(m):
    """'90'+5'' -> 95 ; '45'+1'' -> 46 ; '29'' -> 29 ; '' -> None"""
    if not m:
        return None
    m = m.replace("'", " ").strip()
    parts = re.findall(r"\d+", m)
    if not parts:
        return None
    n = int(parts[0])
    if "+" in m and len(parts) > 1:
        n += int(parts[1])
    return n


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fifa_match_events (
            fifa_match_id INTEGER, stage_id INTEGER, event_id TEXT,
            minute TEXT, minute_num INTEGER, period INTEGER,
            type_code INTEGER, type_name TEXT,
            team_fifa_id TEXT, team_name TEXT, db_team_id INTEGER,
            player_name TEXT, player_fifa_id TEXT,
            pos_x REAL, pos_y REAL, description TEXT,
            PRIMARY KEY (fifa_match_id, event_id)
        )""")
    conn.commit()


def _calendar(conn):
    """{fifa_match_id: {stage, date, status, home_fid, away_fid, home_db, away_db, home_tid, away_tid}}"""
    d = _get(f"https://api.fifa.com/api/v3/calendar/matches"
             f"?idCompetition={COMP}&idSeason={SEASON}&count=300")
    res = d.get("Results", d.get("results", []))
    db_id = {r[0]: r[1] for r in conn.execute("SELECT name, id FROM teams")}
    out = {}
    for m in res:
        def side(key):
            t = m.get(key, {}) or {}
            tn = t.get("TeamName") or []
            nm = tn[0].get("Description", "") if tn else ""
            return t.get("IdTeam"), NAME.get(nm, nm)
        hf, hn = side("Home")
        af, an = side("Away")
        out[int(m["IdMatch"])] = {
            "stage": m.get("IdStage"), "date": m.get("Date"),
            "status": m.get("MatchStatus"),
            "home_fid": hf, "away_fid": af, "home_db": hn, "away_db": an,
            "home_tid": db_id.get(hn), "away_tid": db_id.get(an),
        }
    return out


def fetch_match(conn, fid, info):
    url = f"https://api.fifa.com/api/v3/timelines/{COMP}/{SEASON}/{info['stage']}/{fid}"
    evs = (_get(url) or {}).get("Event") or []
    conn.execute("DELETE FROM fifa_match_events WHERE fifa_match_id=?", (fid,))
    rows = []
    for e in evs:
        tfid = e.get("IdTeam")
        if tfid == info["home_fid"]:
            tname, tid = info["home_db"], info["home_tid"]
        elif tfid == info["away_fid"]:
            tname, tid = info["away_db"], info["away_tid"]
        else:
            tname, tid = None, None
        pn = ""
        if e.get("PlayerName"):
            pn = e["PlayerName"][0].get("Description", "")
        desc = ""
        if e.get("EventDescription"):
            desc = e["EventDescription"][0].get("Description", "")
        tc = e.get("Type")
        rows.append((fid, info["stage"], e.get("EventId"), e.get("MatchMinute"),
                     _minute_num(e.get("MatchMinute")), e.get("Period"),
                     tc, TYPE_NAMES.get(tc, str(tc)), tfid, tname, tid,
                     pn, e.get("IdPlayer"), e.get("PositionX"), e.get("PositionY"), desc))
    conn.executemany(
        "INSERT OR REPLACE INTO fifa_match_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def main():
    conn = sqlite3.connect(str(DB))
    _ensure_table(conn)
    cal = _calendar(conn)
    if len(sys.argv) > 1:
        targets = [int(x) for x in sys.argv[1:]]
    else:
        targets = [fid for fid, i in cal.items() if i["status"] == 0]
    print(f"Partidos a bajar: {len(targets)}")
    total = 0
    for i, fid in enumerate(sorted(targets), 1):
        info = cal.get(fid)
        if not info:
            print(f"  ! {fid} no está en el calendario, salto"); continue
        try:
            n = fetch_match(conn, fid, info)
            total += n
            print(f"  [{i}/{len(targets)}] {fid} {info['home_db']} vs {info['away_db']}: {n} eventos")
        except Exception as ex:
            print(f"  ! {fid} ERROR {type(ex).__name__}: {ex}")
        time.sleep(0.3)
    print(f"TOTAL eventos cargados: {total}")
    conn.close()


if __name__ == "__main__":
    main()
