# MUNDIAL 2026 — SISTEMA DE PREDICCION AVANZADO

## ESTADO DEL PROYECTO
**Ultima actualizacion:** 21 de mayo de 2026
**Proposito:** Sistema completo de prediccion y analisis del Mundial 2026
**Stack:** Python 3.11 · SQLite · requests · pandas · scikit-learn
**Estado:** MVP COMPLETO Y FUNCIONAL

---

## DATOS DEL TORNEO

### Mundial 2026
- **Fechas:** 11 junio – 19 julio de 2026
- **Sedes:** USA (principal), Mexico, Canada
- **Equipos:** 48 selecciones (12 grupos de 4)
- **Partido inaugural:** 11 de junio, 2026 — Estadio Azteca, CDMX
- **Anfitriones:** Mexico, USA, Canada

---

## ARQUITECTURA COMPLETA

```
mundial2026/
  predict.py                     — Script maestro de prediccion
  requirements.txt               — Dependencias Python

  scripts/
    setup_db.py                  — Crea y pobla la BD SQLite completa
                                   Incluye: 48 equipos, 517+ jugadores, 72 partidos WC,
                                   144 registros historial WC, 100 matches de forma

  models/
    __init__.py
    predictor.py                 — Motor de prediccion avanzado (REEMPLAZADO)
                                   Flujo: Squad ratings -> Form -> H2H/Proxy -> WC History
                                   Output: probs, scoreline, line-by-line, matchups
    player_rating.py             — Rating de jugadores 1-10 por posicion
                                   club_form_rating, nat_form_rating, consistency_delta
    team_similarity.py           — Similitud entre equipos para proxy H2H
                                   8 dimensiones: goles, defensa, posesion, estilo...

  pipelines/
    __init__.py
    fetch_teams.py               — Actualiza FIFA rankings (API + static fallback)
    fetch_team_matches.py        — Ultimos 3 anos de resultados por equipo
    fetch_players.py             — Listas de convocados y perfiles de jugadores
    fetch_club_stats.py          — Stats de club por jugador (con sintesis si no hay API)
    fetch_nat_stats.py           — Stats en seleccion + sintesis desde historial
    update_wc.py                 — Actualiza resultados durante el torneo
    update_lineup.py             — Crea/carga alineaciones confirmadas
    full_update.py               — Pipeline maestro: ejecuta todo en orden correcto

  data/
    mundial2026.db               — Base de datos SQLite (generada por setup_db.py)
    static/
      teams_wc2026.json          — 48 equipos con grupo, ranking, seed
      schedule_wc2026.json       — Calendario completo de partidos
      wc_history.json            — Historial WC 2014, 2018, 2022 por equipo
    processed/
      mexico.json                — (Legacy) datos procesados por seleccion
    lineups/
      *.json                     — Alineaciones confirmadas por partido
    cache/
      teams/, matches/, players/ — Cache de respuestas de API (evita re-llamadas)
    raw/                         — Datos crudos de APIs
```

---

## ESQUEMA DE BASE DE DATOS

### Tablas principales:

| Tabla | Descripcion | Registros |
|-------|-------------|-----------|
| `teams` | 48 selecciones WC2026 | 48 |
| `players` | Jugadores por seleccion | 517+ |
| `team_matches` | Historial reciente de partidos | 100+ |
| `wc_history` | Rendimiento en WC 2014-2022 | 144 |
| `wc_matches` | Calendario WC2026 | 72 |
| `player_club_stats` | Stats de club por temporada | Auto |
| `player_nat_stats` | Stats en seleccion | 1100+ |
| `player_ratings` | Ratings computados | Auto |
| `squad_selections` | Convocados confirmados | 517+ |
| `match_lineups` | Alineaciones de partidos WC | Auto |

---

## MODELO DE PREDICCION

### Flujo de prediccion (predict_match):
1. Cargar registros de ambos equipos desde DB
2. Cargar plantillas y calcular ratings por posicion (GK/DEF/MID/FWD)
3. Calcular forma reciente (ultimos 10 partidos, decay=0.88)
4. Buscar H2H directo (ultimos 10 partidos)
5. Si no hay H2H: usar similitud de equipos para proxy
6. Cargar historial WC (2014, 2018, 2022) con decay por antiguedad
7. Calcular ranking FIFA factor (log scale)
8. Composicion ponderada del score final
9. Probabilidades W/D/L + normalizacion
10. Marcador probable (modelo Poisson)

### Pesos del modelo:
| Componente | Peso |
|------------|------|
| Calidad de jugadores | 32% |
| Forma reciente | 25% |
| H2H (o proxy) | 18% |
| Ranking FIFA | 15% |
| Historial WC | 10% |

