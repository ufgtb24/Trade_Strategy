## 项目上下文

Trade_Strategy 项目的 `BreakoutStrategy/news_sentiment` 模块负责采集股票新闻并进行情感分析。每条新闻由 LLM 分析后产出 sentiment（正/负/中性）和 impact（影响等级：negligible/low/medium/high/extreme）。多条新闻通过聚合公式（`analyzer.py:_summarize`）汇总为单一的 `sentiment_score`（有符号连续评分）用于选股决策。

本 prompt 是参数校准流程的一部分。完整流程见 `scripts/experiments/CALIBRATION_GUIDE.md`。

---

## 任务

读取 AI 标注结果和聚合公式代码，逐场景对比公式输出与 AI 标注，生成差异分析报告。

**注意**：本任务应在标注完成后单独执行，不要与标注任务混合。

---

## 输入文件

1. `scripts/experiments/impact_scenarios.json` — 场景定义
2. `scripts/experiments/impact_baseline.json` — AI 标注结果
3. `BreakoutStrategy/news_sentiment/analyzer.py` — 聚合公式源码（`_summarize` 方法）

---

## 公式计算要求

对每个场景，精确复制 `analyzer.py:_summarize` 的完整逻辑计算公式输出：

### impact 值映射

```
negligible → 0.05
low        → 0.20
medium     → 0.50
high       → 0.80
extreme    → 1.00
```

### 计算注意事项

- 时间权重全部设为 1.0（合成场景无时间信息）
- 包含 evidence 归一化：`evidence = (w_p + w_n) / tw_sum_dir`
- 包含 scarcity 保护：`scarcity = min(1.0, n_dir / SCARCITY_N)`
- 三分支计算（positive / negative / neutral）
- sentiment_score = sign(rho) × confidence
- 使用 analyzer.py 中**当前**的参数值

---

## 输出

保存分析报告到 `scripts/experiments/labeling_analysis.md`，格式如下：

```markdown
# Impact 标注 vs 公式差异分析

## 概览
- 标注场景总数: N
- sentiment 方向匹配率: X/N (Y%)
- MAD (Mean Absolute Deviation): Z
- 最大偏差场景: ...

## 逐场景对比

| ID | AI Sentiment | AI Score | Formula Sentiment | Formula Score | Diff | 分析 |
|----|-------------|----------|-------------------|---------------|------|------|
| 1  | positive    | +0.22    | positive          | +0.35         | 0.13 | ...  |
| ...| ...         | ...      | ...               | ...           | ...  | ...  |

## 差异根本原因分析

（按差异类型归类：哪些是参数问题、哪些是公式结构问题、哪些是标注偏差）

## 公式改进方向

（哪些参数需要调整、调整方向、预期效果）
```

---

## 重要提醒

- 不要直接修改公式代码
- AI 标注和公式输出的 score 范围均为 [-1.0, +1.0]，可直接对比
- 关注系统性偏差（如公式是否在某类场景下普遍偏高/偏低），而非个别场景的随机偏差
