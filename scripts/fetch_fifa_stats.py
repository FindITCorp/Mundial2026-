"""
fetch_fifa_stats.py — Carga los stats AVANZADOS de FIFA FDH (Enhanced Football
Intelligence) de TODOS los partidos. 142 stats/equipo, API abierta, más detallado
que Sofascore: GoalkeeperSaves/%, presiones (high/mid/low press y block),
line-breaks, ball progressions, attempts por zona/tipo, etc.

COMPLEMENTA sin perder:
- Tabla NUEVA fifa_fdh_stats (tall: match_id, team_id, stat, value) → los 142 stats
  íntegros, sin tocar nada.
- Rellena match_team_stats SOLO donde está NULL (saves, possession, tiros…), así el
  analizador y el modelo se benefician. xG de Sofascore queda intacto (FDH no da xG).

Mapeo: calendario FIFA da Properties.IdIFES (= id FDH) y Home/Away.IdTeam (FIFA).
FDH: https://fdh-api.fifa.com/v1/stats/match/{idIFES}/teams.json

Uso: python scripts/fetch_fifa_stats.py
"""
import json
import sqlite3
import urllib.request
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "mundial2026.db"
COMP, SEASON = 17, 285023

NAME = {"Cabo Verde": "Cape Verde", "Congo DR": "DR Congo", "Curaçao": "Curacao",
        "Côte d'Ivoire": "Ivory Coast", "IR Iran": "Iran",
        "Korea Republic": "South Korea", "Türkiye": "Turkey"}

# FDH stat -> columna match_team_stats (solo se rellena si está NULL). xG NO (Sofascore).
FILL = {
    "GoalkeeperSaves": ("saves", 1), "Corners": ("corners", 1),
    "AttemptAtGoal": ("shots_total", 1), "AttemptAtGoalOnTarget": ("shots_on_target", 1),
    "AttemptAtGoalOffTarget": ("shots_off_target", 1), "AttemptAtGoalBlocked": ("shots_blocked", 1),
    "AttemptAtGoalInsideThePenaltyArea": ("shots_inside_box", 1),
    "AttemptAtGoalOutsideThePenaltyArea": ("shots_outside_box", 1),
    "Offsides": ("offsides", 1), "Passes": ("passes_total", 1),
    "PassesCompleted": ("passes_accurate", 1), "Crosses": ("crosses_total", 1),
    "CrossesCompleted": ("crosses_accurate", 1), "FoulsFor": ("fouls", 1),
    "Possession": ("possession", 100),  # 0.57 -> 57
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=25))


def _tname(team):
    n = team.get("TeamName")
    return n[0]["Description"] if isinstance(n, list) and n else None


def sync(db_path=DB, verbose=True):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS fifa_fdh_stats (
        match_id INTEGER, team_id INTEGER, stat TEXT, value REAL,
        PRIMARY KEY (match_id, team_id, stat))""")

    def db_id(name):
        nm = NAME.get(name, name)
        r = conn.execute("SELECT id FROM teams WHERE name=?", (nm,)).fetchone()
        return r[0] if r else None

    cal = _get(f"https://api.fifa.com/api/v3/calendar/matches?idCompetition={COMP}&idSeason={SEASON}&count=300")
    played = [m for m in cal["Results"] if m.get("MatchStatus") == 0 and m.get("HomeTeamScore") is not None]

    # FIFA team id -> DB id (desde el calendario)
    fifa2db = {}
    for m in played:
        for side in ("Home", "Away"):
            fid = m[side].get("IdTeam"); nm = _tname(m[side])
            if fid and nm:
                fifa2db[fid] = db_id(nm)

    nstats = nmatches = filled = 0
    for m in played:
        ifes = (m.get("Properties") or {}).get("IdIFES")
        if not ifes:
            continue
        hid, aid = db_id(_tname(m["Home"])), db_id(_tname(m["Away"]))
        mid = conn.execute(
            "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND stage='group'",
            (hid, aid)).fetchone()
        if not mid:
            continue
        mid = mid[0]
        try:
            data = _get(f"https://fdh-api.fifa.com/v1/stats/match/{ifes}/teams.json")
        except Exception:
            continue
        nmatches += 1
        for fifa_tid, statlist in data.items():
            tid = fifa2db.get(fifa_tid) or fifa2db.get(int(fifa_tid)) if str(fifa_tid).isdigit() else None
            tid = fifa2db.get(fifa_tid)
            if not tid:
                continue
            vals = {}
            for entry in statlist:
                stat, val = entry[0], entry[1]
                vals[stat] = val
                conn.execute("INSERT OR REPLACE INTO fifa_fdh_stats (match_id,team_id,stat,value) VALUES (?,?,?,?)",
                             (mid, tid, stat, val if isinstance(val, (int, float)) else None))
                nstats += 1
            # rellenar match_team_stats donde NULL
            for fdh, (col, mult) in FILL.items():
                if fdh in vals and isinstance(vals[fdh], (int, float)):
                    v = round(vals[fdh] * mult, 1) if mult != 1 else vals[fdh]
                    r = conn.execute("SELECT id FROM match_team_stats WHERE match_id=? AND team_id=?", (mid, tid)).fetchone()
                    if r:
                        conn.execute(f"UPDATE match_team_stats SET {col}=COALESCE({col},?) WHERE id=?", (v, r[0]))
                    else:
                        is_home = 1 if tid == hid else 0
                        conn.execute(f"INSERT INTO match_team_stats (match_id,team_id,is_home,{col}) VALUES (?,?,?,?)", (mid, tid, is_home, v))
                    filled += 1
    conn.commit()
    conn.close()
    if verbose:
        print(f"FDH: {nmatches} partidos | {nstats} stats cargados | {filled} campos rellenados en match_team_stats")


if __name__ == "__main__":
    sync()
