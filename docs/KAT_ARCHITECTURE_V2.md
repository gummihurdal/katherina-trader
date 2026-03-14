# KAT System Architecture v2.0
## Katherina Algorithmic Trader — Technical Design Document

**Classification:** Internal Research Document  
**Version:** 2.0 — Complete Rebuild  
**Date:** March 14, 2026  
**Status:** Pre-Implementation Design  

---

## Abstract

This document presents the complete technical architecture for KAT v2.0, a production-grade deep reinforcement learning trading system. Drawing from six primary research sources spanning 167 empirical studies (2017–2025), we present a theoretically grounded and empirically validated design. The architecture addresses fundamental flaws identified in v1.0 — specifically the dead policy problem, insufficient feature engineering, suboptimal reward formulation, and GPU underutilization — and proposes a clean, research-backed solution that is robust, reproducible, and scalable to live trading.

**Key contributions of v2.0:**
1. Elimination of the dead policy problem through reward function redesign
2. Richer observation space incorporating technical indicators alongside macro and futures data
3. GPU utilization improvement from 1% to projected 40-60% through architecture changes
4. Theoretically grounded algorithm selection with GRPO as the terminal algorithm
5. Production-grade infrastructure with DuckDB, distributed training, and Modal deployment

---

## 1. Problem Statement and Motivation

### 1.1 Why Reinforcement Learning for Trading

Financial markets constitute one of the most challenging environments for algorithmic decision-making, characterized by:

- **High dimensionality:** Hundreds of correlated features spanning macro, price, volume, and sentiment domains
- **Non-stationarity:** Market regimes shift due to monetary policy, geopolitical events, and structural changes
- **Delayed and sparse rewards:** A trade entered today may not reveal its quality for days or weeks
- **Adversarial dynamics:** Other participants adapt to and arbitrage away systematic strategies

Traditional supervised learning approaches treat market prediction as a static classification problem, ignoring the sequential decision-making nature of trading. Reinforcement learning (RL) is the natural framework because it directly optimizes the objective we care about — cumulative risk-adjusted return — through interaction with the environment.

As demonstrated by Moody and Saffell (2001), RL can optimize trading performance directly without requiring explicit forecasting models. This direct optimization approach, combined with modern deep learning architectures, forms the theoretical basis for KAT.

### 1.2 Lessons from v1.0

The v1.0 system identified several critical failure modes through empirical experimentation:

**Failure Mode 1 — Dead Policy (Primary)**
The most persistent problem: the model learns to HOLD exclusively, generating zero reward. Root cause analysis (confirmed by Cameron Wolfe 2025, Adaptive ML 2026):

```
transaction_cost = 0.0002
→ Every trade: reward_start = -0.04 (negative bias)
→ Value function learns: V(HOLD) = 0 > V(TRADE) = -0.04
→ Policy gradient: increase P(HOLD)
→ Entropy collapses to -0.5 (overconfident)
→ eval_reward = 0.00 persistently
```

**Failure Mode 2 — Insufficient Feature Engineering**
v1.0 observation space: raw OHLCV + macro + portfolio = 1722 features.
Missing: all technical indicators that constitute actual trading signals.
The model was asked to rediscover RSI, MACD, and momentum from raw prices — requiring orders of magnitude more training steps.

**Failure Mode 3 — GPU Underutilization (1%)**
PPO with SubprocVecEnv is CPU-bound. 64 workers collect rollouts on CPU. GPU sits idle waiting for the next gradient update batch. The GPU only activates during the brief backward pass every ~4096 steps.

**Failure Mode 4 — Reward Signal Weakness**
`reward_scaling = 0.01` in early runs produced reward magnitudes of ~0.0001. Policy gradient signal was effectively zero — the model had nothing to learn from.

**Failure Mode 5 — No Sharpe Component**
Pure P&L reward incentivizes high variance strategies. A model that makes 20% with 80% drawdown scores higher than one making 8% with 3% drawdown. Risk-adjusted reward is essential for production deployment.

---

