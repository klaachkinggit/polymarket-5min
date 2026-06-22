"""Trade-tape data layer: window math, pagination, dedup, per-token split.

Network is never touched — `_get` is stubbed with canned pages so the suite
stays deterministic. Live fetching is exercised separately in the notebook.
"""
import json

import pytest

from polymarket_arb.trades import (SETTLE_TAIL_S, WINDOW_SECONDS, Trade,
                                    TradeHistoryClient, TradeWindow,
                                    _dedup_trades, _parse_trade, _slug_window)


def _row(ts, asset, side="BUY", price=0.5, size=1.0, tx="0xabc", oidx=0):
    return {"timestamp": ts, "asset": asset, "side": side, "price": price,
            "size": size, "transactionHash": tx, "outcomeIndex": oidx,
            "conditionId": "0xcond"}


# ---- window math -----------------------------------------------------------
def test_slug_window_is_half_open_5min():
    open_ts, close_ts = _slug_window("btc-updown-5m-1781756700")
    assert open_ts == 1781756700
    assert close_ts == 1781756700 + WINDOW_SECONDS


def test_slug_window_other_assets():
    assert _slug_window("eth-updown-5m-1700000000") == (1700000000, 1700000300)


# ---- parsing & dedup -------------------------------------------------------
def test_parse_trade_maps_fields():
    t = _parse_trade(_row(123, "TKY", side="SELL", price=0.18, size=2.5, tx="0xff", oidx=1))
    assert (t.ts, t.token, t.side, t.price, t.size, t.tx, t.outcome_index) == \
        (123.0, "TKY", "SELL", 0.18, 2.5, "0xff", 1)


def test_dedup_drops_only_exact_tuple_dupes():
    a = Trade(1.0, "Y", "BUY", 0.44, 1.0, "0x1", 0)
    a_dup = Trade(1.0, "Y", "BUY", 0.44, 1.0, "0x1", 0)
    # same tx but a genuinely different leg (size differs) must be KEPT
    b = Trade(1.0, "Y", "BUY", 0.44, 2.0, "0x1", 0)
    out = _dedup_trades([a, a_dup, b])
    assert len(out) == 2
    assert a in out and b in out


# ---- pagination ------------------------------------------------------------
def _stub_pages(client, pages):
    """Make client.client._get serve `pages` keyed by offset, newest-first."""
    def fake_get(base, path, **params):
        assert path == "/trades"
        return pages.get(params["offset"], [])
    client.client._get = fake_get


def test_fetch_trades_pages_until_short_page():
    c = TradeHistoryClient()
    full = [_row(1000 - i, "Y", tx=f"0x{i}") for i in range(1000)]
    tail = [_row(0 - i, "Y", tx=f"0xt{i}") for i in range(120)]
    _stub_pages(c, {0: full, 1000: tail})  # 1000 then a short 120 -> stop
    got = c.fetch_trades("0xcond")
    assert len(got) == 1120


def test_fetch_trades_stops_on_empty_first_page():
    c = TradeHistoryClient()
    _stub_pages(c, {0: []})
    assert c.fetch_trades("0xcond") == []


def test_fetch_trades_stops_at_offset_cap_and_flags_truncation():
    """Busy market: full pages at offset 0/1000/2000/3000 then the API would 400."""
    c = TradeHistoryClient()
    pages = {off: [_row(9_000_000 - off - i, "Y", tx=f"0x{off}_{i}") for i in range(1000)]
             for off in (0, 1000, 2000, 3000)}
    _stub_pages(c, pages)              # offset 4000 not served -> would be a 400 live
    got = c.fetch_trades("0xcond")
    assert len(got) == 4000            # 4 full pages, never requests offset > 3000
    assert c.truncated is True


# ---- window assembly -------------------------------------------------------
def _event(slug="btc-updown-5m-1000", yes="Y", no="N", outcome_prices='["0", "1"]'):
    return {"slug": slug, "markets": [{
        "conditionId": "0xcond",
        "clobTokenIds": f'["{yes}", "{no}"]',
        "outcomePrices": outcome_prices,
    }]}


