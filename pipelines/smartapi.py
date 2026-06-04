"""
smartapi.py — Cliente para "Free API Live Football Data" (RapidAPI, Creativesdev).

Host: free-api-live-football-data.p.rapidapi.com
Endpoints confirmados (plan gratis, 100 req/día):
  /football-get-matches-by-date?date=YYYYMMDD   → {response:{matches:[...]}}
  /football-get-hometeam-lineup?eventid=ID      → {response:{lineup:{...}}}
  /football-get-awayteam-lineup?eventid=ID      → {response:{lineup:{...}}}
  /football-get-match-all-stats?eventid=ID       → {response:{stats:[...]}}
  /football-current-live                         → {response:{live:[...]}}
  /football-get-standing-all?leagueid=ID         → {response:{standing:[...]}}

El secret APIFOOT puede venir como blob multilínea; _clean_key extrae el token.
RapidAPI solo responde desde GitHub Actions (bloqueado localmente).
"""
from __future__ import annotations

import os
import re
import time

HOST = "free-api-live-football-data.p.rapidapi.com"


def clean_key(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if "\n" not in raw and " " not in raw and "=" not in raw:
        return raw
    m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", raw)
    return m.group(0) if m else raw


def get(path: str, params: dict | None = None, retries: int = 2) -> dict | None:
    """GET a un endpoint. Devuelve el objeto 'response' o None."""
    import requests

    key = clean_key(os.getenv("APIFOOT", ""))
    if not key:
        return None
    url = f"https://{HOST}{path}"
    headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=20)
            if r.status_code == 200:
                data = r.json()
                time.sleep(0.8)
                return data.get("response", data)
            if r.status_code == 429:
                print(f"  [smartapi] 429 rate limit en {path}, espera 30s...")
                time.sleep(30)
                continue
            print(f"  [smartapi] {path} → {r.status_code}")
            return None
        except Exception as e:
            print(f"  [smartapi] error {path}: {e}")
            time.sleep(2)
    return None


def matches_by_date(date_yyyymmdd: str) -> list:
    """Partidos de una fecha (formato YYYYMMDD)."""
    resp = get("/football-get-matches-by-date", {"date": date_yyyymmdd})
    if isinstance(resp, dict):
        return resp.get("matches", []) or []
    return []


def team_lineup(event_id, side: str) -> dict | None:
    """side = 'home' | 'away'. Devuelve el dict de lineup o None."""
    path = "/football-get-hometeam-lineup" if side == "home" else "/football-get-awayteam-lineup"
    resp = get(path, {"eventid": str(event_id)})
    if isinstance(resp, dict):
        lu = resp.get("lineup")
        if isinstance(lu, dict) and lu.get("starters"):
            return lu
    return None


def match_stats(event_id) -> list | None:
    """Estadísticas de equipo del partido (lista de grupos de stats) o None."""
    resp = get("/football-get-match-all-stats", {"eventid": str(event_id)})
    if isinstance(resp, dict):
        st = resp.get("stats")
        if isinstance(st, list) and st:
            return st
    return None


def flatten_team_stats(stats_groups: list) -> dict:
    """Convierte la estructura de grupos en {key: (home_val, away_val)}.

    Devuelve métricas clave normalizadas para match_stats:
      possession, xg, shots_total, shots_on_target, big_chances, corners, fouls.
    """
    flat: dict[str, tuple] = {}
    for group in stats_groups or []:
        for s in group.get("stats", []):
            key = s.get("key", "")
            vals = s.get("stats", [])
            if len(vals) == 2:
                flat[key] = (vals[0], vals[1])

    def _num(v):
        try:
            return float(str(v).replace("%", ""))
        except Exception:
            return None

    def pick(*keys):
        for k in keys:
            if k in flat:
                return _num(flat[k][0]), _num(flat[k][1])
        return (None, None)

    return {
        "possession":      pick("BallPossesion", "ball_possession"),
        "xg":              pick("expected_goals"),
        "shots_total":     pick("total_shots"),
        "shots_on_target": pick("ShotsOnTarget", "shots_on_target"),
        "big_chances":     pick("big_chance"),
        "corners":         pick("corners", "CornerKicks"),
        "fouls":           pick("fouls"),
        "saves":           pick("GoalkeeperSaves", "saves"),
        "passes":          pick("Passes", "passes"),
        "offsides":        pick("Offsides", "offsides"),
    }
