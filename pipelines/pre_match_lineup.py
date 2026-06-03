"""
pipelines/pre_match_lineup.py — Orquestador completo del ciclo de alineaciones.

Tres modos:
  --mode estimate  : Estima XI para partidos de hoy/mañana (si no hay confirmada)
  --mode confirm   : Intenta obtener XI oficial vía API-Football (1h antes kickoff)
  --mode record    : Registra resultado real post-partido: titulares, cambios, minutos
  --mode learn     : (auto, post-partido) Actualiza player_match_usage y squad_weight

Uso:
  python pipelines/pre_match_lineup.py --mode estimate
  python pipelines/pre_match_lineup.py --mode confirm --fixture-id 12345
  python pipelines/pre_match_lineup.py --mode record --home "France" --away "Argentina" \\
      --date 2026-06-15 --starters-home "Maignan,Koundé,..." \\
      --subs "Camavinga:65:Tchouaméni,Thuram:78:Dembélé"
"""
import argparse
import sqlite3
import sys
import os
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DB = BASE / "data" / "mundial2026.db"


# ── Utilidades ───────────────────────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _normalize(name: str) -> str:
    n = unicodedata.normalize("NFD", name.lower().strip())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return n.split()[-1]  # apellido normalizado


def _find_player(conn, name: str, team_id: int):
    """Busca jugador por nombre exacto o por apellido normalizado."""
    row = conn.execute(
        "SELECT id, name FROM players WHERE team_id=? AND name=?", (team_id, name)
    ).fetchone()
    if row:
        return row
    # Búsqueda por apellido normalizado
    norm = _normalize(name)
    candidates = conn.execute(
        "SELECT id, name FROM players WHERE team_id=?", (team_id,)
    ).fetchall()
    for c in candidates:
        if _normalize(c["name"]) == norm:
            return c
    return None


def _get_team(conn, name: str):
    return conn.execute(
        "SELECT id, name FROM teams WHERE name=? OR name LIKE ?",
        (name, f"%{name}%")
    ).fetchone()


def _get_wc_match(conn, home: str, away: str, date: str):
    return conn.execute("""
        SELECT id FROM wc_matches
        WHERE home_team_name=? AND away_team_name=? AND date=?
    """, (home, away, date)).fetchone()


# ── MODO: ESTIMAR ─────────────────────────────────────────────────────────────

def mode_estimate(date_str: str | None = None):
    """Genera XI estimado para partidos sin lineup confirmado."""
    from models.lineup_estimator import estimate_lineup

    conn = _conn()
    today = date_str or datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    matches = conn.execute("""
        SELECT id, date, home_team_name, away_team_name
        FROM wc_matches
        WHERE date BETWEEN ? AND ? AND played=0
        ORDER BY date, time
    """, (today, tomorrow)).fetchall()

    if not matches:
        print(f"Sin partidos WC para {today}–{tomorrow}")
        conn.close()
        return

    for m in matches:
        for role, team_name in [("home", m["home_team_name"]), ("away", m["away_team_name"])]:
            team = _get_team(conn, team_name)
            if not team:
                continue

            # ¿Ya tiene lineup confirmado?
            confirmed = conn.execute("""
                SELECT COUNT(*) FROM match_lineups
                WHERE match_id=? AND team_id=? AND estimated=0 AND starter=1
            """, (m["id"], team["id"])).fetchone()[0]
            if confirmed > 0:
                print(f"  {team_name}: lineup confirmado, skip")
                continue

            # Borrar estimación previa si existe
            conn.execute("""
                DELETE FROM match_lineups
                WHERE match_id=? AND team_id=? AND estimated=1
            """, (m["id"], team["id"]))

            lineup = estimate_lineup(team_name)
            now_ts = datetime.utcnow().isoformat()
            inserted = 0
            for p in lineup["starters"]:
                player = _find_player(conn, p["name"], team["id"])
                player_id = player["id"] if player else None
                conn.execute("""
                    INSERT OR IGNORE INTO match_lineups
                    (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                    VALUES (?,?,?,?,1,1,?)
                """, (m["id"], team["id"], player_id, p["position"], now_ts))
                inserted += 1

            conn.commit()
            conf = lineup["confidence"].upper()
            print(f"  {team_name}: XI estimado ({conf}), {inserted} jugadores guardados")

    conn.close()


