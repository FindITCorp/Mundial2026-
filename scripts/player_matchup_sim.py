"""
player_matchup_sim.py — Simulacion JUGADOR vs DEFENSA (pedido del dueño 01-jul,
ejemplo literal: "lo de Kane, simular cuantas oportunidades de gol tendria, cuales
se convertirian, si la defensa lo permitiria").

Antes esto era IMPOSIBLE: los remates de fifa_match_events tenian 0/1962 con
nombre de jugador (solo `player_fifa_id`, sin resolver). Se descubrio que
`api.fifa.com/api/v3/players/{id}` SI resuelve el nombre -> `fetch_fifa_player_names.py`
cachea el mapeo (tabla `fifa_player_names`, 725 jugadores resueltos). Con eso YA
se puede reconstruir el registro de remates de UN jugador especifico.

MODELO (honesto sobre lo que hay y lo que no):
  1. TASA PERSONAL de remates/90 y conversion (goles/remates) del jugador, de TODOS
     sus remates en el Mundial (fifa_match_events, type 12=remate, 0/41=gol).
  2. AJUSTE POR RIVAL: volumen de remates escalado por cuanto el rival permite
     rematar (shots_total concedidos / promedio del torneo) — un rival que
     concede menos tiros que el promedio reduce el volumen esperado del jugador.
  3. AJUSTE POR PORTERO/DEFENSA DEL RIVAL: la conversion se ajusta por
     `goals_prevented` promedio del rival (negativo = su arquero/defensa
     conceden MAS de lo esperado por xG -> sube la conversion esperada del
     atacante; positivo = achican -> la baja).
  4. MONTE CARLO: remates ~ Poisson(tasa ajustada), cada remate gol ~ Bernoulli
     (conversion ajustada) -> distribucion de goles del jugador en ESE partido.

LIMITACION EXPLICITA (no se inventa el dato): NO hay regates (dribbles) a nivel
jugador en la base — solo agregado de equipo (`match_team_stats.dribbles_won`).
Este simulador NO reporta un numero de regates individuales; si se pide, se
muestra el agregado de equipo con esa etiqueta, nunca como si fuera del jugador.

Uso:
    python scripts/player_matchup_sim.py "Harry Kane" "DR Congo"
    python scripts/player_matchup_sim.py "Harry Kane" "DR Congo" --n 40000
"""
import math
import random
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def player_shot_profile(conn, player_name, exclude_fifa_match_id=None):
    """Remates/90 y conversion de un jugador en el Mundial (fifa_match_events).

    `exclude_fifa_match_id`: para VALIDAR contra un partido ya jugado sin fuga de
    datos (no usar los remates de ESE partido para "predecirlo") — mismo criterio
    leave-one-out aplicado hoy en el prototipo de hazard_model.py."""
    rows = conn.execute(
        "SELECT e.fifa_match_id, e.minute_num, e.type_code FROM fifa_match_events e "
        "JOIN fifa_player_names fp ON fp.fifa_player_id = e.player_fifa_id "
        "WHERE UPPER(fp.name) = UPPER(?) AND e.type_code IN (0, 12, 41)", (player_name,)).fetchall()
    if exclude_fifa_match_id is not None:
        rows = [r for r in rows if r[0] != exclude_fifa_match_id]
    shots = sum(1 for _, _, tc in rows if tc == 12)
    goals = sum(1 for _, _, tc in rows if tc in (0, 41))
    matches = len(set(fmid for fmid, _, _ in rows))
    mins = conn.execute(
        "SELECT SUM(minutes) FROM match_player_stats WHERE UPPER(player_name)=UPPER(?) AND competition='World Cup'",
        (player_name,)).fetchone()[0]
    if exclude_fifa_match_id is not None:
        # aproxima minutos SIN ese partido: resta ~90 si había mins registrados de sobra
        mins = max(90, (mins or matches * 90) - 90) if mins else matches * 90
    if not mins:
        mins = matches * 90 if matches else 90
    shots_per_90 = shots / (mins / 90) if mins else None
    conversion = goals / shots if shots else None
    return {"shots": shots, "goals": goals, "minutes": mins, "matches": matches,
            "shots_per_90": shots_per_90, "conversion": conversion}


