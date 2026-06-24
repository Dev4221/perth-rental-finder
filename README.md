# 🏠 Perth Rental Finder

> Built for Perth renters who are tired of guessing. Real suburb data, no marketing fluff.

🔗 **[Try it live → perth-rental-finder.onrender.com](https://perth-rental-finder.onrender.com)**

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green) ![Claude API](https://img.shields.io/badge/Claude-API-orange) ![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## The problem it solves

Perth is the least affordable capital city in Australia for renters. Most search tools show you listings. This one helps you figure out *which suburb* to look in — based on your actual budget, where you need to be, and what matters to you day-to-day.

The data comes from real tenancy history, government records, and public datasets — not estimates or marketing copy.

---

## How it works

You answer three quick questions:

1. **What's your budget?** — type it naturally, like `$600/wk` or `$500–$650`
2. **Which part of Perth?** — tap a region (north, south, inner city, beach, etc.)
3. **What matters most nearby?** — train station, schools, beach, cafes, hospital, etc.

The app matches suburbs to your answers, sorts them cheapest-first, and gives you a breakdown of each one — rent trend, landlord fairness score, schools, train access, and a plain-English profile of what it's actually like to live there.

After the results, you can keep chatting — compare two suburbs, ask about a specific area, or get advice on a lease.

---

## What's under the hood

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pandas, DuckDB |
| Frontend | Vanilla JS, Chart.js |
| AI | Claude API (Anthropic) |
| Data | 470,254 residential tenancy bond records |
| Hosting | Render |

---

## Data sources

**Residential tenancy bonds** — 470,254 bond records from the Department of Mines, Industry Regulation and Safety (DMIRS), covering bond lodgements, returns, and dispute outcomes across Perth suburbs. Used to calculate median rent, landlord fairness (bond return rate), and average tenant tenure per suburb.

**Schools** — Primary and secondary school locations sourced from the School Curriculum and Standards Authority (SCSA) and cross-referenced with suburb boundaries. Used to show school counts within each suburb's catchment area.

**Public transport** — Train station locations and bus route coverage sourced from Transperth's open GTFS feed. Used to calculate distance to nearest train station per suburb.

**Crime statistics** — District-level crime data from WA Police Force annual statistical releases. Used to generate a relative safety score per suburb based on offence rates.

**Postcodes and suburb boundaries** — Australian Bureau of Statistics (ABS) suburb and locality boundaries, cross-referenced with Australia Post postcode data to map records to correct suburbs.

---

## What I learned building this

- How to call the Claude API and shape it into a real conversational experience
- Building a FastAPI backend with caching, data pipelines, and multiple endpoints
- Working with real messy data — bond records, school catchments, transport networks
- Writing frontend JS without a framework: state machines, DOM rendering, localStorage
- The gap between "AI course project" and "something people can actually use"

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
