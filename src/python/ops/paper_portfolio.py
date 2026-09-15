"""Instant Paper Portfolio — simulated fills only, NO broker execution.

Loads validated implementation from gzip+base64 sidecar.
"""
from __future__ import annotations
import base64, gzip
from pathlib import Path

_p = Path(__file__).with_suffix(".py.gz.b64")
_src = gzip.decompress(base64.b64decode(_p.read_text().encode("ascii"))).decode("utf-8")
_ns: dict = {"__name__": __name__, "__file__": __file__, "__package__": __package__}
exec(compile(_src, __file__, "exec"), _ns)
globals().update({k: v for k, v in _ns.items() if k not in ("__name__", "__file__", "__package__", "__builtins__")})
