"""Trade-tape backtester for the double-dip strategy.

Unlike `engine.ArbBacktester` (which reconstructs an ask from a 1-minute mid),
this consumes the full executed-trade tape (`trades.TradeWindow`) and fills on
PROVEN marketable liquidity only.

Fill model (designed against the real tape; see research/findings.json):
  * A resting BUY at threshold T fills ONLY when a SELL print on that token
    prints at price <= T. A SELL means a taker hit a resting bid at that price,
    so the book was bid there and our resting bid at T (>= that price) would have
    been hit first by price-time priority. BUY prints (ask lifts) do NOT fill a
    resting BUY — using them is the classic look-ahead/optimism error.
  * Execution price is our limit T (we are the passive order; we get our posted
    price, never the deeper print). Conservative on price.
  * YES and NO are independent streams: each leg fills on its own clock, so the
    temporal double-dip (two legs at different seconds, or one never) is native.
  * Fillable size is a fraction (`participation`) of the triggering SELL print's
    size, accumulated across qualifying prints — we never see resting depth, only
    realized taker volume, so this is a lower-bound proxy.
  * Settlement-tail prints (t >= close_ts) are post-resolution convergence to
    {0,1} and are excluded; `convergence_guard_s` optionally drops the last few
    in-window seconds too.

Look-ahead safety is structural: `_fill_leg` sees only (ts, side, price, size);
`resolution_yes` is read solely in `_settle`, after all fills are decided.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .engine import (ARB_LOCKED, HEDGED_NEGEDGE, NO_FILL, UNHEDGED_LOSS,
                     UNHEDGED_WIN)
from .trades import Trade, TradeWindow


@dataclass(frozen=True)
class TapeConfig:
    threshold: float = 0.45
    fee_bps: float = 0.0
    size: float = 1.0
    participation: float = 1.0          # fraction of a SELL print's size we can capture
    exclude_settlement_tail: bool = True
    convergence_guard_s: float = 0.0    # also drop SELLs in the last N in-window seconds


@dataclass(frozen=True)
class TapeFill:
    leg: str            # 'YES' | 'NO'
    ts: float           # first qualifying SELL print
    trigger_price: float  # that print's price (proven hittable level, <= threshold)
    fill_price: float   # our limit T
    size: float         # actually filled (<= cfg.size)
    fee: float
    cost: float         # fill_price * size + fee


@dataclass
class TapeResult:
    slug: str
    asset: str
    start_ts: float
    end_ts: float
    yes_fill: TapeFill | None
    no_fill: TapeFill | None
    resolution_yes: float | None
    cost: float
    payout: float
    pnl: float
    outcome: str

    @property
    def n_legs(self) -> int:
        return int(self.yes_fill is not None) + int(self.no_fill is not None)


class TapeBacktester:
    def __init__(self, cfg: TapeConfig | None = None):
        self.cfg = cfg or TapeConfig()

    # ---- fill (no resolution in scope) ------------------------------------
    def _window_prints(self, w: TradeWindow, prints: list[Trade]) -> list[Trade]:
        if self.cfg.exclude_settlement_tail:
            hi = w.close_ts - self.cfg.convergence_guard_s
            kept = (t for t in prints if w.open_ts <= t.ts < hi)
        else:
            kept = (t for t in prints if w.open_ts <= t.ts)   # include whatever tail is stored
        return sorted(kept, key=lambda t: t.ts)

    def _fill_leg(self, leg: str, prints: list[Trade]) -> TapeFill | None:
        cfg = self.cfg
        remaining = cfg.size
        filled = 0.0
        first_ts: float | None = None
        trigger_price: float | None = None
        for t in prints:
            if t.side != "SELL" or t.price > cfg.threshold:
                continue
            if first_ts is None:
                first_ts, trigger_price = t.ts, t.price
            take = min(remaining, cfg.participation * t.size)
            filled += take
            remaining -= take
            if remaining <= 1e-9:
                break
        if filled <= 1e-9:
            return None
        fill_price = cfg.threshold
        fee = (cfg.fee_bps / 1e4) * filled * max(0.0, min(fill_price, 1.0 - fill_price))
        return TapeFill(leg=leg, ts=first_ts, trigger_price=trigger_price,
                        fill_price=fill_price, size=filled, fee=fee,
                        cost=fill_price * filled + fee)

    # ---- settlement (only reader of resolution) ---------------------------
    def _settle(self, w: TradeWindow, yes_fill: TapeFill | None,
                no_fill: TapeFill | None) -> TapeResult:
        res = w.resolution_yes
        cost = (yes_fill.cost if yes_fill else 0.0) + (no_fill.cost if no_fill else 0.0)
        n = int(yes_fill is not None) + int(no_fill is not None)

        if res is None:
            payout = math.nan
            pnl = math.nan
            outcome = NO_FILL if n == 0 else "UNRESOLVED"
        else:
            payout = 0.0
            if yes_fill is not None:
                payout += res * yes_fill.size
            if no_fill is not None:
                payout += (1.0 - res) * no_fill.size
            pnl = payout - cost
            outcome = self._classify(yes_fill, no_fill, res, cost)

        return TapeResult(
            slug=w.slug, asset=w.asset, start_ts=w.open_ts, end_ts=w.close_ts,
            yes_fill=yes_fill, no_fill=no_fill, resolution_yes=res,
            cost=cost, payout=payout, pnl=pnl, outcome=outcome,
        )

    def _classify(self, yes_fill: TapeFill | None, no_fill: TapeFill | None,
                  res: float, cost: float) -> str:
        n = int(yes_fill is not None) + int(no_fill is not None)
        if n == 0:
            return NO_FILL
        if n == 2:
            # holding both: whatever the outcome, you collect $1*size on one side.
            # guaranteed payout = the smaller leg; locked profit iff cost < that.
            guaranteed = min(yes_fill.size, no_fill.size)
            return ARB_LOCKED if cost < guaranteed else HEDGED_NEGEDGE
        leg_won = (res >= 0.5) if yes_fill is not None else (res < 0.5)
        return UNHEDGED_WIN if leg_won else UNHEDGED_LOSS

    # ---- public -----------------------------------------------------------
    def run_window(self, w: TradeWindow) -> TapeResult:
        yes_fill = self._fill_leg("YES", self._window_prints(w, w.yes_trades))
        no_fill = self._fill_leg("NO", self._window_prints(w, w.no_trades))
        return self._settle(w, yes_fill, no_fill)

    def run(self, windows: list[TradeWindow]) -> list[TapeResult]:
        return [self.run_window(w) for w in windows]
