"""
build_fact_suburb_profile.py — Phase 1, step D

Builds fact_suburb_profile: one row per suburb_key (current snapshot,
SCD Type 1), populated for the ~26 "rich stats" suburbs and NULL elsewhere.

CORE columns (confirmed schemas — these column names were successfully
queried in earlier diagnostics this session):
  median_rent_2br, median_rent_3br, total_tenancies, disadvantage_category,
  irsd_decile, rent_to_income_ratio   <- from affordability
  avg_tenancy_years, dispute_rate_pct <- from suburb_stats

ENRICHMENT columns (UNCERTAIN schemas — ato_income/seifa/census_g02 column
names haven't been confirmed against the real database, the same situation
'seifa' was in for step A). For each, this script auto-detects plausible
suburb-name and value columns; if none match, it prints DESCRIBE output and
leaves that column NULL rather than guessing and erroring:
  ato_median_income          <- ato_income, best-effort
  seifa_decile                <- seifa, best-effort
  census_median_hhd_income    <- census_g02, best-effort SA2-name match,
                                   expected mostly NULL regardless (SA2 areas
                                   don't map 1:1 to suburbs)

Depends on: dim_suburb, dim_suburb_alias (step A), affordability, suburb_stats.

Run: uv run python build_fact_suburb_profile.py
(stop the FastAPI server first — same read-write reasoning as steps A-C)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
conn = duckdb.connect(DB_PATH)

tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
missing = [t for t in ["dim_suburb", "dim_suburb_alias", "affordability", "suburb_stats"] if t not in tables]
if missing:
    print(f"ERROR: required table(s) missing: {missing}")
    print("If dim_suburb/dim_suburb_alias are missing, run build_dim_suburb.py first (step A).")
    sys.exit(1)


def find_column(table, candidates):
    """Return (matched_column_name, all_actual_columns) — case-insensitive
    match against a list of candidate names, or (None, all_actual_columns)
    if none match."""
    actual = conn.execute(f"DESCRIBE {table}").fetchdf()["column_name"].tolist()
    actual_lower = {c.lower(): c for c in actual}
    for cand in candidates:
        if cand.lower() in actual_lower:
            return actual_lower[cand.lower()], actual
    return None, actual


print("=" * 70)
print("STEP D-CORE: fact_suburb_profile from affordability + suburb_stats")
print("=" * 70)

conn.execute("DROP TABLE IF EXISTS fact_suburb_profile")
conn.execute("""
    CREATE TABLE fact_suburb_profile AS
    SELECT
        s.suburb_key,
        af.median_rent_2br,
        af.median_rent_3br,
        af.total_tenancies,
        ss.avg_tenancy_years,
        ss.dispute_rate_pct,
        af.disadvantage_category,
        af.irsd_decile,
        af.rent_to_income_ratio,
        CAST(NULL AS DOUBLE)  AS ato_median_income,
        CAST(NULL AS INTEGER) AS seifa_decile,
        CAST(NULL AS DOUBLE)  AS census_median_hhd_income
    FROM dim_suburb s
    LEFT JOIN (
        SELECT a.suburb_key, af.*
        FROM affordability af
        JOIN dim_suburb_alias a
          ON a.alias_raw = af.suburb
    ) af ON af.suburb_key = s.suburb_key
    LEFT JOIN (
        SELECT a.suburb_key, ss.*
        FROM suburb_stats ss
        JOIN dim_suburb_alias a
          ON a.alias_raw = ss.suburb
    ) ss ON ss.suburb_key = s.suburb_key
