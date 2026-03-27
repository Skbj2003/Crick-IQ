**A full-stack IPL cricket analytics platform powered by real ball-by-ball data, ML models, and AI.**



---

## Overview

CricIQ turns 278,000+ real IPL ball-by-ball deliveries into actionable tactical insights. It combines classical statistical analysis with modern ML models and an AI chat interface.

---

## Features

| Module | Description |
|---|---|
| **Head-to-Head** | Batsman vs bowler matchup with 7 metrics and tactical verdict |
| **Leaderboards** | Runs, wickets, SR, economy — filterable by season |
| **Form Tracker** | Match-by-match rolling averages with streak detection |
| **Bowler Phases** | Economy and wickets across Powerplay / Middle / Death |
| **Phase Scoring** | Batsman SR and boundary% by phase with radar chart |
| **Match Predictor** | Gradient Boosting score prediction from live match state |
| **Simulator** | Over-by-over Monte Carlo simulation — 200 scenarios |


---

## Architecture

```
criciq/
├── app.py                  # Streamlit frontend 
├── analytics.py            # Phase, form, and bowler analysis queries
├── predictor.py            # Gradient Boosting score prediction
├── simulator.py            # Monte Carlo match simulation engine
├── local_ai.py             # AI: Ollama → Gemini → rule-based NLP
├── agent.py                # Gemini tool-use agent with 6 DB tools
├── squad_fetcher.py        # Live 2026 IPL squads (Cricinfo)
├── setup_db.py             # Build DuckDB from Cricsheet YAML files
├── fetch_squad_images.py   # Download player headshots
└── build_player_images.py  # Build player → Cricinfo ID mapping
```

---

## ML Models

| Model | Task | Algorithm |
|---|---|---|
| Score Predictor | Final score from live match state | Gradient Boosting Regressor |
| Ball Outcome | Simulate each delivery outcome | Blended player profile sampling |
| Monte Carlo | Score distribution across N simulations | Probabilistic sampling |

**Prediction features:** over, cumulative score, wickets, run rate, balls remaining, venue average, phase

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit · Plotly · Custom CSS |
| Database | DuckDB — sub-second analytical queries |
| ML | Scikit-learn — GBR, Monte Carlo |
| AI | Ollama ·  Rule-based NLP |
| Data | Cricsheet open cricket dataset |

---
