"""
Punto de entrada principal. Predice el resultado de un partido.

Uso:
  python predict.py --home "Mexico" --away "USA" --lineup mexico_vs_usa

El script:
1. Carga datos históricos del equipo desde data/processed/
2. Carga alineación confirmada desde data/lineups/
3. Ejecuta el modelo de predicción
4. Imprime el análisis completo
"""
import json
import argparse
from pathlib import Path

from models.predictor import TeamSnapshot, predict_match
from models.simulator import simulate_match
from pipelines.update_lineup import load_lineup

PROCESSED_DIR = Path("data/processed")
LINEUPS_DIR   = Path("data/lineups")


def load_team_data(team_name: str) -> dict:
    slug = team_name.lower().replace(" ", "_")
    path = PROCESSED_DIR / f"{slug}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    print(f"  Advertencia: sin datos procesados para {team_name}. Usando defaults.")
    return {}


def build_snapshot(team_name: str, lineup_data: dict, side: str) -> TeamSnapshot:
    team_raw = load_team_data(team_name)
    lineup   = lineup_data.get(side, {})

    return TeamSnapshot(
        name=team_name,
        recent_form=team_raw.get("recent_form", []),
        h2h_record=team_raw.get("h2h", []),
        key_players_available=lineup.get("key_players", []),
        key_players_missing=lineup.get("injuries", []) + lineup.get("suspensions", []),
        formation=lineup.get("formation", "4-3-3"),
        ranking_fifa=team_raw.get("ranking_fifa"),
        goals_scored_avg=team_raw.get("goals_scored_avg", 1.5),
        goals_conceded_avg=team_raw.get("goals_conceded_avg", 1.0),
        possession_avg=team_raw.get("possession_avg", 50.0),
    )


def print_report(home_name: str, away_name: str, result: dict, lineup: dict, sim: dict | None = None):
    print("\n" + "="*60)
    print(f"  ANÁLISIS: {home_name} vs {away_name}")
    print("="*60)

    print(f"\n  Resultado más probable: {result['prediction']}")
    print(f"  Confianza: {result['confidence']}%\n")

    print("  Probabilidades:")
    for outcome, prob in result["probabilities"].items():
        bar = "█" * int(prob / 3)
        print(f"    {outcome:<25} {prob:>5.1f}%  {bar}")

    print("\n  Scores por componente:")
    for team, scores in result["component_scores"].items():
        print(f"\n    {team}:")
        for k, v in scores.items():
            print(f"      {k:<20} {v:.2f}")

    context = lineup.get("context", {})
    if context.get("notes"):
        print(f"\n  Contexto: {context['notes']}")

    home_missing = lineup.get("home", {}).get("injuries", []) + lineup.get("home", {}).get("suspensions", [])
    away_missing = lineup.get("away", {}).get("injuries", []) + lineup.get("away", {}).get("suspensions", [])
    if home_missing:
        print(f"\n  Bajas {home_name}: {', '.join(home_missing)}")
    if away_missing:
        print(f"  Bajas {away_name}: {', '.join(away_missing)}")

    if sim is not None:
        print("\n" + "-"*60)
        print(f"  xG estimados:  {home_name} {sim['xg_home']}  |  {away_name} {sim['xg_away']}")
        print(sim["raw_text"])

    print("\n" + "="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Predicción de partidos — Mundial 2026")
    parser.add_argument("--home",    required=True, help="Selección local")
    parser.add_argument("--away",    required=True, help="Selección visitante")
    parser.add_argument("--lineup",  required=False, help="Slug del archivo de alineación (sin .json)")
    parser.add_argument("--neutral", action="store_true", help="Sede neutral (Mundial = siempre neutral)")
    args = parser.parse_args()

    lineup_slug = args.lineup or f"{args.home.lower().replace(' ', '_')}_vs_{args.away.lower().replace(' ', '_')}"

    try:
        lineup = load_lineup(lineup_slug)
    except FileNotFoundError:
        print(f"Sin alineación confirmada para '{lineup_slug}'. Usando datos base.")
        lineup = {
            "home": {"team": args.home, "key_players": [], "injuries": [], "suspensions": [], "formation": "4-3-3"},
            "away": {"team": args.away, "key_players": [], "injuries": [], "suspensions": [], "formation": "4-3-3"},
            "context": {}
        }

    home_snap = build_snapshot(args.home, lineup, "home")
    away_snap = build_snapshot(args.away, lineup, "away")

    result = predict_match(home_snap, away_snap, neutral_venue=True)

    sim = simulate_match(
        home=home_snap,
        away=away_snap,
        all_teams=[home_snap, away_snap],
    )

    print_report(args.home, args.away, result, lineup, sim=sim)


if __name__ == "__main__":
    main()
