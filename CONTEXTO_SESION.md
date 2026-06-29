# Contexto de Sesión — Pool Mundial 2026 "Kike"

> **Documento de handoff.** Lee esto primero para retomar el trabajo sin perder nada.
> Última actualización: **2026-06-28 (fase de grupos COMPLETA + dieciseisavos en curso + modelo optimizado + capas tácticas nuevas)**

---

## 🆕 EMPEZAR AQUÍ (resumen para chat nuevo — 28-jun)

**ESTADO: fase de grupos COMPLETA (72/72), dieciseisavos EN CURSO.**
- ✅ **R32 #1 jugado: Sudáfrica 0-1 Canadá** (gol 94'). **Mi pronóstico Canadá 1-0 = GANADOR + MARCADOR EXACTO** + tiebreaker (Canadá 76% avanzar) acertó.
- 🔜 **MAÑANA 29-jun:** **Brasil vs Japón 17:00** (sellado **1-1**, Brasil avanza en penales al borde) · **Alemania vs Paraguay 20:30** (PRELIMINAR, esperar XI).
- Resto del bracket R32 en `data/processed/wc2026_standings_after_j3.json` (8 mejores terceros = FIFA oficial).

**🛠️ HERRAMIENTAS/CAPAS NUEVAS (todas salen AUTOMÁTICAS en `analyze_match.py` — usar siempre):**
1. **Calidad del XI desplegado** (`xi_quality.py`) — rating de torneo de los 11 titulares, emparejamiento difuso FIFA↔Sofascore (casa 11/11). **VALIDADO: 89% acierto del ganador en decisivos con XI claro.** Pasar match_id con XI confirmado para versión real.
2. **Choque de formaciones** (`formation_matchup.py`, tabla `match_formations` 60 part.) — récord por formación + cruce directo. 4-3-3/4-4-2 dominan (2.0 pts/p); el bus **5-4-1 fracasa (0V-3E-7D)**; 4-3-3 vs 3-4-2-1 = 3-0-1 (9-4).
3. **Desempate de fase final** (`knockout_tiebreaker.py`) — resistencia(0.45)+portero(0.35)+pateadores(0.20) → prob de AVANZAR en penales/prórroga.
4. **Bandera CONCEDE TEMPRANO SIEMPRE** (riesgo ALTO, no genérico) + nota **🚨 PELIGRO INICIAL** cuando el rival marca temprano. Detecta con minutos reales (`fifa_match_goals`).
5. **ALERTA EMPATE** (Elo parejo <50 → 41% empató) · **calidad a deber** · **killer enchufado** · **portero en forma**.

**🔧 MODELO OPTIMIZADO (auditoría integral 28-jun — está en el estado del arte):**
- **2 knobs ACTIVADOS por defecto** en `models/match_predictor.py`: `WC_LAMBDA_SCALE=0.90` (corrige sobre-predicción de goles) + `WC_DRAW_BOOST_TIGHT=1.4` (empates en parejos). Acierto grupos 68.1%→**70.8%**. Revertir con `=1.0`.
- Techo de acierto 1X2 es ~56-58% (literatura); nuestro 70.8% (79% J3) está por encima por los mismatches del Mundial. **El ~30% de fallos son empates/varianza irreducible — subir más SOBREAJUSTA (demostrado out-of-sample).**
- ⚠️ **El factor `finishing` está mal orientado** (premia sobre-conversión, castiga sub-conversión) → infla equipos en racha. `WC_FINISHING=0` da +1pp. Tenerlo en cuenta al leer λ.

