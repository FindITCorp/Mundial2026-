"""
Parser de stats de equipo desde texto plano copiado de Sofascore (ES).
Divide el texto en bloques por "Resumen del partido" y extrae las
estadísticas al esquema de match_team_stats.

Uso como módulo:  from load_sofascore_text import parse_blocks
Uso directo:      python3 scripts/load_sofascore_text.py <archivo.txt>
                  (solo imprime los bloques parseados, no escribe DB)
"""
import re
import sys

# etiqueta → columna mts (patrón triple: valor_local / etiqueta / valor_visitante)
TRIPLES = {
    "Posesión de balón": "possession",
    "Goles esperados (xG)": "xg",
    "Ocasiones claras": "clear_chances",
    "Tiros totales": "shots_total",
    "Paradas": "saves",
    "Saques de esquina": "corners",
    "Faltas": "fouls",
    "Pases": "passes_total",
    "Entradas": "tackles_total",
    "Tiros libres": "free_kicks",
    "Tarjetas amarillas": "yellow_cards",
    "Tarjetas rojas": "red_cards",
    "Tiros a puerta": "shots_on_target",
    "Tiros fuera": "shots_off_target",
    "Tiros bloqueados": "shots_blocked",
    "Tiros adentro del área penal": "shots_inside_box",
    "Tiros fuera del área": "shots_outside_box",
    "Toques dentro del área": "touches_box",
    "Fueras de juego": "offsides",
    "Pases precisos": "passes_accurate",
    "Pases al último tercio": "passes_final_third",
    "Intercepciones": "interceptions",
    "Recuperaciones": "recoveries",
    "Despejes": "clearances",
    "Grandes paradas": "big_saves",
    "Tackles totales": "tackles_total",
}

# etiqueta → prefijo; formato: ganados_local/total · pct / etiqueta / pct · ganados_vis/total
# (el total del duelo es compartido entre ambos equipos)
SHARED_PAIRS = {"Duelos en el suelo": "ground", "Duelos aéreos": "aerial"}

# etiqueta → (col_acc, col_total); formato: acc/total por equipo a cada lado
PER_TEAM_PAIRS = {
    "Pases largos": ("long_balls_accurate", "long_balls_total"),
    "Centros": ("crosses_accurate", "crosses_total"),
}


def _num(s):
    s = s.strip().rstrip("%")
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.\d+", s):
        return float(s)
    return None


def _pair(s):
    m = re.fullmatch(r"(\d+)/(\d+)", s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_block(lines):
    """Devuelve (home: dict, away: dict) con columnas de match_team_stats."""
    home, away, extra = {}, {}, {}
    n = len(lines)
    for i, l in enumerate(lines):
        if l in TRIPLES:
            col = TRIPLES[l]
            if col in home:
                continue  # primera aparición gana (la del resumen)
            hv = _num(lines[i - 1]) if i > 0 else None
            av = _num(lines[i + 1]) if i + 1 < n else None
            if hv is not None and av is not None:
                home[col], away[col] = hv, av
        elif l in SHARED_PAIRS:
            p = SHARED_PAIRS[l]
            ph = _pair(lines[i - 2]) if i >= 2 else None
            pa = _pair(lines[i + 2]) if i + 2 < n else None
            if ph and pa:
                extra[p] = (ph, pa)  # ((won_h, tot), (won_a, tot))
        elif l in PER_TEAM_PAIRS:
            ca, ct = PER_TEAM_PAIRS[l]
            ph = _pair(lines[i - 2]) if i >= 2 else None
            pa = _pair(lines[i + 2]) if i + 2 < n else None
            if ph:
                home[ca], home[ct] = ph
            if pa:
                away[ca], away[ct] = pa
        elif l == "Entradas ganadas":
            hv = _num(lines[i - 1]) if i > 0 else None
            av = _num(lines[i + 1]) if i + 1 < n else None
            if hv is not None and av is not None:
                extra["tackles_won_pct"] = (hv, av)

    # duelos suelo + aéreos → duels_total / duels_won / aerial_*
    if "ground" in extra:
        (gwh, gt), (gwa, _) = extra["ground"]
        awh = awa = at = 0
        if "aerial" in extra:
            (awh, at), (awa, _) = extra["aerial"]
            home["aerial_total"] = away["aerial_total"] = at
            home["aerial_won"], away["aerial_won"] = awh, awa
        home["duels_total"] = away["duels_total"] = gt + at
        home["duels_won"], away["duels_won"] = gwh + awh, gwa + awa

    if "tackles_won_pct" in extra and "tackles_total" in home:
        ph, pa = extra["tackles_won_pct"]
        home["tackles_won"] = round(ph / 100 * home["tackles_total"])
        away["tackles_won"] = round(pa / 100 * away["tackles_total"])

    for d in (home, away):
        if d.get("passes_total") and d.get("passes_accurate"):
            d["passes_pct"] = round(d["passes_accurate"] / d["passes_total"] * 100, 1)
    return home, away


def parse_blocks(text):
    """Divide el texto por 'Resumen del partido' y parsea cada bloque."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    idxs = [i for i, l in enumerate(lines) if l == "Resumen del partido"]
    blocks = []
    for j, st in enumerate(idxs):
        end = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        blocks.append(parse_block(lines[st:end]))
    return blocks


if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    for k, (h, a) in enumerate(parse_blocks(text), 1):
        # goles deducidos: SoT propio − paradas rival (control de identidad del partido)
        gh = (h.get("shots_on_target") or 0) - (a.get("saves") or 0)
        ga = (a.get("shots_on_target") or 0) - (h.get("saves") or 0)
        print(f"B{k}: pos={h.get('possession')}-{a.get('possession')} "
              f"xG={h.get('xg')}-{a.get('xg')} tiros={h.get('shots_total')}-{a.get('shots_total')} "
              f"SoT={h.get('shots_on_target')}-{a.get('shots_on_target')} → goles deducidos {gh}-{ga}")
