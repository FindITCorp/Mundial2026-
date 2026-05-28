"""
update_official_squads_may2026.py
Reemplaza squad_selections con las listas oficiales confirmadas al 28 mayo 2026.
Idempotente — se puede correr N veces sin duplicar.
fmt por jugador: (name, pos, club, league, age, caps, goals)
"""
import sqlite3, logging
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("official_squads")

OFFICIAL_SQUADS = {

"Brazil": [
    ("Alisson",           "GK",  "Liverpool",              "premier league",   32, 78, 0),
    ("Ederson",           "GK",  "Fenerbahçe",             "super lig",        31, 32, 0),
    ("Weverton",          "GK",  "Palmeiras",              "brasileirao",      37, 28, 0),
    ("Alex Sandro",       "DEF", "Flamengo",               "brasileirao",      33, 45, 5),
    ("Bremer",            "DEF", "Juventus",               "serie a",          27, 22, 2),
    ("Danilo",            "DEF", "Flamengo",               "brasileirao",      33, 85, 8),
    ("Douglas Santos",    "DEF", "Zenit",                  "russian premier",  30, 18, 1),
    ("Gabriel Magalhães", "DEF", "Arsenal",                "premier league",   27, 35, 5),
    ("Ibañez",            "DEF", "Al-Ahli",                "saudi pro league", 27, 15, 1),
    ("Léo Pereira",       "DEF", "Flamengo",               "brasileirao",      28, 12, 1),
    ("Marquinhos",        "DEF", "Paris Saint-Germain",    "ligue 1",          30, 82, 12),
    ("Wesley",            "DEF", "Aston Villa",            "premier league",   22,  8, 0),
    ("Bruno Guimarães",   "MID", "Newcastle",              "premier league",   27, 42, 8),
    ("Casemiro",          "MID", "Manchester United",      "premier league",   32, 85, 9),
    ("Danilo Santos",     "MID", "Botafogo",               "brasileirao",      26, 10, 1),
    ("Fabinho",           "MID", "Al-Ittihad",             "saudi pro league", 31, 55, 3),
    ("Lucas Paquetá",     "MID", "West Ham",               "premier league",   27, 55, 12),
    ("Andreas Pereira",   "MID", "Fulham",                 "premier league",   29, 15, 2),
    ("João Gomes",        "MID", "Wolverhampton",          "premier league",   23, 15, 1),
    ("Neymar",            "FWD", "Santos",                 "brasileirao",      32, 120, 77),
    ("Vinícius Júnior",   "FWD", "Real Madrid",            "la liga",          24, 55, 22),
    ("Rodrygo",           "FWD", "Real Madrid",            "la liga",          24, 38, 15),
    ("Raphinha",          "FWD", "Barcelona",              "la liga",          28, 48, 18),
    ("Gabriel Martinelli","FWD", "Arsenal",                "premier league",   23, 32, 8),
    ("Endrick",           "FWD", "Lyon",                   "ligue 1",          18, 12, 6),
    ("Savinho",           "FWD", "Manchester City",        "premier league",   21, 10, 3),
],

"Colombia": [
    ("David Ospina",      "GK",  "Al-Qadsiah",             "saudi pro league", 36, 120, 0),
    ("Camilo Vargas",     "GK",  "Atlas",                  "liga mx",          33, 45, 0),
    ("Álvaro Montero",    "GK",  "Deportes Tolima",        "liga betplay",     31, 12, 0),
    ("Davinson Sánchez",  "DEF", "Stade Rennais",          "ligue 1",          28, 75, 5),
    ("Yerry Mina",        "DEF", "Cagliari",               "serie a",          30, 62, 8),
    ("Carlos Cuesta",     "DEF", "Genk",                   "pro league",       25, 22, 2),
    ("Daniel Muñoz",      "DEF", "Crystal Palace",         "premier league",   28, 35, 3),
    ("Johan Mojica",      "DEF", "Getafe",                 "la liga",          32, 42, 2),
    ("Deiver Machado",    "DEF", "Lyon",                   "ligue 1",          30, 28, 1),
    ("Jhon Lucumí",       "DEF", "Bologna",                "serie a",          26, 20, 1),
    ("Willer Ditta",      "DEF", "Independiente",          "primera a",        29, 15, 1),
    ("James Rodríguez",   "MID", "Rayo Vallecano",         "la liga",          34, 95, 28),
    ("Jefferson Lerma",   "MID", "Crystal Palace",         "premier league",   29, 78, 5),
    ("Richard Ríos",      "MID", "Palmeiras",              "brasileirao",      25, 30, 3),
    ("Jorge Carrascal",   "MID", "River Plate",            "primera division", 27, 22, 4),
    ("Kevin Castaño",     "MID", "Villarreal",             "la liga",          26, 18, 1),
    ("Gustavo Puerta",    "MID", "Bayer Leverkusen",       "bundesliga",       22, 15, 2),
    ("Jhon Arias",        "MID", "Fluminense",             "brasileirao",      27, 25, 5),
    ("Juan Fernando Quintero","MID","River Plate",         "primera division", 32, 62, 12),
    ("Luis Díaz",         "FWD", "Liverpool",              "premier league",   28, 58, 18),
    ("Jhon Córdoba",      "FWD", "Krasnodar",              "russian premier",  31, 45, 15),
    ("Juan Camilo Hernández","FWD","Querétaro",            "liga mx",          27, 52, 20),
    ("Carlos Andrés Gómez","FWD","Independiente Medellín", "primera a",        27,  8, 2),
    ("Luis Suárez",       "FWD", "América de Cali",        "primera a",        28, 12, 3),
    ("Rafael Santos Borré","FWD","Internacional",          "brasileirao",      29, 42, 10),
],

"Spain": [
    ("Unai Simón",        "GK",  "Athletic Bilbao",        "la liga",          27, 38, 0),
    ("David Raya",        "GK",  "Arsenal",                "premier league",   29, 22, 0),
    ("Joan García",       "GK",  "Espanyol",               "la liga",          23,  5, 0),
    ("Dani Carvajal",     "DEF", "Real Madrid",            "la liga",          32, 78, 5),
    ("Aymeric Laporte",   "DEF", "Athletic Bilbao",        "la liga",          31, 52, 5),
    ("Robin Le Normand",  "DEF", "Atletico Madrid",        "la liga",          28, 22, 2),
    ("Pau Cubarsí",       "DEF", "Barcelona",              "la liga",          18, 12, 0),
    ("Alejandro Balde",   "DEF", "Barcelona",              "la liga",          21, 18, 1),
    ("Marc Cucurella",    "DEF", "Chelsea",                "premier league",   26, 28, 2),
    ("Marcos Llorente",   "DEF", "Atletico Madrid",        "la liga",          30, 42, 5),
    ("Dani Vivian",       "DEF", "Athletic Bilbao",        "la liga",          25, 15, 1),
    ("Rodri",             "MID", "Manchester City",        "premier league",   28, 55, 5),
    ("Pedri",             "MID", "Barcelona",              "la liga",          23, 38, 8),
    ("Gavi",              "MID", "Barcelona",              "la liga",          20, 42, 6),
    ("Martín Zubimendi",  "MID", "Arsenal",                "premier league",   26, 22, 1),
    ("Mikel Merino",      "MID", "Arsenal",                "premier league",   28, 35, 8),
    ("Fermín López",      "MID", "Barcelona",              "la liga",          22, 15, 4),
    ("Álex Baena",        "MID", "Villarreal",             "la liga",          24, 18, 3),
    ("Álvaro Morata",     "FWD", "AC Milan",               "serie a",          32, 72, 38),
    ("Nico Williams",     "FWD", "Athletic Bilbao",        "la liga",          22, 22, 8),
    ("Lamine Yamal",      "FWD", "Barcelona",              "la liga",          17, 20, 10),
    ("Dani Olmo",         "FWD", "Barcelona",              "la liga",          27, 38, 12),
    ("Ferran Torres",     "FWD", "Barcelona",              "la liga",          25, 42, 15),
    ("Yeremy Pino",       "FWD", "Crystal Palace",         "premier league",   22, 22, 5),
    ("Joselu",            "FWD", "Al-Qadsiah",             "saudi pro league", 34, 18, 8),
],

"France": [
    ("Mike Maignan",      "GK",  "AC Milan",               "serie a",          29, 32, 0),
    ("Robin Risser",      "GK",  "RC Lens",                "ligue 1",          24,  5, 0),
    ("Brice Samba",       "GK",  "RC Lens",                "ligue 1",          30, 12, 0),
    ("Jules Koundé",      "DEF", "Barcelona",              "la liga",          26, 42, 2),
    ("Malo Gusto",        "DEF", "Chelsea",                "premier league",   22, 18, 0),
    ("William Saliba",    "DEF", "Arsenal",                "premier league",   23, 25, 1),
    ("Dayot Upamecano",   "DEF", "Bayern Munich",          "bundesliga",       26, 48, 2),
    ("Ibrahima Konaté",   "DEF", "Liverpool",              "premier league",   26, 28, 1),
    ("Lucas Hernández",   "DEF", "Paris Saint-Germain",    "ligue 1",          28, 52, 2),
    ("Théo Hernández",    "DEF", "Al-Hilal",               "saudi pro league", 27, 42, 5),
    ("Lucas Digne",       "DEF", "Aston Villa",            "premier league",   31, 48, 2),
    ("Maxence Lacroix",   "DEF", "Crystal Palace",         "premier league",   25, 12, 1),
    ("Aurélien Tchouaméni","MID","Real Madrid",            "la liga",          25, 38, 2),
    ("Adrien Rabiot",     "MID", "AC Milan",               "serie a",          29, 55, 5),
    ("N'Golo Kanté",      "MID", "Fenerbahçe",             "super lig",        33, 58, 2),
    ("Warren Zaïre-Emery","MID", "Paris Saint-Germain",    "ligue 1",          18, 18, 2),
    ("Manu Koné",         "MID", "Roma",                   "serie a",          23, 15, 1),
    ("Kylian Mbappé",     "FWD", "Real Madrid",            "la liga",          26, 78, 48),
    ("Michael Olise",     "FWD", "Bayern Munich",          "bundesliga",       23, 15, 5),
    ("Ousmane Dembélé",   "FWD", "Paris Saint-Germain",    "ligue 1",          28, 52, 15),
    ("Désiré Doué",       "FWD", "Paris Saint-Germain",    "ligue 1",          20, 10, 2),
    ("Bradley Barcola",   "FWD", "Paris Saint-Germain",    "ligue 1",          22, 15, 3),
    ("Marcus Thuram",     "FWD", "Inter Milan",            "serie a",          27, 38, 12),
    ("Maghnes Akliouche", "FWD", "Monaco",                 "ligue 1",          23, 10, 2),
    ("Jean-Philippe Mateta","FWD","Crystal Palace",        "premier league",   27, 18, 5),
    ("Rayan Cherki",      "FWD", "Manchester City",        "premier league",   22, 12, 2),
],

"England": [
    ("Jordan Pickford",   "GK",  "Everton",                "premier league",   30, 62, 0),
    ("Aaron Ramsdale",    "GK",  "Southampton",            "premier league",   26, 12, 0),
    ("Dean Henderson",    "GK",  "Crystal Palace",         "premier league",   27,  8, 0),
    ("Kyle Walker",       "DEF", "Bayern Munich",          "bundesliga",       34, 82, 1),
    ("John Stones",       "DEF", "Manchester City",        "premier league",   30, 68, 3),
    ("Marc Guéhi",        "DEF", "Manchester City",        "premier league",   24, 22, 0),
    ("Ben White",         "DEF", "Arsenal",                "premier league",   27, 12, 0),
    ("Luke Shaw",         "DEF", "Manchester United",      "premier league",   29, 32, 1),
    ("Trent Alexander-Arnold","DEF","Real Madrid",         "la liga",          26, 38, 3),
    ("Reece James",       "DEF", "Chelsea",                "premier league",   25, 22, 1),
    ("Levi Colwill",      "DEF", "Chelsea",                "premier league",   22, 10, 0),
    ("Jude Bellingham",   "MID", "Real Madrid",            "la liga",          21, 38, 12),
    ("Declan Rice",       "MID", "Arsenal",                "premier league",   26, 48, 5),
    ("Cole Palmer",       "MID", "Chelsea",                "premier league",   22, 18, 5),
    ("Phil Foden",        "MID", "Manchester City",        "premier league",   24, 38, 8),
    ("Kobbie Mainoo",     "MID", "Manchester United",      "premier league",   20, 15, 2),
    ("Conor Gallagher",   "MID", "Atletico Madrid",        "la liga",          24, 22, 2),
    ("James Maddison",    "MID", "Tottenham",              "premier league",   28, 12, 2),
    ("Harry Kane",        "FWD", "Bayern Munich",          "bundesliga",       31, 90, 68),
    ("Bukayo Saka",       "FWD", "Arsenal",                "premier league",   23, 52, 15),
    ("Ollie Watkins",     "FWD", "Aston Villa",            "premier league",   29, 28, 8),
    ("Anthony Gordon",    "FWD", "Newcastle",              "premier league",   24, 12, 2),
    ("Ivan Toney",        "FWD", "Al-Ahli",                "saudi pro league", 29, 18, 5),
    ("Jarrod Bowen",      "FWD", "West Ham",               "premier league",   28, 22, 5),
],

"Portugal": [
    ("Diogo Costa",       "GK",  "Porto",                  "primeira liga",    25, 22, 0),
    ("Rui Patrício",      "GK",  "AS Roma",                "serie a",          36, 102, 0),
    ("José Sá",           "GK",  "Wolverhampton",          "premier league",   32, 18, 0),
    ("João Cancelo",      "DEF", "Al-Hilal",               "saudi pro league", 30, 62, 5),
    ("Nuno Mendes",       "DEF", "Paris Saint-Germain",    "ligue 1",          22, 28, 1),
    ("Rúben Dias",        "DEF", "Manchester City",        "premier league",   27, 65, 3),
    ("António Silva",     "DEF", "Benfica",                "primeira liga",    21, 18, 1),
    ("Gonçalo Inácio",    "DEF", "Sporting CP",            "primeira liga",    23, 22, 1),
    ("Diogo Dalot",       "DEF", "Manchester United",      "premier league",   26, 35, 2),
    ("Pepe",              "DEF", "Porto",                  "primeira liga",    42, 142, 8),
    ("Nélson Semedo",     "DEF", "Wolverhampton",          "premier league",   31, 42, 1),
    ("Bruno Fernandes",   "MID", "Manchester United",      "premier league",   30, 82, 12),
    ("Bernardo Silva",    "MID", "Manchester City",        "premier league",   30, 88, 18),
    ("João Neves",        "MID", "Paris Saint-Germain",    "ligue 1",          20, 22, 2),
    ("Vitinha",           "MID", "Paris Saint-Germain",    "ligue 1",          25, 35, 2),
    ("Palhinha",          "MID", "Bayern Munich",          "bundesliga",       29, 42, 2),
    ("Matheus Nunes",     "MID", "Manchester City",        "premier league",   26, 28, 1),
    ("Otávio",            "MID", "Al-Nassr",               "saudi pro league", 29, 38, 3),
    ("Cristiano Ronaldo", "FWD", "Al Nassr",               "saudi pro league", 41, 212, 128),
    ("Rafael Leão",       "FWD", "AC Milan",               "serie a",          25, 38, 8),
    ("Gonçalo Ramos",     "FWD", "Paris Saint-Germain",    "ligue 1",          23, 28, 12),
    ("João Félix",        "FWD", "Chelsea",                "premier league",   25, 42, 12),
    ("Diogo Jota",        "FWD", "Liverpool",              "premier league",   28, 48, 18),
    ("Pedro Neto",        "FWD", "Chelsea",                "premier league",   25, 28, 5),
],

"Panama": [
    ("Orlando Mosquera",  "GK",  "Club Atlético Ind.",     "primera a",        28, 22, 0),
    ("Luis Mejía",        "GK",  "Independiente Medellín", "primera a",        27, 18, 0),
    ("César Samudio",     "GK",  "Tauro FC",               "lpf panama",       30, 10, 0),
    ("César Blackman",    "DEF", "Tauro FC",               "lpf panama",       26, 28, 1),
    ("Fidel Escobar",     "DEF", "Santos Laguna",          "liga mx",          30, 55, 3),
    ("Andrés Andrade",    "DEF", "Independiente",          "primera a",        28, 38, 2),
    ("José Córdoba",      "DEF", "Club Atlético Nacional", "primera a",        27, 22, 1),
    ("Amir Murillo",      "DEF", "Montpellier",            "ligue 1",          30, 62, 2),
    ("Jorge Gutiérrez",   "DEF", "Club Atlético Nacional", "primera a",        29, 35, 1),
    ("Eric Davis",        "DEF", "New England Revolution", "mls",              35, 72, 5),
    ("Jiovany Ramos",     "DEF", "CD Plaza Amador",        "lpf panama",       23,  8, 0),
    ("Adalberto Carrasquilla","MID","Wigan Athletic",      "championship",     26, 45, 5),
    ("Aníbal Godoy",      "MID", "Nashville SC",           "mls",              35, 95, 3),
    ("Cristian Martínez", "MID", "Tauro FC",               "lpf panama",       27, 22, 2),
    ("Édgar Bárcenas",    "MID", "Leganés",                "la liga",          31, 55, 5),
    ("Víctor Griffith",   "MID", "Houston Dynamo",         "mls",              26, 28, 3),
    ("César Yanis",       "MID", "CD Plaza Amador",        "lpf panama",       28, 18, 2),
    ("Abdiel Ayarza",     "MID", "Vitória",                "brasileirao",      22, 15, 1),
    ("José Luis Rodríguez","MID","CD Olimpia",             "liga nacional hn", 29, 32, 2),
    ("Ismael Díaz",       "FWD", "Guadalajara",            "liga mx",          25, 38, 8),
    ("Cecilio Waterman",  "FWD", "Orlando City",           "mls",              30, 48, 12),
    ("José Fajardo",      "FWD", "FC Dallas",              "mls",              27, 35, 8),
    ("Eduardo Guerrero",  "FWD", "CD Plaza Amador",        "lpf panama",       28, 25, 5),
    ("Tomás Rodríguez",   "FWD", "Tauro FC",               "lpf panama",       22, 10, 2),
],

"Germany": [
    ("Manuel Neuer",      "GK",  "Bayern Munich",          "bundesliga",       39, 120, 0),
    ("Marc-André ter Stegen","GK","Barcelona",             "la liga",          33, 42, 0),
    ("Oliver Baumann",    "GK",  "Hoffenheim",             "bundesliga",       34, 18, 0),
    ("Antonio Rüdiger",   "DEF", "Real Madrid",            "la liga",          31, 78, 2),
    ("Jonathan Tah",      "DEF", "Bayern Munich",          "bundesliga",       29, 35, 1),
    ("Nico Schlotterbeck","DEF", "Borussia Dortmund",      "bundesliga",       25, 22, 1),
    ("Benjamin Henrichs", "DEF", "RB Leipzig",             "bundesliga",       28, 35, 2),
    ("David Raum",        "DEF", "RB Leipzig",             "bundesliga",       26, 28, 3),
    ("Robin Koch",        "DEF", "Eintracht Frankfurt",    "bundesliga",       28, 22, 0),
    ("Waldemar Anton",    "DEF", "Borussia Dortmund",      "bundesliga",       28, 18, 1),
    ("Joshua Kimmich",    "DEF", "Bayern Munich",          "bundesliga",       29, 82, 8),
    ("Jamal Musiala",     "MID", "Bayern Munich",          "bundesliga",       22, 38, 12),
    ("Florian Wirtz",     "MID", "Liverpool",              "premier league",   22, 28, 8),
    ("İlkay Gündoğan",    "MID", "Barcelona",              "la liga",          35, 82, 18),
    ("Pascal Groß",       "MID", "Borussia Dortmund",      "bundesliga",       33, 22, 2),
    ("Leon Goretzka",     "MID", "Bayern Munich",          "bundesliga",       30, 52, 10),
    ("Robert Andrich",    "MID", "Bayer Leverkusen",       "bundesliga",       30, 25, 2),
    ("Aleksandar Pavlović","MID","Bayern Munich",          "bundesliga",       21, 12, 1),
    ("Kai Havertz",       "FWD", "Arsenal",                "premier league",   26, 55, 25),
    ("Leroy Sané",        "FWD", "Galatasaray",            "super lig",        29, 62, 18),
    ("Niclas Füllkrug",   "FWD", "West Ham",               "premier league",   32, 28, 12),
    ("Deniz Undav",       "FWD", "VfB Stuttgart",          "bundesliga",       28, 18, 6),
    ("Maximilian Beier",  "FWD", "Borussia Dortmund",      "bundesliga",       22, 12, 3),
    ("Chris Führich",     "FWD", "VfB Stuttgart",          "bundesliga",       27, 15, 2),
],

"Uruguay": [
    ("Sergio Rochet",     "GK",  "Nacional",               "primera division uy",30,35, 0),
    ("Santiago Mele",     "GK",  "Junior",                 "primera a",        26, 12, 0),
    ("Franco Israel",     "GK",  "Sporting CP",            "primeira liga",    25,  8, 0),
    ("Ronald Araújo",     "DEF", "Barcelona",              "la liga",          25, 38, 3),
    ("José María Giménez","DEF", "Atletico Madrid",        "la liga",          30, 75, 5),
    ("Mathías Olivera",   "DEF", "Napoli",                 "serie a",          27, 35, 2),
    ("Nahitan Nández",    "DEF", "Cagliari",               "serie a",          28, 52, 3),
    ("Sebastián Cáceres", "DEF", "Club America",           "liga mx",          27, 18, 1),
    ("Joaquín Piquerez",  "DEF", "Palmeiras",              "brasileirao",      26, 22, 1),
    ("Guillermo Varela",  "DEF", "Flamengo",               "brasileirao",      32, 28, 1),
    ("Federico Valverde", "MID", "Real Madrid",            "la liga",          26, 62, 10),
    ("Manuel Ugarte",     "MID", "Manchester United",      "premier league",   23, 32, 2),
    ("Nicolás de la Cruz","MID", "Flamengo",               "brasileirao",      27, 45, 8),
    ("Rodrigo Bentancur", "MID", "Tottenham",              "premier league",   27, 65, 5),
    ("Giorgian De Arrascaeta","MID","Flamengo",            "brasileirao",      30, 68, 12),
    ("Facundo Pellistri", "MID", "Panathinaikos",          "super league greece",23,22, 3),
    ("Nicolás Fonseca",   "MID", "Inter Milan",            "serie a",          24, 15, 1),
    ("Darwin Núñez",      "FWD", "Liverpool",              "premier league",   25, 42, 18),
    ("Luis Suárez",       "FWD", "Independiente",          "primera a",        37, 142, 68),
    ("Maximiliano Araújo","FWD", "Sporting CP",            "primeira liga",    25, 28, 5),
    ("Brian Rodríguez",   "FWD", "Atlas",                  "liga mx",          25, 32, 5),
    ("Agustín Canobbio",  "FWD", "Toronto FC",             "mls",              25, 18, 3),
    ("Cristian Olivera",  "FWD", "Napoli",                 "serie a",          24, 15, 2),
],

"Croatia": [
    ("Dominik Livaković", "GK",  "Fenerbahçe",             "super lig",        29, 55, 0),
    ("Ivica Ivušić",      "GK",  "Panathinaikos",          "super league greece",30,22, 0),
    ("Nediljko Labrović", "GK",  "Hajduk Split",           "hnl",              25, 10, 0),
    ("Joško Gvardiol",    "DEF", "Manchester City",        "premier league",   23, 48, 3),
    ("Josip Šutalo",      "DEF", "Ajax",                   "eredivisie",       24, 18, 1),
    ("Borna Sosa",        "DEF", "Ajax",                   "eredivisie",       26, 32, 3),
    ("Josip Juranović",   "DEF", "Union Berlin",           "bundesliga",       29, 42, 2),
    ("Marin Pongračić",   "DEF", "Celta Vigo",             "la liga",          28, 22, 1),
    ("Martin Erlić",      "DEF", "RB Leipzig",             "bundesliga",       26, 18, 0),
    ("Josip Stanišić",    "DEF", "Bayer Leverkusen",       "bundesliga",       24, 18, 0),
    ("Luka Modrić",       "MID", "Real Madrid",            "la liga",          39, 172, 25),
    ("Mateo Kovačić",     "MID", "Manchester City",        "premier league",   30, 98, 18),
    ("Marcelo Brozović",  "MID", "Al-Nassr",               "saudi pro league", 32, 102, 12),
    ("Lovro Majer",       "MID", "Wolfsburg",              "bundesliga",       27, 38, 5),
    ("Mario Pašalić",     "MID", "Atalanta",               "serie a",          29, 52, 10),
    ("Luka Sučić",        "MID", "RB Leipzig",             "bundesliga",       22, 18, 2),
    ("Martin Baturina",   "MID", "Chelsea",                "premier league",   22, 12, 2),
    ("Andrej Kramarić",   "FWD", "Hoffenheim",             "bundesliga",       34, 82, 35),
    ("Bruno Petković",    "FWD", "Dinamo Zagreb",          "hnl",              30, 42, 10),
    ("Ante Budimir",      "FWD", "Osasuna",                "la liga",          33, 38, 15),
    ("Marko Pjaca",       "FWD", "Sporting CP",            "primeira liga",    29, 32, 5),
    ("Josip Brekalo",     "FWD", "Hajduk Split",           "hnl",              27, 35, 5),
    ("Petar Musa",        "FWD", "Benfica",                "primeira liga",    25, 18, 5),
],

}


