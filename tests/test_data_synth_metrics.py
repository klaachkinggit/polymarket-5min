"""Data parsing, synthetic generator invariants, and metric sanity."""
import math

import pytest

from polymarket_arb.data import _merge_histories, _parse_resolution
from polymarket_arb.engine import ArbBacktester, ExecConfig
from polymarket_arb.metrics import max_drawdown, summary
from polymarket_arb.synth import generate_dataset, generate_window


def test_parse_resolution_up_down_unresolved():
    assert _parse_resolution({"outcomePrices": '["1", "0"]'}) == 1.0  # Up won
    assert _parse_resolution({"outcomePrices": '["0", "1"]'}) == 0.0  # Down won
    assert _parse_resolution({"outcomePrices": '["0.5", "0.5"]'}) is None  # live
    assert _parse_resolution({}) is None


def test_merge_histories_forward_fills_and_clips():
    yh = {10.0: 0.5, 30.0: 0.6}
    nh = {10.0: 0.5, 20.0: 0.4}
    ticks = _merge_histories(yh, nh, start=10.0, end=30.0)
    assert [t.ts for t in ticks] == [10.0, 20.0, 30.0]
    assert ticks[1].yes_mid == 0.5  # forward-filled from t=10
    assert ticks[2].no_mid == 0.4   # forward-filled from t=20


def test_synth_resolution_matches_terminal_price():
    for seed in range(50):
        w = generate_window(seed=seed)
        assert w.resolution_yes in (0.0, 1.0)
        terminal_yes = w.ticks[-1].yes_mid
        assert terminal_yes == pytest.approx(w.resolution_yes)
        # complementary prices
        for t in w.ticks:
            assert t.yes_mid + t.no_mid == pytest.approx(1.0)


def test_synth_produces_overshoot():
    """Across many windows the Up price should dip below 0.45 sometimes."""
    ds = generate_dataset(n=100, seed0=0)
    dips = sum(1 for w in ds if any(t.yes_mid <= 0.45 for t in w.ticks))
    assert dips > 20  # overshoot is common


def test_max_drawdown_known_sequence():
    assert max_drawdown([0, 5, 3, 8, 2, 6]) == 6  # peak 8 -> trough 2


def test_summary_rates_are_consistent():
    ds = generate_dataset(n=200, seed0=1, vol_window=0.012)
    bt = ArbBacktester(ExecConfig(threshold=0.45))
    s = summary(bt.run(ds))
    # the partition of windows must sum to 1
    total = (s["arb_lock_rate"] + s["hedged_negedge_rate"]
             + s["unhedged_win_rate"] + s["unhedged_loss_rate"] + s["no_fill_rate"])
    assert total == pytest.approx(1.0)
    assert 0.0 <= s["fill_rate"] <= 1.0
    assert s["n_windows"] == 200
