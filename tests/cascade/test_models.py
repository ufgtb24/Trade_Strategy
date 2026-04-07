"""models.py 的基础测试：数据类构造和字段验证"""

from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)


def test_breakout_sample_creation():
    sample = BreakoutSample(
        symbol="AAPL", date="2024-01-15", label=0.05,
        template_name="tmpl_1", template_key=7,
    )
    assert sample.symbol == "AAPL"
    assert sample.date == "2024-01-15"
    assert sample.label == 0.05


def test_cascade_result_defaults():
    sample = BreakoutSample("AAPL", "2024-01-15", 0.05, "tmpl_1", 7)
    result = CascadeResult(
        sample=sample, sentiment_score=0.35,
        sentiment="positive", confidence=0.8,
        category="pass", total_count=10,
    )
    assert result.analysis_report is None
    assert result.category == "pass"


def test_cascade_report_creation():
    report = CascadeReport(
        total_samples=50, unique_tickers=30,
        analyzed_count=48, error_count=2,
        pass_count=40, reject_count=5, strong_reject_count=3,
        insufficient_data_count=2, positive_boost_count=8,
        pre_filter_median=0.04, post_filter_median=0.06,
        cascade_lift=0.02,
    )
    assert report.results == []
    assert report.cascade_lift == 0.02
    assert report.positive_boost_count == 8
