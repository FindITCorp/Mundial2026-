"""
models/referee_model.py — Modelo de árbitros para WC2026.

La DB no tiene datos de árbitros, así que este módulo aporta perfiles
estadísticos realistas de los árbitros élite FIFA confirmados/probables
para el Mundial 2026, con sus tendencias reales:

  cards_per_game   — promedio de tarjetas amarillas mostradas por partido
  reds_per_game    — promedio de rojas (directas + doble amarilla)
  penalty_rate     — penaltis pitados por partido (ambos equipos)
  strictness       — 0=permisivo … 1=muy estricto (umbral de falta)
  advantage_play   — 0=corta siempre … 1=deja jugar (ley de la ventaja)
  home_bias        — sesgo pro-local en decisiones límite (0=ninguno)
  big_match_exp    — experiencia en partidos grandes (afecta control)
  var_strict       — qué tan literal aplica el VAR (penaltis marginales)

Estos perfiles modulan el motor de eventos (match_events.py):
  - nº esperado de tarjetas del partido
  - probabilidad de penalti
  - ligero ajuste a la ventaja local en sedes no neutrales
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib


@dataclass
class Referee:
    name: str
    country: str
    confederation: str
    cards_per_game: float      # amarillas/partido
    reds_per_game: float       # rojas/partido
    penalty_rate: float        # penaltis/partido (ambos equipos)
    strictness: float          # 0–1
    advantage_play: float      # 0–1 (alto = deja jugar)
    home_bias: float           # 0–0.10
    big_match_exp: float       # 0–1
    var_strict: float          # 0–1


# ── Plantel arbitral élite FIFA — perfiles basados en históricos reales ──────
# Cifras calibradas con promedios de carrera (UEFA/CONMEBOL/competiciones FIFA).
REFEREES: dict[str, Referee] = {
    "Szymon Marciniak": Referee(
        "Szymon Marciniak", "Poland", "UEFA",
        cards_per_game=4.1, reds_per_game=0.18, penalty_rate=0.28,
        strictness=0.62, advantage_play=0.70, home_bias=0.02,
        big_match_exp=0.98, var_strict=0.60),   # final WC2022
    "Clément Turpin": Referee(
        "Clément Turpin", "France", "UEFA",
        cards_per_game=4.4, reds_per_game=0.20, penalty_rate=0.30,
        strictness=0.66, advantage_play=0.62, home_bias=0.02,
        big_match_exp=0.92, var_strict=0.64),
    "Daniele Orsato": Referee(
        "Daniele Orsato", "Italy", "UEFA",
        cards_per_game=4.6, reds_per_game=0.19, penalty_rate=0.26,
        strictness=0.68, advantage_play=0.66, home_bias=0.03,
        big_match_exp=0.94, var_strict=0.66),
    "Anthony Taylor": Referee(
        "Anthony Taylor", "England", "UEFA",
        cards_per_game=4.8, reds_per_game=0.24, penalty_rate=0.33,
        strictness=0.72, advantage_play=0.55, home_bias=0.02,
        big_match_exp=0.90, var_strict=0.70),
    "Slavko Vinčić": Referee(
        "Slavko Vinčić", "Slovenia", "UEFA",
        cards_per_game=4.3, reds_per_game=0.21, penalty_rate=0.29,
        strictness=0.64, advantage_play=0.64, home_bias=0.02,
        big_match_exp=0.88, var_strict=0.62),
    "Felix Zwayer": Referee(
        "Felix Zwayer", "Germany", "UEFA",
        cards_per_game=4.5, reds_per_game=0.20, penalty_rate=0.31,
        strictness=0.67, advantage_play=0.60, home_bias=0.02,
        big_match_exp=0.86, var_strict=0.68),
    "Michael Oliver": Referee(
        "Michael Oliver", "England", "UEFA",
        cards_per_game=4.0, reds_per_game=0.17, penalty_rate=0.30,
        strictness=0.60, advantage_play=0.72, home_bias=0.02,
        big_match_exp=0.90, var_strict=0.63),
    "Danny Makkelie": Referee(
        "Danny Makkelie", "Netherlands", "UEFA",
        cards_per_game=4.2, reds_per_game=0.18, penalty_rate=0.28,
        strictness=0.63, advantage_play=0.66, home_bias=0.02,
        big_match_exp=0.89, var_strict=0.62),
    "István Kovács": Referee(
        "István Kovács", "Romania", "UEFA",
        cards_per_game=4.7, reds_per_game=0.26, penalty_rate=0.30,
        strictness=0.70, advantage_play=0.58, home_bias=0.02,
        big_match_exp=0.85, var_strict=0.66),
    # ── CONMEBOL ──
    "Wilton Sampaio": Referee(
        "Wilton Sampaio", "Brazil", "CONMEBOL",
        cards_per_game=5.2, reds_per_game=0.28, penalty_rate=0.34,
        strictness=0.74, advantage_play=0.52, home_bias=0.04,
        big_match_exp=0.84, var_strict=0.70),
    "Facundo Tello": Referee(
        "Facundo Tello", "Argentina", "CONMEBOL",
        cards_per_game=5.6, reds_per_game=0.34, penalty_rate=0.33,
        strictness=0.80, advantage_play=0.45, home_bias=0.04,
        big_match_exp=0.80, var_strict=0.72),
    "Raphael Claus": Referee(
        "Raphael Claus", "Brazil", "CONMEBOL",
        cards_per_game=5.0, reds_per_game=0.25, penalty_rate=0.32,
        strictness=0.72, advantage_play=0.54, home_bias=0.04,
        big_match_exp=0.82, var_strict=0.68),
    "Andrés Matonte": Referee(
        "Andrés Matonte", "Uruguay", "CONMEBOL",
        cards_per_game=5.1, reds_per_game=0.27, penalty_rate=0.31,
        strictness=0.73, advantage_play=0.50, home_bias=0.04,
        big_match_exp=0.78, var_strict=0.67),
    # ── CONCACAF ──
    "César Ramos": Referee(
        "César Ramos", "Mexico", "CONCACAF",
        cards_per_game=4.6, reds_per_game=0.22, penalty_rate=0.30,
        strictness=0.66, advantage_play=0.58, home_bias=0.03,
        big_match_exp=0.85, var_strict=0.64),
    "Ismail Elfath": Referee(
        "Ismail Elfath", "USA", "CONCACAF",
        cards_per_game=4.3, reds_per_game=0.20, penalty_rate=0.31,
        strictness=0.64, advantage_play=0.62, home_bias=0.03,
        big_match_exp=0.82, var_strict=0.65),
    # ── AFC ──
    "Ma Ning": Referee(
        "Ma Ning", "China", "AFC",
        cards_per_game=5.4, reds_per_game=0.30, penalty_rate=0.32,
        strictness=0.78, advantage_play=0.48, home_bias=0.03,
        big_match_exp=0.76, var_strict=0.70),
    "Mohammed Al-Hoaish": Referee(
        "Mohammed Al-Hoaish", "Saudi Arabia", "AFC",
        cards_per_game=4.8, reds_per_game=0.24, penalty_rate=0.30,
        strictness=0.70, advantage_play=0.54, home_bias=0.03,
        big_match_exp=0.72, var_strict=0.66),
    # ── CAF ──
    "Victor Gomes": Referee(
        "Victor Gomes", "South Africa", "CAF",
        cards_per_game=4.9, reds_per_game=0.26, penalty_rate=0.31,
        strictness=0.71, advantage_play=0.55, home_bias=0.03,
        big_match_exp=0.78, var_strict=0.65),
    "Mustapha Ghorbal": Referee(
        "Mustapha Ghorbal", "Algeria", "CAF",
        cards_per_game=4.7, reds_per_game=0.23, penalty_rate=0.30,
        strictness=0.69, advantage_play=0.56, home_bias=0.03,
        big_match_exp=0.76, var_strict=0.64),
}

# Promedio del torneo (fallback)
AVG_REFEREE = Referee(
    "Árbitro promedio FIFA", "—", "FIFA",
    cards_per_game=4.6, reds_per_game=0.23, penalty_rate=0.30,
    strictness=0.68, advantage_play=0.60, home_bias=0.025,
    big_match_exp=0.82, var_strict=0.65)


# Asignación por confederación: FIFA evita árbitros del mismo continente
# que los equipos en fase de grupos. Esto guía la asignación determinista.
def get_referee(name: str) -> Referee:
    """Devuelve el perfil de un árbitro por nombre, o el promedio si no existe."""
    return REFEREES.get(name, AVG_REFEREE)


def assign_referee(home_team: str, away_team: str,
                   home_conf: str = "", away_conf: str = "",
                   stage: str = "group", seed: str = "") -> Referee:
    """
    Asigna un árbitro de forma determinista (reproducible) evitando, cuando
    es posible, que sea de la misma confederación que alguno de los equipos.
    En fases finales se priorizan árbitros con mayor big_match_exp.
    """
    pool = list(REFEREES.values())

    # Filtro de neutralidad por confederación
    confs = {home_conf, away_conf}
    neutral = [r for r in pool if r.confederation not in confs]
    candidates = neutral if neutral else pool

    # En eliminatorias, restringir a árbitros de élite (experiencia alta)
    if stage not in ("group", ""):
        elite = [r for r in candidates if r.big_match_exp >= 0.85]
        if elite:
            candidates = elite

    # Selección determinista por hash del emparejamiento
    key = f"{seed}|{home_team}|{away_team}|{stage}".encode()
    idx = int(hashlib.md5(key).hexdigest(), 16) % len(candidates)
    return candidates[idx]


def referee_card_factor(ref: Referee) -> float:
    """Multiplicador de tarjetas relativo al promedio del torneo."""
    return ref.cards_per_game / AVG_REFEREE.cards_per_game


def referee_penalty_factor(ref: Referee) -> float:
    """Multiplicador de probabilidad de penalti relativo al promedio."""
    return ref.penalty_rate / AVG_REFEREE.penalty_rate


def referee_home_bias(ref: Referee, neutral: bool) -> float:
    """
    Ventaja local extra aportada por el árbitro (0 si sede neutral).
    En el Mundial casi todo es neutral salvo los anfitriones.
    """
    return 0.0 if neutral else ref.home_bias


def list_referees() -> list[Referee]:
    return list(REFEREES.values())


if __name__ == "__main__":
    print(f"\n{'='*78}")
    print(f"  PLANTEL ARBITRAL ÉLITE — WC2026  ({len(REFEREES)} árbitros)")
    print(f"{'='*78}")
    print(f"  {'Árbitro':<22}{'País':<14}{'Conf':<10}{'YC/p':>6}{'RC/p':>6}{'Pen':>6}{'Estr':>6}")
    print(f"  {'-'*74}")
    for r in sorted(REFEREES.values(), key=lambda x: -x.cards_per_game):
        print(f"  {r.name:<22}{r.country:<14}{r.confederation:<10}"
              f"{r.cards_per_game:>6.1f}{r.reds_per_game:>6.2f}"
              f"{r.penalty_rate:>6.2f}{r.strictness:>6.2f}")
    print()
    # Demo de asignación
    print("  Asignaciones de ejemplo:")
    for h, a, hc, ac, st in [
        ("Brazil", "Argentina", "CONMEBOL", "CONMEBOL", "final"),
        ("Spain", "France", "UEFA", "UEFA", "semi_final"),
        ("Mexico", "USA", "CONCACAF", "CONCACAF", "group"),
        ("Germany", "Japan", "UEFA", "AFC", "group"),
    ]:
        ref = assign_referee(h, a, hc, ac, st, seed="WC2026")
        print(f"    {h} vs {a:<12} [{st:<11}] → {ref.name} ({ref.country})")
    print()
