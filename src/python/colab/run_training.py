"""Colab/local training orchestrator — invokes existing repo paths only.

Never auto-promotes. Never mutates production pointer.
Hard budget via COLAB_TRAINING_BUDGET_SEC (default 1200).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.python.colab.hardware import probe_hardware, benchmark_lgbm_cpu_gpu
from src.python.governor.governor import MLGovernor, SafetyContext, MarketContext, ResourceProfile
from src.python.ml.pipeline import run_lightweight_training
from src.python.registry.artifacts import find_production_version
from src.python.registry.promotion import evaluate_promotion
from src.python.features.version import FEATURE_SET_VERSION


def _git_commit() -> str:
    env = os.getenv("GITHUB_SHA") or os.getenv("IDX_COMMIT") or ""
    if env:
        return env[:40]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()[:40]
    except Exception:
        return "UNKNOWN"


def _dataset_fingerprint(bars) -> str:
    if bars is None or (hasattr(bars, "empty") and bars.empty):
        return "empty"
    cols = [c for c in ("timestamp", "symbol", "open", "high", "low", "close", "volume") if c in bars.columns]
    raw = bars[cols].sort_values([c for c in ("symbol", "timestamp") if c in cols]).to_csv(index=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _load_bars(csv_path: Optional[str], symbols: str):
    import pandas as pd
    from src.python.market.providers import SyntheticProvider
    from src.python.data.quality import validate_ohlcv

    if csv_path and Path(csv_path).exists():
        df = pd.read_csv(csv_path)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        source = f"csv:{csv_path}"
    else:
        env_csv = os.getenv("IDX_CSV_PATH", "data/ops/ohlcv.csv")
        if env_csv and Path(env_csv).exists():
            df = pd.read_csv(env_csv)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            source = f"csv:{env_csv}"
        else:
            syms = [s.strip() for s in symbols.split(",") if s.strip()] or [
                "BBCA", "BBRI", "TLKM", "ASII", "ICBP"
            ]
            c = SyntheticProvider(n=120, seed=42).fetch(syms)
            df, source = c.df, c.source
    q = validate_ohlcv(df)
    return df, source, q


def run_colab_training(
    *,
    budget_sec: float = 1200.0,
    out_dir: str = "models/candidates",
    report_dir: str = "artifacts/training",
    symbols: str = "BBCA,BBRI,TLKM,ASII,ICBP,BMRI,BBNI,UNVR,KLBF,INDF",
    csv_path: Optional[str] = None,
    promote: bool = False,
    run_shadow: bool = True,
    try_gpu_benchmark: bool = True,
    models_dir: str = "models",
) -> dict[str, Any]:
    t0 = time.perf_counter()
    budget_sec = float(os.getenv("COLAB_TRAINING_BUDGET_SEC", budget_sec))
    prod_before = find_production_version(models_dir, "ops_sma") or find_production_version(models_dir, "ops_sma_v0")
    prod_files_before = sorted(str(p) for p in Path(models_dir).glob("**/*.PRODUCTION")) if Path(models_dir).exists() else []

    hw = probe_hardware(budget_sec=budget_sec, try_lgbm_gpu=False)
    gpu_bench = None
    if try_gpu_benchmark and hw.cuda_available:
        remaining = budget_sec - (time.perf_counter() - t0)
        if remaining > 60:
            try:
                gpu_bench = benchmark_lgbm_cpu_gpu()
                hw.selected_backend = gpu_bench.get("backend") or "cpu"
            except Exception as e:
                gpu_bench = {"backend": "cpu", "error": str(e)[:200]}
                hw.selected_backend = "cpu"
        else:
            gpu_bench = {"backend": "cpu", "reason": "budget_too_low_for_benchmark"}
            hw.selected_backend = "cpu"
    else:
        hw.selected_backend = "cpu"
        gpu_bench = {"backend": "cpu", "reason": "gpu_unavailable_or_disabled"}

    bars, source, dq = _load_bars(csv_path, symbols)
    if not dq.ok:
        report = {
            "status": "HALTED_DATA_QUALITY",
            "dq_issues": list(dq.issues)[:20],
            "hardware": hw.to_dict(),
            "promotion": {"decision": "REJECT", "reason": "invalid_data"},
            "promoted": False,
            "production_pointer_before": prod_before,
            "production_pointer_after": prod_before,
            "production_pointer_unchanged": True,
            "economic_edge": "UNVERIFIED",
        }
        _write_report(report_dir, report)
        return report

    remaining = budget_sec - (time.perf_counter() - t0)
    resources = ResourceProfile.detect()
    resources.training_budget_sec = remaining
    gov = MLGovernor(resources=resources)
    safety = SafetyContext(dq_ok=True, data_available=True)
    selection = gov.select_models(remaining_sec=remaining, safety=safety, market=MarketContext(), purpose="train")

    train_report = run_lightweight_training(bars, out_dir=out_dir, budget_sec=remaining, governor=gov)
    train_report["promoted"] = False
    train_report["promote_requested"] = bool(promote)

    commit = _git_commit()
    fp = _dataset_fingerprint(bars)
    artifacts = []
    for r in train_report.get("results") or []:
        path = r.get("path")
        meta_path = Path(str(path).replace(".joblib", ".meta.json")) if path else None
        model_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).exists() else ""
        meta = {
            "model_id": r.get("model_id"),
            "model_family": r.get("family"),
            "algorithm": r.get("family"),
            "feature_version": FEATURE_SET_VERSION,
            "schema_version": "ops_paper_v1",
            "training_commit": commit,
            "dataset_fingerprint": fp,
            "training_date": datetime.now(timezone.utc).isoformat(),
            "data_source": source,
            "symbols": sorted(bars["symbol"].astype(str).unique().tolist()) if "symbol" in bars.columns else [],
            "hardware": hw.to_dict(),
            "backend": hw.selected_backend,
            "runtime": r.get("train_sec"),
            "governor_decision": selection,
            "metrics": r.get("metrics"),
            "status": r.get("status", "TRAINED_NOT_PROMOTED"),
            "model_hash": model_hash,
            "promoted": False,
            "production_unchanged": True,
        }
        promo = evaluate_promotion(r.get("metrics") or {})
        meta["promotion"] = {"approved": promo.approved, "reason": promo.reason}
        if meta_path:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if meta_path.exists():
                try:
                    existing = json.loads(meta_path.read_text())
                except Exception:
                    existing = {}
            existing.update(meta)
            meta_path.write_text(json.dumps(existing, indent=2, default=str))
            meta["artifact_hash"] = hashlib.sha256(meta_path.read_bytes()).hexdigest()
            existing["artifact_hash"] = meta["artifact_hash"]
            meta_path.write_text(json.dumps(existing, indent=2, default=str))
        artifacts.append(meta)
        r["promotion_approved"] = False
        r["promotion_reason"] = "colab_default_promote_false" if promote else promo.reason

    shadow_report = None
    if run_shadow and remaining > 30:
        try:
            from src.python.shadow.compare import run_shadow_evaluation
            from src.python.ops.signal_bot import _naive_signals_from_bars, _latest_day_signals
            all_sig = _naive_signals_from_bars(bars)
            day_sig = _latest_day_signals(all_sig)
            shadow_budget = min(90.0, budget_sec - (time.perf_counter() - t0))
            if shadow_budget >= 30:
                shadow_report = run_shadow_evaluation(bars, day_sig, state_dir="state/ops", budget_sec=shadow_budget)
                Path(report_dir).mkdir(parents=True, exist_ok=True)
                (Path(report_dir) / "shadow_report.json").write_text(json.dumps(shadow_report, indent=2, default=str))
        except Exception as e:
            shadow_report = {"status": "SHADOW_ERROR", "error": f"{type(e).__name__}: {e}"[:200]}

    elapsed = time.perf_counter() - t0
    prod_after = find_production_version(models_dir, "ops_sma") or find_production_version(models_dir, "ops_sma_v0")
    prod_files_after = sorted(str(p) for p in Path(models_dir).glob("**/*.PRODUCTION")) if Path(models_dir).exists() else []

    report: dict[str, Any] = {
        "status": train_report.get("status", "TRAINED_NOT_PROMOTED"),
        "commit": commit,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "hardware": hw.to_dict(),
        "gpu_benchmark": gpu_bench,
        "governor": selection,
        "feature_set_version": FEATURE_SET_VERSION,
        "data_source": source,
        "dataset_fingerprint": fp,
        "n_rows": int(len(bars)),
        "models": train_report.get("results") or [],
        "artifacts": artifacts,
        "oos": {"note": "temporal split inside train_family; economic edge UNVERIFIED"},
        "calibration": {"status": "NOT_RUN"},
        "shadow": shadow_report,
        "budget": {
            "requested_sec": budget_sec,
            "actual_runtime_sec": elapsed,
            "remaining_sec": max(0.0, budget_sec - elapsed),
            "models_trained": len([m for m in (train_report.get("results") or []) if m.get("status") == "TRAINED_NOT_PROMOTED"]),
            "models_skipped": 0,
        },
        "promotion": {"decision": "REJECT", "reason": "colab_training_never_auto_promotes"},
        "promoted": False,
        "promote_requested": bool(promote),
        "production_pointer_before": prod_before,
        "production_pointer_after": prod_after,
        "production_pointer_unchanged": (prod_before == prod_after) and (prod_files_before == prod_files_after),
        "production_model": "ops_sma_v0",
        "economic_edge": "UNVERIFIED",
        "live_execution": False,
        "signal_only": True,
    }
    _write_report(report_dir, report)
    return report


def _write_report(report_dir: str, report: dict[str, Any]) -> Path:
    d = Path(report_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "last_training_report.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    return path
