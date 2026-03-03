# 联合信号 UI 集成 -- 最小实现路径架构分析

## Executive Summary

联合信号系统的 4 个新字段（`weighted_sum`, `sequence_label`, `amplitude`, `turbulent`）已在后端管道中完整计算（`aggregator.py` 输出到 `SignalStats`），但在 **JSON 序列化** 和 **UI 消费** 两个环节存在明确断点。核心问题是 `SignalScanManager._results_to_json()` 使用**手工字段映射**而非模型自动序列化，导致新字段被丢弃。

修复路径非常清晰：最少改动 **3 个文件**，最多 **5 个文件**（含可选的图表增强），总代码变更量约 60-100 行。

---

## 1. 数据流断点精确定位

### 1.1 完整数据流路径

```
scanner.scan()
  → worker: _scan_single_stock() → signals + amplitude
  → aggregator.aggregate(signals, scan_date, amplitude_by_symbol)
    → SignalStats(weighted_sum=..., sequence_label=..., amplitude=..., turbulent=...)
  → 返回 List[SignalStats]
                │
                │  *** 断点 1: JSON 序列化 ***
                ▼
SignalScanManager._results_to_json(results: List[SignalStats])
  → 手工映射 result_item = { "symbol", "signal_count", "b_count", ... }
  → 【缺失】weighted_sum, sequence_label, amplitude, turbulent 未映射
  → scan_data JSON
                │
                │  *** 断点 2: UI 数据解析 ***
                ▼
StockListPanel.load_data(scan_results)
  → item["signal_count"] = result.get("signal_count", 0)
  → 【缺失】不读取 weighted_sum 等字段
  → columns = ["signal_count", "b_count", "v_count", "y_count", "d_count"]
  → 【缺失】列定义中无新字段
```

### 1.2 断点 1 详细分析 -- JSON 序列化丢失

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/managers/signal_scan_manager.py`
**方法**: `_results_to_json()` (第 255-338 行)

序列化逻辑使用**手工逐字段映射**：

```python
# 第 316-335 行 -- 当前代码
result_item = {
    "symbol": stats.symbol,
    "signal_count": stats.signal_count,
    "b_count": b_count,
    "v_count": v_count,
    "y_count": y_count,
    "d_count": d_count,
    "latest_signal_date": str(stats.latest_signal_date),
    "latest_price": _make_json_serializable(stats.latest_price),
    "signals": [...]
}
# *** 缺失以下 4 个字段 ***
# "weighted_sum": stats.weighted_sum
# "sequence_label": stats.sequence_label
# "amplitude": stats.amplitude
# "turbulent": stats.turbulent
```

**根因**: `SignalStats` 是 `dataclass`，理论上可用 `dataclasses.asdict()` 自动序列化，但代码选择了手工映射（因为 `signals` 列表中包含 `AbsoluteSignal` 对象需要自定义格式化）。新字段加入 `SignalStats` 时未同步更新此映射。

### 1.3 断点 2 详细分析 -- UI 数据解析遗漏

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/panels/stock_list_panel.py`
**方法**: `load_data()` (第 528-569 行)

```python
# 第 550-555 行 -- 字段提取
item["signal_count"] = result.get("signal_count", 0)
item["b_count"] = result.get("b_count", ...)
item["v_count"] = result.get("v_count", ...)
item["y_count"] = result.get("y_count", ...)
item["d_count"] = result.get("d_count", ...)
# *** 缺失 ***
# item["weighted_sum"] = result.get("weighted_sum", 0.0)
# item["sequence_label"] = result.get("sequence_label", "")
# item["amplitude"] = result.get("amplitude", 0.0)
# item["turbulent"] = result.get("turbulent", False)

# 第 563-565 行 -- 列定义
columns = ["signal_count", "b_count", "v_count", "y_count", "d_count"]
# *** 缺失新列 ***
```

---

## 2. 最小变更路径

### 2.1 必须修改的文件（3 个）

