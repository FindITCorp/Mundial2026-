"""
models/elo.py — Sistema Elo dinámico para selecciones nacionales.

Mejoras implementadas (jun 2026):
  1. Decay temporal: partidos viejos pesan menos (K * decay)
     < 2 años → 100%  |  2-4 → 75%  |  4-6 → 50%  |  > 6 → 25%
  2. Ancla FIFA: al final del rebuild, se mezcla 70% Elo histórico + 30% FIFA
     para evitar que equipos con muchos amistosos fáciles se disparen
  3. K-factor diferenciado por competición y corregido (no hay duplicados)

Uso:
    from models.elo import EloSystem
    elo = EloSystem(db_path)
    elo.build_from_history()
    rating = elo.get_rating(team_id)
"""

import sqlite3
import logging
import math
from pathlib import Path
from datetime import datetime, date

log = logging.getLogger("elo")

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# K-factor por tipo de competición
K_MAP = {
    "world cup":           60,
    "copa america":        50,
    "euro":                50,
    "nations league":      40,
    "confederation cup":   40,
    "gold cup":            40,
    "afcon":               40,
    "african cup":         40,
    "asian cup":           40,
    "wc qualifier":        30,
    "wcq":                 30,
    "qualifier":           25,
    "friendly":            10,
    "fifa series":         12,
}

BASE_ELO  = 1500
HOME_ADV  = 50       # puntos extra por jugar en casa (neutral = 0)
FIFA_ANCHOR_W = 0.30 # peso del ancla FIFA al final del rebuild


def _k_factor(competition: str) -> int:
    if not competition:
        return 20
    comp = competition.lower()
    for key, k in K_MAP.items():
        if key in comp:
            return k
    return 20


def _temporal_decay(match_date: str) -> float:
    """
    Factor de decay por antigüedad del partido.
    Un partido de hace 5 años vale la mitad que uno reciente.
    """
    try:
        d = date.fromisoformat(str(match_date)[:10])
    except Exception:
        return 0.5
    years_old = (date(2026, 6, 1) - d).days / 365.25
    if years_old < 2:
        return 1.00
    if years_old < 4:
        return 0.75
    if years_old < 6:
        return 0.50
    return 0.25


def _fifa_rank_to_elo(fifa_rank: int) -> float:
    """
    Convierte ranking FIFA a Elo de referencia.
    Calibrado abril 2026:
      #1  → 1900   #10 → 1700   #50 → 1560   #100 → 1500   #200 → 1440
    Fórmula: 1900 - 200 * log10(rank)
    """
    if not fifa_rank or fifa_rank <= 0 or fifa_rank >= 999:
        return None
    return round(1900 - 200 * math.log10(max(1, fifa_rank)), 1)


def _expected(elo_own: float, elo_opp: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_opp - elo_own) / 400))


def _goal_multiplier(gf: int, ga: int) -> float:
    """Ajuste por diferencia de goles (Elo FIFA style)."""
    diff = abs(gf - ga)
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return 1.75 + (diff - 3) * 0.04


