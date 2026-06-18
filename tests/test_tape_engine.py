"""Trade-tape fill model verification.

Core rule (from the research design): a resting BUY fills ONLY on a SELL print
at price <= threshold (a SELL proves a taker hit a resting bid => marketable
liquidity existed at or below our bid). BUY prints never fill a resting BUY.
Fill executes at our limit T (not the deeper print). Per-token streams are
independent (temporal double-dip). Settlement tail is excluded. Resolution is
read only at settlement, never in the fill path.
"""
import inspect
import math

import pytest

from polymarket_arb.engine import (ARB_LOCKED, HEDGED_NEGEDGE, NO_FILL,
                                    UNHEDGED_LOSS, UNHEDGED_WIN)
from polymarket_arb.tape_engine import TapeBacktester, TapeConfig
from polymarket_arb.trades import Trade, TradeWindow


def _tw(yes_trades, no_trades, resolution_yes, open_ts=1000.0, close_ts=1300.0):
    return TradeWindow(slug="btc-updown-5m-1000", asset="BTC",
                       open_ts=open_ts, close_ts=close_ts,
                       yes_token="Y", no_token="N",
                       yes_trades=yes_trades, no_trades=no_trades,
                       resolution_yes=resolution_yes)


def _t(ts, side, price, size=100.0, token="Y"):
    return Trade(ts=float(ts), token=token, side=side, price=price, size=size,
                 tx="0x", outcome_index=0)


# ---------------------------------------------------------------------------
# CORE RULE: SELL fills, BUY does not
# ---------------------------------------------------------------------------
def test_sell_print_at_or_below_threshold_fills():
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "SELL", 0.40)], [], resolution_yes=1.0)
    r = bt.run_window(w)
    assert r.yes_fill is not None
    assert r.yes_fill.ts == 1100


def test_buy_print_below_threshold_does_NOT_fill():
    """A BUY (ask lift) does not prove a seller would reach our resting bid."""
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "BUY", 0.13)], [], resolution_yes=1.0)
    r = bt.run_window(w)
    assert r.yes_fill is None
    assert r.outcome == NO_FILL


def test_sell_above_threshold_does_not_fill():
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "SELL", 0.46)], [], resolution_yes=1.0)
    assert bt.run_window(w).yes_fill is None


def test_fill_price_is_limit_T_not_the_deeper_print():
    """Resting bid at T is hit first at T; deeper prints are bids below us."""
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "SELL", 0.18)], [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    assert f.fill_price == pytest.approx(0.45)
    assert f.trigger_price == pytest.approx(0.18)


def test_arms_at_first_qualifying_sell_not_a_later_deeper_one():
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "SELL", 0.44), _t(1150, "SELL", 0.10)], [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    assert f.ts == 1100 and f.trigger_price == pytest.approx(0.44)


# ---------------------------------------------------------------------------
# LOOK-AHEAD SAFETY
# ---------------------------------------------------------------------------
def test_fill_path_signature_excludes_resolution():
    params = set(inspect.signature(TapeBacktester._fill_leg).parameters)
    assert "resolution_yes" not in params and "res_yes" not in params


def test_fills_identical_regardless_of_resolution():
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    yt, nt = [_t(1100, "SELL", 0.40)], [_t(1120, "SELL", 0.44, token="N")]
    r1 = bt.run_window(_tw(yt, nt, 1.0))
    r0 = bt.run_window(_tw(yt, nt, 0.0))
    assert (r1.yes_fill.ts, r1.yes_fill.fill_price) == (r0.yes_fill.ts, r0.yes_fill.fill_price)
    assert (r1.no_fill.ts, r1.no_fill.fill_price) == (r0.no_fill.ts, r0.no_fill.fill_price)


def test_settlement_tail_excluded_by_default():
    """A SELL <= T after window close (positions unwinding to 0/1) must not fill."""
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1305, "SELL", 0.01)], [], resolution_yes=0.0)  # t > close_ts=1300
    assert bt.run_window(w).yes_fill is None


def test_convergence_guard_drops_final_seconds():
    bt = TapeBacktester(TapeConfig(threshold=0.45, convergence_guard_s=5.0))
    w = _tw([_t(1297, "SELL", 0.02)], [], resolution_yes=0.0)  # within last 5s
    assert bt.run_window(w).yes_fill is None