| # | 文件 | 改动范围 | 改动内容 |
|---|------|---------|---------|
| 1 | `BreakoutStrategy/UI/managers/signal_scan_manager.py` | ~4 行新增 | `_results_to_json()` 中添加 4 个字段映射 |
| 2 | `BreakoutStrategy/UI/panels/stock_list_panel.py` | ~8 行新增 | `load_data()` 中添加字段提取 + 更新 columns 列表 |
| 3 | `configs/signals/ui_config.yaml` | ~12 行新增 | `column_labels` 中添加新字段的 display/tooltip 配置 |

### 2.2 可选修改的文件（2 个）

| # | 文件 | 改动范围 | 改动内容 |
|---|------|---------|---------|
| 4 | `BreakoutStrategy/UI/main.py` | ~10 行修改 | `_compute_temp_stats_from_signals()` 添加联合字段计算（Analysis Mode） |
| 5 | `BreakoutStrategy/UI/charts/canvas_manager.py` | ~5 行新增 | tooltip 中显示联合信号信息（可选增强） |

### 2.3 各文件改动详细规格

#### 文件 1: `signal_scan_manager.py` -- JSON 序列化补全

**位置**: `_results_to_json()` 方法，第 335 行 `"signals": [...]` 之后

**改动**: 在 `result_item` 字典中新增 4 个键值对：

```python
result_item = {
    # ... 现有字段 ...
    "signals": [...],
    # --- 新增联合信号字段 ---
    "weighted_sum": round(stats.weighted_sum, 2),
    "sequence_label": stats.sequence_label,
    "amplitude": round(stats.amplitude, 4),
    "turbulent": stats.turbulent,
}
```

**注意事项**:
- `weighted_sum` 和 `amplitude` 是 float，需要 round 控制精度（避免 JSON 中出现过长小数）
- `sequence_label` 是 str，包含 unicode 箭头 "→"，`ensure_ascii=False` 已在 `_save_json()` 中设置（第 344 行），无需额外处理
- `turbulent` 是 bool，JSON 原生支持
- `_make_json_serializable` 不需要调用，因为这 4 个字段类型已经是 JSON 兼容类型（float, str, bool）

#### 文件 2: `stock_list_panel.py` -- UI 数据解析与列展示

**位置 A**: `load_data()` 方法，第 555 行之后

```python
# 联合信号字段
item["weighted_sum"] = result.get("weighted_sum", 0.0)
item["sequence_label"] = result.get("sequence_label", "")
item["amplitude"] = result.get("amplitude", 0.0)
item["turbulent"] = result.get("turbulent", False)
```

**位置 B**: `load_data()` 方法，第 564 行列定义

```python
# 当前
columns = ["signal_count", "b_count", "v_count", "y_count", "d_count"]

# 修改为
columns = ["signal_count", "b_count", "v_count", "y_count", "d_count",
           "weighted_sum", "sequence_label", "turbulent"]
```

**设计决策 -- 关于列的选择**:
- `weighted_sum`: 核心排序指标，必须展示
- `sequence_label`: 直观的信号组合概览，高信息密度
- `turbulent`: 风险标记，影响排序逻辑
- `amplitude`: 可选展示。考虑到信息密度，建议初期不放入默认可见列，但放入 `stock_data` 以便用户通过列配置菜单自行启用

**关于 `_update_tree()` 中的格式化**:
当前已有通用浮点格式化逻辑（第 646-649 行）：
```python
if isinstance(val, float):
    values.append(f"{val:.1f}")
```
`weighted_sum` 和 `amplitude` 作为 float 会被自动格式化为 1 位小数。
`sequence_label` 作为 str 直接显示。
`turbulent` 作为 bool 会显示 "True"/"False"，可能需要映射为更直观的标记（如 "*" 或 ""），可在后续迭代优化。

#### 文件 3: `ui_config.yaml` -- 列标签配置

在 `column_labels` 下新增：

```yaml
weighted_sum:
  display: W.Sum
  tooltip: "Weighted Sum: Effective weighted signal strength (turbulent only counts D)"
sequence_label:
  display: Seq
  tooltip: "Sequence: Chronological signal pattern, e.g. D(2) → B(3) → V"
amplitude:
  display: Amp
  tooltip: "Amplitude: Price swing range in lookback window (High-Low)/Low"
turbulent:
  display: Turb
  tooltip: "Turbulent: Abnormal price movement (amplitude >= 80%)"
```

