"""
models/full_match_sim.py — Simulador integral de UN partido.

Combina TODOS los subsistemas en un único escenario realista:
  • match_predictor  → λ de goles, posesión, probabilidades 1X2
  • referee_model    → árbitro asignado y sus tendencias
  • match_events     → tiros, córners, faltas, tarjetas, penaltis
  • goal_scorer      → quién marca cada gol (+ penalty taker)

Ejecuta una simulación Monte Carlo (N partidos) y agrega:
  - marcador más probable y distribución
  - probabilidades 1X2 (frecuentista, validadas contra el Poisson analítico)
  - goleadores más frecuentes y su P(marcar)
  - promedios de córners, tarjetas, tiros, faltas
  - probabilidad de penalti y de tarjeta roja
  - "jugador del partido" probable (heurística de impacto)

API:
  simulate_full_match(home_id, away_id, ...) -> dict
  format_full_match(result) -> str
"""
from __future__ import annotations
import sqlite3
import random
from collections import Counter
from pathlib import Path

from models.match_predictor import predict_match
from models.referee_model import assign_referee, Referee
from models.match_events import (
    expected_events, simulate_events, _poisson_sample, _conversion,
)
from models.goal_scorer import scorer_weights, simulate_scorers, build_squad_with_subs, _finishing_weight
from models.team_stats_analyzer import get_team_profile

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Clásicos / rivalidades (sube fricción y tarjetas)
RIVALRIES = {
    frozenset({"Brazil", "Argentina"}): 0.9,
    frozenset({"Argentina", "Uruguay"}): 0.7,
    frozenset({"Germany", "Netherlands"}): 0.7,
    frozenset({"England", "Argentina"}): 0.8,
    frozenset({"Spain", "Portugal"}): 0.5,
    frozenset({"Mexico", "USA"}): 0.7,
    frozenset({"Serbia", "Croatia"}): 0.9,
    frozenset({"Germany", "England"}): 0.5,
}


def _team_meta(conn, team_id: int) -> dict:
    row = conn.execute(
        "SELECT name, confederation FROM teams WHERE id=?", (team_id,)
    ).fetchone()
    return {"name": row["name"], "conf": row["confederation"] or ""}


def _build_up_style(conn, team_id: int) -> str:
    row = conn.execute(
        "SELECT build_up_style FROM team_tactics WHERE team_id=?", (team_id,)
    ).fetchone()
    return row["build_up_style"] if row else "mixed"


