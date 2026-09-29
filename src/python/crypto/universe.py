"""Crypto universe — dynamic full USDT discovery wrapper."""
from __future__ import annotations

from typing import Optional

from src.python.crypto.config import assert_crypto_paper_only
from src.python.crypto.models import UniverseDiscoveryReport
from src.python.crypto.provider import BinancePublicProvider


class CryptoUniverseProvider:
    def __init__(self, market_provider: Optional[BinancePublicProvider] = None):
        assert_crypto_paper_only()
        self.market = market_provider or BinancePublicProvider()

    def discover(self) -> UniverseDiscoveryReport:
        assert_crypto_paper_only()
        report = self.market.discover_instruments()
        return report
