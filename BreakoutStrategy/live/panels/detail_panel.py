"""底部因子/情感摘要面板（两行紧凑）。"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


class DetailPanel(ttk.Frame):
    """因子值 + 情感摘要的两行展示区。"""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, padding=(8, 4, 8, 4))
        self.factors_var = tk.StringVar(value="Factors: -")
        self.sentiment_var = tk.StringVar(value="Sentiment: -")

        ttk.Label(self, textvariable=self.factors_var, anchor="w").pack(
            fill=tk.X, anchor="w"
        )
        ttk.Label(self, textvariable=self.sentiment_var, anchor="w").pack(
            fill=tk.X, anchor="w"
        )

    def update_item(self, item: "MatchedBreakout | None") -> None:
        if item is None:
            self.factors_var.set("Factors: -")
            self.sentiment_var.set("Sentiment: -")
            return

        factors_txt = " ".join(f"{k}={_fmt(v)}" for k, v in item.factors.items())
        self.factors_var.set(f"Factors: {factors_txt}")

        if item.sentiment_category == "insufficient_data":
            self.sentiment_var.set("Sentiment: insufficient data")
        elif item.sentiment_category == "error":
            self.sentiment_var.set("Sentiment: error")
        elif item.sentiment_category == "pending":
            self.sentiment_var.set("Sentiment: (pending analysis)")
        else:
            score = item.sentiment_score if item.sentiment_score is not None else 0.0
            summary = item.sentiment_summary or ""
            self.sentiment_var.set(f"Sentiment: {score:+.2f}  {summary}")

    def clear(self) -> None:
        self.update_item(None)
