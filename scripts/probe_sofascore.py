"""
Probe Sofascore RapidAPI — detecta host activo y obtiene últimos 5 partidos.
Siempre escribe sofascore_probe_results.json aunque falle.
"""
import os, json, time, traceback, pathlib

RESULTS = {
    "api_key_present": False,
    "hosts_tested": {},
    "working_host": None,
    "team_search": None,
    "near_events_status": None,
    "sample_matches": [],
    "errors": [],
}

SCRIPT_DIR = pathlib.Path(__file__).parent

def save():
    out = SCRIPT_DIR / "sofascore_probe_results.json"
    with open(out, "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)
    print(f"Resultados guardados en {out}")

try:
    import requests

    API_KEY = os.environ.get("INPUT_API_KEY") or os.environ.get("SECRET_API_KEY", "")
    TEAM = os.environ.get("TEAM_NAME", "Brazil")

    print(f"API_KEY presente: {bool(API_KEY)}")
    print(f"API_KEY (primeros 12): {API_KEY[:12] if API_KEY else 'VACÍO'}")
    print(f"Equipo: {TEAM}")

    RESULTS["api_key_present"] = bool(API_KEY)

    if not API_KEY:
        RESULTS["errors"].append("INPUT_API_KEY y SECRET_API_KEY están vacíos")
        save()
        exit(0)

    def get(host, path, params=None):
        url = f"https://{host}{path}"
        headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": host}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = r.text[:600]
            return r.status_code, body
        except Exception as e:
            return None, str(e)

    # --- Paso 1: Encontrar host Sofascore activo ---
    HOSTS = [
        ("sofascore.p.rapidapi.com",     "/api/v1/sport/football/scheduled-events/2026-06-12"),
        ("sofascore3.p.rapidapi.com",    "/api/v1/sport/football/scheduled-events/2026-06-12"),
        ("sofascore-v1.p.rapidapi.com",  "/api/v1/sport/football/scheduled-events/2026-06-12"),
        ("api-sofascore.p.rapidapi.com", "/api/v1/sport/football/scheduled-events/2026-06-12"),
    ]

    working_host = None
    for host, path in HOSTS:
        sc, data = get(host, path)
        RESULTS["hosts_tested"][host] = {"status": sc, "body": str(data)[:300]}
        print(f"{host}: HTTP {sc} → {str(data)[:120]}")
        if sc in (200, 429):
            working_host = host
            RESULTS["working_host"] = host
            break
        time.sleep(0.5)

    # --- Paso 2: Si ninguno funciona, probar APIs genéricas de fútbol ---
    if not working_host:
        ALT = [
            ("free-api-live-football-data.p.rapidapi.com", "/football-get-all-leagues", {}),
            ("footapi7.p.rapidapi.com",                    "/api/teams/search", {"name": TEAM}),
            ("api-football-v1.p.rapidapi.com",             "/v3/leagues", {}),
            ("football-live-scores2.p.rapidapi.com",       "/fixtures/date/2026-06-12", {}),
            ("sportscore1.p.rapidapi.com",                 "/sport-events", {}),
        ]
        for host, path, params in ALT:
            sc, data = get(host, path, params or None)
            RESULTS["hosts_tested"][f"alt:{host}"] = {"status": sc, "body": str(data)[:300]}
            print(f"ALT {host}: HTTP {sc} → {str(data)[:120]}")
            if sc in (200, 429):
                working_host = host
                RESULTS["working_host"] = host
                break
            time.sleep(0.3)

    # --- Paso 3: Con host activo, buscar equipo y últimos partidos ---
    if working_host:
        sc, data = get(working_host, "/api/v1/teams/search", {"query": TEAM})
        RESULTS["team_search"] = {"status": sc, "body": str(data)[:500]}
        print(f"Team search: HTTP {sc}")

        team_id = 3  # Brasil por defecto en Sofascore
        if sc == 200 and isinstance(data, dict):
            teams = data.get("teams", data.get("results", data.get("data", [])))
            if isinstance(teams, list) and teams:
                tid = teams[0].get("id")
                if tid:
                    team_id = tid

        sc2, data2 = get(working_host, f"/api/v1/team/{team_id}/near-events/0")
        RESULTS["near_events_status"] = sc2
        RESULTS["near_events_body"] = str(data2)[:500]
        print(f"Near events (team {team_id}): HTTP {sc2}")

        if sc2 == 200 and isinstance(data2, dict):
            events = data2.get("previousEvents", data2.get("events", []))
            for ev in (events or [])[-5:]:
                RESULTS["sample_matches"].append({
                    "home": ev.get("homeTeam", {}).get("name"),
                    "away": ev.get("awayTeam", {}).get("name"),
                    "score_home": ev.get("homeScore", {}).get("current"),
                    "score_away": ev.get("awayScore", {}).get("current"),
                    "date": ev.get("startTimestamp"),
                })
    else:
        RESULTS["errors"].append("Ningún host respondió con 200 o 429. Key inválida o sin suscripción Sofascore.")

except Exception as e:
    RESULTS["errors"].append(f"EXCEPCION: {traceback.format_exc()}")
    print(f"ERROR: {e}")

finally:
    save()
