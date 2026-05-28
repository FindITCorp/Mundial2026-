"""
team_scout.py — Narrative scouting reports and player identity analysis for WC2026.

Provides structured scouting summaries per team: tactical system, key players,
historical patterns, and context for predictions.
"""
from __future__ import annotations
from typing import Optional
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"


SCOUT_REPORTS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    # CONMEBOL
    # -------------------------------------------------------------------------
    "Argentina": {
        "system": "4-3-3 → 4-4-2 defensivo (Scaloni)",
        "identity": "El mejor equipo del mundo en 2022-2024, organización defensiva perfecta + Messi",
        "key_players": ["Lionel Messi", "Julián Álvarez", "Rodrigo De Paul"],
        "strengths": [
            "Bloque defensivo impenetrable",
            "Messi genera diferencia en cualquier momento",
            "Mentalidad campeona probada",
        ],
        "weaknesses": [
            "Post-Messi dependencia absoluta",
            "CBs no son los más rápidos",
            "Puede sufrir vs presión muy alta",
        ],
        "historical_pattern": "Llega fuerte, nunca fue eliminado en grupos desde 2002",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos que presionan muy alto y tienen velocidad extrema (Austria-style)",
    },
    "Brazil": {
        "system": "4-2-3-1 / 4-3-3 ofensivo",
        "identity": "Vinicius Jr + Rodrygo como bandas veloces con Rodrygo como 9 falso",
        "key_players": ["Vinicius Jr", "Rodrygo", "Lucas Paquetá"],
        "strengths": [
            "Velocidad en bandas devastadora",
            "Profundidad de plantel excepcional",
            "Creatividad técnica individual",
        ],
        "weaknesses": [
            "Fragilidad defensiva en transiciones",
            "Inconsistencia en partidos sin generar",
            "Lesiones frecuentes de figuras clave",
        ],
        "historical_pattern": "Favorito constante pero no gana desde 2002",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos físicos que ganan duelos y neutralizan bandas",
    },
    "Colombia": {
        "system": "4-2-3-1 / 4-3-3 (Nestor Lorenzo)",
        "identity": "Campeón Copa América 2024, generación dorada con Luis Díaz y James",
        "key_players": ["Luis Díaz", "James Rodríguez", "Richard Ríos"],
        "strengths": [
            "Velocidad de transición con Luis Díaz",
            "Creatividad de James desde mediocampo",
            "Presión organizada que recupera alto",
        ],
        "weaknesses": [
            "Gestión emocional en momentos adversos",
            "Defensa puede desorganizarse",
            "Dependencia de James para el juego",
        ],
        "historical_pattern": "Buena fase de grupos, tiende a caer en cuartos",
        "threat_level": "Media-Alta",
        "key_matchup_note": "Defensas compactas que anulan el espacio para Díaz",
    },
    "Uruguay": {
        "system": "3-3-1-3 (Bielsa)",
        "identity": "Físico extremo y pressing intenso con Bielsa, Arrascaeta como motor",
        "key_players": ["Federico Valverde", "Rodrigo Bentancur", "Darwin Núñez"],
        "strengths": [
            "Sistema Bielsa agotador físicamente para rivales",
            "Valverde: capacidad de trabajo y gol desde mediocampo",
            "Garra charrúa y mentalidad histórica",
        ],
        "weaknesses": [
            "Muy demandante físicamente: riesgo de bajas por lesión",
            "Velocidad defensiva limitada",
            "Sin Suárez/Cavani la amenaza de gol cae",
        ],
        "historical_pattern": "Siempre competitivo, 4to puesto 2010",
        "threat_level": "Media",
        "key_matchup_note": "Equipos veloces que explotan el espacio en su línea alta de pressing",
    },
    "Ecuador": {
        "system": "4-4-2 / 5-4-1 defensivo",
        "identity": "Físico y aéreo con Valencia como 9 referente, poco técnico pero muy intenso",
        "key_players": ["Enner Valencia", "Moisés Caicedo", "Piero Hincapié"],
        "strengths": [
            "Caicedo: mejor mediocampista defensivo joven del torneo",
            "Valencia como referencia aérea y de presión",
            "Solidez en balones divididos",
        ],
        "weaknesses": [
            "Poca velocidad en banda y técnica limitada",
            "Muy vulnerable a equipos veloces y técnicos",
            "Sin Valencia el juego ofensivo sufre mucho",
        ],
        "historical_pattern": "Primer equipo del torneo en WC2022, luego cayó en grupos",
        "threat_level": "Media",
        "key_matchup_note": "Equipos técnicos rápidos que los presionan alto",
    },
    "Paraguay": {
        "system": "4-4-2 físico / 5-3-2 defensivo",
        "identity": "Físico extremo, juego directo y defensa recia",
        "key_players": ["Julio Enciso", "Miguel Almirón", "Gustavo Gómez"],
        "strengths": [
            "Almirón: energía y llegada desde mediocampo",
            "Físico dominante en duelos",
            "Disciplina táctica colectiva",
        ],
        "weaknesses": [
            "Poca velocidad en transición",
            "Técnica limitada bajo presión alta",
            "Generación de juego escasa",
        ],
        "historical_pattern": "Llega al mundo pero rara vez pasa de grupos",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos técnicos y veloces que los exponen",
    },
    "Bolivia": {
        "system": "4-4-2 defensivo",
        "identity": "Depende de la altitud de La Paz para resultados, nivel bajo fuera de casa",
        "key_players": ["Marcelo Moreno", "Henry Vaca", "Jaime Arrascaeta"],
        "strengths": [
            "Ventaja de altitud extrema en La Paz (3,600m)",
            "Mentalidad guerrera local",
            "Físico adaptado a la altura",
        ],
        "weaknesses": [
            "Nivel técnico muy bajo fuera de La Paz",
            "Velocidad muy limitada",
            "Poca experiencia mundialista reciente",
        ],
        "historical_pattern": "Rara vez pasa de la fase de grupos, sin altitud son el peor equipo de CONMEBOL",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo técnico fuera de Bolivia",
    },
    "Chile": {
        "system": "4-3-3 / 4-2-3-1 pressing",
        "identity": "Generación post-dorada en reconstrucción, sombra del equipo bicampeón Copa América 2015-2016",
        "key_players": ["Alexis Sánchez", "Arturo Vidal", "Charles Aránguiz"],
        "strengths": [
            "Experiencia de la generación dorada: Vidal, Sánchez, Medel",
            "Presión organizada histórica (Bielsa-style heredado)",
            "Intensidad y garra como señas de identidad",
        ],
        "weaknesses": [
            "Generación mayor con piernas agotadas",
            "Reconstrucción aún en proceso: faltan jugadores jóvenes de nivel",
            "Velocidad defensiva muy limitada",
        ],
        "historical_pattern": "WC2010: semis. Campeones Copa América 2015 y 2016. Ahora en declive.",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos veloces que explotan las espaldas de su defensa envejecida",
    },
    # -------------------------------------------------------------------------
    # CONCACAF
    # -------------------------------------------------------------------------
    "USA": {
        "system": "4-3-3 pressing (Pochettino)",
        "identity": "Generación joven de primera calidad con jugadores en Premier League, Bundesliga",
        "key_players": ["Christian Pulisic", "Gio Reyna", "Yunus Musah"],
        "strengths": [
            "Atletismo y velocidad extrema",
            "Pressing organizado de Pochettino",
            "Juega en casa (WC2026 en USA)",
        ],
        "weaknesses": [
            "Poca experiencia en presión de eliminatorias mundiales",
            "Gestión de partido posicional: inferior a élite",
            "Puede desmoronarse bajo presión de gran torneo",
        ],
        "historical_pattern": "Mejor actuación: cuartos WC2002",
        "threat_level": "Media",
        "key_matchup_note": "Equipos técnicos de posesión que los hacen correr y se adaptan a su press",
    },
    "Mexico": {
        "system": "4-3-3 / 4-2-3-1 (Aguirre)",
        "identity": "Ventaja de altitud en Azteca, juego de contraataque y local WC2026",
        "key_players": ["Hirving Lozano", "Edson Álvarez", "Raúl Jiménez"],
        "strengths": [
            "Azteca: fortín con altitud 2240m",
            "Lozano: velocidad y desequilibrio en banda",
            "Álvarez: liderazgo en mediocampo",
        ],
        "weaknesses": [
            "Maldición del quinto partido: 0 cuartos de final desde 1986",
            "Sin espacio para contragolpear sufre",
            "Nivel de Liga MX vs Europa: brecha real",
        ],
        "historical_pattern": "Siempre pasa grupos, siempre cae en octavos",
        "threat_level": "Media",
        "key_matchup_note": "Equipos que anulan el contraataque y presionan alto desde el inicio",
    },
    "Canada": {
        "system": "3-4-3 / 4-3-3 pressing (Marsch)",
        "identity": "Primera generación dorada histórica con Davies, David, Buchanan",
        "key_players": ["Alphonso Davies", "Jonathan David", "Cyle Larin"],
        "strengths": [
            "Davies: el mejor lateral izquierdo del torneo",
            "David: uno de los mejores delanteros",
            "Pressing agresivo de alta intensidad",
        ],
        "weaknesses": [
            "Primera generación: presión del debut puede pesar",
            "Organización defensiva en transición negativa",
            "Defensa central puede sufrir vs. físicos",
        ],
        "historical_pattern": "Primera World Cup desde 1986",
        "threat_level": "Media",
        "key_matchup_note": "Equipos técnicos pacientes que no se desordenan ante el pressing canadiense",
    },
    "Panama": {
        "system": "4-4-2 / 5-4-1 defensivo",
        "identity": "Bloque bajo compacto, físico, poco técnico, difícil de batir",
        "key_players": ["Gabriel Torres", "Adalberto Carrasquilla", "Harold Cummings"],
        "strengths": [
            "Organización defensiva disciplinada",
            "Mentalidad de equipo que no se rinde",
            "Difícil de batir para equipos que no tienen paciencia",
        ],
        "weaknesses": [
            "Muy vulnerable a velocidad extrema en banda (Francia, Brasil)",
            "Técnica bajo presión alta: liga doméstica de nivel muy bajo",
            "Poca amenaza ofensiva propia",
        ],
        "historical_pattern": "Segunda WC (2018 debut), cayó en todos los grupos",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo de calidad media con velocidad en bandas",
    },
    "Curacao": {
        "system": "4-3-3",
        "identity": "Jugadores de herencia holandesa con calidad superior a CONCACAF típico",
        "key_players": ["Cuco Martina", "Leandro Bacuna", "Jurickson Profar"],
        "strengths": [
            "Herencia holandesa: técnica superior a la región CONCACAF",
            "Velocidad en transiciones ofensivas",
            "Sorpresa potencial del torneo",
        ],
        "weaknesses": [
            "Primera Copa del Mundo: inexperiencia total en esta presión",
            "Físicamente inferiores a los grandes",
            "Vulnerables a todo: presión, velocidad, físico, aéreo",
        ],
        "historical_pattern": "Primera participación en Copa del Mundo",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo grande de Europa o América",
    },
    "Haiti": {
        "system": "4-4-2 defensivo",
        "identity": "Físico y determinación como únicos activos, nivel muy bajo globalmente",
        "key_players": ["Duckens Nazon", "Frantzdy Pierrot", "Wilde-Donald Guerrier"],
        "strengths": [
            "Físico y determinación individual",
            "Rápido en transiciones cuando recupera el balón",
            "Jugadores con experiencia en MLS y Europa menor",
        ],
        "weaknesses": [
            "Nivel técnico muy inferior al torneo",
            "Muy vulnerable a presión alta organizada",
            "Poca experiencia en este nivel de competición",
        ],
        "historical_pattern": "Primera participación desde 1974",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo con presión organizada y técnica básica",
    },
    "Costa Rica": {
        "system": "5-4-1 defensivo (Suárez)",
        "identity": "Bloque bajo histórico, la leyenda de WC2014 es lejana",
        "key_players": ["Keylor Navas", "Bryan Ruiz", "Joel Campbell"],
        "strengths": [
            "Navas: portero de nivel Real Madrid histórico",
            "Organización defensiva en bloque bajo",
            "Experiencia en grandes torneos (WC2014: cuartos)",
        ],
        "weaknesses": [
            "Generación mayor muy envejecida",
            "Poca creatividad ofensiva propia",
            "Velocidad defensiva muy limitada",
        ],
        "historical_pattern": "WC2014: cuartos (sorpresa histórica). Desde entonces declive total.",
        "threat_level": "Baja",
        "key_matchup_note": "Equipos veloces con jugadores jóvenes que superan la experiencia con físico",
    },
    # -------------------------------------------------------------------------
    # UEFA
    # -------------------------------------------------------------------------
    "France": {
        "system": "4-3-3 / 4-2-3-1 (Deschamps)",
        "identity": "Velocidad francesa con Mbappé como diferencial absoluto, plantilla más profunda del torneo",
        "key_players": ["Kylian Mbappé", "Antoine Griezmann", "Marcus Thuram"],
        "strengths": [
            "Mbappé: el jugador más rápido y desequilibrante del mundo",
            "Profundidad: cada suplente sería titular en otro equipo",
            "Mentalidad de campeón, probada en 2018",
        ],
        "weaknesses": [
            "Cuando Mbappé no aparece, el equipo baja nivel",
            "Puede ser sorprendido por presión alta organizada",
            "Deschamps puede ser demasiado conservador en finales",
        ],
        "historical_pattern": "Campeón WC2018, finalista WC2022, siempre llega lejos",
        "threat_level": "Alta",
        "key_matchup_note": "Presión alta muy organizada tipo Austria/Rangnick que les hace incomodarse",
    },
    "Spain": {
        "system": "4-3-3 posesión y presión (De la Fuente)",
        "identity": "Tiki-taka evolucionado: presión alta + posesión + jóvenes como Yamal/Pedri",
        "key_players": ["Pedri", "Lamine Yamal", "Rodri"],
        "strengths": [
            "Rodri: el mejor centrocampista del mundo",
            "Yamal: 17 años con nivel de campeón EURO",
            "Posesión y presión dominan el partido",
        ],
        "weaknesses": [
            "Línea muy alta: un contraataque directo puede doler",
            "Poca presencia aérea en corners propios",
            "Dependencia de Rodri en mediocampo",
        ],
        "historical_pattern": "WC2010: campeones. EURO 2024: campeones.",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos veloces que contraatacan y tienen delantero punta efectivo",
    },
    "England": {
        "system": "4-3-3 / 4-2-3-1 (Southgate→próximo)",
        "identity": "Generación dorada con Bellingham/Saka/Kane, candidato real por primera vez desde 1966",
        "key_players": ["Harry Kane", "Jude Bellingham", "Bukayo Saka"],
        "strengths": [
            "Kane: el mejor delantero en el aire del torneo",
            "Bellingham: motor, gol y carisma",
            "Saka: velocidad y desborde por derecha",
        ],
        "weaknesses": [
            "Historial de fracasos en penales y torneos",
            "Puede volverse predecible en ataque directo",
            "Defensa sufre vs. equipos con mucha velocidad en banda",
        ],
        "historical_pattern": "Últimos tres torneos: final EURO2021, semis WC2018",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos con CBs veloces que niegan el juego aéreo de Kane",
    },
    "Germany": {
        "system": "4-2-3-1 pressing muy alto (Nagelsmann)",
        "identity": "Renacimiento con Nagelsmann: pressing extremo, línea altísima, Müller ya retirado",
        "key_players": ["Jamal Musiala", "Florian Wirtz", "Antonio Rüdiger"],
        "strengths": [
            "Musiala+Wirtz: generación más talentosa del mundo con 21-22 años",
            "Pressing Nagelsmann: recuperaciones altas constantes",
            "Mentalidad histórica alemana en torneos",
        ],
        "weaknesses": [
            "Línea altísima: los contraataques pueden destruirlos",
            "Reconstrucción aún en proceso",
            "Portería sin figura histórica (ter Stegen lesiones)",
        ],
        "historical_pattern": "WC2018/2022: eliminado en grupos. Reconstrucción en marcha",
        "threat_level": "Media-Alta",
        "key_matchup_note": "Equipos con velocidad extrema que se adaptan a contraatacar su línea",
    },
    "Netherlands": {
        "system": "4-3-3 pressing (Koeman)",
        "identity": "Van Dijk como pilar defensivo, velocidad en bandas con Gakpo/Depay",
        "key_players": ["Virgil van Dijk", "Cody Gakpo", "Xavi Simons"],
        "strengths": [
            "Van Dijk: mejor defensa central del torneo",
            "Pressing organizado de alta intensidad",
            "Velocidad y creatividad en bandas",
        ],
        "weaknesses": [
            "Históricamente implosionan en partidos decisivos",
            "Dependencia de Van Dijk en la retaguardia",
            "Sin Bergwijn la banda derecha puede sufrir",
        ],
        "historical_pattern": "WC2022: semis. WC2010: finalistas.",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos técnicos de posesión que los hacen correr sin balón",
    },
    "Portugal": {
        "system": "4-2-3-1 / 4-3-3 (Roberto Martínez)",
        "identity": "Post-Ronaldo con Bruno Fernandes como cerebro, Leao como velocidad",
        "key_players": ["Bruno Fernandes", "Rafael Leão", "Rúben Dias"],
        "strengths": [
            "Bruno: generador de juego y gol desde mediocampo",
            "Leão: uno de los más veloces del torneo",
            "Días: central de nivel absoluto",
        ],
        "weaknesses": [
            "Transición post-Ronaldo aún en proceso",
            "Portero bajo nivel histórico",
            "Pressing medio: puede sufrir vs. equipos muy físicos",
        ],
        "historical_pattern": "WC2022: cuartos. EURO 2016: campeones.",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos físicos que ganan el duelo de mediocampo y cierran a Bruno",
    },
    "Belgium": {
        "system": "4-3-3 / 3-4-3 (Tedesco)",
        "identity": "Generación dorada terminal: De Bruyne, Lukaku en el ocaso",
        "key_players": ["Kevin De Bruyne", "Romelu Lukaku", "Axel Witsel"],
        "strengths": [
            "De Bruyne: todavía el mejor creador del torneo",
            "Lukaku: referencia física y de área imponente",
            "Profundidad de plantel histórica",
        ],
        "weaknesses": [
            "Generación mayor: piernas que se agotan",
            "Defensa puede ser lenta lateralmente",
            "Historial de fracaso en grandes momentos",
        ],
        "historical_pattern": "WC2018: 3er lugar. Después siempre decepciona.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos veloces que explotan la defensa lenta belga en transiciones",
    },
    "Croatia": {
        "system": "4-2-3-1 posesión (Zlatko Dalic)",
        "identity": "Modric lidera a los balcánicos en su último mundial probable",
        "key_players": ["Luka Modrić", "Mateo Kovačić", "Andrej Kramarić"],
        "strengths": [
            "Modrić: el cerebro táctico más experimentado del torneo",
            "Kovačić: trabajo, gol y presencia en mediocampo",
            "Mentalidad de equipo en eliminatorias: los mejores",
        ],
        "weaknesses": [
            "Modrić ya tiene 40 años en 2026",
            "Velocidad defensiva muy limitada",
            "Sin ritmo alto de juego el equipo pierde efectividad",
        ],
        "historical_pattern": "WC2018: finalistas. WC2022: semis. Siempre llegan lejos.",
        "threat_level": "Media-Alta",
        "key_matchup_note": "Equipos con velocidad extrema que atacan sus espaldas",
    },
    "Austria": {
        "system": "4-2-3-1 pressing extremo (Rangnick)",
        "identity": "El pressing más alto e intenso del torneo, línea defensiva casi en campo contrario",
        "key_players": ["Marcel Sabitzer", "Konrad Laimer", "David Alaba"],
        "strengths": [
            "Pressing récord: recuperaciones a 5m del arco rival",
            "Línea de defensa altísima asfixiante",
            "Laimer+Sabitzer: motor de pressing implacable",
        ],
        "weaknesses": [
            "Máximo riesgo de contraataque: Francia/Brasil/Colombia pueden destrozarlos",
            "Alaba lesiones frecuentes a su edad",
            "Poca experiencia en fases eliminatorias mundiales",
        ],
        "historical_pattern": "WC: primera vez desde 1998.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos con velocidad extrema (Francia, Brasil) que explotan la espalda",
    },
    "Switzerland": {
        "system": "4-3-3 / 3-4-3 compacto (Yakin)",
        "identity": "Equilibrio y solidez: difícil de batir, siempre competitivo",
        "key_players": ["Granit Xhaka", "Ricardo Rodríguez", "Breel Embolo"],
        "strengths": [
            "Xhaka: liderazgo, experiencia y lectura táctica",
            "Organización defensiva sin fisuras",
            "Especialistas en balón parado: 38% goles de set pieces",
        ],
        "weaknesses": [
            "Poca creatividad individual para generar juego fluido",
            "Limitada potencia ofensiva sin Shaqiri",
            "Generación de juego lenta vs. pressing alto",
        ],
        "historical_pattern": "Últimas 3 WC: octavos o cuartos, nunca llegan más",
        "threat_level": "Media",
        "key_matchup_note": "Equipos muy técnicos de posesión que los hacen correr y les ganan el mediocampo",
    },
    "Morocco": {
        "system": "4-3-3 / 5-4-1 (Regragui)",
        "identity": "El equipo más sorprendente de WC2022: semis, defensiva perfecta + contraataque",
        "key_players": ["Achraf Hakimi", "Yassine Bounou", "Sofiane Boufal"],
        "strengths": [
            "Hakimi: mejor lateral del mundo en ataque",
            "Bounou: portero con reflejos de élite",
            "Contraataque desde bloque bajo: los mejores del torneo",
        ],
        "weaknesses": [
            "Set pieces DEFENSIVOS: vulnerables (44% de sus goles encajados)",
            "Sin Hakimi proyectado el equipo pierde su principal amenaza",
            "Construcción de juego escasa cuando no contragolpean",
        ],
        "historical_pattern": "WC2022: semis (histórico). WC2026: candidatos reales.",
        "threat_level": "Alta",
        "key_matchup_note": "Equipos con especialistas en balón parado y juego aéreo",
    },
    "Serbia": {
        "system": "3-4-3 / 4-2-3-1",
        "identity": "Dusan Vlahovic como 9 clásico, potencial físico pero inconsistente",
        "key_players": ["Dušan Vlahović", "Sergej Milinković-Savić", "Aleksandar Mitrović"],
        "strengths": [
            "Vlahovic: referencia aérea y gol de primer nivel",
            "Milinković-Savić: calidad y llegada desde mediocampo",
            "Físico e intensidad balcánica",
        ],
        "weaknesses": [
            "Inconsistencia táctica entre partidos",
            "Vulnerabilidad defensiva lateral",
            "Pocas WC recientes: poca experiencia",
        ],
        "historical_pattern": "Históricamente irregular",
        "threat_level": "Media",
        "key_matchup_note": "Presión alta organizada que gana el mediocampo",
    },
    "Scotland": {
        "system": "4-3-3 / 4-2-3-1 pressing (Clarke)",
        "identity": "Robertson y Tierney en bandas, físico e intensidad como identidad",
        "key_players": ["Andrew Robertson", "Scott McTominay", "Che Adams"],
        "strengths": [
            "Robertson: el mejor lateral del torneo en proyección ofensiva",
            "McTominay: gol, carisma y trabajo",
            "Pressing físico que genera recuperaciones",
        ],
        "weaknesses": [
            "Primer Mundial desde 1998: presión histórica",
            "Ofensiva limitada más allá de Robertson",
            "Vulnerables a velocidad por banda derecha propia",
        ],
        "historical_pattern": "Primera WC desde 1998",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos veloces por la derecha escocesa",
    },
    "Czechia": {
        "system": "4-2-3-1 / 4-3-3",
        "identity": "Schick como 9 referencia, Kuchta como opción física",
        "key_players": ["Patrik Schick", "Vladimír Coufal", "Tomáš Souček"],
        "strengths": [
            "Schick: goleador de nivel Bundesliga de primer nivel",
            "Souček: llegada y gol desde mediocampo",
            "Disciplina y organización colectiva",
        ],
        "weaknesses": [
            "Poca creatividad en ataque posicional",
            "Sin Schick el equipo pierde todo su gol",
            "Mediocampo limitado vs. élite europea",
        ],
        "historical_pattern": "EURO2020: semis. WC: irregulares",
        "threat_level": "Media",
        "key_matchup_note": "Pressing muy alto que niega el balón a Schick",
    },
    "Turkey": {
        "system": "4-2-3-1 / 4-3-3 (Montella)",
        "identity": "Çalhanoğlu como eje total, Yilmaz como referencia ofensiva",
        "key_players": ["Hakan Çalhanoğlu", "Kerem Aktürkoğlu", "Merih Demiral"],
        "strengths": [
            "Çalhanoğlu: el mejor mediocampista del torneo técnicamente",
            "Aktürkoğlu: velocidad y desequilibrio",
            "Historia de rendimientos sorprendentes en torneos",
        ],
        "weaknesses": [
            "Inconsistencia táctica y mental",
            "Dependen de Çalhanoğlu al 80%",
            "Defensa puede ser explotada en transiciones",
        ],
        "historical_pattern": "WC2002: 3er lugar. Después irregular.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos que neutralizan a Çalhanoğlu con un volante de marca",
    },
    "Norway": {
        "system": "4-3-3 pressing (Ståle Solbakken)",
        "identity": "Haaland como el delantero más peligroso del torneo, generación joven con calidad",
        "key_players": ["Erling Haaland", "Martin Ødegaard", "Sander Berge"],
        "strengths": [
            "Haaland: el goleador más letal del planeta (194 cm, explosivo)",
            "Ødegaard: creatividad y visión de juego excepcional",
            "Pressing colectivo bien organizado",
        ],
        "weaknesses": [
            "Primera WC desde 1998: inexperiencia en este nivel",
            "Defensa central: lenta y vulnerable al espacio",
            "Dependencia extrema de Haaland",
        ],
        "historical_pattern": "Primera participación en 28 años",
        "threat_level": "Media-Alta",
        "key_matchup_note": "Defensas veloces que niegan el espacio a Haaland",
    },
    "Sweden": {
        "system": "4-3-3 / 4-4-2 físico",
        "identity": "Victor Gyökeres como nuevo gran 9, generación de relevo post-Ibrahimovic",
        "key_players": ["Viktor Gyökeres", "Alexander Isak", "Dejan Kulusevski"],
        "strengths": [
            "Gyökeres: el goleador más en forma de Europa 2024-25",
            "Isak: velocidad y elegancia técnica en Newcastle",
            "Físico nórdico con juego aéreo dominante",
        ],
        "weaknesses": [
            "Velocidad defensiva limitada en centrales",
            "Sin Ibrahimovic la identidad está cambiando",
            "Vulnerable a equipos veloces que atacan las espaldas",
        ],
        "historical_pattern": "WC2018: semis. Sólida tradición reciente.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos veloces por banda que explotan los espacios",
    },
    "Bosnia and Herzegovina": {
        "system": "4-3-3 / 3-5-2 físico",
        "identity": "Džeko como gran 9 histórico, primera WC en el futuro",
        "key_players": ["Edin Džeko", "Miralem Pjanić", "Ermedin Demirović"],
        "strengths": [
            "Džeko: historial goleador impresionante en WC/EURO",
            "Físico e intensidad balcánica",
            "Pjanić: creatividad y visión en mediocampo",
        ],
        "weaknesses": [
            "Velocidad defensiva muy baja",
            "Sin Džeko el equipo tiene muy poco gol",
            "Poca experiencia mundialista",
        ],
        "historical_pattern": "WC2014 fue su única actuación histórica",
        "threat_level": "Media",
        "key_matchup_note": "Equipos veloces que atacan las espaldas de su lenta defensa",
    },
    # -------------------------------------------------------------------------
    # CAF (Africa)
    # -------------------------------------------------------------------------
    "Senegal": {
        "system": "4-3-3 / 4-2-3-1 (Cissé)",
        "identity": "Mejor equipo africano: físico, velocidad, campeones AFCON 2022",
        "key_players": ["Sadio Mané", "Kalidou Koulibaly", "Idrissa Gueye"],
        "strengths": [
            "Mané: velocidad, gol y determinación de clase mundial",
            "Koulibaly: el mejor defensa africano",
            "Físico y atletismo superiores",
        ],
        "weaknesses": [
            "Juego posicional técnico limitado",
            "Vulnerables en set pieces defensivos",
            "Irregularidad cuando el rival niega el espacio a Mané",
        ],
        "historical_pattern": "AFCON 2022: campeones. WC2002: semis históricos.",
        "threat_level": "Media-Alta",
        "key_matchup_note": "Defensas muy organizadas que anulan el espacio a Mané y presionan",
    },
    "Ivory Coast": {
        "system": "4-3-3 / 4-2-3-1 (Peseiro)",
        "identity": "Velocidad africana + calidad técnica, AFCON 2023 campeones",
        "key_players": ["Sébastien Haller", "Nicolas Pépé", "Franck Kessié"],
        "strengths": [
            "Velocidad en banda: devastadora",
            "Kessié: motor físico de mediocampo",
            "Campeones AFCON 2023",
        ],
        "weaknesses": [
            "Organización defensiva frágil",
            "Se desordenan cuando van en desventaja",
            "Inconsistencia en la fase de eliminatorias",
        ],
        "historical_pattern": "Siempre con expectativas, pocas veces cumple",
        "threat_level": "Media",
        "key_matchup_note": "Equipos organizados que explotan su desorden defensivo",
    },
    "Egypt": {
        "system": "4-2-3-1 / 4-5-1 defensivo",
        "identity": "Mohamed Salah como único diferencial real",
        "key_players": ["Mohamed Salah", "Mohamed El-Shenawy", "Mostafa Mohamed"],
        "strengths": [
            "Salah: el mejor jugador africano posiblemente de la historia",
            "Organización defensiva sólida",
            "Contraataque con Salah: letal",
        ],
        "weaknesses": [
            "Sin Salah el equipo no genera absolutamente nada",
            "Mediocampo de nivel regional limitado",
            "Físicamente inferior a Europa",
        ],
        "historical_pattern": "Sin Salah WC2018 fue decepcionante",
        "threat_level": "Media",
        "key_matchup_note": "Cualquier equipo que neutralice a Salah individualmente",
    },
    "Ghana": {
        "system": "4-2-3-1 / 4-3-3 ofensivo",
        "identity": "Velocidad y físico, pero inconsistencia táctica",
        "key_players": ["Jordan Ayew", "Mohammed Kudus", "Thomas Partey"],
        "strengths": [
            "Kudus: velocidad y habilidad técnica excepcional",
            "Partey: uno de los mejores mediocampistas del torneo",
            "Historia competitiva en Mundiales (semis WC2010)",
        ],
        "weaknesses": [
            "Organización defensiva frágil",
            "Inconsistencia entre partidos",
            "Puede desmoronarse tras primer gol en contra",
        ],
        "historical_pattern": "WC2010: cuartos histórico. Luego irregular.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos que presionan alto y no les dan tiempo de organizar",
    },
    "Algeria": {
        "system": "4-3-3 / 4-2-3-1 (Petkovic)",
        "identity": "Mahrez como diferencial individual, AFCON 2019 campeones",
        "key_players": ["Riyad Mahrez", "Ismaël Bennacer", "Youcef Atal"],
        "strengths": [
            "Mahrez: velocidad, regate y gol de primer nivel",
            "Bennacer: distribución y recuperación en mediocampo",
            "Transición rápida desde defensa",
        ],
        "weaknesses": [
            "Alta dependencia de Mahrez",
            "Organización defensiva inconsistente",
            "Historial de irregularidad en grandes torneos",
        ],
        "historical_pattern": "WC2014: octavos (sorprendentes)",
        "threat_level": "Media",
        "key_matchup_note": "Defensas veloces que anulan a Mahrez en una mano",
    },
    "Tunisia": {
        "system": "4-3-3 / 5-4-1 defensivo",
        "identity": "Compacidad y resistencia como identidad",
        "key_players": ["Wahbi Khazri", "Dylan Bronn", "Hamza Mathlouthi"],
        "strengths": [
            "Bloque defensivo disciplinado",
            "Mentalidad de equipo que lucha",
            "Resistente ante equipos superiores",
        ],
        "weaknesses": [
            "Poca amenaza ofensiva propia",
            "Técnica muy limitada bajo presión",
            "Sin Khazri el juego pierde todo",
        ],
        "historical_pattern": "Irregular en Mundiales, rara vez es sorpresa",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo técnico y bien organizado",
    },
    "DR Congo": {
        "system": "4-3-3 / 4-2-3-1 ofensivo (Heymans)",
        "identity": "Físico africano extremo + velocidad de los grandes",
        "key_players": ["Yannick Bolasie", "Chancel Mbemba", "Jonathan Bolingi"],
        "strengths": [
            "Físico y velocidad extrema en bandas",
            "Mbemba: central de clase Premier League",
            "Juego de transición explosivo",
        ],
        "weaknesses": [
            "Organización defensiva muy frágil",
            "Poca experiencia en Mundiales",
            "Vulnerables en set pieces defensivos",
        ],
        "historical_pattern": "Nunca han pasado a cuartos de final",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos organizados tácticamente que explotan su desorden defensivo",
    },
    "South Africa": {
        "system": "4-3-3 / 4-4-2 físico",
        "identity": "Físico e intensidad, Ronwen Williams como figura",
        "key_players": ["Percy Tau", "Ronwen Williams", "Themba Zwane"],
        "strengths": [
            "Williams: portero del año de la CAF",
            "Tau: habilidad técnica de primera",
            "Físico e intensidad en duelos",
        ],
        "weaknesses": [
            "Generación de juego técnico limitada",
            "Organización ofensiva escasa",
            "Poca experiencia en Mundiales (desde 2010 anfitriones)",
        ],
        "historical_pattern": "WC2010: anfitriones eliminados en grupos",
        "threat_level": "Baja",
        "key_matchup_note": "Equipos técnicos que les generan muchas ocasiones",
    },
    "Cape Verde": {
        "system": "4-3-3 / 4-4-2 físico (Pedro Leitão)",
        "identity": "Sorpresa del torneo potencial con jugadores de la Ligue 1 francesa",
        "key_players": ["Garry Rodrigues", "Dylan Tavares", "Stopira"],
        "strengths": [
            "Velocidad y técnica en bandas",
            "Mentalidad de sorpresa sin presión",
            "Físico atlético africano",
        ],
        "weaknesses": [
            "Liga de Cabo Verde: nivel muy bajo",
            "Poca experiencia en torneos mundiales",
            "Vulnerables en balones parados defensivos",
        ],
        "historical_pattern": "Primera participación en Mundial",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo grande de Europa o América",
    },
    # -------------------------------------------------------------------------
    # AFC (Asia)
    # -------------------------------------------------------------------------
    "Japan": {
        "system": "4-3-3 / 3-4-3 pressing (Moriyasu)",
        "identity": "WC2022: eliminó a Alemania y España, el mejor equipo asiático de la historia",
        "key_players": ["Takumi Minamino", "Wataru Endō", "Ritsu Doan"],
        "strengths": [
            "Pressing organizado que sorprendió al mundo en WC2022",
            "Disciplina táctica sin precedentes",
            "Velocidad en transiciones ofensivas desde el pressing",
        ],
        "weaknesses": [
            "Poca estatura: devastados por juego aéreo rival",
            "Sin experiencia en cuartos de final mundiales",
            "Físicamente inferior vs. europeos y africanos",
        ],
        "historical_pattern": "WC2022: octavos (maravillosos). Históricamente octavos.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos altos que ganan los duelos aéreos y los superan físicamente",
    },
    "South Korea": {
        "system": "4-3-3 / 4-2-3-1 (Hong Myung-bo)",
        "identity": "Son Heung-min como diferencial, disciplina colectiva",
        "key_players": ["Son Heung-min", "Lee Kang-in", "Kim Min-jae"],
        "strengths": [
            "Son: el mejor jugador asiático del torneo",
            "Kim Min-jae: central de clase Serie A",
            "Velocidad de transición colectiva",
        ],
        "weaknesses": [
            "Depende de Son para generar juego",
            "Poca presencia aérea defensiva",
            "Irregular vs. equipos que marcan a Son",
        ],
        "historical_pattern": "WC2002: semis histórico. Después octavos máximo.",
        "threat_level": "Media",
        "key_matchup_note": "Equipos que marcan a Son individualmente con físico",
    },
    "Australia": {
        "system": "4-3-3 / 4-2-3-1 (Arnold)",
        "identity": "Físico australiano + Matt Ryan como portero Premier League",
        "key_players": ["Mat Ryan", "Mathew Leckie", "Martin Boyle"],
        "strengths": [
            "Ryan: portero de clase Premier League",
            "Físico e intensidad",
            "Leckie: velocidad y llegada",
        ],
        "weaknesses": [
            "Técnica limitada vs. élite",
            "Organización ofensiva escasa",
            "Nivel A-League inferior al global",
        ],
        "historical_pattern": "WC2022: octavos (sorpresa). WC2006: octavos.",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos técnicos de posesión que los dominan",
    },
    "Saudi Arabia": {
        "system": "4-2-3-1 / 4-3-3 (Blanc)",
        "identity": "Sorpresa táctica del torneo (ganó a Argentina WC2022)",
        "key_players": ["Salem Al-Dawsari", "Firas Al-Buraikan", "Mohammed Al-Owais"],
        "strengths": [
            "Al-Dawsari: velocidad y remate desde banda",
            "Al-Owais: portero de nivel AFC muy sólido",
            "Contraataque rápido con línea alta rival",
        ],
        "weaknesses": [
            "Liga local (Saudi Pro League): nivel inflado por dinero, bajo competitivo",
            "Físico inferior a Europa",
            "Vulnerable a pressing sostenido",
        ],
        "historical_pattern": "WC2022: ganó a Argentina, cayó en grupos igual",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Presión alta sostenida que no les da espacios de contraataque",
    },
    "Iran": {
        "system": "4-1-4-1 / 5-3-2 defensivo (Queiroz?)",
        "identity": "Bloque bajo impenetrable, lento pero muy disciplinado",
        "key_players": ["Sardar Azmoun", "Alireza Jahanbakhsh", "Ali Gholizadeh"],
        "strengths": [
            "Organización defensiva de bloque bajo (5-4-1)",
            "Disciplina táctica y unidad colectiva",
            "Resistencia física en partidos de alto desgaste",
        ],
        "weaknesses": [
            "Velocidad defensiva muy baja: devastados por contraataques",
            "Poca generación ofensiva propia",
            "Muy vulnerable a presión alta",
        ],
        "historical_pattern": "WC2018/2022: siempre grupos, jamás octavos",
        "threat_level": "Baja-Media",
        "key_matchup_note": "Equipos veloces con espacios en profundidad",
    },
    "Iraq": {
        "system": "4-4-2 / 5-3-2 defensivo",
        "identity": "Defensiva organizada con experiencia en Copa Asia",
        "key_players": ["Aymen Hussein", "Ahmed Yasin", "Mohammed Qasim"],
        "strengths": [
            "Disciplina táctica defensiva",
            "Experiencia en Copa Asia",
            "Físico y determinación colectiva",
        ],
        "weaknesses": [
            "Poca experiencia en Mundiales (1986 fue la última)",
            "Técnica muy limitada",
            "Vulnerable a presión y velocidad",
        ],
        "historical_pattern": "Primera WC desde 1986",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo técnico o veloz europeo/americano",
    },
    "Qatar": {
        "system": "4-3-3 posesión (Marquez)",
        "identity": "WC2022 anfitrión eliminado en grupos, nivel real bajo",
        "key_players": ["Almoez Ali", "Akram Afif", "Boualem Khoukhi"],
        "strengths": [
            "Almoez Ali: goleador histórico de Copa Asia",
            "Afif: habilidad técnica elevada para la región AFC",
            "Experiencia de haber organizado WC2022",
        ],
        "weaknesses": [
            "WC2022: primer anfitrión eliminado en grupos",
            "Físico y velocidad muy inferiores",
            "Técnica inferior a cualquier equipo europeo o americano",
        ],
        "historical_pattern": "Primera WC como participante competitivo 2022 (mal)",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo del torneo",
    },
    "Jordan": {
        "system": "4-4-2 defensivo / 5-3-2 (Hasan Shehata?)",
        "identity": "Sorpresa de Copa Asia 2023 (finalistas), primera WC",
        "key_players": ["Mousa Al-Tamari", "Ahmad Ismail", "Yazan Al-Naimat"],
        "strengths": [
            "Disciplina defensiva que sorprende a equipos confiados",
            "Mentalidad de equipo compacto",
            "Capacidad de sorpresa",
        ],
        "weaknesses": [
            "Primera WC: inexperiencia total en este nivel",
            "Liga jordana de nivel muy bajo",
            "Físicamente muy inferior",
        ],
        "historical_pattern": "Primera participación en Mundial",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo con algo de calidad técnica",
    },
    "Uzbekistan": {
        "system": "4-3-3 / 4-2-3-1",
        "identity": "Generación joven de calidad para AFC, físico y disciplina",
        "key_players": ["Eldor Shomurodov", "Otabek Shukurov", "Jamshid Iskanderov"],
        "strengths": [
            "Shomurodov: delantero de nivel Serie A",
            "Físico y resistencia",
            "Disciplina colectiva",
        ],
        "weaknesses": [
            "Liga uzbeka de nivel muy bajo",
            "Poca experiencia internacional de primer nivel",
            "Técnica limitada bajo presión",
        ],
        "historical_pattern": "Primera WC",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo técnico del torneo",
    },
    "New Zealand": {
        "system": "4-4-2 / 5-3-2",
        "identity": "Chris Wood como referencia física, mentalidad guerrera",
        "key_players": ["Chris Wood", "Liberato Cacace", "Bill Tuilagi"],
        "strengths": [
            "Wood: delantero de nivel Premier League físico",
            "Cacace: lateral de calidad italiana (Empoli)",
            "Mentalidad valiente",
        ],
        "weaknesses": [
            "Liga neozelandesa de nivel mínimo mundial",
            "Vulnerable a pressing y velocidad",
            "Poca experiencia mundialista reciente",
        ],
        "historical_pattern": "WC2010 co-anfitriones con Australia",
        "threat_level": "Baja",
        "key_matchup_note": "Cualquier equipo con algo de velocidad o técnica",
    },
}


