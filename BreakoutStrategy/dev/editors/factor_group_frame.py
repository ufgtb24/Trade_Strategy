"""FactorGroupFrame — 带 tooltip 的因子分组容器

替代 ttk.LabelFrame 用于 Parameter Editor 中的因子组渲染。
与 LabelFrame 的差异：标题作为顶部独立 Label 行（而非嵌入边框线），
从而可以绑定鼠标 hover 事件，弹出因子说明 tooltip。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from BreakoutStrategy.UI.styles import FONT_SECTION_TITLE
from .input_factory import ToolTip


class FactorGroupFrame(ttk.Frame):
    """因子组容器：边框 Frame + 顶部标题 Label（带 tooltip）+ 子参数区。

    继承自 ttk.Frame，调用方将其作为 parent 直接 pack 子组件即可，
    标题始终保持在顶部（先 pack 之故）。
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        tooltip_text: Optional[str] = None,
    ):
        """
        Args:
            parent: 父容器
            title: 顶部显示的标题文字（如 'age_factor'）
            tooltip_text: hover 标题时弹出的说明；None / '' 表示不绑 tooltip
        """
        super().__init__(parent, relief='solid', borderwidth=1, padding=10)

        # 顶部标题 Label
        self.title_label = ttk.Label(
            self, text=title, font=FONT_SECTION_TITLE
        )
        self.title_label.pack(side='top', anchor='w', pady=(0, 5))

        # 绑 tooltip（仅当文本非空）
        # wraplength=600：因子描述含两段中文，宽 tooltip 比窄高更易读
        if tooltip_text:
            self.title_label._tooltip = ToolTip(
                self.title_label, tooltip_text, wraplength=1600
            )
        else:
            self.title_label._tooltip = None
