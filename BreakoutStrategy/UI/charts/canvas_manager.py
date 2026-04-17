"""图表Canvas管理器"""

import tkinter as tk
from datetime import timedelta
from typing import Optional, List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..styles import get_chart_colors
from .components import CandlestickComponent, MarkerComponent, PanelComponent, ScoreDetailWindow
from .axes_interaction import AxesInteractionController
from .filter_range import compute_left_idx
from .tooltip_anchor import compute_tooltip_anchor
from ...analysis.breakout_scorer import BreakoutScorer
from ...analysis.breakout_detector import Peak, Breakout
from ...analysis.indicators import TechnicalIndicators


class ChartCanvasManager:
    """图表Canvas管理器"""

    def __init__(
        self,
        parent_container,
        breakout_scorer: Optional[BreakoutScorer] = None
    ):
        """
        初始化图表管理器

        Args:
            parent_container: 父容器
            breakout_scorer: 突破评分器实例
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
        self.breakout_scorer = breakout_scorer or BreakoutScorer()
        self.score_detail_windows: List[ScoreDetailWindow] = []  # 打开的窗口列表
        self._hovered_peak: Optional[Peak] = None  # 当前悬停的峰值
        self._hovered_bo: Optional[Breakout] = None  # 当前悬停的突破
        self._hover_position: tuple = (0, 0)  # 悬停位置（屏幕坐标）
        self._all_peaks: List[Peak] = []  # 所有峰值（用于查找）
        self._all_breakouts: List[Breakout] = []  # 所有突破（用于查找）
        self._current_symbol: str = ""  # 当前股票代码

        # Ctrl模式状态（自由Y轴悬停）
        self._ctrl_pressed: bool = False  # Ctrl键是否按下
        self._last_mouse_x: float = 0.0   # 鼠标X坐标（数据坐标系，实际位置）
        self._last_mouse_y: float = 0.0   # 鼠标Y坐标（数据坐标系）
        self._last_hover_x: int = 0       # 最近悬停的K线索引
        self._hover_df: Optional[pd.DataFrame] = None  # 保存df引用

        # ATR 相关（用于 tooltip 显示）
        self._atr_series: Optional[pd.Series] = None
        self._atr_period: int = 14
        # 放量倍数序列（用于 tooltip 显示 RV，与因子系统共用计算源）
        self._vol_ratio_series: Optional[pd.Series] = None

        # 交互控制器（滚轮水平缩放 + 右键水平拖拽平移）
        self.interaction: Optional[AxesInteractionController] = None

        # Filter 时间范围可视化：浅灰背景 Rectangle + 黑色虚线左边界
        self._filter_span = None
        self._filter_line = None

    def update_chart(
        self,
        df: pd.DataFrame,
        breakouts: list,
        active_peaks: list,
        superseded_peaks: list,
        symbol: str,
        display_options: dict = None,
        label_buffer_start_idx: int = None,
        template_matched_indices: list[int] = None,
        initial_window_days: int | None = None,
        filter_cutoff_date=None,
        spec=None,
    ):
        """
        更新图表显示

        Args:
            df: OHLCV数据
            breakouts: 突破列表
            active_peaks: 活跃峰值列表（用于绘制未被突破的峰值）
            superseded_peaks: 被新峰值取代的峰值列表
            symbol: 股票代码
            display_options: 显示选项
            label_buffer_start_idx: Label 缓冲区在 df 中的起始索引（用于视觉区分）
            template_matched_indices: 模板匹配命中的 K 线索引列表（用于绘制高亮条）
            initial_window_days: 初始显示窗口（日历日数），None 表示保留 candlestick 默认全范围
            filter_cutoff_date: Filter 时间范围可视化的截止日期，由 Task 5 的 _draw_filter_range 消费
            spec: ChartRangeSpec，可选。本 task 仅存储不消费
        """
        self._last_spec = spec

        # 1. 清理旧图表（防内存泄漏）
        self._cleanup()

        # 保存当前股票代码
        self._current_symbol = symbol

        display_options = display_options or {}
        show_bo_score = display_options.get("show_bo_score", True)
        show_superseded_peaks = display_options.get("show_superseded_peaks", False)

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
        breakout_dates = [df.index[bo.index] for bo in breakouts]
        self.candlestick.draw_volume_background(
            ax_main, df, highlight_dates=breakout_dates, colors=colors
        )

        # 然后绘制K线（叠加在成交量上）
        self.candlestick.draw(ax_main, df, colors=colors)

        # 收集所有被突破的峰值（按 id 去重，同一峰值可能因"突破巩固"被多次突破）
        seen_peak_ids = set()
        all_broken_peaks = []
        for bo in breakouts:
            if hasattr(bo, "broken_peaks") and bo.broken_peaks:
                for p in bo.broken_peaks:
                    if p.id not in seen_peak_ids:
                        seen_peak_ids.add(p.id)
                        all_broken_peaks.append(p)

        # 绘制被突破的峰值（如果有）
        if all_broken_peaks:
            self.marker.draw_peaks(
                ax_main,
                df,
                all_broken_peaks,
                colors=colors,
            )

        # 额外绘制 active_peaks（如果存在且不重复）
        active_only_peaks = []
        if active_peaks:
            # 过滤掉已经在 broken_peaks 中的峰值
            broken_peak_indices = {p.index for p in all_broken_peaks}
            active_only_peaks = [
                p for p in active_peaks if p.index not in broken_peak_indices
            ]
            if active_only_peaks:
                self.marker.draw_peaks(
                    ax_main,
                    df,
                    active_only_peaks,
                    colors=colors,
                )

        # 绘制被取代的峰值（如果启用）
        superseded_only_peaks = []
        if show_superseded_peaks and superseded_peaks:
            # 过滤掉已绘制的峰值（按 index 去重）
            drawn_indices = {p.index for p in all_broken_peaks + active_only_peaks}
            superseded_only_peaks = [
                p for p in superseded_peaks if p.index not in drawn_indices
            ]
            if superseded_only_peaks:
                self.marker.draw_peaks(
                    ax_main,
                    df,
                    superseded_only_peaks,
                    colors=colors,
                    style="superseded",
                )

        # 合并所有绘制的 peaks，用于碰撞检测
        all_drawn_peaks = all_broken_peaks + active_only_peaks + superseded_only_peaks

        # BO 绘制：live_mode=True 走新 4-tier 圆圈渲染；否则走 Dev UI 原路径
        _live_mode = display_options.get("live_mode", False)
        if _live_mode:
            self.marker.draw_breakouts_live_mode(
                ax_main,
                df,
                breakouts,
                current_bo_index=display_options.get("current_bo_index"),
                visible_matched_indices=display_options.get("visible_matched_indices", set()),
                filtered_out_matched_indices=display_options.get("filtered_out_matched_indices", set()),
                peaks=all_drawn_peaks,
                colors=colors,
            )
            # 暂存回调；pick_event 连线在 canvas 创建后进行（见下方）
            self._on_bo_picked_callback = display_options.get("on_bo_picked")
        else:
            self.marker.draw_breakouts(
                ax_main,
                df,
                breakouts,
                highlight_multi_peak=True,
                peaks=all_drawn_peaks,
                colors=colors,
                show_score=show_bo_score,
            )

        self.marker.draw_resistance_zones(
            ax_main, df, breakouts, alpha=0.15, color=None, colors=colors
        )

        # 绘制均线（从参数面板获取周期）
        from BreakoutStrategy.param_loader import get_param_loader
        loader = get_param_loader()
        feature_params = loader.get_feature_calculator_params()
        ma_period = feature_params.get("ma_period", 200)
        self.marker.draw_moving_averages(
            ax_main,
            df,
            ma_periods=[ma_period],
            colors=colors,
        )

        # 优先按 spec 绘三段；spec 为 None 时保留旧的 label_buffer 逻辑
        if self._last_spec is not None:
            self._draw_range_spec_shading(ax_main, df, self._last_spec)
        elif label_buffer_start_idx is not None and label_buffer_start_idx < len(df):
            self._draw_label_buffer_zone(ax_main, df, label_buffer_start_idx, colors)

        self.panel.draw_statistics_panel(ax_stats, breakouts)

        # 绘制模板匹配高亮条
        if template_matched_indices:
            self.marker.draw_template_highlights(ax_main, template_matched_indices)

        # 左侧 padding（与 candlestick.py:72 一致），供 data_span_left 界定 zoom-out 极限
        margin_left = max(1, len(df) * 0.02) if len(df) > 0 else 1

        # 3b. 计算 RIGHT_ALIGNED 模式所需几何：
        # - right_anchor：xlim_right 上限，= 最右 K 线右边缘 + initial_margin_right
        # - bar_anchor：最右 K 线右边缘数据位置，RA 模式缩放锚点（像素留白恒定）
        # - data_span_left：xlim_left 下限（全数据 + 左 padding）
        # initial_window_days=None 时退化为"全数据视图"，仍走双模式控制器。
        if len(df) > 0:
            if initial_window_days is not None:
                default_cutoff = df.index[-1] - timedelta(days=initial_window_days)
                visible_left_idx = compute_left_idx(df.index, default_cutoff)
            else:
                visible_left_idx = 0
            visible_bars = max(1, len(df) - visible_left_idx)
            initial_margin_right = max(2, visible_bars * 0.05)

            bar_anchor = len(df) - 0.5
            right_anchor = bar_anchor + initial_margin_right
            data_span_left = -0.5 - margin_left
            initial_width = right_anchor - (visible_left_idx - 0.5)

            ax_main.set_xlim(right_anchor - initial_width, right_anchor)
        else:
            bar_anchor = 0.0
            right_anchor = 0.5
            data_span_left = -0.5
            initial_width = 1.0

        # 3c. 绘制 filter 时间范围背景（左边界虚线 + 浅灰 span）
        if filter_cutoff_date is not None:
            self._draw_filter_range(ax_main, df, filter_cutoff_date)

        # 不添加标题，因为信息已显示在UI右上角，避免浪费空间

        # 4. 嵌入Tkinter Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.container)

        # 禁用 matplotlib 3.9+ 的自动 DPI 缩放 (PR #28588)
        self._disable_auto_dpi_scaling()

        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()

        # pick_event 连线（live_mode）；幂等：先 disconnect 上次的 cid
        if _live_mode:
            if getattr(self, "_pick_cid", None) is not None:
                try:
                    self.canvas.mpl_disconnect(self._pick_cid)
                except Exception:
                    pass
            self._pick_cid = self.canvas.mpl_connect("pick_event", self._on_pick)

        # 5. 绑定交互控制器（双模式：RIGHT_ALIGNED 默认，Ctrl+滚轮/左键拖拽进 FREE）
        self.interaction = AxesInteractionController(
            ax_main,
            self.canvas,
            on_pan_state_change=self._on_pan_state_change,
            is_ctrl_pressed=lambda: self._ctrl_pressed,
        )
        self.interaction.attach(
            data_span=(data_span_left, right_anchor),
            bar_anchor=bar_anchor,
            initial_width=initial_width,
        )

        # 6. 绑定鼠标悬停事件
        self._attach_hover(ax_main, df, breakouts, peaks=all_drawn_peaks)

    def _on_pick(self, event):
        """matplotlib pick_event handler：BO marker 点击反向同步到 MatchList。"""
        cb = getattr(self, "_on_bo_picked_callback", None)
        if cb is None:
            return
        artist = event.artist
        idxs = getattr(artist, "bo_chart_indices", None)
        if not idxs:
            return
        # event.ind 是被点中的点在 scatter offsets 里的索引
        for i in event.ind:
            if 0 <= i < len(idxs):
                cb(idxs[i])
                return

    def _cleanup(self):
        """清理旧图表，防止内存泄漏"""
        if self.interaction is not None:
            self.interaction.detach()
            self.interaction = None

        # Filter 范围 artists 随 fig 关闭自动释放，这里只清引用
        self._filter_span = None
        self._filter_line = None

        if self.canvas:
            self.canvas.get_tk_widget().destroy()
            self.canvas = None
            # canvas 销毁后，旧 _pick_cid 已失效；清空避免下次 update_chart
            # 对已死 canvas 做 stale disconnect
            if hasattr(self, "_pick_cid"):
                self._pick_cid = None

        if self.fig:
            plt.close(self.fig)
            self.fig = None

        self.annotation = None
        self.crosshair_v = None
        self.crosshair_h = None

        # 清理评分详情窗口相关状态
        self._hovered_peak = None
        self._hovered_bo = None
        self._all_peaks = []
        self._all_breakouts = []
        self._atr_series = None
        self._atr_period = 14
        self._vol_ratio_series = None
        # 注意：不关闭已打开的窗口，让用户可以继续查看

        # 重置Ctrl模式状态
        self._ctrl_pressed = False
        self._last_mouse_x = 0.0
        self._last_mouse_y = 0.0
        self._last_hover_x = 0
        self._hover_df = None

    def _on_pan_state_change(self, panning: bool) -> None:
        """拖拽期间隐藏 hover annotation/crosshair，避免视觉闪烁。"""
        if self.annotation is not None:
            self.annotation.set_visible(not panning and self.annotation.get_text() != "")
        if self.crosshair_v is not None:
            self.crosshair_v.set_visible(False if panning else self.crosshair_v.get_visible())
        if self.crosshair_h is not None:
            self.crosshair_h.set_visible(False if panning else self.crosshair_h.get_visible())
        if self.canvas is not None:
            self.canvas.draw_idle()

    def _draw_label_buffer_zone(
        self, ax, df: pd.DataFrame, buffer_start_idx: int, colors: dict
    ):
        """
        绘制 Label 缓冲区的视觉标记（分割线 + 浅灰背景）

        Args:
            ax: matplotlib Axes 对象
            df: 显示用的 DataFrame
            buffer_start_idx: 缓冲区起始索引（在 df 中的位置）
            colors: 颜色配置
        """
        # 1. 分割线（垂直虚线）
        ax.axvline(
            x=buffer_start_idx - 0.5,
            color=colors.get("label_buffer_divider", "#888888"),
            linestyle="--",
            linewidth=2,
            alpha=0.7,
            zorder=5,
        )

        # 2. 浅灰背景矩形
        ylim = ax.get_ylim()
        if ylim[0] == 0.0 and ylim[1] == 1.0:
            # Y 轴尚未初始化，跳过背景绘制
            return

        rect = mpatches.Rectangle(
            (buffer_start_idx - 0.5, ylim[0]),
            len(df) - buffer_start_idx + 0.5,
            ylim[1] - ylim[0],
            color=colors.get("label_buffer_bg", "#F5F5F5"),
            alpha=0.3,
            zorder=0,
            linewidth=0,
        )
        ax.add_patch(rect)

    def _draw_range_spec_shading(self, ax, df, spec):
        """按 spec 绘制三段阴影 + 降级虚线。

        三段阴影：pre-scan / main / post-scan。
        降级虚线：scan_start_degraded 或 scan_end_degraded 时，在对应位置画橙色虚线。
        """
        if spec is None:
            return

        # 三段阴影
        self._draw_shade(ax, df, spec.display_start, spec.scan_start_actual)
        self._draw_shade(ax, df, spec.scan_end_actual, spec.display_end)

        # 降级虚线
        if spec.scan_start_degraded:
            self._draw_degradation_line(
                ax, df, spec.scan_start_actual,
                label=f"scan start (req {spec.scan_start_ideal})",
            )
        if spec.scan_end_degraded:
            self._draw_degradation_line(
                ax, df, spec.scan_end_actual,
                label=f"scan end (req {spec.scan_end_ideal})",
            )

    def _draw_degradation_line(self, ax, df, date_value, label, color="#FF8800"):
        """在指定日期画橙色虚线，顶部附文字标注。"""
        if date_value is None:
            return
        dt = pd.to_datetime(date_value)
        mask = df.index >= dt
        if not mask.any():
            return
        idx = int(mask.argmax())
        ax.axvline(x=idx, color=color, linestyle="--", linewidth=1.0, zorder=5, alpha=0.8)
        _ymin, ymax = ax.get_ylim()
        ax.text(
            idx, ymax * 0.98, label,
            color=color, fontsize=8, ha="left", va="top",
            bbox=dict(facecolor="white", edgecolor=color, alpha=0.9, boxstyle="round,pad=0.3"),
        )

    def _draw_shade(self, ax, df, start_date, end_date, alpha=0.15, color="#808080"):
        """在 ax 上绘制 [start_date, end_date] 区间的灰色阴影（基于 df 行号）。

        start_date/end_date 为 datetime.date；区间空/逆序时跳过。
        """
        if start_date is None or end_date is None:
            return
        if start_date >= end_date:
            return
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        start_mask = df.index >= start_dt
        if not start_mask.any():
            return
        start_idx = int(start_mask.argmax())
        # end_idx: 在 df 中找 <= end_date 的最后一个位置的后一位
        end_idx = int(df.index.searchsorted(end_dt, side="right"))
        if end_idx <= start_idx:
            return
        ax.axvspan(start_idx - 0.5, end_idx - 0.5, alpha=alpha, color=color, zorder=0)

    def _draw_filter_range(self, ax, df, cutoff_date):
        """绘制 filter 的时间范围：浅灰背景 + 黑色虚线左边界。

        Args:
            ax: 主 axes（ax_main）
            df: 当前 OHLCV DataFrame
            cutoff_date: filter 的 date cutoff（datetime.date）
        """
        left_idx = compute_left_idx(df.index, cutoff_date)
        if left_idx >= len(df):
            # cutoff 晚于最新数据 → 无可绘制范围
            return

        ylim = ax.get_ylim()
        if ylim[0] == 0.0 and ylim[1] == 1.0:
            # Y 轴尚未初始化，跳过背景绘制
            return

        self._filter_span = mpatches.Rectangle(
            (left_idx - 0.5, ylim[0]),
            len(df) - left_idx,
            ylim[1] - ylim[0],
            color="#D8D8D8",
            alpha=0.25,
            zorder=0,
            linewidth=0,
        )
        ax.add_patch(self._filter_span)
        self._filter_line = ax.axvline(
            x=left_idx - 0.5,
            color="black",
            linestyle="--",
            linewidth=1.5,
            alpha=0.8,
            zorder=4,
        )

    def update_filter_range(self, cutoff_date):
        """Surgical 更新 filter 背景/边界位置（不重绘 figure）。

        Args:
            cutoff_date: filter 的 date cutoff（datetime.date）
        """
        if (
            self._filter_span is None
            or self._filter_line is None
            or self._hover_df is None
        ):
            return
        df = self._hover_df
        left_idx = compute_left_idx(df.index, cutoff_date)

        if left_idx >= len(df):
            self._filter_span.set_visible(False)
            self._filter_line.set_visible(False)
        else:
            ylim = self._filter_span.axes.get_ylim()
            self._filter_span.set_xy((left_idx - 0.5, ylim[0]))
            self._filter_span.set_width(len(df) - left_idx)
            self._filter_line.set_xdata([left_idx - 0.5, left_idx - 0.5])
            self._filter_span.set_visible(True)
            self._filter_line.set_visible(True)

        if self.canvas is not None:
            self.canvas.draw_idle()

    def _disable_auto_dpi_scaling(self):
        """
        禁用 matplotlib 3.9+ 的自动 DPI 缩放

        matplotlib 3.9+ 在 Linux 上会通过 <Map> 事件自动检测屏幕 DPI 并缩放渲染，
        导致高 DPI 环境下图表超出容器边界。此方法通过解绑 <Map> 事件来禁用此行为。

        参考: matplotlib/backends/_backend_tk.py (PR #28588)
        """
        if self.canvas is None:
            return

        # 获取底层 Tk canvas widget
        tk_canvas = self.canvas.get_tk_widget()

        # 解绑 <Map> 事件，阻止 matplotlib 自动调用 _update_device_pixel_ratio
        # 这是 matplotlib 3.9+ 在 Linux 上触发 DPI 缩放的入口
        tk_canvas.unbind("<Map>")

        # 强制设置 device_pixel_ratio 为 1.0（如果方法存在）
        if hasattr(self.canvas, '_set_device_pixel_ratio'):
            self.canvas._set_device_pixel_ratio(1.0)

    def _attach_hover(self, ax, df, breakouts, peaks=None):
        """
        绑定鼠标悬停事件

        Args:
            ax: 主axes
            df: 数据
            breakouts: 突破列表
            peaks: 峰值列表 (可选)
        """
        # 保存数据供快捷键回调使用
        self._all_peaks = peaks or []
        self._all_breakouts = breakouts or []
        self._hover_df = df  # 保存df引用供Ctrl模式使用

        # 获取 ATR 序列（用于 tooltip 显示）
        from BreakoutStrategy.param_loader import get_param_loader
        loader = get_param_loader()
        feature_params = loader.get_feature_calculator_params()
        self._atr_period = feature_params.get("atr_period", 14)
        # 优先使用预计算的 ATR 列（在 preprocess_dataframe 中计算，包含缓冲区）
        if "atr" in df.columns:
            self._atr_series = df["atr"]
        else:
            # 回退：实时计算（数据可能不含缓冲区，ATR 会延迟显示）
            self._atr_series = TechnicalIndicators.calculate_atr(
                df["high"], df["low"], df["close"], self._atr_period
            )

        # 预计算放量倍数序列（与因子系统共用计算源）
        from BreakoutStrategy.analysis.features import FeatureCalculator
        vol_lookback = feature_params.get("vol_lookback", 63)
        self._vol_ratio_series = FeatureCalculator.precompute_vol_ratio_series(df, lookback=vol_lookback)

        # 获取颜色配置
        colors = get_chart_colors()

        # 创建十字线（初始隐藏）
        self.crosshair_v = ax.axvline(
            0, color=colors["crosshair_normal"], linestyle="--", linewidth=1.5, alpha=0.7, visible=False
        )
        self.crosshair_h = ax.axhline(
            0, color=colors["crosshair_normal"], linestyle="--", linewidth=1.5, alpha=0.7, visible=False
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
            # 拖拽平移期间完全跳过悬停渲染，避免与控制器冲突
            if self.interaction is not None and self.interaction.is_panning:
                return
            if event.inaxes != ax:
                self.annotation.set_visible(False)
                self.crosshair_v.set_visible(False)
                self.crosshair_h.set_visible(False)
                # 清除悬停状态
                self._hovered_peak = None
                self._hovered_bo = None
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
                self._hovered_bo = None
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

            # 保存鼠标位置（用于Ctrl模式）
            self._last_mouse_x = event.xdata
            self._last_mouse_y = event.ydata
            self._last_hover_x = x

            # 重置悬停状态
            self._hovered_peak = None
            self._hovered_bo = None

            # 根据Ctrl状态选择不同的显示模式
            if self._ctrl_pressed:
                # Ctrl模式：只显示鼠标位置的价格
                text = f"Price: {event.ydata:.2f}"

                # 更新十字线位置（完全跟随鼠标，不附着K线）
                self.crosshair_v.set_xdata([event.xdata])
                self.crosshair_h.set_ydata([event.ydata])
                self.crosshair_h.set_color(colors["crosshair_ctrl"])
            else:
                # 普通模式：显示完整OHLC信息

                # 计算 Chg (涨跌幅)
                if x > 0:
                    prev_close = df.iloc[x - 1]['close']
                    chg = (row['close'] - prev_close) / prev_close * 100
                    chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                else:
                    chg_str = "N/A"

                # RV (相对成交量, 复用因子系统的 vol_ratio 序列)
                if self._vol_ratio_series is not None:
                    rv = self._vol_ratio_series.iloc[x]
                    rv_str = f"{rv:.2f}" if rv > 0 else "N/A"
                else:
                    rv_str = "N/A"

                # 构建显示文本
                text = f"Date: {date.strftime('%Y-%m-%d')}\n"
                text += f"Open: {row['open']:.2f}\n"
                text += f"High: {row['high']:.2f}\n"
                text += f"Low: {row['low']:.2f}\n"
                text += f"Close: {row['close']:.2f}\n"
                text += f"Chg: {chg_str}\n"
                text += f"Volume: {int(row['volume']):,}\n"
                text += f"RV: {rv_str}\n"

                # 添加 ATR
                if hasattr(self, '_atr_series') and self._atr_series is not None:
                    atr_val = self._atr_series.iloc[x]
                    if pd.notna(atr_val):
                        text += f"ATR_{self._atr_period}: {atr_val:.2f}"

                # 计算该 K 线时刻的 active peaks
                # 1. 收集在当前位置之前或当前被真正移除的峰值 ID（突破幅度 > supersede_threshold）
                superseded_at_x = set()
                for bo in breakouts:
                    if bo.index <= x:  # 该突破发生在当前 K 线之前或当前
                        superseded_at_x.update(bo.superseded_peak_ids)

                # 2. 筛选在当前位置之前创建、且未被真正移除的峰值
                active_at_x = []
                if peaks:
                    active_at_x = [
                        p for p in peaks
                        if p.index < x and p.id not in superseded_at_x
                    ]

                # 3. 始终显示 active peaks id 列表（按 ID 排序），即使为空
                active_ids = [str(p.id) for p in sorted(active_at_x, key=lambda p: p.id)]
                text += f"\nActive: [{','.join(active_ids)}]"

                # 检查是否是突破点
                for bo in breakouts:
                    if bo.index == x:
                        self._hovered_bo = bo  # 记录悬停的突破
                        peak_ids_text = ",".join(map(str, bo.broken_peak_ids)) if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids else ""
                        score_text = f"{bo.quality_score:.0f}" if bo.quality_score else "N/A"
                        text += f"\n\nBO:\n[{peak_ids_text}],{score_text}"
                        # 显示 labels（如果存在）
                        if hasattr(bo, "labels") and bo.labels:
                            label_parts = []
                            for key, val in bo.labels.items():
                                if val is not None:
                                    label_parts.append(f"{key}:{val:.2%}")
                            if label_parts:
                                text += f"\nLabel: {', '.join(label_parts)}"
                        break

                # 检查是否是峰值
                if peaks:
                    for peak in peaks:
                        if peak.index == x:
                            self._hovered_peak = peak  # 记录悬停的峰值
                            id_text = str(peak.id) if peak.id is not None else "N/A"
                            text += f"\n\nPeak:\n{id_text}"
                            break

                # 更新十字线位置（横线锁定收盘价）
                self.crosshair_v.set_xdata([x])
                self.crosshair_h.set_ydata([row["close"]])
                self.crosshair_h.set_color(colors["crosshair_normal"])

            self.crosshair_v.set_visible(True)
            self.crosshair_h.set_visible(True)

            # 边缘感知：右/上边不够时自动翻到可见象限
            fig_w, fig_h = self.canvas.get_width_height()
            offset_x, offset_y, ha, va = compute_tooltip_anchor(
                cursor_px=(event.x, event.y),
                fig_size=(fig_w, fig_h),
                est_tooltip_size=(400, 350),
            )

            self.annotation.xy = (event.xdata, event.ydata)
            self.annotation.xyann = (offset_x, offset_y)
            self.annotation.set_ha(ha)
            self.annotation.set_va(va)
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

        # 绑定 Ctrl 键事件（用于自由Y轴悬停模式）
        canvas_widget.bind("<Control_L>", self._on_ctrl_press)
        canvas_widget.bind("<Control_R>", self._on_ctrl_press)
        canvas_widget.bind("<KeyRelease-Control_L>", self._on_ctrl_release)
        canvas_widget.bind("<KeyRelease-Control_R>", self._on_ctrl_release)

        # 鼠标进入时自动获取焦点（以便接收键盘事件）
        canvas_widget.bind("<Enter>", lambda e: canvas_widget.focus_set())

        # 窗口失焦时重置Ctrl状态
        canvas_widget.bind("<FocusOut>", lambda e: setattr(self, '_ctrl_pressed', False))

        # 鼠标点击时让 canvas 获得焦点（以便接收键盘事件）
        # add="+" 避免替换 matplotlib TkAgg 内部的 <Button-1> 绑定
        canvas_widget.bind("<Button-1>", lambda e: canvas_widget.focus_set(), add="+")

    def _on_score_detail_key(self, event):
        """
        D 键按下回调：显示评分详情窗口

        Args:
            event: Tkinter 键盘事件
        """
        # 检查是否有悬停的峰值或突破
        if self._hovered_peak is None and self._hovered_bo is None:
            return  # 没有悬停在任何标记点上，忽略

        # 创建评分详情窗口
        window = ScoreDetailWindow(
            parent=self.container,
            peak=self._hovered_peak,
            breakout=self._hovered_bo,
            breakout_scorer=self.breakout_scorer,
            position=self._hover_position,
            symbol=self._current_symbol
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

    def _on_ctrl_press(self, event):
        """
        Ctrl键按下回调：切换到自由Y轴悬停模式

        Args:
            event: Tkinter键盘事件
        """
        if self._ctrl_pressed:
            return  # 已经在Ctrl模式，避免重复处理

        self._ctrl_pressed = True

        # 立即更新十字线颜色和位置
        colors = get_chart_colors()
        need_redraw = False

        if self.crosshair_h and self.crosshair_h.get_visible():
            self.crosshair_h.set_color(colors["crosshair_ctrl"])
            # 如果有保存的鼠标Y位置，立即应用
            if self._last_mouse_y:
                self.crosshair_h.set_ydata([self._last_mouse_y])
            need_redraw = True

        if self.crosshair_v and self.crosshair_v.get_visible():
            # 如果有保存的鼠标X位置，立即应用（脱离K线附着）
            if self._last_mouse_x:
                self.crosshair_v.set_xdata([self._last_mouse_x])
            need_redraw = True

        if need_redraw and self.canvas:
            self.canvas.draw_idle()

    def _on_ctrl_release(self, event):
        """
        Ctrl键释放回调：恢复锁定收盘价模式

        Args:
            event: Tkinter键盘事件
        """
        if not self._ctrl_pressed:
            return  # 不在Ctrl模式，忽略

        self._ctrl_pressed = False

        # 恢复十字线颜色和位置（锁定回K线）
        colors = get_chart_colors()
        need_redraw = False

        if self.crosshair_h and self.crosshair_h.get_visible():
            self.crosshair_h.set_color(colors["crosshair_normal"])
            # 恢复到当前K线的收盘价
            if self._hover_df is not None and 0 <= self._last_hover_x < len(self._hover_df):
                row = self._hover_df.iloc[self._last_hover_x]
                self.crosshair_h.set_ydata([row["close"]])
            need_redraw = True

        if self.crosshair_v and self.crosshair_v.get_visible():
            # 恢复垂直线到K线位置
            self.crosshair_v.set_xdata([self._last_hover_x])
            need_redraw = True

        if need_redraw and self.canvas:
            self.canvas.draw_idle()

    def close_all_score_windows(self):
        """关闭所有评分详情窗口（供外部调用）"""
        self._on_close_all_windows_key(None)

    def clear(self) -> None:
        """清空图表（无选中时调用）。_cleanup 已 destroy 掉 canvas widget，
        无需再 draw_idle——下次 update_chart 会重建。"""
        self._cleanup()
