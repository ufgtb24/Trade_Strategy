"""_classify_sentiment 分类逻辑测试"""

import pytest

from BreakoutStrategy.mining.template_validator import _classify_sentiment


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
