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

## REGLAS DE TRABAJO CON EL DUEÑO (12-jun — OBLIGATORIAS)

1. **LOS DATOS RIGEN TODO. SIN RESTRICCIÓN DE GANADOR.** Si el modelo arroja
   empate, EL EMPATE ES EL RESULTADO OFICIAL. Nunca forzar el marcador a
   coincidir con el ganador más probable ni con ninguna expectativa. El
   marcador oficial y el ganador más probable son dos lecturas independientes
   de los mismos datos y se reportan POR SEPARADO cuando difieren.
2. **Pronóstico oficial = ARGMAX del grid Dixon-Coles** (el marcador con mayor
   probabilidad conjunta, nunca la mediana). Es la guía de alineación
   datos↔realidad. Siempre guardarlo en `pred_scoreline` + `pred_score_prob`.
3. **No cambiar metodología por complacencia.** Cualquier cambio se decide
   por BACKTEST con regla pre-definida, se documenta aquí, y queda fijo
   hasta que otro backtest lo supere. Nunca variar para dar la razón.
4. **No dar resultados/datos de partidos que el dueño no pidió.** Él pide,
   o él carga. Procesar datos en silencio está bien; volcar tablas no pedidas, no.
5. **Acumular, NUNCA sobrescribir.** Todos los loaders insertan-si-no-existe.
   Si el dueño recarga un partido, se salta lo existente. La curva de datos
   solo sube. Borrar solo duplicados exactos verificados.
6. **Horas SIEMPRE en hora Panamá** (la columna `time` de wc_matches está en
   hora Panamá). No confundir con UTC al narrar (error cometido 11-jun).
7. **Alineaciones confirmadas:** cuando el dueño las pegue, aplicar a
   projected_lineups (ids con más datos si hay duplicados), re-correr el
   modelo SOLO de ese partido, re-sellar y reportar el delta y su causa.
8. **Dumps de Sofascore:** el dueño pega texto crudo. Parsear: columnas
   goles/[asistencias]/[entradas]/pases/duelos/suelo/aéreos/min/pos
   (2 números antes de pases = goles,entradas; 3 = goles,asist,entradas).
   Cargar match_player_stats (por nombre+team_id), match_team_stats (37
   campos, xg NULL si no publicado), wc_matches si falta el fixture, espejos
   team_matches, y correr: team_strengths + build_team_performance_profile +
   sync_player_match_ratings + predict_upcoming + commit + push.

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

## BASE DE DATOS — ESTADO (12 junio 2026, día 2 del torneo)

**Archivo:** `/home/user/mundial2026/data/mundial2026.db`

| Tabla | Filas | Descripción |
|-------|-------|-------------|
| `teams` | 197 | Todos los equipos (48 WC2026 + históricos) |
| `team_matches` | 24,758 | Historial resultados (deduped continuo; cleaner idempotente) |
| `team_elo` | 197 | Ratings Elo dinámicos |
| `players` | 4,151 | Jugadores; convocatorias oficiales cargadas (ver abajo) |
| `projected_lineups` | 1,589 | XI titular + 26 convocados por equipo |
| `player_club_stats` | 1,364 | Stats 2024/25 en clubs (parcial, vía Actions) |
| `player_nat_stats` | 23,743 | Stats selección + StatsBomb WC2018/22 |
| `player_ratings` | 2,010 | Ratings por partido 'nat' (agregados last-5 en el factor XI) |
| `match_team_stats` | 168 | Stats equipo por partido (37 campos; 100% enlazadas a wc_matches) |
| `match_player_stats` | 2,317 | Stats por jugador por partido (cargas del dueño, por nombre) |
| `match_predictions` | 145 | Predicciones (v1.5-argmax: argmax grid Dixon-Coles, no mediana) |
| `match_lineups` | 1,709 | Alineaciones confirmadas (api-sports) |
| `wc_matches` | 192 | Calendario OFICIAL 72 grupos (hora Panamá) + amistosos/quals con stats |
| `wc_group_draw` | 48 | Grupos reales A-L — tournament.py operativo |
| `model_evaluation_log` | 74 | Evaluaciones (accuracy 64.9%, Brier 0.2866) |
| `team_strengths` | 336 (42 equipos) | ★ Fortalezas/debilidades 8 ejes (z-scores) |
| `confed_elo_offset` / `team_elo_offset` | 6 / 60 | Offsets inter-confederación (pool y por equipo) |
| `team_performance_profile` | 68 | Perfiles agregados (xG for/against, aéreo, press) |

