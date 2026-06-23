# Out-of-Sample Test — the low-vol momentum tilt

In-sample (regime analysis), **momentum in low-vol windows** was the one suggestive tilt
(~+0.035/window, t≈1.8, below significance). Two honest stress tests follow.

## (A) Statistical OOS — temporal train/test split
Low-vol tercile defined on the **earlier 59%**
of pairs (3504 train), tested on the later 2337 (split at ts=1781904000).
Realistic ask entry; cluster-robust t (by wall-clock window).

| subset | low-vol momentum | low-vol reversal |
|---|---|---|
| train (in-sample) | n=1148, mean=-0.0063, t=-0.33 | n=1152, mean=-0.0040, t=-0.21 |
| **test (out-of-sample)** | **n=1440, mean=0.0252, t=1.45** | n=1447, mean=-0.0292, t=-1.72 |

If the test-momentum mean is ~0 / t<2, the in-sample tilt does **not** persist forward
(it was an in-sample artifact of looking at 9 regime×strategy cells).

## (B) Real order-book spread test
For the 357 consecutive pairs the live collector captured with a **post-open**
quote (causal — the momentum signal is known only at the open), the bet is filled at the real
best ask, on average 23s into the window.

- Mean **ask paid** = 0.5167; mean **half-spread** (ask−mid) = **0.0236**.
- Momentum at the real ask — **all regimes**: n=357, mean=-0.0517, t=-1.41
- Momentum at the real ask — **low-vol** (prev_rvol ≤ 0.0007): n=120, mean=-0.0529, t=-1.00

Two reads from the real book:
1. **The real spread is ~0.047 round-trip — far tighter than the ~9% I
   estimated from trade-print (YES+NO) overrounds** (those mix ask-side prints on both legs and
   stale prints, overstating it). Honest correction to market_dynamics.md: the book is tighter.
2. **It still loses.** The causal entry is ~23s post-open at an ask of
   0.5167 — already above 0.50, i.e. the early move toward the persisting side is
   *already priced* by the time you can act on the signal. So the bet is ~fair gross, and the
   spread makes it negative. The ~3.5¢ in-sample tilt does not exist at the real, causal fill.

## Verdict
**(A) The low-vol momentum tilt does NOT survive the temporal hold-out** (test momentum mean 0.0252, t=1.45 — not significant). The in-sample t≈1.8 was consistent with multiple-testing noise across the 9 regime×strategy cells. **(B) At the real collected spread** (half-spread 0.0236), low-vol momentum nets -0.0529/bet (t=-1.00, n=120) — still not tradeable.
