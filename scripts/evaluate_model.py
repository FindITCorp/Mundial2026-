"""
evaluate_model.py — Evalúa predicciones pasadas vs resultados reales.

Qué hace:
1. Cruza match_predictions con wc_matches donde ya hay resultado
2. Calcula métricas: accuracy (ganador correcto), Brier score, error de goles
3. Detecta sesgos sistémicos (favoritismo, sub/sobre estimación de goles)
4. Guarda análisis en model_bias y model_evaluation_log
5. Imprime resumen legible para que puedas entender QUÉ está fallando

Filosofía: no fuerza resultados, solo muestra los patrones.
Los ajustes en lambda_scale y bias se propagan a match_predictor.py
via load_model_bias().
"""
import sqlite3
import math
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

DB = BASE_DIR / "data" / "mundial2026.db"


# ── Métricas ──────────────────────────────────────────────────────────────────

def _brier(prob_correct: float) -> float:
    """Brier score para UN resultado: (p_correct - 1)^2. Rango 0–1, menor=mejor."""
    return (prob_correct - 1.0) ** 2


def _winner(gh, ga, hname, aname):
    if gh > ga: return hname
    if ga > gh: return aname
    return "Draw"


def _log_loss(p: float) -> float:
    p = max(1e-6, min(1 - 1e-6, p))
    return -math.log(p)


# ── Evaluación ───────────────────────────────────────────────────────────────