**Convocatorias oficiales de 26 cargadas:** Chequia, Canadá, Bosnia (relevo
generacional: Dedić/Bajraktarević, fuera Pjanić), Paraguay, Suiza, Marruecos
(bajas Aguerd/Ezzalzouli → Saadane/Sbai; Bounou='Bono'), Brasil (2 Danilos
desambiguados; sin Rodrygo/Militão/Estêvão; Neymar suplente), Haití (sin
Delcroix — verificar si es lesión), Qatar, México (XI confirmado inaugural).

---

## ARQUITECTURA DEL MODELO

### Motor Principal: `models/match_predictor.py`

```python
from models.match_predictor import predict_match
r = predict_match(home_id, away_id, neutral=True)
# r["predicted_score"], r["prob_home_win"], r["lambda_home"], r["top_scores"]
```

**Factores Poisson:**
- Elo diferencial (ancla principal)
- xG blended: 40% club + 60% forma avg_gf + xG real SOS-ajustado (hasta 50%)
- Forma reciente ponderada (últimos 10, SOS por Elo rival)
- Rating XI titular (player_ratings agregado last-5 por jugador + shrink por cobertura)
- Set pieces & corners efficiency
- Posesión/pressing matchup
- Dixon-Coles HAS/HDS/AAS/ADS
- ★ **Experiencia mundialista** (`models/veteran_experience.py`): ±4.5% λ,
  stage group=0.05/knockout=0.11, pressure-vs-elite, shootout edge ±2.5pp.
- ★ **Sesgo de confederación + EQUIPO** (`scripts/fit_confederation_bias.py`):
  tablas `confed_elo_offset` y `team_elo_offset` (blend propio↔pool w=n/(n+30),
  cap ±75). El predictor usa team offset si existe, sino confed. Solo cruces
  inter-confed. Refit automático diario. México -40 propio; CONMEBOL +60 pool.
- ★ **Paquete 4 fixes (11-jun):** xG por rival (opp_elo/1550)^1.5; shrink XI
  por cobertura (sin datos→neutral 1.0, nunca penaliza); localía anfitriones
  (México/USA/Canadá grupos neutral=False); offsets por equipo.
  Backtest: acc 64.4→65.1, Brier 0.4790→0.4772, draw recall 71→75.4.
- ★ **Fortalezas/debilidades + matchup (11-jun)** (`scripts/team_strengths.py`):
  8 ejes (ataque, definición, aéreo, balón parado, pressing, seguridad,
  defensa, portería) desde match_team_stats, SOS-ponderado, denominadores
  por métrica (NULL no diluye), z-scores → `_strengths_matchup()` sube el λ
  del atacante cuando su fortaleza golpea debilidad rival (ataque vs defensa
  = la goleada; aéreo vs aéreo; pressing vs seguridad). Cap ±8%, gate n≥3
  ambos lados, A/B con WC_MATCHUP=0. Backtest: acc +0.3pp, Brier igual.
- ★ **Ratings por partido → factor XI (11-jun)**
  (`scripts/sync_player_match_ratings.py`): los ratings Sofascore que carga
  el dueño en match_player_stats fluyen a player_ratings 'nat' (matching
  multi-clave: acentos/guiones/orden — variantes coreanas). El factor XI
  agrega los últimos 5 ratings por jugador (antes el JOIN explotaba filas).
