# 联合信号判断系统 (Composite Signal Judgment)

> 状态：设计中 (Planning) | 创建日期：2026-02-03

## 一、概述

### 1.1 背景

当前绝对信号系统（B/V/Y/D）仅按信号数量排序，存在以下局限：
- 丢失信号间的时序关系（D→B 的确认模式未被捕捉）
- 忽略信号组合的协同效应（放量突破比无量突破更可靠）
- 近期信号与远期信号被同等对待
- 无法区分信号聚集 vs 分散

### 1.2 目标

设计联合信号判断机制，在 `lookback_days` 窗口内：
1. 捕捉信号的时序关系（顺序依赖）
2. 识别高价值组合模式（协同效应）
3. 量化信号的时效性（时间衰减）
4. 输出可行动的买入判断（分级推荐）

### 1.3 设计原则

- **简洁可解释**：每个评分维度对应明确的市场机制
- **加法模型**：各维度独立可追溯，避免黑箱
- **渐进复杂度**：先实现核心功能，再按需扩展
- **参数可控**：核心参数 ≤ 15 个，避免过拟合

---

## 二、信号语义分析

### 2.1 四种信号的市场本质

| 信号 | 代码 | 市场本质 | 捕捉维度 |
|------|------|---------|---------|
| Breakout | B | 价格突破前期阻力位，供需关系逆转 | 价格结构 |
| High Volume | V | 异常放量，大资金入场痕迹 | 资金流动 |
| Big Yang | Y | 单日涨幅超 Nσ，买方情绪爆发 | 市场情绪 |
| Double Trough | D | 126日最低 + 反弹 + 次底确认，底部形成 | 底部形态 |

### 2.2 信号组合的语义关系

**核心洞察**：某些信号组合具有确认关系，后续信号验证前序信号的有效性。

#### 确认关系矩阵

| 前序 → 后续 | 语义含义 | 可靠性 |
|------------|---------|--------|
| **D → B** | 双底形成后突破，底部确认完成 | ★★★★★ |
| **D → V** | 双底后放量，资金开始介入 | ★★★★☆ |
| **D → Y** | 双底后大阳，情绪面确认 | ★★★★☆ |
| **B + V** | 放量突破，量价配合（同步） | ★★★★☆ |
| **B → Y** | 突破后大阳，趋势加速 | ★★★☆☆ |
| **V → B** | 放量后突破，资金先行 | ★★★☆☆ |

#### 高价值组合模式

```
模式 1: D → B + V (放量突破确认双底) - 教科书级信号
模式 2: D + V (底部放量) → B - 底部有机构吸筹
模式 3: B + V (放量突破) - 经典技术确认
模式 4: D + B + Y + V (四重共振) - 极强信号
```

### 2.3 假信号识别

| 风险类型 | 场景 | 识别方法 |
|---------|------|---------|
| 假双底 | 持续下跌中的"双底" | D 后无 B 确认，观察 first_bounce_height |
| 假突破 | 无量突破后回落 | B 无 V 配合，需回测确认 |
| 出货型放量 | 高位放量下跌 | V 需结合价格方向判断 |
| Y 噪音 | 高波动股频繁触发 | Y 单独出现时低权重 |

---

## 三、时序建模方案

### 3.1 方法选择

**推荐方案**：事件序列 + 时间衰减 + 确认链

| 方案 | 优点 | 缺点 | 适用性 |
|------|------|------|-------|
| 状态机 | 逻辑清晰 | 状态爆炸，难扩展 | ❌ 不推荐 |
| 滑动窗口计数 | 简单 | 丢失顺序信息 | ⚠️ 当前方案 |
| **事件序列+确认链** | 灵活可扩展，保留语义 | 需预定义关系 | ✅ 推荐 |
| ML (LSTM) | 自动学习 | 黑箱，需大量数据 | ❌ 过度工程 |

### 3.2 时间衰减函数

**指数衰减模型**：

```
W(t) = exp(-λ × t)

参数：
- t = scan_date - signal_date（信号年龄，交易日）
- λ = 0.07（推荐值，半衰期约 10 天）
```

**衰减效果**：

