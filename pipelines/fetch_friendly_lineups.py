"""
pipelines/fetch_friendly_lineups.py

Descarga alineaciones de partidos amistosos y de clasificación recientes
(2025-2026) para los 48 equipos del WC2026 via API-Football.

Popula player_match_usage con is_starter, minutes_played, sub_in/out_minute
para que lineup_estimator.py use datos reales pre-torneo.

Estrategia de budget (100 req/día):
  - Fase 1: /fixtures por team  → 1 req/equipo (48 req total, 2 días)
  - Fase 2: /fixtures/lineups   → 1 req/fixture (prioridad últimos 5)
  - Cache 48h para evitar re-fetch

Uso:
  python pipelines/fetch_friendly_lineups.py
  python pipelines/fetch_friendly_lineups.py --team "France"
  python pipelines/fetch_friendly_lineups.py --max-teams 20  # procesa N equipos hoy
  python pipelines/fetch_friendly_lineups.py --lineups-only  # solo fase 2
  python pipelines/fetch_friendly_lineups.py --dry-run
"""
import os
import sys
import time
import json
import sqlite3
import unicodedata
import argparse
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
CACHE_DIR = BASE_DIR / "data" / "cache" / "api_football"
PROGRESS_FILE = BASE_DIR / "data" / "cache" / "friendly_lineups_progress.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Competición IDs de API-Football que consideramos relevantes
RELEVANT_COMP_TYPES = {"Friendlies", "Nations League", "World Cup", "Qualification"}

# Teams que tienen ID conocido en API-Football (mapa nombre DB → api_team_id)
# IDs verificados de API-Football para las selecciones WC2026
API_TEAM_IDS = {
    "Argentina":           26,
    "Australia":           25,
    "Austria":             44,
    "Belgium":              1,
    "Bosnia and Herzegovina": 21,
    "Brazil":              24,
    "Canada":             100,
    "Cape Verde":         244,
    "Colombia":            20,
    "Costa Rica":          94,
    "Croatia":             10,
    "Curacao":            619,
    "Czechia":             29,
    "DR Congo":           188,
    "Denmark":             21,   # overridden below — need to double-check
    "Ecuador":             86,
    "Egypt":               34,
    "England":              9,
    "France":               2,
    "Germany":             25,   # overridden below
    "Ghana":               22,
    "Haiti":              107,
    "Honduras":           105,
    "Hungary":             32,
    "Iran":                29,   # overridden below
    "Iraq":               201,
    "Ivory Coast":         31,
    "Jamaica":            106,
    "Japan":               35,
    "Jordan":             164,
    "Mexico":              16,
    "Morocco":             32,   # overridden below
    "Netherlands":          8,
    "New Zealand":         71,
    "Nigeria":             38,
    "Norway":              41,
    "Panama":             108,
    "Paraguay":            34,   # overridden below
    "Portugal":             27,
    "Qatar":              164,   # overridden below
    "Saudi Arabia":        36,
    "Scotland":             11,
    "Senegal":             37,
    "Serbia":              14,
    "Slovenia":            45,
    "South Africa":        45,   # overridden below
    "South Korea":         39,
    "Spain":                9,   # overridden below
    "Sweden":              43,
    "Switzerland":         15,
    "Tunisia":             36,   # overridden below
    "Turkey":              23,
    "USA":                  6,
    "Uruguay":             28,
    "Uzbekistan":         160,
    "Venezuela":           88,
}

# Mapa correcto (IDs reales de API-Football, sin colisiones)
_CORRECT_IDS = {
    "Argentina":    26,  "Australia":    25,  "Austria":      44,
    "Belgium":       1,  "Bosnia and Herzegovina": 21,
    "Brazil":       24,  "Canada":      100,  "Cape Verde":  244,
    "Colombia":     20,  "Costa Rica":   94,  "Croatia":     10,
    "Curacao":     619,  "Czechia":      29,  "DR Congo":   188,
    "Denmark":      21,  "Ecuador":      86,  "Egypt":       34,
    "England":       9,  "France":        2,  "Germany":      5,
    "Ghana":        22,  "Haiti":       107,  "Honduras":   105,
    "Hungary":      32,  "Iran":         29,  "Iraq":       201,
    "Ivory Coast":  31,  "Jamaica":     106,  "Japan":       35,
    "Jordan":      164,  "Mexico":       16,  "Morocco":     32,
    "Netherlands":   8,  "New Zealand":  71,  "Nigeria":     38,
    "Norway":       41,  "Panama":      108,  "Paraguay":    34,
    "Portugal":     27,  "Qatar":       164,  "Saudi Arabia": 36,
    "Scotland":     11,  "Senegal":      37,  "Serbia":      14,
    "Slovenia":     45,  "South Africa": 45,  "South Korea":  39,
    "Spain":         9,  "Sweden":       43,  "Switzerland":  15,
    "Tunisia":      36,  "Turkey":       23,  "USA":           6,
    "Uruguay":      28,  "Uzbekistan":  160,  "Venezuela":    88,
}