- ★ **Eficiencia conversión + portería (14-jun)** (`_finishing_gk_factor` en
  match_predictor.py): λ del atacante × (goles/xG propio) × (GA/xGA del GK
  rival). Mide EFICIENCIA (desviación goles↔xG), ortogonal al VOLUMEN que ya
  da el blend xG. Shrinkage w=n/(n+6), cap producto ±10%, gate n≥3 ambos lados,
  neutral sin datos. A/B con WC_FINISHING=0. **Hallazgo que lo motivó** (eval 77
  partidos): el modelo no veía empates bajos (0/17) ni 0-0 (1 pred vs 6 reales)
  porque ignoraba que Egipto convierte 2.03× su xG + GK para a 0.49× (→0-0 vs
  España) o que Escocia GK 0.61× (→0-1 a Haití pese a xG inferior). **Backtest
  (regla pre-fijada: fijar si acc no cae >0.2pp Y Brier mejora):** 955 part.
  acc 64.5→64.7%, Brier 0.4809→0.4806 ✓; set WC 140 part. Brier 0.5206→0.5176,
  log-loss 0.8756→0.8703; en los 58 con cobertura Brier −0.0073 (2.4× más
  fuerte). Accuracy plana (−0.7pp = 1 partido, ruido); gana CALIBRACIÓN. FIJADO.
  Nota: la inflación de λ que se vio en predicciones selladas (λ_tot 2.89, 9%
  low) era de bias OBSOLETO; el modelo vivo con model_bias ya está en λ_tot 2.27
  / 36% low (real 27%) — model_bias auto-corrige el grueso; este factor afina la
  EFICIENCIA por equipo que el promedio global no captura.
- ★ **Jugadores diferenciadores / techo individual (14-jun)** (`scripts/
  load_star_players.py` → tabla `star_players`; `_star_off_factor`/
  `_star_def_factor` en match_predictor.py): lista curada del dueño (100 cracks
  con ranking). rank→tier_weight, posición→eje (FWD/MID = OFF sube λ propio;
  DEF/GK = DEF baja λ rival), × disponibilidad en projected_lineups (titular 1.0,
  suplente 0.4). Rendimientos decrecientes tanh; cap OFF +7% (scale 2.5), DEF
  −5% (scale 1.2). Flag A/B WC_STARS. **Backtest (misma regla pre-fijada):**
  955 part. acc 64.7→64.6% (−0.1pp, dentro de umbral), Brier 0.4806→0.4805 ✓
  → REGLA CUMPLIDA, FIJADO. PERO señal DÉBIL (set WC: Brier 0.5176→0.5165,
  log-loss −0.0018, pero accuracy −0.7pp; cobertura Brier −0.0019, 4× más flojo
  que finishing). Causa: doble-conteo parcial — Elo + factor XI YA capturan que
  los grandes son fuertes. ⚠ El backtest es ANACRÓNICO (XI 2026 sobre partidos
  2024-25) y SUBESTIMA el factor para WC2026 con XI contemporáneo. Re-evaluar con
  resultados WC reales; si daña accuracy → WC_STARS=0. 95/100 matchean directo;
  Georgia (Kvara, Mamardashvili) y Boniface sin plantilla cargada (player_id
  NULL, se activan al cargarla).