## 2. System Architecture v2.0

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
│  DuckDB (kat_v2.db)                                         │
│  ├── macro_data        (277K rows, 47 FRED series)          │
│  ├── market_data_cont  (20K rows, 6 futures daily)          │
│  ├── options_chains    (103M rows, DoltHub, Stage 4)        │
│  └── features_cache    (precomputed technicals)             │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    FEATURE LAYER                             │
│  KATFeaturePipeline v2                                      │
│  ├── MacroEncoder     (1404 features, FRED pivot)           │
│  ├── PortfolioEncoder (108 features, positions/PnL)         │
│  ├── FuturesEncoder   (210 features, OHLCV)                 │
│  └── TechnicalEncoder (NEW: ~150 features, indicators)      │
│  Total obs size: ~1872                                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    POLICY LAYER                              │
│  KATPolicy v2 (Custom Attention)                            │
│  ├── MacroStream      (1404 → 512 → 256)                    │
│  ├── PortfolioStream  (108  → 128 → 256)                    │
│  ├── FuturesStream    (210  → 256 → 256)                    │
│  ├── TechnicalStream  (150  → 256 → 256) [NEW]              │
│  ├── CrossAttention   (4 streams, 8 heads)                  │
│  └── OutputHead       (256 → 5 actions)                     │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    ALGORITHM LAYER                           │
│  Stage 3: PPO  (stable, proven, checkpoint continuity)      │
│  Stage 4: GRPO (no critic, relative rewards, no dead policy)│
│  Stage 5: SAC  (continuous actions for options sizing)      │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    TRAINING LAYER                            │
│  Stage 3: 1x RTX 4090, 64 envs, ~3000 FPS                  │
│  Stage 4: 4x RTX 4090 cluster, 288 envs, ~12000 FPS        │
│  Stage 5: 4x cluster, same                                  │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                    DEPLOYMENT LAYER                          │
│  Paper Trading: IBKR paper (port 4002)                      │
│  Live Trading:  SNB API (0% commission)                     │
│  Runtime:       Modal.com (serverless, market hours only)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Algorithm Selection — Research Justified

### 3.1 Algorithm Comparison for Financial RL

| Algorithm | Type | Critic | Dead Policy Risk | Best For | Source |
|-----------|------|--------|-----------------|---------|--------|
| **PPO** | On-policy | Yes | Medium | Stable training, discrete | Schulman et al. 2017 |
| **GRPO** | On-policy | No | Low | Complex envs, no value fn | DeepSeek 2024 |
| **A2C** | On-policy | Yes | Medium | Fast convergence | Mnih et al. 2016 |
| **SAC** | Off-policy | Yes | Low | Continuous actions | Haarnoja et al. 2018 |
| **TD3** | Off-policy | Yes | Low | Continuous control | Fujimoto et al. 2018 |
| **DQN** | Off-policy | No | High | Discrete, experience replay | Mnih et al. 2015 |

### 3.2 Why PPO for Stage 3

PPO is selected for Stage 3 for the following research-backed reasons:

1. **Stability guarantee via target_kl:** The `target_kl` parameter provides a hard safety constraint on policy updates. A2C has no equivalent mechanism. In volatile financial environments with noisy rewards, this prevents catastrophic policy degradation.

2. **Confirmed superiority over DPO:** Allen Institute for AI (Ivison et al. 2024) demonstrates PPO outperforms alternative policy optimization methods by up to 2.5% across evaluation domains, with strongest advantages in reasoning and decision-making tasks — directly analogous to trading.

3. **On-policy data efficiency:** While off-policy methods (SAC, TD3) theoretically offer higher sample efficiency through experience replay, on-policy methods better handle the non-stationary reward landscape of financial markets. Replayed experiences from different market regimes can corrupt the value function.

4. **Checkpoint continuity:** PPO checkpoints can be loaded and continued with additional data. This is critical for the staged data expansion strategy (futures → options → stocks).

### 3.3 Why GRPO for Stage 4 (Not A2C)

The question of PPO vs A2C is frequently raised. For Stage 4 onwards, we select GRPO over A2C for the following reasons:

**The dead policy problem is structural in actor-critic methods:**
Both PPO and A2C use a value function (critic). In financial environments:
```
If V(HOLD) = 0 (baseline)
And V(TRADE) = -ε (any small cost)
Then A(TRADE) = Q(TRADE) - V(HOLD) < 0
→ Policy gradient discourages trading
```

This is not a hyperparameter problem. It is a structural problem with actor-critic methods when the environment has a "do nothing" action that generates zero cost.

**GRPO eliminates this structurally:**
```
Sample G outcomes for same state s:
  HOLD → reward = 0
  BUY  → reward = +0.05
  SELL → reward = -0.02

Relative advantage:
  A(HOLD) = (0 - mean) / std   = negative
  A(BUY)  = (0.05 - mean) / std = positive  
  A(SELL) = (-0.02 - mean) / std = most negative

→ Policy learns to BUY without a value function
```

