# Tiered Cold Storage Lifecycle

There is **no Phase B “decommission GitHub archive”**.

```
GitHub Cold Storage Tier 1
        │  near capacity / retention policy
        ▼
Colab Migration Bridge (SHA-256 + manifest)
        ▼
Google Drive Tier 2 (drive_01)
        │  near capacity
        ▼
Drive Account N (pool rotation)
```

## Rules

1. New archives enter **GitHub Tier 1**.
2. GitHub keeps them while retention/capacity allows.
3. Eligible oldest archives are **promoted** to Drive pool.
4. Transfer + SHA-256 + manifest verification required.
5. **Never delete** from current tier until a **verified copy** exists in another tier.
6. Drive→Drive rotation follows the same rule.
7. Failure → keep previous tier copy.

## FIFO meaning

FIFO = **promote oldest eligible to next tier**, not delete from the whole system.

## Modules

| Module | Role |
|--------|------|
| `archive/manager.py` + GitHub backend | Tier 1 write path |
| `archive/drive_fs_backend.py` | Drive path layout |
| `archive/migration.py` | Hash-verified put |
| `archive/tiers.py` | Pool, promotion policy, lifecycle |
