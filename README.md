# 🏠 Perth Rental Finder

> Built for Perth renters who are tired of guessing. Real suburb data, no marketing fluff.

🔗 **[Try it live → perth-rental-finder.onrender.com](https://perth-rental-finder.onrender.com)**

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green) ![Claude API](https://img.shields.io/badge/Claude-API-orange) ![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## The problem it solves

Perth is the least affordable capital city in Australia for renters. Most search tools show you listings. This one helps you figure out *which suburb* to look in — based on your actual budget, where you need to be, and what matters to you day-to-day.

It's backed by 470,254 real WA government bond records, so the data on landlord fairness, how long people tend to stay, and what rents are actually doing comes from real tenancy history — not estimates.

---

## How it works

You answer three quick questions:

1. **What's your budget?** — type it naturally, like `$600/wk` or `$500–$650`
2. **Which part of Perth?** — tap a region (north, south, inner city, beach, etc.)
3. **What matters most nearby?** — train station, schools, beach, cafes, hospital, etc.

The app matches suburbs to your answers, sorts them cheapest-first, and gives you a breakdown of each one — rent trend, bond return rate, schools, train access, and a plain-English profile of what it's actually like to live there.

After the results, you can keep chatting — compare two suburbs, ask about a specific area, or get advice on a lease.

---

## What's under the hood

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pandas, DuckDB |
| Frontend | Vanilla JS, Chart.js |
| AI | Claude API (Anthropic) |
| Data | 470,254 WA Government bond records |
| Hosting | Render |

---

## Background

I built this as a portfolio project while completing two courses by Ed Donner:

- [LLM Engineering](https://www.udemy.com/course/llm-engineering-master-ai-and-large-language-models/) — working with large language models, RAG, fine-tuning, the Claude API
- [Agentic AI Engineering](https://www.udemy.com/course/agentic-ai-engineering/) — multi-agent systems, CrewAI, LangGraph, MCP servers

The goal was to build something genuinely useful, not just a demo. Perth's rental market felt like the right problem — it's real, it's local, and good information is hard to find.

---

## Run it locally

```bash
git clone https://github.com/Dev4221/perth-rental-finder.git
cd perth-rental-finder
pip install -r requirements.txt
```

```bash
# Set your Anthropic API key
set ANTHROPIC_API_KEY=your_key_here        # Windows
export ANTHROPIC_API_KEY=your_key_here     # Mac/Linux
```

```bash
uvicorn main:app --reload --port 8502
# Open http://localhost:8502
```

---

## Data sources

- WA Government bond records — 470,254 tenancy bonds lodged with the Department of Mines, Industry Regulation and Safety
- School counts per suburb — primary and secondary
- Train station distances — nearest station per suburb
- Crime data — WA Police district-level statistics

Suburb profiles for ~40 major Perth suburbs are hand-researched. The rest use auto-generated cards built from the data above.

---

## What I learned building this

- How to call the Claude API and shape it into a real conversational experience
- Building a FastAPI backend with caching, data pipelines, and multiple endpoints
- Working with real messy data — bond records, school catchments, transport networks
- Writing frontend JS without a framework: state machines, DOM rendering, localStorage
- The gap between "AI course project" and "something people can actually use"

---

*Data sourced from the Western Australian Government open data portal. Built following Ed Donner's LLM Engineering and Agentic AI Engineering courses.*