在 `visible_columns` 中按需添加（建议默认可见 weighted_sum 和 sequence_label）。

#### 文件 4: `main.py` -- Analysis Mode 临时行计算（可选）

**位置**: `_compute_temp_stats_from_signals()` 方法（第 575-594 行）

当前 Analysis Mode 选中股票时，会通过 `_compute_signals_for_stock()` 获取信号列表，然后用 `_compute_temp_stats_from_signals()` 计算临时统计行数据。但目前只计算了 count 类字段。

要让 Analysis Mode 的临时行也显示联合信号数据，需要在此方法中调用 composite 模块的函数：

```python
def _compute_temp_stats_from_signals(self, signals: list) -> dict:
    stats = {
        "signal_count": len(signals),
        "b_count": 0, "v_count": 0, "y_count": 0, "d_count": 0,
    }
    for sig in signals:
        # ... 现有 count 逻辑 ...

    # --- 新增：联合信号计算 ---
    # 需要将 dict 格式的 signals 转换为 AbsoluteSignal 对象
    # 或直接用 dict 数据实现等价计算
    # 建议：编写轻量适配函数，避免在 UI 层直接依赖 AbsoluteSignal
    ...
    return stats
```

**注意**: 这里涉及一个设计选择。`_compute_signals_for_stock()` 返回的是 dict 列表（已从 AbsoluteSignal 转换），而 composite 函数接受 AbsoluteSignal 对象。有两种处理方式：

- **方案 A**: 在 `_compute_signals_for_stock()` 中同时返回联合字段数据（metadata 已包含 amplitude），在转换为 dict 之前从 AbsoluteSignal 列表计算 weighted_sum 等
- **方案 B**: 在 `_compute_temp_stats_from_signals()` 中用纯 dict 数据重新实现等价计算

方案 A 更符合 DRY 原则，推荐。

#### 文件 5: `canvas_manager.py` -- 图表 tooltip 增强（可选）

在 `_attach_hover` 的 `on_hover()` 中，当鼠标悬停在有信号的日期时，可以在 tooltip 中展示 strength 信息。当前已有信号类型显示逻辑（第 678-707 行）。

可以在 B/D 信号的 tooltip 中补充 `strength` 字段：
```python
if sig_type == "B":
    strength = sig.get("strength")
    if strength and strength > 1:
        sig_line += f" str={strength:.0f}"
```

**优先级**: 低。这是纯体验优化，不影响核心功能。

---

## 3. 向后兼容性分析

### 3.1 旧 JSON 文件（不含新字段）加载

**结论: 完全兼容，零风险。**

原因：`load_data()` 中使用 `.get(key, default)` 模式提取字段：

```python
item["weighted_sum"] = result.get("weighted_sum", 0.0)    # 旧JSON → 0.0
item["sequence_label"] = result.get("sequence_label", "")   # 旧JSON → ""
item["amplitude"] = result.get("amplitude", 0.0)           # 旧JSON → 0.0
item["turbulent"] = result.get("turbulent", False)          # 旧JSON → False
```

旧 JSON 缺少这些字段时，所有值都会有合理的默认值：
- `weighted_sum = 0.0` -- 排序时排在最后
- `sequence_label = ""` -- 列表中显示空白
- `amplitude = 0.0` -- 无振幅数据
- `turbulent = False` -- 不标记异常

### 3.2 新 JSON 文件在旧 UI 代码中加载

**结论: 完全兼容。**

JSON 中多出的字段会被旧版 `load_data()` 忽略（未 get 的字段直接不使用）。

### 3.3 新旧格式混合使用

列配置系统（`set_visible_columns`）是基于字段名的白名单机制。如果用户配置了 `weighted_sum` 列为可见，但加载了旧 JSON，该列会显示默认值 "0.0"。这是可接受的降级行为。

---

## 4. Browse Mode vs Analysis Mode 数据路径对比

### 4.1 Browse Mode（从 JSON 加载）

