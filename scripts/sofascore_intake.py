#!/usr/bin/env python3
"""
sofascore_intake.py — Carga datos copiados de Sofascore al DB.

Uso interactivo:
    python3 scripts/sofascore_intake.py

O pasando un archivo JSON:
    python3 scripts/sofascore_intake.py match.json

Formato de entrada (JSON):
{
  "date": "2026-06-08",
  "competition": "Friendly",
  "home": "Germany",
  "away": "Greece",
  "score_home": 2,
  "score_away": 0,
  "home_stats": {
    "possession": 63,
    "xg": 2.14,
    "shots_total": 18,
    "shots_on_target": 7,
    "corners": 6,
    "fouls": 10,
    "yellow_cards": 1,
    "red_cards": 0,
    "passes_total": 542,
    "passes_accurate": 489,
    "passes_pct": 90.2,
    "tackles_total": 14,
    "tackles_won": 9,
    "aerial_total": 22,
    "aerial_won": 12,
    "saves": 1
  },
  "away_stats": { ... },
  "events": [
    {"team": "Germany", "player": "Havertz", "minute": 23, "type": "goal", "assist": "Musiala"},
    {"team": "Germany", "player": "Gnabry",  "minute": 67, "type": "goal"},
    {"team": "Greece",  "player": "Bakasetas","minute": 34, "type": "yellow"},
    {"team": "Germany", "player": "Rüdiger", "minute": 55, "type": "yellow"}
  ]
}

Tipos de evento válidos: goal, penalty_goal, own_goal, yellow, red, yellow_red
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "mundial2026.db"


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_team_id(conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM teams WHERE name=? OR name LIKE ? OR name LIKE ?",
        (name, f"%{name}%", f"{name[:6]}%")
    ).fetchone()
    return row[0] if row else None


def find_wc_match_id(conn, home_id, away_id, date) -> int | None:
    """Busca el id en wc_matches para usar como match_id canónico."""
    row = conn.execute("""
        SELECT id FROM wc_matches
        WHERE home_team_id=? AND away_team_id=? AND date=?
    """, (home_id, away_id, date)).fetchone()
    if row:
        return row[0]
    # Buscar por fecha aproximada (±2 días) por si la fecha difiere
    row = conn.execute("""
        SELECT id FROM wc_matches
        WHERE home_team_id=? AND away_team_id=?
        ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1
    """, (home_id, away_id, date)).fetchone()
    return row[0] if row else None


def upsert_team_match(conn, team_id, date, opponent_id, opponent_name,
                      gf, ga, competition, venue):
    result = "W" if gf > ga else ("D" if gf == ga else "L")
    conn.execute("""
        INSERT OR IGNORE INTO team_matches
          (team_id, opponent_id, opponent_name, date, competition,
           goals_for, goals_against, result, venue)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (team_id, opponent_id, opponent_name, date, competition, gf, ga, result, venue))
    return conn.execute(
        "SELECT id FROM team_matches WHERE team_id=? AND date=? AND opponent_id=?",
        (team_id, date, opponent_id)
    ).fetchone()[0]


def insert_stats(conn, match_id, team_id, is_home, stats: dict):
    cols = [
        "possession", "xg", "shots_total", "shots_on_target", "shots_off_target",
        "shots_blocked", "shots_inside_box", "shots_outside_box", "clear_chances",
        "corners", "fouls", "yellow_cards", "red_cards", "passes_total",
        "passes_accurate", "passes_pct", "passes_final_third", "long_balls_total",
        "long_balls_accurate", "crosses_total", "crosses_accurate", "touches_box",
        "tackles_total", "tackles_won", "interceptions", "recoveries", "clearances",
        "saves", "big_saves", "duels_total", "duels_won", "aerial_total",
        "aerial_won", "offsides", "free_kicks"
    ]
    vals = [stats.get(c) for c in cols]
    placeholders = ",".join(["?"] * (3 + len(cols)))
    conn.execute(f"""
        INSERT OR REPLACE INTO match_team_stats
          (match_id, team_id, is_home, {",".join(cols)})
        VALUES ({placeholders})
    """, [match_id, team_id, int(is_home)] + vals)


