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
            save_to_db(profiles, conn)
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
