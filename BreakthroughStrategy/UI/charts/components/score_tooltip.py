"""
评分详情浮动窗口组件

提供峰值和突破点的评分详情展示，包括：
- 各特征的原始数值、分数、权重
- 阻力强度的子因素展开
- 完整的计算公式
- 支持复合情况（峰值+突破同一K线）
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple, List

from ....analysis.quality_scorer import (
    ScoreBreakdown,
    FeatureScoreDetail,
    BonusDetail,
    QualityScorer
)
from ....analysis.breakthrough_detector import Peak, Breakthrough
from ...styles import SCORE_TOOLTIP_COLORS, SCORE_TOOLTIP_FONTS


class ScoreDetailWindow:
    """
    评分详情浮动窗口

    通过快捷键触发显示，展示峰值或突破点的评分详情。
    窗口可拖拽、可关闭，支持同时打开多个窗口对比。
    """

    # 使用集中的样式配置
    COLORS = SCORE_TOOLTIP_COLORS
    FONTS = SCORE_TOOLTIP_FONTS

    def __init__(
        self,
        parent: tk.Widget,
        peak: Optional[Peak],
        breakthrough: Optional[Breakthrough],
        scorer: QualityScorer,
        position: Tuple[int, int],
        symbol: str = ""
    ):
        """
        创建评分详情窗口

        Args:
            parent: 父窗口
            peak: 峰值对象（可选）
            breakthrough: 突破对象（可选）
            scorer: 质量评分器实例
            position: 窗口位置 (x, y)
            symbol: 股票代码
        """
        self.parent = parent
        self.peak = peak
        self.breakthrough = breakthrough
        self.scorer = scorer
        self.position = position
        self.symbol = symbol

        # 创建窗口
        self.window = tk.Toplevel(parent)
        self._setup_window()
        self._build_content()
        self._position_window()

        # 绑定事件
        self._bind_events()

    def _setup_window(self):
        """设置窗口属性"""
        # 标题中加入股票代码
        title = f"Score Details - {self.symbol}" if self.symbol else "Score Details"
        self.window.title(title)
        self.window.resizable(False, False)
        self.window.configure(bg=self.COLORS["window_bg"])

        # 设置窗口始终在最上层（但允许操作其他窗口）
        self.window.attributes("-topmost", True)

        # 窗口关闭协议
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _build_content(self):
        """构建窗口内容"""
        main_frame = tk.Frame(
            self.window,
            bg=self.COLORS["window_bg"],
            padx=2,
            pady=2
        )
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 判断显示模式
        has_peak = self.peak is not None
        has_bt = self.breakthrough is not None

        if has_peak and has_bt:
            # 复合模式：垂直堆叠
            self._build_combined_view(main_frame)
        elif has_peak:
            # 仅峰值
            self._build_peak_view(main_frame)
        elif has_bt:
            # 仅突破
            self._build_breakthrough_view(main_frame)

    def _build_combined_view(self, parent: tk.Frame):
        """构建复合视图（峰值 + 突破）"""
        # 峰值部分
        peak_frame = tk.Frame(parent, bg=self.COLORS["window_bg"])
        peak_frame.pack(fill=tk.X, padx=4, pady=(4, 2))
        self._build_peak_card(peak_frame)

        # 分隔线
        separator = tk.Frame(
            parent,
            bg=self.COLORS["separator"],
            height=2
        )
        separator.pack(fill=tk.X, padx=8, pady=4)

        # 突破部分
        bt_frame = tk.Frame(parent, bg=self.COLORS["window_bg"])
        bt_frame.pack(fill=tk.X, padx=4, pady=(2, 4))
        self._build_breakthrough_card(bt_frame)

    def _build_peak_view(self, parent: tk.Frame):
        """构建峰值视图"""
        frame = tk.Frame(parent, bg=self.COLORS["window_bg"])
        frame.pack(fill=tk.X, padx=4, pady=4)
        self._build_peak_card(frame)

    def _build_breakthrough_view(self, parent: tk.Frame):
        """构建突破视图"""
        frame = tk.Frame(parent, bg=self.COLORS["window_bg"])
        frame.pack(fill=tk.X, padx=4, pady=4)
        self._build_breakthrough_card(frame)

    def _build_peak_card(self, parent: tk.Frame):
        """构建峰值卡片"""
        breakdown = self.scorer.get_peak_score_breakdown(self.peak)

        # 标题栏
        header = tk.Frame(parent, bg=self.COLORS["peak_header_bg"])
        header.pack(fill=tk.X)

        # 左侧标题
        peak_id_text = f"Peak #{self.peak.id}" if self.peak.id else "Peak"
        title_label = tk.Label(
            header,
            text=peak_id_text,
            font=self.FONTS["header"],
            bg=self.COLORS["peak_header_bg"],
            fg=self.COLORS["peak_header_fg"],
            padx=10,
            pady=6
        )
        title_label.pack(side=tk.LEFT)

        # 右侧总分（统一使用金色，在深色背景上醒目）
        score_label = tk.Label(
            header,
            text=f"Score: {breakdown.total_score:.1f}",
            font=self.FONTS["header"],
            bg=self.COLORS["peak_header_bg"],
            fg=self.COLORS["score_medium_light"],
            padx=10,
            pady=6
        )
        score_label.pack(side=tk.RIGHT)

        # 内容区
        content = tk.Frame(
            parent,
            bg=self.COLORS["window_bg"],
            highlightbackground=self.COLORS["peak_border"],
            highlightthickness=1
        )
        content.pack(fill=tk.X)

        # 表格
        self._build_score_table(content, breakdown.features)

        # 公式区域
        self._build_formula_area(content, breakdown)

    def _build_breakthrough_card(self, parent: tk.Frame):
        """构建突破卡片"""
        breakdown = self.scorer.get_breakthrough_score_breakdown_bonus(self.breakthrough)

        # 标题栏
        header = tk.Frame(parent, bg=self.COLORS["bt_header_bg"])
        header.pack(fill=tk.X)

        # 左侧标题
        title_label = tk.Label(
            header,
            text="Breakthrough",
            font=self.FONTS["header"],
            bg=self.COLORS["bt_header_bg"],
            fg=self.COLORS["bt_header_fg"],
            padx=10,
            pady=6
        )
        title_label.pack(side=tk.LEFT)

        # 右侧总分（统一使用金色，在深色背景上醒目）
        score_label = tk.Label(
            header,
            text=f"Score: {breakdown.total_score:.1f}",
            font=self.FONTS["header"],
            bg=self.COLORS["bt_header_bg"],
            fg=self.COLORS["score_medium_light"],
            padx=10,
            pady=6
        )
        score_label.pack(side=tk.RIGHT)

        # 被突破峰值信息
        if breakdown.broken_peak_ids:
            peaks_text = f"Broken Peaks: [{', '.join(str(p) for p in breakdown.broken_peak_ids)}]"
            peaks_label = tk.Label(
                header,
                text=peaks_text,
                font=self.FONTS["header_small"],
                bg=self.COLORS["bt_header_bg"],
                fg=self.COLORS["bt_header_fg"],
                padx=10
            )
            peaks_label.pack(side=tk.LEFT)

        # 内容区
        content = tk.Frame(
            parent,
            bg=self.COLORS["window_bg"],
            highlightbackground=self.COLORS["bt_border"],
            highlightthickness=1
        )
        content.pack(fill=tk.X)

        # Bonus 表格
        self._build_bonus_table(content, breakdown.bonuses)

        # 公式区域
        self._build_formula_area(content, breakdown)

    def _build_score_table(
        self,
        parent: tk.Frame,
        features: List[FeatureScoreDetail],
        expand_resistance: bool = False
    ):
        """
        构建评分表格

        Args:
            parent: 父容器
            features: 特征列表
            expand_resistance: 是否展开阻力强度子因素
        """
        table = tk.Frame(parent, bg=self.COLORS["window_bg"])
        table.pack(fill=tk.X, padx=8, pady=8)

        # 表头
        headers = ["Factor", "Value", "Score", "Weight"]
        widths = [14, 8, 6, 7]

        for col, (text, width) in enumerate(zip(headers, widths)):
            lbl = tk.Label(
                table,
                text=text,
                font=self.FONTS["table_header"],
                bg=self.COLORS["separator"],
                width=width,
                anchor=tk.CENTER,
                padx=4,
                pady=4
            )
            lbl.grid(row=0, column=col, sticky="ew", padx=1, pady=1)

        # 数据行
        row_idx = 1
        for feature in features:
            bg_color = self.COLORS["row_bg"] if row_idx % 2 == 1 else self.COLORS["row_alt_bg"]

            # 特征名
            tk.Label(
                table,
                text=feature.name,
                font=self.FONTS["table_cell"],
                bg=bg_color,
                anchor=tk.W,
                padx=6,
                pady=3
            ).grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)

            # 原始值
            value_text = self._format_value(feature.raw_value, feature.unit)
            tk.Label(
                table,
                text=value_text,
                font=self.FONTS["table_cell"],
                bg=bg_color,
                anchor=tk.CENTER,
                padx=4,
                pady=3
            ).grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)

            # 分数
            score_color = self._get_score_color(feature.score)
            tk.Label(
                table,
                text=f"{feature.score:.0f}",
                font=self.FONTS["table_cell"],
                bg=bg_color,
                fg=score_color,
                anchor=tk.CENTER,
                padx=4,
                pady=3
            ).grid(row=row_idx, column=2, sticky="ew", padx=1, pady=1)

            # 权重
            tk.Label(
                table,
                text=f"{feature.weight*100:.0f}%",
                font=self.FONTS["table_cell"],
                bg=bg_color,
                fg=self.COLORS["text_secondary"],
                anchor=tk.CENTER,
                padx=4,
                pady=3
            ).grid(row=row_idx, column=3, sticky="ew", padx=1, pady=1)

            row_idx += 1

            # 展开阻力强度子因素
            if expand_resistance and feature.sub_features:
                for sub in feature.sub_features:
                    sub_bg = self.COLORS["sub_feature_bg"]

                    # 子特征名（缩进）
                    tk.Label(
                        table,
                        text=f"  - {sub.name}",
                        font=self.FONTS["sub_feature"],
                        bg=sub_bg,
                        fg=self.COLORS["text_secondary"],
                        anchor=tk.W,
                        padx=6,
                        pady=2
                    ).grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)

                    # 子特征值
                    sub_value_text = self._format_value(sub.raw_value, sub.unit)
                    tk.Label(
                        table,
                        text=sub_value_text,
                        font=self.FONTS["sub_feature"],
                        bg=sub_bg,
                        fg=self.COLORS["text_secondary"],
                        anchor=tk.CENTER,
                        padx=4,
                        pady=2
                    ).grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)

                    # 子特征分数
                    tk.Label(
                        table,
                        text=f"{sub.score:.0f}",
                        font=self.FONTS["sub_feature"],
                        bg=sub_bg,
                        fg=self.COLORS["text_secondary"],
                        anchor=tk.CENTER,
                        padx=4,
                        pady=2
                    ).grid(row=row_idx, column=2, sticky="ew", padx=1, pady=1)

                    # 子特征权重（显示在括号中）
                    tk.Label(
                        table,
                        text=f"({sub.weight*100:.0f}%)",
                        font=self.FONTS["sub_feature"],
                        bg=sub_bg,
                        fg=self.COLORS["text_secondary"],
                        anchor=tk.CENTER,
                        padx=4,
                        pady=2
                    ).grid(row=row_idx, column=3, sticky="ew", padx=1, pady=1)

                    row_idx += 1

        # 配置列权重
        for col in range(4):
            table.columnconfigure(col, weight=1)

    def _build_bonus_table(
        self,
        parent: tk.Frame,
        bonuses: List[BonusDetail]
    ):
        """
        构建 Bonus 评分表格

        Args:
            parent: 父容器
            bonuses: Bonus 列表
        """
        table = tk.Frame(parent, bg=self.COLORS["window_bg"])
        table.pack(fill=tk.X, padx=8, pady=8)

        # 表头
        headers = ["Factor", "Value", "Bonus"]
        widths = [12, 8, 8]

        for col, (text, width) in enumerate(zip(headers, widths)):
            lbl = tk.Label(
                table,
                text=text,
                font=self.FONTS["table_header"],
                bg=self.COLORS["separator"],
                width=width,
                anchor=tk.CENTER,
                padx=4,
                pady=4
            )
            lbl.grid(row=0, column=col, sticky="ew", padx=1, pady=1)

        # 数据行
        row_idx = 1
        for bonus in bonuses:
            bg_color = self.COLORS["row_bg"] if row_idx % 2 == 1 else self.COLORS["row_alt_bg"]

            # 根据触发状态选择颜色
            if bonus.triggered:
                bonus_color = self.COLORS.get("bonus_triggered", "#2E7D32")
            else:
                bonus_color = self.COLORS.get("bonus_not_triggered", "#9E9E9E")

            # Factor 名称
            tk.Label(
                table,
                text=bonus.name,
                font=self.FONTS["table_cell"],
                bg=bg_color,
                fg=bonus_color,
                anchor=tk.W,
                padx=6,
                pady=3
            ).grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)

            # 原始值
            value_text = self._format_value(bonus.raw_value, bonus.unit)
            tk.Label(
                table,
                text=value_text,
                font=self.FONTS["table_cell"],
                bg=bg_color,
                fg=bonus_color,
                anchor=tk.CENTER,
                padx=4,
                pady=3
            ).grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)

            # Bonus 乘数
            bonus_text = f"×{bonus.bonus:.2f}"
            tk.Label(
                table,
                text=bonus_text,
                font=self.FONTS["table_cell"],
                bg=bg_color,
                fg=bonus_color,
                anchor=tk.CENTER,
                padx=4,
                pady=3
            ).grid(row=row_idx, column=2, sticky="ew", padx=1, pady=1)

            row_idx += 1

        # 配置列权重
        for col in range(3):
            table.columnconfigure(col, weight=1)

    def _build_formula_area(self, parent: tk.Frame, breakdown: ScoreBreakdown):
        """构建公式显示区域"""
        formula_frame = tk.Frame(
            parent,
            bg=self.COLORS["formula_bg"],
            padx=8,
            pady=6
        )
        formula_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        # 公式标签
        tk.Label(
            formula_frame,
            text="Formula:",
            font=self.FONTS["formula"],
            bg=self.COLORS["formula_bg"],
            fg=self.COLORS["text_secondary"],
            anchor=tk.W
        ).pack(anchor=tk.W)

        # 公式内容
        formula_text = breakdown.get_formula_string()
        tk.Label(
            formula_frame,
            text=formula_text,
            font=self.FONTS["formula"],
            bg=self.COLORS["formula_bg"],
            fg=self.COLORS["text_primary"],
            anchor=tk.W
        ).pack(anchor=tk.W)

    def _format_value(self, value: float, unit: str) -> str:
        """格式化数值显示"""
        if unit == "x":
            return f"{value:.1f}x"
        elif unit == "%":
            return f"{value:.1f}%"
        elif unit == "d":
            return f"{int(value)}d"
        elif unit == "pks":
            return f"{int(value)} pks"
        else:
            return f"{value:.1f}"

    def _get_score_color(self, score: float, for_dark_bg: bool = False) -> str:
        """
        根据分数返回颜色

        Args:
            score: 分数值
            for_dark_bg: 是否用于深色背景（标题栏）

        Returns:
            颜色代码
        """
        suffix = "_light" if for_dark_bg else ""
        if score >= 80:
            return self.COLORS[f"score_high{suffix}"]
        elif score >= 50:
            return self.COLORS[f"score_medium{suffix}"]
        else:
            return self.COLORS[f"score_low{suffix}"]

    def _position_window(self):
        """定位窗口"""
        x, y = self.position

        # 更新窗口以获取实际尺寸
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()

        # 获取屏幕尺寸
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        # 智能定位：避免超出屏幕边界
        # 优先右上方
        final_x = x + 20
        final_y = y - height - 20

        # 检查右边界
        if final_x + width > screen_width:
            final_x = x - width - 20

        # 检查上边界
        if final_y < 0:
            final_y = y + 20

        # 检查下边界
        if final_y + height > screen_height:
            final_y = screen_height - height - 10

        # 确保不会超出左边界
        if final_x < 0:
            final_x = 10

        self.window.geometry(f"+{final_x}+{final_y}")

    def _bind_events(self):
        """绑定事件"""
        # ESC 键关闭窗口
        self.window.bind("<Escape>", lambda e: self.close())

        # 窗口获得焦点时确保可以接收键盘事件
        self.window.focus_set()

    def close(self):
        """关闭窗口"""
        if self.window:
            self.window.destroy()
            self.window = None

    def is_open(self) -> bool:
        """检查窗口是否打开"""
        return self.window is not None and self.window.winfo_exists()