# ---------------------------------------------------------------------------
# STATE INTEGRITY ($0 vs $1) — per-leg size aware
# ---------------------------------------------------------------------------
def test_both_legs_lock_arb_when_cost_below_guaranteed_payout():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=1.0))
    w = _tw([_t(1100, "SELL", 0.40)], [_t(1120, "SELL", 0.43, token="N")], resolution_yes=1.0)
    r = bt.run_window(w)
    assert r.n_legs == 2 and r.outcome == ARB_LOCKED
    assert r.cost == pytest.approx(0.45 + 0.45)      # both fill at limit T
    assert r.payout == pytest.approx(1.0)            # one side pays $1
    assert r.pnl == pytest.approx(1.0 - 0.90)


def test_unhedged_loss_buys_the_loser_cheap():
    """The adversely-selected case: only the losing side dipped to T."""
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=1.0))
    w = _tw([_t(1100, "SELL", 0.20)], [], resolution_yes=0.0)  # YES filled, Up LOST
    r = bt.run_window(w)
    assert r.n_legs == 1 and r.outcome == UNHEDGED_LOSS
    assert r.payout == pytest.approx(0.0) and r.pnl == pytest.approx(-0.45)


def test_unhedged_win():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=1.0))
    w = _tw([], [_t(1100, "SELL", 0.30, token="N")], resolution_yes=0.0)  # NO filled, Down won
    r = bt.run_window(w)
    assert r.n_legs == 1 and r.outcome == UNHEDGED_WIN
    assert r.payout == pytest.approx(1.0) and r.pnl == pytest.approx(0.55)


def test_no_fill_window_is_flat():
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1100, "BUY", 0.10)], [_t(1110, "SELL", 0.80, token="N")], resolution_yes=1.0)
    r = bt.run_window(w)
    assert r.n_legs == 0 and r.outcome == NO_FILL
    assert r.cost == 0.0 and r.payout == 0.0 and r.pnl == 0.0


# ---------------------------------------------------------------------------
# SIZE / PARTICIPATION
# ---------------------------------------------------------------------------
def test_partial_fill_when_print_size_thin_under_participation_cap():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=10.0, participation=0.25))
    # one SELL print of size 8 -> capture 0.25*8 = 2.0; no more prints -> partial
    w = _tw([_t(1100, "SELL", 0.40, size=8.0)], [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    assert f.size == pytest.approx(2.0)
    assert f.cost == pytest.approx(0.45 * 2.0)


def test_participation_accumulates_across_qualifying_sells():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=3.0, participation=0.5))
    w = _tw([_t(1100, "SELL", 0.40, size=2.0), _t(1110, "SELL", 0.30, size=10.0)],
            [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    assert f.size == pytest.approx(3.0)   # 0.5*2=1.0 then capped to remaining 2.0
    assert f.ts == 1100                   # armed at first qualifying SELL


def test_fee_applied_and_never_negative():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=5.0, fee_bps=200))
    w = _tw([_t(1100, "SELL", 0.40)], [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    expected_fee = (200 / 1e4) * 5.0 * min(0.45, 0.55)
    assert f.fee == pytest.approx(expected_fee)
    assert f.cost == pytest.approx(0.45 * 5.0 + expected_fee)


def test_pnl_identity_holds():
    bt = TapeBacktester(TapeConfig(threshold=0.45, size=1.0, fee_bps=50))
    w = _tw([_t(1100, "SELL", 0.40)], [_t(1120, "SELL", 0.42, token="N")], resolution_yes=0.0)
    r = bt.run_window(w)
    assert r.cost == pytest.approx((r.yes_fill.cost) + (r.no_fill.cost))
    assert r.pnl == pytest.approx(r.payout - r.cost)


def test_unsorted_prints_are_handled_causally():
    """Defensive: even if prints arrive out of order, fill arms at earliest qualifying SELL."""
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    w = _tw([_t(1150, "SELL", 0.30), _t(1100, "SELL", 0.44)], [], resolution_yes=1.0)
    f = bt.run_window(w).yes_fill
    assert f.ts == 1100
