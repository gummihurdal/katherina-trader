# KAT Training Guide — Complete Reference

> Last updated: March 14, 2026

## Overview
KAT (Katherina Algorithmic Trader) is a PPO-based RL trading system with a custom Attention policy.
This guide documents everything learned from Stages 1-3 training sessions.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| Training server | Vast.ai RTX 4090, Netherlands DC |
| DB (training) | PostgreSQL local on Vast.ai |
| DB (future) | DuckDB single file — copy to Vast.ai |
| Scripts | GitHub: gummihurdal/katherina-trader |
| Monitoring | Telegram bot — hourly + every eval |
| Backups | Local laptop + GitHub |

### Vast.ai Instance Requirements
- **Disk:** 83GB minimum
- **RAM:** 128GB+ (1TB recommended)
- **GPU:** RTX 4090
- **Location:** Netherlands (same DC for multi-server)
- **Cost:** ~$0.30/hr

### SSH Connection
```bash
# From any Linux server
ssh -i ~/.ssh/id_ed25519 -p PORT root@VAST_IP

# From Windows
ssh -i C:\Users\breka\.ssh\kat-hetzner_key -p PORT root@VAST_IP
```

---

## Pre-Launch Checklist (ALWAYS follow before training)

### 1. PostgreSQL Tuning
```bash
cat >> /etc/postgresql/16/main/postgresql.conf << 'PGEOF'
shared_buffers = 16GB
work_mem = 256MB
maintenance_work_mem = 2GB
effective_cache_size = 48GB
tcp_keepalives_idle = 60
tcp_keepalives_interval = 10
tcp_keepalives_count = 10
fsync = off
synchronous_commit = off
full_page_writes = off
max_connections = 200
random_page_cost = 1.1
PGEOF
service postgresql restart
```

### 2. Verify Train/Eval Obs Size Match
```bash
KAT_DB_URI='postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production' python3 -c "
import sys; sys.path.insert(0,'/root/kat')
from kat_env_v3 import KATEnvV3
db='postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production'
t=KATEnvV3(db_uri=db,start_date='2015-01-01',end_date='2023-12-31')
e=KATEnvV3(db_uri=db,start_date='2024-01-01',end_date='2025-12-31')
print('Train:',t._obs_size,'Eval:',e._obs_size,'MATCH:',t._obs_size==e._obs_size)
assert t._obs_size == e._obs_size, 'MISMATCH — fix before training!'
"
```

### 3. Delete Old VecNormalize Files
```bash
rm -rf /data/kat/checkpoints/stage*/best/*.pkl
rm -rf /data/kat/checkpoints/stage*/periodic/*.pkl
rm -f /data/kat/checkpoints/stage*/eval_logs/*
```

### 4. Check CPU Usage
```bash
top -bn1 | grep "Cpu(s)"
# Target: 60-80% CPU → set N_envs=96
# Over 85% → reduce N_envs
# Under 50% → increase N_envs
```

### 5. Verify Syntax
```bash
python3 -c "import ast; ast.parse(open('/root/stage3_launch.py').read()); print('launch OK')"
python3 -c "import ast; ast.parse(open('/root/kat/kat_env_v3.py').read()); print('env OK')"
python3 -c "import ast; ast.parse(open('/root/kat/kat_policy.py').read()); print('policy OK')"
```

### 6. Launch with Monitor
```bash
nohup python3 /kat_monitor.py > /tmp/monitor.log 2>&1 &
echo "PID: $!"
sleep 90 && tail -20 /tmp/stage3.log
```

---

## Known Crash Causes & Fixes

### 1. VecNormalize Shape Mismatch
**Error:** `ValueError: operands could not be broadcast together with shapes (1696,) (1722,)`
**Cause:** Old .pkl normalization files from previous run with different obs size
**Fix:**
```bash
rm -rf /data/kat/checkpoints/stage*/best/*.pkl
rm -rf /data/kat/checkpoints/stage*/periodic/*.pkl
```

