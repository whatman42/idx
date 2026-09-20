"""Deep-freeze EvidencePackage nested state after construction.

Hash alone is insufficient if callers can mutate nested dicts/lists.
"""
from __future__ import annotations

from typing import Any, Mapping


class FrozenMutationError(TypeError):
    """Raised when attempting to mutate a frozen evidence structure."""


class FrozenDict(dict):
    def __setitem__(self, key, value):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def __delitem__(self, key):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def clear(self):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def pop(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def popitem(self):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def update(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")

    def setdefault(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested dict is immutable")


class FrozenList(list):
    def __setitem__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def __delitem__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def append(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def extend(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def insert(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def pop(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def clear(self):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def remove(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def sort(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")

    def reverse(self):  # type: ignore[no-untyped-def]
        raise FrozenMutationError("EvidencePackage nested list is immutable")


def deep_freeze(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, bytes, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):
        return FrozenDict({k: deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return FrozenList([deep_freeze(v) for v in obj])
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return deep_freeze(obj.to_dict())
    return obj


def freeze_evidence_package(pkg: Any) -> Any:
    """Freeze mutable nested fields on EvidencePackage in-place."""
    for attr in (
        "wf_windows", "hard_rejects", "notes", "regimes_tested",
        "regime_trade_share",
    ):
        if hasattr(pkg, attr):
            val = getattr(pkg, attr)
            if isinstance(val, list):
                frozen_items = []
                for item in val:
                    if hasattr(item, "to_dict"):
                        frozen_items.append(deep_freeze(item.to_dict()))
                    else:
                        frozen_items.append(deep_freeze(item))
                object.__setattr__(pkg, attr, FrozenList(frozen_items))
            elif isinstance(val, dict):
                object.__setattr__(pkg, attr, deep_freeze(val))
    object.__setattr__(pkg, "_frozen", True)
    return pkg
