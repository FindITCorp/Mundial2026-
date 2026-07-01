# 🔁 LEARNING LOOP — motor de mejora continua del pool Mundial 2026

> **Filosofía (dueño, 01-jul):** loop constante, siempre acercándonos. No nos conformamos
> con resultados fallados, ni con imposibles, ni con el techo. Buscamos romper paradigmas.
> **Regla honesta:** perseguimos el frontier (datos que otros no usan), medimos el progreso
> en `calibration_ledger`, y no cantamos números que no podemos sostener.

## El ciclo (cada partido / cada ronda)
1. **PREDECIR** con el flujo integral obligatorio:
   `simulate_match` (forense gol-por-gol + ventanas + Monte Carlo) → `scoreline_ground`
   (registros de gol/concesión) → **XI real** → factores que emergen → `predict_ensemble`
   (consenso + tope de tanda + banderas) → sellar → **`validate_predictions.py --fix`
   (GATE OBLIGATORIO, nace 01-jul tras encontrar el MISMO bug de consistencia
   marcador↔ganador en Bélgica-Senegal Y en Australia-Egipto el mismo día — la
   revisión manual no lo cazó las dos veces, un validador automático sí). Nunca
   presentar/cerrar un sello sin correrlo.**
2. **OBSERVAR** el resultado real (bajar de FIFA, registrar).
3. **DIAGNOSTICAR EL FALLO** — no "fallé", sino ¿QUÉ señal lo habría cazado? (abajo).
4. **ENCODAR** esa señal como herramienta/knob y **medir** en `calibration_ledger` si sube.
5. **REPETIR** — cada resultado entra como contexto del siguiente (autoregresivo).

