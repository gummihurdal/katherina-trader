"""
KAT Signal Outcome Logger
==========================
The core of the feedback loop.

WHAT IT DOES:
  1. When any signal fires (C2, Holly, TradersPost, internal) →
     snapshot the full market state at that moment (60 bars of context)
  2. When the trade closes (profit, loss, stop, take-profit) →
     tag the outcome back onto the original snapshot
  3. Every tagged snapshot = one labeled training example
  4. Daily: flush labeled examples to training buffer → retrain AI

THIS IS WHY THIS MATTERS:
  The AI doesn't just see "Holly fired on NVDA → +2.3%"
  It sees:
    - RSI was 67 (approaching overbought)
    - Market was trending up (SMA20 > SMA50)
    - Volume spike: 2.1x average
    - Time: 09:47 (first 15 min after open)
    - Portfolio heat: 4% (room to add)
    - Holly confidence: 0.81
    → Outcome: +2.3% in 47 minutes

  After 500 such examples, the agent knows EXACTLY
  when Holly signals are reliable vs. noise.

DATABASE TABLES USED:
  signal_snapshots  — market state at signal fire time
  signal_outcomes   — final P&L tagged to snapshot
  training_buffer   — ready-to-train labeled examples
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger("kat.feedback.logger")


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class MarketSnapshot:
    """
    Complete market state at the moment a signal fires.
    This is the INPUT to the AI when it learns from this trade.
    """
    snapshot_id: str = field(default_factory=lambda: str(uuid4()))
    signal_id: str = ""
    source: str = ""                    # "holly_ai", "collective2", etc.
    source_strategy_id: str = ""
    symbol: str = ""
    signal_action: str = ""             # "buy" or "sell"
    signal_confidence: float = 0.0
    signal_urgency: str = "normal"
    fired_at: str = ""                  # ISO timestamp

    # Market context (60 bars → compressed to key features)
    price_at_signal: float = 0.0
    market_features: List[float] = field(default_factory=list)  # 25 indicators
    market_trend: str = ""              # "up", "down", "sideways"
    rsi_14: float = 0.0
    macd_signal: float = 0.0
    atr_pct: float = 0.0                # volatility at signal time
    volume_ratio: float = 0.0           # vs 20-day average
    bb_position: float = 0.0            # 0=lower band, 1=upper band

    # Time context
    hour_of_day: int = 0
    day_of_week: int = 0
    minutes_since_open: int = 0

    # Portfolio context at signal time
    portfolio_heat: float = 0.0         # % of capital at risk
    cash_pct: float = 0.0
    open_positions: int = 0
    todays_pnl_pct: float = 0.0

    # Source performance context (rolling)
    source_win_rate_30d: float = 0.0    # how well this source has been doing
    source_signal_count_today: int = 0  # how many signals from this source today

    # Raw state vector (full 1560-dim for direct replay training)
    full_state_vector: List[float] = field(default_factory=list)

    # Outcome — filled in when trade closes
    outcome: Optional["TradeOutcome"] = None
    outcome_tagged: bool = False


@dataclass
class TradeOutcome:
    """
    What actually happened after the signal fired.
    This is the LABEL the AI learns from.
    """
    snapshot_id: str = ""
    trade_id: str = ""
    symbol: str = ""

    # Fill details
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    hold_minutes: int = 0

    # Results
    pnl_abs: float = 0.0
    pnl_pct: float = 0.0
    was_profitable: bool = False

    # Exit reason
    exit_reason: str = ""               # "stop_loss", "take_profit", "signal", "eod", "manual"
    max_favorable_excursion: float = 0.0  # best P&L seen during trade
    max_adverse_excursion: float = 0.0   # worst P&L seen during trade

    # What action should AI have taken?
    # 1=follow signal, 0=ignore signal
    optimal_action: int = 0
    reward_signal: float = 0.0          # direct reward value for RL training


@dataclass
class TrainingExample:
    """
    One complete labeled example ready for model training.
    state → action → reward mapping.
    """
    example_id: str = field(default_factory=lambda: str(uuid4()))
    snapshot_id: str = ""
    source: str = ""
    symbol: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    state_vector: List[float] = field(default_factory=list)   # full obs vector
    action_taken: int = 0                                      # what signal said to do
    reward: float = 0.0                                        # actual outcome
    next_state_vector: List[float] = field(default_factory=list)
    done: bool = False

    # Metadata for analysis
    pnl_pct: float = 0.0
    source_win_rate_context: float = 0.0
    was_profitable: bool = False


# ─── Signal Logger ────────────────────────────────────────────────────────────

class SignalOutcomeLogger:
    """
    Attaches to the signal pipeline and trade lifecycle.
    Every signal → snapshot → outcome → training example.
    """

    def __init__(
        self,
        supabase_client=None,
        buffer_dir: Path = Path("/data/kat/training_buffer"),
        source_stats_window_days: int = 30,
    ):
        self.supabase = supabase_client
        self.buffer_dir = buffer_dir
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache of open snapshots waiting for outcomes
        self._open_snapshots: Dict[str, MarketSnapshot] = {}

        # Rolling source performance stats
        self._source_stats: Dict[str, Dict] = {}

        logger.info("SignalOutcomeLogger initialized")

    # ─── Step 1: Snapshot when signal fires ───────────────────────────────────

    def on_signal_fired(
        self,
        signal: Dict,               # UnifiedSignal as dict
        price_bars: pd.DataFrame,   # last 60+ bars of OHLCV + indicators
        portfolio_state: Dict,      # current portfolio snapshot
    ) -> MarketSnapshot:
        """
        Called immediately when a signal arrives and passes Guardian.
        Captures everything about this moment in time.
        """
        snapshot = MarketSnapshot()
        snapshot.signal_id = signal.get("id", "")
        snapshot.source = signal.get("source", "")
        snapshot.source_strategy_id = signal.get("source_strategy_id", "")
        snapshot.symbol = signal.get("symbol", "")
        snapshot.signal_action = signal.get("action", "buy")
        snapshot.signal_confidence = float(signal.get("confidence", 0.0))
        snapshot.signal_urgency = signal.get("urgency", "normal")
        snapshot.fired_at = datetime.utcnow().isoformat()

        # Market features from price bars
        if not price_bars.empty and len(price_bars) >= 60:
            snapshot = self._extract_market_features(snapshot, price_bars)

        # Time context
        now = datetime.utcnow()
        snapshot.hour_of_day = now.hour
        snapshot.day_of_week = now.weekday()
        market_open = now.replace(hour=9, minute=30, second=0)
        snapshot.minutes_since_open = max(0, int((now - market_open).total_seconds() / 60))

        # Portfolio context
        snapshot.portfolio_heat = float(portfolio_state.get("portfolio_heat", 0.0))
        snapshot.cash_pct = float(portfolio_state.get("cash_pct", 1.0))
        snapshot.open_positions = int(portfolio_state.get("open_positions", 0))
        snapshot.todays_pnl_pct = float(portfolio_state.get("todays_pnl_pct", 0.0))

        # Source performance context
        src_stats = self._source_stats.get(snapshot.source, {})
        snapshot.source_win_rate_30d = src_stats.get("win_rate_30d", 0.5)
        snapshot.source_signal_count_today = src_stats.get("signals_today", 0)

        # Register as open (waiting for outcome)
        self._open_snapshots[snapshot.snapshot_id] = snapshot

        # Persist to Supabase
        self._save_snapshot(snapshot)

        logger.info(
            f"Snapshot created | {snapshot.source} → {snapshot.symbol} "
            f"| conf={snapshot.signal_confidence:.2f} "
            f"| RSI={snapshot.rsi_14:.1f} "
            f"| vol_ratio={snapshot.volume_ratio:.1f}x"
        )
        return snapshot

    # ─── Step 2: Tag outcome when trade closes ────────────────────────────────

    def on_trade_closed(
        self,
        snapshot_id: str,
        trade_result: Dict,
        next_price_bars: Optional[pd.DataFrame] = None,
        next_portfolio_state: Optional[Dict] = None,
    ) -> Optional[TrainingExample]:
        """
        Called when a paper trade closes (stop, take-profit, signal, EOD).
        Tags the outcome to the snapshot and creates a training example.
        """
        snapshot = self._open_snapshots.get(snapshot_id)
        if snapshot is None:
            # Try loading from Supabase
            snapshot = self._load_snapshot(snapshot_id)
            if snapshot is None:
                logger.warning(f"Snapshot {snapshot_id} not found — cannot tag outcome")
                return None

        # Build outcome
        entry_time = trade_result.get("entry_time", "")
        exit_time = trade_result.get("exit_time", datetime.utcnow().isoformat())
        hold_minutes = self._calc_hold_minutes(entry_time, exit_time)
        pnl_pct = float(trade_result.get("pnl_pct", 0.0))

        outcome = TradeOutcome(
            snapshot_id=snapshot_id,
            trade_id=trade_result.get("trade_id", ""),
            symbol=snapshot.symbol,
            entry_price=float(trade_result.get("entry_price", 0.0)),
            exit_price=float(trade_result.get("exit_price", 0.0)),
            entry_time=entry_time,
            exit_time=exit_time,
            hold_minutes=hold_minutes,
            pnl_abs=float(trade_result.get("pnl_abs", 0.0)),
            pnl_pct=pnl_pct,
            was_profitable=pnl_pct > 0,
            exit_reason=trade_result.get("exit_reason", "unknown"),
            max_favorable_excursion=float(trade_result.get("mfe", 0.0)),
            max_adverse_excursion=float(trade_result.get("mae", 0.0)),
        )

        # Compute reward signal for RL
        # Reward = risk-adjusted return, penalizing:
        #   - losses more than proportional (loss aversion baked in)
        #   - trades held too long (opportunity cost)
        #   - signals from low-performing sources
        outcome.reward_signal = self._compute_reward(outcome, snapshot)

        # Was it right to follow the signal?
        outcome.optimal_action = 1 if pnl_pct > -0.005 else 0  # 0.5% grace

        # Attach to snapshot
        snapshot.outcome = outcome
        snapshot.outcome_tagged = True

        # Update source statistics
        self._update_source_stats(snapshot.source, outcome)

        # Build training example
        example = self._build_training_example(snapshot, next_price_bars, next_portfolio_state)

        # Persist
        self._save_outcome(outcome)
        self._save_training_example(example)

        # Remove from open cache
        self._open_snapshots.pop(snapshot_id, None)

        logger.info(
            f"Outcome tagged | {snapshot.source} → {snapshot.symbol} "
            f"| P&L={pnl_pct:+.2%} | reward={outcome.reward_signal:+.3f} "
            f"| exit={outcome.exit_reason}"
        )
        return example

    # ─── Reward Engineering ───────────────────────────────────────────────────

    def _compute_reward(self, outcome: TradeOutcome, snapshot: MarketSnapshot) -> float:
        """
        Multi-factor reward that teaches the agent what "good" looks like.
        
        Factors:
          + P&L (scaled, asymmetric — losses hurt more)
          + Quick profitable exits (time efficiency)
          + Source quality bonus (high win-rate source + profit = strong signal)
          - Following low-confidence signals into losses
          - Holding too long
        """
        pnl = outcome.pnl_pct

        # Base: asymmetric P&L (losses weighted 1.5x to build risk aversion)
        if pnl >= 0:
            base_reward = pnl * 100
        else:
            base_reward = pnl * 150  # losses hurt more

        # Time efficiency bonus: profitable trades that close quickly are better
        if outcome.was_profitable and outcome.hold_minutes < 120:
            base_reward *= 1.2
        elif outcome.hold_minutes > 480:  # held all day with small gain
            base_reward *= 0.8

        # Source quality context
        # If source has high win rate AND this was profitable → strong positive
        # If source has high win rate AND this was a loss → penalize more (should have worked)
        src_wr = snapshot.source_win_rate_30d
        if src_wr > 0.60:
            base_reward *= (1.3 if outcome.was_profitable else 1.2)  # amplify both
        elif src_wr < 0.45:
            base_reward *= 0.7  # discount rewards from underperforming source

        # Confidence calibration
        # High confidence + loss → penalize (agent should learn this signal was misleading)
        if snapshot.signal_confidence > 0.75 and not outcome.was_profitable:
            base_reward -= 0.5

        # Market condition context bonus
        # Profitable trade that went WITH the trend → well done
        trend_aligned = (
            (snapshot.market_trend == "up" and snapshot.signal_action == "buy")
            or (snapshot.market_trend == "down" and snapshot.signal_action == "sell")
        )
        if trend_aligned and outcome.was_profitable:
            base_reward *= 1.1

        return round(float(base_reward), 4)

    # ─── Market Feature Extraction ────────────────────────────────────────────

    def _extract_market_features(
        self, snapshot: MarketSnapshot, bars: pd.DataFrame
    ) -> MarketSnapshot:
        """Extract key market features from price bars."""
        bars = bars.copy()
        bars.columns = [c.lower() for c in bars.columns]

        close = bars["close"]
        last = close.iloc[-1]
        snapshot.price_at_signal = float(last)

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        snapshot.rsi_14 = float(rsi)

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()
        snapshot.macd_signal = float((macd - signal_line).iloc[-1] / last)

        # ATR %
        h, l, c = bars["high"], bars["low"], close.shift(1)
        tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        snapshot.atr_pct = float(atr / last)

        # Volume ratio
        if "volume" in bars.columns:
            vol_avg = bars["volume"].rolling(20).mean().iloc[-1]
            vol_now = bars["volume"].iloc[-1]
            snapshot.volume_ratio = float(vol_now / (vol_avg + 1))

        # Bollinger band position
        bb_mid = close.rolling(20).mean().iloc[-1]
        bb_std = close.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        if bb_upper > bb_lower:
            snapshot.bb_position = float((last - bb_lower) / (bb_upper - bb_lower))

        # Trend
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else sma20
        if last > sma20 > sma50:
            snapshot.market_trend = "up"
        elif last < sma20 < sma50:
            snapshot.market_trend = "down"
        else:
            snapshot.market_trend = "sideways"

        # Compact feature vector for quick comparisons (25 values)
        snapshot.market_features = [
            snapshot.rsi_14 / 100,
            snapshot.macd_signal,
            snapshot.atr_pct,
            snapshot.volume_ratio / 5,
            snapshot.bb_position,
            (last / close.rolling(5).mean().iloc[-1] - 1),
            (last / close.rolling(10).mean().iloc[-1] - 1),
            (last / close.rolling(20).mean().iloc[-1] - 1),
            (last / close.rolling(50).mean().iloc[-1] - 1) if len(close) >= 50 else 0,
            float(close.pct_change().iloc[-1]),
            float(close.pct_change(5).iloc[-1]),
            float(close.pct_change(10).iloc[-1]),
            float(close.rolling(20).std().iloc[-1] / last),
            1 if snapshot.market_trend == "up" else (-1 if snapshot.market_trend == "down" else 0),
            snapshot.signal_confidence,
            1 if snapshot.signal_action == "buy" else 0,
            snapshot.hour_of_day / 24,
            snapshot.day_of_week / 5,
            snapshot.portfolio_heat,
            snapshot.cash_pct,
            snapshot.source_win_rate_30d,
            snapshot.todays_pnl_pct,
            float(snapshot.open_positions / 10),
            snapshot.signal_urgency == "immediate",
            snapshot.minutes_since_open / 390,  # normalized to trading day
        ]

        return snapshot

    # ─── Training Example Builder ─────────────────────────────────────────────

    def _build_training_example(
        self,
        snapshot: MarketSnapshot,
        next_bars: Optional[pd.DataFrame],
        next_portfolio: Optional[Dict],
    ) -> TrainingExample:
        """Convert snapshot + outcome into a training example for the RL agent."""
        outcome = snapshot.outcome

        # State: market features + portfolio + signal context
        state = list(snapshot.market_features) + [
            snapshot.portfolio_heat,
            snapshot.cash_pct,
            snapshot.source_win_rate_30d,
            snapshot.todays_pnl_pct,
            snapshot.signal_confidence,
            1.0 if snapshot.signal_action == "buy" else 0.0,
        ]

        # Use full state vector if available
        if snapshot.full_state_vector:
            state = snapshot.full_state_vector

        # Action: 1=buy, 2=sell (maps to env action space)
        action = 1 if snapshot.signal_action == "buy" else 2

        return TrainingExample(
            snapshot_id=snapshot.snapshot_id,
            source=snapshot.source,
            symbol=snapshot.symbol,
            state_vector=state,
            action_taken=action,
            reward=outcome.reward_signal,
            pnl_pct=outcome.pnl_pct,
            source_win_rate_context=snapshot.source_win_rate_30d,
            was_profitable=outcome.was_profitable,
            done=False,
        )

    # ─── Source Stats ─────────────────────────────────────────────────────────

    def _update_source_stats(self, source: str, outcome: TradeOutcome):
        """Rolling performance tracker per signal source."""
        if source not in self._source_stats:
            self._source_stats[source] = {
                "trades": [],
                "win_rate_30d": 0.5,
                "signals_today": 0,
                "total_pnl": 0.0,
            }

        stats = self._source_stats[source]
        now = datetime.utcnow()
        stats["trades"].append({
            "time": now.isoformat(),
            "pnl_pct": outcome.pnl_pct,
            "profitable": outcome.was_profitable,
        })

        # Keep only last 30 days
        cutoff = (now - timedelta(days=30)).isoformat()
        stats["trades"] = [t for t in stats["trades"] if t["time"] > cutoff]

        # Recalculate win rate
        if stats["trades"]:
            wins = sum(1 for t in stats["trades"] if t["profitable"])
            stats["win_rate_30d"] = wins / len(stats["trades"])
            stats["total_pnl"] = sum(t["pnl_pct"] for t in stats["trades"])

        stats["signals_today"] = sum(
            1 for t in stats["trades"]
            if t["time"][:10] == now.strftime("%Y-%m-%d")
        )

    def get_source_leaderboard(self) -> List[Dict]:
        """Rank signal sources by 30-day performance."""
        lb = []
        for source, stats in self._source_stats.items():
            n = len(stats["trades"])
            lb.append({
                "source": source,
                "n_trades_30d": n,
                "win_rate_30d": round(stats["win_rate_30d"], 3),
                "total_pnl_30d": round(stats["total_pnl"], 4),
                "signals_today": stats["signals_today"],
            })
        return sorted(lb, key=lambda x: x["win_rate_30d"], reverse=True)

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _save_snapshot(self, snapshot: MarketSnapshot):
        """Save to Supabase + local buffer."""
        try:
            data = asdict(snapshot)
            data.pop("outcome", None)  # save separately
            data["market_features"] = json.dumps(data["market_features"])
            data["full_state_vector"] = json.dumps(data["full_state_vector"])

            if self.supabase:
                self.supabase.table("signal_snapshots").insert(data).execute()

            # Local JSONL buffer (always write, even if Supabase is down)
            path = self.buffer_dir / f"snapshots_{datetime.utcnow():%Y%m%d}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(data) + "\n")

        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    def _save_outcome(self, outcome: TradeOutcome):
        """Save trade outcome to Supabase."""
        try:
            if self.supabase:
                self.supabase.table("signal_outcomes").insert(asdict(outcome)).execute()

            path = self.buffer_dir / f"outcomes_{datetime.utcnow():%Y%m%d}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(asdict(outcome)) + "\n")

        except Exception as e:
            logger.error(f"Failed to save outcome: {e}")

    def _save_training_example(self, example: TrainingExample):
        """Save completed training example to buffer."""
        try:
            path = self.buffer_dir / f"examples_{datetime.utcnow():%Y%m%d}.jsonl"
            with open(path, "a") as f:
                f.write(json.dumps(asdict(example)) + "\n")

            logger.debug(f"Training example saved: reward={example.reward:+.3f}")

        except Exception as e:
            logger.error(f"Failed to save training example: {e}")

    def _load_snapshot(self, snapshot_id: str) -> Optional[MarketSnapshot]:
        """Try loading snapshot from Supabase if not in memory."""
        if not self.supabase:
            return None
        try:
            result = self.supabase.table("signal_snapshots") \
                .select("*") \
                .eq("snapshot_id", snapshot_id) \
                .execute()
            if result.data:
                d = result.data[0]
                d["market_features"] = json.loads(d.get("market_features", "[]"))
                d["full_state_vector"] = json.loads(d.get("full_state_vector", "[]"))
                return MarketSnapshot(**{k: v for k, v in d.items() if k in MarketSnapshot.__dataclass_fields__})
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
        return None

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_hold_minutes(entry_time: str, exit_time: str) -> int:
        try:
            t0 = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
            return max(0, int((t1 - t0).total_seconds() / 60))
        except Exception:
            return 0
