"""
squad_fetcher.py
────────────────
Fetches current IPL squad data from ESPN Cricinfo.
Falls back to hardcoded 2026 squads if network unavailable.

Usage:
    from squad_fetcher import get_squad, get_all_squads
    players = get_squad("Mumbai Indians")
"""

import json
import os
import time
import urllib.request
from pathlib import Path

# Cache file — squads saved locally so we don't re-fetch every run
CACHE_FILE = "squad_cache.json"
CACHE_TTL  = 86400 * 3   # refresh every 3 days

# ─────────────────────────────────────────────────────────────────────────────
# HARDCODED 2026 SQUADS  (fallback — always works)
# ─────────────────────────────────────────────────────────────────────────────
_SQUADS_2026 = {
    "Chennai Super Kings": [
        "RD Gaikwad","MS Dhoni","SV Samson","D Brevis","A Mhatre",
        "Kartik Sharma","Sarfaraz Khan","Urvil Patel","A Kamboj",
        "J Overton","Ramakrishna Ghosh","Prashant Veer","M Short",
        "Aman Khan","Zak Foulkes","Shivam Dube","Khaleel Ahmed",
        "Noor Ahmad","Mukesh Choudhary","S Gopal","Gurjapneet Singh",
        "Akeal Hosein","M Henry","Rahul Chahar",
    ],
    "Mumbai Indians": [
        "HH Pandya","RG Sharma","Suryakumar Yadav","R Minz",
        "S Rutherford","RJ Rickelton","Q de Kock","D Malewar",
        "Tilak Varma","N Dhir","MJ Santner","RA Bawa",
        "A Ankolekar","M Rawat","C Bosch","WG Jacks",
        "ST Thakur","JJ Bumrah","T Boult","DL Chahar",
        "M Markande","Ashwani Kumar","M Izhar","Raghu Sharma",
    ],
    "Royal Challengers Bangalore": [
        "RR Patidar","V Kohli","Devdutt Padikkal","PD Salt",
        "JR Sharma","JM Cox","KH Pandya","TH David",
        "R Shepherd","J Bethell","V Iyer","Satvik Deswal",
        "M Yadav","V Ostwal","Vihaan Malhotra","Kanishk Chouhan",
        "Yash Dayal","Swapnil Singh",
    ],
    "Delhi Capitals": [
        "KL Rahul","Axar Patel","Kuldeep Yadav","S Rizvi",
        "A Porel","Vipraj Nigam","T Stubbs","MA Starc",
        "Mukesh Kumar","Tripurana Vijay","T Natarajan",
        "MR Marsh","Faf du Plessis","HV Patel","Mohit Sharma",
    ],
    "Gujarat Titans": [
        "Shubman Gill","Rashid Khan","DA Miller","MS Wade",
        "B Sai Sudharsan","Shahrukh Khan","R Tewatia","Noor Ahmad",
        "Sai Kishore","Spencer Johnson","Umesh Yadav",
        "Gerald Coetzee","Kagiso Rabada","Mohammed Siraj",
    ],
    "Kolkata Knight Riders": [
        "AM Rahane","SP Narine","A Russell","Rinku Singh",
        "Varun Chakravarthy","Cameron Green","Matheesha Pathirana",
        "Phil Salt","Angkrish Raghuvanshi","Suyash Sharma",
        "Harshit Rana","Ramandeep Singh","Moeen Ali",
        "Anrich Nortje","Rovman Powell",
    ],
    "Lucknow Super Giants": [
        "N Pooran","Ravi Bishnoi","Avesh Khan","M Stoinis",
        "Mohsin Khan","Prerak Mankad","Ayush Badoni",
        "Mitchell Marsh","Matt Henry","Digvijay Deshmukh",
        "Akash Deep","Abdul Samad","David Miller",
    ],
    "Rajasthan Royals": [
        "YBK Jaiswal","R Parag","JC Buttler","SO Hetmyer",
        "Donovan Ferreira","Sam Curran","JC Archer","YS Chahal",
        "Sandeep Sharma","KM Asif","Dhruv Jurel",
        "Maheesh Theekshana","Shimron Hetmyer","Wanindu Hasaranga",
    ],
    "Punjab Kings": [
        "SS Iyer","M Stoinis","Arshdeep Singh","YS Chahal",
        "JM Bairstow","Liam Livingstone","Harshal Patel",
        "Nathan Ellis","Harpreet Brar","Prabhsimran Singh",
        "Shashank Singh","Azmatullah Omarzai","Glenn Maxwell",
        "Marco Jansen","Lockie Ferguson",
    ],
    "Sunrisers Hyderabad": [
        "I Kishan","PJ Cummins","Abhishek Sharma","HH Klaasen",
        "Aiden Markram","Travis Head","Washington Sundar",
        "T Natarajan","Marco Jansen","Nitish Kumar Reddy",
        "Glenn Phillips","Jaydev Unadkat","Fazalhaq Farooqi",
        "Adam Zampa","Zeeshan Ansari",
    ],
}