## Bitácora de aprendizaje (fallo → causa → señal añadida)
| Fallo | Causa raíz | Señal/herramienta que nació |
|---|---|---|
| Alemania-Paraguay (sellé 71%, cayó en penales) | confundí "gana en 90'" con "avanza"; tanda = volado | `predict_ensemble`: TOPE DE TANDA + banderas tácticas |
| CIV-Noruega (sellé CIV, ganó Noruega) | pisé la señal de proceso con criterio | `regression_check` + `calibration_ledger` (regla: deferir en grupos, experto en knockout) |
| México (bajé 2-1→volado, ganó 2-0) | sobre-hedgeé un favorito claro con localía | lección: no diluir favoritos claros a 50/50 |
| "England 2-0 Congo" | no fundamenté el marcador en lo que Congo CONCEDE (exacto 1) | `scoreline_ground` |
| "gana el favorito" superficial | no usé la forense gol-por-gol ni simulé escenarios | `simulate_match` (Monte Carlo + ventanas) |
| sub-predicción de goles (1.86 vs 2.83) | knob λ mal calibrado tras evolucionar el torneo | `WC_LAMBDA_SCALE` 0.90→1.10 (exacto 12→15%) |
| Bélgica-Senegal sellado 2-2 (el dueño lo cazó: "no parecen muchos goles") | el marcador venía de `scoreline_ground` (heurístico de promedios GF/GA) sin validarlo contra el top-6 real de `simulate_match` — el 2-2 NO aparecía en ese top-6, y además contradecía el campo ganador=Bélgica (un empate no puede tener "ganador" en 90') | corregido a 2-1 (sí está en el top-6). Auditados los otros 7 sellos del día: todos ya estaban dentro de su propio top-6 — regla nueva: SIEMPRE cruzar el marcador final contra el top-6 de `simulate_match` antes de sellar, no solo contra `scoreline_ground` |
| El dueño desconfió tras el fallo de Bélgica ("siempre hay algo que se te olvida... no se automejora") — con razón: la revisión de Bélgica fue MANUAL, ad-hoc, no sistemática | validar "cuando se pregunta" en vez de SIEMPRE, para TODOS los partidos, no solo el que se señaló | **`scripts/validate_predictions.py`** — gate automático que corre en TODA la tabla `match_predictions` (probs suman 1, marcador↔ganador coherente, marcador↔goles coherente, marcador dentro del top-8 de `simulate_match`). Al correrlo sobre TODO encontró el MISMO bug en **Australia-Egipto** (nadie lo había visto) — corregido con `--fix` sin que el dueño tuviera que señalarlo. Distingue el pipeline automático (GitHub Action, `predict_upcoming.py`: winner=argmax 1X2 agregado, scoreline=argmax del grid Dixon-Coles — DIVERGEN por diseño, verificado leyendo el código, no es bug ahí) de mis sellos expertos (ahí sí debe ser 100% coherente). Correrlo es ahora paso OBLIGATORIO del flujo, no opcional. |
| El dueño pidió re-evaluar Bélgica-Senegal antes del kickoff y "considerar cosas nuevas que validar/ajustar" cada partido | al re-correr TODO el flujo con lupa aparecieron DOS gaps más del MISMO patrón de hoy (dato real ya cargado pero no conectado): `analyze_match.py` seguía usando XI "proxy J1" para la calidad del XI y formación "predominante" de grupos, AUNQUE ya había XI real confirmado en `fifa_lineups` para el partido de HOY (proxy J1 daba brecha XI +0.18, XI real daba +0.09; "predominante" daba 4-2-3-1 vs 4-2-3-1, la formación REAL era 4-3-3 vs 3-4-3) | Fix en `analyze_match.py`: auto-detecta el match_id con lineup real más reciente entre los dos equipos y lo usa para AMBAS señales — calidad de XI (`xi_quality.xi_rating(match_id=...)`) y formación real (nueva `_derive_formation()`, cuenta def/med/del por `position`). Si no hay XI real, cae al comportamiento anterior sin romper nada (verificado: Spain-Austria sin XI usa fallback; England-Congo y Bélgica-Senegal con XI usan datos reales). `validate_predictions.py --all` sigue OK. |
| England 1-0 sellado → real 2-1 (Congo marcó primero al 7', England remontó 75'/86') | BUG REAL en `_window_clash()` (analyze_match.py): usaba el timing HISTÓRICO (amistosos/clasificatorios) para decidir AMENAZA REAL/NEUTRALIZADA, ignorando `wc_goal_timing` (datos REALES de este Mundial, ya cargados y marcados "prioritario" en el código pero nunca conectados a esta función). Dijo "DR Congo aguanta bien 76-90" con datos viejos; con datos reales del Mundial, Congo SÍ concedía tarde — y England anotó ahí. Nota: el ganador SÍ se acertó (sellado y modelo coinciden, ambos correctos en 1X2 vía `calibration_ledger`); el fallo fue solo de MARCADOR EXACTO y de narrativa táctica, no de dirección. | `_window_clash()` arreglado 01-jul: usa `wc_scored`/`wc_conceded` (Mundial real) si hay ≥2 goles de muestra, si no cae al histórico. Verificado en los 8 partidos de R32 pendientes: cambia la narrativa en varios casos (Spain-Austria, Portugal-Croatia, Australia-Egypt, Argentina-CapeVerde, Colombia-Ghana) pero NINGUNO requirió re-sellar el número — la narrativa de ventanas es color cualitativo, no alimenta la λ del Monte Carlo. |

**🎯 CORRECCIÓN DE ENFOQUE 01-jul — ESTIMAR, no esperar a evaluar en la marcha:** el dueño frenó una deriva real: "no podemos evaluar en la marcha, debemos estimar resultados basados en la simulación, sino no tiene sentido predecir." `team_lineup_sim.py`/`full_match_sim.py` requerían XI real del cruce (fallaban en partidos aún sin alineación, como USA-Bosnia antes del kickoff). Se generalizaron con `resolve_xi_source()`: sin XI real, cada equipo usa su último XI propio como proxy — la simulación se corre YA, no se espera. **USA-Bosnia sellado con esto (2-1 USA, avance ~66%) reveló que el modelo de producción (Dixon-Coles, 70%/11%/11% "CONFIANZA ALTA") está más sobreconfiado en este cruce que la simulación grounded en remates reales de jugadores (53-56%/18-20%/24-29%)** — pendiente de ver en `calibration_ledger` si la simulación jugador-por-jugada le gana al modelo de producción en desacuerdos como este.

## Métricas que perseguimos (medidas, no inventadas)
- **Ganador/avance:** 67% actual → objetivo ~75-80% (knockout con favoritos claros).
- **Marcador exacto:** ~15% actual → romper el techo convencional (~20%) con micro-datos.
- Se miden en `calibration_ledger` tras CADA ronda. Si una señal no sube el ledger, se descarta.

## 🆕 FRONTERA DESBLOQUEADA 01-jul — SIMULACIÓN JUGADOR vs DEFENSA (`scripts/player_matchup_sim.py`)

El dueño exigió, con razón, ir más allá del agregado de equipo: "simular cuántas oportunidades de gol tendría [ej. Kane], cuáles se convertirían, si la defensa lo permitiría" — no una promesa, una herramienta que funcione.

**Bloqueador que lo impedía (encontrado y resuelto):** los remates de `fifa_match_events` (type 12) tenían **0 de 1962 con nombre de jugador** — solo `player_fifa_id` sin resolver. Se descubrió que `api.fifa.com/api/v3/players/{id}` SÍ da el nombre → **`scripts/fetch_fifa_player_names.py`** cachea el mapeo (tabla `fifa_player_names`, 725 jugadores resueltos de una sola pasada). Con eso se puede reconstruir el registro de remates de CUALQUIER jugador.

**Modelo (`player_matchup_sim.py "Jugador" "Rival"`):** remates/90 y conversión PERSONALES del jugador (todo el Mundial) → ajustados por (a) cuánto tiro permite el rival vs el promedio del torneo, (b) `goals_prevented` del rival (arquero/defensa que conceden más de lo esperado por xG sube la conversión ajustada) → Monte Carlo de remates (Poisson) × conversión (Bernoulli) → distribución de goles del jugador en ESE partido.

**VALIDADO retrospectivamente (Harry Kane vs DR Congo, partido ya jugado, sin fuga vía `--exclude-match`):** modelo daba esperado 1.44 goles, P(≥1)=76.5%, P(2 goles)=24.4%. Real: **Kane marcó 2 goles de 5 remates** — cae dentro de la probabilidad del modelo (24.4%, no un resultado extremo), buena validación honesta (no un ajuste retroactivo perfecto, un resultado plausible dentro de la distribución).

**Probado hacia adelante:** Cristiano Ronaldo vs Croacia (Portugal-Croacia, R32 pendiente) → esperado 0.99 goles, P(≥1)=63%.

**LIMITACIÓN EXPLÍCITA (no se infla el dato):** (1) NO hay regates (dribbles) a nivel jugador en la base, solo agregado de equipo — el script lo etiqueta claro, nunca lo hace pasar por individual. (2) Con muestra chica (ej. Sadio Mané, 5 remates/0 goles) la conversión personal es MUY ruidosa — el modelo lo refleja (P(≥1)=4.9%) pero hay que leerlo con cautela, no como oráculo. (3) El perfil defensivo del rival se restringió a partidos de Mundial (group/R32) — se encontró que mezclaba amistosos de otro nivel, corregido antes de reportar.

**Pendiente de siguiente sesión:** correr `--fix`/backtest contra MÁS jugadores decisivos (Messi, Mbappé, Haaland) para ver si el patrón de validación se sostiene con n>1; conectar la salida a `predict_ensemble`/`analyze_match` si se confirma que aporta señal más allá de lo agregado.

**🆕 CIERRE DEL PENDIENTE + SIMULACIÓN COMPLETA DESDE EL KICKOFF (01-jul, `scripts/full_match_sim.py`):** el dueño pidió "una simulación real desde el primer movimiento de pelota" con los datos de jugadores. Antes de construirla se cerró el pendiente declarado la vez anterior (Senegal 2.68 vs 1.67 de goles esperados sumando individuales): **fix de ANCLAJE** en `team_lineup_sim.py` — la suma individual se reescala (factor único por equipo) para que cuadre EXACTO con el λ de `simulate_match` (más validado, 68% acierto de ganador), preservando la proporción relativa entre jugadores (quién es más peligroso que quién no cambia). `full_match_sim.py` simula MINUTO A MINUTO: cada jugador de medio/ataque tira una moneda cada minuto con su tasa de remates/90 (volumen crudo, ajustado por rival) y, si remata, otra con su conversión ANCLADA (goles/remate reescalado) para decidir gol/parada/fuera — genera un relato jugada-por-jugada real, y valida que 2000 corridas agregadas promedian goles ≈ λ de equipo (Bélgica 1.96≈2.00, Senegal 1.69≈1.67 — cuadra). Nota curiosa: una corrida al azar (semilla arbitraria) dio Bélgica 0-2 Senegal, el marcador real del partido en curso esa noche — coincidencia, no predicción, pero valida que el motor genera resultados realistas.

**🆕 EXTENSIÓN 01-jul — TODO EL XI, no un jugador (`scripts/team_lineup_sim.py`), pedido del dueño ("no es un solo jugador, es todos los delanteros, todo el mediocampo, todo el juego"):** corre `player_matchup_sim` para cada jugador de medio(2)/ataque(3) del XI real de AMBOS equipos, y SUMA — con un chequeo de consistencia nuevo: cruzar la suma individual contra el λ de equipo de `simulate_match` (algo que nunca se había comprobado). **Al correrlo sobre Bélgica-Senegal salió un bug real de inmediato:** la suma de Senegal daba **4.27 goles esperados vs 1.67 del modelo de equipo** — Ndiaye y Diarra con 1G/2 tiros (50% conversión) proyectaban una tasa irreal de un solo gol de suerte. **Fix: shrinkage bayesiano** en `player_shot_profile()` — conversión = (goles + k·prior)/(tiros + k), prior=conversión global del torneo (~11.9%), k=8. Muestra chica se acerca al promedio, muestra grande (Kane, n=18) casi no se mueve. Tras el fix: Bélgica suma 2.11 vs modelo 2.00 (cuadra bien); **Senegal sigue algo alto, 2.68 vs 1.67 (diferencia -1.02, no resuelta del todo)** — probablemente el descuento por la defensa élite de Bélgica no pega tan fuerte a nivel individual como en el λ de equipo; queda como pendiente honesto, no oculto.

## Fronteras a explorar (romper paradigmas — pendientes, con hipótesis medible)
- **Modelo de HAZARD por minuto (`scripts/hazard_model.py`, prototipado 01-jul) — RESULTADO: NULO, no se activa.**
  Hipótesis original: Senegal (y otros) "colapsan en OLEADAS" (43'/48'/58' vs Noruega) —
  un Poisson plano no lo captura, un proceso auto-excitante (Hawkes: conceder sube el
  riesgo de volver a conceder) sí. **Test 1 (`--test`): FALSEADO.** Se compararon los 106
  huecos reales entre goles-encajados-consecutivos-del-mismo-equipo contra 10000 sims de
  "mismos N goles colocados al azar en 90'" — fracción real de huecos ≤15' = 0.453,
  esperado por azar = 0.471 (CI90 [0.406,0.538]), p=0.70. **El patrón Senegal es varianza
  normal de un proceso plano, no derrumbe sistemático — a nivel torneo NO hay auto-
  excitación real.** **Test 2 (`--backtest`): la alternativa más floja (peso numérico por
  "choque de ventanas" en vez de auto-excitación) mejoraba Brier IN-SAMPLE (0.4466→0.4355)
  pero se REVIRTIÓ bajo leave-one-out (0.6142→0.6247, empeora) — la mejora era overfitting
  a la propia muestra (3 partidos/equipo de grupos es muy poco para 6 buckets).**
  **CONCLUSIÓN: no activar. Frontera con la hipótesis original cerrada (no hay auto-
  excitación); la versión más floja queda ABIERTA pero bloqueada por tamaño de muestra —
  re-intentar con más partidos acumulados (post-Mundial completo, o históricos de otros
  torneos vía StatsBomb) antes de reintentar el peso por ventanas.** El choque de ventanas
  SIGUE siendo útil como señal CUALITATIVA (ya integrada en `analyze_match.py`), solo no
  como ajuste numérico de λ.
- **Matchups jugador-vs-jugador:** Wissa vs los laterales suplentes de England — predecir
  goles por quién marca a quién, no por agregados de equipo. Datos: ratings + XI real.
- **Condicionar por ESTILO del rival** (bus / press / contra) no solo por Elo. Datos: FDH
  (presiones, líneas) + `match_formations`.
- **Ensemble con pesos APRENDIDOS** del ledger (autoregresivo): reponderar señales por su
  acierto reciente ronda a ronda.
