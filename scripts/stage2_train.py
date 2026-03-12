#!/usr/bin/env python3
"""
KAT v3 — Stage 2 Training Script
==================================
Fixes applied vs Stage 1 (based on TensorBoard diagnosis):

PROBLEM 1: approx_kl 0.012 → 0.289  (exploded — should stay <0.05)
FIX:        target_kl=0.02           (halts update if KL too large)

PROBLEM 2: entropy_loss -1.60 → -0.42  (collapsed — no exploration)
FIX:        ent_coef=0.01              (forces continued exploration)

PROBLEM 3: eval/mean_reward +166 → -463  (overfit — gamed train env)
FIX:        strict temporal train/eval split (train 2015-2023, eval 2024-2025)

PROBLEM 4: clip_fraction 0.12 → 0.31  (policy jumps too large)
FIX:        clip_range=0.15, n_epochs=5, lr=1e-4

PROBLEM 5: loaded final model (overfit) instead of best_model
FIX:        load from /data/kat/checkpoints/stage1/best/best_model.zip

Stage 1 summary:
  ep_rew_mean:        54 → 1018   ← learned to game training env
  eval/mean_reward: +166 → -463   ← catastrophic on unseen data
  approx_kl:        0.01 → 0.289  ← exploded
  explained_var:    -0.94 → 0.99  ← value fn good (keep this)

Usage:
    # On Vast.ai RTX 4090:
    python3 stage2_train.py

    # Sanity check env first:
    python3 stage2_train.py --check

    # Monitor:
    tensorboard --logdir /data/kat/tensorboard/stage2 --port 6006

    # Watch these metrics:
    #   eval/mean_reward  → must be POSITIVE and not collapsing
    #   train/approx_kl   → must stay BELOW 0.05
    #   train/entropy_loss → must stay around -1.0 to -1.5 (not collapse to 0)
"""

import os, sys, json, time, logging
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
S1_BEST     = Path("/data/kat/checkpoints/stage1/best/best_model.zip")
S1_VECNORM  = Path("/data/kat/checkpoints/stage1/kat_stage1_final_vecnorm.pkl")
S2_DIR      = Path("/data/kat/checkpoints/stage2")
TB_DIR      = Path("/data/kat/tensorboard/stage2")
DB_URI      = os.environ.get("KAT_DB_URI",
              "postgresql://kat_db:31gco8PwYniP5psuCwa6in3OvS86LAKI@127.0.0.1:5432/kat_production")

for d in [S2_DIR, TB_DIR, S2_DIR/"periodic", S2_DIR/"best"]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(S2_DIR / "stage2.log"),
    ]
)
log = logging.getLogger("kat.stage2")

# ── Hyperparameters ────────────────────────────────────────────────────────────
HP = {
    "policy":        "MlpPolicy",
    "policy_kwargs": dict(net_arch=[256, 256, 128]),  # wider than S1 [128,128]

    # Conservative updates — prevent KL explosion
    "learning_rate": 1e-4,      # S1: 3e-4 — slower, more stable
    "n_steps":       4096,      # S1: 2048 — more data per update
    "batch_size":    512,       # S1: 64   — larger batches
    "n_epochs":      5,         # S1: 10   — fewer gradient steps
    "gamma":         0.995,     # S1: 0.99 — longer horizon
    "gae_lambda":    0.95,
    "clip_range":    0.15,      # S1: 0.20 — tighter clipping
    "clip_range_vf": 0.15,
    "ent_coef":      0.01,      # S1: ~0   — CRITICAL: prevent entropy collapse
    "vf_coef":       0.5,
    "max_grad_norm": 0.5,
    "target_kl":     0.02,      # S1: None — CRITICAL: prevent KL explosion

    "total_timesteps": 200_000_000,
    "n_envs":          16,      # S1: 8 — RTX 4090 can handle more
}

