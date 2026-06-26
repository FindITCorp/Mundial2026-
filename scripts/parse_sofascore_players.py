"""
parse_sofascore_players.py — Carga stats POR JUGADOR desde el crudo Sofascore
(data/sofascore_raw/{id}/lineups.json + event.json) a match_player_stats.

Completa el hueco: parse_sofascore_raw.py cargaba solo stats de EQUIPO; los stats
por jugador (rating, minutos, goles, asistencias, titular/suplente) vivían solo en
13 partidos cargados a mano. Este parser los carga para cualquier partido del que
haya crudo Sofascore.

Idempotente: por defecto SALTA un partido si ya tiene filas en match_player_stats
(preserva las 13 cargas previas). --force re-escribe (delete+insert).

Uso:
    python scripts/parse_sofascore_players.py              # todos los dirs en sofascore_raw
    python scripts/parse_sofascore_players.py 15186907     # solo ese
    python scripts/parse_sofascore_players.py --force      # re-escribe existentes
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "mundial2026.db"
RAW = BASE / "data" / "sofascore_raw"

NAME = {"Czech Republic": "Czechia", "Curaçao": "Curacao", "Türkiye": "Turkey",
        "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
        "Cabo Verde": "Cape Verde", "Congo DR": "DR Congo", "IR Iran": "Iran",
        "Korea Republic": "South Korea", "United States": "USA",
        "Bosnia & Herzegovina": "Bosnia and Herzegovina"}


def _tid(conn, sofa_name):
    nm = NAME.get(sofa_name, sofa_name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (nm,)).fetchone()
    return r[0] if r else None


def _pair(won, lost):
    if won is None and lost is None:
        return None, None
    won = won or 0
    lost = lost or 0
    return won, won + lost


def _rows_for_side(side_obj, team_id):
    out = []
    for p in side_obj.get("players", []):
        st = p.get("statistics") or {}
        mins = st.get("minutesPlayed")
        if not st or not mins:
            continue  # suplente NO usado (sin minutos): no entra como participante
        name = (p.get("player") or {}).get("name")
        dw, dt = _pair(st.get("duelWon"), st.get("duelLost"))
        aw, at = _pair(st.get("aerialWon"), st.get("aerialLost"))
        tp = st.get("totalPass"); ap = st.get("accuratePass")
        out.append({
            "team_id": team_id,
            "player_name": name,
            "position": p.get("position"),
            "minutes": st.get("minutesPlayed"),
            "goals": st.get("goals") or 0,
            "assists": st.get("goalAssist") or 0,
            "rating": st.get("rating"),
            "passes_accurate": ap,
            "passes_total": tp,
            "passes_pct": round(100 * ap / tp, 1) if (tp and ap is not None) else None,
            "tackles_total": st.get("totalTackle"),
            "tackles_won": st.get("wonTackle"),
            "duels_won": dw, "duels_total": dt,
            "aerial_won": aw, "aerial_total": at,
            "substitute": 1 if p.get("substitute") else 0,
        })
    return out


def parse_dir(conn, ev_dir: Path, force=False):
    ev_f = ev_dir / "event.json"
    lu_f = ev_dir / "lineups.json"
    if not ev_f.exists() or not lu_f.exists():
        return f"{ev_dir.name}: faltan event/lineups"
    ev = json.loads(ev_f.read_text(encoding="utf-8"))["event"]
    hid = _tid(conn, ev["homeTeam"]["name"])
    aid = _tid(conn, ev["awayTeam"]["name"])
    if not hid or not aid:
        return f"{ev_dir.name}: no resuelvo equipos ({ev['homeTeam']['name']}/{ev['awayTeam']['name']})"
    wm = conn.execute(
        "SELECT id, date FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND stage='group'",
        (hid, aid)).fetchone()
    if not wm:
        return f"{ev_dir.name}: sin partido en wc_matches"
    mdate = wm[1]

    existing = conn.execute(
        "SELECT COUNT(*) FROM match_player_stats WHERE match_date=? "
        "AND home_team_id=? AND away_team_id=?", (mdate, hid, aid)).fetchone()[0]
    if existing and not force:
        return f"{ev_dir.name}: YA tiene {existing} jugadores (skip; usa --force)"
    if existing and force:
        conn.execute("DELETE FROM match_player_stats WHERE match_date=? "
                     "AND home_team_id=? AND away_team_id=?", (mdate, hid, aid))

    lu = json.loads(lu_f.read_text(encoding="utf-8"))
    rows = _rows_for_side(lu.get("home", {}), hid) + _rows_for_side(lu.get("away", {}), aid)
    n = 0
    for r in rows:
        conn.execute("""INSERT INTO match_player_stats
            (match_date, competition, home_team_id, away_team_id, team_id, player_name,
             position, minutes, goals, assists, rating, passes_accurate, passes_total,
             passes_pct, tackles_total, tackles_won, duels_total, duels_won,
             aerial_total, aerial_won, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
            (mdate, "World Cup", hid, aid, r["team_id"], r["player_name"], r["position"],
             r["minutes"], r["goals"], r["assists"], r["rating"], r["passes_accurate"],
             r["passes_total"], r["passes_pct"], r["tackles_total"], r["tackles_won"],
             r["duels_total"], r["duels_won"], r["aerial_total"], r["aerial_won"]))
        n += 1
    subs = sum(1 for r in rows if r["substitute"])
    return f"{ev_dir.name}: {ev['homeTeam']['name']} vs {ev['awayTeam']['name']} → {n} jugadores ({subs} suplentes)"


def run(ids=None, force=False):
    conn = sqlite3.connect(str(DB))
    dirs = ([RAW / str(e) for e in ids] if ids
            else sorted(d for d in RAW.iterdir() if d.is_dir())) if RAW.exists() else []
    for d in dirs:
        print("  " + parse_dir(conn, d, force=force))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    ids = [a for a in sys.argv[1:] if not a.startswith("--")] or None
    run(ids=ids, force=force)
