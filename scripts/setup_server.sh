#!/bin/bash
# ================================================================
# KAT v3 — Hetzner EX63 Server Setup
# Ubuntu 24.04 LTS
#
# RUN AS ROOT on a fresh server:
#   curl -sO https://raw.githubusercontent.com/gummihurdal/katherina-trader/main/scripts/setup_server.sh
#   chmod +x setup_server.sh
#   ./setup_server.sh
#
# What this installs:
#   - System hardening (firewall, SSH, fail2ban)
#   - Python 3.12 + all KAT dependencies
#   - PostgreSQL 16 (local, optimized for ML workloads)
#   - Redis 7 (signal queue + hot state)
#   - MLflow (experiment tracking)
#   - KAT directory structure
#   - All DB migrations
#   - Systemd services (auto-start on reboot)
#   - Logrotate
# ================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log()     { echo -e "${GREEN}[KAT]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
section() { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════${NC}"; \
            echo -e "${BOLD}${BLUE}  $1${NC}"; \
            echo -e "${BOLD}${BLUE}══════════════════════════════════════${NC}"; }

# ── Verify root ───────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Must run as root. Use: sudo ./setup_server.sh"

# ── Configuration — edit before running ──────────────────────────
KAT_USER="kat"
KAT_HOME="/opt/kat"
DATA_DIR="/data/kat"
DB_NAME="kat_production"
DB_USER="kat_db"
DB_PASS="${KAT_DB_PASSWORD:-$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)}"
REDIS_PASS="${KAT_REDIS_PASSWORD:-$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)}"
MLFLOW_PORT=5001
KAT_API_PORT=8000

# ── Save generated passwords ──────────────────────────────────────
SECRETS_FILE="/root/kat_secrets.txt"

section "KAT v3 — Server Setup Starting"
log "Server: $(hostname) | OS: $(lsb_release -d | cut -f2)"
log "Secrets will be saved to: $SECRETS_FILE"


# ================================================================
# 1. SYSTEM UPDATE & BASE PACKAGES
# ================================================================
section "1. System Update"

apt-get update -qq
apt-get upgrade -y -qq

apt-get install -y -qq \
    build-essential \
    curl wget git unzip \
    htop iotop nethogs \
    ufw fail2ban \
    software-properties-common \
    apt-transport-https ca-certificates \
    gnupg lsb-release \
    libpq-dev \
    libssl-dev libffi-dev \
    libblas-dev liblapack-dev \
    pkg-config \
    jq \
    logrotate \
    screen tmux

log "Base packages installed ✓"


# ================================================================
# 2. SECURITY HARDENING
# ================================================================
section "2. Security Hardening"

# Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow $KAT_API_PORT/tcp    # KAT API
ufw allow $MLFLOW_PORT/tcp     # MLflow UI (bind to localhost in prod)
ufw --force enable
log "UFW firewall configured ✓"

# Fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s
EOF
systemctl enable fail2ban
systemctl restart fail2ban
log "Fail2ban configured ✓"

# SSH hardening
sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
# Note: add your SSH public key before disabling password auth
# systemctl restart sshd
log "SSH hardened (password auth still on — add your key first, then disable) ✓"

# System limits for ML workloads
cat >> /etc/security/limits.conf << 'EOF'
kat soft nofile 65536
kat hard nofile 65536
kat soft nproc  32768
kat hard nproc  32768
EOF

# Kernel tuning for Postgres + Redis
cat >> /etc/sysctl.conf << 'EOF'
# KAT performance tuning
vm.overcommit_memory = 1          # Redis requirement
vm.swappiness = 10                # Prefer RAM over swap
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
fs.file-max = 200000
EOF
sysctl -p
log "System limits and kernel tuning applied ✓"


# ================================================================
# 3. KAT USER
# ================================================================
section "3. KAT User"

if ! id "$KAT_USER" &>/dev/null; then
    useradd -m -s /bin/bash -d $KAT_HOME $KAT_USER
    log "User '$KAT_USER' created ✓"
else
    log "User '$KAT_USER' already exists ✓"
fi


# ================================================================
# 4. PYTHON 3.12
# ================================================================
section "4. Python 3.12"

# Ubuntu 24.04 ships Python 3.12 natively — no PPA needed, no distutils (removed in 3.12+)
apt-get install -y -qq python3.12 python3.12-venv python3.12-dev python3-pip

# pip already available via python3-pip
python3.12 -m pip install --upgrade pip --break-system-packages 2>/dev/null || true

# Virtual environment
python3.12 -m venv $KAT_HOME/venv
source $KAT_HOME/venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

PYTHON_VERSION=$(python3.12 --version)
log "Python: $PYTHON_VERSION ✓"


# ================================================================
# 5. POSTGRESQL 16
# ================================================================
section "5. PostgreSQL 16"

# Add PostgreSQL official repo
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
    gpg --dearmor | tee /etc/apt/trusted.gpg.d/postgresql.gpg > /dev/null

echo "deb [signed-by=/etc/apt/trusted.gpg.d/postgresql.gpg] \
    https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list

apt-get update -qq
apt-get install -y -qq postgresql-16 postgresql-client-16 postgresql-contrib-16

# Start PostgreSQL
systemctl enable postgresql
systemctl start postgresql

# Wait for PostgreSQL socket to be ready
for i in $(seq 1 15); do
    pg_isready -q && break
    echo "[KAT] Waiting for PostgreSQL ($i/15)..."
    sleep 2
done

# ── Create DB user and database ───────────────────────────────────
sudo -u postgres psql << EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
ALTER USER $DB_USER CREATEDB;
EOF

# ── PostgreSQL config — tuned for EX63 (20 cores, 64GB DDR5) ───────
PG_CONF="/etc/postgresql/16/main/postgresql.conf"

# Only append tuning block once
if ! grep -q "KAT ML Workload Tuning" $PG_CONF; then
cat >> $PG_CONF << 'EOF'

# ── KAT ML Workload Tuning ─────────────────────────────────────────
# Server: Hetzner EX63 — 20 cores, 64GB DDR5, 2x1TB NVMe Gen4

# Memory
shared_buffers          = 16GB
effective_cache_size    = 48GB
work_mem                = 128MB
maintenance_work_mem    = 2GB
huge_pages              = try

# Parallelism
max_parallel_workers_per_gather = 8
max_parallel_workers            = 20
max_worker_processes            = 24

# WAL / Checkpointing
wal_buffers             = 64MB
checkpoint_completion_target = 0.9
min_wal_size            = 1GB
max_wal_size            = 4GB

# NVMe SSD
random_page_cost        = 1.1
effective_io_concurrency = 200
seq_page_cost           = 1.0

# Connections
max_connections         = 200

# Logging
log_min_duration_statement = 1000
log_checkpoints            = on
log_lock_waits             = on

# Statistics
track_io_timing         = on
track_functions         = all
EOF
fi

# Allow local connections
cat >> /etc/postgresql/16/main/pg_hba.conf << EOF
# KAT local access
local   $DB_NAME    $DB_USER                        md5
host    $DB_NAME    $DB_USER    127.0.0.1/32        md5
EOF

systemctl restart postgresql

log "PostgreSQL 16 installed and configured ✓"
log "DB: $DB_NAME | User: $DB_USER"


# ================================================================
# 6. REDIS 7
# ================================================================
section "6. Redis 7"

apt-get install -y -qq redis-server

# Redis config — optimized for signal queue use
REDIS_CONF="/etc/redis/redis.conf"
cp $REDIS_CONF ${REDIS_CONF}.orig

sed -i "s/# requirepass foobared/requirepass $REDIS_PASS/" $REDIS_CONF
sed -i 's/bind 127.0.0.1 -::1/bind 127.0.0.1/' $REDIS_CONF
sed -i 's/# maxmemory <bytes>/maxmemory 4gb/' $REDIS_CONF
sed -i 's/# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' $REDIS_CONF
sed -i 's/appendonly no/appendonly yes/' $REDIS_CONF

# Persistence for signal queue durability
echo "save 900 1"    >> $REDIS_CONF
echo "save 300 10"   >> $REDIS_CONF
echo "save 60 10000" >> $REDIS_CONF

systemctl enable redis-server
systemctl restart redis-server

log "Redis 7 configured ✓"


# ================================================================
# 7. DIRECTORY STRUCTURE
# ================================================================
section "7. KAT Directory Structure"

mkdir -p \
    $DATA_DIR/postgres \
    $DATA_DIR/models/checkpoints/stage1 \
    $DATA_DIR/models/checkpoints/stage2 \
    $DATA_DIR/models/production \
    $DATA_DIR/training_buffer \
    $DATA_DIR/price_data/parquet \
    $DATA_DIR/orats/backtests \
    $DATA_DIR/orats/live \
    $DATA_DIR/signals/archive \
    $DATA_DIR/logs \
    $DATA_DIR/mlflow \
    $KAT_HOME/app \
    $KAT_HOME/scripts \
    $KAT_HOME/venv

chown -R $KAT_USER:$KAT_USER $DATA_DIR $KAT_HOME

log "Directory structure created ✓"
log "Layout:"
log "  $DATA_DIR/           ← all data"
log "  $DATA_DIR/models/    ← AI model weights"
log "  $DATA_DIR/orats/     ← ORATS backtest cache"
log "  $DATA_DIR/price_data ← Polygon OHLCV parquet"
log "  $KAT_HOME/app/       ← KAT Python engine"


# ================================================================
# 8. PYTHON DEPENDENCIES
# ================================================================
section "8. Python Dependencies"

source $KAT_HOME/venv/bin/activate

# TA-Lib replaced by pandas-ta (pure Python, no C build required)

# Core
pip install -q \
    fastapi uvicorn[standard] \
    httpx pydantic python-dotenv \
    APScheduler \
    python-telegram-bot

# Database
pip install -q \
    psycopg2-binary \
    sqlalchemy \
    alembic \
    redis \
    supabase   # still needed for frontend sync

# Data
pip install -q \
    numpy pandas pyarrow \
    pandas-ta \
    polygon-api-client \
    mplfinance matplotlib

# ML / AI — install PyTorch CPU (no GPU on EX63)
pip install -q \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

pip install -q \
    stable-baselines3 \
    sb3-contrib \
    gymnasium \
    mlflow

# IBKR
pip install -q ibapi

# Monitoring
pip install -q \
    prometheus-client \
    psutil

log "Python dependencies installed ✓"
pip list | grep -E "torch|stable|gymnasium|postgres|redis|mlflow" | \
    awk '{printf "  %-30s %s\n", $1, $2}'


# ================================================================
# 9. DATABASE SCHEMA
# ================================================================
section "9. Database Schema"

export PGPASSWORD="$DB_PASS"

# Run all migrations in order
MIGRATIONS_DIR="$KAT_HOME/app/supabase/migrations"

# Create schema inline (in case migrations aren't cloned yet)
sudo -u postgres psql -d $DB_NAME << 'EOSQL'

-- ── Extensions ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ── Price Bars ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_bars (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT        NOT NULL,
    timespan    TEXT        NOT NULL DEFAULT 'day',
    ts          TIMESTAMPTZ NOT NULL,
    open        DECIMAL     NOT NULL,
    high        DECIMAL     NOT NULL,
    low         DECIMAL     NOT NULL,
    close       DECIMAL     NOT NULL,
    volume      BIGINT,
    vwap        DECIMAL,
    n_trades    INT,
    UNIQUE(symbol, timespan, ts)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_ts ON price_bars(symbol, ts DESC);

-- ── ORATS Backtest Results ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orats_backtests (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT        NOT NULL,
    strategy        TEXT        NOT NULL,
    trade_date      DATE        NOT NULL,
    expiry_date     DATE,
    dte             INT,
    strike_call     DECIMAL,
    strike_put      DECIMAL,
    delta           DECIMAL,
    iv_rank         DECIMAL,
    iv_pct          DECIMAL,
    entry_price     DECIMAL,
    exit_price      DECIMAL,
    pnl_pct         DECIMAL,
    was_profitable  BOOLEAN,
    hold_days       INT,
    exit_reason     TEXT,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(symbol, strategy, trade_date, dte, delta)
);
CREATE INDEX IF NOT EXISTS idx_orats_symbol     ON orats_backtests(symbol, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_orats_strategy   ON orats_backtests(strategy, was_profitable);
CREATE INDEX IF NOT EXISTS idx_orats_iv_rank    ON orats_backtests(iv_rank, strategy);

-- ── Signal Sources ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signal_sources (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    config      JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ── Signals ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID REFERENCES signal_sources(id),
    symbol          TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    confidence      DECIMAL     DEFAULT 0,
    price           DECIMAL,
    stop_loss       DECIMAL,
    take_profit     DECIMAL,
    quantity        INT,
    strategy_name   TEXT,
    raw_payload     JSONB       DEFAULT '{}',
    status          TEXT        DEFAULT 'pending',
    fired_at        TIMESTAMPTZ DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol   ON signals(symbol, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status   ON signals(status, fired_at DESC);

-- ── Signal Snapshots (feedback loop input) ────────────────────────
CREATE TABLE IF NOT EXISTS signal_snapshots (
    snapshot_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id           UUID REFERENCES signals(id),
    source              TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    signal_action       TEXT NOT NULL,
    signal_confidence   DECIMAL DEFAULT 0,
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_at_signal     DECIMAL,
    market_features     JSONB,
    market_trend        TEXT,
    rsi_14              DECIMAL,
    macd_signal         DECIMAL,
    atr_pct             DECIMAL,
    volume_ratio        DECIMAL,
    bb_position         DECIMAL,
    iv_rank             DECIMAL,       -- ORATS IV rank at signal time
    iv_pct_1y           DECIMAL,       -- ORATS IV percentile (1yr)
    hour_of_day         INT,
    day_of_week         INT,
    minutes_since_open  INT,
    portfolio_heat      DECIMAL,
    cash_pct            DECIMAL,
    open_positions      INT,
    todays_pnl_pct      DECIMAL,
    source_win_rate_30d DECIMAL,
    full_state_vector   JSONB,
    outcome_tagged      BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_snapshots_source     ON signal_snapshots(source, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol     ON signal_snapshots(symbol, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_untagged   ON signal_snapshots(outcome_tagged) WHERE outcome_tagged = FALSE;

-- ── Signal Outcomes (feedback loop labels) ────────────────────────
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_id         UUID REFERENCES signal_snapshots(snapshot_id),
    symbol              TEXT NOT NULL,
    entry_price         DECIMAL,
    exit_price          DECIMAL,
    entry_time          TIMESTAMPTZ,
    exit_time           TIMESTAMPTZ,
    hold_minutes        INT,
    pnl_abs             DECIMAL,
    pnl_pct             DECIMAL,
    was_profitable      BOOLEAN,
    exit_reason         TEXT,
    max_favorable_excursion DECIMAL,
    max_adverse_excursion   DECIMAL,
    optimal_action      INT,
    reward_signal       DECIMAL,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ── Trades ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id       UUID REFERENCES signals(id),
    symbol          TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    quantity        INT         NOT NULL,
    entry_price     DECIMAL     NOT NULL,
    exit_price      DECIMAL,
    stop_loss       DECIMAL,
    take_profit     DECIMAL,
    entry_time      TIMESTAMPTZ DEFAULT now(),
    exit_time       TIMESTAMPTZ,
    pnl_abs         DECIMAL,
    pnl_pct         DECIMAL,
    exit_reason     TEXT,
    mode            TEXT        DEFAULT 'paper',
    broker_order_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trades_mode      ON trades(mode, entry_time DESC);

-- ── Positions ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          TEXT        NOT NULL UNIQUE,
    quantity        INT         NOT NULL,
    entry_price     DECIMAL     NOT NULL,
    current_price   DECIMAL,
    stop_loss       DECIMAL,
    take_profit     DECIMAL,
    unrealized_pnl  DECIMAL     DEFAULT 0,
    entry_time      TIMESTAMPTZ DEFAULT now(),
    mode            TEXT        DEFAULT 'paper',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Training Reports ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS training_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_date     DATE        NOT NULL,
    stage           INT         DEFAULT 2,
    decision        TEXT        NOT NULL,
    n_examples      INT,
    pre_accuracy    DECIMAL,
    post_accuracy   DECIMAL,
    accuracy_delta  DECIMAL,
    reward_delta    DECIMAL,
    win_rate        DECIMAL,
    sharpe_ratio    DECIMAL,
    max_drawdown    DECIMAL,
    buffer_stats    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Source Performance View ───────────────────────────────────────
CREATE OR REPLACE VIEW source_performance AS
SELECT
    ss.source,
    COUNT(*)                                            AS total_signals,
    COUNT(*) FILTER (WHERE so.was_profitable)           AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE so.was_profitable)::DECIMAL
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                                   AS win_rate_pct,
    ROUND(AVG(so.pnl_pct) * 100, 3)                    AS avg_pnl_pct,
    ROUND(SUM(so.pnl_abs), 2)                           AS total_pnl,
    ROUND(AVG(ss.signal_confidence), 3)                 AS avg_confidence,
    ROUND(AVG(ss.iv_rank), 1)                           AS avg_iv_rank,
    MAX(ss.fired_at)                                    AS last_signal_at
FROM signal_snapshots ss
LEFT JOIN signal_outcomes so ON so.snapshot_id = ss.snapshot_id
WHERE ss.fired_at > now() - interval '30 days'
GROUP BY ss.source
ORDER BY win_rate_pct DESC NULLS LAST;

-- ── Seed signal sources ───────────────────────────────────────────
INSERT INTO signal_sources (name, type, config) VALUES
    ('collective2',  'webhook', '{"poll_interval": 5}'),
    ('holly_ai',     'webhook', '{"provider": "tradeideas"}'),
    ('traderspost',  'webhook', '{"secret": ""}'),
    ('orats',        'api',     '{"base_url": "https://api.orats.io/datav2"}'),
    ('internal',     'engine',  '{"strategies": ["iron_condor", "momentum"]}')
ON CONFLICT DO NOTHING;

EOSQL

log "Database schema applied ✓"
log "Tables: price_bars, orats_backtests, signals, signal_snapshots,"
log "        signal_outcomes, trades, positions, training_reports"


# ================================================================
# 10. MLFLOW
# ================================================================
section "10. MLflow Experiment Tracking"

source $KAT_HOME/venv/bin/activate

# MLflow systemd service
cat > /etc/systemd/system/kat-mlflow.service << EOF
[Unit]
Description=KAT MLflow Tracking Server
After=network.target

[Service]
User=$KAT_USER
WorkingDirectory=$DATA_DIR/mlflow
Environment="PATH=$KAT_HOME/venv/bin"
ExecStart=$KAT_HOME/venv/bin/mlflow server \
    --host 127.0.0.1 \
    --port $MLFLOW_PORT \
    --backend-store-uri postgresql://$DB_USER:$DB_PASS@127.0.0.1/$DB_NAME \
    --default-artifact-root $DATA_DIR/mlflow/artifacts
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kat-mlflow
systemctl start kat-mlflow

log "MLflow running on http://127.0.0.1:$MLFLOW_PORT ✓"


# ================================================================
# 11. KAT ENGINE SERVICE
# ================================================================
section "11. KAT Engine Systemd Service"

cat > /etc/systemd/system/kat-engine.service << EOF
[Unit]
Description=KAT Trading Engine
After=network.target postgresql.service redis-server.service

[Service]
User=$KAT_USER
WorkingDirectory=$KAT_HOME/app
Environment="PATH=$KAT_HOME/venv/bin"
EnvironmentFile=$KAT_HOME/.env
ExecStart=$KAT_HOME/venv/bin/python -m backend.main
Restart=always
RestartSec=10
StandardOutput=append:$DATA_DIR/logs/kat-engine.log
StandardError=append:$DATA_DIR/logs/kat-engine-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
# Don't start yet — app code not cloned
log "KAT engine service registered (not started — clone repo first) ✓"


# ================================================================
# 12. ENVIRONMENT FILE
# ================================================================
section "12. Environment Configuration"

cat > $KAT_HOME/.env << EOF
# ── KAT v3 Environment ─────────────────────────────────────────────
KAT_MODE=paper
KAT_ENV=production

# Database (local Postgres)
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
DB_HOST=127.0.0.1
DB_PORT=5432

# Redis (local)
REDIS_URL=redis://:$REDIS_PASS@127.0.0.1:6379/0
REDIS_PASS=$REDIS_PASS

# Data directories
KAT_DATA_DIR=$DATA_DIR
KAT_MODELS_DIR=$DATA_DIR/models
KAT_BUFFER_DIR=$DATA_DIR/training_buffer
KAT_CHECKPOINT_DIR=$DATA_DIR/models/checkpoints

# MLflow
MLFLOW_TRACKING_URI=http://127.0.0.1:$MLFLOW_PORT

# IBKR
IBKR_HOST=127.0.0.1
IBKR_PAPER_PORT=7496
IBKR_LIVE_PORT=7497
IBKR_CLIENT_ID=1

# API Keys (fill in after subscribing)
POLYGON_API_KEY=your_polygon_key_here
ORATS_API_KEY=your_orats_key_here
COLLECTIVE2_API_KEY=your_c2_key_here
TELEGRAM_BOT_TOKEN=your_telegram_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Supabase (frontend sync only)
SUPABASE_URL=https://palmswzrpquwemhfrvxs.supabase.co
SUPABASE_SERVICE_KEY=your_service_key_here

# Training
TRAINING_INITIAL_CAPITAL=100000
TRAINING_N_PARALLEL_ENVS=8
EOF

chmod 600 $KAT_HOME/.env
chown $KAT_USER:$KAT_USER $KAT_HOME/.env
log ".env created at $KAT_HOME/.env (chmod 600) ✓"


# ================================================================
# 13. LOGROTATE
# ================================================================
section "13. Log Rotation"

cat > /etc/logrotate.d/kat << EOF
$DATA_DIR/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 $KAT_USER $KAT_USER
    postrotate
        systemctl kill -s HUP kat-engine.service 2>/dev/null || true
    endscript
}
EOF

log "Logrotate configured (30 days retention) ✓"


# ================================================================
# 14. MONITORING SCRIPT
# ================================================================
section "14. Health Check Script"

cat > $KAT_HOME/scripts/health_check.sh << 'HEALTH'
#!/bin/bash
# KAT Health Check — run anytime to see system status
echo "═══════════════════════════════════════════"
echo "  KAT v3 — System Health Check"
echo "  $(date)"
echo "═══════════════════════════════════════════"

check() {
    if systemctl is-active --quiet "$1"; then
        echo "  ✅ $1"
    else
        echo "  ❌ $1 — NOT RUNNING"
    fi
}

echo ""
echo "  SERVICES:"
check postgresql
check redis-server
check kat-mlflow
check kat-engine

echo ""
echo "  DATABASE:"
if pg_isready -h 127.0.0.1 -U kat_db -d kat_production -q 2>/dev/null; then
    TABLES=$(sudo -u postgres psql -d kat_production -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null)
    echo "  ✅ PostgreSQL — $TABLES tables"
    
    BARS=$(sudo -u postgres psql -d kat_production -t -c \
        "SELECT count(*) FROM price_bars" 2>/dev/null | tr -d ' ')
    echo "  📊 price_bars: $BARS rows"
    
    TRADES=$(sudo -u postgres psql -d kat_production -t -c \
        "SELECT count(*) FROM trades" 2>/dev/null | tr -d ' ')
    echo "  📈 trades: $TRADES rows"
else
    echo "  ❌ PostgreSQL — cannot connect"
fi

echo ""
echo "  DISK:"
df -h $DATA_DIR | tail -1 | awk '{printf "  💾 %s used of %s (%s)\n", $3, $2, $5}'

echo ""
echo "  MEMORY:"
free -h | grep Mem | awk '{printf "  🧠 %s used of %s\n", $3, $2}'

echo ""
echo "  MODELS:"
if [ -d "/data/kat/models/production" ]; then
    ls /data/kat/models/production/*.zip 2>/dev/null | \
        xargs -I{} sh -c 'echo "  🤖 $(basename {}): $(stat -c %y {} | cut -d. -f1)"' \
        || echo "  ⏳ No production model yet"
fi
echo "═══════════════════════════════════════════"
HEALTH

chmod +x $KAT_HOME/scripts/health_check.sh
chown $KAT_USER:$KAT_USER $KAT_HOME/scripts/health_check.sh


# ================================================================
# 15. SAVE SECRETS
# ================================================================
section "15. Saving Secrets"

cat > $SECRETS_FILE << EOF
# ================================================================
# KAT v3 — Generated Secrets
# Created: $(date)
# KEEP THIS FILE SECURE — chmod 600, do not commit to git
# ================================================================

DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS

REDIS_PASS=$REDIS_PASS

DATABASE_URL=postgresql://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME
REDIS_URL=redis://:$REDIS_PASS@127.0.0.1:6379/0

MLFLOW_URL=http://127.0.0.1:$MLFLOW_PORT
EOF

chmod 600 $SECRETS_FILE
log "Secrets saved to $SECRETS_FILE ✓"


# ================================================================
# DONE
# ================================================================
section "Setup Complete"

echo ""
echo -e "${GREEN}${BOLD}  KAT v3 — Server Ready${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Clone your repo:"
echo "     cd $KAT_HOME/app"
echo "     git clone https://github.com/gummihurdal/katherina-trader.git ."
echo ""
echo "  2. Fill in API keys:"
echo "     nano $KAT_HOME/.env"
echo "     (Add: POLYGON_API_KEY, ORATS_API_KEY, C2 key, Telegram)"
echo ""
echo "  3. Start the engine:"
echo "     systemctl start kat-engine"
echo ""
echo "  4. Health check:"
echo "     $KAT_HOME/scripts/health_check.sh"
echo ""
echo "  5. MLflow UI (tunnel first):"
echo "     ssh -L $MLFLOW_PORT:127.0.0.1:$MLFLOW_PORT user@your-server"
echo "     → http://localhost:$MLFLOW_PORT"
echo ""
echo "  Secrets file: $SECRETS_FILE"
echo ""
echo -e "${YELLOW}  ⚠️  Add your SSH public key before disabling password auth${NC}"
echo -e "${YELLOW}  ⚠️  Keep $SECRETS_FILE secure and backed up${NC}"
echo ""
