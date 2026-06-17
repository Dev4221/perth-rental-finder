"""
build_fact_suburb_amenities.py — Phase 1, step E

Builds fact_suburb_amenities: one row per suburb_key (current snapshot),
populated wherever dim_suburb.postcode is known (~1,200 of 1,222 per step A).

All joins go through dim_suburb.postcode directly — step A already chose
that postcode preferring the 'schools' table when available, and
train_proximity/bus_proximity/suburb_crime are all keyed by that same
school-derived postcode universe (load_transport_crime.py and
load_bus_proximity.py both compute postcode centroids from 'schools').

Columns:
  school_total, primary_schools, secondary_schools  <- schools, aggregated by postcode
  nearest_station, distance_km, has_train_1km/2km   <- train_proximity
  nearest_bus_stop, bus_stops_1km, has_bus_1km      <- bus_proximity (step B —
                                                         optional; NULL if not yet built)
  safety_score, district, burglary, vehicle_theft,
  assault, property_damage                          <- suburb_crime (district-level,
                                                         see earlier discussion)

Depends on: dim_suburb (step A), schools, train_proximity, suburb_crime.
bus_proximity (step B) is optional — if missing, bus columns are NULL and a
note is printed, but the build still completes.

Run: uv run python build_fact_suburb_amenities.py
(stop the FastAPI server first — same read-write reasoning as steps A-D)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
conn = duckdb.connect(DB_PATH)

tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
missing = [t for t in ["dim_suburb", "schools", "train_proximity", "suburb_crime"] if t not in tables]
if missing:
    print(f"ERROR: required table(s) missing: {missing}")
    print("If dim_suburb is missing, run build_dim_suburb.py first (step A).")
    sys.exit(1)

has_bus = "bus_proximity" in tables
print("=" * 70)
print("Building fact_suburb_amenities")
print("=" * 70)
if not has_bus:
    print("NOTE: bus_proximity not found — bus columns will be NULL. "
          "Run load_bus_proximity.py (step B) and re-run this script to add them.")

bus_cols_select = (
    "bp.nearest_bus_stop, bp.bus_stops_1km, bp.has_bus_1km"
    if has_bus else
    "CAST(NULL AS VARCHAR) as nearest_bus_stop, CAST(NULL AS INTEGER) as bus_stops_1km, "
    "CAST(NULL AS BOOLEAN) as has_bus_1km"
)
bus_join = "LEFT JOIN bus_proximity bp ON bp.postcode = d.postcode" if has_bus else ""

conn.execute("DROP TABLE IF EXISTS fact_suburb_amenities")
conn.execute(f"""
    CREATE TABLE fact_suburb_amenities AS
    WITH school_agg AS (
        SELECT postcode, COUNT(*) as total,
               SUM(CASE WHEN school_type='Primary' THEN 1 ELSE 0 END) as primary_schools,
               SUM(CASE WHEN school_type='Secondary' THEN 1 ELSE 0 END) as secondary_schools
        FROM schools GROUP BY postcode
    )
    SELECT
        d.suburb_key,
        sa.total as school_total,
        sa.primary_schools,
        sa.secondary_schools,
        tp.nearest_station,
        tp.distance_km,
        tp.has_train_1km,
        tp.has_train_2km,
        {bus_cols_select},
        sc.safety_score,
        sc.district,
        sc.burglary,
        sc.vehicle_theft,
        sc.assault,
        sc.property_damage
    FROM dim_suburb d
    LEFT JOIN school_agg sa ON sa.postcode = d.postcode
    LEFT JOIN train_proximity tp ON tp.postcode = d.postcode
    {bus_join}
    LEFT JOIN suburb_crime sc ON sc.postcode = d.postcode
""")

n_total = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities").fetchone()[0]
n_with_postcode = conn.execute("SELECT COUNT(*) FROM dim_suburb WHERE postcode IS NOT NULL").fetchone()[0]
n_with_schools = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE school_total IS NOT NULL").fetchone()[0]
n_with_train = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE nearest_station IS NOT NULL").fetchone()[0]
n_with_crime = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE safety_score IS NOT NULL").fetchone()[0]
n_with_bus = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE bus_stops_1km IS NOT NULL").fetchone()[0]

print(f"\nfact_suburb_amenities: {n_total} rows written (one per dim_suburb row)")
print(f"  dim_suburb rows with a postcode: {n_with_postcode}")
print(f"  rows with school data:  {n_with_schools}")
print(f"  rows with train data:   {n_with_train}")
print(f"  rows with bus data:     {n_with_bus}" + ("" if has_bus else " (bus_proximity not built yet)"))
print(f"  rows with crime data:   {n_with_crime} "
      f"(suburb_crime is small — low number here is expected)")

# -----------------------------------------------------------------------
# Validation: Maylands (train, no rich stats) / Murdoch (train+crime+rich) /
# a suburb with no postcode at all
# -----------------------------------------------------------------------
print("\n" + "=" * 70)
print("VALIDATION: Maylands / Murdoch")
print("=" * 70)
sample = conn.execute("""
    SELECT s.suburb_name, s.postcode, a.school_total, a.primary_schools, a.secondary_schools,
           a.nearest_station, a.distance_km, a.has_train_1km, a.has_train_2km,
           a.nearest_bus_stop, a.bus_stops_1km,
           a.safety_score, a.district
    FROM fact_suburb_amenities a
    JOIN dim_suburb s ON s.suburb_key = a.suburb_key
    WHERE UPPER(s.suburb_name) IN ('MAYLANDS','MURDOCH')
    ORDER BY s.suburb_name
""").fetchdf()
print(sample.to_string(index=False))

print("\n" + "=" * 70)
print("VALIDATION: a suburb with no postcode (all amenity columns should be NULL)")
print("=" * 70)
no_pc = conn.execute("""
    SELECT s.suburb_name, a.school_total, a.nearest_station, a.safety_score
    FROM fact_suburb_amenities a
    JOIN dim_suburb s ON s.suburb_key = a.suburb_key
    WHERE s.postcode IS NULL
    LIMIT 3
""").fetchdf()
print(no_pc.to_string(index=False) if not no_pc.empty else "(no suburbs without a postcode)")

print("\n" + "=" * 70)
print("DONE. Paste this entire output back.")
print("=" * 70)
