import os, time, requests, psycopg2
import pandas as pd
import yfinance as yf
from datetime import datetime

DATABASE_URL = os.environ["DATABASE_URL"]
FRED_KEY = os.environ.get("FRED_API_KEY", "")  # optional, works without for most series

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ── Create macro_data table if not exists ────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS macro_data (
    id SERIAL PRIMARY KEY,
    series_id VARCHAR(50) NOT NULL,
    ts DATE NOT NULL,
    value DOUBLE PRECISION,
    category VARCHAR(50),
    description VARCHAR(200),
    UNIQUE(series_id, ts)
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_macro_series_ts ON macro_data(series_id, ts DESC)")
conn.commit()
print("Table macro_data ready")

def insert_series(series_id, df, category, description):
    inserted = 0
    for ts, val in df.items():
        if pd.isna(val):
            continue
        try:
            cur.execute(
                "INSERT INTO macro_data (series_id,ts,value,category,description) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (series_id,ts) DO NOTHING",
                (series_id, ts.date() if hasattr(ts,'date') else ts, float(val), category, description)
            )
            inserted += cur.rowcount
        except:
            pass
    conn.commit()
    return inserted

# ── FRED DATA (no API key needed for public series) ──────────────────────────
FRED_SERIES = [
    # Interest rates & yield curve
    ("DFF",       "rates",     "Fed Funds Rate"),
    ("DGS2",      "rates",     "2Y Treasury Yield"),
    ("DGS5",      "rates",     "5Y Treasury Yield"),
    ("DGS10",     "rates",     "10Y Treasury Yield"),
    ("DGS30",     "rates",     "30Y Treasury Yield"),
    ("T10Y2Y",    "rates",     "10Y-2Y Yield Spread (Recession Indicator)"),
    ("T10Y3M",    "rates",     "10Y-3M Yield Spread"),
    ("TEDRATE",   "rates",     "TED Spread (Banking Stress)"),
    ("BAMLH0A0HYM2", "credit", "HY Credit Spread OAS"),
    ("BAMLC0A0CM",   "credit", "IG Credit Spread OAS"),
    # Inflation
    ("CPIAUCSL",  "inflation", "CPI All Items YoY"),
    ("CPILFESL",  "inflation", "Core CPI ex Food Energy"),
    ("PCEPI",     "inflation", "PCE Price Index"),
    ("PCEPILFE",  "inflation", "Core PCE (Fed Target)"),
    ("PPIFIS",    "inflation", "PPI Final Demand"),
    # Growth & employment
    ("GDPC1",     "growth",    "Real GDP"),
    ("UNRATE",    "employment","Unemployment Rate"),
    ("PAYEMS",    "employment","Nonfarm Payrolls"),
    ("ICSA",      "employment","Initial Jobless Claims"),
    ("JTSJOL",    "employment","Job Openings (JOLTS)"),
    ("HOUST",     "housing",   "Housing Starts"),
    ("PERMIT",    "housing",   "Building Permits"),
    ("CSUSHPINSA","housing",   "Case-Shiller Home Price Index"),
    # Money & liquidity
    ("M2SL",      "liquidity", "M2 Money Supply"),
    ("M2V",       "liquidity", "M2 Velocity"),
    ("BOGMBASE",  "liquidity", "Monetary Base"),
    ("WALCL",     "liquidity", "Fed Balance Sheet Total Assets"),
    # Consumer & business
    ("UMCSENT",   "sentiment", "U Michigan Consumer Sentiment"),
    ("RETAILSL",  "consumer",  "Retail Sales"),
    ("INDPRO",    "activity",  "Industrial Production Index"),
    ("TCU",       "activity",  "Capacity Utilization"),
    ("DGORDER",   "activity",  "Durable Goods Orders"),
    ("ISRATIO",   "activity",  "Inventory to Sales Ratio"),
    # Trade & global
    ("BOPGSTB",   "trade",     "US Trade Balance"),
    ("DEXUSEU",   "fx",        "USD/EUR Exchange Rate"),
    ("DEXJPUS",   "fx",        "JPY/USD Exchange Rate"),
    ("DEXCHUS",   "fx",        "CNY/USD Exchange Rate"),
    ("DCOILWTICO","commodities","WTI Crude Oil Price"),
    ("DCOILBRENTEU","commodities","Brent Crude Oil Price"),
    ("GOLDAMGBD228NLBM","commodities","Gold Price London Fix"),
]

print(f"\n{'='*60}")
print(f"FRED Macro Data ({len(FRED_SERIES)} series)")
print('='*60)

for series_id, category, description in FRED_SERIES:
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        if FRED_KEY:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_KEY}&file_type=json&observation_start=2000-01-01"
        
        df = pd.read_csv(url, index_col=0, parse_dates=True, squeeze=True)
        df = df[df != '.']
        df = pd.to_numeric(df, errors='coerce').dropna()
        df = df[df.index >= '2000-01-01']
        
        inserted = insert_series(series_id, df, category, description)
        print(f"  {series_id}: {inserted} rows ({description})")
        time.sleep(0.2)
    except Exception as e:
        print(f"  {series_id}: ERROR {str(e)[:60]}")

