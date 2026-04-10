"""匹配列表面板：3 行过滤栏 + 可排序 Treeview。"""

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from BreakoutStrategy.live.pipeline.results import MatchedBreakout


_DATE_FILTERS = ["All", "Today", "Last 3 days", "Last 7 days"]


def _parse_iso_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


class MatchList(ttk.Frame):
    """左侧匹配列表：过滤 + 排序 + 单选回调。"""

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[["MatchedBreakout | None"], None],
    ):
        super().__init__(parent)
        self._all_items: list["MatchedBreakout"] = []
        self._visible_items: list["MatchedBreakout"] = []
        self._on_select = on_select

        # 排序状态
        self._sort_col: str = "date"
        self._sort_asc: bool = False  # 初始 Date 降序

        self._build_filter_bar()
        self._build_treeview()

    # ---------- 过滤栏 ----------

    def _build_filter_bar(self) -> None:
        filter_frame = ttk.LabelFrame(self, text="Filter", padding=(6, 4, 6, 4))
        filter_frame.pack(fill=tk.X, padx=4, pady=(4, 2))

        # Row 1: Date
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Date", width=6).pack(side=tk.LEFT)
        self.date_var = tk.StringVar(value=_DATE_FILTERS[0])
        date_cb = ttk.Combobox(
            row1, textvariable=self.date_var, values=_DATE_FILTERS,
            state="readonly", width=14,
        )
        date_cb.pack(side=tk.LEFT)
        date_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_visible())

        # Row 2: Price
        row2 = ttk.Frame(filter_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Price", width=6).pack(side=tk.LEFT)
        self.min_price_var = tk.StringVar(value="1.0")
        self.max_price_var = tk.StringVar(value="10.0")
        ttk.Entry(row2, textvariable=self.min_price_var, width=6).pack(side=tk.LEFT)
        ttk.Label(row2, text=" ~ ").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.max_price_var, width=6).pack(side=tk.LEFT)
        self.min_price_var.trace_add("write", lambda *_: self._refresh_visible())
        self.max_price_var.trace_add("write", lambda *_: self._refresh_visible())

        # Row 3: Score
        row3 = ttk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Score", width=6).pack(side=tk.LEFT)
        self.score_var = tk.DoubleVar(value=-1.0)
        self.score_label_var = tk.StringVar(value="≥ -1.00")
        score_scale = ttk.Scale(
            row3, from_=-1.0, to=1.0, orient=tk.HORIZONTAL,
            variable=self.score_var,
            command=lambda v: self._on_score_changed(),
        )
        score_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Label(row3, textvariable=self.score_label_var, width=10).pack(side=tk.LEFT)

        # Row 3b: Include N/A checkbox
        self.include_na_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_frame, text="Include insufficient/error",
            variable=self.include_na_var,
            command=self._refresh_visible,
        ).pack(anchor="w", padx=(40, 0), pady=(0, 2))

    def _on_score_changed(self) -> None:
        self.score_label_var.set(f"≥ {self.score_var.get():+.2f}")
        self._refresh_visible()

    # ---------- Treeview ----------

    def _build_treeview(self) -> None:
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))

        cols = ("symbol", "date", "price", "score")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.column("symbol", width=80, anchor="w")
        self.tree.column("date", width=85, anchor="w")
        self.tree.column("price", width=60, anchor="e")
        self.tree.column("score", width=70, anchor="e")

        headings = [
            ("symbol", "Symbol"),
            ("date", "Date"),
            ("price", "Price"),
            ("score", "Score"),
        ]
        for col, label in headings:
            self.tree.heading(col, text=label, command=lambda c=col: self._on_heading_click(c))

        # 颜色 tag
        self.tree.tag_configure("neg", foreground="#d00")
        self.tree.tag_configure("neu", foreground="#666")
        self.tree.tag_configure("pos", foreground="#080")
        self.tree.tag_configure("na", foreground="#aaa")

        # 滚动条
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self._update_heading_indicators()

    def _on_heading_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = (col == "price")  # Price 默认升序
        self._refresh_visible()
        self._update_heading_indicators()

    def _update_heading_indicators(self) -> None:
        labels = {"symbol": "Symbol", "date": "Date", "price": "Price", "score": "Score"}
        arrow = " ↑" if self._sort_asc else " ↓"
        for col, base in labels.items():
            text = base + arrow if col == self._sort_col else base
            self.tree.heading(col, text=text)

    def _on_tree_select(self, _event) -> None:
        sel = self.tree.selection()
        if not sel:
            self._on_select(None)
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self._visible_items):
            self._on_select(self._visible_items[idx])

    # ---------- 数据接口 ----------

    def set_items(self, items: list["MatchedBreakout"]) -> None:
        self._all_items = list(items)
        self._refresh_visible()

    def clear(self) -> None:
        self._all_items = []
        self._visible_items = []
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._on_select(None)

    # ---------- 过滤和排序 ----------

    def _refresh_visible(self) -> None:
        filtered = self._apply_filters(self._all_items)
        sorted_items = self._apply_sort(filtered)
        self._visible_items = sorted_items

        # 重建 Treeview
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for it in sorted_items:
            self.tree.insert("", tk.END, values=self._row_values(it), tags=(self._row_tag(it),))

    def _apply_filters(
        self, items: list["MatchedBreakout"]
    ) -> list["MatchedBreakout"]:
        # Date 过滤
        date_choice = self.date_var.get()
        today = datetime.now().date()
        if date_choice == "Today":
            date_cutoff = today
        elif date_choice == "Last 3 days":
            date_cutoff = today - timedelta(days=3)
        elif date_choice == "Last 7 days":
            date_cutoff = today - timedelta(days=7)
        else:
            date_cutoff = None

        # Price 过滤
        try:
            min_price = float(self.min_price_var.get())
        except ValueError:
            min_price = 0.0
        try:
            max_price = float(self.max_price_var.get())
        except ValueError:
            max_price = float("inf")

        # Score 过滤
        score_cutoff = self.score_var.get()
        include_na = self.include_na_var.get()

        result = []
        for it in items:
            # Date
            if date_cutoff is not None:
                bo_date = _parse_iso_date(it.breakout_date).date()
                if bo_date < date_cutoff:
                    continue
            # Price
            if not (min_price <= it.breakout_price <= max_price):
                continue
            # Score
            if it.sentiment_score is None:
                if not include_na:
                    continue
            else:
                if it.sentiment_score < score_cutoff:
                    continue
            result.append(it)
        return result

    def _apply_sort(
        self, items: list["MatchedBreakout"]
    ) -> list["MatchedBreakout"]:
        col = self._sort_col
        reverse = not self._sort_asc

        def keyfn(it: "MatchedBreakout"):
            if col == "symbol":
                return it.symbol
            if col == "date":
                return it.breakout_date
            if col == "price":
                return it.breakout_price
            if col == "score":
                # None 总是排在末尾（无论升降序）
                if it.sentiment_score is None:
                    return float("-inf") if not reverse else float("inf")
                return it.sentiment_score
            return 0

        return sorted(items, key=keyfn, reverse=reverse)

    # ---------- 行渲染 ----------

    def _row_values(self, it: "MatchedBreakout") -> tuple:
        symbol = it.symbol
        # 星标规则：sentiment_score > 0.30
        if it.sentiment_score is not None and it.sentiment_score > 0.30:
            symbol += " ★"
        date_txt = it.breakout_date
        price_txt = f"{it.breakout_price:.2f}"
        if it.sentiment_score is None:
            score_txt = "N/A"
        else:
            score_txt = f"{it.sentiment_score:+.2f}"
        return (symbol, date_txt, price_txt, score_txt)

    def _row_tag(self, it: "MatchedBreakout") -> str:
        if it.sentiment_score is None:
            return "na"
        if it.sentiment_score < 0:
            return "neg"
        if it.sentiment_score < 0.3:
            return "neu"
        return "pos"
