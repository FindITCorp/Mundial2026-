"""
formation_engine.py — Tactical matchup analysis between two teams.

Calculates formation-based xG multipliers by evaluating:
  - Midfield / forward / defensive line numerical advantages
  - Tactical style matchups (pressing vs counter, possession vs physical, etc.)
  - Pressing intensity vs opponent's defensive line depth
  - Defensive line vulnerability against pace/forward overloads
  - Underdog motivation factor (FIFA ranking gap)

Main entry point: formation_matchup_factor(home_data, away_data) -> dict
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"

FORMATION_SLOTS: dict[str, dict[str, int]] = {
    "4-3-3":   {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3},
    "4-2-3-1": {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "4-4-2":   {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
    "3-4-3":   {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    "3-5-2":   {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
    "5-3-2":   {"GK": 1, "DEF": 5, "MID": 3, "FWD": 2},
    "4-5-1":   {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "4-1-4-1": {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "3-3-1-3": {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
    "5-4-1":   {"GK": 1, "DEF": 5, "MID": 4, "FWD": 1},
    "5-2-3":   {"GK": 1, "DEF": 5, "MID": 2, "FWD": 3},
}

_ALT_FORMATION_MAP: dict[str, str] = {
    "4-3-3":   "5-4-1",
    "4-2-3-1": "5-3-2",
    "4-4-2":   "5-4-1",
    "3-4-3":   "5-4-1",
    "3-5-2":   "5-3-2",
    "4-5-1":   "5-4-1",
    "4-1-4-1": "5-4-1",
    "3-3-1-3": "5-4-1",
    "5-4-1":   "5-4-1",
    "5-3-2":   "5-3-2",
    "5-2-3":   "5-4-1",
}

# Tactical style matchup bonuses (attacker_style, defender_style) -> xG delta for attacker
_STYLE_MATCHUP: dict[tuple[str, str], float] = {
    ("pressing",   "defensive"):  0.08,
    ("pressing",   "balanced"):   0.04,
    ("pressing",   "counter"):   -0.06,   # counter exploits high press
    ("attacking",  "defensive"):  0.05,
    ("defensive",  "attacking"):  0.03,
    ("counter",    "possession"): 0.04,
    ("counter",    "pressing"):   0.06,
    ("possession", "counter"):   -0.04,   # slightly vulnerable
    ("possession", "possession"): -0.02,
    ("physical",   "possession"):  0.0,
    ("possession", "physical"):    0.0,
    ("disciplined","pressing"):    0.02,
}


# ---------------------------------------------------------------------------
# Core parsing helpers
# ---------------------------------------------------------------------------

def parse_formation(formation_str: str) -> dict[str, int]:
    """
    Return slot counts for a formation string.

    Falls back to numeric parsing (split by '-') if the formation is not in
    FORMATION_SLOTS.  The parsed result always contains GK=1.
    """
    slots = FORMATION_SLOTS.get(formation_str)
    if slots:
        return dict(slots)

    parts = formation_str.split("-")
    if len(parts) >= 3:
        try:
            def_ = int(parts[0])
            fwd  = int(parts[-1])
            mid  = sum(int(p) for p in parts[1:-1])
            return {"GK": 1, "DEF": def_, "MID": mid, "FWD": fwd}
        except ValueError:
            pass

    return dict(FORMATION_SLOTS["4-4-2"])


# ---------------------------------------------------------------------------
# Individual bonus functions
# ---------------------------------------------------------------------------

def style_matchup_bonus(attacker_style: str, defender_style: str) -> float:
    """
    Return xG delta for the attacking team based on tactical style pairing.

    Positive = attacker benefits; negative = attacker suffers.
    0.0 returned for unknown / symmetric pairings.
    """
    key = (attacker_style, defender_style)
    if key in _STYLE_MATCHUP:
        return _STYLE_MATCHUP[key]

    reverse_key = (defender_style, attacker_style)
    if reverse_key in _STYLE_MATCHUP:
        return -_STYLE_MATCHUP[reverse_key]

    return 0.0


def pressing_bonus(attacker_press: float, defender_line: str) -> float:
    """
    Return xG delta for the attacking team based on pressing intensity vs
    opponent's defensive line depth.
    """
    if attacker_press > 6.5:
        if defender_line == "low":
            return 0.06
        if defender_line in ("high", "very_high"):
            return 0.0
        return 0.03   # medium line: partial benefit
    if attacker_press < 5.0:
        return -0.03  # passive press penalized against any pressing team
    return 0.0


# ---------------------------------------------------------------------------
# Main matchup function
# ---------------------------------------------------------------------------

def formation_matchup_factor(
    home_data: dict,
    away_data: dict,
) -> dict:
    """
    Calculate tactical xG multipliers for a match.

    Parameters
    ----------
    home_data / away_data : dict
        Each must contain at minimum:
          formation, pressing_intensity, defensive_line, tactical_style
        Optional: fifa_ranking (int), alt_formation

    Returns
    -------
    dict with keys:
        home_factor, away_factor   — xG multipliers (1.0 = neutral)
        home_mid_adv, away_mid_adv
        home_style_bonus, away_style_bonus
        home_press_bonus, away_press_bonus
        analysis                   — human-readable tactical summary
    """
    h_slots = parse_formation(home_data.get("formation", "4-4-2"))
    a_slots = parse_formation(away_data.get("formation", "4-4-2"))

    h_mid = h_slots["MID"]
    a_mid = a_slots["MID"]
    h_fwd = h_slots["FWD"]
    a_fwd = a_slots["FWD"]
    h_def = h_slots["DEF"]
    a_def = a_slots["DEF"]

    h_style = home_data.get("tactical_style", "balanced")
    a_style = away_data.get("tactical_style", "balanced")
    h_press = float(home_data.get("pressing_intensity", 5.0))
    a_press = float(away_data.get("pressing_intensity", 5.0))
    h_line  = home_data.get("defensive_line", "medium")
    a_line  = away_data.get("defensive_line", "medium")

    notes: list[str] = []

    # ── 1. Midfield advantage ──────────────────────────────────────────────
    mid_diff = h_mid - a_mid
    home_mid_adv = float(max(-0.12, min(0.12, mid_diff * 0.03)))
    away_mid_adv = float(max(-0.12, min(0.12, -mid_diff * 0.03)))

    # Extra midfielders also reduce exposure for the team that has them
    # (opponent xG reduced slightly)
    home_mid_def_reduction = max(0.0, mid_diff) * 0.02   # applied to away attack
    away_mid_def_reduction = max(0.0, -mid_diff) * 0.02  # applied to home attack

    if abs(mid_diff) >= 1:
        leader = "Home" if mid_diff > 0 else "Away"
        notes.append(
            f"{leader} has midfield numbers advantage "
            f"({h_mid} vs {a_mid} mids, {abs(mid_diff) * 0.03:.2f} xG swing)."
        )

    # ── 2. Forward advantage ──────────────────────────────────────────────
    fwd_diff = h_fwd - a_fwd
    home_fwd_adv = float(max(-0.10, min(0.10, fwd_diff * 0.05)))
    away_fwd_adv = float(max(-0.10, min(0.10, -fwd_diff * 0.05)))

    # Extra forwards reduce opponent's defensive coverage
    home_fwd_def_reduction = max(0.0, fwd_diff) * 0.03   # applied to away attack
    away_fwd_def_reduction = max(0.0, -fwd_diff) * 0.03  # applied to home attack

    if abs(fwd_diff) >= 1:
        leader = "Home" if fwd_diff > 0 else "Away"
        notes.append(
            f"{leader} outnumbers opponent in attack "
            f"({h_fwd} vs {a_fwd} forwards)."
        )

    # ── 3. Defensive solidity ──────────────────────────────────────────────
    def_diff = h_def - a_def
    # Extra home DEF reduces away xG; extra away DEF reduces home xG
    home_def_reduction = max(0.0, def_diff) * 0.04    # how much home DEF helps vs away
    away_def_reduction = max(0.0, -def_diff) * 0.04   # how much away DEF helps vs home

    if abs(def_diff) >= 1:
        leader = "Home" if def_diff > 0 else "Away"
        notes.append(
            f"{leader} has stronger defensive block "
            f"({h_def} vs {a_def} defenders)."
        )

    # ── 4. Tactical style matchup ──────────────────────────────────────────
    home_style_bonus = style_matchup_bonus(h_style, a_style)
    away_style_bonus = style_matchup_bonus(a_style, h_style)

    if home_style_bonus != 0.0 or away_style_bonus != 0.0:
        if home_style_bonus > 0:
            notes.append(
                f"Home ({h_style}) style exploits Away ({a_style}) "
                f"(+{home_style_bonus:.2f} xG)."
            )
        elif away_style_bonus > 0:
            notes.append(
                f"Away ({a_style}) style exploits Home ({h_style}) "
                f"(+{away_style_bonus:.2f} xG)."
            )
        else:
            notes.append(
                f"Style matchup ({h_style} vs {a_style}) slightly suppresses scoring."
            )

    # ── 5. Pressing intensity interaction ──────────────────────────────────
    home_press_bonus = pressing_bonus(h_press, a_line)
    away_press_bonus = pressing_bonus(a_press, h_line)

    if home_press_bonus != 0.0:
        notes.append(
            f"Home pressing (intensity {h_press}) vs Away line '{a_line}': "
            f"{'+' if home_press_bonus > 0 else ''}{home_press_bonus:.2f} xG."
        )
    if away_press_bonus != 0.0:
        notes.append(
            f"Away pressing (intensity {a_press}) vs Home line '{h_line}': "
            f"{'+' if away_press_bonus > 0 else ''}{away_press_bonus:.2f} xG."
        )

    # ── 6. Defensive line vulnerability ───────────────────────────────────
    home_line_vuln = 0.0
    away_line_vuln = 0.0

    if h_line in ("high", "very_high") and a_fwd > 2:
        away_line_vuln += 0.04
        notes.append(
            f"Away exploits Home's high line with {a_fwd} forwards (+0.04 xG)."
        )
    if a_line in ("high", "very_high") and h_fwd > 2:
        home_line_vuln += 0.04
        notes.append(
            f"Home exploits Away's high line with {h_fwd} forwards (+0.04 xG)."
        )

    both_high_line = h_line in ("high", "very_high") and a_line in ("high", "very_high")
    if both_high_line:
        home_line_vuln += 0.05
        away_line_vuln += 0.05
        notes.append("Both teams play a high line — open, attacking game expected (+0.05 xG each).")

    # ── 7. Underdog factor ─────────────────────────────────────────────────
    home_underdog_bonus = 0.0
    away_underdog_bonus = 0.0

    h_rank = home_data.get("fifa_ranking") or home_data.get("fifa_rank")
    a_rank = away_data.get("fifa_ranking") or away_data.get("fifa_rank")

    if h_rank and a_rank:
        rank_gap = h_rank - a_rank  # positive = home is lower-ranked (underdog)
        if rank_gap >= 25:
            home_underdog_bonus = 0.03
            away_underdog_bonus = -0.02
            notes.append(
                f"Home is underdog by {rank_gap} FIFA places "
                f"(motivation boost +0.03 xG; Favorite -0.02)."
            )
        elif rank_gap <= -25:
            away_underdog_bonus = 0.03
            home_underdog_bonus = -0.02
            notes.append(
                f"Away is underdog by {abs(rank_gap)} FIFA places "
                f"(motivation boost +0.03 xG; Favorite -0.02)."
            )

    # ── Aggregate delta values ────────────────────────────────────────────
    # home attack xG delta
    home_attack_delta = (
        home_mid_adv
        + home_fwd_adv
        + home_style_bonus
        + home_press_bonus
        + away_line_vuln        # away's high line helps home attack
        + home_underdog_bonus
        - away_mid_def_reduction
        - away_fwd_def_reduction
        - away_def_reduction
    )

    # away attack xG delta
    away_attack_delta = (
        away_mid_adv
        + away_fwd_adv
        + away_style_bonus
        + away_press_bonus
        + home_line_vuln        # home's high line helps away attack
        + away_underdog_bonus
        - home_mid_def_reduction
        - home_fwd_def_reduction
        - home_def_reduction
    )

    home_factor = round(max(0.70, min(1.40, 1.0 + home_attack_delta)), 4)
    away_factor = round(max(0.70, min(1.40, 1.0 + away_attack_delta)), 4)

    analysis = _build_analysis(
        home_data, away_data, h_slots, a_slots,
        home_factor, away_factor, notes
    )

    return {
        "home_factor":      home_factor,
        "away_factor":      away_factor,
        "home_mid_adv":     round(home_mid_adv, 4),
        "away_mid_adv":     round(away_mid_adv, 4),
        "home_style_bonus": round(home_style_bonus, 4),
        "away_style_bonus": round(away_style_bonus, 4),
        "home_press_bonus": round(home_press_bonus, 4),
        "away_press_bonus": round(away_press_bonus, 4),
        "analysis":         analysis,
    }


# ---------------------------------------------------------------------------
# Analysis text builder
# ---------------------------------------------------------------------------

def _build_analysis(
    home_data: dict,
    away_data: dict,
    h_slots: dict,
    a_slots: dict,
    home_factor: float,
    away_factor: float,
    notes: list[str],
) -> str:
    home_name = home_data.get("name", "Home")
    away_name = away_data.get("name", "Away")
    h_form = home_data.get("formation", "?")
    a_form = away_data.get("formation", "?")
    h_style = home_data.get("tactical_style", "?")
    a_style = away_data.get("tactical_style", "?")
    h_coach = home_data.get("coach", "")
    a_coach = away_data.get("coach", "")

    lines = [
        f"TACTICAL REPORT: {home_name} vs {away_name}",
        "=" * 55,
        f"  {home_name:<22} {h_form} ({h_style})"
        + (f"  [{h_coach}]" if h_coach else ""),
        f"  {away_name:<22} {a_form} ({a_style})"
        + (f"  [{a_coach}]" if a_coach else ""),
        "",
        f"  Formation slots:",
        f"    {home_name}: DEF {h_slots['DEF']} | MID {h_slots['MID']} | FWD {h_slots['FWD']}",
        f"    {away_name}: DEF {a_slots['DEF']} | MID {a_slots['MID']} | FWD {a_slots['FWD']}",
        "",
        f"  xG multipliers:",
        f"    {home_name}: {home_factor:.3f}x",
        f"    {away_name}: {away_factor:.3f}x",
    ]

    if notes:
        lines.append("")
        lines.append("  Key tactical factors:")
        for note in notes:
            lines.append(f"    - {note}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_team_tactics(team_name: str, db_path: Optional[Path] = None) -> dict:
    """
    Load a team's tactical profile from the DB.

    Returns a dict with keys: name, formation, pressing_intensity,
    defensive_line, tactical_style, coach, alt_formation, fifa_ranking.
    Returns an empty dict if the team is not found.
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT * FROM teams WHERE name=? OR name LIKE ?",
        (team_name, f"%{team_name}%"),
    ).fetchone()
    conn.close()

    if not row:
        return {}

    data = dict(row)
    # Normalise fifa_ranking key (DB may use fifa_rank or fifa_ranking)
    if "fifa_ranking" not in data:
        data["fifa_ranking"] = data.get("fifa_rank")
    return data


