from datetime import date
import pandas as pd
import pytest

from BreakoutStrategy.live.pipeline.daily_runner import _build_range_spec_for_symbol


def _make_pkl_df(start="2022-01-01", periods=900):
    idx = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0
    }, index=idx)


def test_build_range_spec_returns_spec_when_df_valid(tmp_path):
    """从 pkl 构造 spec，应得到合理的 ChartRangeSpec。"""
    df = _make_pkl_df()
    pkl_path = tmp_path / "AAPL.pkl"
    df.to_pickle(pkl_path)

    spec = _build_range_spec_for_symbol(
        pkl_path=pkl_path,
        scan_start="2024-01-01",
        scan_end=df.index[-1].date().isoformat(),
    )

    assert spec is not None
    assert spec.scan_start_ideal == date(2024, 1, 1)


def test_build_range_spec_returns_none_on_missing_pkl(tmp_path):
    spec = _build_range_spec_for_symbol(
        pkl_path=tmp_path / "NOTEXIST.pkl",
        scan_start="2024-01-01",
        scan_end="2024-12-31",
    )
    assert spec is None


def test_compute_download_days_covers_display_window():
    """download_days 应至少覆盖 DISPLAY_MIN_WINDOW。"""
    from BreakoutStrategy.live.pipeline.daily_runner import _compute_download_days
    from BreakoutStrategy.UI.charts.range_utils import DISPLAY_MIN_WINDOW
    days = _compute_download_days(scan_window_days=180)
    assert days >= DISPLAY_MIN_WINDOW.days


def test_compute_download_days_covers_scan_plus_buffers():
    """当 scan + buffer 超过 display_window 时，download_days 应跟随增大。"""
    from BreakoutStrategy.live.pipeline.daily_runner import _compute_download_days
    # 极端：scan_window=3000 天，远大于 3 年 display
    days = _compute_download_days(scan_window_days=3000)
    # 至少 3000 + compute_buffer + label_buffer + safety
    # compute_buffer ≈ 415，label ≈ 30，safety 30 → 约 3475
    assert days >= 3000 + 400 + 25 + 20  # 宽松下限


def test_compute_download_days_includes_safety_margin():
    """safety margin 应添加到最终结果。"""
    from BreakoutStrategy.live.pipeline.daily_runner import _compute_download_days
    days_with_safety = _compute_download_days(scan_window_days=180)
    days_without_safety = _compute_download_days(scan_window_days=180, safety_days=0)
    assert days_with_safety > days_without_safety


def test_compute_download_days_scales_with_ma_period():
    """MA 周期更大时 compute_buffer 应更大，但仅在超过 display_window 时才影响结果。"""
    from BreakoutStrategy.live.pipeline.daily_runner import _compute_download_days
    # 用极小 display_window=0 来暴露 buffer 差异
    # 此测试验证函数内部的 ma_period 参数会传递到 compute_buffer 计算
    days_ma200 = _compute_download_days(scan_window_days=180, ma_period=200, display_window_days=0)
    days_ma400 = _compute_download_days(scan_window_days=180, ma_period=400, display_window_days=0)
    assert days_ma400 > days_ma200