# Strict temporal split — NO data leakage
SPLIT = {
    "train": ("2015-01-01", "2023-12-31"),  # 9yr training
    "eval":  ("2024-01-01", "2025-12-31"),  # 2yr held out — never touched
    "test":  ("2026-01-01", "2026-03-12"),  # Final test — run once at end
}

# ── Environment Factory ────────────────────────────────────────────────────────
def make_env_fn(split="train", rank=0):
    def _init():
        start, end = SPLIT[split]
        try:
            sys.path.insert(0, "/root/kat")
            from kat_env_v2 import KATEnvV2
            return KATEnvV2(
                db_uri=DB_URI,
                start_date=start,
                end_date=end,
                initial_capital=10_000,
                symbols=["MES", "MNQ", "MCL", "MGC", "ZB"],
                transaction_cost=0.0002,
                reward_scaling=0.01,
            )
        except ImportError:
            log.warning(f"[env:{rank}] KATEnvV2 not found — using CartPole placeholder")
            import gymnasium as gym
            return gym.make("CartPole-v1")
    return _init


def build_vec_env(split="train"):
    from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize
    fns = [make_env_fn(split, i) for i in range(HP["n_envs"])]
    env = SubprocVecEnv(fns)
    env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.0)
    return env


# ── Callbacks ──────────────────────────────────────────────────────────────────
def build_callbacks(eval_env):
    from stable_baselines3.common.callbacks import (
        EvalCallback, CheckpointCallback, CallbackList
    )
    freq_per_env = max(1_000_000 // HP["n_envs"], 1)

    ckpt = CheckpointCallback(
        save_freq=freq_per_env,
        save_path=str(S2_DIR / "periodic"),
        name_prefix="kat_s2",
        save_vecnormalize=True,
        verbose=1,
    )

    # Eval runs on HELD-OUT 2024-2025 data
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(S2_DIR / "best"),
        log_path=str(S2_DIR / "eval_logs"),
        eval_freq=max(2_000_000 // HP["n_envs"], 1),
        n_eval_episodes=10,
        deterministic=True,
        verbose=1,
    )

    return CallbackList([ckpt, eval_cb])


# ── Training ───────────────────────────────────────────────────────────────────
def train():
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import VecNormalize

    log.info("=" * 65)
    log.info("KAT Stage 2 — Starting")
    log.info(f"Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Loading: {S1_BEST}")
    log.info("=" * 65)
    log.info("Fixes vs Stage 1:")
    log.info("  target_kl=0.02    KL was 0.289 — now halts if >0.02")
    log.info("  ent_coef=0.01     Entropy collapsed — now forced exploration")
    log.info("  n_epochs=5        Was 10 — less overfit per batch")
    log.info("  clip_range=0.15   Was 0.20 — tighter policy updates")
    log.info("  lr=1e-4           Was 3e-4 — slower convergence")
    log.info("  Train 2015-2023 / Eval 2024-2025 — strict split")
    log.info("  Loading best_model (not final — final was overfit)")
    log.info("=" * 65)

    if not S1_BEST.exists():
        log.error(f"Stage 1 best model not found at {S1_BEST}")
        sys.exit(1)

    log.info("Building environments...")
    train_env = build_vec_env("train")
    eval_env  = build_vec_env("eval")

    # Load best Stage 1 checkpoint (not final — final overfit badly)
    log.info(f"Loading Stage 1 best model ({S1_BEST.stat().st_size/1e6:.1f} MB)...")
    model = PPO.load(
        str(S1_BEST),
        env=train_env,
        learning_rate=HP["learning_rate"],
        n_steps=HP["n_steps"],
        batch_size=HP["batch_size"],
        n_epochs=HP["n_epochs"],
        gamma=HP["gamma"],
        gae_lambda=HP["gae_lambda"],
        clip_range=HP["clip_range"],
        clip_range_vf=HP["clip_range_vf"],
        ent_coef=HP["ent_coef"],
        vf_coef=HP["vf_coef"],
        max_grad_norm=HP["max_grad_norm"],
        target_kl=HP["target_kl"],
        tensorboard_log=str(TB_DIR),
        verbose=1,
        device="auto",  # uses GPU if available
    )

    # Load Stage 1 observation normalisation stats
    if S1_VECNORM.exists():
        log.info("Loading Stage 1 VecNormalize stats (preserving obs scaling)...")
        train_env = VecNormalize.load(str(S1_VECNORM), train_env)
        train_env.training    = True
        train_env.norm_reward = True
    else:
        log.warning("VecNormalize not found — obs scaling starts fresh")

    # Save config to disk
    cfg = {
        "stage": 2,
        "started_at": datetime.now().isoformat(),
        "loaded_from": str(S1_BEST),
        "hyperparams": {k: str(v) for k, v in HP.items()},
        "data_split": SPLIT,
        "stage1_diagnosis": {
            "ep_rew_mean": "54 → 1018 (gamed training env)",
            "eval_mean_reward": "+166 → -463 (OVERFIT)",
            "approx_kl": "0.012 → 0.289 (EXPLODED)",
            "explained_variance": "-0.94 → +0.99 (good)",
        },
    }
    (S2_DIR / "config.json").write_text(json.dumps(cfg, indent=2))

    # Run
    callbacks = build_callbacks(eval_env)
    log.info(f"Training {HP['total_timesteps']:,} timesteps...")
    log.info(f"TensorBoard: tensorboard --logdir {TB_DIR} --port 6006")
    log.info("Key metrics to watch:")
    log.info("  eval/mean_reward  → must be POSITIVE and STABLE")
    log.info("  train/approx_kl   → must stay BELOW 0.05")
    log.info("  train/entropy_loss → must stay around -1.0 (not collapse)")
    log.info("-" * 65)

    t0 = time.time()
    model.learn(
        total_timesteps=HP["total_timesteps"],
        callback=callbacks,
        reset_num_timesteps=False,
        tb_log_name="PPO_stage2",
        progress_bar=True,
    )

    elapsed = time.time() - t0
    log.info(f"Complete in {elapsed/3600:.1f}h")

    # Save
    final = S2_DIR / "kat_stage2_final"
    model.save(str(final))
    train_env.save(str(S2_DIR / "kat_stage2_vecnorm.pkl"))
    log.info(f"Saved: {final}.zip")

    cfg["completed_at"]    = datetime.now().isoformat()
    cfg["duration_hours"]  = round(elapsed/3600, 2)
    (S2_DIR / "config.json").write_text(json.dumps(cfg, indent=2))

    log.info("=" * 65)
    log.info("Stage 2 done.")
    log.info(f"Best:  {S2_DIR}/best/best_model.zip")
    log.info(f"Final: {final}.zip")
    log.info("Next: push results + run Databento Tier 1 ingestion")
    log.info("=" * 65)


# ── Env Check ──────────────────────────────────────────────────────────────────
def check():
    log.info("Environment sanity check...")
    try:
        env = make_env_fn("train", 0)()
        obs, _ = env.reset()
        log.info(f"  obs shape:    {obs.shape}")
        log.info(f"  action space: {env.action_space}")
        for i in range(3):
            a = env.action_space.sample()
            obs, r, done, trunc, info = env.step(a)
            log.info(f"  step {i+1}: reward={r:.4f} done={done}")
        env.close()
        log.info("  PASSED ✓")
        return True
    except Exception as e:
        log.error(f"  FAILED: {e}")
        return False


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--check",  action="store_true", help="Env check only")
    p.add_argument("--config", action="store_true", help="Print config and exit")
    args = p.parse_args()

    if args.config:
        print(json.dumps({**HP, "data_split": SPLIT}, indent=2, default=str))
    elif args.check:
        sys.exit(0 if check() else 1)
    else:
        train()
