"""IDX operational signal bot - SIGNAL ONLY + continuous paper portfolio (Rp10M).
Loader: decompress split payload (PART_A + PART_B).
"""
from __future__ import annotations
import base64, zlib, types
from src.python.ops.sb_payload_a import PART_A
from src.python.ops.sb_payload_b import PART_B
_SRC = zlib.decompress(base64.b64decode(PART_A + PART_B)).decode()
_mod = types.ModuleType(__name__)
_mod.__dict__["__name__"] = __name__
_mod.__dict__["__file__"] = __file__
exec(compile(_SRC, __file__, "exec"), _mod.__dict__)
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
app = _mod.app
if __name__ == "__main__":
    app()
