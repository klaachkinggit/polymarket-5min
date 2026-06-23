"""Opening-quote reconstruction helpers (pure; no file/network)."""
from polymarket_arb.book_replay import _best, _open_ts, _prefer, window_open_quotes
from polymarket_arb.trades import TradeWindow


def _w(slug, yes="AAA", no="BBB"):
    return TradeWindow(slug=slug, asset="BTC", open_ts=300.0, close_ts=600.0,
                       yes_token=yes, no_token=no, yes_trades=[], no_trades=[],
                       resolution_yes=1.0)


def test_best_bid_is_max_ask_is_min_excluding_zero_size():
    bids = [{"price": "0.40", "size": "10"}, {"price": "0.45", "size": "0"},
            {"price": "0.43", "size": "5"}]
    asks = [{"price": "0.55", "size": "3"}, {"price": "0.52", "size": "0"},
            {"price": "0.57", "size": "2"}]
    assert _best(bids, "bid") == 0.43      # 0.45 has zero size -> excluded
    assert _best(asks, "ask") == 0.55      # 0.52 has zero size -> excluded
    assert _best([], "bid") is None


def test_prefer_post_open_beats_pre_open_then_nearest_open():
    assert _prefer(5, -3) is True          # any post-open beats any pre-open
    assert _prefer(-3, 5) is False
    assert _prefer(2, 10) is True          # earliest after open
    assert _prefer(10, 2) is False
    assert _prefer(-2, -10) is True        # latest before open
    assert _prefer(-10, -2) is False


def test_open_ts_parses_slug():
    assert _open_ts("btc-updown-5m-1781723100") == 1781723100
    assert _open_ts(None) is None


def test_window_open_quotes_maps_yes_no_tokens():
    idx = {"btc-updown-5m-300": {"AAA": {"bid": 0.48, "ask": 0.52, "off": 3},
                                 "BBB": {"bid": 0.47, "ask": 0.53, "off": 4}}}
    q = window_open_quotes(_w("btc-updown-5m-300"), idx)
    assert q["yes"]["ask"] == 0.52 and q["no"]["ask"] == 0.53
    assert window_open_quotes(_w("eth-updown-5m-999"), idx) is None     # slug not in index
    assert window_open_quotes(_w("btc-updown-5m-300", no="ZZZ"), idx) is None  # token missing
