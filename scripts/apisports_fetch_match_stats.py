"""
apisports_fetch_match_stats.py — Fetchea resultados + stats de partidos WC
para fechas históricas usando el pipeline existente del proyecto.

Uso:
  python scripts/apisports_fetch_match_stats.py                  # hoy + ayer
  python scripts/apisports_fetch_match_stats.py 2026-06-15
  python scripts/apisports_fetch_match_stats.py 2026-06-15,2026-06-16
"""
import os, sys, sqlite3, json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"
sys.path.insert(0, str(ROOT))

NAME_MAP = {
    "United States": "USA", "Korea Republic": "South Korea",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde", "Cape Verde Islands": "Cape Verde",
    "Bosnia": "Bosnia and Herzegovina", "Czech Republic": "Czechia",
    "Congo DR": "DR Congo", "Türkiye": "Turkey",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Rep. Of Ireland": "Republic of Ireland",
}

def resolve(name):
    return NAME_MAP.get(name, name)

def get_team_id(conn, name):
    n = resolve(name)
    r = conn.execute("SELECT id FROM teams WHERE LOWER(name)=LOWER(?)", (n,)).fetchone()
    return r[0] if r else None

def val(raw, key, default=None):
    v = raw.get(key, default)
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace("%", ""))
    except Exception:
        return default

def process_date(target_date, conn):
    print(f"\n=== {target_date} ===")

    # Usar el fetcher existente del proyecto (ya sabe el formato correcto de api-sports)
    try:
        from scripts.fetch_apisports_today import run as fetch_run
        data = fetch_run(target_date=target_date)
    except Exception as e:
        print(f"  fetch_apisports_today falló: {e}")
        return 0, 0

    if not data:
        print("  Sin datos de api-sports")
        return 0, 0

    if data.get("error"):
        print(f"  Error api-sports: {data['error']}")
        return 0, 0

    fixtures = data.get("fixtures", [])
    print(f"  {data.get('wc_fixtures_count', 0)} fixtures WC encontrados")

    # Guardar el JSON actualizado para que store_apisports_today.py pueda usarlo
    out = ROOT / "data" / "lineups" / "apisports_today.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    # Cargar lineups y player_nat_stats con el script existente
    try:
        from scripts.store_apisports_today import run as store_run
        store_run()
    except Exception as e:
        print(f"  store_apisports_today: {e}")

    # Adicionalmente: actualizar wc_matches + match_team_stats + match_player_stats
    scores_saved = 0
    players_saved = 0
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    for fix in fixtures:
        if fix.get("status") not in ("FT", "AET", "PEN"):
            print(f"  {fix.get('home')} vs {fix.get('away')}: status={fix.get('status')}, skip")
            continue

        home_name = fix["home"]
        away_name = fix["away"]
        home_id   = get_team_id(conn, home_name)
        away_id   = get_team_id(conn, away_name)

        if not home_id or not away_id:
            print(f"  Equipos no encontrados: {home_name}({home_id}) vs {away_name}({away_id})")
            continue

        score_str = fix.get("score", "None-None")
        parts = score_str.split("-")
        try:
            sh = int(parts[0])
            sa = int(parts[1])
        except Exception:
            print(f"  Score inválido: {score_str}")
            continue

        # Buscar match en wc_matches
        wm = conn.execute(
            "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND date=?",
            (home_id, away_id, target_date)
        ).fetchone()

        if not wm:
            print(f"  No en wc_matches: {home_name} vs {away_name}")
            continue

        wm_id = wm[0]

        # Actualizar resultado
        conn.execute(
            "UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
            (sh, sa, wm_id)
        )
        # Espejo en team_matches
        for tid, opp_id, opp_name, gf, ga, venue in [
            (home_id, away_id, resolve(away_name), sh, sa, "home"),
            (away_id, home_id, resolve(home_name), sa, sh, "away"),
        ]:
            res = "W" if gf > ga else ("D" if gf == ga else "L")
            conn.execute("""
                INSERT OR IGNORE INTO team_matches
                  (team_id, opponent_id, opponent_name, date, competition,
                   goals_for, goals_against, result, venue)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (tid, opp_id, opp_name, target_date,
                  "FIFA World Cup 2026", gf, ga, res, venue))
        scores_saved += 1
        print(f"  [{wm_id}] {home_name} {sh}-{sa} {away_name} -> guardado")

        # Team stats desde los lineups del fixture (si los hay)
        # match_player_stats desde players del fixture
        for tdata in fix.get("players", []):
            t_id = get_team_id(conn, tdata["team"])
            if not t_id:
                continue
            for p in tdata.get("players", []):
                if not p.get("name") or not p.get("minutes"):
                    continue
                POS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
                pos = POS.get((p.get("position") or "")[:1], p.get("position", ""))
                conn.execute("""
                    INSERT OR REPLACE INTO match_player_stats
                      (match_date, competition, home_team_id, away_team_id, team_id,
                       player_name, position, minutes, goals, assists, rating, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    target_date, "FIFA World Cup 2026",
                    home_id, away_id, t_id,
                    p["name"], pos, p.get("minutes", 0),
                    p.get("goals") or 0, p.get("assists") or 0,
                    float(p["rating"]) if p.get("rating") else None,
                    now,
                ))
                players_saved += 1

    conn.commit()
    return scores_saved, players_saved


def run(target_dates):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    total_scores  = 0
    total_players = 0
    for d in target_dates:
        s, p = process_date(d, conn)
        total_scores  += s
        total_players += p

    conn.close()
    print(f"\nTotal: {total_scores} resultados, {total_players} player stats")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0]:
        dates = [d.strip() for d in ",".join(args).split(",") if d.strip()]
    else:
        today = date.today()
        dates = [(today - timedelta(days=1)).isoformat(), today.isoformat()]
    run(dates)
