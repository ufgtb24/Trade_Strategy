## 项目上下文

Trade_Strategy 项目的 `BreakoutStrategy/news_sentiment` 模块负责采集股票新闻并进行情感分析。每条新闻由 LLM 分析后产出 sentiment（正/负/中性）和 impact（影响等级：negligible/low/medium/high/extreme）。多条新闻通过聚合公式（`analyzer.py:_summarize`）汇总为单一的 `sentiment_score`（有符号连续评分）用于选股决策。

本 prompt 是参数校准流程的一部分。完整流程见 `scripts/experiments/CALIBRATION_GUIDE.md`。

---

## 任务

改进 `BreakoutStrategy/news_sentiment/analyzer.py` 的 `_summarize` 聚合逻辑，使公式输出尽可能接近人类模拟基准，同时保持金融可解释性和结构简洁性。

你拥有完全的自主权来决定改进策略——可以调整参数、修改公式结构、或两者兼做。

---

## 输入文件

1. **`BreakoutStrategy/news_sentiment/analyzer.py`** — 聚合公式源码（`_summarize` 方法），直接阅读源码理解完整逻辑
2. **`scripts/experiments/impact_scenarios.json`** — 合成场景定义（43 个场景，每个场景包含若干 `{s, impact}` 条目）
3. **`scripts/experiments/impact_baseline.json`** — AI 模拟的人类分析师标注（每个场景的 sentiment + sentiment_score + reasoning）

<!-- 根据校准阶段选择以下之一，取消注释对应行 -->
<!-- 首次校准：使用 Step 3 差异分析报告 -->
<!--4. **`scripts/experiments/labeling_analysis.md`** — Step 3 差异分析报告（公式当前输出与标注的逐场景对比） -->
<!-- 迭代校准：使用上一轮 review 产出的技术债文档 -->
4. **`scripts/experiments/tech_debt.md`** — 上一轮校准的 review 报告（已知耦合、结构问题和改进方向）

---

## 公式的设计意图

`_summarize` 将多条新闻的 (sentiment, impact) 聚合为单一的 `sentiment_score ∈ [-1.0, +1.0]`。公式编码了以下金融直觉：

- **损失厌恶**：负面新闻的权重 > 正面新闻（LA 系数 + BETA 不对称放大）
- **证据饱和**：边际信息价值递减（指数饱和曲线 `1 - exp(-evidence/_K)`）
- **稀缺性保护**：方向性新闻 < 3 条时线性惩罚，防止单条新闻获得过高评分
- **冲突衰减**：正负严重对冲时 confidence 压低，分析师持观望态度

公式结构：`sentiment_score = sign(rho) × confidence`，其中 confidence = certainty × sufficiency × (1 - opp_penalty)。

---

## 下游使用

sentiment_score 是选股多因子模型的一个输入因子。使用方式：

- score > +0.30 → 正面加分
- score ∈ [-0.15, +0.30] → 中性
- score < -0.15 → 负面排除
- score < -0.40 → 强否决

核心需求：**跨股票可比、排序正确性 > 绝对精度**。0.35 和 0.42 的差异对决策无影响，但 0.25 和 0.35 的差异（跨越 +0.30 阈值）直接影响选股结果。

---

## 标注数据的使用说明

标注数据（`impact_baseline.json`）由 AI 双 Agent 模拟投资分析师直觉生成，不是真人标注。`calibration_path_analysis.md` 指出标注和公式编码了同一套金融知识（损失厌恶、scarcity 保护等），因此：

- 标注数据是**有价值的参考基准**，但不是绝对真理
- 方向一致性（sentiment 方向匹配）是**硬约束**——方向不一致说明公式有问题
- 数值偏差（|score diff|）是**软参考**——标注值本身有 ±0.05~0.10 的不确定性
- 如果发现某些场景的标注本身存疑，可以在报告中标注并说明理由

---

## 红线约束（不可违反）

1. **语义透明**：任何修改必须附带金融直觉解释。禁止纯数学拟合（如加多项式项逼近标注值）
2. **结构简洁**：参数总数 ≤ 当前的 13 个，公式分支数（positive/negative/neutral）不增加
3. **属性不退化**：
   - 单调性：同等条件下 positive 比例增加 → score 增加
   - 不对称性：镜像场景中 |negative_score| > |positive_score|
   - 饱和性：score 绝对值随 evidence 增加趋于上限而非无限增长
   - 跨样本量一致性：同比例组成的 cold(3-6条) vs hot(15-20条) 场景，score 差 < 0.10
4. **接口不变**：`_summarize` 的方法签名和返回类型（`SummaryResult`）不变
5. **可回滚**：报告中记录每项修改的旧值/新值/理由，支持选择性回滚

---

## 设计约束（强烈建议遵守）

### 参数正交性
一个宏观效果应由一个参数控制，而非多个参数在不同计算层级分别实现再级联相乘。多层级联会导致：调一个参数的效果被其他层放大或截断，难以预测总体影响。

### 参数独立性
每个参数应控制一个独立的语义维度。如果两个参数的效果高度重叠，应合并为一个。派生关系（一个参数由另一个参数乘以常数得到）必须在注释中明确标注。

### 阈值解耦
语义不同的阈值应使用独立参数，即使它们在数值上相关。避免用 `threshold = 参数A × 常数` 的形式将两个概念耦合——修改参数 A 时会产生意料之外的连锁反应。

---

## 验收标准

| 类型 | 标准 |
|------|------|
| 硬性 | 所有场景 sentiment 方向 100% 匹配 |
| 软性 | MAD（mean \|formula_score - baseline_score\|）< 0.08 |
| 约束 | 上述 4 条属性全部通过 |

---

## 交付物

1. **更新后的 `BreakoutStrategy/news_sentiment/analyzer.py`**
2. **校准报告 `scripts/experiments/calibration_report.md`**，包含：

### (a) 诊断发现
偏差模式分析：系统性偏高/偏低？特定场景类别（edge/cold/medium/hot）的差异？参数级问题还是结构级问题？

### (b) 修改清单
做了什么修改、为什么、每项修改的旧值 → 新值。

### (c) 消融分析
逐项修改的独立贡献量——恢复该修改后 MAD 变化多少。

### (d) 全场景对比表

| id | baseline_sent | formula_sent | baseline_score | formula_score | diff | match |
|----|---------------|--------------|----------------|---------------|------|-------|
| 1  | positive      | positive     | +0.45          | +0.43         | -0.02| Yes   |
| ...| ...           | ...          | ...            | ...           | ...  | ...   |

### (e) 属性验证结果
逐项验证单调性、不对称性、饱和性、跨样本量一致性是否通过。

---

## 工作方式

使用 ralph-loop 迭代。每轮自主决定做什么。

建议（非强制）的工作流程：
1. 阅读公式源码和已有分析报告，理解现状
2. 编写 Python 脚本计算当前公式在所有场景上的输出，分析偏差模式
3. 诊断问题根因（参数级 or 结构级）
4. 实施修改并验证
5. 迭代直到满足验收标准

---

## 启动命令

```
/ralph-loop:ralph-loop "根据人类模拟基准数据和分析报告对聚合公式进行迭代改进，使公式输出接近基准且满足红线约束" --completion-promise "方向匹配率>=95% AND MAD连续2轮无显著改善 AND 红线约束未被违反" --max-iterations 10
```