### 2. Inconsistent Train/Eval Obs Size
**Error:** Train obs=1722, Eval obs=1696
**Cause:** `macro_raw` filtered by date BEFORE pivot — eval period missing some series
**Fix:** In `_build_features()` — pivot on FULL macro data first, then filter:
```python
# WRONG
macro_raw = macro_raw[(macro_raw["ts"] >= sd) & (macro_raw["ts"] <= ed)]
macro_pivot = macro_raw.pivot_table(...)

# CORRECT
macro_pivot = macro_raw.pivot_table(...)  # full data first
macro_pivot = macro_pivot[(macro_pivot.index >= sd) & (macro_pivot.index <= ed)]
```

### 3. EOFError / BrokenPipeError on Startup
**Error:** `EOFError` or `BrokenPipeError: [Errno 32]`
**Cause 1:** PostgreSQL max_connections too low for 64+ workers
**Fix 1:** Set max_connections=200, add TCP keepalives (see PostgreSQL tuning above)
**Cause 2:** Script missing `if __name__ == "__main__"` guard
**Fix 2:** Always wrap training code in `if __name__ == "__main__":`

### 4. KL Explosion / Early Stopping
**Error:** `Early stopping at step N due to reaching max kl: 0.03`
**Cause:** Reward shaping values too large
**Fix:** Keep reward shaping tiny:
```python
# reward_scaling too high → KL explodes
reward_scaling = 0.1   # OK
reward_scaling = 1.0   # Too high

# trade_bonus too large → KL explodes
trade_bonus = 0.00005  # OK
trade_bonus = 0.001    # Too high — causes explosion
```

### 5. Dead Policy (Always HOLD)
**Symptom:** `mean_reward=0.00`, `episode_length=261` at every eval
**Cause:** Model discovers HOLD=0 is safer than trading with transaction costs
**Fix:** Check reward_scaling is high enough (0.1 minimum), transaction_cost not too high
```python
reward_scaling = 0.1      # Must be high enough to signal
transaction_cost = 0.0002 # If 0% commission available, set to 0.0
```

### 6. Timezone Comparison Error
**Error:** `TypeError: Invalid comparison between dtype=datetime64[us, UTC] and Timestamp`
**Fix:**
```python
macro_raw["ts"] = pd.to_datetime(macro_raw["ts"]).dt.tz_localize(None).dt.normalize()
```

### 7. GPU Underutilization Warning
**Warning:** `You are trying to run PPO on the GPU with MlpPolicy`
**Fix:** Use KATPolicy (custom attention) — this IS GPU optimized, ignore this warning

---

## Architecture

### Environment: KATEnvV3
- **Obs size:** 1722 (macro 1404 + portfolio 108 + futures 210)
- **Action space:** Discrete(5) — HOLD, BUY, SELL, ADD, CLOSE
- **Train split:** 2015-01-01 to 2023-12-31
- **Eval split:** 2024-01-01 to 2025-12-31
- **Test split:** 2026-01-01 onwards (never touch until final evaluation)

### Policy: KATPolicy (custom)
- 3 separate encoders: macro stream, portfolio stream, futures stream
- Cross-attention between all 3 streams
- 1,880,710 parameters
- GPU-optimized (CUDA)
- Located: `/root/kat/kat_policy.py`

### Algorithm: PPO
```python
learning_rate = 1e-4
n_steps       = 4096
batch_size    = 2048
n_epochs      = 5
gamma         = 0.995
target_kl     = 0.02   # CRITICAL — prevents KL explosion
ent_coef      = 0.02   # Keep entropy alive
clip_range    = 0.15
N_envs        = 96     # Adjust based on CPU %
device        = "cuda"
```

---

## Reward Function
```python
# In KATEnvV3.step() — keep simple, no complex shaping
reward = (total_equity - prev_equity) / (prev_equity + 1e-8) * self.reward_scaling \
         - cost * 0.001 \
         - drawdown * 0.001

# reward_scaling: 0.1 (must be high enough to signal through noise)
# transaction_cost: 0.0002 (set to 0.0 if broker has 0% commission)
```

---

## Healthy Training Metrics

