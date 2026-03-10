"""
Earnings history + News sentiment ingest for KAT
Sources:
  - yfinance earnings dates + EPS surprise
  - RSS feeds (Reuters, FT, Yahoo Finance) + finBERT sentiment
  - Wikipedia pageviews (retail attention signal)
  - Google Trends via pytrends
"""
import os, time, requests, psycopg2
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

DATABASE_URL = os.environ["DATABASE_URL"]
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ── Create tables ─────────────────────────────────────────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    earnings_date DATE NOT NULL,
    eps_estimate DOUBLE PRECISION,
    eps_actual DOUBLE PRECISION,
    surprise_pct DOUBLE PRECISION,
    revenue_estimate DOUBLE PRECISION,
    revenue_actual DOUBLE PRECISION,
    UNIQUE(symbol, earnings_date)
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS news_sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    ts TIMESTAMP NOT NULL,
    headline TEXT,
    source VARCHAR(50),
    sentiment_score DOUBLE PRECISION,
    sentiment_label VARCHAR(10),
    url TEXT,
    UNIQUE(symbol, ts, source)
)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS wikipedia_pageviews (
    id SERIAL PRIMARY KEY,
    article VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    date DATE NOT NULL,
    views INTEGER,
    UNIQUE(article, date)
)""")

conn.commit()
print("Tables ready: earnings_history, news_sentiment, wikipedia_pageviews")

# ── EARNINGS HISTORY via yfinance ─────────────────────────────────────────────
SYMBOLS = [
    "AAPL","MSFT","AMZN","NVDA","GOOGL","META","TSLA","JPM","BAC","GS",
    "AMD","INTC","NFLX","CRM","ADBE","ORCL","CSCO","IBM","QCOM","TXN",
    "V","MA","PYPL","SQ","COIN","XOM","CVX","COP","EOG","SLB",
    "JNJ","PFE","ABBV","MRK","BMY","LLY","AMGN","GILD","BIIB","MRNA",
    "SPY","QQQ","DIA","IWM","GLD","SLV","USO","TLT","HYG","VNQ"
]

print(f"\n{'='*60}")
print(f"Earnings History ({len(SYMBOLS)} symbols)")
print('='*60)

for symbol in SYMBOLS:
    try:
        ticker = yf.Ticker(symbol)
        
        # Get earnings history
        earnings = ticker.earnings_history
        if earnings is None or earnings.empty:
            print(f"  {symbol}: no earnings data")
            continue
            
        inserted = 0
        for idx, row in earnings.iterrows():
            try:
                eps_est = float(row.get("epsEstimate", 0) or 0)
                eps_act = float(row.get("epsActual", 0) or 0)
                surprise = ((eps_act - eps_est) / abs(eps_est) * 100) if eps_est != 0 else 0
                
                cur.execute("""
                    INSERT INTO earnings_history (symbol, earnings_date, eps_estimate, eps_actual, surprise_pct)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol, earnings_date) DO NOTHING
                """, (symbol, idx.date() if hasattr(idx,'date') else idx, eps_est, eps_act, surprise))
                inserted += cur.rowcount
            except:
                pass
        conn.commit()
        print(f"  {symbol}: {inserted} earnings records")
        time.sleep(0.5)
    except Exception as e:
        print(f"  {symbol}: ERROR {str(e)[:60]}")
        conn.rollback()

# ── NEWS SENTIMENT via RSS + finBERT ──────────────────────────────────────────
print(f"\n{'='*60}")
print("News Sentiment via RSS feeds")
print('='*60)

# Check if transformers available for finBERT
try:
    from transformers import pipeline
    sentiment_pipeline = pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        device=-1  # CPU
    )
    USE_FINBERT = True
    print("finBERT loaded successfully")
except Exception as e:
    USE_FINBERT = False
    print(f"finBERT not available ({e}) — storing headlines only, scoring later")

RSS_FEEDS = [
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US", "AAPL", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSFT&region=US&lang=en-US", "MSFT", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US", "NVDA", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US", "TSLA", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=AMZN&region=US&lang=en-US", "AMZN", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=META&region=US&lang=en-US", "META", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=GOOGL&region=US&lang=en-US", "GOOGL", "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=JPM&region=US&lang=en-US",  "JPM",  "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=AMD&region=US&lang=en-US",  "AMD",  "yahoo"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=NFLX&region=US&lang=en-US", "NFLX", "yahoo"),
    ("https://feeds.reuters.com/reuters/businessNews", None, "reuters"),
    ("https://feeds.reuters.com/reuters/technologyNews", None, "reuters_tech"),
    ("https://www.ft.com/rss/home", None, "ft"),
]

try:
    import feedparser
    
    for url, symbol, source in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            inserted = 0
            for entry in feed.entries[:50]:  # last 50 per feed
                headline = entry.get("title", "")
                ts = entry.get("published", datetime.now().isoformat())
                link = entry.get("link", "")
                
                score = 0.0
                label = "neutral"
                if USE_FINBERT and headline:
                    try:
                        result = sentiment_pipeline(headline[:512])[0]
                        label = result["label"].lower()
                        score = result["score"] if label == "positive" else -result["score"] if label == "negative" else 0.0
                    except:
                        pass
                
                try:
                    cur.execute("""
                        INSERT INTO news_sentiment (symbol, ts, headline, source, sentiment_score, sentiment_label, url)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (symbol, ts, source) DO NOTHING
                    """, (symbol, ts[:19], headline[:500], source, score, label, link[:500]))
                    inserted += cur.rowcount
                except:
                    pass
            conn.commit()
            print(f"  {source} ({symbol or 'general'}): {inserted} headlines")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {source}: ERROR {str(e)[:60]}")
            conn.rollback()
except ImportError:
    print("feedparser not installed — skipping RSS")

# ── WIKIPEDIA PAGEVIEWS ───────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("Wikipedia Pageviews (retail attention signal)")
print('='*60)

WIKI_ARTICLES = [
    ("Apple_Inc.", "AAPL"), ("Microsoft", "MSFT"), ("Nvidia", "NVDA"),
    ("Amazon_(company)", "AMZN"), ("Tesla,_Inc.", "TSLA"), ("Meta_Platforms", "META"),
    ("Alphabet_Inc.", "GOOGL"), ("JPMorgan_Chase", "JPM"), ("Bitcoin", "BTC-USD"),
    ("Ethereum", "ETH-USD"), ("GameStop", "GME"), ("AMC_Entertainment", "AMC"),
    ("Gold", "GLD"), ("Crude_oil", "CL=F"), ("S%26P_500", "SPY"),
]

start_date = "2015010100"
end_date   = "2025030100"

for article, symbol in WIKI_ARTICLES:
    try:
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{article}/monthly/{start_date}/{end_date}"
        r = requests.get(url, headers={"User-Agent": "KAT-ML-Bot/1.0"}, timeout=10)
        if r.status_code != 200:
            print(f"  {article}: HTTP {r.status_code}")
            continue
        
        items = r.json().get("items", [])
        inserted = 0
        for item in items:
            ts = item["timestamp"][:8]  # YYYYMMDD
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            views = item["views"]
            try:
                cur.execute("""
                    INSERT INTO wikipedia_pageviews (article, symbol, date, views)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (article, date) DO NOTHING
                """, (article, symbol, date, views))
                inserted += cur.rowcount
            except:
                pass
        conn.commit()
        print(f"  {article} ({symbol}): {inserted} months")
        time.sleep(0.3)
    except Exception as e:
        print(f"  {article}: ERROR {str(e)[:60]}")
        conn.rollback()

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("SENTIMENT DATABASE SUMMARY")
print('='*60)
for table in ["earnings_history", "news_sentiment", "wikipedia_pageviews"]:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"  {table:<30} {cur.fetchone()[0]:,} rows")

cur.close()
conn.close()
