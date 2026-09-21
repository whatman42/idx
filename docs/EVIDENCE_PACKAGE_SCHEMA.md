# EvidencePackage — immutable evidence record

**evidence_origin is mandatory and must never be inferred.**

Valid values only: `CORE` | `COLAB`.

```
TRACK A COLAB ──evidence origin=COLAB──► PromotionGate
TRACK B CORE  ──evidence origin=CORE ──► PromotionGate
```

No control loop Colab ↔ Core. Colab must not touch Signal, Governor, Ledger, Paper, or auto-promote.

## Schema groups

| Group | Fields |
|-------|--------|
| identity | experiment_id, experiment_version, parent_experiment_id, **evidence_origin**, timestamp |
| source | git_commit, dataset_*, feature_snapshot_version, strategy/model version |
| environment | environment_hash, dependency_lock_hash, colab_runtime_type |
| methodology | random_seed, train/val/oos periods, cost/slippage models |
| results | sample_count, metrics, data_quality/leakage/reproducibility status |
| artifacts | artifact_manifest, artifact_checksums |
| governance | boundary_attestation, promotion_status=PENDING (Colab), authority_decision (Authority only) |

## Governance freeze

- Colab may leave `promotion_status=PENDING` and `authority_decision=""`.
- Final promotion/authority decisions come **only** from PromotionGate / Authority.
- Validator rejects missing/invalid origin and Colab-written APPROVED/PROMOTED/CHAMPION.

## Joint review (before P2)

1. Reproducible
2. Auditable
3. Recoverable
4. Isolated

```
CORE FROZEN → TRACK A P0 + TRACK B P1 PARALLEL → JOINT REVIEW → P2 → P3
```
