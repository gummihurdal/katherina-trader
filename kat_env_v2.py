import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from typing import Optional
from sqlalchemy import create_engine

TARGET_OBS_DIM = 1518
ACTIONS = {0: "HOLD", 1: "BUY", 2: "SELL", 3: "ADD", 4: "CLOSE"}

ALL_SERIES = [
    "CL=F","CORN","CPER","DBC","GC=F","HG=F","PDBC","SOYB","WEAT",
    "COPPER_GOLD_RATIO","HYG_IEF_RATIO","SPY_TLT_RATIO","XLK_XLP_RATIO",
    "DX-Y.NYB",
    "EEM","EFA","EWG","EWJ","EWT","EWY","EWZ","FXI","INDA","RSX",
    "^FVX","^TNX","^TYX",
    "XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY",
    "BDI",
    "^EVZ","^GVZ","^MOVE","^OVX","^VIX","^VIX3M","^VVIX",
]
TRADEABLE = ["CL=F","GC=F","HG=F","^VIX","XLE","XLF","XLK","XLV","EEM","DX-Y.NYB"]
N_SYMBOLS = 10
PORTFOLIO_FEATURES = 108
FEATURES_PER_SERIES = 30


class KATEnvV2(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, db_uri, start_date="2015-01-01", end_date="2023-12-31",
                 initial_capital=10_000.0, symbols=None, transaction_cost=0.0002,
                 reward_scaling=0.01, max_position_pct=0.20):
        super().__init__()
        self.db_uri = db_uri
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.symbols = symbols or TRADEABLE
        self.n_symbols = len(self.symbols)
        self.transaction_cost = transaction_cost
        self.reward_scaling = reward_scaling
        self.max_position_pct = max_position_pct

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(TARGET_OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(5)

        self._step_idx = 0
        self._portfolio = {}
        self._load_data()

    def _load_data(self):
        engine = create_engine(self.db_uri)
        try:
            df = pd.read_sql(
                "SELECT series_id, ts, value FROM macro_data "
                "WHERE ts >= %(s)s AND ts <= %(e)s ORDER BY ts, series_id",
                engine, params={"s": self.start_date, "e": self.end_date}
            )
        finally:
            engine.dispose()

        wide = df.pivot_table(index="ts", columns="series_id", values="value").sort_index()
        wide = wide.ffill().bfill()
        available = [s for s in ALL_SERIES if s in wide.columns]
        wide = wide[available]

        blocks = []
        for col in available:
            s = wide[col]
            ret = s.pct_change()
            ma20  = s.rolling(20).mean()
            ma50  = s.rolling(50).mean()
            ma200 = s.rolling(200).mean()
            std20  = s.rolling(20).std() + 1e-8
            std50  = s.rolling(50).std() + 1e-8
            std252 = s.rolling(252).std() + 1e-8
            vol21  = ret.rolling(21).std() * np.sqrt(252)
            vol63  = ret.rolling(63).std() * np.sqrt(252)
            hi252  = s.rolling(252).max()
            lo252  = s.rolling(252).min()
            rng252 = hi252 - lo252 + 1e-8

            feats = np.column_stack([
                ((s - s.rolling(252).mean()) / std252).fillna(0),   # 0 z252
                ret.fillna(0),                                        # 1 r1
                s.pct_change(5).fillna(0),                           # 2 r5
                s.pct_change(21).fillna(0),                          # 3 r21
                s.pct_change(63).fillna(0),                          # 4 r63
                (s / (ma20 + 1e-8) - 1).fillna(0),                  # 5 ma20r
                (s / (ma50 + 1e-8) - 1).fillna(0),                  # 6 ma50r
                (s / (ma200 + 1e-8) - 1).fillna(0),                 # 7 ma200r
                ((s - ma20) / std20).fillna(0),                      # 8 z20
                ((s - s.rolling(63).mean()) / (s.rolling(63).std() + 1e-8)).fillna(0),  # 9 z63
                vol21.fillna(0),                                      # 10 vol21
                ((s - lo252) / rng252).fillna(0.5),                  # 11 hi52w_pct
                ((hi252 - s) / rng252).fillna(0.5),                  # 12 lo52w_pct
                s.pct_change(21).fillna(0),                          # 13 mom1m
                s.pct_change(63).fillna(0),                          # 14 mom3m
                s.pct_change(126).fillna(0),                         # 15 mom6m
                s.pct_change(252).fillna(0),                         # 16 mom12m
                ((s - (ma20 - 2*std20)) / (4*std20)).fillna(0.5),   # 17 bb_pos
                (s > ma200).astype(float),                            # 18 regime
                ((s - ma50) / std50).fillna(0),                      # 19 mr_sig
                (vol21 / (vol63 + 1e-8) - 1).fillna(0),             # 20 vol_reg
                ret.rolling(63).skew().clip(-3, 3).fillna(0),        # 21 skew63
                (s / (ma200 + 1e-8) - 1).abs().fillna(0),           # 22 trend
                s.pct_change(21).diff().fillna(0),                   # 23 accel
                (s.pct_change(21) / (vol21 + 1e-8)).fillna(0),      # 24 vadj_r
                (ret * vol21).fillna(0),                              # 25 rxv
                ((s - s.rolling(252).mean()) / std252).clip(-3, 3).fillna(0),  # 26 z_clip
                ((s > ma200).astype(float) * s.pct_change(21)).fillna(0),      # 27 reg_mom
                ((s - ma20) / std20 * (s - s.rolling(63).mean()) / (s.rolling(63).std() + 1e-8)).fillna(0),  # 28 zrsi
                ret.rolling(21).mean().fillna(0),                    # 29 ret_ma21
            ]).astype(np.float32)

            blocks.append(feats)

        self._feature_matrix = np.hstack(blocks)
        self._dates = wide.index.values
        self._wide = wide
        print(f"Loaded: {len(self._dates)} days | features: {self._feature_matrix.shape}")

    def _init_portfolio(self):
        self._portfolio = {
            "cash": self.initial_capital,
            "equity": self.initial_capital,
            "peak_equity": self.initial_capital,
            "positions": {s: 0.0 for s in self.symbols},
            "entry_prices": {s: 0.0 for s in self.symbols},
            "holding_days": {s: 0 for s in self.symbols},
            "realized_pnl": 0.0,
            "trade_count": 0,
            "daily_returns": [],
        }

    def _get_prices(self):
        return {s: float(self._wide[s].iloc[self._step_idx])
                if s in self._wide.columns else 1.0
                for s in self.symbols}

    def _portfolio_obs(self):
        p = self._portfolio
        prices = self._get_prices()
        equity = p["cash"] + sum(p["positions"][s] * prices.get(s, 1.0) for s in self.symbols)
        p["equity"] = equity
        p["peak_equity"] = max(p["peak_equity"], equity)

        f = []
        f.append(equity / self.initial_capital - 1)
        f.append(p["cash"] / (equity + 1e-8))
        f.append((p["peak_equity"] - equity) / (p["peak_equity"] + 1e-8))
        f.append(len([s for s in self.symbols if p["positions"][s] != 0]) / self.n_symbols)
        f.append(p["realized_pnl"] / self.initial_capital)
        f.append(p["trade_count"] / 1000.0)
        rets = p["daily_returns"]
        f.append(float(np.mean(rets[-63:]) / (np.std(rets[-63:]) + 1e-8) * np.sqrt(252))
                 if len(rets) >= 20 else 0.0)
        f.append(float(np.std(rets[-21:]) * np.sqrt(252)) if len(rets) >= 5 else 0.0)

        for sym in self.symbols:
            pos = p["positions"][sym]
            entry = p["entry_prices"][sym]
            price = prices.get(sym, 1.0)
            upnl = (price - entry) * pos if pos != 0 and entry > 0 else 0.0
            f += [
                pos / (equity + 1e-8),
                1.0 if pos > 0 else (-1.0 if pos < 0 else 0.0),
                upnl / (equity + 1e-8),
                min(p["holding_days"][sym] / 252.0, 1.0),
                (price - entry) / (entry + 1e-8) if entry > 0 else 0.0,
                0.0,
                1.0 if pos > 0 and upnl > 0 else 0.0,
                1.0 if pos != 0 else 0.0,
                min(abs(pos * price) / (equity + 1e-8), 1.0),
            ]

        date = pd.Timestamp(self._dates[self._step_idx])
        f += [
            np.sin(2 * np.pi * date.dayofweek / 5),
            np.cos(2 * np.pi * date.dayofweek / 5),
            np.sin(2 * np.pi * date.month / 12),
            np.cos(2 * np.pi * date.month / 12),
            np.sin(2 * np.pi * date.quarter / 4),
            np.cos(2 * np.pi * date.quarter / 4),
            self._step_idx / max(len(self._dates), 1),
            float(date.month in [1, 4, 7, 10]),
            float(date.month == 12),
            float(date.dayofweek == 4),
        ]

        arr = np.array(f, dtype=np.float32)
        if len(arr) < PORTFOLIO_FEATURES:
            arr = np.pad(arr, (0, PORTFOLIO_FEATURES - len(arr)))
        return np.clip(arr[:PORTFOLIO_FEATURES], -10, 10)

    def _get_obs(self):
        obs = np.concatenate([
            self._feature_matrix[self._step_idx],
            self._portfolio_obs()
        ])
        if len(obs) < TARGET_OBS_DIM:
            obs = np.pad(obs, (0, TARGET_OBS_DIM - len(obs)))
        return obs[:TARGET_OBS_DIM].astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._step_idx = 200
        self._init_portfolio()
        return self._get_obs(), {}

    def step(self, action):
        prices = self._get_prices()
        prev_eq = self._portfolio["equity"]
        primary = self.symbols[0]
        price = prices.get(primary, 1.0)
        equity = self._portfolio["cash"] + sum(
            self._portfolio["positions"][s] * prices.get(s, 1.0) for s in self.symbols)

        if action == 1 and self._portfolio["positions"][primary] == 0:
            size = (equity * self.max_position_pct) / (price + 1e-8)
            cost = size * price * (1 + self.transaction_cost)
            if cost <= self._portfolio["cash"]:
                self._portfolio["cash"] -= cost
                self._portfolio["positions"][primary] = size
                self._portfolio["entry_prices"][primary] = price
                self._portfolio["trade_count"] += 1

        elif action == 2 and self._portfolio["positions"][primary] == 0:
            size = (equity * self.max_position_pct) / (price + 1e-8)
            self._portfolio["cash"] += size * price * (1 - self.transaction_cost)
            self._portfolio["positions"][primary] = -size
            self._portfolio["entry_prices"][primary] = price
            self._portfolio["trade_count"] += 1

        elif action == 3 and self._portfolio["positions"][primary] > 0:
            add = (equity * 0.05) / (price + 1e-8)
            cost = add * price * (1 + self.transaction_cost)
            if cost <= self._portfolio["cash"]:
                self._portfolio["cash"] -= cost
                self._portfolio["positions"][primary] += add
                self._portfolio["trade_count"] += 1

        elif action == 4:
            for sym in self.symbols:
                pos = self._portfolio["positions"][sym]
                if pos != 0:
                    p2 = prices.get(sym, 1.0)
                    self._portfolio["cash"] += pos * p2 * (1 - self.transaction_cost * np.sign(pos))
                    self._portfolio["realized_pnl"] += (p2 - self._portfolio["entry_prices"][sym]) * pos
                    self._portfolio["positions"][sym] = 0
                    self._portfolio["entry_prices"][sym] = 0
                    self._portfolio["holding_days"][sym] = 0
                    self._portfolio["trade_count"] += 1

        for sym in self.symbols:
            if self._portfolio["positions"][sym] != 0:
                self._portfolio["holding_days"][sym] += 1

        new_eq = self._portfolio["cash"] + sum(
            self._portfolio["positions"][s] * prices.get(s, 1.0) for s in self.symbols)
        self._portfolio["equity"] = new_eq
        self._portfolio["peak_equity"] = max(self._portfolio["peak_equity"], new_eq)
        daily_ret = (new_eq - prev_eq) / (prev_eq + 1e-8)
        self._portfolio["daily_returns"].append(daily_ret)
        drawdown = (self._portfolio["peak_equity"] - new_eq) / (self._portfolio["peak_equity"] + 1e-8)
        reward = float(daily_ret * self.reward_scaling - drawdown * 0.001)

        self._step_idx += 1
        done = self._step_idx >= len(self._dates) - 1
        obs = self._get_obs() if not done else np.zeros(TARGET_OBS_DIM, dtype=np.float32)
        return obs, reward, done, False, {
            "equity": new_eq, "daily_return": daily_ret, "drawdown": drawdown}

    def render(self):
        pass

    def close(self):
        pass
