# 观察池评估器架构分析：状态评估 vs 过程评估

> 研究日期：2026-01-04
> 研究方法：多代理头脑风暴 + 第一性原理分析

---

## 一、研究背景

### 1.1 问题起源

在观察池系统中，当前的 `CompositeBuyEvaluator` 使用统一的评估逻辑处理 Realtime 池和 Daily 池。然而，观察发现：

- **Realtime 池**：当价格相对于 ref price 下跌时，会扣分（合理）
- **Daily 池**：如果价格下跌后能稳定下来，反而是好的买入信号

这揭示了一个本质性问题：**两种池的评估逻辑应该根本不同**。

### 1.2 核心洞察

> "Daily 池在意的是**过程**（稳定到一个价位的过程），Realtime 池在意的是**状态**（当前的状态）"

---

## 二、本质差异分析

### 2.1 状态 vs 过程的哲学差异

| 维度 | 状态评估 (Realtime) | 过程评估 (Daily) |
|------|---------------------|------------------|
| **核心问题** | "现在怎么样？" | "经历了什么？" |
| **关注点** | 瞬时快照 | 时间演化 |
| **时间性** | 无状态，单点 | 有状态，多点 |
| **隐喻** | 体检报告（当前指标） | 病历记录（康复过程） |

### 2.2 输入数据的差异

**状态评估的输入**：
```python
Input = {
    entry: PoolEntry,           # 跟踪记录
    current_bar: pd.Series,     # 当前快照 (OHLCV)
    time_provider,              # 当前时间
    context: {}                 # 辅助数据
}
```

**过程评估的输入**：
```python
Input = {
    entry: PoolEntry,                   # 跟踪记录
    historical_bars: pd.DataFrame,      # 历史序列 (N天的OHLCV)
    price_trajectory: List[float],      # 价格轨迹
    volatility_series: List[float],     # 波动率序列
    support_tests: List[SupportTest],   # 支撑测试记录
    time_provider,
    context: {}
}
```

### 2.3 计算模式的差异

**状态评估（点评估）**：
```python
# 当前价格 vs 参考价格的静态比较
margin = (current_price - reference_price) / reference_price
if margin in ideal_zone:
    score = HIGH
elif margin < threshold:
    action = REMOVE
```

**过程评估（序列评估）**：
```python
# 需要分析时间序列的特征
volatility_trend = analyze_volatility_convergence(historical_bars)
support_formed = detect_support_level(price_trajectory)
pullback_quality = assess_pullback_pattern(historical_bars)
consolidation_days = count_consolidation_period(historical_bars)

score = weighted_sum(volatility_trend, support_formed,
                     pullback_quality, consolidation_days)
```

---

## 三、Realtime 池业务本质

### 3.1 核心定位

**Realtime 池是一个"状态快照评估器"**，它回答的是：**"此刻，这只股票是否值得买入？"**

### 3.2 业务场景

```
[突破发生] → [进入 Realtime 池] → [1天观察期] → [买入/转移/移除]
```

观察期内的评估是**反复检查状态**，每次检查都是独立的、无记忆的判断：

```
09:30 ────── 10:00 ────── 11:30 ────── 15:00 ────── 16:00
  │            │            │            │            │
  │         检查状态      检查状态      检查状态      │
  │         "是否买入？"  "是否买入？"  "是否买入？"  │
  │                                                   │
突破发生                                           转入日K池
```

### 3.3 状态向量定义

```
State = {
    price_position:     当前价格相对于突破价的位置（ATR 倍数）
    time_window:        当前时间在交易日的位置
    volume_condition:   成交量是否支持
    risk_flags:         风险门槛是否触发
}
```

**关键点**：这个状态向量不包含任何历史序列信息。

### 3.4 成功与失败模式

**成功模式：健康突破**
```
价格走势：
     ▲
     │    ╭──────╮ 理想买入区
     │   ╱       ╲
     │  ╱    ★买入  ╲
     ├─┴────────────────  ← 突破价
     │
     │   突破日   次日
     └────────────────▶ 时间
```

**失败模式：假突破**
```
价格走势：
     ▲
     │    ╭─╮
     │   ╱   ╲
     ├─┴──────╲──────  ← 突破价
     │          ╲
     │           ╲  ← 跌破移出阈值
     └────────────▶ 时间
```

---

## 四、Daily 池业务本质

### 4.1 核心定位

