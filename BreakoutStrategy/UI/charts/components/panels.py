"""信息面板组件 - 展示统计信息"""
import matplotlib.pyplot as plt
from typing import List


class PanelComponent:
    """信息面板组件"""

    @staticmethod
    def draw_statistics_panel(ax, breakouts: list):
        """
        绘制统计信息面板

        Args:
            ax: matplotlib Axes 对象
            breakouts: Breakout 对象列表
        """
        ax.axis('off')  # 隐藏坐标轴

        if not breakouts:
            ax.text(
                0.5, 0.5,
                'No breakouts detected',
                ha='center',
                va='center',
                fontsize=28,
                color='gray'
            )
            return

        # 计算统计数据
        total_count = len(breakouts)
        multi_peak_count = sum(1 for bo in breakouts if bo.num_peaks_broken > 1)

        # 平均质量分数
        quality_scores = [bo.quality_score for bo in breakouts if bo.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Top 5 平均分
        top5_scores = sorted(quality_scores, reverse=True)[:5]
        top5_avg = sum(top5_scores) / len(top5_scores) if top5_scores else 0

        # 多峰值突破的详细信息
        multi_peak_details = [
            (bo.date.strftime('%Y-%m-%d'), bo.num_peaks_broken, bo.quality_score or 0)
            for bo in breakouts
            if bo.num_peaks_broken > 1
        ]
        multi_peak_details = sorted(multi_peak_details, key=lambda x: x[1], reverse=True)[:5]

        # 构建信息文本（简化版，减少文字重叠）
        info_text = (
            f"Total: {total_count} | "
            f"Multi-Peak: {multi_peak_count} ({multi_peak_count/total_count*100:.1f}%) | "
            f"Avg Q: {avg_quality:.1f} | "
            f"Top-5 Avg: {top5_avg:.1f}"
        )

        # 添加多峰值突破详情（单行）
        if multi_peak_details:
            details_str = " | Top Multi-Peak: "
            details_parts = []
            for date, num_peaks, quality in multi_peak_details[:3]:  # 只显示前3个
                details_parts.append(f"{date}: {num_peaks}peaks (Q={quality:.0f})")
            info_text += details_str + ", ".join(details_parts)

        # 绘制单行文本
        ax.text(
            0.02, 0.5,
            info_text,
            fontsize=17,
            va='center',
            ha='left',
            family='monospace'
        )

    @staticmethod
    def draw_breakout_detail_panel(ax, breakout):
        """
        绘制单个突破的详细信息面板（简化版）

        Args:
            ax: matplotlib Axes 对象
            breakout: Breakout 对象
        """
        ax.axis('off')

        # 构建简化的详细信息（两行）
        line1 = (
            f"Date: {breakout.date.strftime('%Y-%m-%d')} | "
            f"Price: ${breakout.price:.2f} | "
            f"Type: {breakout.breakout_type.upper()} | "
            f"Peaks Broken: {breakout.num_peaks_broken}"
        )

        quality_str = f"{breakout.quality_score:.1f}" if breakout.quality_score else "N/A"
        line2 = (
            f"Quality Score: {quality_str} | "
            f"Price Change: {breakout.price_change_pct*100:.2f}% | "
            f"Volume Surge: {breakout.volume_surge_ratio:.2f}x | "
            f"Gap Up: {'Yes' if breakout.gap_up else 'No'} | "
            f"Continuity Days: {breakout.continuity_days} | "
            f"Stability: {breakout.stability_score:.1f}"
        )

        # 峰值详情（单行）
        line3 = ""
        if breakout.broken_peaks:
            peaks_str = "Broken Peaks: "
            peak_parts = []
            for i, peak in enumerate(breakout.broken_peaks[:5], 1):
                id_str = f"#{peak.id}" if peak.id is not None else ""
                peak_parts.append(f"${peak.price:.2f}{id_str}")
            line3 = peaks_str + ", ".join(peak_parts)

        # 绘制三行文本
        ax.text(0.02, 0.7, line1, fontsize=14, va='center', ha='left', family='monospace')
        ax.text(0.02, 0.5, line2, fontsize=14, va='center', ha='left', family='monospace')
        if line3:
            ax.text(0.02, 0.3, line3, fontsize=14, va='center', ha='left', family='monospace')
