# Colab plane (research & maintenance only)

**Not a trading runtime.** Operational signals/paper/ledger run on GitHub Actions + IDX Core.

## Notebooks

| Notebook | Function |
|----------|----------|
| `IDX_GPU_TRAINING.ipynb` | Research compute — candidate ML training (Governor-gated; no auto-promote) |
| `cold_archive_migration.ipynb` | Archive plane — GitHub Tier 1 → Drive pool (SHA-256, recovery) |

## Scripts (run from Colab)

```bash
# After: drive.mount + git clone whatman42/idx
python /content/idx/scripts/ops_real_drive_integration_test.py \
  --drive-root /content/drive/MyDrive
```

## Architecture

See [docs/COLAB_RESEARCH_PLANE.md](../docs/COLAB_RESEARCH_PLANE.md).

```
Research Compute | Data Laboratory | Strategy Evaluation | Archive & Recovery
        ↓
  EvidencePackage / operator reports
        ↓
  PromotionGate / Authority   (never auto-promote from Colab)
```

## Invariants

- `LIVE_EXECUTION = FALSE`
- `BROKER_EXECUTION = FALSE`
- Colab does **not** write the paper Ledger or production signals.