| 信号年龄 | 权重 |
|---------|------|
| 0 天（当天） | 1.00 |
| 7 天 | 0.61 |
| 14 天 | 0.37 |
| 21 天 | 0.23 |
| 42 天 | 0.05 |

### 3.3 确认链 (Confirmation Chain)

**核心概念**：检测信号序列中的确认模式，计算确认强度。

```python
# 确认关系定义
CONFIRMATION_PAIRS = {
    ("D", "B"): 2.0,   # D → B 最强确认
    ("D", "V"): 1.5,   # D → V 强确认
    ("D", "Y"): 1.3,   # D → Y 中确认
    ("B", "V"): 1.5,   # B + V 量价配合
    ("B", "Y"): 1.3,   # B → Y 趋势延续
    ("V", "B"): 1.4,   # V → B 资金先行
}

# 确认强度衰减（时间间隔影响）
max_confirmation_gap = 15  # 最大确认间隔（交易日）
```

**确认强度计算**：

```
confirmation_strength = base_strength × (1 - gap_days / max_gap × 0.5)

示例：D → B 间隔 3 天
strength = 2.0 × (1 - 3/15 × 0.5) = 2.0 × 0.9 = 1.8
```

---

## 四、评分系统设计

### 4.1 总体架构

```
Composite Score = Base Score + Synergy Bonus

Base Score = w₁×Count + w₂×Diversity + w₃×Cluster + w₄×Recency

Synergy Bonus = Σ(pattern_bonus)
```

### 4.2 基础评分维度

#### 4.2.1 信号数量得分 (Count Score)

```
Count Score = min(signal_count / max_count, 1.0) × 100

参数: max_count = 4
```

#### 4.2.2 信号多样性得分 (Diversity Score)

```
Diversity Score = (unique_types / 4) × 100

其中 unique_types = 不重复的信号类型数
```

#### 4.2.3 信号聚集度得分 (Cluster Score)

```
Cluster Score = (1 - avg_gap / max_gap) × 100

其中:
- avg_gap = 相邻信号平均间隔天数
- max_gap = lookback_days / 2
```

#### 4.2.4 信号时效性得分 (Recency Score)

```
Recency Score = mean(exp(-λ × age(s)) for s in signals) × 100

参数: λ = 0.07
```

### 4.3 组合模式加分 (Synergy Bonus)

| 模式 | 检测条件 | 加分 |
|------|---------|------|
| **D → B 确认** | D 先于 B，间隔 ≤ 21 天 | +15 |
| **B + V 放量突破** | B 和 V 间隔 ≤ 3 天 | +10 |
| **多信号共振** | 7 天内出现 ≥ 3 种信号 | +20 |
| **Y → B 动量延续** | Y 先于 B，间隔 ≤ 5 天 | +8 |

### 4.4 权重配置

```yaml
# 初期等权配置
weights:
  count: 0.25
  diversity: 0.25
  cluster: 0.25
  recency: 0.25
```

### 4.5 分级判断

| 等级 | 分数范围 | 行动建议 |
|------|---------|---------|
| **A (Strong Buy)** | ≥ 75 | 优先关注，多重确认 |
| **B (Buy)** | 60-74 | 可买入，信号充足 |
| **C (Watch)** | 45-59 | 观望，加入观察池 |
| **D (Ignore)** | < 45 | 忽略，信号稀疏或过期 |

---

## 五、数据模型

### 5.1 确认事件

```python
@dataclass
class ConfirmationEvent:
    """确认事件"""
    prior_signal: AbsoluteSignal      # 前序信号
    confirm_signal: AbsoluteSignal    # 确认信号
    pattern: str                       # 模式名称 (e.g., "D→B")
    strength: float                    # 确认强度
    gap_days: int                      # 间隔天数
```

### 5.2 联合评分结果

```python
@dataclass
class CompositeScore:
    """联合评分结果"""
    total: float                       # 总分
    base_score: float                  # 基础分
    synergy_bonus: float               # 模式加分

    # 各维度得分 (0-100)
    count_score: float
    diversity_score: float
    cluster_score: float
    recency_score: float

    # 检测到的模式和确认链
    detected_patterns: List[str]
    confirmations: List[ConfirmationEvent]

    # 置信度与风险
    confidence: str                    # "high" / "medium" / "low"
    risks: List[str]                   # 风险提示
```

