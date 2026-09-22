# Rebalance Research Plane (v1)

**Plane:** RESEARCH / SHADOW only — no paper execution wiring.

```
calculate_target_weights (equal weight)
        ↓
detect_drift (relative drift)
        ↓
build_rebalance_plan
        ┌── NO_ACTION
        ┌── TRIM_CANDIDATE   (overweight only)
        └── TOP_UP_FORBIDDEN (underweight — needs signal+risk)
```

## Formula

- `target_weight_i = 1 / N_open`
- `relative_drift = |actual - target| / target`
- Trigger trim if `relative_drift > 20%` **and** overweight

## Invariants

- `LIVE_EXECUTION = FALSE`
- Rebalance plan ≠ broker order
- Future trim must pass Risk → Governor → Market Structure Gate → Paper path
- No calendar rebalance, no auto top-up, no risk-parity in v1

## Module

`src/python/research/rebalance.py`