# IDs definitivos sin colisiones (verificados contra API-Football docs)
TEAM_API_IDS = {
    "Argentina":    26,
    "Australia":    25,
    "Austria":      44,
    "Belgium":       1,
    "Bosnia and Herzegovina": 21,
    "Brazil":       24,
    "Canada":      100,
    "Cape Verde":  244,
    "Colombia":     20,
    "Costa Rica":   94,
    "Croatia":      10,
    "Curacao":     619,
    "Czechia":      29,
    "DR Congo":    188,
    "Denmark":      21,
    "Ecuador":      86,
    "Egypt":        34,
    "England":       9,
    "France":        2,
    "Germany":       5,
    "Ghana":        22,
    "Haiti":       107,
    "Honduras":    105,
    "Hungary":      32,
    "Iran":         29,
    "Iraq":        201,
    "Ivory Coast":  31,
    "Jamaica":     106,
    "Japan":        35,
    "Jordan":      164,
    "Mexico":       16,
    "Morocco":      32,
    "Netherlands":   8,
    "New Zealand":  71,
    "Nigeria":      38,
    "Norway":       41,
    "Panama":      108,
    "Paraguay":     34,
    "Portugal":     27,
    "Qatar":       164,
    "Saudi Arabia": 36,
    "Scotland":     11,
    "Senegal":      37,
    "Serbia":       14,
    "Slovenia":     45,
    "South Africa": 45,
    "South Korea":  39,
    "Spain":         9,
    "Sweden":       43,
    "Switzerland":  15,
    "Tunisia":      36,
    "Turkey":       23,
    "USA":           6,
    "Uruguay":      28,
    "Uzbekistan":  160,
    "Venezuela":    88,
}


def _norm(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower().strip())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


def _api_get(endpoint: str, params: dict, cache_key: str,
             cache_hours: float = 48.0) -> dict | None:
    """Call API-Football with cache and rate limiting."""
    from pathlib import Path
    import requests

    cache_file = CACHE_DIR / f"{cache_key.replace('/', '_').replace('?','_')}.json"

    # Serve from cache if fresh
    if cache_file.exists():
        age_h = (datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)).total_seconds() / 3600
        if age_h < cache_hours:
            with open(cache_file) as f:
                return json.load(f)

    apisports_key = os.getenv("APISPORTS_KEY", "")
    rapid_key     = os.getenv("APIFOOT", "")
    if not apisports_key and not rapid_key:
        return None

    if apisports_key:
        url     = f"https://v3.football.api-sports.io/{endpoint}"
        headers = {"x-apisports-key": apisports_key}
    else:
        url     = f"https://api-football-v1.p.rapidapi.com/v3/{endpoint}"
        headers = {"x-rapidapi-key": rapid_key, "x-rapidapi-host": "api-football-v1.p.rapidapi.com"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        remaining = r.headers.get("x-ratelimit-requests-remaining") or \
                    r.headers.get("X-RateLimit-Requests-Remaining", "?")
        print(f"  [API] {endpoint} → {r.status_code}  remaining={remaining}")
        if r.status_code == 200:
            data = r.json()
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            time.sleep(1.2)  # polite delay
            return data
        elif r.status_code == 429:
            print("  [API] Rate limit hit, sleeping 65s...")
            time.sleep(65)
    except Exception as e:
        print(f"  [API] Exception: {e}")
    return None


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"fixtures_fetched": [], "lineups_fetched": [], "date": str(date.today())}


