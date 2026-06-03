"""
models/goal_scorer.py — Modelo de probabilidad de goleador por jugador.

Dado el XI proyectado de un equipo y un número de goles, reparte esos goles
entre los jugadores según un "peso de definición" (finishing weight) que
combina las señales disponibles en la DB:

  goals_as_nat / caps   — ratio goleador histórico con la selección (señal #1)
  position              — FWD >> MID > DEF >> GK
  club goals (2024/25)  — forma goleadora reciente en el club
  market_value_m        — proxy de jerarquía ofensiva (cuando existe)

También identifica al lanzador de penaltis (penalty taker) y reparte
asistencias por separado usando xa/assists + caps de creadores.

API:
  scorer_weights(team_id)            -> [{name, position, weight, pen_taker}, ...]
  simulate_scorers(team_id, n_goals) -> [names]  (un sorteo)
  expected_scorer_table(team_id)     -> [{name, goals_share, prob_anytime}, ...]
"""
from __future__ import annotations
import sqlite3
import random
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Peso base por posición (cuánto contribuye a marcar)
POS_GOAL_WEIGHT = {"FWD": 1.00, "MID": 0.45, "DEF": 0.14, "GK": 0.004}
# Fracción de goles de un equipo que llegan por asistencia (resto: jugadas individuales/BP)
ASSIST_FRACTION = 0.74


def _xi(conn, team_id: int) -> list[dict]:
    """XI titular con métricas ofensivas; cae a squad_selections si no hay XI."""
    rows = conn.execute("""
        SELECT p.id, p.name, p.position, p.caps, p.goals_as_nat,
               p.market_value_m,
               pcs.goals AS club_goals, pcs.assists AS club_assists,
               pcs.minutes AS club_minutes, pcs.xg, pcs.xa
        FROM projected_lineups pl
        JOIN players p ON p.id = pl.player_id
        LEFT JOIN player_club_stats pcs
               ON pcs.player_id = pl.player_id AND pcs.season = '2024/25'
        WHERE pl.team_id = ? AND pl.is_starter = 1
    """, (team_id,)).fetchall()

    if not rows:
        rows = conn.execute("""
            SELECT p.id, p.name, p.position, p.caps, p.goals_as_nat,
                   p.market_value_m,
                   pcs.goals AS club_goals, pcs.assists AS club_assists,
                   pcs.minutes AS club_minutes, pcs.xg, pcs.xa
            FROM squad_selections ss
            JOIN players p ON p.id = ss.player_id
            LEFT JOIN player_club_stats pcs
                   ON pcs.player_id = ss.player_id AND pcs.season = '2024/25'
            WHERE ss.team_id = ?
            ORDER BY p.caps DESC LIMIT 11
        """, (team_id,)).fetchall()

    return [dict(r) for r in rows]


def _finishing_weight(p: dict) -> float:
    """Peso de definición combinando ratio nacional, posición y forma de club."""
    pos = (p.get("position") or "MID").upper()
    pos_w = POS_GOAL_WEIGHT.get(pos, 0.40)

    caps = p.get("caps") or 0
    nat_goals = p.get("goals_as_nat") or 0
    # Ratio goleador nacional (regularizado para muestras chicas)
    nat_rate = nat_goals / (caps + 8) if caps else 0.0

    # Forma de club: goles por 90' (si hay minutos)
    club_goals = p.get("club_goals") or 0
    club_min = p.get("club_minutes") or 0
    club_per90 = (club_goals / club_min * 90) if club_min and club_min > 300 else 0.0

    # Combinar: la señal nacional manda; club y posición complementan
    raw = (
        pos_w
        * (0.55 + 6.0 * nat_rate + 1.4 * club_per90)
    )
    # Jerarquía por valor de mercado (cuando existe) — leve empujón
    mv = p.get("market_value_m") or 0
    if mv:
        raw *= 1.0 + min(0.25, mv / 600.0)

    return max(0.001, raw)


