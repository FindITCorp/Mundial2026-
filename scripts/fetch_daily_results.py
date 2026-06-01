#!/usr/bin/env python3
"""
fetch_daily_results.py — Descarga resultados del día anterior desde football-data.org
y los registra en team_matches + actualiza Elo.

Uso:
    python scripts/fetch_daily_results.py              # ayer
    python scripts/fetch_daily_results.py 2026-06-03   # fecha específica
    python scripts/fetch_daily_results.py --dry-run    # solo muestra, no guarda

Requiere:
    FOOTBALL_DATA_API_KEY en .env o variable de entorno
    pip install requests python-dotenv
"""

import sys
import os
import json
import sqlite3
import requests
import argparse
from datetime import date, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
DB_PATH  = ROOT / "data" / "mundial2026.db"
ALIASES  = ROOT / "data" / "team_name_aliases.json"
ENV_FILE = ROOT / ".env"

# ── Cargar .env si existe ─────────────────────────────────────────────────────
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")

# football-data.org: áreas para selecciones nacionales
# Tier free cubre: WC Qualifiers, Nations League, amistosos internacionales
COMPETITIONS_INTL = [
    "WC",    # FIFA World Cup
    "EC",    # UEFA Euro
    "CL",    # solo referencia
    "WCQ",   # Qualifiers — no disponible en free, pero sí vía /matches?areas=
]

# Área FIFA = todas las selecciones del mundo
HEADERS = {"X-Auth-Token": API_KEY}
BASE_URL = "https://api.football-data.org/v4"

# ── Elo update (K-factor adaptativo) ─────────────────────────────────────────
ELO_K_BASE    = 20.0   # partidos amistosos
ELO_K_COMP    = 30.0   # partidos clasificatorios / torneos
ELO_K_TOURNEY = 40.0   # fases finales (WC, Copa America, Euro)

COMP_KEYWORDS_HIGH = ("world cup", "copa america", "euro championship",
                      "nations league final", "afcon", "asian cup")
COMP_KEYWORDS_MID  = ("qualifier", "wcq", "nations league", "gold cup",
                      "confederation")


def _elo_k(competition: str) -> float:
    c = (competition or "").lower()
    if any(kw in c for kw in COMP_KEYWORDS_HIGH):
        return ELO_K_TOURNEY
    if any(kw in c for kw in COMP_KEYWORDS_MID):
        return ELO_K_COMP
    return ELO_K_BASE


def _expected(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400))


def update_elo(conn, team_id: int, opp_id: int, result: str,
               competition: str, gf: int, ga: int):
    """Actualiza Elo de ambos equipos tras un partido."""
    def get_elo(tid):
        row = conn.execute("SELECT elo FROM team_elo WHERE team_id=?", (tid,)).fetchone()
        return row[0] if row else 1500.0

    def set_elo(tid, new_elo):
        conn.execute("""
            INSERT INTO team_elo (team_id, elo, peak_elo, matches, updated_at)
            VALUES (?, ?, ?, 1, date('now'))
            ON CONFLICT(team_id) DO UPDATE SET
                elo        = excluded.elo,
                peak_elo   = MAX(peak_elo, excluded.elo),
                matches    = matches + 1,
                updated_at = excluded.updated_at
        """, (tid, round(new_elo, 2), round(new_elo, 2)))

    elo_h = get_elo(team_id)
    elo_a = get_elo(opp_id)
    K     = _elo_k(competition)
    E_h   = _expected(elo_h, elo_a)

    # Score real: 1=W, 0.5=D, 0=L
    S_h = {"W": 1.0, "D": 0.5, "L": 0.0}.get(result, 0.5)

    # Goal difference bonus (±0.1 por gol de diferencia, máx ±0.3)
    gd = abs(gf - ga)
    gd_bonus = min(0.3, gd * 0.1) if gf > ga else (-min(0.3, gd * 0.1) if ga > gf else 0)
    S_h_adj = max(0.0, min(1.0, S_h + gd_bonus))

    new_elo_h = elo_h + K * (S_h_adj - E_h)
    new_elo_a = elo_a + K * ((1 - S_h_adj) - (1 - E_h))

    set_elo(team_id, new_elo_h)
    set_elo(opp_id, new_elo_a)
    return round(elo_h, 0), round(new_elo_h, 0), round(elo_a, 0), round(new_elo_a, 0)


