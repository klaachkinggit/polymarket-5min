"""Polymarket data access for 5-minute crypto Up/Down markets.

Two real APIs are used:
  * Gamma  (https://gamma-api.polymarket.com)  — market discovery + resolution.
  * CLOB   (https://clob.polymarket.com)        — historical price series.

Hard constraints discovered against the live API (2026-06):
  * 5-minute markets have slug `{asset}-updown-5m-{unix_ts}` and live under
    `tag_slug=crypto`. Each event holds one market with two CLOB tokens
    (`clobTokenIds[0]`=Up/YES, `[1]`=Down/NO).
  * Resolution is the market's `outcomePrices`: ["1","0"] => Up won, ["0","1"]
    => Down won. These are the settlement payoffs ($1 winner / $0 loser).
  * `/prices-history` returns a single MID series per token (not bid/ask) and its
    finest fidelity is 1 MINUTE -> only ~5-9 points per 5-minute window. A true
    sub-second tick backtest is therefore impossible from public history; the
    executable ASK is reconstructed downstream as mid + half_spread (+ slippage).
    For high-fidelity validation use `polymarket_arb.synth`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ASSET_PREFIXES = {"btc": "BTC", "eth": "ETH", "sol": "SOL", "bnb": "BNB", "doge": "DOGE"}

log = logging.getLogger("polymarket_arb.data")


@dataclass(frozen=True)
class Tick:
    """One observed quote in a window. Prices are token MIDPOINTS in [0, 1]."""
    ts: float        # unix seconds
    yes_mid: float   # Up midpoint
    no_mid: float    # Down midpoint


@dataclass
class MarketWindow:
    """A single 5-minute market: its quote path plus final resolution.

    `resolution_yes` is 1.0 if Up settled the winner, 0.0 if Down won, or None
    if unknown/unresolved. The backtester reads it ONLY at settlement.
    """
    slug: str
    asset: str
    start_ts: float
    end_ts: float
    yes_token: str
    no_token: str
    ticks: list[Tick]
    resolution_yes: float | None
    spread_hint: float = 0.01

    @property
    def resolution_no(self) -> float | None:
        return None if self.resolution_yes is None else 1.0 - self.resolution_yes

    @property
    def resolved(self) -> bool:
        return self.resolution_yes is not None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug, "asset": self.asset,
            "start_ts": self.start_ts, "end_ts": self.end_ts,
            "yes_token": self.yes_token, "no_token": self.no_token,
            "resolution_yes": self.resolution_yes, "spread_hint": self.spread_hint,
            "ticks": [[t.ts, t.yes_mid, t.no_mid] for t in self.ticks],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MarketWindow":
        return cls(
            slug=d["slug"], asset=d["asset"], start_ts=d["start_ts"], end_ts=d["end_ts"],
            yes_token=d["yes_token"], no_token=d["no_token"],
            resolution_yes=d["resolution_yes"], spread_hint=d.get("spread_hint", 0.01),
            ticks=[Tick(*row) for row in d["ticks"]],
        )


def _asset_from_slug(slug: str) -> str:
    prefix = slug.split("-updown-", 1)[0]
    return ASSET_PREFIXES.get(prefix, prefix.upper())


def _parse_resolution(market: dict) -> float | None:
    """Final Up payoff from `outcomePrices`, only when cleanly settled to 0/1."""
    raw = market.get("outcomePrices")
    if not raw:
        return None
    try:
        prices = [float(x) for x in (json.loads(raw) if isinstance(raw, str) else raw)]
    except (ValueError, TypeError):
        return None
    if len(prices) != 2:
        return None
    up, down = prices
    if abs((up + down) - 1.0) > 1e-6 or min(up, down) > 1e-6:
        return None  # not a clean binary settlement (still trading / disputed)
    return 1.0 if up > down else 0.0


class PolymarketClient:
    """Thin, retrying, disk-cached client for the public Polymarket APIs."""

    def __init__(self, gamma: str = GAMMA, clob: str = CLOB,
                 cache_dir: str | Path = ".cache", throttle: float = 0.15,
                 max_retries: int = 4, session: requests.Session | None = None):
        self.gamma = gamma.rstrip("/")
        self.clob = clob.rstrip("/")
        self.throttle = throttle
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- HTTP -------------------------------------------------------------
    def _get(self, base: str, path: str, **params):
        url = f"{base}{path}"
        backoff = 0.5
        for attempt in range(self.max_retries):
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("HTTP %s on %s (attempt %d) backing off %.1fs",
                            resp.status_code, path, attempt + 1, backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            time.sleep(self.throttle)
            return resp.json()
        resp.raise_for_status()

    # ---- discovery --------------------------------------------------------
    def discover_5m_events(self, asset: str | None = None, closed: bool = True,
                           max_events: int = 200, page: int = 100) -> list[dict]:
        """Recent crypto 5-minute Up/Down events (most recent first)."""
        want = asset.lower() if asset else None
        out: list[dict] = []
        offset = 0
        while len(out) < max_events:
            batch = self._get(
                self.gamma, "/events",
                closed=str(closed).lower(), tag_slug="crypto",
                order="startDate", ascending="false",
                limit=page, offset=offset,
            )
            if not batch:
                break
            for ev in batch:
                slug = ev.get("slug") or ""
                if "-updown-5m-" not in slug:
                    continue
                if want and not slug.startswith(f"{want}-"):
                    continue
                out.append(ev)
            offset += page
            if len(batch) < page:
                break
        return out[:max_events]

    # ---- price history ----------------------------------------------------
    def price_history(self, token: str, start_ts: float, end_ts: float,
                      fidelity: int = 1) -> list[tuple[float, float]]:
        data = self._get(self.clob, "/prices-history", market=token,
                         startTs=int(start_ts), endTs=int(end_ts), fidelity=fidelity)
        return [(float(p["t"]), float(p["p"])) for p in data.get("history", [])]

    # ---- window assembly --------------------------------------------------
    def fetch_window(self, event: dict, pad_s: int = 120,
                     fidelity: int = 1) -> MarketWindow | None:
        market = (event.get("markets") or [None])[0]
        if not market:
            return None
        try:
            tokens = json.loads(market["clobTokenIds"])
        except (KeyError, json.JSONDecodeError):
            return None
        if len(tokens) != 2:
            return None
        yes_token, no_token = tokens[0], tokens[1]
        start = _iso_to_unix(event.get("startDate"))
        end = _iso_to_unix(event.get("endDate"))
        if start is None or end is None:
            return None

        yh = dict(self.price_history(yes_token, start - pad_s, end + pad_s, fidelity))
        nh = dict(self.price_history(no_token, start - pad_s, end + pad_s, fidelity))
        ticks = _merge_histories(yh, nh, start, end)
        if not ticks:
            return None
        return MarketWindow(
            slug=event["slug"], asset=_asset_from_slug(event["slug"]),
            start_ts=start, end_ts=end, yes_token=yes_token, no_token=no_token,
            ticks=ticks, resolution_yes=_parse_resolution(market),
            spread_hint=float(market.get("spread") or 0.01),
        )

    def load_dataset(self, asset: str | None = None, max_windows: int = 100,
                     resolved_only: bool = True, use_cache: bool = True,
                     fidelity: int = 1) -> list[MarketWindow]:
        """Assemble a backtest dataset of closed 5-minute windows, cached per slug."""
        events = self.discover_5m_events(asset=asset, closed=True,
                                         max_events=max_windows * 2)
        windows: list[MarketWindow] = []
        for ev in events:
            if len(windows) >= max_windows:
                break
            slug = ev["slug"]
            cache_path = self.cache_dir / f"{slug}.json"
            if use_cache and cache_path.exists():
                w = MarketWindow.from_dict(json.loads(cache_path.read_text()))
            else:
                w = self.fetch_window(ev, fidelity=fidelity)
                if w is not None and use_cache:
                    cache_path.write_text(json.dumps(w.to_dict()))
            if w is None:
                continue
            if resolved_only and not w.resolved:
                continue
            windows.append(w)
        log.info("loaded %d windows (asset=%s)", len(windows), asset or "all")
        return windows


def _iso_to_unix(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _merge_histories(yh: dict[float, float], nh: dict[float, float],
                     start: float, end: float) -> list[Tick]:
    """Union timestamps, forward-fill each leg, clip to [start, end]."""
    times = sorted(set(yh) | set(nh))
    ticks: list[Tick] = []
    last_y = last_n = None
    for t in times:
        last_y = yh.get(t, last_y)
        last_n = nh.get(t, last_n)
        if last_y is None or last_n is None:
            continue
        if t < start or t > end:   # strict window: never admit post-resolution ticks
            continue
        ticks.append(Tick(ts=t, yes_mid=last_y, no_mid=last_n))
    return ticks
