"""
predict_ensemble.py — Motor de CONSENSO + CONFIANZA con tope de tanda (idea autónoma 30-jun).

Diagnóstico que lo motiva: nuestros 2 fallos de octavos (Alemania-Paraguay, Holanda-
Marruecos) fueron los 2 PENALES. En los 4 resueltos en el campo, el consenso de señales
fue 4/4. El error no era el análisis — era CONFUNDIR "gana en 90'" con "avanza" y sellar
confianza alta en partidos que iban rumbo a una moneda al aire (sellé Alemania 71% cuando
era ~55%).

Separa DOS ejes que antes mezclaba a ojo:
  1. QUIÉN gana en 90'  → consenso de señales independientes (modelo 1X2, SOT-dif de
     proceso, calidad de XI, desempate). Las señales clavan esto.
  2. ¿Se decide en 90' o en la LOTERÍA?  → prob de empate del modelo. Si es alta, el que
     avanza es casi moneda al aire por bueno que sea el favorito.

TOPE DE TANDA: si hay empate, la cuota de avance se acota a [0.42, 0.58] (una tanda NUNCA
es más predecible que ~coin-flip, aunque el desempate incline algo). Así la prob de AVANCE
se jala hacia 50% en partidos apretados — que es lo honesto.

CONFIANZA: ALTA sólo si hay favorito claro en 90' (poca prob de empate) Y las señales
concuerdan. Si el partido pinta a tanda o las señales discrepan → BAJA (no sellar puntual
con exceso de confianza; es donde perdimos).

Uso:
    python scripts/predict_ensemble.py "Mexico" "Ecuador"
    python scripts/predict_ensemble.py --backtest        # retro sobre los 6 octavos
"""
import sqlite3
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"

from models.match_predictor import predict_match
from regression_check import sot_diff
from xi_quality import xi_rating
from knockout_tiebreaker import ratings as ko_ratings


def _tid(conn, name):
    r = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    return r[0] if r else None


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def ensemble(conn, a, b, groups_only=False):
    aid, bid = _tid(conn, a), _tid(conn, b)
    if not aid or not bid:
        return None
    m = predict_match(aid, bid, neutral=True, db_path=str(DB))
    ph, pd, pa = m["prob_home_win"], m["prob_draw"], m["prob_away_win"]
    if ph + pd + pa > 2:                 # el modelo devuelve 0-100 → normalizar a 0-1
        ph, pd, pa = ph / 100, pd / 100, pa / 100

    # --- eje 1: consenso de quién es mejor (favorito en 90') ---
    votes = []
    votes.append(a if ph > pa else b)                              # modelo
    da, db_ = sot_diff(conn, a, groups_only), sot_diff(conn, b, groups_only)
    if da is not None and db_ is not None and da != db_:
        votes.append(a if da > db_ else b)                         # SOT-dif proceso
    xa, xb = xi_rating(conn, a), xi_rating(conn, b)
    if xa and xb and abs(xa["avg"] - xb["avg"]) > 0.05:
        votes.append(a if xa["avg"] > xb["avg"] else b)            # calidad XI
    kr = ko_ratings(conn)
    if a in kr and b in kr:
        votes.append(a if kr[a]["tie"] > kr[b]["tie"] else b)      # desempate
    cons, cnt = Counter(votes).most_common(1)[0]
    agreement = cnt / len(votes)

    # --- eje 2: reparto de la tanda, ACOTADO (nunca más confiable que coin-flip) ---
    if a in kr and b in kr:
        ta, tb = kr[a]["tie"], kr[b]["tie"]
        share_a = ta / (ta + tb) if (ta + tb) else 0.5
    else:
        share_a = 0.5
    share_a = _clamp(share_a, 0.42, 0.58)                          # TOPE DE TANDA

    # piso de tanda en knockout: van a prórroga/penales ~25% histórico, y el modelo
    # SUBESTIMA empates (Alemania-Paraguay dio 14% y fue tanda) → no fiarse de <20%.
    shoot = max(pd, 0.20)
    adv_a = ph + shoot * share_a - (shoot - pd) * 0.5
    adv_b = pa + shoot * (1 - share_a) - (shoot - pd) * 0.5
    adv_cons = adv_a if cons == a else adv_b

    # --- confianza: favorito claro en 90' (poca prob de tanda) Y señales de acuerdo ---
    decisive = 1 - shoot
    if decisive >= 0.62 and agreement == 1.0:
        conf = "ALTA"
    elif decisive < 0.50 or agreement < 0.6:
        conf = "BAJA"
    else:
        conf = "MEDIA"
    return {"a": a, "b": b, "ph": ph, "pd": pd, "pa": pa,
            "cons": cons, "agreement": agreement, "nvotes": len(votes),
            "adv_cons": adv_cons, "adv_a": adv_a, "adv_b": adv_b,
            "shootout_risk": shoot, "conf": conf}


def _print(r):
    print(f"  Modelo 90': {r['a']} {r['ph']*100:.0f}% / empate {r['pd']*100:.0f}% / {r['b']} {r['pa']*100:.0f}%")
    print(f"  Consenso favorito 90': {r['cons']}  (acuerdo {r['agreement']*100:.0f}% de {r['nvotes']} señales)")
    print(f"  Riesgo de TANDA (prob empate): {r['shootout_risk']*100:.0f}%  → avance acotado")
    print(f"  AVANCE: {r['a']} {r['adv_a']*100:.0f}%  |  {r['b']} {r['adv_b']*100:.0f}%")
    print(f"  ★ CONFIANZA: {r['conf']}  → favorito a avanzar: {r['cons']} {r['adv_cons']*100:.0f}%")
    if r["conf"] == "BAJA":
        print("  ⚠ BAJA confianza: NO sellar puntual con exceso; es donde perdimos (tandas/discrepancia).")


def backtest(conn):
    R32 = [("South Africa", "Canada", "Canada", "juego"),
           ("Brazil", "Japan", "Brazil", "juego"),
           ("Germany", "Paraguay", "Paraguay", "PENALES"),
           ("Netherlands", "Morocco", "Morocco", "PENALES"),
           ("Ivory Coast", "Norway", "Norway", "juego"),
           ("France", "Sweden", "France", "juego")]
    print(f"{'OCTAVO':24}{'consenso':>11}{'conf':>6}{'P(tanda)':>10}  avanzó     ok")
    hi_ok = hi_n = lo_n = 0
    for h, a, adv, how in R32:
        r = ensemble(conn, h, a, groups_only=True)
        ok = r["cons"] == adv
        if r["conf"] == "ALTA":
            hi_n += 1; hi_ok += ok
        else:
            lo_n += 1
        print(f"{h[:10]+' v '+a[:9]:24}{r['cons'][:10]:>11}{r['conf']:>6}{r['pd']*100:>9.0f}%  {adv[:9]:9}({how[:3]}) {'OK' if ok else 'MISS'}")
    print(f"\nConfianza ALTA: {hi_ok}/{hi_n} acierto. Los MISS deberían caer en BAJA/tanda.")


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if "--backtest" in sys.argv:
        backtest(conn)
    else:
        args = [x for x in sys.argv[1:] if not x.startswith("--")]
        if len(args) < 2:
            print(__doc__)
        else:
            r = ensemble(conn, args[0], args[1])
            if r:
                print(f"=== {args[0]} vs {args[1]} ===")
                _print(r)
    conn.close()
