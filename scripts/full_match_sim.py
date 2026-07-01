"""
full_match_sim.py — Simulación REAL minuto a minuto, desde el primer balón, con
los jugadores del XI (pedido del dueño 01-jul: "esperaría una simulación real
desde el primer movimiento de pelota y de ahí con los datos de los jugadores").

Construida sobre team_lineup_sim.py (tasas por jugador, ya con shrinkage
bayesiano + ANCLAJE al λ de equipo — ver ese script para el porqué). Aquí se
usa la tasa de remates/90 CRUDA de cada jugador (volumen, para decidir CUÁNDO
y QUIÉN dispara) y la conversión ANCLADA (goles/remate ya reescalada para que
la suma cuadre con el modelo de equipo, más validado) para decidir si ese
remate es gol — así el marcador total de la simulación es SIEMPRE consistente
con `simulate_match.py`, y el reparto entre jugadores es información real.

MECÁNICA (por minuto, 1..90, ambos equipos en paralelo):
  para cada jugador de medio/ataque: Bernoulli(remates_90/90) → ¿dispara este minuto?
  si dispara: Bernoulli(conversión anclada) → ¿gol?
    si no gol: clasifica a puerta/fuera con el % de precisión de tiro del EQUIPO
               (match_team_stats.shots_on_target/shots_total) → 'parada' o 'fuera'

Se corre UNA vez como relato jugada-por-jugada, y N veces (Monte Carlo) para
comprobar que el marcador agregado cuadra con simulate_match (honestidad, no
solo un relato bonito).

Uso:
    python scripts/full_match_sim.py "Belgium" "Senegal"
    python scripts/full_match_sim.py "Belgium" "Senegal" --mc 3000   # solo el chequeo agregado
"""
import random
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
sys.path.insert(0, str(BASE_DIR / "scripts"))

from team_lineup_sim import team_xi, run_side, resolve_xi_source
from simulate_match import simulate as _sim_team


def _shot_accuracy(conn, team_id):
    row = conn.execute(
        "SELECT AVG(shots_on_target*1.0/shots_total) FROM match_team_stats "
        "WHERE team_id=? AND shots_total>0", (team_id,)).fetchone()
    return row[0] if row and row[0] else 0.33


def build_squad(conn, team_name, opponent_name, match_id):
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()[0]
    xi = team_xi(conn, match_id, tid)
    rows = run_side(conn, xi, opponent_name)
    raw_total = sum(r["exp_goals"] for r in rows if r["data"])
    return rows, raw_total, tid


def simulate_once(conn, team_a, team_b, rows_a, rows_b, scale_a, scale_b, acc_a, acc_b, rng, minutes=90):
    """Una corrida completa: devuelve (goles_a, goles_b, lista de eventos)."""
    events = []
    goals = {team_a: 0, team_b: 0}
    for minute in range(1, minutes + 1):
        for team_name, rows, scale, acc in ((team_a, rows_a, scale_a, acc_a), (team_b, rows_b, scale_b, acc_b)):
            for r in rows:
                if not r["data"] or not r.get("shots90"):
                    continue
                if rng.random() < r["shots90"] / 90:
                    anchored_conv = min(0.85, r["conv"] * scale)
                    if rng.random() < anchored_conv:
                        goals[team_name] += 1
                        events.append((minute, team_name, r["name"], "GOL"))
                    elif rng.random() < acc:
                        events.append((minute, team_name, r["name"], "parada del portero"))
                    else:
                        events.append((minute, team_name, r["name"], "fuera"))
    return goals[team_a], goals[team_b], events


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(0)
    team_a, team_b = args[0], args[1]
    mc_only = "--mc" in sys.argv
    n_mc = int(sys.argv[sys.argv.index("--mc") + 1]) if "--mc" in sys.argv else 2000

    conn = sqlite3.connect(str(DB))
    tid_a = conn.execute("SELECT id FROM teams WHERE name=?", (team_a,)).fetchone()
    tid_b = conn.execute("SELECT id FROM teams WHERE name=?", (team_b,)).fetchone()
    if not tid_a or not tid_b:
        print("Equipo no encontrado."); sys.exit(1)
    tid_a, tid_b = tid_a[0], tid_b[0]

    mid_a, mid_b, is_real = resolve_xi_source(conn, tid_a, tid_b)
    if not mid_a or not mid_b:
        print(f"No hay NINGÚN XI (ni real ni propio) para {team_a} o {team_b}."); sys.exit(1)
    src_tag = "XI REAL confirmado" if is_real else "PROXY (último XI propio de cada equipo — aún sin alineación real del cruce)"

    rows_a, raw_a, _ = build_squad(conn, team_a, team_b, mid_a)
    rows_b, raw_b, _ = build_squad(conn, team_b, team_a, mid_b)
    s = _sim_team(conn, team_a, team_b, n=20000)
    lam_a, lam_b = s["la"], s["lb"]
    scale_a = lam_a / raw_a if raw_a else 1.0
    scale_b = lam_b / raw_b if raw_b else 1.0
    acc_a = _shot_accuracy(conn, tid_a)
    acc_b = _shot_accuracy(conn, tid_b)

    rng = random.Random(7)
    if not mc_only:
        print(f"=== SIMULACIÓN JUGADA-POR-JUGADA — {team_a} vs {team_b} (desde el minuto 1, {src_tag}) ===\n")
        ga, gb, events = simulate_once(conn, team_a, team_b, rows_a, rows_b, scale_a, scale_b, acc_a, acc_b, rng)
        for minute, team, player, outcome in events:
            tag = "⚽ GOOOL" if outcome == "GOL" else ("🧤 parada" if "parada" in outcome else "↗ fuera")
            print(f"  {minute:3}' {team:10} — {player}: remata... {tag}")
        print(f"\nMARCADOR FINAL DE ESTA CORRIDA: {team_a} {ga} - {gb} {team_b}")
        print(f"(un solo relato posible entre miles — no es 'el' resultado, es UNA muestra coherente con las tasas reales)\n")

    print(f"=== VALIDACIÓN AGREGADA ({n_mc} corridas) — ¿el marcador simulado cuadra con simulate_match? ===")
    print(f"λ de equipo (referencia, más validado): {team_a} {lam_a:.2f}  {team_b} {lam_b:.2f}")
    tot_a = tot_b = 0
    wins_a = wins_b = draws = 0
    from collections import Counter
    scorelines = Counter()
    for i in range(n_mc):
        rng2 = random.Random(1000 + i)
        ga, gb, _ = simulate_once(conn, team_a, team_b, rows_a, rows_b, scale_a, scale_b, acc_a, acc_b, rng2)
        tot_a += ga; tot_b += gb
        scorelines[(ga, gb)] += 1
        if ga > gb: wins_a += 1
        elif gb > ga: wins_b += 1
        else: draws += 1
    print(f"Promedio simulado: {team_a} {tot_a/n_mc:.2f}  {team_b} {tot_b/n_mc:.2f}  "
          f"(debería acercarse a λ de equipo — es la misma prueba de consistencia de team_lineup_sim, "
          f"ahora sobre el motor jugada-por-jugada completo)")
    print(f"1X2 de esta simulación: {team_a} {100*wins_a/n_mc:.0f}%  empate {100*draws/n_mc:.0f}%  {team_b} {100*wins_b/n_mc:.0f}%")
    print("Marcadores más comunes: " + ", ".join(f"{x}-{y} {100*c/n_mc:.0f}%" for (x, y), c in scorelines.most_common(6)))
    conn.close()
