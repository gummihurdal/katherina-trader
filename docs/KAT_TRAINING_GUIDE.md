# KAT Training Guide — Complete Reference

> Last updated: March 14, 2026 — v2.0 rebuild complete

## Overview
KAT (Katherina Algorithmic Trader) is a PPO-based RL trading system with a custom 4-stream Attention policy.
This guide documents everything learned from Stages 1-3 training sessions including the complete v2.0 rebuild.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| Training server | Vast.ai RTX 4090, Netherlands DC |
| DB | DuckDB — single file `/data/kat/kat_v2.db` |
| Scripts | GitHub: gummihurdal/katherina-trader/kat_v2/ |
| Monitoring | Telegram bot — hourly + every eval |
| Backups | Local laptop + GitHub |

### Vast.ai Instance Requirements
- **Disk:** 83GB minimum
- **RAM:** 128GB+
- **GPU:** RTX 4090
- **Location:** Netherlands
- **Cost:** ~$0.30/hr

---

## v2.0 Fresh Start Checklist (NEW INSTANCE)

### Step 1 — Install dependencies
```bash
pip install duckdb sqlalchemy --break-system-packages
```

### Step 2 — Clone repo
```bash
cd /root && git clone https://github.com/gummihurdal/katherina-trader.git
cp -r katherina-trader/kat_v2 /root/kat_v2
```

### Step 3 — Migrate DB (one time only)
```bash
python3 /root/kat_v2/migrate_to_duckdb.py \
  --pg-uri postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production \
  --out /data/kat/kat_v2.db
```

### Step 4 — Smoke tests (ALL must pass before training)
```bash
python3 /root/kat_v2/feature_pipeline.py /data/kat/kat_v2.db
python3 /root/kat_v2/kat_env_v2.py /data/kat/kat_v2.db
python3 /root/kat_v2/kat_policy_v2.py /data/kat/kat_v2.db
```

Expected output:
```
Loaded: 2266 days | macro: 1404 | futures: 150 | technical: 108 | total obs: 1770
...
KATEnvV2 OK ✓
KATPolicyV2 PASSED ✓
```

### Step 5 — Launch training
```bash
mkdir -p /data/kat/checkpoints/stage3_v2/best \
         /data/kat/checkpoints/stage3_v2/periodic \
         /data/kat/tensorboard/stage3_v2

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
KAT_DB_PATH=/data/kat/kat_v2.db \
nohup python3 /root/kat_v2/stage3_launch_v2.py > /tmp/stage3_v2.log 2>&1 &
echo "Training PID: $!"

sleep 5
OPENBLAS_NUM_THREADS=1 \
nohup python3 /kat_monitor_v2.py > /tmp/monitor_v2.log 2>&1 &
echo "Monitor PID: $!"
```

**CRITICAL:** Always set `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` — without these, 96 workers try to spawn 64 threads each = 6144 threads = OS crash.

---

## Known Issues & Fixes

### 1. OpenBLAS Thread Crash
**Error:** `pthread_create failed for thread N of 64: Resource temporarily unavailable`
**Cause:** 96 workers × 64 OpenBLAS threads = 6144 threads exceeds OS limit
**Fix:** `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` in launch command

### 2. DuckDB Column Name Mismatch
**Error:** `Referenced column "date" not found`
**Cause:** PostgreSQL uses `ts` column, not `date`
**Fix:** Use `SELECT ts as date` in all DuckDB queries

### 3. Feature Count Assert Failure
**Error:** `AssertionError: Expected 25 technical features, got 18`
**Cause:** Assert was wrong — actual count is 18 per contract
**Fix:** Update assert to match actual count, update TECHNICAL_FEATURES constant

### 4. Policy Dimension Mismatch
**Error:** `mat1 and mat2 shapes cannot be multiplied (1x48 and 150x256)`
**Cause:** Policy constants don't match actual feature pipeline output
**Fix:** Verify and match these constants in `kat_policy_v2.py`:
```python
MACRO_DIM     = 1404  # 54 series × 26 rolling features
PORTFOLIO_DIM = 108   # portfolio state
FUTURES_DIM   = 150   # 6 contracts × 25 OHLCV features
TECHNICAL_DIM = 108   # 6 contracts × 18 technical indicators
# Total obs:   1770
```

### 5. Reward Explosion
**Symptom:** `ep_rew_mean = -11,600,000` or similar extreme values
**Cause:** ADD action allows unbounded position growth; no reward clipping
**Fix:** Added to `kat_env_v2.py`:
```python
# Position cap
self._position = np.clip(self._position, -3.0, 3.0)
# Reward clipping
pnl_return = np.clip(pnl_return, -1.0, 1.0)
```

### 6. Two Training Processes Running
**Symptom:** Binary log file, unstable metrics, EV going to -0.866
**Cause:** Old `stage3_launch.py` still running alongside v2.0
**Fix:** `pkill -f stage3_launch` — kill ALL training processes before restarting

### 7. Dead Policy (HOLD only)
**Symptom:** `mean_reward=0.00`, `episode_length=261`
**Root cause:** `transaction_cost > 0` creates V(HOLD)=0 > V(TRADE)=-cost structural bias
**Fix:** `transaction_cost=0.0` — confirmed correct for SNB 0% commission

### 8. VecNormalize Shape Mismatch
**Error:** `operands could not be broadcast together`
**Cause:** Old .pkl normalization files from different obs size run
**Fix:** `rm -rf /data/kat/checkpoints/stage3_v2/best/*.pkl`

---

## Observation Space v2.0