```
load_scan_results(json_path)
  → json.load(f) → scan_data
  → stock_list_panel.load_data(scan_data)
    → result.get("weighted_sum", 0.0)  # 直接从 JSON 读取

选中股票 → _on_stock_selected()
  → signals = stock_data.get("signals", [])  # 从 JSON 读取
  → chart_manager.update_chart(signals=signals)
  → stock_list_panel.hide_temp_row()  # Browse Mode 不显示临时行
```

**关键**: Browse Mode 的联合信号数据**完全依赖 JSON 持久化**。只要断点 1（序列化）修复，Browse Mode 自动工作。

### 4.2 Analysis Mode（实时计算）

```
选中股票 → _on_stock_selected()
  → signals = _compute_signals_for_stock(symbol, scan_date)
    → scan_single_stock() → all_signals, filtered_signals, metadata
    → 转换为 dict 列表（*** 此处丢失了 strength 字段 ***）
  → chart_manager.update_chart(signals=signals)
  → temp_stats = _compute_temp_stats_from_signals(filtered_signals)
    → *** 目前只计算 count 字段，无联合信号字段 ***
  → stock_list_panel.show_temp_row(symbol, temp_stats)
```

**关键差异与额外工作**:

1. **列表显示**: Analysis Mode 的列表数据来自 `scan_data`（最初的 JSON 加载），所以 `weighted_sum` 等字段已经通过 `load_data()` 解析。临时行（黄色行）的数据来自 `_compute_temp_stats_from_signals()`，需要额外计算。

2. **strength 字段丢失**: `_compute_signals_for_stock()` 在第 542-549 行将 `AbsoluteSignal` 转换为 dict 时，**没有包含 `strength` 字段**：
   ```python
   signals_dict = [
       {
           "date": str(s.date),
           "signal_type": s.signal_type.value,
           "price": s.price,
           "details": s.details,
           # *** 缺失 "strength": s.strength ***
       }
       for s in sorted(filtered_signals, ...)
   ]
   ```
   不过 `strength` 字段已经在 `_results_to_json()` 的 signals 子项中序列化（第 330 行），所以 Browse Mode 的信号 dict 中是有的。Analysis Mode 需要额外补充。

3. **联合字段计算**: 临时行的 `weighted_sum`, `sequence_label`, `amplitude`, `turbulent` 需要在 Analysis Mode 实时计算。这需要：
   - `amplitude`: 已在 `scan_single_stock()` 的 metadata 中返回（`metadata["amplitude"]`），但当前 `_compute_signals_for_stock()` 未保存此值
   - `weighted_sum`, `sequence_label`, `turbulent`: 需要从信号列表计算，依赖 composite 函数

### 4.3 处理建议

**Browse Mode**: 修复断点 1 + 断点 2 即可，无额外工作。

**Analysis Mode**: 需要额外修改 `_compute_signals_for_stock()` 和 `_compute_temp_stats_from_signals()`，具体来说：

1. `_compute_signals_for_stock()`: 保存 metadata 中的 amplitude，在 signals_dict 中补充 strength 字段
2. `_compute_temp_stats_from_signals()` 或一个新的适配函数: 利用保存的 metadata 和 signals 数据计算联合字段

---

## 5. 可复用的现有机制

### 5.1 列配置系统 -- 完全可复用

现有机制链路：
```
ui_config.yaml (column_labels, visible_columns)
  → UIConfigLoader.get_stock_list_column_config()
  → StockListPanel._load_column_config()
  → _get_column_display_name(column) → 缩写标题
  → HeaderTooltip → 悬停显示完整名称
  → 右键菜单 → 切换列显示/隐藏
  → 拖拽排序 → 调整列顺序
```

只需在 `ui_config.yaml` 中配置新字段的 `display` 和 `tooltip`，整个列管理系统自动生效。用户可以：
- 通过工具栏 "Columns" 按钮配置可见列
- 右键菜单快速切换
- 拖拽调整列顺序
- 一键隐藏/显示所有属性列

### 5.2 _make_json_serializable -- 无需扩展

新字段类型（float, str, bool）都是 JSON 原生类型，不需要经过 `_make_json_serializable` 转换。

### 5.3 Treeview 格式化 -- 自动适配

