"""
agent.py
────────
IPL Tactical AI Agent — supports BOTH:
  • Google Gemini  (FREE tier — gemini-2.5-flash-preview-04-17)
  • Anthropic Claude (paid — claude-sonnet)

Same 6 tools, same agentic loop, same answers.
Switch by passing provider="gemini" or provider="claude" to run_agent().

Install:
    pip install google-generativeai anthropic
"""

import json
import duckdb

DB_PATH = "ipl_tactics.db"

# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITIONS — Claude format (Anthropic)
# ─────────────────────────────────────────────────────────────────────────────
TOOLS_CLAUDE = [
    {
        "name": "player_matchup",
        "description": (
            "Get head-to-head statistics between a batsman and a bowler. "
            "Returns balls faced, runs scored, dismissals, strike rate, 4s, 6s and matches played. "
            "Use when the user asks how a specific batsman performs against a specific bowler."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "batsman": {"type": "string", "description": "Batsman name in DB format e.g. 'V Kohli', 'MS Dhoni'"},
                "bowler":  {"type": "string", "description": "Bowler name in DB format e.g. 'SP Narine', 'JJ Bumrah'"},
                "venue":   {"type": "string", "description": "Optional venue filter. Empty = all venues.", "default": ""},
                "season":  {"type": "integer", "description": "Season year e.g. 2023. 0 = all seasons.", "default": 0},
            },
            "required": ["batsman", "bowler"],
        },
    },
    {
        "name": "team_matchup",
        "description": (
            "Get head-to-head record between two IPL franchises. "
            "Returns matches played, runs, and season-by-season breakdown. "
            "Use when the user asks about team vs team records."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team1":  {"type": "string", "description": "First team e.g. 'Mumbai Indians'"},
                "team2":  {"type": "string", "description": "Second team e.g. 'Chennai Super Kings'"},
                "season": {"type": "integer", "description": "Season year or 0 for all.", "default": 0},
            },
            "required": ["team1", "team2"],
        },
    },
    {
        "name": "top_performers",
        "description": (
            "Get top run scorers, wicket takers, best strike rates or best economy rates. "
            "Use when user asks who is the best batsman/bowler or for leaderboard queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["runs", "wickets", "strike_rate", "economy"],
                    "description": "What to rank players by.",
                },
                "season": {"type": "integer", "description": "Season year or 0 for all.", "default": 0},
                "team":   {"type": "string",  "description": "Filter by team. Empty = all.", "default": ""},
                "limit":  {"type": "integer", "description": "Number of players to return.", "default": 5},
            },
            "required": ["category"],
        },
    },
    {
        "name": "player_stats",
        "description": (
            "Get career or season stats for a single player — runs, balls, SR, wickets, economy. "
            "Use when the user asks about one specific player's overall record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {"type": "string", "description": "Player name."},
                "role":   {"type": "string", "enum": ["batsman", "bowler", "both"], "default": "both"},
                "season": {"type": "integer", "description": "Season year or 0 for all.", "default": 0},
            },
            "required": ["player"],
        },
    },
    {
        "name": "venue_stats",
        "description": (
            "Get stats for a specific stadium — top batsmen, top bowlers, match counts. "
            "Use when user asks about a ground or stadium."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "venue":  {"type": "string", "description": "Venue/stadium name."},
                "season": {"type": "integer", "description": "Season year or 0 for all.", "default": 0},
            },
            "required": ["venue"],
        },
    },
    {
        "name": "run_custom_query",
        "description": (
            "Run a custom SELECT SQL query on the deliveries table for anything not covered above. "
            "Columns: match_id, season, venue, batting_team, bowling_team, striker, non_striker, "
            "bowler, over, ball, runs_batter, extras_wides, extras_noballs, is_wicket, wicket_kind. "
            "Only safe SELECT queries allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql":         {"type": "string", "description": "A safe SELECT SQL query."},
                "description": {"type": "string", "description": "What this query does."},
            },
            "required": ["sql", "description"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL DEFINITIONS — Gemini format
# ─────────────────────────────────────────────────────────────────────────────
def _build_gemini_tools():
    """Convert TOOLS_CLAUDE to google-generativeai Tool format."""
    import google.generativeai as genai

    declarations = []
    for t in TOOLS_CLAUDE:
        # Strip "default" keys — Gemini schema doesn't accept them
        props = {}
        for k, v in t["input_schema"].get("properties", {}).items():
            props[k] = {kk: vv for kk, vv in v.items() if kk != "default"}

        clean_schema = {"type": "object", "properties": props}
        if "required" in t["input_schema"]:
            clean_schema["required"] = t["input_schema"]["required"]

        declarations.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": clean_schema,
        })

    return declarations


