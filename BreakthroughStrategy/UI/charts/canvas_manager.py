"""图表Canvas管理器"""

import tkinter as tk
from typing import Optional, List

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..styles import get_chart_colors
from .components import CandlestickComponent, MarkerComponent, PanelComponent, ScoreDetailWindow
from ...analysis.quality_scorer import QualityScorer
from ...analysis.breakthrough_detector import Peak, Breakthrough


class ChartCanvasManager:
    """图表Canvas管理器"""

    def __init__(self, parent_container, scorer: Optional[QualityScorer] = None):
        """
        初始化图表管理器

        Args:
            parent_container: 父容器
            scorer: 质量评分器实例（用于评分详情窗口）
        """
        self.container = parent_container
        # 直接使用绘图组件
        self.candlestick = CandlestickComponent()
        self.marker = MarkerComponent()
        self.panel = PanelComponent()
        self.canvas = None
        self.fig = None
        self.annotation = None  # 用于悬停显示
        self.crosshair_v = None  # 垂直十字线
        self.crosshair_h = None  # 水平十字线

        # 评分详情窗口相关
        self.scorer = scorer or QualityScorer()
        self.score_detail_windows: List[ScoreDetailWindow] = []  # 打开的窗口列表
        self._hovered_peak: Optional[Peak] = None  # 当前悬停的峰值
        self._hovered_bt: Optional[Breakthrough] = None  # 当前悬停的突破
        self._hover_position: tuple = (0, 0)  # 悬停位置（屏幕坐标）
        self._all_peaks: List[Peak] = []  # 所有峰值（用于查找）
        self._all_breakthroughs: List[Breakthrough] = []  # 所有突破（用于查找）

    def update_chart(
        self,
        df: pd.DataFrame,
        breakthroughs: list,
        detector,
        symbol: str,
        display_options: dict = None,
    ):
        """
        更新图表显示

        Args:
            df: OHLCV数据
            breakthroughs: 突破列表
            detector: 检测器实例（用于获取active_peaks）
            symbol: 股票代码
            display_options: 显示选项
        """
        # 1. 清理旧图表（防内存泄漏）
        self._cleanup()

        display_options = display_options or {}
        show_peak_score = display_options.get("show_peak_score", True)
        show_bt_score = display_options.get("show_bt_score", True)

        # 2. 创建新图表（2个子图：主图+统计面板）
        # 动态计算图表大小，适应容器尺寸
        self.container.update_idletasks()  # 强制更新容器尺寸
        container_width = self.container.winfo_width()
        container_height = self.container.winfo_height()
        dpi = 100

        # 计算合适的figsize（单位：英寸）
        # 如果容器尺寸太小（窗口未初始化），使用默认值
        if container_width < 100 or container_height < 100:
            fig_width, fig_height = 12, 8
        else:
            fig_width = container_width / dpi
            fig_height = container_height / dpi

        self.fig = plt.Figure(figsize=(fig_width, fig_height), dpi=dpi)
        self.fig.patch.set_facecolor("white")  # 设置背景为白色
        axes = self.fig.subplots(2, 1, height_ratios=[10, 0.3])
        ax_main, ax_stats = axes

        # 设置坐标系背景和边框
        for ax in axes:
            ax.set_facecolor("white")
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_color("black")
                spine.set_linewidth(1.0)

        # 优化布局边距，减少空白区域，顶到最上沿
        # left=0.02 减少左侧留白
        self.fig.subplots_adjust(
            left=0.03, right=0.98, top=0.99, bottom=0.02, hspace=0.01
        )

        # 设置全局字体大小（2倍放大）
        plt.rcParams.update(
            {
                "font.size": 32,
                "axes.titlesize": 40,
                "axes.labelsize": 28,
                "xtick.labelsize": 22,
                "ytick.labelsize": 22,
                "legend.fontsize": 26,
            }
        )

        # 获取颜色配置
        colors = get_chart_colors()

        # 3. 调用现有组件绘图
        # 先绘制成交量作为背景
        breakthrough_dates = [df.index[bt.index] for bt in breakthroughs]
        self.candlestick.draw_volume_background(
            ax_main, df, highlight_dates=breakthrough_dates, colors=colors
        )

        # 然后绘制K线（叠加在成交量上）
        self.candlestick.draw(ax_main, df, colors=colors)

        # 收集所有被突破的峰值
        all_broken_peaks = []
        for bt in breakthroughs:
            if hasattr(bt, "broken_peaks") and bt.broken_peaks:
                all_broken_peaks.extend(bt.broken_peaks)

        # 绘制被突破的峰值（如果有）
        if all_broken_peaks:
            self.marker.draw_peaks(
                ax_main,
                df,
                all_broken_peaks,
                quality_color_map=True,
                colors=colors,
                show_score=show_peak_score,
            )

        # 额外绘制 active_peaks（如果存在且不重复）
        active_only_peaks = []
        if detector and hasattr(detector, "active_peaks"):
            # 过滤掉已经在 broken_peaks 中的峰值
            broken_peak_indices = {p.index for p in all_broken_peaks}
            active_only_peaks = [
                p for p in detector.active_peaks if p.index not in broken_peak_indices
            ]
            if active_only_peaks:
                self.marker.draw_peaks(
                    ax_main,
                    df,
                    active_only_peaks,
                    quality_color_map=True,
                    colors=colors,
                    show_score=show_peak_score,
                )

        # 合并所有绘制的 peaks，用于碰撞检测
        all_drawn_peaks = all_broken_peaks + active_only_peaks

        self.marker.draw_breakthroughs(
            ax_main,
            df,
            breakthroughs,
            highlight_multi_peak=True,
            peaks=all_drawn_peaks,  # 传入 peaks 以处理重叠
            colors=colors,
            show_score=show_bt_score,
        )

        self.marker.draw_resistance_zones(
            ax_main, df, breakthroughs, alpha=0.15, color=None, colors=colors
        )

        self.panel.draw_statistics_panel(ax_stats, breakthroughs)

        # 不添加标题，因为信息已显示在UI右上角，避免浪费空间

        # 4. 嵌入Tkinter Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()

        # 5. 绑定鼠标悬停事件
        self._attach_hover(ax_main, df, breakthroughs, peaks=all_drawn_peaks)

    def _cleanup(self):
        """清理旧图表，防止内存泄漏"""
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None

        if self.fig:
            plt.close(self.fig)
            self.fig = None

        self.annotation = None
        self.crosshair_v = None
        self.crosshair_h = None

        # 清理评分详情窗口相关状态
        self._hovered_peak = None
        self._hovered_bt = None
        self._all_peaks = []
        self._all_breakthroughs = []
        # 注意：不关闭已打开的窗口，让用户可以继续查看

    def _attach_hover(self, ax, df, breakthroughs, peaks=None):
        """
        绑定鼠标悬停事件

        Args:
            ax: 主axes
            df: 数据
            breakthroughs: 突破列表
            peaks: 峰值列表 (可选)
        """
        # 保存数据供快捷键回调使用
        self._all_peaks = peaks or []
        self._all_breakthroughs = breakthroughs or []

        # 创建十字线（初始隐藏）
        self.crosshair_v = ax.axvline(
            0, color="#0088CC", linestyle="--", linewidth=1.5, alpha=0.7, visible=False
        )
        self.crosshair_h = ax.axhline(
            0, color="#0088CC", linestyle="--", linewidth=1.5, alpha=0.7, visible=False
        )

        # 创建annotation（用于显示悬停信息）
        self.annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(20, 20),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="w", alpha=0.9),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
            fontsize=22,  # 字体减小一半
            zorder=100,  # 最上层
        )
        self.annotation.set_linespacing(1.5)  # 设置行距为 1.5 倍
        self.annotation.set_visible(False)

        def on_hover(event):
            """鼠标悬停回调"""
            if event.inaxes != ax:
                self.annotation.set_visible(False)
                self.crosshair_v.set_visible(False)
                self.crosshair_h.set_visible(False)
                # 清除悬停状态
                self._hovered_peak = None
                self._hovered_bt = None
                self.canvas.draw_idle()
                return

            if event.xdata is None:
                return

            # 计算最近的数据点
            x = int(round(event.xdata))
            if x < 0 or x >= len(df):
                self.annotation.set_visible(False)
                self.crosshair_v.set_visible(False)
                self.crosshair_h.set_visible(False)
                # 清除悬停状态
                self._hovered_peak = None
                self._hovered_bt = None
                self.canvas.draw_idle()
                return

            # 保存悬停位置（屏幕坐标）
            canvas_widget = self.canvas.get_tk_widget()
            self._hover_position = (
                canvas_widget.winfo_rootx() + event.x,
                canvas_widget.winfo_rooty() + event.y
            )

            # 获取数据
            row = df.iloc[x]
            date = df.index[x]

            # 重置悬停状态
            self._hovered_peak = None
            self._hovered_bt = None

            # 构建显示文本
            text = f"Date: {date.strftime('%Y-%m-%d')}\n"
            text += f"Open: {row['open']:.2f}\n"
            text += f"High: {row['high']:.2f}\n"
            text += f"Low: {row['low']:.2f}\n"
            text += f"Close: {row['close']:.2f}\n"
            text += f"Volume: {int(row['volume']):,}"

            # 检查是否是突破点
            for bt in breakthroughs:
                if bt.index == x:
                    self._hovered_bt = bt  # 记录悬停的突破
                    text += "\n\n* Breakthrough!"
                    text += f"\nPeaks Broken: {bt.num_peaks_broken}"
                    if hasattr(bt, "broken_peak_ids") and bt.broken_peak_ids:
                        peak_ids_text = ", ".join(map(str, bt.broken_peak_ids))
                        text += f"\nPeak IDs: [{peak_ids_text}]"
                    if bt.quality_score:
                        text += f"\nQuality: {bt.quality_score:.1f}"
                    text += "\n[Press D for details]"
                    break

            # 检查是否是峰值
            if peaks:
                for peak in peaks:
                    if peak.index == x:
                        self._hovered_peak = peak  # 记录悬停的峰值
                        text += "\n\n▼ Peak"
                        if peak.id is not None:
                            text += f"\nID: {peak.id}"
                        if peak.quality_score is not None:
                            text += f"\nScore: {peak.quality_score:.1f}"
                        text += "\n[Press D for details]"
                        break

            # 更新十字线位置（指示实际的 K线数据点）
            self.crosshair_v.set_xdata(x)
            self.crosshair_h.set_ydata(row["close"])
            self.crosshair_v.set_visible(True)
            self.crosshair_h.set_visible(True)

            # 始终显示在鼠标右上角
            # 偏移量要足够大，避免遮挡鼠标
            offset_x = 40
            offset_y = 40

            # 更新annotation（锚点在鼠标位置，不在 K线数据点）
            self.annotation.xy = (event.xdata, event.ydata)  # 锚点在鼠标位置
            self.annotation.xyann = (offset_x, offset_y)  # 固定右上角偏移
            self.annotation.set_text(text)
            self.annotation.set_visible(True)
            self.canvas.draw_idle()

        # 绑定 matplotlib 鼠标移动事件
        self.canvas.mpl_connect("motion_notify_event", on_hover)

        # 绑定快捷键事件（需要绑定到 tk widget）
        canvas_widget = self.canvas.get_tk_widget()

        # 确保 canvas 可以接收键盘焦点
        canvas_widget.configure(takefocus=True)

        # 绑定 D 键显示评分详情
        canvas_widget.bind("<d>", self._on_score_detail_key)
        canvas_widget.bind("<D>", self._on_score_detail_key)

        # 绑定 Escape 键关闭最近的窗口
        canvas_widget.bind("<Escape>", self._on_close_window_key)

        # 绑定 Shift+Escape 关闭所有窗口
        canvas_widget.bind("<Shift-Escape>", self._on_close_all_windows_key)

        # 鼠标点击时让 canvas 获得焦点（以便接收键盘事件）
        canvas_widget.bind("<Button-1>", lambda e: canvas_widget.focus_set())

    def _on_score_detail_key(self, event):
        """
        D 键按下回调：显示评分详情窗口

        Args:
            event: Tkinter 键盘事件
        """
        # 检查是否有悬停的峰值或突破
        if self._hovered_peak is None and self._hovered_bt is None:
            return  # 没有悬停在任何标记点上，忽略

        # 创建评分详情窗口
        window = ScoreDetailWindow(
            parent=self.container,
            peak=self._hovered_peak,
            breakthrough=self._hovered_bt,
            scorer=self.scorer,
            position=self._hover_position
        )

        # 添加到窗口列表
        self.score_detail_windows.append(window)

        # 清理已关闭的窗口
        self._cleanup_closed_windows()

    def _on_close_window_key(self, event):
        """
        Escape 键按下回调：关闭最近打开的窗口

        Args:
            event: Tkinter 键盘事件
        """
        self._cleanup_closed_windows()

        if self.score_detail_windows:
            window = self.score_detail_windows.pop()
            window.close()

    def _on_close_all_windows_key(self, event):
        """
        Shift+Escape 键按下回调：关闭所有窗口

        Args:
            event: Tkinter 键盘事件
        """
        for window in self.score_detail_windows:
            window.close()
        self.score_detail_windows.clear()

    def _cleanup_closed_windows(self):
        """清理已关闭的窗口"""
        self.score_detail_windows = [
            w for w in self.score_detail_windows if w.is_open()
        ]

    def close_all_score_windows(self):
        """关闭所有评分详情窗口（供外部调用）"""
        self._on_close_all_windows_key(None)
