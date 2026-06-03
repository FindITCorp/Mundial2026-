"""
models/team_stats_analyzer.py — Análisis estadístico histórico de selecciones.

Extrae de la base de datos patrones reales de:
  • Sustituciones: cuántas, en qué minuto, qué posición, qué jugadores
  • Estadísticas de partido: tiros, tiros al arco (a favor y en contra),
    posesión, faltas, tarjetas, córners (estimados)
  • Goles en balones parados (estimados vía fracción histórica por estilo)
  • Rendimiento goleador de suplentes históricos

API principal:
  get_team_profile(team_id, db_path)   → TeamProfile (dataclass)
  get_sub_pattern(team_id, db_path)    → SubPattern (para build_squad_with_subs)
  format_team_profile(profile)         → str (para CLI/reports)
"""
from __future__ import annotations
import sqlite3
import math
from pathlib import Path
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# ─── Defaults globales (si no hay datos del equipo) ───────────────────────────
DEFAULT_SUBS_PER_GAME    = 3.5
DEFAULT_ENTRY_MIN_MID    = 62.0   # minuto promedio de ingreso de MID
DEFAULT_ENTRY_MIN_FWD    = 65.0
DEFAULT_ENTRY_MIN_DEF    = 68.0
DEFAULT_SET_PIECE_FRAC   = 0.30   # fracción de goles desde balones parados
SUB_GOAL_BOOST           = 1.20   # los suplentes marcan ~20% más goles/min que titulares

# Fracción de sustituciones por posición (normalizada, promedio histórico)
DEFAULT_POS_DIST = {"MID": 0.55, "FWD": 0.31, "DEF": 0.14}

# Equipos conocidos por jugar con muchos suplentes ofensivos
OFFENSIVE_SUB_TEAMS = {"Spain", "Germany", "Netherlands", "Portugal"}
DEFENSIVE_SUB_TEAMS = {"Morocco", "Argentina", "Italy", "Iran"}


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SubSlot:
    """Un slot de sustitución: cuándo y qué posición entra."""
    entry_min_mean: float          # minuto promedio de ingreso
    entry_min_std: float           # dispersión
    position_prefs: dict           # {"MID": 0.55, "FWD": 0.31, "DEF": 0.14}
    frequent_subs: list[dict]      # [{"player_id", "name", "position", "apps", "goals_as_sub"}]


@dataclass
class SubPattern:
    """Patrón de sustituciones de un equipo basado en datos históricos."""
    team_name: str
    n_matches_analyzed: int
    subs_per_game_mean: float
    subs_per_game_std: float
    # Slots representativos (3-5 cambios posibles, ordenados por minuto)
    slots: list[SubSlot]
    # Jugadores históricos que tienden a entrar como suplentes (pueden ya no estar)
    sub_candidates: list[dict]     # con campo "current_squad": bool
    data_source: str               # "historical" | "default"


@dataclass
class MatchStatsProfile:
    """Estadísticas promedio de partido extraídas del historial."""
    n_matches: int
    # Tiros
    sot_for_pg: float              # tiros al arco a favor / partido
    sot_against_pg: float          # tiros al arco en contra / partido
    shots_for_pg: float            # estimado (SoT / 0.37)
    shots_against_pg: float
    # Goles
    gf_pg: float                   # goles a favor / partido
    ga_pg: float                   # goles en contra / partido
    clean_sheet_rate: float        # % partidos sin gol recibido
    # Balones parados (estimados)
    set_piece_goals_for_pg: float  # goles en BP a favor
    set_piece_goals_against_pg: float
    set_piece_frac_for: float      # fracción de goles desde BP
    # Córners (estimados desde goles y posesión)
    est_corners_for_pg: float
    est_corners_against_pg: float
    # Tarjetas y faltas (de team_tactics)
    yellow_cards_pg: float
    fouls_pg: float
    # Posesión
    possession_pct: float
    # Regularidad ofensiva
    scored_in_pct: float           # % partidos donde marcaron
    conceded_in_pct: float         # % partidos donde recibieron gol
    win_rate: float
    draw_rate: float
    loss_rate: float
    # Contexto
    competitions_sampled: list[str]


@dataclass
class TeamProfile:
    team_id: int
    team_name: str
    sub_pattern: SubPattern
    match_stats: MatchStatsProfile
    # Jugadores actuales en plantilla (para cruzar con histórico)
    current_squad: list[dict]      # [{id, name, position}]


