"""Stochastic-process EDA functions (pure; no network)."""
import math

import pytest

from polymarket_arb.dynamics import (arcsine_cdf, brier_score, calibration_curve,
                                     crossing_count, digital_snr, fraction_time_above,
                                     moments, opening_mid_prob, resample_last,
                                     token_mid_path, variance_ratio, yes_no_sum_stats)
from polymarket_arb.trades import Trade, TradeWindow


def _win(yes, no, open_ts=0, res=1.0):
    """yes/no: list of (offset_s, side, price)."""
    return TradeWindow(slug="btc-updown-5m-0", asset="BTC", open_ts=float(open_ts),
                       close_ts=float(open_ts + 300), yes_token="Y", no_token="N",
                       yes_trades=[Trade(open_ts + o, "Y", s, p, 1.0, "0x", 0) for o, s, p in yes],
                       no_trades=[Trade(open_ts + o, "N", s, p, 1.0, "0x", 1) for o, s, p in no],
                       resolution_yes=res)


# ---- variance ratio (the audited fix) --------------------------------------
def test_variance_ratio_mean_reverting_series_below_one():
    rets = [1.0, -1.0] * 50                      # perfectly alternating -> reversion
    vr = variance_ratio(rets, 2)
    assert vr["vr"] < 1.0 and vr["z"] < 0 and vr["z_star"] < 0


def test_variance_ratio_trending_series_above_one():
    rets = ([1.0] * 5 + [-1.0] * 5) * 10          # persistent blocks -> trending
    vr = variance_ratio(rets, 2)
    assert vr["vr"] > 1.0 and vr["z"] > 0


def test_variance_ratio_reports_both_z_and_zstar_finite():
    rets = [math.sin(i) for i in range(200)]
    vr = variance_ratio(rets, 4)
    assert vr["z"] == vr["z"] and vr["z_star"] == vr["z_star"]   # not nan


def test_variance_ratio_guards_small_samples():
    assert variance_ratio([0.1, 0.2], 5)["vr"] != variance_ratio([0.1, 0.2], 5)["vr"]  # nan


# ---- digital SNR -----------------------------------------------------------
def test_digital_snr_zero_drift_is_half():
    d = digital_snr(0.0, 0.001, 5)
    assert d["snr"] == 0.0 and d["fair_up"] == pytest.approx(0.5)


def test_digital_snr_positive_drift_tilts_up_but_small():
    d = digital_snr(1e-5, 0.0007, 5)
    assert 0.5 < d["fair_up"] < 0.55 and abs(d["snr"]) < 0.1


# ---- token mid construction & path stats -----------------------------------
def test_token_mid_is_yes_no_synthesis():
    w = _win(yes=[(1, "BUY", 0.60)], no=[(2, "SELL", 0.50)])
    mp = token_mid_path(w)
    assert mp[-1][1] == pytest.approx((0.60 + (1 - 0.50)) / 2)   # 0.55


def test_opening_mid_prob_averages_early_window():
    w = _win(yes=[(1, "BUY", 0.60), (5, "BUY", 0.62)], no=[(2, "SELL", 0.40)])
    p = opening_mid_prob(w, within_s=30)
    assert p is not None and 0.5 < p < 0.8


def test_fraction_time_above_is_time_weighted():
    path = [(0.0, 0.6), (10.0, 0.4), (20.0, 0.4)]   # above for [0,10), below for [10,20)
    assert fraction_time_above(path, 0.5) == pytest.approx(0.5)


def test_arcsine_cdf_known_points():
    assert arcsine_cdf(0.5) == pytest.approx(0.5)
    assert arcsine_cdf(0.0) == 0.0 and arcsine_cdf(1.0) == pytest.approx(1.0)


def test_crossing_count_counts_level_crossings():
    assert crossing_count([0.4, 0.6, 0.4, 0.6], 0.5) == 3
    assert crossing_count([0.4, 0.45, 0.49], 0.5) == 0


def test_resample_last_takes_last_per_bucket():
    path = [(0.0, 0.5), (3.0, 0.52), (10.0, 0.6), (12.0, 0.61)]
    assert resample_last(path, 0.0, 300.0, dt=10.0) == [0.52, 0.61]


# ---- calibration & brier ---------------------------------------------------
def test_brier_perfect_and_worst():
    assert brier_score([(1.0, 1), (0.0, 0)]) == pytest.approx(0.0)
    assert brier_score([(0.5, 1), (0.5, 0)]) == pytest.approx(0.25)


def test_calibration_curve_bins_and_has_wilson_ci():
    pairs = [(0.05, 0)] * 20 + [(0.95, 1)] * 20
    rows = calibration_curve(pairs, nbins=10)
    assert {r["bin"] for r in rows} == {0, 9}
    for r in rows:
        assert r["lo"] <= r["freq"] <= r["hi"]


# ---- no-arb sum ------------------------------------------------------------
def test_yes_no_sum_near_one():
    w = _win(yes=[(1, "BUY", 0.55)], no=[(2, "BUY", 0.46)])
    s = yes_no_sum_stats(w)
    assert s["mean_sum"] == pytest.approx(1.01) and s["n"] == 1


# ---- moments ---------------------------------------------------------------
def test_moments_symmetric_has_zero_skew():
    m = moments([-2.0, -1.0, 0.0, 1.0, 2.0])
    assert m["skew"] == pytest.approx(0.0, abs=1e-9)


def test_statsmodels_wrappers_accept_plain_lists():
    from polymarket_arb.dynamics import arch_lm, ljung_box
    xs = [math.sin(i) * 0.01 + (0.005 if i % 7 == 0 else 0.0) for i in range(300)]
    assert 0.0 <= ljung_box(xs, 10)["lb_pvalue"] <= 1.0
    assert 0.0 <= arch_lm(xs, 10)["lm_pvalue"] <= 1.0
