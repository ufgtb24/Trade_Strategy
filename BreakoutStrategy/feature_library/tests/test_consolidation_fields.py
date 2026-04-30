"""Tests for consolidation field calculator (5 字段 + pivot_close，共 6 项)."""
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.consolidation_fields import (
    compute_consolidation_fields,
)


@pytest.fixture
def synthetic_df():
    """构造 91 个交易日（60 pre + 30 consol + 1 bo）的合成数据：前 60 天波动，后 30 天紧凑盘整，最后突破。"""
    n = 91  # 60 pre + 30 consol + 1 bo = 91 rows
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)

    # 前 60 天：波动 20-30
    pre_close = rng.uniform(20, 30, 60)
    # 后 30 天：紧凑盘整 28-32
    consol_close = rng.uniform(28, 32, 30)
    # 突破日：跳到 35
    breakout_close = np.array([35.0])

    closes = np.concatenate([pre_close, consol_close, breakout_close])
    highs = closes * 1.02
    lows = closes * 0.98
    opens = closes * 1.0
    volumes = np.concatenate([
        rng.uniform(800_000, 1_200_000, 60),       # 前期均量 ~1M
        rng.uniform(400_000, 600_000, 30),         # 盘整期缩量 ~500K
        np.array([2_500_000]),                     # 突破日放量
    ])

    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes,
    }, index=dates)


def test_returns_6_keys(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert set(fields.keys()) == {
        "consolidation_length_bars",
        "consolidation_height_pct",
        "consolidation_position_vs_52w_high",
        "consolidation_volume_ratio",
        "consolidation_tightness_atr",
        "pivot_close",
    }


def test_pivot_close_equals_pk_row_close(synthetic_df):
    """pivot_close 应等于 df.iloc[pk_index]['close']。"""
    pk_index = 60
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=pk_index,
    )
    expected = float(synthetic_df.iloc[pk_index]["close"])
    assert fields["pivot_close"] == expected


def test_length_bars_equals_bo_minus_pk(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert fields["consolidation_length_bars"] == 30


def test_volume_ratio_below_one_for_quiet_consolidation(synthetic_df):
    """合成数据盘整期均量 ~500K vs 前期 ~1M，比值应 < 1。"""
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert 0 < fields["consolidation_volume_ratio"] < 1.0


def test_height_pct_positive(synthetic_df):
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert fields["consolidation_height_pct"] > 0


def test_tightness_atr_positive(synthetic_df):
    """tightness 应为正浮点（盘整高度 / ATR）。"""
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=90, pk_index=60,
    )
    assert fields["consolidation_tightness_atr"] is not None
    assert fields["consolidation_tightness_atr"] > 0


def test_insufficient_lookback_returns_null(synthetic_df):
    """pk_index 太小时无法计算 volume_ratio 的前置 60 bars，应返回 None。"""
    fields = compute_consolidation_fields(
        df=synthetic_df, bo_index=30, pk_index=20,
    )
    assert fields["consolidation_volume_ratio"] is None


def test_tightness_atr_returns_null_for_small_bo_index():
    """bo_index < ATR_PERIOD + 1 (=15) 时 ATR 无法计算，应返回 None。"""
    # 小 fixture：12 行就够（< 15）
    n = 12
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 30, n)
    df = pd.DataFrame({
        "open": closes, "high": closes * 1.02, "low": closes * 0.98,
        "close": closes, "volume": rng.uniform(800_000, 1_200_000, n),
    }, index=dates)

    fields = compute_consolidation_fields(df=df, bo_index=10, pk_index=5)
    assert fields["consolidation_tightness_atr"] is None
