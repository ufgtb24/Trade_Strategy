# Live UI Same-Symbol Selection Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 左侧匹配列表中同一 symbol 的多个 matched breakout 建立联动——当前选中深蓝/白字，同股票伴生行浅蓝/黑字，同股票上一次选中深绿/白字；K 线图 BO marker 四级着色；图表 marker 点击可反向选中列表行。

**Architecture:** SSOT 在 `LiveApp.state`，新增 `current_selected` + `previous_same_symbol_selected`；`MatchList` 作 view，全部视觉用 tag 表达（绕开 tkinter 原生 selection 避免色冲突）；`draw_breakouts_live_mode` 扩为 4 级独立 scatter 组，前三级挂 picker。

**Tech Stack:** tkinter ttk.Treeview (tag_configure), matplotlib Agg backend (scatter picker + pick_event), pytest。

> **POST-IMPLEMENTATION NOTES (added 2026-04-15):**
>
> Mid-implementation, the `previous_same_symbol_selected` concept was removed
> based on user feedback. The shipped feature uses a simpler 3-state row model:
> - `row_current` (slate-blue `#4F6D8C` bg, white fg) — replaces the planned depth-blue
> - `row_companion` (light blue `#CFE2F3` bg, black fg)
> - default (no state tag)
>
> See commits c65f0e7, 5a20a05, 51afb63 for the removal.
> Late color iterations: 8a5d47f, caa1b0c, 6f9b9de.
> Current code is the source of truth; below tasks reflect the original plan.

**Design Reference:** `docs/research/live_ui_same_symbol_selection.md`（agent team 产出）

---

## Pre-flight

- [ ] **Check clean working tree**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git status --short
```

工作树当前有未提交改动（markers.py / canvas_manager.py / test_draw_breakouts_live_mode.py / system_outline.md / 未跟踪 live.md / tooltip_anchor.py / docs/research/）。这些是之前 live UI 相关 WIP + 本次设计产出，与本 plan 的改动方向一致但不冲突。开始前先把设计文档 + WIP 单独提交掉，隔离 baseline：

```bash
git add docs/research/live_ui_same_symbol_selection.md
git commit -m "docs: add same-symbol selection sync design"
```

其余 WIP 根据其是否已完成决定 commit 或 stash；不要带脏工作树进入 Task 1。

- [ ] **Verify test baseline passes**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest BreakoutStrategy/live/tests/ BreakoutStrategy/UI/charts/ -x -q
```

Expected: 全部绿。若有失败，先修现有测试再开始。

---

## Task 1: AppState 新字段

**Files:**
- Modify: `BreakoutStrategy/live/state.py`

**Context:** 把原 `selected` 字段改名 `current_selected`，新增 `previous_same_symbol_selected`。同步更新所有读取方。

- [ ] **Step 1: 修改 state.py**

完全替换文件内容：

```python
"""实盘 UI 的应用状态。"""

from dataclasses import dataclass, field

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


@dataclass
class AppState:
    items: list[MatchedBreakout] = field(default_factory=list)
    current_selected: MatchedBreakout | None = None
    previous_same_symbol_selected: MatchedBreakout | None = None
    last_scan_date: str = ""
    last_scan_bar_date: str = ""
```

- [ ] **Step 2: 更新 app.py 对 state.selected 的引用**

```bash
grep -n "state.selected\|self.state.selected" BreakoutStrategy/live/app.py
```

每处 `self.state.selected = item` 改为 `self.state.current_selected = item`；每处 `self.state.selected` 读也改为 `self.state.current_selected`。Task 6 会进一步重构，此处只做字面量替换保持可运行。

- [ ] **Step 3: 跑 import-level 冒烟**

```bash
uv run python -c "from BreakoutStrategy.live.state import AppState; s=AppState(); print(s.current_selected, s.previous_same_symbol_selected)"
```

Expected: `None None`

- [ ] **Step 4: 运行 live UI smoke（人工）**

```bash
uv run python -m BreakoutStrategy.live
```

Expected: 窗口正常打开，列表可点击、能渲染图表（行为和之前完全一致——本 task 是纯字段重命名）。关闭窗口。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/live/state.py BreakoutStrategy/live/app.py
git commit -m "refactor(live): rename state.selected to current_selected + add previous_same_symbol_selected"
```

---

## Task 2: LiveApp._update_selection 状态转移（测试先行）

**Files:**
- Create: `BreakoutStrategy/live/tests/test_selection_transition.py`
- Modify: `BreakoutStrategy/live/app.py`（新增方法）

**Context:** 把选中状态转移从 `_on_item_selected` 抽出到纯函数 `_update_selection`，便于单元测试。规则：
- new=None → current=None, previous=None
- new.symbol == old.symbol 且 new ≠ old → previous=old, current=new
- 其他（首次选 / 换股票） → previous=None, current=new

- [ ] **Step 1: 写测试**

文件 `BreakoutStrategy/live/tests/test_selection_transition.py`：

```python
"""Unit tests for LiveApp._update_selection state transition logic.

Tests the pure state-machine portion only; no Tk/chart wiring here.
"""
from dataclasses import dataclass
from typing import Any

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.live.state import AppState


def _mb(symbol: str, date: str) -> MatchedBreakout:
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=date,
        breakout_price=1.0,
        factors={},
        sentiment_score=None,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": 0},
        raw_peaks=[],
    )


class _StubApp:
    """Isolate _update_selection logic from LiveApp's Tk dependencies."""
    def __init__(self):
        self.state = AppState()
        self.rendered = 0

    def _render_selection(self):
        self.rendered += 1

    # The function under test is imported & bound below.


def test_update_selection_to_none_clears_both():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    app.state.current_selected = _mb("AAPL", "2026-04-01")
    app.state.previous_same_symbol_selected = _mb("AAPL", "2026-03-15")

    LiveApp._update_selection(app, None)

    assert app.state.current_selected is None
    assert app.state.previous_same_symbol_selected is None
    assert app.rendered == 1


def test_update_selection_first_click_sets_current_no_previous():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    item = _mb("AAPL", "2026-04-01")

    LiveApp._update_selection(app, item)

    assert app.state.current_selected is item
    assert app.state.previous_same_symbol_selected is None


def test_update_selection_same_symbol_promotes_previous():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    first = _mb("AAPL", "2026-04-01")
    second = _mb("AAPL", "2026-03-15")
    app.state.current_selected = first

    LiveApp._update_selection(app, second)

    assert app.state.current_selected is second
    assert app.state.previous_same_symbol_selected is first


def test_update_selection_different_symbol_clears_previous():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    old = _mb("AAPL", "2026-04-01")
    new = _mb("MSFT", "2026-04-02")
    app.state.current_selected = old
    app.state.previous_same_symbol_selected = _mb("AAPL", "2026-03-15")

    LiveApp._update_selection(app, new)

    assert app.state.current_selected is new
    assert app.state.previous_same_symbol_selected is None


def test_update_selection_same_item_idempotent():
    """Selecting the already-current item keeps state stable, no new previous."""
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp()
    item = _mb("AAPL", "2026-04-01")
    app.state.current_selected = item

    LiveApp._update_selection(app, item)

    assert app.state.current_selected is item
    assert app.state.previous_same_symbol_selected is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_selection_transition.py -v
```

Expected: 5 个 FAIL（AttributeError: LiveApp has no `_update_selection`）。

- [ ] **Step 3: 在 app.py 添加 `_update_selection` 方法**

在 `LiveApp` 类里，紧跟 `_on_pipeline_error` 之后（`# ---------- 交互回调 ----------` 注释之前）加入：

