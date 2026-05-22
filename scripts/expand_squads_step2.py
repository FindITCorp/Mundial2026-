#!/usr/bin/env python3
"""Step 2: Add known players for teams still under 26 via hardcoded squads."""
import sqlite3
from pathlib import Path

DB = Path("/home/user/mundial2026/data/mundial2026.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

teams = {r['name']: r['id'] for r in conn.execute("SELECT id, name FROM teams").fetchall()}
existing_players = set()
for r in conn.execute("SELECT LOWER(name), team_id FROM players").fetchall():
    existing_players.add((r[0], r[1]))

def add_player(team_name, name, position, club='', league='', age=None, caps=0, goals=0, height=None, market=None):
    name = name.strip()
    if not name or len(name) < 2: return False
    tid = teams.get(team_name)
    if not tid: return False
    pos_map = {
        'GK':'GK','DF':'DEF','MF':'MID','FW':'FWD',
        'DEF':'DEF','MID':'MID','FWD':'FWD','FOR':'FWD',
        'CB':'DEF','LB':'DEF','RB':'DEF','LWB':'DEF','RWB':'DEF',
        'CM':'MID','DM':'MID','AM':'MID','LM':'MID','RM':'MID',
        'CF':'FWD','ST':'FWD','LW':'FWD','RW':'FWD',
    }
    pos = pos_map.get(position.upper()[:3], 'MID')
    if (name.lower(), tid) in existing_players: return False
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO players (name, team_id, position, club, club_league, age, caps, goals_as_nat, height_cm, market_value_m)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (name, tid, pos, club or '', league or '', age, caps or 0, goals or 0, height, market))
        if cur.rowcount:
            pid = cur.lastrowid
            conn.execute("INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed) VALUES (?,?,1)", (tid, pid))
            existing_players.add((name.lower(), tid))
            return True
    except Exception as e:
        print(f"  Error {name}: {e}")
    return False

total = 0

