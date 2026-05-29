"""
simulate.py — Simulador integral del Mundial 2026.

Junta TODOS los subsistemas en un único punto de entrada:

  Escenario completo de un partido (marcador, goleadores, córners, tarjetas,
  tiros, penaltis, árbitro asignado, posesión, mercados):
      python simulate.py --match "Brazil" "Argentina"
      python simulate.py --match "Spain" "France" --stage final --sims 30000

  Simulación Monte Carlo del torneo entero (P de campeón, semis, etc.):
      python simulate.py --tournament
      python simulate.py --tournament --sims 10000

  Simular un grupo concreto:
      python simulate.py --group F

  Utilidades:
      python simulate.py --referees          # plantel arbitral
      python simulate.py --scorers "Brazil"  # tabla de goleadores
      python simulate.py --draw              # ver el sorteo de grupos
"""
import sys
import argparse
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "mundial2026.db"


def _tid(name: str):
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT id FROM teams WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    conn.close()
    return row[0] if row else None


def cmd_match(args):
    from models.full_match_sim import simulate_full_match, format_full_match
    h, a = _tid(args.match[0]), _tid(args.match[1])
    if not h or not a:
        print(f"  ⚠ Equipo no encontrado: {args.match[0] if not h else args.match[1]}")
        print("  Usa el nombre en inglés (ej: Brazil, Germany, Spain).")
        return
    r = simulate_full_match(
        h, a, neutral=not args.home_advantage, stage=args.stage,
        home_absence=args.home_absence, away_absence=args.away_absence,
        n_sims=args.sims, db_path=DB_PATH,
        home_exclude=args.home_out, away_exclude=args.away_out,
        with_subs=not args.no_subs)
    print(format_full_match(r))


def cmd_tournament(args):
    from models.tournament import TournamentSimulator, format_tournament
    print(f"\n  Simulando {args.sims:,} torneos completos del Mundial 2026...")
    sim = TournamentSimulator(db_path=DB_PATH, seed=args.seed)
    res = sim.run(n_sims=args.sims, progress=True)
    print(format_tournament(res, top=args.top))
    # Resumen de favoritos
    champ = res["teams"][0]
    print(f"\n  🏆 Favorito: {champ['team']} ({champ['p_champion']}% de probabilidad)")
    print(f"  📊 Top 4 candidatos: " +
          ", ".join(f"{t['team']} {t['p_champion']}%" for t in res["teams"][:4]))


def cmd_group(args):
    from models.tournament import TournamentSimulator
    from collections import defaultdict
    g = args.group.upper()
    sim = TournamentSimulator(db_path=DB_PATH, seed=args.seed)
    if g not in sim.groups:
        print(f"  ⚠ Grupo '{g}' no existe. Grupos: {', '.join(sorted(sim.groups))}")
        return
    ids = sim.groups[g]
    print(f"\n{'='*58}")
    print(f"  GRUPO {g} — {args.sims:,} simulaciones")
    print(f"{'='*58}")
    names = {t: sim.name[t] for t in ids}
    for t in ids:
        s = sim.strength[t]
        print(f"    {sim.name[t]:<18} Elo {s['elo']:.0f}")
    # Monte Carlo del grupo
    pos = defaultdict(lambda: [0, 0, 0, 0])   # team -> [1º,2º,3º,4º]
    pts_sum = defaultdict(float)
    for _ in range(args.sims):
        table = sim._sim_group(ids)
        for rank, row in enumerate(table):
            pos[row["id"]][rank] += 1
            pts_sum[row["id"]] += row["pts"]
    print(f"\n  {'Equipo':<18}{'1º':>7}{'2º':>7}{'3º':>7}{'4º':>7}{'PtsProm':>9}{'Avanza':>8}")
    print(f"  {'-'*56}")
    ranked = sorted(ids, key=lambda t: -(pos[t][0] + pos[t][1]))
    for t in ranked:
        p = [x / args.sims * 100 for x in pos[t]]
        adv = p[0] + p[1]   # top-2 directo (sin contar mejor tercero)
        print(f"  {sim.name[t]:<18}{p[0]:>6.1f}%{p[1]:>6.1f}%{p[2]:>6.1f}%{p[3]:>6.1f}%"
              f"{pts_sum[t]/args.sims:>9.2f}{adv:>7.1f}%")


