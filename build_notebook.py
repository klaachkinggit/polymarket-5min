"""Builds notebooks/polymarket_5min_arb.ipynb from source cells (reproducible)."""
import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

C = []
md = lambda s: C.append(new_markdown_cell(s.strip("\n")))
code = lambda s: C.append(new_code_cell(s.strip("\n")))

# ============================================================ TITLE
md(r"""
# Polymarket 5-Minute Up/Down — Double-Dip Arbitrage Backtest

**Strategy.** In each recurring 5-minute crypto Up/Down market we watch the
**ask** of both tokens. The first time a token's ask falls to `<= threshold`
(e.g. $0.45) we buy 1 share of it. The two legs are filled **independently and
at different times**, exploiting intra-window *overshoot*.

- **Both legs fill** for a combined cost `< $1.00` &rarr; one side settles at
  $1.00 &rarr; **locked, risk-free arbitrage**.
- **Only one leg fills** &rarr; **unhedged** directional bet: settles $1 (win) or
  **$0 (the core risk)**.

**Honest data constraint (verified against the live API).** Polymarket's public
`/prices-history` exposes a **mid** series at **1-minute** finest fidelity — not
the order book, and not sub-second. So:
- The executable **ask** is reconstructed as `mid + half_spread (+ slippage)`.
- Real-history backtests are **coarse**; a true tick-level study requires
  collecting the live CLOB WebSocket book going forward.
- For high-fidelity engine validation we also drive a **synthetic** generator.

**Architecture** — logic lives in the importable `polymarket_arb` package
(`data`, `synth`, `engine`, `metrics`, `optimize`) so this exact code lifts into
the production bot. The notebook is the analysis surface.
""")

code(r"""
import sys, os, logging
sys.path.insert(0, os.path.abspath(".."))   # import the package from repo root
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
logging.basicConfig(level=logging.WARNING)

from polymarket_arb import (PolymarketClient, ArbBacktester, ExecConfig,
                            summary, equity_curve, threshold_sweep, param_grid,
                            generate_dataset)
from polymarket_arb.engine import (ARB_LOCKED, HEDGED_NEGEDGE, UNHEDGED_WIN,
                                   UNHEDGED_LOSS, NO_FILL)
pd.set_option("display.width", 120)
plt.rcParams["figure.figsize"] = (10, 4)
""")

# ============================================================ 1. DATA
md(r"""
## 1 — Data Acquisition & API Integration

Two official endpoints:

| API | Base | Used for |
|-----|------|----------|
| Gamma | `gamma-api.polymarket.com` | discover 5-min events (`tag_slug=crypto`, slug `*-updown-5m-*`); read resolution from `outcomePrices` |
| CLOB | `clob.polymarket.com` | `/prices-history` mid series per token |

`clobTokenIds[0]` = **Up/YES**, `[1]` = **Down/NO**. Resolution `["1","0"]` &rarr; Up won, `["0","1"]` &rarr; Down won.
""")

code(r"""
client = PolymarketClient(cache_dir="../.cache")   # disk-cached, retrying

# Discover a few live/recent 5-minute events
events = client.discover_5m_events(asset="btc", closed=True, max_events=6)
print("recent BTC 5-min events:")
for e in events[:6]:
    print("  ", e["slug"], "|", e.get("title"))
""")

code(r"""
# Load a REAL backtest dataset. Falls back to synthetic if the API is unreachable.
ASSET, MAX_WINDOWS = "btc", 80
try:
    windows = client.load_dataset(asset=ASSET, max_windows=MAX_WINDOWS, fidelity=1)
    DATA_SOURCE = f"REAL Polymarket history ({ASSET.upper()})"
    assert len(windows) >= 5
except Exception as ex:
    print("API unavailable -> synthetic fallback:", repr(ex))
    windows = generate_dataset(n=MAX_WINDOWS, asset="BTC", vol_window=0.012)
    DATA_SOURCE = "SYNTHETIC fallback"

print(f"{DATA_SOURCE}: {len(windows)} resolved windows")
w = windows[0]
print("sample:", w.slug, "| ticks", len(w.ticks),
      "| res_yes", w.resolution_yes,
      "| YES range", round(min(t.yes_mid for t in w.ticks), 3),
      "-", round(max(t.yes_mid for t in w.ticks), 3))
""")

