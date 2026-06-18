"""Collector discovery logic (no network — client._get is stubbed)."""
from polymarket_arb.collector import (discover_current_windows,
                                       discover_live_windows)
from polymarket_arb.data import PolymarketClient


def _ev(slug, yes="Y", no="N", cond="0xc"):
    return {"slug": slug, "markets": [{"conditionId": cond,
            "clobTokenIds": f'["{yes}", "{no}"]'}]}


def _client(events):
    c = PolymarketClient(cache_dir=".cache")
    c._get = lambda base, path, **p: events
    return c


def test_discover_filters_to_5m_and_asset_and_parses_tokens():
    evs = [
        _ev("btc-updown-5m-100", yes="YB", no="NB"),
        _ev("eth-updown-5m-100"),                 # wrong asset
        _ev("btc-will-x-happen"),                 # not a 5m updown
        _ev("btc-updown-5m-200", yes="YB2", no="NB2"),
    ]
    out = discover_live_windows(_client(evs), asset="btc")
    assert [w["slug"] for w in out] == ["btc-updown-5m-100", "btc-updown-5m-200"]
    assert out[0]["yes"] == "YB" and out[0]["no"] == "NB"


def test_discover_respects_max_windows_and_no_asset_filter():
    evs = [_ev(f"sol-updown-5m-{i}") for i in range(10)]
    out = discover_live_windows(_client(evs), asset=None, max_windows=3)
    assert len(out) == 3


def test_discover_skips_markets_without_two_tokens():
    bad = {"slug": "btc-updown-5m-1", "markets": [{"conditionId": "0x", "clobTokenIds": "[]"}]}
    assert discover_live_windows(_client([bad]), asset="btc") == []


def test_discover_current_windows_enumerates_clock_aligned_slugs():
    c = PolymarketClient(cache_dir=".cache")
    present = {"btc-updown-5m-900", "btc-updown-5m-1200"}   # 1500 absent

    def fake(base, path, **p):
        slug = p.get("slug")
        return ([{"slug": slug, "markets": [{"conditionId": "0xc",
                 "clobTokenIds": '["Y", "N"]'}]}] if slug in present else [])
    c._get = fake
    out = discover_current_windows(c, assets="btc", horizon_s=600, now=1000)  # base=900
    assert [w["open_ts"] for w in out] == [900, 1200]
    assert out[0]["yes"] == "Y" and out[0]["no"] == "N"