### 5.3 扩展 SignalStats

```python
@dataclass
class SignalStats:
    # ... 现有字段 ...

    # 新增字段
    composite_score: Optional[CompositeScore] = None
    grade: Optional[str] = None        # A/B/C/D
```

---

## 六、配置规范

### 6.1 配置文件

`configs/signals/composite_scoring.yaml`

```yaml
# 联合信号评分配置

# === 基础维度权重 ===
weights:
  count: 0.25
  diversity: 0.25
  cluster: 0.25
  recency: 0.25

# === 时间衰减 ===
time_decay:
  lambda: 0.07                    # 衰减系数（半衰期约 10 天）

# === 组合模式配置 ===
patterns:
  d_b_confirmation:
    enabled: true
    bonus: 15
    max_gap_days: 21

  b_v_volume_breakout:
    enabled: true
    bonus: 10
    max_gap_days: 3

  multi_resonance:
    enabled: true
    bonus: 20
    window_days: 7
    min_types: 3

  y_b_momentum:
    enabled: true
    bonus: 8
    max_gap_days: 5

# === 确认链配置 ===
confirmation:
  max_gap_days: 15                # 最大确认间隔
  pairs:
    D_B: 2.0
    D_V: 1.5
    D_Y: 1.3
    B_V: 1.5
    B_Y: 1.3
    V_B: 1.4

# === 分级阈值 ===
thresholds:
  strong_buy: 75                  # A 级
  buy: 60                         # B 级
  watch: 45                       # C 级

# === 信号类型权重（可选，初期禁用）===
signal_type_weights:
  enabled: false
  B: 1.2
  V: 1.0
  Y: 0.8
  D: 1.1
```

### 6.2 参数汇总

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `weights.*` | 0.25 | 四个维度等权 |
| `time_decay.lambda` | 0.07 | 衰减系数 |
| `patterns.*.bonus` | 8-20 | 模式加分 |
| `patterns.*.max_gap_days` | 3-21 | 模式间隔阈值 |
| `thresholds.*` | 45/60/75 | 分级阈值 |

**总参数数**：约 14 个核心参数

---

## 七、模块结构

```
BreakoutStrategy/signals/
├── composite/                        # 新增：联合评分模块
│   ├── __init__.py                   # 模块导出
│   ├── config.py                     # CompositeConfig 配置类
│   ├── scorer.py                     # CompositeScorer 核心评分
│   ├── patterns.py                   # PatternDetector 模式检测
│   ├── confirmation.py               # ConfirmationChainAnalyzer
│   ├── time_decay.py                 # TimeDecayCalculator
│   └── grader.py                     # Grader 分级判断
├── aggregator.py                     # 修改：集成 CompositeScorer
├── scanner.py                        # 修改：传递评分到输出
└── models.py                         # 修改：扩展 SignalStats
```

---

## 八、集成方案

### 8.1 与 Aggregator 集成

```python
# aggregator.py
class SignalAggregator:
    def __init__(self, lookback_days: int, composite_config: dict = None):
        self.lookback_days = lookback_days
        if composite_config:
            self.scorer = CompositeScorer(composite_config)
        else:
            self.scorer = None

    def aggregate(self, all_signals, scan_date) -> List[SignalStats]:
        # ... 现有逻辑 ...

        # 新增：计算联合评分
        if self.scorer:
            for stats in stats_list:
                stats.composite_score = self.scorer.score(
                    stats.signals, scan_date
                )
                stats.grade = self.scorer.grade(stats.composite_score.total)

        # 排序：先按 count，再按 composite_score
        stats_list.sort(
            key=lambda s: (
                s.signal_count,
                s.composite_score.total if s.composite_score else 0
            ),
            reverse=True
        )

        return stats_list
```

### 8.2 与 UI 集成

**股票列表显示增强**：

