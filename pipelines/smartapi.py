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

import json
import os
import re
import time
from pathlib import Path

HOST = "free-api-live-football-data.p.rapidapi.com"

# Caché en disco (data/cache/smartapi) + memoización en-run para no gastar cuota.
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "smartapi"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MEM: dict = {}

# TTL por tipo de endpoint (segundos). Lineups/stats de partidos terminados no
# cambian → TTL larguísimo. matches-by-date de fechas pasadas tampoco.
_TTL_LONG = 60 * 60 * 24 * 30   # 30 días
_TTL_LIVE = 60 * 2             # 2 min para current-live


def _cache_path(path: str, params: dict) -> Path:
    key = (path + "_" + "_".join(f"{k}{v}" for k, v in sorted((params or {}).items())))
    key = re.sub(r"[^0-9a-zA-Z_]", "", key)
    return _CACHE_DIR / f"{key}.json"


def clean_key(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if "\n" not in raw and " " not in raw and "=" not in raw:
        return raw
    m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", raw)
    return m.group(0) if m else raw


def get(path: str, params: dict | None = None, retries: int = 2,
        ttl: int = _TTL_LONG) -> dict | None:
    """GET a un endpoint con caché en disco + memoización. Devuelve 'response' o None."""
    import requests

    params = params or {}
    cache_file = _cache_path(path, params)
    mem_key = str(cache_file)

    # 1) memoización en-run
    if mem_key in _MEM:
        return _MEM[mem_key]

    # 2) caché en disco (no gasta cuota)
    if cache_file.exists() and ttl > 0:
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            try:
                data = json.loads(cache_file.read_text())
                resp = data.get("response", data)
                _MEM[mem_key] = resp
                return resp
            except Exception:
                pass

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
                # FALLO BLANDO: la API devuelve 200 con {"status":"failed",
                # "message":"Request Failed Please try Again"}. NO cachear (envenena
                # el caché) y reintentar con back-off — es intermitente.
                if isinstance(data, dict) and str(data.get("status", "")).lower() == "failed":
                    if attempt < retries:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    return None
                try:
                    cache_file.write_text(json.dumps(data, ensure_ascii=False))
                except Exception:
                    pass
                time.sleep(0.8)
                resp = data.get("response", data)
                _MEM[mem_key] = resp
                return resp
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


def matches_by_date(date_yyyymmdd: str, fresh: bool = False) -> list:
    """Partidos de una fecha (formato YYYYMMDD). fresh=True ignora caché (hoy/en vivo)."""
    ttl = _TTL_LIVE if fresh else _TTL_LONG
    resp = get("/football-get-matches-by-date", {"date": date_yyyymmdd}, ttl=ttl)
    if isinstance(resp, dict):
        return resp.get("matches", []) or []
    return []


def team_lineup(event_id, side: str) -> dict | None:
    """side = 'home' | 'away'. Devuelve el dict de lineup o None.

    El endpoint es intermitente ('Request Failed'), así que reintentamos más veces.
    """
    path = "/football-get-hometeam-lineup" if side == "home" else "/football-get-awayteam-lineup"
    resp = get(path, {"eventid": str(event_id)}, retries=4)
    if isinstance(resp, dict):
        lu = resp.get("lineup")
        if isinstance(lu, dict) and lu.get("starters"):
            return lu
        # algunas variantes devuelven el lineup directo en response
        if resp.get("starters"):
            return resp
    return None


def match_stats(event_id) -> list | None:
    """Estadísticas de equipo del partido (lista de grupos de stats) o None."""
    resp = get("/football-get-match-all-stats", {"eventid": str(event_id)})
    if isinstance(resp, dict):
        st = resp.get("stats")
        if isinstance(st, list) and st:
            return st
    return None


_ODDS_PATH_FILE = _CACHE_DIR / "_odds_path.txt"


def match_odds(event_id) -> dict | None:
    """Cuotas pre-partido. Recuerda el path que funciona para no gastar llamadas.

    La 1ª vez prueba candidatos (máx 4 req); guarda el path bueno y luego usa 1.
    """
    # Si ya descubrimos el path, usar solo ese (1 request)
    if _ODDS_PATH_FILE.exists():
        path = _ODDS_PATH_FILE.read_text().strip()
        if path:
            resp = get(path, {"eventid": str(event_id)})
            if isinstance(resp, dict) and resp and "message" not in resp:
                return {"path": path, "data": resp}
            return None

    for path in ("/football-get-match-odds", "/football-get-odds",
                 "/football-get-pre-match-odds", "/football-get-match-prematch-odds"):
        resp = get(path, {"eventid": str(event_id)})
        if isinstance(resp, dict) and resp and "message" not in resp:
            try:
                _ODDS_PATH_FILE.write_text(path)
            except Exception:
                pass
            return {"path": path, "data": resp}
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
