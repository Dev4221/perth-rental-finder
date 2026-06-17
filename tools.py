"""
tools.py — RAG-enhanced tools for the Perth Rental Finder.
Built for anyone looking for a rental in Perth — not occupation-specific.
"""

from typing import Optional
import pandas as pd
import database as db


# ── Helpers ────────────────────────────────────────────────────────────────

def _bool(val) -> bool:
    if val is None:
        return False
    try:
        return bool(val)
    except Exception:
        return False

def _safe_float(val, default=0.0) -> float:
    if val is None or (hasattr(val, '__class__') and 'NA' in val.__class__.__name__):
        return default
    try:
        return float(val)
    except Exception:
        return default


# ── RAG context builder ────────────────────────────────────────────────────

def build_suburb_context(suburb: str) -> str:
    """
    Pull everything we know about a suburb and return a plain-English
    context block the agent reads before answering.

    Resolves the suburb name via dim_suburb_alias first (the same warehouse
    main.py now uses, built in steps A-E of this session), so this covers
    all ~1,222 suburbs in dim_suburb rather than only the 26 in the
    affordability table. Previously this queried affordability/rent_trend/
    tenancy_duration directly via UPPER(suburb)=UPPER(?), which not only
    missed suburbs outside the original 26 but also bypassed the casing/
    whitespace alias normalization built in build_dim_suburb.py — the same
    root-cause class of bug already fixed in main.py.
    """
    try:
        tables = [t for (t,) in db.get_connection().execute("SHOW TABLES").fetchall()]
        if "dim_suburb" not in tables:
            # Warehouse not built yet — fall back to the old direct query so
            # this doesn't hard-fail before steps A-E have been run.
            return _build_suburb_context_legacy(suburb)

        resolved = db.query_df("""
            SELECT s.suburb_key, s.suburb_name, s.postcode, s.has_rich_stats
            FROM dim_suburb_alias a
            JOIN dim_suburb s ON s.suburb_key = a.suburb_key
            WHERE UPPER(a.alias_raw) = UPPER(?)
            LIMIT 1
        """, [suburb])

        if resolved.empty:
            close = db.query_df("""
                SELECT DISTINCT s.suburb_name FROM dim_suburb_alias a
                JOIN dim_suburb s ON s.suburb_key = a.suburb_key
                WHERE UPPER(a.alias_raw) LIKE UPPER(?) LIMIT 5
            """, [f"%{suburb}%"])
            if not close.empty:
                return f"No exact match for '{suburb}'. Similar suburbs: {', '.join(close['suburb_name'].tolist())}."
            return f"No data found for '{suburb}'."

        r = resolved.iloc[0]
        suburb_key = int(r["suburb_key"])

        profile = db.query_df("""
            SELECT median_rent_2br, median_rent_3br, total_tenancies,
                   avg_tenancy_years, dispute_rate_pct, disadvantage_category,
                   irsd_decile, ato_median_income
            FROM fact_suburb_profile WHERE suburb_key = ?
        """, [suburb_key])

        rent_row = db.query_df("""
            SELECT median_weekly_rent, month_key FROM fact_rent_trend
            WHERE suburb_key = ? ORDER BY month_key DESC LIMIT 1
        """, [suburb_key])

        trend = db.query_df("""
            SELECT month_key as month, median_weekly_rent
            FROM fact_rent_trend WHERE suburb_key = ? ORDER BY month_key
        """, [suburb_key])

        lines = [f"SUBURB: {r['suburb_name']} (postcode {r['postcode']})", ""]

        lines.append("RENT:")
        if not rent_row.empty and pd.notna(rent_row.iloc[0]["median_weekly_rent"]):
            lines.append(f"  Median weekly rent: {rent_row.iloc[0]['median_weekly_rent']:.0f}/wk "
                         f"(as of {rent_row.iloc[0]['month_key']})")
        else:
            lines.append("  No rent data available for this suburb.")

        p = profile.iloc[0] if not profile.empty else None
        if p is not None and pd.notna(p.get("median_rent_2br")):
            lines.append(f"  2-bedroom median: {p['median_rent_2br']:.0f}/wk")
        if p is not None and pd.notna(p.get("median_rent_3br")):
            lines.append(f"  3-bedroom median: {p['median_rent_3br']:.0f}/wk")
        if p is not None and pd.notna(p.get("total_tenancies")):
            lines.append(f"  Number of rentals in dataset: {int(p['total_tenancies']):,}")

        lines.append("")
        lines.append("AREA CHARACTER:")
        if p is not None and pd.notna(p.get("ato_median_income")):
            lines.append(f"  Typical local income: {p['ato_median_income']:,.0f}/yr")

        irsd = p.get("irsd_decile") if p is not None else None
        disadv = p.get("disadvantage_category", "") if p is not None else ""
        if p is not None and pd.notna(irsd):
            try:
                irsd_int = int(irsd)
                if irsd_int <= 2: area_desc = "lower income working class area"
                elif irsd_int <= 4: area_desc = "modest income suburban area"
                elif irsd_int <= 6: area_desc = "middle income suburban area"
                elif irsd_int <= 8: area_desc = "comfortable middle class suburb"
                else: area_desc = "affluent, well-resourced suburb"
                lines.append(f"  Area type: {area_desc} (SEIFA decile {irsd_int}/10)")
            except Exception:
                lines.append(f"  Area type: {disadv}")
        else:
            lines.append(f"  Area type: {disadv}" if disadv else "  Area type: data not available "
                         "(this suburb is outside the ~26 with detailed affordability/SEIFA data)")

        if p is not None and pd.notna(p.get("avg_tenancy_years")) and bool(r.get("has_rich_stats")):
            yrs = _safe_float(p.get("avg_tenancy_years"), 1.5)
            if yrs >= 2.0:
                stability = f"very stable — renters stay an average of {yrs:.1f} years, well above Perth average"
            elif yrs >= 1.5:
                stability = f"stable — renters stay about {yrs:.1f} years on average"
            else:
                stability = f"higher turnover — renters stay about {yrs:.1f} years on average"
            lines.append(f"  Community stability: {stability}")
            if pd.notna(p.get("dispute_rate_pct")):
                lines.append(f"  Bond return rate: {p['dispute_rate_pct']:.0f}% of tenants get some bond back")
        # Note: when has_rich_stats is False, avg_tenancy_years/dispute_rate_pct
        # may still be present as a region-wide fallback (see main.py's
        # get_all_suburbs_data) — deliberately NOT presented here as this
        # suburb's own figure, same small-area-estimation boundary as main.py.

        if not trend.empty and len(trend) >= 3:
            lines.append("")
            lines.append("RENT TREND:")
            oldest, newest = trend.iloc[0], trend.iloc[-1]
            change = newest["median_weekly_rent"] - oldest["median_weekly_rent"]
            pct = change / oldest["median_weekly_rent"] * 100 if oldest["median_weekly_rent"] > 0 else 0
            direction = "risen" if change > 0 else "fallen"
            lines.append(f"  {oldest['month']} to {newest['month']}: {direction} {abs(pct):.0f}% "
                         f"({oldest['median_weekly_rent']:.0f}/wk to {newest['median_weekly_rent']:.0f}/wk)")
            lines.append("  Recent months:")
            for _, row in trend.tail(4).iterrows():
                lines.append(f"    {row['month']}: {row['median_weekly_rent']:.0f}/wk")

        return "\n".join(lines)

    except Exception as e:
        return f"Error looking up '{suburb}': {e}"


