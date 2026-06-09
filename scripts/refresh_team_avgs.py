"""
Refresca teams.possession_avg / goals_scored_avg / goals_conceded_avg.

Fuentes (en orden de prioridad):
1. match_team_stats (Sofascore) — stats directos con xG
2. team_matches histórico — resultados con competition+opponent weighting

Filosofía:
- Peso por calidad del rival: ganarle al #1 vale mucho más que ganarle al #150
- Peso por competición: WC/Euros/Nations League >> clasificatorias >> amistosos
  · Clasificatorias CAF/CONMEBOL vs rivales débiles cuentan muy poco
- Peso por resultado: win vs fuerte cuenta más que win vs débil
- Decaimiento temporal: partidos recientes pesan más (half-life 90 días)
- Mínimo 5 partidos históricos para que los goles cambien el historial
- Peso máximo histórico 70% para los 48 equipos WC sin Sofascore
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path
import math

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"

MAX_BLEND_GOALS   = 0.55
MAX_BLEND_POSS    = 0.65
MIN_MATCHES_GOALS = 3
RECENCY_HALFLIFE_DAYS = 90

# Peso por competición — partidos vs rivales débiles en clasificatorias valen poco
_COMP_QUALITY = {
    "fifa world cup": 1.50,
    "world cup": 1.50,
    "copa america": 1.40,
    "copa americana": 1.40,
    "uefa euro": 1.40,
    "african cup of nations": 1.30,
    "africa cup of nations": 1.30,
    "afc asian cup": 1.25,
    "gold cup": 1.20,
    "concacaf gold cup": 1.20,
    "uefa nations league": 1.15,
    "nations league": 1.15,
    "concacaf nations league": 1.15,
    "world cup qualification": 0.90,
    "wcq": 0.90,
    "uefa euro qualification": 0.95,
    "african cup of nations qualification": 0.70,
    "africa cup of nations qualification": 0.70,
    "copa america qualification": 0.75,
    "fifa world cup qualification": 0.80,
    "afc asian cup qualification": 0.75,
    "friendly": 0.70,
    "international friendly": 0.70,
    "int. friendly": 0.70,
}

def _comp_weight(competition: str) -> float:
    if not competition:
        return 0.75
    c = competition.lower()
    for key, w in _COMP_QUALITY.items():
        if key in c:
            return w
    return 0.85  # torneo desconocido → peso neutro-bajo


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
        # Leer de wc_matches (partidos WC oficial)
        rows_wc = conn.execute("""
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
        # Leer de team_matches (amistosos Sofascore cargados manualmente)
        rows_tm = conn.execute("""
            SELECT mts.possession, mts.xg,
                   CASE WHEN mts.is_home=1 THEN tm.goals_for  ELSE tm.goals_against END,
                   CASE WHEN mts.is_home=1 THEN tm.goals_against ELSE tm.goals_for  END,
                   mts.is_home, mts.team_id, tm.date,
                   opp.fifa_ranking AS opp_rank
            FROM match_team_stats mts
            JOIN team_matches tm ON tm.id = mts.match_id
            JOIN teams opp ON opp.id = tm.opponent_id
            WHERE mts.team_id = ?
              AND NOT EXISTS (SELECT 1 FROM wc_matches wm2 WHERE wm2.id = mts.match_id)
            ORDER BY tm.date DESC LIMIT 10
        """, (tid,)).fetchall()
        rows = (rows_wc + rows_tm)[:10]  # máx 10, recientes primero
        rows.sort(key=lambda r: r[6] or "0000-00-00", reverse=True)
        rows = rows[:10]
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


def refresh_from_history(db_path=DB):
    """
    Calcula goals_scored_avg / goals_conceded_avg para los 48 equipos WC
    usando team_matches histórico con competition + opponent quality weighting.
    Se ejecuta para todos los equipos, complementando refresh() que solo toca
    los que tienen datos Sofascore.
    """
    conn = sqlite3.connect(db_path)
    updated = []

    wc_teams = conn.execute(
        "SELECT id, name, fifa_ranking FROM teams WHERE wc_group IS NOT NULL OR id IN "
        "(SELECT DISTINCT team_id FROM team_matches WHERE date>='2023-01-01')"
    ).fetchall()

    for tid, tname, t_rank in wc_teams:
        rows = conn.execute("""
            SELECT tm.date, tm.goals_for, tm.goals_against,
                   tm.competition, opp.fifa_ranking
            FROM team_matches tm
            LEFT JOIN teams opp ON opp.id = tm.opponent_id
            WHERE tm.team_id = ?
              AND tm.date >= '2022-01-01'
            ORDER BY tm.date DESC
            LIMIT 40
        """, (tid,)).fetchall()

        if len(rows) < 5:
            continue

        gf_num = ga_num = g_den = 0.0
        for match_date, gf, ga, competition, opp_rank in rows:
            opp_r = opp_rank or 80
            opp_w = _opp_weight(opp_r)
            rec_w = _recency_weight(match_date)
            comp_w = _comp_weight(competition or "")
            att_f, def_f = _result_factors(gf or 0, ga or 0, opp_r)

            # Descuento extra: clasificatorias vs rivales muy débiles
            # son infladores artificiales (ej: Senegal 5-0 vs #180)
            if opp_r > 120 and comp_w < 0.85:
                comp_w *= 0.60  # clasificatoria vs rival muy débil → casi irrelevante

            base_w = opp_w * rec_w * comp_w
            gf_num += (gf or 0) * base_w * att_f
            ga_num += (ga or 0) * base_w * def_f
            g_den  += base_w

        if g_den < 1.0:
            continue

        avg_gf = round(gf_num / g_den, 2)
        avg_ga = round(ga_num / g_den, 2)

        # Ancla con ranking FIFA: top 10 nunca bajan de 1.3 xG, bottom 48 nunca suben de 1.8
        rank = t_rank or 50
        rank_floor_gf = max(0.8, 1.8 - rank * 0.010)   # #1→1.79  #50→1.30  #100→0.80
        rank_ceil_ga  = min(1.8, 0.5 + rank * 0.012)   # #1→0.51  #50→1.10  #100→1.70

        avg_gf = max(avg_gf, rank_floor_gf * 0.70)  # suelo flexible
        avg_ga = min(avg_ga, rank_ceil_ga  * 1.30)  # techo flexible

        # Limites de sentido
        avg_gf = round(max(0.6, min(3.5, avg_gf)), 2)
        avg_ga = round(max(0.4, min(2.5, avg_ga)), 2)

        conn.execute(
            "UPDATE teams SET goals_scored_avg=?, goals_conceded_avg=? WHERE id=?",
            (avg_gf, avg_ga, tid)
        )
        updated.append((tname, avg_gf, avg_ga, len(rows)))

    conn.commit()
    conn.close()
    print(f"[refresh_from_history] {len(updated)} equipos actualizados desde team_matches:")
    for name, gf, ga, n in sorted(updated, key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {name:<22} GF={gf:.2f}  GA={ga:.2f}  (n={n})")
    return updated


if __name__ == "__main__":
    refresh_from_history()  # primero: histórico para todos los 48 equipos
    refresh()               # segundo: Sofascore encima (datos más recientes y exactos)
    rebuild_timing_and_performance()
