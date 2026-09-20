# Turso Research Memory — Setup

**Turso is persistent research/learning memory only.**  
Not financial truth, not Champion, not PromotionGate, not Ledger.

## 1. Create database

```bash
turso db create idx-research
turso db show idx-research --url
turso db tokens create idx-research
```

## 2. GitHub Actions secrets

| Secret | Example |
|--------|---------|
| `TURSO_DATABASE_URL` | `libsql://idx-research-xxxx.turso.io` |
| `TURSO_AUTH_TOKEN` | token from `turso db tokens create` |

Repo → Settings → Secrets and variables → Actions.

## 3. Local `.env` (never commit)

```
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
```

## 4. Runtime behavior

| Condition | Result |
|-----------|--------|
| URL + token + reachable | `AVAILABLE` (`turso_libsql` or `turso_http`) |
| URL + token + fail | SQLite **DEGRADED** fallback or `UNAVAILABLE` |
| No env | SQLite — paper trading unaffected |

Schema migrates on connect (`schema_version`).

## 5. Usage

```python
from src.python.memory.client import get_research_memory
from src.python.memory.queries import write_experiment, query_by_fingerprint

mem = get_research_memory()
write_experiment(mem, {
    "experiment_id": "EXP-1",
    "fingerprint": "abc...",
    "status": "COMPLETED",
    "result_hash": "...",
})
print(query_by_fingerprint(mem, "abc..."))
```

## 6. Drivers

1. Optional: `pip install libsql`
2. Default remote path: **httpx** → `/v2/pipeline` (already in requirements)

## 7. Boundaries

- PRODUCTION MUTATION = FALSE
- AUTO PROMOTE = FALSE
- TURSO → Champion / Ledger / Promotion = FALSE