def _build_suburb_context_legacy(suburb: str) -> str:
    """Original implementation, queries staging tables directly. Used only
    as a fallback if the Phase 1 warehouse (dim_suburb etc.) hasn't been
    built yet — see build_suburb_context above."""
    try:
        aff = db.query_df("""
            SELECT suburb, postcode, median_weekly_rent, median_rent_2br, median_rent_3br,
                   total_tenancies, median_annual_income,
                   ROUND(rent_to_income_ratio * 100, 1) AS stress_pct,
                   in_rental_stress, IRSD_DECILE AS irsd_decile,
                   disadvantage_category
            FROM affordability
            WHERE UPPER(suburb) = UPPER(?)
            LIMIT 1
        """, [suburb])

        if aff.empty:
            close = db.query_df("""
                SELECT DISTINCT suburb FROM affordability
                WHERE UPPER(suburb) LIKE UPPER(?) LIMIT 5
            """, [f"%{suburb}%"])
            if not close.empty:
                return f"No exact match for '{suburb}'. Similar suburbs: {', '.join(close['suburb'].tolist())}."
            return f"No data found for '{suburb}'."

        r = aff.iloc[0]

        trend = db.query_df("""
            SELECT month, median_weekly_rent, tenancy_count
            FROM rent_trend
            WHERE UPPER(suburb) = UPPER(?)
            ORDER BY month
        """, [suburb])

        tenure = db.query_df("""
            SELECT median_years_held, dispute_rate_pct, total_bonds_ended
            FROM tenancy_duration
            WHERE UPPER(suburb) = UPPER(?)
            LIMIT 1
        """, [suburb])

        lines = [f"SUBURB: {r['suburb']} (postcode {r['postcode']})", ""]

        lines.append("RENT:")
        lines.append(f"  Median weekly rent: {r['median_weekly_rent']:.0f}/wk")
        if pd.notna(r.get('median_rent_2br')):
            lines.append(f"  2-bedroom median: {r['median_rent_2br']:.0f}/wk")
        if pd.notna(r.get('median_rent_3br')):
            lines.append(f"  3-bedroom median: {r['median_rent_3br']:.0f}/wk")
        lines.append(f"  Number of rentals in dataset: {int(r['total_tenancies']):,}")

        lines.append("")
        lines.append("AREA CHARACTER:")
        if pd.notna(r.get('median_annual_income')):
            lines.append(f"  Typical local income: {r['median_annual_income']:,.0f}/yr")

        irsd = r.get('irsd_decile')
        disadv = r.get('disadvantage_category', '')
        if pd.notna(irsd):
            try:
                irsd_int = int(irsd)
                if irsd_int <= 2:
                    area_desc = "lower income working class area"
                elif irsd_int <= 4:
                    area_desc = "modest income suburban area"
                elif irsd_int <= 6:
                    area_desc = "middle income suburban area"
                elif irsd_int <= 8:
                    area_desc = "comfortable middle class suburb"
                else:
                    area_desc = "affluent, well-resourced suburb"
                lines.append(f"  Area type: {area_desc} (SEIFA decile {irsd_int}/10)")
            except Exception:
                lines.append(f"  Area type: {disadv}")
        else:
            lines.append(f"  Area type: {disadv}" if disadv else "  Area type: data not available")

        if not tenure.empty:
            t = tenure.iloc[0]
            yrs = _safe_float(t.get('median_years_held'), 1.5)
            if yrs >= 2.0:
                stability = f"very stable — renters stay an average of {yrs:.1f} years, well above Perth average"
            elif yrs >= 1.5:
                stability = f"stable — renters stay about {yrs:.1f} years on average"
            else:
                stability = f"higher turnover — renters stay about {yrs:.1f} years on average"
            lines.append(f"  Community stability: {stability}")
            disputes = _safe_float(t.get('dispute_rate_pct'), 0)
            lines.append(f"  Bond return rate: {disputes:.0f}% of tenants get some bond back")

        if not trend.empty and len(trend) >= 3:
            lines.append("")
            lines.append("RENT TREND:")
            oldest = trend.iloc[0]
            newest = trend.iloc[-1]
            change = newest['median_weekly_rent'] - oldest['median_weekly_rent']
            pct    = change / oldest['median_weekly_rent'] * 100 if oldest['median_weekly_rent'] > 0 else 0
            direction = "risen" if change > 0 else "fallen"
            lines.append(f"  {oldest['month']} to {newest['month']}: {direction} {abs(pct):.0f}% ({oldest['median_weekly_rent']:.0f}/wk to {newest['median_weekly_rent']:.0f}/wk)")
            lines.append("  Recent months:")
            for _, row in trend.tail(4).iterrows():
                lines.append(f"    {row['month']}: {row['median_weekly_rent']:.0f}/wk")

        return "\n".join(lines)

    except Exception as e:
        return f"Error looking up '{suburb}': {e}"