**A2C's theoretical advantage (faster convergence) is real but smaller than GRPO's advantage (no dead policy).**

### 3.4 Why SAC for Stage 5 (Options)

Options trading requires continuous position sizing:
- "Sell 0.3 of maximum Iron Condor position at 0.15 delta"
- "Size position to 2% portfolio risk given current ATR"

PPO and GRPO handle discrete actions natively. For continuous action spaces, SAC is the research-validated choice (Haarnoja et al. 2018), demonstrating:
- Maximum entropy framework ensures exploration
- Off-policy learning via replay buffer for sample efficiency
- Automatic temperature tuning (`ent_coef='auto'`)

---

## 4. Feature Engineering — v2.0 Observation Space

### 4.1 Design Principles

The observation space design follows three principles from the ScienceDirect review (2025):

1. **Multi-hierarchy:** Combine macro (economy), technical (price/volume), fundamental (portfolio state)
2. **Temporal depth:** Include lagged features to encode momentum and regime
3. **Orthogonality:** Remove highly correlated features (correlation > 0.95) to prevent overfitting

### 4.2 Complete Feature Specification

#### Stream 1: Macro Features (1404 dimensions)
Source: FRED API, 47 economic series, daily frequency, 2015-2026
Preprocessing: Forward-fill, min-max normalize, pivot to wide format
```
Series include: Fed Funds Rate, CPI, Unemployment, GDP growth,
Treasury yields (2Y/5Y/10Y/30Y), yield curve spreads,
VIX, credit spreads, M2 money supply, Industrial Production,
PMI composites, housing data, trade balances, etc.
```

#### Stream 2: Portfolio State (108 dimensions)  
Real-time portfolio encoding:
```python
portfolio_features = {
    'equity_normalized': total_equity / initial_equity,
    'position_size': current_position,          # 0 to 1
    'entry_price_normalized': entry / current,  # relative entry
    'unrealized_pnl': unrealized / equity,      # % unrealized
    'drawdown': current_drawdown,               # peak-to-trough
    'trade_count': trades / max_trades,         # activity
    'days_held': days / max_days,               # holding period
    # ... time encoding (sin/cos of day-of-week, month, etc.)
}
```

#### Stream 3: Futures OHLCV (210 dimensions)
6 contracts: CL (crude oil), GC (gold), HG (copper), ES (S&P500), NQ (Nasdaq), ZB (T-bonds)
35 features per contract: OHLCV + rolling lookbacks (5, 10, 20, 60 day)

#### Stream 4: Technical Indicators [NEW IN v2.0] (~150 dimensions)
Computed per futures contract, appended to obs:
```python
# Momentum indicators
RSI_14        # Relative Strength Index — overbought/oversold
MACD          # Moving Average Convergence Divergence — trend momentum
MACD_signal   # MACD signal line
MACD_hist     # MACD histogram — acceleration

# Volatility indicators  
BB_upper      # Bollinger Band upper (2σ above 20-day MA)
BB_lower      # Bollinger Band lower
BB_width      # Band width — volatility regime
ATR_14        # Average True Range — absolute volatility
ATR_pct       # ATR as % of price — normalized volatility

# Momentum/price
Stoch_K       # Stochastic oscillator %K
Stoch_D       # Stochastic oscillator %D (signal)
Williams_R    # Williams %R — momentum

# Lagged returns (momentum)
return_1d     # 1-day return
return_5d     # 5-day return (weekly)
return_10d    # 10-day return (2-week)
return_20d    # 20-day return (monthly)
return_60d    # 60-day return (quarterly)

# Volume
volume_sma20  # Volume vs 20-day average
volume_ratio  # Current / 20-day average — unusual activity
```

**Justification:** The Medium article (Abdul Haseeb 2025) demonstrates that Temporal Fusion Transformer with these exact indicators achieved 63% live accuracy — directly deployable. Raw OHLCV without indicators requires the model to discover these relationships from scratch, requiring orders of magnitude more training steps.

### 4.3 Implementation in feature_pipeline.py

