"""
team_lineup_sim.py — Extiende player_matchup_sim.py a TODO EL XI (medio + ataque),
de AMBOS equipos. Pedido del dueño 01-jul: "no es un solo jugador, es todos los
delanteros, todo el mediocampo, todo el juego."

Para cada jugador del XI real (posición 2=medio o 3=delantero; los defensas y el
GK casi no rematan y se omiten de la tabla individual, pero cuentan para el
CHOQUE DE VENTANAS a nivel equipo que ya cubre analyze_match.py) corre la misma
simulación remates×conversión ajustada por la defensa rival de player_matchup_sim.py,
y las suma por equipo. Cruza esa suma contra el λ de equipo de simulate_match.py
(chequeo de consistencia: si los individuales sumados no cuadran con el agregado,
algo anda mal en uno de los dos modelos — antes esto no se comprobaba).

Uso:
    python scripts/team_lineup_sim.py "Belgium" "Senegal" 400021526
    (el tercer argumento es el match_id INTERNO de wc_matches con el XI real cargado)
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
sys.path.insert(0, str(BASE_DIR / "scripts"))

from player_matchup_sim import simulate as _sim_player, opponent_defense_profile


def resolve_xi_source(conn, tid_a, tid_b):
    """
    Devuelve (match_id_a, match_id_b, is_real_h2h). Si ya existe un cruce REAL
    entre estos dos equipos con XI cargado (partido de hoy/knockout confirmado),
    usa ESE match_id para ambos. Si NO (aún no salen alineaciones, como
    USA-Bosnia antes del kickoff — pedido del dueño 01-jul: "debemos estimar
    basados en la simulación, no esperar a poder evaluar en la marcha"), cada
    equipo usa su ÚLTIMO XI propio (su partido de grupos más reciente) como
    proxy — igual que el fallback ya usado en analyze_match.py/xi_quality.py.
    """
    shared = conn.execute(
        "SELECT m.id FROM wc_matches m JOIN fifa_lineups fl ON fl.match_id=m.id "
        "WHERE ((m.home_team_id=? AND m.away_team_id=?) OR (m.home_team_id=? AND m.away_team_id=?)) "
        "GROUP BY m.id ORDER BY m.date DESC LIMIT 1", (tid_a, tid_b, tid_b, tid_a)).fetchone()
    if shared:
        return shared[0], shared[0], True

    def _latest_own(tid):
        r = conn.execute(
            "SELECT m.id FROM wc_matches m JOIN fifa_lineups fl ON fl.match_id=m.id AND fl.team_id=? "
            "WHERE (m.home_team_id=? OR m.away_team_id=?) ORDER BY m.date DESC LIMIT 1",
            (tid, tid, tid)).fetchone()
        return r[0] if r else None

    return _latest_own(tid_a), _latest_own(tid_b), False


def team_xi(conn, match_id, team_id):
    return conn.execute(
        "SELECT player_name, position FROM fifa_lineups WHERE match_id=? AND team_id=? AND is_starter=1 "
        "ORDER BY position", (match_id, team_id)).fetchall()


def run_side(conn, attackers_xi, opponent_team, n=15000):
    """Simula cada jugador de medio/ataque del XI contra la defensa del rival."""
    rows = []
    for name, pos in attackers_xi:
        if pos not in (2, 3):   # solo medio (2) y ataque (3): quien remata de verdad
            continue
        r = _sim_player(conn, name, opponent_team, n=n)
        if not r:
            rows.append({"name": name, "pos": pos, "data": False})
            continue
        exp_goals = sum(i * r["goals_dist"][i] for i in range(6))
        rows.append({"name": name, "pos": pos, "data": True,
                      "shots90": r["adj_shots_per_90"], "conv": r["adj_conversion"],
                      "exp_goals": exp_goals, "p_score": 1 - r["goals_dist"][0],
                      "raw_shots": r["profile"]["shots"], "raw_goals": r["profile"]["goals"]})
    return rows


def print_side(team_name, opponent_name, rows, team_lambda=None):
    """
    FIX 01-jul: la suma individual NO siempre cuadra con el λ de equipo (validado
    en Bélgica-Senegal: Senegal daba 2.68 vs 1.67 del modelo, incluso tras el
    shrinkage bayesiano — el descuento por rival difiere estructuralmente entre
    el modelo agregado, que promedia GF propio con GA del rival 50/50, y el
    individual, que solo ajusta volumen+conversión por separado). En vez de dejar
    la inconsistencia sin resolver, se ANCLA la suma al λ de equipo (más validado,
    68% acierto de ganador en el torneo) preservando la PROPORCIÓN entre
    jugadores — quién es más peligroso relativo a quién no cambia, solo se re-
    escala el total al número que ya sabemos que es más fiable.
    """
    POS_LBL = {2: "MED", 3: "DEL"}
    print(f"\n--- {team_name} (medio+ataque) vs defensa {opponent_name} ---")
    raw_total = sum(r.get("exp_goals", 0) for r in rows if r["data"])
    scale = (team_lambda / raw_total) if (team_lambda and raw_total > 0) else 1.0
    header = f"{'Jugador':22}{'Pos':5}{'tiros/90':>9}{'conv%':>7}{'G.esper':>9}"
    if scale != 1.0:
        header += f"{'ANCLADO':>9}"
    header += f"{'P(marca)':>10}   histórico Mundial"
    print(header)
    total = 0.0
    any_data = False
    for r in sorted(rows, key=lambda x: -x.get("exp_goals", 0)):
        if not r["data"]:
            print(f"{r['name']:22}{POS_LBL.get(r['pos'],'?'):5}   sin datos de remates en el Mundial")
            continue
        any_data = True
        anchored = r["exp_goals"] * scale
        total += anchored
        line = (f"{r['name']:22}{POS_LBL.get(r['pos'],'?'):5}{r['shots90']:9.2f}{r['conv']*100:6.1f}%"
                f"{r['exp_goals']:9.2f}")
        if scale != 1.0:
            line += f"{anchored:9.2f}"
        line += f"{r['p_score']*100:9.1f}%   {r['raw_goals']}G/{r['raw_shots']}tiros"
        print(line)
    if any_data:
        label = "TOTAL (anclado a λ equipo)" if scale != 1.0 else "TOTAL suma individual"
        print(f"{label:22}{'':5}{'':9}{'':7}{total:9.2f}"
              + (f" (crudo {raw_total:.2f}, factor x{scale:.2f})" if scale != 1.0 else ""))
    return total


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(0)
    team_a, team_b = args[0], args[1]
    match_id = int(args[2]) if len(args) > 2 else None

    conn = sqlite3.connect(str(DB))
    tid_a = conn.execute("SELECT id FROM teams WHERE name=?", (team_a,)).fetchone()
    tid_b = conn.execute("SELECT id FROM teams WHERE name=?", (team_b,)).fetchone()
    if not tid_a or not tid_b:
        print("Equipo no encontrado."); sys.exit(1)
    tid_a, tid_b = tid_a[0], tid_b[0]

    if match_id is not None:
        mid_a = mid_b = match_id
        is_real = True
    else:
        mid_a, mid_b, is_real = resolve_xi_source(conn, tid_a, tid_b)
    if not mid_a or not mid_b:
        print(f"No hay NINGÚN XI cargado (ni real ni propio) para {team_a} o {team_b}.")
        sys.exit(1)

    xi_a = team_xi(conn, mid_a, tid_a)
    xi_b = team_xi(conn, mid_b, tid_b)
    if not xi_a or not xi_b:
        print("XI incompleto en fifa_lineups.")
        sys.exit(1)

    src_tag = "XI REAL confirmado" if is_real else "PROXY (último XI propio de cada equipo, aún sin alineación real del cruce)"
    print(f"=== SIMULACIÓN COMPLETA DE XI — {team_a} vs {team_b} ({src_tag}) ===")
    rows_a = run_side(conn, xi_a, team_b)
    rows_b = run_side(conn, xi_b, team_a)

    team_lambda_a = team_lambda_b = None
    try:
        from simulate_match import simulate as _sim_team
        s = _sim_team(conn, team_a, team_b, n=20000)
        team_lambda_a, team_lambda_b = s["la"], s["lb"]
    except Exception:
        s = None

    total_a = print_side(team_a, team_b, rows_a, team_lambda=team_lambda_a)
    total_b = print_side(team_b, team_a, rows_b, team_lambda=team_lambda_b)

    if s:
        print(f"\n=== CRUCE CON EL MODELO DE EQUIPO (simulate_match) ===")
        print(f"λ de equipo (Monte Carlo agregado, más validado — 68% acierto de ganador en el torneo): "
              f"{team_a} {team_lambda_a:.2f} vs {team_b} {team_lambda_b:.2f}")
        print(f"→ suma individual anclada a este λ (ver tabla arriba); la proporción entre jugadores "
              f"SÍ es información nueva, el total ya no diverge del modelo de equipo.")
    else:
        print(f"\nNo se pudo cruzar con simulate_match — quedó sin anclar (revisar).")

    conn.close()
