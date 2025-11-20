"""信息面板组件 - 展示统计信息"""
import matplotlib.pyplot as plt
from typing import List


class PanelComponent:
    """信息面板组件"""

    @staticmethod
    def draw_statistics_panel(ax, breakthroughs: list):
        """
        绘制统计信息面板

        Args:
            ax: matplotlib Axes 对象
            breakthroughs: Breakthrough 对象列表
        """
        ax.axis('off')  # 隐藏坐标轴

        if not breakthroughs:
            ax.text(
                0.5, 0.5,
                'No breakthroughs detected',
                ha='center',
                va='center',
                fontsize=28,
                color='gray'
            )
            return

        # 计算统计数据
        total_count = len(breakthroughs)
        multi_peak_count = sum(1 for bt in breakthroughs if bt.num_peaks_broken > 1)

        # 平均质量分数
        quality_scores = [bt.quality_score for bt in breakthroughs if bt.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Top 5 平均分
        top5_scores = sorted(quality_scores, reverse=True)[:5]
        top5_avg = sum(top5_scores) / len(top5_scores) if top5_scores else 0

        # 多峰值突破的详细信息
        multi_peak_details = [
            (bt.date.strftime('%Y-%m-%d'), bt.num_peaks_broken, bt.quality_score or 0)
            for bt in breakthroughs
            if bt.num_peaks_broken > 1
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
            fontsize=14,
            va='center',
            ha='left',
            family='monospace'
        )

    @staticmethod
    def draw_breakthrough_detail_panel(ax, breakthrough):
        """
        绘制单个突破的详细信息面板（简化版）

        Args:
            ax: matplotlib Axes 对象
            breakthrough: Breakthrough 对象
        """
        ax.axis('off')

        # 构建简化的详细信息（两行）
        line1 = (
            f"Date: {breakthrough.date.strftime('%Y-%m-%d')} | "
            f"Price: ${breakthrough.price:.2f} | "
            f"Type: {breakthrough.breakthrough_type.upper()} | "
            f"Peaks Broken: {breakthrough.num_peaks_broken}"
        )

        quality_str = f"{breakthrough.quality_score:.1f}" if breakthrough.quality_score else "N/A"
        line2 = (
            f"Quality Score: {quality_str} | "
            f"Price Change: {breakthrough.price_change_pct*100:.2f}% | "
            f"Volume Surge: {breakthrough.volume_surge_ratio:.2f}x | "
            f"Gap Up: {'Yes' if breakthrough.gap_up else 'No'} | "
            f"Continuity Days: {breakthrough.continuity_days} | "
            f"Stability: {breakthrough.stability_score:.1f}"
        )

        # 峰值详情（单行）
        line3 = ""
        if breakthrough.broken_peaks:
            peaks_str = "Broken Peaks: "
            peak_parts = []
            for i, peak in enumerate(breakthrough.broken_peaks[:5], 1):
                quality_str = f"Q={peak.quality_score:.0f}" if peak.quality_score else "Q=N/A"
                peak_parts.append(f"${peak.price:.2f}({quality_str})")
            line3 = peaks_str + ", ".join(peak_parts)

        # 绘制三行文本
        ax.text(0.02, 0.7, line1, fontsize=14, va='center', ha='left', family='monospace')
        ax.text(0.02, 0.5, line2, fontsize=14, va='center', ha='left', family='monospace')
        if line3:
            ax.text(0.02, 0.3, line3, fontsize=14, va='center', ha='left', family='monospace')
