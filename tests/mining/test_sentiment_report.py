"""_generate_sentiment_section 报告生成测试"""

import pytest

from BreakoutStrategy.mining.template_validator import _generate_sentiment_section


def _make_sample_results():
    """构造典型的 sample_results 列表"""
    return [
        {"symbol": "AAPL", "date": "2024-01-15", "label": 0.10,
         "template_name": "t1", "sentiment_score": 0.40, "sentiment": "positive",
         "confidence": 0.8, "category": "pass", "total_count": 15},
        {"symbol": "GOOG", "date": "2024-01-16", "label": 0.06,
         "template_name": "t1", "sentiment_score": 0.05, "sentiment": "neutral",
         "confidence": 0.5, "category": "pass", "total_count": 12},
        {"symbol": "MSFT", "date": "2024-01-17", "label": -0.02,
         "template_name": "t1", "sentiment_score": -0.25, "sentiment": "negative",
         "confidence": 0.6, "category": "reject", "total_count": 8},
        {"symbol": "TSLA", "date": "2024-01-18", "label": -0.05,
         "template_name": "t1", "sentiment_score": -0.50, "sentiment": "negative",
         "confidence": 0.7, "category": "strong_reject", "total_count": 10},
        {"symbol": "NVDA", "date": "2024-01-19", "label": 0.03,
         "template_name": "t1", "sentiment_score": 0.0, "sentiment": "neutral",
         "confidence": 0.0, "category": "insufficient_data", "total_count": 0},
    ]


def _make_stats(results):
    """从 sample_results 构造 stats dict"""
    import numpy as np
    all_labels = np.array([r["label"] for r in results])
    passed_labels = np.array([
        r["label"] for r in results
        if r["category"] in ("pass", "insufficient_data", "error")
    ])
    return {
        "total_samples": 5, "unique_tickers": 5,
        "analyzed_count": 4, "error_count": 0,
        "pass_count": 2, "reject_count": 1, "strong_reject_count": 1,
        "insufficient_data_count": 1, "positive_boost_count": 1,
        "pre_filter_median": float(np.median(all_labels)),
        "post_filter_median": float(np.median(passed_labels)),
        "sentiment_lift": float(np.median(passed_labels) - np.median(all_labels)),
    }


class TestGenerateSentimentSection:

    def test_returns_lines_verdict_reasons(self):
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        lines, verdict, reasons = _generate_sentiment_section(stats, results, pre)

        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)
        assert verdict in ("EFFECTIVE", "MARGINAL", "INEFFECTIVE")
        assert isinstance(reasons, list)

    def test_section_headers_present(self):
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        lines, _, _ = _generate_sentiment_section(stats, results, pre)
        content = "\n".join(lines)

        assert "## 6. Sentiment Filter" in content
        assert "### 6.1 Sentiment Distribution" in content
        assert "### 6.2 Sentiment Effect" in content
        assert "### 6.3 Rejected Sample Analysis" in content
        assert "### 6.4 Positive Boost Analysis" in content
        assert "### 6.5 Sentiment Judgment" in content
        assert "Post-filter = pass + insufficient_data + error" in content
        assert "| Pre-filter | Pass-only |" in content
        assert "Coverage ratio" in content

    def test_verdict_effective(self):
        """sentiment_lift > 0 且 rejected_median < pass_median → EFFECTIVE"""
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        _, verdict, _ = _generate_sentiment_section(stats, results, pre)
        assert verdict == "EFFECTIVE"

    def test_verdict_ineffective_when_lift_zero(self):
        """sentiment_lift <= 0 → INEFFECTIVE"""
        results = [
            {"symbol": "AAPL", "date": "2024-01-15", "label": 0.05,
             "template_name": "t1", "sentiment_score": 0.10,
             "sentiment": "neutral", "confidence": 0.5,
             "category": "pass", "total_count": 10},
        ]
        stats = {
            "total_samples": 1, "unique_tickers": 1,
            "analyzed_count": 1, "error_count": 0,
            "pass_count": 1, "reject_count": 0, "strong_reject_count": 0,
            "insufficient_data_count": 0, "positive_boost_count": 0,
            "pre_filter_median": 0.05, "post_filter_median": 0.05,
            "sentiment_lift": 0.0,
        }
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        _, verdict, reasons = _generate_sentiment_section(stats, results, pre)
        assert verdict == "INEFFECTIVE"

    def test_empty_results(self):
        """空结果不崩溃"""
        stats = {
            "total_samples": 0, "unique_tickers": 0,
            "analyzed_count": 0, "error_count": 0,
            "pass_count": 0, "reject_count": 0, "strong_reject_count": 0,
            "insufficient_data_count": 0, "positive_boost_count": 0,
            "pre_filter_median": 0.0, "post_filter_median": 0.0,
            "sentiment_lift": 0.0,
        }
        pre = {"template_lift": 0.0, "matched_median": 0.0}

        lines, verdict, _ = _generate_sentiment_section(stats, [], pre)
        assert "## 6. Sentiment Filter" in "\n".join(lines)
        assert verdict == "INEFFECTIVE"
