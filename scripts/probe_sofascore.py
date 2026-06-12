"""
Probe Sofascore RapidAPI — detecta host activo y últimos 5 partidos.
Pushea resultados via GitHub API (sin git) para garantizar entrega.
"""
import os, json, time, traceback, base64, urllib.request

RESULTS = {
    "api_key_present": False,
    "hosts_tested": {},
    "working_host": None,
    "team_search": None,
    "near_events_status": None,
    "near_events_body": None,
    "sample_matches": [],
    "errors": [],
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "FindITCorp/Mundial2026-"
TARGET_FILE = "scripts/sofascore_probe_results.json"


def gh_push(content_str):
    """Sube el archivo a GitHub via API."""
    if not GITHUB_TOKEN:
        print("Sin GITHUB_TOKEN — no se puede pushear via API")
        return
    api_url = f"https://api.github.com/repos/{REPO}/contents/{TARGET_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    # Obtener SHA actual si existe
    sha = None
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            existing = json.loads(r.read().decode())
            sha = existing.get("sha")
    except Exception:
        pass

    body = {
        "message": "data: sofascore rapidapi probe results",
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha

    data = json.dumps(body).encode()
    req = urllib.request.Request(api_url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode())
            print(f"✅ GitHub push OK: {resp.get('commit', {}).get('sha', '?')[:8]}")
    except Exception as e:
        print(f"❌ GitHub push FAIL: {e}")


try:
    import requests

    API_KEY = os.environ.get("INPUT_API_KEY") or os.environ.get("SECRET_API_KEY", "")
    TEAM = os.environ.get("TEAM_NAME", "Brazil")

    print(f"API_KEY presente: {bool(API_KEY)}")
    print(f"API_KEY (primeros 15 chars): {repr(API_KEY[:15]) if API_KEY else 'VACÍO'}")
    print(f"Equipo buscado: {TEAM}")

    RESULTS["api_key_present"] = bool(API_KEY)
    RESULTS["api_key_len"] = len(API_KEY)

    if not API_KEY:
        RESULTS["errors"].append("INPUT_API_KEY y SECRET_API_KEY están vacíos")
        raise RuntimeError("Sin API key")

    def get(host, path, params=None):
        url = f"https://{host}{path}"
        hdrs = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": host}
        try:
            r = requests.get(url, headers=hdrs, params=params, timeout=15)
            try:
                body = r.json()
            except Exception:
                body = r.text[:600]
            return r.status_code, body
        except Exception as e:
            return None, str(e)

    # --- Paso 1: Hosts Sofascore ---
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
        print(f"{host}: HTTP {sc} | {str(data)[:100]}")
        if sc in (200, 429):
            working_host = host
            RESULTS["working_host"] = host
            break
        time.sleep(0.5)

    # --- Paso 2: Alternativas si Sofascore no funciona ---
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
            print(f"ALT {host}: HTTP {sc} | {str(data)[:100]}")
            if sc in (200, 429):
                working_host = host
                RESULTS["working_host"] = host
                break
            time.sleep(0.3)

    # --- Paso 3: Buscar equipo y últimos partidos ---
    if working_host:
        sc, data = get(working_host, "/api/v1/teams/search", {"query": TEAM})
        RESULTS["team_search"] = {"status": sc, "body": str(data)[:500]}
        print(f"Team search: HTTP {sc}")

        team_id = 3
        if sc == 200 and isinstance(data, dict):
            teams = data.get("teams", data.get("results", []))
            if isinstance(teams, list) and teams:
                tid = teams[0].get("id")
                if tid:
                    team_id = tid

        sc2, data2 = get(working_host, f"/api/v1/team/{team_id}/near-events/0")
        RESULTS["near_events_status"] = sc2
        RESULTS["near_events_body"] = str(data2)[:500]
        print(f"Near events (team_id={team_id}): HTTP {sc2}")

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
        RESULTS["errors"].append(
            "Ningún host respondió con 200/429. Key sin suscripción Sofascore en RapidAPI."
        )

except Exception as e:
    RESULTS["errors"].append(f"EXCEPCION: {traceback.format_exc()}")
    print(f"ERROR: {e}")

finally:
    out_str = json.dumps(RESULTS, indent=2, ensure_ascii=False)
    print("\n=== RESULTADO FINAL ===")
    print(out_str)
    print("=======================")
    gh_push(out_str)
