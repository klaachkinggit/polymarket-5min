"""Collector discovery logic (no network — client._get is stubbed)."""
from polymarket_arb.collector import (BookCollector, discover_current_windows,
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


# ---- non-stop (forever) mode -----------------------------------------------
def test_daily_path_rotates_by_utc_day(tmp_path):
    bc = BookCollector(out_dir=tmp_path)
    p1 = bc._daily_path(None, now=0)            # 1970-01-01 UTC
    p2 = bc._daily_path(None, now=86400)        # 1970-01-02 UTC
    assert p1.name == "book-all-19700101.jsonl"
    assert p2.name == "book-all-19700102.jsonl"


def test_tokens_builds_subscription_list_and_slug_map():
    wins = [{"slug": "btc-updown-5m-300", "yes": "Y1", "no": "N1"},
            {"slug": "eth-updown-5m-300", "yes": "Y2", "no": "N2"}]
    ids, m = BookCollector._tokens(wins)
    assert ids == ["Y1", "N1", "Y2", "N2"]
    assert m["Y1"] == "btc-updown-5m-300" and m["N2"] == "eth-updown-5m-300"


def test_collect_forever_re_discovers_each_cycle_and_stops_at_max_cycles(tmp_path):
    c = PolymarketClient(cache_dir=".cache")
    c._get = lambda base, path, **p: (
        [{"slug": p.get("slug"), "markets": [{"conditionId": "0xc",
          "clobTokenIds": '["Y", "N"]'}]}] if p.get("slug") else [])
    bc = BookCollector(out_dir=tmp_path, client=c)
    cycles = {"n": 0}

    def fake_stream(token_ids, token_to_slug, f, deadline, n=0, max_messages=None):
        cycles["n"] += 1
        assert token_ids == ["Y", "N"]          # discovered fresh each cycle
        return 7, False
    bc._stream_until = fake_stream
    total = bc.collect_forever(asset="btc", refresh_s=0.01, horizon_s=0, max_cycles=3)
    assert cycles["n"] == 3 and total == 21
