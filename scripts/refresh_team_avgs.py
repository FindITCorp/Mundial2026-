"""
Refresca teams.possession_avg / goals_scored_avg / goals_conceded_avg
a partir de match_team_stats (stats reales de Sofascore).

Filosofía:
- Peso por calidad del rival: ganarle al #1 vale mucho más que ganarle al #150
- Peso por resultado: win/draw/loss frente al nivel del rival
  · Ganar vs rival fuerte → goles ofensivos cuentan +60%
  · Perder vs rival débil → goles recibidos cuentan +60%, goles marcados -40%
- Decaimiento temporal: partidos recientes pesan más (half-life 90 días)
- Mínimo 3 partidos para que los goles cambien el historial
- Peso máximo 55% (los datos reales no reemplazan todo el historial)
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path
import math

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"

MAX_BLEND_GOALS = 0.55
MAX_BLEND_POSS  = 0.65
MIN_MATCHES_GOALS = 3
RECENCY_HALFLIFE_DAYS = 90  # partidos de hace 90 días valen la mitad


def _recency_weight(match_date_str: str) -> float:
    """Decaimiento exponencial: partido de hoy=1.0, hace 90 días=0.5"""
    try:
        md = datetime.strptime(match_date_str[:10], "%Y-%m-%d").date()
        days_ago = (date.today() - md).days
        return math.exp(-math.log(2) * days_ago / RECENCY_HALFLIFE_DAYS)
    except Exception:
        return 0.8


def _opp_weight(opp_rank: int) -> float:
    """
    Peso base por calidad del rival.
    rank 1  → 1.60  (selección de élite)
    rank 50 → 1.00  (promedio mundial)
    rank 150+ → 0.40 (rival débil)
    """
    if opp_rank is None or opp_rank <= 0:
        return 0.80
    return max(0.40, min(1.60, 1.0 + (50 - opp_rank) * 0.010))


def _result_factors(gf: int, ga: int, opp_rank: int):
    """
    Retorna (att_factor, def_factor) según resultado y rival.

    att_factor: multiplicador para los goles MARCADOS en este partido
    def_factor: multiplicador para los goles RECIBIDOS en este partido

    Lógica:
    - Win vs fuerte: marcar goles fue mérito real → att↑, encajar pocos también → def↑
    - Win vs débil:  era lo esperado → factores neutros
    - Draw vs fuerte: decente → ligero bonus att
    - Draw vs débil:  preocupante → ligera penalización att, def penalizada
    - Loss vs fuerte: normal → factores neutros/ligero descuento
    - Loss vs débil:  alarmante → att muy descontado, def penalizada fuerte
    """
    rank = opp_rank if (opp_rank and opp_rank > 0) else 50
    # nivel 0-1: 0=debilísimo, 1=el mejor
    strength = max(0.0, min(1.0, (150 - rank) / 149))

    if gf > ga:           # VICTORIA
        att = 1.0 + 0.60 * strength   # vs #1 → ×1.60, vs #150 → ×1.00
        def_ = 1.0 + 0.40 * strength  # mantener cero vs fuerte = mérito
    elif gf == ga:        # EMPATE
        att = 0.90 + 0.30 * strength   # empate vs #1 → ×1.20, vs #150 → ×0.90
        def_ = 0.90 + 0.20 * strength
    else:                 # DERROTA
        att = 0.60 + 0.30 * strength   # golear a Brasil y perder → ×0.90; perder vs débil → ×0.60
        def_ = 1.00 + 0.60 * (1 - strength)  # perder vs débil → goles recibidos cuentan ×1.60

    return att, def_


def refresh(db_path=DB):
    conn = sqlite3.connect(db_path)
    updated = []

    for (tid,) in conn.execute("SELECT DISTINCT team_id FROM match_team_stats").fetchall():
        rows = conn.execute("""
            SELECT mts.possession, mts.xg, wm.score_home, wm.score_away,
                   mts.is_home, mts.team_id, wm.date,
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

        # ── Posesión: media ponderada por rival + recencia ──────────────────────
        poss_num = poss_den = 0.0
        for r in rows:
            if r[0] is None:
                continue
            w = _opp_weight(r[7]) * _recency_weight(r[6])
            poss_num += r[0] * w
            poss_den += w
        avg_poss = poss_num / poss_den if poss_den else (ex_poss or 50.0)

        # ── Goles: solo si hay suficientes partidos ──────────────────────────────
        if n >= MIN_MATCHES_GOALS:
            gf_num = ga_num = g_den = 0.0
            for r in rows:
                sh, sa, is_home = r[2], r[3], r[4]
                match_date, opp_rank = r[6], r[7]
                gf = (sh if is_home else sa) or 0
                ga = (sa if is_home else sh) or 0

                opp_w  = _opp_weight(opp_rank)
                rec_w  = _recency_weight(match_date)
                att_f, def_f = _result_factors(gf, ga, opp_rank)

                base_w = opp_w * rec_w
                gf_num += gf * base_w * att_f
                ga_num += ga * base_w * def_f
                g_den  += base_w          # denominador neutral para promediar

            avg_gf = gf_num / g_den if g_den else (ex_gf or 1.5)
            avg_ga = ga_num / g_den if g_den else (ex_ga or 1.2)
            w_goals = min(MAX_BLEND_GOALS, 0.15 + n * 0.07)
        else:
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


def rebuild_timing_and_performance(db_path=DB):
    """
    Reconstruye team_goal_timing y team_performance_profile a partir de
    los datos actuales (martj42 CSV + match_events locales).
    Se llama automáticamente después de refresh() para mantener perfiles al día.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from scripts.build_goal_timing import (
            build_timing_profile,
            merge_from_match_events,
            save_to_db,
            build_team_performance_profile,
        )
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        print("[rebuild_timing] Reconstruyendo team_goal_timing …")
        profiles = build_timing_profile(since_year=2018)
        if profiles:
            profiles = merge_from_match_events(profiles, conn)
            save_to_db(profiles, conn)
        else:
            print("  [rebuild_timing] Sin datos del CSV — solo merge local")
            from collections import defaultdict
            profiles = defaultdict(lambda: {
                "scored": defaultdict(int), "conceded": defaultdict(int),
                "penalties_scored": 0, "penalties_conceded": 0, "matches": 0,
            })
            profiles = merge_from_match_events(dict(profiles), conn)
            if profiles:
                save_to_db(profiles, conn)

        print("[rebuild_timing] Reconstruyendo team_performance_profile …")
        build_team_performance_profile(conn)
        conn.close()
    except Exception as e:
        print(f"[rebuild_timing] Error (no crítico): {e}")


if __name__ == "__main__":
    refresh()
    rebuild_timing_and_performance()
