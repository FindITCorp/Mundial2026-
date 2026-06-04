"""diagnose_wc_coverage.py — ¿Qué API cubre el WC2026 con datos COMPLETOS?

Prueba api-sports.io (APISPORTS_KEY) y la RapidAPI "Free API Live Football Data"
(APIFOOT) para responder, sin ambigüedad:
  1. ¿Cuánta cuota queda en cada una?
  2. ¿Existe el WC2026 como liga? ¿Con qué league_id?
  3. ¿Tienen los fixtures de la jornada 1 (11-jun-2026)?
  4. ¿Tienen DATOS INCREMENTALES (lineups, stats) por partido?

Corre SOLO desde GitHub Actions (las APIs están bloqueadas localmente).
Escribe data/lineups/wc_coverage_report.json para inspección.
"""
import os
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "lineups" / "wc_coverage_report.json"

APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")
APIFOOT = os.getenv("APIFOOT", "")

report = {"ran_at": datetime.utcnow().isoformat(), "apisports": {}, "rapidapi": {}}


def _get(url, headers, params, timeout=15):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        return r.status_code, r.json()
    except Exception as e:
        return None, {"error": str(e)}


# ─────────────────────────── api-sports.io ───────────────────────────
def test_apisports():
    out = report["apisports"]
    if not APISPORTS_KEY:
        out["error"] = "APISPORTS_KEY no configurada"
        return
    base = "https://v3.football.api-sports.io"
    h = {"x-apisports-key": APISPORTS_KEY}

    # 1. Cuota
    st, d = _get(f"{base}/status", h, {})
    if isinstance(d, dict):
        resp = d.get("response", {})
        out["plan"] = resp.get("subscription", {}).get("plan")
        out["requests"] = resp.get("requests", {})

    # 2. Liga WC2026 — buscar por varios criterios
    ligas = []
    for params in ({"search": "World Cup"}, {"id": 1}, {"type": "cup", "current": "true"}):
        st, d = _get(f"{base}/leagues", h, params)
        for item in (d.get("response", []) if isinstance(d, dict) else []):
            lg = item.get("league", {})
            seasons = [s.get("year") for s in item.get("seasons", [])]
            name = lg.get("name", "")
            if "world" in name.lower() or lg.get("id") == 1:
                ligas.append({"id": lg.get("id"), "name": name,
                              "type": lg.get("type"), "seasons": seasons[-5:]})
    out["leagues_wc"] = ligas

    # 3. Fixtures jornada 1 — probar varios league_id candidatos
    out["fixtures"] = {}
    candidate_ids = [1] + [l["id"] for l in ligas if l.get("id")]
    for lid in dict.fromkeys(candidate_ids):
        st, d = _get(f"{base}/fixtures", h,
                     {"league": lid, "season": 2026, "from": "2026-06-11", "to": "2026-06-12"})
        fixtures = d.get("response", []) if isinstance(d, dict) else []
        sample = []
        first_fixture_id = None
        for f in fixtures[:3]:
            t = f.get("teams", {})
            sample.append(f"{t.get('home', {}).get('name')} vs {t.get('away', {}).get('name')}")
            if first_fixture_id is None:
                first_fixture_id = f.get("fixture", {}).get("id")
        out["fixtures"][str(lid)] = {"count": len(fixtures), "sample": sample,
                                     "first_fixture_id": first_fixture_id}

        # 4. ¿Datos incrementales? (lineups + stats del primer fixture si existe)
        if first_fixture_id:
            st_l, dl = _get(f"{base}/fixtures/lineups", h, {"fixture": first_fixture_id})
            st_s, ds = _get(f"{base}/fixtures/statistics", h, {"fixture": first_fixture_id})
            out["incremental_sample"] = {
                "fixture_id": first_fixture_id,
                "lineups_available": len(dl.get("response", [])) if isinstance(dl, dict) else 0,
                "stats_available": len(ds.get("response", [])) if isinstance(ds, dict) else 0,
            }


