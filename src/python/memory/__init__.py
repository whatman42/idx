"""Research / learning persistent memory (Turso/libSQL).

TURSO ≠ Ledger SSOT, Champion, Registry, PromotionGate, or Broker.
Optional: paper trading continues if memory unavailable.
"""
from src.python.memory.client import MemoryStatus, ResearchMemory, get_research_memory
from src.python.memory.schema import SCHEMA_VERSION

__all__ = [
    "MemoryStatus",
    "ResearchMemory",
    "get_research_memory",
    "SCHEMA_VERSION",
]
