"""batch_analyzer.py 的测试：样本提取和报告组装"""

import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.cascade.batch_analyzer import (
    extract_top_k_samples,
    deduplicate_analysis_tasks,
    build_cascade_report,
)
from BreakoutStrategy.cascade.models import BreakoutSample, CascadeResult


class TestExtractTopKSamples:
    """从 df_test + keys_test 中提取 top-K 模板命中样本"""

    def setup_method(self):
        self.df_test = pd.DataFrame({
            "symbol": ["AAPL", "GOOG", "MSFT", "TSLA", "AAPL"],
            "date": ["2024-01-10", "2024-01-11", "2024-01-12",
                     "2024-01-13", "2024-01-15"],
            "label_40": [0.05, 0.03, -0.02, 0.08, 0.04],
        })
        self.keys_test = np.array([7, 3, 7, 5, 7])
        self.top_k_keys = {7}
        self.top_k_names = {7: "tmpl_age_vol_mom"}

    def test_extract_matched_samples(self):
        samples = extract_top_k_samples(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            label_col="label_40",
        )
        assert len(samples) == 3
        assert all(isinstance(s, BreakoutSample) for s in samples)
        symbols = [s.symbol for s in samples]
        assert symbols == ["AAPL", "MSFT", "AAPL"]

    def test_extract_empty_when_no_match(self):
        samples = extract_top_k_samples(
            self.df_test, self.keys_test,
            {99}, {99: "no_match"},
            label_col="label_40",
        )
        assert samples == []


class TestDeduplicateAnalysisTasks:
    """按 (ticker, breakout_date) 去重生成分析任务"""

    def test_single_sample(self):
        samples = [BreakoutSample("AAPL", "2024-01-15", 0.05, "t1", 7)]
        tasks = deduplicate_analysis_tasks(samples, lookback_days=7)
        assert ("AAPL", "2024-01-15") in tasks
        assert tasks[("AAPL", "2024-01-15")]["date_from"] == "2024-01-08"
        assert tasks[("AAPL", "2024-01-15")]["date_to"] == "2024-01-15"

    def test_same_ticker_different_dates_separate_tasks(self):
        """同 ticker 不同日期产生独立的分析任务（各自 reference_date）"""
        samples = [
            BreakoutSample("AAPL", "2024-01-10", 0.05, "t1", 7),
            BreakoutSample("AAPL", "2024-01-15", 0.04, "t1", 7),
        ]
        tasks = deduplicate_analysis_tasks(samples, lookback_days=7)
        assert len(tasks) == 2
        assert tasks[("AAPL", "2024-01-10")]["date_to"] == "2024-01-10"
        assert tasks[("AAPL", "2024-01-15")]["date_to"] == "2024-01-15"

    def test_duplicate_ticker_date_deduplicated(self):
        """同 ticker 同日期（不同模板匹配）只产生一个分析任务"""
        samples = [
            BreakoutSample("AAPL", "2024-01-15", 0.05, "t1", 7),
            BreakoutSample("AAPL", "2024-01-15", 0.05, "t2", 3),
        ]
        tasks = deduplicate_analysis_tasks(samples, lookback_days=7)
        assert len(tasks) == 1

    def test_multiple_tickers(self):
        samples = [
            BreakoutSample("AAPL", "2024-01-15", 0.05, "t1", 7),
            BreakoutSample("GOOG", "2024-01-20", 0.03, "t1", 7),
        ]
        tasks = deduplicate_analysis_tasks(samples, lookback_days=7)
        assert len(tasks) == 2
        assert ("AAPL", "2024-01-15") in tasks
        assert ("GOOG", "2024-01-20") in tasks


class TestBuildCascadeReport:
    """从 CascadeResult 列表构建 CascadeReport"""

    def _make_result(self, label, score, category, total_count=10):
        sample = BreakoutSample("X", "2024-01-01", label, "t1", 7)
        return CascadeResult(
            sample=sample, sentiment_score=score,
            sentiment="positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral"),
            confidence=0.5, category=category, total_count=total_count,
        )

    def test_basic_report_stats(self):
        results = [
            self._make_result(0.05, 0.10, "pass"),
            self._make_result(0.08, 0.35, "pass"),
            self._make_result(-0.01, -0.20, "reject"),
            self._make_result(0.02, -0.50, "strong_reject"),
            self._make_result(0.03, 0.0, "insufficient_data", total_count=0),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)

        assert report.total_samples == 5
        assert report.pass_count == 2
        assert report.reject_count == 1
        assert report.strong_reject_count == 1
        assert report.insufficient_data_count == 1
        assert report.positive_boost_count == 1
        assert report.error_count == 0

    def test_cascade_lift_calculation(self):
        results = [
            self._make_result(0.10, 0.05, "pass"),
            self._make_result(0.06, 0.02, "pass"),
            self._make_result(-0.05, -0.30, "reject"),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)

        assert report.pre_filter_median == pytest.approx(0.06)
        assert report.post_filter_median == pytest.approx(0.08)
        assert report.cascade_lift == pytest.approx(0.02)

    def test_results_sorted_by_sentiment_score_desc(self):
        results = [
            self._make_result(0.05, -0.10, "pass"),
            self._make_result(0.08, 0.40, "pass"),
            self._make_result(0.03, 0.20, "pass"),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)
        scores = [r.sentiment_score for r in report.results]
        assert scores == sorted(scores, reverse=True)
