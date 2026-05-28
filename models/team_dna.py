"""
team_dna.py — Team identity profiles and tactical matchup engine for WC2026.

Each team has a DNA profile (11 quantified attributes, 0-10 scale) representing
their playing identity. Matchup functions compute xG multipliers based on how
each team's strengths interact with their opponent's weaknesses.

Usage:
    from models.team_dna import get_team_dna, matchup_xg_factor, format_matchup_analysis

    dna_france = get_team_dna("France")
    dna_panama = get_team_dna("Panama")
    factor = matchup_xg_factor(dna_france, dna_panama)  # France attacking Panama
    # factor ≈ 1.18 (pace mismatch + technical advantage)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeamDNA:
    name: str
    aerial_strength: float        # 0-10
    pace_rating: float            # 0-10
    technical_quality: float      # 0-10
    counter_threat: float         # 0-10
    defensive_organization: float # 0-10
    physical_strength: float      # 0-10
    big_game_mentality: float     # 0-10
    pressing_vulnerability: float # 0-10 (higher=weaker vs press)
    pace_vulnerability: float     # 0-10 (higher=weaker vs pace)
    aerial_vulnerability: float   # 0-10 (higher=weaker in the air)
    defensive_line_height: float  # 1-10 (10=very high, 1=very low)
    strengths: list[str]          # top 3 strengths as text
    weaknesses: list[str]         # top 3 weaknesses as text


TEAM_DNA: dict[str, TeamDNA] = {
    "France": TeamDNA(
        name="France", aerial_strength=7.5, pace_rating=9.5, technical_quality=8.5,
        counter_threat=8.5, defensive_organization=8.0, physical_strength=7.5,
        big_game_mentality=9.5, pressing_vulnerability=3.5, pace_vulnerability=4.0,
        aerial_vulnerability=5.0, defensive_line_height=8.0,
        strengths=["Velocidad devastadora en transición (Mbappé)", "Gran mentalidad en partidos grandes", "Profundidad de plantel de clase mundial"],
        weaknesses=["Dependencia excesiva de Mbappé", "Susceptible a equipos que presionan alto en salida", "Defensa puede fallar ante balones colgados"]
    ),
    "Spain": TeamDNA(
        name="Spain", aerial_strength=5.5, pace_rating=7.0, technical_quality=9.5,
        counter_threat=5.0, defensive_organization=8.5, physical_strength=6.0,
        big_game_mentality=9.0, pressing_vulnerability=4.0, pace_vulnerability=5.5,
        aerial_vulnerability=5.5, defensive_line_height=9.0,
        strengths=["Mejor calidad técnica y de posesión del torneo", "Presión organizada recupera el balón alto", "Juego de tiki-taka desgasta rivales"],
        weaknesses=["Baja estatura media: vulnerable a balones aéreos", "Línea alta expuesta a contraataques con velocidad", "Poca amenaza directa por arriba en córners"]
    ),
    "Argentina": TeamDNA(
        name="Argentina", aerial_strength=7.0, pace_rating=8.0, technical_quality=9.0,
        counter_threat=8.0, defensive_organization=8.5, physical_strength=8.0,
        big_game_mentality=9.5, pressing_vulnerability=4.0, pace_vulnerability=4.5,
        aerial_vulnerability=5.0, defensive_line_height=8.0,
        strengths=["Messi: factor diferencial en momentos decisivos", "Organización defensiva excepcional (Scaloni)", "Mentalidad ganadora probada en Mundiales"],
        weaknesses=["Post-Messi: generación de juego puede caer", "Velocidad media en la defensa central", "Dependencia del estado de forma de Messi"]
    ),
    "England": TeamDNA(
        name="England", aerial_strength=8.5, pace_rating=7.5, technical_quality=8.0,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=8.0,
        big_game_mentality=7.5, pressing_vulnerability=4.5, pace_vulnerability=5.0,
        aerial_vulnerability=5.5, defensive_line_height=8.0,
        strengths=["Amenaza aérea brutal en balones parados (Stones, Maguire)", "Delanteros veloces y directos", "Profundidad en ataque (Saka, Bellingham, Kane)"],
        weaknesses=["Historial de presión en torneos grandes", "Puede volverse predecible en ataque", "Central lento puede ser explotado por delantera rápida"]
    ),
    "Portugal": TeamDNA(
        name="Portugal", aerial_strength=7.0, pace_rating=7.5, technical_quality=9.0,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=7.5,
        big_game_mentality=8.5, pressing_vulnerability=4.5, pace_vulnerability=5.0,
        aerial_vulnerability=5.5, defensive_line_height=8.0,
        strengths=["Bruno Fernandes: creatividad y trabajo desde mediocampo", "Variedad ofensiva: múltiples generadores de juego", "Solidez defensiva mejorada en era Martínez"],
        weaknesses=["Transición post-Ronaldo aún en proceso", "Puede sufrir con equipos que presionan alto", "Dependencia de Bruno Fernandes en mediocampo"]
    ),
    "Brazil": TeamDNA(
        name="Brazil", aerial_strength=7.0, pace_rating=8.5, technical_quality=9.0,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=7.5,
        big_game_mentality=9.5, pressing_vulnerability=4.0, pace_vulnerability=4.5,
        aerial_vulnerability=5.5, defensive_line_height=8.0,
        strengths=["Habilidad técnica individual superior", "Profundidad ofensiva con velocidad en bandas", "Transiciones rápidas con Rodrygo/Vinicius"],
        weaknesses=["Fragilidad defensiva en transiciones (WC2014/2018)", "Puede ser inconsistente en partidos de bajo perfil", "Mediocampo a veces desconectado defensivamente"]
    ),
    "Netherlands": TeamDNA(
        name="Netherlands", aerial_strength=8.0, pace_rating=8.0, technical_quality=8.5,
        counter_threat=7.5, defensive_organization=8.0, physical_strength=7.5,
        big_game_mentality=8.0, pressing_vulnerability=4.0, pace_vulnerability=4.5,
        aerial_vulnerability=5.5, defensive_line_height=8.0,
        strengths=["Juego aéreo en balones parados (van Dijk)", "Velocidad y calidad técnica combinada", "Pressing organizado de alto rendimiento"],
        weaknesses=["Historial de implosión en semfinales", "Dependencia de van Dijk en defensa", "Pueden tener inconsistencia entre grupo y eliminatorias"]
    ),
    "Morocco": TeamDNA(
        name="Morocco", aerial_strength=7.5, pace_rating=7.0, technical_quality=7.5,
        counter_threat=8.5, defensive_organization=9.0, physical_strength=8.5,
        big_game_mentality=8.0, pressing_vulnerability=5.0, pace_vulnerability=5.5,
        aerial_vulnerability=6.0, defensive_line_height=6.0,
        strengths=["Mejor organización defensiva de WC2022 (0.54 GA/match)", "Contraataque letal desde bloque bajo", "Unidad y mentalidad de equipo excepcional"],
        weaknesses=["Juego aéreo en córners defensivos (44% goles propios de balón parado)", "Generación de juego limitada sin Hakimi proyectado", "Poca amenaza en pelota parada ofensiva propia"]
    ),
    "Belgium": TeamDNA(
        name="Belgium", aerial_strength=7.5, pace_rating=7.0, technical_quality=8.5,
        counter_threat=7.0, defensive_organization=7.0, physical_strength=7.5,
        big_game_mentality=7.5, pressing_vulnerability=5.0, pace_vulnerability=5.5,
        aerial_vulnerability=5.5, defensive_line_height=7.0,
        strengths=["Experiencia: generación dorada con Lukaku/De Bruyne", "Calidad técnica en mediocampo", "Amenaza aérea en córners (Lukaku)"],
        weaknesses=["Generación mayor con piernas que se van acabando", "Defensa puede ser lenta lateralmente", "Semiretiro de figuras clave en curso"]
    ),
    "Germany": TeamDNA(
        name="Germany", aerial_strength=8.5, pace_rating=8.0, technical_quality=8.5,
        counter_threat=7.5, defensive_organization=8.0, physical_strength=8.0,
        big_game_mentality=9.0, pressing_vulnerability=4.0, pace_vulnerability=4.5,
        aerial_vulnerability=5.0, defensive_line_height=9.0,
        strengths=["Presión altísima e intensa (Nagelsmann)", "Amenaza aérea en balones parados (Rüdiger, Süle)", "Organización táctica de elite, adaptabilidad"],
        weaknesses=["Línea muy alta: contraataques de equipos veloces", "Reconstrucción en curso tras WC2018/2022", "Portería: nivel inferior al histórico"]
    ),
    "USA": TeamDNA(
        name="USA", aerial_strength=6.5, pace_rating=8.5, technical_quality=7.5,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=8.0,
        big_game_mentality=7.0, pressing_vulnerability=5.0, pace_vulnerability=5.5,
        aerial_vulnerability=6.0, defensive_line_height=8.0,
        strengths=["Atletismo y velocidad excepcional (Pulisic, Weah)", "Pressing físico alto (Pochettino)", "Juega en casa (local bonus en WC2026)"],
        weaknesses=["Experiencia en grandes torneos aún en desarrollo", "Gestión del juego posicional: inferior a élite europea", "Susceptible a equipos que circulan el balón pacientemente"]
    ),
    "Japan": TeamDNA(
        name="Japan", aerial_strength=4.5, pace_rating=8.0, technical_quality=8.0,
        counter_threat=8.5, defensive_organization=8.5, physical_strength=5.5,
        big_game_mentality=7.5, pressing_vulnerability=5.5, pace_vulnerability=5.0,
        aerial_vulnerability=7.5, defensive_line_height=8.0,
        strengths=["Organización táctica y disciplina colectiva excepcional", "Transiciones rapidísimas (WC2022: eliminó a España y Alemania)", "Pressing organizado que sorprende a equipos superiores"],
        weaknesses=["Poca estatura: muy vulnerable en balones aéreos", "Físicamente inferior vs. europeos/africanos", "Baja producción individual de talla mundial"]
    ),
    "Croatia": TeamDNA(
        name="Croatia", aerial_strength=7.5, pace_rating=6.5, technical_quality=8.5,
        counter_threat=7.0, defensive_organization=8.5, physical_strength=7.5,
        big_game_mentality=9.0, pressing_vulnerability=5.5, pace_vulnerability=6.0,
        aerial_vulnerability=5.5, defensive_line_height=6.0,
        strengths=["Experiencia y mentalidad excepcional en eliminatorias", "Calidad técnica de mediocampo (Modrić, Kovačić)", "Compactidad defensiva y disciplina táctica"],
        weaknesses=["Velocidad defensiva limitada (Gvardiol es la excepción)", "Generación envejeciendo: Modrić 40 años en 2026", "Juego de transición lento: vulnerable a equipos veloces"]
    ),
    "Colombia": TeamDNA(
        name="Colombia", aerial_strength=7.0, pace_rating=8.0, technical_quality=8.0,
        counter_threat=8.0, defensive_organization=7.0, physical_strength=7.0,
        big_game_mentality=7.5, pressing_vulnerability=5.0, pace_vulnerability=5.5,
        aerial_vulnerability=5.5, defensive_line_height=7.0,
        strengths=["Velocidad y habilidad técnica en transiciones (Díaz, Díaz)", "Copa América 2024: mejor equipo de CONMEBOL reciente", "Luis Díaz: factor diferencial de clase mundial"],
        weaknesses=["Defensa puede ser vulnerable en transiciones", "Rendimiento irregular vs. defensas muy organizadas", "Historia de fragilidad mental en momentos clave"]
    ),
    "Mexico": TeamDNA(
        name="Mexico", aerial_strength=6.0, pace_rating=7.5, technical_quality=7.5,
        counter_threat=7.5, defensive_organization=7.0, physical_strength=6.5,
        big_game_mentality=7.5, pressing_vulnerability=5.5, pace_vulnerability=6.0,
        aerial_vulnerability=6.5, defensive_line_height=6.0,
        strengths=["Ventaja de altitud en Azteca (2,240m)", "Local advantage WC2026 (juega en casa)", "Historia sólida en fases de grupos"],
        weaknesses=["Maldición del quinto partido: nunca pasó a cuartos", "Juego aéreo defensivo vulnerable", "Dependencia excesiva del espacio para contragolpear"]
    ),
    "Uruguay": TeamDNA(
        name="Uruguay", aerial_strength=8.0, pace_rating=7.0, technical_quality=7.5,
        counter_threat=7.5, defensive_organization=8.5, physical_strength=9.0,
        big_game_mentality=8.5, pressing_vulnerability=4.5, pace_vulnerability=6.0,
        aerial_vulnerability=5.0, defensive_line_height=7.0,
        strengths=["Físico e intensidad defensiva superior (Bielsa)", "Tradición histórica de resultados en Mundiales", "Compactidad y garra como señas de identidad"],
        weaknesses=["Velocidad relativa inferior en defensa central", "Post-Suárez/Cavani: potencia ofensiva reducida", "Sistema de Bielsa exige mucho físicamente: riesgo de fatiga"]
    ),
    "Switzerland": TeamDNA(
        name="Switzerland", aerial_strength=7.0, pace_rating=7.0, technical_quality=8.0,
        counter_threat=7.5, defensive_organization=8.5, physical_strength=7.5,
        big_game_mentality=7.5, pressing_vulnerability=4.5, pace_vulnerability=5.5,
        aerial_vulnerability=5.5, defensive_line_height=7.0,
        strengths=["38% de goles desde balón parado: especialistas en set pieces", "Organización defensiva consistente (Elvedi, Akanji)", "Rendimiento sólido en eliminaciones directas (historial reciente)"],
        weaknesses=["Generación de juego limitada sin Xhaka dominante", "Poca creatividad individual para abrir defensas cerradas", "Ofensiva depende de balones parados para marcar"]
    ),
    "South Korea": TeamDNA(
        name="South Korea", aerial_strength=6.0, pace_rating=8.5, technical_quality=7.5,
        counter_threat=8.0, defensive_organization=7.5, physical_strength=7.0,
        big_game_mentality=7.0, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=6.0, defensive_line_height=7.0,
        strengths=["Velocidad en transiciones (Son Heung-min)", "Disciplina táctica y trabajo colectivo", "Capacidad de sorpresa táctica ante equipos superiores"],
        weaknesses=["Poca presencia aérea defensiva", "Bajo rendimiento sostenido vs. élite europea", "Dependencia de Son en transiciones"]
    ),
    "Ecuador": TeamDNA(
        name="Ecuador", aerial_strength=7.5, pace_rating=6.5, technical_quality=7.0,
        counter_threat=7.0, defensive_organization=7.0, physical_strength=8.0,
        big_game_mentality=6.5, pressing_vulnerability=6.0, pace_vulnerability=6.5,
        aerial_vulnerability=6.5, defensive_line_height=6.0,
        strengths=["Presencia física dominante (Valencia el 9 central)", "Ventaja histórica de altitud (Quito)", "Solidez defensiva basada en físico"],
        weaknesses=["Juego técnico limitado bajo presión alta", "Vulnerable a equipos con velocidad en bandas", "Generación de juego escasa en mediocampo"]
    ),
    "Senegal": TeamDNA(
        name="Senegal", aerial_strength=8.0, pace_rating=8.5, technical_quality=7.0,
        counter_threat=8.0, defensive_organization=7.0, physical_strength=9.0,
        big_game_mentality=7.5, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=6.5, defensive_line_height=7.0,
        strengths=["Físico y atletismo supremo (Koulibaly, Mendy)", "Sadio Mané: velocidad y gol de clase mundial", "Presión colectiva intensa"],
        weaknesses=["Juego técnico de construcción limitado", "Mediocampo puede ser desordenado sin presión alta", "Concede muchos desde set pieces defensivos"]
    ),
    "Iran": TeamDNA(
        name="Iran", aerial_strength=7.5, pace_rating=5.5, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=8.5, physical_strength=7.5,
        big_game_mentality=6.5, pressing_vulnerability=6.5, pace_vulnerability=7.5,
        aerial_vulnerability=5.5, defensive_line_height=4.0,
        strengths=["Organización defensiva de bloque bajo (5-4-1)", "Disciplina táctica y unidad colectiva", "Resistencia física en partidos de alto desgaste"],
        weaknesses=["Muy lenta defensivamente: devastada por equipos veloces", "Poca generación ofensiva propia", "Vulnerable a presión alta por su juego de salida"]
    ),
    "Austria": TeamDNA(
        name="Austria", aerial_strength=7.0, pace_rating=8.0, technical_quality=8.0,
        counter_threat=7.5, defensive_organization=8.0, physical_strength=7.5,
        big_game_mentality=7.0, pressing_vulnerability=4.0, pace_vulnerability=4.5,
        aerial_vulnerability=5.5, defensive_line_height=9.0,
        strengths=["Pressing más intenso del torneo (Rangnick: press=7.5, línea muy alta)", "Calidad técnica de jugadores en Bundesliga alemana", "David Alaba y Arnautovic: jugadores de clase mundial"],
        weaknesses=["Línea extremadamente alta: máximo riesgo de contraataques", "Poca experiencia en eliminatorias mundiales recientes", "Presión intensa puede generar fatiga en el torneo"]
    ),
    "Turkey": TeamDNA(
        name="Turkey", aerial_strength=7.0, pace_rating=7.0, technical_quality=7.5,
        counter_threat=7.0, defensive_organization=7.0, physical_strength=7.5,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=6.0, defensive_line_height=6.0,
        strengths=["Hakan Çalhanoğlu: uno de los mejores mediocampistas del torneo", "Versatilidad táctica (puede defender y atacar con calidad)", "Rendimiento sólido en clasificatorias UEFA"],
        weaknesses=["Rendimiento irregular en torneos grandes", "Defensa puede sufrir contra equipos de alta movilidad", "Dependencia de Çalhanoğlu en mediocampo"]
    ),
    "Iraq": TeamDNA(
        name="Iraq", aerial_strength=6.5, pace_rating=6.5, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=7.5, physical_strength=7.0,
        big_game_mentality=5.0, pressing_vulnerability=6.5, pace_vulnerability=7.0,
        aerial_vulnerability=6.5, defensive_line_height=4.0,
        strengths=["Disciplina defensiva en bloque bajo", "Experiencia en torneos AFC", "Físico y determinación colectiva"],
        weaknesses=["Poca experiencia en Mundiales (primera vez desde 1986)", "Técnica bajo presión: muy limitada", "Vulnerable a velocidad y pressing alto"]
    ),
    "Saudi Arabia": TeamDNA(
        name="Saudi Arabia", aerial_strength=6.5, pace_rating=7.0, technical_quality=7.0,
        counter_threat=7.5, defensive_organization=7.0, physical_strength=6.5,
        big_game_mentality=6.5, pressing_vulnerability=6.0, pace_vulnerability=6.5,
        aerial_vulnerability=6.0, defensive_line_height=6.0,
        strengths=["Sorpresa táctica demostrada (derrotó a Argentina WC2022)", "Contraataque rápido con línea alta rival", "Organización y cohesión en bloques defensivos"],
        weaknesses=["Liga local (Saudi Pro League) de nivel bajo", "Poco rodaje vs. equipos de primer nivel europeo", "Vulnerable a presión sostenida de equipos técnicos"]
    ),
    "Australia": TeamDNA(
        name="Australia", aerial_strength=7.5, pace_rating=6.5, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=7.0, physical_strength=8.0,
        big_game_mentality=6.5, pressing_vulnerability=6.0, pace_vulnerability=6.5,
        aerial_vulnerability=6.5, defensive_line_height=6.0,
        strengths=["Físico e intensidad (típico juego australiano)", "Mat Ryan: portero de clase Premier League", "Unidad de equipo y mentalidad guerrera"],
        weaknesses=["Calidad técnica limitada vs. equipos superiores", "Poca creatividad en ataque posicional", "Vulnerable a pressing alto en salida"]
    ),
    "Algeria": TeamDNA(
        name="Algeria", aerial_strength=7.0, pace_rating=7.5, technical_quality=7.0,
        counter_threat=7.5, defensive_organization=7.0, physical_strength=7.0,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=6.0, defensive_line_height=6.0,
        strengths=["Riyad Mahrez: velocidad y desequilibrio individual", "Potencia en transiciones ofensivas", "Cohesión de equipo campeón AFCON 2019"],
        weaknesses=["Rendimiento inconsistente en grandes torneos", "Dependencia alta de Mahrez para generar juego", "Defensivamente frágil en marcadores de desventaja"]
    ),
    "Scotland": TeamDNA(
        name="Scotland", aerial_strength=7.5, pace_rating=6.5, technical_quality=7.0,
        counter_threat=7.0, defensive_organization=7.5, physical_strength=8.0,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=6.5,
        aerial_vulnerability=6.0, defensive_line_height=6.0,
        strengths=["Robertson y Tierney: laterales de clase Premier League", "Intensidad física y juego directo", "Pressing bien organizado bajo Steve Clarke"],
        weaknesses=["Poco histórico en Mundiales (primer mundial desde 1998)", "Calidad ofensiva limitada para grandes torneos", "Vulnerable a equipos con velocidad en banda"]
    ),
    "Paraguay": TeamDNA(
        name="Paraguay", aerial_strength=7.5, pace_rating=6.5, technical_quality=6.5,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=8.5,
        big_game_mentality=6.5, pressing_vulnerability=6.0, pace_vulnerability=7.0,
        aerial_vulnerability=6.0, defensive_line_height=5.0,
        strengths=["Físico agresivo y batalla defensiva", "Juego aéreo en balones detenidos (atacante alto)", "Disciplina táctica en bloque bajo"],
        weaknesses=["Generación de juego técnico limitada", "Velocidad defensiva baja (vulnerable a transiciones)", "Poca creatividad en construcción desde atrás"]
    ),
    "Norway": TeamDNA(
        name="Norway", aerial_strength=8.5, pace_rating=7.5, technical_quality=7.0,
        counter_threat=8.0, defensive_organization=6.5, physical_strength=7.5,
        big_game_mentality=6.0, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=7.0, defensive_line_height=7.0,
        strengths=["Erling Haaland: el delantero más peligroso del torneo", "Martin Ødegaard: control y creatividad en mediocampo", "Amenaza aérea absoluta con Haaland (1.94m)"],
        weaknesses=["Primera participación en Mundial desde 1998: poca experiencia", "Vulnerables en balones parados defensivos (media estatura)", "Dependencia extrema de Haaland para el gol"]
    ),
    "Ghana": TeamDNA(
        name="Ghana", aerial_strength=7.5, pace_rating=8.0, technical_quality=7.0,
        counter_threat=8.0, defensive_organization=6.5, physical_strength=7.5,
        big_game_mentality=7.0, pressing_vulnerability=5.5, pace_vulnerability=6.0,
        aerial_vulnerability=6.5, defensive_line_height=6.0,
        strengths=["Velocidad y explosividad en transiciones", "Calidad individual de jugadores de Premier League", "Historia competitiva en Mundiales"],
        weaknesses=["Inconsistencia táctica y defensiva", "Organización puede fallar en segundas partes", "Vulnerable a pressing alto organizado"]
    ),
    "Ivory Coast": TeamDNA(
        name="Ivory Coast", aerial_strength=7.5, pace_rating=8.5, technical_quality=7.5,
        counter_threat=8.0, defensive_organization=6.5, physical_strength=8.0,
        big_game_mentality=7.0, pressing_vulnerability=5.5, pace_vulnerability=5.5,
        aerial_vulnerability=6.5, defensive_line_height=7.0,
        strengths=["Velocidad y físico devastador en bandas", "Haller y Pépé: amenaza constante", "Campeones AFCON 2023: mentalidad ganadora renovada"],
        weaknesses=["Organización defensiva inconsistente", "Vulnerable a presión organizada en su propio campo", "Tendencia a debilitarse tras marcador adverso"]
    ),
    "Egypt": TeamDNA(
        name="Egypt", aerial_strength=7.0, pace_rating=7.0, technical_quality=7.5,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=7.0,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=6.0,
        aerial_vulnerability=6.0, defensive_line_height=5.0,
        strengths=["Mohamed Salah: clase mundial absoluta en ataque", "Contraataque eficiente con Salah", "Disciplina defensiva de bloque medio"],
        weaknesses=["Sin Salah el equipo pierde la mitad de su amenaza", "Poca calidad en mediocampo generativo", "Lenta salida desde atrás bajo presión"]
    ),
    "Sweden": TeamDNA(
        name="Sweden", aerial_strength=8.5, pace_rating=6.5, technical_quality=7.0,
        counter_threat=7.0, defensive_organization=7.5, physical_strength=8.0,
        big_game_mentality=7.0, pressing_vulnerability=5.5, pace_vulnerability=7.0,
        aerial_vulnerability=5.5, defensive_line_height=6.0,
        strengths=["Juego aéreo superior: Isak, Gyökeres son jugadores altos y físicos", "Victor Gyökeres: goleador de clase mundial (Sporting CP)", "Organización colectiva y mentalidad nórdica"],
        weaknesses=["Velocidad defensiva limitada en defensas centrales", "Poco creativo en juego combinativo posicional", "Vulnerable a equipos rápidos que atacan por detrás"]
    ),
    "Czechia": TeamDNA(
        name="Czechia", aerial_strength=7.5, pace_rating=7.0, technical_quality=7.5,
        counter_threat=7.5, defensive_organization=7.5, physical_strength=7.5,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=6.0,
        aerial_vulnerability=5.5, defensive_line_height=6.0,
        strengths=["Schick: goleador de nivel Bundesliga", "Balón parado efectivo históricamente", "Organización táctica sólida"],
        weaknesses=["Creatividad limitada en construcción posicional", "Sin experiencia reciente en grandes torneos", "Faltan jugadores de nivel top europeo en mediocampo"]
    ),
    "Panama": TeamDNA(
        name="Panama", aerial_strength=6.5, pace_rating=6.0, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=7.5, physical_strength=7.0,
        big_game_mentality=6.0, pressing_vulnerability=7.0, pace_vulnerability=7.5,
        aerial_vulnerability=7.0, defensive_line_height=5.0,
        strengths=["Organización defensiva y disciplina táctica", "Unidad de equipo y mentalidad colectiva", "Solidez en bloque bajo difícil de penetrar"],
        weaknesses=["Vulnerable a equipos veloces que atacan por detrás (defensa lenta)", "Técnica bajo presión alta: limitada (Liga Panameña nivel bajo)", "Poca amenaza aérea propia en córners"]
    ),
    "Tunisia": TeamDNA(
        name="Tunisia", aerial_strength=7.0, pace_rating=6.5, technical_quality=6.5,
        counter_threat=7.0, defensive_organization=7.5, physical_strength=7.5,
        big_game_mentality=6.0, pressing_vulnerability=6.0, pace_vulnerability=6.5,
        aerial_vulnerability=6.5, defensive_line_height=5.0,
        strengths=["Físico e intensidad defensiva", "Organización en bloque compacto", "Mentalidad competitiva ante rivales superiores"],
        weaknesses=["Poca calidad ofensiva para proponer en ataque", "Vulnerable a balones aéreos en corner propio", "Liga de Tunicia: nivel inferior al europeo"]
    ),
    "DR Congo": TeamDNA(
        name="DR Congo", aerial_strength=8.0, pace_rating=8.5, technical_quality=7.0,
        counter_threat=8.0, defensive_organization=6.0, physical_strength=8.5,
        big_game_mentality=5.5, pressing_vulnerability=6.5, pace_vulnerability=6.5,
        aerial_vulnerability=7.5, defensive_line_height=5.0,
        strengths=["Explosividad y físico africano excepcional", "Velocidad en bandas: desequilibrante", "Habilidad técnica individual sorprendente"],
        weaknesses=["Organización defensiva muy frágil", "Poca experiencia en torneos mundiales", "Muy vulnerables en córners y balones parados defensivos"]
    ),
    "Canada": TeamDNA(
        name="Canada", aerial_strength=7.0, pace_rating=8.5, technical_quality=7.5,
        counter_threat=8.0, defensive_organization=7.5, physical_strength=7.5,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=5.0,
        aerial_vulnerability=6.5, defensive_line_height=8.0,
        strengths=["Jonathan David: uno de los mejores delanteros del torneo", "Velocidad y presión alta organizada", "Alphonso Davies: el mejor lateral izquierdo del torneo"],
        weaknesses=["Primera generación histórica: poca experiencia en presión", "Pueden desordenarse bajo pressing de élite", "Defensa central puede sufrir vs. delanteras físicas y aéreas"]
    ),
    "Jordan": TeamDNA(
        name="Jordan", aerial_strength=6.5, pace_rating=6.5, technical_quality=6.5,
        counter_threat=7.0, defensive_organization=7.5, physical_strength=6.5,
        big_game_mentality=5.0, pressing_vulnerability=7.0, pace_vulnerability=7.0,
        aerial_vulnerability=6.5, defensive_line_height=4.0,
        strengths=["Disciplina táctica defensiva", "Capacidad de sorpresa ante rivales de mayor nivel (derrotó a Corea en Copa Asia 2023)", "Mentalidad de equipo unido"],
        weaknesses=["Primera participación en Mundial: inexperiencia total", "Liga Jordana: nivel muy bajo comparado al global", "Muy vulnerable a presión alta y equipos veloces"]
    ),
    "Uzbekistan": TeamDNA(
        name="Uzbekistan", aerial_strength=6.5, pace_rating=6.5, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=7.0, physical_strength=7.0,
        big_game_mentality=5.0, pressing_vulnerability=6.5, pace_vulnerability=7.0,
        aerial_vulnerability=6.5, defensive_line_height=5.0,
        strengths=["Físico y resistencia en partidos largos", "Disciplina colectiva de equipo AFC", "Sorpresa táctica posible contra equipos confiados"],
        weaknesses=["Liga uzbeka de nivel muy bajo", "Poca experiencia internacional de primer nivel", "Técnica limitada bajo presión alta"]
    ),
    "Qatar": TeamDNA(
        name="Qatar", aerial_strength=6.0, pace_rating=6.5, technical_quality=7.0,
        counter_threat=6.5, defensive_organization=6.5, physical_strength=6.0,
        big_game_mentality=5.5, pressing_vulnerability=7.0, pace_vulnerability=7.0,
        aerial_vulnerability=7.0, defensive_line_height=5.0,
        strengths=["Experiencia de haber organizado WC2022", "Almoez Ali: goleador histórico de Copa Asia", "Juego posicional entrenado bajo Marquez"],
        weaknesses=["WC2022: primer anfitrión eliminado en fase de grupos", "Físico y velocidad muy inferior a Europa/América", "Muy vulnerable a pressing alto y físico"]
    ),
    "South Africa": TeamDNA(
        name="South Africa", aerial_strength=7.5, pace_rating=8.0, technical_quality=6.5,
        counter_threat=7.5, defensive_organization=6.5, physical_strength=8.0,
        big_game_mentality=6.0, pressing_vulnerability=6.0, pace_vulnerability=6.0,
        aerial_vulnerability=7.0, defensive_line_height=5.0,
        strengths=["Velocidad y físico en bandas", "Intensidad defensiva", "Ronwen Williams: portero de nivel AFC"],
        weaknesses=["Organización ofensiva inconsistente", "Vulnerable a balones parados defensivos", "Poco rodaje vs. equipos europeos de nivel"]
    ),
    "Bosnia and Herzegovina": TeamDNA(
        name="Bosnia and Herzegovina", aerial_strength=8.5, pace_rating=6.5, technical_quality=7.0,
        counter_threat=7.5, defensive_organization=7.0, physical_strength=8.5,
        big_game_mentality=6.5, pressing_vulnerability=5.5, pace_vulnerability=7.5,
        aerial_vulnerability=6.0, defensive_line_height=5.0,
        strengths=["Edin Džeko: líder goleador histórico de clase europea", "Físico imponente en ataque y mediocampo", "Amenaza aérea en balones parados (Džeko + Sesar)"],
        weaknesses=["Defensa lenta: muy vulnerable a contraataques veloces", "Pocas opciones más allá de Džeko en ataque", "Poca experiencia mundialista reciente"]
    ),
    "Cape Verde": TeamDNA(
        name="Cape Verde", aerial_strength=7.5, pace_rating=8.0, technical_quality=7.0,
        counter_threat=7.5, defensive_organization=7.0, physical_strength=7.5,
        big_game_mentality=6.0, pressing_vulnerability=6.0, pace_vulnerability=6.5,
        aerial_vulnerability=7.0, defensive_line_height=5.0,
        strengths=["Velocidad y físico en bandas (varios jugadores de la Ligue 1)", "Mentalidad de equipo sorpresa", "Buen juego de transición"],
        weaknesses=["Poca experiencia en torneos mundiales", "Vulnerable en balones parados defensivos", "Liga de Cabo Verde: nivel muy inferior"]
    ),
    "Curacao": TeamDNA(
        name="Curacao", aerial_strength=6.5, pace_rating=7.5, technical_quality=7.0,
        counter_threat=7.5, defensive_organization=6.0, physical_strength=6.5,
        big_game_mentality=4.5, pressing_vulnerability=7.0, pace_vulnerability=7.5,
        aerial_vulnerability=7.5, defensive_line_height=5.0,
        strengths=["Jugadores holandeses de origen: técnica superior a la región CONCACAF", "Velocidad en transiciones", "Sorpresa potencial del torneo"],
        weaknesses=["Primera Copa del Mundo: inexperiencia total en esta presión", "Físicamente inferiores a los grandes", "Vulnerables a todo: presión, velocidad, físico, aéreo"]
    ),
    "Haiti": TeamDNA(
        name="Haiti", aerial_strength=6.5, pace_rating=7.0, technical_quality=6.0,
        counter_threat=7.0, defensive_organization=6.5, physical_strength=6.5,
        big_game_mentality=4.5, pressing_vulnerability=7.5, pace_vulnerability=7.5,
        aerial_vulnerability=7.0, defensive_line_height=4.0,
        strengths=["Físico y determinación individual", "Rápido en transiciones cuando recupera el balón", "Jugadores con experiencia en MLS y Europa menor"],
        weaknesses=["Nivel técnico muy inferior al torneo", "Muy vulnerable a presión alta organizada", "Poca experiencia en este nivel de competición"]
    ),
    "New Zealand": TeamDNA(
        name="New Zealand", aerial_strength=7.0, pace_rating=6.5, technical_quality=6.5,
        counter_threat=6.5, defensive_organization=6.5, physical_strength=7.0,
        big_game_mentality=5.0, pressing_vulnerability=7.0, pace_vulnerability=7.0,
        aerial_vulnerability=7.0, defensive_line_height=5.0,
        strengths=["Chris Wood: delantero físico de clase Bundesliga", "Mentalidad valiente ante rivales superiores", "Organización defensiva compacta"],
        weaknesses=["Nivel de la liga neozelandesa: inferior global", "Poca experiencia mundialista reciente", "Vulnerable a pressing, velocidad y juego aéreo ofensivo rival"]
    ),
}


def get_team_dna(team_name: str) -> Optional[TeamDNA]:
    """Return TeamDNA for a team. Tries exact name, then partial match."""
    if team_name in TEAM_DNA:
        return TEAM_DNA[team_name]
    # Partial match
    for name, dna in TEAM_DNA.items():
        if team_name.lower() in name.lower() or name.lower() in team_name.lower():
            return dna
    return None


def compute_matchup_factors(
    attacker_dna: TeamDNA,
    defender_dna: TeamDNA,
) -> dict[str, float]:
    """
    Compute specific matchup advantages/disadvantages for the attacker vs. defender.

    Returns dict of factor_name -> value where:
      positive = attacker benefits
      negative = attacker is disadvantaged
    """
    factors = {}

    # 1. Pace mismatch: attacker speed vs. defender pace vulnerability
    # Amplified if defender has high defensive line (more space to exploit)
    pace_gap = attacker_dna.pace_rating - (10 - defender_dna.pace_vulnerability)
    line_amplifier = 1.0 + (defender_dna.defensive_line_height - 5) * 0.08
    factors["pace_mismatch"] = round(pace_gap * line_amplifier / 20, 4)

    # 2. Aerial dominance: attacker aerial vs. defender aerial vulnerability
    aerial_gap = attacker_dna.aerial_strength - (10 - defender_dna.aerial_vulnerability)
    factors["aerial_dominance"] = round(aerial_gap / 20, 4)

    # 3. Pressing suffocation: defender's pressing vs. attacker's press vulnerability
    pressing_impact = (defender_dna.physical_strength * 0.3 +
                       defender_dna.defensive_organization * 0.3 +
                       (10 - attacker_dna.pressing_vulnerability) * 0.4) / 10
    factors["pressing_resistance"] = round((pressing_impact - 0.5) * 0.4, 4)

    # 4. Counter-threat: attacker counter ability vs. defender line height
    counter_factor = attacker_dna.counter_threat * (defender_dna.defensive_line_height / 10)
    factors["counter_threat_bonus"] = round((counter_factor - 5) / 20, 4)

    # 5. Physical dominance: attacker physical vs. defender technical quality
    # Strong physical team vs. small technical team = advantage
    physical_gap = attacker_dna.physical_strength - (10 - defender_dna.pressing_vulnerability * 0.5)
    factors["physical_dominance"] = round(physical_gap / 30, 4)

    # 6. Technical quality vs. defensive organization
    # Technical team breaks down organized defense better
    tech_vs_def = attacker_dna.technical_quality - defender_dna.defensive_organization
    factors["technical_advantage"] = round(tech_vs_def / 20, 4)

    # 7. Big game mentality differential (only matters in tight games)
    mentality_gap = attacker_dna.big_game_mentality - defender_dna.big_game_mentality
    factors["mentality_edge"] = round(mentality_gap / 40, 4)

    return factors


def matchup_xg_factor(
    attacker_dna: TeamDNA,
    defender_dna: TeamDNA,
) -> float:
    """
    Compute overall xG multiplier for the attacker against this specific defender.

    Returns float in [0.78, 1.30].
    Factors:
      - Pace mismatch (±10% max)
      - Aerial dominance (±8% max)
      - Pressing resistance (±6% max)
      - Counter-threat (±5% max, only positive)
      - Physical dominance (±5% max)
      - Technical advantage (±5% max)
      - Mentality edge (±3% max)
    """
    factors = compute_matchup_factors(attacker_dna, defender_dna)

    multiplier = 1.0

    # Pace: strongest factor (±10%)
    multiplier += factors["pace_mismatch"] * 0.20

    # Aerial: (±8%)
    multiplier += factors["aerial_dominance"] * 0.16

    # Pressing resistance: (±6%)
    multiplier += factors["pressing_resistance"] * 0.12

    # Counter threat: only boost when positive (±5%)
    multiplier += max(0, factors["counter_threat_bonus"]) * 0.10

    # Physical dominance (±4%)
    multiplier += factors["physical_dominance"] * 0.08

    # Technical advantage (±4%)
    multiplier += factors["technical_advantage"] * 0.08

    # Mentality (±3%)
    multiplier += factors["mentality_edge"] * 0.06

    return round(max(0.78, min(1.30, multiplier)), 4)


def format_matchup_analysis(
    attacker_name: str,
    defender_name: str,
    attacker_dna: Optional[TeamDNA] = None,
    defender_dna: Optional[TeamDNA] = None,
) -> str:
    """
    Return human-readable matchup analysis string.
    """
    att = attacker_dna or get_team_dna(attacker_name)
    dfn = defender_dna or get_team_dna(defender_name)

    if not att or not dfn:
        return f"  Sin datos DNA para {attacker_name} o {defender_name}"

    factors = compute_matchup_factors(att, dfn)
    xg_mult = matchup_xg_factor(att, dfn)

    lines = [f"\n  Análisis de identidad: {attacker_name} vs. defensa {defender_name}"]
    lines.append(f"  xG multiplier: {xg_mult:.3f} ({'↑ ventaja' if xg_mult > 1.02 else '↓ desventaja' if xg_mult < 0.98 else '~ equilibrado'})")

    # Report significant factors only (abs > 0.02)
    sorted_factors = sorted(factors.items(), key=lambda x: abs(x[1]), reverse=True)
    significant = [(k, v) for k, v in sorted_factors if abs(v) > 0.015]

    if significant:
        lines.append("  Factores clave:")
        labels = {
            "pace_mismatch": "Velocidad",
            "aerial_dominance": "Juego aéreo",
            "pressing_resistance": "Resistencia al pressing",
            "counter_threat_bonus": "Amenaza de contragolpe",
            "physical_dominance": "Dominio físico",
            "technical_advantage": "Superioridad técnica",
            "mentality_edge": "Mentalidad en grandes partidos",
        }
        for k, v in significant[:4]:
            sign = "✚" if v > 0 else "✖"
            label = labels.get(k, k)
            lines.append(f"    {sign} {label}: {v:+.3f}")

    if att.strengths:
        lines.append(f"  Fortalezas {attacker_name}: {', '.join(att.strengths[:2])}")
    if dfn.weaknesses:
        lines.append(f"  Debilidades {defender_name}: {', '.join(dfn.weaknesses[:2])}")

    return "\n".join(lines)