md(r"""
### Synthetic high-fidelity generator (for validation & stress)

Drives Up = `Phi(d)` off a GBM underlying; as time-to-expiry &rarr; 0 the price
snaps to 0/1 and resolution is read from the terminal underlying. This is the
only way to study realistic **sub-second overshoot**, since real history is
1-minute mid only.
""")

code(r"""
synth = generate_dataset(n=300, asset="BTC", vol_window=0.012, n_ticks=300)
sw = synth[0]
t = np.array([tk.ts for tk in sw.ticks]); y = np.array([tk.yes_mid for tk in sw.ticks])
plt.plot(t, y, label="Up (YES) mid"); plt.plot(t, 1 - y, label="Down (NO) mid", alpha=.7)
plt.axhline(0.45, ls="--", c="grey", label="threshold 0.45")
plt.title(f"Synthetic window {sw.slug} — resolves Up={sw.resolution_yes:.0f}")
plt.xlabel("seconds into window"); plt.ylabel("price"); plt.legend(); plt.show()
""")

# ============================================================ 2. ENGINE
md(r"""
## 2 — Core Simulation Engine

State machine per window: `WAITING -> {YES_FILLED, NO_FILLED} -> HEDGED -> settle`.

**Look-ahead is structural.** `ArbBacktester.simulate(ticks)` receives *only* the
tick path — never the resolution. Fills are decided sequentially on observable
asks. `_settle()` is the **only** code that reads `resolution_yes`, applied after
the window closes.

`ExecConfig`: `threshold`, `half_spread` (ask = mid + half_spread),
`slippage` (extra price paid per share), `fee_bps` (Polymarket-style
`fee = bps/1e4 * size * min(p, 1-p)`), `size`.
""")

code(r"""
cfg = ExecConfig(threshold=0.47, half_spread=0.005, slippage=0.0, fee_bps=0.0, size=1.0)
results = ArbBacktester(cfg).run(windows)

rows = [{"slug": r.slug[-18:], "res_yes": r.resolution_yes, "legs": r.n_legs,
         "cost": round(r.cost, 3), "payout": round(r.payout, 3),
         "pnl": round(r.pnl, 3), "outcome": r.outcome} for r in results[:12]]
pd.DataFrame(rows)
""")

md(r"""
**Outcome taxonomy** — `ARB_LOCKED` (both legs, cost < $1, guaranteed profit),
`HEDGED_NEGEDGE` (both legs but overpaid), `UNHEDGED_WIN` / `UNHEDGED_LOSS`
(single leg settles $1 / $0 — the core risk), `NO_FILL`.
""")

# ============================================================ 3. VISUALS
md(r"""## 3 — Visual Analytics""")

code(r"""
# Equity curve (cumulative PnL, $1/leg sizing)
ts, eq = equity_curve(results, starting_capital=0.0)
plt.plot(range(len(eq)), eq, lw=1.5)
plt.axhline(0, c="grey", lw=.8)
plt.title(f"Equity curve — {DATA_SOURCE}, threshold={cfg.threshold}, half_spread={cfg.half_spread}")
plt.xlabel("window # (time order)"); plt.ylabel("cumulative PnL ($)"); plt.show()
""")

code(r"""
# Threshold sweep — the "sweet spot": net profit vs fill rate
sweep = threshold_sweep(windows, np.round(np.arange(0.35, 0.495, 0.01), 3),
                        ExecConfig(half_spread=0.005))
fig, ax1 = plt.subplots()
ax1.plot(sweep.threshold, sweep.net_profit, "o-", color="tab:blue", label="net profit")
ax1.axhline(0, c="grey", lw=.8); ax1.set_xlabel("entry threshold")
ax1.set_ylabel("net profit ($)", color="tab:blue")
ax2 = ax1.twinx()
ax2.plot(sweep.threshold, sweep.both_fill_rate, "s--", color="tab:green", label="both-fill (hedge) rate")
ax2.plot(sweep.threshold, sweep.unhedged_loss_rate, "^--", color="tab:red", label="unhedged-loss rate")
ax2.set_ylabel("rate", color="tab:green")
fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.88)); plt.title("Threshold optimisation")
plt.show()
sweep.round(3)
""")

