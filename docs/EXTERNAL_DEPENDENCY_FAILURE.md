# External Dependency Failure Model

**EXTERNAL FAILURE ≠ DATA SUCCESS**

## Required vs Optional (per-job)

| Dependency | Plane role | Required when |
|------------|------------|---------------|
| Market data | Research input | experiment needs OHLCV |
| Colab | Heavy compute | `requires_colab=True` (WFA/ML) |
| Turso | Research memory | `requires_memory=True` (rare) |
| Drive | Artifact store | `requires_artifact=True` |
| LLM | Reasoning | `requires_llm=True` |
| Actions | Control plane | never required for correctness |

Lightweight deterministic research may run with Colab UNAVAILABLE.

## Memory read semantics

| Result | Meaning |
|--------|---------|
| MATCH_FOUND | Row exists |
| NO_MATCH | Memory available; no row |
| MEMORY_UNAVAILABLE | Cannot trust absence |

**MEMORY_UNAVAILABLE ≠ NO_MATCH**

## Memory write semantics

MEMORY_WRITE_SUCCESS (persisted=True) · MEMORY_WRITE_FAILED · MEMORY_UNAVAILABLE

## Authority chain

EvidencePackage → PromotionGate → Authority → Champion

Turso / Drive / Colab / LLM / Actions **cannot approve**.