IPL_TEAMS = sorted(_SQUADS_2026.keys())


# ─────────────────────────────────────────────────────────────────────────────
# CACHE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    try:
        if Path(CACHE_FILE).exists():
            data = json.loads(Path(CACHE_FILE).read_text())
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return data.get("squads", {})
    except Exception:
        pass
    return {}


def _save_cache(squads: dict):
    try:
        Path(CACHE_FILE).write_text(json.dumps({"ts": time.time(), "squads": squads}))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# LIVE FETCH  (ESPN Cricinfo IPL 2026 squad pages)
# ─────────────────────────────────────────────────────────────────────────────
# Team ID map for Cricinfo series (IPL 2026 = series 1449924 tentatively)
# These are the team IDs used in Cricinfo's squad endpoint
_CRICINFO_TEAM_IDS = {
    "Chennai Super Kings":       2,
    "Mumbai Indians":            4,
    "Royal Challengers Bangalore": 4340,
    "Kolkata Knight Riders":     305,
    "Delhi Capitals":            1,
    "Rajasthan Royals":          3,
    "Punjab Kings":              11,
    "Sunrisers Hyderabad":       6,
    "Gujarat Titans":            7966,
    "Lucknow Super Giants":      8048,
}

def _fetch_cricinfo_squad(team_name: str) -> list[str]:
    """Try to fetch squad from Cricinfo. Returns list of player names or []."""
    # Use a simpler public endpoint — Cricinfo players API
    team_id = _CRICINFO_TEAM_IDS.get(team_name)
    if not team_id:
        return []
    try:
        url = f"https://hs-consumer-api.espncricinfo.com/v1/pages/team/squad?teamId={team_id}&type=tournament"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        players = []
        for p in data.get("players", []):
            name = p.get("displayName") or p.get("longDisplayName", "")
            if name:
                players.append(name)
        return players
    except Exception:
        return []


def refresh_squads() -> dict:
    """
    Try to fetch live squads. On any failure, return hardcoded 2026 data.
    Results cached for 3 days.
    """
    # Check cache first
    cached = _load_cache()
    if cached:
        return cached

    # Try live fetch
    live = {}
    for team in _SQUADS_2026:
        fetched = _fetch_cricinfo_squad(team)
        live[team] = fetched if len(fetched) >= 10 else _SQUADS_2026[team]

    if any(len(v) >= 10 for v in live.values()):
        _save_cache(live)
        return live

    # Fall back to hardcoded
    return _SQUADS_2026


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
_LOADED_SQUADS: dict = {}

def get_all_squads() -> dict:
    """Return all squad data (cached in memory)."""
    global _LOADED_SQUADS
    if not _LOADED_SQUADS:
        _LOADED_SQUADS = refresh_squads()
    return _LOADED_SQUADS


def get_squad(team: str) -> list[str]:
    """Return sorted player list for a team."""
    squads = get_all_squads()
    # Try exact match first, then partial
    squad = squads.get(team, [])
    if not squad:
        for k, v in squads.items():
            if team.lower() in k.lower() or k.lower() in team.lower():
                squad = v
                break
    return sorted(squad) if squad else sorted(_SQUADS_2026.get(team, []))


def get_teams() -> list[str]:
    """Return sorted list of all IPL team names."""
    return sorted(get_all_squads().keys())