```python
    # ---------- 选中状态转移 ----------

    def _update_selection(self, new: MatchedBreakout | None) -> None:
        """Core state transition. Call from both list-click and chart-pick paths.

        Rules:
        - new is None → current=None, previous=None
        - same symbol and new != old → previous=old, current=new
        - different symbol or first click → previous=None, current=new
        """
        old = self.state.current_selected
        if new is None:
            self.state.current_selected = None
            self.state.previous_same_symbol_selected = None
        elif old is not None and old.symbol == new.symbol and old is not new:
            self.state.previous_same_symbol_selected = old
            self.state.current_selected = new
        else:
            self.state.previous_same_symbol_selected = None
            self.state.current_selected = new
        self._render_selection()

    def _render_selection(self) -> None:
        """Stub for now; Task 11 wires this to MatchList + chart rebuild."""
        pass
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_selection_transition.py -v
```

Expected: 5 PASS。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/live/app.py BreakoutStrategy/live/tests/test_selection_transition.py
git commit -m "feat(live): add _update_selection state transition logic"
```

---

## Task 3: MatchList 回调签名重构 + 新 API：get_visible_items / get_visible_bo_indices

**Files:**
- Modify: `BreakoutStrategy/live/panels/match_list.py`
- Create/Modify: `BreakoutStrategy/live/tests/test_match_list_visible_api.py`

**Context:** 
- `on_select` 回调现在在两处触发：用户点击行、filter/排序刷新（用 None 通知"选中消失"）。后者语义混淆，需抽掉，只保留"真的点击"。
- 新 API `get_visible_items()`、`get_visible_bo_indices(symbol)` 让 LiveApp 可查当前可见的同股票 BO 索引，用于图表 4 级分类。

- [ ] **Step 1: 写新 API 测试**

文件 `BreakoutStrategy/live/tests/test_match_list_visible_api.py`：

```python
"""Tests for MatchList visible-items / bo-indices accessors."""
from datetime import date, timedelta

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _mb(symbol, bo_index, days_ago, price=5.0, score=0.0):
    today = date.today()
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=(today - timedelta(days=days_ago)).isoformat(),
        breakout_price=price,
        factors={},
        sentiment_score=score,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": bo_index},
        raw_peaks=[],
        all_stock_breakouts=[],
        all_matched_bo_chart_indices=[bo_index],
    )


@pytest.fixture
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_get_visible_items_returns_filtered_subset(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 20, days_ago=30),   # 超出 default 2 weeks
        _mb("MSFT", 15, days_ago=5),
    ])
    visible = ml.get_visible_items()
    # default weeks=2 → cutoff=14 天前，30 天前的被过滤
    assert len(visible) == 2
    symbols = {it.symbol for it in visible}
    assert symbols == {"AAPL", "MSFT"}


def test_get_visible_bo_indices_same_symbol(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 20, days_ago=5),
        _mb("MSFT", 15, days_ago=5),
    ])
    assert ml.get_visible_bo_indices("AAPL") == {10, 20}
    assert ml.get_visible_bo_indices("MSFT") == {15}
    assert ml.get_visible_bo_indices("GOOG") == set()


def test_get_visible_bo_indices_excludes_filtered(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    ml.set_items([
        _mb("AAPL", 10, days_ago=3),
        _mb("AAPL", 99, days_ago=60),  # 被 date filter 过滤
    ])
    assert ml.get_visible_bo_indices("AAPL") == {10}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visible_api.py -v
```

Expected: 3 FAIL（`on_row_selected` 参数未知 或 `get_visible_items` 未定义）。

- [ ] **Step 3: 重命名 MatchList 构造参数**

`BreakoutStrategy/live/panels/match_list.py` 第 27-38 行构造签名改为：

```python
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
```

- [ ] **Step 4: 重写回调触发点**

把 `_on_tree_select` 第 368-375 行重写——**只在用户真的选中某行时**触发，且传非 None 的 item：

```python
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
```

把 `_refresh_visible` 第 417 行的 `self._on_select(None)` **整行删除**——清空决策现在上移到 LiveApp（Task 13 实现）：

```python
        # 过滤/排序改变后，之前的选中行已消失；通知订阅者 filter 已变化
        # （LiveApp 会在 on_filter_changed 回调里决定是否清空 state.current_selected）
        if self._on_filter_changed is not None:
            self._on_filter_changed()
```

删除原来的 `self._on_select(None)` 行。

把 `clear` 方法（第 395-400 行）改为不再调用 `_on_select`：

```python
    def clear(self) -> None:
        self._all_items = []
        self._visible_items = []
        for iid in self.tree.get_children():
            self.tree.delete(iid)
```

（清空 detail panel 等责任移交 LiveApp）

- [ ] **Step 5: 加 get_visible_items + get_visible_bo_indices**

在 `# ---------- 数据接口 ----------` section（第 389 行附近）之后加入：

```python
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
```

- [ ] **Step 6: 更新 app.py 对 on_select 的引用**

`BreakoutStrategy/live/app.py` 约 70-76 行：

```python
        self.match_list = MatchList(
            main_paned,
            on_row_selected=self._on_item_selected,   # 旧 _on_item_selected 仍存在
            scan_window_days=self.config.scan_window_days,
            on_filter_changed=self._on_filter_changed,
        )
```

暂不重命名 `_on_item_selected`（Task 11 统一改）。但要处理旧签名允许 `item=None` 的写法——`_on_item_selected` 现在保证被调用时 item 非 None，头部的 `if item is None: return` 分支变成死代码但先留着，Task 11 一并清理。

- [ ] **Step 7: 更新现有 test_match_list_filter.py 的构造调用**

`BreakoutStrategy/live/tests/test_match_list_filter.py` 每处 `on_select=lambda _: None` 改为 `on_row_selected=lambda _: None`（共 3 处）：

```python
    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
```

- [ ] **Step 8: 跑全部相关测试**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_filter.py BreakoutStrategy/live/tests/test_match_list_visible_api.py -v
```

Expected: 全部 PASS。

- [ ] **Step 9: Commit**

```bash
git add BreakoutStrategy/live/panels/match_list.py BreakoutStrategy/live/app.py BreakoutStrategy/live/tests/
git commit -m "refactor(live): MatchList on_row_selected callback + get_visible_* APIs"
```

---

## Task 4: MatchList apply_selection_visual + 4 态 tag 配置

**Files:**
- Modify: `BreakoutStrategy/live/panels/match_list.py`
- Create: `BreakoutStrategy/live/tests/test_match_list_visual.py`

**Context:** 核心视觉层：用 tag 同时展现 current/previous/companion/default 4 态。tag 顺序 `(color_tag, state_tag)`，后者覆盖前者 foreground/background。

- [ ] **Step 1: 写测试**

文件 `BreakoutStrategy/live/tests/test_match_list_visual.py`：

```python
"""Tests for MatchList.apply_selection_visual 4-state row tagging."""
from datetime import date, timedelta

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout


def _mb(symbol, bo_index, days_ago=3):
    today = date.today()
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=(today - timedelta(days=days_ago)).isoformat(),
        breakout_price=5.0,
        factors={},
        sentiment_score=0.0,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": bo_index},
        raw_peaks=[],
        all_stock_breakouts=[],
        all_matched_bo_chart_indices=[bo_index],
    )


@pytest.fixture
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def _row_tags(ml, item):
    for iid in ml.tree.get_children():
        idx = ml.tree.index(iid)
        if ml._visible_items[idx] is item:
            return set(ml.tree.item(iid, "tags"))
    return None


