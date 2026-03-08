"""
KAT Training Pipeline
======================
Orchestrates the full training lifecycle:

STAGE 1 — OFFLINE PRE-TRAINING  (weeks 1-2)
  Feed: Millions of bars from Polygon.io + historical C2/Holly signals
  Goal: Agent learns basic market structure, when signals are reliable,
        how to size positions, when NOT to trade
  Output: Pre-trained checkpoint (~50M timesteps)

STAGE 2 — PAPER TRADING LOOP  (weeks 3+)
  Feed: Live market data + live signals from all sources
  Loop: Observe → Decide → Execute (paper) → Get result → Learn
  Goal: Fine-tune on real execution quality, slippage, signal timing
  Output: Production model that graduates when performance criteria met

STAGE 3 — LIVE TRADING  (post-graduation)
  Same model, same logic — IBKR port switches from 7496 to 7497
"""

import os
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import mlflow
import mlflow.pytorch
from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize

logger = logging.getLogger("kat.trainer")

CHECKPOINT_DIR = Path(os.getenv("KAT_CHECKPOINT_DIR", "/data/kat/checkpoints"))
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")


# ─── Training Configuration ───────────────────────────────────────────────────

class TrainingConfig:
    """All hyperparameters in one place."""

    # PPO hyperparameters (tuned for financial time-series)
    LEARNING_RATE = 3e-4
    N_STEPS = 2048           # steps per env per update
    BATCH_SIZE = 256         # minibatch size
    N_EPOCHS = 10            # passes over each rollout buffer
    GAMMA = 0.995            # discount — high because we want long-term profit
    GAE_LAMBDA = 0.95        # GAE parameter
    CLIP_RANGE = 0.2         # PPO clip
    ENT_COEF = 0.005         # entropy bonus — reduced from default to avoid over-exploration
    VF_COEF = 0.5
    MAX_GRAD_NORM = 0.5

    # Training stages
    STAGE1_TOTAL_STEPS = 50_000_000   # 50M steps offline
    STAGE2_STEPS_PER_DAY = 10_000     # ~10k paper steps per trading day

    # Environment settings
    N_PARALLEL_ENVS = 8              # parallel environments (use all Hetzner cores)
    INITIAL_CAPITAL = 100_000
    TRANSACTION_COST = 0.001

    # Evaluation
    EVAL_FREQ = 100_000
    N_EVAL_EPISODES = 10

    # Training symbols (subset used in Stage 1)
    STAGE1_SYMBOLS = [
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA",
        "META", "GOOGL", "TSLA", "AMD", "GLD",
    ]


# ─── Stage 1: Offline Pre-Training ────────────────────────────────────────────

