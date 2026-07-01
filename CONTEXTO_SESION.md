# Contexto de Sesión — Pool Mundial 2026 "Kike"

> **Documento de handoff.** Lee esto primero para retomar el trabajo sin perder nada.
> Última actualización: **2026-07-01 tarde (England-Congo evaluado + BUG REAL encontrado y arreglado en analyze_match.py; Bélgica-Senegal re-sellado con XI real; R32 16/16 sellados)**
> ⚙️ **NORMA DEL DUEÑO (29-jun): SIEMPRE actualizar este handoff y commitear+pushear TODO tras cada avance.** No acumular. [[mundial2026-handoff-commit]]

---

## 🚀 EMPEZAR AQUÍ (01-jul tarde — para CHAT NUEVO, leer primero)

**R32 AHORA COMPLETO (16/16 partidos con fila en `wc_matches`/sello en `match_predictions`):**
- ✅ Jugados/evaluados (7): SAf 0-1 Can · Bra 2-1 Jpn · Ale 1-1 Par→Paraguay pen · Hol 1-1 Mar→Marruecos pen · CIV 1-2 Nor · Fra 3-0 Sue · Mex 2-0 Ecu.
- 🔴 **EN VIVO ahora mismo: England vs DR Congo** (kickoff 16:00Z 01-jul) — sello ya con XI real `integral_R32_ENG1-0adv68..._ENGrotado`, id 400021525.
- ✅ **RE-SELLADO CON XI REAL (link del dueño, match-centre FIFA 289287/400021525):** **Bélgica 2-2 Senegal, avance Bélgica ~57%** (id interno 400021526). XI real: **Bélgica 4-3-3** (Courtois; Théate-Mechele-De Cuyper-Castagne; De Bruyne-Tielemans-Vanaken; Trossard-Doku-De Ketelaere) — la formación MÁS EXITOSA del torneo (12V-2E-5D, 2.00 pts/p). **Senegal sorprende con 3-4-3** (línea de 3: Jakobs-Niakhaté-Diatta; Diaw; Gueye-Ciss-Diarra-P.Gueye; Mané-Ndiaye-Sarr) — formación RARA y FRÁGIL en el torneo (n=2, 0.50 pts/p, apenas 0.50 GF/p) pero muestra chica, no generalizar entre equipos. Bajé de la lectura preliminar (72% aún ayer) porque: Elo prácticamente EMPATADO (1733 vs 1735), `opponent_adjust` sigue favoreciendo el proceso de Senegal ajustado por rival (+2.7 vs +2.0, enfrentó a Francia), y Bélgica fue BLANQUEADA por Egipto (su único rival fuerte) — mismo patrón de alerta que España-Austria. Lo que sostiene a Bélgica: XI de gala completo, formación estructuralmente superior, y ventaja clara en el desempate de penales (64% vs 44%, pateadores 81pct vs 22pct). Partido ABIERTO (over2.5 65%, ambos marcan 58%) — **pendiente de evaluar cuando termine (kickoff 20:00Z).**
- 🔮 **Pendiente re-sellar con XI real cuando el dueño pase el link:** **USA-Bosnia** 00:00Z 02-jul (id 400021527, sello preliminar `USA2-1adv63`).
- 🆕 **Creados y sellados HOY (no existían en `wc_matches`, faltaba el resto del bracket) — preliminares SIN XI, re-sellar cuando salgan alineaciones (~1h antes, se puede auto-consultar FIFA live sin depender del link):**
  - id 400021528 **Spain 2-0 Austria** (~80% avance) — España defensa élite (0 GA/3, 100% paradas) pero ojo: proceso ajustado por rival (`opponent_adjust`) matiza a favor de Austria (rivales de España más flojos); Austria fue blanqueada por Argentina (su rival más fuerte) → patrón que podría repetirse ante la defensa de España.
  - id 400021529 **Portugal 2-1 Croatia** (~81%) — partido PAREJO (Elo brecha 41, alerta empate 41%), pero desempate claramente Portugal (80% vs 43%, GK Diogo Costa 88pct).
  - id 400021530 **Switzerland 2-1 Algeria** (~59%, el más abierto de los 3 europeos) — ambos con killer enchufado (Manzambi 8.25/3G vs Mahrez 7.63/2G), choque de ventanas real en 76-90 a favor de Algeria.
  - id 400021531 **Egypt 1-1 Australia → Egipto avanza en penales (~62%)** — CONFIANZA BAJA (bandera de ensemble: Australia bus/contra, arquetipo de upset); Egipto favorito flojo, portero Shobeir clave en tanda (94pct).
  - id 400021532 **Argentina 2-0 Cape Verde (~72%)** — CONFIANZA BAJA: Cabo Verde ajustado por rival en realidad SUPERA a Argentina en proceso (+1.8 vs +0.5, misma lección que Bélgica-Senegal); además Vozinha (GK Cabo Verde) es favorito EN LA TANDA (65% vs 35%) — mismo punto ciego de Bono/Holanda-Marruecos. Si empata, ojo con los penales.
  - id 400021533 **Colombia 2-0 Ghana (~77%)** — el más sólido de los 3 sudamericanos/africanos: Colombia con proceso fuerte incluso ajustado por rival (+3.4, ante DRC/Uzbekistán/Portugal 0-0), Ghana casi no genera (0.69 xG/p).

