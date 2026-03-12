#!/usr/bin/env python3
"""
KAT — Databento Data Ingestion Pipeline
=========================================
Pulls CME futures data (MES, MNQ, MCL, MGC, ZB) into PostgreSQL
on the Hetzner server, ready for Stage 2 training.

Usage:
    export DATABENTO_API_KEY=db-U6SHwwHnQP8w76gcsss5AgAAqpkkA
    export KAT_DB_URI=postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production

    # Pull all instruments, 5 years, 1-minute bars (recommended first run)
    python3 scripts/ingest_databento.py --schema ohlcv-1m --years 5

    # Pull tick-level data (expensive — run after checking cost)
    python3 scripts/ingest_databento.py --schema trades --years 2 --symbols MES MNQ

    # Daily update cron (add to crontab: 0 6 * * 1-5)
    python3 scripts/ingest_databento.py --mode update

Install:
    pip install databento psycopg2-binary pandas
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta, date
from pathlib import Path

import databento as db
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DATABENTO_API_KEY", "db-U6SHwwHnQP8w76gcsss5AgAAqpkkA")
DB_URI  = os.environ.get("KAT_DB_URI", "postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production")

DATASET = "GLBX.MDP3"  # CME Globex

# Continuous front-month contracts — best for training (auto roll-adjusted)
INSTRUMENTS = {
    "MES":  "MES.c.0",   # Micro E-mini S&P 500   — primary equity index
    "MNQ":  "MNQ.c.0",   # Micro Nasdaq-100        — tech/growth
    "MCL":  "MCL.c.0",   # Micro WTI Crude Oil     — geopolitical/energy
    "MGC":  "MGC.c.0",   # Micro Gold              — risk-off / safe haven
    "ZB":   "ZB.c.0",    # 30yr Treasury Bond      — macro / rates
    "MHG":  "MHG.c.0",   # Micro Copper            — global growth indicator
    "SI":   "SI.c.0",    # Silver                  — commodity momentum
}

# Schema options — costs vary significantly
SCHEMAS = {
    "ohlcv-1m":  "1-minute OHLCV bars — best training cost/quality ratio",
    "ohlcv-1h":  "1-hour OHLCV bars  — cheapest, use for long backtests",
    "ohlcv-1d":  "Daily OHLCV bars   — free tier friendly",
    "trades":    "Every trade tick   — most expensive, best for microstructure",
    "mbp-1":     "Top of book        — bid/ask spread, order flow signals",
    "tbbo":      "Trade + best B/O   — good balance of depth vs cost",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("kat.ingest")


# ── Database Setup ─────────────────────────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS market_data_futures (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL,
    schema          VARCHAR(20)  NOT NULL,
    ts_event        TIMESTAMPTZ  NOT NULL,
    open            DOUBLE PRECISION,
    high            DOUBLE PRECISION,
    low             DOUBLE PRECISION,
    close           DOUBLE PRECISION,
    volume          BIGINT,
    -- Tick fields (populated for trades/mbp schemas)
    bid_px          DOUBLE PRECISION,
    ask_px          DOUBLE PRECISION,
    bid_sz          INTEGER,
    ask_sz          INTEGER,
    side            CHAR(1),
    price           DOUBLE PRECISION,
    size            INTEGER,
    -- Metadata
    ingested_at     TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (symbol, schema, ts_event)
);

CREATE INDEX IF NOT EXISTS idx_futures_symbol_ts
    ON market_data_futures (symbol, ts_event DESC);

CREATE INDEX IF NOT EXISTS idx_futures_ts
    ON market_data_futures (ts_event DESC);

-- Ingestion log to track what we've pulled
CREATE TABLE IF NOT EXISTS ingestion_log (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20),
    schema      VARCHAR(20),
    start_date  DATE,
    end_date    DATE,
    rows_added  INTEGER,
    cost_usd    DOUBLE PRECISION,
    duration_s  DOUBLE PRECISION,
    status      VARCHAR(20),
    error       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
"""


def get_conn():
    return psycopg2.connect(DB_URI)


