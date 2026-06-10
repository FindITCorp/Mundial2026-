#!/usr/bin/env bash
# session_start.sh — Arranque automático Mundial 2026
set -e
cd /home/user/mundial2026

echo "════════════════════════════════════════════════"
echo "  MUNDIAL 2026 — Iniciando sesión"
echo "════════════════════════════════════════════════"

# 1. Identidad git
git config user.email "noreply@anthropic.com"
git config user.name "Claude"
echo "✅ Git identity: noreply@anthropic.com"

# 2. Token GitHub
if [ -f /root/.claude/.tokens ]; then
    source /root/.claude/.tokens 2>/dev/null
    git remote set-url origin "https://${GITHUB_TOKEN}@github.com/FindITCorp/Mundial2026-.git"
    echo "✅ GitHub token cargado (FindITCorp/Mundial2026-)"
else
    echo "⚠️  ALERTA: /root/.claude/.tokens no encontrado — notificar al usuario"
fi

# 3. Sincronizar branch main
if git fetch origin main 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "none")
    REMOTE=$(git rev-parse FETCH_HEAD 2>/dev/null || echo "none")
    if [ "$LOCAL" != "$REMOTE" ]; then
        git reset --hard FETCH_HEAD
        echo "✅ Branch main sincronizado (actualizado)"
    else
        echo "✅ Branch main al día"
    fi
else
    echo "⚠️  No se pudo sincronizar (token expirado o sin red)"
fi

# 4. Verificar DB
DB_STATUS=$(python3 - << 'PYEOF'
import sqlite3, sys
try:
    conn = sqlite3.connect('data/mundial2026.db')
    checks = {
        'teams': 48, 'team_matches': 20000, 'match_players': 3000,
        'players': 3000, 'team_elo': 48, 'wc26_squad': 100,
        'player_nat_stats': 20000,
    }
    msgs, ok = [], True
    for t, min_n in checks.items():
        n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        flag = '✅' if n >= min_n else '❌'
        if n < min_n: ok = False
        msgs.append(f'{flag}{t}={n}')
    # Partidos WC reales cargados
    wc = conn.execute("SELECT COUNT(*) FROM match_events").fetchone()[0]
    msgs.append(f'match_events={wc}')
    print(('OK' if ok else 'WARN') + '|' + '|'.join(msgs))
except Exception as e:
    print(f'ERROR|{e}')
PYEOF
)

if echo "$DB_STATUS" | grep -q "^OK"; then
    echo "✅ DB íntegra"
    echo "$DB_STATUS" | tr '|' '\n' | tail -n +2 | tr '\n' ' ' | sed 's/^/   /'
    echo
elif echo "$DB_STATUS" | grep -q "^WARN"; then
    echo "⚠️  DB: tablas por debajo del mínimo"
    echo "$DB_STATUS" | tr '|' '\n' | grep "❌" | sed 's/^/   /'
else
    echo "❌ DB ERROR: $DB_STATUS"
fi

# 5. Test del modelo
MODEL_TEST=$(python3 - 2>&1 << 'PYEOF'
import sys; sys.path.insert(0, '.')
try:
    from models.match_predictor import predict_match
    import sqlite3
    conn = sqlite3.connect('data/mundial2026.db')
    ids = {r[0]: r[1] for r in conn.execute('SELECT name, id FROM teams').fetchall()}
    for pair in [('Argentina','France'), ('Brazil','Spain'), ('Argentina','Brazil')]:
        if pair[0] in ids and pair[1] in ids:
            r = predict_match(ids[pair[0]], ids[pair[1]], neutral=True)
            print(f"OK:{pair[0]} vs {pair[1]} → {r['predicted_score']} ({r['prob_home_win']}%/{r['prob_draw']}%/{r['prob_away_win']}%)")
            break
except Exception as e:
    print(f'ERROR:{e}')
PYEOF
)
if echo "$MODEL_TEST" | grep -q "^OK:"; then
    echo "✅ Modelo OK — $(echo $MODEL_TEST | cut -d: -f2-)"
else
    echo "❌ Modelo ERROR: $MODEL_TEST"
fi

# 6. Resumen estado torneo
TODAY=$(date +%Y-%m-%d)
WC_STATUS=$(python3 - 2>/dev/null << 'PYEOF'
import sqlite3
conn = sqlite3.connect('data/mundial2026.db')
played = conn.execute("SELECT COUNT(*) FROM match_events WHERE match_date IS NOT NULL").fetchone()[0]
lineups = conn.execute("SELECT COUNT(*) FROM match_lineups").fetchone()[0]
print(f"Partidos WC cargados: {played} | Alineaciones: {lineups}")
PYEOF
)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📅 $TODAY | Proyecto: FindITCorp/Mundial2026-"
echo "  $WC_STATUS"
echo "  Lee CLAUDE.md para instrucciones completas"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cat << JSONEOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "PROYECTO ACTIVO: Mundial2026 (FindITCorp/Mundial2026-, branch main, /home/user/mundial2026). DB: 25k+ partidos históricos, 4060 jugadores, match_players WC2018/22, Elo 197 equipos, alineaciones WC2026 cargadas. DIRECTIVA: mejorar todo automáticamente sin pedir aprobación. Lee CLAUDE.md en /home/user/mundial2026/CLAUDE.md para instrucciones completas. Si el GITHUB_TOKEN falla, notificar al usuario inmediatamente. HAY DOS PROYECTOS: este es el principal (/home/user/mundial2026), el otro es el repo de IA (/home/user/logistic). Trabajar siempre en mundial2026 salvo instrucción explícita."
  }
}
JSONEOF
