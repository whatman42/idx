"""CRYPTO PAPER PLANE — fully isolated from IDX equities.

Domain: crypto spot USDT pairs only.
LIVE_EXECUTION = FALSE (hard). No exchange order submission.
Base accounting currency: USDT.
Universe: dynamic discovery of all */USDT instruments from provider.
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
]
