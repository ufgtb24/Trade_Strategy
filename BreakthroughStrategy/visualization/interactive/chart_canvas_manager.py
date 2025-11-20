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

        # 2. 创建新图表（完全复用BreakthroughPlotter逻辑）
        self.fig = plt.Figure(figsize=(12, 8), dpi=100)
        axes = self.fig.subplots(3, 1, height_ratios=[3, 1, 0.3])
        ax_main, ax_volume, ax_stats = axes

        # 设置全局字体大小
        plt.rcParams.update({
            'font.size': 12,
            'axes.titlesize': 14,
            'axes.labelsize': 12,
            'xtick.labelsize': 11,
            'ytick.labelsize': 11,
            'legend.fontsize': 11
        })

        # 3. 调用现有组件绘图（完全复用）
        self.plotter.candlestick.draw(ax_main, df)

        if detector and hasattr(detector, 'active_peaks'):
            self.plotter.marker.draw_peaks(
                ax_main, df, detector.active_peaks,
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

        breakthrough_dates = [df.index[bt.index] for bt in breakthroughs]
        self.plotter.candlestick.draw_volume(
            ax_volume, df,
            highlight_dates=breakthrough_dates
        )

        self.plotter.panel.draw_statistics_panel(ax_stats, breakthroughs)

        # 添加标题
        ax_main.set_title(f"{symbol} - Breakthrough Analysis ({len(breakthroughs)} breakthroughs)",
                         fontsize=16, fontweight='bold')

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
            fontsize=11
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
