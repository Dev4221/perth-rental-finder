"""
Dimensional model — Phase 1: dim_suburb + dim_suburb_alias + dim_month

This is the foundational piece: a single conformed dimension that every
suburb-name spelling across every source table maps to, via a bridge table.
Once this exists, every fact table (built in later phases) joins to
dim_suburb.suburb_key — no more per-query UPPER(TRIM(...)) normalization.

Approach:
  1. Collect every distinct raw suburb-name string from every source table
     that has one, tagged with which table it came from (and postcode, where
     available).
  2. Normalize each (TRIM+UPPER) into a suburb_key candidate.
  3. Group by suburb_key: pick a canonical display name + postcode (prefer
     the 'schools' table's casing, since it's the cleanest), flag whether the
     suburb has "rich stats" (is one of the 26 in affordability/suburb_stats),
     and classify a region.
  4. Assign surrogate integer keys -> dim_suburb.
  5. Write every raw alias -> surrogate key -> dim_suburb_alias.
  6. Build dim_month from the date range found across the time-series tables.
  7. Validate: Maylands/Bayswater specifically, plus overall coverage stats.

Run:
  uv run python build_dim_suburb.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
import pandas as pd
import re

# This script WRITES new tables (dim_suburb, dim_suburb_alias, dim_month).
# database.py's get_connection() returns a READ-ONLY connection (by design,
# for the app), which is why "CREATE TABLE" failed when this script used it
# for both reads and writes. This script instead opens its own read-write
# connection directly to the same database file, bypassing database.py.
#
# IMPORTANT: stop the running FastAPI server (Ctrl+C in its terminal) before
# running this script. DuckDB needs exclusive access to open read-write, and
# won't get it while another process (the app) has the file open.
DB_PATH = os.getenv("DUCKDB_PATH", "data/rental.duckdb")
conn = duckdb.connect(DB_PATH)
tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
print(f"Tables available: {len(tables)}")

# ---------------------------------------------------------------------------
# Step 1: collect raw suburb-name aliases from every source table
# ---------------------------------------------------------------------------
# (table_name, suburb_column, postcode_column_or_None)
SOURCES = [
    ("rent_trend", "suburb", None),
    ("rental_bonds", "SUBURB", "POSTCODE"),
    ("affordability", "suburb", "postcode"),
    ("suburb_stats", "suburb", None),
    ("key_worker_affordability", "suburb", None),
    ("suburb_overall_rent", "suburb", None),
    ("suburb_rent_summary", "suburb", None),
    ("tenancy_duration", "suburb", None),
    ("stress_hotspots", "suburb", None),
    ("ato_income", "suburb", None),
    ("seifa", "suburb_name", None),
    ("schools", "suburb", "postcode"),
]

print("\n" + "=" * 70)
print("STEP 1: Collecting raw suburb-name aliases from every source table")
print("=" * 70)

alias_rows = []
for table, col, pc_col in SOURCES:
    if table not in tables:
        print(f"  {table:30} SKIPPED (table not found)")
        continue
    try:
        cols = f'"{col}"' + (f', "{pc_col}"' if pc_col else "")
        df = conn.execute(f'SELECT DISTINCT {cols} FROM {table}').fetchdf()
        n = 0
        for _, row in df.iterrows():
            raw = row[col]
            if raw is None or str(raw).strip() == "":
                continue
            pc = str(row[pc_col]).strip() if pc_col and pd.notna(row[pc_col]) else None
            alias_rows.append({"alias_raw": str(raw), "source_table": table, "postcode": pc})
            n += 1
        print(f"  {table:30} {n:>5} distinct names")
    except Exception as e:
        print(f"  {table:30} ERROR: {e}")
        try:
            actual_cols = conn.execute(f"DESCRIBE {table}").fetchdf()["column_name"].tolist()
            print(f"  {' ':30} (actual columns in {table}: {actual_cols})")
        except Exception:
            pass

alias_df = pd.DataFrame(alias_rows)
alias_df["suburb_key_str"] = alias_df["alias_raw"].str.strip().str.upper()
print(f"\nTotal raw aliases collected: {len(alias_df)}")
print(f"Distinct normalized suburb_key values: {alias_df['suburb_key_str'].nunique()}")

# ---------------------------------------------------------------------------
# Step 2: pick a canonical display name + postcode per suburb_key
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 2: Choosing canonical name + postcode per suburb")
print("=" * 70)

# Row-based "pick the best per group" — avoids version-sensitive
# groupby().apply()/include_groups behaviour. Prefer the 'schools' table's
# casing for the display name (cleanest source), with frequency as tiebreak.
freq = alias_df.groupby(["suburb_key_str", "alias_raw"]).size().reset_index(name="freq")
name_candidates = alias_df.merge(freq, on=["suburb_key_str", "alias_raw"])
name_candidates["is_schools"] = (name_candidates["source_table"] == "schools").astype(int)
name_candidates = name_candidates.sort_values(
    ["suburb_key_str", "is_schools", "freq", "alias_raw"],
    ascending=[True, False, False, True],
)
name_pick = (
    name_candidates.groupby("suburb_key_str", as_index=False).head(1)
    [["suburb_key_str", "alias_raw"]]
    .rename(columns={"alias_raw": "suburb_name"})
)
name_pick["suburb_name"] = name_pick["suburb_name"].str.strip()

# Postcode: prefer 'schools' rows, else most frequent non-null postcode
pc_rows = alias_df[alias_df["postcode"].notna()].copy()
if not pc_rows.empty:
    pc_freq = pc_rows.groupby(["suburb_key_str", "postcode"]).size().reset_index(name="freq")
    pc_candidates = pc_rows.merge(pc_freq, on=["suburb_key_str", "postcode"])
    pc_candidates["is_schools"] = (pc_candidates["source_table"] == "schools").astype(int)
    pc_candidates = pc_candidates.sort_values(
        ["suburb_key_str", "is_schools", "freq"], ascending=[True, False, False]
    )
    pc_pick = (
        pc_candidates.groupby("suburb_key_str", as_index=False).head(1)
        [["suburb_key_str", "postcode"]]
    )
else:
    pc_pick = pd.DataFrame({"suburb_key_str": [], "postcode": []})

canon = name_pick.merge(pc_pick, on="suburb_key_str", how="left")
print(f"Canonical suburb rows: {len(canon)}")
print(f"  with a postcode: {canon['postcode'].notna().sum()}")

# ---------------------------------------------------------------------------
# Step 3: has_rich_stats flag — is this one of the 26 in affordability?
# ---------------------------------------------------------------------------
rich_keys = set(alias_df[alias_df["source_table"] == "affordability"]["suburb_key_str"])
canon["has_rich_stats"] = canon["suburb_key_str"].isin(rich_keys)
print(f"\nSTEP 3: has_rich_stats=True for {canon['has_rich_stats'].sum()} suburbs "
      f"(expect ~26)")

# ---------------------------------------------------------------------------
# Step 4: region classification
#   - named Perth sub-regions from the app's existing geography knowledge
#   - else classify by postcode (Perth metro vs regional WA)
#   - else 'Unknown'
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 4: Region classification")
print("=" * 70)

# Region classification is derived from each suburb's local government area
# (LGA), per Wikipedia's "List of Perth suburbs" (357 suburbs, 31 LGAs grouped
# into 5 named Perth regions below). Suburbs spanning multiple LGAs use the
# first-listed LGA. Suburbs not in this list (genuinely regional WA, e.g.
# 'Mayanup') fall through to the postcode-based classification below.
NAMED_REGIONS = {
    "Perth — northern suburbs": [
        "ALEXANDER HEIGHTS","ALKIMOS","ASHBY","BALCATTA","BALGA","BANKSIA GROVE",
        "BELDON","BURNS BEACH","BUTLER","CARABOODA","CARINE","CARRAMAR",
        "CHURCHLANDS","CLARKSON","CONNOLLY","COOLBINIA","CRAIGIE","CURRAMBINE",
        "DARCH","DIANELLA","DOUBLEVIEW","DUNCRAIG","EDGEWATER","EGLINTON",
        "GIRRAWHEEN","GLENDALOUGH","GNANGARA","GREENWOOD","GWELUP","HAMERSLEY",
        "HEATHRIDGE","HERDSMAN","HILLARYS","HOCKING","ILUKA","INGLEWOOD",
        "INNALOO","JANDABUP","JINDALEE","JOONDALUP","JOONDANNA","KALLAROO",
        "KARRINYUP","KINGSLEY","KINROSS","KOONDOOLA","LANDSDALE","MADELEY",
        "MARANGAROO","MARIGINIUP","MARMION","MENORA","MERRIWA","MINDARIE",
        "MIRRABOOKA","MULLALOO","NEERABUP","NOLLAMARA","NORTH BEACH","NOWERGUP",
        "OCEAN REEF","OSBORNE PARK","PADBURY","PEARSALL","PINJAR","QUINNS ROCKS",
        "RIDGEWOOD","SCARBOROUGH","SINAGRA","SORRENTO","STIRLING","TAMALA PARK",
        "TAPPING","TRIGG","TUART HILL","TWO ROCKS","WANGARA","WANNEROO",
        "WARWICK","WATERMANS BAY","WESTMINSTER","WOODLANDS","WOODVALE","YANCHEP",
        "YOKINE",
    ],
    "Perth — southern suburbs": [
        "ALFRED COVE","ANKETELL","APPLECROSS","ARDROSS","ARMADALE","ASHENDON",
        "ATTADALE","ATWELL","AUBIN GROVE","BALDIVIS","BANJUP","BATEMAN",
        "BEACONSFIELD","BECKENHAM","BEDFORDALE","BEELIAR","BENTLEY","BERTRAM",
        "BIBRA LAKE","BICTON","BOORAGOON","BRENTWOOD","BROOKDALE","BULL CREEK",
        "BYFORD","CALISTA","CAMILLO","CANNING VALE","CANNINGTON","CARDUP",
        "CASUARINA","CHAMPION LAKES","COCKBURN CENTRAL","COOGEE","COOLBELLUP","COOLOONGUP",
        "DARLING DOWNS","DOOBARDA","EAST CANNINGTON","EAST FREMANTLE","EAST ROCKINGHAM","FERNDALE",
        "FORRESTDALE","FREMANTLE","GARDEN ISLAND","GOLDEN BAY","GOSNELLS","HAMILTON HILL",
        "HAMMOND PARK","HARRISDALE","HAYNES","HENDERSON","HILBERT","HILLMAN",
        "HILTON","HOPE VALLEY","HOPELAND","HUNTINGDALE","JANDAKOT","JARRAHDALE",
        "KARDINYA","KARNUP","KARRAGULLEN","KARRAKUP","KELMSCOTT","KENWICK",
        "KERALUP","KEYSBROOK","KWINANA BEACH","KWINANA TOWN CENTRE","LAKE COOGEE","LANGFORD",
        "LEDA","LEEMING","LYNWOOD","MADDINGTON","MANDOGALUP","MARDELLA",
        "MARTIN","MEDINA","MELVILLE","MOUNT NASURA","MOUNT PLEASANT","MOUNT RICHON",
        "MUNDIJONG","MUNSTER","MURDOCH","MYAREE","NAVAL BASE","NORTH COOGEE",
        "NORTH FREMANTLE","NORTH LAKE","O'CONNOR","OAKFORD","OLDBURY","ORANGE GROVE",
        "ORELIA","PALMYRA","PARKWOOD","PARMELIA","PERON","PIARA WATERS",
        "PORT KENNEDY","POSTANS","QUEENS PARK","RIVERTON","ROCKINGHAM","ROLEYSTONE",
        "ROSSMOYNE","ROTTNEST ISLAND","SAFETY BAY","SAMSON","SECRET HARBOUR","SERPENTINE",
        "SEVILLE GROVE","SHELLEY","SHOALWATER","SINGLETON","SOUTH FREMANTLE","SOUTH LAKE",
        "SOUTHERN RIVER","SPEARWOOD","ST JAMES","SUCCESS","THE SPECTACLES","THORNLIE",
        "TREEBY","WAIKIKI","WANDI","WARNBRO","WATTLEUP","WELLARD",
        "WELSHPOOL","WHITBY","WHITE GUM VALLEY","WILLAGEE","WILLETTON","WILSON",
        "WINTHROP","WUNGONG","YANGEBUP",
    ],
    "Perth — eastern suburbs": [
        "ASCOT","ASHFIELD","AVELEY","BAILUP","BALLAJURA","BASKERVILLE",
        "BASSENDEAN","BAYSWATER","BEDFORD","BEECHBORO","BEECHINA","BELHUS",
        "BELLEVUE","BELMONT","BENNETT SPRINGS","BICKLEY","BOYA","BRABHAM",
        "BRIGADOON","BULLSBROOK","BUSHMEAD","CANNING MILLS","CARMEL","CAVERSHAM",
        "CHIDLOW","CLOVERDALE","CULLACABARDEE","DARLINGTON","DAYTON","EDEN HILL",
        "ELLENBROOK","EMBLETON","FORRESTFIELD","GIDGEGANNUP","GLEN FORREST","GOOSEBERRY HILL",
        "GORRIE","GREENMOUNT","GUILDFORD","HACKETTS GULLY","HAZELMERE","HELENA VALLEY",
        "HENLEY BROOK","HERNE HILL","HIGH WYCOMBE","HOVEA","JANE BROOK","KALAMUNDA",
        "KEWDALE","KIARA","KOONGAMIA","LESMURDIE","LEXIA","LOCKRIDGE",
        "MAHOGANY CREEK","MAIDA VALE","MALAGA","MAYLANDS","MELALEUCA","MIDDLE SWAN",
        "MIDLAND","MIDVALE","MILLENDON","MORLEY","MOUNT HELENA","MOUNT LAWLEY",
        "MUNDARING","NORANDA","PARKERVILLE","PAULLS VALLEY","PERTH AIRPORT","PICKERING BROOK",
        "PIESSE BROOK","RED HILL","REDCLIFFE","RESERVOIR","RIVERVALE","SAWYERS VALLEY",
        "SOUTH GUILDFORD","STONEVILLE","STRATTON","SWAN VIEW","THE LAKES","THE VINES",
        "UPPER SWAN","VIVEASH","WALLISTON","WATTLE GROVE","WEST SWAN","WHITEMAN",
        "WOODBRIDGE","WOOROLOO",
    ],
    "Perth — inner city": [
        "BURSWOOD","CARLISLE","COMO","CRAWLEY","EAST PERTH","EAST VICTORIA PARK",
        "HIGHGATE","KARAWARA","KENSINGTON","LATHLAIN","LEEDERVILLE","MANNING",
        "MOUNT HAWTHORN","NORTH PERTH","NORTHBRIDGE","PERTH","SALTER POINT","SOUTH PERTH",
        "VICTORIA PARK","WATERFORD","WEST PERTH",
    ],
    "Perth — western suburbs": [
        "CITY BEACH","CLAREMONT","COTTESLOE","DAGLISH","DALKEITH","FLOREAT",
        "JOLIMONT","KARRAKATTA","MOSMAN PARK","MOUNT CLAREMONT","NEDLANDS","PEPPERMINT GROVE",
        "SHENTON PARK","SUBIACO","SWANBOURNE","WEMBLEY","WEMBLEY DOWNS","WEST LEEDERVILLE",
    ],
}
NAMED_LOOKUP = {s: region for region, subs in NAMED_REGIONS.items() for s in subs}

def classify_region(row):
    key = row["suburb_key_str"]
    if key in NAMED_LOOKUP:
        return NAMED_LOOKUP[key]
    pc = row["postcode"]
    if pc is not None:
        try:
            pcn = int(pc)
            if 6000 <= pcn <= 6214:
                return "Perth metro (other)"
            return "Regional WA"
        except ValueError:
            pass
    return "Unknown"

canon["region"] = canon.apply(classify_region, axis=1)
print(canon["region"].value_counts().to_string())

# ---------------------------------------------------------------------------
# Step 5: assign surrogate keys, write dim_suburb
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 5: Writing dim_suburb")
print("=" * 70)

canon = canon.sort_values("suburb_name").reset_index(drop=True)
canon["suburb_key"] = range(1, len(canon) + 1)

dim_suburb = canon[["suburb_key", "suburb_name", "postcode", "region", "has_rich_stats"]].copy()

conn.execute("DROP TABLE IF EXISTS dim_suburb")
conn.register("dim_suburb_df", dim_suburb)
conn.execute("CREATE TABLE dim_suburb AS SELECT * FROM dim_suburb_df")
conn.unregister("dim_suburb_df")
print(f"dim_suburb: {len(dim_suburb)} rows written")

# ---------------------------------------------------------------------------
# Step 6: write dim_suburb_alias (bridge table)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 6: Writing dim_suburb_alias")
print("=" * 70)

alias_out = alias_df.merge(
    canon[["suburb_key_str", "suburb_key"]], on="suburb_key_str", how="left"
)
alias_out = alias_out[["alias_raw", "source_table", "suburb_key"]].drop_duplicates(
    subset=["alias_raw", "suburb_key"]
)
unmapped = alias_out[alias_out["suburb_key"].isna()]
if not unmapped.empty:
    print(f"WARNING: {len(unmapped)} aliases failed to map (should be 0):")
    print(unmapped.head(10).to_string(index=False))

conn.execute("DROP TABLE IF EXISTS dim_suburb_alias")
conn.register("dim_suburb_alias_df", alias_out)
conn.execute("CREATE TABLE dim_suburb_alias AS SELECT * FROM dim_suburb_alias_df")
conn.unregister("dim_suburb_alias_df")
print(f"dim_suburb_alias: {len(alias_out)} rows written "
      f"({alias_out['alias_raw'].nunique()} distinct raw strings)")

# ---------------------------------------------------------------------------
# Step 7: build dim_month from the date range across time-series tables
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 7: Writing dim_month")
print("=" * 70)

month_sources = []
if "rent_trend" in tables:
    month_sources.append("SELECT DISTINCT month FROM rent_trend")
if "rental_bonds" in tables:
    month_sources.append("SELECT DISTINCT LODGEMENT_MONTH as month FROM rental_bonds")
if "perth_monthly_trend" in tables:
    month_sources.append("SELECT DISTINCT month FROM perth_monthly_trend")

all_months = set()
for q in month_sources:
    try:
        df = conn.execute(q).fetchdf()
        all_months.update(df["month"].dropna().astype(str).tolist())
    except Exception as e:
        print(f"  (skipping a month source: {e})")

month_list = sorted(m for m in all_months if re.match(r"^\d{4}-\d{2}$", m))
dim_month = pd.DataFrame({"month_key": month_list})
dim_month["year"] = dim_month["month_key"].str[:4].astype(int)
dim_month["month_num"] = dim_month["month_key"].str[5:7].astype(int)
dim_month["quarter"] = ((dim_month["month_num"] - 1) // 3) + 1
dim_month["month_label"] = pd.to_datetime(dim_month["month_key"] + "-01").dt.strftime("%b %Y")

conn.execute("DROP TABLE IF EXISTS dim_month")
conn.register("dim_month_df", dim_month)
conn.execute("CREATE TABLE dim_month AS SELECT * FROM dim_month_df")
conn.unregister("dim_month_df")
print(f"dim_month: {len(dim_month)} rows written "
      f"({dim_month['month_key'].min()} to {dim_month['month_key'].max()})")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("VALIDATION: Maylands / Bayswater / Murdoch")
print("=" * 70)

check = conn.execute("""
    SELECT s.suburb_key, s.suburb_name, s.postcode, s.region, s.has_rich_stats,
           COUNT(a.alias_raw) as n_aliases
    FROM dim_suburb s
    LEFT JOIN dim_suburb_alias a ON a.suburb_key = s.suburb_key
    WHERE UPPER(s.suburb_name) IN ('MAYLANDS','BAYSWATER','MURDOCH')
    GROUP BY s.suburb_key, s.suburb_name, s.postcode, s.region, s.has_rich_stats
""").fetchdf()
print(check.to_string(index=False))

print("\nAliases for Maylands:")
mayl = conn.execute("""
    SELECT a.alias_raw, a.source_table
    FROM dim_suburb_alias a
    JOIN dim_suburb s ON s.suburb_key = a.suburb_key
    WHERE UPPER(s.suburb_name) = 'MAYLANDS'
    ORDER BY a.source_table, a.alias_raw
""").fetchdf()
print(mayl.to_string(index=False))

print("\n" + "=" * 70)
print(f"DONE. dim_suburb={len(dim_suburb)} rows, "
      f"dim_suburb_alias={len(alias_out)} rows, dim_month={len(dim_month)} rows.")
print("Paste this entire output back.")
print("=" * 70)
