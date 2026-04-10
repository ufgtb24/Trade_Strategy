"""数据更新确认对话框。"""

import tkinter as tk
from tkinter import ttk

from BreakoutStrategy.live.pipeline.freshness import FreshnessStatus


def confirm_update(parent: tk.Tk, status: FreshnessStatus) -> bool:
    """弹出确认对话框，返回用户是否同意更新+扫描。"""
    dialog = tk.Toplevel(parent)
    dialog.title("数据需要更新")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)

    result = {"confirmed": False}

    frame = ttk.Frame(dialog, padding=16)
    frame.pack()

    ttk.Label(
        frame, text="数据需要更新",
        font=("TkDefaultFont", 11, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    newest = status.newest_local_date or "(no local data)"
    ttk.Label(frame, text=f"本地数据最新日期: {newest}").pack(anchor="w")

    missing = status.missing_trading_days
    ttk.Label(frame, text=f"待补交易日: {len(missing)} 个").pack(anchor="w")

    if missing:
        shown = missing[:5]
        for day in shown:
            ttk.Label(frame, text=f"  • {day}", foreground="#555").pack(anchor="w")
        if len(missing) > 5:
            ttk.Label(frame, text=f"  ...(and {len(missing) - 5} more)",
                     foreground="#888").pack(anchor="w")

    ttk.Label(
        frame, text="\n将自动下载新数据并运行扫描，是否继续？",
        wraplength=340,
    ).pack(anchor="w", pady=(8, 12))

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(fill=tk.X)

    def on_cancel():
        result["confirmed"] = False
        dialog.destroy()

    def on_confirm():
        result["confirmed"] = True
        dialog.destroy()

    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(btn_frame, text="确认", command=on_confirm).pack(side=tk.RIGHT)

    dialog.update_idletasks()
    # 自适应 + 居中
    w = dialog.winfo_reqwidth()
    h = dialog.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    dialog.geometry(f"+{x}+{y}")

    parent.wait_window(dialog)
    return result["confirmed"]
