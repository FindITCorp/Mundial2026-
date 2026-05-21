"""
team_similarity.py — Encuentra equipos similares para proxy H2H.

Cuando no hay historial directo entre dos equipos, usamos equipos similares
y su historial como referencia.

Similitud basada en:
  - goals scored avg
  - goals conceded avg
  - possession %
  - pressing intensity
  - defensive line height
  - tactical style
  - confederation (bonus si misma confederacion)
  - FIFA ranking proximity
"""
import math
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Tactical style similarity scores (0-1)
STYLE_SIMILARITY = {
    ("attacking",  "attacking"):  1.0,
    ("attacking",  "possession"): 0.8,
    ("attacking",  "counter"):    0.5,
    ("attacking",  "balanced"):   0.6,
    ("attacking",  "physical"):   0.5,
    ("attacking",  "disciplined"):0.4,
    ("attacking",  "defensive"):  0.2,
    ("possession", "possession"): 1.0,
    ("possession", "attacking"):  0.8,
    ("possession", "balanced"):   0.7,
    ("possession", "counter"):    0.5,
    ("possession", "physical"):   0.4,
    ("possession", "disciplined"):0.5,
    ("possession", "defensive"):  0.3,
    ("counter",    "counter"):    1.0,
    ("counter",    "disciplined"):0.7,
    ("counter",    "defensive"):  0.6,
    ("counter",    "balanced"):   0.6,
    ("counter",    "physical"):   0.5,
    ("counter",    "attacking"):  0.5,
    ("counter",    "possession"): 0.5,
    ("balanced",   "balanced"):   1.0,
    ("balanced",   "possession"): 0.7,
    ("balanced",   "counter"):    0.6,
    ("balanced",   "physical"):   0.6,
    ("balanced",   "attacking"):  0.6,
    ("balanced",   "disciplined"):0.5,
    ("balanced",   "defensive"):  0.4,
    ("physical",   "physical"):   1.0,
    ("physical",   "attacking"):  0.5,
    ("physical",   "balanced"):   0.6,
    ("physical",   "counter"):    0.5,
    ("physical",   "disciplined"):0.6,
    ("physical",   "possession"): 0.4,
    ("physical",   "defensive"):  0.5,
    ("disciplined","disciplined"):1.0,
    ("disciplined","counter"):    0.7,
    ("disciplined","defensive"):  0.7,
    ("disciplined","balanced"):   0.5,
    ("disciplined","physical"):   0.6,
    ("disciplined","possession"): 0.5,
    ("disciplined","attacking"):  0.4,
    ("defensive",  "defensive"):  1.0,
    ("defensive",  "disciplined"):0.7,
    ("defensive",  "counter"):    0.6,
    ("defensive",  "balanced"):   0.4,
    ("defensive",  "physical"):   0.5,
    ("defensive",  "possession"): 0.3,
    ("defensive",  "attacking"):  0.2,
}

DEFENSIVE_LINE_SIMILARITY = {
    ("high",   "high"):   1.0,
    ("high",   "medium"): 0.6,
    ("high",   "low"):    0.2,
    ("medium", "high"):   0.6,
    ("medium", "medium"): 1.0,
    ("medium", "low"):    0.6,
    ("low",    "high"):   0.2,
    ("low",    "medium"): 0.6,
    ("low",    "low"):    1.0,
}


def style_sim(a: str, b: str) -> float:
    a, b = (a or "balanced").lower(), (b or "balanced").lower()
    return STYLE_SIMILARITY.get((a, b), STYLE_SIMILARITY.get((b, a), 0.5))


def dline_sim(a: str, b: str) -> float:
    a, b = (a or "medium").lower(), (b or "medium").lower()
    return DEFENSIVE_LINE_SIMILARITY.get((a, b), 0.5)


def normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to [0, 1]."""
    r = max_val - min_val
    if r == 0:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / r))


def team_similarity_score(team_a: dict, team_b: dict) -> float:
    """
    Compute similarity between two teams (0.0 = completely different, 1.0 = identical).

    team_a, team_b: dicts with keys:
      goals_scored_avg, goals_conceded_avg, possession_avg,
      pressing_intensity, defensive_line, tactical_style,
      confederation, fifa_ranking
    """
    scores = []
    weights = []

    # 1. Goals scored avg (similar attacking output)
    gs_diff = abs(team_a.get("goals_scored_avg", 1.5) - team_b.get("goals_scored_avg", 1.5))
    gs_sim = max(0.0, 1.0 - gs_diff / 3.0)  # 3 goals diff = 0 similarity
    scores.append(gs_sim)
    weights.append(0.20)

    # 2. Goals conceded avg (similar defensive solidity)
    gc_diff = abs(team_a.get("goals_conceded_avg", 1.2) - team_b.get("goals_conceded_avg", 1.2))
    gc_sim = max(0.0, 1.0 - gc_diff / 3.0)
    scores.append(gc_sim)
    weights.append(0.18)

    # 3. Possession avg
    poss_diff = abs(team_a.get("possession_avg", 50.0) - team_b.get("possession_avg", 50.0))
    poss_sim = max(0.0, 1.0 - poss_diff / 30.0)  # 30pp diff = 0
    scores.append(poss_sim)
    weights.append(0.15)

    # 4. Pressing intensity (1-10 scale)
    press_diff = abs(team_a.get("pressing_intensity", 5.0) - team_b.get("pressing_intensity", 5.0))
    press_sim = max(0.0, 1.0 - press_diff / 9.0)
    scores.append(press_sim)
    weights.append(0.12)

    # 5. Defensive line
    dl_sim = dline_sim(
        team_a.get("defensive_line", "medium"),
        team_b.get("defensive_line", "medium")
    )
    scores.append(dl_sim)
    weights.append(0.10)

    # 6. Tactical style
    t_sim = style_sim(
        team_a.get("tactical_style", "balanced"),
        team_b.get("tactical_style", "balanced")
    )
    scores.append(t_sim)
    weights.append(0.12)

    # 7. Confederation bonus
    same_conf = team_a.get("confederation") == team_b.get("confederation")
    scores.append(1.0 if same_conf else 0.0)
    weights.append(0.05)

    # 8. Ranking proximity
    rank_a = team_a.get("fifa_ranking", 50) or 50
    rank_b = team_b.get("fifa_ranking", 50) or 50
    rank_diff = abs(rank_a - rank_b)
    rank_sim = max(0.0, 1.0 - rank_diff / 80.0)
    scores.append(rank_sim)
    weights.append(0.08)

    total = sum(w * s for w, s in zip(weights, scores))
    return round(total, 4)


def find_similar_teams(
    target_team: str,
    db_path: Optional[Path] = None,
    top_n: int = 5,
    exclude: list = None
) -> list[dict]:
    """
    Find the top N teams most similar to target_team.

    Returns list of dicts:
      {team_name, similarity_score, goals_scored_avg, goals_conceded_avg, ...}
    """
    db_path = db_path or DB_PATH
    exclude = exclude or []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    target = conn.execute(
        "SELECT * FROM teams WHERE name=?", (target_team,)
    ).fetchone()
    if not target:
        # Try slug
        target = conn.execute(
            "SELECT * FROM teams WHERE slug=?",
            (target_team.lower().replace(" ", "_"),)
        ).fetchone()

    if not target:
        conn.close()
        return []

    target_dict = dict(target)
    all_teams = conn.execute(
        "SELECT * FROM teams WHERE name != ?", (target_team,)
    ).fetchall()

    similarities = []
    for t in all_teams:
        if t["name"] in exclude:
            continue
        sim = team_similarity_score(target_dict, dict(t))
        similarities.append({
            "team_name": t["name"],
            "team_id": t["id"],
            "slug": t["slug"],
            "confederation": t["confederation"],
            "fifa_ranking": t["fifa_ranking"],
            "goals_scored_avg": t["goals_scored_avg"],
            "goals_conceded_avg": t["goals_conceded_avg"],
            "possession_avg": t["possession_avg"],
            "tactical_style": t["tactical_style"],
            "similarity_score": sim,
        })

    similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
    conn.close()
    return similarities[:top_n]


def find_proxy_h2h(
    team_a: str,
    team_b: str,
    db_path: Optional[Path] = None
) -> dict:
    """
    When there's no H2H between team_a and team_b:
    1. Find teams similar to team_b
    2. Use team_a's matches against those similar teams as proxy
    Returns a proxy H2H summary.
    """
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find teams similar to team_b
    similar_to_b = find_similar_teams(team_b, db_path, top_n=5, exclude=[team_a])

    team_a_row = conn.execute("SELECT id FROM teams WHERE name=?", (team_a,)).fetchone()
    if not team_a_row:
        conn.close()
        return {"available": False, "reason": f"Team {team_a} not found"}

    team_a_id = team_a_row["id"]

    proxy_matches = []
    for sim_team in similar_to_b:
        matches = conn.execute("""
            SELECT * FROM team_matches
            WHERE team_id=? AND opponent_name=?
            ORDER BY date DESC LIMIT 5
        """, (team_a_id, sim_team["team_name"])).fetchall()

        for m in matches:
            proxy_matches.append({
                "opponent": sim_team["team_name"],
                "similarity": sim_team["similarity_score"],
                "date": m["date"],
                "result": m["result"],
                "goals_for": m["goals_for"],
                "goals_against": m["goals_against"],
                "competition": m["competition"],
            })

    if not proxy_matches:
        conn.close()
        return {
            "available": False,
            "reason": f"No proxy matches found for {team_a} vs similar teams to {team_b}",
            "similar_teams": similar_to_b[:3],
        }

    # Compute proxy win/draw/loss %
    wins = sum(1 for m in proxy_matches if m["result"] == "W")
    draws = sum(1 for m in proxy_matches if m["result"] == "D")
    losses = sum(1 for m in proxy_matches if m["result"] == "L")
    total = len(proxy_matches)

    avg_gf = sum(m["goals_for"] for m in proxy_matches) / total
    avg_ga = sum(m["goals_against"] for m in proxy_matches) / total

    conn.close()
    return {
        "available": True,
        "team_a": team_a,
        "team_b": team_b,
        "proxy_matches": proxy_matches,
        "total_proxy_matches": total,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_pct": round(wins / total * 100, 1),
        "draw_pct": round(draws / total * 100, 1),
        "loss_pct": round(losses / total * 100, 1),
        "avg_goals_for": round(avg_gf, 2),
        "avg_goals_against": round(avg_ga, 2),
        "similar_teams_used": [s["team_name"] for s in similar_to_b[:3]],
        "avg_similarity": round(
            sum(m["similarity"] for m in proxy_matches) / total, 3
        ) if proxy_matches else 0,
    }


if __name__ == "__main__":
    import sys

    team = sys.argv[1] if len(sys.argv) > 1 else "Panama"
    print(f"\n=== Equipos mas similares a {team} ===\n")

    similar = find_similar_teams(team, top_n=5)
    for i, t in enumerate(similar, 1):
        print(f"  {i}. {t['team_name']:<20} similitud: {t['similarity_score']:.3f}  "
              f"(ranking: {t['fifa_ranking']}, {t['confederation']})")

    if len(sys.argv) > 2:
        team2 = sys.argv[2]
        print(f"\n=== Proxy H2H: {team} vs {team2} ===\n")
        proxy = find_proxy_h2h(team, team2)
        if proxy.get("available"):
            print(f"  Partidos proxy: {proxy['total_proxy_matches']}")
            print(f"  W/D/L: {proxy['wins']}/{proxy['draws']}/{proxy['losses']}")
            print(f"  Goles a favor avg: {proxy['avg_goals_for']}")
            print(f"  Goles en contra avg: {proxy['avg_goals_against']}")
            print(f"  Equipos similares usados: {', '.join(proxy['similar_teams_used'])}")
        else:
            print(f"  No disponible: {proxy.get('reason')}")
    print()