| Stream | Dimensions | Source |
|--------|-----------|--------|
| Macro | 1404 | 54 FRED series × 26 rolling features |
| Portfolio | 108 | Equity, position, drawdown, trades |
| Futures OHLCV | 150 | 6 contracts × 25 features |
| Technical | 108 | 6 contracts × 18 indicators |
| **Total** | **1770** | |

### Technical Indicators (18 per contract)
RSI_14, MACD, MACD_signal, MACD_hist, BB_position, BB_width,
ATR_pct, Stoch_K, Stoch_D, Williams_R, ROC_1d/5d/10d/20d/60d,
Volume_ratio, Trend_strength, MA20_dist

### Macro Rolling Features (26 per series)
raw, pct1/5/10/20, ma5/10/20/60, std5/10/20, zscore20/60,
mom5/20/60, rank20, above_ma20/60, vol_ratio, accel,
high20, low20, trend, cross

---

## Hyperparameters v2.0

```python
learning_rate   = 1e-4
n_steps         = 8192    # 2x v1 — better advantage estimation
batch_size      = 4096    # 2x v1 — larger GPU batches
n_epochs        = 10      # 2x v1 — more gradient steps per rollout
gamma           = 0.995
gae_lambda      = 0.95
clip_range      = 0.15
ent_coef        = 0.05    # CRITICAL — prevents entropy collapse
vf_coef         = 0.5
max_grad_norm   = 0.5
target_kl       = 0.02    # CRITICAL — prevents catastrophic updates
N_envs          = 96
device          = "cuda"
transaction_cost = 0.0    # SNB 0% commission — eliminates dead policy
reward_scaling   = 0.1
```

---

## Healthy Training Metrics v2.0

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|---------|
| approx_kl | 0.003-0.015 | >0.02 | >0.05 |
| clip_fraction | 0.03-0.10 | >0.20 | >0.40 |
| entropy_loss | -1.4 to -1.6 | >-0.8 | >-0.5 |
| explained_variance | >0.3 after 20M | <0 | <-1.0 |
| eval/mean_reward | Positive after 10M | 0.00 | Deeply negative |
| ep_rew_mean | Reasonable | >10,000 | >1,000,000 (explosion) |
| FPS | 4,000-6,000 | <2,000 | <500 |

---

## Database v2.0

### File: `/data/kat/kat_v2.db` (DuckDB)

| Table | Rows | Description |
|-------|------|-------------|
| macro_data | 277,124 | 54 series, 2000-2025 |
| market_data_continuous | 20,519 | 6 futures, 2015-2025 |
| technical_features | 20,519 | Precomputed indicators |

### Macro Series (54 total)
Volatility: VIX, VIX3M, VVIX, OVX, EVZ, GVZ, MOVE
Rates: TNX (10Y), TYX (30Y), FVX (5Y)
Commodities: CL, GC, HG, CORN, WEAT, SOYB
Credit: HYG, LQD, IEF, TLT, EMB, SHY, TIP
Sectors: XLF, XLK, XLE, XLV, XLP, XLI, XLB, XLU, XLC, XLRE, XLY
International: EEM, EFA, EWG, EWJ, FXI, INDA, EWZ, EWT, EWY
Ratios: SPY_TLT, HYG_IEF, XLK_XLP, COPPER_GOLD
Dollar: DX-Y.NYB

### Futures Symbols
CL (crude oil), ES (S&P500), GC (gold), HG (copper), NQ (Nasdaq), ZB (T-bonds)

---

## Stage Roadmap

| Stage | Algorithm | Data | Status |
|-------|-----------|------|--------|
| 3 v2 | PPO + KATPolicy v2 | Macro + futures + technicals | 🔄 Running |
| 4 | GRPO | + Options (DoltHub) | Pending |
| 5a | PPO v3 | + Stocks + indices | Pending |
| 5b | A2C | Same as 5a (parallel) | Pending |
| Paper | **Ensemble** PPO+A2C | All data | Pending |
| Live | **Ensemble** | All data | Pending |

---

## Key Commands

```bash
# Check training is running
pgrep -a python3 | grep stage3

# Watch live log
tail -f /tmp/stage3_v2.log

# Check eval rewards
strings /tmp/stage3_v2.log | grep -E "mean_reward|New best|Early stop"

# Full restart
pkill -f stage3_launch; pkill -f kat_monitor
rm -rf /data/kat/checkpoints/stage3_v2/best/*.pkl
rm -f /tmp/stage3_v2.log
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 KAT_DB_PATH=/data/kat/kat_v2.db \
nohup python3 /root/kat_v2/stage3_launch_v2.py > /tmp/stage3_v2.log 2>&1 &
```

---

## Lessons Learned (v2.0 rebuild)

1. **OPENBLAS_NUM_THREADS=1 is mandatory** — 96 workers × 64 threads = OS crash
2. **DuckDB column is `ts` not `date`** — check with DESCRIBE before querying
3. **Feature count must be verified** — assert must match actual output not design doc
4. **Policy dims must match pipeline** — always verify MACRO/FUTURES/TECHNICAL_DIM
5. **Kill ALL old processes before restart** — two competing runs = binary log, EV explosion
6. **Add reward clipping** — `np.clip(pnl_return, -1.0, 1.0)` prevents reward explosion
7. **Add position caps** — `np.clip(self._position, -3.0, 3.0)` prevents runaway leverage
8. **transaction_cost=0.0 works** — positive reward at 4M steps confirmed
9. **ent_coef=0.05 works** — entropy stable at -1.6 throughout training
10. **DuckDB is 12x faster startup** — 96 workers load in seconds vs minutes with PostgreSQL
11. **`strings` command for binary logs** — use `strings /tmp/stage3_v2.log | grep ...`
12. **Use `tail -f` to watch live** — exit with Ctrl+Z then `kill %1` in Jupyter terminal

