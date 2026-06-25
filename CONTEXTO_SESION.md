# Contexto de Sesión — Pool Mundial 2026 "Kike"

> **Documento de handoff.** Lee esto primero para retomar el trabajo sin perder nada.
> Última actualización: **2026-06-25**

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
| `data/processed/wc2026_results_j3.json` | J3: **6 partidos terminados** (Grupos A,B,C completos) | 🔄 Parcial — faltan D,E,F,G,H,I,J,K,L |
| `data/processed/wc2026_match_stats_j3.json` | Stats J3 (6 partidos) | 🔄 Parcial |
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
2. **Factor de eliminación** (params `home_eliminated`/`away_eliminated`): equipo eliminado → λ × 0.70 (−30%).
   - Evidencia: Qatar eliminado convirtió mal; Bosnia con presión convirtió 441% xG.
3. **Cap de conversión ampliado** (`_FINISH_CAP` 0.10 → 0.20): captura equipos sistemáticamente clínicos (Marruecos 1.23× xG).
4. **Factor de rotación calibrado** (`_rotation_factor`, params `home_rotation_expected`/`away_rotation_expected`) — **NUEVO 25-jun (esta sesión)**: equipo que rota su XI reduce su λ propia, pero solo según la brecha de Elo con el rival. `rotation_penalty = base × (1 − clamp(signed_gap/FULLPASS,0,1))`, `signed_gap = elo_propio − elo_rival`. Dominante (gap ≥ 300) rota gratis; parejos pagan hasta −25%. Constantes env-tunables: `WC_ROTATION_PENALTY` (def 0.25), `WC_ROTATION_FULLPASS` (def 300). Opt-in (default factor=1.0, no rompe nada). Verificado: México(gap≈98) rota → −17%; Australia(parejo) → −22%.
   - ⚠️ Pendiente de calibrar `FULLPASS`: con 300, México (gap modelo ≈98) aún recibe −17%, y la realidad fue 0-3 (México dominó MÁS). Puede que 300 sea muy conservador → considerar bajarlo a ~200 con más evidencia.

Los 4 factores se exponen en `result["_factors"]` para auditoría (incl. `rotation_factor_home/away`).

---

## 5. Ajustes PROPUESTOS pendientes de implementar (siguiente sesión)

### Validación pendiente
- Evaluar las 6 predicciones del 25-jun (Grupos D/E/F) en `wc2026_predictions_j3_june25.json` cuando terminen.
- Atención especial: Turquía vs USA (predije que USA podría empatar si rota mucho — mismo riesgo que el error de México; ver si USA-rotado aplasta a Turquía igual que México a Chequia).

---

## 6. Tareas pendientes (TODO)

1. [ ] Cuando terminen los partidos del 25-jun (D/E/F), bajar resultados/stats/lineups y evaluar vs `wc2026_predictions_j3_june25.json`.
2. [ ] Completar J3 grupos D-L en los archivos de resultados/stats/lineups.
3. [x] ~~Implementar **Ajuste 4 (rotación calibrada)** en `match_predictor.py`.~~ ✅ HECHO 25-jun (ver §4.4). Pendiente: cablear en flujo de predicción cuando se decida qué equipos marcar como rotación, y calibrar `FULLPASS` con datos reales.
4. [ ] Generar `wc2026_standings_after_j3.json` con los 12 grupos finales de fase de grupos.
5. [ ] Determinar los 8 mejores terceros (clasifican a dieciseisavos en formato 48 equipos).

---

## 7. Credenciales / acceso
- Token GitHub en uso por el dueño (NO exponer en commits). Repo: `FindITCorp/Mundial2026-`.
- Git: hacer `git pull --rebase origin main` antes de push si el remoto tiene commits nuevos.
- Entorno: Windows, shell PowerShell + Bash. Python disponible (`python -c "import models.match_predictor"` compila OK).