# ── VIX TERM STRUCTURE & FEAR GAUGES ────────────────────────────────────────
print(f"\n{'='*60}")
print("VIX & Fear Gauges")
print('='*60)

VIX_SYMBOLS = [
    ("^VIX",   "volatility", "VIX 30-day Implied Volatility"),
    ("^VIX3M", "volatility", "VIX3M 3-Month Implied Vol"),
    ("^VVIX",  "volatility", "VVIX Vol-of-Vol Index"),
    ("^MOVE",  "volatility", "MOVE Bond Volatility Index"),
    ("^OVX",   "volatility", "OVX Oil Volatility Index"),
    ("^GVZ",   "volatility", "GVZ Gold Volatility Index"),
    ("^EVZ",   "volatility", "EVZ EUR/USD Volatility Index"),
]

for symbol, category, description in VIX_SYMBOLS:
    try:
        df = yf.download(symbol, start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)
        if df.empty:
            print(f"  {symbol}: no data")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        inserted = insert_series(symbol, df["Close"], category, description)
        print(f"  {symbol}: {inserted} rows")
        time.sleep(0.3)
    except Exception as e:
        print(f"  {symbol}: ERROR {str(e)[:60]}")

# ── MARKET BREADTH & REGIME INDICATORS ──────────────────────────────────────
print(f"\n{'='*60}")
print("Market Breadth & Regime")
print('='*60)

BREADTH_SYMBOLS = [
    # Risk on/off proxies
    ("HYG",    "breadth", "High Yield Bond ETF (Risk On/Off)"),
    ("LQD",    "breadth", "Investment Grade Bond ETF"),
    ("TLT",    "breadth", "20Y Treasury ETF"),
    ("IEF",    "breadth", "7-10Y Treasury ETF"),
    ("SHY",    "breadth", "1-3Y Treasury ETF"),
    ("TIP",    "breadth", "TIPS Inflation Protected"),
    ("EMB",    "breadth", "Emerging Market Bonds"),
    # Commodity regimes
    ("DBC",    "commodities", "Commodity Index ETF"),
    ("PDBC",   "commodities", "Invesco Commodity ETF"),
    ("BCI",    "commodities", "Bloomberg Commodity Index"),
    ("CPER",   "commodities", "Copper ETF"),
    ("WEAT",   "commodities", "Wheat ETF"),
    ("CORN",   "commodities", "Corn ETF"),
    ("SOYB",   "commodities", "Soybean ETF"),
    # Global macro
    ("EEM",    "global", "Emerging Markets ETF"),
    ("EFA",    "global", "Developed Markets ex-US ETF"),
    ("FXI",    "global", "China Large Cap ETF"),
    ("EWJ",    "global", "Japan ETF"),
    ("EWZ",    "global", "Brazil ETF"),
    ("EWG",    "global", "Germany ETF"),
    ("EWY",    "global", "South Korea ETF"),
    ("EWT",    "global", "Taiwan ETF"),
    ("INDA",   "global", "India ETF"),
    ("RSX",    "global", "Russia ETF"),
    # Sector momentum
    ("XLK",    "sector", "Technology"),
    ("XLF",    "sector", "Financials"),
    ("XLE",    "sector", "Energy"),
    ("XLV",    "sector", "Healthcare"),
    ("XLI",    "sector", "Industrials"),
    ("XLU",    "sector", "Utilities"),
    ("XLB",    "sector", "Materials"),
    ("XLRE",   "sector", "Real Estate"),
    ("XLC",    "sector", "Communication"),
    ("XLY",    "sector", "Consumer Discretionary"),
    ("XLP",    "sector", "Consumer Staples"),
    # Special signals
    ("BDI",    "shipping","Baltic Dry Index"),
    ("^TNX",   "rates",   "10Y Treasury Yield"),
    ("^TYX",   "rates",   "30Y Treasury Yield"),
    ("^FVX",   "rates",   "5Y Treasury Yield"),
    ("DX-Y.NYB","fx",     "US Dollar Index DXY"),
    ("GC=F",   "commodities","Gold Futures"),
    ("HG=F",   "commodities","Copper Futures (Dr Copper)"),
    ("CL=F",   "commodities","WTI Crude Futures"),
]

