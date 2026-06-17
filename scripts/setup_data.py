"""
scripts/setup_data.py
One-time data setup script. Run this once and never again.

    uv run python scripts/setup_data.py

Downloads all required datasets, ingests them into DuckDB,
and rebuilds all analytics tables. Takes about 5 minutes.
"""

import os, sys, time, zipfile, shutil, requests, duckdb, pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DB_PATH  = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
HEADERS  = {"User-Agent": "Mozilla/5.0 (Perth Rental Finder — open data research)"}

# ── Colour output ──────────────────────────────────────────────────────────
def ok(msg):  print(f"  ✓ {msg}")
def err(msg): print(f"  ✗ {msg}")
def hdr(msg): print(f"\n{'─'*55}\n  {msg}\n{'─'*55}")
def info(msg):print(f"  → {msg}")

# ── Download helper ────────────────────────────────────────────────────────
def download(url, dest, description, timeout=60):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        ok(f"Already downloaded: {dest.name}")
        return True
    info(f"Downloading {description}...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        size = dest.stat().st_size / 1024
        if size < 1:
            dest.unlink(missing_ok=True)
            err(f"File too small — download likely failed")
            return False
        ok(f"Saved {dest.name} ({size:.0f} KB)")
        return True
    except requests.exceptions.HTTPError as e:
        err(f"HTTP {e.response.status_code} — {url[:60]}")
        return False
    except Exception as e:
        err(f"Failed: {type(e).__name__}: {str(e)[:80]}")
        return False

def extract_zip(zip_path, dest_dir):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(dest_dir)
    ok(f"Extracted to {dest_dir}")

# ══════════════════════════════════════════════════════════════════════════
# STEP 1 — DOWNLOAD DATA
# ══════════════════════════════════════════════════════════════════════════

hdr("Step 1 of 3: Downloading data files")

results = {}

# 1. SEIFA 2021 — Postal Areas
results["seifa"] = download(
    "https://www.abs.gov.au/statistics/people/people-and-communities/"
    "socio-economic-indexes-areas-seifa-australia/2021/"
    "Postal%20Area%2C%20Indexes%2C%20SEIFA%202021.xlsx",
    DATA_DIR / "seifa" / "seifa_poa_2021.xlsx",
    "ABS SEIFA 2021 Postal Areas"
)

# 2. ATO Table 7D — try direct link first, fall back to manual
ato_dest = DATA_DIR / "ato" / "ato_table7d.xlsx"
if not ato_dest.exists():
    info("Trying ATO Table 7D download...")
    ato_urls = [
        "https://www.ato.gov.au/assets/0/104/2239/2363/2364/2365/7d19e4dc-3e2e-4a5f-8c1f-f8a4d1c2e123.xlsx",
        "https://data.gov.au/data/dataset/individual-sample-file-2022-23/resource/table7d/download",
    ]
    downloaded = False
    for url in ato_urls:
        if download(url, ato_dest, "ATO Table 7D income by postcode", timeout=30):
            downloaded = True
            break
    if not downloaded:
        err("ATO Table 7D could not be auto-downloaded.")
        print()
        print("  MANUAL STEP REQUIRED:")
        print("  1. Go to: https://www.ato.gov.au/about-ato/research-and-statistics/")
        print("            in-detail/taxation-statistics/taxation-statistics-2022-23/")
        print("  2. Find: Table 7D — Individuals by postcode")
        print("  3. Download the Excel file")
        print(f"  4. Save to: {ato_dest.absolute()}")
        print()
        input("  Press Enter when done (or Enter to skip)...")
    results["ato"] = ato_dest.exists()

# 3. ABS Census 2021 G02 WA SA2
census_dest = DATA_DIR / "census" / "2021Census_G02_WA_SA2.csv"
if not census_dest.exists():
    info("Trying ABS Census G02 download...")
    census_urls = [
        "https://www.abs.gov.au/census/find-census-data/datapacks/download/"
        "2021_GCP_SA2_for_WA_short-header.zip",
    ]
    census_zip = DATA_DIR / "census" / "census_wa_sa2.zip"
    downloaded = False
    for url in census_urls:
        if download(url, census_zip, "ABS Census 2021 WA SA2 datapack", timeout=120):
            try:
                # Extract only the G02 file
                with zipfile.ZipFile(census_zip, 'r') as z:
                    g02_files = [f for f in z.namelist() if 'G02' in f and f.endswith('.csv')]
                    if g02_files:
                        z.extract(g02_files[0], DATA_DIR / "census")
                        extracted = DATA_DIR / "census" / g02_files[0]
                        shutil.move(str(extracted), str(census_dest))
                        # Clean up nested dirs
                        for d in (DATA_DIR / "census").iterdir():
                            if d.is_dir(): shutil.rmtree(d)
                        ok(f"Extracted G02 census file")
                        downloaded = True
            except Exception as e:
                err(f"Extraction failed: {e}")
            break
    if not downloaded:
        err("Census G02 could not be auto-downloaded.")
        print()
        print("  MANUAL STEP REQUIRED:")
        print("  1. Go to: https://www.abs.gov.au/census/find-census-data/datapacks")
        print("  2. Choose: 2021 → General Community Profile → WA → SA2")
        print("  3. Extract the G02 CSV file")
        print(f"  4. Save to: {census_dest.absolute()}")
        print()
        input("  Press Enter when done (or Enter to skip)...")
    results["census"] = census_dest.exists()

# 4. Transperth GTFS
gtfs_dest = DATA_DIR / "gtfs" / "stops.txt"
if not gtfs_dest.exists():
    info("Trying Transperth GTFS download...")
    gtfs_zip = DATA_DIR / "gtfs" / "transperth_gtfs.zip"
    gtfs_urls = [
        "https://www.transperth.wa.gov.au/feeds/google_transit.zip",
        "https://realtime.transperth.info/SJP/gtfsrtrequest.aspx",
    ]
    downloaded = False
    for url in gtfs_urls:
        if download(url, gtfs_zip, "Transperth GTFS feed", timeout=60):
            try:
                extract_zip(gtfs_zip, DATA_DIR / "gtfs")
                downloaded = True
            except Exception as e:
                err(f"GTFS extraction failed: {e}")
            break
    results["gtfs"] = (DATA_DIR / "gtfs" / "stops.txt").exists()
    if not results["gtfs"]:
        info("GTFS unavailable — transport matching will use postcode estimates")
        results["gtfs"] = False
else:
    ok("GTFS already downloaded")
    results["gtfs"] = True

print()
print("  Download summary:")
for name, ok_val in results.items():
    print(f"    {'✓' if ok_val else '✗'} {name}")


# ══════════════════════════════════════════════════════════════════════════
# STEP 2 — INGEST INTO DUCKDB
# ══════════════════════════════════════════════════════════════════════════

hdr("Step 2 of 3: Loading data into database")

con = duckdb.connect(DB_PATH)

# ── SEIFA ──────────────────────────────────────────────────────────────────
def ingest_seifa():
    seifa_files = list((DATA_DIR/"seifa").glob("*.xlsx"))
    if not seifa_files:
        err("No SEIFA file found — skipping"); return
    f = seifa_files[0]
    info(f"Loading SEIFA from {f.name}...")
    loaded = False
    for sheet in ["Table 1", "Table 3", "Table 6", "Postal Area", 0, 1, 2]:
        try:
            df = pd.read_excel(f, sheet_name=sheet, dtype=str, header=None)
            # Find header row — look for row containing "POA" or "Postcode"
            header_row = None
            for i, row in df.iterrows():
                row_str = " ".join([str(v) for v in row.values if str(v) != 'nan'])
                if any(kw in row_str.upper() for kw in ["POA", "POSTCODE", "IRSD"]):
                    header_row = i
                    break
            if header_row is None:
                continue
            df = pd.read_excel(f, sheet_name=sheet, header=header_row, dtype=str)
            df.columns = [str(c).strip().upper().replace(" ","_") for c in df.columns]
            # Find postcode column
            pc_col = next((c for c in df.columns if "POA" in c or "POSTCODE" in c or "POSTAL" in c), None)
            irsd_score_col = next((c for c in df.columns if "IRSD" in c and "SCORE" in c), None)
            irsd_decile_col = next((c for c in df.columns if "IRSD" in c and "DECILE" in c), None)
            name_col = next((c for c in df.columns if "NAME" in c), None)
            if not pc_col or not irsd_decile_col:
                continue
            df = df.rename(columns={
                pc_col: "POSTCODE",
                **({irsd_score_col: "IRSD_SCORE"} if irsd_score_col else {}),
                **({irsd_decile_col: "IRSD_DECILE"} if irsd_decile_col else {}),
                **({name_col: "SUBURB_NAME"} if name_col else {}),
            })
            df["POSTCODE"] = df["POSTCODE"].astype(str).str.extract(r"(\d{4})")[0]
            df["IRSD_SCORE"] = pd.to_numeric(df.get("IRSD_SCORE"), errors="coerce")
            df["IRSD_DECILE"] = pd.to_numeric(df.get("IRSD_DECILE"), errors="coerce")
            if "SUBURB_NAME" not in df.columns:
                df["SUBURB_NAME"] = df["POSTCODE"]
            # Filter WA postcodes
            df = df[df["POSTCODE"].str.match(r"^6\d{3}$", na=False)].copy()
            df = df[df["IRSD_DECILE"].notna()].copy()
            if len(df) < 10:
                continue
            con.execute("DROP TABLE IF EXISTS seifa")
            con.execute("""
                CREATE TABLE seifa AS
                SELECT POSTCODE, SUBURB_NAME, IRSD_SCORE, IRSD_DECILE FROM df
            """)
            count = con.execute("SELECT COUNT(*) FROM seifa").fetchone()[0]
            ok(f"SEIFA: {count:,} WA postcodes loaded (sheet: {sheet})")
            loaded = True
            break
        except Exception as e:
            continue
    if not loaded:
        err("Could not parse SEIFA file — SEIFA data will be missing")

ingest_seifa()

# ── ATO ────────────────────────────────────────────────────────────────────
def ingest_ato():
    ato_files = list((DATA_DIR/"ato").glob("*.xlsx"))
    if not ato_files:
        err("No ATO file found — skipping"); return
    f = ato_files[0]
    info(f"Loading ATO from {f.name}...")
    loaded = False
    for sheet in [0, 1, "Table 7D", "7D", "Individuals"]:
        try:
            df = pd.read_excel(f, sheet_name=sheet, dtype=str, header=None)
            # Find header row
            header_row = None
            for i, row in df.iterrows():
                row_str = " ".join([str(v) for v in row.values if str(v) != 'nan'])
                if "POSTCODE" in row_str.upper() or "TAXABLE" in row_str.upper():
                    header_row = i
                    break
            if header_row is None:
                continue
            df = pd.read_excel(f, sheet_name=sheet, header=header_row, dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            pc_col    = next((c for c in df.columns if "postcode" in c.lower()), None)
            med_col   = next((c for c in df.columns if "median" in c.lower() and ("income" in c.lower() or "taxable" in c.lower())), None)
            avg_col   = next((c for c in df.columns if "average" in c.lower() and ("income" in c.lower() or "taxable" in c.lower())), None)
            if not pc_col or not med_col:
                continue
            df = df.rename(columns={
                pc_col:  "Postcode",
                med_col: "Median_taxable_income",
                **({avg_col: "Average_taxable_income"} if avg_col else {}),
            })
            if "Average_taxable_income" not in df.columns:
                df["Average_taxable_income"] = df["Median_taxable_income"]
            df["Postcode"] = df["Postcode"].astype(str).str.extract(r"(\d{4})")[0]
            df["Median_taxable_income"]  = pd.to_numeric(df["Median_taxable_income"],  errors="coerce")
            df["Average_taxable_income"] = pd.to_numeric(df["Average_taxable_income"], errors="coerce")
            df = df[df["Postcode"].str.match(r"^6\d{3}$", na=False)].copy()
            df = df[df["Median_taxable_income"].notna()].copy()
            if len(df) < 10:
                continue
            df["Suburb"] = df["Postcode"]
            con.execute("DROP TABLE IF EXISTS ato_income")
            con.execute("""
                CREATE TABLE ato_income AS
                SELECT Postcode as postcode, Suburb as suburb,
                       CAST(Median_taxable_income AS DOUBLE) as median_taxable_income,
                       CAST(Average_taxable_income AS DOUBLE) as avg_taxable_income
                FROM df WHERE Postcode IS NOT NULL
            """)
            count = con.execute("SELECT COUNT(*) FROM ato_income").fetchone()[0]
            ok(f"ATO income: {count:,} WA postcodes loaded")
            loaded = True
            break
        except Exception as e:
            continue
    if not loaded:
        err("Could not parse ATO file — income data will be missing")

ingest_ato()

# ── Census G02 ─────────────────────────────────────────────────────────────
def ingest_census():
    census_files = list((DATA_DIR/"census").glob("*G02*.csv"))
    if not census_files:
        err("No Census G02 file found — skipping"); return
    f = census_files[0]
    info(f"Loading Census G02 from {f.name}...")
    try:
        df = pd.read_csv(f, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        # Handle two-row header (ABS uses description row below header)
        if df.iloc[0].astype(str).str.contains("Median|Average", case=False, regex=True).any():
            df = df.iloc[1:].reset_index(drop=True)
        hhd_col  = next((c for c in df.columns if "hhd_inc" in c.lower() or "household_income" in c.lower()), None)
        rent_col = next((c for c in df.columns if "rent_weekly" in c.lower()), None)
        sa2_col  = next((c for c in df.columns if "SA2_CODE" in c.upper()), None)
        name_col = next((c for c in df.columns if "SA2_NAME" in c.upper()), None)
        hh_size  = next((c for c in df.columns if "household_size" in c.lower() or "avg_hh" in c.lower()), None)
        if not sa2_col:
            err("Census G02: no SA2_CODE column found — skipping"); return
        df[hhd_col or "income"]  = pd.to_numeric(df.get(hhd_col, pd.Series()), errors="coerce")
        df[rent_col or "rent"]   = pd.to_numeric(df.get(rent_col, pd.Series()), errors="coerce")
        df[hh_size or "hhsize"]  = pd.to_numeric(df.get(hh_size, pd.Series()), errors="coerce")
        con.execute("DROP TABLE IF EXISTS census_g02")
        con.execute(f"""
            CREATE TABLE census_g02 AS
            SELECT
                {sa2_col} AS SA2_CODE_2021,
                {f'"{name_col}" AS SA2_NAME_2021,' if name_col else '"" AS SA2_NAME_2021,'}
                CAST({f'"{hhd_col}"' if hhd_col else 'NULL'} AS DOUBLE) AS median_hhd_income_weekly,
                CAST({f'"{rent_col}"' if rent_col else 'NULL'} AS DOUBLE) AS median_rent_weekly_census,
                CAST({f'"{hh_size}"' if hh_size else 'NULL'} AS DOUBLE) AS avg_household_size
            FROM df WHERE {sa2_col} IS NOT NULL
        """)
        count = con.execute("SELECT COUNT(*) FROM census_g02").fetchone()[0]
        ok(f"Census G02: {count:,} SA2 areas loaded")
    except Exception as e:
        err(f"Census G02 failed: {e}")

ingest_census()

# ── GTFS train stops ───────────────────────────────────────────────────────
def ingest_gtfs():
    stops_file = DATA_DIR / "gtfs" / "stops.txt"
    routes_file = DATA_DIR / "gtfs" / "routes.txt"
    if not stops_file.exists():
        info("No GTFS stops.txt — transport data unavailable")
        return
    info("Loading Transperth GTFS stops...")
    try:
        stops = pd.read_csv(stops_file)
        # Filter to train stations if routes available
        try:
            routes = pd.read_csv(routes_file)
            rail_routes = routes[routes.get("route_type", pd.Series()).astype(str) == "2"]
            if len(rail_routes) > 0:
                trips = pd.read_csv(DATA_DIR/"gtfs"/"trips.txt")
                stoptimes = pd.read_csv(DATA_DIR/"gtfs"/"stop_times.txt", usecols=["trip_id","stop_id"])
                rail_trip_ids = trips[trips["route_id"].isin(rail_routes["route_id"])]["trip_id"]
                rail_stop_ids = stoptimes[stoptimes["trip_id"].isin(rail_trip_ids)]["stop_id"].unique()
                train_stops = stops[stops["stop_id"].isin(rail_stop_ids)][["stop_id","stop_name","stop_lat","stop_lon"]]
                con.execute("DROP TABLE IF EXISTS train_stations")
                con.execute("CREATE TABLE train_stations AS SELECT * FROM train_stops")
                ok(f"GTFS: {len(train_stops):,} train stations loaded")
                return
        except Exception:
            pass
        # Fallback: all stops
        all_stops = stops[["stop_id","stop_name","stop_lat","stop_lon"]].dropna()
        con.execute("DROP TABLE IF EXISTS train_stations")
        con.execute("CREATE TABLE train_stations AS SELECT * FROM all_stops")
        ok(f"GTFS: {len(all_stops):,} stops loaded (all modes)")
    except Exception as e:
        err(f"GTFS loading failed: {e}")

ingest_gtfs()


# ══════════════════════════════════════════════════════════════════════════
# STEP 3 — REBUILD ANALYTICS TABLES
# ══════════════════════════════════════════════════════════════════════════

hdr("Step 3 of 3: Rebuilding analytics tables")

# suburb_overall_rent
info("Building suburb_overall_rent...")
con.execute("""
    CREATE OR REPLACE TABLE suburb_overall_rent AS
    SELECT SUBURB as suburb, POSTCODE as postcode,
           COUNT(*) as total_tenancies,
           MEDIAN(WEEKLY_RENT) as median_weekly_rent_all,
           MEDIAN(CASE WHEN BEDROOMS=2 THEN WEEKLY_RENT END) as median_rent_2br,
           MEDIAN(CASE WHEN BEDROOMS=3 THEN WEEKLY_RENT END) as median_rent_3br,
           COUNT(CASE WHEN DWELLING_TYPE IN ('Unit','Apartment') THEN 1 END) as unit_count,
           COUNT(CASE WHEN DWELLING_TYPE='House' THEN 1 END) as house_count
    FROM rental_bonds WHERE SUBURB IS NOT NULL
    GROUP BY suburb, postcode
""")
ok(f"suburb_overall_rent: {con.execute('SELECT COUNT(*) FROM suburb_overall_rent').fetchone()[0]:,} suburbs")

# rent_trend (no BEDROOMS grouping)
info("Building rent_trend...")
con.execute("""
    CREATE OR REPLACE TABLE rent_trend AS
    SELECT SUBURB as suburb, POSTCODE as postcode, LODGEMENT_MONTH as month,
           COUNT(*) as tenancy_count,
           MEDIAN(WEEKLY_RENT) as median_weekly_rent,
           AVG(WEEKLY_RENT) as avg_weekly_rent
    FROM rental_bonds
    WHERE SUBURB IS NOT NULL AND LODGEMENT_MONTH IS NOT NULL
      AND WEEKLY_RENT BETWEEN 100 AND 5000
    GROUP BY suburb, postcode, month ORDER BY suburb, month
""")
ok(f"rent_trend: {con.execute('SELECT COUNT(*) FROM rent_trend').fetchone()[0]:,} rows")

# perth_monthly_trend
info("Building perth_monthly_trend...")
con.execute("""
    CREATE OR REPLACE TABLE perth_monthly_trend AS
    SELECT LODGEMENT_MONTH as month, COUNT(*) as new_tenancies,
           ROUND(MEDIAN(WEEKLY_RENT)) as median_rent,
           ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY WEEKLY_RENT)) as p25_rent,
           ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY WEEKLY_RENT)) as p75_rent,
           ROUND(MIN(WEEKLY_RENT)) as min_rent, ROUND(MAX(WEEKLY_RENT)) as max_rent
    FROM rental_bonds
    WHERE LODGEMENT_MONTH IS NOT NULL AND WEEKLY_RENT BETWEEN 100 AND 5000
    GROUP BY LODGEMENT_MONTH ORDER BY LODGEMENT_MONTH
""")
ok(f"perth_monthly_trend: {con.execute('SELECT COUNT(*) FROM perth_monthly_trend').fetchone()[0]} months")

# tenancy_duration
info("Building tenancy_duration...")
con.execute("""
    CREATE OR REPLACE TABLE tenancy_duration AS
    SELECT l.SUBURB as suburb, l.POSTCODE as postcode,
           COUNT(*) as total_bonds_ended,
           ROUND(MEDIAN(d.DAYS_BOND_HELD)) as median_days_held,
           ROUND(MEDIAN(d.DAYS_BOND_HELD)/365.0,1) as median_years_held,
           ROUND(100.0*SUM(CASE WHEN d.PAYMENT_TO_TENANT>0 THEN 1 ELSE 0 END)/COUNT(*),1) as dispute_rate_pct
    FROM bond_disposals d
    JOIN (SELECT DISTINCT POSTCODE, SUBURB FROM rental_bonds) l ON d.POSTCODE=l.POSTCODE
    WHERE d.DAYS_BOND_HELD>0 GROUP BY l.SUBURB,l.POSTCODE HAVING COUNT(*)>=10
""")
ok(f"tenancy_duration: {con.execute('SELECT COUNT(*) FROM tenancy_duration').fetchone()[0]:,} suburbs")

# suburb_stats
info("Building suburb_stats...")
con.execute("""
    CREATE OR REPLACE TABLE suburb_stats AS
    SELECT r.suburb, r.postcode,
           r.unit_count as total_tenancies,
           r.median_weekly_rent_all as median_rent,
           r.median_rent_2br as affordable_rent,
           r.median_rent_3br as expensive_rent,
           COALESCE(d.median_years_held,1.0) as avg_tenancy_years,
           COALESCE(d.dispute_rate_pct,0) as dispute_rate_pct
    FROM suburb_overall_rent r
    LEFT JOIN tenancy_duration d ON UPPER(r.suburb)=UPPER(d.suburb)
    ORDER BY r.unit_count DESC
""")
ok(f"suburb_stats: {con.execute('SELECT COUNT(*) FROM suburb_stats').fetchone()[0]:,} suburbs")

# affordability
info("Building affordability...")
con.execute("""
    CREATE OR REPLACE TABLE affordability AS
    SELECT r.suburb, r.postcode,
           r.median_weekly_rent_all AS median_weekly_rent,
           r.median_rent_2br, r.median_rent_3br, r.total_tenancies,
           a.median_taxable_income AS median_annual_income,
           a.median_taxable_income/52.0 AS median_weekly_income,
           CASE WHEN a.median_taxable_income>0
                THEN (r.median_weekly_rent_all*52.0)/a.median_taxable_income
                ELSE NULL END AS rent_to_income_ratio,
           CASE WHEN a.median_taxable_income>0
                THEN ((r.median_weekly_rent_all*52.0)/a.median_taxable_income)>0.30
                ELSE NULL END AS in_rental_stress,
           s.IRSD_SCORE, s.IRSD_DECILE,
           CASE WHEN s.IRSD_DECILE<=3 THEN 'High disadvantage'
                WHEN s.IRSD_DECILE<=6 THEN 'Moderate disadvantage'
                WHEN s.IRSD_DECILE<=8 THEN 'Low disadvantage'
                ELSE 'Advantaged' END AS disadvantage_category,
           CASE WHEN s.IRSD_DECILE IS NOT NULL AND a.median_taxable_income>0
                THEN LEAST((r.median_weekly_rent_all*52.0)/a.median_taxable_income/0.6,1.0)*0.5
                     +((10-s.IRSD_DECILE)/9.0)*0.5
                ELSE NULL END AS vulnerability_score
    FROM suburb_overall_rent r
    LEFT JOIN ato_income a ON r.postcode=a.postcode
    LEFT JOIN seifa s      ON r.postcode=s.POSTCODE
    WHERE r.median_weekly_rent_all IS NOT NULL
""")
n=con.execute("SELECT COUNT(*) FROM affordability").fetchone()[0]
seifa_n=con.execute("SELECT COUNT(*) FROM affordability WHERE IRSD_DECILE IS NOT NULL").fetchone()[0]
ok(f"affordability: {n:,} suburbs · {seifa_n:,} with SEIFA ({seifa_n/n*100:.0f}%)")

# stress_hotspots
con.execute("""
    CREATE OR REPLACE VIEW stress_hotspots AS
    SELECT suburb, postcode, median_weekly_rent,
           ROUND(rent_to_income_ratio*100,1) AS rent_pct_of_income,
           IRSD_DECILE, disadvantage_category,
           ROUND(vulnerability_score*100,1) AS vulnerability_score_pct
    FROM affordability
    WHERE in_rental_stress=true AND IRSD_DECILE IS NOT NULL
    ORDER BY vulnerability_score DESC
""")
ok(f"stress_hotspots: {con.execute('SELECT COUNT(*) FROM stress_hotspots').fetchone()[0]:,} suburbs")

con.close()

# ── Final summary ──────────────────────────────────────────────────────────
hdr("Setup complete")
con2 = duckdb.connect(DB_PATH, read_only=True)
print("\n  Database tables:")
for (t,) in con2.execute("SHOW TABLES").fetchall():
    count = con2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"    {t:<30} {count:>8,} rows")

# Check SEIFA coverage
aff = con2.execute("SELECT COUNT(*) as t, SUM(CASE WHEN IRSD_DECILE IS NOT NULL THEN 1 ELSE 0 END) as s FROM affordability").fetchone()
print(f"\n  SEIFA coverage: {aff[1]}/{aff[0]} suburbs ({aff[1]/aff[0]*100:.0f}%)")

ato_n = con2.execute("SELECT COUNT(*) FROM ato_income").fetchone()[0]
print(f"  ATO coverage:   {ato_n} postcodes")

con2.close()

print("""
  ✓ Data setup complete. You never need to run this again.

  Now restart the app:
    uv run streamlit run app.py
""")
