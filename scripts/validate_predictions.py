"""
validate_predictions.py — GATE DE INTEGRIDAD obligatorio antes de presentar/sellar
cualquier prediccion. Nace 01-jul porque el dueno detecto DOS inconsistencias reales
en la misma sesion (Belgica-Senegal 2-2 contradecia su propio "ganador"; resulto que
Australia-Egypt tenia el MISMO bug y nadie lo habia revisado) — la validacion era
manual y ad-hoc, no sistematica. Esto la hace repetible y la corre TODO, no solo
lo que se pregunta.

Chequeos (todos automaticos, sin juicio subjetivo):
  1. Probabilidades: home+draw+away ~= 1.0 (o ~=100 en filas viejas de otra escala).
  2. CONSISTENCIA marcador<->ganador: si pred_scoreline es EMPATE (h==a), pred_winner
     debe ser 'Draw'/'DRAW' (semantica de penales). Si NO es empate, pred_winner debe
     ser el nombre del equipo que gana ese marcador. Cualquier otra cosa es un bug
     (el que se encontro dos veces hoy).
  3. CONSISTENCIA marcador<->goles: pred_home_goals/pred_away_goals deben coincidir
     con los numeros de pred_scoreline (dentro de redondeo).
  4. Para partidos NO jugados con equipos identificables: el marcador sellado debe
     aparecer en el TOP-8 de `simulate_match.simulate()` — si no, es un marcador
     sacado del heuristico de scoreline_ground sin cruzar contra la simulacion real
     (el bug de Belgica-Senegal).

Uso:
    python scripts/validate_predictions.py                 # todo el pipeline activo (R32 + grupos WC2026)
    python scripts/validate_predictions.py --all            # incluye friendlies/calibracion vieja tambien
    python scripts/validate_predictions.py --fix            # corrige automaticamente lo que se pueda (marcador<->ganador, marcador<->goles)
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"

WC2026_START = "2026-06-11"


def _is_auto_pipeline(model_version):
    """
    El pipeline automatico (predict_upcoming.py, GitHub Action) sella 'winner' con
    el argmax de las probabilidades 1X2 AGREGADAS, y 'scoreline' con el argmax del
    GRID de marcador (Dixon-Coles, con ajuste de baja anotacion) — son dos
    estadisticos DISTINTOS por diseno (0-0 puede ser el marcador exacto mas probable
    aunque el equipo tenga mas prob agregada de ganar, porque esa prob se reparte en
    muchos marcadores: 1-0,2-0,2-1... mientras el empate se concentra en pocos).
    Verificado leyendo predict_upcoming.py (lineas 71-99) antes de asumir bug.
    Por eso el chequeo marcador<->ganador/goles NO aplica a estas filas — solo a
    mis sellos EXPERTOS (expert_/integral_/ensemble_/data_driven_), donde marcador y
    ganador SI deben ser la misma cosa (es un solo pronostico coherente).
    """
    return bool(model_version) and model_version[0].isdigit()


def _parse_scoreline(s):
    if not s or "-" not in s:
        return None
    try:
        h, a = s.split("-")
        return float(h), float(a)
    except ValueError:
        return None


def _rows(conn, include_all=False):
    q = ("SELECT p.id, p.match_id, p.home_team_name, p.away_team_name, p.home_win_prob, "
         "p.draw_prob, p.away_win_prob, p.pred_home_goals, p.pred_away_goals, p.pred_winner, "
         "p.pred_scoreline, p.model_version, m.played, m.score_home, m.score_away, m.date "
         "FROM match_predictions p JOIN wc_matches m ON m.id=p.match_id")
    if not include_all:
        q += f" WHERE m.date >= '{WC2026_START}' AND m.stage IN ('group','R32')"
    q += " ORDER BY p.match_id"
    return conn.execute(q).fetchall()


def validate(conn, include_all=False, fix=False):
    issues = []
    for (pid, mid, hn, an, ph, pd_, pa, phg, pag, winner, scoreline, mv, played, sh, sa, date) in _rows(conn, include_all):
        tag = f"match_id={mid} ({hn} vs {an}) [{mv}]"

        # 1) probabilidades suman ~1 (o ~100)
        if ph is not None and pd_ is not None and pa is not None:
            total = ph + pd_ + pa
            scale = 100 if total > 3 else 1
            if abs(total - scale) > 0.05 * scale:
                issues.append((mid, "PROBS_NO_SUMAN", f"{tag}: {ph}+{pd_}+{pa}={total} (esperado ~{scale})"))

        sc = _parse_scoreline(scoreline)
        auto = _is_auto_pipeline(mv)
        if sc and not auto:
            h, a = sc
            is_draw = abs(h - a) < 1e-9
            expected_winner = "Draw" if is_draw else (hn if h > a else an)
            w_norm = (winner or "").strip().lower()
            exp_norm = expected_winner.strip().lower()
            ok = (w_norm == exp_norm) or (is_draw and w_norm in ("draw", "empate"))
            if not ok:
                issues.append((mid, "MARCADOR_VS_GANADOR",
                               f"{tag}: scoreline='{scoreline}' implica ganador='{expected_winner}' pero pred_winner='{winner}'"))
                if fix:
                    conn.execute("UPDATE match_predictions SET pred_winner=? WHERE id=?", (expected_winner, pid))

            # 3) marcador vs goles numericos (solo sellos EXPERTOS: en el pipeline
            # automatico pred_home_goals=lambda continua, scoreline=argmax discreto
            # del grid — DIVERGEN por diseno, no es un bug ahi)
            if phg is not None and pag is not None:
                if abs(phg - h) > 0.05 or abs(pag - a) > 0.05:
                    issues.append((mid, "MARCADOR_VS_GOLES",
                                   f"{tag}: scoreline='{scoreline}' pero pred_home_goals={phg}/pred_away_goals={pag}"))
                    if fix:
                        conn.execute("UPDATE match_predictions SET pred_home_goals=?, pred_away_goals=? WHERE id=?",
                                     (h, a, pid))

            # 4) marcador vs top-8 de simulate_match (solo partidos NO jugados, cuesta caro)
            if not played and hn and an:
                try:
                    from scripts.simulate_match import simulate
                    s = simulate(conn, hn, an, n=20000)
                    top = [f"{x}-{y}" for (x, y), _ in s["res"].most_common(8)]
                    if scoreline not in top:
                        issues.append((mid, "MARCADOR_FUERA_DE_TOP8",
                                       f"{tag}: '{scoreline}' NO está en el top-8 de simulate_match ({', '.join(top)})"))
                except Exception as e:
                    issues.append((mid, "SIM_ERROR", f"{tag}: no se pudo simular ({e})"))

        # ganador evaluado vs marcador real (solo para diagnostico, no es 'bug' sino desempeño)
        if played and sh is not None and sa is not None and sc:
            pass  # eso lo cubre calibration_ledger.py, no repetir aqui

    if fix and issues:
        conn.commit()
    return issues


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    include_all = "--all" in sys.argv
    fix = "--fix" in sys.argv
    issues = validate(conn, include_all=include_all, fix=fix)
    if not issues:
        print("OK — sin inconsistencias detectadas en el alcance revisado.")
    else:
        print(f"⚠ {len(issues)} inconsistencias encontradas" + (" (corregidas)" if fix else " (correr con --fix para corregir automáticamente lo posible)") + ":\n")
        for mid, kind, msg in issues:
            print(f"  [{kind}] {msg}")
    conn.close()
