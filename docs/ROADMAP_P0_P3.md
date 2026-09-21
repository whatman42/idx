# IDX Roadmap P0–P3 (locked)

Core and Colab Research/Maintenance Plane are locked. **No new authority. No Core changes** for roadmap delivery unless a certified defect requires it.

```
OPERATIONAL (GitHub Actions)          COLAB (Research / Maintenance)
Data→Signal→Risk→Governor→Paper       Research / Dataset / WFA / ML
         → Ledger → Telegram          Evidence / Archive / Recovery
                    │                              │
                    │         NO AUTHORITY         │
                    └──────────────┬───────────────┘
                                   ▼
                            EvidencePackage
                                   ▼
                             PromotionGate
                                   ▼
                         Authority / Champion
```

## Parallel tracks

**Soak Core** and **Real Drive validation** run **in parallel** (different planes). Drive does not block scheduled paper-cycle evidence collection.

---

### P0 — Proof of Plane

1. Real Google Drive integration (operator Colab)
2. GitHub Tier 1 → Colab → Drive Pool
3. SHA-256 + size + manifest verification
4. Restore drill (archive → fresh Colab)
5. RTO/RPO measurement
6. EvidencePackage schema standard (immutable facts)
7. Experiment Registry on Drive
8. Reproducibility test

### P1 — Production Boundary & Soak

1. Soak operational Core on baseline `5bb33b0`
2. Signal → Risk → Governor → Paper → Ledger → Telegram
3. Replay / idempotency
4. Ledger invariants
5. LIVE_EXECUTION = FALSE
6. BROKER_EXECUTION = FALSE
7. PRODUCTION_MUTATION = FALSE
8. Static/import/network boundary audit (Colab vs ops)

### P2 — Research Rigor

1. Dataset schema / data-quality validation
2. Missing / outlier / leakage detection
3. Time-series / PIT enforcement
4. Research dataset vs FeatureSnapshot drift
5. WFA / OOS
6. Monte Carlo
7. Fee / slippage models
8. Multiple-testing correction
9. PBO
10. Deflated Sharpe
11. EvidencePackage = factual evidence only

### P3 — Operations & Governance

1. Structured logging / metrics
2. Telegram operational alerting
3. Runbooks
4. Secret / credential governance
5. Least privilege
6. Retention policy
7. ADR
8. Evidence catalog
9. Decision log
10. Recovery / rollback documentation

---

## System status (current)

| Area | Status |
|------|--------|
| Core | FROZEN / CERTIFIED (`5bb33b0`) |
| Colab Plane | IMPLEMENTED |
| Archive Plane | CERTIFIED |
| Real Drive | VALIDATION PENDING (operator) |
| Dataset Research | ARCHITECTURE IMPLEMENTED / OPS PROOF PENDING |
| Evidence Reproducibility | NEXT P0 |
| Operational Soak | IN PROGRESS |
| Trading Edge | NOT YET PROVEN |

Next phase is **not** “build more bot features” — it is proving reproducible, auditable, recoverable evidence without piercing the operational Core boundary.
