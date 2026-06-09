#!/usr/bin/env python3
"""
build_goal_timing.py — Construye perfiles de timing de goles por equipo.

Analiza el CSV de martj42 (47,601 goles con minuto) y genera:
  - team_goal_timing: goles marcados/recibidos por franja de 15 min
  - Índice de "fatiga" (ratio de goles en últimos 30' vs primeros 30')
  - Perfil de inicio fuerte / inicio lento
  - Vulnerabilidad en cada franja

Uso:
    python scripts/build_goal_timing.py
    python scripts/build_goal_timing.py --team "Panama"
"""

import sys
import sqlite3
import argparse
import requests
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"

# Franjas de 15 minutos (+ tiempo añadido agrupado en 90+)
FRANJAS = [
    (1,  15,  "1-15"),
    (16, 30,  "16-30"),
    (31, 45,  "31-45"),
    (46, 60,  "46-60"),
    (61, 75,  "61-75"),
    (76, 120, "76-90+"),
]

FRANJAS_LABEL = [f[2] for f in FRANJAS]

CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv"


def get_franja(minute: int) -> str:
    for lo, hi, label in FRANJAS:
        if lo <= minute <= hi:
            return label
    return "76-90+"


def build_timing_profile(since_year: int = 2018) -> dict:
    """
    Descarga el CSV de goleadores y construye perfil por equipo.
    Retorna dict: team_name -> {scored: {franja: n}, conceded: {franja: n}, matches: int}
    """
    print("Descargando goalscorers.csv...")
    try:
        r = requests.get(CSV_URL, timeout=20)
        r.raise_for_status()
        lines = r.text.strip().split('\n')
    except Exception as e:
        print(f"  Error: {e}")
        return {}

    # Primero construir mapa de partidos por fecha+equipos para saber el rival
    # CSV: date,home_team,away_team,team,scorer,minute,own_goal,penalty
    match_teams = {}  # (date,home,away) -> (home, away)
    goals = []

    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) < 8:
            continue
        date, home, away, team, scorer, minute, own_goal, penalty = parts[:8]
        year = int(date[:4]) if date else 0
        if year < since_year:
            continue
        try:
            min_int = int(float(minute)) if minute else 0
        except ValueError:
            continue
        if min_int <= 0 or min_int > 120:
            continue

        is_own   = own_goal.strip().upper() == "TRUE"
        is_pen   = penalty.strip().upper() == "TRUE"
        key      = (date, home, away)
        match_teams[key] = (home, away)

        # El gol fue marcado por 'team'; si es en propia, beneficia al rival
        scoring_team  = away if (is_own and team == home) else (home if (is_own and team == away) else team)
        conceding_team = home if scoring_team == away else away

        goals.append({
            "date":     date,
            "home":     home,
            "away":     away,
            "scorer":   scoring_team,
            "conceder": conceding_team,
            "minute":   min_int,
            "penalty":  is_pen,
            "own_goal": is_own,
        })

    print(f"  {len(goals)} goles desde {since_year}")

    # Contar partidos por equipo
    match_counts = defaultdict(set)
    for key, (home, away) in match_teams.items():
        match_counts[home].add(key)
        match_counts[away].add(key)

    # Construir perfiles
    profiles = defaultdict(lambda: {
        "scored":   defaultdict(int),
        "conceded": defaultdict(int),
        "penalties_scored":  0,
        "penalties_conceded": 0,
        "matches": 0,
    })

    for g in goals:
        franja = get_franja(g["minute"])
        profiles[g["scorer"]]["scored"][franja]   += 1
        profiles[g["conceder"]]["conceded"][franja] += 1
        if g["penalty"]:
            profiles[g["scorer"]]["penalties_scored"]   += 1
            profiles[g["conceder"]]["penalties_conceded"] += 1

    for team in profiles:
        profiles[team]["matches"] = len(match_counts[team])

    return dict(profiles)