# ── Team name resolver ────────────────────────────────────────────────────────

def load_aliases() -> dict:
    if ALIASES.exists():
        return json.loads(ALIASES.read_text())
    return {}


def resolve_team(name: str, aliases: dict, conn) -> int | None:
    """Resuelve nombre externo → team_id interno. None si no se encuentra."""
    canonical = aliases.get(name, name)
    row = conn.execute("SELECT id FROM teams WHERE name=?", (canonical,)).fetchone()
    if row:
        return row[0]
    # Búsqueda fuzzy: nombre contiene o está contenido
    row = conn.execute(
        "SELECT id, name FROM teams WHERE name LIKE ? OR ? LIKE '%' || name || '%' LIMIT 1",
        (f"%{canonical}%", canonical)
    ).fetchone()
    if row:
        return row[0]
    return None


# ── football-data.org API ─────────────────────────────────────────────────────

def fetch_matches_football_data(target_date: str) -> list[dict]:
    """
    football-data.org — requiere host allowlist en el dashboard.
    Ve a: https://www.football-data.org/client → 'Edit' → Client Origin = '*'
    """
    if not API_KEY:
        return []

    url = f"{BASE_URL}/matches"
    params = {"dateFrom": target_date, "dateTo": target_date}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 403:
            err = resp.text.lower()
            if "allowlist" in err or "host" in err:
                print("  ⚠️  football-data.org: host no permitido")
                print("     Solución: ve a https://www.football-data.org/client")
                print("     → Edit → Client Origin → escribe '*' → Save")
            return []
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  ❌ Error football-data.org: {e}")
        return []

    matches = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        full = m.get("score", {}).get("fullTime", {})
        hg = full.get("home")
        ag = full.get("away")
        if hg is None or ag is None:
            continue
        matches.append({
            "home_name":   m["homeTeam"]["name"],
            "away_name":   m["awayTeam"]["name"],
            "home_goals":  int(hg),
            "away_goals":  int(ag),
            "competition": m.get("competition", {}).get("name", "International"),
            "date":        m.get("utcDate", target_date)[:10],
            "source":      "football-data.org",
        })
    return matches


