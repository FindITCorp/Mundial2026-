"""
models/match_events.py — Motor de eventos secundarios de un partido.

A partir de los λ de goles, las tácticas de ambos equipos y el árbitro
asignado, estima (valores esperados) y simula (un sorteo) los eventos:

  • Tiros y tiros a puerta (shots / shots on target)
  • Córners
  • Faltas
  • Tarjetas amarillas y rojas
  • Penaltis
  • Posesión
  • Fueras de juego (offsides)

Modelos:
  Córners      ~ f(λ, posesión, estilo de ataque por banda, pressing rival)
  Tiros        ~ derivados de λ y de la tasa de conversión SoT→gol del equipo
  Faltas       ~ f(pressing de ambos, estrictez del árbitro)
  Tarjetas     ~ Poisson(faltas · prob_tarjeta · factor_árbitro)
  Penaltis     ~ f(tiempo en área rival ≈ λ atacante, penalty_rate del árbitro)
"""
from __future__ import annotations
import math
import random

from models.referee_model import Referee, AVG_REFEREE, referee_card_factor

# Tasas de conversión SoT→gol por equipo (de match_players WC2018/2022).
# Default 0.32 si el equipo no está calibrado.
CONVERSION = {
    "Brazil": 0.212, "Germany": 0.182, "Panama": 0.125, "Belgium": 0.348,
    "Croatia": 0.486, "Argentina": 0.26, "France": 0.28, "Spain": 0.24,
    "England": 0.25, "Portugal": 0.27, "Colombia": 0.30, "Costa Rica": 0.22,
}
DEFAULT_CONVERSION = 0.30

# Reparto de tiros: SoT ≈ 35-38% del total de tiros
SOT_RATIO = 0.37
# Probabilidad de que una falta termine en tarjeta (modulada por árbitro)
FOUL_TO_CARD = 0.135


def _conversion(team_name: str) -> float:
    return CONVERSION.get(team_name, DEFAULT_CONVERSION)


def expected_shots(team_name: str, lam: float) -> tuple[float, float]:
    """Devuelve (tiros_totales, tiros_a_puerta) esperados dado λ goles."""
    conv = _conversion(team_name)
    sot = lam / max(conv, 0.08)          # goles = SoT * conversión → SoT = goles/conv
    shots = sot / SOT_RATIO
    # límites realistas
    sot = max(1.5, min(11.0, sot))
    shots = max(4.0, min(28.0, shots))
    return round(shots, 1), round(sot, 1)


def expected_corners(lam: float, possession: float, press_against: float,
                     build_up_style: str = "mixed") -> float:
    """
    Córners esperados: crecen con λ (presión ofensiva), posesión y estilo.
    Equipos de juego por banda / build-up corto generan más córners.
    """
    base = 2.2 + lam * 1.7 + (possession - 50) * 0.045
    style_mult = {"short": 1.10, "mixed": 1.0, "direct": 0.92}.get(build_up_style, 1.0)
    # Defensa que presiona arriba concede algo más de córners en transición
    press_mult = 1.0 + (press_against - 0.55) * 0.10
    return round(max(1.5, base * style_mult * press_mult), 1)


def expected_fouls(press_for: float, press_against: float,
                   ref: Referee) -> float:
    """Faltas cometidas por un equipo: f(su pressing, estrictez del árbitro)."""
    base = 9.0 + press_for * 7.0
    # Árbitros más estrictos "detectan" más faltas
    strict_mult = 0.85 + ref.strictness * 0.35
    return round(base * strict_mult, 1)


def expected_cards(fouls: float, ref: Referee, rivalry: float = 0.0) -> float:
    """Tarjetas amarillas esperadas para un equipo."""
    card_prob = FOUL_TO_CARD * (0.8 + ref.strictness * 0.5)
    base = fouls * card_prob * referee_card_factor(ref)
    base *= 1.0 + rivalry * 0.25        # derbis/clásicos suben la fricción
    return round(max(0.5, base), 2)


def expected_penalty_prob(lam_attack: float, ref: Referee) -> float:
    """P(un equipo obtenga ≥1 penalti) dado su λ y el árbitro."""
    # Tiempo de peligro en área ≈ proporcional a λ
    base = 0.085 + lam_attack * 0.035
    base *= ref.penalty_rate / AVG_REFEREE.penalty_rate
    return round(min(0.42, base), 3)


