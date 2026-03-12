#!/usr/bin/env python3
"""
KAT — Databento Master Ingestion Pipeline v2
=============================================
Three-tier data pull using continuous, parent, and ALL_SYMBOLS
symbology. Stores everything into PostgreSQL on Hetzner.

Verified costs:
  Tier 1 — Continuous 1m, 7 symbols, 11yr:  ~$45  ← RUN THIS FIRST
  Tier 2 — Parent all-expiry 1h, 11yr:       ~$89  ← Phase 2
  Tier 3 — Options chains daily, 4yr:         TBD  ← Phase 3

Usage:
    export DATABENTO_API_KEY=db-xxxxxxxxxxxx
    export KAT_DB_URI=postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production

    python3 ingest_databento.py --estimate          # cost check only
    python3 ingest_databento.py --tier 1            # run Tier 1 (~$45)
    python3 ingest_databento.py --tier 2            # run Tier 2 (~$89)
    python3 ingest_databento.py --mode update       # daily cron increment
    python3 ingest_databento.py --status            # DB row counts

Install:
    pip install databento psycopg2-binary pandas
"""

import os, sys, time, argparse, logging
from datetime import datetime, timedelta, date

import databento as db
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Credentials ───────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DATABENTO_API_KEY", "")
DB_URI  = os.environ.get("KAT_DB_URI",
          "postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production")

if not API_KEY:
    sys.exit("ERROR: export DATABENTO_API_KEY=db-xxxxxxxxxxxx")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("kat.ingest")

# ── Instrument Universe ────────────────────────────────────────────────────────
# Tier 1 — continuous front-month (best for RL training)
TIER1 = {
    "MES": ("MES.c.0", "Micro E-mini S&P 500"),
    "MNQ": ("MNQ.c.0", "Micro Nasdaq-100"),
    "MCL": ("MCL.c.0", "Micro WTI Crude Oil"),
    "MGC": ("MGC.c.0", "Micro Gold"),
    "ZB":  ("ZB.c.0",  "30yr Treasury Bond"),
    "MHG": ("MHG.c.0", "Micro Copper"),
    "SI":  ("SI.c.0",  "Silver"),
}

# Tier 2 — all expiries (roll analysis, options prep)
TIER2 = {
    "ES":  ("ES.FUT",  "E-mini S&P all expiries"),
    "NQ":  ("NQ.FUT",  "Nasdaq all expiries"),
    "CL":  ("CL.FUT",  "WTI Crude all expiries"),
    "GC":  ("GC.FUT",  "Gold all expiries"),
    "ZB":  ("ZB.FUT",  "30yr Bond all expiries"),
    "HG":  ("HG.FUT",  "Copper all expiries"),
}

# Tier 3 — options chains
TIER3 = {
    "ES_OPT": ("ES.OPT", "S&P 500 options"),
    "NQ_OPT": ("NQ.OPT", "Nasdaq options"),
    "GC_OPT": ("GC.OPT", "Gold options"),
    "CL_OPT": ("CL.OPT", "Crude options"),
}

# ── DB Setup ──────────────────────────────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS market_data_futures (
    symbol       VARCHAR(20)   NOT NULL,
    stype        VARCHAR(20)   NOT NULL,
    schema       VARCHAR(20)   NOT NULL,
    ts_event     TIMESTAMPTZ   NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    volume       BIGINT,
    bid_px       DOUBLE PRECISION,
    ask_px       DOUBLE PRECISION,
    trade_price  DOUBLE PRECISION,
    trade_size   INTEGER,
    side         CHAR(1),
    instr_id     INTEGER,
    ingested_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, schema, ts_event)
);
CREATE INDEX IF NOT EXISTS idx_mdf_sym_ts ON market_data_futures (symbol, ts_event DESC);
CREATE INDEX IF NOT EXISTS idx_mdf_ts     ON market_data_futures (ts_event DESC);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id         SERIAL PRIMARY KEY,
    tier       INTEGER,
    symbol     VARCHAR(20),
    stype      VARCHAR(20),
    schema     VARCHAR(20),
    start_date DATE,
    end_date   DATE,
    rows_added INTEGER,
    duration_s DOUBLE PRECISION,
    status     VARCHAR(20),
    error      TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

def get_conn():
    return psycopg2.connect(DB_URI)

def setup_db():
    with get_conn() as conn:
        conn.cursor().execute(DDL)
        conn.commit()
    log.info("DB schema ready.")

def last_ingested(symbol, schema):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(end_date) FROM ingestion_log "
                            "WHERE symbol=%s AND schema=%s AND status='success'",
                            (symbol, schema))
                r = cur.fetchone()
                return r[0] if r and r[0] else None
    except Exception:
        return None