def merge_from_match_events(profiles: dict, conn: sqlite3.Connection) -> dict:
    """
    Incorpora goles de la tabla match_events (partidos 2026 con minutos exactos)
    al dict de perfiles ya construido desde el CSV de martj42.
    También añade métricas agregadas de match_team_stats si disponibles.
    """
    rows = conn.execute("""
        SELECT me.match_date, me.home_team_id, me.away_team_id,
               me.team_id, me.event_type, me.minute, me.minute_extra,
               th.name AS home_name, ta.name AS away_name, t.name AS team_name
        FROM match_events me
        JOIN teams t  ON t.id  = me.team_id
        JOIN teams th ON th.id = me.home_team_id
        JOIN teams ta ON ta.id = me.away_team_id
        WHERE me.event_type IN ('goal', 'penalty_goal', 'own_goal')
          AND me.minute IS NOT NULL AND me.minute > 0
    """).fetchall()

    # Track matches seen in match_events to count them for each team
    me_matches = defaultdict(set)   # team_name -> set of (date, home_id, away_id)

    for r in rows:
        minute    = r[5] + (r[6] or 0)   # minute + minute_extra
        minute    = min(120, max(1, minute))
        franja    = get_franja(minute)
        is_own    = r[4] == "own_goal"
        is_pen    = r[4] == "penalty_goal"
        team_name = r[9]
        home_name = r[7]
        away_name = r[8]
        match_key = (r[0], r[2], r[3])   # (date, home_team_id, away_team_id)

        # Determine scoring/conceding team (own goal flips beneficiary)
        if is_own:
            scoring_team   = away_name if team_name == home_name else home_name
            conceding_team = team_name
        else:
            scoring_team   = team_name
            conceding_team = away_name if team_name == home_name else home_name

        if scoring_team not in profiles:
            profiles[scoring_team] = {
                "scored": defaultdict(int), "conceded": defaultdict(int),
                "penalties_scored": 0, "penalties_conceded": 0, "matches": 0,
            }
        if conceding_team not in profiles:
            profiles[conceding_team] = {
                "scored": defaultdict(int), "conceded": defaultdict(int),
                "penalties_scored": 0, "penalties_conceded": 0, "matches": 0,
            }

        profiles[scoring_team]["scored"][franja]     += 1
        profiles[conceding_team]["conceded"][franja] += 1
        if is_pen:
            profiles[scoring_team]["penalties_scored"]      += 1
            profiles[conceding_team]["penalties_conceded"]  += 1

        me_matches[scoring_team].add(match_key)
        me_matches[conceding_team].add(match_key)

    # Add newly seen matches to match counts (don't double-count)
    for team, match_keys in me_matches.items():
        if team in profiles:
            profiles[team]["matches"] = profiles[team].get("matches", 0) + len(match_keys)

    print(f"  merge_from_match_events: {len(rows)} goles de match_events incorporados "
          f"({len(me_matches)} equipos actualizados)")
    return profiles


