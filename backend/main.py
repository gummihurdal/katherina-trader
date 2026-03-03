"""KAT — Main Entry Point"""
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("kat")

def main():
    logger.info("=" * 50)
    logger.info("  KAT — Katherina's Autonomous Trader v2.0")
    logger.info("  Signal Aggregator Edition")
    logger.info("=" * 50)
    mode = os.getenv("KAT_MODE", "paper")
    logger.info(f"  Mode: {mode.upper()}")
    logger.info(f"  IBKR Port: {'7497 (LIVE)' if mode == 'live' else '7496 (PAPER)'}")
    logger.info("=" * 50)
    logger.info("KAT ready. Waiting for signals...")

if __name__ == "__main__":
    main()
