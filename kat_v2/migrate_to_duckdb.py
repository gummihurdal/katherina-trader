"""
KAT v2.0 — DuckDB Migration Script
=====================================
One-time migration from PostgreSQL to DuckDB.
Also precomputes technical features for fast training startup.

Usage:
    python3 migrate_to_duckdb.py --pg-uri postgresql://... --out /data/kat/kat_v2.db

Runtime: ~5-10 minutes
Output: Single kat_v2.db file (~500MB)
"""

import argparse
import duckdb
import pandas as pd
import sys
sys.path.insert(0, "/root/kat_v2")


def migrate(pg_uri: str, duckdb_path: str):
    print(f"Migrating PostgreSQL → DuckDB: {duckdb_path}")

    from sqlalchemy import create_engine
    engine = create_engine(pg_uri)
    conn   = duckdb.connect(duckdb_path)

    # ── Core tables ────────────────────────────────────────────────────────────
    tables = ["macro_data", "market_data_continuous"]

    for table in tables:
        print(f"  Migrating {table}...")
        df = pd.read_sql(f"SELECT * FROM {table}", engine)
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
        print(f"    → {len(df):,} rows")

    # ── Precompute technical features ─────────────────────────────────────────
    print("  Precomputing technical features...")

    from feature_pipeline import load_features, FUTURES_SYMBOLS, compute_technical_features

    # Load full history for precomputation
    futures_raw = conn.execute("""
        SELECT date, symbol, open, high, low, close, volume
        FROM market_data_continuous
        ORDER BY date, symbol
    """).df()

    futures_raw["date"] = pd.to_datetime(futures_raw["date"]).dt.tz_localize(None).dt.normalize()

    tech_frames = []
    for sym in FUTURES_SYMBOLS:
        sym_df = futures_raw[futures_raw["symbol"] == sym].copy()
        sym_df = sym_df.set_index("date")[["open", "high", "low", "close", "volume"]]
        tech   = compute_technical_features(sym_df)
        tech.columns = [f"{sym}_{c}" for c in tech.columns]
        tech["date"]   = tech.index
        tech["symbol"] = sym
        tech_frames.append(tech.reset_index(drop=True))

    tech_all = pd.concat(tech_frames, ignore_index=True)
    conn.execute("DROP TABLE IF EXISTS technical_features")
    conn.execute("CREATE TABLE technical_features AS SELECT * FROM tech_all")
    print(f"    → {len(tech_all):,} rows of precomputed technical features")

    conn.close()
    print(f"\nMigration complete: {duckdb_path}")
    print(f"Tables: macro_data, market_data_continuous, technical_features")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-uri", default="postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production")
    parser.add_argument("--out",    default="/data/kat/kat_v2.db")
    args = parser.parse_args()
    migrate(args.pg_uri, args.out)