def log_result(tier, symbol, stype, schema, start, end, rows, dur, status, error=None):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ingestion_log
                        (tier,symbol,stype,schema,start_date,end_date,
                         rows_added,duration_s,status,error)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (tier,symbol,stype,schema,str(start),str(end),
                      rows,round(dur,1),status,error))
            conn.commit()
    except Exception as e:
        log.warning(f"Could not write log: {e}")

# ── Price Scaling ─────────────────────────────────────────────────────────────
def scale(df):
    for col in ["open","high","low","close","price","bid_px","ask_px","trade_price"]:
        if col in df.columns:
            s = df[col].dropna()
            if len(s) and s.abs().median() > 1_000_000:
                df[col] = df[col] / 1e9
    return df

# ── Pull One Symbol ───────────────────────────────────────────────────────────
def pull(client, sym_key, db_sym, stype_in, schema,
         start_str, end_str, tier, dataset="GLBX.MDP3"):
    t0 = time.time()
    log.info(f"  [{sym_key}] {stype_in}/{schema}  {start_str[:10]} → {end_str[:10]}")

    data = client.timeseries.get_range(
        dataset=dataset,
        symbols=[db_sym],
        stype_in=stype_in,
        schema=schema,
        start=start_str,
        end=end_str,
    )
    df = data.to_df()
    if df.empty:
        log.warning(f"  [{sym_key}] No data returned")
        return 0

    df = scale(df)
    if "ts_event" not in df.columns:
        df = df.reset_index()

    is_ohlcv = schema.startswith("ohlcv")

    records = []
    for _, row in df.iterrows():
        if is_ohlcv:
            records.append((sym_key, stype_in, schema,
                             row.get("ts_event"),
                             row.get("open"), row.get("high"),
                             row.get("low"),  row.get("close"),
                             row.get("volume"),
                             None, None, None, None, None,
                             row.get("instrument_id")))
        else:
            records.append((sym_key, stype_in, schema,
                             row.get("ts_event"),
                             None, None, None, None, None,
                             row.get("bid_px"), row.get("ask_px"),
                             row.get("price") or row.get("trade_price"),
                             row.get("size")  or row.get("trade_size"),
                             row.get("side"),
                             row.get("instrument_id")))

    SQL = """
        INSERT INTO market_data_futures
            (symbol,stype,schema,ts_event,
             open,high,low,close,volume,
             bid_px,ask_px,trade_price,trade_size,side,instr_id)
        VALUES %s
        ON CONFLICT (symbol,schema,ts_event) DO NOTHING
    """
    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(records), 5000):
                execute_values(cur, SQL, records[i:i+5000])
                inserted += cur.rowcount
        conn.commit()

    dur = time.time() - t0
    close_col = df.get("close", df.get("price", pd.Series(dtype=float)))
    price_rng = f"{close_col.dropna().min():.2f}–{close_col.dropna().max():.2f}" \
                if len(close_col.dropna()) else "N/A"
    log.info(f"  [{sym_key}] ✓ {inserted:,} rows | {dur:.1f}s | price {price_rng}")

    log_result(tier, sym_key, stype_in, schema,
               start_str[:10], end_str[:10], inserted, dur, "success")
    return inserted

# ── Cost Estimate ─────────────────────────────────────────────────────────────
def cost_check(client, symbols, stype_in, schema, start, end, dataset="GLBX.MDP3"):
    try:
        c = client.metadata.get_cost(
            dataset=dataset, symbols=symbols,
            stype_in=stype_in, schema=schema,
            start=start, end=end)
        return float(c)
    except Exception as e:
        log.warning(f"Cost check failed: {e}")
        return None

def confirm_cost(cost, label):
    if cost is None:
        log.warning("Could not verify cost — proceed with caution")
        yn = input("Proceed anyway? [y/N] ").strip().lower()
        return yn == "y"
    log.info(f"Estimated cost ({label}): ${cost:.2f}")
    if cost < 5:
        return True  # auto-approve small amounts
    yn = input(f"Proceed with ${cost:.2f}? [y/N] ").strip().lower()
    return yn == "y"

# ── Tier Runners ──────────────────────────────────────────────────────────────
def run_tier1(client, mode="full"):
    log.info("=" * 60)
    log.info("TIER 1 — Continuous front-month | ohlcv-1m | 2015→now")
    log.info("Cost: ~$45 | Purpose: Primary RL training dataset")
    log.info("=" * 60)

    end   = str(datetime.now().date())
    start = "2015-01-01"
    syms  = [v[0] for v in TIER1.values()]

    if not confirm_cost(cost_check(client, syms, "continuous", "ohlcv-1m", start, end),
                        "Tier 1"):
        return

    total = 0
    for sym_key, (db_sym, _) in TIER1.items():
        pull_start = start
        if mode == "update":
            last = last_ingested(sym_key, "ohlcv-1m")
            pull_start = str(last + timedelta(days=1)) if last else start
            if pull_start >= end:
                log.info(f"  [{sym_key}] up to date")
                continue
        try:
            total += pull(client, sym_key, db_sym, "continuous",
                          "ohlcv-1m", pull_start, end, tier=1)
        except Exception as e:
            log.error(f"  [{sym_key}] FAILED: {e}")
            log_result(1, sym_key, "continuous", "ohlcv-1m",
                       pull_start, end, 0, 0, "error", str(e))
    log.info(f"Tier 1 done — {total:,} rows total")

