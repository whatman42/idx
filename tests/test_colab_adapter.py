"""Colab adapter tests — CPU-safe, no GPU required, no promotion."""
from __future__ import annotations
import json
from pathlib import Path
from src.python.colab.hardware import probe_hardware, benchmark_lgbm_cpu_gpu, HardwareReport
from src.python.colab.run_training import run_colab_training, _dataset_fingerprint
from src.python.colab.publish import publish_candidates
from src.python.registry.artifacts import find_production_version
from src.python.market.providers import SyntheticProvider
from src.python.ops.paper_portfolio import paper_reset_scope


def test_probe_hardware_cpu_fallback():
    hw = probe_hardware(budget_sec=100)
    assert isinstance(hw, HardwareReport)
    assert hw.cpu_count >= 1
    assert hw.budget_sec == 100
    assert hw.selected_backend in ("cpu", "gpu")
    assert hw.to_dict()["python_version"]
    text = hw.print_summary()
    assert "Budget" in text


def test_benchmark_cpu_path_always():
    r = benchmark_lgbm_cpu_gpu(n_rows=200, n_features=8, n_estimators=5)
    assert "backend" in r
    assert r["backend"] in ("cpu", "gpu")


def test_run_colab_training_no_promote(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "models" / "candidates"
    rep = tmp_path / "artifacts" / "training"
    models = tmp_path / "models"
    models.mkdir(parents=True)
    report = run_colab_training(
        budget_sec=90,
        out_dir=str(out),
        report_dir=str(rep),
        symbols="BBCA,BBRI,TLKM,ASII",
        promote=True,
        run_shadow=False,
        try_gpu_benchmark=False,
        models_dir=str(models),
    )
    assert report["promoted"] is False
    assert report["promotion"]["decision"] == "REJECT"
    assert report["production_pointer_unchanged"] is True
    assert report["economic_edge"] == "UNVERIFIED"
    assert report["live_execution"] is False
    assert (rep / "last_training_report.json").exists()
    assert find_production_version(models, "ops_sma_v0") is None


def test_dataset_fingerprint_stable():
    bars = SyntheticProvider(n=30, seed=1).fetch(["BBCA"]).df
    a = _dataset_fingerprint(bars)
    b = _dataset_fingerprint(bars)
    assert a == b
    assert len(a) == 64


def test_publish_without_token(monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    r = publish_candidates(paths=[])
    assert r["status"] == "SKIPPED"
    assert r["token_present"] is False
    assert r.get("production_pointer_touched") is False


def test_publish_does_not_echo_token(monkeypatch):
    monkeypatch.setenv("GH_PAT", "ghp_fake_token_should_not_appear")
    r = publish_candidates(paths=["/nonexistent/file.json"])
    dumped = json.dumps(r)
    assert "ghp_fake" not in dumped


def test_paper_reset_does_not_claim_model_wipe():
    scope = paper_reset_scope()
    assert scope["resets"] == "PAPER_ACCOUNT_STATE_ONLY"
    preserved = " ".join(scope.get("preserved") or []).lower()
    assert "model" in preserved or "governor" in preserved


def test_budget_env(monkeypatch, tmp_path):
    monkeypatch.setenv("COLAB_TRAINING_BUDGET_SEC", "45")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    report = run_colab_training(
        budget_sec=45,
        out_dir=str(tmp_path / "cand"),
        report_dir=str(tmp_path / "rep"),
        symbols="BBCA,BBRI,TLKM",
        run_shadow=False,
        try_gpu_benchmark=False,
        models_dir=str(tmp_path / "models"),
    )
    assert report["budget"]["requested_sec"] == 45
    assert report["promoted"] is False
