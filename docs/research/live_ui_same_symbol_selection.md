# Live UI 同股票多 BO 联动 —— 可行性判断与实现方案

> Agent team `live-ui-selection-sync` 产出。2026-04-14。更新于 2026-04-15，反映实际交付状态。
>
> 用户需求：左侧匹配列表中同一 symbol 的多个 matched breakout 建立联动，
> 新增同股票伴生行高亮 + K 线图 BO marker 四级着色
> + 图表 → 列表的反向选中。

---

## 可行性结论

**可行**。无根本阻碍，全部改动集中在 UI 层（`BreakoutStrategy/live/` + `BreakoutStrategy/UI/charts/`），无需动 pipeline/data 层。

关键风险只有两条，都可控：
1. **ttk.Treeview 的系统选中色优先级**：原生 selection 蓝底白字会压过 tag 的 background，导致"浅蓝伴生"显不出来。解决方案是**绕开真 selection**——在 `<<TreeviewSelect>>` 回调里立即 `selection_remove`，全部视觉用 tag 表达。副作用：键盘 ↑↓ 导航失效，需手工绑定到"选中下一/上一 visible item"。
2. **图表 → 列表反向同步的事件环**：点击 chart marker 触发列表选中，若再反弹触发 `<<TreeviewSelect>>` 会递归。用 `_suppress_select` flag 临时屏蔽回调即可。

---

## 方案总览

```
┌──────────────────────────── SSOT: LiveApp.state ────────────────────────────┐
│  current_selected: MatchedBreakout | None                                    │
└─────────────────────────────────────────────────────────────────────────────┘
       ▲                                ▲                                ▲
       │ _on_row_selected               │ _on_chart_bo_picked            │ _on_filter_changed
       │                                │                                │
┌──────┴──────┐                 ┌───────┴────────┐                ┌──────┴──────┐
│  MatchList  │ ─── apply ───▶  │  LiveApp       │ ─── rebuild ─▶ │  Chart      │
│  (view)     │   selection_    │  (controller)  │   chart        │  (view)     │
│             │   visual        │                │                │             │
└─────────────┘                 └────────────────┘                └─────────────┘
```

**原则**：
- `LiveApp.state` 是唯一状态源，`MatchList` 不持有选中状态
- 所有用户输入都收敛到 `LiveApp._update_selection(item)` 做状态转移，再由 `_render_selection()` 分发到两个 view
- MatchList 视觉完全用 tag 驱动，不依赖 tkinter 原生 selection

---

## 颜色 / 视觉规格

### MatchList 行背景（3 态）
| 态 | 触发 | 背景 | 前景 |
|---|---|---|---|
| default | 普通行 | 白 | 原 pos/neg/neu/na foreground（绿/黑/蓝/灰斜体） |
| companion | 与 current 同 symbol、非 current | `#CFE2F3`（浅蓝） | 黑（覆盖原 foreground） |
| current | 用户主选中 | `#4F6D8C`（石板蓝） | 白 |

**Tag 行为**：被高亮时**不叠加** base sentiment color tag。`current` 和 `companion` 行仅挂对应 state tag（`row_current` / `row_companion`），不带 pos/neg/neu/na tag——避免不同主题下 tag 优先级不可靠导致白字前景被覆盖。default 态行只挂 base sentiment tag。

```python
tree.tag_configure("row_current",  background="#4F6D8C", foreground="#FFFFFF")
tree.tag_configure("row_companion", background="#CFE2F3", foreground="#000000")
# default 态：不挂 state tag，只保留原 pos/neg/neu/na
```

### K 线图 BO marker（4 级）
| 级 | 判定 | 样式 | zorder | picker |
|---|---|---|---|---|
| current | `bo.index == state.current_selected.raw_breakout["index"]` | 实心 `#0000FF`（蓝色，运行时从 `styles.py` 的 `bo_marker_current` 读取，与 dev UI 的 `breakout_marker` 同色） | 13 | ✓ |
| visible matched | `bo.index ∈ 该 symbol 的 visible_bo_indices` 且非 current | 实心 `#64B5F6`（浅蓝） | 12 | ✓ |
| filtered_out matched | `bo.index ∈ all_matched_bo_chart_indices` 但不在 visible | 实心 `#9E9E9E`（灰）+ alpha 0.7 | 11 | ✓（点击仅状态栏提示） |
| plain | 其他 BO | 空心 edge=`#64B5F6` | 10 | ✗ |

marker 仍是 4 级（`current` / `visible` / `filtered_out` / `plain`），与 MatchList 的 3 态行无对应关系：图表不区分"companion vs 其他 visible"，同 symbol 的伴生 BO 在图表上就是 visible matched 浅蓝。

---

## 按模块改动清单