# ─── Funciones de extracción ──────────────────────────────────────────────────

def _conn(db_path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def _sub_pattern(conn, team_id: int, team_name: str) -> SubPattern:
    """Extrae patrón de sustituciones desde match_players y player_nat_stats."""

    # ── 1. Sustituciones desde match_players (datos WC2022) ───────────────────
    # Suplentes que entraron
    subs_in = conn.execute("""
        SELECT position, minutes_played, player_id, player_name
        FROM match_players
        WHERE team_id=? AND started=0 AND minutes_played > 0
        ORDER BY player_id
    """, (team_id,)).fetchall()

    # Partidos jugados (distintos fixtures)
    n_fixtures = conn.execute("""
        SELECT COUNT(DISTINCT fixture_api_id) FROM match_players WHERE team_id=?
    """, (team_id,)).fetchone()[0] or 0

    # ── 2. Suplentes desde player_nat_stats (más amplio) ─────────────────────
    nat_subs = conn.execute("""
        SELECT pns.player_id, p.name, p.position,
               COUNT(*) apps, SUM(pns.goals) goals,
               AVG(pns.minutes) avg_min, SUM(pns.assists) assists
        FROM player_nat_stats pns
        JOIN players p ON p.id=pns.player_id
        WHERE pns.player_id IN (
            SELECT player_id FROM squad_selections WHERE team_id=?
            UNION
            SELECT player_id FROM match_players WHERE team_id=?
        )
        AND pns.was_starter=0 AND pns.minutes > 0
        GROUP BY pns.player_id
        HAVING apps >= 2
        ORDER BY goals DESC, apps DESC
    """, (team_id, team_id)).fetchall()

    # Plantilla actual del equipo (para saber si el jugador histórico sigue)
    squad_ids = {r[0] for r in conn.execute(
        "SELECT player_id FROM squad_selections WHERE team_id=?", (team_id,)
    ).fetchall()}

    sub_candidates = []
    for r in nat_subs:
        sub_candidates.append({
            "player_id": r["player_id"],
            "name": r["name"],
            "position": r["position"] or "MID",
            "apps_as_sub": r["apps"],
            "goals_as_sub": r["goals"] or 0,
            "assists_as_sub": r["assists"] or 0,
            "avg_min_played": round(r["avg_min"], 1),
            "current_squad": r["player_id"] in squad_ids,
            # Minuto estimado de ingreso = 90 - avg_min
            "avg_entry_min": round(max(45.0, 90.0 - (r["avg_min"] or 30.0)), 1),
        })

    # ── 3. Calcular distribución de sustituciones ─────────────────────────────
    if n_fixtures >= 3 and subs_in:
        subs_per_game = len(subs_in) / n_fixtures

        # Minuto de ingreso estimado por posición desde match_players
        entry_by_pos: dict[str, list] = {}
        for r in subs_in:
            pos = (r["position"] or "MID").upper()
            # entry_min = 90 - minutes_played (aprox para partidos de 90')
            mp = r["minutes_played"] or 0
            entry_min = max(45.0, min(88.0, 90.0 - mp))
            entry_by_pos.setdefault(pos, []).append(entry_min)

        # Distribución de posiciones sustituidas
        pos_counts = {pos: len(mins) for pos, mins in entry_by_pos.items()}
        total_sub_pos = sum(pos_counts.values()) or 1
        pos_dist = {pos: cnt / total_sub_pos for pos, cnt in pos_counts.items()}

        # Fallback a defaults si faltan posiciones
        for pos, default_frac in DEFAULT_POS_DIST.items():
            if pos not in pos_dist:
                pos_dist[pos] = default_frac

        # Slots representativos (3 oleadas típicas)
        def _slot_stats(entries):
            if not entries:
                return 60.0, 10.0
            mean = sum(entries) / len(entries)
            std = math.sqrt(sum((x - mean)**2 for x in entries) / len(entries)) if len(entries) > 1 else 8.0
            return round(mean, 1), round(max(3.0, std), 1)

        # Separar en oleadas: early (<60'), mid (60-72'), late (>72')
        all_entries = [90.0 - (r["minutes_played"] or 0) for r in subs_in
                       if (r["minutes_played"] or 0) > 0]
        early  = [e for e in all_entries if e < 60]
        mid    = [e for e in all_entries if 60 <= e < 73]
        late   = [e for e in all_entries if e >= 73]

        slots = []
        if early:
            m, s = _slot_stats(early)
            slots.append(SubSlot(entry_min_mean=m, entry_min_std=s,
                                  position_prefs=pos_dist,
                                  frequent_subs=[c for c in sub_candidates
                                                 if abs(c["avg_entry_min"] - m) < 15][:3]))
        if mid:
            m, s = _slot_stats(mid)
            slots.append(SubSlot(entry_min_mean=m, entry_min_std=s,
                                  position_prefs={**pos_dist, "FWD": pos_dist.get("FWD", 0.3) * 1.2},
                                  frequent_subs=[c for c in sub_candidates
                                                 if abs(c["avg_entry_min"] - m) < 12][:3]))
        if late:
            m, s = _slot_stats(late)
            slots.append(SubSlot(entry_min_mean=m, entry_min_std=s,
                                  position_prefs={**pos_dist, "FWD": pos_dist.get("FWD", 0.3) * 1.3},
                                  frequent_subs=[c for c in sub_candidates
                                                 if c["avg_entry_min"] >= 70][:3]))

        if not slots:
            slots = _default_slots(sub_candidates)

        data_source = "historical"
    else:
        subs_per_game = DEFAULT_SUBS_PER_GAME
        slots = _default_slots(sub_candidates)
        data_source = "default"
        n_fixtures = max(n_fixtures, 0)

    # Ajuste según estilo conocido del equipo
    if team_name in OFFENSIVE_SUB_TEAMS:
        subs_per_game = min(5.0, subs_per_game * 1.1)
    elif team_name in DEFENSIVE_SUB_TEAMS:
        subs_per_game = max(2.0, subs_per_game * 0.9)

    import statistics as _stats
    # Varianza de subs/game desde match_players por fixture
    per_fixture = {}
    for r in subs_in:
        per_fixture.setdefault(r["fixture_api_id"] if hasattr(r, "fixture_api_id") else 0, 0)

    subs_std = 0.8  # default si no hay varianza calculable

    return SubPattern(
        team_name=team_name,
        n_matches_analyzed=n_fixtures,
        subs_per_game_mean=round(subs_per_game, 2),
        subs_per_game_std=subs_std,
        slots=slots,
        sub_candidates=sub_candidates,
        data_source=data_source,
    )


def _default_slots(sub_candidates: list[dict]) -> list[SubSlot]:
    """Slots por defecto basados en promedios históricos globales."""
    pos_dist = DEFAULT_POS_DIST.copy()
    return [
        SubSlot(entry_min_mean=54.0, entry_min_std=8.0, position_prefs=pos_dist,
                frequent_subs=[c for c in sub_candidates if c["avg_entry_min"] < 62][:3]),
        SubSlot(entry_min_mean=64.0, entry_min_std=6.0, position_prefs={**pos_dist, "FWD": 0.38},
                frequent_subs=[c for c in sub_candidates if 62 <= c["avg_entry_min"] < 73][:3]),
        SubSlot(entry_min_mean=73.0, entry_min_std=5.0, position_prefs={**pos_dist, "FWD": 0.45},
                frequent_subs=[c for c in sub_candidates if c["avg_entry_min"] >= 73][:3]),
    ]


def _match_stats_profile(conn, team_id: int) -> MatchStatsProfile:
    """Extrae estadísticas de partido desde match_players y team_matches."""

    # ── SoT for/against desde match_players ───────────────────────────────────
    sot_row = conn.execute("""
        WITH per_fixture AS (
            SELECT fixture_api_id, team_id,
                   SUM(shots_on) as sot, SUM(goals) as goals_mp
            FROM match_players GROUP BY fixture_api_id, team_id
        ),
        joined AS (
            SELECT a.team_id, a.sot as sot_for, b.sot as sot_against,
                   a.goals_mp as gf_mp, b.goals_mp as ga_mp
            FROM per_fixture a
            JOIN per_fixture b
                ON b.fixture_api_id=a.fixture_api_id AND b.team_id!=a.team_id
            WHERE a.team_id=?
        )
        SELECT COUNT(*) n_mp, AVG(sot_for) sot_for, AVG(sot_against) sot_against,
               AVG(gf_mp) gf_mp, AVG(ga_mp) ga_mp
        FROM joined
    """, (team_id,)).fetchone()

    # ── Estadísticas amplias desde team_matches (últimos 3 años, sin amistosos) ─
    tm_row = conn.execute("""
        SELECT COUNT(*) n_tm,
               AVG(goals_for) avg_gf,
               AVG(goals_against) avg_ga,
               1.0*SUM(CASE WHEN goals_against=0 THEN 1 ELSE 0 END)/COUNT(*) cs_rate,
               1.0*SUM(CASE WHEN goals_for > 0 THEN 1 ELSE 0 END)/COUNT(*) scored_rate,
               1.0*SUM(CASE WHEN goals_against > 0 THEN 1 ELSE 0 END)/COUNT(*) conceded_rate,
               1.0*SUM(CASE WHEN result='W' THEN 1 ELSE 0 END)/COUNT(*) win_rate,
               1.0*SUM(CASE WHEN result='D' THEN 1 ELSE 0 END)/COUNT(*) draw_rate,
               1.0*SUM(CASE WHEN result='L' THEN 1 ELSE 0 END)/COUNT(*) loss_rate
        FROM team_matches
        WHERE team_id=? AND date >= '2022-01-01'
            AND goals_for IS NOT NULL
            AND competition NOT IN ('Friendly')
    """, (team_id,)).fetchone()

    # Fallback con amistosos si pocos datos
    if (tm_row["n_tm"] or 0) < 10:
        tm_row = conn.execute("""
            SELECT COUNT(*) n_tm,
                   AVG(goals_for) avg_gf, AVG(goals_against) avg_ga,
                   1.0*SUM(CASE WHEN goals_against=0 THEN 1 ELSE 0 END)/COUNT(*) cs_rate,
                   1.0*SUM(CASE WHEN goals_for > 0 THEN 1 ELSE 0 END)/COUNT(*) scored_rate,
                   1.0*SUM(CASE WHEN goals_against > 0 THEN 1 ELSE 0 END)/COUNT(*) conceded_rate,
                   1.0*SUM(CASE WHEN result='W' THEN 1 ELSE 0 END)/COUNT(*) win_rate,
                   1.0*SUM(CASE WHEN result='D' THEN 1 ELSE 0 END)/COUNT(*) draw_rate,
                   1.0*SUM(CASE WHEN result='L' THEN 1 ELSE 0 END)/COUNT(*) loss_rate
            FROM team_matches
            WHERE team_id=? AND date >= '2021-01-01' AND goals_for IS NOT NULL
        """, (team_id,)).fetchone()

    # Competiciones muestreadas
    comp_rows = conn.execute("""
        SELECT DISTINCT competition FROM team_matches
        WHERE team_id=? AND date >= '2022-01-01'
        ORDER BY competition LIMIT 6
    """, (team_id,)).fetchall()
    competitions = [r[0] for r in comp_rows]

    # ── Tácticas para posesión y faltas ───────────────────────────────────────
    tac_row = conn.execute(
        "SELECT pressing_intensity FROM team_tactics WHERE team_id=?", (team_id,)
    ).fetchone()
    pressing = (tac_row["pressing_intensity"] if tac_row else 0.5) or 0.5

    # ── Derivar métricas ───────────────────────────────────────────────────────
    n_mp = sot_row["n_mp"] or 0
    sot_for    = sot_row["sot_for"]    or 4.0
    sot_against = sot_row["sot_against"] or 3.5
    SOT_RATIO  = 0.37   # SoT / total shots

    gf = tm_row["avg_gf"]    or 1.3
    ga = tm_row["avg_ga"]    or 1.2
    cs = tm_row["cs_rate"]   or 0.30

    # Goles desde balones parados:
    # Media histórica ~30% en Copa del Mundo; equipos con mucho pressing defensivo tienden a
    # conceder más goles en BP (corners y faltas cerca del área)
    sp_frac_for     = min(0.45, 0.28 + (1.0 - pressing) * 0.10)
    sp_frac_against = min(0.50, 0.28 + pressing * 0.12)
    sp_goals_for    = round(gf * sp_frac_for, 3)
    sp_goals_against = round(ga * sp_frac_against, 3)

    # Córners estimados: ~1 córner por SoT + 1.5 base (equipos que generan más tiros generan más córners)
    est_corners_for     = round(1.5 + sot_for * 0.65, 2)
    est_corners_against = round(1.5 + sot_against * 0.65, 2)

    # Posesión estimada desde pressing (mayor pressing → más posesión)
    possession = round(45.0 + pressing * 15.0, 1)
    possession = max(35.0, min(65.0, possession))

    # Faltas y amarillas desde pressing y estilo defensivo
    fouls_pg        = round(9.0 + pressing * 5.0, 1)
    yellow_cards_pg = round(1.5 + pressing * 1.5, 1)

    # Datos de SoT de match_players priorizados si hay suficientes partidos
    use_sot = n_mp >= 5

    return MatchStatsProfile(
        n_matches=tm_row["n_tm"] or 0,
        sot_for_pg=round(sot_for, 2) if use_sot else round(gf / 0.20, 2),
        sot_against_pg=round(sot_against, 2) if use_sot else round(ga / 0.22, 2),
        shots_for_pg=round((sot_for if use_sot else gf / 0.20) / SOT_RATIO, 1),
        shots_against_pg=round((sot_against if use_sot else ga / 0.22) / SOT_RATIO, 1),
        gf_pg=round(gf, 3),
        ga_pg=round(ga, 3),
        clean_sheet_rate=round(cs, 3),
        set_piece_goals_for_pg=sp_goals_for,
        set_piece_goals_against_pg=sp_goals_against,
        set_piece_frac_for=round(sp_frac_for, 3),
        est_corners_for_pg=est_corners_for,
        est_corners_against_pg=est_corners_against,
        yellow_cards_pg=yellow_cards_pg,
        fouls_pg=fouls_pg,
        possession_pct=possession,
        scored_in_pct=round((tm_row["scored_rate"] or 0.75) * 100, 1),
        conceded_in_pct=round((tm_row["conceded_rate"] or 0.65) * 100, 1),
        win_rate=round((tm_row["win_rate"] or 0.4) * 100, 1),
        draw_rate=round((tm_row["draw_rate"] or 0.25) * 100, 1),
        loss_rate=round((tm_row["loss_rate"] or 0.35) * 100, 1),
        competitions_sampled=competitions,
    )


def _current_squad(conn, team_id: int) -> list[dict]:
    rows = conn.execute("""
        SELECT p.id, p.name, p.position, p.caps, p.goals_as_nat
        FROM squad_selections ss
        JOIN players p ON p.id=ss.player_id
        WHERE ss.team_id=?
        ORDER BY p.caps DESC
    """, (team_id,)).fetchall()
    return [dict(r) for r in rows]


# ─── API pública ───────────────────────────────────────────────────────────────

def get_team_profile(team_id: int, db_path=DB_PATH) -> TeamProfile:
    """Construye el perfil completo de un equipo desde datos históricos."""
    conn = _conn(db_path)
    try:
        name_row = conn.execute(
            "SELECT name FROM teams WHERE id=?", (team_id,)
        ).fetchone()
        team_name = name_row["name"] if name_row else f"Team#{team_id}"

        sub_pat = _sub_pattern(conn, team_id, team_name)
        match_stats = _match_stats_profile(conn, team_id)
        squad = _current_squad(conn, team_id)
    finally:
        conn.close()

    return TeamProfile(
        team_id=team_id,
        team_name=team_name,
        sub_pattern=sub_pat,
        match_stats=match_stats,
        current_squad=squad,
    )


def get_sub_pattern(team_id: int, db_path=DB_PATH) -> SubPattern:
    """Atajo para obtener solo el patrón de sustituciones."""
    conn = _conn(db_path)
    try:
        name_row = conn.execute("SELECT name FROM teams WHERE id=?", (team_id,)).fetchone()
        team_name = name_row["name"] if name_row else ""
        pat = _sub_pattern(conn, team_id, team_name)
    finally:
        conn.close()
    return pat


def format_team_profile(p: TeamProfile, verbose: bool = True) -> str:
    """Formatea el perfil de un equipo para mostrar en consola."""
    ms = p.match_stats
    sp = p.sub_pattern
    sep = "═" * 72
    thin = "─" * 72

    lines = [
        f"\n{sep}",
        f"  PERFIL ESTADÍSTICO — {p.team_name.upper()}",
        f"  (basado en {ms.n_matches} partidos competitivos desde 2022)",
        thin,
        f"  📊 ATAQUE",
        f"     Goles a favor / partido:      {ms.gf_pg:.2f}",
        f"     Tiros al arco / partido:      {ms.sot_for_pg:.1f}  "
        f"(total tiros ~{ms.shots_for_pg:.1f})",
        f"     Córners estimados / partido:  {ms.est_corners_for_pg:.1f}",
        f"     Goles en balón parado:        {ms.set_piece_goals_for_pg:.2f}/p "
        f"({ms.set_piece_frac_for*100:.0f}% del total)",
        f"     Marca en el partido:          {ms.scored_in_pct:.0f}%",
        thin,
        f"  🛡️  DEFENSA",
        f"     Goles en contra / partido:    {ms.ga_pg:.2f}",
        f"     Tiros al arco recibidos / p:  {ms.sot_against_pg:.1f}",
        f"     Córners concedidos / partido: {ms.est_corners_against_pg:.1f}",
        f"     Goles en BP en contra:        {ms.set_piece_goals_against_pg:.2f}/p",
        f"     Portería en 0:                {ms.clean_sheet_rate*100:.0f}%",
        f"     Recibe gol en el partido:     {ms.conceded_in_pct:.0f}%",
        thin,
        f"  🎮 JUEGO",
        f"     Posesión estimada:            {ms.possession_pct:.0f}%",
        f"     Faltas / partido:             {ms.fouls_pg:.1f}",
        f"     Tarjetas amarillas / partido: {ms.yellow_cards_pg:.1f}",
        f"     Win/Draw/Loss:                {ms.win_rate:.0f}% / {ms.draw_rate:.0f}% / {ms.loss_rate:.0f}%",
    ]

    if ms.competitions_sampled:
        lines.append(f"     Competiciones:               {', '.join(ms.competitions_sampled[:4])}")

    lines += [
        thin,
        f"  🔄 SUSTITUCIONES (fuente: {sp.data_source}, {sp.n_matches_analyzed} partidos analizados)",
        f"     Cambios por partido:          {sp.subs_per_game_mean:.1f} promedio",
    ]

    for i, slot in enumerate(sp.slots, 1):
        pos_str = "  ".join(f"{pos}={v*100:.0f}%" for pos, v in
                            sorted(slot.position_prefs.items(), key=lambda x: -x[1])
                            if v > 0.05)
        lines.append(f"     Oleada {i} — min {slot.entry_min_mean:.0f}' ±{slot.entry_min_std:.0f}  [{pos_str}]")

        if slot.frequent_subs and verbose:
            for fs in slot.frequent_subs[:3]:
                tag = "✓squad" if fs.get("current_squad") else "(histór)"
                g_str = f"  {fs['goals_as_sub']}g" if fs.get("goals_as_sub") else ""
                lines.append(f"          {fs['name'][:26]:<27} {fs['position']:<4} "
                              f"avg_min={fs['avg_entry_min']:.0f}'{g_str}  {tag}")

    if verbose and sp.sub_candidates:
        current_subs = [c for c in sp.sub_candidates if c["current_squad"]]
        if current_subs:
            lines += [thin, "  ⚡ SUPLENTES ACTUALES CON HISTORIAL DE ENTRADA"]
            for c in current_subs[:8]:
                g_str = f"  {c['goals_as_sub']}g" if c.get("goals_as_sub") else ""
                a_str = f"  {c['assists_as_sub']}a" if c.get("assists_as_sub") else ""
                lines.append(f"     {c['name'][:26]:<27} {c['position']:<4} "
                              f"{c['apps_as_sub']}x entró avg min {c['avg_entry_min']:.0f}'"
                              f"{g_str}{a_str}")

    lines.append(sep)
    return "\n".join(lines)


# ─── CLI de prueba ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    teams_to_show = sys.argv[1:] if len(sys.argv) > 1 else ["Brazil", "Argentina", "France", "Morocco", "Panama"]

    conn = _conn(DB_PATH)
    for name in teams_to_show:
        row = conn.execute(
            "SELECT id FROM teams WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
        if not row:
            print(f"  ⚠ No encontrado: {name}")
            continue
        profile = get_team_profile(row["id"], DB_PATH)
        print(format_team_profile(profile, verbose=True))
    conn.close()
