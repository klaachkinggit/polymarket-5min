# Stochastic-Process EDA — Design Spec (multi-agent critique)

*Output of the `design-stochastic-battery` workflow: 4 quant lenses (econometrics,
derivatives pricing, market-microstructure, probability) → 38 recommendations →
consolidated. This is the spec `polymarket_arb/dynamics.py` and the dynamics notebook
implement. ✅ = applied.*

**Governing principle.** The "no directional edge" conclusion rests on the **spot/SNR
side** (Binance 1m klines — clean), NOT on the token executed-trade path. Every token
statistic on raw executed prints is contaminated by bid/ask bounce (Roll 1984), so the
headline runs on a **constructed mid**; raw prints are a sensitivity check only.

## MUST-FIX (statistical / conceptual errors)
1. ✅ **`variance_ratio` bias**: divide the overlapping k-sum SS by `k·(n−k+1)·(1−k/n)`,
   not `k·(n−k+1)`. Omitting `(1−k/n)` biases VR **down** → spurious VR<1 (fake
   mean-reversion — the exact "reverses early" artifact under scrutiny).
2. ✅ **Unbiased 1-period variance** `var1 = Σ(r−μ)²/(n−1)` to match the corrected numerator.
3. ✅ **Heteroskedasticity-robust z\*** (Lo-MacKinlay z2): `θ*=Σ_{j=1}^{k−1}[2(k−j)/k]²·δ_j`,
   `δ_j=Σ(r_t−μ)²(r_{t−j}−μ)²/[Σ(r_t−μ)²]²`; report `z*=(VR−1)/√θ*` **as primary** (the
   data show vol clustering, under which the homoskedastic z over-rejects RW).
4. ✅ **`digital_snr` framing**: not "vol-insensitive / only drift matters." Correct:
   `fair_up=Φ(SNR)`, `SNR=μ√n/σ`; since `|SNR|≪1`, `P(Up)≈0.5` to first order
   (`dP/dSNR=φ(0)=0.399`). Vol sets the **level** (toward 0.5); the **edge** is what's
   vol-robust (≈0). Separate "level of P(Up)" from "existence of exploitable direction."
5. ✅ **Arcsine misattribution**: the arcsine law is about *fraction-of-time-positive*,
   not a count of sign changes. `crossing_count` reframed as a descriptive microstructure
   stat; a genuine arcsine quantity added (`fraction_time_above` vs `arcsine_cdf`).
6. ✅ **Crossing counts are sampling-frequency dependent** → `resample_last` to a fixed
   time grid before comparing; bucket by minute-of-window.

## HIGH-VALUE ADDITIONS
7. ✅ **Constructed mid** for all token stats: `token_mid_path` = `(yes+(1−no))/2` from
   time-aligned prints (cancels bounce). Raw `token_path` kept as sensitivity.
8. ✅ **YES+NO=1 no-arb check** (`yes_no_sum_stats`): distribution of the contemporaneous
   sum + fraction deviating >2¢.
9. ✅ **Confirmatory return tests**: Ljung-Box Q on `r` (martingale), on `r²`/`|r|` (vol
   clustering); Engle ARCH-LM; ADF + KPSS (stationarity) — via statsmodels.
10. ◑ **Effective-spread / bounce magnitude**: surfaced via `yes_no_sum` round-trip gap
    and the raw-vs-mid autocorr contrast (Roll estimator noted as future work).
11. ✅ **Terminal martingale convergence** (`terminal_convergence`): mean `|mid−outcome|`
    vs seconds-to-close → 0.
12. ✅ **Within-window term structure**: `E[|mid−0.5|]`, `Var(mid)` and crossings per
    30s bucket (notebook).
13. ✅ **Trade-intensity time profile** within the 300s window (notebook).
14. ✅ **Calibration upgrades**: calibrate against the **mid** (`opening_mid_prob`), add
    Brier score + per-bin Wilson CI; plot empirical `Φ(SNR)` vs realized frequency.
15. ✅ **Opening-price distribution** + test `H0: mean=0.5` with cluster-robust SE.
16. ✅ **Vol-vs-direction independence**: regress `|opening_mid−0.5|` on per-window `rvol`
    (≈zero slope ⇒ directionally vol-insensitive).
17. ✅ **Mid-based increment martingale probe**: `lag1_autocorr` + `variance_ratio` on the
    constructed-mid increments.

## REQUIRED CAVEATS
18. Executed-price-as-mid is bounce-contaminated (Roll 1984); negative raw-print
    increment autocorrelation and inflated crossing counts are partly microstructure, not
    predictable alpha. Headline uses the constructed mid; raw prints are labelled as such.
19. Pooling 1m returns across a multi-day span ignores intraday vol seasonality / overnight
    gaps — stated; the VR/ARCH conclusions are robust to it but the caveat is noted.
