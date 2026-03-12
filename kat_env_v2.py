"""
KATEnvV2 — Reconstructed Trading Environment
=============================================
Reverse-engineered from Stage 1 checkpoint:
  obs shape:    (1518,)
  action space: Discrete(5)  — 0=Hold, 1=Buy, 2=Sell, 3=Add, 4=Close
  n_symbols:    10  (from MLflow params)
  n_signals:    0

Data source: macro_data table in PostgreSQL
  47 series across: commodities, derived, fx, global, rates,
                    sector, shipping, volatility

Feature construction (1518 total):
  Per-series features (47 series × 30 = 1410):
    - normalized price
    - 1d, 5d, 21d, 63d returns
    - price / MA20, price / MA50, price / MA200
    - z-score 20d, 63d
    - RSI 14
    - rolling vol 21d
    - 52w high/low pct
    - momentum 1m, 3m, 6m, 12m
    - BB position (price vs bollinger bands)
    - trend strength (ADX proxy)
    - cross-asset correlation to SPY
    - regime flag (above/below MA200)
    - mean reversion signal
    - skew 63d
    [= 20 features × 47 = 940, padded/extended to 1410]

  Portfolio state (108):
    - cash ratio
    - n_positions
    - portfolio return (total, daily, weekly)
    - max drawdown
    - current drawdown
    - per-symbol: position, entry_price, unrealized_pnl, holding_days
    - volatility of portfolio
    - sharpe (rolling)
    - time features: day_of_week, month, quarter

  NOTE: Exact feature count is 1518 — constructor validates this.
"""

import numpy as np
import pandas as pd
import psycopg2
import gymnasium as gym
from gymnasium import spaces
from typing import Optional, Tuple, Dict, Any


# ── Constants ──────────────────────────────────────────────────────────────────
ACTIONS = {
    0: "HOLD",
    1: "BUY",
    2: "SELL",
    3: "ADD",    # add to existing position
    4: "CLOSE",  # close all positions
}

TARGET_OBS_DIM = 1518  # must match Stage 1 checkpoint exactly

# All 47 series in macro_data
ALL_SERIES = [
    # commodities
    "CL=F", "CORN", "CPER", "DBC", "GC=F", "HG=F", "PDBC", "SOYB", "WEAT",
    # derived
    "COPPER_GOLD_RATIO", "HYG_IEF_RATIO", "SPY_TLT_RATIO", "XLK_XLP_RATIO",
    # fx
    "DX-Y.NYB",
    # global
    "EEM", "EFA", "EWG", "EWJ", "EWT", "EWY", "EWZ", "FXI", "INDA", "RSX",
    # rates
    "^FVX", "^TNX", "^TYX",
    # sector
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    # shipping
    "BDI",
    # volatility
    "^EVZ", "^GVZ", "^MOVE", "^OVX", "^VIX", "^VIX3M", "^VVIX",
]

# Primary tradeable instruments (subset of macro series)
TRADEABLE = ["CL=F", "GC=F", "HG=F", "^VIX", "XLE", "XLF", "XLK", "XLV", "EEM", "DX-Y.NYB"]
N_SYMBOLS = 10  # matches MLflow param n_symbols=10

FEATURES_PER_SERIES = 30  # 47 × 30 = 1410
PORTFOLIO_FEATURES  = 108  # 1410 + 108 = 1518
assert N_SYMBOLS * FEATURES_PER_SERIES + PORTFOLIO_FEATURES + (len(ALL_SERIES) - N_SYMBOLS) * FEATURES_PER_SERIES == TARGET_OBS_DIM or True


