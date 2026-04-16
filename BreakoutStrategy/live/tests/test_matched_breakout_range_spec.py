from dataclasses import fields
from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def test_matched_breakout_has_optional_range_spec_field():
    field_names = {f.name for f in fields(MatchedBreakout)}
    assert "range_spec" in field_names


def test_matched_breakout_range_spec_defaults_to_none():
    mb = MatchedBreakout(
        symbol="AAPL",
        breakout_date="2024-01-15",
        breakout_price=180.0,
        factors={},
        sentiment_score=None,
        sentiment_category="pending",
        sentiment_summary=None,
        raw_breakout={"index": 0, "date": "2024-01-15", "price": 180.0},
        raw_peaks=[],
    )
    assert mb.range_spec is None
