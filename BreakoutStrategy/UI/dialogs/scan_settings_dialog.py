"""扫描设置对话框"""

import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

from ..config import get_ui_config_loader


class ScanSettingsDialog:
    """
    扫描设置对话框

    配置数据目录、输出目录、scan_date、股票过滤等扫描参数。
    """

    def __init__(
        self,
        parent,
        on_save_callback: Optional[Callable[[dict], None]] = None,
        initial_scan_date: Optional[date] = None,
        initial_lookback_days: int = 42,
        initial_filter_config: Optional[dict] = None,
        initial_forward_return_config: Optional[dict] = None,
    ):
        """
        初始化对话框

        Args:
            parent: 父窗口
            on_save_callback: 保存回调
            initial_scan_date: 初始 scan_date（None 表示自动推断）
            initial_lookback_days: 初始 lookback_days（信号统计窗口天数）
            initial_filter_config: 初始股票过滤配置
            initial_forward_return_config: 初始前瞻涨幅配置
        """
        self.on_save_callback = on_save_callback
        self._initial_scan_date = initial_scan_date
        self._initial_lookback_days = initial_lookback_days
        self._initial_filter_config = initial_filter_config or {
            "enabled": True,
            "price_min": 1.0,
            "price_max": 10.0,
            "volume_min": 100000,
        }
        self._initial_fr_config = initial_forward_return_config or {
            "enabled": True,
            "days": 42,
        }

        self.window = tk.Toplevel(parent)
        self.window.title("Scan Settings")
        self.window.transient(parent)
        self.window.grab_set()

        self._load_current_settings()
        self._create_ui()

        # 自适应窗口大小
        self.window.update_idletasks()
        self.window.minsize(450, 360)

    def _load_current_settings(self):
        """加载当前设置"""
        config_loader = get_ui_config_loader()
        self._data_dir = config_loader.get_stock_data_dir()
        self._output_dir = config_loader.get_scan_results_dir()

    def _create_ui(self):
        """创建 UI"""
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 数据目录
        ttk.Label(main_frame, text="Stock Data Directory:").grid(
            row=0, column=0, sticky="w", pady=5
        )

        data_frame = ttk.Frame(main_frame)
        data_frame.grid(row=0, column=1, sticky="ew", pady=5)

        self._data_dir_var = tk.StringVar(value=self._data_dir)
        ttk.Entry(data_frame, textvariable=self._data_dir_var, width=40).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(data_frame, text="Browse", command=self._browse_data_dir).pack(
            side=tk.LEFT
        )

        # 输出目录
        ttk.Label(main_frame, text="Output Directory:").grid(
            row=1, column=0, sticky="w", pady=5
        )

        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=1, column=1, sticky="ew", pady=5)

        self._output_dir_var = tk.StringVar(value=self._output_dir)
        ttk.Entry(output_frame, textvariable=self._output_dir_var, width=40).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(output_frame, text="Browse", command=self._browse_output_dir).pack(
            side=tk.LEFT
        )

        # Scan Date 设置
        ttk.Label(main_frame, text="Scan Date:").grid(
            row=2, column=0, sticky="w", pady=5
        )

        date_frame = ttk.Frame(main_frame)
        date_frame.grid(row=2, column=1, sticky="ew", pady=5)

        # 自动推断 checkbox（默认选中，除非有初始日期）
        self._auto_infer_date_var = tk.BooleanVar(
            value=(self._initial_scan_date is None)
        )
        self._auto_infer_cb = ttk.Checkbutton(
            date_frame,
            text="Auto-infer from data",
            variable=self._auto_infer_date_var,
            command=self._on_auto_infer_toggled,
        )
        self._auto_infer_cb.pack(side=tk.LEFT, padx=(0, 10))

        # 日期输入框
        initial_date_str = (
            self._initial_scan_date.strftime("%Y-%m-%d")
            if self._initial_scan_date
            else ""
        )
        self._scan_date_var = tk.StringVar(value=initial_date_str)
        self._date_entry = ttk.Entry(
            date_frame, textvariable=self._scan_date_var, width=12
        )
        self._date_entry.pack(side=tk.LEFT, padx=(0, 5))

        # 格式提示
        self._date_hint = ttk.Label(
            date_frame, text="(YYYY-MM-DD)", foreground="gray"
        )
        self._date_hint.pack(side=tk.LEFT)

        # 初始状态
        self._on_auto_infer_toggled()

        # Lookback Days
        ttk.Label(main_frame, text="Lookback Days:").grid(
            row=3, column=0, sticky="w", pady=5
        )

        lookback_frame = ttk.Frame(main_frame)
        lookback_frame.grid(row=3, column=1, sticky="w", pady=5)

        self._lookback_days_var = tk.IntVar(value=self._initial_lookback_days)
        ttk.Spinbox(
            lookback_frame,
            from_=7,
            to=252,
            textvariable=self._lookback_days_var,
            width=8,
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(lookback_frame, text="days", foreground="gray").pack(side=tk.LEFT)

        # Stock Filter 区域
        filter_frame = ttk.LabelFrame(main_frame, text="Stock Filter", padding=10)
        filter_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)

        # Enable Filter checkbox
        self._filter_enabled_var = tk.BooleanVar(
            value=self._initial_filter_config.get("enabled", True)
        )
        self._filter_enabled_cb = ttk.Checkbutton(
            filter_frame,
            text="Enable Filter (at entry date: scan_date - lookback_days)",
            variable=self._filter_enabled_var,
            command=self._on_filter_enabled_toggled,
        )
        self._filter_enabled_cb.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 5))

        # Price Range
        ttk.Label(filter_frame, text="Price Range:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self._price_min_var = tk.DoubleVar(
            value=self._initial_filter_config.get("price_min", 1.0)
        )
        self._price_min_entry = ttk.Entry(
            filter_frame, textvariable=self._price_min_var, width=8
        )
        self._price_min_entry.grid(row=1, column=1, padx=2)

        self._price_range_label = ttk.Label(filter_frame, text="~")
        self._price_range_label.grid(row=1, column=2)

        self._price_max_var = tk.DoubleVar(
            value=self._initial_filter_config.get("price_max", 10.0)
        )
        self._price_max_entry = ttk.Entry(
            filter_frame, textvariable=self._price_max_var, width=8
        )
        self._price_max_entry.grid(row=1, column=3, padx=2)

        self._price_unit_label = ttk.Label(filter_frame, text="USD", foreground="gray")
        self._price_unit_label.grid(row=1, column=4, sticky="w", padx=(5, 0))

        # Min Avg Volume (3M)
        ttk.Label(filter_frame, text="Min Avg Volume (3M):").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self._volume_min_var = tk.IntVar(
            value=self._initial_filter_config.get("volume_min", 100000)
        )
        self._volume_min_entry = ttk.Entry(
            filter_frame, textvariable=self._volume_min_var, width=12
        )
        self._volume_min_entry.grid(row=2, column=1, columnspan=2, sticky="w", padx=2)

        self._volume_unit_label = ttk.Label(filter_frame, text="shares", foreground="gray")
        self._volume_unit_label.grid(row=2, column=3, sticky="w", padx=(5, 0))

        # 初始状态
        self._on_filter_enabled_toggled()

        # Forward Return 区域
        fr_frame = ttk.LabelFrame(main_frame, text="Forward Return", padding=10)
        fr_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)

        # Enable checkbox
        self._fr_enabled_var = tk.BooleanVar(
            value=self._initial_fr_config.get("enabled", True)
        )
        self._fr_enabled_cb = ttk.Checkbutton(
            fr_frame,
            text="Calculate forward return",
            variable=self._fr_enabled_var,
            command=self._on_fr_enabled_toggled,
        )
        self._fr_enabled_cb.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))

        # Forward Days
        self._fr_days_label = ttk.Label(fr_frame, text="Forward Days:")
        self._fr_days_label.grid(row=1, column=0, sticky="w", padx=(20, 0), pady=2)

        self._fr_days_var = tk.IntVar(
            value=self._initial_fr_config.get("days", 42)
        )
        self._fr_days_spinbox = ttk.Spinbox(
            fr_frame,
            from_=5,
            to=252,
            textvariable=self._fr_days_var,
            width=8,
        )
        self._fr_days_spinbox.grid(row=1, column=1, padx=2)

        self._fr_days_unit = ttk.Label(fr_frame, text="trading days", foreground="gray")
        self._fr_days_unit.grid(row=1, column=2, sticky="w", padx=(5, 0))

        # 初始状态
        self._on_fr_enabled_toggled()

        # 按钮区
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Save", command=self._on_save).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_frame, text="Cancel", command=self.window.destroy).pack(
            side=tk.LEFT, padx=5
        )

        main_frame.columnconfigure(1, weight=1)

    def _browse_data_dir(self):
        """浏览数据目录"""
        path = filedialog.askdirectory(
            title="Select Stock Data Directory",
            initialdir=self._data_dir_var.get(),
        )
        if path:
            self._data_dir_var.set(path)

    def _browse_output_dir(self):
        """浏览输出目录"""
        path = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=self._output_dir_var.get(),
        )
        if path:
            self._output_dir_var.set(path)

    def _on_auto_infer_toggled(self):
        """自动推断 checkbox 切换"""
        if self._auto_infer_date_var.get():
            # 禁用日期输入
            self._date_entry.configure(state="disabled")
            self._date_hint.configure(foreground="gray")
        else:
            # 启用日期输入
            self._date_entry.configure(state="normal")
            self._date_hint.configure(foreground="black")

    def _on_filter_enabled_toggled(self):
        """过滤开关切换"""
        enabled = self._filter_enabled_var.get()
        state = "normal" if enabled else "disabled"
        fg_color = "black" if enabled else "gray"

        self._price_min_entry.configure(state=state)
        self._price_max_entry.configure(state=state)
        self._volume_min_entry.configure(state=state)
        self._price_range_label.configure(foreground=fg_color)
        self._price_unit_label.configure(foreground="gray")
        self._volume_unit_label.configure(foreground="gray")

    def _on_fr_enabled_toggled(self):
        """前瞻涨幅开关切换"""
        enabled = self._fr_enabled_var.get()
        state = "normal" if enabled else "disabled"

        self._fr_days_spinbox.configure(state=state)
        self._fr_days_label.configure(foreground="black" if enabled else "gray")
        self._fr_days_unit.configure(foreground="gray")

    def _parse_scan_date(self) -> Optional[date]:
        """
        解析 scan_date 输入

        Returns:
            date 对象，如果自动推断或解析失败返回 None
        """
        if self._auto_infer_date_var.get():
            return None

        date_str = self._scan_date_var.get().strip()
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _on_save(self):
        """保存设置"""
        settings = {
            "data_dir": self._data_dir_var.get(),
            "output_dir": self._output_dir_var.get(),
            "scan_date": self._parse_scan_date(),
            "lookback_days": self._lookback_days_var.get(),
            "filter_config": {
                "enabled": self._filter_enabled_var.get(),
                "price_min": self._price_min_var.get(),
                "price_max": self._price_max_var.get(),
                "volume_min": self._volume_min_var.get(),
            },
            "forward_return_config": {
                "enabled": self._fr_enabled_var.get(),
                "days": self._fr_days_var.get(),
            },
        }

        if self.on_save_callback:
            self.on_save_callback(settings)

        self.window.destroy()