""")

n_total = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile").fetchone()[0]
n_with_affordability = conn.execute(
    "SELECT COUNT(*) FROM fact_suburb_profile WHERE median_rent_2br IS NOT NULL"
).fetchone()[0]
n_rich = conn.execute("SELECT COUNT(*) FROM dim_suburb WHERE has_rich_stats").fetchone()[0]

print(f"fact_suburb_profile: {n_total} rows written (one per dim_suburb row)")
print(f"  populated from affordability: {n_with_affordability} "
      f"(dim_suburb.has_rich_stats=true count: {n_rich} — should match)")
if n_with_affordability != n_rich:
    print("  WARNING: these don't match — worth investigating before relying on this table.")

# -----------------------------------------------------------------------
# Enrichment 1: ato_income
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("ENRICHMENT 1: ato_income -> ato_median_income")
print("=" * 70)
if "ato_income" not in tables:
    print("ato_income table not found — skipping, ato_median_income stays NULL.")
else:
    # NOTE: ato_income's "suburb" column actually holds POSTCODES (confirmed by
    # inspection — values like 6150, 6160, 6163 — despite the name). Join via
    # dim_suburb.postcode directly, same pattern as the amenities tables, not
    # via dim_suburb_alias (which only matches real suburb-name strings and
    # silently matched ~nothing against postcode values).
    postcode_col, ato_cols = find_column("ato_income", ["suburb", "postcode", "Suburb", "SUBURB"])
    value_col, _ = find_column("ato_income", [
        "median_income", "ato_median_income", "median_taxable_income",
        "median_total_income", "median_income_aud", "income"
    ])
    if postcode_col and value_col:
        conn.execute(f"""
            UPDATE fact_suburb_profile
            SET ato_median_income = src.val
            FROM (
                SELECT d.suburb_key, ai."{value_col}" as val
                FROM ato_income ai
                JOIN dim_suburb d
                  ON d.postcode = CAST(ai."{postcode_col}" AS VARCHAR)
            ) src
            WHERE fact_suburb_profile.suburb_key = src.suburb_key
        """)
        n = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE ato_median_income IS NOT NULL").fetchone()[0]
        print(f"OK: matched postcode column '{postcode_col}', value column '{value_col}'. "
              f"{n} suburbs populated (joined via postcode, not name).")
    else:
        print(f"Could not confidently match columns. ato_income columns are: {ato_cols}")
        print(f"  postcode column match: {postcode_col!r}, value column match: {value_col!r}")
        print("ato_median_income stays NULL — revisit with the real column names above.")

# -----------------------------------------------------------------------
# Enrichment 2: seifa
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("ENRICHMENT 2: seifa -> seifa_decile")
print("=" * 70)
if "seifa" not in tables:
    print("seifa table not found — skipping, seifa_decile stays NULL.")
else:
    # NOTE: seifa's "SUBURB_NAME" column actually holds POSTCODES (confirmed
    # by inspection — values like 6061, 6027, 6150 — despite the name). Same
    # postcode-join fix as ato_income above.
    postcode_col, seifa_cols = find_column("seifa", ["suburb_name", "suburb", "postcode", "SUBURB"])
    value_col, _ = find_column("seifa", [
        "irsd_decile", "seifa_decile", "IRSD_DECILE", "decile", "irsd_score"
    ])
    if postcode_col and value_col:
        conn.execute(f"""
            UPDATE fact_suburb_profile
            SET seifa_decile = src.val
            FROM (
                SELECT d.suburb_key, sf."{value_col}" as val
                FROM seifa sf
                JOIN dim_suburb d
                  ON d.postcode = CAST(sf."{postcode_col}" AS VARCHAR)
            ) src
            WHERE fact_suburb_profile.suburb_key = src.suburb_key
        """)
        n = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE seifa_decile IS NOT NULL").fetchone()[0]
        print(f"OK: matched postcode column '{postcode_col}', value column '{value_col}'. "
              f"{n} suburbs populated (joined via postcode, not name).")
    else:
        print(f"Could not confidently match columns. seifa columns are: {seifa_cols}")
        print(f"  postcode column match: {postcode_col!r}, value column match: {value_col!r}")
        print("seifa_decile stays NULL — revisit with the real column names above.")

# -----------------------------------------------------------------------
# Enrichment 3: census_g02 (best-effort SA2-name match, expected low coverage)
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("ENRICHMENT 3: census_g02 -> census_median_hhd_income (best-effort)")
print("=" * 70)
if "census_g02" not in tables:
    print("census_g02 table not found — skipping, census_median_hhd_income stays NULL.")
else:
    name_col, census_cols = find_column("census_g02", [
        "sa2_name_2021", "SA2_NAME_2021", "sa2_name", "suburb_name", "suburb"
    ])
    value_col, _ = find_column("census_g02", [
        "median_tot_hhd_inc_weekly", "Median_tot_hhd_inc_weekly",
        "median_hhd_income_weekly", "median_household_income"
    ])
    if name_col and value_col:
        conn.execute(f"""
            UPDATE fact_suburb_profile
            SET census_median_hhd_income = src.val
            FROM (
                SELECT s.suburb_key, c."{value_col}" as val
                FROM census_g02 c
                JOIN dim_suburb s
                  ON UPPER(TRIM(c."{name_col}")) = UPPER(TRIM(s.suburb_name))
            ) src
            WHERE fact_suburb_profile.suburb_key = src.suburb_key
        """)
        n = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE census_median_hhd_income IS NOT NULL").fetchone()[0]
        print(f"OK: matched name column '{name_col}', value column '{value_col}'. "
              f"{n} suburbs populated via exact SA2-name match (expected to be low — "
              f"SA2 areas don't map 1:1 to suburbs).")
    else:
        print(f"Could not confidently match columns. census_g02 columns are: {census_cols}")
        print(f"  name column match: {name_col!r}, value column match: {value_col!r}")
        print("census_median_hhd_income stays NULL — documented limitation either way.")

# -----------------------------------------------------------------------
# Validation: Murdoch / Fremantle / Cottesloe (the 26) + a non-rich suburb
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("VALIDATION: sample rows")
print("=" * 70)
sample = conn.execute("""
    SELECT s.suburb_name, s.has_rich_stats, p.median_rent_2br, p.median_rent_3br,
           p.total_tenancies, p.avg_tenancy_years, p.dispute_rate_pct,
           p.ato_median_income, p.seifa_decile, p.census_median_hhd_income
    FROM fact_suburb_profile p
    JOIN dim_suburb s ON s.suburb_key = p.suburb_key
    WHERE UPPER(s.suburb_name) IN ('MURDOCH','FREMANTLE','COTTESLOE','MAYLANDS')
    ORDER BY s.suburb_name
""").fetchdf()
print(sample.to_string(index=False))

print("\n" + "=" * 70)
print("DONE. Paste this entire output back.")
print("=" * 70)
