"""Performance metrics over a list of WindowResult."""
from __future__ import annotations

import math

import numpy as np

from .engine import (ARB_LOCKED, HEDGED_NEGEDGE, NO_FILL, UNHEDGED_LOSS,
                     UNHEDGED_WIN, WindowResult)


def equity_curve(results: list[WindowResult], starting_capital: float = 0.0):
    """(timestamps, equity) where equity = starting_capital + cumulative pnl."""
    ordered = sorted(results, key=lambda r: r.start_ts)
    ts = [r.start_ts for r in ordered]
    equity, run = [], starting_capital
    for r in ordered:
        run += 0.0 if math.isnan(r.pnl) else r.pnl
        equity.append(run)
    return ts, equity


def max_drawdown(equity: list[float]) -> float:
    """Largest peak-to-trough drop (>= 0)."""
    peak = -math.inf
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = max(mdd, peak - v)
    return mdd


def summary(results: list[WindowResult]) -> dict:
    scored = [r for r in results if not math.isnan(r.pnl)]
    n = len(scored)
    if n == 0:
        return {"n_windows": 0}

    pnls = np.array([r.pnl for r in scored])
    by = lambda label: sum(1 for r in scored if r.outcome == label)
    n_arb = by(ARB_LOCKED)
    n_hedged_neg = by(HEDGED_NEGEDGE)
    n_uwin = by(UNHEDGED_WIN)
    n_uloss = by(UNHEDGED_LOSS)
    n_nofill = by(NO_FILL)
    n_traded = n - n_nofill
    n_both = n_arb + n_hedged_neg
    n_wins = sum(1 for r in scored if r.pnl > 0)

    _, equity = equity_curve(scored)
    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(-pnls[pnls < 0].sum())

    return {
        "n_windows": n,
        "n_traded": n_traded,
        "total_pnl": float(pnls.sum()),
        "avg_pnl_per_window": float(pnls.mean()),
        "avg_pnl_per_trade": float(pnls.sum() / n_traded) if n_traded else 0.0,
        "win_rate": n_wins / n_traded if n_traded else 0.0,
        "fill_rate": n_traded / n,                 # >= 1 leg filled
        "both_fill_rate": n_both / n,              # hedged
        "arb_lock_rate": n_arb / n,                # locked profit
        "hedged_negedge_rate": n_hedged_neg / n,
        "unhedged_rate": (n_uwin + n_uloss) / n,
        "unhedged_loss_rate": n_uloss / n,         # the core risk realised
        "unhedged_win_rate": n_uwin / n,
        "no_fill_rate": n_nofill / n,
        "max_drawdown": max_drawdown(equity),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else math.inf,
        "sharpe_per_window": float(pnls.mean() / pnls.std()) if pnls.std() > 0 else 0.0,
        "counts": {ARB_LOCKED: n_arb, HEDGED_NEGEDGE: n_hedged_neg,
                   UNHEDGED_WIN: n_uwin, UNHEDGED_LOSS: n_uloss, NO_FILL: n_nofill},
    }
