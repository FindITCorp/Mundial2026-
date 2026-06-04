"""predict_pair.py — Predice parejas explícitas (TeamA|TeamB por línea) con el
MOTOR COMPLETO de 6 factores (Elo + xG + forma + XI + balón parado + pressing),
que pesa la PLANTILLA real (ratings de club + selección) y mide 11 vs 11.

Acepta ausencias/suspensiones opcionales tras la pareja, separadas por ' ;; ':
  Mexico|Serbia ;; home_out=Edson Álvarez:suspension,Raúl Jiménez:injury

Lee data/lineups/predict_pairs.txt y escribe data/lineups/pair_predictions.json.
Corre en el runner (usa datos ya en la DB; no requiere API).
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"
PAIRS = BASE_DIR / "data" / "lineups" / "predict_pairs.txt"
OUT = BASE_DIR / "data" / "lineups" / "pair_predictions.json"

from models.match_predictor import predict_by_name  # noqa: E402


def _parse_events(spec: str) -> list:
    """'Edson Álvarez:suspension,Raúl Jiménez:injury' → [{player,reason}, ...]"""
    out = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            name, reason = chunk.split(":", 1)
        else:
            name, reason = chunk, "injury"
        out.append({"player": name.strip(), "reason": reason.strip()})
    return out


def main():
    report = {"generated_at": datetime.utcnow().isoformat(),
              "engine": "match_predictor.predict_by_name (6 factores, XI 11v11)",
              "predictions": [], "errors": []}

    if not PAIRS.exists():
        report["errors"].append("no predict_pairs.txt")
    else:
        for line in PAIRS.read_text().splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            pair, _, extra = line.partition(";;")
            home, away = [x.strip() for x in pair.split("|", 1)]
            home_events, away_events = [], []
            for tok in extra.split():
                if tok.startswith("home_out="):
                    home_events = _parse_events(tok[len("home_out="):])
                elif tok.startswith("away_out="):
                    away_events = _parse_events(tok[len("away_out="):])
            try:
                r = predict_by_name(home, away, neutral=True,
                                    home_events=home_events or None,
                                    away_events=away_events or None,
                                    db_path=str(DB))
                report["predictions"].append({
                    "home": home, "away": away,
                    "scoreline": r.get("predicted_score"),
                    "winner": r.get("winner"),
                    "p_home": r.get("prob_home_win"),
                    "p_draw": r.get("prob_draw"),
                    "p_away": r.get("prob_away_win"),
                    "lambda_home": r.get("lambda_home"),
                    "lambda_away": r.get("lambda_away"),
                    "xi_home": r.get("xi_home"),
                    "xi_away": r.get("xi_away"),
                    "elo_home": r.get("elo_home"),
                    "elo_away": r.get("elo_away"),
                    "formation_home": r.get("formation_home"),
                    "formation_away": r.get("formation_away"),
                    "possession_home": r.get("possession_home"),
                    "possession_away": r.get("possession_away"),
                    "goleada_band": r.get("goleada_band"),
                    "top_scores": r.get("top_scores"),
                    "home_events": home_events,
                    "away_events": away_events,
                })
                print(f"OK {home} vs {away}: {r.get('predicted_score')} "
                      f"(XI {r.get('xi_home')} vs {r.get('xi_away')})")
            except Exception as e:
                report["errors"].append(f"{home} vs {away}: {e} | {traceback.format_exc()[:400]}")
                print(f"ERR {home} vs {away}: {e}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"{len(report['predictions'])} predicciones → {OUT}")


if __name__ == "__main__":
    main()
