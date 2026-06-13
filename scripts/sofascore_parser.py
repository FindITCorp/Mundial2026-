#!/usr/bin/env python3
"""
Parser unificado de SofaScore (texto copiado manualmente) a CSV.

Detecta automaticamente el tipo de tabla:
  - PLAYERS: estadisticas por jugador (linea continua con nombres de equipo)
  - TEAM:    estadisticas de equipo (trios valor / etiqueta / valor)

Uso:
    python sofascore_parser.py entrada.txt salida.csv
    python sofascore_parser.py entrada.txt                 # imprime en pantalla
    python sofascore_parser.py entrada.txt salida.csv --equipos Brazil,Egypt

Si no se pasan --equipos para una tabla de jugadores, el script intenta
inferirlos del encabezado (los dos nombres que aparecen antes de 'Goles').
"""

import re
import sys
import csv
import io

# ----------------------------------------------------------------------
# DETECCION DE TIPO
# ----------------------------------------------------------------------

def detectar_tipo(texto):
    """Devuelve 'players' o 'team'.

    Heuristica:
      - TEAM: el texto tiene muchos saltos de linea y trios valor/etiqueta/valor.
        Senal fuerte: aparece 'Posesión de balón' o 'Goles esperados'.
      - PLAYERS: linea (casi) continua, contiene 'Valoración Sofascore' y
        nombres de equipo repetidos.
    """
    if "Posesión de balón" in texto or "Goles esperados" in texto:
        return "team"
    if "Valoración Sofascore" in texto:
        return "players"
    # Fallback por densidad de saltos de linea
    lineas = [l for l in texto.splitlines() if l.strip()]
    valores = sum(1 for l in lineas if re.match(r"^(\d+%?|\d+\.\d+|-)$", l.strip()))
    return "team" if valores >= 5 else "players"


# ----------------------------------------------------------------------
# PARSER DE JUGADORES
# ----------------------------------------------------------------------

ETIQUETAS_HEADER_FIN = "Valoración Sofascore"
POSICIONES = {"G", "D", "M", "F", "P"}

COLUMNAS_PLAYERS = [
    "equipo", "jugador", "goles", "asistencias",
    "entradas", "entradas_ganadas",
    "pases_precisos", "pases_total", "pases_pct",
    "duelos_total", "duelos_ganados",
    "duelos_suelo_total", "duelos_suelo_ganados",
    "duelos_aereos_total", "duelos_aereos_ganados",
    "minutos", "posicion", "rating",
]


def inferir_equipos(texto):
    """Intenta sacar los dos equipos del encabezado (antes de 'Goles')."""
    norm = re.sub(r"\s+", " ", texto).strip()
    m = re.search(r"^(.*?)\bGoles\b", norm)
    if not m:
        return []
    cabeza = m.group(1)
    # Los nombres de equipo suelen repetirse; toma palabras capitalizadas
    # unicas, excluyendo simbolos. Heuristica simple.
    candidatos = re.findall(r"[A-ZÁÉÍÓÚ][\wÁÉÍÓÚáéíóúñ]+", cabeza)
    vistos = []
    for c in candidatos:
        if c not in vistos:
            vistos.append(c)
    return vistos[:2]


def parsear_jugadores(texto, equipos):
    texto = re.sub(r"\s+", " ", texto).strip()
    idx = texto.find(ETIQUETAS_HEADER_FIN)
    if idx != -1:
        texto = texto[idx + len(ETIQUETAS_HEADER_FIN):].strip()

    eq_pat = "|".join(re.escape(e) for e in equipos)
    patron = re.compile(rf"({eq_pat})\s+(.*?)(?=(?:{eq_pat})\s|\Z)")

    filas = []
    for equipo, cuerpo in patron.findall(texto):
        filas.append(_parsear_bloque_jugador(equipo, cuerpo.strip()))
    return filas


