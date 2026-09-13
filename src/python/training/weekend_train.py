"""Weekend training under hard deadline. Failure → production UNCHANGED.

Trains diverse lightweight ML families selected by MLGovernor (no same-family twins).
Never auto-promotes.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import typer
from src.python.governor.governor import MLGovernor, ResourceProfile
from src.python.scheduler.schedule import SystemClock, TrainingDeadline, classify_schedule, training_run_key, ScheduleType

app = typer.Typer()

def _stage_from_plan(stage: str) -> str:
    if stage in ("exploration", "validation"):
        return stage
    plan = classify_schedule(SystemClock())
    if plan.schedule_type == ScheduleType.SATURDAY_EXPLORATION:
        return "exploration"
    if plan.schedule_type == ScheduleType.SUNDAY_VALIDATION:
        return "validation"
    return "exploration"

def _load_bars_for_train(symbols: str):
    import pandas as pd
    csv = os.getenv("IDX_CSV_PATH", "data/ops/ohlcv.csv")
    if csv and Path(csv).exists():
        df = pd.read_csv(csv)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df, f"csv:{csv}"
    from src.python.market.providers import SyntheticProvider
    syms = [s.strip() for s in symbols.split(",") if s.strip()] or ["BBCA", "BBRI", "TLKM", "ASII", "ICBP"]
    c = SyntheticProvider(n=120, seed=42).fetch(syms)
    return c.df, c.source


@app.command()
def main(
    stage: str = typer.Option("auto"),
    budget_sec: int = typer.Option(1200),
    out_dir: str = typer.Option("models/candidates"),
    symbols: str = typer.Option("BBCA,BBRI,TLKM,ASII,ICBP,BMRI,BBNI,UNVR,KLBF,INDF"),
) -> None:
    clock = SystemClock()
    deadline = TrainingDeadline(internal_budget_sec=budget_sec)
    deadline.start(clock)
    resolved = _stage_from_plan(stage)
    run_date = clock.now().date()
    run_id = training_run_key(run_date, resolved)
    resources = ResourceProfile.detect()
    resources.training_budget_sec = budget_sec
    gov = MLGovernor(resources=resources)
    plan = gov.training_plan(deadline.remaining_sec(clock))
    state_dir = Path(os.getenv("IDX_STATE_DIR", "state"))
    runs_dir = state_dir / "training_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "training_run_id": run_id, "stage": resolved, "started_at": clock.now().isoformat(),
        "budget_sec": budget_sec, "training_plan": plan, "status": "RUNNING",
        "promoted": False, "production_unchanged": True,
    }
    jkt = clock.now().astimezone(ZoneInfo("Asia/Jakarta"))
    emergency = os.getenv("EMERGENCY_TRAINING", "").lower() in ("1", "true", "yes")
    record["timezone"] = "Asia/Jakarta"
    record["local_date"] = str(jkt.date())
    record["emergency_training"] = emergency
    if jkt.weekday() < 5 and not emergency:
        record["status"] = "TRAINING_BLOCKED_WEEKDAY"
        record["reason"] = "weekday_training_forbidden_asia_jakarta"
        (runs_dir / f"{run_id.replace(':', '_')}.json").write_text(json.dumps(record, indent=2, default=str))
        print(json.dumps(record, indent=2, default=str))
        raise SystemExit(0)
    if budget_sec > 1200:
        record["status"] = "TRAINING_DEFERRED"
        record["reason"] = "budget_exceeds_20min_hard_limit"
        (runs_dir / f"{run_id.replace(':', '_')}.json").write_text(json.dumps(record, indent=2, default=str))
        print(json.dumps(record, indent=2, default=str))
        raise SystemExit(0)
    if not plan["allow_train"]:
        record["status"] = "SKIPPED"
        record["reason"] = "budget_too_low"
        (runs_dir / f"{run_id.replace(':', '_')}.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record, indent=2))
        raise SystemExit(0)

    bars, source = _load_bars_for_train(symbols)
    record["data_source"] = source
    from src.python.ml.pipeline import run_lightweight_training
    remaining = deadline.remaining_sec(clock)
    train_report = run_lightweight_training(
        bars, out_dir=out_dir, budget_sec=remaining, governor=gov,
    )
    record["train"] = train_report
    record["status"] = train_report.get("status", "TRAINED_NOT_PROMOTED")
    record["promoted"] = False
    record["production_unchanged"] = True
    record["finished_at"] = clock.now().isoformat()
    (runs_dir / f"{run_id.replace(':', '_')}.json").write_text(json.dumps(record, indent=2, default=str))
    print(json.dumps(record, indent=2, default=str))

if __name__ == "__main__":
    app()
