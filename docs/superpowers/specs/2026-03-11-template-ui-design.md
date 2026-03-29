# Template UI Integration Design

## 概述

将组合模板（factor_filter.yaml）的选择和使用集成到 UI 中，用模板筛选突破，在 stock list 中显示匹配数量，在 K 线图中高亮匹配突破。

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `BreakoutStrategy/UI/panels/template_panel.py` | TemplatePanel — 左侧面板上部的模板列表 UI 组件 |
| `BreakoutStrategy/UI/managers/template_manager.py` | TemplateManager — 模板加载与匹配业务逻辑（纯逻辑，无 UI） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `BreakoutStrategy/UI/panels/parameter_panel.py` | 添加模板文件下拉框 + "Use Template" 复选框 |
| `BreakoutStrategy/UI/panels/__init__.py` | 导出 TemplatePanel |
| `BreakoutStrategy/UI/managers/__init__.py` | 导出 TemplateManager |
| `BreakoutStrategy/UI/panels/stock_list_panel.py` | 支持动态添加/移除 `t_count` 列 |
| `BreakoutStrategy/UI/charts/components/markers.py` | 新增 `draw_template_highlights()` |
| `BreakoutStrategy/UI/charts/canvas_manager.py` | `update_chart()` 接受 `template_matched_indices` 参数 |
| `BreakoutStrategy/UI/main.py` | 编排 4 种场景的状态管理与刷新逻辑 |

### 模板文件目录

`configs/templates/` — 存放 factor_filter*.yaml 文件（与 `configs/params/` 分开）。

## 组件设计

### 1. TemplateManager（业务逻辑层）

```python
class TemplateManager:
    def load_filter_yaml(self, path: str) -> dict:
        """加载 factor_filter YAML，提取 templates/thresholds/negative_factors/sample_size"""

    def match_breakout(self, bo_data: dict, template: dict) -> bool:
        """单个突破是否匹配模板（逐因子检查阈值）"""

    def match_stock(self, stock_result: dict, template: dict) -> list[int]:
        """返回匹配的突破索引列表"""

    def match_all_stocks(self, scan_data: dict, template: dict) -> dict[str, list[int]]:
        """批量匹配，返回 {symbol: [matched_bo_indices]}"""
```

匹配逻辑：对模板的每个因子，检查突破原始值是否达到阈值。正向因子 `>=`，反向因子 `<=`。因子值直接从 breakout dict/对象中读取（JSON 缓存和 full computation 路径均可用）。

### 2. ParameterPanel 新增控件

在现有 Display Options 区域之后添加 Separator + 模板组：

```
| [separator] | ☐ [▼factor_filter.yaml (disabled)] |
```

- 复选框未勾选 → 下拉框 disabled（灰色），与参数配置的交互模式一致
- 复选框勾选 → 下拉框 readonly，启用模板筛选
- 下拉框扫描 `configs/templates/*.yaml`
- 提供回调: `on_use_template_changed_callback`, `on_template_file_changed_callback`

### 3. TemplatePanel（左侧面板 UI）

位于左侧面板顶部，stock list 上方：

```
┌─ Templates ──────────────────┐
│   Name              Med  N  R│
│ ● vol+str+day..    0.60 115 1.3%│
│ ○ age+vol+pk..     0.51  23 0.3%│
│ ...  (共 10 行，按 Med 降序)   │
└──────────────────────────────┘
```

- `ttk.Treeview` 单选模式
- 3 列: Med (median), N (count), R (count/total 百分比)
- 按 median 降序排列
- 面板高度固定（~250px），未加载 YAML 时隐藏
- 选中模板 → 回调 `on_template_selected_callback`

### 4. StockListPanel 动态列

- `add_t_count(matched_dict)` — 注入 t_count 值到 stock_data，追加列
- `remove_t_count()` — 移除 t_count 字段和列
- `update_t_count(matched_dict)` — 更新已有 t_count 值并刷新

### 5. 图表高亮条

`MarkerComponent.draw_template_highlights(ax, df, matched_indices)`:
- 使用 `axvspan(idx-0.4, idx+0.4)` 绘制全 Y 轴高度的垂直半透明带
- 颜色: `#00FF00`，alpha=0.15，zorder=0（在所有元素之下）

`ChartCanvasManager.update_chart()` 新增参数 `template_matched_indices`，在绘制完成后调用高亮绘制。

## 状态管理（main.py）

### 新增状态

```python
self.template_manager = TemplateManager()
self.template_matched = {}          # {symbol: [matched_bo_indices]}
self.current_template_matches = []  # 当前显示股票的匹配索引
```

### 四种场景

**场景 1: 先有 stock list → 勾选 Use Template**
```
_on_use_template_changed(enabled=True)
  → match_all_stocks(scan_data, selected_template)
  → stock_list_panel.add_t_count(matched)
  → 重绘当前 K 线图（带高亮条）
```

**场景 2: 先勾选 Use Template → load/new scan**
```
load_scan_results() 完成
  → 正常加载 stock list
  → 检查 use_template 已勾选?
    → 是: match_all_stocks + add_t_count
```

**场景 3: 取消勾选**
```
_on_use_template_changed(enabled=False)
  → stock_list_panel.remove_t_count()
  → 清空 template_matched
  → 重绘 K 线图（无高亮条）
```

**场景 4: 切换模板**
```
_on_template_selected(new_template)
  → 如果 use_template 已勾选:
    → match_all_stocks(scan_data, new_template)
    → stock_list_panel.update_t_count(matched)
    → 重绘 K 线图
```

### _on_stock_selected 适配

在现有 `_on_stock_selected` 方法末尾，检查 template 状态：
- 如果 use_template 已勾选，从 `template_matched[symbol]` 获取匹配索引
- 传递给 `chart_manager.update_chart(..., template_matched_indices=indices)`
