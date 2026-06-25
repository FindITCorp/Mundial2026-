"""
matchday.py — Comando ÚNICO: refresca TODOS los datos y analiza los partidos.

Corre, en orden, el pipeline completo antes de cada jornada para que el análisis
nunca use datos parciales:
  1. sync_results_to_db.py   resultados JSON → wc_matches (la DB que lee el modelo)
  2. fetch_fifa.py           alineaciones + goles con minuto (FIFA, todos los partidos)
  3. fetch_fifa_stats.py     142 stats avanzados FDH (paradas, presiones, line-breaks)
  4. sync_stats_to_db.py     stats core de Sofascore (si hay JSON nuevo)
  5. rebuild_wc_timing.py    timing real del Mundial desde los goles reales
  6. refresh_team_avgs.py    reconstruye perfiles cacheados

Luego analiza cada partido (pares de equipos) con analyze_match (choque de ventanas,
portero en racha, conversión, timing real, etc.).

Uso:
    python scripts/matchday.py "Japan" "Sweden" "Tunisia" "Netherlands"
    python scripts/matchday.py                     # solo refresca datos, sin analizar
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

PIPELINE = [
    "sync_results_to_db.py",
    "fetch_fifa.py",
    "fetch_fifa_stats.py",
    "sync_stats_to_db.py",
    "rebuild_wc_timing.py",
    "refresh_team_avgs.py",
]


def _run(script, args=None):
    print(f"\n{'─'*70}\n▶ {script}\n{'─'*70}")
    try:
        r = subprocess.run([PY, str(HERE / script), *(args or [])],
                           capture_output=True, text=True, timeout=600,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        if out:
            print(out[-1500:])
        if r.returncode != 0:
            err = (r.stderr or "").strip()[-500:]
            print(f"  ⚠ terminó con código {r.returncode}: {err}")
            return False
        return True
    except Exception as e:
        print(f"  ⚠ ERROR: {e}")
        return False


def main():
    pairs = sys.argv[1:]
    print("══════════════════════════════════════════════════════════════════")
    print("  MATCHDAY — refresco de datos + análisis")
    print("══════════════════════════════════════════════════════════════════")

    ok = sum(_run(s) for s in PIPELINE)
    print(f"\n✔ Pipeline de datos: {ok}/{len(PIPELINE)} pasos OK")

    if len(pairs) >= 2:
        print("\n══════════════════════════════════════════════════════════════════")
        print("  ANÁLISIS DE PARTIDOS")
        print("══════════════════════════════════════════════════════════════════")
        for i in range(0, len(pairs) - 1, 2):
            _run("analyze_match.py", [pairs[i], pairs[i + 1]])
            _run("predict_adjusted.py", [pairs[i], pairs[i + 1]])
    else:
        print("\n(Sin partidos para analizar — pasa pares de equipos para incluir análisis.)")


if __name__ == "__main__":
    main()
