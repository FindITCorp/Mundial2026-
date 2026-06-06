"""
store_apisports_today.py — Lee data/lineups/apisports_today.json y graba
lineups + player_nat_stats en la DB. Idempotente (INSERT OR IGNORE).
"""
import json, sqlite3, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
IN_FILE  = BASE_DIR / "data" / "lineups" / "apisports_today.json"

MAP = {
    "Czech Republic": "Czechia", "Korea Republic": "South Korea",
    "United States": "USA",      "Rep. Of Ireland": "Ireland",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Congo DR": "DR Congo",      "Cabo Verde": "Cape Verde",
    "Türkiye": "Turkey",         "Bosnia-Herzegovina": "Bosnia and Herzegovina",
}

def run(db_path=None, in_file=None):
    db_path = Path(db_path or DB_PATH)
    in_file = Path(in_file or IN_FILE)
    if not in_file.exists():
        print("  apisports_today.json no encontrado — skip")
        return

    data = json.loads(in_file.read_text())
    if not data.get("key_configured"):
        print("  API key no configurada — skip")
        return

    conn = sqlite3.connect(str(db_path))

    def tid(name):
        n = MAP.get(name, name)
        r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
        return r[0] if r else None

    def pid(team_id, name):
        r = conn.execute("SELECT id FROM players WHERE team_id=? AND name=?", (team_id, name)).fetchone()
        if r: return r[0]
        parts = name.strip().split()
        if len(parts) >= 2:
            r = conn.execute("SELECT id FROM players WHERE team_id=? AND name LIKE ?",
                             (team_id, f"%{parts[-1]}%")).fetchone()
            if r: return r[0]
        return None

    def get_or_create_match(htid, atid, date, score):
        sc = (score or "0-0").split("-")
        hg = int(sc[0]) if sc[0].isdigit() else None
        ag = int(sc[1]) if len(sc)>1 and sc[1].isdigit() else None
        r = conn.execute(
            "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND date=?",
            (htid, atid, date)).fetchone()
        if r: return r[0]
        hn = conn.execute("SELECT name FROM teams WHERE id=?", (htid,)).fetchone()[0]
        an = conn.execute("SELECT name FROM teams WHERE id=?", (atid,)).fetchone()[0]
        conn.execute(
            "INSERT INTO wc_matches (home_team_id,away_team_id,date,home_team_name,away_team_name,"
            "score_home,score_away,stage,played) VALUES (?,?,?,?,?,?,?,'Friendly',1)",
            (htid, atid, date, hn, an, hg, ag))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    ins_lu = ins_ns = 0
    match_date = data["date"]

    for fix in data.get("fixtures", []):
        if fix["status"] not in ("FT", "AET", "PEN"):
            continue
        htid = tid(fix["home"])
        atid = tid(fix["away"])
        if not htid or not atid:
            continue

        match_id = get_or_create_match(htid, atid, match_date, fix["score"])

        # Lineups
        for lu in fix.get("lineups", []):
            t = tid(lu["team"])
            if not t: continue
            for pname in (lu.get("starters") or []):
                p = pid(t, pname)
                if p and not conn.execute(
                        "SELECT 1 FROM match_lineups WHERE match_id=? AND player_id=?",
                        (match_id, p)).fetchone():
                    conn.execute(
                        "INSERT OR IGNORE INTO match_lineups "
                        "(match_id,team_id,player_id,position,starter) VALUES (?,?,?,?,1)",
                        (match_id, t, p, "UNK"))
                    ins_lu += 1

        # Player stats
        for tdata in fix.get("players", []):
            t = tid(tdata["team"])
            if not t: continue
            opp_raw = fix["away"] if tdata["team"] == fix["home"] else fix["home"]
            opp = MAP.get(opp_raw, opp_raw)
            for p in tdata.get("players", []):
                if not p.get("name") or p.get("minutes") is None:
                    continue
                plid = pid(t, p["name"])
                if not plid: continue
                if not conn.execute(
                        "SELECT 1 FROM player_nat_stats WHERE player_id=? AND match_id=?",
                        (plid, match_id)).fetchone():
                    conn.execute(
                        "INSERT OR IGNORE INTO player_nat_stats "
                        "(player_id,match_id,match_date,opponent,minutes,goals,assists,rating,was_starter) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (plid, match_id, match_date, opp,
                         p["minutes"] or 0, p["goals"] or 0, p["assists"] or 0,
                         float(p["rating"]) if p["rating"] else None, 1))
                    ins_ns += 1

    conn.commit()
    conn.close()
    print(f"  match_lineups: +{ins_lu}  player_nat_stats: +{ins_ns}  (fecha: {match_date})")

if __name__ == "__main__":
    run()
