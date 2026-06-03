"""
models/tournament.py — Simulador Monte Carlo del Mundial 2026 completo.

Simula el torneo entero miles de veces y agrega probabilidades:
  • Fase de grupos: 12 grupos de 4 (round-robin, 6 partidos c/u)
  • Clasificación con tiebreakers FIFA (pts → dif. goles → goles a favor)
  • Clasifican 32: 12 primeros + 12 segundos + 8 mejores terceros
  • Eliminatorias: 16avos → octavos → cuartos → semis → final
    (empates resueltos con prórroga + penaltis simulados)

Para cada equipo reporta P(avanzar de grupo), P(octavos/cuartos/semis/final)
y P(campeón).

El motor de λ es una versión rápida y vectorizable del modelo principal
(match_predictor): combina Elo absoluto con ataque/defensa recientes
(strength-of-schedule + regularización ya aplicados en _get_form).

API:
  TournamentSimulator(db_path).run(n_sims=5000) -> dict
"""
from __future__ import annotations
import sqlite3
import math
import random
from collections import defaultdict
from pathlib import Path

from models.match_predictor import _get_form, BASE_GOALS

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
GROUPS = list("ABCDEFGHIJKL")

# Anfitriones con ligera localía en fase de grupos
HOSTS = {"USA", "Mexico", "Canada"}
HOST_BONUS = 0.06   # +6% λ jugando "en casa"


