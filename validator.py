"""
validator.py
────────────
Data Validation Dashboard — compares your ipl_tactics.db stats
against hardcoded official IPL career reference values.

Reference data sourced from official IPL records (iplt20.com) and
ESPN Cricinfo career statistics pages.

Discrepancy reasons explained inline so users understand WHY they differ.
"""

import duckdb
import pandas as pd

DB_PATH = "ipl_tactics.db"

# ─────────────────────────────────────────────────────────────────────────────
# OFFICIAL REFERENCE DATA
# Source: iplt20.com official records + ESPN Cricinfo (as of IPL 2024)
# These are CAREER IPL totals across all seasons
# ─────────────────────────────────────────────────────────────────────────────
BATTING_REFERENCE = [
    # (player_db_name,    display_name,        official_runs, official_matches)
    ("V Kohli",          "Virat Kohli",         8004,          252),
    ("S Dhawan",         "Shikhar Dhawan",      6769,          222),
    ("RG Sharma",        "Rohit Sharma",        6628,          257),
    ("DA Warner",        "David Warner",        6565,          184),
    ("MS Dhoni",         "MS Dhoni",            5082,          264),
    ("SK Raina",         "Suresh Raina",        5528,          205),
    ("AB de Villiers",   "AB de Villiers",      5162,          184),
    ("CH Gayle",         "Chris Gayle",         4965,          142),
    ("KL Rahul",         "KL Rahul",            4683,          132),
    ("RR Pant",          "Rishabh Pant",        3284,          111),
    ("HH Pandya",        "Hardik Pandya",       2704,          136),
    ("SR Watson",        "Shane Watson",        3874,          145),
    ("AM Rahane",        "Ajinkya Rahane",      4281,          176),
    ("G Gambhir",        "Gautam Gambhir",      4217,          154),
    ("F du Plessis",     "Faf du Plessis",      4247,          143),
]

BOWLING_REFERENCE = [
    # (player_db_name,   display_name,        official_wickets, official_matches)
    ("SL Malinga",       "Lasith Malinga",      170,             122),
    ("DJ Bravo",         "DJ Bravo",            183,             161),
    ("PP Chawla",        "Piyush Chawla",       157,             165),
    ("Harbhajan Singh",  "Harbhajan Singh",     150,             163),
    ("A Mishra",         "Amit Mishra",         166,             154),
    ("JJ Bumrah",        "Jasprit Bumrah",      145,             135),
    ("SP Narine",        "Sunil Narine",        178,             177),
    ("RA Jadeja",        "Ravindra Jadeja",     132,             226),
    ("YS Chahal",        "Yuzvendra Chahal",    187,             148),
    ("Rashid Khan",      "Rashid Khan",         107,              92),
    ("B Kumar",          "Bhuvneshwar Kumar",   158,             176),
    ("UT Yadav",         "Umesh Yadav",         132,             148),
    ("R Ashwin",         "R Ashwin",            157,             206),
    ("DW Steyn",         "Dale Steyn",           97,              95),
]

# Tolerance thresholds for RAG status
GREEN_THRESHOLD  = 0.08   # within 8%  → data matches well
AMBER_THRESHOLD  = 0.20   # within 20% → minor discrepancy
# > 20% → RED → likely name mismatch or missing seasons


# ─────────────────────────────────────────────────────────────────────────────
# QUERY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def validate_batting(con) -> pd.DataFrame:
    rows = []
    for db_name, display, official_runs, official_matches in BATTING_REFERENCE:
        row = con.execute(f"""
            SELECT
                sum(runs_batter)             AS db_runs,
                count(DISTINCT match_id)     AS db_matches
            FROM deliveries
            WHERE LOWER(striker) LIKE LOWER('%{db_name}%')
        """).fetchone()
        db_runs    = int(row[0] or 0)
        db_matches = int(row[1] or 0)
        diff_runs  = db_runs - official_runs
        pct_diff   = abs(diff_runs) / official_runs if official_runs else 0

        if pct_diff <= GREEN_THRESHOLD:
            status = "🟢 MATCH"
        elif pct_diff <= AMBER_THRESHOLD:
            status = "🟡 CLOSE"
        else:
            status = "🔴 GAP"

        rows.append({
            "Player":        display,
            "DB Name":       db_name,
            "Official Runs": official_runs,
            "DB Runs":       db_runs,
            "Difference":    diff_runs,
            "% Diff":        round(pct_diff * 100, 1),
            "Official M":    official_matches,
            "DB Matches":    db_matches,
            "Status":        status,
        })
    return pd.DataFrame(rows)


