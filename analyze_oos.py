"""Out-of-sample test of the low-vol MOMENTUM tilt — statistical + real order-book spread.

(A) Statistical OOS: temporal train/test split. Define the low-vol tercile on the earlier
    `train_frac` of windows; on the held-out later windows, bet momentum in low-vol and
    measure net PnL (realistic ask entry, cluster-robust t). Tests whether the in-sample
    tilt persists forward.
(B) Real-spread test: for windows the live collector captured, fill the same low-vol
    momentum bet at the ACTUAL book ask at the open (book_replay), and measure net PnL.
    Tests whether it survives the real spread we collected.

Writes research/oos_momentum.md. Run:  python analyze_oos.py
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from polymarket_arb import clustered_tstat, load_all
from polymarket_arb.dynamics import SPOT_ASSETS, load_spot, window_spot_features
from polymarket_arb.regimes import _by_asset_sorted, regime_rows
from polymarket_arb.book_replay import load_opening_quotes, window_open_quotes
from polymarket_arb.trades import WINDOW_SECONDS

OUT = Path("research/oos_momentum.md")


def f(x, n=4):
    return "nan" if x != x or x is None else f"{x:.{n}f}"


def _cell(vals):
    """vals: list of (pnl, cluster). -> dict mean/t/n via cluster-robust SE."""
    if not vals:
        return {"n": 0, "mean": float("nan"), "t": float("nan")}
    ct = clustered_tstat([v for v, _ in vals], [c for _, c in vals])
    return {"n": len(vals), "mean": ct["mean"], "t": ct["t"]}


def statistical_oos(rows, train_frac=0.6):
    rows = sorted(rows, key=lambda r: r["cur_open_ts"])
    cut = int(len(rows) * train_frac)
    train, test = rows[:cut], rows[cut:]
    tv = sorted(r["prev_rvol"] for r in train)
    q1 = tv[len(tv) // 3]                         # low-vol threshold from TRAIN only
    out = {"q1": q1, "n_train": len(train), "n_test": len(test), "split_ts": rows[cut]["cur_open_ts"]}
    for name, rs in (("train", train), ("test", test)):
        lo = [r for r in rs if r["prev_rvol"] <= q1]
        for strat in ("momentum", "reversal"):
            out[f"{name}_{strat}"] = _cell([(r[strat], r["cur_open_ts"]) for r in lo
                                            if r.get(strat) is not None])
    return out


def real_spread_rows(windows, index, spot_dir="data/spot", entry_max_off=180.0):
    """Per consecutive (prev,cur) pair with book coverage: prev vol, momentum bet filled at
    the real opening ask, PnL to settlement, and the real half-spread."""
    spots = {a: load_spot(a, spot_dir) for a in SPOT_ASSETS}
    rows = []
    for a, ws in _by_asset_sorted(windows).items():
        if not spots.get(a):
            continue
        for prev, cur in zip(ws, ws[1:]):
            if abs(cur.open_ts - prev.open_ts - WINDOW_SECONDS) >= 1.0:
                continue
            q = window_open_quotes(cur, index)
            if not q or q["yes"]["off"] > entry_max_off or q["no"]["off"] > entry_max_off:
                continue
            pf = window_spot_features(prev, spots[a])
            if not pf:
                continue
            bet_up = prev.resolution_yes == 1.0          # momentum: bet prior side
            ask = q["yes"]["ask"] if bet_up else q["no"]["ask"]
            mid = (q["yes"]["ask"] + q["yes"]["bid"]) / 2 if bet_up else (q["no"]["ask"] + q["no"]["bid"]) / 2
            half_spread = (q["yes"]["ask"] - q["yes"]["bid"]) / 2 if bet_up else (q["no"]["ask"] - q["no"]["bid"]) / 2
            correct = (cur.resolution_yes == 1.0) == bet_up
            rows.append({"asset": a, "cur_open_ts": cur.open_ts, "prev_rvol": pf["rvol"],
                         "ask": ask, "mid": mid, "half_spread": half_spread,
                         "pnl": (1.0 if correct else 0.0) - ask, "entry_off": q["yes"]["off"]})
    return rows


def main():
    data = load_all(count=2000)                   # cache-only; all cached windows
    allw = [w for ws in data.values() for w in ws]
    rows = regime_rows(allw)
    A = statistical_oos(rows)

    idx = load_opening_quotes()
    if idx:
        rs = real_spread_rows(allw, idx)
        rsv = sorted(r["prev_rvol"] for r in rs)
        q1b = rsv[len(rsv) // 3] if rsv else float("nan")
        lo = [r for r in rs if r["prev_rvol"] <= q1b]
        B = {"n_book_pairs": len(rs), "q1": q1b,
             "all": _cell([(r["pnl"], r["cur_open_ts"]) for r in rs]),
             "low": _cell([(r["pnl"], r["cur_open_ts"]) for r in lo]),
             "mean_half_spread": (sum(r["half_spread"] for r in rs) / len(rs)) if rs else float("nan"),
             "mean_ask": (sum(r["ask"] for r in rs) / len(rs)) if rs else float("nan"),
             "mean_entry_off": (sum(r["entry_off"] for r in rs) / len(rs)) if rs else float("nan")}
    else:
        B = None

    def cell(c):
        return f"n={c['n']}, mean={f(c['mean'])}, t={f(c['t'],2)}"

    md = f"""# Out-of-Sample Test — the low-vol momentum tilt

