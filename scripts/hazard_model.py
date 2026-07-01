"""
hazard_model.py — PROTOTIPO de la frontera pendiente: hazard por minuto + auto-excitacion.

Motivacion (ver LEARNING_LOOP.md / memoria mundial2026-pool): el Monte Carlo actual
(simulate_match.py) usa un Poisson de TASA PLANA por partido (lambda unico para 90').
Eso es CIEGO a que un equipo pueda derrumbarse EN OLEADAS (Senegal: 3 goles en
43'/48'/58' vs Noruega, 3 en 66'/82'/90' vs Francia) — un proceso de Poisson homogeneo
predice esos goles ESPARCIDOS, no agrupados. Si el derrumbe-en-racha es real (no solo
anecdotico), un proceso AUTO-EXCITANTE (tipo Hawkes: conceder sube temporalmente el
riesgo de volver a conceder) captura mas varianza real que el Poisson plano.

Dos fases, EN ORDEN (no saltar la 1 para llegar a la 2 — rigor del proyecto):
  FASE 1 — TEST EMPIRICO honesto: ¿los goles encajados por un mismo equipo en el MISMO
  partido estan mas AGRUPADOS en el tiempo de lo que predeciria colocarlos al azar en
  90'? Se compara la distribucion real de huecos entre goles consecutivos encajados
  contra 10000 simulaciones de "mismos N goles colocados uniformemente al azar en 90'"
  (mismo numero de goles, mismo partido) — control honesto, no strawman.
  FASE 2 — si la Fase 1 valida el efecto: simulador minuto-a-minuto con hazard base
  por bucket (igual que simulate_match) + boost temporal de auto-excitacion tras
  conceder, calibrado con el exceso medido en Fase 1. Backtest contra el Poisson
  plano en los partidos de grupos YA JUGADOS (Brier) — si no mejora, se DESCARTA
  (regla del proyecto: ninguna señal entra sin subir el ledger).

Uso:
    python scripts/hazard_model.py --test          # Fase 1 (test de agrupamiento)
    python scripts/hazard_model.py --backtest       # Fase 2 (Brier hazard vs Poisson plano)
    python scripts/hazard_model.py "Senegal" "Belgium"   # simulacion hazard concreta
"""
import math
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

MATCH_MINUTES = 90
WINDOW = 15          # ventana de "racha" tras conceder (min)
N_RANDOM_SIMS = 10000  # sims del control (colocar N goles al azar)


# ---------------------------------------------------------------- datos base
def _match_team_goals(conn):
    """
    match_id -> {team_id: sorted [minutos en que ESE equipo concedio]}
    Reconstruido de fifa_match_events (type 0/41 = gol/penal), igual fuente
    que simulate_match.forensics.
    """
    goals = defaultdict(list)      # fmid -> [(minute, scoring_team_id)]
    teams_in = defaultdict(set)    # fmid -> {team_id, team_id}
    for fmid, mn, dbt in conn.execute(
            "SELECT fifa_match_id,minute_num,db_team_id FROM fifa_match_events "
            "WHERE type_code IN (0,41) AND db_team_id IS NOT NULL AND minute_num IS NOT NULL"):
        goals[fmid].append((mn, dbt))
    for fmid, dbt in conn.execute(
            "SELECT DISTINCT fifa_match_id,db_team_id FROM fifa_match_events WHERE db_team_id IS NOT NULL"):
        teams_in[fmid].add(dbt)

    conceded = {}  # fmid -> {team_id: [minutos encajados]}
    for fmid, tset in teams_in.items():
        if len(tset) != 2:
            continue
        t1, t2 = tuple(tset)
        gs = goals.get(fmid, [])
        conceded[fmid] = {
            t1: sorted(m for m, d in gs if d == t2),
            t2: sorted(m for m, d in gs if d == t1),
        }
    return conceded


