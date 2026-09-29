"""CRYPTO PAPER PLANE — fully isolated from IDX equities.

Domain: crypto spot USDT pairs only.
LIVE_EXECUTION = FALSE (hard). No exchange order submission.
Base accounting currency: USDT.
Universe: dynamic discovery of all */USDT instruments from provider.
Research plane: Turso memory (optional) + Colab compute + independent PromotionGate.
"""
from src.python.crypto.config import (
    CRYPTO_BASE_CURRENCY,
    CRYPTO_LIVE_EXECUTION,
    assert_crypto_paper_only,
)
from src.python.crypto.models import (
    CryptoInstrument,
    ExclusionReason,
    UniverseDiscoveryReport,
)
from src.python.crypto.universe import CryptoUniverseProvider
from src.python.crypto.provider import BinancePublicProvider
from src.python.crypto.paper_ledger import CryptoPaperLedger
from src.python.crypto.research_memory import (
    CryptoResearchMemory,
    get_crypto_research_memory,
    crypto_memory_cannot_mutate_ledger,
)
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.colab_bridge import run_crypto_colab_research_stub

__all__ = [
    "CRYPTO_BASE_CURRENCY",
    "CRYPTO_LIVE_EXECUTION",
    "assert_crypto_paper_only",
    "CryptoInstrument",
    "ExclusionReason",
    "UniverseDiscoveryReport",
    "CryptoUniverseProvider",
    "BinancePublicProvider",
    "CryptoPaperLedger",
    "CryptoResearchMemory",
    "get_crypto_research_memory",
    "crypto_memory_cannot_mutate_ledger",
    "CryptoPromotionGate",
    "run_crypto_colab_research_stub",
]
