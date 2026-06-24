# 🏠 Perth Rental Finder

> AI-powered suburb finder for Perth renters — built with Claude API and 470,254 real WA government bond records.

🔗 **[Live demo → perth-rental-finder.onrender.com](https://perth-rental-finder.onrender.com)**

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green) ![Claude API](https://img.shields.io/badge/Claude-API-orange) ![License](https://img.shields.io/badge/License-MIT-lightgrey)

![Perth Rental Finder](assets/screenshot.png)

---

## What It Does

Perth Rental Finder helps renters find the right suburb based on their budget and lifestyle priorities. It uses real WA government bond records to surface honest, data-driven insights — not marketing copy.

A 3-step conversational questionnaire guides the user through budget, area preference, and lifestyle priorities. Results are sorted cheapest-first, filtered by region, and backed by real data on landlord fairness, tenant tenure, schools, and transport.

---

## Features

- Conversational questionnaire — budget → area → amenity priorities → results
- Region-aware filtering (north/south/east Perth enforced in results)
- Cheapest suburbs shown first, automatically
- Chat history saved across browser sessions
- Free-form chat after search — compare suburbs, deep dive, property advisor
- 7 renter calculators: affordability, sharehouse split, moving costs, lease break, rent scenario planner, WA renter checklist, suburb insights
- Dark mode, mobile-responsive, no login required

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pandas |
| Frontend | Vanilla JS, Chart.js, CSS |
| AI | Claude API (Anthropic) |
| Data | WA Government Bond Records (470,254 records) |
| Hosting | Render |

---

## Project Background

Built as a capstone portfolio project across two Ed Donner courses:

- [LLM Engineering](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) — RAG, fine-tuning, Claude API
- [Agentic AI Engineering](https://www.udemy.com/course/agentic-ai-engineering/) — multi-agent systems, CrewAI, LangGraph, MCP

The goal was to build something real and useful — not a toy demo.

---

## How to Run Locally

```bash
git clone https://github.com/YOUR_USERNAME/perth-rental-finder.git
cd perth-rental-finder
pip install -r requirements.txt
```

Set your API key:
```bash
# Windows
set ANTHROPIC_API_KEY=your_key_here

# Mac/Linux
export ANTHROPIC_API_KEY=your_key_here
```

Start the server:
```bash
uvicorn main:app --reload --port 8502
```

Open `http://localhost:8502`

---

## Data Sources

- WA Government Bond Records — 470,254 records (Department of Mines, Industry Regulation and Safety)
- Primary and secondary school counts per suburb
- Distance to nearest train station per suburb
- WA Police district-level crime statistics

---

## What I Learned

- Calling the Claude API to build real conversational UX
- Structuring a FastAPI backend with caching and data pipelines
- Parsing and ranking real-world data (bond records, schools, transport)
- Frontend JS state machines, DOM manipulation, localStorage persistence
- Translating AI course concepts into a production-style project

---

## Acknowledgements

Built following Ed Donner's [LLM Engineering](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) and [Agentic AI Engineering](https://www.udemy.com/course/agentic-ai-engineering/) courses.

Data sourced from the Western Australian Government open data portal.

---

*Perth is the least affordable capital city in Australia for renters. This tool exists to help.*
