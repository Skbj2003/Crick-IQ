"""
simulator.py  —  IPL Match Simulator
─────────────────────────────────────
Speed design:
  • ALL DB queries happen ONCE during profile pre-fetch
  • _simulate_once() has ZERO DB calls — pure numpy
  • 150 sims finish in ~1-2 seconds

Ball-counting fix:
  • Wides do NOT count as legal deliveries → over continues until 6 legal balls
  • Over always completes 6 legal balls (or all-out)
"""

import duckdb
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

DB_PATH = "ipl_tactics.db"
N_SIMS  = 150

OUTCOMES = ["dot","1","2","3","4","6","wicket","wide"]
RUNS_MAP = {"dot":0,"1":1,"2":2,"3":3,"4":4,"6":6,"wicket":0,"wide":1}

# ── Module-level profile cache (survives across reruns in same session) ──
_BAT_CACHE     : dict = {}
_BOWL_CACHE    : dict = {}
_VENUE_MULT    : dict = {}

# ─────────────────────────────────────────────────────────────────────────────
# SEASON HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _recent_seasons(n=5):
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        s = con.execute(
            "SELECT DISTINCT season FROM deliveries WHERE season>0 ORDER BY season DESC"
        ).df()["season"].tolist()
        con.close()
        return s[:n]
    except Exception:
        return []

def _sc(n=5):
    s = _recent_seasons(n)
    return f"AND season IN ({','.join(str(x) for x in s)})" if s else ""


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE FETCHERS  (each player queried at most ONCE per session)
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULT_BAT  = {"dot":.30,"1":.25,"2":.08,"3":.02,"4":.15,"6":.10,"wicket":.05,"wide":.05}
_DEFAULT_BOWL = {"dot":.32,"1":.26,"2":.08,"3":.02,"4":.14,"6":.08,"wicket":.05,"wide":.05}

def _fetch_batsman(name: str) -> dict:
    if name in _BAT_CACHE:
        return _BAT_CACHE[name]
    sc = _sc(5)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT count(*),
                   sum(CASE WHEN extras_wides>0                                        THEN 1 ELSE 0 END),
                   sum(CASE WHEN extras_wides=0 AND runs_batter=0 AND is_wicket=0     THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=1  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=2  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=3  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=4  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=6  THEN 1 ELSE 0 END),
                   sum(is_wicket)
            FROM deliveries
            WHERE LOWER(striker) LIKE LOWER('%{name}%') {sc}
        """).fetchone()
        con.close()
        t = max(row[0] or 1, 1)
        p = {"dot":row[2]/t,"1":row[3]/t,"2":row[4]/t,"3":row[5]/t,
             "4":row[6]/t,"6":row[7]/t,"wicket":row[8]/t,"wide":row[1]/t}
    except Exception:
        p = dict(_DEFAULT_BAT)
    _BAT_CACHE[name] = p
    return p


def _fetch_bowler(name: str, phase: str) -> dict:
    key = (name, phase)
    if key in _BOWL_CACHE:
        return _BOWL_CACHE[key]
    o_ranges = {"Powerplay":(0,5),"Middle":(6,14),"Death":(15,19)}
    o_lo,o_hi = o_ranges.get(phase,(6,14))
    sc = _sc(5)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT count(*),
                   sum(CASE WHEN extras_wides>0                                        THEN 1 ELSE 0 END),
                   sum(CASE WHEN extras_wides=0 AND runs_batter=0 AND is_wicket=0     THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=1  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=2  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=3  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=4  THEN 1 ELSE 0 END),
                   sum(CASE WHEN runs_batter=6  THEN 1 ELSE 0 END),
                   sum(is_wicket)
            FROM deliveries
            WHERE LOWER(bowler) LIKE LOWER('%{name}%')
              AND over BETWEEN {o_lo} AND {o_hi} {sc}
        """).fetchone()
        con.close()
        t = max(row[0] or 1, 1)
        p = {"dot":row[2]/t,"1":row[3]/t,"2":row[4]/t,"3":row[5]/t,
             "4":row[6]/t,"6":row[7]/t,"wicket":row[8]/t,"wide":row[1]/t}
    except Exception:
        p = dict(_DEFAULT_BOWL)
    _BOWL_CACHE[key] = p
    return p


