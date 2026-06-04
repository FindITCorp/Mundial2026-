# MUNDIAL 2026 — SISTEMA DE PREDICCION AVANZADO

## ESTADO DEL PROYECTO
**Ultima actualizacion:** 04 de junio de 2026
**Proposito:** Sistema completo de prediccion y analisis del Mundial 2026
**Stack:** Python 3.11 · SQLite · requests · scipy · StatsBomb open data
**Estado:** 🟢 DATOS CARGADOS · WORKFLOWS PASANDO · COMANDO ÚNICO `predict_match.py` (6 factores + auditoría) · EXPERT ANALYSIS LISTO

---

## INICIO RAPIDO (nueva sesion)

```bash
# 1. Cargar tokens y configurar remote
source /root/.claude/.tokens 2>/dev/null
git -C /home/user/mundial2026 remote set-url origin https://${GITHUB_TOKEN}@github.com/FindITCorp/Mundial2026-.git

# 2. Verificar DB
cd /home/user/mundial2026
python3 -c "import sqlite3; conn=sqlite3.connect('data/mundial2026.db'); print('players:', conn.execute('SELECT COUNT(*) FROM players').fetchone()[0])"
```

---

## REPOSITORIO

- **GitHub:** `FindITCorp/Mundial2026-` (con guion al final — es el nombre real)
- **Rama:** `main` (deploy y commits van aqui)
- **Ruta local:** `/home/user/mundial2026`
- **DB local:** `/home/user/mundial2026/data/mundial2026.db`
- **Token:** en `/root/.claude/.tokens` como `$GITHUB_TOKEN`

### Commits NO usan GPG — siempre usar:
```bash
git -c commit.gpgsign=false commit -m "mensaje"
```

---

## ESTADO DE LA BASE DE DATOS (04 junio 2026)

| Tabla | Registros | Fuente |
|-------|-----------|--------|
| teams | 48 WC correctos | Sorteo oficial FIFA verificado 04-jun |
| players | 2,131+ | martj42 CSV + Wikipedia + manual (32-68 por equipo) |
| team_matches | 11,015+ | martj42 + amistosos jun 2026 |
| player_club_stats | 1,000+ | Seeded + manual 27 equipos + Jamaica |
| player_nat_stats | 1,437 | StatsBomb WC2022 |
| player_ratings | 2,855+ | Computados (club+nat context) |
| squad_selections | 2,131 | Todos los jugadores |
| match_players | 3,782 | StatsBomb WC2022 (1992) + WC2018 (1790) |
| wc_matches | 72 | Calendario WC2026 estatico |
| wc_history | 192 | Historial WC 2014/2018/2022 |
| match_lineups | 0 | Se llenara durante el torneo |

**Cobertura de datos 48 equipos WC:** 48/48 con club_stats ✅ · 48/48 con xG>0 ✅

### GRUPOS OFICIALES WC 2026 (verificados 04 junio 2026)
| Grupo | Equipos |
|-------|---------|
| A | Czechia · Mexico · South Africa · South Korea |
| B | Bosnia and Herzegovina · Canada · Qatar · Switzerland |
| C | Brazil · Haiti · Morocco · Scotland |
| D | Australia · Paraguay · Turkey · USA |
| E | Curacao · Ecuador · Germany · Ivory Coast |
| F | Japan · Netherlands · Sweden · Tunisia |
| G | Belgium · Egypt · Iran · New Zealand |
| H | Cape Verde · Saudi Arabia · Spain · Uruguay |
| I | Costa Rica · France · Norway · Senegal |
| J | Algeria · Argentina · Austria · Jordan |
| K | Colombia · Jamaica · Portugal · Uzbekistan |
| L | Croatia · England · Ghana · Panama |

**EQUIPOS CORREGIDOS (04-jun-2026):** Eliminados de grupos: Italia, Dinamarca, Nigeria, DR Congo, Polonia, Rumania, Serbia, Venezuela, Honduras, Bolivia, Hungría, Eslovenia, Irak, Camerún (no clasificados al WC 2026).

---

## GITHUB ACTIONS — ESTADO

| Workflow | Estado | Trigger |
|----------|--------|---------|
| `fetch_data.yml` | ✅ PASANDO | Push a main + cron diario 7am UTC |
| `match_day.yml` | ✅ Configurado | Cada 30min Jun-Jul 2026 |
| `fetch_players.yml` | ✅ Configurado | Manual |

### Auto-scope logic en fetch_data:
- DB vacia → `all` (bootstrap)
- match_players < 100 → `historical`
- Junio/Julio → `wc`
- Lunes → `all`
- Resto → `form`