class TournamentSimulator:
    def __init__(self, db_path: str | Path = DB_PATH, seed: int | None = None):
        self.db_path = Path(db_path)
        self.rng = random.Random(seed)
        self._load()

    # ── Carga de datos ──────────────────────────────────────────────────────
    def _load(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Grupos desde wc_group_draw (sorteo válido); si no existe, error guía
        draw = conn.execute("SELECT team_id, grp FROM wc_group_draw").fetchall()
        if not draw:
            conn.close()
            raise RuntimeError(
                "Falta el sorteo de grupos. Ejecuta:  python scripts/seed_wc_groups.py")

        self.groups: dict[str, list[int]] = defaultdict(list)
        for r in draw:
            self.groups[r["grp"]].append(r["team_id"])

        # Fuerzas por equipo (Elo + att/def recientes), precalculadas una vez
        self.strength: dict[int, dict] = {}
        self.name: dict[int, str] = {}
        all_ids = [tid for ids in self.groups.values() for tid in ids]
        for tid in all_ids:
            elo_row = conn.execute("SELECT elo FROM team_elo WHERE team_id=?", (tid,)).fetchone()
            nm_row = conn.execute("SELECT name FROM teams WHERE id=?", (tid,)).fetchone()
            form = _get_form(conn, tid)
            self.strength[tid] = {
                "elo": elo_row["elo"] if elo_row else 1500.0,
                "att": form["avg_gf"],
                "deff": form["avg_ga"],
            }
            self.name[tid] = nm_row["name"] if nm_row else f"Team{tid}"
        conn.close()

    # ── Motor de λ rápido (coherente con match_predictor) ────────────────────
    def _lambdas_base(self, h: int, a: int, neutral: bool = True) -> tuple[float, float]:
        sh, sa = self.strength[h], self.strength[a]
        elo_diff = sh["elo"] - sa["elo"]
        adj = 0 if neutral else 50
        e_h = 1.0 / (1.0 + 10 ** (-(elo_diff + adj) / 400))

        # Ataque = blend forma (avg_gf) + Elo absoluto (coherente con match_predictor)
        h_att = (min(1.70, sh["att"] / BASE_GOALS) ** 0.55) * ((sh["elo"] / 1550.0) ** 0.45)
        a_att = (min(1.70, sa["att"] / BASE_GOALS) ** 0.55) * ((sa["elo"] / 1550.0) ** 0.45)
        # Defensa
        h_def = (1.0 / max(0.60, sh["deff"] / BASE_GOALS)) ** 0.55
        a_def = (1.0 / max(0.60, sa["deff"] / BASE_GOALS)) ** 0.55
        # Factor Elo sobre λ (ancla reforzada, exp 0.90)
        elo_f_h = (0.7 + e_h * 0.6)
        elo_f_a = (0.7 + (1 - e_h) * 0.6)

        lh = BASE_GOALS * h_att * a_def * (elo_f_h ** 0.90)
        la = BASE_GOALS * a_att * h_def * (elo_f_a ** 0.90)

        # Localía de anfitriones
        if not neutral:
            if self.name[h] in HOSTS:
                lh *= 1 + HOST_BONUS
            if self.name[a] in HOSTS:
                la *= 1 + HOST_BONUS

        return min(max(lh, 0.25), 2.90), min(max(la, 0.25), 2.90)

    def _poisson(self, mu: float) -> int:
        if mu <= 0:
            return 0
        L = math.exp(-mu); k = 0; p = 1.0
        while True:
            k += 1
            p *= self.rng.random()
            if p <= L:
                return k - 1

    def _sim_penalty_shootout(self, h: int, a: int) -> int:
        """
        Cadena de Markov para penales — basado en:
        'A Markovian model for football penalty shootout' (Taylor & Francis, 2026)

        Parámetros calibrados con datos históricos de Mundiales/Euros:
          p_base   = 0.725  tasa de conversión base (72.5%)
          momentum = -0.179 impacto psicológico si rival convierte el penal anterior

        Formato: 5 rondas alternadas (h,a,h,a,...), luego muerte súbita.
        El Elo del equipo da un pequeño edge (±2pp) para capturar calidad.
        """
        P_BASE    = 0.725
        MOMENTUM  = -0.179   # penalización si rival convirtió su último penal

        # Edge por Elo: ±2pp máximo (penales son casi lotería)
        elo_h = self.strength[h]["elo"]
        elo_a = self.strength[a]["elo"]
        elo_edge = min(0.02, max(-0.02, (elo_h - elo_a) / 2000))

        p_h = max(0.55, min(0.85, P_BASE + elo_edge))
        p_a = max(0.55, min(0.85, P_BASE - elo_edge))

        scored_h, scored_a = [], []
        prev_scored_h = prev_scored_a = False

        # 5 rondas obligatorias
        for rnd in range(5):
            # Home dispara
            p_h_adj = p_h + (MOMENTUM if prev_scored_a else 0)
            p_h_adj = max(0.50, min(0.90, p_h_adj))
            sh = self.rng.random() < p_h_adj
            scored_h.append(sh)
            prev_scored_h = sh

            # Away dispara
            p_a_adj = p_a + (MOMENTUM if prev_scored_h else 0)
            p_a_adj = max(0.50, min(0.90, p_a_adj))
            sa = self.rng.random() < p_a_adj
            scored_a.append(sa)
            prev_scored_a = sa

            # Verificar si ya es matemáticamente imposible empatar antes de 5
            if rnd < 4:
                remaining = 4 - rnd
                gh_now = sum(scored_h); ga_now = sum(scored_a)
                if gh_now - ga_now > remaining or ga_now - gh_now > remaining:
                    break   # resultado decidido anticipadamente

        gh = sum(scored_h); ga = sum(scored_a)
        if gh == ga:
            # Muerte súbita
            for _ in range(20):   # cap anti-loop
                p_h_adj = max(0.50, p_h + (MOMENTUM if prev_scored_a else 0))
                sh = self.rng.random() < p_h_adj
                prev_scored_h = sh
                p_a_adj = max(0.50, p_a + (MOMENTUM if prev_scored_h else 0))
                sa = self.rng.random() < p_a_adj
                prev_scored_a = sa
                gh += sh; ga += sa
                if sh != sa:
                    break
                if not sh and not sa:
                    break   # ambos fallan en muerte súbita → break

        return h if gh >= ga else a

    def _sim_match(self, h: int, a: int, neutral: bool = True,
                   knockout: bool = False,
                   fatigue_h: float = 0.0, fatigue_a: float = 0.0) -> tuple[int, int, int]:
        """Devuelve (goles_h, goles_a, ganador_id). En knockout nunca hay empate."""
        lh, la = self._lambdas(h, a, neutral, fatigue_h, fatigue_a)
        gh, ga = self._poisson(lh), self._poisson(la)
        if not knockout:
            winner = h if gh > ga else (a if ga > gh else 0)
            return gh, ga, winner
        if gh == ga:
            # Prórroga: mini-Poisson (30 min ≈ λ/3)
            eh, ea = self._poisson(lh / 3), self._poisson(la / 3)
            gh += eh; ga += ea
            if gh == ga:
                # Penales — modelo Markov (reemplaza simple random Elo)
                winner = self._sim_penalty_shootout(h, a)
                return gh, ga, winner
        return gh, ga, (h if gh > ga else a)

    # ── Fase de grupos ────────────────────────────────────────────────────────
    def _sim_group(self, group_ids: list[int]) -> list[dict]:
        """Round-robin; devuelve tabla ordenada con tiebreakers FIFA."""
        stats = {tid: {"pts": 0, "gf": 0, "ga": 0, "id": tid} for tid in group_ids}
        for i in range(len(group_ids)):
            for j in range(i + 1, len(group_ids)):
                h, a = group_ids[i], group_ids[j]
                neutral = not (self.name[h] in HOSTS or self.name[a] in HOSTS)
                gh, ga, w = self._sim_match(h, a, neutral=neutral)
                stats[h]["gf"] += gh; stats[h]["ga"] += ga
                stats[a]["gf"] += ga; stats[a]["ga"] += gh
                if w == h: stats[h]["pts"] += 3
                elif w == a: stats[a]["pts"] += 3
                else:
                    stats[h]["pts"] += 1; stats[a]["pts"] += 1
        table = list(stats.values())
        for s in table:
            s["gd"] = s["gf"] - s["ga"]
        # Tiebreakers: pts → gd → gf → desempate aleatorio reproducible
        table.sort(key=lambda s: (s["pts"], s["gd"], s["gf"], self.rng.random()),
                   reverse=True)
        return table

    def _lambdas(self, h: int, a: int, neutral: bool = True,
                fatigue_h: float = 0.0, fatigue_a: float = 0.0):
        """Calcula lambdas con penalización opcional por fatiga acumulada."""
        lh, la = self._lambdas_base(h, a, neutral)
        # Fatiga: cada punto reduce λ hasta 6% máx (calibrado de Liverpool/PMC 2024)
        lh *= max(0.94, 1.0 - fatigue_h)
        la *= max(0.94, 1.0 - fatigue_a)
        return lh, la

    # ── Torneo completo (un sorteo) ───────────────────────────────────────────
    def _sim_tournament(self) -> dict[int, str]:
        """Devuelve {team_id: ronda_máxima_alcanzada}."""
        reached = {tid: "group" for ids in self.groups.values() for tid in ids}
        # Fatiga acumulada por equipo: crece con partidos de alta intensidad
        fatigue: dict[int, float] = {tid: 0.0
                                     for ids in self.groups.values() for tid in ids}
        # Umbral de rival "intenso" (partido que genera fatiga adicional)
        HARD_RIVAL_ELO = 1620
        FATIGUE_HARD   = 0.012   # +1.2% penalización en λ por partido duro
        FATIGUE_NORMAL = 0.006   # +0.6% por partido normal
        FATIGUE_DECAY  = 0.004   # recuperación por cada ronda sin partido duro

        firsts, seconds, thirds = [], [], []
        for g in GROUPS:
            table = self._sim_group(self.groups[g])
            firsts.append(table[0]["id"])
            seconds.append(table[1]["id"])
            thirds.append({"id": table[2]["id"], "pts": table[2]["pts"],
                           "gd": table[2]["gd"], "gf": table[2]["gf"]})

        # Mejores 8 terceros
        thirds.sort(key=lambda s: (s["pts"], s["gd"], s["gf"], self.rng.random()),
                    reverse=True)
        best_thirds = [t["id"] for t in thirds[:8]]

        # 32 clasificados marcados
        qualified = firsts + seconds + best_thirds
        for tid in qualified:
            reached[tid] = "round_of_32"

        # ── Sembrado del bracket (siembra serpiente por jerarquía) ────────────
        # 1ºs (más fuertes) → seeds altos; 2ºs medios; mejores 3ºs bajos.
        def seed_key(tid):
            return self.strength[tid]["elo"]
        firsts_sorted = sorted(firsts, key=seed_key, reverse=True)
        seconds_sorted = sorted(seconds, key=seed_key, reverse=True)
        thirds_sorted = sorted(best_thirds, key=seed_key, reverse=True)
        seeds = firsts_sorted + seconds_sorted + thirds_sorted   # 32 sembrados 0..31

        # Bracket estándar: seed i vs seed (31 - i)
        round_teams = []
        for i in range(16):
            round_teams.append((seeds[i], seeds[31 - i]))

        # ── Acumular fatiga de fase de grupos ────────────────────────────────
        # Un partido vs rival duro (Elo > 1620) genera más fatiga que vs débil.
        for g in GROUPS:
            group_ids = self.groups[g]
            for i in range(len(group_ids)):
                for j in range(i + 1, len(group_ids)):
                    h_id, a_id = group_ids[i], group_ids[j]
                    opp_h_elo = self.strength[a_id]["elo"]
                    opp_a_elo = self.strength[h_id]["elo"]
                    fatigue[h_id] += FATIGUE_HARD if opp_h_elo > HARD_RIVAL_ELO else FATIGUE_NORMAL
                    fatigue[a_id] += FATIGUE_HARD if opp_a_elo > HARD_RIVAL_ELO else FATIGUE_NORMAL

        # ── Eliminatorias ─────────────────────────────────────────────────────
        stage_names = ["round_of_16", "quarter_final", "semi_final", "final", "champion"]
        pairs = round_teams
        for stage in stage_names:
            winners = []
            for h, a in pairs:
                fh = fatigue.get(h, 0.0)
                fa = fatigue.get(a, 0.0)
                _, _, w = self._sim_match(h, a, neutral=True, knockout=True,
                                         fatigue_h=fh, fatigue_a=fa)
                winners.append(w)
                loser = a if w == h else h
                # Actualizar fatiga para la siguiente ronda
                for tid in (h, a):
                    opp = a if tid == h else h
                    inc = FATIGUE_HARD if self.strength[opp]["elo"] > HARD_RIVAL_ELO else FATIGUE_NORMAL
                    fatigue[tid] = fatigue.get(tid, 0.0) + inc - FATIGUE_DECAY
                    fatigue[tid] = max(0.0, fatigue[tid])
                if stage != "champion":
                    reached[w] = stage      # el ganador alcanza la SIGUIENTE ronda
            if stage == "final":
                # el ganador de la final es campeón
                reached[winners[0]] = "champion"
                break
            # emparejar ganadores para la siguiente ronda
            pairs = [(winners[i], winners[i + 1]) for i in range(0, len(winners), 2)]
            if len(winners) == 1:
                break
        return reached

    # ── Monte Carlo ─────────────────────────────────────────────────────────
    def run(self, n_sims: int = 5000, progress: bool = False) -> dict:
        order = ["group", "round_of_32", "round_of_16", "quarter_final",
                 "semi_final", "final", "champion"]
        rank = {s: i for i, s in enumerate(order)}

        counts = defaultdict(lambda: defaultdict(int))   # team → stage → veces alcanzada (acumulado)
        for it in range(n_sims):
            reached = self._sim_tournament()
            for tid, st in reached.items():
                # acumular en todas las rondas ≤ alcanzada
                for s in order[:rank[st] + 1]:
                    counts[tid][s] += 1
            if progress and (it + 1) % max(1, n_sims // 10) == 0:
                print(f"    ... {it+1}/{n_sims} torneos simulados")

        results = []
        for tid in self.strength:
            c = counts[tid]
            results.append({
                "team": self.name[tid],
                "elo": round(self.strength[tid]["elo"], 0),
                "p_advance":  round(c["round_of_32"] / n_sims * 100, 1),
                "p_r16":      round(c["round_of_16"] / n_sims * 100, 1),
                "p_quarter":  round(c["quarter_final"] / n_sims * 100, 1),
                "p_semi":     round(c["semi_final"] / n_sims * 100, 1),
                "p_final":    round(c["final"] / n_sims * 100, 1),
                "p_champion": round(c["champion"] / n_sims * 100, 1),
            })
        results.sort(key=lambda r: -r["p_champion"])
        return {"n_sims": n_sims, "teams": results, "groups": self._group_view()}

    def _group_view(self) -> dict:
        return {g: [self.name[t] for t in ids] for g, ids in self.groups.items()}


def format_tournament(res: dict, top: int = 24) -> str:
    L = [f"\n{'='*74}",
         f"  SIMULACIÓN MUNDIAL 2026 — {res['n_sims']:,} torneos Monte Carlo",
         f"{'='*74}",
         f"  {'#':>3}  {'Equipo':<18}{'Elo':>6}{'Octavos':>9}{'Cuartos':>9}"
         f"{'Semis':>8}{'Final':>8}{'CAMPEÓN':>9}",
         f"  {'-'*70}"]
    for i, t in enumerate(res["teams"][:top], 1):
        L.append(f"  {i:>3}  {t['team']:<18}{t['elo']:>6.0f}"
                 f"{t['p_r16']:>8.1f}%{t['p_quarter']:>8.1f}%"
                 f"{t['p_semi']:>7.1f}%{t['p_final']:>7.1f}%{t['p_champion']:>8.1f}%")
    L.append('='*74)
    return "\n".join(L)


if __name__ == "__main__":
    import time
    sim = TournamentSimulator(seed=2026)
    t0 = time.time()
    res = sim.run(n_sims=3000, progress=True)
    print(format_tournament(res, top=24))
    print(f"\n  ⏱  {time.time()-t0:.1f}s para {res['n_sims']:,} torneos")
