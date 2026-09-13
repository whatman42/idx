"""Colab compute adapter — thin wrapper around existing training/Governor paths.

Does not own ML logic, production pointer, or paper portfolio state.
"""
from src.python.colab.hardware import probe_hardware, HardwareReport

__all__ = ["probe_hardware", "HardwareReport"]
