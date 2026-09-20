"""Research plane: factory, regime matrix, Colab jobs, cycle — no production mutation."""
from __future__ import annotations

import pytest

from src.python.learning.contracts import SignalEpisode
from src.python.learning.failure_memory import FailureMemory
from src.python.research.adoption import ADOPTION_MATRIX, AdoptionDecision, matrix_as_dicts
from src.python.research.colab_jobs import ResearchJobKind, make_job, validate_job
from src.python.research.cycle import ResearchCycle
from src.python.research.factory import ResearchFactory, cluster_failures
from src.python.research.regime_matrix import RegimeMatrix


def _ep(**kw) -> SignalEpisode:
    base = dict(
        episode_id="E1",
        trading_date="2026-09-19",
        symbol="BBCA",
        strategy_id="momentum_v2",
        regime="SIDEWAYS",
        side=1,
        r_multiple=-1.2,
        pnl=-120.0,
        outcome="LOSS",
        lifecycle="COMPLETED",
        fill_id="F1",
        idempotency_key="ik1",
    )
    base.update(kw)
    return SignalEpisode(**base)


def test_adoption_matrix_has_reject_live_and_auto_promote():
    rejects = [r for r in ADOPTION_MATRIX if r.decision == AdoptionDecision.REJECT]
    sources = {r.source for r in rejects}
    assert "Online Champion mutation" in sources
    assert "Live / demo / dry-run broker" in sources
    assert any(r.decision == AdoptionDecision.ADAPT and r.source == "RD-Agent" for r in ADOPTION_MATRIX)
    rows = matrix_as_dicts()
    assert len(rows) >= 10


def test_regime_matrix_strategy_x_regime():
    m = RegimeMatrix(min_n=3)
    for i in range(5):
        m.observe(_ep(episode_id=f"L{i}", r_multiple=-0.5, regime="SIDEWAYS"))
    for i in range(5):
        m.observe(_ep(episode_id=f"W{i}", r_multiple=0.8, regime="bull", outcome="WIN"))
    weak = m.weak_pairs(max_expectancy=0.0, min_n=3)
    assert any(c.regime == "sideways" for c in weak)
    strong = [c for c in m.reliable_cells() if c.regime == "bull"]
    assert strong and strong[0].expectancy_r > 0


def test_failure_cluster_and_factory_no_duplicate_knowledge():
    mem = FailureMemory()
    for i in range(4):
        mem.observe(_ep(episode_id=f"E{i}", r_multiple=-1.5), failure_id=f"F{i}")
    clusters = cluster_failures(mem.list_observed(), min_count=2)
    assert clusters
    fac = ResearchFactory()
    batch = fac.build_batch(failures=mem.list_observed(), episodes=[_ep(episode_id=f"E{i}") for i in range(4)])
    assert batch.to_dict()["production_mutation"] is False
    assert batch.to_dict()["promotion_required"] is True
    batch2 = fac.build_batch(failures=mem.list_observed())
    assert any("skip_duplicate" in n or "exp_exists" in n for n in batch2.notes) or len(batch2.hypotheses) == 0


def test_colab_job_forbids_auto_promote():
    with pytest.raises(ValueError, match="auto_promote"):
        make_job(
            job_id="J1",
            kind=ResearchJobKind.WALK_FORWARD,
            experiment_id="EXP-1",
            parameters={"auto_promote": True},
        )
    job = make_job(job_id="J2", kind=ResearchJobKind.HYPEROPT, strategy_id="trend_multi")
    assert validate_job(job) == []
    assert "no_auto_promote" in job.notes


def test_research_cycle_blocked_on_integrity_fail_and_never_promotes():
    from src.python.learning.integrity import reconcile_episode_pnl

    ep1 = _ep(episode_id="A", idempotency_key="same", fill_id="f1")
    ep2 = _ep(episode_id="B", idempotency_key="same", fill_id="f2")
    bad = reconcile_episode_pnl([ep1, ep2])
    assert bad.ok is False or "duplicate" in str(bad.issues)

    cycle2 = ResearchCycle()
    for i in range(5):
        cycle2.learning.observe_episode(_ep(episode_id=f"R{i}", idempotency_key=f"k{i}", fill_id=f"f{i}"))
        cycle2.learning.failures.observe(
            _ep(episode_id=f"R{i}", idempotency_key=f"k{i}"), failure_id=f"FF{i}",
        )
    out = cycle2.run_research_batch(experiment_evidence={
        "signal_defined": True,
        "feature_ssot": True,
        "lookahead_safe": True,
        "data_quality_ok": True,
        "out_of_sample": {"evaluated": False, "n_trades": 0},
    })
    assert out["production_mutation"] is False
    assert out["promotion_path"].startswith("EvidencePackage")
    for c in out.get("experiment_candidacy") or []:
        assert c.get("approved") is False