- ★ **Sobredispersión de goles / incertidumbre del marcador (14-jun)**
  (`_negbin` + `_DISP_R=10` en match_predictor.py): los goles reales están
  SOBREDISPERSOS respecto a Poisson (Var>media). Medido con el propio modelo
  sobre 350 partidos: residuos estandarizados (G−λ)/√λ dan φ_home=1.40,
  φ_away=1.06 (Poisson daría φ=1.0) → el grid Poisson puro es DEMASIADO ESTRECHO
  y subestima marcadores atípicos/upsets (caso testigo: Australia 2-0 Turquía,
  13-jun — Turquía 30 tiros/xG 1.36 y 0 goles; el modelo daba Turquía favorita
  46.6%). La Negative Binomial conserva la media λ y ENSANCHA la cola
  (Var=λ+λ²/r); r→∞ recupera Poisson. **Hallazgo clave del backtest (set
  canónico 1508 part.):** la dispersión SOLO ayuda al MARCADOR (log-loss
  2.9169→2.9072, acierto exacto del grid 15.3%→15.7% con r óptimo≈10). En el
  **1X2 la calibración ya es buena** (los favoritos ganan algo MÁS de lo predicho:
  gaps +2..+6pp), así que ensanchar la distribución daña Brier W/D/L (+0.0018) y
  accuracy (−0.27pp) → **NO PASA el guard para 1X2.** Decisión guiada por datos
  (coherente con "marcador y ganador = lecturas independientes"): **NB se aplica
  SOLO a la grilla de marcador** (top_scores/predicted_score/goleada band, donde
  mejora la calibración) y **el 1X2 se mantiene en Poisson** (donde está mejor
  calibrado). Backtest del híbrido: W/D/L EXACTAMENTE intacto (Δacc=0, Δbrier=0,
  guard ✅) + cola de marcador más realista. `predicted_score` casi no cambia
  (−0.3pp ≈ ruido) porque está winner-gated; lo que mejora es la INCERTIDUMBRE
  reportada (pred_score_prob y top_scores). Flag A/B: WC_DISPERSION (1=on),
  WC_DISPERSION_R (valor de r). **Próximo paso (data-gated):** ligar r a la
  calidad/disponibilidad del plantel (menos cracks disponibles ⇒ más
  incertidumbre ⇒ r menor) — la 2ª intuición del dueño; requiere más resultados
  WC para calibrar sin sobreajuste.

**Parámetros calibrados:**
- `BASE_GOALS = 1.22`
- Neutral venue para WC EXCEPTO anfitriones en fase de grupos
- Draw boost W-5 framework (5 señales)
- model_bias λ_scale 0.907-0.910 (refit continuo)
- `_DISP_R = 10` (Negative Binomial en grilla de marcador; Poisson en 1X2)

### METODOLOGÍA DEL MARCADOR OFICIAL (13-jun — revisión v1.5)
**pred_scoreline = ARGMAX del grid conjunto Dixon-Coles** (pico real de la
distribución bivariada, nunca la mediana marginal). Razón: la mediana de
Poisson(λ) salta de 0→1 cuando λ>ln(2)≈0.693 aunque el MODO siga en 0,
produciendo empates fantasma incoherentes con el ganador probable.
Ejemplo: Haití(λ0.84) vs Escocia(λ1.46) → mediana daba 1-1, argmax da 0-1.
Código: `top_scores[0][0]` en `models/match_predictor.py`; model_version='1.5-argmax'.

### Simulador Torneo: `models/tournament.py` / `simulate.py`
### Simulación 1 partido: `models/full_match_sim.py`
### Análisis experto: `models/expert_analysis.py`

---

## COMANDOS PRINCIPALES

