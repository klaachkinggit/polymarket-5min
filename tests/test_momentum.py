"""Cross-window momentum / autocorrelation strategy."""
import pytest

from polymarket_arb.momentum import (MomentumBacktester, MomentumConfig,
                                      autocorr_stats, momentum_summary)
from polymarket_arb.trades import Trade, TradeWindow


def _w(open_ts, res, yes_first=0.50, no_first=0.50, asset="BTC"):
    ts = open_ts + 1
    return TradeWindow(slug=f"btc-updown-5m-{int(open_ts)}", asset=asset,
                       open_ts=float(open_ts), close_ts=float(open_ts + 300),
                       yes_token="Y", no_token="N",
                       yes_trades=[Trade(ts, "Y", "SELL", yes_first, 100.0, "0x", 0)],
                       no_trades=[Trade(ts, "N", "SELL", no_first, 100.0, "0x", 1)],
                       resolution_yes=res)


def test_autocorr_all_up_is_full_persistence():
    wins = [_w(i * 300, 1.0) for i in range(5)]
    s = autocorr_stats(wins)
    assert s["n_pairs"] == 4
    assert s["repeat_rate"] == pytest.approx(1.0)
    assert s["p_up_after_up"] == pytest.approx(1.0)


def test_autocorr_alternating_is_mean_reversion():
    wins = [_w(i * 300, float(i % 2)) for i in range(6)]
    s = autocorr_stats(wins)
    assert s["repeat_rate"] == pytest.approx(0.0)       # never repeats
    assert s["lag1_autocorr"] < 0


def test_non_consecutive_windows_are_not_paired():
    wins = [_w(0, 1.0), _w(300, 1.0), _w(1200, 1.0)]    # gap after the 2nd
    assert autocorr_stats(wins)["n_pairs"] == 1


def test_momentum_bets_same_direction_as_prev_and_prices_at_open():
    # prev Up -> bet Up; YES opens at 0.50; this window resolves Up -> win
    wins = [_w(0, 1.0), _w(300, 1.0, yes_first=0.50)]
    r = MomentumBacktester(MomentumConfig(direction="momentum")).run(wins)
    assert len(r) == 1
    assert r[0].bet_up is True and r[0].entry_price == pytest.approx(0.50)
    assert r[0].correct is True and r[0].pnl == pytest.approx(0.50)


def test_reversal_bets_opposite():
    wins = [_w(0, 1.0), _w(300, 0.0, no_first=0.40)]    # prev Up -> reversal bets Down
    r = MomentumBacktester(MomentumConfig(direction="reversal")).run(wins)
    assert r[0].bet_up is False and r[0].entry_price == pytest.approx(0.40)
    assert r[0].correct is True and r[0].pnl == pytest.approx(0.60)


def test_signal_uses_only_previous_window():
    # the bet on window 2 depends on window 1's outcome, not window 2's
    up = MomentumBacktester(MomentumConfig()).run([_w(0, 1.0), _w(300, 0.0)])
    dn = MomentumBacktester(MomentumConfig()).run([_w(0, 0.0), _w(300, 0.0)])
    assert up[0].bet_up is True and dn[0].bet_up is False   # flips with prev only


def test_summary_aggregates_winrate_and_pnl():
    wins = [_w(0, 1.0), _w(300, 1.0), _w(600, 0.0)]   # bet Up,Up; win then lose
    res = MomentumBacktester(MomentumConfig()).run(wins)
    s = momentum_summary(res)
    assert s["n_bets"] == 2
    assert s["win_rate"] == pytest.approx(0.5)
