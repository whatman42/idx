# Research Memory (Turso / libSQL)

**Turso is persistent research memory, not financial truth and not production authority.**

## Role

| Component | Role |
|-----------|------|
| Paper Ledger | Financial truth |
| ExperimentResult | Research result truth |
| EvidencePackage | Promotion evidence truth |
| **Turso** | Historical research / learning memory |
| PromotionGate | Candidate governance |
| Authority | Production mutation authority |
| Champion | Production strategy state |

## Boundaries

- TURSO → Champion = FALSE
- TURSO → Ledger = FALSE
- TURSO → Promotion approval = FALSE
- TURSO → Broker = FALSE

If Turso is unavailable: paper trading continues. Research may be `MEMORY_DEGRADED` / `MEMORY_UNAVAILABLE`.

## Config

```
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=
```

Never logged. Never in fingerprints or EvidencePackage.

## Schema domains

experiments, hypotheses, knowledge, failures, drift_events, audit_events, experiment_events

## Deduplication

Experiment identity for dedup = **fingerprint** (UNIQUE). Primary key = experiment_id.

## Failure

No silent pretend-available. Explicit status codes only.
