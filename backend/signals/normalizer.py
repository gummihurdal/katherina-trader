"""KAT — Signal Normalizer. Routes raw payloads to correct parser."""
import logging
from typing import Optional
from .models import UnifiedSignal, SignalSource
from .parsers.collective2 import C2Parser
from .parsers.traderspost import TradersPostParser
from .parsers.trade_ideas import TradeIdeasParser
from .parsers.signalstack import SignalStackParser
from .parsers.telegram import TelegramParser

logger = logging.getLogger(__name__)

class SignalNormalizer:
    def __init__(self):
        self._parsers = {
            SignalSource.COLLECTIVE2: C2Parser(),
            SignalSource.TRADERSPOST: TradersPostParser(),
            SignalSource.TRADE_IDEAS: TradeIdeasParser(),
            SignalSource.SIGNALSTACK: SignalStackParser(),
            SignalSource.TELEGRAM: TelegramParser(),
        }

    def normalize(self, source: SignalSource, raw: dict) -> Optional[UnifiedSignal]:
        parser = self._parsers.get(source)
        if not parser:
            logger.warning(f"No parser for source: {source.value}")
            return None
        try:
            signal = parser.parse(raw)
            signal.raw_payload = raw
            logger.info(f"Normalized: {signal}")
            return signal
        except Exception as e:
            logger.error(f"Parse failed ({source.value}): {e}", exc_info=True)
            return None

    def register_parser(self, source: SignalSource, parser):
        self._parsers[source] = parser
