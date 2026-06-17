"""
test_data_model.py — Phase 1, step F

Validates the warehouse built in steps A-E. Every check prints PASS/FAIL.
This is the gate before step G (rewiring main.py onto these tables).

Run: uv run python test_data_model.py
(read-only checks only — safe to run with the server running, no need to stop it)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb

DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
conn = duckdb.connect(DB_PATH, read_only=True)

failures = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not passed:
        failures.append(label)

print("=" * 70)
print("1. REFERENTIAL INTEGRITY — every fact row's suburb_key exists in dim_suburb")
print("=" * 70)
for fact_table in ["fact_rent_trend", "fact_suburb_profile", "fact_suburb_amenities"]:
    tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
    if fact_table not in tables:
        check(f"{fact_table} referential integrity", False, "table not found, skipped")
        continue
    orphans = conn.execute(f"""
        SELECT COUNT(*) FROM {fact_table} f
        LEFT JOIN dim_suburb d ON d.suburb_key = f.suburb_key
        WHERE d.suburb_key IS NULL
    """).fetchone()[0]
    check(f"{fact_table} — no orphan suburb_key", orphans == 0,
          f"{orphans} orphan rows" if orphans else "all rows resolve")

print("\n" + "=" * 70)
print("2. NO DUPLICATE FACT ROWS")
print("=" * 70)
dup = conn.execute("""
    SELECT COUNT(*) FROM (
        SELECT suburb_key, month_key, COUNT(*) c FROM fact_rent_trend
        GROUP BY suburb_key, month_key HAVING COUNT(*) > 1
    )
""").fetchone()[0]
check("fact_rent_trend — one row per (suburb_key, month_key)", dup == 0,
      f"{dup} duplicate keys" if dup else "no duplicates")

for fact_table in ["fact_suburb_profile", "fact_suburb_amenities"]:
    tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
    if fact_table not in tables:
        check(f"{fact_table} — one row per suburb_key", False, "table not found, skipped")
        continue
    dup = conn.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT suburb_key, COUNT(*) c FROM {fact_table}
            GROUP BY suburb_key HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    check(f"{fact_table} — one row per suburb_key", dup == 0,
          f"{dup} duplicate suburb_keys" if dup else "no duplicates")

print("\n" + "=" * 70)
print("3. dim_suburb_alias — every alias points to a real suburb_key, no orphan aliases")
print("=" * 70)
orphan_alias = conn.execute("""
    SELECT COUNT(*) FROM dim_suburb_alias a
    LEFT JOIN dim_suburb d ON d.suburb_key = a.suburb_key
    WHERE d.suburb_key IS NULL
""").fetchone()[0]
check("dim_suburb_alias — no orphan suburb_key references", orphan_alias == 0,
      f"{orphan_alias} orphans" if orphan_alias else "all resolve")

dup_alias = conn.execute("""
    SELECT COUNT(*) FROM (
        SELECT alias_raw, COUNT(*) c FROM dim_suburb_alias
        GROUP BY alias_raw HAVING COUNT(*) > 1
    )
""").fetchone()[0]
check("dim_suburb_alias — no duplicate alias_raw (each spelling maps to exactly one suburb)",
      dup_alias == 0, f"{dup_alias} alias strings map to multiple suburbs" if dup_alias else "")

print("\n" + "=" * 70)
print("4. SPOT CHECKS — Maylands / Bayswater / Murdoch")
print("=" * 70)
for name in ["MAYLANDS", "BAYSWATER", "MURDOCH"]:
    row = conn.execute(f"""
        SELECT s.suburb_key, s.suburb_name, s.postcode, s.region, s.has_rich_stats,
               (SELECT COUNT(*) FROM dim_suburb_alias a WHERE a.suburb_key = s.suburb_key) as n_aliases,
               (SELECT COUNT(*) FROM fact_rent_trend f WHERE f.suburb_key = s.suburb_key) as n_rent_months
        FROM dim_suburb s WHERE UPPER(s.suburb_name) = '{name}'
    """).fetchdf()
    if row.empty:
        check(f"{name} resolves in dim_suburb", False, "not found")
    else:
        r = row.iloc[0]
        check(f"{name} resolves in dim_suburb", True,
              f"key={r['suburb_key']}, postcode={r['postcode']}, region={r['region']}, "
              f"rich={r['has_rich_stats']}, aliases={r['n_aliases']}, rent_months={r['n_rent_months']}")

print("\n" + "=" * 70)
print("5. has_rich_stats CONSISTENCY — flag should match actual profile data presence")
print("=" * 70)
mismatch = conn.execute("""
    SELECT COUNT(*) FROM dim_suburb d
    JOIN fact_suburb_profile p ON p.suburb_key = d.suburb_key
    WHERE d.has_rich_stats = true AND p.median_rent_2br IS NULL
""").fetchone()[0]
check("every has_rich_stats=true suburb has a populated profile", mismatch == 0,
      f"{mismatch} suburbs flagged rich but profile is empty" if mismatch else "consistent")

print("\n" + "=" * 70)
print("6. COVERAGE SUMMARY — answers the original '26 vs ~1163' question with real numbers")
print("=" * 70)
total = conn.execute("SELECT COUNT(*) FROM dim_suburb").fetchone()[0]
with_postcode = conn.execute("SELECT COUNT(*) FROM dim_suburb WHERE postcode IS NOT NULL").fetchone()[0]
with_rent = conn.execute("SELECT COUNT(DISTINCT suburb_key) FROM fact_rent_trend").fetchone()[0]
with_profile = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE median_rent_2br IS NOT NULL").fetchone()[0]
with_ato = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE ato_median_income IS NOT NULL").fetchone()[0]
with_seifa = conn.execute("SELECT COUNT(*) FROM fact_suburb_profile WHERE seifa_decile IS NOT NULL").fetchone()[0]
with_school = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE school_total IS NOT NULL").fetchone()[0]
with_train = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE nearest_station IS NOT NULL").fetchone()[0]
with_crime = conn.execute("SELECT COUNT(*) FROM fact_suburb_amenities WHERE safety_score IS NOT NULL").fetchone()[0]

print(f"  Total suburbs in dim_suburb:                  {total}")
print(f"  ...with a known postcode:                      {with_postcode}")
print(f"  ...with rent history (fact_rent_trend):        {with_rent}")
print(f"  ...with full affordability profile:            {with_profile}  (the original '26')")
print(f"  ...with ATO median income:                     {with_ato}")
print(f"  ...with SEIFA decile:                           {with_seifa}")
print(f"  ...with school data:                            {with_school}")
print(f"  ...with train proximity:                        {with_train}")
print(f"  ...with crime data:                             {with_crime}")

print("\nRegion distribution:")
regions = conn.execute("SELECT region, COUNT(*) n FROM dim_suburb GROUP BY region ORDER BY n DESC").fetchdf()
print(regions.to_string(index=False))

print("\n" + "=" * 70)
print(f"RESULT: {len(failures)} failing check(s)")
print("=" * 70)
if failures:
    print("FAILED CHECKS:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("All checks passed. Warehouse is ready for step G (rewire main.py).")