def build_perth_context() -> str:
    """Perth-wide overview."""
    try:
        trend = db.query_df("""
            SELECT month, median_rent, p25_rent, p75_rent
            FROM perth_monthly_trend ORDER BY month
        """)

        hotspots = db.query_df("""
            SELECT suburb, median_weekly_rent, rent_pct_of_income,
                   IRSD_DECILE AS irsd_decile, disadvantage_category,
                   vulnerability_score_pct
            FROM stress_hotspots ORDER BY vulnerability_score_pct DESC LIMIT 10
        """)

        total   = db.query_one("SELECT COUNT(*) FROM rental_bonds")
        suburbs = db.query_one("SELECT COUNT(DISTINCT suburb) FROM affordability")

        lines = ["PERTH RENTAL OVERVIEW", ""]
        lines.append(f"Dataset: {total:,} real rental bonds across {suburbs:,} suburbs, March 2023 to May 2026")

        if len(trend) >= 2:
            fr  = float(trend.iloc[0]['median_rent'])
            lr  = float(trend.iloc[-1]['median_rent'])
            fr25 = float(trend.iloc[0]['p25_rent'])
            lr25 = float(trend.iloc[-1]['p25_rent'])
            pct = round((lr/fr - 1)*100)
            pct25 = round((lr25/fr25 - 1)*100)
            lines.append(f"Perth median rent today: {lr:.0f}/wk (was {fr:.0f}/wk in March 2023, +{pct}%)")
            lines.append(f"Cheapest 25% of rentals: {lr25:.0f}/wk (was {fr25:.0f}/wk, +{pct25}%)")

        if not hotspots.empty:
            lines.append("")
            lines.append("MOST STRESSED SUBURBS (high rent relative to incomes):")
            for i, (_, h) in enumerate(hotspots.iterrows(), 1):
                lines.append(
                    f"  {i}. {h['suburb']:<20} {h['median_weekly_rent']:.0f}/wk  "
                    f"{h['rent_pct_of_income']:.0f}% of local income"
                )

        return "\n".join(lines)
    except Exception as e:
        return f"Error building Perth overview: {e}"


