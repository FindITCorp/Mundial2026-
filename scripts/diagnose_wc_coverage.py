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

    # 5. PRUEBA CLAVE: ¿api-sports trae AMISTOSOS 2026 con MINUTOS por jugador?
    #    Friendlies = league 10. Esto decide si el objetivo (minutos) es viable.
    fr = out["friendlies_2026"] = {}
    st, d = _get(f"{base}/fixtures", h,
                 {"league": 10, "season": 2026, "from": "2026-06-01", "to": "2026-06-04"})
    fr["errors"] = d.get("errors") if isinstance(d, dict) else None
    fixtures = d.get("response", []) if isinstance(d, dict) else []
    fr["count"] = len(fixtures)
    fr["sample"] = []
    fid = None
    for f in fixtures[:8]:
        t = f.get("teams", {})
        fr["sample"].append(f"{t.get('home', {}).get('name')} vs {t.get('away', {}).get('name')}")
        if fid is None and t.get("home", {}).get("name"):
            fid = f.get("fixture", {}).get("id")
    # ¿Hay MINUTOS por jugador para un amistoso? (/fixtures/players)
    if fid:
        st_p, dp = _get(f"{base}/fixtures/players", h, {"fixture": fid})
        players = dp.get("response", []) if isinstance(dp, dict) else []
        sample_player = None
        if players and players[0].get("players"):
            pl = players[0]["players"][0]
            stats0 = (pl.get("statistics") or [{}])[0]
            sample_player = {
                "name": pl.get("player", {}).get("name"),
                "minutes": stats0.get("games", {}).get("minutes"),
                "rating": stats0.get("games", {}).get("rating"),
                "goals": stats0.get("goals", {}).get("total"),
            }
        fr["players_endpoint"] = {"fixture_id": fid, "teams": len(players),
                                  "sample_player": sample_player}


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


# ─────────────────────── football-data.org ───────────────────────
def test_football_data_org():
    """Testea football-data.org con FOOTBALL_DATA_KEY.
    Preguntas clave:
      1. ¿Qué competiciones cubre para 2026?
      2. ¿Tiene el WC2026 (FIFA World Cup)?
      3. ¿Tiene amistosos (Friendlies) de junio 2026?
      4. ¿Devuelve lineups con minutos por jugador?
    """
    key = os.getenv("FOOTBALL_DATA_KEY", "")
    out = report["football_data_org"] = {}
    if not key:
        out["error"] = "FOOTBALL_DATA_KEY no configurada"
        return

    base = "https://api.football-data.org/v4"
    h = {"X-Auth-Token": key}

    # 1. Plan / cuota
    st, d = _get(f"{base}/", h, {})
    out["status_root"] = st
    if isinstance(d, dict):
        out["plan"] = d.get("plan")
        out["version"] = d.get("version")
        out["message_root"] = d.get("message")

    # 2. Competiciones disponibles
    st, d = _get(f"{base}/competitions", h, {})
    out["competitions_status"] = st
    comps = []
    if isinstance(d, dict):
        for c in d.get("competitions", []):
            comps.append({
                "id": c.get("id"),
                "code": c.get("code"),
                "name": c.get("name"),
                "type": c.get("type"),
                "plan": c.get("plan"),
            })
    out["competitions"] = comps
    out["competitions_count"] = len(comps)

    # Buscar WC2026 específicamente
    wc_candidates = [c for c in comps if "world" in (c.get("name") or "").lower()
                     or c.get("code") in ("WC", "FIFA")]
    out["wc_candidates"] = wc_candidates

    # 3. Matches del WC2026 — probar código WC
    for code in ("WC", "FIFA", "CWC"):
        st, d = _get(f"{base}/competitions/{code}/matches", h,
                     {"dateFrom": "2026-06-11", "dateTo": "2026-06-12"})
        fixtures = []
        if isinstance(d, dict):
            for m in (d.get("matches") or [])[:5]:
                home = (m.get("homeTeam") or {}).get("name", "?")
                away = (m.get("awayTeam") or {}).get("name", "?")
                fixtures.append(f"{home} vs {away}")
        out[f"wc_matches_{code}"] = {"status": st, "count": len(fixtures), "sample": fixtures}
        if st == 200 and len(fixtures):
            break

    # 4. Amistosos junio 2026 — endpoint general /matches con dateFrom/dateTo
    st, d = _get(f"{base}/matches", h,
                 {"dateFrom": "2026-06-01", "dateTo": "2026-06-05"})
    out["friendlies_june_status"] = st
    friendlies = []
    fid = None
    if isinstance(d, dict):
        for m in (d.get("matches") or []):
            home = (m.get("homeTeam") or {}).get("name", "?")
            away = (m.get("awayTeam") or {}).get("name", "?")
            comp = (m.get("competition") or {}).get("name", "?")
            mid = m.get("id")
            friendlies.append(f"{home} vs {away} [{comp}] id={mid}")
            if fid is None:
                fid = mid
    out["friendlies_june"] = {"count": len(d.get("matches", [])) if isinstance(d, dict) else 0,
                               "sample": friendlies[:8]}

    # 5. ¿Hay lineup con minutos? — probar con primer partido encontrado
    if fid:
        st_l, dl = _get(f"{base}/matches/{fid}/lineups", h, {})
        out["lineups_endpoint"] = {"status": st_l, "fixture_id": fid}
        if isinstance(dl, dict):
            out["lineups_endpoint"]["keys"] = list(dl.keys())
            lineups = dl.get("lineups") or dl.get("response") or []
            if isinstance(lineups, list) and lineups:
                first = lineups[0]
                out["lineups_endpoint"]["first_keys"] = list(first.keys()) if isinstance(first, dict) else None
                # ¿tiene minutos por jugador?
                players = first.get("startXI") or first.get("lineup") or []
                if players:
                    sample_p = players[0]
                    out["lineups_endpoint"]["player_sample"] = sample_p
            out["lineups_endpoint"]["raw_200"] = json.dumps(dl, ensure_ascii=False)[:2000]

        # También probar /matches/{id}/head2head y /matches/{id} para ver la estructura
        st_m, dm = _get(f"{base}/matches/{fid}", h, {})
        out["match_detail_sample"] = {
            "status": st_m,
            "keys": list(dm.keys()) if isinstance(dm, dict) else None,
            "score": dm.get("score") if isinstance(dm, dict) else None,
        }
    else:
        out["lineups_endpoint"] = {"error": "no fixture found to test lineups"}

    # 6. Probar España-Iraq específicamente (2026-06-04) si existe
    st, d = _get(f"{base}/matches", h,
                 {"dateFrom": "2026-06-04", "dateTo": "2026-06-04"})
    spain_iraq = []
    spain_iraq_id = None
    if isinstance(d, dict):
        for m in (d.get("matches") or []):
            home = (m.get("homeTeam") or {}).get("name", "?")
            away = (m.get("awayTeam") or {}).get("name", "?")
            spain_iraq.append(f"{home} vs {away} id={m.get('id')}")
            if "spain" in home.lower() or "spain" in away.lower():
                spain_iraq_id = m.get("id")
    out["june4_matches"] = spain_iraq

    if spain_iraq_id:
        st_l, dl = _get(f"{base}/matches/{spain_iraq_id}/lineups", h, {})
        out["spain_iraq_lineups"] = {
            "status": st_l,
            "raw": json.dumps(dl, ensure_ascii=False)[:3000] if isinstance(dl, dict) else str(dl)
        }