| Metric | Target | Warning |
|--------|--------|---------|
| approx_kl | 0.003-0.015 | > 0.02 = danger |
| clip_fraction | 0.03-0.10 | > 0.20 = too aggressive |
| entropy_loss | -1.0 to -1.6 | > -0.5 = collapsed |
| explained_variance | > 0.5 after 10M steps | < 0 = not learning |
| eval/mean_reward | Positive after 20M steps | 0.00 = dead policy |
| FPS | ~3,000 | < 1,000 = something wrong |

---

## Telegram Monitor
- **Updates:** hourly + at every eval
- **Eval notification includes:** reward, KL, EV, trend indicator
- **Alerts:** immediate on crash or completion
- **Monitor script:** `/kat_monitor.py` on Vast.ai
- Checks log every 15 seconds for new eval results

---

## Database

### Connection strings
```
# PostgreSQL (training)
postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production

# DuckDB (future — faster startup)
import duckdb; conn = duckdb.connect('kat.db')
```

### Tables
| Table | Rows | Description |
|-------|------|-------------|
| macro_data | 277,124 | 47 FRED macro series, 2000-2026 |
| market_data_continuous | 20,519 | 6 futures contracts, daily OHLCV |
| market_data | ~500K | Raw futures contracts |

### Migrate to DuckDB
```bash
# Export from PostgreSQL
PGPASSWORD=KATguard2026 psql -U kat_db -h 127.0.0.1 -d kat_production \
  -c "\COPY macro_data TO '/tmp/macro_data.csv' CSV HEADER"
PGPASSWORD=KATguard2026 psql -U kat_db -h 127.0.0.1 -d kat_production \
  -c "\COPY market_data_continuous TO '/tmp/market_data_continuous.csv' CSV HEADER"

# Convert to DuckDB
python3 -c "
import duckdb
conn = duckdb.connect('kat.db')
conn.execute(\"CREATE TABLE macro_data AS SELECT * FROM read_csv_auto('macro_data.csv')\")
conn.execute(\"CREATE TABLE market_data_continuous AS SELECT * FROM read_csv_auto('market_data_continuous.csv')\")
print('DuckDB ready')
"
```

---

## Stage Roadmap

| Stage | Data | Algorithm | Target |
|-------|------|-----------|--------|
| 1 | Macro only | PPO MLP | ✅ Complete |
| 2 | Macro only | PPO MLP | ✅ Complete |
| 3 | Macro + futures daily | PPO KATPolicy GPU | 🔄 Running |
| 4 | + Options chains (DoltHub free) | PPO KATPolicy | Pending |
| 5 | + Stocks + indices | PPO → compare A2C | Pending |
| Paper trading | All data | Best model | Pending |
| Live trading | All data | $20K, stop $14K | Pending |

---

## Scaling to 4 Servers (Stage 4+)

For distributed A2C training:
- All servers: **Netherlands datacenter** (10Gbps internal)
- Server 1: Parameter server + PostgreSQL DB
- Servers 2-4: Workers (96 envs each = 288 total)
- Expected FPS: ~12,000 (4x current)
- 500M steps: ~12 hours vs ~50 hours single server
- Cost: ~$1.20/hr = ~$14 per run

---

## File Locations (Vast.ai)

```
/root/stage3_launch.py      — main training script
/kat_monitor.py             — Telegram monitor
/root/kat/kat_env_v3.py     — trading environment
/root/kat/kat_policy.py     — custom attention policy
/data/kat/checkpoints/      — model checkpoints
/data/kat/tensorboard/      — training logs
/tmp/stage3.log             — live training output
/tmp/monitor.log            — monitor output
```

---

## Key Commands

```bash
# Check training status
pgrep -f stage3_launch && echo "RUNNING" || echo "DEAD"

# Watch live
tail -f /tmp/stage3.log

# Check all eval rewards
grep "mean_reward\|episode_reward\|New best\|Early stop" /tmp/stage3.log

# PostgreSQL health
tail -20 /var/log/postgresql/postgresql-16-main.log

# CPU usage
top -bn1 | grep "Cpu(s)"

# Full restart after crash
pkill -f stage3_launch; pkill -f kat_monitor
rm -rf /data/kat/checkpoints/stage3/best/*.pkl
rm -rf /data/kat/checkpoints/stage3/periodic/*.pkl
nohup python3 /kat_monitor.py > /tmp/monitor.log 2>&1 &
```

