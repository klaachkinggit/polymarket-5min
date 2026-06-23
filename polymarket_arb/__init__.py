"""Polymarket 5-minute Up/Down double-dip arbitrage backtester."""
from .active import (EXIT_LOSS, EXIT_WIN, ActiveConfig, ActiveExitBacktester,
                     ActiveResult)
from .collector import BookCollector, discover_live_windows
from .data import MarketWindow, PolymarketClient, Tick
from .engine import (ARB_LOCKED, HEDGED_NEGEDGE, NO_FILL, UNHEDGED_LOSS,
                     UNHEDGED_WIN, ArbBacktester, ExecConfig, Fill, WindowResult)
from .metrics import equity_curve, max_drawdown, summary
from .momentum import (MomentumBacktester, MomentumConfig, MomentumResult,
                       autocorr_stats, momentum_summary)
from .optimize import (param_grid, tape_param_grid, tape_threshold_sweep,
                       threshold_sweep)
from .reversal_analysis import (autocorr_table, block_bootstrap,
                                clustered_tstat, friction_grid, load_all,
                                naive_tstat, sample_decay)
from .dynamics import (SPOT_ASSETS, all_spot_returns, arcsine_cdf, brier_score,
                       calibration_curve, crossing_count, digital_snr,
                       fraction_time_above, lag1_autocorr, load_spot, moments,
                       opening_mid_prob, opening_token_prob, spot_resolution_agreement,
                       terminal_convergence, token_mid_path, token_path,
                       variance_ratio, window_spot_features, yes_no_sum_stats)
from .regimes import (REGIMES, label_terciles, regime_performance, regime_rows,
                      strategy_pnls, vol_by_hour, vol_persistence)
from .synth import generate_dataset, generate_window
from .tape_engine import TapeBacktester, TapeConfig, TapeFill, TapeResult
from .trades import Trade, TradeHistoryClient, TradeWindow

__all__ = [
    "MarketWindow", "PolymarketClient", "Tick",
    "ArbBacktester", "ExecConfig", "Fill", "WindowResult",
    "ARB_LOCKED", "HEDGED_NEGEDGE", "NO_FILL", "UNHEDGED_LOSS", "UNHEDGED_WIN",
    "equity_curve", "max_drawdown", "summary",
    "param_grid", "threshold_sweep", "tape_param_grid", "tape_threshold_sweep",
    "generate_dataset", "generate_window",
    "Trade", "TradeHistoryClient", "TradeWindow",
    "TapeBacktester", "TapeConfig", "TapeFill", "TapeResult",
    "ActiveConfig", "ActiveExitBacktester", "ActiveResult", "EXIT_WIN", "EXIT_LOSS",
    "BookCollector", "discover_live_windows",
    "MomentumBacktester", "MomentumConfig", "MomentumResult",
    "autocorr_stats", "momentum_summary",
    "load_all", "naive_tstat", "clustered_tstat", "block_bootstrap",
    "autocorr_table", "friction_grid", "sample_decay",
    "SPOT_ASSETS", "all_spot_returns", "arcsine_cdf", "brier_score",
    "calibration_curve", "crossing_count", "digital_snr", "fraction_time_above",
    "lag1_autocorr", "load_spot", "moments", "opening_mid_prob", "opening_token_prob",
    "spot_resolution_agreement", "terminal_convergence", "token_mid_path",
    "token_path", "variance_ratio", "window_spot_features", "yes_no_sum_stats",
    "REGIMES", "label_terciles", "regime_performance", "regime_rows",
    "strategy_pnls", "vol_by_hour", "vol_persistence",
]
