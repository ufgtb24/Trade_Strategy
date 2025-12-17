---
name: bonus-system-gap-analysis
description: Use when a bonus statistical analysis and summary report are available and need to be compared against the current system implementation (scorer config, pattern classification logic) to identify gaps between statistical conclusions and actual system behavior.
---

# Bonus System Gap Analysis

## Overview

对比统计分析结论与评分系统的实际实现（配置参数、代码逻辑），找出"数据说应该这样，但系统实际那样"的缺口。核心原则：**每个缺口必须量化偏差幅度，并给出可操作的修复建议和优先级**。

## 输入

1. **统计报告**：`docs/statistics/bonus_combination_*.md`
2. **总结报告**：`docs/statistics/bonus_combination_*_summary.md`
3. **系统实际状态**（需主动收集）：
   - 评分器配置：`configs/params/scan_params.yaml` → `quality_scorer` 段
   - 评分器代码：`BreakoutStrategy/analysis/breakout_scorer.py` → 各 bonus 方法
   - Pattern 分类：`breakout_scorer.py` → `_classify_pattern()` 方法

## 输出

- 缺口分析报告：`docs/research/bonus_system_gap_analysis_[版本号].md`

## 分析方法论

### Phase 1: 收集系统现状

**必须收集的信息**：

```
对每个 bonus 因子：
├── enabled: true/false
├── thresholds: [阈值列表]
├── values (multipliers): [乘数列表]
├── 代码中的默认值（与 YAML 是否一致？）
└── 是否参与 _classify_pattern()
```

### Phase 2: 缺口识别

系统性扫描 5 类缺口：

**3a. 方向错误**（最严重）
- 检查条件：Spearman r < 0 但 multiplier > 1.0（或反之）
- 量化指标：r 值 × 受影响样本比例
- 示例：Streak r=-0.1936 但 values=[1.20, 1.40]

**3b. 权重失衡**
- 计算方法：对每个因子算 `ln(max_multiplier)` 得到权重占比，与 `|r| / sum(|r|)` 对比
- 严重失衡标准：权重占比与 r 占比偏差 > 10 个百分点
- 构造荒谬场景说明影响（如 "Height level 3 + Age level 3 同时触发 → 1.4×1.5=2.1x 但 Age 对收益无贡献"）

**3c. 因子缺席**
- 检查 Pattern 分类使用了哪些因子，与因子有效性排名对比
- 关注：最强因子是否参与分类？无效因子是否是分类核心输入？

**3d. 非线性效应未处理**
- 检查 level 分布是否呈倒 U 型（level 1 最佳，level 2/3 回落）
- 对比当前 multiplier 是否线性递增
- 示例：Drought level 1 median 最佳，但 values=[1.2, 1.3, 1.5] 线性递增

**3e. 配置同步问题**
- 检查代码中的默认值（`config.get("thresholds", [...])` 的回退值）是否与 YAML 一致
- 检查分析脚本读取的阈值是否与评分器使用的一致

### Phase 3: 权重失衡量化

**标准分析模板**：

```
1. 列出所有因子的最大乘数
2. 计算 ln(乘数) 得到对数权重
3. 求权重占比 = ln(该因子) / sum(ln(所有因子))
4. 计算 r 占比 = |r_该因子| / sum(|r_所有正向因子|)
5. 偏差 = 权重占比 - r 占比
6. |偏差| > 10pp → 标记为严重失衡
```

输出一张包含所有因子的汇总表（见输出结构）。

### Phase 4: Pattern 分类审计

构建一张模式审计表：

| 模式名 | 判定条件 | 所用因子有效性 | 样本量 | median | 评价 |
|--------|---------|--------------|--------|--------|------|

关键检查：
- 依赖无效因子（r ≈ 0）的模式 → 标记为"伪模式"
- 最大类别（如 `momentum` 占 58%）→ 区分度不足
- 反向因子驱动的模式（如 `trend_continuation` 由 Streak 驱动）→ 标签语义误导
- 提出重构方向：哪些因子应替代哪些因子

### Phase 5: 行动优先级

**优先级框架**：

| 优先级 | 标准 | 典型类型 |
|--------|------|---------|
| **P0** | 方向完全错误 + 影响大量样本 | Streak 反转 |
| **P1** | 权重严重失衡 + 实施简单（改 YAML） | 乘数调整、禁用无效因子 |
| **P2** | 结构性问题 + 需要改代码 | Pattern 重构、代码同步 |
| **P3** | 数据收集/验证型 | 新增统计维度 |

**分阶段实施建议**：
- Phase 1：纯 YAML 修改（零代码变更，最低风险，最高回报）
- Phase 2：代码修改（Pattern 重构等）
- Phase 3：数据收集与重新验证

每条行动需标注：ID、优先级、描述、类型、预期影响、实施难度、前置依赖。

## 输出结构

```markdown
# Bonus 系统缺口分析报告 ([版本号])
> 基于 [日期] 统计报告（N 个样本）的系统审计。

## 一、缺口清单
### 1.x [Px] [缺口名称]（GAP-0x）
**问题描述**：...
**量化对比**：具体数字表
**当前系统状态**：配置/代码现状
**根本原因**：...

## 二、权重失衡量化分析
### 2.1 理想权重 vs 当前权重
全因子汇总表（乘数 / ln权重 / 权重占比 / r / r占比 / 偏差）
### 2.2 最严重的失衡点
用具体场景说明荒谬性

## 三、Pattern 分类系统缺口
### 3.1 核心结构问题
模式审计表
### 3.2 重构方向
伪代码示例

## 四、行动优先级总结
合并行动表 + 分阶段实施建议

## 五、核心结论
3-5 条最关键洞察
```

## 常见错误

| 错误 | 正确做法 |
|------|---------|
| 只说"权重不合理"不量化 | 必须算出 ln 权重占比和偏差百分点 |
| 建议移除因子时忽略下游依赖 | 检查 _classify_pattern() 是否依赖该因子 |
| Overshoot 等反直觉结果简单建议"禁用" | 深入分析交互矩阵，区分子场景 |
| 行动建议不分阶段 | 必须区分 YAML-only vs 代码修改 vs 数据收集 |
| 忽略代码/配置同步问题 | 检查代码默认值与 YAML 是否一致 |