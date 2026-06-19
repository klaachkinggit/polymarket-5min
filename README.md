# Polymarket 5-Minute Up/Down — Double-Dip Arbitrage Backtester

Backtests a high-frequency statistical-arbitrage strategy on Polymarket's
recurring 5-minute crypto Up/Down binary markets, then optimises the entry
threshold. Logic lives in an importable package so it lifts directly into a
live bot; `notebooks/polymarket_5min_arb.ipynb` is the analysis surface.

## Strategy

Per 5-minute market, watch each token's **ask**. The first time a token's ask
hits `<= threshold` (e.g. $0.45) buy 1 share. Legs fill **independently, at
different times** (temporal overshoot):

- Both legs fill for combined cost `< $1.00` &rarr; one side settles $1 &rarr; **locked arbitrage**.
- Only one leg fills &rarr; **unhedged**: settles $1 (win) or **$0 (the core risk)**.

## Layout

```
polymarket_arb/
  data.py       PolymarketClient (Gamma + CLOB), MarketWindow/Tick, resolution parsing, disk cache
  trades.py     TradeHistoryClient: full executed-trade tape (data-api), TradeWindow, offset paging
  synth.py      high-fidelity synthetic windows (BS digital off GBM) for validation/stress
  engine.py     ArbBacktester (mid-based) state machine, ExecConfig, Fill, WindowResult
  tape_engine.py TapeBacktester: trade-through fill model over the real tape, TapeConfig/TapeResult
  active.py     ActiveExitBacktester: double-dip that abandons an unhedged leg after a timeout
  momentum.py   MomentumBacktester + autocorr_stats: cross-window serial-correlation bet
  collector.py  BookCollector: forward-only live CLOB WebSocket L2 order-book recorder
  metrics.py    equity curve, drawdown, win/fill/arb-lock/unhedged-loss rates, profit factor
  optimize.py   threshold_sweep / param_grid (mid) + tape_threshold_sweep / tape_param_grid (tape)
tests/          per-constraint verification (look-ahead, slippage/fee, state integrity) — 74 tests
research/findings.json   verified on-chain + WebSocket routes and the fill-model design
notebooks/      polymarket_5min_arb.ipynb  (§1-4 mid, §5 tape, §6 data-driven threshold)
build_notebook.py   regenerates the notebook from source cells
```

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q            # 74 tests
python -m polymarket_arb.collector --minutes 30   # live order-book collector (forward data)
python build_notebook.py             # (re)build the notebook
jupyter lab notebooks/polymarket_5min_arb.ipynb
```

```python
from polymarket_arb import PolymarketClient, ArbBacktester, ExecConfig, summary
windows = PolymarketClient().load_dataset(asset="btc", max_windows=80)   # real, cached
res = ArbBacktester(ExecConfig(threshold=0.47, half_spread=0.005, slippage=0.005)).run(windows)
print(summary(res))
```

## Real APIs (verified live, 2026-06)

| API | Base | Role |
|-----|------|------|
| Gamma | `gamma-api.polymarket.com/events?tag_slug=crypto` | discover slugs `*-updown-5m-*`; resolution from `outcomePrices` |
| CLOB | `clob.polymarket.com/prices-history` | per-token mid series |

`clobTokenIds[0]`=Up/YES, `[1]`=Down/NO. `outcomePrices` `["1","0"]`=Up won, `["0","1"]`=Down won.

## Higher-fidelity data: the on-chain trade tape

`/prices-history` is a **1-minute mid** (~5 points/window) — too coarse for an
intra-window strategy. Polymarket settles on Polygon, so **every executed trade is
recorded**. `data-api.polymarket.com/trades?market=<conditionId>` returns the full
tape (`price`, `size`, `side`, token, second-granularity `timestamp`) —
**~2000–3000 trades/window** vs 5 mids. Verified live (see `research/findings.json`):

- **Paging.** `limit` caps at 1000; `offset` pages newest-first; `offset` caps at
  **3000** &rarr; at most the latest **4000** trades (busier windows flagged
  `TradeWindow.truncated`). No server-side time filter — page all, filter client-side.
- **Window.** The 5-min trading window is `[slug_ts, slug_ts+300)`; the market opens
  ~20h early at ~0.50. Pre-open dust and the post-close settlement tail are excluded.
- **Fill model (`tape_engine.py`).** A resting BUY at `T` fills **only on a SELL print
  `<= T`** (a SELL proves a taker hit a resting bid — real marketable liquidity);
  BUY prints are forbidden (look-ahead/optimism). Execution is at our limit `T`; YES
  and NO are independent streams (true temporal double-dip); resolution is read only
  at settlement.
- **Not available historically:** resting **book depth** is off-chain — only the live
  CLOB WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) exposes it,
  forward-only. The complete-tape remedy past the offset cap is on-chain
  `eth_getLogs` (V2 CTF Exchange `0xE111…996B`, `OrderFilled` topic0 `0xd543adfd…`,
  `tokenId == clobTokenId`). Both documented in `research/findings.json`.

```python
from polymarket_arb import TradeHistoryClient, TapeBacktester, TapeConfig, summary
wins = TradeHistoryClient().load_dataset(asset="btc", max_windows=80)   # real tape, cached
print(summary(TapeBacktester(TapeConfig(threshold=0.45)).run(wins)))
```

## Honest constraints & design decisions

- **`/prices-history` is 1-minute mid only** (~5 points/window) — the basis for the
  mid engine (§1-4). It is *not* the finest available data: the executed **trade
  tape** (above, §5) is ~500× denser and is the accurate layer. The mid path is kept
  for contrast and as a fallback. On the mid path:
  - Executable **ask** is reconstructed: `ask = mid + half_spread`, fill at
    `ask + slippage`. `half_spread` defaults to the market's live `spread`/2.
  - `synth.py` provides high-fidelity sub-second windows for engine validation.
  - Resting **book depth** over time remains unavailable historically (off-chain);
    collect the CLOB WebSocket book going forward for true fill quality.
- **No look-ahead — structural.** `ArbBacktester.simulate(ticks)` never receives
  resolution; `_settle()` is the sole reader of `resolution_yes`. Post-resolution
  ticks (`t > end_ts`) are clipped out of the path in `_merge_histories`.
- **Friction is explicit.** `ExecConfig(slippage, fee_bps)`; fee uses the
  Polymarket-style `fee_bps/1e4 * size * min(p, 1-p)`.
- **Sizing.** 1 share per leg per window (`size`), per spec.

## Strategies tested (1,250 windows: btc/eth/sol/bnb/doge × 250)

All on the high-fidelity trade tape, look-ahead-safe, best-case parameters:

| Strategy | Module | Net P&L | Per-window | Verdict |
|----------|--------|---------|------------|---------|
| Passive double-dip | `tape_engine` | −$32.8 @ T=0.48 (390 win) | −$0.084 | No edge |
| Active-exit double-dip | `active` | −$11.6 @ 5s timeout (390 win) | −$0.030 | No edge (better) |
| Momentum (bet same as prev) | `momentum` | negative | −$0.042 | Loses |
| **Reversal (bet opposite)** | `momentum` | **+$46.5** / +$36.2 w/ 200bps (1,235 bets) | **+$0.038** | **Significant edge (thin)** |

**Outcomes are mean-reverting, and on the full 1,250-window sample it is
statistically significant:** lag-1 autocorrelation **−0.104, z = −3.66** over 1,245
consecutive pairs (negative for *all five* assets). Betting **against** the previous
window wins **55.5%** at an avg entry of 0.518:

| entry | fee | avg/bet | t-stat |
|-------|-----|---------|--------|
| opening print | 0 | +$0.038 | **2.74** |
| opening print | 200bps | +$0.029 | **2.13** |
| +1-tick ask | 0 | +$0.028 | **2.01** |
| +1-tick ask | 200bps | +$0.019 | 1.41 |

The edge is **real but thin** (~2–4¢/bet): significant at zero/low friction and at
realistic ask-entry with low fees (Polymarket fees are typically ~0), but eroded to
marginal (t≈1.4) only under the most pessimistic spread **and** 200bps combined.
It survives out-of-sample across 5 independent assets. This is the one tradeable
signal found — pending live fill-quality validation (see the WebSocket collector).

## Finding (double-dip)

Methodology (per §6): **analyse the tape first, then read the threshold off the data.**

- **Trades span the whole window** (≈23/22/20/19/16% per minute; all 80 windows have
  trades in the first 3 min) — early reversals are real and tradable.
- **Fill model corrected.** A resting BUY at `T` fills when the price *trades through*
  `T` (`fill_mode="trade_through"`, the standard limit rule), not only on a SELL print.
  This halved the loss vs the conservative `sell_through` bound and moved the optimum up.
- **Data-driven optimum ≈ T=0.49**, and net P&L there is **still negative** (≈ −$0.04
  /window, 0 fees, generous fills). The loser reaches `T` ~100% of the time but the
  **winner only reverses below 0.49 in ~89%** of windows; the other ~11% are clean
  trends (winner bottoms 0.50–0.52, *complete data* — 0 of them truncated). A lock earns
  `1 − 2T` = **2¢** at 0.49 while each trend costs **~49¢**: break-even needs the
  clean-trend rate < ~4%, observed ~11%.
- **Active exit explored** (abandon an unhedged leg after Δs): best ≈ −$1.9 vs −$3.0
  passive — better, still negative (and optimistic: ignores exit spread).

**Verdict.** Across every realistic model on the best *historical* data (mid → trade
tape → trade-through → optimal threshold → active exit), the passive double-dip does
not clear zero. The one untested lever — whether early-window **quote** reversals
(book mid, which moves without trading) are fillable — can't be settled historically:
book depth is off-chain (only fills settle on-chain), so it needs a forward CLOB
WebSocket collector (`research/findings.json`). **Do not deploy** on this evidence.
See notebook §4 (mid), §5 (tape), §6 (data-driven threshold).
