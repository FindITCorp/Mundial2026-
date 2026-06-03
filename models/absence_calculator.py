"""
models/absence_calculator.py — Calcula el impacto de ausencias sobre el lambda del equipo.

Fuentes de ausencia:
  1. Pre-partido: lesiones o suspensiones conocidas (ingresadas manualmente o via API)
  2. En vivo:     tarjeta roja (jugador expulsado, equipo con 10) o lesión en el partido

Cómo impacta al predictor:
  predict_match(home_id, away_id, home_absence=X, away_absence=Y)
  donde X/Y ∈ [0, 0.30] — reducción porcentual del lambda

Lógica de peso por posición:
  GK ausente    → +0.12 concedidos (rival marca más)
  CB ausente    → +0.09 concedidos
  FB ausente    → +0.05 concedidos
  MID ausente   → -0.06 anotados y -0.04 concedidos
  FWD ausente   → -0.10 anotados
  Expulsión (10 hombres) → +0.15 concedidos, -0.12 anotados
"""

import sqlite3
from pathlib import Path
from dataclasses import dataclass, field

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# Impacto por posición sobre el lambda propio y rival
POSITION_IMPACT = {
    # (delta_own_attack, delta_own_defense) — defense = cuánto más concede el equipo
    "GK":  (0.00,  0.12),
    "CB":  (0.00,  0.09),
    "LB":  (0.02,  0.05),
    "RB":  (0.02,  0.05),
    "DEF": (0.00,  0.08),
    "DM":  (0.04,  0.05),
    "MID": (0.06,  0.04),
    "CM":  (0.06,  0.04),
    "AM":  (0.08,  0.02),
    "LW":  (0.09,  0.01),
    "RW":  (0.09,  0.01),
    "FWD": (0.10,  0.00),
    "ST":  (0.12,  0.00),
    "CF":  (0.11,  0.00),
}

# Red card en vivo: 10 vs 11 durante los minutos restantes
RED_CARD_IMPACT = (0.15, 0.14)  # (ataque reducido, defensa deteriorada)

# Rating umbral para considerar al jugador "clave" (multiplica impacto)
KEY_PLAYER_RATING_THRESHOLD = 7.0
KEY_PLAYER_MULTIPLIER = 1.4


@dataclass
class AbsenceEvent:
    """Un jugador ausente o expulsado."""
    player_name: str
    team_id: int
    reason: str          # "injury" | "suspension" | "red_card"
    position: str = "MID"
    rating: float = 6.0
    minute: int = 0      # para expulsiones en vivo


@dataclass
class AbsenceReport:
    """Resultado del cálculo de ausencias para un equipo."""
    team_id: int
    events: list = field(default_factory=list)
    attack_penalty: float = 0.0    # reducción porcentual del lambda ofensivo
    defense_penalty: float = 0.0   # aumento porcentual del lambda rival
    has_red_card: bool = False
    red_card_minute: int = 0
    summary: str = ""

    @property
    def absence_factor(self) -> float:
        """Factor combinado para pasar a predict_match como home_absence/away_absence."""
        return round(min(0.35, (self.attack_penalty + self.defense_penalty) / 2), 3)


def calculate_absence(events: list[AbsenceEvent]) -> AbsenceReport:
    """
    Calcula el impacto total de un conjunto de ausencias sobre el equipo.
    """
    if not events:
        return AbsenceReport(team_id=0)

    team_id = events[0].team_id
    report = AbsenceReport(team_id=team_id, events=events)

    descriptions = []
    for ev in events:
        pos = ev.position.upper().strip()
        imp = POSITION_IMPACT.get(pos, POSITION_IMPACT["MID"])
        atk_imp, def_imp = imp

        # Jugador clave → multiplica impacto
        if ev.rating >= KEY_PLAYER_RATING_THRESHOLD:
            atk_imp *= KEY_PLAYER_MULTIPLIER
            def_imp *= KEY_PLAYER_MULTIPLIER

        if ev.reason == "red_card":
            report.has_red_card = True
            report.red_card_minute = ev.minute
            # Minutos restantes — mayor impacto si expulsión temprana
            mins_remaining = max(1, 90 - ev.minute)
            time_factor = mins_remaining / 90.0
            report.attack_penalty  += RED_CARD_IMPACT[0] * time_factor
            report.defense_penalty += RED_CARD_IMPACT[1] * time_factor
            descriptions.append(
                f"🟥 {ev.player_name} expulsado min {ev.minute} "
                f"({mins_remaining}' restantes, impact×{time_factor:.2f})"
            )
        else:
            report.attack_penalty  += atk_imp
            report.defense_penalty += def_imp
            icon = "🤕" if ev.reason == "injury" else "🚫"
            descriptions.append(
                f"{icon} {ev.player_name} ({pos}, rating={ev.rating:.1f}) — {ev.reason}"
            )

    report.attack_penalty  = min(0.35, report.attack_penalty)
    report.defense_penalty = min(0.35, report.defense_penalty)
    report.summary = "\n".join(descriptions)
    return report


