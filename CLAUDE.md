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

### Actualizar datos:
```bash
python pipelines/full_update.py                       # Actualizacion completa
python pipelines/full_update.py --quick               # Sin API calls lentos
python pipelines/full_update.py --teams "Panama" "Croatia"  # Solo 2 equipos
python pipelines/full_update.py --wc-only             # Solo resultados WC (durante torneo)
```

### Durante el torneo:
```bash
python pipelines/update_wc.py                         # Auto-actualizar resultados
python pipelines/update_wc.py --upcoming              # Ver proximos partidos
python pipelines/update_wc.py --result 5 2 1          # Setear resultado manualmente
python pipelines/update_wc.py --match-id 19           # Recomputar ratings match
```

### Jugadores y similitud:
```bash
python models/player_rating.py "Panama"               # Ratings plantilla
python models/team_similarity.py "Panama"             # Equipos similares
python models/team_similarity.py "Panama" "Croatia"   # Proxy H2H
```

---

## FUENTES DE DATOS

| Fuente | Que tiene | API Key |
|--------|-----------|---------|
| football-data.org | Resultados, H2H, clasificaciones | FOOTBALL_DATA_API_KEY |
| api-football.com | Stats por jugador, alineaciones, fixtures | API_FOOTBALL_KEY |
| Datos estaticos (data/static/) | 48 equipos, calendario, historial WC | Sin clave |

API Keys en `.env` (nunca en git). Ver `.env.example`.

**El sistema funciona sin API keys** usando los datos estaticos y sintetizados.

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

## PROXIMOS PASOS

- [ ] Conectar API keys para datos reales (football-data.org, api-football.com)
- [ ] Agregar datos de alineaciones cuando se confirmen convocatorias oficiales
- [ ] Actualizar fixtures en schedule_wc2026.json con horarios confirmados
- [ ] Agregar modelo xG (goles esperados) para prediccion de marcador mas precisa
- [ ] Jupyter notebook con analisis de grupos completo
- [ ] Durante torneo: correr `pipelines/update_wc.py` tras cada jornada
