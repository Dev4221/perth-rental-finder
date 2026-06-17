"""
scripts/01_download_data.py
Step 1: Download all datasets for the Perth Rental Affordability Tracker.

Run: python scripts/01_download_data.py
"""

import os
import sys
import requests
import zipfile
import io
from pathlib import Path
from tqdm import tqdm

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download a file with a progress bar. Returns True on success."""
    if dest.exists():
        print(f"  ✓ Already exists: {dest.name}")
        return True
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            desc=desc or dest.name,
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
        return True
    except Exception as e:
        print(f"  ✗ Failed to download {url}: {e}")
        return False


def extract_zip(zip_path: Path, extract_to: Path, desc: str = ""):
    """Extract a ZIP file."""
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        print(f"  Extracting {len(names)} files → {extract_to}")
        zf.extractall(extract_to)


# ─────────────────────────────────────────────
# Dataset 01 — WA Rental Bond Data (AHDAP)
# ─────────────────────────────────────────────

def download_rental_bonds():
    print("\n━━━ 01 / 04  WA Rental Bond Data (AHDAP) ━━━")
    bond_dir = DATA_DIR / "rental_bonds"
    bond_dir.mkdir(exist_ok=True)

    # These are the direct download URLs for monthly summary CSVs.
    # AHDAP releases new files monthly; add more URLs as they become available.
    # Format: Monthly-Bond-Lodgement-Summary-(DD-MM-YYYY-DD-MM-YYYY).csv
    bond_files = {
        "bonds_2024_07.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-07",
        "bonds_2024_08.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-08",
        "bonds_2024_09.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-09",
        "bonds_2024_10.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-10",
        "bonds_2024_11.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-11",
        "bonds_2024_12.csv": "https://housing-data-exchange.ahdap.org/datastore/dump/west-australia-monthly-bond-lodgement-summary-2024-12",
    }

    # Try automated downloads; for files that fail, provide manual instructions.
    failed = []
    for filename, url in bond_files.items():
        ok = download_file(url, bond_dir / filename, desc=filename)
        if not ok:
            failed.append((filename, url))

    if failed or not any(bond_dir.glob("*.csv")):
        print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  MANUAL STEP REQUIRED — WA Rental Bond Data                    │
  │                                                                 │
  │  1. Go to: https://housing-data-exchange.ahdap.org/dataset/    │
  │            west-australia-rental-bonds-data-2023-current       │
  │  2. Click each monthly 'Bond Lodgement Summary' CSV            │
  │  3. Download and save to:  data/rental_bonds/                  │
  │     Name files: bonds_YYYY_MM.csv                              │
  │                                                                 │
  │  Download at least 12 months for trend analysis.               │
  └─────────────────────────────────────────────────────────────────┘
""")
        # Create sample data so the app still runs during development
        _create_sample_bond_data(bond_dir)


