# KAT Training Guide — Complete Reference

## Overview
KAT (Katherina Algorithmic Trader) is a PPO-based RL trading system.
This guide documents everything learned from Stages 1-3 training sessions.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| Training server | Vast.ai RTX 4090, Netherlands DC |
| DB (training) | PostgreSQL local on Vast.ai |
| DB (permanent) | DuckDB file → copy to Vast.ai |
| Scripts | GitHub: gummihurdal/katherina-trader |
| Monitoring | Telegram bot notifications |
| Backups | Local laptop + GitHub |

### Vast.ai Instance Requirements
- **Disk:** 83GB minimum
- **RAM:** 128GB+ (1TB recommended)
- **GPU:** RTX 4090
- **Location:** Netherlands (same DC for multi-server)
- **Cost:** ~$0.30/hr

### SSH Connection
```bash
# From Hetzner/any server
ssh -i ~/.ssh/id_ed25519 -p PORT root@VAST_IP

# From Windows
ssh -i C:\Users\breka\.ssh\kat-hetzner_key -p PORT root@VAST_IP
```

---

## Pre-Launch Checklist (ALWAYS follow before training)

### 1. PostgreSQL Setup
```bash
# Set max_connections and tuning params
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
rm -rf /data/kat/checkpoints/stage3/best/*.pkl
rm -rf /data/kat/checkpoints/stage3/periodic/*.pkl
rm -f /data/kat/checkpoints/stage3/eval_logs/*
```

