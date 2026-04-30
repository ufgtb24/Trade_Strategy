"""Tests for sample chart renderer."""
import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.feature_library.sample_renderer import render_sample_chart


@pytest.fixture
def synthetic_df():
    n = 100
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed=42)
    closes = rng.uniform(20, 35, n)
    return pd.DataFrame({
        "open": closes, "high": closes * 1.02, "low": closes * 0.98,
        "close": closes, "volume": rng.uniform(500_000, 1_500_000, n),
    }, index=dates)


def test_render_creates_png_file(tmp_path, synthetic_df, monkeypatch):
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    out_path = render_sample_chart(
        sample_id="BO_TEST_20230301",
        df_window=synthetic_df,
        bo_index=90,
        left_index=60,
    )
    assert out_path.exists()
    assert out_path.suffix == ".png"
    assert out_path.stat().st_size > 5_000  # PNG 至少 5KB


def test_render_idempotent(tmp_path, synthetic_df, monkeypatch):
    """重复渲染应覆盖原文件，不报错。"""
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "FEATURE_LIBRARY_ROOT", tmp_path / "feature_library")
    monkeypatch.setattr(paths, "SAMPLES_DIR", paths.FEATURE_LIBRARY_ROOT / "samples")

    sample_id = "BO_TEST_20230301"
    p1 = render_sample_chart(sample_id, synthetic_df, 90, 60)
    p2 = render_sample_chart(sample_id, synthetic_df, 90, 60)
    assert p1 == p2
    assert p2.exists()


def test_render_sample_chart_does_not_pollute_global_backend(tmp_path, monkeypatch):
    """OO API 改造后调用 render_sample_chart 必须不修改全局 matplotlib backend。"""
    import matplotlib

    # 强制设置一个非 Agg backend（模拟 dev UI 的 TkAgg 环境）
    # 用 Agg 之外的 headless 替代品 'pdf' 以避免 CI 缺图形栈
    matplotlib.use("pdf", force=True)
    backend_before = matplotlib.get_backend()

    try:
        # 准备一个最小有效 sample
        from BreakoutStrategy.feature_library import paths
        monkeypatch.setattr(paths, "SAMPLES_DIR", tmp_path)

        df = pd.DataFrame({
            "open":   [10.0, 10.5, 11.0, 11.5, 12.0],
            "high":   [10.5, 11.0, 11.5, 12.0, 13.0],
            "low":    [9.5,  10.0, 10.5, 11.0, 11.5],
            "close":  [10.3, 10.8, 11.3, 11.8, 12.8],
            "volume": [1e6,  1.1e6, 1.2e6, 1.3e6, 2.5e6],
        }, index=pd.date_range("2024-01-01", periods=5, freq="B"))

        out_path = render_sample_chart(
            sample_id="BO_TEST_20240101",
            df_window=df, bo_index=4, left_index=1,
        )

        backend_after = matplotlib.get_backend()
        assert backend_before == backend_after, \
            f"render_sample_chart 污染了全局 backend: {backend_before} → {backend_after}"
        assert out_path.exists(), "chart.png 应该被生成"
        assert out_path.stat().st_size > 0, "chart.png 不应为空"
    finally:
        # 无论断言是否失败，都还原 backend，避免污染同 session 后续测试
        matplotlib.use(backend_before, force=True)


