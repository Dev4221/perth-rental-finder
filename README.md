# Perth Rental Affordability Tracker

> **Core question:** Which Perth suburbs are locking vulnerable renters into a cycle of disadvantage?
> **Key chatbot query:** "Can a nurse afford to rent near Fiona Stanley Hospital?"

Built with Python · DuckDB · Claude API · Streamlit

---

## Project Structure

```
perth-rental-tracker/
├── README.md
├── requirements.txt
├── .env.example
├── app.py                        # Main Streamlit app (entry point)
├── pages/
│   ├── 1_Map.py                  # Choropleth map page
│   └── 2_Data_Explorer.py        # Raw data explorer page
├── scripts/
│   ├── 01_download_data.py       # Step 1: Download all 4 datasets
│   ├── 02_ingest_duckdb.py       # Step 2: Load into DuckDB
│   ├── 03_build_affordability.py # Step 3: Build analytics tables
│   └── 04_verify.py              # Step 4: Verify everything looks right
├── agent.py                      # Claude agent with tool-use loop
├── database.py                   # DuckDB connection + query helpers
├── tools.py                      # The 3 agent tools (query functions)
└── data/                         # Downloaded datasets land here (gitignored)
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

```bash
cp .env.example .env
# Edit .env and add your key
```

### 3. Download the datasets

```bash
python scripts/01_download_data.py
```

This downloads:
- **WA Rental Bond Data** — monthly tenancy records (AHDAP)
- **ABS SEIFA 2021** — disadvantage index by postcode
- **ABS 2021 Census G02** — income & housing data by SA2
- **ATO Postcode Tax Stats** — taxable income by postcode

> Most files download automatically. The ATO individual sample file requires a brief registration (see script output for instructions).

### 4. Ingest into DuckDB

```bash
python scripts/02_ingest_duckdb.py
python scripts/03_build_affordability.py
python scripts/04_verify.py
```

### 5. Run the app

```bash
streamlit run app.py
```

---

## Dataset Sources

| # | Dataset | Source | Licence |
|---|---------|--------|---------|
| 01 | WA Rental Bond Data | [AHDAP](https://housing-data-exchange.ahdap.org/dataset/west-australia-rental-bonds-data-2023-current) | CC BY 4.0 |
| 02 | ABS SEIFA 2021 | [ABS](https://www.abs.gov.au/statistics/people/people-and-communities/socio-economic-indexes-areas-seifa-australia/latest-release) | CC BY 4.0 |
| 03 | ABS Census 2021 DataPack | [ABS](https://www.abs.gov.au/census/find-census-data/datapacks) | CC BY 4.0 |
| 04 | ATO Taxation Statistics 2022–23 | [ATO](https://www.ato.gov.au/about-ato/research-and-statistics/in-detail/taxation-statistics/taxation-statistics-2022-23/) | CC BY 4.0 |

---

## What the Chatbot Answers

| Type | Example Query |
|------|--------------|
| Key worker | "Can a nurse on a single income afford a 2-bed unit near Fiona Stanley Hospital?" |
| Suburb search | "Show suburbs where a teacher can afford to rent" |
| Trend | "How has rent changed in Armadale over 12 months?" |
| Stress zones | "Which suburbs have both high rent stress AND high disadvantage?" |
| Availability | "How many rentals are under $450/week in Perth metro?" |
| Compare | "Compare affordability in Fremantle vs Midland for $80k income" |

---

## Affordability Formula

```
rent_to_income_ratio = (median_weekly_rent × 52) / median_annual_income
rental_stress = rent_to_income_ratio > 0.30  # 30% threshold
```

---

## LinkedIn Post Strategy

- Lead with a stark finding (e.g. "X% of Perth suburbs are unaffordable for a single nurse")
- 30-second screen recording of the chatbot
- One sentence on the stack
- Tag: @REIWA @DeptCommunitiesWA @ABS @ATO @Anthropic @Streamlit
- End with: "Which suburb surprised you most?"
