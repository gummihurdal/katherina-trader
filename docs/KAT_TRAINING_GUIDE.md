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

