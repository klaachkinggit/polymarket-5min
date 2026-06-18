"""Double-dip arbitrage backtester for 5-minute Up/Down binary markets.

Strategy (per window): independently watch each leg's ASK. The first time a
leg's ask falls to <= `threshold`, buy `size` shares of that leg. If BOTH legs
fill across the window for a combined cost < $1, one side must settle at $1 so
the position is a locked arbitrage. If only one leg fills, the position is
unhedged and settles at $1 (win) or $0 (loss).

Look-ahead safety is STRUCTURAL: `simulate()` receives only the tick path and
never the resolution; `_settle()` is the sole reader of `MarketWindow.resolution_yes`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .data import MarketWindow, Tick

# window outcome labels
NO_FILL = "NO_FILL"
ARB_LOCKED = "ARB_LOCKED"          # both legs, cost < notional -> guaranteed profit
HEDGED_NEGEDGE = "HEDGED_NEGEDGE"  # both legs, cost >= notional -> hedged but no edge
UNHEDGED_WIN = "UNHEDGED_WIN"      # one leg, settled the winner
UNHEDGED_LOSS = "UNHEDGED_LOSS"    # one leg, settled the loser


@dataclass(frozen=True)
class ExecConfig:
    """Execution assumptions. `threshold` is compared against the ASK.

    ask        = mid + half_spread
    fill_price = ask + slippage
    fee        = (fee_bps / 1e4) * size * min(fill_price, 1 - fill_price)   # Polymarket-style
    """
    threshold: float = 0.45
    half_spread: float = 0.01
    slippage: float = 0.0
    fee_bps: float = 0.0
    size: float = 1.0


@dataclass(frozen=True)
class Fill:
    leg: str          # 'YES' | 'NO'
    ts: float
    ask: float
    fill_price: float
    fee: float
    cost: float       # fill_price * size + fee


@dataclass
class WindowResult:
    slug: str
    asset: str
    start_ts: float
    end_ts: float
    yes_fill: Fill | None
    no_fill: Fill | None
    resolution_yes: float | None
    cost: float
    payout: float
    pnl: float
    outcome: str
    state_path: list[str] = field(default_factory=list)

    @property
    def n_legs(self) -> int:
        return int(self.yes_fill is not None) + int(self.no_fill is not None)


class ArbBacktester:
    def __init__(self, cfg: ExecConfig | None = None):
        self.cfg = cfg or ExecConfig()

    # ---- fill logic (no resolution in scope) ------------------------------
    def _try_fill(self, leg: str, mid: float, ts: float) -> Fill | None:
        cfg = self.cfg
        ask = mid + cfg.half_spread
        if ask > cfg.threshold:
            return None
        fill_price = ask + cfg.slippage
        fee = (cfg.fee_bps / 1e4) * cfg.size * max(0.0, min(fill_price, 1.0 - fill_price))
        return Fill(leg=leg, ts=ts, ask=ask, fill_price=fill_price, fee=fee,
                    cost=fill_price * cfg.size + fee)

    def simulate(self, ticks: list[Tick]) -> tuple[Fill | None, Fill | None, list[str]]:
        """Sequentially process ticks. Returns (yes_fill, no_fill, state_path).

        Pure function of the tick PATH only — it has no access to the eventual
        resolution, which makes look-ahead bias on fills structurally impossible.

        Precondition: `ticks` are time-ordered (guaranteed by `data._merge_histories`
        and `synth.generate_window`); the 'past + current only' property relies on it.
        """
        yes_fill: Fill | None = None
        no_fill: Fill | None = None
        path = ["WAITING"]
        for tk in ticks:
            if yes_fill is None:
                f = self._try_fill("YES", tk.yes_mid, tk.ts)
                if f is not None:
                    yes_fill = f
                    path.append(f"YES_FILLED@{f.fill_price:.3f}")
            if no_fill is None:
                f = self._try_fill("NO", tk.no_mid, tk.ts)
                if f is not None:
                    no_fill = f
                    path.append(f"NO_FILLED@{f.fill_price:.3f}")
            if yes_fill is not None and no_fill is not None:
                path.append("HEDGED")
                break  # nothing left to fill; not look-ahead
        return yes_fill, no_fill, path

    # ---- settlement (only reader of resolution) ---------------------------
    def _settle(self, w: MarketWindow, yes_fill: Fill | None,
                no_fill: Fill | None, path: list[str]) -> WindowResult:
        cfg = self.cfg
        res_yes = w.resolution_yes
        cost = (yes_fill.cost if yes_fill else 0.0) + (no_fill.cost if no_fill else 0.0)

        if res_yes is None:
            payout = float("nan")
            pnl = float("nan")
            outcome = NO_FILL if (yes_fill is None and no_fill is None) else "UNRESOLVED"
        else:
            payout = 0.0
            if yes_fill is not None:
                payout += res_yes * cfg.size
            if no_fill is not None:
                payout += (1.0 - res_yes) * cfg.size
            pnl = payout - cost
            outcome = self._classify(yes_fill, no_fill, res_yes, cost)

        return WindowResult(
            slug=w.slug, asset=w.asset, start_ts=w.start_ts, end_ts=w.end_ts,
            yes_fill=yes_fill, no_fill=no_fill, resolution_yes=res_yes,
            cost=cost, payout=payout, pnl=pnl, outcome=outcome, state_path=path,
        )

    def _classify(self, yes_fill: Fill | None, no_fill: Fill | None,
                  res_yes: float, cost: float) -> str:
        n = int(yes_fill is not None) + int(no_fill is not None)
        if n == 0:
            return NO_FILL
        if n == 2:
            # both legs settle to $1 total; edge exists iff we paid < notional
            return ARB_LOCKED if cost < self.cfg.size else HEDGED_NEGEDGE
        leg_won = (res_yes >= 0.5) if yes_fill is not None else (res_yes < 0.5)
        return UNHEDGED_WIN if leg_won else UNHEDGED_LOSS

    # ---- public ----------------------------------------------------------
    def run_window(self, w: MarketWindow) -> WindowResult:
        yes_fill, no_fill, path = self.simulate(w.ticks)
        return self._settle(w, yes_fill, no_fill, path)

    def run(self, windows: list[MarketWindow]) -> list[WindowResult]:
        return [self.run_window(w) for w in windows]