```bash
# Predicción partido
python3 predict.py --home "Argentina" --away "France"
python3 predict.py --home "Argentina" --away "France" --expert

# Simulación completa / torneo Monte Carlo
python3 simulate.py --match "Brazil" "Argentina"
python3 simulate.py --tournament

# Pipeline de datos
python3 pipelines/full_update.py --scope form|wc|all

# Backtest del modelo
python3 scripts/validate_model.py --days 365

# Resultados: team_matches → wc_matches y recalibrar
python3 scripts/sync_friendly_results.py            # auto
python3 scripts/sync_friendly_results.py --set 147 2-1   # manual (ej. id=1 2-0)
python3 scripts/evaluate_model.py                   # evalúa + refit (incluye % exactos)

# Pipeline de cargas manuales (TODO corre solo en daily_improvement.yml):
python3 scripts/fix_stats_links.py            # re-enlaza stats huérfanas
python3 scripts/sync_player_match_ratings.py  # ratings dueño → player_ratings
python3 scripts/team_strengths.py --report    # fortalezas/debilidades 8 ejes
python3 scripts/clean_team_matches.py --apply # dedupe/anti-fabricados (idempotente)
python3 scripts/fit_confederation_bias.py     # offsets confed + equipo
python3 scripts/predict_upcoming.py           # sella oficiales (argmax grid v1.5)
python3 scripts/sync_confirmed_xi.py          # match_lineups → projected_lineups
# Perfiles agregados:
python3 -c "import sys,sqlite3; sys.path.insert(0,'scripts'); \
from build_goal_timing import build_team_performance_profile; \
c=sqlite3.connect('data/mundial2026.db'); build_team_performance_profile(c)"
```

---

## WORKFLOWS GITHUB ACTIONS

| Workflow | Trigger | Scope |
|----------|---------|-------|
| `fetch_data.yml` | Diario 7am UTC + push | Auto-detectado |
| `match_day.yml` | Cada 30min 14:00-23:30 UTC + 00:00-03:30 UTC | wc + lineups por-fecha + sync XI |
| `fetch_players.yml` | Lunes 8am + DIARIO 5am UTC jun-jul | squads + club stats |
| `daily_improvement.yml` | Diario 8am UTC | sync resultados + fix_stats_links + confed refit + team_strengths + sync XI + ratings + predict + evaluate |

**Cadena de alineaciones:** api-sports → `match_lineups` → `sync_confirmed_xi.py`
→ `projected_lineups` → factor XI. Solo aplica con ≥10 titulares mapeados.

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

> **Mejoras del repo `logistic` deben portarse a `mundial2026` cuando estén validadas.**

---

## ERRORES CONOCIDOS Y SOLUCIONES

| Error | Causa | Solución |
|-------|-------|----------|
| `No module named 'models'` | CWD incorrecto | `cd /home/user/mundial2026` |
| `push rejected non-fast-forward` | Workflow pushó | fetch + importar DB remota POR CONTENIDO (nunca pisar lo local), rebase con --theirs (mi DB), push |
| Commits "Unverified" | Falta autor | `git config user.email "noreply@anthropic.com"` |
| APIs externas 403 | Política de red | Solo via GitHub Actions |
| `UNIQUE constraint failed` | Inserción duplicada | `INSERT OR IGNORE` / merge por densidad de datos |
| Lote predicciones v1.0 corrupto (09-jun) | probs invertidas | Corregido: nombres sellados + guard en evaluate |
| Amistosos sin evaluar | fetch escribe team_matches, evaluate lee wc_matches | `sync_friendly_results.py` |
| Filas dobles/fabricadas en team_matches | loaders múltiples + lote sintético ids 1-100 | `clean_team_matches.py --apply` (idempotente, en workflow) |
| **Stats huérfanas (11-jun)** | loader viejo usó match_id de team_matches; el modelo lee wc_matches | `fix_stats_links.py` (52→0 huérfanos; en workflow) |
| Ratings cargados ignorados | match_player_stats sin puente a player_ratings + JOIN explosivo | `sync_player_match_ratings.py` + agregado last-5 en `_get_xi_rating` |
| Ejes con -2.5σ falsos | campos NULL diluían promedios | denominadores por métrica en team_strengths (NULL→z neutral) |
| SIGPIPE mata scripts | `python3 script | head -N` | redirigir a archivo: `> /tmp/x.log 2>&1` |
| Jugadores duplicados (acentos) | 'Johan Vasquez' vs 'Johan Vásquez' | resolver por densidad de datos (best_id) |

---

## ESTADO ACTUAL

**Última actualización:** 14 junio 2026 — día 4 WC2026

