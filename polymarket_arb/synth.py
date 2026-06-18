"""High-fidelity synthetic 5-minute windows for engine validation / stress tests.

Public history is capped at 1-minute mids, so realistic intra-window overshoot
cannot be observed historically. Here we drive the binary Up price off a GBM
underlying via the Black-Scholes digital: price_up = Phi(d) with
d = ln(S_t/S0) / (sigma * sqrt(tau_remaining)). As tau -> 0 the price snaps to
0/1, and resolution is taken from the terminal underlying (no look-ahead: the
path is generated forward, then the final sign is read off).
"""
from __future__ import annotations

import math

import numpy as np

from .data import MarketWindow, Tick


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def generate_window(seed: int, asset: str = "BTC", n_ticks: int = 300,
                    vol_window: float = 0.012, drift: float = 0.0,
                    start_ts: float = 0.0, duration_s: float = 300.0,
                    half_spread: float = 0.01) -> MarketWindow:
    """One synthetic window with ~`n_ticks` sub-second quotes.

    `vol_window` is the total stdev of the underlying log-return over the whole
    5 minutes (~0.012 = 1.2% is typical for 5-min crypto and yields Up prices
    that oscillate around 0.5 and overshoot into the 0.35-0.65 band).
    """
    rng = np.random.RandomState(seed)
    dt = 1.0 / n_ticks
    step_vol = vol_window * math.sqrt(dt)
    shocks = rng.normal(drift * dt, step_vol, size=n_ticks)
    log_path = np.concatenate([[0.0], np.cumsum(shocks)])  # length n_ticks+1, starts at 0

    frac = np.arange(n_ticks + 1) / n_ticks            # 0 .. 1
    tau = np.clip(1.0 - frac, 1e-6, None)              # remaining fraction of window
    denom = vol_window * np.sqrt(tau)
    d = log_path / denom
    yes_mid = np.clip(_norm_cdf(d), 1e-4, 1.0 - 1e-4)
    yes_mid[-1] = 1.0 if log_path[-1] > 0 else 0.0     # settle exactly at expiry
    no_mid = 1.0 - yes_mid

    ts = start_ts + frac * duration_s
    ticks = [Tick(ts=float(ts[i]), yes_mid=float(yes_mid[i]), no_mid=float(no_mid[i]))
             for i in range(n_ticks + 1)]
    resolution_yes = 1.0 if log_path[-1] > 0 else 0.0
    return MarketWindow(
        slug=f"synth-{asset.lower()}-updown-5m-{seed}", asset=asset.upper(),
        start_ts=float(start_ts), end_ts=float(start_ts + duration_s),
        yes_token=f"synthYES{seed}", no_token=f"synthNO{seed}",
        ticks=ticks, resolution_yes=resolution_yes, spread_hint=half_spread * 2,
    )


def generate_dataset(n: int = 500, asset: str = "BTC", seed0: int = 0,
                     **kwargs) -> list[MarketWindow]:
    return [generate_window(seed=seed0 + i, asset=asset, **kwargs) for i in range(n)]
