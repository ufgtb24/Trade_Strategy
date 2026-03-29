# 趋势感知聚合方案设计

## Executive Summary

基于 math-analyst 的数学分析，绝对指数衰减 **不能** 隐式捕获情感的相对时序信息。信息新鲜度（绝对）与情感轨迹（相对）是数学上正交的两个维度。本方案提出一个轻量级的 **Sentiment Momentum** 机制，以 rank-based 半窗口对比方式叠加在现有 rho 之上，新增 1 个参数，与现有框架完全兼容。

---

## 1. 问题诊断

### 1.1 现有 _summarize 的盲区

当前聚合公式：
```
tw_i = exp(-ln2/H * days_i)
w_p = sum(confidence_i * tw_i)   for positive
w_n = sum(confidence_i * tw_i)   for negative
rho = (w_p - w_n) / (w_p + w_n + neu_tw * 0.1)
```

math-analyst 识别出的三个具体盲区：

| 盲区 | 描述 | 影响 |
|------|------|------|
| **趋势盲视** | [neg,neg,neg,pos,pos,pos] 和 [pos,pos,pos,neg,neg,neg] 在相同时间位置下产生相同 rho | 无法区分"恶化"与"好转" |
| **远期模式消亡** | 距参考日 25-30 天的反转信号 confidence ~0.0007，本质信息被衰减杀死 | 长窗口下趋势不可见 |
| **爆发不敏感** | 14天持续负面 vs 单日5条负面得分几乎相同 | 持续恶化和孤立事件无法区分 |

### 1.2 绝对衰减的正当角色

绝对衰减回答的是 **"这条新闻现在还重要吗？"** ——它正确地将旧新闻打折。这个功能不应被替换。

趋势组件回答的是另一个问题：**"情感在朝哪个方向移动？"** ——它捕获的是极性变化的方向。

结论：**叠加（layer），不替换**。

---

## 2. 方案设计：Rank-Based Sentiment Momentum

### 2.1 设计哲学

- **Rank-based**: 按时间排序后使用序号位置，不依赖绝对时间距离 → 满足时间平移不变性
- **半窗口对比**: 将有效新闻（排除 fail 和 neutral）按时间分为前半和后半，比较两半的极性倾向 → 简单直观
- **乘法叠加**: momentum 作为 certainty 的调制因子，顺势放大、逆势压缩 → 与现有框架天然兼容
- **单参数**: 仅引入一个强度参数 `_MU`，控制 momentum 的影响幅度

### 2.2 算法

**Step 0: 构建有序极性序列**

从 analyzed_items 中提取所有有效（confidence > 0）的 positive 和 negative 条目，按 published_at 升序排列，每条映射为带符号极性值：

```
polarity_i = +confidence_i   if positive
           = -confidence_i   if negative
```

Neutral 不参与 momentum 计算（它们不携带方向信息）。

**Step 1: 半窗口分割**

将有序序列在中点分为 older half 和 newer half：

```
mid = len(polarities) // 2
older = polarities[:mid]
newer = polarities[mid:]
```

当 len 为奇数时，中间元素归入 newer half（近期偏好）。

**Step 2: 计算 Momentum**

```
avg_older = mean(older)   if older else 0
avg_newer = mean(newer)   if newer else 0
raw_momentum = avg_newer - avg_older
```

raw_momentum 的含义：
- `> 0`：情感从负面/弱正面 → 正面/强正面（好转趋势）
- `< 0`：情感从正面/弱负面 → 负面/强负面（恶化趋势）
- `≈ 0`：情感无明显趋势变化

由于 polarity_i 在 [-1, 1] 范围内，avg_older 和 avg_newer 也在 [-1, 1]，因此 raw_momentum 在 [-2, 2] 范围内。归一化到 [-1, 1]：

```
momentum = raw_momentum / 2.0
```

**Step 3: 叠加到 certainty**

Momentum 通过调制 certainty 来影响最终 confidence。核心思想：**如果 rho 的方向与 momentum 一致（趋势确认），增强 certainty；如果相反（趋势背离），削弱 certainty**。

```python
# 方向一致性：rho 和 momentum 同号为正，异号为负
alignment = sign(rho) * momentum    # 范围 [-1, 1]
# 调制因子
trend_factor = 1.0 + _MU * alignment   # 范围 [1-MU, 1+MU]
# 应用到 certainty
adjusted_certainty = certainty * trend_factor
```

其中 `_MU` 是唯一新增参数，建议值 `0.15`（即 momentum 最多调制 certainty ±15%）。

### 2.3 完整集成伪代码