class OfflineTrainer:
    """
    Pre-trains the agent on years of historical data.
    
    We create N_PARALLEL_ENVS environments, each on a different symbol
    and time period. The agent sees millions of diverse market scenarios.
    
    Key insight: We also inject the historical C2/Holly signals into
    the environment's signal features. The agent learns to trust/distrust
    signals based on what actually happened afterward.
    """

    def __init__(
        self,
        dataset_bundle,       # DatasetBundle from pipeline.py
        config: TrainingConfig = None,
        checkpoint_dir: Path = CHECKPOINT_DIR,
    ):
        self.bundle = dataset_bundle
        self.config = config or TrainingConfig()
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        total_steps: Optional[int] = None,
        resume_from: Optional[str] = None,
    ):
        """Run offline pre-training."""
        from backend.ai.environment.trading_env import KATTradingEnv
        from backend.ai.agent.kat_agent import create_kat_agent, make_callbacks

        total_steps = total_steps or self.config.STAGE1_TOTAL_STEPS
        logger.info(f"Starting Stage 1: Offline pre-training ({total_steps:,} steps)")

        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment("kat_stage1_offline")

        with mlflow.start_run(run_name=f"stage1_{datetime.now():%Y%m%d_%H%M}"):
            # Log config
            mlflow.log_params({
                "stage": 1,
                "total_steps": total_steps,
                "n_symbols": self.bundle.n_symbols,
                "n_signals": self.bundle.n_signals,
                "learning_rate": self.config.LEARNING_RATE,
                "n_parallel_envs": self.config.N_PARALLEL_ENVS,
            })

            # Build vectorized environment
            env_fns = self._make_env_fns(KATTradingEnv, train=True)
            vec_env = SubprocVecEnv(env_fns)
            vec_env = VecNormalize(
                vec_env, norm_obs=True, norm_reward=True,
                clip_obs=10.0, clip_reward=10.0,
            )

            # Eval environment (held-out symbols / later time period)
            eval_env_fns = self._make_env_fns(KATTradingEnv, train=False)
            eval_vec_env = SubprocVecEnv(eval_env_fns[:2])
            eval_vec_env = VecNormalize(eval_vec_env, norm_obs=True, norm_reward=False)

            # Create or resume agent
            agent = create_kat_agent(
                env=vec_env,
                model_path=resume_from,
                learning_rate=self.config.LEARNING_RATE,
                n_steps=self.config.N_STEPS,
                batch_size=self.config.BATCH_SIZE,
                n_epochs=self.config.N_EPOCHS,
                gamma=self.config.GAMMA,
            )

            callbacks = make_callbacks(
                eval_env=eval_vec_env,
                checkpoint_dir=str(self.checkpoint_dir / "stage1"),
                eval_freq=self.config.EVAL_FREQ,
                n_eval_episodes=self.config.N_EVAL_EPISODES,
            )

            logger.info(f"Training on {len(env_fns)} environments...")
            agent.learn(
                total_timesteps=total_steps,
                callback=callbacks,
                progress_bar=True,
                reset_num_timesteps=resume_from is None,
            )

            # Save final model
            final_path = self.checkpoint_dir / "stage1" / "kat_stage1_final"
            agent.save(str(final_path))
            vec_env.save(str(final_path) + "_vecnorm.pkl")

            # Log final model to MLflow
            mlflow.log_artifact(str(final_path) + ".zip", artifact_path="model")
            logger.info(f"Stage 1 complete. Model saved: {final_path}")

        return str(final_path)

    def _make_env_fns(self, EnvClass, train: bool = True) -> list:
        """Create env factory functions for vectorization."""
        symbols = list(self.bundle.price_data.keys())
        n_envs = self.config.N_PARALLEL_ENVS

        # Split: first 80% for training, last 20% for eval
        if train:
            symbols = symbols[:int(len(symbols) * 0.8)]
        else:
            symbols = symbols[int(len(symbols) * 0.8):]

        env_fns = []
        for i in range(n_envs):
            symbol = symbols[i % len(symbols)]
            price_df = self.bundle.price_data[symbol].copy()
            signal_df = self.bundle.get_signal_df_for_symbol(symbol)

            # For training: use different time slice per env to maximize diversity
            if train:
                n_bars = len(price_df)
                slice_size = int(n_bars * 0.8)
                start = (i * slice_size // n_envs) % (n_bars - slice_size - 100)
                price_df = price_df.iloc[start : start + slice_size]

            def make_fn(pdf=price_df, sdf=signal_df):
                from backend.ai.environment.trading_env import KATTradingEnv
                from stable_baselines3.common.monitor import Monitor

                def _fn():
                    env = KATTradingEnv(
                        price_data=pdf,
                        signal_data=sdf,
                        initial_capital=self.config.INITIAL_CAPITAL,
                        transaction_cost=self.config.TRANSACTION_COST,
                        use_sharpe_reward=True,
                    )
                    return Monitor(env)
                return _fn

            env_fns.append(make_fn())

        return env_fns


# ─── Stage 2: Online Paper Trading Loop ──────────────────────────────────────

class PaperTradingLoop:
    """
    Continuous online learning loop during paper trading.
    
    Lifecycle (runs daily during market hours):
      1. Pull live market data (Polygon WebSocket)
      2. Pull live signals (C2 poller + webhook receiver)
      3. Agent observes current state → selects action
      4. Execute on IBKR paper account
      5. Observe fill price and outcome
      6. Add (state, action, reward, next_state) to replay buffer
      7. Periodically update model (every N paper trades)
      8. Log everything to Supabase + MLflow
      9. Check graduation criteria
    """

    def __init__(
        self,
        model_path: str,           # Stage 1 checkpoint to fine-tune
        ibkr_client=None,          # IBKR connection
        supabase_client=None,      # For logging
        config: TrainingConfig = None,
        checkpoint_dir: Path = CHECKPOINT_DIR,
    ):
        self.model_path = model_path
        self.ibkr = ibkr_client
        self.supabase = supabase_client
        self.config = config or TrainingConfig()
        self.checkpoint_dir = checkpoint_dir / "stage2"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        from backend.ai.agent.kat_agent import AgentPerformanceTracker
        self.tracker = AgentPerformanceTracker()

    def run_session(self, price_data: pd.DataFrame, signal_data: Optional[pd.DataFrame] = None):
        """
        Run one paper trading session (one market day).
        Called by the scheduler at market open.
        """
        from backend.ai.environment.trading_env import KATTradingEnv
        from backend.ai.agent.kat_agent import create_kat_agent

        env = KATTradingEnv(
            price_data=price_data,
            signal_data=signal_data,
            initial_capital=self.config.INITIAL_CAPITAL,
        )

        agent = create_kat_agent(env=env, model_path=self.model_path)

        obs, _ = env.reset()
        done = False
        session_trades = 0

        while not done:
            action, _ = agent.predict(obs, deterministic=False)  # stochastic during training
            obs, reward, terminated, truncated, info = env.step(int(action))
            done = terminated or truncated

            # If a trade was executed, sync to IBKR paper account
            if info.get("trade_executed") and self.ibkr:
                self._sync_to_ibkr(info, action)
                session_trades += 1

        # End of session: update model on today's experience
        if env.trade_history:
            self._update_model_from_session(agent, env)
            self._log_session(env, session_trades)

        # Check graduation
        passed, report = self.tracker.graduation_check()
        if passed:
            logger.info("🎓 GRADUATION CRITERIA MET — Agent ready for live trading!")
            self._notify_graduation(report)

        return env.trade_history, report

    def _sync_to_ibkr(self, info: Dict, action: int):
        """Mirror the agent's paper decision to IBKR paper account."""
        if self.ibkr is None:
            return
        # IBKR execution code here — uses the execution manager
        logger.debug(f"Syncing action {action} to IBKR paper account")

    def _update_model_from_session(self, agent, env):
        """
        Fine-tune agent on today's experience.
        Uses the trade history + outcomes to update policy.
        """
        try:
            agent.learn(
                total_timesteps=len(env.trade_history) * 100,
                reset_num_timesteps=False,
                progress_bar=False,
            )
            # Save updated checkpoint
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            save_path = self.checkpoint_dir / f"kat_paper_{ts}"
            agent.save(str(save_path))
            self.model_path = str(save_path)  # use latest for next session
            logger.info(f"Model updated. Checkpoint: {save_path}")
        except Exception as e:
            logger.error(f"Model update failed: {e}")

    def _log_session(self, env, n_trades: int):
        """Log session summary to Supabase."""
        info = env._get_info()
        if self.supabase:
            try:
                self.supabase.table("training_sessions").insert({
                    "date": datetime.now().isoformat(),
                    "n_trades": n_trades,
                    "total_return": info["total_return"],
                    "win_rate": info["win_rate"],
                    "portfolio_value": info["portfolio_value"],
                    "drawdown": info["drawdown"],
                }).execute()
            except Exception as e:
                logger.error(f"Supabase log failed: {e}")

        for trade in env.trade_history:
            self.tracker.record_trade({
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "hold_bars": trade.hold_bars,
            })

        logger.info(
            f"Session complete | Trades: {n_trades} | "
            f"Return: {info['total_return']:+.2%} | "
            f"WinRate: {info['win_rate']:.1%}"
        )

    def _notify_graduation(self, report: Dict):
        """Send graduation notification via Telegram."""
        logger.info("Sending graduation notification...")
        logger.info(f"Graduation report: {report}")


# ─── Main Entry Point ─────────────────────────────────────────────────────────

class KATTrainer:
    """
    Top-level coordinator for all training stages.
    Called by the main KAT process.
    """

    def __init__(self, config: TrainingConfig = None):
        self.config = config or TrainingConfig()

    def stage1_pretrain(self, c2_strategy_ids: List[str] = None, resume_from: str = None) -> str:
        """Full Stage 1 offline pre-training pipeline."""
        from backend.ai.data_ingestion.pipeline import DatasetBuilder

        logger.info("═" * 60)
        logger.info("  KAT TRAINING — STAGE 1: OFFLINE PRE-TRAINING")
        logger.info("═" * 60)

        # Build training dataset from subscriptions
        builder = DatasetBuilder()
        bundle = builder.build_training_bundle(
            c2_strategy_ids=c2_strategy_ids or [],
            symbols=self.config.STAGE1_SYMBOLS,
            from_date="2018-01-01",
            to_date="2025-12-31",
        )
        logger.info(f"Dataset ready: {bundle}")

        # Train
        trainer = OfflineTrainer(bundle, self.config)
        model_path = trainer.run(resume_from=resume_from)

        logger.info(f"Stage 1 complete. Model: {model_path}")
        return model_path

    def stage2_paper(self, model_path: str, ibkr_client=None, supabase_client=None):
        """Start Stage 2 paper trading loop."""
        logger.info("═" * 60)
        logger.info("  KAT TRAINING — STAGE 2: PAPER TRADING LOOP")
        logger.info("═" * 60)

        loop = PaperTradingLoop(
            model_path=model_path,
            ibkr_client=ibkr_client,
            supabase_client=supabase_client,
            config=self.config,
        )
        return loop

    def print_graduation_status(self, loop: PaperTradingLoop):
        """Print current performance vs graduation targets."""
        print(loop.tracker.summary())
