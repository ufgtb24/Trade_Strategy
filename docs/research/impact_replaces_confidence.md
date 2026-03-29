# Impact 替代 Confidence 方案分析

> 2026-03-24 | Agent Team 研究报告

## 问题

当前 LLM 返回 `(sentiment, confidence, reasoning)`。是否应该用 `impact`（新闻对股价的影响大小）替代 `confidence`（LLM 对判断的确信度），使其成为 sentiment 强度的唯一衡量维度？

## 核心论点

impact 是比 confidence 更本质的属性。在选股场景中，我们关心的是"这条新闻对股票影响有多大"，而非"LLM 多确定这是正面/负面"。如果 impact 很大，sentiment × impact 就是完整的情绪信号。

## 分析结论

### 1. 理论合理性：替代方案多维度优于现状

| 维度 | confidence (现状) | impact (替代方案) |
|------|------------------|------------------|
| 语义本质 | 二阶判断（关于判断的判断） | 一阶属性（事件本身的属性） |
| 可验证性 | 不可验证 | 可回溯验证（事件是否确实产生了大影响） |
| rho 含义 | 置信加权极性比 | 影响力加权极性比（更贴近选股意图） |
| evidence 含义 | 平均 LLM 自信度 | 平均影响力（少量重磅 > 大量花边） |

confidence 在当前系统中的四重角色全部可被 impact 替代：
- 失败标记（conf=0.0）→ impact=0.0
- 极性加权因子（w_p/w_n）→ impact 加权更合理
- 证据充分性（evidence）→ impact 加权平均更有意义
- 排序/展示 → 直接替换

聚合公式结构完全不变，仅替换加权因子：`w = impact_i × tw_i`

### 2. LLM 能力评估：impact 不是更难，而是更适合 LLM

**confidence = 元认知任务（向内看）**
- LLM 没有真正的 uncertainty estimator
- 输出是模式匹配而非自省，存在 overconfidence bias
- 数值集中在 0.7-0.9 区间，区分力差

**impact = 领域知识任务（向外看）**
- LLM 预训练含海量金融案例，擅长知识检索 + 分类映射
- FDA 批准/拒绝、并购、诉讼等事件的影响量级是确定性知识
- 分类型判断（选等级）比元认知自省更可靠

### 3. 推荐实现：离散等级 impact

```
negligible: 对股价几乎无影响（<0.5%）  → 0.05
low:        轻微影响（0.5-2%）         → 0.2
medium:     中等影响（2-5%）           → 0.5
high:       重大影响（5-15%）          → 0.8
extreme:    剧烈影响（>15%）           → 1.0
```

离散等级优于连续值的理由：
- 输出一致性高（分类 >> 回归）
- 百分比锚点解决标定模糊问题
- LLM 分类准确率远高于连续值回归
- 映射表可独立调优

### 4. Prompt 设计

```
你是一个金融新闻影响力分析专家。评估以下新闻对该股票价格的潜在影响。
仅返回JSON：{"sentiment": "positive|negative|neutral", "impact": "negligible|low|medium|high|extreme", "reasoning": "一句话理由"}
impact等级: negligible(<0.5%), low(0.5-2%), medium(2-5%), high(5-15%), extreme(>15%)
```

### 5. 成本

Token 消耗与当前方案无差异（输出格式相同）。

### 6. 注意事项

- 现有聚合参数（`_K`, `_BETA`, `_SCARCITY_N` 等）基于 confidence 分布校准，impact 分布不同，需要重新调参
- impact=0.0 同时标记"无影响"和"分析失败"，功能上等价（两者都应排除在方向性加权之外）
- 不同行业/市值公司对同一事件的 impact 可能不同，但在粗粒度离散等级下差异可接受

## 实施路径

1. `_llm_utils.py` — 替换 SYSTEM_PROMPT，输出 impact 替代 confidence
2. `models.py` — SentimentResult 中 confidence → impact，增加 IMPACT_MAP 映射表
3. `analyzer.py` — `_summarize` 中 `conf` 替换为 `impact` 数值（映射后），公式结构不变
4. 重新校准聚合参数（`_K`, `_BETA` 等）
5. 清理缓存（已缓存的 sentiment 结果不含 impact）