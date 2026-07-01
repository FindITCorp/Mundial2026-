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
- **Modelo de HAZARD por minuto** en vez de Poisson total: Senegal concede en OLEADAS
  (43-58'), invisible al total pero real por franja. Hipótesis: mejora over/under y
  marcadores en equipos de varianza por franja.
- **Matchups jugador-vs-jugador:** Wissa vs los laterales suplentes de England — predecir
  goles por quién marca a quién, no por agregados de equipo. Datos: ratings + XI real.
- **Condicionar por ESTILO del rival** (bus / press / contra) no solo por Elo. Datos: FDH
  (presiones, líneas) + `match_formations`.
- **Ensemble con pesos APRENDIDOS** del ledger (autoregresivo): reponderar señales por su
  acierto reciente ronda a ronda.