### Rating de jugadores (1-10):
- Base: 6.0
- Goles: +1.5/gol (DEF: +1.8)
- Asistencias: +0.8
- Precision pase vs benchmark por posicion: +-1.5
- Tackles/intercepciones (DEF/MID): hasta +1.2
- Shots on target ratio (FWD/MID): hasta +0.8
- Tarjeta amarilla: -0.3, Roja: -2.0
- Factor de minutos jugados (<45min = parcial)
- GK: saves bonus, goals_conceded penalty

---

## COMO USAR

### Predecir un partido:
```bash
python predict.py --home "Panama" --away "Croatia"
python predict.py --home "Brazil" --away "Argentina"
python predict.py --home "Mexico" --away "USA" --lineup mexico_vs_usa
python predict.py --home "France" --away "England" --json  # Output JSON
python predict.py --home "Spain" --away "Germany" --no-lineup  # Sin mostrar alineacion
```

### Ver equipos y calendario:
```bash
python predict.py --list-teams          # Todos los 48 equipos
python predict.py --group D             # Calendario Grupo D
python predict.py --schedule            # Calendario completo
```

### Setup inicial (solo primera vez):
```bash
python scripts/setup_db.py              # Crea BD con todos los datos
python scripts/setup_db.py --reset      # Borra y recrea desde cero
```

### Actualizar datos (pipelines):
```bash
python pipelines/full_update.py                          # Actualizacion completa
python pipelines/full_update.py --scope squads           # Solo convocatorias (cuando salen oficialmente)
python pipelines/full_update.py --scope form             # Solo forma reciente
python pipelines/full_update.py --scope stats            # Solo stats de jugadores
python pipelines/full_update.py --scope lineups          # Solo alineaciones confirmadas
python pipelines/full_update.py --scope wc               # Solo resultados WC (durante torneo)
python pipelines/full_update.py --teams "Panama" "Croatia"  # Solo 2 equipos
python pipelines/full_update.py --quick                  # Sin API calls lentos
```

### Durante el torneo:
```bash
python pipelines/update_wc.py                         # Auto-actualizar resultados
python pipelines/update_wc.py --upcoming              # Ver proximos partidos
python pipelines/update_wc.py --result 5 2 1          # Setear resultado manualmente
python pipelines/update_wc.py --match-id 19           # Recomputar ratings match
```

### APIs individuales:
```bash
# API-Football (RapidAPI):
python pipelines/fetch_api_football.py --status           # Ver uso de API (calls/day)
python pipelines/fetch_api_football.py --squad "Panama"   # Squad oficial de Panama
python pipelines/fetch_api_football.py --fixtures 1887    # Ultimos 20 partidos Panama
python pipelines/fetch_api_football.py --h2h 1887 3       # H2H Panama vs Croatia
python pipelines/fetch_api_football.py --lineup 1234567   # Alineacion confirmada por fixture_id
python pipelines/fetch_api_football.py --all-squads       # Squads de los 48 equipos

# football-data.org:
python pipelines/fetch_football_data_org.py --schedule     # Calendario WC2026
python pipelines/fetch_football_data_org.py --standings    # Clasificacion actual
python pipelines/fetch_football_data_org.py --history "Panama"  # Historial Panama (3 anos)
python pipelines/fetch_football_data_org.py --all          # Todo de una vez
```

### Jugadores y similitud:
```bash
python models/player_rating.py "Panama"               # Ratings plantilla
python models/team_similarity.py "Panama"             # Equipos similares
python models/team_similarity.py "Panama" "Croatia"   # Proxy H2H
python models/lineup_estimator.py "Panama"            # Alineacion estimada standalone
```

### Trigger manual via GitHub Actions:
- Ve a: `Actions` > `Update WC2026 Data` > `Run workflow`
- Selecciona scope: `all / squads / stats / form / lineups / wc`
- El workflow corre, actualiza el DB y hace commit automatico

---

## COMO FUNCIONA LA ESTIMACION DE ALINEACION

Cuando NO hay alineacion confirmada en `match_lineups`, `predict.py` llama a `models/lineup_estimator.py`:

1. **Formacion del DT** (hardcodeada por equipo):
   - Brazil/Argentina/Spain/England/Portugal/Morocco/Senegal/Mexico/USA: 4-3-3
   - France/Germany/Croatia/Japan: 4-2-3-1
   - Netherlands: 3-4-3
   - Panama: 4-4-2
   - Default (otros): 4-4-2

2. **Seleccion de jugadores** (por posicion segun formacion):
   - Prioridad 1: Frecuencia en ultimos 10 partidos de seleccion (player_nat_stats)
   - Prioridad 2: Rating mas alto disponible (player_ratings)
   - Prioridad 3: Si ratings vacios, usa club_stats como proxy (goles/asistencias/minutos)
   - Excluye: jugadores con confirmed=0 en squad_selections (lesionados/suspendidos)