def build_team_performance_profile(conn: sqlite3.Connection):
    """
    Construye la tabla team_performance_profile desde match_team_stats + teams.
    Agregados ponderados por partido: xg, shots, possession, corners, fouls,
    press intensity (tackles/match), aerial dominance, set piece threat.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_performance_profile (
            team_name               TEXT PRIMARY KEY,
            matches_analyzed        INTEGER,
            avg_xg_for              REAL,
            avg_xg_against          REAL,
            avg_shots_for           REAL,
            avg_shots_on_target_for REAL,
            avg_possession          REAL,
            avg_corners_for         REAL,
            avg_fouls_committed     REAL,
            avg_yellow_cards        REAL,
            press_intensity         REAL,
            aerial_dominance        REAL,
            set_piece_threat        REAL,
            updated_at              TEXT
        )
    """)

    # Get all teams with match_team_stats data
    team_rows = conn.execute("""
        SELECT DISTINCT t.id, t.name
        FROM match_team_stats mts
        JOIN teams t ON t.id = mts.team_id
    """).fetchall()

    # Ranking mediano FIFA para normalizar pesos
    all_rankings = conn.execute(
        "SELECT fifa_ranking FROM teams WHERE fifa_ranking IS NOT NULL"
    ).fetchall()
    rank_list = sorted([r[0] for r in all_rankings])
    median_rank = rank_list[len(rank_list)//2] if rank_list else 40

    inserted = 0
    for (tid, tname) in team_rows:
        # Incluir el ranking del rival para ponderar cada partido
        stats = conn.execute("""
            SELECT mts.possession, mts.xg,
                   mts.shots_total, mts.shots_on_target,
                   mts.corners, mts.fouls, mts.yellow_cards,
                   mts.tackles_total, mts.aerial_total, mts.aerial_won,
                   mts.free_kicks,
                   opp.xg AS opp_xg,
                   t_opp.fifa_ranking AS opp_rank
            FROM match_team_stats mts
            LEFT JOIN match_team_stats opp
                   ON opp.match_id = mts.match_id AND opp.team_id != mts.team_id
            LEFT JOIN teams t_opp ON t_opp.id = opp.team_id
            WHERE mts.team_id = ?
        """, (tid,)).fetchall()

        if not stats:
            continue

        m = len(stats)

        def _opp_weight(opp_rank):
            """
            Peso por fortaleza del rival.
            FIFA #1  → ~1.45  (enfrentarse a los mejores = más mérito)
            FIFA #40 → ~1.00  (partido estándar)
            FIFA #100→ ~0.65  (rival débil = menos relevante)
            Panamá generando xG vs Francia cuenta MÁS que vs Costa Rica.
            Francia generando xG vs Panamá cuenta MENOS que vs España.
            """
            if opp_rank is None:
                return 1.0
            w = 1.0 + (median_rank - opp_rank) / (median_rank * 2.2)
            return max(0.55, min(1.50, w))

        def _wavg(idx, invert_weight=False):
            """Promedio ponderado por fortaleza del rival."""
            pairs = [(r[idx], _opp_weight(r[12])) for r in stats if r[idx] is not None]
            if not pairs:
                return None
            if invert_weight:
                # xGa: conceder vs rival fuerte es esperable → reducir peso
                pairs = [(v, 1.0 / w) for v, w in pairs]
            total_w = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / total_w if total_w > 0 else None

        avg_poss     = _wavg(0)
        avg_xg_for   = _wavg(1)            # xGf vs rival fuerte pesa MÁS
        avg_shots    = _wavg(2)
        avg_sot      = _wavg(3)
        avg_corners  = _wavg(4)
        avg_fouls    = _wavg(5)
        avg_yellows  = _wavg(6)
        press_int    = _wavg(7)
        aer_total_vals = [(r[8], r[9]) for r in stats if r[8] and r[9] and r[8] > 0]
        aerial_dom = (sum(r[1] for r in aer_total_vals) / sum(r[0] for r in aer_total_vals)
                      if aer_total_vals else None)
        sp_threat_vals = [(r[4] or 0) + (r[10] or 0) for r in stats]
        set_piece_threat = sum(sp_threat_vals) / m if m else None
        # xGa vs rival fuerte es esperable → pesa MENOS (invert)
        avg_xg_against = _wavg(11, invert_weight=True)

        from datetime import datetime
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        conn.execute("""
            INSERT OR REPLACE INTO team_performance_profile VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            tname, m,
            round(avg_xg_for,    3) if avg_xg_for    is not None else None,
            round(avg_xg_against,3) if avg_xg_against is not None else None,
            round(avg_shots,     2) if avg_shots      is not None else None,
            round(avg_sot,       2) if avg_sot        is not None else None,
            round(avg_poss,      1) if avg_poss       is not None else None,
            round(avg_corners,   2) if avg_corners     is not None else None,
            round(avg_fouls,     2) if avg_fouls       is not None else None,
            round(avg_yellows,   2) if avg_yellows     is not None else None,
            round(press_int,     2) if press_int       is not None else None,
            round(aerial_dom,    3) if aerial_dom      is not None else None,
            round(set_piece_threat, 2) if set_piece_threat is not None else None,
            now,
        ))
        inserted += 1

    conn.commit()
    print(f"  {inserted} equipos guardados en team_performance_profile")


def save_to_db(profiles: dict, conn: sqlite3.Connection):
    """Guarda perfiles en team_goal_timing."""
    conn.execute("DROP TABLE IF EXISTS team_goal_timing")
    conn.execute("""
        CREATE TABLE team_goal_timing (
            team_name       TEXT    NOT NULL,
            matches         INTEGER DEFAULT 0,
            -- Goles marcados por franja
            scored_1_15     REAL    DEFAULT 0,
            scored_16_30    REAL    DEFAULT 0,
            scored_31_45    REAL    DEFAULT 0,
            scored_46_60    REAL    DEFAULT 0,
            scored_61_75    REAL    DEFAULT 0,
            scored_76_90    REAL    DEFAULT 0,
            -- Goles recibidos por franja
            conceded_1_15   REAL    DEFAULT 0,
            conceded_16_30  REAL    DEFAULT 0,
            conceded_31_45  REAL    DEFAULT 0,
            conceded_46_60  REAL    DEFAULT 0,
            conceded_61_75  REAL    DEFAULT 0,
            conceded_76_90  REAL    DEFAULT 0,
            -- Índices derivados
            fatigue_scored  REAL    DEFAULT 1.0,  -- ratio goles 61-90 / 1-30
            fatigue_conceded REAL   DEFAULT 1.0,  -- ratio concedidos 61-90 / 1-30
            strong_start    INTEGER DEFAULT 0,    -- 1 si marca >avg en 1-15
            late_collapse   INTEGER DEFAULT 0,    -- 1 si concede >avg en 76-90+
            penalties_scored   INTEGER DEFAULT 0,
            penalties_conceded INTEGER DEFAULT 0,
            PRIMARY KEY (team_name)
        )
    """)

    inserted = 0
    for team, prof in profiles.items():
        m = max(1, prof["matches"])
        s = prof["scored"];   c = prof["conceded"]

        # Goles por partido en cada franja
        s15  = s.get("1-15",  0) / m;  s30  = s.get("16-30", 0) / m
        s45  = s.get("31-45", 0) / m;  s60  = s.get("46-60", 0) / m
        s75  = s.get("61-75", 0) / m;  s90  = s.get("76-90+",0) / m

        c15  = c.get("1-15",  0) / m;  c30  = c.get("16-30", 0) / m
        c45  = c.get("31-45", 0) / m;  c60  = c.get("46-60", 0) / m
        c75  = c.get("61-75", 0) / m;  c90  = c.get("76-90+",0) / m

        early_s = s15 + s30;  late_s = s75 + s90
        early_c = c15 + c30;  late_c = c75 + c90

        fat_s = (late_s / early_s) if early_s > 0.01 else 1.0
        fat_c = (late_c / early_c) if early_c > 0.01 else 1.0

        avg_s_franja = (s15+s30+s45+s60+s75+s90) / 6
        strong_start = 1 if s15 > avg_s_franja * 1.25 else 0
        late_collapse = 1 if c90 > (c15+c30+c45+c60+c75) / 5 * 1.40 else 0

        conn.execute("""
            INSERT OR REPLACE INTO team_goal_timing VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (team, prof["matches"],
              round(s15,3), round(s30,3), round(s45,3),
              round(s60,3), round(s75,3), round(s90,3),
              round(c15,3), round(c30,3), round(c45,3),
              round(c60,3), round(c75,3), round(c90,3),
              round(fat_s,3), round(fat_c,3),
              strong_start, late_collapse,
              prof["penalties_scored"], prof["penalties_conceded"]))
        inserted += 1

    conn.commit()
    print(f"  {inserted} equipos guardados en team_goal_timing")


def print_team_profile(team_name: str, conn: sqlite3.Connection):
    """Muestra el perfil de timing de un equipo."""
    row = conn.execute(
        "SELECT * FROM team_goal_timing WHERE team_name=?", (team_name,)
    ).fetchone()

    if not row:
        # Buscar nombre similar
        row = conn.execute(
            "SELECT * FROM team_goal_timing WHERE team_name LIKE ?",
            (f"%{team_name[:5]}%",)
        ).fetchone()

    if not row:
        print(f"  No se encontró perfil para '{team_name}'")
        return

    r = dict(row)
    m = r["matches"]
    print(f"\n{'='*55}")
    print(f"  PERFIL DE TIMING — {r['team_name']}  ({m} partidos desde 2018)")
    print(f"{'='*55}")
    print(f"\n  GOLES MARCADOS por franja (por partido):")
    franjas_data = [
        ("1-15",   r["scored_1_15"]),
        ("16-30",  r["scored_16_30"]),
        ("31-45",  r["scored_31_45"]),
        ("46-60",  r["scored_46_60"]),
        ("61-75",  r["scored_61_75"]),
        ("76-90+", r["scored_76_90"]),
    ]
    for label, val in franjas_data:
        bar = "█" * int(val * 20) + ("▌" if (val*20 % 1) >= 0.5 else "")
        print(f"  {label:7}  {val:.3f}/p  {bar}")

    print(f"\n  GOLES RECIBIDOS por franja (por partido):")
    franjas_c = [
        ("1-15",   r["conceded_1_15"]),
        ("16-30",  r["conceded_16_30"]),
        ("31-45",  r["conceded_31_45"]),
        ("46-60",  r["conceded_46_60"]),
        ("61-75",  r["conceded_61_75"]),
        ("76-90+", r["conceded_76_90"]),
    ]
    for label, val in franjas_c:
        bar = "█" * int(val * 20) + ("▌" if (val*20 % 1) >= 0.5 else "")
        print(f"  {label:7}  {val:.3f}/p  {bar}")

    print(f"\n  ÍNDICES:")
    fat_s = r["fatigue_scored"]
    fat_c = r["fatigue_conceded"]
    fat_s_label = "FUERTE al final" if fat_s > 1.3 else ("Normal" if fat_s > 0.7 else "Baja tarde")
    fat_c_label = "VULNERABLE al final" if fat_c > 1.3 else ("Normal" if fat_c > 0.7 else "Sólido tarde")
    print(f"  Fatiga ofensiva  (goles tarde/temprano): {fat_s:.2f}  → {fat_s_label}")
    print(f"  Fatiga defensiva (concedidos tarde/tmp): {fat_c:.2f}  → {fat_c_label}")
    print(f"  Inicio fuerte (marca >25% más en 1-15): {'SÍ ✅' if r['strong_start'] else 'No'}")
    print(f"  Colapso tardío (vulnerable en 76-90+):  {'SÍ ⚠️' if r['late_collapse'] else 'No'}")
    print(f"  Penales marcados: {r['penalties_scored']}  |  Penales recibidos: {r['penalties_conceded']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", help="Ver perfil de un equipo específico")
    parser.add_argument("--since", type=int, default=2018, help="Desde qué año (default: 2018)")
    parser.add_argument("--rebuild", action="store_true", help="Reconstruir tabla aunque ya exista")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Verificar si ya existe la tabla
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='team_goal_timing'"
    ).fetchone()

    if not exists or args.rebuild:
        profiles = build_timing_profile(since_year=args.since)
        if profiles:
            # Merge goals from local match_events (2026 friendlies with exact minutes)
            profiles = merge_from_match_events(profiles, conn)
            save_to_db(profiles, conn)
        # Always rebuild team_performance_profile
        build_team_performance_profile(conn)
    else:
        n = conn.execute("SELECT COUNT(*) FROM team_goal_timing").fetchone()[0]
        print(f"  Tabla team_goal_timing ya existe ({n} equipos) — usa --rebuild para regenerar")

    if args.team:
        print_team_profile(args.team, conn)
    else:
        # Mostrar top equipos con colapso tardío
        rows = conn.execute("""
            SELECT team_name, matches, fatigue_conceded, conceded_76_90, late_collapse,
                   scored_1_15, strong_start
            FROM team_goal_timing
            WHERE matches >= 10
            ORDER BY fatigue_conceded DESC
            LIMIT 15
        """).fetchall()
        print(f"\n{'='*60}")
        print("  EQUIPOS CON MAYOR VULNERABILIDAD EN TRAMO FINAL (76-90+)")
        print(f"{'='*60}")
        print(f"  {'Equipo':<22} {'PJ':>4} {'Fat.Def':>8} {'Conc76+':>8} {'Colapso'}")
        print(f"  {'-'*55}")
        for r in rows:
            col = "⚠️ " if r["late_collapse"] else "   "
            print(f"  {r['team_name']:<22} {r['matches']:>4} {r['fatigue_conceded']:>8.2f} "
                  f"{r['conceded_76_90']:>8.3f} {col}")

    conn.close()


if __name__ == "__main__":
    main()
