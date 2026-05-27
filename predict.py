"""
predict.py — Master prediction script for FIFA World Cup 2026.

Usage:
  python predict.py --home "Panama" --away "Croatia"
  python predict.py --home "Brazil" --away "Argentina" --neutral
  python predict.py --home "Mexico" --away "USA" --lineup mexico_vs_usa
  python predict.py --list-teams
  python predict.py --group A
  python predict.py --schedule
"""
import json
import argparse
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models.predictor import predict_match
from pipelines.update_lineup import load_lineup
from models.lineup_estimator import estimate_lineup, print_lineup

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "data" / "mundial2026.db"
LINEUPS_DIR = BASE_DIR / "data" / "lineups"


def check_db():
    """Ensure DB exists and is populated."""
    if not DB_PATH.exists():
        print("\n[!] Base de datos no encontrada.")
        print("    Ejecuta primero: python scripts/setup_db.py\n")
        return False

    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    conn.close()

    if count == 0:
        print("\n[!] Base de datos vacia. Ejecuta: python scripts/setup_db.py --reset\n")
        return False
    return True


def list_teams():
    """List all 48 WC2026 teams from DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    teams = conn.execute("""
        SELECT name, confederation, wc_group, fifa_ranking, formation
        FROM teams ORDER BY confederation, fifa_ranking
    """).fetchall()
    conn.close()

    print(f"\n{'='*70}")
    print(f"  EQUIPOS FIFA MUNDIAL 2026 -- {len(teams)} selecciones")
    print(f"{'='*70}")

    conf_prev = ""
    for t in teams:
        if t["confederation"] != conf_prev:
            print(f"\n  [{t['confederation']}]")
            conf_prev = t["confederation"]
        print(f"    {t['name']:<22} Grupo {t['wc_group'] or '?':>3}  "
              f"Ranking #{t['fifa_ranking'] or '?':<4}  {t['formation']}")
    print()


def show_schedule(group=None):
    """Show WC2026 match schedule."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT id, date, time, home_team_name, away_team_name, venue, city,
               wc_group, stage, score_home, score_away, played
        FROM wc_matches
    """
    params = []
    if group:
        query += " WHERE wc_group=?"
        params.append(group.upper())
    query += " ORDER BY date, time LIMIT 80"

    matches = conn.execute(query, params).fetchall()
    conn.close()

    title = "CALENDARIO MUNDIAL 2026" + (f" -- GRUPO {group.upper()}" if group else "")
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

    prev_date = ""
    for m in matches:
        if m["date"] != prev_date:
            print(f"\n  {m['date']}")
            prev_date = m["date"]

        result_str = ""
        if m["played"]:
            result_str = f" [{m['score_home']}-{m['score_away']}]"

        stage_label = {
            "group": "Grupo",
            "round_of_32": "Octavos",
            "round_of_16": "Octavos",
            "quarter_final": "Cuartos",
            "semi_final": "Semis",
            "third_place": "3er Lugar",
            "final": "FINAL",
        }.get(m["stage"], m["stage"] or "")

        print(f"    [{m['id']:3d}] {m['time']} | {m['home_team_name']:<20} vs "
              f"{m['away_team_name']:<20} | {m['city']:<15}{result_str}  ({stage_label})")
    print()


def print_full_report(result, lineup_data=None):
    """Print the comprehensive match analysis report."""
    home = result["home"]
    away = result["away"]
    sep = "=" * 65

    venue = result.get("venue", "")
    print(f"\n{sep}")
    print(f"  ANALISIS PREDICTIVO -- MUNDIAL 2026")
    print(f"  {home.upper()} vs {away.upper()}")
    if venue:
        print(f"  Sede: {venue}")
    print(f"{sep}")

    # Team info
    ti = result.get("team_info", {})
    home_info = ti.get(home, {})
    away_info = ti.get(away, {})

    print(f"\n  {home}")
    print(f"    FIFA Ranking: #{home_info.get('fifa_ranking', 'N/A')}")
    print(f"    Grupo: {home_info.get('group', 'N/A')}  |  "
          f"Confederacion: {home_info.get('confederation', 'N/A')}")
    print(f"    Esquema: {home_info.get('formation', '?')}  |  "
          f"Estilo: {home_info.get('tactical_style', '?').title()}")

    print(f"\n  {away}")
    print(f"    FIFA Ranking: #{away_info.get('fifa_ranking', 'N/A')}")
    print(f"    Grupo: {away_info.get('group', 'N/A')}  |  "
          f"Confederacion: {away_info.get('confederation', 'N/A')}")
    print(f"    Esquema: {away_info.get('formation', '?')}  |  "
          f"Estilo: {away_info.get('tactical_style', '?').title()}")

    # Main prediction — exact result, no percentages
    conf = result.get("confidence", {})
    scoreline = result.get("predicted_scoreline", "?-?")
    try:
        sh, sa = scoreline.split("-")
        exact_result = f"{home} {sh} – {sa} {away}"
    except Exception:
        exact_result = f"{home} vs {away}  ({scoreline})"

    print(f"\n{'═'*65}")
    print(f"  RESULTADO PRONOSTICADO  [{conf.get('level', '?')} confianza]")
    print(f"  ➤  {exact_result}")
    print(f"{'═'*65}")

    # Line analysis
    print(f"\n{'-'*65}")
    print(f"  ANALISIS LINEA POR LINEA:")
    print(f"  {'Linea':<8} {home[:20]:>20}    {away[:20]:<20}  Ventaja")
    print(f"  {'-'*60}")
    la = result.get("line_analysis", {})
    for line in ["GK", "DEF", "MID", "FWD", "Overall"]:
        if line in la:
            d = la[line]
            ha = d.get(home, 0)
            aa = d.get(away, 0)
            adv = d.get("advantage", {})
            adv_team = adv.get("team", "Equal")
            adv_label = adv.get("margin_label", "")
            if adv_team == "Equal":
                indicator = "  ~"
            elif adv_team == home:
                indicator = " <-"
            else:
                indicator = " ->"

            line_label = "Global" if line == "Overall" else line
            print(f"  {line_label:<8} {ha:>20.2f}    {aa:<20.2f}  "
                  f"{indicator} {adv_team[:15]} ({adv_label})")

    # Squad ratings -- top players
    print(f"\n{'-'*65}")
    print(f"  JUGADORES CLAVE:")
    sq = result.get("squad_ratings", {})

    for team_name in [home, away]:
        team_sq = sq.get(team_name, {})
        top = team_sq.get("top_players", {})
        print(f"\n  [{team_name}]")
        for pos in ["GK", "DEF", "MID", "FWD"]:
            players = top.get(pos, [])
            for p in players[:2]:
                doubt = "  [BAJA?]" if p.get("availability") == "doubt" else ""
                print(f"    {pos}  {p['name']:<28} {p['rating']:>4.1f}  {p.get('club', '')}{doubt}")

    # Key matchups
    matchups = result.get("key_matchups", [])
    if matchups:
        print(f"\n{'-'*65}")
        print(f"  DUELOS CLAVE:")
        for m in matchups[:4]:
            adv = m.get("advantage", "?")
            print(f"    {m['type']}")
            print(f"      {m['player_a']:<28} {m['rating_a']:>4.1f}")
            print(f"      {m['player_b']:<28} {m['rating_b']:>4.1f}")
            print(f"      Ventaja: {adv} (margen: {m.get('margin', 0):.2f})")
            print()

    # Form analysis
    print(f"{'-'*65}")
    print(f"  FORMA RECIENTE:")
    form = result.get("form_analysis", {})
    for team_name in [home, away]:
        team_form = form.get(team_name, {})
        score = team_form.get("score", 50)
        matches = team_form.get("last_10", [])
        results_str = " ".join(
            f"[{m['result']}]" for m in matches[:5]
        )
        form_label = "Excelente" if score >= 80 else "Buena" if score >= 60 else "Regular" if score >= 40 else "Baja"
        print(f"    {team_name:<22} Forma: {form_label:<10} ({score:.0f}/100)  {results_str}")
        for m in matches[:5]:
            comp_short = m['comp'][:30] if m.get('comp') else ''
            print(f"      vs {m['opponent']:<20} {m['result']}  {m['score']:<6}  {comp_short}")

    # H2H
    print(f"\n{'-'*65}")
    h2h = result.get("h2h", {})
    h2h_src = h2h.get("source", "none")
    print(f"  HISTORIAL H2H:")
    if h2h_src == "direct":
        summ = h2h.get("summary", {})
        total = summ.get("total", 0)
        draws = summ.get("draws", 0)
        home_wins = summ.get(home, {}).get("wins", 0)
        away_wins = summ.get(away, {}).get("wins", 0)
        print(f"    {total} partidos directos | {home}: {home_wins}V  Empates: {draws}  {away}: {away_wins}V")
        for m in h2h.get("matches", [])[:5]:
            if m.get("result") and m.get("date"):
                print(f"    {m['date']}  {m.get('competition', '')}  "
                      f"GF:{m.get('goals_for',0)}-GA:{m.get('goals_against',0)}  [{m['result']}]")
    elif h2h_src == "proxy":
        proxy = h2h.get("proxy", {})
        if proxy:
            print(f"    Sin H2H directo. Proxy via equipos similares:")
            print(f"    Similares usados: {', '.join(proxy.get('similar_teams_used', []))}")
            pw = proxy.get('win_pct', 0)
            pd = proxy.get('draw_pct', 0)
            pl = proxy.get('loss_pct', 0)
            if pw >= pd and pw >= pl:
                proxy_result = f"Ventaja {home}"
            elif pl >= pw and pl >= pd:
                proxy_result = f"Ventaja {away}"
            else:
                proxy_result = "Equilibrado"
            print(f"    Tendencia histórica similar: {proxy_result}")
    else:
        print(f"    Sin datos H2H disponibles.")

    # WC History
    print(f"\n{'-'*65}")
    print(f"  HISTORIAL EN MUNDIALES:")
    wch = result.get("wc_history", {})
    for team_name in [home, away]:
        team_wch = wch.get(team_name, {})
        score = team_wch.get("score", 0)
        editions = team_wch.get("editions", [])
        print(f"\n  {team_name} (score: {score:.2f}):")
        for ed in editions[:3]:
            rnd = ed.get("round_reached", "?")
            if rnd and rnd != "Did not qualify":
                print(f"    {ed['year']}: {rnd:<22} "
                      f"GF:{ed.get('goals_scored',0)} GA:{ed.get('goals_conceded',0)} "
                      f"PJ:{ed.get('matches_played',0)}")
            elif rnd == "Did not qualify":
                print(f"    {ed['year']}: No clasifico")

    # Component breakdown
    print(f"\n{'-'*65}")
    print(f"  SCORES POR COMPONENTE (0-1):")
    comp = result.get("component_scores", {})
    labels = {
        "players": "Calidad jugadores",
        "form": "Forma reciente",
        "h2h": "H2H",
        "ranking": "Ranking FIFA",
        "wc_history": "Historial WC",
        "composite": "COMPOSITE",
    }
    print(f"  {'Componente':<22} {home[:18]:>18}  {away[:18]:<18}")
    print(f"  {'-'*60}")
    for k, label in labels.items():
        hv = comp.get(home, {}).get(k, 0)
        av = comp.get(away, {}).get(k, 0)
        winner = "<" if hv > av else (">" if av > hv else "=")
        print(f"  {label:<22} {hv:>18.3f}  {av:<18.3f}  {winner}")

    # DNA tactical identity & matchup analysis
    home_dna_txt = result.get("home_matchup_analysis", "")
    away_dna_txt = result.get("away_matchup_analysis", "")
    if home_dna_txt or away_dna_txt:
        print(f"\n{'-'*65}")
        print(f"  ANÁLISIS DE IDENTIDAD TÁCTICA (DNA):")
        if home_dna_txt:
            print(home_dna_txt)
        if away_dna_txt:
            print(away_dna_txt)

    # Scout reports
    try:
        from models.team_scout import format_scouting_summary
        print(f"\n{'-'*65}")
        print(f"  INFORME DE SCOUTING:")
        print(format_scouting_summary(home))
        print(format_scouting_summary(away))
    except Exception:
        pass

    # Similar teams context
    sim = result.get("similar_teams", {})
    if sim.get(home) or sim.get(away):
        print(f"\n{'-'*65}")
        print(f"  EQUIPOS SIMILARES (contexto):")
        for team_name in [home, away]:
            sim_list = sim.get(team_name, [])
            if sim_list:
                print(f"    {team_name}: {', '.join(sim_list[:3])}")

    # Missing players (from lineup file)
    if lineup_data:
        home_miss = (lineup_data.get("home", {}).get("injuries", []) +
                     lineup_data.get("home", {}).get("suspensions", []))
        away_miss = (lineup_data.get("away", {}).get("injuries", []) +
                     lineup_data.get("away", {}).get("suspensions", []))
        if home_miss or away_miss:
            print(f"\n{'-'*65}")
            print(f"  BAJAS CONFIRMADAS:")
            if home_miss:
                print(f"    {home}: {', '.join(home_miss)}")
            if away_miss:
                print(f"    {away}: {', '.join(away_miss)}")

    # External prediction signal
    try:
        from pipelines.fetch_predictions import get_external_prediction
        match_date = result.get("match_date", datetime.now().strftime("%Y-%m-%d"))
        ext = get_external_prediction(home, away, match_date)
        if ext:
            print(f"\n{'-'*65}")
            print(f"  SEÑAL EXTERNA (Football Prediction API):")
            print(f"    Señal externa: {ext.get('prediction', 'N/A')}")
    except Exception:
        pass

    print(f"\n{sep}")
    import datetime as dt
    print(f"  Generado: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{sep}\n")


def _get_confirmed_lineup_from_db(team_name: str, match_id: int = None) -> list:
    """
    Check match_lineups table for a confirmed lineup.
    Returns list of starter dicts or empty list if not found.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find team_id
    team_row = conn.execute(
        "SELECT id FROM teams WHERE name=?", (team_name,)
    ).fetchone()

    if not team_row:
        conn.close()
        return []

    team_id = team_row["id"]

    query = """
        SELECT ml.player_id, ml.position, ml.starter,
               p.name, p.club, p.caps
        FROM match_lineups ml
        JOIN players p ON p.id = ml.player_id
        WHERE ml.team_id=? AND ml.starter=1
    """
    params = [team_id]

    if match_id:
        query += " AND ml.match_id=?"
        params.append(match_id)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _show_lineup_estimate(home_team: str, away_team: str) -> None:
    """
    Display lineup info for both teams:
    - CONFIRMADA if match_lineups table has data
    - ESTIMADA (basada en historial del DT) if estimated
    """
    print(f"\n{'='*65}")
    print(f"  ALINEACIONES")
    print(f"{'='*65}")

    for team_name in [home_team, away_team]:
        # 1. Check match_lineups table for confirmed lineup
        confirmed = _get_confirmed_lineup_from_db(team_name)

        if confirmed:
            print(f"\n  [{team_name}] ALINEACION CONFIRMADA")
            print(f"  {'#':<3} {'Nombre':<28} {'POS':<5} {'Club'}")
            print(f"  {'-'*65}")
            for i, p in enumerate(confirmed[:11], 1):
                print(f"  {i:<3} {p['name']:<28} {p['position'] or '?':<5} {p.get('club','')}")
        else:
            # 2. Estimate lineup using lineup_estimator
            lineup = estimate_lineup(team_name)
            print_lineup(lineup)
            if lineup.get("estimated"):
                print(f"  [Nota: Alineacion ESTIMADA basada en historial del DT]")


