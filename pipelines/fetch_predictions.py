"""
fetch_predictions.py — Integración con Football Prediction API (RapidAPI).

Endpoint: football-prediction-api.p.rapidapi.com
Obtiene predicciones externas por partido y las guarda en DB como señal adicional.
"""
import os
import json
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache" / "predictions"
DB_PATH   = BASE_DIR / "data" / "mundial2026.db"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

RAPIDAPI_KEY  = os.getenv("APIFOOT", "")
API_HOST      = "football-prediction-api.p.rapidapi.com"
BASE_URL      = f"https://{API_HOST}/api/v2"

HEADERS = {
    "x-rapidapi-host": API_HOST,
    "x-rapidapi-key":  RAPIDAPI_KEY,
}


def _cache_file(name: str) -> Path:
    today = datetime.now().strftime("%Y%m%d")
    return CACHE_DIR / f"{name}_{today}.json"


def _load_cache(name: str):
    p = _cache_file(name)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_cache(name: str, data):
    p = _cache_file(name)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_predictions_by_date(iso_date: str, federation: str = "FIFA") -> list:
    """
    Obtiene predicciones para todos los partidos de una fecha.
    iso_date: "2026-06-11"
    federation: "FIFA", "UEFA", "CONMEBOL", etc.
    """
    if not RAPIDAPI_KEY:
        print("  Sin APIFOOT key — saltando Football Prediction API")
        return []

    cache_key = f"pred_{federation}_{iso_date}"
    cached = _load_cache(cache_key)
    if cached:
        print(f"  [FP] Cache hit: {iso_date}")
        return cached

    try:
        r = requests.get(
            f"{BASE_URL}/predictions",
            headers=HEADERS,
            params={"market": "classic", "iso_date": iso_date, "federation": federation},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            _save_cache(cache_key, data)
            print(f"  [FP] {iso_date} {federation}: {len(data)} predicciones")
            return data
        print(f"  [FP] Error {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"  [FP] Exception: {e}")
    return []


def fetch_wc_predictions() -> list:
    """Descarga predicciones para todos los días del Mundial 2026 (11 jun – 19 jul)."""
    all_preds = []
    start = datetime(2026, 6, 11)
    end   = datetime(2026, 7, 19)
    current = start
    while current <= end:
        iso = current.strftime("%Y-%m-%d")
        preds = fetch_predictions_by_date(iso, "FIFA")
        all_preds.extend(preds)
        if preds:
            time.sleep(1.2)  # respeta rate limit
        current += timedelta(days=1)
    return all_preds


def fetch_match_prediction(home_team: str, away_team: str, match_date: str) -> dict:
    """
    Busca la predicción externa para un partido específico.
    Devuelve dict con probabilidades o {} si no hay datos.
    """
    preds = fetch_predictions_by_date(match_date, "FIFA")
    for p in preds:
        h = p.get("home_team", "").lower()
        a = p.get("away_team", "").lower()
        if home_team.lower() in h or h in home_team.lower():
            if away_team.lower() in a or a in away_team.lower():
                return p
    return {}


def save_predictions_to_db(predictions: list) -> int:
    """Guarda predicciones externas en tabla external_predictions."""
    if not predictions:
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Crea tabla si no existe
    cur.execute("""
        CREATE TABLE IF NOT EXISTS external_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_date      TEXT,
            home_team       TEXT,
            away_team       TEXT,
            federation      TEXT,
            prediction      TEXT,
            home_win_pct    REAL,
            draw_pct        REAL,
            away_win_pct    REAL,
            raw_json        TEXT,
            fetched_at      TEXT,
            UNIQUE(match_date, home_team, away_team)
        )
    """)

    saved = 0
    for p in predictions:
        try:
            result = p.get("result", "")
            odds = p.get("odds", {})

            # Intentar extraer probabilidades de distintos formatos de la API
            home_pct = float(p.get("home_win", odds.get("home", 0)) or 0)
            draw_pct = float(p.get("draw",     odds.get("draw", 0)) or 0)
            away_pct = float(p.get("away_win", odds.get("away", 0)) or 0)

            cur.execute("""
                INSERT OR REPLACE INTO external_predictions
                (match_date, home_team, away_team, federation, prediction,
                 home_win_pct, draw_pct, away_win_pct, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                p.get("start_date", p.get("date", ""))[:10],
                p.get("home_team", ""),
                p.get("away_team", ""),
                p.get("federation", "FIFA"),
                result,
                home_win_pct,
                draw_pct,
                away_win_pct,
                json.dumps(p),
                datetime.now().isoformat(),
            ))
            saved += cur.rowcount
        except Exception as e:
            print(f"  Error guardando predicción: {e}")

    conn.commit()
    conn.close()
    return saved


def get_external_prediction(home_team: str, away_team: str, match_date: str) -> dict:
    """Lee predicción externa de la DB para un partido."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Crea tabla si no existe
    conn.execute("""
        CREATE TABLE IF NOT EXISTS external_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_date TEXT, home_team TEXT, away_team TEXT,
            federation TEXT, prediction TEXT,
            home_win_pct REAL, draw_pct REAL, away_win_pct REAL,
            raw_json TEXT, fetched_at TEXT,
            UNIQUE(match_date, home_team, away_team)
        )
    """)

    row = conn.execute("""
        SELECT * FROM external_predictions
        WHERE match_date=? AND (
            (home_team LIKE ? AND away_team LIKE ?) OR
            (home_team LIKE ? AND away_team LIKE ?)
        )
    """, (
        match_date,
        f"%{home_team}%", f"%{away_team}%",
        f"%{away_team}%", f"%{home_team}%",
    )).fetchone()
    conn.close()
    return dict(row) if row else {}


def run():
    """Pipeline principal: descarga predicciones del Mundial completo."""
    print("\n=== Pipeline: Football Prediction API ===\n")

    if not RAPIDAPI_KEY:
        print("  Sin APIFOOT key. Configura en .env o GitHub Secrets.")
        return

    # Hoy y próximos 7 días primero
    today = datetime.now()
    priority_dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    all_saved = 0
    for date in priority_dates:
        preds = fetch_predictions_by_date(date, "FIFA")
        if preds:
            saved = save_predictions_to_db(preds)
            all_saved += saved
        time.sleep(1)

    print(f"\n  Total predicciones guardadas: {all_saved}")
    print("Pipeline Football Prediction completado.\n")


if __name__ == "__main__":
    run()
