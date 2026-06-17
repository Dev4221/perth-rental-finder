# Perth Rental Finder

**Live: [add Render URL here once deployed]** · [Dashboard](/dashboard) · `DEPLOYMENT.md` has the full deploy writeup.

A conversational rental-search app for Perth and regional WA, built on a
proper dimensional data warehouse over 470,254 real WA government rental
bond records (March 2023 – May 2026). FastAPI backend, an embedded HTML/JS
chat frontend, DuckDB for storage and analytics.

## What this actually is

Most of this project's interesting decisions are about taking a working
prototype — a chatbot that answered convincingly for a curated set of 26
suburbs — and rebuilding its data layer so it correctly covers the other
~1,196 suburbs that were sitting in the same raw dataset the whole time,
unreachable because of how the original queries were written.

`DATA_QUALITY.md` is the detailed writeup: the specific bugs this surfaced
(a postcode-formatted-as-a-string join bug, a suburb name substring
collision, a second independent code path that disagreed with the first one
about the same suburb's rent), how each was found through live testing
rather than code review alone, and where the data is genuinely thin versus
where it's been backfilled and clearly flagged as such.

## Architecture

```
Raw source tables (19 tables, ~470k bond records, government data)
        │
        ▼
dim_suburb, dim_suburb_alias, dim_month        (build_dim_suburb.py)
        │
        ├──► fact_rent_trend                   (build_fact_rent_trend.py)
        ├──► fact_suburb_profile               (build_fact_suburb_profile.py)
        └──► fact_suburb_amenities             (build_fact_suburb_amenities.py,
                                                  load_bus_proximity.py)
        │
        ▼
main.py  ── get_all_suburbs_data() / get_rent_trend_for()
        │         reads the warehouse, not the raw tables
        ├──► 6 named workflows (search, deep dive, compare, negotiate,
        │     property advisor, application review)
        └──► general workflow ──► agent.py / tools.py
                                    (Claude tool-calling loop, same warehouse)
```

The dimensional model exists so that every part of the app — the chat
workflows in `main.py`, the agent's tools in `tools.py`, and (eventually)
any dashboard — reads suburb data through the same `dim_suburb` /
`dim_suburb_alias` resolution and the same fact tables, rather than each
having its own slightly-different idea of which 26 suburbs exist or how a
raw spelling maps to a canonical name.

## Coverage

| | |
|---|---|
| Total suburbs | 1,222 |
| With rent history | 1,163 |
| With full affordability profile (2BR/3BR rent, tenancy, dispute rate) | 26 |
| With ATO income / SEIFA decile | 173 |
| With school data | 1,129 |
| With train proximity | 1,055 |
| With crime data (district-level) | 173 |

The 26-suburb profile set is real, detailed data for those specific
suburbs — not a placeholder. Every other suburb still gets real rent
history and, where available, school/train/crime data; it just doesn't get
the deeper affordability profile, and the app is honest about that rather
than estimating it. See `DATA_QUALITY.md` for the full reasoning on what
gets estimated (a narrow, flagged exception for two ranking-only fields)
versus what's simply left absent.

## Running it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```powershell
# Build the warehouse (run once, or after source data changes)
uv run python build_dim_suburb.py
uv run python load_bus_proximity.py
uv run python build_fact_rent_trend.py
uv run python build_fact_suburb_profile.py
uv run python build_fact_suburb_amenities.py

# Validate the build
uv run python test_data_model.py

# Run the app
uv run python -m uvicorn main:app --reload --port 8502
```

`main.py` requires `database.py` (a thin DuckDB connection wrapper, not
included in this listing — see your local setup) and an `ANTHROPIC_API_KEY`
environment variable for the conversational workflows.

## Key files

- `main.py` — FastAPI app: the embedded chat frontend, the 6 named
  workflow handlers, and the warehouse-reading data functions
  (`get_all_suburbs_data`, `get_rent_trend_for`, `suburb_to_card`,
  `suburb_deep_dive`, `find_suburb_mentions`, `match_suburbs`)
- `agent.py` — the Claude tool-calling loop for free-form questions that
  don't match one of the 6 named workflows
- `tools.py` — the tools the agent above can call, reading the same
  warehouse as `main.py`
- `build_dim_suburb.py`, `build_fact_rent_trend.py`,
  `build_fact_suburb_profile.py`, `build_fact_suburb_amenities.py`,
  `load_bus_proximity.py` — the ETL scripts that build the warehouse from
  raw source tables
- `test_data_model.py` — referential integrity and coverage checks against
  the built warehouse
- `schema.sql` — full DDL reference for the dimensional model
- `DATA_QUALITY.md` — the detailed findings, fixes, and known limitations

## Status

The data warehouse and all 6 named chat workflows, plus the general/agent
fallback path, have been built, tested against real data, and smoke-tested
against the live running app. The `/dashboard` page is built and live,
reading from the same warehouse as the chat workflows. See
`DATA_QUALITY.md` and `DEPLOYMENT.md` for the full findings and how this is
deployed.

**Live app**: see the link at the top of this README (add it here once the
Render deploy is confirmed working end to end).
