"""
venue_model.py — WC2026 venue altitude and travel fatigue penalties.

Altitude penalty: teams not adapted to high altitude suffer reduced xG
at Mexico City (2,240m) and Guadalajara (1,566m).
"""
from __future__ import annotations
from typing import Optional

# WC2026 venues with altitude in meters
WC2026_VENUES: dict[str, dict] = {
    "Mexico City":   {"altitude": 2240, "country": "Mexico", "stadium": "Estadio Azteca"},
    "Guadalajara":   {"altitude": 1566, "country": "Mexico", "stadium": "Estadio Akron"},
    "Monterrey":     {"altitude":  538, "country": "Mexico", "stadium": "Estadio BBVA"},
    "Los Angeles":   {"altitude":   93, "country": "USA",    "stadium": "SoFi Stadium"},
    "San Francisco": {"altitude":    5, "country": "USA",    "stadium": "Levi's Stadium"},
    "New York":      {"altitude":    5, "country": "USA",    "stadium": "MetLife Stadium"},
    "Dallas":        {"altitude":  183, "country": "USA",    "stadium": "AT&T Stadium"},
    "Houston":       {"altitude":   14, "country": "USA",    "stadium": "NRG Stadium"},
    "Seattle":       {"altitude":   52, "country": "USA",    "stadium": "Lumen Field"},
    "Kansas City":   {"altitude":  320, "country": "USA",    "stadium": "Arrowhead Stadium"},
    "Atlanta":       {"altitude":  336, "country": "USA",    "stadium": "Mercedes-Benz Stadium"},
    "Boston":        {"altitude":    5, "country": "USA",    "stadium": "Gillette Stadium"},
    "Miami":         {"altitude":    2, "country": "USA",    "stadium": "Hard Rock Stadium"},
    "Philadelphia":  {"altitude":   12, "country": "USA",    "stadium": "Lincoln Financial Field"},
    "Toronto":       {"altitude":   76, "country": "Canada", "stadium": "BMO Field"},
    "Vancouver":     {"altitude":    5, "country": "Canada", "stadium": "BC Place"},
}

# Teams naturally adapted to high altitude (based in cities > 1000m)
HIGH_ALTITUDE_TEAMS = {
    "Bolivia", "Colombia", "Ecuador", "Peru",
    "Mexico",  # Mexico City home
}

# Altitude above which penalty applies (meters)
ALTITUDE_THRESHOLD = 1000

def altitude_xg_factor(venue: Optional[str], team_name: str) -> float:
    """
    Returns an xG multiplier for a team playing at a given venue.
    Teams NOT adapted to altitude suffer a penalty at high-altitude venues.

    - No penalty at venues below 1000m
    - At Mexico City (2240m): up to -10% xG for non-adapted teams
    - At Guadalajara (1566m): up to -5% xG for non-adapted teams
    - High-altitude teams get +3% bonus at altitude venues (familiar conditions)

    Returns float in [0.87, 1.03].
    """
    if not venue:
        return 1.0

    # Try to find venue (case-insensitive partial match)
    venue_data = None
    for v_name, v_data in WC2026_VENUES.items():
        if v_name.lower() in venue.lower() or venue.lower() in v_name.lower():
            venue_data = v_data
            break

    if not venue_data:
        return 1.0

    altitude = venue_data["altitude"]
    if altitude < ALTITUDE_THRESHOLD:
        return 1.0

    # Altitude penalty for non-adapted teams
    is_adapted = team_name in HIGH_ALTITUDE_TEAMS

    if is_adapted:
        return min(1.03, 1.0 + (altitude - ALTITUDE_THRESHOLD) / 10000 * 0.5)
    else:
        # Penalty: -1% per 200m above threshold, max -10%
        penalty = (altitude - ALTITUDE_THRESHOLD) / 200 * 0.01
        return round(max(0.87, 1.0 - penalty), 4)


def get_venue_info(venue: str) -> Optional[dict]:
    """Return venue metadata dict or None."""
    for v_name, v_data in WC2026_VENUES.items():
        if v_name.lower() in venue.lower() or venue.lower() in v_name.lower():
            return {"name": v_name, **v_data}
    return None
