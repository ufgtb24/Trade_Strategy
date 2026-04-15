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


def test_matched_breakout_has_all_stock_breakouts_field_defaults_empty():
    """新字段 all_stock_breakouts 默认空 list，保证旧调用点无需显式传。"""
    from BreakoutStrategy.live.pipeline.results import MatchedBreakout

    item = MatchedBreakout(
        symbol="AAPL",
        breakout_date="2026-04-08",
        breakout_price=150.0,
        factors={},
        sentiment_score=None,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 100},
        raw_peaks=[],
    )
    assert item.all_stock_breakouts == []
    assert item.all_matched_bo_chart_indices == []


def test_roundtrip_preserves_new_fields(tmp_path):
    """save/load 保留 all_stock_breakouts 与 all_matched_bo_chart_indices。"""
    from BreakoutStrategy.live.pipeline.results import (
        CachedResults, MatchedBreakout,
        save_cached_results, load_cached_results,
    )

    item = MatchedBreakout(
        symbol="AAPL",
        breakout_date="2026-04-08",
        breakout_price=150.0,
        factors={"f1": 1.0},
        sentiment_score=None,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 100, "date": "2026-04-08"},
        raw_peaks=[{"id": 1, "index": 50, "price": 140.0, "is_active": False, "is_superseded": False}],
        all_stock_breakouts=[
            {"index": 70, "date": "2026-03-01"},
            {"index": 100, "date": "2026-04-08"},
        ],
        all_matched_bo_chart_indices=[100],
    )
    cached = CachedResults(items=[item], scan_date="2026-04-13T10:00:00",
                           last_scan_bar_date="2026-04-10")

    path = tmp_path / "cache.json"
    save_cached_results(cached, path)
    loaded = load_cached_results(path)

    assert loaded is not None
    assert len(loaded.items) == 1
    restored = loaded.items[0]
    assert restored.all_stock_breakouts == [
        {"index": 70, "date": "2026-03-01"},
        {"index": 100, "date": "2026-04-08"},
    ]
    assert restored.all_matched_bo_chart_indices == [100]


def test_load_cached_results_legacy_file_without_new_fields(tmp_path):
    """旧缓存 JSON 缺 all_stock_breakouts / all_matched_bo_chart_indices 字段 → 加载后两字段退化为空 list。"""
    import json
    from BreakoutStrategy.live.pipeline.results import load_cached_results

    legacy_cache = {
        "scan_date": "2026-04-13T10:00:00",
        "last_scan_bar_date": "2026-04-10",
        "items": [
            {
                "symbol": "AAPL",
                "breakout_date": "2026-04-08",
                "breakout_price": 150.0,
                "factors": {},
                "sentiment_score": None,
                "sentiment_category": "pending",
                "sentiment_summary": None,
                "raw_breakout": {"index": 100},
                "raw_peaks": [],
                # 故意不包含 all_stock_breakouts 和 all_matched_bo_chart_indices
            }
        ],
    }
    path = tmp_path / "legacy_cache.json"
    path.write_text(json.dumps(legacy_cache))

    loaded = load_cached_results(path)
    assert loaded is not None
    item = loaded.items[0]
    assert item.all_stock_breakouts == []
    assert item.all_matched_bo_chart_indices == []
