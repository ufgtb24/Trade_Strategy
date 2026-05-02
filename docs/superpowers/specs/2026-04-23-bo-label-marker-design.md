# BO Label Marker 显示功能设计

**日期：** 2026-04-23
**范围：** dev 模式 chart

## 1. 目标与非目标

### 目标
在 dev 模式 chart 上为每个突破点（BO）在现有 marker 堆叠顶端增加一层"回测 label 值"显示：

- 通过 "BO Label" 复选框整体开关（与现有 "BO Score" 复选框对称）
- 通过 Spinbox 运行时调整计算窗口 N（天数），无需重扫即可看到不同 N 下的 label 值
- 多个 BO 的 label 值中，**最大值**用一种 tier 高亮，其他用另一种 tier，肉眼可区分

### 非目标
- 不动 Stock List 的 "Label" 列（该列基于扫描固化的 `bo.labels`，与逐 BO marker 的原值语义不同）
- 不改 Live 模式（`draw_breakouts_live_mode` 与 `live/` 不动）
- 不回写运行时 N 的计算结果到 `bo.labels` 或 scan JSON（纯运行时显示）
- 不按 label 正负着色（统一 tier 样式）
- 不把 "BO Label" 联动到 Stock List 的 Label 列

## 2. 用户交互

`dev/panels/parameter_panel.py` 工具栏在 "BO Score" 复选框右侧新增一组：

```
[✓] BO Score    [ ] BO Label  N:[20 ⇅]    [ ] SU_PK
                ↑ 新 checkbox  ↑ 新 Spinbox
```

**控件：**

| 控件 | 规格 |
|---|---|
| Checkbox "BO Label" | `show_bo_label_var: BooleanVar`，默认 `False` |
| Spinbox N | 整数 `1..200`，宽度 4；checkbox 关闭时 `state="disabled"` 灰显但保留值 |

**默认值来源：**
- Spinbox N 的默认值 = 当前 scan 的 `label_configs[0].max_days`，若 scan 无 `label_configs` 则回退 20
- 新 scan 加载后由 `main.py` 调 `parameter_panel.set_bo_label_n_default(max_days)` 设置
- 用户在 session 内手动修改 N 后保留，切换股票不重置；加载新 scan 时从新 scan 的 metadata 重置

**事件：**
- Checkbox toggle → 现有 `_on_checkbox_changed` → `on_display_option_changed_callback` → chart 重绘
- Spinbox 值变化 → 同一回调链 → chart 重绘

## 3. 数据流

**`get_display_options()` 返回字典扩展：**
```python
{
    "show_bo_score": bool,
    "show_superseded_peaks": bool,
    "show_bo_label": bool,       # 新
    "bo_label_n": int,           # 新
}
```

**传递链：**
```
parameter_panel.get_display_options()
  → main.py (on_display_option_changed_callback 触发 chart 刷新)
  → canvas_manager.render_chart(..., display_options=...)
  → 读 show_bo_label / bo_label_n，传给 draw_breakouts(..., show_label=..., label_n=...)
  → markers.draw_breakouts 内部逐 BO 调 compute_label_value(df, bo.index, label_n)
```

`df` 在 `render_chart` 签名中已有，往 `draw_breakouts` 额外透传一步即可（原签名里已含 df）。

## 4. Helper 抽取（`analysis/features.py`）

### 4.1 新增模块级函数

```python
def compute_label_value(
    df: pd.DataFrame, index: int, max_days: int
) -> Optional[float]:
    """
    计算单个 BO 的回测 label：
    (未来 max_days 天内最高收盘价 - 突破日收盘价) / 突破日收盘价

    Args:
        df: OHLCV DataFrame
        index: 突破点索引
        max_days: 回看窗口天数（不含突破当日）

    Returns:
        label 值；数据不足 max_days 天、或突破日收盘价非正时返回 None
    """
    breakout_price = df.iloc[index]["close"]
    max_end = min(len(df), index + max_days + 1)
    future_data = df.iloc[index + 1 : max_end]
    if len(future_data) < max_days:
        return None
    if breakout_price <= 0:
        return None
    max_high = future_data["close"].max()
    return (max_high - breakout_price) / breakout_price
```

