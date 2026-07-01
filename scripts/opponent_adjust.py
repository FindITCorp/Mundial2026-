"""
opponent_adjust.py — Ajuste por FUERZA DEL RIVAL de las señales de proceso (idea autónoma).

Problema: el SOT-dif crudo no distingue a quién le hiciste esos remates. El +4.7 de
Colombia puede ser contra rivales flojos. Este módulo mide el proceso POR ENCIMA de lo
que la brecha de Elo predice → dominar a un rival fuerte vale más que a uno débil.

Método (calibrado de los propios datos, sin números mágicos):
  1. Se ajusta una pendiente: remates-a-puerta-dif por partido ~ pendiente × (Elo_propio −
     Elo_rival), a través del origen (0 de brecha → 0 esperado).
  2. Índice ajustado de un equipo = promedio de (SOT-dif real − pendiente×brecha_Elo) por
     partido = cuánto out-shoota MÁS de lo que su Elo predice (proceso real, no calendario).

Positivo = mejor de lo que su Elo dice (infravalorado). Negativo = peor.

Uso:
    python scripts/opponent_adjust.py --table
    python scripts/opponent_adjust.py "Mexico" "Ecuador"
    from opponent_adjust import adj_process
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
R32_STAGE = "289287"


def _per_match(conn, groups_only=False):
    """[(team_id, opp_id, sot_dif_de_ese_partido)] para todos los partidos WC."""
    ev = defaultdict(lambda: defaultdict(lambda: {"saves": 0, "goals": 0}))
    stage = {}
    for fmid, tc, dbt, stg in conn.execute(
            "SELECT fifa_match_id, type_code, db_team_id, stage_id FROM fifa_match_events "
            "WHERE db_team_id IS NOT NULL AND type_code IN (57,0,41)"):
        stage[fmid] = stg
        ev[fmid][dbt]["saves" if tc == 57 else "goals"] += 1
    out = []
    for m, teams in ev.items():
        if groups_only and stage.get(m) == R32_STAGE:
            continue
        if len(teams) != 2:
            continue
        a, b = list(teams.keys())
        for t, o in [(a, b), (b, a)]:
            sot = (teams[o]["saves"] + teams[t]["goals"]) - (teams[t]["saves"] + teams[o]["goals"])
            out.append((t, o, sot))
    return out


def _elo(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT team_id, elo FROM team_elo")}


def adj_process(conn, groups_only=False):
    """{team_id: {raw, adj, opp_elo, n}} — proceso ajustado por rival."""
    pm = _per_match(conn, groups_only)
    elo = _elo(conn)
    # 1) calibrar pendiente por mínimos cuadrados a través del origen
    num = den = 0.0
    for t, o, sot in pm:
        if t in elo and o in elo:
            gap = elo[t] - elo[o]
            num += gap * sot
            den += gap * gap
    slope = num / den if den else 0.0
    # 2) residuales por equipo
    agg = defaultdict(lambda: {"raw": 0.0, "adj": 0.0, "opp": 0.0, "n": 0})
    for t, o, sot in pm:
        if t not in elo or o not in elo:
            continue
        exp = slope * (elo[t] - elo[o])
        d = agg[t]
        d["raw"] += sot
        d["adj"] += sot - exp
        d["opp"] += elo[o]
        d["n"] += 1
    res = {}
    for t, d in agg.items():
        if d["n"]:
            res[t] = {"raw": d["raw"] / d["n"], "adj": d["adj"] / d["n"],
                      "opp_elo": d["opp"] / d["n"], "n": d["n"]}
    return {"slope": slope, "teams": res}


def _name(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT id, name FROM teams")}


def adj_sot_diff(conn, team, groups_only=False):
    """Índice ajustado por rival para un equipo (para el ensemble)."""
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
    if not tid:
        return None
    d = adj_process(conn, groups_only)["teams"].get(tid[0])
    return d["adj"] if d else None


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    r = adj_process(conn)
    name = _name(conn)
    print(f"Pendiente calibrada: {r['slope']*100:.2f} remates-a-puerta-dif por cada 100 Elo\n")
    if "--table" in sys.argv:
        rows = [(name.get(t, t), d["raw"], d["adj"], d["opp_elo"], d["n"])
                for t, d in r["teams"].items() if d["n"] >= 3]
        print(f"{'EQUIPO':16}{'SOTdif':>8}{'AJUST':>8}{'EloRival':>10}  (Δ = calidad de rival)")
        print("-- MEJORES por proceso AJUSTADO (out-shootan más de lo que su Elo dice) --")
        for x in sorted(rows, key=lambda z: -z[2])[:8]:
            print(f"{x[0]:16}{x[1]:+8.1f}{x[2]:+8.1f}{x[3]:10.0f}")
        print("-- El ajuste CAMBIA el ranking (crudo vs ajustado): mayores caídas --")
        for x in sorted(rows, key=lambda z: (z[2] - z[1]))[:5]:
            print(f"{x[0]:16}{x[1]:+8.1f}{x[2]:+8.1f}{x[3]:10.0f}  (bajó {x[1]-x[2]:+.1f}: rival flojo)")
    else:
        args = [x for x in sys.argv[1:] if not x.startswith("--")]
        if len(args) >= 2:
            for tm in args[:2]:
                tid = conn.execute("SELECT id FROM teams WHERE name=?", (tm,)).fetchone()
                d = r["teams"].get(tid[0]) if tid else None
                if d:
                    print(f"{tm:14} SOTdif crudo {d['raw']:+.1f} → AJUSTADO {d['adj']:+.1f}  "
                          f"(Elo rival medio {d['opp_elo']:.0f})")
            print("→ la señal ajustada por rival favorece al de mayor AJUSTADO")
        else:
            print(__doc__)
    conn.close()