def _fetch_venue_mult(venue: str) -> float:
    if venue in _VENUE_MULT:
        return _VENUE_MULT[venue]
    sc = _sc(5)
    vf = f"AND LOWER(venue) LIKE LOWER('%{venue}%')" if venue and venue != "All Venues" else ""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT avg(t) FROM (
                SELECT match_id, sum(runs_batter+extras_wides+extras_noballs) as t
                FROM deliveries WHERE season>0 {sc} {vf}
                GROUP BY match_id HAVING sum(runs_batter)>30)
        """).fetchone()
        con.close()
        mult = (row[0] or 165) / 165.0
    except Exception:
        mult = 1.0
    _VENUE_MULT[venue] = mult
    return mult


# ─────────────────────────────────────────────────────────────────────────────
# PRE-FETCH ALL PROFILES  (call once before simulation loop)
# ─────────────────────────────────────────────────────────────────────────────
def prefetch_profiles(bowling_plan: list, batting_lineup: list, venue: str):
    """
    Fetch all DB data needed for the simulation.
    After this, _simulate_once has ZERO DB calls.
    """
    for bat in set(batting_lineup):
        _fetch_batsman(bat)
    for bowl in set(bowling_plan):
        for ph in ["Powerplay","Middle","Death"]:
            _fetch_bowler(bowl, ph)
    _fetch_venue_mult(venue)


# ─────────────────────────────────────────────────────────────────────────────
# BLEND PROFILES  (pure numpy, no I/O)
# ─────────────────────────────────────────────────────────────────────────────
def _blend(bat: dict, bowl: dict) -> np.ndarray:
    keys = ["dot","1","2","3","4","6","wicket","wide"]
    b  = np.array([bat.get(k, 0) for k in keys], dtype=float)
    w  = np.array([bowl.get(k, 0) for k in keys], dtype=float)
    p  = 0.5 * b + 0.5 * w
    p  = np.clip(p, 1e-6, 1.0)
    return p / p.sum()


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE SIMULATION  —  ZERO DB CALLS, pure numpy
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_once(
    bowling_plan    : list,
    batting_lineup  : list,
    start_over      : int,
    start_score     : int,
    start_wickets   : int,
    venue_mult      : float,      # pre-fetched
    rng             : np.random.Generator,
) -> dict:

    lineup        = list(batting_lineup)
    score         = start_score
    wickets       = start_wickets
    striker_idx   = 0
    nonstr_idx    = 1
    next_bat_idx  = 2
    over_scores   = []

    for over_i, bowler in enumerate(bowling_plan):
        over_num = start_over + over_i
        if wickets >= 10:
            break

        phase = ("Powerplay" if over_num <= 5
                 else "Death" if over_num >= 15
                 else "Middle")

        striker = lineup[striker_idx] if striker_idx < len(lineup) else "Generic"

        bat_p  = _BAT_CACHE.get(striker,  _DEFAULT_BAT)
        bowl_p = _BOWL_CACHE.get((bowler, phase),
                 _BOWL_CACHE.get((bowler, "Middle"), _DEFAULT_BOWL))

        probs = _blend(bat_p, bowl_p)

        # Venue adjustment — shift dots → boundaries at high-scoring grounds
        if venue_mult > 1.02:
            shift      = min(0.04, (venue_mult - 1.0) * 0.2)
            probs[4]  += shift          # index 4 = "4"
            probs[5]  += shift          # index 5 = "6"
            probs[0]  -= shift * 2      # index 0 = "dot"
            probs      = np.clip(probs, 1e-6, 1.0)
            probs     /= probs.sum()

        over_runs    = 0
        over_wickets = 0
        events       = []
        legal_balls  = 0          # counts LEGAL deliveries only

        # ── Bowl the over: continue until 6 LEGAL balls ──
        while legal_balls < 6 and wickets < 10:
            idx     = rng.choice(8, p=probs)
            outcome = OUTCOMES[idx]
            runs    = RUNS_MAP[outcome]

            if outcome == "wide":
                # Wide: extra run, ball NOT counted, over continues
                score     += 1
                over_runs += 1
                events.append({"ball": legal_balls + 1, "outcome": "Wd", "runs": 1})
                # Do NOT increment legal_balls

            elif outcome == "wicket":
                wickets      += 1
                over_wickets += 1
                legal_balls  += 1          # wicket IS a legal delivery
                events.append({"ball": legal_balls, "outcome": "W", "runs": 0})
                # Bring in next batsman
                if next_bat_idx < len(lineup):
                    lineup[striker_idx] = lineup[next_bat_idx]
                    next_bat_idx += 1
                else:
                    lineup[striker_idx] = "Tailender"
                # New batsman faces next ball (no strike rotation after wicket)

            else:
                score       += runs
                over_runs   += runs
                legal_balls += 1
                events.append({"ball": legal_balls, "outcome": outcome, "runs": runs})
                # Rotate strike on odd runs
                if runs % 2 == 1:
                    striker_idx, nonstr_idx = nonstr_idx, striker_idx

        # End of over — automatic strike rotation
        striker_idx, nonstr_idx = nonstr_idx, striker_idx

        over_scores.append({
            "over"              : over_num + 1,
            "runs"              : over_runs,
            "wickets"           : over_wickets,
            "cumulative_score"  : score,
            "cumulative_wickets": wickets,
            "bowler"            : bowler,
            "events"            : events,
        })

    return {"final_score": score, "final_wickets": wickets, "over_scores": over_scores}


# ─────────────────────────────────────────────────────────────────────────────
# MONTE CARLO ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def run_simulation(
    bowling_plan    : list,
    batting_lineup  : list,
    start_over      : int   = 0,
    start_score     : int   = 0,
    start_wickets   : int   = 0,
    venue           : str   = "All Venues",
    n_sims          : int   = N_SIMS,
    label           : str   = "Plan",
) -> dict:

    # ── Step 1: Fetch ALL data from DB (happens once) ──
    prefetch_profiles(bowling_plan, batting_lineup, venue)
    venue_mult = _fetch_venue_mult(venue)

    rng     = np.random.default_rng(seed=42)
    n_overs = len(bowling_plan)

    all_finals       = np.empty(n_sims, dtype=float)
    over_runs_matrix = np.empty((n_sims, n_overs), dtype=float)

    # ── Step 2: Run simulations — ZERO DB calls ──
    for i in range(n_sims):
        result = _simulate_once(
            bowling_plan, batting_lineup,
            start_over, start_score, start_wickets,
            venue_mult, rng)

        all_finals[i] = result["final_score"]
        row = [o["cumulative_score"] for o in result["over_scores"]]
        # Pad if innings ended early (all out)
        while len(row) < n_overs:
            row.append(row[-1] if row else start_score)
        over_runs_matrix[i] = row[:n_overs]

    # ── Step 3: Statistics ──
    overs_list = list(range(start_over + 1, start_over + n_overs + 1))

    # Representative innings = the simulation closest to median
    median_idx = int(np.argsort(all_finals)[n_sims // 2])
    rep_rng    = np.random.default_rng(seed=median_idx)
    rep        = _simulate_once(
        bowling_plan, batting_lineup,
        start_over, start_score, start_wickets,
        venue_mult, rep_rng)

    return {
        "label"     : label,
        "n_sims"    : n_sims,
        "overs"     : overs_list,

        # Score summary
        "predicted" : int(np.median(all_finals)),
        "mean"      : int(np.mean(all_finals)),
        "p10"       : int(np.percentile(all_finals, 10)),
        "p25"       : int(np.percentile(all_finals, 25)),
        "p75"       : int(np.percentile(all_finals, 75)),
        "p90"       : int(np.percentile(all_finals, 90)),
        "std"       : round(float(np.std(all_finals)), 1),

        # Over bands
        "over_p10"  : np.percentile(over_runs_matrix, 10, axis=0).tolist(),
        "over_p25"  : np.percentile(over_runs_matrix, 25, axis=0).tolist(),
        "over_p50"  : np.percentile(over_runs_matrix, 50, axis=0).tolist(),
        "over_p75"  : np.percentile(over_runs_matrix, 75, axis=0).tolist(),
        "over_p90"  : np.percentile(over_runs_matrix, 90, axis=0).tolist(),

        # Full distribution for histogram / win prob
        "finals_arr" : all_finals.tolist(),

        # Representative scorecard
        "rep_innings": rep["over_scores"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPARISON + WIN PROBABILITY
# ─────────────────────────────────────────────────────────────────────────────
def compare_plans(result_a: dict, result_b: dict) -> dict:
    a = np.array(result_a["finals_arr"])
    b = np.array(result_b["finals_arr"])
    d = b - a
    return {
        "plan_a_label" : result_a["label"],
        "plan_b_label" : result_b["label"],
        "a_median"     : result_a["predicted"],
        "b_median"     : result_b["predicted"],
        "diff_median"  : int(np.median(d)),
        "b_better_pct" : round(float(np.mean(b > a) * 100), 1),
        "a_better_pct" : round(float(np.mean(a > b) * 100), 1),
    }


def win_probability(result: dict, target: int) -> float:
    if not target:
        return 0.0
    return round(float(np.mean(np.array(result["finals_arr"]) >= target) * 100), 1)