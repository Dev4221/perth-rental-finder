# 🏠 Perth Rental Finder

### An AI-powered rental search tool for Perth, Western Australia

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Claude API](https://img.shields.io/badge/Claude-API-D97706?style=flat&logo=anthropic&logoColor=white)](https://anthropic.com)
[![Render](https://img.shields.io/badge/Deployed_on-Render-46E3B7?style=flat&logo=render&logoColor=white)](https://perth-rental-finder.onrender.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey?style=flat)](LICENSE)

🔗 **[Try the live app → perth-rental-finder.onrender.com](https://perth-rental-finder.onrender.com)**

---


---

## Why I built this

Perth is the least affordable capital city in Australia for renters. But the tools available to renters are mostly listing aggregators — they'll show you what's available, not whether a suburb is worth living in, whether the landlord is likely to be reasonable, or whether rents are heading up or down.

I wanted to build something that answered those questions honestly, using real data — not marketing copy. So I built Perth Rental Finder: a conversational tool that asks three quick questions and returns suburb recommendations backed by 470,254 real WA government tenancy bond records.

---

## What it does

**A guided 3-step search:**

1. **Budget** — type it naturally: `$600/wk`, `$500–$650`, `700`
2. **Area** — tap your preferred region of Perth (north, south, inner city, near the beach, etc.)
3. **Priorities** — select what matters most: train access, schools, cafes, hospital, parks, dog-friendly, and more

Results are sorted cheapest-first and filtered by the region you chose — so if you pick "Northern suburbs", you won't see Fremantle in the results.

**Each suburb card shows:**
- Median weekly rent + trend (↑ Rent rising / → Rent stable / ↓ Rent easing)
- Bond return rate: the % of tenants who got their bond back, used as a signal for landlord fairness
- Average tenant tenure: how long people tend to stay, used as a signal for community stability
- Schools nearby (primary + secondary)
- Distance to nearest train station
- A plain-English profile of what the suburb is actually like

**After the results, you can keep chatting:**
- *"Compare Joondalup and Balga"*
- *"Tell me everything about Victoria Park"*
- *"Is this a good lease agreement?"*

**7 built-in renter tools** in a side panel:
- Affordability calculator — enter your salary and see how much rent you can comfortably afford (based on the standard guideline that rent should be under 30% of your income)
- Sharehouse rent splitter
- Moving costs estimator
- Lease break calculator (with WA law references)
- 3-year rent scenario planner
- WA renter rights checklist
- Suburb insights panel

---

## Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python, FastAPI | API server, data processing |
| Database | DuckDB, Pandas | Querying bond + suburb data |
| AI | Claude API (Anthropic) | Conversational search, suburb insights |
| Frontend | Vanilla JS, Chart.js | Chat UI, calculators, charts |
| Hosting | Render | Production deployment |

No frontend framework. The entire UI is vanilla JS with state machines, DOM rendering, and localStorage persistence. I built it this way to understand how it works, not abstract it away.

---

## Data sources

All data is sourced from official Australian government datasets.

| Dataset | Source | Used for |
|---|---|---|
| **Residential tenancy bonds** | [Department of Mines, Industry Regulation and Safety (DMIRS)](https://www.dmirs.wa.gov.au/content/bond-data) — 470,254 records | Median rent, bond return rate, average tenure per suburb |
| **School locations** | [School Curriculum and Standards Authority (SCSA)](https://www.scsa.wa.edu.au) + [Data.WA](https://www.data.wa.gov.au) | Primary and secondary school counts per suburb |
| **Public transport** | [Transperth GTFS feed](https://www.transperth.wa.gov.au/About/Spatial-Data-Access) | Distance to nearest train station per suburb |
| **Crime statistics** | [WA Police Force annual statistical releases](https://www.police.wa.gov.au/Crime/CrimeStatistics) | Relative safety score per suburb |
| **Suburb boundaries** | [Australian Bureau of Statistics (ABS)](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files) + [Australia Post](https://auspost.com.au/postcode) | Mapping records to correct suburbs and postcodes |

---

## Architecture

```
User → 3-step questionnaire (budget, area, amenities)
         ↓
Frontend sends request to /api/survey-search
         ↓
match_suburbs() filters by budget + region + amenity score
         ↓
Results sorted ascending by rent
         ↓
Suburb cards rendered with bond data, schools, transport, trend
         ↓
Free-form chat → Claude API → workflow routing
  ├── "compare X and Y"     → compare workflow
  ├── "tell me about X"     → deep dive workflow
  ├── "is this lease ok?"   → property advisor workflow
  └── general search        → match_suburbs() again
```

Chat history is persisted to localStorage so conversations survive page refreshes.

---

## Running locally

```bash
git clone https://github.com/Dev4221/perth-rental-finder.git
cd perth-rental-finder
pip install -r requirements.txt
```

Set your Anthropic API key:
```bash
# Windows
set ANTHROPIC_API_KEY=your_key_here

# Mac / Linux
export ANTHROPIC_API_KEY=your_key_here
```

Start the server:
```bash
uvicorn main:app --reload --port 8502
```

Open `http://localhost:8502`

---

## What I learned

This was the most technically demanding project I've built. A few things that stand out:

- **Working with messy real data** — bond records, school catchments, and transport feeds all have their own quirks. Getting them to join cleanly took more work than the AI parts.
- **Conversational UX is harder than it looks** — getting the Claude API to consistently route messages to the right workflow (search vs. compare vs. deep dive) required careful prompt engineering and fallback logic.
- **Vanilla JS forces clarity** — without a framework, every interaction is explicit. I now understand state management in a way I didn't before.
- **The gap between "working" and "production-ready"** — caching, error handling, graceful fallbacks, region filtering, and mobile responsiveness were all second-pass work that made the difference between a demo and something people can actually use.

---

## Project context

Built as a capstone portfolio project following two courses by [Ed Donner](https://edwarddonner.com):

- [LLM Engineering — Master AI and Large Language Models](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) — RAG pipelines, fine-tuning, prompt engineering, the Claude and OpenAI APIs
- [The Complete Agentic AI Engineering Course](https://www.udemy.com/course/agentic-ai-engineering/) — multi-agent systems, CrewAI, LangGraph, OpenAI Agents SDK, MCP servers

---

*Data sourced from official Australian and Western Australian government open data portals. 470,254 bond records covering Perth metro and regional WA.*
