"""IDX operational signal bot — SIGNAL ONLY + continuous paper portfolio (Rp10M).
Restored atr_opt_v1 payload (zlib+b64 parts). SHA256=91f820df761ecefbbb63e86dc73dfc7f569270582ceecfa77e59a4ece668c7e8
"""
from __future__ import annotations
import base64, zlib
from pathlib import Path
_d = Path(__file__).resolve().parent
_blob = "".join((_d / f"_sb_opt_part{i}.b64").read_text().strip() for i in range(6))
_src = zlib.decompress(base64.b64decode(_blob))
assert __import__("hashlib").sha256(_src).hexdigest() == "91f820df761ecefbbb63e86dc73dfc7f569270582ceecfa77e59a4ece668c7e8", "signal_bot payload corrupt"
exec(compile(_src, __file__, "exec"), globals())
