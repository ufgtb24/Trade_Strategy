"""Integration test: _step3_match_templates populates new MatchedBreakout fields."""
from unittest.mock import MagicMock

from BreakoutStrategy.live.pipeline.daily_runner import DailyPipeline


def _stub_pipeline(trial_template):
    """Construct a DailyPipeline stub with the minimum needed to run _step3."""
    trial = MagicMock()
    trial.template = trial_template
    trial.thresholds = {}
    trial.negative_factors = []

    pipeline = DailyPipeline.__new__(DailyPipeline)
    pipeline.trial = trial
    return pipeline


def test_step3_populates_all_stock_breakouts_and_matched_indices(monkeypatch):
    """Given a stock with 3 BOs (idx 50/100/200) where BOs at df-idx 100 and 200 match template,
    the resulting MatchedBreakouts must each carry:
      - all_stock_breakouts: 全部 3 个 BO dict
      - all_matched_bo_chart_indices: [100, 200] （即 df-idx 列表）
    """
    from BreakoutStrategy.mining import template_matcher

    class _FakeMatcher:
        templates = []
        thresholds = {}
        negative_factors = []
        sample_size = 1
        _loaded = True
        def match_stock(self, stock_result, template):
            # 返回 breakouts 列表的 index (非 df-idx)：第 1 和 2 项匹配
            return [1, 2]

    monkeypatch.setattr(template_matcher, "TemplateManager", lambda: _FakeMatcher())

    pipeline = _stub_pipeline({"factors": []})

    scan_results = [
        {
            "symbol": "AAPL",
            "breakouts": [
                {"index": 50, "date": "2026-01-01", "price": 100.0},
                {"index": 100, "date": "2026-03-01", "price": 120.0},
                {"index": 200, "date": "2026-04-01", "price": 150.0},
            ],
            "all_peaks": [],
        }
    ]

    candidates = pipeline._step3_match_templates(scan_results)

    assert len(candidates) == 2, "应为每个 matched idx 生成一个 MatchedBreakout"
    for mb in candidates:
        # 全部 BO 保留
        assert len(mb.all_stock_breakouts) == 3
        assert [b["index"] for b in mb.all_stock_breakouts] == [50, 100, 200]
        # 匹配到的 df-idx 是 100 和 200
        assert mb.all_matched_bo_chart_indices == [100, 200]

    # 两个 MatchedBreakout 的 raw_breakout 分别是 idx=100 和 idx=200
    assert candidates[0].raw_breakout["index"] == 100
    assert candidates[1].raw_breakout["index"] == 200


def test_step3_skips_stocks_without_breakouts(monkeypatch):
    """stock_result 没有 breakouts 或报错时跳过；不影响其他股票的新字段。"""
    from BreakoutStrategy.mining import template_matcher

    class _FakeMatcher:
        templates = []
        thresholds = {}
        negative_factors = []
        sample_size = 1
        _loaded = True
        def match_stock(self, stock_result, template):
            return [0]

    monkeypatch.setattr(template_matcher, "TemplateManager", lambda: _FakeMatcher())

    pipeline = _stub_pipeline({"factors": []})
    scan_results = [
        {"symbol": "BAD", "error": "some error"},
        {
            "symbol": "GOOD",
            "breakouts": [{"index": 10, "date": "2026-01-01", "price": 10.0}],
            "all_peaks": [],
        },
    ]

    candidates = pipeline._step3_match_templates(scan_results)
    assert len(candidates) == 1
    assert candidates[0].symbol == "GOOD"
    assert candidates[0].all_stock_breakouts == [{"index": 10, "date": "2026-01-01", "price": 10.0}]
    assert candidates[0].all_matched_bo_chart_indices == [10]
