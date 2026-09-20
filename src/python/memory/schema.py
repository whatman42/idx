"""Schema versioning for research memory (Turso/libSQL/SQLite)."""
from __future__ import annotations

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            hypothesis_id TEXT,
            strategy_id TEXT,
            commit_sha TEXT,
            dataset_hash TEXT,
            feature_hash TEXT,
            parameters_hash TEXT,
            cost_model TEXT,
            seed INTEGER,
            status TEXT,
            result_hash TEXT,
            evidence_hash TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(fingerprint)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id TEXT PRIMARY KEY,
            parent_id TEXT,
            hypothesis TEXT,
            counter_hypothesis TEXT,
            source TEXT,
            status TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge (
            knowledge_id TEXT PRIMARY KEY,
            source_type TEXT,
            source_id TEXT,
            category TEXT,
            content TEXT,
            provenance TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS failures (
            failure_id TEXT PRIMARY KEY,
            episode_id TEXT,
            signal_id TEXT,
            failure_type TEXT,
            attribution TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS drift_events (
            drift_id TEXT PRIMARY KEY,
            metric TEXT,
            baseline TEXT,
            observed TEXT,
            regime TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT,
            entity_type TEXT,
            entity_id TEXT,
            fingerprint TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS experiment_events (
            event_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            created_at TEXT NOT NULL
        )
        """,
    ],
}
