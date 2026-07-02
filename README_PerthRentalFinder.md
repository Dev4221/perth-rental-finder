# Perth Rental Finder

**A conversational rental search tool built on 470,254 real WA government tenancy bond records.**

Live demo: https://perth-rental-finder.onrender.com

---

## The problem

Perth is the least affordable capital city in Australia for renters. Vacancy rates have been below 1% for over two years. Median rents have risen faster than any other Australian city. And the tools available to renters are almost entirely listing aggregators - they show you what is available, not whether a suburb is actually worth living in.

The data to answer those questions exists. The WA government publishes every residential tenancy bond lodged and returned across the state. That record contains the median rent per suburb, how long tenants tend to stay, and what percentage of tenants get their bond back in full - a reliable signal for how landlords in that area tend to behave.

Perth Rental Finder makes that data accessible through a three-question conversational search, backed by AI.

---

## What it does

The search takes three inputs: budget, preferred area of Perth, and what matters most to the person searching. It returns suburb recommendations sorted by price, each with a plain-English profile built from real government data.

Each result shows the median weekly rent and whether it has been rising, stable, or easing over time. It shows the bond return rate - the percentage of tenants who got their full bond back - as a signal for landlord behaviour in that suburb. It shows average tenant tenure as a signal for community stability. It shows nearby schools, distance to the nearest train station, and a plain-English description of what the suburb is actually like to live in.

After the initial results, the conversation continues. You can compare two suburbs, ask for everything about a specific area, paste in a lease agreement and ask whether it looks reasonable, or ask a general question about your rights as a renter in Western Australia.

Seven built-in tools sit in a side panel: an affordability calculator based on the 30% of income guideline, a sharehouse rent splitter, a moving costs estimator, a lease break calculator with references to WA tenancy law, a three-year rent scenario planner, a WA renter rights checklist, and a suburb insights panel.

---

## The data

All data is sourced from official Australian government datasets.

| Dataset | Source | Used for |
|---|---|---|
| Residential tenancy bonds | Department of Mines, Industry Regulation and Safety (DMIRS) | Median rent, bond return rate, average tenure per suburb |
| School locations | School Curriculum and Standards Authority and Data.WA | Primary and secondary school counts per suburb |
| Public transport | Transperth GTFS feed | Distance to nearest train station per suburb |
| Crime statistics | WA Police Force annual statistical releases | Relative safety score per suburb |
| Suburb boundaries | Australian Bureau of Statistics and Australia Post | Mapping records to suburbs and postcodes |

470,254 bond records covering Perth metro and regional WA.

---

## Technical decisions worth noting

**Why DuckDB rather than a traditional database?** The bond dataset is 470,000 rows of flat records that need fast aggregation by suburb, rent range, and date range. DuckDB handles analytical queries on flat files faster than SQLite and without the infrastructure overhead of PostgreSQL. The entire dataset fits in memory and query times are under 100ms.

**Why vanilla JavaScript rather than React or Vue?** Without a framework, every interaction is explicit. State management, DOM updates, and event handling all have to be reasoned about directly. The result is a more complete understanding of how the UI actually works, and a codebase with no build step and no dependency on a framework that might change.

**Why a three-step questionnaire rather than a free-text search box?** Free-text search works well when people know what they are looking for. Most renters searching in an unfamiliar city do not. A structured questionnaire surfaces the right suburbs from the right region at the right price point before any AI is involved. The conversational layer then handles the follow-up questions that a questionnaire cannot.

**Why workflow routing in the conversational layer?** A single general-purpose prompt for all conversation types produces inconsistent output. Messages that look like comparisons, deep dives, lease reviews, and general searches each need different context and different response formats. The routing logic classifies the intent of each message before choosing which prompt and which data to include. This is the approach used in production conversational systems and it is what separates a reliable tool from one that works sometimes.

---

## Stack

Python, FastAPI, DuckDB, Pandas, Claude API (Anthropic), Vanilla JavaScript, Chart.js, Render

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

Open http://localhost:8502

---

## License

MIT