for symbol, category, description in BREADTH_SYMBOLS:
    try:
        df = yf.download(symbol, start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)
        if df.empty:
            print(f"  {symbol}: no data")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        inserted = insert_series(symbol, df["Close"], category, description)
        print(f"  {symbol}: {inserted} rows ({description})")
        time.sleep(0.3)
    except Exception as e:
        print(f"  {symbol}: ERROR {str(e)[:60]}")

# ── DERIVED SIGNALS (computed from existing data) ────────────────────────────
print(f"\n{'='*60}")
print("Computing Derived Signals")
print('='*60)

try:
    # Copper/Gold ratio - economic growth signal
    copper = yf.download("HG=F", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    gold   = yf.download("GC=F", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    if isinstance(copper, pd.DataFrame): copper = copper.iloc[:,0]
    if isinstance(gold, pd.DataFrame): gold = gold.iloc[:,0]
    ratio = (copper / gold).dropna()
    inserted = insert_series("COPPER_GOLD_RATIO", ratio, "derived", "Copper/Gold Ratio (Growth Proxy)")
    print(f"  COPPER_GOLD_RATIO: {inserted} rows")
except Exception as e:
    print(f"  COPPER_GOLD_RATIO: ERROR {e}")

try:
    # HYG/IEF ratio - credit risk appetite
    hyg = yf.download("HYG", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    ief = yf.download("IEF", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    if isinstance(hyg, pd.DataFrame): hyg = hyg.iloc[:,0]
    if isinstance(ief, pd.DataFrame): ief = ief.iloc[:,0]
    ratio = (hyg / ief).dropna()
    inserted = insert_series("HYG_IEF_RATIO", ratio, "derived", "HYG/IEF Ratio (Credit Risk Appetite)")
    print(f"  HYG_IEF_RATIO: {inserted} rows")
except Exception as e:
    print(f"  HYG_IEF_RATIO: ERROR {e}")

try:
    # SPY/TLT ratio - stocks vs bonds (risk regime)
    spy = yf.download("SPY", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    tlt = yf.download("TLT", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    if isinstance(spy, pd.DataFrame): spy = spy.iloc[:,0]
    if isinstance(tlt, pd.DataFrame): tlt = tlt.iloc[:,0]
    ratio = (spy / tlt).dropna()
    inserted = insert_series("SPY_TLT_RATIO", ratio, "derived", "SPY/TLT Ratio (Risk-On vs Risk-Off)")
    print(f"  SPY_TLT_RATIO: {inserted} rows")
except Exception as e:
    print(f"  SPY_TLT_RATIO: ERROR {e}")

try:
    # XLK/XLP ratio - growth vs defensive rotation
    xlk = yf.download("XLK", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    xlp = yf.download("XLP", start="2000-01-01", end="2025-03-01", progress=False, auto_adjust=True)["Close"]
    if isinstance(xlk, pd.DataFrame): xlk = xlk.iloc[:,0]
    if isinstance(xlp, pd.DataFrame): xlp = xlp.iloc[:,0]
    ratio = (xlk / xlp).dropna()
    inserted = insert_series("XLK_XLP_RATIO", ratio, "derived", "XLK/XLP Ratio (Growth vs Defensive)")
    print(f"  XLK_XLP_RATIO: {inserted} rows")
except Exception as e:
    print(f"  XLK_XLP_RATIO: ERROR {e}")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
cur.execute("SELECT category, COUNT(*) as series, SUM(1) FROM macro_data GROUP BY category ORDER BY category")
print(f"\n{'='*60}")
print("MACRO DATABASE SUMMARY")
print('='*60)
cur.execute("SELECT category, COUNT(DISTINCT series_id) as series FROM macro_data GROUP BY category ORDER BY category")
for row in cur.fetchall():
    print(f"  {row[0]:<20} {row[1]} series")
cur.execute("SELECT COUNT(*) FROM macro_data")
print(f"\nTotal macro rows: {cur.fetchone()[0]:,}")
cur.close()
conn.close()