### Cargados en sesión 14-jun:
```
✅ Colombia 1-3 France (amistoso 29-mar) — 33 jugadores + team stats (xG 1.12-1.63)
✅ Haití 0-1 Escocia (WC Grupo C, 13-jun) — 30 jugadores + team stats (xG 1.21-1.05)
   → Haití dominó xG y posesión pero McGinn (83') decidió: caso testigo del
     hallazgo de eficiencia/portería (Escocia GK para 0.61× el xGA).
```

### Evolución del modelo (14-jun): dos factores nuevos
1. **Eficiencia conversión + portería** (`_finishing_gk_factor`, WC_FINISHING):
   diagnóstico → el modelo no veía empates bajos/0-0 por ignorar la DESVIACIÓN
   goles↔xG y goles_concedidos↔xGA. Backtest CLARO (Brier cobertura −0.0073).
   FIJADO y activo.
2. **Jugadores diferenciadores** (`star_players` + `_star_off/def_factor`,
   WC_STARS): lista de 100 cracks del dueño. Backtest cumplió la regla
   pre-fijada (canónico Brier mejora, acc −0.1pp) → FIJADO, pero señal DÉBIL
   (doble-conteo con Elo/XI; backtest anacrónico subestima). Re-evaluar con WC
   real. Loader: `python3 scripts/load_star_players.py` (re-correr si cambia la
   lista o se cargan plantillas de Georgia/Nigeria).
Predicciones 14-17 jun re-selladas con ambos factores.

### Calibración acumulada (77 partidos selladas histórico):
accuracy **62.3%** | Brier **0.2975** | away_bias +0.207 | λ_scale 0.911 | v1.5-argmax
(histórico de predicciones viejas; el factor nuevo mejora calibración a futuro)

### Cobertura de datos (sesión 11-jun cargó ~20 partidos con stats):
- 42 selecciones con perfil de fortalezas; matchup ON para: todos los del
  12-13 jun salvo Escocia/Australia (n=2); Jordania/Túnez/Egipto/Brasil/
  Marruecos/Suiza/Qatar/Haití listos
- Calendario oficial completo: 72 partidos de grupos con fecha/hora Panamá/grupo
  (24 fixtures venían con local/visitante INVERTIDO — corregidos)
- Pendientes de convocatoria oficial: Escocia, Sudáfrica ya jugó, resto a demanda

### TAREAS AL INICIAR NUEVA SESION
1. Verificar hook + `git fetch` (importar datos remotos POR CONTENIDO si difieren)
2. **Pedir al dueño resultado + stats de Corea-Chequia** (día 1 sin cerrar)
3. **Pedir Qatar-Suiza y Brasil-Marruecos** (partido del 12-jun, sin cargar aún)
4. Si hay partidos nuevos → cargar (regla 8) y recalibrar
5. Re-sellar predicciones del día con alineaciones confirmadas cuando lleguen
6. Actualizar este CLAUDE.md con cambios relevantes + commit + push

---

## SESIONES WEB (Claude Code on the Web) — LÍMITES VERIFICADOS

| Recurso | Estado |
|---------|--------|
| `/root/.claude/.tokens` | ❌ NO existe en contenedores web |
| Repo de la sesión | Solo el del scope; este repo accesible vía **PAT pegado por el usuario** |
| Push | `git push https://<PAT>@github.com/FindITCorp/Mundial2026-.git main` (NO persistir el PAT) |
| APIs GitHub (api.github.com) | ❌ 403 — workflows solo desde GitHub Actions |
| APIs fútbol | ❌ Bloqueadas local — solo via GitHub Actions |
| WebSearch/WebFetch | ✅ Disponibles para verificar fechas/resultados puntuales |

**Para la próxima sesión web:** crear la sesión con `FindITCorp/Mundial2026-`
en el scope para no depender del PAT. Si el PAT se usó en un chat, ROTARLO después.
