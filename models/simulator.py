"""
Motor de simulacion de partidos basado en distribucion de Poisson.

Simula N=10,000 partidos para calcular:
- Probabilidades de victoria local, empate y victoria visitante
- El marcador mas probable
- Top 5 marcadores con sus porcentajes

Factores que ajustan los expected goals (xG):
- Ataque del equipo: goals_scored_avg normalizado vs. todos los equipos
- Defensa del rival: goals_conceded_avg normalizado vs. todos los equipos
- Calidad de jugadores: rating promedio de FWD/MID del equipo atacante
- Bajas de jugadores clave: reduccion de xG si falta el top scorer/creator
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np
from scipy.stats import poisson

from models.predictor import TeamSnapshot
from models.formation_engine import formation_matchup_factor, get_team_tactics


# ---------------------------------------------------------------------------
# Constantes de calibracion
# ---------------------------------------------------------------------------

# Goals-per-game promedio en Mundiales (historico: ~2.64 goles/partido)
_LEAGUE_AVG_GOALS = 1.32       # promedio por equipo por partido
_MAX_GOALS_DISPLAY = 5         # goles maximos que mostramos en top marcadores
N_SIMULATIONS = 10_000

# Ratings promedio por posicion (escala 0-100).
# Valores de referencia para normalizar el ajuste de calidad.
_DEFAULT_FWD_MID_RATING = 78.0   # rating promedio mundial de campo
_RATING_SCALE_MAX = 95.0         # rating del mejor jugador del mundo
_RATING_SCALE_MIN = 60.0         # minimo representativo de la competicion


# ---------------------------------------------------------------------------
# Helpers de normalizacion
# ---------------------------------------------------------------------------

def _normalize_attack(team: TeamSnapshot, all_teams: list[TeamSnapshot]) -> float:
    """
    Fuerza de ataque normalizada.
    1.0 = promedio. >1.0 = ataca mejor que el promedio.
    """
    all_avgs = [t.goals_scored_avg for t in all_teams if t.goals_scored_avg > 0]
    league_avg = float(np.mean(all_avgs)) if all_avgs else _LEAGUE_AVG_GOALS
    return team.goals_scored_avg / league_avg if league_avg > 0 else 1.0


def _normalize_defense(team: TeamSnapshot, all_teams: list[TeamSnapshot]) -> float:
    """
    Debilidad defensiva normalizada del equipo.
    1.0 = promedio. >1.0 = concede mas goles que el promedio (defensa peor).
    """
    all_avgs = [t.goals_conceded_avg for t in all_teams if t.goals_conceded_avg > 0]
    league_avg = float(np.mean(all_avgs)) if all_avgs else _LEAGUE_AVG_GOALS
    return team.goals_conceded_avg / league_avg if league_avg > 0 else 1.0


def _player_quality_factor(fwd_mid_rating: Optional[float]) -> float:
    """
    Convierte el rating promedio FWD/MID (0-100) en un multiplicador de xG.
    Rating 78 (promedio mundial) -> factor 1.0
    Rating 90 -> factor ~1.15
    Rating 65 -> factor ~0.85
    """
    if fwd_mid_rating is None:
        return 1.0
    rating = float(fwd_mid_rating)
    # Normalizamos entre min y max esperados
    norm = (rating - _DEFAULT_FWD_MID_RATING) / (_RATING_SCALE_MAX - _RATING_SCALE_MIN)
    # Factor entre 0.75 y 1.25
    return float(np.clip(1.0 + norm * 0.5, 0.75, 1.25))


def _missing_key_player_factor(missing: list[str], key_players: list[str]) -> float:
    """
    Reduce xG si faltan jugadores clave (top scorer / creador).
    Cada baja clave resta 5% del xG, con un maximo de 25% de reduccion.
    """
    if not key_players:
        return 1.0
    missing_key = [p for p in missing if p in key_players]
    reduction = len(missing_key) * 0.05
    return max(0.75, 1.0 - reduction)


# ---------------------------------------------------------------------------
# Calculo de xG
# ---------------------------------------------------------------------------

def compute_xg(
    attacking_team: TeamSnapshot,
    defending_team: TeamSnapshot,
    all_teams: list[TeamSnapshot],
    fwd_mid_rating: Optional[float] = None,
) -> float:
    """
    Calcula los expected goals (xG) del equipo atacante contra el equipo
    defensor, dado el contexto de todos los equipos del torneo.

    xG = base * ataque_norm * defensa_rival_norm * factor_calidad * factor_bajas
    """
    attack_strength  = _normalize_attack(attacking_team, all_teams)
    defense_weakness = _normalize_defense(defending_team, all_teams)
    quality_factor   = _player_quality_factor(fwd_mid_rating)
    missing_factor   = _missing_key_player_factor(
        attacking_team.key_players_missing,
        attacking_team.key_players_available,
    )

    xg = _LEAGUE_AVG_GOALS * attack_strength * defense_weakness * quality_factor * missing_factor
    # Limitamos a un rango razonable
    return float(np.clip(xg, 0.2, 5.0))


# ---------------------------------------------------------------------------
# Simulacion principal
# ---------------------------------------------------------------------------

def simulate_match(
    home: TeamSnapshot,
    away: TeamSnapshot,
    all_teams: Optional[list[TeamSnapshot]] = None,
    home_fwd_mid_rating: Optional[float] = None,
    away_fwd_mid_rating: Optional[float] = None,
    n: int = N_SIMULATIONS,
    rng_seed: Optional[int] = None,
    apply_formation_factor: bool = True,
    db_path=None,
) -> dict:
    """
    Simula n partidos usando distribucion de Poisson y devuelve estadisticas
    completas del resultado.

    Parametros
    ----------
    home : TeamSnapshot
        Datos del equipo local.
    away : TeamSnapshot
        Datos del equipo visitante.
    all_teams : list[TeamSnapshot], opcional
        Lista de todos los equipos del torneo para normalizar.
    home_fwd_mid_rating : float, opcional
        Rating promedio de FWD/MID del equipo local (escala 0-100).
    away_fwd_mid_rating : float, opcional
        Rating promedio de FWD/MID del equipo visitante (escala 0-100).
    n : int
        Numero de simulaciones (default 10,000).
    rng_seed : int, opcional
        Semilla para reproducibilidad.
    apply_formation_factor : bool
        Si True, aplica multiplicador tactico basado en formaciones de los DTs.
    db_path : opcional
        Ruta a la base de datos (para cargar tacticas).

    Retorna
    -------
    dict con claves:
        xg_home, xg_away,
        home_wins_pct, draws_pct, away_wins_pct,
        most_likely_scoreline, most_likely_pct,
        top_scorelines (lista de dicts {scoreline, pct}),
        raw_text (bloque de texto listo para imprimir),
        tactical_analysis (str, analisis tactico del partido),
        home_formation_factor, away_formation_factor
    """
    if all_teams is None:
        all_teams = [home, away]

    # --- Expected goals ---
    xg_home = compute_xg(home, away, all_teams, home_fwd_mid_rating)
    xg_away = compute_xg(away, home, all_teams, away_fwd_mid_rating)

    # --- Formation / tactical factor ---
    tactical_analysis = ""
    home_formation_factor = 1.0
    away_formation_factor = 1.0

    if apply_formation_factor:
        try:
            home_tactics = get_team_tactics(home.name, db_path)
            away_tactics = get_team_tactics(away.name, db_path)
            if home_tactics and away_tactics:
                matchup = formation_matchup_factor(home_tactics, away_tactics)
                home_formation_factor = matchup["home_factor"]
                away_formation_factor = matchup["away_factor"]
                tactical_analysis = matchup.get("analysis", "")
                xg_home = float(np.clip(xg_home * home_formation_factor, 0.2, 5.0))
                xg_away = float(np.clip(xg_away * away_formation_factor, 0.2, 5.0))
        except Exception:
            pass  # formation factor is non-critical; simulation still runs

    # --- Simulacion ---
    rng = np.random.default_rng(rng_seed)
    home_goals_sim = rng.poisson(xg_home, size=n)
    away_goals_sim = rng.poisson(xg_away, size=n)

    # --- Resultados globales ---
    home_wins = int(np.sum(home_goals_sim > away_goals_sim))
    draws     = int(np.sum(home_goals_sim == away_goals_sim))
    away_wins = int(np.sum(home_goals_sim < away_goals_sim))

    home_wins_pct = round(home_wins / n * 100, 1)
    draws_pct     = round(draws     / n * 100, 1)
    away_wins_pct = round(away_wins / n * 100, 1)

    # --- Marcadores ---
    scorelines = Counter(zip(home_goals_sim.tolist(), away_goals_sim.tolist()))
    total = sum(scorelines.values())

    top5 = scorelines.most_common(5)
    top_scorelines = [
        {
            "scoreline": f"{g}-{a}",
            "home_goals": g,
            "away_goals": a,
            "pct": round(cnt / total * 100, 1),
        }
        for (g, a), cnt in top5
    ]

    most_likely = top_scorelines[0] if top_scorelines else {"scoreline": "0-0", "pct": 0.0}
    most_likely_label = (
        f"{home.name} {most_likely['home_goals']} "
        f"– {most_likely['away_goals']} {away.name}"
    )

    # --- Texto de salida ---
    raw_text = _format_output(
        home_name=home.name,
        away_name=away.name,
        most_likely_label=most_likely_label,
        most_likely_pct=most_likely["pct"],
        top_scorelines=top_scorelines,
        home_wins_pct=home_wins_pct,
        draws_pct=draws_pct,
        away_wins_pct=away_wins_pct,
        n=n,
    )

    return {
        "xg_home": round(xg_home, 2),
        "xg_away": round(xg_away, 2),
        "home_wins_pct": home_wins_pct,
        "draws_pct": draws_pct,
        "away_wins_pct": away_wins_pct,
        "most_likely_scoreline": most_likely["scoreline"],
        "most_likely_label": most_likely_label,
        "most_likely_pct": most_likely["pct"],
        "top_scorelines": top_scorelines,
        "raw_text": raw_text,
        "tactical_analysis": tactical_analysis,
        "home_formation_factor": round(home_formation_factor, 4),
        "away_formation_factor": round(away_formation_factor, 4),
    }


# ---------------------------------------------------------------------------
# Formato de salida
# ---------------------------------------------------------------------------

def _confidence_label(pct: float) -> str:
    """Convert most-likely scoreline probability to a confidence label."""
    if pct >= 18:
        return "ALTA"
    if pct >= 12:
        return "MEDIA"
    return "BAJA"


def _format_output(
    home_name: str,
    away_name: str,
    most_likely_label: str,
    most_likely_pct: float,
    top_scorelines: list[dict],
    home_wins_pct: float,
    draws_pct: float,
    away_wins_pct: float,
    n: int,
) -> str:
    conf = _confidence_label(most_likely_pct)

    # Determine dominant outcome label
    if home_wins_pct >= away_wins_pct and home_wins_pct >= draws_pct:
        outcome = f"Victoria {home_name}"
    elif away_wins_pct >= home_wins_pct and away_wins_pct >= draws_pct:
        outcome = f"Victoria {away_name}"
    else:
        outcome = "Empate"

    lines = [
        f"\n  RESULTADO PRONOSTICADO  [{conf} confianza]",
        f"  ══════════════════════════════════════════",
        f"  {most_likely_label}",
        f"",
        f"  Otros marcadores probables:",
    ]
    for s in top_scorelines[1:5]:
        lines.append(f"    {s['scoreline']}")

    lines += [
        f"",
        f"  Desenlace más probable: {outcome}",
    ]
    return "\n".join(lines)
