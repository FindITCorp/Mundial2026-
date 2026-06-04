"""predict_pair.py — Predice parejas explícitas (TeamA|TeamB por línea) con el
simulador Poisson, sin importar el estado del partido. Para evaluar en vivo.

Lee parejas de data/lineups/predict_pairs.txt y escribe data/lineups/pair_predictions.json.
Corre en el runner (no requiere API; usa datos ya en la DB).
Uso: python scripts/predict_pair.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"
PAIRS = BASE_DIR / "data" / "lineups" / "predict_pairs.txt"
OUT = BASE_DIR / "data" / "lineups" / "pair_predictions.json"

from models.predictor import TeamSnapshot, load_team, load_recent_form  # noqa: E402
from models.simulator import simulate_match  # noqa: E402


def _snapshot(name: str) -> TeamSnapshot:
    team = load_team(name, db_path=DB) or {}
    form = load_recent_form(name, last_n=10, db_path=DB)
    return TeamSnapshot(
        name=name,
        recent_form=form,
        ranking_fifa=team.get("fifa_ranking", 50),
        goals_scored_avg=team.get("goals_scored_avg", 1.5),
        goals_conceded_avg=team.get("goals_conceded_avg", 1.2),
        possession_avg=team.get("possession_avg", 50.0),
    )


def main():
    report = {"generated_at": datetime.utcnow().isoformat(), "predictions": [], "errors": []}
    if not PAIRS.exists():
        report["errors"].append("no predict_pairs.txt")
    else:
        for line in PAIRS.read_text().splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            home, away = [x.strip() for x in line.split("|", 1)]
            try:
                res = simulate_match(_snapshot(home), _snapshot(away), n=10000, db_path=DB)
                report["predictions"].append({
                    "home": home, "away": away,
                    "scoreline": res.get("most_likely_scoreline"),
                    "p_home": res.get("home_wins_pct"),
                    "p_draw": res.get("draws_pct"),
                    "p_away": res.get("away_wins_pct"),
                    "xg_home": res.get("xg_home"),
                    "xg_away": res.get("xg_away"),
                    "top_scorelines": res.get("top_scorelines"),
                })
                print(f"OK {home} vs {away}: {res.get('most_likely_scoreline')}")
            except Exception as e:
                report["errors"].append(f"{home} vs {away}: {e} | {traceback.format_exc()[:300]}")
                print(f"ERR {home} vs {away}: {e}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"{len(report['predictions'])} predicciones → {OUT}")


if __name__ == "__main__":
    main()