### 4.2 重构 `FeatureCalculator._calculate_labels`（公有签名不变）

```python
def _calculate_labels(self, df, index):
    labels = {}
    for config in self.label_configs:
        max_days = config.get("max_days", 20)
        labels[f"label_{max_days}"] = compute_label_value(df, index, max_days)
    return labels
```

### 4.3 Docstring 修正

`_calculate_labels` 原 docstring 写"N 天内最高价"，实际代码用 `close.max()`。本次保持**行为不变**（继续用 `close.max()`），同步将 docstring 改为"最高收盘价"，helper 的 docstring 也明确写"最高收盘价"。是否改成 `high.max()` 属于独立的语义决策，不在本次范围。

## 5. 渲染层改动

### 5.1 Stacking 层名：`bo_label_value`

现有 `MARKER_STACK_GAPS_PT["bo_label"]` 语义是 `[broken_peak_ids]` 方框（与回测 label **无关**）。为避免混淆，新层命名 **`bo_label_value`**。

`UI/styles.py` 更新：
```python
MARKER_STACK_GAPS_PT = {
    "triangle":       20,
    "peak_id":        14,
    "bo_label":       14,   # [broken_peak_ids] 方框（保持原义）
    "bo_score":       30,
    "bo_label_value": 30,   # 新：回测 label 值方框
}
```

### 5.2 堆叠顺序（自下而上）

```
triangle → peak_id → bo_label → bo_score → bo_label_value
                                            ↑ 最顶
```

`bo_label_value` 始终在最顶：
- 同时开 BO Score + BO Label：`... → bo_score → bo_label_value`
- 只开 BO Label：`bo_label_value` 退到 bo_score 的位置（复用 markers.py 现有 `tmp_layers` 的"退一层"做法）

### 5.3 Tier 样式（`UI/styles.py`）

新增：
```python
BO_LABEL_VALUE_TIER_STYLE = {
    "max":   {"bg": "#FFD700", "fg": "#0000FF"},  # 黄底深蓝字
    "other": {"bg": "#FFA500", "fg": "#0000FF"},  # 橙底深蓝字
}
# 边框统一使用 fg（深蓝）
```

不新增 `CHART_COLORS` 键（tier 样式是 dev 专属，不走全局色板）。

### 5.4 `draw_breakouts` 签名扩展

```python
def draw_breakouts(
    ax, df, breakouts,
    highlight_multi_peak=True, peaks=None, colors=None,
    show_score=True,
    show_label=False, label_n=20,     # 新增
):
```

### 5.5 渲染流程（两遍结构）

1. **第 1 遍**：若 `show_label`，对每个 BO 调 `compute_label_value(df, bo.index, label_n)`，收集 `(bo, value)` 非空对；如全空，跳过 label 层
2. **求 max**：`max_value = max(v for _, v in pairs)`
3. **第 2 遍**：绘制 breakouts。若该 BO value 非空：
   - Tier 判定：`"max" if abs(value - max_value) < 1e-9 else "other"`（多个并列最大都用 `max` tier）
   - 样式从 `BO_LABEL_VALUE_TIER_STYLE[tier]` 取
   - 格式化：
     ```python
     sign = "+" if value >= 0 else ""
     text = f"{sign}{value*100:.1f}%"
     ```
   - Annotation：圆角方框，字号 20 粗体，`zorder=12`，位置 = `offsets["bo_label_value"]`

### 5.6 位置退层逻辑

`markers.py` 原本已有"bo_score 无 broken_peak_ids 时退到 bo_label 位"的临时层逻辑。`bo_label_value` 沿用同模式：构造 `layers` 时按实际需要追加 `bo_label_value`，`compute_marker_offsets_pt` 自动处理累积偏移；如果只有 `bo_label_value` 而没有 `bo_score`，则通过同样的 `tmp_layers` 模式退一层。

## 6. 配置与兼容性

### 6.1 `configs/ui_config.yaml`