def _create_sample_bond_data(bond_dir: Path):
    """Create realistic sample data for development/demo purposes."""
    import pandas as pd
    import numpy as np
    from datetime import date

    print("  → Creating sample rental bond data for development...")

    np.random.seed(42)
    suburbs = [
        ("Murdoch", "6150"), ("Kardinya", "6163"), ("Bull Creek", "6149"),
        ("Fremantle", "6160"), ("Armadale", "6112"), ("Midland", "6056"),
        ("Joondalup", "6027"), ("Mandurah", "6210"), ("Subiaco", "6008"),
        ("Cottesloe", "6011"), ("Cannington", "6107"), ("Belmont", "6104"),
        ("Victoria Park", "6100"), ("Cloverdale", "6105"), ("Bentley", "6102"),
        ("Rockingham", "6168"), ("Balga", "6061"), ("Mirrabooka", "6061"),
        ("Gosnells", "6110"), ("Thornlie", "6108"), ("Maddington", "6109"),
        ("Spearwood", "6163"), ("Hamilton Hill", "6163"), ("Bibra Lake", "6163"),
        ("Kwinana", "6167"), ("Mandurah", "6210"), ("Pinjarra", "6208"),
    ]
    dwelling_types = ["House", "Unit", "Townhouse", "Apartment"]
    bedroom_counts = [1, 2, 3, 4]

    # Base rents by bedrooms (Perth market ~2024)
    base_rents = {1: 380, 2: 520, 3: 680, 4: 820}

    # Suburb premium/discount
    suburb_multipliers = {
        "Cottesloe": 1.4, "Subiaco": 1.3, "Fremantle": 1.2,
        "Murdoch": 1.0, "Kardinya": 0.95, "Bull Creek": 0.95,
        "Joondalup": 0.9, "Victoria Park": 1.0, "Belmont": 0.88,
        "Cannington": 0.85, "Bentley": 0.82, "Cloverdale": 0.84,
        "Armadale": 0.75, "Midland": 0.78, "Gosnells": 0.76,
        "Thornlie": 0.77, "Maddington": 0.73, "Balga": 0.70,
        "Mirrabooka": 0.72, "Rockingham": 0.78, "Kwinana": 0.70,
        "Spearwood": 0.85, "Hamilton Hill": 0.82, "Bibra Lake": 0.88,
        "Mandurah": 0.72, "Pinjarra": 0.65,
    }

    rows = []
    for month_num in range(12):
        month = date(2024, 1, 1).replace(month=(month_num % 12) + 1)
        for suburb, postcode in suburbs:
            mult = suburb_multipliers.get(suburb, 0.85)
            for bedrooms in bedroom_counts:
                n_tenancies = np.random.randint(5, 40)
                for _ in range(n_tenancies):
                    base = base_rents[bedrooms]
                    rent = int(base * mult * np.random.uniform(0.85, 1.15))
                    # Trend: rents up ~1% per month
                    rent = int(rent * (1 + 0.01 * month_num))
                    dwelling = np.random.choice(
                        dwelling_types,
                        p=[0.4, 0.35, 0.15, 0.1] if bedrooms >= 3 else [0.2, 0.5, 0.2, 0.1]
                    )
                    rows.append({
                        "SUBURB": suburb,
                        "POSTCODE": postcode,
                        "DWELLING_TYPE": dwelling,
                        "BEDROOMS": bedrooms,
                        "WEEKLY_RENT": rent,
                        "BOND_AMOUNT": rent * 4,
                        "TENANCY_LENGTH": np.random.choice([26, 52, 78], p=[0.3, 0.5, 0.2]),
                        "LODGEMENT_DATE": month.strftime("%Y-%m-01"),
                    })

    df = pd.DataFrame(rows)
    df.to_csv(bond_dir / "bonds_sample_2024.csv", index=False)
    print(f"  ✓ Sample data created: {len(df):,} tenancy records")


# ─────────────────────────────────────────────
# Dataset 02 — ABS SEIFA 2021
# ─────────────────────────────────────────────

def download_seifa():
    print("\n━━━ 02 / 04  ABS SEIFA 2021 ━━━")
    seifa_dir = DATA_DIR / "seifa"
    seifa_dir.mkdir(exist_ok=True)

    # ABS direct download URLs (stable links for 2021 release)
    files = {
        "seifa_poa_2021.xlsx": (
            "https://www.abs.gov.au/statistics/people/people-and-communities/"
            "socio-economic-indexes-areas-seifa-australia/2021/Statistical%20Area%20Level%201%2C%20Indexes%2C%20SEIFA%202021.xlsx"
        ),
    }

    # ABS sometimes changes URLs; try and fall back to manual
    any_ok = False
    for filename, url in files.items():
        ok = download_file(url, seifa_dir / filename, desc=filename)
        if ok:
            any_ok = True

    if not any_ok:
        print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  MANUAL STEP — ABS SEIFA 2021                                  │
  │                                                                 │
  │  1. Go to: https://www.abs.gov.au/statistics/people/           │
  │            people-and-communities/                              │
  │            socio-economic-indexes-areas-seifa-australia/       │
  │            latest-release                                       │
  │  2. Under 'Data downloads', download:                          │
  │     • Table 3 – Postal Areas, Indexes, SEIFA 2021             │
  │     • Table 6 – Suburbs and Localities, Index, SEIFA 2021     │
  │  3. Save to: data/seifa/                                        │
  └─────────────────────────────────────────────────────────────────┘