def test_build_window_filters_to_half_open_window_and_splits_tokens():
    c = TradeHistoryClient()
    open_ts, close_ts = 1000, 1300
    trades = [
        _row(open_ts - 5, "Y"),          # pre-open dust -> dropped
        _row(open_ts, "Y", price=0.44),  # in-window YES (boundary included)
        _row(open_ts + 10, "N", price=0.55),
        _row(close_ts - 1, "Y", price=0.30),
        _row(close_ts, "Y"),             # close is exclusive -> dropped
        _row(close_ts + 30, "N"),        # settlement tail -> dropped by default
    ]
    c.fetch_trades = lambda cond: [_parse_trade(r) for r in trades]
    w = c.build_window(_event())
    assert isinstance(w, TradeWindow)
    assert (w.open_ts, w.close_ts) == (open_ts, close_ts)
    assert [t.ts for t in w.yes_trades] == [open_ts, close_ts - 1]   # sorted, in-window
    assert [t.ts for t in w.no_trades] == [open_ts + 10]
    assert w.resolution_yes == 0.0   # ["0","1"] -> Down won


def test_build_window_can_include_settlement_tail():
    c = TradeHistoryClient()
    trades = [_row(1000, "Y"), _row(1300 + 30, "N")]
    c.fetch_trades = lambda cond: [_parse_trade(r) for r in trades]
    w = c.build_window(_event(), include_settlement_tail=True)
    assert len(w.no_trades) == 1
    assert SETTLE_TAIL_S >= 30


def test_load_history_walks_back_by_300_and_stops_after_max_gap():
    c = TradeHistoryClient()
    present = {3000, 2700, 2400}                       # then 2100,1800 missing -> stop
    c.fetch_event_by_slug = lambda slug: (
        {"slug": slug} if int(slug.rsplit("-", 1)[1]) in present else None)
    c.build_window = lambda ev, **k: TradeWindow(
        slug=ev["slug"], asset="BTC",
        open_ts=int(ev["slug"].rsplit("-", 1)[1]),
        close_ts=int(ev["slug"].rsplit("-", 1)[1]) + 300,
        yes_token="Y", no_token="N",
        yes_trades=[Trade(0.0, "Y", "SELL", 0.5, 1.0, "0x", 0)], no_trades=[],
        resolution_yes=1.0)
    out = c.load_history("btc", count=10, end_ts=3000, use_cache=False, max_gap=2)
    assert [w.open_ts for w in out] == [3000, 2700, 2400]


def test_load_history_cache_only_reads_disk_and_never_fetches(tmp_path):
    c = TradeHistoryClient(cache_dir=tmp_path)

    def _boom(slug):
        raise AssertionError("network must not be touched in cache_only mode")
    c.fetch_event_by_slug = _boom
    w = TradeWindow(slug="btc-updown-5m-3000", asset="BTC", open_ts=3000, close_ts=3300,
                    yes_token="Y", no_token="N",
                    yes_trades=[Trade(3001, "Y", "BUY", 0.5, 1.0, "0x", 0)], no_trades=[],
                    resolution_yes=1.0)
    (tmp_path / "trades-btc-updown-5m-3000.json").write_text(json.dumps(w.to_dict()))
    out = c.load_history("btc", count=10, cache_only=True, max_gap=2)
    assert [x.open_ts for x in out] == [3000]   # found via _latest_cached_ts, no network


def test_build_window_roundtrips_through_cache_dict():
    c = TradeHistoryClient()
    trades = [_row(1000, "Y", price=0.44), _row(1010, "N", price=0.55)]
    c.fetch_trades = lambda cond: [_parse_trade(r) for r in trades]
    w = c.build_window(_event())
    w2 = TradeWindow.from_dict(w.to_dict())
    assert w2.slug == w.slug
    assert [t.price for t in w2.yes_trades] == [0.44]
    assert [t.price for t in w2.no_trades] == [0.55]
    assert w2.resolution_yes == w.resolution_yes
