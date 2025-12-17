# Pattern Label UI Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 pattern_label 完整集成到 UI 各环节：JSON 序列化、Stock List 表格列、图表标注

**Architecture:** 三层修改 — (1) 数据持久化层：scan_manager 序列化 breakout 时写入 pattern_label; (2) 列表展示层：stock_list_panel 从 breakouts 聚合每只股票的主导模式; (3) 图表渲染层：markers.py 在突破分数旁显示模式缩写

**Tech Stack:** Python, tkinter (ttk.Treeview), matplotlib

---

## Task 1: JSON 序列化补上 pattern_label

**Files:**
- Modify: `BreakoutStrategy/UI/managers/scan_manager.py:401-466`

**Step 1: 在 breakout 序列化字典中添加 pattern_label 字段**

在 `_scan_single_stock()` 函数的 breakout 序列化块 (约 line 455，`"annual_volatility"` 之后，`"labels"` 之前) 添加：

```python
                    # 模式标签
                    "pattern_label": getattr(bo, 'pattern_label', 'basic'),
```

注意：`pattern_label` 是在 `BreakoutScorer.score_breakout()` 中动态设置到 Breakout 对象上的属性（非 dataclass field），所以用 `getattr` 安全访问。

**Step 2: 验证**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.UI.managers.scan_manager import _scan_single_stock; print('import ok')"`
Expected: `import ok`

**Step 3: Commit**

```bash
git add BreakoutStrategy/UI/managers/scan_manager.py
git commit -m "fix: serialize pattern_label in scan results JSON"
```

---

## Task 2: Stock List 表格增加 pattern 列

**Files:**
- Modify: `BreakoutStrategy/UI/panels/stock_list_panel.py:452-513` (load_data 方法)
- Modify: `configs/ui_config.yaml` (列配置)

**Step 1: 在 load_data() 中计算 pattern 统计量**

在 `stock_list_panel.py` 的 `load_data()` 方法中，在 `# 4. 初始化 label 字段` 之前（约 line 508），添加 pattern 聚合计算：

```python
            # 5. 计算主导模式标签
            patterns = [bo.get("pattern_label", "basic") for bo in breakouts]
            if patterns:
                # 排除 basic，找出最常见的非基础模式
                non_basic = [p for p in patterns if p != "basic"]
                if non_basic:
                    from collections import Counter
                    item["pattern"] = Counter(non_basic).most_common(1)[0][0]
                else:
                    item["pattern"] = "basic"
            else:
                item["pattern"] = ""
```

同时把原来的 `# 4.` 注释改为 `# 6.`：

```python
            # 6. 初始化 label 字段（根据当前选择的类型）
```

**Step 2: 在 ui_config.yaml 中添加 pattern 列配置**

在 `column_labels` 中添加 `pattern` 配置（在 `multi_peak_count` 之前）：

```yaml
      pattern:
        display: Pattern
        tooltip: 'Pattern: Dominant breakout pattern (momentum, historical, etc.)'
```

在 `column_priority` 列表中的 `label` 之后、`multi_peak_count` 之前添加 `pattern`：

```yaml
    - pattern
```

在 `visible_columns` 中添加 `pattern`（在 `label` 之后）：

```yaml
    - pattern
```

**Step 3: 验证**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.UI.panels.stock_list_panel import StockListPanel; print('import ok')"`
Expected: `import ok`

**Step 4: Commit**

```bash
git add BreakoutStrategy/UI/panels/stock_list_panel.py configs/ui_config.yaml
git commit -m "feat: add pattern column to stock list table"
```

---

## Task 3: 图表突破点标注模式缩写

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/markers.py:114-251` (draw_breakouts 方法)

**Step 1: 定义模式缩写映射**

在 `draw_breakouts` 方法内，`colors` 初始化之后（约 line 138）添加模式缩写映射：

```python
        # 模式标签缩写映射
        pattern_abbr = {
            "momentum": "MOM",
            "historical": "HIST",
            "volume_surge": "VOL",
            "dense_test": "TEST",
            "trend_continuation": "TREND",
            "deep_rebound": "D.REB",
            "power_historical": "P.HIST",
            "grind_through": "GRIND",
        }
```

**Step 2: 在分数旁添加模式标签**

在 score 文本绘制逻辑之后（约 line 229 之后），添加 pattern label 绘制。将模式缩写紧贴在分数右侧（用 score_y 相同高度但 x 偏移），或者放在分数文本下方。

考虑到分数已在上方、peak IDs 在下方，最佳方案是**将 pattern 缩写附加到分数文本中**，改变分数显示格式为 `"72 MOM"` 而不是单独的 `"72"`。

修改现有的 score 文本绘制代码（line 212-229），将分数文本改为包含 pattern：

找到这段代码（约 line 212-229）：
```python
                ax.text(
                    bo_x,
                    score_y,
                    f"{bo.quality_score:.0f}",
```

改为：
```python
                # 构建分数文本：包含模式缩写
                score_text = f"{bo.quality_score:.0f}"
                p_label = getattr(bo, 'pattern_label', None)
                if p_label and p_label != "basic":
                    abbr = pattern_abbr.get(p_label, p_label[:4].upper())
                    score_text = f"{bo.quality_score:.0f} {abbr}"

                ax.text(
                    bo_x,
                    score_y,
                    score_text,
```

其余 `ax.text()` 参数保持不变。

**Step 3: 验证**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && python -c "from BreakoutStrategy.UI.charts.components.markers import MarkerComponent; print('import ok')"`
Expected: `import ok`

**Step 4: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/markers.py
git commit -m "feat: display pattern abbreviation on chart breakout markers"
```

---

## Task 4: 端到端验证

**Step 1: 全模块导入验证**

```python
from BreakoutStrategy.UI.managers.scan_manager import _scan_single_stock, ScanManager
from BreakoutStrategy.UI.panels.stock_list_panel import StockListPanel
from BreakoutStrategy.UI.charts.components.markers import MarkerComponent
from BreakoutStrategy.UI.charts.components.score_tooltip import ScoreDetailWindow
from BreakoutStrategy.analysis.breakout_scorer import BreakoutScorer, ScoreBreakdown
print("All imports OK")
```

**Step 2: pattern_label 序列化验证**

选择一只有突破的股票进行单股扫描，验证输出 JSON 中 breakout 字典包含 `pattern_label` 字段。

**Step 3: Commit (如有修复)**

```bash
git add -A
git commit -m "fix: end-to-end verification fixes for pattern label UI"
```