### `BreakoutStrategy/live/state.py`

- `AppState.selected` 改名 → `current_selected`（唯一选中字段，无 previous 字段）

```python
@dataclass
class AppState:
    items: list[MatchedBreakout] = field(default_factory=list)
    current_selected: MatchedBreakout | None = None
    last_scan_date: str = ""
    last_scan_bar_date: str = ""
```

### `BreakoutStrategy/live/panels/match_list.py`

**回调重构**：
- 构造参数 `on_select` → `on_row_selected`，语义变：**只在用户真点击行时触发**，不再在 filter 刷新时传 None
- `_refresh_visible` 内部**移除** `self._on_select(None)` 调用；filter 变化仅通过 `_on_filter_changed` 通知 LiveApp，由 LiveApp 决定 current 是否失效

**新 API**：
- `get_visible_items() -> list[MatchedBreakout]` —— 暴露 `_visible_items`
- `get_visible_bo_indices(symbol: str) -> set[int]` —— 返回 visible 中同 symbol 的 `raw_breakout["index"]` 集合，供 chart 分级用
- `apply_selection_visual(current: MatchedBreakout | None) -> None` —— 按 `(symbol, breakout_date, bo_index)` key 定位 iid，给每行设 tag：`row_current` / `row_companion` / base_tag
- `select_item(item: MatchedBreakout) -> None` —— 图表反向同步用：scroll 到该行（`tree.see(iid)`）+ 调 `_on_row_selected(item)`；过程中设 `self._suppress_tree_select = True` 暂屏蔽 `<<TreeviewSelect>>`（防环路）

**键盘导航保留**：绑 `<Up>/<Down>` 手动走 visible_items 索引 ±1 后调 `_on_row_selected`。

### `BreakoutStrategy/UI/charts/components/markers.py`

- `_classify_bo` 扩为 4 分支签名：`(idx, current, visible_matched, filtered_out_matched) -> {"current", "visible", "filtered_out", "plain"}`
- `draw_breakouts_live_mode` 签名：`visible_matched_indices: set[int]`, `filtered_out_matched_indices: set[int]`
- 绘制：分 4 组独立 `ax.scatter` 调用，各自设 facecolor/edgecolor/zorder；前三级加 `picker=True, pickradius=8`；plain 不设 picker
- 为可 pick 的三组 scatter 挂 artist 属性：`sc.bo_chart_indices = [bo.index ...]`——pick_event 通过 `event.ind[0]` 查到组内位置，再取 index

### `BreakoutStrategy/UI/charts/canvas_manager.py`

- `update_chart` 的 `display_options` 新增：
  - `visible_matched_indices: set[int]`
  - `filtered_out_matched_indices: set[int]`
  - `on_bo_picked: Callable[[int], None] | None`（回调：接收 bo 的 chart_index）
- live_mode 分支把新入参传给 `draw_breakouts_live_mode`
- 每次 `update_chart` 结束时 `self.canvas.mpl_connect("pick_event", self._on_pick)`（保证幂等：换图前先 `disconnect` 上次的 cid）
- `_on_pick(event)`：从 `event.artist.bo_chart_indices[event.ind[0]]` 拿 bo_index，调 `display_options["on_bo_picked"](bo_index)`

### `BreakoutStrategy/live/app.py`

**状态转移核心**：
```python
def _update_selection(self, new: MatchedBreakout | None) -> None:
    self.state.current_selected = new
    self._render_selection()

def _render_selection(self) -> None:
    self.match_list.apply_selection_visual(
        current=self.state.current_selected,
    )
    self.detail_panel.update_item(self.state.current_selected)
    self._rebuild_chart()
```

**三个入口**：
- `_on_row_selected(item)` —— 替换原 `_on_item_selected`，直接调 `_update_selection(item)`
- `_on_chart_bo_picked(bo_index)` —— 在 `state.items` 中按 `(current.symbol, bo_index)` 查 MatchedBreakout；若在 visible → `match_list.select_item(item)`（会走 `_on_row_selected`）；若不在 visible（灰色）→ `toolbar.set_status("This BO is hidden by current filter")`
- `_on_filter_changed()` —— 校验 `state.current_selected` 是否仍在 `match_list.get_visible_items()`；不在则 `_update_selection(None)`；在则 `_render_selection()`（iid 重建后需重新应用 tag）；最后调 `chart.update_filter_range`

**`_rebuild_chart()`**（从原 `_on_item_selected` 的图表绘制部分抽出）：
```python
symbol = self.state.current_selected.symbol if self.state.current_selected else None
visible_idx = self.match_list.get_visible_bo_indices(symbol) if symbol else set()
all_matched = set(self.state.current_selected.all_matched_bo_chart_indices) if symbol else set()
filtered_out = all_matched - visible_idx
self.chart.update_chart(
    ...,
    display_options={
        "live_mode": True,
        "current_bo_index": self.state.current_selected.raw_breakout["index"],
        "visible_matched_indices": visible_idx,
        "filtered_out_matched_indices": filtered_out,
        "on_bo_picked": self._on_chart_bo_picked,
        ...
    },
)
```

