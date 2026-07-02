#!/usr/bin/env bash
# sofascore_blitz.sh — UNA SOLA PASADA contra Sofascore antes del bloqueo (02-jul).
# El dueño da acceso a una red nueva que SE VA A BLOQUEAR: este script baja TODO
# lo pendiente en orden de VALOR (si el bloqueo corta a la mitad, lo crítico ya
# entró) y luego parsea/reconstruye todo offline (el parseo no toca la red).
#
# Orden de valor:
#   TIER 1 (sin xG — el modelo los necesita): Spain-Austria, Belgium-Senegal,
#     USA-Bosnia, Mexico-Ecuador, England-Congo, France-Sweden, CIV-Norway
#   TIER 2 (con xG pero sin player-stats/formaciones): SAf-Canada, Brazil-Japan,
#     Germany-Paraguay, Netherlands-Morocco
#
# Uso:  bash scripts/sofascore_blitz.sh
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8

URLS=(
  # TIER 1 — sin xG
  "https://www.sofascore.com/football/match/spain-austria/YTbstUb#id:12813004"
  "https://www.sofascore.com/football/match/belgium-senegal/rUbsOUb#id:12813013"
  "https://www.sofascore.com/football/match/usa-bosnia-and-herzegovina/EObszUb#id:12812992"
  "https://www.sofascore.com/football/match/mexico-ecuador/hVbsGVb#id:12813001"
  "https://www.sofascore.com/football/match/england-dr-congo/nUbsyWb#id:12813020"
  "https://www.sofascore.com/football/match/france-sweden/GObsNTb#id:12812995"
  "https://www.sofascore.com/football/match/cote-divoire-norway/AObstVb#id:12812989"
  # TIER 2 — sin player stats
  "https://www.sofascore.com/football/match/south-africa-canada/LUbscVb#id:12813000"
  "https://www.sofascore.com/football/match/brazil-japan/YUbsvVb#id:12813012"
  "https://www.sofascore.com/football/match/germany-paraguay/lUbsOVb#id:12813014"
  "https://www.sofascore.com/football/match/netherlands-morocco/fUbsDVb#id:12812998"
)
IDS=(12813004 12813013 12812992 12813001 12813020 12812995 12812989 12813000 12813012 12813014 12812998)

echo "=== FASE 1 (RED): fetch de ${#URLS[@]} partidos en UNA sesión Playwright ==="
python scripts/fetch_sofascore_pw.py "${URLS[@]}"

echo ""
echo "=== FASE 1b (RED, si sigue viva): URLs de los partidos que vienen (03/04-jul) ==="
python scripts/discover_sofascore_urls.py 2026-07-03 2026-07-04 2>&1 | tail -2

echo ""
echo "=== FASE 2 (OFFLINE): parseo — ya sin tocar la red ==="
echo "--- team stats (fill-only, no pisa FIFA) ---"
python scripts/parse_sofascore_raw.py "${IDS[@]}" --fill-only
echo "--- player stats ---"
python scripts/parse_sofascore_players.py "${IDS[@]}"
echo "--- formaciones (rebuild de toda la tabla desde el crudo) ---"
python scripts/formation_matchup.py --rebuild 2>&1 | head -2

echo ""
echo "=== FASE 3 (OFFLINE): derivados + validación ==="
python scripts/refresh_team_avgs.py 2>&1 | tail -1
python scripts/validate_predictions.py --all 2>&1 | tail -1

echo ""
echo "=== COBERTURA FINAL ==="
python - << 'PYEOF'
import sqlite3
conn = sqlite3.connect("data/mundial2026.db")
rows = conn.execute("""SELECT w.id, w.home_team_name || ' vs ' || w.away_team_name,
  (SELECT COUNT(*) FROM match_team_stats m WHERE m.match_id=w.id AND m.xg IS NOT NULL)
  FROM wc_matches w WHERE w.stage='R32' AND w.played=1 ORDER BY w.id""").fetchall()
ok = sum(1 for r in rows if r[2] > 0)
for r in rows:
    print(f"  {'xG OK ' if r[2] else 'SIN xG'}  {r[1]}")
print(f"Cobertura xG R32: {ok}/{len(rows)}")
print(conn.execute("PRAGMA integrity_check").fetchone())
PYEOF

echo ""
echo "BLITZ COMPLETO. Revisar arriba: si algún TIER 1 quedó 'sin datos', reintentar SOLO esos."
