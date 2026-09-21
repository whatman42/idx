#!/usr/bin/env python3
"""Restore src/python/ops/paper_portfolio.py from parts under scripts/_pp_parts/."""
import base64
from pathlib import Path

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parts_dir = Path(__file__).resolve().parent / "_pp_parts"
    chunks = sorted(parts_dir.glob("part_*.b64"))
    if not chunks:
        raise SystemExit(f"no parts in {parts_dir}")
    b64 = "".join(p.read_text().strip() for p in chunks)
    raw = base64.b64decode(b64)
    dest = root / "src/python/ops/paper_portfolio.py"
    dest.write_bytes(raw)
    print("restored", dest, "bytes", len(raw))
    assert b"enforce_market_gate" in raw and b"apply_long_entry" in raw

if __name__ == "__main__":
    main()
