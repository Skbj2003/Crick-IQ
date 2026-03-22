"""
analytics.py
────────────
Three advanced IPL analytics modules:

  1. Player Form Tracker   — match-by-match runs/wickets + rolling average
  2. Bowler Phase Analysis — economy & wickets across powerplay/middle/death
  3. Phase Scoring Chart   — batsman strike rate & runs by phase (radar + bar)

All functions return plain DataFrames — charts are built in app.py with Plotly.
"""

import duckdb
import pandas as pd

DB_PATH = "ipl_tactics.db"


# ─────────────────────────────────────────────────────────────────────────────
# 1. PLAYER FORM TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def get_batsman_form(player: str, season: int = 0, last_n: int = 20) -> pd.DataFrame:
    """
    Returns match-by-match batting stats for a player.
    Columns: match_id, season, runs, balls, sr, fours, sixes, dismissed
    Sorted oldest → newest.  last_n limits to most recent N matches.
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            match_id,
            season,
            sum(runs_batter)                                                                       AS runs,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                            AS balls,
            round(sum(runs_batter)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                        AS sr,
            sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END)                                        AS fours,
            sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END)                                        AS sixes,
            max(is_wicket)                                                                         AS dismissed
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{player}%')
          {sf}
        GROUP BY match_id, season
        ORDER BY season ASC, match_id ASC
    """).df()
    con.close()

    if df.empty:
        return df

    # Keep last N matches
    df = df.tail(last_n).reset_index(drop=True)
    df["match_num"] = range(1, len(df) + 1)

    # Rolling average (window=5)
    df["rolling_avg"] = df["runs"].rolling(window=5, min_periods=1).mean().round(1)

    # Career average for reference line
    df["career_avg"] = round(df["runs"].mean(), 1)

    return df


def get_bowler_form(player: str, season: int = 0, last_n: int = 20) -> pd.DataFrame:
    """
    Returns match-by-match bowling stats.
    Columns: match_id, season, wickets, runs_conceded, balls, economy, dismissed
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            match_id,
            season,
            sum(is_wicket)                                                                         AS wickets,
            sum(runs_batter + extras_wides + extras_noballs)                                       AS runs_conceded,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                            AS balls,
            round((sum(runs_batter + extras_wides + extras_noballs)*6.0) /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 2)                        AS economy
        FROM deliveries
        WHERE LOWER(bowler) LIKE LOWER('%{player}%')
          {sf}
        GROUP BY match_id, season
        ORDER BY season ASC, match_id ASC
    """).df()
    con.close()

    if df.empty:
        return df

    df = df.tail(last_n).reset_index(drop=True)
    df["match_num"] = range(1, len(df) + 1)
    df["rolling_wickets"] = df["wickets"].rolling(window=5, min_periods=1).mean().round(2)
    df["rolling_economy"] = df["economy"].rolling(window=5, min_periods=1).mean().round(2)
    df["career_avg_wkts"]  = round(df["wickets"].mean(), 2)

    return df


def get_form_summary(player: str, role: str = "batsman", season: int = 0) -> dict:
    """
    Returns a summary dict with hot/cold streak detection.
    role: 'batsman' or 'bowler'
    """
    if role == "batsman":
        df = get_batsman_form(player, season, last_n=5)
        if df.empty:
            return {}
        avg5     = round(df["runs"].mean(), 1)
        all_df   = get_batsman_form(player, 0, last_n=100)
        career   = round(all_df["runs"].mean(), 1) if not all_df.empty else 0
        streak   = "🔥 HOT" if avg5 > career * 1.25 else ("❄️ COLD" if avg5 < career * 0.6 else "📊 NORMAL")
        return {"last5_avg": avg5, "career_avg": career, "streak": streak,
                "last5_runs": df["runs"].tolist(), "matches": len(df)}
    else:
        df = get_bowler_form(player, season, last_n=5)
        if df.empty:
            return {}
        avg5_wkts = round(df["wickets"].mean(), 2)
        avg5_eco  = round(df["economy"].mean(), 2)
        all_df    = get_bowler_form(player, 0, last_n=100)
        career_eco = round(all_df["economy"].mean(), 2) if not all_df.empty else 8.0
        streak = "🔥 HOT" if (avg5_eco < career_eco * 0.85) else ("❄️ COLD" if avg5_eco > career_eco * 1.2 else "📊 NORMAL")
        return {"last5_wkts": avg5_wkts, "last5_eco": avg5_eco,
                "career_eco": career_eco, "streak": streak, "matches": len(df)}


