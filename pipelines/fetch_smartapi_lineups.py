"""
fetch_smartapi_lineups.py — Alineaciones y datos de partido vía Free API Live
Football Data (Creativesdev / RapidAPI).

Modos:
  --mode friendlies   Recorre los últimos N días, toma partidos donde participa
                      al menos un equipo del WC2026, baja alineaciones (titulares
                      + suplentes) y estadísticas → player_match_usage, match_stats.
  --mode matchday     Para HOY: cruza con wc_matches, baja XI confirmado (1h antes)
                      → match_lineups (estimated=0) + player_match_usage + match_stats.

Solo corre desde GitHub Actions (RapidAPI bloqueado localmente).

Uso:
  python pipelines/fetch_smartapi_lineups.py --mode friendlies --days 10
  python pipelines/fetch_smartapi_lineups.py --mode matchday
  python pipelines/fetch_smartapi_lineups.py --mode friendlies --dry-run
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB_PATH = BASE_DIR / "data" / "mundial2026.db"

from pipelines import smartapi  # noqa: E402

# Alias nombre Smart API → nombre en nuestra tabla teams
TEAM_ALIASES = {
    "united states": "USA",
    "korea republic": "South Korea",
    "ivory coast": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "dr congo": "DR Congo",
    "czech republic": "Czechia",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
    "cabo verde": "Cape Verde",
    "curacao": "Curacao",
    "curaçao": "Curacao",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _build_team_index(conn) -> dict:
    """norm(name) → team_id para todos los equipos WC."""
    idx = {}
    for tid, name in conn.execute("SELECT id, name FROM teams WHERE wc_group IS NOT NULL").fetchall():
        idx[_norm(name)] = tid
    return idx


def _resolve_team(team_index: dict, api_name: str) -> int | None:
    n = _norm(api_name)
    if n in team_index:
        return team_index[n]
    alias = TEAM_ALIASES.get(n)
    if alias and _norm(alias) in team_index:
        return team_index[_norm(alias)]
    # contiene
    for k, tid in team_index.items():
        if n and (n in k or k in n):
            return tid
    return None


def _resolve_player(conn, team_id: int, api_player: dict, cache: dict) -> int | None:
    """Mapea un jugador de Smart API a players.id dentro del equipo."""
    key = (team_id, api_player.get("id"))
    if key in cache:
        return cache[key]

    name = api_player.get("name") or ""
    first = api_player.get("firstName") or ""
    last = api_player.get("lastName") or ""
    candidates = conn.execute(
        "SELECT id, name FROM players WHERE team_id=?", (team_id,)
    ).fetchall()

    norm_full = _norm(name)
    norm_last = _norm(last)
    pid = None
    # exacto normalizado
    for cid, cname in candidates:
        if _norm(cname) == norm_full:
            pid = cid
            break
    # apellido
    if pid is None and len(norm_last) > 2:
        for cid, cname in candidates:
            if _norm(cname).split() and _norm(cname).split()[-1] == norm_last:
                pid = cid
                break
    # primer+último
    if pid is None and first and last:
        target = _norm(f"{first} {last}")
        for cid, cname in candidates:
            if _norm(cname) == target:
                pid = cid
                break
    cache[key] = pid
    return pid


def _ensure_player(conn, team_id: int, api_player: dict) -> int | None:
    """Crea el jugador si no existe (datos de Smart API: nombre, edad, club, dorsal)."""
    name = api_player.get("name") or ""
    if not name:
        return None
    pos_id = api_player.get("usualPlayingPositionId", 0)
    # Map grosero positionId FotMob → nuestra categoría
    pos = "GK" if api_player.get("positionId") == 11 else None
    row = conn.execute(
        "INSERT INTO players (name, team_id, position, club, age) VALUES (?,?,?,?,?)",
        (name, team_id, pos or "MID", api_player.get("primaryTeamName"), api_player.get("age")),
    )
    return row.lastrowid


def _save_lineup(conn, team_id: int, lineup: dict, match_id, match_date: str,
                 competition: str, wc_match_id: int | None, pcache: dict,
                 dry_run: bool) -> int:
    """Guarda titulares+suplentes en player_match_usage (+ match_lineups si es WC)."""
    saved = 0
    for is_starter, group in ((1, lineup.get("starters", [])),
                              (0, lineup.get("subs", []))):
        for ap in group:
            pid = _resolve_player(conn, team_id, ap, pcache)
            if pid is None and not dry_run:
                pid = _ensure_player(conn, team_id, ap)
            if pid is None:
                continue
            mins = 90 if is_starter else 0
            if not dry_run:
                conn.execute("""
                    INSERT OR IGNORE INTO player_match_usage
                        (player_id, team_id, match_id, match_date, competition,
                         is_starter, minutes_played)
                    VALUES (?,?,?,?,?,?,?)
                """, (pid, team_id, match_id, match_date, competition, is_starter, mins))
                if wc_match_id:
                    conn.execute("""
                        INSERT OR IGNORE INTO match_lineups
                            (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                        VALUES (?,?,?,?,?,0,datetime('now'))
                    """, (wc_match_id, team_id, pid, str(ap.get("positionId") or ""), is_starter))
            saved += 1
    return saved


def _save_stats(conn, event_id, wc_match_id, home_tid, away_tid,
                home_name, away_name, dry_run: bool) -> int:
    groups = smartapi.match_stats(event_id)
    if not groups:
        return 0
    flat = smartapi.flatten_team_stats(groups)
    rows = 0
    for side, tid, tname, is_home in (("home", home_tid, home_name, 1),
                                      ("away", away_tid, away_name, 0)):
        i = 0 if side == "home" else 1
        if not tid or dry_run:
            continue
        conn.execute("""
            INSERT INTO match_stats
                (wc_match_id, api_fixture_id, team_id, team_name, is_home,
                 xg, possession, shots_total, shots_on_target, corners, fouls,
                 offsides, saves)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(api_fixture_id, team_id) DO UPDATE SET
                xg=excluded.xg, possession=excluded.possession,
                shots_total=excluded.shots_total, shots_on_target=excluded.shots_on_target,
                corners=excluded.corners, fouls=excluded.fouls,
                offsides=excluded.offsides, saves=excluded.saves
        """, (wc_match_id, event_id, tid, tname, is_home,
              flat["xg"][i], flat["possession"][i], flat["shots_total"][i],
              flat["shots_on_target"][i], flat["corners"][i], flat["fouls"][i],
              flat["offsides"][i], flat["saves"][i]))
        rows += 1
    return rows


def _process_match(conn, m: dict, team_index: dict, pcache: dict,
                   wc_match_id: int | None, dry_run: bool) -> dict:
    event_id = m.get("id")
    home = m.get("home", {})
    away = m.get("away", {})
    home_tid = _resolve_team(team_index, home.get("name", ""))
    away_tid = _resolve_team(team_index, away.get("name", ""))
    if not home_tid and not away_tid:
        return {"skipped": True}

    match_date = (m.get("status", {}).get("utcTime", "") or "")[:10] or \
                 datetime.utcnow().strftime("%Y-%m-%d")
    competition = "Friendly"
    summary = {"event_id": event_id, "home": home.get("name"), "away": away.get("name"),
               "players": 0, "stats_rows": 0}

    if home_tid:
        lu = smartapi.team_lineup(event_id, "home")
        if lu:
            summary["players"] += _save_lineup(conn, home_tid, lu, event_id, match_date,
                                                competition, wc_match_id, pcache, dry_run)
    if away_tid:
        lu = smartapi.team_lineup(event_id, "away")
        if lu:
            summary["players"] += _save_lineup(conn, away_tid, lu, event_id, match_date,
                                                competition, wc_match_id, pcache, dry_run)

    summary["stats_rows"] = _save_stats(conn, event_id, wc_match_id, home_tid, away_tid,
                                        home.get("name"), away.get("name"), dry_run)
    return summary


def run_friendlies(days: int = 10, dry_run: bool = False) -> None:
    import traceback
    report = {"mode": "friendlies", "ran_at": datetime.utcnow().isoformat(),
              "days": days, "matches_processed": [], "total_players": 0,
              "errors": [], "dates_scanned": []}
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        team_index = _build_team_index(conn)
        pcache: dict = {}
        today = datetime.utcnow().date()
        for d in range(days):
            day = today - timedelta(days=d)
            ymd = day.strftime("%Y%m%d")
            try:
                matches = smartapi.matches_by_date(ymd)
            except Exception as e:
                report["errors"].append(f"matches_by_date {ymd}: {e}")
                continue
            report["dates_scanned"].append({"date": ymd, "matches": len(matches)})
            if not matches:
                continue
            for m in matches:
                home = (m.get("home") or {}).get("name", "")
                away = (m.get("away") or {}).get("name", "")
                if not (_resolve_team(team_index, home) or _resolve_team(team_index, away)):
                    continue
                if not (m.get("status", {}).get("finished")):
                    continue
                try:
                    s = _process_match(conn, m, team_index, pcache, None, dry_run)
                except Exception as e:
                    report["errors"].append(f"{home} vs {away}: {e} | {traceback.format_exc()[:300]}")
                    continue
                if s.get("skipped"):
                    continue
                report["matches_processed"].append(s)
                report["total_players"] += s.get("players", 0)
                print(f"  {ymd} {s.get('home')} vs {s.get('away')}: "
                      f"{s.get('players')} jugadores, {s.get('stats_rows')} stats")
        if not dry_run:
            conn.commit()
        report["pmu_total"] = conn.execute("SELECT COUNT(*) FROM player_match_usage").fetchone()[0]
        report["teams_covered"] = conn.execute("SELECT COUNT(DISTINCT team_id) FROM player_match_usage").fetchone()[0]
    except Exception as e:
        report["fatal"] = f"{e} | {traceback.format_exc()[:500]}"
    finally:
        conn.close()
        out = BASE_DIR / "data" / "lineups" / "smartapi_friendlies_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(f"\n  Reporte → {out.relative_to(BASE_DIR)} | players(run)={report['total_players']} "
              f"pmu_total={report.get('pmu_total')} errors={len(report['errors'])}")


def run_matchday(dry_run: bool = False) -> None:
    """Para HOY: alineaciones confirmadas de partidos del Mundial."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    team_index = _build_team_index(conn)
    pcache: dict = {}

    today = datetime.utcnow().strftime("%Y-%m-%d")
    wc_today = conn.execute("""
        SELECT id, home_team_id, away_team_id, home_team_name, away_team_name
        FROM wc_matches WHERE date=?
    """, (today,)).fetchall()
    if not wc_today:
        print("  Sin partidos WC hoy")
        conn.close()
        return

    matches = smartapi.matches_by_date(today.replace("-", ""))
    processed = 0
    for wc in wc_today:
        # buscar el evento Smart API que cruce por nombres
        for m in matches:
            h = _resolve_team(team_index, (m.get("home") or {}).get("name", ""))
            a = _resolve_team(team_index, (m.get("away") or {}).get("name", ""))
            if h == wc["home_team_id"] and a == wc["away_team_id"]:
                s = _process_match(conn, m, team_index, pcache, wc["id"], dry_run)
                # mapear eventid
                if not dry_run:
                    conn.execute("UPDATE wc_matches SET api_fixture_id=? WHERE id=?",
                                 (m.get("id"), wc["id"]))
                print(f"  WC {wc['home_team_name']} vs {wc['away_team_name']}: "
                      f"{s.get('players')} jugadores")
                processed += 1
                break

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"  Partidos WC procesados hoy: {processed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["friendlies", "matchday"], default="friendlies")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.mode == "friendlies":
        run_friendlies(days=args.days, dry_run=args.dry_run)
    else:
        run_matchday(dry_run=args.dry_run)
