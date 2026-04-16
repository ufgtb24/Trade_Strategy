"""匹配列表面板：3 行过滤栏 + 可排序 Treeview。"""

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

from BreakoutStrategy.UI.styles import (
    FONT_FAMILY,
    FONT_LABEL,
    FONT_LABEL_BOLD,
    FONT_SIZE_SMALL,
)

if TYPE_CHECKING:
    from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _parse_iso_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


class MatchList(ttk.Frame):
    """左侧匹配列表：过滤 + 排序 + 单选回调。"""

    def __init__(
        self,
        parent: tk.Misc,
        on_row_selected: Callable[["MatchedBreakout"], None],
        scan_window_days: int,
        on_filter_changed: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self._all_items: list["MatchedBreakout"] = []
        self._visible_items: list["MatchedBreakout"] = []
        self._on_row_selected = on_row_selected
        self._on_filter_changed = on_filter_changed

        # Weeks 上限跟随 scan_window_days；scan 过的范围之外的 cutoff 没意义。
        # max(1, ...) 防止 scan_window_days < 7 时上限变 0。
        self._max_weeks: int = max(1, scan_window_days // 7)

        # 排序状态
        self._sort_col: str = "date"
        self._sort_asc: bool = False  # 初始 Date 降序

        self._build_filter_bar()
        self._build_treeview()

    # ---------- 过滤栏 ----------

    def _build_filter_bar(self) -> None:
        filter_frame = ttk.LabelFrame(self, text="Filter", padding=(6, 4, 6, 4))
        filter_frame.pack(fill=tk.X, padx=4, pady=(4, 2))

        # Row 1: Date —— 二选一 radio（weeks / days）+ 两个 Spinbox。
        # 无 "All" 选项：weeks max = scan_window_days//7，拉到最大即显示整个
        # 扫描窗口内的全部记录，与旧版 "All" 语义等价。
        # 文字用 "W"/"D" 单字符，避免 "Last 2 weeks" 这类长文案把 Filter 行
        # 撑到和 panel 一样宽 —— 实测这是左面板视觉"太宽"的主要来源。
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Date", width=6).pack(side=tk.LEFT)

        self.date_mode_var = tk.StringVar(value="weeks")
        default_weeks = min(2, self._max_weeks)
        self.weeks_var = tk.IntVar(value=default_weeks)
        self.days_var = tk.IntVar(value=7)

        ttk.Radiobutton(
            row1,
            text="",
            variable=self.date_mode_var,
            value="weeks",
            command=self._on_date_mode_changed,
        ).pack(side=tk.LEFT)
        self.weeks_spin = ttk.Spinbox(
            row1,
            from_=1,
            to=self._max_weeks,
            increment=1,
            textvariable=self.weeks_var,
            width=4,
            command=self._refresh_visible,
        )
        self.weeks_spin.pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(row1, text="W").pack(side=tk.LEFT, padx=(0, 8))

        ttk.Radiobutton(
            row1,
            text="",
            variable=self.date_mode_var,
            value="days",
            command=self._on_date_mode_changed,
        ).pack(side=tk.LEFT)
        self.days_spin = ttk.Spinbox(
            row1,
            from_=1,
            to=30,
            increment=1,
            textvariable=self.days_var,
            width=4,
            command=self._refresh_visible,
        )
        self.days_spin.pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(row1, text="D").pack(side=tk.LEFT)

        # Spinbox 直接输入数字时也要触发刷新（command 只响应箭头点击）
        self.weeks_var.trace_add("write", lambda *_: self._refresh_visible())
        self.days_var.trace_add("write", lambda *_: self._refresh_visible())

        # 同步初始 disabled/normal 状态
        self._update_date_controls_state()

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
        # 这里用 tk.Scale 而不是 ttk.Scale —— ttk.Scale 在默认主题下不接受
        # troughcolor，而用户需要把 trough 改成深灰以看清滑轨；tk.Scale 直接
        # 支持 troughcolor。同时 tk.Scale 提供 get(x, y) 把屏幕坐标反算成值，
        # 让 "点击 trough 跳到点击位置" 的精细筛选成为可能（ttk.Scale 默认
        # 只按 page-increment 跳几个固定档位）。
        row3 = ttk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Score", width=6).pack(side=tk.LEFT)
        self.score_var = tk.DoubleVar(value=-1.0)
        self.score_label_var = tk.StringVar(value="≥ -1.00")
        score_scale = tk.Scale(
            row3,
            from_=-1.0,
            to=1.0,
            orient=tk.HORIZONTAL,
            variable=self.score_var,
            resolution=0.01,
            length=350,             # 定长 350px，不随面板宽度拉伸；resolution=0.01
                                    # 下约 1.7px/档，点击跳转仍足够精确（不冲突）
            showvalue=0,  # 右侧已有自己的 Label 显示
            troughcolor="#555555",  # 深灰滑轨（原默认太浅看不清）
            highlightthickness=0,
            borderwidth=1,
            sliderrelief="raised",
            command=lambda v: self._on_score_changed(),
        )
        score_scale.pack(side=tk.LEFT, padx=(0, 4))
        # Button-1 默认是 "在 trough 上按 pageincrement 跳"。改成 "跳到点击处"：
        # 用 tk.Scale.get(x, y) 把点击坐标换算成数值再 set()。点击到 slider
        # 本身时放行，保留默认的抓取+拖拽逻辑。
        score_scale.bind("<Button-1>", self._on_scale_click)
        # 鼠标滚轮微调：Linux 是 Button-4 (上滚) / Button-5 (下滚)，
        # Windows/macOS 是 <MouseWheel> 带 event.delta。两套都绑，跨平台。
        score_scale.bind("<MouseWheel>", self._on_scale_wheel)
        score_scale.bind("<Button-4>", self._on_scale_wheel)
        score_scale.bind("<Button-5>", self._on_scale_wheel)
        ttk.Label(row3, textvariable=self.score_label_var, width=10).pack(side=tk.LEFT)

        # Row 3b: Include N/A checkbox
        self.include_na_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_frame,
            text="Include insufficient/error",
            variable=self.include_na_var,
            command=self._refresh_visible,
        ).pack(anchor="w", padx=(40, 0), pady=(0, 2))

    def _on_score_changed(self) -> None:
        self.score_label_var.set(f"≥ {self.score_var.get():+.2f}")
        self._refresh_visible()

    def _on_scale_wheel(self, event) -> str:
        """鼠标滚轮微调 Score 阈值。每格 ±0.02（resolution 0.01 的 2 倍）。

        Linux 通过 Button-4/5 上报滚动方向，event.delta 是 0；
        Windows/macOS 通过 <MouseWheel>，event.delta 是 120 的倍数（正=向上）。
        两套编码都处理，上下滚方向跟"上=加，下=减"的常识一致。
        """
        step = 0.02
        if event.num == 4 or (event.num == 0 and event.delta > 0):
            delta = step
        elif event.num == 5 or (event.num == 0 and event.delta < 0):
            delta = -step
        else:
            return "break"
        w = event.widget
        new_val = max(-1.0, min(1.0, self.score_var.get() + delta))
        w.set(round(new_val, 2))
        return "break"

    def _on_scale_click(self, event) -> str | None:
        """拦截 trough 点击，跳到点击位置对应的值；slider 本身放行（允许拖拽）。"""
        w = event.widget
        # tk.Scale.identify 返回 "slider" / "trough1" / "trough2" / ""
        if w.identify(event.x, event.y) == "slider":
            return None  # 点在滑块上，放行默认 drag
        # Tcl 层的 `scale get x y` 会把屏幕坐标反算成值 —— 内部已经处理好
        # trough 两端的滑块半径边距。Python 的 tk.Scale.get() 包装不接坐标
        # 参数，这里直接走 tk.call 调用底层命令。
        try:
            # str(w) 返回 Tcl widget path (等价于 w._w，但不触发 protected-access 警告)
            new_val = float(w.tk.call(str(w), "get", event.x, event.y))
        except tk.TclError:
            return "break"
        w.set(round(new_val, 2))
        return "break"  # 阻止默认的 page-increment 行为

    def _on_date_mode_changed(self) -> None:
        """Radio 切换时更新 Spinbox 启用状态，并立即刷新列表。"""
        self._update_date_controls_state()
        self._refresh_visible()

    def _update_date_controls_state(self) -> None:
        """按当前 mode 把对应 Spinbox 设为 normal，其它灰化。"""
        mode = self.date_mode_var.get()
        self.weeks_spin.configure(state="normal" if mode == "weeks" else "disabled")
        self.days_spin.configure(state="normal" if mode == "days" else "disabled")

    def _compute_date_cutoff(self) -> date:
        """按当前 radio/spinbox 计算 date cutoff（供 filter 和图表背景共用）。"""
        mode = self.date_mode_var.get()
        today = datetime.now().date()
        if mode == "weeks":
            try:
                weeks = self.weeks_var.get()
            except tk.TclError:
                weeks = 0
            return today - timedelta(days=max(1, weeks) * 7)
        try:
            days = self.days_var.get()
        except tk.TclError:
            days = 0
        return today - timedelta(days=max(1, days))

    def get_date_cutoff(self) -> date:
        """公开 API：当前 filter 的 date cutoff。"""
        return self._compute_date_cutoff()

    # ---------- Treeview ----------

    def _build_treeview(self) -> None:
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))

        # configure_global_styles 里全局 rowheight=25 是为更小的默认字体留的，
        # 但 FONT_LABEL (Arial 14pt) 在 HiDPI 下 linespace 可达 42px，25px 会
        # 让相邻行的文字上下重叠。这里按 font metrics 动态算出合适的行高，
        # 随字号变化自动跟上。ttk.Style 是进程全局的，但 live 进程只有 MatchList
        # 这一个 Treeview，不会有外溢副作用。
        content_font = tkfont.Font(font=FONT_LABEL)
        heading_font = tkfont.Font(font=FONT_LABEL_BOLD)
        linespace = content_font.metrics("linespace")
        rowheight = linespace + 6  # 少量上下 padding，避免字符紧贴行边
        ttk.Style().configure("Treeview", rowheight=rowheight)

        # 动态算列宽：按最长样本 + heading 的实际像素宽取 max，再加内边距。
        # Treeview 默认 stretch=True 会让列撑满可用空间 → 左面板被拉很宽，
        # 挤占 K 线图。我们 stretch=False + 精确宽度，让面板"用多少占多少"。
        col_samples = {
            # 真实美股 ticker 绝大多数 ≤5 字符，"OPTXW ★" 是用户实际场景里的
            # 5 字符 + 星标最宽情况。不用 "WWWWW ★" —— 那会让列宽被宽字母夸大，
            # 结果面板喧宾夺主挤走 K 线图。
            "symbol": ["OPTXW ★"],
            "date": ["2026-03-26"],  # ISO 固定 10 字
            "price": ["999.99"],  # 最大 3 位整数 + 2 位小数
            "score": ["+0.00", "N/A"],  # 正负分或 N/A
        }
        col_headings = {
            # 只算 heading 基础文本，不给排序箭头 " ↓" 预留宽度。
            # price/score 的 "Price ↓" bold 其实比 "999.99"/"+0.00" 更宽，如果
            # 为箭头预留会凭空多出 ~30px。代价是被选中排序的那一列的箭头会稍微
            # 挤压 heading 文本（大概 2 字符），但数据行不受影响，值得。
            "symbol": "Symbol",
            "date": "Date",
            "price": "Price",
            "score": "Score",
        }
        # Cell padding 16px：给相邻列之间留出呼吸感（两列之间的间隔 = 左列
        # 非锚定边的 padding + 右列非锚定边的 padding）。4px 下列文字贴得太紧。
        col_padding = 16
        self._col_widths: dict[str, int] = {}
        for c in ("symbol", "date", "price", "score"):
            content_w = max(content_font.measure(s) for s in col_samples[c])
            heading_w = heading_font.measure(col_headings[c])
            self._col_widths[c] = max(content_w, heading_w) + col_padding

        cols = ("symbol", "date", "price", "score")
        self.tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", selectmode="browse"
        )
        self.tree.column(
            "symbol", width=self._col_widths["symbol"], anchor="w", stretch=False
        )
        self.tree.column(
            "date", width=self._col_widths["date"], anchor="w", stretch=False
        )
        self.tree.column(
            "price", width=self._col_widths["price"], anchor="e", stretch=False
        )
        self.tree.column(
            "score", width=self._col_widths["score"], anchor="e", stretch=False
        )

        headings = [
            ("symbol", "Symbol"),
            ("date", "Date"),
            ("price", "Price"),
            ("score", "Score"),
        ]
        for col, label in headings:
            self.tree.heading(
                col, text=label, command=lambda c=col: self._on_heading_click(c)
            )

        # 颜色 tag：
        # - neg 由红改蓝（#0055CC）——用户红绿色盲，蓝/绿/灰组合更易分辨
        # - na 从 "#aaa" 9pt italic 改成 "#505050" + 正常字号 italic：
        #   原配色太浅看不清，且 9pt 比其他行 14pt 明显小；加深到 #505050，
        #   字号跟上 FONT_LABEL，保留 italic 维持 "降权" 的视觉暗示。
        self.tree.tag_configure("neg", foreground="#000000")
        self.tree.tag_configure("neu", foreground="#006AFF")
        self.tree.tag_configure("pos", foreground="#00A900")
        self.tree.tag_configure(
            "na",
            foreground="#A7A7A7",
            font=(FONT_FAMILY, FONT_SIZE_SMALL, "italic"),
        )

        # 选中状态 tag：放在颜色 tag 之后应用，覆盖 foreground。
        # 背景色 companion=浅蓝、current=灰蓝（与图表鲜艳深蓝区分，列表里更柔和）。
        self.tree.tag_configure("row_companion", background="#CFE2F3", foreground="#000000")
        self.tree.tag_configure("row_current", background="#4F6D8C", foreground="#FFFFFF")

        # 滚动条
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 键盘导航：因 _on_tree_select 里会 selection_remove，原生 ↑↓ 无 anchor，
        # 手动接管。Home/End 跳首尾。用 bind_all 不行（全局），只绑到 tree 本身。
        def _current_selected() -> "MatchedBreakout | None":
            # MatchList 自身不持有 current（SSOT 在 LiveApp），但我们可以从 tag
            # 反查行：谁挂 row_current，谁就是当前选中。
            for iid in self.tree.get_children():
                if "row_current" in self.tree.item(iid, "tags"):
                    idx = self.tree.index(iid)
                    return self._visible_items[idx]
            return None

        self.tree.bind("<Down>",  lambda _e: self._handle_key_navigate(1, _current_selected()))
        self.tree.bind("<Up>",    lambda _e: self._handle_key_navigate(-1, _current_selected()))
        self.tree.bind("<Home>",  lambda _e: self._handle_key_navigate_to(0))
        self.tree.bind("<End>",   lambda _e: self._handle_key_navigate_to(-1))

        self._update_heading_indicators()

    def _on_heading_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col == "price"  # Price 默认升序
        self._refresh_visible()
        self._update_heading_indicators()

    def _update_heading_indicators(self) -> None:
        labels = {
            "symbol": "Symbol",
            "date": "Date",
            "price": "Price",
            "score": "Score",
        }
        arrow = " ↑" if self._sort_asc else " ↓"
        for col, base in labels.items():
            text = base + arrow if col == self._sort_col else base
            self.tree.heading(col, text=text)

    def _on_tree_select(self, _event) -> None:
        if getattr(self, "_suppress_tree_select", False):
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self._visible_items):
            item = self._visible_items[idx]
            # 立刻清空原生 selection，避免系统蓝底压过 tag 背景（见 Task 5）
            self.tree.selection_remove(sel)
            self._on_row_selected(item)

    # ---------- 布局查询 ----------

    def get_preferred_width(self) -> int:
        """Treeview 列宽总和 + 滚动条 + 内边距。供外层 PanedWindow 设 sashpos 用。

        treeview 本身 stretch=False，列宽是精确的；为避免贴边，给滚动条和
        tree_frame 的 padx 各留一点余量。"""
        tree_width = sum(self._col_widths.values())
        scrollbar_width = 14  # ttk.Scrollbar 默认宽度经验值（紧凑）
        frame_padding = 6     # tree_frame padx=4 两侧 + 2 安全
        return tree_width + scrollbar_width + frame_padding

    # ---------- 数据接口 ----------

    def apply_selection_visual(
        self,
        current: "MatchedBreakout | None",
    ) -> None:
        """按 current 更新每行的状态 tag。

        规则：
        - current 行: 只挂 row_current（白字深蓝底）
        - 与 current 同 symbol 且非 current: 只挂 row_companion（黑字浅蓝底）
        - 其他: 仅 base_tag（pos/neg/neu/na 的原 sentiment 颜色）

        被高亮时**不**叠加 base_tag——因 ttk.Treeview 在不同主题下 tag 优先级
        不可靠，base_tag 的 foreground 可能压过 row_current 的白字导致看不清；
        高亮态本身已通过背景色明确区分，无需保留 sentiment 着色。
        """
        def _item_key(it: "MatchedBreakout") -> tuple:
            return (it.symbol, it.breakout_date)

        current_key = _item_key(current) if current else None
        current_symbol = current.symbol if current else None

        for iid in self.tree.get_children():
            idx = self.tree.index(iid)
            it = self._visible_items[idx]

            if _item_key(it) == current_key:
                new_tags = ("row_current",)
            elif current_symbol is not None and it.symbol == current_symbol:
                new_tags = ("row_companion",)
            else:
                new_tags = (self._row_tag(it),)
            self.tree.item(iid, tags=new_tags)

    def select_item(self, item: "MatchedBreakout") -> None:
        """从外部（如图表 pick）同步选中到 item，等价于模拟用户点击该行。

        过程：
        1. 按 (symbol, breakout_date) 2-tuple 定位 iid（不在 visible 则 no-op）
        2. tree.see(iid) 滚动到可见
        3. 直接调 on_row_selected(item) 走正常状态转移
        不使用 tree.selection_set()——本面板走全 tag 驱动的视觉模型，不依赖
        原生 selection；设 selection 反而会引入 <<TreeviewSelect>> 环路。
        """
        target_key = (item.symbol, item.breakout_date)
        for iid in self.tree.get_children():
            idx = self.tree.index(iid)
            it = self._visible_items[idx]
            if (it.symbol, it.breakout_date) == target_key:
                self.tree.see(iid)
                self._on_row_selected(item)
                return

    def _handle_key_navigate(
        self,
        direction: int,
        current: "MatchedBreakout | None",
    ) -> str | None:
        """↑/↓ 键触发；direction=+1 选下一行，-1 上一行。

        边界钳制不 wrap：在顶部按 ↑ 保持在顶部。
        """
        if not self._visible_items:
            return "break"
        if current is None:
            target_idx = 0
        else:
            target_key = (current.symbol, current.breakout_date)
            cur_idx = -1
            for i, it in enumerate(self._visible_items):
                if (it.symbol, it.breakout_date) == target_key:
                    cur_idx = i
                    break
            if cur_idx < 0:
                target_idx = 0
            else:
                target_idx = max(0, min(len(self._visible_items) - 1, cur_idx + direction))
        self._select_visible_index(target_idx)
        return "break"

    def _handle_key_navigate_to(self, idx: int) -> str | None:
        """Home/End 直跳首/尾。idx=-1 表示末尾。"""
        if not self._visible_items:
            return "break"
        if idx < 0:
            idx = len(self._visible_items) - 1
        self._select_visible_index(idx)
        return "break"

    def _select_visible_index(self, idx: int) -> None:
        """统一入口：滚动到 visible_items[idx] 并触发 on_row_selected 回调。

        供键盘导航和外部 select_item 复用——保证两条路径都先 scroll 后 notify。
        """
        children = self.tree.get_children()
        if 0 <= idx < len(children):
            self.tree.see(children[idx])
        self._on_row_selected(self._visible_items[idx])

    def set_items(self, items: list["MatchedBreakout"]) -> None:
        self._all_items = list(items)
        self._refresh_visible()

    def clear(self) -> None:
        self._all_items = []
        self._visible_items = []
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def get_visible_items(self) -> list["MatchedBreakout"]:
        """返回当前 filter+sort 后可见的 MatchedBreakout 列表。供 LiveApp 做
        current_selected 失效判定。"""
        return list(self._visible_items)

    def get_visible_bo_indices(self, symbol: str) -> set[int]:
        """返回 visible 中同 symbol 的 raw_breakout chart_index 集合。

        供 chart 4 级分类使用——此集合外、但属该 symbol 的 matched BO 会被
        渲染为灰色（filtered_out）。
        """
        return {
            it.raw_breakout["index"]
            for it in self._visible_items
            if it.symbol == symbol
        }

    # ---------- 过滤和排序 ----------

    def _refresh_visible(self) -> None:
        filtered = self._apply_filters(self._all_items)
        sorted_items = self._apply_sort(filtered)
        self._visible_items = sorted_items

        # 重建 Treeview
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for it in sorted_items:
            self.tree.insert(
                "", tk.END, values=self._row_values(it), tags=(self._row_tag(it),)
            )
        # 过滤/排序改变后，之前的选中行已消失；通知订阅者 filter 已变化
        # （LiveApp 会在 on_filter_changed 回调里决定是否清空 state.current_selected）
        if self._on_filter_changed is not None:
            self._on_filter_changed()

    def _apply_filters(self, items: list["MatchedBreakout"]) -> list["MatchedBreakout"]:
        # Date 过滤 —— cutoff 计算抽到 _compute_date_cutoff（同一 cutoff 用于
        # Treeview 过滤 + 图表背景范围可视化）。
        date_cutoff = self._compute_date_cutoff()

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
            # Date（date_cutoff 一定有值，不再需要 None 判断）
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

    def _apply_sort(self, items: list["MatchedBreakout"]) -> list["MatchedBreakout"]:
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
                    # None 总是排在末尾：升序时当作 +inf（排在最大之后），降序时当作 -inf
                    return float("inf") if not reverse else float("-inf")
                return it.sentiment_score
            return 0

        return sorted(items, key=keyfn, reverse=reverse)

    # ---------- 行渲染 ----------

    def _row_values(self, it: "MatchedBreakout") -> tuple:
        from BreakoutStrategy.UI.charts.range_utils import _collect_warnings

        symbol = it.symbol
        # 星标规则：sentiment_score > 0.30
        if it.sentiment_score is not None and it.sentiment_score > 0.30:
            symbol += " ★"
        # 范围降级标记：任一 warning 触发 ⚠
        if it.range_spec is not None and _collect_warnings(it.range_spec):
            symbol += " ⚠"

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
