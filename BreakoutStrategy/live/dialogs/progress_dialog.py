"""流水线进度对话框。"""

import tkinter as tk
from tkinter import ttk

from BreakoutStrategy.live.pipeline.daily_runner import PipelineProgress


_STAGE_LABELS = {
    "downloading": "Downloading data...",
    "scanning": "Scanning breakouts...",
    "matching": "Matching templates...",
    "sentiment": "Analyzing sentiment...",
    "done": "Done",
}


class ProgressDialog:
    """非阻塞进度对话框，提供 update_progress 接口。"""

    def __init__(self, parent: tk.Tk, title: str = "Running..."):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)
        self.dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # 禁止关闭

        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack()

        self.stage_var = tk.StringVar(value="Starting...")
        ttk.Label(frame, textvariable=self.stage_var, width=40).pack(pady=(0, 8))

        self.bar = ttk.Progressbar(
            frame, orient="horizontal", length=360, mode="determinate",
        )
        self.bar.pack(pady=(0, 4))

        self.detail_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.detail_var, foreground="#666").pack()

        self.dialog.update_idletasks()
        w = self.dialog.winfo_reqwidth()
        h = self.dialog.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.dialog.geometry(f"+{x}+{y}")

    def update_progress(self, progress: PipelineProgress) -> None:
        self.stage_var.set(_STAGE_LABELS.get(progress.stage, progress.stage))
        if progress.stage in ("downloading", "scanning", "matching"):
            self.bar.config(mode="indeterminate")
            self.bar.start(10)
            self.detail_var.set("")
        else:
            self.bar.stop()
            self.bar.config(mode="determinate", maximum=max(1, progress.total))
            self.bar["value"] = progress.current
            self.detail_var.set(f"{progress.current}/{progress.total}")
        self.dialog.update_idletasks()

    def close(self) -> None:
        self.bar.stop()
        self.dialog.grab_release()
        self.dialog.destroy()
