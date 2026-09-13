"""Fair shadow comparison: same data, T+1, costs; isolated from production paper."""
from __future__ import annotations
from typing import Any, Optional
import pandas as pd

from src.python.data.costs import CostModel
from src.python.governor.governor import MLGovernor, SafetyContext, MarketContext, ResourceProfile
from src.python.governor.utility import score_model_utility
from src.python.ml.families import ModelFamily, FAMILY_SPECS
from src.python.shadow.infer import train_and_signal
from src.python.shadow.ledger import write_shadow_report, load_governor_memory, save_governor_memory
from src.python.validation.economic_sim import simulate_long_only
from src.python.features.version import FEATURE_SET_VERSION
from src.python.validation.cost_sensitivity import cost_grid


PRODUCTION_MODEL = "ops_sma_v0"


def _metrics_from_sim(sim: dict[str, Any]) -> dict[str, Any]:
    trades = sim.get("trades") or []
    nets = [float(t.get("net_pnl", 0)) for t in trades]
    wins = sum(1 for x in nets if x > 0)
    gross_win = sum(x for x in nets if x > 0)
    gross_loss = abs(sum(x for x in nets if x < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (10.0 if gross_win > 0 else 0.0)
    avg = (sum(nets) / len(nets)) if nets else 0.0
    return {
        "signal_count": len(trades),
        "fills": len(trades),
        "win_rate": (wins / len(nets)) if nets else 0.0,
        "net_pnl": float(sum(nets)),
        "gross_pnl": float(sum(float(t.get("gross_pnl", 0)) for t in trades)),
        "expectancy": float(avg),
        "profit_factor": float(pf),
        "max_drawdown": float((sim.get("metrics") or {}).get("max_drawdown") or 0.0),
        "total_trades": int((sim.get("metrics") or {}).get("total_trades") or len(trades)),
    }


def _disagreements(prod: pd.DataFrame, chal: pd.DataFrame, model_id: str) -> list[dict[str, Any]]:
    if prod is None or prod.empty or chal is None or chal.empty:
        return []
    p = prod.copy()
    c = chal.copy()
    p["timestamp"] = pd.to_datetime(p["timestamp"])
    c["timestamp"] = pd.to_datetime(c["timestamp"])
    p["symbol"] = p["symbol"].astype(str)
    c["symbol"] = c["symbol"].astype(str)
    merged = p.merge(c, on=["timestamp", "symbol"], how="outer", suffixes=("_prod", "_chal"))
    rows = []
    for _, r in merged.iterrows():
        sp_raw = r.get("side_prod")
        sc_raw = r.get("side_chal")
        sp = int(sp_raw) if pd.notna(sp_raw) else 0
        sc = int(sc_raw) if pd.notna(sc_raw) else 0
        if sp == sc:
            continue
        kind = "SMA_BUY_ML_FLAT" if (sp == 1 and sc == 0) else "SMA_FLAT_ML_BUY"
        conf = r.get("confidence")
        rows.append({
            "symbol": str(r["symbol"]),
            "timestamp": str(r["timestamp"]),
            "production_signal": sp,
            "challenger_signal": sc,
            "confidence": float(conf) if conf is not None and pd.notna(conf) else None,
            "model_id": model_id,
            "kind": kind,
            "feature_set_version": FEATURE_SET_VERSION,
        })
    return rows


def run_shadow_evaluation(
    bars: pd.DataFrame,
    production_signals: pd.DataFrame,
    *,
    state_dir: str = "state/ops",
    budget_sec: float = 120.0,
    fee_bps: float = 15.0,
    slippage_bps: float = 5.0,
    hold_bars: int = 5,
    safety: Optional[SafetyContext] = None,
    market: Optional[MarketContext] = None,
    max_tier: int = 1,
) -> dict[str, Any]:
    safety = safety or SafetyContext()
    market = market or MarketContext()
    mem = load_governor_memory(state_dir)
    gov = MLGovernor(resources=ResourceProfile.detect(), utility_memory=mem)
    selection = gov.select_models(
        remaining_sec=budget_sec,
        safety=safety,
        market=market,
        purpose="shadow",
    )
    report: dict[str, Any] = {
        "status": "RUNNING",
        "production_model": PRODUCTION_MODEL,
        "production_pointer_unchanged": True,
        "promoted": False,
        "economic_edge": "UNVERIFIED",
        "feature_set_version": FEATURE_SET_VERSION,
        "governor_selection": selection,
        "baseline": {},
        "challengers": {},
        "disagreements": [],
        "shadow_isolated": True,
    }
    if not selection.get("allow"):
        report["status"] = "SHADOW_SKIPPED"
        report["reason"] = selection.get("reason")
        write_shadow_report(state_dir, report)
        return report

    cost = CostModel(fee_bps, slippage_bps)
    base_sim = simulate_long_only(bars, production_signals, cost=cost, hold_bars=hold_bars)
    report["baseline"] = {
        "model_id": PRODUCTION_MODEL,
        "family": "RULE_SMA",
        "metrics": _metrics_from_sim(base_sim),
        "signal_count": int(len(production_signals)) if production_signals is not None else 0,
        "buy_count": int((production_signals["side"] == 1).sum()) if production_signals is not None and not production_signals.empty else 0,
    }

    disagreements: list[dict[str, Any]] = []
    for fam_s in selection.get("families") or []:
        fam = ModelFamily(fam_s)
        out = train_and_signal(bars, fam, max_tier=max_tier)
        mid = out["model_id"]
        sig = out.get("signals")
        if not isinstance(sig, pd.DataFrame):
            sig = pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"])
        sim = simulate_long_only(bars, sig, cost=cost, hold_bars=hold_bars)
        m = _metrics_from_sim(sim)
        m["accuracy"] = (out.get("metrics") or {}).get("accuracy")
        try:
            grid = cost_grid(bars, sig, hold_bars=hold_bars,
                             fee_bps_list=[10.0, 15.0, 25.0],
                             slippage_bps_list=[5.0, 10.0])
            scenarios = grid.get("grid") or []
            if scenarios:
                pos = sum(1 for s in scenarios if float(s.get("net_pnl", 0) or 0) > 0)
                m["cost_survive_ratio"] = pos / len(scenarios)
            else:
                m["cost_survive_ratio"] = None
        except Exception:
            m["cost_survive_ratio"] = None
        ur = score_model_utility(model_id=mid, family=fam_s, metrics=m, train_sec=FAMILY_SPECS[fam].typical_train_sec * 0.25)
        gov.remember_utility(mid, ur)
        buy_n = int((sig["side"] == 1).sum()) if not sig.empty else 0
        report["challengers"][mid] = {
            "family": fam_s,
            "status": out.get("status"),
            "feature_set_version": out.get("feature_set_version"),
            "metrics": m,
            "utility": ur.to_dict(),
            "signal_count": int(len(sig)),
            "buy_count": buy_n,
            "promotion_approved": False,
            "promotion_reason": "shadow_only_default_promote_false",
        }
        disagreements.extend(_disagreements(production_signals, sig, mid))

    report["disagreements"] = disagreements
    report["disagreement_count"] = len(disagreements)
    report["status"] = "SHADOW_OK"
    save_governor_memory(state_dir, gov.utility_memory)
    write_shadow_report(state_dir, report)
    return report