---

## 事件顺序图

### 列表点击
```
Tree <<TreeviewSelect>>
  → MatchList._on_tree_select
  → (if _suppress_tree_select) return
  → on_row_selected(item)
  → LiveApp._on_row_selected
  → _update_selection(item)
      state.current_selected 更新
  → _render_selection
      ├─ match_list.apply_selection_visual  # 全部 row 重打 tag
      ├─ detail_panel.update_item
      └─ _rebuild_chart                      # chart.update_chart
```

### 图表点击 BO marker
```
canvas pick_event
  → canvas_manager._on_pick → display_options["on_bo_picked"](bo_index)
  → LiveApp._on_chart_bo_picked
      在 state.items 查 (current.symbol, bo_index)
      ├─ 命中 visible: match_list.select_item(item)
      │    → _suppress_tree_select=True, tree.see(iid)
      │    → _on_row_selected(item)（直接调，绕过 <<TreeviewSelect>>）
      │    → _update_selection / _render_selection（同上）
      │    → _suppress_tree_select=False
      └─ 灰色 filtered_out: toolbar.set_status(提示文案)
```

### Filter 变化
```
Spinbox/Entry trace
  → MatchList._refresh_visible
      重建 _visible_items
      重建 Treeview 行（全 delete + insert）
  → on_filter_changed
  → LiveApp._on_filter_changed
      visible = match_list.get_visible_items()
      if state.current_selected not in visible:
          _update_selection(None)
      else:
          _render_selection()  # iid 变了，重打 tag + 重绘 chart
      chart.update_filter_range(...)
```

---

## 边界情况处理

| 情况 | 处理 |
|---|---|
| 排序列切换 | `_refresh_visible` → `_on_filter_changed` 同一路径。current 身份不变，只是 iid 位置变 → `_render_selection` 重打 tag 即可 |
| filter 缩窄导致 current 被过滤掉 | LiveApp 清空 current（`_update_selection(None)`）；detail panel 清空；chart 回到"无选中"态（全部 matched 画浅蓝，其他画灰/空心） |
| 点击同股票的其他 companion 行 | 规则简单：旧 current 变 companion，新行变 current，无 previous 状态 |
| 点击灰色 marker | 状态栏提示 "This BO is hidden by current filter; adjust Date/Score to see it"，**不**自动扩 filter（副作用太重，用户意图不明确） |
| 点击空心 plain marker | `picker=False`，事件不触发。用户继续 hover 查看 tooltip |
| MatchedBreakout 身份比较 | 用 `(symbol, breakout_date, bo_index)` tuple 作 key，不依赖 `is` 或 dataclass eq，避免 filter 重建后对象复活问题 |
| 缓存旧 JSON 缺 `all_matched_bo_chart_indices` | 现有 `dataclass` 有 `field(default_factory=list)` 兜底，此时 4 级退化为 "current+all plain"，无伴生浅蓝。旧缓存被覆盖一次后自动修复 |
| 键盘 ↑↓ 导航 | `_suppress_tree_select` 方案下原生导航失效。绑 `<Up>/<Down>/<Home>/<End>` 到 "调 `_on_row_selected(visible_items[new_idx])`" |

---

## 不动的东西

- Pipeline、cache、scanner、news_sentiment —— 0 改动
- MatchedBreakout 字段定义 —— 0 改动（已有字段就够了）
- Dev UI (`BreakoutStrategy/UI/`) 的非 live 分支 —— 0 改动（`draw_breakouts_live_mode` 独立于 `draw_breakouts`）
- 过滤逻辑 `_apply_filters` / 排序 `_apply_sort` —— 0 改动

---

## 估算改动量

| 文件 | 行数量级 | 复杂度 |
|---|---|---|
| `live/state.py` | +1 行（改名，去掉 previous 字段） | 低 |
| `live/panels/match_list.py` | +60~80 行（tag + 新 API + 键盘绑定 + 回调重构） | 中 |
| `live/app.py` | +40 行，重构 `_on_item_selected` 拆成 `_on_row_selected` + `_rebuild_chart` | 中 |
| `UI/charts/components/markers.py` | +30 行（4 分支 + picker 属性挂载） | 中 |
| `UI/charts/canvas_manager.py` | +20 行（pick 连接 + display_options 新字段） | 低 |

总计 ~140-170 行纯 UI 层改动，无 pipeline 风险。