def get_scout_report(team_name: str) -> Optional[dict]:
    """
    Return the scouting report dict for a team.

    Tries exact match first, then partial match (case-insensitive).
    Returns None if no match found.
    """
    if team_name in SCOUT_REPORTS:
        return SCOUT_REPORTS[team_name]
    # Partial match
    tl = team_name.lower()
    for name, report in SCOUT_REPORTS.items():
        if tl in name.lower() or name.lower() in tl:
            return report
    return None


def format_scouting_summary(team_name: str) -> str:
    """
    Return a formatted scouting summary block for the given team.

    If no report is found, returns a short 'no data' message.
    """
    report = get_scout_report(team_name)
    if not report:
        return f"  Sin informe de scouting disponible para: {team_name}"

    identity = report.get("identity", "—")
    system = report.get("system", "—")
    key_players = report.get("key_players", [])
    strengths = report.get("strengths", [])
    weaknesses = report.get("weaknesses", [])
    historical = report.get("historical_pattern", "—")
    threat = report.get("threat_level", "—")
    matchup_note = report.get("key_matchup_note", "—")

    lines = [
        f"\n  SCOUTING: {team_name}",
        f"  {'=' * 50}",
        f"  Sistema:       {system}",
        f"  Identidad:     {identity}",
        f"  Amenaza:       {threat}",
        f"",
        f"  Jugadores clave:",
    ]
    for p in key_players:
        lines.append(f"    • {p}")

    lines.append(f"")
    lines.append(f"  Fortalezas:")
    for s in strengths:
        lines.append(f"    ✚ {s}")

    lines.append(f"")
    lines.append(f"  Debilidades:")
    for w in weaknesses:
        lines.append(f"    ✖ {w}")

    lines += [
        f"",
        f"  Patrón histórico: {historical}",
        f"  Rival peligroso: {matchup_note}",
    ]

    return "\n".join(lines)
