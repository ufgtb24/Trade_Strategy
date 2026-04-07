"""filter.py 的测试：分类逻辑和配置加载"""

import pytest

from BreakoutStrategy.cascade.filter import classify_sample, load_cascade_config


class TestClassifySample:
    """classify_sample 分类逻辑测试"""

    def setup_method(self):
        self.thresholds = {
            "strong_reject": -0.40,
            "reject": -0.15,
            "positive_boost": 0.30,
        }
        self.max_fail_ratio = 0.5
        self.min_total_count = 1

    def test_strong_reject(self):
        assert classify_sample(-0.50, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "strong_reject"

    def test_reject(self):
        assert classify_sample(-0.20, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "reject"

    def test_pass_neutral(self):
        assert classify_sample(0.0, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_pass_positive_boost(self):
        """score > +0.30 仍返回 'pass'（positive_boost 只是标记，不是独立分类）"""
        assert classify_sample(0.35, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_insufficient_data_zero_count(self):
        assert classify_sample(0.0, 0, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_insufficient_data_high_fail_ratio(self):
        assert classify_sample(0.0, 10, 6, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_insufficient_data_takes_priority_over_reject(self):
        """数据充足度检查优先于阈值判定"""
        assert classify_sample(-0.50, 0, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_boundary_reject_line(self):
        """-0.15 边界值归为 pass（score < -0.15 才 reject）"""
        assert classify_sample(-0.15, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_boundary_strong_reject_line(self):
        """score == -0.40 归为 strong_reject"""
        assert classify_sample(-0.40, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "strong_reject"


class TestIsPositiveBoost:
    def test_positive_boost_true(self):
        from BreakoutStrategy.cascade.filter import is_positive_boost
        assert is_positive_boost(0.35, {"positive_boost": 0.30}) is True

    def test_positive_boost_false(self):
        from BreakoutStrategy.cascade.filter import is_positive_boost
        assert is_positive_boost(0.20, {"positive_boost": 0.30}) is False


class TestLoadConfig:
    def test_load_config_returns_dict(self):
        config = load_cascade_config()
        assert isinstance(config, dict)
        assert "lookback_days" in config
        assert "thresholds" in config
