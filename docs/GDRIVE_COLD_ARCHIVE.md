# Google Drive = COLD_ARCHIVE_STORAGE only

Not financial truth. Not Ledger. Not Champion. Not PromotionGate.

## Secrets

| Secret | Purpose |
|--------|---------|
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Service account JSON (GitHub Actions secret) |

Scope: `drive.file`

## Layout

```
IDX/cold/{research,evidence,experiments,reports,logs,models,datasets,backups,certification,audit}/
```

## Runtime

Paper trading does **not** depend on Drive. If Drive is down → local fallback or ARCHIVE_UNAVAILABLE; trading continues.

## Architecture

```
Turso = Research Memory
Google Drive = Cold File / Archive
Paper Ledger = Financial Truth
EvidencePackage = Evidence Truth
PromotionGate → Authority → Champion
```
