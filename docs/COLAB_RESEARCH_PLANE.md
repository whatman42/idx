# Google Colab — Research + Data + Archive + Recovery Plane

Colab is **not** the trading runtime.

```
IDX CORE (GitHub Actions)          GOOGLE COLAB
Operational Plane                  Research / Maintenance Plane
─────────────────────────────────  ─────────────────────────────
Signal generation                  Research compute (WFA, backtest, MC)
Risk / Governor                    Data laboratory
Paper execution + Ledger           ML training (CPU/GPU)
Telegram delivery                  Strategy evaluation → EvidencePackage
Deterministic schedule             Archive migration + recovery drill
```

## Invariants

| Flag | Value |
|------|--------|
| LIVE_EXECUTION | FALSE |
| BROKER_EXECUTION | FALSE |
| PRODUCTION_MUTATION | FALSE |
| Colab promotes Champion | **NO** — only produces EvidencePackage candidates |
| Colab writes Ledger | **NO** |
| Colab generates production signals | **NO** |

Promotion path remains:

```
EvidencePackage → PromotionGate → Authority / Champion
```

Colab must not short-circuit this path.

---

## Four Colab functions

### 1. Research Compute

```
Historical Data → Feature Engineering → WFA / Backtest → ML Training → Evaluation → EvidencePackage
```

- CPU/RAM: walk-forward, Monte Carlo, multi-symbol backtests
- GPU: heavy ML training (optional; CPU fallback supported)
- TPU: low priority for IDX

Notebook: `colab/IDX_GPU_TRAINING.ipynb` (candidate training only).

### 2. Data Laboratory

Research data preparation (not operational FeatureSnapshot SSOT):

- Missing / duplicate OHLCV detection
- Survivorship / look-ahead / leakage probes
- Feature statistics, provider comparison
- Dataset versioning, Parquet packaging

Operational SSOT for features remains **FeatureSnapshot** in IDX core. Colab datasets are research inputs only.

### 3. Model / Strategy Evaluation

```
Strategy candidates → WFA → OOS → ML eval → Monte Carlo → Robustness → EvidencePackage → PromotionGate
```

Colab may **recommend**; it may not **promote**.

### 4. Archive & Disaster Recovery

```
GitHub Tier 1 → Colab (checksum, manifest, restore) → Drive Pool
```

- Tiered promotion (not GitHub decommission)
- SHA-256 dual verify
- Recovery drills
- Multi-account routing (`drive_01…N`)

| Tool | Path |
|------|------|
| Migration notebook | `colab/cold_archive_migration.ipynb` |
| Real Drive harness | `scripts/ops_real_drive_integration_test.py` |

---

## Resource map

| Colab facility | IDX use |
|----------------|---------|
| CPU/RAM | WFA, backtest, Monte Carlo, features |
| GPU | Heavy ML training |
| Google Drive | Datasets, models, cold archive, evidence |
| GitHub | Pull source, research pipeline, artifacts |
| Network | Public datasets / allowed APIs |
| Secrets (runtime only) | Ephemeral credentials — never commit |
| Temp disk | Staging archives, extract, preprocess |
| Visualization | Equity/drawdown/signal diagnostics |
| Compression + SHA-256 | Archive integrity |

---

## Explicitly forbidden on Colab

```
Colab → signal generation → paper execution → ledger
Colab → broker
Colab → auto-promote Champion
```

Operational signals and paper fills stay on **GitHub Actions + IDX Core**.

---

## Evidence classes

| Evidence | Source |
|----------|--------|
| Software lifecycle / unit tests | GitHub Actions CI |
| Real Drive auth / write / read | Operator Colab run only |
| Research EvidencePackage | Colab research notebooks |
| Production paper cycle | `idx_signal.yml` runtime |

Do not conflate CI PASS with real Drive verification, or research scores with production authority.