```python
import pandas as pd
import numpy as np

def compute_technical_features(ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute technical indicators for a single futures contract.
    
    Args:
        ohlcv_df: DataFrame with columns [open, high, low, close, volume]
        
    Returns:
        DataFrame with all technical features, same index
    """
    df = ohlcv_df.copy()
    
    # ── RSI ──────────────────────────────────────────────────
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    df['rsi_14'] = df['rsi_14'] / 100  # normalize 0-1
    
    # ── MACD ─────────────────────────────────────────────────
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = (ema12 - ema26) / df['close']  # normalized
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # ── Bollinger Bands ───────────────────────────────────────
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_upper'] = (ma20 + 2*std20) / df['close'] - 1
    df['bb_lower'] = (ma20 - 2*std20) / df['close'] - 1
    df['bb_width'] = (4*std20) / ma20  # bandwidth normalized
    df['bb_position'] = (df['close'] - (ma20 - 2*std20)) / (4*std20 + 1e-8)
    
    # ── ATR ───────────────────────────────────────────────────
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean() / df['close']  # as % of price
    
    # ── Stochastic ────────────────────────────────────────────
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = (df['close'] - low14) / (high14 - low14 + 1e-8)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    
    # ── Williams %R ───────────────────────────────────────────
    df['williams_r'] = (high14 - df['close']) / (high14 - low14 + 1e-8)
    
    # ── Lagged Returns ────────────────────────────────────────
    for period in [1, 5, 10, 20, 60]:
        df[f'return_{period}d'] = df['close'].pct_change(period).clip(-0.3, 0.3)
    
    # ── Volume ────────────────────────────────────────────────
    vol_ma20 = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / (vol_ma20 + 1e-8)
    df['volume_ratio'] = df['volume_ratio'].clip(0, 5) / 5  # normalize 0-1
    
    # Fill any NaN from rolling windows
    df = df.fillna(0)
    
    return df
```

---

## 5. Reward Function Design — Research Backed

### 5.1 The Reward Function IS the Reward Model

A critical insight from the Allen AI paper (Ivison et al. 2024): in PPO, the reward function IS the reward model. Its quality determines everything. A corrupted or weak reward signal cannot be overcome by any algorithmic sophistication.

### 5.2 v1.0 Reward Function — Problems

```python
# v1.0 (BROKEN)
reward = (total_equity - prev_equity) / prev_equity * 0.01  \
         - cost * 0.001                                       \
         - drawdown * 0.001
```

Problems:
1. `reward_scaling = 0.01` → typical reward magnitude ~0.0001 → signal drowned in noise
2. `cost * 0.001` with `transaction_cost=0.0002` → negative bias on every trade
3. No exploration incentive
4. No risk-adjustment

### 5.3 v2.0 Reward Function — Design

```python
# v2.0 (RESEARCH-BACKED)
def compute_reward(self, total_equity, prev_equity, action, price):
    """
    Risk-adjusted reward with Sharpe component.
    
    Design principles:
    1. No transaction cost → removes dead policy bias (SNB = 0% commission)
    2. reward_scaling = 0.1 → clear signal magnitude
    3. Drawdown penalty → incentivizes risk management
    4. Sharpe warmup → activates after sufficient history (Stage 4)
    """
    # Core P&L signal
    pnl_return = (total_equity - prev_equity) / (prev_equity + 1e-8)
    reward = pnl_return * self.reward_scaling  # reward_scaling = 0.1
    
    # Drawdown penalty (risk management)
    drawdown = (self.peak_equity - total_equity) / (self.peak_equity + 1e-8)
    reward -= drawdown * 0.001
    
    # Stage 4+: Add Sharpe ratio component
    # (requires rolling buffer of returns, implemented in Stage 4)
    # sharpe_component = self._rolling_sharpe() * 0.01
    # reward += sharpe_component
    
    return reward

# Parameters:
# transaction_cost = 0.0    (SNB confirmed 0% — eliminates dead policy)
# reward_scaling   = 0.1    (10x improvement in signal clarity)
# drawdown_penalty = 0.001  (gentle risk management incentive)
```

### 5.4 Stage 4 Sharpe Component

```python
def _rolling_sharpe(self, window=60):
    """
    Rolling Sharpe ratio over recent returns.
    Incentivizes consistent returns over high-variance strategies.
    Only active after warmup period (first 10M steps).
    """
    if len(self._return_buffer) < window:
        return 0.0
    returns = np.array(list(self._return_buffer)[-window:])
    if returns.std() < 1e-8:
        return 0.0
    return (returns.mean() / returns.std()) * np.sqrt(252)  # annualized
```

