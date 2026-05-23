# MUNDIAL 2026 — SISTEMA DE PREDICCION AVANZADO

## ESTADO DEL PROYECTO
**Ultima actualizacion:** 23 de mayo de 2026
**Proposito:** Sistema completo de prediccion y analisis del Mundial 2026
**Stack:** Python 3.11 · SQLite · requests · scipy · StatsBomb open data
**Estado:** 🟢 DATOS CARGADOS · WORKFLOWS PASANDO · SIMULADOR FUNCIONAL · EXPERT ANALYSIS LISTO

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

## ESTADO DE LA BASE DE DATOS (22 mayo 2026)

| Tabla | Registros | Fuente |
|-------|-----------|--------|
| teams | 48 | Estatico JSON |
| players | 2,131 | martj42 CSV + Wikipedia + manual (32-68 por equipo) |
| team_matches | 11,015 | martj42 CSV (hasta marzo 2026) |
| player_club_stats | 724 | Solo jugadores originales seeded |
| player_nat_stats | 1,437 | StatsBomb WC2022 |
| player_ratings | 2,855 | Computados (club+nat context) |
| squad_selections | 2,131 | Todos los jugadores |
| match_players | 3,782 | StatsBomb WC2022 (1992) + WC2018 (1790) |
| wc_matches | 72 | Calendario WC2026 estatico |
| wc_history | 192 | Historial WC 2014/2018/2022 |
| match_lineups | 0 | Se llenara durante el torneo |

**Jugadores por equipo:** min=32, max=68, promedio=44.4

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
  predict.py                       — Script maestro CLI

  scripts/
    setup_db.py                    — Crea/migra BD SQLite
                                     Incluye migrate_db() para ALTER TABLE seguro
    populate_match_players.py      — Carga StatsBomb WC2022 → match_players
    load_statsbomb_wc2018.py       — Carga StatsBomb WC2018 → match_players
    expand_squads_step1/2/3.py     — Expansion de plantillas a 32+ jugadores

  models/
    predictor.py                   — Motor prediccion (predict_match, TeamSnapshot)
    player_rating.py               — Rating 1-10 (PlayerRatingEngine, compute_all_ratings)
    simulator.py                   — Simulador Poisson 10,000 iteraciones (simulate_match)
    team_similarity.py             — Similitud entre equipos (8 dimensiones)
    expert_analysis.py             — ⚠ PENDIENTE DE CREAR (tarea activa)

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

### Para predecir un partido:
```bash
cd /home/user/mundial2026
python3 predict.py --home "Panama" --away "Croatia"
# O el analisis experto (cuando este listo):
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
