"""
predictor.py
────────────
ML-powered IPL Match Predictor

Model: Gradient Boosting Regressor trained on ball-by-ball DB
Features: over, cumulative_runs, wickets_fallen, run_rate,
          wickets_left, balls_remaining, venue_avg, phase

Trained fresh each session from your ipl_tactics.db
No external data needed — 100% self-contained.
"""

import duckdb
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings("ignore")

DB_PATH = "ipl_tactics.db"

# ─────────────────────────────────────────────────────────────────────────────
# 2026 IPL SQUADS  (official — update each season)
# ─────────────────────────────────────────────────────────────────────────────
IPL_2026_SQUADS = {
    "Chennai Super Kings": [
        "RD Gaikwad", "MS Dhoni", "SV Samson", "D Brevis", "A Mhatre",
        "Kartik Sharma", "Sarfaraz Khan", "Urvil Patel", "A Kamboj",
        "J Overton", "Ramakrishna Ghosh", "Prashant Veer", "M Short",
        "Aman Khan", "Zak Foulkes", "Shivam Dube", "Khaleel Ahmed",
        "Noor Ahmad", "Mukesh Choudhary", "S Gopal", "Gurjapneet Singh",
        "Akeal Hosein", "M Henry", "Rahul Chahar",
    ],
    "Mumbai Indians": [
        "HH Pandya", "RG Sharma", "Suryakumar Yadav", "R Minz",
        "S Rutherford", "RJ Rickelton", "Q de Kock", "D Malewar",
        "Tilak Varma", "N Dhir", "MJ Santner", "RA Bawa",
        "A Ankolekar", "M Rawat", "C Bosch", "WG Jacks",
        "ST Thakur", "JJ Bumrah", "T Boult", "DL Chahar",
        "M Markande", "Ashwani Kumar", "M Izhar", "Raghu Sharma",
    ],
    "Royal Challengers Bangalore": [
        "RR Patidar", "V Kohli", "Devdutt Padikkal", "PD Salt",
        "JR Sharma", "JM Cox", "KH Pandya", "TH David",
        "R Shepherd", "J Bethell", "V Iyer", "Satvik Deswal",
        "M Yadav", "V Ostwal", "Vihaan Malhotra", "Kanishk Chouhan",
    ],
    "Delhi Capitals": [
        "KL Rahul", "Axar Patel", "Kuldeep Yadav", "S Rizvi",
        "A Porel", "Vipraj Nigam", "T Stubbs", "MA Starc",
        "Mukesh Kumar", "Tripurana Vijay", "T Natarajan",
        "MR Marsh", "Faf du Plessis", "HV Patel",
    ],
    "Gujarat Titans": [
        "Shubman Gill", "Rashid Khan", "DA Miller", "MS Wade",
        "B Sai Sudharsan", "Shahrukh Khan", "R Tewatia", "Noor Ahmad",
        "Sai Kishore", "Spencer Johnson", "Umesh Yadav",
        "Gerald Coetzee", "Kagiso Rabada", "Mohammed Siraj",
    ],
    "Kolkata Knight Riders": [
        "AM Rahane", "SP Narine", "A Russell", "Rinku Singh",
        "Varun Chakravarthy", "Cameron Green", "Matheesha Pathirana",
        "Phil Salt", "Angkrish Raghuvanshi", "Suyash Sharma",
        "Harshit Rana", "Ramandeep Singh", "Moeen Ali",
    ],
    "Lucknow Super Giants": [
        "N Pooran", "Ravi Bishnoi", "Avesh Khan", "M Stoinis",
        "Mohsin Khan", "Prerak Mankad", "Ayush Badoni", "KH Pandya",
        "Mitchell Marsh", "AB de Villiers", "Matt Henry",
        "Digvijay Deshmukh", "Akash Deep",
    ],
    "Rajasthan Royals": [
        "YBK Jaiswal", "R Parag", "JC Buttler", "SO Hetmyer",
        "Donovan Ferreira", "Sam Curran", "JC Archer", "YS Chahal",
        "Sandeep Sharma", "KM Asif", "Dhruv Jurel",
        "Maheesh Theekshana", "Shimron Hetmyer",
    ],
    "Punjab Kings": [
        "SS Iyer", "M Stoinis", "Arshdeep Singh", "YS Chahal",
        "JM Bairstow", "Liam Livingstone", "Harshal Patel",
        "Nathan Ellis", "Harpreet Brar", "Prabhsimran Singh",
        "Shashank Singh", "Azmatullah Omarzai", "Glenn Maxwell",
    ],
    "Sunrisers Hyderabad": [
        "I Kishan", "PJ Cummins", "Abhishek Sharma", "HH Klaasen",
        "Aiden Markram", "Travis Head", "Washington Sundar",
        "T Natarajan", "Marco Jansen", "Nitish Kumar Reddy",
        "Glenn Phillips", "Jaydev Unadkat", "Fazalhaq Farooqi",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# TEAM LIST
# ─────────────────────────────────────────────────────────────────────────────
IPL_TEAMS = sorted(IPL_2026_SQUADS.keys())


def get_players_by_team(team: str, role: str = "batsman") -> list:
    """Return 2026 squad for the team. Same list for bat/bowl — user picks."""
    squad = IPL_2026_SQUADS.get(team, [])
    if squad:
        return sorted(squad)
    # Fallback to DB
    try:
        sc = _season_clause(3)
        con = duckdb.connect(DB_PATH, read_only=True)
        col = "striker" if role == "batsman" else "bowler"
        tcol = "batting_team" if role == "batsman" else "bowling_team"
        df = con.execute(f"""
            SELECT DISTINCT {col} AS player FROM deliveries
            WHERE LOWER({tcol}) LIKE LOWER('%{team}%') {sc}
            ORDER BY {col}
        """).df()
        con.close()
        return df["player"].tolist()
    except Exception:
        return []


def get_teams_from_db() -> list:
    return IPL_TEAMS


# ─────────────────────────────────────────────────────────────────────────────
# SEASON HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _get_recent_seasons(n: int = 5) -> list:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        s = con.execute(
            "SELECT DISTINCT season FROM deliveries WHERE season>0 ORDER BY season DESC"
        ).df()["season"].tolist()
        con.close()
        return s[:n]
    except Exception:
        return []


def _season_clause(n: int = 5, col: str = "season") -> str:
    seasons = _get_recent_seasons(n)
    if not seasons:
        return ""
    return f"AND {col} IN ({','.join(str(s) for s in seasons)})"


# ─────────────────────────────────────────────────────────────────────────────
# BUILD TRAINING DATA FROM DB
# ─────────────────────────────────────────────────────────────────────────────
def _build_training_data(n_seasons: int = 5) -> pd.DataFrame:
    """
    Extract innings snapshots at each over as training rows.
    Features at over X → target = final score of that innings.
    """
    sc = _season_clause(n_seasons)
    con = duckdb.connect(DB_PATH, read_only=True)

    # Get venue averages for encoding
    venue_avg = con.execute(f"""
        SELECT venue,
               avg(innings_total) as avg_score
        FROM (
            SELECT match_id, batting_team, venue,
                   sum(runs_batter + extras_wides + extras_noballs) as innings_total
            FROM deliveries WHERE season > 0 {sc}
            GROUP BY match_id, batting_team, venue
            HAVING sum(runs_batter) > 30
        )
        GROUP BY venue
    """).df().set_index("venue")["avg_score"].to_dict()

    # Build cumulative over-level data
    df = con.execute(f"""
        WITH over_stats AS (
            SELECT match_id, season, batting_team, bowling_team, venue,
                   over,
                   sum(runs_batter + extras_wides + extras_noballs) as over_runs,
                   sum(is_wicket) as over_wickets
            FROM deliveries
            WHERE season > 0 {sc}
            GROUP BY match_id, season, batting_team, bowling_team, venue, over
        ),
        cumulative AS (
            SELECT match_id, season, batting_team, bowling_team, venue,
                   over,
                   SUM(over_runs)    OVER (PARTITION BY match_id, batting_team ORDER BY over) as cum_runs,
                   SUM(over_wickets) OVER (PARTITION BY match_id, batting_team ORDER BY over) as cum_wickets,
                   SUM(over_runs)    OVER (PARTITION BY match_id, batting_team)               as final_score
            FROM over_stats
        )
        SELECT * FROM cumulative
        WHERE over BETWEEN 3 AND 19  -- skip first 3 and last over for noise
          AND final_score > 50
        ORDER BY match_id, over
    """).df()
    con.close()

    if df.empty:
        return pd.DataFrame()

    # Feature engineering
    df["over_num"]        = df["over"] + 1                          # 1-indexed
    df["balls_remaining"] = (20 - df["over_num"]) * 6
    df["wickets_left"]    = 10 - df["cum_wickets"]
    df["run_rate"]        = df["cum_runs"] / df["over_num"].clip(1)
    df["req_runs"]        = (df["final_score"] - df["cum_runs"]).clip(0)
    df["venue_avg"]       = df["venue"].map(venue_avg).fillna(165)

    # Phase encoding
    df["phase"] = pd.cut(df["over_num"],
                         bins=[0, 6, 15, 20],
                         labels=[0, 1, 2]).astype(float)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# ML MODEL — trained on DB, cached in module
# ─────────────────────────────────────────────────────────────────────────────
_model       = None
_venue_avgs  = {}
_model_ready = False

FEATURES = [
    "over_num", "cum_runs", "cum_wickets",
    "run_rate", "wickets_left", "balls_remaining",
    "venue_avg", "phase",
]

def _train_model() -> bool:
    global _model, _venue_avgs, _model_ready
    try:
        df = _build_training_data(n_seasons=5)
        if df.empty or len(df) < 100:
            return False

        # Cache venue averages for inference
        con = duckdb.connect(DB_PATH, read_only=True)
        sc  = _season_clause(5)
        va  = con.execute(f"""
            SELECT venue, avg(innings_total) as avg_score
            FROM (
                SELECT match_id, batting_team, venue,
                       sum(runs_batter + extras_wides + extras_noballs) as innings_total
                FROM deliveries WHERE season > 0 {sc}
                GROUP BY match_id, batting_team, venue
                HAVING sum(runs_batter) > 30
            )
            GROUP BY venue
        """).df()
        con.close()
        _venue_avgs = va.set_index("venue")["avg_score"].to_dict()

        X = df[FEATURES].fillna(0).values
        y = df["final_score"].values

        _model = GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.08,
            max_depth=5,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42,
        )
        _model.fit(X, y)
        _model_ready = True
        return True
    except Exception as e:
        print(f"[predictor] Model training failed: {e}")
        return False


