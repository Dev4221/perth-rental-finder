"""
database.py
DuckDB connection manager and low-level query helpers.
"""

import os
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")

# Module-level connection (reused across Streamlit reruns)
_connection: Optional[duckdb.DuckDBPyConnection] = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get (or create) the shared DuckDB connection."""
    global _connection
    if _connection is None:
        if not Path(DB_PATH).exists():
            raise FileNotFoundError(
                f"Database not found: {DB_PATH}\n"
                "Run the setup scripts first:\n"
                "  python scripts/01_download_data.py\n"
                "  python scripts/02_ingest_duckdb.py\n"
                "  python scripts/03_build_affordability.py"
            )
        _connection = duckdb.connect(DB_PATH, read_only=True)
    return _connection


def query_df(sql: str, params: list = None) -> pd.DataFrame:
    """Execute a SQL query and return a DataFrame."""
    con = get_connection()
    if params:
        return con.execute(sql, params).fetchdf()
    return con.execute(sql).fetchdf()


def query_one(sql: str, params: list = None):
    """Execute a SQL query and return the first value."""
    con = get_connection()
    if params:
        result = con.execute(sql, params).fetchone()
    else:
        result = con.execute(sql).fetchone()
    return result[0] if result else None


# ─────────────────────────────────────────────
# High-level query functions used by tools.py
# ─────────────────────────────────────────────

def get_suburb_affordability(suburb: str, bedrooms: Optional[int] = None) -> pd.DataFrame:
    """Get affordability data for a suburb."""
    if bedrooms:
        sql = """
            SELECT
                srs.suburb, srs.postcode, srs.bedrooms, srs.dwelling_type,
                srs.median_weekly_rent, srs.tenancy_count,
                a.median_annual_income, a.rent_to_income_ratio,
                a.in_rental_stress, a.irsd_decile, a.disadvantage_category
            FROM suburb_rent_summary srs
            LEFT JOIN affordability a ON srs.suburb = a.suburb
            WHERE UPPER(srs.suburb) = UPPER(?)
              AND srs.bedrooms = ?
            ORDER BY srs.dwelling_type
        """
        return query_df(sql, [suburb, bedrooms])
    else:
        sql = """
            SELECT
                a.suburb, a.postcode, a.median_weekly_rent,
                a.median_rent_2br, a.median_rent_3br,
                a.median_annual_income, a.rent_to_income_ratio,
                a.in_rental_stress, a.irsd_decile, a.disadvantage_category,
                a.total_tenancies
            FROM affordability a
            WHERE UPPER(a.suburb) = UPPER(?)
        """
        return query_df(sql, [suburb])


def get_key_worker_affordability(occupation: str, suburb: Optional[str] = None) -> pd.DataFrame:
    """Get affordability for a key worker, optionally filtered by suburb."""
    if suburb:
        sql = """
            SELECT *,
                ROUND(stress_ratio * 100, 1) AS rent_pct_of_income,
                ROUND(stress_ratio_2br * 100, 1) AS rent_pct_2br
            FROM key_worker_affordability
            WHERE occupation = LOWER(?)
              AND UPPER(suburb) = UPPER(?)
        """
        return query_df(sql, [occupation, suburb])
    else:
        sql = """
            SELECT *,
                ROUND(stress_ratio * 100, 1) AS rent_pct_of_income,
                ROUND(stress_ratio_2br * 100, 1) AS rent_pct_2br
            FROM key_worker_affordability
            WHERE occupation = LOWER(?)
            ORDER BY stress_ratio ASC
        """
        return query_df(sql, [occupation])


def get_rent_trend(suburb: str, bedrooms: Optional[int], months: int = 12) -> pd.DataFrame:
    """Get rent trend for a suburb over the last N months."""
    if bedrooms:
        sql = """
            SELECT month, bedrooms, median_weekly_rent, tenancy_count
            FROM rent_trend
            WHERE UPPER(suburb) = UPPER(?)
              AND bedrooms = ?
            ORDER BY month DESC
            LIMIT ?
        """
        return query_df(sql, [suburb, bedrooms, months])
    else:
        sql = """
            SELECT month, bedrooms, median_weekly_rent, tenancy_count
            FROM rent_trend
            WHERE UPPER(suburb) = UPPER(?)
            ORDER BY month DESC, bedrooms
            LIMIT ?
        """
        return query_df(sql, [suburb, months * 4])


def get_affordable_suburbs_for_occupation(occupation: str, max_bedrooms: Optional[int] = 2) -> pd.DataFrame:
    """Get suburbs where a given occupation can afford to rent."""
    sql = """
        SELECT
            suburb, postcode, display_name, median_annual_salary,
            median_weekly_rent, median_rent_2br,
            ROUND(stress_ratio * 100, 1)     AS rent_pct_of_income,
            ROUND(stress_ratio_2br * 100, 1) AS rent_2br_pct,
            can_afford_median, can_afford_2br,
            irsd_decile, disadvantage_category
        FROM key_worker_affordability
        WHERE occupation = LOWER(?)
          AND can_afford_2br = true
        ORDER BY stress_ratio_2br ASC
        LIMIT 20
    """
    return query_df(sql, [occupation])


def get_stress_hotspots(top_n: int = 15) -> pd.DataFrame:
    """Get suburbs with highest vulnerability (stress + disadvantage)."""
    sql = """
        SELECT
            suburb, postcode, median_weekly_rent,
            rent_pct_of_income, irsd_decile,
            disadvantage_category, vulnerability_score_pct
        FROM stress_hotspots
        LIMIT ?
    """
    return query_df(sql, [top_n])


def get_all_suburbs() -> list:
    """Get sorted list of all suburbs in the database."""
    df = query_df("SELECT DISTINCT suburb FROM affordability ORDER BY suburb")
    return df["suburb"].tolist()


def get_all_occupations() -> pd.DataFrame:
    """Get all key worker occupations with their salaries."""
    return query_df("SELECT occupation, display_name, median_annual_salary FROM key_worker_salaries ORDER BY display_name")


def get_summary_stats() -> dict:
    """Get high-level summary statistics for the dashboard header."""
    stats = {}
    try:
        stats["total_suburbs"] = query_one("SELECT COUNT(DISTINCT suburb) FROM affordability")
        stats["total_tenancies"] = query_one("SELECT COUNT(*) FROM rental_bonds")
        stats["pct_in_stress"] = query_one("""
            SELECT ROUND(100.0 * SUM(CASE WHEN in_rental_stress THEN 1 ELSE 0 END) / COUNT(*), 0)
            FROM affordability WHERE rent_to_income_ratio IS NOT NULL
        """)
        stats["median_rent_perth"] = query_one("SELECT MEDIAN(median_weekly_rent) FROM affordability")
        stats["most_affordable"] = query_one("""
            SELECT suburb FROM affordability
            WHERE rent_to_income_ratio IS NOT NULL
            ORDER BY rent_to_income_ratio ASC LIMIT 1
        """)
        stats["least_affordable"] = query_one("""
            SELECT suburb FROM affordability
            WHERE rent_to_income_ratio IS NOT NULL
            ORDER BY rent_to_income_ratio DESC LIMIT 1
        """)
    except Exception:
        pass
    return stats


def get_compare_suburbs(suburb_a: str, suburb_b: str, annual_income: Optional[float] = None) -> pd.DataFrame:
    """Compare affordability between two suburbs."""
    sql = """
        SELECT
            suburb, postcode, median_weekly_rent, median_rent_2br, median_rent_3br,
            median_annual_income, ROUND(rent_to_income_ratio * 100, 1) AS rent_pct,
            in_rental_stress, irsd_decile, disadvantage_category,
            ROUND(median_weekly_rent * 52 / NULLIF(?, 0) * 100, 1) AS custom_income_rent_pct
        FROM affordability
        WHERE UPPER(suburb) IN (UPPER(?), UPPER(?))
        ORDER BY suburb
    """
    income = annual_income or 0
    return query_df(sql, [income, suburb_a, suburb_b])
