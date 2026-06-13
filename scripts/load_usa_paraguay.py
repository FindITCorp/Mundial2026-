"""
Carga datos reales del partido USA 3-1 Paraguay (12 jun 2026).
"""
import sqlite3
from datetime import datetime

DB = '/home/user/mundial2026/data/mundial2026.db'
USA = 11
PAR = 48
MATCH_ID = 19
DATE = '2026-06-12'
COMP = 'FIFA World Cup 2026'

team_stats = [
    dict(match_id=MATCH_ID, team_id=USA, is_home=1,
         possession=65.0, xg=1.34,
         shots_total=16, shots_on_target=6, shots_off_target=6,
         shots_blocked=4, shots_inside_box=13, shots_outside_box=3,
         clear_chances=4, corners=3, fouls=13,
         yellow_cards=1, red_cards=0,
         passes_total=598, passes_accurate=510, passes_pct=85.3,
         passes_final_third=78, long_balls_total=50, long_balls_accurate=28,
         crosses_total=17, crosses_accurate=3,
         touches_box=53, tackles_total=7, tackles_won=6,
         interceptions=11, recoveries=43, clearances=17,
         saves=1, big_saves=None,
         duels_total=114, duels_won=60,
         aerial_total=31, aerial_won=17,
         offsides=2, free_kicks=17),
    dict(match_id=MATCH_ID, team_id=PAR, is_home=0,
         possession=35.0, xg=0.47,
         shots_total=9, shots_on_target=1, shots_off_target=3,
         shots_blocked=5, shots_inside_box=4, shots_outside_box=5,
         clear_chances=1, corners=1, fouls=17,
         yellow_cards=5, red_cards=0,
         passes_total=320, passes_accurate=230, passes_pct=71.9,
         passes_final_third=35, long_balls_total=58, long_balls_accurate=18,
         crosses_total=5, crosses_accurate=1,
         touches_box=9, tackles_total=22, tackles_won=16,
         interceptions=9, recoveries=40, clearances=33,
         saves=3, big_saves=None,
         duels_total=114, duels_won=54,
         aerial_total=31, aerial_won=14,
         offsides=1, free_kicks=13),
]

# (name, team_id, pos, mins, goals, assists, tkl_tot, tkl_won,
#  pass_acc, pass_tot, pass_pct, duel_tot, duel_won, air_tot, air_won)
players = [
    # USA
    ("Folarin Balogun",    USA, 'F', 72, 2, 0, 0, 0, 10, 16, 62.5, 10,  5,  1,  0),
    ("Giovanni Reyna",     USA, 'M',  8, 1, 0, 0, 0,  8,  8,100.0,  3,  2,  0,  0),
    ("Tim Ream",           USA, 'D', 90, 0, 1, 0, 0, 85, 91, 93.4,  5,  3,  3,  1),
    ("Malik Tillman",      USA, 'M', 82, 0, 1, 0, 0, 30, 38, 78.9, 18,  7,  4,  1),
    ("Christian Pulisic",  USA, 'M', 45, 0, 1, 1, 0, 18, 22, 81.8,  8,  5,  0,  0),
    ("Weston McKennie",    USA, 'M', 90, 0, 0, 0, 0, 40, 52, 76.9,  6,  3,  1,  0),
    ("Alexander Freeman",  USA, 'D', 90, 0, 1, 1, 0, 64, 74, 86.5, 13,  8,  6,  5),
    ("Tyler Adams",        USA, 'M', 90, 0, 0, 2, 0, 52, 58, 89.7, 14,  9,  4,  2),
    ("Chris Richards",     USA, 'D', 90, 0, 1, 0, 0, 83, 83,100.0, 10,  6,  6,  4),
    ("Antonee Robinson",   USA, 'D', 90, 0, 0, 0, 0, 44, 56, 78.6,  8,  4,  3,  2),
    ("Sebastian Berhalter",USA, 'M', 45, 0, 0, 0, 0, 20, 28, 71.4,  3,  3,  2,  2),
    ("Sergino Dest",       USA, 'M', 72, 0, 0, 0, 0, 28, 35, 80.0, 10,  4,  0,  0),
    ("Tim Weah",           USA, 'F', 18, 0, 0, 0, 0, 13, 14, 92.9,  3,  0,  0,  0),
    ("Ricardo Pepi",       USA, 'F', 18, 0, 1, 0, 0,  3,  3,100.0,  3,  1,  1,  0),
    ("Matthew Freese",     USA, 'G', 90, 0, 0, 0, 0, 12, 20, 60.0,  0,  0,  0,  0),
    # Paraguay
    ("Mauricio",           PAR, 'M', 45, 1, 0, 2, 0, 14, 20, 70.0,  5,  3,  2,  0),
    ("Julio Enciso",       PAR, 'F', 90, 0, 1, 2, 0, 20, 25, 80.0, 14,  8,  2,  0),
    ("Andres Cubas",       PAR, 'M', 90, 0, 0, 5, 0, 25, 31, 80.6, 12,  5,  0,  0),
    ("Ramon Sosa",         PAR, 'F', 11, 0, 0, 0, 0,  3,  3,100.0,  1,  1,  0,  0),
    ("Alejandro Romero",   PAR, 'M', 10, 0, 0, 0, 0,  6,  9, 66.7,  2,  1,  0,  0),
    ("Miguel Almiron",     PAR, 'M', 79, 0, 0, 2, 0, 18, 23, 78.3,  9,  6,  2,  1),
    ("Antonio Sanabria",   PAR, 'F', 62, 0, 0, 0, 0,  5, 10, 50.0, 11,  4,  5,  3),
    ("Gustavo Velazquez",  PAR, 'D', 11, 0, 0, 0, 0,  3,  3,100.0,  3,  1,  2,  1),
    ("Juan Caceres",       PAR, 'D', 79, 0, 0, 5, 0, 20, 32, 62.5, 16,  9,  2,  1),
    ("Diego Gomez",        PAR, 'M', 80, 0, 0, 2, 0, 21, 26, 80.8, 10,  5,  3,  2),
    ("Alex Arce",          PAR, 'F', 28, 0, 1, 0, 0,  4,  6, 66.7,  8,  1,  5,  0),
    ("Orlando Gill",       PAR, 'G', 90, 0, 0, 0, 0, 15, 25, 60.0,  0,  0,  0,  0),
    ("Gustavo Gomez",      PAR, 'D', 90, 0, 1, 0, 0, 23, 29, 79.3,  7,  5,  4,  4),
    ("Omar Alderete",      PAR, 'D', 90, 0, 0, 0, 0, 21, 33, 63.6,  4,  2,  2,  2),
    ("Damian Bobadilla",   PAR, 'M', 45, 0, 0, 0, 0,  9, 11, 81.8,  4,  0,  0,  0),
    ("Junior Alonso",      PAR, 'D', 90, 0, 0, 2, 0, 23, 34, 67.6,  8,  3,  2,  0),
]