**Daily 池关注的是"突破后的筹码交换与价格发现过程"**。这个过程包含：回调阶段 → 企稳阶段 → 再启动阶段。

### 4.2 "过程"的三阶段模型

```
┌─────────────────────────────────────────────────────────────────┐
│                     突破后的价格稳定化过程                        │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   阶段1: 回调    │   阶段2: 企稳    │       阶段3: 再启动         │
│   (Pullback)    │  (Consolidation) │      (Re-ignition)         │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ 价格：下跌       │ 价格：横盘/震荡  │ 价格：向上突破               │
│ 成交量：萎缩中   │ 成交量：极度萎缩 │ 成交量：放量                 │
│ 波动：较大       │ 波动：收窄       │ 波动：放大                   │
│ 心理：恐惧       │ 心理：平静       │ 心理：贪婪                   │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ 持续：1-5天      │ 持续：2-10天     │ 持续：1-3天                  │
└─────────────────┴─────────────────┴─────────────────────────────┘
                                      ↑
                                   最佳买入点
```

### 4.3 阶段特征量化

#### 阶段1: 回调 (Pullback)

**识别规则**：
```python
is_pullback = (
    current_price < peak_after_breakout * 0.97  # 从高点回落>3%
    AND current_price > breakout_price * 0.90   # 但未跌破突破价10%
    AND volume < volume_ma20 * 1.2              # 成交量萎缩
    AND days_since_breakout <= 5                # 在5天内
)
```

#### 阶段2: 企稳 (Consolidation)

**识别规则**：
```python
is_consolidation = (
    max(close[-N:]) - min(close[-N:]) < close.mean() * 0.03  # 振幅<3%
    AND volume_ma5 < volume_ma20 * 0.8                       # 成交量萎缩
    AND atr_5 < atr_14 * 0.8                                 # 波动率收敛
    AND N >= 3                                                # 持续至少3天
)
```

#### 阶段3: 再启动 (Re-ignition)

**识别规则**：
```python
is_reignition = (
    close > max(close[-N:-1])                     # 突破前N-1日高点
    AND volume > volume_ma20 * 1.5                # 放量
    AND close > open                              # 阳线
    AND (close - open) / open > 0.01              # 涨幅>1%
    AND was_in_consolidation                       # 前期处于企稳状态
)
```

### 4.4 理想买入点优势分析

以具体案例对比 Day 0 买入 vs Day 6 买入：

| 指标 | Day 0 买入 | Day 6 买入 | Day 6 优势 |
|------|-----------|-----------|-----------|
| 买入价 | $101.20 | $101.50 | 仅高 0.3% |
| 止损位 | $95.00 (突破价下方) | $96.50 (企稳低点) | 更高、更明确 |
| 止损幅度 | 6.1% | 4.9% | 风险降低 1.2% |
| **风险收益比** | 1:1.4 | 1:1.7 | **提高 21%** |
| 确定性 | 突破可能失败 | 经过验证的突破 | 更高 |

---

## 五、当前统一评估器的问题

### 5.1 接口设计局限

```python
# 当前接口
def evaluate(entry, current_bar, ...):  # 只接收单个 bar

# Daily 池需要
def evaluate(entry, historical_bars, ...):  # 需要多日数据
```

### 5.2 具体设计缺陷

| 局限 | 说明 |
|------|------|
| **输入接口缺失历史数据** | 只有单个 bar，无法分析时间序列 |
| **价格确认只做点比较** | 只比较当前价和参考价，不分析价格是怎么到达的 |
| **缺失过程相关维度** | 无波动率收敛、支撑形成、回调质量、整理时间评估 |
| **PoolEntry 缺失过程追踪字段** | 缺少每日收盘价序列、波动率历史、支撑测试次数等 |

### 5.3 问题总结

当前 `CompositeBuyEvaluator` 是为**状态评估**设计的，强行用于 Daily 池的**过程评估**会导致：

1. **信息丢失**：只看收盘价，丢失过程信息
2. **误判风险**：无法区分"刚跌到位"和"企稳多日"
3. **代码扭曲**：如果硬塞历史数据到 context，会导致 API 污染

---

## 六、架构方案对比

### 6.1 方案A：统一评估器 + 池类型分支

```
CompositeBuyEvaluator
└── evaluate(entry, ..., pool_type)
    ├── if realtime: 执行状态评估逻辑
    └── if daily: 执行过程评估逻辑
```