code(r"""
# Heatmap: threshold x slippage -> net profit
grid = param_grid(windows,
                  thresholds=np.round(np.arange(0.38, 0.495, 0.015), 3),
                  slippages=[0.0, 0.005, 0.01, 0.015, 0.02],
                  base_cfg=ExecConfig(half_spread=0.005), metric="total_pnl")
fig, ax = plt.subplots(figsize=(9, 4))
im = ax.imshow(grid.values, aspect="auto", origin="lower", cmap="RdYlGn",
               vmin=-abs(grid.values).max(), vmax=abs(grid.values).max())
ax.set_xticks(range(len(grid.columns))); ax.set_xticklabels(grid.columns, rotation=45)
ax.set_yticks(range(len(grid.index))); ax.set_yticklabels(grid.index)
ax.set_xlabel("threshold"); ax.set_ylabel("slippage")
plt.colorbar(im, label="net profit ($)"); plt.title("Net profit surface (green = profitable)")
plt.show()
""")

code(r"""
# Outcome composition across thresholds
comp = []
for thr in np.round(np.arange(0.38, 0.495, 0.02), 3):
    s = summary(ArbBacktester(ExecConfig(threshold=thr, half_spread=0.005)).run(windows))
    comp.append({"threshold": thr, **{k: s["counts"][k] / s["n_windows"]
                 for k in (ARB_LOCKED, HEDGED_NEGEDGE, UNHEDGED_WIN, UNHEDGED_LOSS, NO_FILL)}})
comp = pd.DataFrame(comp).set_index("threshold")
comp.plot(kind="bar", stacked=True, colormap="Spectral", figsize=(10, 4))
plt.ylabel("share of windows"); plt.title("Outcome composition vs threshold"); plt.show()
""")

# ============================================================ 4. ANALYSIS
md(r"""## 4 — Analysis & Commentary""")

code(r"""
s = summary(results)
metric_keys = ["n_windows","n_traded","total_pnl","avg_pnl_per_window","win_rate",
               "fill_rate","both_fill_rate","arb_lock_rate","unhedged_rate",
               "unhedged_loss_rate","no_fill_rate","max_drawdown","profit_factor",
               "sharpe_per_window"]
pd.Series({k: s[k] for k in metric_keys}).to_frame(f"value (threshold={cfg.threshold})")
""")

md(r"""
### Reading the numbers

- **Total profit / avg per window** — net of reconstructed spread + slippage.
- **Arb-lock rate vs unhedged-loss rate** — the heart of the thesis. A real edge
  needs `arb_lock_rate` &times; (locked profit) to dominate
  `unhedged_loss_rate` &times; (avg loss). Lowering the threshold *raises*
  unhedged-loss rate faster than it raises locked arbs.
- **Max drawdown / profit factor** — survivability and gross-win vs gross-loss.

**Conclusion on this sample (80 real BTC windows, half_spread=0.005).** The
"overshoot arbitrage" is an illusion once the **ask spread** is paid. Net profit
is **negative at every threshold 0.40–0.49** (profit factor ≈ 0.61–0.82): a cheap
dip on one leg is usually *informative* (the market keeps trending), so the second
leg only fills while the position is collapsing — leaving you unhedged on the
losing side (unhedged-loss rate 30–72%). Locked arbs do occur (22–70% of windows)
but their combined cost sits too close to $1, so the few thin locks cannot offset
the unhedged losers. Raising the threshold trades unhedged risk for a vanishing
per-trade edge — there is no profitable "sweet spot" here under realistic fills.

### Before any live capital
1. **Get real book data.** Collect the CLOB WebSocket (`wss://ws-subscriptions-clob.polymarket.com`) to measure the *actual* ask depth and whether `<= threshold` quantities are even fillable at size.
2. **Latency.** A retail bot will not win the queue at the best dip; widen `slippage` to your measured fill quality and re-check the heatmap.
3. **Decision rule.** Lift to production **only** if the net-profit surface stays green under realistic `half_spread` + `slippage` and out-of-sample windows.
""")

