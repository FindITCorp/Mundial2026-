"""
full_update.py — Master orchestrator pipeline for Mundial 2026 data.

Runs ALL pipelines in correct order with rate limiting and logging.

Usage:
  python pipelines/full_update.py                        # Full refresh
  python pipelines/full_update.py --scope squads         # Only squad lists
  python pipelines/full_update.py --scope stats          # Only player stats
  python pipelines/full_update.py --scope form           # Only recent form
  python pipelines/full_update.py --scope lineups        # Only match lineups
  python pipelines/full_update.py --scope wc             # Only WC results
  python pipelines/full_update.py --teams "Panama" "Croatia"  # Specific teams
  python pipelines/full_update.py --quick                # Skip slow API calls
"""
import sys
import time
import argparse
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
LOGS_DIR = BASE_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

VALID_SCOPES = ("all", "squads", "stats", "form", "lineups", "wc", "historical")


def _setup_logger() -> logging.Logger:
    """Configure logging to file and stdout."""
    today = datetime.now().strftime("%Y%m%d")
    log_file = LOGS_DIR / f"update_{today}.log"

    logger = logging.getLogger("full_update")
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                   datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


logger = _setup_logger()


# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_db_exists() -> bool:
    """Run setup_db.py if DB doesn't exist or is missing tables."""
    if not DB_PATH.exists():
        logger.info("Base de datos no encontrada. Ejecutando setup_db.py...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "scripts" / "setup_db.py")],
            capture_output=False,
        )
        return result.returncode == 0

    # Check if tables exist
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        conn.close()
        if count == 0:
            logger.warning("DB existe pero sin datos. Ejecutando setup_db.py...")
            import subprocess
            subprocess.run(
                [sys.executable, str(BASE_DIR / "scripts" / "setup_db.py")],
                capture_output=False,
            )
    except Exception:
        logger.warning("DB existe pero tablas faltan. Ejecutando setup_db.py...")
        import subprocess
        subprocess.run(
            [sys.executable, str(BASE_DIR / "scripts" / "setup_db.py")],
            capture_output=False,
        )

    return DB_PATH.exists()