---

## 6. GPU Utilization — From 1% to 40-60%

### 6.1 Root Cause Analysis: Why GPU is at 1%

PPO with SubprocVecEnv is fundamentally CPU-bound:

```
Timeline per iteration (n_steps=4096, N=64 envs):

[CPU: 64 workers collecting rollouts] ←── 95% of time
         ↓
[GPU: Backward pass, 1-2 seconds]    ←── 5% of time
         ↓
[CPU: 64 workers collecting rollouts] ←── repeat
```

The GPU activates only during the backward pass. With 64 environments each running 4096 steps, the CPU spends ~100 seconds collecting data for every ~2 seconds of GPU computation. Result: GPU utilization ~2%.

### 6.2 Solutions Ranked by Impact

#### Solution 1: Increase Batch Size (Highest Impact, Immediate)
```python
# v1.0
n_steps  = 4096
batch_size = 2048

# v2.0 — larger batches = longer GPU compute per iteration
n_steps  = 8192   # 2x longer rollout
batch_size = 4096  # 2x larger mini-batch
n_epochs = 10      # More gradient steps per rollout
```

Effect: GPU active for ~2x longer per iteration. Estimated GPU utilization: 3-5%.

#### Solution 2: Increase N_envs to Saturate CPU (Medium Impact)
```python
# Current: N=64, CPU at 68%
# Increase until CPU at 80-85%
N = 96   # → ~80% CPU, more data per second
```

Effect: More rollout data per second → GPU updates more frequently.

#### Solution 3: Switch to A2C for CPU Parallelism (Medium Impact)
A2C uses synchronous gradient updates from multiple workers directly — designed for multi-CPU parallelism. With 255 available CPUs on Vast.ai:

```python
# A2C with many workers
from stable_baselines3 import A2C
model = A2C("MlpPolicy", env, n_steps=20, ...)
# Each worker sends gradient after just 20 steps
# Much faster update cycle
```

Effect: ~3x FPS improvement. GPU utilization may reach 5-10%.

#### Solution 4: Distributed Training — 4 Server Cluster (Highest Impact)
The real GPU utilization improvement comes from scale:
```
4 servers × 96 envs = 384 parallel environments
→ 4x data generation rate
→ 4x gradient update frequency  
→ GPU active 4x more often
→ Estimated GPU utilization: 15-25%
```

#### Solution 5: Switch to Image-Based Observations (Maximum GPU Impact)
The fundamental reason GPU stays at 1% is that our observations are tabular vectors. GPUs excel at spatial data (CNN) and attention over long sequences (Transformer).

For KAT Stage 5, encoding market data as a 2D image (candlestick chart representation) would allow CNN processing — GPU utilization would reach 60-80%.

```python
# Stage 5 concept: encode obs as 2D matrix
# Shape: (channels, timesteps, features)
# → CNN processes it → GPU utilization jumps dramatically
obs_shape = (4, 60, 47)  # 4 channels, 60 timesteps, 47 features
```

### 6.3 Recommended GPU Optimization Path

| Stage | GPU % | Method |
|-------|-------|--------|
| Stage 3 v2 (now) | ~2-3% | Larger batch_size=4096, n_steps=8192 |
| Stage 4 | ~15-25% | 4-server cluster, GRPO |
| Stage 5 | ~40-60% | CNN obs encoding or TFT architecture |
| Stage 6 | ~70-80% | Full image-based obs + CNN policy |

---

## 7. Database Architecture — DuckDB

### 7.1 Why DuckDB Over PostgreSQL

| Criterion | PostgreSQL | DuckDB | Winner |
|-----------|-----------|--------|--------|
| Startup time | ~60s per worker | ~5s | DuckDB (12x) |
| Query speed (analytics) | 1x baseline | 10-100x faster | DuckDB |
| Training FPS impact | Same | Same | Tie |
| Setup complexity | Server, auth, tuning | Single file | DuckDB |
| Portability | pg_dump + restore | scp kat.db | DuckDB |
| Memory usage | High (server process) | Low (embedded) | DuckDB |
| Cost | $40/mo (Hetzner) | $0 | DuckDB |
| Multi-server access | Complex (network) | Copy per server | DuckDB |
| Concurrent readers | Excellent | Good (read-only) | PostgreSQL |