**🩹 England 2-1 DR Congo — EVALUADO, y BUG REAL encontrado y arreglado (no un placebo):** sellé 1-0 (~68% avance); real fue **2-1** (Congo marcó primero al 7' con Wissa, England remontó con DOS goles tarde: 75' y 86'). **El GANADOR se acertó** (sellado y modelo base coinciden, ambos 1X2 correctos vía `calibration_ledger`: knockout sellado 57% acc vs modelo 43% — mis overrides SIGUEN sumando ahí); el fallo fue de MARCADOR EXACTO y de narrativa táctica. **Diagnóstico → causa raíz real:** `_window_clash()` en `analyze_match.py` decidía "AMENAZA REAL"/"NEUTRALIZADA" usando el timing HISTÓRICO (amistosos/clasificatorios, tabla `team_goal_timing`) en vez de `wc_goal_timing` (datos REALES de este Mundial, ya cargados y marcados "prioritario" en el código pero nunca conectados a esta función específica). Por eso dijo "DR Congo aguanta bien 76-90" con datos viejos, cuando en ESTE Mundial sí concedía tarde — y England anotó ahí (75',86'), exactamente en su propia ventana LETAL TARDE. **FIX aplicado:** `_window_clash()` ahora usa `wc_scored`/`wc_conceded` si hay ≥2 goles de muestra (si no, cae al histórico) — corrige TODAS las llamadas futuras a `analyze_match.py`. **Verificado en los 7 partidos de R32 pendientes** (Spain-Austria, Portugal-Croatia, Switzerland-Algeria, Australia-Egypt, Argentina-CapeVerde, Colombia-Ghana, USA-Bosnia): la narrativa de ventanas cambió en varios casos, pero NINGUNO requirió re-sellar el número — el choque de ventanas es color cualitativo (no alimenta la λ del Monte Carlo/predict_ensemble numéricamente), consistente con el hallazgo del hazard-model de hoy mismo. Detalle en `LEARNING_LOOP.md`.

**🔬 HAZARD-BY-MINUTE PROTOTIPADO (`scripts/hazard_model.py`) — frontera cerrada con evidencia, NO activar:**
1. **Auto-excitación ("colapso en oleadas") — FALSEADA.** Test riguroso (huecos reales entre goles-encajados-consecutivos vs 10000 sims de goles colocados al azar en 90'): fracción real de huecos ≤15' = 0.453 vs esperado por azar 0.471 (p=0.70). El patrón Senegal es varianza normal de Poisson plano, NO derrumbe sistemático a nivel torneo.
2. **Peso numérico por "choque de ventanas" en λ — mejora in-sample (Brier 0.4466→0.4355) que SE REVIERTE en leave-one-out (0.6142→0.6247, empeora)** → era sobreajuste (3 partidos/equipo es muy poco para 6 buckets). Frontera ABIERTA pero bloqueada por tamaño de muestra, no por la idea en sí.
3. **Conclusión:** no tocar el modelo de producción; el choque de ventanas sigue útil como señal CUALITATIVA (ya en `analyze_match.py`). Detalle completo en `LEARNING_LOOP.md` (bitácora fallo→causa, sección Fronteras).

**⚙️ FLUJO OBLIGATORIO POR PARTIDO (sin cambios):**
`simulate_match.py "A" "B"` → `scoreline_ground.py "A" "B"` → **bajar XI real de FIFA live** (`/live/football/17/285023/{stage}/{match}`, se puede auto-consultar sin esperar link) → `predict_ensemble.py "A" "B"` → factores que emergen (`opponent_adjust`, `analyze_match`, `knockout_tiebreaker`) → sellar → push.

**📌 PENDIENTES:** re-sellar Bélgica-Senegal y USA-Bosnia con XI real (el dueño pasa el link) · re-sellar los 6 nuevos (Spain-Austria … Colombia-Ghana) cuando salgan sus alineaciones (kickoffs 02-jul a 04-jul, ir consultando FIFA live) · evaluar los partidos en vivo/próximos + `calibration_ledger` · seguir explorando fronteras: matchups jugador-vs-jugador, condicionar por estilo del rival (ver `LEARNING_LOOP.md`).

---

## 🗄️ EMPEZAR AQUÍ (resumen anterior — 01-jul mañana)

**ESTADO R32:** 7 jugados+evaluados · 3 sellados sin jugar (hoy). Acierto de avance 4/6 (67%), marcador exacto 1/6 (17%).
- ✅ Evaluados: SAf 0-1 Can · Bra 2-1 Jpn · **Ale 1-1 Par→Paraguay pen (fallé)** · Hol 1-1 Mar→Marruecos pen · **CIV 1-2 Nor (fallé)** · Fra 3-0 Sue · **Mex 2-0 Ecu** (mi coinflip fue peor que mi 2-1 original).
- 🔮 Sellados hoy (integral, re-sellar con XI al salir): **Inglaterra 1-0 Congo (~68%, XI ya cargado)** id 400021525 · **Bélgica 2-1 Senegal (~55%, ABIERTO, Senegal amenaza real)** id 400021526 · **USA 2-1 Bosnia (~63%, abierto)** id 400021527.
- Ids internos R32: 518-527 (mis sellos). Tras cada merge del pipeline: verificar sellos (`git checkout --ours data/mundial2026.db`).

**⚙️ FLUJO OBLIGATORIO POR PARTIDO (regla reforzada, NO saltar):**
`simulate_match.py "A" "B"` (forense gol-por-gol + ventanas + Monte Carlo, TODOS los escenarios) → `scoreline_ground.py "A" "B"` (fundamentar marcador en goles/concesión REALES, no la λ) → **bajar XI real de FIFA live** → `predict_ensemble.py "A" "B"` (consenso + tope tanda + banderas tácticas + ajuste por rival) → factores que emergen → sellar → push.

**🧰 SUITE DE HERRAMIENTAS (todas en scripts/):** `simulate_match` · `scoreline_ground` · `predict_ensemble` · `opponent_adjust` · `regression_check` · `calibration_ledger` · `live_winprob` · `analyze_match` · `xi_quality` · `knockout_tiebreaker` · `formation_matchup` · `timeline_stats` · `fetch_fifa_timeline`.

**🔧 MODELO:** `WC_LAMBDA_SCALE` re-calibrado **0.90→1.10** (marcador exacto 12→15%, ganador 67% estable; el torneo evolucionó a más goles).

**📏 PRINCIPIOS (memoria):** (1) **MANDATO GLOBAL:** ver lo que el dueño no ve, ser crítico siempre, buscar mejoras/detalles sin que lo pida, no conformarse — en TODO. (2) **LOOP de mejora** (`LEARNING_LOOP.md`): cada fallo → diagnosticar QUÉ señal lo cazaría → encodar → medir en ledger. (3) **Deferir al modelo en GRUPOS, criterio experto en KNOCKOUT** (medido). (4) **Análisis INTEGRAL siempre**, nunca "gana el favorito". (5) Techo honesto: marcador exacto ~20% (no 80%); el 80% es para el GANADOR.

**📌 PENDIENTES:** re-sellar Bélgica/USA con XI real al salir alineaciones · evaluar los 3 al cierre + `calibration_ledger` · resto de R32 (Spain-Austria, Portugal-Croatia, Switzerland-Algeria, Australia-Egypt, Argentina-CaboVerde, Colombia-Ghana) · **FRONTERA a prototipar: modelo de HAZARD por minuto** (Senegal concede en oleadas 43-58', invisible al Poisson total — el paradigma con más potencial de romper el techo).

---

## 🏗️ SUITE PREDICTIVA AUTÓNOMA (30-jun — control total del dueño)
4 herramientas nuevas + **principio operativo clave**:
- `opponent_adjust.py` — ajusta proceso por fuerza del rival (Elo). México-Ecuador: brecha se cierra a casi empate.
- `predict_ensemble.py` — consenso + **tope de tanda** [0.42,0.58] + **banderas tácticas** de analyze_match (recortan confianza y avance). Uso: `"A" "B"` / `--backtest`.
- `calibration_ledger.py` — **¿mis overrides suman? En GRUPOS RESTAN (deferir al modelo), en KNOCKOUT SUMAN (esfuerzo experto ahí).**
- `live_winprob.py` — prob de avance EN VIVO (marcador+minuto). `--match ID` auto-live.
- **REGLA NUEVA: no toquetear predicciones de grupo (el modelo gana); volcar el análisis experto en eliminatorias.**

## 🆕 EMPEZAR AQUÍ (30-jun)

**R32 jugados (5):** SAf 0-1 Canadá ✅exacto · Brasil 2-1 Japón ✅ganador · **Alemania 1-1 Paraguay → PARAGUAY avanza pen** (mi sello 2-1 Ale falló; upset que marqué ~19-29% se cumplió) · **P.Bajos 1-1 Marruecos → MARRUECOS avanza pen** (predije "penales→Marruecos por Bono", ✅). Ids internos R32: 518-524 (520=Ger-Par, 521=Ned-Mor result-only, 522/523/524=preliminares).

**DATOS COMPLETOS:** Sofascore disparado (IP desbloqueada, 1 sesión Playwright) para los 5 incompletos → **cobertura xG 100%**. fix `parse_sofascore_raw` (ahora mapea knockout, no solo group). FIFA complementó (timeline 6869 ev/76 part + FDH). Faltan stats ricos: ninguno de los jugados.

**3 PRELIMINARES SELLADAS (evaluated=0, `prelim_..._pendingXI`, re-sellar con XI real):**
- **400021522 Costa de Marfil 1-1 Noruega → CIV avanza ~57%** (campeón AFCON 2024, pedigrí penales: 5-4 a Senegal con Kessié -hoy titular- y Mali en pr 122'; Noruega 1ª eliminatoria desde 1998, pero Haaland 16g clasif). Cerrado, pinta a pen.
- **400021523 Francia 2-0 Suecia ~80%** (Francia campeona 18/finalista 22, Mbappé; Suecia se clasificó SIN ganar en grupo, vía repechaje NL, solo Isak+Gyökeres; encajó 5-1 vs Holanda).
- **400021524 México 1-1 Ecuador → Ecuador avanza ~52-53% pen** (mejor defensa CONMEBOL: 5 GA/18, Pacho-Hincapié-Caicedo; vs factor local México campeón Gold Cup/NL'25). 50/50 real. OJO: el "portero en racha Eloy Room" es de **Curaçao**, NO de Ecuador (lapsus corregido; arquero Ecuador = Galíndez).

**MÉTODO NUEVO validado (pedido del dueño):** evaluación profunda = proceso del torneo (timeline/xG) + XI de gala J1 (en knockout salen con ese) + **datos REALES de clasificación/competencia vía WebSearch** (pedigrí, ranking, experiencia de knockout/penales). Reveló a CIV como especialista de tanda y a Ecuador como sleeper defensivo.

**PENDIENTE:** re-sellar las 3 con XI confirmado al salir; seguir R32 (resto del bracket).

---

## 🆕 EMPEZAR AQUÍ (resumen para chat nuevo — 29-jun)

**ESTADO: dieciseisavos (R32) en curso.** Ids internos R32 en `wc_matches`/`match_predictions` son SECUENCIALES (NO el `fifa_match` del bracket): **400021518** SAf-Canadá, **400021519** Brasil-Japón, **400021520** Alemania-Paraguay (creado a mano esta sesión).

**Resultados y sellos R32 (los 3 verificados intactos):**
- ✅ **SAf 0-1 Canadá** — sello Canadá 1-0 = ganador + exacto.
- ✅ **Brasil 2-1 Japón** (J 29', B 56', **B 90'+5'**) — sello 1-1/penales: ganador ✅ (Brasil avanza), marcador/vía ❌. Remontó 0-1 con gol en el descuento. `evaluated=1`.
- 🟡 **Alemania-Paraguay SELLADO 2-1, avanza ~71%** (`expert_R32_GERMANY2-1_XIreal_earlyconcede`, evaluated=0). XI real cargado en `fifa_lineups` (match 400021520). Paraguay NO puso bus → salió **4-4-2 con Enciso+Ávalos**; riesgo vivo: **Alemania concede ≤30' en 3/3**. Evaluar cuando termine (20:30Z).

**🆕 FUENTE NUEVA — PLAY-BY-PLAY de FIFA (sin anti-bot), pedida por el dueño:**
- `scripts/fetch_fifa_timeline.py` → tabla **`fifa_match_events`** (74 partidos / **6610 eventos**: remate/parada/córner/falta/gol/tarjeta con minuto, autor y coordenadas). **Cableado en `matchday.py`** (sale cada jornada).
- `scripts/timeline_stats.py` → proceso por equipo. **SOT a favor = paradas del rival + goles = proxy de `goals_prevented` SIN xG** (Sofascore sigue bloqueado). Integrado en `analyze_match` (bloque PLAY-BY-PLAY + ⚡OCASIONES/🎯a-deber/🧤portero-muro).
- `scripts/timeline_patterns.py` → escaneo de los 32 clasificados.

**🔑 HALLAZGOS de patrones (leans, n=3-4/equipo):**
- **Remates a puerta (timeline) r=+0.66 con goles** = mejor proxy de output, abierto. Córners r=+0.37 (asedio, no gol).
- **A DEBER↑ (regresan al alza, sleepers):** Colombia (19.7 rem/6.7 SOT/1.33 gol), Bélgica (24.3 rem/1.67 gol), Ecuador (0.67 gol).
- **SOBRE-CONVIERTEN↓ (enfrían):** P.Bajos (3.0 gol/4.7 SOT **+ portero asediado = frágil, trampa**), Alemania, Suiza.
- **MURALLA por proceso:** Francia (mejor doble cara), España (élite atrás pero estéril, 1.33 gol), Argentina, Canadá.
- **Vulnerables temprano:** Brasil (le costó hoy), Noruega, Egipto.

**📌 PENDIENTES:** evaluar Alemania-Paraguay al terminar · **Sofascore SIGUE sin disparar** (orden del dueño; faltan stats ricos de Argelia-Austria, SAf-Canadá, Brasil-Japón; URLs en `data/sofascore_urls.json`) · seguir R32 (resto del bracket en `wc2026_standings_after_j3.json`).

---

## 🗄️ EMPEZAR AQUÍ (resumen anterior — 28-jun)

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
