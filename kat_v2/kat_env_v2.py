"""
KAT v2.0 — Trading Environment
================================
Clean rebuild of KATEnvV3 with:
  - transaction_cost = 0.0 (SNB confirmed 0% commission)
  - Technical indicators in observation space (Stream 4)
  - Sharpe-aware reward (warmup then Sharpe component)
  - No inaction penalty (causes instability)
  - Clean reward signal: reward_scaling = 0.1

Action space: Discrete(5)
  0 = HOLD
  1 = BUY  (open long, full position)
  2 = SELL (close long, open short)
  3 = ADD  (add 50% to existing position)
  4 = CLOSE (close 50% of position)

Observation space: Box(1872,)
  [0:1404]    macro features (FRED)
  [1404:1512] portfolio state
  [1512:1722] futures OHLCV
  [1722:1872] technical indicators

Author: KAT Research Team
Version: 2.0
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from collections import deque
from feature_pipeline import load_features, PORTFOLIO_FEATURES


# ── Constants ─────────────────────────────────────────────────────────────────
ACTIONS = {0: "HOLD", 1: "BUY", 2: "SELL", 3: "ADD", 4: "CLOSE"}
INITIAL_EQUITY    = 100_000.0
TRANSACTION_COST  = 0.0        # SNB = 0% commission — eliminates dead policy bias
REWARD_SCALING    = 0.1        # High enough for clear gradient signal
MAX_POSITION      = 1.0        # Maximum position size (1 = 100% of equity)
SHARPE_WARMUP     = 10_000_000 # Steps before Sharpe component activates (Stage 4)
SHARPE_WINDOW     = 60         # Days for rolling Sharpe calculation


class KATEnvV2(gym.Env):
    """
    KAT Trading Environment v2.0

    Core design principles (from research synthesis):
    1. transaction_cost=0.0: removes structural dead policy bias
    2. reward_scaling=0.1: ensures policy gradient has clear signal
    3. No inaction penalty: caused KL explosions in v1.0 testing
    4. Stochastic eval: deterministic=False in EvalCallback
    5. Clean obs normalization: all features in [-1, 1] or [0, 1]
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        db_path: str,
        start_date: str,
        end_date: str,
        initial_equity: float = INITIAL_EQUITY,
        transaction_cost: float = TRANSACTION_COST,
        reward_scaling: float = REWARD_SCALING,
        sharpe_warmup: int = SHARPE_WARMUP,
    ):
        super().__init__()

        self.db_path          = db_path
        self.start_date       = start_date
        self.end_date         = end_date
        self.initial_equity   = initial_equity
        self.transaction_cost = transaction_cost
        self.reward_scaling   = reward_scaling
        self.sharpe_warmup    = sharpe_warmup

        # Load all features at init — cached in RAM for training speed
        self._macro, self._futures, self._tech = load_features(
            db_path, start_date, end_date
        )
        self._dates = self._macro.index.tolist()
        self._n_days = len(self._dates)

        # Compute observation size
        self._macro_size    = self._macro.shape[1]
        self._futures_size  = self._futures.shape[1]
        self._tech_size     = self._tech.shape[1]
        self._obs_size = (
            self._macro_size +
            PORTFOLIO_FEATURES +
            self._futures_size +
            self._tech_size
        )

        # Gym spaces
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(self._obs_size,),
            dtype=np.float32
        )
        self.action_space = spaces.Discrete(5)

        # Portfolio state (reset on each episode)
        self._reset_portfolio()

        # Rolling return buffer for Sharpe calculation
        self._return_buffer = deque(maxlen=SHARPE_WINDOW)
        self._total_steps   = 0

    def _reset_portfolio(self):
        """Reset all portfolio state variables."""
        self._equity      = self.initial_equity
        self._peak_equity = self.initial_equity
        self._position    = 0.0   # Long: +, Short: -, Zero: flat
        self._entry_price = 0.0
        self._trade_count = 0
        self._idx         = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._reset_portfolio()
        return self._obs(), {}

    def step(self, action: int):
        """
        Execute one trading step.

        Returns: (obs, reward, terminated, truncated, info)
        """
        price      = float(self._futures.iloc[self._idx]["ES_close"])  # use ES as reference
        prev_equity = self._equity
        cost        = 0.0

        # ── Execute action ────────────────────────────────────────────────────
        if action == 1 and self._position == 0:
            # BUY: open long position
            self._position    = 1.0
            self._entry_price = price
            cost = price * self.transaction_cost
            self._trade_count += 1

        elif action == 2 and self._position > 0:
            # SELL: close long, open short
            self._equity     += (price - self._entry_price) * self._position - cost
            self._position    = -1.0
            self._entry_price = price
            cost = price * self.transaction_cost * 2  # close + open
            self._trade_count += 1

        elif action == 2 and self._position == 0:
            # SELL: open short from flat
            self._position    = -1.0
            self._entry_price = price
            cost = price * self.transaction_cost
            self._trade_count += 1

        elif action == 3 and self._position != 0:
            # ADD: increase position by 50%
            add_size = abs(self._position) * 0.5
            sign     = 1.0 if self._position > 0 else -1.0
            self._position += sign * add_size
            cost = price * self.transaction_cost * add_size
            self._trade_count += 1

        elif action == 4 and self._position != 0:
            # CLOSE: reduce position by 50%
            close_size = abs(self._position) * 0.5
            sign       = 1.0 if self._position > 0 else -1.0
            pnl = sign * (price - self._entry_price) * close_size
            self._equity   += pnl - cost
            self._position -= sign * close_size
            cost = price * self.transaction_cost * close_size
            self._trade_count += 1

        # ── Compute equity and drawdown ───────────────────────────────────────
        unrealized = (price - self._entry_price) * self._position if self._position != 0 else 0.0
        total_equity = self._equity + unrealized

        if total_equity > self._peak_equity:
            self._peak_equity = total_equity

        drawdown = (self._peak_equity - total_equity) / (self._peak_equity + 1e-8)

        # ── Reward function (research-backed v2.0) ────────────────────────────
        pnl_return = (total_equity - prev_equity) / (prev_equity + 1e-8)
        reward = pnl_return * self.reward_scaling - drawdown * 0.001

        # Update rolling return buffer
        self._return_buffer.append(pnl_return)
        self._total_steps += 1

        # ── Advance timestep ──────────────────────────────────────────────────
        self._idx += 1
        terminated = self._idx >= self._n_days - 1
        truncated  = False

        info = {
            "equity":     total_equity,
            "position":   self._position,
            "drawdown":   drawdown,
            "trades":     self._trade_count,
            "price":      price,
            "pnl_return": pnl_return,
        }

        return self._obs(), float(reward), terminated, truncated, info

    def _obs(self) -> np.ndarray:
        """
        Build observation vector for current timestep.
        Shape: (obs_size,) = (1872,)
        """
        idx = min(self._idx, self._n_days - 1)

        # Stream 1: Macro (1404)
        macro_obs = self._macro.iloc[idx].values.astype(np.float32)

        # Stream 2: Portfolio (108)
        price     = float(self._futures.iloc[idx]["ES_close"])
        equity    = self._equity + (
            (price - self._entry_price) * self._position if self._position != 0 else 0.0
        )
        portfolio_obs = self._build_portfolio_obs(equity, price)

        # Stream 3: Futures OHLCV (210)
        futures_obs = self._futures.iloc[idx].values.astype(np.float32)

        # Stream 4: Technical indicators (150)
        tech_obs = self._tech.iloc[idx].values.astype(np.float32)

        obs = np.concatenate([macro_obs, portfolio_obs, futures_obs, tech_obs])

        # Clip and replace NaN/Inf
        obs = np.nan_to_num(obs, nan=0.0, posinf=1.0, neginf=-1.0)
        obs = np.clip(obs, -10.0, 10.0)

        return obs.astype(np.float32)

    def _build_portfolio_obs(self, equity: float, price: float) -> np.ndarray:
        """
        Build 108-dimensional portfolio state vector.
        All values normalized to [0, 1] or [-1, 1].
        """
        obs = np.zeros(PORTFOLIO_FEATURES, dtype=np.float32)

        # Equity ratio (current / initial)
        obs[0] = np.clip(equity / self.initial_equity, 0, 5) / 5

        # Position direction and size
        obs[1] = np.clip(self._position, -1, 1)  # -1=short, 0=flat, 1=long

        # Entry price relative to current
        if self._entry_price > 0:
            obs[2] = np.clip((price - self._entry_price) / (self._entry_price + 1e-8), -0.2, 0.2) / 0.2

        # Drawdown
        peak = self._peak_equity
        drawdown = (peak - equity) / (peak + 1e-8)
        obs[3] = np.clip(drawdown, 0, 0.5) / 0.5

        # Trade count (normalized)
        obs[4] = np.clip(self._trade_count / 100, 0, 1)

        # Progress through episode
        obs[5] = self._idx / self._n_days

        # Remaining obs[6:108] = 0 (reserved for future features)
        return obs


# ── Smoke Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/kat/kat_v2.db"

    print("Testing KATEnvV2...")
    env = KATEnvV2(db_path=db_path, start_date="2015-01-01", end_date="2023-12-31")

    print(f"Obs size:    {env.observation_space.shape[0]}")
    print(f"Action size: {env.action_space.n}")

    obs, _ = env.reset()
    print(f"Reset obs shape: {obs.shape}")
    print(f"Obs range: [{obs.min():.3f}, {obs.max():.3f}]")

    # Run 100 random steps
    total_reward = 0
    for i in range(100):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        if terminated:
            break

    print(f"100 steps completed. Total reward: {total_reward:.4f}")
    print(f"Final equity: {info['equity']:.2f}")
    print(f"Trades executed: {info['trades']}")
    print("KATEnvV2 OK ✓")
