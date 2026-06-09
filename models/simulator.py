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
import math
import sqlite3

import numpy as np
from scipy.stats import poisson

from models.predictor import TeamSnapshot
from models.formation_engine import formation_matchup_factor, get_team_tactics


# ---------------------------------------------------------------------------
# Constantes de calibracion
# ---------------------------------------------------------------------------

_LEAGUE_AVG_GOALS   = 1.32   # goles/equipo/partido en WC historico
_MAX_GOALS_DISPLAY  = 5
N_SIMULATIONS       = 10_000
_DEFAULT_FWD_MID_RATING = 78.0
_RATING_SCALE_MAX   = 95.0
_RATING_SCALE_MIN   = 60.0

# Equipos sede con ventaja real
_WC_HOST_TEAMS = {"USA", "United States", "Mexico", "Canada"}
_HOST_SCALE_HOME    = 0.96   # sede: pequeña ventaja
_NEUTRAL_SCALE_HOME = 0.90   # neutral: elimina sesgo de "local" en DB

# Boost de empate en partidos parejos
_DRAW_BOOST_THRESHOLD = 0.40
_DRAW_BOOST_FACTOR    = 0.05

# Peso del Elo en el xG: 80% Elo, 20% forma/calidad
_ELO_WEIGHT = 0.80
_ELO_XG_ALPHA = 0.65   # curvatura: e=0.5→xG=1.32, e=0.75→xG=1.74, e=0.25→xG=1.00


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expected_elo(elo_att: float, elo_def: float) -> float:
    """Probabilidad de que att gane 1v1 (sin empate)."""
    return 1.0 / (1.0 + 10 ** ((elo_def - elo_att) / 400))


def _player_quality_factor(fwd_mid_rating: Optional[float]) -> float:
    if fwd_mid_rating is None:
        return 1.0
    norm = (float(fwd_mid_rating) - _DEFAULT_FWD_MID_RATING) / (_RATING_SCALE_MAX - _RATING_SCALE_MIN)
    return float(np.clip(1.0 + norm * 0.5, 0.75, 1.25))


def _missing_key_player_factor(missing: list[str], key_players: list[str]) -> float:
    if not key_players:
        return 1.0
    missing_key = [p for p in missing if p in key_players]
    return max(0.75, 1.0 - len(missing_key) * 0.05)


def _load_elo(db_path, team_name: str) -> Optional[float]:
    """Carga Elo desde team_elo. Devuelve None si no existe."""
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT e.elo FROM team_elo e JOIN teams t ON t.id=e.team_id WHERE t.name=?",
            (team_name,)
        ).fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception:
        return None


def _rank_to_elo(fifa_rank: int) -> float:
    """Fallback: convierte ranking FIFA a Elo aproximado."""
    return 1900 - 200 * math.log10(max(1, fifa_rank or 50))


def _form_factor(recent_form) -> float:
    """Convierte lista de resultados recientes en modificador ±15%."""
    if not recent_form:
        return 1.0
    scores = []
    for m in recent_form:
        if isinstance(m, dict):
            r = m.get('result', '')
            scores.append(1.0 if r == 'W' else (0.5 if r == 'D' else 0.0))
        else:
            scores.append(float(m))
    if not scores:
        return 1.0
    score = sum(scores) / len(scores)
    return 1.0 + (score - 0.5) * 0.30


# ---------------------------------------------------------------------------
# Calculo de xG — Elo como driver principal
# ---------------------------------------------------------------------------

