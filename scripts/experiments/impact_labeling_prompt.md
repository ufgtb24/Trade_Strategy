## 项目上下文

Trade_Strategy 项目的 `BreakoutStrategy/news_sentiment` 模块负责采集股票新闻并进行情感分析。每条新闻由 LLM 分析后产出 sentiment（正/负/中性）和 impact（影响等级：negligible/low/medium/high/extreme）。多条新闻通过聚合公式（`analyzer.py:_summarize`）汇总为单一的 `sentiment_score`（有符号连续评分）用于选股决策。

本 prompt 是参数校准流程的一部分。完整流程见 `scripts/experiments/CALIBRATION_GUIDE.md`。

---

## 任务

读取 `scripts/experiments/impact_scenarios.json`，对每个场景进行 AI 双 agent 标注，生成综合 sentiment 判断和 sentiment_score。

标注结果写入 `scripts/experiments/impact_baseline.json`。

---

## 背景

我们的新闻情感聚合公式需要校准参数。为此我们设计了一组合成场景（每个场景包含若干条抽象新闻标签），需要"人类金融分析师视角"的标注作为 ground truth。标注结果将用于后续公式参数搜索的目标值。

每个场景的 items 是 `[{"s": sentiment, "impact": level}, ...]` 的抽象标签组合，不含具体新闻内容。你需要模拟一个经验丰富的投资分析师，综合考虑所有 items 后给出整体判断。

---

## 双 Agent 标注流程

### Agent 1（金融分析师角色）

使用 tom（Opus 4.6 模型）作为 Agent 1。

**Agent 1 的 Prompt 要求：**

你是一位拥有 15 年经验的机构投资分析师。你需要对每个场景中的新闻组合做出综合判断，给出：
- `sentiment`：整体情绪方向（positive / negative / neutral）
- `sentiment_score`：有符号连续评分，范围 [-1.0, +1.0]
- `reasoning`：简短推理说明（1-2 句，说明为何给出此判断）

你不是在运行公式，而是在用你的投资直觉和经验做判断。想象这些是你今天早上浏览新闻终端时看到的某只股票相关信息的影响力标签。

### Agent 2（审核员角色）

使用 tom（Opus 4.6 模型）作为 Agent 2。

**Agent 2 的 Prompt 要求：**

你是一位资深投资组合经理，负责审核分析师的情绪评估。逐一检查 Agent 1 的每个场景结果：
1. sentiment 方向是否符合投资逻辑？
2. sentiment_score 的幅度是否合理？是否存在过度自信或过度保守？
3. 是否遵循了下方列出的标注原则（尤其是损失厌恶、scarcity 保护、negligible 近乎透明等）？

如果发现问题，直接修正 sentiment、sentiment_score 和 reasoning。修正时在 reasoning 中简要说明修改原因。

### 执行方式

0. **预处理（必须）**：在标注开始前，编写并运行一个 Python 脚本，读取 `impact_scenarios.json`，对每个场景生成结构化摘要（按 sentiment × impact 分组计数，如 `"5 positive(low), 1 positive(extreme), 1 neutral"`）。后续标注和审核均以此摘要为准，禁止手动数 items。
1. 调用 Agent 1，将摘要与原始 items 一同提供，对所有场景完成标注
2. 调用 Agent 2 对 Agent 1 的结果逐一审核，不符合则修正
3. 两个 Agent 都使用 Opus 4.6 模型

---

## 输入格式

读取 `scripts/experiments/impact_scenarios.json`，格式如下：

```json
[
    {
        "id": 1,
        "items": [{"s": "positive", "impact": "extreme"}]
    },
    ...
]
```

每个 item 的字段：
- `s`：新闻情绪标签（"positive" / "negative" / "neutral"）
- `impact`：影响力等级（"negligible" / "low" / "medium" / "high" / "extreme"）

---

## impact 等级权重关系

五个等级按影响力递增排列：negligible << low < medium < high << extreme

等级间差距是**高度非线性**的：
- negligible 是信息噪音，对判断几乎无贡献
- extreme 是公司级别的转折事件，单条即可主导判断
- 1 条 extreme 的信号强度远大于 10 条 negligible 的总和