`_update_tree()` 中的通用格式化逻辑：
- float → `f"{val:.1f}"` （weighted_sum, amplitude 自动格式化）
- str → `str(val)` （sequence_label 直接显示）
- bool → `str(val)` （turbulent 显示 "True"/"False"，后续可优化为 "*"/""）

### 5.4 排序系统 -- 自动适配

`sort_by(column)` 使用 `x.get(column)` 通用排序，新列自动支持点击排序。数值字段（weighted_sum, amplitude）按数值排序，字符串字段（sequence_label）按字典序排序。

---

## 6. 实现分层建议

### 迭代 1: 核心数据打通（最小可用版本）

**目标**: Browse Mode 列表中展示联合信号数据。
**改动文件**: 3 个
**工作量估算**: ~30 行代码 + 12 行 YAML

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `signal_scan_manager.py` | `_results_to_json()` 添加 4 字段 |
| 2 | `stock_list_panel.py` | `load_data()` 添加字段提取 + 列定义 |
| 3 | `ui_config.yaml` | 添加 column_labels 配置 |

**验证方法**:
1. 运行 New Scan 生成新 JSON
2. 检查 JSON 文件中是否包含 `weighted_sum`, `sequence_label`, `amplitude`, `turbulent`
3. UI 列表中确认新列是否正确显示
4. 加载旧 JSON 确认不报错，新列显示默认值

**限制**: Analysis Mode 的临时行不显示联合字段（显示为空/0），这是可接受的因为列表主数据已经正确。

### 迭代 2: Analysis Mode 完善

**目标**: Analysis Mode 临时行也显示联合信号数据。
**改动文件**: 1-2 个
**工作量估算**: ~30-50 行代码

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `main.py` : `_compute_signals_for_stock()` | 保留 metadata.amplitude，信号 dict 补充 strength |
| 2 | `main.py` : `_compute_temp_stats_from_signals()` | 调用 composite 函数计算联合字段 |

**设计选择**:
- 最简方案：在 `_compute_temp_stats_from_signals()` 中直接用 dict 数据重新计算（纯函数，~20行）
- 更优方案：修改 `_compute_signals_for_stock()` 返回值，携带 amplitude 和预计算的联合数据，避免重复计算

### 迭代 3: 体验优化（可选）

**目标**: 图表 tooltip 增强 + 显示优化。
**改动文件**: 2 个
**工作量估算**: ~20 行代码

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `canvas_manager.py` | tooltip 中显示 strength 信息 |
| 2 | `stock_list_panel.py` | turbulent 列格式优化（"*" 代替 "True"） |

---

## 7. 风险评估

| 风险项 | 等级 | 说明 |
|--------|------|------|
| 向后兼容性 | 低 | `.get(key, default)` 模式保证旧 JSON 兼容 |
| 序列化正确性 | 低 | 新字段均为 JSON 原生类型 |
| UI 列宽度 | 中 | `sequence_label` 可能较长（如 "D(2) → B(3) → V → Y"），需确保列宽足够或支持水平滚动 |
| Analysis Mode 数据一致性 | 中 | 需确保临时行计算逻辑与批量扫描逻辑一致 |
| 性能 | 低 | 所有计算均为 O(n) 复杂度，n 为单股信号数（通常 < 20） |

---

## 附录: 关键代码位置索引

| 模块 | 文件绝对路径 | 关键方法/行号 |
|------|------------|-------------|
| JSON 序列化 | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/managers/signal_scan_manager.py` | `_results_to_json()` L255-338 |
| UI 数据加载 | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/panels/stock_list_panel.py` | `load_data()` L528-569 |
| 列配置 | `/home/yu/PycharmProjects/Trade_Strategy/configs/signals/ui_config.yaml` | `stock_list_columns.column_labels` L22-52 |
| 聚合器 | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/signals/aggregator.py` | `aggregate()` L33-100 |
| 数据模型 | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/signals/models.py` | `SignalStats` L46-66 |
| 联合函数 | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/signals/composite.py` | 全文件 6 个纯函数 |
| Analysis Mode | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/main.py` | `_compute_signals_for_stock()` L487-573, `_compute_temp_stats_from_signals()` L575-594 |
| 图表 tooltip | `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/UI/charts/canvas_manager.py` | `on_hover()` L604-726 |
