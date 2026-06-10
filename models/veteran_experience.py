"""
models/veteran_experience.py — Factor de experiencia mundialista para WC2026.

Calcula cuánta experiencia previa en Mundiales (WC2018 + WC2022, datos StatsBomb
cargados en match_players) tiene la plantilla oficial de 26 (wc26_squad) y el XI
proyectado (projected_lineups) de cada equipo.

Matching jugador↔historial en 3 niveles (por equipo, para evitar falsos positivos):
  1. player_id exacto (cuando match_players.player_id está poblado)
  2. Nombre exacto normalizado (sin acentos, lowercase)
  3. Tokens del nombre de plantilla ⊆ tokens del nombre StatsBomb
     (resuelve "Alexander Bah" ⊆ "Alexander Hartmann Bah")

Evidencia que motiva el factor:
  - Equipos con alta concentración de veteranos (England, Croatia, South Korea)
    gestionan mejor presión de torneo y penales.
  - Equipos sin veteranos (Czechia 0%) muestran inconsistencia en partidos
    decisivos: 0 goles vs defensas elite en eliminatorias 2025-26.

API:
    get_team_veteran_stats(conn, team_id, db_key) -> dict
    get_global_exp_mean(conn, db_key)             -> float (pivote)
    veteran_lambda_factor(exp_score, mean, stage) -> multiplicador λ (±4.5% cap)
    veteran_shootout_edge(exp_h, exp_a)           -> edge penales (±2.5pp cap)

Diseño conservador: acotado para sumar señal sin dominar los factores
principales (Elo, xG, forma). Mueve probabilidades ~2-5pp en los extremos.
"""

from __future__ import annotations
import math
import sqlite3
import logging
import unicodedata

log = logging.getLogger("veteran_experience")

# Recencia: WC2022 pesa el doble que WC2018 (plantilla más vigente)
SEASON_WEIGHT = {2022: 1.0, 2018: 0.5}

# Fallback del pivote si no se puede calcular la media global
DEFAULT_GLOBAL_MEAN = 0.15

# Sensibilidad del multiplicador λ por etapa (pendiente lineal sobre exp-mean).
# Calibrado para que el rango real de exp_score (0 a ~0.70, media ~0.22)
# produzca factores graduales: equipos top ~+3%, debutantes ~-1.5/-2.5%.
# group: experiencia pesa menos; knockout: pesa más (presión, penales).
STAGE_SENSITIVITY = {
    "group":    0.07,
    "knockout": 0.11,
}
LAMBDA_CAP = 0.045   # ±4.5% máximo sobre λ

_CACHE: dict = {}    # (db_key, team_id) -> stats ; (db_key, "_mean") -> float


# ── Normalización de nombres ──────────────────────────────────────────────────