def insert_player_stats(conn, date, home_id, away_id, competition, players: list):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    for p in players:
        team_name = p.get("team", "")
        team_id = find_team_id(conn, team_name) if team_name else None
        # Accept "passes" or "passes_accurate" field
        passes_str = p.get("passes") or p.get("passes_accurate", "")
        passes_total, passes_accurate, passes_pct = None, None, None
        if isinstance(passes_str, str) and "/" in passes_str:
            parts = passes_str.split("/")
            try:
                passes_accurate = int(parts[0])
                rest = parts[1].split("(")
                passes_total = int(rest[0].strip())
                if len(rest) > 1:
                    passes_pct = float(rest[1].replace("%)", "").strip())
            except Exception:
                pass
        elif isinstance(passes_str, dict):
            passes_accurate = passes_str.get("accurate")
            passes_total = passes_str.get("total")
            passes_pct = passes_str.get("pct")

        def parse_duel(val):
            if val is None:
                return None, None
            if isinstance(val, str) and "/" in val:
                try:
                    w, t = val.split("/")
                    return int(w.strip()), int(t.strip())
                except Exception:
                    return None, None
            if isinstance(val, dict):
                return val.get("won"), val.get("total")
            return None, None

        duels_won, duels_total = parse_duel(p.get("duels"))
        aerial_won, aerial_total = parse_duel(p.get("aerials"))
        # Accept "tackles" or "tackles_won" field
        tackles_won, tackles_total = parse_duel(p.get("tackles") or p.get("tackles_won"))

        conn.execute("""
            INSERT OR REPLACE INTO match_player_stats
              (match_date, competition, home_team_id, away_team_id, team_id,
               player_name, position, minutes, goals, assists, rating,
               passes_accurate, passes_total, passes_pct,
               tackles_total, tackles_won, duels_total, duels_won,
               aerial_total, aerial_won, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            date, competition, home_id, away_id, team_id,
            p.get("player") or p.get("name", ""), p.get("position"), p.get("minutes"),
            p.get("goals", 0), p.get("assists", 0), p.get("rating"),
            passes_accurate, passes_total, passes_pct,
            tackles_total, tackles_won, duels_total, duels_won,
            aerial_total, aerial_won, now
        ))


def insert_events(conn, date, home_id, away_id, competition, events: list):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    for ev in events:
        team_name = ev.get("team", "")
        team_id = find_team_id(conn, team_name) if team_name else None
        minute = ev.get("minute")
        minute_extra = ev.get("minute_extra")
        etype = ev.get("type", "goal")
        # Normalizar tipo
        etype_map = {
            "gol": "goal", "penalti": "penalty_goal", "penal": "penalty_goal",
            "penalty": "penalty_goal", "propia": "own_goal", "own": "own_goal",
            "amarilla": "yellow", "roja": "red", "amarilla_roja": "yellow_red",
            "double_yellow": "yellow_red"
        }
        etype = etype_map.get(etype.lower(), etype.lower())

        conn.execute("""
            INSERT INTO match_events
              (match_date, home_team_id, away_team_id, team_id, player_name,
               event_type, minute, minute_extra, assist_player, detail, competition, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            date, home_id, away_id, team_id,
            ev.get("player", ""),
            etype, minute, minute_extra,
            ev.get("assist"), ev.get("detail", ""),
            competition, now
        ))


# ── Carga principal ──────────────────────────────────────────────────────────

