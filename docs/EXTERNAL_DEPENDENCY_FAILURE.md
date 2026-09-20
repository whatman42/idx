# External Dependency Failure Model

**EXTERNAL FAILURE ≠ DATA SUCCESS**

External services may fail. Research must degrade **explicitly**. Required evidence must **fail closed**. Paper Ledger remains correct. Champion remains protected.

## Inventory

| Dependency | Required/Optional | Failure State | Fallback | Continue Research? | Promote? | Affect Ledger? |
|------------|-------------------|---------------|----------|--------------------|----------|----------------|
| Turso/libSQL | Optional | UNAVAILABLE/AUTH/NETWORK | MEMORY_UNAVAILABLE / SQLite | Yes (without memory) | No | No |
| SQLite local | Optional | CONFIG | MEMORY_UNAVAILABLE | Yes | No | No |
| Google Colab | Required (heavy jobs) | TIMEOUT/INCOMPLETE/MISSING | QUEUE/BLOCK; no heavy WFA on Actions | No (for that job) | No | No |
| Google Drive | Optional | AUTH/MISSING/CORRUPT | ARTIFACT_STORAGE_DEGRADED | Yes | No | No |
| Gemini/LLM | Optional | UNAVAILABLE/TIMEOUT | LLM_UNAVAILABLE; no fabrication | Yes | No | No |
| Market data | Required | STALE/INVALID/NETWORK | BLOCK research | No | No | No |
| GitHub API publish | Optional | AUTH/NETWORK | record error | Yes | No | No |
| GitHub Actions | Optional control plane | TIMEOUT | scheduler retry only | Yes (lightweight) | No | No |

## Status codes

AVAILABLE · DEGRADED · UNAVAILABLE · TIMEOUT · AUTH_ERROR · CONFIG_ERROR · NETWORK_ERROR · DATA_INVALID · DATA_STALE · ARTIFACT_MISSING · ARTIFACT_CORRUPT · INTEGRITY_ERROR

## Composite job

SUCCESS only if all **required** dependencies are AVAILABLE.
Optional degraded → DEGRADED (metadata explicit).
Required fail → BLOCKED/FAILED → **no promotion candidacy**.

## Authority chain (unchanged)

EvidencePackage → PromotionGate → Authority → Champion

Turso, Drive, Colab, Gemini **cannot approve**.
