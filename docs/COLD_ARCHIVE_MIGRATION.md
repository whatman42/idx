# Tiered Cold Storage Lifecycle

There is **no Phase B “decommission GitHub archive”**.

```
GitHub Cold Storage Tier 1
        │  near capacity / retention threshold
        ▼
Colab Migration Bridge (SHA-256 + manifest)
        ▼
Google Drive Pool (drive_01 … drive_N)
```

## Rules

1. New archives enter **GitHub Tier 1**.
2. GitHub keeps them while retention/capacity allows.
3. When Tier-1 exceeds threshold, oldest eligible are **promoted** (copy-forward) to Drive.
4. Transfer + SHA-256 + manifest verification required.
5. **Never delete** from current tier until a **verified copy** exists in another tier.
6. Drive→Drive rotation may release source only after target verified.
7. Failure → keep previous tier copy.

## Threshold policy

`plan_tier1_promotions()` lists oldest archives for promotion when count > `max_tier1_archives`.

GitHub capacity pressure triggers **promotion**, never automatic Tier-1 deletion.

## FIFO meaning

FIFO = **promote oldest eligible to next tier**, not delete from the whole system.

## Modules

| Module | Role |
|--------|------|
| `archive/manager.py` + GitHub backend | Tier 1 write path |
| `archive/drive_fs_backend.py` | Drive path layout |
| `archive/migration.py` | Hash-verified put |
| `archive/tiers.py` | Pool, promotion plan, lifecycle |
