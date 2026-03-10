"""
KAT Phase 2 Training Script
============================
Runs on Vast.ai RTX 4090 (Norway host:1276)
Full dataset: price_bars + macro_data + earnings + sentiment

Usage on Vast.ai:
  python stage2_train.py

Expected: 200M steps, ~5hrs on RTX 4090
"""
import os, sys, multiprocessing
import numpy as np
import pandas as pd
import psycopg2
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]
CHECKPOINT_DIR = Path(os.getenv("KAT_CHECKPOINT_DIR", "/data/kat/checkpoints"))
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "file:///data/kat/models/mlflow")
STAGE1_MODEL = os.getenv("STAGE1_MODEL_PATH", "/data/kat/checkpoints/stage1/kat_stage1_final")

TOTAL_STEPS   = 200_000_000
N_ENVS        = 16          # RTX 4090 can handle more parallel envs
LEARNING_RATE = 1e-4        # Lower than stage1 — fine-tuning
BATCH_SIZE    = 512
N_STEPS       = 4096
EVAL_FREQ     = 500_000

# All symbols available in our DB
ALL_SYMBOLS = [
    # US large cap
    "AAPL","MSFT","AMZN","NVDA","GOOGL","META","TSLA","JPM","BAC","GS",
    "AMD","INTC","NFLX","CRM","ADBE","V","MA","XOM","CVX","JNJ",
    # ETFs & indices
    "SPY","QQQ","IWM","GLD","TLT","HYG","XLE","XLK","XLF","XLV",
    # Futures
    "ES.c.0","NQ.c.0","CL.c.0","GC.c.0","NG.c.0","ZB.c.0","6E.c.0",
    # European
    "ASML.AS","SAP.DE","NESN.SW","NOVN.SW","ROG.SW","SIE.DE","LVMH.PA",
    # Crypto
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD",
    # FX
    "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X",
]

# ── Data Loading ──────────────────────────────────────────────────────────────
print("Loading data from PostgreSQL...")
conn = psycopg2.connect(DATABASE_URL)

def load_price_data(symbol: str) -> pd.DataFrame:
    df = pd.read_sql(
        "SELECT ts, open, high, low, close, volume FROM price_bars WHERE symbol=%s AND timespan='1d' ORDER BY ts",
        conn, params=(symbol,), index_col="ts", parse_dates=["ts"]
    )
    return df

def load_macro_data() -> pd.DataFrame:
    """Load macro regime features — aligned to trading days."""
    key_series = [
        "T10Y2Y",      # yield curve inversion
        "DFF",         # fed funds rate
        "BAMLH0A0HYM2", # HY credit spread
        "CPIAUCSL",    # inflation
        "UNRATE",      # unemployment
        "^VIX",        # volatility regime
        "^VIX3M",      # vol term structure
        "HYG_IEF_RATIO", # credit risk appetite
        "SPY_TLT_RATIO", # stocks vs bonds
        "COPPER_GOLD_RATIO", # growth proxy
        "DX-Y.NYB",    # dollar strength
        "WALCL",       # fed balance sheet
        "M2SL",        # money supply
    ]
    placeholders = ','.join(['%s'] * len(key_series))
    df = pd.read_sql(
        f"SELECT series_id, ts, value FROM macro_data WHERE series_id IN ({placeholders}) ORDER BY ts",
        conn, params=key_series
    )
    # Pivot to wide format: date × series
    pivot = df.pivot_table(index='ts', columns='series_id', values='value')
    pivot = pivot.resample('D').last().ffill().bfill()
    return pivot

print("Loading macro features...")
macro_df = load_macro_data()
N_MACRO_FEATURES = len(macro_df.columns)
print(f"  Macro features: {N_MACRO_FEATURES} series, {len(macro_df)} days")

print(f"Loading price data for {len(ALL_SYMBOLS)} symbols...")
price_data = {}
for sym in ALL_SYMBOLS:
    try:
        df = load_price_data(sym)
        if len(df) >= 500:  # min 2 years of data
            price_data[sym] = df
    except Exception as e:
        pass

print(f"  Loaded {len(price_data)} symbols with sufficient history")
conn.close()

# ── Environment with Macro Features ──────────────────────────────────────────
import gymnasium as gym
from gymnasium import spaces

