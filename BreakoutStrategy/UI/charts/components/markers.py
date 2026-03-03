"""标记组件 - 绘制峰值、突破点、阻力区、信号标记"""

from collections import defaultdict
from typing import List

import matplotlib.patches as mpatches
import pandas as pd

from ...styles import SIGNAL_COLORS


def draw_signal_markers(ax, df, signals: List[dict], y_margin: float = 0.02):
    """
    在 K 线图上绘制信号标记

    Args:
        ax: matplotlib axes
        df: DataFrame with OHLC data
        signals: 信号列表，每个信号包含 date, signal_type
        y_margin: 标记与 K 线的间距（相对于价格范围）
    """
    if not signals:
        return

    # 按日期分组信号
    signals_by_date = defaultdict(list)
    for sig in signals:
        sig_date = sig.get("date")
        if sig_date:
            signals_by_date[sig_date].append(sig)

    # 获取价格范围用于计算偏移
    price_range = df["high"].max() - df["low"].min()
    base_offset = price_range * y_margin

    for date_str, day_signals in signals_by_date.items():
        # 找到对应的 K 线索引
        try:
            # 处理不同的日期格式
            if hasattr(df.index, 'date'):
                # DatetimeIndex
                target_date = pd.to_datetime(date_str).date()
                mask = df.index.date == target_date
                if not mask.any():
                    continue
                idx = mask.argmax()
            else:
                idx = df.index.get_loc(date_str)
        except (KeyError, ValueError):
            continue

        high = df.iloc[idx]["high"]

        # 垂直堆叠绘制（从下到上）
        # 使用动态间距：有数值的信号需要更多空间
        cumulative_offset = 1.0  # 初始偏移（第一个信号距离 K 线）
        for i, sig in enumerate(day_signals):
            y_pos = high + base_offset * cumulative_offset
            signal_type = sig.get("signal_type", "")

            # 获取颜色
            color = SIGNAL_COLORS.get(signal_type, "#888888")

            # 绘制信号标记
            ax.text(
                idx,
                y_pos,
                signal_type,
                color=color,
                fontsize=18,
                fontweight="bold",
                ha="center",
                va="bottom",
            )

            # 绘制 num 标签（pk_num / tr_num）
            num_value = None
            details = sig.get("details", {})
            support_status = details.get("support_status", {})
            is_invalidated = support_status.get("invalidated", False) if support_status else False

            if signal_type == "B":
                num_value = details.get("pk_num")
            elif signal_type == "D":
                num_value = details.get("tr_num")

            # 仅当 num >= 2 时显示
            if num_value is not None and num_value >= 2:
                num_y = y_pos + base_offset * 1.0

                # 失效信号使用灰色样式
                if is_invalidated:
                    num_color = "#808080"  # 灰色
                    box_style = dict(
                        boxstyle="round,pad=0.2",
                        facecolor="#E0E0E0",  # 浅灰色背景
                        edgecolor="#808080",  # 灰色边框
                        linewidth=1.5,
                        alpha=0.6,  # 半透明
                    )
                else:
                    num_color = color
                    box_style = dict(
                        boxstyle="round,pad=0.2",
                        facecolor="#FFFFFF",
                        edgecolor=color,
                        linewidth=1.5,
                        alpha=0.8,
                    )

                ax.text(
                    idx,
                    num_y,
                    str(num_value),
                    fontsize=18,
                    fontweight="bold",
                    ha="center",
                    va="bottom",
                    color=num_color,
                    bbox=box_style,
                )
                # 下一个信号需要更多空间（跳过数值框）
                cumulative_offset += 2.0
            else:
                # 无数值，使用紧凑间距
                cumulative_offset += 0.8


