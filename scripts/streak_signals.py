"""
streak_signals.py — RACHAS especificas como señal de marcador (nace de fallo real).

Origen (03-jul): en Portugal-Croacia mi sello 2-1 (H2H: Croacia le marco a Portugal
6 seguidos) era EXACTO y lo sobre-corregi a 1-0 con el prior generico de xG. El
real fue 2-1. La leccion quedo en LEARNING_LOOP pero NO como herramienta — este
modulo la encoda y la BACKTESTEA (regla del proyecto: ninguna señal entra sin medirse).

SEÑALES (todas del torneo actual, wc_matches):
  - scored_all:     el equipo marco en TODOS sus partidos -> P(lo blanqueen) baja
  - conceded_all:   el equipo encajo en TODOS -> P(porteria a cero propia) baja
  - h2h_scored_streak: si hay historial directo (team_matches), cuantos partidos
    seguidos lleva marcandole al rival de HOY (la señal Croacia)

REGLA DE AJUSTE DE MARCADOR (la que se backtestea):
  si el pick dice que X recibe 0 goles, PERO el rival marco-en-todos (torneo) o
  le marca a X hace >=3 directos seguidos -> subir el marcador del rival 0->1.

Uso:
    python scripts/streak_signals.py "Switzerland" "Algeria"     # señales del cruce
    python scripts/streak_signals.py --backtest                   # mide la regla en R32
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def team_streaks(conn, team, before_date=None):
    """Rachas del torneo ACTUAL para un equipo (opcionalmente solo partidos previos a una fecha)."""
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
    if not tid:
        return None
    tid = tid[0]
    q = ("SELECT home_team_id, score_home, score_away FROM wc_matches "
         "WHERE (home_team_id=? OR away_team_id=?) AND played=1 AND stage IN ('group','R32')")
    args = [tid, tid]
    if before_date:
        q += " AND date < ?"
        args.append(before_date)
    gf_all = ga_all = True
    n = 0
    for hid, sh, sa in conn.execute(q, args):
        f, c = (sh, sa) if hid == tid else (sa, sh)
        n += 1
        if f == 0:
            gf_all = False
        if c == 0:
            ga_all = False
    return {"team": team, "n": n, "scored_all": gf_all and n >= 2, "conceded_all": ga_all and n >= 2}


def h2h_scored_streak(conn, team, rival):
    """Cuantos enfrentamientos directos seguidos lleva `team` marcandole a `rival`."""
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team,)).fetchone()
    if not tid:
        return 0
    rows = conn.execute(
        "SELECT goals_for FROM team_matches WHERE team_id=? AND opponent_name=? ORDER BY date DESC LIMIT 8",
        (tid[0], rival)).fetchall()
    streak = 0
    for (gf,) in rows:
        if gf and gf > 0:
            streak += 1
        else:
            break
    return streak


def adjust_scoreline(conn, team_a, team_b, pick_a, pick_b, before_date=None, verbose=False):
    """Aplica la regla: un 0 en el marcador se sube a 1 si el que 'no marca' tiene
    racha de marcar-en-todos (torneo) o racha directa >=3 vs este rival."""
    # BACKTEST 03-jul (12 R32): la version amplia (torneo scored_all/conceded_all
    # tambien auto-ajustaba) salio NEUTRA 4/12 vs 4/12 — gano Portugal 2-1 pero
    # rompio Francia 3-0 (Suecia 'marco en todos' y Francia la blanqueo igual:
    # la racha generica ignora la calidad de la defensa de enfrente). El AUTO-
    # AJUSTE queda restringido a la señal ORIGINAL y especifica del cruce:
    # racha H2H >=3 directa (el caso Croacia, que SI habria dado el exacto).
    # Con esa restriccion el backtest da 5/12 — PERO la restriccion se eligio
    # DESPUES de ver los resultados (riesgo de sobreajuste declarado):
    # tratarla como HIPOTESIS y re-medirla en cada ronda, no como regla probada.
    # Las rachas de torneo quedan como BANDERA informativa (no tocan el numero).
    sa_ = team_streaks(conn, team_a, before_date)
    sb_ = team_streaks(conn, team_b, before_date)
    h2h_a = h2h_scored_streak(conn, team_a, team_b)
    h2h_b = h2h_scored_streak(conn, team_b, team_a)
    adj_a, adj_b = pick_a, pick_b
    notes = []
    if sb_ and sb_["scored_all"]:
        notes.append(f"(flag) {team_b} marcó en todos sus partidos ({sb_['n']})")
    if sa_ and sa_["scored_all"]:
        notes.append(f"(flag) {team_a} marcó en todos sus partidos ({sa_['n']})")
    if pick_b == 0 and h2h_b >= 3:
        adj_b = 1
        notes.append(f"0→1 para {team_b}: racha H2H {h2h_b} seguidos marcándole a {team_a}")
    if pick_a == 0 and h2h_a >= 3:
        adj_a = 1
        notes.append(f"0→1 para {team_a}: racha H2H {h2h_a} seguidos marcándole a {team_b}")
    if adj_a == adj_b and pick_a != pick_b:
        # el ajuste no debe convertir una victoria en empate: sube tambien al ganador
        if pick_a > pick_b: adj_a = adj_b + 1
        else: adj_b = adj_a + 1
        notes.append("ajuste preservó al ganador (+1)")
    if verbose:
        for nt in notes:
            print("  ↺", nt)
    return adj_a, adj_b, notes


def backtest(conn):
    """Mide la regla en los R32 JUGADOS: argmax+cap original vs argmax+cap+rachas.
    Rachas calculadas SOLO con partidos previos a cada fecha (sin fuga)."""
    # picks argmax+cap que estaban sellados/medidos antes (del estudio n=80, escala 1.10)
    argmax_cap = {
        400021518: (0, 1), 400021519: (1, 1), 400021520: (3, 0), 400021521: (1, 1),
        400021522: (1, 1), 400021523: (3, 0), 400021524: (0, 0), 400021525: (1, 0),
        400021526: (3, 1), 400021527: (3, 1), 400021528: (3, 0), 400021529: (2, 0)}
    rows = conn.execute(
        "SELECT id, home_team_name, away_team_name, score_home, score_away, date FROM wc_matches "
        "WHERE stage='R32' AND played=1 ORDER BY id").fetchall()
    base_hits = adj_hits = n = 0
    print(f"{'partido':34}{'real':>6}{'base':>7}{'ajust':>7}")
    for mid, hn, an, sh, sa, dt in rows:
        if mid not in argmax_cap:
            continue
        n += 1
        ph, pa = argmax_cap[mid]
        ah, aa, _ = adjust_scoreline(conn, hn, an, ph, pa, before_date=dt)
        b_ok = (ph, pa) == (sh, sa)
        a_ok = (ah, aa) == (sh, sa)
        base_hits += b_ok
        adj_hits += a_ok
        mark = "  <-- cambió" if (ah, aa) != (ph, pa) else ""
        print(f"{hn[:15]+' v '+an[:15]:34}{f'{sh}-{sa}':>6}{f'{ph}-{pa}':>7}{f'{ah}-{aa}':>7}{mark}")
    print(f"\nEXACTOS — base (argmax+cap): {base_hits}/{n} ({100*base_hits/n:.0f}%)  |  "
          f"con rachas: {adj_hits}/{n} ({100*adj_hits/n:.0f}%)")
    if adj_hits > base_hits:
        print("→ La regla de rachas MEJORA el picker. Mantener integrada.")
    elif adj_hits == base_hits:
        print("→ Neutra en esta muestra; mantener por la lógica causal, re-medir cada ronda.")
    else:
        print("→ EMPEORA — descartar (regla del proyecto).")


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if "--backtest" in sys.argv:
        backtest(conn)
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if len(args) >= 2:
            a, b = args[0], args[1]
            sa_, sb_ = team_streaks(conn, a), team_streaks(conn, b)
            print(f"{a}: marcó en todos={sa_['scored_all']} · encajó en todos={sa_['conceded_all']} (n={sa_['n']})")
            print(f"{b}: marcó en todos={sb_['scored_all']} · encajó en todos={sb_['conceded_all']} (n={sb_['n']})")
            print(f"H2H: {a} lleva {h2h_scored_streak(conn, a, b)} seguidos marcándole a {b}; "
                  f"{b} lleva {h2h_scored_streak(conn, b, a)} vs {a}")
        else:
            print(__doc__)
    conn.close()
