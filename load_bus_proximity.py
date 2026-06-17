"""
scripts/load_bus_proximity.py
Loads bus stop proximity from the Transperth GTFS feed already used for
train_proximity (data/gtfs/google_transit.zip) — no new download needed.

Computes, per postcode (using the same school-derived suburb centroids as
train_proximity):
  - nearest_bus_stop: name of the closest bus stop
  - distance_km: distance to it
  - bus_stops_1km: COUNT of distinct bus stops within 1km (coverage/density)
  - has_bus_1km: bus_stops_1km > 0

Note on what this measures: bus stops are dense, so "distance to nearest
stop" alone won't discriminate well — most suburbs will have one nearby.
bus_stops_1km is a better coverage signal. Neither captures service
frequency (how often a bus actually comes) — that needs GTFS
stop_times.txt/frequencies.txt, which this script does not process.

Run: uv run python scripts/load_bus_proximity.py
"""
import zipfile, math
import pandas as pd
import numpy as np
import duckdb
from pathlib import Path

import os
DB = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
GTFS = "data/gtfs/google_transit.zip"

con = duckdb.connect(DB)

if not Path(GTFS).exists():
    print(f"GTFS not found at {GTFS} — skipping")
    con.close()
    raise SystemExit(0)

print("Loading Transperth bus stops...")
with zipfile.ZipFile(GTFS) as z:
    with z.open("stops.txt") as f:
        stops = pd.read_csv(f)
stops.columns = [c.strip() for c in stops.columns]

if "supported_modes" not in stops.columns:
    print("WARNING: 'supported_modes' column not found in stops.txt — "
          "cannot filter by mode. Columns available: " + ", ".join(stops.columns))
    con.close()
    raise SystemExit(1)

bus_stops = stops[stops["supported_modes"].str.strip().str.contains("Bus", na=False)].copy()
bus_stops = bus_stops.dropna(subset=["stop_lat", "stop_lon"])
print(f"Bus stops found: {len(bus_stops)} (of {len(stops)} total stops in feed)")

if bus_stops.empty:
    print("No bus stops matched — check the 'supported_modes' values:")
    print(stops["supported_modes"].value_counts().head(10).to_string())
    con.close()
    raise SystemExit(1)

# Same suburb centroids as train_proximity, for a consistent join key
suburb_centroids = con.execute("""
    SELECT postcode, AVG(latitude) as lat, AVG(longitude) as lon
    FROM schools WHERE latitude IS NOT NULL GROUP BY postcode
""").fetchdf()
print(f"Suburb (postcode) centroids: {len(suburb_centroids)}")

bus_lat = np.radians(bus_stops["stop_lat"].to_numpy())
bus_lon = np.radians(bus_stops["stop_lon"].to_numpy())
bus_names = bus_stops["stop_name"].to_numpy()
R = 6371.0  # Earth radius, km

def haversine_to_all(lat1_deg, lon1_deg):
    """Vectorized distance (km) from one point to every bus stop."""
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    dlat = bus_lat - lat1
    dlon = bus_lon - lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(lat1) * np.cos(bus_lat) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

results = []
for _, sub in suburb_centroids.iterrows():
    dists = haversine_to_all(sub["lat"], sub["lon"])
    nearest_idx = int(np.argmin(dists))
    results.append({
        "postcode": sub["postcode"],
        "nearest_bus_stop": str(bus_names[nearest_idx]),
        "distance_km": round(float(dists[nearest_idx]), 2),
        "bus_stops_1km": int(np.sum(dists <= 1.0)),
        "has_bus_1km": bool(np.any(dists <= 1.0)),
    })

prox = pd.DataFrame(results)
con.execute("DROP TABLE IF EXISTS bus_proximity")
con.register("prox_df", prox)
con.execute("CREATE TABLE bus_proximity AS SELECT * FROM prox_df")
con.unregister("prox_df")

print(f"\nbus_proximity: {len(prox)} postcodes")
print(f"  median nearest-stop distance: {prox['distance_km'].median():.2f} km")
print(f"  median stops within 1km: {prox['bus_stops_1km'].median():.0f}")
print(f"  postcodes with zero bus stops within 1km: {(prox['bus_stops_1km']==0).sum()}")
print("\nSample:")
print(prox.sort_values('bus_stops_1km', ascending=False).head(5).to_string(index=False))
print(prox.sort_values('bus_stops_1km').head(5).to_string(index=False))

con.close()
print("\nDone. Restart the app.")