def _parsear_bloque_jugador(equipo, cuerpo):
    fila = {c: "" for c in COLUMNAS_PLAYERS}
    fila["equipo"] = equipo
    tokens = cuerpo.split()

    # Rating decimal al final
    if tokens and re.fullmatch(r"\d+\.\d+", tokens[-1]):
        fila["rating"] = tokens.pop()
    # Posicion (letra sola) al final
    if tokens and tokens[-1] in POSICIONES:
        fila["posicion"] = tokens.pop()
    # Minutos (token con apostrofo)
    for i, t in enumerate(tokens):
        if re.fullmatch(r"\d+'", t):
            fila["minutos"] = t.rstrip("'")
            tokens.pop(i)
            break

    # Pases A/B (C%) -> ancla que divide entradas (antes) de duelos (despues)
    idx_pases = None
    for i, t in enumerate(tokens):
        m = re.fullmatch(r"(\d+)/(\d+)", t)
        if m:
            fila["pases_precisos"] = m.group(1)
            fila["pases_total"] = m.group(2)
            idx_pases = i
            if i + 1 < len(tokens):
                mp = re.fullmatch(r"\((\d+)%\)", tokens[i + 1])
                if mp:
                    fila["pases_pct"] = mp.group(1)
                    tokens.pop(i + 1)
            tokens.pop(i)
            break

    def extraer_pares(lista):
        pares, resto, i = [], [], 0
        while i < len(lista):
            if (re.fullmatch(r"\d+", lista[i]) and i + 1 < len(lista)
                    and re.fullmatch(r"\(\d+\)", lista[i + 1])):
                pares.append((lista[i], lista[i + 1].strip("()")))
                i += 2
            else:
                resto.append(lista[i])
                i += 1
        return pares, resto

    if idx_pases is not None:
        antes, despues = tokens[:idx_pases], tokens[idx_pases:]
    else:
        antes, despues = tokens, []

    pares_antes, resto_antes = extraer_pares(antes)
    if pares_antes:
        fila["entradas"], fila["entradas_ganadas"] = pares_antes[0]

    pares_despues, resto_despues = extraer_pares(despues)
    destinos = [
        ("duelos_total", "duelos_ganados"),
        ("duelos_suelo_total", "duelos_suelo_ganados"),
        ("duelos_aereos_total", "duelos_aereos_ganados"),
    ]
    for (total, ganados), (col_t, col_g) in zip(pares_despues, destinos):
        fila[col_t], fila[col_g] = total, ganados

    tokens = resto_antes + resto_despues
    numeros = [t for t in tokens if re.fullmatch(r"\d+", t)]
    nombre_tokens = [t for t in tokens if not re.fullmatch(r"\d+", t)]
    fila["jugador"] = " ".join(nombre_tokens).strip()
    if len(numeros) >= 1:
        fila["goles"] = numeros[0]
    if len(numeros) >= 2:
        fila["asistencias"] = numeros[1]
    return fila


# ----------------------------------------------------------------------
# PARSER DE EQUIPO
# ----------------------------------------------------------------------

RUIDO_TEAM = {
    "Resumen del partido", "Mapa de disparos", "Mapa de ataques",
    "Mapa de pases", "Tiros", "Ataque",
    "A mayor intensidad del juego", "A menor intensidad del juego",
}
VALOR_TEAM = re.compile(r"^(\d+%?|\d+\.\d+|-)$")
COLUMNAS_TEAM = ["metrica", "local", "visitante", "es_pct"]


def parsear_equipo(texto, dedup=True):
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    filas, vistos, i = [], set(), 0

    def es_valor(s):
        return bool(VALOR_TEAM.match(s))

    while i < len(lineas) - 2:
        a, b, c = lineas[i], lineas[i + 1], lineas[i + 2]
        if es_valor(a) and (not es_valor(b)) and b not in RUIDO_TEAM and es_valor(c):
            if dedup and b in vistos:
                i += 3
                continue
            vistos.add(b)
            filas.append({
                "metrica": b,
                "local": a.rstrip("%"),
                "visitante": c.rstrip("%"),
                "es_pct": "si" if a.endswith("%") else "no",
            })
            i += 3
        else:
            i += 1
    return filas


# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------

def a_csv(filas, columnas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columnas)
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue()


def validar_jugadores(filas):
    """Devuelve lista de advertencias (no detiene el proceso)."""
    avisos = []
    for f in filas:
        if not f["minutos"]:
            avisos.append(f"Jugador sin minutos: {f['jugador'] or '??'}")
        if not f["posicion"]:
            avisos.append(f"Jugador sin posicion: {f['jugador'] or '??'}")
        if not f["jugador"]:
            avisos.append("Fila sin nombre de jugador (posible error de parseo)")
    return avisos


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    equipos = None
    for a in sys.argv[1:]:
        if a.startswith("--equipos"):
            equipos = a.split("=", 1)[1].split(",") if "=" in a else None
    # Soporta '--equipos Brazil,Egypt' como dos tokens
    if "--equipos" in sys.argv:
        k = sys.argv.index("--equipos")
        if k + 1 < len(sys.argv):
            equipos = sys.argv[k + 1].split(",")

    if not args:
        print("Uso: python sofascore_parser.py entrada.txt [salida.csv] [--equipos A,B]")
        sys.exit(1)

    entrada = args[0]
    salida = args[1] if len(args) >= 2 else None

    with open(entrada, encoding="utf-8") as f:
        texto = f.read()

    tipo = detectar_tipo(texto)

    if tipo == "team":
        filas = parsear_equipo(texto)
        columnas = COLUMNAS_TEAM
        print(f"[detectado: estadisticas de EQUIPO] {len(filas)} metricas", file=sys.stderr)
    else:
        if not equipos:
            equipos = inferir_equipos(texto)
            print(f"[equipos inferidos: {equipos}] usa --equipos para forzar",
                  file=sys.stderr)
        filas = parsear_jugadores(texto, equipos)
        columnas = COLUMNAS_PLAYERS
        print(f"[detectado: estadisticas de JUGADORES] {len(filas)} jugadores",
              file=sys.stderr)
        for aviso in validar_jugadores(filas):
            print(f"  ADVERTENCIA: {aviso}", file=sys.stderr)

    csv_str = a_csv(filas, columnas)
    if salida:
        with open(salida, "w", encoding="utf-8", newline="") as f:
            f.write(csv_str)
        print(f"Escrito en {salida}", file=sys.stderr)
    else:
        print(csv_str)


if __name__ == "__main__":
    main()
