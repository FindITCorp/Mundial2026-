"""
Carga datos reales del partido Canada 1-0 Bosnia & Herzegovina (12 jun 2026).
- Actualiza wc_matches id=7
- Inserta match_team_stats (match_id=7)
- Inserta 32 filas en match_player_stats
"""
import sqlite3
from datetime import datetime

DB = '/home/user/mundial2026/data/mundial2026.db'

# team_ids
CAN = 21  # Canada (home)
BIH = 51  # Bosnia & Herzegovina (away)
MATCH_ID = 7
DATE = '2026-06-12'
COMP = 'FIFA World Cup 2026'

# ── match_team_stats ──────────────────────────────────────────────────────────
team_stats = [
    # Canada (home, is_home=1)
    dict(
        match_id=MATCH_ID, team_id=CAN, is_home=1,
        possession=61.0, xg=1.25,
        shots_total=13, shots_on_target=4, shots_off_target=5,
        shots_blocked=4, shots_inside_box=10, shots_outside_box=3,
        clear_chances=2, corners=9, fouls=10,
        yellow_cards=2, red_cards=0,
        passes_total=417, passes_accurate=310, passes_pct=74.3,
        passes_final_third=75, long_balls_total=43, long_balls_accurate=19,
        crosses_total=24, crosses_accurate=5,
        touches_box=38, tackles_total=23, tackles_won=15,
        interceptions=4, recoveries=50, clearances=21,
        saves=2, big_saves=None,
        duels_total=149, duels_won=70,
        aerial_total=63, aerial_won=20,
        offsides=1, free_kicks=20,
    ),
    # Bosnia (away, is_home=0)
    dict(
        match_id=MATCH_ID, team_id=BIH, is_home=0,
        possession=39.0, xg=0.98,
        shots_total=8, shots_on_target=3, shots_off_target=4,
        shots_blocked=1, shots_inside_box=5, shots_outside_box=3,
        clear_chances=2, corners=4, fouls=20,
        yellow_cards=3, red_cards=0,
        passes_total=268, passes_accurate=170, passes_pct=63.4,
        passes_final_third=58, long_balls_total=62, long_balls_accurate=18,
        crosses_total=10, crosses_accurate=6,
        touches_box=14, tackles_total=21, tackles_won=13,
        interceptions=10, recoveries=54, clearances=71,
        saves=1, big_saves=None,
        duels_total=149, duels_won=79,
        aerial_total=63, aerial_won=43,
        offsides=0, free_kicks=10,
    ),
]

# ── match_player_stats ────────────────────────────────────────────────────────
# fmt: (player_name, team_id, pos, mins, goals, assists, tkl_tot, tkl_won,
#        pass_acc, pass_tot, pass_pct, duel_tot, duel_won, air_tot, air_won)
players = [
    # Bosnia
    ("Nikola Katić",         BIH, 'D', 90, 0, 0, 5,  0, 13, 22, 59.1, 24, 15, 15, 10),
    ("Sead Kolašinac",       BIH, 'D', 84, 0, 1, 3,  0, 15, 21, 71.4, 10,  6,  2,  1),
    ("Tarik Muharemović",    BIH, 'D', 90, 0, 1, 0,  0, 24, 31, 77.4, 10,  8,  7,  6),
    ("Ivan Bašić",           BIH, 'M', 62, 0, 0, 0,  0, 17, 21, 81.0,  5,  2,  2,  1),
    ("Jovo Lukić",           BIH, 'F', 62, 1, 1, 0,  0,  7, 17, 41.2, 13, 10,  9,  9),
    ("Amar Dedić",           BIH, 'D', 90, 0, 0, 3,  0, 13, 21, 61.9, 11,  7,  3,  3),
    ("Ermedin Demirović",    BIH, 'F', 90, 0, 0, 3,  0, 12, 17, 70.6, 21, 11, 10,  7),
    ("Armin Gigović",        BIH, 'M', 28, 0, 1, 0,  0, 12, 16, 75.0,  7,  4,  1,  1),
    ("Dženis Burnić",        BIH, 'M', 13, 0, 0, 0,  0,  2,  2,100.0,  0,  0,  0,  0),
    ("Benjamin Tahirović",   BIH, 'M', 90, 0, 0, 3,  0, 16, 23, 69.6,  8,  5,  2,  1),
    ("Kerim Alajbegović",    BIH, 'F', 16, 0, 0, 0,  0,  5,  5,100.0,  3,  1,  0,  0),
    ("Ivan Šunjić",          BIH, 'M', 16, 0, 0, 0,  0, 10, 14, 71.4,  3,  1,  1,  1),
    ("Amar Memić",           BIH, 'M', 74, 0, 0, 0,  0,  3,  7, 42.9,  8,  2,  2,  1),
    ("Nikola Vasilj",        BIH, 'G', 90, 0, 0, 0,  0, 12, 30, 40.0,  0,  0,  0,  0),
    ("Samed Baždar",         BIH, 'F', 28, 0, 1, 0,  0,  2,  6, 33.3, 13,  4,  6,  1),
    ("Esmir Bajraktarević",  BIH, 'M', 74, 0, 0, 0,  0,  7, 15, 46.7, 13,  3,  3,  1),
    # Canada
    ("Richie Laryea",        CAN, 'D', 90, 0, 0, 5,  0, 28, 37, 75.7, 11,  9,  3,  1),
    ("Cyle Larin",           CAN, 'F', 14, 1, 0, 0,  0,  0,  0,  0.0,  3,  2,  2,  1),
    ("Stephen Eustaquio",    CAN, 'M', 89, 0, 1, 0,  0, 41, 46, 89.1,  7,  4,  1,  0),
    ("Alistair Johnston",    CAN, 'D', 90, 0, 1, 0,  0, 23, 34, 67.6,  7,  5,  1,  1),
    ("Liam Millar",          CAN, 'M', 61, 0, 0, 2,  0, 21, 28, 75.0, 13,  6,  5,  2),
    ("Maxime Crépeau",       CAN, 'G', 90, 0, 1, 0,  0, 17, 24, 70.8,  2,  2,  1,  1),
    ("Jacob Shaffelburg",    CAN, 'F', 29, 0, 1, 0,  0,  5,  7, 71.4,  4,  1,  1,  0),
    ("Ali Ahmed",            CAN, 'M', 29, 0, 1, 0,  0, 10, 16, 62.5,  6,  2,  1,  0),
    ("Derek Cornelius",      CAN, 'D', 90, 0, 0, 4,  0, 50, 66, 75.8, 15,  9, 10,  4),
    ("Ismael Koné",          CAN, 'M', 90, 0, 1, 0,  0, 51, 61, 83.6, 16,  4,  6,  1),
    ("Luc De Fougerolles",   CAN, 'D', 90, 0, 0, 3,  0, 40, 50, 80.0, 22, 10, 13,  3),
    ("Promise David",        CAN, 'F', 29, 0, 1, 1,  0,  1,  3, 33.3, 10,  3,  3,  1),
    ("Jonathan David",       CAN, 'F', 61, 0, 1, 0,  0,  8, 14, 57.1,  4,  2,  1,  0),
    ("Tajon Buchanan",       CAN, 'M', 61, 0, 1, 0,  0,  5,  6, 83.3, 10,  3,  2,  0),
    ("Tani Oluwaseyi",       CAN, 'F', 76, 0, 0, 0,  0,  6, 20, 30.0, 19,  8, 13,  5),
    ("Jonathan Osorio",      CAN, 'M',  1, 0, 0, 0,  0,  4,  5, 80.0,  0,  0,  0,  0),
]

