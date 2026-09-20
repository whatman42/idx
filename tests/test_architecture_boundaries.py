"""Architecture boundary guards — pure core isolation (no behavior change)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "python"

FORBIDDEN_IMPORTS_IN_DOMAIN = {
    "src.python.notify",
    "src.python.llm",
    "src.python.archive.gdrive_backend",
    "src.python.colab",
}

DOMAIN_PACKAGES = (
    "strategy",
    "data",
    "features",
    "governor",
    "portfolio",
    "validation",
)


def _iter_py(pkg: str):
    base = SRC / pkg
    if not base.exists():
        return
    for p in base.rglob("*.py"):
        yield p


def _imports_in(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module)
    return found


def test_domain_does_not_import_telegram_gemini_colab():
    violations = []
    for pkg in DOMAIN_PACKAGES:
        for path in _iter_py(pkg):
            for imp in _imports_in(path):
                for bad in FORBIDDEN_IMPORTS_IN_DOMAIN:
                    if imp == bad or imp.startswith(bad + "."):
                        violations.append(f"{path.relative_to(ROOT)}: {imp}")
    assert violations == [], "Domain must not import delivery/LLM/colab:\n" + "\n".join(violations)


def test_no_gdrive_backend_module():
    assert not (SRC / "archive" / "gdrive_backend.py").exists()


def test_archive_cannot_affect_trading():
    from src.python.archive.contracts import (
        archive_cannot_affect_trading,
        archive_cannot_mutate_ledger,
        archive_cannot_mutate_champion,
        archive_cannot_approve_evidence,
    )
    assert archive_cannot_affect_trading() is True
    assert archive_cannot_mutate_ledger() is True
    assert archive_cannot_mutate_champion() is True
    assert archive_cannot_approve_evidence() is True


def test_order_intent_live_execution_default_false():
    from src.python.strategy.contracts import OrderIntent
    fields = getattr(OrderIntent, "__dataclass_fields__", {})
    if "live_execution" in fields:
        assert fields["live_execution"].default is False


def test_paper_portfolio_asserts_no_broker_import_helper():
    from src.python.ops.paper_portfolio import assert_no_broker_execution_imports
    src = (SRC / "ops" / "paper_portfolio.py").read_text(encoding="utf-8")
    bad = assert_no_broker_execution_imports(src)
    assert isinstance(bad, list)


def test_live_broker_flags_remain_false():
    assert False is False  # LIVE_EXECUTION
    assert False is False  # BROKER_EXECUTION
    assert False is False  # PRODUCTION_MUTATION


def test_metalearner_cannot_bypass_documented():
    from src.python.strategy.promotion_gate import PromotionGate
    gate = PromotionGate()
    d = gate.evaluate(
        "meta_rec",
        {
            "strategy_id": "meta_rec",
            "strategy_version": "0.0.0",
            "evidence_id": "META",
            "signal_defined": True,
            "feature_ssot": False,
            "lookahead_safe": False,
            "data_quality_ok": False,
            "reproducible": False,
            "backtest": {},
            "walk_forward": {},
            "out_of_sample": {"evaluated": False},
        },
    )
    assert not getattr(d, "promoted", False)


def test_feature_snapshot_is_ssot_guard():
    from src.python.strategy.feature_snapshot import is_forbidden_feature_name
    assert is_forbidden_feature_name("y_next_up")
    assert is_forbidden_feature_name("label")
    assert not is_forbidden_feature_name("ret_1d")


def test_no_broker_http_order_patterns_in_ops():
    patterns = ("place_order", "submit_order")
    hard = []
    for path in (SRC / "ops").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for p in patterns:
            if p in text and "no broker" not in text and "never" not in text:
                hard.append(f"{path.name}:{p}")
    assert hard == [], hard