def predict_formation_for_match(
    team_name: str,
    opponent_name: str,
    db_path: Optional[Path] = None,
) -> str:
    """
    Predict the formation a team will use against a specific opponent.

    Rules:
      - If team is underdog by 20+ FIFA ranking positions: use alt_formation
        (more defensive).
      - If team is heavy favourite by 20+ positions: keep primary formation.
      - Otherwise: keep primary formation.

    Returns the predicted formation string.
    """
    db = db_path or DB_PATH
    team     = get_team_tactics(team_name, db)
    opponent = get_team_tactics(opponent_name, db)

    if not team:
        return "4-4-2"

    primary_formation = team.get("formation") or "4-4-2"
    alt_formation     = team.get("alt_formation") or _ALT_FORMATION_MAP.get(primary_formation, "5-4-1")

    t_rank = team.get("fifa_ranking") or team.get("fifa_rank")
    o_rank = opponent.get("fifa_ranking") or opponent.get("fifa_rank")

    if t_rank and o_rank:
        rank_gap = t_rank - o_rank  # positive = team is lower-ranked (underdog)
        if rank_gap >= 20:
            return alt_formation    # underdog: defensive shape
        # heavy favourite (rank_gap <= -20): keep attacking formation

    return primary_formation


def tactical_report(
    home_name: str,
    away_name: str,
    db_path: Optional[Path] = None,
) -> str:
    """
    Generate a human-readable tactical analysis string for a match.

    Loads both teams from the DB and runs formation_matchup_factor.
    Returns the analysis string from the result dict.
    """
    db = db_path or DB_PATH
    home_data = get_team_tactics(home_name, db)
    away_data = get_team_tactics(away_name, db)

    if not home_data:
        return f"Team not found in database: {home_name}"
    if not away_data:
        return f"Team not found in database: {away_name}"

    result = formation_matchup_factor(home_data, away_data)
    return result["analysis"]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:
        report = tactical_report(sys.argv[1], sys.argv[2])
        print(report)
    else:
        print("Usage: python formation_engine.py <home_team> <away_team>")
        print("Example: python formation_engine.py Spain Germany")
