"""Binance public REST — discovery + OHLCV. No API key. No order endpoints."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import httpx

from src.python.crypto.config import assert_crypto_paper_only
from src.python.crypto.models import (
    CryptoBar,
    CryptoInstrument,
    ExclusionReason,
    InstrumentStatus,
    UniverseDiscoveryReport,
)

BINANCE_BASE = "https://data-api.binance.vision"  # public data mirror; avoids geo-451 on api.binance.com
BINANCE_BASE_FALLBACK = "https://api.binance.com"
EXCHANGE_INFO = f"{BINANCE_BASE}/api/v3/exchangeInfo"
KLINES = f"{BINANCE_BASE}/api/v3/klines"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbol(base: str, quote: str) -> str:
    return f"{str(base).upper().strip()}/{str(quote).upper().strip()}"


def _precision_from_step(step: str) -> int:
    s = str(step or "0").strip()
    if "." not in s:
        return 0
    frac = s.split(".")[-1].rstrip("0")
    return len(frac) if frac else 0


class BinancePublicProvider:
    """Authoritative public market-data for spot USDT pairs.

    HARD: never calls order placement endpoints.
    """

    name = "binance_public"

    def __init__(self, *, timeout: float = 30.0, client: Optional[httpx.Client] = None):
        assert_crypto_paper_only()
        self.timeout = timeout
        self._client = client

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        assert_crypto_paper_only()
        if self._client is not None:
            r = self._client.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            return r.json()

    def discover_instruments(self) -> UniverseDiscoveryReport:
        """Discover ALL spot instruments; primary universe = quote USDT only."""
        assert_crypto_paper_only()
        ts = _utc_now()
        eligible: list[CryptoInstrument] = []
        blocked: list[CryptoInstrument] = []
        errors: list[str] = []
        discovered = 0

        try:
            data = self._get(EXCHANGE_INFO)
        except Exception as e1:
            try:
                fb = EXCHANGE_INFO.replace("data-api.binance.vision", "api.binance.com")
                data = self._get(fb)
            except Exception as e:
                return UniverseDiscoveryReport(
                    universe_version="error",
                    discovery_timestamp=ts,
                    provider=self.name,
                    discovered_count=0,
                    eligible_count=0,
                    blocked_count=0,
                    errors=[f"PROVIDER_ERROR:{type(e).__name__}:{e}"],
                )

        symbols = data.get("symbols") or []
        for row in symbols:
            discovered += 1
            try:
                raw = str(row.get("symbol") or "")
                base = str(row.get("baseAsset") or "")
                quote = str(row.get("quoteAsset") or "")
                status = str(row.get("status") or "")
                if not base or not quote or not raw:
                    blocked.append(
                        CryptoInstrument(
                            symbol=raw or "UNKNOWN",
                            base_asset=base,
                            quote_asset=quote,
                            market_status=status,
                            provider=self.name,
                            discovered_at=ts,
                            status=InstrumentStatus.BLOCKED.value,
                            block_reason=ExclusionReason.INVALID_METADATA.value,
                            raw_symbol=raw,
                        )
                    )
                    continue
                if quote.upper() != "USDT":
                    blocked.append(
                        CryptoInstrument(
                            symbol=_normalize_symbol(base, quote),
                            base_asset=base.upper(),
                            quote_asset=quote.upper(),
                            market_status=status,
                            provider=self.name,
                            discovered_at=ts,
                            status=InstrumentStatus.BLOCKED.value,
                            block_reason=ExclusionReason.NON_USDT_QUOTE.value,
                            raw_symbol=raw,
                        )
                    )
                    continue
                if status.upper() != "TRADING":
                    blocked.append(
                        CryptoInstrument(
                            symbol=_normalize_symbol(base, quote),
                            base_asset=base.upper(),
                            quote_asset="USDT",
                            market_status=status,
                            provider=self.name,
                            discovered_at=ts,
                            status=InstrumentStatus.BLOCKED.value,
                            block_reason=ExclusionReason.MARKET_INACTIVE.value,
                            raw_symbol=raw,
                        )
                    )
                    continue

                filters = {f.get("filterType"): f for f in (row.get("filters") or []) if isinstance(f, dict)}
                lot = filters.get("LOT_SIZE") or {}
                notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
                price_f = filters.get("PRICE_FILTER") or {}
                step = str(lot.get("stepSize") or "0.00000001")
                tick = str(price_f.get("tickSize") or "0.00000001")
                min_qty = float(lot.get("minQty") or 0)
                min_notional = float(notional.get("minNotional") or notional.get("notional") or 0)

                inst = CryptoInstrument(
                    symbol=_normalize_symbol(base, quote),
                    base_asset=base.upper(),
                    quote_asset="USDT",
                    market_status=status,
                    provider=self.name,
                    discovered_at=ts,
                    price_precision=_precision_from_step(tick),
                    quantity_precision=_precision_from_step(step),
                    min_quantity=min_qty,
                    min_notional=min_notional,
                    market_data_available=True,
                    status=InstrumentStatus.ELIGIBLE.value,
                    raw_symbol=raw,
                )
                eligible.append(inst)
            except Exception as e:
                errors.append(f"row_error:{type(e).__name__}")
                blocked.append(
                    CryptoInstrument(
                        symbol=str(row.get("symbol") or "UNKNOWN"),
                        base_asset="",
                        quote_asset="",
                        market_status="",
                        provider=self.name,
                        discovered_at=ts,
                        status=InstrumentStatus.UNKNOWN.value,
                        block_reason=ExclusionReason.PROVIDER_ERROR.value,
                        raw_symbol=str(row.get("symbol") or ""),
                    )
                )

        eligible.sort(key=lambda x: x.symbol)
        version_src = f"{self.name}|{len(eligible)}|{len(blocked)}|{ts[:13]}"
        version = hashlib.sha256(version_src.encode()).hexdigest()[:16]

        return UniverseDiscoveryReport(
            universe_version=version,
            discovery_timestamp=ts,
            provider=self.name,
            discovered_count=discovered,
            eligible_count=len(eligible),
            blocked_count=len(blocked),
            eligible=eligible,
            blocked=blocked,
            errors=errors,
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 90,
        raw_symbol: Optional[str] = None,
    ) -> list[CryptoBar]:
        """Fetch klines. symbol is BASE/USDT; raw_symbol optional Binance form."""
        assert_crypto_paper_only()
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            if quote.upper() != "USDT":
                raise ValueError(f"NON_USDT_QUOTE:{symbol}")
            binance_sym = raw_symbol or f"{base.upper()}USDT"
        else:
            binance_sym = raw_symbol or symbol.upper()
        data = self._get(
            KLINES,
            params={"symbol": binance_sym, "interval": interval, "limit": int(limit)},
        )
        bars: list[CryptoBar] = []
        norm = symbol if "/" in symbol else f"{symbol.replace('USDT', '')}/USDT"
        for row in data:
            # [open_time, o, h, l, c, vol, ...]
            ts = datetime.fromtimestamp(int(row[0]) / 1000.0, tz=timezone.utc).isoformat()
            bars.append(
                CryptoBar(
                    symbol=norm,
                    timestamp=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    provider=self.name,
                    provenance="MARKET_DATA_CRYPTO",
                )
            )
        return bars
