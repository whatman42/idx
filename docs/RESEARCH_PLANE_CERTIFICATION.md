# Research Plane — Institutional Certification Notes

## Boundary

| Flag | Value |
|------|-------|
| PRODUCTION MUTATION | FALSE |
| AUTO PROMOTE | FALSE |
| LIVE EXECUTION | FALSE |
| BROKER EXECUTION | FALSE |
| RESEARCH → CHAMPION WRITE | FALSE |
| LLM → NUMERIC TRUTH | FALSE |

## Pipeline

```
Paper Ledger → Episode → Attribution/Failure → Factory → Hypothesis
  → Experiment → Colab WFA → ExperimentResult (immutable)
  → integrity / anti-overfit / reproducibility
  → EvidencePackage → PromotionGate candidacy
  → Authority → governed promotion → Champion
```

Research may produce **candidates**. Research may **not** promote Champions.

## Fingerprint

Material only: commit, dataset, feature, strategy, params, seed, cost model, declared windows.
**Not** in fingerprint: wall-clock time, paths, UUID.

## Selection policy

- Parameters fixed on job (`selection_rule=fixed_params_from_job_no_oos_tuning`)
- `selection_split=NONE` — no data-driven selection from TEST/OOS
- Evaluation metrics reported on TEST/OOS only

## Status → candidacy

| Status | Candidacy |
|--------|-----------|
| ROBUST | may proceed to gate (still approved=False until Authority) |
| FRAGILE / INSUFFICIENT_EVIDENCE / INVALID / FAILED | blocked |

## Colab vs Actions

- Actions: cheap control plane (job emit, integrity, ingest evidence)
- Colab: WFA / heavy research compute
