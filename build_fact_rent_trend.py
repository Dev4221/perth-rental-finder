"""
build_fact_rent_trend.py — Phase 1, step C

Builds fact_rent_trend: one row per (suburb_key, month_key), with
median_weekly_rent averaged across any alias-variant rows of rent_trend that
reported that month under different spellings ('Maylands'/'MAYLANDS'/
'Maylands ').

Grain: suburb_key x month_key
Source: rent_trend, joined through dim_suburb_alias (exact match on the raw
suburb string — every rent_trend.suburb value was collected into
dim_suburb_alias by build_dim_suburb.py, so this should be a complete join)
and dim_month (exact match on month).

Depends on: dim_suburb, dim_suburb_alias, dim_month (step A) and rent_trend.

Run: uv run python build_fact_rent_trend.py
(stop the FastAPI server first — same read-write reasoning as step A)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
conn = duckdb.connect(DB_PATH)

tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
missing = [t for t in ["dim_suburb", "dim_suburb_alias", "dim_month", "rent_trend"] if t not in tables]
if missing:
    print(f"ERROR: required table(s) missing: {missing}")
    print("If dim_suburb/dim_suburb_alias/dim_month are missing, run build_dim_suburb.py first (step A).")
    sys.exit(1)

print("=" * 70)
print("Building fact_rent_trend")
print("=" * 70)

# Orphan check: any rent_trend.suburb not covered by dim_suburb_alias?
# (should be none, by construction — dim_suburb_alias was built FROM
# rent_trend's distinct suburb values among others)
orphans = conn.execute("""
    SELECT DISTINCT rt.suburb
    FROM rent_trend rt
    LEFT JOIN dim_suburb_alias a ON a.alias_raw = rt.suburb
    WHERE a.suburb_key IS NULL
""").fetchdf()
if not orphans.empty:
    print(f"WARNING: {len(orphans)} distinct rent_trend.suburb values have no "
          f"dim_suburb_alias entry (these rows will be DROPPED from fact_rent_trend):")
    print(orphans.head(10).to_string(index=False))
else:
    print("OK: every rent_trend.suburb value resolves via dim_suburb_alias.")

conn.execute("DROP TABLE IF EXISTS fact_rent_trend")
conn.execute("""
    CREATE TABLE fact_rent_trend AS
    SELECT a.suburb_key, rt.month as month_key,
           AVG(rt.median_weekly_rent) as median_weekly_rent
    FROM rent_trend rt
    JOIN dim_suburb_alias a ON a.alias_raw = rt.suburb
    JOIN dim_month m ON m.month_key = rt.month
    GROUP BY a.suburb_key, rt.month
""")

n_rows = conn.execute("SELECT COUNT(*) FROM fact_rent_trend").fetchone()[0]
n_suburbs = conn.execute("SELECT COUNT(DISTINCT suburb_key) FROM fact_rent_trend").fetchone()[0]
n_dim_suburb = conn.execute("SELECT COUNT(*) FROM dim_suburb").fetchone()[0]
n_rent_trend = conn.execute("SELECT COUNT(*) FROM rent_trend").fetchone()[0]
month_min, month_max = conn.execute("SELECT MIN(month_key), MAX(month_key) FROM fact_rent_trend").fetchone()

print(f"\nfact_rent_trend: {n_rows} rows written")
print(f"  distinct suburbs with rent history: {n_suburbs} of {n_dim_suburb} in dim_suburb")
print(f"  ({n_dim_suburb - n_suburbs} suburbs in dim_suburb have no rent_trend data at all —"
      f" expected for suburbs that entered dim_suburb only via rental_bonds/schools/etc.)")
print(f"  month range: {month_min} to {month_max}")
print(f"  source rent_trend rows: {n_rent_trend} -> {n_rows} after casing-variant grouping "
      f"({n_rent_trend - n_rows} rows merged away)")

# -----------------------------------------------------------------------
# Validation: Maylands' full trend, now a single consistent series
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("VALIDATION: Maylands rent history (single consistent series)")
print("=" * 70)
mayl = conn.execute("""
    SELECT f.month_key, f.median_weekly_rent
    FROM fact_rent_trend f
    JOIN dim_suburb s ON s.suburb_key = f.suburb_key
    WHERE UPPER(s.suburb_name) = 'MAYLANDS'
    ORDER BY f.month_key
""").fetchdf()
print(f"Rows: {len(mayl)}")
print(mayl.to_string(index=False))

if len(mayl) >= 6:
    first_rent = mayl.iloc[0]["median_weekly_rent"]
    first_month = mayl.iloc[0]["month_key"]
    recent = mayl.tail(3)["median_weekly_rent"].mean()
    older = mayl.iloc[-6:-3]["median_weekly_rent"].mean()
    pct = (recent - older) / older * 100 if older > 0 else 0
    signal = "rising" if pct > 4 else ("easing" if pct < -2 else "stable")
    print(f"\nhist_note-equivalent: 'From ${first_rent:.0f}/wk in {first_month}'")
    print(f"trend_txt-equivalent: '{signal} {pct:.1f}%' (last 3 months vs prior 3)")
    print("\nBoth numbers above now come from this ONE series. Earlier this session,")
    print("these were computed from different casing-variant subsets and could")
    print("contradict each other ($850 in 2023 vs 'Rising 12%'); that can't happen")
    print("now. (Separately — main.py's current hist_note wording hardcodes")
    print("'Up from', regardless of whether the value moved up or down since;")
    print("that's a small main.py wording fix for step G, not a fact-table issue.)")
elif len(mayl) > 0:
    print(f"\n(Only {len(mayl)} months — too few for a 3-vs-3 trend comparison, "
          f"but the series itself is the point: one suburb, one series.)")
else:
    print("\nNo rows for Maylands — unexpected, worth investigating before proceeding.")

# -----------------------------------------------------------------------
# Sample: a few suburbs with the most history, as a general sanity check
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("Sample: 5 suburbs with the most months of history")
print("=" * 70)
sample = conn.execute("""
    SELECT s.suburb_name, COUNT(*) as n_months,
           MIN(f.month_key) as first_month, MAX(f.month_key) as last_month,
           ROUND(AVG(f.median_weekly_rent), 0) as avg_rent
    FROM fact_rent_trend f
    JOIN dim_suburb s ON s.suburb_key = f.suburb_key
    GROUP BY s.suburb_name
    ORDER BY n_months DESC
    LIMIT 5
""").fetchdf()
print(sample.to_string(index=False))

print("\n" + "=" * 70)
print("DONE. Paste this entire output back.")
print("=" * 70)
