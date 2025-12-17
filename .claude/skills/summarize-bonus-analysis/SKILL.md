---
name: summarize-bonus-analysis
description: Use when a bonus combination statistical report (bonus_combination_*.md) has been generated and needs a structured summary with core findings, factor tiers, and actionable recommendations. Triggered after running bonus_combination_analysis.py or when user asks to interpret/summarize bonus statistics.
---

# Summarize Bonus Analysis

## Overview

将原始统计报告（含 Spearman 相关、level 分布、组合分析、交互效应、RF 特征重要性、Pattern 分析）转化为面向决策的结构化总结。核心原则：**每条结论必须有数据支撑 + 因果解读，禁止泛泛而谈**。

## 输入

- 统计报告：`docs/statistics/bonus_combination_*.md`（由 `bonus_combination_analysis.py` 生成）

## 输出

- 总结报告：`docs/statistics/bonus_combination_*_summary.md`（同目录，文件名加 `_summary` 后缀）

## 分析方法论

### Step 1: 建立因子排名

从 Spearman 相关系数表提取排名，区分：
- **强正相关** (r > 0.10, p < 0.001)
- **弱正相关** (0 < r < 0.10)
- **无效** (p > 0.05 或 |r| < 0.01)
- **负相关** (r < 0, p < 0.05)

### Step 2: 验证 level 单调性

对每个因子的 level 分布表，检查 median 是否随 level 递增：
- **完美单调递增** → 强信号（如 Height: 0.1261 → 0.2146 → 0.2647 → 0.3394）
- **倒 U 型** → 非线性效应，需注意最佳区间（如 Drought: level 1 最佳）
- **单调递减** → 反向指标（如 Streak: 0.1956 → 0.1732 → 0.1128）
- **平坦/无规律** → 无效因子

### Step 3: 识别交互模式

从交互效应矩阵中：
- 找出"增效器"因子：与多数因子正交互的（如 Volume 占 top 5 正交互 4 席）
- 找出负交互对：同时触发反而不如单独出现的
- 注意交互效应方法的局限（未控制其他因子的混杂）

### Step 4: 评估多因子共振

从 "n_triggered vs label" 表：
- 检查 median 是否随触发数量单调递增
- 关注高触发数量区间的样本量衰减（n < 30 时结论不可靠）
- 量化共振幅度：max_median / min_median

### Step 5: 因子分层

综合 Spearman r、RF 重要性、level 单调性、交互能力，将因子分为四层：

| 层级 | 标准 | 处置方向 |
|------|------|---------|
| **核心因子** | r > 0.10 且 level 单调递增且 RF 重要性 top 5 | 高权重保留 |
| **辅助因子** | r > 0 且 p < 0.001 但 r < 0.10 或 RF 较低 | 适中权重保留 |
| **无效因子** | p > 0.05 或 r ≈ 0 或 level 无区分度 | 降权/禁用 |
| **反向因子** | r < 0 且 p < 0.001 且 level 单调递减 | 反转评分方向 |

### Step 6: 可操作建议

从因子分层直接推导：
- 核心因子 → 是否需要上调权重？
- 反向因子 → 评分方向反转的具体建议
- 无效因子 → 是否有下游依赖（如 Pattern 分类）决定能否移除
- 筛选漏斗 → 分层门槛建议（硬性门槛 → 加分确认 → 高信心信号）

### Step 7: 诚实标注局限性

必须覆盖的局限性维度：
- **模型解释力**：R² < 0.1 说明因子仅解释部分方差
- **小样本组合**：n < 50 的组合结论不可靠
- **label 定义偏差**：label_10_40 是峰值收益非实际可获收益
- **主导因子过拟合风险**：RF 重要性 > 0.5 的因子需样本外验证
- **交互效应混杂**：简单差值法未控制第三方因子

## 输出结构

```markdown
# Bonus 组合分析总结报告
> 基于 [日期] 统计报告，样本量 N 个突破事件

## 1. 报告概述
一段话：范围 + 主要发现（最强因子是谁、最意外的发现）

## 2. 核心发现
按重要性排序，每条包含：
### 2.x [发现标题]
**结论**：一句话
**数据支撑**：引用具体数字（r 值、median、level 分布）
**解读**：因果推理，解释 WHY

## 3. 因子分层
四层分类表，每个因子给出 r、RF、层级、理由
特殊情况单独说明（如 Overshoot 的反直觉正相关）

## 4. 可操作建议
### 4.1 评分模型调整（具体乘数建议）
### 4.2 筛选策略（分层漏斗）
### 4.3 后续验证方向

## 5. 注意事项与局限性
每条局限用具体数字支撑（如 R²=0.1051 而非"解释力有限"）

## 附：因子效能速查表
一张包含 排名/因子/r/RF/层级/建议方向 的汇总表
```

## 反直觉结果的处理

遇到名称与数据矛盾的因子（如 "惩罚" 因子但正相关），必须：
1. 承认矛盾，不回避
2. 给出至少两种可能的解释（如幸存者偏差、动量延续、测量窗口错位）
3. 检查交互矩阵是否提供线索（如 Volume+Overshoot 负交互揭示子类差异）
4. 给出审慎的处置建议（设为中性而非仓促反转）

## 常见错误

| 错误 | 正确做法 |
|------|---------|
| 只列数字不解释因果 | 每条结论后必须有 **解读** 段 |
| 忽视样本量 | 任何引用的组合/level 都注明 n |
| 把 median 和 mean 混用 | 优先用 median（不受极端值影响） |
| 忽略反向因子 | 负 r 因子需要单独分析，不能简单跳过 |
| 对 R² 低的结论过度自信 | 必须在局限性中说明因子仅解释部分方差 |