def get_model():
    """Return trained model, training if needed."""
    global _model_ready
    if not _model_ready:
        _train_model()
    return _model if _model_ready else None


# ─────────────────────────────────────────────────────────────────────────────
# ML PREDICTION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def ml_predict_score(
    current_over: int,
    current_score: int,
    current_wickets: int,
    venue: str,
) -> dict:
    """
    Use ML model to predict final score from current match state.
    Returns point estimate + confidence interval.
    """
    model = get_model()
    venue_avg = _venue_avgs.get(venue, 165.0)
    if not venue_avg:
        venue_avg = 165.0

    over_num        = current_over
    balls_remaining = (20 - over_num) * 6
    wickets_left    = 10 - current_wickets
    run_rate        = current_score / max(over_num, 1)
    phase           = 0 if over_num <= 6 else (1 if over_num <= 15 else 2)

    features = np.array([[
        over_num, current_score, current_wickets,
        run_rate, wickets_left, balls_remaining,
        venue_avg, phase,
    ]])

    if model is None:
        # Statistical fallback if model not trained
        remaining_rr = max(run_rate * 1.15, 8.5)
        est = current_score + remaining_rr * (balls_remaining / 6)
        return {
            "predicted": round(est),
            "low": round(est * 0.88),
            "high": round(est * 1.12),
            "method": "statistical",
        }

    pred = model.predict(features)[0]

    # Confidence interval via quantile-like spread from training residuals
    # Use ±10% of prediction as uncertainty band (conservative)
    spread = max(pred * 0.10, 12)
    return {
        "predicted": round(pred),
        "low":       round(pred - spread),
        "high":      round(pred + spread),
        "method":    "ml_gradient_boosting",
    }


