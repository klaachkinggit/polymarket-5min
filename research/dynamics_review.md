# Dynamics-EDA & Notebook-Split Review

*Adversarial multi-agent review (4 lenses: methodology, look-ahead, honesty, arb-split →
adversarial verify → synthesis). 26 findings, all verified. All actionable items below are
fixed. ✅*

## Verdict
**Methodology sound; split correct.** The "no tradeable directional edge" conclusion is
independently load-bearing (near-zero SNR, calibration Brier 0.220 vs 0.25, the YES+NO
overround ≈1.09, mid-vs-raw increment autocorrelation on symmetric footing, arcsine
fraction-of-time behaviour) and does not depend on any defective piece. The statistical
machinery (Lo-MacKinlay VR with (1−k/n)+het-robust z*, clustered-t / block-bootstrap,
Ljung-Box/ARCH, Wilson CI, digital-SNR) is correct and numerically validated. Every
look-ahead lens came back clean — `resolution_yes` is used only as an outcome label, never
as a predictor or entry input. The arb notebook is genuinely tape-only (no mid/`prices-history`
path); both notebooks execute end-to-end. Defects were reporting/figure/wording only — none
touch trade logic or money.

## Fixed
- ✅ **H1 — `terminal_convergence` bucket collapse** (`dynamics.py`): descending buckets +
  break-on-first dumped every point into the 240s bucket → figure showed one point. Now
  ascending `(10,30,60,120,180,240)` (disjoint bands); convergence renders correctly
  (mean|mid−outcome| 0.41→0.19 as ttc 240→10s). Regression test added.
- ✅ **M1 — stale hardcoded "SNR ≈ 0.05"** in the verdict contradicted the computed ≈−0.02.
  Verdict now prints the computed mean magnitude (≈0.022); notebook cells updated.
- ✅ **M2 — crossing comparison** mixed 10s-resampled mid vs un-resampled raw prints
  (conflated bounce with sampling density). Both series now on the same 10s grid.
- ✅ **M3 — notebook printed "flat"** for the vol-vs-direction corr while the markdown said
  "weak"; notebook wording reconciled.
- ✅ **L1 — arcsine overlay** softened to "qualitatively consistent / arcsine-like" (level
  fixed at 0.5 vs opening ~0.49; bounded/absorbing martingale, not free BM).
- ✅ **L2 — vol-vs-|opening dev| regression** uses full-window realized vol vs the opening
  price; relabelled as contemporaneous/descriptive (not ex-ante, not a signal, not a leak).

## Clean (verified, no change needed)
Look-ahead across `window_spot_features` (in-window bars only), `opening_mid_prob` (first
~30s), calibration/terminal (resolution as label only), and the reversal `friction_grid`
reuse. Arb notebook contains no mid/poor-data path. Dynamics notebook does not duplicate
the arb double-dip.