# ─────────────────────── RapidAPI (lo del $20) ───────────────────────
def test_rapidapi():
    out = report["rapidapi"]
    if not APIFOOT:
        out["error"] = "APIFOOT no configurada"
        return
    # extraer token limpio si viene como blob
    import re
    key = APIFOOT.strip()
    m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", key)
    if m:
        key = m.group(0)
    host = "free-api-live-football-data.p.rapidapi.com"
    h = {"x-rapidapi-host": host, "x-rapidapi-key": key}
    base = f"https://{host}"

    # ¿Tiene fixtures del 11-jun-2026? (sistema de IDs propio)
    st, d = _get(f"{base}/football-get-matches-by-date", h, {"date": "20260611"})
    matches = []
    if isinstance(d, dict):
        matches = d.get("response", {}).get("matches", []) or d.get("response", []) or []
    out["status_20260611"] = st
    out["matches_count"] = len(matches) if isinstance(matches, list) else 0
    # Volcar TODOS los partidos del 11-jun con su estructura real
    all_matches = []
    sample_raw = None
    for m_ in (matches if isinstance(matches, list) else []):
        if sample_raw is None:
            sample_raw = list(m_.keys())  # ver qué campos trae cada match
        home = (m_.get("home") or {}).get("name") or m_.get("homeTeam") or "?"
        away = (m_.get("away") or {}).get("name") or m_.get("awayTeam") or "?"
        league = m_.get("leagueName") or m_.get("league") or m_.get("tournament") or ""
        all_matches.append(f"{home} vs {away} [{league}] id={m_.get('id')}")
    out["match_fields"] = sample_raw
    out["all_matches_20260611"] = all_matches


def probe_lineup_detail():
    """Volcar la estructura CRUDA del lineup de un amistoso senior terminado, para
    ver qué campos por jugador trae la RapidAPI (minutos, subs, goles, tarjetas) y
    qué endpoints adicionales existen (player-stats / events / match-details)."""
    out = report["lineup_detail"] = {}
    if not APIFOOT:
        out["error"] = "APIFOOT no configurada"
        return
    import re
    key = APIFOOT.strip()
    m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", key)
    if m:
        key = m.group(0)
    host = "free-api-live-football-data.p.rapidapi.com"
    h = {"x-rapidapi-host": host, "x-rapidapi-key": key}
    base = f"https://{host}"
    eid = "5729607"  # Panama vs Dominican Republic (senior, terminado)

    # 1. Lineup local crudo — VOLCAR ESTRUCTURA REAL completa (truncada)
    st, d = _get(f"{base}/football-get-hometeam-lineup", h, {"eventid": eid})
    out["lineup_status"] = st
    out["top_keys"] = list(d.keys()) if isinstance(d, dict) else type(d).__name__
    resp = d.get("response") if isinstance(d, dict) else None
    out["response_type"] = type(resp).__name__
    if isinstance(resp, dict):
        out["response_keys"] = list(resp.keys())
    elif isinstance(resp, list) and resp:
        out["response_list_len"] = len(resp)
        out["response_first_keys"] = list(resp[0].keys()) if isinstance(resp[0], dict) else None
    # Volcado crudo truncado para ver la forma exacta
    raw = json.dumps(d, ensure_ascii=False)
    out["raw_sample_2500"] = raw[:2500]

    # 2. Probar endpoints candidatos de detalle por jugador / eventos
    out["candidate_endpoints"] = {}
    for path in ("/football-get-match-player-stats",
                 "/football-get-player-stats",
                 "/football-get-match-events",
                 "/football-get-match-details",
                 "/football-get-lineups-detail",
                 "/football-get-match-lineups"):
        st2, d2 = _get(f"{base}{path}", h, {"eventid": eid})
        keys = list(d2.get("response", {}).keys()) if isinstance(d2, dict) and isinstance(d2.get("response"), dict) else None
        out["candidate_endpoints"][path] = {"status": st2, "response_keys": keys,
                                            "has_data": bool(d2.get("response")) if isinstance(d2, dict) else False}


if __name__ == "__main__":
    test_apisports()
    test_rapidapi()
    probe_lineup_detail()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