# ── MODO: CONFIRMAR VÍA API ───────────────────────────────────────────────────

def mode_confirm(fixture_id: int | None = None):
    """Obtiene XI oficial de API-Football y sobreescribe estimación."""
    import requests

    key = os.environ.get("APISPORTS_KEY") or os.environ.get("APIFOOT", "")
    if not key:
        print("Sin API key, no se puede confirmar lineup")
        return

    conn = _conn()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Obtener fixture_ids de hoy
    if fixture_id:
        fixture_ids = [fixture_id]
        match_dates = {fixture_id: today}
    else:
        matches = conn.execute("""
            SELECT id, date, api_fixture_id FROM wc_matches
            WHERE date BETWEEN ? AND ? AND played=0 AND api_fixture_id IS NOT NULL
        """, (today, tomorrow)).fetchall()
        fixture_ids = [m["api_fixture_id"] for m in matches]
        match_dates = {m["api_fixture_id"]: m["date"] for m in matches}

    for fid in fixture_ids:
        print(f"\nFetcheando lineup fixture {fid}...")
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/fixtures/lineups",
                headers={"x-apisports-key": key},
                params={"fixture": fid},
                timeout=15
            )
            data = r.json().get("response", [])
        except Exception as e:
            print(f"  Error API: {e}")
            continue

        if not data:
            print(f"  Sin datos aún para fixture {fid}")
            continue

        match_row = conn.execute(
            "SELECT id, date FROM wc_matches WHERE api_fixture_id=?", (fid,)
        ).fetchone()
        match_id = match_row["id"] if match_row else None
        match_date = match_row["date"] if match_row else match_dates.get(fid, today)

        for entry in data:
            team_name = entry["team"]["name"]
            team = _get_team(conn, team_name)
            if not team:
                print(f"  Equipo no encontrado: {team_name}")
                continue

            starters = entry.get("startXI", [])
            bench    = entry.get("substitutes", [])
            now_ts   = datetime.utcnow().isoformat()

            # Borrar estimaciones previas para este equipo/partido
            if match_id:
                conn.execute("""
                    DELETE FROM match_lineups
                    WHERE match_id=? AND team_id=? AND estimated=1
                """, (match_id, team["id"]))

            starter_names = []
            for entry_p in starters:
                p_data = entry_p.get("player", {})
                name = p_data.get("name", "")
                pos  = p_data.get("pos", "MID")
                player = _find_player(conn, name, team["id"])
                player_id = player["id"] if player else None
                starter_names.append(name)
                conn.execute("""
                    INSERT OR REPLACE INTO match_lineups
                    (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                    VALUES (?,?,?,?,1,0,?)
                """, (match_id, team["id"], player_id, pos, now_ts))

            for entry_p in bench:
                p_data = entry_p.get("player", {})
                name = p_data.get("name", "")
                pos  = p_data.get("pos", "MID")
                player = _find_player(conn, name, team["id"])
                player_id = player["id"] if player else None
                conn.execute("""
                    INSERT OR IGNORE INTO match_lineups
                    (match_id, team_id, player_id, position, starter, estimated, confirmed_at)
                    VALUES (?,?,?,?,0,0,?)
                """, (match_id, team["id"], player_id, pos, now_ts))

            # squad_weight real
            weight = _compute_squad_weight(conn, team["id"], starter_names)
            print(f"  {team_name}: {len(starter_names)} titulares confirmados, squad_weight={weight:.2f}")

            # Actualizar team_matches del día
            if match_date:
                conn.execute("""
                    UPDATE team_matches SET squad_weight=?
                    WHERE team_id=? AND date=? AND (squad_weight=1.0 OR squad_weight IS NULL)
                """, (weight, team["id"], match_date))

        conn.commit()

    conn.close()


# ── MODO: REGISTRAR RESULTADO REAL ───────────────────────────────────────────