def test_render_sample_chart_anonymizes_title_and_normalizes_yaxis(
    tmp_path, monkeypatch,
):
    """归一化方案 B：chart.png 的标题不应含 ticker/sample_id；
    Y 轴显示相对 BO close 的百分比（D-07）。"""
    from BreakoutStrategy.feature_library import paths
    monkeypatch.setattr(paths, "SAMPLES_DIR", tmp_path)

    df = pd.DataFrame({
        "open":   [10.0, 10.5, 11.0, 11.5, 12.0],
        "high":   [10.5, 11.0, 11.5, 12.0, 13.0],
        "low":    [9.5,  10.0, 10.5, 11.0, 11.5],
        "close":  [10.3, 10.8, 11.3, 11.8, 12.8],
        "volume": [1e6,  1.1e6, 1.2e6, 1.3e6, 2.5e6],
    }, index=pd.date_range("2024-01-01", periods=5, freq="B"))

    # 用一个会泄漏 ticker 的 sample_id 验证标题脱敏
    sid = "BO_AAPL_20240105"
    rendered = render_sample_chart(
        sample_id=sid, df_window=df, bo_index=4, left_index=1,
    )

    # 通过 OCR 不可行，改为重新渲染一份用 in-memory inspect
    # 直接用 OO API 重新构造同样的图，断言我们设置的标题/坐标轴格式
    from matplotlib.figure import Figure
    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
    )
    fig = _build_figure_for_inspection(df, bo_index=4, left_index=1)
    ax_price = fig.axes[0]

    title = ax_price.get_title()
    assert "AAPL" not in title, f"标题不应含 ticker: {title!r}"
    assert "20240105" not in title, f"标题不应含日期: {title!r}"
    assert sid not in title, f"标题不应含 sample_id: {title!r}"

    # D-07: ylabel 必须是 BO close 文本
    assert ax_price.get_ylabel() == "Price (% from BO close)", \
        f"ylabel 应为 'Price (% from BO close)'，实际: {ax_price.get_ylabel()!r}"

    # D-06: 标题恒为通用文本(无 anonymized 后缀)
    assert title == "Breakout sample", \
        f"标题应为 'Breakout sample'，实际: {title!r}"

    # D-07: pivot 是 BO close（= 12.8），不是原来的 pk close（= 10.8）
    formatter = ax_price.yaxis.get_major_formatter()
    at_bo = formatter(12.8, 0)
    assert "0" in at_bo and ("+0" in at_bo or at_bo.startswith("0")), \
        f"BO close 应渲染为 0%，实际: {at_bo!r}"

    # 反向：用旧 pivot 10.8 触发的 0% 现在应是负值（因为 10.8 < 12.8）
    at_old_pk = formatter(10.8, 0)
    assert "-" in at_old_pk, \
        f"原 pk close (10.8) 在新 BO pivot 下应为负百分比，实际: {at_old_pk!r}"

    # Y 轴用 FuncFormatter 显示 % 化值
    formatted = formatter(12.8, 0)
    assert "%" in formatted, f"Y 轴应显示百分比格式，实际: {formatted!r}"


def test_render_window_is_narrowed_to_left_to_bo_inclusive():
    """D-05: 渲染只覆盖 [left_index : bo_index + 1] 区间，不画 left 之前的 K 线。"""
    n = 50
    df = pd.DataFrame({
        "open": np.linspace(10, 20, n), "high": np.linspace(11, 21, n),
        "low": np.linspace(9, 19, n), "close": np.linspace(10, 20, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))

    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
    )
    fig = _build_figure_for_inspection(df, bo_index=40, left_index=20)
    ax_vol = fig.axes[1]

    # volume bar 数量 == 21（= 40 - 20 + 1）
    bar_patches = [p for p in ax_vol.patches]
    assert len(bar_patches) == 21, \
        f"volume bar 数量应为 21，实际: {len(bar_patches)}"


def test_render_does_not_draw_pk_or_bo_axvline():
    """D-06: 删除 pk/bo 虚线 + legend。"""
    n = 30
    df = pd.DataFrame({
        "open": np.linspace(10, 20, n), "high": np.linspace(11, 21, n),
        "low": np.linspace(9, 19, n), "close": np.linspace(10, 20, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))

    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
    )
    fig = _build_figure_for_inspection(df, bo_index=20, left_index=5)
    ax_price, ax_vol = fig.axes

    # 不应有 legend
    assert ax_price.get_legend() is None, "ax_price.legend 应被删除 (D-06)"

    # 检查 axvline：axvline 使用 ax.get_xaxis_transform()（BlendedGenericTransform），
    # 而 K 线影线使用 ax.transData（CompositeGenericTransform），可通过 transform 区分
    def has_vline(ax):
        xaxis_transform = ax.get_xaxis_transform()
        for line in ax.get_lines():
            if line.get_transform() == xaxis_transform:
                return True
        return False

    assert not has_vline(ax_price), "ax_price 不应含 axvline (pk/bo)"
    assert not has_vline(ax_vol), "ax_vol 不应含 axvline (pk/bo)"


