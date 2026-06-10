#!/usr/bin/env python3
"""
validate_model.py — Backtest del motor de predicción sobre resultados reales.

Mide la calidad del modelo (accuracy de ganador + Brier score multiclase)
sobre los partidos recientes registrados en team_matches entre equipos
clasificados al WC2026, y compara A/B el impacto del factor de experiencia
mundialista (use_veteran=True vs False).

Métricas:
  accuracy      % de partidos donde el resultado más probable coincidió
  brier         error cuadrático medio de las probabilidades (menor = mejor;
                0.6667 = modelo uniforme 33/33/33)
  draw_recall   % de empates reales que el modelo asignó >= 25% a empate

Uso:
    python scripts/validate_model.py                # últimos 180 días
    python scripts/validate_model.py --days 365
    python scripts/validate_model.py --min-elo-gap 0   # todos los partidos
"""

import sys
import sqlite3
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"
sys.path.insert(0, str(ROOT))

from models.match_predictor import predict_match  # noqa: E402


def load_matches(conn, days: int) -> list[dict]:
    """Partidos únicos recientes entre equipos WC2026 con resultado conocido."""
    rows = conn.execute("""
        SELECT tm.team_id AS home_id, tm.opponent_id AS away_id,
               tm.goals_for AS gh, tm.goals_against AS ga,
               tm.venue, tm.date, tm.competition
        FROM team_matches tm
        JOIN teams th ON th.id = tm.team_id
        JOIN teams ta ON ta.id = tm.opponent_id
        WHERE tm.goals_for IS NOT NULL
          AND tm.date >= date('now', ?)
          AND tm.venue IN ('home', 'neutral')
        ORDER BY tm.date DESC
    """, (f"-{days} days",)).fetchall()

    seen, matches = set(), []
    for r in rows:
        key = (tuple(sorted([r["home_id"], r["away_id"]])), r["date"])
        if key in seen:
            continue
        seen.add(key)
        matches.append(dict(r))
    return matches


def evaluate(matches: list[dict], use_veteran: bool) -> dict:
    """Corre el modelo sobre los partidos y agrega métricas."""
    n = correct = 0
    brier_sum = 0.0
    draws_total = draws_flagged = 0

    for m in matches:
        try:
            r = predict_match(
                m["home_id"], m["away_id"],
                neutral=(m["venue"] != "home"),
                use_veteran=use_veteran,
            )
        except Exception:
            continue

        ph, pd, pa = (r["prob_home_win"] / 100,
                      r["prob_draw"] / 100,
                      r["prob_away_win"] / 100)

        # Resultado real
        if m["gh"] > m["ga"]:
            actual = "H"
        elif m["gh"] < m["ga"]:
            actual = "A"
        else:
            actual = "D"

        # Predicción más probable
        pred = max([("H", ph), ("D", pd), ("A", pa)], key=lambda x: x[1])[0]
        if pred == actual:
            correct += 1

        # Brier multiclase
        oh, od, oa = (actual == "H"), (actual == "D"), (actual == "A")
        brier_sum += (ph - oh) ** 2 + (pd - od) ** 2 + (pa - oa) ** 2

        if actual == "D":
            draws_total += 1
            if pd >= 0.25:
                draws_flagged += 1

        n += 1

    return {
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "brier": brier_sum / n if n else 0.0,
        "draw_recall": draws_flagged / draws_total if draws_total else None,
        "draws_total": draws_total,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    matches = load_matches(conn, args.days)
    conn.close()

    print(f"📊 Backtest sobre {len(matches)} partidos reales "
          f"(últimos {args.days} días, equipos WC2026)\n")
    if len(matches) < 10:
        print("⚠️  Muy pocos partidos para una validación significativa.")

    base = evaluate(matches, use_veteran=False)
    full = evaluate(matches, use_veteran=True)

    print(f"{'Métrica':<22}{'SIN veterano':>14}{'CON veterano':>14}{'Δ':>10}")
    print("-" * 60)
    print(f"{'Partidos evaluados':<22}{base['n']:>14}{full['n']:>14}")
    print(f"{'Accuracy ganador':<22}{base['accuracy']*100:>13.1f}%"
          f"{full['accuracy']*100:>13.1f}%"
          f"{(full['accuracy']-base['accuracy'])*100:>+9.1f}pp")
    print(f"{'Brier score (↓)':<22}{base['brier']:>14.4f}{full['brier']:>14.4f}"
          f"{full['brier']-base['brier']:>+10.4f}")
    if base["draw_recall"] is not None:
        print(f"{'Draw recall (≥25%)':<22}{base['draw_recall']*100:>13.1f}%"
              f"{full['draw_recall']*100:>13.1f}%   ({base['draws_total']} empates)")

    print()
    if full["brier"] <= base["brier"] and full["accuracy"] >= base["accuracy"]:
        print("✅ El factor veterano MEJORA o iguala el modelo — mantener activo.")
    elif full["brier"] > base["brier"] + 0.005:
        print("⚠️  El factor veterano EMPEORA el Brier — revisar calibración.")
    else:
        print("➖ Impacto neutro en esta ventana (esperado: la señal aparece en torneos).")


if __name__ == "__main__":
    main()
