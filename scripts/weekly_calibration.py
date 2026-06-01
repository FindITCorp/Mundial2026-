#!/usr/bin/env python3
"""
weekly_calibration.py — Recalibra BASE_GOALS basado en resultados recientes.

Analiza los últimos N partidos registrados en team_matches y ajusta BASE_GOALS
en match_predictor.py si la desviación es significativa (>3pp en Over/Under 2.5).

Solo recomienda cambios conservadores (±0.02 por semana máx) para evitar
overfitting a una semana ruidosa.

Uso:
    python scripts/weekly_calibration.py          # analiza y ajusta si necesario
    python scripts/weekly_calibration.py --dry-run  # solo informa, no modifica
"""

import sys
import sqlite3
import argparse
import re
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"
MODEL   = ROOT / "models" / "match_predictor.py"

sys.path.insert(0, str(ROOT))
from models.match_predictor import predict_match

# Umbral mínimo para recalibrar (evita ruido de semana pequeña)
MIN_MATCHES_TO_CALIBRATE = 20
MAX_DELTA_PER_WEEK       = 0.03   # cambio máx en BASE_GOALS por calibración
TARGET_OVER25_RATE       = 0.50   # ~50% es el rate histórico internacional


def run_calibration(dry_run: bool = False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Últimos 60 partidos registrados con los dos lados (deduplicados por fecha+equipo)
    rows = conn.execute("""
        SELECT m.team_id, m.opponent_id, m.goals_for, m.goals_against,
               m.result, m.date, m.competition
        FROM team_matches m
        WHERE m.goals_for IS NOT NULL AND m.opponent_id IS NOT NULL
          AND m.date >= date('now', '-90 days')
        ORDER BY m.date DESC
        LIMIT 100
    """).fetchall()

    seen = set()
    matches = []
    for r in rows:
        key = tuple(sorted([r["team_id"], r["opponent_id"]])) + (r["date"],)
        if key not in seen:
            seen.add(key)
            matches.append(r)

    n = len(matches)
    print(f"📊 Calibración semanal — {n} partidos únicos (últimos 90 días)")

    if n < MIN_MATCHES_TO_CALIBRATE:
        print(f"  ⚠️  Solo {n} partidos — necesita {MIN_MATCHES_TO_CALIBRATE}+ para calibrar")
        conn.close()
        return

    # Métricas reales
    real_over25 = sum(1 for r in matches if r["goals_for"] + r["goals_against"] > 2.5)
    real_o25_rate = real_over25 / n

    # Métricas predichas
    pred_over25 = 0
    errors = []
    direction_ok = 0
    processed = 0

    for r in matches:
        try:
            pred = predict_match(r["team_id"], r["opponent_id"], neutral=True)
            lh = pred["lambda_home"]
            la = pred["lambda_away"]
            if lh + la > 2.5:
                pred_over25 += 1
            errors.append(lh - r["goals_for"])
            errors.append(la - r["goals_against"])
            ph = pred["prob_home_win"] / 100
            pa = pred["prob_away_win"] / 100
            result = r["result"]
            if (ph > pa and result == "W") or (pa > ph and result == "L") or \
               (abs(ph - pa) < 0.05 and result == "D"):
                direction_ok += 1
            processed += 1
        except Exception:
            pass

    if processed == 0:
        print("  ❌ No se pudieron generar predicciones")
        conn.close()
        return

    pred_o25_rate = pred_over25 / processed
    bias = sum(errors) / len(errors) if errors else 0.0
    mae  = sum(abs(e) for e in errors) / len(errors) if errors else 0.0
    direction = direction_ok / processed * 100

    print(f"\n  Métricas ({processed} partidos evaluados):")
    print(f"    Over 2.5 real  : {real_o25_rate*100:.1f}%")
    print(f"    Over 2.5 pred  : {pred_o25_rate*100:.1f}%  (gap: {(pred_o25_rate - real_o25_rate)*100:+.1f}pp)")
    print(f"    λ bias          : {bias:+.3f}  (ideal: 0.000)")
    print(f"    MAE             : {mae:.3f}")
    print(f"    Direction acc   : {direction:.1f}%")

    # Leer BASE_GOALS actual del modelo
    model_text = MODEL.read_text()
    m = re.search(r"BASE_GOALS\s*=\s*([0-9.]+)", model_text)
    current_base = float(m.group(1)) if m else 1.22

    # Decidir ajuste
    over25_gap = pred_o25_rate - real_o25_rate   # positivo → predecimos demasiados goles
    bias_sign  = bias                             # positivo → lambdas demasiado altas

    need_adjust = abs(over25_gap) > 0.05 or abs(bias) > 0.15
    if not need_adjust:
        print(f"\n  ✅ BASE_GOALS={current_base} — no requiere ajuste (gap < 5pp, bias < 0.15)")
        conn.close()
        return

    # Calcular nueva BASE_GOALS (ajuste conservador)
    # Si predecimos demasiados goles (over25_gap > 0) → bajar BASE_GOALS
    adjustment = -over25_gap * 0.10   # escalar: 10pp gap → 0.01 cambio
    adjustment = max(-MAX_DELTA_PER_WEEK, min(MAX_DELTA_PER_WEEK, adjustment))
    # También considerar bias de lambda directamente
    bias_adj = -bias * 0.05
    bias_adj = max(-MAX_DELTA_PER_WEEK, min(MAX_DELTA_PER_WEEK, bias_adj))
    # Promediar ambas señales
    total_adj = (adjustment + bias_adj) / 2
    new_base = round(current_base + total_adj, 3)
    # Clamp absoluto: BASE_GOALS no puede salir de rango razonable
    new_base = max(1.05, min(1.50, new_base))

    print(f"\n  🔧 Ajuste recomendado:")
    print(f"    BASE_GOALS: {current_base} → {new_base}  ({total_adj:+.3f})")
    print(f"    Razón: Over2.5 gap={over25_gap*100:+.1f}pp, λ bias={bias:+.3f}")

    if dry_run:
        print("  [DRY RUN] No se aplicó el cambio")
        conn.close()
        return

    # Aplicar cambio en match_predictor.py
    new_text = re.sub(
        r"(BASE_GOALS\s*=\s*)[0-9.]+",
        f"\\g<1>{new_base}",
        model_text
    )
    # Actualizar comentario de calibración
    import datetime
    today = datetime.date.today().isoformat()
    new_text = re.sub(
        r"(BASE_GOALS\s*=\s*[0-9.]+\s*#.*?)(\n)",
        f"BASE_GOALS = {new_base}         # calibrado {today} "
        f"(Over2.5 real={real_o25_rate*100:.0f}% pred={pred_o25_rate*100:.0f}%)\n",
        new_text
    )
    MODEL.write_text(new_text)
    print(f"  ✅ match_predictor.py actualizado: BASE_GOALS={new_base}")

    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_calibration(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
