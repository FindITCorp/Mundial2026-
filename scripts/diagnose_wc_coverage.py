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

    # 2. Liga WC2026
    st, d = _get(f"{base}/leagues", h, {"name": "World Cup", "season": 2026})
    ligas = []
    for item in (d.get("response", []) if isinstance(d, dict) else []):
        lg = item.get("league", {})
        ligas.append({"id": lg.get("id"), "name": lg.get("name"), "type": lg.get("type")})
    out["leagues_wc2026"] = ligas

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
    # Buscar partidos que parezcan del Mundial (selecciones top)
    wc_like = []
    for m_ in (matches if isinstance(matches, list) else [])[:200]:
        home = (m_.get("home") or {}).get("name", "")
        away = (m_.get("away") or {}).get("name", "")
        if any(x in f"{home} {away}" for x in ["Mexico", "Argentina", "Germany", "Italy", "France"]):
            wc_like.append(f"{home} vs {away} (id={m_.get('id')})")
    out["wc_like_matches"] = wc_like[:10]


if __name__ == "__main__":
    test_apisports()
    test_rapidapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
