"""Reconstruct real best bid/ask at the window open from the collected CLOB book.

The forward collector (collector.py) recorded full L2 `book` snapshots for live 5-minute
windows. This builds a compact OPENING-QUOTE index: per (slug, token), the book snapshot
closest to the window's open (best bid = max bid price, best ask = min ask price). That is
the real, separately-collected price a market order would have paid — used to test whether
the in-sample "low-vol momentum" tilt survives the actual spread.

We use `book` snapshots only (each carries the full two-sided book); `price_change` deltas
carry no slug and are not needed for the opening quote. Build once:

    python -m polymarket_arb.book_replay --build --out data/book/opening_quotes.json
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

BOOK_GLOB = "data/book/book-all-*.jsonl"
DEFAULT_INDEX = "data/book/opening_quotes.json"
_MARKER = '"event_type": "book"'


def _best(levels: list, side: str) -> float | None:
    """best bid = highest price with size>0; best ask = lowest such price."""
    prices = [float(x["price"]) for x in levels if float(x.get("size", 0)) > 0]
    if not prices:
        return None
    return max(prices) if side == "bid" else min(prices)


def _open_ts(slug: str) -> int | None:
    try:
        return int(slug.rsplit("-", 1)[1])
    except (ValueError, AttributeError):
        return None


def build_opening_quote_index(paths: list[str] | None = None, entry_window_s: float = 300.0,
                              preopen_s: float = 0.0, out_path: str = DEFAULT_INDEX) -> dict:
    """Per (slug, asset_id) opening quote = the EARLIEST snapshot in [open, open+entry_window_s].
    `preopen_s=0` keeps it causal: a signal-conditioned bet can only fill at/after the open
    (the previous window's outcome — the momentum signal — is unknown before then). Set
    preopen_s>0 only for descriptive spread stats, never for a tradeable entry."""
    paths = paths or sorted(glob.glob(BOOK_GLOB))
    best: dict = {}                              # (slug, aid) -> dict(ts,bid,ask,off)
    for p in paths:
        with open(p) as f:
            for line in f:
                if _MARKER not in line:          # skip price_change/last_trade cheaply
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = r.get("slug")
                aid = r.get("asset_id")
                o = _open_ts(slug) if slug else None
                if o is None or not aid:
                    continue
                try:
                    ts = float(r.get("timestamp") or 0) / 1000.0   # server ms (JSON string)
                except (TypeError, ValueError):
                    continue
                off = ts - o
                if off < -preopen_s or off > entry_window_s:
                    continue
                bid = _best(r.get("bids") or [], "bid")
                ask = _best(r.get("asks") or [], "ask")
                if bid is None or ask is None:
                    continue
                rec = {"ts": ts, "bid": bid, "ask": ask, "off": off}
                key = f"{slug}\t{aid}"
                cur = best.get(key)
                if cur is None or _prefer(off, cur["off"]):
                    best[key] = rec
    # nest into {slug: {aid: rec}}
    out: dict = {}
    for key, rec in best.items():
        slug, aid = key.split("\t")
        out.setdefault(slug, {})[aid] = rec
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out))
    return out


def _prefer(new_off: float, cur_off: float) -> bool:
    """Prefer the snapshot closest to open from the post-open side; post-open beats pre-open."""
    new_post, cur_post = new_off >= 0, cur_off >= 0
    if new_post != cur_post:
        return new_post                          # any post-open beats any pre-open
    if new_post:
        return new_off < cur_off                 # earliest after open
    return new_off > cur_off                     # latest before open


def load_opening_quotes(path: str = DEFAULT_INDEX) -> dict:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def window_open_quotes(window, index: dict) -> dict | None:
    """{'yes': {bid,ask,off}, 'no': {...}} for a TradeWindow from the opening index."""
    book = index.get(window.slug)
    if not book:
        return None
    y, n = book.get(str(window.yes_token)), book.get(str(window.no_token))
    if not y or not n:
        return None
    return {"yes": y, "no": n}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build opening-quote index from collected book")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--out", default=DEFAULT_INDEX)
    ap.add_argument("--entry-window", type=float, default=120.0)
    args = ap.parse_args(argv)
    if args.build:
        idx = build_opening_quote_index(entry_window_s=args.entry_window, out_path=args.out)
        n_tok = sum(len(v) for v in idx.values())
        print(f"indexed {len(idx)} slugs, {n_tok} (slug,token) opening quotes -> {args.out}")


if __name__ == "__main__":
    main()
