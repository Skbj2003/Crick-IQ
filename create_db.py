"""
setup_db.py
───────────
Rebuilds ipl_tactics.db from your /ipl YAML folder.

Fixes vs original:
  1. Season: old YAMLs (2008-2012) have NO 'season' key — extracts year from 'dates' instead.
             Also handles: "2023", "2023/24", ["2023/24"], 2023 (int).
  2. Runs:   old YAMLs use runs.batsman, new ones use runs.batter — checks both.
  3. Wicket: new YAMLs use 'wickets' (list), old use 'wicket' (dict) — handles both.
  4. Striker key: old='batsman', new='striker' — checks both.
"""

import duckdb
import yaml
import os
import re
import pandas as pd

DB_PATH     = "ipl_tactics.db"
DATA_FOLDER = "ipl"


def parse_season(info: dict) -> int:
    """
    Extract a 4-digit year from whatever format the YAML provides.

    Old format (IPL 2008-2012 files): NO 'season' key, only 'dates'
        dates: ['2008-04-18']  →  2008

    Newer formats:
        season: 2023           →  2023
        season: '2023/24'      →  2023
        season: ['2023/24']    →  2023
    """
    raw = info.get('season')

    if raw is None:
        # No season field at all — fall back to match date year
        dates = info.get('dates', [])
        raw = str(dates[0]) if dates else ''
    elif isinstance(raw, list):
        raw = str(raw[0]) if raw else ''
    else:
        raw = str(raw)

    m = re.search(r'(20\d{2}|19\d{2})', raw)
    return int(m.group(1)) if m else 0


def parse_runs_batter(d: dict) -> int:
    """Old YAMLs: runs.batsman  |  New YAMLs: runs.batter"""
    runs = d.get('runs', {})
    return int(runs.get('batter', runs.get('batsman', 0)))


def parse_wicket(d: dict):
    """
    Old YAMLs:  wicket: {kind: caught, ...}       (single dict)
    New YAMLs:  wickets: [{kind: caught, ...}]     (list of dicts)
    Returns (is_wicket: int, wicket_kind: str|None)
    """
    w = d.get('wicket')
    if w and isinstance(w, dict):
        return 1, w.get('kind')

    ws = d.get('wickets')
    if ws and isinstance(ws, list) and len(ws) > 0:
        return 1, ws[0].get('kind')

    return 0, None


def setup_database():
    print("🚀 Dropping and recreating deliveries table...")

    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS deliveries")
    con.execute("""
        CREATE TABLE deliveries (
            match_id        VARCHAR,
            season          INTEGER,
            venue           VARCHAR,
            batting_team    VARCHAR,
            bowling_team    VARCHAR,
            striker         VARCHAR,
            non_striker     VARCHAR,
            bowler          VARCHAR,
            over            INTEGER,
            ball            INTEGER,
            runs_batter     INTEGER,
            extras_wides    INTEGER,
            extras_noballs  INTEGER,
            is_wicket       INTEGER,
            wicket_kind     VARCHAR
        )
    """)

    yaml_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.yaml')]
    print(f"📂 Found {len(yaml_files)} YAML files in /{DATA_FOLDER}")

    records   = []
    ok_count  = 0
    err_count = 0

    for filename in yaml_files:
        filepath = os.path.join(DATA_FOLDER, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.load(f, Loader=yaml.SafeLoader)

            info         = data.get('info', {})
            season       = parse_season(info)
            venue        = info.get('venue', 'Unknown')
            teams        = info.get('teams', [])
            match_id     = filename.replace('.yaml', '')

            for inning_data in data.get('innings', []):
                inning_key   = list(inning_data.keys())[0]
                inning       = inning_data[inning_key]
                batting_team = inning.get('team', 'Unknown')
                bowling_team = next((t for t in teams if t != batting_team), 'Unknown')

                for delivery_entry in inning.get('deliveries', []):
                    ball_coord   = list(delivery_entry.keys())[0]
                    d            = delivery_entry[ball_coord]
                    is_w, w_kind = parse_wicket(d)

                    records.append({
                        'match_id':       match_id,
                        'season':         season,
                        'venue':          venue,
                        'batting_team':   batting_team,
                        'bowling_team':   bowling_team,
                        'striker':        d.get('striker') or d.get('batsman', ''),
                        'non_striker':    d.get('non_striker', ''),
                        'bowler':         d.get('bowler', ''),
                        'over':           int(float(ball_coord)),
                        'ball':           int(round((float(ball_coord) % 1) * 10)),
                        'runs_batter':    parse_runs_batter(d),
                        'extras_wides':   int(d.get('extras', {}).get('wides', 0)),
                        'extras_noballs': int(d.get('extras', {}).get('noballs', 0)),
                        'is_wicket':      is_w,
                        'wicket_kind':    w_kind,
                    })
            ok_count += 1

        except Exception as e:
            err_count += 1
            print(f"  ⚠️  Skipped {filename}: {e}")

    print(f"✅ Parsed {ok_count} files ({err_count} errors).")

    df = pd.DataFrame(records)
    print(f"📊 Total deliveries: {len(df):,}")
    print(f"📅 Seasons found:    {sorted(df['season'].unique())}")

    con.execute("INSERT INTO deliveries SELECT * FROM df")

    print("⚡ Creating indexes...")
    con.execute("CREATE INDEX idx_striker ON deliveries (striker)")
    con.execute("CREATE INDEX idx_bowler  ON deliveries (bowler)")
    con.execute("CREATE INDEX idx_season  ON deliveries (season)")
    con.execute("CREATE INDEX idx_venue   ON deliveries (venue)")

    con.close()
    print(f"\n🏆 Done! {len(df):,} deliveries across {df['season'].nunique()} seasons in {DB_PATH}.")


if __name__ == "__main__":
    setup_database()