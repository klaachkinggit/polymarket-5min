"""Regime analysis: tercile labelling, per-regime aggregation (no network)."""
import pytest

from polymarket_arb.regimes import (label_terciles, regime_performance,
                                     strategy_pnls)
from polymarket_arb.trades import Trade, TradeWindow


def test_label_terciles_splits_low_med_high():
    rows = [{"prev_rvol": v} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9]]
    q1, q2 = label_terciles(rows)
    assert (q1, q2) == (4, 7)
    # low: v<=4, high: v>7, med otherwise
    assert [r["regime"] for r in rows] == \
        ["low", "low", "low", "low", "med", "med", "med", "high", "high"]


def test_regime_performance_groups_and_means_with_clustered_t():
    rows = [
        {"regime": "low", "cur_open_ts": 0.0, "reversal": 1.0, "momentum": -1.0, "arb": -0.1},
        {"regime": "low", "cur_open_ts": 300.0, "reversal": 3.0, "momentum": -3.0, "arb": -0.1},
        {"regime": "high", "cur_open_ts": 0.0, "reversal": -1.0, "momentum": 1.0, "arb": -0.2},
    ]
    d = {(p["strategy"], p["regime"]): p for p in regime_performance(rows)}
    assert d[("reversal", "low")]["n"] == 2
    assert d[("reversal", "low")]["mean_pnl"] == pytest.approx(2.0)
    assert d[("reversal", "high")]["n"] == 1            # single cluster -> t is nan, still reported


def test_regime_performance_skips_missing_strategy_pnl():
    rows = [{"regime": "med", "cur_open_ts": 0.0, "reversal": None, "momentum": 0.5, "arb": None},
            {"regime": "med", "cur_open_ts": 300.0, "reversal": 2.0, "momentum": 0.5, "arb": None}]
    d = {(p["strategy"], p["regime"]): p for p in regime_performance(rows)}
    assert d[("reversal", "med")]["n"] == 1             # only the non-None reversal counted
    assert d[("momentum", "med")]["n"] == 2
    assert ("arb", "med") not in d                      # all-None -> not reported


def _w(open_ts, res, asset="BTC", first=0.50, side="BUY"):
    ts = open_ts + 1
    return TradeWindow(slug=f"{asset.lower()}-updown-5m-{int(open_ts)}", asset=asset,
                       open_ts=float(open_ts), close_ts=float(open_ts + 300),
                       yes_token="Y", no_token="N",
                       yes_trades=[Trade(ts, "Y", side, first, 100.0, "0x", 0)],
                       no_trades=[Trade(ts, "N", side, 1 - first, 100.0, "0x", 1)],
                       resolution_yes=res)


def test_strategy_pnls_keyed_by_asset_and_start_ts():
    wins = [_w(0, 1.0), _w(300, 1.0), _w(600, 0.0)]
    pnls = strategy_pnls(wins)
    assert set(pnls) == {"reversal", "momentum", "arb"}
    # arb runs on every window; reversal/momentum only on consecutive pairs (cur)
    assert ("btc", 300.0) in pnls["arb"]
    assert all(k[0] == "btc" for k in pnls["reversal"])