def test_render_does_not_pollute_global_rcparams_font_size():
    """D-09: rc_context 局部覆盖，不污染全局 font.size。"""
    import matplotlib as mpl

    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
    )
    font_before = mpl.rcParams["font.size"]
    n = 10
    df = pd.DataFrame({
        "open": np.linspace(10, 20, n), "high": np.linspace(11, 21, n),
        "low": np.linspace(9, 19, n), "close": np.linspace(10, 20, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))

    _build_figure_for_inspection(df, bo_index=8, left_index=2)
    assert mpl.rcParams["font.size"] == font_before, \
        f"font.size 被污染: {font_before} → {mpl.rcParams['font.size']}"


def test_render_applies_unified_fontsize():
    """全图字号统一到 CHART_TEXT_SIZE(=10): title / ylabel / ticks / offset / candlestick 注入文本。
    用户决策: chart.png 视觉上所有文字与 title 同号。
    """
    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
        CHART_TEXT_SIZE,
    )

    n = 30
    df = pd.DataFrame({
        "open": np.linspace(10, 20, n), "high": np.linspace(11, 21, n),
        "low": np.linspace(9, 19, n), "close": np.linspace(10, 20, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))

    fig = _build_figure_for_inspection(df, bo_index=20, left_index=5)
    ax_price, ax_vol = fig.axes

    # title
    assert ax_price.title.get_fontsize() == CHART_TEXT_SIZE, \
        f"title fontsize 应为 {CHART_TEXT_SIZE}，实际: {ax_price.title.get_fontsize()}"

    # ylabels (price + volume); xlabel intentionally absent on volume axis
    assert ax_price.yaxis.label.get_fontsize() == CHART_TEXT_SIZE
    assert ax_vol.yaxis.label.get_fontsize() == CHART_TEXT_SIZE
    assert ax_vol.get_xlabel() == "", \
        f"volume 子图不应有 xlabel('Bar Index'),实际: {ax_vol.get_xlabel()!r}"

    # tick labels (price + volume)
    for ax in (ax_price, ax_vol):
        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            assert tick.get_fontsize() == CHART_TEXT_SIZE, \
                f"tick fontsize 应为 {CHART_TEXT_SIZE}，实际: {tick.get_fontsize()}"

    # offset text (例如 volume 轴的 "1e7")
    assert ax_price.yaxis.get_offset_text().get_fontsize() == CHART_TEXT_SIZE
    assert ax_vol.yaxis.get_offset_text().get_fontsize() == CHART_TEXT_SIZE

    # candlestick.py 注入的 "Interval: 1M(21)" 等额外文本统一到 CHART_TEXT_SIZE
    # (candlestick 默认 fontsize=17,本模块负责覆盖)
    for txt in ax_price.texts:
        assert txt.get_fontsize() == CHART_TEXT_SIZE, \
            f"ax_price.texts 字号未覆盖: {txt.get_text()!r} -> {txt.get_fontsize()}"


def test_render_drops_anonymized_suffix():
    """标题不再带 (anonymized) 后缀 — 用户决策"""
    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
    )
    n = 10
    df = pd.DataFrame({
        "open": np.linspace(10, 12, n), "high": np.linspace(11, 13, n),
        "low": np.linspace(9, 11, n), "close": np.linspace(10, 12, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    fig = _build_figure_for_inspection(df, bo_index=8, left_index=2)
    assert fig.axes[0].get_title() == "Breakout sample"


def test_render_removes_interval_and_shows_bar_count():
    """candlestick.py 注入的 "Interval: 1M(21)" 必须移除;改用 "Bar Count: N" 在
    volume 子图底部展示窗口 K 线根数(N = bo_index - left_index + 1)。
    """
    from BreakoutStrategy.feature_library.sample_renderer import (
        _build_figure_for_inspection,
        CHART_TEXT_SIZE,
    )

    n = 60
    df = pd.DataFrame({
        "open": np.linspace(10, 20, n), "high": np.linspace(11, 21, n),
        "low": np.linspace(9, 19, n), "close": np.linspace(10, 20, n),
        "volume": np.full(n, 1e6),
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))

    left, bo = 5, 24  # 期望窗口 = 24 - 5 + 1 = 20 根
    fig = _build_figure_for_inspection(df, bo_index=bo, left_index=left)
    ax_price, ax_vol = fig.axes

    # 1. ax_price 上不应有 "Interval:" 开头的注释
    interval_texts = [t for t in ax_price.texts if t.get_text().startswith("Interval:")]
    assert not interval_texts, \
        f"chart.png 不应保留 candlestick 的 Interval 注释,实际: {[t.get_text() for t in interval_texts]}"

    # 2. ax_vol 底部应有 "Bar Count: 20" 文本,字号 = CHART_TEXT_SIZE
    bar_count_texts = [t for t in ax_vol.texts if t.get_text().startswith("Bar Count:")]
    assert len(bar_count_texts) == 1, \
        f"volume 底部应有 1 条 Bar Count 注释,实际: {[t.get_text() for t in ax_vol.texts]}"
    assert bar_count_texts[0].get_text() == f"Bar Count: {bo - left + 1}", \
        f"实际: {bar_count_texts[0].get_text()!r}"
    assert bar_count_texts[0].get_fontsize() == CHART_TEXT_SIZE