# ─────────────────────────────────────────────────────────────────────────────
# TOOL EXECUTOR  (shared — runs SQL against DuckDB)
# ─────────────────────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_input: dict) -> dict:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        if tool_name == "player_matchup":
            bat    = tool_input["batsman"]
            bowl   = tool_input["bowler"]
            venue  = tool_input.get("venue", "")
            season = tool_input.get("season", 0)
            vf = f"AND venue = '{venue}'"      if venue  else ""
            sf = f"AND season = {int(season)}" if season else ""

            row = con.execute(f"""
                SELECT
                    count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                    sum(runs_batter)  AS runs,
                    sum(is_wicket)    AS dismissals,
                    round(sum(runs_batter)*100.0/
                          NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                    count(DISTINCT match_id) AS matches,
                    sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END) AS fours,
                    sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END) AS sixes
                FROM deliveries
                WHERE LOWER(striker) LIKE LOWER('%{bat}%')
                  AND LOWER(bowler)  LIKE LOWER('%{bowl}%')
                  {vf} {sf}
            """).fetchone()

            seasons_df = con.execute(f"""
                SELECT season, sum(runs_batter) AS runs,
                       count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                       sum(is_wicket) AS dismissals
                FROM deliveries
                WHERE LOWER(striker) LIKE LOWER('%{bat}%')
                  AND LOWER(bowler)  LIKE LOWER('%{bowl}%')
                  {vf} {sf}
                GROUP BY season ORDER BY season
            """).df()

            return {
                "batsman": bat, "bowler": bowl,
                "balls": row[0], "runs": row[1], "dismissals": row[2],
                "strike_rate": row[3], "matches": row[4],
                "fours": row[5], "sixes": row[6],
                "season_breakdown": seasons_df.to_dict(orient="records"),
            }

        elif tool_name == "team_matchup":
            t1     = tool_input["team1"]
            t2     = tool_input["team2"]
            season = tool_input.get("season", 0)
            sf     = f"AND season = {int(season)}" if season else ""

            matches_df = con.execute(f"""
                SELECT season, batting_team, bowling_team, match_id,
                       sum(runs_batter + extras_wides + extras_noballs) AS total_runs
                FROM deliveries
                WHERE ((LOWER(batting_team) LIKE LOWER('%{t1}%')
                        AND LOWER(bowling_team) LIKE LOWER('%{t2}%'))
                    OR (LOWER(batting_team) LIKE LOWER('%{t2}%')
                        AND LOWER(bowling_team) LIKE LOWER('%{t1}%')))
                  {sf}
                GROUP BY season, batting_team, bowling_team, match_id
                ORDER BY season
            """).df()

            summary = con.execute(f"""
                SELECT count(DISTINCT match_id) AS total_matches
                FROM deliveries
                WHERE ((LOWER(batting_team) LIKE LOWER('%{t1}%')
                        AND LOWER(bowling_team) LIKE LOWER('%{t2}%'))
                    OR (LOWER(batting_team) LIKE LOWER('%{t2}%')
                        AND LOWER(bowling_team) LIKE LOWER('%{t1}%')))
                  {sf}
            """).fetchone()

            return {
                "team1": t1, "team2": t2,
                "total_matches": summary[0],
                "match_records": matches_df.to_dict(orient="records"),
            }

        elif tool_name == "top_performers":
            cat    = tool_input["category"]
            season = tool_input.get("season", 0)
            team   = tool_input.get("team", "")
            limit  = tool_input.get("limit", 5)
            sf = f"AND season = {int(season)}" if season else ""
            tf = (f"AND (LOWER(batting_team) LIKE LOWER('%{team}%') "
                  f"OR LOWER(bowling_team) LIKE LOWER('%{team}%'))") if team else ""

            if cat == "runs":
                df = con.execute(f"""
                    SELECT striker AS player, sum(runs_batter) AS runs,
                           count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                           round(sum(runs_batter)*100.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr
                    FROM deliveries WHERE 1=1 {sf} {tf}
                    GROUP BY striker ORDER BY runs DESC LIMIT {limit}
                """).df()
            elif cat == "wickets":
                df = con.execute(f"""
                    SELECT bowler AS player, sum(is_wicket) AS wickets,
                           round(sum(runs_batter)*6.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy
                    FROM deliveries WHERE 1=1 {sf} {tf}
                    GROUP BY bowler ORDER BY wickets DESC LIMIT {limit}
                """).df()
            elif cat == "strike_rate":
                df = con.execute(f"""
                    SELECT striker AS player,
                           round(sum(runs_batter)*100.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS strike_rate,
                           sum(runs_batter) AS runs,
                           count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
                    FROM deliveries WHERE 1=1 {sf} {tf}
                    GROUP BY striker
                    HAVING count(CASE WHEN extras_wides=0 THEN 1 END) >= 100
                    ORDER BY strike_rate DESC LIMIT {limit}
                """).df()
            elif cat == "economy":
                df = con.execute(f"""
                    SELECT bowler AS player,
                           round(sum(runs_batter)*6.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                           sum(is_wicket) AS wickets,
                           count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
                    FROM deliveries WHERE 1=1 {sf} {tf}
                    GROUP BY bowler
                    HAVING count(CASE WHEN extras_wides=0 THEN 1 END) >= 120
                    ORDER BY economy ASC LIMIT {limit}
                """).df()
            return {"category": cat, "season": season, "results": df.to_dict(orient="records")}

        elif tool_name == "player_stats":
            player = tool_input["player"]
            role   = tool_input.get("role", "both")
            season = tool_input.get("season", 0)
            sf     = f"AND season = {int(season)}" if season else ""
            result = {}
            if role in ("batsman", "both"):
                r = con.execute(f"""
                    SELECT sum(runs_batter) AS runs,
                           count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                           round(sum(runs_batter)*100.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                           count(DISTINCT match_id) AS matches,
                           sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END) AS fours,
                           sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END) AS sixes
                    FROM deliveries
                    WHERE LOWER(striker) LIKE LOWER('%{player}%') {sf}
                """).fetchone()
                result["batting"] = {
                    "runs": r[0], "balls": r[1], "strike_rate": r[2],
                    "matches": r[3], "fours": r[4], "sixes": r[5],
                }
            if role in ("bowler", "both"):
                r = con.execute(f"""
                    SELECT sum(is_wicket) AS wickets,
                           count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                           round(sum(runs_batter)*6.0/
                                 NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                           count(DISTINCT match_id) AS matches
                    FROM deliveries
                    WHERE LOWER(bowler) LIKE LOWER('%{player}%') {sf}
                """).fetchone()
                result["bowling"] = {
                    "wickets": r[0], "balls": r[1],
                    "economy": r[2], "matches": r[3],
                }
            return {"player": player, **result}

        elif tool_name == "venue_stats":
            venue  = tool_input["venue"]
            season = tool_input.get("season", 0)
            sf     = f"AND season = {int(season)}" if season else ""
            stats  = con.execute(f"""
                SELECT count(DISTINCT match_id) AS matches
                FROM deliveries
                WHERE LOWER(venue) LIKE LOWER('%{venue}%') {sf}
            """).fetchone()
            top_bat = con.execute(f"""
                SELECT striker, sum(runs_batter) AS runs
                FROM deliveries
                WHERE LOWER(venue) LIKE LOWER('%{venue}%') {sf}
                GROUP BY striker ORDER BY runs DESC LIMIT 5
            """).df()
            top_bowl = con.execute(f"""
                SELECT bowler, sum(is_wicket) AS wickets
                FROM deliveries
                WHERE LOWER(venue) LIKE LOWER('%{venue}%') {sf}
                GROUP BY bowler ORDER BY wickets DESC LIMIT 5
            """).df()
            return {
                "venue": venue, "matches": stats[0],
                "top_batsmen": top_bat.to_dict(orient="records"),
                "top_bowlers": top_bowl.to_dict(orient="records"),
            }

        elif tool_name == "run_custom_query":
            sql = tool_input["sql"]
            if not sql.strip().upper().startswith("SELECT"):
                return {"error": "Only SELECT queries are allowed."}
            df = con.execute(sql).df()
            return {"results": df.to_dict(orient="records"), "rows": len(df)}

    except Exception as e:
        return {"error": str(e)}
    finally:
        con.close()

    return {"error": f"Unknown tool: {tool_name}"}


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert IPL cricket analyst with access to a ball-by-ball database
covering all IPL seasons. You help coaches, analysts and fans with tactical insights.

