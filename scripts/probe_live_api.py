"""
probe_live_api.py — Descubre qué datos devuelve Free API Live Football Data.
Se corre desde GitHub Actions y guarda los resultados como JSON en data/.
"""
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
KEY  = os.environ.get("APIFOOT", "")
HOST = "free-api-live-football-data.p.rapidapi.com"
HDRS = {"x-rapidapi-host": HOST, "x-rapidapi-key": KEY}

TODAY     = datetime.utcnow().strftime("%Y-%m-%d")
YESTERDAY = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")


def get(path, params=None):
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        return e.code, {"error": f"HTTP {e.code}", "body": body}
    except Exception as e:
        return 0, {"error": str(e)}


def summarize(data):
    if isinstance(data, dict):
        keys = list(data.keys())
        print(f"  keys: {keys[:10]}")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"  [{k}]: {len(v)} items")
                if v and isinstance(v[0], dict):
                    print(f"    first item keys: {list(v[0].keys())[:12]}")
                    print(f"    sample: {json.dumps(v[0], ensure_ascii=False)[:250]}")
            elif isinstance(v, (str, int, bool, float)):
                print(f"  [{k}]: {str(v)[:100]}")
    elif isinstance(data, list):
        print(f"  list of {len(data)} items")
        if data and isinstance(data[0], dict):
            print(f"  first item keys: {list(data[0].keys())[:12]}")
            print(f"  sample: {json.dumps(data[0], ensure_ascii=False)[:250]}")


def probe(name, path, params=None):
    print(f"\n{'='*60}")
    print(f"  {name}")
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    print(f"  {url}")
    status, data = get(path, params)
    print(f"  HTTP {status}")
    summarize(data)
    out = BASE_DIR / "scripts" / f"probe_{name}.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return status, data


print(f"Key set: {'YES' if KEY else 'NO'} (len={len(KEY)})")
print(f"Today={TODAY}  Yesterday={YESTERDAY}")

probe("leagues",       "/football-get-all-leagues")
time.sleep(0.4)
probe("livescores",    "/football-get-all-livescores")
time.sleep(0.4)
probe("today",         "/football-get-fixtures-scores-by-date",  {"date": TODAY})
time.sleep(0.4)
probe("yesterday",     "/football-get-fixtures-scores-by-date",  {"date": YESTERDAY})
time.sleep(0.4)
probe("team_brazil",   "/football-search-teams",   {"searchQuery": "Brazil"})
time.sleep(0.4)
probe("team_france",   "/football-search-teams",   {"searchQuery": "France"})
time.sleep(0.4)
probe("player_mbappe", "/football-search-players", {"searchQuery": "Mbappe"})
time.sleep(0.4)
probe("player_messi",  "/football-search-players", {"searchQuery": "Messi"})

print("\n\nDone. Probe files in scripts/probe_*.json")
