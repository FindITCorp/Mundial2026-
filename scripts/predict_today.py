"""predict_today.py — Para CADA amistoso de hoy con un equipo del WC2026:
baja el fixture vía Smart API y corre el simulador Poisson (10k iteraciones).
Escribe el reporte a data/lineups/today_predictions.json (commiteado por el workflow).

Solo corre desde GitHub Actions (RapidAPI bloqueado localmente).
Uso: python scripts/predict_today.py [YYYYMMDD]
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
OUT = BASE_DIR / "data" / "lineups" / "today_predictions.json"

import re  # noqa: E402

from pipelines import smartapi  # noqa: E402
from pipelines.fetch_smartapi_lineups import _build_team_index, _resolve_team  # noqa: E402
from models.predictor import TeamSnapshot, load_team, load_recent_form  # noqa: E402
from models.simulator import simulate_match  # noqa: E402

# Sufijos que indican selección NO absoluta (juvenil/reserva/femenil) → excluir.
_NOT_SENIOR = re.compile(
    r"\b("
    r"u-?\d{1,2}|"            # U15..U23, U-17
    r"sub-?\d{1,2}|"
    r"under-?\d{1,2}|"
    r"women|femenin|femenil|ladies|girls|"
    r"reserves?|reserva|"
    r"olympic|olimpic|olimpic[oa]|"
    r"amateur|youth|juvenil|academy|"
    r"\bb\b|ii"               # equipos B / II
    r")\b",
    re.IGNORECASE,
)


def _is_senior(name: str) -> bool:
    return not _NOT_SENIOR.search(name or "")


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
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().strftime("%Y%m%d")
    conn = sqlite3.connect(DB)
    team_index = _build_team_index(conn)
    report = {"date": date, "generated_at": datetime.utcnow().isoformat(),
              "predictions": [], "errors": []}

    try:
        matches = smartapi.matches_by_date(date, fresh=True)
    except Exception as e:
        report["errors"].append(f"matches_by_date: {e}")
        matches = []

    print(f"{len(matches)} partidos totales el {date}")
    for m in matches:
        home = (m.get("home") or {}).get("name", "")
        away = (m.get("away") or {}).get("name", "")
        # Solo selecciones ABSOLUTAS: descarta juveniles/reservas/femenil/clubes B.
        if not (_is_senior(home) and _is_senior(away)):
            continue
        # Solo PREDECIR partidos que aún NO empiezan. Los ya iniciados/terminados
        # (la API los lista por timezone aunque se jugaron anoche) NO se predicen:
        # serían "predicciones" de un resultado ya conocido.
        st = m.get("status", {}) if isinstance(m.get("status"), dict) else {}
        if st.get("started") or st.get("finished"):
            continue
        htid = _resolve_team(team_index, home)
        atid = _resolve_team(team_index, away)
        if not (htid or atid):
            continue  # ningun equipo WC
        # nombre canonico en nuestra DB
        def canon(tid, fallback):
            if not tid:
                return fallback
            r = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()
            return r[0] if r else fallback
        hname = canon(htid, home)
        aname = canon(atid, away)
        try:
            res = simulate_match(_snapshot(hname), _snapshot(aname), n=10000, db_path=DB)
            report["predictions"].append({
                "event_id": m.get("id"),
                "home": hname, "away": aname,
                "home_wc": bool(htid), "away_wc": bool(atid),
                "scoreline": res.get("most_likely_scoreline"),
                "p_home": res.get("home_wins_pct"),
                "p_draw": res.get("draws_pct"),
                "p_away": res.get("away_wins_pct"),
                "xg_home": res.get("xg_home"),
                "xg_away": res.get("xg_away"),
            })
            print(f"  OK {hname} vs {aname}: {res.get('most_likely_scoreline')}")
        except Exception as e:
            report["errors"].append(f"{hname} vs {aname}: {e} | {traceback.format_exc()[:300]}")
            print(f"  ERR {hname} vs {aname}: {e}")

    conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"{len(report['predictions'])} predicciones → {OUT}")


if __name__ == "__main__":
    main()
