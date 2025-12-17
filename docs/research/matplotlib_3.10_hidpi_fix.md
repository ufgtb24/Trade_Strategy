# Matplotlib 3.10 高 DPI 环境 K 线图比例失调问题

## 问题描述

从 conda 环境 (matplotlib 3.8.0) 迁移到 uv 环境 (matplotlib 3.10.8) 后，UI 中的 K 线图出现严重的比例失调问题：
- 图表元素和字体变得非常大
- 图表超出容器显示范围
- 现象表现为：图表先正常显示，然后"闪烁"一下变大

## 环境信息

```
Tk scaling: 2.3362202081235313
Screen DPI: 168.20785498489425
Matplotlib: 3.10.8
Tcl/Tk: 8.6.12
Platform: Linux (高 DPI 显示器)
```

## 根本原因

### PR #28588 引入的变更

Matplotlib 3.9+ 通过 [PR #28588](https://github.com/matplotlib/matplotlib/pull/28588) 为 Linux 平台引入了 HiDPI 支持。

在 `matplotlib/backends/_backend_tk.py` 中新增了 Linux 平台的 `device_pixel_ratio` 计算：

```python
# matplotlib 3.8.0 (仅 Windows)
def _update_device_pixel_ratio(self, event=None):
    ratio = round(self._tkcanvas.tk.call('tk', 'scaling') / (96 / 72), 2)
    # ...

# matplotlib 3.10.0 (新增 Linux 支持)
def _update_device_pixel_ratio(self, event=None):
    ratio = None
    if sys.platform == 'win32':
        ratio = round(self._tkcanvas.tk.call('tk', 'scaling') / (96 / 72), 2)
    elif sys.platform == "linux":
        ratio = self._tkcanvas.winfo_fpixels('1i') / 96  # <-- 新增
    # ...
```

### 事件触发机制

Matplotlib 在 TkAgg 后端初始化时绑定了 `<Map>` 事件：

```python
# _backend_tk.py
self._tkcanvas.bind("<Map>", self._update_device_pixel_ratio)
```

当 canvas widget 被映射到屏幕时（`pack()` 执行后），`<Map>` 事件触发，调用 `_update_device_pixel_ratio()`。

### 计算结果

在 168 DPI 环境下：
```
device_pixel_ratio = winfo_fpixels('1i') / 96
                   = 168 / 96
                   = 1.75
```

Matplotlib 内部会将所有渲染放大 1.75 倍，导致图表超出容器边界。

### 为什么 3.8.0 正常

在 matplotlib 3.8.0 中：
- Linux 平台**不绑定** `<Map>` 事件到 `_update_device_pixel_ratio`
- `device_pixel_ratio` 保持默认值 **1.0**
- 渲染按 1:1 进行，显示正常

## 解决方案

### 核心思路

在创建 `FigureCanvasTkAgg` 后、执行 `pack()` 前，解绑 `<Map>` 事件，阻止 matplotlib 自动检测和应用 DPI 缩放。

### 实现代码

在 `BreakoutStrategy/UI/charts/canvas_manager.py` 中添加：

```python
def _disable_auto_dpi_scaling(self):
    """
    禁用 matplotlib 3.9+ 的自动 DPI 缩放

    matplotlib 3.9+ 在 Linux 上会通过 <Map> 事件自动检测屏幕 DPI 并缩放渲染，
    导致高 DPI 环境下图表超出容器边界。此方法通过解绑 <Map> 事件来禁用此行为。

    参考: matplotlib/backends/_backend_tk.py (PR #28588)
    """
    if self.canvas is None:
        return

    # 获取底层 Tk canvas widget
    tk_canvas = self.canvas.get_tk_widget()

    # 解绑 <Map> 事件，阻止 matplotlib 自动调用 _update_device_pixel_ratio
    tk_canvas.unbind("<Map>")

    # 强制设置 device_pixel_ratio 为 1.0（如果方法存在）
    if hasattr(self.canvas, '_set_device_pixel_ratio'):
        self.canvas._set_device_pixel_ratio(1.0)
```

### 调用位置

在 `update_chart()` 方法中，创建 canvas 后立即调用：

```python
# 4. 嵌入Tkinter Canvas
self.canvas = FigureCanvasTkAgg(self.fig, master=self.container)

# 禁用 matplotlib 3.9+ 的自动 DPI 缩放 (PR #28588)
self._disable_auto_dpi_scaling()

self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
self.canvas.draw()
```

## 尝试过但失败的方案

### 方案 1：补偿 figsize

尝试在计算 `figsize` 时除以 `device_pixel_ratio` 进行反向补偿：

```python
device_pixel_ratio = self._get_device_pixel_ratio()
fig_width = container_width / dpi / device_pixel_ratio
fig_height = container_height / dpi / device_pixel_ratio
```

**失败原因**：初始渲染正确（图表变小），但 `<Map>` 事件随后触发，matplotlib 再次应用 1.75x 缩放，导致最终图表仍然过大。

### 方案 2：Patch `_update_device_pixel_ratio` 方法

尝试将方法替换为空操作：

```python
self.canvas._update_device_pixel_ratio = lambda event=None: None
```

**失败原因**：Tkinter 的 `bind()` 在初始化时已保存原始方法的引用，patch 后的新方法不会被调用。

## 版本兼容性

此修复方案具有良好的兼容性：
- **Matplotlib 3.8.x 及更早**：`unbind("<Map>")` 不会产生副作用（本来就没绑定）
- **Matplotlib 3.9+**：成功禁用自动 DPI 缩放
- **Windows/macOS**：同样安全，不会影响正常功能

## 参考资料

- [PR #28588: Fix scaling in Tk on non-Windows systems](https://github.com/matplotlib/matplotlib/pull/28588)
- [PR #22898: Only set Tk scaling-on-map for Windows systems](https://github.com/matplotlib/matplotlib/pull/22898)
- [Issue #10388: Add retina screen support for TkAgg backend](https://github.com/matplotlib/matplotlib/issues/10388)
- [Matplotlib 3.10.0 Release Notes](https://matplotlib.org/stable/users/prev_whats_new/whats_new_3.10.0.html)

## 诊断脚本

用于诊断环境 DPI 信息的脚本：

```python
import tkinter as tk
import matplotlib

root = tk.Tk()
print(f"Tk scaling: {root.tk.call('tk', 'scaling')}")
print(f"Screen DPI: {root.winfo_fpixels('1i')}")
print(f"Matplotlib: {matplotlib.__version__}")
print(f"Tcl/Tk: {root.tk.call('info', 'patchlevel')}")
root.destroy()
```

---

**文档创建时间**: 2024-12-26
**问题影响版本**: matplotlib >= 3.9.0
**修复验证版本**: matplotlib 3.10.8
