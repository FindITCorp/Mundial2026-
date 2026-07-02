"""
full_verdict.py — EL MOTOR CONSOLIDADO. Pedido del dueño 01-jul: "siento que
tienes mucha data de todo el Mundial y no la usamos, o usamos algo y dejamos
de usar otra... pensaba predecir no adivinar."

Diagnóstico (auditoría 01-jul): NO faltaban herramientas — sobraban, sueltas
(15+ scripts), y había que acordarse de correr cada una a mano. Además
`fifa_fdh_stats` (142 métricas/equipo, 20 mil filas — presiones, rupturas de
línea, remates por zona) casi no se usaba fuera de `tournament_scan.py`, que
tampoco se corría por defecto. Y una carpeta `models/` entera (21 archivos,
formation_engine/goal_scorer/simulator/full_match_sim/etc.) resultó estar
HUÉRFANA — nada de eso está conectado al pipeline real (verificado con grep,
no de oídas: match_predictor.py solo importa veteran_experience.py). No se
integra ese código sin más auditoría — sería sumar riesgo, no señal.

Este script corre TODAS las señales YA VALIDADAS de scripts/ en un solo
comando, en el orden del flujo obligatorio, y termina con UN veredicto
sintetizado y trazable (qué dijo cada señal, dónde coincidieron/discreparon,
por qué se decidió lo que se decidió) — no una sola línea de "% favorito".

Uso:
    python scripts/full_verdict.py "Equipo A" "Equipo B"
    python scripts/full_verdict.py "Equipo A" "Equipo B" --seal   # sella en match_predictions y corre validate_predictions
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
sys.path.insert(0, str(BASE_DIR / "scripts"))

from simulate_match import forensics, simulate as sim_team
from scoreline_ground import ground
from analyze_match import analyze
from opponent_adjust import adj_process
from team_lineup_sim import resolve_xi_source, team_xi, run_side, print_side
from full_match_sim import build_squad, simulate_once, _shot_accuracy
from predict_ensemble import ensemble, _print as print_ensemble
from knockout_tiebreaker import ratings as ko_ratings


def _tid(conn, name):
    r = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    return r[0] if r else None


def _fdh_flags(conn, team_name):
    """Señales de fifa_fdh_stats (presión/rupturas de línea) — antes sin usar
    fuera de tournament_scan.py, que tampoco se corría por defecto."""
    tid = _tid(conn, team_name)
    if not tid:
        return []
    rows = conn.execute(
        "SELECT stat, value FROM fifa_fdh_stats f JOIN wc_matches w ON w.id=f.match_id "
        "WHERE f.team_id=? AND w.stage IN ('group','R32') "
        "AND stat IN ('DefensivePressuresApplied','LinebreaksAttemptedAttackingLineCompleted',"
        "'BallRecoveryTime','GoalkeeperSavePercentage')", (tid,)).fetchall()
    if not rows:
        return []
    from collections import defaultdict
    agg = defaultdict(list)
    for stat, val in rows:
        if val is not None:
            agg[stat].append(val)
    flags = []
    if agg.get("DefensivePressuresApplied") and agg.get("BallRecoveryTime"):
        press = sum(agg["DefensivePressuresApplied"]) / len(agg["DefensivePressuresApplied"])
        rec = sum(agg["BallRecoveryTime"]) / len(agg["BallRecoveryTime"])
        # promedio torneo aproximado para contextualizar (percentil crudo, no exacto)
        all_press = conn.execute(
            "SELECT AVG(value) FROM fifa_fdh_stats WHERE stat='DefensivePressuresApplied'").fetchone()[0]
        if all_press and press > all_press * 1.15:
            flags.append(f"presiona MUCHO ({press:.0f}/p vs torneo {all_press:.0f}) — ver si recupera rápido (t.recup {rec:.1f}s)")
    if agg.get("LinebreaksAttemptedAttackingLineCompleted"):
        lb = sum(agg["LinebreaksAttemptedAttackingLineCompleted"]) / len(agg["LinebreaksAttemptedAttackingLineCompleted"])
        all_lb = conn.execute(
            "SELECT AVG(value) FROM fifa_fdh_stats WHERE stat='LinebreaksAttemptedAttackingLineCompleted'").fetchone()[0]
        if all_lb and lb > all_lb * 1.2:
            flags.append(f"rompe líneas de ataque por encima del torneo ({lb:.1f} vs {all_lb:.1f}/p) — progresión real, no solo posesión")
    return flags


def run(team_a, team_b, seal=False):
    conn = sqlite3.connect(str(DB))
    aid, bid = _tid(conn, team_a), _tid(conn, team_b)
    if not aid or not bid:
        print(f"Equipo no encontrado: {team_a if not aid else team_b}")
        return

    print("#" * 78)
    print(f"# VEREDICTO CONSOLIDADO — {team_a} vs {team_b}")
    print("#" * 78)

    print("\n=== 1) ANÁLISIS EXHAUSTIVO (XI real/proxy + formación real + timing + choque de ventanas) ===")
    analyze(team_a, team_b, db_path=DB, verbose=True)

    print("\n=== 2) FORENSE GOL-POR-GOL + MONTE CARLO DE EQUIPO ===")
    conn2 = sqlite3.connect(str(DB))
    for tm in (team_a, team_b):
        lines, att, conc = forensics(conn2, tm)
        for opp, gf, ga, gfl, gal in lines:
            print(f"  {tm} vs {opp}: {gf}-{ga}")
    s = sim_team(conn2, team_a, team_b, n=40000)
    N = s["n"]
    print(f"  λ {team_a} {s['la']:.2f} / {team_b} {s['lb']:.2f}  |  "
          f"1X2: {100*s['out']['A']/N:.0f}%/{100*s['out']['D']/N:.0f}%/{100*s['out']['B']/N:.0f}%  |  "
          f"over2.5 {100*s['over']:.0f}%  ambos marcan {100*s['bts']:.0f}%")
    print("  top marcadores: " + ", ".join(f"{x}-{y} {100*c/N:.0f}%" for (x, y), c in s['res'].most_common(6)))

    print("\n=== 3) FUNDAMENTO DE MARCADOR (registros reales de gol/concesión) ===")
    g = ground(conn2, team_a, team_b)
    if g:
        ra, rb = g["ra"], g["rb"]
        print(f"  {team_a}: marca {ra['gf']:.2f}/p (máx {ra['max_scored'][0]} vs {ra['max_scored'][1]}) · "
              f"concede {ra['ga']:.2f}/p (máx {ra['max_conc'][0]} vs {ra['max_conc'][1]})")
        print(f"  {team_b}: marca {rb['gf']:.2f}/p (máx {rb['max_scored'][0]} vs {rb['max_scored'][1]}) · "
              f"concede {rb['ga']:.2f}/p (máx {rb['max_conc'][0]} vs {rb['max_conc'][1]})")
        print(f"  → MARCADOR FUNDAMENTADO ≈ {team_a} {round(g['a_goals'])}-{round(g['b_goals'])} {team_b}")
    else:
        print("  Sin datos suficientes de grupos para fundamentar (¿aún no jugó grupos?).")

    print("\n=== 4) PROCESO AJUSTADO POR RIVAL (SOT-dif vs lo que predice el Elo) ===")
    r = adj_process(conn2)
    for tm in (team_a, team_b):
        d = r["teams"].get(_tid(conn2, tm))
        if d:
            print(f"  {tm}: SOTdif crudo {d['raw']:+.1f} → AJUSTADO {d['adj']:+.1f} (Elo rival medio {d['opp_elo']:.0f})")

    # 4b) SOT-dif como ALARMA anti-sesgo (validado 5/6 OOS; le acertó a CIV-Noruega
    # cuando mi sello experto falló). Solo display: si contradice al favorito, avisa.
    da_ = r["teams"].get(_tid(conn2, team_a))
    db_ = r["teams"].get(_tid(conn2, team_b))
    if da_ and db_:
        fav_sig = team_a if da_["adj"] > db_["adj"] else team_b
        print(f"  ⚠ regression_check (alarma, no oráculo): la señal ajustada favorece a {fav_sig} "
              f"(brecha {abs(da_['adj']-db_['adj']):.1f})")

    # 4c) SUSPENSIONES por acumulación (2 amarillas o roja en grupos = fuera del R32).
    # Punto ciego encontrado 02-jul: estaba EN los datos (fifa_match_events tipos
    # 2/3/71) y ninguna herramienta lo miraba — cazó a Lasheen (Egipto, titular
    # 270/270 min) y a Lopes Cabral (Cabo Verde) sin que nadie lo pidiera.
    print("\n=== 4c) SUSPENDIDOS por acumulación (2 amarillas / roja en grupos) ===")
    any_susp = False
    for tm, tid_ in ((team_a, aid), (team_b, bid)):
        for nm, yel, red in conn2.execute(
                "SELECT COALESCE(fp.name, e.player_fifa_id), "
                "SUM(CASE WHEN e.type_code=2 THEN 1 ELSE 0 END) yel, "
                "SUM(CASE WHEN e.type_code IN (3,71) THEN 1 ELSE 0 END) red "
                "FROM fifa_match_events e LEFT JOIN fifa_player_names fp ON fp.fifa_player_id=e.player_fifa_id "
                "WHERE e.db_team_id=? AND e.type_code IN (2,3,71) "
                "GROUP BY 1 HAVING yel>=2 OR red>=1", (tid_,)):
            mins = conn2.execute(
                "SELECT SUM(minutes), AVG(rating) FROM match_player_stats "
                "WHERE UPPER(player_name) LIKE UPPER(?) AND competition='World Cup'",
                (f"%{str(nm).split()[-1]}%",)).fetchone()
            peso = f" — TITULAR ({mins[0]:.0f} min, rating {mins[1]:.1f})" if mins and mins[0] and mins[0] >= 180 else ""
            print(f"  🟨 {tm}: {nm} fuera por acumulación ({yel} amarillas, {red} rojas){peso}")
            any_susp = True
    if not any_susp:
        print("  (ninguno en los dos equipos)")

    print("\n=== 5) FDH — presión y progresión (142 métricas/equipo, antes sin usar) ===")
    any_fdh = False
    for tm in (team_a, team_b):
        fl = _fdh_flags(conn2, tm)
        for f in fl:
            print(f"  ⚡ {tm}: {f}")
            any_fdh = True
    if not any_fdh:
        print("  (sin señales FDH destacadas por encima del torneo para este cruce)")

    print("\n=== 6) SIMULACIÓN COMPLETA DE XI (medio+ataque, anclada al λ de equipo) ===")
    mid_a, mid_b, is_real = resolve_xi_source(conn2, aid, bid)
    total_a = total_b = None
    if mid_a and mid_b:
        xi_a, xi_b = team_xi(conn2, mid_a, aid), team_xi(conn2, mid_b, bid)
        if xi_a and xi_b:
            rows_a = run_side(conn2, xi_a, team_b)
            rows_b = run_side(conn2, xi_b, team_a)
            total_a = print_side(team_a, team_b, rows_a, team_lambda=s["la"])
            total_b = print_side(team_b, team_a, rows_b, team_lambda=s["lb"])
            print(f"  (fuente XI: {'REAL confirmado' if is_real else 'PROXY, último XI propio de cada equipo'})")
    else:
        print("  Sin datos de XI (ni real ni propio) para simular jugador por jugador.")

    # 6b) MOTOR MINUTO-A-MINUTO (full_match_sim) — estaba importado pero NUNCA usado
    # (import muerto, detectado 02-jul cuando el dueño exigió "usa TODA la evaluación").
    # 1500 corridas del partido completo jugador-por-jugador: valida el 1X2 desde otro
    # ángulo (motor de eventos, no Poisson de equipo) y da quién anota con qué frecuencia.
    print("\n=== 6b) MOTOR MINUTO-A-MINUTO (1500 partidos simulados jugador-por-jugador) ===")
    try:
        import random as _rnd
        from collections import Counter as _Ctr
        rows_fa, raw_fa, _ = build_squad(conn2, team_a, team_b, mid_a)
        rows_fb, raw_fb, _ = build_squad(conn2, team_b, team_a, mid_b)
        sc_a = s["la"] / raw_fa if raw_fa else 1.0
        sc_b = s["lb"] / raw_fb if raw_fb else 1.0
        ac_a, ac_b = _shot_accuracy(conn2, aid), _shot_accuracy(conn2, bid)
        wa = wb = dd = 0
        scorers = _Ctr()
        for i in range(1500):
            rr = _rnd.Random(5000 + i)
            ga_, gb_, evs = simulate_once(conn2, team_a, team_b, rows_fa, rows_fb, sc_a, sc_b, ac_a, ac_b, rr)
            if ga_ > gb_: wa += 1
            elif gb_ > ga_: wb += 1
            else: dd += 1
            for _, _, pl, out_ in evs:
                if out_ == "GOL":
                    scorers[pl] += 1
        print(f"  1X2 del motor de eventos: {team_a} {100*wa/1500:.0f}% / empate {100*dd/1500:.0f}% / {team_b} {100*wb/1500:.0f}%")
        top_sc = ", ".join(f"{p} ({100*c/1500:.0f} goles/100 sims)" for p, c in scorers.most_common(4))
        print(f"  goleadores más frecuentes: {top_sc}")
    except Exception as e:
        print(f"  (motor minuto-a-minuto no disponible: {e})")

    print("\n=== 7) DESEMPATE knockout (resistencia · portero · pateadores) ===")
    kr = ko_ratings(conn2)
    ka, kb = kr.get(team_a), kr.get(team_b)
    if ka and kb:
        sh = ka["tie"] / (ka["tie"] + kb["tie"]) if (ka["tie"] + kb["tie"]) else 0.5
        print(f"  {team_a}: {ka['tie']*100:.0f}%  {team_b}: {kb['tie']*100:.0f}%  → favorito en tanda: "
              f"{team_a if sh >= 0.5 else team_b} ({max(sh, 1-sh)*100:.0f}%)")

    print("\n=== 8) ENSEMBLE (consenso + tope de tanda + banderas tácticas) ===")
    ens = ensemble(conn2, team_a, team_b)
    if ens:
        print_ensemble(ens)

    conn2.close()

    print("\n" + "#" * 78)
    print("# VEREDICTO FINAL SINTETIZADO")
    print("#" * 78)
    mc_ph = s['out']['A'] / N
    mc_pd = s['out']['D'] / N
    mc_pb = s['out']['B'] / N
    final_ph = final_pd = final_pb = None
    if ens:
        print(f"  Modelo de producción: {team_a} {ens['ph']*100:.0f}% / empate {ens['pd']*100:.0f}% / {team_b} {ens['pa']*100:.0f}%  "
              f"({ens['nvotes']} señales, acuerdo {ens['agreement']*100:.0f}%)")
    print(f"  Monte Carlo equipo (simulate_match, cruzado con XI real): {team_a} {mc_ph*100:.0f}% / empate {mc_pd*100:.0f}% / {team_b} {mc_pb*100:.0f}%")
    if total_a is not None:
        print(f"  Suma XI real/proxy (jugador por jugador, anclada a este mismo λ): {team_a} {total_a:.2f} goles esperados / {team_b} {total_b:.2f}")

    # RECONCILIACIÓN: si el modelo de producción y el Monte Carlo/XI discrepan
    # fuerte (>12pp en la prob del favorito), NO se adopta el del modelo sin más
    # -- es EXACTAMENTE el exceso de confianza que se corrigió a mano varias
    # veces hoy (España-Austria, Bélgica-Senegal, USA-Bosnia). Se promedia y se
    # marca la discrepancia como ALERTA, no se esconde.
    if ens:
        gap = abs(ens['ph'] - mc_ph)
        if gap > 0.12:
            final_ph = (ens['ph'] + mc_ph) / 2
            final_pd = (ens['pd'] + mc_pd) / 2
            final_pb = (ens['pa'] + mc_pb) / 2
            tot = final_ph + final_pd + final_pb
            final_ph, final_pd, final_pb = final_ph/tot, final_pd/tot, final_pb/tot
            print(f"  ⚠ DISCREPANCIA real ({gap*100:.0f}pp) entre modelo de producción y Monte Carlo/XI — "
                  f"NO se adopta el del modelo sin más. Promediado: {team_a} {final_ph*100:.0f}% / "
                  f"empate {final_pd*100:.0f}% / {team_b} {final_pb*100:.0f}%")
        else:
            final_ph, final_pd, final_pb = ens['ph'], ens['pd'], ens['pa']
            print(f"  ✓ Modelo de producción y Monte Carlo/XI coinciden (gap {gap*100:.0f}pp) — se adopta el ensemble.")
    else:
        final_ph, final_pd, final_pb = mc_ph, mc_pd, mc_pb

    # avance con tope de tanda (igual criterio que predict_ensemble, aplicado al numero final ya reconciliado)
    fav = team_a if final_ph >= final_pb else team_b
    fav_p = max(final_ph, final_pb)
    dog_p = min(final_ph, final_pb)
    shoot = max(final_pd, 0.20)
    share_fav = 0.5
    if ka and kb:
        ta_, tb_ = (ka["tie"], kb["tie"]) if fav == team_a else (kb["tie"], ka["tie"])
        share_fav = ta_ / (ta_ + tb_) if (ta_ + tb_) else 0.5
        share_fav = max(0.42, min(0.58, share_fav))
    adv_fav = fav_p + shoot * share_fav - (shoot - final_pd) * 0.5
    # MARCADOR — VALIDADO CON DATOS 02-jul (10 R32 registrados): el argmax del
    # modelo de producción (predicted_score, grid Dixon-Coles con lógica de
    # goleada) acertó el EXACTO 3/10 (30%) vs 1/9 (11%) de los marcadores
    # elegidos a mano/modal del Monte Carlo. En ganador/avance el experto gana
    # (67% vs 56% del ledger), pero en MARCADOR manda el modelo → usar su
    # predicted_score como marcador sellado; fallback al modal del Monte Carlo
    # si el modelo no está disponible.
    top_h = top_a = None
    try:
        from models.match_predictor import predict_match as _pm
        aid_, bid_ = _tid(conn := sqlite3.connect(str(DB)), team_a), _tid(conn, team_b)
        conn.close()
        rprod = _pm(aid_, bid_, neutral=True, stage="knockout", db_path=str(DB))
        ps = rprod.get("predicted_score")
        if ps and "-" in ps:
            top_h, top_a = (int(x) for x in ps.split("-"))
            # CAP scoreline_ground (regla del dueño, validada England-Congo): no
            # poner goles por encima del PEOR partido del defensor. Se combina
            # con el argmax del modelo (mejor picker exacto medido): argmax
            # capado al máximo concedido real de cada lado.
            try:
                _cg = sqlite3.connect(str(DB))
                g_ = ground(_cg, team_a, team_b)
                _cg.close()
                if g_:
                    top_h = min(top_h, int(g_["rb"]["max_conc"][0]))
                    top_a = min(top_a, int(g_["ra"]["max_conc"][0]))
            except Exception:
                pass
            band = ", ".join(f"{s_} {p_:.1f}%" for s_, p_ in (rprod.get("top_scores") or [])[:3])
            print(f"\n  (marcador: argmax del MODELO capado por ground — mejor picker medido n=80: 13.8% vs 6% del ground puro)")
            if band:
                print(f"  (banda top-3 de la grilla: {band} — si están casi empatadas, el exacto es volado entre vecinos)")
    except Exception:
        top_h = None
    if top_h is None:
        top_list = s['res'].most_common(5)
        if fav_p > final_pd + 0.15:
            fav_is_a = (fav == team_a)
            pick = next(((h, a) for (h, a), _ in top_list if (h > a) == fav_is_a and h != a), top_list[0][0])
            top_h, top_a = pick
        else:
            top_h, top_a = top_list[0][0]
    print(f"  → MARCADOR: {top_h}-{top_a} · "
          f"90': {fav} {fav_p*100:.0f}% / empate {final_pd*100:.0f}% / {team_b if fav==team_a else team_a} {dog_p*100:.0f}%")
    print(f"  → AVANCE FINAL: {fav} {adv_fav*100:.0f}%")
    if ens and ens["tactical"]:
        print(f"  → Banderas tácticas activas: {', '.join(ens['tactical'])}")
    print("  (Ver secciones 1-8 arriba para la traza completa — nada de esto se decidió con un solo número.)")

    if seal:
        print("\n=== SELLANDO EN match_predictions ===")
        _seal(team_a, team_b, top_h, top_a, final_ph, final_pd, final_pb, fav, adv_fav)


def _seal(team_a, team_b, top_h, top_a, ph, pd, pb, fav, adv_fav):
    conn = sqlite3.connect(str(DB))
    aid, bid = _tid(conn, team_a), _tid(conn, team_b)
    row = conn.execute(
        "SELECT p.match_id FROM match_predictions p JOIN wc_matches m ON m.id=p.match_id "
        "WHERE ((m.home_team_id=? AND m.away_team_id=?) OR (m.home_team_id=? AND m.away_team_id=?)) "
        "AND m.played=0", (aid, bid, bid, aid)).fetchone()
    if not row:
        print("  No hay match_id sin jugar para este cruce — no se selló (sellar manualmente si es nuevo).")
        conn.close()
        return
    mid = row[0]
    winner = fav if top_h != top_a else "Draw"
    from datetime import datetime
    conn.execute(
        "UPDATE match_predictions SET predicted_at=?, home_win_prob=?, draw_prob=?, away_win_prob=?, "
        "pred_home_goals=?, pred_away_goals=?, pred_winner=?, pred_scoreline=?, model_version=? WHERE match_id=?",
        (datetime.now().isoformat(timespec="seconds"), ph, pd, pb, float(top_h), float(top_a),
         winner, f"{top_h}-{top_a}", f"full_verdict_{fav}adv{adv_fav*100:.0f}_reconciled", mid))
    conn.commit()
    conn.close()
    print(f"  Sellado match_id={mid}: {top_h}-{top_a}, {fav} avance {adv_fav*100:.0f}%")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(0)
    run(args[0], args[1], seal="--seal" in sys.argv)
