# MUNDIAL 2026 — ANÁLISIS Y PREDICCIÓN

## ESTADO DEL PROYECTO
**Última actualización:** 21 de mayo de 2026
**Propósito:** Herramienta personal de análisis y predicción de partidos del Mundial 2026
**Stack:** Python 3.11 · pandas · scikit-learn · APIs de fútbol

---

## DATOS DEL TORNEO

### Mundial 2026
- **Fechas:** 11 junio – 19 julio de 2026
- **Sedes:** USA (principal), México, Canadá
- **Equipos:** 48 selecciones (16 grupos de 3)
- **Partido inaugural:** 11 de junio, 2026 — Estadio Azteca, CDMX
- **Anfitriones:** México, USA, Canadá

### Partido inaugural (11 junio 2026)
- **Estadio Azteca**, Ciudad de México (87,500 cap.)
- México vs. [rival a confirmar por sorteo/fixture oficial]
- Primera vez que México juega Mundial en casa desde 1986

---

## ESTRUCTURA DEL PROYECTO

```
mundial2026/
  predict.py                  — Predicción de un partido concreto
  pipelines/
    fetch_data.py             — Descarga datos de APIs (football-data.org, API-Football)
    update_lineup.py          — Crea/actualiza alineaciones confirmadas
  models/
    predictor.py              — Motor de predicción (form + H2H + ranking + disponibilidad)
  data/
    raw/                      — JSON de APIs (no en git)
    processed/                — Datos procesados por selección (mexico.json, etc.)
    lineups/                  — Alineaciones confirmadas por partido
    news/                     — Noticias relevantes
  analysis/                   — Jupyter notebooks para exploración
```

---

## CÓMO USAR

### Predecir un partido
```bash
# Predecir con alineación en archivo:
python predict.py --home "Mexico" --away "Polonia" --lineup mexico_vs_polonia

# Predecir sin alineación (usa datos base):
python predict.py --home "Mexico" --away "Polonia"
```

### Actualizar datos
```bash
python pipelines/fetch_data.py
```

### Crear archivo de alineación para un partido
```bash
python pipelines/update_lineup.py --match "Mexico vs Polonia" --home "Mexico" --away "Polonia"
# Edita data/lineups/mexico_vs_polonia.json con la alineación confirmada
```

---

## FUENTES DE DATOS

| Fuente | Qué tiene | API Key |
|--------|-----------|---------|
| football-data.org | Resultados, H2H, clasificaciones | FOOTBALL_DATA_API_KEY |
| api-football.com | Stats por jugador, alineaciones | API_FOOTBALL_KEY |
| newsapi.org | Noticias recientes | NEWS_API_KEY |

API Keys en `.env` (nunca en git). Ver `.env.example`.

---

## DATOS DISPONIBLES (selecciones con JSON en data/processed/)

| Selección | Ranking FIFA | Datos | Actualizado |
|-----------|-------------|-------|-------------|
| México | 15 | Forma, jugadores clave | 21 mayo 2026 |

---

## MODELO DE PREDICCIÓN (models/predictor.py)

### Variables del modelo
| Variable | Peso | Descripción |
|----------|------|-------------|
| Forma reciente | 30% | Últimos 10 partidos, más reciente = más peso |
| H2H | 25% | Historial directo entre ambas selecciones |
| Ranking FIFA | 20% | Proxy de calidad general |
| Disponibilidad | 15% | Penaliza por bajas de jugadores clave |
| Ataque | 10% | Goles promedio anotados |

### Output del modelo
- Probabilidades: Victoria local / Empate / Victoria visitante
- Resultado más probable + confianza %
- Breakdown de scores por componente
- Bajas/lesiones incluidas en análisis

---

## PROTOCOLO: "dame el análisis del partido X"

Cuando el usuario pida análisis de un partido:
1. Verificar si hay datos en `data/processed/<team>.json`
2. Verificar si hay alineación en `data/lineups/<slug>.json`
3. Si faltan datos → correr `fetch_data.py` o pedir al usuario que los proporcione
4. Correr `python predict.py --home X --away Y --lineup slug`
5. Complementar con contexto de noticias recientes, lesiones confirmadas y H2H histórico

---

## PRÓXIMOS PASOS

- [ ] Agregar datos de las 47 selecciones clasificadas en data/processed/
- [ ] Conectar API keys (football-data.org, api-football.com)
- [ ] Script de scraping de rankings FIFA actualizados
- [ ] Jupyter notebook con análisis H2H entre grupos
- [ ] Datos del partido inaugural (rival de México confirmado)
- [ ] Modelo de goles esperados (xG) para predicción de marcador exacto

---

## PARA RETOMAR EN NUEVA SESIÓN

Escribe: `continuamos mundial`

El contexto está en este CLAUDE.md. El proyecto logístico (separado) está en `/home/user/logistic/`.
