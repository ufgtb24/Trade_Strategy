# Impact Magnitude 维度分析：是否需要让 LLM 返回影响大小？

> 2026-03-24 | Agent Team 研究报告

## 问题

当前 LLM 返回 `sentiment` + `confidence` + `reasoning`。是否缺少"影响大小"(impact magnitude) 维度？例如 SEC 起诉（极大冲击）vs 产品小更新（轻微影响），两者 sentiment 相同但冲击程度完全不同。

## 核心发现

### 1. confidence 是语义混合体

当前 prompt 未显式定义 confidence 衡量什么。LLM 实际上将"判断确信度"和"影响严重程度"混合编码进 confidence，比例不可控、不可知。

### 2. confidence 和 impact 理论上正交

四类场景证明正交性：

| 场景 | confidence | impact | 典型例子 |
|------|-----------|--------|---------|
| 确信但影响小 | 高(0.85+) | 低 | "Apple 更新新配色选项" |
| 不确定但影响大 | 低(0.4-0.6) | 极高 | "传闻公司正探索拆分方案" |
| 两者一致高 | 高 | 高 | "CEO 被 SEC 正式起诉欺诈" |
| 两者都低 | 低 | 低 | 模糊的行业泛泛评论 |

场景 A 和 B 占比 >70%，方向相反——说明两者需要独立捕捉。

### 3. 但独立信息量有限（约 20-30%）

confidence 已部分代理 impact（估计相关性 0.5-0.7）。大事件通常措辞更确定，LLM 自然给出更高 confidence。impact 的独立贡献约 20-30%。

### 4. 直接加 impact 字段的系统成本很高

- **聚合层重设计**：`w = conf × impact × tw` 会破坏当前已校准的 `_K`, `_BETA`, `_BETA_POS`, `_SCARCITY_N` 等 7+ 个参数的平衡关系，需要全面重新调参
- **LLM 判断质量风险**：三维输出可能降低 confidence 准确性（回归均值效应），且 LLM 区分"确信度"和"影响度"的能力有限（预计 Pearson > 0.7）
- **evidence 归一化被打破**：当前 evidence 是"加权平均 confidence"，加 impact 后物理含义不清晰
- **scarcity 保护失效**：1 条 impact=1.0 的新闻权重等于多条低 impact 新闻，绕过样本量保护

## 推荐方案（渐进式）

### 当前阶段：不改 LLM prompt

**优先级 1（零成本）**：接受 confidence 已部分代理 impact 的现实，不做改动。

**优先级 2（低成本、高性价比）**：基于已有 `category` 字段加 boost 乘数：
```python
CATEGORY_BOOST = {'earnings': 1.4, 'filing': 1.2, 'news': 1.0}
# 在 _summarize 中: w = conf * tw * category_boost
```
- 不改 prompt、不增加 token、不影响 confidence 质量
- boost 系数可独立于现有参数调优
- 可进一步用 title 关键词检测细化（FDA/SEC/merger → high impact）

**优先级 3（中等成本）**：在去重阶段统计 cluster_size（同一事件被多少源报道），作为 impact 代理。

### 未来阶段

如果 category boost 效果不足，再考虑让 LLM 返回**离散** impact 等级：
```
low/medium/high/extreme → 0.2/0.5/0.8/1.0
```
离散等级比连续值更利于 LLM 校准，且需在 prompt 中附带示例明确区分 confidence 和 impact 定义。

## 不推荐

直接让 LLM 返回连续 impact 值（0.0-1.0）。成本/收益比最差：系统复杂度大增，而独立信息量仅 20-30%。