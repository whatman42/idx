# Cold Archive — GitHub Free (No GDrive / No paid storage)

## Backends

| Backend | Role | Retention |
|---------|------|-----------|
| Local workspace | Staging / compress / verify | Ephemeral |
| GitHub Actions Artifacts | Temporary / cert evidence | 7–14 days |
| GitHub Releases | Long-term cold archive | Retain (manual review) |

## Forbidden

Google Drive, R2, S3, paid object storage, credit-card dependencies.

## Architecture

```
Turso            = Research Memory
GitHub Releases  = Cold Archive
Actions Artifact = Temporary archive
Paper Ledger     = Financial Truth
EvidencePackage  = Evidence Truth
PromotionGate → Authority → Champion
```

Archive failure does **not** stop paper trading.

## Pipeline

secret scan → tar.gz → SHA-256 → verify → persist → re-read → SHA-256

Identity: `{artifact_id}:{content_sha256}:{schema_version}`

- Same identity → `ARCHIVE_ALREADY_PRESENT`
- Same artifact_id, different hash → `ARCHIVE_CONFLICT`

## Certification

`.github/workflows/cold_archive_certification.yml` (workflow_dispatch, main only)