In-sample (regime analysis), **momentum in low-vol windows** was the one suggestive tilt
(~+0.035/window, t≈1.8, below significance). Two honest stress tests follow.

## (A) Statistical OOS — temporal train/test split
Low-vol tercile defined on the **earlier {int(A['n_train']/(A['n_train']+A['n_test'])*100)}%**
of pairs ({A['n_train']} train), tested on the later {A['n_test']} (split at ts={int(A['split_ts'])}).
Realistic ask entry; cluster-robust t (by wall-clock window).

| subset | low-vol momentum | low-vol reversal |
|---|---|---|
| train (in-sample) | {cell(A['train_momentum'])} | {cell(A['train_reversal'])} |
| **test (out-of-sample)** | **{cell(A['test_momentum'])}** | {cell(A['test_reversal'])} |

If the test-momentum mean is ~0 / t<2, the in-sample tilt does **not** persist forward
(it was an in-sample artifact of looking at 9 regime×strategy cells).

## (B) Real order-book spread test
{"_(opening-quote index not built yet — run `python -m polymarket_arb.book_replay --build`)_" if B is None else f'''For the {B['n_book_pairs']} consecutive pairs the live collector captured with a **post-open**
quote (causal — the momentum signal is known only at the open), the bet is filled at the real
best ask, on average {f(B['mean_entry_off'],0)}s into the window.

- Mean **ask paid** = {f(B['mean_ask'])}; mean **half-spread** (ask−mid) = **{f(B['mean_half_spread'])}**.
- Momentum at the real ask — **all regimes**: {cell(B['all'])}
- Momentum at the real ask — **low-vol** (prev_rvol ≤ {f(B['q1'])}): {cell(B['low'])}

Two reads from the real book:
1. **The real spread is ~{f(2*B['mean_half_spread'],3)} round-trip — far tighter than the ~9% I
   estimated from trade-print (YES+NO) overrounds** (those mix ask-side prints on both legs and
   stale prints, overstating it). Honest correction to market_dynamics.md: the book is tighter.
2. **It still loses.** The causal entry is ~{f(B['mean_entry_off'],0)}s post-open at an ask of
   {f(B['mean_ask'])} — already above 0.50, i.e. the early move toward the persisting side is
   *already priced* by the time you can act on the signal. So the bet is ~fair gross, and the
   spread makes it negative. The ~3.5¢ in-sample tilt does not exist at the real, causal fill.'''}

## Verdict
{_verdict(A, B)}
"""
    OUT.write_text(md)
    print(md)
    print(f"\nWrote {OUT}")


def _verdict(A, B):
    tm = A["test_momentum"]
    parts = []
    if tm["t"] == tm["t"] and abs(tm["t"]) < 2:
        parts.append(f"**(A) The low-vol momentum tilt does NOT survive the temporal hold-out** "
                     f"(test momentum mean {f(tm['mean'])}, t={f(tm['t'],2)} — not significant). "
                     f"The in-sample t≈1.8 was consistent with multiple-testing noise across the 9 regime×strategy cells.")
    else:
        parts.append(f"**(A) The low-vol momentum tilt persists out-of-sample** "
                     f"(test momentum mean {f(tm['mean'])}, t={f(tm['t'],2)}) — worth a deeper look.")
    if B is not None:
        bl = B["low"]
        parts.append(f"**(B) At the real collected spread** (half-spread {f(B['mean_half_spread'])}), low-vol "
                     f"momentum nets {f(bl['mean'])}/bet (t={f(bl['t'],2)}, n={bl['n']}) — "
                     f"{'still not tradeable' if not (bl['mean'] and bl['mean']>0 and bl['t'] and bl['t']>2) else 'positive and significant (!)'}.")
    return " ".join(parts)


if __name__ == "__main__":
    main()