# ============================================================ 5. HIGH-FIDELITY TRADE TAPE
md(r"""
## 5 — High-Fidelity Data: the On-Chain Trade Tape

Sections 1–4 used the only *public history* endpoint, `/prices-history` — a
**1-minute mid**, ~5 points per 5-minute window. That is far too coarse for an
intra-window strategy: the action is compressed into the final 1–2 minutes, and
the mid sits at ~0.50 for the ~20h the market is open beforehand.

But Polymarket settles on Polygon, so **every executed trade is recorded**. The
public `data-api.polymarket.com/trades?market=<conditionId>` endpoint returns the
full executed tape — exact `price`, `size`, `side` (BUY/SELL), token, and
second-granularity `timestamp` — **~2000–3000 trades per window** instead of 5.

**Fill model on the tape (look-ahead-safe).** A resting BUY at threshold `T` fills
**only on a SELL print** at `price <= T`: a SELL means a taker hit a resting bid
there, proving marketable liquidity existed at-or-below our bid. BUY prints (ask
lifts) are *forbidden* — using them is the classic optimism/look-ahead error. We
execute at our limit `T` (we are the passive order), exclude the post-close
settlement tail (prices snapping to 0/1), and run YES and NO as independent
streams so each leg fills on its own clock — the true temporal double-dip.

**Caveats (verified live).** The API caps `offset` at 3000 → at most the latest
4000 trades per window (busier windows are flagged `truncated`); resting **book
depth** is *not* in any historical feed (it is off-chain) — only the live CLOB
WebSocket exposes it going forward. `research/findings.json` documents the verified
on-chain `eth_getLogs` route (V2 CTF Exchange `0xE111…996B`, `OrderFilled` topic0
`0xd543adfd…`, `tokenId` == `clobTokenId`) which has no offset cap and is the
complete-data remedy / audit path.
""")

code(r"""
from polymarket_arb import TapeBacktester, TapeConfig, tape_threshold_sweep
from polymarket_arb.optimize import tape_param_grid
from polymarket_arb.trades import TradeHistoryClient

thc = TradeHistoryClient(client=client)            # reuse the cached PolymarketClient
try:
    tape_windows = thc.load_dataset(asset=ASSET, max_windows=MAX_WINDOWS)
    assert len(tape_windows) >= 5
    TAPE_OK = True
except Exception as ex:
    print("trade-tape API unavailable:", repr(ex)); tape_windows = []; TAPE_OK = False

if TAPE_OK:
    tt = [w.n_trades for w in tape_windows]
    n_trunc = sum(w.truncated for w in tape_windows)
    print(f"{len(tape_windows)} windows | total trades {sum(tt):,} | "
          f"median {sorted(tt)[len(tt)//2]}/window | truncated(>4000) {n_trunc}")
""")

code(r"""
# Fidelity contrast on ONE window: 1-min mid vs the real executed tape
if TAPE_OK:
    tw = tape_windows[0]
    mw = next((m for m in windows if m.slug == tw.slug), windows[0])
    print(f"window {tw.slug}")
    print(f"  /prices-history mid points : {len(mw.ticks)}")
    print(f"  executed trades (tape)     : {tw.n_trades}  "
          f"(YES {len(tw.yes_trades)}, NO {len(tw.no_trades)})  -> ~{tw.n_trades/max(len(mw.ticks),1):.0f}x")
""")

code(r"""
# The real executed tape for a window that locks arb (both legs dip <= T at different times)
if TAPE_OK:
    bt = TapeBacktester(TapeConfig(threshold=0.45))
    res_t = bt.run(tape_windows)
    pick_i = next((i for i, r in enumerate(res_t) if r.outcome == ARB_LOCKED), 0)
    pick = tape_windows[pick_i]
    fig, ax = plt.subplots(figsize=(10, 4))
    for tr, c, lbl in [(pick.yes_trades, "tab:blue", "Up/YES"), (pick.no_trades, "tab:orange", "Down/NO")]:
        sells = [(t.ts - pick.open_ts, t.price) for t in tr if t.side == "SELL"]
        if sells:
            ax.scatter([p[0] for p in sells], [p[1] for p in sells], s=10, c=c, alpha=.55, label=f"{lbl} SELL")
    ax.axhline(0.45, ls="--", c="grey", label="threshold 0.45")
    ax.set_xlabel("seconds into 5-min window"); ax.set_ylabel("executed price"); ax.set_ylim(0, 1)
    ax.set_title(f"Real trade tape — {pick.slug} (resolves Up={pick.resolution_yes:.0f}, outcome={res_t[pick_i].outcome})")
    ax.legend(); plt.show()
""")

