"""
apisports_fetch_match_stats.py — Fetchea resultados + team stats + player stats
de partidos WC desde api-sports para fechas dadas.

Uso:
  python scripts/apisports_fetch_match_stats.py                  # hoy + ayer
  python scripts/apisports_fetch_match_stats.py 2026-06-15
  python scripts/apisports_fetch_match_stats.py 2026-06-15,2026-06-16
"""
import os, sys, sqlite3, time, requests
from datetime import date, datetime, timedelta
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
        print(f"  [LIMITE] {MAX_REQ} requests alcanzado")
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

def resolve(name):
    return NAME_MAP.get(name, name)

def get_team_id(conn, name):
    n = resolve(name)
    row = conn.execute("SELECT id FROM teams WHERE LOWER(name)=LOWER(?)", (n,)).fetchone()
    return row[0] if row else None

def val(raw, key, default=None):
    v = raw.get(key, default)
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace("%", ""))
    except Exception:
        return default

def run(target_dates):
    if not KEY:
        print("APISPORTS_KEY no configurada.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    total_fixtures = 0
    total_players  = 0

    for target_date in target_dates:
        print(f"\n=== {target_date} ===")

        wc_matches = conn.execute(
            "SELECT id, home_team_name, away_team_name, home_team_id, away_team_id, score_home, score_away "
            "FROM wc_matches WHERE date=? AND wc_group IS NOT NULL",
            (target_date,)
        ).fetchall()

        if not wc_matches:
            wc_matches = conn.execute(
                "SELECT id, home_team_name, away_team_name, home_team_id, away_team_id, score_home, score_away "
                "FROM wc_matches WHERE date=?",
                (target_date,)
            ).fetchall()

        print(f"  {len(wc_matches)} partidos WC en la DB para {target_date}")
        if not wc_matches:
            continue

        # Sin league/season — api-sports bloquea el Mundial 2026 por temporada
        fixtures_data = api_get("/fixtures", {"date": target_date, "timezone": "UTC"})
        time.sleep(0.5)
        if not fixtures_data or not fixtures_data.get("response"):
            print(f"  Sin fixtures en api-sports para {target_date}")
            continue

        # Filtrar solo partidos donde al menos un equipo sea WC
        WC_TEAMS = set(NAME_MAP.values()) | {
            "Algeria","Argentina","Australia","Austria","Belgium","Bolivia",
            "Bosnia and Herzegovina","Brazil","Canada","Cape Verde","Colombia",
            "Costa Rica","Croatia","Curacao","Czechia","DR Congo","Ecuador",
            "Egypt","England","France","Germany","Ghana","Haiti","Iran","Iraq",
            "Ivory Coast","Japan","Jordan","Mexico","Morocco","Netherlands",
            "New Zealand","Norway","Panama","Paraguay","Portugal","Qatar",
            "Saudi Arabia","Scotland","Senegal","South Africa","South Korea",
            "Spain","Sweden","Switzerland","Tunisia","Turkey","USA","Uruguay",
            "Uzbekistan","Venezuela",
        }
        all_fixtures = fixtures_data["response"]
        fixtures = [
            f for f in all_fixtures
            if resolve(f["teams"]["home"]["name"]) in WC_TEAMS
            or resolve(f["teams"]["away"]["name"]) in WC_TEAMS
        ]
        print(f"  {len(all_fixtures)} fixtures totales, {len(fixtures)} con equipos WC")

        for wm in wc_matches:
            wm_id     = wm["id"]
            home_name = wm["home_team_name"]
            away_name = wm["away_team_name"]
            home_id   = wm["home_team_id"]
            away_id   = wm["away_team_id"]

            existing = conn.execute(
                "SELECT COUNT(*) FROM match_player_stats WHERE home_team_id=? AND match_date=?",
                (home_id, target_date)
            ).fetchone()[0]
            if existing > 10:
                print(f"  [{wm_id}] {home_name} vs {away_name}: {existing} player stats ya cargados, skip")
                continue

            fix = None
            for f in fixtures:
                fh = resolve(f["teams"]["home"]["name"])
                fa = resolve(f["teams"]["away"]["name"])
                if home_name.lower() in fh.lower() and away_name.lower() in fa.lower():
                    fix = f
                    break

            if not fix:
                print(f"  [{wm_id}] {home_name} vs {away_name}: no encontrado en api-sports")
                continue

            fix_id = fix["fixture"]["id"]
            sh     = fix["goals"]["home"]
            sa     = fix["goals"]["away"]
            status = fix["fixture"]["status"]["short"]
            print(f"\n  [{wm_id}] {home_name} {sh}-{sa} {away_name} (fix={fix_id}, {status})")

            # Resultado
            if status == "FT" and sh is not None:
                conn.execute(
                    "UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
                    (sh, sa, wm_id)
                )
                for tid, opp_id, opp_name, gf, ga, venue in [
                    (home_id, away_id, away_name, sh, sa, "home"),
                    (away_id, home_id, home_name, sa, sh, "away"),
                ]:
                    res = "W" if gf > ga else ("D" if gf == ga else "L")
                    conn.execute("""
                        INSERT OR IGNORE INTO team_matches
                          (team_id, opponent_id, opponent_name, date, competition,
                           goals_for, goals_against, result, venue)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (tid, opp_id, opp_name, target_date,
                          "FIFA World Cup 2026", gf, ga, res, venue))
                print(f"    resultado: {sh}-{sa}")

            # Team stats
            stats_data = api_get("/fixtures/statistics", {"fixture": fix_id})
            time.sleep(0.5)
            if stats_data and stats_data.get("response"):
                for ts in stats_data["response"]:
                    t_id = get_team_id(conn, ts["team"]["name"])
                    if not t_id:
                        continue
                    raw = {s["type"]: s["value"] for s in ts["statistics"]}
                    conn.execute("""
                        INSERT OR REPLACE INTO match_team_stats
                          (match_id, team_id, is_home, possession, shots_total,
                           shots_on_target, corners, fouls, yellow_cards, red_cards,
                           passes_total, passes_accurate, passes_pct, saves)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        wm_id, t_id, int(t_id == home_id),
                        val(raw,"Ball Possession"), val(raw,"Total Shots"),
                        val(raw,"Shots on Goal"),   val(raw,"Corner Kicks"),
                        val(raw,"Fouls"),            val(raw,"Yellow Cards"),
                        val(raw,"Red Cards"),        val(raw,"Total passes"),
                        val(raw,"Passes accurate"),  val(raw,"Passes %"),
                        val(raw,"Goalkeeper Saves"),
                    ))
                    print(f"    team_stats {ts['team']['name']}: poss={val(raw,'Ball Possession')} shots={val(raw,'Total Shots')}")

            # Player stats
            players_data = api_get("/fixtures/players", {"fixture": fix_id})
            time.sleep(0.5)
            if players_data and players_data.get("response"):
                now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                p_ins = 0
                POS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
                for tb in players_data["response"]:
                    t_id = get_team_id(conn, tb["team"]["name"])
                    if not t_id:
                        continue
                    for p in tb.get("players", []):
                        pi   = p.get("player", {})
                        st   = (p.get("statistics") or [{}])[0]
                        g    = st.get("games", {})
                        mins = g.get("minutes") or 0
                        if not mins:
                            continue
                        pos  = POS.get((g.get("position") or "")[:1], g.get("position",""))
                        gls  = st.get("goals", {})
                        pas  = st.get("passes", {})
                        tck  = st.get("tackles", {})
                        dls  = st.get("duels", {})
                        air  = st.get("aerial", {})
                        sht  = st.get("shots", {})
                        conn.execute("""
                            INSERT OR REPLACE INTO match_player_stats
                              (match_date, competition, home_team_id, away_team_id, team_id,
                               player_name, position, minutes, goals, assists, rating,
                               shots_total, shots_on_target,
                               passes_total, passes_accurate, passes_pct,
                               tackles_total, duels_total, duels_won,
                               aerial_total, aerial_won, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            target_date, "FIFA World Cup 2026",
                            home_id, away_id, t_id,
                            pi.get("name",""), pos, mins,
                            gls.get("total") or 0, gls.get("assists") or 0,
                            g.get("rating"),
                            sht.get("total"), sht.get("on"),
                            pas.get("total"), pas.get("accuracy"), pas.get("accuracy"),
                            tck.get("total"), dls.get("total"), dls.get("won"),
                            air.get("total"), air.get("won"), now,
                        ))
                        p_ins += 1
                total_players += p_ins
                total_fixtures += 1
                print(f"    {p_ins} player stats")

            conn.commit()

    conn.close()
    print(f"\nTotal: {total_fixtures} fixtures, {total_players} player stats | {_reqs[0]} requests")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        dates = [d.strip() for d in ",".join(args).split(",")]
    else:
        today = date.today()
        dates = [(today - timedelta(days=1)).isoformat(), today.isoformat()]
    run(dates)
