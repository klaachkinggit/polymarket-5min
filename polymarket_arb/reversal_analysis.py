"""Rigorous re-analysis of the cross-window reversal signal (post-audit).

The naive per-bet t-stat overstates significance for two reasons the audit flagged:
  * cross-asset correlation — all 7 assets share clock-aligned 5-min timestamps, so
    bets in the same wall-clock window move together (shared crypto beta); the
    effective sample is far below the raw bet count;
  * serial dependence — bet_N and bet_{N+1} share outcome_N.
Both are addressed by clustering on the wall-clock window timestamp (`start_ts`):
all assets' bets in one 5-min slot form one cluster. We report the cluster-robust
t-stat and a cluster (block) bootstrap CI alongside the naive number.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

from .momentum import MomentumBacktester, MomentumConfig, autocorr_stats
from .trades import TradeHistoryClient

ASSETS = ("btc", "eth", "sol", "bnb", "doge", "xrp", "hype")


def load_all(assets=ASSETS, count: int = 500, cache_dir: str = ".cache",
             cache_only: bool = True) -> dict:
    """Load resolved, non-empty trade-tape windows per asset. `cache_only` (default)
    reads only the disk cache from the newest cached window backward — reproducible and
    fast, and it does not chase the advancing clock. Pass cache_only=False to fetch the
    latest windows from the API (grows the cache)."""
    thc = TradeHistoryClient(cache_dir=cache_dir)
    # cache_only never touches the network, so tolerate large gaps to span any holes
    # left by an interrupted fetch and still collect the latest `count` cached windows.
    gap = 100_000 if cache_only else 40
    return {a: [w for w in thc.load_history(a, count=count, cache_only=cache_only, max_gap=gap)
                if w.resolved and w.n_trades > 0] for a in assets}


def naive_tstat(values: list[float]) -> tuple[float, float, int]:
    n = len(values)
    if n < 2:
        return (float("nan"), float("nan"), n)
    m = sum(values) / n
    sd = (sum((x - m) ** 2 for x in values) / (n - 1)) ** 0.5
    return m, (m / (sd / math.sqrt(n)) if sd > 0 else float("nan")), n


def clustered_tstat(values: list[float], clusters: list) -> dict:
    """Cluster-robust t-stat for the mean (regression on a constant, clustered SE).

    Var(mean) = c / N^2 * sum_g ( sum_{i in g} (x_i - mean) )^2, with the standard
    small-sample factor c = G/(G-1). Captures within-cluster correlation (here:
    all assets in the same wall-clock 5-min window).
    """
    n = len(values)
    if n < 2:
        return {"mean": float("nan"), "t": float("nan"), "se": float("nan"),
                "n": n, "n_clusters": 0}
    m = sum(values) / n
    by: dict = defaultdict(float)
    for x, g in zip(values, clusters):
        by[g] += (x - m)
    g_count = len(by)
    meat = sum(s * s for s in by.values())
    factor = g_count / (g_count - 1) if g_count > 1 else 1.0
    var = factor * meat / (n * n)
    se = math.sqrt(var) if var > 0 else float("nan")
    return {"mean": m, "t": (m / se if se and se > 0 else float("nan")),
            "se": se, "n": n, "n_clusters": g_count}


def block_bootstrap(values: list[float], clusters: list, n_boot: int = 2000,
                    seed: int = 7) -> dict:
    """Cluster (block) bootstrap: resample whole wall-clock windows with replacement.

    Preserves both cross-asset and serial dependence within a window. Returns the
    bootstrap mean distribution summary + share of resamples with mean <= 0.
    """
    rng = random.Random(seed)
    groups: dict = defaultdict(list)
    for x, g in zip(values, clusters):
        groups[g].append(x)
    keys = list(groups.keys())
    G = len(keys)
    if G < 2:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"),
                "p_le_0": float("nan"), "boot_t": float("nan")}
    means = []
    for _ in range(n_boot):
        pool = []
        for _ in range(G):
            pool.extend(groups[keys[rng.randrange(G)]])
        means.append(sum(pool) / len(pool))
    means.sort()
    m = sum(means) / len(means)
    sd = (sum((x - m) ** 2 for x in means) / (len(means) - 1)) ** 0.5
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    p_le_0 = sum(1 for x in means if x <= 0) / len(means)
    return {"mean": m, "lo": lo, "hi": hi, "p_le_0": p_le_0,
            "boot_t": (m / sd if sd > 0 else float("nan"))}


def autocorr_table(data: dict) -> list[dict]:
    """Per-asset + pooled lag-1 autocorrelation with naive z = r*sqrt(n_pairs)."""
    allw = [w for ws in data.values() for w in ws]
    rows = []
    for name, ws in list(data.items()) + [("ALL", allw)]:
        s = autocorr_stats(ws)
        if s.get("n_pairs", 0) == 0:
            continue
        z = s["lag1_autocorr"] * math.sqrt(s["n_pairs"])
        rows.append({"asset": name, "n_pairs": s["n_pairs"],
                     "lag1_autocorr": s["lag1_autocorr"], "z": z,
                     "base_up_rate": s["base_up_rate"],
                     "p_up_after_up": s["p_up_after_up"],
                     "p_up_after_down": s["p_up_after_down"],
                     "repeat_rate": s["repeat_rate"]})
    return rows


def friction_grid(windows: list, direction: str = "reversal",
                  half_spreads=(0.0, 0.01, 0.015, 0.02, 0.03),
                  fees=(0, 100, 200), cfg_kw=None) -> list[dict]:
    """Backtest `direction` over a spread x fee grid; naive + clustered (by start_ts) t."""
    cfg_kw = cfg_kw or {}
    rows = []
    for hs in half_spreads:
        for fee in fees:
            res = MomentumBacktester(MomentumConfig(
                direction=direction, entry_half_spread=hs, fee_bps=fee, **cfg_kw)).run(windows)
            if not res:
                continue
            pnl = [r.pnl for r in res]
            clusters = [r.start_ts for r in res]
            m, t_naive, n = naive_tstat(pnl)
            cl = clustered_tstat(pnl, clusters)
            rows.append({
                "half_spread": hs, "fee_bps": fee, "n": n,
                "win_rate": sum(1 for r in res if r.correct) / n,
                "avg_entry": sum(r.entry_price for r in res) / n,
                "avg_pnl": m, "t_naive": t_naive,
                "t_clustered": cl["t"], "n_clusters": cl["n_clusters"]})
    return rows


def sample_decay(data: dict, orig_assets=("btc", "eth", "sol", "bnb", "doge"),
                 depths=(250, 500)) -> list[dict]:
    """Show how the pooled signal weakens as the sample deepens / widens.

    `load_history` returns windows newest-first, so [:depth] is the most-recent
    `depth` per asset — the regime the earlier (250x5) 'significant' result used.
    """
    rows = []
    for depth in depths:
        sub = {a: data[a][:depth] for a in orig_assets if a in data}
        s = autocorr_stats([w for ws in sub.values() for w in ws])
        if s.get("n_pairs"):
            rows.append({"label": f"recent {depth} x {len(sub)} orig assets",
                         "n_pairs": s["n_pairs"], "lag1_autocorr": s["lag1_autocorr"],
                         "z": s["lag1_autocorr"] * math.sqrt(s["n_pairs"])})
    s = autocorr_stats([w for ws in data.values() for w in ws])
    rows.append({"label": f"ALL {len(data)} assets (full depth)",
                 "n_pairs": s["n_pairs"], "lag1_autocorr": s["lag1_autocorr"],
                 "z": s["lag1_autocorr"] * math.sqrt(s["n_pairs"])})
    return rows