# ── GHANA ──────────────────────────────────────────────────────────────────
ghana = [
    ("Lawrence Ati-Zigi","GK","St. Gallen","Swiss Super League",28,32,0,185),
    ("Jojo Wollacott","GK","Charlton Athletic","EFL League One",28,18,0,190),
    ("Ibrahim Danlad","GK","Asante Kotoko","Ghana Premier League",22,5,0,186),
    ("Tariq Lamptey","DEF","Brighton","Premier League",24,28,1,173),
    ("Andy Yiadom","DEF","Reading","EFL Championship",32,52,2,180),
    ("Daniel Amartey","DEF","Besiktas","Süper Lig",29,47,3,188),
    ("Denis Odoi","DEF","Club Brugge","Pro League",36,14,0,180),
    ("Gideon Mensah","DEF","Red Bull Salzburg","Bundesliga",25,22,1,181),
    ("Alexander Djiku","DEF","Fenerbahce","Süper Lig",30,42,2,190),
    ("Baba Rahman","DEF","Reading","EFL Championship",30,45,2,178),
    ("Alidu Seidu","DEF","Clermont Foot","Ligue 1",24,19,0,173),
    ("Thomas Partey","MID","Arsenal","Premier League",31,52,14,185),
    ("Mohammed Kudus","MID","West Ham","Premier League",24,40,16,177),
    ("Elisha Owusu","MID","Gent","Pro League",26,18,1,183),
    ("Salis Abdul Samed","MID","RC Lens","Ligue 1",24,22,1,180),
    ("Kamal Sowah","MID","Club Brugge","Pro League",25,14,2,173),
    ("Osman Bukari","FWD","Red Star Belgrade","Serbian SuperLiga",25,28,7,178),
    ("Antoine Semenyo","FWD","Bournemouth","Premier League",25,18,4,178),
    ("Ernest Nuamah","FWD","Lyon","Ligue 1",22,10,2,178),
    ("Felix Afena-Gyan","FWD","Cremonese","Serie B",22,20,3,178),
    ("Kamaldeen Sulemana","FWD","Southampton","Premier League",22,30,9,178),
    ("Jordan Ayew","FWD","Crystal Palace","Premier League",32,108,22,178),
    ("Andre Ayew","FWD","Le Havre","Ligue 1",34,116,26,180),
    ("Inaki Williams","FWD","Athletic Bilbao","La Liga",30,24,5,182),
    ("Richmond Boakye","FWD","PAOK","Super League Greece",30,18,5,183),
    ("Abdul Fatawu","FWD","Leicester City","Premier League",20,12,3,175),
]
for p in ghana:
    r = add_player("Ghana", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── VENEZUELA ─────────────────────────────────────────────────────────────
venezuela = [
    ("Wuilker Faríñez","GK","Millonarios","Liga BetPlay",28,60,0,185),
    ("Rafael Romo","GK","Sporting KC","MLS",34,32,0,187),
    ("Daniel Martínez","GK","Caracas FC","Venezuelan Primera",26,8,0,188),
    ("Yordan Osorio","DEF","Tigres UANL","Liga MX",28,52,4,186),
    ("Christian Makoun","DEF","Deportivo Táchira","Venezuelan Primera",34,65,2,183),
    ("Nahuel Ferraresi","DEF","Sion","Swiss Super League",24,38,3,186),
    ("Miguel Navarro","DEF","Monaco","Ligue 1",24,32,2,178),
    ("Willian Rincón","MID","Deportivo Táchira","Venezuelan Primera",34,72,5,180),
    ("Tomás Rincón","MID","Parma","Serie A",37,128,8,180),
    ("Yangel Herrera","MID","Barcelona","La Liga",26,70,12,180),
    ("Jefferson Savarino","MID","Real Salt Lake","MLS",28,56,12,178),
    ("Kristopher Villalba","MID","Unattached","",30,34,4,175),
    ("Eduard Bello","MID","Deportivo Táchira","Venezuelan Primera",24,18,3,178),
    ("Junior Moreno","MID","DC United","MLS",34,52,2,183),
    ("Sergio Córdova","FWD","Standard Liège","Pro League",27,45,7,180),
    ("Darwin Machís","FWD","Granada","LaLiga2",31,88,22,175),
    ("Salomón Rondón","FWD","Everton","Premier League",35,114,35,187),
    ("Josef Martínez","FWD","Inter Miami","MLS",31,82,24,175),
    ("Rómulo Otero","FWD","Corinthians","Série A",31,40,8,175),
    ("Jan Hurtado","FWD","Girona","La Liga",25,22,3,183),
    ("Edson Castillo","MID","Club Tijuana","Liga MX",29,38,4,178),
    ("Fernando Aristeguieta","FWD","Estudiantes","Liga Profesional",30,30,6,184),
]
for p in venezuela:
    r = add_player("Venezuela", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── ECUADOR ────────────────────────────────────────────────────────────────
ecuador = [
    ("Hernán Galíndez","GK","Aucas","Serie A Ecuador",36,38,0,187),
    ("Alexander Domínguez","GK","Liga de Quito","Serie A Ecuador",37,72,0,185),
    ("Moisés Ramírez","GK","Independiente del Valle","Serie A Ecuador",26,18,0,183),
    ("Ángelo Preciado","DEF","Genk","Jupiler Pro League",26,42,3,175),
    ("Piero Hincapié","DEF","Bayer Leverkusen","Bundesliga",22,42,2,181),
    ("Robert Arboleda","DEF","São Paulo","Série A",32,62,5,190),
    ("Diego Palacios","DEF","LAFC","MLS",25,32,1,178),
    ("William Pacho","DEF","PSG","Ligue 1",23,30,1,185),
    ("Félix Torres","DEF","Santos Laguna","Liga MX",27,35,2,186),
    ("Jackson Porozo","DEF","Troyes","Ligue 2",24,22,1,188),
    ("Moisés Caicedo","MID","Chelsea","Premier League",23,55,3,178),
    ("Jhegson Méndez","MID","LAFC","MLS",26,48,3,175),
    ("Carlos Gruezo","MID","Augsburg","Bundesliga",29,52,2,175),
    ("Ángel Mena","MID","León","Liga MX",35,82,22,172),
    ("Gonzalo Plata","FWD","Real Valladolid","La Liga",24,48,8,178),
    ("Pervis Estupiñán","DEF","Brighton","Premier League",26,52,3,175),
    ("Kevin Rodríguez","FWD","Ipswich Town","Premier League",23,22,5,178),
    ("Jordy Caicedo","FWD","Aucas","Serie A Ecuador",30,38,12,183),
    ("Renato Ibarra","MID","América","Liga MX",33,62,12,175),
    ("Ayrton Preciado","FWD","Santos Laguna","Liga MX",28,32,6,174),
    ("Djorkaeff Reasco","FWD","Newell's Old Boys","Liga Profesional",24,18,4,178),
    ("Michael Estrada","FWD","Cruz Azul","Liga MX",28,42,12,183),
    ("Enner Valencia","FWD","Fenerbahce","Süper Lig",34,96,40,180),
    ("Jeremy Sarmiento","FWD","Brighton","Premier League",23,28,4,175),
]
for p in ecuador:
    r = add_player("Ecuador", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── CANADA ────────────────────────────────────────────────────────────────
canada = [
    ("Maxime Crépeau","GK","LAFC","MLS",30,40,0,187),
    ("Milan Borjan","GK","Red Star Belgrade","Serbian SuperLiga",36,72,0,193),
    ("James Pantemis","GK","CF Montréal","MLS",27,12,0,188),
    ("Kamal Miller","DEF","LAFC","MLS",27,48,4,183),
    ("Steven Vitória","DEF","Moreirense","Liga Portugal",35,62,3,190),
    ("Alistair Johnston","DEF","Celtic","Scottish Premiership",25,42,2,178),
    ("Sam Adekugbe","DEF","Hatayspor","Süper Lig",28,50,4,175),
    ("Richie Laryea","DEF","Nottm Forest","Premier League",29,52,6,172),
    ("Doneil Henry","DEF","Vancouver Whitecaps","MLS",31,62,2,188),
    ("Derek Cornelius","DEF","Vancouver Whitecaps","MLS",26,38,3,191),
    ("Joel Waterman","DEF","CF Montréal","MLS",28,22,1,187),
    ("Liam Fraser","MID","Lorient","Ligue 1",27,22,1,180),
    ("Stephen Eustáquio","MID","Porto","Primeira Liga",27,52,4,175),
    ("Atiba Hutchinson","MID","Besiktas","Süper Lig",40,104,9,180),
    ("Jonathan Osorio","MID","Toronto FC","MLS",31,68,8,178),
    ("Samuel Piette","MID","CF Montréal","MLS",30,56,0,175),
    ("Mark-Anthony Kaye","MID","San Jose Earthquakes","MLS",29,40,3,180),
    ("Ismaël Koné","MID","Watford","EFL Championship",22,28,2,180),
    ("Tajon Buchanan","FWD","Inter Milan","Serie A",25,52,12,178),
    ("Cyle Larin","FWD","Real Valladolid","La Liga",29,64,28,183),
    ("Lucas Cavallini","FWD","Vancouver Whitecaps","MLS",30,52,18,188),
    ("Jonathan David","FWD","Lille","Ligue 1",24,56,26,178),
    ("Alphonso Davies","DEF","Bayern Munich","Bundesliga",24,68,13,175),
    ("Junior Hoilett","FWD","FC Zürich","Swiss Super League",33,74,16,175),
    ("Theo Bair","FWD","Middlesbrough","EFL Championship",24,8,2,187),
    ("Charles-Andreas Brym","FWD","SC Freiburg","Bundesliga",26,18,4,183),
]
for p in canada:
    r = add_player("Canada", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SENEGAL ────────────────────────────────────────────────────────────────
senegal = [
    ("Édouard Mendy","GK","Al-Ahli","Saudi Pro League",32,40,0,197),
    ("Seny Dieng","GK","Middlesbrough","EFL Championship",29,22,0,193),
    ("Alfred Gomis","GK","Stade Rennais","Ligue 1",31,18,0,193),
    ("Bouna Sarr","DEF","Bayern Munich","Bundesliga",32,18,1,177),
    ("Abdou Diallo","DEF","RB Leipzig","Bundesliga",28,42,3,185),
    ("Kalidou Koulibaly","DEF","Al-Hilal","Saudi Pro League",33,72,6,187),
    ("Youssouf Sabaly","DEF","Real Betis","La Liga",32,30,2,175),
    ("Ibrahima Mbaye","DEF","Bologna","Serie A",28,22,0,178),
    ("Formose Mendy","DEF","Girondins Bordeaux","Ligue 2",26,12,0,183),
    ("Pape Abou Cissé","DEF","Olympiakos","Super League Greece",29,30,2,192),
    ("Nampalys Mendy","MID","Lorient","Ligue 1",32,42,1,168),
    ("Cheikhou Kouyaté","MID","Nottm Forest","Premier League",34,102,5,185),
    ("Idrissa Gueye","MID","Everton","Premier League",35,106,2,174),
    ("Pape Matar Sarr","MID","Tottenham","Premier League",22,32,3,183),
    ("Moussa Niakhaté","DEF","Nottm Forest","Premier League",28,22,1,187),
    ("Krepin Diatta","FWD","Monaco","Ligue 1",25,42,6,175),
    ("Bamba Dieng","FWD","Lorient","Ligue 1",23,18,3,183),
    ("Ismaïla Sarr","FWD","Crystal Palace","Premier League",26,58,16,180),
    ("Nicolas Jackson","FWD","Chelsea","Premier League",23,32,7,185),
    ("Habib Diallo","FWD","Al-Shabab","Saudi Pro League",29,48,20,185),
    ("Sadio Mané","FWD","Al-Nassr","Saudi Pro League",32,96,35,175),
    ("Iliman Ndiaye","FWD","Everton","Premier League",24,28,8,175),
    ("Famara Diédhiou","FWD","Al-Fayha","Saudi Pro League",32,52,18,190),
    ("Mame Baba Thiam","FWD","Karagümrük","Süper Lig",28,24,5,183),
    ("Abdallah Sima","FWD","Brighton","Premier League",23,18,4,188),
    ("Lamine Camara","MID","AS Monaco","Ligue 1",20,18,5,178),
]
for p in senegal:
    r = add_player("Senegal", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SOUTH KOREA ────────────────────────────────────────────────────────────
south_korea = [
    ("Kim Seung-gyu","GK","Vissel Kobe","J1 League",35,72,0,188),
    ("Jo Hyeon-woo","GK","Ulsan HD","K League 1",32,18,0,190),
    ("Song Bum-keun","GK","Jeonbuk Motors","K League 1",27,5,0,188),
    ("Kim Min-jae","DEF","Bayern Munich","Bundesliga",28,62,8,190),
    ("Kim Young-gwon","DEF","Ulsan HD","K League 1",35,112,8,185),
    ("Kim Jin-su","DEF","Jeonbuk Motors","K League 1",32,80,4,180),
    ("Hong Chul","DEF","Suwon","K League 1",31,20,0,175),
    ("Lee Ki-je","DEF","Gimcheon Sangmu","K League 1",26,8,0,183),
    ("Jung Seung-hyun","DEF","Al-Shabab","Saudi Pro League",30,42,3,186),
    ("Kim Tae-hwan","DEF","Ulsan HD","K League 1",33,62,2,183),
    ("Lee Jae-sung","MID","Mainz","Bundesliga",32,82,17,178),
    ("Jung Woo-young","MID","Al-Qadsiah","Saudi Pro League",34,76,4,183),
    ("Son Heung-min","FWD","Tottenham","Premier League",32,130,35,183),
    ("Hwang Hee-chan","FWD","Wolves","Premier League",28,72,18,177),
    ("Hwang In-beom","MID","Vancouver Whitecaps","MLS",29,68,8,180),
    ("Lee Kang-in","MID","PSG","Ligue 1",23,62,12,173),
    ("Cho Gue-sung","FWD","Jeonbuk Motors","K League 1",26,28,12,185),
    ("Um Won-sang","FWD","Jeonbuk Motors","K League 1",27,22,5,178),
    ("Na Sang-ho","FWD","Seoul E-Land","K League 2",27,18,4,178),
    ("Paik Seung-ho","MID","Jeonbuk Motors","K League 1",28,38,4,175),
    ("Kwon Chang-hoon","FWD","Gimcheon Sangmu","K League 1",29,60,11,175),
    ("Oh Se-hun","FWD","Seoul","K League 1",25,12,3,188),
    ("Seol Young-woo","FWD","Gent","Pro League",23,8,2,178),
    ("Bae Jun-ho","MID","Stoke City","EFL Championship",22,18,3,180),
    ("Yang Hyun-jun","FWD","Celtic","Scottish Premiership",22,22,4,178),
    ("Kim Hyun-woo","DEF","Jeju United","K League 1",28,8,0,183),
]
for p in south_korea:
    r = add_player("South Korea", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── JAPAN ──────────────────────────────────────────────────────────────────
japan = [
    ("Shuichi Gonda","GK","Shimizu S-Pulse","J1 League",34,62,0,183),
    ("Zion Suzuki","GK","Sint-Truiden","Jupiler Pro League",22,12,0,189),
    ("Kosuke Heguri","GK","Urawa Reds","J1 League",24,5,0,185),
    ("Hiroki Sakai","DEF","Urawa Reds","J1 League",34,70,4,176),
    ("Yuto Nagatomo","DEF","FC Tokyo","J1 League",37,142,9,170),
    ("Miki Yamane","DEF","Kawasaki Frontale","J1 League",30,22,2,175),
    ("Ko Itakura","DEF","Borussia Mönchengladbach","Bundesliga",27,40,3,185),
    ("Maya Yoshida","DEF","Shamrock Rovers","League of Ireland",36,132,4,187),
    ("Shogo Taniguchi","DEF","Kawasaki Frontale","J1 League",32,48,2,181),
    ("Takehiro Tomiyasu","DEF","Arsenal","Premier League",25,52,2,187),
    ("Hidemasa Morita","MID","Sporting CP","Primeira Liga",29,40,3,178),
    ("Wataru Endo","MID","Liverpool","Premier League",31,56,2,178),
    ("Shunsuke Nakamura","MID","Yokohama F. Marinos","J1 League",46,98,24,175),
    ("Junya Ito","FWD","Stade Rennais","Ligue 1",31,58,12,176),
    ("Daichi Kamada","MID","Crystal Palace","Premier League",28,46,12,180),
    ("Kaoru Mitoma","FWD","Brighton","Premier League",27,40,14,178),
    ("Ayase Ueda","FWD","Stade Rennais","Ligue 1",26,28,14,180),
    ("Ritsu Doan","FWD","Freiburg","Bundesliga",26,52,16,172),
    ("Takumi Minamino","FWD","Monaco","Ligue 1",29,62,22,172),
    ("Keito Nakamura","FWD","Stade Rennais","Ligue 1",24,22,6,175),
    ("Takefusa Kubo","FWD","Real Sociedad","La Liga",23,42,5,173),
    ("Ao Tanaka","MID","Dortmund","Bundesliga",25,42,5,177),
    ("Mao Hosoya","FWD","Kashiwa Reysol","J1 League",24,8,3,182),
    ("Hiroki Ito","DEF","Stuttgart","Bundesliga",25,22,2,184),
    ("Yuki Soma","MID","Nagoya Grampus","J1 League",27,20,3,178),
    ("Yukinari Sugawara","DEF","AZ Alkmaar","Eredivisie",23,22,2,172),
]
for p in japan:
    r = add_player("Japan", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SWITZERLAND ────────────────────────────────────────────────────────────
switzerland = [
    ("Yann Sommer","GK","Inter Milan","Serie A",35,88,0,183),
    ("Gregor Kobel","GK","Dortmund","Bundesliga",27,12,0,194),
    ("Philipp Köhn","GK","Monaco","Ligue 1",26,5,0,186),
    ("Silvan Widmer","DEF","Mainz","Bundesliga",31,44,3,180),
    ("Loris Benito","DEF","Girondins Bordeaux","Ligue 2",33,18,1,178),
    ("Manuel Akanji","DEF","Manchester City","Premier League",29,62,5,187),
    ("Nico Elvedi","DEF","Borussia Mönchengladbach","Bundesliga",27,58,4,190),
    ("Fabian Schär","DEF","Newcastle","Premier League",32,72,7,186),
    ("Ricardo Rodriguez","DEF","Torino","Serie A",32,110,7,182),
    ("Kevin Mbabu","DEF","Fulham","Premier League",29,42,2,181),
    ("Denis Zakaria","MID","Monaco","Ligue 1",27,42,4,191),
    ("Granit Xhaka","MID","Bayer Leverkusen","Bundesliga",31,122,14,186),
    ("Remo Freuler","MID","Nottm Forest","Premier League",32,70,5,180),
    ("Xherdan Shaqiri","FWD","Chicago Fire","MLS",32,108,32,169),
    ("Haris Seferovic","FWD","Galatasaray","Süper Lig",31,84,27,187),
    ("Breel Embolo","FWD","Monaco","Ligue 1",27,62,18,187),
    ("Ruben Vargas","FWD","Augsburg","Bundesliga",25,38,8,178),
    ("Michel Aebischer","MID","Bologna","Serie A",27,26,3,180),
    ("Fabian Frei","MID","Basel","Swiss Super League",35,72,14,181),
    ("Dan Ndoye","FWD","Bologna","Serie A",24,22,6,183),
    ("Andi Zeqiri","FWD","Genk","Jupiler Pro League",25,22,6,178),
    ("Zeki Amdouni","FWD","Burnley","EFL Championship",24,18,7,184),
    ("Noah Okafor","FWD","AC Milan","Serie A",24,28,8,183),
    ("Edimilson Fernandes","MID","Mainz","Bundesliga",28,38,4,188),
    ("Vincent Sierro","MID","Toulouse","Ligue 1",29,22,3,182),
    ("Ardon Jashari","MID","Club Brugge","Pro League",22,12,2,180),
]
for p in switzerland:
    r = add_player("Switzerland", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── COLOMBIA ────────────────────────────────────────────────────────────────
colombia = [
    ("Camilo Vargas","GK","Atlas","Liga MX",33,58,0,188),
    ("David Ospina","GK","Al-Qadsiah","Saudi Pro League",36,122,0,183),
    ("Álvaro Montero","GK","Millonarios","Liga BetPlay",27,8,0,188),
    ("Santiago Arias","DEF","Girona","La Liga",32,68,5,172),
    ("Yerry Mina","DEF","Valencia","La Liga",29,62,10,194),
    ("Dávinson Sánchez","DEF","Galatasaray","Süper Lig",27,74,4,192),
    ("William Tesillo","DEF","Club León","Liga MX",34,58,2,183),
    ("Juan Guillermo Cuadrado","MID","Inter Milan","Serie A",36,104,12,176),
    ("Jefferson Lerma","MID","Crystal Palace","Premier League",29,82,3,181),
    ("Wilmar Barrios","MID","Zenit","Russian Premier League",30,78,2,183),
    ("Mateus Uribe","MID","Porto","Primeira Liga",32,74,8,178),
    ("Juan Fernando Quintero","MID","Racing Club","Liga Profesional",31,48,7,175),
    ("Gustavo Cuéllar","MID","Al-Hilal","Saudi Pro League",30,48,2,180),
    ("James Rodríguez","MID","Rayo Vallecano","La Liga",33,100,26,180),
    ("Luis Díaz","FWD","Liverpool","Premier League",27,56,18,180),
    ("Rafael Santos Borré","FWD","Eintracht Frankfurt","Bundesliga",28,62,20,178),
    ("Miguel Ángel Borja","FWD","River Plate","Liga Profesional",31,52,20,187),
    ("Jhon Durán","FWD","Aston Villa","Premier League",21,18,5,183),
    ("Cucho Hernández","FWD","Columbus Crew","MLS",25,32,8,183),
    ("Jhon Córdoba","FWD","Krasnodar","Russian Premier League",30,32,9,187),
    ("Falcao García","FWD","Rayo Vallecano","La Liga",38,109,36,177),
    ("Lerma Daniel","MID","Real Betis","La Liga",27,30,2,183),
    ("Daniel Muñoz","DEF","Crystal Palace","Premier League",27,38,3,180),
    ("Jorge Carrascal","MID","Dynamo Kyiv","Ukrainian Premier",26,18,3,178),
    ("Carlos Cuesta","DEF","Genk","Jupiler Pro League",25,18,1,188),
    ("Edier Ocampo","FWD","Deportivo Cali","Liga BetPlay",26,10,2,175),
]
for p in colombia:
    r = add_player("Colombia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── URUGUAY ────────────────────────────────────────────────────────────────
uruguay = [
    ("Fernando Muslera","GK","Galatasaray","Süper Lig",37,138,0,190),
    ("Sebastián Sosa","GK","Independiente","Primera División",36,12,0,185),
    ("Guillermo De Amores","GK","Montevideo City Torque","Uruguayan Primera",28,8,0,188),
    ("Martín Cáceres","DEF","LA Galaxy","MLS",36,118,5,181),
    ("Diego Godín","DEF","Vélez Sarsfield","Liga Profesional",38,160,16,186),
    ("José María Giménez","DEF","Atlético Madrid","La Liga",29,72,3,188),
    ("Ronald Araújo","DEF","Barcelona","La Liga",25,48,4,188),
    ("Matías Viña","DEF","Sassuolo","Serie A",26,40,3,179),
    ("Guillermo Varela","DEF","Flamengo","Série A",32,28,3,178),
    ("Mathías Olivera","DEF","Napoli","Serie A",26,42,2,181),
    ("Lucas Torreira","MID","Galatasaray","Süper Lig",28,62,5,175),
    ("Rodrigo Bentancur","MID","Tottenham","Premier League",27,64,6,187),
    ("Federico Valverde","MID","Real Madrid","La Liga",25,62,14,182),
    ("Giorgian De Arrascaeta","MID","Flamengo","Série A",30,68,16,173),
    ("Manuel Ugarte","MID","Manchester United","Premier League",23,32,1,179),
    ("Nicolás De La Cruz","MID","River Plate","Liga Profesional",27,42,6,173),
    ("Diego Forlan","FWD","Retired","",45,112,36,178),
    ("Darwin Núñez","FWD","Liverpool","Premier League",25,52,18,187),
    ("Luis Suárez","FWD","Grêmio","Série A",37,142,68,182),
    ("Edinson Cavani","FWD","Boca Juniors","Liga Profesional",37,136,58,184),
    ("Facundo Torres","FWD","Orlando City","MLS",25,28,8,178),
    ("Maximiliano Gómez","FWD","Sporting CP","Primeira Liga",27,28,7,183),
    ("Brian Ocampo","FWD","Cádiz","La Liga",24,12,2,175),
    ("Agustín Canobbio","FWD","Athletico Paranaense","Série A",25,18,4,175),
    ("Emiliano Martínez","MID","Peñarol","Uruguayan Primera",25,8,1,178),
    ("Nicolás Fonseca","MID","River Plate","Liga Profesional",27,14,2,180),
]
for p in uruguay:
    r = add_player("Uruguay", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── DENMARK ────────────────────────────────────────────────────────────────
denmark = [
    ("Kasper Schmeichel","GK","Anderlecht","Pro League",37,104,0,189),
    ("Oliver Christensen","GK","Hertha BSC","2. Bundesliga",25,12,0,188),
    ("Frederik Rønnow","GK","Union Berlin","Bundesliga",31,18,0,190),
    ("Joachim Andersen","DEF","Crystal Palace","Premier League",28,42,3,193),
    ("Simon Kjær","DEF","AC Milan","Serie A",35,142,9,190),
    ("Andreas Christensen","DEF","Barcelona","La Liga",28,62,3,185),
    ("Jannik Vestergaard","DEF","Leicester City","EFL Championship",32,58,7,196),
    ("Jens Stryger Larsen","DEF","Trabzonspor","Süper Lig",32,72,4,180),
    ("Joakim Mæhle","DEF","Atalanta","Serie A",27,52,6,182),
    ("Alexander Bah","DEF","Benfica","Primeira Liga",26,22,2,182),
    ("Pierre-Emile Höjbjerg","MID","Atlético Madrid","La Liga",28,92,9,186),
    ("Thomas Delaney","MID","Anderlecht","Pro League",32,82,6,183),
    ("Christian Eriksen","MID","Manchester United","Premier League",32,130,42,182),
    ("Mathias Jensen","MID","Brentford","Premier League",28,38,3,180),
    ("Mikkel Damsgaard","MID","Brentford","Premier League",24,32,5,181),
    ("Daniel Wass","MID","Vejle BK","Danish Superliga",35,82,7,180),
    ("Martin Braithwaite","FWD","Español","La Liga",33,82,24,176),
    ("Kasper Dolberg","FWD","Anderlecht","Pro League",26,38,11,187),
    ("Jonas Wind","FWD","Wolfsburg","Bundesliga",25,28,8,188),
    ("Andreas Skov Olsen","FWD","Club Brugge","Pro League",24,28,6,179),
    ("Rasmus Højlund","FWD","Manchester United","Premier League",22,22,10,192),
    ("Lasse Schöne","MID","Retired","",38,72,12,177),
    ("Viktor Gyökeres","FWD","Sporting CP","Primeira Liga",26,22,8,188),
    ("Yussuf Poulsen","FWD","RB Leipzig","Bundesliga",30,70,16,194),
    ("Gustav Isaksen","FWD","Lazio","Serie A",23,14,3,181),
    ("Morten Hjulmand","MID","Sporting CP","Primeira Liga",25,28,2,185),
]
for p in denmark:
    r = add_player("Denmark", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── PORTUGAL ────────────────────────────────────────────────────────────────
portugal = [
    ("Diogo Costa","GK","Porto","Primeira Liga",25,22,0,190),
    ("Rui Patrício","GK","Roma","Serie A",36,105,0,190),
    ("José Sá","GK","Wolves","Premier League",31,5,0,190),
    ("Nélson Semedo","DEF","Wolves","Premier League",30,40,2,177),
    ("João Cancelo","DEF","Barcelona","La Liga",30,58,5,182),
    ("Rúben Dias","DEF","Manchester City","Premier League",27,66,7,187),
    ("Pepe","DEF","Porto","Primeira Liga",41,144,8,187),
    ("Raphaël Guerreiro","DEF","Bayern Munich","Bundesliga",31,72,10,170),
    ("Nuno Mendes","DEF","PSG","Ligue 1",22,22,1,178),
    ("Danilo Pereira","MID","PSG","Ligue 1",32,66,4,186),
    ("João Palhinha","MID","Bayern Munich","Bundesliga",28,42,3,187),
    ("Rúben Neves","MID","Al-Hilal","Saudi Pro League",27,62,6,182),
    ("Vitinha","MID","PSG","Ligue 1",24,32,4,169),
    ("Bruno Fernandes","MID","Manchester United","Premier League",30,82,22,180),
    ("Bernardo Silva","MID","Manchester City","Premier League",30,90,22,173),
    ("João Félix","FWD","Barcelona","La Liga",24,44,11,181),
    ("Pedro Neto","FWD","Chelsea","Premier League",24,24,5,173),
    ("Rafael Leão","FWD","AC Milan","Serie A",25,38,12,188),
    ("Gonçalo Ramos","FWD","PSG","Ligue 1",23,22,10,187),
    ("André Silva","FWD","RB Leipzig","Bundesliga",29,70,26,187),
    ("Diogo Jota","FWD","Liverpool","Premier League",28,52,16,178),
    ("Cristiano Ronaldo","FWD","Al-Nassr","Saudi Pro League",39,208,130,187),
    ("Bruma","FWD","Panathinaikos","Super League Greece",29,22,3,175),
    ("Gonçalo Guedes","FWD","Wolves","Premier League",27,40,11,177),
    ("Matheus Nunes","MID","Manchester City","Premier League",26,22,2,180),
    ("Otávio","MID","Al-Nassr","Saudi Pro League",29,32,5,172),
]
for p in portugal:
    r = add_player("Portugal", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── NETHERLANDS ────────────────────────────────────────────────────────────
netherlands = [
    ("Bart Verbruggen","GK","Brighton","Premier League",22,12,0,190),
    ("Jasper Cillessen","GK","NEC Nijmegen","Eredivisie",35,64,0,186),
    ("Mark Flekken","GK","Brentford","Premier League",30,8,0,194),
    ("Jurriën Timber","DEF","Arsenal","Premier League",23,18,1,183),
    ("Matthijs de Ligt","DEF","Bayern Munich","Bundesliga",25,52,5,188),
    ("Virgil van Dijk","DEF","Liverpool","Premier League",33,68,8,193),
    ("Nathan Aké","DEF","Manchester City","Premier League",29,42,3,180),
    ("Daley Blind","DEF","Girona","La Liga",34,100,7,180),
    ("Denzel Dumfries","DEF","Inter Milan","Serie A",28,58,12,187),
    ("Tyrell Malacia","DEF","Manchester United","Premier League",25,12,0,167),
    ("Marten de Roon","MID","Atalanta","Serie A",33,50,5,186),
    ("Frenkie de Jong","MID","Barcelona","La Liga",27,68,5,180),
    ("Davy Klaassen","MID","Inter Milan","Serie A",31,62,12,182),
    ("Georginio Wijnaldum","MID","Al-Ettifaq","Saudi Pro League",33,92,26,175),
    ("Teun Koopmeiners","MID","Juventus","Serie A",26,32,10,183),
    ("Ryan Gravenberch","MID","Liverpool","Premier League",22,14,2,187),
    ("Cody Gakpo","FWD","Liverpool","Premier League",25,48,16,189),
    ("Memphis Depay","FWD","Atlético Madrid","La Liga",30,102,46,175),
    ("Donyell Malen","FWD","Dortmund","Bundesliga",25,40,10,178),
    ("Steven Bergwijn","FWD","Ajax","Eredivisie",26,38,10,175),
    ("Wout Weghorst","FWD","Hoffenheim","Bundesliga",32,52,14,197),
    ("Vincent Janssen","FWD","Royal Antwerp","Pro League",30,44,11,189),
    ("Noa Lang","FWD","PSV","Eredivisie",25,14,4,175),
    ("Tijjani Reijnders","MID","AC Milan","Serie A",26,22,3,184),
    ("Joshua Zirkzee","FWD","Manchester United","Premier League",23,8,3,193),
    ("Ian Maatsen","DEF","Chelsea","Premier League",22,6,1,173),
]
for p in netherlands:
    r = add_player("Netherlands", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── BELGIUM ────────────────────────────────────────────────────────────────
belgium = [
    ("Thibaut Courtois","GK","Real Madrid","La Liga",32,104,0,200),
    ("Koen Casteels","GK","Al-Qadsiah","Saudi Pro League",32,24,0,196),
    ("Matz Sels","GK","Nottm Forest","Premier League",32,12,0,187),
    ("Thomas Meunier","DEF","Trabzonspor","Süper Lig",32,78,6,187),
    ("Jan Vertonghen","DEF","Anderlecht","Pro League",37,152,9,189),
    ("Toby Alderweireld","DEF","Royal Antwerp","Pro League",35,130,5,187),
    ("Jason Denayer","DEF","Unattached","",28,38,3,185),
    ("Timothy Castagne","DEF","Fulham","Premier League",28,42,4,183),
    ("Arthur Theate","DEF","Stade Rennais","Ligue 1",24,18,2,188),
    ("Zeno Debast","DEF","Anderlecht","Pro League",20,14,1,189),
    ("Axel Witsel","MID","Atlético Madrid","La Liga",35,134,10,184),
    ("Youri Tielemans","MID","Aston Villa","Premier League",27,82,22,176),
    ("Kevin De Bruyne","MID","Manchester City","Premier League",33,106,26,181),
    ("Hans Vanaken","MID","Club Brugge","Pro League",31,52,11,190),
    ("Thorgan Hazard","MID","PSG","Ligue 1",31,52,16,175),
    ("Amadou Onana","MID","Everton","Premier League",23,18,1,196),
    ("Eden Hazard","FWD","Retired","",33,126,33,175),
    ("Dries Mertens","FWD","Galatasaray","Süper Lig",37,109,21,169),
    ("Michy Batshuayi","FWD","Fenerbahce","Süper Lig",31,42,26,186),
    ("Romelu Lukaku","FWD","Roma","Serie A",31,110,76,190),
    ("Lois Openda","FWD","RB Leipzig","Bundesliga",24,18,8,180),
    ("Leandro Trossard","FWD","Arsenal","Premier League",29,42,13,173),
    ("Charles De Ketelaere","FWD","Atalanta","Serie A",23,24,5,183),
    ("Johan Bakayoko","FWD","PSV","Eredivisie",22,10,3,183),
    ("Aster Vranckx","MID","Wolfsburg","Bundesliga",21,6,1,180),
    ("Jeremy Doku","FWD","Manchester City","Premier League",22,22,4,173),
]
for p in belgium:
    r = add_player("Belgium", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

conn.commit()
print(f"Total added in step 2: {total}")

# Final counts
print("\nFinal player counts:")
rows = conn.execute("""
    SELECT t.name, COUNT(p.id) as cnt
    FROM teams t LEFT JOIN players p ON t.id = p.team_id
    GROUP BY t.id ORDER BY cnt ASC
""").fetchall()
for r in rows:
    flag = " ⚠" if r[1] < 20 else ""
    print(f"  {r[1]:3d}  {r[0]}{flag}")