### APIs configuradas como GitHub Secrets:
- `FOOTBALL_DATA_KEY` = `8b7502413ce14eca89def90fc0be0fc4`
- `APIFOOT` = `557119c7a1mshdf149ae73f548b9p12dddfjsn039c48b00953` (RapidAPI)
- `APISPORTS_KEY` = `f4bc4a4935ea7cc82677931a55ed6c5c` (100 req/dia)

---

## ARQUITECTURA DE ARCHIVOS

```
mundial2026/
  CLAUDE.md                        — Este archivo (memoria del proyecto)
  requirements.txt
  predict.py                       — CLI clasico (analisis 1 partido, predictor.py)
  simulate.py                      — ★ CLI INTEGRAL: --match / --tournament / --group
                                     / --scorers / --referees / --draw

  scripts/
    setup_db.py                    — Crea/migra BD SQLite
                                     Incluye migrate_db() para ALTER TABLE seguro
    populate_match_players.py      — Carga StatsBomb WC2022 → match_players
    load_statsbomb_wc2018.py       — Carga StatsBomb WC2018 → match_players
    expand_squads_step1/2/3.py     — Expansion de plantillas a 32+ jugadores
    seed_tactics.py                — Tabla team_tactics (formacion, pressing, linea)
    seed_wc_groups.py              — ★ Sorteo valido 12 grupos de 4 (bombos Elo)
                                     → tabla wc_group_draw (datos de grupos limpios)
    validate_squads.py             — Validador de integridad de plantillas
    update_official_squads_may2026.py — Squads oficiales confirmados (10 equipos)

  models/
    predictor.py                   — Motor prediccion clasico (predict_match, TeamSnapshot)
    match_predictor.py             — ★ Motor Poisson 6-factores (Elo+xG+forma+XI+BP+pressing)
                                     con strength-of-schedule, regularizacion y ancla Elo
    elo.py                         — Sistema Elo dinamico (EloSystem, build_from_history)
    player_rating.py               — Rating 1-10 (PlayerRatingEngine, compute_all_ratings)
    simulator.py                   — Simulador Poisson 10,000 iteraciones (simulate_match)
    team_similarity.py             — Similitud entre equipos (8 dimensiones)
    team_dna.py / team_scout.py    — Perfiles tacticos e informes de scouting
    formation_engine.py            — Matchup de formaciones (multiplicadores xG)
    lineup_estimator.py            — XI estimado por historial del DT
    venue_model.py                 — Factor altitud sedes WC2026
    expert_analysis.py             — Analisis narrativo estilo experto
    ── NUEVOS (simulador integral) ──
    referee_model.py               — ★ 19 arbitros elite FIFA (tarjetas/penaltis/sesgo)
                                     + asignacion neutral por confederacion
    goal_scorer.py                 — ★ Modelo de goleador por jugador (goals_as_nat,
                                     posicion, forma club) + penalty taker + exclusiones
    match_events.py                — ★ Corners, tiros, faltas, tarjetas, penaltis
                                     (conversion SoT→gol real por equipo)
    full_match_sim.py              — ★ Simulador integral 1 partido (Monte Carlo):
                                     marcador + goleadores + eventos + arbitro + mercados
    tournament.py                  — ★ Monte Carlo del torneo completo (grupos→final):
                                     P(campeon/semis/etc) por equipo, ~1.2s/3000 torneos

  pipelines/
    full_update.py                 — Orquestador maestro (--scope all/squads/stats/form/lineups/wc/historical)
    fetch_daily_form.py            — Actualiza form: martj42 + FD.org + api-sports
    fetch_historical.py            — Descarga match_players historicos de WC via api-sports
    fetch_api_football.py          — API-Football wrapper con cache y rate limiting
    fetch_football_data_org.py     — football-data.org (schedule, history)
    fetch_club_stats.py            — Stats de jugadores en sus clubs
    fetch_nat_stats.py             — Stats en seleccion
    fetch_players.py               — Convocados oficiales
    fetch_predictions.py           — Predicciones de API externa
    update_wc.py                   — Resultados durante torneo
    update_lineup.py               — Alineaciones confirmadas

  .github/workflows/
    fetch_data.yml                 — Workflow principal (cron + push)
    match_day.yml                  — Actualizaciones cada 30min dia de partido
    fetch_players.yml              — Manual trigger para convocados

  data/
    mundial2026.db                 — BD SQLite principal
    static/
      teams_wc2026.json            — 48 equipos con grupo, ranking, seed
      schedule_wc2026.json         — 72 partidos WC2026
      wc_history.json              — Historial WC 2014/2018/2022
    cache/                         — Cache de API responses (24h TTL)
    logs/                          — Logs de pipelines
```

