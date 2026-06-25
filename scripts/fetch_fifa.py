"""
fetch_fifa.py — Fetcher de la API ABIERTA de FIFA (api.fifa.com, sin anti-bot).

COMPLEMENTA los datos de Sofascore, NO los reemplaza. FIFA aporta lo que faltaba:
alineaciones (XI titular) de TODOS los partidos jugados, formación, goles con
minuto y posesión — sin el muro de URLs de Sofascore. Los datos ricos de Sofascore
(xG, regates, goles-evitados) se conservan intactos: FIFA escribe en TABLAS NUEVAS
(fifa_lineups, fifa_match_goals) y solo rellena match_team_stats donde está NULL.

API:
  /calendar/matches?idCompetition=17&idSeason=285023   → todos los partidos (IdMatch, score, MatchStatus)
  /live/football/{comp}/{seas}/{stage}/{match}         → alineaciones (Players.Status==1), goles, posesión

Uso:
    python scripts/fetch_fifa.py            # todos los partidos jugados
    python scripts/fetch_fifa.py --dry-run
"""
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

COMP, SEASON = 17, 285023

# FIFA TeamName -> teams.name DB
NAME = {
    "Cabo Verde": "Cape Verde", "Congo DR": "DR Congo", "Curaçao": "Curacao",
    "Côte d'Ivoire": "Ivory Coast", "IR Iran": "Iran",
    "Korea Republic": "South Korea", "Türkiye": "Turkey",
    "USA": "USA", "Bosnia and Herzegovina": "Bosnia and Herzegovina",
}


def _fifa(path):
    req = urllib.request.Request("https://api.fifa.com/api/v3/" + path,
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=25))


def _tname(team):
    n = team.get("TeamName")
    return n[0]["Description"] if isinstance(n, list) and n else None


def _pname(p):
    for k in ("PlayerName", "ShortName"):
        v = p.get(k)
        if isinstance(v, list) and v:
            return v[0]["Description"]
    return None


def _tid(conn, fifa_name):
    nm = NAME.get(fifa_name, fifa_name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (nm,)).fetchone()
    return r[0] if r else None


def _ensure_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS fifa_lineups (
        match_id INTEGER, team_id INTEGER, player_name TEXT, shirt INTEGER,
        position INTEGER, is_starter INTEGER, source TEXT DEFAULT 'fifa',
        PRIMARY KEY (match_id, team_id, player_name))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS fifa_match_goals (
        match_id INTEGER, team_id INTEGER, scorer TEXT, minute INTEGER, type TEXT,
        PRIMARY KEY (match_id, team_id, scorer, minute))""")


def _match_id(conn, hid, aid):
    r = conn.execute(
        "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND stage='group'",
        (hid, aid)).fetchone()
    return r[0] if r else None


def sync(db_path=DB, dry_run=False, verbose=True):
    conn = sqlite3.connect(str(db_path))
    _ensure_tables(conn)

    cal = _fifa(f"calendar/matches?idCompetition={COMP}&idSeason={SEASON}&count=300")
    played = [m for m in cal["Results"] if m.get("MatchStatus") == 0
              and m.get("HomeTeamScore") is not None]

    lus = goals = matches = unresolved = 0
    for m in played:
        hid = _tid(conn, _tname(m["Home"]))
        aid = _tid(conn, _tname(m["Away"]))
        if not hid or not aid:
            unresolved += 1
            continue
        mid = _match_id(conn, hid, aid)
        if not mid:
            unresolved += 1
            continue
        try:
            liv = _fifa(f"live/football/{COMP}/{SEASON}/{m['IdStage']}/{m['IdMatch']}")
        except Exception:
            continue
        matches += 1
        for side, tid in (("HomeTeam", hid), ("AwayTeam", aid)):
            t = liv.get(side, {})
            for p in t.get("Players", []):
                nm = _pname(p)
                if not nm:
                    continue
                starter = 1 if p.get("Status") == 1 else 0
                if not dry_run:
                    conn.execute(
                        "INSERT OR IGNORE INTO fifa_lineups "
                        "(match_id,team_id,player_name,shirt,position,is_starter) VALUES (?,?,?,?,?,?)",
                        (mid, tid, nm, p.get("ShirtNumber"), p.get("Position"), starter))
                lus += 1
            for g in (t.get("Goals") or []):
                gp = _pname(g) or g.get("IdPlayer")
                mins = g.get("Minute")
                if not dry_run and mins is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO fifa_match_goals (match_id,team_id,scorer,minute,type) "
                        "VALUES (?,?,?,?,?)", (mid, tid, str(gp), _min_int(mins), str(g.get("Type"))))
                goals += 1
        # posesión: rellenar match_team_stats solo si NULL (complementar)
        bp = liv.get("BallPossession") or {}
        if not dry_run and bp:
            for side, tid, key in (("HomeTeam", hid, "HomeTeamPercentage"),
                                   ("AwayTeam", aid, "AwayTeamPercentage")):
                val = bp.get(key)
                if val:
                    conn.execute(
                        "UPDATE match_team_stats SET possession=COALESCE(possession,?) "
                        "WHERE match_id=? AND team_id=?", (round(float(val)), mid, tid))

    if not dry_run:
        conn.commit()
    conn.close()
    if verbose:
        tag = "[DRY-RUN] " if dry_run else ""
        print(f"{tag}FIFA: {matches} partidos | {lus} jugadores (lineups) | {goals} goles | "
              f"{unresolved} sin resolver")
    return {"matches": matches, "lineups": lus, "goals": goals}


def _min_int(mins):
    try:
        return int(str(mins).split("+")[0].rstrip("'"))
    except Exception:
        return None


if __name__ == "__main__":
    sync(dry_run="--dry-run" in sys.argv)