def simulate_full_match(
    home_id: int,
    away_id: int,
    neutral: bool = True,
    home_absence: float = 0.0,
    away_absence: float = 0.0,
    stage: str = "group",
    n_sims: int = 20000,
    referee: Referee | None = None,
    db_path: str | Path = DB_PATH,
    seed: str = "WC2026",
    home_exclude: list[str] | None = None,
    away_exclude: list[str] | None = None,
    with_subs: bool = True,
) -> dict:
    """Simula un partido completo N veces y agrega el escenario más probable.

    with_subs=True (default): cada iteración simula 2-3 sustituciones por equipo,
    ajustando los pesos de gol por minutos jugados.
    """
    # ── 1. Predicción base (λ, posesión, prob 1X2) ───────────────────────────
    base = predict_match(home_id, away_id, neutral=neutral,
                         home_absence=home_absence, away_absence=away_absence,
                         db_path=db_path, stage=stage)
    lam_h = base["lambda_home"]
    lam_a = base["lambda_away"]

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    hm = _team_meta(conn, home_id)
    am = _team_meta(conn, away_id)
    style_h = _build_up_style(conn, home_id)
    style_a = _build_up_style(conn, away_id)
    conn.close()

    home, away = hm["name"], am["name"]
    rivalry = RIVALRIES.get(frozenset({home, away}), 0.0)

    # ── 2. Árbitro ────────────────────────────────────────────────────────────
    ref = referee or assign_referee(home, away, hm["conf"], am["conf"],
                                    stage, seed=seed)

    poss_h = base["possession_home"]
    poss_a = base["possession_away"]
    press_h = base["pressing_home"]
    press_a = base["pressing_away"]

    # ── 3. Eventos esperados (analíticos) ─────────────────────────────────────
    exp_ev = expected_events(home, away, lam_h, lam_a, poss_h, poss_a,
                            press_h, press_a, style_h, style_a, ref, rivalry)

    # ── 4. Perfiles históricos y pesos de goleadores base ─────────────────────
    # Cargar perfil histórico (sustituciones + estadísticas)
    profile_h = get_team_profile(home_id, db_path)
    profile_a = get_team_profile(away_id, db_path)
    sub_pat_h = profile_h.sub_pattern
    sub_pat_a = profile_a.sub_pattern

    sw_h_base = scorer_weights(home_id, db_path, exclude=home_exclude)
    sw_a_base = scorer_weights(away_id, db_path, exclude=away_exclude)
    names_h_base = [w["name"] for w in sw_h_base] or ["?"]
    probs_h_base = [w["weight"] for w in sw_h_base] or [1.0]
    names_a_base = [w["name"] for w in sw_a_base] or ["?"]
    probs_a_base = [w["weight"] for w in sw_a_base] or [1.0]

    # Penalty taker: se basa en el XI base
    pen_taker_h = next((w["name"] for w in sw_h_base if w["pen_taker"]), names_h_base[0])
    pen_taker_a = next((w["name"] for w in sw_a_base if w["pen_taker"]), names_a_base[0])

    # RNG dedicado para sustituciones (reproducible)
    sub_rng = random.Random(hash(seed) & 0xFFFFFFFF)

    pen_prob_h = exp_ev["penalty_prob"]["home"]
    pen_prob_a = exp_ev["penalty_prob"]["away"]
    pen_convert = 0.78   # tasa de conversión de penaltis

    # ── 5. Monte Carlo ────────────────────────────────────────────────────────
    score_counter = Counter()
    hw = dw = aw = 0
    scorer_counter_h = Counter()      # goles totales por jugador (en todas las sims)
    scorer_counter_a = Counter()
    anytime_h = Counter()             # partidos en que el jugador marcó ≥1
    anytime_a = Counter()
    sum_corners_h = sum_corners_a = 0
    sum_cards_h = sum_cards_a = 0
    sum_shots_h = sum_shots_a = 0
    sum_sot_h = sum_sot_a = 0
    sum_fouls_h = sum_fouls_a = 0
    pen_matches = 0
    red_matches = 0
    btts = 0                       # both teams to score
    over25 = 0                     # over 2.5 goles
    clean_sheet_h = clean_sheet_a = 0

    # Para reportar qué suplentes entran más frecuentemente
    sub_counter_h: Counter = Counter()
    sub_counter_a: Counter = Counter()

    for _ in range(n_sims):
        gh = _poisson_sample(lam_h)
        ga = _poisson_sample(lam_a)
        score_counter[(gh, ga)] += 1

        if gh > ga: hw += 1
        elif gh == ga: dw += 1
        else: aw += 1

        if gh > 0 and ga > 0: btts += 1
        if gh + ga > 2: over25 += 1
        if ga == 0: clean_sheet_h += 1
        if gh == 0: clean_sheet_a += 1

        # Penaltis del partido
        pen_h = 1 if random.random() < pen_prob_h else 0
        pen_a = 1 if random.random() < pen_prob_a else 0
        if pen_h or pen_a:
            pen_matches += 1
        pen_goals_h = min(gh, pen_h) if random.random() < pen_convert else 0
        pen_goals_a = min(ga, pen_a) if random.random() < pen_convert else 0

        # ── Goleadores con sustituciones ──────────────────────────────────────
        if with_subs:
            players_h, mins_h = build_squad_with_subs(
                home_id, db_path, exclude=home_exclude, rng=sub_rng,
                sub_pattern=sub_pat_h)
            players_a, mins_a = build_squad_with_subs(
                away_id, db_path, exclude=away_exclude, rng=sub_rng,
                sub_pattern=sub_pat_a)

            # Registrar suplentes que entraron (diferencia con XI base)
            base_names_h = {w["name"] for w in sw_h_base}
            base_names_a = {w["name"] for w in sw_a_base}
            for p in players_h:
                if p["name"] not in base_names_h:
                    sub_counter_h[p["name"]] += 1
            for p in players_a:
                if p["name"] not in base_names_a:
                    sub_counter_a[p["name"]] += 1

            # Recalcular pesos con minutos jugados
            sw_h = scorer_weights(home_id, db_path, exclude=home_exclude,
                                  minutes_played=mins_h)
            sw_a = scorer_weights(away_id, db_path, exclude=away_exclude,
                                  minutes_played=mins_a)
            names_h = [w["name"] for w in sw_h] or ["?"]
            probs_h = [w["weight"] for w in sw_h] or [1.0]
            names_a = [w["name"] for w in sw_a] or ["?"]
            probs_a = [w["weight"] for w in sw_a] or [1.0]
        else:
            names_h, probs_h = names_h_base, probs_h_base
            names_a, probs_a = names_a_base, probs_a_base

        match_scorers_h = []
        for i in range(gh):
            if i < pen_goals_h:
                match_scorers_h.append(pen_taker_h)
            else:
                match_scorers_h.append(random.choices(names_h, weights=probs_h, k=1)[0])
        match_scorers_a = []
        for i in range(ga):
            if i < pen_goals_a:
                match_scorers_a.append(pen_taker_a)
            else:
                match_scorers_a.append(random.choices(names_a, weights=probs_a, k=1)[0])
        for nm in match_scorers_h:
            scorer_counter_h[nm] += 1
        for nm in match_scorers_a:
            scorer_counter_a[nm] += 1
        for nm in set(match_scorers_h):
            anytime_h[nm] += 1
        for nm in set(match_scorers_a):
            anytime_a[nm] += 1

        # Eventos secundarios (muestreo Poisson rápido)
        sum_corners_h += _poisson_sample(exp_ev["corners"]["home"])
        sum_corners_a += _poisson_sample(exp_ev["corners"]["away"])
        sum_cards_h += _poisson_sample(exp_ev["yellow_cards"]["home"])
        sum_cards_a += _poisson_sample(exp_ev["yellow_cards"]["away"])
        sum_shots_h += _poisson_sample(exp_ev["shots"]["home"])
        sum_shots_a += _poisson_sample(exp_ev["shots"]["away"])
        sum_sot_h += _poisson_sample(exp_ev["shots_on_target"]["home"])
        sum_sot_a += _poisson_sample(exp_ev["shots_on_target"]["away"])
        sum_fouls_h += _poisson_sample(exp_ev["fouls"]["home"])
        sum_fouls_a += _poisson_sample(exp_ev["fouls"]["away"])
        if random.random() < ref.reds_per_game:
            red_matches += 1

    n = n_sims
    top_scores = score_counter.most_common(8)
    mode_score = top_scores[0][0]

    # Goleadores más probables (P de marcar al menos 1 en el partido)
    def scorer_table(goals_counter, anytime_counter):
        out = []
        for name, cnt in goals_counter.most_common(8):
            out.append({"name": name,
                        "goals_total": cnt,
                        "goals_per_match": round(cnt / n, 3),
                        "prob_anytime": round(anytime_counter[name] / n * 100, 1)})
        return out

    scorers_h = scorer_table(scorer_counter_h, anytime_h)
    scorers_a = scorer_table(scorer_counter_a, anytime_a)

    # Ganador 1X2 (por probabilidad), independiente del marcador modal.
    # En partidos parejos el marcador modal puede ser empate aunque haya favorito.
    probs_1x2 = {home: hw, "EMPATE": dw, away: aw}
    winner = max(probs_1x2, key=probs_1x2.get)
    # Marcador modal NO-empate del favorito (si el favorito no es empate)
    if winner != "EMPATE" and mode_score[0] == mode_score[1]:
        fav_scores = [(s, c) for s, c in top_scores
                      if (s[0] > s[1]) == (winner == home) and s[0] != s[1]]
        likely_score = fav_scores[0][0] if fav_scores else mode_score
    else:
        likely_score = mode_score

    # Suplentes más frecuentes (top 3 por equipo)
    top_subs_h = [{"name": nm, "pct": round(cnt / n * 100, 1)}
                  for nm, cnt in sub_counter_h.most_common(3)]
    top_subs_a = [{"name": nm, "pct": round(cnt / n * 100, 1)}
                  for nm, cnt in sub_counter_a.most_common(3)]

    return {
        "home": home, "away": away,
        "stage": stage, "neutral": neutral,
        "referee": ref.name, "referee_country": ref.country,
        "rivalry": rivalry,
        "with_subs": with_subs,
        # Predicción
        "lambda_home": lam_h, "lambda_away": lam_a,
        "predicted_score": f"{mode_score[0]}-{mode_score[1]}",
        "likely_score_winner": f"{likely_score[0]}-{likely_score[1]}",
        "winner": winner,
        "prob_home_win": round(hw / n * 100, 1),
        "prob_draw": round(dw / n * 100, 1),
        "prob_away_win": round(aw / n * 100, 1),
        "top_scores": [(f"{s[0]}-{s[1]}", round(c / n * 100, 1)) for s, c in top_scores],
        # Mercados
        "btts_prob": round(btts / n * 100, 1),
        "over25_prob": round(over25 / n * 100, 1),
        "clean_sheet_home": round(clean_sheet_h / n * 100, 1),
        "clean_sheet_away": round(clean_sheet_a / n * 100, 1),
        # Dominio
        "possession": {"home": poss_h, "away": poss_a},
        "formation": {"home": base["formation_home"], "away": base["formation_away"]},
        "elo": {"home": base["elo_home"], "away": base["elo_away"]},
        # Eventos (promedios simulados)
        "shots": {"home": round(sum_shots_h / n, 1), "away": round(sum_shots_a / n, 1)},
        "shots_on_target": {"home": round(sum_sot_h / n, 1), "away": round(sum_sot_a / n, 1)},
        "corners": {"home": round(sum_corners_h / n, 1), "away": round(sum_corners_a / n, 1)},
        "fouls": {"home": round(sum_fouls_h / n, 1), "away": round(sum_fouls_a / n, 1)},
        "yellow_cards": {"home": round(sum_cards_h / n, 1), "away": round(sum_cards_a / n, 1)},
        "total_cards": round((sum_cards_h + sum_cards_a) / n, 1),
        "total_corners": round((sum_corners_h + sum_corners_a) / n, 1),
        "penalty_prob": round(pen_matches / n * 100, 1),
        "red_card_prob": round(red_matches / n * 100, 1),
        # Goleadores
        "scorers_home": scorers_h,
        "scorers_away": scorers_a,
        "pen_taker_home": pen_taker_h,
        "pen_taker_away": pen_taker_a,
        # Sustituciones
        "subs_home": top_subs_h,
        "subs_away": top_subs_a,
        # Estadísticas históricas del perfil de cada equipo
        "hist_home": {
            "sot_for": profile_h.match_stats.sot_for_pg,
            "sot_against": profile_h.match_stats.sot_against_pg,
            "set_piece_frac": profile_h.match_stats.set_piece_frac_for,
            "clean_sheet_rate": profile_h.match_stats.clean_sheet_rate,
            "corners_for": profile_h.match_stats.est_corners_for_pg,
            "corners_against": profile_h.match_stats.est_corners_against_pg,
            "fouls": profile_h.match_stats.fouls_pg,
            "subs_per_game": sub_pat_h.subs_per_game_mean,
        },
        "hist_away": {
            "sot_for": profile_a.match_stats.sot_for_pg,
            "sot_against": profile_a.match_stats.sot_against_pg,
            "set_piece_frac": profile_a.match_stats.set_piece_frac_for,
            "clean_sheet_rate": profile_a.match_stats.clean_sheet_rate,
            "corners_for": profile_a.match_stats.est_corners_for_pg,
            "corners_against": profile_a.match_stats.est_corners_against_pg,
            "fouls": profile_a.match_stats.fouls_pg,
            "subs_per_game": sub_pat_a.subs_per_game_mean,
        },
        "n_sims": n,
    }


