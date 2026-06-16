"""Carga Spain vs Cape Verde (15-jun, match_id=43) desde dump Sofascore."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"
conn = sqlite3.connect(str(DB))
NOW = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

MATCH_ID  = 43
DATE      = "2026-06-15"
COMP      = "FIFA World Cup 2026"
SPAIN_ID  = 7
CV_ID     = 59

# ── Team stats ────────────────────────────────────────────────────────────────
team_stats = [
    # (team_id, is_home, possession, xg, shots_total, shots_on_target, shots_off,
    #  shots_blocked, shots_in_box, shots_out_box, clear_chances,
    #  corners, fouls, yellow_cards, red_cards,
    #  passes_total, passes_accurate, passes_pct,
    #  tackles_total, saves)
    (SPAIN_ID, 1,  74.0, 2.1, 27, 7, 12, 8, 16, 11, 2,  11, 10, 1, 0, 800, None, 88.0, 13, 1),
    (CV_ID,    0,  26.0, 0.2,  6, 1,  3, 2,  2,  4, 1,   1,  1, 1, 0, 278, None, 81.0, 18, 7),
]
for row in team_stats:
    tid, is_home, poss, xg, shots, sot, soff, sblk, sinb, sout, cc, corners, fouls, yc, rc, pt, pa, ppct, tck, saves = row
    conn.execute("""
        INSERT OR REPLACE INTO match_team_stats
          (match_id, team_id, is_home, possession, xg, shots_total, shots_on_target,
           shots_off_target, shots_blocked, shots_inside_box, shots_outside_box,
           clear_chances, corners, fouls, yellow_cards, red_cards,
           passes_total, passes_accurate, passes_pct, tackles_total, saves)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (MATCH_ID, tid, is_home, poss, xg, shots, sot, soff, sblk, sinb, sout,
          cc, corners, fouls, yc, rc, pt, pa, ppct, tck, saves))
print("Team stats: OK")

# ── Player stats ──────────────────────────────────────────────────────────────
# (name, team_id, pos, mins, goals, assists, entradas, pases_prec, pases_tot, pases_pct,
#  duelos_tot, duelos_gan, duelos_suelo_tot, duelos_suelo_gan, duelos_aereos_tot, duelos_aereos_gan)
players = [
    # ── Cape Verde ────────────────────────────────────────────────────────────
    ("Vozinha",             CV_ID,    "GK", 90, 0, 0, None, 29, 42, 69, 2,  2, 1, 1, 1, 1),
    ("Diney Borges",        CV_ID,    "DEF",90, 0, 0,    5, 32, 40, 80, 9,  6, 6, 5, 3, 1),
    ("Pico",                CV_ID,    "DEF",90, 0, 0, None, 31, 41, 76, 3,  2, 1, 0, 2, 2),
    ("Ryan Mendes",         CV_ID,    "MID",90, 0, 0,    2, 13, 18, 72, 7,  4, 6, 4, 1, 0),
    ("Sidny Lopes Cabral",  CV_ID,    "DEF",76, 0, 0,    2, 14, 17, 82,11,  5,10, 5, 1, 0),
    ("Joao Paulo",          CV_ID,    "MID",14, 0, 0,    1, None,None,None,2,  2, 2, 2,None,None),
    ("Telmo Arcanjo",       CV_ID,    "MID",11, 0, 0, None,  2,  2,100,None,None,0, 0,None,None),
    ("Jovane Cabral",       CV_ID,    "MID",61, 0, 0,    2, 10, 13, 77, 5,  3, 4, 3, 1, 0),
    ("Jamiro Monteiro",     CV_ID,    "MID",79, 0, 0,    3, 16, 21, 76, 5,  3, 5, 3,None,None),
    ("Deroy Duarte",        CV_ID,    "MID",29, 0, 0, None,  6,  8, 75,None,None,0, 0,None,None),
    ("Nuno Da Costa",       CV_ID,    "FWD",29, 0, 0,    1,  3,  6, 50, 8,  3, 5, 2, 3, 1),
    ("Dailon Rocha Livramento",CV_ID, "FWD",61, 0, 0, None,  3,  4, 75, 7,  3, 1, 1, 6, 2),
    ("Steven Moreira",      CV_ID,    "DEF",90, 0, 0, None, 22, 27, 81, 5,  1, 2, 1, 3, 0),
    ("Willy Semedo",        CV_ID,    "FWD",29, 0, 0,    1,  6,  9, 67, 5,  2, 4, 1, 1, 1),
    ("Kevin Lenini",        CV_ID,    "MID",90, 0, 0,    1, 12, 20, 60, 7,  4, 5, 3, 2, 1),
    ("Laros Duarte",        CV_ID,    "MID",61, 0, 0, None,  6,  7, 86, 4,  0, 0, 0, 4, 0),
    # ── Spain ─────────────────────────────────────────────────────────────────
    ("Pedri",               SPAIN_ID, "MID",90, 0, 0,    2, 86, 99, 87, 8,  6, 7, 5, 1, 1),
    ("Rodri",               SPAIN_ID, "MID",87, 0, 0,    1,116,126, 92, 7,  4, 3, 1, 4, 3),
    ("Aymeric Laporte",     SPAIN_ID, "DEF",90, 0, 0, None,106,110, 96,10,  3, 2, 0, 8, 3),
    ("Marcos Llorente",     SPAIN_ID, "DEF",90, 0, 0,    2, 76, 82, 93, 8,  5, 5, 3, 3, 2),
    ("Pau Cubarsi",         SPAIN_ID, "DEF",90, 0, 0, None,107,109, 98, 1,  1, 0, 0, 1, 1),
    ("Marc Cucurella",      SPAIN_ID, "DEF",90, 0, 0,    1, 63, 67, 94, 5,  2, 5, 2,None,None),
    ("Fabian Ruiz",         SPAIN_ID, "MID",71, 0, 0,    2, 70, 75, 93, 4,  3, 3, 2, 1, 1),
    ("Unai Simon",          SPAIN_ID, "GK", 90, 0, 0, None, 17, 17,100,None,None,0, 0,None,None),
    ("Dani Olmo",           SPAIN_ID, "MID", 9, 0, 0, None,  8, 10, 80,None,None,0, 0,None,None),
    ("Lamine Yamal",        SPAIN_ID, "FWD",19, 0, 0, None, 16, 19, 84, 6,  2, 6, 2,None,None),
    ("Pablo Gavi",          SPAIN_ID, "FWD",71, 0, 0,    3, 26, 30, 87,10,  7, 6, 3, 4, 4),
    ("Nico Williams",       SPAIN_ID, "FWD", 9, 0, 0, None,  1,  2, 50,None,None,0, 0,None,None),
    ("Mikel Merino",        SPAIN_ID, "MID",19, 0, 0,    1,  8, 10, 80, 2,  1, 2, 1,None,None),
    ("Mikel Oyarzabal",     SPAIN_ID, "FWD",90, 0, 0,    1,  8, 10, 80, 8,  3, 4, 1, 4, 2),
    ("Ferran Torres",       SPAIN_ID, "FWD",81, 0, 0, None, 26, 34, 76,11,  3, 9, 1, 2, 2),
]