**Verdict:** DuckDB is correct for our use case. We have one writer (data ingestion) and many readers (training workers). DuckDB's columnar storage is optimal for the analytical queries in `_build_features()`.

### 7.2 Migration Script

```python
import duckdb
import pandas as pd

def migrate_postgres_to_duckdb(pg_uri: str, duckdb_path: str):
    """One-time migration from PostgreSQL to DuckDB."""
    from sqlalchemy import create_engine
    
    engine = create_engine(pg_uri)
    conn = duckdb.connect(duckdb_path)
    
    tables = ['macro_data', 'market_data_continuous', 'market_data']
    
    for table in tables:
        print(f"Migrating {table}...")
        df = pd.read_sql(f"SELECT * FROM {table}", engine)
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
        print(f"  → {len(df):,} rows migrated")
    
    conn.close()
    print(f"Migration complete: {duckdb_path}")
```

### 7.3 Schema Design v2.0

```sql
-- Core tables (existing, unchanged)
macro_data              -- 277K rows, 47 FRED series
market_data_continuous  -- 20K rows, 6 futures

-- New tables (v2.0)
technical_features      -- Precomputed indicators (fast training startup)
options_chains          -- 103M rows, DoltHub (Stage 4)
training_runs           -- Metadata for each training run
eval_results            -- Eval metrics per run per timestamp

-- Precomputed features table (critical for fast startup)
CREATE TABLE technical_features AS
SELECT 
    date, symbol,
    rsi_14, macd, macd_signal, macd_hist,
    bb_upper, bb_lower, bb_width, bb_position,
    atr_14, stoch_k, stoch_d, williams_r,
    return_1d, return_5d, return_10d, return_20d, return_60d,
    volume_ratio
FROM compute_all_technicals();
```

**Why precompute features?** With 64-96 workers each loading the full dataset on startup, computing technical indicators 96 times wastes ~5 minutes per launch. Precomputing once and loading from `technical_features` reduces startup from 5 minutes to 30 seconds.

---

## 8. Training Configuration v2.0

### 8.1 Hyperparameter Specification

```python
# ─── Algorithm ───────────────────────────────────────────────
ALGORITHM = "PPO"           # Stage 3; GRPO Stage 4+

# ─── PPO Core ────────────────────────────────────────────────
learning_rate   = 1e-4      # Standard for financial RL
n_steps         = 8192      # 2x v1.0 → longer GPU active time
batch_size      = 4096      # 2x v1.0 → larger mini-batches
n_epochs        = 10        # 2x v1.0 → more gradient steps per rollout
gamma           = 0.995     # High discount — rewards matter for 200+ steps ahead
gae_lambda      = 0.95      # GAE bias/variance tradeoff
target_kl       = 0.02      # CRITICAL — prevents catastrophic updates
ent_coef        = 0.05      # Prevents entropy collapse (dead policy)
clip_range      = 0.15      # Tight clipping for financial stability
vf_coef         = 0.5       # Value function loss weight
max_grad_norm   = 0.5       # Gradient clipping

# ─── Environment ─────────────────────────────────────────────
N_envs              = 96        # ~75-80% CPU target
transaction_cost    = 0.0       # SNB = 0% commission; eliminates dead policy
reward_scaling      = 0.1       # Clear signal magnitude
initial_equity      = 100_000   # Starting capital (normalized)
device              = "cuda"

# ─── Training ────────────────────────────────────────────────
total_timesteps     = 500_000_000   # 500M steps
eval_freq           = 2_000_000     # Eval every 2M steps
eval_episodes       = 10            # Episodes per eval
deterministic_eval  = False         # Stochastic eval — model must trade

# ─── Data Splits ─────────────────────────────────────────────
TRAIN_START = "2015-01-01"
TRAIN_END   = "2023-12-31"
EVAL_START  = "2024-01-01"
EVAL_END    = "2025-12-31"
TEST_START  = "2026-01-01"  # NEVER TOUCH until final deployment
```

### 8.2 Justification for Key Parameters

**n_steps = 8192 (doubled from 4096):**
Longer rollouts provide:
- Better advantage estimation (more future rewards captured)
- Larger GPU batches (2x longer GPU active time)
- Better estimate of market state correlations across episodes

**n_epochs = 10 (doubled from 5):**
More gradient steps per rollout means:
- More efficient use of collected data
- Higher GPU utilization during update phase
- Better convergence per unit of compute

