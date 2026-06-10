# MUNDIAL 2026 — PROYECTO PRINCIPAL
# INSTRUCCIONES OBLIGATORIAS PARA CADA NUEVA SESION

> **ESTE ES EL PROYECTO PRINCIPAL. El otro proyecto en /home/user/logistic
> es el repo de investigación/IA — trabajar aquí salvo instrucción explícita.**

---

## PROTOCOLO DE ARRANQUE — SE EJECUTA AUTOMATICAMENTE

El hook SessionStart ya corre `.claude/session_start.sh` al iniciar.
Si algo falla, ejecutar manualmente:

```bash
bash /home/user/mundial2026/.claude/session_start.sh
```

O paso a paso:
```bash
# 1. Identidad git
git config user.email "noreply@anthropic.com"
git config user.name "Claude"

# 2. Token y remote
source /root/.claude/.tokens 2>/dev/null
git remote set-url origin https://${GITHUB_TOKEN}@github.com/FindITCorp/Mundial2026-.git

# 3. Sincronizar
git fetch origin main && git reset --hard origin/main

# 4. Verificar DB
cd /home/user/mundial2026
python3 -c "
import sqlite3; conn=sqlite3.connect('data/mundial2026.db')
for t in ['teams','team_matches','match_players','wc26_squad','match_events']:
    print(t, conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
"

# 5. Test modelo
python3 -c "
import sys; sys.path.insert(0,'.')
from models.match_predictor import predict_match
import sqlite3
conn = sqlite3.connect('data/mundial2026.db')
ids = {r[0]:r[1] for r in conn.execute('SELECT name,id FROM teams').fetchall()}
r = predict_match(ids['Argentina'], ids['France'], neutral=True)
print(f'Test OK: {r[\"predicted_score\"]} ({r[\"prob_home_win\"]}%/{r[\"prob_draw\"]}%/{r[\"prob_away_win\"]}%)')
"
```

---

## DIRECTIVA DE MEJORA AUTOMATICA

**Mejorar SIN pedir aprobación:**
- Integrar resultados de partidos cuando el usuario los proporcione
- Recalibrar BASE_GOALS y parámetros tras cada 10+ partidos WC nuevos
- Corregir bugs detectados en cualquier módulo
- Actualizar este CLAUDE.md tras cada cambio importante
- Commit + push a `main` de cada mejora

**Pedir aprobación SOLO para:**
- Cambiar arquitectura del modelo (reemplazar Poisson)
- Eliminar tablas de la DB
- Cambiar nombres de repo o branch

---

## REPOSITORIO Y ACCESO

| Parámetro | Valor |
|-----------|-------|
| **GitHub repo** | `FindITCorp/Mundial2026-` (con guion al final) |
| **Branch** | `main` |
| **Ruta local** | `/home/user/mundial2026` |
| **DB local** | `/home/user/mundial2026/data/mundial2026.db` |
| **Token GitHub** | En `/root/.claude/.tokens` como `$GITHUB_TOKEN` |

> **⚠️ Si GITHUB_TOKEN da 401/403: notificar al usuario inmediatamente.**

### Git — siempre así:
```bash
git config user.email "noreply@anthropic.com"
git config user.name "Claude"
git -c commit.gpgsign=false commit -m "mensaje"
git push origin main
```

---

## CLAVES DE API

| Clave | Dónde | Estado |
|-------|-------|--------|
| `GITHUB_TOKEN` | `/root/.claude/.tokens` | ✅ Activa (puede expirar) |
| `FOOTBALL_DATA_KEY` | GitHub Secret | ✅ [en GitHub Secrets] |
| `APIFOOT` | GitHub Secret | ✅ RapidAPI (100 req/día) |
| `APISPORTS_KEY` | GitHub Secret | ✅ [en GitHub Secrets] |

> APIs externas (Sofascore, Opta, ESPN) **bloqueadas por política de red**.
> Solo funcionan las 3 de arriba, y solo via GitHub Actions.

---

## BASE DE DATOS — ESTADO (10 junio 2026)

**Archivo:** `/home/user/mundial2026/data/mundial2026.db`

