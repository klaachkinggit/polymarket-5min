# Reversal Strategy Audit

*Adversarial multi-agent audit (4 independent lenses → adversarial verify → synthesis).
22 candidate findings, all 22 verified; merged into the issues below. Re-analysis that
acts on these findings: `research/reversal_analysis.md` (run `analyze_reversal.py`).*

## Verdict

The reversal edge is **real as a statistical phenomenon but not trustworthy as a
tradeable claim**. The core anomaly — negative lag-1 autocorrelation of 5-min Up/Down
outcomes — is computed purely on the ±1 resolution series with **no price input** and
survived every adversarial check: the signal is correctly lagged (the previous window
closes before the current opens, and the current window's own outcome never feeds the
entry), so there is **no look-ahead**. What is *not* sound is the chain of optimistic
**execution** assumptions behind the claimed t≈2.0–2.7 tradeable edge: (a) the entry
price was taken side-blind at the earliest executed print, which assumes a *buy* can
fill at a possible *bid*; (b) the 2–4¢/bet edge was only ever stress-tested against
spreads ≤1¢; (c) the open-price-missing skip preferentially drops likely-losing bets;
and (d) the IID t-stat pools cross-correlated assets, understating the standard error.
None of these manufactures the autocorrelation, but together they erode t≈2 toward
insignificance. **The anomaly is sound; the "+$0.02–0.04/bet tradeable" claim is not,
until fill realism and dependence-robust SEs are addressed.**

## Confirmed issues (ranked by corrected severity)

### HIGH

**1. Side-blind entry buys at the earliest print regardless of trade side.**
`momentum.py` `_opening_price` returned the earliest in-window print with no side
check, and `run()` treated it as a taker buy at the ask. An executed **SELL** print is
a taker hitting the resting **bid** — you cannot buy there; the ask is strictly higher.
So entry cost was understated whenever the opening print was a SELL (~half the time).
On a 2–4¢ edge against a 1–3¢ spread this can erase the headline significance.
**Fix (done):** `entry_side="buy"` enters at the earliest **BUY** (ask-lift) print —
real evidence the ask was takeable — and never a SELL/bid print. `entry_side="any"`
keeps the old behavior for contrast.

**2. Truncated windows give a shifted opening price and were never filtered.**
`fetch_trades` pages newest-first and stops past `MAX_OFFSET=3000`, keeping the latest
~4000 trades and flagging `truncated`. `_opening_price` then took the earliest
*retained* trade as the open. The backtest never inspected `truncated`. Impact is
bounded (~0.8% of windows, all BTC, earliest retained trade still within ~10–14s of
open, and the bias is conservative for reversal), so corrected critical→high.
**Fix (done):** `exclude_truncated=True` drops them by default; count is reported.

### MEDIUM

**3. The edge was never stress-tested against a realistic spread.** The friction grid
only ever used half-spread ∈ {0.0, 0.01}; a thin 5-min ~$0.50 book plausibly has a
1.5–3¢ touch — comparable to the entire edge.
**Fix (done):** grid extended to 0.015 / 0.02 / 0.03. (Polymarket CLOB fees are
currently 0; the `fee_bps` knob remains for stress.)

**4. The open-price-missing skip is non-random w.r.t. outcome (selection bias).**
When the bet token had no in-window trade, the pair was silently skipped — but a token
trades ~never precisely when it has ~no chance, so skipped bets almost always lose.
Dropping them inflates win-rate/avg-PnL (≈0.9pp). Magnitude limited (~1.5% of pairs).
**Fix (added):** `require_both_quotes=True` restricts to pairs where both tokens have an
entry quote (an outcome-independent sample). Note: for *executable* PnL, skipping a
truly unfillable bet is realistic (you simply don't bet); the bias only matters for
interpreting the win-rate, so the autocorr z (no skips, no prices) remains the clean
signal measure.

**5. IID t-stat over a pooled, cross-correlated, serially dependent sample.** The
textbook `m/(sd/√n)` with n≈1245 assumes independence. All assets share clock-aligned
windows, so calendar-overlapping bets are cross-correlated → effective n ≪ n, inflating
t. (Serial dependence is the smaller effect and, with negative autocorrelation, the
HAC variance is if anything *smaller* than IID — so the net correction is dominated by
cross-asset inflation, on the order of ~10–40% of the SE.)
**Fix (done):** `reversal_analysis.clustered_tstat` clusters by wall-clock window
(`start_ts`), and `block_bootstrap` resamples whole windows. Both are reported next to
the naive t.

**6. Win-rate, autocorr z, and reversal PnL are largely the same statistic.** Reversal
wins exactly when the outcome does not repeat, so `win_rate ≈ (1 − r)/2` — the "55.5%
win-rate", the "z", and the per-asset bars are three views of one quantity, not three
independent confirmations. (The PnL *t-stat* does carry independent price/mispricing
information.)
**Fix (done):** the analysis presents these as one phenomenon; the economic test is the
friction-net, cluster-robust PnL t-stat.

## Examined and found clean (no finding)

- **Look-ahead / temporal leakage:** signal = previous window's resolved outcome, known
  before the current window opens; `_consecutive_pairs` enforces an exact 300s gap;
  `run()` reads `cur.resolution_yes` only to score the payout, never to set the entry;
  no future trades, windows, or settlement leak into signal or entry.
- **Resolution parsing:** Up=1.0 / Down=0.0 mapping via `_parse_resolution` is correct.
- **Autocorrelation computation:** the Pearson lag-1 on the ±1 series is correct; it uses
  no prices and no fill assumptions, so it is immune to the execution issues above.

## Recommended next steps (status)

1. ✅ Realistic ask entry (earliest BUY print); exclude truncated windows.
2. ✅ Dependence-robust significance (cluster by wall-clock window + block bootstrap).
3. ✅ Stress the spread to 1.5–3¢ and report the spread-net edge as the headline.
4. ✅ Expand the sample (≈3× depth, +2 less-correlated assets) and re-test.
5. ⏳ Validate live fill quality on the collected order book (the forward collector) —
   whether a resting order near the opening mid actually fills — before any deployment.