---

## Lessons Learned

1. **Always check disk size before renting** — minimum 83GB
2. **Copy DB locally** — never train with remote DB (10x speed difference)
3. **Always verify train/eval obs size match** — macro pivot must happen before date filter
4. **Delete VecNormalize pkl files** when restarting with different obs size
5. **Keep reward_scaling=0.1** — too low = dead policy, too high = KL explosion
6. **Keep trade_bonus tiny (0.00005 max)** — larger values cause KL explosion
7. **Add `if __name__ == "__main__"` guard** — required for SubprocVecEnv
8. **PostgreSQL needs tuning** — max_connections=200, fsync=off, keepalives on
9. **MLP policy is CPU-bound** — KATPolicy (attention) is GPU optimized
10. **FPS only improves with more parallel envs** — DB speed, network size are marginal
11. **reward_scaling=0.1 + no inaction penalty** — cleanest training signal
12. **Telegram monitor checks every 15s** — eval notifications + hourly updates


---

## Research Foundation

### Key Papers Studied

#### 1. PPO for LLMs (Cameron Wolfe, 2025)
Key insight for KAT: The **advantage function** is what drives learning. If the value function V(s)=0 for all states (which happens when policy always HOLDs), the advantage A(s,a) = Q(s,a) - V(s) never signals that trading is better. Fix: remove transaction costs so trading has positive expected value.

#### 2. Unpacking DPO and PPO (Allen Institute / UW, 2024)
Key finding: **Data quality matters more than algorithm choice**. Better market data (options chains, IV surface) will improve KAT more than switching from PPO to A2C or GRPO. PPO outperforms DPO by 2.5% — confirms our algorithm choice is correct.

#### 3. PPO and GRPO Introduction (TDS, 2025)
Key insight: **GRPO eliminates the critic/value network** by comparing multiple actions' rewards relative to each other. This directly solves the dead policy problem — the model learns what's *relatively better* rather than needing absolute positive rewards. Recommended for Stage 4.

#### 4. PPO Fundamentals (GeeksforGeeks, 2025)
Confirms our parameter choices:
- `ent_coef=0.02` — prevents entropy collapse (overconfident HOLD policy)
- `clip_range=0.15` — controls policy deviation per update
- `target_kl=0.02` — prevents large destabilizing updates
- `gamma=0.995` — values future rewards appropriately

### Algorithm Roadmap Based on Research

| Stage | Algorithm | Why |
|-------|-----------|-----|
| Stage 3 | PPO + KATPolicy | Stable, proven, handles discrete actions |
| Stage 4 | GRPO | No critic needed, eliminates dead policy, relative reward comparison |
| Stage 5 | Ensemble PPO + GRPO | Best of both |

### Critical Insight: Why transaction_cost Must Be 0.0

With `transaction_cost=0.0002`:
- Every trade starts with reward = -0.04 (transaction penalty)
- Value function learns V(s) = 0 for all states (HOLD is safe)
- Advantage A(BUY) = -0.04 - 0 = negative → model learns BUY is bad
- Dead policy emerges — HOLD forever

With `transaction_cost=0.0`:
- Trades start with reward = actual P&L
- Value function learns real market dynamics
- Advantage correctly signals when trading is profitable
- Model learns to trade when expected P&L > 0

**Always use `transaction_cost=0.0` when broker has 0% commission.**


---

## v2.0 Launch Session — March 14, 2026

### What Changed in v2.0

| Component | v1.0 | v2.0 |
|-----------|------|------|
| Database | PostgreSQL | DuckDB (12x faster startup) |
| Obs size | 1722 | 1770 |
| Macro features | 1404 (54×26) | 1404 (54×26) ✅ same |
| Futures features | 210 | 150 (corrected) |
| Technical indicators | 0 | 108 (6 contracts × 18) |
| transaction_cost | 0.0002 | **0.0** (SNB confirmed) |
| ent_coef | 0.01-0.02 | **0.05** |
| n_steps | 4096 | **8192** |
| n_epochs | 5 | **10** |
| batch_size | 2048 | **4096** |
| Policy params | 1,880,710 | 2,943,366 |
| FPS | ~2,400 | **~5,000** |
| Positive reward | Never cleanly | **At 1.5M steps** |