def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Prediccion -- FIFA Mundial 2026",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python predict.py --home "Panama" --away "Croatia"
  python predict.py --home "Brazil" --away "Argentina"
  python predict.py --home "Mexico" --away "USA" --lineup mexico_vs_usa
  python predict.py --list-teams
  python predict.py --group D
  python predict.py --schedule
        """
    )
    parser.add_argument("--home", help="Equipo local")
    parser.add_argument("--away", help="Equipo visitante")
    parser.add_argument("--lineup", help="Slug del archivo de alineacion (sin .json)")
    parser.add_argument("--no-lineup", action="store_true",
                        help="Omitir visualizacion de alineaciones")
    parser.add_argument("--neutral", action="store_true", default=True,
                        help="Sede neutral (default en Mundial)")
    parser.add_argument("--no-neutral", dest="neutral", action="store_false",
                        help="Sede no neutral")
    parser.add_argument("--venue", default="",
                        help="Ciudad sede del partido (ej: 'Mexico City', 'New York', 'Toronto')")
    parser.add_argument("--list-teams", action="store_true",
                        help="Listar todos los equipos clasificados")
    parser.add_argument("--group", help="Ver partidos de un grupo: A-L")
    parser.add_argument("--schedule", action="store_true",
                        help="Ver calendario completo")
    parser.add_argument("--json", action="store_true",
                        help="Output en formato JSON")
    parser.add_argument("--expert", action="store_true",
                        help="Analisis estilo experto deportivo (resultado concreto, sin probabilidades)")

    args = parser.parse_args()

    # Check DB
    if not check_db():
        sys.exit(1)

    # Subcommands
    if args.list_teams:
        list_teams()
        return

    if args.schedule:
        show_schedule()
        return

    if args.group:
        show_schedule(group=args.group)
        return

    if not args.home or not args.away:
        parser.print_help()
        sys.exit(0)

    # Expert analysis mode — concrete result, no probabilities
    if args.expert:
        from models.expert_analysis import analyze_match
        print(analyze_match(args.home, args.away, str(DB_PATH)))
        return

    # Load lineup if provided
    lineup_data = None
    if args.lineup:
        try:
            lineup_data = load_lineup(args.lineup)
            print(f"  Alineacion CONFIRMADA cargada: {args.lineup}")
        except FileNotFoundError:
            print(f"  Sin alineacion confirmada para '{args.lineup}'. Buscando en DB...")

    # If no lineup provided (and not suppressed), check match_lineups table then estimate
    if not lineup_data and not args.no_lineup:
        _show_lineup_estimate(args.home, args.away)

    # Run prediction
    print(f"\nCalculando prediccion: {args.home} vs {args.away}...")

    # Resolve venue from schedule if not provided
    venue = args.venue or ""
    if not venue and args.home and args.away:
        try:
            conn = sqlite3.connect(DB_PATH)
            m = conn.execute("""
                SELECT city FROM wc_matches
                WHERE (home_team_name=? AND away_team_name=?)
                   OR (home_team_name=? AND away_team_name=?)
                LIMIT 1
            """, (args.home, args.away, args.away, args.home)).fetchone()
            if m:
                venue = m[0] or ""
            conn.close()
        except Exception:
            pass

    if venue:
        print(f"  Sede: {venue}")

    try:
        result = predict_match(
            home_name=args.home,
            away_name=args.away,
            neutral=args.neutral,
            venue=venue,
        )
    except ValueError as e:
        print(f"\nERROR: {e}")
        print("Usa --list-teams para ver los nombres exactos de los equipos.")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_full_report(result, lineup_data)


if __name__ == "__main__":
    main()