# ------------------------------------------------------- FASE 1: test de agrupamiento
def gap_clustering_test(conn, window=WINDOW, n_random=N_RANDOM_SIMS):
    conceded = _match_team_goals(conn)

    real_gaps = []
    for fmid, by_team in conceded.items():
        for tid, mins in by_team.items():
            if len(mins) < 2:
                continue
            for a, b in zip(mins, mins[1:]):
                real_gaps.append(b - a)

    real_short = sum(1 for g in real_gaps if g <= window)
    real_frac = real_short / len(real_gaps) if real_gaps else 0.0

    # control: para cada partido/equipo con >=2 goles encajados, colocar el MISMO
    # numero de goles al azar en [1,90] y medir la misma fraccion de huecos cortos.
    rng = random.Random(42)
    null_fracs = []
    cases = [(len(mins)) for by_team in conceded.values() for mins in by_team.values() if len(mins) >= 2]
    for _ in range(n_random):
        short = total = 0
        for k in cases:
            pts = sorted(rng.randint(1, MATCH_MINUTES) for _ in range(k))
            for a, b in zip(pts, pts[1:]):
                total += 1
                if b - a <= window:
                    short += 1
        null_fracs.append(short / total if total else 0.0)
    null_mean = sum(null_fracs) / len(null_fracs)
    null_fracs_sorted = sorted(null_fracs)
    # p-value de una cola: cuantas veces el azar iguala o supera lo real
    p_val = sum(1 for f in null_fracs_sorted if f >= real_frac) / len(null_fracs_sorted)

    print(f"=== TEST DE AGRUPAMIENTO (goles encajados por el mismo equipo, mismo partido) ===")
    print(f"Huecos reales entre goles consecutivos encajados: n={len(real_gaps)}")
    print(f"  fraccion con hueco <={window}' : {real_frac:.3f}  ({real_short}/{len(real_gaps)})")
    print(f"Control (mismos N goles/partido colocados AL AZAR en 90', {n_random} sims):")
    print(f"  fraccion esperada bajo azar    : {null_mean:.3f}  (rango 90% CI [{null_fracs_sorted[int(0.05*n_random)]:.3f}, {null_fracs_sorted[int(0.95*n_random)]:.3f}])")
    print(f"  p-valor (real >= azar por casualidad): {p_val:.4f}")
    if real_frac > null_fracs_sorted[int(0.95*n_random)]:
        print(f"  -> CLUSTERING REAL: los goles encajados se agrupan MAS de lo que el azar produce (p<{p_val:.3f}).")
        print(f"     Justifica auto-excitacion (Fase 2).")
    else:
        print(f"  -> NULO: la fraccion real cae DENTRO de lo que el azar ya produce.")
        print(f"     El patron Senegal es varianza normal de un proceso plano, NO derrumbe sistematico.")
        print(f"     Por disciplina del proyecto: NO construir auto-excitacion sin esta evidencia.")
    return real_frac, null_mean, p_val


# ------------------------------------------------------- ejemplo por equipo (forense)
def team_examples(conn, min_goals=3):
    conceded = _match_team_goals(conn)
    name = {r[0]: r[1] for r in conn.execute("SELECT id,name FROM teams")}
    by_team_matches = defaultdict(list)
    for fmid, by_team in conceded.items():
        for tid, mins in by_team.items():
            if len(mins) >= min_goals:
                by_team_matches[tid].append(mins)
    print(f"\n=== EQUIPOS con >= {min_goals} goles encajados en UN partido (ejemplos de racha) ===")
    for tid, matches in by_team_matches.items():
        for mins in matches:
            gaps = [b - a for a, b in zip(mins, mins[1:])]
            print(f"  {name.get(tid, tid):18} encajo en {mins}  huecos {gaps}")


# ------------------------------------------------------- FASE 2: hazard por bucket
BUCKET_EDGES = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 200)]
NB = len(BUCKET_EDGES)


def _bkt(m):
    for i, (lo, hi) in enumerate(BUCKET_EDGES):
        if lo <= m <= hi:
            return i
    return NB - 1


def team_bucket_rates(conn):
    """
    {team_id: {"att": [6 tasas gol/partido/bucket], "def": [...], "n": partidos}}
    Restringido a grupos (mismo alcance que _rate() en simulate_match, apples-to-apples).
    """
    games = defaultdict(int)
    att = defaultdict(lambda: [0]*NB)
    dfn = defaultdict(lambda: [0]*NB)
    for hid, aid in conn.execute(
            "SELECT home_team_id, away_team_id FROM wc_matches WHERE stage='group' AND played=1"):
        games[hid] += 1
        games[aid] += 1
    for mid, tid, minute in conn.execute(
            "SELECT g.match_id, g.team_id, g.minute FROM fifa_match_goals g "
            "JOIN wc_matches w ON g.match_id=w.id WHERE w.stage='group'"):
        row = conn.execute("SELECT home_team_id, away_team_id FROM wc_matches WHERE id=?", (mid,)).fetchone()
        if not row:
            continue
        hid, aid = row
        opp = aid if tid == hid else hid if tid == aid else None
        if opp is None:
            continue
        b = _bkt(minute if minute is not None else 45)
        att[tid][b] += 1
        dfn[opp][b] += 1
    out = {}
    for tid, n in games.items():
        if n == 0:
            continue
        out[tid] = {
            "att": [att[tid][i]/n for i in range(NB)],
            "def": [dfn[tid][i]/n for i in range(NB)],
            "n": n,
        }
    return out