def setup_db():
    log.info("Setting up database tables...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    log.info("Database ready.")


def get_last_ingested(symbol: str, schema: str) -> date | None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MAX(end_date) FROM ingestion_log
                    WHERE symbol = %s AND schema = %s AND status = 'success'
                """, (symbol, schema))
                row = cur.fetchone()
                return row[0] if row and row[0] else None
    except Exception:
        return None


# ── Cost Estimate ─────────────────────────────────────────────────────────────
def estimate_cost(client, symbols: list, schema: str, start: str, end: str):
    try:
        cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=symbols,
            schema=schema,
            start=start,
            end=end,
        )
        return cost
    except Exception as e:
        log.warning(f"Cost estimate unavailable: {e}")
        return None


# ── Data Pull ─────────────────────────────────────────────────────────────────
def pull_ohlcv(client, symbol_key: str, symbol: str, schema: str,
               start: str, end: str) -> pd.DataFrame:
    log.info(f"Pulling {symbol_key} ({symbol}) | {schema} | {start} → {end}")
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[symbol],
        schema=schema,
        start=start,
        end=end,
    )
    df = data.to_df()
    if df.empty:
        log.warning(f"  No data returned for {symbol_key}")
        return df

    df["symbol"] = symbol_key
    df["schema"] = schema

    # Normalize column names from Databento
    col_map = {
        "open":   "open",
        "high":   "high",
        "low":    "low",
        "close":  "close",
        "volume": "volume",
        "ts_event": "ts_event",
    }
    df = df.rename(columns={v: k for k, v in col_map.items() if v in df.columns})

    # Price scaling — Databento returns prices in fixed-point (divide by 1e9)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns and df[col].max() > 1_000_000:
            df[col] = df[col] / 1_000_000_000

    log.info(f"  → {len(df):,} rows | "
             f"price range: {df['close'].min():.2f} – {df['close'].max():.2f}")
    return df


def pull_ticks(client, symbol_key: str, symbol: str, schema: str,
               start: str, end: str) -> pd.DataFrame:
    log.info(f"Pulling TICKS {symbol_key} ({symbol}) | {schema} | {start} → {end}")
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[symbol],
        schema=schema,
        start=start,
        end=end,
    )
    df = data.to_df()
    df["symbol"] = symbol_key
    df["schema"] = schema

    # Scale prices
    for col in ["price", "bid_px", "ask_px"]:
        if col in df.columns and df[col].max() > 1_000_000:
            df[col] = df[col] / 1_000_000_000

    log.info(f"  → {len(df):,} ticks")
    return df


# ── Database Write ─────────────────────────────────────────────────────────────
def write_to_db(df: pd.DataFrame, symbol: str, schema: str,
                start_date: date, end_date: date) -> int:
    if df.empty:
        return 0

    is_ohlcv = schema.startswith("ohlcv")

    if is_ohlcv:
        records = [
            (
                row.get("symbol", symbol),
                schema,
                row.get("ts_event"),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                None, None, None, None, None, None, None,
            )
            for _, row in df.iterrows()
        ]
    else:
        records = [
            (
                row.get("symbol", symbol),
                schema,
                row.get("ts_event"),
                None, None, None, None, None,
                row.get("bid_px"),
                row.get("ask_px"),
                row.get("bid_sz"),
                row.get("ask_sz"),
                row.get("side"),
                row.get("price"),
                row.get("size"),
            )
            for _, row in df.iterrows()
        ]

    insert_sql = """
        INSERT INTO market_data_futures
            (symbol, schema, ts_event, open, high, low, close, volume,
             bid_px, ask_px, bid_sz, ask_sz, side, price, size)
        VALUES %s
        ON CONFLICT (symbol, schema, ts_event) DO NOTHING
    """

    inserted = 0
    batch_size = 5000
    with get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                execute_values(cur, insert_sql, batch)
                inserted += cur.rowcount
            # Log ingestion
            cur.execute("""
                INSERT INTO ingestion_log
                    (symbol, schema, start_date, end_date, rows_added, status)
                VALUES (%s, %s, %s, %s, %s, 'success')
            """, (symbol, schema, start_date, end_date, inserted))
        conn.commit()

    log.info(f"  → DB: {inserted:,} new rows written")
    return inserted


# ── Main Ingestion ─────────────────────────────────────────────────────────────
def ingest(symbols: list, schema: str, years: int, mode: str):
    client = db.Historical(API_KEY)
    setup_db()

    end_date   = datetime.now().date()
    start_date = end_date - timedelta(days=365 * years)

    total_rows = 0
    total_start = datetime.now()

    log.info("=" * 60)
    log.info(f"KAT Databento Ingestion — {schema}")
    log.info(f"Symbols: {symbols}")
    log.info(f"Period:  {start_date} → {end_date} ({years}yr)")
    log.info("=" * 60)

    # Cost check first
    db_symbols = [INSTRUMENTS[s] for s in symbols if s in INSTRUMENTS]
    cost = estimate_cost(client, db_symbols, schema,
                         str(start_date), str(end_date))
    if cost is not None:
        log.info(f"Estimated cost: ${cost:.4f}")
        if cost > 50:
            confirm = input(f"\nCost is ${cost:.2f}. Proceed? [y/N] ").strip().lower()
            if confirm != "y":
                log.info("Aborted by user.")
                return

    for sym_key in symbols:
        if sym_key not in INSTRUMENTS:
            log.warning(f"Unknown symbol: {sym_key}, skipping")
            continue

        symbol = INSTRUMENTS[sym_key]
        t0 = datetime.now()

        # In update mode, only pull since last successful ingest
        if mode == "update":
            last = get_last_ingested(sym_key, schema)
            pull_start = (last + timedelta(days=1)) if last else start_date
            if pull_start >= end_date:
                log.info(f"{sym_key} — already up to date (last: {last})")
                continue
        else:
            pull_start = start_date

        try:
            if schema.startswith("ohlcv"):
                df = pull_ohlcv(client, sym_key, symbol, schema,
                                str(pull_start), str(end_date))
            else:
                df = pull_ticks(client, sym_key, symbol, schema,
                                str(pull_start), str(end_date))

            rows = write_to_db(df, sym_key, schema, pull_start, end_date)
            total_rows += rows

            elapsed = (datetime.now() - t0).total_seconds()
            log.info(f"{sym_key} done in {elapsed:.1f}s — {rows:,} rows")

        except Exception as e:
            log.error(f"{sym_key} FAILED: {e}")
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ingestion_log
                            (symbol, schema, start_date, end_date, rows_added, status, error)
                        VALUES (%s, %s, %s, %s, 0, 'error', %s)
                    """, (sym_key, schema, pull_start, end_date, str(e)))
                conn.commit()

    total_elapsed = (datetime.now() - total_start).total_seconds()
    log.info("=" * 60)
    log.info(f"COMPLETE — {total_rows:,} total rows in {total_elapsed:.1f}s")
    log.info(f"Schema: {schema} | {SCHEMAS.get(schema, '')}")
    log.info("=" * 60)

    # Summary stats
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol, COUNT(*) as rows,
                           MIN(ts_event) as earliest,
                           MAX(ts_event) as latest
                    FROM market_data_futures
                    WHERE schema = %s
                    GROUP BY symbol
                    ORDER BY symbol
                """, (schema,))
                rows = cur.fetchall()
                if rows:
                    log.info("\nDatabase summary:")
                    log.info(f"  {'Symbol':<8} {'Rows':>12}  {'Earliest':<22}  {'Latest'}")
                    for r in rows:
                        log.info(f"  {r[0]:<8} {r[1]:>12,}  {str(r[2])[:19]:<22}  {str(r[3])[:19]}")
    except Exception:
        pass


# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="KAT Databento Ingestion Pipeline")
    parser.add_argument("--symbols", nargs="+",
                        default=list(INSTRUMENTS.keys()),
                        help="Symbols to pull (default: all)")
    parser.add_argument("--schema", default="ohlcv-1m",
                        choices=list(SCHEMAS.keys()),
                        help="Data schema (default: ohlcv-1m)")
    parser.add_argument("--years", type=int, default=5,
                        help="Years of history to pull (default: 5)")
    parser.add_argument("--mode", default="full",
                        choices=["full", "update"],
                        help="full=backfill, update=incremental (default: full)")
    parser.add_argument("--list-schemas", action="store_true",
                        help="List available schemas and exit")
    parser.add_argument("--status", action="store_true",
                        help="Show DB status and exit")

    args = parser.parse_args()

    if args.list_schemas:
        print("\nAvailable schemas:")
        for k, v in SCHEMAS.items():
            print(f"  {k:<12} {v}")
        return

    if args.status:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT symbol, schema, COUNT(*) as rows,
                               MIN(ts_event) as earliest,
                               MAX(ts_event) as latest
                        FROM market_data_futures
                        GROUP BY symbol, schema
                        ORDER BY symbol, schema
                    """)
                    rows = cur.fetchall()
                    if rows:
                        print(f"\n{'Symbol':<8} {'Schema':<12} {'Rows':>12}  Earliest → Latest")
                        print("-" * 70)
                        for r in rows:
                            print(f"{r[0]:<8} {r[1]:<12} {r[2]:>12,}  "
                                  f"{str(r[3])[:19]} → {str(r[4])[:19]}")
                    else:
                        print("No data in database yet.")
        except Exception as e:
            print(f"DB error: {e}")
        return

    ingest(args.symbols, args.schema, args.years, args.mode)


if __name__ == "__main__":
    main()
