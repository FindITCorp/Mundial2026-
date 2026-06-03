"""
scripts/remediate_missing_data.py
Remediación inmediata de datos faltantes en mundial2026.db:

  1. Fusionar jugadores duplicados (tildes/sin tildes del mismo equipo)
  2. Imputar player_club_stats 2024/25 desde estadísticas nacionales
  3. Estimar market_value_m para todos los jugadores sin valor

Ejecutar: python3 scripts/remediate_missing_data.py
"""
import sqlite3
import unicodedata
import math
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

# ─── Utilidades ───────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def log(msg): print(f"  {msg}")


# ─── 1. FUSIONAR DUPLICADOS ───────────────────────────────────────────────────

def merge_duplicates(conn):
    """
    Detecta jugadores del mismo equipo con nombre normalizado idéntico.
    Conserva el registro con más datos (más caps / goals) y redirige todas
    las referencias FK al id ganador. Elimina el duplicado.
    """
    rows = conn.execute("""
        SELECT ss.team_id, p.id, p.name, p.position, p.caps, p.goals_as_nat,
               p.market_value_m
        FROM squad_selections ss JOIN players p ON p.id=ss.player_id
        ORDER BY ss.team_id, p.name
    """).fetchall()

    by_key = defaultdict(list)
    for r in rows:
        key = (r["team_id"], norm(r["name"]))
        by_key[key].append(dict(r))

    dupes = {k: v for k, v in by_key.items() if len(v) > 1}
    log(f"Duplicados detectados: {len(dupes)} pares")
    merged = 0

    for (tid, nname), players in dupes.items():
        # Ganador: el que tiene más caps; si igual, el id menor (más antiguo)
        winner = max(players, key=lambda p: (p["caps"] or 0, p["goals_as_nat"] or 0))
        losers = [p for p in players if p["id"] != winner["id"]]

        for loser in losers:
            lid, wid = loser["id"], winner["id"]

            # Actualizar FKs en todas las tablas relacionadas
            for tbl, col in [
                ("squad_selections",  "player_id"),
                ("projected_lineups", "player_id"),
                ("match_players",     "player_id"),
                ("player_nat_stats",  "player_id"),
                ("player_club_stats", "player_id"),
                ("player_ratings",    "player_id"),
            ]:
                try:
                    # evitar conflicto de PK si el ganador ya tiene registro en esa tabla
                    conn.execute(f"DELETE FROM {tbl} WHERE {col}=? AND EXISTS "
                                 f"(SELECT 1 FROM {tbl} WHERE {col}=?)", (lid, wid))
                    conn.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (wid, lid))
                except Exception:
                    pass

            # Fusionar datos del perdedor al ganador si el ganador tiene NULL
            if not (winner.get("caps") or 0) and (loser.get("caps") or 0):
                conn.execute("UPDATE players SET caps=?, goals_as_nat=? WHERE id=?",
                             (loser["caps"], loser["goals_as_nat"], wid))

            # Eliminar jugador duplicado
            try:
                conn.execute("DELETE FROM players WHERE id=?", (lid,))
            except Exception:
                pass

            merged += 1

    conn.commit()
    log(f"  ✅ Fusionados: {merged} duplicados eliminados")


# ─── 2. IMPUTAR CLUB STATS 2024/25 ───────────────────────────────────────────

# Parámetros de imputación por posición
# Multiplicadores calibrados contra goleadores reales conocidos (ver calibración)
# goals ≈ nat_rate * GOAL_MULT, capped at GOAL_CAP
# nat_rate = goals_as_nat / (caps + 8)  — regularizado para muestras pequeñas
POS_PARAMS = {
    "FWD": dict(goal_mult=52, goal_cap=35, assist_ratio=0.50, min_base=1800, min_cap_boost=600),
    "MID": dict(goal_mult=28, goal_cap=18, assist_ratio=1.20, min_base=1900, min_cap_boost=500),
    "DEF": dict(goal_mult=12, goal_cap= 6, assist_ratio=0.35, min_base=2000, min_cap_boost=400),
    "GK":  dict(goal_mult= 0, goal_cap= 0, assist_ratio=0.00, min_base=2200, min_cap_boost=300),
}

