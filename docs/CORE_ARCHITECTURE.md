# IDX Core Architecture (Purified)

## Operational flow (paper only)

```
DATA → VALIDATION → FeatureSnapshot → SIGNAL → RISK → GOVERNOR
  → PaperExecution → Ledger → P&L/Metrics → (Telegram delivery)
```

## SSOT

| Concern | Authority |
|---------|-----------|
| Features | FeatureSnapshot |
| Evidence | EvidencePackage |
| Money | Ledger |
| Promotion | PromotionGate + Authority |
| Active strategy | Champion |
| Reporting | Telegram / Gemini (interpretation only) |

## Forbidden

- LIVE_EXECUTION / BROKER_EXECUTION / PRODUCTION_MUTATION
- Domain importing notify / llm / colab
- Archive controlling trades
- MetaLearner self-promotion
- LLM numeric truth

## Research vs production

Research produces candidates/evidence only. Champion changes only via PromotionGate → Authority.
