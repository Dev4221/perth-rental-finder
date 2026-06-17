"""
scripts/04_verify.py
Step 4: Verify the database is complete and ready to serve the app.

Run: python scripts/04_verify.py
"""

import os
import sys
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
PASS = "✓"
FAIL = "✗"


def check(label: str, condition: bool, detail: str = "") -> bool:
    icon = PASS if condition else FAIL
    msg = f"  {icon} {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    return condition


def verify():
    print("Perth Rental Affordability Tracker — Verification")
    print("=" * 60)

    if not Path(DB_PATH).exists():
        print(f"{FAIL} Database not found: {DB_PATH}")
        print("  Run: python scripts/02_ingest_duckdb.py")
        sys.exit(1)

    con = duckdb.connect(DB_PATH, read_only=True)
    results = []

    # ── Required tables ──────────────────────────────────────────────────────
    print("\n── Tables ──")
    required_tables = [
        "rental_bonds", "seifa", "census_g02", "ato_income",
        "key_worker_salaries", "suburb_rent_summary", "suburb_overall_rent",
        "rent_trend", "affordability", "key_worker_affordability",
    ]
    for table in required_tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            results.append(check(f"{table}", count > 0, f"{count:,} rows"))
        except Exception as e:
            results.append(check(f"{table}", False, str(e)))

    # ── Data quality ──────────────────────────────────────────────────────────
    print("\n── Data Quality ──")

    # Rental bonds: should have Perth postcodes
    try:
        bond_count = con.execute("SELECT COUNT(*) FROM rental_bonds").fetchone()[0]
        results.append(check("rental_bonds has Perth postcodes", bond_count > 0, f"{bond_count:,} records"))

        # Check rent range is realistic
        min_rent, max_rent = con.execute("SELECT MIN(WEEKLY_RENT), MAX(WEEKLY_RENT) FROM rental_bonds").fetchone()
        results.append(check("rent range is realistic", 50 < min_rent and max_rent < 5000, f"${min_rent}–${max_rent}/wk"))

        # Check we have multiple months
        months = con.execute("SELECT COUNT(DISTINCT LODGEMENT_MONTH) FROM rental_bonds WHERE LODGEMENT_MONTH IS NOT NULL").fetchone()[0]
        results.append(check("has multiple months of data", months >= 3, f"{months} months"))
    except Exception as e:
        results.append(check("rental_bonds quality", False, str(e)))

    # Affordability: check stress ratios are sensible
    try:
        stressed_pct = con.execute("""
            SELECT ROUND(100.0 * SUM(CASE WHEN in_rental_stress THEN 1 ELSE 0 END) / COUNT(*), 1)
            FROM affordability WHERE rent_to_income_ratio IS NOT NULL
        """).fetchone()[0]
        results.append(check(
            "stress rate is plausible (10–90%)",
            stressed_pct is not None and 10 <= stressed_pct <= 90,
            f"{stressed_pct}% of suburbs in stress"
        ))
    except Exception as e:
        results.append(check("affordability stress rates", False, str(e)))

    # Key workers: should have nurse data
    try:
        nurse_suburbs = con.execute(
            "SELECT COUNT(*) FROM key_worker_affordability WHERE occupation = 'registered_nurse'"
        ).fetchone()[0]
        results.append(check("nurse affordability data exists", nurse_suburbs > 0, f"{nurse_suburbs} suburb/nurse pairs"))
    except Exception as e:
        results.append(check("nurse data", False, str(e)))

    # ── Key chatbot query test ─────────────────────────────────────────────
    print("\n── Key Query Test ──")
    print("  Query: Can a nurse afford to rent near Fiona Stanley Hospital?")
    print("  (Fiona Stanley Hospital = Murdoch, postcode 6150)\n")
    try:
        result = con.execute("""
            SELECT
                kw.suburb,
                kw.median_annual_salary,
                kw.median_weekly_rent,
                ROUND(kw.stress_ratio * 100, 1) AS rent_pct_of_income,
                kw.can_afford_median,
                kw.median_rent_2br,
                kw.can_afford_2br
            FROM key_worker_affordability kw
            WHERE kw.occupation = 'registered_nurse'
              AND (kw.suburb IN ('Murdoch', 'Kardinya', 'Bull Creek', 'Melville', 'Fremantle')
                   OR kw.postcode IN ('6150', '6163', '6149', '6156', '6160'))
            ORDER BY kw.stress_ratio
        """).fetchdf()

        if len(result) > 0:
            print(result.to_string(index=False))
            results.append(check("key chatbot query returns results", True, f"{len(result)} suburbs near FSH"))
        else:
            results.append(check("key chatbot query returns results", False, "no results for nurse/Murdoch"))
    except Exception as e:
        results.append(check("key chatbot query", False, str(e)))

    # ── Summary ──────────────────────────────────────────────────────────────
    con.close()
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"  {passed}/{total} checks passed")

    if passed == total:
        print("  ✓ Database is ready! Run: streamlit run app.py")
    else:
        failed = total - passed
        print(f"  ✗ {failed} check(s) failed — review output above")
        print("    Common fixes:")
        print("    • Re-run: python scripts/01_download_data.py")
        print("    • Re-run: python scripts/02_ingest_duckdb.py")
        print("    • Re-run: python scripts/03_build_affordability.py")

    return passed == total


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