| Tabla | Filas | Descripción |
|-------|-------|-------------|
| `teams` | 197 | Todos los equipos (48 WC2026 + históricos) |
| `team_matches` | 24,795 | Historial resultados (DEDUPED 10-jun: -406 filas dobles ±1 día) |
| `team_elo` | 197 | Ratings Elo dinámicos |
| `team_tactics` | 61 | Formación, pressing, build_up_style |
| `players` | 4,075 | Jugadores; name, position, club, caps, goals_as_nat |
| `squad_selections` | 3,341 | Plantillas confirmadas |
| `wc26_squad` | 1,602 | Plantilla oficial WC2026 |
| `projected_lineups` | 1,602 | XI titular proyectado |
| `player_club_stats` | 1,364 | Stats 2024/25 en clubs |
| `player_nat_stats` | 23,743 | Stats selección + StatsBomb WC2018/22 |
| `player_ratings` | 1,778 | Ratings 1-10 calculados |
| `match_players` | 3,476 | Por jugador por partido (WC2018+WC2022) |
| `match_events` | 218 | ★ Eventos/resultados partidos WC2026 reales |
| `match_team_stats` | 104 | Stats equipo por partido WC2026 |
| `match_predictions` | 89 | Predicciones del modelo (v1.2-veteran, con nombres sellados) |
| `match_lineups` | 1,709 | ★ Alineaciones confirmadas WC2026 |
| `wc_matches` | 147 | Calendario WC2026 (72 grupos reales + amistosos; deduped 10-jun) |
| `wc_group_draw` | 48 | ★ NUEVO 10-jun: grupos REALES derivados de wc_matches (`scripts/sync_wc_group_draw.py`) — lo necesita tournament.py |
| `model_evaluation_log` | 65 | Evaluaciones del modelo (limpio de duplicados) |
| `model_bias` | 12 | Sesgos aprendidos (λ_scale 0.9005 @ 10-jun, post-veterano) |
| `team_goal_timing` | 215 | Timing de goles (early/late patterns) |
| `team_performance_profile` | 53 | Perfiles de rendimiento por equipo |

---

## ARQUITECTURA DEL MODELO

### Motor Principal: `models/match_predictor.py`

```python
from models.match_predictor import predict_match
r = predict_match(home_id, away_id, neutral=True)
# r["predicted_score"], r["prob_home_win"], r["lambda_home"]
```

**Factores Poisson:**
- Elo diferencial (ancla principal)
- xG blended: 40% club + 60% forma avg_gf
- Forma reciente ponderada (últimos 10 partidos)
- Rating XI titular (player_ratings + projected_lineups)
- Set pieces & corners efficiency
- Posesión/pressing matchup
- Dixon-Coles HAS/HDS/AAS/ADS
- ★ **Experiencia mundialista** (PORTADO 10-jun desde logistic): `models/veteran_experience.py`,
  ±4.5% λ, STAGE_SENSITIVITY group=0.05/knockout=0.11, pressure-vs-elite adjustment,
  shootout edge ±2.5pp en penales (tournament.py). Params: `stage="group"|"knockout"`,
  `use_veteran=True` (A/B con False)

**Parámetros calibrados:**
- `BASE_GOALS = 1.22`
- Neutral venue para todos los partidos WC
- Draw boost W-5 framework (5 señales)
- model_bias λ_scale 0.9005 (refit 10-jun con veterano activo, 68 partidos)

**Backtest A/B veterano (10-jun, 461 partidos hist.):** neutro en ventana pre-torneo
(acc 66.4→65.9, Brier 0.4647→0.4642) — la señal es de KNOCKOUT/penales, no medible
en retrodict de amistosos. En logistic (491 pj): +0.4pp. Mantener activo y
re-evaluar tras los primeros 10+ partidos del Mundial.
**Evaluación producción (65 pj limpios, 10-jun tarde):** accuracy 63.1%, Brier 0.2869,
λ_scale ×0.900. Tras dedupe de 406 team_matches + 3 fixtures dobles que se contaban 2x.
21.5% de los fallos son empates no predichos (0-0 de amistosos con rotaciones).

### Simulador Torneo: `models/tournament.py` / `simulate.py`
### Simulación 1 partido: `models/full_match_sim.py`
### Análisis experto: `models/expert_analysis.py`

---

## COMANDOS PRINCIPALES

```bash
# Predicción partido
python3 predict.py --home "Argentina" --away "France"
python3 predict.py --home "Argentina" --away "France" --expert

# Simulación completa (goleadores + eventos + árbitro)
python3 simulate.py --match "Brazil" "Argentina"

# Torneo completo Monte Carlo
python3 simulate.py --tournament

# Pipeline de datos
python3 pipelines/full_update.py --scope form      # diario
python3 pipelines/full_update.py --scope wc        # durante torneo
python3 pipelines/full_update.py --scope all       # semanal

# Backtest del modelo
python3 scripts/validate_model.py --days 365

# Sincronizar resultados team_matches → wc_matches (amistosos) y recalibrar
python3 scripts/sync_friendly_results.py            # auto desde team_matches
python3 scripts/sync_friendly_results.py --set 147 2-1   # resultado manual
python3 scripts/evaluate_model.py                   # evalúa + refit model_bias
```

---

## WORKFLOWS GITHUB ACTIONS

| Workflow | Trigger | Scope |
|----------|---------|-------|
| `fetch_data.yml` | Diario 7am UTC + push | Auto-detectado |
| `match_day.yml` | Cada 30min durante partidos | wc |
| `fetch_players.yml` | Lunes 8am UTC | squads |

### Triggear manualmente:
```bash
source /root/.claude/.tokens
curl -X POST "https://api.github.com/repos/FindITCorp/Mundial2026-/actions/workflows/fetch_data.yml/dispatches" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -d '{"ref":"main","inputs":{"scope":"wc"}}'
```

---

## DOS PROYECTOS — DIFERENCIAS