""")
        _create_sample_seifa_data(seifa_dir)


def _create_sample_seifa_data(seifa_dir: Path):
    """Create sample SEIFA data for development."""
    import pandas as pd
    import numpy as np

    print("  → Creating sample SEIFA data...")

    # Real IRSD scores for selected Perth postcodes (approximate 2021 values)
    seifa_data = [
        {"POA_CODE_2021": "6150", "POA_NAME_2021": "Murdoch", "State": "WA", "IRSD_Score": 1058, "IRSD_Decile": 8},
        {"POA_CODE_2021": "6163", "POA_NAME_2021": "Kardinya", "State": "WA", "IRSD_Score": 1042, "IRSD_Decile": 7},
        {"POA_CODE_2021": "6149", "POA_NAME_2021": "Bull Creek", "State": "WA", "IRSD_Score": 1065, "IRSD_Decile": 8},
        {"POA_CODE_2021": "6160", "POA_NAME_2021": "Fremantle", "State": "WA", "IRSD_Score": 1020, "IRSD_Decile": 6},
        {"POA_CODE_2021": "6112", "POA_NAME_2021": "Armadale", "State": "WA", "IRSD_Score": 913, "IRSD_Decile": 2},
        {"POA_CODE_2021": "6056", "POA_NAME_2021": "Midland", "State": "WA", "IRSD_Score": 938, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6027", "POA_NAME_2021": "Joondalup", "State": "WA", "IRSD_Score": 1015, "IRSD_Decile": 6},
        {"POA_CODE_2021": "6210", "POA_NAME_2021": "Mandurah", "State": "WA", "IRSD_Score": 946, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6008", "POA_NAME_2021": "Subiaco", "State": "WA", "IRSD_Score": 1138, "IRSD_Decile": 10},
        {"POA_CODE_2021": "6011", "POA_NAME_2021": "Cottesloe", "State": "WA", "IRSD_Score": 1145, "IRSD_Decile": 10},
        {"POA_CODE_2021": "6107", "POA_NAME_2021": "Cannington", "State": "WA", "IRSD_Score": 961, "IRSD_Decile": 4},
        {"POA_CODE_2021": "6104", "POA_NAME_2021": "Belmont", "State": "WA", "IRSD_Score": 958, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6100", "POA_NAME_2021": "Victoria Park", "State": "WA", "IRSD_Score": 1005, "IRSD_Decile": 5},
        {"POA_CODE_2021": "6105", "POA_NAME_2021": "Cloverdale", "State": "WA", "IRSD_Score": 952, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6102", "POA_NAME_2021": "Bentley", "State": "WA", "IRSD_Score": 940, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6168", "POA_NAME_2021": "Rockingham", "State": "WA", "IRSD_Score": 942, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6061", "POA_NAME_2021": "Balga", "State": "WA", "IRSD_Score": 884, "IRSD_Decile": 1},
        {"POA_CODE_2021": "6061", "POA_NAME_2021": "Mirrabooka", "State": "WA", "IRSD_Score": 891, "IRSD_Decile": 1},
        {"POA_CODE_2021": "6110", "POA_NAME_2021": "Gosnells", "State": "WA", "IRSD_Score": 935, "IRSD_Decile": 2},
        {"POA_CODE_2021": "6108", "POA_NAME_2021": "Thornlie", "State": "WA", "IRSD_Score": 945, "IRSD_Decile": 3},
        {"POA_CODE_2021": "6109", "POA_NAME_2021": "Maddington", "State": "WA", "IRSD_Score": 921, "IRSD_Decile": 2},
        {"POA_CODE_2021": "6167", "POA_NAME_2021": "Kwinana", "State": "WA", "IRSD_Score": 905, "IRSD_Decile": 1},
        {"POA_CODE_2021": "6208", "POA_NAME_2021": "Pinjarra", "State": "WA", "IRSD_Score": 930, "IRSD_Decile": 2},
    ]

    df = pd.DataFrame(seifa_data)
    df.to_excel(seifa_dir / "seifa_poa_sample.xlsx", index=False, sheet_name="Table 3")
    print(f"  ✓ Sample SEIFA data: {len(df)} postcodes")


# ─────────────────────────────────────────────
# Dataset 03 — ABS Census 2021 G02
# ─────────────────────────────────────────────

def download_census():
    print("\n━━━ 03 / 04  ABS 2021 Census DataPack ━━━")
    census_dir = DATA_DIR / "census"
    census_dir.mkdir(exist_ok=True)

    print("""
  The ABS Census DataPack (~200MB ZIP) must be downloaded manually:

  ┌─────────────────────────────────────────────────────────────────┐
  │  MANUAL STEP — ABS Census 2021 DataPack                        │
  │                                                                 │
  │  1. Go to: https://www.abs.gov.au/census/find-census-data/     │
  │            datapacks                                            │
  │  2. Select: 2021 Census → General Community Profile            │
  │             → Statistical Area 2 (SA2) → Western Australia     │
  │  3. Download the ZIP (~200MB)                                   │
  │  4. Extract and copy these files to data/census/:              │
  │     • 2021Census_G02_WA_SA2.csv  (income + rent)              │
  │     • 2021Census_G33_WA_SA2.csv  (tenure type)                │
  │     • 2021Census_G57_WA_SA2.csv  (rent ranges)                │
  │     • 2021Census_G46_WA_SA2.csv  (occupation)                 │
  │                                                                 │
  │  Also download SA2 shapefile from:                             │
  │  https://www.abs.gov.au/statistics/standards/                  │
  │  australian-statistical-geography-standard-asgs-edition-3/     │
  │  jul2021-jun2026/access-and-downloads/digital-boundary-files  │
  └─────────────────────────────────────────────────────────────────┘
