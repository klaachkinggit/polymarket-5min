"""Forward-only CLOB L2 order-book collector for 5-minute Up/Down windows.

Historical book depth does not exist publicly (the book is off-chain; only fills
settle on-chain), so the ONLY way to test whether the early-window QUOTE reversals
are fillable is to record the live book GOING FORWARD. This subscribes the CLOB
market WebSocket for upcoming/active windows and appends every `book` snapshot and
`price_change` delta — each stamped with a local receive time — to JSONL, for later
reconstruction of the resting bid/ask at any instant inside a window.

CLI:
    python -m polymarket_arb.collector --asset btc --minutes 30 --out data/book

This is intentionally a bounded, single-socket collector (good for capturing a
batch of windows). For an always-on production feed, wrap `collect()` in a
reconnect loop (websocket-client `run_forever`) and rotate output files daily.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import websocket  # websocket-client

from .data import PolymarketClient
from .trades import WINDOW_SECONDS, _slug_window

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

log = logging.getLogger("polymarket_arb.collector")


def discover_live_windows(client: PolymarketClient, asset: str | None = None,
                          max_windows: int = 50) -> list[dict]:
    """Open (not-yet-closed) 5-minute Up/Down windows with their two CLOB tokens."""
    want = asset.lower() if asset else None
    # ascending startDate: the longest-open markets resolve soonest (close = open + ~20h)
    batch = client._get(client.gamma, "/events", closed="false", tag_slug="crypto",
                        order="startDate", ascending="true", limit=200, offset=0)
    out: list[dict] = []
    for ev in batch or []:
        slug = ev.get("slug") or ""
        if "-updown-5m-" not in slug or (want and not slug.startswith(f"{want}-")):
            continue
        m = (ev.get("markets") or [{}])[0]
        try:
            toks = json.loads(m.get("clobTokenIds") or "[]")
        except json.JSONDecodeError:
            continue
        if len(toks) != 2:
            continue
        out.append({"slug": slug, "conditionId": m.get("conditionId"),
                    "yes": str(toks[0]), "no": str(toks[1]),
                    "open_ts": _slug_window(slug)[0]})
        if len(out) >= max_windows:
            break
    return out


DEFAULT_ASSETS = ("btc", "eth", "sol", "bnb", "doge")


def discover_current_windows(client: PolymarketClient, assets=DEFAULT_ASSETS,
                             horizon_s: float = 1800.0, now: float | None = None) -> list[dict]:
    """Windows whose 5-min scoring period is happening now or within `horizon_s`.

    5-min slugs are clock-aligned (open_ts is a multiple of WINDOW_SECONDS), so we
    enumerate the current + upcoming slug timestamps per asset and fetch each by
    slug — reliable regardless of the discovery endpoint's ordering/offset caps.
    """
    now = time.time() if now is None else now
    base = (int(now) // WINDOW_SECONDS) * WINDOW_SECONDS
    out: list[dict] = []
    for asset in ([assets] if isinstance(assets, str) else assets):
        ts = base
        while ts <= now + horizon_s:
            slug = f"{asset}-updown-5m-{ts}"
            evs = client._get(client.gamma, "/events", slug=slug)
            ev = evs[0] if isinstance(evs, list) and evs else None
            if ev:
                m = (ev.get("markets") or [{}])[0]
                try:
                    toks = json.loads(m.get("clobTokenIds") or "[]")
                except json.JSONDecodeError:
                    toks = []
                if len(toks) == 2:
                    out.append({"slug": slug, "conditionId": m.get("conditionId"),
                                "yes": str(toks[0]), "no": str(toks[1]), "open_ts": ts})
            ts += WINDOW_SECONDS
    return out


class BookCollector:
    def __init__(self, out_dir: str | Path = "data/book", ws_url: str = WS_URL,
                 client: PolymarketClient | None = None):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.ws_url = ws_url
        self.client = client or PolymarketClient()

    def collect(self, asset: str | None = None, duration_s: float = 300.0,
                max_windows: int = 20, max_messages: int | None = None) -> tuple[int, str | None]:
        """Subscribe the live book for current 5m windows; append events to JSONL.

        Returns (events_written, path). Each line: the raw server message plus
        `recv_ts` (local unix seconds) and the owning `slug`.
        """
        # windows whose 5-min scoring period happens during the capture horizon
        assets = asset if asset else DEFAULT_ASSETS
        wins = discover_current_windows(self.client, assets, horizon_s=duration_s)[:max_windows]
        token_to_slug: dict[str, str] = {}
        token_ids: list[str] = []
        for w in wins:
            for side in ("yes", "no"):
                token_ids.append(w[side])
                token_to_slug[w[side]] = w["slug"]
        if not token_ids:
            log.warning("no live 5m windows found for asset=%s", asset)
            return 0, None

        path = self.out_dir / f"book-{asset or 'all'}-{int(time.time())}.jsonl"
        ws = websocket.create_connection(self.ws_url, timeout=20)
        n = 0
        try:
            ws.send(json.dumps({"assets_ids": token_ids, "type": "market"}))
            deadline = time.time() + duration_s
            with open(path, "a") as f:
                while time.time() < deadline:
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        continue
                    recv_ts = time.time()
                    try:
                        msgs = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msgs, dict):
                        msgs = [msgs]
                    for m in msgs:
                        if not isinstance(m, dict):
                            continue
                        rec = {"recv_ts": recv_ts,
                               "slug": token_to_slug.get(m.get("asset_id")), **m}
                        f.write(json.dumps(rec) + "\n")
                        n += 1
                    f.flush()
                    if max_messages and n >= max_messages:
                        break
        finally:
            ws.close()
        log.info("wrote %d events to %s (%d tokens, %d windows)",
                 n, path, len(token_ids), len(wins))
        return n, str(path)


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Collect live Polymarket 5m order-book feed")
    ap.add_argument("--asset", default=None, help="btc|eth|sol|... (default: all)")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--max-windows", type=int, default=20)
    ap.add_argument("--out", default="data/book")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    n, path = BookCollector(out_dir=args.out).collect(
        asset=args.asset, duration_s=args.minutes * 60, max_windows=args.max_windows)
    print(f"collected {n} events -> {path}")


if __name__ == "__main__":
    main()
