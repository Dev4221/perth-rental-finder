"""
scripts/03_build_affordability.py
Step 3: Build the affordability analytics tables from the raw data.

Run: python scripts/03_build_affordability.py
"""

import os
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
STRESS_THRESHOLD = 0.30  # 30% of income on rent = rental stress


def build_affordability_tables(con: duckdb.DuckDBPyConnection):
    print("\n── Building affordability tables ──")

    # ── 1. Suburb rent summary (from rental bond data) ──────────────────────
    print("  Building suburb_rent_summary...")
    con.execute("""
        CREATE OR REPLACE TABLE suburb_rent_summary AS
        SELECT
            SUBURB                                      AS suburb,
            POSTCODE                                    AS postcode,
            BEDROOMS                                    AS bedrooms,
            DWELLING_TYPE                               AS dwelling_type,
            COUNT(*)                                    AS tenancy_count,
            MEDIAN(WEEKLY_RENT)                         AS median_weekly_rent,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY WEEKLY_RENT) AS p25_weekly_rent,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY WEEKLY_RENT) AS p75_weekly_rent,
            AVG(WEEKLY_RENT)                            AS avg_weekly_rent,
            MIN(WEEKLY_RENT)                            AS min_weekly_rent,
            MAX(WEEKLY_RENT)                            AS max_weekly_rent
        FROM rental_bonds
        WHERE SUBURB IS NOT NULL
          AND WEEKLY_RENT IS NOT NULL
          AND BEDROOMS IS NOT NULL
        GROUP BY suburb, postcode, bedrooms, dwelling_type
    """)
    count = con.execute("SELECT COUNT(*) FROM suburb_rent_summary").fetchone()[0]
    print(f"    ✓ {count:,} suburb/bedrooms/type combinations")

    # ── 2. Overall suburb median (all bedrooms combined) ────────────────────
    print("  Building suburb_overall_rent...")
    con.execute("""
        CREATE OR REPLACE TABLE suburb_overall_rent AS
        SELECT
            SUBURB                  AS suburb,
            POSTCODE                AS postcode,
            COUNT(*)                AS total_tenancies,
            MEDIAN(WEEKLY_RENT)     AS median_weekly_rent_all,
            MEDIAN(CASE WHEN BEDROOMS = 2 THEN WEEKLY_RENT END) AS median_rent_2br,
            MEDIAN(CASE WHEN BEDROOMS = 3 THEN WEEKLY_RENT END) AS median_rent_3br,
            COUNT(CASE WHEN DWELLING_TYPE = 'Unit' OR DWELLING_TYPE = 'Apartment' THEN 1 END) AS unit_count,
            COUNT(CASE WHEN DWELLING_TYPE = 'House' THEN 1 END) AS house_count
        FROM rental_bonds
        WHERE SUBURB IS NOT NULL
        GROUP BY suburb, postcode
    """)

    # ── 3. Rent trend (month-by-month) ──────────────────────────────────────
    print("  Building rent_trend...")
    con.execute("""
        CREATE OR REPLACE TABLE rent_trend AS
        SELECT
            SUBURB                  AS suburb,
            POSTCODE                AS postcode,
            BEDROOMS                AS bedrooms,
            LODGEMENT_MONTH         AS month,
            COUNT(*)                AS tenancy_count,
            MEDIAN(WEEKLY_RENT)     AS median_weekly_rent,
            AVG(WEEKLY_RENT)        AS avg_weekly_rent
        FROM rental_bonds
        WHERE SUBURB IS NOT NULL
          AND LODGEMENT_MONTH IS NOT NULL
          AND BEDROOMS IS NOT NULL
        GROUP BY suburb, postcode, bedrooms, month
        ORDER BY suburb, bedrooms, month
    """)

    # ── 4. Main affordability table ─────────────────────────────────────────
    print("  Building affordability...")
    con.execute(f"""
        CREATE OR REPLACE TABLE affordability AS
        SELECT
            r.suburb,
            r.postcode,
            r.median_weekly_rent_all                                            AS median_weekly_rent,
            r.median_rent_2br,
            r.median_rent_3br,
            r.total_tenancies,

            -- ATO income data
            a.median_taxable_income                                             AS median_annual_income,
            a.median_taxable_income / 52.0                                      AS median_weekly_income,

            -- Rent-to-income ratio (annual rent / annual income)
            CASE
                WHEN a.median_taxable_income > 0
                THEN (r.median_weekly_rent_all * 52.0) / a.median_taxable_income
                ELSE NULL
            END                                                                 AS rent_to_income_ratio,

            -- Rental stress flag
            CASE
                WHEN a.median_taxable_income > 0
                THEN ((r.median_weekly_rent_all * 52.0) / a.median_taxable_income) > {STRESS_THRESHOLD}
                ELSE NULL
            END                                                                 AS in_rental_stress,

            -- SEIFA disadvantage
            s.irsd_score,
            s.irsd_decile,
            CASE
                WHEN s.irsd_decile <= 3 THEN 'High disadvantage'
                WHEN s.irsd_decile <= 6 THEN 'Moderate disadvantage'
                WHEN s.irsd_decile <= 8 THEN 'Low disadvantage'
                ELSE 'Advantaged'
            END                                                                 AS disadvantage_category,

            -- Combined vulnerability score (rental stress + disadvantage)
            CASE
                WHEN s.irsd_decile IS NOT NULL AND a.median_taxable_income > 0
                THEN (
                    -- Normalise rent-to-income (0-1, capped at 0.6)
                    LEAST((r.median_weekly_rent_all * 52.0) / a.median_taxable_income / 0.6, 1.0) * 0.5
                    -- Add disadvantage component (decile 1=worst → 1.0, decile 10=best → 0.0)
                    + ((10 - s.irsd_decile) / 9.0) * 0.5
                )
                ELSE NULL
            END                                                                 AS vulnerability_score

        FROM suburb_overall_rent r
        LEFT JOIN ato_income a ON r.postcode = a.postcode
        LEFT JOIN seifa s      ON r.postcode = s.postcode
        WHERE r.median_weekly_rent_all IS NOT NULL
    """)
    count = con.execute("SELECT COUNT(*) FROM affordability").fetchone()[0]
    stressed = con.execute("SELECT COUNT(*) FROM affordability WHERE in_rental_stress = true").fetchone()[0]
    print(f"    ✓ {count:,} suburbs · {stressed} in rental stress ({100*stressed//max(count,1)}%)")

    # ── 5. Key worker affordability ─────────────────────────────────────────
    print("  Building key_worker_affordability...")
    con.execute(f"""
        CREATE OR REPLACE TABLE key_worker_affordability AS
        SELECT
            k.occupation,
            k.display_name,
            k.median_annual_salary,
            a.suburb,
            a.postcode,
            a.median_weekly_rent,
            a.median_rent_2br,

            -- Stress ratio for this worker in this suburb
            (a.median_weekly_rent * 52.0) / k.median_annual_salary          AS stress_ratio,
            (a.median_rent_2br   * 52.0) / k.median_annual_salary           AS stress_ratio_2br,

            -- Can afford flag
            ((a.median_weekly_rent * 52.0) / k.median_annual_salary) <= {STRESS_THRESHOLD}   AS can_afford_median,
            ((a.median_rent_2br   * 52.0) / k.median_annual_salary) <= {STRESS_THRESHOLD}     AS can_afford_2br,

            -- SEIFA context
            a.irsd_decile,
            a.disadvantage_category

        FROM key_worker_salaries k
        CROSS JOIN affordability a
        WHERE a.median_weekly_rent IS NOT NULL
    """)
    count = con.execute("SELECT COUNT(*) FROM key_worker_affordability").fetchone()[0]
    print(f"    ✓ {count:,} occupation × suburb combinations")

    # ── 6. Stress hotspots view ─────────────────────────────────────────────
    print("  Building stress_hotspots view...")
    con.execute("""
        CREATE OR REPLACE VIEW stress_hotspots AS
        SELECT
            suburb,
            postcode,
            median_weekly_rent,
            ROUND(rent_to_income_ratio * 100, 1)    AS rent_pct_of_income,
            irsd_decile,
            disadvantage_category,
            ROUND(vulnerability_score * 100, 1)     AS vulnerability_score_pct
        FROM affordability
        WHERE in_rental_stress = true
          AND irsd_decile IS NOT NULL
        ORDER BY vulnerability_score DESC
    """)
    count = con.execute("SELECT COUNT(*) FROM stress_hotspots").fetchone()[0]
    print(f"    ✓ {count:,} stress hotspots identified")


