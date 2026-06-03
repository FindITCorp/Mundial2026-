"""
scripts/validate_squads.py — Validador de integridad de squads WC2026.
Detecta: faltan GK/DEF/MID/FWD, edad >38, duplicados, XI sin GK, posiciones mal balanceadas.
"""
import sqlite3, logging
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("validate")

MIN_POS = {"GK": 2, "DEF": 5, "MID": 4, "FWD": 2}
MAX_AGE  = 42
SQUAD_SIZE_MIN = 20
SQUAD_SIZE_MAX = 26


def validate(db_path: Path = DB_PATH) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    teams = conn.execute(
        "SELECT id, name FROM teams ORDER BY name"
    ).fetchall()

    issues: dict[str, list[str]] = {}
    total_warnings = 0

    for team in teams:
        tid, tname = team["id"], team["name"]

        players = conn.execute("""
            SELECT p.id, p.name, p.position, p.age, p.club
            FROM squad_selections ss
            JOIN players p ON p.id = ss.player_id
            WHERE ss.team_id = ?
        """, (tid,)).fetchall()

        if not players:
            continue   # equipo sin squad — skip (no WC)

        errs = []

        # ── 1. Tamaño del squad ──────────────────────────────────────────
        n = len(players)
        if n < SQUAD_SIZE_MIN:
            errs.append(f"Squad pequeño: {n} jugadores (mín {SQUAD_SIZE_MIN})")
        if n > SQUAD_SIZE_MAX:
            errs.append(f"Squad grande: {n} jugadores (máx {SQUAD_SIZE_MAX})")

        # ── 2. Balance por posición ──────────────────────────────────────
        pos_count = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
        for p in players:
            pos = p["position"]
            if pos in pos_count:
                pos_count[pos] += 1
        for pos, min_n in MIN_POS.items():
            if pos_count[pos] < min_n:
                errs.append(f"Pocos {pos}: {pos_count[pos]} (mín {min_n})")

        # ── 3. XI proyectado sin GK ──────────────────────────────────────
        xi_gk = conn.execute("""
            SELECT COUNT(*) FROM projected_lineups pl
            JOIN players p ON p.id = pl.player_id
            WHERE pl.team_id = ? AND pl.is_starter = 1 AND p.position = 'GK'
        """, (tid,)).fetchone()[0]
        if xi_gk == 0:
            errs.append("XI proyectado sin GK")
        elif xi_gk > 1:
            errs.append(f"XI proyectado con {xi_gk} GK")

        # ── 4. Jugadores mayores de MAX_AGE ─────────────────────────────
        old = [p["name"] for p in players if p["age"] and p["age"] > MAX_AGE]
        if old:
            errs.append(f"Edad >{MAX_AGE}: {', '.join(old)}")

        # ── 5. Duplicados (nombre normalizado) ───────────────────────────
        import unicodedata
        def norm(s):
            nfkd = unicodedata.normalize("NFKD", s or "")
            return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

        names_norm = [norm(p["name"]) for p in players]
        seen = set(); dupes = set()
        for nm in names_norm:
            if nm in seen:
                dupes.add(nm)
            seen.add(nm)
        if dupes:
            errs.append(f"Duplicados: {', '.join(dupes)}")

        # ── 6. Balance ofensivo-defensivo del XI ─────────────────────────
        xi = conn.execute("""
            SELECT p.position FROM projected_lineups pl
            JOIN players p ON p.id = pl.player_id
            WHERE pl.team_id = ? AND pl.is_starter = 1
        """, (tid,)).fetchall()
        xi_pos = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
        for r in xi:
            if r["position"] in xi_pos:
                xi_pos[r["position"]] += 1
        if xi_pos["FWD"] > 4:
            errs.append(f"XI desequilibrado: {xi_pos['FWD']} FWD (máx esperado 4)")
        if xi_pos["MID"] < 2:
            errs.append(f"XI desequilibrado: solo {xi_pos['MID']} MID")
        if xi_pos["DEF"] < 3:
            errs.append(f"XI desequilibrado: solo {xi_pos['DEF']} DEF")

        if errs:
            issues[tname] = errs
            total_warnings += len(errs)

    conn.close()

    # ── Reporte ───────────────────────────────────────────────────────────
    if not issues:
        log.info("✅ Todos los squads son válidos")
    else:
        log.warning("⚠️  %d equipos con %d problemas detectados:",
                    len(issues), total_warnings)
        for team, errs in sorted(issues.items()):
            for e in errs:
                log.warning("  %-20s → %s", team, e)

    return issues


if __name__ == "__main__":
    issues = validate()
    print(f"\n{'='*55}")
    print(f"  Equipos con problemas: {len(issues)}")
    print(f"{'='*55}")
    for team, errs in sorted(issues.items()):
        print(f"  {team}")
        for e in errs:
            print(f"    ⚠  {e}")