def get_player_info(player_name: str, team_id: int,
                    db_path: Path = DB_PATH) -> dict | None:
    """Busca posición y rating de un jugador en la DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT p.position, pr.rating
        FROM players p
        LEFT JOIN player_ratings pr ON pr.player_id = p.id AND pr.context = 'nat'
        WHERE p.team_id = ? AND (p.name LIKE ? OR p.name LIKE ?)
        ORDER BY pr.rating DESC NULLS LAST LIMIT 1
    """, (team_id, f"%{player_name}%", f"{player_name}%")).fetchone()
    conn.close()
    return dict(row) if row else None


def absence_from_events(
    home_id: int,
    away_id: int,
    home_events: list[dict] | None = None,
    away_events: list[dict] | None = None,
    db_path: Path = DB_PATH,
) -> tuple[float, float, str]:
    """
    API principal: recibe listas de eventos y retorna (home_absence, away_absence, resumen).

    Formato de evento:
        {"player": "Messi", "reason": "injury"}          # pre-partido
        {"player": "De Paul", "reason": "red_card", "minute": 67}
        {"player": "Lautaro", "reason": "suspension"}

    Retorna:
        (home_absence, away_absence, texto_resumen)
        Los valores se pasan directamente a predict_match().
    """
    def build_events(team_id, raw_events):
        result = []
        for ev in (raw_events or []):
            name = ev.get("player", "")
            info = get_player_info(name, team_id, db_path) or {}
            result.append(AbsenceEvent(
                player_name=name,
                team_id=team_id,
                reason=ev.get("reason", "injury"),
                position=info.get("position") or ev.get("position", "MID"),
                rating=info.get("rating") or ev.get("rating", 6.0),
                minute=ev.get("minute", 0),
            ))
        return result

    h_report = calculate_absence(build_events(home_id, home_events))
    a_report = calculate_absence(build_events(away_id, away_events))

    lines = []
    if h_report.events:
        lines.append(f"Local — ausencias ({h_report.absence_factor:.2f} penalización):")
        lines.append(h_report.summary)
    if a_report.events:
        lines.append(f"Visitante — ausencias ({a_report.absence_factor:.2f} penalización):")
        lines.append(a_report.summary)

    return h_report.absence_factor, a_report.absence_factor, "\n".join(lines)


# ── Tabla para persistir eventos durante el torneo ────────────────────────────
def ensure_absence_table(db_path: Path = DB_PATH):
    """Crea tabla match_absences si no existe."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_absences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_date  TEXT NOT NULL,
            team_id     INTEGER REFERENCES teams(id),
            player_name TEXT NOT NULL,
            reason      TEXT NOT NULL,  -- injury | suspension | red_card
            minute      INTEGER DEFAULT 0,
            position    TEXT,
            rating      REAL,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def register_absence(match_date: str, team_id: int, player_name: str,
                     reason: str, minute: int = 0,
                     db_path: Path = DB_PATH):
    """Persiste una ausencia en la DB para tracking histórico."""
    ensure_absence_table(db_path)
    info = get_player_info(player_name, team_id, db_path) or {}
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO match_absences (match_date, team_id, player_name, reason, minute, position, rating)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (match_date, team_id, player_name, reason, minute,
          info.get("position"), info.get("rating")))
    conn.commit()
    conn.close()


def get_active_absences(team_id: int, match_date: str,
                        db_path: Path = DB_PATH) -> list[dict]:
    """Recupera ausencias registradas para un equipo en una fecha dada."""
    ensure_absence_table(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT player_name, reason, minute, position, rating
        FROM match_absences
        WHERE team_id = ? AND match_date = ?
    """, (team_id, match_date)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    # Demo: Argentina sin Messi, Bélgica con tarjeta roja al 67'
    from models.absence_calculator import absence_from_events
    import sqlite3

    DB = DB_PATH
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    arg_id = conn.execute("SELECT id FROM teams WHERE name='Argentina'").fetchone()["id"]
    bel_id = conn.execute("SELECT id FROM teams WHERE name='Belgium'").fetchone()["id"]
    conn.close()

    h_abs, a_abs, summary = absence_from_events(
        home_id=arg_id,
        away_id=bel_id,
        home_events=[{"player": "Messi", "reason": "injury"}],
        away_events=[{"player": "De Bruyne", "reason": "red_card", "minute": 67}],
    )
    print(summary)
    print(f"\nhome_absence={h_abs}  away_absence={a_abs}")
    print("\nEfecto en predicción:")

    import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
    from models.match_predictor import predict_match
    r_normal = predict_match(arg_id, bel_id, neutral=True)
    r_absent = predict_match(arg_id, bel_id, neutral=True,
                             home_absence=h_abs, away_absence=a_abs)
    print(f"  Sin ausencias:  {r_normal['predicted_score']}  λ={r_normal['lambda_home']}/{r_normal['lambda_away']}")
    print(f"  Con ausencias:  {r_absent['predicted_score']}  λ={r_absent['lambda_home']}/{r_absent['lambda_away']}")
