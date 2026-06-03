#!/bin/bash
# daily_pipeline.sh — Ejecutar después de que terminen los partidos del día
#
# Uso:
#   ./scripts/daily_pipeline.sh                 # procesa ayer
#   ./scripts/daily_pipeline.sh 2026-06-03      # fecha específica
#   ./scripts/daily_pipeline.sh --dry-run        # sin guardar
#
# Para automatizar (cron): correr a las 02:00 AM cada día
#   0 2 * * * cd /home/user/mundial2026 && ./scripts/daily_pipeline.sh >> logs/daily.log 2>&1

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATE_ARG="${1:-}"
DRY_FLAG=""

if [[ "$DATE_ARG" == "--dry-run" ]]; then
    DRY_FLAG="--dry-run"
    DATE_ARG=""
fi

echo "============================================================"
echo " FINDIT WC2026 — Daily Results Pipeline"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# 1. Cargar .env si existe
if [ -f "$ROOT/.env" ]; then
    export $(grep -v '^#' "$ROOT/.env" | xargs)
    echo "✅ .env cargado"
fi

# 2. Verificar API key
if [ -z "$FOOTBALL_DATA_API_KEY" ]; then
    echo "⚠️  FOOTBALL_DATA_API_KEY no configurado"
    echo "   Obtén tu key gratis en: https://www.football-data.org/client/register"
    echo "   Luego agrega al .env: FOOTBALL_DATA_API_KEY=tu_key_aqui"
    echo ""
    echo "   Mientras tanto, usa el modo manual:"
    echo "   python scripts/fetch_daily_results.py --manual"
    exit 1
fi

# 3. Descargar y registrar resultados
echo ""
echo "📥 Paso 1/2: Descargando resultados..."
if [ -n "$DATE_ARG" ]; then
    python scripts/fetch_daily_results.py "$DATE_ARG" $DRY_FLAG
else
    python scripts/fetch_daily_results.py $DRY_FLAG
fi

# 4. Recalibrar si tenemos suficientes partidos nuevos (semanal)
# Solo recalibra los lunes para no oversofittear con una muestra pequeña
DAY_OF_WEEK=$(date '+%u')  # 1=Lunes
if [ "$DAY_OF_WEEK" == "1" ] && [ -z "$DRY_FLAG" ]; then
    echo ""
    echo "📊 Paso 2/2: Recalibración semanal (lunes)..."
    python scripts/weekly_calibration.py 2>/dev/null || echo "  ℹ️  Calibración omitida (script no disponible aún)"
else
    echo ""
    echo "⏭️  Paso 2/2: Calibración omitida (solo lunes)"
fi

echo ""
echo "============================================================"
echo " Pipeline completado — $(date '+%H:%M:%S')"
echo "============================================================"
