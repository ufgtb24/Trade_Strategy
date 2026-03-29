# Template Self-Contained Params Design

## 概述

将模板文件（factor_filter.yaml）改为自包含扫描参数，启用模板时强制使用模板自带参数，禁用 Analysis Mode，保证数据挖掘结果的绝对有效性。

## 核心原则

1. 模板是自包含的数据挖掘产物，不依赖外部参数文件
2. 启用模板时，系统保证扫描参数与模板一致，用户无法修改扫描参数
3. 未启用模板时，现有所有功能完全不受影响
4. 灵活性边界：可调整模板阈值（不改变扫描参数），但本次不实现

## 数据模型

### factor_filter.yaml 新结构（version 4）

```yaml
_meta:
  version: 4
  generated_at: '...'
  data_source: '...'
  sample_size: 8770
  baseline_median: 0.1268
  min_count: 50
  generator: BreakoutStrategy.mining.threshold_optimizer
  total_templates: 10
  optimization:
    thresholds: { volume: 8.6415, pk_mom: 2.7552, ... }
    negative_factors: [age, height, overshoot, peak_vol, pk_mom, test]
    # ... 其他优化元数据不变

scan_params:                          # 新增：完整扫描参数快照
  breakout_detector:
    breakout_modes: [close]
    exceed_threshold: 0.01
    min_relative_height: 0.1
    min_side_bars: 6
    peak_measure: body_top
    peak_supersede_threshold: 0.01
    total_window: 20
  general_feature:
    atr_period: 14
    ma_period: 20
    stability_lookforward: 5
  quality_scorer:                     # 完整 quality_scorer 内容
    age_factor: { enabled: true, thresholds: [...], values: [...], mode: lte }
    streak_factor: { enabled: true, window: 10, thresholds: [...], values: [...] }
    pk_mom_factor: { enabled: true, lookback: 30, ... }
    # ... 所有因子
    # 排除: cache_dir, use_cache（运行时配置，不影响计算）

templates:
  - name: volume+pk_mom+streak+pbm+day_str+drought
    factors: [volume, pk_mom, streak, pbm, day_str, drought]
    count: 279
    median: 0.3408
    q25: 0.1119
  # ...
```

嵌入策略：全量嵌入 breakout_detector / general_feature / quality_scorer 三个 section，排除 `cache_dir` 和 `use_cache`。由 `threshold_optimizer.py` 生成时自动嵌入。

### 兼容性检测

`TemplateManager.check_compatibility(scan_metadata)` 比较模板 `scan_params` 与 JSON `scan_metadata` 中的：
- `detector_params` 全部字段（7 个）
- `feature_calculator_params` 中影响因子计算的字段（atr_period, ma_period, stability_lookforward, gain_window, pk_lookback, continuity_lookback）

完全匹配为兼容，否则返回不匹配字段列表。

## UI 交互流程

### 模式关系

```
未选 "Use Template"              选中 "Use Template"
┌──────────────────────┐        ┌──────────────────────┐
│ Browse / Analysis    │        │ Template Mode         │
│ 自由切换             │  ────► │ 强制 Browse Mode      │
│ 参数随意修改         │        │ Analysis 控件禁用     │
│ 模板面板隐藏         │  ◄──── │ 模板面板显示          │
└──────────────────────┘        └──────────────────────┘
```

### 勾选 "Use Template" 时

```
勾选 Use Template
  -> 加载模板文件，读取 scan_params
  -> 强制切换到 Browse Mode，禁用 Analysis 控件
  -> 显示 template list 面板
  -> 当前有 stock list?
    |-- 无 -> 等待用户 Load 或 New Scan
    +-- 有 -> 检查 scan_metadata 兼容性
         |-- 兼容 -> 直接执行模板匹配（毫秒级）
         +-- 不兼容 -> 弹出三选一对话框：
              [Rescan]  -> 用模板参数执行 New Scan
              [Load]    -> 打开文件对话框（预过滤兼容文件）
              [Cancel]  -> 取消勾选，恢复原状态
```

### 禁用的控件（模板模式下）

| 控件 | 状态 |
|------|------|
| Analysis Mode 复选框 | disabled，强制 unchecked |
| 参数文件下拉框 | disabled |
| Edit 按钮 | disabled |
| Rescan All 按钮 | disabled |

### 保持可用的控件

| 控件 | 说明 |
|------|------|
| New Scan | 使用模板自带参数扫描 |
| Load Result | 预过滤兼容 JSON 文件 |
| 模板文件下拉框 | 可切换不同模板文件 |
| 显示选项（BO Score / SU_PK） | 不影响模板匹配 |

### 取消勾选 "Use Template"

隐藏模板面板 -> 移除 t_count 列 -> 清空匹配数据 -> 恢复 Analysis 控件可用 -> 重绘图表（无高亮）。当前 stock list 保留不清空。

### Load Result 预过滤

模板启用时，CustomFileDialog 只显示与模板参数兼容的 JSON 文件。通过读取每个 JSON 文件头部的 `scan_metadata` 进行轻量检测。

## New Scan 参数注入

模板模式下，`_start_new_scan` 和 `_start_background_rescan` 从 `TemplateManager.scan_params` 获取参数。

实现方式：`UIParamLoader` 新增类方法 `parse_params(raw_dict)`，接受原始参数字典，返回 (detector_params, feature_calculator_params, scorer_params) 三元组，复用现有参数验证逻辑，不污染单例状态。

`main.py` 提取公共方法 `_get_scan_params()` 根据模板状态决定参数来源。

## 文件改动

### 修改文件

| 文件 | 改动 |
|------|------|
| `BreakoutStrategy/mining/threshold_optimizer.py` | 生成时嵌入 scan_params，version 3->4 |
| `BreakoutStrategy/UI/managers/template_manager.py` | 解析 scan_params、check_compatibility()、get_scan_params() |
| `BreakoutStrategy/UI/panels/parameter_panel.py` | _update_combobox_state() 增加模板模式分支 |
| `BreakoutStrategy/UI/main.py` | 勾选流程（兼容性检查+三选一对话框）、Load 验证、New Scan 参数注入、_get_scan_params() |
| `BreakoutStrategy/UI/config/param_loader.py` | parse_params() 类方法 |
| `BreakoutStrategy/UI/dialogs/askopenfilename.py` | 模板模式下预过滤兼容 JSON |

### 不在本次范围

- 模板阈值编辑功能（用户标注为可选，后续独立迭代）