def cmd_referees(args):
    from models.referee_model import REFEREES
    print(f"\n{'='*78}")
    print(f"  PLANTEL ARBITRAL ÉLITE WC2026 ({len(REFEREES)})")
    print(f"{'='*78}")
    print(f"  {'Árbitro':<22}{'País':<14}{'Conf':<10}{'YC/p':>6}{'Pen':>6}{'Estrictez':>10}")
    print(f"  {'-'*74}")
    for r in sorted(REFEREES.values(), key=lambda x: -x.cards_per_game):
        print(f"  {r.name:<22}{r.country:<14}{r.confederation:<10}"
              f"{r.cards_per_game:>6.1f}{r.penalty_rate:>6.2f}{r.strictness:>9.2f}")


def cmd_scorers(args):
    from models.goal_scorer import expected_scorer_table
    t = _tid(args.scorers)
    if not t:
        print(f"  ⚠ Equipo no encontrado: {args.scorers}")
        return
    print(f"\n{'='*58}")
    print(f"  GOLEADORES ESPERADOS — {args.scorers}")
    print(f"{'='*58}")
    print(f"  {'Jugador':<24}{'Pos':<5}{'%goles':>8}{'P(marca)':>10}  Pen")
    print(f"  {'-'*54}")
    for s in expected_scorer_table(t, lam=args.lam):
        pen = "⚽PK" if s["pen_taker"] else ""
        print(f"  {s['name'][:23]:<24}{s['position']:<5}"
              f"{s['goals_share']:>7.1f}%{s['prob_anytime']:>9.1f}%  {pen}")


def cmd_profile(args):
    from models.team_stats_analyzer import get_team_profile, format_team_profile
    t = _tid(args.profile)
    if not t:
        print(f"  ⚠ Equipo no encontrado: {args.profile}")
        return
    profile = get_team_profile(t, DB_PATH)
    print(format_team_profile(profile, verbose=True))


def cmd_draw(args):
    from models.tournament import TournamentSimulator, GROUPS
    sim = TournamentSimulator(db_path=DB_PATH)
    print(f"\n{'='*52}")
    print(f"  SORTEO MUNDIAL 2026 — 12 grupos de 4")
    print(f"{'='*52}")
    for g in GROUPS:
        if g not in sim.groups:
            continue
        teams = sorted(sim.groups[g], key=lambda t: -sim.strength[t]["elo"])
        line = ", ".join(sim.name[t] for t in teams)
        print(f"  {g}: {line}")


def main():
    p = argparse.ArgumentParser(
        description="Simulador integral del Mundial 2026",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--match", nargs=2, metavar=("LOCAL", "VISITA"),
                   help="Escenario completo de un partido")
    p.add_argument("--tournament", action="store_true", help="Simular el torneo completo")
    p.add_argument("--group", help="Simular un grupo (A-L)")
    p.add_argument("--referees", action="store_true", help="Listar árbitros")
    p.add_argument("--scorers", metavar="EQUIPO", help="Tabla de goleadores de un equipo")
    p.add_argument("--draw", action="store_true", help="Ver el sorteo de grupos")
    p.add_argument("--profile", metavar="EQUIPO",
                   help="Perfil estadístico histórico completo de un equipo")
    p.add_argument("--stage", default="group",
                   choices=["group", "round_of_16", "quarter_final", "semi_final", "final"],
                   help="Etapa del partido (afecta árbitro)")
    p.add_argument("--sims", type=int, default=20000, help="Nº de simulaciones")
    p.add_argument("--top", type=int, default=24, help="Equipos a mostrar (torneo)")
    p.add_argument("--seed", type=int, default=2026, help="Semilla del sorteo")
    p.add_argument("--lam", type=float, default=1.6, help="λ para tabla de goleadores")
    p.add_argument("--home-advantage", action="store_true",
                   help="Aplicar localía (default: sede neutral)")
    p.add_argument("--home-absence", type=float, default=0.0, help="Penalización bajas local 0-0.3")
    p.add_argument("--away-absence", type=float, default=0.0, help="Penalización bajas visita 0-0.3")
    p.add_argument("--home-out", nargs="*", default=None,
                   help="Jugadores ausentes del local (ej: --home-out Neymar)")
    p.add_argument("--away-out", nargs="*", default=None,
                   help="Jugadores ausentes de la visita (ej: --away-out Carrasquilla)")
    p.add_argument("--no-subs", action="store_true",
                   help="Desactivar simulación de cambios (todos juegan 90 min)")

    args = p.parse_args()

    if not DB_PATH.exists():
        print("  [!] Base de datos no encontrada.")
        sys.exit(1)

    if args.match:          cmd_match(args)
    elif args.tournament:   cmd_tournament(args)
    elif args.group:        cmd_group(args)
    elif args.referees:     cmd_referees(args)
    elif args.scorers:      cmd_scorers(args)
    elif args.draw:         cmd_draw(args)
    elif args.profile:      cmd_profile(args)
    else:                   p.print_help()


if __name__ == "__main__":
    main()
