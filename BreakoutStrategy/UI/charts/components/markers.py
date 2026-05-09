"""标记组件 - 绘制峰值、突破点、阻力区"""

import matplotlib.patches as mpatches
import pandas as pd


def _classify_bo(
    idx: int,
    current: int | None,
    visible: set[int],
    filtered_out: set[int],
) -> tuple[str, bool]:
    """Classify a BO into visual tier + pickability.

    Visual tier (3 values) drives bbox color via BO_LABEL_TIER_STYLE;
    pickability is independent — matched BOs passing the filter are clickable,
    matched BOs outside the filter share the same visual but are inert.

    Args:
        idx: This BO's chart-df index.
        current: Currently-selected BO's chart-df index (or None).
        visible: matched BO indices that appear in the MatchList right now.
        filtered_out: matched BO indices that are hidden by MatchList filter.

    Returns:
        (tier, pickable) where tier is "current" | "matched" | "plain".
    """
    if current is not None and idx == current:
        return "current", True
    if idx in visible:
        return "matched", True
    if idx in filtered_out:
        return "matched", False
    return "plain", False


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

        # 尝试获取 high 列，处理大小写
        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        from matplotlib.transforms import offset_copy
        from BreakoutStrategy.UI.styles import compute_marker_offsets_pt

        for peak in peaks:
            peak_x = peak.index

            # 获取基准高度 (K bar high)
            if has_high and 0 <= peak_x < len(df):
                base_price = df.iloc[peak_x][high_col]
            else:
                base_price = peak.price

            color = marker_color

            layers = ["triangle", "peak_id"] if peak.id is not None else ["triangle"]
            offsets = compute_marker_offsets_pt(layers)

            marker_trans = offset_copy(
                ax.transData, fig=ax.get_figure(),
                x=0.0, y=offsets["triangle"], units="points",
            )

            # 1. 绘制峰值标记（倒三角，像素偏移避免遮挡 K 线）
            ax.scatter(
                peak_x,
                base_price,
                marker="v",
                s=400,
                facecolors="none" if style == "normal" else color,
                edgecolors=color,
                linewidths=2,
                zorder=5,
                alpha=1.0 if style == "normal" else 0.6,
                label="Peak" if peak == peaks[0] else None,
                transform=marker_trans,
            )

            # 2. 添加 ID 标注（像素偏移，不受 Y 轴缩放影响）
            if peak.id is not None:
                ax.annotate(
                    f"{peak.id}",
                    xy=(peak_x, base_price),
                    xycoords="data",
                    xytext=(0, offsets["peak_id"]),
                    textcoords="offset points",
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
        show_label: bool = False,
        label_n: int = 20,
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
            show_score: 是否显示 quality_score
            show_label: 是否显示回测 label 值（窗口 = label_n 天）
            label_n: label 计算窗口天数
        """
        if not breakouts:
            return

        colors = colors or {}
        marker_color = colors.get("breakout_marker", "#0000FF")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")
        text_score_color = colors.get("breakout_text_score", "#FF0000")

        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        from BreakoutStrategy.UI.styles import (
            BO_LABEL_VALUE_TIER_STYLE,
            compute_marker_offsets_pt,
        )
        from BreakoutStrategy.analysis.features import compute_label_value

        # 构建峰值索引集合（两层：是否存在 peak / peak 是否带 id）
        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )

        # 第 1 遍：若开启 show_label，为所有 BO 预先计算 label value，并找出最大值
        bo_label_values: dict[int, float] = {}
        max_label_value = None
        if show_label:
            for bo in breakouts:
                v = compute_label_value(df, bo.index, label_n)
                if v is not None:
                    bo_label_values[bo.index] = v
            if bo_label_values:
                max_label_value = max(bo_label_values.values())

        # 第 2 遍：逐 BO 绘制
        for bo in breakouts:
            bo_x = bo.index

            if has_high and 0 <= bo_x < len(df):
                base_price = df.iloc[bo_x][high_col]
            else:
                base_price = bo.price

            color = marker_color

            has_broken_ids = bool(getattr(bo, "broken_peak_ids", None))
            has_score = (
                show_score
                and hasattr(bo, "quality_score")
                and bo.quality_score is not None
            )
            has_label_value = show_label and bo_x in bo_label_values

            # 构造本 bar 实际存在的堆叠层（自下而上）
            layers: list[str] = []
            if bo_x in peak_indices:
                layers.append("triangle")
                if bo_x in peak_id_indices:
                    layers.append("peak_id")
            if has_broken_ids:
                layers.append("bo_label")
            if has_score and has_broken_ids:
                layers.append("bo_score")
            if has_label_value and (has_score or has_broken_ids):
                layers.append("bo_label_value")

            offsets = compute_marker_offsets_pt(layers) if layers else {}

            # 绘制突破分数
            if has_score:
                if has_broken_ids:
                    score_y = offsets["bo_score"]
                else:
                    tmp_layers = layers + ["bo_label"]
                    score_y = compute_marker_offsets_pt(tmp_layers)["bo_label"]

                score_text = f"{bo.quality_score:.0f}"
                ax.annotate(
                    score_text,
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, score_y),
                    textcoords="offset points",
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

            # 绘制回测 label 值
            if has_label_value:
                value = bo_label_values[bo_x]
                # Tier 分类（浮点等值用容差）
                is_max = (
                    max_label_value is not None
                    and abs(value - max_label_value) < 1e-9
                )
                tier = "max" if is_max else "other"
                tier_style = BO_LABEL_VALUE_TIER_STYLE[tier]

                # 计算 y 偏移
                if "bo_label_value" in offsets:
                    label_value_y = offsets["bo_label_value"]
                else:
                    # 只有 label_value，无 score 无 broken_ids：退到 bo_score 位
                    tmp_layers = layers + ["bo_score"]
                    label_value_y = compute_marker_offsets_pt(tmp_layers)["bo_score"]

                sign = "+" if value >= 0 else ""
                value_text = f"{sign}{value * 100:.1f}%"

                ax.annotate(
                    value_text,
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, label_value_y),
                    textcoords="offset points",
                    fontsize=20,
                    ha="center",
                    va="bottom",
                    color=tier_style["fg"],
                    weight="bold",
                    zorder=14 if tier == "max" else 12,
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor=tier_style["bg"],
                        edgecolor=tier_style["fg"],
                        linewidth=1.0,
                        alpha=0.9,
                    ),
                )

            # 在上方显示被突破的 peaks id 列表
            if has_broken_ids:
                peak_ids_text = ",".join(map(str, bo.broken_peak_ids))
                ax.annotate(
                    f"[{peak_ids_text}]",
                    xy=(bo_x, base_price),
                    xycoords="data",
                    xytext=(0, offsets["bo_label"]),
                    textcoords="offset points",
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
        """Live UI 专用：以 bo_label annotation 作为单一 BO marker。

        视觉三态（current / matched / plain）通过 BO_LABEL_TIER_STYLE 查背景/
        文字色，边框统一为 CHART_COLORS['bo_marker_current']（深蓝）。

        Pickability 与视觉独立：current 与通过 filter 的 matched 挂 picker=True
        并记 `.bo_chart_idx`；被 filter 过滤掉的 matched 与 plain 不可点击。
        所有 annotation 都会记 `.bo_tier` 便于测试/调试。

        注：`colors` 参数为签名兼容保留（canvas_manager 仍会传入），实际使用的
        颜色一律取自 BO_LABEL_TIER_STYLE / CHART_COLORS（SSoT）。
        """
        if not breakouts:
            return

        if visible_matched_indices is None:
            visible_matched_indices = set()
        if filtered_out_matched_indices is None:
            filtered_out_matched_indices = set()

        from BreakoutStrategy.UI.styles import (
            BO_LABEL_TIER_STYLE,
            CHART_COLORS,
            compute_marker_offsets_pt,
        )

        border_color = CHART_COLORS["bo_marker_current"]

        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )

        tier_zorder = {
            "current": 13,
            "matched": 11,
            "plain": 10,
        }

        for bo in breakouts:
            if not getattr(bo, "broken_peak_ids", None):
                continue

            bo_x = bo.index
            base_price = (
                df.iloc[bo_x][high_col]
                if has_high and 0 <= bo_x < len(df)
                else bo.price
            )

            tier, pickable = _classify_bo(
                bo_x,
                current_bo_index,
                visible_matched_indices,
                filtered_out_matched_indices,
            )

            # 构造本 bar 实际存在的堆叠层（自下而上）
            if bo_x in peak_id_indices:
                layers = ["triangle", "peak_id", "bo_label"]
            elif bo_x in peak_indices:
                layers = ["triangle", "bo_label"]
            else:
                layers = ["bo_label"]
            offset_pt = compute_marker_offsets_pt(layers)["bo_label"]

            style = BO_LABEL_TIER_STYLE[tier]
            text = "[" + ",".join(map(str, bo.broken_peak_ids)) + "]"

            kwargs = dict(
                xy=(bo_x, base_price),
                xycoords="data",
                xytext=(0, offset_pt),
                textcoords="offset points",
                fontsize=20,
                ha="center",
                va="bottom",
                color=style["fg"],
                weight="bold",
                zorder=tier_zorder[tier],
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=style["bg"],
                    edgecolor=border_color,
                    linewidth=1.5,
                    alpha=0.9,
                ),
            )
            if pickable:
                kwargs["picker"] = True

            ann = ax.annotate(text, **kwargs)
            ann.bo_chart_idx = bo_x
            ann.bo_tier = tier

    @staticmethod
    def draw_filtered_breakouts(
        ax,
        df: pd.DataFrame,
        infos: list,
        peaks: list = None,
        colors: dict = None,
    ):
        """绘制被价格门过滤的 BO（仅参考显示）。

        简化版：灰色 [broken_peak_ids] 标签框，无 quality_score / label_value
        / 阻力区（这些字段在过滤路径下根本没计算，is by-design）。

        若同一根 K 线上存在已绘制的 peak（active/broken/superseded），按
        compute_marker_offsets_pt 做层堆叠避免覆盖——与 draw_breakouts_
        live_mode 同样的方式。

        Args:
            ax: matplotlib Axes
            df: OHLCV DataFrame
            infos: BreakoutInfo 列表（不是 Breakout）
            peaks: 当前图上已绘制的 peak 列表（用于堆叠计算）
            colors: 颜色配置字典（复用 peak_marker_superseded 的灰色调）
        """
        if not infos:
            return

        colors = colors or {}
        marker_color = colors.get("peak_marker_superseded", "#808080")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")

        high_col = "high" if "high" in df.columns else "High"
        has_high = high_col in df.columns

        from BreakoutStrategy.UI.styles import compute_marker_offsets_pt

        # 与 draw_breakouts_live_mode 一致的层堆叠规则
        peak_indices = {p.index for p in peaks} if peaks else set()
        peak_id_indices = (
            {p.index for p in peaks if getattr(p, "id", None) is not None}
            if peaks else set()
        )

        for info in infos:
            bo_x = info.current_index

            if has_high and 0 <= bo_x < len(df):
                base_price = df.iloc[bo_x][high_col]
            else:
                base_price = info.current_price

            broken_ids = [p.id for p in info.broken_peaks if p.id is not None]
            if not broken_ids:
                continue

            # 决定本 bar 上方实际堆叠层；filtered BO 的标签层语义对齐 bo_label
            if bo_x in peak_id_indices:
                layers = ["triangle", "peak_id", "bo_label"]
            elif bo_x in peak_indices:
                layers = ["triangle", "bo_label"]
            else:
                layers = ["bo_label"]
            offset_pt = compute_marker_offsets_pt(layers)["bo_label"]

            text = "[" + ",".join(map(str, broken_ids)) + "]"
            ax.annotate(
                text,
                xy=(bo_x, base_price),
                xycoords="data",
                xytext=(0, offset_pt),
                textcoords="offset points",
                fontsize=20,
                ha="center",
                va="bottom",
                color=marker_color,
                weight="bold",
                zorder=8,
                alpha=0.7,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=text_bg_color,
                    edgecolor=marker_color,
                    linewidth=1.0,
                    alpha=0.7,
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
    def draw_peak_supersedes(
        ax,
        df: pd.DataFrame,
        killer_to_victims: dict[int, list[int]],
        colors: dict = None,
    ):
        """在 killer bar 下影线下方绘制 ▲ 三角 + [victim_ids] 方框。

        与上方 peak/bo 标记镜像：锚点为 K线 Low，使用 LOWER_MARKER_STACK_GAPS_PT
        的负偏移堆叠（详见 styles.compute_marker_offsets_below_pt）。

        Args:
            ax: matplotlib Axes
            df: OHLCV DataFrame（需含 low / Low 列）
            killer_to_victims: {bar_index: [victim_peak_id, ...]} —— 每个 killer
                bar 对应它令哪些 peak ids 退场。空列表跳过。
            colors: 颜色配置（可选；缺省取灰色调，与 SU_PK 灰色 victim ▽ 同色系）
        """
        if not killer_to_victims:
            return

        from matplotlib.transforms import offset_copy
        from BreakoutStrategy.UI.styles import compute_marker_offsets_below_pt

        colors = colors or {}
        # killer 三角用黑色实心，与 victim 灰色 ▽ 区分（killer 强调 / victim 标记位置）
        triangle_color = "#000000"
        # [ids] 方框边框跟随三角色，文字保持黑色，背景白色
        text_color = colors.get("peak_text_id_superseded", "#000000")
        text_bg = colors.get("breakout_text_bg", "#FFFFFF")

        low_col = "low" if "low" in df.columns else ("Low" if "Low" in df.columns else None)
        if low_col is None:
            return

        offsets = compute_marker_offsets_below_pt(
            ["triangle_down", "supersede_label"]
        )

        for bar_idx, victim_ids in killer_to_victims.items():
            if not victim_ids:
                continue
            if bar_idx < 0 or bar_idx >= len(df):
                continue
            base_low = df.iloc[bar_idx][low_col]

            # 1. ▲ 三角（黑色实心，指向 K 线方向）：scatter offset_copy 走负 y
            tri_trans = offset_copy(
                ax.transData, fig=ax.get_figure(),
                x=0.0, y=offsets["triangle_down"], units="points",
            )
            ax.scatter(
                bar_idx,
                base_low,
                marker="^",
                s=400,
                facecolors=triangle_color,
                edgecolors=triangle_color,
                linewidths=2,
                zorder=5,
                transform=tri_trans,
            )

            # 2. [ids] 方框：annotation va="top"，bbox 上沿对齐 supersede_label offset
            ids_text = "[" + ",".join(map(str, victim_ids)) + "]"
            ann = ax.annotate(
                ids_text,
                xy=(bar_idx, base_low),
                xycoords="data",
                xytext=(0, offsets["supersede_label"]),
                textcoords="offset points",
                fontsize=20,
                ha="center",
                va="top",
                color=text_color,
                weight="bold",
                zorder=11,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=text_bg,
                    edgecolor=triangle_color,
                    linewidth=1.5,
                    alpha=0.9,
                ),
            )
            ann.is_supersede_label = True
