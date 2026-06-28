"""
knockout_tiebreaker.py — Desempate de FASE FINAL (prórroga/penales).

En la fase de eliminatorias, ~el 25-40% de los partidos no se resuelven en 90'.
El modelo de marcador (predict_match) da la prob de EMPATE en 90' pero NO dice
quién sobrevive el empate. Este módulo construye un "tiebreaker rating" por equipo
con tres componentes (pedido del dueño 28-jun) y convierte la prob de empate en
prob de AVANZAR:

  • RESISTENCIA (prórroga): plantilla más joven + cierre fuerte (gol en 76-90) +
    baja fatiga (fatigue_conceded). — El mejor soportado: timing real del Mundial.
  • PORTERO (penales): rating del GK en el Mundial + altura. — Proxy (no hay
    datos de penales atajados específicos).
  • PATEADORES: historial de penales del equipo (volumen). — El más débil: es
    volumen, NO % de conversión (falta el dato de penales fallados). Pesa menos.

⚠️ NO está backtesteado: no hay resultados de knockout del Mundial 2026 todavía.
Es un factor de cara a la fase final, validado por sentido futbolístico, no por
acierto medido. Pesos: resistencia 0.45, portero 0.35, pateadores 0.20 (los dos
primeros tienen datos más limpios).

Uso:
    python scripts/knockout_tiebreaker.py                 # tabla de los 32
    python scripts/knockout_tiebreaker.py "South Africa" "Canada" [draw_prob]
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

W_RESIST, W_GK, W_PEN = 0.45, 0.35, 0.20

R32 = ["South Africa", "Canada", "Brazil", "Japan", "Germany", "Paraguay",
       "Netherlands", "Morocco", "Ivory Coast", "Norway", "France", "Sweden",
       "Mexico", "Ecuador", "England", "DR Congo", "Belgium", "Senegal", "USA",
       "Bosnia and Herzegovina", "Spain", "Austria", "Portugal", "Croatia",
       "Switzerland", "Algeria", "Australia", "Egypt", "Argentina", "Cape Verde",
       "Colombia", "Ghana"]


def _raw(conn, pool=R32):
    out = {}
    for tm in pool:
        t = conn.execute("SELECT id FROM teams WHERE name=?", (tm,)).fetchone()
        if not t:
            continue
        tid = t[0]
        age = conn.execute("SELECT AVG(age) FROM players WHERE team_id=? AND age IS NOT NULL", (tid,)).fetchone()[0]
        gkr = conn.execute("SELECT AVG(rating) FROM match_player_stats WHERE team_id=? "
                           "AND position IN ('G','GK') AND match_date>='2026-06-01'", (tid,)).fetchone()[0]
        tg = conn.execute("SELECT scored_76_90, conceded_76_90, fatigue_conceded, penalties_scored "
                          "FROM team_goal_timing WHERE team_name=?", (tm,)).fetchone()
        if not tg or age is None or gkr is None:
            continue
        out[tm] = {"age": age, "gk": gkr, "late": tg[0] - tg[1],
                   "fat": tg[2], "pen": tg[3]}
    return out


def _pct(vals, v, rev=False):
    s = sorted(vals)
    r = sum(1 for x in s if x < v) / len(s)
    return 1 - r if rev else r


def ratings(conn, pool=R32):
    raw = _raw(conn, pool)
    ages = [d["age"] for d in raw.values()]
    gks = [d["gk"] for d in raw.values()]
    lates = [d["late"] for d in raw.values()]
    fats = [d["fat"] for d in raw.values()]
    pens = [d["pen"] for d in raw.values()]
    res = {}
    for tm, d in raw.items():
        resist = (_pct(ages, d["age"], rev=True) + _pct(lates, d["late"]) + _pct(fats, d["fat"], rev=True)) / 3
        gk = _pct(gks, d["gk"])
        pat = _pct(pens, d["pen"])
        res[tm] = {"resist": resist, "gk": gk, "pat": pat,
                   "tie": W_RESIST * resist + W_GK * gk + W_PEN * pat}
    return res


def advance_prob(conn, team_a, team_b, draw_prob, p_a_win):
    """Convierte prob de empate-en-90' en prob de AVANZAR usando el tiebreaker."""
    r = ratings(conn)
    ta, tb = r.get(team_a, {}).get("tie", 0.5), r.get(team_b, {}).get("tie", 0.5)
    share_a = ta / (ta + tb) if (ta + tb) > 0 else 0.5
    p_b_win = 1 - p_a_win - draw_prob
    adv_a = p_a_win + draw_prob * share_a
    adv_b = p_b_win + draw_prob * (1 - share_a)
    return adv_a, adv_b, share_a


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if len(sys.argv) >= 3:
        a, b = sys.argv[1], sys.argv[2]
        dp = float(sys.argv[3]) if len(sys.argv) > 3 else None
        r = ratings(conn)
        for tm in (a, b):
            d = r.get(tm)
            if not d:
                print(f"{tm}: sin datos"); continue
            print(f"{tm:22} RESIST {d['resist']*100:3.0f}%  PORTERO {d['gk']*100:3.0f}%  "
                  f"PATEAD {d['pat']*100:3.0f}%  → TIEBREAK {d['tie']*100:3.0f}%")
        if dp is not None:
            print(f"\nCon empate-en-90' = {dp*100:.0f}% (resto repartido por el modelo):")
            print("  (pasa p_a_win como 4º arg para la prob de avanzar exacta)")
    else:
        r = ratings(conn)
        print(f"{'EQUIPO':22} {'RESIST':>7} {'PORTERO':>8} {'PATEAD':>7} {'TIEBREAK':>9}")
        for tm, d in sorted(r.items(), key=lambda kv: -kv[1]["tie"]):
            print(f"{tm:22} {d['resist']*100:6.0f}% {d['gk']*100:7.0f}% "
                  f"{d['pat']*100:6.0f}% {d['tie']*100:8.0f}%")
    conn.close()
