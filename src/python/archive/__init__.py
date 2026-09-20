"""Cold archive — GitHub Releases + Actions Artifacts + local staging.

Never trading dependency. No GDrive / R2 / S3.
"""
from src.python.archive.contracts import (
    ArchiveReference,
    ArchiveResult,
    ArchiveStatus,
    archive_cannot_affect_trading,
    archive_cannot_approve_evidence,
    archive_cannot_mutate_champion,
    archive_cannot_mutate_ledger,
)
from src.python.archive.manager import ArchiveManager, get_archive_manager

__all__ = [
    "ArchiveManager",
    "ArchiveReference",
    "ArchiveResult",
    "ArchiveStatus",
    "get_archive_manager",
    "archive_cannot_mutate_ledger",
    "archive_cannot_mutate_champion",
    "archive_cannot_approve_evidence",
    "archive_cannot_affect_trading",
]
