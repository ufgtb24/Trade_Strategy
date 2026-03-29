# Impact 替代 Confidence 完整开发计划

> 2026-03-25 | Agent Team 研究报告 (Task #3)

## Executive Summary

将 LLM 输出从 `confidence`(元认知自信度) 切换为 `impact`(事件对股价的影响等级)。公式结构不变，仅替换加权因子。核心工作量在于：(1) prompt/模型层改造，(2) 聚合参数重校准，(3) 缓存兼容处理。

本计划分 5 个阶段，总计约 7 个开发步骤，每步可独立验证。

---

## 一、开发阶段划分

```
Phase 1: 数据模型 + Prompt 改造 (无公式改动)
   |
Phase 2: 聚合公式适配 (结构不变，替换权重语义)
   |
Phase 3: 参数校准 (第一性原理 + 敏感性分析)
   |
Phase 4: 实验验证 (场景测试 + 回测对比)
   |
Phase 5: 缓存迁移 + 上线收尾
```

阶段间严格串行依赖：Phase N 完成后才能开始 Phase N+1。

---

## 二、每阶段具体任务

### Phase 1: 数据模型 + Prompt 改造

**目标**: LLM 返回 impact 等级，数据模型能承载新字段，现有代码编译通过。

#### Step 1.1: 修改 `models.py` — 新增 impact 字段和映射表

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/news_sentiment/models.py`

**改动内容**:

```python
# 在文件顶部新增映射常量
IMPACT_MAP: dict[str, float] = {
    "negligible": 0.05,
    "low": 0.20,
    "medium": 0.50,
    "high": 0.80,
    "extreme": 1.00,
}

@dataclass
class SentimentResult:
    """单条新闻的情感分析结果"""
    sentiment: str          # positive/negative/neutral (不变)
    confidence: float       # 保留向后兼容，新流程中 = impact_value
    reasoning: str          # 不变
    impact: str = ""        # 新增: 离散等级 (negligible/low/medium/high/extreme)
    impact_value: float = 0.0  # 新增: 映射后的数值 (0.05-1.0)
```

**设计决策**:
- 保留 `confidence` 字段不删除，确保向后兼容（旧缓存记录仍可读取）
- 新代码路径使用 `impact_value` 作为权重
- `confidence` 在新流程中设为 `impact_value` 的别名值，旧代码路径不感知差异

#### Step 1.2: 修改 `_llm_utils.py` — 替换 SYSTEM_PROMPT

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/news_sentiment/backends/_llm_utils.py`

**改动内容**:

1. 替换 `SYSTEM_PROMPT`:
```python
SYSTEM_PROMPT = (
    "你是一个金融新闻影响力分析专家。评估以下新闻对该股票价格的潜在影响。\n"
    '仅返回JSON：{"sentiment": "positive|negative|neutral", '
    '"impact": "negligible|low|medium|high|extreme", "reasoning": "一句话理由"}\n'
    "impact等级: negligible(<0.5%), low(0.5-2%), medium(2-5%), high(5-15%), extreme(>15%)"
)
```

2. 修改 `_obj_to_result()`:
```python
def _obj_to_result(obj: dict) -> SentimentResult:
    """将 JSON 对象转为 SentimentResult"""
    impact_str = obj.get('impact', '')
    # 向后兼容: 如果 LLM 返回旧格式 (confidence)，走降级路径
    if impact_str and impact_str in IMPACT_MAP:
        impact_val = IMPACT_MAP[impact_str]
    else:
        # fallback: 使用 confidence 值 (旧格式兼容)
        impact_str = ''
        impact_val = float(obj.get('confidence', 0.0))

    return SentimentResult(
        sentiment=obj.get('sentiment', 'neutral'),
        confidence=impact_val,      # 向后兼容: confidence = impact_value
        reasoning=obj.get('reasoning', ''),
        impact=impact_str,
        impact_value=impact_val,
    )
```

3. 修改 `DEFAULT_SENTIMENT`:
```python
DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", confidence=0.0, reasoning="Analysis failed",
    impact="", impact_value=0.0,
)
```

**注意**: 需要在 `_llm_utils.py` 顶部导入 `IMPACT_MAP`:
```python
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult, IMPACT_MAP
```

#### Step 1.3: 验证 Step 1 完成度

- 运行现有单元测试（如有），确保编译通过
- 手动调用 LLM 分析 3-5 条新闻，确认返回格式正确
- 确认 `impact_value` 落入 {0.05, 0.2, 0.5, 0.8, 1.0} 之一

---

### Phase 2: 聚合公式适配

**目标**: `analyzer.py` 中用 `impact_value` 替代 `confidence` 作为加权因子。公式数学结构完全不变。

#### Step 2.1: 修改 `analyzer.py` — `_summarize` 方法

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/news_sentiment/analyzer.py`

**改动范围**: `_summarize` 方法的 Step 0 分组统计部分

**当前代码** (第 199-213 行):
```python
for i, item in enumerate(analyzed_items):
    s, c = item.sentiment.sentiment, item.sentiment.confidence
    tw = item_tw[i]
    if c == 0.0:
        fail_count += 1
        continue
    if s == 'positive':
        pos_confs.append(c)
        pos_tw.append(tw)
    elif s == 'negative':
        neg_confs.append(c)
        neg_tw.append(tw)
    else:
        neu_valid += 1
        neu_tw_sum += tw
```

**修改为**:
```python
for i, item in enumerate(analyzed_items):
    s = item.sentiment.sentiment
    iv = item.sentiment.impact_value  # 使用 impact_value 替代 confidence
    tw = item_tw[i]
    if iv == 0.0:
        fail_count += 1
        continue
    if s == 'positive':
        pos_confs.append(iv)   # 变量名保留为 pos_confs 以减少改动
        pos_tw.append(tw)
    elif s == 'negative':
        neg_confs.append(iv)
        neg_tw.append(tw)
    else:
        neu_valid += 1
        neu_tw_sum += tw
```

**关键点**: 其余公式代码（Step 1-5）完全不需要改动。`w_p`, `w_n`, `rho`, `evidence`, `sufficiency` 等的计算逻辑不变——只是输入从 "confidence 值" 变成了 "impact_value 值"。

**附加改动**: 缓存写入判断条件（`analyzer.py` 第 133 行）:
```python
# 原: if sent.confidence > 0:
# 改:
if sent.impact_value > 0:
```

#### Step 2.2: 更新 `_generate_reasoning` 中的显示文本

- `"strength"` 后面显示的 `w_p`/`w_n` 值在 impact 语境下含义变为"累计影响力"，但数值格式无需改变
- 可选：在 reasoning 模板中将 "strength" 改为 "impact weight" 以提高可读性

#### Step 2.3: 更新 `SummaryResult` 文档字符串

- `rho` 的 docstring 从 "置信加权极性比" 改为 "影响力加权极性比"
- `confidence` 在 SummaryResult 层面含义不变（它是聚合后的系统 confidence，不是 LLM confidence）

---

### Phase 3: 参数校准

**目标**: 为 impact 分布确定最优聚合参数。

#### 3.1 参数分析：哪些需要调，哪些不需要

| 参数 | 当前值 | 是否需要调整 | 理由 |
|------|--------|-------------|------|
| `_DELTA` | 0.1 | **不变** | 死区阈值与 rho 比例相关，与绝对权重值无关。rho 是归一化的比例指标，impact 替换 confidence 后 rho 的值域 [-1,1] 不变 |
| `_CAP` | 1.0 | **已改为 1.0** | 移除人为硬上限，指数饱和曲线自然控制实际上限 |
| `_W0_RHO` | 0.1 | **不变** | neutral 在 rho 分母的名义权重，与加权因子量级无关（n_u 是计数不是加权和） |
| `_ALPHA` | 0.5 | **不变** | 失败惩罚强度，与权重分布无关 |
| `_LA` | 1.02 | **基本不变** | 损失厌恶系数是行为偏差设计，微调即可 |
| `_K` | 0.55 | **需要调整** | evidence 饱和速度。当前 `_K=0.55` 适配归一化 evidence [0,1]。impact 的 evidence 也是归一化的（平均 impact_value），值域 [0.05, 1.0]，但分布中心可能偏移（impact 分布中心约 0.4-0.5 vs confidence 约 0.7），需要重新确定 |
| `_GAMMA` | 0.40 | **可能需要微调** | positive 被 negative 反对的惩罚系数。impact 场景下高 impact 负面新闻的惩罚效应可能需要调整 |
| `_BETA` | 2.2 | **可能需要微调** | negative certainty 放大系数。取决于 impact 分布下 rho 的典型值域 |
| `_BETA_POS` | 1.15 | **可能需要微调** | 同 _BETA |
| `_OPP_NEG` | 0.20 | **可能需要微调** | 同 _GAMMA |
| `_K_NEU` | 2.47 | **不变** | 纯 neutral 饱和速度基于计数 n_u，不受 impact 影响 |
| `_SCARCITY_N` | 3 | **不变** | 方向性新闻最少条数，基于计数 |
| `_CONFLICT_POW` | 3.0 | **不变** | 冲突型 neutral balance 幂次，基于 w_p/w_n 比值，比值本身不受 impact 值域影响 |
| `_CONFLICT_CAP` | 0.15 | **不变** | 冲突型 neutral confidence 天花板，设计决策 |

**结论**: 核心需要调整的参数是 `_K`（1 个必须），`_GAMMA`, `_BETA`, `_BETA_POS`, `_OPP_NEG`（4 个可能微调）。

#### 3.2 第一性原理推导参数范围

**_K (evidence 饱和速度)**:

公式: `sufficiency = CAP × (1 - exp(-evidence / K))`

其中当前 `evidence = 平均 impact_value = (w_p + w_n) / (n_p + n_n)` (归一化后)

- confidence 分布: 集中在 0.6-0.8，均值约 0.70
- impact 分布: 离散 5 档 {0.05, 0.2, 0.5, 0.8, 1.0}

需要估算典型新闻的 impact 分布。基于金融新闻的经验分布：
- 大部分日常新闻: negligible 或 low (约 60%)
- 有一定影响的: medium (约 25%)
- 重大事件: high (约 12%)
- 极端事件: extreme (约 3%)

加权平均 evidence 期望: `0.6×0.125 + 0.25×0.5 + 0.12×0.8 + 0.03×1.0 = 0.075 + 0.125 + 0.096 + 0.03 = 0.326`

对比 confidence 的 evidence 均值约 0.70，impact evidence 约 0.33，降低了约 53%。

**推导 K 的合理范围**:
- 饱和曲线的特征: 当 evidence = K 时，sufficiency ≈ 0.63 × CAP
- 我们希望 "典型中等场景"(evidence ≈ 0.4-0.5) 达到约 50-60% 的 sufficiency
- 需要 K 使得 `1 - exp(-0.45/K) ≈ 0.6`，解得 K ≈ 0.49
- 搜索范围: **K ∈ [0.25, 0.80]**，步长 0.05

**_BETA / _BETA_POS (certainty 放大)**:

rho 的计算: `rho = (w_p - w_n×LA) / (w_p + w_n×LA + n_u×W0)`

当所有 impact_value 等比例缩放时，rho 值不变（分子分母同比变化）。因此 **rho 分布与 confidence→impact 切换无关**。

结论: `_BETA` 和 `_BETA_POS` 理论上不需要调整。但因为 evidence 变了，certainty × sufficiency 的乘积效应可能需要微调。

搜索范围: `_BETA ∈ [1.8, 2.8]`，`_BETA_POS ∈ [0.9, 1.5]`

**_GAMMA / _OPP_NEG (反对惩罚)**:

反对惩罚的公式: `opp_penalty = GAMMA × w_n / (w_p + w_n)`

`w_n / (w_p + w_n)` 是比值，不受绝对值域影响。因此 **理论上 _GAMMA 和 _OPP_NEG 不需要调整**。

保守搜索范围: `_GAMMA ∈ [0.30, 0.50]`，`_OPP_NEG ∈ [0.15, 0.30]`

#### 3.3 敏感性分析方案

**方法**: 对每个需调参数，固定其余参数为理论推导的中心值，单独扫描该参数，绘制 impact_score 随参数变化的曲线。

**评估指标**:
1. **跨样本量一致性**: 相同 P:N:U 比例在 3 条 vs 10 条 vs 20 条时，confidence 差异应 < 0.08
2. **单调性**: P 比例增加时 sentiment_score 严格递增
3. **不对称性**: 相同正负比例下 negative 的 |score| > positive 的 |score|
4. **饱和行为**: 15P+5U 场景的 confidence 受指数饱和曲线自然控制
5. **冲突区分**: 冲突型 neutral (3P+3N) 的 confidence 远低于共识型 neutral (8U)

**执行步骤**:
1. 用 impact 值重新构建 30 个场景（替换 confidence → impact 等级）
2. 逐参数扫描，记录上述 5 个指标
3. 选择所有指标同时满足约束的参数交集

---

### Phase 4: 实验验证

**目标**: 验证 impact 版本的输出质量不低于 confidence 版本。

#### 4.1 场景设计（复用 + 适配）

**复用已有 30 场景的结构**，但替换数值：

原场景中每条新闻的 `{"s": "positive", "c": 0.7}` 格式需要替换为 `{"s": "positive", "impact": "medium", "iv": 0.5}`。

**替换规则** (基于 confidence → impact 的语义映射):
```
c=0.5 → impact="low" (iv=0.2)      # 低确信 ≈ 低影响
c=0.6 → impact="low" (iv=0.2)      #
c=0.7 → impact="medium" (iv=0.5)   # 中等确信 ≈ 中等影响
c=0.8 → impact="high" (iv=0.8)     # 高确信 ≈ 高影响
```

注意: 这个映射不是精确对应，而是合理的初始估计。impact 场景的关键差异是**值域更宽、分布更离散**。

**新增 impact 特有场景** (10 个):
- 1 条 extreme + 4 条 negligible → 应输出有方向性信号（extreme 新闻主导）
- 3 条 high + 3 条 low (同方向) → high 应主导
- 2 条 extreme (对立) → 高冲突但高不确定
- 全部 negligible (10 条) → 接近无方向信号
- 混合 extreme/negligible 场景 → 测试极端值域下公式行为

这些场景是 impact 特有的，因为 confidence 版本中 0.05 和 1.0 这样的极端差异不存在。

#### 4.2 敏感性分析实验

**复用基础设施**: `optimize_params.py` 的参数化 `compute_formula` 函数

**修改点**:
1. `compute_formula` 输入从 `{"s": ..., "c": ...}` 改为 `{"s": ..., "iv": ...}`（或兼容两种格式）
2. 搜索空间缩小到 Phase 3.2 确定的范围
3. 评估函数**不使用 human baseline**（Task #2 结论：不需要标注数据），改为使用 5 个理论约束指标

**新评估函数**:
```python
def evaluate_impact(params, scenarios):
    """理论约束驱动的评估"""
    violations = 0

    # 约束 1: 跨样本量一致性
    # 相同 P:N 比例的 cold(3条) vs hot(15条) 场景，confidence 差异 < 0.08

    # 约束 2: 单调性
    # P 比例递增序列的 score 应严格递增

    # 约束 3: 不对称性
    # mirror 场景 (xP+yN vs yP+xN) 中 negative |score| > positive |score|

    # 约束 4: 天花板
    # 所有 confidence <= CAP

    # 约束 5: 冲突 vs 共识
    # conflict neutral conf < consensus neutral conf

    # 综合得分: violations 越少越好，辅以 confidence 分布的方差合理性
    return score
```

#### 4.3 参数优化流水线

复用两阶段搜索策略:

1. **粗搜索** (复用 `optimize_params.py` 框架):
   - 搜索空间: K × GAMMA × BETA × BETA_POS × OPP_NEG (5 维)
   - 步长: 各维度 5-7 个点
   - 目标: 找到约束全满足的参数区域

2. **精细搜索** (复用 `optimize_fine.py` 框架):
   - 在粗搜索最优点附近 ±20% 范围内细化
   - 步长减半
   - 选择最稳健点（非边界最优）

3. **消融验证** (复用 `ablation_study.py` 框架):
   - 对每个调整的参数逐一恢复原值
   - 验证每个参数的贡献独立且正向

#### 4.4 历史回测验证 (A/B 对比)

**目标**: 在真实新闻数据上对比 confidence-based 和 impact-based 的选股效果。

**方法**:
1. 选取 20-30 只有足够新闻覆盖的股票
2. 对同一时期的新闻，分别用 confidence prompt 和 impact prompt 调用 LLM
3. 计算两种方案的 sentiment_score
4. 对比指标:
   - score 分布形状（impact 版应有更宽的值域、更好的区分度）
   - 与后续 N 日涨跌幅的相关性（Spearman 秩相关）
   - 极端 score 的预测准确率
5. 如果 impact 版的秩相关系数 >= confidence 版，则验证通过

**注意**: 回测需要实际调用 LLM，有 API 成本。建议先在 5 只股票上做 pilot，确认趋势后再扩展。

---

### Phase 5: 缓存迁移 + 上线收尾

#### 5.1 缓存处理

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/BreakoutStrategy/news_sentiment/cache.py`

**问题**: `sentiments` 表当前 schema 为 `(fingerprint, backend, model, sentiment, confidence, reasoning)`，没有 impact 字段。

**方案**: 版本化缓存，而非迁移

1. 在 `sentiments` 表新增 `impact TEXT DEFAULT ''` 和 `impact_value REAL DEFAULT 0.0` 列
2. 新增 `schema_version INTEGER DEFAULT 1` 列
3. `get_sentiment` 查询时检查 `schema_version`:
   - `version=1` (旧记录): 只有 confidence，`impact=""`, `impact_value=0.0`
   - `version=2` (新记录): 有 impact 和 impact_value
4. `put_sentiment` 写入时设 `schema_version=2`

**降级策略**: 旧缓存记录在读取时 `impact_value=0.0`，会被聚合层视为失败分析 (fail_count++)。这意味着旧缓存**自动失效**而非产生错误结果。

**或更简单的方案**: 直接清空 sentiments 表。因为 prompt 变了，旧的 sentiment 结果语义已不同，不应复用。

```python
# 在上线切换时执行一次
cache.clear()  # 或仅清空 sentiments: DELETE FROM sentiments
```

推荐**清空方案**，因为更简单、更安全。

#### 5.2 配置更新

**文件**: `/home/yu/PycharmProjects/Trade_Strategy/configs/news_sentiment.yaml`

无需改动。impact 的参数（映射表、等级定义）硬编码在 `models.py` 中，不需要配置化。

#### 5.3: 更新文档

- `analyzer.py` 顶部注释和 `_summarize` docstring 中的 "confidence" 语义说明更新为 "impact"
- `docs/research/sentiment_score_design.md` 如果涉及 confidence 权重描述需更新

---

## 三、可复用的基础设施清单

| 已有组件 | 文件路径 | 复用方式 | 需要的修改 |
|---------|---------|---------|----------|
| 30 场景定义 | `calibration_v2.py` SCENARIOS | 复用结构，替换 `c` 值为 `iv` 值 | 值替换 + 新增 10 个 impact 特有场景 |
| 参数化公式计算 | `optimize_params.py` compute_formula | 直接复用，只改输入字段名 | `it["c"]` → `it["iv"]` |
| 网格搜索框架 | `optimize_params.py` main loop | 直接复用搜索循环 | 缩小搜索空间，替换评估函数 |
| 精细搜索 | `optimize_fine.py` | 直接复用 | 同上 |
| 消融实验框架 | `ablation_study.py` | 直接复用 | 仅替换基准参数和场景 |
| 评估函数结构 | `optimize_params.py` evaluate() | 框架复用，内部逻辑重写 | MAD+人类基准 → 理论约束评估 |
| 时间衰减测试 | `time_decay_scenarios.py` | Phase 4 中可选复用 | 无 |
| evidence 归一化测试 | `evidence_normalization_test.py` | 验证 impact 下归一化是否仍正确 | 场景数据替换 |

**不复用的组件**:
- `human_baseline_v3.json` — impact 不使用标注数据（Task #2 结论）
- `AI标注_prompt.txt` — 不需要 AI 标注流程

---

## 四、参数校准策略（逐参数）

### 可直接保持的参数 (2 个)

| 参数 | 值 | 理由 |
|------|---|------|
| `_DELTA` (死区) | 0.1 | rho 是归一化比率，不受权重绝对值影响 |
| `_CAP` (饱和上界) | 1.0 | 移除硬上限，指数曲线自然控制 |

### 基本不变的参数 (5 个)

| 参数 | 值 | 理由 | 验证方法 |
|------|---|------|---------|
| `_W0_RHO` | 0.1 | n_u 是计数非加权 | 消融验证 |
| `_ALPHA` | 0.5 | fail_count 基于计数 | 消融验证 |
| `_LA` | 1.02 | 比率空间操作 | 消融验证 |
| `_K_NEU` | 2.47 | 基于 n_u 计数 | 消融验证 |
| `_SCARCITY_N` | 3 | 基于 n_dir 计数 | 消融验证 |
| `_CONFLICT_POW` | 3.0 | balance 是比率 | 消融验证 |
| `_CONFLICT_CAP` | 0.15 | 设计决策 | 消融验证 |

### 需要理论推导 + 敏感性分析的参数 (3 个)

**1. `_K` (evidence 饱和速度) — 最关键**

- **当前值**: 0.55（适配归一化 evidence，均值约 0.7）
- **第一性原理推导**:
  - impact evidence 均值约 0.33（基于金融新闻 impact 分布估计）
  - 希望 evidence=0.45 时 sufficiency ≈ 60% CAP
  - 解方程: `1 - exp(-0.45/K) = 0.6` → `K ≈ 0.49`
- **搜索范围**: [0.25, 0.80]，步长 0.05
- **敏感性检验**: 绘制 sufficiency vs evidence 曲线族（K=0.3/0.4/0.5/0.6/0.7），选择曲线形状最合理的 K

**2. `_GAMMA` (positive 反对惩罚)**

- **当前值**: 0.40
- **推导**: opp_penalty = GAMMA × w_n/(w_p+w_n)，比率操作，理论上不需要变
- **验证**: 在 impact 场景下检查：当 1 条 extreme negative 对抗 5 条 medium positive 时，惩罚是否过重/过轻
- **搜索范围**: [0.30, 0.50]，步长 0.05

**3. `_BETA` / `_BETA_POS` (certainty 放大)**

- **当前值**: BETA=2.2, BETA_POS=1.15
- **推导**: rho 不变 → certainty 不变 → 理论上不需要调整
- **验证**: 但因为 sufficiency 的绝对值可能变化（K 变了），certainty × sufficiency 的乘积可能需要微调 BETA 以维持最终 confidence 的合理范围
- **搜索范围**: BETA ∈ [1.8, 2.8]，BETA_POS ∈ [0.9, 1.5]

---

## 五、风险点和回退方案

### 风险 1: LLM impact 判断一致性差

**描述**: LLM 对 impact 等级的判断比 confidence 更不稳定（同一新闻多次调用返回不同等级）。

**检测**: Phase 1 完成后，对 20 条新闻各调用 3 次，计算 impact 等级的一致率。阈值: 一致率 >= 85%。

**回退**: 如果一致性 < 85%，在 prompt 中增加 few-shot 示例（3-5 条标准案例）提高稳定性。如果仍不足，考虑对模糊边界案例（如 medium vs high）取较保守等级。

### 风险 2: 参数校准无法满足全部理论约束

**描述**: 在搜索空间内找不到同时满足 5 个约束的参数组合。

**检测**: Phase 3 精细搜索后检查约束满足情况。

**回退**: 放宽跨样本量一致性约束（0.08 → 0.12），或接受 1-2 个约束的边界违反。如果核心约束（单调性、不对称性）都无法满足，说明公式结构本身需要调整（但这种可能性极低，因为公式结构是比率驱动的）。

### 风险 3: 回测中 impact 版选股效果不如 confidence 版

**描述**: A/B 回测中 impact 版的秩相关系数低于 confidence 版。

**检测**: Phase 4.4 回测结果。

**回退**:
1. 检查是否是参数校准问题（重新搜索更大范围）
2. 检查是否是 impact 分布问题（映射表 IMPACT_MAP 的数值需要调整）
3. 最坏情况：保留 confidence 方案，将 impact 作为辅助维度（`w = confidence × impact × tw`）

### 风险 4: 缓存清空导致的冷启动成本

**描述**: 清空 sentiments 缓存后，所有历史新闻需要重新 LLM 分析。

**缓解**:
1. 只在确认 impact 版本就绪后才清空缓存
2. 在低峰期批量重分析高频使用的 ticker
3. 缓存预热脚本：对 top 50 ticker 的最近 30 天新闻预先分析并缓存

### 风险 5: 向后兼容问题

**描述**: 其他模块引用 `SentimentResult.confidence` 的代码在切换后行为异常。

**检测**: 全局搜索 `sentiment.confidence` 和 `\.confidence` 的使用位置。

**缓解**: Step 1.1 中保留 `confidence` 字段且设为 `impact_value` 的别名，确保旧代码路径不中断。

---

## 六、验证标准

### Phase 1 验证 (Prompt + 模型)
- [ ] LLM 对 20 条测试新闻，100% 返回有效 impact 等级 (非空、在 5 档之内)
- [ ] 3 次重复调用的 impact 等级一致率 >= 85%
- [ ] `SentimentResult` 的 `impact_value` 正确映射

### Phase 2 验证 (公式适配)
- [ ] 旧代码路径（无 impact 字段的 SentimentResult）不报错
- [ ] 新代码路径正确使用 impact_value 计算 w_p/w_n
- [ ] `sentiment_score` 输出范围仍在 [-0.80, +0.80]

### Phase 3 验证 (参数校准)
- [ ] 5 个理论约束全部满足:
  - 跨样本量一致性: 同比例 cold vs hot 的 confidence 差 < 0.08
  - 单调性: P 比例增加时 score 严格递增
  - 不对称性: mirror 场景中 |neg score| > |pos score|
  - 饱和: confidence 受指数曲线自然控制（_CAP=1.0）
  - 冲突 < 共识: conflict neutral conf < consensus neutral conf
- [ ] 消融实验中所有保留参数的 contribution 为正

### Phase 4 验证 (回测)
- [ ] impact 版 sentiment_score 与 N 日涨跌幅的 Spearman 秩相关 >= confidence 版
- [ ] 极端 score (|score| > 0.40) 的方向预测准确率 >= 60%
- [ ] impact 版 score 分布的标准差 > confidence 版（说明区分度更好）

### 最终上线标准
- [ ] Phase 1-4 全部通过
- [ ] 缓存迁移/清空完成
- [ ] 文档更新完成

---

## 七、开发顺序建议和工作量估计

| 阶段 | 核心工作 | 涉及文件数 | 关键依赖 |
|------|---------|-----------|---------|
| Phase 1 | models.py + _llm_utils.py | 2 | 无 |
| Phase 2 | analyzer.py | 1 | Phase 1 |
| Phase 3 | 实验脚本 (新建/改造) | 3-4 | Phase 2 |
| Phase 4 | 实验脚本 + 回测脚本 | 2-3 | Phase 3 |
| Phase 5 | cache.py + 配置 | 2 | Phase 4 |

Phase 1-2 是纯代码改动，工作量小。Phase 3-4 是核心工作量所在（参数搜索和回测验证）。Phase 5 是收尾工作。

建议 Phase 1 + Phase 2 合并为一个 PR，Phase 3 + Phase 4 为第二个 PR，Phase 5 为第三个 PR。
