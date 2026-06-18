"""Verification of the three correctness constraints.

  1. No look-ahead bias   — fills depend only on the past tick path.
  2. Slippage / fees       — explicit, additive, correctly applied.
  3. State integrity       — capital accounted exactly for $0 vs $1 settlement.
"""
import inspect
import math

import pytest

from polymarket_arb.data import MarketWindow, Tick
from polymarket_arb.engine import (ARB_LOCKED, HEDGED_NEGEDGE, NO_FILL,
                                    UNHEDGED_LOSS, UNHEDGED_WIN, ArbBacktester,
                                    ExecConfig, Fill)


def _win(ticks, resolution_yes, slug="t"):
    return MarketWindow(slug=slug, asset="BTC", start_ts=0.0, end_ts=300.0,
                        yes_token="Y", no_token="N", ticks=ticks,
                        resolution_yes=resolution_yes)


def _flat(yes_mids, no_mids=None):
    if no_mids is None:
        no_mids = [1.0 - y for y in yes_mids]
    return [Tick(ts=float(i), yes_mid=y, no_mid=n)
            for i, (y, n) in enumerate(zip(yes_mids, no_mids))]


# ----------------------------------------------------------------------------
# 1. LOOK-AHEAD BIAS
# ----------------------------------------------------------------------------
def test_simulate_signature_excludes_resolution():
    """Structural guarantee: simulate() cannot even see the outcome."""
    params = set(inspect.signature(ArbBacktester.simulate).parameters)
    assert "resolution_yes" not in params
    assert params == {"self", "ticks"}


def test_fills_identical_regardless_of_resolution():
    """Same path -> same fills whether Up or Down ultimately wins."""
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    ticks = _flat([0.50, 0.44, 0.55, 0.40, 0.60])  # YES dips; NO dips at idx 2/4
    y1, n1, _ = bt.simulate(_win(ticks, 1.0).ticks)
    y0, n0, _ = bt.simulate(_win(ticks, 0.0).ticks)
    assert (y1, n1) == (y0, n0)


def test_fill_acts_at_first_dip_not_best_later_price():
    """Engine buys the moment ask<=threshold; it must not wait for a deeper dip."""
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    ticks = _flat([0.44, 0.30, 0.99])  # first crossing is 0.44, deeper later
    yf, _, _ = bt.simulate(ticks)
    assert yf is not None and yf.fill_price == pytest.approx(0.44)
    assert yf.ts == 0.0  # acted on the first qualifying tick


def test_fill_can_happen_on_last_tick():
    """A dip only on the final tick still fills — no future confirmation needed."""
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    yf, _, _ = bt.simulate(_flat([0.99, 0.99, 0.40]))
    assert yf is not None and yf.ts == 2.0


# ----------------------------------------------------------------------------
# 2. SLIPPAGE / FEES
# ----------------------------------------------------------------------------
def test_threshold_compares_against_ask_not_mid():
    """mid below threshold but ask above => no fill."""
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.02))
    # mid 0.44 -> ask 0.46 > 0.45 => no fill
    yf, _, _ = bt.simulate(_flat([0.44]))
    assert yf is None
    # mid 0.42 -> ask 0.44 <= 0.45 => fill at 0.44
    yf, _, _ = bt.simulate(_flat([0.42]))
    assert yf is not None and yf.ask == pytest.approx(0.44)


def test_slippage_adds_to_fill_price_and_cost():
    base = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0, slippage=0.0, size=10))
    slip = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0, slippage=0.03, size=10))
    yf0, _, _ = base.simulate(_flat([0.40]))
    yf1, _, _ = slip.simulate(_flat([0.40]))
    assert yf0.fill_price == pytest.approx(0.40)
    assert yf1.fill_price == pytest.approx(0.43)
    assert yf1.cost - yf0.cost == pytest.approx(0.03 * 10)  # slippage * size


def test_fee_is_polymarket_symmetric_form():
    cfg = ExecConfig(threshold=0.45, half_spread=0.0, fee_bps=200, size=5)  # 2%
    yf, _, _ = ArbBacktester(cfg).simulate(_flat([0.40]))
    expected_fee = (200 / 1e4) * 5 * min(0.40, 0.60)
    assert yf.fee == pytest.approx(expected_fee)
    assert yf.cost == pytest.approx(0.40 * 5 + expected_fee)


def test_fee_never_negative_under_pathological_fill():
    """fill_price > 1 (absurd slippage) must not produce a fee rebate."""
    cfg = ExecConfig(threshold=0.45, half_spread=0.0, slippage=0.7, fee_bps=500, size=1)
    yf, _, _ = ArbBacktester(cfg).simulate(_flat([0.40]))
    assert yf.fill_price == pytest.approx(1.10)
    assert yf.fee == 0.0  # clamped, not negative


def test_zero_friction_cost_equals_notional():
    cfg = ExecConfig(threshold=0.45, half_spread=0.0, slippage=0.0, fee_bps=0.0, size=3)
    yf, _, _ = ArbBacktester(cfg).simulate(_flat([0.40]))
    assert yf.cost == pytest.approx(0.40 * 3)