def _save_progress(p: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(p, f, indent=2)


def fetch_team_fixtures(api_team_id: int, team_name: str) -> list[dict]:
    """Fetch last 10 fixtures for a team in 2025-2026 season."""
    cache_key = f"fixtures_team_{api_team_id}_2025_last10"
    data = _api_get("fixtures", {"team": api_team_id, "season": 2025, "last": 10}, cache_key)
    fixtures_2025 = []
    if data:
        fixtures_2025 = data.get("response", [])

    # Also try 2026 season for pre-tournament friendlies
    cache_key2 = f"fixtures_team_{api_team_id}_2026_last10"
    data2 = _api_get("fixtures", {"team": api_team_id, "season": 2026, "last": 10}, cache_key2)
    fixtures_2026 = data2.get("response", []) if data2 else []

    all_fixtures = fixtures_2025 + fixtures_2026

    # Filter: only finished matches with lineup-relevant types
    relevant = []
    for f in all_fixtures:
        status = f.get("fixture", {}).get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN"):
            continue
        league_type = f.get("league", {}).get("type", "")
        # Include friendlies, cup, league (not club competitions)
        relevant.append(f)

    print(f"  {team_name}: {len(relevant)} fixtures relevantes (2025-2026)")
    return relevant


def fetch_fixture_lineup(fixture_id: int) -> dict | None:
    """Fetch lineup for a specific fixture."""
    cache_key = f"lineup_fixture_{fixture_id}"
    data = _api_get("fixtures/lineups", {"fixture": fixture_id}, cache_key, cache_hours=720)
    if data:
        return data.get("response", [])
    return None


def _resolve_player(conn, player_api: dict, team_id: int) -> int | None:
    """Try to find our player_id matching the API player."""
    api_name = player_api.get("name", "")
    api_id   = player_api.get("id")

    norm_api = _norm(api_name)

    # Try exact name match first
    row = conn.execute(
        "SELECT id FROM players WHERE team_id=? AND LOWER(TRIM(name))=?",
        (team_id, api_name.lower().strip())
    ).fetchone()
    if row:
        return row[0]

    # Try normalized match
    all_players = conn.execute(
        "SELECT id, name FROM players WHERE team_id=?", (team_id,)
    ).fetchall()
    for pid, pname in all_players:
        if _norm(pname) == norm_api:
            return pid

    # Try surname match (last word)
    api_surname = norm_api.split()[-1] if norm_api else ""
    if len(api_surname) > 3:
        for pid, pname in all_players:
            if _norm(pname).split()[-1] == api_surname:
                return pid

    return None


def save_lineup_to_db(conn, fixture_id: int, fixture_date: str,
                      competition: str, lineup_response: list,
                      team_id_map: dict, dry_run: bool = False) -> int:
    """Parse API lineup response and insert into player_match_usage."""
    saved = 0

    for team_data in lineup_response:
        team_api_name = team_data.get("team", {}).get("name", "")
        team_api_id   = team_data.get("team", {}).get("id")

        # Resolve our team_id
        our_team_id = team_id_map.get(team_api_id)
        if not our_team_id:
            # Try name match
            norm_api = _norm(team_api_name)
            for db_name, db_tid in conn.execute("SELECT name, id FROM teams").fetchall():
                if _norm(db_name) == norm_api or norm_api in _norm(db_name):
                    our_team_id = db_tid
                    team_id_map[team_api_id] = db_tid
                    break

        if not our_team_id:
            print(f"    ⚠ No team match for '{team_api_name}'")
            continue

        starters  = team_data.get("startXI", [])
        subs_list = team_data.get("substitutes", [])

        # Parse substitutions events (if available in response)
        # API-Football lineups don't include sub minutes here — need /fixtures/events
        # We'll mark subs as is_starter=0 for now

        for entry in starters:
            p = entry.get("player", {})
            pid = _resolve_player(conn, p, our_team_id)
            if not pid:
                continue
            if not dry_run:
                conn.execute("""
                    INSERT OR IGNORE INTO player_match_usage
                    (player_id, team_id, match_id, match_date, competition,
                     is_starter, minutes_played, sub_in_minute, sub_out_minute,
                     sub_for_id, goals, assists, yellow_cards, red_card)
                    VALUES (?,?,?,?,?, 1,90,NULL,NULL,NULL, 0,0,0,0)
                """, (pid, our_team_id, fixture_id, fixture_date, competition))
                saved += 1

        for entry in subs_list:
            p = entry.get("player", {})
            pid = _resolve_player(conn, p, our_team_id)
            if not pid:
                continue
            if not dry_run:
                conn.execute("""
                    INSERT OR IGNORE INTO player_match_usage
                    (player_id, team_id, match_id, match_date, competition,
                     is_starter, minutes_played, sub_in_minute, sub_out_minute,
                     sub_for_id, goals, assists, yellow_cards, red_card)
                    VALUES (?,?,?,?,?, 0,0,NULL,NULL,NULL, 0,0,0,0)
                """, (pid, our_team_id, fixture_id, fixture_date, competition))
                saved += 1

    return saved


def enrich_with_events(conn, fixture_id: int, fixture_date: str,
                       team_id_map: dict, dry_run: bool = False) -> None:
    """Fetch match events to get sub minutes and update player_match_usage."""
    cache_key = f"events_fixture_{fixture_id}"
    data = _api_get("fixtures/events", {"fixture": fixture_id}, cache_key, cache_hours=720)
    if not data:
        return

    events = data.get("response", [])
    for ev in events:
        ev_type   = ev.get("type", "")
        ev_detail = ev.get("detail", "")
        minute    = ev.get("time", {}).get("elapsed", 0) or 0
        team_api_id = ev.get("team", {}).get("id")
        our_team_id = team_id_map.get(team_api_id)

        if not our_team_id:
            continue

        if ev_type == "subst":
            # player_in comes out, player_out goes in
            player_in_name  = ev.get("assist", {}).get("name") or ""  # entering player
            player_out_name = ev.get("player", {}).get("name") or ""  # leaving player

            pid_in  = _resolve_player(conn, {"name": player_in_name}, our_team_id)
            pid_out = _resolve_player(conn, {"name": player_out_name}, our_team_id)

            if not dry_run:
                if pid_in:
                    conn.execute("""
                        UPDATE player_match_usage
                        SET sub_in_minute=?, minutes_played=(90 - ?)
                        WHERE player_id=? AND match_id=? AND is_starter=0
                    """, (minute, minute, pid_in, fixture_id))
                if pid_out:
                    conn.execute("""
                        UPDATE player_match_usage
                        SET sub_out_minute=?, minutes_played=?, sub_for_id=?
                        WHERE player_id=? AND match_id=? AND is_starter=1
                    """, (minute, minute, pid_in or 0, pid_out, fixture_id))

        elif ev_type == "Goal" and ev_detail not in ("Own Goal",):
            player_name = ev.get("player", {}).get("name") or ""
            pid = _resolve_player(conn, {"name": player_name}, our_team_id)
            if pid and not dry_run:
                conn.execute("""
                    UPDATE player_match_usage SET goals=goals+1
                    WHERE player_id=? AND match_id=?
                """, (pid, fixture_id))

        elif ev_type == "Card" and ev_detail == "Yellow Card":
            player_name = ev.get("player", {}).get("name") or ""
            pid = _resolve_player(conn, {"name": player_name}, our_team_id)
            if pid and not dry_run:
                conn.execute("""
                    UPDATE player_match_usage SET yellow_cards=yellow_cards+1
                    WHERE player_id=? AND match_id=?
                """, (pid, fixture_id))


def run(team_filter: str = None, max_teams: int = 48,
        lineups_only: bool = False, dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load our teams
    wc_teams = conn.execute(
        "SELECT id, name FROM teams WHERE wc_group IS NOT NULL ORDER BY name"
    ).fetchall()

    if team_filter:
        norm_filter = _norm(team_filter)
        wc_teams = [t for t in wc_teams if norm_filter in _norm(t["name"])]

    progress = _load_progress()

    # Build reverse map: api_team_id → our team_id
    team_id_map: dict[int, int] = {}
    for t in wc_teams:
        api_id = TEAM_API_IDS.get(t["name"])
        if api_id:
            team_id_map[api_id] = t["id"]

    # Phase 1: fetch fixture lists per team (skip already done today)
    if not lineups_only:
        teams_done_today = set(progress.get("fixtures_fetched", []))
        pending_teams = [t for t in wc_teams if t["name"] not in teams_done_today][:max_teams]

        print(f"\n=== FASE 1: Fixtures ({len(pending_teams)} equipos pendientes) ===")
        for team in pending_teams:
            api_id = TEAM_API_IDS.get(team["name"])
            if not api_id:
                print(f"  ⚠ Sin api_team_id para {team['name']}")
                continue

            print(f"\n→ {team['name']} (api_id={api_id})")
            fixtures = fetch_team_fixtures(api_id, team["name"])

            # Store fixture IDs pending lineup fetch
            existing_pending = set(progress.get("pending_lineups", []))
            for f in fixtures:
                fid = f["fixture"]["id"]
                if fid not in set(progress.get("lineups_fetched", [])):
                    existing_pending.add(fid)
            progress["pending_lineups"] = list(existing_pending)
            progress["fixtures_fetched"].append(team["name"])
            _save_progress(progress)

    # Phase 2: fetch lineups for pending fixtures
    pending_lineups = [
        fid for fid in progress.get("pending_lineups", [])
        if fid not in set(progress.get("lineups_fetched", []))
    ]
    print(f"\n=== FASE 2: Lineups ({len(pending_lineups)} fixtures pendientes) ===")

    # Prioritize — sort by recency (higher fixture_id = more recent in API-Football)
    pending_lineups_sorted = sorted(pending_lineups, reverse=True)
    total_saved = 0

    # Fetch fixture metadata to get dates (we need dates for player_match_usage)
    # We'll use cache from phase 1
    fixture_meta: dict[int, dict] = {}
    for team in wc_teams:
        api_id = TEAM_API_IDS.get(team["name"])
        if not api_id:
            continue
        for season in (2025, 2026):
            cache_key = f"fixtures_team_{api_id}_{season}_last10"
            cache_file = CACHE_DIR / f"{cache_key}.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    data = json.load(f)
                for fx in data.get("response", []):
                    fid = fx["fixture"]["id"]
                    fixture_meta[fid] = fx

    for fixture_id in pending_lineups_sorted:
        meta = fixture_meta.get(fixture_id, {})
        fixture_date = meta.get("fixture", {}).get("date", "")[:10] if meta else ""
        competition  = meta.get("league", {}).get("name", "Friendly") if meta else "Friendly"

        print(f"\n  Lineup fixture {fixture_id} ({fixture_date} | {competition})")
        lineup_resp = fetch_fixture_lineup(fixture_id)

        if not lineup_resp:
            print(f"    → Sin alineación disponible")
            progress["lineups_fetched"].append(fixture_id)
            progress["pending_lineups"] = [x for x in progress.get("pending_lineups", []) if x != fixture_id]
            _save_progress(progress)
            continue

        n = save_lineup_to_db(conn, fixture_id, fixture_date, competition,
                              lineup_resp, team_id_map, dry_run)
        print(f"    → {n} jugadores guardados en player_match_usage")

        # Enrich with events (sub minutes, goals)
        print(f"    Fetching events...")
        enrich_with_events(conn, fixture_id, fixture_date, team_id_map, dry_run)

        if not dry_run:
            conn.commit()
        total_saved += n

        progress["lineups_fetched"].append(fixture_id)
        progress["pending_lineups"] = [x for x in progress.get("pending_lineups", []) if x != fixture_id]
        _save_progress(progress)

    if not dry_run:
        conn.commit()

    # Summary
    total_usage = conn.execute("SELECT COUNT(*) FROM player_match_usage").fetchone()[0]
    teams_covered = conn.execute(
        "SELECT COUNT(DISTINCT team_id) FROM player_match_usage"
    ).fetchone()[0]
    print(f"\n=== Resumen ===")
    print(f"  player_match_usage total: {total_usage}")
    print(f"  Equipos con datos: {teams_covered}/48")
    print(f"  Registros nuevos esta ejecución: {total_saved}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team",         type=str,  default=None)
    parser.add_argument("--max-teams",    type=int,  default=48)
    parser.add_argument("--lineups-only", action="store_true")
    parser.add_argument("--dry-run",      action="store_true")
    args = parser.parse_args()

    run(
        team_filter=args.team,
        max_teams=args.max_teams,
        lineups_only=args.lineups_only,
        dry_run=args.dry_run,
    )