```python
_MU = 0.15    # momentum 调制强度

def _compute_momentum(analyzed_items, item_tw_unused):
    """计算 rank-based sentiment momentum"""
    # 收集有效的 directional 条目，按时间排序
    directional = []
    for item in analyzed_items:
        s, c = item.sentiment.sentiment, item.sentiment.confidence
        if c == 0.0 or s == 'neutral':
            continue
        polarity = c if s == 'positive' else -c
        date_str = item.news.published_at[:10] if item.news.published_at else '9999-99-99'
        directional.append((date_str, polarity))

    if len(directional) < 2:
        return 0.0   # 不足 2 条方向性新闻，无趋势可言

    # 按日期升序排列
    directional.sort(key=lambda x: x[0])
    polarities = [p for _, p in directional]

    # 半窗口分割
    mid = len(polarities) // 2
    older = polarities[:mid]
    newer = polarities[mid:]

    avg_older = sum(older) / len(older)
    avg_newer = sum(newer) / len(newer)

    raw_momentum = avg_newer - avg_older
    return raw_momentum / 2.0    # 归一化到 [-1, 1]


# 在 _summarize 的 Step 3 中，计算 certainty 之后：
momentum = _compute_momentum(analyzed_items, item_tw)

if sentiment in ('positive', 'negative'):
    alignment = (1.0 if rho > 0 else -1.0) * momentum
    trend_factor = 1.0 + _MU * alignment
    # certainty 已经计算完毕，应用 trend_factor
    adjusted_certainty = certainty * max(0.0, trend_factor)
    # 用 adjusted_certainty 替换 certainty 重算 base_conf
    base_conf = adjusted_certainty * sufficiency * (1.0 - opp_penalty)
```

### 2.4 边界情况分析

| 情况 | 行为 | 正确性 |
|------|------|--------|
| **0-1 条方向性新闻** | momentum = 0.0, trend_factor = 1.0 | 退化为现有行为，无影响 |
| **所有新闻同一天** | 排序稳定，分两半。如果极性混合，momentum 捕获列表前后半的差异 | 合理但信号较弱（同日内排序依赖输入顺序） |
| **纯正面或纯负面** | older 和 newer 都是同方向，momentum ≈ 0（confidence 差异的微小波动） | 正确：单一方向无"趋势变化"可言 |
| **完美反转 neg→pos** | momentum > 0, rho > 0 → alignment > 0 → 增强 certainty | 正确：趋势确认了当前判断 |
| **完美反转 pos→neg** | momentum < 0, rho < 0 → alignment > 0 → 增强 certainty | 正确：恶化趋势确认了 negative 判断 |
| **反转与 rho 矛盾** | 如 neg→pos 但整体仍 rho < 0 → alignment < 0 → 削弱 certainty | 正确：趋势在好转，但尚未足够翻转整体判断，降低对 negative 的信心 |
| **neutral 判定** | momentum 不参与 neutral 分支的 confidence | 正确：neutral 表示无方向性，趋势调制无意义 |

### 2.5 同日新闻的排序问题

当前时间精度为日级（`published_at[:10]`），同一天内的多条新闻排序依赖输入顺序。这不是一个严重问题：

1. **半窗口对比对微观排序不敏感**：同日新闻即使重排，只要它们整体在同一半窗口内，momentum 不变
2. **跨越中点的同日新闻**：极端情况下可能因微观排序变化导致 momentum 轻微波动，但 `_MU = 0.15` 的限制使最终影响 < 2%
3. **如未来需要更高精度**：可使用完整的 `published_at` 时间戳排序，代码已预留空间

---

## 3. 为什么选择半窗口对比而非其他方案

### 3.1 备选方案评估

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **Kendall's tau** | 严格的秩相关，理论性质优美 | O(n^2) 计算复杂度；对 tied ranks（同日多条新闻）需要特殊处理；输出值解释不直观 | 过度工程化 |
| **线性回归斜率** | 连续值，信息量大 | 需要选择自变量（用序号还是实际天数？）；对异常值敏感；引入最小二乘计算 | 复杂度不匹配 |
| **EWMA 交叉** | 类比技术分析中的金叉/死叉 | 需要两个窗口参数（快/慢 EWMA）；对新闻到达不均匀敏感；引入 2+ 新参数 | 参数黑洞 |
| **半窗口均值差** | 一行可算；0 参数（仅 _MU 控制强度）；O(n)；对 tied ranks 天然鲁棒 | 不如 Kendall's tau 精细 | **最优权衡** |

### 3.2 核心论点