# ----------------------------------------------------------------------------
# 3. STATE INTEGRITY ($0 vs $1)
# ----------------------------------------------------------------------------
def test_hedged_locks_profit_independent_of_winner():
    """Both legs filled cheap: payout is exactly `size` whichever side wins."""
    bt = ArbBacktester(ExecConfig(threshold=0.46, half_spread=0.0))
    ticks = _flat([0.40, 0.55], [0.60, 0.45])  # YES fills @0.40, NO fills @0.45
    for res in (1.0, 0.0):
        r = bt.run_window(_win(ticks, res))
        assert r.n_legs == 2
        assert r.payout == pytest.approx(1.0)            # one leg pays $1
        assert r.cost == pytest.approx(0.40 + 0.45)
        assert r.pnl == pytest.approx(1.0 - 0.85)
        assert r.outcome == ARB_LOCKED


def test_hedged_negedge_when_overpaid():
    """Both legs but combined cost >= notional -> hedged, no edge, pnl<=0."""
    bt = ArbBacktester(ExecConfig(threshold=0.60, half_spread=0.0))
    ticks = _flat([0.55, 0.50], [0.50, 0.55])  # 0.55 + 0.50 = 1.05 > 1
    r = bt.run_window(_win(ticks, 1.0))
    assert r.n_legs == 2
    assert r.outcome == HEDGED_NEGEDGE
    assert r.payout == pytest.approx(1.0)
    assert r.pnl == pytest.approx(1.0 - 1.05)


def test_unhedged_yes_win_and_loss():
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    ticks = _flat([0.40, 0.52])  # YES dips to 0.40; NO=[0.60,0.48] never <=0.45
    win = bt.run_window(_win(ticks, 1.0))   # Up wins
    assert win.n_legs == 1 and win.outcome == UNHEDGED_WIN
    assert win.payout == pytest.approx(1.0) and win.pnl == pytest.approx(0.60)
    loss = bt.run_window(_win(ticks, 0.0))  # Up loses
    assert loss.outcome == UNHEDGED_LOSS
    assert loss.payout == pytest.approx(0.0) and loss.pnl == pytest.approx(-0.40)


def test_unhedged_no_win_and_loss():
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    ticks = _flat([0.99, 0.99], [0.40, 0.40])  # only NO fills @0.40
    win = bt.run_window(_win(ticks, 0.0))   # Down wins
    assert win.n_legs == 1 and win.outcome == UNHEDGED_WIN
    assert win.payout == pytest.approx(1.0) and win.pnl == pytest.approx(0.60)
    loss = bt.run_window(_win(ticks, 1.0))  # Down loses
    assert loss.outcome == UNHEDGED_LOSS
    assert loss.pnl == pytest.approx(-0.40)


def test_no_fill_is_flat():
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    # both legs hover just above threshold the whole window: YES in [.52,.54] -> NO in [.46,.48]
    r = bt.run_window(_win(_flat([0.53, 0.52, 0.54]), 1.0))
    assert r.n_legs == 0 and r.outcome == NO_FILL
    assert r.cost == 0.0 and r.payout == 0.0 and r.pnl == 0.0


def test_capital_conservation_across_run():
    """Final equity == starting capital + sum of per-window pnl."""
    from polymarket_arb.metrics import equity_curve
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0))
    wins = [
        _win(_flat([0.40, 0.55], [0.60, 0.45]), 1.0, "a"),  # arb
        _win(_flat([0.40, 0.99]), 0.0, "b"),                # unhedged loss
        _win(_flat([0.99, 0.99], [0.40, 0.40]), 0.0, "c"),  # unhedged win
    ]
    results = bt.run(wins)
    _, equity = equity_curve(results, starting_capital=100.0)
    assert equity[-1] == pytest.approx(100.0 + sum(r.pnl for r in results))


def test_property_pnl_identity_random_configs():
    """Randomised: for every fill, cost == fill_price*size + fee, and per window
    pnl == payout - sum(leg costs). The core accounting identity must never drift."""
    import numpy as np
    from polymarket_arb.synth import generate_window
    rng = np.random.RandomState(7)
    for _ in range(60):
        cfg = ExecConfig(
            threshold=float(rng.uniform(0.35, 0.49)),
            half_spread=float(rng.uniform(0.0, 0.02)),
            slippage=float(rng.uniform(0.0, 0.05)),
            fee_bps=float(rng.choice([0, 50, 200])),
            size=float(rng.choice([1, 3, 10])),
        )
        bt = ArbBacktester(cfg)
        w = generate_window(seed=int(rng.randint(0, 10_000)))
        r = bt.run_window(w)
        leg_cost = 0.0
        for f in (r.yes_fill, r.no_fill):
            if f is not None:
                assert f.fill_price == pytest.approx(f.ask + cfg.slippage)
                assert f.fee >= 0.0
                assert f.cost == pytest.approx(f.fill_price * cfg.size + f.fee)
                leg_cost += f.cost
        assert r.cost == pytest.approx(leg_cost)
        if not math.isnan(r.pnl):
            assert r.pnl == pytest.approx(r.payout - r.cost)


def test_settlement_payout_is_zero_or_one_per_leg():
    """Every filled leg contributes exactly 0*size or 1*size at settlement."""
    bt = ArbBacktester(ExecConfig(threshold=0.45, half_spread=0.0, size=7))
    r = bt.run_window(_win(_flat([0.40, 0.52]), 1.0))  # only YES filled, Up wins
    assert r.n_legs == 1
    assert r.payout in (pytest.approx(0.0), pytest.approx(7.0))
