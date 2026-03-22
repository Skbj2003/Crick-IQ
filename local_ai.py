

import re
import duckdb
import requests

DB_PATH = "ipl_tactics.db"


# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA  (local LLM — free, works offline after install)
# ─────────────────────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODELS = ["llama3", "llama3.1", "llama3.2", "llama3.3", "gemma2", "mistral", "phi3"]


def _ollama_available() -> str | None:
    """Return model name if Ollama is running, else None."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=1)
        if r.status_code == 200:
            models = [m["name"].split(":")[0] for m in r.json().get("models", [])]
            for preferred in OLLAMA_MODELS:
                if preferred in models:
                    return preferred
            if models:
                return models[0]
    except Exception:
        pass
    return None


def _ask_ollama(prompt: str, model: str) -> str:
    """Send prompt to local Ollama and return response."""
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 400},
        }, timeout=30)
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception as e:
        return f"Ollama error: {e}"
    return "No response from Ollama."


# ─────────────────────────────────────────────────────────────────────────────
# RULE-BASED NLP ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    return duckdb.connect(DB_PATH, read_only=True)

def _sc(n=5):
    try:
        con = _db()
        s = con.execute(
            "SELECT DISTINCT season FROM deliveries WHERE season>0 ORDER BY season DESC"
        ).df()["season"].tolist()
        con.close()
        return f"AND season IN ({','.join(str(x) for x in s[:n])})" if s else ""
    except Exception:
        return ""


# Intent patterns
_INTENTS = [
    ("head_to_head",   r"(\bvs\b|\bversus\b|against|facing|faced)",),
    ("top_runs",       r"(top|most|highest|best).{0,20}(run|score|bat)",),
    ("top_wickets",    r"(top|most|best).{0,20}(wicket|bowl|take)",),
    ("best_economy",   r"(best|lowest).{0,20}econom",),
    ("best_sr",        r"(best|highest|top).{0,20}strike.rate",),
    ("player_stats",   r"(stat|career|record|overall|how (has|did|does))",),
    ("team_h2h",       r"(mi|csk|rcb|kkr|dc|srh|rr|pbks|gt|lsg).{0,15}(vs|versus|against|beat|record)",),
    ("venue_stats",    r"(wankhede|eden|chepauk|chinnaswamy|feroz|kotla|narendra|brabourne|ekana|sawai|rajiv).{0,30}(stat|best|top|perform)",),
    ("phase_stats",    r"(powerplay|middle over|death over|pp|slog)",),
    ("form",           r"(form|recent|last \d+ match|in form|current)",),
    ("prediction",     r"(predict|forecast|expect|likely|will score|how many)",),
    ("compare",        r"(compare|better|worse|who is|which is)",),
]

def _detect_intent(text: str) -> str:
    t = text.lower()
    for intent, pattern in _INTENTS:
        if re.search(pattern, t):
            return intent
    return "general"


def _extract_players(text: str) -> list[str]:
    """Extract player name fragments from text."""
    # Common name patterns: initials + surname, or just surname
    patterns = [
        r'\b([A-Z]{1,2}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b',   # V Kohli, JJ Bumrah
        r'\b(Kohli|Sharma|Dhoni|Bumrah|Narine|Malinga|Warner|'
        r'Gayle|De Villiers|Pandya|Jadeja|Chahal|Rahul|Watson|'
        r'Raina|Gambhir|McCullum|Pollard|Bravo|Yadav|Pant|'
        r'Iyer|Gill|Jaiswal|Maxwell|Stoinis|Buttler|Samson)\b',
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, text, re.IGNORECASE))
    return list(dict.fromkeys(found))[:2]   # max 2 players


def _extract_season(text: str) -> int | None:
    m = re.search(r'\b(20\d{2})\b', text)
    return int(m.group(1)) if m else None


def _extract_number(text: str, default: int = 5) -> int:
    m = re.search(r'\b(\d+)\b', text)
    v = int(m.group(1)) if m else default
    return max(1, min(v, 20))


# ── Query functions ──

def _fmt_table(df, max_rows=8) -> str:
    if df.empty:
        return "No data found."
    rows = df.head(max_rows).to_dict(orient="records")
    lines = []
    for i, r in enumerate(rows, 1):
        parts = [f"{k}: {v}" for k, v in r.items()]
        lines.append(f"{i}. " + "  |  ".join(parts))
    return "\n".join(lines)


def _q_top_runs(season=None, n=5) -> str:
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        df = con.execute(f"""
            SELECT striker AS player,
                   sum(runs_batter) AS runs,
                   count(DISTINCT match_id) AS matches,
                   round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr
            FROM deliveries WHERE 1=1 {sf}
            GROUP BY striker ORDER BY runs DESC LIMIT {n}
        """).df()
        con.close()
        era = f" in {season}" if season else " (all time)"
        return f"**Top {n} Run Scorers{era}:**\n" + _fmt_table(df)
    except Exception as e:
        return f"Error: {e}"


def _q_top_wickets(season=None, n=5) -> str:
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        df = con.execute(f"""
            SELECT bowler AS player,
                   sum(is_wicket) AS wickets,
                   round(sum(runs_batter)*6.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                   count(DISTINCT match_id) AS matches
            FROM deliveries WHERE 1=1 {sf}
            GROUP BY bowler ORDER BY wickets DESC LIMIT {n}
        """).df()
        con.close()
        era = f" in {season}" if season else " (all time)"
        return f"**Top {n} Wicket Takers{era}:**\n" + _fmt_table(df)
    except Exception as e:
        return f"Error: {e}"


def _q_head_to_head(players: list, season=None) -> str:
    if len(players) < 2:
        return "Please name both a batsman and a bowler. Example: 'Kohli vs Bumrah'"
    bat, bowl = players[0], players[1]
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        row = con.execute(f"""
            SELECT count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
                   sum(runs_batter) AS runs, sum(is_wicket) AS dismissals,
                   round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                   count(DISTINCT match_id) AS matches
            FROM deliveries
            WHERE LOWER(striker) LIKE LOWER('%{bat}%')
              AND LOWER(bowler)  LIKE LOWER('%{bowl}%') {sf}
        """).fetchone()
        con.close()
        if not row[0]:
            return f"No matchup data found between **{bat}** and **{bowl}**."
        balls, runs, dis, sr, matches = row
        verdict = ("🔴 Bowler dominates" if dis >= 4 else
                   "🟠 Bowler has edge" if (dis >= 2 and sr < 110) else
                   "🟢 Batsman dominates" if sr > 160 else
                   "🔵 Even contest")
        return (f"**{bat} vs {bowl}**\n"
                f"Balls: {balls}  |  Runs: {runs}  |  Dismissals: {dis}\n"
                f"Strike Rate: {sr}  |  Matches: {matches}\n\n"
                f"**Verdict:** {verdict}")
    except Exception as e:
        return f"Error: {e}"


def _q_player_stats(player: str, season=None) -> str:
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        bat = con.execute(f"""
            SELECT sum(runs_batter) AS runs,
                   count(DISTINCT match_id) AS matches,
                   round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                   sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END) AS fours,
                   sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END) AS sixes
            FROM deliveries WHERE LOWER(striker) LIKE LOWER('%{player}%') {sf}
        """).fetchone()
        bowl = con.execute(f"""
            SELECT sum(is_wicket) AS wickets,
                   round(sum(runs_batter)*6.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                   count(DISTINCT match_id) AS matches
            FROM deliveries WHERE LOWER(bowler) LIKE LOWER('%{player}%') {sf}
        """).fetchone()
        con.close()
        era = f" in {season}" if season else ""
        lines = [f"**{player} Career Stats{era}**"]
        if bat[0]:
            lines.append(f"🏏 Batting: {bat[0]} runs | SR {bat[2]} | {bat[3]}×4 {bat[4]}×6 | {bat[1]} matches")
        if bowl[0]:
            lines.append(f"🎯 Bowling: {bowl[0]} wickets | Economy {bowl[1]} | {bowl[2]} matches")
        if not bat[0] and not bowl[0]:
            return f"No data found for **{player}**. Try the short name format (e.g. 'V Kohli', 'JJ Bumrah')."
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _q_best_economy(season=None, n=5) -> str:
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        df = con.execute(f"""
            SELECT bowler AS player,
                   round(sum(runs_batter)*6.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
                   sum(is_wicket) AS wickets,
                   count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
            FROM deliveries WHERE 1=1 {sf}
            GROUP BY bowler HAVING count(CASE WHEN extras_wides=0 THEN 1 END)>=120
            ORDER BY economy ASC LIMIT {n}
        """).df()
        con.close()
        era = f" in {season}" if season else ""
        return f"**Best Economy Rates{era} (min 120 balls):**\n" + _fmt_table(df)
    except Exception as e:
        return f"Error: {e}"


def _q_best_sr(season=None, n=5) -> str:
    sf = f"AND season={season}" if season else ""
    try:
        con = _db()
        df = con.execute(f"""
            SELECT striker AS player,
                   round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
                   sum(runs_batter) AS runs,
                   count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
            FROM deliveries WHERE 1=1 {sf}
            GROUP BY striker HAVING count(CASE WHEN extras_wides=0 THEN 1 END)>=100
            ORDER BY sr DESC LIMIT {n}
        """).df()
        con.close()
        era = f" in {season}" if season else ""
        return f"**Best Strike Rates{era} (min 100 balls):**\n" + _fmt_table(df)
    except Exception as e:
        return f"Error: {e}"


def _q_team_h2h(text: str) -> str:
    team_map = {
        "mi": "Mumbai Indians", "mumbai": "Mumbai Indians",
        "csk": "Chennai Super Kings", "chennai": "Chennai Super Kings",
        "rcb": "Royal Challengers", "bangalore": "Royal Challengers",
        "kkr": "Kolkata Knight Riders", "kolkata": "Kolkata Knight Riders",
        "dc": "Delhi Capitals", "delhi": "Delhi Capitals",
        "srh": "Sunrisers Hyderabad", "hyderabad": "Sunrisers Hyderabad",
        "rr": "Rajasthan Royals", "rajasthan": "Rajasthan Royals",
        "pbks": "Punjab Kings", "punjab": "Punjab Kings",
        "gt": "Gujarat Titans", "gujarat": "Gujarat Titans",
        "lsg": "Lucknow Super Giants", "lucknow": "Lucknow Super Giants",
    }
    t = text.lower()
    found = [v for k, v in team_map.items() if k in t]
    found = list(dict.fromkeys(found))
    if len(found) < 2:
        return "Please mention two teams. Example: 'MI vs CSK record'"
    t1, t2 = found[0], found[1]
    try:
        con = _db()
        df = con.execute(f"""
            SELECT batting_team,
                   count(DISTINCT match_id) AS innings,
                   round(avg(match_runs),1) AS avg_score,
                   max(match_runs) AS highest
            FROM (
                SELECT match_id, batting_team,
                       sum(runs_batter+extras_wides+extras_noballs) AS match_runs
                FROM deliveries
                WHERE (LOWER(batting_team) LIKE LOWER('%{t1}%')
                       OR LOWER(batting_team) LIKE LOWER('%{t2}%'))
                GROUP BY match_id, batting_team
            )
            GROUP BY batting_team ORDER BY avg_score DESC
        """).df()
        con.close()
        return f"**{t1} vs {t2} — Head to Head:**\n" + _fmt_table(df)
    except Exception as e:
        return f"Error: {e}"


def _q_general(text: str) -> str:
    return (
        "I can answer questions about:\n"
        "• **Player matchups** — 'Kohli vs Bumrah stats'\n"
        "• **Top performers** — 'Top 5 run scorers in 2023'\n"
        "• **Player career** — 'Dhoni batting stats'\n"
        "• **Economy/SR** — 'Best economy bowlers ever'\n"
        "• **Team records** — 'MI vs CSK all time'\n\n"
        "Try asking one of those!"
    )


# ── Main rule-based router ──

def rule_based_answer(question: str) -> str:
    """
    Route a natural language question to the right DB query.
    Returns a formatted markdown string.
    """
    q       = question.strip()
    intent  = _detect_intent(q)
    players = _extract_players(q)
    season  = _extract_season(q)
    n       = _extract_number(q, default=5)

    if intent == "head_to_head" and len(players) >= 2:
        return _q_head_to_head(players, season)
    elif intent == "top_runs":
        return _q_top_runs(season, n)
    elif intent == "top_wickets":
        return _q_top_wickets(season, n)
    elif intent == "best_economy":
        return _q_best_economy(season, n)
    elif intent == "best_sr":
        return _q_best_sr(season, n)
    elif intent == "player_stats" and players:
        return _q_player_stats(players[0], season)
    elif intent == "team_h2h":
        return _q_team_h2h(q)
    elif players and len(players) == 2:
        return _q_head_to_head(players, season)
    elif players and len(players) == 1:
        return _q_player_stats(players[0], season)
    else:
        return _q_general(q)


# ─────────────────────────────────────────────────────────────────────────────
# UNIFIED CHAT FUNCTION  (used by app.py floating chat)
# ─────────────────────────────────────────────────────────────────────────────
def chat(question: str, gemini_key: str = "", history: list = None) -> tuple[str, str]:
    """
    Answer a cricket question using best available method.
    Priority: Ollama (local) → Gemini (cloud) → Rule-based (always)
    Returns (answer, method_used)
    """
    history = history or []

    # 1. Try Ollama first (local, free, private)
    ollama_model = _ollama_available()
    if ollama_model:
        # Give Ollama full context from DB query first
        db_context = rule_based_answer(question)
        prompt = (
            f"You are an expert IPL cricket analyst. Use the data below to answer the question.\n\n"
            f"DATABASE RESULT:\n{db_context}\n\n"
            f"USER QUESTION: {question}\n\n"
            f"Give a sharp, insightful 2-4 sentence analysis. "
            f"Reference the specific numbers. Sound like a professional cricket analyst."
        )
        reply = _ask_ollama(prompt, ollama_model)
        if reply and not reply.startswith("Ollama error"):
            return reply, f"ollama:{ollama_model}"

    # 2. Try Gemini if key provided
    if gemini_key and gemini_key != "YOUR_GEMINI_API_KEY_HERE":
        try:
            from agent import run_agent
            reply, _ = run_agent(question, history, gemini_key, provider="gemini")
            return reply, "gemini"
        except Exception:
            pass   # fall through

    # 3. Rule-based (always works — no dependencies)
    reply = rule_based_answer(question)
    return reply, "rule_based"


def get_ai_status() -> dict:
    """Returns what AI is available right now."""
    ollama = _ollama_available()
    return {
        "ollama":     ollama,
        "rule_based": True,   # always available
    }
