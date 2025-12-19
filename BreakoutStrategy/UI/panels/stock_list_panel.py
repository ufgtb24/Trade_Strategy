"""股票列表面板"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional, Any

# 临时行常量
TEMP_ROW_PREFIX = "__temp_"
TEMP_ROW_TAG = "temp_stats"


class HeaderTooltip:
    """列标题 Tooltip 管理器"""

    def __init__(self, treeview: ttk.Treeview, column_config: Dict[str, Any]):
        """
        初始化 Tooltip 管理器

        Args:
            treeview: 关联的 Treeview 组件
            column_config: 列配置字典，包含 tooltip 信息
        """
        self.treeview = treeview
        self.column_config = column_config
        self.tooltip_window = None
        self.current_column = None
        self._after_id = None
        self._delay_ms = 500  # 显示延迟

        # 绑定事件
        self.treeview.bind("<Motion>", self._on_motion)
        self.treeview.bind("<Leave>", self._on_leave)

    def update_config(self, column_config: Dict[str, Any]):
        """更新列配置"""
        self.column_config = column_config

    def _on_motion(self, event):
        """鼠标移动事件"""
        # 检查是否在表头区域
        region = self.treeview.identify_region(event.x, event.y)
        if region != "heading":
            self._hide_tooltip()
            return

        # 获取当前列
        col_id = self.treeview.identify_column(event.x)
        if not col_id or col_id == "#0":
            self._hide_tooltip()
            return

        try:
            col_index = int(col_id.replace("#", "")) - 1
            columns = self.treeview["columns"]
            if 0 <= col_index < len(columns):
                column = columns[col_index]
            else:
                self._hide_tooltip()
                return
        except (ValueError, IndexError):
            self._hide_tooltip()
            return

        # 如果是同一列，不重复处理
        if column == self.current_column:
            return

        # 取消之前的延迟显示
        if self._after_id:
            self.treeview.after_cancel(self._after_id)
            self._after_id = None

        self._hide_tooltip()
        self.current_column = column

        # 延迟显示 tooltip
        self._after_id = self.treeview.after(
            self._delay_ms, lambda: self._show_tooltip(event, column)
        )

    def _on_leave(self, event):
        """鼠标离开事件"""
        if self._after_id:
            self.treeview.after_cancel(self._after_id)
            self._after_id = None
        self._hide_tooltip()

    def _show_tooltip(self, event, column: str):
        """显示 tooltip"""
        # 获取 tooltip 文本（tooltip 已包含完整名称和描述）
        col_info = self.column_config.get(column, {})
        if isinstance(col_info, dict):
            tooltip_text = col_info.get("tooltip", "")
        else:
            tooltip_text = ""

        if not tooltip_text:
            return

        # 创建 tooltip 窗口
        self.tooltip_window = tk.Toplevel(self.treeview)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_attributes("-topmost", True)

        frame = ttk.Frame(self.tooltip_window, relief="solid", borderwidth=1)
        frame.pack()

        label = ttk.Label(
            frame,
            text=tooltip_text,
            justify=tk.LEFT,
            padding=(5, 3),
        )
        label.pack()

        # 定位：在鼠标下方
        x = self.treeview.winfo_rootx() + event.x + 10
        y = self.treeview.winfo_rooty() + event.y + 20
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

    def _hide_tooltip(self):
        """隐藏 tooltip"""
        self.current_column = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class StockListPanel:
    """股票列表面板"""

    def __init__(
        self,
        parent,
        on_selection_callback: Optional[Callable] = None,
        on_width_changed_callback: Optional[Callable] = None,
    ):
        """
        初始化股票列表面板

        Args:
            parent: 父容器
            on_selection_callback: 选择回调函数
            on_width_changed_callback: 宽度变化回调函数
        """
        self.parent = parent
        self.on_selection_callback = on_selection_callback
        self.on_width_changed_callback = on_width_changed_callback
        self.stock_data = []  # 原始数据
        self.filtered_data = []  # 筛选后的数据
        self._selection_in_progress = False  # 防止递归触发（同步期间）
        self._last_selected_symbol = None  # 记录上次选择的股票，防止重复处理

        # 列拖拽状态
        self._drag_data = {"column": None, "start_x": 0, "dragging": False}
        self._drag_indicator = None  # 拖拽指示器窗口
        self._drag_threshold = 10  # 拖拽阈值（像素），超过才开始拖拽

        # 列配置（从配置文件加载）
        self._column_labels = {}  # 列标签配置
        self._header_tooltip = None  # Tooltip 管理器

        # 创建UI
        self._create_ui()
        self._load_column_config()

    def _create_ui(self):
        """创建UI组件"""
        # 注意：字体样式由 ui_styles.py 的 configure_global_styles() 统一管理
        # 这里只调整行高以适应内容显示
        style = ttk.Style()
        style.configure("Treeview", rowheight=50)

        # 主容器
        container = ttk.Frame(self.parent)
        container.pack(fill=tk.BOTH, expand=True)

        # 工具栏（列配置控件）
        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X, padx=2, pady=(2, 0))

        # 列显示开关（复选框，无标签）
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        column_config = config_loader.get_stock_list_column_config()
        self._columns_enabled_var = tk.BooleanVar(
            value=column_config.get("columns_enabled", True)
        )

        self._toggle_checkbox = ttk.Checkbutton(
            toolbar,
            text="👁",
            variable=self._columns_enabled_var,
            command=self._on_toggle_columns,
            width=3,
        )
        self._toggle_checkbox.pack(side=tk.LEFT)

        # 列配置按钮
        ttk.Button(
            toolbar,
            text="Columns",
            command=self._on_configure_columns,
            width=8,
        ).pack(side=tk.LEFT, padx=(2, 0))

        # 标签类型选择器
        label_frame = ttk.Frame(toolbar)
        label_frame.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(label_frame, text="Label:").pack(side=tk.LEFT)
        self._label_type_var = tk.StringVar(value="avg")
        self._label_type_combo = ttk.Combobox(
            label_frame,
            textvariable=self._label_type_var,
            values=["avg", "max", "best_quality", "latest"],
            width=10,
            state="readonly",
        )
        self._label_type_combo.pack(side=tk.LEFT, padx=(2, 0))
        self._label_type_combo.bind("<<ComboboxSelected>>", self._on_label_type_changed)

        # 列表容器 (包含两个Treeview和滚动条)
        list_frame = ttk.Frame(container)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 垂直滚动条
        self.v_scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self._on_vsb_scroll
        )
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 左侧固定列容器
        fixed_frame = ttk.Frame(list_frame)
        fixed_frame.pack(side=tk.LEFT, fill=tk.Y)

        # 右侧可滚动列容器
        main_frame = ttk.Frame(list_frame)
        main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 水平滚动条 (只控制右侧Treeview)
        self.h_scrollbar = ttk.Scrollbar(main_frame, orient=tk.HORIZONTAL)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        # 1. 左侧固定Treeview (Symbol)
        self.fixed_tree = ttk.Treeview(
            fixed_frame,
            columns=("Symbol",),
            show="headings",
            selectmode="browse",
            height=20,
        )
        self.fixed_tree.heading(
            "Symbol", text="Symbol", command=lambda: self.sort_by("symbol")
        )
        self.fixed_tree.column("Symbol", width=160, anchor=tk.W, stretch=False)
        self.fixed_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 2. 右侧主Treeview (其他属性)
        # 初始不设置列，等待数据加载
        self.main_tree = ttk.Treeview(
            main_frame,
            show="headings",
            selectmode="browse",
            xscrollcommand=self.h_scrollbar.set,
            height=20,
        )
        self.h_scrollbar.config(command=self.main_tree.xview)

        self.main_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 绑定滚动同步
        self.main_tree.config(yscrollcommand=self.v_scrollbar.set)

        # 绑定鼠标滚轮
        self._bind_mouse_wheel(self.fixed_tree)
        self._bind_mouse_wheel(self.main_tree)

        # 绑定选择同步
        self.fixed_tree.bind("<<TreeviewSelect>>", self._on_fixed_select)
        self.main_tree.bind("<<TreeviewSelect>>", self._on_main_select)

        # 绑定右键菜单到 fixed_tree（当所有属性列隐藏时，仍可通过 Symbol 列头弹出菜单）
        self.fixed_tree.bind("<Button-3>", self._show_column_context_menu)

        # 配置临时行样式（黄色背景 + 黑色字）
        self.fixed_tree.tag_configure(
            TEMP_ROW_TAG,
            background="#FFF3CD",
            foreground="#000000"
        )
        self.main_tree.tag_configure(
            TEMP_ROW_TAG,
            background="#FFF3CD",
            foreground="#000000"
        )

        # 临时行状态
        self._current_temp_iid = None
        self._current_temp_stats = None  # (symbol, stats) 元组，用于排序后重建

    def _load_column_config(self):
        """从配置文件加载列标签配置"""
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()

        # 加载列标签配置
        self._column_labels = config.get("column_labels", {})

        # 初始化 main_tree 的 Tooltip 管理器
        if self._header_tooltip is None:
            self._header_tooltip = HeaderTooltip(self.main_tree, self._column_labels)
        else:
            self._header_tooltip.update_config(column_config=self._column_labels)

    def _get_column_display_name(self, column: str) -> str:
        """
        获取列的显示名称

        Args:
            column: 列名（内部键名）

        Returns:
            显示名称
        """
        col_info = self._column_labels.get(column, {})
        if isinstance(col_info, dict):
            return col_info.get("display", column.replace("_", " ").title())
        elif isinstance(col_info, str):
            # 兼容旧格式：直接是字符串
            return col_info
        else:
            return column.replace("_", " ").title()

    def _bind_mouse_wheel(self, widget):
        """绑定鼠标滚轮事件"""
        # Linux uses Button-4 and Button-5
        widget.bind("<Button-4>", self._on_mouse_wheel)
        widget.bind("<Button-5>", self._on_mouse_wheel)
        # Windows/MacOS uses MouseWheel
        widget.bind("<MouseWheel>", self._on_mouse_wheel)

    def _on_mouse_wheel(self, event):
        """处理鼠标滚轮滚动"""
        if event.num == 4 or event.delta > 0:
            self.fixed_tree.yview_scroll(-1, "units")
            self.main_tree.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.fixed_tree.yview_scroll(1, "units")
            self.main_tree.yview_scroll(1, "units")
        return "break"  # 阻止默认事件，防止重复滚动

    def _on_vsb_scroll(self, *args):
        """垂直滚动条回调"""
        self.fixed_tree.yview(*args)
        self.main_tree.yview(*args)

    def _on_fixed_select(self, event):
        """左侧选择同步到右侧"""
        if self._selection_in_progress:
            return  # 防止递归触发

        selection = self.fixed_tree.selection()
        if selection:
            self._selection_in_progress = True
            try:
                # 避免递归触发
                if self.main_tree.selection() != selection:
                    self.main_tree.selection_set(selection)
                    self.main_tree.see(selection[0])
                self._handle_selection(selection[0])
            finally:
                self._selection_in_progress = False

    def _on_main_select(self, event):
        """右侧选择同步到左侧"""
        if self._selection_in_progress:
            return  # 防止递归触发

        selection = self.main_tree.selection()
        if selection:
            self._selection_in_progress = True
            try:
                if self.fixed_tree.selection() != selection:
                    self.fixed_tree.selection_set(selection)
                    self.fixed_tree.see(selection[0])
                self._handle_selection(selection[0])
            finally:
                self._selection_in_progress = False

    def _handle_selection(self, symbol):
        """处理选择逻辑"""

        # 忽略临时行的选择，自动跳转到实际股票行
        if symbol.startswith(TEMP_ROW_PREFIX):
            actual_symbol = symbol.replace(TEMP_ROW_PREFIX, "")
            self._restore_selection(actual_symbol)
            return

        # 防止重复处理同一只股票（由于事件异步排队导致）
        if symbol == self._last_selected_symbol:
            return

        self._last_selected_symbol = symbol

        # 找到对应的原始数据
        stock_data = next(
            (s for s in self.filtered_data if s["symbol"] == symbol), None
        )

        if stock_data and self.on_selection_callback:
            self.on_selection_callback(symbol, stock_data["raw_data"])

    def _configure_tree_columns(self, columns):
        """
        动态配置Treeview列

        Args:
            columns: 列名列表
        """
        self.main_tree["columns"] = columns

        for col in columns:
            # 使用配置中的缩写名作为标题
            title = self._get_column_display_name(col)

            # 绑定排序命令
            # 注意：lambda中的col需要默认参数绑定当前值
            self.main_tree.heading(
                col, text=title, command=lambda c=col: self.sort_by(c)
            )

            # 动态计算宽度: 字符数 * 系数 + padding，确保最小宽度
            # 使用较大的系数确保标题完整显示
            width = max(len(title) * 20 + 30, 70)
            self.main_tree.column(col, width=width, anchor=tk.CENTER, stretch=False)

        # 绑定右键菜单（每次配置列时重新绑定）
        self.main_tree.bind("<Button-3>", self._show_column_context_menu)

        # 绑定列拖拽事件（在表头区域）
        self.main_tree.bind("<ButtonPress-1>", self._on_header_press)
        self.main_tree.bind("<B1-Motion>", self._on_header_drag)
        self.main_tree.bind("<ButtonRelease-1>", self._on_header_release)

        # 列配置变化时通知宽度变化
        self._notify_width_changed()

    def load_data(self, scan_results: Dict):
        """
        加载扫描结果数据

        Args:
            scan_results: 扫描结果字典
        """
        # 清除临时行状态（重新加载数据时）
        self._remove_temp_row()
        self._current_temp_stats = None

        self.stock_data = []

        for result in scan_results.get("results", []):
            if "error" in result:
                continue  # 跳过错误股票

            symbol = result["symbol"]

            # 基础数据
            item = {"symbol": symbol, "raw_data": result}

            # 1. 统计字段：优先使用 JSON cache 中的预计算值
            # 如果不存在（向后兼容），则回退到自己计算
            if "avg_quality" in result and "max_quality" in result:
                # 直接使用 batch_scan 计算好的统计信息
                item["avg_quality"] = result["avg_quality"]
                item["max_quality"] = result["max_quality"]
            else:
                # 向后兼容：旧版本 JSON 没有这些字段，自己计算
                breakouts = result.get("breakouts", [])
                quality_scores = [
                    bo.get("quality_score", 0)
                    for bo in breakouts
                    if bo.get("quality_score")
                ]
                item["avg_quality"] = (
                    sum(quality_scores) / len(quality_scores) if quality_scores else 0
                )
                item["max_quality"] = max(quality_scores) if quality_scores else 0

            # 2. 动态添加其他标量字段（直接使用 JSON 原始字段名）
            # 注意：排除 label_ 开头的字段，避免在 Configure Columns 中显示
            for k, v in result.items():
                if k in ["symbol", "breakouts", "error"]:
                    continue
                if k.startswith("label_"):
                    continue  # 跳过标签统计量字段
                # 只添加标量值
                if isinstance(v, (int, float, str, bool)):
                    item[k] = v

            # 3. 从突破点的 labels 计算标签统计量
            breakouts = result.get("breakouts", [])
            label_stats = self._calculate_label_stats(breakouts)
            item["_label_stats"] = label_stats  # 内部字段，不会被 Configure Columns 发现

            # 4. 初始化 label 字段（根据当前选择的类型）
            label_type = self._label_type_var.get()
            item["label"] = label_stats.get(label_type)

            self.stock_data.append(item)

        # 动态确定列（应用列配置过滤）
        if self.stock_data:
            from ..config import get_ui_config_loader

            # 动态发现所有标量字段（排除内部字段和特殊字段）
            first_item = self.stock_data[0]
            all_columns = [
                k for k in first_item.keys()
                if k not in ["symbol", "raw_data"] and not k.startswith("_")
            ]

            # 从配置加载列设置
            config_loader = get_ui_config_loader()
            config = config_loader.get_stock_list_column_config()

            # 第一层：总开关（一键显示/隐藏）
            columns_enabled = config.get("columns_enabled", True)
            if not columns_enabled:
                # 只显示 Symbol（无其他列）
                columns = []
            else:
                # 第二层：过滤可见列
                visible_columns = config.get("visible_columns", all_columns)
                columns = [c for c in visible_columns if c in all_columns]

                # 排序：按优先级
                priority = config.get("column_priority", [])
                columns.sort(key=lambda x: priority.index(x) if x in priority else 999)

            self._configure_tree_columns(columns)

        # 直接使用原始数据（无筛选）
        self.filtered_data = self.stock_data
        self._update_tree()

    def calculate_required_width(self) -> int:
        """
        计算 StockListPanel 所需的总宽度

        计算公式：
        - Symbol列：160px（固定）
        - 可见列：sum(len(title) * 15 + 15 for each column)
        - 垂直滚动条：20px
        - Padding：10px

        Returns:
            所需宽度（像素）
        """
        SYMBOL_WIDTH = 160
        SCROLLBAR_WIDTH = 20
        PADDING = 10

        # 获取当前可见列
        columns = self.main_tree["columns"]

        # 如果没有可见列，只显示 Symbol 列
        if not columns:
            return SYMBOL_WIDTH + SCROLLBAR_WIDTH + PADDING

        # 计算所有可见列的总宽度
        total_column_width = 0
        for col in columns:
            # 使用配置中的缩写名（与 _configure_tree_columns 中的逻辑一致）
            title = self._get_column_display_name(col)
            col_width = max(len(title) * 20 + 30, 70)
            total_column_width += col_width

        # 总宽度 = Symbol列 + 所有属性列 + 滚动条 + Padding
        total_width = SYMBOL_WIDTH + total_column_width + SCROLLBAR_WIDTH + PADDING

        return total_width

    def _notify_width_changed(self):
        """通知宽度变化（触发回调）"""
        if self.on_width_changed_callback:
            required_width = self.calculate_required_width()
            self.on_width_changed_callback(required_width)

    def _update_tree(self, restore_selection: bool = True):
        """
        更新Treeview显示

        Args:
            restore_selection: 是否恢复之前的选中状态（默认True）
        """
        # 【1】保存当前选中的股票
        current_selection = None
        if restore_selection:
            current_selection = self.get_selected_symbol()

        # 清空现有项
        for item in self.fixed_tree.get_children():
            self.fixed_tree.delete(item)
        for item in self.main_tree.get_children():
            self.main_tree.delete(item)

        # 获取当前动态列
        columns = self.main_tree["columns"]

        # 插入数据
        for stock in self.filtered_data:
            symbol = stock["symbol"]
            # 使用 symbol 作为 iid，方便同步
            self.fixed_tree.insert("", tk.END, iid=symbol, values=(symbol,))

            # 动态构建值列表
            values = []
            for col in columns:
                val = stock.get(col, "")
                # 格式化浮点数
                if isinstance(val, float):
                    values.append(f"{val:.1f}")
                else:
                    values.append(str(val))

            self.main_tree.insert(
                "",
                tk.END,
                iid=symbol,
                values=values,
            )

        # 【2】恢复之前的选中状态
        if restore_selection and current_selection:
            # 检查该股票是否还在筛选后的列表中
            if any(s["symbol"] == current_selection for s in self.filtered_data):
                self._restore_selection(current_selection)

    def sort_by(self, column: str, reverse: bool = None):
        """
        按列排序

        Args:
            column: 列名 (数据字段名)
            reverse: 是否倒序（None表示自动切换）
        """
        # 自动切换排序方向
        if reverse is None:
            if hasattr(self, "_last_sort_column") and self._last_sort_column == column:
                reverse = not self._last_sort_reverse
            else:
                reverse = True  # 默认倒序

        self._last_sort_column = column
        self._last_sort_reverse = reverse

        # 排序
        # 使用 get(column, 0) 处理缺失值，同时处理 None 值
        def sort_key(x):
            val = x.get(column)
            if val is None:
                return (0, 0)  # None 值排在最后（倒序时）或最前（正序时）
            return (1, val)
        self.filtered_data.sort(key=sort_key, reverse=reverse)
        self._update_tree()

        # 排序后重新插入临时行（如果存在）
        if self._current_temp_stats:
            symbol, stats = self._current_temp_stats
            self.show_temp_row(symbol, stats)

    def get_selected_symbol(self):
        """获取当前选中的股票代码"""
        selection = self.fixed_tree.selection()
        if not selection:
            return None
        return selection[0]

    def _restore_selection(self, symbol: str):
        """
        恢复指定股票的选中状态

        Args:
            symbol: 股票代码
        """
        try:
            # 使用 _selection_in_progress 标志防止触发回调
            self._selection_in_progress = True

            # 同时选中左右两侧的 Treeview
            self.fixed_tree.selection_set(symbol)
            self.main_tree.selection_set(symbol)

            # 确保选中项可见（滚动到视图内）
            self.fixed_tree.see(symbol)
            self.main_tree.see(symbol)

        finally:
            self._selection_in_progress = False

    def set_visible_columns(self, columns: list):
        """
        动态设置可见列（不重新加载数据）

        Args:
            columns: 可见列名列表
        """
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config_loader.set_visible_columns(columns)

        # 只更新列配置，复用现有数据
        self._configure_tree_columns(columns)
        self._update_tree()

    def _on_toggle_columns(self):
        """工具栏复选框回调：切换列显示"""
        new_state = self.toggle_columns_enabled()
        self._columns_enabled_var.set(new_state)

    def _on_configure_columns(self):
        """工具栏按钮回调：打开列配置对话框"""
        from ..dialogs import ColumnConfigDialog
        from ..config import get_ui_config_loader

        if not self.stock_data:
            return  # 没有数据时不打开

        # 动态发现所有字段（排除内部字段）
        first_item = self.stock_data[0]
        available_columns = [
            k for k in first_item.keys()
            if k not in ["symbol", "raw_data"] and not k.startswith("_")
        ]

        # 当前可见列
        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = config.get("visible_columns", [])

        # 打开对话框
        ColumnConfigDialog(
            parent=self.parent.winfo_toplevel(),
            available_columns=available_columns,
            visible_columns=visible_columns,
            on_apply_callback=self.set_visible_columns,
        )

    def _on_label_type_changed(self, event=None):
        """标签类型切换时更新显示"""
        label_type = self._label_type_var.get()

        # 从内部统计量字典中获取对应类型的值
        for stock in self.stock_data:
            label_stats = stock.get("_label_stats", {})
            stock["label"] = label_stats.get(label_type)

        # 同步到 filtered_data 并更新显示
        self.filtered_data = self.stock_data
        self._update_tree()

    def _calculate_label_stats(self, breakouts: list) -> dict:
        """
        从突破点的 labels 计算标签统计量

        Args:
            breakouts: 突破点列表（来自 JSON）

        Returns:
            统计量字典：{"avg": 0.12, "max": 0.25, "best_quality": 0.18, "latest": 0.10}
        """
        if not breakouts:
            return {}

        # 获取第一个有效的 label_key
        label_key = None
        for bo in breakouts:
            labels = bo.get("labels", {})
            if labels:
                label_key = list(labels.keys())[0]
                break

        if not label_key:
            return {}

        # 收集所有有效的标签值
        valid_labels = []
        for bo in breakouts:
            labels = bo.get("labels", {})
            val = labels.get(label_key)
            if val is not None:
                valid_labels.append(val)

        stats = {}

        # 1. 平均值
        stats["avg"] = sum(valid_labels) / len(valid_labels) if valid_labels else None

        # 2. 最大值
        stats["max"] = max(valid_labels) if valid_labels else None

        # 3. 最高质量突破的标签
        best_quality_bo = max(
            breakouts, key=lambda x: x.get("quality_score") or 0
        )
        best_labels = best_quality_bo.get("labels", {})
        stats["best_quality"] = best_labels.get(label_key)

        # 4. 最近突破的标签（按日期排序）
        latest_bo = max(breakouts, key=lambda x: x.get("date", ""))
        latest_labels = latest_bo.get("labels", {})
        stats["latest"] = latest_labels.get(label_key)

        return stats

    def toggle_columns_enabled(self):
        """
        一键开关：显示/隐藏所有属性列

        Returns:
            新的状态（True=显示，False=隐藏）
        """
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()

        # 切换状态
        current_state = config.get("columns_enabled", True)
        new_state = not current_state
        config_loader.set_columns_enabled(new_state)

        # 重新加载列显示（不重新加载数据）
        if self.stock_data:
            if new_state:
                # 恢复用户配置的列
                visible_columns = config.get("visible_columns", [])
                # 过滤出实际存在的列（排除内部字段）
                first_item = self.stock_data[0]
                all_columns = [
                    k for k in first_item.keys()
                    if k not in ["symbol", "raw_data"] and not k.startswith("_")
                ]
                columns = [c for c in visible_columns if c in all_columns]
                self._configure_tree_columns(columns)
            else:
                # 隐藏所有列
                self._configure_tree_columns([])

            self._update_tree()

        return new_state

    def _show_column_context_menu(self, event):
        """显示列右键菜单"""
        # 获取所有可用列（排除内部字段）
        if not self.stock_data:
            return

        first_item = self.stock_data[0]
        all_columns = [
            k for k in first_item.keys()
            if k not in ["symbol", "raw_data"] and not k.startswith("_")
        ]

        # 获取当前可见列
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = config.get("visible_columns", [])

        # 创建上下文菜单（使用较大字体以便复选标记更清晰）
        menu = tk.Menu(self.main_tree, tearoff=0, font=("TkDefaultFont", 12))

        # 保存 BooleanVar 引用，防止被垃圾回收导致复选状态丢失
        self._menu_vars = []

        for col in all_columns:
            # 在右键菜单中也显示缩写名（保持一致）
            display_name = self._get_column_display_name(col)
            is_visible = col in visible_columns

            # 使用自定义标记符号代替默认复选框（更大更明显）
            label = f"✓  {display_name}" if is_visible else f"    {display_name}"

            menu.add_command(
                label=label,
                font=("TkDefaultFont", 12),
                command=lambda c=col: self._toggle_column(c),
            )

        # 显示菜单
        # 点击菜单外区域时自动关闭菜单
        menu.bind("<FocusOut>", lambda e: menu.unpost())
        menu.tk_popup(event.x_root, event.y_root)

    def _toggle_column(self, column: str):
        """切换单个列的显示/隐藏"""
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = list(config.get("visible_columns", []))

        if column in visible_columns:
            visible_columns.remove(column)
        else:
            visible_columns.append(column)

        self.set_visible_columns(visible_columns)

    # ==================== 列拖拽排序 ====================

    def _get_column_at_x(self, x: int, y: int = 5) -> Optional[str]:
        """
        根据 x 坐标获取列名

        Args:
            x: 相对于 Treeview 的 x 坐标
            y: 相对于 Treeview 的 y 坐标（默认 5，表头区域）

        Returns:
            列名，如果不在任何列上返回 None
        """
        # 使用 identify_column 获取列标识符（如 "#1", "#2" 等）
        col_id = self.main_tree.identify_column(x)
        if not col_id or col_id == "#0":
            return None

        # 将 "#1" 转换为索引 0
        try:
            col_index = int(col_id.replace("#", "")) - 1
            columns = self.main_tree["columns"]
            if 0 <= col_index < len(columns):
                return columns[col_index]
        except (ValueError, IndexError):
            pass

        return None

    def _get_column_insert_index(self, x: int) -> int:
        """
        根据 x 坐标计算插入位置索引

        Args:
            x: 相对于 Treeview 的 x 坐标

        Returns:
            插入位置索引
        """
        columns = self.main_tree["columns"]
        if not columns:
            return 0

        # 使用 identify_column 获取当前列
        col_id = self.main_tree.identify_column(x)
        if not col_id or col_id == "#0":
            return len(columns)

        try:
            col_index = int(col_id.replace("#", "")) - 1
            if col_index < 0:
                return 0
            if col_index >= len(columns):
                return len(columns)

            # 获取该列的边界框来判断是在左半边还是右半边
            # 使用 bbox 获取列的实际位置
            col_name = columns[col_index]

            # 获取列宽和计算中点
            # 由于 bbox 需要 item，我们用另一种方式：通过累加宽度
            # 但需要考虑滚动偏移
            xview = self.main_tree.xview()
            total_width = sum(self.main_tree.column(c, "width") for c in columns)
            scroll_offset = xview[0] * total_width

            # 计算当前列的起始位置（相对于视口）
            col_start = -scroll_offset
            for i, c in enumerate(columns):
                if i == col_index:
                    break
                col_start += self.main_tree.column(c, "width")

            col_width = self.main_tree.column(col_name, "width")
            col_center = col_start + col_width / 2

            if x < col_center:
                return col_index
            else:
                return col_index + 1

        except (ValueError, IndexError):
            return len(columns)

    def _is_in_header(self, x: int, y: int) -> bool:
        """
        判断坐标是否在表头区域

        Args:
            x: 相对于 Treeview 的 x 坐标
            y: 相对于 Treeview 的 y 坐标

        Returns:
            是否在表头区域
        """
        region = self.main_tree.identify_region(x, y)
        return region == "heading"

    def _on_header_press(self, event):
        """表头按下事件"""
        # DEBUG
        region = self.main_tree.identify_region(event.x, event.y)
        print(f"[DEBUG] Press: x={event.x}, y={event.y}, region={region}")

        # 只在表头区域响应
        if not self._is_in_header(event.x, event.y):
            print(f"[DEBUG] Not in header, skipping")
            self._drag_data["column"] = None
            self._drag_data["dragging"] = False
            return

        column = self._get_column_at_x(event.x)
        print(f"[DEBUG] Column at x: {column}")
        if column:
            self._drag_data["column"] = column
            self._drag_data["start_x"] = event.x
            self._drag_data["dragging"] = False  # 还未开始拖拽

    def _on_header_drag(self, event):
        """表头拖拽事件"""
        if not self._drag_data["column"]:
            return

        # 检查是否超过拖拽阈值
        if not self._drag_data["dragging"]:
            dx = abs(event.x - self._drag_data["start_x"])
            if dx < self._drag_threshold:
                return  # 还未超过阈值，不开始拖拽
            # 超过阈值，开始拖拽
            self._drag_data["dragging"] = True
            self.main_tree.config(cursor="fleur")

        # 创建或更新拖拽指示器
        self._update_drag_indicator(event.x)

    def _on_header_release(self, event):
        """表头释放事件"""
        # 恢复光标
        self.main_tree.config(cursor="")

        # 销毁拖拽指示器
        if self._drag_indicator:
            self._drag_indicator.destroy()
            self._drag_indicator = None

        drag_column = self._drag_data["column"]
        was_dragging = self._drag_data["dragging"]

        # 重置状态
        self._drag_data["column"] = None
        self._drag_data["dragging"] = False

        # 如果没有真正拖拽（只是点击），让默认的排序行为处理
        if not drag_column or not was_dragging:
            return  # 不返回 "break"，让点击排序正常工作

        # 计算目标位置
        target_index = self._get_column_insert_index(event.x)
        columns = list(self.main_tree["columns"])

        # 获取当前列的索引
        if drag_column not in columns:
            return "break"

        current_index = columns.index(drag_column)

        # 如果位置没有变化，不做处理
        if target_index == current_index or target_index == current_index + 1:
            return "break"

        # 重新排列列顺序
        columns.remove(drag_column)
        # 调整插入索引（因为移除了元素）
        if target_index > current_index:
            target_index -= 1
        columns.insert(target_index, drag_column)

        # 更新列配置并保存
        self._apply_column_order(columns)

        # 阻止后续事件（如排序命令）
        return "break"

    def _update_drag_indicator(self, x: int):
        """
        更新拖拽位置指示器

        Args:
            x: 当前 x 坐标
        """
        # 计算插入位置的 x 坐标
        target_index = self._get_column_insert_index(x)
        columns = self.main_tree["columns"]

        if not columns:
            return

        # 计算指示线的位置（考虑水平滚动）
        xview = self.main_tree.xview()
        total_width = sum(self.main_tree.column(c, "width") for c in columns)
        scroll_offset = xview[0] * total_width

        # 计算目标列的起始位置
        col_offset = 0
        for i, col in enumerate(columns):
            if i == target_index:
                break
            col_offset += self.main_tree.column(col, "width")

        # 相对于视口的位置
        indicator_x = col_offset - scroll_offset

        # 获取 Treeview 在屏幕上的位置
        tree_x = self.main_tree.winfo_rootx()
        tree_y = self.main_tree.winfo_rooty()

        # 创建或更新指示器（一条红色竖线）
        if not self._drag_indicator:
            self._drag_indicator = tk.Toplevel(self.main_tree)
            self._drag_indicator.overrideredirect(True)  # 无边框
            self._drag_indicator.attributes("-topmost", True)
            # 创建红色竖线
            line = tk.Frame(self._drag_indicator, bg="red", width=2, height=50)
            line.pack(fill=tk.Y, expand=True)

        # 更新位置
        self._drag_indicator.geometry(f"2x50+{tree_x + int(indicator_x)}+{tree_y}")

    def _apply_column_order(self, columns: list):
        """
        应用新的列顺序并保存到配置

        Args:
            columns: 新的列顺序列表
        """
        from ..config import get_ui_config_loader

        config_loader = get_ui_config_loader()

        # 更新可见列配置（保持新顺序）
        config_loader.set_visible_columns(columns)

        # 重新配置列显示
        self._configure_tree_columns(columns)
        self._update_tree()

    # ==================== 临时统计行功能 ====================

    def get_label_type(self) -> str:
        """
        获取当前选择的 label 类型

        Returns:
            label 类型: "avg", "max", "best_quality", "latest"
        """
        return self._label_type_var.get()

    def show_temp_row(self, symbol: str, temp_stats: dict):
        """
        在指定股票下方插入临时统计行

        Args:
            symbol: 股票代码
            temp_stats: 临时统计量字典 {
                "avg_quality": float,
                "max_quality": float,
                "total_breakouts": int,
                "label": float,
                ...
            }
        """
        # 1. 移除现有临时行
        self._remove_temp_row()

        # 2. 查找选中行的位置
        children = list(self.fixed_tree.get_children())
        try:
            index = children.index(symbol)
        except ValueError:
            return  # 股票不存在

        # 3. 计算插入位置（选中行之后）
        insert_index = index + 1

        # 4. 构建临时行 iid
        temp_iid = f"{TEMP_ROW_PREFIX}{symbol}"

        # 5. 插入左侧固定列（Symbol 显示为 "↳ (UI)"）
        self.fixed_tree.insert(
            "", insert_index,
            iid=temp_iid,
            values=("↳ (UI)",),
            tags=(TEMP_ROW_TAG,)
        )

        # 6. 插入右侧动态列
        columns = self.main_tree["columns"]
        values = []
        for col in columns:
            val = temp_stats.get(col, "")
            if isinstance(val, float):
                values.append(f"{val:.1f}")
            elif val is None:
                values.append("")
            else:
                values.append(str(val))

        self.main_tree.insert(
            "", insert_index,
            iid=temp_iid,
            values=values,
            tags=(TEMP_ROW_TAG,)
        )

        # 7. 记录当前临时行状态（用于排序后重建）
        self._current_temp_iid = temp_iid
        self._current_temp_stats = (symbol, temp_stats)

    def _remove_temp_row(self):
        """移除当前临时行（如存在）"""
        if self._current_temp_iid:
            try:
                self.fixed_tree.delete(self._current_temp_iid)
            except tk.TclError:
                pass  # 行已不存在
            try:
                self.main_tree.delete(self._current_temp_iid)
            except tk.TclError:
                pass  # 行已不存在
            self._current_temp_iid = None

    def hide_temp_row(self):
        """
        隐藏临时行（切换到 Browse Mode 时调用）
        """
        self._remove_temp_row()
        self._current_temp_stats = None
