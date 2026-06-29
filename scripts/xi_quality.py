"""
xi_quality.py — Calidad del XI DESPLEGADO (rating de torneo de los 11 titulares).

La palanca de acierto que el modelo NO usa (auditoría 28-jun): predict_match pesa
Elo/plantilla, pero NO el rating real de torneo de los 11 que SALEN. En knockout
(sin rotación) o cuando hay XI confirmado, la calidad desplegada es señal directa.
Demostrado en Brasil-Japón: el modelo daba Japón por forma, pero el XI estelar real
daba Brasil 7.36 vs Japón 6.96 → Brasil (correcto por proceso).

Resuelve el muro del mapeo nombres FIFA↔Sofascore con emparejamiento DIFUSO
(normaliza acentos/mayúsculas + apellido), que casa la gran mayoría de titulares
(el match exacto solo daba ~62/1244). Fuente de rating: match_player_stats
(rating de torneo por jugador).

Uso:
    python scripts/xi_quality.py "Brazil" "Japan"            # usa XI del J1 como proxy
    python scripts/xi_quality.py "Brazil" "Japan" 13 31      # XI de match_id concretos
    from xi_quality import xi_rating
"""
import re
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"

NAME = {"Turkiye": "Turkey", "Cabo Verde": "Cape Verde", "United States": "USA",
        "Korea Republic": "South Korea", "Cote d'Ivoire": "Ivory Coast",
        "Czech Republic": "Czechia", "Curaçao": "Curacao"}


def _norm(s):
    s = s.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n"), ("ç", "c"), ("ã", "a"), ("õ", "o"), ("ü", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def _tid(conn, name):
    n = NAME.get(name, name)
    r = conn.execute("SELECT id FROM teams WHERE name=?", (n,)).fetchone()
    return r[0] if r else None


def _tourn_ratings(conn, tid):
    """{nombre_normalizado: rating_medio_torneo} desde match_player_stats."""
    out = {}
    for n, r in conn.execute(
            "SELECT player_name, AVG(rating) FROM match_player_stats "
            "WHERE team_id=? AND match_date>='2026-06-01' AND rating IS NOT NULL "
            "GROUP BY player_name", (tid,)):
        out[_norm(n)] = r
    return out


def _match_rating(key, ratings):
    if key in ratings:
        return ratings[key]
    # difuso: coincidencia por sufijo de apellido (>=6 chars)
    cand = [v for k, v in ratings.items() if (key[-6:] and (key[-6:] in k or k[-6:] in key))]
    return max(cand) if cand else None


def xi_rating(conn, team, match_id=None):
    """Rating medio del XI titular de `team`. Si match_id es None, usa el J1."""
    tid = _tid(conn, team)
    if not tid:
        return None
    if match_id is None:
        m = conn.execute("SELECT id FROM wc_matches WHERE (home_team_id=? OR away_team_id=?) "
                         "AND played=1 AND stage='group' ORDER BY date LIMIT 1", (tid, tid)).fetchone()
        match_id = m[0] if m else None
    xi = [n for (n,) in conn.execute(
        "SELECT player_name FROM fifa_lineups WHERE match_id=? AND team_id=? AND is_starter=1",
        (match_id, tid))]
    if not xi:
        return None
    ratings = _tourn_ratings(conn, tid)
    vals, missing = [], []
    for n in xi:
        r = _match_rating(_norm(n), ratings)
        (vals.append(r) if r else missing.append(n))
    if not vals:
        return None
    return {"team": team, "n_xi": len(xi), "n_rated": len(vals),
            "avg": sum(vals) / len(vals), "missing": missing}


def compare(conn, a, b, mid_a=None, mid_b=None):
    ra, rb = xi_rating(conn, a, mid_a), xi_rating(conn, b, mid_b)
    if not ra or not rb:
        return ra, rb, None
    gap = ra["avg"] - rb["avg"]
    edge = a if gap > 0.10 else (b if gap < -0.10 else "parejo")
    return ra, rb, {"gap": gap, "edge": edge}


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    a, b = sys.argv[1], sys.argv[2]
    ma = int(sys.argv[3]) if len(sys.argv) > 3 else None
    mb = int(sys.argv[4]) if len(sys.argv) > 4 else None
    ra, rb, cmp = compare(conn, a, b, ma, mb)
    for r in (ra, rb):
        if r:
            print(f"{r['team']:14} XI rating {r['avg']:.2f}  ({r['n_rated']}/{r['n_xi']} casados"
                  + (f"; sin rating: {', '.join(r['missing'])}" if r['missing'] else "") + ")")
    if cmp:
        print(f"→ ventaja de calidad del XI: {cmp['edge']} (brecha {cmp['gap']:+.2f})")
    conn.close()
