from src.python.strategy.evidence import EvidencePackage
from src.python.strategy.evidence_schema import (
    experiment_registry_relpath,
    require_origin,
    validate_evidence_package_dict,
)
import pytest


def test_evidence_package_accepts_provenance_defaults():
    pkg = EvidencePackage(
        strategy_id="rule_sma20",
        evidence_origin="COLAB",
        experiment_id="exp-1",
        git_commit="abc",
    )
    d = pkg.to_dict()
    assert d["evidence_origin"] == "COLAB"
    assert d["experiment_id"] == "exp-1"
    assert "auto_promote" not in d


def test_missing_origin_rejected():
    ok, issues = validate_evidence_package_dict(
        {"strategy_id": "x", "experiment_id": "e", "git_commit": "c", "dataset_checksum": "h"}
    )
    assert ok is False
    assert any("missing_evidence_origin" in i for i in issues)


def test_invalid_origin_rejected():
    ok, issues = validate_evidence_package_dict(
        {
            "strategy_id": "x",
            "evidence_origin": "INFERRED",
            "experiment_id": "e",
            "git_commit": "c",
            "dataset_checksum": "h",
        }
    )
    assert ok is False
    assert any("invalid_evidence_origin" in i for i in issues)


def test_core_and_colab_origins_ok():
    for o in ("CORE", "COLAB", "core", "colab"):
        ok, issues = validate_evidence_package_dict(
            {
                "strategy_id": "rule_sma20",
                "evidence_origin": o,
                "experiment_id": "e1",
                "git_commit": "deadbeef",
                "dataset_checksum": "abc",
            }
        )
        assert ok is True, issues


def test_colab_cannot_set_authority_approved():
    ok, issues = validate_evidence_package_dict(
        {
            "strategy_id": "x",
            "evidence_origin": "COLAB",
            "authority_decision": "APPROVED",
            "experiment_id": "e",
            "git_commit": "c",
            "dataset_checksum": "h",
        }
    )
    assert ok is False
    assert any("colab_cannot_set_authority" in i for i in issues)


def test_validate_rejects_authority_keys():
    ok, issues = validate_evidence_package_dict(
        {
            "strategy_id": "x",
            "evidence_origin": "CORE",
            "auto_promote": True,
            "experiment_id": "e",
            "git_commit": "c",
            "dataset_checksum": "h",
        }
    )
    assert ok is False
    assert any("auto_promote" in i for i in issues)


def test_require_origin_fail_closed():
    with pytest.raises(ValueError):
        require_origin({})
    assert require_origin({"evidence_origin": "colab"}) == "COLAB"


def test_registry_path_safe():
    p = experiment_registry_relpath("exp/../evil")
    assert ".." not in p
    assert p.startswith("IDX/experiment_registry/")
