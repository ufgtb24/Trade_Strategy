# K 线图交互行为重构

## 目标

重构 `AxesInteractionController` 的缩放/平移交互模型，并新增动态 Y 轴自适应。

## 变更概要

| 维度 | 当前 | 目标 |
|------|------|------|
| 默认缩放锚点 | 数据集最右 K 线（RIGHT_ALIGNED） | 鼠标位置 |
| Ctrl+缩放 | 切入 FREE 模式（永久） | 瞬态：按住 = 当前 view 最右可见 K 线锚点，松开 = 回鼠标 |
| 模式状态机 | RIGHT_ALIGNED ↔ FREE 持久双模式 | 无持久模式，Ctrl 是瞬态修饰键 |
| Y 轴 | 全局 OHLC min/max，固定不变 | 每次 xlim 变化后按可见 K 线 OHLC 重算 |
| Reset | 恢复 RIGHT_ALIGNED + initial_width | 恢复 initial xlim + 重算 Y 轴 |

## 1. 缩放锚点

### 1.1 默认（无 Ctrl）

`_on_scroll` 每次读 `event.xdata` 作为 `compute_zoom_xlim` 的 `mouse_x`。无状态，无模式切换。

### 1.2 Ctrl 按住

`_on_scroll` 检测 `is_ctrl_pressed()` 为 True 时，锚点 = 当前 view 最右侧可见 K 线的右边缘：

```python
anchor = min(ax.get_xlim()[1], len(df) - 0.5)
```

`len(df) - 0.5` 是数据集最后一根 K 线的右边缘（data coordinate）。取 `min` 确保：如果 xlim 右端超出数据范围（有 margin），锚点落在实际最右 K 线上。

Ctrl 松开后下一次 scroll 自动回到 `event.xdata` 锚点。无需"切回"操作。

### 1.3 controller 需要持有 df 长度

attach 时传入 `n_bars: int`（df 行数），用于计算 Ctrl 模式下的动态锚点 `min(xlim[1], n_bars - 0.5)`。

## 2. 平移

行为不变：左键按下 → 拖拽平移 → 松开。约束：
- `x1` 不超过 `right_anchor`
- `x0` 不低于 `data_span_left`

平移不涉及模式概念。

## 3. apply_constraints 简化

删除 `mode` 参数和模式切换逻辑。仅保留：
- 右边界 ceiling：`x1 >= right_anchor` → 整体左移到 `x1 = right_anchor`
- 左边界 clip：`x0 < data_span_left` → `x0 = data_span_left`
- 最小宽度：`x1 - x0 < min_width` → `x0 = x1 - min_width`

返回 `(x0, x1)` 而非 `((x0, x1), mode)`。

## 4. Reset 按钮

- 点击条件：`_needs_reset`（zoom_level 偏离 1.0 超过 1%，或 xlim 左端偏离初始值）
- 行为：恢复 initial xlim + 触发 Y 轴重算
- 样式：`_needs_reset` 为 True 时黑色，否则灰色（逻辑不变）

`_needs_reset` 新增判断 xlim 左端是否偏移（平移后 zoom_level 可能仍为 1.0 但视图已偏移）：

```python
@property
def _needs_reset(self) -> bool:
    if abs(self.zoom_level - 1.0) > 0.01:
        return True
    x0, _ = self._ax.get_xlim()
    initial_x0 = self._right_anchor - self._initial_width
    return abs(x0 - initial_x0) > 0.5
```

## 5. 动态 Y 轴自适应

### 5.1 数据源

当前可见范围内 df 行的 OHLC 价格（High 最大值 / Low 最小值）。不含 MA、标注。

### 5.2 计算

沿用现有 80/10/10 比例（`candlestick.py:draw_volume_background` 的逻辑）：

```python
price_min = visible_high_low_min
price_max = visible_high_low_max
price_range = price_max - price_min
display_height = price_range / 0.8
y_bottom = price_min - display_height * 0.1
y_top = y_bottom + display_height
ax.set_ylim(y_bottom, y_top)
```

### 5.3 触发时机

每次 `ax.set_xlim()` 之后立即调用 `_rescale_y()`。涉及位置：
- `_on_scroll`（缩放后）
- `_on_motion`（平移拖拽中）
- `reset()`（重置后）

### 5.4 controller 需要持有 df 引用

attach 时传入 df（或 High/Low 的 numpy array），用于按 xlim 范围切片计算。避免每次回调都做 pandas 操作，存储 `_highs: np.ndarray` 和 `_lows: np.ndarray`。

## 6. 删除的概念

- `MODE_RIGHT_ALIGNED` / `MODE_FREE` 常量和 `self.mode` 属性
- `_switch_to_free()` / `_switch_to_right_aligned()`
- `apply_constraints` 的 `mode` 参数和模式切换返回值
- `bar_anchor` attach 参数（被 `n_bars` 替代）

## 7. 保留的概念

- `right_anchor`：xlim 右边界上限（数据右端 + margin）
- `data_span_left`：xlim 左边界下限
- `initial_width`：Reset 恢复的窗口宽度
- `zoom_level` property
- `_needs_reset` property（逻辑增强）
- `_update_zoom_text()` / `_update_reset_button_style()`
- `is_panning` / pan 回调

## 8. 影响范围

| 文件 | 改动 |
|------|------|
| `UI/charts/axes_interaction.py` | 重写核心逻辑 |
| `UI/charts/canvas_manager.py` | attach 调用改签名（去 bar_anchor，加 n_bars + df 数据） |
| `UI/charts/tests/test_axes_interaction.py` | 重写模式相关测试，新增 Y 轴测试 |
| `live/app.py` | 若直接调用 interaction controller 则同步签名 |