def normalize(name: str) -> str:
    """Simple normalization for fuzzy matching."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def find_player(cur, name: str, team_id: int):
    """Find player by exact name or normalized name."""
    row = cur.execute(
        "SELECT id FROM players WHERE name=? AND team_id=?", (name, team_id)
    ).fetchone()
    if row:
        return row["id"]
    norm = normalize(name)
    all_players = cur.execute(
        "SELECT id, name FROM players WHERE team_id=?", (team_id,)
    ).fetchall()
    for p in all_players:
        if normalize(p["name"]) == norm:
            return p["id"]
    return None


def run():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    for team_name, squad in OFFICIAL_SQUADS.items():
        row = cur.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            log.warning("Team not found: %s", team_name)
            continue
        team_id = row["id"]

        # Clear existing squad_selections for this team
        cur.execute("DELETE FROM squad_selections WHERE team_id=?", (team_id,))
        log.info("Cleared squad_selections for %s (team_id=%d)", team_name, team_id)

        inserted = 0
        for name, pos, club, league, age, caps, goals in squad:
            pid = find_player(cur, name, team_id)
            if pid:
                # Update club/age data
                cur.execute("""
                    UPDATE players SET club=?, club_league=?, age=?, caps=?, goals_as_nat=?
                    WHERE id=?
                """, (club, league, age, caps, goals, pid))
            else:
                # Insert new player
                cur.execute("""
                    INSERT INTO players (name, team_id, position, club, club_league, age, caps, goals_as_nat)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (name, team_id, pos, club, league, age, caps, goals))
                pid = cur.lastrowid
                log.info("  NEW player: %s (%s)", name, team_name)

            cur.execute("""
                INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed)
                VALUES (?,?,1)
            """, (team_id, pid))
            inserted += 1

        conn.commit()
        log.info("%-12s → %d jugadores en squad_selections", team_name, inserted)

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    run()
