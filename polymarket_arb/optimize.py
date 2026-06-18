"""Threshold / parameter sweeps for optimisation plots."""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .data import MarketWindow
from .engine import ArbBacktester, ExecConfig
from .metrics import summary
from .tape_engine import TapeBacktester, TapeConfig
from .trades import TradeWindow


def threshold_sweep(windows: list[MarketWindow], thresholds,
                    base_cfg: ExecConfig | None = None) -> pd.DataFrame:
    """One row per threshold: net profit, fill rate, lock/loss rates, etc."""
    base_cfg = base_cfg or ExecConfig()
    rows = []
    for thr in thresholds:
        bt = ArbBacktester(replace(base_cfg, threshold=float(thr)))
        s = summary(bt.run(windows))
        rows.append({
            "threshold": float(thr),
            "net_profit": s.get("total_pnl", 0.0),
            "avg_pnl_per_window": s.get("avg_pnl_per_window", 0.0),
            "fill_rate": s.get("fill_rate", 0.0),
            "both_fill_rate": s.get("both_fill_rate", 0.0),
            "arb_lock_rate": s.get("arb_lock_rate", 0.0),
            "unhedged_loss_rate": s.get("unhedged_loss_rate", 0.0),
            "win_rate": s.get("win_rate", 0.0),
            "max_drawdown": s.get("max_drawdown", 0.0),
            "profit_factor": s.get("profit_factor", 0.0),
        })
    return pd.DataFrame(rows)


def param_grid(windows: list[MarketWindow], thresholds, slippages,
               base_cfg: ExecConfig | None = None,
               metric: str = "total_pnl") -> pd.DataFrame:
    """2-D grid (threshold x slippage) of one metric — pivot for a heatmap."""
    base_cfg = base_cfg or ExecConfig()
    rows = []
    for thr in thresholds:
        for slip in slippages:
            bt = ArbBacktester(replace(base_cfg, threshold=float(thr), slippage=float(slip)))
            s = summary(bt.run(windows))
            rows.append({"threshold": float(thr), "slippage": float(slip),
                         "value": s.get(metric, 0.0)})
    df = pd.DataFrame(rows)
    return df.pivot(index="slippage", columns="threshold", values="value")


# --- trade-tape engine sweeps ----------------------------------------------
def tape_threshold_sweep(windows: list[TradeWindow], thresholds,
                         base_cfg: TapeConfig | None = None) -> pd.DataFrame:
    """One row per threshold over the real trade-tape fill model."""
    base_cfg = base_cfg or TapeConfig()
    rows = []
    for thr in thresholds:
        bt = TapeBacktester(replace(base_cfg, threshold=float(thr)))
        s = summary(bt.run(windows))
        rows.append({
            "threshold": float(thr),
            "net_profit": s.get("total_pnl", 0.0),
            "avg_pnl_per_window": s.get("avg_pnl_per_window", 0.0),
            "fill_rate": s.get("fill_rate", 0.0),
            "both_fill_rate": s.get("both_fill_rate", 0.0),
            "arb_lock_rate": s.get("arb_lock_rate", 0.0),
            "unhedged_loss_rate": s.get("unhedged_loss_rate", 0.0),
            "win_rate": s.get("win_rate", 0.0),
            "max_drawdown": s.get("max_drawdown", 0.0),
            "profit_factor": s.get("profit_factor", 0.0),
        })
    return pd.DataFrame(rows)


def tape_param_grid(windows: list[TradeWindow], thresholds, fee_bps_grid,
                    base_cfg: TapeConfig | None = None,
                    metric: str = "total_pnl") -> pd.DataFrame:
    """2-D grid (threshold x fee_bps) of one metric — pivot for a heatmap.

    Slippage isn't a tape concept (we fill at our limit T), so the second axis is
    trading friction (fee in bps) — the realistic knob that erodes the edge.
    """
    base_cfg = base_cfg or TapeConfig()
    rows = []
    for thr in thresholds:
        for fee in fee_bps_grid:
            bt = TapeBacktester(replace(base_cfg, threshold=float(thr), fee_bps=float(fee)))
            s = summary(bt.run(windows))
            rows.append({"threshold": float(thr), "fee_bps": float(fee),
                         "value": s.get(metric, 0.0)})
    df = pd.DataFrame(rows)
    return df.pivot(index="fee_bps", columns="threshold", values="value")