def test_apply_visual_no_selection_no_state_tag(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    items = [_mb("AAPL", 10), _mb("AAPL", 20), _mb("MSFT", 15)]
    ml.set_items(items)
    ml.apply_selection_visual(current=None, previous=None)

    for it in items:
        tags = _row_tags(ml, it)
        assert "row_current" not in tags
        assert "row_previous" not in tags
        assert "row_companion" not in tags


def test_apply_visual_current_marks_current_row(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    items = [a1, _mb("AAPL", 20), _mb("MSFT", 15)]
    ml.set_items(items)
    ml.apply_selection_visual(current=a1, previous=None)

    assert "row_current" in _row_tags(ml, a1)


def test_apply_visual_same_symbol_siblings_become_companion(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    m1 = _mb("MSFT", 15)
    ml.set_items([a1, a2, m1])
    ml.apply_selection_visual(current=a1, previous=None)

    assert "row_current" in _row_tags(ml, a1)
    assert "row_companion" in _row_tags(ml, a2)
    # Different symbol stays plain
    t = _row_tags(ml, m1)
    assert "row_current" not in t
    assert "row_companion" not in t
    assert "row_previous" not in t


def test_apply_visual_previous_marks_previous_row(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    a3 = _mb("AAPL", 30, days_ago=5)
    ml.set_items([a1, a2, a3])
    # current=a2, previous=a1 → a3 应为 companion
    ml.apply_selection_visual(current=a2, previous=a1)

    assert "row_current" in _row_tags(ml, a2)
    assert "row_previous" in _row_tags(ml, a1)
    assert "row_companion" in _row_tags(ml, a3)


def test_apply_visual_color_tags_preserved(tk_root):
    """状态 tag 叠加在原 pos/neg/neu/na 颜色 tag 上，不能替换掉。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a1.sentiment_score = 0.5  # → pos tag
    ml.set_items([a1])
    ml.apply_selection_visual(current=a1, previous=None)

    tags = _row_tags(ml, a1)
    assert "pos" in tags
    assert "row_current" in tags
    # row_current 应该在 pos 之后，以保证 foreground 被覆盖
    tag_list = list(ml.tree.item(ml.tree.get_children()[0], "tags"))
    assert tag_list.index("pos") < tag_list.index("row_current")


def test_apply_visual_rerender_cleans_stale_state(tk_root):
    """二次调用要能清掉上一次的 state tag。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    ml.set_items([a1, a2])
    ml.apply_selection_visual(current=a1, previous=None)
    assert "row_current" in _row_tags(ml, a1)

    ml.apply_selection_visual(current=a2, previous=a1)
    # a1 不应再带 row_current，只剩 row_previous
    t1 = _row_tags(ml, a1)
    assert "row_current" not in t1
    assert "row_previous" in t1
    assert "row_current" in _row_tags(ml, a2)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py -v
```

Expected: 6 FAIL（`apply_selection_visual` 未定义）。

- [ ] **Step 3: 添加 tag_configure**

`BreakoutStrategy/live/panels/match_list.py` 的 `_build_treeview`，在现有 `tag_configure` 块（约第 328-335 行）之后加入：

```python
        # 选中状态 tag：放在颜色 tag 之后应用，覆盖 foreground。
        # 背景色 companion=浅蓝、previous=深绿、current=深蓝。
        self.tree.tag_configure("row_companion", background="#CFE2F3", foreground="#000000")
        self.tree.tag_configure("row_previous", background="#2E7D32", foreground="#FFFFFF")
        self.tree.tag_configure("row_current", background="#1565C0", foreground="#FFFFFF")
```

- [ ] **Step 4: 加 apply_selection_visual 方法**

在 `# ---------- 数据接口 ----------` section 的 `set_items` 之前加入：

```python
    def apply_selection_visual(
        self,
        current: "MatchedBreakout | None",
        previous: "MatchedBreakout | None",
    ) -> None:
        """按 current/previous 更新每行的状态 tag。

        规则：
        - current 行: row_current
        - previous 行（如在 visible）: row_previous
        - 与 current 同 symbol 且非 current/previous: row_companion
        - 其他: 无状态 tag

        tag 顺序为 (color_tag, state_tag)，后者在前者之后，利用 Tk 的 tag
        优先级把 foreground 覆盖为白/黑以保证可读。
        """
        current_key = (current.symbol, current.breakout_date) if current else None
        previous_key = (previous.symbol, previous.breakout_date) if previous else None
        current_symbol = current.symbol if current else None

        for iid in self.tree.get_children():
            idx = self.tree.index(iid)
            it = self._visible_items[idx]
            key = (it.symbol, it.breakout_date)
            base_tag = self._row_tag(it)  # "pos"/"neg"/"neu"/"na"

            if key == current_key:
                state_tag = "row_current"
            elif key == previous_key:
                state_tag = "row_previous"
            elif current_symbol is not None and it.symbol == current_symbol:
                state_tag = "row_companion"
            else:
                state_tag = None

            new_tags = (base_tag,) if state_tag is None else (base_tag, state_tag)
            self.tree.item(iid, tags=new_tags)
```

- [ ] **Step 5: 跑测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py -v
```

Expected: 6 PASS。

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/live/panels/match_list.py BreakoutStrategy/live/tests/test_match_list_visual.py
git commit -m "feat(live): MatchList.apply_selection_visual 4-state row tags"
```

---

## Task 5: MatchList.select_item + `_suppress_tree_select` 环路抑制

**Files:**
- Modify: `BreakoutStrategy/live/panels/match_list.py`
- Modify: `BreakoutStrategy/live/tests/test_match_list_visual.py`（追加测试）

**Context:** 图表 pick 反向选中要调 `match_list.select_item(item)`——需 scroll 到该行并触发 `_on_row_selected`，但要防止由 `tree.see()` 或 `selection_set` 间接触发的 `<<TreeviewSelect>>` 再次回调导致环路。

- [ ] **Step 1: 追加测试**

`BreakoutStrategy/live/tests/test_match_list_visual.py` 末尾追加：

```python
def test_select_item_triggers_on_row_selected_once(tk_root):
    """select_item 触发一次回调且不因内部 selection 操作产生重入。"""
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    ml.set_items([a1, a2])

    ml.select_item(a1)
    tk_root.update()   # flush <<TreeviewSelect>> events

    assert calls == [a1]


def test_select_item_scrolls_target_into_view(tk_root):
    """select_item 必须调 tree.see 让目标行可见。"""
    from BreakoutStrategy.live.panels.match_list import MatchList
    from unittest.mock import patch

    ml = MatchList(tk_root, on_row_selected=lambda _: None, scan_window_days=90)
    a1 = _mb("AAPL", 10)
    ml.set_items([a1])

    with patch.object(ml.tree, "see") as mock_see:
        ml.select_item(a1)
        assert mock_see.called


def test_select_item_unknown_item_is_noop(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    ml.set_items([a1])

    ghost = _mb("GOOG", 99)
    ml.select_item(ghost)  # 不在 visible 里
    tk_root.update()

    assert calls == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py::test_select_item_triggers_on_row_selected_once -v
```

Expected: FAIL（`select_item` 未定义）。

- [ ] **Step 3: 实现 select_item**

在 `apply_selection_visual` 之后加入：

```python
    def select_item(self, item: "MatchedBreakout") -> None:
        """从外部（如图表 pick）同步选中到 item，等价于模拟用户点击该行。

        过程：
        1. 按 (symbol, breakout_date) 定位 iid（不在 visible 则 no-op）
        2. tree.see(iid) 滚动到可见
        3. 直接调 on_row_selected(item) 走正常状态转移
        不使用 tree.selection_set()——本面板走全 tag 驱动的视觉模型，不依赖
        原生 selection；设 selection 反而会引入 <<TreeviewSelect>> 环路。
        """
        key = (item.symbol, item.breakout_date)
        for iid in self.tree.get_children():
            idx = self.tree.index(iid)
            it = self._visible_items[idx]
            if (it.symbol, it.breakout_date) == key:
                self.tree.see(iid)
                self._on_row_selected(item)
                return
```

注：因为不用 `selection_set`，`_suppress_tree_select` flag 目前不需要启用；但 `_on_tree_select` 里已经加了 flag 检查（Task 3 Step 4），留作未来若需要通过 selection 触发时的预备。

- [ ] **Step 4: 跑测试**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py -v
```

Expected: 9 PASS（6 原有 + 3 新增）。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/live/panels/match_list.py BreakoutStrategy/live/tests/test_match_list_visual.py
git commit -m "feat(live): MatchList.select_item for reverse selection from chart"
```

---

## Task 6: MatchList 键盘导航 ↑↓

**Files:**
- Modify: `BreakoutStrategy/live/panels/match_list.py`
- Modify: `BreakoutStrategy/live/tests/test_match_list_visual.py`

**Context:** 因 Task 3 Step 4 在 `_on_tree_select` 里 selection_remove，tkinter 原生 ↑↓ 导航失效（没有真选中 anchor）。需绑 `<Up>/<Down>/<Home>/<End>` 到"调用 on_row_selected(visible_items[new_idx])"。

- [ ] **Step 1: 追加测试**

`test_match_list_visual.py` 末尾：

```python
def test_keyboard_down_selects_next_visible(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    a1 = _mb("AAPL", 10)
    a2 = _mb("AAPL", 20)
    a3 = _mb("MSFT", 30)
    ml.set_items([a1, a2, a3])

    # 无当前选中 → 按 Down 选第一行
    ml._handle_key_navigate(direction=1, current=None)
    assert calls[-1] is ml._visible_items[0]

    # 当前选中第 0 行 → 按 Down 选第 1 行
    ml._handle_key_navigate(direction=1, current=ml._visible_items[0])
    assert calls[-1] is ml._visible_items[1]


def test_keyboard_up_at_top_stays(tk_root):
    from BreakoutStrategy.live.panels.match_list import MatchList

    calls = []
    ml = MatchList(tk_root, on_row_selected=lambda it: calls.append(it), scan_window_days=90)
    ml.set_items([_mb("AAPL", 10), _mb("AAPL", 20)])

    # 当前第 0 行，按 Up 应保持在第 0 行（不 wrap）
    first = ml._visible_items[0]
    ml._handle_key_navigate(direction=-1, current=first)
    assert calls[-1] is first
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py::test_keyboard_down_selects_next_visible -v
```

Expected: FAIL（`_handle_key_navigate` 未定义）。

- [ ] **Step 3: 在 `_build_treeview` 末尾添加键盘绑定**

在 `_build_treeview` 的末尾（`self._update_heading_indicators()` 之前）加入：

```python
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
```

- [ ] **Step 4: 加 `_handle_key_navigate` 和 `_handle_key_navigate_to` 方法**

在 `select_item` 之后：

```python
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
            try:
                cur_idx = self._visible_items.index(current)
            except ValueError:
                target_idx = 0
            else:
                target_idx = max(0, min(len(self._visible_items) - 1, cur_idx + direction))
        self._on_row_selected(self._visible_items[target_idx])
        return "break"

    def _handle_key_navigate_to(self, idx: int) -> str | None:
        """Home/End 直跳首/尾。idx=-1 表示末尾。"""
        if not self._visible_items:
            return "break"
        if idx < 0:
            idx = len(self._visible_items) - 1
        self._on_row_selected(self._visible_items[idx])
        return "break"
```

- [ ] **Step 5: 跑测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_match_list_visual.py -v
```

Expected: 11 PASS。

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/live/panels/match_list.py BreakoutStrategy/live/tests/test_match_list_visual.py
git commit -m "feat(live): MatchList keyboard nav (↑↓ Home/End) post selection_remove"
```

---

## Task 7: markers._classify_bo 扩为 4 分支

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py`
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_bo_classifier.py`

**Context:** 从 3 级（current/matched/plain）扩为 4 级（current/visible/filtered_out/plain）。`visible` 和 `filtered_out` 都是 matched，区别在是否被 MatchList filter 过滤掉。

- [ ] **Step 1: 更新测试**

`test_bo_classifier.py` 完全替换为：

```python
"""Unit tests for _classify_bo BO style classifier (4-tier)."""
from BreakoutStrategy.UI.charts.components.markers import _classify_bo


def test_current_wins_over_everything():
    assert _classify_bo(5, current=5, visible={5, 7}, filtered_out={3}) == "current"


def test_visible_matched_not_current():
    assert _classify_bo(7, current=5, visible={5, 7}, filtered_out={3}) == "visible"


def test_filtered_out_matched_not_current():
    assert _classify_bo(3, current=5, visible={5, 7}, filtered_out={3}) == "filtered_out"


def test_plain_when_not_in_any_matched():
    assert _classify_bo(99, current=5, visible={5, 7}, filtered_out={3}) == "plain"


def test_no_current_selected_falls_to_visible_or_filtered():
    assert _classify_bo(7, current=None, visible={7}, filtered_out=set()) == "visible"
    assert _classify_bo(3, current=None, visible=set(), filtered_out={3}) == "filtered_out"
    assert _classify_bo(99, current=None, visible=set(), filtered_out=set()) == "plain"


def test_visible_takes_precedence_over_filtered_out():
    """sanity: 同一 idx 只会归一处，但若 visible 和 filtered_out 都含它（理论不该
    发生），visible 优先——它更能代表"列表里能看到"的状态。"""
    assert _classify_bo(7, current=None, visible={7}, filtered_out={7}) == "visible"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/components/tests/test_bo_classifier.py -v
```

Expected: 全 FAIL（函数签名不匹配）。

- [ ] **Step 3: 改 `_classify_bo`**

`BreakoutStrategy/UI/charts/components/markers.py` 第 7-19 行整体替换：

```python
def _classify_bo(
    idx: int,
    current: int | None,
    visible: set[int],
    filtered_out: set[int],
) -> str:
    """Classify a BO into one of 4 live-UI tiers.

    Args:
        idx: This BO's chart-df index.
        current: Currently-selected BO's chart-df index (or None).
        visible: matched BO indices that appear in the MatchList right now.
        filtered_out: matched BO indices that are hidden by MatchList filter.

    Returns one of: "current" | "visible" | "filtered_out" | "plain".
    """
    if current is not None and idx == current:
        return "current"
    if idx in visible:
        return "visible"
    if idx in filtered_out:
        return "filtered_out"
    return "plain"
```

- [ ] **Step 4: 跑测试**

```bash
uv run pytest BreakoutStrategy/UI/charts/components/tests/test_bo_classifier.py -v
```

Expected: 6 PASS。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py BreakoutStrategy/UI/charts/components/tests/test_bo_classifier.py
git commit -m "feat(chart): _classify_bo 4-tier (current/visible/filtered_out/plain)"
```

---

## Task 8: draw_breakouts_live_mode 4 组 scatter + picker

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py`
- Modify: `BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py`
- Modify: `BreakoutStrategy/UI/styles.py`（追加颜色）

**Context:** 4 级各自一组 scatter（zorder 10→13）。current/visible/filtered_out 设 picker=True 并在 artist 上挂 `bo_chart_indices` 列表。plain 不设 picker。

- [ ] **Step 1: styles.py 追加颜色**

`BreakoutStrategy/UI/styles.py` 的 `CHART_COLORS` 里找到 `"bo_marker_current": "#2E7D32"` 一行，替换这一行并在其后追加：

```python
    "bo_marker_current": "#1565C0",    # 当前选中 matched BO（深蓝，live mode 专用）
    "bo_marker_visible": "#64B5F6",    # 通过 filter 但未选中 matched BO（浅蓝）
    "bo_marker_filtered_out": "#9E9E9E",  # 被 filter 过滤掉的 matched BO（灰）
```

- [ ] **Step 2: 重写 draw_breakouts_live_mode**

完全替换 `markers.py` 的 `draw_breakouts_live_mode` 方法（第 270-376 行）：

```python
    @staticmethod
    def draw_breakouts_live_mode(
        ax,
        df: pd.DataFrame,
        breakouts: list,
        current_bo_index,
        visible_matched_indices: set[int] | None = None,
        filtered_out_matched_indices: set[int] | None = None,
        peaks: list = None,
        colors: dict = None,
    ):
        """Live UI 专用：按 4 级（current/visible/filtered_out/plain）画圆圈 marker + 蓝字 label。

        - current BO：深蓝实心、zorder=13、picker
        - visible matched BO：浅蓝实心、zorder=12、picker
        - filtered_out matched BO：灰实心 alpha=0.7、zorder=11、picker（点击仅提示）
        - plain BO：浅蓝空心、zorder=10、无 picker

        每组独立 `ax.scatter`，以便 pick_event 通过 artist 区分归属。三组可点击
        scatter 在 artist 上挂 `.bo_chart_indices` 列表，pick 回调用 event.ind[0]
        反查。label [broken_peak_ids] 共用一次循环独立画。
        """
        if not breakouts:
            return

        visible_matched_indices = visible_matched_indices or set()
        filtered_out_matched_indices = filtered_out_matched_indices or set()
        colors = colors or {}
        color_current = colors.get("bo_marker_current", "#1565C0")
        color_visible = colors.get("bo_marker_visible", "#64B5F6")
        color_filtered = colors.get("bo_marker_filtered_out", "#9E9E9E")
        text_bg_color = colors.get("breakout_text_bg", "#FFFFFF")

        # y 偏移计算（与 draw_breakouts 保持一致）
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"
        has_high = high_col in df.columns
        has_low = low_col in df.columns

        ylim = ax.get_ylim()
        if ylim != (0.0, 1.0) and ylim[1] > ylim[0]:
            price_range = ylim[1] - ylim[0]
        elif has_high and has_low:
            price_range = (df[high_col].max() - df[low_col].min()) * 1.1
        else:
            price_range = df.iloc[0]["close"] * 0.2 if not df.empty else 1.0
        if price_range == 0:
            price_range = df[high_col].mean() * 0.1 if has_high else 1.0
        offset_unit = price_range * 0.02

        peak_indices = {p.index for p in peaks} if peaks else set()

        # 按 4 级分桶
        buckets: dict[str, list[tuple[int, float, float]]] = {
            "current": [], "visible": [], "filtered_out": [], "plain": [],
        }
        label_items: list[tuple[int, float, str, str]] = []

        for bo in breakouts:
            bo_x = bo.index
            base_price = (
                df.iloc[bo_x][high_col] if has_high and 0 <= bo_x < len(df) else bo.price
            )

            is_overlap = bo_x in peak_indices
            if is_overlap:
                label_y = base_price + offset_unit * 2.2
                marker_y = base_price + offset_unit * 4.0
            else:
                label_y = base_price + offset_unit * 0.6
                marker_y = base_price + offset_unit * 2.4

            tier = _classify_bo(
                bo_x, current_bo_index, visible_matched_indices, filtered_out_matched_indices,
            )
            buckets[tier].append((bo_x, marker_y, base_price))

            if hasattr(bo, "broken_peak_ids") and bo.broken_peak_ids:
                peak_ids_text = ",".join(map(str, bo.broken_peak_ids))
                label_items.append((bo_x, label_y, f"[{peak_ids_text}]", tier))

        # 画 4 组 scatter，zorder 逐级抬高，可点击三组挂属性
        def _draw_group(name, face, edge, zorder, pickable, alpha=1.0):
            pts = buckets[name]
            if not pts:
                return
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            idxs = [p[0] for p in pts]
            kwargs = dict(
                marker="o", s=400, facecolors=face, edgecolors=edge,
                linewidths=2, zorder=zorder, alpha=alpha,
            )
            if pickable:
                kwargs["picker"] = True
                kwargs["pickradius"] = 8
            sc = ax.scatter(xs, ys, **kwargs)
            # 所有组都挂，pick 回调只会对 pickable 的触发
            sc.bo_chart_indices = idxs
            sc.bo_tier = name
            return sc

        _draw_group("plain", "none", color_visible, zorder=10, pickable=False)
        _draw_group("filtered_out", color_filtered, color_filtered, zorder=11, pickable=True, alpha=0.7)
        _draw_group("visible", color_visible, color_visible, zorder=12, pickable=True)
        _draw_group("current", color_current, color_current, zorder=13, pickable=True)

        # 画 label（复用之前颜色：蓝色边框/字）
        label_color = color_visible
        for bo_x, label_y, text, _tier in label_items:
            ax.text(
                bo_x, label_y, text,
                fontsize=20, ha="center", va="bottom",
                color=label_color, weight="bold", zorder=10,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=text_bg_color, edgecolor=label_color,
                    linewidth=1.5, alpha=0.9,
                ),
            )
```

- [ ] **Step 3: 更新 test_draw_breakouts_live_mode.py**

文件里每个测试的调用 `matched_bo_indices=[...]` 改为新签名。完全替换整个文件：

```python
"""Unit tests for MarkerComponent.draw_breakouts_live_mode (4-tier)."""
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from BreakoutStrategy.UI.charts.components.markers import MarkerComponent


@pytest.fixture
def axes_with_df():
    fig, ax = plt.subplots(figsize=(6, 4))
    df = pd.DataFrame({
        "open": [1.0, 1.1, 1.2, 1.3, 1.4],
        "high": [1.1, 1.2, 1.3, 1.4, 1.5],
        "low":  [0.9, 1.0, 1.1, 1.2, 1.3],
        "close":[1.05,1.15,1.25,1.35,1.45],
    })
    ax.plot(range(5), df["close"])
    ax.set_ylim(0.8, 1.6)
    yield ax, df
    plt.close(fig)


def _make_bo(index, broken_peak_ids):
    return SimpleNamespace(index=index, broken_peak_ids=broken_peak_ids, price=1.0)


_COLORS = {
    "bo_marker_current": "#1565C0",
    "bo_marker_visible": "#64B5F6",
    "bo_marker_filtered_out": "#9E9E9E",
    "breakout_marker": "#0000FF",   # legacy, kept for safety
    "breakout_text_bg": "#FFFFFF",
}


def _find_tier_scatter(ax, tier: str):
    for c in ax.collections:
        if getattr(c, "bo_tier", None) == tier:
            return c
    return None


def test_current_bo_drawn_in_current_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=2,
        visible_matched_indices={2},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "current")
    assert sc is not None
    face = sc.get_facecolor()
    assert face[0][0] == pytest.approx(0x15 / 255, abs=0.01)
    assert face[0][1] == pytest.approx(0x65 / 255, abs=0.01)
    assert face[0][2] == pytest.approx(0xC0 / 255, abs=0.01)


def test_visible_matched_drawn_in_visible_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={2, 100},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "visible")
    assert sc is not None
    assert _find_tier_scatter(ax, "current") is None


def test_filtered_out_drawn_in_filtered_group(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices=set(),
        filtered_out_matched_indices={2},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "filtered_out")
    assert sc is not None
    # 灰色 alpha 0.7
    face = sc.get_facecolor()
    assert face[0][3] == pytest.approx(0.7, abs=0.01)


def test_plain_drawn_hollow(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7])],
        current_bo_index=100,
        visible_matched_indices={100},
        colors=_COLORS,
    )
    sc = _find_tier_scatter(ax, "plain")
    assert sc is not None
    assert len(sc.get_facecolor()) == 0   # facecolor="none" 返回空数组


def test_pickable_groups_have_picker_and_indices(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [7]), _make_bo(3, [8])],
        current_bo_index=2,
        visible_matched_indices={2, 3},
        colors=_COLORS,
    )
    current = _find_tier_scatter(ax, "current")
    visible = _find_tier_scatter(ax, "visible")
    assert current.get_picker() is not None   # True / pickradius
    assert visible.get_picker() is not None
    assert current.bo_chart_indices == [2]
    assert visible.bo_chart_indices == [3]


def test_plain_group_has_no_picker(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [])],
        current_bo_index=100,
        visible_matched_indices={100},
        colors=_COLORS,
    )
    plain = _find_tier_scatter(ax, "plain")
    # matplotlib 的 picker=None → get_picker() 返回 None
    assert plain.get_picker() is None


def test_label_still_drawn(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(2, [3, 5, 8])],
        current_bo_index=2,
        visible_matched_indices={2},
        colors=_COLORS,
    )
    texts = [t.get_text() for t in ax.texts]
    assert any("[3,5,8]" in t for t in texts)


def test_empty_noop(axes_with_df):
    ax, df = axes_with_df
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [], current_bo_index=None,
        visible_matched_indices=set(),
        colors=_COLORS,
    )
    assert len(ax.collections) == 0
    assert len(ax.texts) == 0


def test_overlap_stacks_above_peak(axes_with_df):
    ax, df = axes_with_df
    bo_idx = 2
    fake_peak = SimpleNamespace(index=bo_idx, price=1.2)
    MarkerComponent.draw_breakouts_live_mode(
        ax, df, [_make_bo(bo_idx, [7])],
        current_bo_index=bo_idx,
        visible_matched_indices={bo_idx},
        peaks=[fake_peak],
        colors=_COLORS,
    )
    # price_range=0.8 → offset_unit=0.016；base=df.iloc[2]["high"]=1.3
    # overlap 分支 marker_y=1.3+0.016*4=1.364, label_y=1.3+0.016*2.2=1.3352
    offset = 0.8 * 0.02
    expected_marker_y = 1.3 + offset * 4.0
    sc = _find_tier_scatter(ax, "current")
    marker_y = sc.get_offsets()[0][1]
    assert marker_y == pytest.approx(expected_marker_y, abs=1e-6)
```

- [ ] **Step 4: 跑测试**

```bash
uv run pytest BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py -v
```

Expected: 9 PASS。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py BreakoutStrategy/UI/charts/components/tests/test_draw_breakouts_live_mode.py BreakoutStrategy/UI/styles.py
git commit -m "feat(chart): draw_breakouts_live_mode 4-tier scatter groups with picker"
```

---

## Task 9: canvas_manager 接入新 display_options + pick_event

**Files:**
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py`
- Modify: `BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py`

**Context:** 
- `display_options` 新增 `visible_matched_indices`, `filtered_out_matched_indices`, `on_bo_picked`。
- canvas 侧 mpl_connect pick_event；回调解析 `event.artist.bo_chart_indices[event.ind[0]]` → 调 `on_bo_picked(bo_index)`。
- 幂等：每次 update_chart 前 disconnect 旧 cid。

- [ ] **Step 1: 追加测试**

`test_canvas_manager_live_mode.py` 末尾追加：

```python
def test_live_mode_passes_new_display_options_to_marker(tk_container, minimal_df):
    mgr = ChartCanvasManager(tk_container)
    captured = {}
    def fake_live(ax, df, breakouts, **kwargs):
        captured.update(kwargs)
    with patch.object(mgr.marker, "draw_breakouts_live_mode", side_effect=fake_live):
        mgr.update_chart(
            df=minimal_df,
            breakouts=[_fake_bo(10)],
            active_peaks=[], superseded_peaks=[],
            symbol="TEST",
            display_options={
                "live_mode": True,
                "current_bo_index": 10,
                "visible_matched_indices": {10, 15},
                "filtered_out_matched_indices": {20},
                "on_bo_picked": lambda _i: None,
            },
        )
    assert captured["current_bo_index"] == 10
    assert captured["visible_matched_indices"] == {10, 15}
    assert captured["filtered_out_matched_indices"] == {20}


def test_live_mode_pick_event_invokes_on_bo_picked(tk_container, minimal_df):
    """模拟 pick_event 触发，验证回调拿到正确的 bo_chart_index。"""
    from types import SimpleNamespace
    mgr = ChartCanvasManager(tk_container)
    received = []
    mgr.update_chart(
        df=minimal_df,
        breakouts=[_fake_bo(10), _fake_bo(12)],
        active_peaks=[], superseded_peaks=[],
        symbol="TEST",
        display_options={
            "live_mode": True,
            "current_bo_index": 10,
            "visible_matched_indices": {10, 12},
            "on_bo_picked": lambda i: received.append(i),
        },
    )
    # 找到某个可点击 scatter，伪造 pick_event
    target = None
    for c in mgr.fig.axes[0].collections:
        if getattr(c, "bo_tier", None) == "visible":
            target = c
            break
    assert target is not None
    fake_event = SimpleNamespace(artist=target, ind=[0])
    mgr._on_pick(fake_event)
    assert received == [target.bo_chart_indices[0]]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py -v
```

Expected: 新测试 FAIL（`on_bo_picked` 未转发；`_on_pick` 未定义）。

- [ ] **Step 3: 修改 canvas_manager 的 live_mode 分支**

定位到 `update_chart` 的 `if display_options.get("live_mode", False):` 分支（约 231 行），替换整个 if 块为：

```python
        # BO 绘制：live_mode=True 走新 4-tier 圆圈渲染；否则走 Dev UI 原路径
        if display_options.get("live_mode", False):
            self.marker.draw_breakouts_live_mode(
                ax_main,
                df,
                breakouts,
                current_bo_index=display_options.get("current_bo_index"),
                visible_matched_indices=display_options.get("visible_matched_indices", set()),
                filtered_out_matched_indices=display_options.get("filtered_out_matched_indices", set()),
                peaks=all_drawn_peaks,
                colors=colors,
            )
            # pick_event 连线；幂等：先 disconnect 上次的 cid
            self._on_bo_picked_callback = display_options.get("on_bo_picked")
            if getattr(self, "_pick_cid", None) is not None:
                try:
                    self.canvas.mpl_disconnect(self._pick_cid)
                except Exception:
                    pass
            self._pick_cid = self.canvas.mpl_connect("pick_event", self._on_pick)
        else:
            self.marker.draw_breakouts(
                ax_main,
                df,
                breakouts,
                highlight_multi_peak=True,
                peaks=all_drawn_peaks,
                colors=colors,
                show_score=show_bo_score,
            )
```

- [ ] **Step 4: 加 `_on_pick` 方法**

在 ChartCanvasManager 类任意合适位置（例如紧接 `update_chart` 之后），添加：

```python
    def _on_pick(self, event):
        """matplotlib pick_event handler：BO marker 点击反向同步到 MatchList。"""
        cb = getattr(self, "_on_bo_picked_callback", None)
        if cb is None:
            return
        artist = event.artist
        idxs = getattr(artist, "bo_chart_indices", None)
        if not idxs:
            return
        # event.ind 是被点中的点在 scatter offsets 里的索引
        for i in event.ind:
            if 0 <= i < len(idxs):
                cb(idxs[i])
                return
```

- [ ] **Step 5: 更新旧 test_canvas_manager_live_mode 里的第一个测试（test_live_mode_true_calls_live_mode_draw）**

它的 display_options 仍用 `matched_bo_indices=[10]`（旧签名），需改为新签名——只是保证 draw_breakouts_live_mode 被调用即可，不验证参数：

找到 `matched_bo_indices=[10]`（约第 61 行），替换为 `"visible_matched_indices": {10},`。

- [ ] **Step 6: 跑测试**

```bash
uv run pytest BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py -v
```

Expected: 5 PASS（3 原有 + 2 新增）。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/UI/charts/canvas_manager.py BreakoutStrategy/UI/charts/tests/test_canvas_manager_live_mode.py
git commit -m "feat(chart): canvas pick_event routing + 4-tier display_options"
```

---

## Task 10: LiveApp 整合 —— _rebuild_chart + _on_row_selected + _on_chart_bo_picked + _render_selection

**Files:**
- Modify: `BreakoutStrategy/live/app.py`

**Context:** 本 task 把之前的 stub `_render_selection` 真正连起来，并拆解旧 `_on_item_selected` 为：
- `_on_row_selected(item)` —— MatchList 回调入口，只调 `_update_selection`
- `_rebuild_chart()` —— 根据当前 state 绘图（原 `_on_item_selected` 下半段搬家）
- `_on_chart_bo_picked(bo_index)` —— 图表反向入口
- `_render_selection` —— 调 `apply_selection_visual` + `detail_panel.update_item` + `_rebuild_chart`

- [ ] **Step 1: 替换 `_on_item_selected` 为 `_on_row_selected`**

`BreakoutStrategy/live/app.py` 约 198 行的整个 `_on_item_selected` 方法删除，换为：

```python
    # ---------- 交互回调 ----------

    def _on_row_selected(self, item: MatchedBreakout) -> None:
        """MatchList 回调：用户真点击某行。直接走状态转移。"""
        self._update_selection(item)

    def _on_chart_bo_picked(self, bo_chart_index: int) -> None:
        """图表反向入口：点击 BO marker 后的回调。

        若 bo_chart_index 对应的 MatchedBreakout 在当前 visible items 里
        → 模拟列表点击；否则为 filtered_out 灰色 marker → 状态栏提示。
        """
        current = self.state.current_selected
        if current is None:
            return
        # 只在当前股票范围内解析
        for it in self.match_list.get_visible_items():
            if it.symbol == current.symbol and it.raw_breakout["index"] == bo_chart_index:
                self.match_list.select_item(it)   # 会回调 _on_row_selected
                return
        # 不在 visible → filtered_out 或 plain；只提示
        self.toolbar.set_status(
            f"BO {bo_chart_index} is hidden by current filter; adjust Date/Score to see it"
        )
```

同时替换 `_render_selection` 的 stub 为真实实现（替换 Task 2 里加的 `pass` 版本）：

```python
    def _render_selection(self) -> None:
        """把 state 变更推到两个 view：MatchList tag 高亮 + Chart 重绘 + Detail 面板。"""
        current = self.state.current_selected
        previous = self.state.previous_same_symbol_selected
        self.match_list.apply_selection_visual(current=current, previous=previous)
        self.detail_panel.update_item(current)
        self._rebuild_chart()
```

- [ ] **Step 2: 加 `_rebuild_chart` 方法**

在 `_on_chart_bo_picked` 之后加入：

```python
    def _rebuild_chart(self) -> None:
        """按 state 当前的 current_selected 重绘图表。无选中时清空图表。"""
        current = self.state.current_selected
        if current is None:
            self.chart.clear()
            return

        pkl_path = self.config.data_dir / f"{current.symbol}.pkl"
        if not pkl_path.exists():
            return
        try:
            df = pd.read_pickle(pkl_path)
        except Exception:
            return

        chart_active_peaks, chart_superseded_peaks, peaks_by_id = adapt_peaks(current.raw_peaks)
        raw_bos = current.all_stock_breakouts or [current.raw_breakout]
        all_chart_bos = [adapt_breakout(raw_bo, peaks_by_id) for raw_bo in raw_bos]

        # 4 级分类所需索引集
        visible_idx = self.match_list.get_visible_bo_indices(current.symbol)
        all_matched = set(current.all_matched_bo_chart_indices)
        filtered_out_idx = all_matched - visible_idx

        try:
            self.chart.update_chart(
                df=df,
                breakouts=all_chart_bos,
                active_peaks=chart_active_peaks,
                superseded_peaks=chart_superseded_peaks,
                symbol=current.symbol,
                display_options={
                    "live_mode": True,
                    "current_bo_index": current.raw_breakout["index"],
                    "visible_matched_indices": visible_idx,
                    "filtered_out_matched_indices": filtered_out_idx,
                    "on_bo_picked": self._on_chart_bo_picked,
                    "show_superseded_peaks": True,
                },
                initial_window_days=180,
                filter_cutoff_date=self.match_list.get_date_cutoff(),
            )
        except Exception as e:
            print(f"[LiveApp] Chart render failed: {e}", file=sys.stderr)
```

注：`self.chart.clear()` 方法需确认存在——若不存在则本 task 里补一个。

- [ ] **Step 3: 确认 ChartCanvasManager 有 clear 方法**

```bash
grep -n "def clear\|def _cleanup" BreakoutStrategy/UI/charts/canvas_manager.py
```

若只有 `_cleanup`（内部清理）没有 public `clear`，在 `ChartCanvasManager` 末尾加：

```python
    def clear(self) -> None:
        """清空图表（无选中时调用）。等价于 _cleanup 的 public wrapper。"""
        self._cleanup()
        if self.canvas is not None:
            self.canvas.draw_idle()
```

- [ ] **Step 4: 更新 MatchList 构造器里的回调名**

app.py `_build_ui` 约 70-76 行：
```python
        self.match_list = MatchList(
            main_paned,
            on_row_selected=self._on_row_selected,
            scan_window_days=self.config.scan_window_days,
            on_filter_changed=self._on_filter_changed,
        )
```
（Task 3 Step 6 已做了 on_select → on_row_selected 的 keyword 改动并指向旧 `_on_item_selected`；现在要指向新 `_on_row_selected`。）

- [ ] **Step 5: 启动 UI 手工冒烟**

```bash
uv run python -m BreakoutStrategy.live
```

Expected（人工验证）:
- 窗口正常打开
- 点击某一 matched row → 图表按 4 级画出 current 深蓝 + visible 浅蓝 + filtered_out 灰 + plain 空心
- 列表中该 symbol 其他 row 背景变浅蓝黑字
- 再点同股票另一 row → 新行深蓝白字，上一行深绿白字，其余同股票浅蓝
- 再点不同股票 row → previous 消失，current 更新

关闭窗口。

- [ ] **Step 6: 运行全量测试**

```bash
uv run pytest BreakoutStrategy/live/ BreakoutStrategy/UI/charts/ -q
```

Expected: 全绿。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/live/app.py BreakoutStrategy/UI/charts/canvas_manager.py
git commit -m "feat(live): wire _render_selection + _rebuild_chart + _on_chart_bo_picked"
```

---

## Task 11: _on_filter_changed 重构 —— current 失效检测 + previous 保留

**Files:**
- Modify: `BreakoutStrategy/live/app.py`
- Create: `BreakoutStrategy/live/tests/test_filter_consistency.py`

**Context:** 当 filter/sort 变化导致 current 不再 visible 时，LiveApp 需要清空 state（current 和 previous 都置空）。若 current 仍 visible，只需 `_render_selection` 重打 tag + 重绘。previous 即使被过滤掉也保留在 state 里（它只是视觉 hint，不一定要 visible；但若不可见，`apply_selection_visual` 自然不会打 tag）。

- [ ] **Step 1: 写测试**

文件 `BreakoutStrategy/live/tests/test_filter_consistency.py`：

```python
"""Tests for LiveApp._on_filter_changed current-selected invalidation."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from BreakoutStrategy.live.pipeline.results import MatchedBreakout
from BreakoutStrategy.live.state import AppState


def _mb(symbol, date, bo_index=0):
    return MatchedBreakout(
        symbol=symbol,
        breakout_date=date,
        breakout_price=1.0,
        factors={},
        sentiment_score=None,
        sentiment_category="analyzed",
        sentiment_summary=None,
        raw_breakout={"index": bo_index},
        raw_peaks=[],
    )


class _StubMatchList:
    def __init__(self, visible):
        self._visible = list(visible)

    def get_visible_items(self):
        return list(self._visible)

    def get_date_cutoff(self):
        from datetime import date
        return date.today()


class _StubApp:
    """Reuse enough of LiveApp for _on_filter_changed."""
    def __init__(self, visible):
        self.state = AppState()
        self.match_list = _StubMatchList(visible)
        self.chart = SimpleNamespace(update_filter_range=lambda *_a, **_k: None)
        self.detail_panel = SimpleNamespace(update_item=lambda *_a, **_k: None)
        self.rendered = 0
        self.cleared = 0
        self.rebuilt = 0

    def _render_selection(self):
        self.rendered += 1

    def _update_selection(self, new):
        # Copy of real logic (no Tk)
        old = self.state.current_selected
        if new is None:
            self.state.current_selected = None
            self.state.previous_same_symbol_selected = None
        elif old is not None and old.symbol == new.symbol and old is not new:
            self.state.previous_same_symbol_selected = old
            self.state.current_selected = new
        else:
            self.state.previous_same_symbol_selected = None
            self.state.current_selected = new
        self._render_selection()


def test_filter_changed_keeps_current_when_still_visible():
    from BreakoutStrategy.live.app import LiveApp
    a = _mb("AAPL", "2026-04-01")
    app = _StubApp(visible=[a])
    app.state.current_selected = a

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is a
    assert app.rendered >= 1


def test_filter_changed_clears_current_when_filtered_out():
    from BreakoutStrategy.live.app import LiveApp
    a = _mb("AAPL", "2026-04-01")
    app = _StubApp(visible=[])  # a 被过滤掉
    app.state.current_selected = a
    app.state.previous_same_symbol_selected = _mb("AAPL", "2026-03-15")

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is None
    assert app.state.previous_same_symbol_selected is None


def test_filter_changed_noop_when_nothing_selected():
    from BreakoutStrategy.live.app import LiveApp
    app = _StubApp(visible=[])

    LiveApp._on_filter_changed(app)

    assert app.state.current_selected is None
```

- [ ] **Step 2: 跑测试**

```bash
uv run pytest BreakoutStrategy/live/tests/test_filter_consistency.py -v
```

Expected: 可能 2 pass 1 fail——现有 `_on_filter_changed` 只调 `update_filter_range`，不校验 current。若测试表达方式不符，调整到能复现失败。

- [ ] **Step 3: 重写 `_on_filter_changed`**

`BreakoutStrategy/live/app.py` 末尾的 `_on_filter_changed` 替换为：

```python
    def _on_filter_changed(self) -> None:
        """MatchList 的 Date/Price/Score/sort 变化时调用。

        责任：
        1. 若 current_selected 被新 filter 过滤掉（不在 visible） → 清空 state
        2. 否则重绘视觉（iid 已重建，tag 需重打；图表 4 级分类也变了）
        3. 同步图表背景 filter range
        """
        current = self.state.current_selected
        if current is not None:
            visible = self.match_list.get_visible_items()
            still_visible = any(
                it.symbol == current.symbol and it.breakout_date == current.breakout_date
                for it in visible
            )
            if not still_visible:
                self._update_selection(None)
            else:
                self._render_selection()

        self.chart.update_filter_range(self.match_list.get_date_cutoff())
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest BreakoutStrategy/live/tests/test_filter_consistency.py -v
```

Expected: 3 PASS。

- [ ] **Step 5: 手工冒烟**

```bash
uv run python -m BreakoutStrategy.live
```

验证：
- 点击某 row → 选中 + 伴生高亮生效
- 把 Date filter Weeks 从 2 拉到 1（缩窄）
  - 若 current row 仍在 → 高亮保留，chart 4 级可能变（之前 visible 的同 symbol 可能变成 filtered_out 灰色）
  - 若 current row 被过滤掉 → 图表清空、detail 清空
- 把 Date 拉回 2 → 原 current 不会自动回来（符合规则）
- 切换排序列 → 高亮跟随

关闭。

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/live/app.py BreakoutStrategy/live/tests/test_filter_consistency.py
git commit -m "feat(live): _on_filter_changed invalidates stale current_selected"
```

---

## Task 12: 图表反向点击手工验证 + 灰色 marker 提示文案

**Files:**
- 无代码改动（纯 manual test）

**Context:** Task 9/10 已接通 pick 链路，但 picker=True 在 Agg backend 下不会真的触发鼠标事件，需要真实 GUI 场景验证。灰色 marker 点击走 `toolbar.set_status` —— 验证该提示可见。

- [ ] **Step 1: 启动 live UI**

```bash
uv run python -m BreakoutStrategy.live
```

- [ ] **Step 2: 人工测试矩阵**

| 场景 | 操作 | 预期 |
|---|---|---|
| 点深蓝 marker | 找已选中行，点图上它的深蓝圆圈 | 什么都不变（已是 current） |
| 点浅蓝 marker（同股票另一 BO） | 选 A，然后在图上点同股票另一浅蓝圆 | 列表中该行变深蓝、原 current 变深绿；图表 current marker 切换 |
| 点灰色 marker | 缩窄 Date filter 让某 matched BO 被过滤，然后点该 BO 的灰色圆 | Toolbar 显示 "BO ... is hidden by current filter; adjust Date/Score to see it"；列表/图表不变 |
| 点空心 marker | 点一个非 matched 的空心圆 | 什么都不变（plain 不设 picker） |

若任何场景失败，定位到 `_on_chart_bo_picked` 或 `canvas_manager._on_pick` 加日志排查，修复后回到 Task 10 的对应 step。

- [ ] **Step 3: Commit（若有 debugging 改动）**

若无改动则跳过。否则：

```bash
git add -p
git commit -m "fix(live): resolve chart pick event regression found in manual test"
```

---

## Task 13: 全量回归 + 清理

**Files:**
- 无新代码；只跑测试 + 整理

- [ ] **Step 1: 全量测试**

```bash
uv run pytest BreakoutStrategy/ -x -q
```

Expected: 全绿。若有失败（尤其是非 live UI 相关的），定位原因——本 plan 不应影响 mining / analysis / news_sentiment 测试。

- [ ] **Step 2: 搜索是否遗漏字面量引用**

```bash
grep -rn "state\.selected\b\|matched_bo_indices=" BreakoutStrategy/ --include="*.py" | grep -v test_ | grep -v "__pycache__"
```

Expected: 0 结果。若有遗漏（比如旧命名的残留），补齐。

- [ ] **Step 3: 检查旧 on_select kwarg 残留**

```bash
grep -rn "on_select=" BreakoutStrategy/live/ --include="*.py"
```

Expected: 只在测试里用 `on_row_selected=`。若生产代码里还有 `on_select=`，改过来。

- [ ] **Step 4: Commit（若有清理改动）**

若无改动跳过；否则：

```bash
git add -p
git commit -m "chore(live): cleanup residual selected/matched_bo_indices references"
```

---

## Self-Review Notes

**Spec coverage check**（每项对应需求）:
- ✅ 主选中深蓝白字 → Task 4 `row_current`
- ✅ 伴生同股票浅蓝黑字 → Task 4 `row_companion`
- ✅ 切换同股票：上一次深绿 → Task 4 `row_previous` + Task 2 状态转移
- ✅ marker 4 级（current 深蓝 / visible 浅蓝 / filtered_out 灰 / plain 空心）→ Task 7+8
- ✅ 点击可点 marker 反向选中 → Task 9+10
- ✅ 灰色点击忽略+提示 → Task 10 `_on_chart_bo_picked` else 分支

**Placeholder scan**: 无 TODO/TBD/"implement later"/"add error handling"。全部代码块完整。

**Type consistency**:
- `_classify_bo` 签名：`(idx, current, visible: set, filtered_out: set)` — Task 7/8/9 一致
- `on_row_selected` 参数类型：`Callable[[MatchedBreakout], None]` — Task 3/10 一致（非可选 None）
- `apply_selection_visual(current, previous)` — Task 4 定义、Task 10 调用一致
- 颜色常量 `bo_marker_current` 改色 `#1565C0`（原 `#2E7D32`）—— Task 8 styles.py 改了一并同步
