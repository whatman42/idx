import numpy as np
import pandas as pd
from src.python.validation.cost_sensitivity import cost_grid

def test_cost_grid_labels_unverified():
    idx = pd.bdate_range("2026-01-01", periods=40)
    px = np.linspace(100, 120, len(idx))
    bars = pd.DataFrame({"timestamp": idx, "symbol": "BBCA", "open": px, "high": px+1, "low": px-1, "close": px, "volume": 1e6})
    sig = bars[["timestamp", "symbol"]].assign(side=1)
    out = cost_grid(bars, sig, fee_bps_list=[0, 40], slippage_bps_list=[0, 20])
    assert out["cost_model_status"] == "UNVERIFIED_ASSUMPTION"
    assert len(out["grid"]) == 4