半窗口对比是最符合奥卡姆剃刀的选择：
1. **零额外排序/计算成本**：sort + 一次 split + 两次 mean
2. **单参数 `_MU`**：语义清晰——"允许趋势调制 certainty 的最大幅度"
3. **自然鲁棒**：均值操作对异常值/噪声的敏感度远低于斜率或秩相关
4. **与框架兼容**：乘法调制 certainty，不改变 rho 计算、不改变标签判定、不改变 sufficiency 逻辑

---

## 4. 参数选择与敏感性

### 4.1 `_MU = 0.15` 的推导

- certainty 在现有框架中的典型范围为 0.1 ~ 0.8
- momentum 在实际数据中（非极端情况）的典型范围为 -0.3 ~ 0.3
- 实际调制幅度 = `_MU * |momentum|` ≈ `0.15 * 0.3 = 0.045`，即 ~5% 的 certainty 调制
- 极端情况（完美反转，momentum = ±1）：调制 ±15%，仍在合理范围内
- 这意味着 momentum 是一个 **微调因子**，不会颠覆基于 rho 的主判断

### 4.2 敏感性矩阵

| momentum | _MU=0.10 | _MU=0.15 | _MU=0.20 |
|----------|----------|----------|----------|
| 0.0 (无趋势) | ×1.00 | ×1.00 | ×1.00 |
| +0.3 (温和好转) | ×1.03 | ×1.045 | ×1.06 |
| +0.7 (强烈好转) | ×1.07 | ×1.105 | ×1.14 |
| +1.0 (完美反转) | ×1.10 | ×1.15 | ×1.20 |

`_MU = 0.15` 在各场景下都保持了 "微调而非颠覆" 的特性。

---

## 5. 配置集成

### 5.1 TimeDecayConfig 扩展

建议在 `TimeDecayConfig` 中增加一个可选字段：

```python
@dataclass
class TimeDecayConfig:
    enable: bool
    half_life: float
    sample_alpha: float
    momentum_mu: float = 0.15    # 新增：趋势动量调制强度 (0=禁用)
```

`momentum_mu: 0` 等效于完全禁用 momentum（trend_factor 恒为 1.0），实现零开关成本的向后兼容。

### 5.2 YAML 配置

```yaml
time_decay:
  enable: true
  half_life: 3.0
  sample_alpha: 0.25
  momentum_mu: 0.15    # 趋势动量强度 (0=禁用)
```

---

## 6. 对 _summarize 信息流的最小侵入

修改仅涉及 `_summarize` 方法内部，影响范围：

```
Step 0: 不变 (分组 + 时间加权)
Step 1: 不变 (rho 计算)
Step 2: 不变 (标签判定)
Step 3: 修改 (certainty 乘以 trend_factor)  ← 唯一修改点
Step 4: 不变 (失败惩罚)
Step 5: 可选扩展 (reasoning 中报告 momentum 值)
```

不影响：rho 值、标签判定逻辑、sufficiency 计算、opp_penalty 计算、SummaryResult 数据结构。

---

## 7. 实施建议

### 7.1 实施步骤

1. 在 `analyzer.py` 顶部新增 `_MU = 0.15` 常量
2. 新增 `_compute_momentum(analyzed_items) -> float` 函数（约 15 行）
3. 在 Step 3 的 positive/negative 分支中，certainty 计算后、base_conf 计算前，插入 trend_factor 调制
4. 在 `TimeDecayConfig` 中新增 `momentum_mu` 字段（默认 0.15）
5. 可选：在 reasoning 模板中追加 momentum 方向描述

### 7.2 验证计划

用 benchmark_v3 的现有测试集运行 A/B 对比：
- A: 现有 _summarize（baseline）
- B: 加入 momentum 的 _summarize

关注指标：
- 趋势反转场景下的标签准确性是否提升
- 整体 confidence 分布是否保持稳定（momentum 不应大幅改变分布）
- 边界情况（单条新闻、全同日期）是否正确退化

---

## 8. 结论

**需要引入相对时序感知。** 理由充分：绝对衰减和相对趋势回答不同的问题，且 math-analyst 给出了具体的盲区场景证明二者的正交性。

推荐方案：**Rank-Based Half-Window Sentiment Momentum**，以乘法因子调制 certainty，新增 1 个参数 `_MU = 0.15`。方案满足所有约束：
- 确定性公式（无 LLM 依赖）
- 与 rho/certainty/sufficiency 框架兼容（仅修改 certainty 一个变量）
- 复杂度可控（1 个参数，O(n log n) 计算）
- 对分布不均匀鲁棒（rank-based，不依赖绝对时间间隔）
- 边界情况正确退化（< 2 条方向性新闻时 momentum = 0）
