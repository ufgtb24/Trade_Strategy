"""Unit tests for compute_label_value helper in analysis/features.py."""
import pandas as pd
import pytest

from BreakoutStrategy.analysis.features import compute_label_value, FeatureCalculator


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Minimal OHLCV-shaped DataFrame; only 'close' is read by compute_label_value."""
    n = len(closes)
    return pd.DataFrame({
        "open":  closes,
        "high":  [c * 1.01 for c in closes],
        "low":   [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000] * n,
    })


def test_basic_positive_gain():
    # close at index 0 = 10; next 3 days closes = [11, 13, 12]; max = 13
    # label = (13 - 10) / 10 = 0.3
    df = _make_df([10.0, 11.0, 13.0, 12.0, 12.5])
    assert compute_label_value(df, 0, 3) == pytest.approx(0.3)


def test_basic_negative_gain():
    # close at index 0 = 10; next 3 closes = [9, 8, 9.5]; max = 9.5
    # label = (9.5 - 10) / 10 = -0.05
    df = _make_df([10.0, 9.0, 8.0, 9.5, 9.0])
    assert compute_label_value(df, 0, 3) == pytest.approx(-0.05)


def test_insufficient_future_data_returns_none():
    # only 2 days after index 0, asking for 3
    df = _make_df([10.0, 11.0, 12.0])
    assert compute_label_value(df, 0, 3) is None


def test_zero_breakout_price_returns_none():
    df = _make_df([0.0, 1.0, 2.0, 3.0])
    assert compute_label_value(df, 0, 2) is None


def test_negative_breakout_price_returns_none():
    df = _make_df([-1.0, 1.0, 2.0, 3.0])
    assert compute_label_value(df, 0, 2) is None


def test_window_excludes_breakout_day():
    # index 1, max_days=2: future = closes[2:4] = [8, 20]; max = 20
    # label = (20 - 10) / 10 = 1.0  (breakout_price = closes[1] = 10)
    df = _make_df([999.0, 10.0, 8.0, 20.0, 5.0])
    assert compute_label_value(df, 1, 2) == pytest.approx(1.0)


def test_calculate_labels_equivalent_to_helper():
    """FeatureCalculator._calculate_labels 输出应与直接调 helper 等价。"""
    df = _make_df([10.0, 11.0, 12.5, 11.8, 13.0, 12.0, 14.0, 13.5])
    fc = FeatureCalculator({
        "label_configs": [{"max_days": 3}, {"max_days": 5}],
    })

    labels = fc._calculate_labels(df, index=1)

    assert labels == {
        "label_3": compute_label_value(df, 1, 3),
        "label_5": compute_label_value(df, 1, 5),
    }


def test_calculate_labels_default_max_days_when_missing():
    """label_configs 中 config 字典缺 max_days 时，按原实现应使用 20 天默认值。"""
    df = _make_df([10.0] + [11.0] * 25)
    fc = FeatureCalculator({"label_configs": [{}]})

    labels = fc._calculate_labels(df, index=0)

    assert "label_20" in labels
    assert labels["label_20"] == compute_label_value(df, 0, 20)


def test_calculate_labels_empty_configs():
    df = _make_df([10.0, 11.0, 12.0, 13.0])
    fc = FeatureCalculator({"label_configs": []})
    assert fc._calculate_labels(df, index=0) == {}


def test_calculate_labels_preserves_none_for_insufficient_data():
    """数据不足时 _calculate_labels 应保留 None，不吞并或替换成 0.0。

    下游消费者（UI 渲染路径、mining pipeline）依赖 None 作为"跳过此 BO"信号。
    """
    df = _make_df([10.0, 11.0, 12.0])  # only 2 future rows beyond index 0
    fc = FeatureCalculator({"label_configs": [{"max_days": 5}]})
    assert fc._calculate_labels(df, index=0) == {"label_5": None}
