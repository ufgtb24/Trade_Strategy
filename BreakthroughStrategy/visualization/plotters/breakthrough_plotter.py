"""突破检测绘图器"""

from typing import List, Optional

import matplotlib.pyplot as plt
import pandas as pd

from ..components import CandlestickComponent, MarkerComponent, PanelComponent
from ..utils import ensure_datetime_index
from .base_plotter import BasePlotter


class BreakthroughPlotter(BasePlotter):
    """突破检测可视化工具"""

    def __init__(self, style: str = "seaborn-v0_8-darkgrid"):
        """
        初始化绘图器

        Args:
            style: matplotlib 样式
        """
        super().__init__(style)
        self.candlestick = CandlestickComponent()
        self.marker = MarkerComponent()
        self.panel = PanelComponent()

    def plot_full_analysis(
        self,
        df: pd.DataFrame,
        breakthroughs: List,
        detector=None,
        title: Optional[str] = None,
        save_path: Optional[str] = None,
        show: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        colors: dict = None,
    ):
        """
        绘制完整分析图

        Args:
            df: OHLCV DataFrame
            breakthroughs: Breakthrough 对象列表
            detector: BreakthroughDetector 实例 (获取 active_peaks)
            title: 图表标题
            save_path: 保存路径 (可选)
            show: 是否显示图表
            start_date: 开始日期 (可选)
            end_date: 结束日期 (可选)
            colors: 颜色配置字典 (可选)
        """
        # 准备数据
        df = self.prepare_data(df, start_date, end_date)

        # 如果未提供颜色，尝试加载配置
        if colors is None:
            try:
                from ..interactive.ui_config_loader import get_ui_config_loader

                loader = get_ui_config_loader()
                colors = loader.get_colors()
            except Exception:
                colors = {}

        # 创建图表布局
        fig, axes = self.create_figure(
            figsize=(16, 10), nrows=3, height_ratios=[3, 1, 0.3]
        )

        ax_main, ax_volume, ax_stats = axes

        # 1. 绘制 K线图
        self.candlestick.draw(ax_main, df, colors=colors)

        # 2. 绘制峰值标记
        active_peaks = []
        if detector and hasattr(detector, "active_peaks"):
            active_peaks = detector.active_peaks
            self.marker.draw_peaks(
                ax_main, df, active_peaks, quality_color_map=True, colors=colors
            )

        # 3. 绘制突破标记
        self.marker.draw_breakthroughs(
            ax_main,
            df,
            breakthroughs,
            highlight_multi_peak=True,
            peaks=active_peaks,  # 传入 peaks 以处理重叠
            colors=colors,
        )

        # 4. 绘制阻力区
        self.marker.draw_resistance_zones(
            ax_main, df, breakthroughs, alpha=0.15, colors=colors
        )

        # 5. 绘制成交量
        breakthrough_dates = [df.index[bt.index] for bt in breakthroughs]
        self.candlestick.draw_volume(
            ax_volume, df, highlight_dates=breakthrough_dates, colors=colors
        )

        # 6. 绘制统计面板
        self.panel.draw_statistics_panel(ax_stats, breakthroughs)

        # 7. 添加标题和图例
        if title is None:
            title = (
                f"Breakthrough Analysis ({len(breakthroughs)} breakthroughs detected)"
            )

        self.add_title(fig, title)
        self.add_legend(ax_main)

        # 8. 保存或显示
        self.show_or_save(fig, save_path, show)

    def plot_breakout_detail(
        self,
        df: pd.DataFrame,
        breakthrough,
        context_days: int = 50,
        save_path: Optional[str] = None,
        show: bool = True,
    ):
        """
        绘制单个突破的详细视图

        Args:
            df: OHLCV DataFrame
            breakthrough: Breakthrough 对象
            context_days: 突破前后显示的天数
            save_path: 保存路径
            show: 是否显示图表
        """
        # 准备数据
        df = ensure_datetime_index(df)

        # 确定日期范围
        bt_index = breakthrough.index
        start_index = max(0, bt_index - context_days)
        end_index = min(len(df) - 1, bt_index + context_days)

        # 过滤数据
        df_subset = df.iloc[start_index : end_index + 1]

        # 创建图表布局
        fig, axes = self.create_figure(
            figsize=(14, 9), nrows=3, height_ratios=[3, 1, 0.5]
        )

        ax_main, ax_volume, ax_detail = axes

        # 1. 绘制 K线图
        self.candlestick.draw(ax_main, df_subset)

        # 2. 绘制被突破的峰值
        # 调整峰值索引到子集
        adjusted_peaks = []
        for peak in breakthrough.broken_peaks:
            if start_index <= peak.index <= end_index:
                adjusted_peak = type(peak)(**vars(peak))
                adjusted_peak.index = peak.index - start_index
                adjusted_peaks.append(adjusted_peak)

        self.marker.draw_peaks(
            ax_main, df_subset, adjusted_peaks, quality_color_map=True
        )

        # 3. 绘制突破标记
        adjusted_bt = type(breakthrough)(**vars(breakthrough))
        adjusted_bt.index = bt_index - start_index

        self.marker.draw_breakthroughs(
            ax_main,
            df_subset,
            [adjusted_bt],
            highlight_multi_peak=True,
            peaks=adjusted_peaks,  # 传入 peaks 以处理重叠
        )

        # 4. 绘制阻力区价格线
        if breakthrough.broken_peaks:
            prices = [p.price for p in breakthrough.broken_peaks]
            zone_bottom = min(prices)
            zone_top = max(prices)

            ax_main.axhspan(
                zone_bottom,
                zone_top,
                color="#FFEB3B",
                alpha=0.2,
                zorder=1,
                label="Resistance Zone",
            )

        # 5. 绘制成交量
        bt_date = df_subset.index[adjusted_bt.index]
        self.candlestick.draw_volume(ax_volume, df_subset, highlight_dates=[bt_date])

        # 6. 绘制详情面板
        self.panel.draw_breakthrough_detail_panel(ax_detail, breakthrough)

        # 7. 添加标题和图例
        title = f"Breakthrough Detail: {breakthrough.date.strftime('%Y-%m-%d')}"
        subtitle = (
            f"{breakthrough.num_peaks_broken} peaks broken | Quality: {breakthrough.quality_score:.1f}"
            if breakthrough.quality_score
            else ""
        )

        self.add_title(fig, title, subtitle)
        self.add_legend(ax_main)

        # 8. 保存或显示
        self.show_or_save(fig, save_path, show)

    def plot_parameter_comparison(
        self,
        df: pd.DataFrame,
        param_results: dict,
        param_name: str,
        param_values: list,
        save_path: Optional[str] = None,
        show: bool = True,
    ):
        """
        绘制参数对比图

        Args:
            df: OHLCV DataFrame
            param_results: {param_value: (breakthroughs, detector)} 字典
            param_name: 参数名称 (如 'window')
            param_values: 参数值列表 (如 [3,5,7,10])
            save_path: 保存路径
            show: 是否显示图表
        """
        df = ensure_datetime_index(df)

        n_params = len(param_values)
        nrows = (n_params + 1) // 2  # 2列布局

        fig, axes = plt.subplots(
            nrows=nrows, ncols=2, figsize=(20, 5 * nrows), sharex=True, sharey=True
        )

        axes = axes.flatten() if n_params > 1 else [axes]

        # 为每个参数值绘制子图
        for i, param_value in enumerate(param_values):
            ax = axes[i]

            if param_value not in param_results:
                ax.text(
                    0.5,
                    0.5,
                    f"No data for {param_name}={param_value}",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
                continue

            breakthroughs, detector = param_results[param_value]

            # 绘制 K线图
            self.candlestick.draw(ax, df)

            # 绘制峰值
            active_peaks = []
            if detector and hasattr(detector, "active_peaks"):
                active_peaks = detector.active_peaks
                self.marker.draw_peaks(ax, df, active_peaks, quality_color_map=True)

            # 绘制突破
            self.marker.draw_breakthroughs(
                ax, df, breakthroughs, highlight_multi_peak=True, peaks=active_peaks
            )

            # 添加子标题
            quality_scores = [
                bt.quality_score for bt in breakthroughs if bt.quality_score
            ]
            avg_quality = (
                sum(quality_scores) / len(quality_scores) if quality_scores else 0
            )

            ax.set_title(
                f"{param_name}={param_value}: {len(breakthroughs)} BTs | Avg Q={avg_quality:.1f}",
                fontsize=11,
                weight="bold",
            )

            ax.grid(True, alpha=0.3, linestyle="--")

        # 隐藏多余的子图
        for i in range(n_params, len(axes)):
            axes[i].axis("off")

        # 添加主标题
        self.add_title(fig, f"Parameter Comparison: {param_name}")

        plt.tight_layout()

        # 保存或显示
        self.show_or_save(fig, save_path, show)

    def plot_multi_peak_cases(
        self,
        df: pd.DataFrame,
        multi_peak_breakthroughs: List,
        top_n: int = 6,
        save_path: Optional[str] = None,
        show: bool = True,
    ):
        """
        绘制多峰值突破案例集

        Args:
            df: OHLCV DataFrame
            multi_peak_breakthroughs: 多峰值突破列表
            top_n: 显示前N个案例
            save_path: 保存路径
            show: 是否显示图表
        """
        df = ensure_datetime_index(df)

        # 按峰值数量排序
        multi_peak_breakthroughs = sorted(
            multi_peak_breakthroughs, key=lambda bt: bt.num_peaks_broken, reverse=True
        )[:top_n]

        if not multi_peak_breakthroughs:
            print("No multi-peak breakthroughs to display")
            return

        # 创建网格布局
        nrows = (top_n + 2) // 3  # 3列布局
        ncols = min(3, top_n)

        fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(18, 5 * nrows))

        axes = axes.flatten() if top_n > 1 else [axes]

        # 为每个案例绘制子图
        for i, bt in enumerate(multi_peak_breakthroughs):
            ax = axes[i]

            # 确定日期范围
            context_days = 50
            bt_index = bt.index
            start_index = max(0, bt_index - context_days)
            end_index = min(len(df) - 1, bt_index + context_days)

            df_subset = df.iloc[start_index : end_index + 1]

            # 绘制 K线图
            self.candlestick.draw(ax, df_subset)

            # 调整峰值和突破的索引
            adjusted_peaks = []
            for peak in bt.broken_peaks:
                if start_index <= peak.index <= end_index:
                    adjusted_peak = type(peak)(**vars(peak))
                    adjusted_peak.index = peak.index - start_index
                    adjusted_peaks.append(adjusted_peak)

            adjusted_bt = type(bt)(**vars(bt))
            adjusted_bt.index = bt_index - start_index

            # 绘制标记
            self.marker.draw_peaks(
                ax, df_subset, adjusted_peaks, quality_color_map=True
            )
            self.marker.draw_breakthroughs(
                ax,
                df_subset,
                [adjusted_bt],
                highlight_multi_peak=True,
                peaks=adjusted_peaks,
            )

            # 添加子标题
            quality_str = f"Q={bt.quality_score:.0f}" if bt.quality_score else ""
            ax.set_title(
                f"{bt.date.strftime('%Y-%m-%d')}: {bt.num_peaks_broken} peaks {quality_str}",
                fontsize=10,
                weight="bold",
            )

            ax.grid(True, alpha=0.3, linestyle="--")

        # 隐藏多余的子图
        for i in range(len(multi_peak_breakthroughs), len(axes)):
            axes[i].axis("off")

        # 添加主标题
        self.add_title(
            fig, f"Top {len(multi_peak_breakthroughs)} Multi-Peak Breakthroughs"
        )

        plt.tight_layout()

        # 保存或显示
        self.show_or_save(fig, save_path, show)
