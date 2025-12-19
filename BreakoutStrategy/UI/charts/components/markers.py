"""标记组件 - 绘制峰值、突破点、阻力区"""

import matplotlib.patches as mpatches
import pandas as pd


class MarkerComponent:
    """标记绘制组件"""

    @staticmethod
    def draw_peaks(
        ax,
        df: pd.DataFrame,
        peaks: list,
        colors: dict = None,
    ):
        """
        绘制峰值标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
            peaks: Peak 对象列表
            colors: 颜色配置字典
        """
        if not peaks:
            return

        colors = colors or {}
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
                facecolors="none",  # 空心
                edgecolors=color,  # 边缘颜色
                linewidths=2,
                zorder=5,
                alpha=1.0,
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