---

## TAREA COMPLETADA: expert_analysis.py ✅

### Que quiere el usuario:
Analisis estilo **analista experto** (no probabilidades), con:
1. Resultado concreto: `Croatia 2-1 Panama` (no `34% Panama gana`)
2. Analisis defensivo: cuanto concede la seleccion + calidad individual defensores en sus clubs
3. Analisis ofensivo: goles seleccion + referentes goleadores con datos de club
4. Forma reciente: ultimas 5 partidos con rachas (ej: "3 victorias consecutivas")
5. Historial directo (H2H)
6. Quien es el favorito segun los datos (no porcentajes de apuestas, sino analisis propio)
7. Proyeccion xG interna (Poisson) pero mostrar solo EL resultado, no las probabilidades
8. Narrativa cohesionada como un analista deportivo lo explicaria

### Diseño de la funcion principal:
```python
# models/expert_analysis.py
from models.expert_analysis import analyze_match

texto = analyze_match("Panama", "Croatia", db_path="data/mundial2026.db")
print(texto)
# Salida: informe completo en texto con bordes ASCII
```

### Factores del calculo de xG:
- `base_xg_a` = promedio goles marcados (ultimos 20 partidos seleccion)
- `def_mod_b` = 1.0 - (def_score_b - 5.0) * 0.04  # defensa fuerte reduce xG rival
- `att_mod_a` = 1.0 + (att_score_a - 5.0) * 0.035 # ataque fuerte aumenta xG
- `form_mod_a` = 1.0 + (form_score_a - 0.5) * 0.25 # forma reciente (0-1)
- `h2h_factor` = ±0.12 si hay dominio historico claro
- `xg_a = base_a * def_mod_b * att_mod_a * form_mod_a * h2h_a`

### Scoring de defensores (0-10):
- Base: player_ratings.rating
- +0.6 si juega en liga Tier-1 (PL, La Liga, Bundesliga, Serie A, Ligue 1)
- +0.3 si liga Tier-2 (Eredivisie, Liga PT, MLS, Liga MX, Saudi, etc.)
- -0.3 si liga Tier-4 (ligas nacionales centroamericanas, etc.)
- +0.5 bonus si market_value_m > 50M (jugador de alto valor)

### Scoring de atacantes (0-10):
- Base: player_ratings.rating
- +hasta 1.2 por goles/caps en seleccion nacional
- +hasta 0.8 por goles+asistencias en club (si player_club_stats disponible)
- Ajuste por tier de liga

---

## ⚠️ PRINCIPIO DE COBERTURA (NO DEJAR EQUIPOS AFUERA)

**Regla de oro:** TODA predicción debe pasar por `predict_match()` con equipos
registrados en `teams` + `team_elo`. **NUNCA** improvisar fórmulas Poisson manuales
para equipos "que no están en la DB" — eso se salta Elo, Dixon-Coles, timing y XI.

### Cómo se garantiza:
```bash
# Auditar cobertura (qué equipos con historial NO están registrados)
python3 scripts/repair_coverage.py --audit

# Reparar: registra equipos faltantes, enlaza opponent_id, reconstruye Elo
python3 scripts/repair_coverage.py --repair

# Verificar que un fixture sea 100% predecible ANTES de predecir
python3 scripts/repair_coverage.py --check "Wales" "Ghana"
```

### Qué resolvió (2 jun 2026):
- Antes: solo 79 equipos en `teams`; 177 con historial sin registrar → improvisación
- `team_matches` tenía 44% de partidos SIN `opponent_id` → excluidos del Elo
- Después: **198 equipos con Elo**, **97% de partidos enlazados**
- Alias en `data/team_name_aliases.json` evitan duplicados (United States→USA,
  Czech Republic→Czechia, Ireland→Republic of Ireland, etc.)
- Equipos extintos/sancionados (Yugoslavia, Czechoslovakia, Russia…) NO se registran

### Checklist antes de cualquier predicción nueva:
1. `--check` los dos equipos → ambos deben decir ✅ PREDECIBLE
2. Si alguno dice ❌ INCOMPLETO → correr `--repair`
3. Predecir SIEMPRE con `predict_match(home_id, away_id)` — jamás a mano

---

## SIMULADOR (FUNCIONANDO)

