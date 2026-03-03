-- KAT — Initial Schema v2.0 (Signal Aggregator)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'trader' CHECK (role IN ('admin','trader')),
    settings JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    display_name TEXT,
    encrypted_key TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE signal_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_name TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('api_poll','webhook','internal')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT false,
    is_paper BOOLEAN DEFAULT true,
    max_allocation_pct DECIMAL(5,4) DEFAULT 0.2000,
    current_allocation_pct DECIMAL(5,4) DEFAULT 0.0000,
    total_signals INT DEFAULT 0,
    approved_signals INT DEFAULT 0,
    rejected_signals INT DEFAULT 0,
    total_pnl DECIMAL(12,2) DEFAULT 0.00,
    win_count INT DEFAULT 0,
    loss_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id) ON DELETE CASCADE,
    endpoint_token TEXT UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    is_active BOOLEAN DEFAULT true,
    ip_whitelist TEXT[] DEFAULT '{}',
    last_received_at TIMESTAMPTZ,
    total_received INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT false,
    params JSONB DEFAULT '{}'::jsonb,
    performance JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id) ON DELETE SET NULL,
    source_strategy_id TEXT,
    source_strategy_name TEXT,
    action TEXT NOT NULL CHECK (action IN ('buy','sell','bto','sto','btc','stc')),
    asset_class TEXT NOT NULL CHECK (asset_class IN ('stock','option','future','forex','crypto')),
    symbol TEXT NOT NULL,
    quantity INT NOT NULL,
    order_type TEXT DEFAULT 'market' CHECK (order_type IN ('market','limit','stop','stop_limit')),
    limit_price DECIMAL(12,4),
    stop_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    take_profit DECIMAL(12,4),
    expiry DATE,
    strike DECIMAL(12,4),
    put_call TEXT CHECK (put_call IN ('call','put',NULL)),
    legs JSONB,
    risk_approved BOOLEAN,
    risk_checks JSONB,
    risk_rejection_reason TEXT,
    trade_id UUID,
    raw_payload JSONB,
    confidence DECIMAL(3,2),
    urgency TEXT DEFAULT 'normal' CHECK (urgency IN ('immediate','normal','low')),
    notes TEXT,
    signal_time TIMESTAMPTZ,
    received_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    source_id UUID REFERENCES signal_sources(id) ON DELETE SET NULL,
    signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    asset_class TEXT DEFAULT 'stock',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long','short')),
    order_type TEXT DEFAULT 'market',
    quantity INT NOT NULL,
    entry_price DECIMAL(12,4),
    exit_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    take_profit DECIMAL(12,4),
    expiry DATE,
    strike DECIMAL(12,4),
    put_call TEXT,
    legs JSONB,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','open','partial','closed','cancelled','rejected')),
    pnl DECIMAL(12,2),
    pnl_pct DECIMAL(8,4),
    fees DECIMAL(8,2) DEFAULT 0.00,
    is_paper BOOLEAN DEFAULT true,
    risk_checks JSONB,
    metadata JSONB DEFAULT '{}'::jsonb,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE signals ADD CONSTRAINT fk_signals_trade FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL;

CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    source_id UUID REFERENCES signal_sources(id) ON DELETE SET NULL,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    asset_class TEXT DEFAULT 'stock',
    quantity INT NOT NULL,
    avg_cost DECIMAL(12,4) NOT NULL,
    current_price DECIMAL(12,4),
    unrealized_pnl DECIMAL(12,2),
    stop_loss DECIMAL(12,4),
    is_paper BOOLEAN DEFAULT true,
    opened_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE risk_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    portfolio_value DECIMAL(14,2),
    total_risk_pct DECIMAL(5,4),
    daily_pnl DECIMAL(12,2),
    daily_pnl_pct DECIMAL(8,4),
    weekly_pnl DECIMAL(12,2),
    weekly_pnl_pct DECIMAL(8,4),
    cash_pct DECIMAL(5,4),
    positions_count INT,
    source_allocations JSONB,
    snapshot_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id UUID,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    severity TEXT DEFAULT 'info' CHECK (severity IN ('info','warning','critical')),
    source_id UUID REFERENCES signal_sources(id) ON DELETE SET NULL,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_signals_user_time ON signals(user_id, received_at DESC);
CREATE INDEX idx_signals_source ON signals(source_id, received_at DESC);
CREATE INDEX idx_signals_approved ON signals(user_id, risk_approved, received_at DESC);
CREATE INDEX idx_trades_user_time ON trades(user_id, created_at DESC);
CREATE INDEX idx_trades_source ON trades(source_id, created_at DESC);
CREATE INDEX idx_trades_status ON trades(user_id, status);
CREATE INDEX idx_positions_user ON positions(user_id);
CREATE INDEX idx_sources_user ON signal_sources(user_id, is_active);
CREATE INDEX idx_webhooks_token ON webhooks(endpoint_token);
CREATE INDEX idx_risk_snapshots ON risk_snapshots(user_id, snapshot_at DESC);
CREATE INDEX idx_alerts_user ON alerts(user_id, is_read, created_at DESC);

-- RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_data" ON users FOR ALL USING (auth.uid() = id);
CREATE POLICY "own_data" ON api_keys FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON signal_sources FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON webhooks FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON strategies FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON signals FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON trades FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON positions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON risk_snapshots FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON audit_log FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON alerts FOR ALL USING (auth.uid() = user_id);
