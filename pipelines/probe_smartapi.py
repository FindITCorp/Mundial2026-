"""
probe_smartapi.py — Sonda de descubrimiento para "Free API Live Football Data"
(RapidAPI, provider Creativesdev, host free-api-live-football-data.p.rapidapi.com).

No conocemos los endpoints exactos, así que probamos una lista de candidatos,
registramos status + claves de respuesta + una muestra, y escribimos un reporte
commiteado (data/lineups/smartapi_probe.json) para inspeccionar el formato real.

Corre SOLO desde GitHub Actions (RapidAPI bloqueado localmente).

Uso:
  python pipelines/probe_smartapi.py
  python pipelines/probe_smartapi.py --date 20260604
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

HOST = "free-api-live-football-data.p.rapidapi.com"


def _clean_key(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if "\n" not in raw and " " not in raw and "=" not in raw:
        return raw
    m = re.search(r"[0-9a-zA-Z]+msh[0-9a-zA-Z]+jsn[0-9a-zA-Z]+", raw)
    return m.group(0) if m else raw


def _probe(path: str, params: dict | None = None) -> dict:
    import requests
    key = _clean_key(os.getenv("APIFOOT", ""))
    if not key:
        return {"path": path, "error": "APIFOOT no configurado"}
    url = f"https://{HOST}{path}"
    headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
    out = {"path": path, "params": params or {}}
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=20)
        out["status"] = r.status_code
        try:
            data = r.json()
            # Resumir estructura
            if isinstance(data, dict):
                out["top_keys"] = list(data.keys())[:20]
                # buscar la lista de resultados
                body = data.get("response", data.get("data", data))
                if isinstance(body, list):
                    out["list_len"] = len(body)
                    out["first_item"] = body[0] if body else None
                elif isinstance(body, dict):
                    out["body_keys"] = list(body.keys())[:25]
                    out["body_sample"] = {k: body[k] for k in list(body.keys())[:6]}
            elif isinstance(data, list):
                out["list_len"] = len(data)
                out["first_item"] = data[0] if data else None
        except Exception:
            out["raw_text"] = r.text[:400]
    except Exception as e:
        out["error"] = str(e)[:200]
    time.sleep(1.2)
    return out


# Candidatos de endpoints (basados en convención Creativesdev / FotMob)
def candidate_calls(date_str: str) -> list:
    return [
        ("/football-current-live", None),
        ("/football-get-matches-by-date", {"date": date_str}),
        ("/football-get-all-matches-by-date", {"date": date_str}),
        ("/football-get-list-detail-matches-by-date", {"date": date_str}),
        ("/football-get-match-detail", {"eventid": "0"}),
        ("/football-get-match-info", {"eventid": "0"}),
        ("/football-get-lineups", {"eventid": "0"}),
        ("/football-get-match-lineups", {"eventid": "0"}),
        ("/football-get-team-detail", {"teamid": "8633"}),  # Real Madrid en FotMob
        ("/football-get-team-info", {"teamid": "8633"}),
        ("/football-league-detail", {"leagueid": "47"}),
        ("/football-get-standing-all", {"leagueid": "47"}),
        ("/football-players-search", {"search": "Mbappe"}),
        ("/football-players-detail", {"playerid": "0"}),
        ("/football-leagues", None),
        ("/football-get-all-leagues", None),
    ]


def _extract_match_id(date_str: str) -> str | None:
    """Obtiene un eventid real de los partidos de la fecha dada."""
    res = _probe("/football-get-matches-by-date", {"date": date_str})
    sample = res.get("body_sample") or {}
    matches = sample.get("matches") or []
    if matches:
        return str(matches[0].get("id"))
    return None


def detail_calls(event_id: str) -> list:
    return [
        ("/football-get-match-detail", {"eventid": event_id}),
        ("/football-get-match-info", {"eventid": event_id}),
        ("/football-get-match-lineups", {"eventid": event_id}),
        ("/football-get-lineups", {"eventid": event_id}),
        ("/football-get-match-all-stats", {"eventid": event_id}),
        ("/football-get-match-stats", {"eventid": event_id}),
        ("/football-get-match-events", {"eventid": event_id}),
        ("/football-get-match-shotmap", {"eventid": event_id}),
        ("/football-get-match-player-stats", {"eventid": event_id}),
        ("/football-get-match-h2h", {"eventid": event_id}),
    ]


def run(date_str: str) -> None:
    report = {
        "ran_at": datetime.utcnow().isoformat(),
        "host": HOST,
        "key_present": bool(os.getenv("APIFOOT")),
        "probes": [],
    }
    for path, params in candidate_calls(date_str):
        print(f"  Probing {path} {params or ''}")
        res = _probe(path, params)
        print(f"    → status={res.get('status')} keys={res.get('top_keys') or res.get('error')}")
        report["probes"].append(res)

    # Fase 2: con un eventid real, probar endpoints de detalle/lineups/eventos
    event_id = _extract_match_id(date_str)
    report["event_id_used"] = event_id
    print(f"\n  event_id real: {event_id}")
    if event_id:
        for path, params in detail_calls(event_id):
            print(f"  Probing {path} {params}")
            res = _probe(path, params)
            print(f"    → status={res.get('status')} keys={res.get('top_keys') or res.get('error')}")
            report["probes"].append(res)

    out_dir = BASE_DIR / "data" / "lineups"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "smartapi_probe.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Reporte → data/lineups/smartapi_probe.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.utcnow().strftime("%Y%m%d"))
    args = parser.parse_args()
    run(args.date)
