"""SKIPPED_CASH / REJECTED must not claim portfolio position in report or state."""
from __future__ import annotations

from pathlib import Path

from src.python.ops.paper_portfolio import (
    PaperPortfolioStore,
    apply_long_entry,
    new_session,
)
from src.python.reporting.composer import DeterministicComposer
from src.python.reporting.models import (
    CycleReport,
    OpenPositionView,
    PortfolioSnapshot,
    SignalReport,
)
from src.python.reporting.validation import validate_telegram_payload


def test_skipped_cash_does_not_create_position():
    st = new_session(1_000.0)
    st.cash = 50.0
    st2, trade, cls = apply_long_entry(
        st,
        symbol="ADES",
        price=35950.0,
        weight=0.15,
        signal_id="sig_ades_2",
        timestamp="2026-09-29T00:00:00+00:00",
    )
    assert cls == "SKIPPED_CASH"
    assert trade is None
    assert "ADES" not in st2.positions


def test_paper_filled_creates_position():
    st = new_session(10_000_000)
    st2, trade, cls = apply_long_entry(
        st,
        symbol="AKSI",
        price=380.0,
        weight=0.12,
        signal_id="sig_aksi",
        timestamp="2026-09-29T00:00:00+00:00",
    )
    assert cls == "PAPER_FILLED"
    assert trade is not None
    assert trade.get("portfolio_mutated") is True
    assert "AKSI" in st2.positions


def test_report_skipped_does_not_claim_position():
    sig = SignalReport(
        signal_id="s1",
        timestamp="2026-09-29T00:00:00+00:00",
        decision="BUY",
        symbol="ADES",
        fill_status="SKIPPED_CASH",
        entry_reference=35950.0,
    )
    pf = PortfolioSnapshot(
        initial_capital=10_000_000,
        equity=9_995_252,
        cash=7_622_252,
        market_value=2_373_000,
        exposure_pct=23.74,
        realized_pnl=0.0,
        unrealized_pnl=-1186.0,
        open_positions=[
            OpenPositionView(symbol="AKSI", entry_price=380, mark_price=380, shares=3100, lots=31, market_value=1_178_000, unrealized_pnl=-589),
            OpenPositionView(symbol="ALDO", entry_price=1196, mark_price=1195, shares=1000, lots=10, market_value=1_195_000, unrealized_pnl=-597),
        ],
    )
    report = CycleReport(
        trading_date="2026-09-29",
        integrity_ok=True,
        live_execution=False,
        mode="PAPER",
        signal=sig,
        portfolio=pf,
    )
    text = DeterministicComposer().compose(report)
    assert "ASET PORTOFOLIO: ADES tercatat" not in text
    assert "SKIPPED_CASH" in text or "Tidak ada PAPER_FILL" in text
    errs = validate_telegram_payload(text, report)
    assert "skipped_claimed_as_position" not in errs


def test_report_filled_claims_only_if_in_ssot():
    sig = SignalReport(
        signal_id="s2",
        timestamp="2026-09-29T00:00:00+00:00",
        decision="BUY",
        symbol="ASMI",
        fill_status="PAPER_FILLED",
        entry_reference=18.0,
        lots=666,
        shares=66600,
    )
    pf = PortfolioSnapshot(
        initial_capital=10_000_000,
        equity=9_995_204,
        cash=7_597_904,
        market_value=2_397_300,
        exposure_pct=23.98,
        realized_pnl=0.0,
        unrealized_pnl=-1199.0,
        open_positions=[
            OpenPositionView(symbol="ASMI", entry_price=18, mark_price=18, shares=66600, lots=666, market_value=1_198_800, unrealized_pnl=-599),
        ],
    )
    report = CycleReport(
        trading_date="2026-09-29",
        integrity_ok=True,
        live_execution=False,
        mode="PAPER",
        signal=sig,
        portfolio=pf,
    )
    text = DeterministicComposer().compose(report)
    assert "ASET PORTOFOLIO: ASMI tercatat" in text


def test_portfolio_persists_across_cycles(tmp_path: Path):
    path = tmp_path / "paper_portfolio.json"
    store = PaperPortfolioStore(path)
    st = new_session(10_000_000)
    st, trade, cls = apply_long_entry(
        st,
        symbol="AKSI",
        price=380.0,
        weight=0.12,
        signal_id="c1",
        timestamp="2026-09-29T00:00:00+00:00",
    )
    assert cls == "PAPER_FILLED"
    store.save_atomic(st)
    st2 = store.load()
    assert "AKSI" in st2.positions
    st2, t2, c2 = apply_long_entry(
        st2,
        symbol="ALDO",
        price=1196.0,
        weight=0.12,
        signal_id="c2",
        timestamp="2026-09-29T01:00:00+00:00",
    )
    assert c2 == "PAPER_FILLED"
    assert "AKSI" in st2.positions and "ALDO" in st2.positions
    store.save_atomic(st2)
    st3 = store.load()
    assert set(st3.positions.keys()) == {"AKSI", "ALDO"}


def test_asmi_lot_quantity_conversion():
    st = new_session(10_000_000)
    st2, trade, cls = apply_long_entry(
        st,
        symbol="ASMI",
        price=18.0,
        weight=0.12,
        signal_id="asmi1",
        timestamp="2026-09-29T00:00:00+00:00",
        lot_size=100,
    )
    assert cls == "PAPER_FILLED", cls
    assert trade is not None
    lots = trade["qty"] / 100.0
    assert abs(lots - round(lots)) < 1e-9
    assert trade["qty"] * trade["fill_price"] <= 1_250_000


def test_equity_equals_cash_plus_mv():
    st = new_session(10_000_000)
    st, trade, cls = apply_long_entry(
        st,
        symbol="AKSI",
        price=380.0,
        weight=0.12,
        signal_id="eq1",
        timestamp="2026-09-29T00:00:00+00:00",
    )
    assert cls == "PAPER_FILLED"
    marks = {"AKSI": 380.0}
    eq = st.equity(marks)
    mv = sum(float(p["qty"]) * marks["AKSI"] for p in st.positions.values())
    assert abs(eq - (st.cash + mv)) < 1.0
