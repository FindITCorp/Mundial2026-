"""
Actualiza la alineación confirmada de un partido antes de correr la predicción.
Uso: python pipelines/update_lineup.py --match "Mexico vs USA" --home "Mexico" --away "USA"

La alineación se guarda en data/lineups/<match_id>.json para que predict.py la use.
"""
import json
import argparse
from pathlib import Path
from datetime import datetime

LINEUPS_DIR = Path("data/lineups")
LINEUPS_DIR.mkdir(parents=True, exist_ok=True)


LINEUP_TEMPLATE = {
    "match": "",
    "date": "",
    "updated_at": "",
    "home": {
        "team": "",
        "formation": "4-3-3",
        "starters": [],    # lista de nombres
        "injuries": [],
        "suspensions": [],
        "key_players": []
    },
    "away": {
        "team": "",
        "formation": "4-3-3",
        "starters": [],
        "injuries": [],
        "suspensions": [],
        "key_players": []
    },
    "context": {
        "venue": "",
        "weather": "",
        "notes": ""        # info relevante: presión, rivalidad, etc.
    }
}


def create_lineup_file(match: str, home: str, away: str):
    slug = match.lower().replace(" ", "_").replace("/", "_vs_")
    path = LINEUPS_DIR / f"{slug}.json"

    data = LINEUP_TEMPLATE.copy()
    data["match"] = match
    data["date"] = datetime.now().strftime("%Y-%m-%d")
    data["updated_at"] = datetime.now().isoformat()
    data["home"]["team"] = home
    data["away"]["team"] = away

    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Archivo de alineación creado: {path}")
    print("Edítalo con la alineación confirmada antes de correr predict.py")
    return path


def load_lineup(match_slug: str) -> dict:
    path = LINEUPS_DIR / f"{match_slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"No hay alineación para: {match_slug}")
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", required=True, help="Nombre del partido: 'Mexico vs USA'")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    args = parser.parse_args()
    create_lineup_file(args.match, args.home, args.away)