def mode_record(home: str, away: str, date: str,
                starters_home: list[str], starters_away: list[str],
                subs_home: list[dict], subs_away: list[dict]):
    """
    Registra el XI real y sustituciones después del partido.
    Actualiza match_lineups (estimated=0) y player_match_usage.

    subs format: [{"out": "nombre", "in": "nombre", "minute": 65}, ...]
    """
    conn = _conn()

    team_h = _get_team(conn, home)
    team_a = _get_team(conn, away)
    match  = _get_wc_match(conn, home, away, date)
    match_id = match["id"] if match else None

    now_ts = datetime.utcnow().isoformat()

    def _record_team(team, starters, subs, competition="WC2026"):
        if not team:
            return

        # Construir mapa de sustituciones: quién salió → {minuto, reemplazado_por}
        sub_out_map = {}   # player_id → sub_out_minute
        sub_in_map  = {}   # player_id → {sub_in_minute, sub_for_id}
        for s in subs:
            p_out = _find_player(conn, s["out"], team["id"])
            p_in  = _find_player(conn, s["in"],  team["id"])
            minute = s.get("minute", 90)
            if p_out:
                sub_out_map[p_out["id"]] = minute
            if p_in:
                sub_in_map[p_in["id"]] = {
                    "minute": minute,
                    "sub_for_id": p_out["id"] if p_out else None
                }

        # Limpiar lineup estimado del partido
        if match_id:
            conn.execute("""
                DELETE FROM match_lineups
                WHERE match_id=? AND team_id=?
            """, (match_id, team["id"]))

        # Insertar titulares reales
        for name in starters:
            player = _find_player(conn, name, team["id"])
            player_id = player["id"] if player else None
            sub_out_min = sub_out_map.get(player_id)
            mins = sub_out_min if sub_out_min else 90

            conn.execute("""
                INSERT OR REPLACE INTO match_lineups
                (match_id, team_id, player_id, starter, estimated,
                 minutes_played, sub_out_minute, confirmed_at)
                VALUES (?,?,?,1,0,?,?,?)
            """, (match_id, team["id"], player_id, mins, sub_out_min, now_ts))

            # player_match_usage
            conn.execute("""
                INSERT OR REPLACE INTO player_match_usage
                (player_id, team_id, match_id, match_date, competition,
                 is_starter, minutes_played, sub_out_minute)
                VALUES (?,?,?,?,?,1,?,?)
            """, (player_id, team["id"], match_id, date, competition, mins, sub_out_min))

        # Insertar sustitutos que entraron
        for player_id, info in sub_in_map.items():
            min_in  = info["minute"]
            mins    = 90 - min_in
            sub_for = info["sub_for_id"]

            conn.execute("""
                INSERT OR REPLACE INTO match_lineups
                (match_id, team_id, player_id, starter, estimated,
                 minutes_played, sub_in_minute, sub_for_player_id, confirmed_at)
                VALUES (?,?,?,0,0,?,?,?,?)
            """, (match_id, team["id"], player_id, mins, min_in, sub_for, now_ts))

            conn.execute("""
                INSERT OR REPLACE INTO player_match_usage
                (player_id, team_id, match_id, match_date, competition,
                 is_starter, minutes_played, sub_in_minute, sub_for_id)
                VALUES (?,?,?,?,?,0,?,?,?)
            """, (player_id, team["id"], match_id, date, competition, mins, min_in, sub_for))

        # squad_weight real basado en titulares confirmados
        weight = _compute_squad_weight(conn, team["id"], starters)
        conn.execute("""
            UPDATE team_matches SET squad_weight=?
            WHERE team_id=? AND date=? AND opponent_id=(SELECT id FROM teams WHERE name=?)
        """, (weight, team["id"], date, away if team["id"] == team_h["id"] else home))

        print(f"  {team['name']}: {len(starters)} titulares + {len(subs)} cambios registrados | squad_weight={weight:.2f}")

    _record_team(team_h, starters_home, subs_home)
    _record_team(team_a, starters_away, subs_away)
    conn.commit()
    conn.close()


# ── MODO: APRENDER (actualizar estimador con datos reales) ────────────────────

