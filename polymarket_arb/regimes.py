"""Regime analysis for the 5-minute Up/Down strategies.

Question (per request): do market REGIMES favor any strategy, and are regimes
PREDICTABLE so you could condition on them ex-ante?

Regime axis = the previous window's underlying realized volatility (terciles). It is
*ex-ante*: known at the current window's open (the prior window has already closed), so a
strategy could legitimately condition on it. Volatility clusters (ARCH p≈0 in dynamics.py),
so this regime is forecastable — `vol_persistence` quantifies that.

For each consecutive (prev, cur) pair within an asset we record the regime (from prev's
vol) and the per-window PnL of each strategy on `cur`: reversal, momentum (momentum.py,
realistic ask entry) and the passive double-dip arb (tape_engine.py at a fixed threshold).
Per-regime means use a cluster-robust t (clustered by wall-clock window). Spot covers 6
assets (HYPE is not on Binance); regimes use those.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .dynamics import SPOT_ASSETS, load_spot, window_spot_features
from .momentum import MomentumBacktester, MomentumConfig
from .reversal_analysis import clustered_tstat
from .tape_engine import TapeBacktester, TapeConfig
from .trades import WINDOW_SECONDS, TradeWindow

REGIMES = ("low", "med", "high")


def _by_asset_sorted(windows: list[TradeWindow]) -> dict[str, list[TradeWindow]]:
    by: dict[str, list[TradeWindow]] = defaultdict(list)
    for w in windows:
        if w.resolved:
            by[w.asset.lower()].append(w)
    for a in by:
        by[a].sort(key=lambda w: w.open_ts)
    return by


def strategy_pnls(windows: list[TradeWindow], arb_threshold: float = 0.49) -> dict:
    """Per-window PnL for each strategy, keyed by (asset, start_ts)."""
    rev = {(r.asset.lower(), r.start_ts): r.pnl
           for r in MomentumBacktester(MomentumConfig(direction="reversal")).run(windows)}
    mom = {(r.asset.lower(), r.start_ts): r.pnl
           for r in MomentumBacktester(MomentumConfig(direction="momentum")).run(windows)}
    arb = {(r.asset.lower(), r.start_ts): r.pnl
           for r in TapeBacktester(TapeConfig(threshold=arb_threshold)).run(windows)}
    return {"reversal": rev, "momentum": mom, "arb": arb}


def regime_rows(windows: list[TradeWindow], spot_dir: str = "data/spot",
                arb_threshold: float = 0.49) -> list[dict]:
    """One row per consecutive (prev, cur) pair: prev's realized vol + each strategy's
    PnL on cur. Vol (hence regime) is ex-ante — it comes from the already-closed prev."""
    spots = {a: load_spot(a, spot_dir) for a in SPOT_ASSETS}
    pnls = strategy_pnls(windows, arb_threshold)
    rows: list[dict] = []
    for a, ws in _by_asset_sorted(windows).items():
        if not spots.get(a):
            continue
        for prev, cur in zip(ws, ws[1:]):
            if abs(cur.open_ts - prev.open_ts - WINDOW_SECONDS) >= 1.0:
                continue
            pf = window_spot_features(prev, spots[a])
            if not pf:
                continue
            key = (a, cur.open_ts)
            rows.append({"asset": a, "cur_open_ts": cur.open_ts, "prev_rvol": pf["rvol"],
                         "reversal": pnls["reversal"].get(key),
                         "momentum": pnls["momentum"].get(key),
                         "arb": pnls["arb"].get(key)})
    return rows


def label_terciles(rows: list[dict], key: str = "prev_rvol") -> tuple[float, float]:
    """Tag each row with regime ∈ {low,med,high} by terciles of `key`. Returns the edges."""
    vals = sorted(r[key] for r in rows)
    n = len(vals)
    if n < 3:
        for r in rows:
            r["regime"] = "med"
        return (float("nan"), float("nan"))
    q1, q2 = vals[n // 3], vals[2 * n // 3]
    for r in rows:
        v = r[key]
        r["regime"] = "low" if v <= q1 else ("high" if v > q2 else "med")
    return q1, q2


def regime_performance(rows: list[dict]) -> list[dict]:
    """Per (regime, strategy): n, mean PnL, cluster-robust t (clustered by wall-clock window)."""
    out = []
    for regime in REGIMES:
        sub = [r for r in rows if r.get("regime") == regime]
        for strat in ("reversal", "momentum", "arb"):
            vals = [(r[strat], r["cur_open_ts"]) for r in sub if r.get(strat) is not None]
            if not vals:
                continue
            ct = clustered_tstat([v for v, _ in vals], [c for _, c in vals])
            out.append({"regime": regime, "strategy": strat, "n": len(vals),
                        "mean_pnl": ct["mean"], "t": ct["t"]})
    return out


def vol_persistence(windows: list[TradeWindow], spot_dir: str = "data/spot") -> dict:
    """Lag-1 autocorrelation of per-window realized vol (consecutive pairs). >0 ⇒ vol
    clusters ⇒ the vol regime is predictable from the prior window."""
    spots = {a: load_spot(a, spot_dir) for a in SPOT_ASSETS}
    x0, x1 = [], []
    for a, ws in _by_asset_sorted(windows).items():
        if not spots.get(a):
            continue
        seq = []
        for w in ws:
            f = window_spot_features(w, spots[a])
            if f:
                seq.append((w.open_ts, f["rvol"]))
        for (t0, v0), (t1, v1) in zip(seq, seq[1:]):
            if abs(t1 - t0 - WINDOW_SECONDS) < 1.0:
                x0.append(v0)
                x1.append(v1)
    n = len(x0)
    if n < 3:
        return {"n": n, "autocorr": float("nan")}
    m0, m1 = sum(x0) / n, sum(x1) / n
    cov = sum((a - m0) * (b - m1) for a, b in zip(x0, x1))
    s0 = sum((a - m0) ** 2 for a in x0)
    s1 = sum((b - m1) ** 2 for b in x1)
    return {"n": n, "autocorr": cov / math.sqrt(s0 * s1) if s0 > 0 and s1 > 0 else float("nan")}


def vol_by_hour(windows: list[TradeWindow], spot_dir: str = "data/spot") -> list[dict]:
    """Mean realized vol by UTC hour-of-day (intraday seasonality of the regime)."""
    spots = {a: load_spot(a, spot_dir) for a in SPOT_ASSETS}
    by: dict[int, list[float]] = defaultdict(list)
    for a, ws in _by_asset_sorted(windows).items():
        if not spots.get(a):
            continue
        for w in ws:
            f = window_spot_features(w, spots[a])
            if f:
                by[int(w.open_ts // 3600) % 24].append(f["rvol"])
    return [{"hour": h, "n": len(by[h]), "mean_rvol": sum(by[h]) / len(by[h])}
            for h in sorted(by)]
