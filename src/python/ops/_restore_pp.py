#!/usr/bin/env python3
"""One-shot restore paper_portfolio.py from base64 parts."""
from pathlib import Path
import base64
root = Path(__file__).resolve().parent
parts = sorted((root / "_pp_parts").glob("part*.b64"))
data = "".join(p.read_text().strip() for p in parts)
out = root / "paper_portfolio.py"
out.write_bytes(base64.b64decode(data))
print(f"restored {out} bytes={out.stat().st_size} parts={len(parts)}")
