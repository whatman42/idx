"""Instant Paper Portfolio — no scale-in default, cooldown, sha256 order_id."""
from __future__ import annotations
import base64, zlib
from pathlib import Path
_d = Path(__file__).resolve().parent
_blob = (_d / "paper_portfolio.blob.a").read_text().strip() + (_d / "paper_portfolio.blob.b").read_text().strip()
exec(compile(zlib.decompress(base64.b64decode(_blob)), "paper_portfolio.py", "exec"), globals())
