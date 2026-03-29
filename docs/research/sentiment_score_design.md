# 情感评分选股应用方案设计

> 2026-03-24 | Agent Team 研究报告

## 问题

如何将情感分析结果应用于选股场景，要求量纲恒定、跨股票可比。

## 前提：跨股票可比性已验证

- **rho** 是比率指标，天然尺度不变（3正1负 vs 30正10负，rho 相同）
- **confidence** 中的 evidence 已归一化（加权平均而非总和），scarcity 保护小样本
- 不存在"新闻多 → 评分高"的系统性偏差，无需额外归一化

## 推荐方案：固定阈值 + 有符号连续评分

### 核心公式

```python
sentiment_score = sign(rho) * confidence
# sign: positive → +1, negative → -1, neutral → 0
# 范围: [-1.0, +1.0]（指数饱和曲线自然控制上限）
```

### 为什么不用 rho × confidence？

会双重编码极性强度（confidence 内部的 certainty 已是 |rho| 的放大函数），导致极端值过度压缩。

### 为什么不直接用 rho？

rho 只反映极性比例，不反映证据充分性。1条正面0条负面 → rho≈1.0，但 evidence 极弱。confidence 编码了"证据不足"，选股需要"方向对 + 证据足"。

### 阈值标准

```
score > +0.30  →  正面信号 (Bullish)
score ∈ [-0.15, +0.30]  →  中性 (Neutral)
score < -0.15  →  负面信号 (Bearish)
```

阈值非对称：负面阈值更敏感（-0.15 vs +0.30），体现选股中"排除坏股比选入好股更重要"。

### 选股决策模式

| 使用方式 | 规则 | 说明 |
|---------|------|------|
| 硬过滤 | score >= -0.15 | 排除明确负面股票 |
| 正面加分 | score >= +0.30 | 多因子模型中加分 |
| 否决权 | score < -0.40 | 强负面一票否决 |
| 排序 | 按 score 降序 | 同等条件优先情感更好的 |

### SummaryResult 新增字段

```python
rho: float = 0.0              # 极性分数 [-1, 1]
sentiment_score: float = 0.0  # sign(rho) * confidence [-0.80, +0.80]
```

### 实现

在 `_summarize()` 返回前计算：
```python
sign = 1 if sentiment == 'positive' else (-1 if sentiment == 'negative' else 0)
sentiment_score = round(sign * confidence, 4)
```

## 横向比较方案（不推荐一期实施）

不推荐原因：rho 已天然可比、需额外基础设施、批次依赖、行业基线差异是真实信号不应归一化。
如未来需要同行业比较，可在 sentiment_score 之上叠加百分位计算。
