"""
KAT v2.0 — Feature Pipeline
============================
Loads macro + futures data from DuckDB and computes all features
including technical indicators. Designed to be called once per
environment instance at startup — data cached in RAM during training.

Architecture:
    Stream 1: Macro      — 1404 features (FRED pivot, 47 series)
    Stream 2: Portfolio  — 108  features (positions, PnL, drawdown)
    Stream 3: Futures    — 210  features (OHLCV, 6 contracts)
    Stream 4: Technical  — 150  features (RSI, MACD, ATR, BB, etc.)
    ─────────────────────────────────────────────────────────────
    Total obs size: 1872

Author: KAT Research Team
Version: 2.0
"""

import numpy as np
import pandas as pd
import duckdb
from typing import Tuple, Dict

# ── Constants ────────────────────────────────────────────────────────────────
FUTURES_SYMBOLS = ["CL", "GC", "HG", "ES", "NQ", "ZB"]
MACRO_FEATURES  = 1404
PORTFOLIO_FEATURES = 108
FUTURES_FEATURES   = 210  # 35 per contract × 6 contracts
TECHNICAL_FEATURES = 150  # 25 per contract × 6 contracts
TOTAL_OBS_SIZE = MACRO_FEATURES + PORTFOLIO_FEATURES + FUTURES_FEATURES + TECHNICAL_FEATURES


# ── Technical Indicator Computation ──────────────────────────────────────────