3. **Confianza** (high/medium/low):
   - HIGH: ratings + frecuencia nat stats + squad completo
   - MEDIUM: ratings disponibles o squad completo pero sin freq data
   - LOW: datos limitados

4. **Output** muestra: "ESTIMADA (basada en historial del DT)" vs "CONFIRMADA"

---

## CUANDO SALEN LAS CONVOCATORIAS OFICIALES

1. Ejecutar: `python pipelines/full_update.py --scope squads`
2. O via GitHub Actions: `Actions > Update WC2026 Data > Run workflow > scope=squads`
3. Si tienes los datos en JSON: crear `data/lineups/equipo_vs_equipo.json` y usar `--lineup`

---

## API RATE LIMITS Y PRESUPUESTO DIARIO

### API-Football (RapidAPI) — Free Tier:
- **100 requests/day** limite duro
- El sistema trackea uso en: `data/cache/api_calls_log.json`
- Cache: 24h (no re-llama si cache reciente)
- Para ver uso actual: `python pipelines/fetch_api_football.py --status`
- Priorizar llamadas: squads (48 calls) + form (48 calls) = 96 calls/dia maximo
- Guardar 4-5 calls de reserva para lineups live en dia de partido

### football-data.org — Free Tier:
- 10 requests/minute
- El pipeline incluye sleeps automaticos para respetar el limite
- Scope `form` y `schedule` son las mas utiles en free tier

### Estrategia para conservar calls:
```
Lunes (off-season): full update = squads + form
Dia de partido: scope=lineups (1-2 calls) + scope=wc (1 call)
Post-partido: scope=stats para actualizar ratings
```

---

## FUENTES DE DATOS

| Fuente | Que tiene | API Key |
|--------|-----------|---------|
| football-data.org | Resultados, H2H, clasificaciones, calendario | FOOTBALL_DATA_API_KEY |
| api-football.com (RapidAPI) | Squads, stats jugadores, alineaciones live | API_FOOTBALL_KEY |
| Datos estaticos (data/static/) | 48 equipos, calendario, historial WC | Sin clave |

API Keys en `.env` (nunca en git). Ver `.env.example`.

**El sistema funciona completamente sin API keys** usando datos estaticos y sintetizados.

---

## DATOS DISPONIBLES SIN API

### 48 Selecciones con:
- Nombre, confederacion, grupo, ranking FIFA
- Estilo tactico, esquema, linea defensiva, pressing
- Promedios historicos de goles y posesion

### 517+ Jugadores (11 por equipo) con:
- Posicion, club, liga, edad, caps, goles en seleccion
- Ratings estimados por liga de club y perfil

### Historial WC (2014, 2018, 2022):
- Ronda alcanzada por equipo
- Goles a favor/en contra
- Partidos jugados

### Calendario WC2026:
- 72 partidos (fase de grupos + inicio eliminacion)
- Fechas, venues, ciudades, grupos

---

## PROTOCOLO: "dame el analisis del partido X"

1. Verificar DB: `python scripts/setup_db.py` si no existe
2. Correr prediccion: `python predict.py --home X --away Y`
3. Si quieres actualizar con datos reales de API: `python pipelines/full_update.py --teams X Y`
4. Para alineacion confirmada: crear `data/lineups/x_vs_y.json` y usar `--lineup x_vs_y`

---

## PARA RETOMAR EN NUEVA SESION

Escribe: `continuamos mundial`

El contexto esta en este CLAUDE.md.
El sistema esta completamente funcional: BD creada, 517 jugadores, 48 equipos.
El proyecto logistico (separado) esta en `/home/user/logistic/`.

---

## ARCHIVOS NUEVOS (mayo 2026)

| Archivo | Descripcion |
|---------|-------------|
| `pipelines/fetch_api_football.py` | Pipeline completo API-Football con cache y rate limiting |
| `pipelines/fetch_football_data_org.py` | Pipeline football-data.org (schedule, history, standings) |
| `pipelines/full_update.py` | Orquestador maestro reemplazado con --scope y logging |
| `.github/workflows/fetch_data.yml` | Workflow actualizado con scope selection y cron schedule |
| `.github/workflows/match_day.yml` | Nuevo workflow: actualizaciones cada 30min en dias de partido |

---

## PROXIMOS PASOS

- [ ] Configurar API keys en GitHub Secrets (FOOTBALL_DATA_API_KEY, API_FOOTBALL_KEY)
- [ ] Agregar datos de alineaciones cuando se confirmen convocatorias oficiales
- [ ] Actualizar fixtures en schedule_wc2026.json con horarios confirmados
- [ ] Agregar modelo xG (goles esperados) para prediccion de marcador mas precisa
- [ ] Jupyter notebook con analisis de grupos completo
- [ ] Durante torneo: correr scope=wc tras cada jornada via GitHub Actions
