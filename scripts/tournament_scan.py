"""
tournament_scan.py — Análisis INTEGRAL y AUTO-ACTUALIZABLE del Mundial.

Pedido del dueño (26-jun): el análisis debe (1) priorizar datos del Mundial,
(2) usar TODA la riqueza (no solo goles: intentos por zona, rupturas de líneas,
presiones, recuperación, set-pieces, portería...), (3) ser EVOLUTIVO (tendencia
jornada a jornada) y (4) AUTO-DETECTAR patrones que no vemos. Se re-corre tras
cada jornada y siempre refleja el estado actual.

Fuente primaria: fifa_fdh_stats (142 métricas/equipo) + match_team_stats (xG) +
wc_matches (goles, resultado). Amistosos solo como contexto de forma.

Cada métrica se convierte en PERCENTIL vs el campo (los 48), así un valor se lee
como "élite / pobre" sin saber escalas. Auto-flags: outliers (top/bottom ~15%),
DIVERGENCIAS (crea pero no remata, presiona pero no recupera, sobre/sub-convierte)
y TENDENCIA (sube/baja entre jornadas).

Uso:
    python scripts/tournament_scan.py                 # escanea y lista patrones de todos
    python scripts/tournament_scan.py "Morocco"       # perfil integral + patrones de un equipo
    python scripts/tournament_scan.py --qualified     # solo equipos clasificados/vivos
"""
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "mundial2026.db"

# Métricas FDH a minar (nombre FDH -> etiqueta corta). Se promedian por partido.
FDH = {
    "AttemptAtGoal": "remates",
    "AttemptAtGoalOnTarget": "remates_puerta",
    "AttemptAtGoalInsideThePenaltyArea": "remates_area",
    "AttemptAtGoalFromPass": "remates_jugada",
    "AttemptAtGoalAgainst": "remates_conced",
    "AttemptAtGoalAgainstOnTarget": "rem_conced_puerta",
    "LinebreaksAttemptedAttackingLineCompleted": "rupturas_ultima_linea",
    "DefensivePressuresApplied": "presiones",
    "BallRecoveryTime": "t_recuperacion",
    "Possession": "posesion",
    "PassesCompleted": "pases_ok",
    "Crosses": "centros",
    "GoalkeeperSavePercentage": "gk_save_pct",
    "HeadedAttemptAtGoal": "remates_cabeza",
}
# set-piece threat (suma de intentos a balón parado)
SETPIECE = ["AttemptAtGoalFromCorner", "AttemptAtGoalFromCross",
            "AttemptAtGoalFromFreeKicks"]


def _team_match_metrics(conn):
    """Devuelve {team_id: {metric: [valores por partido]}} desde fifa_fdh_stats,
    + goles/xG por partido desde match_team_stats/wc_matches. Solo WC grupo."""
    data = {}
    # mapa match_id -> (home_id, away_id, sh, sa)
    wcm = {r[0]: r[1:] for r in conn.execute(
        "SELECT id,home_team_id,away_team_id,score_home,score_away FROM wc_matches "
        "WHERE stage='group' AND played=1")}
    # FDH
    for mid, tid, stat, val in conn.execute(
            "SELECT match_id, team_id, stat, value FROM fifa_fdh_stats WHERE value IS NOT NULL"):
        if mid not in wcm:
            continue
        d = data.setdefault(tid, {})
        if stat in FDH:
            d.setdefault(FDH[stat], []).append(val)
        if stat in SETPIECE:
            d.setdefault("_sp", []).append((mid, val))
    # set-piece: sumar por partido
    for tid, d in data.items():
        if "_sp" in d:
            bym = {}
            for mid, v in d.pop("_sp"):
                bym[mid] = bym.get(mid, 0) + v
            d["remates_balon_parado"] = list(bym.values())
    # goles a favor/contra + xG por partido
    for mid, (h, a, sh, sa) in wcm.items():
        for tid, gf, ga in ((h, sh, sa), (a, sa, sh)):
            d = data.setdefault(tid, {})
            d.setdefault("goles", []).append(gf)
            d.setdefault("goles_contra", []).append(ga)
        for tid in (h, a):
            xg = conn.execute("SELECT xg FROM match_team_stats WHERE match_id=? AND team_id=?",
                              (mid, tid)).fetchone()
            if xg and xg[0] is not None:
                data.setdefault(tid, {}).setdefault("xg", []).append(xg[0])
    return data


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _percentile(value, allvals):
    allvals = sorted(v for v in allvals if v is not None)
    if not allvals or value is None:
        return None
    below = sum(1 for v in allvals if v < value)
    return round(100 * below / len(allvals))


