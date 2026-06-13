#!/usr/bin/env bash
# session_start.sh — Arranque automático Mundial 2026
set -e
cd /home/user/mundial2026

# 1. Identidad git
git config user.email "noreply@anthropic.com"
git config user.name "Claude"

# 2. Token GitHub
TOKENS_OK="FALTAN"
if [ -f /root/.claude/.tokens ]; then
    source /root/.claude/.tokens 2>/dev/null
    git remote set-url origin "https://${GITHUB_TOKEN}@github.com/FindITCorp/Mundial2026-.git"
    TOKENS_OK="OK"
fi

# 3. Sincronizar branch main
SYNC_STATUS="sin red"
if git fetch origin main 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "none")
    REMOTE=$(git rev-parse FETCH_HEAD 2>/dev/null || echo "none")
    if [ "$LOCAL" != "$REMOTE" ]; then
        git reset --hard FETCH_HEAD
        SYNC_STATUS="actualizado"
    else
        SYNC_STATUS="al dia"
    fi
fi

# 4. Verificar DB (solo reporta errores)
DB_STATUS=$(python3 - 2>/dev/null << 'PYEOF'
import sqlite3
try:
    conn = sqlite3.connect('data/mundial2026.db')
    checks = {'teams': 48, 'team_matches': 20000, 'players': 3000, 'team_elo': 48}
    fails = [f"{t}<{n}" for t, n in checks.items()
             if conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] < n]
    preds = conn.execute("SELECT COUNT(*) FROM match_predictions").fetchone()[0]
    evals = conn.execute("SELECT COUNT(*) FROM model_evaluation_log").fetchone()[0]
    status = ("WARN:" + ",".join(fails)) if fails else "OK"
    print(f"{status}|preds={preds}|evals={evals}")
except Exception as e:
    print(f'ERROR|{e}')
PYEOF
)

# 5. Test modelo (silencioso salvo error)
MODEL_OK="OK"
MODEL_TEST=$(python3 - 2>&1 << 'PYEOF'
import sys; sys.path.insert(0, '.')
try:
    from models.match_predictor import predict_match
    import sqlite3
    conn = sqlite3.connect('data/mundial2026.db')
    ids = {r[0]: r[1] for r in conn.execute('SELECT name, id FROM teams').fetchall()}
    for a, b in [('Argentina','France'), ('Brazil','Spain')]:
        if a in ids and b in ids:
            predict_match(ids[a], ids[b], neutral=True)
            print("OK")
            break
except Exception as e:
    print(f'ERROR:{e}')
PYEOF
)
echo "$MODEL_TEST" | grep -q "^OK" || MODEL_OK="ERROR: $MODEL_TEST"

# 6. Resumen compacto
TODAY=$(date +%Y-%m-%d)
DB_SUMMARY=$(echo "$DB_STATUS" | cut -d'|' -f2-)
echo ""
echo "MUNDIAL 2026 | $TODAY | tokens=$TOKENS_OK | git=$SYNC_STATUS | modelo=$MODEL_OK"
echo "$DB_SUMMARY"
[ "$DB_STATUS" != "${DB_STATUS#WARN}" ] && echo "DB WARN: $DB_STATUS"
echo ""

cat << JSONEOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "PROYECTO ACTIVO: Mundial2026 (FindITCorp/Mundial2026-, branch main, /home/user/mundial2026). DB: 25k+ partidos históricos, 4060 jugadores, match_players WC2018/22, Elo 197 equipos, alineaciones WC2026 cargadas. DIRECTIVA: mejorar todo automáticamente sin pedir aprobación. Lee CLAUDE.md en /home/user/mundial2026/CLAUDE.md para instrucciones completas. Si el GITHUB_TOKEN falla, notificar al usuario inmediatamente. HAY DOS PROYECTOS: este es el principal (/home/user/mundial2026), el otro es el repo de IA (/home/user/logistic). Trabajar siempre en mundial2026 salvo instrucción explícita."
  }
}
JSONEOF