def opponent_defense_profile(conn, team_name):
    """Perfil defensivo del RIVAL: tiros concedidos/partido y goals_prevented medio."""
    tid = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
    if not tid:
        return None
    tid = tid[0]
    # Solo Mundial (group/R32) — mezclar amistosos infla/diluye el perfil defensivo
    # con rivales de otro nivel (norma del proyecto: datos del Mundial PRIMARIOS).
    rows = conn.execute(
        "SELECT mts.shots_total, mts.shots_on_target, mts.goals_prevented "
        "FROM wc_matches w JOIN match_team_stats mts ON mts.match_id = w.id "
        "WHERE (w.home_team_id=? OR w.away_team_id=?) AND mts.team_id != ? AND mts.shots_total IS NOT NULL "
        "AND w.stage IN ('group', 'R32')",
        (tid, tid, tid)).fetchall()
    if not rows:
        return None
    n = len(rows)
    shots_allowed = sum(r[0] for r in rows) / n
    sot_allowed = sum(r[1] for r in rows if r[1] is not None) / n
    gp = [r[2] for r in rows if r[2] is not None]
    goals_prevented_avg = sum(gp) / len(gp) if gp else 0.0
    tourn_avg_shots = conn.execute("SELECT AVG(shots_total) FROM match_team_stats").fetchone()[0]
    return {"n": n, "shots_allowed": shots_allowed, "sot_allowed": sot_allowed,
            "goals_prevented_avg": goals_prevented_avg, "tourn_avg_shots": tourn_avg_shots,
            "team_dribbles_conceded": conn.execute(
                "SELECT AVG(dribbles_won) FROM wc_matches w JOIN match_team_stats mts ON mts.match_id=w.id "
                "WHERE (w.home_team_id=? OR w.away_team_id=?) AND mts.team_id != ?", (tid, tid, tid)).fetchone()[0]}


def simulate(conn, player_name, opponent_team, n=20000, seed=42, exclude_fifa_match_id=None):
    prof = player_shot_profile(conn, player_name, exclude_fifa_match_id=exclude_fifa_match_id)
    opp = opponent_defense_profile(conn, opponent_team)
    if not prof["shots_per_90"] or not opp:
        return None

    shot_adj = opp["shots_allowed"] / opp["tourn_avg_shots"] if opp["tourn_avg_shots"] else 1.0
    adj_shots_per_90 = prof["shots_per_90"] * shot_adj

    # goals_prevented negativo = el rival concede MAS de lo esperado por xG -> sube conversion
    per_shot_gp = opp["goals_prevented_avg"] / opp["shots_allowed"] if opp["shots_allowed"] else 0.0
    adj_conversion = max(0.02, min(0.6, prof["conversion"] - per_shot_gp))

    rng = random.Random(seed)
    goals_dist = [0] * 6  # 0,1,2,3,4,5+
    for _ in range(n):
        lam = adj_shots_per_90
        k = 0; p = math.exp(-lam); cum = p; u = rng.random()
        while u > cum and k < 15:
            k += 1; p *= lam / k; cum += p
        shots_this_game = k
        goals = sum(1 for _ in range(shots_this_game) if rng.random() < adj_conversion)
        goals_dist[min(goals, 5)] += 1

    return {"profile": prof, "opponent": opp, "shot_adj": shot_adj,
            "adj_shots_per_90": adj_shots_per_90, "adj_conversion": adj_conversion,
            "goals_dist": [x / n for x in goals_dist], "n": n}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(0)
    player, opponent = args[0], args[1]
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 20000
    excl = int(sys.argv[sys.argv.index("--exclude-match") + 1]) if "--exclude-match" in sys.argv else None

    conn = sqlite3.connect(str(DB))
    r = simulate(conn, player, opponent, n=n, exclude_fifa_match_id=excl)
    if not r:
        print(f"Datos insuficientes para {player} vs {opponent} (¿remates o stats de rival faltantes?)")
        sys.exit(1)

    p, o = r["profile"], r["opponent"]
    print(f"=== {player} vs {opponent} — simulación de oportunidades ===")
    print(f"{player}: {p['shots']} remates / {p['goals']} goles en {p['matches']} partidos del Mundial "
          f"({p['minutes']} min) → {p['shots_per_90']:.2f} remates/90, conversión {p['conversion']*100:.1f}%")
    print(f"{opponent} (defensa, {o['n']} partidos): concede {o['shots_allowed']:.1f} tiros/p "
          f"(promedio torneo {o['tourn_avg_shots']:.1f}) · goals_prevented medio {o['goals_prevented_avg']:+.2f}/p")
    print(f"→ AJUSTE: remates esperados {r['adj_shots_per_90']:.2f}/90 (rival {'concede menos' if r['shot_adj']<1 else 'concede más'} tiros de lo normal, x{r['shot_adj']:.2f})")
    print(f"→ conversión ajustada por calidad defensiva del rival: {r['adj_conversion']*100:.1f}% "
          f"(personal {p['conversion']*100:.1f}% {'+' if r['adj_conversion']>p['conversion'] else ''}{(r['adj_conversion']-p['conversion'])*100:+.1f}pp)")
    exp_goals = sum(i * r["goals_dist"][i] for i in range(6))
    print(f"\nMONTE CARLO ({r['n']} sims) — distribución de goles de {player} en este partido:")
    for i, pct in enumerate(r["goals_dist"]):
        label = f"{i}" if i < 5 else "5+"
        print(f"   {label} goles: {pct*100:.1f}%")
    print(f"   Esperado: {exp_goals:.2f} goles · P(marca ≥1): {(1-r['goals_dist'][0])*100:.1f}%")
    if o.get("team_dribbles_conceded"):
        print(f"\n(Nota: NO hay regates por jugador en la base, solo agregado de equipo. "
              f"{opponent} concede {o['team_dribbles_conceded']:.1f} regates/p de equipo — no es la cifra de {player}.)")
    conn.close()
