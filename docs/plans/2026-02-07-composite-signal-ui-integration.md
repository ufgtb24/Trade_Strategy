# Composite Signal UI Integration

> **Goal**: Display weighted_sum, sequence_label, amplitude, turbulent in UI to help identify buy opportunities at scan_date
> **Date**: 2026-02-07
> **Scope**: Phase 1 (Data Enhancement) + Phase 2 (Visual Highlighting)

---

## Phase 1: Data Enhancement

### 1.1 JSON Extension (`signal_scan_manager.py`)

`_results_to_json()` 的 `result_item` 新增 4 字段，直接从 SignalStats 读取：

```python
result_item = {
    ...
    "weighted_sum": stats.weighted_sum,
    "sequence_label": stats.sequence_label,
    "amplitude": round(stats.amplitude, 3),
    "turbulent": stats.turbulent,
    ...
}
```

### 1.2 StockListPanel Data Loading (`stock_list_panel.py`)

`load_data()` 中提取新字段：

```python
item["weighted_sum"] = result.get("weighted_sum", 0.0)
item["sequence_label"] = result.get("sequence_label", "")
item["amplitude"] = result.get("amplitude", 0.0)
item["turbulent"] = result.get("turbulent", False)
```

默认列列表扩展：

```python
columns = ["signal_count", "weighted_sum", "sequence_label", "b_count", "v_count", "y_count", "d_count"]
```

### 1.3 Column Config (`ui_config.yaml`)

`column_labels` 新增：

```yaml
weighted_sum:
  display: W.Sum
  tooltip: "Weighted Sum: Signal strength weighted by pk_num/tr_num"
sequence_label:
  display: Sequence
  tooltip: "Sequence: Signal timeline (e.g. D(2) -> B(3) -> V)"
```

`visible_columns` 追加 `weighted_sum` 和 `sequence_label`。

---

## Phase 2: Visual Highlighting

### 2.1 Row Color Tags (`stock_list_panel.py`)

`_create_ui()` 中注册 Tag：

```python
for tree in (self.fixed_tree, self.main_tree):
    tree.tag_configure("turbulent", background="#FFCDD2", foreground="#000000")
    tree.tag_configure("high_ws", background="#C8E6C9", foreground="#000000")
```

`_update_tree()` 中应用 Tag（优先级：turbulent > high_ws > none）：

```python
tags = ()
if stock.get("turbulent", False):
    tags = ("turbulent",)
elif stock.get("weighted_sum", 0) >= self._high_ws_threshold:
    tags = ("high_ws",)
```

阈值从 `ui_config.yaml` 读取：

```yaml
ui:
  composite_highlight:
    high_ws_threshold: 5.0
```

### 2.2 Hide Turbulent Filter (`stock_list_panel.py`)

StockListPanel 工具栏新增 Checkbox（Columns 按钮右侧）：

```python
self._hide_turbulent_var = tk.BooleanVar(value=False)
ttk.Checkbutton(toolbar, text="Hide Turbulent", variable=self._hide_turbulent_var,
                command=self._on_filter_changed).pack(side=tk.LEFT, padx=(10, 0))
```

过滤逻辑：

```python
def _on_filter_changed(self):
    if self._hide_turbulent_var.get():
        self.filtered_data = [s for s in self.stock_data if not s.get("turbulent", False)]
    else:
        self.filtered_data = self.stock_data
    self._update_tree()
```

---

## Modified Files

| File | Changes |
|------|---------|
| `UI/managers/signal_scan_manager.py` | `_results_to_json()` add 4 fields |
| `UI/panels/stock_list_panel.py` | `load_data()` read fields, `_create_ui()` register tags + filter, `_update_tree()` apply tags |
| `configs/signals/ui_config.yaml` | `column_labels` +2, `visible_columns` +2, new `composite_highlight` block |
