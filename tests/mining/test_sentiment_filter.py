"""_classify_sentiment / _run_sentiment_filter 测试"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from BreakoutStrategy.mining.template_validator import _classify_sentiment, _run_sentiment_filter


class TestClassifySentiment:
    """分类逻辑：数据充足度检查优先于阈值判定"""

    def setup_method(self):
        self.thresholds = {
            "strong_reject": -0.40,
            "reject": -0.15,
            "positive_boost": 0.30,
        }

    def test_strong_reject(self):
        assert _classify_sentiment(-0.50, 10, 0, self.thresholds) == "strong_reject"

    def test_reject(self):
        assert _classify_sentiment(-0.20, 10, 0, self.thresholds) == "reject"

    def test_pass_neutral(self):
        assert _classify_sentiment(0.0, 10, 0, self.thresholds) == "pass"

    def test_pass_positive_score(self):
        """score > positive_boost 仍返回 'pass'"""
        assert _classify_sentiment(0.35, 10, 0, self.thresholds) == "pass"

    def test_insufficient_data_zero_count(self):
        assert _classify_sentiment(0.0, 0, 0, self.thresholds) == "insufficient_data"

    def test_insufficient_data_high_fail_ratio(self):
        assert _classify_sentiment(0.0, 10, 6, self.thresholds) == "insufficient_data"

    def test_insufficient_data_takes_priority(self):
        """数据充足度检查优先于阈值判定"""
        assert _classify_sentiment(-0.50, 0, 0, self.thresholds) == "insufficient_data"

    def test_boundary_reject_line(self):
        """-0.15 边界值归为 pass（score < reject 才 reject）"""
        assert _classify_sentiment(-0.15, 10, 0, self.thresholds) == "pass"

    def test_boundary_strong_reject_line(self):
        """score == strong_reject 归为 strong_reject（<=）"""
        assert _classify_sentiment(-0.40, 10, 0, self.thresholds) == "strong_reject"

    def test_custom_min_total_count(self):
        assert _classify_sentiment(0.0, 3, 0, self.thresholds,
                                   min_total_count=5) == "insufficient_data"

    def test_custom_max_fail_ratio(self):
        assert _classify_sentiment(0.0, 10, 4, self.thresholds,
                                   max_fail_ratio=0.3) == "insufficient_data"


class TestRunSentimentFilter:
    """_run_sentiment_filter 批量编排测试"""

    def setup_method(self):
        self.df_test = pd.DataFrame({
            "symbol": ["AAPL", "GOOG", "MSFT", "TSLA", "AAPL"],
            "date": ["2024-01-10", "2024-01-11", "2024-01-12",
                     "2024-01-13", "2024-01-15"],
            "label": [0.05, 0.03, -0.02, 0.08, 0.04],
        })
        self.keys_test = np.array([7, 3, 7, 5, 7])
        self.top_k_keys = {7}
        self.top_k_names = {7: "tmpl_age_vol_mom"}
        self.sentiment_config = {
            'lookback_days': 7,
            'thresholds': {
                'strong_reject': -0.40,
                'reject': -0.15,
                'positive_boost': 0.30,
            },
            'min_total_count': 1,
            'max_fail_ratio': 0.5,
            'max_concurrent_tickers': 2,
            'max_retries': 0,
            'retry_delay': 0,
            'save_individual_reports': False,
        }

    @patch("BreakoutStrategy.news_sentiment.config.load_config")
    @patch("BreakoutStrategy.news_sentiment.api.analyze")
    def test_basic_flow(self, mock_analyze, mock_load_config):
        """mock sentiment.analyze，验证统计结果正确"""
        mock_load_config.return_value = MagicMock()
        mock_report = MagicMock()
        mock_report.summary.sentiment_score = 0.10
        mock_report.summary.sentiment = "neutral"
        mock_report.summary.confidence = 0.5
        mock_report.summary.total_count = 10
        mock_report.summary.fail_count = 1
        mock_analyze.return_value = mock_report

        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            self.sentiment_config,
        )
        assert stats["total_samples"] == 3  # AAPL×2 + MSFT matched key=7
        assert stats["pass_count"] == 3     # score=0.10 > -0.15 → pass
        assert stats["reject_count"] == 0
        assert len(results) == 3

    @patch("BreakoutStrategy.news_sentiment.config.load_config")
    @patch("BreakoutStrategy.news_sentiment.api.analyze")
    def test_no_matched_samples(self, mock_analyze, mock_load_config):
        """无匹配样本时返回空统计"""
        mock_load_config.return_value = MagicMock()
        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            {99}, {99: "no_match"},
            self.sentiment_config,
        )
        assert stats["total_samples"] == 0
        assert results == []

    @patch("BreakoutStrategy.news_sentiment.config.load_config")
    @patch("BreakoutStrategy.news_sentiment.api.analyze")
    def test_analyze_failure_marked_as_error(self, mock_analyze, mock_load_config):
        """analyze 返回 None（全部重试失败）时标记为 error"""
        mock_load_config.return_value = MagicMock()
        mock_analyze.return_value = None

        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            self.sentiment_config,
        )
        assert stats["error_count"] == 3
        assert all(r["category"] == "error" for r in results)