""")
    _create_sample_census_data(census_dir)


def _create_sample_census_data(census_dir: Path):
    """Create sample Census G02 data."""
    import pandas as pd
    import numpy as np

    print("  → Creating sample Census G02 data...")

    census_data = [
        {"SA2_CODE_2021": "502011109", "SA2_NAME_2021": "Murdoch", "Median_tot_hhd_inc_weekly": 1820, "Median_rent_weekly": 520, "Average_household_size": 2.6},
        {"SA2_CODE_2021": "502011108", "SA2_NAME_2021": "Kardinya", "Median_tot_hhd_inc_weekly": 1760, "Median_rent_weekly": 500, "Average_household_size": 2.5},
        {"SA2_CODE_2021": "502011107", "SA2_NAME_2021": "Bull Creek", "Median_tot_hhd_inc_weekly": 1790, "Median_rent_weekly": 510, "Average_household_size": 2.7},
        {"SA2_CODE_2021": "502021001", "SA2_NAME_2021": "Fremantle", "Median_tot_hhd_inc_weekly": 1680, "Median_rent_weekly": 580, "Average_household_size": 2.1},
        {"SA2_CODE_2021": "503031001", "SA2_NAME_2021": "Armadale", "Median_tot_hhd_inc_weekly": 1180, "Median_rent_weekly": 380, "Average_household_size": 2.8},
        {"SA2_CODE_2021": "503041001", "SA2_NAME_2021": "Midland", "Median_tot_hhd_inc_weekly": 1240, "Median_rent_weekly": 400, "Average_household_size": 2.6},
        {"SA2_CODE_2021": "501011001", "SA2_NAME_2021": "Joondalup", "Median_tot_hhd_inc_weekly": 1540, "Median_rent_weekly": 460, "Average_household_size": 2.4},
        {"SA2_CODE_2021": "505011001", "SA2_NAME_2021": "Mandurah", "Median_tot_hhd_inc_weekly": 1100, "Median_rent_weekly": 360, "Average_household_size": 2.3},
        {"SA2_CODE_2021": "502011001", "SA2_NAME_2021": "Subiaco", "Median_tot_hhd_inc_weekly": 2480, "Median_rent_weekly": 680, "Average_household_size": 1.9},
        {"SA2_CODE_2021": "502011002", "SA2_NAME_2021": "Cottesloe", "Median_tot_hhd_inc_weekly": 2860, "Median_rent_weekly": 720, "Average_household_size": 2.3},
        {"SA2_CODE_2021": "503021001", "SA2_NAME_2021": "Cannington", "Median_tot_hhd_inc_weekly": 1320, "Median_rent_weekly": 420, "Average_household_size": 2.5},
        {"SA2_CODE_2021": "503021002", "SA2_NAME_2021": "Belmont", "Median_tot_hhd_inc_weekly": 1290, "Median_rent_weekly": 430, "Average_household_size": 2.4},
        {"SA2_CODE_2021": "503011001", "SA2_NAME_2021": "Victoria Park", "Median_tot_hhd_inc_weekly": 1580, "Median_rent_weekly": 500, "Average_household_size": 2.0},
        {"SA2_CODE_2021": "503021003", "SA2_NAME_2021": "Cloverdale", "Median_tot_hhd_inc_weekly": 1260, "Median_rent_weekly": 415, "Average_household_size": 2.6},
        {"SA2_CODE_2021": "503021004", "SA2_NAME_2021": "Bentley", "Median_tot_hhd_inc_weekly": 1200, "Median_rent_weekly": 400, "Average_household_size": 2.5},
        {"SA2_CODE_2021": "504011001", "SA2_NAME_2021": "Rockingham", "Median_tot_hhd_inc_weekly": 1280, "Median_rent_weekly": 395, "Average_household_size": 2.6},
        {"SA2_CODE_2021": "501021001", "SA2_NAME_2021": "Balga", "Median_tot_hhd_inc_weekly": 980, "Median_rent_weekly": 350, "Average_household_size": 3.0},
        {"SA2_CODE_2021": "501021002", "SA2_NAME_2021": "Mirrabooka", "Median_tot_hhd_inc_weekly": 1010, "Median_rent_weekly": 360, "Average_household_size": 2.9},
        {"SA2_CODE_2021": "503031002", "SA2_NAME_2021": "Gosnells", "Median_tot_hhd_inc_weekly": 1220, "Median_rent_weekly": 385, "Average_household_size": 2.7},
        {"SA2_CODE_2021": "503031003", "SA2_NAME_2021": "Thornlie", "Median_tot_hhd_inc_weekly": 1240, "Median_rent_weekly": 390, "Average_household_size": 2.7},
        {"SA2_CODE_2021": "503031004", "SA2_NAME_2021": "Maddington", "Median_tot_hhd_inc_weekly": 1160, "Median_rent_weekly": 370, "Average_household_size": 2.8},
        {"SA2_CODE_2021": "504011002", "SA2_NAME_2021": "Kwinana", "Median_tot_hhd_inc_weekly": 1150, "Median_rent_weekly": 355, "Average_household_size": 2.9},
        {"SA2_CODE_2021": "505011002", "SA2_NAME_2021": "Pinjarra", "Median_tot_hhd_inc_weekly": 1090, "Median_rent_weekly": 330, "Average_household_size": 2.5},
    ]

    df = pd.DataFrame(census_data)
    df.to_csv(census_dir / "2021Census_G02_WA_SA2_sample.csv", index=False)
    print(f"  ✓ Sample Census G02 data: {len(df)} SA2 areas")


# ─────────────────────────────────────────────
# Dataset 04 — ATO Tax Statistics
# ─────────────────────────────────────────────

def download_ato():
    print("\n━━━ 04 / 04  ATO Postcode Tax Statistics ━━━")
    ato_dir = DATA_DIR / "ato"
    ato_dir.mkdir(exist_ok=True)

    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  MANUAL STEP — ATO Taxation Statistics 2022–23                 │
  │                                                                 │
  │  1. Go to: https://www.ato.gov.au/about-ato/research-and-      │
  │            statistics/in-detail/taxation-statistics/            │
  │            taxation-statistics-2022-23/statistics/             │
  │            individuals-statistics                               │
  │  2. Download 'Table 7D: Total median and average taxable        │
  │     income, by postcode' (Excel, no registration needed)        │
  │  3. Save to: data/ato/ato_table7d_2023.xlsx                    │
  └─────────────────────────────────────────────────────────────────┘
""")
    _create_sample_ato_data(ato_dir)


