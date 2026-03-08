"""
KAT Data Ingestion Pipeline
============================
Downloads and normalizes historical data from all subscribed sources.
This is the fuel for offline pre-training the RL agent.

SOURCES:
  1. Polygon.io          — OHLCV for all US equities/ETFs/options (primary)
  2. Collective2 API     — Historical strategy signals (audited win rates)
  3. Holly AI / Trade Ideas — Daily signal logs (paid subscription)
  4. TradersPost         — Pine Script backtest exports
  5. IBKR Historical     — Direct from IBKR TWS API (free with account)

PIPELINE:
  Raw download → Normalize → Add indicators → Align signals → Save parquet
  
  The output is a DatasetBundle consumed by the trainer.
"""

import os
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import httpx
import time

logger = logging.getLogger("kat.data")

DATA_DIR = Path(os.getenv("KAT_DATA_DIR", "/data/kat"))
POLYGON_KEY = os.getenv("POLYGON_API_KEY", "")
C2_KEY = os.getenv("COLLECTIVE2_API_KEY", "")


# ─── Polygon.io Downloader ────────────────────────────────────────────────────

class PolygonDownloader:
    """
    Download OHLCV + options data from Polygon.io.
    Stocks + Options plan: $199/mo — covers everything we need.
    """

    BASE = "https://api.polygon.io"

    def __init__(self, api_key: str = POLYGON_KEY):
        self.api_key = api_key
        self.client = httpx.Client(timeout=30)

    def get_bars(
        self,
        ticker: str,
        from_date: str,        # "2020-01-01"
        to_date: str,          # "2025-12-31"
        timespan: str = "day", # "minute", "hour", "day", "week"
        multiplier: int = 1,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars. Auto-paginates."""
        url = f"{self.BASE}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        results = []
        params = {
            "apiKey": self.api_key,
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
        }

        while url:
            resp = self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("resultsCount", 0) == 0:
                break

            results.extend(data.get("results", []))
            url = data.get("next_url")  # Polygon auto-paginates via next_url
            params = {"apiKey": self.api_key}  # next_url has params built in
            time.sleep(0.1)  # rate limit: 5 calls/min on free, unlimited on paid

        if not results:
            logger.warning(f"No data returned for {ticker}")
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True)
        df = df.set_index("timestamp").rename(columns={
            "o": "open", "h": "high", "l": "low",
            "c": "close", "v": "volume", "vw": "vwap",
            "n": "n_trades",
        })
        df = df[["open", "high", "low", "close", "volume", "vwap", "n_trades"]]
        logger.info(f"Downloaded {len(df)} bars for {ticker} ({timespan})")
        return df

    def get_batch(self, tickers: List[str], **kwargs) -> Dict[str, pd.DataFrame]:
        """Download multiple tickers."""
        data = {}
        for ticker in tickers:
            try:
                df = self.get_bars(ticker, **kwargs)
                if not df.empty:
                    data[ticker] = df
            except Exception as e:
                logger.error(f"Failed to download {ticker}: {e}")
        return data

    def get_options_chain(self, underlying: str, expiration_date: str) -> pd.DataFrame:
        """Fetch options chain snapshot for a given expiry."""
        url = f"{self.BASE}/v3/snapshot/options/{underlying}"
        params = {
            "apiKey": self.api_key,
            "expiration_date": expiration_date,
            "limit": 250,
        }
        resp = self.client.get(url, params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return pd.DataFrame([r.get("details", {}) | r.get("greeks", {}) for r in results])


# ─── Collective2 Historical Signal Downloader ─────────────────────────────────

class Collective2Downloader:
    """
    Pull historical trade signals from subscribed C2 strategies.
    These are AUDITED signals with real fill prices — perfect training data.
    
    Each C2 strategy provides:
      - Entry signal (buy/sell/short/cover)
      - Symbol, quantity, price
      - Timestamp
      - P&L on close
    
    We use this as LABELED training data: the signal is the label,
    the market state at signal time is the input.
    """

    BASE = "https://api.collective2.com/world/apiv3"

    def __init__(self, api_key: str = C2_KEY):
        self.api_key = api_key
        self.client = httpx.Client(timeout=30)

    def get_strategy_trades(self, system_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Pull all historical trades for a C2 strategy system.
        system_id: e.g. "94679653" — get this from C2 marketplace.
        """
        resp = self.client.post(
            f"{self.BASE}/requestTrades",
            json={
                "apikey": self.api_key,
                "systemid": system_id,
                "tradelist": "closed",
            }
        )
        resp.raise_for_status()
        trades = resp.json().get("response", {}).get("tradelist", {}).get("trade", [])
        if not trades:
            return pd.DataFrame()

        df = pd.DataFrame(trades)
        df["entry_time"] = pd.to_datetime(df.get("opentime", pd.Series()))
        df["exit_time"] = pd.to_datetime(df.get("closetime", pd.Series()))
        df["pnl"] = pd.to_numeric(df.get("pnl", 0), errors="coerce")
        df["symbol"] = df.get("symbol", "")
        df["action"] = df.get("action", "")
        df["source"] = "collective2"
        df["source_strategy_id"] = system_id

        mask = (df["entry_time"] >= start_date) & (df["entry_time"] <= end_date)
        return df[mask].reset_index(drop=True)

    def get_all_subscribed_trades(self, system_ids: List[str], **kwargs) -> pd.DataFrame:
        """Merge trades from all subscribed strategies."""
        frames = []
        for sid in system_ids:
            try:
                df = self.get_strategy_trades(sid, **kwargs)
                frames.append(df)
                logger.info(f"C2 strategy {sid}: {len(df)} historical trades")
            except Exception as e:
                logger.error(f"C2 strategy {sid} failed: {e}")
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ─── Holly AI Signal Log Parser ───────────────────────────────────────────────

class HollyAIParser:
    """
    Parse historical Holly AI signal logs.
    Trade Ideas sends daily recaps — we archive them to build training data.
    
    The key insight: Holly retrained daily on ALL US stocks.
    If we archive 6-12 months of Holly signals + market outcomes,
    we have ~1500-3000 labeled signal examples.
    """

    def parse_signal_log(self, log_path: str) -> pd.DataFrame:
        """Parse a JSON log of Holly AI signals (from our webhook archive)."""
        import json
        signals = []
        with open(log_path) as f:
            for line in f:
                try:
                    sig = json.loads(line.strip())
                    signals.append({
                        "timestamp": pd.to_datetime(sig.get("timestamp")),
                        "symbol": sig.get("symbol", ""),
                        "action": sig.get("action", "buy"),
                        "confidence": sig.get("confidence", 0.0),
                        "strategy_name": sig.get("strategy_name", "holly"),
                        "entry_price": sig.get("price", 0.0),
                        "stop_loss": sig.get("stop", 0.0),
                        "source": "holly_ai",
                    })
                except Exception:
                    continue

        df = pd.DataFrame(signals).set_index("timestamp")
        logger.info(f"Parsed {len(df)} Holly AI signals from {log_path}")
        return df

    def synthesize_from_api(self, api_key: str, lookback_days: int = 180) -> pd.DataFrame:
        """
        If we have Trade Ideas API access, pull historical signal performance.
        This is the premium feature — gives us bulk labeled data immediately.
        """
        # Implementation depends on Trade Ideas API v2
        # https://www.trade-ideas.com/developers/
        logger.info(f"Fetching {lookback_days} days of Holly AI history...")
        # TODO: Implement Trade Ideas API call
        return pd.DataFrame()


# ─── Dataset Builder ─────────────────────────────────────────────────────────

class DatasetBuilder:
    """
    Combines price data + external signals into training datasets.
    
    Output: DatasetBundle ready for the trainer.
    """

    TRAINING_SYMBOLS = [
        # High-liquidity US equities — where signals cluster
        "SPY", "QQQ", "IWM",           # Index ETFs
        "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN",  # Mega caps
        "TSLA", "AMD", "NFLX",          # High-vol favorites
        "GLD", "SLV", "USO",            # Commodities
        "TLT", "HYG",                   # Bonds
        # Add more based on which C2 strategies we subscribe to
    ]

    def __init__(
        self,
        polygon_key: str = POLYGON_KEY,
        c2_key: str = C2_KEY,
        output_dir: Path = DATA_DIR / "processed",
    ):
        self.polygon = PolygonDownloader(polygon_key)
        self.c2 = Collective2Downloader(c2_key)
        self.holly = HollyAIParser()
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_price_dataset(
        self,
        symbols: Optional[List[str]] = None,
        from_date: str = "2018-01-01",
        to_date: str = "2025-12-31",
        timespan: str = "day",
    ) -> Dict[str, pd.DataFrame]:
        """Download and save price data for all training symbols."""
        symbols = symbols or self.TRAINING_SYMBOLS
        logger.info(f"Building price dataset: {len(symbols)} symbols, {from_date} → {to_date}")

        price_data = {}
        for symbol in symbols:
            cache_path = self.output_dir / f"{symbol}_{timespan}_{from_date}_{to_date}.parquet"

            if cache_path.exists():
                df = pd.read_parquet(cache_path)
                logger.info(f"Loaded {symbol} from cache ({len(df)} bars)")
            else:
                df = self.polygon.get_bars(symbol, from_date, to_date, timespan)
                if not df.empty:
                    df.to_parquet(cache_path)

            if not df.empty:
                price_data[symbol] = df

        logger.info(f"Price dataset complete: {len(price_data)} symbols")
        return price_data

    def build_signal_dataset(
        self,
        c2_strategy_ids: List[str],
        holly_log_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """Build unified signal dataset from all sources."""
        frames = []

        # Collective2 historical signals
        if c2_strategy_ids:
            c2_df = self.c2.get_all_subscribed_trades(
                c2_strategy_ids,
                start_date="2018-01-01",
                end_date="2025-12-31",
            )
            if not c2_df.empty:
                frames.append(c2_df)

        # Holly AI logs
        if holly_log_dir:
            for log_file in Path(holly_log_dir).glob("*.jsonl"):
                holly_df = self.holly.parse_signal_log(str(log_file))
                if not holly_df.empty:
                    frames.append(holly_df.reset_index())

        if not frames:
            logger.warning("No signal data available — training without signal features")
            return pd.DataFrame()

        signals = pd.concat(frames, ignore_index=True)
        signals = signals.sort_values("timestamp").reset_index(drop=True)
        logger.info(f"Signal dataset: {len(signals)} total signals from {signals['source'].nunique()} sources")
        return signals

    def build_training_bundle(
        self,
        c2_strategy_ids: List[str] = None,
        symbols: Optional[List[str]] = None,
        from_date: str = "2020-01-01",
        to_date: str = "2025-12-31",
    ) -> "DatasetBundle":
        """Full pipeline: prices + signals → training bundle."""
        price_data = self.build_price_dataset(symbols, from_date, to_date)
        signal_data = self.build_signal_dataset(c2_strategy_ids or [], holly_log_dir=None)
        return DatasetBundle(price_data=price_data, signal_data=signal_data)


class DatasetBundle:
    """Holds all training data. Passed to the KATTrainer."""

    def __init__(
        self,
        price_data: Dict[str, pd.DataFrame],
        signal_data: pd.DataFrame,
    ):
        self.price_data = price_data
        self.signal_data = signal_data

    @property
    def n_symbols(self) -> int:
        return len(self.price_data)

    @property
    def n_signals(self) -> int:
        return len(self.signal_data)

    def get_signal_df_for_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get signals for a specific symbol, aligned to its price index."""
        if self.signal_data.empty:
            return None
        mask = self.signal_data.get("symbol", pd.Series()) == symbol
        sig = self.signal_data[mask].copy()
        if sig.empty:
            return None
        sig = sig.set_index("timestamp").sort_index()
        return sig

    def __repr__(self):
        return (
            f"DatasetBundle("
            f"symbols={self.n_symbols}, "
            f"signals={self.n_signals})"
        )


class DataPipeline:
    """Unified pipeline wrapper — fetches price data and builds training datasets."""

    def __init__(self):
        import os
        self.polygon_key = os.environ.get('POLYGON_API_KEY', '')
        self.db_url = os.environ.get('DATABASE_URL', '')
        self.downloader = PolygonDownloader(api_key=self.polygon_key)
        self.builder = DatasetBuilder(db_url=self.db_url)

    def fetch_bars(self, symbol: str, start: str, end: str, timespan: str = 'day'):
        """Fetch OHLCV bars for a symbol and store in DB."""
        return self.downloader.fetch(symbol=symbol, start=start, end=end, timespan=timespan)

    def build_dataset(self, symbols: list, start: str, end: str):
        """Build a training DatasetBundle for the given symbols and date range."""
        return self.builder.build(symbols=symbols, start=start, end=end)

    def status(self):
        """Quick connectivity check."""
        import urllib.request, json as _json
        url = f'https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/2025-01-02/2025-01-03?apiKey={self.polygon_key}'
        try:
            r = urllib.request.urlopen(url, timeout=5)
            d = _json.loads(r.read())
            return f"Polygon OK — {d.get('status', '?')} | DB: {self.db_url[:30]}..."
        except Exception as e:
            return f"Polygon ERROR: {e}"
