# 🔁 LEARNING LOOP — motor de mejora continua del pool Mundial 2026

> **Filosofía (dueño, 01-jul):** loop constante, siempre acercándonos. No nos conformamos
> con resultados fallados, ni con imposibles, ni con el techo. Buscamos romper paradigmas.
> **Regla honesta:** perseguimos el frontier (datos que otros no usan), medimos el progreso
> en `calibration_ledger`, y no cantamos números que no podemos sostener.

## El ciclo (cada partido / cada ronda)
1. **PREDECIR** con el flujo integral obligatorio:
   `simulate_match` (forense gol-por-gol + ventanas + Monte Carlo) → `scoreline_ground`
   (registros de gol/concesión) → **XI real** → factores que emergen → `predict_ensemble`
   (consenso + tope de tanda + banderas) → sellar.
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
