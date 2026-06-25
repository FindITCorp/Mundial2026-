"""
predict_adjusted.py — Predicción del modelo AJUSTADA por patrones de análisis.

Toma la λ base del modelo y la corrige con lo que un analista pesa y el modelo
no captura del todo:
  1. REGRESIÓN DE DEFINICIÓN: un equipo que crea mucho y no marca (conv<0.7) está
     "a deber" → sube su λ; uno que sobre-convierte (conv>1.5) regresa → baja su λ.
     (Lección 25-jun: descartar a Ecuador por su sequía fue el error; ganó 2-1.)
  2. CHOQUE DE VENTANAS: si la franja de máximo ataque del equipo coincide con la
     franja floja del rival → boost; si el rival aguanta esa franja → recorte.
  3. PORTERO EN RACHA del rival (save% alto) → recorte adicional.
Ajustes acotados (±18% por factor) para no sobreajustar. Re-deriva 1X2 y marcador
por Poisson sobre la λ ajustada.

Uso: python scripts/predict_adjusted.py "Japan" "Sweden"
"""
import math
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from models.match_predictor import predict_match
from analyze_match import team_profile, _tid, _share

DB = HERE.parent / "data" / "mundial2026.db"


def _regression_factor(prof):
    """Equipo a deber (sub-convierte) → >1; con suerte (sobre-convierte) → <1."""
    conv = prof.get("conversion")
    xg = prof.get("xg")
    if conv is None or not xg or xg < 0.8:
        return 1.0, ""
    if conv < 0.7:
        return 1.15, f"a deber (conv {conv}, xG {xg:.1f}) → +15%"
    if conv > 1.6:
        return 0.85, f"sobre-convierte (conv {conv}) → regresa −15%"
    if conv > 1.3:
        return 0.93, f"convierte alto (conv {conv}) → −7%"
    return 1.0, ""


def _clash_factor(att, deff):
    a = _share(att.get("hist_scored"))
    d = _share(deff.get("hist_conceded"))
    axg = att.get("xg")
    if not a or not d or (axg is not None and axg < 0.7):
        return 1.0, ""
    apeak = a.index(max(a))
    avg_d = sum(d) / 6
    if d[apeak] >= avg_d * 1.15:
        return 1.08, f"ataca en franja floja del rival → +8%"
    if d[apeak] <= avg_d * 0.85:
        return 0.95, f"rival aguanta su franja → −5%"
    return 1.0, ""


def _gk_factor(deff):
    sp = deff.get("save_pct")
    if sp and sp >= 72:
        return 0.92, f"portero rival en racha ({sp}%) → −8%"
    return 1.0, ""


def _poisson_1x2(lh, la, maxg=8):
    def p(l, k): return (l**k * math.exp(-l)) / math.factorial(k)
    ph = pd = pa = 0.0
    best = (0, 0); bestp = 0
    for i in range(maxg):
        for j in range(maxg):
            pr = p(lh, i) * p(la, j)
            if i > j: ph += pr
            elif i == j: pd += pr
            else: pa += pr
            if pr > bestp: bestp, best = pr, (i, j)
    t = ph + pd + pa
    return round(100*ph/t), round(100*pd/t), round(100*pa/t), f"{best[0]}-{best[1]}"


def adjusted(team_a, team_b, db_path=DB):
    conn = sqlite3.connect(str(db_path)); conn.row_factory = sqlite3.Row
    aid, an = _tid(conn, team_a); bid, bn = _tid(conn, team_b)
    pa = team_profile(conn, aid); pb = team_profile(conn, bid)
    conn.close()

    base = predict_match(aid, bid, neutral=True, db_path=db_path)
    lh, la = base["lambda_home"], base["lambda_away"]

    # factores sobre cada λ (atacante propio)
    notes = []
    rfh, n1 = _regression_factor(pa); rfa, n2 = _regression_factor(pb)
    cfh, n3 = _clash_factor(pa, pb); cfa, n4 = _clash_factor(pb, pa)
    gfa, n5 = _gk_factor(pb)  # GK de B reduce λ de A
    gfh, n6 = _gk_factor(pa)  # GK de A reduce λ de B
    for nm, ns in [(an, [n1, n3]), (bn, [n2, n4])]:
        for s in ns:
            if s: notes.append(f"{nm}: {s}")
    if n5: notes.append(f"{an} λ: {n5}")
    if n6: notes.append(f"{bn} λ: {n6}")

    lh_adj = lh * rfh * cfh * gfa
    la_adj = la * rfa * cfa * gfh

    bh, bd, ba, bscore = base["prob_home_win"], base["prob_draw"], base["prob_away_win"], base["predicted_score"]
    ah, ad, aa, ascore = _poisson_1x2(lh_adj, la_adj)
    return {"an": an, "bn": bn,
            "base": (bscore, bh, bd, ba, round(lh, 2), round(la, 2)),
            "adj": (ascore, ah, ad, aa, round(lh_adj, 2), round(la_adj, 2)),
            "notes": notes}


def show(team_a, team_b):
    r = adjusted(team_a, team_b)
    print(f"\n=== {r['an']} vs {r['bn']} ===")
    s = r["base"]; print(f"  MODELO:    {s[0]}  | {s[1]}/{s[2]}/{s[3]}  (λ {s[4]}-{s[5]})")
    s = r["adj"];  print(f"  AJUSTADO:  {s[0]}  | {s[1]}/{s[2]}/{s[3]}  (λ {s[4]}-{s[5]})")
    if r["notes"]:
        print("  Ajustes aplicados:")
        for n in r["notes"]: print("   • " + n)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        show(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)
