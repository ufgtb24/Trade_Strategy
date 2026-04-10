"""顶部工具栏：扫描状态显示 + 刷新按钮。"""

import tkinter as tk
from tkinter import ttk
from typing import Callable


class Toolbar(ttk.Frame):
    """顶部单行工具栏。"""

    def __init__(self, parent: tk.Misc, on_refresh: Callable[[], None]):
        super().__init__(parent, padding=(8, 4, 8, 4))

        self.last_scan_var = tk.StringVar(value="Last scan: (not loaded)")
        self.trial_var = tk.StringVar(value="Trial: (not loaded)")
        self.status_var = tk.StringVar(value="")

        ttk.Label(self, textvariable=self.last_scan_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(self, textvariable=self.trial_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(self, textvariable=self.status_var, foreground="#86868b").pack(side=tk.LEFT)

        ttk.Button(self, text="⟳ Refresh", command=on_refresh).pack(side=tk.RIGHT)

    def set_last_scan(self, scan_date_iso: str) -> None:
        self.last_scan_var.set(f"Last scan: {scan_date_iso}")

    def set_trial(self, trial_label: str) -> None:
        self.trial_var.set(f"Trial: {trial_label}")

    def set_status(self, status: str) -> None:
        self.status_var.set(status)
