"""Cross-window momentum / autocorrelation strategy."""
import pytest

from polymarket_arb.momentum import (MomentumBacktester, MomentumConfig,
                                      _opening_quote, autocorr_stats,
                                      momentum_summary)
from polymarket_arb.trades import Trade, TradeWindow


def _w(open_ts, res, yes_first=0.50, no_first=0.50, asset="BTC", side="BUY",
       truncated=False):
    ts = open_ts + 1
    return TradeWindow(slug=f"btc-updown-5m-{int(open_ts)}", asset=asset,
                       open_ts=float(open_ts), close_ts=float(open_ts + 300),
                       yes_token="Y", no_token="N",
                       yes_trades=[Trade(ts, "Y", side, yes_first, 100.0, "0x", 0)],
                       no_trades=[Trade(ts, "N", side, no_first, 100.0, "0x", 1)],
                       resolution_yes=res, truncated=truncated)


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
    # prev Up -> bet Up; YES opens (BUY/ask-lift) at 0.50; this window resolves Up -> win
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


# ---- audit fixes -----------------------------------------------------------
def test_realistic_entry_skips_window_with_only_sell_prints():
    # default entry_side="buy": a SELL-only window offers no ask-lift -> no entry
    wins = [_w(0, 1.0), _w(300, 1.0, side="SELL")]
    bt = MomentumBacktester(MomentumConfig(direction="momentum"))
    assert bt.run(wins) == []
    assert bt.n_skipped_nofill == 1


def test_entry_side_any_restores_earliest_print_entry():
    wins = [_w(0, 1.0), _w(300, 1.0, side="SELL", yes_first=0.50)]
    r = MomentumBacktester(MomentumConfig(direction="momentum", entry_side="any")).run(wins)
    assert len(r) == 1 and r[0].entry_price == pytest.approx(0.50)


def test_buy_entry_picks_earliest_buy_not_an_earlier_sell():
    # an earlier SELL@0.30 then a BUY@0.55: realistic entry must be the BUY (the ask)
    w_prev = _w(0, 1.0)
    cur = TradeWindow(slug="btc-updown-5m-300", asset="BTC", open_ts=300.0,
                      close_ts=600.0, yes_token="Y", no_token="N",
                      yes_trades=[Trade(301, "Y", "SELL", 0.30, 50, "0x", 0),
                                  Trade(302, "Y", "BUY", 0.55, 50, "0x", 0)],
                      no_trades=[Trade(301, "N", "BUY", 0.46, 50, "0x", 1)],
                      resolution_yes=1.0)
    assert _opening_quote(cur, bet_up=True, taker_side="BUY") == pytest.approx(0.55)
    r = MomentumBacktester(MomentumConfig(direction="momentum")).run([w_prev, cur])
    assert r[0].entry_price == pytest.approx(0.55)


def test_exclude_truncated_skips_window_by_default():
    wins = [_w(0, 1.0), _w(300, 1.0, truncated=True)]
    bt = MomentumBacktester(MomentumConfig(direction="momentum"))
    assert bt.run(wins) == []
    assert bt.n_skipped_truncated == 1
    # opt back in
    bt2 = MomentumBacktester(MomentumConfig(direction="momentum", exclude_truncated=False))
    assert len(bt2.run(wins)) == 1


def test_require_both_quotes_skips_one_sided_window():
    # cur has a YES BUY but no NO BUY -> with require_both_quotes the pair is dropped
    cur = TradeWindow(slug="btc-updown-5m-300", asset="BTC", open_ts=300.0,
                      close_ts=600.0, yes_token="Y", no_token="N",
                      yes_trades=[Trade(301, "Y", "BUY", 0.50, 50, "0x", 0)],
                      no_trades=[Trade(301, "N", "SELL", 0.50, 50, "0x", 1)],
                      resolution_yes=1.0)
    wins = [_w(0, 1.0), cur]   # prev Up -> momentum bets Up (YES), which HAS a quote
    bt = MomentumBacktester(MomentumConfig(direction="momentum", require_both_quotes=True))
    assert bt.run(wins) == []
    assert bt.n_skipped_oneside == 1
