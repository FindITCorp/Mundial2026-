"""
sync_results_to_db.py — Sincroniza los resultados de los JSON procesados a la
tabla wc_matches (que es la que LEE el modelo).

Bug que arregla (detectado 25-jun-2026): el pipeline guardaba resultados en
data/processed/wc2026_results_*.json pero NO los cargaba a wc_matches, así que
el modelo predecía con una DB a la que le faltaban decenas de resultados reales
(p.ej. Turquía con λ 2.25 pese a llevar 0 goles, porque sus partidos de grupo
sin gol no estaban en la DB).

Empareja por TEAM_ID (robusto ante variantes de nombre: Turkiye/Turkey,
Curaçao/Curacao, Czech Republic/Czechia, Cabo Verde/Cape Verde, etc.).
Idempotente: solo actualiza filas cuyo marcador difiere o que están played=0.

Uso:
    python scripts/sync_results_to_db.py            # sincroniza todos los JSON de resultados
    python scripts/sync_results_to_db.py --dry-run  # solo reporta, no escribe
"""
import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

RESULT_FILES = [
    BASE_DIR / "data" / "processed" / "wc2026_results_j1_j2.json",
    BASE_DIR / "data" / "processed" / "wc2026_results_j3.json",
]

# JSON team name -> teams.name canónico en la DB
NAME = {
    "Turkiye": "Turkey", "Cabo Verde": "Cape Verde",
    "United States": "USA", "Korea Republic": "South Korea",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Cote d'Ivoire": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia", "Curaçao": "Curacao",
}


def _load(path: Path):
    if not path.exists():
        return []
    j = json.loads(path.read_text(encoding="utf-8"))
    return j if isinstance(j, list) else j.get("matches", j.get("results", []))


def _tid(conn, name):
    n = NAME.get(name, name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
    return r[0] if r else None


def sync(db_path=DB, dry_run=False, verbose=True):
    conn = sqlite3.connect(str(db_path))
    results = []
    for f in RESULT_FILES:
        results += _load(f)

    updated = already = 0
    problems = []
    for m in results:
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        hid, aid = _tid(conn, m["home"]), _tid(conn, m["away"])
        if not hid or not aid:
            problems.append(("sin team_id", m["home"], m["away"]))
            continue
        row = conn.execute(
            "SELECT id, played, score_home, score_away FROM wc_matches "
            "WHERE home_team_id=? AND away_team_id=? AND stage='group'",
            (hid, aid)).fetchone()
        if not row:
            problems.append(("sin fila", m["home"], m["away"]))
            continue
        mid, played, sh, sa = row
        if played == 1 and sh == hs and sa == as_:
            already += 1
            continue
        if not dry_run:
            conn.execute(
                "UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
                (hs, as_, mid))
        updated += 1

    if not dry_run:
        conn.commit()

    played_total = conn.execute(
        "SELECT COUNT(*) FROM wc_matches WHERE stage='group' AND played=1").fetchone()[0]
    conn.close()

    if verbose:
        tag = "[DRY-RUN] " if dry_run else ""
        print(f"{tag}Resultados sincronizados: {updated} actualizados, "
              f"{already} ya correctos, {len(problems)} problemas.")
        for p in problems:
            print("   ", p)
        print(f"{tag}wc_matches stage=group played=1: {played_total}/72")
    return {"updated": updated, "already": already, "problems": problems}


if __name__ == "__main__":
    sync(dry_run="--dry-run" in sys.argv)
