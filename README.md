# 🏠 Perth Rental Finder

An AI-powered rental search tool for Perth, Western Australia — built as a portfolio project using real government bond data and large language models.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green) ![Claude API](https://img.shields.io/badge/Claude-API-orange) ![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What It Does

Perth Rental Finder helps renters find the right suburb based on their budget and lifestyle priorities. It uses **470,254 real WA government bond records** to surface honest, data-driven insights rather than marketing copy.

**Key features:**
- Conversational questionnaire — budget → area → amenity priorities → results
- Region-aware filtering (north/south/east Perth enforced in results)
- Ascending rent sort — cheapest matching suburbs shown first
- Conversation persistence — chat history saved across browser sessions
- 7 renter calculators: affordability, sharehouse split, moving costs, lease break, rent scenario planner, WA renter checklist, suburb insights
- Free-form chat after search — compare suburbs, deep dive, property advisor
- Dark mode, mobile-responsive, no login required

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pandas |
| Frontend | Vanilla JS, Chart.js, CSS custom properties |
| AI | Claude API (Anthropic) |
| Data | WA Government Bond Records (470K+ records) |
| Hosting | Local / any Python-compatible server |

---

## Project Background

This was built as a capstone portfolio project across two Ed Donner courses:

- [LLM Engineering](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) — RAG, fine-tuning, Claude API
- [Agentic AI Engineering](https://www.udemy.com/course/agentic-ai-engineering/) — multi-agent systems, CrewAI, LangGraph, MCP

The goal was to build something real and useful using the skills from both courses — not a toy demo.

---

## How to Run

**1. Clone the repo**
```bash
git clone https://github.com/YOUR_USERNAME/perth-rental-finder.git
cd perth-rental-finder
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set your API key**
```bash
# Windows
set ANTHROPIC_API_KEY=your_key_here

# Mac/Linux
export ANTHROPIC_API_KEY=your_key_here
```

**4. Start the server**
```bash
uvicorn main:app --reload --port 8502
```

**5. Open in browser**
```
http://localhost:8502
```

---

## How It Works

```
User opens app
     ↓
Friendly intro → asks weekly budget
     ↓
Area selection (8 Perth regions, single-select chip)
     ↓
Amenity priorities (10 options, multi-select chips)
     ↓
Backend: match_suburbs() filters by budget + region + amenities
     ↓
Results: 3 best matches (cheapest first) + 3 "also consider"
     ↓
Free-form chat: compare, deep dive, property advisor
```

The `match_suburbs()` function ranks suburbs by amenity score, applies region filtering, then sorts ascending by rent. Results are backed by real bond data — bond return rate indicates landlord fairness, average tenure indicates community stability.

---

## Data Sources

- **WA Government Bond Records** — 470,254 records from the Department of Mines, Industry Regulation and Safety
- **School data** — Primary and secondary school counts per suburb
- **Train network** — Distance to nearest station per suburb
- **Crime data** — WA Police district-level crime statistics

Suburb profiles for ~40 major Perth suburbs are hand-researched. Remaining ~160 suburbs use auto-generated data cards.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Chat UI |
| GET | `/dashboard` | Dashboard with 4 Chart.js charts |
| POST | `/api/chat` | Free-form chat + workflows |
| POST | `/api/survey-search` | Questionnaire search (region filter + rent sort) |
| GET | `/api/perth-stats` | Live Perth rent stats |
| GET | `/api/suburb-count` | Budget range → suburb count |
| GET | `/api/amenity-groups` | Amenity options |

---

## What I Learned

- Building and calling the Claude API for real conversational UX
- Structuring a FastAPI backend with caching and data pipelines
- Parsing and ranking real-world data (bond records, census, transport)
- Frontend JS without a framework — state machines, DOM manipulation, localStorage persistence
- Translating AI course concepts (RAG, agents, prompting) into a production-style project

---

## Acknowledgements

Built following Ed Donner's [LLM Engineering](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) and [Agentic AI Engineering](https://www.udemy.com/course/agentic-ai-engineering/) courses on Udemy.

Data sourced from the Western Australian Government open data portal.

---

*Perth is the least affordable capital city in Australia for renters. This tool exists to help.*
