"""
KAT v2.0 — Stage 3 PPO Training Launch Script
===============================================
Research-backed configuration:
  - transaction_cost = 0.0  (SNB confirmed 0% — eliminates dead policy)
  - ent_coef = 0.05          (prevents entropy collapse)
  - n_steps = 8192           (2x v1 — better advantage estimation + GPU utilization)
  - n_epochs = 10            (2x v1 — more gradient steps per rollout)
  - batch_size = 4096        (2x v1 — larger GPU batches)
  - target_kl = 0.02         (safety constraint — prevents catastrophic updates)
  - deterministic = False    (stochastic eval — model must actively trade)

Data splits:
  Train: 2015-01-01 — 2023-12-31
  Eval:  2024-01-01 — 2025-12-31
  Test:  2026-01-01 — (NEVER TOUCH until final deployment)

Author: KAT Research Team
Version: 2.0
"""

if __name__ == "__main__":
    import os, sys
    import time

    sys.path.insert(0, "/root/kat_v2")

    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize
    from stable_baselines3.common.callbacks import (
        EvalCallback, CheckpointCallback, CallbackList
    )
    from stable_baselines3.common.monitor import Monitor
    import logging

    from kat_env_v2 import KATEnvV2
    from kat_policy_v2 import KATPolicyV2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler()]
    )
    log = logging.getLogger("kat_v2")

    # ── Configuration ─────────────────────────────────────────────────────────
    DB_PATH   = os.environ.get("KAT_DB_PATH", "/data/kat/kat_v2.db")
    CKPT_DIR  = "/data/kat/checkpoints/stage3_v2"
    TB_DIR    = "/data/kat/tensorboard/stage3_v2"

    SPLITS = {
        "train": ("2015-01-01", "2023-12-31"),
        "eval":  ("2024-01-01", "2025-12-31"),
    }

    # ── Hyperparameters (research-backed v2.0) ─────────────────────────────────
    N          = 96            # Parallel environments (~75-80% CPU target)
    TOTAL_STEPS = 500_000_000  # 500M steps

    PPO_CONFIG = dict(
        learning_rate   = 1e-4,
        n_steps         = 8192,   # 2x v1 — better advantage estimation
        batch_size      = 4096,   # 2x v1 — larger GPU batches
        n_epochs        = 10,     # 2x v1 — more gradient steps per rollout
        gamma           = 0.995,  # High discount — rewards matter for 200+ steps ahead
        gae_lambda      = 0.95,   # GAE bias/variance tradeoff
        clip_range      = 0.15,   # Tight clipping for financial stability
        ent_coef        = 0.05,   # CRITICAL — prevents entropy collapse / dead policy
        vf_coef         = 0.5,    # Value function loss weight
        max_grad_norm   = 0.5,    # Gradient clipping
        target_kl       = 0.02,   # Safety constraint — prevents catastrophic updates
        policy_kwargs   = {},     # populated below
        verbose         = 1,
        device          = "cuda",
        tensorboard_log = TB_DIR,
    )

    # ── Environment factory ────────────────────────────────────────────────────
    def make_env(split: str, rank: int = 0):
        import time, random
        def _init():
            # Stagger startup to avoid PostgreSQL connection storm
            time.sleep(random.uniform(0, 3))
            s, e = SPLITS[split]
            env = KATEnvV2(db_path=DB_PATH, start_date=s, end_date=e)
            return Monitor(env)
        return _init

    # ── Pre-flight checks ──────────────────────────────────────────────────────
    log.info("KAT v2.0 Stage 3 — Pre-flight checks...")

    # Verify obs size match between train and eval
    log.info("Verifying train/eval obs size match...")
    train_env_check = KATEnvV2(db_path=DB_PATH, start_date=SPLITS["train"][0], end_date=SPLITS["train"][1])
    eval_env_check  = KATEnvV2(db_path=DB_PATH, start_date=SPLITS["eval"][0],  end_date=SPLITS["eval"][1])

    train_obs = train_env_check.observation_space.shape[0]
    eval_obs  = eval_env_check.observation_space.shape[0]
    assert train_obs == eval_obs, f"OBS SIZE MISMATCH: train={train_obs} eval={eval_obs}"
    log.info(f"Obs size: {train_obs} (train={train_obs}, eval={eval_obs}) MATCH ✓")

    del train_env_check, eval_env_check

    # ── Build environments ─────────────────────────────────────────────────────
    log.info(f"Building {N} training environments...")
    train_env = SubprocVecEnv([make_env("train", i) for i in range(N)])
    train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True, clip_obs=10.0)

    log.info("Building eval environment...")
    eval_env = SubprocVecEnv([make_env("eval")])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False, clip_obs=10.0)

    # ── Build model ────────────────────────────────────────────────────────────
    log.info("Building KAT Policy v2 (4-stream attention, GPU)...")

    os.makedirs(CKPT_DIR, exist_ok=True)
    os.makedirs(TB_DIR, exist_ok=True)

    model = PPO(
        policy=KATPolicyV2,
        env=train_env,
        **PPO_CONFIG,
    )

    params = sum(p.numel() for p in model.policy.parameters())
    log.info(f"Policy parameters: {params:,}")
    log.info(f"Device: {next(model.policy.parameters()).device}")

    # ── Callbacks ──────────────────────────────────────────────────────────────
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path = f"{CKPT_DIR}/best",
        log_path             = f"{CKPT_DIR}/eval_logs",
        eval_freq            = max(2_000_000 // N, 1),
        n_eval_episodes      = 10,
        deterministic        = False,   # STOCHASTIC EVAL — model must trade
        verbose              = 1,
    )
    checkpoint_callback = CheckpointCallback(
        save_freq      = max(10_000_000 // N, 1),
        save_path      = f"{CKPT_DIR}/periodic",
        name_prefix    = "kat_v2_stage3",
        verbose        = 0,
    )
    callbacks = CallbackList([eval_callback, checkpoint_callback])

    # ── Train ──────────────────────────────────────────────────────────────────
    log.info(f"Training {TOTAL_STEPS:,} steps with PPO + KATPolicy v2...")
    log.info(f"N_envs={N}, n_steps={PPO_CONFIG['n_steps']}, batch={PPO_CONFIG['batch_size']}")
    log.info(f"ent_coef={PPO_CONFIG['ent_coef']}, target_kl={PPO_CONFIG['target_kl']}")
    log.info(f"transaction_cost=0.0 (SNB 0% commission)")

    start_time = time.time()
    model.learn(
        total_timesteps = TOTAL_STEPS,
        callback        = callbacks,
        tb_log_name     = "PPO_stage3_v2",
    )

    elapsed = (time.time() - start_time) / 3600
    log.info(f"Training complete. Duration: {elapsed:.1f}h")

    # Save final model
    model.save(f"{CKPT_DIR}/final_model")
    train_env.save(f"{CKPT_DIR}/vec_normalize.pkl")
    log.info(f"Model saved to {CKPT_DIR}/final_model")
