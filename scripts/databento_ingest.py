import os, sys, time, psycopg2, databento as db

DATABENTO_KEY = os.environ["DATABENTO_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
END_DATE = "2025-03-01"

DATASETS = [
    {"dataset": "GLBX.MDP3", "symbols": ["ES.c.0","NQ.c.0","CL.c.0","GC.c.0","NG.c.0","ZB.c.0","6E.c.0","6J.c.0","RTY.c.0","SI.c.0"], "start": "2010-06-06", "desc": "CME Futures"},
    {"dataset": "IFEU.IMPACT", "symbols": ["BRN.c.0","WBS.c.0"], "start": "2018-01-01", "desc": "ICE Brent+WTI"},
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM price_bars")
print(f"Bars before: {cur.fetchone()[0]:,}")

client = db.Historical(DATABENTO_KEY)

for ds in DATASETS:
    print(f"\n{ds['desc']}")
    for symbol in ds["symbols"]:
        try:
            data = client.timeseries.get_range(
                dataset=ds["dataset"],
                symbols=[symbol],
                schema="ohlcv-1d",
                start=ds["start"],
                end=END_DATE,
                stype_in="continuous"
            )
            df = data.to_df()
            inserted = 0
            for idx, row in df.iterrows():
                cur.execute(
                    "INSERT INTO price_bars (symbol,timeframe,timestamp,open,high,low,close,volume,source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (symbol,timeframe,timestamp) DO NOTHING",
                    (symbol,"1d",idx.date(),float(row.get("open",0)),float(row.get("high",0)),float(row.get("low",0)),float(row.get("close",0)),int(row.get("volume",0)),"databento")
                )
                inserted += cur.rowcount
            conn.commit()
            print(f"  {symbol}: {inserted} bars")
            time.sleep(0.3)
        except Exception as e:
            print(f"  {symbol}: ERROR {e}")
            conn.rollback()

cur.execute("SELECT COUNT(*) FROM price_bars")
print(f"\nBars after: {cur.fetchone()[0]:,}")
cur.close()
conn.close()