---

## sentiment_score 定义

- 范围：**[-1.0, +1.0]**
- positive sentiment → 正值
- negative sentiment → 负值
- neutral sentiment → 0（或极接近 0）
- 不确定性余量应与信号强度成反比——信号越强（样本越多、impact 越高、冲突越少），余量越小

### 评分锚点

以下是不同场景强度对应的 |score| 参考范围。标注时应**充分利用**整个评分区间：

| 场景强度 | 典型配置 | 正面 |score| | 负面 |score| |
|---------|---------|--------------|--------------|
| 极弱 | 少量 negligible 同向 | 0.02 - 0.08 | 0.03 - 0.12 |
| 弱 | 少量 low 同向，或强冲突场景 | 0.08 - 0.25 | 0.11 - 0.35 |
| 中等 | 数条 medium/high 同向 + 少量反向 | 0.25 - 0.50 | 0.33 - 0.65 |
| 强 | 多条 high 同向 + 无/极少反向 | 0.50 - 0.75 | 0.60 - 0.90 |
| 极强 | 大样本纯方向 + 含 high/extreme + 无反向 | 0.75 - 0.95 | 0.85 - 1.00 |

**损失厌恶说明**：负面列的范围已内置损失厌恶偏移——同等配置下负面比正面更高。这种偏移在弱信号端更显著（约 1.4-1.5 倍），在极强信号端因评分上限自然收敛（约 1.05-1.1 倍）。标注时直接参照对应列即可，无需额外计算倍率。

---

## 标注原则（关键，必须严格遵循）

### 1. 损失厌恶
同等 impact 等级下，**负面新闻的心理权重约为正面的 1.5-2 倍**。这符合行为金融学中的前景理论：投资者对损失的敏感度天然高于收益。例如，1 条 medium negative 的影响应大于 1 条 medium positive。

### 2. Scarcity 保护
**方向性新闻不足 3 条时，不应给出高 |sentiment_score|**（即使方向完全一致）。原因：样本太少时判断缺乏统计支撑，经验丰富的分析师会保持克制。

### 3. Impact 主导
**1 条 extreme 新闻的权重应远大于多条 negligible/low 新闻**。不要简单数人头。5 条 low positive 的信号强度应低于 1 条 high positive。判断时以最高 impact 的新闻为锚点，低 impact 新闻仅提供微弱的方向确认。

### 4. Negligible 近乎透明
**大量 negligible 新闻不应产生显著的 sentiment_score**。negligible 是信息噪音，数量再多也不会质变。

### 5. 冲突压低
**正负力量平衡时 sentiment_score 接近 0**，无论 impact 等级多高。正负冲突意味着市场信号矛盾，分析师会持观望态度。

### 6. Neutral 不稀释
**neutral 新闻是背景噪音，不应降低方向性信号的强度**。neutral 新闻只是"没有新的信息"，不构成反向证据。

---

## 输出格式

将标注结果写入 `scripts/experiments/impact_baseline.json`，格式如下：

```json
[
    {
        "id": 1,
        "sentiment": "positive",
        "sentiment_score": 0.22,
        "reasoning": "单条 extreme positive 信号强，但样本不足限制判断，分析师会保持谨慎"
    },
    ...
]
```

字段说明：
- `id`：与 impact_scenarios.json 中的 id 一致
- `sentiment`：整体情绪方向（positive / negative / neutral）
- `sentiment_score`：有符号连续评分，范围 [-1.0, +1.0]，保留 2 位小数
- `reasoning`：简短推理说明（中文，1-2 句话）

---

## 重要提醒

1. **不要迭代公式设计**：专注于模拟投资分析师的认知来完成标注。不要试图逆向工程任何公式，也不要用数学公式来推算 sentiment_score。纯粹用投资直觉和标注原则来判断。
2. **仅根据 items 列表判断**：每个场景只看 items 中的 (sentiment, impact) 组合，不参考其他信息。
3. 标注完成后，使用 `scripts/experiments/analysis_prompt.md` 的指引进行公式对比分析（独立任务，不在本次标注中执行）。
