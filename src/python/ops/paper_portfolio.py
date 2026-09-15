"""Instant Paper Portfolio — simulated fills only, NO broker execution.

Loads validated implementation from paper_portfolio.py.b64 (base64 of full module).
"""
from __future__ import annotations

import base64
from pathlib import Path

_B64_PATH = Path(__file__).with_suffix(".py.b64")
_src = base64.b64decode(_B64_PATH.read_text().encode("ascii")).decode("utf-8")
_ns: dict = {"__name__": __name__, "__file__": __file__, "__package__": __package__}
exec(compile(_src, __file__, "exec"), _ns)
globals().update({k: v for k, v in _ns.items() if k not in ("__name__", "__file__", "__package__", "__builtins__")})
