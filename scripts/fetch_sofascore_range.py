"""
fetch_sofascore_range.py — Extrae datos de jugadores de Sofascore para un
rango de fechas. Sin API key. Llama a fetch_sofascore_today.run() por cada día.

Uso:
  python scripts/fetch_sofascore_range.py --from 2026-05-22 --to 2026-06-06
  python scripts/fetch_sofascore_range.py --dates 2026-05-31,2026-06-01,2026-06-04
"""
import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.fetch_sofascore_today import run as sofascore_run


def date_range(start: str, end: str):
    d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while d <= end_d:
        yield d.isoformat()
        d += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default=None, help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--to",   dest="to_date",   default=None, help="Fecha fin YYYY-MM-DD")
    parser.add_argument("--dates", default=None, help="Fechas separadas por coma: 2026-05-31,2026-06-01")
    args = parser.parse_args()

    if args.dates:
        dates = [d.strip() for d in args.dates.split(",")]
    elif args.from_date and args.to_date:
        dates = list(date_range(args.from_date, args.to_date))
    else:
        # Default: fechas conocidas con amistosos WC mayo-junio 2026
        dates = [
            "2026-05-22",
            "2026-05-30",
            "2026-05-31",
            "2026-06-01",
            "2026-06-02",
            "2026-06-04",
            "2026-06-05",
            "2026-06-06",
        ]
        print(f"Sin argumentos — usando fechas WC mayo-junio: {dates}")

    totals = {"events": 0, "lineups": 0, "player_stats": 0}

    for i, d in enumerate(dates):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(dates)}] Procesando {d}")
        print(f"{'='*60}")
        try:
            result = sofascore_run(target_date=d)
            totals["events"]       += result.get("events_processed", len(result.get("events", [])))
            totals["lineups"]      += sum(e.get("lineups", 0) for e in result.get("events", []))
            totals["player_stats"] += sum(e.get("player_stats", 0) for e in result.get("events", []))
        except Exception as e:
            print(f"  ERROR en {d}: {e}")

        if i < len(dates) - 1:
            time.sleep(2)  # cortesía entre fechas

    print(f"\n{'='*60}")
    print("RESUMEN TOTAL")
    print(f"  Fechas procesadas: {len(dates)}")
    print(f"  Eventos WC:        {totals['events']}")
    print(f"  match_lineups:     +{totals['lineups']}")
    print(f"  player_nat_stats:  +{totals['player_stats']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