def _norm(name: str) -> str:
    """lowercase + sin acentos + espacios colapsados."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("-", " ").split())


def _tokens(name: str) -> frozenset:
    return frozenset(t for t in _norm(name).split() if len(t) > 1)


# ── Experiencia por jugador ───────────────────────────────────────────────────

def _player_exp_weight(matches: int, season: int) -> float:
    """Experiencia de un jugador: log-saturante en partidos × recencia."""
    if matches <= 0:
        matches = 1
    return math.log1p(matches) / math.log1p(7) * SEASON_WEIGHT.get(season, 0.5)


def _wc_history_for_team(conn: sqlite3.Connection, team_id: int) -> list[dict]:
    """Historial WC2018/2022 del equipo: (player_id, player_name, season, matches)."""
    rows = conn.execute("""
        SELECT player_id, player_name, season,
               COUNT(DISTINCT fixture_api_id) AS wc_matches
        FROM match_players
        WHERE team_id = ? AND season IN (2018, 2022)
        GROUP BY player_id, player_name, season
    """, (team_id,)).fetchall()
    return [dict(r) for r in rows]


def _match_player_history(pid: int, pname: str, history: list[dict]) -> float:
    """
    Devuelve exp acumulada del jugador cruzando con el historial WC del equipo.
    Niveles: player_id exacto → nombre exacto → tokens subset.
    """
    exp = 0.0
    matched_seasons: set[int] = set()

    # Nivel 1: player_id
    for h in history:
        if h["player_id"] is not None and h["player_id"] == pid:
            exp += _player_exp_weight(h["wc_matches"], h["season"])
            matched_seasons.add(h["season"])

    p_norm = _norm(pname)
    p_tok = _tokens(pname)
    for h in history:
        if h["season"] in matched_seasons:
            continue
        h_name = h["player_name"] or ""
        # Nivel 2: nombre exacto normalizado
        if _norm(h_name) == p_norm:
            exp += _player_exp_weight(h["wc_matches"], h["season"])
            matched_seasons.add(h["season"])
            continue
        # Nivel 3: tokens de plantilla ⊆ tokens StatsBomb (nombres largos)
        h_tok = _tokens(h_name)
        if p_tok and len(p_tok) >= 2 and p_tok <= h_tok:
            exp += _player_exp_weight(h["wc_matches"], h["season"])
            matched_seasons.add(h["season"])

    return exp


# ── Cálculo por equipo ────────────────────────────────────────────────────────

def _squad_experience(conn: sqlite3.Connection, team_id: int) -> dict:
    """Cruza wc26_squad/projected_lineups con el historial WC del equipo."""
    squad = conn.execute("""
        SELECT ws.player_id, p.name,
               COALESCE(MAX(pl.is_starter), 0) AS is_starter
        FROM wc26_squad ws
        JOIN players p ON p.id = ws.player_id
        LEFT JOIN projected_lineups pl
               ON pl.player_id = ws.player_id AND pl.team_id = ws.team_id
        WHERE ws.team_id = ?
        GROUP BY ws.player_id, p.name
    """, (team_id,)).fetchall()

    if not squad:
        return {"squad_size": 0, "veterans": 0, "squad_vet_pct": 0.0,
                "xi_vet_pct": 0.0, "exp_score": 0.0}

    history = _wc_history_for_team(conn, team_id)

    per_player = []
    for r in squad:
        exp = _match_player_history(r["player_id"], r["name"], history) if history else 0.0
        per_player.append({
            "starter": bool(r["is_starter"]),
            "exp": min(1.0, exp),
            "vet": exp > 0.0,
        })

    squad_size = len(per_player)
    veterans = sum(1 for p in per_player if p["vet"])
    squad_vet_pct = veterans / squad_size
    squad_exp = sum(p["exp"] for p in per_player) / squad_size

    starters = [p for p in per_player if p["starter"]]
    if starters:
        xi_vet_pct = sum(1 for p in starters if p["vet"]) / len(starters)
        xi_exp = sum(p["exp"] for p in starters) / len(starters)
    else:
        xi_vet_pct = squad_vet_pct
        xi_exp = squad_exp

    # Score combinado: XI proyectado pesa más (son los que juegan)
    exp_score = 0.60 * xi_exp + 0.40 * squad_exp

    return {
        "squad_size": squad_size,
        "veterans": veterans,
        "squad_vet_pct": round(squad_vet_pct, 4),
        "xi_vet_pct": round(xi_vet_pct, 4),
        "exp_score": round(exp_score, 4),
    }


def get_team_veteran_stats(conn: sqlite3.Connection, team_id: int,
                           db_key: str = "default") -> dict:
    """Stats de experiencia mundialista, cacheadas por (db, team)."""
    key = (db_key, team_id)
    if key not in _CACHE:
        try:
            _CACHE[key] = _squad_experience(conn, team_id)
        except sqlite3.Error as e:
            log.warning("veteran stats failed for team %s: %s", team_id, e)
            _CACHE[key] = {"squad_size": 0, "veterans": 0, "squad_vet_pct": 0.0,
                           "xi_vet_pct": 0.0, "exp_score": 0.0}
    return _CACHE[key]


def get_global_exp_mean(conn: sqlite3.Connection, db_key: str = "default") -> float:
    """Media de exp_score entre todos los equipos con plantilla — pivote."""
    key = (db_key, "_mean")
    if key not in _CACHE:
        try:
            team_ids = [r[0] for r in conn.execute(
                "SELECT DISTINCT team_id FROM wc26_squad").fetchall()]
            scores = [get_team_veteran_stats(conn, tid, db_key)["exp_score"]
                      for tid in team_ids]
            scores = [s for s in scores if s is not None]
            _CACHE[key] = (sum(scores) / len(scores)) if scores else DEFAULT_GLOBAL_MEAN
        except sqlite3.Error:
            _CACHE[key] = DEFAULT_GLOBAL_MEAN
    return _CACHE[key]


# ── Factores para el modelo ───────────────────────────────────────────────────

def veteran_lambda_factor(exp_score: float, global_mean: float = DEFAULT_GLOBAL_MEAN,
                          stage: str = "group") -> float:
    """
    Multiplicador de λ por experiencia relativa a la media global.
    Acotado a ±LAMBDA_CAP. stage='knockout' aumenta la sensibilidad.
    """
    sens = STAGE_SENSITIVITY.get(stage, STAGE_SENSITIVITY["group"])
    delta = (exp_score - global_mean) * sens
    delta = max(-LAMBDA_CAP, min(LAMBDA_CAP, delta))
    return 1.0 + delta


def veteran_shootout_edge(exp_h: float, exp_a: float) -> float:
    """
    Edge de conversión en tanda de penales por diferencia de experiencia.
    Veteranos gestionan mejor la presión: hasta ±2.5pp de conversión.
    Devuelve el edge para el equipo local (negativo si visitante más veterano).
    """
    return max(-0.025, min(0.025, (exp_h - exp_a) * 0.08))


# Ajuste por presión vs elites: equipos SIN experiencia mundialista
# sub-convierten frente a rivales mucho más fuertes.
# Evidencia (eliminatorias 2025-26): Czechia (exp=0.00) generó 0.46-0.70 xG
# y 0 goles vs Denmark/Croatia, pero 2.00 xG y 2 goles vs Ireland.
# Equipos veteranos mantienen su output vs elites (Croatia, Morocco WC2022).
PRESSURE_ELO_GAP = 80.0     # gap de Elo a partir del cual aplica
PRESSURE_MAX_PEN = 0.030    # penalización máxima de λ: -3%


def pressure_adjustment(exp_score: float, global_mean: float,
                        own_elo: float, opp_elo: float) -> float:
    """
    Multiplicador λ extra cuando un equipo INEXPERTO enfrenta a un rival
    claramente superior (opp_elo - own_elo > PRESSURE_ELO_GAP).

    - exp_score >= media global → sin penalización (resisten la presión)
    - exp_score = 0 y gap grande → hasta -3% adicional
    Escala lineal en ambas dimensiones (déficit de experiencia × tamaño del gap).
    """
    gap = opp_elo - own_elo
    if gap <= PRESSURE_ELO_GAP:
        return 1.0
    exp_deficit = max(0.0, (global_mean - exp_score) / max(global_mean, 0.05))
    if exp_deficit <= 0:
        return 1.0
    gap_scale = min(1.0, (gap - PRESSURE_ELO_GAP) / 200.0)   # satura a gap=280
    pen = PRESSURE_MAX_PEN * exp_deficit * gap_scale
    return 1.0 - pen


def clear_cache() -> None:
    _CACHE.clear()


if __name__ == "__main__":
    from pathlib import Path
    db = Path(__file__).parent.parent / "data" / "mundial2026.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    mean = get_global_exp_mean(conn, str(db))
    print(f"Global exp_score mean: {mean:.4f}\n")
    for name in ("South Korea", "Czechia", "Croatia", "Denmark", "England",
                 "Argentina", "France", "Morocco", "Japan", "Haiti"):
        row = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
        if not row:
            print(f"{name}: NOT FOUND")
            continue
        s = get_team_veteran_stats(conn, row["id"], str(db))
        f_g = veteran_lambda_factor(s["exp_score"], mean, "group")
        f_k = veteran_lambda_factor(s["exp_score"], mean, "knockout")
        print(f"{name:<14} squad={s['squad_size']:>2} vets={s['veterans']:>2} "
              f"({s['squad_vet_pct']*100:4.1f}%) XI={s['xi_vet_pct']*100:5.1f}% "
              f"exp={s['exp_score']:.3f} λ_group={f_g:.4f} λ_ko={f_k:.4f}")
    conn.close()
