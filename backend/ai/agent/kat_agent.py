"""
KAT RL Agent
=============
PPO-based reinforcement learning agent for autonomous trading.

Architecture:
  Input → Feature Extractor (LSTM + MLP) → Policy Network → Action
                                          → Value Network → V(s)

Why PPO (Proximal Policy Optimization)?
  - Stable training — critical for financial data with non-stationarity
  - Handles continuous + discrete action spaces
  - Battle-tested on trading tasks in research literature
  - Stable-Baselines3 implementation is production-quality

Why LSTM in feature extractor?
  - Markets have temporal dependencies — yesterday's pattern matters
  - LSTM processes the 60-bar market history with memory
  - Better than pure MLP at capturing momentum/mean-reversion patterns

Training stages:
  Stage 1: Offline pre-training on historical backtest data (weeks 1-2)
  Stage 2: Online paper trading — agent learns from real executions (weeks 3+)
  Stage 3: Performance validation — must hit targets before live
"""

import os
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Type, Union
from stable_baselines3 import PPO
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize
from stable_baselines3.common.callbacks import (
    EvalCallback, CheckpointCallback, CallbackList
)
from stable_baselines3.common.monitor import Monitor
import gymnasium as gym
import logging

logger = logging.getLogger("kat.agent")

# ─── Dimensions (must match trading_env.py) ───────────────────────────────────
LOOKBACK = 60
N_MARKET_FEATURES = 25
N_PORTFOLIO_FEATURES = 8
N_SIGNAL_FEATURES = 6
N_TIME_FEATURES = 4

MARKET_DIM = LOOKBACK * N_MARKET_FEATURES
PORTFOLIO_DIM = N_PORTFOLIO_FEATURES
SIGNAL_DIM = N_SIGNAL_FEATURES
TIME_DIM = N_TIME_FEATURES


# ─── Custom Feature Extractor ─────────────────────────────────────────────────

