import streamlit as st
import duckdb
import pandas as pd
import json
import os
import base64
from pathlib import Path
from difflib import get_close_matches
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="CricIQ — IPL Analytics", layout="wide",
                   page_icon="🏏", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH        = "ipl_tactics.db"

# ── API key: try Streamlit secrets → env var → hardcoded ──
import os as _os
try:
    import streamlit as _st_secrets
    GEMINI_API_KEY = _st_secrets.secrets.get("GEMINI_API_KEY", "")
except Exception:
    GEMINI_API_KEY = _os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# ── Squad data: live from Cricinfo with hardcoded fallback ──
from squad_fetcher import get_squad, get_teams
from local_ai import chat as _ai_chat, get_ai_status

PLOT_BG = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
               font=dict(family="Inter", color="#90b4ce", size=12),
               margin=dict(l=20, r=20, t=44, b=20))
AX = dict(gridcolor="#0f2035", linecolor="#1a3050", tickcolor="#1a3050", zeroline=False)
CYAN="#38bdf8"; INDIGO="#818cf8"; GREEN="#4ade80"; RED="#f87171"; AMBER="#fbbf24"

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@600;700&family=Inter:wght@300;400;500;600&display=swap');
html,body,[class*="css"],.main{background:#07090f;color:#c8daea;font-family:'Inter',sans-serif;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0a1020,#06080f)!important;border-right:1px solid #0e1a2a;}
[data-testid="stSidebar"] *{color:#6b8fa8!important;}
[data-testid="stSidebar"] .stSelectbox>div>div,
[data-testid="stSidebar"] .stTextInput>div>div>input{background:#080f1c!important;border:1px solid #1a2e45!important;border-radius:8px!important;color:#c8daea!important;font-size:13px!important;}
.stTabs [data-baseweb="tab-list"]{
    background:#060c18;border-bottom:1px solid #0e1a2a;
    padding:0 4px;gap:0;border-radius:0;border:none;
    border-top:1px solid #0e1a2a;}
.stTabs [data-baseweb="tab"]{
    font-family:'Rajdhani',sans-serif;font-size:13px;font-weight:700;
    letter-spacing:1.5px;color:#2d4a62!important;
    border-radius:0;text-transform:uppercase;
    padding:12px 22px;border-bottom:2px solid transparent;
    transition:color .15s,border-color .15s;background:transparent!important;}
.stTabs [data-baseweb="tab"]:hover{color:#56b4e9!important;}
.stTabs [aria-selected="true"]{
    color:#38bdf8!important;border-bottom:2px solid #38bdf8!important;
    background:transparent!important;}
[data-testid="stMetric"]{background:linear-gradient(135deg,#0a1520,#07101a);
    border:1px solid #0e1a2a;border-radius:12px;padding:16px 14px;position:relative;overflow:hidden;}
[data-testid="stMetric"]::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,#0ea5e9,#6366f1);}
[data-testid="stMetricValue"]{font-family:'Rajdhani',sans-serif!important;font-size:30px!important;
    color:#38bdf8!important;font-weight:700!important;line-height:1.1!important;}
[data-testid="stMetricLabel"]{font-size:10px!important;color:#1e3a52!important;
    text-transform:uppercase;letter-spacing:1.8px;margin-bottom:4px!important;}
.pcard{background:linear-gradient(160deg,#0b1828 0%,#070f1c 60%,#050a14 100%);
    border:1px solid rgba(56,189,248,.12);border-radius:20px;
    padding:28px 20px 22px;text-align:center;position:relative;overflow:hidden;min-height:300px;}
.pcard::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,transparent,#0ea5e9,#6366f1,transparent);}
.pcard::after{content:'';position:absolute;bottom:0;left:10%;right:10%;height:1px;
    background:linear-gradient(90deg,transparent,rgba(56,189,248,.3),transparent);}
.pcard-glow{position:absolute;top:20px;left:50%;transform:translateX(-50%);
    width:160px;height:160px;border-radius:50%;
    background:radial-gradient(circle,rgba(56,189,248,.08) 0%,transparent 70%);
    pointer-events:none;}
.pcard h2{font-family:'Rajdhani',sans-serif;font-size:24px;font-weight:700;
    color:#f0f8ff;margin:12px 0 4px;letter-spacing:.5px;}
.pcard-role{font-size:10px;color:#2d4a62;letter-spacing:2.5px;text-transform:uppercase;
    margin-bottom:16px;}
.rbadge{display:inline-block;background:rgba(14,165,233,.08);border:1px solid rgba(14,165,233,.2);
    border-radius:20px;font-size:9px;padding:3px 14px;color:#38bdf8;
    letter-spacing:2.5px;text-transform:uppercase;margin-bottom:20px;}
.player-img{width:180px;height:180px;border-radius:12px;border:none;
    object-fit:cover;object-position:top center;display:block;margin:0 auto;
    filter:drop-shadow(0 8px 24px rgba(56,189,248,.25));}
.player-img-wrap{position:relative;width:180px;margin:0 auto 14px;}
.vs-wrap{display:flex;align-items:center;justify-content:center;height:100%;flex-direction:column;gap:8px;}
.vs-txt{font-family:'Rajdhani',sans-serif;font-size:42px;font-weight:700;
    background:linear-gradient(135deg,#1a3050,#0e1a2a);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.vs-line{width:1px;height:60px;background:linear-gradient(180deg,transparent,#1a3050,transparent);}
.insight{border-radius:10px;padding:12px 16px;margin-top:14px;font-size:13px;line-height:1.65;}
.insight strong{font-family:'Rajdhani',sans-serif;font-size:14px;}
.ins-red  {background:rgba(248,113,113,.07);border-left:3px solid #f87171;}
.ins-amber{background:rgba(251,191,36,.07); border-left:3px solid #fbbf24;}
.ins-green{background:rgba(74,222,128,.07); border-left:3px solid #4ade80;}
.ins-blue {background:rgba(56,189,248,.07); border-left:3px solid #38bdf8;}
.slabel{font-family:'Rajdhani',sans-serif;font-size:15px;font-weight:700;color:#56b4e9;
    text-transform:uppercase;letter-spacing:2px;border-left:3px solid #0ea5e9;
    padding-left:10px;margin:22px 0 10px;}
.phcard{background:linear-gradient(145deg,#0a1520,#07101a);border:1px solid #0e1a2a;
    border-radius:14px;padding:14px;text-align:center;position:relative;overflow:hidden;}
.nodata{background:rgba(56,189,248,.03);border:1px dashed #0e1a2a;border-radius:10px;
    padding:18px;text-align:center;color:#1e3a52;font-size:13px;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:#07090f;}
::-webkit-scrollbar-thumb{background:#0e1a2a;border-radius:4px;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "msg_history"  not in st.session_state: st.session_state.msg_history  = []

# ─────────────────────────────────────────────────────────────────────────────
# IMAGE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
IMAGES_DIR = Path("player_images")

@st.cache_data
def load_player_id_map():
    if os.path.exists("player_ids.json"):
        with open("player_ids.json") as f: return json.load(f)
    return {}

PLAYER_ID_MAP = load_player_id_map()

def _monogram(name):
    ini = "".join(p[0].upper() for p in name.split()[:2])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 180 180">'
        '<defs>'
        '<linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#0a1828"/>'
        '<stop offset="100%" stop-color="#050e1a"/>'
        '</linearGradient>'
        '<radialGradient id="g2" cx="50%" cy="40%" r="60%">'
        '<stop offset="0%" stop-color="#0ea5e9" stop-opacity="0.12"/>'
        '<stop offset="100%" stop-color="#0a1828" stop-opacity="0"/>'
        '</radialGradient>'
        '</defs>'
        '<rect width="180" height="180" rx="12" fill="url(#g1)"/>'
        '<rect width="180" height="180" rx="12" fill="url(#g2)"/>'
        '<rect width="180" height="2" rx="1" fill="#0ea5e9" opacity="0.7"/>'
        f'<text x="90" y="112" text-anchor="middle" font-family="Rajdhani,sans-serif" '
        f'font-size="72" font-weight="700" fill="#38bdf8" opacity="0.9">{ini}</text>'
        '<rect x="30" y="158" width="120" height="1" fill="#1a3050" opacity="0.6"/>'
        '</svg>'
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

@st.cache_data(max_entries=500)
def _local_img(pid):
    p = IMAGES_DIR / f"{pid}.png"
    if p.exists(): return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
    return ""

def _resolve_pid(name):
    pid = PLAYER_ID_MAP.get(name, "")
    if not pid:
        close = get_close_matches(name, PLAYER_ID_MAP.keys(), n=1, cutoff=0.5)
        if close: pid = PLAYER_ID_MAP[close[0]]
    if not pid and " " in name:
        last = name.split()[-1]
        cands = [k for k in PLAYER_ID_MAP if k.endswith(last)]
        if len(cands) == 1: pid = PLAYER_ID_MAP[cands[0]]
        elif cands:
            m = next((k for k in cands if k.startswith(name[0].upper())), None)
            if m: pid = PLAYER_ID_MAP[m]
    return str(pid) if pid else ""

def player_img_tag(name):
    pid = _resolve_pid(name)
    src = (_local_img(pid) if pid and IMAGES_DIR.exists() else "") or _monogram(name)
    return f'<img src="{src}" class="player-img"/>'

# ─────────────────────────────────────────────────────────────────────────────
# DB QUERIES
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_lists():
    con = duckdb.connect(DB_PATH, read_only=True)
    s  = con.execute("SELECT DISTINCT striker FROM deliveries ORDER BY striker").df()["striker"].tolist()
    b  = con.execute("SELECT DISTINCT bowler  FROM deliveries ORDER BY bowler" ).df()["bowler" ].tolist()
    v  = con.execute("SELECT DISTINCT venue   FROM deliveries ORDER BY venue"  ).df()["venue"  ].tolist()
    sn = con.execute("SELECT DISTINCT season  FROM deliveries WHERE season>0 ORDER BY season DESC").df()["season"].tolist()
    con.close(); return s, b, v, sn

@st.cache_data(ttl=3600)
def matchup_stats(bat, bowl, venue=""):
    vf = f"AND venue='{venue}'" if venue and venue != "All Venues" else ""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
               sum(runs_batter) AS runs, sum(is_wicket) AS outs,
               round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
               count(DISTINCT match_id) AS matches,
               sum(CASE WHEN runs_batter=4 THEN 1 ELSE 0 END) AS fours,
               sum(CASE WHEN runs_batter=6 THEN 1 ELSE 0 END) AS sixes
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{bat}%')
          AND LOWER(bowler)  LIKE LOWER('%{bowl}%') {vf}""").df()
    con.close(); return df

@st.cache_data(ttl=3600)
def season_breakdown(bat, bowl):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT season,
               count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
               sum(runs_batter) AS runs, sum(is_wicket) AS outs,
               round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr
        FROM deliveries
        WHERE LOWER(striker) LIKE LOWER('%{bat}%')
          AND LOWER(bowler)  LIKE LOWER('%{bowl}%') AND season>0
        GROUP BY season ORDER BY season""").df()
    con.close(); return df

def _sf(s): return f"WHERE season={int(s)}" if s else "WHERE 1=1"
def _sa(s): return f"AND season={int(s)}"   if s else ""

@st.cache_data(ttl=3600)
def top_run_scorers(season, n=10):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT striker AS player, sum(runs_batter) AS runs,
               count(CASE WHEN extras_wides=0 THEN 1 END) AS balls,
               round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
               count(DISTINCT match_id) AS matches
        FROM deliveries {_sf(season)} GROUP BY striker ORDER BY runs DESC LIMIT {n}""").df()
    con.close(); return df

@st.cache_data(ttl=3600)
def top_wicket_takers(season, n=10):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT bowler AS player, sum(is_wicket) AS wickets,
               round(sum(runs_batter)*6.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
               count(DISTINCT match_id) AS matches
        FROM deliveries {_sf(season)} GROUP BY bowler ORDER BY wickets DESC LIMIT {n}""").df()
    con.close(); return df

@st.cache_data(ttl=3600)
def sr_leaders(season, n=10):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT striker AS player,
               round(sum(runs_batter)*100.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),1) AS sr,
               sum(runs_batter) AS runs, count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
        FROM deliveries WHERE 1=1 {_sa(season)}
        GROUP BY striker HAVING count(CASE WHEN extras_wides=0 THEN 1 END)>=100
        ORDER BY sr DESC LIMIT {n}""").df()
    con.close(); return df

@st.cache_data(ttl=3600)
def economy_leaders(season, n=10):
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(f"""
        SELECT bowler AS player,
               round(sum(runs_batter)*6.0/NULLIF(count(CASE WHEN extras_wides=0 THEN 1 END),0),2) AS economy,
               sum(is_wicket) AS wickets, count(CASE WHEN extras_wides=0 THEN 1 END) AS balls
        FROM deliveries WHERE 1=1 {_sa(season)}
        GROUP BY bowler HAVING count(CASE WHEN extras_wides=0 THEN 1 END)>=120
        ORDER BY economy ASC LIMIT {n}""").df()
    con.close(); return df

# ─────────────────────────────────────────────────────────────────────────────
# LOAD LISTS
# ─────────────────────────────────────────────────────────────────────────────
try:
    strikers, bowlers, venues, seasons = load_lists()
except Exception as e:
    st.error(f"⚠️ Database error: {e}")
    st.info("Run `setup_db.py` first.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand
    st.markdown("""
    <div style="padding:4px 0 16px;">
      <div style="font-family:'Rajdhani',sans-serif;font-size:24px;font-weight:700;
          color:#38bdf8;letter-spacing:2px;">CricIQ</div>
      <div style="font-size:10px;color:#2d4a62;letter-spacing:3px;
          text-transform:uppercase;margin-top:1px;">IPL Analytics</div>
    </div>""", unsafe_allow_html=True)

    st.divider()

    # Head-to-Head section
    st.markdown('<div style="font-size:10px;font-weight:700;color:#56b4e9;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">HEAD-TO-HEAD</div>', unsafe_allow_html=True)
    bs = st.text_input("bs", placeholder="Search batsman…", label_visibility="collapsed")
    bf = [p for p in strikers if bs.strip().lower() in p.lower()] if bs.strip() else strikers
    if not bf: bf = get_close_matches(bs.strip(), strikers, n=8, cutoff=0.4) or strikers
    batsman = st.selectbox("Batsman", bf, index=bf.index("V Kohli") if "V Kohli" in bf else 0, label_visibility="collapsed")

    ws = st.text_input("ws", placeholder="Search bowler…", label_visibility="collapsed")
    wf = [p for p in bowlers if ws.strip().lower() in p.lower()] if ws.strip() else bowlers
    if not wf: wf = get_close_matches(ws.strip(), bowlers, n=8, cutoff=0.4) or bowlers
    bowler = st.selectbox("Bowler", wf, index=wf.index("SP Narine") if "SP Narine" in wf else 0, label_visibility="collapsed")
    venue  = st.selectbox("Venue", ["All Venues"]+venues, label_visibility="collapsed")

    st.divider()

    # Leaderboards section
    st.markdown('<div style="font-size:10px;font-weight:700;color:#56b4e9;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">LEADERBOARDS</div>', unsafe_allow_html=True)
    lb_season = st.selectbox("Season", [0]+seasons, format_func=lambda x:"All Seasons" if x==0 else str(x), label_visibility="collapsed")
    top_n = st.slider("Top N", 5, 20, 10)

    st.divider()

    # AI status
    st.markdown('<div style="font-size:10px;color:#4ade80;letter-spacing:1px;">● AI ANALYST  ACTIVE</div>', unsafe_allow_html=True)
    if st.session_state.chat_history:
        if st.button("Clear chat history", use_container_width=True, key="_clr"):
            st.session_state.chat_history = []
            st.session_state.msg_history  = []
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:10px 0 26px;text-align:center;">
  <div style="font-size:10px;color:#2d4a62;letter-spacing:6px;text-transform:uppercase;margin-bottom:10px;">IPL ANALYTICS PLATFORM</div>
  <div style="font-family:'Rajdhani',sans-serif;font-size:46px;font-weight:700;line-height:1;
              background:linear-gradient(100deg,#38bdf8 20%,#818cf8 65%,#e879f9 100%);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
    CricIQ
  </div>
  <div style="width:44px;height:2px;background:linear-gradient(90deg,#38bdf8,#818cf8);margin:10px auto 0;border-radius:2px;"></div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6,tab7 = st.tabs([
    "HEAD-TO-HEAD",
    "LEADERBOARDS",
    "FORM TRACKER",
    "BOWLER PHASES",
    "PHASE SCORING",
    "MATCH PREDICTOR",
    "SIMULATOR",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HEAD-TO-HEAD
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    c1,cv,c2 = st.columns([5,1,5])
    with c1:
        st.markdown(f"""
        <div class="pcard">
          <div class="pcard-glow"></div>
          <div class="rbadge">Batsman</div>
          {player_img_tag(batsman)}
          <h2>{batsman}</h2>
          <div class="pcard-role">Batter · {batsman.split()[0] if batsman else ""}</div>
        </div>""", unsafe_allow_html=True)
    with cv:
        st.markdown('''<div class="vs-wrap">
          <div class="vs-line"></div>
          <div class="vs-txt">VS</div>
          <div class="vs-line"></div>
        </div>''', unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="pcard">
          <div class="pcard-glow"></div>
          <div class="rbadge">Bowler</div>
          {player_img_tag(bowler)}
          <h2>{bowler}</h2>
          <div class="pcard-role">Bowler · {bowler.split()[0] if bowler else ""}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    df = matchup_stats(batsman, bowler, venue)
    balls = int(df['balls'][0]) if not df.empty else 0

    if balls > 0:
        runs=int(df['runs'][0]); outs=int(df['outs'][0])
        sr=float(df['sr'][0] or 0); matches=int(df['matches'][0])
        fours=int(df['fours'][0]); sixes=int(df['sixes'][0])

        cols = st.columns(7)
        for col,label,val in zip(cols,
            ["Balls","Runs","Outs","Strike Rate","Matches","4s","6s"],
            [balls,runs,outs,f"{sr:.1f}",matches,fours,sixes]):
            col.metric(label, val)

        if   outs>=4:                  cls,t,b="red",  "🔴 BOWLER DOMINATES",      f"{bowler} dismissed {batsman} {outs} times. Prime powerplay & death option."
        elif outs>=2 and sr<110:       cls,t,b="red",  "🟠 BOWLER HAS CLEAR EDGE", f"Multiple dismissals ({outs}), SR just {sr:.1f}."
        elif sr<100:                   cls,t,b="amber","🟡 BOWLER CONTAINING",      f"SR {sr:.1f} — excellent containment in middle overs."
        elif sr<130 and outs>=2:       cls,t,b="amber","🟡 SLIGHT BOWLER EDGE",     f"SR {sr:.1f} with {outs} dismissals."
        elif sr>170:                   cls,t,b="green","🟢 BATSMAN DOMINATES",      f"SR {sr:.1f} with {sixes} sixes. Rotate this bowler."
        elif sr>140:                   cls,t,b="green","🔵 BATSMAN COMFORTABLE",    f"SR {sr:.1f} shows fluency."
        else:                          cls,t,b="blue", "🔵 EVEN CONTEST",           f"{balls} balls · {runs} runs · {outs} outs."
        st.markdown(f'<div class="insight ins-{cls}"><strong>{t}</strong><br>{b}</div>', unsafe_allow_html=True)

        st.markdown('<div class="slabel">Season Breakdown</div>', unsafe_allow_html=True)
        sdf = season_breakdown(batsman, bowler)
        if not sdf.empty:
            sdf.columns=["Season","Balls","Runs","Outs","SR"]
            sdf["Season"]=sdf["Season"].astype(str)
            st.dataframe(sdf, use_container_width=True, hide_index=True)
        else:
            st.markdown('<div class="nodata">No season data found.</div>', unsafe_allow_html=True)
    else:
        v_note = f"at **{venue}**" if venue!="All Venues" else "across all venues"
        st.markdown(f'<div class="insight ins-blue"><strong>🔵 No Records</strong><br>{batsman} has not faced {bowler} {v_note}.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — LEADERBOARDS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    sl = str(lb_season) if lb_season else "All Seasons"
    st.markdown(f'<div class="slabel">Season: {sl}</div>', unsafe_allow_html=True)
    ca,cb = st.columns(2)
    with ca:
        st.markdown("#### 🏆 Top Run Scorers")
        rdf = top_run_scorers(lb_season, top_n)
        if not rdf.empty:
            rdf.columns=["Player","Runs","Balls","SR","Matches"]; rdf.insert(0,"#",range(1,len(rdf)+1))
            st.dataframe(rdf, use_container_width=True, hide_index=True)
        else: st.markdown('<div class="nodata">No data.</div>', unsafe_allow_html=True)
    with cb:
        st.markdown("#### 🎯 Top Wicket Takers")
        wdf = top_wicket_takers(lb_season, top_n)
        if not wdf.empty:
            wdf.columns=["Player","Wickets","Economy","Matches"]; wdf.insert(0,"#",range(1,len(wdf)+1))
            st.dataframe(wdf, use_container_width=True, hide_index=True)
        else: st.markdown('<div class="nodata">No data.</div>', unsafe_allow_html=True)

    st.divider()
    cc,cd = st.columns(2)
    with cc:
        st.markdown("#### ⚡ Best Strike Rates")
        st.caption("Min 100 balls")
        srdf = sr_leaders(lb_season, top_n)
        if not srdf.empty:
            srdf.columns=["Player","SR","Runs","Balls"]; srdf.insert(0,"#",range(1,len(srdf)+1))
            st.dataframe(srdf, use_container_width=True, hide_index=True)
        else: st.markdown('<div class="nodata">No data.</div>', unsafe_allow_html=True)
    with cd:
        st.markdown("#### 💎 Best Economy")
        st.caption("Min 120 balls")
        edf = economy_leaders(lb_season, top_n)
        if not edf.empty:
            edf.columns=["Player","Economy","Wickets","Balls"]; edf.insert(0,"#",range(1,len(edf)+1))
            st.dataframe(edf, use_container_width=True, hide_index=True)
        else: st.markdown('<div class="nodata">No data.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FORM TRACKER
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    from analytics import get_batsman_form, get_bowler_form, get_form_summary
    st.markdown('<div class="slabel">Player Form Tracker</div>', unsafe_allow_html=True)

    f1,f2,f3,f4 = st.columns([3,2,2,2])
    with f1: form_player = st.selectbox("Player",strikers,key="fp",index=strikers.index("V Kohli") if "V Kohli" in strikers else 0,label_visibility="collapsed")
    with f2: form_role   = st.radio("Role",["Batsman","Bowler"],horizontal=True,key="fr")
    with f3: form_season = st.selectbox("Season",[0]+seasons,format_func=lambda x:"All" if x==0 else str(x),key="fs",label_visibility="collapsed")
    with f4: last_n      = st.slider("Last N",5,30,15,key="fn")

    if form_role=="Batsman":
        fdf = get_batsman_form(form_player,form_season,last_n)
        sm  = get_form_summary(form_player,"batsman",form_season)
        if fdf.empty:
            st.markdown('<div class="nodata">No batting data found.</div>', unsafe_allow_html=True)
        else:
            s1,s2,s3,s4 = st.columns(4)
            s1.metric("Last 5 Avg",  sm.get("last5_avg",0))
            s2.metric("Career Avg",  sm.get("career_avg",0))
            s3.metric("Matches",     sm.get("matches",0))
            s4.metric("Form",        sm.get("streak","—"))

            fig = go.Figure()
            colors=[GREEN if r>=fdf["career_avg"].iloc[0] else RED for r in fdf["runs"]]
            fig.add_trace(go.Bar(x=fdf["match_num"],y=fdf["runs"],name="Runs",marker_color=colors,opacity=0.6,
                hovertemplate="Match %{x}<br>Runs: %{y}<extra></extra>"))
            fig.add_trace(go.Scatter(x=fdf["match_num"],y=fdf["rolling_avg"],mode="lines+markers",name="5-match avg",
                line=dict(color=CYAN,width=2.5),marker=dict(size=5)))
            fig.add_hline(y=fdf["career_avg"].iloc[0],line_dash="dash",line_color=INDIGO,line_width=1.5,
                annotation_text=f"Career avg {fdf['career_avg'].iloc[0]}",annotation_font_color=INDIGO)
            fig.update_layout(**PLOT_BG,
                title=dict(text=f"{form_player} — Batting Form",font=dict(color="#f0f8ff",size=14),x=0),
                xaxis=dict(**AX,title="Match"),yaxis=dict(**AX,title="Runs"),height=340,
                legend=dict(orientation="h",y=1.1,bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig,use_container_width=True)

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=fdf["match_num"],y=fdf["sr"],mode="lines+markers",name="SR",
                line=dict(color=AMBER,width=2),fill="tozeroy",fillcolor="rgba(251,191,36,0.05)"))
            dis=fdf[fdf["dismissed"]==1]
            if not dis.empty:
                fig2.add_trace(go.Scatter(x=dis["match_num"],y=dis["sr"],mode="markers",name="Out",
                    marker=dict(color=RED,size=8,symbol="x")))
            fig2.add_hline(y=100,line_dash="dot",line_color="#1a3050",line_width=1)
            fig2.update_layout(**PLOT_BG,
                title=dict(text="Strike Rate Per Match",font=dict(color="#f0f8ff",size=13),x=0),
                xaxis=dict(**AX,title="Match"),yaxis=dict(**AX,title="SR"),height=230,
                legend=dict(orientation="h",y=1.15,bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig2,use_container_width=True)
    else:
        bwl_sel = st.selectbox("Bowler",bowlers,index=bowlers.index(bowler) if bowler in bowlers else 0,key="fbwl",label_visibility="collapsed")
        fdf = get_bowler_form(bwl_sel,form_season,last_n)
        sm  = get_form_summary(bwl_sel,"bowler",form_season)
        if fdf.empty:
            st.markdown('<div class="nodata">No bowling data found.</div>', unsafe_allow_html=True)
        else:
            s1,s2,s3,s4 = st.columns(4)
            s1.metric("Last 5 Wkts",    sm.get("last5_wkts",0))
            s2.metric("Last 5 Economy", sm.get("last5_eco",0))
            s3.metric("Career Economy", sm.get("career_eco",0))
            s4.metric("Form",           sm.get("streak","—"))

            fig = go.Figure()
            wkc=[GREEN if w>=2 else (AMBER if w==1 else RED) for w in fdf["wickets"]]
            fig.add_trace(go.Bar(x=fdf["match_num"],y=fdf["wickets"],name="Wickets",marker_color=wkc,opacity=0.65))
            fig.add_trace(go.Scatter(x=fdf["match_num"],y=fdf["rolling_wickets"],mode="lines+markers",name="5-match avg",
                line=dict(color=CYAN,width=2.5),marker=dict(size=5)))
            fig.update_layout(**PLOT_BG,
                title=dict(text=f"{bwl_sel} — Wickets Per Match",font=dict(color="#f0f8ff",size=14),x=0),
                xaxis=dict(**AX,title="Match"),yaxis=dict(**AX,title="Wickets"),height=320,
                legend=dict(orientation="h",y=1.1,bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig,use_container_width=True)

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=fdf["match_num"],y=fdf["economy"],mode="lines+markers",name="Economy",
                line=dict(color=AMBER,width=2),fill="tozeroy",fillcolor="rgba(251,191,36,0.05)"))
            fig2.add_trace(go.Scatter(x=fdf["match_num"],y=fdf["rolling_economy"],mode="lines",name="5-match avg",
                line=dict(color=INDIGO,width=2,dash="dash")))
            fig2.add_hline(y=sm.get("career_eco",8),line_dash="dot",line_color="#1a3050",line_width=1)
            fig2.update_layout(**PLOT_BG,
                title=dict(text="Economy Per Match",font=dict(color="#f0f8ff",size=13),x=0),
                xaxis=dict(**AX,title="Match"),yaxis=dict(**AX,title="Economy"),height=250,
                legend=dict(orientation="h",y=1.15,bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig2,use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — BOWLER PHASE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    from analytics import get_bowler_phase_stats, get_bowler_over_by_over, get_bowler_vs_teams
    st.markdown('<div class="slabel">Bowler Phase Analysis</div>', unsafe_allow_html=True)

    p1,p2 = st.columns([3,2])
    with p1: phase_bowler = st.selectbox("Bowler",bowlers,key="pbwl",index=bowlers.index("JJ Bumrah") if "JJ Bumrah" in bowlers else 0,label_visibility="collapsed")
    with p2: phase_season = st.selectbox("Season",[0]+seasons,format_func=lambda x:"All" if x==0 else str(x),key="pbs",label_visibility="collapsed")

    pdf = get_bowler_phase_stats(phase_bowler,phase_season)
    obo = get_bowler_over_by_over(phase_bowler,phase_season)

    if pdf.empty:
        st.markdown('<div class="nodata">No data found.</div>', unsafe_allow_html=True)
    else:
        PC=[CYAN,INDIGO,AMBER]
        mc=st.columns(3)
        for i,row in pdf.iterrows():
            with mc[i]:
                st.markdown(f"""<div class="phcard">
                    <div style="position:absolute;top:0;left:0;right:0;height:2px;background:{PC[i]};"></div>
                    <div style="font-family:Rajdhani,sans-serif;font-size:10px;color:#1e3a52;letter-spacing:1.5px;text-transform:uppercase;">{row['phase']}</div>
                    <div style="font-family:Rajdhani,sans-serif;font-size:32px;font-weight:700;color:{PC[i]};margin:4px 0 1px;">{row['economy']}</div>
                    <div style="font-size:9px;color:#1e3a52;">Economy</div>
                    <div style="display:flex;justify-content:space-around;margin-top:10px;">
                        <div><div style="color:#f0f8ff;font-weight:600;font-size:14px;">{int(row['wickets'])}</div><div style="font-size:9px;color:#1e3a52;">Wkts</div></div>
                        <div><div style="color:#f0f8ff;font-weight:600;font-size:14px;">{row['dot_pct']}%</div><div style="font-size:9px;color:#1e3a52;">Dot%</div></div>
                        <div><div style="color:#f0f8ff;font-weight:600;font-size:14px;">{int(row['balls'])}</div><div style="font-size:9px;color:#1e3a52;">Balls</div></div>
                    </div></div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if not obo.empty:
            pcols=[CYAN if o<=6 else (INDIGO if o<=15 else AMBER) for o in obo["over_num"]]
            fig=go.Figure()
            fig.add_trace(go.Bar(x=obo["over_num"],y=obo["economy"],marker_color=pcols,opacity=0.8,
                hovertemplate="Over %{x}<br>Economy: %{y}<extra></extra>"))
            fig.add_vrect(x0=.5,x1=6.5,  fillcolor=CYAN,  opacity=0.03,line_width=0)
            fig.add_vrect(x0=6.5,x1=15.5,fillcolor=INDIGO,opacity=0.03,line_width=0)
            fig.add_vrect(x0=15.5,x1=20.5,fillcolor=AMBER,opacity=0.03,line_width=0)
            for xm,lbl,col in [(3.5,"POWERPLAY",CYAN),(11,"MIDDLE",INDIGO),(18,"DEATH",AMBER)]:
                fig.add_annotation(x=xm,y=obo["economy"].max()*1.05,text=lbl,showarrow=False,font=dict(color=col,size=10))
            fig.update_layout(**PLOT_BG,
                title=dict(text=f"{phase_bowler} — Economy by Over",font=dict(color="#f0f8ff",size=14),x=0),
                xaxis=dict(**AX,tickvals=list(range(1,21)),title="Over"),
                yaxis=dict(**AX,title="Economy"),height=320,showlegend=False)
            st.plotly_chart(fig,use_container_width=True)

        tvt=get_bowler_vs_teams(phase_bowler,phase_season)
        if not tvt.empty:
            st.markdown('<div class="slabel" style="margin-top:4px;">vs Each Team</div>', unsafe_allow_html=True)
            tvt.columns=["Team","Balls","Wickets","Economy","Matches"]
            tvt.insert(0,"#",range(1,len(tvt)+1))
            st.dataframe(tvt,use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PHASE SCORING
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    from analytics import get_batsman_phase_stats, get_batsman_over_by_over

    ps1,ps2 = st.columns([4,2])
    with ps1:
        phase_bat = st.selectbox("Batsman", strikers, key="psbat",
            index=strikers.index("V Kohli") if "V Kohli" in strikers else 0,
            label_visibility="collapsed")
    with ps2:
        pbs2 = st.selectbox("Season", [0]+seasons,
            format_func=lambda x:"All Seasons" if x==0 else str(x),
            key="psbs", label_visibility="collapsed")

    psdf = get_batsman_phase_stats(phase_bat, pbs2)
    obo2 = get_batsman_over_by_over(phase_bat, pbs2)

    if psdf.empty:
        st.markdown('<div class="nodata">No batting data found.</div>', unsafe_allow_html=True)
    else:
        PC = [CYAN, INDIGO, AMBER]
        PHASE_SUB = {"Powerplay":"Overs 1–6","Middle":"Overs 7–15","Death":"Overs 16–20"}

        # ── Row 1: Phase stat cards ──
        c1,c2,c3 = st.columns(3)
        for col_w,(idx,row) in zip([c1,c2,c3], psdf.iterrows()):
            i   = list(psdf.index).index(idx)
            clr = PC[i]
            sub = PHASE_SUB.get(row['phase'], row['phase'])
            src = "#4ade80" if row['sr']>=140 else "#fbbf24" if row['sr']>=110 else "#f87171"
            card = (
                '<div style="background:linear-gradient(145deg,#0a1520,#07101a);'
                'border:1px solid #0e1a2a;border-radius:16px;padding:18px 16px;'
                'position:relative;overflow:hidden;text-align:center;">'
                f'<div style="position:absolute;top:0;left:0;right:0;height:3px;background:{clr};"></div>'
                f'<div style="font-family:Rajdhani,sans-serif;font-size:11px;font-weight:700;'
                f'color:{clr};letter-spacing:2px;text-transform:uppercase;">{row["phase"]}</div>'
                f'<div style="font-size:10px;color:#1e3a52;margin-bottom:10px;">{sub}</div>'
                f'<div style="font-family:Rajdhani,sans-serif;font-size:44px;font-weight:700;'
                f'color:{src};line-height:1;">{row["sr"]}</div>'
                '<div style="font-size:10px;color:#1e3a52;letter-spacing:1px;margin-bottom:14px;">STRIKE RATE</div>'
                '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">'
                '<div style="background:#060c18;border-radius:8px;padding:8px 4px;">'
                f'<div style="font-family:Rajdhani,sans-serif;font-size:18px;font-weight:700;color:#f0f8ff;">{int(row["runs"])}</div>'
                '<div style="font-size:9px;color:#1e3a52;">RUNS</div></div>'
                '<div style="background:#060c18;border-radius:8px;padding:8px 4px;">'
                f'<div style="font-family:Rajdhani,sans-serif;font-size:18px;font-weight:700;color:#4ade80;">{row["boundary_pct"]}%</div>'
                '<div style="font-size:9px;color:#1e3a52;">BOUNDARY</div></div>'
                '<div style="background:#060c18;border-radius:8px;padding:8px 4px;">'
                f'<div style="font-family:Rajdhani,sans-serif;font-size:18px;font-weight:700;color:#f87171;">{row["dot_pct"]}%</div>'
                '<div style="font-size:9px;color:#1e3a52;">DOT</div></div>'
                '</div></div>'
            )
            col_w.markdown(card, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Row 2: Bar chart (3/5) + Radar (2/5) ──
        col_bar, col_rad = st.columns([3,2])

        with col_bar:
            st.markdown('<div class="slabel" style="margin-top:0;">Phase Comparison</div>', unsafe_allow_html=True)
            fig = go.Figure()
            for nm,clr,key in [("Strike Rate",CYAN,"sr"),("Boundary %",AMBER,"boundary_pct"),("Dot Ball %",RED,"dot_pct")]:
                fig.add_trace(go.Bar(name=nm, x=psdf["phase"], y=psdf[key],
                    marker=dict(color=clr, opacity=0.85, line=dict(width=0)),
                    hovertemplate=f"<b>%{{x}}</b><br>{nm}: %{{y}}<extra></extra>"))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter",color="#90b4ce",size=12),
                margin=dict(l=10,r=10,t=10,b=10), barmode="group",
                xaxis=dict(**AX,tickfont=dict(size=13,family="Rajdhani",color="#f0f8ff")),
                yaxis=dict(**AX,title=""),
                legend=dict(orientation="h",y=1.1,bgcolor="rgba(0,0,0,0)",font=dict(size=11)),
                height=280, bargap=0.25, bargroupgap=0.08)
            st.plotly_chart(fig, use_container_width=True)

        with col_rad:
            st.markdown('<div class="slabel" style="margin-top:0;">Phase Radar</div>', unsafe_allow_html=True)
            cats = ["Strike Rate","Boundary%","Sixes","Consistency","Strike Rate"]
            figr = go.Figure()
            for i,(idx,row) in enumerate(psdf.iterrows()):
                vals = [
                    min(row["sr"]/15,10),
                    min(row["boundary_pct"]/4,10),
                    min((row["sixes"]/max(row["balls"],1))*120,10),
                    min((1-row["dot_pct"]/100)*13,10),
                    min(row["sr"]/15,10),
                ]
                hx = PC[i].lstrip('#')
                rgb = ",".join(str(int(hx[j:j+2],16)) for j in (0,2,4))
                figr.add_trace(go.Scatterpolar(r=vals,theta=cats,fill="toself",
                    name=row["phase"],line=dict(color=PC[i],width=2.5),
                    fillcolor=f"rgba({rgb},0.12)"))
            figr.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20,r=20,t=20,b=20),
                polar=dict(bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True,range=[0,10],gridcolor="#0e1a2a",
                        linecolor="#0e1a2a",tickfont=dict(size=8,color="#1e3a52")),
                    angularaxis=dict(gridcolor="#0e1a2a",linecolor="#0e1a2a",
                        tickfont=dict(size=11,color="#6b8fa8",family="Rajdhani"))),
                font=dict(color="#90b4ce",family="Inter"),
                legend=dict(bgcolor="rgba(0,0,0,0)",orientation="h",
                    y=-0.15,font=dict(size=11)),
                height=280)
            st.plotly_chart(figr, use_container_width=True)

        # ── Row 3: Over-by-over full width ──
        if not obo2.empty:
            st.markdown('<div class="slabel">Over-by-Over Runs & Strike Rate</div>', unsafe_allow_html=True)
            pcols2 = [CYAN if o<=6 else (INDIGO if o<=15 else AMBER) for o in obo2["over_num"]]
            fig2 = go.Figure()
            for x0,x1,fc in [(.5,6.5,CYAN),(6.5,15.5,INDIGO),(15.5,20.5,AMBER)]:
                fig2.add_vrect(x0=x0,x1=x1,fillcolor=fc,opacity=0.04,line_width=0)
            for xm,lbl,clr in [(3.5,"POWERPLAY",CYAN),(11,"MIDDLE",INDIGO),(18,"DEATH",AMBER)]:
                fig2.add_annotation(x=xm,y=obo2["runs"].max()*1.06,text=lbl,
                    showarrow=False,font=dict(color=clr,size=9,family="Rajdhani"),xanchor="center")
            fig2.add_trace(go.Bar(x=obo2["over_num"],y=obo2["runs"],name="Runs",
                marker=dict(color=pcols2,opacity=0.65,line=dict(width=0)),
                hovertemplate="Over %{x}<br>Runs: %{y}<extra></extra>"))
            fig2.add_trace(go.Scatter(x=obo2["over_num"],y=obo2["sr"],mode="lines+markers",
                name="Strike Rate",line=dict(color=GREEN,width=2.5),
                marker=dict(size=5,color=GREEN),yaxis="y2",
                hovertemplate="Over %{x}<br>SR: %{y}<extra></extra>"))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter",color="#90b4ce",size=12),
                margin=dict(l=10,r=50,t=20,b=10),
                xaxis=dict(**AX,tickvals=list(range(1,21)),title="Over"),
                yaxis=dict(**AX,title="Runs"),
                yaxis2=dict(title="SR",overlaying="y",side="right",
                    gridcolor="#0f2035",showgrid=False,
                    tickfont=dict(color=GREEN,size=10)),
                height=300,bargap=0.2,
                legend=dict(orientation="h",y=1.08,bgcolor="rgba(0,0,0,0)",font=dict(size=11)))
            st.plotly_chart(fig2, use_container_width=True)


# TAB 6 — OVER-BY-OVER MATCH PREDICTOR
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    IPL_TEAMS = get_teams()
    get_players_by_team = lambda team, role="batsman": get_squad(team)
    from simulator import (run_simulation, win_probability,
                           prefetch_profiles, _simulate_once,
                           _fetch_venue_mult)
    import numpy as _np2

    # ── Extra CSS ──
    st.markdown("""
    <style>
    .obо-header{text-align:center;padding:6px 0 18px;}
    .obо-title{font-family:'Rajdhani',sans-serif;font-size:28px;font-weight:700;
        background:linear-gradient(100deg,#38bdf8 30%,#818cf8 80%);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
    .obо-sub{font-size:12px;color:#1e3a52;margin-top:4px;}
    .setup-section{background:#060c18;border:1px solid #0a1525;border-radius:14px;
        padding:16px 18px 10px;margin-bottom:12px;}
    .setup-label{font-size:10px;font-weight:600;color:#38bdf8;letter-spacing:1.5px;
        text-transform:uppercase;margin-bottom:8px;}
    .over-live-card{background:linear-gradient(145deg,#0a1520,#07101a);
        border:1px solid rgba(56,189,248,.15);border-radius:16px;padding:20px;
        position:relative;overflow:hidden;margin-bottom:12px;}
    .over-live-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
        background:linear-gradient(90deg,#0ea5e9,#6366f1);}
    .scorecard-live{background:#060c18;border:1px solid #0a1525;
        border-radius:12px;overflow:hidden;}
    .sc-row{display:flex;align-items:center;padding:9px 14px;
        border-bottom:1px solid #050b14;font-size:13px;}
    .sc-row:last-child{border-bottom:none;}
    .ball-chip{display:inline-flex;align-items:center;justify-content:center;
        width:24px;height:24px;border-radius:50%;font-size:11px;
        font-weight:700;margin:1px;flex-shrink:0;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="obо-header">
      <div class="obо-title">🏏 Over-by-Over Predictor</div>
      <div class="obо-sub">Pick your striker · non-striker · bowler · simulate one over at a time</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Session state for live match ──
    if "obo_score"    not in st.session_state: st.session_state.obo_score    = 0
    if "obo_wickets"  not in st.session_state: st.session_state.obo_wickets  = 0
    if "obo_over"     not in st.session_state: st.session_state.obo_over     = 1
    if "obo_history"  not in st.session_state: st.session_state.obo_history  = []
    if "obo_lineup"   not in st.session_state: st.session_state.obo_lineup   = []
    if "obo_setup"    not in st.session_state: st.session_state.obo_setup    = False
    if "obo_innings"  not in st.session_state: st.session_state.obo_innings  = 1
    if "obo_target"   not in st.session_state: st.session_state.obo_target   = 0

    # ── SETUP PHASE ──
    if not st.session_state.obo_setup:
        st.markdown('<div class="setup-section"><div class="setup-label">⚙ Match Setup</div>', unsafe_allow_html=True)
        s1,s2,s3 = st.columns(3)
        with s1:
            mi_i = IPL_TEAMS.index("Mumbai Indians") if "Mumbai Indians" in IPL_TEAMS else 0
            obo_bat_team = st.selectbox("Batting Team", IPL_TEAMS, key="obt", index=mi_i)
        with s2:
            csk_i = IPL_TEAMS.index("Chennai Super Kings") if "Chennai Super Kings" in IPL_TEAMS else 1
            obo_bowl_team = st.selectbox("Bowling Team", IPL_TEAMS, key="obwlt", index=csk_i)
        with s3:
            obo_venue = st.selectbox("Venue", ["All Venues"]+venues, key="ov")
        s4,s5,s6,s7 = st.columns(4)
        with s4: obo_innings  = st.radio("Innings",[1,2],horizontal=True,format_func=lambda x:"1st" if x==1 else "2nd",key="oi")
        with s5: obo_start_over = st.slider("Start Over",1,20,1,key="oso")
        with s6: obo_start_score = st.number_input("Starting Score",0,400,0,key="oss")
        with s7: obo_start_wkts  = st.number_input("Wickets Fallen",0,9,0,key="osw")
        obo_target_val = 0
        if obo_innings == 2:
            obo_target_val = st.number_input("Target",50,400,180,key="otgt")
        st.markdown('</div>', unsafe_allow_html=True)

        # Batting lineup
        st.markdown('<div class="setup-section"><div class="setup-label">🏏 Batting Order (top 5)</div>', unsafe_allow_html=True)
        bat_pool_s = get_players_by_team(obo_bat_team,"batsman") or strikers
        lc = st.columns(5)
        lineup_init = []
        for li in range(5):
            with lc[li]:
                def_li = min(li, len(bat_pool_s)-1)
                p = st.selectbox(
                    ["Striker","Non-Striker","#3","#4","#5"][li],
                    [x for x in bat_pool_s if x not in lineup_init] or bat_pool_s,
                    key=f"obl_{li}", index=0)
                lineup_init.append(p)
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("▶  Start Match", type="primary", use_container_width=True, key="obo_start"):
            st.session_state.obo_score   = int(obo_start_score)
            st.session_state.obo_wickets = int(obo_start_wkts)
            st.session_state.obo_over    = int(obo_start_over)
            st.session_state.obo_history = []
            st.session_state.obo_lineup  = lineup_init
            st.session_state.obo_bat_team  = obo_bat_team
            st.session_state.obo_bowl_team = obo_bowl_team
            st.session_state.obo_venue     = obo_venue
            st.session_state.obo_innings   = obo_innings
            st.session_state.obo_target    = obo_target_val
            st.session_state.obo_setup     = True
            st.rerun()

    # ── LIVE SIMULATION PHASE ──
    else:
        score   = st.session_state.obo_score
        wickets = st.session_state.obo_wickets
        over    = st.session_state.obo_over
        lineup  = st.session_state.obo_lineup
        bat_t   = st.session_state.obo_bat_team
        bowl_t  = st.session_state.obo_bowl_team
        venue   = st.session_state.obo_venue
        innings = st.session_state.obo_innings
        target  = st.session_state.obo_target

        # ── Live scoreboard ──
        overs_done = over - 1
        rr_cur = round(score / max(overs_done,1), 2)
        rrr    = round((target-score)/max(20-overs_done,1),2) if innings==2 and target else None

        rr_col = "#4ade80" if rr_cur >= 8 else "#fbbf24" if rr_cur >= 6 else "#f87171"
        st.markdown(f"""
        <div class="over-live-card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="font-family:'Rajdhani',sans-serif;font-size:52px;font-weight:700;
                  color:#f0f8ff;line-height:1;">{score}<span style="font-size:28px;color:#4a6580;">/{wickets}</span></div>
              <div style="font-size:12px;color:#1e3a52;margin-top:2px;">{bat_t} · Over {over-1}.0</div>
            </div>
            <div style="display:flex;gap:20px;flex-wrap:wrap;">
              <div style="text-align:center;">
                <div style="font-family:'Rajdhani',sans-serif;font-size:26px;font-weight:700;color:{rr_col};">{rr_cur}</div>
                <div style="font-size:10px;color:#1e3a52;">Run Rate</div>
              </div>
              <div style="text-align:center;">
                <div style="font-family:'Rajdhani',sans-serif;font-size:26px;font-weight:700;color:#38bdf8;">{20-over+1}</div>
                <div style="font-size:10px;color:#1e3a52;">Overs Left</div>
              </div>
              {f'<div style="text-align:center;"><div style="font-family:Rajdhani,sans-serif;font-size:26px;font-weight:700;color:#fbbf24;">{rrr}</div><div style="font-size:10px;color:#1e3a52;">Req RR</div></div>' if rrr else ""}
              {f'<div style="text-align:center;"><div style="font-family:Rajdhani,sans-serif;font-size:26px;font-weight:700;color:#818cf8;">{target-score}</div><div style="font-size:10px;color:#1e3a52;">Need</div></div>' if innings==2 and target else ""}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Check if innings over ──
        if over > 20 or wickets >= 10:
            st.markdown(f"""
            <div style="background:rgba(74,222,128,.08);border:1px solid rgba(74,222,128,.2);
                border-radius:14px;padding:20px;text-align:center;margin:12px 0;">
              <div style="font-family:'Rajdhani',sans-serif;font-size:28px;font-weight:700;color:#4ade80;">
                Innings Complete
              </div>
              <div style="font-size:16px;color:#c8daea;margin-top:6px;">
                Final Score: {score}/{wickets} {"· Target reached! 🎉" if innings==2 and target and score>=target else "· Target not reached" if innings==2 and target else ""}
              </div>
            </div>""", unsafe_allow_html=True)
            if st.button("🔄 New Match", use_container_width=True, key="obo_reset"):
                for k in ["obo_score","obo_wickets","obo_over","obo_history",
                          "obo_lineup","obo_setup","obo_innings","obo_target"]:
                    del st.session_state[k]
                st.rerun()

        else:
            # ── Pick players for this over ──
            phase_label   = "Powerplay" if over<=6 else ("Death" if over>=16 else "Middle")
            bat_pool_live  = get_players_by_team(bat_t, "batsman") or strikers
            bowl_pool_live = get_players_by_team(bowl_t, "bowler") or bowlers

            # Safety check — ensure pools are not empty
            if not bat_pool_live:  bat_pool_live  = strikers
            if not bowl_pool_live: bowl_pool_live = bowlers

            # Defaults from current lineup
            striker_def = lineup[0] if lineup and len(lineup)>0 else bat_pool_live[0]
            nonstr_def  = lineup[1] if lineup and len(lineup)>1 else bat_pool_live[min(1,len(bat_pool_live)-1)]

            # Last bowler (to avoid consecutive)
            last_bowl = st.session_state.obo_history[-1]["bowler"] if st.session_state.obo_history else None
            # Put last bowler at bottom of list
            if last_bowl and last_bowl in bowl_pool_live and len(bowl_pool_live) > 1:
                bowl_opts = [b for b in bowl_pool_live if b != last_bowl] + [last_bowl]
            else:
                bowl_opts = bowl_pool_live

            st.markdown(
                f'<div class="setup-section">'
                f'<div class="setup-label">🎯 Over {over} · {phase_label}</div>',
                unsafe_allow_html=True)

            pc1, pc2, pc3 = st.columns(3)

            with pc1:
                st.markdown('<div style="font-size:11px;color:#4a6580;margin-bottom:4px;">🏏 On Strike</div>', unsafe_allow_html=True)
                striker_sel = st.selectbox(
                    "On Strike",
                    bat_pool_live,
                    key=f"obo_str_{over}",
                    index=bat_pool_live.index(striker_def) if striker_def in bat_pool_live else 0,
                    label_visibility="collapsed")

            with pc2:
                st.markdown('<div style="font-size:11px;color:#4a6580;margin-bottom:4px;">🏃 Non-Striker</div>', unsafe_allow_html=True)
                ns_pool = [x for x in bat_pool_live if x != striker_sel]
                if not ns_pool: ns_pool = bat_pool_live
                nonstr_sel = st.selectbox(
                    "Non-Striker",
                    ns_pool,
                    key=f"obo_ns_{over}",
                    index=ns_pool.index(nonstr_def) if nonstr_def in ns_pool else 0,
                    label_visibility="collapsed")

            with pc3:
                st.markdown('<div style="font-size:11px;color:#4a6580;margin-bottom:4px;">🎯 Bowler</div>', unsafe_allow_html=True)
                bowler_sel = st.selectbox(
                    "Bowler",
                    bowl_opts,
                    key=f"obo_bowl_{over}",
                    index=0,
                    label_visibility="collapsed")

            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown(
                f'<div style="font-size:11px;color:#1e3a52;margin:-6px 0 12px;text-align:center;">'
                f'{bowler_sel} bowling to {striker_sel} · {phase_label}</div>',
                unsafe_allow_html=True)

            if st.button(f"⚡ Simulate Over {over}", type="primary", use_container_width=True, key=f"obo_sim_{over}"):
                # Pre-fetch profiles (uses cache after first call)
                prefetch_profiles([bowler_sel],[striker_sel,nonstr_sel],venue)
                vm  = _fetch_venue_mult(venue)
                rng = _np2.random.default_rng(seed=over*7+score)

                # Simulate ONE over
                result = _simulate_once(
                    [bowler_sel],
                    [striker_sel, nonstr_sel, lineup[2] if len(lineup)>2 else striker_sel],
                    start_over=over-1,
                    start_score=score,
                    start_wickets=wickets,
                    venue_mult=vm,
                    rng=rng)

                if result["over_scores"]:
                    od = result["over_scores"][0]
                    # Store in history
                    st.session_state.obo_history.append({
                        "over":    over,
                        "bowler":  bowler_sel,
                        "striker": striker_sel,
                        "runs":    od["runs"],
                        "wickets": od["wickets"],
                        "events":  od["events"],
                        "score_after": od["cumulative_score"],
                        "wkts_after":  od["cumulative_wickets"],
                    })
                    # Update live state
                    st.session_state.obo_score   = od["cumulative_score"]
                    st.session_state.obo_wickets = od["cumulative_wickets"]
                    st.session_state.obo_over    = over + 1
                    # Auto-rotate lineup if wicket
                    if od["wickets"] > 0:
                        new_lineup = list(lineup)
                        for _ in range(od["wickets"]):
                            if len(new_lineup) > 2:
                                new_lineup.pop(0)   # dismissed batsman gone
                        st.session_state.obo_lineup = new_lineup
                    else:
                        # Rotate strike at end of over
                        st.session_state.obo_lineup = [nonstr_sel, striker_sel] + lineup[2:]
                    st.rerun()

        # ── History scorecard ──
        if st.session_state.obo_history:
            st.markdown('<div class="slabel" style="margin-top:16px;">Scorecard</div>', unsafe_allow_html=True)

            def ball_chip(ev):
                out = ev["outcome"]
                BASE = ("display:inline-flex;align-items:center;justify-content:center;"
                        "width:24px;height:24px;border-radius:50%;font-size:11px;"
                        "font-weight:700;margin:1px;flex-shrink:0;")
                chip_styles = {
                    "W":  BASE+"background:#2a0808;color:#f87171;border:1px solid #3d0a0a;",
                    "4":  BASE+"background:#062010;color:#4ade80;border:1px solid #0d2e0a;",
                    "6":  BASE+"background:#0f0a2a;color:#818cf8;border:1px solid #1a1040;",
                    "Wd": BASE+"background:#1a1010;color:#fbbf24;border:1px solid #2a1a0a;",
                }
                lbl = "·" if out in ("dot","0") else out
                st_s = chip_styles.get(out, BASE+"background:#060c18;color:#1a3050;border:1px solid #0a1525;")
                return f'<span style="{st_s}">{lbl}</span>'

            # Build scorecard with 100% inline styles — no CSS class dependency
            rows_html = ""
            for hd in st.session_state.obo_history:
                balls_html = "".join(ball_chip(e) for e in hd["events"])
                rc = "#4ade80" if hd["runs"]>=12 else "#fbbf24" if hd["runs"]>=8 else "#c8daea"
                wkt_badge = (f'<span style="color:#f87171;font-size:11px;margin-left:4px;">✕{hd["wickets"]}</span>'
                             if hd["wickets"] else "")
                rows_html += (
                    '<div style="display:flex;align-items:center;padding:9px 14px;' +
                    'border-bottom:1px solid #050b14;">' +
                    '<div style="width:70px;flex-shrink:0;">' +
                    f'<div style="font-family:Rajdhani,sans-serif;font-weight:700;' +
                    f'color:#38bdf8;font-size:13px;">Over {hd["over"]}</div>' +
                    f'<div style="font-size:9px;color:#1e3a52;">{hd["bowler"].split()[-1]}</div>' +
                    '</div>' +
                    f'<div style="flex:1;display:flex;flex-wrap:wrap;gap:2px;">{balls_html}</div>' +
                    f'<div style="width:52px;text-align:right;font-family:Rajdhani,sans-serif;' +
                    f'font-size:16px;font-weight:700;color:{rc};">{hd["runs"]}{wkt_badge}</div>' +
                    f'<div style="width:62px;text-align:right;font-family:Rajdhani,sans-serif;' +
                    f'font-size:13px;font-weight:700;color:#4a6580;">' +
                    f'{hd["score_after"]}/{hd["wkts_after"]}</div></div>'
                )

            st.markdown(
                '<div style="background:#060c18;border:1px solid #0a1525;' +
                'border-radius:12px;overflow:hidden;">' +
                '<div style="background:#080f1c;padding:7px 14px;display:flex;' +
                'font-size:9px;color:#1e3a52;text-transform:uppercase;letter-spacing:1px;' +
                'border-bottom:1px solid #050b14;">' +
                '<div style="width:70px;">Over</div>' +
                '<div style="flex:1;">Balls</div>' +
                '<div style="width:52px;text-align:right;">Runs</div>' +
                '<div style="width:62px;text-align:right;">Score</div></div>' +
                rows_html + '</div>',
                unsafe_allow_html=True)

        col_reset = st.columns([3,1])[1]
        with col_reset:
            if st.button("🔄 Reset", key="obo_reset_live"):
                for k in list(st.session_state.keys()):
                    if k.startswith("obo_"):
                        del st.session_state[k]
                st.rerun()

with tab7:
    IPL_TEAMS = get_teams()
    get_players_by_team = lambda team, role="batsman": get_squad(team)
    from simulator import run_simulation, compare_plans, win_probability
    import plotly.graph_objects as go

    st.markdown("""
    <style>
    .sim-hero{text-align:center;padding:6px 0 22px;}
    .sim-title{font-family:'Rajdhani',sans-serif;font-size:30px;font-weight:700;
        background:linear-gradient(100deg,#38bdf8 30%,#818cf8 70%,#e879f9 100%);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
    .sim-sub{font-size:12px;color:#1e3a52;margin-top:5px;}

    .sim-section{background:#060c18;border:1px solid #0a1525;border-radius:14px;
        padding:16px 18px 10px;margin-bottom:14px;}
    .sim-sec-label{font-size:10px;font-weight:600;color:#38bdf8;letter-spacing:1.5px;
        text-transform:uppercase;margin-bottom:10px;}

    .over-plan-row{display:flex;align-items:center;gap:10px;
        padding:8px 0;border-bottom:1px solid #080f1c;}
    .over-badge{width:36px;height:36px;border-radius:8px;
        background:linear-gradient(135deg,#0a1828,#070f1c);
        border:1px solid #0e1a2a;display:flex;align-items:center;
        justify-content:center;flex-shrink:0;}
    .over-num{font-family:'Rajdhani',sans-serif;font-size:14px;
        font-weight:700;color:#38bdf8;}

    .sim-result-card{background:linear-gradient(145deg,#0a1828,#07101a);
        border:1px solid #0e1a2a;border-radius:16px;padding:20px;
        text-align:center;position:relative;overflow:hidden;}
    .sim-result-card::before{content:'';position:absolute;top:0;left:0;right:0;
        height:2px;background:linear-gradient(90deg,#0ea5e9,#818cf8,#e879f9);}
    .sim-big{font-family:'Rajdhani',sans-serif;font-size:52px;font-weight:700;
        color:#38bdf8;line-height:1;}
    .sim-lbl{font-size:10px;color:#1e3a52;text-transform:uppercase;
        letter-spacing:1.5px;margin-top:6px;}
    .sim-sub2{font-size:12px;color:#4a6580;margin-top:3px;}

    .scorecard-row{display:flex;align-items:center;padding:9px 14px;
        border-bottom:1px solid #060c18;font-size:13px;}
    .scorecard-row:last-child{border-bottom:none;}
    .scorecard-row:hover{background:rgba(56,189,248,.03);}
    .event-dot{display:inline-block;width:22px;height:22px;border-radius:50%;
        font-size:11px;font-weight:700;line-height:22px;text-align:center;margin:1px;}

    .plan-compare{display:flex;gap:12px;}
    .plan-box{flex:1;background:#060c18;border:1px solid #0a1525;
        border-radius:12px;padding:14px 16px;text-align:center;}
    .plan-score{font-family:'Rajdhani',sans-serif;font-size:36px;
        font-weight:700;line-height:1;}
    .plan-name{font-size:11px;color:#1e3a52;margin-top:4px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="sim-hero">
      <div class="sim-title">🎮 Match Simulator</div>
      <div class="sim-sub">Set your bowling plan · Pick batsmen · Instant simulation across 150 scenarios</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Match Context ──
    st.markdown('<div class="sim-section"><div class="sim-sec-label">⚙ Match Context</div>', unsafe_allow_html=True)
    sc1,sc2,sc3 = st.columns(3)
    with sc1:
        mi_i = IPL_TEAMS.index("Mumbai Indians") if "Mumbai Indians" in IPL_TEAMS else 0
        sim_bat_team = st.selectbox("Batting Team", IPL_TEAMS, key="sbt", index=mi_i)
    with sc2:
        csk_i = IPL_TEAMS.index("Chennai Super Kings") if "Chennai Super Kings" in IPL_TEAMS else 1
        sim_bowl_team = st.selectbox("Bowling Team", IPL_TEAMS, key="sbwlt", index=csk_i)
    with sc3:
        sim_venue = st.selectbox("Venue", ["All Venues"]+venues, key="sv")

    sc4,sc5,sc6,sc7 = st.columns(4)
    with sc4: sim_innings  = st.radio("Innings",[1,2],horizontal=True,format_func=lambda x:"1st" if x==1 else "2nd",key="si")
    with sc5: sim_over     = st.slider("Start From Over",1,20,11,key="so")
    with sc6: sim_score    = st.number_input("Current Score",0,400,105,key="ss")
    with sc7: sim_wickets  = st.number_input("Wickets Fallen",0,9,2,key="sw")

    sim_target = 0
    if sim_innings == 2:
        sim_target = st.number_input("Target",50,400,180,key="st2")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Batting Lineup — only 3 slots ──
    st.markdown('<div class="sim-section"><div class="sim-sec-label">🏏 Batsmen at the Crease</div>', unsafe_allow_html=True)
    bat_pool = get_players_by_team(sim_bat_team,"batsman") or strikers
    overs_left_count = 21 - sim_over

    bc1,bc2,bc3 = st.columns(3)
    # Ensure all three default to different players
    def_0 = 0
    def_1 = min(1, len(bat_pool)-1)
    def_2 = min(2, len(bat_pool)-1)
    with bc1: sim_striker   = st.selectbox("On Strike",      bat_pool, key="sbat_0", index=def_0)
    with bc2:
        # Filter out striker for non-striker choices
        ns_pool = [p for p in bat_pool if p != sim_striker] or bat_pool
        sim_nonstriker = st.selectbox("Non-Striker",    ns_pool,  key="sbat_1", index=0)
    with bc3:
        # Filter out both current batsmen
        next_pool = [p for p in bat_pool if p not in (sim_striker, sim_nonstriker)] or bat_pool
        sim_next   = st.selectbox("Next to Come In",  next_pool, key="sbat_2", index=0)
    sim_batting = [sim_striker, sim_nonstriker, sim_next]
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Bowling Plan — max 4 overs per bowler, no consecutive repeats ──
    bowl_pool = get_players_by_team(sim_bowl_team,"bowler") or bowlers
    n_overs_sim = min(overs_left_count, 20)

    def build_bowl_plan(plan_key_prefix, label_text):
        """Render bowling plan UI with validation hints."""
        st.markdown(f'<div class="sim-section"><div class="sim-sec-label">🎯 {label_text}</div>', unsafe_allow_html=True)
        plan = []
        bowl_counts = {}   # track overs per bowler
        prev_bowler = None

        for row_start in range(0, n_overs_sim, 5):
            row_range = list(range(row_start, min(row_start+5, n_overs_sim)))
            row_cols  = st.columns(len(row_range))
            for col_idx, i in enumerate(row_range):
                over_num = sim_over + i
                phase = "PP" if over_num<=6 else ("Death" if over_num>=16 else "Mid")
                with row_cols[col_idx]:
                    # Build available list: rotate defaults to avoid consecutive
                    avail = bowl_pool
                    # Default suggestion: rotate bowlers to avoid consecutive
                    default_j = (i * 2) % max(len(bowl_pool), 1)
                    b = st.selectbox(
                        f"Over {over_num} · {phase}",
                        avail,
                        key=f"{plan_key_prefix}_{i}",
                        index=min(default_j, len(avail)-1))
                    # Track usage count
                    bowl_counts[b] = bowl_counts.get(b, 0) + 1
                    plan.append(b)
                    prev_bowler = b

        # Validation warnings
        warnings_list = []
        bc2 = {}
        for idx, bw in enumerate(plan):
            bc2[bw] = bc2.get(bw, 0) + 1
            if bc2[bw] > 4:
                warnings_list.append(f"⚠️ {bw} has more than 4 overs")
            if idx > 0 and plan[idx-1] == bw:
                warnings_list.append(f"⚠️ {bw} bowling consecutive overs {sim_over+idx}–{sim_over+idx+1}")
        for w in list(dict.fromkeys(warnings_list))[:3]:   # show max 3 unique
            st.warning(w)

        st.markdown('</div>', unsafe_allow_html=True)
        return plan

    plan_a_bowlers = build_bowl_plan("pa", "Bowling Plan A")

    show_b = st.toggle("⚡ Compare with Plan B", value=False, key="show_planb")
    plan_b_bowlers = []
    if show_b:
        plan_b_bowlers = build_bowl_plan("pb", "Bowling Plan B (Alternative)")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Session state keys for instant results
    if "sim_res_a"  not in st.session_state: st.session_state.sim_res_a  = None
    if "sim_res_b"  not in st.session_state: st.session_state.sim_res_b  = None
    if "sim_ran"    not in st.session_state: st.session_state.sim_ran    = False

    run_sim = st.button("▶  Simulate", type="primary",
                        use_container_width=True, key="runsim")

    if run_sim:
        import time as _time
        _t0 = _time.time()
        _status = st.empty()
        _status.markdown('''
        <div style="background:rgba(14,165,233,0.08);border:1px solid rgba(14,165,233,0.2);
            border-radius:10px;padding:12px 18px;text-align:center;margin:8px 0;">
          <div style="font-family:Rajdhani,sans-serif;font-size:15px;font-weight:700;
              color:#38bdf8;letter-spacing:1px;">
            ⚡ Running 150 simulations…
          </div>
          <div style="font-size:11px;color:#1e3a52;margin-top:4px;">
            Computing over-by-over outcomes for every scenario
          </div>
        </div>''', unsafe_allow_html=True)

        st.session_state.sim_res_a = run_simulation(
            plan_a_bowlers, sim_batting,
            start_over=sim_over-1, start_score=int(sim_score),
            start_wickets=int(sim_wickets), venue=sim_venue,
            label="Plan A", n_sims=150)
        st.session_state.sim_res_b = run_simulation(
            plan_b_bowlers, sim_batting,
            start_over=sim_over-1, start_score=int(sim_score),
            start_wickets=int(sim_wickets), venue=sim_venue,
            label="Plan B", n_sims=150) if show_b and plan_b_bowlers else None
        st.session_state.sim_ran = True

        _elapsed = round(_time.time() - _t0, 1)
        _status.markdown(f'''
        <div style="background:rgba(74,222,128,0.07);border:1px solid rgba(74,222,128,0.2);
            border-radius:10px;padding:10px 18px;text-align:center;margin:8px 0;">
          <div style="font-family:Rajdhani,sans-serif;font-size:14px;font-weight:700;
              color:#4ade80;letter-spacing:1px;">
            ✓ Simulation complete in {_elapsed}s
          </div>
        </div>''', unsafe_allow_html=True)

    # Always render results if they exist — instant on every rerun
    if st.session_state.sim_ran and st.session_state.sim_res_a:
        res_a = st.session_state.sim_res_a
        res_b = st.session_state.sim_res_b

        st.divider()

        # ── Comparison banner ──
        if res_b:
            cmp = compare_plans(res_a, res_b)
            diff = cmp["diff_median"]
            winner  = "Plan B" if diff > 0 else ("Plan A" if diff < 0 else "Equal")
            w_color = "#f87171" if diff > 0 else "#4ade80" if diff < 0 else "#fbbf24"
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0a1828,#07101a);
                border:1px solid rgba(56,189,248,.1);border-radius:16px;
                padding:18px 22px;margin-bottom:20px;text-align:center;">
              <div style="font-size:11px;color:#1e3a52;letter-spacing:2px;
                  text-transform:uppercase;margin-bottom:8px;">COMPARISON RESULT</div>
              <div style="font-family:'Rajdhani',sans-serif;font-size:28px;
                  font-weight:700;color:{w_color};">
                {winner} scores {abs(diff)} runs {"more" if diff>0 else "fewer"}
              </div>
              <div style="font-size:12px;color:#4a6580;margin-top:4px;">
                {cmp["b_better_pct"]}% of simulations favour Plan B ·
                {cmp["a_better_pct"]}% favour Plan A
              </div>
            </div>""", unsafe_allow_html=True)

        # ── Score result cards ──
        col_results = st.columns(2 if res_b else 1)
        for idx, (res, col) in enumerate(zip(
            [r for r in [res_a, res_b] if r], col_results)):
            wp = win_probability(res, sim_target) if sim_innings==2 and sim_target else None
            with col:
                wc = "#4ade80" if (wp or 0)>=50 else "#f87171"
                st.markdown(f"""
                <div class="sim-result-card">
                  <div style="font-size:10px;color:#38bdf8;letter-spacing:2px;
                      text-transform:uppercase;margin-bottom:8px;">{res["label"]}</div>
                  <div class="sim-big">{res["predicted"]}</div>
                  <div class="sim-lbl">Predicted Final Score</div>
                  <div class="sim-sub2">Range: {res["p25"]}–{res["p75"]} · Best case: {res["p90"]}</div>
                  {f'<div style="margin-top:12px;font-family:Rajdhani,sans-serif;font-size:22px;font-weight:700;color:{wc};">{wp}% Win Chance</div>' if wp is not None else ""}
                </div>""", unsafe_allow_html=True)

        # ── Chart + Scorecard side by side ──
        st.markdown("<br>", unsafe_allow_html=True)

        def ball_dot(ev):
            out = ev["outcome"]
            if out == "W":
                return '<span class="event-dot" style="background:#2a0808;color:#f87171;border:1px solid #3d0a0a;">W</span>'
            elif out == "4":
                return '<span class="event-dot" style="background:#062010;color:#4ade80;border:1px solid #0d2e0a;">4</span>'
            elif out == "6":
                return '<span class="event-dot" style="background:#0f0a2a;color:#818cf8;border:1px solid #1a1040;">6</span>'
            elif out == "Wd":
                return '<span class="event-dot" style="background:#1a1010;color:#fbbf24;border:1px solid #2a1a0a;">Wd</span>'
            elif out in ("dot","0"):
                return '<span class="event-dot" style="background:#060c18;color:#1a3050;border:1px solid #0a1525;">·</span>'
            return f'<span class="event-dot" style="background:#0a1828;color:#90b4ce;border:1px solid #0e1a2a;">{out}</span>'

        def make_scorecard_html(res):
            rows = ""
            for od in res["rep_innings"]:
                balls_html = "".join(ball_dot(e) for e in od["events"])
                wkt  = f'<span style="color:#f87171;font-size:11px;margin-left:4px;">✕{od["wickets"]}</span>' if od["wickets"] else ""
                rc   = "#4ade80" if od["runs"]>=12 else "#fbbf24" if od["runs"]>=8 else "#c8daea"
                rows += (
                    '<div style="display:flex;align-items:center;padding:8px 12px;' +
                    'border-bottom:1px solid #050b14;">' +
                    '<div style="width:68px;flex-shrink:0;">' +
                    f'<div style="font-family:Rajdhani,sans-serif;font-weight:700;color:#38bdf8;font-size:13px;">Over {od["over"]}</div>' +
                    f'<div style="font-size:9px;color:#1e3a52;">{od["bowler"].split()[-1]}</div></div>' +
                    f'<div style="flex:1;display:flex;flex-wrap:wrap;gap:1px;">{balls_html}</div>' +
                    '<div style="width:52px;text-align:right;flex-shrink:0;">' +
                    f'<span style="font-family:Rajdhani,sans-serif;font-size:16px;font-weight:700;color:{rc};">{od["runs"]}</span>{wkt}</div>' +
                    '<div style="width:60px;text-align:right;flex-shrink:0;padding-left:6px;' +
                    f'font-family:Rajdhani,sans-serif;font-size:13px;font-weight:700;color:#4a6580;">{od["cumulative_score"]}/{od["cumulative_wickets"]}</div></div>'
                )
            final = res["rep_innings"][-1]
            rows += (
                '<div style="padding:9px 12px;background:#080f1c;' +
                'display:flex;justify-content:space-between;align-items:center;">' +
                f'<div style="font-size:10px;color:#1e3a52;">{res["label"]}</div>' +
                f'<div style="font-family:Rajdhani,sans-serif;font-size:17px;font-weight:700;color:#38bdf8;">{final["cumulative_score"]}/{final["cumulative_wickets"]}</div></div>'
            )
            return (
                '<div style="background:#060c18;border:1px solid #0a1525;border-radius:12px;overflow:hidden;">' +
                '<div style="background:#080f1c;padding:7px 12px;display:flex;font-size:9px;color:#1e3a52;' +
                'text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #050b14;">' +
                '<div style="width:68px;">Over</div><div style="flex:1;">Balls</div>' +
                '<div style="width:52px;text-align:right;">Runs</div>' +
                '<div style="width:60px;text-align:right;">Score</div></div>' +
                rows + '</div>'
            )

        chart_col, sc_col = st.columns([3, 2])

        with chart_col:
            st.markdown('<div class="slabel" style="margin-top:0;">Score Trajectory</div>', unsafe_allow_html=True)
            fig_traj = go.Figure()
            overs_x  = res_a["overs"]
            clr_a = {"band":"rgba(56,189,248,0.07)","line":"#38bdf8","fill":"rgba(56,189,248,0.13)"}
            clr_b = {"band":"rgba(129,140,248,0.07)","line":"#818cf8","fill":"rgba(129,140,248,0.13)"}
            for res_i, clrs in [(r,c) for r,c in [(res_a,clr_a),(res_b,clr_b)] if r]:
                fig_traj.add_trace(go.Scatter(
                    x=overs_x+overs_x[::-1],
                    y=res_i["over_p90"]+res_i["over_p10"][::-1],
                    fill="toself",fillcolor=clrs["band"],line=dict(width=0),
                    showlegend=False,hoverinfo="skip"))
                fig_traj.add_trace(go.Scatter(
                    x=overs_x+overs_x[::-1],
                    y=res_i["over_p75"]+res_i["over_p25"][::-1],
                    fill="toself",fillcolor=clrs["fill"],line=dict(width=0),
                    showlegend=False,hoverinfo="skip"))
                fig_traj.add_trace(go.Scatter(
                    x=overs_x, y=res_i["over_p50"], mode="lines+markers",
                    name=f"{res_i['label']} ({res_i['predicted']})",
                    line=dict(color=clrs["line"],width=2.5),
                    marker=dict(size=5,color=clrs["line"]),
                    hovertemplate="Over %{x}<br><b>%{y}</b><extra>"+res_i["label"]+"</extra>"))
            for od in res_a["rep_innings"]:
                if od["wickets"] > 0:
                    fig_traj.add_annotation(
                        x=od["over"], y=od["cumulative_score"]+4,
                        text="W", showarrow=False,
                        font=dict(color="#f87171",size=10,family="Rajdhani"),
                        bgcolor="rgba(248,113,113,0.12)",
                        bordercolor="rgba(248,113,113,0.3)",borderwidth=1)
            if sim_innings==2 and sim_target:
                fig_traj.add_hline(y=sim_target, line_color="#fbbf24",
                    line_dash="dash", line_width=1.5,
                    annotation_text=f"Target {sim_target}",
                    annotation_font_color="#fbbf24",
                    annotation_position="top right")
            fig_traj.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter",color="#90b4ce",size=12),
                margin=dict(l=10,r=10,t=28,b=30),
                xaxis=dict(**AX,title="Over",tickvals=overs_x,tickfont=dict(size=10)),
                yaxis=dict(**AX,title="Score"),
                height=440,
                legend=dict(orientation="h",y=1.04,bgcolor="rgba(0,0,0,0)",font=dict(size=11)),
                hovermode="x unified")
            st.plotly_chart(fig_traj, use_container_width=True)

        with sc_col:
            st.markdown('<div class="slabel" style="margin-top:0;">Ball-by-Ball Breakdown</div>', unsafe_allow_html=True)
            if res_b:
                sc_tab_a, sc_tab_b = st.tabs(["Plan A","Plan B"])
                sc_tab_a.markdown(make_scorecard_html(res_a), unsafe_allow_html=True)
                sc_tab_b.markdown(make_scorecard_html(res_b), unsafe_allow_html=True)
            else:
                st.markdown(make_scorecard_html(res_a), unsafe_allow_html=True)

        # ── AI Bowling Recommendation ──
        st.markdown("<br>", unsafe_allow_html=True)
        if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            plan_summary = ", ".join([f"Over {sim_over+i}: {b}" for i,b in enumerate(plan_a_bowlers)])
            cmp_line = ""
            if res_b:
                cmp2 = compare_plans(res_a, res_b)
                cmp_line = f"Plan B scores {abs(cmp2['diff_median'])} runs {'more' if cmp2['diff_median']>0 else 'fewer'} than Plan A ({cmp2['b_better_pct']}% of simulations)"
            prompt = f"""You are an IPL tactical analyst. Give 2-3 sharp insights from these simulation results.
Focus on bowling strategy — which bowler worked best, what risks the plan takes.

Match: {sim_bat_team} batting vs {sim_bowl_team} | Over {sim_over} | {int(sim_score)}/{int(sim_wickets)}
{"Chasing " + str(sim_target) if sim_innings==2 else "1st innings"}
Bowling Plan: {plan_summary}
Simulation result: {res_a["predicted"]} predicted ({res_a["p25"]}–{res_a["p75"]} range)
{cmp_line}

End with one clear recommendation: which bowler to use in the most critical over."""
            try:
                from agent import run_agent
                import re as _re3
                ai_reply,_ = run_agent(prompt,[],GEMINI_API_KEY,provider="gemini")
                ai_html = _re3.sub(r'\*\*(.*?)\*\*', r'<strong style="color:#f0f8ff;">\1</strong>', ai_reply)
                ai_html = ai_html.replace('\n','<br>')
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#080f1c,#060c16);
                    border:1px solid rgba(56,189,248,.1);border-radius:16px;
                    padding:20px 22px;position:relative;">
                  <div style="position:absolute;top:0;left:0;right:0;height:2px;
                      background:linear-gradient(90deg,#0ea5e9,#818cf8,#e879f9);
                      border-radius:16px 16px 0 0;"></div>
                  <div style="font-family:'Rajdhani',sans-serif;font-size:10px;color:#818cf8;
                      letter-spacing:2px;text-transform:uppercase;margin-bottom:10px;">
                    🤖 AI Strategy Analysis
                  </div>
                  <div style="font-size:13px;color:#c8daea;line-height:1.75;">{ai_html}</div>
                </div>""", unsafe_allow_html=True)
            except Exception as e:
                st.warning(f"AI analysis unavailable: {e}")

# FLOATING CHAT
# ══════════════════════════════════════════════════════════════════════════════
_chat_q = st.query_params.get("chat_q","")
if _chat_q and _chat_q != st.session_state.get("_last_q",""):
    st.session_state._last_q = _chat_q
    st.query_params.clear()
    st.session_state.chat_history.append({"role":"user","content":_chat_q})
    with st.spinner(""):
        try:
            from agent import run_agent
            reply,updated = run_agent(_chat_q,st.session_state.msg_history,GEMINI_API_KEY,provider="gemini")
            st.session_state.msg_history = updated
            st.session_state.chat_history.append({"role":"assistant","content":reply})
        except Exception as e:
            st.session_state.chat_history.append({"role":"assistant","content":f"❌ {e}"})

_hist = json.dumps(st.session_state.chat_history)

st.markdown(f"""
<style>
#fab{{position:fixed;bottom:26px;right:26px;z-index:99999;width:52px;height:52px;border-radius:50%;
    border:none;outline:none;cursor:pointer;background:linear-gradient(135deg,#0ea5e9,#6366f1);
    font-size:21px;color:#fff;display:flex;align-items:center;justify-content:center;
    animation:fp 3s ease-in-out infinite;transition:transform .2s;}}
#fab:hover{{transform:scale(1.1);}}
@keyframes fp{{0%,100%{{box-shadow:0 0 0 0 rgba(56,189,248,.35),0 4px 14px rgba(56,189,248,.2);}}
               50%{{box-shadow:0 0 0 9px rgba(56,189,248,0),0 4px 22px rgba(56,189,248,.4);}}}}
#cpanel{{position:fixed;bottom:88px;right:26px;z-index:99998;width:390px;height:560px;
    display:flex;flex-direction:column;overflow:hidden;
    background:#050a14;border:1px solid rgba(56,189,248,.1);border-radius:18px;
    box-shadow:0 20px 60px rgba(0,0,0,.85);transition:opacity .2s,transform .2s;}}
#cpanel.hidden{{opacity:0;pointer-events:none;transform:translateY(12px) scale(0.98);}}
#chead{{flex-shrink:0;padding:13px 15px 11px;background:linear-gradient(135deg,#0a1520,#091320);
    border-bottom:1px solid rgba(56,189,248,.07);display:flex;align-items:center;gap:10px;}}
#cavt{{width:32px;height:32px;border-radius:50%;flex-shrink:0;
    background:linear-gradient(135deg,#0ea5e9,#6366f1);
    display:flex;align-items:center;justify-content:center;font-size:14px;}}
#cname{{font-family:Rajdhani,sans-serif;font-weight:700;font-size:13px;color:#f0f8ff;}}
#cstat{{font-size:10px;color:#1e3a52;margin-top:1px;}}
#cstat span{{color:#4ade80;}}
#cclose{{margin-left:auto;width:24px;height:24px;border-radius:6px;border:none;cursor:pointer;
    background:rgba(255,255,255,.04);color:#4a6580;font-size:12px;
    display:flex;align-items:center;justify-content:center;}}
#cclose:hover{{background:rgba(255,255,255,.09);}}
#cmsgs{{flex:1;overflow-y:auto;padding:12px 11px 5px;display:flex;flex-direction:column;gap:7px;scroll-behavior:smooth;}}
#cmsgs::-webkit-scrollbar{{width:3px;}}
#cmsgs::-webkit-scrollbar-thumb{{background:rgba(56,189,248,.12);border-radius:3px;}}
.fw{{background:rgba(14,165,233,.04);border:1px solid rgba(14,165,233,.09);border-radius:11px;
    padding:11px 13px;font-size:12px;color:#1e3a52;line-height:1.7;}}
.fw strong{{color:#38bdf8;font-size:12px;}}
.chips{{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px;}}
.chip{{background:rgba(14,165,233,.06);border:1px solid rgba(14,165,233,.13);color:#38bdf8;
    border-radius:20px;padding:3px 10px;font-size:11px;cursor:pointer;white-space:nowrap;user-select:none;}}
.chip:hover{{background:rgba(14,165,233,.16);}}
.fmu{{align-self:flex-end;max-width:85%;background:linear-gradient(135deg,#0ea5e9,#2563eb);
    color:#fff;border-radius:13px 13px 4px 13px;padding:8px 12px;font-size:13px;line-height:1.5;word-break:break-word;}}
.fmb{{align-self:flex-start;max-width:93%;background:#090f1e;border:1px solid rgba(56,189,248,.07);
    color:#c8daea;border-radius:13px 13px 13px 4px;padding:10px 12px;font-size:13px;line-height:1.65;word-break:break-word;}}
.fmb strong{{color:#38bdf8;}}
.dot-wrap{{align-self:flex-start;padding:9px 12px;background:#090f1e;border:1px solid rgba(56,189,248,.07);
    border-radius:13px 13px 13px 4px;display:flex;gap:4px;align-items:center;}}
.dot{{width:6px;height:6px;border-radius:50%;background:#38bdf8;opacity:.4;animation:db 1.2s ease-in-out infinite;}}
.dot:nth-child(2){{animation-delay:.2s;}}.dot:nth-child(3){{animation-delay:.4s;}}
@keyframes db{{0%,60%,100%{{transform:translateY(0);opacity:.4;}}30%{{transform:translateY(-5px);opacity:1;}}}}
#cinput{{flex-shrink:0;padding:9px 11px;border-top:1px solid rgba(56,189,248,.06);
    background:#03060e;display:flex;gap:6px;align-items:flex-end;}}
#ctxt{{flex:1;background:#090f1e;border:1px solid rgba(56,189,248,.1);border-radius:9px;
    color:#c8daea;padding:8px 11px;font-size:13px;outline:none;resize:none;
    line-height:1.45;font-family:'Inter',sans-serif;max-height:88px;transition:border-color .15s;}}
#ctxt::placeholder{{color:#152235;}}
#ctxt:focus{{border-color:rgba(14,165,233,.3);}}
#csend{{width:36px;height:36px;border-radius:9px;border:none;cursor:pointer;flex-shrink:0;
    background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;font-size:15px;
    display:flex;align-items:center;justify-content:center;transition:opacity .15s;}}
#csend:hover:not(:disabled){{opacity:.82;}}
#csend:disabled{{opacity:.28;cursor:not-allowed;}}
</style>

<button id="fab" title="AI Analyst">🏏</button>

<div id="cpanel" class="hidden">
  <div id="chead">
    <div id="cavt">🤖</div>
    <div><div id="cname">IPL AI Analyst</div>
         <div id="cstat"><span>●</span> Gemini 2.5 · Live Data</div></div>
    <button id="cclose">✕</button>
  </div>
  <div id="cmsgs">
    <div class="fw" id="welcome">
      <strong>Ask me anything about IPL 🏏</strong><br>
      Real ball-by-ball data · Tactical insights
      <div class="chips">
        <span class="chip" onclick="fc('Kohli vs Malinga career stats')">Kohli vs Malinga</span>
        <span class="chip" onclick="fc('Top 5 wicket takers 2023')">Top wickets 2023</span>
        <span class="chip" onclick="fc('MI vs CSK all time record')">MI vs CSK</span>
        <span class="chip" onclick="fc('Best economy bowlers ever')">Best economy</span>
        <span class="chip" onclick="fc('Dhoni batting career stats')">Dhoni stats</span>
        <span class="chip" onclick="fc('Best batsmen at Wankhede')">Wankhede</span>
      </div>
    </div>
  </div>
  <div id="cinput">
    <textarea id="ctxt" rows="1" placeholder="Ask about any player, team or stat…"></textarea>
    <button id="csend">➤</button>
  </div>
</div>

<script>
var __h={_hist};
(function(){{
  var fab=document.getElementById('fab'),panel=document.getElementById('cpanel'),
      cl=document.getElementById('cclose'),msgs=document.getElementById('cmsgs'),
      inp=document.getElementById('ctxt'),send=document.getElementById('csend');
  function sb(){{msgs.scrollTop=msgs.scrollHeight;}}
  window.fc=function(t){{inp.value=t;inp.focus();ar();}}
  fab.addEventListener('click',function(){{
    panel.classList.toggle('hidden');
    if(!panel.classList.contains('hidden')){{setTimeout(function(){{inp.focus();sb();}},80);}}
  }});
  cl.addEventListener('click',function(){{panel.classList.add('hidden');}});
  function ar(){{inp.style.height='auto';inp.style.height=Math.min(inp.scrollHeight,88)+'px';}}
  inp.addEventListener('input',ar);
  inp.addEventListener('keydown',function(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();go();}}}} );
  send.addEventListener('click',go);
  function safe(t){{
    return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/[*][*](.*?)[*][*]/g,'<strong>$1</strong>').replace(/\n/g,'<br>');
  }}
  function addMsg(t,role){{
    var d=document.createElement('div');
    if(role==='user'){{
      d.style.cssText='align-self:flex-end;max-width:85%;background:linear-gradient(135deg,#0ea5e9,#2563eb);color:#fff;border-radius:14px 14px 4px 14px;padding:9px 13px;font-size:13px;line-height:1.5;word-break:break-word;margin:2px 0;';
    }}else{{
      d.style.cssText='align-self:flex-start;max-width:93%;background:#090f1e;border:1px solid rgba(56,189,248,.07);color:#c8daea;border-radius:14px 14px 14px 4px;padding:10px 13px;font-size:13px;line-height:1.65;word-break:break-word;margin:2px 0;';
    }}
    d.innerHTML=safe(t);msgs.appendChild(d);sb();
  }}
  function showDots(){{
    var d=document.createElement('div');d.id='dots';
    d.style.cssText='align-self:flex-start;padding:10px 13px;background:#090f1e;border:1px solid rgba(56,189,248,.07);border-radius:14px 14px 14px 4px;display:flex;gap:4px;align-items:center;margin:2px 0;';
    d.innerHTML='<div style="width:6px;height:6px;border-radius:50%;background:#38bdf8;opacity:.4;animation:db 1.2s ease-in-out infinite;"></div><div style="width:6px;height:6px;border-radius:50%;background:#38bdf8;opacity:.4;animation:db 1.2s .2s ease-in-out infinite;"></div><div style="width:6px;height:6px;border-radius:50%;background:#38bdf8;opacity:.4;animation:db 1.2s .4s ease-in-out infinite;"></div>';
    msgs.appendChild(d);sb();
  }}
  function hideDots(){{var d=document.getElementById('dots');if(d)d.remove();}}
  function go(){{
    var t=inp.value.trim();if(!t)return;
    var w=document.getElementById('welcome');if(w)w.style.display='none';
    addMsg(t,'user');inp.value='';inp.style.height='auto';
    send.disabled=true;showDots();
    var url=new URL(window.location.href);
    url.searchParams.set('chat_q',t);window.location.href=url.toString();
  }}
  if(__h&&__h.length){{
    var w=document.getElementById('welcome');if(w)w.style.display='none';
    hideDots();
    __h.forEach(function(m){{addMsg(m.content,m.role==='user'?'user':'bot');}});
    panel.classList.remove('hidden');send.disabled=false;sb();
  }}
}})();
</script>
""", unsafe_allow_html=True)