def run_tier2(client, mode="full"):
    log.info("=" * 60)
    log.info("TIER 2 — All expiries (parent) | ohlcv-1h | 2015→now")
    log.info("Cost: ~$89 | Purpose: Roll analysis, multi-expiry features")
    log.info("=" * 60)

    end   = str(datetime.now().date())
    start = "2015-01-01"
    syms  = [v[0] for v in TIER2.values()]

    if not confirm_cost(cost_check(client, syms, "parent", "ohlcv-1h", start, end),
                        "Tier 2"):
        return

    total = 0
    for sym_key, (db_sym, _) in TIER2.items():
        label = f"{sym_key}_FULL"
        pull_start = start
        if mode == "update":
            last = last_ingested(label, "ohlcv-1h")
            pull_start = str(last + timedelta(days=1)) if last else start
        try:
            total += pull(client, label, db_sym, "parent",
                          "ohlcv-1h", pull_start, end, tier=2)
        except Exception as e:
            log.error(f"  [{sym_key}] FAILED: {e}")
            log_result(2, label, "parent", "ohlcv-1h",
                       pull_start, end, 0, 0, "error", str(e))
    log.info(f"Tier 2 done — {total:,} rows total")

def run_tier3(client, mode="full"):
    log.info("=" * 60)
    log.info("TIER 3 — Options chains | ohlcv-1d | 2022→now")
    log.info("Purpose: Options module training — IV chains, strikes")
    log.info("=" * 60)

    end   = str(datetime.now().date())
    start = "2022-01-01"
    syms  = [v[0] for v in TIER3.values()]

    if not confirm_cost(cost_check(client, syms, "parent", "ohlcv-1d", start, end),
                        "Tier 3"):
        return

    total = 0
    for sym_key, (db_sym, _) in TIER3.items():
        try:
            total += pull(client, sym_key, db_sym, "parent",
                          "ohlcv-1d", start, end, tier=3)
        except Exception as e:
            log.error(f"  [{sym_key}] FAILED: {e}")
    log.info(f"Tier 3 done — {total:,} rows total")

# ── Status ────────────────────────────────────────────────────────────────────
def print_status():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol, schema, COUNT(*) as rows,
                           MIN(ts_event)::date, MAX(ts_event)::date
                    FROM market_data_futures
                    GROUP BY symbol, schema ORDER BY symbol, schema
                """)
                rows = cur.fetchall()
        print(f"\n{'Symbol':<14} {'Schema':<12} {'Rows':>12}  {'From':<12}  To")
        print("-" * 62)
        for r in rows:
            print(f"{r[0]:<14} {r[1]:<12} {r[2]:>12,}  {str(r[3]):<12}  {r[4]}")
        print()
    except Exception as e:
        print(f"DB error: {e}")

# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="KAT Databento Ingestion")
    p.add_argument("--tier",     type=int, choices=[1,2,3])
    p.add_argument("--mode",     default="full", choices=["full","update"])
    p.add_argument("--estimate", action="store_true")
    p.add_argument("--status",   action="store_true")
    args = p.parse_args()

    client = db.Historical(API_KEY)

    if args.status:
        print_status(); return

    if args.estimate:
        end = str(datetime.now().date())
        c1 = cost_check(client,[v[0] for v in TIER1.values()],"continuous","ohlcv-1m","2015-01-01",end)
        c2 = cost_check(client,[v[0] for v in TIER2.values()],"parent",    "ohlcv-1h","2015-01-01",end)
        c3 = cost_check(client,[v[0] for v in TIER3.values()],"parent",    "ohlcv-1d","2022-01-01",end)
        print(f"\n  Tier 1 (continuous 1m 11yr 7sym): ${c1:.2f}" if c1 else "  Tier 1: unavailable")
        print(f"  Tier 2 (parent    1h 11yr 6sym): ${c2:.2f}" if c2 else "  Tier 2: unavailable")
        print(f"  Tier 3 (options   1d  4yr 4sym): ${c3:.2f}" if c3 else "  Tier 3: unavailable")
        print()
        return

    setup_db()

    tier = args.tier
    if tier == 1 or tier is None: run_tier1(client, args.mode)
    if tier == 2:                  run_tier2(client, args.mode)
    if tier == 3:                  run_tier3(client, args.mode)

    print_status()

if __name__ == "__main__":
    main()
