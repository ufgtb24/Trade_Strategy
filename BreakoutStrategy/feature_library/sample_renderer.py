"""渲染 samples/<id>/chart.png — AI 友好的静态脱敏 K 线图。

复用 BreakoutStrategy/UI/charts/components/candlestick.py 的
CandlestickComponent.draw 在 matplotlib Axes 上绘制 K 线主体；
本模块负责构造 Figure、添加 volume subplot、按 [left_index, bo_index]
收窄渲染窗口、导出 PNG（不交互、固定尺寸、统一风格）。

OO API 设计：使用 matplotlib.figure.Figure + FigureCanvasAgg 直接渲染，
不调 matplotlib.use() / pyplot —— 避免污染调用方进程的全局 backend
（dev UI 的 TkAgg 同进程调用此模块时尤其关键）。

视觉脱敏（归一化方案 B）：chart.png 不含 ticker / 日期 / 绝对价格，
仅显示相对 BO close 的百分比变化 —— 防止 GLM-4V 通过 OCR 标题/Y 轴恢复原始信息。
不含 pk/bo 垂直虚线，不含 legend，标题恒为 "Breakout sample"。
"""

from pathlib import Path

import matplotlib as mpl
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import FuncFormatter

from BreakoutStrategy.feature_library import paths
from BreakoutStrategy.UI.charts.components.candlestick import CandlestickComponent

CHART_DPI = 100
CHART_FIGSIZE = (12, 8)
PRICE_PANEL_RATIO = 3
VOLUME_PANEL_RATIO = 1
CHART_TEXT_SIZE = 10  # 全图统一字号(标题/坐标轴标签/tick/offset/candlestick 注入文本)


def _build_figure_for_inspection(
    df_window: pd.DataFrame, bo_index: int, left_index: int,
) -> Figure:
    """构造脱敏 K 线图 Figure（内部工具，单元测试用）。

    渲染窗口仅含 [left_index : bo_index + 1] 闭区间（用户挑的左端到 BO），
    不再画 pk/bo 虚线，不显示 legend，标题恒为 "Breakout sample"。
    Y 轴 pivot = df_window.iloc[bo_index]['close']（BO close = 0%）。

    Args:
        df_window: 完整 OHLCV DataFrame（local index 体系）
        bo_index:  突破日 index（df_window 局部）
        left_index: 用户挑选的左端 index（df_window 局部，< bo_index；
                    兼任 consolidation anchor）

    Returns:
        渲染完成的 matplotlib Figure（未落盘）
    """
    # 先计算 pivot（在切片前，避免 bo_index 在子 df 中失效）
    pivot_close = float(df_window.iloc[bo_index]["close"])
    sub_df = df_window.iloc[left_index : bo_index + 1]

    with mpl.rc_context({"font.size": CHART_TEXT_SIZE}):
        fig = Figure(figsize=CHART_FIGSIZE, dpi=CHART_DPI)
        FigureCanvasAgg(fig)

        gs = fig.add_gridspec(
            2, 1, height_ratios=[PRICE_PANEL_RATIO, VOLUME_PANEL_RATIO],
            hspace=0.05,
        )
        ax_price = fig.add_subplot(gs[0])
        ax_vol = fig.add_subplot(gs[1], sharex=ax_price)

        # 主图：K 线（只画收窄后的子 df，无 pk/bo 虚线）
        # candlestick.py 会在 ax_price 上注入 "Interval: 1M(21)" 文本,
        # 该信息对 GLM-4V 输入是噪音;移除并改用 "Bar Count: N" 在底部表达窗口长度。
        CandlestickComponent.draw(ax_price, sub_df)
        for txt in list(ax_price.texts):
            if txt.get_text().startswith("Interval:"):
                txt.remove()

        # 脱敏标题(无 anonymized 后缀)
        ax_price.set_title("Breakout sample", fontsize=CHART_TEXT_SIZE)
        ax_price.set_ylabel("Price (% from BO close)", fontsize=CHART_TEXT_SIZE)
        # 不设 legend（D-06）;不设 ax_vol xlabel("Bar Index"):用户要求移除底部冗余文字

        # Y 轴用 BO close 作 pivot，FuncFormatter 显示相对百分比
        def _pct_fmt(price: float, _pos: int) -> str:
            if pivot_close <= 0:
                return f"{price:.2f}"
            pct = (price - pivot_close) / pivot_close * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.1f}%"

        ax_price.yaxis.set_major_formatter(FuncFormatter(_pct_fmt))

        # 副图：volume bar（同样只画 sub_df，无 pk/bo 虚线）
        ax_vol.bar(
            range(len(sub_df)), sub_df["volume"], color="#888888", width=0.8,
        )
        ax_vol.set_ylabel("Volume", fontsize=CHART_TEXT_SIZE)
        ax_vol.grid(True, alpha=0.3)

        # 底部居中显示窗口 K 线根数(替代被移除的 "Interval: 1M(21)" + "Bar Index"):
        # 让 GLM-4V 直接读到样本的离散长度,而不需要数 K 线。
        n_bars = len(sub_df)
        ax_vol.text(
            0.5, -0.04, f"Bar Count: {n_bars}",
            transform=ax_vol.transAxes,
            ha="center", va="top",
            fontsize=CHART_TEXT_SIZE,
        )

        # 字号统一: title / labels / ticks / offset text / candlestick 注入文本 都到 CHART_TEXT_SIZE
        ax_price.tick_params(labelsize=CHART_TEXT_SIZE)
        ax_vol.tick_params(labelsize=CHART_TEXT_SIZE)
        ax_price.yaxis.get_offset_text().set_fontsize(CHART_TEXT_SIZE)
        ax_vol.yaxis.get_offset_text().set_fontsize(CHART_TEXT_SIZE)
        # candlestick.py 硬编码的 "Interval: 1M(21)" 等 ax_price.text 注入文本同步压缩
        for txt in ax_price.texts:
            txt.set_fontsize(CHART_TEXT_SIZE)
        for txt in ax_vol.texts:
            txt.set_fontsize(CHART_TEXT_SIZE)

        # 收紧 figure 四边空白(默认 ~10-15% margin → 5%)
        fig.subplots_adjust(left=0.06, right=0.99, top=0.94, bottom=0.05, hspace=0.05)

    return fig


def render_sample_chart(
    sample_id: str,
    df_window: pd.DataFrame,
    bo_index: int,
    left_index: int,
) -> Path:
    """渲染单个 breakout 样本的脱敏 K 线图为 PNG。

    sample_id 仅用于决定输出路径（samples/<id>/chart.png），
    不会出现在图像内容中（归一化方案 B —— AI 视角脱敏）。

    Args:
        sample_id: 样本 ID（仅用于路径，不写入图像）
        df_window: OHLCV DataFrame，DatetimeIndex
        bo_index:  突破日 index（df_window 局部）
        left_index: 用户挑的窗口左端 index（df_window 局部，< bo_index；
                    兼任 consolidation anchor）

    Returns:
        生成的 PNG 文件绝对路径
    """
    paths.ensure_sample_dir(sample_id)
    out_path = paths.chart_png_path(sample_id)

    fig = _build_figure_for_inspection(df_window, bo_index, left_index=left_index)
    # 直接通过 canvas 写文件，不走 pyplot.savefig（避免污染全局 figure 表）
    fig.canvas.print_png(out_path)
    return out_path