# ── Tool schemas ───────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "lookup_suburb",
        "description": (
            "Get detailed rental data for a specific Perth suburb — rent prices, "
            "2-bedroom and 3-bedroom medians, rent trend over time, area character "
            "(income level, community stability, how long renters stay), and bond return rate. "
            "Use for any suburb-specific question including safety, cost, community feel, or trends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suburb": {
                    "type": "string",
                    "description": "Perth suburb name, e.g. 'Armadale', 'Fremantle', 'Joondalup'"
                }
            },
            "required": ["suburb"]
        }
    },
    {
        "name": "compare_suburbs",
        "description": (
            "Compare two Perth suburbs side by side — rent, community character, "
            "tenancy stability, area income level, and rent trends. "
            "Use when someone asks to compare two places."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suburb_a": {"type": "string", "description": "First suburb"},
                "suburb_b": {"type": "string", "description": "Second suburb"}
            },
            "required": ["suburb_a", "suburb_b"]
        }
    },
    {
        "name": "find_cheap_suburbs",
        "description": (
            "Find the most affordable Perth suburbs within a given budget. "
            "Use for questions like 'cheapest suburbs', 'what can I afford for X/wk', "
            "'suburbs under X dollars per week', 'most affordable areas'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_rent": {
                    "type": "number",
                    "description": "Maximum weekly rent in dollars, e.g. 500"
                },
                "min_rent": {
                    "type": "number",
                    "description": "Minimum weekly rent (optional), e.g. 300"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 10)",
                    "default": 10
                }
            },
            "required": ["max_rent"]
        }
    },
    {
        "name": "get_rent_trend",
        "description": (
            "Get how rent has changed over time in a Perth suburb. "
            "Use for 'has rent gone up in X', 'rent trend', 'how has rent changed'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suburb": {"type": "string", "description": "Perth suburb name"},
                "months": {
                    "type": "integer",
                    "description": "Months of history to show (default 12)",
                    "default": 12
                }
            },
            "required": ["suburb"]
        }
    },
    {
        "name": "get_perth_overview",
        "description": (
            "Get a Perth-wide rental overview — median rent, rent trends, "
            "most stressed suburbs. Use for general Perth questions."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "find_suburbs_near",
        "description": (
            "Find affordable suburbs near a specific Perth location or landmark. "
            "Use for 'near Fremantle', 'close to the beach', 'near Fiona Stanley Hospital', "
            "'within 20 minutes of the CBD'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location or landmark, e.g. 'Fremantle', 'Fiona Stanley Hospital', 'CBD', 'beach'"
                },
                "max_rent": {
                    "type": "number",
                    "description": "Maximum weekly rent budget (optional)"
                }
            },
            "required": ["location"]
        }
    }
]