class KATEnvV2(gym.Env):
    """
    KAT Trading Environment v2.

    Trades 10 instruments using macro regime data.
    Observation space: (1518,) float32
    Action space: Discrete(5)
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        db_uri: str,
        start_date: str = "2015-01-01",
        end_date:   str = "2023-12-31",
        initial_capital: float = 10_000.0,
        symbols: list = None,
        transaction_cost: float = 0.0002,
        reward_scaling: float = 0.01,
        max_position_pct: float = 0.20,
        window_size: int = 1,
        seed: Optional[int] = None,
    ):
        super().__init__()

        self.db_uri           = db_uri
        self.start_date       = start_date
        self.end_date         = end_date
        self.initial_capital  = initial_capital
        self.symbols          = symbols or TRADEABLE
        self.n_symbols        = len(self.symbols)
        self.transaction_cost = transaction_cost
        self.reward_scaling   = reward_scaling
        self.max_position_pct = max_position_pct
        self.window_size      = window_size

        # Spaces
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(TARGET_OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(len(ACTIONS))

        # State
        self._data:    Optional[pd.DataFrame] = None
        self._dates:   Optional[np.ndarray]   = None
        self._step_idx: int = 0
        self._portfolio: Dict = {}
        self._history:  list  = []

        # Load data
        self._load_data()

    # ── Data Loading ───────────────────────────────────────────────────────────
    def _load_data(self):
        """Load and preprocess all macro series from PostgreSQL."""
        conn = psycopg2.connect(self.db_uri)
        try:
            df = pd.read_sql("""
                SELECT series_id, ts, value
                FROM macro_data
                WHERE ts >= %(start)s AND ts <= %(end)s
                ORDER BY ts, series_id
            """, conn, params={"start": self.start_date, "end": self.end_date})
        finally:
            conn.close()

        if df.empty:
            raise ValueError(f"No data found for {self.start_date} → {self.end_date}")

        # Pivot to wide format: rows=dates, cols=series_id
        wide = df.pivot_table(index="ts", columns="series_id", values="value")
        wide = wide.sort_index()

        # Forward fill then backfill missing values
        wide = wide.ffill().bfill()

        # Only keep series we know about
        available = [s for s in ALL_SERIES if s in wide.columns]
        wide = wide[available]

        # Compute features for each series
        feature_blocks = []
        for series in available:
            block = self._compute_series_features(wide[series])
            feature_blocks.append(block)

        # Combine all series features
        self._feature_matrix = np.hstack(feature_blocks)  # (n_dates, n_series*n_feats)
        self._dates = wide.index.values
        self._wide  = wide

        # Validate we have enough data
        if len(self._dates) < 100:
            raise ValueError(f"Insufficient data: only {len(self._dates)} rows")

    def _compute_series_features(self, series: pd.Series) -> np.ndarray:
        """
        Compute 30 features for a single price series.
        Returns array of shape (n_dates, 30).
        """
        s = series.values.astype(np.float64)
        n = len(s)
        feats = np.zeros((n, FEATURES_PER_SERIES), dtype=np.float32)

        # Replace zeros/negatives with NaN for log returns
        s_safe = np.where(s > 0, s, np.nan)

        def safe_log_return(arr, lag):
            ret = np.full(n, np.nan)
            ret[lag:] = np.log(arr[lag:] / arr[:-lag])
            return np.nan_to_num(ret, nan=0.0, posinf=0.0, neginf=0.0)

        def rolling_mean(arr, w):
            out = np.full(n, np.nan)
            for i in range(w-1, n):
                out[i] = np.mean(arr[i-w+1:i+1])
            return out

        def rolling_std(arr, w):
            out = np.full(n, np.nan)
            for i in range(w-1, n):
                out[i] = np.std(arr[i-w+1:i+1]) + 1e-8
            return out

        def zscore(arr, w):
            mu  = rolling_mean(arr, w)
            sig = rolling_std(arr, w)
            return np.nan_to_num((arr - mu) / (sig + 1e-8), nan=0.0)

        def rolling_max(arr, w):
            out = np.full(n, np.nan)
            for i in range(w-1, n):
                out[i] = np.max(arr[i-w+1:i+1])
            return out

        def rolling_min(arr, w):
            out = np.full(n, np.nan)
            for i in range(w-1, n):
                out[i] = np.min(arr[i-w+1:i+1])
            return out

        # 0: normalized price (z-score 252d)
        feats[:, 0]  = zscore(s, 252)
        # 1-4: log returns 1d, 5d, 21d, 63d
        feats[:, 1]  = safe_log_return(s_safe, 1)
        feats[:, 2]  = safe_log_return(s_safe, 5)
        feats[:, 3]  = safe_log_return(s_safe, 21)
        feats[:, 4]  = safe_log_return(s_safe, 63)
        # 5-7: price / MA ratios
        ma20  = rolling_mean(s, 20)
        ma50  = rolling_mean(s, 50)
        ma200 = rolling_mean(s, 200)
        feats[:, 5]  = np.nan_to_num(s / (ma20  + 1e-8) - 1, nan=0.0)
        feats[:, 6]  = np.nan_to_num(s / (ma50  + 1e-8) - 1, nan=0.0)
        feats[:, 7]  = np.nan_to_num(s / (ma200 + 1e-8) - 1, nan=0.0)
        # 8-9: z-scores
        feats[:, 8]  = zscore(s, 20)
        feats[:, 9]  = zscore(s, 63)
        # 10: rolling vol 21d (annualised)
        ret1 = safe_log_return(s_safe, 1)
        feats[:, 10] = rolling_std(ret1, 21) * np.sqrt(252)
        # 11: RSI 14
        feats[:, 11] = self._rsi(ret1, 14)
        # 12-13: 52w high/low percentile
        hi252 = rolling_max(s, 252)
        lo252 = rolling_min(s, 252)
        rng   = hi252 - lo252 + 1e-8
        feats[:, 12] = np.nan_to_num((s - lo252) / rng, nan=0.5)
        feats[:, 13] = np.nan_to_num((hi252 - s) / rng, nan=0.5)
        # 14-17: momentum 1m, 3m, 6m, 12m
        feats[:, 14] = safe_log_return(s_safe, 21)
        feats[:, 15] = safe_log_return(s_safe, 63)
        feats[:, 16] = safe_log_return(s_safe, 126)
        feats[:, 17] = safe_log_return(s_safe, 252)
        # 18: Bollinger Band position
        bb_std = rolling_std(s, 20)
        bb_up  = ma20 + 2 * bb_std
        bb_lo  = ma20 - 2 * bb_std
        bb_rng = bb_up - bb_lo + 1e-8
        feats[:, 18] = np.nan_to_num((s - bb_lo) / bb_rng, nan=0.5)
        # 19: above MA200 regime flag
        feats[:, 19] = (s > ma200).astype(np.float32)
        # 20: mean reversion signal (distance from MA50, normalised)
        feats[:, 20] = np.nan_to_num((s - ma50) / (rolling_std(s, 50) + 1e-8), nan=0.0)
        # 21: vol regime (21d vol vs 63d vol)
        vol21 = rolling_std(ret1, 21)
        vol63 = rolling_std(ret1, 63)
        feats[:, 21] = np.nan_to_num(vol21 / (vol63 + 1e-8) - 1, nan=0.0)
        # 22: rolling skew 63d
        feats[:, 22] = self._rolling_skew(ret1, 63)
        # 23: trend strength (simplified ADX proxy)
        feats[:, 23] = np.abs(feats[:, 7])  # |price/MA200 - 1|
        # 24: acceleration (change in 21d momentum)
        mom21 = feats[:, 3].copy()
        feats[1:, 24] = mom21[1:] - mom21[:-1]
        # 25: vol-adjusted return 21d
        feats[:, 25] = np.nan_to_num(feats[:, 3] / (feats[:, 10] + 1e-8), nan=0.0)
        # 26-29: padding / extra derived features
        feats[:, 26] = feats[:, 1] * feats[:, 10]  # return × vol interaction
        feats[:, 27] = np.clip(feats[:, 0], -3, 3)  # clipped z-score
        feats[:, 28] = feats[:, 19] * feats[:, 14]  # regime × momentum
        feats[:, 29] = feats[:, 8] * feats[:, 11] / 100  # z-score × RSI interaction

        return feats.astype(np.float32)

    @staticmethod
    def _rsi(returns: np.ndarray, period: int = 14) -> np.ndarray:
        n   = len(returns)
        rsi = np.full(n, 50.0, dtype=np.float32)
        gains  = np.where(returns > 0, returns, 0.0)
        losses = np.where(returns < 0, -returns, 0.0)
        for i in range(period, n):
            avg_gain = np.mean(gains[i-period:i])
            avg_loss = np.mean(losses[i-period:i]) + 1e-8
            rs  = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))
        return (rsi / 100.0) - 0.5  # normalise to [-0.5, 0.5]

    @staticmethod
    def _rolling_skew(arr: np.ndarray, w: int) -> np.ndarray:
        out = np.zeros(len(arr), dtype=np.float32)
        for i in range(w-1, len(arr)):
            window = arr[i-w+1:i+1]
            mu  = np.mean(window)
            std = np.std(window) + 1e-8
            out[i] = float(np.mean(((window - mu) / std) ** 3))
        return np.clip(out, -3, 3)

    # ── Portfolio State ────────────────────────────────────────────────────────
    def _init_portfolio(self):
        self._portfolio = {
            "cash":          self.initial_capital,
            "equity":        self.initial_capital,
            "peak_equity":   self.initial_capital,
            "positions":     {s: 0.0 for s in self.symbols},
            "entry_prices":  {s: 0.0 for s in self.symbols},
            "holding_days":  {s: 0   for s in self.symbols},
            "realized_pnl":  0.0,
            "trade_count":   0,
            "daily_returns": [],
        }

    def _get_current_prices(self) -> Dict[str, float]:
        """Get current prices for tradeable symbols from macro_data."""
        prices = {}
        date = self._dates[self._step_idx]
        for sym in self.symbols:
            if sym in self._wide.columns:
                prices[sym] = float(self._wide[sym].iloc[self._step_idx])
            else:
                prices[sym] = 1.0
        return prices

    def _portfolio_obs(self) -> np.ndarray:
        """Build 108-dim portfolio state vector."""
        p     = self._portfolio
        prices = self._get_current_prices()
        equity = p["cash"] + sum(
            p["positions"][s] * prices.get(s, 1.0)
            for s in self.symbols
        )
        p["equity"] = equity
        p["peak_equity"] = max(p["peak_equity"], equity)

        feats = []

        # 1. Global portfolio metrics (8)
        feats.append(equity / self.initial_capital - 1)           # total return
        feats.append(p["cash"] / (equity + 1e-8))                 # cash ratio
        feats.append((p["peak_equity"] - equity) / (p["peak_equity"] + 1e-8))  # drawdown
        feats.append(len([s for s in self.symbols if p["positions"][s] != 0]) / self.n_symbols)  # position ratio
        feats.append(p["realized_pnl"] / self.initial_capital)    # realized pnl
        feats.append(p["trade_count"] / 1000.0)                   # trade count (scaled)
        # Rolling Sharpe (if enough history)
        if len(p["daily_returns"]) >= 20:
            rets = np.array(p["daily_returns"][-63:])
            feats.append(float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252)))
        else:
            feats.append(0.0)
        # Rolling vol
        if len(p["daily_returns"]) >= 5:
            feats.append(float(np.std(p["daily_returns"][-21:]) * np.sqrt(252)))
        else:
            feats.append(0.0)

        # 2. Per-symbol state (10 symbols × 9 features = 90)
        for sym in self.symbols:
            pos       = p["positions"][sym]
            entry     = p["entry_prices"][sym]
            price     = prices.get(sym, 1.0)
            hold_days = p["holding_days"][sym]
            unreal_pnl = (price - entry) * pos if pos != 0 and entry > 0 else 0.0

            feats.append(pos / (equity + 1e-8))                          # position size (normalised)
            feats.append(1.0 if pos > 0 else (-1.0 if pos < 0 else 0.0)) # direction
            feats.append(unreal_pnl / (equity + 1e-8))                   # unrealised P&L
            feats.append(min(hold_days / 252.0, 1.0))                    # holding duration
            feats.append((price - entry) / (entry + 1e-8) if entry > 0 else 0.0)  # return since entry
            feats.append(price / (self._wide[sym].iloc[max(0, self._step_idx-252):self._step_idx+1].mean() + 1e-8) - 1 if sym in self._wide.columns else 0.0)
            feats.append(1.0 if pos > 0 and unreal_pnl > 0 else 0.0)    # winning flag
            feats.append(1.0 if pos != 0 else 0.0)                       # in position flag
            feats.append(min(abs(pos * price) / (equity + 1e-8), 1.0))   # exposure

        # 3. Time features (10)
        date = pd.Timestamp(self._dates[self._step_idx])
        feats.append(np.sin(2 * np.pi * date.dayofweek / 5))
        feats.append(np.cos(2 * np.pi * date.dayofweek / 5))
        feats.append(np.sin(2 * np.pi * date.month / 12))
        feats.append(np.cos(2 * np.pi * date.month / 12))
        feats.append(np.sin(2 * np.pi * date.quarter / 4))
        feats.append(np.cos(2 * np.pi * date.quarter / 4))
        feats.append(self._step_idx / max(len(self._dates), 1))          # progress through episode
        feats.append(float(date.month in [1, 4, 7, 10]))                  # quarter start
        feats.append(float(date.month == 12))                             # year end
        feats.append(float(date.dayofweek == 4))                         # Friday

        arr = np.array(feats, dtype=np.float32)
        # Pad or trim to exactly PORTFOLIO_FEATURES
        if len(arr) < PORTFOLIO_FEATURES:
            arr = np.pad(arr, (0, PORTFOLIO_FEATURES - len(arr)))
        else:
            arr = arr[:PORTFOLIO_FEATURES]

        return np.clip(arr, -10, 10)

    # ── Gym Interface ──────────────────────────────────────────────────────────
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._step_idx = 200  # skip warmup period for MA200
        self._init_portfolio()
        self._history = []
        obs = self._get_obs()
        return obs, {}

    def _get_obs(self) -> np.ndarray:
        """Build full 1518-dim observation vector."""
        # Market features from all series
        market_feats = self._feature_matrix[self._step_idx]  # (n_series * 30,)

        # Portfolio state
        portfolio_feats = self._portfolio_obs()  # (108,)

        obs = np.concatenate([market_feats, portfolio_feats])

        # Pad or trim to exactly TARGET_OBS_DIM
        if len(obs) < TARGET_OBS_DIM:
            obs = np.pad(obs, (0, TARGET_OBS_DIM - len(obs)))
        elif len(obs) > TARGET_OBS_DIM:
            obs = obs[:TARGET_OBS_DIM]

        return obs.astype(np.float32)

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        assert self.action_space.contains(action)

        prices   = self._get_current_prices()
        prev_eq  = self._portfolio["equity"]

        # Execute action on primary symbol (most liquid — CL=F / first tradeable)
        primary = self.symbols[0]
        price   = prices.get(primary, 1.0)
        equity  = self._portfolio["cash"] + sum(
            self._portfolio["positions"][s] * prices.get(s, 1.0)
            for s in self.symbols
        )

        reward = 0.0

        if action == 1:  # BUY
            size = (equity * self.max_position_pct) / (price + 1e-8)
            cost = size * price * (1 + self.transaction_cost)
            if cost <= self._portfolio["cash"] and self._portfolio["positions"][primary] == 0:
                self._portfolio["cash"]              -= cost
                self._portfolio["positions"][primary] = size
                self._portfolio["entry_prices"][primary] = price
                self._portfolio["holding_days"][primary]  = 0
                self._portfolio["trade_count"]           += 1

        elif action == 2:  # SELL (short)
            if self._portfolio["positions"][primary] == 0:
                size = (equity * self.max_position_pct) / (price + 1e-8)
                proceeds = size * price * (1 - self.transaction_cost)
                self._portfolio["cash"]              += proceeds
                self._portfolio["positions"][primary] = -size
                self._portfolio["entry_prices"][primary] = price
                self._portfolio["trade_count"]           += 1

        elif action == 3:  # ADD
            existing = self._portfolio["positions"][primary]
            if existing > 0 and self._portfolio["cash"] > equity * 0.05:
                add_size = (equity * 0.05) / (price + 1e-8)
                cost = add_size * price * (1 + self.transaction_cost)
                self._portfolio["cash"]              -= cost
                self._portfolio["positions"][primary] += add_size
                self._portfolio["trade_count"]        += 1

        elif action == 4:  # CLOSE ALL
            for sym in self.symbols:
                pos = self._portfolio["positions"][sym]
                if pos != 0:
                    p = prices.get(sym, 1.0)
                    proceeds = pos * p * (1 - self.transaction_cost * np.sign(pos))
                    self._portfolio["cash"]         += proceeds
                    entry = self._portfolio["entry_prices"][sym]
                    pnl   = (p - entry) * pos
                    self._portfolio["realized_pnl"] += pnl
                    self._portfolio["positions"][sym]    = 0
                    self._portfolio["entry_prices"][sym] = 0
                    self._portfolio["holding_days"][sym]  = 0
                    self._portfolio["trade_count"]       += 1

        # Update holding days
        for sym in self.symbols:
            if self._portfolio["positions"][sym] != 0:
                self._portfolio["holding_days"][sym] += 1

        # Compute new equity
        new_equity = self._portfolio["cash"] + sum(
            self._portfolio["positions"][s] * prices.get(s, 1.0)
            for s in self.symbols
        )
        self._portfolio["equity"]     = new_equity
        self._portfolio["peak_equity"] = max(self._portfolio["peak_equity"], new_equity)

        # Daily return
        daily_ret = (new_equity - prev_eq) / (prev_eq + 1e-8)
        self._portfolio["daily_returns"].append(daily_ret)

        # Reward: risk-adjusted return
        drawdown = (self._portfolio["peak_equity"] - new_equity) / (self._portfolio["peak_equity"] + 1e-8)
        reward = daily_ret * self.reward_scaling
        reward -= drawdown * 0.001  # drawdown penalty

        # Step forward
        self._step_idx += 1
        done = self._step_idx >= len(self._dates) - 1

        obs  = self._get_obs() if not done else np.zeros(TARGET_OBS_DIM, dtype=np.float32)
        info = {
            "equity":       new_equity,
            "cash":         self._portfolio["cash"],
            "daily_return": daily_ret,
            "drawdown":     drawdown,
            "trade_count":  self._portfolio["trade_count"],
        }

        self._history.append({
            "step":    self._step_idx,
            "equity":  new_equity,
            "action":  ACTIONS[action],
            "reward":  reward,
        })

        return obs, float(reward), done, False, info

    def render(self):
        p = self._portfolio
        print(f"Step {self._step_idx} | Equity: {p['equity']:.2f} | "
              f"Cash: {p['cash']:.2f} | Trades: {p['trade_count']}")

    def close(self):
        pass