```python
# Uso correcto del simulador
from models.predictor import TeamSnapshot, load_team, load_recent_form
from models.simulator import simulate_match

def make_snapshot(name):
    team = load_team(name, db_path="data/mundial2026.db")
    form = load_recent_form(name, last_n=10, db_path="data/mundial2026.db")
    return TeamSnapshot(
        name=name,
        recent_form=form,
        ranking_fifa=team.get("fifa_ranking", 50) if team else 50,
        goals_scored_avg=team.get("goals_scored_avg", 1.5) if team else 1.5,
        goals_conceded_avg=team.get("goals_conceded_avg", 1.2) if team else 1.2,
        possession_avg=team.get("possession_avg", 50.0) if team else 50.0,
    )

snap_a = make_snapshot("Brazil")
snap_b = make_snapshot("Argentina")
result = simulate_match(snap_a, snap_b, n=10000)
# result["most_likely_scoreline"] = "1-1"
# result["home_wins_pct"] = 34.2
# result["raw_text"] = texto completo formateado
```

### Resultado verificado:
```
Brazil vs Argentina (10,000 sim):
  Victoria Brazil:    34.2%
  Empate:             26.2%
  Victoria Argentina: 39.5%
  Marcador mas probable: 1-1 (12.5%)
  xG: Brazil 1.27 - Argentina 1.37
```

---

## ERRORES RESUELTOS (para no repetir)

| Error | Causa | Solucion |
|-------|-------|----------|
| `No module named 'pipelines'` | `sys.path[0]` apunta a `pipelines/` al correr `python pipelines/full_update.py` | Agregar `sys.path.insert(0, str(BASE_DIR))` en full_update.py |
| `UNIQUE constraint failed: team_matches` | `seed_sample_match_history()` usaba `INSERT INTO` sin `OR IGNORE` | Cambiar a `INSERT OR IGNORE` |
| `no such column: wc_history.api_fixture_id` | Tabla creada antes de agregar esa columna | `migrate_db()` en setup_db.py hace `ALTER TABLE` seguro |
| `PlayerRater not found` | full_update.py importaba `PlayerRater` que no existia | Agregar `PlayerRater = PlayerRatingEngine` en player_rating.py |
| `context='overall'` CHECK constraint | player_ratings.context solo acepta `'club'` o `'nat'` | Usar `context='nat'` |
| Workflow `fetch_data` falla en `Setup database` | UNIQUE constraint en seed → exit code 1 | INSERT OR IGNORE fix |
| `cron '0 7 * * 2-7'` invalido | GitHub Actions no acepta 7 en rangos de dia | Cambiar a `'0 7 * * *'` |

---

## DATOS PENDIENTES

| Dato | Estado | Accion |
|------|--------|--------|
| player_club_stats para 1407 jugadores nuevos | Sin datos | Se llenara via api-sports GitHub Actions diario (100 req/dia) |
| Datos abril-mayo 2026 | No en martj42 | Llegara via api-sports cuando corran los workflows |
| WC 2014 match_players | No disponible en StatsBomb | Requiere api-sports (scope=historical via Actions) |
| match_lineups | 0 | Se llena cuando comiencen partidos (11 junio 2026) |

---

## PROTOCOLO DE TRABAJO

### ★★★ COMANDO OFICIAL DE PREDICCION — predict_match.py ★★★
**ÚNICO comando canónico. El usuario pasa los partidos, este devuelve el resultado.**
NO usar simuladores parciales ni scripts ad-hoc: SIEMPRE pasa por el motor completo
de 6 factores (Elo + forma/xG + XI 11v11 con ratings club+selección + balón parado
+ pressing + H2H) y AUDITA que cada factor tenga datos reales. Si alguno cae en
default, lo AVISA explícitamente (regla de oro: el modelo nunca deja una
consideración fuera en silencio).

```bash
cd /home/user/mundial2026
python3 predict_match.py "Mexico" "Serbia"                       # un partido
python3 predict_match.py --pairs "Spain|Iraq" "Mexico|Serbia"    # varios
python3 predict_match.py --file data/lineups/predict_pairs.txt   # desde archivo
python3 predict_match.py "Mexico" "Serbia" --home-out "Edson Álvarez:suspension,Raúl Jiménez:injury"
python3 predict_match.py "Mexico" "Serbia" --json                # salida JSON
```
- Corre LOCAL (solo lee la DB, no consume API ni GitHub Actions).
- Salida: marcador probable + prob (L/E/V) + λ goles + **calidad XI (11v11)** + Elo
  + formación + posesión + top marcadores + **AUDITORÍA de los 6 factores**.
- Acepta bajas/suspensiones con `--home-out` / `--away-out` (formato `Jugador:reason`,
  reason ∈ injury/suspension/red_card). Recalcula el λ excluyendo al ausente.

REGLAS DURAS (no repetir errores pasados):
- El motor lee `projected_lineups` (XI titular, 26 convocados) + `player_ratings`
  (context='nat') + `player_club_stats` season '2024/25' (xg/goals/assists reales).