def print_summary(con: duckdb.DuckDBPyConnection):
    print("\n── Affordability Summary ──")

    top_stress = con.execute("""
        SELECT suburb, median_weekly_rent, ROUND(rent_to_income_ratio*100,1) AS rent_pct,
               irsd_decile, disadvantage_category
        FROM affordability
        WHERE in_rental_stress = true
        ORDER BY vulnerability_score DESC NULLS LAST
        LIMIT 8
    """).fetchdf()

    print("\n  Top stress hotspots:")
    print(top_stress.to_string(index=False))

    nurse_suburbs = con.execute("""
        SELECT suburb, median_annual_salary, median_weekly_rent,
               ROUND(stress_ratio*100,1) AS stress_pct, can_afford_median
        FROM key_worker_affordability
        WHERE occupation = 'registered_nurse'
        ORDER BY suburb
        LIMIT 8
    """).fetchdf()

    print("\n  Nurse affordability by suburb:")
    print(nurse_suburbs.to_string(index=False))


if __name__ == "__main__":
    print("Perth Rental Affordability Tracker — Build Analytics Tables")
    print("=" * 60)

    con = duckdb.connect(DB_PATH)
    build_affordability_tables(con)
    print_summary(con)
    con.close()

    print(f"\n✓ Analytics tables built in: {DB_PATH}")
    print("  Next: python scripts/04_verify.py")
