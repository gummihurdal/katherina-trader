import os, time, psycopg2, yfinance as yf

DATABASE_URL = os.environ["DATABASE_URL"]

SYMBOLS = [
    "^STOXX50E", "^GDAXI", "^FCHI", "^FTSE", "^AEX",
    "ASML.AS", "SAP.DE", "NESN.SW", "NOVN.SW", "ROG.SW",
    "SIE.DE", "ALV.DE", "BAS.DE", "MBG.DE", "TTE.PA",
    "LVMH.PA", "OR.PA", "AIR.PA", "BNP.PA", "SAN.PA",
    "VOD.L", "SHEL.L", "AZN.L", "HSBA.L", "BP.L",
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM price_bars")
print(f"Bars before: {cur.fetchone()[0]:,}")

for symbol in SYMBOLS:
    try:
        df = yf.download(symbol, start="2010-01-01", end="2025-03-01", progress=False)
        if df.empty:
            print(f"  {symbol}: no data")
            continue
        inserted = 0
        for ts, row in df.iterrows():
            cur.execute(
                "INSERT INTO price_bars (symbol,timespan,ts,open,high,low,close,volume) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (symbol,timespan,ts) DO NOTHING",
                (symbol,"1d",ts,float(row["Open"]),float(row["High"]),float(row["Low"]),float(row["Close"]),int(row["Volume"]))
            )
            inserted += cur.rowcount
        conn.commit()
        print(f"  {symbol}: {inserted} bars")
        time.sleep(0.5)
    except Exception as e:
        print(f"  {symbol}: ERROR {e}")
        conn.rollback()

cur.execute("SELECT COUNT(*) FROM price_bars")
print(f"\nBars after: {cur.fetchone()[0]:,}")
cur.close()
conn.close()
