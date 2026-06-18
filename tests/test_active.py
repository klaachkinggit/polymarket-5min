"""Active-exit strategy: abandon an unhedged leg after a timeout.

Look-ahead safety: fill/exit decisions use only trades at/before the decision
time; resolution is read only for positions held to settlement.
"""
import pytest

from polymarket_arb.active import (EXIT_LOSS, EXIT_WIN, ActiveConfig,
                                   ActiveExitBacktester)
from polymarket_arb.engine import (ARB_LOCKED, NO_FILL, UNHEDGED_LOSS,
                                    UNHEDGED_WIN)
from polymarket_arb.trades import Trade, TradeWindow


def _tw(yes, no, res, open_ts=0.0, close_ts=300.0):
    return TradeWindow(slug="btc-updown-5m-0", asset="BTC", open_ts=open_ts,
                       close_ts=close_ts, yes_token="Y", no_token="N",
                       yes_trades=yes, no_trades=no, resolution_yes=res)


def _t(ts, price, side="SELL", token="Y"):
    return Trade(ts=float(ts), token=token, side=side, price=price, size=100.0,
                 tx="0x", outcome_index=0)


def test_lock_when_both_fill_within_timeout():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    w = _tw([_t(10, 0.40)], [_t(20, 0.42, token="N")], res=1.0)
    r = bt.run_window(w)
    assert r.outcome == ARB_LOCKED
    assert r.pnl == pytest.approx(1.0 - 2 * 0.49)


def test_gap_beyond_timeout_exits_first_leg_not_lock():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    # YES fills @10; NO would fill @100 (>10+30) -> we exit YES @40, cancel NO
    w = _tw([_t(10, 0.40), _t(40, 0.30)], [_t(100, 0.42, token="N")], res=1.0)
    r = bt.run_window(w)
    assert r.outcome in (EXIT_WIN, EXIT_LOSS)
    assert r.pnl == pytest.approx(0.30 - 0.49)        # sold @0.30, bought @T


def test_only_loser_fills_exit_caps_loss():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    # only YES fills (it is the loser, res=Down); exit @40 at 0.35 -> capped loss
    w = _tw([_t(10, 0.45), _t(40, 0.35)], [], res=0.0)
    r = bt.run_window(w)
    assert r.outcome == EXIT_LOSS
    assert r.pnl == pytest.approx(0.35 - 0.49)
    assert r.pnl > -0.49                              # better than holding to $0


def test_exit_win_when_price_above_T_at_exit():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    w = _tw([_t(10, 0.45), _t(40, 0.55)], [], res=1.0)
    r = bt.run_window(w)
    assert r.outcome == EXIT_WIN
    assert r.pnl == pytest.approx(0.55 - 0.49)


def test_exit_beyond_window_holds_to_settlement():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    # YES fills @290; 290+30=320 >= close 300 -> cannot exit -> settle; Down won
    w = _tw([_t(290, 0.45)], [], res=0.0)
    r = bt.run_window(w)
    assert r.outcome == UNHEDGED_LOSS
    assert r.pnl == pytest.approx(0.0 - 0.49)


def test_lookahead_exit_price_ignores_post_exit_recovery():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30))
    # exit @40 uses the 0.30 print at t=20, NOT the 0.90 recovery at t=60
    w = _tw([_t(10, 0.45), _t(20, 0.30), _t(60, 0.90)], [], res=1.0)
    r = bt.run_window(w)
    assert r.pnl == pytest.approx(0.30 - 0.49)


def test_exit_half_spread_haircut_applied():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49, hold_timeout_s=30,
                                           exit_half_spread=0.02))
    w = _tw([_t(10, 0.45), _t(40, 0.40)], [], res=1.0)
    r = bt.run_window(w)
    assert r.pnl == pytest.approx((0.40 - 0.02) - 0.49)


def test_no_fill_is_flat():
    bt = ActiveExitBacktester(ActiveConfig(threshold=0.49))
    w = _tw([_t(10, 0.60)], [_t(20, 0.80, token="N")], res=1.0)
    r = bt.run_window(w)
    assert r.outcome == NO_FILL and r.pnl == 0.0


def test_exit_pnl_independent_of_resolution():
    cfg = ActiveConfig(threshold=0.49, hold_timeout_s=30)
    yes, no = [_t(10, 0.45), _t(40, 0.35)], []
    r1 = ActiveExitBacktester(cfg).run_window(_tw(yes, no, 1.0))
    r0 = ActiveExitBacktester(cfg).run_window(_tw(yes, no, 0.0))
    assert r1.pnl == pytest.approx(r0.pnl)            # an exited leg never reads resolution


def test_lock_pnl_independent_of_winner():
    cfg = ActiveConfig(threshold=0.49, hold_timeout_s=30)
    yes, no = [_t(10, 0.40)], [_t(15, 0.42, token="N")]
    for res in (1.0, 0.0):
        r = ActiveExitBacktester(cfg).run_window(_tw(yes, no, res))
        assert r.outcome == ARB_LOCKED and r.pnl == pytest.approx(1.0 - 0.98)
