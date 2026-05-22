"""
test_api.py — Test connectivity to all APIs used by the WC2026 prediction system.

Usage:
    python scripts/test_api.py

Output example:
    Testing API connections...
      api-sports.io (APISPORTS_KEY):  OK - 45 requests remaining today
      RapidAPI Football (APIFOOT):    ERROR - Host not in allowlist (IP blocked)
      football-data.org:              OK - Tier: FREE_TIER
      Football Prediction API:        OK - 87 requests remaining

    Active key: APISPORTS_KEY (api-sports.io direct)
"""
import os
import sys
from pathlib import Path

# Add project root to path so dotenv and project modules can be found
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import requests
except ImportError:
    print("ERROR: 'requests' module not installed. Run: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # dotenv optional; rely on environment variables

APISPORTS_KEY = os.getenv("APISPORTS_KEY", "")
AF_KEY        = os.getenv("APIFOOT", "")
FD_KEY        = os.getenv("FOOTBALL_DATA_KEY", "")
PRED_KEY      = os.getenv("FOOTBALL_PREDICTION_KEY", "")

AF_BASE_DIRECT = "https://v3.football.api-sports.io"
AF_BASE_RAPID  = "https://api-football-v1.p.rapidapi.com/v3"
FD_BASE        = "https://api.football-data.org/v4"
PRED_BASE      = "https://football-prediction-api.p.rapidapi.com"


def _ok(msg: str) -> str:
    return f"OK - {msg}"


def _err(msg: str) -> str:
    return f"ERROR - {msg}"


def test_apisports(key: str) -> str:
    """Test api-sports.io direct endpoint."""
    if not key:
        return "SKIP - APISPORTS_KEY not set"

    url = f"{AF_BASE_DIRECT}/status"
    headers = {"x-apisports-key": key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # api-sports returns account info; check requests_remaining
            account = data.get("response", {}).get("requests", {})
            remaining = account.get("remaining", "?")
            limit = account.get("limit_day", "?")
            return _ok(f"{remaining}/{limit} requests remaining today")
        elif r.status_code == 403:
            return _err("Invalid API key or IP blocked")
        elif r.status_code == 429:
            return _err("Daily limit reached")
        else:
            # Try to parse error message
            try:
                body = r.json()
                msg = body.get("message") or body.get("errors") or r.text[:120]
            except Exception:
                msg = r.text[:120]
            return _err(f"HTTP {r.status_code}: {msg}")
    except requests.exceptions.ConnectionError as e:
        return _err(f"Connection refused (IP blocked or no network): {e}")
    except requests.exceptions.Timeout:
        return _err("Request timed out")
    except Exception as e:
        return _err(str(e))


def test_rapidapi_football(key: str) -> str:
    """Test RapidAPI Football endpoint."""
    if not key:
        return "SKIP - APIFOOT not set"

    url = f"{AF_BASE_RAPID}/status"
    headers = {
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
        "x-rapidapi-key": key,
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            remaining = r.headers.get("X-RateLimit-Requests-Remaining", "?")
            return _ok(f"{remaining} requests remaining today")
        elif r.status_code == 403:
            return _err("Host not in allowlist (IP blocked)")
        elif r.status_code == 401:
            return _err("Invalid API key")
        elif r.status_code == 429:
            return _err("Daily limit reached")
        else:
            try:
                body = r.json()
                msg = body.get("message") or r.text[:120]
            except Exception:
                msg = r.text[:120]
            return _err(f"HTTP {r.status_code}: {msg}")
    except requests.exceptions.ConnectionError as e:
        return _err(f"Connection refused (IP blocked or no network): {e}")
    except requests.exceptions.Timeout:
        return _err("Request timed out")
    except Exception as e:
        return _err(str(e))


def test_football_data_org(key: str) -> str:
    """Test football-data.org API."""
    if not key:
        return "SKIP - FOOTBALL_DATA_KEY not set"

    url = f"{FD_BASE}/competitions"
    headers = {"X-Auth-Token": key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            # Check response headers for tier info
            tier = r.headers.get("X-Auth-Token-Plan", "")
            if not tier:
                tier = "UNKNOWN_TIER"
            return _ok(f"Tier: {tier}")
        elif r.status_code == 403:
            return _err("Invalid API key or IP blocked")
        elif r.status_code == 429:
            return _err("Rate limit exceeded")
        else:
            try:
                body = r.json()
                msg = body.get("message") or r.text[:120]
            except Exception:
                msg = r.text[:120]
            return _err(f"HTTP {r.status_code}: {msg}")
    except requests.exceptions.ConnectionError as e:
        return _err(f"Connection refused (IP blocked or no network): {e}")
    except requests.exceptions.Timeout:
        return _err("Request timed out")
    except Exception as e:
        return _err(str(e))


def test_football_prediction_api(key: str) -> str:
    """Test Football Prediction API (RapidAPI)."""
    if not key:
        return "SKIP - FOOTBALL_PREDICTION_KEY not set"

    url = f"{PRED_BASE}/v2/predictions"
    headers = {
        "x-rapidapi-host": "football-prediction-api.p.rapidapi.com",
        "x-rapidapi-key": key,
    }
    # Minimal query to test auth
    params = {"market": "classic", "iso_date": "2026-06-12", "federation": "FIFA"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code in (200, 204):
            remaining = r.headers.get("X-RateLimit-Requests-Remaining", "?")
            return _ok(f"{remaining} requests remaining")
        elif r.status_code == 403:
            return _err("Host not in allowlist (IP blocked)")
        elif r.status_code == 401:
            return _err("Invalid API key")
        elif r.status_code == 429:
            return _err("Rate limit exceeded")
        else:
            try:
                body = r.json()
                msg = body.get("message") or r.text[:120]
            except Exception:
                msg = r.text[:120]
            return _err(f"HTTP {r.status_code}: {msg}")
    except requests.exceptions.ConnectionError as e:
        return _err(f"Connection refused (IP blocked or no network): {e}")
    except requests.exceptions.Timeout:
        return _err("Request timed out")
    except Exception as e:
        return _err(str(e))


def determine_active_key() -> str:
    """Return a human-readable description of which API key is active."""
    if APISPORTS_KEY:
        return "APISPORTS_KEY (api-sports.io direct)"
    elif AF_KEY:
        return "APIFOOT (RapidAPI Football)"
    else:
        return "NONE — no API-Football key configured"


def main():
    print("\nTesting API connections...")
    col_width = 38

    # Test each API
    label_apisports  = "api-sports.io (APISPORTS_KEY):"
    label_rapidapi   = "RapidAPI Football (APIFOOT):"
    label_fd         = "football-data.org:"
    label_pred       = "Football Prediction API:"

    result_apisports = test_apisports(APISPORTS_KEY)
    result_rapidapi  = test_rapidapi_football(AF_KEY)
    result_fd        = test_football_data_org(FD_KEY)
    result_pred      = test_football_prediction_api(PRED_KEY)

    print(f"  {label_apisports:<{col_width}} {result_apisports}")
    print(f"  {label_rapidapi:<{col_width}} {result_rapidapi}")
    print(f"  {label_fd:<{col_width}} {result_fd}")
    print(f"  {label_pred:<{col_width}} {result_pred}")

    print(f"\nActive key: {determine_active_key()}")

    # Summary
    any_ok = any(
        r.startswith("OK")
        for r in [result_apisports, result_rapidapi, result_fd, result_pred]
    )
    if not any_ok:
        print("\nWARNING: No APIs are reachable from this environment.")
        print("  This is expected when running from a container with IP restrictions.")
        print("  Pipelines are correctly configured to use APISPORTS_KEY via GitHub Actions.")
    print()


if __name__ == "__main__":
    main()
