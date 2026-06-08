"""
probe_live_api.py — Prueba Free API Live Football Data y sube resultados via GitHub API.
"""
import base64
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
_raw_key = os.environ.get("APIFOOT", "")
# Secret may be a multi-line .env file — extract API_FOOTBALL_KEY line if present
KEY = _raw_key.strip()
if "\n" in KEY or "=" in KEY:
    for line in KEY.splitlines():
        line = line.strip()
        if "API_FOOTBALL_KEY" in line or "APIFOOT" in line:
            KEY = line.split("=", 1)[-1].strip()
            break
        elif line and "=" not in line:
            KEY = line  # bare key, use as-is
HOST  = "free-api-live-football-data.p.rapidapi.com"
HDRS  = {"x-rapidapi-host": HOST, "x-rapidapi-key": KEY}
TODAY     = datetime.utcnow().strftime("%Y-%m-%d")
YESTERDAY = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO  = os.environ.get("GITHUB_REPOSITORY", "")
GH_BRANCH= os.environ.get("GITHUB_REF_NAME", "main")


def api_get(path, params=None):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": f"HTTP {e.code}", "body": e.read().decode()[:200]}
    except Exception as e:
        return 0, {"error": str(e)}


def push_to_github(path, content_str, message="chore: API probe results"):
    """Create or update a file in the GitHub repo via REST API."""
    if not GH_TOKEN or not GH_REPO:
        print("  [push] No GITHUB_TOKEN or REPO — skipping upload")
        return False
    api_url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    encoded = base64.b64encode(content_str.encode()).decode()
    # Get current SHA if file exists
    sha = None
    try:
        req = urllib.request.Request(api_url, headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            existing = json.loads(r.read().decode())
            sha = existing.get("sha")
    except Exception:
        pass  # file doesn't exist yet

    payload = {"message": message, "content": encoded, "branch": GH_BRANCH}
    if sha:
        payload["sha"] = sha
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        api_url, data=data, method="PUT",
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status = r.status
            print(f"  [push] GitHub API → {status} {'CREATED' if status==201 else 'UPDATED'}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  [push] GitHub API error {e.code}: {e.read().decode()[:200]}")
        return False


results = {}

print(f"Key: {'SET len=' + str(len(KEY)) if KEY else 'EMPTY — all calls will fail'}")
print(f"Repo: {GH_REPO}  Branch: {GH_BRANCH}")
print(f"Today={TODAY}  Yesterday={YESTERDAY}")


def probe(name, path, params=None):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    print(f"\n=== {name}  {url}")
    status, data = api_get(path, params)
    print(f"  HTTP {status}")
    if isinstance(data, dict):
        err = data.get("error") or data.get("body")
        if err:
            print(f"  ERROR: {str(err)[:150]}")
        else:
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"  [{k}]: {len(v)} items" +
                          (f"  first_keys={list(v[0].keys())[:6]}" if v and isinstance(v[0], dict) else ""))
                    if v and isinstance(v[0], dict):
                        print(f"    sample: {json.dumps(v[0], ensure_ascii=False)[:300]}")
    results[name] = {"status": status, "data": data}
    return status, data


# Known: WC=77, Friendlies=114, CL=42

# 1. Test matches-by-date with currently active leagues to verify endpoint works
probe("mbd_CL42",     "/football-get-matches-by-date", {"leagueId": "42", "date": TODAY})
time.sleep(0.3)
probe("mbd_CL42_nodt","/football-get-matches-by-date", {"leagueId": "42"})
time.sleep(0.3)
probe("mbd_noparams", "/football-get-matches-by-date", {})
time.sleep(0.3)
probe("mbd_yesterday_fr", "/football-get-matches-by-date", {"leagueId": "114", "date": YESTERDAY})
time.sleep(0.3)
# Try alternate endpoint name patterns
probe("all_matches",  "/football-get-all-matches-by-date", {"date": TODAY})
time.sleep(0.3)
probe("scores_date",  "/football-get-scores-by-league-date", {"leagueId": "114", "date": YESTERDAY})
time.sleep(0.3)

# 2. Match details — try with real match IDs (we don't know them yet)
probe("match_1000",   "/football-get-match-details", {"matchId": "1000000"})
time.sleep(0.3)
probe("match_str",    "/football-get-match-details", {"id": "1000000"})
time.sleep(0.3)

# 3. Search — try team/player search
probe("search_team1", "/football-search-team",    {"query": "Brazil"})
time.sleep(0.3)
probe("search_team2", "/football-get-team",        {"name": "Brazil"})
time.sleep(0.3)
probe("search_team3", "/football-get-teams",       {"leagueId": "77"})
time.sleep(0.3)
probe("team_stats",   "/football-get-team-statistics", {"teamId": "1", "leagueId": "77"})
time.sleep(0.3)

# 4. Standings
probe("standings77",  "/football-get-league-standings", {"leagueId": "77"})
time.sleep(0.3)
probe("standings114", "/football-get-league-standings", {"leagueId": "114"})
time.sleep(0.3)

# Upload to GitHub via REST API
content = json.dumps(results, indent=2, ensure_ascii=False)
print(f"\nTotal result size: {len(content)} chars")
push_to_github(
    "scripts/api_probe_results.json",
    content,
    f"chore: API probe results {TODAY}"
)
print("Done.")
