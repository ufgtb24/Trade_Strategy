"""Test MatchedBreakout serialization and cache I/O."""
import json
from pathlib import Path

from BreakoutStrategy.live.pipeline.results import (
    MatchedBreakout,
    CachedResults,
    save_cached_results,
    load_cached_results,
)


def test_matched_breakout_roundtrip(tmp_path: Path):
    """往返序列化一个 MatchedBreakout 列表。"""
    item = MatchedBreakout(
        symbol="AAPL",
        breakout_date="2026-04-08",
        breakout_price=5.42,
        factors={"age": 25, "height": 0.46, "volume": 3.2},
        sentiment_score=0.61,
        sentiment_category="analyzed",
        sentiment_summary="2 positive news",
        raw_breakout={"date": "2026-04-08", "price": 5.42, "age": 25},
        raw_peaks=[{"id": 1, "price": 5.0, "date": "2026-03-01"}],
    )
    cached = CachedResults(
        items=[item],
        scan_date="2026-04-08T18:30:00",
        last_scan_bar_date="2026-04-08",
    )
    path = tmp_path / "cache.json"
    save_cached_results(cached, path)
    assert path.exists()

    loaded = load_cached_results(path)
    assert loaded is not None
    assert len(loaded.items) == 1
    assert loaded.items[0].symbol == "AAPL"
    assert loaded.items[0].sentiment_score == 0.61
    assert loaded.items[0].factors == {"age": 25, "height": 0.46, "volume": 3.2}
    assert loaded.scan_date == "2026-04-08T18:30:00"
    assert loaded.last_scan_bar_date == "2026-04-08"


def test_load_cached_results_missing_file_returns_none(tmp_path: Path):
    assert load_cached_results(tmp_path / "does_not_exist.json") is None


def test_load_cached_results_corrupt_file_returns_none(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("not valid json {{{")
    assert load_cached_results(path) is None
