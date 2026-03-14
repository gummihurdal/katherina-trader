"""
KAT v2.0 — Custom Attention Policy
=====================================
4-stream cross-attention architecture:
  Stream 1: Macro      (1404 → 512 → 256)
  Stream 2: Portfolio  (108  → 128 → 256)
  Stream 3: Futures    (210  → 256 → 256)
  Stream 4: Technical  (150  → 256 → 256)  [NEW in v2.0]

Cross-attention: 8 heads between all 4 streams
Final projection: 1024 → 512 → 256

Architecture rationale:
  - 4 streams allow specialized encoders for each data type
  - Cross-attention lets macro context modulate technical signals
  - Technical stream prevents model from rediscovering RSI/MACD from raw prices
  - Similar to Temporal Fusion Transformer (TFT) that achieved 63% live accuracy

Author: KAT Research Team
Version: 2.0
"""

import torch
import torch.nn as nn
import numpy as np
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3 import PPO
from gymnasium import spaces
import gymnasium as gym

# ── Stream Dimensions (must match feature_pipeline.py) ───────────────────────
MACRO_DIM       = 1404
PORTFOLIO_DIM   = 108
FUTURES_DIM     = 210
TECHNICAL_DIM   = 150
HIDDEN_DIM      = 256
N_HEADS         = 8


# ── Feature Extractor ─────────────────────────────────────────────────────────

class KATFeatureExtractorV2(BaseFeaturesExtractor):
    """
    4-stream cross-attention feature extractor.

    Takes flat observation vector and routes to 4 specialized encoders,
    then applies cross-attention to let streams inform each other.

    Output: 1024-dimensional latent representation
    """

    def __init__(self, observation_space: spaces.Box, hidden_dim: int = HIDDEN_DIM):
        features_dim = hidden_dim * 4  # 4 streams × 256 = 1024
        super().__init__(observation_space, features_dim=features_dim)

        self.hidden_dim = hidden_dim
        obs_size = observation_space.shape[0]

        # Compute stream boundaries
        self.macro_end      = MACRO_DIM
        self.portfolio_end  = MACRO_DIM + PORTFOLIO_DIM
        self.futures_end    = MACRO_DIM + PORTFOLIO_DIM + FUTURES_DIM
        self.technical_end  = obs_size  # rest

        # ── Stream encoders ───────────────────────────────────────────────────
        self.macro_encoder = nn.Sequential(
            nn.Linear(MACRO_DIM, 512),
            nn.LayerNorm(512),
            nn.GELU(),
            nn.Linear(512, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )
        self.portfolio_encoder = nn.Sequential(
            nn.Linear(PORTFOLIO_DIM, 128),
            nn.LayerNorm(128),
            nn.GELU(),
            nn.Linear(128, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )
        self.futures_encoder = nn.Sequential(
            nn.Linear(FUTURES_DIM, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Linear(256, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )
        self.technical_encoder = nn.Sequential(
            nn.Linear(TECHNICAL_DIM, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Linear(256, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )

        # ── Cross-attention ────────────────────────────────────────────────────
        # MultiheadAttention: (seq_len=4, batch, hidden_dim)
        self.cross_attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=N_HEADS,
            dropout=0.1,
            batch_first=True,  # (batch, seq, dim)
        )
        self.attention_norm = nn.LayerNorm(hidden_dim)

        # ── Final projection ──────────────────────────────────────────────────
        self.final_proj = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim * 2),
            nn.LayerNorm(hidden_dim * 2),
            nn.GELU(),
            nn.Linear(hidden_dim * 2, features_dim),
            nn.LayerNorm(features_dim),
            nn.GELU(),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through 4-stream cross-attention architecture.

        Args:
            obs: (batch, obs_size) flat observation tensor

        Returns:
            features: (batch, features_dim=1024)
        """
        # Split observation into 4 streams
        macro_in     = obs[:, :self.macro_end]
        portfolio_in = obs[:, self.macro_end:self.portfolio_end]
        futures_in   = obs[:, self.portfolio_end:self.futures_end]
        technical_in = obs[:, self.futures_end:]

        # Encode each stream
        macro_enc     = self.macro_encoder(macro_in)       # (B, 256)
        portfolio_enc = self.portfolio_encoder(portfolio_in)  # (B, 256)
        futures_enc   = self.futures_encoder(futures_in)   # (B, 256)
        technical_enc = self.technical_encoder(technical_in)  # (B, 256)

        # Stack for cross-attention: (B, 4, 256)
        streams = torch.stack(
            [macro_enc, portfolio_enc, futures_enc, technical_enc], dim=1
        )

        # Cross-attention: each stream attends to all others
        attended, _ = self.cross_attention(streams, streams, streams)
        attended = self.attention_norm(attended + streams)  # residual connection

        # Flatten attended streams: (B, 4*256=1024)
        out = attended.reshape(attended.shape[0], -1)

        # Final projection: (B, features_dim)
        return self.final_proj(out)

    def forward_actor(self, obs: torch.Tensor) -> torch.Tensor:
        return self.forward(obs)

    def forward_critic(self, obs: torch.Tensor) -> torch.Tensor:
        return self.forward(obs)


# ── Policy ────────────────────────────────────────────────────────────────────

class KATPolicyV2(ActorCriticPolicy):
    """
    KAT Policy v2.0 — wraps KATFeatureExtractorV2.

    Policy network: 1024 → 256 → 5 actions
    Value network:  1024 → 256 → 1
    """

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs,
            features_extractor_class=KATFeatureExtractorV2,
            features_extractor_kwargs={"hidden_dim": HIDDEN_DIM},
            net_arch=dict(pi=[256], vf=[256]),
        )


def make_kat_policy_v2():
    """Return policy class and kwargs for PPO constructor."""
    return KATPolicyV2, {}


# ── Smoke Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/root/kat_v2")
    from stable_baselines3.common.env_util import make_vec_env
    from kat_env_v2 import KATEnvV2

    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/kat/kat_v2.db"
    print("Testing KATPolicyV2...")

    env = KATEnvV2(db_path=db_path, start_date="2015-01-01", end_date="2023-12-31")

    model = PPO(
        policy=KATPolicyV2,
        env=env,
        n_steps=256,
        batch_size=64,
        verbose=0,
        device="cuda" if torch.cuda.is_available() else "cpu",
    )

    device = next(model.policy.parameters()).device
    params = sum(p.numel() for p in model.policy.parameters())
    print(f"Device:     {device}")
    print(f"Parameters: {params:,}")
    print(f"Obs size:   {env.observation_space.shape[0]}")

    # Quick learn test
    model.learn(total_timesteps=512)
    print("KATPolicyV2 PASSED ✓")
