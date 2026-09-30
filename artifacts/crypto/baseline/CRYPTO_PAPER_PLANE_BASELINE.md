# Crypto Paper Plane — Locked Baseline

**Status:** FROZEN (operational control plane)  
**Plane:** CRYPTO (parallel to IDX; not a clone)  
**Mode:** PAPER ONLY

## Production control flow

```
OHLCV / Universe
      ↓
Data Quality Gate
      ↓
CryptoFeatureSnapshot
      ↓
SMA20 Signal (crypto_rule_sma20)
      ↓
Signal Contract
      ↓
Risk
      ↓
Governor
      ↓
Execution Gate
      ↓
NEXT_BAR_OPEN Resolver (single SSOT)
      ↓
USDT Paper Ledger (accounting SSOT)
      ↓
┌─────────────────┬─────────────────┐
Operational       Accounting SSOT
Awareness         (ledger)
READ-ONLY
      ↓
Artifact + [CRYPTO PAPER] Telegram
```

## Research flow (separate — no paper ledger path)

```
FeatureSnapshot → Scorer → Evaluator/WFA → EvidencePackage
  → PromotionGate → Manual Review
```

## Locked invariants

| Flag | Value |
|------|--------|
| LIVE_EXECUTION | false |
| BROKER_EXECUTION | false |
| PAPER_ONLY | true |
| AUTO_PROMOTION | false |
| IDX_CORE_FROZEN | true |
| CRYPTO_LEDGER_SEPARATE | true |
| CRYPTO_EXECUTION_POLICY | NEXT_BAR_OPEN |
| EXECUTION_RESOLVER_SINGLE_SSOT | true |
| SHADOW_AUTO_PAPER | false |
| Production strategy | crypto_rule_sma20 |
| Momentum shadow | REJECTED → KEEP_SHADOW_RESEARCH |

## Operational Awareness contract

Pattern only:

```
observe → classify → explain → record
```

Forbidden:

```
observe → modify → trade
```

Awareness MUST NOT change strategy, risk, promotion, execution policy, or ledger;
must not enable live paths or auto-promote from confidence/health.

## Authority map

| Layer | Authority |
|-------|-----------|
| DQ / Risk / Governor / Execution Gate | Enforcement |
| NEXT_BAR_OPEN resolver | Execution price SSOT |
| USDT Paper Ledger | Accounting SSOT |
| Operational Awareness | Diagnosis only (read-only) |
| Evaluator / WFA / Evidence | Research only |
| PromotionGate | Lifecycle (no auto paper for shadow) |
| Telegram | Reporting only |

## Do not add without explicit new phase

- AI brain / subjective confidence on ops path
- Self-learning on production paper path
- Autonomous optimization of SMA20 / risk / costs
- Live exchange order paths
- Merge of IDX and Crypto engines