# ─────────────────────────────────────────────────────────────────────────────
# 2. BOWLER PHASE ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def get_bowler_phase_stats(bowler: str, season: int = 0) -> pd.DataFrame:
    """
    Returns economy, wickets, dot%, balls for each over phase.
    Phases: Powerplay (1-6), Middle (7-15), Death (16-20)
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            CASE
                WHEN over BETWEEN 0 AND 5  THEN 'Powerplay'
                WHEN over BETWEEN 6 AND 14 THEN 'Middle'
                ELSE 'Death'
            END AS phase,
            CASE
                WHEN over BETWEEN 0 AND 5  THEN 1
                WHEN over BETWEEN 6 AND 14 THEN 2
                ELSE 3
            END AS phase_order,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                                AS balls,
            sum(runs_batter + extras_wides + extras_noballs)                                          AS runs_conceded,
            sum(is_wicket)                                                                            AS wickets,
            round((sum(runs_batter + extras_wides + extras_noballs)*6.0) /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 2)                           AS economy,
            round(sum(CASE WHEN runs_batter=0 AND extras_wides=0 THEN 1 ELSE 0 END)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS dot_pct,
            round(sum(is_wicket)*6.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS wickets_per_over,
            count(DISTINCT match_id)                                                                  AS matches
        FROM deliveries
        WHERE LOWER(bowler) LIKE LOWER('%{bowler}%')
          {sf}
        GROUP BY phase, phase_order
        ORDER BY phase_order
    """).df()
    con.close()
    return df


def get_bowler_over_by_over(bowler: str, season: int = 0) -> pd.DataFrame:
    """
    Economy and wickets for EACH over number (1-20).
    Good for sparkline / granular phase chart.
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            over + 1                                                                                  AS over_num,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                               AS balls,
            sum(runs_batter + extras_wides + extras_noballs)                                          AS runs_conceded,
            sum(is_wicket)                                                                            AS wickets,
            round((sum(runs_batter + extras_wides + extras_noballs)*6.0) /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 2)                           AS economy,
            round(sum(CASE WHEN runs_batter=0 AND extras_wides=0 THEN 1 ELSE 0 END)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS dot_pct
        FROM deliveries
        WHERE LOWER(bowler) LIKE LOWER('%{bowler}%')
          {sf}
        GROUP BY over_num
        ORDER BY over_num
    """).df()
    con.close()
    return df


def get_bowler_vs_teams(bowler: str, season: int = 0) -> pd.DataFrame:
    """Economy and wickets against each team — for weakness/strength table."""
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            batting_team                                                                              AS team,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                               AS balls,
            sum(is_wicket)                                                                            AS wickets,
            round((sum(runs_batter + extras_wides + extras_noballs)*6.0) /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 2)                           AS economy,
            count(DISTINCT match_id)                                                                  AS matches
        FROM deliveries
        WHERE LOWER(bowler) LIKE LOWER('%{bowler}%')
          {sf}
        GROUP BY batting_team
        HAVING count(CASE WHEN extras_wides=0 THEN 1 END) >= 12
        ORDER BY economy ASC
    """).df()
    con.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. PHASE SCORING CHART (Batsman)
# ─────────────────────────────────────────────────────────────────────────────

def get_batsman_phase_stats(batsman: str, season: int = 0) -> pd.DataFrame:
    """
    Runs, balls, SR, boundary%, dot% for each phase.
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            CASE
                WHEN over BETWEEN 0 AND 5  THEN 'Powerplay'
                WHEN over BETWEEN 6 AND 14 THEN 'Middle'
                ELSE 'Death'
            END AS phase,
            CASE
                WHEN over BETWEEN 0 AND 5  THEN 1
                WHEN over BETWEEN 6 AND 14 THEN 2
                ELSE 3
            END AS phase_order,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                                AS balls,
            sum(runs_batter)                                                                           AS runs,
            round(sum(runs_batter)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS sr,
            round(sum(CASE WHEN runs_batter IN (4,6) THEN 1 ELSE 0 END)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS boundary_pct,
            round(sum(CASE WHEN runs_batter=0 AND extras_wides=0 THEN 1 ELSE 0 END)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS dot_pct,
            sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END)                                           AS fours,
            sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END)                                           AS sixes,
            sum(is_wicket)                                                                            AS dismissals,
            count(DISTINCT match_id)                                                                  AS matches
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{batsman}%')
          {sf}
        GROUP BY phase, phase_order
        ORDER BY phase_order
    """).df()
    con.close()
    return df


def get_batsman_over_by_over(batsman: str, season: int = 0) -> pd.DataFrame:
    """Strike rate and runs for each over number."""
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT
            over + 1                                                                                   AS over_num,
            sum(runs_batter)                                                                           AS runs,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                                AS balls,
            round(sum(runs_batter)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                           AS sr,
            sum(is_wicket)                                                                            AS dismissals
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{batsman}%')
          {sf}
        GROUP BY over_num
        ORDER BY over_num
    """).df()
    con.close()
    return df


def get_batsman_vs_bowler_types(batsman: str, season: int = 0) -> pd.DataFrame:
    """
    Batsman performance split by inferred bowler type.
    Uses naming heuristics: names ending in typical spin/pace patterns.
    """
    sf = f"AND season = {int(season)}" if season else ""
    con = duckdb.connect(DB_PATH, read_only=True)

    # Pull all bowlers this batsman has faced with enough balls
    df = con.execute(f"""
        SELECT
            bowler,
            count(CASE WHEN extras_wides=0 THEN 1 END)                                               AS balls,
            sum(runs_batter)                                                                          AS runs,
            round(sum(runs_batter)*100.0 /
                  NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0), 1)                          AS sr,
            sum(is_wicket)                                                                           AS dismissals
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{batsman}%')
          {sf}
        GROUP BY bowler
        HAVING count(CASE WHEN extras_wides=0 THEN 1 END) >= 6
        ORDER BY balls DESC
    """).df()
    con.close()
    return df