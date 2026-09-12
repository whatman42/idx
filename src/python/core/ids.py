from __future__ import annotations
import hashlib
def order_id(*parts: str) -> str:
    return "ord_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
def tx_id(*parts: str) -> str:
    return "tx_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