def expected_events(home_name: str, away_name: str,
                    lam_h: float, lam_a: float,
                    poss_h: float, poss_a: float,
                    press_h: float, press_a: float,
                    style_h: str, style_a: str,
                    ref: Referee, rivalry: float = 0.0) -> dict:
    """Calcula todos los valores ESPERADOS de eventos del partido."""
    sh_h, sot_h = expected_shots(home_name, lam_h)
    sh_a, sot_a = expected_shots(away_name, lam_a)

    cor_h = expected_corners(lam_h, poss_h, press_a, style_h)
    cor_a = expected_corners(lam_a, poss_a, press_h, style_a)

    foul_h = expected_fouls(press_h, press_a, ref)
    foul_a = expected_fouls(press_a, press_h, ref)

    yc_h = expected_cards(foul_h, ref, rivalry)
    yc_a = expected_cards(foul_a, ref, rivalry)

    pen_h = expected_penalty_prob(lam_h, ref)
    pen_a = expected_penalty_prob(lam_a, ref)

    return {
        "referee": ref.name,
        "referee_country": ref.country,
        "shots":        {"home": sh_h, "away": sh_a},
        "shots_on_target": {"home": sot_h, "away": sot_a},
        "corners":      {"home": cor_h, "away": cor_a},
        "fouls":        {"home": foul_h, "away": foul_a},
        "yellow_cards": {"home": yc_h, "away": yc_a},
        "red_cards":    {"home": round(ref.reds_per_game / 2, 3),
                          "away": round(ref.reds_per_game / 2, 3)},
        "penalty_prob": {"home": pen_h, "away": pen_a},
        "total_cards":  round(yc_h + yc_a, 1),
        "total_corners": round(cor_h + cor_a, 1),
    }


def simulate_events(home_name: str, away_name: str,
                    lam_h: float, lam_a: float,
                    poss_h: float, poss_a: float,
                    press_h: float, press_a: float,
                    style_h: str, style_a: str,
                    ref: Referee, rivalry: float = 0.0) -> dict:
    """Un sorteo concreto de eventos (para un escenario de partido)."""
    exp = expected_events(home_name, away_name, lam_h, lam_a, poss_h, poss_a,
                          press_h, press_a, style_h, style_a, ref, rivalry)

    def pois(mu):
        return _poisson_sample(mu)

    pen_h = 1 if random.random() < exp["penalty_prob"]["home"] else 0
    pen_a = 1 if random.random() < exp["penalty_prob"]["away"] else 0

    return {
        "referee": ref.name,
        "shots":        {"home": pois(exp["shots"]["home"]),
                          "away": pois(exp["shots"]["away"])},
        "shots_on_target": {"home": pois(exp["shots_on_target"]["home"]),
                             "away": pois(exp["shots_on_target"]["away"])},
        "corners":      {"home": pois(exp["corners"]["home"]),
                          "away": pois(exp["corners"]["away"])},
        "fouls":        {"home": pois(exp["fouls"]["home"]),
                          "away": pois(exp["fouls"]["away"])},
        "yellow_cards": {"home": pois(exp["yellow_cards"]["home"]),
                          "away": pois(exp["yellow_cards"]["away"])},
        "red_cards":    {"home": 1 if random.random() < ref.reds_per_game / 2 else 0,
                          "away": 1 if random.random() < ref.reds_per_game / 2 else 0},
        "penalties":    {"home": pen_h, "away": pen_a},
    }


def _poisson_sample(mu: float) -> int:
    """Muestra de una Poisson (algoritmo de Knuth)."""
    if mu <= 0:
        return 0
    L = math.exp(-mu)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


if __name__ == "__main__":
    from models.referee_model import assign_referee
    ref = assign_referee("Brazil", "Argentina", "CONMEBOL", "CONMEBOL",
                         "final", seed="WC2026")
    print(f"\nÁrbitro: {ref.name} ({ref.country}) — "
          f"{ref.cards_per_game} YC/p, pen_rate {ref.penalty_rate}")
    exp = expected_events("Brazil", "Argentina", 1.6, 1.4, 52, 48,
                          0.65, 0.62, "short", "mixed", ref, rivalry=0.8)
    print("\nEVENTOS ESPERADOS (Brazil vs Argentina):")
    for k, v in exp.items():
        print(f"  {k:<18} {v}")
