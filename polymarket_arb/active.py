"""Active-exit variant of the double-dip strategy.

`tape_engine.TapeBacktester` holds every filled leg to settlement, so an unhedged
leg settles at $0 — the dominant loss. This engine instead **abandons an unhedged
leg after a timeout**: place resting bids at T on both legs; once the first leg
fills, wait `hold_timeout_s` for the second; if it doesn't come, sell the filled
leg at the prevailing price and cancel the other bid.

Look-ahead safety is structural: fills and the exit price use only trades at/before
the decision timestamp (`_price_at` scans `ts <= tau`); `resolution_yes` is read
only for positions actually held to settlement (a lock, or a leg whose exit time
falls past the window close).
"""
from __future__ import annotations

from dataclasses import dataclass

from .engine import ARB_LOCKED, NO_FILL, UNHEDGED_LOSS, UNHEDGED_WIN
from .trades import Trade, TradeWindow

EXIT_WIN = "EXIT_WIN"      # abandoned an unhedged leg at a gain vs T
EXIT_LOSS = "EXIT_LOSS"    # abandoned an unhedged leg at a (capped) loss vs T


@dataclass(frozen=True)
class ActiveConfig:
    threshold: float = 0.49
    hold_timeout_s: float = 30.0       # wait this long for the second leg before bailing
    exit_half_spread: float = 0.0      # haircut when selling on exit (cross to the bid)
    fee_bps: float = 0.0
    size: float = 1.0
    fill_mode: str = "trade_through"   # see tape_engine; 'sell_through' = conservative
    exclude_settlement_tail: bool = True
    convergence_guard_s: float = 0.0


@dataclass
class ActiveResult:
    slug: str
    asset: str
    start_ts: float
    end_ts: float
    resolution_yes: float | None
    cost: float
    payout: float          # settlement payout or exit proceeds
    pnl: float
    outcome: str
    exit_price: float | None = None


def _confine(w: TradeWindow, prints: list[Trade], cfg: ActiveConfig) -> list[Trade]:
    hi = w.close_ts - cfg.convergence_guard_s if cfg.exclude_settlement_tail else \
        (max((t.ts for t in prints), default=w.close_ts) + 1.0)
    return sorted((t for t in prints if w.open_ts <= t.ts < hi), key=lambda t: t.ts)


def _first_fill_ts(prints: list[Trade], T: float, mode: str) -> float | None:
    # Full marketable fill at the first threshold-touch (no partial-size accounting):
    # fine for the default unit size where TapeBacktester(participation=1) also fills
    # fully on the first qualifying print.
    for t in prints:
        if t.price <= T and (mode != "sell_through" or t.side == "SELL"):
            return t.ts
    return None


def _price_at(prints: list[Trade], tau: float) -> float | None:
    """Most recent traded price at or before tau (strictly causal)."""
    last = None
    for t in prints:
        if t.ts <= tau:
            last = t.price
        else:
            break
    return last


class ActiveExitBacktester:
    def __init__(self, cfg: ActiveConfig | None = None):
        self.cfg = cfg or ActiveConfig()

    def _fee(self, price: float) -> float:
        return (self.cfg.fee_bps / 1e4) * self.cfg.size * max(0.0, min(price, 1.0 - price))

    def run_window(self, w: TradeWindow) -> ActiveResult:
        cfg = self.cfg
        T, size = cfg.threshold, cfg.size
        yp = _confine(w, w.yes_trades, cfg)
        npr = _confine(w, w.no_trades, cfg)
        ty = _first_fill_ts(yp, T, cfg.fill_mode)
        tn = _first_fill_ts(npr, T, cfg.fill_mode)
        cost_leg = T * size + self._fee(T)
        res = w.resolution_yes

        def result(cost, payout, pnl, outcome, exit_price=None):
            return ActiveResult(slug=w.slug, asset=w.asset, start_ts=w.open_ts,
                                end_ts=w.close_ts, resolution_yes=res, cost=cost,
                                payout=payout, pnl=pnl, outcome=outcome, exit_price=exit_price)

        if ty is None and tn is None:
            return result(0.0, 0.0, 0.0, NO_FILL)

        # both legs filled and within the hold window -> keep the locked pair
        if ty is not None and tn is not None and abs(ty - tn) <= cfg.hold_timeout_s:
            cost = 2 * cost_leg
            payout = size                      # one side settles $1 whichever wins
            return result(cost, payout, payout - cost, ARB_LOCKED)

        # otherwise we hold only the first-filled leg, then bail at tf + timeout
        if ty is not None and tn is not None:
            first_leg, tf, legp = ("YES", ty, yp) if ty < tn else ("NO", tn, npr)
        else:
            first_leg, tf, legp = ("YES", ty, yp) if ty is not None else ("NO", tn, npr)
        exit_ts = tf + cfg.hold_timeout_s

        if exit_ts >= w.close_ts:              # cannot exit in time -> settle the leg
            if res is None:
                return result(cost_leg, float("nan"), float("nan"), "UNRESOLVED")
            won = (res >= 0.5) if first_leg == "YES" else (res < 0.5)
            payout = size if won else 0.0
            outcome = UNHEDGED_WIN if won else UNHEDGED_LOSS
            return result(cost_leg, payout, payout - cost_leg, outcome)

        px = _price_at(legp, exit_ts)
        if px is None:
            px = T
        sell_px = max(0.0, px - cfg.exit_half_spread)
        proceeds = sell_px * size - self._fee(sell_px)
        pnl = proceeds - cost_leg
        outcome = EXIT_WIN if pnl > 0 else EXIT_LOSS
        return result(cost_leg, proceeds, pnl, outcome, exit_price=sell_px)

    def run(self, windows: list[TradeWindow]) -> list[ActiveResult]:
        return [self.run_window(w) for w in windows]
