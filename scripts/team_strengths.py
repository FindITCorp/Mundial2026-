#!/usr/bin/env python3
"""
team_strengths.py — Fortalezas y debilidades por selección desde su juego real.

Pedido del usuario (11-jun-2026): "detectar fortalezas y debilidades según su
juego para predecir con más certeza — defensa débil vs ataque fuerte = goleada".

Método:
1. Por equipo, agrega match_team_stats (vía wc_matches) ponderando por Elo del
   rival (mismo SOS del resto del modelo: (opp_elo/1550)^1.5 escala los valores
   ofensivos; los defensivos se ponderan inverso — encajar vs Brasil no es lo
   mismo que vs Nicaragua).
2. Ejes: ataque (xG+área+ocasiones), definición (goles−xG), aéreo, balón parado,
   pressing (recuperación), seguridad (precisión de pase), defensa (xG y tiros
   en contra), portería (% de paradas).
3. Normaliza en z-scores contra el resto de selecciones con datos y guarda en
   team_strengths. z ≥ +0.6 = fortaleza, z ≤ −0.6 = debilidad.

match_predictor consume la tabla en _strengths_matchup(): el λ del atacante
sube cuando su fortaleza golpea una debilidad del rival (ataque vs defensa,
aéreo vs aéreo, pressing vs seguridad) — capado a ±10% y solo con n≥3 de
ambos lados, para no duplicar lo que Elo/xG ya capturan.

Uso:
    python3 scripts/team_strengths.py            # recalcula y guarda
    python3 scripts/team_strengths.py --report   # además imprime el informe
"""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

SOS_PIVOT = 1550.0
SOS_EXP = 1.5
MIN_MATCHES = 2

AXES = ("ataque", "definicion", "aereo", "balon_parado",
        "pressing", "seguridad", "defensa", "porteria")


def _collect(conn) -> dict[int, dict]:
    elo = {r[0]: r[1] for r in conn.execute("SELECT team_id, elo FROM team_elo")}
    rows = conn.execute("""
        SELECT m.team_id, m.match_id, wm.home_team_id, wm.away_team_id,
               wm.score_home, wm.score_away,
               m.xg, m.shots_inside_box, m.clear_chances, m.aerial_won,
               m.aerial_total, m.corners, m.tackles_won, m.interceptions,
               m.recoveries, m.passes_pct, m.saves,
               o.xg AS xg_against, o.shots_inside_box AS sib_against
        FROM match_team_stats m
        JOIN wc_matches wm ON wm.id = m.match_id
        LEFT JOIN match_team_stats o ON o.match_id = m.match_id
            AND o.team_id != m.team_id
    """).fetchall()

    acc: dict[int, dict] = {}
    for r in rows:
        (tid, mid, h_id, a_id, sh, sa, xg, sib, cc, aw, at_, crn,
         tklw, itc, rec, ppct, sv, xga, siba) = r
        opp_id = a_id if tid == h_id else h_id
        gf = (sh if tid == h_id else sa)
        ga = (sa if tid == h_id else sh)
        w = ((elo.get(opp_id) or 1430.0) / SOS_PIVOT) ** SOS_EXP
        d = acc.setdefault(tid, {"n": 0, "w": 0.0, "wi": 0.0,
                                 **{k: 0.0 for k in
                                    ("xg", "sib", "cc", "fin", "aw", "at",
                                     "crn", "press", "ppct", "xga", "siba",
                                     "sv", "ga")}})
        d["n"] += 1
        d["w"] += w
        d["wi"] += 1.0 / w           # peso inverso para ejes defensivos
        if xg is not None:
            d["xg"] += xg * w
            if gf is not None:
                d["fin"] += (gf - xg)          # definición: goles − xG (sin peso)
        d["sib"] += (sib or 0) * w
        d["cc"] += (cc or 0) * w
        if at_:
            d["aw"] += (aw or 0)
            d["at"] += at_
        d["crn"] += (crn or 0)
        d["press"] += ((tklw or 0) + (itc or 0) + (rec or 0))
        if ppct is not None:
            d["ppct"] += ppct
        if xga is not None:
            d["xga"] += xga / w               # encajar vs débil pesa MÁS
        d["siba"] += (siba or 0) / w
        if sv is not None and ga is not None:
            d["sv"] += sv
            d["ga"] += ga
    return acc


def _axes(d: dict) -> dict[str, float] | None:
    n, w, wi = d["n"], d["w"], d["wi"]
    if n < MIN_MATCHES or w <= 0:
        return None
    return {
        "ataque":       d["xg"] / w + 0.05 * d["sib"] / w + 0.15 * d["cc"] / w,
        "definicion":   d["fin"] / n,
        "aereo":        (d["aw"] / d["at"]) if d["at"] else 0.5,
        "balon_parado": d["crn"] / n,
        "pressing":     d["press"] / n,
        "seguridad":    d["ppct"] / n,
        "defensa":      -(d["xga"] / wi + 0.05 * d["siba"] / wi),
        "porteria":     (d["sv"] / (d["sv"] + d["ga"])) if (d["sv"] + d["ga"]) else 0.5,
    }


def build(conn, report: bool = False) -> int:
    acc = _collect(conn)
    profiles = {tid: (_axes(d), d["n"]) for tid, d in acc.items()}
    profiles = {t: (p, n) for t, (p, n) in profiles.items() if p}

    # z-scores por eje
    stats = {}
    for ax in AXES:
        vals = [p[ax] for p, _ in profiles.values()]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        stats[ax] = (mu, sd)

    conn.execute("""CREATE TABLE IF NOT EXISTS team_strengths (
        team_id INTEGER, axis TEXT, z REAL, raw REAL, n INTEGER,
        updated_at TEXT, PRIMARY KEY (team_id, axis))""")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    conn.execute("DELETE FROM team_strengths")
    for tid, (p, n) in profiles.items():
        for ax in AXES:
            mu, sd = stats[ax]
            z = (p[ax] - mu) / sd
            conn.execute("INSERT INTO team_strengths VALUES (?,?,?,?,?,?)",
                         (tid, ax, round(z, 3), round(p[ax], 3), n, now))
    conn.commit()

    if report:
        wc_teams = {r[0] for r in conn.execute(
            """SELECT DISTINCT home_team_id FROM wc_matches WHERE stage='group'
               UNION SELECT DISTINCT away_team_id FROM wc_matches WHERE stage='group'""")}
        print(f"\n{'='*64}\n  FORTALEZAS / DEBILIDADES (z±0.6, {len(profiles)} equipos)\n{'='*64}")
        for tid, (p, n) in sorted(profiles.items(),
                                  key=lambda x: -(x[1][0]["ataque"])):
            if tid not in wc_teams:
                continue
            name = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()[0]
            f = [ax for ax in AXES if (p[ax] - stats[ax][0]) / stats[ax][1] >= 0.6]
            d_ = [ax for ax in AXES if (p[ax] - stats[ax][0]) / stats[ax][1] <= -0.6]
            print(f"  {name:24s} (n={n})  ✚ {', '.join(f) or '—':38s} ▼ {', '.join(d_) or '—'}")
    return len(profiles)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    conn = sqlite3.connect(str(DB))
    n = build(conn, report=args.report)
    print(f"\n[team_strengths] {n} equipos perfilados")
    conn.close()


if __name__ == "__main__":
    main()