def format_full_match(r: dict) -> str:
    sep = "═" * 70
    L = [
        f"\n{sep}",
        f"  {r['home'].upper()}  vs  {r['away'].upper()}",
        f"  {r['formation']['home']} vs {r['formation']['away']}   |   "
        f"Etapa: {r['stage']}   |   {'Sede neutral' if r['neutral'] else 'Con localía'}",
        f"  🧑‍⚖️  Árbitro: {r['referee']} ({r['referee_country']})"
        + (f"   ⚔️ rivalidad alta" if r['rivalry'] >= 0.7 else ""),
        f"{'─'*70}",
        f"  ⚡ Elo: {r['home'][:14]} {r['elo']['home']:.0f}  vs  "
        f"{r['away'][:14]} {r['elo']['away']:.0f}",
        f"  🎯 λ goles: {r['lambda_home']:.2f}  vs  {r['lambda_away']:.2f}",
        f"{'─'*70}",
        f"  📈 RESULTADO ({r['n_sims']:,} simulaciones)",
        f"     {r['home'][:18]:<18} {r['prob_home_win']:>5.1f}%   "
        f"Empate {r['prob_draw']:>5.1f}%   {r['away'][:18]} {r['prob_away_win']:>5.1f}%",
        f"  🏆 Favorito: {r['winner']}   |   Marcador más probable: "
        f"{r['home']} {r['predicted_score']} {r['away']}",
        f"     Top marcadores: " + "  ".join(f"{s}({p}%)" for s, p in r['top_scores'][:5]),
        f"{'─'*70}",
        f"  🏃 DOMINIO Y JUEGO",
        f"     Posesión   {r['possession']['home']:.0f}% - {r['possession']['away']:.0f}%",
        f"     Tiros       {r['shots']['home']:.1f} - {r['shots']['away']:.1f}   "
        f"(a puerta {r['shots_on_target']['home']:.1f} - {r['shots_on_target']['away']:.1f})",
        f"     Córners     {r['corners']['home']:.1f} - {r['corners']['away']:.1f}   "
        f"(total {r['total_corners']:.1f})",
        f"     Faltas      {r['fouls']['home']:.1f} - {r['fouls']['away']:.1f}",
        f"     Amarillas   {r['yellow_cards']['home']:.1f} - {r['yellow_cards']['away']:.1f}   "
        f"(total {r['total_cards']:.1f})",
        f"     P(penalti)  {r['penalty_prob']:.1f}%      P(roja) {r['red_card_prob']:.1f}%",
        f"{'─'*70}",
        f"  💰 MERCADOS",
        f"     Ambos marcan: {r['btts_prob']:.1f}%   |   Over 2.5: {r['over25_prob']:.1f}%",
        f"     Portería 0 {r['home'][:10]}: {r['clean_sheet_home']:.1f}%   |   "
        f"Portería 0 {r['away'][:10]}: {r['clean_sheet_away']:.1f}%",
        f"{'─'*70}",
        f"  ⚽ GOLEADORES PROBABLES",
        f"     [{r['home']}]  (penaltis: {r['pen_taker_home']})",
    ]
    for s in r["scorers_home"][:5]:
        L.append(f"        {s['name'][:24]:<24} P(marca) {s['prob_anytime']:>5.1f}%")
    L.append(f"     [{r['away']}]  (penaltis: {r['pen_taker_away']})")
    for s in r["scorers_away"][:5]:
        L.append(f"        {s['name'][:24]:<24} P(marca) {s['prob_anytime']:>5.1f}%")
    # Sustituciones
    if r.get("with_subs") and (r.get("subs_home") or r.get("subs_away")):
        L.append(f"{'─'*70}")
        L.append(f"  🔄 CAMBIOS MÁS FRECUENTES (sims con sustituciones)")
        if r.get("subs_home"):
            subs_str = "  ".join(f"{s['name'][:18]} {s['pct']:.0f}%" for s in r["subs_home"])
            L.append(f"     {r['home'][:14]}: {subs_str}")
        if r.get("subs_away"):
            subs_str = "  ".join(f"{s['name'][:18]} {s['pct']:.0f}%" for s in r["subs_away"])
            L.append(f"     {r['away'][:14]}: {subs_str}")
    L.append(sep)
    return "\n".join(L)


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    tid = lambda n: conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()[0]
    demos = [("Brazil", "Argentina", "final"), ("Spain", "France", "semi_final")]
    for h, a, st in demos:
        r = simulate_full_match(tid(h), tid(a), neutral=True, stage=st, n_sims=20000)
        print(format_full_match(r))
    conn.close()
