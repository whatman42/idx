"""Colab compute adapter — thin wrapper around existing training/Governor paths.

Does not own ML logic, production pointer, or paper portfolio state.
Never auto-promotes. Never enables live execution.
"""
from src.python.colab.hardware import probe_hardware, HardwareReport, benchmark_lgbm_cpu_gpu
from src.python.colab.run_training import run_colab_training
from src.python.colab.publish import publish_candidates

__all__ = [
    "probe_hardware",
    "HardwareReport",
    "benchmark_lgbm_cpu_gpu",
    "run_colab_training",
    "publish_candidates",
]
