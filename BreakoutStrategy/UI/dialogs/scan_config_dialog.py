"""扫描配置对话框

用于编辑 configs/scan_config.yaml 的配置
"""

import tkinter as tk
from tkinter import filedialog, ttk

from ..config import UIScanConfigLoader


class ScanConfigDialog:
    """扫描配置对话框

    支持两种扫描模式的配置：
    - Global 模式：全局时间范围
    - CSV 模式：基于 CSV 文件的 per-stock 时间范围
    """

    def __init__(
        self,
        parent: tk.Widget,
        scan_config_loader: UIScanConfigLoader,
    ):
        """
        初始化对话框

        Args:
            parent: 父窗口
            scan_config_loader: 扫描配置加载器
        """
        self.scan_config_loader = scan_config_loader

        # 创建模态窗口
        self.window = tk.Toplevel(parent)
        self.window.title("Scan Configuration")
        self.window.transient(parent)
        self.window.grab_set()

        # 变量
        self._init_variables()

        # 创建 UI
        self._create_ui()

        # 加载当前配置
        self._load_current_config()

        # 调整窗口大小和位置 - 自适应内容大小
        self.window.update_idletasks()
        # 获取内容所需的实际尺寸
        req_width = self.window.winfo_reqwidth()
        req_height = self.window.winfo_reqheight()
        # 设置最小尺寸，并添加一些边距
        min_width = max(550, req_width + 20)
        min_height = max(480, req_height + 20)
        self.window.minsize(min_width, min_height)

        # 居中显示
        x = parent.winfo_rootx() + (parent.winfo_width() - min_width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - min_height) // 2
        self.window.geometry(f"{min_width}x{min_height}+{x}+{y}")

    def _init_variables(self):
        """初始化 Tkinter 变量"""
        # 模式选择
        self.mode_var = tk.StringVar(value="global")

        # Global 模式
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()

        # CSV 模式
        self.csv_file_var = tk.StringVar()
        self.mon_before_var = tk.IntVar(value=3)
        self.mon_after_var = tk.IntVar(value=1)

        # 通用配置
        self.data_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.num_workers_var = tk.IntVar(value=8)
        self.max_stocks_var = tk.StringVar(value="")  # 空字符串表示不限制
        self.label_config_var = tk.StringVar(value="5-20")  # 回测标签配置

        # 配置快照（用于检测修改）
        self._config_snapshot = {}

        # 监听变量变化
        for var in [
            self.mode_var,
            self.start_date_var,
            self.end_date_var,
            self.csv_file_var,
            self.mon_before_var,
            self.mon_after_var,
            self.data_dir_var,
            self.output_dir_var,
            self.num_workers_var,
            self.max_stocks_var,
            self.label_config_var,
        ]:
            var.trace_add("write", self._on_config_changed)

    def _create_ui(self):
        """创建 UI 组件"""
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== 模式选择区 =====
        mode_frame = ttk.LabelFrame(main_frame, text="Scan Mode", padding=10)
        mode_frame.pack(fill=tk.X, pady=(0, 10))

        # 使用 tk.Radiobutton 以支持更大的指示器和选中边框
        self.global_radio = tk.Radiobutton(
            mode_frame,
            text="Global Time Range",
            variable=self.mode_var,
            value="global",
            command=self._on_mode_changed,
            font=("", 11, "bold"),
            indicatoron=1,
            selectcolor="#2e7d32",  # 深绿色指示器
            padx=8,
            pady=5,
            borderwidth=3,
            highlightthickness=2,
            highlightcolor="#1976d2",  # 蓝色高亮边框
            highlightbackground="#cccccc",
            relief=tk.FLAT,
        )
        self.global_radio.pack(side=tk.LEFT, padx=15)

        self.csv_radio = tk.Radiobutton(
            mode_frame,
            text="CSV Index Mode",
            variable=self.mode_var,
            value="csv",
            command=self._on_mode_changed,
            font=("", 11, "bold"),
            indicatoron=1,
            selectcolor="#2e7d32",
            padx=8,
            pady=5,
            borderwidth=3,
            highlightthickness=2,
            highlightcolor="#1976d2",
            highlightbackground="#cccccc",
            relief=tk.FLAT,
        )
        self.csv_radio.pack(side=tk.LEFT, padx=15)

        # ===== Global 模式配置 =====
        self.global_frame = ttk.LabelFrame(
            main_frame, text="Global Time Range", padding=10
        )
        self.global_frame.pack(fill=tk.X, pady=(0, 10))

        row1 = ttk.Frame(self.global_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Start Date:", width=12).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.start_date_var, width=15).pack(side=tk.LEFT)
        ttk.Label(row1, text="(YYYY-MM-DD, empty = no limit)").pack(
            side=tk.LEFT, padx=10
        )

        row2 = ttk.Frame(self.global_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="End Date:", width=12).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.end_date_var, width=15).pack(side=tk.LEFT)
        ttk.Label(row2, text="(YYYY-MM-DD, empty = no limit)").pack(
            side=tk.LEFT, padx=10
        )

        # ===== CSV 模式配置 =====
        self.csv_frame = ttk.LabelFrame(main_frame, text="CSV Index Mode", padding=10)
        self.csv_frame.pack(fill=tk.X, pady=(0, 10))

        # CSV 文件选择
        csv_row = ttk.Frame(self.csv_frame)
        csv_row.pack(fill=tk.X, pady=2)
        ttk.Label(csv_row, text="CSV File:", width=12).pack(side=tk.LEFT)
        self.csv_entry = ttk.Entry(csv_row, textvariable=self.csv_file_var, width=35)
        self.csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(csv_row, text="Browse", command=self._browse_csv).pack(
            side=tk.LEFT, padx=5
        )

        # 相对月份
        months_row = ttk.Frame(self.csv_frame)
        months_row.pack(fill=tk.X, pady=2)
        ttk.Label(months_row, text="Months Before:", width=12).pack(side=tk.LEFT)
        tk.Spinbox(
            months_row,
            textvariable=self.mon_before_var,
            from_=0,
            to=24,
            width=5,
            font=("", 12),
            buttondownrelief=tk.FLAT,
            buttonuprelief=tk.FLAT,
        ).pack(side=tk.LEFT)
        ttk.Label(months_row, text="  Months After:", width=12).pack(side=tk.LEFT)
        tk.Spinbox(
            months_row,
            textvariable=self.mon_after_var,
            from_=0,
            to=24,
            width=5,
            font=("", 12),
            buttondownrelief=tk.FLAT,
            buttonuprelief=tk.FLAT,
        ).pack(side=tk.LEFT)

        # ===== 通用配置 =====
        common_frame = ttk.LabelFrame(main_frame, text="Common Settings", padding=10)
        common_frame.pack(fill=tk.X, pady=(0, 10))

        # 数据目录
        data_row = ttk.Frame(common_frame)
        data_row.pack(fill=tk.X, pady=2)
        ttk.Label(data_row, text="Data Dir:", width=12).pack(side=tk.LEFT)
        ttk.Entry(data_row, textvariable=self.data_dir_var, width=35).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(data_row, text="Browse", command=self._browse_data_dir).pack(
            side=tk.LEFT, padx=5
        )

        # 输出目录
        output_row = ttk.Frame(common_frame)
        output_row.pack(fill=tk.X, pady=2)
        ttk.Label(output_row, text="Output Dir:", width=12).pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.output_dir_var, width=35).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(output_row, text="Browse", command=self._browse_output_dir).pack(
            side=tk.LEFT, padx=5
        )

        # 性能配置
        import os

        max_workers = os.cpu_count() or 8

        perf_row = ttk.Frame(common_frame)
        perf_row.pack(fill=tk.X, pady=2)
        ttk.Label(perf_row, text="Workers:", width=12).pack(side=tk.LEFT)
        tk.Spinbox(
            perf_row,
            textvariable=self.num_workers_var,
            from_=1,
            to=max_workers,
            width=5,
            font=("", 12),
            buttondownrelief=tk.FLAT,
            buttonuprelief=tk.FLAT,
        ).pack(side=tk.LEFT)

        ttk.Label(perf_row, text="  Max Stocks:", width=12).pack(side=tk.LEFT)
        ttk.Entry(perf_row, textvariable=self.max_stocks_var, width=8).pack(
            side=tk.LEFT
        )
        ttk.Label(perf_row, text="(empty = no limit)").pack(side=tk.LEFT, padx=5)

        # Label 配置
        label_row = ttk.Frame(common_frame)
        label_row.pack(fill=tk.X, pady=2)
        ttk.Label(label_row, text="Label:", width=12).pack(side=tk.LEFT)
        ttk.Entry(label_row, textvariable=self.label_config_var, width=10).pack(
            side=tk.LEFT
        )
        ttk.Label(label_row, text="(min-max days, e.g. 5-20)").pack(
            side=tk.LEFT, padx=5
        )

        # ===== 状态显示 =====
        self.status_label = ttk.Label(
            main_frame, text="", foreground="gray", font=("", 9)
        )
        self.status_label.pack(fill=tk.X, pady=5)

        # ===== 底部按钮 =====
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self.window.destroy).pack(
            side=tk.RIGHT, padx=5
        )

        self.save_button = ttk.Button(
            button_frame, text="Save", command=self._save_config, state="disabled"
        )
        self.save_button.pack(side=tk.RIGHT, padx=5)

        ttk.Button(button_frame, text="Reset", command=self._reset_config).pack(
            side=tk.LEFT, padx=5
        )

    def _on_mode_changed(self):
        """模式切换时更新 UI 状态"""
        mode = self.mode_var.get()

        # 选中/未选中样式
        selected_style = {"relief": tk.RIDGE, "bg": "#e3f2fd", "highlightbackground": "#1976d2"}
        normal_style = {"relief": tk.FLAT, "bg": "#d9d9d9", "highlightbackground": "#cccccc"}

        if mode == "global":
            # 启用 Global 配置，禁用 CSV 配置
            self._set_frame_state(self.global_frame, "normal")
            self._set_frame_state(self.csv_frame, "disabled")
            # 更新 Radiobutton 样式
            self.global_radio.config(**selected_style)
            self.csv_radio.config(**normal_style)
        else:
            # 禁用 Global 配置，启用 CSV 配置
            self._set_frame_state(self.global_frame, "disabled")
            self._set_frame_state(self.csv_frame, "normal")
            # 更新 Radiobutton 样式
            self.global_radio.config(**normal_style)
            self.csv_radio.config(**selected_style)

    def _set_frame_state(self, frame: ttk.Frame, state: str):
        """设置 frame 内所有输入控件的状态"""
        for child in frame.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Spinbox, ttk.Button, tk.Spinbox)):
                child.config(state=state)
            elif isinstance(child, ttk.Frame):
                self._set_frame_state(child, state)

    def _load_current_config(self):
        """加载当前配置到 UI"""
        loader = self.scan_config_loader

        # 模式
        mode = loader.get_scan_mode()
        self.mode_var.set(mode)

        # Global 模式配置
        start, end = loader.get_date_range()
        self.start_date_var.set(start or "")
        self.end_date_var.set(end or "")

        # CSV 模式配置
        csv_file = loader.get_csv_file()
        self.csv_file_var.set(csv_file or "")
        mon_before, mon_after = loader.get_relative_months()
        self.mon_before_var.set(mon_before)
        self.mon_after_var.set(mon_after)

        # 通用配置
        self.data_dir_var.set(loader.get_data_dir())
        self.output_dir_var.set(loader.get_output_dir())
        self.num_workers_var.set(loader.get_num_workers())

        max_stocks = loader.get_max_stocks()
        self.max_stocks_var.set(str(max_stocks) if max_stocks else "")

        # Label 配置
        self.label_config_var.set(loader.get_label_config_string())

        # 更新 UI 状态
        self._on_mode_changed()

        # 显示配置来源
        if loader.is_using_user_config():
            self.status_label.config(
                text="Using: user_scan_config.yaml", foreground="blue"
            )
        else:
            self.status_label.config(
                text="Using: scan_config.yaml (default)", foreground="gray"
            )

        # 保存快照并更新按钮状态
        self._save_snapshot()
        self._on_config_changed()

    def _reset_config(self):
        """重置为默认配置"""
        self.scan_config_loader.reset_to_default()
        self._load_current_config()
        self.status_label.config(
            text="Reset to default config", foreground="green"
        )

    def _save_snapshot(self):
        """保存当前配置快照"""
        self._config_snapshot = {
            "mode": self.mode_var.get(),
            "start_date": self.start_date_var.get(),
            "end_date": self.end_date_var.get(),
            "csv_file": self.csv_file_var.get(),
            "mon_before": self.mon_before_var.get(),
            "mon_after": self.mon_after_var.get(),
            "data_dir": self.data_dir_var.get(),
            "output_dir": self.output_dir_var.get(),
            "num_workers": self.num_workers_var.get(),
            "max_stocks": self.max_stocks_var.get(),
            "label_config": self.label_config_var.get(),
        }

    def _is_modified(self) -> bool:
        """检查配置是否有修改"""
        current = {
            "mode": self.mode_var.get(),
            "start_date": self.start_date_var.get(),
            "end_date": self.end_date_var.get(),
            "csv_file": self.csv_file_var.get(),
            "mon_before": self.mon_before_var.get(),
            "mon_after": self.mon_after_var.get(),
            "data_dir": self.data_dir_var.get(),
            "output_dir": self.output_dir_var.get(),
            "num_workers": self.num_workers_var.get(),
            "max_stocks": self.max_stocks_var.get(),
            "label_config": self.label_config_var.get(),
        }
        return current != self._config_snapshot

    def _on_config_changed(self, *args):
        """配置变化回调，更新 Save 按钮状态"""
        # 在 UI 完全初始化之前不处理
        if not hasattr(self, "save_button"):
            return

        if self._is_modified():
            self.save_button.config(state="normal")
        else:
            self.save_button.config(state="disabled")

    def _browse_csv(self):
        """浏览选择 CSV 文件"""
        file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV/Text files", "*.csv *.txt"), ("All files", "*.*")],
        )
        if file_path:
            self.csv_file_var.set(file_path)

    def _browse_data_dir(self):
        """浏览选择数据目录"""
        dir_path = filedialog.askdirectory(title="Select Data Directory")
        if dir_path:
            self.data_dir_var.set(dir_path)

    def _browse_output_dir(self):
        """浏览选择输出目录"""
        dir_path = filedialog.askdirectory(title="Select Output Directory")
        if dir_path:
            self.output_dir_var.set(dir_path)

    def _get_config_from_ui(self) -> dict:
        """从 UI 收集配置"""
        config = {}

        # 模式决定
        mode = self.mode_var.get()

        # Global 模式配置
        start_date = self.start_date_var.get().strip() or None
        end_date = self.end_date_var.get().strip() or None
        config["start_date"] = start_date
        config["end_date"] = end_date

        # CSV 模式配置
        csv_file = self.csv_file_var.get().strip() if mode == "csv" else None
        config["csv_file"] = csv_file
        config["mon_before"] = self.mon_before_var.get()
        config["mon_after"] = self.mon_after_var.get()

        # 通用配置
        config["data_dir"] = self.data_dir_var.get().strip()
        config["output_dir"] = self.output_dir_var.get().strip()
        config["num_workers"] = self.num_workers_var.get()

        max_stocks_str = self.max_stocks_var.get().strip()
        config["max_stocks"] = int(max_stocks_str) if max_stocks_str else None

        # Label 配置
        config["label_config"] = self.label_config_var.get().strip()

        return config

    def _save_config(self):
        """保存配置到用户配置文件"""
        try:
            config = self._get_config_from_ui()

            loader = self.scan_config_loader
            loader.set_date_range(config["start_date"], config["end_date"])
            loader.set_csv_file(config["csv_file"])
            loader.set_relative_months(config["mon_before"], config["mon_after"])
            loader.set_data_dir(config["data_dir"])
            loader.set_output_dir(config["output_dir"])
            loader.set_num_workers(config["num_workers"])
            loader.set_max_stocks(config["max_stocks"])

            # Label 配置（带验证）
            try:
                loader.set_label_config_from_string(config["label_config"])
            except ValueError as e:
                self.status_label.config(
                    text=f"Label config error: {str(e)}", foreground="red"
                )
                return

            # 保存到用户配置文件
            loader.save()

            # 更新快照和按钮状态
            self._save_snapshot()
            self._on_config_changed()

            self.status_label.config(
                text="Saved to: user_scan_config.yaml",
                foreground="green",
            )

        except Exception as e:
            self.status_label.config(text=f"Save error: {str(e)}", foreground="red")
