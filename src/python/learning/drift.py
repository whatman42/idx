"""Drift Detection — feature / regime / performance degradation alerts."""
from __future__ import annotations

from typing import Sequence

from src.python.learning.contracts import DriftAlert, DriftKind, SignalEpisode


def _psi(expected: Sequence[float], actual: Sequence[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi <= lo:
        return 0.0
    width = (hi - lo) / bins

    def hist(xs):
        h = [0] * bins
        for x in xs:
            i = min(bins - 1, max(0, int((x - lo) / width)))
            h[i] += 1
        n = max(1, len(xs))
        return [(c + 1e-6) / n for c in h]

    e = hist(list(expected))
    a = hist(list(actual))
    psi = 0.0
    import math
    for pe, pa in zip(e, a):
        psi += (pa - pe) * math.log(pa / pe)
    return float(psi)


def performance_drift(
    historical_rs: Sequence[float],
    recent_rs: Sequence[float],
    *,
    expected_win_rate: float = 0.55,
    psi_warn: float = 0.2,
    psi_degraded: float = 0.3,
) -> DriftAlert:
    if not recent_rs:
        return DriftAlert(
            kind=DriftKind.PERFORMANCE.value,
            name="performance",
            score=0.0,
            threshold=psi_warn,
            status="OK",
            detail={"reason": "insufficient_recent"},
        )
    recent_wr = sum(1 for r in recent_rs if r > 0) / len(recent_rs)
    psi = _psi(list(historical_rs) or list(recent_rs), list(recent_rs))
    status = "OK"
    if psi >= psi_degraded or recent_wr < expected_win_rate - 0.15:
        status = "DEGRADED"
    elif psi >= psi_warn or recent_wr < expected_win_rate - 0.08:
        status = "WARN"
    return DriftAlert(
        kind=DriftKind.PERFORMANCE.value,
        name="performance",
        score=psi,
        threshold=psi_warn,
        status=status,
        detail={
            "recent_win_rate": recent_wr,
            "expected_win_rate": expected_win_rate,
            "n_recent": len(recent_rs),
            "n_hist": len(historical_rs),
        },
    )


def regime_distribution_drift(
    historical_regimes: Sequence[str],
    recent_regimes: Sequence[str],
    *,
    shift_warn: float = 0.25,
) -> DriftAlert:
    from collections import Counter

    def dist(xs):
        c = Counter(xs)
        n = max(1, len(xs))
        return {k: v / n for k, v in c.items()}

    h = dist(historical_regimes)
    r = dist(recent_regimes)
    keys = set(h) | set(r)
    shift = 0.5 * sum(abs(h.get(k, 0) - r.get(k, 0)) for k in keys)
    status = "DEGRADED" if shift >= shift_warn * 1.5 else ("WARN" if shift >= shift_warn else "OK")
    return DriftAlert(
        kind=DriftKind.REGIME.value,
        name="regime_distribution",
        score=float(shift),
        threshold=shift_warn,
        status=status,
        detail={"historical": h, "recent": r},
    )


def drift_from_episodes(
    historical: list[SignalEpisode],
    recent: list[SignalEpisode],
) -> list[DriftAlert]:
    h_r = [float(e.r_multiple or 0) for e in historical if e.outcome not in ("OPEN", "SKIPPED")]
    r_r = [float(e.r_multiple or 0) for e in recent if e.outcome not in ("OPEN", "SKIPPED")]
    h_reg = [e.regime for e in historical]
    r_reg = [e.regime for e in recent]
    return [
        performance_drift(h_r, r_r),
        regime_distribution_drift(h_reg, r_reg),
    ]