### 4. Check CPU Usage
```bash
top -bn1 | grep "Cpu(s)"
# Target: 60-80% CPU usage
# Adjust N_envs accordingly:
# 60% CPU → can increase N_envs
# 90% CPU → reduce N_envs
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
**Fix:** `rm -rf /data/kat/checkpoints/stage*/best/*.pkl /data/kat/checkpoints/stage*/periodic/*.pkl`

### 2. Inconsistent Train/Eval Obs Size
**Error:** Train obs=1722, Eval obs=1696
**Cause:** `macro_raw` filtered by date BEFORE pivot → eval period missing some series
**Fix:** In `_build_features()` — pivot on FULL macro data first, then filter pivot by date:
```python
# WRONG — filter before pivot
macro_raw = macro_raw[(macro_raw["ts"] >= sd) & (macro_raw["ts"] <= ed)]
macro_pivot = macro_raw.pivot_table(...)

# CORRECT — pivot first, filter after
macro_pivot = macro_raw.pivot_table(...)  # full data
macro_pivot = macro_pivot[(macro_pivot.index >= sd) & (macro_pivot.index <= ed)]
```

### 3. EOFError / BrokenPipeError on Startup
**Error:** `EOFError` or `BrokenPipeError: [Errno 32]`
**Cause 1:** Too many workers hitting PostgreSQL simultaneously
**Fix 1:** Increase max_connections to 200, add TCP keepalives
**Cause 2:** Script run without `if __name__ == "__main__"` guard
**Fix 2:** Always wrap training code in `if __name__ == "__main__":`

### 4. KL Explosion / Early Stopping
**Error:** `Early stopping at step 2 due to reaching max kl: 0.03`
**Cause:** Reward shaping values too large (trade_bonus, inaction_penalty)
**Fix:** Keep bonuses small:
```python
inaction_penalty = 0.0002  # NOT 0.001
trade_bonus = 0.00005      # NOT 0.0002
```

### 5. Dead Policy (Always HOLD)
**Symptom:** `mean_reward=0.00`, `episode_length=261` every eval
**Cause:** Model discovers HOLD=0 reward is better than bad trades
**Fix:** Add small inaction penalty + tiny trade bonus to reward:
```python
inaction_penalty = 0.0002 if action == 0 and self._position == 0 else 0.0
trade_bonus = 0.00005 if action in [1, 2] else 0.0
reward = pnl_reward - cost_penalty - drawdown_penalty - inaction_penalty + trade_bonus
```

### 6. Timezone Comparison Error
**Error:** `TypeError: Invalid comparison between dtype=datetime64[us, UTC] and Timestamp`
**Fix:** Strip timezone before comparison:
```python
macro_raw["ts"] = pd.to_datetime(macro_raw["ts"]).dt.tz_localize(None).dt.normalize()
```

### 7. GPU Warning (MLP on GPU)
**Warning:** `You are trying to run PPO on the GPU with MlpPolicy`
**Fix:** Use KATPolicy (custom attention) with `device="cuda"` — this is GPU optimized

---

## Architecture

### Environment: KATEnvV3
- **Obs size:** 1722 (macro 1404 + portfolio 108 + futures 210)
- **Action space:** Discrete(5) — HOLD, BUY, SELL, ADD, CLOSE
- **Train split:** 2015-01-01 to 2023-12-31
- **Eval split:** 2024-01-01 to 2025-12-31
- **Test split:** 2026-01-01 onwards (never touch until final evaluation)

### Policy: KATPolicy
- Custom attention architecture — 3 streams (macro, portfolio, futures)
- Cross-attention between streams
- 1,880,710 parameters
- GPU-optimized (CUDA)

### Algorithm: PPO
- `learning_rate=1e-4`
- `n_steps=4096`
- `batch_size=2048`
- `n_epochs=5`
- `gamma=0.995`
- `target_kl=0.02` — critical safety parameter
- `ent_coef=0.01`
- `clip_range=0.15`
- `N_envs=96` (adjust based on CPU %)

---

## Reward Function
```python
# In KATEnvV3.step()
inaction_penalty = 0.0002 if action == 0 and self._position == 0 else 0.0
trade_bonus = 0.00005 if action in [1, 2] else 0.0
reward = (total_equity - prev_equity) / (prev_equity + 1e-8) * self.reward_scaling \
         - cost * 0.001 \
         - drawdown * 0.001 \
         - inaction_penalty \
         + trade_bonus
```

---

## Healthy Training Metrics

| Metric | Target | Warning |
|--------|--------|---------|
| approx_kl | < 0.02 | > 0.05 = danger |
| clip_fraction | 0.03-0.10 | > 0.20 = too aggressive |
| entropy_loss | -1.0 to -1.6 | > -0.5 = collapsed |
| explained_variance | > 0.5 after 10M steps | < 0 = not learning |
| eval/mean_reward | Positive after 20M steps | 0.00 = dead policy |

---

## Telegram Monitor
- **Bot token:** stored in `/kat_monitor.py`
- **Updates:** every 60 minutes
- **Alerts:** immediate on crash or completion
- **Monitor script:** `/kat_monitor.py` on Vast.ai

---

## Database

### Connection strings
```
# Local Vast.ai
postgresql://kat_db:KATguard2026@127.0.0.1:5432/kat_production

# Future: DuckDB
duckdb:///path/to/kat.db
```

### Tables
| Table | Rows | Description |
|-------|------|-------------|
| macro_data | 277,124 | 47 FRED macro series, 2000-2026 |
| market_data_continuous | 20,519 | 6 futures continuous contracts, daily |
| market_data | ~500K | Raw futures contracts |

### Export to DuckDB (migration)
```bash
# On PostgreSQL server
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
print('DuckDB created')
"
```

---

## Stage Roadmap

| Stage | Data | Algorithm | Status |
|-------|------|-----------|--------|
| 1 | Macro only | PPO MLP | ✅ Complete (overfit) |
| 2 | Macro only | PPO MLP | ✅ Complete (negative eval) |
| 3 | Macro + futures daily | PPO KATPolicy | 🔄 Running |
| 4 | + Options chains (DoltHub) | PPO KATPolicy | Pending |
| 5 | + Stocks + indices | PPO or A2C | Pending |
| Paper trading | All data | Best model | Pending |
| Live trading | All data | Best model | Pending |

---

## Multi-Server Training (Stage 4+)

For A2C distributed training across 4 Vast.ai servers:
- All servers in **Netherlands datacenter** (same DC = 10Gbps internal)
- Server 1: Parameter server + PostgreSQL DB
- Servers 2-4: Workers (64 envs each = 192 total envs)
- Expected FPS: ~10,000 (4x current)
- Cost: ~$1.20/hr vs $0.30/hr = ~$25 per 500M steps

---

## File Locations (Vast.ai)

```
/root/stage3_launch.py      — main training script
/root/kat_monitor.py        — Telegram monitor
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
# Check if training is running
pgrep -f stage3_launch && echo "RUNNING" || echo "DEAD"

# Watch training live
tail -f /tmp/stage3.log

# Check eval rewards
grep "mean_reward\|episode_reward\|New best" /tmp/stage3.log

# Check PostgreSQL health
tail -20 /var/log/postgresql/postgresql-16-main.log

# CPU usage
top -bn1 | grep "Cpu(s)"

# Restart after crash
pkill -f stage3_launch; pkill -f kat_monitor
rm -rf /data/kat/checkpoints/stage3/best/*.pkl
nohup python3 /kat_monitor.py > /tmp/monitor.log 2>&1 &
```

---

## Lessons Learned

1. **Always check disk size before renting Vast.ai** — minimum 83GB
2. **Always copy DB locally** — never train with remote DB (10x speed difference)
3. **Always verify train/eval obs size match** before launching
4. **Delete VecNormalize pkl files** when restarting with different obs size
5. **Keep reward shaping values tiny** — large values cause KL explosion
6. **Add `if __name__ == "__main__"` guard** — required for SubprocVecEnv
7. **PostgreSQL needs tuning** for 64+ concurrent connections
8. **MLP policy is CPU-bound** — use KATPolicy (attention) for GPU utilization
9. **Dead policy (HOLD forever)** — add tiny inaction penalty to reward
10. **FPS only improves with more parallel envs** — everything else is marginal