def scan(focus=None, qualified_only=False):
    conn = sqlite3.connect(str(DB))
    raw = _team_match_metrics(conn)
    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM teams")}

    # promedios por equipo
    metrics = list(next(iter(raw.values())).keys()) if raw else []
    allmetrics = set()
    for d in raw.values():
        allmetrics.update(d.keys())
    prof = {}
    for tid, d in raw.items():
        prof[tid] = {m: _avg(d.get(m, [])) for m in allmetrics}
        # derivadas
        g = prof[tid].get("goles"); xg = prof[tid].get("xg")
        prof[tid]["conversion"] = round(g / xg, 2) if (g is not None and xg) else None
        ra = prof[tid].get("remates"); rb = prof[tid].get("remates_area")
        prof[tid]["pct_remates_area"] = round(100 * rb / ra) if (ra and rb) else None
        sp = prof[tid].get("remates_balon_parado")
        prof[tid]["pct_balon_parado"] = round(100 * sp / ra) if (ra and sp) else None

    # campo de valores por métrica (para percentiles)
    field = {m: [prof[t].get(m) for t in prof] for m in list(allmetrics) + ["conversion", "pct_remates_area", "pct_balon_parado"]}

    n_matches = {t: len(raw[t].get("goles", [])) for t in raw}

    if focus:
        tid = next((i for i, nm in names.items() if nm.lower() == focus.lower()
                    or focus.lower() in nm.lower()), None)
        if not tid or tid not in prof:
            print(f"No encontré datos de: {focus}")
            return
        _print_team(names[tid], prof[tid], field, n_matches.get(tid, 0), raw[tid])
    else:
        _print_field(prof, field, names, n_matches, qualified_only, conn)
    conn.close()


# etiquetas: percentil alto = bueno (True) o malo (False, ej. goles_contra)
LOWER_BETTER = {"goles_contra", "remates_conced", "rem_conced_puerta", "t_recuperacion"}

def _band(pct):
    if pct is None: return "—"
    if pct >= 85: return "ÉLITE"
    if pct >= 65: return "alto"
    if pct >= 35: return "medio"
    if pct >= 15: return "bajo"
    return "POBRE"


def _print_team(name, p, field, nm, raw):
    print("=" * 74)
    print(f"PERFIL INTEGRAL — {name}  ({nm} partidos del Mundial)")
    print("=" * 74)
    order = ["goles", "xg", "conversion", "remates", "remates_puerta", "remates_area",
             "pct_remates_area", "remates_jugada", "remates_balon_parado", "pct_balon_parado",
             "remates_cabeza", "rupturas_ultima_linea", "presiones", "t_recuperacion",
             "posesion", "pases_ok", "centros", "goles_contra", "remates_conced",
             "rem_conced_puerta", "gk_save_pct"]
    for m in order:
        v = p.get(m)
        if v is None: continue
        pct = _percentile(v, field.get(m, []))
        disp = pct if pct is None else (100 - pct if m in LOWER_BETTER else pct)
        print(f"  {m:24} {v:7.2f}   pct vs campo: {disp if disp is not None else '—':>3}  [{_band(disp)}]")
    # EVOLUTIVO: trayectoria jornada a jornada (xG propio, xG/goles concedidos)
    traj = _trajectory(name)
    if traj:
        print("\n  EVOLUTIVO (J1→J2→J3):")
        for line in traj:
            print("   " + line)
    print("\n  PATRONES AUTO-DETECTADOS:")
    for flag in _flags(p, field):
        print("   • " + flag)


def _trajectory(name):
    """xG/goles a favor y en contra POR JORNADA (orden cronológico) + flecha de tendencia."""
    conn = sqlite3.connect(str(DB))
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    if not tid:
        return []
    tid = tid[0]
    rows = conn.execute(
        "SELECT id,date,home_team_id,away_team_id,score_home,score_away FROM wc_matches "
        "WHERE stage='group' AND played=1 AND (home_team_id=? OR away_team_id=?) ORDER BY date",
        (tid, tid)).fetchall()
    gf, ga, xgf, xga = [], [], [], []
    for mid, dt, h, a, sh, sa in rows:
        isH = h == tid
        gf.append(sh if isH else sa); ga.append(sa if isH else sh)
        oid = a if isH else h
        my = conn.execute("SELECT xg FROM match_team_stats WHERE match_id=? AND team_id=?", (mid, tid)).fetchone()
        op = conn.execute("SELECT xg FROM match_team_stats WHERE match_id=? AND team_id=?", (mid, oid)).fetchone()
        xgf.append(my[0] if my else None); xga.append(op[0] if op else None)
    conn.close()

    def arrow(seq):
        s = [x for x in seq if x is not None]
        if len(s) < 2: return ""
        d = s[-1] - s[0]
        return " ↑ subiendo" if d > 0.4 else (" ↓ bajando" if d < -0.4 else " → estable")
    def def_arrow(seq):
        s = [x for x in seq if x is not None]
        if len(s) < 2: return ""
        d = s[-1] - s[0]  # más xG concedido = peor
        return " ↓ defensa empeora" if d > 0.4 else (" ↑ defensa mejora" if d < -0.4 else " → estable")
    out = []
    if any(x is not None for x in xgf):
        out.append(f"xG creado:   {' → '.join(f'{x:.1f}' if x is not None else '?' for x in xgf)}{arrow(xgf)}")
    if any(x is not None for x in xga):
        out.append(f"xG concedido:{' → '.join(f'{x:.1f}' if x is not None else '?' for x in xga)}{def_arrow(xga)}")
    out.append(f"goles:       {' → '.join(map(str, gf))}  |  encajados: {' → '.join(map(str, ga))}")
    return out


