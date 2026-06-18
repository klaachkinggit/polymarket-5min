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
]
