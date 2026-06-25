"""
sync_stats_to_db.py — Sincroniza los stats de equipo de los JSON procesados a
match_team_stats (que es la que LEE el modelo para xG/tiros/posesión).

Mismo bug de raíz que los resultados (ver sync_results_to_db.py): los stats se
guardaban en data/processed/wc2026_match_stats_*.json pero no se cargaban a la DB,
así que el modelo leía stats solo de la J1 (13/54 partidos). Faltaban ~41.

El JSON trae el set CORE (posesión, xG, tiros, tiros a puerta, córners, amarillas,
ocasiones claras). NO trae el set rico (intercepciones, recuperaciones, duelos…),
que en los 13 partidos ya cargados vino de Sofascore. Por eso este sync hace UPSERT
solo de las columnas core: si la fila (match_id, team_id) ya existe, actualiza solo
esas columnas (preserva las ricas); si no existe, la crea.

Empareja por team_id (robusto a variantes de nombre). Idempotente.

Uso:
    python scripts/sync_stats_to_db.py
    python scripts/sync_stats_to_db.py --dry-run
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

STAT_FILES = [
    BASE_DIR / "data" / "processed" / "wc2026_match_stats_j1_j2.json",
    BASE_DIR / "data" / "processed" / "wc2026_match_stats_j3.json",
]

NAME = {
    "Turkiye": "Turkey", "Cabo Verde": "Cape Verde", "United States": "USA",
    "Korea Republic": "South Korea", "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia", "Curaçao": "Curacao",
}

# columna match_team_stats <- (campo_home, campo_away) del JSON
CORE = {
    "possession":      ("possession_home", "possession_away"),
    "xg":              ("xg_home", "xg_away"),
    "shots_total":     ("shots_total_home", "shots_total_away"),
    "shots_on_target": ("shots_on_target_home", "shots_on_target_away"),
    "corners":         ("corners_home", "corners_away"),
    "yellow_cards":    ("yellow_home", "yellow_away"),
    "clear_chances":   ("big_chances_home", "big_chances_away"),
}


def _load(path):
    if not path.exists():
        return []
    j = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(j, list):
        return j
    return j.get("stats", j.get("matches", []))


def _tid(conn, name):
    n = NAME.get(name, name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
    return r[0] if r else None


def _upsert(conn, match_id, team_id, is_home, vals, dry):
    """UPSERT solo de columnas core; preserva columnas ricas existentes."""
    row = conn.execute(
        "SELECT id FROM match_team_stats WHERE match_id=? AND team_id=?",
        (match_id, team_id)).fetchone()
    if dry:
        return "update" if row else "insert"
    if row:
        sets = ", ".join(f"{c}=?" for c in vals)
        conn.execute(f"UPDATE match_team_stats SET {sets} WHERE id=?",
                     (*vals.values(), row[0]))
        return "update"
    cols = ["match_id", "team_id", "is_home", *vals.keys()]
    qs = ",".join("?" * len(cols))
    conn.execute(f"INSERT INTO match_team_stats ({','.join(cols)}) VALUES ({qs})",
                 (match_id, team_id, 1 if is_home else 0, *vals.values()))
    return "insert"


def sync(db_path=DB, dry_run=False, verbose=True):
    conn = sqlite3.connect(str(db_path))
    items = []
    for f in STAT_FILES:
        items += _load(f)

    ins = upd = 0
    problems = []
    for m in items:
        h = m.get("home_team") or m.get("home")
        a = m.get("away_team") or m.get("away")
        hid, aid = _tid(conn, h), _tid(conn, a)
        if not hid or not aid:
            problems.append(("sin team_id", h, a))
            continue
        row = conn.execute(
            "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? AND stage='group'",
            (hid, aid)).fetchone()
        if not row:
            problems.append(("sin partido", h, a))
            continue
        mid = row[0]
        for team_id, is_home, side in ((hid, True, 0), (aid, False, 1)):
            vals = {}
            for col, (fh, fa) in CORE.items():
                v = m.get(fh if is_home else fa)
                if v is not None:
                    vals[col] = v
            if not vals:
                continue
            r = _upsert(conn, mid, team_id, is_home, vals, dry_run)
            if r == "insert":
                ins += 1
            else:
                upd += 1

    if not dry_run:
        conn.commit()
    n = conn.execute(
        "SELECT COUNT(DISTINCT match_id) FROM match_team_stats mts "
        "JOIN wc_matches w ON w.id=mts.match_id WHERE w.stage='group'").fetchone()[0]
    conn.close()

    if verbose:
        tag = "[DRY-RUN] " if dry_run else ""
        print(f"{tag}Stats: {ins} filas-equipo insertadas, {upd} actualizadas, "
              f"{len(problems)} problemas.")
        for p in problems:
            print("   ", p)
        print(f"{tag}match_team_stats: {n} partidos de grupo con stats.")
    return {"insert": ins, "update": upd, "problems": problems}


if __name__ == "__main__":
    sync(dry_run="--dry-run" in sys.argv)