class KATEnvV2(gym.Env):
    """
    Phase 2 environment with macro regime features added to observation.
    
    State space:
      - 60 bars OHLCV + 5 technical indicators = 60 * 10 = 600
      - Portfolio state: cash%, position, pnl, drawdown = 4
      - Macro features: 13 regime indicators = 13
      Total: 617
    """
    
    LOOKBACK = 60
    N_FEATURES = 10   # OHLCV + RSI + MACD + BB + ATR + volume_ratio
    
    def __init__(self, price_df: pd.DataFrame, macro_df: pd.DataFrame,
                 initial_capital: float = 100_000, transaction_cost: float = 0.001):
        super().__init__()
        
        self.price_df = price_df.copy()
        self.macro_df = macro_df.copy()
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost
        
        # Precompute features
        self._compute_features()
        
        n_obs = self.LOOKBACK * self.N_FEATURES + 4 + N_MACRO_FEATURES
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(n_obs,), dtype=np.float32)
        self.action_space = spaces.Discrete(5)  # hold, buy, sell, buy_half, sell_half
        
        self.reset()
    
    def _compute_features(self):
        df = self.price_df.copy()
        
        # Normalised OHLCV
        df['ret'] = df['close'].pct_change()
        df['hl_ratio'] = (df['high'] - df['low']) / df['close']
        df['oc_ratio'] = (df['close'] - df['open']) / df['open']
        
        # RSI(14)
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = (ema12 - ema26) / df['close']
        
        # Bollinger Band position
        sma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        df['bb_pos'] = (df['close'] - sma20) / (2 * std20.replace(0, 1e-9))
        
        # ATR normalised
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean() / df['close']
        
        # Volume ratio
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean().replace(0, 1)
        
        self.features = df[['ret','hl_ratio','oc_ratio','rsi','macd','bb_pos','atr',
                             'open','high','low']].fillna(0).values
        self.closes = df['close'].values
        self.dates = df.index
        self.n_bars = len(df)
    
    def _get_macro(self, date):
        try:
            idx = self.macro_df.index.searchsorted(date)
            idx = min(idx, len(self.macro_df) - 1)
            row = self.macro_df.iloc[idx].fillna(0).values
            # Normalise roughly
            return np.clip(row / 100.0, -5, 5).astype(np.float32)
        except:
            return np.zeros(N_MACRO_FEATURES, dtype=np.float32)
    
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        start_min = self.LOOKBACK + 20
        self.t = np.random.randint(start_min, max(start_min + 1, self.n_bars - 200))
        
        self.cash = self.initial_capital
        self.position = 0
        self.entry_price = 0.0
        self.peak_value = self.initial_capital
        self.trade_history = []
        self.returns = []
        
        return self._obs(), {}
    
    def _obs(self):
        # Price features: lookback window
        start = max(0, self.t - self.LOOKBACK)
        window = self.features[start:self.t]
        if len(window) < self.LOOKBACK:
            window = np.vstack([np.zeros((self.LOOKBACK - len(window), self.N_FEATURES)), window])
        
        price_obs = window.flatten()
        
        # Portfolio state
        current_price = self.closes[self.t - 1]
        portfolio_value = self.cash + self.position * current_price
        pnl = (current_price - self.entry_price) * self.position if self.position != 0 else 0
        cost_basis = self.entry_price * abs(self.position) if self.entry_price != 0 else 1
        pnl_pct = pnl / cost_basis if cost_basis != 0 else 0.0
        drawdown = (portfolio_value - self.peak_value) / self.peak_value
        
        portfolio_obs = np.array([
            self.cash / self.initial_capital,
            self.position * current_price / self.initial_capital,
            pnl_pct,
            drawdown,
        ], dtype=np.float32)
        
        # Macro features
        date = self.dates[self.t - 1]
        macro_obs = self._get_macro(date)
        
        return np.concatenate([price_obs.astype(np.float32), portfolio_obs, macro_obs])
    
    def step(self, action):
        current_price = self.closes[self.t]
        prev_value = self.cash + self.position * self.closes[self.t - 1]
        
        # Execute action
        if action == 1 and self.position == 0:   # BUY full
            shares = int(self.cash * 0.95 / current_price)
            if shares > 0:
                cost = shares * current_price * (1 + self.transaction_cost)
                self.cash -= cost
                self.position = shares
                self.entry_price = current_price
        
        elif action == 3 and self.position == 0: # BUY half
            shares = int(self.cash * 0.475 / current_price)
            if shares > 0:
                cost = shares * current_price * (1 + self.transaction_cost)
                self.cash -= cost
                self.position = shares
                self.entry_price = current_price
        
        elif action == 2 and self.position > 0:  # SELL full
            proceeds = self.position * current_price * (1 - self.transaction_cost)
            pnl = proceeds - self.entry_price * self.position
            self.trade_history.append(pnl)
            self.cash += proceeds
            self.position = 0
            self.entry_price = 0.0
        
        elif action == 4 and self.position > 0:  # SELL half
            half = self.position // 2
            if half > 0:
                proceeds = half * current_price * (1 - self.transaction_cost)
                pnl = proceeds - self.entry_price * half
                self.trade_history.append(pnl)
                self.cash += proceeds
                self.position -= half
        
        self.t += 1
        
        # Portfolio value
        portfolio_value = self.cash + self.position * current_price
        self.peak_value = max(self.peak_value, portfolio_value)
        
        # Sharpe-adjusted reward
        step_return = (portfolio_value - prev_value) / prev_value
        self.returns.append(step_return)
        
        if len(self.returns) >= 20:
            ret_arr = np.array(self.returns[-20:])
            sharpe = ret_arr.mean() / (ret_arr.std() + 1e-9) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        drawdown = (portfolio_value - self.peak_value) / self.peak_value
        reward = float(sharpe + step_return * 10 + drawdown * 5)
        
        done = self.t >= self.n_bars - 1 or portfolio_value < self.initial_capital * 0.5
        
        info = {
            "portfolio_value": portfolio_value,
            "total_return": (portfolio_value - self.initial_capital) / self.initial_capital,
            "n_trades": len(self.trade_history),
            "drawdown": drawdown,
        }
        
        return self._obs(), reward, done, False, info