**ent_coef = 0.05 (increased from 0.01-0.02):**
Based on GeeksforGeeks PPO analysis: entropy coefficient must be high enough to prevent entropy collapse, but not so high as to cause KL explosion. Empirical testing in v1.0 showed entropy_loss collapsing to -0.5 with ent_coef=0.02. The 0.05 value maintains healthy exploration (entropy_loss -1.3 to -1.6).

**transaction_cost = 0.0:**
Theoretically justified by Cameron Wolfe (2025): with any positive transaction cost, the value function converges to V(HOLD)=0 as the dominant strategy, creating a structural dead policy. Since SNB offers 0% commission, this parameter accurately reflects our live trading conditions.

---

## 9. Production Deployment Architecture

### 9.1 Paper Trading Thresholds (Minimum to Go Live)

Based on the Medium article (Abdul Haseeb 2025) and industry standards:

| Metric | Minimum | Target | Elite |
|--------|---------|--------|-------|
| Win rate | 55% | 60% | 63%+ |
| Sharpe ratio | 1.0 | 1.2 | 1.5+ |
| Max drawdown | 20% | 15% | 10% |
| Profit factor | 1.2 | 1.3 | 1.5+ |
| Min trades | 20 | 50 | 100+ |
| Paper period | 1 month | 3 months | 6 months |

### 9.2 Walk-Forward Validation Protocol

```
Month 1-3:   Paper trading with model trained on 2015-2025
Month 4:     Walk-forward retrain on 2015-2025 + Month 1-3 data
Month 5:     Trade on out-of-sample Month 4 predictions
→ Repeat rolling validation
→ Decision threshold: Sharpe >1.2 over 3 rolling windows
```

### 9.3 Live Trading Risk Management

```python
# Position sizing (ATR-based, from Medium article)
max_risk_per_trade = 0.02        # 2% of equity per trade
stop_loss = atr_14 * 1.5         # Dynamic stop
position_size = (equity * max_risk_per_trade) / stop_loss

# Portfolio limits
max_drawdown_limit = 0.30        # Hard stop: close all at 30% drawdown
max_position_size  = 0.20        # No more than 20% in one instrument
max_open_trades    = 5           # Maximum concurrent positions

# SNB compliance
min_holding_period = 30          # 30-day minimum hold
prohibited_pairs   = ['CHF']     # No CHF pairs
```

### 9.4 Modal Deployment

```python
# modal_deploy.py
import modal

app = modal.App("kat-live-trader")
image = modal.Image.debian_slim().pip_install(
    "stable-baselines3", "torch", "duckdb", "ibkr-web-api"
)

@app.function(
    image=image,
    schedule=modal.Cron("30 9 * * 1-5"),   # 9:30 EST weekdays
    secrets=[modal.Secret.from_name("snb-api-key")],
    timeout=28800,                            # 8 hours (market hours)
)
def run_trading_session():
    """Execute daily trading session."""
    from kat_live import KATLiveTrader
    trader = KATLiveTrader(
        model_path="/mnt/kat_models/best_model.zip",
        db_path="/mnt/kat_data/kat.db",
        broker="snb",
    )
    trader.run_session()

@app.function(schedule=modal.Cron("0 16 * * 1-5"))  # 4pm EST
def end_of_day_report():
    """Generate daily P&L report and Telegram notification."""
    pass
```

---

## 10. Monitoring & Observability

### 10.1 Telegram Monitor v2.0

Enhanced notifications include:
- Every eval result (reward, Sharpe, win rate, KL, entropy)
- Hourly training progress (steps, FPS, ETA, cost)
- Immediate crash alert with last 10 log lines
- Daily summary during paper trading

### 10.2 TensorBoard Metrics

Logged every iteration:
```python
# Training metrics
train/approx_kl, train/clip_fraction, train/entropy_loss
train/explained_variance, train/value_loss, train/policy_gradient_loss

# Eval metrics (v2.0 additions)
eval/mean_reward, eval/episode_length, eval/win_rate
eval/sharpe_ratio, eval/max_drawdown, eval/profit_factor

# Environment metrics (v2.0 additions)
env/trade_count, env/avg_holding_period, env/avg_trade_pnl
```

### 10.3 Health Check Dashboard