# ── Tool implementations ───────────────────────────────────────────────────

def lookup_suburb(suburb: str) -> str:
    return build_suburb_context(suburb)


def compare_suburbs(suburb_a: str, suburb_b: str) -> str:
    return build_suburb_context(suburb_a) + "\n\n" + "="*50 + "\n\n" + build_suburb_context(suburb_b)


def find_cheap_suburbs(max_rent: float, min_rent: float = 0, max_results: int = 10) -> str:
    """Reads from the warehouse (fact_rent_trend, the latest month per
    suburb_key) rather than the affordability table directly. affordability
    only covers ~26 suburbs — using it as the base table here would have
    silently limited every budget search to that set. fact_suburb_profile is
    joined for extra context where available, but is NOT required (its
    total_tenancies/etc. are NULL for suburbs outside the 26, by design —
    see fact_suburb_profile's docstring in build_fact_suburb_profile.py)."""
    try:
        tables = [t for (t,) in db.get_connection().execute("SHOW TABLES").fetchall()]
        if "dim_suburb" not in tables or "fact_rent_trend" not in tables:
            return _find_cheap_suburbs_legacy(max_rent, min_rent, max_results)

        df = db.query_df("""
            WITH latest_rent AS (
                SELECT suburb_key, median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY suburb_key ORDER BY month_key DESC) as rn
                FROM fact_rent_trend
            )
            SELECT d.suburb_name as suburb, d.postcode, lr.median_weekly_rent,
                   p.median_rent_2br, p.total_tenancies,
                   p.disadvantage_category, p.irsd_decile, p.avg_tenancy_years
            FROM latest_rent lr
            JOIN dim_suburb d ON d.suburb_key = lr.suburb_key
            LEFT JOIN fact_suburb_profile p ON p.suburb_key = lr.suburb_key
            WHERE lr.rn = 1 AND lr.median_weekly_rent <= ? AND lr.median_weekly_rent >= ?
            ORDER BY lr.median_weekly_rent ASC,
                     COALESCE(p.total_tenancies, 0) DESC
            LIMIT ?
        """, [max_rent, min_rent, max_results])

        if df.empty:
            return f"No suburbs found with median rent under {max_rent:.0f}/wk. Try a higher budget."

        lines = [f"CHEAPEST SUBURBS UNDER {max_rent:.0f}/WK", ""]
        lines.append(f"{'Suburb':<22} {'Rent/wk':<12} {'2br':<12} {'Area type':<25} {'Stability'}")
        lines.append("-" * 85)

        for _, row in df.iterrows():
            rent   = row['median_weekly_rent']
            rent2  = f"{row['median_rent_2br']:.0f}/wk" if pd.notna(row.get('median_rent_2br')) else "–"
            disadv = row.get('disadvantage_category', '')
            tenure = _safe_float(row.get('avg_tenancy_years'), 0)
            stability = f"{tenure:.1f}yr avg" if tenure > 0 else "–"

            irsd = row.get('irsd_decile')
            disadv_clean = disadv if (disadv and pd.notna(disadv)) else None
            try:
                irsd_int = int(irsd) if pd.notna(irsd) else None
                if irsd_int is None:
                    area = disadv_clean or "data not available"
                elif irsd_int <= 3:
                    area = "lower income area"
                elif irsd_int <= 6:
                    area = "middle income suburb"
                else:
                    area = "comfortable suburb"
            except Exception:
                area = disadv_clean or "–"

            lines.append(
                f"{row['suburb']:<22} {rent:.0f}/wk{'':<6} {rent2:<12} {area:<25} {stability}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"Error finding cheap suburbs: {e}"


def _find_cheap_suburbs_legacy(max_rent: float, min_rent: float = 0, max_results: int = 10) -> str:
    """Original implementation (affordability table only, ~26 suburbs).
    Used only if the warehouse hasn't been built yet."""
    try:
        df = db.query_df("""
            SELECT a.suburb, a.postcode, a.median_weekly_rent,
                   a.median_rent_2br, a.total_tenancies,
                   a.disadvantage_category, a.IRSD_DECILE AS irsd_decile,
                   ss.avg_tenancy_years
            FROM affordability a
            LEFT JOIN suburb_stats ss ON UPPER(a.suburb)=UPPER(ss.suburb)
            WHERE a.median_weekly_rent <= ?
              AND a.median_weekly_rent >= ?
              AND a.total_tenancies > 50
            ORDER BY a.median_weekly_rent ASC, a.total_tenancies DESC
            LIMIT ?
        """, [max_rent, min_rent, max_results])

        if df.empty:
            return f"No suburbs found with median rent under {max_rent:.0f}/wk. Try a higher budget."

        lines = [f"CHEAPEST SUBURBS UNDER {max_rent:.0f}/WK", ""]
        lines.append(f"{'Suburb':<22} {'Rent/wk':<12} {'2br':<12} {'Area type':<25} {'Stability'}")
        lines.append("-" * 85)

        for _, row in df.iterrows():
            rent   = row['median_weekly_rent']
            rent2  = f"{row['median_rent_2br']:.0f}/wk" if pd.notna(row.get('median_rent_2br')) else "–"
            disadv = row.get('disadvantage_category', '')
            tenure = _safe_float(row.get('avg_tenancy_years'), 0)
            stability = f"{tenure:.1f}yr avg" if tenure > 0 else "–"

            # Plain English area description
            irsd = row.get('irsd_decile')
            try:
                irsd_int = int(irsd) if pd.notna(irsd) else 5
                if irsd_int <= 3:
                    area = "lower income area"
                elif irsd_int <= 6:
                    area = "middle income suburb"
                else:
                    area = "comfortable suburb"
            except Exception:
                area = disadv or "–"

            lines.append(
                f"{row['suburb']:<22} {rent:.0f}/wk{'':<6} {rent2:<12} {area:<25} {stability}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"Error finding cheap suburbs: {e}"


def get_rent_trend(suburb: str, months: int = 12) -> str:
    """Resolves via dim_suburb_alias + fact_rent_trend (the warehouse,
    steps A/C of this session) instead of querying rent_trend directly by
    raw string match — same reasoning as build_suburb_context above."""
    try:
        months = min(months, 36)
        tables = [t for (t,) in db.get_connection().execute("SHOW TABLES").fetchall()]
        if "dim_suburb" not in tables or "fact_rent_trend" not in tables:
            return _get_rent_trend_legacy(suburb, months)

        resolved = db.query_df("""
            SELECT s.suburb_key, s.suburb_name FROM dim_suburb_alias a
            JOIN dim_suburb s ON s.suburb_key = a.suburb_key
            WHERE UPPER(a.alias_raw) = UPPER(?) LIMIT 1
        """, [suburb])
        if resolved.empty:
            return f"No trend data found for '{suburb}'."

        suburb_key = int(resolved.iloc[0]["suburb_key"])
        canonical_name = resolved.iloc[0]["suburb_name"]

        df = db.query_df("""
            SELECT month_key as month, median_weekly_rent FROM fact_rent_trend
            WHERE suburb_key = ? ORDER BY month_key DESC LIMIT ?
        """, [suburb_key, months])

        if df.empty:
            return f"No trend data found for '{canonical_name}'."

        df = df.sort_values("month")
        oldest, newest = df.iloc[0], df.iloc[-1]
        change = newest['median_weekly_rent'] - oldest['median_weekly_rent']
        pct = change / oldest['median_weekly_rent'] * 100 if oldest['median_weekly_rent'] > 0 else 0
        direction = "risen" if change > 0 else "fallen"

        lines = [f"RENT TREND: {canonical_name}", ""]
        lines.append(f"Over {len(df)} months ({oldest['month']} to {newest['month']}):")
        lines.append(f"  Rent has {direction} {abs(pct):.0f}% — from {oldest['median_weekly_rent']:.0f}/wk to {newest['median_weekly_rent']:.0f}/wk")
        lines.append(f"  That is {abs(change):.0f}/wk more, or {abs(change)*52:.0f}/year")
        lines.append("")
        lines.append("Month by month:")
        for _, row in df.iterrows():
            lines.append(f"  {row['month']}: {row['median_weekly_rent']:.0f}/wk")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting trend for '{suburb}': {e}"


def _get_rent_trend_legacy(suburb: str, months: int = 12) -> str:
    """Original implementation, used only if the warehouse hasn't been built yet."""
    try:
        df = db.query_df("""
            SELECT month, median_weekly_rent, tenancy_count
            FROM rent_trend
            WHERE UPPER(suburb) = UPPER(?)
            ORDER BY month DESC LIMIT ?
        """, [suburb, months])

        if df.empty:
            return f"No trend data found for '{suburb}'."

        df = df.sort_values("month")
        oldest = df.iloc[0]
        newest = df.iloc[-1]
        change = newest['median_weekly_rent'] - oldest['median_weekly_rent']
        pct    = change / oldest['median_weekly_rent'] * 100 if oldest['median_weekly_rent'] > 0 else 0
        direction = "risen" if change > 0 else "fallen"

        lines = [f"RENT TREND: {suburb}", ""]
        lines.append(f"Over {len(df)} months ({oldest['month']} to {newest['month']}):")
        lines.append(f"  Rent has {direction} {abs(pct):.0f}% — from {oldest['median_weekly_rent']:.0f}/wk to {newest['median_weekly_rent']:.0f}/wk")
        lines.append(f"  That is {abs(change):.0f}/wk more, or {abs(change)*52:.0f}/year")
        lines.append("")
        lines.append("Month by month:")
        for _, row in df.iterrows():
            lines.append(f"  {row['month']}: {row['median_weekly_rent']:.0f}/wk ({int(row['tenancy_count'])} new tenancies)")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting trend for '{suburb}': {e}"


def get_perth_overview() -> str:
    return build_perth_context()


def find_suburbs_near(location: str, max_rent: Optional[float] = None) -> str:
    """Find suburbs near a Perth landmark or area."""

    LANDMARK_SUBURBS = {
        "fiona stanley":     ["Murdoch", "Kardinya", "Bull Creek", "Bibra Lake", "Spearwood"],
        "fsh":               ["Murdoch", "Kardinya", "Bull Creek", "Bibra Lake"],
        "royal perth":       ["Perth", "East Perth", "Northbridge", "Mount Lawley", "Highgate"],
        "rph":               ["Perth", "East Perth", "Northbridge"],
        "perth children":    ["Nedlands", "Subiaco", "Shenton Park", "Crawley"],
        "joondalup hospital":["Joondalup", "Edgewater", "Beldon", "Craigie"],
        "fremantle":         ["Fremantle", "North Fremantle", "South Fremantle", "Hamilton Hill", "Palmyra", "White Gum Valley"],
        "cbd":               ["Perth", "East Perth", "West Perth", "Northbridge", "Leederville", "Mount Lawley"],
        "city":              ["Perth", "East Perth", "Northbridge", "Leederville", "Mount Lawley"],
        "beach":             ["Scarborough", "Cottesloe", "Fremantle", "Rockingham", "Mandurah", "Hillarys", "Sorrento"],
        "coast":             ["Scarborough", "Cottesloe", "Fremantle", "Rockingham", "Mandurah", "Hillarys"],
        "kings park":        ["Subiaco", "Nedlands", "West Perth", "Crawley", "Shenton Park"],
        "airport":           ["Redcliffe", "Belmont", "Cloverdale", "Rivervale", "Forrestfield"],
        "joondalup":         ["Joondalup", "Edgewater", "Beldon", "Craigie", "Currambine"],
        "midland":           ["Midland", "Bassendean", "Bayswater", "Morley", "Noranda"],
        "armadale":          ["Armadale", "Gosnells", "Maddington", "Thornlie", "Kelmscott"],
        "rockingham":        ["Rockingham", "Baldivis", "Safety Bay", "Warnbro", "Port Kennedy"],
        "mandurah":          ["Mandurah", "Pinjarra", "Halls Head", "Meadow Springs", "Greenfields"],
        "south of the river":["Fremantle", "Cockburn", "Rockingham", "Mandurah", "Armadale", "Gosnells"],
        "north of the river":["Joondalup", "Wanneroo", "Stirling", "Morley", "Midland", "Swan"],
    }

    loc_lower = location.lower().strip()
    matched_suburbs = []

    # Two-pass matching, same reasoning as find_suburb_mentions in main.py:
    # full-key matches are strong evidence and should win over a generic
    # word-overlap fallback. Without this, "Joondalup" (no qualifier) could
    # match the "joondalup hospital" key instead of the plain "joondalup"
    # key, since "joondalup" is also a substring of "joondalup hospital".
    # Sorting candidates by key length (longest first) means the most
    # specific real match wins when more than one key is contained in the
    # input text (e.g. "near joondalup hospital" contains both "joondalup"
    # and "joondalup hospital" as substrings - the longer, more specific
    # one should win).
    full_matches = [key for key in LANDMARK_SUBURBS if key in loc_lower]
    full_matches.sort(key=len, reverse=True)
    if full_matches:
        matched_suburbs = LANDMARK_SUBURBS[full_matches[0]]
    else:
        # Fallback: a single short, common word (e.g. "north", "city") is
        # weak evidence on its own and risks false positives on ordinary
        # conversational text ("I live north" should not silently resolve
        # to "north of the river"). Require at least 2 of the key's words
        # to appear, or the key to be a single distinctive word of
        # meaningful length, before accepting a fallback match.
        for key, suburbs in LANDMARK_SUBURBS.items():
            key_words = key.split()
            matches = sum(1 for w in key_words if w in loc_lower)
            if (len(key_words) >= 2 and matches >= 2) or (len(key_words) == 1 and len(key) > 5 and key in loc_lower):
                matched_suburbs = suburbs
                break

    if not matched_suburbs:
        return f"I don't have specific suburb proximity data for '{location}'. Try searching for a specific suburb name instead."

    lines = [f"SUBURBS NEAR {location.upper()}", ""]

    for suburb in matched_suburbs:
        ctx = build_suburb_context(suburb)
        # Extract just the rent line. build_suburb_context's "Median weekly
        # rent" line may include a trailing "(as of YYYY-MM)" — strip that
        # before display so the response doesn't show date metadata inline.
        for line in ctx.split("\n"):
            if "Median weekly rent:" in line or "2-bedroom median:" in line:
                rent_str = line.strip()
                rent_value_str = rent_str.split(":")[1].strip().split("(")[0].strip()
                if max_rent:
                    try:
                        rent_num = float(rent_value_str.split("/")[0])
                        if rent_num <= max_rent * 1.2:
                            lines.append(f"- {suburb}: {rent_value_str}")
                    except Exception:
                        lines.append(f"- {suburb}: {rent_value_str}")
                else:
                    lines.append(f"- {suburb}: {rent_value_str}")
                break

    if len(lines) <= 2:
        lines.append("(All nearby suburbs are above your budget — try widening your range)")

    lines.append("")
    lines.append(f"For full details on any of these, ask me to look up a specific suburb.")
    return "\n".join(lines)


# ── Dispatcher ─────────────────────────────────────────────────────────────

def call_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "lookup_suburb":     lambda i: lookup_suburb(i["suburb"]),
        "compare_suburbs":   lambda i: compare_suburbs(i["suburb_a"], i["suburb_b"]),
        "find_cheap_suburbs":lambda i: find_cheap_suburbs(
            i["max_rent"],
            min_rent=i.get("min_rent", 0),
            max_results=i.get("max_results", 10)
        ),
        "get_rent_trend":    lambda i: get_rent_trend(i["suburb"], i.get("months", 12)),
        "get_perth_overview":lambda i: get_perth_overview(),
        "find_suburbs_near": lambda i: find_suburbs_near(
            i["location"], max_rent=i.get("max_rent")
        ),
        # Legacy names kept for backward compatibility
        "query_affordability":    lambda i: lookup_suburb(i.get("suburb", "")),
        "check_key_worker":       lambda i: find_cheap_suburbs(i.get("max_rent", 700)),
        "get_trend":              lambda i: get_rent_trend(i.get("suburb", "")),
        "find_stress_hotspots":   lambda i: get_perth_overview(),
        "find_affordable_suburbs":lambda i: find_cheap_suburbs(700),
        "get_hotspots":           lambda i: get_perth_overview(),
    }
    fn = dispatch.get(name)
    if fn:
        return fn(inputs)
    return f"Unknown tool: {name}"