def load_match(data: dict, db_path=DB_PATH) -> bool:
    conn = sqlite3.connect(str(db_path))

    date        = data["date"]
    home_name   = data["home"]
    away_name   = data["away"]
    score_home  = int(data["score_home"])
    score_away  = int(data["score_away"])
    competition = data.get("competition", "Friendly")
    home_stats  = data.get("home_stats", {})
    away_stats  = data.get("away_stats", {})
    events      = data.get("events", [])

    home_id = find_team_id(conn, home_name)
    away_id = find_team_id(conn, away_name)

    if not home_id:
        print(f"  ⚠  Equipo no encontrado: '{home_name}'")
    if not away_id:
        print(f"  ⚠  Equipo no encontrado: '{away_name}'")
    if not home_id or not away_id:
        conn.close()
        return False

    print(f"\n  Cargando: {home_name} {score_home}-{score_away} {away_name}  ({date})")

    # Insertar en team_matches para ambos equipos (historial de forma)
    upsert_team_match(conn, home_id, date, away_id, away_name,
                      score_home, score_away, competition, "home")
    upsert_team_match(conn, away_id, date, home_id, home_name,
                      score_away, score_home, competition, "away")

    # ID canónico para match_team_stats = wc_matches.id
    wc_id = find_wc_match_id(conn, home_id, away_id, date)
    if wc_id is None:
        # Partido no está en wc_matches (amistoso pre-torneo) — usar team_matches.id del local
        wc_id = conn.execute(
            "SELECT id FROM team_matches WHERE team_id=? AND date=? AND opponent_id=?",
            (home_id, date, away_id)
        ).fetchone()
        wc_id = wc_id[0] if wc_id else None
        print(f"  ⚠  Partido no en wc_matches — usando team_matches.id={wc_id}")

    # Stats de equipo
    if home_stats and wc_id:
        insert_stats(conn, wc_id, home_id, True, home_stats)
        print(f"  ✓ Stats {home_name}: xG={home_stats.get('xg')} shots={home_stats.get('shots_total')} poss={home_stats.get('possession')}%")
    if away_stats and wc_id:
        insert_stats(conn, wc_id, away_id, False, away_stats)
        print(f"  ✓ Stats {away_name}: xG={away_stats.get('xg')} shots={away_stats.get('shots_total')} poss={away_stats.get('possession')}%")

    # Actuaciones de jugadores
    players = data.get("players", [])
    if players:
        # Asegurarse que cada jugador tenga el campo "team" correcto
        home_players = [p for p in players if find_team_id(conn, p.get("team","")) == home_id]
        away_players = [p for p in players if find_team_id(conn, p.get("team","")) == away_id]
        if len(home_players) == 0 and len(away_players) == 0:
            # Sin campo "team": asignar por orden (mitad local, mitad visitante)
            mid = len(players) // 2
            for p in players[:mid]:
                p["team"] = home_name
            for p in players[mid:]:
                p["team"] = away_name
            home_players = players[:mid]
            away_players = players[mid:]

        insert_player_stats(conn, date, home_id, away_id, competition, players)
        print(f"  ✓ Jugadores: {len(players)} actuaciones ({home_name}={len(home_players)}, {away_name}={len(away_players)})")

    # Eventos (goles, tarjetas)
    if events:
        insert_events(conn, date, home_id, away_id, competition, events)
        goals = [e for e in events if "goal" in e.get("type","")]
        cards = [e for e in events if e.get("type","") in ("yellow","red","yellow_red")]
        print(f"  ✓ Eventos: {len(goals)} goles, {len(cards)} tarjetas")

    conn.commit()

    # ── VERIFICACIÓN OBLIGATORIA ─────────────────────────────────────────────
    # Solo si se enviaron jugadores: ambos equipos deben tener filas guardadas
    if players:
        n_home = conn.execute(
            "SELECT COUNT(*) FROM match_player_stats "
            "WHERE match_date=? AND home_team_id=? AND away_team_id=? AND team_id=?",
            (date, home_id, away_id, home_id)
        ).fetchone()[0]
        n_away = conn.execute(
            "SELECT COUNT(*) FROM match_player_stats "
            "WHERE match_date=? AND home_team_id=? AND away_team_id=? AND team_id=?",
            (date, home_id, away_id, away_id)
        ).fetchone()[0]

        if n_home == 0 or n_away == 0:
            print(f"  ✗ ERROR VERIFICACIÓN: {home_name}={n_home} jugadores, "
                  f"{away_name}={n_away} jugadores — DATOS INCOMPLETOS")
            conn.close()
            return False

        print(f"  ✓ VERIFICADO: {home_name}={n_home} jugadores, {away_name}={n_away} jugadores guardados")

    conn.close()
    return True


