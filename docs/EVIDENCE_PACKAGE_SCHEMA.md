# EvidencePackage — immutable evidence record

**Not** a promotional narrative. **Not** an auto-promote trigger.

```
Facts / Metrics / Artifacts
        ↓
EvidencePackage
        ↓
PromotionGate
        ↓
Authority Decision
```

Forbidden:

```
Colab → "model looks good" → Auto Promote
```

## Minimal provenance fields

| Field | Role |
|-------|------|
| experiment_id / experiment_version | Identity |
| git_commit | Code pin |
| dataset_id / dataset_version / dataset_checksum | Data pin |
| feature_snapshot_version | Feature SSOT pin |
| code_environment / dependency_lock_hash | Env pin |
| random_seed | Reproducibility |
| experiment_timestamp / timezone | When |
| train_period / validation_period / oos_period | Temporal splits |
| strategy_version / model_version | Candidate identity |
| metrics | Factual numbers only |
| transaction_cost_model / slippage_model | Cost assumptions |
| sample_count | N |
| artifact_manifest / artifact_checksums | Artifact integrity |
| reproducibility_status | PASS\|FAIL\|UNKNOWN |
| data_quality_status | PASS\|FAIL\|UNKNOWN |
| leakage_check_status | PASS\|FAIL\|UNKNOWN |

Implementation: `src/python/strategy/evidence.py` (optional fields) + `evidence_schema.py` (validation helpers).

## Experiment Registry (Drive, research only)

```
IDX/experiment_registry/<experiment_id>/
  evidence_package.json
  artifacts/
  checksums.json
```

Registry is **not** Champion authority and **not** Ledger SSOT.
