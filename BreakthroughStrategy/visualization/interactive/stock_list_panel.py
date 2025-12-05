"""股票列表面板"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional


class StockListPanel:
    """股票列表面板"""

    def __init__(self, parent, on_selection_callback: Optional[Callable] = None):
        """
        初始化股票列表面板

        Args:
            parent: 父容器
            on_selection_callback: 选择回调函数
        """
        self.parent = parent
        self.on_selection_callback = on_selection_callback
        self.stock_data = []  # 原始数据
        self.filtered_data = []  # 筛选后的数据
        self._selection_in_progress = False  # 防止递归触发（同步期间）
        self._last_selected_symbol = None  # 记录上次选择的股票，防止重复处理

        # 创建UI
        self._create_ui()

    def _create_ui(self):
        """创建UI组件"""
        # 注意：字体样式由 ui_styles.py 的 configure_global_styles() 统一管理
        # 这里只调整行高以适应内容显示
        style = ttk.Style()
        style.configure("Treeview", rowheight=50)

        # 主容器
        container = ttk.Frame(self.parent)
        container.pack(fill=tk.BOTH, expand=True)

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

        # 筛选面板
        filter_frame = ttk.Frame(container)
        filter_frame.pack(fill=tk.X, pady=5)

        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Min Quality:").pack(side=tk.LEFT)
        self.min_quality_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(
            filter_frame,
            from_=0,
            to=100,
            textvariable=self.min_quality_var,
            width=8,
            command=self._on_filter_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="Min Breakthroughs:").pack(
            side=tk.LEFT, padx=(10, 0)
        )
        self.min_bts_var = tk.IntVar(value=0)
        ttk.Spinbox(
            filter_frame,
            from_=0,
            to=1000,
            textvariable=self.min_bts_var,
            width=8,
            command=self._on_filter_changed,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="Reset", command=self._reset_filters).pack(
            side=tk.LEFT, padx=5
        )

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
            # 格式化标题: snake_case -> Title Case
            title = col.replace("_", " ").title()

            # 绑定排序命令
            # 注意：lambda中的col需要默认参数绑定当前值
            self.main_tree.heading(
                col, text=title, command=lambda c=col: self.sort_by(c)
            )

            # 动态计算宽度: 字符数 * 12 + 20 padding
            width = len(title) * 15 + 15
            self.main_tree.column(col, width=width, anchor=tk.CENTER, stretch=False)

        # 绑定右键菜单（每次配置列时重新绑定）
        self.main_tree.bind("<Button-3>", self._show_column_context_menu)

    def load_data(self, scan_results: Dict):
        """
        加载扫描结果数据

        Args:
            scan_results: 扫描结果字典
        """
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
                breakthroughs = result.get("breakthroughs", [])
                quality_scores = [
                    bt.get("quality_score", 0)
                    for bt in breakthroughs
                    if bt.get("quality_score")
                ]
                item["avg_quality"] = (
                    sum(quality_scores) / len(quality_scores) if quality_scores else 0
                )
                item["max_quality"] = max(quality_scores) if quality_scores else 0

            # 2. 动态添加其他标量字段
            # 映射常用字段名以保持兼容性
            mappings = {"total_breakthroughs": "bts", "active_peaks": "active_peaks"}

            for k, v in result.items():
                if k in ["symbol", "breakthroughs", "error"]:
                    continue  # 如果是映射字段，使用新名字
                key = mappings.get(k, k)

                # 只添加标量值
                if isinstance(v, (int, float, str, bool)):
                    item[key] = v

            self.stock_data.append(item)

        # 动态确定列（应用列配置过滤）
        if self.stock_data:
            from .ui_config_loader import get_ui_config_loader

            # 动态发现所有标量字段
            first_item = self.stock_data[0]
            all_columns = [k for k in first_item.keys() if k not in ["symbol", "raw_data"]]

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

        # 初始化过滤数据
        self.filtered_data = self.stock_data.copy()
        self._update_tree()

    def _update_tree(self):
        """更新Treeview显示"""
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

    def _on_filter_changed(self, *args):
        """筛选条件变化"""
        min_quality = self.min_quality_var.get()
        min_bts = self.min_bts_var.get()

        self.filtered_data = [
            stock
            for stock in self.stock_data
            if stock.get("max_quality", 0) >= min_quality
            and stock.get("bts", 0) >= min_bts
        ]

        self._update_tree()

    def _reset_filters(self):
        """重置筛选"""
        self.min_quality_var.set(0.0)
        self.min_bts_var.set(0)
        self.filtered_data = self.stock_data.copy()
        self._update_tree()

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
        # 使用 get(column, 0) 处理缺失值
        self.filtered_data.sort(key=lambda x: x.get(column, 0), reverse=reverse)
        self._update_tree()

    def get_selected_symbol(self):
        """获取当前选中的股票代码"""
        selection = self.fixed_tree.selection()
        if not selection:
            return None
        return selection[0]

    def set_visible_columns(self, columns: list):
        """
        动态设置可见列（不重新加载数据）

        Args:
            columns: 可见列名列表
        """
        from .ui_config_loader import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config_loader.set_visible_columns(columns)

        # 只更新列配置，复用现有数据
        self._configure_tree_columns(columns)
        self._update_tree()

    def toggle_columns_enabled(self):
        """
        一键开关：显示/隐藏所有属性列

        Returns:
            新的状态（True=显示，False=隐藏）
        """
        from .ui_config_loader import get_ui_config_loader

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
                # 过滤出实际存在的列
                first_item = self.stock_data[0]
                all_columns = [k for k in first_item.keys() if k not in ["symbol", "raw_data"]]
                columns = [c for c in visible_columns if c in all_columns]
                self._configure_tree_columns(columns)
            else:
                # 隐藏所有列
                self._configure_tree_columns([])

            self._update_tree()

        return new_state

    def _show_column_context_menu(self, event):
        """显示列右键菜单"""
        # 获取所有可用列
        if not self.stock_data:
            return

        first_item = self.stock_data[0]
        all_columns = [k for k in first_item.keys() if k not in ["symbol", "raw_data"]]

        # 获取当前可见列
        from .ui_config_loader import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = config.get("visible_columns", [])

        # 创建上下文菜单
        menu = tk.Menu(self.main_tree, tearoff=0)

        for col in all_columns:
            display_name = col.replace("_", " ").title()
            is_visible = col in visible_columns

            # 创建 BooleanVar 来控制复选状态
            var = tk.BooleanVar(value=is_visible)
            menu.add_checkbutton(
                label=display_name,
                variable=var,
                command=lambda c=col: self._toggle_column(c),
            )

        # 显示菜单
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_column(self, column: str):
        """切换单个列的显示/隐藏"""
        from .ui_config_loader import get_ui_config_loader

        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()
        visible_columns = list(config.get("visible_columns", []))

        if column in visible_columns:
            visible_columns.remove(column)
        else:
            visible_columns.append(column)

        self.set_visible_columns(visible_columns)
