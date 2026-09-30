"""Baseline lock — awareness stays observe-only; production invariants."""
from __future__ import annotations

import inspect

from src.python.crypto.config import CRYPTO_LIVE_EXECUTION, CRYPTO_EXECUTION_POLICY
from src.python.crypto import operational_awareness as oa


def test_baseline_flags():
    assert CRYPTO_LIVE_EXECUTION is False
    assert CRYPTO_EXECUTION_POLICY == "NEXT_BAR_OPEN"
    assert getattr(oa, "BASELINE_LOCKED", True) is True


def test_awareness_observe_only_source():
    src = inspect.getsource(oa)
    assert "apply_buy" not in src
    assert "apply_sell" not in src
    assert "set_status" not in src