`ui.display_options` 段：
- 新增 `show_bo_label: false`
- 删除死键 `show_peak_score`（代码无引用，早期残留）

```yaml
ui:
  display_options:
    show_bo_score: true
    show_bo_label: false        # 新增
```

`dev/config/ui_loader.py::get_display_options_defaults()` 是 `dict.get(key, default)` 的泛型读取，不需要改。

### 6.2 向后兼容

- `draw_breakouts` 新参数 `show_label=False` / `label_n=20` 默认关闭，已有调用方（canvas_manager）只在 dev 分支显式传入；其他路径行为不变
- `display_options.get(key, default)` 保证旧字典不缺键报错

### 6.3 Live 模式

完全不影响：
- `draw_breakouts_live_mode` 不动
- `live/` 下 pipeline / UI 不动
- BO Label checkbox 不出现在 live 窗口（live 用独立 UI）

## 7. 测试计划

### 7.1 `analysis/tests/test_label_helper.py`（新文件）

- `test_compute_label_value_basic`：构造 df，基础公式正确
- `test_compute_label_value_insufficient_data`：`len(future_data) < max_days` 返回 `None`
- `test_compute_label_value_zero_price`：突破日 close ≤ 0 返回 `None`
- `test_calculate_labels_uses_helper`：`FeatureCalculator._calculate_labels` 输出与直接调 helper 等价（回归保护）

### 7.2 `UI/charts/components/tests/test_marker_offsets.py`（扩展）

- `test_compute_marker_offsets_with_label_value`：
  `compute_marker_offsets_pt(["triangle", "peak_id", "bo_label", "bo_score", "bo_label_value"])` 累计偏移
- `test_compute_marker_offsets_label_only`：开 BO Label、关 BO Score 时的偏移

### 7.3 Tier 分类测试（`UI/charts/components/tests/test_bo_label_value.py`，新文件）

用 `SimpleNamespace` 构造 BO（参考 `test_marker_offsets.py:117` 现有做法，不启动 tk）：

- 3 个 BO value 分别 0.1 / 0.3 / 0.2 → 第二个 `max`，其他 `other`
- value 并列最大（0.3 / 0.3 / 0.1）→ 前两个都 `max`
- value 包含 `None` → `None` 不参与比较，不绘制

### 7.4 Manual QA

- 加载含多 BO 的 scan，勾选 "BO Label"，marker 出现在 bo_score 上方
- 只勾选 "BO Label"（关 BO Score），marker 退到 bo_score 位
- Spinbox N = 10 / 20 / 40，观察 marker 值即时切换
- 切换股票，N 保留；加载新 scan，N 按新 scan metadata 重置
- 最近几个 BO 窗口不足 N 天 → 不显示 label value
- 多 BO 中最大值用黄底、其他橙底

## 8. 文件改动清单

| 文件 | 改动 |
|---|---|
| `analysis/features.py` | 新增 `compute_label_value()`；`_calculate_labels()` 改为调 helper；修正 docstring |
| `UI/styles.py` | `MARKER_STACK_GAPS_PT` 增 `bo_label_value: 30`；新增 `BO_LABEL_VALUE_TIER_STYLE` |
| `UI/charts/components/markers.py` | `draw_breakouts()` 加 `show_label / label_n`；两遍结构：先算 values + max，再 tier-aware 绘制 |
| `UI/charts/canvas_manager.py` | 读 `display_options["show_bo_label"]` / `["bo_label_n"]`，传给 `draw_breakouts` |
| `dev/panels/parameter_panel.py` | 新增 "BO Label" checkbox + N Spinbox；`get_display_options()` 扩展；新增 `set_bo_label_n_default()` |
| `dev/main.py` | scan 加载后调 `parameter_panel.set_bo_label_n_default(max_days)` |
| `configs/ui_config.yaml` | 新增 `show_bo_label: false`；删除死键 `show_peak_score` |
| `analysis/tests/test_label_helper.py` | 新文件 |
| `UI/charts/components/tests/test_marker_offsets.py` | 扩展 |
| `UI/charts/components/tests/test_bo_label_value.py` | 新文件，承载 tier 分类测试 |