ins = 0
for p in players:
    name, tid, pos, mins, goals, assists, tck, pp, pt, ppct, dt, dg, dst, dsg, dat, dag = p
    conn.execute("""
        INSERT OR REPLACE INTO match_player_stats
          (match_date, competition, home_team_id, away_team_id, team_id,
           player_name, position, minutes, goals, assists,
           passes_accurate, passes_total, passes_pct,
           tackles_total, tackles_won,
           duels_total, duels_won,
           aerial_total, aerial_won, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (DATE, COMP, SPAIN_ID, CV_ID, tid,
          name, pos, mins, goals, assists,
          pp, pt, ppct, tck, tck, dt, dg, dat, dag, NOW))
    ins += 1

print(f"Player stats: {ins} jugadores cargados")

# ── Ratings Sofascore ─────────────────────────────────────────────────────────
ratings = {
    "Pedri": 9.0, "Rodri": 8.6, "Aymeric Laporte": 8.2, "Mikel Oyarzabal": 8.0,
    "Pau Cubarsi": 7.8, "Marcos Llorente": 7.8, "Unai Simon": 7.1,
    "Fabian Ruiz": 7.1, "Marc Cucurella": 7.3, "Pablo Gavi": 6.7,
    "Ferran Torres": 5.9, "Mikel Merino": 6.4, "Lamine Yamal": 6.8,
    "Dani Olmo": 6.8, "Nico Williams": 6.5,
    "Vozinha": 9.7, "Diney Borges": 8.5, "Pico": 7.6,
    "Sidny Lopes Cabral": 6.9, "Ryan Mendes": 6.9, "Steven Moreira": 6.5,
    "Jamiro Monteiro": 6.7, "Laros Duarte": 6.4, "Kevin Lenini": 6.4,
    "Dailon Rocha Livramento": 6.5, "Jovane Cabral": 6.7,
}
for name, rating in ratings.items():
    conn.execute("""
        UPDATE match_player_stats SET rating=?
        WHERE match_date=? AND home_team_id=? AND away_team_id=? AND player_name=?
    """, (rating, DATE, SPAIN_ID, CV_ID, name))

print(f"Ratings: {len(ratings)} actualizados")
conn.commit()
conn.close()
print("Listo. Falta: UPDATE wc_matches SET score_home=?, score_away=?, played=1 WHERE id=43")
