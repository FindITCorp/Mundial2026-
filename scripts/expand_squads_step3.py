#!/usr/bin/env python3
"""Step 3: Top up remaining teams under 26 players."""
import sqlite3
from pathlib import Path

DB = Path("/home/user/mundial2026/data/mundial2026.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

teams = {r['name']: r['id'] for r in conn.execute("SELECT id, name FROM teams").fetchall()}
existing_players = set()
for r in conn.execute("SELECT LOWER(name), team_id FROM players").fetchall():
    existing_players.add((r[0], r[1]))

def add_player(team_name, name, position, club='', league='', age=None, caps=0, goals=0, height=None):
    name = name.strip()
    if not name or len(name) < 2: return False
    tid = teams.get(team_name)
    if not tid: return False
    pos_map = {
        'GK':'GK','DF':'DEF','MF':'MID','FW':'FWD',
        'DEF':'DEF','MID':'MID','FWD':'FWD',
        'CB':'DEF','LB':'DEF','RB':'DEF','LWB':'DEF','RWB':'DEF',
        'CM':'MID','DM':'MID','AM':'MID',
        'CF':'FWD','ST':'FWD','LW':'FWD','RW':'FWD',
    }
    pos = pos_map.get(position.upper()[:3], 'MID')
    if (name.lower(), tid) in existing_players: return False
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO players (name, team_id, position, club, club_league, age, caps, goals_as_nat, height_cm)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (name, tid, pos, club or '', league or '', age, caps or 0, goals or 0, height))
        if cur.rowcount:
            pid = cur.lastrowid
            conn.execute("INSERT OR IGNORE INTO squad_selections (team_id, player_id, confirmed) VALUES (?,?,1)", (tid, pid))
            existing_players.add((name.lower(), tid))
            return True
    except Exception as e:
        print(f"  Error {name}: {e}")
    return False

total = 0