def rebuild_timing():
    """Reconstruye team_goal_timing y team_performance_profile después de cargar."""
    try:
        import importlib.util, subprocess
        result = subprocess.run(
            ["python3", str(ROOT / "scripts" / "build_goal_timing.py"), "--rebuild"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        if result.returncode == 0:
            print("\n  ✓ team_goal_timing reconstruida")
        else:
            print(f"\n  ⚠ rebuild_timing: {result.stderr[:200]}")
    except Exception as e:
        print(f"\n  ⚠ rebuild_timing skipped: {e}")


# ── CLI ──────────────────────────────────────────────────────────────────────

TEMPLATE = {
    "date": "2026-06-08",
    "competition": "Friendly",
    "home": "Team A",
    "away": "Team B",
    "score_home": 0,
    "score_away": 0,
    "home_stats": {
        "possession": 50,
        "xg": 1.20,
        "shots_total": 12,
        "shots_on_target": 4,
        "corners": 5,
        "fouls": 10,
        "yellow_cards": 1,
        "red_cards": 0,
        "passes_pct": 85.0,
        "tackles_total": 15,
        "tackles_won": 10,
        "aerial_total": 20,
        "aerial_won": 10,
        "saves": 2
    },
    "away_stats": {
        "possession": 50,
        "xg": 0.80,
        "shots_total": 8,
        "shots_on_target": 3,
        "corners": 3,
        "fouls": 12,
        "yellow_cards": 2,
        "red_cards": 0,
        "passes_pct": 80.0,
        "tackles_total": 18,
        "tackles_won": 12,
        "aerial_total": 20,
        "aerial_won": 10,
        "saves": 3
    },
    "events": [
        {"team": "Team A", "player": "Player Name", "minute": 35, "type": "goal", "assist": "Other Player"},
        {"team": "Team B", "player": "Player Name", "minute": 72, "type": "yellow"}
    ]
}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Cargar desde archivo
        files = sys.argv[1:]
        loaded = 0
        for f in files:
            path = Path(f)
            if not path.exists():
                print(f"Archivo no encontrado: {f}")
                continue
            data = json.loads(path.read_text())
            # Puede ser un dict (1 partido) o lista (varios)
            matches = data if isinstance(data, list) else [data]
            for m in matches:
                if load_match(m):
                    loaded += 1
        print(f"\n{loaded} partido(s) cargado(s).")
        if loaded:
            rebuild_timing()
    else:
        # Modo interactivo
        print("=" * 60)
        print("  SOFASCORE INTAKE — Carga de estadísticas")
        print("=" * 60)
        print("\nPega el JSON del partido (termina con una línea vacía):")
        print("(Tip: usa la plantilla de abajo como guía)\n")
        print("PLANTILLA:")
        print(json.dumps(TEMPLATE, indent=2, ensure_ascii=False))
        print("\n" + "─" * 60)
        print("Pega tu JSON aquí (Ctrl+D para terminar):\n")

        lines = []
        try:
            for line in sys.stdin:
                lines.append(line)
        except EOFError:
            pass

        raw = "".join(lines).strip()
        if not raw:
            print("No se ingresó nada.")
            sys.exit(0)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON inválido: {e}")
            sys.exit(1)

        matches = data if isinstance(data, list) else [data]
        loaded = 0
        for m in matches:
            if load_match(m):
                loaded += 1

        print(f"\n{loaded} partido(s) cargado(s).")
        if loaded:
            rebuild_timing()
            print("\n✓ Perfiles de timing actualizados.")