# ─────────────────────── iSports API ───────────────────────
def test_isports():
    """Testea iSports API (isportsapi.com) con ISPORTS_KEY.
    Preguntas clave:
      1. ¿Tiene amistosos junio 2026 con lineup/minutos por jugador?
      2. ¿Tiene el WC2026 partidos?
      3. ¿Qué campos devuelve por jugador?
    Base: http://api.isportsapi.com  o  http://api2.isportsapi.com
    """
    key = os.getenv("ISPORTS_KEY", "")
    out = report["isports"] = {}
    if not key:
        out["error"] = "ISPORTS_KEY no configurada"
        return

    base = "http://api.isportsapi.com"

    def _iget(path, extra_params=None):
        params = {"api_key": key}
        if extra_params:
            params.update(extra_params)
        return _get(f"{base}{path}", {}, params)

    # 1. Livescores (sanity check que la key funciona)
    st, d = _iget("/sport/football/livescores")
    out["livescores_status"] = st
    out["livescores_sample"] = str(d)[:500] if isinstance(d, dict) else str(d)[:200]

    # 2. Amistosos/partidos junio 2026
    for date in ("2026-06-04", "2026-06-03", "2026-06-01"):
        st, d = _iget("/sport/football/fixtures", {"date": date})
        matches = []
        if isinstance(d, dict):
            for m in (d.get("data") or d.get("fixtures") or d.get("results") or [])[:10]:
                home = m.get("homeName") or m.get("homeTeam") or m.get("home_team") or "?"
                away = m.get("awayName") or m.get("awayTeam") or m.get("away_team") or "?"
                comp = m.get("leagueName") or m.get("competition") or ""
                mid = m.get("matchId") or m.get("id") or m.get("fixture_id")
                matches.append(f"{home} vs {away} [{comp}] id={mid}")
        out[f"fixtures_{date}"] = {"status": st, "count": len(matches), "sample": matches,
                                   "raw_keys": list(d.keys()) if isinstance(d, dict) else None}
        if matches:
            break

    # 3. Probar endpoints de lineup/player stats
    # Primero intentar encontrar un match_id reciente
    st, d = _iget("/sport/football/fixtures", {"date": "2026-06-04"})
    sample_mid = None
    if isinstance(d, dict):
        items = d.get("data") or d.get("fixtures") or d.get("results") or []
        if items:
            first = items[0]
            sample_mid = first.get("matchId") or first.get("id") or first.get("fixture_id")
            out["sample_match_raw"] = json.dumps(first, ensure_ascii=False)[:1000]

    out["lineup_tests"] = {}
    candidates = [
        "/sport/football/lineups",
        "/sport/football/lineup",
        "/sport/football/match/lineups",
        "/sport/football/match/players",
        "/sport/football/player/stats",
        "/sport/football/match/stats",
        "/sport/football/events",
    ]
    for path in candidates:
        params = {}
        if sample_mid:
            params["matchId"] = sample_mid
        st2, d2 = _iget(path, params)
        has = bool(d2) if isinstance(d2, dict) else False
        out["lineup_tests"][path] = {
            "status": st2,
            "has_data": has,
            "raw": json.dumps(d2, ensure_ascii=False)[:600] if isinstance(d2, dict) else str(d2)[:200]
        }

    # 4. WC2026 — buscar por liga/competición
    for path in ("/sport/football/leagues", "/sport/football/competitions",
                 "/sport/football/tournaments"):
        st, d = _iget(path)
        if isinstance(d, dict) and st == 200:
            items = d.get("data") or d.get("leagues") or d.get("results") or []
            wc = [x for x in items if "world" in str(x).lower() and "cup" in str(x).lower()]
            out[f"wc_search_{path.split('/')[-1]}"] = wc[:5]
            if wc:
                break


if __name__ == "__main__":
    test_apisports()
    test_rapidapi()
    probe_lineup_detail()
    test_football_data_org()
    test_isports()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
