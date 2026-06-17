"""
Diagnostic v7 — final validation of the integrated main.py.

Tests get_all_suburbs_data(), match_suburbs() across multiple budget ranges,
suburb_to_card()/suburb_deep_dive() across many suburbs (including ones with
sparse data), and find_suburb_mentions() — to catch any remaining pd.NA edge
cases across the full ~1,163-suburb dataset before live testing.

Usage:
  uv run python diagnose7.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows' default console encoding (cp1252) can't print characters like
# ↓ ↑ → or — that appear in main.py's output (trend arrows, em-dashes).
# Force UTF-8 stdout so this script's prints don't crash on them, regardless
# of the terminal's default codepage.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import main as app
import pandas as pd

print("=" * 70)
print("STEP 1: get_all_suburbs_data() — basic shape")
print("=" * 70)
try:
    df = app.get_all_suburbs_data()
    print(f"Total rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print(f"Rows with postcode: {df['postcode'].notna().sum()}")
    print(f"Rows with median_rent_2br: {df['median_rent_2br'].notna().sum()}")
    print(f"Rows with has_train_1km not NA: {df['has_train_1km'].notna().sum()}")
    print(f"Rows with safety_score not NA: {df['safety_score'].notna().sum()}")
    print(f"Rows with total_tenancies not NA: {df['total_tenancies'].notna().sum()}")

    print("\nMaylands / Bayswater / Murdoch / Fremantle rows:")
    sample = df[df["suburb"].str.upper().isin(["MAYLANDS","BAYSWATER","MURDOCH","FREMANTLE"])]
    print(sample.to_string(index=False))
except Exception as e:
    import traceback
    traceback.print_exc()
    df = None

print("\n" + "=" * 70)
print("STEP 2: match_suburbs() across a range of budgets (catch pd.NA crashes)")
print("=" * 70)
test_cases = [
    (500, 700, "Near Fiona Stanley Hospital"),
    (500, 700, "Tell me about Maylands"),
    (300, 450, "cheap suburbs for a student"),
    (800, 1200, "near Cottesloe Beach"),
    (400, 600, "near Joondalup with a dog"),
    (1500, 2500, "luxury suburb near the river"),
    (200, 350, "regional WA cheap rent"),
]
for min_r, max_r, msg in test_cases:
    try:
        results, also = app.match_suburbs(min_r, max_r, msg)
        print(f"OK   ${min_r}-${max_r} {msg!r:35} -> primary={[r['suburb'] for r in results]}, also={[r['suburb'] for r in also]}")
    except Exception as e:
        print(f"FAIL ${min_r}-${max_r} {msg!r:35} -> {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 70)
print("STEP 3: suburb_to_card() / suburb_deep_dive() across many suburbs")
print("=" * 70)
if df is not None and not df.empty:
    import random
    random.seed(42)
    # Mix of: the 26 rich suburbs, suburbs with postcode but no rich stats,
    # and suburbs with neither (sparsest case)
    sample_names = ["Maylands","Bayswater","Murdoch","Fremantle"]
    no_postcode = df[df["postcode"].isna()]["suburb"].tolist()
    sample_names += random.sample(no_postcode, min(5, len(no_postcode)))

    trend_df = app.get_rent_trend_for(sample_names)
    for name in sample_names:
        try:
            row_df = df[df["suburb"]==name]
            if row_df.empty:
                print(f"FAIL {name!r:20} -> not found in df")
                continue
            row = row_df.iloc[0]
            card = app.suburb_to_card(row, "Test", trend_df, 500, 700)
            dive = app.suburb_deep_dive(name)
            print(f"OK   {name!r:20} card.rent={card['rent']!r:8} dive.br_label={dive['br_label']!r:15} dive.trend_txt={dive['trend_txt']!r}")
        except Exception as e:
            print(f"FAIL {name!r:20} -> {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
else:
    print("Skipped — Step 1 failed")

print("\n" + "=" * 70)
print("STEP 4: find_suburb_mentions() for deep_dive/compare workflows")
print("=" * 70)
if df is not None and not df.empty:
    subs = df["suburb"].tolist()
    for msg in [
        "Tell me everything about Maylands",
        "compare Maylands and Bayswater",
        "tell me about Cottesloe",
        "compare Fremantle and Subiaco",
    ]:
        found = app.find_suburb_mentions(msg, subs, limit=2)
        print(f"{msg!r:40} -> {found}")
else:
    print("Skipped — Step 1 failed")

print("\n" + "=" * 70)
print("STEP 5: Maylands rent trend (normalized) — checks history consistency")
print("=" * 70)
try:
    trend_df = app.get_rent_trend_for(["Maylands"])
    print(f"Rows: {len(trend_df)}")
    print(trend_df.to_string(index=False))
    signal, pct = app.get_trend_signal("Maylands", trend_df)
    print(f"\nget_trend_signal -> signal={signal!r}, pct={pct!r}")
except Exception as e:
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("STEP 6: Live /api/chat for 'Tell me everything about Maylands' and 'compare'")
print("=" * 70)
print("(requires the server running on http://localhost:8502)\n")
try:
    import requests
    for msg in ["Tell me everything about Maylands", "compare Maylands and Bayswater"]:
        r = requests.post("http://localhost:8502/api/chat", json={
            "message": msg, "history": [], "min_r": None, "max_r": None
        }, timeout=60)
        data = r.json()
        print(f"--- {msg!r} ---")
        print(f"  status: {r.status_code}, workflow: {data.get('workflow')!r}")
        if "card" in data:
            print(f"  card is None: {data.get('card') is None}")
            if data.get("card"):
                print(f"  card.rent: {data['card'].get('rent')!r}, card.postcode: {data['card'].get('postcode')!r}")
        if "cards" in data:
            print(f"  cards: {[c.get('name') for c in data.get('cards',[])]}")
        print(f"  text (first 200 chars): {data.get('text','')[:200]!r}")
        print()
except Exception as e:
    print(f"Could not reach the live server: {e}")

print("\n" + "=" * 70)
print("DONE — paste this entire output back.")
print("=" * 70)