```
Symbol | Count | Grade | Score | Types  | Patterns      | Latest
-------|-------|-------|-------|--------|---------------|--------
AAPL   | 4     | A     | 82.5  | B,V,Y,D| D→B, B+V     | 2026-02-01
MSFT   | 4     | B     | 68.3  | B,B,V,Y| B+V          | 2026-01-28
GOOGL  | 3     | B     | 61.2  | D,V,Y  | -            | 2026-01-30
```

### 8.3 与 Simple Pool 协同

```
Layer 1 (信号扫描) → Composite Score → Grade
  "这只股票是否值得关注？"

Layer 2 (Simple Pool) → Stability + Rising
  "现在是否是买入时机？"

入池条件：Grade >= C (score >= 45)
```

---

## 九、实现路线图

### Phase 1: 核心评分 (MVP)

- [ ] 实现 `CompositeScorer` 基础评分（Count, Diversity, Cluster, Recency）
- [ ] 实现时间衰减函数
- [ ] 实现分级判断
- [ ] 集成到 `SignalAggregator`
- [ ] UI 显示评分和等级

### Phase 2: 模式检测

- [ ] 实现 `PatternDetector`（D→B, B+V, 多信号共振, Y→B）
- [ ] 实现 `ConfirmationChainAnalyzer`
- [ ] 加分逻辑集成
- [ ] UI 显示检测到的模式

### Phase 3: 优化与验证

- [ ] 配置文件支持
- [ ] 回测验证评分有效性
- [ ] 权重参数调优
- [ ] 风险标记实现

---

## 十、附录

### A. 评分计算示例

**场景**：某股票在 42 天窗口内有以下信号

| 日期 | 信号 | 距 scan_date 天数 |
|------|------|------------------|
| D-30 | D | 30 |
| D-20 | V | 20 |
| D-8  | B | 8 |
| D-5  | Y | 5 |

**计算过程**：

```
1. Count Score = min(4/4, 1.0) × 100 = 100

2. Diversity Score = 4/4 × 100 = 100

3. Cluster Score:
   gaps = [10, 12, 3], avg = 8.3
   max_gap = 42/2 = 21
   score = (1 - 8.3/21) × 100 = 60.5

4. Recency Score:
   weights = [exp(-0.07×30), exp(-0.07×20), exp(-0.07×8), exp(-0.07×5)]
          = [0.12, 0.25, 0.57, 0.70]
   score = mean([0.12, 0.25, 0.57, 0.70]) × 100 = 41.0

5. Base Score = 0.25×100 + 0.25×100 + 0.25×60.5 + 0.25×41.0
              = 25 + 25 + 15.1 + 10.3 = 75.4

6. Synergy Bonus:
   - D→B: D(D-30) → B(D-8), gap=22 > 21, 不满足
   - Y→B: Y(D-5) 晚于 B(D-8), 不满足
   - B+V: |B - V| = 12 > 3, 不满足
   - 多信号共振: 检查 7 天窗口...
     - D-8 ~ D-2: B, Y (2种 < 3)
     不满足

   synergy_bonus = 0

7. Total = 75.4 + 0 = 75.4 → Grade A
```

### B. 确认链检测伪代码

```python
def detect_confirmations(signals: List[AbsoluteSignal]) -> List[ConfirmationEvent]:
    """检测信号序列中的确认模式"""
    sorted_signals = sorted(signals, key=lambda s: s.date)
    confirmations = []

    for i, confirm in enumerate(sorted_signals):
        for j in range(i - 1, -1, -1):
            prior = sorted_signals[j]
            key = (prior.signal_type.value, confirm.signal_type.value)

            if key not in CONFIRMATION_PAIRS:
                continue

            gap = (confirm.date - prior.date).days
            if gap > MAX_CONFIRMATION_GAP:
                continue

            base_strength = CONFIRMATION_PAIRS[key]
            strength = base_strength * (1 - gap / MAX_CONFIRMATION_GAP * 0.5)

            confirmations.append(ConfirmationEvent(
                prior_signal=prior,
                confirm_signal=confirm,
                pattern=f"{prior.signal_type.value}→{confirm.signal_type.value}",
                strength=strength,
                gap_days=gap
            ))
            break  # 每个确认信号只匹配最近的前序信号

    return confirmations
```

---

**文档版本**：v1.0
**作者**：Claude (多代理协作)
**审核状态**：待审核