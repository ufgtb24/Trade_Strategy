"""标记组件 - 绘制峰值、突破点、阻力区"""

import matplotlib.patches as mpatches
import pandas as pd


def _classify_bo(
    idx: int,
    current: int | None,
    visible: set[int],
    filtered_out: set[int],
) -> str:
    """Classify a BO into one of 4 live-UI tiers.

    Args:
        idx: This BO's chart-df index.
        current: Currently-selected BO's chart-df index (or None).
        visible: matched BO indices that appear in the MatchList right now.
        filtered_out: matched BO indices that are hidden by MatchList filter.

    Returns one of: "current" | "visible" | "filtered_out" | "plain".
    """
    if current is not None and idx == current:
        return "current"
    if idx in visible:
        return "visible"
    if idx in filtered_out:
        return "filtered_out"
    return "plain"


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

                score_text = f"{bo.quality_score:.0f}"

                ax.text(
                    bo_x,
                    score_y,
                    score_text,
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
    def draw_breakouts_live_mode(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        current_bo_index,
        visible_matched_indices: set[int] | None = None,
        filtered_out_matched_indices: set[int] | None = None,
        peaks: list = None,
        colors: dict = None,
    ):
        """Live UI 专用：按 4 级（current/visible/filtered_out/plain）画圆圈 marker + 蓝字 label。

        - current BO：深蓝实心、zorder=13、picker
        - visible matched BO：浅蓝实心、zorder=12、picker
        - filtered_out matched BO：青绿实心 alpha=0.7、zorder=11、picker（点击仅提示）
        - plain BO：浅蓝空心、zorder=10、无 picker

        每组独立 `ax.scatter`，以便 pick_event 通过 artist 区分归属。三组可点击
        scatter 在 artist 上挂 `.bo_chart_indices` 列表，pick 回调用 event.ind[0]
        反查。label [broken_peak_ids] 共用一次循环独立画。
        """
        if not breakouts:
            return

        if visible_matched_indices is None:
            visible_matched_indices = set()
        if filtered_out_matched_indices is None:
            filtered_out_matched_indices = set()
        colors = colors or {}
        color_current = colors.get("bo_marker_current", "#1565C0")
        color_visible = colors.get("bo_marker_visible", "#64B5F6")
        color_filtered = colors.get("bo_marker_filtered_out", "#9E9E9E")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")

        # y 偏移计算（与 draw_breakouts 保持一致）
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        ylim = ax.get_ylim()
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            price_range = (df[high_col].max() - df[low_col].min()) * 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0
        if price_range == 0:
            price_range = df[high_col].mean() * 0.1 if has_high else 1.0
        offset_unit = price_range * 0.02

        peak_indices = {p.index for p in peaks} if peaks else set()

        # 按 4 级分桶
        buckets: dict[str, list[tuple[int, float, float]]] = {
            "current": [], "visible": [], "filtered_out": [], "plain": [],
        }
        label_items: list[tuple[int, float, str]] = []

        for bo in breakouts:
            bo_x = bo.index
            base_price = (
                df.iloc[bo_x][high_col] if has_high and 0 <= bo_x < len(df) else bo.price
            )

            is_overlap = bo_x in peak_indices
            if is_overlap:
                label_y = base_price + offset_unit * 2.2
                marker_y = base_price + offset_unit * 4.0
            else:
                label_y = base_price + offset_unit * 0.6
                marker_y = base_price + offset_unit * 2.4

            tier = _classify_bo(
                bo_x, current_bo_index, visible_matched_indices, filtered_out_matched_indices,
            )
            buckets[tier].append((bo_x, marker_y, base_price))

            if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids:
                peak_ids_text = ",".join(map(str, bo.broken_peak_ids))
                label_items.append((bo_x, label_y, f"[{peak_ids_text}]"))

        # 画 4 组 scatter，zorder 逐级抬高，可点击三组挂属性
        def _draw_group(name, face, edge, zorder, pickable, alpha=1.0):
            pts = buckets[name]
            if not pts:
                return
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            idxs = [p[0] for p in pts]
            kwargs = dict(
                marker="o", s=400, facecolors=face, edgecolors=edge,
                linewidths=2, zorder=zorder, alpha=alpha,
            )
            if pickable:
                kwargs["picker"] = True
                kwargs["pickradius"] = 8
            sc = ax.scatter(xs, ys, **kwargs)
            # 所有组都挂，pick 回调只会对 pickable 的触发
            sc.bo_chart_indices = idxs
            sc.bo_tier = name
            return sc

        # plain：空心 + 深蓝边（与 current 同色，仅形状/填充区分）
        # 三种实心（filtered_out/visible/current）：黑色边，face 体现 tier
        edge_filled = "#000000"
        _draw_group("plain", "none", color_current, zorder=10, pickable=False)
        _draw_group("filtered_out", color_filtered, edge_filled, zorder=11, pickable=True, alpha=0.7)
        _draw_group("visible", color_visible, edge_filled, zorder=12, pickable=True)
        _draw_group("current", color_current, edge_filled, zorder=13, pickable=True)

        # label 颜色统一用 current 深蓝，不随 tier 变——4 种背景+4 种 label 色会让
        # 密集 BO 区域视觉过载；marker 形状/色已足以区分 tier，label 仅需可读
        label_color = color_current
        for bo_x, label_y, text in label_items:
            ax.text(
                bo_x, label_y, text,
                fontsize=20, ha="center", va="bottom",
                color=label_color, weight="bold", zorder=10,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=text_bg_color, edgecolor=label_color,
                    linewidth=1.5, alpha=0.9,
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

    @staticmethod
    def draw_template_highlights(
        ax,
        matched_indices: list[int],
        color: str = "#00FF00",
        alpha: float = 0.15,
    ):
        """绘制模板匹配突破的全高垂直高亮条。

        Args:
            ax: matplotlib Axes 对象
            matched_indices: 匹配突破的整数索引列表（在 display_df 中的位置）
            color: 高亮颜色
            alpha: 透明度
        """
        for idx in matched_indices:
            ax.axvspan(idx - 0.4, idx + 0.4, color=color, alpha=alpha, zorder=0)
