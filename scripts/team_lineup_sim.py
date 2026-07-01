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


def print_side(team_name, opponent_name, rows):
    POS_LBL = {2: "MED", 3: "DEL"}
    print(f"\n--- {team_name} (medio+ataque) vs defensa {opponent_name} ---")
    print(f"{'Jugador':22}{'Pos':5}{'tiros/90':>9}{'conv%':>7}{'G.esper':>9}{'P(marca)':>10}   histórico Mundial")
    total = 0.0
    any_data = False
    for r in sorted(rows, key=lambda x: -x.get("exp_goals", 0)):
        if not r["data"]:
            print(f"{r['name']:22}{POS_LBL.get(r['pos'],'?'):5}   sin datos de remates en el Mundial")
            continue
        any_data = True
        total += r["exp_goals"]
        print(f"{r['name']:22}{POS_LBL.get(r['pos'],'?'):5}{r['shots90']:9.2f}{r['conv']*100:6.1f}%"
              f"{r['exp_goals']:9.2f}{r['p_score']*100:9.1f}%   {r['raw_goals']}G/{r['raw_shots']}tiros")
    if any_data:
        print(f"{'TOTAL suma individual':22}{'':5}{'':9}{'':7}{total:9.2f}")
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

    if match_id is None:
        r = conn.execute(
            "SELECT m.id FROM wc_matches m JOIN fifa_lineups fl ON fl.match_id=m.id "
            "WHERE ((m.home_team_id=? AND m.away_team_id=?) OR (m.home_team_id=? AND m.away_team_id=?)) "
            "GROUP BY m.id ORDER BY m.date DESC LIMIT 1", (tid_a, tid_b, tid_b, tid_a)).fetchone()
        match_id = r[0] if r else None
    if not match_id:
        print(f"No hay XI real cargado para {team_a} vs {team_b}. Pasa el match_id o carga fifa_lineups primero.")
        sys.exit(1)

    xi_a = team_xi(conn, match_id, tid_a)
    xi_b = team_xi(conn, match_id, tid_b)
    if not xi_a or not xi_b:
        print("XI incompleto en fifa_lineups para ese match_id.")
        sys.exit(1)

    print(f"=== SIMULACIÓN COMPLETA DE XI — {team_a} vs {team_b} (match_id={match_id}) ===")
    rows_a = run_side(conn, xi_a, team_b)
    rows_b = run_side(conn, xi_b, team_a)
    total_a = print_side(team_a, team_b, rows_a)
    total_b = print_side(team_b, team_a, rows_b)

    print(f"\n=== CRUCE CON EL MODELO DE EQUIPO (simulate_match) ===")
    try:
        from simulate_match import simulate as _sim_team
        s = _sim_team(conn, team_a, team_b, n=20000)
        print(f"λ de equipo (Monte Carlo agregado): {team_a} {s['la']:.2f} vs {team_b} {s['lb']:.2f}")
        print(f"Suma de individuales (solo medio+ataque, este script): {team_a} {total_a:.2f} vs {team_b} {total_b:.2f}")
        da, db = s['la'] - total_a, s['lb'] - total_b
        print(f"Diferencia: {team_a} {da:+.2f} · {team_b} {db:+.2f} "
              f"(positivo = el agregado espera MÁS goles que la suma de medio+ataque individual — "
              f"la diferencia son los goles que 'faltan' de defensas/gente sin datos de remates registrados)")
    except Exception as e:
        print(f"No se pudo cruzar con simulate_match: {e}")

    conn.close()
