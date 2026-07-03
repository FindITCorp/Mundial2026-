"""
auto_sync.py — AUTOSUFICIENCIA: sincroniza el Mundial completo sin intervencion.

Origen (03-jul): el dueño señaló que cada resultado/evaluación esperaba a que él
lo pidiera. Este script cierra ese ciclo en UN comando (o programado):

  1. Lee el calendario FIFA: partidos terminados (MatchStatus=0) que en la DB
     siguen con played=0 → carga marcador, marca played=1, evalúa el sello.
  2. Baja goles con minuto/autor del live de FIFA → fifa_match_goals.
  3. Corre el pipeline de stats: timeline (eventos), nombres de jugador, FDH.
  4. Reconstruye derivados (timing, perfiles).
  5. valida (validate_predictions) + integridad + commit + push.

Uso:
    python scripts/auto_sync.py            # todo el ciclo
    python scripts/auto_sync.py --dry-run  # solo muestra qué haría (sin escribir)
"""
import json
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB = BASE_DIR / "data" / "mundial2026.db"
COMP, SEASON = 17, 285023

# FIFA IdMatch -> id interno wc_matches para R32 (los ids NO coinciden en knockout)
FIFA2INT = {
    "400021518": 400021518, "400021516": 400021519, "400021513": 400021520,
    "400021522": 400021521, "400021514": 400021522, "400021523": 400021523,
    "400021520": 400021524, "400021512": 400021525, "400021525": 400021526,
    "400021524": 400021527, "400021519": 400021528, "400021526": 400021529,
    "400021527": 400021530, "400021515": 400021531, "400021521": 400021532,
    "400021517": 400021533,
}


def _fifa(path):
    req = urllib.request.Request(f"https://api.fifa.com/api/v3/{path}",
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=25))


def _run(cmd, desc):
    print(f"  → {desc}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       cwd=str(BASE_DIR), encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()
    for line in tail[-2:]:
        print(f"     {line}")
    return r.returncode == 0


def sync(dry=False):
    conn = sqlite3.connect(str(DB))
    cal = _fifa(f"calendar/matches?idCompetition={COMP}&idSeason={SEASON}&count=300")
    finished = {m["IdMatch"]: m for m in cal["Results"]
                if m.get("MatchStatus") == 0 and m.get("HomeTeamScore") is not None}

    new_results = []
    for fifa_id, m in finished.items():
        internal = FIFA2INT.get(fifa_id)
        if not internal:
            continue
        row = conn.execute("SELECT played, home_team_name, away_team_name FROM wc_matches WHERE id=?",
                           (internal,)).fetchone()
        if not row or row[0] == 1:
            continue
        sh, sa = m["HomeTeamScore"], m["AwayTeamScore"]
        new_results.append((internal, fifa_id, row[1], row[2], sh, sa, m.get("IdStage")))

    if not new_results:
        print("Sin partidos nuevos terminados. DB al día.")
    for internal, fifa_id, hn, an, sh, sa, stage in new_results:
        print(f"NUEVO RESULTADO: {hn} {sh}-{sa} {an} (interno {internal})")
        if dry:
            continue
        conn.execute("UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=?",
                     (sh, sa, internal))
        conn.execute("UPDATE match_predictions SET evaluated=1 WHERE match_id=?", (internal,))
        # goles con minuto desde el live
        try:
            liv = _fifa(f"live/football/{COMP}/{SEASON}/{stage}/{fifa_id}")
            for side in ("HomeTeam", "AwayTeam"):
                t = liv.get(side) or {}
                tid_row = conn.execute("SELECT home_team_id, away_team_id FROM wc_matches WHERE id=?",
                                       (internal,)).fetchone()
                tid = tid_row[0] if side == "HomeTeam" else tid_row[1]
                for g in (t.get("Goals") or []):
                    mins = g.get("Minute")
                    if mins is None:
                        continue
                    mnum = int(str(mins).split("+")[0].rstrip("'"))
                    conn.execute("INSERT OR IGNORE INTO fifa_match_goals (match_id,team_id,scorer,minute,type) "
                                 "VALUES (?,?,?,?,?)", (internal, tid, str(g.get("IdPlayer")), mnum, str(g.get("Type"))))
        except Exception as e:
            print(f"  (goles live no disponibles: {e})")
    conn.commit()
    conn.close()

    if dry or not new_results:
        return bool(new_results)

    print("\nPIPELINE DE STATS:")
    _run("python scripts/fetch_fifa_timeline.py", "timeline de eventos")
    _run("python scripts/fetch_fifa_player_names.py", "nombres de jugador nuevos")
    _run("python scripts/fetch_fifa_stats.py", "FDH 142 stats")
    _run("python scripts/rebuild_wc_timing.py", "timing por franjas")
    _run("python scripts/refresh_team_avgs.py", "perfiles de equipo")
    _run("python scripts/validate_predictions.py --all", "validador de sellos")

    print("\nCOMMIT + PUSH:")
    _run('git add -A -- data/mundial2026.db && git commit -m "auto-sync: resultados+stats [auto_sync.py]" && git push origin main',
         "commit y push")
    return True


if __name__ == "__main__":
    sync(dry="--dry-run" in sys.argv)
