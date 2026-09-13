"""Reusable hardware probe for Colab / local / CI (CPU-safe)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
import os
import platform
import time


@dataclass
class HardwareReport:
    cpu_count: int = 0
    cpu_model: str = ""
    ram_gb: float = 0.0
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    cuda_available: bool = False
    cuda_version: str = ""
    lightgbm_gpu: str = "UNKNOWN"
    platform: str = ""
    python_version: str = ""
    is_colab: bool = False
    budget_sec: float = 1200.0
    selected_backend: str = "cpu"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def print_summary(self) -> str:
        lines = [
            "COLAB HARDWARE" if self.is_colab else "RUNTIME HARDWARE",
            f"CPU: {self.cpu_count} ({self.cpu_model or 'n/a'})",
            f"RAM: {self.ram_gb:.1f} GB",
            f"GPU: {self.gpu_name or 'none'}",
            f"GPU RAM: {self.gpu_vram_gb:.2f} GB" if self.gpu_name else "GPU RAM: n/a",
            f"CUDA: {'PASS' if self.cuda_available else 'FAIL/N/A'}"
            + (f" ({self.cuda_version})" if self.cuda_version else ""),
            f"LightGBM GPU: {self.lightgbm_gpu}",
            f"Budget: <={int(self.budget_sec)} sec",
            f"Backend default: {self.selected_backend}",
        ]
        return "\n".join(lines)


def _ram_gb() -> float:
    try:
        import psutil
        return float(psutil.virtual_memory().total) / (1024 ** 3)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = float(line.split()[1])
                    return kb / (1024 ** 2)
    except Exception:
        pass
    return 0.0


def _gpu_via_nvidia_smi() -> tuple[str, float, bool]:
    import subprocess
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=5, text=True,
        ).strip()
        if not out:
            return "", 0.0, False
        line = out.splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts else ""
        vram = float(parts[1]) / 1024.0 if len(parts) > 1 else 0.0
        return name, vram, True
    except Exception:
        return "", 0.0, False


def _torch_cuda() -> tuple[bool, str, str]:
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            ver = getattr(torch.version, "cuda", "") or ""
            return True, name, str(ver)
    except Exception:
        pass
    return False, "", ""


def _lightgbm_gpu_probe() -> str:
    try:
        import lightgbm as lgb
        import numpy as np
        X = np.random.randn(50, 4)
        y = (X[:, 0] > 0).astype(int)
        try:
            clf = lgb.LGBMClassifier(n_estimators=2, device="gpu", verbosity=-1)
            clf.fit(X, y)
            return "PASS"
        except Exception:
            return "FAIL"
    except Exception:
        return "N/A"


def probe_hardware(*, budget_sec: Optional[float] = None, try_lgbm_gpu: bool = False) -> HardwareReport:
    budget = float(budget_sec if budget_sec is not None else os.getenv("COLAB_TRAINING_BUDGET_SEC", "1200"))
    is_colab = os.path.exists("/content") or bool(os.getenv("COLAB_RELEASE_TAG") or os.getenv("COLAB_GPU"))
    if not is_colab:
        try:
            import google.colab  # type: ignore
            is_colab = True
        except Exception:
            pass
    cpu_count = os.cpu_count() or 1
    cpu_model = platform.processor() or platform.machine()
    ram = _ram_gb()
    smi_name, smi_vram, smi_ok = _gpu_via_nvidia_smi()
    torch_ok, torch_name, cuda_ver = _torch_cuda()
    gpu_name = smi_name or torch_name
    cuda_available = bool(smi_ok or torch_ok)
    lgbm = "UNKNOWN"
    if try_lgbm_gpu and cuda_available:
        lgbm = _lightgbm_gpu_probe()
    elif not cuda_available:
        lgbm = "N/A"
    notes = []
    if not cuda_available:
        notes.append("GPU unavailable — CPU fallback")
    else:
        notes.append(f"GPU detected: {gpu_name} — optional backend; Governor decides")
    return HardwareReport(
        cpu_count=cpu_count, cpu_model=str(cpu_model), ram_gb=float(ram),
        gpu_name=str(gpu_name or ""), gpu_vram_gb=float(smi_vram or 0.0),
        cuda_available=cuda_available, cuda_version=str(cuda_ver or ""),
        lightgbm_gpu=lgbm, platform=platform.platform(),
        python_version=platform.python_version(), is_colab=is_colab,
        budget_sec=budget, selected_backend="cpu", notes=notes,
    )


def benchmark_lgbm_cpu_gpu(n_rows: int = 2000, n_features: int = 20, n_estimators: int = 30) -> dict[str, Any]:
    import numpy as np
    try:
        import lightgbm as lgb
    except Exception as e:
        return {"backend": "cpu", "error": f"lightgbm_missing:{e}", "speedup": None}
    rng = np.random.default_rng(42)
    X = rng.normal(size=(n_rows, n_features))
    y = (X[:, 0] + rng.normal(size=n_rows) > 0).astype(int)

    def _fit(device: str) -> float:
        t0 = time.perf_counter()
        clf = lgb.LGBMClassifier(
            n_estimators=n_estimators, max_depth=4, num_leaves=15,
            verbosity=-1, n_jobs=1, device=device, random_state=42,
        )
        clf.fit(X, y)
        return time.perf_counter() - t0

    cpu_s = _fit("cpu")
    try:
        gpu_s = _fit("gpu")
    except Exception as e:
        return {
            "backend": "cpu", "cpu_seconds": cpu_s, "gpu_seconds": None,
            "speedup": None, "reason": f"GPU unavailable or failed: {type(e).__name__}",
        }
    speedup = (cpu_s / gpu_s) if gpu_s and gpu_s > 0 else 0.0
    if speedup > 1.05:
        return {"backend": "gpu", "cpu_seconds": cpu_s, "gpu_seconds": gpu_s,
                "speedup": speedup, "reason": "GPU faster on current workload"}
    return {"backend": "cpu", "cpu_seconds": cpu_s, "gpu_seconds": gpu_s,
            "speedup": speedup, "reason": "CPU faster or comparable on current workload"}