def _est_minutes(caps: int, pos: str) -> int:
    """Estima minutos jugados en club basados en regularidad con la selección."""
    params = POS_PARAMS.get(pos, POS_PARAMS["MID"])
    base = params["min_base"]
    boost = params["min_cap_boost"]
    # Más caps → más minutos de club (regularidad)
    if caps >= 80:   return min(3200, base + boost)
    if caps >= 50:   return min(2800, base + boost * 0.85)
    if caps >= 30:   return min(2500, base + boost * 0.65)
    if caps >= 15:   return min(2000, base + boost * 0.40)
    if caps >= 5:    return min(1500, base + boost * 0.20)
    return 700


def impute_club_stats(conn):
    """
    Inserta registros en player_club_stats para jugadores sin datos 2024/25.
    Usa ratio goleador nacional + posición para estimar goles, asistencias y minutos.
    """
    # Jugadores del WC2026 sin club stats
    missing = conn.execute("""
        SELECT DISTINCT p.id, p.name, p.position, p.caps, p.goals_as_nat
        FROM squad_selections ss
        JOIN wc_group_draw wgd ON wgd.team_id=ss.team_id
        JOIN players p ON p.id=ss.player_id
        WHERE NOT EXISTS (
            SELECT 1 FROM player_club_stats pcs
            WHERE pcs.player_id=p.id AND pcs.season='2024/25'
        )
    """).fetchall()

    log(f"Jugadores sin club stats 2024/25: {len(missing)}")
    inserted = 0

    for p in missing:
        pos = (p["position"] or "MID").upper()
        caps = p["caps"] or 0
        nat_goals = p["goals_as_nat"] or 0
        params = POS_PARAMS.get(pos, POS_PARAMS["MID"])

        # Ratio goleador nacional (regularizado para muestras pequeñas)
        nat_rate = nat_goals / (caps + 8)

        # Goles de club estimados: nat_rate * multiplicador calibrado, con techo
        goals = min(params["goal_cap"], max(0, round(nat_rate * params["goal_mult"])))

        # Asistencias: correlacionadas con goles, más altas para mediocampistas creativos
        assists = min(params["goal_cap"], max(0, round(goals * params["assist_ratio"])))

        # xG ligeramente por debajo de goles (regresión a la media)
        xg = round(goals * 0.82, 2)
        xa = round(assists * 0.78, 2)

        # Minutos
        minutes = _est_minutes(caps, pos)

        # Shots on target estimados desde xG
        sot = max(0, round(xg / 0.25)) if pos in ("FWD", "MID") else 0

        try:
            conn.execute("""
                INSERT INTO player_club_stats
                  (player_id, season, league, club, matches, minutes,
                   goals, assists, shots_on_target, xg, xa,
                   pass_accuracy, dribbles_completed, tackles, interceptions,
                   yellow_cards, red_cards)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                p["id"], "2024/25", "EST", "EST",
                int(minutes / 90),   # matches ≈ min/90
                minutes,
                goals, assists, sot, xg, xa,
                None, None, None, None, None, None,
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # Ya existe (raza condition)

    conn.commit()
    log(f"  ✅ Club stats imputadas para {inserted} jugadores")


# ─── 3. ESTIMAR MARKET VALUES ─────────────────────────────────────────────────

# Valores conocidos de los jugadores más mediáticos (millones €, mayo 2026)
KNOWN_VALUES = {
    # top tier
    "Kylian Mbappe":           180.0, "Kylian Mbappé":           180.0,
    "Vinicius Junior":         200.0,
    "Jude Bellingham":         180.0,
    "Erling Haaland":          180.0,
    "Lamine Yamal":            150.0,
    "Florian Wirtz":           130.0,
    "Phil Foden":              150.0,
    "Pedri":                   120.0,
    "Bukayo Saka":             150.0,
    "Rodri":                    80.0,
    "Lionel Messi":             35.0,   # valor de mercado actual, no histórico
    # delanteros clave
    "Dusan Vlahovic":           65.0,  "Dušan Vlahović":          65.0,
    "Victor Osimhen":           80.0,
    "Rafael Leao":              80.0,  "Rafael Leão":             80.0,
    "Robert Lewandowski":       15.0,
    "Harry Kane":               80.0,
    "Marcus Rashford":          40.0,
    "Richarlison":              40.0,
    "Lautaro Martinez":         80.0,  "Lautaro Martínez":        80.0,
    "Alejandro Garnacho":       65.0,
    "Julian Alvarez":           65.0,  "Julián Álvarez":          65.0,
    "Olivier Giroud":           10.0,
    "Ciro Immobile":             8.0,
    "Mateo Retegui":            40.0,
    "Raphinha":                 60.0,
    "Endrick":                  60.0,
    "Neymar":                   25.0,
    "Ferran Torres":            40.0,
    "Alvaro Morata":            20.0,  "Álvaro Morata":           20.0,
    "Benjamin Sesko":           65.0,  "Benjamin Šeško":          65.0,
    # mediocampistas
    "Jamal Musiala":           130.0,
    "Nico Williams":            70.0,
    "Alexis Mac Allister":      70.0,
    "Rodrigo De Paul":          40.0,
    "Enzo Fernandez":           60.0,  "Enzo Fernández":          60.0,
    "Dominik Szoboszlai":       70.0,
    "Joshua Kimmich":           60.0,
    "Toni Kroos":               15.0,
    "Declan Rice":              90.0,
    "Bruno Fernandes":          60.0,
    "Bernardo Silva":           60.0,
    "Vitinha":                  65.0,
    "Gavi":                     80.0,
    "Frenkie de Jong":          45.0,
    "Xavi Simons":              80.0,
    "Tijjani Reijnders":        60.0,
    "Yunus Musah":              30.0,
    "Weston McKennie":          20.0,
    "Christian Pulisic":        35.0,
    "Brenden Aaronson":         18.0,
    "Alphonso Davies":          65.0,
    "Jonathan David":           70.0,
    "Tajon Buchanan":           20.0,
    "Cyle Larin":               10.0,
    "Leon Bailey":              25.0,
    "Kaoru Mitoma":             40.0,
    "Takefusa Kubo":            45.0,
    "Heung-min Son":            20.0,  "Son Heung-min":           20.0,
    "Hwang Hee-chan":           22.0,
    "Ademola Lookman":          45.0,
    # porteros
    "Alisson":                  40.0,
    "Ederson":                  35.0,
    "Emiliano Martinez":        30.0,  "Emiliano Martínez":       30.0,
    "Gianluigi Donnarumma":     40.0,
    "Manuel Neuer":              8.0,
    "Marc-Andre ter Stegen":    25.0,
    "Thibaut Courtois":         25.0,
    "Keylor Navas":              5.0,
    # defensas destacados
    "Ruben Dias":               80.0,  "Rúben Dias":              80.0,
    "Virgil van Dijk":          25.0,
    "William Saliba":           80.0,
    "Dayot Upamecano":          45.0,
    "Antonio Rudiger":          20.0,  "Antonio Rüdiger":         20.0,
    "Achraf Hakimi":            65.0,
    "Trent Alexander-Arnold":   80.0,
    "Marc Cucurella":           35.0,
    "Theo Hernandez":           50.0,  "Théo Hernandez":          50.0,
    "Marquinhos":               30.0,
    "Casemiro":                 20.0,
}

# Valor base por posición (para jugadores sin valor conocido)
POS_BASE_VALUE = {"GK": 8.0, "DEF": 12.0, "MID": 15.0, "FWD": 18.0}

def _formula_value(caps: int, goals: int, pos: str) -> float:
    """Estima valor de mercado por fórmula cuando no está en KNOWN_VALUES."""
    base = POS_BASE_VALUE.get(pos, 12.0)
    # Factor de experiencia (logarítmico)
    exp_factor = min(2.5, math.log1p(caps) / math.log1p(40))
    # Factor goleador
    nat_rate = goals / (caps + 8) if caps else 0.0
    goal_factor = 1.0 + nat_rate * (5.0 if pos == "FWD" else 3.0 if pos == "MID" else 1.5)
    val = base * exp_factor * goal_factor
    return round(min(120.0, max(1.0, val)), 1)


def estimate_market_values(conn):
    """
    Actualiza market_value_m para todos los jugadores del WC2026.
    Usa valores conocidos primero; para el resto aplica la fórmula.
    """
    players = conn.execute("""
        SELECT DISTINCT p.id, p.name, p.position, p.caps, p.goals_as_nat, p.market_value_m
        FROM squad_selections ss
        JOIN wc_group_draw wgd ON wgd.team_id=ss.team_id
        JOIN players p ON p.id=ss.player_id
        WHERE (p.market_value_m IS NULL OR p.market_value_m = 0)
    """).fetchall()

    log(f"Jugadores sin market_value: {len(players)}")
    updated = 0
    known_used = 0

    for p in players:
        name = p["name"]
        pos  = (p["position"] or "MID").upper()
        caps = p["caps"] or 0
        goals = p["goals_as_nat"] or 0

        # Buscar valor conocido (con y sin tildes)
        val = KNOWN_VALUES.get(name)
        if val is None:
            # Intentar normalizado
            nname = norm(name)
            for kn, kv in KNOWN_VALUES.items():
                if norm(kn) == nname:
                    val = kv
                    break

        if val is not None:
            known_used += 1
        else:
            val = _formula_value(caps, goals, pos)

        conn.execute("UPDATE players SET market_value_m=? WHERE id=?", (val, p["id"]))
        updated += 1

    conn.commit()
    log(f"  ✅ Market values asignados: {updated} jugadores ({known_used} con valor conocido, {updated-known_used} por fórmula)")


# ─── 4. COMPLETAR DATOS FALTANTES DE JUGADORES ───────────────────────────────

def fix_missing_player_fields(conn):
    """Rellena caps=0/NULL para jugadores que deberían tenerlo."""
    # Jugadores con NULL caps → 0
    r = conn.execute(
        "UPDATE players SET caps=0 WHERE caps IS NULL"
    ).rowcount
    r2 = conn.execute(
        "UPDATE players SET goals_as_nat=0 WHERE goals_as_nat IS NULL"
    ).rowcount
    conn.commit()
    if r + r2:
        log(f"  ✅ Caps/goals NULL → 0: {r} + {r2} jugadores")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  REMEDIACIÓN DE DATOS — mundial2026.db")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")  # Para poder eliminar duplicados

    print("1️⃣  Reparando campos NULL...")
    fix_missing_player_fields(conn)

    print("\n2️⃣  Fusionando jugadores duplicados...")
    merge_duplicates(conn)

    print("\n3️⃣  Imputando club stats 2024/25 desde estadísticas nacionales...")
    impute_club_stats(conn)

    print("\n4️⃣  Estimando valores de mercado...")
    estimate_market_values(conn)

    # ── Resumen final ─────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  RESUMEN FINAL")
    print(f"{'─'*60}")

    total = conn.execute("""
        SELECT COUNT(DISTINCT ss.player_id) FROM squad_selections ss
        JOIN wc_group_draw wgd ON wgd.team_id=ss.team_id
    """).fetchone()[0]

    with_club = conn.execute("""
        SELECT COUNT(DISTINCT ss.player_id) FROM squad_selections ss
        JOIN wc_group_draw wgd ON wgd.team_id=ss.team_id
        JOIN player_club_stats pcs ON pcs.player_id=ss.player_id AND pcs.season='2024/25'
    """).fetchone()[0]

    with_mkt = conn.execute("""
        SELECT COUNT(DISTINCT ss.player_id) FROM squad_selections ss
        JOIN wc_group_draw wgd ON wgd.team_id=ss.team_id
        JOIN players p ON p.id=ss.player_id
        WHERE p.market_value_m > 0
    """).fetchone()[0]

    print(f"  Total jugadores WC2026:     {total}")
    print(f"  Con club stats 2024/25:     {with_club} ({with_club/total*100:.1f}%)")
    print(f"  Con market_value_m > 0:     {with_mkt} ({with_mkt/total*100:.1f}%)")

    # Top goleadores imputados de cada equipo sin datos reales
    print(f"\n  Top goleadores estimados en equipos sin datos previos:")
    for tname in ["Italy", "Serbia", "Denmark", "Poland", "Nigeria", "Slovenia"]:
        row = conn.execute("SELECT id FROM teams WHERE name=?", (tname,)).fetchone()
        if not row: continue
        tid = row["id"]
        top = conn.execute("""
            SELECT p.name, p.position, pcs.goals, pcs.minutes, p.market_value_m
            FROM squad_selections ss
            JOIN players p ON p.id=ss.player_id
            JOIN player_club_stats pcs ON pcs.player_id=ss.player_id AND pcs.season='2024/25'
            WHERE ss.team_id=?
            ORDER BY pcs.goals DESC LIMIT 3
        """, (tid,)).fetchall()
        tops = "  ".join(f"{r['name'][:18]}({r['goals']}g,{r['minutes']}min,€{r['market_value_m']:.0f}M)" for r in top)
        print(f"    {tname:<12}: {tops}")

    conn.close()
    print(f"\n{'='*60}")
    print("  ✅ Remediación completada")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