### New Files
```
/root/kat_v2/feature_pipeline.py    — DuckDB loader + technical indicators
/root/kat_v2/kat_env_v2.py          — Clean environment (tx_cost=0)
/root/kat_v2/kat_policy_v2.py       — 4-stream attention policy
/root/kat_v2/stage3_launch_v2.py    — PPO training script v2
/root/kat_v2/migrate_to_duckdb.py   — One-time migration
/data/kat/kat_v2.db                 — DuckDB database
/kat_monitor_v2.py                  — Telegram monitor v2
```

### Launch Command (v2.0)
```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 KAT_DB_PATH=/data/kat/kat_v2.db \
  nohup python3 /root/kat_v2/stage3_launch_v2.py > /tmp/stage3_v2.log 2>&1 &
OPENBLAS_NUM_THREADS=1 nohup python3 /kat_monitor_v2.py > /tmp/monitor_v2.log 2>&1 &
```

**IMPORTANT:** Always set `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` — without this,
96 workers × 64 OpenBLAS threads = 6144 threads → OS limit exceeded → crash.

### Known Issues Fixed in v2.0

#### 1. OpenBLAS Thread Explosion
**Error:** `pthread_create failed: Resource temporarily unavailable`
**Fix:** `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` in launch command

#### 2. Reward Explosion (ep_rew_mean = -11,600,000)
**Cause:** ADD action could compound positions without limit
**Fix:** Added position caps and reward clipping in kat_env_v2.py:
```python
self._position = np.clip(self._position, -3.0, 3.0)
pnl_return = np.clip(pnl_return, -1.0, 1.0)
```

#### 3. DuckDB Column Name
**Error:** `Referenced column "date" not found`
**Cause:** market_data_continuous uses `ts` not `date`
**Fix:** Use `SELECT ts as date` in all queries

#### 4. Technical Feature Count Mismatch
**Error:** `Expected 25 technical features, got 18`
**Fix:** Updated assert to 18, TECHNICAL_FEATURES=108 (6×18)

#### 5. Binary Log File
**Cause:** Two competing processes writing to same log
**Fix:** Kill old process first, then restart fresh

#### 6. Two Competing Training Processes
**Always check before launching:**
```bash
pgrep -a python3 | grep stage3
```
Kill any old processes before starting new run.

### v2.0 Training Results (First Run)
- Positive reward at **1.5M steps** (vs never in v1.0)
- FPS **5,000+** (vs 2,400 in v1.0)
- ep_rew_mean climbing: 0.075 → 0.881 → 1.35 at 3M steps
- New best model saved at ~2M steps
- No early stopping, no KL explosions

### Database Schema (v2.0)
```
/data/kat/kat_v2.db (DuckDB)
├── macro_data              277,124 rows, 54 series, 2000-2025
├── market_data_continuous   20,519 rows, 6 symbols, 2015-2025
└── technical_features       20,519 rows, 108 features per symbol
```

### Obs Space Breakdown (v2.0)
```
Total: 1770 features
├── Macro:      1404  (54 series × 26 rolling features each)
├── Portfolio:   108  (equity, position, drawdown, etc.)
├── Futures:     150  (6 contracts × 25 OHLCV features)
└── Technical:   108  (6 contracts × 18 indicators)
```

### Hyperparameters (v2.0 — Final)
```python
learning_rate  = 1e-4
n_steps        = 8192    # 2x v1
batch_size     = 4096    # 2x v1
n_epochs       = 10      # 2x v1
gamma          = 0.995
gae_lambda     = 0.95
clip_range     = 0.15
ent_coef       = 0.05    # prevents entropy collapse
vf_coef        = 0.5
max_grad_norm  = 0.5
target_kl      = 0.02    # critical safety parameter
N_envs         = 96
device         = "cuda"
transaction_cost = 0.0   # SNB 0% commission
reward_scaling   = 0.1
```
