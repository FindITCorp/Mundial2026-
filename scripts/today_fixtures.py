"""today_fixtures.py — Lista los partidos de HOY (o fecha dada) donde participa al
menos un equipo del WC2026 y los vuelca a data/lineups/today_fixtures.json.

No filtra por 'finished': incluye programados para poder PREDECIR antes del pitido.
Solo corre desde GitHub Actions (RapidAPI bloqueado localmente).

Uso: python scripts/today_fixtures.py [YYYYMMDD]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from pipelines import smartapi  # noqa: E402
from scripts.predict_today import _is_senior  # noqa: E402

OUT = BASE_DIR / "data" / "lineups" / "today_fixtures.json"


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().strftime("%Y%m%d")
    conn = sqlite3.connect(BASE_DIR / "data" / "mundial2026.db")
    wc = set(r[0].lower() for r in conn.execute("SELECT name FROM teams").fetchall())
    conn.close()

    matches = smartapi.matches_by_date(date, fresh=True)
    out = []
    for m in matches:
        h = (m.get("home", {}) or {}).get("name", "")
        a = (m.get("away", {}) or {}).get("name", "")
        if not (_is_senior(h) and _is_senior(a)):
            continue
        if h.lower() in wc or a.lower() in wc:
            st = m.get("status", {})
            out.append({
                "event_id": m.get("id"),
                "home": h,
                "away": a,
                "home_wc": h.lower() in wc,
                "away_wc": a.lower() in wc,
                "time": (st.get("utcTime") if isinstance(st, dict) else None) or m.get("time"),
                "started": (st.get("started") if isinstance(st, dict) else None),
                "finished": (st.get("finished") if isinstance(st, dict) else None),
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"date": date, "count": len(out), "matches": out},
                              ensure_ascii=False, indent=2))
    print(f"{len(out)} partidos WC el {date} → {OUT}")
    for o in out:
        print(f"  [{o['event_id']}] {o['home']} vs {o['away']}  ({o['time']})")


if __name__ == "__main__":
    main()
