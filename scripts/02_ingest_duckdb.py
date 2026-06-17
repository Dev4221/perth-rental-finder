"""
scripts/02_ingest_duckdb.py
Step 2: Load all downloaded datasets into DuckDB.

Run: python scripts/02_ingest_duckdb.py
"""

import os
import sys
import glob
import pandas as pd
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")


def get_connection():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DB_PATH)


# ─────────────────────────────────────────────
# Table 1: rental_bonds
# ─────────────────────────────────────────────

def ingest_rental_bonds(con: duckdb.DuckDBPyConnection):
    print("\n── Ingesting rental bond data ──")

    bond_dir = DATA_DIR / "rental_bonds"
    csv_files = list(bond_dir.glob("*.csv"))

    if not csv_files:
        print("  ✗ No CSV files found in data/rental_bonds/")
        print("    Run: python scripts/01_download_data.py first")
        return

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype=str)
            # Normalise column names to uppercase
            df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]
            df["SOURCE_FILE"] = f.name
            dfs.append(df)
            print(f"  ✓ {f.name}: {len(df):,} rows")
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")

    if not dfs:
        return

    combined = pd.concat(dfs, ignore_index=True)

    # Standardise column names across different source formats
    rename_map = {
        "WEEKLY_RENT_AMOUNT": "WEEKLY_RENT",
        "RENT_AMOUNT": "WEEKLY_RENT",
        "PROPERTY_TYPE": "DWELLING_TYPE",
        "NUMBER_OF_BEDROOMS": "BEDROOMS",
        "BOND_LODGEMENT_DATE": "LODGEMENT_DATE",
    }
    combined.rename(columns={k: v for k, v in rename_map.items() if k in combined.columns}, inplace=True)

    # Ensure required columns exist
    required = ["SUBURB", "POSTCODE", "WEEKLY_RENT", "BEDROOMS", "LODGEMENT_DATE"]
    for col in required:
        if col not in combined.columns:
            combined[col] = None

    # Type conversions
    combined["WEEKLY_RENT"] = pd.to_numeric(combined["WEEKLY_RENT"], errors="coerce")
    combined["BEDROOMS"] = pd.to_numeric(combined["BEDROOMS"], errors="coerce").astype("Int64")
    combined["POSTCODE"] = combined["POSTCODE"].astype(str).str.strip().str.zfill(4)
    combined["LODGEMENT_DATE"] = pd.to_datetime(combined["LODGEMENT_DATE"], errors="coerce")
    combined["LODGEMENT_MONTH"] = combined["LODGEMENT_DATE"].dt.to_period("M").astype(str)

    # Filter Perth metro (6000–6999)
    combined = combined[combined["POSTCODE"].str.match(r"^6\d{3}$")].copy()

    # Drop obvious outliers
    combined = combined[combined["WEEKLY_RENT"].between(50, 5000)].copy()

    con.execute("DROP TABLE IF EXISTS rental_bonds")
    con.execute("""
        CREATE TABLE rental_bonds AS
        SELECT
            SUBURB,
            POSTCODE,
            COALESCE(DWELLING_TYPE, 'Unknown') AS DWELLING_TYPE,
            BEDROOMS,
            WEEKLY_RENT,
            COALESCE(TRY_CAST(BOND_AMOUNT AS DOUBLE), WEEKLY_RENT * 4) AS BOND_AMOUNT,
            TENANCY_LENGTH,
            LODGEMENT_DATE,
            LODGEMENT_MONTH,
            SOURCE_FILE
        FROM combined
        WHERE WEEKLY_RENT IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM rental_bonds").fetchone()[0]
    print(f"  ✓ rental_bonds table: {count:,} records")


# ─────────────────────────────────────────────
# Table 2: seifa
# ─────────────────────────────────────────────

def ingest_seifa(con: duckdb.DuckDBPyConnection):
    print("\n── Ingesting SEIFA data ──")

    seifa_dir = DATA_DIR / "seifa"
    xlsx_files = list(seifa_dir.glob("*.xlsx"))

    if not xlsx_files:
        print("  ✗ No XLSX files in data/seifa/ — run 01_download_data.py")
        return

    dfs = []
    for f in xlsx_files:
        # Try multiple sheet names used by ABS
        for sheet in ["Table 3", "Table 6", 0]:
            try:
                df = pd.read_excel(f, sheet_name=sheet, dtype=str)
                df.columns = [str(c).strip() for c in df.columns]
                dfs.append(df)
                print(f"  ✓ {f.name} (sheet: {sheet}): {len(df):,} rows")
                break
            except Exception:
                continue

    if not dfs:
        return

    combined = pd.concat(dfs, ignore_index=True)
    combined.columns = [c.upper().replace(" ", "_") for c in combined.columns]

    # Normalise postcode column (different ABS releases use different names)
    postcode_cols = [c for c in combined.columns if "POA" in c or "POSTCODE" in c or "POSTAL" in c]
    if postcode_cols:
        combined.rename(columns={postcode_cols[0]: "POSTCODE"}, inplace=True)

    name_cols = [c for c in combined.columns if "NAME" in c]
    if name_cols:
        combined.rename(columns={name_cols[0]: "SUBURB_NAME"}, inplace=True)

    irsd_score_cols = [c for c in combined.columns if "IRSD" in c and "SCORE" in c]
    irsd_decile_cols = [c for c in combined.columns if "IRSD" in c and "DECILE" in c]

    if irsd_score_cols:
        combined.rename(columns={irsd_score_cols[0]: "IRSD_SCORE"}, inplace=True)
    if irsd_decile_cols:
        combined.rename(columns={irsd_decile_cols[0]: "IRSD_DECILE"}, inplace=True)

    # Filter WA
    if "STATE" in combined.columns:
        combined = combined[combined["STATE"].str.upper().str.strip() == "WA"].copy()

    combined["POSTCODE"] = combined["POSTCODE"].astype(str).str.strip().str.extract(r"(\d{4})")[0]
    combined["IRSD_SCORE"] = pd.to_numeric(combined.get("IRSD_SCORE"), errors="coerce")
    combined["IRSD_DECILE"] = pd.to_numeric(combined.get("IRSD_DECILE"), errors="coerce")

    combined = combined[combined["POSTCODE"].str.match(r"^6\d{3}$", na=False)].copy()

    con.execute("DROP TABLE IF EXISTS seifa")
    con.execute("""
        CREATE TABLE seifa AS
        SELECT POSTCODE, SUBURB_NAME, IRSD_SCORE, IRSD_DECILE
        FROM (
            SELECT
                POSTCODE,
                COALESCE(SUBURB_NAME, POSTCODE) AS SUBURB_NAME,
                IRSD_SCORE,
                IRSD_DECILE,
                ROW_NUMBER() OVER (PARTITION BY POSTCODE ORDER BY IRSD_SCORE DESC NULLS LAST) AS rn
            FROM combined
            WHERE POSTCODE IS NOT NULL
        ) sub
        WHERE rn = 1
    """)

    count = con.execute("SELECT COUNT(*) FROM seifa").fetchone()[0]
    print(f"  ✓ seifa table: {count:,} postcodes")


# ─────────────────────────────────────────────
# Table 3: census_g02
# ─────────────────────────────────────────────

def ingest_census(con: duckdb.DuckDBPyConnection):
    print("\n── Ingesting Census G02 data ──")

    census_dir = DATA_DIR / "census"
    csv_files = list(census_dir.glob("*G02*.csv"))

    if not csv_files:
        print("  ✗ No G02 CSV in data/census/ — run 01_download_data.py")
        return

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype=str)
            dfs.append(df)
            print(f"  ✓ {f.name}: {len(df):,} rows")
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")

    if not dfs:
        return

    combined = pd.concat(dfs, ignore_index=True)
    combined.columns = [c.strip() for c in combined.columns]

    combined["Median_tot_hhd_inc_weekly"] = pd.to_numeric(combined.get("Median_tot_hhd_inc_weekly"), errors="coerce")
    combined["Median_rent_weekly"] = pd.to_numeric(combined.get("Median_rent_weekly"), errors="coerce")

    con.execute("DROP TABLE IF EXISTS census_g02")
    con.execute("""
        CREATE TABLE census_g02 AS
        SELECT
            SA2_CODE_2021,
            SA2_NAME_2021,
            CAST(Median_tot_hhd_inc_weekly AS DOUBLE) AS median_hhd_income_weekly,
            CAST(Median_rent_weekly AS DOUBLE) AS median_rent_weekly_census,
            CAST(Average_household_size AS DOUBLE) AS avg_household_size
        FROM combined
        WHERE SA2_CODE_2021 IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM census_g02").fetchone()[0]
    print(f"  ✓ census_g02 table: {count:,} SA2 areas")


# ─────────────────────────────────────────────
# Table 4: ato_income
# ─────────────────────────────────────────────

def ingest_ato(con: duckdb.DuckDBPyConnection):
    print("\n── Ingesting ATO income data ──")

    ato_dir = DATA_DIR / "ato"

    # Table 7D
    xlsx_files = list(ato_dir.glob("*.xlsx"))
    if xlsx_files:
        for f in xlsx_files:
            try:
                df = pd.read_excel(f, dtype=str)
                df.columns = [c.strip() for c in df.columns]

                postcode_col = next((c for c in df.columns if "postcode" in c.lower()), None)
                median_col = next((c for c in df.columns if "median" in c.lower() and "income" in c.lower()), None)

                if postcode_col:
                    df.rename(columns={postcode_col: "Postcode"}, inplace=True)
                if median_col:
                    df.rename(columns={median_col: "Median_taxable_income"}, inplace=True)

                df["Postcode"] = df["Postcode"].astype(str).str.strip().str.zfill(4)
                df["Median_taxable_income"] = pd.to_numeric(df.get("Median_taxable_income"), errors="coerce")
                df = df[df["Postcode"].str.match(r"^6\d{3}$", na=False)].copy()

                con.execute("DROP TABLE IF EXISTS ato_income")
                con.execute("""
                    CREATE TABLE ato_income AS
                    SELECT
                        Postcode AS postcode,
                        COALESCE(Suburb, Postcode) AS suburb,
                        CAST(Median_taxable_income AS DOUBLE) AS median_taxable_income,
                        CAST(Average_taxable_income AS DOUBLE) AS avg_taxable_income
                    FROM df
                    WHERE Postcode IS NOT NULL
                """)
                count = con.execute("SELECT COUNT(*) FROM ato_income").fetchone()[0]
                print(f"  ✓ ato_income table: {count:,} postcodes")
                break
            except Exception as e:
                print(f"  ✗ {f}: {e}")

    # Key worker salaries
    salary_csv = ato_dir / "key_worker_salaries.csv"
    if salary_csv.exists():
        df = pd.read_csv(salary_csv)
        con.execute("DROP TABLE IF EXISTS key_worker_salaries")
        con.execute("CREATE TABLE key_worker_salaries AS SELECT * FROM df")
        print(f"  ✓ key_worker_salaries table: {len(df)} occupations")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Perth Rental Affordability Tracker — DuckDB Ingestion")
    print("=" * 60)

    con = get_connection()

    ingest_rental_bonds(con)
    ingest_seifa(con)
    ingest_census(con)
    ingest_ato(con)

    print("\n── Tables in database ──")
    tables = con.execute("SHOW TABLES").fetchdf()
    print(tables.to_string(index=False))

    con.close()
    print(f"\n✓ Database saved to: {DB_PATH}")
    print("  Next: python scripts/03_build_affordability.py")
