"""
Motor de predicción de partidos basado en:
- Forma reciente (últimos 5-10 partidos)
- Historial H2H
- Estadísticas de jugadores clave
- Alineación confirmada (lesiones, suspensiones)
- Factor sede / tipo de torneo
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeamSnapshot:
    name: str
    recent_form: list[dict] = field(default_factory=list)    # últimos 10 partidos
    h2h_record: list[dict] = field(default_factory=list)     # H2H vs rival
    key_players_available: list[str] = field(default_factory=list)
    key_players_missing: list[str] = field(default_factory=list)
    formation: str = "4-3-3"
    ranking_fifa: Optional[int] = None
    goals_scored_avg: float = 0.0
    goals_conceded_avg: float = 0.0
    possession_avg: float = 50.0


def form_score(matches: list[dict], team_name: str) -> float:
    """Convierte forma reciente en score 0-1. Más reciente = más peso."""
    if not matches:
        return 0.5
    weights = [1.5 ** i for i in range(len(matches))]
    total_weight = sum(weights)
    score = 0.0
    for i, m in enumerate(reversed(matches)):
        result = m.get("result", "D")
        pts = {"W": 1.0, "D": 0.5, "L": 0.0}.get(result, 0.5)
        score += pts * weights[i]
    return score / total_weight


def h2h_score(h2h: list[dict], team_name: str) -> float:
    """Score 0-1 basado en historial H2H."""
    if not h2h:
        return 0.5
    wins = sum(1 for m in h2h if m.get("winner") == team_name)
    draws = sum(1 for m in h2h if m.get("winner") == "draw")
    total = len(h2h)
    return (wins + 0.5 * draws) / total


def availability_factor(missing: list[str], key_players: list[str]) -> float:
    """Penaliza por jugadores clave ausentes. 1.0 = plantel completo."""
    if not key_players:
        return 1.0
    missing_key = [p for p in missing if p in key_players]
    penalty = len(missing_key) * 0.05  # -5% por cada titular clave ausente
    return max(0.7, 1.0 - penalty)


def ranking_factor(ranking: Optional[int]) -> float:
    """FIFA ranking → score 0-1. Ranking 1 = 1.0, ranking 50+ = ~0.5"""
    if ranking is None:
        return 0.5
    return max(0.2, 1.0 - (ranking - 1) * 0.01)


def predict_match(home: TeamSnapshot, away: TeamSnapshot, neutral_venue: bool = False) -> dict:
    """
    Predice el resultado más probable de un partido.
    Retorna probabilidades de victoria local, empate y victoria visitante.
    """
    # --- Scores por componente ---
    home_form    = form_score(home.recent_form, home.name)
    away_form    = form_score(away.recent_form, away.name)

    home_h2h     = h2h_score(home.h2h_record, home.name)
    away_h2h     = h2h_score(away.h2h_record, away.name)

    home_avail   = availability_factor(home.key_players_missing, home.key_players_available)
    away_avail   = availability_factor(away.key_players_missing, away.key_players_available)

    home_rank    = ranking_factor(home.ranking_fifa)
    away_rank    = ranking_factor(away.ranking_fifa)

    home_goals   = min(1.0, home.goals_scored_avg / 3.0)
    away_goals   = min(1.0, away.goals_scored_avg / 3.0)

    # --- Score compuesto (pesos ajustables) ---
    W = {"form": 0.30, "h2h": 0.25, "ranking": 0.20, "availability": 0.15, "attack": 0.10}

    home_score = (
        W["form"]         * home_form   +
        W["h2h"]          * home_h2h    +
        W["ranking"]      * home_rank   +
        W["availability"] * home_avail  +
        W["attack"]       * home_goals
    )
    away_score = (
        W["form"]         * away_form   +
        W["h2h"]          * away_h2h    +
        W["ranking"]      * away_rank   +
        W["availability"] * away_avail  +
        W["attack"]       * away_goals
    )

    # Ventaja de sede (en Mundial la sede es neutral)
    if not neutral_venue:
        home_score *= 1.1

    # --- Convertir a probabilidades ---
    total = home_score + away_score
    raw_home = home_score / total
    raw_away = away_score / total

    # El empate toma de ambas probabilidades (modelo simplificado)
    draw_base = 0.28  # base estadística histórica de empates en Mundiales
    draw = draw_base * (1 - abs(raw_home - raw_away))
    home_win = raw_home * (1 - draw / 2)
    away_win = raw_away * (1 - draw / 2)

    # Normalizar a 100%
    total_prob = home_win + draw + away_win
    home_win /= total_prob
    draw     /= total_prob
    away_win /= total_prob

    # --- Resultado más probable ---
    probs = {"home_win": home_win, "draw": draw, "away_win": away_win}
    most_likely = max(probs, key=probs.get)

    labels = {"home_win": f"Victoria {home.name}", "draw": "Empate", "away_win": f"Victoria {away.name}"}

    return {
        "prediction": labels[most_likely],
        "confidence": round(probs[most_likely] * 100, 1),
        "probabilities": {
            labels["home_win"]: round(home_win * 100, 1),
            "Empate":            round(draw     * 100, 1),
            labels["away_win"]: round(away_win  * 100, 1),
        },
        "component_scores": {
            home.name: {"form": round(home_form,2), "h2h": round(home_h2h,2), "ranking": round(home_rank,2), "disponibilidad": round(home_avail,2)},
            away.name: {"form": round(away_form,2), "h2h": round(away_h2h,2), "ranking": round(away_rank,2), "disponibilidad": round(away_avail,2)},
        }
    }
