from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ResourceProfile:
    cpu_count: int = 2
    ram_gb: float = 4.0
    gpu_name: str = ""
    vram_gb: float = 0.0
    training_budget_sec: float = 1200.0

    @classmethod
    def detect(cls) -> "ResourceProfile":
        import os
        return cls(cpu_count=os.cpu_count() or 2)

@dataclass
class MLGovernor:
    resources: ResourceProfile = field(default_factory=ResourceProfile.detect)

    def training_plan(self, remaining_sec: float) -> dict[str, Any]:
        allow = remaining_sec >= 30
        return {"allow_train": allow, "workload": "PRIMARY" if allow else "SKIP",
                "remaining_sec": remaining_sec}