```python
HEALTH_THRESHOLDS = {
    "approx_kl":         {"warn": 0.02, "critical": 0.05},
    "clip_fraction":     {"warn": 0.20, "critical": 0.40},
    "entropy_loss":      {"warn": -0.80, "critical": -0.50},  # higher = worse
    "explained_variance": {"warn": 0.10, "critical": -0.50},  # lower = worse
    "fps":               {"warn": 1500, "critical": 500},    # lower = worse
}
```

---

## 11. Complete Stage Implementation Plan

### Stage 3 v2 — Launch Checklist

Pre-flight (30 minutes):
- [ ] Migrate PostgreSQL → DuckDB
- [ ] Precompute technical features into `technical_features` table
- [ ] Update `KATEnvV3` to load from DuckDB + add technical stream
- [ ] Update `KATPolicy` to add 4th stream (technical encoder)
- [ ] Update `stage3_launch.py` with new hyperparameters
- [ ] Verify obs size match: train == eval
- [ ] Run `python3 /root/kat/kat_policy.py` smoke test
- [ ] Confirm `transaction_cost=0.0`, `ent_coef=0.05`
- [ ] Launch monitor
- [ ] Verify Telegram notification received

Expected first eval (2M steps, ~15 minutes):
- eval/mean_reward: non-zero (positive or negative, not 0.00)
- entropy_loss: -1.3 to -1.6 (exploring)
- clip_fraction: 0.03-0.10 (stable)

### Stage 4 — GRPO + Options (Post Stage 3)

Prerequisites:
- Stage 3 eval/mean_reward consistently positive for 10+ evals
- Sharpe > 0.5 on eval period
- No early stopping for 50M+ steps

Implementation:
- Implement GRPO from scratch (no SB3 implementation — write custom)
- Add DoltHub options data to DuckDB
- Add IV surface features to observation space
- 4-server Vast.ai cluster deployment

### Stage 5 — Full Market Data

Prerequisites:
- Stage 4 Sharpe > 0.8
- Win rate > 55% on eval
- Stable training for 200M+ steps

Implementation:
- Add stocks and indices to DuckDB
- SAC for continuous position sizing
- TFT-style multi-horizon prediction
- Walk-forward backtesting framework

---

## 12. Research Bibliography

1. Schulman, J. et al. (2017). *Proximal Policy Optimization Algorithms.* arXiv:1707.06347
2. Ivison, H. et al. (2024). *Unpacking DPO and PPO.* Allen Institute for AI. arXiv:2406.09279
3. Wolfe, C.R. (2025). *PPO for LLMs: A Guide for Normal People.* Deep Learning Focus.
4. Adaptive ML (2026). *From Zero to PPO.* adaptive-ml.com
5. Hoque, M.R. et al. (2025). *RL in Financial Decision Making: Systematic Review.* arXiv:2512.10913
6. Bhuiyan, A. et al. (2025). *Deep Learning for Algorithmic Trading: Systematic Review.* ScienceDirect S2590005625000177
7. Abdul Haseeb (2025). *Building a Full-Stack Production-Grade ML-Powered Trading System.* Medium.
8. DeepSeek Team (2024). *DeepSeekMath: Pushing the Limits of Mathematical Reasoning.* arXiv:2402.03300 [GRPO origin]
9. Haarnoja, T. et al. (2018). *Soft Actor-Critic.* arXiv:1801.01290
10. Moody, J. & Saffell, M. (2001). *Learning to trade via direct reinforcement.* IEEE Trans. Neural Networks.
11. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley.
12. Chan, E. (2013). *Quantitative Trading.* Wiley.

---

## 13. Decision Matrix — Final Answers

| Question | Decision | Rationale |
|----------|----------|-----------|
| Start fresh? | **Yes** | Missing technical indicators, wrong tx_cost from day 1 |
| Algorithm Stage 3? | **PPO** | Stability, target_kl, checkpoint continuity |
| Algorithm Stage 4? | **GRPO** | Eliminates dead policy structurally, no critic |
| Algorithm Stage 5? | **SAC** | Continuous actions for options sizing |
| Database? | **DuckDB** | 12x faster startup, portable, free, no server |
| GPU utilization? | **Structural limit** | PPO/CPU bound. Improve via larger batches, 4-server cluster |
| transaction_cost? | **0.0** | SNB confirmed, eliminates dead policy bias |
| ent_coef? | **0.05** | Prevents entropy collapse, research confirmed |
| N_envs? | **96** | ~75-80% CPU target |
| When to go live? | **After paper trading** | Sharpe >1.2, win rate >60%, 3 months paper |