def window_clash_lambda(rates, team_a, team_b):
    """
    Lambda total de A, ponderando por bucket donde el ataque de A y la fragilidad
    de B COINCIDEN (por encima de su propio promedio) — cuantifica el 'choque de
    ventanas' que hoy solo se imprime como texto en analyze_match.py.
    """
    ra, rb = rates[team_a], rates[team_b]
    a_avg = sum(ra["att"]) / NB
    b_avg = sum(rb["def"]) / NB
    total = 0.0
    detail = []
    for i in range(NB):
        base = (ra["att"][i] + rb["def"][i]) / 2
        a_hot = ra["att"][i] > a_avg
        b_weak = rb["def"][i] > b_avg
        if a_hot and b_weak:
            w = 1.25   # choque real: amenaza + brecha coinciden
        elif a_hot and not b_weak:
            w = 0.85   # ventana neutralizada (ataca donde el rival aguanta)
        else:
            w = 1.0
        total += base * w
        detail.append((i, base, w))
    return total, detail


def flat_lambda(rates, team_a, team_b):
    ra, rb = rates[team_a], rates[team_b]
    return (sum(ra["att"]) + sum(rb["def"])) / 2


def _skellam(la, lb, kmax=12):
    from math import exp, factorial
    px = [exp(-la) * la**k / factorial(k) for k in range(kmax)]
    py = [exp(-lb) * lb**k / factorial(k) for k in range(kmax)]
    draw = sum(px[k]*py[k] for k in range(kmax))
    home = sum(px[k]*py[j] for k in range(kmax) for j in range(kmax) if k > j)
    away = max(0.0, 1 - draw - home)
    return home, draw, away


def _brier(probs, outcome):
    # outcome: 0=home,1=draw,2=away
    onehot = [1.0 if i == outcome else 0.0 for i in range(3)]
    return sum((p - o)**2 for p, o in zip(probs, onehot))


def backtest(conn):
    """
    Compara, EN LOS 72 PARTIDOS DE GRUPOS YA JUGADOS (in-sample, mismo alcance que
    las auditorias previas del proyecto — necesita validacion OOS antes de usarse en
    produccion): Brier del lambda PLANO (el que ya usa simulate_match) vs el lambda
    con PESO POR CHOQUE DE VENTANAS (Fase 2 de este prototipo).
    """
    rates = team_bucket_rates(conn)
    name = {r[0]: r[1] for r in conn.execute("SELECT id,name FROM teams")}
    brier_flat = brier_clash = 0.0
    n = 0
    for hid, aid, sh, sa in conn.execute(
            "SELECT home_team_id, away_team_id, score_home, score_away FROM wc_matches "
            "WHERE stage='group' AND played=1"):
        if hid not in rates or aid not in rates:
            continue
        outcome = 0 if sh > sa else (2 if sa > sh else 1)

        lf_h = flat_lambda(rates, hid, aid)
        lf_a = flat_lambda(rates, aid, hid)
        brier_flat += _brier(_skellam(lf_h, lf_a), outcome)

        lc_h, _ = window_clash_lambda(rates, hid, aid)
        lc_a, _ = window_clash_lambda(rates, aid, hid)
        brier_clash += _brier(_skellam(lc_h, lc_a), outcome)
        n += 1

    print(f"=== BACKTEST (in-sample, {n} partidos de grupos) — Brier (menor=mejor) ===")
    print(f"  Lambda PLANO (actual, simulate_match)     : {brier_flat/n:.4f}")
    print(f"  Lambda CHOQUE-DE-VENTANAS (este prototipo): {brier_clash/n:.4f}")
    delta = brier_flat/n - brier_clash/n
    if delta > 0.002:
        print(f"  -> MEJORA ({delta:+.4f}). Candidato a validar OUT-OF-SAMPLE antes de activar (regla del proyecto).")
    elif delta < -0.002:
        print(f"  -> EMPEORA ({delta:+.4f}). Se DESCARTA — el peso por choque de ventanas no ayuda a nivel agregado.")
    else:
        print(f"  -> SIN DIFERENCIA relevante ({delta:+.4f}). El peso por ventanas no mueve el agregado;")
        print(f"     puede seguir siendo util como SEÑAL CUALITATIVA (ya lo es en analyze_match) pero no como lambda numerico.")


