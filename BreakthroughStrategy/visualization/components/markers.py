"""标记组件 - 绘制峰值、突破点、阻力区"""
import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Optional
from ..utils import quality_to_color


class MarkerComponent:
    """标记绘制组件"""

    @staticmethod
    def draw_peaks(ax, df: pd.DataFrame, peaks: list,
                   quality_color_map: bool = True):
        """
        绘制峰值标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame (必须有 DatetimeIndex)
            peaks: Peak 对象列表
            quality_color_map: 是否根据质量分数映射颜色
        """
        if not peaks:
            return

        for peak in peaks:
            # 使用整数索引而不是日期对象
            peak_x = peak.index  # 整数索引
            peak_price = peak.price

            # 确定颜色
            if quality_color_map and peak.quality_score is not None:
                color = quality_to_color(peak.quality_score)
            else:
                color = '#D32F2F'  # 默认红色

            # 绘制峰值标记（向上三角形）
            ax.scatter(
                peak_x,
                peak_price,
                marker='^',
                s=100,
                color=color,
                edgecolors='white',
                linewidths=1.5,
                zorder=5,
                alpha=0.9,
                label='Peak' if peak == peaks[0] else None
            )

            # 添加质量分数标注（可选）
            if quality_color_map and peak.quality_score is not None:
                ax.text(
                    peak_x,
                    peak_price * 1.01,
                    f'{peak.quality_score:.0f}',
                    fontsize=7,
                    ha='center',
                    va='bottom',
                    color=color,
                    weight='bold'
                )

    @staticmethod
    def draw_breakthroughs(ax, df: pd.DataFrame, breakthroughs: list,
                          highlight_multi_peak: bool = True):
        """
        绘制突破标记

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            breakthroughs: Breakthrough 对象列表
            highlight_multi_peak: 多峰值突破是否使用大标记
        """
        if not breakthroughs:
            return

        for bt in breakthroughs:
            # 使用整数索引而不是日期对象
            bt_x = bt.index  # 整数索引
            bt_price = bt.price

            # 确定标记大小（多峰值突破更大）
            is_multi_peak = bt.num_peaks_broken > 1
            marker_size = 300 if (highlight_multi_peak and is_multi_peak) else 150

            # 确定颜色
            if bt.quality_score is not None:
                color = quality_to_color(bt.quality_score)
            else:
                color = '#FFD700'  # 默认金色

            # 绘制突破标记（星形）
            ax.scatter(
                bt_x,
                bt_price,
                marker='*',
                s=marker_size,
                color=color,
                edgecolors='white',
                linewidths=2,
                zorder=10,
                alpha=1.0,
                label='Breakthrough' if bt == breakthroughs[0] else None
            )

            # 多峰值突破添加数字标注
            if is_multi_peak:
                ax.text(
                    bt_x,
                    bt_price * 1.02,
                    f'{bt.num_peaks_broken}',
                    fontsize=9,
                    ha='center',
                    va='bottom',
                    color='black',
                    weight='bold',
                    bbox=dict(
                        boxstyle='circle,pad=0.3',
                        facecolor='white',
                        edgecolor=color,
                        linewidth=2
                    )
                )

    @staticmethod
    def draw_resistance_zones(ax, df: pd.DataFrame, breakthroughs: list,
                            alpha: float = 0.2):
        """
        绘制阻力区高亮（半透明矩形）

        Args:
            ax: matplotlib Axes 对象
            df: OHLCV DataFrame
            breakthroughs: Breakthrough 对象列表
            alpha: 透明度
        """
        if not breakthroughs:
            return

        for bt in breakthroughs:
            # 只高亮多峰值突破的阻力区
            if bt.num_peaks_broken <= 1:
                continue

            # 计算阻力区范围
            prices = [p.price for p in bt.broken_peaks]
            zone_bottom = min(prices)
            zone_top = max(prices)

            # 找到最早的峰值索引（整数）
            earliest_peak_index = min(p.index for p in bt.broken_peaks)

            # 突破索引（整数）
            bt_x = bt.index

            # 计算相对位置（归一化到 0-1）
            xmin = earliest_peak_index / (len(df) - 1) if len(df) > 1 else 0
            xmax = bt_x / (len(df) - 1) if len(df) > 1 else 1

            # 绘制矩形
            ax.axhspan(
                zone_bottom,
                zone_top,
                xmin=xmin,
                xmax=xmax,
                color='#FFEB3B',  # 黄色
                alpha=alpha,
                zorder=1
            )

    @staticmethod
    def draw_price_line(ax, df: pd.DataFrame, price: float,
                       label: str, color: str = 'red',
                       linestyle: str = '--'):
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
            zorder=2
        )
