"""图表Canvas管理器"""

import tkinter as tk
from datetime import datetime
from types import SimpleNamespace
from typing import Optional, List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..styles import get_chart_colors, SIGNAL_COLORS
from .components import CandlestickComponent, MarkerComponent, PanelComponent
from .components.markers import draw_signal_markers


class ChartCanvasManager:
    """图表Canvas管理器"""

    def __init__(self, parent_container):
        """
        初始化图表管理器

        Args:
            parent_container: 父容器
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

        self._current_symbol: str = ""  # 当前股票代码

        # Ctrl模式状态（自由Y轴悬停）
        self._ctrl_pressed: bool = False  # Ctrl键是否按下
        self._last_mouse_x: float = 0.0   # 鼠标X坐标（数据坐标系，实际位置）
        self._last_mouse_y: float = 0.0   # 鼠标Y坐标（数据坐标系）
        self._last_hover_x: int = 0       # 最近悬停的K线索引
        self._hover_df: Optional[pd.DataFrame] = None  # 保存df引用
        self._signals_by_date: dict = {}  # 日期 -> 信号列表映射

    def update_chart(
        self,
        df: pd.DataFrame,
        signals: List[dict] = None,
        symbol: str = "",
        display_options: dict = None,
        lookback_days: int = 42,
        before_days: int = 21,
        after_days: int = 0,
        highlight_start_idx: int = None,
        highlight_end_idx: int = None,
    ):
        """
        更新图表显示

        Args:
            df: OHLCV数据（已截取到显示范围）
            signals: 信号列表，每个信号包含 date, signal_type
            symbol: 股票代码
            display_options: 显示选项
            lookback_days: lookback期间天数，用于高亮显示
            before_days: lookback 前显示的天数
            after_days: lookback 后显示的天数
            highlight_start_idx: 高亮区域起始索引（可选，用于精确控制）
            highlight_end_idx: 高亮区域结束索引（可选，用于精确控制）
        """
        # 1. 清理旧图表（防内存泄漏）
        self._cleanup()

        # 保存当前股票代码
        self._current_symbol = symbol
        signals = signals or []

        # 构建日期 -> 信号列表的映射（用于 tooltip 显示）
        self._signals_by_date = {}
        for sig in signals:
            sig_date = sig.get("date", "")
            if sig_date not in self._signals_by_date:
                self._signals_by_date[sig_date] = []
            self._signals_by_date[sig_date].append(sig)

        # 2. 创建新图表（单个主图）
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
        ax_main = self.fig.add_subplot(111)

        # 设置坐标系背景和边框
        ax_main.set_facecolor("white")
        for spine in ax_main.spines.values():
            spine.set_visible(True)
            spine.set_color("black")
            spine.set_linewidth(1.0)

        # 优化布局边距，减少空白区域
        self.fig.subplots_adjust(
            left=0.03, right=0.98, top=0.99, bottom=0.02
        )

        # 设置全局字体大小
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

        # 3. 绘制 K 线图
        # 先绘制成交量作为背景
        self.candlestick.draw_volume_background(ax_main, df, colors=colors)

        # 然后绘制K线（叠加在成交量上）
        self.candlestick.draw(ax_main, df, colors=colors)

        # 绘制lookback期间背景（在信号标记之前）
        self._draw_lookback_background(
            ax_main, df, lookback_days, before_days, after_days,
            highlight_start_idx, highlight_end_idx
        )

        # 获取符号筛选配置
        symbol_filter = display_options.get("symbol_filter", {}) if display_options else {}
        show_bo = symbol_filter.get("show_bo", True)
        show_hv = symbol_filter.get("show_hv", True)
        show_by = symbol_filter.get("show_by", True)
        show_dt = symbol_filter.get("show_dt", True)
        show_peak = symbol_filter.get("show_peak", True)
        show_trough = symbol_filter.get("show_trough", True)

        # 根据筛选配置过滤信号
        filtered_signals = []
        if signals:
            for sig in signals:
                sig_type = sig.get("signal_type", "")
                if sig_type == "B" and show_bo:
                    filtered_signals.append(sig)
                elif sig_type == "V" and show_hv:
                    filtered_signals.append(sig)
                elif sig_type == "Y" and show_by:
                    filtered_signals.append(sig)
                elif sig_type == "D" and show_dt:
                    filtered_signals.append(sig)

        # 绘制信号标记
        if filtered_signals:
            draw_signal_markers(ax_main, df, filtered_signals)

        # 从 BO 信号中提取 Peak 数据并绘制
        if signals and show_peak:
            peaks_to_draw = []
            for sig in signals:
                if sig.get("signal_type") == "B":
                    peaks_data = sig.get("details", {}).get("peaks", [])
                    for p in peaks_data:
                        peak_date_str = p.get("date")
                        if not peak_date_str:
                            continue
                        try:
                            # 解析日期并在 display_df 中查找本地索引
                            peak_date = datetime.fromisoformat(peak_date_str).date()
                            if hasattr(df.index, "date"):
                                mask = df.index.date == peak_date
                                if not mask.any():
                                    continue  # Peak 不在显示范围内
                                local_idx = int(mask.argmax())
                            else:
                                continue
                            # 创建 Peak 对象（使用本地索引）
                            peak_obj = SimpleNamespace(
                                index=local_idx,
                                price=p["price"],
                                id=p.get("id"),
                            )
                            peaks_to_draw.append(peak_obj)
                        except (ValueError, KeyError, AttributeError):
                            pass

            if peaks_to_draw:
                self.marker.draw_peaks(ax_main, df, peaks_to_draw, colors=colors)

        # 绘制阻力带（跟随 show_bo，仅多 peak 突破）
        if signals and show_bo:
            for sig in signals:
                if sig.get("signal_type") != "B":
                    continue
                peaks_data = sig.get("details", {}).get("peaks", [])
                if len(peaks_data) <= 1:
                    continue

                # 计算价格范围
                prices = [p["price"] for p in peaks_data]
                zone_top = max(prices)
                zone_bottom = min(prices)

                # 找最早 peak 的本地索引
                try:
                    earliest_date = min(
                        datetime.fromisoformat(p["date"]).date() for p in peaks_data
                    )
                    # B 信号日期
                    bo_date = datetime.fromisoformat(sig["date"]).date()
                except (ValueError, KeyError):
                    continue

                # 转换为本地索引
                if not hasattr(df.index, "date"):
                    continue

                mask_earliest = df.index.date == earliest_date
                mask_bo = df.index.date == bo_date
                if not mask_earliest.any() or not mask_bo.any():
                    continue

                earliest_local_idx = int(mask_earliest.argmax())
                bo_local_idx = int(mask_bo.argmax())

                # 确保有宽度
                width = bo_local_idx - earliest_local_idx
                if width <= 0:
                    continue

                # 确保有高度
                height = zone_top - zone_bottom
                if height <= 0:
                    margin = zone_bottom * 0.001
                    zone_bottom -= margin
                    zone_top += margin
                    height = zone_top - zone_bottom

                # 绘制矩形
                rect = mpatches.Rectangle(
                    (earliest_local_idx, zone_bottom),
                    width,
                    height,
                    color=colors.get("resistance_zone", "#FFA500"),
                    alpha=0.2,
                    zorder=1,
                    linewidth=0,
                )
                ax_main.add_patch(rect)

        # 从 DT 信号中提取 Trough1 数据并绘制（颜色跟随信号类型）
        if signals:
            troughs_to_draw = []
            for sig in signals:
                sig_type = sig.get("signal_type")
                # D 信号的 TR1：仅当 show_dt 启用时显示
                if sig_type == "D" and show_dt:
                    trough_obj = self._extract_trough1(sig, df)
                    if trough_obj:
                        trough_obj.color = SIGNAL_COLORS["D"]  # 紫色
                        trough_obj.signal_type = "D"
                        troughs_to_draw.append(trough_obj)

            if troughs_to_draw:
                self.marker.draw_troughs(ax_main, df, troughs_to_draw, colors=colors)

        # 从 D 信号中提取支撑 trough 数据并绘制
        if signals and show_trough:
            support_troughs_to_draw = []
            for sig in signals:
                if sig.get("signal_type") != "D":
                    continue
                support_troughs = sig.get("details", {}).get("support_troughs", [])
                for t in support_troughs:
                    trough_date_str = t.get("date")
                    if not trough_date_str:
                        continue
                    try:
                        # 解析日期并在 display_df 中查找本地索引
                        trough_date = datetime.fromisoformat(trough_date_str).date()
                        if hasattr(df.index, "date"):
                            mask = df.index.date == trough_date
                            if not mask.any():
                                continue  # trough 不在显示范围内
                            local_idx = int(mask.argmax())
                        else:
                            continue
                        # 创建 trough 对象（使用本地索引）
                        trough_obj = SimpleNamespace(
                            index=local_idx,
                            price=t["price"],
                            id=t.get("id"),
                        )
                        support_troughs_to_draw.append(trough_obj)
                    except (ValueError, KeyError, AttributeError):
                        pass

            if support_troughs_to_draw:
                self.marker.draw_support_troughs(ax_main, df, support_troughs_to_draw, colors=colors)

        # 绘制支撑带（跟随 show_dt）
        if signals and show_dt:
            # 收集所有 D 信号并按日期排序
            d_signals = [
                s for s in signals
                if s.get("signal_type") == "D"
                and s.get("details", {}).get("support_status", {}).get("support_zone")
            ]
            d_signals.sort(key=lambda s: s.get("date", ""))

            for i, sig in enumerate(d_signals):
                details = sig.get("details", {})
                support_status = details.get("support_status", {})
                support_zone = support_status.get("support_zone")
                is_broken = support_status.get("status") == "broken"
                break_date_str = support_status.get("break_date")

                if not support_zone:
                    continue

                zone_lower, zone_upper = support_zone

                if not hasattr(df.index, "date"):
                    continue

                # 左边界：优先使用 trough2_window_end_date（TR2 确认日期），回退到信号日期
                # 支撑带从确认日期的下一天开始显示
                trough2_window_end_date_str = details.get("trough2_window_end_date")
                left_idx = None

                if trough2_window_end_date_str:
                    try:
                        window_end_date = datetime.fromisoformat(trough2_window_end_date_str).date()
                        mask_window_end = df.index.date == window_end_date
                        if mask_window_end.any():
                            left_idx = int(mask_window_end.argmax()) + 1  # 从下一天开始
                    except (ValueError, KeyError):
                        pass

                # 回退：使用信号日期
                if left_idx is None:
                    try:
                        sig_date = datetime.fromisoformat(sig["date"]).date()
                    except (ValueError, KeyError):
                        continue
                    mask_left = df.index.date == sig_date
                    if not mask_left.any():
                        continue
                    left_idx = int(mask_left.argmax()) + 1  # 从下一天开始

                # 右边界优先级：跌破日期 > 下一个 D 信号 > 最后一根 K 线
                right_idx = len(df) - 1

                # 1. 如果支撑被跌破，支撑带止于跌破日期
                if is_broken and break_date_str:
                    try:
                        break_date = datetime.fromisoformat(break_date_str).date()
                        mask_break = df.index.date == break_date
                        if mask_break.any():
                            right_idx = int(mask_break.argmax())
                    except (ValueError, KeyError):
                        pass
                # 2. 否则，止于下一个 D 信号
                elif i + 1 < len(d_signals):
                    try:
                        next_sig_date = datetime.fromisoformat(d_signals[i + 1]["date"]).date()
                        mask_right = df.index.date == next_sig_date
                        if mask_right.any():
                            right_idx = int(mask_right.argmax())
                    except (ValueError, KeyError):
                        pass

                # 确保有宽度
                width = right_idx - left_idx
                if width <= 0:
                    width = 1  # 至少显示一根 K 线宽度

                # 确保有高度
                height = zone_upper - zone_lower
                if height <= 0:
                    margin = zone_lower * 0.001
                    zone_lower -= margin
                    zone_upper += margin
                    height = zone_upper - zone_lower

                # 根据支撑带状态选择颜色
                if is_broken:
                    zone_color = colors.get("support_zone_broken", "#C0C0C0")
                    zone_alpha = 0.15
                else:
                    zone_color = colors.get("support_zone", "#87CEEB")
                    zone_alpha = 0.2

                # 绘制矩形
                rect = mpatches.Rectangle(
                    (left_idx - 0.4, zone_lower),  # 对齐 K 线左边缘
                    width,
                    height,
                    color=zone_color,
                    alpha=zone_alpha,
                    zorder=0,
                    linewidth=0,
                )
                ax_main.add_patch(rect)

        # 4. 嵌入Tkinter Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.container)

        # 禁用 matplotlib 3.9+ 的自动 DPI 缩放
        self._disable_auto_dpi_scaling()

        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()

        # 5. 绑定鼠标悬停事件
        self._attach_hover(ax_main, df)

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

        # 重置Ctrl模式状态
        self._ctrl_pressed = False
        self._last_mouse_x = 0.0
        self._last_mouse_y = 0.0
        self._last_hover_x = 0
        self._hover_df = None
        self._signals_by_date = {}

    def _extract_trough1(self, sig: dict, df: pd.DataFrame):
        """
        从信号中提取 Trough1 数据

        Args:
            sig: 信号字典，包含 details.trough1_date 和 details.trough1_price
            df: OHLCV DataFrame（显示部分）

        Returns:
            SimpleNamespace 对象（含 index, price 属性）或 None
        """
        details = sig.get("details", {})
        trough1_date_str = details.get("trough1_date")
        trough1_price = details.get("trough1_price")
        if not trough1_date_str or trough1_price is None:
            return None
        try:
            # 解析日期并在 display_df 中查找本地索引
            trough1_date = datetime.fromisoformat(trough1_date_str).date()
            if hasattr(df.index, "date"):
                mask = df.index.date == trough1_date
                if not mask.any():
                    return None  # Trough1 不在显示范围内
                local_idx = int(mask.argmax())
            else:
                return None
            # 创建 Trough 对象（使用本地索引）
            return SimpleNamespace(
                index=local_idx,
                price=trough1_price,
            )
        except (ValueError, KeyError, AttributeError):
            return None

    def _draw_lookback_background(
        self, ax, df: pd.DataFrame, lookback_days: int,
        before_days: int = 21, after_days: int = 0,
        highlight_start_idx: int = None, highlight_end_idx: int = None
    ):
        """
        绘制lookback期间的深色背景高亮

        Args:
            ax: matplotlib axes
            df: OHLCV数据（显示部分）
            lookback_days: lookback期间天数
            before_days: lookback 前显示的天数
            after_days: lookback 后显示的天数
            highlight_start_idx: 高亮区域起始索引（可选，优先使用）
            highlight_end_idx: 高亮区域结束索引（可选，优先使用）
        """
        if len(df) <= lookback_days:
            # 数据量不足，无需区分
            return

        # 如果提供了精确的高亮索引，使用它们
        if highlight_start_idx is not None and highlight_end_idx is not None:
            # 使用传入的精确索引（-0.5/+0.5 用于对齐K线边界）
            start_idx = highlight_start_idx - 0.5
            end_idx = highlight_end_idx + 0.5
        else:
            # 回退到旧逻辑（兼容）
            end_idx = len(df) - after_days - 0.5
            start_idx = end_idx - lookback_days

        # 确保不超出范围
        start_idx = max(-0.5, start_idx)
        end_idx = min(len(df) - 0.5, end_idx)

        if end_idx <= start_idx:
            return

        ylim = ax.get_ylim()
        width = end_idx - start_idx
        height = ylim[1] - ylim[0]

        rect = mpatches.Rectangle(
            (start_idx, ylim[0]),
            width,
            height,
            facecolor='#000000',
            alpha=0.05,  # 非常轻微的深色，仅作为视觉提示
            zorder=0,  # 放在最底层
            linewidth=0,
        )
        ax.add_patch(rect)

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

    def _attach_hover(self, ax, df):
        """
        绑定鼠标悬停事件

        Args:
            ax: 主axes
            df: 数据
        """
        self._hover_df = df  # 保存df引用供Ctrl模式使用

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
            fontsize=22,
            zorder=100,
        )
        self.annotation.set_linespacing(1.5)
        self.annotation.set_visible(False)

        def on_hover(event):
            """鼠标悬停回调"""
            if event.inaxes != ax:
                self.annotation.set_visible(False)
                self.crosshair_v.set_visible(False)
                self.crosshair_h.set_visible(False)
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
                self.canvas.draw_idle()
                return

            # 获取数据
            row = df.iloc[x]
            date = df.index[x]

            # 保存鼠标位置（用于Ctrl模式）
            self._last_mouse_x = event.xdata
            self._last_mouse_y = event.ydata
            self._last_hover_x = x

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

                # 计算 RV (相对成交量, 基于约60个交易日)
                lookback = min(60, x)  # 最多回看60天
                if lookback > 0:
                    avg_vol = df.iloc[x - lookback:x]['volume'].mean()
                    rv = row['volume'] / avg_vol if avg_vol > 0 else 0
                    rv_str = f"{rv:.2f}"
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
                text += f"RV: {rv_str}"

                # 添加当天的信号显示
                date_str = date.strftime('%Y-%m-%d')
                day_signals = self._signals_by_date.get(date_str, [])
                if day_signals:
                    text += "\n---"
                    for sig in day_signals:
                        sig_type = sig.get("signal_type", "")
                        sig_line = f"\n{sig_type}"
                        # B 信号显示被突破的 peak id
                        if sig_type == "B":
                            details = sig.get("details", {})
                            peaks = details.get("peaks", [])
                            if peaks:
                                peak_ids = [str(p.get("id", "?")) for p in peaks]
                                sig_line += f" [{','.join(peak_ids)}]"
                        # D 信号显示支撑 trough id（仅显示可见范围内的）
                        elif sig_type == "D":
                            details = sig.get("details", {})
                            support_troughs = details.get("support_troughs", [])
                            if support_troughs:
                                # 过滤出在显示范围内的 trough
                                visible_ids = []
                                for t in support_troughs:
                                    t_date_str = t.get("date")
                                    if not t_date_str:
                                        continue
                                    try:
                                        t_date = datetime.fromisoformat(t_date_str).date()
                                        if hasattr(df.index, "date") and (df.index.date == t_date).any():
                                            visible_ids.append(str(t.get("id", "?")))
                                    except (ValueError, AttributeError):
                                        pass
                                if visible_ids:
                                    sig_line += f": [{','.join(visible_ids)}]"
                        # 所有信号类型都显示 freshness
                        details = sig.get("details", {})
                        freshness = details.get("freshness", {})
                        if isinstance(freshness, dict):
                            f_val = freshness.get("value", 0)
                            p_dec = freshness.get("price_decay", 0)
                            t_dec = freshness.get("time_decay", 0)
                            sig_line += f"  f={f_val:.2f} ({p_dec:.2f}×{t_dec:.2f})"

                        text += sig_line

                # 更新十字线位置（横线锁定收盘价）
                self.crosshair_v.set_xdata([x])
                self.crosshair_h.set_ydata([row["close"]])
                self.crosshair_h.set_color(colors["crosshair_normal"])

            self.crosshair_v.set_visible(True)
            self.crosshair_h.set_visible(True)

            # 始终显示在鼠标右上角
            offset_x = 40
            offset_y = 40

            # 更新annotation
            self.annotation.xy = (event.xdata, event.ydata)
            self.annotation.xyann = (offset_x, offset_y)
            self.annotation.set_text(text)
            self.annotation.set_visible(True)
            self.canvas.draw_idle()

        # 绑定 matplotlib 鼠标移动事件
        self.canvas.mpl_connect("motion_notify_event", on_hover)

        # 绑定快捷键事件（需要绑定到 tk widget）
        canvas_widget = self.canvas.get_tk_widget()

        # 确保 canvas 可以接收键盘焦点
        canvas_widget.configure(takefocus=True)

        # 绑定 Ctrl 键事件（用于自由Y轴悬停模式）
        canvas_widget.bind("<Control_L>", self._on_ctrl_press)
        canvas_widget.bind("<Control_R>", self._on_ctrl_press)
        canvas_widget.bind("<KeyRelease-Control_L>", self._on_ctrl_release)
        canvas_widget.bind("<KeyRelease-Control_R>", self._on_ctrl_release)

        # 鼠标进入时自动获取焦点
        canvas_widget.bind("<Enter>", lambda e: canvas_widget.focus_set())

        # 窗口失焦时重置Ctrl状态
        canvas_widget.bind("<FocusOut>", lambda e: setattr(self, '_ctrl_pressed', False))

        # 鼠标点击时让 canvas 获得焦点
        canvas_widget.bind("<Button-1>", lambda e: canvas_widget.focus_set())

    def _on_ctrl_press(self, event):
        """Ctrl键按下回调：切换到自由Y轴悬停模式"""
        if self._ctrl_pressed:
            return

        self._ctrl_pressed = True

        colors = get_chart_colors()
        need_redraw = False

        if self.crosshair_h and self.crosshair_h.get_visible():
            self.crosshair_h.set_color(colors["crosshair_ctrl"])
            if self._last_mouse_y:
                self.crosshair_h.set_ydata([self._last_mouse_y])
            need_redraw = True

        if self.crosshair_v and self.crosshair_v.get_visible():
            if self._last_mouse_x:
                self.crosshair_v.set_xdata([self._last_mouse_x])
            need_redraw = True

        if need_redraw and self.canvas:
            self.canvas.draw_idle()

    def _on_ctrl_release(self, event):
        """Ctrl键释放回调：恢复锁定收盘价模式"""
        if not self._ctrl_pressed:
            return

        self._ctrl_pressed = False

        colors = get_chart_colors()
        need_redraw = False

        if self.crosshair_h and self.crosshair_h.get_visible():
            self.crosshair_h.set_color(colors["crosshair_normal"])
            if self._hover_df is not None and 0 <= self._last_hover_x < len(self._hover_df):
                row = self._hover_df.iloc[self._last_hover_x]
                self.crosshair_h.set_ydata([row["close"]])
            need_redraw = True

        if self.crosshair_v and self.crosshair_v.get_visible():
            self.crosshair_v.set_xdata([self._last_hover_x])
            need_redraw = True

        if need_redraw and self.canvas:
            self.canvas.draw_idle()
