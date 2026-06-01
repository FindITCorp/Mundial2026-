#!/usr/bin/env python3
"""
Monte Carlo simulation — FIFA World Cup 2026
48 teams, 12 groups of 4, top 2 + 8 best 3rd advance (32 total).
Precomputes all pairwise matchup lambdas for speed.
"""
import sys, sqlite3, math, random
from collections import defaultdict
import numpy as np

sys.path.insert(0, "/home/user/mundial2026")
from models.match_predictor import predict_match

DB_PATH = "/home/user/mundial2026/data/mundial2026.db"
N_SIMS  = 5_000


def precompute_matchups(team_ids, conn):
    """Precompute (lambda_home, lambda_away) for all pairs. Neutral venue."""
    print("Precomputing matchup lambdas...")
    cache = {}
    n = len(team_ids)
    for i, t1 in enumerate(team_ids):
        for t2 in team_ids:
            if t1 == t2:
                continue
            try:
                r = predict_match(t1, t2, neutral=True)
                cache[(t1, t2)] = (r["lambda_home"], r["lambda_away"])
            except Exception:
                cache[(t1, t2)] = (1.2, 1.2)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{n} teams done...")
    print(f"  Cache size: {len(cache)} matchups")
    return cache


def simulate_group(group_teams, cache):
    standings = {tid: {"pts": 0, "gd": 0, "gf": 0} for tid in group_teams}
    for i in range(len(group_teams)):
        for j in range(i + 1, len(group_teams)):
            h_id = group_teams[i]
            a_id = group_teams[j]
            lh, la = cache.get((h_id, a_id), (1.2, 1.2))
            gh = int(np.random.poisson(lh))
            ga = int(np.random.poisson(la))
            standings[h_id]["gf"] += gh
            standings[a_id]["gf"] += ga
            standings[h_id]["gd"] += gh - ga
            standings[a_id]["gd"] += ga - gh
            if gh > ga:
                standings[h_id]["pts"] += 3
            elif gh == ga:
                standings[h_id]["pts"] += 1
                standings[a_id]["pts"] += 1
            else:
                standings[a_id]["pts"] += 3
    sorted_teams = sorted(
        group_teams,
        key=lambda t: (standings[t]["pts"], standings[t]["gd"], standings[t]["gf"]),
        reverse=True
    )
    return [(tid, standings[tid]["pts"], standings[tid]["gd"], standings[tid]["gf"])
            for tid in sorted_teams]


def simulate_ko(t1, t2, cache):
    """KO match — no draw. Penalties coin-flip weighted by strength."""
    lh, la = cache.get((t1, t2), (1.2, 1.2))
    # Poisson win probabilities (approximate)
    # p(t1 wins) based on lambda ratio
    ratio = lh / (lh + la) if (lh + la) > 0 else 0.5
    return t1 if random.random() < ratio else t2


def run_simulation(groups, cache):
    grp_names = sorted(groups.keys())
    third_place = []
    winners = []
    runners = []

    for grp in grp_names:
        standing = simulate_group(groups[grp], cache)
        winners.append(standing[0][0])
        runners.append(standing[1][0])
        # (pts, gd, gf, team_id)
        third_place.append((standing[2][1], standing[2][2], standing[2][3], standing[2][0]))

    # 8 best 3rd-place teams
    third_place.sort(reverse=True)
    best_thirds = [t[3] for t in third_place[:8]]

    # 32 qualifiers: 12 winners + 12 runners + 8 thirds
    r32_pool = winners + runners + best_thirds  # 32 teams

    # Random draw for KO bracket — eliminates systematic bias from fixed pairings
    random.shuffle(r32_pool)

    # Round of 32 → 16
    r16 = [simulate_ko(r32_pool[i], r32_pool[i + 1], cache) for i in range(0, 32, 2)]

    # QF → 8
    qf = [simulate_ko(r16[i], r16[i + 1], cache) for i in range(0, 16, 2)]

    # SF → 4
    sf = [simulate_ko(qf[i], qf[i + 1], cache) for i in range(0, 8, 2)]

    # Final
    return simulate_ko(sf[0], sf[1], cache)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT gd.grp, gd.team_id, t.name
        FROM wc_group_draw gd
        JOIN teams t ON t.id = gd.team_id
        ORDER BY gd.grp, gd.pot
    """).fetchall()

    groups = defaultdict(list)
    tid_name = {}
    for r in rows:
        groups[r["grp"]].append(r["team_id"])
        tid_name[r["team_id"]] = r["name"]

    all_team_ids = list(tid_name.keys())

    print(f"WC2026 Monte Carlo — {N_SIMS:,} simulations")
    print(f"Groups: {len(groups)}  Teams: {len(all_team_ids)}\n")

    cache = precompute_matchups(all_team_ids, conn)
    conn.close()

    print(f"\nRunning {N_SIMS:,} simulations...")
    champion_counts = defaultdict(int)

    for sim in range(N_SIMS):
        winner = run_simulation(dict(groups), cache)
        if winner:
            champion_counts[winner] += 1
        if (sim + 1) % 1000 == 0:
            print(f"  {sim + 1:,}/{N_SIMS:,} done")

    total = sum(champion_counts.values())
    print(f"\n{'='*52}")
    print(f"WORLD CUP 2026 — CHAMPION PROBABILITIES ({total:,} sims)")
    print(f"{'='*52}")
    print(f"{'Rank':<5} {'Team':<22} {'Win%':>6}  {'Group'}")
    print(f"{'-'*45}")

    # Get group for each team
    team_group = {}
    for grp, tids in groups.items():
        for tid in tids:
            team_group[tid] = grp

    sorted_champs = sorted(champion_counts.items(), key=lambda x: -x[1])
    for rank, (tid, cnt) in enumerate(sorted_champs[:20], 1):
        pct = cnt / N_SIMS * 100
        grp = team_group.get(tid, "?")
        print(f"{rank:<5} {tid_name[tid]:<22} {pct:>5.1f}%  Group {grp}")

    # Summary stats
    top5_pct = sum(cnt for _, cnt in sorted_champs[:5]) / N_SIMS * 100
    print(f"\nTop 5 combined: {top5_pct:.1f}%  |  Rest of field: {100 - top5_pct:.1f}%")
    print(f"Teams with >1% win chance: {sum(1 for _, c in champion_counts.items() if c/N_SIMS >= 0.01)}")


if __name__ == "__main__":
    main()
