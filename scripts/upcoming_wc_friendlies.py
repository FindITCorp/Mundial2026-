"""
upcoming_wc_friendlies.py — Busca próximos amistosos internacionales con
equipos WC2026, registra resultados pendientes y corre predicciones.
"""
import json
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
TSDB     = "https://www.thesportsdb.com/api/v1/json/3"

# Mapping TheSportsDB → nuestra DB
TSDB_TO_DB = {
    "United States": "USA", "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia", "Congo DR": "DR Congo",
    "Cabo Verde": "Cape Verde", "Türkiye": "Turkey",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
}

WC_TEAMS = {
    "Algeria","Argentina","Australia","Austria","Belgium","Bolivia",
    "Bosnia and Herzegovina","Brazil","Cameroon","Canada","Cape Verde",
    "Colombia","Costa Rica","Croatia","Curacao","Czechia","DR Congo",
    "Denmark","Ecuador","Egypt","England","France","Germany","Ghana",
    "Haiti","Honduras","Hungary","Iran","Iraq","Italy","Ivory Coast",
    "Jamaica","Japan","Jordan","Mexico","Morocco","Netherlands",
    "New Zealand","Nigeria","Norway","Panama","Paraguay","Poland",
    "Portugal","Qatar","Romania","Saudi Arabia","Scotland","Senegal",
    "Serbia","Slovenia","South Africa","South Korea","Spain","Sweden",
    "Switzerland","Tunisia","Turkey","USA","Uruguay","Uzbekistan","Venezuela"
}


def _resolve(name: str) -> str:
    return TSDB_TO_DB.get(name, name)


def _is_wc(name: str) -> bool:
    return _resolve(name) in WC_TEAMS


def _get(path, params):
    try:
        r = requests.get(f"{TSDB}{path}", params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [tsdb] {path}: {e}")
    return None


def _team_id(conn, name):
    r = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    return r[0] if r else None


def _insert_result(conn, home_db, away_db, hg, ag, ev_date, dry=False):
    """Inserta resultado en team_matches con protección de duplicados."""
    inserted = 0
    for our_name, opp_name, gf, ga in [
        (home_db, away_db, hg, ag),
        (away_db, home_db, ag, hg),
    ]:
        if our_name not in WC_TEAMS and opp_name not in WC_TEAMS:
            continue
        tid = _team_id(conn, our_name)
        if not tid:
            continue
        exists = conn.execute(
            "SELECT 1 FROM team_matches WHERE team_id=? AND date=? AND opponent_name=?",
            (tid, ev_date, opp_name)).fetchone()
        if exists:
            continue
        result = "W" if gf > ga else ("D" if gf == ga else "L")
        if dry:
            print(f"    [DRY] {our_name} {gf}-{ga} {opp_name} ({ev_date})")
        else:
            conn.execute(
                "INSERT OR IGNORE INTO team_matches "
                "(team_id,opponent_id,opponent_name,date,competition,goals_for,goals_against,result) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (tid, _team_id(conn, opp_name), opp_name, ev_date, "Friendly", gf, ga, result))
        inserted += 1
    return inserted


def fetch_upcoming_and_results(days_back=3, days_ahead=10):
    """Devuelve (resultados_nuevos, proximos_partidos)."""
    today = date.today()
    results_new = []
    upcoming = {}

    for delta in range(-days_back, days_ahead + 1):
        d = (today + timedelta(days=delta)).isoformat()
        data = _get("/eventsday.php", {"d": d, "s": "Soccer"})
        if not data:
            time.sleep(0.5)
            continue
        for ev in (data.get("events") or []):
            home_tsdb = ev.get("strHomeTeam", "")
            away_tsdb = ev.get("strAwayTeam", "")
            league    = ev.get("strLeague", "")
            home_db   = _resolve(home_tsdb)
            away_db   = _resolve(away_tsdb)

            # Solo amistosos internacionales
            if "friendly" not in league.lower() and "international" not in league.lower():
                continue
            # Al menos un equipo WC2026
            if not (_is_wc(home_tsdb) or _is_wc(away_tsdb)):
                continue

            score_h = ev.get("intHomeScore")
            score_a = ev.get("intAwayScore")
            has_score = score_h is not None and score_a is not None

            entry = {
                "date": d, "home": home_db, "away": away_db,
                "home_wc": _is_wc(home_tsdb), "away_wc": _is_wc(away_tsdb),
                "league": league, "id": ev.get("idEvent"),
                "score_h": int(score_h) if has_score else None,
                "score_a": int(score_a) if has_score else None,
            }
            key = f"{d}|{home_db}|{away_db}"

            if delta <= 0 and has_score:
                results_new.append(entry)
            elif delta > 0 and not has_score:
                upcoming[key] = entry

        time.sleep(0.4)

    return results_new, list(upcoming.values())


def predict_match(home, away):
    """Llama al predictor canónico y devuelve texto."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from models.match_predictor import predict_match as pm
        result = pm(home, away, db_path=str(DB_PATH))
        if not result:
            return None
        hw = result.get("home_win_pct", 0)
        dw = result.get("draw_pct", 0)
        aw = result.get("away_win_pct", 0)
        xgh = result.get("xg_home", 0)
        xga = result.get("xg_away", 0)
        score = result.get("most_likely_score", "?-?")
        return {
            "home_win": round(hw, 1), "draw": round(dw, 1), "away_win": round(aw, 1),
            "xg_home": round(xgh, 2), "xg_away": round(xga, 2), "score": score,
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)

    print("=" * 70)
    print("SINCRONIZANDO RESULTADOS RECIENTES...")
    print("=" * 70)
    results_new, upcoming = fetch_upcoming_and_results()

    new_total = 0
    for ev in results_new:
        n = _insert_result(conn, ev["home"], ev["away"],
                           ev["score_h"], ev["score_a"], ev["date"])
        if n > 0:
            star_h = "★" if ev["home_wc"] else " "
            star_a = "★" if ev["away_wc"] else " "
            print(f"  ✅ {ev['date']}  {star_h}{ev['home']} {ev['score_h']}-{ev['score_a']} {ev['away']}{star_a}")
            new_total += n
    conn.commit()
    print(f"  → {new_total} filas insertadas\n")

    print("=" * 70)
    print("PRÓXIMOS AMISTOSOS INTERNACIONALES CON EQUIPOS WC2026")
    print("=" * 70)

    if not upcoming:
        print("  Sin amistosos internacionales encontrados en los próximos 10 días.")
    else:
        for ev in sorted(upcoming, key=lambda x: x["date"]):
            star_h = "★" if ev["home_wc"] else " "
            star_a = "★" if ev["away_wc"] else " "
            print(f"\n  📅 {ev['date']}  {star_h}{ev['home']} vs {star_a}{ev['away']}")

            # Solo predecir si al menos UN equipo es WC2026
            home_ok = ev["home"] in WC_TEAMS
            away_ok = ev["away"] in WC_TEAMS
            pred_home = ev["home"] if home_ok else None
            pred_away = ev["away"] if away_ok else None

            if not (home_ok or away_ok):
                print("     (ningún equipo en WC2026 — skip predicción)")
                continue

            p = predict_match(ev["home"], ev["away"])
            if not p or "error" in p:
                print(f"     ⚠️  Sin predicción: {p}")
            else:
                print(f"     xG: {p['xg_home']} - {p['xg_away']}  |  "
                      f"Resultado más probable: {p['score']}")
                print(f"     {ev['home']} gana {p['home_win']}%  |  "
                      f"Empate {p['draw']}%  |  "
                      f"{ev['away']} gana {p['away_win']}%")

    conn.close()
    print("\n" + "=" * 70)