| | `mundial2026` (ESTE) | `logistic` |
|---|---|---|
| **Repo** | `FindITCorp/Mundial2026-` | `FindITCorp/logistic` |
| **Branch** | `main` | `claude/sleepy-bohr-PDVSt` |
| **Ruta** | `/home/user/mundial2026` | `/home/user/logistic` |
| **Propósito** | Proyecto principal de predicción | Repo de desarrollo/IA |
| **DB filas** | 25k+ team_matches, 218 match_events WC | 26k team_matches, sin match_events WC |
| **Diferencial** | ★ match_lineups (1709), model_evaluation, goal_timing | ★ veteran_experience.py, validate_model.py |

> **Mejoras del repo `logistic` deben portarse a `mundial2026` cuando estén validadas.**

---

## ERRORES CONOCIDOS Y SOLUCIONES

| Error | Causa | Solución |
|-------|-------|----------|
| `No module named 'models'` | CWD incorrecto | `cd /home/user/mundial2026` |
| `push rejected non-fast-forward` | Remote adelantado | `git fetch && git reset --hard origin/main` |
| Commits "Unverified" | Falta autor correcto | `git config user.email "noreply@anthropic.com"` |
| APIs externas 403 | Política de red | Solo via GitHub Actions |
| `UNIQUE constraint failed` | Inserción duplicada | Usar `INSERT OR IGNORE` |
| Lote predicciones v1.0 corrupto (09-jun) | Registro ad-hoc con probs invertidas (México 16% vs Sudáfrica 52%!) | CORREGIDO 10-jun: regeneradas las 82 pendientes como v1.2-veteran con nombres sellados; guard de integridad en evaluate_model.py |
| Amistosos sin evaluar | fetch escribe team_matches pero evaluate lee wc_matches | `scripts/sync_friendly_results.py` copia resultados (creado 10-jun) |
| Filas dobles en team_matches | Loaders distintos, fechas ±1 día | Dedupe aplicado 10-jun (-406); criterio: mismo rival+score ±1 día |

---

## ESTADO ACTUAL

**Última actualización:** 10 junio 2026 (noche — víspera del torneo)
**Torneo:** comienza MAÑANA 11 junio 2026 (inaugural: Mexico vs South Africa)

```
✅ DB: 25,201 partidos históricos + 218 eventos WC reales
✅ Alineaciones: 1,709 confirmadas
✅ Elo: 197 equipos
✅ Modelo calibrado (BASE_GOALS=1.22, λ_scale 0.9005 @ 10-jun)
✅ FACTOR VETERANO PORTADO desde logistic e integrado (predictor+torneo+full_sim)
✅ wc_group_draw creada (48 equipos, grupos reales) — tournament.py operativo
✅ scripts/validate_model.py (harness A/B) y scripts/sync_wc_group_draw.py portados/creados
✅ model_evaluation_log: 65 evaluaciones LIMPIAS (dedupe 10-jun) — 63.1% acc, Brier 0.2869
✅ Predicciones amistosos 09-10 jun + 5 de hoy (Pakistán-Afganistán, Austria-Guatemala incl.) registradas v1.2-veteran
✅ Lote corrupto v1.0 del 09-jun detectado y regenerado (México 1-0 60/32/7, antes decía 0-1 16/33/52)
✅ sync_friendly_results.py cierra ciclo: fetch → team_matches → wc_matches → evaluate → recalibrar
✅ team_goal_timing: 215 equipos con patrones de timing
⚠️  player_club_stats: solo 1,364 (parcial, se actualiza via Actions)
⚠️  Backtest A/B veterano neutro en pre-torneo — re-evaluar tras 10+ partidos WC
```

---

## SESIONES WEB (Claude Code on the Web) — LÍMITES VERIFICADOS 10-jun

| Recurso | Estado |
|---------|--------|
| `/root/.claude/.tokens` | ❌ NO existe en contenedores web (no es expiración: no está) |
| Repo de la sesión | Solo el del scope elegido al crearla; este repo fue accesible vía **PAT pegado por el usuario en el chat** |
| Push | `git push https://<PAT>@github.com/FindITCorp/Mundial2026-.git main` (github.com permitido por red; NO persistir el PAT en remotes/archivos) |
| APIs GitHub (api.github.com) | ❌ 403 — workflows solo se disparan desde GitHub Actions o tools MCP de la sesión |
| APIs fútbol | ❌ Bloqueadas local (igual que siempre) — solo via GitHub Actions |

**Para la próxima sesión web:** crear la sesión con `FindITCorp/Mundial2026-` en el
scope para no depender del PAT. Si el PAT se usó en un chat, ROTARLO después.

---

## TAREAS AL INICIAR NUEVA SESION

1. Verificar que el hook corrió sin errores
2. Comprobar si hay partidos WC nuevos desde la última sesión
3. Si hay partidos nuevos → `--scope wc` para actualizar
4. Si el usuario provee datos de partido → cargar y recalibrar
5. Actualizar este CLAUDE.md con cambios relevantes
