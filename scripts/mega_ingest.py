import os, time, psycopg2, yfinance as yf
import pandas as pd

DATABASE_URL = os.environ["DATABASE_URL"]

# ── S&P 500 ──────────────────────────────────────────────────────────────────
SP500 = [
    "AAPL","MSFT","AMZN","NVDA","GOOGL","GOOG","META","TSLA","BRK-B","JPM",
    "LLY","V","UNH","XOM","MA","JNJ","PG","AVGO","HD","MRK","ABBV","CVX",
    "KO","PEP","ADBE","COST","WMT","MCD","BAC","CRM","NFLX","TMO","CSCO",
    "ACN","ABT","AMD","LIN","DHR","NEE","TXN","ORCL","PM","UNP","MS","HON",
    "RTX","INTC","AMGN","T","BMY","INTU","LOW","UPS","SPGI","GS","BLK","CAT",
    "DE","ISRG","MDLZ","ADP","GILD","ADI","REGN","VRTX","ETN","SYK","C","NOW",
    "ZTS","CB","MMC","CI","AON","MO","DUK","SO","D","EXC","AEP","PCG","SRE",
    "WM","ECL","APD","ITW","EMR","GD","NSC","CSX","FDX","WBA","KMB","CL",
    "GIS","HUM","ELV","MCK","ABC","CAH","CVS","WBA","ANTM","CI","HCA","UHS",
    "THC","DGX","LH","IQV","A","RMD","EW","DXCM","PODD","IDXX","BIO","ILMN",
    "BIIB","MRNA","BNTX","REGN","VRTX","ALNY","BMRN","RARE","BLUE","EDIT",
    "CRSP","NTLA","BEAM","FATE","KYMR","SGEN","INCY","EXEL","CLDX","RCUS",
    "PFE","AZN","SNY","NVO","RHHBY","GSK","AstraZeneca","NVS","MNK","ENDP",
    "F","GM","TM","HMC","STLA","RACE","RIVN","LCID","NKLA","WKHS",
    "GE","BA","LMT","NOC","HII","TDG","HEICO","TransDigm","SPR","AAL","DAL",
    "UAL","LUV","ALK","SAVE","JBLU","SKYW","MESA","HA",
    "XOM","CVX","COP","EOG","PXD","DVN","HAL","SLB","BKR","OXY","MPC","PSX",
    "VLO","FANG","CTRA","APA","AR","EQT","RRC","COG","SWN","CHK",
    "GLD","SLV","GDX","GDXJ","NEM","GOLD","AEM","KGC","AG","PAAS",
    "SPY","QQQ","IWM","DIA","VTI","VOO","IVV","VEA","VWO","EEM","EFA",
    "TLT","IEF","SHY","LQD","HYG","JNK","BND","AGG","MBB","TIP",
    "USO","UNG","DBO","PDBC","COMT","DJP","GSG","COMB",
    "XLK","XLF","XLE","XLV","XLI","XLU","XLB","XLRE","XLC","XLY","XLP",
    "VNQ","O","AMT","PLD","EQIX","SPG","PSA","EXR","AVB","EQR","DRE",
    "JPM","BAC","WFC","C","GS","MS","BK","STT","USB","PNC","TFC","COF",
    "AXP","DFS","SYF","ALLY","CIT","KEY","RF","HBAN","FITB","CFG",
    "PYPL","SQ","COIN","HOOD","SOFI","AFRM","UPST","LC","OPEN","MKTX",
    "CRM","NOW","SNOW","DDOG","NET","CRWD","PANW","FTNT","ZS","OKTA",
    "SHOP","AMZN","ETSY","EBAY","W","CHWY","CHEWY","PRTS","RVLV",
    "NFLX","DIS","CMCSA","WBD","PARA","FOX","FOXA","AMC","CNK","IMAX",
    "MSFT","ORCL","SAP","IBM","CTSH","ACN","INFY","WIT","EPAM","GLOB",
    "TSLA","RIVN","F","GM","NIO","XPEV","LI","LCID","FSR","WKHS",
    "AMZN","WMT","TGT","COST","DG","DLTR","FIVE","BIG","BBY","HD","LOW",
    "MCD","SBUX","YUM","QSR","CMG","DPZ","DRI","TXRH","BJRI","CAKE"
]