- El factor XI se capa a 0.62 si hay club_stats reales (no a 0.36, que era para
  equipos sin datos). Ver `_get_xi_rating()` en models/match_predictor.py.
- Si la auditoría marca ⚠ DEFAULT en un equipo CLASIFICADO → hay que cargar ese
  dato antes de confiar en la predicción. Para rivales NO clasificados, el ⚠ es
  esperado y la predicción se reporta como "no fiable".

### ★ PESO DE SEÑAL POR PARTIDO en la FORMA (calibración 04-jun-2026) ★
No todos los partidos informan igual sobre la forma real. `_get_form()` pondera
CADA partido por `señal = importancia_competición × fuerza_alineación`:
- **Importancia de competición** (`_comp_importance`): amistoso 0.45 ≪ eliminatoria
  0.84-0.88 < torneo mayor 1.00 (WC/Euro/Copa América). Un amistoso pesa la mitad.
- **Fuerza de alineación** (`_lineup_strength_factor`): mide qué tanto del XI que
  REALMENTE jugó (player_match_usage) está entre los 26 convocados oficiales
  (projected_lineups). Equipo A ≈ 1.00; equipo B ≈ 0.60; juvenil/amateur ≈ 0.40.
  → "empatar 1-1 con tu equipo B" NO penaliza la forma del equipo A del Mundial.
  El cruce es por APELLIDO normalizado (`_name_key`), robusto a player_id duplicados.
- Datos reales: competition (team_matches) + alineación (player_match_usage). NO se
  recalibran parámetros sin datos — solo se pondera la SEÑAL conocida de cada partido.

### ⚠ CONTAMINACIÓN JUVENIL/B — resuelta (04-jun-2026)
El pipeline `fetch_smartapi_lineups.py` metía partidos juveniles ("Spain U21",
"France U19") en el team_id ABSOLUTO por el fallback "contiene" de `_resolve_team`.
Doble blindaje:
1. **Pipeline**: `_is_senior()` rechaza nombres con U17/U21/women/reserves/etc ANTES
   del match difuso. NO ingiere juveniles.
2. **Modelo**: `_lineup_strength_factor` descuenta a 0.40 cualquier XI sin solape
   con los convocados (defensa en profundidad si la API mintiera el nombre).
Se limpiaron 638 filas (31 partidos) ya contaminadas de player_match_usage.

### Predicción legacy (referencia, NO usar como principal):
```bash
python3 predict.py --home "Panama" --away "Croatia"
python3 models/expert_analysis.py "Panama" "Croatia"
```

### Para correr el pipeline de datos (local):
```bash
python3 pipelines/full_update.py --scope form
```

### Para triggear GitHub Actions manualmente:
```bash
source /root/.claude/.tokens
curl -X POST "https://api.github.com/repos/FindITCorp/Mundial2026-/actions/workflows/fetch_data.yml/dispatches" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -d '{"ref":"main","inputs":{"scope":"historical"}}'
```

### Para hacer commit y push:
```bash
cd /home/user/mundial2026
git add <archivos>
git -c commit.gpgsign=false commit -m "mensaje"
git push -u origin main
```

---

## PROXIMOS PASOS

- [x] ~~CREAR `models/expert_analysis.py`~~ — LISTO, deployado
- [x] ~~Conectar expert_analysis con predict.py como `--expert`~~ — LISTO
- [x] ~~Corregir roster 48 equipos WC2026~~ — LISTO (script fix_teams_wc2026.py ejecutado)
- [ ] Incorporar odds por partido (The Odds API, 500 req/mes gratis) — disponible cuando empiece torneo
- [ ] Cuando esten las convocatorias oficiales: `scope=squads` via GitHub Actions
- [ ] Durante torneo (desde 11 junio): `scope=wc` para actualizar resultados en tiempo real

### Uso del analisis experto:
```bash
python3 predict.py --home "Panama" --away "Croatia" --expert
# o directamente:
python3 models/expert_analysis.py "Panama" "Croatia"
```

### Estado equipos (23 mayo 2026):
- 48 equipos correctos (fixture oficial FIFA draw)
- 14 equipos erroneos eliminados (Bolivia, Italy, Denmark, Poland, etc.)
- 14 equipos nuevos agregados (Ivory Coast, Norway, Algeria, Haiti, etc.)
- Grupos A-L asignados segun sorteo oficial
- Rankings FIFA abril 2026: Francia #1, España #2, Argentina #3
- Odds apuestas y probabilidades Opta cargadas para los 48 equipos
