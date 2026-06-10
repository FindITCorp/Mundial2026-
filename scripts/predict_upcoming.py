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


def _predict_safe(home_id, away_id, db_path):
    """Llama predict_match y captura cualquier excepción."""
    try:
        from models.match_predictor import predict_match
        return predict_match(home_id, away_id, neutral=True, db_path=db_path)
    except Exception as e:
        print(f"    [WARN] predict_match falló: {e}")
        return None


def store_predictions(db_path=DB, days_ahead=3):
    conn = sqlite3.connect(str(db_path))
    today = date.today()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()

    upcoming = conn.execute("""
        SELECT id, home_team_id, away_team_id, home_team_name, away_team_name, date
        FROM wc_matches
        WHERE date >= ? AND date <= ?
          AND (score_home IS NULL OR played = 0)
          AND home_team_id IS NOT NULL AND away_team_id IS NOT NULL
        ORDER BY date
    """, (today_str, cutoff)).fetchall()

    print(f"[predict_upcoming] {len(upcoming)} partidos próximos ({today_str} → {cutoff})")
    stored = 0

    for match_id, h_id, a_id, h_name, a_name, mdate in upcoming:
        print(f"  Prediciendo {h_name} vs {a_name} ({mdate})...", end=" ")
        result = _predict_safe(h_id, a_id, db_path)
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

        scoreline = f"{round(lh)}-{round(la)}"

        # Siempre reemplaza — el modelo mejora cada día con bias actualizado.
        # Sella nombres + versión: si el fixture cambia bajo la predicción,
        # la evaluación puede detectarlo (lección del lote corrupto v1.0 del 09-jun).
        conn.execute("""
            INSERT INTO match_predictions
              (match_id, predicted_at, home_win_prob, draw_prob, away_win_prob,
               pred_home_goals, pred_away_goals, pred_winner, pred_scoreline,
               model_version, home_team_name, away_team_name)
            VALUES (?,?,?,?,?,?,?,?,?,'1.2-veteran',?,?)
            ON CONFLICT(match_id) DO UPDATE SET
              predicted_at    = excluded.predicted_at,
              home_win_prob   = excluded.home_win_prob,
              draw_prob       = excluded.draw_prob,
              away_win_prob   = excluded.away_win_prob,
              pred_home_goals = excluded.pred_home_goals,
              pred_away_goals = excluded.pred_away_goals,
              pred_winner     = excluded.pred_winner,
              pred_scoreline  = excluded.pred_scoreline,
              model_version   = excluded.model_version,
              home_team_name  = excluded.home_team_name,
              away_team_name  = excluded.away_team_name,
              evaluated       = 0
        """, (match_id, today_str, hw, dw, aw, lh, la, winner, scoreline,
              h_name, a_name))
        stored += 1
        print(f"OK ({winner}, {scoreline})")

    conn.commit()
    conn.close()
    print(f"[predict_upcoming] {stored} nuevas predicciones guardadas.")
    return stored


if __name__ == "__main__":
    store_predictions()
