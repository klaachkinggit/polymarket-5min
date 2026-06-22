"""Stochastic-process EDA for the 5-minute Up/Down markets.

These markets are at-the-money digital options on a crypto diffusion: the YES token's
fair value is P(S_{t+5m} > S_t | F_t). This module pulls the underlying spot (Binance
1m klines, aligned to each window's exact timestamps) and provides the analysis battery.

Governing principle (from the design audit, research/dynamics_design_spec.md): the
"no directional edge" conclusion rests on the SPOT/SNR side (clean), NOT on the token
executed-trade path. Raw executed YES prints bounce between bid and ask (Roll 1984), so
every token-path statistic is computed on a CONSTRUCTED MID (YES/NO synthesis) as the
headline, with raw prints kept only as a sensitivity check.

HYPE is not on Binance, so spot panels cover 6 assets; token-tape panels cover all 7.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import requests

from .trades import TradeWindow

log = logging.getLogger("polymarket_arb.dynamics")

BINANCE = "https://api.binance.com/api/v3/klines"
SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "bnb": "BNBUSDT",
           "doge": "DOGEUSDT", "xrp": "XRPUSDT"}     # hype: not on Binance
SPOT_ASSETS = tuple(SYMBOLS)
SPOT_DIR = "data/spot"


# ---- spot data ------------------------------------------------------------
def fetch_spot_1m(asset: str, start_s: int, end_s: int, cache_dir: str = SPOT_DIR,
                  session: requests.Session | None = None) -> list[list]:
    """Continuous 1-minute klines for `asset` over [start_s, end_s], cached as JSON.
    Each row: [open_time_s, open, high, low, close, volume]."""
    sym = SYMBOLS[asset]
    sess = session or requests.Session()
    out: list[list] = []
    start_ms, end_ms = int(start_s) * 1000, int(end_s) * 1000
    while start_ms < end_ms:
        for attempt in range(4):
            r = sess.get(BINANCE, params={"symbol": sym, "interval": "1m",
                         "startTime": start_ms, "endTime": end_ms, "limit": 1000}, timeout=20)
            if r.status_code == 200:
                break
            time.sleep(1 + attempt)
        else:
            raise RuntimeError(f"binance {sym} {r.status_code} {r.text[:100]}")
        batch = r.json()
        if not batch:
            break
        for k in batch:
            out.append([k[0] // 1000, float(k[1]), float(k[2]), float(k[3]),
                        float(k[4]), float(k[5])])
        if len(batch) < 1000:
            break
        start_ms = batch[-1][0] + 60_000
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{asset}-1m.json").write_text(json.dumps(out))
    log.info("spot %s: %d 1m bars cached", asset, len(out))
    return out


def load_spot(asset: str, cache_dir: str = SPOT_DIR) -> dict[int, tuple]:
    """{minute_ts_s: (open, high, low, close)} for an asset, or {} if uncached."""
    p = Path(cache_dir) / f"{asset}-1m.json"
    if not p.exists():
        return {}
    return {int(r[0]): (r[1], r[2], r[3], r[4]) for r in json.loads(p.read_text())}


def window_span(windows: list[TradeWindow]) -> tuple[int, int]:
    return (min(int(w.open_ts) for w in windows), max(int(w.close_ts) for w in windows))


# ---- pure statistics ------------------------------------------------------
def log_returns(prices: list[float]) -> list[float]:
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))
            if prices[i - 1] > 0 and prices[i] > 0]


def moments(xs: list[float]) -> dict:
    """mean, std, skewness, excess kurtosis (0 for a normal)."""
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": float("nan"), "std": float("nan"),
                "skew": float("nan"), "exkurt": float("nan")}
    m = sum(xs) / n
    sd = (sum((x - m) ** 2 for x in xs) / n) ** 0.5
    if sd == 0:
        return {"n": n, "mean": m, "std": 0.0, "skew": 0.0, "exkurt": 0.0}
    skew = sum(((x - m) / sd) ** 3 for x in xs) / n
    exkurt = sum(((x - m) / sd) ** 4 for x in xs) / n - 3.0
    return {"n": n, "mean": m, "std": sd, "skew": skew, "exkurt": exkurt}


def lag1_autocorr(xs: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 0 else float("nan")


def variance_ratio(returns: list[float], k: int) -> dict:
    """Lo-MacKinlay variance ratio with the (1-k/n) bias correction and BOTH the
    homoskedastic z and the heteroskedasticity-robust z*. VR=1 ⇒ random walk; VR<1 ⇒
    mean-reversion, VR>1 ⇒ trending. z* is the one to trust under volatility clustering
    (homoskedastic z over-rejects). Omitting (1-k/n) would bias VR down (fake reversion)."""
    n = len(returns)
    if n < 2 * k or k < 2:
        return {"k": k, "vr": float("nan"), "z": float("nan"), "z_star": float("nan"), "n": n}
    mu = sum(returns) / n
    e = [r - mu for r in returns]
    ss = sum(x * x for x in e)
    var1 = ss / (n - 1)                                  # unbiased 1-period variance
    if var1 == 0:
        return {"k": k, "vr": float("nan"), "z": float("nan"), "z_star": float("nan"), "n": n}
    overl = [sum(returns[i:i + k]) for i in range(n - k + 1)]
    denom = k * (n - k + 1) * (1.0 - k / n)              # LM bias correction
    vark = sum((o - k * mu) ** 2 for o in overl) / denom
    vr = vark / var1
    phi = 2.0 * (2 * k - 1) * (k - 1) / (3.0 * k * n)
    z = (vr - 1.0) / math.sqrt(phi) if phi > 0 else float("nan")
    # heteroskedasticity-robust (Lo-MacKinlay z2)
    theta = 0.0
    for j in range(1, k):
        num = sum(e[t] ** 2 * e[t - j] ** 2 for t in range(j, n))
        delta_j = num / (ss * ss) if ss > 0 else 0.0
        theta += (2.0 * (k - j) / k) ** 2 * delta_j
    z_star = (vr - 1.0) / math.sqrt(theta) if theta > 0 else float("nan")
    return {"k": k, "vr": vr, "z": z, "z_star": z_star, "n": n}


def digital_snr(mu_per_min: float, sigma_per_min: float, n_min: int = 5) -> dict:
    """Directional signal-to-noise of an at-the-money 5-min digital.

    Outcome = sign(sum of n_min log-returns); fair YES = Φ(SNR), SNR = mu*sqrt(n)/sigma.
    Since |SNR| ≪ 1 over 5 min, P(Up) ≈ 0.5 to first order (dP/dSNR = φ(0) = 0.399), so
    realized VOL cannot create a directional edge — vol only sets the LEVEL (damping the
    price toward 0.5). The price is vol-sensitive; the *edge* is what's vol-robust (≈0)."""
    if sigma_per_min <= 0:
        return {"snr": float("nan"), "fair_up": float("nan")}
    snr = mu_per_min * math.sqrt(n_min) / sigma_per_min
    fair_up = 0.5 * (1 + math.erf(snr / math.sqrt(2)))
    return {"snr": snr, "fair_up": fair_up}


