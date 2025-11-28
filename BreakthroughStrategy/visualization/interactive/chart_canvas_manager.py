"""图表Canvas管理器"""
import tkinter as tk
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from typing import Optional

from BreakthroughStrategy.visualization import BreakthroughPlotter


class ChartCanvasManager:
    """图表Canvas管理器"""

    def __init__(self, parent_container):
        """
        初始化图表管理器

        Args:
            parent_container: 父容器
        """
        self.container = parent_container
        self.plotter = BreakthroughPlotter()  # 复用现有绘图器
        self.canvas = None
        self.fig = None
        self.annotation = None  # 用于悬停显示

    def update_chart(self, df: pd.DataFrame, breakthroughs: list, detector,
                    symbol: str):
        """
        更新图表显示

        Args:
            df: OHLCV数据
            breakthroughs: 突破列表
            detector: 检测器实例（用于获取active_peaks）
            symbol: 股票代码
        """
        # 1. 清理旧图表（防内存泄漏）
        self._cleanup()

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
        axes = self.fig.subplots(2, 1, height_ratios=[10, 0.3])
        ax_main, ax_stats = axes

        # 优化布局边距，减少空白区域，顶到最上沿
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.99, bottom=0.08, hspace=0.15)

        # 设置全局字体大小（2倍放大）
        plt.rcParams.update({
            'font.size': 32,
            'axes.titlesize': 40,
            'axes.labelsize': 28,
            'xtick.labelsize': 22,
            'ytick.labelsize': 22,
            'legend.fontsize': 26
        })

        # 3. 调用现有组件绘图
        # 先绘制成交量作为背景
        breakthrough_dates = [df.index[bt.index] for bt in breakthroughs]
        self.plotter.candlestick.draw_volume_background(
            ax_main, df,
            highlight_dates=breakthrough_dates
        )

        # 然后绘制K线（叠加在成交量上）
        self.plotter.candlestick.draw(ax_main, df)

        # 收集所有被突破的峰值
        all_broken_peaks = []
        for bt in breakthroughs:
            if hasattr(bt, 'broken_peaks') and bt.broken_peaks:
                all_broken_peaks.extend(bt.broken_peaks)

        # 绘制被突破的峰值（如果有）
        if all_broken_peaks:
            self.plotter.marker.draw_peaks(
                ax_main, df, all_broken_peaks,
                quality_color_map=True
            )

        # 额外绘制 active_peaks（如果存在且不重复）
        if detector and hasattr(detector, 'active_peaks'):
            # 过滤掉已经在 broken_peaks 中的峰值
            broken_peak_indices = {p.index for p in all_broken_peaks}
            active_only_peaks = [p for p in detector.active_peaks
                               if p.index not in broken_peak_indices]
            if active_only_peaks:
                self.plotter.marker.draw_peaks(
                    ax_main, df, active_only_peaks,
                    quality_color_map=True
                )

        self.plotter.marker.draw_breakthroughs(
            ax_main, df, breakthroughs,
            highlight_multi_peak=True
        )

        self.plotter.marker.draw_resistance_zones(
            ax_main, df, breakthroughs,
            alpha=0.15
        )

        self.plotter.panel.draw_statistics_panel(ax_stats, breakthroughs)

        # 不添加标题，因为信息已显示在UI右上角，避免浪费空间

        # 4. 嵌入Tkinter Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()

        # 5. 绑定鼠标悬停事件
        self._attach_hover(ax_main, df, breakthroughs)

    def _cleanup(self):
        """清理旧图表，防止内存泄漏"""
        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None

        if self.fig:
            plt.close(self.fig)
            self.fig = None

        self.annotation = None

    def _attach_hover(self, ax, df, breakthroughs):
        """
        绑定鼠标悬停事件

        Args:
            ax: 主axes
            df: 数据
            breakthroughs: 突破列表
        """
        # 创建annotation（用于显示悬停信息）
        self.annotation = ax.annotate(
            "", xy=(0, 0), xytext=(20, 20),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="w", alpha=0.9),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
            fontsize=36
        )
        self.annotation.set_visible(False)

        def on_hover(event):
            """鼠标悬停回调"""
            if event.inaxes != ax:
                self.annotation.set_visible(False)
                self.canvas.draw_idle()
                return

            if event.xdata is None:
                return

            # 计算最近的数据点
            x = int(round(event.xdata))
            if x < 0 or x >= len(df):
                self.annotation.set_visible(False)
                self.canvas.draw_idle()
                return

            # 获取数据
            row = df.iloc[x]
            date = df.index[x]

            # 构建显示文本
            text = f"Date: {date.strftime('%Y-%m-%d')}\n"
            text += f"Open: ${row['open']:.2f}\n"
            text += f"High: ${row['high']:.2f}\n"
            text += f"Low: ${row['low']:.2f}\n"
            text += f"Close: ${row['close']:.2f}\n"
            text += f"Volume: {int(row['volume']):,}"

            # 检查是否是突破点
            for bt in breakthroughs:
                if bt.index == x:
                    text += f"\n\n★ Breakthrough!"
                    text += f"\nPeaks Broken: {bt.num_peaks_broken}"
                    if bt.quality_score:
                        text += f"\nQuality: {bt.quality_score:.1f}"
                    break

            # 更新annotation
            self.annotation.xy = (x, row['close'])
            self.annotation.set_text(text)
            self.annotation.set_visible(True)
            self.canvas.draw_idle()

        # 绑定事件
        self.canvas.mpl_connect('motion_notify_event', on_hover)
