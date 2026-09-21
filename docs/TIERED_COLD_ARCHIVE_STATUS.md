# Tiered Cold Archive — Status

| Plane | Status |
|-------|--------|
| Trading Core | CERTIFIED / FROZEN (`5bb33b0` behavior) |
| Archive Plane | CERTIFIED |
| GitHub Tier 1 | ACTIVE (primary cold) |
| Drive Pool | ACTIVE (architecture) |
| Tier Promotion | IMPLEMENTED |
| SHA-256 | ENFORCED |
| Fail-closed | ENFORCED |
| Multi-account Drive | SUPPORTED BY ARCHITECTURE |
| GitHub Decommission | **NONE** |
| Live / Broker | FALSE |

## Capacity model

GitHub growth is expected under `deleted_source=False` for Tier-1→Drive.

- **Threshold** → plan/promote oldest eligible to Drive (copy-forward)
- **Not** → delete Tier-1 because capacity is tight
- Optional Tier-1 release only via `may_release_from_tier1` when policy min verified copies exist (caller-controlled; engine does not auto-delete GitHub Release assets)

## What CI proves vs does not

| Proved in CI | Not proved in CI |
|--------------|------------------|
| Lifecycle engine | Live Google OAuth |
| SHA-256 dual verify | Real multi-account Drive transfer |
| Fail-closed / no wipe | Colab runtime auth |
| Pool select by capacity | Network Drive quota APIs |

Operational proof of Colab → multi-account Drive remains an **operator run** using `colab/cold_archive_migration.ipynb` with mounted accounts mapped to `drive_01…N`.
