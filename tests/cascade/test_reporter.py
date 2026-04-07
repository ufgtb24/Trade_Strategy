"""reporter.py 的测试：报告生成"""

from pathlib import Path

import pytest

from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)
from BreakoutStrategy.cascade.reporter import generate_cascade_report


@pytest.fixture
def sample_report():
    """构造一个包含各种 category 的 CascadeReport"""
    def _make(label, score, category, tc=10):
        s = BreakoutSample("AAPL", "2024-01-15", label, "tmpl_1", 7)
        sent = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")
        return CascadeResult(s, score, sent, 0.5, category, tc)

    results = [
        _make(0.10, 0.40, "pass", 15),
        _make(0.06, 0.05, "pass", 12),
        _make(-0.02, -0.25, "reject", 8),
        _make(-0.05, -0.50, "strong_reject", 10),
        _make(0.03, 0.0, "insufficient_data", 0),
    ]
    return CascadeReport(
        total_samples=5, unique_tickers=1,
        analyzed_count=4, error_count=0,
        pass_count=2, reject_count=1, strong_reject_count=1,
        insufficient_data_count=1, positive_boost_count=1,
        pre_filter_median=0.03, post_filter_median=0.06,
        cascade_lift=0.03,
        results=results,
    )


def test_generate_report_creates_file(sample_report, tmp_path):
    output = tmp_path / "cascade_report.md"
    pre_filter_metrics = {
        "template_lift": 0.02,
        "matched_median": 0.04,
    }
    generate_cascade_report(sample_report, pre_filter_metrics, output)
    assert output.exists()
    content = output.read_text()
    assert "Cascade Validation Report" in content
    assert "EFFECTIVE" in content or "MARGINAL" in content or "INEFFECTIVE" in content


def test_report_contains_all_sections(sample_report, tmp_path):
    output = tmp_path / "cascade_report.md"
    generate_cascade_report(sample_report, {"template_lift": 0.02, "matched_median": 0.04}, output)
    content = output.read_text()
    assert "## 0. Summary" in content
    assert "## 1. Pre-filter Baseline" in content
    assert "## 2. Sentiment Distribution" in content
    assert "## 3. Cascade Effect" in content
    assert "## 4. Rejected Sample Analysis" in content
    assert "## 4.1 Positive Boost Analysis" in content
    assert "## 5. Judgment" in content