def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 25 technical indicators for a single futures contract.

    All indicators are normalized to [0, 1] or [-1, 1] range to
    ensure compatibility with neural network inputs.

    Args:
        df: DataFrame with columns [open, high, low, close, volume]
            sorted ascending by date.

    Returns:
        DataFrame with 25 technical feature columns appended.
        NaN values from rolling windows filled with 0.
    """
    out = pd.DataFrame(index=df.index)
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]

    # ── RSI (14) ─────────────────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-8)
    out["rsi_14"] = (100 - 100 / (1 + rs)) / 100  # normalize to [0, 1]

    # ── MACD (12/26/9) ───────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = (ema12 - ema26) / (close + 1e-8)
    out["macd"]        = macd.clip(-0.05, 0.05) / 0.05   # normalize
    out["macd_signal"] = macd.ewm(span=9, adjust=False).mean().clip(-0.05, 0.05) / 0.05
    out["macd_hist"]   = (out["macd"] - out["macd_signal"]).clip(-1, 1)

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────────
    ma20  = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    bb_range = (bb_upper - bb_lower).clip(lower=1e-8)
    out["bb_position"] = ((close - bb_lower) / bb_range).clip(0, 1)
    out["bb_width"]    = (bb_range / (ma20 + 1e-8)).clip(0, 0.2) / 0.2

    # ── ATR (14) ──────────────────────────────────────────────────────────────
    hl  = high - low
    hcp = (high - close.shift()).abs()
    lcp = (low - close.shift()).abs()
    tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out["atr_pct"] = (atr / (close + 1e-8)).clip(0, 0.05) / 0.05  # normalize

    # ── Stochastic Oscillator (14, 3) ─────────────────────────────────────────
    low14  = low.rolling(14).min()
    high14 = high.rolling(14).max()
    stoch_range = (high14 - low14).clip(lower=1e-8)
    stoch_k = ((close - low14) / stoch_range).clip(0, 1)
    out["stoch_k"] = stoch_k
    out["stoch_d"] = stoch_k.rolling(3).mean()

    # ── Williams %R (14) ──────────────────────────────────────────────────────
    out["williams_r"] = 1 - stoch_k  # %R is inverse of Stochastic

    # ── Rate of Change (momentum) ─────────────────────────────────────────────
    for period in [1, 5, 10, 20, 60]:
        roc = close.pct_change(period)
        out[f"roc_{period}d"] = roc.clip(-0.3, 0.3) / 0.3  # normalize

    # ── Volume Ratio ──────────────────────────────────────────────────────────
    vol_ma20 = vol.rolling(20).mean()
    out["volume_ratio"] = (vol / (vol_ma20 + 1e-8)).clip(0, 5) / 5

    # ── Trend Strength (ADX proxy) ────────────────────────────────────────────
    # Simple proxy: ratio of directional moves
    up_moves   = (close - close.shift()).clip(lower=0).rolling(14).mean()
    down_moves = (close.shift() - close).clip(lower=0).rolling(14).mean()
    total = up_moves + down_moves + 1e-8
    out["trend_strength"] = (up_moves / total).fillna(0.5)

    # ── Mean Reversion Signal ─────────────────────────────────────────────────
    # Distance from 20-day moving average
    out["ma20_dist"] = ((close - ma20) / (ma20 + 1e-8)).clip(-0.1, 0.1) / 0.1

    # Fill NaN from rolling windows with 0 (neutral signal)
    out = out.fillna(0)

    # Verify feature count
    assert len(out.columns) == 25, f"Expected 25 technical features, got {len(out.columns)}"

    return out


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_features(
    db_path: str,
    start_date: str,
    end_date: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load and compute all features from DuckDB.

    Returns:
        macro_df:    (n_days, 1404) — FRED macro pivot
        futures_df:  (n_days, 210)  — OHLCV for 6 contracts
        tech_df:     (n_days, 150)  — technical indicators

    All DataFrames share the same date index.
    """
    conn = duckdb.connect(db_path, read_only=True)

    # ── Macro features ────────────────────────────────────────────────────────
    macro_raw = conn.execute("""
        SELECT ts, series_id, value
        FROM macro_data
        ORDER BY ts
    """).df()

    macro_raw["ts"] = pd.to_datetime(macro_raw["ts"]).dt.tz_localize(None).dt.normalize()
    macro_pivot = macro_raw.pivot_table(
        index="ts", columns="series_id", values="value", aggfunc="last"
    )
    macro_pivot = macro_pivot.ffill().fillna(0)

    # Filter by date AFTER pivot to ensure consistent columns
    sd = pd.Timestamp(start_date)
    ed = pd.Timestamp(end_date)
    macro_pivot = macro_pivot[(macro_pivot.index >= sd) & (macro_pivot.index <= ed)]

    # ── Futures OHLCV ─────────────────────────────────────────────────────────
    futures_raw = conn.execute("""
        SELECT date, symbol, open, high, low, close, volume
        FROM market_data_continuous
        ORDER BY date, symbol
    """).df()

    futures_raw["date"] = pd.to_datetime(futures_raw["date"]).dt.tz_localize(None).dt.normalize()

    # Build wide futures dataframe (35 features per symbol)
    futures_frames = []
    tech_frames    = []

    for sym in FUTURES_SYMBOLS:
        sym_df = futures_raw[futures_raw["symbol"] == sym].copy()
        sym_df = sym_df.set_index("date")[["open", "high", "low", "close", "volume"]]
        sym_df = sym_df.reindex(macro_pivot.index).ffill().fillna(0)

        # OHLCV + rolling lookbacks (5 features × 7 lookbacks = 35 per symbol)
        sym_features = {}
        for col in ["open", "high", "low", "close", "volume"]:
            sym_features[f"{sym}_{col}"] = sym_df[col]
            for lookback in [5, 10, 20, 60]:
                sym_features[f"{sym}_{col}_ma{lookback}"] = (
                    sym_df[col].rolling(lookback).mean().fillna(sym_df[col])
                )
                # Normalize by current value
                sym_features[f"{sym}_{col}_ma{lookback}"] = (
                    sym_features[f"{sym}_{col}_ma{lookback}"] /
                    (sym_features[f"{sym}_{col}"] + 1e-8)
                )
        futures_frames.append(pd.DataFrame(sym_features, index=macro_pivot.index))

        # Technical indicators (25 per symbol)
        tech = compute_technical_features(sym_df)
        tech.columns = [f"{sym}_{c}" for c in tech.columns]
        tech_frames.append(tech)

    futures_df = pd.concat(futures_frames, axis=1).fillna(0)
    tech_df    = pd.concat(tech_frames, axis=1).fillna(0)

    conn.close()

    # Filter to date range
    futures_df = futures_df[(futures_df.index >= sd) & (futures_df.index <= ed)]
    tech_df    = tech_df[(tech_df.index >= sd) & (tech_df.index <= ed)]

    # Align all DataFrames to common date index
    common_idx = macro_pivot.index.intersection(futures_df.index)
    macro_pivot = macro_pivot.loc[common_idx]
    futures_df  = futures_df.loc[common_idx]
    tech_df     = tech_df.loc[common_idx]

    print(
        f"Loaded: {len(common_idx)} days | "
        f"macro: {macro_pivot.shape[1]} | "
        f"futures: {futures_df.shape[1]} | "
        f"technical: {tech_df.shape[1]} | "
        f"total obs: {macro_pivot.shape[1] + futures_df.shape[1] + tech_df.shape[1] + PORTFOLIO_FEATURES}"
    )

    return macro_pivot, futures_df, tech_df


# ── Verification ──────────────────────────────────────────────────────────────

def verify_obs_size(db_path: str) -> bool:
    """
    Verify train and eval observation spaces have identical sizes.
    MUST pass before launching any training run.
    """
    from kat_env_v2 import KATEnvV2

    train_env = KATEnvV2(db_path=db_path, start_date="2015-01-01", end_date="2023-12-31")
    eval_env  = KATEnvV2(db_path=db_path, start_date="2024-01-01", end_date="2025-12-31")

    train_size = train_env.observation_space.shape[0]
    eval_size  = eval_env.observation_space.shape[0]
    match      = train_size == eval_size

    print(f"Train obs: {train_size} | Eval obs: {eval_size} | Match: {match}")
    assert match, f"MISMATCH: train={train_size} vs eval={eval_size}. FIX BEFORE TRAINING."
    return True


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/kat/kat_v2.db"
    print("Testing feature pipeline...")
    macro, futures, tech = load_features(db_path, "2015-01-01", "2023-12-31")
    print(f"Macro shape:   {macro.shape}")
    print(f"Futures shape: {futures.shape}")
    print(f"Tech shape:    {tech.shape}")
    print(f"Total features (excl. portfolio): {macro.shape[1] + futures.shape[1] + tech.shape[1]}")
    print("Feature pipeline OK ✓")
