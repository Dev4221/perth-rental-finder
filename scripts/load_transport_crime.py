"""
scripts/load_transport_crime.py
Loads Transperth GTFS and WA Police crime data into the database.
Run: uv run python scripts/load_transport_crime.py
"""
import zipfile, pandas as pd, duckdb, math, openpyxl
from pathlib import Path

DB = "data/rental.duckdb"
GTFS = "data/gtfs/google_transit.zip"
CRIME = "data/crime/wa-police-force-crime-timeseries.xlsx"

con = duckdb.connect(DB)

# ── GTFS ──────────────────────────────────────────────────────────────────
if Path(GTFS).exists():
    print("Loading Transperth train stops...")
    with zipfile.ZipFile(GTFS) as z:
        with z.open('stops.txt') as f:
            stops = pd.read_csv(f)
    stops.columns = [c.strip() for c in stops.columns]
    train_stops = stops[stops['supported_modes'].str.strip().str.contains('Rail', na=False)].copy()
    train_stops['station_name'] = train_stops['stop_name'].str.replace(r'\s+Platform\s+\d+.*','',regex=True).str.strip()
    train_stations = train_stops.groupby('station_name').agg(lat=('stop_lat','mean'),lon=('stop_lon','mean')).reset_index()
    con.execute("DROP TABLE IF EXISTS train_stations")
    con.execute("CREATE TABLE train_stations AS SELECT station_name, lat, lon FROM train_stations")

    suburb_centroids = con.execute("""
        SELECT postcode, AVG(latitude) as lat, AVG(longitude) as lon
        FROM schools WHERE latitude IS NOT NULL GROUP BY postcode
    """).fetchdf()

    def haversine(lat1,lon1,lat2,lon2):
        R=6371; dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
        a=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

    results=[]
    for _,sub in suburb_centroids.iterrows():
        best_d,best_n=999,None
        for _,stn in train_stations.iterrows():
            d=haversine(sub['lat'],sub['lon'],stn['lat'],stn['lon'])
            if d<best_d: best_d=d; best_n=stn['station_name']
        results.append({'postcode':sub['postcode'],'nearest_station':best_n,
                        'distance_km':round(best_d,2),'has_train_1km':best_d<=1.0,'has_train_2km':best_d<=2.0})
    prox=pd.DataFrame(results)
    con.execute("DROP TABLE IF EXISTS train_proximity")
    con.execute("CREATE TABLE train_proximity AS SELECT * FROM prox")
    print(f"Train proximity: {len(prox)} postcodes")
else:
    print(f"GTFS not found at {GTFS} — skipping")

# ── CRIME ─────────────────────────────────────────────────────────────────
if Path(CRIME).exists():
    print("Loading WA Police crime data...")
    wb = openpyxl.load_workbook(CRIME, read_only=True, data_only=True)
    ws = wb['Data']
    rows = list(ws.iter_rows(values_only=True))
    df = pd.DataFrame(rows[1:], columns=rows[0])
    key = ['Burglary','Stealing of Motor Vehicle','Assault (Non-Family)','Property Damage']
    df_k = df[(df['WAPOL_Hierarchy_Lvl2'].isin(key))&(df['Year'].isin(['2023-24','2024-25']))]
    pivot = df_k.groupby(['Website Region','WAPOL_Hierarchy_Lvl2'])['Count'].sum().reset_index()
    pivot = pivot.pivot_table(index='Website Region',columns='WAPOL_Hierarchy_Lvl2',values='Count',aggfunc='sum').reset_index().fillna(0)
    pivot.columns=[c.strip().replace(' ','_').replace('(','').replace(')','').replace('-','_').lower() for c in pivot.columns]
    district_map = {
        'PERTH DISTRICT':      list(range(6000,6012)),
        'CANNINGTON DISTRICT': list(range(6090,6112))+list(range(6147,6160)),
        'ARMADALE DISTRICT':   list(range(6111,6145)),
        'FREMANTLE DISTRICT':  list(range(6155,6175)),
        'JOONDALUP DISTRICT':  list(range(6020,6040)),
        'MIDLAND DISTRICT':    list(range(6050,6085)),
        'MIRRABOOKA DISTRICT': list(range(6060,6070))+list(range(6030,6055)),
        'MANDURAH DISTRICT':   list(range(6174,6215)),
    }
    pc_to_d={}
    for d,pr in district_map.items():
        for p in pr:
            if str(p).zfill(4) not in pc_to_d: pc_to_d[str(p).zfill(4)]=d
    active = con.execute("SELECT DISTINCT postcode FROM affordability WHERE total_tenancies>30").fetchdf()['postcode'].tolist()
    out=[]
    for pc in active:
        d=pc_to_d.get(pc)
        if not d: continue
        row=pivot[pivot['website_region']==d]
        if row.empty: continue
        r=row.iloc[0]
        out.append({'postcode':pc,'district':d,'burglary':int(r.get('burglary',0)),
                    'vehicle_theft':int(r.get('stealing_of_motor_vehicle',0)),
                    'assault':int(r.get('assault_non_family',0)),'property_damage':int(r.get('property_damage',0))})
    cdf=pd.DataFrame(out)
    for c in ['burglary','vehicle_theft','assault','property_damage']:
        cdf[c]=pd.to_numeric(cdf[c],errors='coerce').fillna(0)
    cdf['total_crime']=cdf[['burglary','vehicle_theft','assault','property_damage']].sum(axis=1)
    mx=cdf['total_crime'].max()
    cdf['safety_score']=((1-cdf['total_crime']/mx)*10).round(1)
    cdf['safety_label']=cdf['safety_score'].apply(lambda s:
        "Very low crime" if s>=8 else ("Low crime" if s>=6 else ("Average" if s>=4 else ("Above average crime" if s>=2 else "High crime area"))))
    con.execute("DROP TABLE IF EXISTS suburb_crime")
    con.execute("CREATE TABLE suburb_crime AS SELECT * FROM cdf")
    print(f"Crime data: {len(cdf)} postcodes")
else:
    print(f"Crime file not found at {CRIME} — skipping")

con.close()
print("Done. Restart the app.")