def evaluate(db_path=DB, verbose=True) -> dict:
    conn = sqlite3.connect(str(db_path))
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    # Partidos con predicción Y resultado real
    rows = conn.execute("""
        SELECT
            mp.match_id,
            wm.home_team_name, wm.away_team_name,
            wm.score_home, wm.score_away,
            mp.home_win_prob AS hw_raw, mp.draw_prob AS dw_raw, mp.away_win_prob AS aw_raw,
            mp.pred_home_goals, mp.pred_away_goals,
            mp.pred_winner, mp.pred_scoreline
        FROM match_predictions mp
        JOIN wc_matches wm ON wm.id = mp.match_id
        WHERE wm.score_home IS NOT NULL
          AND (mp.evaluated = 0 OR 1=1)          -- evalúa siempre para tener histórico fresco
          AND wm.home_team_name IS NOT NULL
        ORDER BY wm.date
    """).fetchall()

    if not rows:
        print("[evaluate_model] No hay predicciones con resultado para evaluar.")
        conn.close()
        return {}

    # ── Acumular métricas ────────────────────────────────────────────────────
    n = len(rows)
    correct_winner = 0
    brier_total = 0.0
    log_loss_total = 0.0
    goal_error_home = []   # predicho - real
    goal_error_away = []
    home_overestimate = 0  # veces que el modelo sobreestimó prob local
    draw_missed = 0        # empates que el modelo no predijo
    upset_missed = 0       # sorpresas que el modelo no vio venir

    log_entries = []

    for (mid, hname, aname, rh, ra, hw_raw, dw_raw, aw_raw, ph, pa, pw, psc) in rows:
        rh, ra = int(rh or 0), int(ra or 0)
        real_w = _winner(rh, ra, hname, aname)
        pred_w = pw or _winner(round(ph or 1.3), round(pa or 1.2), hname, aname)

        # Normalizar a [0,1] — las probs se guardan como porcentaje (0-100)
        hw = (hw_raw or 33.3) / 100.0
        dw = (dw_raw or 33.3) / 100.0
        aw = (aw_raw or 33.3) / 100.0
        total = hw + dw + aw
        if total > 0:
            hw, dw, aw = hw / total, dw / total, aw / total

        # Probabilidad del resultado que REALMENTE ocurrió
        if real_w == hname:
            p_correct = hw
        elif real_w == aname:
            p_correct = aw
        else:
            p_correct = dw

        b = _brier(p_correct)
        ll = _log_loss(p_correct)
        brier_total += b
        log_loss_total += ll

        ok = (real_w == pred_w)
        if ok:
            correct_winner += 1

        goal_error_home.append((ph or 1.3) - rh)
        goal_error_away.append((pa or 1.2) - ra)

        # Detectar patrones
        notes = []
        if real_w == "Draw" and pred_w != "Draw":
            draw_missed += 1
            notes.append("empate_no_predicho")
        if real_w != pred_w and (hw or 0) > 0.55:
            home_overestimate += 1
            notes.append("favorito_local_fallido")
        if real_w != pred_w and (aw or 0) > 0.50 and real_w == hname:
            upset_missed += 1
            notes.append("sorpresa_no_vista")

        log_entries.append((
            now, mid, hname, aname,
            rh, ra, ph, pa,
            real_w, pred_w, int(ok),
            round(b, 4),
            "; ".join(notes) if notes else None
        ))

    # ── Calcular sesgos ──────────────────────────────────────────────────────
    avg_brier = brier_total / n
    avg_ll    = log_loss_total / n
    accuracy  = correct_winner / n
    home_bias = sum(goal_error_home) / n   # positivo = sobreestima goles locales
    away_bias = sum(goal_error_away) / n

    # lambda_scale: si el modelo predijo sistemáticamente más goles de los que cayeron
    total_real  = sum((int(r[3] or 0) + int(r[4] or 0)) for r in rows)
    total_pred2 = sum((r[8] or 1.3) + (r[9] or 1.2) for r in rows)
    lambda_scale = (total_real / total_pred2) if total_pred2 > 0 else 1.0
    lambda_scale = max(0.80, min(1.20, lambda_scale))  # clamp ±20%

    # ── Persistir ────────────────────────────────────────────────────────────
    # Limpiar log anterior y reinsertar (para tener siempre el estado más fresco)
    # INSERT OR REPLACE — preserva historial, solo actualiza partidos ya evaluados
    conn.executemany("""
        INSERT OR REPLACE INTO model_evaluation_log
          (evaluated_at, match_id, home_name, away_name,
           real_home_goals, real_away_goals, pred_home_goals, pred_away_goals,
           real_winner, pred_winner, correct_winner, brier_score, error_notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, log_entries)

    # model_bias: acumula historial, no borra — el predictor lee siempre el último
    notes_str = []
    if draw_missed / n > 0.40:
        notes_str.append("modelo subestima empates")
    if home_overestimate / n > 0.30:
        notes_str.append("favorito local falla demasiado")
    if upset_missed / n > 0.15:
        notes_str.append("no detecta sorpresas")
    if abs(home_bias) > 0.4:
        notes_str.append(f"sesgo goles locales: {home_bias:+.2f}")
    if abs(away_bias) > 0.4:
        notes_str.append(f"sesgo goles visitantes: {away_bias:+.2f}")

    conn.execute("""
        INSERT INTO model_bias
          (updated_at, n_matches, home_lambda_bias, away_lambda_bias,
           brier_home, brier_draw, brier_away, win_overestimate,
           draw_underestimate, lambda_scale, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        now, n,
        round(home_bias, 4), round(away_bias, 4),
        round(avg_brier, 4), round(avg_brier, 4), round(avg_brier, 4),
        round(home_overestimate / n, 3),
        round(draw_missed / n, 3),
        round(lambda_scale, 4),
        "; ".join(notes_str) if notes_str else "sin sesgos detectados"
    ))

    # Marcar predicciones como evaluadas
    conn.execute("UPDATE match_predictions SET evaluated=1 WHERE match_id IN "
                 "(SELECT match_id FROM model_evaluation_log)")

    # Snapshot diario — nunca se borra, acumula el progreso del modelo
    today_snap = now[:10]
    existing_snap = conn.execute(
        "SELECT id FROM model_calibration_history WHERE snapshot_date=?", (today_snap,)
    ).fetchone()
    if not existing_snap:
        conn.execute("""
            INSERT INTO model_calibration_history
              (snapshot_date, n_matches, accuracy, avg_brier, avg_log_loss,
               lambda_scale, home_bias, away_bias, draw_miss_rate, upset_miss_rate, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (today_snap, n, round(accuracy, 3), round(avg_brier, 4), round(avg_ll, 4),
              round(lambda_scale, 4), round(home_bias, 3), round(away_bias, 3),
              round(draw_missed / n, 3), round(upset_missed / n, 3),
              "; ".join(notes_str) if notes_str else "sin sesgos detectados"))

    conn.commit()

    # ── Reporte ──────────────────────────────────────────────────────────────
    summary = {
        "n_matches": n,
        "accuracy": round(accuracy, 3),
        "avg_brier": round(avg_brier, 4),
        "avg_log_loss": round(avg_ll, 4),
        "home_lambda_bias": round(home_bias, 3),
        "away_lambda_bias": round(away_bias, 3),
        "lambda_scale": round(lambda_scale, 4),
        "draw_miss_rate": round(draw_missed / n, 3),
        "upset_miss_rate": round(upset_missed / n, 3),
        "notes": notes_str,
    }

    if verbose:
        _print_report(summary, log_entries, rows)

    conn.close()
    return summary


def _print_report(s, log_entries, rows):
    sep = "─" * 62
    print(f"\n{'═'*62}")
    print(f"  EVALUACIÓN DEL MODELO  ({s['n_matches']} partidos)")
    print(f"{'═'*62}")
    print(f"  Accuracy (ganador correcto):  {s['accuracy']*100:.1f}%")
    print(f"  Brier score (0=perfecto):     {s['avg_brier']:.4f}")
    print(f"  Log-loss:                     {s['avg_log_loss']:.4f}")
    print(f"  Sesgo goles locales:          {s['home_lambda_bias']:+.3f} goles/partido")
    print(f"  Sesgo goles visitantes:       {s['away_lambda_bias']:+.3f} goles/partido")
    print(f"  Escala lambda sugerida:       ×{s['lambda_scale']:.3f}")
    print(f"  Tasa empates no predichos:    {s['draw_miss_rate']*100:.1f}%")
    print(f"  Tasa sorpresas no vistas:     {s['upset_miss_rate']*100:.1f}%")
    print(sep)

    if s["notes"]:
        print("  ⚠  PATRONES DETECTADOS:")
        for note in s["notes"]:
            print(f"     • {note}")
        print(sep)

    # Mostrar los partidos donde el modelo se equivocó más
    wrong = [(e[2], e[3], e[4], e[5], e[6], e[7], e[8], e[9], e[11])
             for e in log_entries if not e[10]]
    if wrong:
        print(f"  PARTIDOS FALLADOS ({len(wrong)}):")
        for (hn, an, rh, ra, ph, pa, rw, pw, bs) in wrong[:10]:
            print(f"  {hn} {rh}-{ra} {an}  |  predicho: {pw} ({ph:.1f}-{pa:.1f})  Brier:{bs:.3f}")
    print(f"{'═'*62}\n")


def load_model_bias(db_path=DB) -> dict:
    """
    Devuelve el último ajuste de bias para que match_predictor.py lo aplique.
    Uso:
        bias = load_model_bias()
        lambda_h *= bias['lambda_scale']
        lambda_h -= bias['home_lambda_bias']
    """
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("""
            SELECT lambda_scale, home_lambda_bias, away_lambda_bias,
                   draw_underestimate, win_overestimate
            FROM model_bias ORDER BY id DESC LIMIT 1
        """).fetchone()
        conn.close()
        if row:
            return {
                "lambda_scale":       row[0] or 1.0,
                "home_lambda_bias":   row[1] or 0.0,
                "away_lambda_bias":   row[2] or 0.0,
                "draw_underestimate": row[3] or 0.0,
                "win_overestimate":   row[4] or 0.0,
            }
    except Exception:
        pass
    return {"lambda_scale": 1.0, "home_lambda_bias": 0.0, "away_lambda_bias": 0.0,
            "draw_underestimate": 0.0, "win_overestimate": 0.0}


if __name__ == "__main__":
    evaluate()