class EloSystem:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._ratings: dict[int, float] = {}

    def _load_or_init(self, conn) -> None:
        rows = conn.execute(
            "SELECT team_id, elo FROM team_elo ORDER BY team_id"
        ).fetchall() if self._table_exists(conn) else []
        if rows:
            self._ratings = {r[0]: r[1] for r in rows}
        else:
            teams = conn.execute("SELECT id FROM teams").fetchall()
            self._ratings = {t[0]: float(BASE_ELO) for t in teams}

    def _table_exists(self, conn) -> bool:
        return conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='team_elo'"
        ).fetchone()[0] > 0

    def build_from_history(self) -> None:
        """Recalcula Elo completo desde team_matches con decay temporal y ancla FIFA."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_elo (
                team_id    INTEGER PRIMARY KEY REFERENCES teams(id),
                elo        REAL    NOT NULL DEFAULT 1500,
                peak_elo   REAL    NOT NULL DEFAULT 1500,
                matches    INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
        """)

        teams = [r[0] for r in conn.execute("SELECT id FROM teams").fetchall()]
        self._ratings = {t: float(BASE_ELO) for t in teams}

        matches = conn.execute("""
            SELECT team_id, opponent_id, goals_for, goals_against,
                   result, competition, venue, date
            FROM team_matches
            WHERE opponent_id IS NOT NULL
              AND goals_for IS NOT NULL
            ORDER BY date ASC, id ASC
        """).fetchall()

        processed = set()
        match_count = {t: 0 for t in teams}

        for m in matches:
            pair = tuple(sorted([m["team_id"], m["opponent_id"]]))
            key  = (pair, m["date"])
            if key in processed:
                continue
            processed.add(key)

            h_id = m["team_id"]
            a_id = m["opponent_id"]
            if h_id not in self._ratings or a_id not in self._ratings:
                continue

            gf = m["goals_for"]; ga = m["goals_against"]
            venue = m["venue"] or "neutral"

            # K con decay temporal — partidos viejos pesan menos
            k_base = _k_factor(m["competition"] or "")
            decay  = _temporal_decay(m["date"])
            k      = k_base * decay
            gm     = _goal_multiplier(gf, ga)

            h_adj = HOME_ADV if venue == "home" else (-HOME_ADV if venue == "away" else 0)
            elo_h = self._ratings[h_id] + h_adj
            elo_a = self._ratings[a_id]

            e_h = _expected(elo_h, elo_a)
            e_a = 1.0 - e_h

            if m["result"] == "W":
                r_h, r_a = 1.0, 0.0
            elif m["result"] == "D":
                r_h, r_a = 0.5, 0.5
            else:
                r_h, r_a = 0.0, 1.0

            delta_h = k * gm * (r_h - e_h)
            delta_a = k * gm * (r_a - e_a)

            self._ratings[h_id] = round(self._ratings[h_id] + delta_h, 2)
            self._ratings[a_id] = round(self._ratings[a_id] + delta_a, 2)
            match_count[h_id] = match_count.get(h_id, 0) + 1
            match_count[a_id] = match_count.get(a_id, 0) + 1

        # ── Ancla FIFA: mezclar historial + referencia FIFA ───────────────────
        # Para equipos CON ranking FIFA válido: 65% historial + 35% FIFA
        # Para equipos SIN ranking (999/null): anclar a la mediana (1500)
        # Esto evita que equipos con muchos amistosos fáciles se disparen
        # y que equipos recién registrados sin ranking queden inflados
        fifa_data = {
            r["id"]: (r["fifa_ranking"], r["fifa_rank"])
            for r in conn.execute("SELECT id, fifa_ranking, fifa_rank FROM teams").fetchall()
        }
        anchored = 0
        for tid in list(self._ratings.keys()):
            rank_primary, rank_secondary = fifa_data.get(tid, (999, 0))
            # Usar el mejor ranking disponible
            rank = None
            for r in [rank_primary, rank_secondary]:
                if r and 0 < r < 999:
                    rank = r
                    break
            hist_elo = self._ratings[tid]
            if rank is not None:
                fifa_elo = _fifa_rank_to_elo(rank)
                # 65% historial, 35% FIFA
                self._ratings[tid] = round(0.65 * hist_elo + 0.35 * fifa_elo, 2)
                anchored += 1
            else:
                # Sin ranking: regresión suave hacia BASE_ELO para no inflar equipos desconocidos
                # Equipos muy por encima de 1600 sin ranking = sospechosos → tirar hacia 1550
                if hist_elo > 1600:
                    self._ratings[tid] = round(0.70 * hist_elo + 0.30 * 1500, 2)
                elif hist_elo < 1350:
                    self._ratings[tid] = round(0.80 * hist_elo + 0.20 * 1450, 2)

        # Persistir
        now = datetime.utcnow().isoformat()
        conn.execute("DELETE FROM team_elo")
        for tid, elo in self._ratings.items():
            conn.execute("""
                INSERT INTO team_elo (team_id, elo, peak_elo, matches, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (tid, elo, elo, match_count.get(tid, 0), now))
        conn.commit()
        conn.close()
        log.info(
            "Elo recalculado: %d equipos, %d pares procesados, %d anclados a FIFA",
            len(self._ratings), len(processed), anchored
        )

    def get_rating(self, team_id: int) -> float:
        if not self._ratings:
            conn = sqlite3.connect(str(self.db_path))
            self._load_or_init(conn)
            conn.close()
        return self._ratings.get(team_id, BASE_ELO)

    def win_prob(self, home_id: int, away_id: int, neutral: bool = False) -> tuple[float, float, float]:
        adj = 0 if neutral else HOME_ADV
        e_h = _expected(self.get_rating(home_id) + adj, self.get_rating(away_id))
        diff = abs(self.get_rating(home_id) - self.get_rating(away_id))
        draw_base = max(0.18, 0.28 - diff * 0.0003)
        return round(e_h * (1 - draw_base), 4), round(draw_base, 4), round((1-e_h) * (1-draw_base), 4)

    def top_n(self, n: int = 20) -> list[tuple[str, float]]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT t.name, e.elo, e.matches
            FROM team_elo e JOIN teams t ON t.id = e.team_id
            ORDER BY e.elo DESC LIMIT ?
        """, (n,)).fetchall()
        conn.close()
        return [(r["name"], r["elo"], r["matches"]) for r in rows]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    elo = EloSystem()
    print("Construyendo Elo desde historial...")
    elo.build_from_history()
    print("\nTop 25 selecciones por Elo:")
    print(f"  {'#':>3}  {'Equipo':<22} {'Elo':>7}  {'FIFA':>5}  {'Partidos':>8}")
    print("  " + "-"*50)
    for i, (name, rating, m) in enumerate(elo.top_n(25), 1):
        print(f"  {i:>3}  {name:<22} {rating:>7.1f}  {m:>8}")
