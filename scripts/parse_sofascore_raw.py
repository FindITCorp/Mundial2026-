"""
parse_sofascore_raw.py — Parsea el JSON CRUDO de Sofascore (data/sofascore_raw/{id}/)
que baja fetch_sofascore_pw.py y lo carga a la DB con TODOS los stats ricos.

Completa el pipeline: fetch_sofascore_pw.py guarda crudo → este script lo parsea →
match_team_stats (incl. goals_prevented, dribbles, big_chances, recuperaciones,
errores) y match_player_stats (minutos, rating, etc.).

El /statistics crudo trae lo que el JSON procesado NO tenía: paradas, GOLES
EVITADOS (shot-stopping del portero, métrica para porteros en racha tipo Eloy
Room), REGATES, ataques efectivos (big chances scored/missed), duelos, errores.

Empareja el partido por team_id (Sofascore) → wc_matches. Idempotente (UPSERT).

Uso:
    python scripts/parse_sofascore_raw.py            # parsea todos los dirs en sofascore_raw
    python scripts/parse_sofascore_raw.py 15186732   # solo ese event
    python scripts/parse_sofascore_raw.py 15186907 --fill-only   # SOLO rellena columnas
        # NULL (no sobrescribe lo que ya vino de FIFA) — para completar xG/regates en
        # partidos cargados solo desde FIFA. Ver discover_sofascore_urls.py + fetch_sofascore_pw.py.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
RAW = BASE_DIR / "data" / "sofascore_raw"

# nombre Sofascore -> teams.name DB (por si hace falta resolver por nombre)
NAME = {"Czech Republic": "Czechia", "Curaçao": "Curacao", "Türkiye": "Turkey",
        "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
        "Cabo Verde": "Cape Verde", "Congo DR": "DR Congo", "IR Iran": "Iran",
        "Korea Republic": "South Korea", "United States": "USA",
        "Bosnia & Herzegovina": "Bosnia and Herzegovina"}

# stat de Sofascore -> columna match_team_stats. Tipo: num | pct | pair (x/y)
STATMAP = {
    "Ball possession": ("possession", "pct"),
    "Expected goals": ("xg", "num"),
    "Big chances": ("clear_chances", "num"),
    "Total shots": ("shots_total", "num"),
    "Shots on target": ("shots_on_target", "num"),
    "Shots off target": ("shots_off_target", "num"),
    "Blocked shots": ("shots_blocked", "num"),
    "Shots inside box": ("shots_inside_box", "num"),
    "Shots outside box": ("shots_outside_box", "num"),
    "Big chances scored": ("big_chances_scored", "num"),
    "Big chances missed": ("big_chances_missed", "num"),
    "Touches in penalty area": ("touches_box", "num"),
    "Offsides": ("offsides", "num"),
    "Corner kicks": ("corners", "num"),
    "Fouls": ("fouls", "num"),
    "Free kicks": ("free_kicks", "num"),
    "Yellow cards": ("yellow_cards", "num"),
    "Red cards": ("red_cards", "num"),
    "Passes": ("passes_total", "num"),
    "Accurate passes": ("passes_accurate", "num"),
    "Total tackles": ("tackles_total", "num"),
    "Interceptions": ("interceptions", "num"),
    "Recoveries": ("recoveries", "num"),
    "Clearances": ("clearances", "num"),
    "Total saves": ("saves", "num"),
    "Goalkeeper saves": ("saves", "num"),
    "Goals prevented": ("goals_prevented", "num"),
    "Dispossessed": ("dispossessed", "num"),
    "Errors lead to a shot": ("errors_lead_shot", "num"),
    "Errors lead to a goal": ("errors_lead_goal", "num"),
    # pares x/y → dos columnas
    "Ground duels": (("duels_won", "duels_total"), "pair"),
    "Aerial duels": (("aerial_won", "aerial_total"), "pair"),
    "Dribbles": (("dribbles_won", "dribbles_total"), "pair"),
    "Crosses": (("crosses_accurate", "crosses_total"), "pair"),
    "Long balls": (("long_balls_accurate", "long_balls_total"), "pair"),
}


def _num(v):
    if v is None:
        return None
    s = str(v).strip().rstrip("%")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def _pair(v):
    m = re.match(r"(\d+)\s*/\s*(\d+)", str(v))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def parse_statistics(stats_json):
    """Devuelve {'home': {col: val}, 'away': {col: val}} desde /statistics."""
    out = {"home": {}, "away": {}}
    period = next((g for g in stats_json["statistics"] if g["period"] == "ALL"), None)
    if not period:
        return out
    for grp in period["groups"]:
        for it in grp["statisticsItems"]:
            spec = STATMAP.get(it["name"])
            if not spec:
                continue
            col, kind = spec
            for side in ("home", "away"):
                raw = it.get(side)
                if raw is None:
                    continue
                if kind == "pair":
                    won, tot = _pair(raw)
                    if won is not None:
                        out[side][col[0]] = won
                        out[side][col[1]] = tot
                else:
                    val = _num(raw)
                    if val is not None:
                        out[side][col] = val
    return out


def _upsert_team(conn, match_id, team_id, is_home, vals, fill_only=False):
    """fill_only=True: solo escribe columnas que están en NULL (no sobrescribe lo que
    ya vino de FIFA/otra fuente). Útil para completar xG/regates en partidos FIFA-only."""
    if not vals:
        return
    row = conn.execute(
        "SELECT * FROM match_team_stats WHERE match_id=? AND team_id=?",
        (match_id, team_id)).fetchone()
    if row:
        cols = [d[1] for d in conn.execute("PRAGMA table_info(match_team_stats)")]
        rowd = dict(zip(cols, row))
        rid = rowd["id"]
        writable = {c: v for c, v in vals.items()
                    if not fill_only or rowd.get(c) is None}
        if not writable:
            return
        sets = ", ".join(f"{c}=?" for c in writable)
        conn.execute(f"UPDATE match_team_stats SET {sets} WHERE id=?",
                     (*writable.values(), rid))
    else:
        cols = ["match_id", "team_id", "is_home", *vals.keys()]
        conn.execute(
            f"INSERT INTO match_team_stats ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            (match_id, team_id, 1 if is_home else 0, *vals.values()))


def _db_team_id(conn, sofa_team):
    """Resuelve el id DB desde el objeto team de Sofascore (por nombre)."""
    nm = NAME.get(sofa_team["name"], sofa_team["name"])
    r = conn.execute("SELECT id FROM teams WHERE name=?", (nm,)).fetchone()
    return r[0] if r else None


def parse_event(conn, ev_dir: Path, fill_only=False):
    ev_file = ev_dir / "event.json"
    st_file = ev_dir / "statistics.json"
    if not ev_file.exists() or not st_file.exists():
        return f"{ev_dir.name}: faltan event/statistics"
    ev = json.loads(ev_file.read_text(encoding="utf-8"))["event"]
    hid = _db_team_id(conn, ev["homeTeam"])
    aid = _db_team_id(conn, ev["awayTeam"])
    if not hid or not aid:
        return f"{ev_dir.name}: no resuelvo equipos ({ev['homeTeam']['name']}/{ev['awayTeam']['name']})"
    # Mapea por par de equipos a una etapa del Mundial (grupos o knockout),
    # NO a amistosos/clasificatorios. Prefiere el knockout (id alto) si hay ambos.
    row = conn.execute(
        "SELECT id FROM wc_matches WHERE home_team_id=? AND away_team_id=? "
        "AND stage IN ('group','R32','R16','QF','SF','Final','Third') "
        "ORDER BY (stage='group') ASC, id DESC LIMIT 1",
        (hid, aid)).fetchone()
    if not row:
        return f"{ev_dir.name}: sin partido en wc_matches"
    mid = row[0]
    stats = json.loads(st_file.read_text(encoding="utf-8"))
    parsed = parse_statistics(stats)
    _upsert_team(conn, mid, hid, True, parsed["home"], fill_only=fill_only)
    _upsert_team(conn, mid, aid, False, parsed["away"], fill_only=fill_only)
    nrich = len(parsed["home"])
    tag = " [fill-only]" if fill_only else ""
    return f"{ev_dir.name}{tag}: {ev['homeTeam']['name']} vs {ev['awayTeam']['name']} → {nrich} stats/equipo"


def run(event_ids=None, db_path=DB, fill_only=False):
    conn = sqlite3.connect(str(db_path))
    dirs = ([RAW / str(e) for e in event_ids] if event_ids
            else [d for d in RAW.iterdir() if d.is_dir()]) if RAW.exists() else []
    for d in dirs:
        print("  " + parse_event(conn, d, fill_only=fill_only))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    fill = "--fill-only" in sys.argv
    ids = [a for a in sys.argv[1:] if not a.startswith("--")] or None
    run(event_ids=ids, fill_only=fill)