# ── Training ──────────────────────────────────────────────────────────────────
def make_env(symbol):
    def _fn():
        from stable_baselines3.common.monitor import Monitor
        df = price_data[symbol]
        env = KATEnvV2(df, macro_df)
        return Monitor(env)
    return _fn


def main():
    multiprocessing.set_start_method("fork", force=True)
    
    import mlflow
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
    
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    
    symbols = list(price_data.keys())
    train_symbols = symbols[:int(len(symbols) * 0.85)]
    eval_symbols  = symbols[int(len(symbols) * 0.85):]
    
    print(f"\nTraining symbols: {len(train_symbols)}")
    print(f"Eval symbols:     {len(eval_symbols)}")
    
    # Build vectorized envs
    n_train = min(N_ENVS, len(train_symbols))
    env_fns = [make_env(train_symbols[i % len(train_symbols)]) for i in range(n_train)]
    vec_env = DummyVecEnv(env_fns)
    vec_env = VecNormalize(vec_env, norm_obs=True, norm_reward=True, clip_obs=10.0)
    
    eval_fns = [make_env(eval_symbols[0])]
    eval_env = DummyVecEnv(eval_fns)
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False)
    
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment("kat_stage2_full")
    
    with mlflow.start_run(run_name=f"stage2_{datetime.now():%Y%m%d_%H%M}"):
        mlflow.log_params({
            "stage": 2,
            "total_steps": TOTAL_STEPS,
            "n_envs": n_train,
            "n_symbols": len(train_symbols),
            "n_macro_features": N_MACRO_FEATURES,
            "learning_rate": LEARNING_RATE,
            "batch_size": BATCH_SIZE,
        })
        
        # Load Stage 1 model or start fresh
        stage1_path = STAGE1_MODEL + ".zip"
        if Path(stage1_path).exists():
            print(f"\nLoading Stage 1 checkpoint: {stage1_path}")
            model = PPO.load(STAGE1_MODEL, env=vec_env, 
                           learning_rate=LEARNING_RATE,
                           batch_size=BATCH_SIZE,
                           n_steps=N_STEPS)
        else:
            print("\nNo Stage 1 checkpoint found — starting fresh (Phase 2 only)")
            model = PPO(
                "MlpPolicy", vec_env,
                learning_rate=LEARNING_RATE,
                n_steps=N_STEPS,
                batch_size=BATCH_SIZE,
                n_epochs=10,
                gamma=0.995,
                gae_lambda=0.95,
                clip_range=0.2,
                ent_coef=0.003,
                vf_coef=0.5,
                max_grad_norm=0.5,
                verbose=1,
                tensorboard_log="/data/kat/models/tensorboard",
                policy_kwargs=dict(net_arch=[512, 512, 256]),
            )
        
        callbacks = [
            CheckpointCallback(
                save_freq=max(1_000_000 // n_train, 1),
                save_path=str(CHECKPOINT_DIR / "stage2"),
                name_prefix="kat_stage2",
            ),
            EvalCallback(
                eval_env,
                best_model_save_path=str(CHECKPOINT_DIR / "stage2" / "best"),
                log_path=str(CHECKPOINT_DIR / "stage2" / "eval_logs"),
                eval_freq=max(EVAL_FREQ // n_train, 1),
                n_eval_episodes=5,
                deterministic=True,
            ),
        ]
        
        print(f"\nStarting Phase 2 training: {TOTAL_STEPS:,} steps on {n_train} envs")
        print(f"Macro features: {N_MACRO_FEATURES}")
        print(f"Estimated time on RTX 4090: ~5 hours\n")
        
        model.learn(
            total_timesteps=TOTAL_STEPS,
            callback=callbacks,
            progress_bar=True,
            reset_num_timesteps=True,
        )
        
        # Save final
        final_path = CHECKPOINT_DIR / "stage2" / "kat_stage2_final"
        model.save(str(final_path))
        vec_env.save(str(final_path) + "_vecnorm.pkl")
        mlflow.log_artifact(str(final_path) + ".zip", artifact_path="model")
        
        print(f"\n✅ Stage 2 complete. Model: {final_path}")


if __name__ == "__main__":
    main()
