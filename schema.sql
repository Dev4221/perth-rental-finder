-- =============================================================================
-- Perth Rental Finder — dimensional model schema (logical reference)
--
-- This is the *target structure* — what build_dim_suburb.py and the Phase 1
-- fact-table scripts produce, expressed as DDL with explicit constraints for
-- documentation purposes. In practice, the build scripts use
-- `CREATE TABLE ... AS SELECT` from a pandas dataframe (types inferred, no
-- declared constraints) — simpler to write, and test_data_model.py (step F)
-- validates the relationships below by query instead of relying on the
-- database to enforce them.
--
-- Status markers:
--   [BUILT]    — build_dim_suburb.py (pending real-data run, step A)
--   [PHASE 1]  — designed, scripts to be written (steps C/D/E)
--   [FUTURE]   — designed, only built if the dashboard needs them
-- =============================================================================


-- =============================================================================
-- DIMENSIONS
-- =============================================================================

-- [BUILT] One row per real suburb (~1,163 expected)
CREATE TABLE dim_suburb (
    suburb_key      INTEGER PRIMARY KEY,        -- surrogate key, 1..N
    suburb_name     VARCHAR NOT NULL,           -- canonical display name
    postcode        VARCHAR,                    -- nullable; ~467 of 1,163 known
    region          VARCHAR NOT NULL,           -- named Perth region or fallback
    has_rich_stats  BOOLEAN NOT NULL            -- true for the 26 affordability suburbs
);

-- [BUILT] Every raw spelling from every source table -> one suburb_key.
-- A single alias_raw string maps to exactly one suburb (by construction:
-- it normalizes to one suburb_key_str, which maps to one suburb_key),
-- so alias_raw alone is the primary key.
CREATE TABLE dim_suburb_alias (
    alias_raw     VARCHAR PRIMARY KEY,          -- e.g. 'Maylands', 'MAYLANDS', 'Maylands '
    source_table  VARCHAR NOT NULL,             -- which of the 12 source tables this came from
    suburb_key    INTEGER NOT NULL REFERENCES dim_suburb(suburb_key)
);

-- [BUILT] One row per calendar month across the date range in the time-series tables
CREATE TABLE dim_month (
    month_key    VARCHAR PRIMARY KEY,           -- 'YYYY-MM', e.g. '2023-04'
    year         INTEGER NOT NULL,
    month_num    INTEGER NOT NULL,              -- 1-12
    quarter      INTEGER NOT NULL,              -- 1-4
    month_label  VARCHAR NOT NULL               -- e.g. 'Apr 2023', for chart axes
);


-- =============================================================================
-- PHASE 1 FACTS — what get_all_suburbs_data() / get_rent_trend_for() will read
-- =============================================================================

-- [PHASE 1, step C] Grain: one row per suburb per month.
-- median_weekly_rent is averaged across alias-variant rows that reported
-- that month (the fix for the Maylands casing-variant trend inconsistency).
CREATE TABLE fact_rent_trend (
    suburb_key           INTEGER NOT NULL REFERENCES dim_suburb(suburb_key),
    month_key            VARCHAR NOT NULL REFERENCES dim_month(month_key),
    median_weekly_rent   DOUBLE,
    PRIMARY KEY (suburb_key, month_key)
);

-- [PHASE 1, step D] Grain: one row per suburb (current snapshot, SCD Type 1).
-- Populated for all ~26 has_rich_stats=true suburbs; mostly NULL elsewhere.
-- census_median_hhd_income is best-effort SA2-name match — expect mostly NULL.
CREATE TABLE fact_suburb_profile (
    suburb_key                INTEGER PRIMARY KEY REFERENCES dim_suburb(suburb_key),
    median_rent_2br           DOUBLE,           -- affordability
    median_rent_3br           DOUBLE,           -- affordability
    total_tenancies           INTEGER,          -- affordability
    avg_tenancy_years         DOUBLE,           -- suburb_stats
    dispute_rate_pct          DOUBLE,           -- suburb_stats
    disadvantage_category     VARCHAR,          -- affordability
    irsd_decile               INTEGER,          -- affordability
    rent_to_income_ratio      DOUBLE,           -- affordability
    ato_median_income         DOUBLE,           -- ato_income
    seifa_decile              INTEGER,          -- seifa
    census_median_hhd_income  DOUBLE            -- census_g02, best-effort, mostly NULL
);

-- [PHASE 1, step E] Grain: one row per suburb (current snapshot).
-- Populated wherever dim_suburb.postcode is known (~467 of 1,163).
-- safety_score/district/* are district-level (see crime data discussion) —
-- multiple suburbs in the same district will share identical values.
CREATE TABLE fact_suburb_amenities (
    suburb_key        INTEGER PRIMARY KEY REFERENCES dim_suburb(suburb_key),
    school_total      INTEGER,                  -- schools
    primary_schools   INTEGER,                  -- schools
    secondary_schools INTEGER,                  -- schools
    nearest_station   VARCHAR,                  -- train_proximity
    distance_km       DOUBLE,                   -- train_proximity
    has_train_1km     BOOLEAN,                  -- train_proximity
    has_train_2km     BOOLEAN,                  -- train_proximity
    nearest_bus_stop  VARCHAR,                  -- bus_proximity (step B)
    bus_stops_1km     INTEGER,                  -- bus_proximity (step B)
    has_bus_1km       BOOLEAN,                  -- bus_proximity (step B)
    safety_score      DOUBLE,                   -- suburb_crime, district-level
    district          VARCHAR,                  -- suburb_crime
    burglary          INTEGER,                  -- suburb_crime
    vehicle_theft     INTEGER,                  -- suburb_crime
    assault           INTEGER,                  -- suburb_crime
    property_damage   INTEGER                   -- suburb_crime
);


-- =============================================================================
-- FUTURE FACTS — only built if the dashboard's "movers"/"bond market" pages
-- need transaction-level detail beyond fact_rent_trend / perth_monthly_trend
-- =============================================================================

-- [FUTURE] Grain: one row per suburb per month, aggregated from 246,005 rows
CREATE TABLE fact_bond_lodgement (
    suburb_key            INTEGER NOT NULL REFERENCES dim_suburb(suburb_key),
    month_key             VARCHAR NOT NULL REFERENCES dim_month(month_key),
    lodgement_count       INTEGER,
    median_weekly_rent    DOUBLE,
    avg_weekly_rent       DOUBLE,
    PRIMARY KEY (suburb_key, month_key)
);

-- [FUTURE] Grain: one row per suburb per month, aggregated from 224,262 rows
-- (suburb derived via dim_suburb.postcode, since bond_disposals has no suburb column)
CREATE TABLE fact_bond_disposal (
    suburb_key             INTEGER NOT NULL REFERENCES dim_suburb(suburb_key),
    month_key              VARCHAR NOT NULL REFERENCES dim_month(month_key),
    disposal_count         INTEGER,
    avg_payment_to_tenant  DOUBLE,
    avg_payment_to_lessor  DOUBLE,
    avg_days_bond_held     DOUBLE,
    PRIMARY KEY (suburb_key, month_key)
);

-- [FUTURE] Grain: one row per month, citywide
CREATE TABLE fact_perth_trend (
    month_key      VARCHAR PRIMARY KEY REFERENCES dim_month(month_key),
    median_rent    DOUBLE,
    p25_rent       DOUBLE,
    p75_rent       DOUBLE,
    new_tenancies  INTEGER
);