| 评估 | 说明 |
|------|------|
| 优点 | 修改最小，对外接口不变 |
| 缺点 | 违反 SRP，产生 if-else 地狱 |
| 结论 | 短期可行，长期技术债务高 |

### 6.2 方案B：完全独立的评估器

```
RealtimeEvaluator (状态评估)
DailyEvaluator (过程评估)
```

| 评估 | 说明 |
|------|------|
| 优点 | 职责清晰，易于测试 |
| 缺点 | 代码重复，维护成本高 |
| 结论 | 职责清晰，但需要处理复用问题 |

### 6.3 方案C：策略模式 + 共享基础设施（推荐）

```
                    ┌──────────────────────────┐
                    │      IPoolEvaluator      │
                    │      <<interface>>       │
                    └────────────┬─────────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            │                                         │
            ▼                                         ▼
┌───────────────────────┐             ┌───────────────────────────┐
│ RealtimePoolEvaluator │             │    DailyPoolEvaluator     │
│   (状态评估策略)       │             │     (过程评估策略)         │
├───────────────────────┤             ├───────────────────────────┤
│ - PointPriceEvaluator │             │ - PullbackQualityEval     │
│ - CurrentVolumeEval   │             │ - VolatilityConvergenceEval│
│ - TimeWindowEval      │             │ - SupportFormationEval    │
│ - RiskFilterEval ─────┼─── 共享 ────┼─ RiskFilterEval           │
└───────────────────────┘             │ - ConsolidationPeriodEval │
                                      └───────────────────────────┘
```

| 评估 | 说明 |
|------|------|
| 优点 | 符合 OCP/DIP，代码复用高，易扩展 |
| 缺点 | 初期设计成本较高 |
| 结论 | **最佳平衡方案** |

### 6.4 设计原则检验

| 原则 | 方案A | 方案B | 方案C |
|------|-------|-------|-------|
| 单一职责 (SRP) | ❌ 违反 | ✅ 符合 | ✅ 符合 |
| 开闭原则 (OCP) | ❌ 新池需改代码 | ✅ 新增实现 | ✅ 新增实现 |
| 依赖倒置 (DIP) | ❌ 依赖具体类 | ⚠️ 中等 | ✅ 依赖接口 |
| 代码复用 | ❌ 低 | ❌ 低 | ✅ 高 |

---

## 七、Daily 池需要的新评估维度

### 7.1 波动率收敛 (Volatility Convergence)

```python
class VolatilityConvergenceEvaluator:
    """检测波动率是否在收窄（企稳信号）"""

    # 评分映射
    # 收敛比率 < 0.6: 显著收窄 → bonus 1.3
    # 收敛比率 0.6-0.8: 明显收窄 → bonus 1.15
    # 收敛比率 > 0.9: 未收窄 → bonus 0.8
```

### 7.2 支撑形成 (Support Formation)

```python
class SupportFormationEvaluator:
    """检测是否形成有效支撑"""

    # 评分映射
    # 触及次数 >= 3: 强支撑 → bonus 1.3
    # 触及次数 = 2: 中等支撑 → bonus 1.15
    # 触及次数 = 1: 弱支撑 → bonus 1.0
```

### 7.3 成交量模式 (Volume Pattern)

```python
class VolumePatternEvaluator:
    """识别"放量-缩量-再放量"模式"""

    # 理想模式：
    # 1. 突破日放量 (volume > 1.5x MA20)
    # 2. 回调期缩量 (volume < 0.8x MA20)
    # 3. 企稳期极缩量 (volume < 0.6x MA20)
    # 4. 再启动放量 (volume > 1.5x MA20)
```

### 7.4 整理时间 (Consolidation Period)

```python
class ConsolidationPeriodEvaluator:
    """评估整理时间是否足够"""

    # 评估指标：
    # 1. 从突破后最高点回落至今的天数
    # 2. 在当前区间停留的天数
    # 3. 相对于突破前整理时间的比例
```

### 7.5 价格结构 (Price Structure)

```python
class PriceStructureEvaluator:
    """检测 Higher Low 形成"""

    # 评分映射
    # Higher Low 确认: 趋势延续 → bonus 1.25
    # 持平: 盘整 → bonus 1.0
    # Lower Low: 趋势反转风险 → bonus 0.6
```

---

## 八、推荐架构详细设计

### 8.1 接口定义

