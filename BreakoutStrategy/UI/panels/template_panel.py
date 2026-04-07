"""模板列表面板 — 在左侧面板上部显示可选的组合模板"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class TemplatePanel:
    """模板列表面板（左侧面板上部）

    显示 filter.yaml 中的模板列表，支持单选。
    列: # | Med | N | R（序号列，模板名通过悬浮提示显示）
    按 median 降序排列。
    """

    def __init__(
        self,
        parent,
        on_template_selected_callback: Optional[Callable] = None,
    ):
        """
        Args:
            parent: 父容器
            on_template_selected_callback: 选中模板时的回调，参数为 template_name: str
        """
        self.parent = parent
        self.on_template_selected_callback = on_template_selected_callback
        self._templates = []  # 模板显示数据列表
        self._selected_name = None  # 当前选中的模板名称
        self._tooltip_window = None  # 行级 tooltip 窗口
        self._tooltip_row = None  # 当前 tooltip 对应的行 iid

        self._create_ui()

    def _create_ui(self):
        """创建 UI 组件"""
        self.frame = ttk.LabelFrame(self.parent, text="Templates")

        # Treeview: 单选模式，序号 | Med | N | R
        columns = ("no", "med", "n", "r")
        self.tree = ttk.Treeview(
            self.frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=10,
        )

        self.tree.heading("no", text="#")
        self.tree.heading("med", text="Med")
        self.tree.heading("n", text="N")
        self.tree.heading("r", text="R")

        self.tree.column("no", width=35, anchor=tk.CENTER, stretch=False)
        self.tree.column("med", width=60, anchor=tk.CENTER, stretch=False)
        self.tree.column("n", width=50, anchor=tk.CENTER, stretch=False)
        self.tree.column("r", width=55, anchor=tk.CENTER, stretch=False)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 绑定选择事件
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 绑定行级 tooltip 事件
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._hide_tooltip)

    def load_templates(self, template_display_list: list[dict]):
        """加载模板数据到列表。

        Args:
            template_display_list: TemplateManager.get_template_display_list() 的输出
        """
        self._templates = template_display_list

        # 清空
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 插入数据（已按 median 降序），第一列为序号
        for idx, tmpl in enumerate(template_display_list, start=1):
            self.tree.insert(
                "", tk.END,
                iid=tmpl["name"],
                values=(
                    idx,
                    f"{tmpl['median']:.2f}",
                    str(tmpl["count"]),
                    f"{tmpl['ratio']:.1f}%",
                ),
            )

        # 默认选中第一行
        if template_display_list:
            first_name = template_display_list[0]["name"]
            self.tree.selection_set(first_name)
            self._selected_name = first_name

    def _on_select(self, event=None):
        """Treeview 选择事件"""
        selection = self.tree.selection()
        if not selection:
            return

        name = selection[0]
        if name == self._selected_name:
            return  # 防止重复触发

        self._selected_name = name
        if self.on_template_selected_callback:
            self.on_template_selected_callback(name)

    def _on_motion(self, event):
        """鼠标移动时显示行级 tooltip（模板名称）"""
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            self._hide_tooltip()
            return

        if row_id == self._tooltip_row:
            # 同一行，更新位置即可
            if self._tooltip_window:
                x = event.x_root + 15
                y = event.y_root + 10
                self._tooltip_window.wm_geometry(f"+{x}+{y}")
            return

        # 切换到新行
        self._hide_tooltip()
        self._tooltip_row = row_id

        self._tooltip_window = tk.Toplevel(self.tree)
        self._tooltip_window.wm_overrideredirect(True)
        x = event.x_root + 15
        y = event.y_root + 10
        self._tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self._tooltip_window,
            text=row_id,  # iid 即模板名
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Arial", 12),
        )
        label.pack()

    def _hide_tooltip(self, event=None):
        """隐藏行级 tooltip"""
        if self._tooltip_window:
            self._tooltip_window.destroy()
            self._tooltip_window = None
        self._tooltip_row = None

    def get_selected_template_name(self) -> str | None:
        """返回当前选中的模板名称"""
        return self._selected_name

    def show(self):
        """显示面板"""
        if not self.is_visible():
            self.frame.pack(fill=tk.X, padx=2, pady=(2, 0), before=self._find_stock_list())

    def hide(self):
        """隐藏面板"""
        self.frame.pack_forget()

    def _find_stock_list(self):
        """找到同级的 stock list widget，用于 pack 定位（跳过自身）"""
        for child in self.parent.winfo_children():
            if child is not self.frame:
                return child
        return None

    def is_visible(self) -> bool:
        """面板是否可见"""
        return self.frame.winfo_manager() != ""
