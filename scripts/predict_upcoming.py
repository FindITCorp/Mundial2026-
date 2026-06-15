"""
predict_upcoming.py — Genera y guarda predicciones para los próximos partidos WC.

Ejecutar ANTES de cada jornada (el workflow daily_improvement lo corre).
Guarda en match_predictions para que luego evaluate_model.py compare vs resultados reales.
"""
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

DB = BASE_DIR / "data" / "mundial2026.db"


# Anfitriones WC2026: por formato FIFA juegan TODA la fase de grupos en su
# país (México: Azteca/Guadalajara; USA: LA/Seattle; Canadá: Toronto/Vancouver).
# El inaugural México-Sudáfrica se predecía como cancha neutral (bug 11-jun).
# Eliminatorias: neutral (la sede depende del bracket y no está cargada).
HOSTS = {"Mexico", "USA", "Canada"}


def _predict_safe(home_id, away_id, db_path, neutral=True, stage="group"):
    """Llama predict_match y captura cualquier excepción."""
    try:
        from models.match_predictor import predict_match
        return predict_match(home_id, away_id, neutral=neutral,
                             stage=stage, db_path=db_path)
    except Exception as e:
        print(f"    [WARN] predict_match falló: {e}")
        return None


def store_predictions(db_path=DB, days_ahead=3):
    conn = sqlite3.connect(str(db_path))
    today = date.today()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()

    upcoming = conn.execute("""
        SELECT id, home_team_id, away_team_id, home_team_name, away_team_name,
               date, stage
        FROM wc_matches
        WHERE date >= ? AND date <= ?
          AND (score_home IS NULL OR played = 0)
          AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL
        ORDER BY date
    """, (today_str, cutoff)).fetchall()

    print(f"[predict_upcoming] {len(upcoming)} partidos próximos ({today_str} → {cutoff})")
    stored = 0

    for match_id, h_id, a_id, h_name, a_name, mdate, stage in upcoming:
        stage = (stage or "group").lower()
        is_group = "group" in stage
        is_knockout = any(k in stage for k in
                          ("knockout", "round", "quarter", "semi", "final", "32", "16"))
        # Anfitrión jugando en casa en fase de grupos → localía real
        neutral = not (is_group and h_name in HOSTS)
        loc = " [LOCAL]" if not neutral else ""
        print(f"  Prediciendo {h_name} vs {a_name} ({mdate}){loc}...", end=" ")
        result = _predict_safe(h_id, a_id, db_path,
                               neutral=neutral,
                               stage="knockout" if is_knockout else "group")
        if result is None:
            print("SKIPPED")
            continue

        hw = result.get("prob_home_win") or result.get("home_win_prob") or 0.33
        dw = result.get("prob_draw") or result.get("draw_prob") or 0.33
        aw = result.get("prob_away_win") or result.get("away_win_prob") or 0.33
        lh = result.get("lambda_home") or 1.3
        la = result.get("lambda_away") or 1.2

        if hw >= dw and hw >= aw:
            winner = h_name
        elif aw >= dw and aw >= hw:
            winner = a_name
        else:
            winner = "Draw"

        # PRONÓSTICO OFICIAL: predicted_score del modelo (puede ser goleada_band
        # top score cuando hay mismatch extremo, o argmax del grid en partidos normales).
        # Se prefiere result["predicted_score"] que ya incorpora la lógica de goleada.
        top = result.get("top_scores") or []
        pred_score = result.get("predicted_score")
        if pred_score:
            scoreline = pred_score
            # Buscar probabilidad exacta de este marcador en el top_scores
            score_prob_val = next((p for s, p in top if s == pred_score), None)
            score_prob = round(score_prob_val, 1) if score_prob_val is not None else (round(top[0][1], 1) if top else None)
        elif top:
            scoreline = top[0][0]
            score_prob = round(top[0][1], 1)
        else:
            scoreline = f"{int(lh)}-{int(la)}"
            score_prob = None

        # Siempre reemplaza — el modelo mejora cada día con bias actualizado.
        # Sella nombres + versión: si el fixture cambia bajo la predicción,
        # la evaluación puede detectarlo (lección del lote corrupto v1.0 del 09-jun).
        conn.execute("""
            INSERT INTO match_predictions
              (match_id, predicted_at, home_win_prob, draw_prob, away_win_prob,
               pred_home_goals, pred_away_goals, pred_winner, pred_scoreline,
               pred_score_prob, model_version, home_team_name, away_team_name)
            VALUES (?,?,?,?,?,?,?,?,?,?,'1.5-argmax',?,?)
            ON CONFLICT(match_id) DO UPDATE SET
              predicted_at    = excluded.predicted_at,
              home_win_prob   = excluded.home_win_prob,
              draw_prob       = excluded.draw_prob,
              away_win_prob   = excluded.away_win_prob,
              pred_home_goals = excluded.pred_home_goals,
              pred_away_goals = excluded.pred_away_goals,
              pred_winner     = excluded.pred_winner,
              pred_scoreline  = excluded.pred_scoreline,
              pred_score_prob = excluded.pred_score_prob,
              model_version   = excluded.model_version,
              home_team_name  = excluded.home_team_name,
              away_team_name  = excluded.away_team_name,
              evaluated       = 0
        """, (match_id, today_str, hw, dw, aw, lh, la, winner, scoreline,
              score_prob, h_name, a_name))
        stored += 1
        print(f"OK ({winner}, exacto {scoreline}" +
              (f" @{score_prob}%" if score_prob else "") + ")")

    conn.commit()
    conn.close()
    print(f"[predict_upcoming] {stored} nuevas predicciones guardadas.")
    return stored


if __name__ == "__main__":
    store_predictions()