def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    now = datetime.utcnow().isoformat()

    # 1. Update wc_matches
    cur.execute("""
        UPDATE wc_matches
        SET score_home=1, score_away=0, played=1
        WHERE id=?
    """, (MATCH_ID,))
    print(f"wc_matches id={MATCH_ID} → score 1-0, played=1  (rows: {cur.rowcount})")

    # 2. Insert match_team_stats
    cols = [
        'match_id','team_id','is_home','possession','xg',
        'shots_total','shots_on_target','shots_off_target','shots_blocked',
        'shots_inside_box','shots_outside_box','clear_chances','corners','fouls',
        'yellow_cards','red_cards','passes_total','passes_accurate','passes_pct',
        'passes_final_third','long_balls_total','long_balls_accurate',
        'crosses_total','crosses_accurate','touches_box',
        'tackles_total','tackles_won','interceptions','recoveries','clearances',
        'saves','big_saves','duels_total','duels_won','aerial_total','aerial_won',
        'offsides','free_kicks',
    ]
    placeholders = ','.join(['?'] * len(cols))
    col_list = ','.join(cols)
    inserted_ts = 0
    for s in team_stats:
        vals = tuple(s[c] for c in cols)
        cur.execute(f"""
            INSERT OR IGNORE INTO match_team_stats ({col_list})
            VALUES ({placeholders})
        """, vals)
        inserted_ts += cur.rowcount
    print(f"match_team_stats inserted: {inserted_ts}/2")

    # 3. Insert match_player_stats
    inserted_ps = 0
    skipped = 0
    for row in players:
        (name, tid, pos, mins, goals, assists,
         tkl_tot, tkl_won,
         pass_acc, pass_tot, pass_pct,
         duel_tot, duel_won, air_tot, air_won) = row
        try:
            cur.execute("""
                INSERT INTO match_player_stats
                (match_date, competition, home_team_id, away_team_id, team_id,
                 player_name, position, minutes, goals, assists,
                 passes_accurate, passes_total, passes_pct,
                 tackles_total, tackles_won,
                 duels_total, duels_won, aerial_total, aerial_won,
                 created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (DATE, COMP, CAN, BIH, tid,
                  name, pos, mins, goals, assists,
                  pass_acc if pass_tot > 0 else None,
                  pass_tot if pass_tot > 0 else None,
                  pass_pct if pass_tot > 0 else None,
                  tkl_tot if tkl_tot > 0 else None,
                  tkl_won if tkl_tot > 0 else None,
                  duel_tot if duel_tot > 0 else None,
                  duel_won if duel_tot > 0 else None,
                  air_tot if air_tot > 0 else None,
                  air_won if air_tot > 0 else None,
                  now))
            inserted_ps += 1
        except sqlite3.IntegrityError:
            print(f"  SKIP (dup): {name}")
            skipped += 1

    print(f"match_player_stats inserted: {inserted_ps}/32  (skipped: {skipped})")

    db.commit()
    db.close()
    print("Done.")

if __name__ == '__main__':
    main()
