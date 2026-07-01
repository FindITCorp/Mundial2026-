"""
fetch_fifa_player_names.py — Resuelve nombres de jugador para fifa_match_events.

Descubrimiento 01-jul: el feed de eventos de FIFA (fetch_fifa_timeline.py) NUNCA
trae PlayerName en los remates/goles (0 de 1962 remates tienen nombre) — solo
`player_fifa_id`. Sin nombre, NINGÚN análisis por jugador (remates, regates propios,
matchups jugador-vs-defensa) es posible desde esta fuente, aunque el minuto y el
tipo de evento sí estén completos. Se encontró que `api.fifa.com/api/v3/players/{id}`
SÍ resuelve el nombre — este script cachea ese mapeo en una tabla nueva
`fifa_player_names` (fifa_id -> nombre) y permite hacer JOIN en cualquier consulta
futura sin tener que re-pegarle a la API cada vez.

Uso:
    python scripts/fetch_fifa_player_names.py            # resuelve todos los IDs pendientes
    python scripts/fetch_fifa_player_names.py --limit 50  # solo los primeros 50 (prueba rápida)
"""
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"


def _fifa(path, timeout=15):
    req = urllib.request.Request("https://api.fifa.com/api/v3/" + path,
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS fifa_player_names (
        fifa_player_id TEXT PRIMARY KEY, name TEXT, country TEXT)""")


def sync(db_path=DB, limit=None, verbose=True):
    conn = sqlite3.connect(str(db_path))
    _ensure_table(conn)
    ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT player_fifa_id FROM fifa_match_events "
        "WHERE type_code IN (0,1,12,34,41,57) AND player_fifa_id IS NOT NULL AND player_fifa_id != '' "
        "AND player_fifa_id NOT IN (SELECT fifa_player_id FROM fifa_player_names)")]
    if limit:
        ids = ids[:limit]
    ok = fail = 0
    for i, pid in enumerate(ids, 1):
        try:
            d = _fifa(f"players/{pid}")
            nm = d.get("Name")
            name = nm[0]["Description"] if isinstance(nm, list) and nm else None
            country = d.get("IdCountry")
            if name:
                conn.execute("INSERT OR REPLACE INTO fifa_player_names (fifa_player_id, name, country) "
                             "VALUES (?,?,?)", (pid, name, country))
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        if verbose and i % 50 == 0:
            print(f"  [{i}/{len(ids)}] {ok} ok, {fail} fail...")
            conn.commit()
    conn.commit()
    if verbose:
        print(f"TOTAL: {ok} nombres resueltos, {fail} fallidos, de {len(ids)} pendientes.")
    conn.close()
    return {"ok": ok, "fail": fail}


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    sync(limit=lim)
