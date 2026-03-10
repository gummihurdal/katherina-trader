"""
KAT Trading Environment
=======================
OpenAI Gym-compatible environment for training the RL agent.

STATE SPACE (per step):
  Market features:   OHLCV + 20 technical indicators (60-bar lookback)
  Portfolio state:   cash %, position size, unrealized P&L, drawdown
  Signal features:   incoming signal confidence, source, action
  Time features:     hour of day, day of week, days to expiry (options)

ACTION SPACE (discrete):
  0 = HOLD / do nothing
  1 = BUY  (size determined by position sizer)
  2 = SELL / close position
  3 = BUY  (half size)
  4 = SELL (half size — partial close)

REWARD:
  Sharpe-adjusted step return with drawdown penalty and transaction cost.
  Goal: maximize risk-adjusted return, not raw P&L.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict, Any
import gymnasium as gym
from gymnasium import spaces
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger("kat.env")

# ─── Constants ─────────────────────────────────────────────────────────────────

LOOKBACK = 60          # bars of history in state
N_MARKET_FEATURES = 25 # OHLCV + indicators per bar
N_PORTFOLIO_FEATURES = 8
N_SIGNAL_FEATURES = 6
N_TIME_FEATURES = 4

STATE_DIM = LOOKBACK * N_MARKET_FEATURES + N_PORTFOLIO_FEATURES + N_SIGNAL_FEATURES + N_TIME_FEATURES
ACTION_DIM = 5

TRANSACTION_COST = 0.001   # 0.1% per trade (commissions + slippage)
MAX_POSITION_PCT = 0.20    # Max 20% of capital in one position
INITIAL_CAPITAL = 100_000  # Paper account starting capital


# ─── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0

    def update_pnl(self, current_price: float):
        self.unrealized_pnl = (current_price - self.entry_price) * self.quantity

    @property
    def current_value(self) -> float:
        return self.entry_price * self.quantity + self.unrealized_pnl


@dataclass
class TradeRecord:
    symbol: str
    action: str
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    hold_bars: int
    entry_time: datetime
    exit_time: datetime
    signal_source: str = ""
    signal_confidence: float = 0.0


# ─── Core Environment ──────────────────────────────────────────────────────────

class KATTradingEnv(gym.Env):
    """
    Single-symbol trading environment.
    Instantiate one per symbol during training. Vectorize with SubprocVecEnv.
    """

    metadata = {"render_modes": ["human", "ansi"]}

    def __init__(
        self,
        price_data: pd.DataFrame,       # OHLCV + indicators, DatetimeIndex
        signal_data: Optional[pd.DataFrame] = None,  # External signals aligned to price_data index
        initial_capital: float = INITIAL_CAPITAL,
        max_position_pct: float = MAX_POSITION_PCT,
        transaction_cost: float = TRANSACTION_COST,
        reward_scaling: float = 1.0,
        use_sharpe_reward: bool = True,
        render_mode: Optional[str] = None,
    ):
        super().__init__()

        self.price_data = price_data.copy()
        self.signal_data = signal_data
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.transaction_cost = transaction_cost
        self.reward_scaling = reward_scaling
        self.use_sharpe_reward = use_sharpe_reward
        self.render_mode = render_mode

        self._validate_data()
        self._build_feature_columns()

        # Spaces
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(STATE_DIM,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(ACTION_DIM)

        # State
        self._reset_state()

    # ─── Setup ────────────────────────────────────────────────────────────────

    def _validate_data(self):
        required = ["open", "high", "low", "close", "volume"]
        cols = [c.lower() for c in self.price_data.columns]
        missing = [c for c in required if c not in cols]
        if missing:
            raise ValueError(f"price_data missing columns: {missing}")
        self.price_data.columns = [c.lower() for c in self.price_data.columns]

    def _build_feature_columns(self):
        """Pre-compute all technical indicators."""
        df = self.price_data

        # Price transforms
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["hl_ratio"] = (df["high"] - df["low"]) / df["close"]
        df["co_ratio"] = (df["close"] - df["open"]) / df["open"]

        # Moving averages
        for n in [5, 10, 20, 50]:
            df[f"sma_{n}"] = df["close"].rolling(n).mean() / df["close"] - 1
            df[f"ema_{n}"] = df["close"].ewm(span=n).mean() / df["close"] - 1

        # Volatility
        df["atr_14"] = self._atr(df, 14) / df["close"]
        df["vol_20"] = df["log_return"].rolling(20).std()

        # Momentum
        df["rsi_14"] = self._rsi(df["close"], 14)
        df["rsi_6"] = self._rsi(df["close"], 6)
        macd_line, signal_line = self._macd(df["close"])
        df["macd"] = macd_line / df["close"]
        df["macd_signal"] = signal_line / df["close"]

        # Volume
        df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

        # Bollinger
        bb_mid = df["close"].rolling(20).mean()
        bb_std = df["close"].rolling(20).std()
        df["bb_upper_dist"] = (bb_mid + 2 * bb_std - df["close"]) / df["close"]
        df["bb_lower_dist"] = (df["close"] - (bb_mid - 2 * bb_std)) / df["close"]
        df["bb_width"] = (4 * bb_std) / bb_mid

        self.price_data = df.fillna(0)

        # Feature column names (in order)
        self.market_cols = [
            "log_return", "hl_ratio", "co_ratio",
            "sma_5", "sma_10", "sma_20", "sma_50",
            "ema_5", "ema_10", "ema_20", "ema_50",
            "atr_14", "vol_20",
            "rsi_14", "rsi_6",
            "macd", "macd_signal",
            "vol_ratio",
            "bb_upper_dist", "bb_lower_dist", "bb_width",
            "open", "high", "low", "close",  # normalized in observation
        ]
        assert len(self.market_cols) == N_MARKET_FEATURES, \
            f"Expected {N_MARKET_FEATURES} cols, got {len(self.market_cols)}"

    def _reset_state(self):
        self.current_step = LOOKBACK
        self.capital = self.initial_capital
        self.position: Optional[Position] = None
        self.trade_history: list[TradeRecord] = []
        self.portfolio_values = [self.initial_capital]
        self.returns = []
        self.peak_value = self.initial_capital

    # ─── Core Gym Interface ────────────────────────────────────────────────────

    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        super().reset(seed=seed)
        self._reset_state()
        obs = self._get_observation()
        info = self._get_info()
        return obs, info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        assert self.action_space.contains(action), f"Invalid action: {action}"

        current_price = self._current_price()
        reward = 0.0
        trade_executed = False

        # ── Execute action ──────────────────────────────────────────────────────
        if action == 1 and self.position is None:  # BUY full
            reward += self._open_position(current_price, size_pct=self.max_position_pct)
            trade_executed = True

        elif action == 3 and self.position is None:  # BUY half
            reward += self._open_position(current_price, size_pct=self.max_position_pct / 2)
            trade_executed = True

        elif action == 2 and self.position is not None:  # SELL all
            reward += self._close_position(current_price)
            trade_executed = True

        elif action == 4 and self.position is not None:  # SELL half
            reward += self._partial_close(current_price, fraction=0.5)
            trade_executed = True

        # action == 0: HOLD — no trade

        # ── Update position P&L ─────────────────────────────────────────────────
        if self.position is not None:
            self.position.update_pnl(current_price)
            # Check stop-loss / take-profit
            reward += self._check_risk_exits(current_price)

        # ── Step forward ───────────────────────────────────────────────────────
        self.current_step += 1

        # ── Portfolio tracking ─────────────────────────────────────────────────
        portfolio_value = self._portfolio_value(current_price)
        self.portfolio_values.append(portfolio_value)
        step_return = (portfolio_value - self.portfolio_values[-2]) / self.portfolio_values[-2]
        self.returns.append(step_return)

        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value

        # ── Reward ─────────────────────────────────────────────────────────────
        if self.use_sharpe_reward:
            reward += self._sharpe_reward(step_return)
        else:
            reward += step_return * 100  # simple scaled return

        # Drawdown penalty
        drawdown = (self.peak_value - portfolio_value) / self.peak_value
        if drawdown > 0.05:
            reward -= drawdown * 10

        reward *= self.reward_scaling

        # ── Terminal conditions ────────────────────────────────────────────────
        terminated = (
            self.current_step >= len(self.price_data) - 1
            or portfolio_value < self.initial_capital * 0.50  # blown out
        )
        truncated = False

        obs = self._get_observation()
        info = self._get_info()
        info["trade_executed"] = trade_executed

        return obs, reward, terminated, truncated, info

    # ─── Observations ──────────────────────────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        # 1. Market features: LOOKBACK bars × N_MARKET_FEATURES
        window = self.price_data.iloc[self.current_step - LOOKBACK : self.current_step]
        market_array = window[self.market_cols].values.astype(np.float32)

        # Normalize price cols by last close
        last_close = window["close"].iloc[-1]
        if last_close > 0:
            for i, col in enumerate(self.market_cols):
                if col in ["open", "high", "low", "close"]:
                    market_array[:, i] = market_array[:, i] / last_close - 1

        market_flat = market_array.flatten()  # LOOKBACK * N_MARKET_FEATURES

        # 2. Portfolio state
        current_price = self._current_price()
        portfolio_value = self._portfolio_value(current_price)
        cash_pct = self.capital / portfolio_value if portfolio_value > 0 else 1.0
        position_size = 0.0
        unrealized_pnl_pct = 0.0
        entry_price_norm = 0.0
        bars_held = 0.0

        if self.position is not None:
            self.position.update_pnl(current_price)
            position_size = (self.position.current_value / portfolio_value) if portfolio_value > 0 else 0
            unrealized_pnl_pct = self.position.unrealized_pnl / (self.position.entry_price * self.position.quantity + 1e-8)
            entry_price_norm = (current_price - self.position.entry_price) / (self.position.entry_price + 1e-8)
            bars_held = (self.current_step - self._position_open_step) / 100.0

        drawdown = (self.peak_value - portfolio_value) / (self.peak_value + 1e-8)
        total_return = (portfolio_value - self.initial_capital) / self.initial_capital

        portfolio_state = np.array([
            cash_pct,
            position_size,
            unrealized_pnl_pct,
            entry_price_norm,
            bars_held,
            drawdown,
            total_return,
            len(self.trade_history) / 100.0,  # normalized trade count
        ], dtype=np.float32)

        # 3. Signal features (external signal at this bar, if any)
        signal_state = self._get_signal_features()

        # 4. Time features
        ts = self.price_data.index[self.current_step]
        if hasattr(ts, 'hour'):
            time_state = np.array([
                np.sin(2 * np.pi * ts.hour / 24),
                np.cos(2 * np.pi * ts.hour / 24),
                np.sin(2 * np.pi * ts.dayofweek / 5),
                np.cos(2 * np.pi * ts.dayofweek / 5),
            ], dtype=np.float32)
        else:
            time_state = np.zeros(N_TIME_FEATURES, dtype=np.float32)

        return np.concatenate([market_flat, portfolio_state, signal_state, time_state])

    def _get_signal_features(self) -> np.ndarray:
        """Extract signal features at current bar."""
        features = np.zeros(N_SIGNAL_FEATURES, dtype=np.float32)
        if self.signal_data is None:
            return features

        idx = self.price_data.index[self.current_step]
        if idx not in self.signal_data.index:
            return features

        sig = self.signal_data.loc[idx]
        # [has_signal, action_buy, action_sell, confidence, source_encoded, urgency]
        features[0] = 1.0  # has signal
        features[1] = 1.0 if sig.get("action") == "buy" else 0.0
        features[2] = 1.0 if sig.get("action") == "sell" else 0.0
        features[3] = float(sig.get("confidence", 0.0))
        source_map = {"collective2": 0.2, "holly_ai": 0.4, "traderspost": 0.6, "internal": 0.8}
        features[4] = source_map.get(sig.get("source", ""), 0.0)
        features[5] = 1.0 if sig.get("urgency") == "immediate" else 0.5

        return features

    # ─── Trade Execution ───────────────────────────────────────────────────────

    def _open_position(self, price: float, size_pct: float) -> float:
        max_value = self.capital * size_pct
        quantity = int(max_value / price)
        if quantity <= 0:
            return -0.01  # tiny penalty for trying to trade with no capital

        cost = quantity * price * (1 + self.transaction_cost)
        if cost > self.capital:
            quantity = int(self.capital / (price * (1 + self.transaction_cost)))
            cost = quantity * price * (1 + self.transaction_cost)

        if quantity <= 0:
            return -0.01

        self.capital -= cost
        self._position_open_step = self.current_step
        self.position = Position(
            symbol=self._symbol,
            quantity=quantity,
            entry_price=price,
            entry_time=self.price_data.index[self.current_step],
            stop_loss=price * 0.95,   # default 5% stop
            take_profit=price * 1.15, # default 15% take profit
        )
        return -self.transaction_cost  # immediate cost as negative reward

    def _close_position(self, price: float, fraction: float = 1.0) -> float:
        if self.position is None:
            return 0.0

        close_qty = int(self.position.quantity * fraction)
        if close_qty == 0:
            close_qty = self.position.quantity

        proceeds = close_qty * price * (1 - self.transaction_cost)
        cost_basis = close_qty * self.position.entry_price
        pnl = proceeds - cost_basis
        pnl_pct = pnl / cost_basis if cost_basis != 0 else 0.0

        self.capital += proceeds
        hold_bars = self.current_step - self._position_open_step

        self.trade_history.append(TradeRecord(
            symbol=self.position.symbol,
            action="sell",
            quantity=close_qty,
            entry_price=self.position.entry_price,
            exit_price=price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_bars=hold_bars,
            entry_time=self.position.entry_time,
            exit_time=self.price_data.index[self.current_step],
        ))

        if fraction >= 1.0:
            self.position = None
        else:
            self.position.quantity -= close_qty

        return pnl_pct * 10  # scale P&L into reward

    def _partial_close(self, price: float, fraction: float = 0.5) -> float:
        return self._close_position(price, fraction=fraction)

    def _check_risk_exits(self, price: float) -> float:
        if self.position is None:
            return 0.0

        # Stop loss hit
        if self.position.stop_loss and price <= self.position.stop_loss:
            logger.debug(f"Stop loss triggered at {price:.2f}")
            return self._close_position(price)

        # Take profit hit
        if self.position.take_profit and price >= self.position.take_profit:
            logger.debug(f"Take profit triggered at {price:.2f}")
            return self._close_position(price)

        return 0.0

    # ─── Reward Engineering ────────────────────────────────────────────────────

    def _sharpe_reward(self, step_return: float) -> float:
        """Rolling Sharpe as reward signal — punishes volatility."""
        if len(self.returns) < 20:
            return step_return * 100

        recent = np.array(self.returns[-20:])
        mean_r = np.mean(recent)
        std_r = np.std(recent) + 1e-8
        sharpe = (mean_r / std_r) * np.sqrt(252)
        return sharpe * 0.1 + step_return * 50

    # ─── Helpers ───────────────────────────────────────────────────────────────

    def _current_price(self) -> float:
        return float(self.price_data["close"].iloc[self.current_step])

    def _portfolio_value(self, current_price: float) -> float:
        value = self.capital
        if self.position is not None:
            self.position.update_pnl(current_price)
            value += self.position.current_value
        return value

    def _get_info(self) -> Dict[str, Any]:
        current_price = self._current_price()
        pv = self._portfolio_value(current_price)
        drawdown = (self.peak_value - pv) / (self.peak_value + 1e-8)
        win_rate = 0.0
        if self.trade_history:
            wins = sum(1 for t in self.trade_history if t.pnl > 0)
            win_rate = wins / len(self.trade_history)

        return {
            "portfolio_value": pv,
            "capital": self.capital,
            "total_return": (pv - self.initial_capital) / self.initial_capital,
            "drawdown": drawdown,
            "n_trades": len(self.trade_history),
            "win_rate": win_rate,
            "step": self.current_step,
            "has_position": self.position is not None,
        }

    @property
    def _symbol(self) -> str:
        return getattr(self.price_data, "name", "UNKNOWN")

    # ─── Technical Indicators ─────────────────────────────────────────────────

    @staticmethod
    def _rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / (loss + 1e-8)
        return (100 - (100 / (1 + rs))) / 100  # normalized 0-1

    @staticmethod
    def _macd(prices: pd.Series, fast=12, slow=26, signal=9):
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h, l, c = df["high"], df["low"], df["close"].shift(1)
        tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def render(self):
        if self.render_mode == "human":
            info = self._get_info()
            print(
                f"Step {self.current_step:5d} | "
                f"Value: ${info['portfolio_value']:>10,.2f} | "
                f"Return: {info['total_return']:>+7.2%} | "
                f"Drawdown: {info['drawdown']:>6.2%} | "
                f"Trades: {info['n_trades']:>4d} | "
                f"WinRate: {info['win_rate']:>5.1%}"
            )