def _assist_weight(p: dict) -> float:
    """Peso de asistencia: creadores (MID/FWD) con xa/assists altos."""
    pos = (p.get("position") or "MID").upper()
    base = {"MID": 1.0, "FWD": 0.85, "DEF": 0.45, "GK": 0.02}.get(pos, 0.6)
    club_assists = p.get("club_assists") or 0
    club_min = p.get("club_minutes") or 0
    a_per90 = (club_assists / club_min * 90) if club_min and club_min > 300 else 0.0
    caps = p.get("caps") or 0
    return max(0.001, base * (0.6 + 4.0 * a_per90 + 0.004 * caps))


def _norm(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _bench(conn, team_id: int, exclude_ids: set[int] | None = None) -> list[dict]:
    """Jugadores del banco (squad_selections no en projected_lineups)."""
    rows = conn.execute("""
        SELECT p.id, p.name, p.position, p.caps, p.goals_as_nat,
               p.market_value_m,
               pcs.goals AS club_goals, pcs.assists AS club_assists,
               pcs.minutes AS club_minutes, pcs.xg, pcs.xa
        FROM squad_selections ss
        JOIN players p ON p.id = ss.player_id
        LEFT JOIN player_club_stats pcs
               ON pcs.player_id = ss.player_id AND pcs.season = '2024/25'
        WHERE ss.team_id = ?
          AND ss.player_id NOT IN (
              SELECT player_id FROM projected_lineups
              WHERE team_id = ? AND is_starter = 1
          )
        ORDER BY p.caps DESC LIMIT 12
    """, (team_id, team_id)).fetchall()
    bench = [dict(r) for r in rows]
    if exclude_ids:
        bench = [p for p in bench if p["id"] not in exclude_ids]
    return bench


def scorer_weights(team_id: int, db_path=DB_PATH,
                   exclude: list[str] | None = None,
                   minutes_played: dict[str, float] | None = None) -> list[dict]:
    """Lista de jugadores del XI con su peso de gol normalizado + flag pen_taker.

    exclude: nombres de jugadores ausentes (lesión/suspensión) a omitir.
    minutes_played: {player_name: minutos} para escalar peso por participación.
                    Si None, se asume 90 min para todos (sin cambios).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    xi = _xi(conn, team_id)
    conn.close()
    if exclude:
        ex = {_norm(e) for e in exclude}
        xi = [p for p in xi if not any(e in _norm(p["name"]) or _norm(p["name"]) in e
                                       for e in ex)]
    if not xi:
        return []

    weights = [_finishing_weight(p) for p in xi]

    # Escalar peso por minutos jugados (si se provee)
    if minutes_played:
        weights = [
            w * min(minutes_played.get(p["name"], 90.0), 90.0) / 90.0
            for w, p in zip(weights, xi)
        ]

    total = sum(weights) or 1.0

    # Penalty taker: mejor finisher entre FWD/MID con buen ratio nacional
    pen_idx = max(
        range(len(xi)),
        key=lambda i: (
            (xi[i].get("goals_as_nat") or 0) / ((xi[i].get("caps") or 0) + 6)
            + (0.15 if (xi[i].get("position") or "") in ("FWD", "MID") else 0)
        ),
    )

    out = []
    for i, p in enumerate(xi):
        out.append({
            "player_id": p["id"],
            "name": p["name"],
            "position": p.get("position") or "?",
            "weight": round(weights[i] / total, 4),
            "raw_weight": weights[i],
            "pen_taker": (i == pen_idx),
            "nat_goals": p.get("goals_as_nat") or 0,
            "caps": p.get("caps") or 0,
            "minutes": minutes_played.get(p["name"], 90.0) if minutes_played else 90.0,
        })
    out.sort(key=lambda x: -x["weight"])
    return out


def build_squad_with_subs(team_id: int, db_path=DB_PATH,
                           exclude: list[str] | None = None,
                           n_subs: int | None = None,
                           rng: random.Random | None = None,
                           sub_pattern=None) -> tuple[list[dict], dict[str, float]]:
    """
    Construye el plantel completo (titulares + suplentes que entran) y retorna:
      - players: lista de dicts con datos de todos los que participan
      - minutes: {player_name: minutos_jugados}

    Usa patrones históricos reales del equipo (sub_pattern de team_stats_analyzer)
    para determinar cuántos cambios hacer, en qué minutos y qué posiciones entran.
    Si no se provee sub_pattern, usa defaults genéricos.
    """
    import math as _math
    r = rng or random.Random()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    starters = _xi(conn, team_id)

    # Filtrar ausentes
    if exclude:
        ex = {_norm(e) for e in exclude}
        starters = [p for p in starters if not any(
            e in _norm(p["name"]) or _norm(p["name"]) in e for e in ex)]

    starter_ids = {p["id"] for p in starters}
    bench = _bench(conn, team_id, exclude_ids=starter_ids)

    if exclude:
        ex = {_norm(e) for e in exclude}
        bench = [p for p in bench if not any(
            e in _norm(p["name"]) or _norm(p["name"]) in e for e in ex)]

    conn.close()

    # ── Número de sustituciones desde patrón histórico ────────────────────────
    if n_subs is not None:
        num_subs = n_subs
    elif sub_pattern is not None:
        mean = sub_pattern.subs_per_game_mean
        std  = sub_pattern.subs_per_game_std
        # Muestrear número de subs: distribución discreta alrededor de la media
        raw = int(round(r.gauss(mean, std)))
        num_subs = max(1, min(5, raw))
    else:
        num_subs = r.choices([2, 3, 3, 4], k=1)[0]

    num_subs = min(num_subs, len(bench), len(starters) - 1)
    if num_subs <= 0:
        # Sin cambios: todos juegan 90'
        return starters, {p["name"]: 90.0 for p in starters}

    # ── Minutos de ingreso desde patrones históricos (oleadas reales) ─────────
    if sub_pattern and sub_pattern.slots:
        slots = sub_pattern.slots
        # Tomar num_subs slots (con repetición si hay menos slots que subs)
        selected_slots = []
        for i in range(num_subs):
            slot = slots[min(i, len(slots) - 1)]
            mu, sigma = slot.entry_min_mean, slot.entry_min_std
            raw_min = r.gauss(mu, sigma)
            entry_min = max(45.0, min(88.0, raw_min))
            selected_slots.append(round(entry_min))
        sub_minutes = sorted(selected_slots)
        # Asegurar que no hay dos cambios en el mismo minuto exacto
        for i in range(1, len(sub_minutes)):
            if sub_minutes[i] <= sub_minutes[i-1]:
                sub_minutes[i] = sub_minutes[i-1] + 1
    else:
        # Sin patrón: distribución empírica global (mitad, ~62', ~73')
        base_slots = [54, 63, 73, 78, 82]
        raw_slots = [base_slots[i] + r.randint(-5, 5) for i in range(num_subs)]
        sub_minutes = sorted(max(45, min(88, m)) for m in raw_slots)

    # ── Selección de qué titulares salen ──────────────────────────────────────
    # Lógica mejorada: la posición del suplente que entra determina al que sale
    # - Los defensas salen menos (a menos que vaya perdiendo)
    # - Los mediocentros son los más sustituidos
    # - Delanteros entran con más frecuencia en la 2ª parte
    non_gk_starters = [p for p in starters if (p.get("position") or "").upper() != "GK"]
    # Peso de ser sustituido: inverso del finishing_weight (los más peligrosos salen menos)
    fw_vals = [_finishing_weight(p) for p in non_gk_starters]
    max_fw = max(fw_vals) if fw_vals else 1.0
    # Probabilidad de ser sustituido: más alta para DEF/MID de menor impacto ofensivo
    sub_out_weights = []
    for p, fw in zip(non_gk_starters, fw_vals):
        pos = (p.get("position") or "MID").upper()
        # DEF tienen 0.6x la prob de salir vs MID, FWD estrella (alto fw) sale menos
        pos_factor = {"DEF": 0.7, "MID": 1.2, "FWD": 0.9}.get(pos, 1.0)
        w = pos_factor * (1.0 - 0.6 * (fw / max_fw))
        sub_out_weights.append(max(0.05, w))

    # Seleccionar sin reemplazo
    subs_out_indices = []
    available = list(range(len(non_gk_starters)))
    remaining_weights = sub_out_weights.copy()
    for _ in range(min(num_subs, len(available))):
        if not available:
            break
        total_w = sum(remaining_weights[i] for i in available)
        probs = [remaining_weights[i] / total_w for i in available]
        chosen_idx = r.choices(available, weights=probs, k=1)[0]
        subs_out_indices.append(chosen_idx)
        available.remove(chosen_idx)

    subs_out = [non_gk_starters[i] for i in subs_out_indices]
    subs_out_ids = {p["id"] for p in subs_out}

    # Suplentes que entran: preferir jugadores con historial de suplente en ese slot
    # Para simplificar la simulación Monte Carlo, usamos los primeros del banco
    # (ordenados por caps DESC desde _bench, que son los más relevantes)
    subs_in = bench[:num_subs]

    # ── Calcular minutos jugados ───────────────────────────────────────────────
    minutes: dict[str, float] = {}
    for p in starters:
        if p["id"] in subs_out_ids:
            idx_in_list = [i for i, s in enumerate(subs_out) if s["id"] == p["id"]][0]
            minutes[p["name"]] = float(sub_minutes[idx_in_list])
        else:
            minutes[p["name"]] = 90.0

    for i, p in enumerate(subs_in):
        # Minutos del suplente = 90 - minuto de entrada + pequeño boost por impacto
        # Los suplentes frescos tienden a ser más activos por minuto → SUB_GOAL_BOOST
        played = 90.0 - sub_minutes[i]
        minutes[p["name"]] = max(1.0, played)

    remaining_starters = [p for p in starters if p["id"] not in subs_out_ids]
    all_players = remaining_starters + subs_in

    return all_players, minutes


def _assist_weights(team_id: int, db_path=DB_PATH) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    xi = _xi(conn, team_id)
    conn.close()
    if not xi:
        return []
    aw = [_assist_weight(p) for p in xi]
    total = sum(aw) or 1.0
    return [{"name": p["name"], "position": p.get("position") or "?",
             "weight": aw[i] / total} for i, p in enumerate(xi)]


def simulate_scorers(team_id: int, n_goals: int,
                     pen_goals: int = 0, db_path=DB_PATH) -> list[str]:
    """
    Sortea quién marca los n_goals de un equipo en un partido.
    pen_goals de ellos se asignan al lanzador de penaltis.
    """
    if n_goals <= 0:
        return []
    weights = scorer_weights(team_id, db_path)
    if not weights:
        return ["?"] * n_goals

    names = [w["name"] for w in weights]
    probs = [w["weight"] for w in weights]
    pen_taker = next((w["name"] for w in weights if w["pen_taker"]), names[0])

    scorers = []
    for g in range(n_goals):
        if g < pen_goals:
            scorers.append(pen_taker)
        else:
            scorers.append(random.choices(names, weights=probs, k=1)[0])
    return scorers


def expected_scorer_table(team_id: int, lam: float = 1.5,
                          db_path=DB_PATH, top: int = 8) -> list[dict]:
    """
    Tabla de goleadores esperados dado λ (goles esperados del equipo):
      goals_share   — fracción de los goles del equipo que marca el jugador
      exp_goals     — goles esperados del jugador en el partido (share * λ)
      prob_anytime  — P(marca al menos 1) ≈ 1 - exp(-exp_goals)
    """
    import math
    weights = scorer_weights(team_id, db_path)
    out = []
    for w in weights[:top]:
        exp_g = w["weight"] * lam
        out.append({
            "name": w["name"],
            "position": w["position"],
            "goals_share": round(w["weight"] * 100, 1),
            "exp_goals": round(exp_g, 3),
            "prob_anytime": round((1 - math.exp(-exp_g)) * 100, 1),
            "pen_taker": w["pen_taker"],
        })
    return out


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    tid = lambda n: conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()[0]
    for team in ["Brazil", "Argentina", "France", "Panama"]:
        try:
            t = tid(team)
        except Exception:
            continue
        print(f"\n{'='*60}")
        print(f"  GOLEADORES ESPERADOS — {team}  (λ=1.8)")
        print(f"{'='*60}")
        print(f"  {'Jugador':<22}{'Pos':<5}{'%goles':>8}{'P(marca)':>10}  Pen")
        print(f"  {'-'*56}")
        for s in expected_scorer_table(t, lam=1.8):
            pen = "⚽PK" if s["pen_taker"] else ""
            print(f"  {s['name'][:21]:<22}{s['position']:<5}"
                  f"{s['goals_share']:>7.1f}%{s['prob_anytime']:>9.1f}%  {pen}")
    conn.close()