def _step(name: str, fn, *args, **kwargs):
    """
    Run a pipeline step with timing, error handling, and logging.
    Returns result or None on error.
    """
    logger.info(f"{'='*55}")
    logger.info(f"PASO: {name}")
    logger.info(f"{'='*55}")
    start = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"  Completado en {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"  ERROR despues de {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


def _db_summary() -> dict:
    """Return row counts for all main tables."""
    conn = sqlite3.connect(DB_PATH)
    tables = [
        "teams", "players", "team_matches", "wc_matches",
        "wc_history", "player_club_stats", "player_nat_stats",
        "player_ratings", "squad_selections", "match_lineups", "match_players",
    ]
    summary = {}
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            summary[table] = count
        except Exception:
            summary[table] = 0
    conn.close()
    return summary


def _print_summary(summary: dict) -> None:
    logger.info(f"\n{'='*55}")
    logger.info("RESUMEN DE BASE DE DATOS:")
    for table, count in summary.items():
        logger.info(f"  {table:<25}: {count:>6} registros")


# ── Pipeline steps ────────────────────────────────────────────────────────────

def step_setup_db():
    """Step 0: Ensure DB exists with all tables populated."""
    ensure_db_exists()


def step_fetch_wc_schedule():
    """Step 1: Fetch WC2026 match schedule from football-data.org."""
    try:
        from pipelines.fetch_football_data_org import fetch_wc_schedule, _save_schedule_to_db
        matches = fetch_wc_schedule()
        if matches:
            saved = _save_schedule_to_db(matches)
            logger.info(f"  Schedule: {len(matches)} partidos, {saved} guardados")
        else:
            logger.info("  Schedule: sin datos API, usando calendario estático")
    except Exception as e:
        logger.error(f"  fetch_wc_schedule error: {e}")


def step_fetch_team_form(teams=None, delay_secs=2.0):
    """Step 2: Daily form update — all 48 teams, all sources."""
    # Primary: multi-source daily form (martj42 + FD.org + api-sports.io)
    try:
        from pipelines.fetch_daily_form import run as daily_form_run
        daily_form_run()
        return
    except Exception as e:
        logger.warning(f"  fetch_daily_form error: {e}")

    # Fallback: API-Football only
    try:
        from pipelines.fetch_api_football import run_fetch_team_form, _has_api_key
        if _has_api_key():
            result = run_fetch_team_form(teams=teams, last=20, delay_secs=delay_secs)
            logger.info(f"  API-Football form: {result}")
            return
    except Exception as e:
        logger.warning(f"  API-Football form error: {e}")

    # Last fallback
    try:
        from pipelines.fetch_team_matches import run as fetch_matches_run
        fetch_matches_run(teams=teams, delay_secs=delay_secs)
    except Exception as e:
        logger.error(f"  fetch_team_matches error: {e}")


def step_fetch_squads(teams=None, delay_secs=2.0):
    """Step 3: Fetch official squads for all 48 teams."""
    # Try API-Football
    try:
        from pipelines.fetch_api_football import run_fetch_all_squads, _has_api_key
        if _has_api_key():
            result = run_fetch_all_squads(teams=teams, delay_secs=delay_secs)
            logger.info(f"  API-Football squads: {result}")
    except Exception as e:
        logger.warning(f"  API-Football squads error: {e}")

    # Always run existing fetch_players as fallback / supplement
    try:
        from pipelines.fetch_players import run as fetch_players_run
        fetch_players_run(teams=teams)
    except Exception as e:
        logger.error(f"  fetch_players error: {e}")


def step_fetch_club_stats(teams=None):
    """Step 4: Fetch club stats for all convoked players (last 3 seasons)."""
    try:
        from pipelines.fetch_club_stats import run as fetch_club_run
        fetch_club_run(teams=teams)
    except Exception as e:
        logger.error(f"  fetch_club_stats error: {e}")


def step_fetch_nat_stats(teams=None):
    """Step 5: Fetch and synthesize national team stats."""
    try:
        from pipelines.fetch_nat_stats import run as fetch_nat_run
        fetch_nat_run(teams=teams)
    except Exception as e:
        logger.error(f"  fetch_nat_stats error: {e}")


def step_compute_player_ratings(teams=None):
    """Step 6: Compute player_ratings for all players."""
    try:
        from models.player_rating import compute_all_ratings
        compute_all_ratings(teams=teams)
        logger.info("  Player ratings computed")
    except AttributeError:
        # compute_all_ratings may not exist — try alternative
        try:
            from models.player_rating import PlayerRater
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row

            if teams:
                rows = conn.execute(
                    f"SELECT id FROM teams WHERE name IN ({','.join('?' * len(teams))})",
                    teams
                ).fetchall()
            else:
                rows = conn.execute("SELECT id FROM teams").fetchall()

            rater = PlayerRater(DB_PATH)
            count = 0
            for row in rows:
                count += rater.rate_team(row["id"])
            conn.close()
            logger.info(f"  {count} player ratings computed")
        except Exception as e2:
            logger.error(f"  compute_player_ratings error: {e2}")
    except Exception as e:
        logger.error(f"  compute_player_ratings error: {e}")


def step_update_squad_selections(teams=None):
    """Step 7: Update squad_selections with latest official lists."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure every player in players table has a squad_selections entry
    if teams:
        rows = cur.execute(
            f"SELECT id FROM teams WHERE name IN ({','.join('?' * len(teams))})",
            teams
        ).fetchall()
        team_ids = [r["id"] for r in rows]
    else:
        team_ids = [r["id"] for r in cur.execute("SELECT id FROM teams").fetchall()]

    inserted = 0
    for team_id in team_ids:
        players = cur.execute(
            "SELECT id FROM players WHERE team_id=?", (team_id,)
        ).fetchall()
        for p in players:
            cur.execute("""
                INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed)
                VALUES (?,?,1)
            """, (team_id, p["id"]))
            inserted += cur.rowcount

    conn.commit()
    conn.close()
    if inserted:
        logger.info(f"  squad_selections: {inserted} nuevas entradas")


def step_update_wc_results():
    """Step 8: Update WC match results (during tournament)."""
    try:
        from pipelines.update_wc import run as update_wc_run
        update_wc_run()
    except Exception as e:
        logger.error(f"  update_wc error: {e}")


def step_fetch_historical():
    """Step: Fetch historical WC match data + player stats per match."""
    try:
        from pipelines.fetch_historical import run as fetch_historical_run
        fetch_historical_run()
    except Exception as e:
        logger.error(f"  fetch_historical error: {e}")


def step_fetch_live_lineups(upcoming_only=True):
    """Step 9 (tournament mode): Fetch confirmed lineups for upcoming/live matches."""
    try:
        from pipelines.fetch_api_football import fetch_live_lineups, _save_lineups_to_db, _has_api_key
        if not _has_api_key():
            logger.info("  Sin API key — saltando fetch de alineaciones")
            return

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if upcoming_only:
            today = datetime.now().strftime("%Y-%m-%d")
            matches = conn.execute("""
                SELECT id FROM wc_matches
                WHERE date >= ? AND played=0
                ORDER BY date, time LIMIT 4
            """, (today,)).fetchall()
        else:
            matches = conn.execute("""
                SELECT id FROM wc_matches
                WHERE played=0
                ORDER BY date, time LIMIT 10
            """).fetchall()

        conn.close()

        for m in matches:
            logger.info(f"  Fetching lineup for match ID {m['id']}")
            lineups = fetch_live_lineups(m["id"])
            if lineups:
                saved = _save_lineups_to_db(m["id"], lineups)
                logger.info(f"    -> {saved} lineup entries saved")
            time.sleep(1)

    except Exception as e:
        logger.error(f"  fetch_live_lineups error: {e}")


def step_fetch_martj42(since: str = "2023-01-01", teams=None):
    """Step: Import open-source international results from martj42/international_results."""
    try:
        from pipelines.fetch_martj42 import run as martj42_run
        stats = martj42_run(since=since, team_filter=teams)
        logger.info(
            f"  martj42: +{stats['matches_inserted']} partidos | "
            f"{stats['goals_linked']} goles vinculados"
        )
    except Exception as e:
        logger.error(f"  fetch_martj42 error: {e}")


def step_rebuild_projected_lineups(teams=None):
    """Step 8: Rebuild wc26_squad + projected_lineups from current DB state."""
    try:
        from pipelines.rebuild_squads import rebuild
        stats = rebuild(team_filter=teams)
        logger.info(
            f"  Projected lineups: {stats['teams']} equipos | "
            f"{stats['starters']} titulares | {stats['bench']} suplentes"
        )
        if stats["warnings"]:
            logger.warning(f"  {len(stats['warnings'])} data warnings en rebuild")
    except Exception as e:
        logger.error(f"  rebuild_projected_lineups error: {e}")


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run(scope: str = "all", teams=None, quick: bool = False) -> bool:
    """
    Master pipeline orchestrator.

    Args:
        scope: One of "all", "squads", "stats", "form", "lineups"
        teams: Optional list of team names to limit updates to
        quick: Skip slow API calls (useful for testing)

    Returns:
        True on success, False on critical failure
    """
    start_total = time.time()

    scope = scope.lower()
    if scope not in VALID_SCOPES:
        logger.error(f"Scope invalido: {scope}. Usar: {VALID_SCOPES}")
        return False

    logger.info(f"\n{'='*55}")
    logger.info(f"FULL UPDATE PIPELINE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Scope: {scope}")
    logger.info(f"Teams: {teams or 'ALL'}")
    logger.info(f"Quick: {quick}")
    logger.info(f"{'='*55}")

    delay = 1.0 if quick else 2.5

    # Step 0: Always ensure DB
    _step("Setup DB", step_setup_db)

    # ── Scope: wc (tournament results only) ──────────────────────────────────
    if scope == "wc":
        _step("Update WC Results", step_update_wc_results)
        _print_summary(_db_summary())
        return True

    # ── Scope: historical (WC 2014/2018/2022 + player stats per match) ──────
    if scope == "historical":
        _step("Fetch Historical WC Data", step_fetch_historical)
        _print_summary(_db_summary())
        return True

    # ── Scope: lineups (fetch confirmed match lineups) ────────────────────────
    if scope == "lineups":
        _step("Fetch WC Schedule", step_fetch_wc_schedule)
        _step("Fetch Live Lineups", step_fetch_live_lineups, upcoming_only=True)
        _print_summary(_db_summary())
        return True

    # ── Scope: form (team recent form only) ──────────────────────────────────
    if scope == "form":
        _step("Fetch WC Schedule", step_fetch_wc_schedule)
        _step("martj42 open results (2023+)", step_fetch_martj42, "2023-01-01", teams)
        _step("Fetch Team Form (last 20 matches)",
              step_fetch_team_form, teams, delay)
        _print_summary(_db_summary())
        return True

    # ── Scope: squads (official squad lists only) ────────────────────────────
    if scope == "squads":
        _step("Fetch Official Squads", step_fetch_squads, teams, delay)
        _step("Update Squad Selections", step_update_squad_selections, teams)
        _step("Rebuild Projected Lineups", step_rebuild_projected_lineups, teams)
        _print_summary(_db_summary())
        return True

    # ── Scope: stats (player stats only) ────────────────────────────────────
    if scope == "stats":
        _step("Fetch Club Stats", step_fetch_club_stats, teams)
        _step("Fetch Nat Stats", step_fetch_nat_stats, teams)
        _step("Compute Player Ratings", step_compute_player_ratings, teams)
        _print_summary(_db_summary())
        return True

    # ── Scope: all — full pipeline ───────────────────────────────────────────
    # Step 1: WC Schedule (football-data.org)
    _step("Fetch WC Schedule (football-data.org)", step_fetch_wc_schedule)

    # Step 1b: Open-source international results (no API key needed)
    _step("martj42 open results (2023+)", step_fetch_martj42, "2023-01-01", teams)

    # Step 2: Team recent form (last 20 matches for all 48 teams)
    if not quick:
        _step("Fetch Team Form (last 20 matches)",
              step_fetch_team_form, teams, delay)
    else:
        logger.info("Saltando Team Form (modo quick)")

    # Step 3: Official squads for all 48 teams
    _step("Fetch Official Squads (all 48 teams)",
          step_fetch_squads, teams, delay)

    # Step 4: Club stats for all convoked players
    if not quick:
        _step("Fetch Club Stats (last 3 seasons)",
              step_fetch_club_stats, teams)
    else:
        logger.info("Saltando Club Stats (modo quick)")

    # Step 5: National team stats
    _step("Synthesize Nat Stats", step_fetch_nat_stats, teams)

    # Step 6: Compute player ratings
    _step("Compute Player Ratings", step_compute_player_ratings, teams)

    # Step 7: Update squad selections
    _step("Update Squad Selections", step_update_squad_selections, teams)

    # Step 8: Rebuild projected lineups (wc26_squad + projected_lineups)
    _step("Rebuild Projected Lineups", step_rebuild_projected_lineups, teams)

    # Step 9: WC results (even before tournament = setup/verify wc_matches)
    _step("Update WC Results/Schedule", step_update_wc_results)

    # Final summary
    total_elapsed = time.time() - start_total
    summary = _db_summary()

    logger.info(f"\n{'='*55}")
    logger.info(f"PIPELINE COMPLETADO en {total_elapsed:.0f}s")
    _print_summary(summary)

    teams_updated = summary.get("teams", 0)
    players_updated = summary.get("players", 0)
    matches_updated = summary.get("team_matches", 0)
    logger.info(f"\n  {teams_updated} equipos | {players_updated} jugadores | {matches_updated} partidos")

    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Master pipeline — Mundial 2026",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scopes:
  all        — Full refresh (squads + stats + form + schedule + ratings)
  squads     — Only fetch official squad lists (useful when convocatorias drop)
  stats      — Only update player stats and ratings
  form       — Only update team recent form (last 20 matches)
  lineups    — Only fetch confirmed match lineups
  wc         — Only update WC match results (use during tournament)
  historical — Fetch WC 2014/2018/2022 + player stats per match (incremental)

Examples:
  python pipelines/full_update.py --scope all
  python pipelines/full_update.py --scope squads
  python pipelines/full_update.py --scope form --teams "Panama" "Croatia"
  python pipelines/full_update.py --scope historical
  python pipelines/full_update.py --scope all --quick
        """
    )
    parser.add_argument(
        "--scope",
        default="all",
        choices=list(VALID_SCOPES),
        help="What to update (default: all)",
    )
    parser.add_argument(
        "--teams", nargs="+",
        help="Only update specific teams: --teams Panama Croatia",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Skip slow API calls (club_stats, team_form)",
    )
    args = parser.parse_args()

    success = run(
        scope=args.scope,
        teams=args.teams,
        quick=args.quick,
    )
    sys.exit(0 if success else 1)