def backtest_loo(conn):
    """
    Version LEAVE-ONE-OUT del backtest: para cada partido, la tasa por bucket de
    CADA equipo se calcula excluyendo ESE partido (usando solo sus otros 2 juegos
    de grupo) — quita la fuga trivial de "el resultado ayuda a predecirse a si
    mismo" que tiene el backtest in-sample de arriba. Con solo 2 partidos de
    referencia por equipo el ruido es alto; se reporta como lo que es: un check
    mas honesto, no una prueba definitiva (para eso hace falta mas de un Mundial).
    """
    name = {r[0]: r[1] for r in conn.execute("SELECT id,name FROM teams")}
    matches = conn.execute(
        "SELECT id, home_team_id, away_team_id, score_home, score_away FROM wc_matches "
        "WHERE stage='group' AND played=1").fetchall()
    all_goals = conn.execute(
        "SELECT g.match_id, g.team_id, g.minute FROM fifa_match_goals g "
        "JOIN wc_matches w ON g.match_id=w.id WHERE w.stage='group'").fetchall()
    match_teams = {m[0]: (m[1], m[2]) for m in matches}

    def rates_excluding(mid_excl):
        games = defaultdict(int)
        att = defaultdict(lambda: [0]*NB)
        dfn = defaultdict(lambda: [0]*NB)
        for mid, hid, aid, sh, sa in matches:
            if mid == mid_excl:
                continue
            games[hid] += 1
            games[aid] += 1
        for mid, tid, minute in all_goals:
            if mid == mid_excl:
                continue
            hid, aid = match_teams[mid]
            opp = aid if tid == hid else hid if tid == aid else None
            if opp is None:
                continue
            b = _bkt(minute if minute is not None else 45)
            att[tid][b] += 1
            dfn[opp][b] += 1
        out = {}
        for tid, n in games.items():
            if n:
                out[tid] = {"att": [att[tid][i]/n for i in range(NB)],
                            "def": [dfn[tid][i]/n for i in range(NB)], "n": n}
        return out

    brier_flat = brier_clash = 0.0
    n = 0
    for mid, hid, aid, sh, sa in matches:
        rates = rates_excluding(mid)
        if hid not in rates or aid not in rates:
            continue
        outcome = 0 if sh > sa else (2 if sa > sh else 1)
        lf_h, lf_a = flat_lambda(rates, hid, aid), flat_lambda(rates, aid, hid)
        brier_flat += _brier(_skellam(lf_h, lf_a), outcome)
        lc_h, _ = window_clash_lambda(rates, hid, aid)
        lc_a, _ = window_clash_lambda(rates, aid, hid)
        brier_clash += _brier(_skellam(lc_h, lc_a), outcome)
        n += 1

    print(f"\n=== BACKTEST LEAVE-ONE-OUT ({n} partidos, cada uno predicho SIN su propio dato) ===")
    print(f"  Lambda PLANO      : {brier_flat/n:.4f}")
    print(f"  Lambda CHOQUE      : {brier_clash/n:.4f}")
    delta = brier_flat/n - brier_clash/n
    tag = "MEJORA" if delta > 0.002 else ("EMPEORA" if delta < -0.002 else "SIN DIFERENCIA relevante")
    print(f"  -> {tag} ({delta:+.4f})")


def show_matchup(conn, team_a, team_b):
    rates = team_bucket_rates(conn)
    tid = {r[1]: r[0] for r in conn.execute("SELECT id,name FROM teams")}
    a, b = tid.get(team_a), tid.get(team_b)
    if a not in rates or b not in rates:
        print(f"Faltan datos de grupos para {team_a} o {team_b} (bucket_rates solo cubre fase de grupos).")
        return
    lf_a, lf_b = flat_lambda(rates, a, b), flat_lambda(rates, b, a)
    lc_a, det_a = window_clash_lambda(rates, a, b)
    lc_b, det_b = window_clash_lambda(rates, b, a)
    print(f"=== {team_a} vs {team_b} — lambda PLANO vs CHOQUE-DE-VENTANAS ===")
    print(f"  PLANO:  {team_a} {lf_a:.2f}  /  {team_b} {lf_b:.2f}")
    print(f"  CHOQUE: {team_a} {lc_a:.2f}  /  {team_b} {lc_b:.2f}")
    LBL = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90+"]
    print(f"  detalle {team_a}: " + " ".join(f"{LBL[i]}(x{w:.2f})" for i, base, w in det_a))
    print(f"  detalle {team_b}: " + " ".join(f"{LBL[i]}(x{w:.2f})" for i, base, w in det_b))
    h, d, aw = _skellam(lc_a, lc_b)
    print(f"  1X2 (choque-de-ventanas, Skellam): {team_a} {h*100:.0f}% / empate {d*100:.0f}% / {team_b} {aw*100:.0f}%")


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if "--test" in sys.argv:
        gap_clustering_test(conn)
        team_examples(conn)
    elif "--backtest" in sys.argv:
        backtest(conn)
        backtest_loo(conn)
    else:
        args = [x for x in sys.argv[1:] if not x.startswith("--")]
        if len(args) >= 2:
            show_matchup(conn, args[0], args[1])
        else:
            print(__doc__)
    conn.close()
