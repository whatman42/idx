from src.python.strategy.evidence import EvidencePackage
from src.python.strategy.evidence_schema import (
    experiment_registry_relpath,
    validate_evidence_package_dict,
)


def test_evidence_package_accepts_provenance_defaults():
    pkg = EvidencePackage(strategy_id="rule_sma20", experiment_id="exp-1", git_commit="abc")
    d = pkg.to_dict()
    assert d["experiment_id"] == "exp-1"
    assert d["git_commit"] == "abc"
    assert "auto_promote" not in d


def test_validate_rejects_authority_keys():
    ok, issues = validate_evidence_package_dict(
        {
            "strategy_id": "x",
            "auto_promote": True,
            "experiment_id": "e",
            "git_commit": "c",
            "dataset_checksum": "h",
        }
    )
    assert ok is False
    assert any("auto_promote" in i for i in issues)


def test_validate_ok_minimal():
    ok, issues = validate_evidence_package_dict(
        {
            "strategy_id": "rule_sma20",
            "experiment_id": "e1",
            "git_commit": "deadbeef",
            "dataset_checksum": "abc",
        }
    )
    assert ok is True


def test_registry_path_safe():
    p = experiment_registry_relpath("exp/../evil")
    assert ".." not in p
    assert p.startswith("IDX/experiment_registry/")