class MarkerComponent:
    """标记绘制组件"""

    @staticmethod
    def draw_peaks(
        ax,
        df: pd.DataFrame,
        peaks: list,
        colors: dict = None,
        style: str = "normal",
    ):
        """
        绘制峰值标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
            peaks: Peak 对象列表
            colors: 颜色配置字典
            style: 绘制样式 ("normal" 或 "superseded")
        """
        if not peaks:
            return

        colors = colors or {}
        # 根据 style 选择颜色
        if style == "superseded":
            marker_color = colors.get("peak_marker_superseded", "#808080")
            text_id_color = colors.get("peak_text_id_superseded", "#000000")
        else:
            marker_color = colors.get("peak_marker", "#000000")
            text_id_color = colors.get("peak_text_id", "#000000")

        # 尝试获取 high/low 列，处理大小写
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        # 计算偏移单位
        # 优先使用坐标轴当前的显示范围 (ylim)，这样能保证相对于面板的比例是绝对固定的
        ylim = ax.get_ylim()
        # 检查 ylim 是否有效（不是默认的 0, 1）
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            # 如果坐标轴还没初始化，回退到使用数据范围
            price_range = df[high_col].max() - df[low_col].min()
            # 考虑 matplotlib 默认 padding (约 10%)
            price_range *= 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0

        # 避免 range 为 0
        if price_range == 0:
            price_range = df[high_col].mean() * 0.1 if has_high else 1.0

        # 使用价格范围的 2% 作为基本偏移单位
        offset_unit = price_range * 0.02

        for peak in peaks:
            # 使用整数索引而不是日期对象
            peak_x = peak.index  # 整数索引

            # 获取基准高度 (K bar high)
            if has_high and 0 <= peak_x < len(df):
                base_price = df.iloc[peak_x][high_col]
            else:
                base_price = peak.price

            # 1. 绘制峰值标记（倒三角，位于 K bar 上方）
            # 使用固定偏移量：基准 + 0.5 * 单位 (1% Range)
            marker_y = base_price + offset_unit * 0.6

            # 确定颜色
            color = marker_color  # 使用配置颜色

            ax.scatter(
                peak_x,
                marker_y,
                marker="v",  # 倒三角
                s=400,
                facecolors="none" if style == "normal" else color,  # superseded 用填充
                edgecolors=color,  # 边缘颜色
                linewidths=2,
                zorder=5,
                alpha=1.0 if style == "normal" else 0.6,  # superseded 半透明
                label="Peak" if peak == peaks[0] else None,
            )

            # 2. 添加 ID 标注 (位于标记上方)
            # 文本位于标记上方：标记位置 + 0.6 * 单位 (1.2% Range)
            text_y = marker_y + offset_unit * 0.6

            if peak.id is not None:
                ax.text(
                    peak_x,
                    text_y,
                    f"{peak.id}",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=text_id_color,
                    weight="bold",
                )

    @staticmethod
    def draw_breakouts(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        highlight_multi_peak: bool = True,
        peaks: list = None,
        colors: dict = None,
        show_score: bool = True,
    ):
        """
        绘制突破标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            breakouts: Breakout 对象列表
            highlight_multi_peak: 多峰值突破是否使用大标记
            peaks: 当前图表中绘制的峰值列表 (用于避免重叠)
            colors: 颜色配置字典
            show_score: 是否显示分数
        """
        if not breakouts:
            return

        colors = colors or {}
        marker_color = colors.get("breakout_marker", "#0000FF")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")
        text_score_color = colors.get("breakout_text_score", "#FF0000")

        # 尝试获取 high/low 列
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        # 计算偏移单位
        # 优先使用坐标轴当前的显示范围 (ylim)，这样能保证相对于面板的比例是绝对固定的
        ylim = ax.get_ylim()
        # 检查 ylim 是否有效（不是默认的 0, 1）
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            # 如果坐标轴还没初始化，回退到使用数据范围
            price_range = df[high_col].max() - df[low_col].min()
            # 考虑 matplotlib 默认 padding (约 10%)
            price_range *= 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0

        # 避免 range 为 0
        if price_range == 0:
            price_range = df[high_col].mean() * 0.1 if has_high else 1.0

        # 使用价格范围的 2% 作为基本偏移单位
        offset_unit = price_range * 0.02

        # 构建峰值索引集合，用于快速查找重叠
        peak_indices = {p.index for p in peaks} if peaks else set()

        for bo in breakouts:
            # 使用整数索引而不是日期对象
            bo_x = bo.index  # 整数索引

            # 获取基准高度
            if has_high and 0 <= bo_x < len(df):
                base_price = df.iloc[bo_x][high_col]
            else:
                base_price = bo.price

            # 确定颜色
            color = marker_color

            # 检查是否与峰值重叠
            is_overlap = bo_x in peak_indices

            # 确定文本位置
            if is_overlap:
                # 如果重叠，显示在峰值信息上方
                # KBar -> Marker(0.5) -> PeakText(1.1) -> BOText(2.0)
                # 之前 PeakText 是 marker_y(0.5) + 0.6 = 1.1
                # 所以这里设为 2.0 比较安全 (4% Range)
                text_y = base_price + offset_unit * 2.2
            else:
                # 如果不重叠，显示在 KBar 上方
                # KBar -> BOText(0.8) (1.6% Range)
                text_y = base_price + offset_unit * 0.6

            # 绘制突破分数
            if (
                show_score
                and hasattr(bo, "quality_score")
                and bo.quality_score is not None
            ):
                # 如果有 IDs，分数显示在 IDs 上方
                score_y = text_y
                if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids:
                    score_y += offset_unit * 1.2

                ax.text(
                    bo_x,
                    score_y,
                    f"{bo.quality_score:.0f}",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=text_score_color,
                    weight="bold",
                    zorder=12,
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor=text_bg_color,
                        edgecolor=text_score_color,
                        linewidth=1.0,
                        alpha=0.8,
                    ),
                )

            # 在上方显示被突破的 peaks id 列表
            if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids:
                peak_ids_text = ",".join(map(str, bo.broken_peak_ids))
                ax.text(
                    bo_x,
                    text_y,
                    f"[{peak_ids_text}]",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=color,
                    weight="bold",
                    zorder=11,
                    bbox=dict(
                        boxstyle="round,pad=0.3",
                        facecolor=text_bg_color,
                        edgecolor=color,
                        linewidth=1.5,
                        alpha=0.9,
                    ),
                )

    @staticmethod
    def draw_resistance_zones(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        alpha: float = 0.2,
        color: str = None,
        colors: dict = None,
    ):
        """
        绘制阻力区高亮（半透明矩形）

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            breakouts: Breakout 对象列表
            alpha: 透明度
            color: 阻力区颜色 (如果为None，则尝试从colors中获取)
            colors: 颜色配置字典
        """
        if not breakouts:
            return

        colors = colors or {}
        if color is None:
            color = colors.get("resistance_zone", "#FFEB3B")

        for bo in breakouts:
            # 只高亮多峰值突破的阻力区
            if bo.num_peaks_broken <= 1:
                continue

            # 计算阻力区范围
            prices = [p.price for p in bo.broken_peaks]
            zone_bottom = min(prices)
            zone_top = max(prices)

            # 找到最早的峰值索引（整数）
            earliest_peak_index = min(p.index for p in bo.broken_peaks)

            # 突破索引（整数）
            bo_x = bo.index

            # 确保有一定高度
            if zone_top == zone_bottom:
                margin = zone_bottom * 0.001
                zone_bottom -= margin
                zone_top += margin

            height = zone_top - zone_bottom
            width = bo_x - earliest_peak_index

            # 使用 Rectangle 绘制，绑定到数据坐标
            rect = mpatches.Rectangle(
                (earliest_peak_index, zone_bottom),
                width,
                height,
                color=color,
                alpha=alpha,
                zorder=1,
                linewidth=0,
            )
            ax.add_patch(rect)

    @staticmethod
    def draw_troughs(
        ax,
        df: pd.DataFrame,
        troughs: list,
        colors: dict = None,
    ):
        """
        绘制低谷标记（实心正三角，位于 K 线下方）

        用于显示 V 形反转/双底信号中的 Trough1。
        每个 trough 可通过 color 属性指定独立颜色。
        支持同一 K 线位置有多个 TR1 时垂直排列显示。
        排列顺序：D 在上，R 在下。

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
            troughs: Trough 对象列表，每个对象需有 index, price 属性，
                     可选 color, signal_type 属性
            colors: 颜色配置字典（提供默认颜色）
        """
        if not troughs:
            return

        colors = colors or {}
        default_color = colors.get("trough_marker", "#9C27B0")  # 默认紫色

        # 尝试获取 high/low 列
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        # 计算偏移单位
        ylim = ax.get_ylim()
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            price_range = df[high_col].max() - df[low_col].min()
            price_range *= 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0

        if price_range == 0:
            price_range = df[high_col].mean() * 0.1 if has_high else 1.0

        offset_unit = price_range * 0.02

        # 按 index 分组，处理同一 K 线位置的多个 trough
        troughs_by_index = defaultdict(list)
        for trough in troughs:
            troughs_by_index[trough.index].append(trough)

        # 定义信号类型优先级（数字越小越靠下）
        SIGNAL_PRIORITY = {"D": 0}

        first_drawn = False
        for trough_x, group in troughs_by_index.items():
            # 按信号类型排序：R 在前（下），D 在后（上）
            group.sort(key=lambda t: SIGNAL_PRIORITY.get(getattr(t, 'signal_type', ''), 99))

            # 获取基准低点 (K bar low)
            if has_low and 0 <= trough_x < len(df):
                base_price = df.iloc[trough_x][low_col]
            else:
                base_price = group[0].price

            # 绘制每个 trough，垂直排列
            for stack_idx, trough in enumerate(group):
                # 基础偏移 + 堆叠偏移（每个标记间隔 0.6 个单位）
                marker_y = base_price - offset_unit * (0.6 + stack_idx * 0.6)

                # 优先使用 trough 对象上的颜色，否则使用默认颜色
                marker_color = getattr(trough, 'color', default_color)

                ax.scatter(
                    trough_x,
                    marker_y,
                    marker="^",  # 正三角（朝上）
                    s=400,
                    facecolors=marker_color,  # 实心填充
                    edgecolors=marker_color,
                    linewidths=2,
                    zorder=5,
                    alpha=1.0,
                    label="Trough1" if not first_drawn else None,
                )
                first_drawn = True

    @staticmethod
    def draw_support_troughs(
        ax,
        df: pd.DataFrame,
        troughs: list,
        colors: dict = None,
    ):
        """
        绘制支撑 trough 标记（空心正三角 + 编号，位于 K 线下方）

        与 Peak 标记镜像对称：
        - 标记位置：K 线最低价 - 1.2% 价格范围
        - 编号位置：标记下方 - 2.4% 价格范围

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
            troughs: trough 对象列表，每个需有 index, price, id 字段
            colors: 颜色配置字典
        """
        if not troughs:
            return

        colors = colors or {}
        marker_color = colors.get("support_trough_marker", "#000000")
        text_id_color = colors.get("support_trough_text_id", "#000000")

        # 尝试获取 high/low 列
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        # 计算偏移单位
        ylim = ax.get_ylim()
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            price_range = df[high_col].max() - df[low_col].min()
            price_range *= 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0

        if price_range == 0:
            price_range = df[low_col].mean() * 0.1 if has_low else 1.0

        offset_unit = price_range * 0.02

        first_drawn = False
        for trough in troughs:
            trough_x = trough.index  # 本地索引

            # 获取基准低点 (K bar low)
            if has_low and 0 <= trough_x < len(df):
                base_price = df.iloc[trough_x][low_col]
            else:
                base_price = trough.price

            # 1. 绘制 trough 标记（空心正三角，位于 K bar 下方）
            marker_y = base_price - offset_unit * 0.6

            ax.scatter(
                trough_x,
                marker_y,
                marker="^",  # 正三角
                s=400,
                facecolors="none",  # 空心
                edgecolors=marker_color,
                linewidths=2,
                zorder=5,
                alpha=1.0,
                label="Support Trough" if not first_drawn else None,
            )
            first_drawn = True

            # 2. 添加 ID 标注 (位于标记下方)
            text_y = marker_y - offset_unit * 0.6

            if trough.id is not None:
                ax.text(
                    trough_x,
                    text_y,
                    f"{trough.id}",
                    fontsize=20,
                    ha="center",
                    va="top",  # 文字顶部对齐标记位置
                    color=text_id_color,
                    weight="bold",
                )

    @staticmethod
    def draw_price_line(
        ax,
        df: pd.DataFrame,
        price: float,
        label: str,
        color: str = "red",
        linestyle: str = "--",
    ):
        """
        绘制水平价格线

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            price: 价格
            label: 标签
            color: 颜色
            linestyle: 线型
        """
        ax.axhline(
            y=price,
            color=color,
            linestyle=linestyle,
            linewidth=1.5,
            alpha=0.7,
            label=label,
            zorder=2,
        )

    @staticmethod
    def draw_moving_averages(
        ax,
        df: pd.DataFrame,
        ma_periods: list = None,
        colors: dict = None,
    ):
        """
        绘制移动平均线

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            ma_periods: 均线周期列表，如 [50, 150, 200]
            colors: 颜色配置字典
        """
        if ma_periods is None:
            ma_periods = [200]  # 默认只显示 MA200

        if colors is None:
            colors = {}

        # 颜色映射
        color_map = {
            50: colors.get("ma_50", "#FFA500"),
            150: colors.get("ma_150", "#9370DB"),
            200: colors.get("ma_200", "#4169E1"),
        }

        for period in ma_periods:
            # 优先使用预计算的均线列（数据加载时已计算，包含缓冲区）
            ma_col = f"ma_{period}"
            if ma_col in df.columns:
                ma_series = df[ma_col]
            elif len(df) >= period:
                # 回退：实时计算（数据可能不含缓冲区，均线会延迟显示）
                ma_series = df["close"].rolling(window=period).mean()
            else:
                continue  # 数据不足，跳过

            # 获取颜色
            color = color_map.get(period, "#808080")

            # 绘制均线（使用整数索引，与K线图保持一致）
            x_positions = range(len(df))
            ax.plot(
                x_positions,
                ma_series,
                color=color,
                linewidth=1.2,
                alpha=0.8,
                label=f"MA{period}",
                zorder=4,  # 在K线之上，标记之下
            )