```python
from typing import Protocol, Union
from enum import Enum

class DataType(Enum):
    CURRENT_BAR = "current_bar"
    HISTORICAL_SERIES = "historical_series"

class IPoolEvaluator(Protocol):
    """池评估器接口"""

    def evaluate(
        self,
        entry: PoolEntry,
        data: EvaluationData,
        time_provider: ITimeProvider,
        context: Optional[Dict] = None
    ) -> EvaluationResult:
        ...

    def get_required_data_type(self) -> DataType:
        """声明需要的数据类型，便于调用方准备数据"""
        ...
```

### 8.2 数据类型定义

```python
@dataclass
class CurrentBarData:
    """状态评估数据（Realtime 池）"""
    bar: pd.Series
    intraday_bars: Optional[pd.DataFrame] = None

@dataclass
class HistoricalSeriesData:
    """过程评估数据（Daily 池）"""
    bars: pd.DataFrame  # N 天日 K 线
    price_trajectory: List[float]
    volatility_series: List[float]
    support_tests: List[SupportTest]
    atr_at_breakout: float
    volume_ma20: float

EvaluationData = Union[CurrentBarData, HistoricalSeriesData]
```

### 8.3 PoolManager 整合

```python
class PoolManager:
    def __init__(
        self,
        realtime_evaluator: IPoolEvaluator,
        daily_evaluator: IPoolEvaluator,
        data_preparer: EvaluationDataPreparer,
        ...
    ):
        self.evaluators = {
            'realtime': realtime_evaluator,
            'daily': daily_evaluator
        }
        self.data_preparer = data_preparer

    def evaluate_entry(self, entry: PoolEntry, price_data: pd.DataFrame):
        pool_type = entry.pool_type
        evaluator = self.evaluators[pool_type]

        # 根据评估器需求准备数据
        data_type = evaluator.get_required_data_type()
        data = self.data_preparer.prepare(entry, price_data, data_type)

        return evaluator.evaluate(entry, data, self.time_provider)
```

---

## 九、实施路径

### Phase 1：接口定义（低风险）

1. 定义 `IPoolEvaluator` 接口
2. 定义 `EvaluationData` 联合类型
3. 定义 `EvaluationDataPreparer`

### Phase 2：重构现有代码为 Realtime 策略（中风险）

1. 将现有 `CompositeBuyEvaluator` 重命名为 `RealtimePoolEvaluator`
2. 实现 `IPoolEvaluator` 接口
3. 确保现有测试通过

### Phase 3：实现 Daily 策略（新功能）

1. 实现 `DailyPoolEvaluator`
2. 实现过程评估相关的子评估器：
   - `PullbackQualityEvaluator`
   - `VolatilityConvergenceEvaluator`
   - `SupportFormationEvaluator`
   - `ConsolidationPeriodEvaluator`
3. 扩展 `PoolEntry` 添加过程追踪字段

### Phase 4：整合到 PoolManager

1. 修改 `PoolManager` 注入两个评估器
2. 实现 `EvaluationDataPreparer`
3. 根据 `entry.pool_type` 选择评估器和数据

---

## 十、结论

### 10.1 核心发现

1. **Realtime 池关注"状态"**：评估"此刻是否买入"，使用点比较
2. **Daily 池关注"过程"**：评估"回调-企稳-再启动"阶段，使用模式识别
3. **当前评估器设计局限**：只支持状态评估，无法处理过程评估

### 10.2 设计建议

**推荐方案C：策略模式 + 共享基础设施**

- 两种池的评估器应该**独立设计**
- 通过接口抽象实现松耦合
- 共享组件（如 RiskFilterEvaluator）避免代码重复

### 10.3 关键价值

- Daily 池企稳后买入 vs 突破当日买入：**风险收益比提高 20%+**
- 独立设计使系统符合 SOLID 原则，便于扩展和维护

---

## 附录：关键代码位置

| 文件 | 职责 |
|------|------|
| `BreakoutStrategy/observation/pool_manager.py` | 池管理器 |
| `BreakoutStrategy/observation/pool_entry.py` | 条目数据结构 |
| `BreakoutStrategy/observation/evaluators/composite.py` | 组合评估器 |
| `BreakoutStrategy/observation/evaluators/components/price_confirm.py` | 价格确认评估 |
| `BreakoutStrategy/observation/evaluators/result.py` | 评估结果定义 |
