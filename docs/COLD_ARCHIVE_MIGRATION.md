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

```
SOURCE → SHA-256 → upload → re-read → SHA-256
source_sha256 == target_sha256
source_size == target_size
```

Mismatch → `MIGRATION_FAILED` → **KEEP source** → no delete → no FIFO.

## FIFO

Only after verified migration. Protect `MIN_RECOVERY_ARCHIVES`. Deterministic order by `created_at`, `cycle_id`, `archive_id`.

## Layout (Drive)

```
IDX/cold_archive/YYYY/MM/YYYY-MM-DD/archives/
IDX/cold_archive/YYYY/MM/YYYY-MM-DD/manifests/
IDX/cold_archive/archive_index.json
```

## Colab

Use `colab/cold_archive_migration.ipynb` with Drive mount. Credentials stay in Colab runtime — never commit.

## Modules

- `src/python/archive/drive_fs_backend.py` — path layout + index
- `src/python/archive/migration.py` — state machine + FIFO + journal