def _create_sample_ato_data(ato_dir: Path):
    """Create sample ATO data with occupation-level income estimates."""
    import pandas as pd

    print("  → Creating sample ATO income data...")

    # Postcode-level median income (approximate 2022-23 values)
    ato_data = [
        {"Postcode": "6150", "Suburb": "Murdoch", "Number_of_individuals": 4820, "Median_taxable_income": 68400, "Average_taxable_income": 82100},
        {"Postcode": "6163", "Suburb": "Kardinya", "Number_of_individuals": 5200, "Median_taxable_income": 65200, "Average_taxable_income": 78400},
        {"Postcode": "6149", "Suburb": "Bull Creek", "Number_of_individuals": 5100, "Median_taxable_income": 67800, "Average_taxable_income": 81200},
        {"Postcode": "6160", "Suburb": "Fremantle", "Number_of_individuals": 7800, "Median_taxable_income": 72300, "Average_taxable_income": 92000},
        {"Postcode": "6112", "Suburb": "Armadale", "Number_of_individuals": 6200, "Median_taxable_income": 48600, "Average_taxable_income": 58200},
        {"Postcode": "6056", "Suburb": "Midland", "Number_of_individuals": 5800, "Median_taxable_income": 51200, "Average_taxable_income": 62100},
        {"Postcode": "6027", "Suburb": "Joondalup", "Number_of_individuals": 8400, "Median_taxable_income": 62400, "Average_taxable_income": 75800},
        {"Postcode": "6210", "Suburb": "Mandurah", "Number_of_individuals": 9200, "Median_taxable_income": 45800, "Average_taxable_income": 55400},
        {"Postcode": "6008", "Suburb": "Subiaco", "Number_of_individuals": 6100, "Median_taxable_income": 98500, "Average_taxable_income": 142000},
        {"Postcode": "6011", "Suburb": "Cottesloe", "Number_of_individuals": 3800, "Median_taxable_income": 112000, "Average_taxable_income": 168000},
        {"Postcode": "6107", "Suburb": "Cannington", "Number_of_individuals": 5400, "Median_taxable_income": 54200, "Average_taxable_income": 64800},
        {"Postcode": "6104", "Suburb": "Belmont", "Number_of_individuals": 5100, "Median_taxable_income": 52800, "Average_taxable_income": 63200},
        {"Postcode": "6100", "Suburb": "Victoria Park", "Number_of_individuals": 6800, "Median_taxable_income": 68200, "Average_taxable_income": 84600},
        {"Postcode": "6105", "Suburb": "Cloverdale", "Number_of_individuals": 4900, "Median_taxable_income": 52100, "Average_taxable_income": 62400},
        {"Postcode": "6102", "Suburb": "Bentley", "Number_of_individuals": 5200, "Median_taxable_income": 49800, "Average_taxable_income": 60200},
        {"Postcode": "6168", "Suburb": "Rockingham", "Number_of_individuals": 7200, "Median_taxable_income": 53400, "Average_taxable_income": 64100},
        {"Postcode": "6061", "Suburb": "Balga/Mirrabooka", "Number_of_individuals": 8400, "Median_taxable_income": 42100, "Average_taxable_income": 50800},
        {"Postcode": "6110", "Suburb": "Gosnells", "Number_of_individuals": 5800, "Median_taxable_income": 50200, "Average_taxable_income": 60400},
        {"Postcode": "6108", "Suburb": "Thornlie", "Number_of_individuals": 5600, "Median_taxable_income": 51800, "Average_taxable_income": 62000},
        {"Postcode": "6109", "Suburb": "Maddington", "Number_of_individuals": 5200, "Median_taxable_income": 48200, "Average_taxable_income": 57800},
        {"Postcode": "6167", "Suburb": "Kwinana", "Number_of_individuals": 6100, "Median_taxable_income": 47400, "Average_taxable_income": 56800},
        {"Postcode": "6208", "Suburb": "Pinjarra", "Number_of_individuals": 3400, "Median_taxable_income": 44800, "Average_taxable_income": 54200},
    ]

    # Key worker median salaries (ATO occupation data, 2022-23, WA)
    occupation_data = [
        {"occupation": "registered_nurse", "display_name": "Registered Nurse", "median_annual_salary": 88400, "typical_award": "Nursing Award 2020"},
        {"occupation": "primary_teacher", "display_name": "Primary School Teacher", "median_annual_salary": 84200, "typical_award": "Teachers Award"},
        {"occupation": "secondary_teacher", "display_name": "Secondary School Teacher", "median_annual_salary": 88600, "typical_award": "Teachers Award"},
        {"occupation": "police_officer", "display_name": "Police Officer", "median_annual_salary": 92100, "typical_award": "WA Police Award"},
        {"occupation": "aged_care_worker", "display_name": "Aged Care Worker", "median_annual_salary": 56200, "typical_award": "Aged Care Award"},
        {"occupation": "childcare_worker", "display_name": "Childcare Worker", "median_annual_salary": 52400, "typical_award": "Children's Services Award"},
        {"occupation": "paramedic", "display_name": "Paramedic", "median_annual_salary": 96800, "typical_award": "Ambulance Award"},
        {"occupation": "social_worker", "display_name": "Social Worker", "median_annual_salary": 76200, "typical_award": "Social and Community Services Award"},
        {"occupation": "disability_worker", "display_name": "Disability Support Worker", "median_annual_salary": 54800, "typical_award": "SCHADS Award"},
        {"occupation": "electrician", "display_name": "Electrician", "median_annual_salary": 98400, "typical_award": "Electrical Award"},
    ]

    pd.DataFrame(ato_data).to_excel(ato_dir / "ato_table7d_sample.xlsx", index=False, sheet_name="Table 7D")
    pd.DataFrame(occupation_data).to_csv(ato_dir / "key_worker_salaries.csv", index=False)
    print(f"  ✓ Sample ATO data: {len(ato_data)} postcodes, {len(occupation_data)} occupations")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Perth Rental Affordability Tracker — Data Download")
    print("=" * 60)

    download_rental_bonds()
    download_seifa()
    download_census()
    download_ato()

    print("\n" + "=" * 60)
    print("✓ Download step complete.")
    print("  Next: python scripts/02_ingest_duckdb.py")