# ── EGYPT ──────────────────────────────────────────────────────────────────
egypt = [
    ("Mohamed Elshenawy","GK","Al-Ahly","Egyptian Premier League",35,52,0,190),
    ("Ahmed El-Shenawy","GK","Al-Ahly","Egyptian Premier League",34,18,0,188),
    ("Mohamed Abou Gabal","GK","Zamalek","Egyptian Premier League",32,22,0,192),
    ("Ahmed Hegazi","DEF","Al-Ittihad","Saudi Pro League",33,92,12,194),
    ("Omar Kamal","DEF","Al-Ahly","Egyptian Premier League",26,22,1,183),
    ("Ayman Ashraf","DEF","Al-Ahly","Egyptian Premier League",28,38,2,181),
    ("Ahmed Fatouh","DEF","Pyramids FC","Egyptian Premier League",27,18,1,183),
    ("Mohamed Abdel-Moneim","DEF","Al-Ahly","Egyptian Premier League",29,28,2,185),
    ("Akram Tawfik","DEF","Pyramids FC","Egyptian Premier League",28,22,1,178),
    ("Hamdy Fathy","MID","Al-Ittihad","Saudi Pro League",30,48,5,178),
    ("Tarek Hamed","MID","Pyramids FC","Egyptian Premier League",34,64,2,183),
    ("Amr El-Sulaya","MID","Pyramids FC","Egyptian Premier League",30,38,5,178),
    ("Omar Marmoush","FWD","Eintracht Frankfurt","Bundesliga",25,28,14,178),
    ("Mostafa Mohamed","FWD","Galatasaray","Süper Lig",26,42,18,188),
    ("Ramy Rabia","MID","Al-Ahly","Egyptian Premier League",25,18,3,175),
    ("Emam Ashour","MID","Al-Ahly","Egyptian Premier League",28,32,4,178),
    ("Zizo","MID","Zamalek","Egyptian Premier League",32,52,10,172),
    ("Nasser Maher","MID","Al-Ahly","Egyptian Premier League",26,22,2,178),
    ("Mohamed Sherif","FWD","Benfica","Primeira Liga",26,28,8,188),
    ("Marwan Hamdy","FWD","Al-Ahly","Egyptian Premier League",24,12,4,178),
    ("Mahmoud Trezeguet","FWD","Istanbul Basaksehir","Süper Lig",30,72,21,178),
    ("Kahraba","FWD","Al-Ittihad","Saudi Pro League",30,42,14,172),
    ("Salah Mohsen","FWD","Al-Ahly","Egyptian Premier League",26,28,6,183),
    ("Said Mohamed","MID","Zamalek","Egyptian Premier League",28,18,3,175),
    ("Amr Warda","FWD","PAOK","Super League Greece",30,38,11,172),
    ("Mohamed Salah","FWD","Liverpool","Premier League",32,98,55,175),
]
for p in egypt:
    r = add_player("Egypt", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── BOLIVIA ────────────────────────────────────────────────────────────────
bolivia = [
    ("Carlos Lampe","GK","Bolívar","Bolivian División Profesional",37,82,0,188),
    ("Guillermo Viscarra","GK","The Strongest","Bolivian División Profesional",33,42,0,185),
    ("Mario Martínez","GK","Bolívar","Bolivian División Profesional",28,8,0,183),
    ("Luis Haquin","DEF","Bolívar","Bolivian División Profesional",28,38,2,185),
    ("José Carrasco","DEF","The Strongest","Bolivian División Profesional",30,42,3,183),
    ("Pablo Escobar","DEF","Bolívar","Bolivian División Profesional",32,58,3,180),
    ("Adrián Jusino","DEF","FC Emmen","Eredivisie",26,28,1,185),
    ("Sebastián Reyes","DEF","The Strongest","Bolivian División Profesional",27,22,2,178),
    ("Henry Vaca","MID","Bolívar","Bolivian División Profesional",30,52,8,175),
    ("Ramiro Vaca","MID","Bolívar","Bolivian División Profesional",32,68,10,175),
    ("Erwin Saavedra","MID","The Strongest","Bolivian División Profesional",28,38,5,180),
    ("Jeyson Chura","MID","Always Ready","Bolivian División Profesional",26,22,3,175),
    ("Fernando Saucedo","FWD","Bolívar","Bolivian División Profesional",26,32,8,183),
    ("Juan Apaza","FWD","Bolívar","Bolivian División Profesional",27,28,6,180),
    ("Rodrigo Ramallo","FWD","Bolívar","Bolivian División Profesional",29,62,18,178),
    ("Marcelo Moreno","FWD","Cruzeiro","Série A",37,100,28,188),
    ("Bruno Miranda","FWD","Unattached","",30,42,10,186),
    ("Carmelo Algarañaz","FWD","Always Ready","Bolivian División Profesional",28,18,5,175),
    ("Víctor Ábrego","DEF","Always Ready","Bolivian División Profesional",29,18,1,180),
    ("Roberto Fernández","MID","The Strongest","Bolivian División Profesional",26,12,2,178),
    ("Leonel Justiniano","DEF","Santa Cruz FC","Bolivian División Profesional",27,8,0,185),
    ("Nelson Cabrera","MID","Bolívar","Bolivian División Profesional",25,8,1,178),
]
for p in bolivia:
    r = add_player("Bolivia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── CAMEROON ──────────────────────────────────────────────────────────────
cameroon = [
    ("André Onana","GK","Manchester United","Premier League",28,52,0,190),
    ("Devis Epassy","GK","Abha Club","Saudi Pro League",30,18,0,185),
    ("Simon Omossola","GK","Yverdon","Swiss Challenge League",26,5,0,187),
    ("Enzo Ebosse","DEF","Udinese","Serie A",26,18,1,182),
    ("Nouhou Tolo","DEF","Seattle Sounders","MLS",28,38,2,178),
    ("Jean-Charles Castelletto","DEF","Nantes","Ligue 1",30,28,2,188),
    ("Ambroise Oyongo","DEF","Montpellier","Ligue 1",32,58,3,183),
    ("Collins Fai","DEF","Standard Liège","Pro League",33,48,4,176),
    ("Harold Moukoudi","DEF","Standard Liège","Pro League",27,22,1,188),
    ("Olivier Mbaizo","DEF","Philadelphia Union","MLS",27,18,2,175),
    ("André-Frank Zambo Anguissa","MID","Napoli","Serie A",28,62,5,185),
    ("Samuel Gouet","MID","Mechelen","Pro League",26,28,2,183),
    ("Martin Hongla","MID","Hellas Verona","Serie A",26,22,2,183),
    ("Ibrahim Amadou","MID","Nice","Ligue 1",31,38,1,186),
    ("Pierre Kunde","MID","Mainz","Bundesliga",28,32,2,183),
    ("Nicolas Moumi Ngamaleu","MID","Young Boys","Swiss Super League",30,38,5,178),
    ("Jean-Pierre Nsame","FWD","Young Boys","Swiss Super League",31,32,8,185),
    ("Karl Toko Ekambi","FWD","Lyon","Ligue 1",31,62,19,183),
    ("Vincent Aboubakar","FWD","Besiktas","Süper Lig",32,106,36,184),
    ("Stéphane Bahoken","FWD","Angers","Ligue 2",33,14,3,186),
    ("Georges-Kévin Nkoudou","FWD","Besiktas","Süper Lig",28,18,3,177),
    ("Moumi Ngamaleu","MID","Young Boys","Swiss Super League",30,38,5,178),
    ("Clinton Njie","FWD","Olympique Marseille","Ligue 1",31,42,10,173),
    ("Gael Ondoua","MID","Hannover 96","2. Bundesliga",28,22,2,183),
    ("Jérôme Onguéné","DEF","RB Salzburg","Austrian Bundesliga",26,12,1,186),
    ("Bryan Mbeumo","FWD","Brentford","Premier League",25,22,8,173),
]
for p in cameroon:
    r = add_player("Cameroon", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── IRAN ──────────────────────────────────────────────────────────────────
iran_extra = [
    ("Alireza Beiranvand","GK","Persepolis","Persian Gulf Pro League",32,62,0,194),
    ("Payam Niazmand","GK","Persepolis","Persian Gulf Pro League",28,12,0,190),
    ("Hossein Hosseini","GK","Esteghlal","Persian Gulf Pro League",30,8,0,185),
    ("Shoja Khalilzadeh","DEF","Al-Qadsiah","Saudi Pro League",32,62,4,182),
    ("Majid Hosseini","DEF","Kasimpasa","Süper Lig",26,38,2,188),
    ("Milad Mohammadi","DEF","AEK Athens","Super League Greece",30,68,4,182),
    ("Ramin Rezaeian","DEF","Sepahan","Persian Gulf Pro League",34,72,5,180),
    ("Hossein Kanaanizadegan","DEF","Nottm Forest","Premier League",27,22,1,181),
    ("Morteza Pouraliganji","DEF","Al-Sadd","Qatar Stars League",33,52,4,190),
    ("Abolfazl Jalali","DEF","Esteghlal","Persian Gulf Pro League",28,22,1,183),
    ("Saeid Ezatolahi","MID","Vejle","Danish Superliga",28,58,4,183),
    ("Saman Ghoddos","MID","Brentford","Premier League",30,52,8,181),
    ("Ali Gholizadeh","FWD","Charleroi","Pro League",27,38,8,175),
    ("Sardar Azmoun","FWD","Bayer Leverkusen","Bundesliga",29,68,44,188),
    ("Mehdi Taremi","FWD","Inter Milan","Serie A",32,82,46,187),
    ("Allahyar Sayyadmanesh","FWD","Hull City","EFL Championship",23,22,6,183),
    ("Kaveh Rezaei","FWD","Anderlecht","Pro League",32,38,12,185),
    ("Ahmad Noorollahi","MID","Persepolis","Persian Gulf Pro League",30,48,5,180),
    ("Ali Karimi","MID","Persepolis","Persian Gulf Pro League",28,28,3,178),
    ("Omid Ebrahimi","MID","Vancouver Whitecaps","MLS",34,82,5,183),
    ("Karim Ansarifard","FWD","Persepolis","Persian Gulf Pro League",33,108,30,185),
]
for p in iran_extra:
    r = add_player("Iran", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SAUDI ARABIA ──────────────────────────────────────────────────────────
saudi = [
    ("Mohammed Al-Owais","GK","Al-Hilal","Saudi Pro League",32,62,0,190),
    ("Nawaf Al-Aqidi","GK","Al-Nassr","Saudi Pro League",26,12,0,187),
    ("Yasser Al-Mosailem","GK","Al-Shabab","Saudi Pro League",30,18,0,188),
    ("Ali Al-Bulaihi","DEF","Al-Hilal","Saudi Pro League",34,82,6,186),
    ("Mohammed Al-Burayk","DEF","Al-Hilal","Saudi Pro League",32,72,5,179),
    ("Abdulelah Al-Amri","DEF","Al-Hilal","Saudi Pro League",28,42,2,182),
    ("Hassan Al-Tambakti","DEF","Al-Hilal","Saudi Pro League",26,28,2,191),
    ("Saud Abdulhamid","DEF","Al-Hilal","Saudi Pro League",24,18,1,176),
    ("Sultan Al-Ghannam","DEF","Al-Nassr","Saudi Pro League",28,22,1,180),
    ("Nawaf Al-Abed","MID","Al-Hilal","Saudi Pro League",33,72,10,175),
    ("Salem Al-Dawsari","MID","Al-Hilal","Saudi Pro League",32,82,22,173),
    ("Mohamed Kanno","MID","Al-Hilal","Saudi Pro League",29,52,4,185),
    ("Riyadh Sharahili","MID","Al-Hilal","Saudi Pro League",30,38,5,178),
    ("Haitham Asiri","MID","Al-Ahli","Saudi Pro League",28,22,3,175),
    ("Abdulrahman Ghareeb","FWD","Al-Hilal","Saudi Pro League",29,48,12,175),
    ("Firas Al-Buraikan","FWD","Al-Fateh","Saudi Pro League",24,32,8,183),
    ("Khalid Al-Ghannam","FWD","Al-Nassr","Saudi Pro League",26,22,6,180),
    ("Abdullah Al-Hamdan","FWD","Al-Hilal","Saudi Pro League",25,22,5,185),
    ("Turki Al-Ammar","FWD","Al-Qadsiah","Saudi Pro League",26,12,3,178),
]
for p in saudi:
    r = add_player("Saudi Arabia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── IRAQ ──────────────────────────────────────────────────────────────────
iraq = [
    ("Jalal Hassan","GK","Al-Shorta","Iraqi Premier League",35,72,0,186),
    ("Dhurgham Ismael","GK","Al-Zawraa","Iraqi Premier League",28,18,0,183),
    ("Saad Natiq","GK","Al-Quwa Al-Jawiya","Iraqi Premier League",26,8,0,185),
    ("Ali Adnan","DEF","Kayserispor","Süper Lig",30,82,6,180),
    ("Rebin Sulaka","DEF","Duhok","Iraqi Premier League",28,32,2,183),
    ("Hussein Ali","DEF","Al-Shorta","Iraqi Premier League",27,42,3,183),
    ("Mustafa Nadhim","DEF","Al-Zawraa","Iraqi Premier League",26,22,1,180),
    ("Amjad Attwan","DEF","Al-Quwa Al-Jawiya","Iraqi Premier League",30,38,2,178),
    ("Ibrahim Bayesh","MID","Al-Shorta","Iraqi Premier League",28,48,5,178),
    ("Safaa Hadi","MID","Al-Zawraa","Iraqi Premier League",30,62,8,175),
    ("Alaa Abbas","MID","Basra SC","Iraqi Premier League",28,32,4,180),
    ("Mohammed Karrar","MID","Al-Zawraa","Iraqi Premier League",26,22,3,178),
    ("Mohanad Ali","FWD","Al-Shorta","Iraqi Premier League",28,52,18,180),
    ("Ahmed Yasin","MID","Al-Quwa Al-Jawiya","Iraqi Premier League",30,72,10,175),
    ("Aymen Hussein","FWD","Al-Zawraa","Iraqi Premier League",28,62,22,183),
    ("Hammadi Ahmed","FWD","Al-Shorta","Iraqi Premier League",30,42,12,185),
    ("Bassam Juma","FWD","Al-Quwa Al-Jawiya","Iraqi Premier League",26,28,8,178),
    ("Thaer Krouma","FWD","Erbil SC","Iraqi Premier League",28,32,9,183),
]
for p in iraq:
    r = add_player("Iraq", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── JORDAN ────────────────────────────────────────────────────────────────
jordan = [
    ("Amer Shafi","GK","Al-Wehdat","Jordanian Premier League",38,102,0,189),
    ("Rami Hamadeh","GK","Al-Faisaly","Jordanian Premier League",28,12,0,185),
    ("Zaid Abu Laila","GK","Al-Jazeera","Jordanian Premier League",26,5,0,183),
    ("Yazan Al-Naimat","DEF","Al-Wehdat","Jordanian Premier League",28,42,3,183),
    ("Baha' Faisal","DEF","Al-Faisaly","Jordanian Premier League",30,52,4,180),
    ("Ahmad Ibrahim","DEF","Al-Wehdat","Jordanian Premier League",27,38,2,185),
    ("Omar Al-Dameek","DEF","Al-Ahli","Saudi Pro League",28,32,2,182),
    ("Ahmad Saleh","DEF","Al-Wehdat","Jordanian Premier League",26,22,1,180),
    ("Sanad Naser","MID","Al-Wehdat","Jordanian Premier League",28,48,5,178),
    ("Musa Al-Taamari","MID","Montpellier","Ligue 1",27,52,8,175),
    ("Yazan Al-Arab","MID","Al-Faisaly","Jordanian Premier League",26,28,3,178),
    ("Nour Al-Rawabdeh","MID","Al-Wehdat","Jordanian Premier League",28,38,4,183),
    ("Hamza Al-Dardour","FWD","Al-Ramtha","Jordanian Premier League",32,82,28,183),
    ("Ahmad Hayel","FWD","Al-Wehdat","Jordanian Premier League",26,28,6,180),
    ("Moussa Al-Taamari","FWD","Montpellier","Ligue 1",27,52,8,175),
    ("Yousef Al-Rawashdeh","FWD","Al-Faisaly","Jordanian Premier League",26,18,4,178),
    ("Mohammad Abu Zema","FWD","Al-Wehdat","Jordanian Premier League",24,12,3,183),
    ("Baha Abdel Rahman","MID","Al-Jazeera","Jordanian Premier League",28,32,5,178),
]
for p in jordan:
    r = add_player("Jordan", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── PARAGUAY ──────────────────────────────────────────────────────────────
paraguay = [
    ("Antony Silva","GK","Olimpia","Paraguayan Primera División",39,102,0,183),
    ("Alfredo Aguilar","GK","Olimpia","Paraguayan Primera División",28,12,0,185),
    ("Rodrigo Muñoz","GK","Colorado Rapids","MLS",30,18,0,188),
    ("Junior Alonso","DEF","Atletico Mineiro","Série A",30,42,3,190),
    ("Robert Morales","DEF","Olimpia","Paraguayan Primera División",28,32,2,183),
    ("Fabián Balbuena","DEF","Dinamo Moscow","Russian Premier League",32,68,5,186),
    ("Gustavo Gómez","DEF","Palmeiras","Série A",31,72,12,187),
    ("Santiago Arzamendia","DEF","Athletico Paranaense","Série A",25,32,2,178),
    ("Omar Alderete","DEF","Hertha BSC","Bundesliga",26,32,2,186),
    ("Jorge Morel","MID","Olimpia","Paraguayan Primera División",28,38,4,178),
    ("Mathías Villasanti","MID","Grêmio","Série A",26,22,2,183),
    ("Miguel Almirón","MID","Newcastle","Premier League",30,86,14,174),
    ("Ángel Romero","FWD","Corinthians","Série A",30,78,18,173),
    ("Cecilio Domínguez","FWD","Independiente","Primera División",30,58,15,175),
    ("Iván Piris","DEF","Flamengo","Série A",28,18,1,178),
    ("Hernán Pérez","MID","Olimpia","Paraguayan Primera División",34,78,15,178),
    ("Fernando Cardozo","FWD","Olimpia","Paraguayan Primera División",28,32,8,183),
    ("Antonio Sanabria","FWD","Torino","Serie A",27,56,16,185),
]
for p in paraguay:
    r = add_player("Paraguay", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── JAMAICA ───────────────────────────────────────────────────────────────
jamaica = [
    ("Andre Blake","GK","Philadelphia Union","MLS",33,72,0,193),
    ("Daniel Russell","GK","Dunbeholden FC","Jamaica Premier League",28,8,0,186),
    ("Dillon Barnes","GK","Queens Park Rangers","EFL Championship",29,12,0,188),
    ("Damion Lowe","DEF","Inter Miami","MLS",31,58,3,191),
    ("Adrian Mariappa","DEF","Retired","",37,102,3,181),
    ("Oniel Fisher","DEF","DC United","MLS",29,42,3,178),
    ("Kemar Lawrence","DEF","NY Red Bulls","MLS",31,68,5,175),
    ("Javain Brown","DEF","Watford","EFL Championship",25,18,1,178),
    ("Ethan Pinnock","DEF","Brentford","Premier League",30,18,2,192),
    ("Dexter Lembikisa","DEF","Wolves","Premier League",21,4,0,176),
    ("Je-Vaughn Watson","MID","New England Revolution","MLS",33,78,8,175),
    ("Demarai Gray","FWD","Everton","Premier League",28,12,2,176),
    ("Shamar Nicholson","FWD","Charleroi","Pro League",26,32,12,183),
    ("Leon Bailey","FWD","Aston Villa","Premier League",27,40,14,176),
    ("Bobby Reid","MID","Fulham","Premier League",31,14,3,175),
    ("Daryl Dike","FWD","West Brom","EFL Championship",24,12,5,188),
    ("Michail Antonio","FWD","West Ham","Premier League",34,22,7,183),
    ("Daniel Johnson","MID","Preston North End","EFL Championship",33,38,8,177),
    ("Cory Burke","FWD","Colorado Rapids","MLS",30,28,7,183),
    ("Kasey Palmer","MID","Coventry City","EFL Championship",27,18,4,175),
    ("Ravel Morrison","MID","Unattached","",31,10,1,178),
]
for p in jamaica:
    r = add_player("Jamaica", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── AUSTRIA ───────────────────────────────────────────────────────────────
austria = [
    ("Patrick Pentz","GK","Real Betis","La Liga",27,12,0,189),
    ("Daniel Bachmann","GK","Watford","EFL Championship",30,18,0,193),
    ("Alexander Schlager","GK","LASK","Austrian Bundesliga",29,22,0,186),
    ("Stefan Lainer","DEF","Borussia Mönchengladbach","Bundesliga",31,52,3,172),
    ("Philipp Lienhart","DEF","Freiburg","Bundesliga",28,28,2,187),
    ("Aleksandar Dragovic","DEF","Red Bull Salzburg","Austrian Bundesliga",33,96,6,186),
    ("David Alaba","DEF","Real Madrid","La Liga",32,106,15,180),
    ("Andreas Ulmer","DEF","Red Bull Salzburg","Austrian Bundesliga",37,78,8,180),
    ("Gernot Trauner","DEF","Feyenoord","Eredivisie",31,32,3,185),
    ("Maximilian Wöber","DEF","Leeds United","EFL Championship",26,18,1,184),
    ("Florian Grillitsch","MID","Ajax","Eredivisie",28,42,4,189),
    ("Xaver Schlager","MID","RB Leipzig","Bundesliga",27,42,5,175),
    ("Konrad Laimer","MID","Bayern Munich","Bundesliga",27,38,4,174),
    ("Marcel Sabitzer","MID","Manchester United","Premier League",30,72,18,178),
    ("Louis Schaub","MID","Hamburger SV","2. Bundesliga",30,28,4,178),
    ("Nicolas Seiwald","MID","RB Leipzig","Bundesliga",22,18,1,178),
    ("Michael Gregoritsch","FWD","Freiburg","Bundesliga",30,52,20,192),
    ("Sasa Kalajdzic","FWD","Wolves","Premier League",27,28,12,200),
    ("Marko Arnautovic","FWD","Inter Milan","Serie A",35,108,36,192),
    ("Patrick Wimmer","FWD","Wolfsburg","Bundesliga",24,14,3,180),
    ("Christoph Baumgartner","MID","RB Leipzig","Bundesliga",24,22,5,178),
    ("Romano Schmid","MID","Werder Bremen","Bundesliga",24,14,3,178),
]
for p in austria:
    r = add_player("Austria", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SCOTLAND ──────────────────────────────────────────────────────────────
scotland = [
    ("Craig Gordon","GK","Heart of Midlothian","Scottish Premiership",41,72,0,191),
    ("Jon McLaughlin","GK","Rangers","Scottish Premiership",36,18,0,189),
    ("Liam Kelly","GK","Motherwell","Scottish Premiership",30,8,0,188),
    ("Andrew Robertson","DEF","Liverpool","Premier League",30,72,5,178),
    ("Kieran Tierney","DEF","Arsenal","Premier League",26,58,4,178),
    ("Grant Hanley","DEF","Norwich City","EFL Championship",32,52,3,187),
    ("Scott McKenna","DEF","Nottm Forest","Premier League",28,42,5,190),
    ("John Souttar","DEF","Rangers","Scottish Premiership",28,22,4,192),
    ("Aaron Hickey","DEF","Brentford","Premier League",22,14,2,178),
    ("Liam Cooper","DEF","Leeds United","EFL Championship",32,12,1,185),
    ("Callum McGregor","MID","Celtic","Scottish Premiership",31,62,8,176),
    ("Stuart Armstrong","MID","Southampton","Premier League",32,52,8,183),
    ("Billy Gilmour","MID","Brighton","Premier League",23,28,1,170),
    ("Ryan Jack","MID","Rangers","Scottish Premiership",32,38,3,180),
    ("Kenny McLean","MID","Norwich City","EFL Championship",31,48,6,183),
    ("John McGinn","MID","Aston Villa","Premier League",29,72,16,178),
    ("Ryan Christie","MID","Bournemouth","Premier League",29,52,11,175),
    ("Scott McTominay","MID","Manchester United","Premier League",27,42,8,188),
    ("Lawrence Shankland","FWD","Heart of Midlothian","Scottish Premiership",28,22,10,183),
    ("Che Adams","FWD","Southampton","Premier League",27,28,7,178),
    ("Lyndon Dykes","FWD","Queens Park Rangers","EFL Championship",28,38,14,187),
    ("Oli McBurnie","FWD","Sheffield United","Premier League",27,22,5,190),
]
for p in scotland:
    r = add_player("Scotland", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── DR CONGO ──────────────────────────────────────────────────────────────
drc = [
    ("Ley Matampi","GK","TP Mazembe","TP Mazembe",32,42,0,188),
    ("Joël Kiassumbua","GK","Charleroi","Pro League",32,28,0,190),
    ("Hervé Kanda","GK","AS Vita Club","Ligue nationale de football",28,8,0,186),
    ("Chancel Mbemba","DEF","Marseille","Ligue 1",30,62,5,185),
    ("Arthur Masuaku","DEF","Besiktas","Süper Lig",30,38,3,176),
    ("Marcel Tisserand","DEF","Fenerbahce","Süper Lig",30,52,4,188),
    ("Silas Katompa","DEF","Stuttgart","Bundesliga",24,18,2,182),
    ("Yannick Bolasie","FWD","Middlesbrough","EFL Championship",34,44,5,183),
    ("Cédric Bakambu","FWD","Olympique Marseille","Ligue 1",33,68,22,181),
    ("Dieumerci Mbokani","FWD","TP Mazembe","TP Mazembe",38,60,22,181),
    ("Britt Assombalonga","FWD","Adana Demirspor","Süper Lig",31,28,6,173),
    ("Jonathan Bolingi","FWD","Anderlecht","Pro League",30,32,6,186),
    ("Jordan Botaka","FWD","Sint-Truiden","Jupiler Pro League",30,22,3,175),
    ("Merveille Bope Bokadi","MID","Standard Liège","Pro League",28,32,5,176),
    ("Meschak Elia","FWD","Young Boys","Swiss Super League",23,12,4,178),
    ("Samuel Moutoussamy","MID","Nantes","Ligue 1",27,18,3,180),
    ("Fiston Mayele","FWD","Pyramids","Egyptian Premier League",27,22,8,183),
    ("Paul-José Mpoku","MID","Unattached","",32,54,10,178),
]
for p in drc:
    r = add_player("DR Congo", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── NIGERIA ───────────────────────────────────────────────────────────────
nigeria_extra = [
    ("Francis Uzoho","GK","Omonia Nicosia","Cypriot First Division",26,28,0,190),
    ("Daniel Akpeyi","GK","Kaizer Chiefs","South African Premier Division",37,38,0,186),
    ("John Noble","GK","Enugu Rangers","NPFL",28,5,0,185),
    ("Ola Aina","DEF","Nottm Forest","Premier League",28,48,2,178),
    ("Leon Balogun","DEF","Queens Park Rangers","EFL Championship",35,68,5,188),
    ("William Troost-Ekong","DEF","Watford","EFL Championship",30,78,6,191),
    ("Chidozie Awaziem","DEF","Coimbra","Liga Portugal 2",27,32,2,185),
    ("Tyronne Ebuehi","DEF","Venezia","Serie B",28,28,2,177),
    ("Calvin Bassey","DEF","Fulham","Premier League",24,22,1,185),
    ("Zaidu Sanusi","DEF","Porto","Primeira Liga",26,28,1,178),
    ("Alex Iwobi","MID","Fulham","Premier League",28,68,14,178),
    ("Wilfred Ndidi","MID","Leicester City","EFL Championship",27,72,4,183),
    ("Oghenekaro Etebo","MID","Getafe","La Liga",28,50,3,178),
    ("Joe Aribo","MID","Southampton","Premier League",28,32,5,182),
    ("Frank Onyeka","MID","Brentford","Premier League",26,28,3,186),
    ("Kelechi Iheanacho","FWD","Leicester City","EFL Championship",27,60,20,184),
    ("Emmanuel Dennis","FWD","Nottm Forest","Premier League",26,28,8,183),
    ("Terem Moffi","FWD","Nice","Ligue 1",25,22,8,183),
    ("Taiwo Awoniyi","FWD","Nottm Forest","Premier League",26,18,5,184),
    ("Paul Onuachu","FWD","Southampton","Premier League",30,22,12,202),
    ("Victor Osimhen","FWD","Napoli","Serie A",25,52,22,185),
    ("Samuel Chukwueze","FWD","AC Milan","Serie A",25,42,10,172),
]
for p in nigeria_extra:
    r = add_player("Nigeria", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── POLAND ────────────────────────────────────────────────────────────────
poland_extra = [
    ("Wojciech Szczęsny","GK","Barcelona","La Liga",34,82,0,196),
    ("Łukasz Fabiański","GK","West Ham","Premier League",39,62,0,190),
    ("Bartłomiej Drągowski","GK","Spezia","Serie A",26,12,0,190),
    ("Bartosz Bereszyński","DEF","Napoli","Serie A",31,52,2,181),
    ("Artur Jędrzejczyk","DEF","Legia Warsaw","PKO BP Ekstraklasa",36,82,3,183),
    ("Jan Bednarek","DEF","Aston Villa","Premier League",27,62,4,192),
    ("Tomasz Kędziora","DEF","Dynamo Kyiv","Ukrainian Premier",29,48,2,178),
    ("Tymoteusz Puchacz","DEF","Kaiserslautern","2. Bundesliga",24,22,2,183),
    ("Nicola Zalewski","MID","Roma","Serie A",22,18,3,183),
    ("Przemysław Frankowski","MID","Lens","Ligue 1",28,42,6,175),
    ("Jakub Moder","MID","Brighton","Premier League",25,24,3,183),
    ("Szymon Żurkowski","MID","Empoli","Serie A",26,22,3,185),
    ("Michał Skóraś","MID","Club Brugge","Pro League",23,10,2,180),
    ("Karol Świderski","FWD","Charlotte FC","MLS",27,38,14,182),
    ("Krzysztof Piątek","FWD","Salernitana","Serie A",28,32,12,184),
    ("Adam Buksa","FWD","RC Lens","Ligue 1",27,22,5,190),
    ("Arkadiusz Milik","FWD","Juventus","Serie A",30,68,22,188),
    ("Robert Lewandowski","FWD","Barcelona","La Liga",35,148,82,184),
]
for p in poland_extra:
    r = add_player("Poland", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── TURKEY ────────────────────────────────────────────────────────────────
turkey_extra = [
    ("Mert Günok","GK","Besiktas","Süper Lig",35,32,0,189),
    ("Uğurcan Çakır","GK","Trabzonspor","Süper Lig",27,22,0,190),
    ("Altay Bayındır","GK","Manchester United","Premier League",26,8,0,198),
    ("Zeki Çelik","DEF","Roma","Serie A",27,38,2,177),
    ("Merih Demiral","DEF","Al-Qadsiah","Saudi Pro League",25,38,5,188),
    ("Çağlar Söyüncü","DEF","Atlético Madrid","La Liga",27,52,4,185),
    ("Ferdi Kadıoğlu","DEF","Fenerbahce","Süper Lig",24,18,2,181),
    ("Ridvan Yilmaz","DEF","Besiktas","Süper Lig",23,14,1,178),
    ("Kaan Ayhan","DEF","Galatasaray","Süper Lig",29,52,3,185),
    ("Mert Müldür","DEF","Sassuolo","Serie A",25,18,1,181),
    ("Salih Özcan","MID","Dortmund","Bundesliga",26,22,2,183),
    ("İlkay Gündoğan","MID","Manchester City","Premier League",33,82,18,180),
    ("Orkun Kökçü","MID","Benfica","Primeira Liga",23,22,4,180),
    ("Okay Yokuşlu","MID","West Brom","EFL Championship",29,42,3,188),
    ("Yunus Akgün","FWD","Galatasaray","Süper Lig",24,14,4,178),
    ("Kerem Aktürkoğlu","FWD","Galatasaray","Süper Lig",25,28,8,175),
    ("Cenk Tosun","FWD","Besiktas","Süper Lig",33,72,31,186),
    ("Burak Yilmaz","FWD","Besiktas","Süper Lig",38,82,32,180),
    ("Baris Alper Yilmaz","FWD","Galatasaray","Süper Lig",24,14,3,183),
    ("Arda Güler","MID","Real Madrid","La Liga",19,18,5,175),
    ("Hakan Çalhanoğlu","MID","Inter Milan","Serie A",30,92,20,180),
]
for p in turkey_extra:
    r = add_player("Turkey", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SERBIA ────────────────────────────────────────────────────────────────
serbia_extra = [
    ("Predrag Rajković","GK","Real Mallorca","La Liga",28,42,0,191),
    ("Marko Dmitrović","GK","Sevilla","La Liga",31,22,0,194),
    ("Vanja Milinković-Savić","GK","Torino","Serie A",27,22,0,202),
    ("Stefan Mitrović","DEF","Getafe","La Liga",32,62,5,190),
    ("Milan Gajić","DEF","Frosinone","Serie A",28,28,2,180),
    ("Miloš Veljković","DEF","Werder Bremen","Bundesliga",28,32,3,190),
    ("Nikola Milenkovic","DEF","Nottm Forest","Premier League",26,52,6,193),
    ("Aleksandar Pavlović","MID","Bayern Munich","Bundesliga",20,8,1,185),
    ("Nemanja Gudelj","MID","Al-Nassr","Saudi Pro League",32,42,3,185),
    ("Nemanja Maksimović","MID","Getafe","La Liga",31,42,3,185),
    ("Sasa Lukic","MID","Fulham","Premier League",27,38,5,183),
    ("Andreja Živković","MID","Al-Qadsiah","Saudi Pro League",28,38,5,175),
    ("Dušan Tadić","MID","Fenerbahce","Süper Lig",35,108,22,175),
    ("Filip Kostić","MID","Juventus","Serie A",31,62,12,184),
    ("Luka Jović","FWD","Fiorentina","Serie A",26,40,14,183),
    ("Aleksandar Mitrović","FWD","Al-Hilal","Saudi Pro League",29,98,62,188),
    ("Dušan Vlahović","FWD","Juventus","Serie A",24,48,28,190),
    ("Dušan Tadić","MID","Fenerbahce","Süper Lig",35,108,22,175),
    ("Sergej Milinković-Savić","MID","Al-Hilal","Saudi Pro League",29,72,18,191),
]
for p in serbia_extra:
    r = add_player("Serbia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── AUSTRALIA ─────────────────────────────────────────────────────────────
australia_extra = [
    ("Mathew Ryan","GK","Real Sociedad","La Liga",32,78,0,184),
    ("Andrew Redmayne","GK","Sydney FC","A-League",35,8,0,196),
    ("Danny Vukovic","GK","Central Coast Mariners","A-League",38,14,0,184),
    ("Harry Souttar","DEF","Stoke City","EFL Championship",25,28,4,203),
    ("Miloš Degenek","DEF","Columbus Crew","MLS",31,52,4,182),
    ("Bailey Wright","DEF","Sunderland","EFL Championship",31,60,6,184),
    ("Fran Karačić","DEF","Brescia","Serie B",28,14,1,178),
    ("Nathaniel Atkinson","DEF","Hearts","Scottish Premiership",24,12,1,180),
    ("Aziz Behich","DEF","Dundee United","Scottish Championship",34,52,3,174),
    ("Ryan McGowan","DEF","Unattached","",36,62,5,183),
    ("Tom Rogić","MID","Unattached","",31,52,12,183),
    ("Aaron Mooy","MID","Celtic","Scottish Premiership",33,62,8,177),
    ("Jackson Irvine","MID","St. Pauli","Bundesliga",31,72,14,191),
    ("Ajdin Hrustic","MID","Hellas Verona","Serie A",27,42,6,175),
    ("Denis Genreau","MID","Stade Brestois","Ligue 1",24,12,2,175),
    ("Garang Kuol","FWD","Newcastle","Premier League",20,8,2,183),
    ("Kusini Yengi","FWD","Adelaide United","A-League",24,8,3,185),
    ("Cameron Devlin","MID","Hearts","Scottish Premiership",25,12,1,175),
    ("Mathew Leckie","FWD","Melbourne City","A-League",33,82,12,175),
    ("Mitchell Duke","FWD","Fagiano Okayama","J2 League",32,52,12,186),
    ("Awer Mabil","FWD","Cádiz","La Liga",28,52,14,178),
    ("Jamie Maclaren","FWD","Melbourne City","A-League",30,38,12,176),
    ("Martin Boyle","FWD","Panathinaikos","Super League Greece",31,32,8,175),
]
for p in australia_extra:
    r = add_player("Australia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── ROMANIA ───────────────────────────────────────────────────────────────
romania_extra = [
    ("Florin Niță","GK","Deportivo Alavés","La Liga",36,42,0,188),
    ("Ionuț Radu","GK","Unattached","",26,8,0,188),
    ("Horațiu Moldovan","GK","Atletico Madrid","La Liga",27,12,0,190),
    ("Andrei Rațiu","DEF","Rayo Vallecano","La Liga",25,18,2,178),
    ("Cristian Manea","DEF","CFR Cluj","Liga 1",29,18,1,178),
    ("Bogdan Racovițan","DEF","RB Salzburg","Austrian Bundesliga",24,8,0,185),
    ("Ionuț Nedelcearu","DEF","Palermo","Serie B",27,22,2,190),
    ("Radu Drăgușin","DEF","Tottenham","Premier League",23,18,1,188),
    ("Vasile Mogoș","DEF","Unattached","",30,18,1,177),
    ("Alin Toșca","DEF","Gaziantep","Süper Lig",31,38,3,187),
    ("Marius Marin","MID","Pisa","Serie B",27,18,2,176),
    ("Nicolae Stanciu","MID","Al-Qadsiah","Saudi Pro League",31,82,18,173),
    ("Darius Olaru","MID","FCSB","Liga 1",27,22,4,179),
    ("Alexandru Mitriță","FWD","Al-Ahli","Saudi Pro League",29,32,8,176),
    ("Florin Tănase","FWD","Al-Jazira","UAE Pro League",30,38,8,174),
    ("Denis Alibec","FWD","Muaither SC","Qatar Stars League",33,48,11,181),
    ("Octavian Popescu","FWD","FCSB","Liga 1",22,14,3,175),
    ("George Pușcaș","FWD","Genoa","Serie A",28,42,18,186),
]
for p in romania_extra:
    r = add_player("Romania", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── HUNGARY ───────────────────────────────────────────────────────────────
hungary_extra = [
    ("Péter Gulácsi","GK","RB Leipzig","Bundesliga",34,68,0,191),
    ("Dénes Dibusz","GK","Ferencváros","OTP Bank Liga",32,28,0,186),
    ("Bogdán Ádám","GK","Ferencváros","OTP Bank Liga",36,14,0,188),
    ("Ádám Lang","DEF","Omonia Nicosia","Cypriot First Division",29,42,2,186),
    ("Attila Szalai","DEF","Fenerbahce","Süper Lig",26,38,4,190),
    ("Willi Orbán","DEF","RB Leipzig","Bundesliga",31,52,8,185),
    ("Endre Botka","DEF","Ferencváros","OTP Bank Liga",30,28,2,182),
    ("Mihály Laczko","DEF","MOL Fehérvár","OTP Bank Liga",28,8,0,183),
    ("Bendegúz Bolla","DEF","Rapid Vienna","Austrian Bundesliga",24,12,1,175),
    ("Loic Nego","DEF","MOL Fehérvár","OTP Bank Liga",32,28,2,175),
    ("Ádám Nagy","MID","Bristol City","EFL Championship",29,68,4,181),
    ("László Kleinheisler","MID","Unattached","",30,56,5,180),
    ("Callum Styles","MID","Barnsley","EFL League One",24,22,3,183),
    ("Dominik Szoboszlai","MID","Liverpool","Premier League",23,48,14,182),
    ("Zsolt Kalmár","MID","DAC","Slovak Super Liga",30,32,6,178),
    ("Roland Sallai","FWD","Freiburg","Bundesliga",26,42,12,176),
    ("Ádám Szalai","FWD","Unattached","",36,82,26,190),
    ("Martin Ádám","FWD","Vasas SC","OTP Bank Liga",31,18,5,196),
    ("Kevin Csoboth","FWD","Újpest","OTP Bank Liga",25,8,3,177),
]
for p in hungary_extra:
    r = add_player("Hungary", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── SLOVENIA ──────────────────────────────────────────────────────────────
slovenia_extra = [
    ("Jan Oblak","GK","Atlético Madrid","La Liga",31,62,0,188),
    ("Matevž Vidovšek","GK","Olimpija Ljubljana","Slovenian PrvaLiga",27,8,0,191),
    ("Igor Vekić","GK","Dinamo Zagreb","HNL",26,5,0,186),
    ("Miha Blažič","DEF","Ferencváros","OTP Bank Liga",31,42,3,189),
    ("Jaka Bijol","DEF","Udinese","Serie A",26,28,3,192),
    ("Petar Stojanović","DEF","Sampdoria","Serie B",28,42,4,177),
    ("Nik Škorc","DEF","Olimpija Ljubljana","Slovenian PrvaLiga",26,8,0,185),
    ("Jon Gorenc Stanković","MID","Sturm Graz","Austrian Bundesliga",28,38,3,185),
    ("Jasmin Kurtić","MID","PAOK","Super League Greece",34,62,10,183),
    ("Adam Gnezda Čerin","MID","Panathinaikos","Super League Greece",26,28,4,183),
    ("Timi Max Elšnik","MID","Emmen","Eerste Divisie",24,12,2,183),
    ("Sandi Lovrić","MID","Udinese","Serie A",25,22,3,185),
    ("Benjamin Šeško","FWD","RB Leipzig","Bundesliga",21,24,8,195),
    ("Andraž Šporar","FWD","Sporting CP","Primeira Liga",28,48,14,183),
    ("Luka Zahović","FWD","Sporting Braga","Primeira Liga",28,22,6,183),
    ("Rok Kronaveter","FWD","Olimpija Ljubljana","Slovenian PrvaLiga",37,42,12,177),
    ("Kevin Kampl","MID","RB Leipzig","Bundesliga",33,52,6,174),
    ("Josip Ilicic","FWD","Atalanta","Serie A",36,78,18,183),
]
for p in slovenia_extra:
    r = add_player("Slovenia", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── HONDURAS ──────────────────────────────────────────────────────────────
honduras_extra = [
    ("Luis López","GK","San José Earthquakes","MLS",35,82,0,185),
    ("Harold Fonseca","GK","Olimpia","Liga Nacional Honduras",30,18,0,183),
    ("Orlando Galo","DEF","Motagua","Liga Nacional Honduras",30,28,2,180),
    ("Denil Maldonado","DEF","CD Marathón","Liga Nacional Honduras",25,22,1,183),
    ("Jonathan Meléndez","DEF","Olimpia","Liga Nacional Honduras",28,32,2,183),
    ("Marcelo Santos","DEF","Olimpia","Liga Nacional Honduras",30,52,3,180),
    ("Devron García","MID","Colorado Rapids","MLS",23,18,3,175),
    ("Jorge Benguché","FWD","Olimpia","Liga Nacional Honduras",28,32,8,178),
    ("Diego Rodríguez","MID","Motagua","Liga Nacional Honduras",26,22,2,175),
    ("Marvin Chávez","MID","Unattached","",38,88,10,175),
    ("Mario Martínez","FWD","Olimpia","Liga Nacional Honduras",26,28,6,178),
    ("Brayan Moya","FWD","CD Marathón","Liga Nacional Honduras",24,8,2,183),
    ("Alberth Elis","FWD","Bordeaux","Ligue 2",28,68,18,185),
    ("Eddie Hernández","FWD","Olimpia","Liga Nacional Honduras",28,42,12,183),
    ("Romell Quioto","FWD","CF Montréal","MLS",31,72,14,176),
    ("Deybi Flores","MID","Motagua","Liga Nacional Honduras",30,62,6,178),
]
for p in honduras_extra:
    r = add_player("Honduras", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

# ── COSTA RICA ────────────────────────────────────────────────────────────
costa_rica_extra = [
    ("Keylor Navas","GK","Nottm Forest","Premier League",37,108,0,185),
    ("Esteban Alvarado","GK","Deportivo Saprissa","Primera División Costa Rica",38,28,0,185),
    ("Patrick Sequeira","GK","Gil Vicente","Primeira Liga",26,12,0,188),
    ("Bryan Ruiz","MID","Deportivo Saprissa","Primera División Costa Rica",38,132,28,185),
    ("Kendall Waston","DEF","New England Revolution","MLS",36,82,9,194),
    ("Carlos Martínez","DEF","San Jose Earthquakes","MLS",36,108,4,178),
    ("Oscar Duarte","DEF","Unattached","",36,78,5,186),
    ("Francisco Calvo","DEF","Olimpia","Liga Nacional Honduras",31,72,8,183),
    ("Harold Cummings","DEF","San Jose Earthquakes","MLS",28,28,3,188),
    ("Daniel Chacón","DEF","Colorado Rapids","MLS",26,18,1,175),
    ("Alejandro Bran","MID","Deportivo Saprissa","Primera División Costa Rica",26,18,2,175),
    ("Celso Borges","MID","Deportivo Saprissa","Primera División Costa Rica",35,138,28,186),
    ("Yeltsin Tejeda","MID","Deportivo Saprissa","Primera División Costa Rica",30,88,9,176),
    ("Douglas López","MID","Cincinnati","MLS",24,12,2,175),
    ("Anthony Contreras","FWD","Herediano","Primera División Costa Rica",26,18,5,180),
    ("Rónald Matarrita","DEF","Cincinnati","MLS",28,62,5,175),
    ("Manfred Ugalde","FWD","Toulouse","Ligue 1",21,18,6,183),
    ("Joel Campbell","FWD","Real Betis","La Liga",32,128,28,173),
    ("Josimar Alcócer","FWD","Deportivo Saprissa","Primera División Costa Rica",26,12,3,178),
]
for p in costa_rica_extra:
    r = add_player("Costa Rica", p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    if r: total += 1

conn.commit()
print(f"Total added in step 3: {total}")

print("\nFinal player counts:")
rows = conn.execute("""
    SELECT t.name, COUNT(p.id) as cnt
    FROM teams t LEFT JOIN players p ON t.id = p.team_id
    GROUP BY t.id ORDER BY cnt ASC
""").fetchall()
for r in rows:
    flag = " ⚠" if r[1] < 20 else ""
    print(f"  {r[1]:3d}  {r[0]}{flag}")
