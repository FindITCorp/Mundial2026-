"""
models/elo.py — Sistema Elo dinámico para selecciones nacionales.

Uso:
    from models.elo import EloSystem
    elo = EloSystem(db_path)
    elo.build_from_history()          # pobla desde team_matches
    rating = elo.get_rating(team_id)
    prob_home = elo.win_prob(home_id, away_id)
"""

import sqlite3
import logging
import math
from pathlib import Path
from datetime import datetime

log = logging.getLogger("elo")

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# K-factor por tipo de competición
K_MAP = {
    "friendly":            10,
    "wc qualifier":        25,
    "wcq":                 25,
    "world cup":           60,
    "wc":                  60,
    "copa america":        45,
    "euro":                45,
    "nations league":      35,
    "confederation cup":   35,
    "gold cup":            35,
    "afcon":               35,
    "african":             30,
    "asian":               30,
    "qualifier":           25,
    "friendly":            10,
}

BASE_ELO   = 1500
HOME_ADV   = 50    # puntos extra por jugar en casa (neutral = 0)


def _k_factor(competition: str) -> int:
    if not competition:
        return 20
    comp = competition.lower()
    for key, k in K_MAP.items():
        if key in comp:
            return k
    return 20


def _expected(elo_own: float, elo_opp: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_opp - elo_own) / 400))


def _goal_multiplier(gf: int, ga: int) -> float:
    """Ajuste por diferencia de goles (Elo FIFA style)."""
    diff = abs(gf - ga)
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return 1.75 + (diff - 3) * 0.04   # crece suavemente


class EloSystem:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._ratings: dict[int, float] = {}   # team_id → elo

    # ── Inicializar ratings ────────────────────────────────────────────────
    def _load_or_init(self, conn) -> None:
        """Carga ratings guardados o inicia todos en BASE_ELO."""
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

    # ── Construir desde historial ──────────────────────────────────────────
    def build_from_history(self) -> None:
        """Recalcula Elo completo desde team_matches ordenado por fecha."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Crear/limpiar tabla
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_elo (
                team_id    INTEGER PRIMARY KEY REFERENCES teams(id),
                elo        REAL    NOT NULL DEFAULT 1500,
                peak_elo   REAL    NOT NULL DEFAULT 1500,
                matches    INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
        """)

        # Iniciar todos los equipos en BASE_ELO
        teams = [r[0] for r in conn.execute("SELECT id FROM teams").fetchall()]
        self._ratings = {t: float(BASE_ELO) for t in teams}

        # Partidos ordenados cronológicamente con opponent_id conocido
        matches = conn.execute("""
            SELECT team_id, opponent_id, goals_for, goals_against,
                   result, competition, venue, date
            FROM team_matches
            WHERE opponent_id IS NOT NULL
              AND goals_for IS NOT NULL
            ORDER BY date ASC, id ASC
        """).fetchall()

        processed = set()  # evitar doble conteo (A vs B y B vs A)
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
            k  = _k_factor(m["competition"] or "")
            gm = _goal_multiplier(gf, ga)

            # Ventaja de localía
            h_adj = HOME_ADV if venue == "home" else (-HOME_ADV if venue == "away" else 0)

            elo_h = self._ratings[h_id] + h_adj
            elo_a = self._ratings[a_id]

            e_h = _expected(elo_h, elo_a)
            e_a = 1.0 - e_h

            # Resultado real (desde perspectiva del team_id = local)
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
        log.info("Elo recalculado para %d equipos desde %d pares de partidos",
                 len(self._ratings), len(processed))

    # ── API pública ────────────────────────────────────────────────────────
    def get_rating(self, team_id: int) -> float:
        if not self._ratings:
            conn = sqlite3.connect(str(self.db_path))
            self._load_or_init(conn)
            conn.close()
        return self._ratings.get(team_id, BASE_ELO)

    def win_prob(self, home_id: int, away_id: int, neutral: bool = False) -> tuple[float, float, float]:
        """Retorna (p_home_win, p_draw, p_away_win) basado en Elo."""
        adj = 0 if neutral else HOME_ADV
        e_h = _expected(self.get_rating(home_id) + adj, self.get_rating(away_id))
        # Distribución draw según diferencia de Elo (más pareja → más empates)
        diff = abs(self.get_rating(home_id) - self.get_rating(away_id))
        draw_base = max(0.18, 0.28 - diff * 0.0003)
        p_h   = e_h   * (1 - draw_base)
        p_a   = (1 - e_h) * (1 - draw_base)
        p_d   = draw_base
        return round(p_h, 4), round(p_d, 4), round(p_a, 4)

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
    print("\nTop 20 selecciones por Elo:")
    print(f"  {'#':>3}  {'Equipo':<22} {'Elo':>7}  {'Partidos':>8}")
    print("  " + "-"*45)
    for i, (name, rating, m) in enumerate(elo.top_n(20), 1):
        print(f"  {i:>3}  {name:<22} {rating:>7.1f}  {m:>8}")