code(r"""
# Per-window table + summary on the real tape (T=0.45)
if TAPE_OK:
    rows = [{"slug": r.slug[-18:], "res_yes": r.resolution_yes, "legs": r.n_legs,
             "cost": round(r.cost, 3), "payout": round(r.payout, 3),
             "pnl": round(r.pnl, 3), "outcome": r.outcome} for r in res_t[:12]]
    display(pd.DataFrame(rows))
    st = summary(res_t)
    keys = ["n_windows","total_pnl","avg_pnl_per_window","fill_rate","both_fill_rate",
            "arb_lock_rate","unhedged_loss_rate","unhedged_win_rate","win_rate",
            "max_drawdown","profit_factor"]
    display(pd.Series({k: round(st[k], 4) for k in keys}).to_frame("tape model @ T=0.45"))
    print("counts:", st["counts"])
""")

code(r"""
# Tape-model threshold sweep
if TAPE_OK:
    tsw = tape_threshold_sweep(tape_windows, np.round(np.arange(0.35, 0.495, 0.01), 3))
    fig, ax1 = plt.subplots()
    ax1.plot(tsw.threshold, tsw.net_profit, "o-", color="tab:blue", label="net profit")
    ax1.axhline(0, c="grey", lw=.8); ax1.set_xlabel("threshold")
    ax1.set_ylabel("net profit ($)", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(tsw.threshold, tsw.arb_lock_rate, "s--", color="tab:green", label="arb-lock rate")
    ax2.plot(tsw.threshold, tsw.unhedged_loss_rate, "^--", color="tab:red", label="unhedged-loss rate")
    ax2.set_ylabel("rate", color="tab:green")
    fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.88)); plt.title("Tape-model threshold sweep")
    plt.show()
    display(tsw[["threshold","net_profit","arb_lock_rate","unhedged_loss_rate","profit_factor"]].round(3))
""")

code(r"""
# Heatmap: threshold x trading fee (bps). Slippage is N/A here — we fill at our limit T.
if TAPE_OK:
    grid = tape_param_grid(tape_windows,
                           thresholds=np.round(np.arange(0.38, 0.495, 0.015), 3),
                           fee_bps_grid=[0, 50, 100, 200, 400], metric="total_pnl")
    fig, ax = plt.subplots(figsize=(9, 4))
    im = ax.imshow(grid.values, aspect="auto", origin="lower", cmap="RdYlGn",
                   vmin=-abs(grid.values).max(), vmax=abs(grid.values).max())
    ax.set_xticks(range(len(grid.columns))); ax.set_xticklabels(grid.columns, rotation=45)
    ax.set_yticks(range(len(grid.index))); ax.set_yticklabels(grid.index)
    ax.set_xlabel("threshold"); ax.set_ylabel("fee (bps)")
    plt.colorbar(im, label="net profit ($)"); plt.title("Tape net-profit surface (green = profitable)")
    plt.show()
""")

md(r"""
### What the high-fidelity tape reveals

Running the same strategy on ~190k real trades instead of ~400 mids does **not**
rescue it — and it explains *why* with far higher confidence:

- **The double-dip is real and frequent.** ~66% of windows lock arbitrage at
  T=0.45 (vs ~42% under the coarse mid): when the market oscillates across 0.50
  intra-window, *both* legs cross the threshold at different seconds and you hold a
  guaranteed-$1 pair for < $1.
- **But every single-leg fill is the loser** (`UNHEDGED_WIN` = 0). When the market
  *trends*, only the losing side gets cheap; the winner stays expensive and never
  fills. You are adversely selected into holding losers.
- **The payoff is structurally lopsided.** A lock earns `1 − 2T` = **+$0.10** at
  T=0.45; an unhedged loss costs **−$0.45**. At ~2 locks per loss, the losses win.
  Net P&L is **negative at every threshold 0.35–0.49, even at zero fees and under a
  generous (front-of-queue) fill assumption.** Fees only deepen it.

**Verdict.** Better data did not create edge; it *confirmed* its absence with 190k
real trades and revealed the mechanism the 1-minute mid hid. The passive double-dip
is not viable as stated. The production-relevant fix is a **decision rule that
refuses to hold an unhedged leg** (cancel/exit the first leg if the second hasn't
filled by a cutoff) — turning a directional gamble into actual arbitrage. That is a
different strategy to test next, ideally on live CLOB WebSocket book data so fills
are validated against real resting depth rather than inferred from the trade tape.
""")

nb = new_notebook(cells=C, metadata={"kernelspec": {"name": "python3",
                  "display_name": "Python 3", "language": "python"}})
out = "notebooks/polymarket_5min_arb.ipynb"
with open(out, "w") as f:
    nbf.write(nb, f)
print("wrote", out, "with", len(C), "cells")