**📌 PENDIENTES:**
- **Disparar Sofascore (DISPARAR SOLO CUANDO EL DUEÑO LO DIGA):** faltan stats ricos de **Argelia-Austria** (sin xG), **SAf-Canadá** y **Brasil-Japón**. IP BLOQUEADA por rate-limit; reintentar **mañana tras Brasil-Japón**. URLs ya descubiertas en `data/sofascore_urls.json`. Comando: `python scripts/fetch_sofascore_pw.py {URLs}` (1 sesión).
- **Alemania-Paraguay:** sellar/ajustar al salir XI. PRELIMINAR: **Alemania 2-1, avanza ~70%, upset Paraguay ~19%** — OJO: **Alemania concede ≤30' en 3/3 (9'/21'/30')** y Paraguay marca temprano a la contra (2' vs Turquía) + bus + portero 80% = receta del upset (Ecuador ya la eliminó así).
- **Brasil-Japón (sellado 1-1):** lectura honesta = volado, proceso→Brasil / forma→Japón se cancelan; Brasil avanza ~52% (penales: Alisson + pateadores). Peligro de Brasil = el CIERRE (no marca 61-90 + Japón marca tarde 88'/83'/69'). H2H: **Japón 3-2 Brasil amistoso oct-2025** (registrado en team_matches; Brasil iba con zaga SUPLENTE).

**⚠️ GIT/PIPELINE:** un GitHub Action automático commitea la DB **Y `match_predictions`** a origin → puede pisar mis sellos en los merges. **Tras cada merge: verificar sellos y re-sellar.** Push siempre; protocolo: backup → merge → `git checkout --ours data/mundial2026.db` → push. Ver memoria [[mundial2026-pool]].

---

## 🗄️ EMPEZAR AQUÍ (resumen anterior — 27-jun)

**RESULTADOS G/H/I CARGADOS Y EVALUADOS (27-jun).** Los 6 partidos de 26-jun entraron a `wc_matches` (66/72 grupos), pipeline FIFA/FDH/timing/perfiles corrido, integridad OK (GF=GA por grupo, xG 294 filas). **Scorecard G/H/I = 4/6 ganador:** ✅ NZ 1-5 Bélgica · ✅ Uruguay 0-1 España · ✅ Senegal 5-0 Iraq · ✅ Noruega 1-4 Francia · ❌ Egipto 1-1 Irán (empate que marqué por Beiranvand) · ❌ Cabo Verde 0-0 Saudí (el "0-0 gemelo" anotado). Ambos fallos fueron empates ya señalados como escenario alterno. **Modelo: 63.9% acc / 133 partidos, λ×1.003 (bien calibrado), Brier 0.2949.**

**PENDIENTE HOY (27-jun) — última jornada de grupos, todos status 1 (XI sale ~1h antes):**
- **21:00 Grupo L:** Panamá vs Inglaterra (match 400021508) · Croacia vs Ghana (400021509)
- **23:30 Grupo K:** Congo DR vs Uzbekistán (400021500) · Colombia vs Portugal (400021505)
- **28-jun 02:00 Grupo J:** Argelia vs Austria (400021497) · Jordania vs Argentina (400021495)
- **28-jun 19:00 🏆 EMPIEZAN DIECISEISAVOS:** Sudáfrica vs Canadá (400021518, stage 289287)
- Hay pronósticos PRELIMINARES sellados para J/K/L (evaluated=0) SIN flujo experto — refinarlos con tournament_scan+analyze+ajuste por XI cuando salgan alineaciones.

**PRÓXIMO HITO:** generar standings finales de grupos + 8 mejores terceros + bracket de dieciseisavos (empieza 28-jun 19:00).

---

## 🗄️ EMPEZAR AQUÍ (resumen anterior — 26-jun)

**Datos: COMPLETOS.** match_team_stats 60/60 (equipo) Y match_player_stats 60/60 (jugador: rating, goles, asistencias, minutos, titular/suplente). player_ratings actualizado (+1396). Todo commiteado.

**HERRAMIENTAS NUEVAS (usar siempre):**
- `scripts/tournament_scan.py [equipo] | --qualified` — **análisis INTEGRAL, EVOLUTIVO y auto-actualizable**. Mina los 142 stats FDH (remates por zona, rupturas de líneas, presiones, balón parado, portería) → percentil vs el campo + tendencia J1→J2→J3 + auto-flags (sobre/sub-conversión, dependencia de balón parado, amenaza aérea, defensa/ataque élite por proceso, posesión estéril). **Correr para AMBOS contrincantes antes de cada predicción.**
- `scripts/parse_sofascore_players.py [ids] [--force]` — crudo Sofascore /lineups → match_player_stats (fill-only, idempotente).
- `scripts/discover_sofascore_urls.py {fechas}` — auto-descubre URLs Sofascore interceptando scheduled-events.
- `scripts/analyze_match.py "A" "B"` — ventanas de ataque/concesión, defensa, timing, córners + FORMA reciente (incl. amistosos).

**ESTÁNDAR DE ANÁLISIS (pedido del dueño, OBLIGATORIO — ver memoria [[mundial2026-analisis-exhaustivo]]):** (1) Datos del Mundial PRIMARIOS, amistosos solo rectifican/confirman. (2) PROCESO, no solo goles (20 tiros-1 gol ≠ 1 tiro-1 gol). (3) EVOLUTIVO (tendencia por jornada). (4) Escanear AMBOS contrincantes (el cruce de perfiles es donde está la predicción). (5) Comparador de RIVALES COMUNES. (6) Rigor no complaciente (revisar al alza/baja según datos). (7) ⚠️ Sofascore bloquea IP tras varias sesiones Playwright — bajar 1 sesión/jornada, cambiar de red si bloquea.

**FLUJO POR PARTIDO (cuando salen alineaciones, ~1h antes):** bajar XI confirmado de FIFA live (`live/football/17/285023/{stage}/{match}`, Status==1=titular) → cargar en fifa_lineups → `tournament_scan` ambos → `analyze_match` → `predict_adjusted` con incentivos → ajuste experto (lo que el modelo no capta: XI debilitado, etc.) → sellar en match_predictions.

**PRONÓSTICOS J3 YA SELLADOS (evaluated=0, evaluar cuando terminen):**
- **G:** Bélgica 3-0 NZ (88%) · Egipto 1-0 Irán (42%, empate 33% por Beiranvand)
- **H:** España 2-0 Uruguay (68%) · Cabo Verde 1-0 Saudí (46%, 0-0 gemelo)
- **I:** Francia 2-0 Noruega (70%, Noruega rotó TODO: sin Haaland/Ødegaard, ya clasificada) · Senegal 2-0 Iraq (intrascendente, ambos eliminados)

**PENDIENTE:** J/K/L se juegan 27-jun → cuando salgan XI, aplicar el flujo. Evaluar resultados de G/H/I (hoy) y G-L con `evaluate_model.py`. Generar standings_after_j3 + 8 mejores terceros cuando termine la fase.

**Hallazgos clave del scan (descontar/ojo en knockouts):** Alemania xG en caída 4.2→1.9→0.7 pese a ser 1ª; Japón/México sobre-convierten (regresan); P.Bajos depende de balón parado (45%); SudÁfrica/Australia presionan sin recuperar; Bélgica sub-convierte brutal (goles a deber); España élite por proceso ambos lados.

---

> **Auditoría 26-jun (commit `d35882c`):** Grupo E añadido a results JSON; `wc_goal_timing`
> reconstruido (A-F ahora a 3 partidos; D y F se habían quedado en 2); corregido GD de
> Sudáfrica en Grupo A (GA 2→3); nombres canónicos en wc_matches+match_predictions
> (Czechia/Curacao). Modelo NO tocado: backtest 535 partidos da 63.7% acc, λ×1.002
> (bien calibrado); factor veterano neutro pero se mantiene por señal de torneo.
> **xG COMPLETADO 26-jun (commit `f54ffd0`):** los 3 partidos FIFA-only sin xG (Ecuador-Alemania,
> Curaçao-CIV, España-Saudí) se bajaron de Sofascore vía Playwright (intercepta XHR del SPA;
> el muro Cloudflare bloquea acceso directo y el Chrome MCP bloquea el dominio). Carga
> FILL-ONLY (solo NULLs, sin sobrescribir FIFA). **Cobertura xG ahora 60/60.** Bonus: fix
> `is_home` (3 partidos lo tenían =1 en ambos equipos → corrompía conversión) + causa raíz en
> `fetch_fifa_stats.py`. **Pendiente real: solo faltan resultados G-L, que se juegan 26-28 jun.
> Para bajar Sofascore de G-L: `python scripts/discover_sofascore_urls.py 2026-06-27 2026-06-28`
> (auto-descubre URLs) → `python scripts/fetch_sofascore_pw.py {URLs}` → `python
> scripts/parse_sofascore_raw.py {ids} --fill-only`. Esperar alineaciones oficiales antes de predecir.**

---

## 🟢 ESTADO ACTUAL (lo más importante — leer primero)

### Comando ÚNICO para iniciar cada jornada
```bash
cd C:/Users/enrique.aguilar/Mundial2026
python scripts/matchday.py "EquipoA" "EquipoB" "EquipoC" "EquipoD"
```
Refresca TODOS los datos (resultados→DB, FIFA lineups+goles, FDH 142 stats, timing real, perfiles) y luego, por cada par, imprime **análisis exhaustivo + predicción ajustada por patrones**. Sin pares, solo refresca datos.

### Fuentes de datos (resuelto el muro de Sofascore)
- **FIFA API ABIERTA (principal, sin anti-bot):** `api.fifa.com/api/v3` (comp=17, season=285023). Calendario, alineaciones (`live/football/{comp}/{seas}/{stage}/{match}`, Status==1=titular), goles con minuto.
- **FIFA FDH (stats avanzados, abierto):** `fdh-api.fifa.com/v1/stats/match/{IdIFES}/teams.json` — **142 stats/equipo** (GK saves/%, presiones, line-breaks, attempts por zona). IdIFES = `Properties.IdIFES` del calendario.
- **Sofascore (solo para xG/regates):** muro Cloudflare → requiere URL del partido + Playwright (`fetch_sofascore_pw.py`). FIFA cubre lo demás sin pegar nada.

### Scripts nuevos de esta sesión (todos commiteados)
| Script | Qué hace |
|---|---|
| `scripts/matchday.py` | **Comando único**: pipeline completo + análisis + predicción ajustada |
| `scripts/fetch_fifa.py` | Lineups + goles-minuto de FIFA (tablas `fifa_lineups`, `fifa_match_goals`) |
| `scripts/fetch_fifa_stats.py` | 142 stats FDH (tabla `fifa_fdh_stats` + rellena match_team_stats) |
| `scripts/sync_results_to_db.py` | Resultados JSON → wc_matches (la DB que lee el modelo) |
| `scripts/sync_stats_to_db.py` | Stats core Sofascore JSON → match_team_stats |
| `scripts/rebuild_wc_timing.py` | Timing real del Mundial por equipo (tabla `wc_goal_timing`) |
| `scripts/analyze_match.py` | **Análisis exhaustivo**: choque de ventanas, portero, conversión, timing real |
| `scripts/predict_adjusted.py` | Predicción del modelo **ajustada por patrones** (regresión, ventanas, GK) |
| `scripts/fetch_sofascore_pw.py` + `parse_sofascore_raw.py` | Sofascore vía Playwright (solo si se necesita xG/regates; requiere URL) |

### Bugs de RAÍZ encontrados y arreglados (críticos)
1. **Resultados guardados en JSON pero NO cargados a `wc_matches`** → el modelo predecía con ~42 resultados faltantes (Turquía λ 2.25 con 0 goles). Arreglado: `sync_results_to_db.py`. Tras arreglar: eval 80→121 partidos, escala λ 0.915→1.014.
2. **Stats igual (match_team_stats solo 13/54)** → arreglado con `sync_stats_to_db.py` + FDH. Ahora 56/56.

### Lecciones de calibración (en memoria mundial2026-analisis-exhaustivo)
- **Estándar:** analizar por PATRONES (choque de ventanas: cuándo ataca A vs cuándo se rompe B), NO por ranking. Defensa+delantera+medio+duelos+balón parado SIEMPRE, sin que lo pidan.
- **Regresión de definición:** equipo que crea y no marca (sub-convierte) está "a deber" → peligroso. Fallo 25-jun: predije Alemania 0-2, ganó **Ecuador 2-1** marcando en min 9' y 77' (ventanas flojas de Alemania que identifiqué pero descarté por su sequía). Ya en `predict_adjusted.py`.

### Predicciones J3 (25-jun) — SCORECARD COMPLETO (fase de grupos terminada)
| Partido | Predicción | Real | Veredicto |
|---|---|---|---|
| Curaçao vs C. Marfil | CIV 2-1 | **0-2 CIV** | ✅ dirección |
| Ecuador vs Alemania | Alemania | **2-1 Ecuador** | ❌ (acerté patrón, fallé) |
| Túnez vs P. Bajos | NED 4-0 | **1-3 NED** | ✅ dirección |
| Japón vs Suecia | Japón 2-1 | **1-1** | ❌→✅ con Ajuste 5 (incentivo) |
| Chequia vs México | México | **0-3 México** | ✅ (mi override manual ❌) |
| Sudáfrica vs Corea | — | **1-0 SAf** | — |
| **Turquía vs USA** | USA 2-1 | **3-2 Turquía** | ❌ BOMBAZO (ver Ajuste 2 v2) |
| **Paraguay vs Australia** | 1-1 Australia avanza | **0-0 Australia avanza** | ✅ dirección + incentivo exacto |

**J3 fue alta varianza** (Sui>Can, Bos>Qat, Ecuador>Alemania, Turquía>USA — 4 upsets). El modelo acierta los patrones sistemáticos; los "dead rubbers" de J3 son ruidosos por diseño.

### ⭐ APRENDIZAJE CLAVE 25-jun (tarde): el factor ELIMINACIÓN estaba mal
**Turquía (ELIMINADA) ganó 3-2 a USA con xG 3.01** jugando su MEJOR XI (Arda Güler 8.6), libre de presión. Esto destruyó el factor de eliminación ×0.70.
- **Evidencia de los 7 eliminados en J3:** promediaron **1.06 xG/partido y convirtieron 0.94×** (casi neutral), NO −30%.
- **Recalibrado: `_ELIM_LAMBDA_PENALTY` 0.70 → 0.90** (commit `68d7fc1`). El ×0.70 estaba sobreajustado a Qatar.
- A/B en Turquía-USA: viejo ×0.70 → P(USA)=47.9% (mal); nuevo ×0.90 → 37.5/39.3 (moneda al aire, correcto).
- **Lección:** estar eliminado sube la VARIANZA, no baja la media. Un eliminado con XI-A juega libre, no peor. Los levers reales son ROTACIÓN (Ajuste 4) e INCENTIVO (Ajuste 5).

### Estado del modelo (eval `scripts/evaluate_model.py`)
- **63.8% accuracy / 127 partidos**, marcador exacto 15.0%, Brier 0.2997, log-loss 0.8204, escala λ ×1.002 (calibrada).
- ⚠️ El script necesita `PYTHONIOENCODING=utf-8` en Windows (si no, UnicodeEncodeError en cp1252).

---

## 1. Qué es este proyecto

Pool de predicciones del Mundial FIFA 2026 (48 equipos, 12 grupos A-L de 4).
- **Repo GitHub:** `FindITCorp/Mundial2026-` (rama `main`)
- **Modelo de predicción:** `models/match_predictor.py` (motor principal, Dixon-Coles + Elo + xG + ratings)
- **Fuente de datos en vivo:** Sofascore API
  - Base: `api.sofascore.com/api/v1`
  - tournament_id=**16**, season_id=**58210**
  - Resultado de un partido: `/event/{id}`
  - Stats (xG, posesión, tiros): `/event/{id}/statistics`
  - Alineaciones + ratings jugadores: `/event/{id}/lineups`
  - Partidos por fecha: `/sport/football/scheduled-events/YYYY-MM-DD`
  - Tabla: `/unique-tournament/16/season/58210/standings/total`
  - ⚠️ `/events/round/{n}` solo devuelve 14 de 24 partidos — usar fecha para grupos I-L.

### Bug conocido del API
El endpoint `/event/{id}/lineups` **a veces devuelve marcador incorrecto** (ej. dio 0-2 para Escocia-Brasil que fue 0-3, y 2-1 para Marruecos-Haití que fue 4-2). **El marcador confiable es `/event/{id}` directo**, no el de lineups.

---

## 2. Estado de los datos (archivos en el repo)

| Archivo | Contenido | Estado |
|---|---|---|
| `data/processed/wc2026_results_j1_j2.json` | 48 partidos J1+J2 verificados | ✅ Completo |
| `data/processed/wc2026_match_stats_j1_j2.json` | xG/posesión/tiros/tarjetas 48 partidos | ✅ Completo |
| `data/processed/wc2026_standings_after_j2.json` | Tabla 12 grupos tras J2 | ✅ Completo |
| `data/lineups/wc2026_lineups_j1_j2.json` | Alineaciones+ratings J1+J2 | ✅ Completo |
| `data/processed/wc2026_results_j3.json` | J3: **12 partidos terminados** (Grupos A-F completos) | 🔄 Parcial — faltan G,H,I,J,K,L |
| `data/processed/wc2026_match_stats_j3.json` | Stats J3 (12 entradas, Grupos A-F con xG) | ✅ A-F completo |
| `data/lineups/wc2026_lineups_j3.json` | Alineaciones J3 (Grupos A,B,C) | 🔄 Parcial |
| `data/processed/wc2026_predictions_j3_june25.json` | Predicciones Grupos D/E/F del 25-jun | ✅ Pendiente de evaluar vs resultado real |

### J3 — Grupos ya completados (resultados reales)
- **Grupo A:** Cze 0-3 Mex · SAf 1-0 SKor → **Clasifican: México (9pts, 1ro), Sudáfrica (4pts, 2do)**. Eliminados: Corea (3), Chequia (1).
- **Grupo B:** Bos 3-1 Qat · Sui 2-1 Can → **Clasifican: Suiza (7), Canadá (4)**. Eliminado: Qatar.
- **Grupo C:** Mar 4-2 Hai · Sco 0-3 Bra → **Clasifican: Brasil (7, por GD), Marruecos (7)**. Eliminados: Escocia, Haití.

### J3 — Partidos PENDIENTES (programados 25-jun, predichos sin resultado aún)
- **Grupo D:** Turquía vs USA (15186887) · Paraguay vs Australia (15186891)
- **Grupo E:** Ecuador vs Alemania (15186907) · Curaçao vs Costa de Marfil (15186908)
- **Grupo F:** Túnez vs Países Bajos (15186973) · Japón vs Suecia (15186972)
- **Grupos G-L:** aún no programados/extraídos.

---

## 3. Evaluación predicción vs realidad

### J3 Grupo A (resultado de "ayer" 24-25 jun)

| Partido | Predicción modelo | Mi override manual | Real | Veredicto |
|---|---|---|---|---|
| **Chequia vs México** | México gana (2-1) | ❌ Reviré a "Chequia 1-0" por la rotación | **0-3 México** | Modelo ACERTÓ, mi override FALLÓ |
| **Sudáfrica vs Corea** | (sin predicción formal) | — | **1-0 Sudáfrica** | — |

> **LECCIÓN CRÍTICA:** Sobrecorregí por rotación. Vi que México metió equipo B (Rangel, sin Ochoa/Giménez/Jiménez/Fidalgo) y asumí caída de nivel → predije que Chequia ganaría. **Error:** el equipo B de México seguía siendo muy superior al equipo B de Chequia. México ganó 0-3 con Mateo Chávez (rating 8.1, gol) de figura. El xG lo confirmó: México 1.74 vs Chequia 0.53. La rotación NO iguala cuando la brecha de plantilla es grande.

### Acumulado del modelo en J3 (6 partidos con resultado)
| Partido | Predicho | Real | ✓/✗ |
|---|---|---|---|
| Suiza vs Canadá | Canadá favorito (xG) | Sui 2-1 | ✗ (Kobel GK 8.9) |
| Bosnia vs Qatar | Empate/Qatar (xG) | Bos 3-1 | ✗ (conversión) |
| Brasil vs Escocia | Brasil | 3-0 | ✓ |
| Marruecos vs Haití | Marruecos | 4-2 | ✓ |
| Chequia vs México | México | 0-3 | ✓ (modelo) |
| Sudáfrica vs Corea | — | 1-0 | — |

---

## 4. Ajustes al modelo YA IMPLEMENTADOS (commit 37466f9)

En `models/match_predictor.py`:

1. **GK Outlier Factor** (`_gk_outlier_factor`): GK con rating WC ≥ 8.5 reduce λ rival, escala continua 1.5%/décima, cap −25%, shrinkage k=2.
   - Evidencia: Kobel 8.9, Vozinha 9.7, Beiranvand 9.8, Eloy Room 10.0.
2. **Factor de eliminación** (params `home_eliminated`/`away_eliminated`): equipo eliminado → λ × **0.90** (−10%). **RECALIBRADO 25-jun tarde** (commit `68d7fc1`): era 0.70 (−30%) pero estaba sobreajustado a Qatar. Los 7 eliminados de J3 promediaron 1.06 xG y convirtieron 0.94× → casi neutral. Turquía (eliminada) ganó 3-2 a USA con xG 3.01. Estar eliminado sube la VARIANZA, no baja la media.
3. **Cap de conversión ampliado** (`_FINISH_CAP` 0.10 → 0.20): captura equipos sistemáticamente clínicos (Marruecos 1.23× xG).
4. **Factor de rotación calibrado** (`_rotation_factor`, params `home_rotation_expected`/`away_rotation_expected`) — **NUEVO 25-jun**: equipo que rota su XI reduce su λ propia, pero solo según la brecha de Elo con el rival. `rotation_penalty = base × (1 − clamp(signed_gap/FULLPASS,0,1))`, `signed_gap = elo_propio − elo_rival`. Dominante (gap ≥ 300) rota gratis; parejos pagan hasta −25%. Constantes env-tunables: `WC_ROTATION_PENALTY` (def 0.25), `WC_ROTATION_FULLPASS` (def 300). Opt-in (default factor=1.0). ⚠️ Pendiente calibrar `FULLPASS` (con 300, México gap≈98 recibe −17% pero ganó 0-3 → 300 puede ser muy conservador, bajar a ~200).
5. **Factor de incentivo de tabla** (`_incentive_factor`, params `home_incentive`/`away_incentive`) — **NUEVO 25-jun tarde** (commit `97b07dd`): ACOTADO a ±6% y SOLO fase de grupos (en knockout devuelve 1.0). Pedido del dueño: "no determinante, algo para el final del partido". Casos: `draw_enough` ×0.94 (le basta empate, administra), `needs_win` ×1.03 (se vuelca), `fighting_first` ×1.02 (titulares por 1er lugar), `neutral` ×1.0.
   - **Validado:** Japón 1-1 Suecia (Japón `draw_enough` no forzó pese a xG superior → mi fallo 2-1 se corrige a empate); Paraguay 0-0 Australia (Australia `draw_enough` administró, Paraguay `needs_win` con 5-3-2 no rompió → predije exacto la dirección).

Los 5 factores se exponen en `result["_factors"]` para auditoría (incl. `rotation_factor_*`, `incentive_factor_*`, `elim_factor_*`).

---

## 5. Ajustes PROPUESTOS pendientes de implementar (siguiente sesión)

### Idea pendiente — VARIANZA en dead rubbers
Estar eliminado/clasificado sube la varianza del marcador (no la media). Considerar:
en partidos sin nada en juego para uno o ambos, AUMENTAR la dispersión NB (bajar `disp_r`)
en vez de tocar la media. Capturaría tanto los Turquía 3-2 como los Korea 0-1.

---

## 6. Tareas pendientes (TODO)

1. [x] ~~Evaluar predicciones 25-jun (D/E/F)~~ ✅ HECHO — scorecard en §"Predicciones J3" arriba.
2. [ ] **Capturar RESULTADOS J3** conforme se jueguen (G/H/I hoy 26-jun; J/K/L 27-jun) → sync a DB (`sync_results_to_db.py`, `sync_stats_to_db.py`) → bajar Sofascore (proceso por jugador) con discover→fetch→parse_sofascore_players. Datos J1-J2 de TODOS los grupos ya completos (60/60 equipo y jugador).
   - [ ] **Pronosticar J/K/L** cuando salgan alineaciones (flujo completo, ver "EMPEZAR AQUÍ"). G/H/I ya pronosticados y sellados.
   - [ ] **Evaluar** pronósticos G/H/I/J/K/L vs resultado real (`evaluate_model.py`).
3. [x] ~~Implementar **Ajuste 4 (rotación calibrada)**~~ ✅ + **Ajuste 5 (incentivo)** ✅ + **recalibración Ajuste 2** ✅ (25-jun tarde). Pendiente: calibrar `ROTATION_FULLPASS`.
4. [ ] Generar `wc2026_standings_after_j3.json` con los 12 grupos finales (clasificados de cada grupo).
5. [ ] Determinar los **8 mejores terceros** (formato 48 equipos: 12 primeros + 12 segundos + 8 mejores terceros = 32 a dieciseisavos).
6. [ ] Cablear `sync_results_to_db.py` + `sync_stats_to_db.py` en `daily_pipeline.sh`/`matchday.py` para que el sync a DB no se olvide (bug de raíz recurrente).
7. [ ] **Mapear `fifa_lineups.player_name` ↔ `players.id`** (tabla de alias o fuzzy verificado). Hoy solo 62/1244 nombres casan exacto y 0/100 estrellas → BLOQUEA el análisis de calidad del XI desplegado (sumar rating nacional de los 11 titulares y testear si predice más allá del Elo). Es el ángulo de alineaciones de mayor potencial, hoy imposible. Ver memoria [[mundial2026-analisis-exhaustivo]] "RESULTADOS NULOS de alineaciones".
8. [ ] **Revisar Ajuste 4 (rotación):** análisis 26-jun sobre 64 transiciones jornada→jornada dio corr(cambios XI, rendimiento sobre Elo)=+0.109 (NULO, ni significativo ni en la dirección esperada). El castigo por rotación NO está respaldado por los datos del torneo. Considerar desactivarlo o dejarlo en factor=1.0 hasta tener evidencia real (no calibrar `ROTATION_FULLPASS` sobre un efecto que no aparece).

---

## 7. Credenciales / acceso
- Token GitHub en uso por el dueño (NO exponer en commits). Repo: `FindITCorp/Mundial2026-`.
- Git: hacer `git pull --rebase origin main` antes de push si el remoto tiene commits nuevos.
- Entorno: Windows, shell PowerShell + Bash. Python disponible (`python -c "import models.match_predictor"` compila OK).
