"""
fix_bonds.py — Re-ingests all rental bond data from the ZIP file.
Run: uv run python scripts/fix_bonds.py
"""

import duckdb, pandas as pd, zipfile, os

ZIP_PATH = "data/wa-rental-bond-may2026.zip"
DB_PATH  = "data/rental.duckdb"

print("Checking ZIP file...")
if not os.path.exists(ZIP_PATH):
    print(f"ERROR: ZIP not found at {ZIP_PATH}")
    print("Files in data/:", os.listdir("data"))
    exit(1)

con = duckdb.connect(DB_PATH)

with zipfile.ZipFile(ZIP_PATH) as z:
    all_files = z.namelist()
    lodge_files = [f for f in all_files if "Lodge" in f and f.endswith(".csv") and "__MACOSX" not in f]
    print(f"Found {len(lodge_files)} lodgement files")

    dfs = []
    for fname in lodge_files:
        with z.open(fname) as f:
            df = pd.read_csv(f)
            df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

            # Rename columns to standard names
            rename = {}
            for col in df.columns:
                if "RENT" in col and "AMOUNT" in col: rename[col] = "WEEKLY_RENT"
                elif "RENT" in col and col != "WEEKLY_RENT": rename[col] = "WEEKLY_RENT"
                elif "LOCALITY" in col or "SUBURB" in col: rename[col] = "SUBURB"
                elif "LODGEMENT" in col and "DATE" in col: rename[col] = "LODGEMENT_DATE"
            df = df.rename(columns=rename)

            # Parse month from date
            if "LODGEMENT_DATE" in df.columns:
                df["LODGEMENT_MONTH"] = pd.to_datetime(
                    df["LODGEMENT_DATE"], dayfirst=True, errors="coerce"
                ).dt.to_period("M").astype(str)
            elif "LODGEMENT_MONTH" not in df.columns:
                df["LODGEMENT_MONTH"] = None

            if "WEEKLY_RENT" not in df.columns:
                print(f"  Skipping {fname} — no rent column. Columns: {df.columns.tolist()}")
                continue

            # Clean
            df["POSTCODE"] = df["POSTCODE"].astype(str).str.strip().str.zfill(4)
            df = df[df["POSTCODE"].str.match(r"^6\d{3}$", na=False)]
            df["WEEKLY_RENT"] = pd.to_numeric(df["WEEKLY_RENT"], errors="coerce")
            df = df[df["WEEKLY_RENT"].between(100, 5000)]
            df = df.dropna(subset=["SUBURB", "WEEKLY_RENT"])

            dfs.append(df)
            yr = fname.split("/")[-1]
            print(f"  {yr}: {len(df):,} records, months {df['LODGEMENT_MONTH'].min()} to {df['LODGEMENT_MONTH'].max()}")

if not dfs:
    print("ERROR: No data loaded")
    exit(1)

bonds = pd.concat(dfs, ignore_index=True)
print(f"\nTotal records: {len(bonds):,}")
print(f"Date range: {bonds['LODGEMENT_MONTH'].min()} to {bonds['LODGEMENT_MONTH'].max()}")

con.execute("DROP TABLE IF EXISTS rental_bonds")
con.execute("CREATE TABLE rental_bonds AS SELECT * FROM bonds")

result = con.execute("SELECT MIN(LODGEMENT_MONTH), MAX(LODGEMENT_MONTH), COUNT(*) FROM rental_bonds").fetchone()
print(f"\nDatabase: {result[0]} to {result[1]}, {result[2]:,} records")

# Rebuild rent_trend
print("\nRebuilding rent_trend...")
con.execute("""
    CREATE OR REPLACE TABLE rent_trend AS
    SELECT SUBURB as suburb, POSTCODE as postcode, LODGEMENT_MONTH as month,
           COUNT(*) as tenancy_count,
           MEDIAN(WEEKLY_RENT) as median_weekly_rent,
           AVG(WEEKLY_RENT) as avg_weekly_rent
    FROM rental_bonds
    WHERE SUBURB IS NOT NULL AND LODGEMENT_MONTH IS NOT NULL
    GROUP BY suburb, postcode, month
    ORDER BY suburb, month
""")
rt = con.execute("SELECT MIN(month), MAX(month), COUNT(*) FROM rent_trend").fetchone()
print(f"rent_trend: {rt[0]} to {rt[1]}, {rt[2]:,} rows")

# Rebuild perth_monthly_trend
print("Rebuilding perth_monthly_trend...")
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
pm = con.execute("SELECT MIN(month), MAX(month), COUNT(*) FROM perth_monthly_trend").fetchone()
print(f"perth_monthly_trend: {pm[0]} to {pm[1]}, {pm[2]} months")

con.close()
print("\nDone. Restart the app.")