# ---- token path (constructed mid; raw prints = sensitivity only) ----------
def token_mid_path(window: TradeWindow) -> list[tuple]:
    """Bounce-reduced YES mid from time-aligned YES & NO prints: mid=(yes+(1-no))/2.
    A binary's two tokens sum to ~1, so averaging the YES print with (1 - last NO print)
    cancels much of the bid/ask bounce that contaminates raw executed prices (Roll 1984)."""
    o, c = window.open_ts, window.close_ts
    ev = sorted([(t.ts, 0, t.price) for t in window.yes_trades if o <= t.ts < c]
                + [(t.ts, 1, t.price) for t in window.no_trades if o <= t.ts < c])
    ly = ln = None
    out = []
    for ts, which, px in ev:
        if which == 0:
            ly = px
        else:
            ln = px
        if ly is not None and ln is not None:
            out.append((ts, (ly + (1.0 - ln)) / 2.0))
    return out


def token_path(window: TradeWindow) -> list[tuple]:
    """(ts, raw executed YES price) — bounce-contaminated; sensitivity check only."""
    return [(t.ts, t.price) for t in window.yes_trades
            if window.open_ts <= t.ts < window.close_ts]


def resample_last(path: list[tuple], open_ts: float, close_ts: float, dt: float = 10.0) -> list[float]:
    """Last value per `dt`-second bucket — removes arrival-intensity dependence from
    crossing counts / autocorrelation (raw counts conflate more-trades with more-reversion)."""
    grid: dict[int, float] = {}
    for ts, px in path:
        grid[int((ts - open_ts) // dt)] = px
    return [grid[k] for k in sorted(grid)]


def crossing_count(prices: list[float], level: float = 0.5) -> int:
    """Descriptive: number of times the path crosses `level` (NOT an arcsine quantity)."""
    return sum(1 for i in range(1, len(prices))
               if (prices[i - 1] - level) * (prices[i] - level) < 0)


def fraction_time_above(path: list[tuple], level: float = 0.5) -> float:
    """Time-weighted fraction of the in-window path spent above `level`. THIS is the
    arcsine quantity: for a driftless martingale the across-window distribution of this
    fraction is U-shaped ~ arcsine law F(x)=2/π·arcsin(√x), not uniform."""
    if len(path) < 2:
        return float("nan")
    above = 0.0
    total = 0.0
    for (t0, p0), (t1, _p1) in zip(path, path[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        total += dt
        if p0 > level:
            above += dt
    return above / total if total > 0 else float("nan")


def arcsine_cdf(x: float) -> float:
    """CDF of the Lévy arcsine law on [0,1]: F(x) = (2/π) arcsin(√x)."""
    x = min(1.0, max(0.0, x))
    return (2.0 / math.pi) * math.asin(math.sqrt(x))


def brier_score(pairs: list[tuple]) -> float:
    """Mean (pred - outcome)^2 over (predicted_prob, outcome∈{0,1}); lower = sharper+calibrated."""
    ps = [(p, y) for p, y in pairs if p == p]
    return sum((p - y) ** 2 for p, y in ps) / len(ps) if ps else float("nan")


def calibration_curve(pairs: list[tuple], nbins: int = 10) -> list[dict]:
    """Reliability curve with per-bin Wilson 95% CI. pairs: (predicted_prob, outcome).
    A fairly-priced market lies on y=x within the CIs."""
    bins: list[list] = [[] for _ in range(nbins)]
    for p, y in pairs:
        if p != p:
            continue
        bins[min(nbins - 1, max(0, int(p * nbins)))].append((p, y))
    out = []
    for i, b in enumerate(bins):
        if not b:
            continue
        n = len(b)
        freq = sum(y for _, y in b) / n
        z = 1.96
        denom = 1 + z * z / n
        centre = (freq + z * z / (2 * n)) / denom
        half = z * math.sqrt(freq * (1 - freq) / n + z * z / (4 * n * n)) / denom
        out.append({"bin": i, "n": n, "mean_pred": sum(p for p, _ in b) / n,
                    "freq": freq, "lo": centre - half, "hi": centre + half})
    return out


# ---- window-level features (spot) -----------------------------------------
def window_spot_features(window: TradeWindow, spot: dict[int, tuple]) -> dict | None:
    """In-window underlying features (no look-ahead — uses only bars inside the window)."""
    o, c = int(window.open_ts), int(window.close_ts)
    bars = [spot[t] for t in range(o, c, 60) if t in spot]
    if len(bars) < 2:
        return None
    s_open = bars[0][0]
    closes = [b[3] for b in bars]
    s_close = closes[-1]
    if s_open <= 0 or s_close <= 0:
        return None
    rets = log_returns([s_open] + closes)
    ret = math.log(s_close / s_open)
    rvol = math.sqrt(sum(r * r for r in rets))
    sign = 1 if s_close > s_open else (0 if s_close < s_open else -1)
    diffs = [cl - s_open for cl in closes]
    n_sc = sum(1 for i in range(1, len(diffs))
               if diffs[i - 1] != 0 and diffs[i] != 0 and (diffs[i - 1] > 0) != (diffs[i] > 0))
    res_sign = 1 if window.resolution_yes == 1.0 else 0
    return {"asset": window.asset, "ret": ret, "rvol": rvol, "sign": sign,
            "agree": (sign == res_sign) if sign in (0, 1) else None,
            "n_sign_changes": n_sc, "max_excursion": max(abs(d) for d in diffs) / s_open}


def opening_token_prob(window: TradeWindow) -> float | None:
    """Earliest in-window raw YES print = a single side of the spread (sensitivity)."""
    p = token_path(window)
    return p[0][1] if p else None


def opening_mid_prob(window: TradeWindow, within_s: float = 30.0) -> float | None:
    """Opening implied P(Up) from the constructed mid, averaged over the first `within_s`."""
    mp = token_mid_path(window)
    early = [px for ts, px in mp if ts - window.open_ts <= within_s]
    if early:
        return sum(early) / len(early)
    return mp[0][1] if mp else None


def yes_no_sum_stats(window: TradeWindow) -> dict | None:
    """No-arbitrage check: contemporaneous (last YES + last NO) print sum should ≈ 1.
    Reports mean sum and the fraction of timestamps where it deviates >2¢ (a crude proxy;
    these are trade prints, not asks, so it bounds rather than proves a lock)."""
    o, c = window.open_ts, window.close_ts
    ev = sorted([(t.ts, 0, t.price) for t in window.yes_trades if o <= t.ts < c]
                + [(t.ts, 1, t.price) for t in window.no_trades if o <= t.ts < c])
    ly = ln = None
    sums = []
    for ts, which, px in ev:
        if which == 0:
            ly = px
        else:
            ln = px
        if ly is not None and ln is not None:
            sums.append(ly + ln)
    if not sums:
        return None
    n = len(sums)
    return {"n": n, "mean_sum": sum(sums) / n,
            "frac_below_0.98": sum(1 for s in sums if s < 0.98) / n,
            "frac_above_1.02": sum(1 for s in sums if s > 1.02) / n}


# ---- orchestration helpers ------------------------------------------------
def all_spot_returns(assets=SPOT_ASSETS, cache_dir: str = SPOT_DIR) -> dict[str, list[float]]:
    out = {}
    for a in assets:
        s = load_spot(a, cache_dir)
        if not s:
            continue
        out[a] = log_returns([s[t][3] for t in sorted(s)])
    return out


def spot_resolution_agreement(windows: list[TradeWindow], cache_dir: str = SPOT_DIR) -> dict:
    by: dict[str, list[bool]] = {}
    spots = {a: load_spot(a, cache_dir) for a in SPOT_ASSETS}
    for w in windows:
        a = w.asset.lower()
        if a not in spots or not spots[a]:
            continue
        f = window_spot_features(w, spots[a])
        if f and f["agree"] is not None:
            by.setdefault(a, []).append(f["agree"])
    return {a: {"n": len(v), "agree_rate": sum(v) / len(v)} for a, v in by.items() if v}


def terminal_convergence(windows: list[TradeWindow], buckets=(240, 180, 120, 60, 30, 10)) -> list[dict]:
    """Mean |mid − outcome| as a function of seconds-to-close. A bounded martingale must
    converge to the realized outcome, so this should fall monotonically toward 0."""
    acc = {b: [] for b in buckets}
    for w in windows:
        if not w.resolved:
            continue
        for ts, mid in token_mid_path(w):
            ttc = w.close_ts - ts
            for b in buckets:
                if ttc <= b:
                    acc[b].append(abs(mid - w.resolution_yes))
                    break
    return [{"sec_to_close<=": b, "n": len(v), "mean_abs_err": (sum(v) / len(v) if v else float("nan"))}
            for b, v in acc.items()]


# ---- econometric tests (lazy statsmodels) ---------------------------------
def ljung_box(xs: list[float], lags: int = 10) -> dict:
    import numpy as np
    from statsmodels.stats.diagnostic import acorr_ljungbox
    r = acorr_ljungbox(np.asarray(xs, float), lags=[lags], return_df=True)
    return {"lags": lags, "lb_stat": float(r["lb_stat"].iloc[-1]),
            "lb_pvalue": float(r["lb_pvalue"].iloc[-1])}


def arch_lm(xs: list[float], lags: int = 10) -> dict:
    import numpy as np
    from statsmodels.stats.diagnostic import het_arch
    lm, lmp, f, fp = het_arch(np.asarray(xs, float), nlags=lags)
    return {"lags": lags, "lm_stat": float(lm), "lm_pvalue": float(lmp)}


def adf_kpss(prices: list[float]) -> dict:
    import warnings
    import numpy as np
    from statsmodels.tsa.stattools import adfuller, kpss
    arr = np.asarray(prices, float)
    adf = adfuller(arr, autolag="AIC")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kp = kpss(arr, regression="c", nlags="auto")
    return {"adf_stat": float(adf[0]), "adf_p": float(adf[1]),
            "kpss_stat": float(kp[0]), "kpss_p": float(kp[1])}


def _spans_from_cache(cache_dir: str = ".cache") -> dict[str, tuple]:
    spans = {}
    cd = Path(cache_dir)
    for a in SPOT_ASSETS:
        opens, closes = [], []
        for p in cd.glob(f"trades-{a}-updown-5m-*.json"):
            try:
                d = json.loads(p.read_text())
                opens.append(int(d["open_ts"]))
                closes.append(int(d["close_ts"]))
            except Exception:
                continue
        if opens:
            spans[a] = (min(opens), max(closes))
    return spans


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Fetch aligned Binance spot for the window spans")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--out", default=SPOT_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.fetch:
        spans = _spans_from_cache(args.cache)
        sess = requests.Session()
        for a, (lo, hi) in spans.items():
            n = len(fetch_spot_1m(a, lo, hi, cache_dir=args.out, session=sess))
            print(f"{a}: {n} bars over [{lo},{hi}] ({(hi-lo)/3600:.1f}h)", flush=True)
        print("done", flush=True)


if __name__ == "__main__":
    main()
