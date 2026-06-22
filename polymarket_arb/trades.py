"""High-fidelity trade-tape data layer for 5-minute Up/Down markets.

The 1-minute mid from `data.PolymarketClient` is too coarse for this strategy:
the price action lives in the final ~2-3 minutes of the window, and the mid sits
at ~0.50 for the ~20h the market is open beforehand (so a [startDate, endDate]
pull is ~99% stale pre-market noise). Every executed trade, by contrast, settles
on Polygon and is exposed by the public data API at full transaction granularity:

    GET https://data-api.polymarket.com/trades?market=<conditionId>&limit=1000&offset=N

Facts verified live against the API (2026-06):
  * `limit` is hard-capped at 1000; the ONLY pagination is `offset`, returned
    newest-first (strictly descending timestamp). Page by offset += 1000 until a
    page shorter than `limit` -> that short page is the last.
  * There is NO server-side time filter (every time param is silently ignored),
    so fetch every trade for the conditionId and filter by timestamp client-side.
  * One conditionId returns BOTH outcome tokens in one feed; `price` is always the
    row token's own executed price regardless of BUY/SELL (YES + NO ~ 1.00).
  * The 5-minute trading window is the half-open [open, close) = [slug_ts,
    slug_ts+300). Trades before `open` (pre-market dust) and a settlement tail in
    the ~65s after `close` are excluded by default.
  * Offset paging is exact only for CLOSED markets (the feed is frozen); for an
    open market new trades shift the offset window between page fetches.

A single 5-minute BTC window holds ~2000-3000 real trades here -> ~500x the 5
points `prices-history` exposes. `transactionHash` is NOT a unique key (one tx can
match several makers), so dedup uses the full leg tuple.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .data import (CLOB, GAMMA, MarketWindow, PolymarketClient, _asset_from_slug,
                   _parse_resolution)

DATA_API = "https://data-api.polymarket.com"
WINDOW_SECONDS = 300
SETTLE_TAIL_S = 120            # trades land up to ~65s past close as positions unwind
PAGE = 1000                   # API hard cap on `limit`
MAX_OFFSET = 3000             # API: "max historical activity offset of 3000 exceeded"
                              # -> at most 4000 trades retrievable, NEWEST-first. Busier
                              # windows are truncated to their latest 4000 (a late-window
                              # bias); the on-chain eth_getLogs route has no such cap.

log = logging.getLogger("polymarket_arb.trades")


@dataclass(frozen=True)
class Trade:
    """One executed trade leg. `price` is this `token`'s own executed price."""
    ts: float
    token: str        # clobTokenId (asset)
    side: str         # 'BUY' | 'SELL' (taker side)
    price: float
    size: float
    tx: str
    outcome_index: int


