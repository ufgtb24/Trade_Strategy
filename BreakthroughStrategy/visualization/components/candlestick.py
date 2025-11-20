"""K线图组件"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Optional


class CandlestickComponent:
    """K线图绘制组件"""

    @staticmethod
    def draw(ax, df: pd.DataFrame, style: str = 'charles'):
        """
        在指定 Axes 上绘制 K线图（手动绘制，不使用mplfinance）

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex 和标准列名)
            style: K线样式 (保留参数用于兼容性，暂未使用)
        """
        # 确保列名标准化
        df = CandlestickComponent._normalize_columns(df)

        # 颜色配置
        up_color = '#26A69A'  # 绿色 (上涨)
        down_color = '#EF5350'  # 红色 (下跌)
        width = 0.6

        # 使用整数索引绘制K线
        for i in range(len(df)):
            row = df.iloc[i]
            o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']

            # 确定颜色
            color = up_color if c >= o else down_color

            # 绘制上下影线
            ax.plot([i, i], [l, h], color=color, linewidth=1.2, solid_capstyle='round', zorder=2)

            # 绘制实体
            body_low = min(o, c)
            body_high = max(o, c)
            body_height = body_high - body_low if body_high != body_low else 0.0001

            rect = mpatches.Rectangle(
                (i - width/2, body_low),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                zorder=3
            )
            ax.add_patch(rect)

        # 设置X轴刻度和标签
        CandlestickComponent._format_xaxis(ax, df)

        ax.set_ylabel('Price ($)', fontsize=10)
        ax.set_xlim(-0.5, len(df) - 0.5)
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')

    @staticmethod
    def draw_volume(ax, df: pd.DataFrame, highlight_dates: Optional[list] = None):
        """
        绘制成交量图

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            highlight_dates: 需要高亮的日期列表 (突破日期)
        """
        df = CandlestickComponent._normalize_columns(df)

        # 绘制成交量柱状图（使用整数索引）
        colors = []
        for i in range(len(df)):
            if df.index[i] in (highlight_dates or []):
                colors.append('#FFD700')  # 金色高亮
            elif i > 0 and df['Close'].iloc[i] >= df['Close'].iloc[i-1]:
                colors.append('#26A69A')  # 绿色 (上涨)
            else:
                colors.append('#EF5350')  # 红色 (下跌)

        # 使用整数索引而不是日期索引
        x_positions = range(len(df))
        ax.bar(x_positions, df['Volume'], color=colors, alpha=0.6, width=0.8)

        # 设置X轴刻度和标签
        CandlestickComponent._format_xaxis(ax, df)

        ax.set_ylabel('Volume', fontsize=10)
        ax.set_xlim(-0.5, len(df) - 0.5)
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')

    @staticmethod
    def _format_xaxis(ax, df: pd.DataFrame):
        """
        格式化X轴，显示日期标签

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
        """
        # 根据数据长度决定显示多少个刻度
        n_ticks = min(10, len(df))
        if len(df) <= 20:
            n_ticks = len(df)
        elif len(df) <= 100:
            n_ticks = 10
        else:
            n_ticks = 15

        # 计算刻度位置（均匀分布）
        tick_positions = [int(i * (len(df) - 1) / (n_ticks - 1)) for i in range(n_ticks)]

        # 获取对应的日期标签
        tick_labels = [df.index[pos].strftime('%Y-%m-%d') for pos in tick_positions]

        # 设置刻度
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)

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
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }

        # 重命名列
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df.rename(columns={old_name: new_name}, inplace=True)

        # 检查必需列
        required_columns = ['Open', 'High', 'Low', 'Close']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        return df
