"""
Fix crime safety scores in the database.
The safety_score is 0-10 where 10 = safest.
This recalculates relative to Perth average so labels are accurate.
Run: uv run python scripts/fix_crime_scores.py
"""
import duckdb, pandas as pd

con = duckdb.connect("data/rental.duckdb")

try:
    df = con.execute("SELECT * FROM suburb_crime").fetchdf()
    print(f"Loaded {len(df)} crime records")
    print("Current safety_score range:", df["safety_score"].min(), "to", df["safety_score"].max())

    # Recalculate safety score relative to Perth average
    df["total_crime"] = df["burglary"] + df["vehicle_theft"] + df["assault"] + df["property_damage"]
    
    # Use percentile-based scoring so labels reflect actual distribution
    p20 = df["total_crime"].quantile(0.20)
    p40 = df["total_crime"].quantile(0.40)
    p60 = df["total_crime"].quantile(0.60)
    p80 = df["total_crime"].quantile(0.80)
    
    print(f"\nCrime distribution: p20={p20:.0f} p40={p40:.0f} p60={p60:.0f} p80={p80:.0f}")

    def score(total):
        if total <= p20: return 9.0
        if total <= p40: return 7.0
        if total <= p60: return 5.0
        if total <= p80: return 3.0
        return 1.0

    def label(s):
        if s >= 8:   return "Very low crime"
        if s >= 6:   return "Low crime"
        if s >= 4:   return "Average for Perth"
        if s >= 2:   return "Above average"
        return "High crime area"

    df["safety_score"] = df["total_crime"].apply(score)
    df["safety_label"] = df["safety_score"].apply(label)

    print("\nUpdated label distribution:")
    print(df["safety_label"].value_counts())

    con.execute("DROP TABLE IF EXISTS suburb_crime")
    con.execute("CREATE TABLE suburb_crime AS SELECT * FROM df")
    print("\nDone. Restart the app.")

except Exception as e:
    print(f"Error: {e}")

con.close()