You have tools to query:
- Player head-to-head matchups (batsman vs bowler)
- Team vs team records
- Top performers (runs, wickets, strike rate, economy)
- Individual player career stats
- Venue-specific statistics
- Custom SQL for anything else

Always:
1. Use tools to fetch REAL data — never guess or make up numbers
2. Give tactical insights beyond just the raw numbers
3. Use short DB name format: 'V Kohli', 'MS Dhoni', 'SP Narine', 'JJ Bumrah', 'SL Malinga'
4. If no data found, try alternative name abbreviations
5. Keep answers sharp and insightful — this is for people making real cricket decisions

Team names in DB: 'Mumbai Indians', 'Chennai Super Kings', 'Royal Challengers Bangalore',
'Kolkata Knight Riders', 'Delhi Capitals', 'Rajasthan Royals', 'Punjab Kings', 'Sunrisers Hyderabad'"""


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI AGENT  (FREE tier)
# ─────────────────────────────────────────────────────────────────────────────
def _run_gemini(user_message: str, history: list, api_key: str) -> tuple[str, list]:
    import google.generativeai as genai
    from google.generativeai import protos

    genai.configure(api_key=api_key)

    # Build tool declarations
    tool_declarations = []
    for t in _build_gemini_tools():
        tool_declarations.append(
            protos.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=protos.Schema(
                    type=protos.Type.OBJECT,
                    properties={
                        k: protos.Schema(
                            type=protos.Type.STRING if v.get("type") == "string" else
                                 protos.Type.INTEGER if v.get("type") == "integer" else
                                 protos.Type.STRING,
                            description=v.get("description", ""),
                            enum=v.get("enum", []) if v.get("enum") else [],
                        )
                        for k, v in t["parameters"].get("properties", {}).items()
                    },
                    required=t["parameters"].get("required", []),
                ),
            )
        )
    gemini_tools = protos.Tool(function_declarations=tool_declarations)

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-preview-04-17",
        system_instruction=SYSTEM_PROMPT,
        tools=[gemini_tools],
    )

    # Convert stored history to Gemini format (text turns only)
    gemini_history = []
    for m in history:
        if isinstance(m.get("content"), str) and m["content"]:
            role = "user" if m["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [{"text": m["content"]}]})

    chat = model.start_chat(history=gemini_history)
    response = chat.send_message(user_message)

    # Agentic loop
    while True:
        fn_calls = [
            p.function_call
            for p in response.candidates[0].content.parts
            if hasattr(p, "function_call") and p.function_call.name
        ]

        if not fn_calls:
            # Done — extract final text
            final_text = ""
            for p in response.candidates[0].content.parts:
                if hasattr(p, "text") and p.text:
                    final_text += p.text
            updated = history + [
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": final_text},
            ]
            return final_text, updated

        # Execute function calls and feed results back
        fn_response_parts = []
        for fn_call in fn_calls:
            result = execute_tool(fn_call.name, dict(fn_call.args))
            fn_response_parts.append(
                protos.Part(
                    function_response=protos.FunctionResponse(
                        name=fn_call.name,
                        response={"result": json.dumps(result, default=str)},
                    )
                )
            )

        response = chat.send_message(fn_response_parts)


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE AGENT  (paid)
# ─────────────────────────────────────────────────────────────────────────────
def _run_claude(user_message: str, history: list, api_key: str) -> tuple[str, list]:
    import anthropic

    client   = anthropic.Anthropic(api_key=api_key)
    messages = history + [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS_CLAUDE,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            return final_text, messages

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        break

    return "I couldn't generate a response. Please try again.", messages


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def run_agent(
    user_message: str,
    history: list,
    api_key: str,
    provider: str = "gemini",
) -> tuple[str, list]:
    """
    Run the IPL AI agent.

    Args:
        user_message : What the user asked
        history      : List of {"role": "user"/"assistant", "content": str}
        api_key      : API key for chosen provider
        provider     : "gemini" (free) or "claude" (paid)

    Returns:
        (reply_text, updated_history)
    """
    if provider == "gemini":
        return _run_gemini(user_message, history, api_key)
    elif provider == "claude":
        return _run_claude(user_message, history, api_key)
    else:
        raise ValueError(f"Unknown provider '{provider}'. Use 'gemini' or 'claude'.")