def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    now = datetime.utcnow().isoformat()

    cur.execute("UPDATE wc_matches SET score_home=3, score_away=1, played=1 WHERE id=?", (MATCH_ID,))
    print(f"wc_matches id={MATCH_ID} → 3-1, played=1  (rows: {cur.rowcount})")

    cols = ['match_id','team_id','is_home','possession','xg',
            'shots_total','shots_on_target','shots_off_target','shots_blocked',
            'shots_inside_box','shots_outside_box','clear_chances','corners','fouls',
            'yellow_cards','red_cards','passes_total','passes_accurate','passes_pct',
            'passes_final_third','long_balls_total','long_balls_accurate',
            'crosses_total','crosses_accurate','touches_box',
            'tackles_total','tackles_won','interceptions','recoveries','clearances',
            'saves','big_saves','duels_total','duels_won','aerial_total','aerial_won',
            'offsides','free_kicks']
    ph = ','.join(['?']*len(cols))
    ins_ts = 0
    for s in team_stats:
        cur.execute(f"INSERT OR IGNORE INTO match_team_stats ({','.join(cols)}) VALUES ({ph})",
                    tuple(s[c] for c in cols))
        ins_ts += cur.rowcount
    print(f"match_team_stats: {ins_ts}/2 insertados")

    ins_ps = skipped = 0
    for row in players:
        name, tid, pos, mins, goals, assists, tkt, tkw, pa, pt, pp, dt, dw, at, aw = row
        try:
            cur.execute("""
                INSERT INTO match_player_stats
                (match_date,competition,home_team_id,away_team_id,team_id,
                 player_name,position,minutes,goals,assists,
                 passes_accurate,passes_total,passes_pct,
                 tackles_total,tackles_won,duels_total,duels_won,
                 aerial_total,aerial_won,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (DATE, COMP, USA, PAR, tid,
                  name, pos, mins, goals, assists,
                  pa if pt > 0 else None, pt if pt > 0 else None, pp if pt > 0 else None,
                  tkt if tkt > 0 else None, tkw if tkt > 0 else None,
                  dt if dt > 0 else None, dw if dt > 0 else None,
                  at if at > 0 else None, aw if at > 0 else None,
                  now))
            ins_ps += 1
        except sqlite3.IntegrityError:
            skipped += 1
            print(f"  SKIP: {name}")

    print(f"match_player_stats: {ins_ps} insertados, {skipped} salteados")
    db.commit()
    db.close()
    print("Done.")

if __name__ == '__main__':
    main()