@dataclass
class TradeWindow:
    """A 5-minute market as its full per-token executed-trade tape + resolution.

    `resolution_yes` is 1.0 if Up settled the winner, 0.0 if Down won, else None.
    Trades are time-sorted ascending and confined to [open_ts, close_ts).
    """
    slug: str
    asset: str
    open_ts: float
    close_ts: float
    yes_token: str
    no_token: str
    yes_trades: list[Trade]
    no_trades: list[Trade]
    resolution_yes: float | None
    truncated: bool = False       # True if the market exceeded the API offset cap

    @property
    def resolved(self) -> bool:
        return self.resolution_yes is not None

    @property
    def n_trades(self) -> int:
        return len(self.yes_trades) + len(self.no_trades)

    def to_dict(self) -> dict:
        def pack(ts):
            return [[t.ts, t.token, t.side, t.price, t.size, t.tx, t.outcome_index] for t in ts]
        return {
            "slug": self.slug, "asset": self.asset,
            "open_ts": self.open_ts, "close_ts": self.close_ts,
            "yes_token": self.yes_token, "no_token": self.no_token,
            "resolution_yes": self.resolution_yes, "truncated": self.truncated,
            "yes_trades": pack(self.yes_trades), "no_trades": pack(self.no_trades),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TradeWindow":
        def unpack(rows):
            return [Trade(ts=r[0], token=r[1], side=r[2], price=r[3], size=r[4],
                          tx=r[5], outcome_index=r[6]) for r in rows]
        return cls(
            slug=d["slug"], asset=d["asset"], open_ts=d["open_ts"], close_ts=d["close_ts"],
            yes_token=d["yes_token"], no_token=d["no_token"],
            resolution_yes=d["resolution_yes"], truncated=d.get("truncated", False),
            yes_trades=unpack(d["yes_trades"]), no_trades=unpack(d["no_trades"]),
        )


def _slug_window(slug: str, window_s: int = WINDOW_SECONDS) -> tuple[int, int]:
    """[open, close) for a `*-updown-5m-{unix_ts}` slug."""
    ts = int(slug.rsplit("-", 1)[1])
    return ts, ts + window_s


def _parse_trade(r: dict) -> Trade:
    return Trade(
        ts=float(r["timestamp"]), token=str(r["asset"]), side=r["side"],
        price=float(r["price"]), size=float(r["size"]),
        tx=str(r.get("transactionHash", "")), outcome_index=int(r.get("outcomeIndex", -1)),
    )


def _dedup_trades(trades: Iterable[Trade]) -> list[Trade]:
    """txHash is not unique (one tx can match several makers); key on the full leg."""
    seen: set = set()
    out: list[Trade] = []
    for t in trades:
        k = (t.tx, t.token, t.outcome_index, t.side, t.size, t.price)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


class TradeHistoryClient:
    """Pulls the full executed-trade tape per market. Composes `PolymarketClient`
    for discovery and its retry/throttle GET (no duplicate HTTP plumbing)."""

    def __init__(self, client: PolymarketClient | None = None,
                 data_api: str = DATA_API, cache_dir: str | Path = ".cache"):
        self.client = client or PolymarketClient(cache_dir=cache_dir)
        self.data_api = data_api.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.truncated = False

    def fetch_trades(self, condition_id: str, page: int = PAGE) -> list[Trade]:
        """Every retrievable trade for `condition_id` (both tokens), newest-first.

        Sets `self.truncated` True when the market has more trades than the API's
        offset cap (3000) lets us reach — i.e. we only got the latest ~4000.
        """
        raw: list[dict] = []
        offset = 0
        self.truncated = False
        while True:
            batch = self.client._get(self.data_api, "/trades",
                                     market=condition_id, limit=page, offset=offset)
            if not batch:
                break
            raw.extend(batch)
            if len(batch) < page:
                break
            offset += page
            if offset > MAX_OFFSET:           # next page would 400; stop before it
                self.truncated = True
                log.warning("offset cap hit for %s; tape truncated to latest %d trades",
                            condition_id, len(raw))
                break
        return _dedup_trades(_parse_trade(r) for r in raw)

    def build_window(self, event: dict, include_settlement_tail: bool = False,
                     window_s: int = WINDOW_SECONDS) -> TradeWindow | None:
        market = (event.get("markets") or [None])[0]
        if not market:
            return None
        try:
            tokens = json.loads(market["clobTokenIds"])
        except (KeyError, json.JSONDecodeError):
            return None
        if len(tokens) != 2:
            return None
        cond = market.get("conditionId")
        slug = event.get("slug")
        if not cond or not slug:
            return None

        yes_token, no_token = str(tokens[0]), str(tokens[1])
        open_ts, close_ts = _slug_window(slug, window_s)
        hi = close_ts + (SETTLE_TAIL_S if include_settlement_tail else 0)

        all_trades = self.fetch_trades(cond)
        truncated = self.truncated
        in_win = [t for t in all_trades if open_ts <= t.ts < hi]
        yes_tr = sorted((t for t in in_win if t.token == yes_token), key=lambda x: x.ts)
        no_tr = sorted((t for t in in_win if t.token == no_token), key=lambda x: x.ts)
        return TradeWindow(
            slug=slug, asset=_asset_from_slug(slug), open_ts=open_ts, close_ts=close_ts,
            yes_token=yes_token, no_token=no_token,
            yes_trades=yes_tr, no_trades=no_tr,
            resolution_yes=_parse_resolution(market), truncated=truncated,
        )

    def fetch_event_by_slug(self, slug: str) -> dict | None:
        evs = self.client._get(self.client.gamma, "/events", slug=slug)
        return evs[0] if isinstance(evs, list) and evs else None

    def _latest_cached_ts(self, asset: str) -> int | None:
        """Newest cached window timestamp for an asset (no network)."""
        best = None
        for p in self.cache_dir.glob(f"trades-{asset}-updown-5m-*.json"):
            try:
                ts = int(p.stem.rsplit("-", 1)[1])
            except ValueError:
                continue
            if best is None or ts > best:
                best = ts
        return best

    def load_history(self, asset: str, count: int, end_ts: int | None = None,
                     use_cache: bool = True, max_gap: int = 40,
                     include_settlement_tail: bool = False,
                     cache_only: bool = False) -> list[TradeWindow]:
        """Walk slug timestamps BACKWARD from the latest window, fetching each by
        slug. Bypasses the Gamma discovery offset cap (~2000), so history depth is
        unbounded. `max_gap` consecutive missing/unresolved/empty slugs ends the walk.
        Caches per slug (shared with `load_dataset`). `cache_only` reads only the disk
        cache (no network, no clock-chasing) — used for reproducible analysis."""
        if end_ts is None:
            if cache_only:
                end_ts = self._latest_cached_ts(asset)
                if end_ts is None:
                    return []
            else:
                evs = self.client.discover_5m_events(asset=asset, closed=True, max_events=1)
                if not evs:
                    return []
                end_ts = int(evs[0]["slug"].rsplit("-", 1)[1])
        out: list[TradeWindow] = []
        ts = int(end_ts)
        gap = 0
        while len(out) < count and gap < max_gap and ts > 0:
            slug = f"{asset}-updown-5m-{ts}"
            ts -= WINDOW_SECONDS
            cache_path = self.cache_dir / f"trades-{slug}.json"
            if use_cache and cache_path.exists():
                w = TradeWindow.from_dict(json.loads(cache_path.read_text()))
            elif cache_only:
                w = None                          # offline: uncached slug = gap, never fetch
            else:
                try:                              # tolerate a transient API timeout/error
                    ev = self.fetch_event_by_slug(slug)
                    w = self.build_window(ev, include_settlement_tail=include_settlement_tail) if ev else None
                    if w is not None and use_cache:
                        cache_path.write_text(json.dumps(w.to_dict()))
                except Exception as ex:           # a single hiccup must not kill the walk
                    log.warning("fetch failed for %s (%s); treating as gap", slug, ex)
                    w = None
            if w is None or not w.resolved or w.n_trades == 0:
                gap += 1
                continue
            gap = 0
            out.append(w)
        log.info("load_history %s: %d windows (walked back to ts=%d)", asset, len(out), ts)
        return out

    def load_dataset(self, asset: str | None = None, max_windows: int = 80,
                     resolved_only: bool = True, use_cache: bool = True,
                     include_settlement_tail: bool = False) -> list[TradeWindow]:
        """Assemble a trade-tape dataset of closed 5-minute windows, cached per slug."""
        events = self.client.discover_5m_events(asset=asset, closed=True,
                                                max_events=max_windows * 2)
        windows: list[TradeWindow] = []
        for ev in events:
            if len(windows) >= max_windows:
                break
            slug = ev["slug"]
            cache_path = self.cache_dir / f"trades-{slug}.json"
            if use_cache and cache_path.exists():
                w = TradeWindow.from_dict(json.loads(cache_path.read_text()))
            else:
                w = self.build_window(ev, include_settlement_tail=include_settlement_tail)
                if w is not None and use_cache:
                    cache_path.write_text(json.dumps(w.to_dict()))
            if w is None:
                continue
            if resolved_only and not w.resolved:
                continue
            windows.append(w)
        log.info("loaded %d trade-tape windows (asset=%s)", len(windows), asset or "all")
        return windows