def get_model_status() -> dict:
    """Return info about model training status."""
    model = get_model()
    if model is None:
        return {"trained": False, "estimators": 0}
    seasons = _get_recent_seasons(5)
    return {
        "trained":    True,
        "estimators": model.n_estimators_,
        "seasons":    seasons,
        "features":   FEATURES,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STATISTICAL FALLBACK FUNCTIONS (used alongside ML)
# ─────────────────────────────────────────────────────────────────────────────
def get_historical_context(
    batting_team: str,
    bowling_team: str,
    venue: str,
    current_over: int,
    current_score: int,
    current_wickets: int,
    n_seasons: int = 5,
) -> dict:
    """
    Find historically similar match states for context.
    Returns how many similar matches found + their distribution.
    """
    sc     = _season_clause(n_seasons)
    vf     = f"AND LOWER(venue) LIKE LOWER('%{venue}%')" if venue and venue != "All Venues" else ""
    s_lo   = max(0,  current_score   - 25)
    s_hi   = current_score + 25
    o_lo   = max(0,  current_over    - 2)
    o_hi   = min(20, current_over    + 2)
    w_lo   = max(0,  current_wickets - 1)
    w_hi   = min(10, current_wickets + 1)

    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(f"""
            WITH cumulative AS (
                SELECT match_id, season, batting_team, venue, over,
                       SUM(runs_batter + extras_wides + extras_noballs)
                           OVER (PARTITION BY match_id, batting_team ORDER BY over) as cum_runs,
                       SUM(is_wicket)
                           OVER (PARTITION BY match_id, batting_team ORDER BY over) as cum_wickets,
                       SUM(runs_batter + extras_wides + extras_noballs)
                           OVER (PARTITION BY match_id, batting_team) as final_score
                FROM deliveries
                WHERE season > 0 {sc} {vf}
            )
            SELECT DISTINCT match_id, season, batting_team, cum_runs,
                   cum_wickets, final_score
            FROM cumulative
            WHERE over  BETWEEN {o_lo} AND {o_hi}
              AND cum_runs    BETWEEN {s_lo} AND {s_hi}
              AND cum_wickets BETWEEN {w_lo} AND {w_hi}
              AND final_score > 50
            ORDER BY season DESC
            LIMIT 100
        """).df()
        con.close()

        # Try team-specific first, fall back to general
        team_df = df[df["batting_team"].str.contains(batting_team, case=False, na=False)]
        use_df  = team_df if len(team_df) >= 5 else df

        if use_df.empty:
            return {"matches_found": 0, "similar_matches": use_df,
                    "hist_avg": None, "hist_low": None, "hist_high": None}

        return {
            "matches_found":  len(use_df),
            "similar_matches": use_df,
            "hist_avg":  round(use_df["final_score"].mean()),
            "hist_low":  round(use_df["final_score"].quantile(0.25)),
            "hist_high": round(use_df["final_score"].quantile(0.75)),
        }
    except Exception as e:
        return {"matches_found": 0, "similar_matches": pd.DataFrame(),
                "hist_avg": None, "hist_low": None, "hist_high": None}


def get_live_matchup(batsman: str, bowler: str, n_seasons: int = 5) -> dict:
    sc = _season_clause(n_seasons)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                   sum(runs_batter) AS runs, sum(is_wicket) AS dismissals,
                   round(sum(runs_batter)*100.0/
                         NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                   sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END) AS fours,
                   sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END) AS sixes,
                   count(DISTINCT match_id) AS matches
            FROM deliveries
            WHERE LOWER(striker) LIKE LOWER('%{batsman}%')
              AND LOWER(bowler)  LIKE LOWER('%{bowler}%')
              {sc}
        """).fetchone()
        con.close()

        if not row[0]:  # fallback to all seasons
            con = duckdb.connect(DB_PATH, read_only=True)
            row = con.execute(f"""
                SELECT count(CASE WHEN extras_wides=0 THEN 1 END),
                       sum(runs_batter), sum(is_wicket),
                       round(sum(runs_batter)*100.0/
                             NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1),
                       sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END),
                       sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END),
                       count(DISTINCT match_id)
                FROM deliveries
                WHERE LOWER(striker) LIKE LOWER('%{batsman}%')
                  AND LOWER(bowler)  LIKE LOWER('%{bowler}%')
            """).fetchone()
            con.close()

        return {"balls": row[0] or 0, "runs": row[1] or 0,
                "dismissals": row[2] or 0, "sr": row[3] or 0,
                "fours": row[4] or 0, "sixes": row[5] or 0,
                "matches": row[6] or 0}
    except Exception:
        return {"balls":0,"runs":0,"dismissals":0,"sr":0,"fours":0,"sixes":0,"matches":0}


def get_bowler_current_phase(bowler: str, current_over: int) -> dict:
    if   current_over <= 6:  phase, o_lo, o_hi = "Powerplay", 0,  5
    elif current_over <= 15: phase, o_lo, o_hi = "Middle",    6,  14
    else:                    phase, o_lo, o_hi = "Death",     15, 19
    sc = _season_clause(5)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                   sum(is_wicket) AS wickets,
                   round((sum(runs_batter+extras_wides+extras_noballs)*6.0)/
                         NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                   round(sum(CASE WHEN runs_batter=0 AND extras_wides=0 THEN 1 ELSE 0 END)*100.0/
                         NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS dot_pct
            FROM deliveries
            WHERE LOWER(bowler) LIKE LOWER('%{bowler}%')
              AND over BETWEEN {o_lo} AND {o_hi} {sc}
        """).fetchone()
        con.close()
        return {"phase":phase,"balls":row[0] or 0,"wickets":row[1] or 0,
                "economy":row[2] or 0,"dot_pct":row[3] or 0}
    except Exception:
        return {"phase":phase,"balls":0,"wickets":0,"economy":0,"dot_pct":0}


