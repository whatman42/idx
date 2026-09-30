"""Portfolio continuity contract: same ledger path + no reset => continuous state."""
from __future__ import annotations

from pathlib import Path

from src.python.ops.paper_portfolio import (
    PaperPortfolioStore,
    apply_long_entry,
    is_successful_paper_fill,
    new_session,
)


def test_same_path_no_reset_is_continuous(tmp_path: Path):
    path = tmp_path / "paper_portfolio.json"
    store = PaperPortfolioStore(path)
    st = new_session(10_000_000)
    sid = st.simulation_session_id
    st, tr, cls = apply_long_entry(
        st, symbol="AKSI", price=380.0, weight=0.12,
        signal_id="day1a", timestamp="2026-09-29T00:00:00+00:00",
    )
    assert is_successful_paper_fill(cls)
    store.save_atomic(st)

    st2 = store.load()
    assert st2.simulation_session_id == sid
    assert "AKSI" in st2.positions

    st2, tr2, c2 = apply_long_entry(
        st2, symbol="ALDO", price=1196.0, weight=0.12,
        signal_id="day1b", timestamp="2026-09-29T01:00:00+00:00",
    )
    assert is_successful_paper_fill(c2)
    store.save_atomic(st2)

    st3 = store.load()
    assert st3.simulation_session_id == sid
    assert set(st3.positions.keys()) == {"AKSI", "ALDO"}


def test_explicit_reset_new_session(tmp_path: Path):
    path = tmp_path / "paper_portfolio.json"
    store = PaperPortfolioStore(path)
    st = new_session(10_000_000)
    old_sid = st.simulation_session_id
    st, tr, cls = apply_long_entry(
        st, symbol="AKSI", price=380.0, weight=0.12,
        signal_id="r1", timestamp="2026-09-29T00:00:00+00:00",
    )
    store.save_atomic(st)
    old_pf, new_pf = store.archive_and_reset(initial_capital=10_000_000)
    assert new_pf.simulation_session_id != old_sid
    assert not new_pf.positions
    assert old_pf is not None
