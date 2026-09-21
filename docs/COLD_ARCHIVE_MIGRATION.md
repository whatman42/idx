# Cold Archive Migration — GitHub → Colab → Google Drive

**Phase A (current):** dual retention — GitHub cold archive **kept**; Drive is additional verified copy.

**Phase B (later):** after coverage 100% verified, deprecate GitHub as primary cold store.

## Boundaries

| Plane | Role |
|-------|------|
| GitHub Actions + IDX Core | Paper trading runtime |
| Ledger | Financial truth |
| Google Drive | Cold archive **only** |
| Colab | Migration bridge / maintenance worker |

Core **must not** import Google APIs. Failure of Drive/Colab **must not** stop paper trading.

## Integrity

SOURCE → SHA-256 → upload → re-read → SHA-256 must match. Mismatch → KEEP source, no FIFO.

## FIFO

Only after verified migration. Protect MIN_RECOVERY_ARCHIVES.

## Layout

IDX/cold_archive/YYYY/MM/YYYY-MM-DD/{archives,manifests,metadata}/
IDX/cold_archive/archive_index.json

## Colab

colab/cold_archive_migration.ipynb — mount Drive, stage tar.gz, run MigrationEngine.
