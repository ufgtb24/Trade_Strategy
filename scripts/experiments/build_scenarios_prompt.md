## 项目上下文

Trade_Strategy 项目的 `BreakoutStrategy/news_sentiment` 模块负责采集股票新闻并进行情感分析。每条新闻由 LLM 分析后产出 sentiment（正/负/中性）和 impact（影响等级：negligible/low/medium/high/extreme）。多条新闻通过聚合公式（`analyzer.py:_summarize`）汇总为单一的 `sentiment_score`（有符号连续评分）用于选股决策。

本 prompt 是参数校准流程的一部分。完整流程见 `scripts/experiments/CALIBRATION_GUIDE.md`。

---

## 任务

在 `scripts/experiments/impact_scenarios.json` 中生成 40-50 个合成新闻场景，用于 news_sentiment 模块的 impact 聚合公式参数校准。

## 背景

news_sentiment 模块使用离散 impact 等级作为加权因子。每条新闻有两个属性：
- `s`: sentiment 方向 — "positive" / "negative" / "neutral"
- `impact`: 影响等级 — "negligible" / "low" / "medium" / "high" / "extreme"

## 输出格式

生成一个 JSON 数组，每个元素结构如下：

```json
{
    "id": 1,
    "items": [
        {"s": "positive", "impact": "extreme"}
    ]
}
```

字段说明：
- `id`: 从 1 开始的连续编号
- `items`: 新闻条目列表，每条包含 `s`（sentiment 方向）和 `impact`（影响等级）

## 分层要求

按新闻条数分为 4 层，总共 40-50 个场景：

### edge 层（1-2 条新闻，8-10 个场景）
测试极端稀缺场景：
- 单条各 impact 等级的 positive/negative（包括 neg low、neg negligible 等低 impact 负面基准）
- 2 条同方向不同 impact 组合
- 2 条冲突方向不同 impact 组合
- 1 extreme + 1 negligible 同方向

### cold 层（3-6 条新闻，10-12 个场景）
测试小样本下的方向一致性和冲突处理：
- 方向一致但 impact 不同（如 3P: high + low + negligible）
- **纯负面方向一致**（如 4N: medium × 4）— 校准负面聚合行为
- 方向冲突混合（如 2P + 1N，不同 impact）
- 全 negligible positive
- 全 neutral
- 含 neutral 的混合（如 2 neutral + 1 positive(high)）
- 少量 low positive + 单条 extreme negative（不对称冲突）
- **数量不对称 + impact 对称**（如 3P(high) vs 1N(high)）— 测试数量 vs impact 权衡

### medium 层（7-12 条新闻，12-15 个场景）
测试中等样本的多 impact 混合：
- 多 impact 等级全覆盖混合
- neutral 占多数（如 7 neutral + 2 positive(extreme) + 1 negative(negligible)）
- 高 impact vs 低 impact 对比（如 5 条 low positive vs 1 条 extreme positive + 填充 neutral）
- 方向平衡冲突（如 5P + 5N 全 medium）
- 偏向性但含少量反向高 impact
- 大量 low + 少量 high 的混合
- **纯负面中样本**（如 8N: low × 5 + high × 3）— 校准负面方向的累积行为
- **neutral 大量 + 少量低 impact 方向性**（如 8 neutral + 2 pos low）— 测试 neutral 对弱信号的稀释效果

### hot 层（15-20 条新闻，10-12 个场景）
测试大样本下的信号稀释和主导效应：
- 高 negligible 占比（15 条 negligible + 2-3 条方向性）
- extreme 单条主导（1 条 extreme positive + 大量 neutral/negligible）
- 大量 neutral 稀释
- 均匀 impact 分布
- 全 low 大样本（方向一致但单条权重低）
- 大量冲突混合（各种 impact）
- **纯负面大样本**（如 15N: low × 12 + high × 3）— 确保负面方向不欠拟合

## 必须覆盖的特有场景

以下场景必须**精确匹配**出现在最终结果中（不要添加额外条目）。可分配到任何合适的层级：

1. **单条 extreme positive** — 测试稀缺保护
2. **单条 extreme negative** — 测试稀缺 + 损失厌恶
3. **5 条 low positive + 1 条 extreme positive**（恰好 6 条）— 测试 impact 等级区分
4. **3 条 low positive + 1 条 extreme negative** — 测试不对称冲突
5. **10 条 negligible positive** — negligible 近乎无贡献
6. **3 neutral + 2 positive(extreme) + 1 negative(negligible)** — neutral 不稀释方向性信号
7. **5P + 5N 全 medium** — 完美冲突
8. **15P + 5U 全 low** — 大样本低 impact（U = neutral）
9. **2P(medium) + 1N(high)** — 正负力量接近时的方向判定边界 + 高比例反向惩罚测试
10. **1P(medium) + 3N(low)** — 镜像的方向判定边界 + 负面方向的反向惩罚测试

## 设计原则

### 正负对称性
场景集必须对正面和负面方向有足够的独立覆盖。**每个非 edge 层至少 1 个纯负面场景**（仅含 negative items，无 positive/neutral）。否则负面方向的公式参数无法独立校准。

### 避免冗余
不要生成测试相同能力的重复场景。以下是常见冗余陷阱：
- "5P + 5N 全 medium" 和 "8P + 8N 全 medium" 测试相同的平衡冲突能力 — 只保留一个
- "5x negligible positive" 和 "10x negligible positive" 测试相同的 negligible 无贡献 — 只保留一个
- "15 pos low + 5 neutral low" 和 "18x pos low" 测试高度相似的大样本低 impact 累积 — 至少一个应换成负面方向

### 反向惩罚参数覆盖
公式中 positive 和 negative 分支各有一个"反向惩罚"参数（positive 被 negative 反对、negative 被 positive 反对）。这两个参数只在**主导方向 + 存在少量反向新闻**的场景中生效。因此：
- **positive 主导 + 含 negative**（如 4P(low) + 2N(low)）的场景至少 4 个，且反向 impact 权重占比应有分散（轻微反对 ~ 强烈反对）
- **negative 主导 + 含 positive**（如 3N(low) + 2P(low)）的场景至少 4 个，同样需要权重占比分散
- 纯方向性场景（无反向新闻）对这两个参数无约束力，不应过多

### 控制变量
至少包含 2 组"仅改变一个维度"的对照场景。例如：
- 同 impact、不同数量比（如 3P(high) vs 1N(high)，和 6P(high) vs 2N(high)）
- 同数量比、不同 impact（如 3P(low) vs 1N(low)，和 3P(high) vs 1N(high)）

## 质量检查清单

生成完成后，请自行验证：

1. 总场景数在 40-50 之间
2. 每层场景数符合要求（edge 8-10, cold 10-12, medium 12-15, hot 10-12）
3. 上述 10 个必须覆盖的特有场景全部**精确匹配**（不多不少）
4. 所有 5 种 impact 等级至少各出现 3 次
5. 所有 3 种 sentiment 方向至少各出现 10 次
6. cold/medium/hot 每层至少 1 个纯负面场景
7. "positive 主导 + 含 negative" 场景至少 4 个
8. "negative 主导 + 含 positive" 场景至少 4 个
9. 无高度冗余的场景对（测试相同能力、仅数量翻倍）
10. id 从 1 连续递增
11. JSON 格式正确，可被 `json.loads()` 解析
12. 每个 item 只有 `s` 和 `impact` 两个字段

## 输出

将完整 JSON 写入 `scripts/experiments/impact_scenarios.json`，不需要其他文件。