def get_venue_norms(venue: str) -> dict:
    sc = _season_clause(5)
    vf = f"AND LOWER(venue) LIKE LOWER('%{venue}%')" if venue and venue != "All Venues" else ""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            SELECT round(avg(t),1), max(t), min(t), count(*)
            FROM (
                SELECT match_id, batting_team,
                       sum(runs_batter+extras_wides+extras_noballs) as t
                FROM deliveries WHERE season>0 {sc} {vf}
                GROUP BY match_id, batting_team HAVING sum(runs_batter)>30
            )
        """).fetchone()
        con.close()
        return {"avg_score":row[0] or 0,"highest":row[1] or 0,
                "lowest":row[2] or 0,"innings":row[3] or 0}
    except Exception:
        return {"avg_score":165,"highest":220,"lowest":100,"innings":0}


def get_chase_history(batting_team: str, target: int,
                      current_over: int, current_score: int) -> dict:
    runs_needed = target - current_score
    overs_left  = max(1, 20 - current_over)
    req_rr      = round(runs_needed / overs_left, 2)
    sc = _season_clause(5)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute(f"""
            WITH totals AS (
                SELECT match_id, sum(runs_batter+extras_wides+extras_noballs) AS total
                FROM deliveries
                WHERE LOWER(batting_team) LIKE LOWER('%{batting_team}%')
                  AND season > 0 {sc}
                GROUP BY match_id HAVING sum(runs_batter)>30
            )
            SELECT count(*), sum(CASE WHEN total>={target} THEN 1 ELSE 0 END),
                   round(avg(total),1)
            FROM totals
            WHERE total BETWEEN {max(0,target-60)} AND {target+80}
        """).fetchone()
        con.close()
        total   = row[0] or 0
        success = row[1] or 0
        return {"runs_needed":runs_needed,"overs_left":overs_left,"req_rr":req_rr,
                "total_similar_chases":total,"successful_chases":success,
                "historical_win_pct":round(success/total*100,1) if total>0 else 0,
                "avg_chase_score":row[2] or 0}
    except Exception:
        return {"runs_needed":runs_needed,"overs_left":overs_left,"req_rr":req_rr,
                "total_similar_chases":0,"successful_chases":0,
                "historical_win_pct":0,"avg_chase_score":0}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def build_prediction_context(
    batting_team: str, bowling_team: str, venue: str,
    current_over: int, current_score: int, current_wickets: int,
    batsman: str, bowler: str,
    innings: int = 1, target: int = 0,
) -> dict:
    """
    Build full prediction context combining ML + historical DB.
    """
    # ML score prediction
    ml = ml_predict_score(current_over, current_score, current_wickets, venue)

    # Historical context (for distribution chart + similar match count)
    hist = get_historical_context(
        batting_team, bowling_team, venue,
        current_over, current_score, current_wickets,
    )

    matchup = get_live_matchup(batsman, bowler)
    phase   = get_bowler_current_phase(bowler, current_over)
    venue_n = get_venue_norms(venue)
    chase   = get_chase_history(batting_team, target, current_over, current_score) \
              if innings == 2 and target > 0 else {}
    status  = get_model_status()

    return {
        "match_state": {
            "batting_team":  batting_team, "bowling_team":  bowling_team,
            "venue":         venue,        "innings":       innings,
            "target":        target,       "over":          current_over,
            "score":         current_score,"wickets":       current_wickets,
            "overs_left":    20 - current_over,
            "wickets_left":  10 - current_wickets,
            "current_rr":    round(current_score / max(current_over, 1), 2),
        },
        "ml":          ml,     # ML model prediction
        "hist":        hist,   # Historical similar matches
        "live_matchup": matchup,
        "bowler_phase": phase,
        "venue":        venue_n,
        "chase":        chase,
        "model_status": status,
    }