-- ================================================================
-- KAT Feedback Loop — Database Schema
-- Migration: 007_feedback_loop.sql
-- Run in Supabase SQL Editor
-- ================================================================

-- ── Signal Snapshots ──────────────────────────────────────────────
-- Full market context captured at the moment each signal fires.
-- This is the INPUT the AI learns from.

CREATE TABLE IF NOT EXISTS signal_snapshots (
    snapshot_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id           UUID REFERENCES signals(id) ON DELETE SET NULL,
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,

    -- Signal identity
    source              TEXT NOT NULL,
    source_strategy_id  TEXT,
    symbol              TEXT NOT NULL,
    signal_action       TEXT NOT NULL,          -- 'buy' or 'sell'
    signal_confidence   DECIMAL DEFAULT 0,
    signal_urgency      TEXT DEFAULT 'normal',
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Market context at signal time
    price_at_signal     DECIMAL,
    market_features     JSONB,                  -- 25-dim compact feature vector
    market_trend        TEXT,                   -- 'up', 'down', 'sideways'
    rsi_14              DECIMAL,
    macd_signal         DECIMAL,
    atr_pct             DECIMAL,
    volume_ratio        DECIMAL,
    bb_position         DECIMAL,

    -- Time context
    hour_of_day         INT,
    day_of_week         INT,
    minutes_since_open  INT,

    -- Portfolio context
    portfolio_heat      DECIMAL,
    cash_pct            DECIMAL,
    open_positions      INT,
    todays_pnl_pct      DECIMAL,

    -- Source performance context
    source_win_rate_30d DECIMAL,
    source_signal_count_today INT,

    -- Full state vector (for direct replay)
    full_state_vector   JSONB,

    -- Status
    outcome_tagged      BOOLEAN DEFAULT FALSE,

    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ── Signal Outcomes ───────────────────────────────────────────────
-- What actually happened after each signal.
-- This is the LABEL the AI learns from.

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID REFERENCES signal_snapshots(snapshot_id) ON DELETE CASCADE,
    trade_id            UUID REFERENCES trades(id) ON DELETE SET NULL,
    symbol              TEXT NOT NULL,

    -- Fill details
    entry_price         DECIMAL,
    exit_price          DECIMAL,
    entry_time          TIMESTAMPTZ,
    exit_time           TIMESTAMPTZ,
    hold_minutes        INT,

    -- Results
    pnl_abs             DECIMAL,
    pnl_pct             DECIMAL,
    was_profitable      BOOLEAN,
    exit_reason         TEXT,                   -- 'stop_loss', 'take_profit', 'signal', 'eod'
    max_favorable_excursion  DECIMAL,
    max_adverse_excursion    DECIMAL,

    -- RL training labels
    optimal_action      INT,                    -- 1=follow signal, 0=ignore
    reward_signal       DECIMAL,                -- computed reward for RL

    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ── Training Reports ──────────────────────────────────────────────
-- Nightly retrain results.

CREATE TABLE IF NOT EXISTS training_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date                DATE NOT NULL,
    decision            TEXT NOT NULL,          -- 'ACCEPTED' or 'REJECTED'
    n_examples          INT,
    pre_accuracy        DECIMAL,
    post_accuracy       DECIMAL,
    accuracy_delta      DECIMAL,
    reward_delta        DECIMAL,
    buffer_stats        JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ── Source Performance (materialized view) ────────────────────────

CREATE OR REPLACE VIEW source_performance AS
SELECT
    ss.source,
    COUNT(*)                                        AS total_signals,
    COUNT(*) FILTER (WHERE so.was_profitable)       AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE so.was_profitable)::DECIMAL
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                               AS win_rate_pct,
    ROUND(AVG(so.pnl_pct) * 100, 3)                AS avg_pnl_pct,
    ROUND(SUM(so.pnl_abs), 2)                       AS total_pnl,
    ROUND(AVG(so.hold_minutes), 0)                  AS avg_hold_minutes,
    ROUND(AVG(ss.signal_confidence), 3)             AS avg_confidence,
    MAX(ss.fired_at)                                AS last_signal_at
FROM signal_snapshots ss
LEFT JOIN signal_outcomes so ON so.snapshot_id = ss.snapshot_id
WHERE ss.fired_at > now() - interval '30 days'
GROUP BY ss.source
ORDER BY win_rate_pct DESC NULLS LAST;

-- ── Indexes ───────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_snapshots_user     ON signal_snapshots(user_id, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol   ON signal_snapshots(symbol, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_source   ON signal_snapshots(source, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_untagged ON signal_snapshots(outcome_tagged) WHERE outcome_tagged = FALSE;
CREATE INDEX IF NOT EXISTS idx_outcomes_snapshot  ON signal_outcomes(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_trade     ON signal_outcomes(trade_id);
CREATE INDEX IF NOT EXISTS idx_reports_date       ON training_reports(date DESC);

-- ── RLS ───────────────────────────────────────────────────────────

ALTER TABLE signal_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_outcomes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_reports  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_data" ON signal_snapshots  FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "own_data" ON signal_outcomes   FOR ALL USING (
    snapshot_id IN (SELECT snapshot_id FROM signal_snapshots WHERE user_id = auth.uid())
);
CREATE POLICY "own_data" ON training_reports  FOR ALL USING (true); -- admin only in production