def compute_xg(
    attacking_team: TeamSnapshot,
    defending_team: TeamSnapshot,
    all_teams: list[TeamSnapshot],       # mantenido por compatibilidad
    fwd_mid_rating: Optional[float] = None,
    set_piece_index: float = 0.18,
    elo_att: Optional[float] = None,
    elo_def: Optional[float] = None,
) -> float:
    """
    xG = Elo_base * form_mod * quality_mod * missing_mod * set_piece_mod

    Driver principal: Elo rating relativo (80% del xG).
    Modificadores secundarios: forma reciente, calidad jugadores, bajas, set pieces.
    """
    # ── 1. Base xG desde Elo ───────────────────────────────────────────────
    if elo_att is not None and elo_def is not None:
        e = _expected_elo(elo_att, elo_def)
    else:
        # Fallback a ranking FIFA si no hay Elo
        r_att = getattr(attacking_team, 'ranking_fifa', 50) or 50
        r_def = getattr(defending_team, 'ranking_fifa', 50) or 50
        e = _expected_elo(_rank_to_elo(r_att), _rank_to_elo(r_def))

    xg_elo = _LEAGUE_AVG_GOALS * (e / 0.5) ** _ELO_XG_ALPHA

    # ── 2. Modificadores secundarios (max ±20% total) ──────────────────────
    form_mod    = _form_factor(getattr(attacking_team, 'recent_form', []))
    quality_mod = _player_quality_factor(fwd_mid_rating)
    missing_mod = _missing_key_player_factor(
        attacking_team.key_players_missing,
        attacking_team.key_players_available,
    )
    # Clamp modificadores para que no dominen sobre el Elo
    form_mod    = np.clip(form_mod,    0.88, 1.12)
    quality_mod = np.clip(quality_mod, 0.92, 1.08)

    xg = xg_elo * form_mod * quality_mod * missing_mod

    # ── 3. Set pieces (±4%) ───────────────────────────────────────────────
    set_piece_bonus = (set_piece_index - 0.18) * 0.67
    xg = xg * (1.0 + set_piece_bonus * 0.20)

    # ── 4. DNA matchup (non-critical) ─────────────────────────────────────
    try:
        from models.team_dna import get_team_dna, matchup_xg_factor as dna_xg_factor
        att_dna = get_team_dna(attacking_team.name)
        def_dna = get_team_dna(defending_team.name)
        if att_dna and def_dna:
            xg = xg * np.clip(dna_xg_factor(att_dna, def_dna), 0.92, 1.08)
    except Exception:
        pass

    return float(np.clip(xg, 0.25, 4.0))


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
    venue: str = "",           # NEW: e.g. "Mexico City"
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
    venue : str
        Nombre del estadio/ciudad anfitriona (e.g. "Mexico City", "New York").

    Retorna
    -------
    dict con claves:
        xg_home, xg_away,
        home_wins_pct, draws_pct, away_wins_pct,
        most_likely_scoreline, most_likely_pct,
        top_scorelines (lista de dicts {scoreline, pct}),
        raw_text (bloque de texto listo para imprimir),
        tactical_analysis (str, analisis tactico del partido),
        home_formation_factor, away_formation_factor,
        venue, home_set_piece_index, away_set_piece_index
    """
    if all_teams is None:
        all_teams = [home, away]

    # --- Cargar Elo y set piece indices desde DB ---
    home_spi = getattr(home, 'set_piece_index', 0.18) or 0.18
    away_spi = getattr(away, 'set_piece_index', 0.18) or 0.18
    elo_home = elo_away = None

    if db_path:
        try:
            conn = sqlite3.connect(str(db_path))
            # Set piece indices
            row = conn.execute("SELECT set_piece_index FROM teams WHERE name=?", (home.name,)).fetchone()
            if row and row[0] is not None:
                home_spi = float(row[0])
            row = conn.execute("SELECT set_piece_index FROM teams WHERE name=?", (away.name,)).fetchone()
            if row and row[0] is not None:
                away_spi = float(row[0])
            # Elo ratings desde team_elo
            row = conn.execute(
                "SELECT e.elo FROM team_elo e JOIN teams t ON t.id=e.team_id WHERE t.name=?",
                (home.name,)
            ).fetchone()
            if row:
                elo_home = float(row[0])
            row = conn.execute(
                "SELECT e.elo FROM team_elo e JOIN teams t ON t.id=e.team_id WHERE t.name=?",
                (away.name,)
            ).fetchone()
            if row:
                elo_away = float(row[0])
            conn.close()
        except Exception:
            pass

    # Fallback a ranking FIFA si no hay Elo en DB
    if elo_home is None:
        elo_home = _rank_to_elo(getattr(home, 'ranking_fifa', 50) or 50)
    if elo_away is None:
        elo_away = _rank_to_elo(getattr(away, 'ranking_fifa', 50) or 50)

    # --- Expected goals (Elo como driver principal) ---
    xg_home = compute_xg(home, away, all_teams, home_fwd_mid_rating,
                         set_piece_index=home_spi, elo_att=elo_home, elo_def=elo_away)
    xg_away = compute_xg(away, home, all_teams, away_fwd_mid_rating,
                         set_piece_index=away_spi, elo_att=elo_away, elo_def=elo_home)

    # --- Altitude penalty/bonus based on venue ---
    try:
        from models.venue_model import altitude_xg_factor
        home_alt_f = altitude_xg_factor(venue, home.name)
        away_alt_f = altitude_xg_factor(venue, away.name)
        xg_home = float(np.clip(xg_home * home_alt_f, 0.2, 5.0))
        xg_away = float(np.clip(xg_away * away_alt_f, 0.2, 5.0))
    except Exception:
        pass  # venue model is non-critical

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

    # --- Calibracion venue neutral WC2026 ---
    # En un Mundial en cancha neutral no hay ventaja local real salvo para las sedes.
    # Corrige el sesgo detectado (+0.35 local, -0.10 visitante) en 12 partidos Sofascore.
    # Cancha neutral: reduce sesgo de "local" en DB. Sede conserva pequeña ventaja.
    if home.name not in _WC_HOST_TEAMS:
        xg_home = float(np.clip(xg_home * _NEUTRAL_SCALE_HOME, 0.2, 4.0))
    else:
        xg_home = float(np.clip(xg_home * _HOST_SCALE_HOME,    0.2, 4.0))
    xg_away = float(np.clip(xg_away, 0.2, 4.0))

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

    # --- Boost de empate en partidos parejos ---
    # Cuando |xG_h - xG_a| < umbral el modelo Poisson subestima empates.
    # Redistribuimos +_DRAW_BOOST_FACTOR desde victorias proporcional a sus probs.
    if abs(xg_home - xg_away) < _DRAW_BOOST_THRESHOLD:
        boost = _DRAW_BOOST_FACTOR * 100  # en puntos porcentuales
        total_wins = home_wins_pct + away_wins_pct
        if total_wins > 0:
            h_cut = boost * (home_wins_pct / total_wins)
            a_cut = boost * (away_wins_pct / total_wins)
            home_wins_pct = round(max(0, home_wins_pct - h_cut), 1)
            away_wins_pct = round(max(0, away_wins_pct - a_cut), 1)
            draws_pct     = round(min(100, draws_pct + boost), 1)

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

    # --- DNA matchup analysis ---
    try:
        from models.team_dna import get_team_dna, format_matchup_analysis
        h_dna = get_team_dna(home.name)
        a_dna = get_team_dna(away.name)
        if h_dna and a_dna:
            home_matchup_txt = format_matchup_analysis(home.name, away.name, h_dna, a_dna)
            away_matchup_txt = format_matchup_analysis(away.name, home.name, a_dna, h_dna)
        else:
            home_matchup_txt = away_matchup_txt = ""
    except Exception:
        home_matchup_txt = away_matchup_txt = ""

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
        "venue": venue,
        "home_set_piece_index": round(home_spi, 3),
        "away_set_piece_index": round(away_spi, 3),
        "home_matchup_analysis": home_matchup_txt,
        "away_matchup_analysis": away_matchup_txt,
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
