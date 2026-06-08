"""
Refresca teams.possession_avg / goals_scored_avg / goals_conceded_avg
a partir de match_team_stats (stats reales de Sofascore).

Filosofía conservadora:
- Mínimo 3 partidos para que los datos reales tengan peso significativo
- El peso crece lentamente y se limita al 60% (nunca reemplaza el historial completo)
- Cada partido se pondera por la calidad del rival (rank del oponente)
  para que un amistoso vs rival débil no distorsione el promedio de una selección fuerte
- La posesión sí se actualiza desde partido 1 (es más estable que los goles)
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Peso máximo que los datos reales pueden tener sobre el historial
MAX_BLEND_GOALS = 0.50   # máximo 50% para goles (necesita datos sólidos)
MAX_BLEND_POSS  = 0.65   # posesión es más estable, hasta 65%

# Mínimo de partidos para que los goles reales empiecen a influir
MIN_MATCHES_GOALS = 3

def _opp_weight(opp_rank: int) -> float:
    """Peso por calidad del rival. rank=1→1.40, rank=50→1.0, rank=100→0.65, rank=150+→0.45"""
    if opp_rank is None or opp_rank <= 0:
        return 0.80
    return max(0.45, min(1.40, 1.0 + (50 - opp_rank) * 0.008))

def refresh(db_path=DB):
    conn = sqlite3.connect(db_path)
    updated = []

    for (tid,) in conn.execute("SELECT DISTINCT team_id FROM match_team_stats").fetchall():
        rows = conn.execute("""
            SELECT mts.possession, mts.xg, wm.score_home, wm.score_away,
                   mts.is_home, mts.team_id,
                   CASE WHEN mts.is_home=1 THEN ht_away.fifa_ranking
                        ELSE ht_home.fifa_ranking END AS opp_rank
            FROM match_team_stats mts
            JOIN wc_matches wm ON wm.id = mts.match_id
            LEFT JOIN teams ht_home ON ht_home.id = wm.home_team_id
            LEFT JOIN teams ht_away ON ht_away.id = wm.away_team_id
            WHERE mts.team_id = ?
            ORDER BY wm.date DESC LIMIT 10
        """, (tid,)).fetchall()
        if not rows:
            continue

        ex = conn.execute(
            "SELECT possession_avg, goals_scored_avg, goals_conceded_avg FROM teams WHERE id=?",
            (tid,)
        ).fetchone()
        if not ex:
            continue
        ex_poss, ex_gf, ex_ga = ex
        n = len(rows)

        # ── Posesión: media simple ponderada por rival (actualiza desde partido 1) ──
        poss_num = poss_den = 0.0
        for r in rows:
            if r[0] is None:
                continue
            w = _opp_weight(r[6])
            poss_num += r[0] * w
            poss_den += w
        avg_poss = poss_num / poss_den if poss_den else (ex_poss or 50.0)

        # ── Goles: solo si hay suficientes partidos ──────────────────────────────
        if n >= MIN_MATCHES_GOALS:
            gf_num = ga_num = g_den = 0.0
            for r in rows:
                sh, sa, is_home, opp_rank = r[2], r[3], r[4], r[6]
                gf = (sh if is_home else sa) or 0
                ga = (sa if is_home else sh) or 0
                w = _opp_weight(opp_rank)
                gf_num += gf * w
                ga_num += ga * w
                g_den  += w
            avg_gf = gf_num / g_den if g_den else (ex_gf or 1.5)
            avg_ga = ga_num / g_den if g_den else (ex_ga or 1.2)
            # Peso crece con más partidos pero se limita
            w_goals = min(MAX_BLEND_GOALS, 0.15 + n * 0.07)
        else:
            # Pocos partidos: mantener historial completo para goles
            avg_gf = ex_gf or 1.5
            avg_ga = ex_ga or 1.2
            w_goals = 0.0

        w_poss = min(MAX_BLEND_POSS, 0.20 + n * 0.08)

        new_poss = round(w_poss * avg_poss + (1 - w_poss) * (ex_poss or 50.0), 1)
        new_gf   = round(w_goals * avg_gf  + (1 - w_goals) * (ex_gf or 1.5),   2)
        new_ga   = round(w_goals * avg_ga  + (1 - w_goals) * (ex_ga or 1.2),   2)

        conn.execute(
            "UPDATE teams SET possession_avg=?, goals_scored_avg=?, goals_conceded_avg=? WHERE id=?",
            (new_poss, new_gf, new_ga, tid)
        )
        name = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()[0]
        updated.append(f"{name}(n={n},w_g={w_goals:.0%},w_p={w_poss:.0%})")

    conn.commit()
    conn.close()
    print(f"[refresh_team_avgs] {len(updated)} equipos actualizados:")
    for u in updated:
        print(f"  {u}")
    return updated

if __name__ == "__main__":
    refresh()
