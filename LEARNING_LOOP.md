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

## Métricas que perseguimos (medidas, no inventadas)
- **Ganador/avance:** 67% actual → objetivo ~75-80% (knockout con favoritos claros).
- **Marcador exacto:** ~15% actual → romper el techo convencional (~20%) con micro-datos.
- Se miden en `calibration_ledger` tras CADA ronda. Si una señal no sube el ledger, se descarta.

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
