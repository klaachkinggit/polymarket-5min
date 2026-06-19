"""Cross-window momentum / autocorrelation strategy.

Hypothesis: consecutive 5-minute Up/Down outcomes are serially correlated — if the
previous window resolved Up, the next is more likely Up ("momentum"; the opposite
bet is "reversal"). The signal for window N is the resolved outcome of the
immediately preceding *consecutive* window (N-1 closes before N opens, so the
signal is known at entry — no look-ahead). We bet the signalled side at window N's
OPENING executed price and hold to settlement.

Edge requires the market to MISPRICE serial correlation: a profitable momentum bet
needs entry_price < P(correct). If the book already prices the autocorrelation,
the opening price absorbs it and EV <= 0.

Entry realism (audit fix): a market BUY can only fill at the ASK. An executed SELL
print is a taker hitting the resting BID, so entering at a SELL print understates
cost. By default (`entry_side="buy"`) we enter at the earliest in-window BUY
(ask-lift) print — real evidence the ask was takeable at that price — never a
SELL/bid print. `entry_side="any"` restores the older (optimistic) behavior for
contrast. Truncated windows (tape hit the API offset cap, so the earliest retained
print is not the true open) are excluded by default.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .trades import TradeWindow

WINDOW_SECONDS = 300


@dataclass(frozen=True)
class MomentumConfig:
    direction: str = "momentum"     # "momentum" (bet same as prev) | "reversal" (opposite)
    fee_bps: float = 0.0
    size: float = 1.0
    entry_half_spread: float = 0.0  # added on top of the entry quote (extra slippage stress)
    entry_side: str = "buy"         # "buy": earliest BUY (ask-lift) print [realistic] | "any": earliest print
    exclude_truncated: bool = True  # drop windows whose tape hit the API offset cap (shifted open)
    require_both_quotes: bool = False  # bet only pairs where BOTH tokens have an entry quote
                                       # (outcome-independent sample; de-biases the win-rate)


@dataclass
class MomentumResult:
    slug: str
    asset: str
    start_ts: float
    prev_up: float          # outcome of the signalling window
    bet_up: bool
    entry_price: float
    resolution_yes: float
    pnl: float
    correct: bool


def _ordered_by_asset(windows: list[TradeWindow]) -> dict[str, list[TradeWindow]]:
    by: dict[str, list[TradeWindow]] = {}
    for w in sorted(windows, key=lambda w: (w.asset, w.open_ts)):
        if w.resolved:
            by.setdefault(w.asset, []).append(w)
    return by


def _consecutive_pairs(windows: list[TradeWindow]):
    """Yield (prev, cur) for windows exactly WINDOW_SECONDS apart within an asset."""
    for ws in _ordered_by_asset(windows).values():
        for a, b in zip(ws, ws[1:]):
            if abs(b.open_ts - a.open_ts - WINDOW_SECONDS) < 1.0:
                yield a, b


def _opening_quote(w: TradeWindow, bet_up: bool, taker_side: str | None = None) -> float | None:
    """Earliest in-window executed price of the bet token, optionally filtered to a
    taker side. `taker_side="BUY"` => earliest ask-lift print (the price a market BUY
    would have paid); None => earliest print regardless of side (optimistic)."""
    trades = w.yes_trades if bet_up else w.no_trades
    inwin = [t for t in trades if w.open_ts <= t.ts < w.close_ts
             and (taker_side is None or t.side == taker_side)]
    return min(inwin, key=lambda t: t.ts).price if inwin else None


def autocorr_stats(windows: list[TradeWindow]) -> dict:
    """Lag-1 serial-correlation diagnostics over consecutive window pairs."""
    pairs = [(a.resolution_yes, b.resolution_yes) for a, b in _consecutive_pairs(windows)]
    n = len(pairs)
    if n == 0:
        return {"n_pairs": 0}
    cur = [c for _, c in pairs]
    base = sum(cur) / n
    repeat = sum(1 for p, c in pairs if p == c) / n
    uu = [c for p, c in pairs if p == 1.0]
    ud = [c for p, c in pairs if p == 0.0]
    # Pearson lag-1 autocorrelation on the +/-1 outcome series
    xp = [1.0 if p == 1.0 else -1.0 for p, _ in pairs]
    xc = [1.0 if c == 1.0 else -1.0 for _, c in pairs]
    mp, mc = sum(xp) / n, sum(xc) / n
    cov = sum((a - mp) * (b - mc) for a, b in zip(xp, xc))
    vp = sum((a - mp) ** 2 for a in xp)
    vc = sum((b - mc) ** 2 for b in xc)
    r = cov / math.sqrt(vp * vc) if vp > 0 and vc > 0 else 0.0
    return {
        "n_pairs": n,
        "base_up_rate": base,
        "repeat_rate": repeat,                       # P(outcome repeats prev)
        "p_up_after_up": (sum(uu) / len(uu)) if uu else float("nan"),
        "p_up_after_down": (sum(ud) / len(ud)) if ud else float("nan"),
        "lag1_autocorr": r,
    }


class MomentumBacktester:
    def __init__(self, cfg: MomentumConfig | None = None):
        self.cfg = cfg or MomentumConfig()

    def run(self, windows: list[TradeWindow]) -> list[MomentumResult]:
        cfg = self.cfg
        taker = "BUY" if cfg.entry_side == "buy" else None
        self.n_skipped_truncated = 0   # tape hit the offset cap -> open price unreliable
        self.n_skipped_nofill = 0      # bet token never lifted the ask in-window -> no entry
        self.n_skipped_oneside = 0     # require_both_quotes: opposite token had no quote
        out: list[MomentumResult] = []
        for prev, cur in _consecutive_pairs(windows):
            if cfg.exclude_truncated and cur.truncated:
                self.n_skipped_truncated += 1
                continue
            bet_up = (prev.resolution_yes == 1.0) if cfg.direction == "momentum" \
                else (prev.resolution_yes == 0.0)
            ask = _opening_quote(cur, bet_up, taker)
            if ask is None:
                self.n_skipped_nofill += 1
                continue
            if cfg.require_both_quotes and _opening_quote(cur, not bet_up, taker) is None:
                self.n_skipped_oneside += 1
                continue
            entry = min(1.0, ask + cfg.entry_half_spread)   # fill at the ask (+ stress)
            fee = (cfg.fee_bps / 1e4) * cfg.size * max(0.0, min(entry, 1.0 - entry))
            correct = (cur.resolution_yes == 1.0) == bet_up
            payout = cfg.size if correct else 0.0
            out.append(MomentumResult(
                slug=cur.slug, asset=cur.asset, start_ts=cur.open_ts,
                prev_up=prev.resolution_yes, bet_up=bet_up, entry_price=entry,
                resolution_yes=cur.resolution_yes,
                pnl=payout - entry * cfg.size - fee, correct=correct))
        return out


def momentum_summary(results: list[MomentumResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"n_bets": 0}
    pnl = sum(r.pnl for r in results)
    return {
        "n_bets": n,
        "win_rate": sum(1 for r in results if r.correct) / n,
        "total_pnl": pnl,
        "avg_pnl_per_bet": pnl / n,
        "avg_entry_price": sum(r.entry_price for r in results) / n,
    }