def _flags(p, field):
    out = []
    pc = lambda m: _percentile(p.get(m), field.get(m, []))
    inv = lambda m: (100 - pc(m)) if pc(m) is not None else None
    # finishing / regresión
    conv = p.get("conversion")
    if conv is not None:
        if conv >= 1.3 and (pc("xg") or 50) < 60:
            out.append(f"SOBRE-CONVIERTE ({conv}× xG) con creación normal → regresa a la baja (no fiar repetición)")
        elif conv <= 0.7 and (pc("xg") or 0) >= 55:
            out.append(f"SUB-CONVIERTE ({conv}× xG) pese a crear → goles 'a deber', peligroso (regresa al alza)")
    # crea buildup pero no remata (ruptura alta, remates bajos)
    if (pc("rupturas_ultima_linea") or 0) >= 70 and (pc("remates_area") or 100) <= 40:
        out.append("ROMPE LÍNEAS pero no remata en área → llega y se atasca en el último pase")
    # dependencia de balón parado
    if (p.get("pct_balon_parado") or 0) >= 35:
        out.append(f"DEPENDE DEL BALÓN PARADO ({p.get('pct_balon_parado')}% de sus remates) → si no hay faltas/córners, se apaga")
    # amenaza aérea / por centros — vía clave para batir defensas élite (set pieces/área)
    if (pc("remates_cabeza") or 0) >= 80 and (pc("centros") or 0) >= 75:
        out.append("AMENAZA AÉREA Y POR CENTROS (cabezazos y centros élite) → puede batir defensas sólidas a balón parado/área, donde el dominio de proceso del rival importa menos")
    # presiona pero no recupera rápido
    if (pc("presiones") or 0) >= 70 and (inv("t_recuperacion") or 100) <= 35:
        out.append("PRESIONA MUCHO pero tarda en recuperar → presión poco efectiva, vulnerable a la salida")
    # defensa: concede pocos remates a puerta = sólida más allá de goles
    if (inv("rem_conced_puerta") or 0) >= 80:
        out.append("DEFENSA ÉLITE por proceso (concede muy pocos remates a puerta), no solo por marcador")
    elif (inv("rem_conced_puerta") or 100) <= 20:
        out.append("DEFENSA FRÁGIL por proceso (concede muchos remates a puerta) → marcador puede estar maquillando")
    # ataque élite por proceso
    if (pc("remates_area") or 0) >= 85 and (pc("xg") or 0) >= 80:
        out.append("ATAQUE ÉLITE por proceso (volumen y calidad de remate en área)")
    # posesión estéril
    if (pc("posesion") or 0) >= 75 and (pc("remates_area") or 100) <= 40:
        out.append("POSESIÓN ESTÉRIL (mucho balón, poco remate en área) → dominio sin daño")
    if not out:
        out.append("Sin patrones extremos: perfil equilibrado/promedio en las dimensiones medidas.")
    return out


def _print_field(prof, field, names, nm, qualified_only, conn):
    qualified = set()
    if qualified_only:
        import json
        sp = BASE / "data" / "processed" / "wc2026_results_j3.json"
        if sp.exists():
            d = json.loads(sp.read_text(encoding="utf-8"))
            for g in d.get("group_standings_after_j3", {}).values():
                for t in g["teams"][:2]:
                    r = conn.execute("SELECT id FROM teams WHERE name=?", (t["team"],)).fetchone()
                    if r: qualified.add(r[0])
    print("=" * 74)
    print(f"SCAN DEL TORNEO — patrones auto-detectados ({'clasificados' if qualified_only else 'todos'})")
    print("=" * 74)
    for tid in sorted(prof, key=lambda t: -(prof[t].get('xg') or 0)):
        if qualified_only and tid not in qualified:
            continue
        if nm.get(tid, 0) < 2:
            continue
        fl = _flags(prof[tid], field)
        if fl and "Sin patrones" in fl[0]:
            continue
        print(f"\n[{names.get(tid,tid)}] ({nm.get(tid,0)}p)")
        for f in fl:
            print("   • " + f)


if __name__ == "__main__":
    args = sys.argv[1:]
    qual = "--qualified" in args
    focus = next((a for a in args if not a.startswith("--")), None)
    scan(focus=focus, qualified_only=qual)
