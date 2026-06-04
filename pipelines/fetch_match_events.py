"""
fetch_match_events.py — Fetch post-match events and statistics for WC2026 matches.

Calls API-Football for each played (or recently finished) WC match:
  /fixtures/events?fixture={id}      → goals, cards, substitutions → match_events + player_match_usage
  /fixtures/statistics?fixture={id}  → xG, possession, shots, corners, fouls → match_stats
  /fixtures/lineups?fixture={id}     → confirmed XI → match_lineups + player_match_usage
  /fixtures?id={id}                  → final score → wc_matches (score_home/away, played=1)

Designed to run every 30 min during match day (match_day.yml).
Only processes matches within a ±6h window of now (or all unprocessed if --all flag).

Usage:
  python pipelines/fetch_match_events.py
  python pipelines/fetch_match_events.py --all          # all unprocessed fixtures
  python pipelines/fetch_match_events.py --fixture 123  # single fixture
  python pipelines/fetch_match_events.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

DB_PATH   = BASE_DIR / "data" / "mundial2026.db"
CACHE_DIR = BASE_DIR / "data" / "cache" / "match_events"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

import re


def _clean_key(raw: str, kind: str) -> str:
    """Sanitiza secrets mal configurados (blob multilínea) y extrae el token real."""
    if not raw:
        return ""
    raw = raw.strip()
    if "\n" not in raw and " " not in raw and "=" not in raw:
        return raw
    if kind == "rapid":
        m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", raw)
        if m:
            return m.group(0)
    else:
        for tok in re.findall(r"[0-9a-fA-F]{32}", raw):
            return tok
    for tok in re.findall(r"[0-9a-zA-Z]{20,}", raw):
        return tok
    return raw


RAPID_KEY  = _clean_key(os.getenv("APIFOOT", ""), "rapid")
SPORTS_KEY = _clean_key(os.getenv("APISPORTS_KEY", ""), "apisports")

RAPID_HOST = "api-football-v1.p.rapidapi.com"
SPORTS_URL = "https://v3.football.api-sports.io"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _is_plan_error(data: dict) -> bool:
    errs = data.get("errors") if isinstance(data, dict) else None
    if isinstance(errs, dict):
        return any("plan" in str(k).lower() or "plan" in str(v).lower()
                   for k, v in errs.items())
    return False


def _provider_get(provider: str, endpoint: str, params: dict) -> dict | None:
    import urllib.request
    import urllib.parse

    qs = urllib.parse.urlencode(params)
    if provider == "rapid":
        if not RAPID_KEY:
            return None
        url     = f"https://{RAPID_HOST}/v3/{endpoint}?{qs}"
        headers = {"x-rapidapi-key": RAPID_KEY, "x-rapidapi-host": RAPID_HOST}
    else:
        if not SPORTS_KEY:
            return None
        url     = f"{SPORTS_URL}/{endpoint}?{qs}"
        headers = {"x-apisports-key": SPORTS_KEY}

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  [events:{provider}] HTTP error {endpoint}: {e}")
        return None


def _get(endpoint: str, params: dict) -> dict | None:
    """Call API-Football. RapidAPI primero (tiene temporada actual en free tier),
    fallback a api-sports.io. Si un proveedor falla por plan, prueba el otro."""
    if not SPORTS_KEY and not RAPID_KEY:
        print("  [events] No API key configured — skipping")
        return None

    data = None
    for provider in ("rapid", "apisports"):
        d = _provider_get(provider, endpoint, params)
        if d is None:
            continue
        if _is_plan_error(d):
            print(f"  [events:{provider}] plan error → siguiente proveedor")
            data = d
            continue
        return d
    return data


def _cached_get(cache_key: str, endpoint: str, params: dict, ttl_minutes: int = 35) -> dict | None:
    """Fetch with file cache (ttl_minutes=35 so same match isn't fetched twice per run)."""
    path = CACHE_DIR / f"{cache_key}.json"
    if path.exists():
        age = (datetime.utcnow().timestamp() - path.stat().st_mtime) / 60
        if age < ttl_minutes:
            return json.loads(path.read_text())
    data = _get(endpoint, params)
    if data:
        path.write_text(json.dumps(data))
    return data


# ---------------------------------------------------------------------------
# Player resolution
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _resolve_player(cur: sqlite3.Cursor, team_id: int, api_name: str) -> int | None:
    """Map API player name to our DB player_id."""
    # Exact match
    row = cur.execute(
        "SELECT id FROM players WHERE team_id=? AND name=?", (team_id, api_name)
    ).fetchone()
    if row:
        return row[0]

    # Normalized match
    norm_api = _norm(api_name)
    rows = cur.execute("SELECT id, name FROM players WHERE team_id=?", (team_id,)).fetchall()
    for r in rows:
        if _norm(r["name"]) == norm_api:
            return r["id"]

    # Surname match
    surname = _norm(api_name).split()[-1]
    for r in rows:
        parts = _norm(r["name"]).split()
        if parts and parts[-1] == surname:
            return r["id"]
    return None


# ---------------------------------------------------------------------------
# Process a single fixture
# ---------------------------------------------------------------------------

def process_fixture(fixture_id: int, wc_match_id: int | None, dry_run: bool = False) -> dict:
    """Fetch and store all available data for one fixture. Returns summary dict."""
    summary = {"fixture_id": fixture_id, "events": 0, "stats": 0, "lineups": 0, "score": None}

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    cur = conn.cursor()

    # 1. Fixture result (score + status)
    data = _cached_get(f"fixture_{fixture_id}", "fixtures", {"id": fixture_id}, ttl_minutes=30)
    if data and data.get("response"):
        fix = data["response"][0]
        score_h = fix["goals"].get("home")
        score_a = fix["goals"].get("away")
        status  = fix["fixture"]["status"]["short"]  # FT, NS, 1H, 2H, HT, etc.
        played  = 1 if status in ("FT", "AET", "PEN", "AWD", "WO") else 0
        summary["score"] = f"{score_h}-{score_a}" if score_h is not None else "?"

        if not dry_run and wc_match_id and played:
            cur.execute("""
                UPDATE wc_matches
                SET score_home=?, score_away=?, played=1
                WHERE id=?
            """, (score_h, score_a, wc_match_id))

        # Try to resolve team_ids from fixture
        home_api_name = fix["teams"]["home"]["name"]
        away_api_name = fix["teams"]["away"]["name"]
        home_id_row = cur.execute("SELECT id FROM teams WHERE name=?", (home_api_name,)).fetchone()
        away_id_row = cur.execute("SELECT id FROM teams WHERE name=?", (away_api_name,)).fetchone()
        home_team_id = home_id_row["id"] if home_id_row else None
        away_team_id = away_id_row["id"] if away_id_row else None
    else:
        played = 0
        home_team_id = away_team_id = None

    # 2. Lineups
    lin_data = _cached_get(f"lineups_{fixture_id}", "fixtures/lineups", {"fixture": fixture_id})
    if lin_data and lin_data.get("response"):
        for team_lineup in lin_data["response"]:
            api_team_name = team_lineup["team"]["name"]
            t_row = cur.execute("SELECT id FROM teams WHERE name=?", (api_team_name,)).fetchone()
            team_id = t_row["id"] if t_row else None

            if not team_id:
                continue

            match_date = fix["fixture"]["date"][:10] if data and data.get("response") else None

            for pl in team_lineup.get("startXI", []):
                p = pl["player"]
                pid = _resolve_player(cur, team_id, p["name"])
                if not dry_run and pid and wc_match_id:
                    cur.execute("""
                        INSERT OR IGNORE INTO match_lineups
                            (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                        VALUES (?,?,?,?,1,0,datetime('now'))
                    """, (wc_match_id, team_id, pid, p.get("pos"), ))
                    # Also upsert player_match_usage
                    if match_date:
                        cur.execute("""
                            INSERT OR IGNORE INTO player_match_usage
                                (player_id, team_id, match_id, match_date, competition, is_starter)
                            VALUES (?,?,?,?,'WC2026',1)
                        """, (pid, team_id, wc_match_id, match_date))
                    summary["lineups"] += 1

            for pl in team_lineup.get("substitutes", []):
                p = pl["player"]
                pid = _resolve_player(cur, team_id, p["name"])
                if not dry_run and pid and wc_match_id:
                    cur.execute("""
                        INSERT OR IGNORE INTO match_lineups
                            (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                        VALUES (?,?,?,?,0,0,datetime('now'))
                    """, (wc_match_id, team_id, pid, p.get("pos")))

    # 3. Events (goals, cards, substitutions)
    ev_data = _cached_get(f"events_{fixture_id}", "fixtures/events", {"fixture": fixture_id})
    if ev_data and ev_data.get("response"):
        match_date_ev = fix["fixture"]["date"][:10] if data and data.get("response") else None
        for ev in ev_data["response"]:
            minute = ev["time"]["elapsed"]
            extra  = ev["time"].get("extra") or 0
            detail = ev.get("detail", "")
            etype  = ev["type"]
            api_team = ev["team"]["name"]
            t_row  = cur.execute("SELECT id FROM teams WHERE name=?", (api_team,)).fetchone()
            team_id_ev = t_row["id"] if t_row else None
            player_name = ev["player"].get("name") or ""
            player_id_ev = _resolve_player(cur, team_id_ev, player_name) if team_id_ev else None
            assist_name = (ev.get("assist") or {}).get("name") or None

            if dry_run:
                summary["events"] += 1
                continue

            # Insert into match_events
            if home_team_id or away_team_id:
                cur.execute("""
                    INSERT OR IGNORE INTO match_events
                        (match_date, home_team_id, away_team_id, team_id, player_name,
                         player_id, event_type, minute, minute_extra, assist_player, detail, competition)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,'WC2026')
                """, (match_date_ev, home_team_id, away_team_id, team_id_ev,
                      player_name, player_id_ev, etype, minute, extra, assist_name, detail))
            summary["events"] += 1

            # Update player_match_usage for goals, cards, substitutions
            if not player_id_ev or not match_date_ev or not team_id_ev:
                continue

            if etype == "Goal" and detail not in ("Own Goal",):
                cur.execute("""
                    INSERT INTO player_match_usage
                        (player_id, team_id, match_id, match_date, competition, is_starter, goals)
                    VALUES (?,?,?,?,'WC2026',1,1)
                    ON CONFLICT(player_id, match_date, team_id)
                    DO UPDATE SET goals = goals + 1
                """, (player_id_ev, team_id_ev, wc_match_id, match_date_ev))

            elif etype == "Card":
                if "Yellow" in detail:
                    cur.execute("""
                        INSERT INTO player_match_usage
                            (player_id, team_id, match_id, match_date, competition, is_starter, yellow_cards)
                        VALUES (?,?,?,?,'WC2026',1,1)
                        ON CONFLICT(player_id, match_date, team_id)
                        DO UPDATE SET yellow_cards = yellow_cards + 1
                    """, (player_id_ev, team_id_ev, wc_match_id, match_date_ev))
                elif "Red" in detail:
                    cur.execute("""
                        INSERT INTO player_match_usage
                            (player_id, team_id, match_id, match_date, competition, is_starter, red_card)
                        VALUES (?,?,?,?,'WC2026',1,1)
                        ON CONFLICT(player_id, match_date, team_id)
                        DO UPDATE SET red_card = 1
                    """, (player_id_ev, team_id_ev, wc_match_id, match_date_ev))

            elif etype == "subst":
                # player_name = player coming off; assist = player coming on
                sub_in_name = assist_name or ""
                sub_in_id   = _resolve_player(cur, team_id_ev, sub_in_name) if sub_in_name else None
                # Update player going off
                cur.execute("""
                    INSERT INTO player_match_usage
                        (player_id, team_id, match_id, match_date, competition, is_starter, sub_out_minute)
                    VALUES (?,?,?,?,'WC2026',1,?)
                    ON CONFLICT(player_id, match_date, team_id)
                    DO UPDATE SET sub_out_minute = ?
                """, (player_id_ev, team_id_ev, wc_match_id, match_date_ev, minute, minute))
                # Update player coming on
                if sub_in_id:
                    cur.execute("""
                        INSERT INTO player_match_usage
                            (player_id, team_id, match_id, match_date, competition, is_starter,
                             sub_in_minute, sub_for_id)
                        VALUES (?,?,?,?,'WC2026',0,?,?)
                        ON CONFLICT(player_id, match_date, team_id)
                        DO UPDATE SET sub_in_minute = ?, sub_for_id = ?
                    """, (sub_in_id, team_id_ev, wc_match_id, match_date_ev,
                          minute, player_id_ev, minute, player_id_ev))
                # Update match_lineups sub minutes
                if wc_match_id:
                    cur.execute("""
                        UPDATE match_lineups SET sub_out_minute=?
                        WHERE match_id=? AND player_id=? AND team_id=?
                    """, (minute, wc_match_id, player_id_ev, team_id_ev))
                    if sub_in_id:
                        cur.execute("""
                            UPDATE match_lineups SET sub_in_minute=?, sub_for_player_id=?
                            WHERE match_id=? AND player_id=? AND team_id=?
                        """, (minute, player_id_ev, wc_match_id, sub_in_id, team_id_ev))

    # 4. Statistics (possession, shots, corners, fouls, xG, etc.)
    stat_data = _cached_get(f"stats_{fixture_id}", "fixtures/statistics", {"fixture": fixture_id})
    if stat_data and stat_data.get("response"):
        match_date_st = fix["fixture"]["date"][:10] if data and data.get("response") else None

        for team_stats in stat_data["response"]:
            api_tname = team_stats["team"]["name"]
            t_row = cur.execute("SELECT id FROM teams WHERE name=?", (api_tname,)).fetchone()
            tid = t_row["id"] if t_row else None

            def _v(stats_list, stat_name):
                for s in stats_list:
                    if s["type"] == stat_name:
                        v = s["value"]
                        if v is None:
                            return None
                        if isinstance(v, str) and v.endswith("%"):
                            return float(v.rstrip("%"))
                        return v
                return None

            sl = team_stats["statistics"]
            xg          = _v(sl, "expected_goals") or _v(sl, "xG")
            possession  = _v(sl, "Ball Possession")
            shots_total = _v(sl, "Total Shots")
            shots_on    = _v(sl, "Shots on Goal")
            corners     = _v(sl, "Corner Kicks")
            fouls       = _v(sl, "Fouls")
            offsides    = _v(sl, "Offsides")
            saves       = _v(sl, "Goalkeeper Saves")
            passes_t    = _v(sl, "Total passes")
            pass_acc    = _v(sl, "Passes %")
            yellows     = _v(sl, "Yellow Cards")
            reds        = _v(sl, "Red Cards")

            is_home = 1 if tid == home_team_id else 0

            if not dry_run and tid:
                cur.execute("""
                    INSERT INTO match_stats
                        (wc_match_id, api_fixture_id, team_id, team_name, is_home,
                         xg, possession, shots_total, shots_on_target, corners, fouls,
                         offsides, saves, passes_total, pass_accuracy, yellow_cards, red_cards)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(api_fixture_id, team_id)
                    DO UPDATE SET
                        xg=excluded.xg, possession=excluded.possession,
                        shots_total=excluded.shots_total, shots_on_target=excluded.shots_on_target,
                        corners=excluded.corners, fouls=excluded.fouls, offsides=excluded.offsides,
                        saves=excluded.saves, passes_total=excluded.passes_total,
                        pass_accuracy=excluded.pass_accuracy, yellow_cards=excluded.yellow_cards,
                        red_cards=excluded.red_cards
                """, (wc_match_id, fixture_id, tid, api_tname, is_home,
                      xg, possession, shots_total, shots_on, corners, fouls,
                      offsides, saves, passes_t, pass_acc, yellows, reds))
                summary["stats"] += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return summary


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(fixture_filter: int | None = None, process_all: bool = False,
        dry_run: bool = False, hours_window: int = 6) -> None:
    """Fetch events for WC matches in current time window (or all unprocessed)."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    if fixture_filter:
        rows = conn.execute("""
            SELECT id, api_fixture_id FROM wc_matches WHERE api_fixture_id=?
        """, (fixture_filter,)).fetchall()
        if not rows:
            # treat fixture_filter as wc_match_id
            rows = conn.execute("""
                SELECT id, api_fixture_id FROM wc_matches WHERE id=?
            """, (fixture_filter,)).fetchall()
    elif process_all:
        rows = conn.execute("""
            SELECT id, api_fixture_id FROM wc_matches
            WHERE api_fixture_id IS NOT NULL
            ORDER BY date
        """).fetchall()
    else:
        now   = datetime.utcnow()
        start = (now - timedelta(hours=hours_window)).strftime("%Y-%m-%d %H:%M")
        end   = (now + timedelta(hours=hours_window)).strftime("%Y-%m-%d %H:%M")
        rows = conn.execute("""
            SELECT id, api_fixture_id
            FROM wc_matches
            WHERE api_fixture_id IS NOT NULL
              AND datetime(date || ' ' || COALESCE(time,'00:00')) BETWEEN ? AND ?
            ORDER BY date, time
        """, (start, end)).fetchall()

    conn.close()

    if not rows:
        print("  [events] No WC fixtures to process in current window")
        return

    total_events = 0
    total_stats  = 0
    total_lineups = 0

    for row in rows:
        wc_id  = row["id"]
        fix_id = row["api_fixture_id"]
        if not fix_id:
            continue
        print(f"  [events] Processing fixture {fix_id} (wc_match {wc_id})...")
        summary = process_fixture(fix_id, wc_id, dry_run=dry_run)
        total_events  += summary["events"]
        total_stats   += summary["stats"]
        total_lineups += summary["lineups"]
        score_str = summary["score"] or "N/A"
        print(f"    score={score_str} events={summary['events']} "
              f"stats={summary['stats']} lineups={summary['lineups']}")
        time.sleep(1.5)  # respect rate limits

    print(f"\n  [events] Done. events={total_events} stats={total_stats} lineups={total_lineups}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch WC match events & statistics")
    parser.add_argument("--fixture",  type=int, help="Specific API fixture ID or WC match ID")
    parser.add_argument("--all",      action="store_true", help="Process all fixtures with api_fixture_id")
    parser.add_argument("--dry-run",  action="store_true", help="Fetch but don't write to DB")
    parser.add_argument("--window",   type=int, default=6,  help="Hours window around now (default 6)")
    args = parser.parse_args()

    run(
        fixture_filter=args.fixture,
        process_all=args.all,
        dry_run=args.dry_run,
        hours_window=args.window,
    )