class KATFeatureExtractor(BaseFeaturesExtractor):
    """
    Dual-path feature extractor:
      Path 1: LSTM processes the 60-bar market history
      Path 2: MLP processes portfolio state + signal features + time features
    
    Both paths concatenated → 256-dim features → Policy/Value heads
    """

    def __init__(self, observation_space: gym.Space, features_dim: int = 256):
        super().__init__(observation_space, features_dim)

        # ── LSTM path (market history) ─────────────────────────────────────────
        self.lstm_hidden = 128
        self.lstm = nn.LSTM(
            input_size=N_MARKET_FEATURES,
            hidden_size=self.lstm_hidden,
            num_layers=2,
            batch_first=True,
            dropout=0.1,
        )

        # ── MLP path (portfolio + signals + time) ─────────────────────────────
        flat_dim = PORTFOLIO_DIM + SIGNAL_DIM + TIME_DIM
        self.context_mlp = nn.Sequential(
            nn.Linear(flat_dim, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
        )

        # ── Fusion layer ─────────────────────────────────────────────────────
        fused_dim = self.lstm_hidden + 64
        self.fusion = nn.Sequential(
            nn.Linear(fused_dim, features_dim),
            nn.LayerNorm(features_dim),
            nn.ReLU(),
        )

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        batch_size = observations.shape[0]

        # Split observation into components
        market_flat = observations[:, :MARKET_DIM]
        portfolio = observations[:, MARKET_DIM : MARKET_DIM + PORTFOLIO_DIM]
        signal = observations[:, MARKET_DIM + PORTFOLIO_DIM : MARKET_DIM + PORTFOLIO_DIM + SIGNAL_DIM]
        time_feat = observations[:, -TIME_DIM:]

        # Path 1: reshape market data → (batch, lookback, features) → LSTM
        market_seq = market_flat.view(batch_size, LOOKBACK, N_MARKET_FEATURES)
        lstm_out, (h_n, _) = self.lstm(market_seq)
        market_encoded = h_n[-1]  # last layer hidden state: (batch, lstm_hidden)

        # Path 2: context features through MLP
        context = torch.cat([portfolio, signal, time_feat], dim=1)
        context_encoded = self.context_mlp(context)

        # Fusion
        fused = torch.cat([market_encoded, context_encoded], dim=1)
        return self.fusion(fused)


# ─── Policy ─────────────────────────────────────────────────────────────────

class KATPolicy(ActorCriticPolicy):
    """Custom policy using KATFeatureExtractor."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
            features_extractor_class=KATFeatureExtractor,
            features_extractor_kwargs={"features_dim": 256},
            net_arch=dict(pi=[128, 64], vf=[128, 64]),
            activation_fn=nn.ReLU,
        )


# ─── Agent Factory ────────────────────────────────────────────────────────────

def create_kat_agent(
    env: gym.Env,
    model_path: Optional[str] = None,
    learning_rate: float = 3e-4,
    n_steps: int = 2048,
    batch_size: int = 64,
    n_epochs: int = 10,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    clip_range: float = 0.2,
    ent_coef: float = 0.01,  # entropy bonus — encourages exploration
    device: str = "auto",
) -> PPO:
    """
    Create or load a KAT PPO agent.
    
    If model_path provided, loads from checkpoint.
    Otherwise creates fresh agent.
    """
    policy_kwargs = {
        "features_extractor_class": KATFeatureExtractor,
        "features_extractor_kwargs": {"features_dim": 256},
        "net_arch": dict(pi=[128, 64], vf=[128, 64]),
        "activation_fn": nn.ReLU,
        "share_features_extractor": True,  # share LSTM between policy and value
    }

    if model_path and os.path.exists(model_path):
        logger.info(f"Loading existing agent from {model_path}")
        agent = PPO.load(model_path, env=env, device=device)
        logger.info(f"Agent loaded — trained for {agent.num_timesteps:,} timesteps")
    else:
        logger.info("Creating new KAT agent")
        agent = PPO(
            policy="MlpPolicy",  # overridden by policy_kwargs
            env=env,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            ent_coef=ent_coef,
            verbose=1,
            tensorboard_log="./tensorboard/kat",
            policy_kwargs=policy_kwargs,
            device=device,
        )

    return agent


# ─── Multi-Symbol Vectorized Environment ─────────────────────────────────────

def make_vec_env(
    env_fns: list,
    n_envs: Optional[int] = None,
    normalize: bool = True,
) -> Union[SubprocVecEnv, VecNormalize]:
    """
    Wrap multiple single-symbol environments for parallel training.
    
    Training on 15+ symbols simultaneously = much more data per update.
    SubprocVecEnv runs each env in a separate process (uses all CPU cores).
    """
    n_envs = n_envs or len(env_fns)
    env_fns = env_fns[:n_envs]

    vec_env = SubprocVecEnv(env_fns)

    if normalize:
        # VecNormalize: running mean/std normalization of observations + rewards
        # Critical for stable training — financial data has wildly different scales
        vec_env = VecNormalize(
            vec_env,
            norm_obs=True,
            norm_reward=True,
            clip_obs=10.0,
            clip_reward=10.0,
        )

    logger.info(f"Vectorized environment: {n_envs} parallel envs")
    return vec_env


# ─── Training Callbacks ───────────────────────────────────────────────────────

def make_callbacks(
    eval_env: gym.Env,
    checkpoint_dir: str = "./checkpoints",
    eval_freq: int = 10_000,
    n_eval_episodes: int = 5,
) -> CallbackList:
    """Standard callback stack for training."""
    os.makedirs(checkpoint_dir, exist_ok=True)

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=f"{checkpoint_dir}/best",
        log_path=f"{checkpoint_dir}/eval_logs",
        eval_freq=eval_freq,
        n_eval_episodes=n_eval_episodes,
        deterministic=True,
        render=False,
        verbose=1,
    )

    checkpoint_callback = CheckpointCallback(
        save_freq=eval_freq,
        save_path=f"{checkpoint_dir}/periodic",
        name_prefix="kat_agent",
        verbose=1,
    )

    return CallbackList([eval_callback, checkpoint_callback])


# ─── Performance Metrics ─────────────────────────────────────────────────────

class AgentPerformanceTracker:
    """
    Track agent performance across paper trading.
    
    GRADUATION CRITERIA — must hit ALL before going live:
      - Min 100 paper trades completed
      - Win rate > 52%
      - Sharpe ratio > 1.0 (rolling 30 days)
      - Max drawdown < 8%
      - Consecutive losing days < 3
      - Total return > 5% (on 100k paper capital)
    """

    GRADUATION_TARGETS = {
        "min_trades": 100,
        "win_rate": 0.52,
        "sharpe_ratio": 1.0,
        "max_drawdown": 0.08,
        "max_consecutive_losses": 3,
        "min_total_return": 0.05,
    }

    def __init__(self):
        self.trades: List[Dict] = []
        self.daily_returns: List[float] = []
        self.portfolio_values: List[float] = []
        self.initial_capital: float = 100_000.0

    def record_trade(self, trade: Dict):
        self.trades.append(trade)

    def record_daily_return(self, daily_return: float, portfolio_value: float):
        self.daily_returns.append(daily_return)
        self.portfolio_values.append(portfolio_value)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        return wins / len(self.trades)

    @property
    def sharpe_ratio(self) -> float:
        if len(self.daily_returns) < 20:
            return 0.0
        returns = np.array(self.daily_returns)
        return (np.mean(returns) / (np.std(returns) + 1e-8)) * np.sqrt(252)

    @property
    def max_drawdown(self) -> float:
        if not self.portfolio_values:
            return 0.0
        values = np.array(self.portfolio_values)
        peak = np.maximum.accumulate(values)
        drawdowns = (peak - values) / (peak + 1e-8)
        return float(np.max(drawdowns))

    @property
    def total_return(self) -> float:
        if not self.portfolio_values:
            return 0.0
        return (self.portfolio_values[-1] - self.initial_capital) / self.initial_capital

    @property
    def consecutive_losses(self) -> int:
        """Current streak of losing days."""
        count = 0
        for r in reversed(self.daily_returns):
            if r < 0:
                count += 1
            else:
                break
        return count

    def graduation_check(self) -> Tuple[bool, Dict]:
        """Check if agent has met all graduation criteria for live trading."""
        checks = {
            "min_trades": self.n_trades >= self.GRADUATION_TARGETS["min_trades"],
            "win_rate": self.win_rate >= self.GRADUATION_TARGETS["win_rate"],
            "sharpe_ratio": self.sharpe_ratio >= self.GRADUATION_TARGETS["sharpe_ratio"],
            "max_drawdown": self.max_drawdown <= self.GRADUATION_TARGETS["max_drawdown"],
            "consecutive_losses": self.consecutive_losses <= self.GRADUATION_TARGETS["max_consecutive_losses"],
            "total_return": self.total_return >= self.GRADUATION_TARGETS["min_total_return"],
        }
        passed = all(checks.values())

        report = {
            "passed": passed,
            "checks": checks,
            "metrics": {
                "n_trades": self.n_trades,
                "win_rate": f"{self.win_rate:.1%}",
                "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
                "max_drawdown": f"{self.max_drawdown:.1%}",
                "consecutive_losses": self.consecutive_losses,
                "total_return": f"{self.total_return:.1%}",
            },
            "targets": self.GRADUATION_TARGETS,
        }
        return passed, report

    def summary(self) -> str:
        passed, report = self.graduation_check()
        lines = [
            "═" * 50,
            "  KAT AGENT PERFORMANCE REPORT",
            "═" * 50,
        ]
        for metric, value in report["metrics"].items():
            check = report["checks"].get(metric, False)
            target = report["targets"].get(metric, "")
            status = "✅" if check else "❌"
            lines.append(f"  {status} {metric:<25} {value} (target: {target})")
        lines.append("═" * 50)
        lines.append(f"  {'🎓 READY FOR LIVE TRADING' if passed else '📚 STILL IN TRAINING'}")
        lines.append("═" * 50)
        return "\n".join(lines)


class KATAgent:
    """Wrapper class that bundles the PPO model with KAT-specific config."""

    def __init__(self, env, device='cpu'):
        from stable_baselines3 import PPO
        self.env = env
        self.device = device
        self.tracker = AgentPerformanceTracker()
        self.model = PPO(
            KATPolicy,
            env,
            verbose=0,
            device=device,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
        )

    def learn(self, total_timesteps: int, **kwargs):
        self.model.learn(total_timesteps=total_timesteps, **kwargs)

    def predict(self, obs, deterministic=True):
        return self.model.predict(obs, deterministic=deterministic)

    def save(self, path: str):
        self.model.save(path)

    @classmethod
    def load(cls, path: str, env):
        from stable_baselines3 import PPO
        agent = cls.__new__(cls)
        agent.env = env
        agent.tracker = AgentPerformanceTracker()
        agent.model = PPO.load(path, env=env)
        return agent

