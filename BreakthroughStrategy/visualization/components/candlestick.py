"""K线图组件"""

from typing import Optional

import matplotlib.patches as mpatches
import pandas as pd


class CandlestickComponent:
    """K线图绘制组件"""

    @staticmethod
    def draw(ax, df: pd.DataFrame, style: str = "charles", colors: dict = None):
        """
        在指定 Axes 上绘制 K线图（手动绘制，不使用mplfinance）

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex 和标准列名)
            style: K线样式 (保留参数用于兼容性，暂未使用)
            colors: 颜色配置字典
        """
        # 确保列名标准化
        df = CandlestickComponent._normalize_columns(df)

        colors = colors or {}
        # 颜色配置
        up_color = colors.get("candlestick_up", "#4CAF50")  # 浅绿色 (上涨)
        down_color = colors.get("candlestick_down", "#B71C1C")  # 深红色 (下跌)
        width = 0.8

        # 使用整数索引绘制K线
        for i in range(len(df)):
            row = df.iloc[i]
            o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]

            # 确定颜色
            color = up_color if c >= o else down_color

            # 绘制上下影线
            ax.plot(
                [i, i],
                [l, h],
                color=color,
                linewidth=3.0,
                solid_capstyle="round",
                zorder=2,
            )

            # 绘制实体
            body_low = min(o, c)
            body_high = max(o, c)
            body_height = body_high - body_low if body_high != body_low else 0.0001

            rect = mpatches.Rectangle(
                (i - width / 2, body_low),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                zorder=3,
            )
            ax.add_patch(rect)

        # 设置X轴刻度和标签
        CandlestickComponent._format_xaxis(ax, df)

        # ax.set_ylabel("Price ($)", fontsize=24)

        # 设置左右留白 (左侧少，右侧多用于悬浮窗)
        margin_right = max(5, len(df) * 0.05)  # 15% right margin
        margin_left = max(1, len(df) * 0.02)  # 2% left margin
        ax.set_xlim(-0.5 - margin_left, len(df) - 0.5 + margin_right)

        ax.grid(True, alpha=0.3, linestyle="--", axis="y")

    @staticmethod
    def draw_volume_background(
        ax,
        df: pd.DataFrame,
        highlight_dates: Optional[list] = None,
        volume_scale_ratio: float = 0.2,
        colors: dict = None,
    ):
        """
        在主图上绘制成交量作为背景（参考 new_trade 实现）

        Args:
            ax: matplotlib Axes 对象（主K线图的axes）
            df: OHLCV DataFrame
            highlight_dates: 需要高亮的日期列表 (突破日期)
            volume_scale_ratio: 成交量占显示高度的比例（默认20%）
            colors: 颜色配置字典
        """
        df = CandlestickComponent._normalize_columns(df)

        if len(df) == 0:
            return

        colors = colors or {}
        vol_up_color = colors.get("volume_up", "#D3D3D3")
        vol_down_color = colors.get("volume_down", "#696969")
        vol_highlight_color = colors.get("volume_highlight", "#FFD700")

        # 计算价格范围和显示区域
        price_min = df[["Open", "High", "Low", "Close"]].min().min()
        price_max = df[["Open", "High", "Low", "Close"]].max().max()
        price_range = price_max - price_min

        # 使用80%空间显示价格，顶部10%和底部10%留白用于成交量和标记
        display_height = price_range / 0.8
        display_bottom = price_min - (display_height * 0.1)

        # 成交量缩放因子
        volume_max = df["Volume"].max()
        volume_scale_factor = (
            (display_height * volume_scale_ratio) / volume_max
            if volume_max > 0
            else 1.0
        )

        # 设置Y轴范围
        y_bottom = display_bottom
        y_top = display_bottom + display_height
        ax.set_ylim(y_bottom, y_top)

        # 绘制成交量柱状图作为背景
        for i in range(len(df)):
            row = df.iloc[i]
            volume = row["Volume"]
            o, c = row["Open"], row["Close"]

            # 确定颜色
            if df.index[i] in (highlight_dates or []):
                volume_color = vol_highlight_color  # 高亮（突破日期）
            elif c >= o:
                volume_color = vol_up_color  # 上涨
            else:
                volume_color = vol_down_color  # 下跌

            # 绘制成交量柱
            volume_height = volume * volume_scale_factor
            ax.bar(
                i,
                volume_height,
                bottom=display_bottom,
                width=1.0,
                color=volume_color,
                edgecolor="black",
                linewidth=0.5,
                alpha=0.8,
                zorder=1,
            )

    @staticmethod
    def draw_volume(
        ax,
        df: pd.DataFrame,
        highlight_dates: Optional[list] = None,
        colors: dict = None,
    ):
        """
        绘制成交量图

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            highlight_dates: 需要高亮的日期列表 (突破日期)
            colors: 颜色配置字典
        """
        df = CandlestickComponent._normalize_columns(df)

        colors_config = colors or {}
        vol_up_color = colors_config.get("volume_up", "#D3D3D3")
        vol_down_color = colors_config.get("volume_down", "#696969")
        vol_highlight_color = colors_config.get("volume_highlight", "#FFD700")

        # 绘制成交量柱状图（使用整数索引）
        bar_colors = []
        for i in range(len(df)):
            if df.index[i] in (highlight_dates or []):
                bar_colors.append(vol_highlight_color)  # 高亮
            elif df["Close"].iloc[i] >= df["Open"].iloc[i]:
                bar_colors.append(vol_up_color)  # 上涨
            else:
                bar_colors.append(vol_down_color)  # 下跌

        # 使用整数索引而不是日期索引
        x_positions = range(len(df))
        ax.bar(
            x_positions,
            df["Volume"],
            color=bar_colors,
            alpha=0.8,
            width=1.0,
            edgecolor="black",
            linewidth=0.5,
        )

        # 设置X轴刻度和标签
        CandlestickComponent._format_xaxis(ax, df)

        ax.set_ylabel("Volume", fontsize=24)

        # 设置左右留白 (左侧少，右侧多用于悬浮窗)
        margin_right = max(5, len(df) * 0.15)  # 15% right margin
        margin_left = max(1, len(df) * 0.02)  # 2% left margin
        ax.set_xlim(-0.5 - margin_left, len(df) - 0.5 + margin_right)

        ax.grid(True, alpha=0.3, linestyle="--", axis="y")

    @staticmethod
    def _format_xaxis(ax, df: pd.DataFrame):
        """
        格式化X轴，显示日期标签

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
        """
        if len(df) == 0:
            return

        # 计算跨越月份数，决定刻度间隔
        start_date = df.index[0].date()
        end_date = df.index[-1].date()
        months_diff = (end_date.year - start_date.year) * 12 + (
            end_date.month - start_date.month
        )

        step_days = 21 if months_diff <= 13 else 42  # 交易日步长
        interval_label = "Interval: 1M(21)" if step_days == 21 else "Interval: 2M(42)"

        # 以最后一个日期为基准（因为通常关注最新的数据）
        base_pos = len(df) - 1

        tick_positions = []

        # 从基准位置向左扩展
        curr_pos = base_pos
        while curr_pos >= 0:
            tick_positions.append(curr_pos)
            curr_pos -= step_days

        # 排序
        tick_positions = sorted(tick_positions)

        # 设置刻度
        ax.set_xticks(tick_positions)

        # 取消底部日期显示
        ax.set_xticklabels([])

        # 添加垂直网格线 (代表日期的纵坐标刻度线)
        ax.grid(True, axis="x", linestyle="-", alpha=0.3, color="gray")

        # 在图形底部中间显示间隔信息
        # 使用 transform=ax.transAxes 使得坐标相对于 axes (0-1)
        ax.text(
            0.5,
            0.02,
            interval_label,
            ha="center",
            va="bottom",
            transform=ax.transAxes,
            fontsize=12,
            color="black",
            alpha=0.8,
            bbox=dict(
                boxstyle="round,pad=0.2", facecolor="white", edgecolor="gray", alpha=0.3
            ),
        )

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化列名

        Args:
            df: 输入 DataFrame

        Returns:
            标准化后的 DataFrame
        """
        df = df.copy()

        # 列名映射
        column_mapping = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }

        # 重命名列
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)

        # 检查必需列
        required_columns = ["Open", "High", "Low", "Close"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        return df