def fetch_matches_espn(target_date: str) -> list[dict]:
    """
    ESPN API pública (sin key, sin restricción de host).
    Endpoint: site.api.espn.com — cubre selecciones nacionales y torneos FIFA.
    """
    # Formato ESPN: YYYYMMDD
    espn_date = target_date.replace("-", "")

    # Liga groups para selecciones nacionales en ESPN
    INTL_LEAGUES = [
        ("fifa.world",         "FIFA World Cup"),
        ("fifa.worldq.conmebol", "CONMEBOL WC Qualifier"),
        ("fifa.worldq.uefa",   "UEFA WC Qualifier"),
        ("fifa.worldq.concacaf", "CONCACAF WC Qualifier"),
        ("fifa.worldq.afc",    "AFC WC Qualifier"),
        ("fifa.worldq.caf",    "CAF WC Qualifier"),
        ("uefa.nations",       "UEFA Nations League"),
        ("conmebol.america",   "Copa America"),
        ("uefa.euro",          "UEFA Euro"),
        ("concacaf.nations",   "CONCACAF Nations League"),
        ("concacaf.gold",      "CONCACAF Gold Cup"),
        ("afc.asian.qual",     "AFC Asian Cup Qualifier"),
        ("caf.nations",        "AFCON"),
        ("fifa.friendly.m",    "International Friendly"),
    ]

    all_matches = []
    base = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    for league_slug, league_name in INTL_LEAGUES:
        url = f"{base}/{league_slug}/scoreboard"
        try:
            resp = requests.get(url, params={"dates": espn_date}, timeout=10)
            if not resp.ok:
                continue
            data = resp.json()
        except Exception:
            continue

        for event in data.get("events", []):
            comp_list = event.get("competitions", [])
            if not comp_list:
                continue
            comp = comp_list[0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status not in ("STATUS_FINAL", "STATUS_FULL_TIME"):
                continue

            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            try:
                hg = int(home.get("score", 0))
                ag = int(away.get("score", 0))
            except (ValueError, TypeError):
                continue

            match_date = (event.get("date") or target_date)[:10]

            all_matches.append({
                "home_name":   home.get("team", {}).get("displayName", ""),
                "away_name":   away.get("team", {}).get("displayName", ""),
                "home_goals":  hg,
                "away_goals":  ag,
                "competition": league_name,
                "date":        match_date,
                "source":      "espn",
            })

    return all_matches


def fetch_matches_for_date(target_date: str) -> list[dict]:
    """
    Intenta fuentes en orden: football-data.org → TheSportsDB.
    Retorna la primera que devuelva resultados.
    """
    # 1. football-data.org (más preciso para datos de goles, requiere host config)
    if API_KEY:
        matches = fetch_matches_football_data(target_date)
        if matches:
            print(f"  📡 Fuente: football-data.org ({len(matches)} partidos)")
            return matches

    # 2. ESPN API pública (sin key, sin restricciones)
    print("  📡 Usando ESPN API (pública, sin API key)...")
    matches = fetch_matches_espn(target_date)
    if matches:
        print(f"  ✅ ESPN: {len(matches)} partido(s) internacional(es)")
    return matches


# ── Registro en DB ─────────────────────────────────────────────────────────────

def already_exists(conn, team_id: int, opp_id: int, match_date: str) -> bool:
    row = conn.execute("""
        SELECT 1 FROM team_matches
        WHERE team_id=? AND opponent_id=? AND date=?
    """, (team_id, opp_id, match_date)).fetchone()
    return row is not None


def register_match(conn, aliases: dict, match: dict, dry_run: bool = False) -> bool:
    """Registra un partido (ambos sentidos) y actualiza Elo. Retorna True si se insertó."""
    home_id = resolve_team(match["home_name"], aliases, conn)
    away_id = resolve_team(match["away_name"], aliases, conn)

    if not home_id or not away_id:
        missing = []
        if not home_id: missing.append(match["home_name"])
        if not away_id: missing.append(match["away_name"])
        print(f"  ⚠️  Equipo(s) no encontrado(s): {', '.join(missing)}")
        return False

    if already_exists(conn, home_id, away_id, match["date"]):
        print(f"  ↩️  Ya existe: {match['home_name']} vs {match['away_name']} ({match['date']})")
        return False

    hg = match["home_goals"]
    ag = match["away_goals"]

    h_result = "W" if hg > ag else ("D" if hg == ag else "L")
    a_result = "W" if ag > hg else ("D" if ag == hg else "L")

    if dry_run:
        print(f"  [DRY] {match['home_name']} {hg}-{ag} {match['away_name']} ({match['competition']})")
        return True

    # Insertar ambos sentidos
    for team_id, opp_id, opp_name, gf, ga, result, venue in [
        (home_id, away_id, match["away_name"], hg, ag, h_result, "home"),
        (away_id, home_id, match["home_name"], ag, hg, a_result, "away"),
    ]:
        conn.execute("""
            INSERT INTO team_matches
                (team_id, opponent_id, opponent_name, date, competition,
                 goals_for, goals_against, result, venue)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (team_id, opp_id, opp_name, match["date"],
              match["competition"], gf, ga, result, venue))

    # Actualizar Elo
    elo_bef_h, elo_aft_h, elo_bef_a, elo_aft_a = update_elo(
        conn, home_id, away_id, h_result,
        match["competition"], hg, ag
    )

    conn.commit()

    delta_h = elo_aft_h - elo_bef_h
    delta_a = elo_aft_a - elo_bef_a
    print(f"  ✅ {match['home_name']} {hg}-{ag} {match['away_name']} "
          f"| Elo: {elo_bef_h}→{elo_aft_h} ({delta_h:+.0f}) "
          f"/ {elo_bef_a}→{elo_aft_a} ({delta_a:+.0f})")
    return True


# ── Manual entry fallback ─────────────────────────────────────────────────────

def register_manual(conn, aliases: dict, dry_run: bool):
    """Modo interactivo para registrar resultados manualmente (sin API)."""
    print("\n📝 Registro manual de resultados")
    print("   Formato: 'Equipo A <goles>-<goles> Equipo B [competición]'")
    print("   Ejemplo: 'Argentina 2-0 Colombia Nations League'")
    print("   'q' para salir\n")

    while True:
        line = input("Resultado: ").strip()
        if line.lower() in ("q", "quit", "exit", ""):
            break

        # Parser simple: detecta patrón N-N en el medio
        import re
        m = re.match(r"^(.+?)\s+(\d+)-(\d+)\s+(.+?)(?:\s{2,}(.+))?$", line)
        if not m:
            print("  ❌ Formato no reconocido. Ej: Argentina 2-0 Colombia")
            continue

        home_name = m.group(1).strip()
        hg        = int(m.group(2))
        ag        = int(m.group(3))
        away_name = m.group(4).strip()
        comp      = (m.group(5) or "International Friendly").strip()

        match = {
            "home_name":   home_name,
            "away_name":   away_name,
            "home_goals":  hg,
            "away_goals":  ag,
            "competition": comp,
            "date":        date.today().isoformat(),
        }
        register_match(conn, aliases, match, dry_run=dry_run)


# ── Main ───────────────────────────────────────────────────────────────────────

def apply_pending_json_results(conn, aliases: dict, dry_run: bool = False) -> int:
    """
    Lee todos los JSON en data/daily_results/ y aplica los que aún no están en DB.
    Esto sincroniza la DB con los resultados que GitHub Actions descargó y pusheó.
    """
    results_dir = ROOT / "data" / "daily_results"
    if not results_dir.exists():
        return 0

    json_files = sorted(results_dir.glob("*.json"))
    if not json_files:
        return 0

    total = 0
    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
        except Exception:
            continue
        for m in data.get("matches", []):
            # El JSON de GitHub Actions usa claves "home"/"away", el manual usa "home_name"/"away_name"
            match = {
                "home_name":   m.get("home_name") or m.get("home", ""),
                "away_name":   m.get("away_name") or m.get("away", ""),
                "home_goals":  m.get("home_goals", 0),
                "away_goals":  m.get("away_goals", 0),
                "competition": m.get("competition", "International"),
                "date":        m.get("date", jf.stem),
            }
            if match["home_name"] and match["away_name"]:
                ok = register_match(conn, aliases, match, dry_run=dry_run)
                if ok:
                    total += 1
    return total


def main():
    parser = argparse.ArgumentParser(description="Descarga y registra resultados del día")
    parser.add_argument("date", nargs="?", help="Fecha YYYY-MM-DD (default: ayer)")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no guardar")
    parser.add_argument("--manual", action="store_true", help="Entrada manual interactiva")
    parser.add_argument("--apply-pending", action="store_true",
                        help="Aplica todos los JSON pendientes de data/daily_results/ a la DB")
    parser.add_argument("--days", type=int, default=1,
                        help="Cuántos días hacia atrás procesar (default: 1)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    aliases = load_aliases()

    if args.manual:
        register_manual(conn, aliases, dry_run=args.dry_run)
        conn.close()
        return

    if args.apply_pending:
        print("📂 Aplicando resultados pendientes desde data/daily_results/...")
        total = apply_pending_json_results(conn, aliases, dry_run=args.dry_run)
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}✨ {total} partido(s) aplicado(s)")
        conn.close()
        return

    # Determinar rango de fechas
    if args.date:
        dates = [args.date]
    else:
        today = date.today()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(1, args.days + 1)]

    total_new = 0
    for target_date in dates:
        print(f"\n📅 Procesando {target_date}...")
        matches = fetch_matches_for_date(target_date)

        if not matches:
            print("  📭 Sin partidos desde APIs — prueba --manual para registrar directamente")
            print("  💡 O usa --apply-pending para leer JSONs descargados por GitHub Actions")
            continue

        print(f"  📊 {len(matches)} partido(s) encontrado(s):")
        for m in matches:
            ok = register_match(conn, aliases, m, dry_run=args.dry_run)
            if ok:
                total_new += 1

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}✨ {total_new} partido(s) nuevo(s) registrado(s)")
    conn.close()


if __name__ == "__main__":
    main()