def mode_learn():
    """
    Post-partido: recalcula patrones de titularidad para mejorar próximas estimaciones.
    Usa player_match_usage para derivar:
      - starter_rate: % veces que arranca titular
      - avg_minutes: minutos promedio jugados
      - sub_in_rate: % veces que entra de cambio
    Guarda en player_ratings como metadatos adicionales.
    """
    conn = _conn()

    # Equipos WC con datos de usage
    teams = conn.execute("""
        SELECT DISTINCT team_id FROM player_match_usage
    """).fetchall()

    updated = 0
    for t in teams:
        team_id = t["team_id"]
        players = conn.execute("""
            SELECT player_id,
                   COUNT(*) as appearances,
                   SUM(is_starter) as starts,
                   AVG(minutes_played) as avg_mins,
                   SUM(CASE WHEN sub_in_minute IS NOT NULL THEN 1 ELSE 0 END) as sub_ins
            FROM player_match_usage
            WHERE team_id=?
            GROUP BY player_id
        """, (team_id,)).fetchall()

        for p in players:
            if p["appearances"] == 0:
                continue
            starter_rate = p["starts"] / p["appearances"]
            avg_mins     = p["avg_mins"] or 0

            # Bonus al rating si es titular habitual y juega muchos minutos
            bonus = starter_rate * 0.5 + min(0.3, (avg_mins - 60) / 100)

            conn.execute("""
                UPDATE player_ratings
                SET rating = MIN(9.5, rating + ?)
                WHERE player_id=? AND rating IS NOT NULL
            """, (round(bonus, 3), p["player_id"]))
            updated += 1

    conn.commit()
    conn.close()
    print(f"Learn: {updated} ratings actualizados con datos de usage real")


# ── Utilidad squad_weight ─────────────────────────────────────────────────────

def _compute_squad_weight(conn, team_id: int, starter_names: list[str]) -> float:
    confirmed = conn.execute("""
        SELECT p.name FROM squad_selections ss
        JOIN players p ON p.id=ss.player_id
        WHERE ss.team_id=? AND ss.confirmed=1
    """, (team_id,)).fetchall()
    confirmed_norms = {_normalize(r["name"]) for r in confirmed}
    if not confirmed_norms:
        return 1.0
    hits = sum(1 for n in starter_names if _normalize(n) in confirmed_norms)
    return round(hits / max(len(starter_names), 1), 3)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_subs(subs_str: str) -> list[dict]:
    """Parse 'Camavinga:65:Tchouaméni,Thuram:78:Dembélé' → [{out, in, minute}]"""
    result = []
    if not subs_str:
        return result
    for entry in subs_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            result.append({"in": parts[0].strip(), "minute": int(parts[1]), "out": parts[2].strip()})
        elif len(parts) == 2:
            result.append({"in": parts[0].strip(), "minute": int(parts[1]), "out": ""})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestión de alineaciones WC2026")
    parser.add_argument("--mode", choices=["estimate", "confirm", "record", "learn"],
                        default="estimate")
    parser.add_argument("--date", help="Fecha YYYY-MM-DD")
    parser.add_argument("--fixture-id", type=int, help="API-Football fixture ID")
    parser.add_argument("--home", help="Equipo local")
    parser.add_argument("--away", help="Equipo visitante")
    parser.add_argument("--starters-home", help="Titulares local separados por coma")
    parser.add_argument("--starters-away", help="Titulares visitante separados por coma")
    parser.add_argument("--subs-home", help="Cambios local: 'PlayerIn:min:PlayerOut,...'")
    parser.add_argument("--subs-away", help="Cambios visitante: 'PlayerIn:min:PlayerOut,...'")
    args = parser.parse_args()

    if args.mode == "estimate":
        mode_estimate(args.date)

    elif args.mode == "confirm":
        mode_confirm(args.fixture_id)

    elif args.mode == "record":
        if not all([args.home, args.away, args.date]):
            print("--mode record requiere --home, --away, --date")
            sys.exit(1)
        sh = [n.strip() for n in (args.starters_home or "").split(",") if n.strip()]
        sa = [n.strip() for n in (args.starters_away or "").split(",") if n.strip()]
        subs_h = _parse_subs(args.subs_home or "")
        subs_a = _parse_subs(args.subs_away or "")
        mode_record(args.home, args.away, args.date, sh, sa, subs_h, subs_a)

    elif args.mode == "learn":
        mode_learn()
