"""
timeline_patterns.py — Busca patrones entre los CLASIFICADOS usando el play-by-play
FIFA (fifa_match_events). Objetivo: señales que mejoren la precisión en knockouts.

Convierte cada métrica de proceso a percentil vs el campo de clasificados y auto-flagea
arquetipos: 'a deber' (mucho a puerta, pocos goles → regresa al alza), sobre-conversión
(regresa a la baja), vulnerable temprano, peligro tardío, muralla, asediado.
Reporta correlaciones métrica↔resultado para saber QUÉ predice.

Uso:  python scripts/timeline_patterns.py
"""
import json
import sqlite3
from pathlib import Path

from timeline_stats import team_timeline, BUCKET_LBL

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
STAND = BASE_DIR / "data" / "processed" / "wc2026_standings_after_j3.json"

NAME = {"Türkiye": "Turkey", "Cabo Verde": "Cape Verde", "Côte d'Ivoire": "Ivory Coast",
        "Congo DR": "DR Congo", "IR Iran": "Iran", "Korea Republic": "South Korea",
        "Curaçao": "Curacao", "United States": "USA", "Czech Republic": "Czechia"}


def _qualified():
    d = json.load(open(STAND, encoding="utf-8"))
    out = []
    for m in d["round_of_32"]:
        out += [NAME.get(m["home"], m["home"]), NAME.get(m["away"], m["away"])]
    return sorted(set(out))


def _pct(val, arr):
    arr = sorted(arr)
    return 100.0 * sum(1 for x in arr if x <= val) / len(arr)


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    conn = sqlite3.connect(str(DB))
    teams = _qualified()
    rows = {}
    for t in teams:
        tl = team_timeline(conn, t)
        if tl:
            # share temprano/tardío de remates concedidos
            ag = tl["shot_ag_b"]; tot_ag = sum(ag) or 1
            tl["early_concede_sh"] = (ag[0] + ag[1]) / tot_ag       # 1-30
            tl["late_concede_sh"] = (ag[5] + ag[6]) / tot_ag        # 76-90+
            af = tl["shot_for_b"]; tot_af = sum(af) or 1
            tl["late_attack_sh"] = (af[5] + af[6]) / tot_af
            tl["sot_per_goal"] = tl["sot_for"] / tl["goals_for"] if tl["goals_for"] else 99
            tl["shot_dominance"] = tl["shots_for"] - tl["shots_against"]
            rows[t] = tl
    conn.close()

    def col(k):
        return [r[k] for r in rows.values()]

    # ---- correlaciones métrica de proceso ↔ goles (qué predice el output) ----
    goals = [rows[t]["goals_for"] for t in rows]
    print("=" * 70)
    print("CORRELACIÓN proceso ↔ goles a favor (n=%d clasificados):" % len(rows))
    for k, lbl in [("sot_for", "remates a puerta/p"), ("shots_for", "remates/p"),
                   ("shot_acc", "precisión de tiro"), ("corners_for", "córners/p"),
                   ("shot_dominance", "dominio (remates for−against)")]:
        print(f"  r({lbl:32}, goles) = {_corr(col(k), goals):+.2f}")

    # ---- arquetipos por equipo ----
    print("\n" + "=" * 70)
    print("ARQUETIPOS (percentil vs los 32 clasificados):")
    # mediana de sot_per_goal del campo para 'a deber'
    spg = sorted(r["sot_per_goal"] for r in rows.values() if r["goals_for"] > 0)
    spg_med = spg[len(spg) // 2]
    for t in sorted(rows, key=lambda x: -rows[x]["sot_for"]):
        r = rows[t]
        flags = []
        # 'a deber': genera mucho a puerta y marca poco respecto a ese volumen
        if r["sot_for"] >= 3.5 and r["sot_per_goal"] > spg_med * 1.3:
            flags.append("A DEBER↑ (mucho a puerta, poco gol → regresa al alza)")
        # sobre-convierte: marca alto con poco a puerta
        if r["goals_for"] >= 1.5 and r["sot_per_goal"] < spg_med * 0.7:
            flags.append("SOBRE-CONVIERTE↓ (marca por encima de lo que genera)")
        if r["early_concede_sh"] >= 0.33 and r["shots_against"] >= 8:
            flags.append("VULNERABLE TEMPRANO (≥33% tiros concedidos en 1-30)")
        if r["late_concede_sh"] >= 0.33 and r["shots_against"] >= 8:
            flags.append("VULNERABLE TARDE (≥33% tiros concedidos en 76+)")
        if r["shots_against"] <= 8 and r["sot_against"] <= 3:
            flags.append("MURALLA (suprime tiros del rival)")
        if r["saves_made"] >= 3.5:
            flags.append("PORTERO MURO (≥3.5 paradas/p, asediado)")
        if r["shot_dominance"] >= 6:
            flags.append("DOMINA TERRITORIO (+6 remates netos)")
        if flags:
            print(f"\n  {t} — rem {r['shots_for']:.1f} (a puerta {r['sot_for']:.1f}) · "
                  f"recibe {r['shots_against']:.1f} · gol {r['goals_for']:.2f} · "
                  f"pico {r['peak_attack']}/colador {r['peak_concede']}")
            for f in flags:
                print(f"      • {f}")


if __name__ == "__main__":
    main()