# Remove dupes
SP500 = list(dict.fromkeys(SP500))

# ── CRYPTO ───────────────────────────────────────────────────────────────────
CRYPTO = [
    "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD","ADA-USD","AVAX-USD",
    "DOT-USD","MATIC-USD","LINK-USD","LTC-USD","BCH-USD","ATOM-USD","UNI-USD",
    "DOGE-USD","SHIB-USD","TRX-USD","XLM-USD","NEAR-USD","APT-USD"
]

# ── FX PAIRS ─────────────────────────────────────────────────────────────────
FX = [
    "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","NZDUSD=X",
    "USDCAD=X","EURGBP=X","EURJPY=X","GBPJPY=X","AUDJPY=X","CHFJPY=X",
    "EURCHF=X","EURAUD=X","GBPAUD=X","USDMXN=X","USDBRL=X","USDCNH=X",
    "USDINR=X","USDSEK=X","USDNOK=X","USDDKK=X","USDSGD=X","USDTRY=X"
]

# ── COMMODITIES / FUTURES PROXIES ────────────────────────────────────────────
COMMODITIES = [
    "GC=F","SI=F","CL=F","NG=F","HG=F","ZW=F","ZC=F","ZS=F","KC=F","SB=F",
    "CC=F","CT=F","OJ=F","LBS=F","LE=F","GF=F","HE=F","PL=F","PA=F"
]

# ── GLOBAL INDICES ────────────────────────────────────────────────────────────
INDICES = [
    "^GSPC","^NDX","^DJI","^RUT","^VIX",
    "^STOXX50E","^GDAXI","^FCHI","^FTSE","^AEX","^IBEX","^SSMI",
    "^N225","^HSI","^STI","^KS11","^TWII","^AXJO","^BSESN","^NSEI",
    "^BVSP","^MXX","^MERV","^IPSA","^GSPTSE"
]

ALL_SYMBOLS = [
    ("US Stocks", SP500, "2000-01-01"),
    ("Crypto", CRYPTO, "2015-01-01"),
    ("FX Pairs", FX, "2000-01-01"),
    ("Commodities", COMMODITIES, "2000-01-01"),
    ("Global Indices", INDICES, "2000-01-01"),
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM price_bars")
print(f"Bars before: {cur.fetchone()[0]:,}")

total_inserted = 0
total_errors = 0

for group_name, symbols, start in ALL_SYMBOLS:
    print(f"\n{'='*50}")
    print(f"{group_name} ({len(symbols)} symbols from {start})")
    print('='*50)
    
    for symbol in symbols:
        try:
            df = yf.download(symbol, start=start, end="2025-03-01", progress=False, auto_adjust=True)
            if df.empty:
                print(f"  {symbol}: no data")
                continue
            
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            inserted = 0
            for ts, row in df.iterrows():
                try:
                    cur.execute(
                        "INSERT INTO price_bars (symbol,timespan,ts,open,high,low,close,volume) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (symbol,timespan,ts) DO NOTHING",
                        (symbol,"1d",ts,
                         float(row["Open"]) if pd.notna(row["Open"]) else None,
                         float(row["High"]) if pd.notna(row["High"]) else None,
                         float(row["Low"]) if pd.notna(row["Low"]) else None,
                         float(row["Close"]) if pd.notna(row["Close"]) else None,
                         int(row["Volume"]) if pd.notna(row["Volume"]) else 0)
                    )
                    inserted += cur.rowcount
                except Exception:
                    pass
            conn.commit()
            total_inserted += inserted
            print(f"  {symbol}: {inserted} bars")
            time.sleep(0.3)
        except Exception as e:
            print(f"  {symbol}: ERROR {str(e)[:80]}")
            total_errors += 1
            conn.rollback()

cur.execute("SELECT COUNT(*) FROM price_bars")
final = cur.fetchone()[0]
print(f"\n{'='*50}")
print(f"Done. Inserted: {total_inserted:,} | Errors: {total_errors}")
print(f"Bars after: {final:,}")
cur.close()
conn.close()
