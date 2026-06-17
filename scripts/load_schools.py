"""
scripts/load_schools.py
Loads ACARA school data into the database.
Run: uv run python scripts/load_schools.py
"""
import openpyxl, duckdb, pandas as pd
from pathlib import Path

xlsx = Path("data/schools/SearchResults.xlsx")
if not xlsx.exists():
    print(f"ERROR: File not found at {xlsx}")
    exit(1)

print("Loading school data...")
wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
ws = wb['ASL Search Results']
rows = list(ws.iter_rows(values_only=True))
header = rows[1]
data = [r for r in rows[2:] if r[0] is not None]
df = pd.DataFrame(data, columns=header)
df = df[df['Status'] == 'Open'].copy()
df['Postcode'] = df['Postcode'].astype(str).str.zfill(4)
df['Latitude']  = pd.to_numeric(df['Latitude'],  errors='coerce')
df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
df = df[df['Postcode'].str.startswith('6')]

con = duckdb.connect("data/rental.duckdb")
con.execute("DROP TABLE IF EXISTS schools")
con.execute("""
    CREATE TABLE schools AS
    SELECT
        CAST("ACARA ID" AS VARCHAR) as acara_id,
        "School Name" as school_name,
        Suburb as suburb,
        Postcode as postcode,
        Type as school_type,
        Sector as sector,
        CAST(Latitude AS DOUBLE) as latitude,
        CAST(Longitude AS DOUBLE) as longitude
    FROM df
""")
count = con.execute("SELECT COUNT(*) FROM schools").fetchone()[0]
print(f"Loaded {count} WA schools")
print(con.execute("SELECT school_type, COUNT(*) as n FROM schools GROUP BY school_type ORDER BY n DESC").fetchdf().to_string())
con.close()
print("Done. Restart the app.")