def validate_bowling(con) -> pd.DataFrame:
    rows = []
    for db_name, display, official_wkts, official_matches in BOWLING_REFERENCE:
        row = con.execute(f"""
            SELECT
                sum(is_wicket)               AS db_wickets,
                count(DISTINCT match_id)     AS db_matches
            FROM deliveries
            WHERE LOWER(bowler) LIKE LOWER('%{db_name}%')
        """).fetchone()
        db_wkts    = int(row[0] or 0)
        db_matches = int(row[1] or 0)
        diff       = db_wkts - official_wkts
        pct_diff   = abs(diff) / official_wkts if official_wkts else 0

        if pct_diff <= GREEN_THRESHOLD:
            status = "🟢 MATCH"
        elif pct_diff <= AMBER_THRESHOLD:
            status = "🟡 CLOSE"
        else:
            status = "🔴 GAP"

        rows.append({
            "Player":           display,
            "DB Name":          db_name,
            "Official Wickets": official_wkts,
            "DB Wickets":       db_wkts,
            "Difference":       diff,
            "% Diff":           round(pct_diff * 100, 1),
            "Official M":       official_matches,
            "DB Matches":       db_matches,
            "Status":           status,
        })
    return pd.DataFrame(rows)


def get_db_health(con) -> dict:
    """Overall database health metrics."""
    total   = con.execute("SELECT count(*) FROM deliveries").fetchone()[0]
    seasons = con.execute(
        "SELECT count(DISTINCT season) FROM deliveries WHERE season > 0"
    ).fetchone()[0]
    matches = con.execute(
        "SELECT count(DISTINCT match_id) FROM deliveries"
    ).fetchone()[0]
    players = con.execute(
        "SELECT count(DISTINCT striker) FROM deliveries"
    ).fetchone()[0]
    season_rows = con.execute(
        "SELECT season, count(DISTINCT match_id) AS matches, count(*) AS deliveries "
        "FROM deliveries WHERE season > 0 GROUP BY season ORDER BY season"
    ).df()
    zero_season = con.execute(
        "SELECT count(*) FROM deliveries WHERE season = 0 OR season IS NULL"
    ).fetchone()[0]
    return {
        "total_deliveries": total,
        "seasons": seasons,
        "matches": matches,
        "players": players,
        "season_breakdown": season_rows,
        "zero_season_rows": zero_season,
    }


def run_validation() -> dict:
    """Run full validation and return all results."""
    con = duckdb.connect(DB_PATH, read_only=True)
    bat_df  = validate_batting(con)
    bowl_df = validate_bowling(con)
    health  = get_db_health(con)
    con.close()

    # Summary counts
    bat_green  = (bat_df["Status"] == "🟢 MATCH").sum()
    bat_amber  = (bat_df["Status"] == "🟡 CLOSE").sum()
    bat_red    = (bat_df["Status"] == "🔴 GAP").sum()
    bowl_green = (bowl_df["Status"] == "🟢 MATCH").sum()
    bowl_amber = (bowl_df["Status"] == "🟡 CLOSE").sum()
    bowl_red   = (bowl_df["Status"] == "🔴 GAP").sum()

    overall_score = round(
        (bat_green + bowl_green) /
        (len(bat_df) + len(bowl_df)) * 100, 1
    )

    return {
        "batting":       bat_df,
        "bowling":       bowl_df,
        "health":        health,
        "bat_green":     bat_green,
        "bat_amber":     bat_amber,
        "bat_red":       bat_red,
        "bowl_green":    bowl_green,
        "bowl_amber":    bowl_amber,
        "bowl_red":      bowl_red,
        "overall_score": overall_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DISCREPANCY EXPLANATIONS
# ─────────────────────────────────────────────────────────────────────────────
DISCREPANCY_REASONS = """
**Why your DB numbers may differ from official records:**

1. **Name format** — DB uses short codes (`V Kohli`) while some deliveries
   may be recorded under alternate names (`Virat Kohli`, `V Kohli (2)`).
   The LIKE '%name%' query catches most variants.

2. **Extras counted differently** — Official records count all runs
   including all extras. Your DB separates `runs_batter` from wides/no-balls.
   Total team runs = `runs_batter + extras_wides + extras_noballs`.

3. **Season parsing gaps** — Old YAML files (2008–2011) sometimes fail
   the season extraction regex, leaving `season = 0`. Those deliveries
   are still counted but may be duplicated or misattributed.

4. **Retired hurt / Obstructing the field** — Cricsheet records these
   as `is_wicket = 0` in some formats. Official records count them
   as dismissals.

5. **Data completeness** — Cricsheet covers most IPL seasons but some
   early seasons (2008–2010) have incomplete match coverage.
   A 🟡 CLOSE (within 20%) is expected for these players.

6. **Super Overs** — Some Cricsheet files include super over deliveries.
   Official career stats typically exclude super overs.
"""