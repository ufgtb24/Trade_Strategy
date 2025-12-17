# Daily Pool 完整判断流程分析报告

## 执行摘要 (Executive Summary)

Daily Pool 是一个基于**阶段状态机 (Phase State Machine)** 的突破后观察系统，用于在突破发生后追踪价格行为，识别健康的回调整理模式，并在合适时机生成买入信号。

核心设计理念：
- **阶段驱动**：使用7个离散阶段 (INITIAL, PULLBACK, CONSOLIDATION, REIGNITION, SIGNAL, FAILED, EXPIRED) 描述价格演化
- **多维度分析**：整合价格模式、波动率、成交量三个维度的证据
- **证据驱动决策**：分析器负责"计算事实"，状态机负责"判断决策"
- **可解释性**：完整的转换历史记录和证据快照

从 entry 创建到买入信号生成，需要经历 4-5 个阶段，每个阶段都有严格的进入和退出条件，整个过程耗时约 10-30 天。

---

## 第一部分：阶段状态机模型 (Phase State Machine)

### 1.1 阶段定义 (Phase Definitions)

Daily Pool 定义了 7 个阶段，分为**活跃阶段 (4个)** 和**终态 (3个)**：

#### 活跃阶段 (Active Phases)

| 阶段 | 英文名 | 含义 | 典型持续时间 |
|------|--------|------|--------------|
| 1 | INITIAL | 刚入池，等待行情发展 | 1-3天 |
| 2 | PULLBACK | 健康回调，寻找支撑 | 3-15天 |
| 3 | CONSOLIDATION | 企稳整理，蓄势待发 | 5-20天 |
| 4 | REIGNITION | 放量启动，等待确认 | 1-3天 |

#### 终态 (Terminal Phases)

| 阶段 | 英文名 | 含义 | 触发条件 |
|------|--------|------|----------|
| 5 | SIGNAL | 信号已生成（成功终态） | REIGNITION 确认期满 |
| 6 | FAILED | 观察失败（失败终态） | 回调过深 / 阶段超时 |
| 7 | EXPIRED | 观察期满（失败终态） | 总观察期超过 30 天 |

### 1.2 阶段流转图 (Phase Transition Diagram)

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
    [INITIAL] ──────┼──> [PULLBACK] ──> [CONSOLIDATION] ─────┤
         │          │                           │             │
         │          └───────────────────────────┘             │
         │                                      │             │
         └──────────────────────────────────────┴──> [REIGNITION] ──> [SIGNAL]

    任意阶段 ──> [FAILED] (回调过深/阶段超时)
    任意阶段 ──> [EXPIRED] (观察期满)
```

**关键特点**：
- INITIAL 有两条路径：可直接进入 CONSOLIDATION（无明显回调），或先进入 PULLBACK
- REIGNITION 可能回退到 CONSOLIDATION（假突破）
- FAILED 和 EXPIRED 是全局检查，任何阶段都可能触发

---

## 第二部分：Entry 创建与初始化

### 2.1 Entry 创建流程

**触发条件**：当突破检测系统识别到一个有效突破时

**创建位置**：`DailyPoolManager.add_entry()` 或 `add_entry_from_breakout()`

**创建步骤**：
```python
# Step 1: 生成唯一 ID
entry_id = f"{symbol}_{breakout_date}"  # 例如: "AAPL_2025-01-15"

# Step 2: 创建状态机实例
phase_machine = PhaseStateMachine(
    config=self.config.phase,
    entry_date=breakout_date
)
# 初始状态: Phase.INITIAL, phase_start_date=breakout_date

# Step 3: 创建 Entry 对象
entry = DailyPoolEntry(
    symbol=symbol,
    entry_id=entry_id,
    breakout_date=breakout_date,
    breakout_price=breakout_price,           # 突破价格
    highest_peak_price=highest_peak_price,   # 突破的最高峰值价格
    initial_atr=initial_atr,                 # 突破时的ATR（用于标准化）
    quality_score=quality_score,             # 突破质量评分 (0-100)
    phase_machine=phase_machine,
    phase_history=PhaseHistory(),            # 空的转换历史
    post_breakout_high=highest_peak_price,
    post_breakout_low=breakout_price,
    current_price=breakout_price
)
```

**初始状态**：
- 阶段：`INITIAL`
- 历史记录：空
- 价格追踪：初始化为突破点数据

---

## 第三部分：每日评估流程 (Daily Evaluation Flow)

### 3.1 评估触发

**时机**：每日收盘后调用 `DailyPoolManager.update_all(as_of_date, price_data)`

**主流程**：
```
DailyPoolManager.update_all()
    ├─> 遍历所有活跃 Entry
    └─> 对每个 Entry：
            ├─> 获取截止到 as_of_date 的价格数据
            └─> DailyPoolEvaluator.evaluate(entry, df, as_of_date)
```

### 3.2 评估器核心流程 (DailyPoolEvaluator.evaluate)

这是整个系统的核心，分为 5 个步骤：

#### Step 1: 更新价格追踪
```python
entry.update_price_tracking(
    high=latest['high'],
    low=latest['low'],
    close=latest['close']
)
# 更新 post_breakout_high, post_breakout_low, current_price
```

#### Step 2: 三维度分析 (三个分析器并行工作)

```python
# 价格模式分析
price_result = PricePatternAnalyzer.analyze(df, entry, as_of_date)

# 波动率分析
volatility_result = VolatilityAnalyzer.analyze(df, initial_atr, as_of_date)

# 成交量分析
volume_result = VolumeAnalyzer.analyze(df, as_of_date)
```

#### Step 3: 聚合证据
```python
evidence = AnalysisEvidence(
    # 来自价格模式
    pullback_depth_atr=...,
    support_strength=...,
    support_tests_count=...,
    price_above_consolidation_top=...,
    consolidation_valid=...,
    # 来自波动率
    convergence_score=...,
    volatility_state=...,
    atr_ratio=...,
    # 来自成交量
    volume_expansion_ratio=...,
    surge_detected=...,
    volume_trend=...
)
```

#### Step 4: 驱动状态机
```python
transition = phase_machine.process(evidence)
# 根据当前阶段和证据，决定是否转换阶段
```

#### Step 5: 生成信号（如果到达 SIGNAL 阶段）
```python
if phase_machine.can_emit_signal():
    signal = self._generate_signal(entry, evidence, df)
```

---

## 第四部分：三个分析器的详细逻辑

### 4.1 价格模式分析器 (PricePatternAnalyzer)

**代码位置**：`BreakoutStrategy/daily_pool/analyzers/price_pattern.py`

**职责**：分析价格走势中的关键模式，包括回调深度、支撑位和企稳区间

**主入口函数**：`PricePatternAnalyzer.analyze()`

**输出**：`PricePatternResult`
- `pullback_depth_atr`: 回调深度（ATR单位）
- `support_zones`: 支撑区域列表
- `consolidation_range`: 企稳区间
- `price_position`: 价格相对企稳区间的位置

---

#### 4.1.1 回调深度计算

**函数名**：`PricePatternAnalyzer._calculate_pullback_depth()`

**含义**：计算从突破后最高点到当前价格的回调幅度，使用 ATR 进行标准化，使不同波动率的股票具有可比性。

**算法**：
```python
pullback_depth = (post_breakout_high - current_price) / initial_atr
```

**参数说明**：
- `post_breakout_high`: 突破后的最高价（Entry 中持续追踪更新）
- `current_price`: 当前收盘价
- `initial_atr`: 突破时的 ATR 值（作为标准化基准）

**返回值含义**：
- 返回值 0.5 表示从高点回调了 0.5 倍 ATR
- 返回值 1.0 表示从高点回调了 1 倍 ATR（较深回调）

**用途**：
- 触发 PULLBACK 阶段（depth >= 0.3 ATR）—— 表明开始出现有意义的回调
- 失败检查（depth > 1.5 ATR → FAILED）—— 表明回调过深，趋势可能已破坏

---

#### 4.1.2 支撑位检测

**函数名**：`PricePatternAnalyzer._detect_support_zones()`

**含义**：识别价格走势中的支撑区域。支撑位是价格多次下探但未能有效跌破的价位，表明该位置有较强的买盘承接。

**算法流程**：

**Step 1: 找局部最低点**

**含义**：在价格序列中找出"凹点"，即比前后几天都低的价位，这些点可能是支撑位的候选。

```python
window = 2  # 前后各2天
for i in range(window, len(lows) - window):
    if lows[i] == min(lows[i-window : i+window+1]):
        local_mins.append((date[i], lows[i]))
```

**Step 2: 按价格聚类**

**函数名**：`PricePatternAnalyzer._cluster_by_price()`

**含义**：将价格相近的局部最低点归为同一组，因为它们可能代表同一个支撑位。聚类容差使用 ATR 的 10% 作为判断标准。

```python
tolerance = 0.1 * ATR  # 聚类容差
# 将价格相近（差距 <= tolerance）的局部最低点聚类
clusters = cluster_by_price(local_mins, tolerance)
```

**Step 3: 过滤有效支撑**

**含义**：只保留被测试过至少 2 次的支撑位。单次触及不能确认为有效支撑，多次测试未破才能证明该位置确实存在买盘。

```python
valid_zones = [c for c in clusters if len(c) >= min_touches]  # 默认至少触及2次
```

**Step 4: 计算支撑强度**

**函数名**：`PricePatternAnalyzer._calculate_support_strength()`

**含义**：量化每个支撑位的强度，综合考虑测试次数、时间跨度和反弹质量三个维度。

```python
strength = (
    0.4 * min(test_count / 5, 1.0) +      # 测试次数分数：测试越多越强
    0.3 * min(time_span / 15, 1.0) +      # 时间跨度分数：跨度越长越可靠
    0.3 * bounce_quality                   # 反弹质量分数：反弹力度
)
```

**强度分数解读**：
- `strength >= 0.7`: 强支撑，多次测试且时间跨度长
- `strength >= 0.5`: 中等支撑，具有一定可靠性
- `strength < 0.5`: 弱支撑，可能被跌破

**输出**：按强度降序排列的 `SupportZone` 列表

---

#### 4.1.3 企稳区间计算

**函数名**：`PricePatternAnalyzer._calculate_consolidation_range()`

**含义**：计算价格的企稳整理区间，即价格波动的"箱体"。企稳区间表明价格已经停止趋势性运动，进入横盘整理阶段。

**算法**：
```python
# 取最近 10 天收盘价（可配置）
closes = df.tail(consolidation_window)['close']

# 计算均值和标准差
mean = np.mean(closes)
std = np.std(closes)

# 定义区间：均值 ± 1.5 倍标准差
upper = mean + 1.5 * std
lower = mean - 1.5 * std

# 有效性检查：区间宽度不能过大
width_atr = (upper - lower) / atr
is_valid = (width_atr <= 2.0)  # 宽度超过 2 ATR 说明还在剧烈波动，不算企稳
```

**输出**：`ConsolidationRange`
- `upper_bound`: 区间上界，突破此价位可能触发 REIGNITION
- `lower_bound`: 区间下界，跌破此价位可能导致 FAILED
- `center`: 区间中心价格
- `width_atr`: 区间宽度（ATR单位）
- `is_valid`: 区间是否有效（宽度是否合理）

**判定逻辑**：
- 区间有效 (`is_valid=True`) 表明价格已进入窄幅整理，波动率收缩
- 区间无效 (`is_valid=False`) 表明价格仍在大幅波动，尚未企稳

---

#### 4.1.4 价格位置判断

**函数名**：`PricePatternAnalyzer._determine_price_position()`

**含义**：判断当前价格相对于企稳区间的位置，用于决定是否触发 REIGNITION 阶段或判定为失败。

**逻辑**：
```python
if price > upper_bound:
    position = "above_range"  # 突破区间上沿 → 可能触发 REIGNITION
elif price < lower_bound:
    position = "below_range"  # 跌破区间下沿 → 可能导致 FAILED
else:
    position = "in_range"     # 在区间内 → 继续整理
```

**位置含义**：
- `above_range`: 价格已向上突破企稳区间，表明多头开始发力，是启动信号的前兆
- `in_range`: 价格在区间内波动，属于正常的整理状态
- `below_range`: 价格跌破区间下沿，表明空头占优，可能导致观察失败

---

### 4.2 波动率分析器 (VolatilityAnalyzer)

**代码位置**：`BreakoutStrategy/daily_pool/analyzers/volatility.py`

**职责**：检测波动率是否收缩，判断价格是否进入企稳阶段。波动率收缩是健康整理的关键特征。

**主入口函数**：`VolatilityAnalyzer.analyze()`

**输出**：`VolatilityResult`
- `current_atr`: 当前ATR值
- `atr_ratio`: 当前ATR / 初始ATR（收缩程度）
- `convergence_score`: 收敛分数 (0-1)，越高表示波动率收缩越明显
- `volatility_state`: "contracting" | "stable" | "expanding"

---

#### 4.2.1 ATR 序列计算

**函数名**：`VolatilityAnalyzer._calculate_atr_series()`

**含义**：计算 Average True Range (ATR) 序列，ATR 是衡量价格波动幅度的标准指标。ATR 下降表示波动率收缩，是企稳的信号。

**算法**：
```python
# True Range: 取三者中的最大值
tr1 = high - low                    # 当日振幅
tr2 = abs(high - close.shift(1))    # 当日最高与前日收盘的差
tr3 = abs(low - close.shift(1))     # 当日最低与前日收盘的差
tr = max(tr1, tr2, tr3)

# ATR = True Range 的 N 日移动平均（默认 14 日）
atr = tr.rolling(window=14).mean()
```

**输出含义**：
- ATR 值越大，表示价格波动越剧烈
- ATR 值下降，表示波动率在收缩，价格趋于平稳

---

#### 4.2.2 收敛分数计算

**函数名**：`VolatilityAnalyzer._calculate_convergence_score()`

**含义**：综合评估波动率的收敛程度，分数越高表示波动率收缩越明显。收敛分数是判断能否从 PULLBACK 进入 CONSOLIDATION 的关键指标。

**公式**：
```
convergence_score = 斜率分数(0.5) + ATR比率分数(0.3) + 稳定性分数(0.2)
```

**详细计算**：

**1) 斜率分数 (0.5 权重)**

**辅助函数**：`VolatilityAnalyzer._linear_regression_slope()`

**含义**：通过线性回归计算 ATR 序列的变化趋势。斜率为负表示 ATR 在下降（波动率收缩），斜率越负分数越高。

```python
# 对最近 20 天 ATR 序列做线性回归
slope = linear_regression_slope(atr_series[-20:])
normalized_slope = slope / mean_atr  # 归一化

if slope < 0:  # ATR 在下降，波动率收缩
    slope_score = min(abs(normalized_slope) / 0.05, 1.0) * 0.5
else:  # ATR 在上升，波动率扩张，不得分
    slope_score = 0
```

**2) ATR 比率分数 (0.3 权重)**

**含义**：比较当前 ATR 与突破时的初始 ATR。比率越小，表示波动率收缩越多。

```python
atr_ratio = current_atr / initial_atr

if atr_ratio <= 0.8:  # 收缩到初始值的 80% 以下，满分
    ratio_score = 0.3
elif atr_ratio <= 1.0:  # 有所收缩，按比例得分
    ratio_score = 0.3 * (1.0 - atr_ratio) / (1.0 - 0.8)
else:  # 波动率扩张，不得分
    ratio_score = 0
```

**3) 稳定性分数 (0.2 权重)**

**含义**：评估近期 ATR 的稳定程度。变异系数 (CV) 越小，表示波动率越稳定。

```python
# 最近 5 天的变异系数 (CV = std / mean)
cv = std(last_5_atr) / mean(last_5_atr)
stability_score = max(0, 0.2 * (1 - cv / 0.3))
```

**典型得分解读**：
- `convergence_score >= 0.5`：波动率显著收缩，满足企稳条件，可以进入 CONSOLIDATION
- `convergence_score 0.3~0.5`：波动率有所收缩，但尚未达标
- `convergence_score < 0.3`：波动率扩张或不稳定，未企稳

---

#### 4.2.3 波动状态判断

**函数名**：`VolatilityAnalyzer._determine_volatility_state()`

**含义**：根据收敛分数和 ATR 比率，将波动率状态分类为三种状态，便于状态机做出决策。

**逻辑**：
```python
if convergence_score >= 0.5 and atr_ratio < 1.0:
    return "contracting"   # 收缩中：波动率下降，有利于企稳
elif convergence_score < 0.3 or atr_ratio > 1.2:
    return "expanding"     # 扩张中：波动率上升，不利于企稳
else:
    return "stable"        # 稳定：波动率变化不大
```

**状态含义**：
- `contracting`: 波动率正在收缩，价格趋于平稳，是健康整理的信号
- `stable`: 波动率保持稳定，既不明显收缩也不扩张
- `expanding`: 波动率正在扩张，可能出现新的方向性波动

---

### 4.3 成交量分析器 (VolumeAnalyzer)

**代码位置**：`BreakoutStrategy/daily_pool/analyzers/volume.py`

**职责**：检测放量突破，成交量是确认价格突破有效性的关键指标。真正的突破通常伴随明显放量。

**主入口函数**：`VolumeAnalyzer.analyze()`

**输出**：`VolumeResult`
- `baseline_volume`: 基准成交量（近期平均量）
- `current_volume`: 当前成交量
- `volume_expansion_ratio`: 放量比率（当前/基准）
- `surge_detected`: 是否检测到放量
- `volume_trend`: 成交量趋势

---

#### 4.3.1 基准量计算

**含义**：计算近期的平均成交量作为基准，用于判断当日成交量是否属于"放量"。

**算法**：
```python
baseline = mean(volume[-20:])  # 最近20天平均量
```

**参数说明**：
- 使用 20 日均量作为基准，能够平滑短期波动
- 基准量代表该股票的"正常"成交水平

---

#### 4.3.2 放量检测

**含义**：判断当前成交量是否显著高于正常水平。放量是突破有效性的重要确认信号。

**逻辑**：
```python
ratio = current_volume / baseline
surge_detected = (ratio >= 1.5)  # 至少 1.5 倍基准量
```

**判定标准**：
- `ratio >= 1.5`: 放量，表明有大量资金参与，突破可信度高
- `ratio >= 2.0`: 明显放量，强烈的突破信号
- `ratio < 1.5`: 未放量，突破可能是假突破

**用途**：
- 从 CONSOLIDATION 进入 REIGNITION 必须满足放量条件
- 放量比率越高，最终信号的置信度越高

---

#### 4.3.3 成交量趋势判断

**函数名**：`VolumeAnalyzer._determine_volume_trend()`

**含义**：判断成交量的整体趋势，通过比较短期均量和长期均量来确定。趋势信息用于辅助判断市场活跃度。

**算法**：
```python
short_ma = mean(volume[-5:])   # 短期均量（5日）
long_ma = mean(volume[-20:])   # 长期均量（20日）

if short_ma > long_ma * 1.1:   # 短期均量超过长期的 110%
    trend = "increasing"       # 成交量放大趋势
elif short_ma < long_ma * 0.9: # 短期均量低于长期的 90%
    trend = "decreasing"       # 成交量萎缩趋势
else:
    trend = "neutral"          # 成交量平稳
```

**趋势含义**：
- `increasing`: 近期成交活跃度上升，市场关注度增加
- `neutral`: 成交量保持正常水平
- `decreasing`: 近期成交萎缩，可能缺乏足够的买盘支撑

---

## 第五部分：状态机转换逻辑 (PhaseStateMachine)

### 5.1 状态机处理流程 (process 方法)

**输入**：`AnalysisEvidence`（聚合的三维分析结果）

**输出**：`PhaseTransitionResult`（转换动作）

**流程**：
```python
def process(evidence):
    # Step 0: 全局过期检查
    if total_days >= 30:
        return transition_to(EXPIRED)

    # Step 1: 全局失败检查
    if pullback_depth_atr > 1.5:
        return transition_to(FAILED, "回调过深")

    # Step 2: 阶段特定评估
    if current_phase == INITIAL:
        return _eval_initial(evidence)
    elif current_phase == PULLBACK:
        return _eval_pullback(evidence)
    elif current_phase == CONSOLIDATION:
        return _eval_consolidation(evidence)
    elif current_phase == REIGNITION:
        return _eval_reignition(evidence)
    else:
        return hold()  # 终态不再转换
```

### 5.2 各阶段转换条件

#### 5.2.1 INITIAL 阶段评估

**可能的转换**：
1. INITIAL → CONSOLIDATION（无回调直接企稳）
2. INITIAL → PULLBACK（开始回调）

**判断逻辑**：

```python
def _eval_initial(evidence):
    # 路径1: 直接进入企稳（无明显回调但波动收敛）
    if (evidence.pullback_depth_atr < 0.3 AND
        evidence.convergence_score >= 0.5):
        return transition_to(CONSOLIDATION,
            "Direct to consolidation: no pullback, volatility converging")

    # 路径2: 进入回调
    if evidence.pullback_depth_atr >= 0.3:
        return transition_to(PULLBACK,
            f"Entering pullback: depth={depth:.2f} ATR >= 0.3 ATR")

    # 否则保持 INITIAL
    return hold()
```

**关键参数**（来自配置）：
- `pullback_trigger_atr = 0.3`：回调触发阈值
- `min_convergence_score = 0.5`：最小收敛分数

---

#### 5.2.2 PULLBACK 阶段评估

**可能的转换**：
1. PULLBACK → CONSOLIDATION（企稳成功）
2. PULLBACK → FAILED（超时）

**判断逻辑**：

```python
def _eval_pullback(evidence):
    days_in_phase = (as_of_date - phase_start_date).days

    # 失败: 超时
    if days_in_phase > 15:
        return transition_to(FAILED,
            f"Pullback timeout: {days_in_phase} days > 15 days limit")

    # 进入企稳: 波动收敛 + 支撑形成
    if (evidence.convergence_score >= 0.5 AND
        evidence.support_tests_count >= 2):
        return transition_to(CONSOLIDATION,
            f"Entering consolidation: convergence={score:.2f}, support_tests={count}")

    return hold()
```

**关键条件**：
- 波动收敛：`convergence_score >= 0.5`
- 支撑形成：至少触及支撑 2 次
- 超时限制：15 天

**证据来源**：
- `convergence_score` ← VolatilityAnalyzer（波动率收缩程度）
- `support_tests_count` ← PricePatternAnalyzer（支撑位触及次数）

---

#### 5.2.3 CONSOLIDATION 阶段评估

**可能的转换**：
1. CONSOLIDATION → REIGNITION（放量突破）
2. CONSOLIDATION → FAILED（超时）

**判断逻辑**：

```python
def _eval_consolidation(evidence):
    days_in_phase = (as_of_date - phase_start_date).days

    # 失败: 超时
    if days_in_phase > 20:
        return transition_to(FAILED,
            f"Consolidation timeout: {days_in_phase} days > 20 days limit")

    # 再启动: 放量 + 突破区间上沿
    if (evidence.volume_expansion_ratio >= 1.5 AND
        evidence.price_above_consolidation_top):
        return transition_to(REIGNITION,
            f"Reignition triggered: volume={ratio:.1f}x >= 1.5x, price above top")

    return hold()
```

**关键条件**：
- 放量：`volume_expansion_ratio >= 1.5`（当前量 ≥ 1.5 倍基准量）
- 价格突破：`price_above_consolidation_top = True`
- 超时限制：20 天

**证据来源**：
- `volume_expansion_ratio` ← VolumeAnalyzer
- `price_above_consolidation_top` ← PricePatternAnalyzer（价格 > 企稳区间上界）

---

#### 5.2.4 REIGNITION 阶段评估

**可能的转换**：
1. REIGNITION → SIGNAL（确认成功，生成买入信号）
2. REIGNITION → CONSOLIDATION（假突破回退）

**判断逻辑**：

```python
def _eval_reignition(evidence):
    days_in_phase = (as_of_date - phase_start_date).days

    # 假突破: 价格回落到区间内
    if NOT evidence.price_above_consolidation_top:
        return transition_to(CONSOLIDATION,
            "False breakout: price fell back into consolidation range")

    # 确认信号: 维持突破状态达到确认天数
    if days_in_phase >= 1:  # breakout_confirm_days = 1
        return transition_to(SIGNAL,
            f"Signal confirmed: breakout maintained for {days_in_phase} days")

    return hold()
```

**关键条件**：
- 价格保持突破：连续 1 天（可配置）收盘在企稳区间上方
- 防止假突破：如果价格回落，退回 CONSOLIDATION

**确认机制**：
- 默认确认期 1 天
- 保守配置可设为 2 天

---

### 5.3 全局失败和过期检查

这两个检查在所有阶段都会执行，优先级最高：

#### 5.3.1 过期检查

**条件**：
```python
total_days = (as_of_date - entry_date).days
if total_days >= 30:
    return transition_to(EXPIRED, f"Observation period expired after {total_days} days")
```

**含义**：从入池开始，总观察期不超过 30 天

#### 5.3.2 失败检查

**条件**：
```python
if pullback_depth_atr > 1.5:
    return transition_to(FAILED,
        f"Pullback too deep: {depth:.2f} ATR > 1.5 ATR limit")
```

**含义**：回调幅度超过 1.5 ATR，判定为趋势破坏

---

## 第六部分：买入信号生成

### 6.1 信号触发条件

**时机**：状态机到达 `Phase.SIGNAL` 阶段

**触发逻辑**：
```python
if phase_machine.can_emit_signal():  # current_phase == Phase.SIGNAL
    signal = evaluator._generate_signal(entry, evidence, df)
```

### 6.2 信号生成流程

#### 6.2.1 计算置信度 (Confidence)

**公式**：
```
confidence =
    0.30 * convergence_score +      # 波动收敛
    0.25 * support_strength +       # 支撑强度
    0.25 * volume_score +           # 放量程度
    0.20 * quality_score            # 突破质量
```

**详细计算**：
```python
# 1. 波动收敛贡献
convergence_contribution = evidence.convergence_score * 0.30

# 2. 支撑强度贡献
support_contribution = evidence.support_strength * 0.25

# 3. 放量贡献（归一化到 0-1）
volume_score = min(evidence.volume_expansion_ratio / 2.0, 1.0)
volume_contribution = volume_score * 0.25

# 4. 突破质量贡献（归一化到 0-1）
quality_score = min(entry.quality_score / 100, 1.0)
quality_contribution = quality_score * 0.20

# 总置信度
confidence = sum(all_contributions)
```

**示例**：
- `convergence_score = 0.6` → 贡献 0.18
- `support_strength = 0.8` → 贡献 0.20
- `volume_expansion_ratio = 2.0` → volume_score = 1.0 → 贡献 0.25
- `quality_score = 75` → 贡献 0.15
- **总置信度 = 0.78**（强信号）

#### 6.2.2 确定信号强度

**规则**：
```python
if confidence >= 0.7:
    strength = SignalStrength.STRONG
elif confidence >= 0.5:
    strength = SignalStrength.NORMAL
else:
    strength = SignalStrength.WEAK
```

#### 6.2.3 计算交易参数

**入场价**：
```python
entry_price = entry.current_price  # 当前收盘价
```

**止损价**：
```python
recent_low = min(df.tail(10)['low'])  # 最近10天最低价
stop_loss = recent_low - 0.5 * entry.initial_atr
```

**仓位分配**：
```python
position_sizing = {
    'strong': 0.15,   # 强信号 15% 仓位
    'normal': 0.10,   # 普通信号 10% 仓位
    'weak': 0.05,     # 弱信号 5% 仓位
}
position_pct = position_sizing[strength.value]
```

### 6.3 信号数据结构

最终生成的 `DailySignal` 包含：

```python
DailySignal(
    symbol='AAPL',
    signal_date=date(2025, 02, 10),
    signal_type=SignalType.REIGNITION_BUY,
    strength=SignalStrength.STRONG,

    # 交易参数
    entry_price=175.50,
    stop_loss_price=172.30,
    position_size_pct=0.15,

    # 可解释性信息
    phase_when_signaled=Phase.SIGNAL,
    days_to_signal=18,  # 从入池到信号的天数
    confidence=0.78,
    evidence_summary={
        'pullback_depth_atr': 0.45,
        'convergence_score': 0.60,
        'support_tests': 3,
        'volume_ratio': 2.1,
        'volatility_state': 'contracting',
        'price_position': 'above'
    }
)
```

---

## 第七部分：完整判断流程时间线

### 典型案例演示

假设某股票 AAPL 在 2025-01-15 突破，以下是完整的演化过程：

#### Day 0 (2025-01-15, 突破日)
- **动作**：检测到突破，创建 Entry
- **阶段**：INITIAL
- **状态**：
  - breakout_price = $150.00
  - initial_atr = $2.50
  - quality_score = 75

---

#### Day 1-2 (2025-01-16 至 01-17)
- **阶段**：INITIAL（保持）
- **价格行为**：小幅震荡，未明显回调
- **分析器输出**：
  - pullback_depth_atr = 0.2（< 0.3，未触发回调）
  - convergence_score = 0.3（< 0.5，波动未收敛）
- **状态机判断**：条件不满足，保持 INITIAL

---

#### Day 3 (2025-01-18)
- **价格行为**：开始回调，收盘 $149.00
- **分析器输出**：
  - post_breakout_high = $151.50
  - current_price = $149.00
  - pullback_depth = (151.50 - 149.00) / 2.50 = **0.4 ATR**
- **状态机判断**：pullback_depth_atr >= 0.3
- **转换**：INITIAL → **PULLBACK**
- **原因**："Entering pullback: depth=1.0 ATR >= 0.3 ATR trigger"

---

#### Day 4-10 (2025-01-19 至 01-25)
- **阶段**：PULLBACK
- **价格行为**：在 $148-$149 区间震荡，多次测试 $148 支撑
- **分析器输出**：
  - 检测到支撑区域：$147.80 - $148.20（触及 3 次）
  - support_strength = 0.65
  - convergence_score = 0.45（波动率开始收缩，但未达标）
- **状态机判断**：convergence_score < 0.5，条件不满足
- **转换**：保持 PULLBACK

---

#### Day 11 (2025-01-26)
- **价格行为**：继续在 $148 附近整理，波动率显著收缩
- **分析器输出**：
  - convergence_score = **0.55**（达标！）
  - support_tests_count = **3**（达标！）
  - volatility_state = "contracting"
  - atr_ratio = 0.75（当前 ATR = $1.88）
- **状态机判断**：convergence_score >= 0.5 AND support_tests >= 2
- **转换**：PULLBACK → **CONSOLIDATION**
- **原因**："Entering consolidation: convergence=0.55, support_tests=3"

---

#### Day 12-17 (2025-01-27 至 02-01)
- **阶段**：CONSOLIDATION
- **价格行为**：在 $148-$150 窄幅震荡
- **分析器输出**：
  - consolidation_range: lower=$147.50, upper=$150.50
  - width_atr = (150.50 - 147.50) / 1.88 = 1.6 ATR（有效）
  - price_position = "in_range"
  - volume_expansion_ratio = 1.1（未放量）
- **状态机判断**：volume_expansion_ratio < 1.5，条件不满足
- **转换**：保持 CONSOLIDATION

---

#### Day 18 (2025-02-02)
- **价格行为**：放量突破，收盘 $151.20
- **分析器输出**：
  - current_volume = 15M 股
  - baseline_volume = 8M 股
  - volume_expansion_ratio = **1.88**（达标！）
  - price_above_consolidation_top = **True**（价格突破 $150.50）
  - surge_detected = True
- **状态机判断**：volume_expansion_ratio >= 1.5 AND price_above_consolidation_top
- **转换**：CONSOLIDATION → **REIGNITION**
- **原因**："Reignition triggered: volume=1.9x >= 1.5x, price above top"

---

#### Day 19 (2025-02-03, 确认日)
- **阶段**：REIGNITION
- **价格行为**：收盘 $152.00，维持在企稳区间上方
- **分析器输出**：
  - price_above_consolidation_top = True（仍在上方）
- **状态机判断**：days_in_phase = 1 >= breakout_confirm_days (1)
- **转换**：REIGNITION → **SIGNAL**
- **原因**："Signal confirmed: breakout maintained for 1 days >= 1 days required"

---

#### Day 19 (信号生成)
- **触发**：phase_machine.can_emit_signal() == True
- **置信度计算**：
  ```
  convergence_contribution = 0.55 * 0.30 = 0.165
  support_contribution     = 0.65 * 0.25 = 0.163
  volume_contribution      = min(1.88/2.0, 1.0) * 0.25 = 0.235
  quality_contribution     = 0.75 * 0.20 = 0.150

  total_confidence = 0.713
  ```
- **信号强度**：STRONG（>= 0.7）
- **交易参数**：
  - entry_price = $152.00
  - stop_loss = min(last_10_days_low) - 0.5*ATR = $147.50 - $0.94 = $146.56
  - position_size_pct = 0.15 (15%)

---

#### 生成的信号

```python
DailySignal(
    symbol='AAPL',
    signal_date=date(2025, 02, 03),
    signal_type=REIGNITION_BUY,
    strength=STRONG,
    entry_price=152.00,
    stop_loss_price=146.56,
    position_size_pct=0.15,
    days_to_signal=19,
    confidence=0.713,
    evidence_summary={
        'pullback_depth_atr': 0.4,
        'convergence_score': 0.55,
        'support_tests': 3,
        'volume_ratio': 1.88,
        'volatility_state': 'contracting',
        'price_position': 'above'
    }
)
```

---

## 第八部分：失败案例分析

### 案例1: 回调过深导致失败

**时间线**：
- Day 0: 入池，INITIAL
- Day 3: 回调开始，→ PULLBACK
- Day 7: 继续下跌，pullback_depth_atr = **1.6** (> 1.5)
- **转换**：PULLBACK → **FAILED**
- **原因**："Pullback too deep: 1.60 ATR > 1.5 ATR limit"

### 案例2: 回调阶段超时

**时间线**：
- Day 0-3: INITIAL → PULLBACK
- Day 4-18: 在 PULLBACK 阶段持续震荡，波动率未收敛
- Day 19: days_in_phase = **16** (> 15)
- **转换**：PULLBACK → **FAILED**
- **原因**："Pullback timeout: 16 days > 15 days limit"

### 案例3: 企稳超时

**时间线**：
- Day 0-3: INITIAL → PULLBACK
- Day 11: PULLBACK → CONSOLIDATION
- Day 12-32: 在 CONSOLIDATION 持续震荡，未放量突破
- Day 33: days_in_phase = **21** (> 20)
- **转换**：CONSOLIDATION → **FAILED**
- **原因**："Consolidation timeout: 21 days > 20 days limit"

### 案例4: 假突破

**时间线**：
- Day 18: CONSOLIDATION → REIGNITION（放量突破）
- Day 19: 价格回落到企稳区间内，price_above_consolidation_top = False
- **转换**：REIGNITION → **CONSOLIDATION**（回退）
- **原因**："False breakout: price fell back into consolidation range"

---

## 第九部分：关键配置参数总览

### 9.1 阶段转换阈值

| 参数名称 | 默认值 | 含义 | 影响的转换 |
|---------|--------|------|-----------|
| pullback_trigger_atr | 0.3 | 回调触发阈值 | INITIAL → PULLBACK |
| min_convergence_score | 0.5 | 最小收敛分数 | PULLBACK → CONSOLIDATION |
| min_support_tests | 2 | 最小支撑测试次数 | PULLBACK → CONSOLIDATION |
| min_volume_expansion | 1.5 | 最小放量倍数 | CONSOLIDATION → REIGNITION |
| breakout_confirm_days | 1 | 突破确认天数 | REIGNITION → SIGNAL |
| max_drop_from_breakout_atr | 1.5 | 最大回调深度 | 任意阶段 → FAILED |
| max_pullback_days | 15 | 回调阶段最长天数 | PULLBACK → FAILED |
| max_consolidation_days | 20 | 企稳阶段最长天数 | CONSOLIDATION → FAILED |
| max_observation_days | 30 | 总观察期限 | 任意阶段 → EXPIRED |

### 9.2 分析器参数

#### 价格模式分析器
- `min_touches = 2`：支撑位最小触及次数
- `touch_tolerance_atr = 0.1`：触及容差
- `local_min_window = 2`：局部最低点检测窗口
- `consolidation_window = 10`：企稳区间计算窗口
- `max_width_atr = 2.0`：最大区间宽度

#### 波动率分析器
- `atr_period = 14`：ATR 计算周期
- `lookback_days = 20`：收敛分析回看天数
- `contraction_threshold = 0.8`：收缩判定阈值

#### 成交量分析器
- `baseline_period = 20`：基准量计算周期
- `expansion_threshold = 1.5`：放量判定阈值

### 9.3 信号生成参数

#### 置信度权重
- convergence: 0.30
- support: 0.25
- volume: 0.25
- quality: 0.20

#### 仓位分配
- strong (>= 0.7): 15%
- normal (>= 0.5): 10%
- weak (< 0.5): 5%

---

## 第十部分：设计优势与局限性

### 10.1 设计优势

#### 1. 可解释性强
- 每次阶段转换都有明确的原因
- 完整的历史记录和证据快照
- 信号包含详细的证据摘要

#### 2. 自适应性
- 所有价格阈值使用 ATR 标准化
- 自动适应不同股票的波动特性

#### 3. 防止假突破
- REIGNITION 阶段设置确认机制
- 价格回落会退回 CONSOLIDATION
- 多维度验证（价格 + 波动 + 成交量）

#### 4. 风险控制
- 多重失败检查（回调过深、阶段超时、观察期限）
- 动态止损（基于近期低点 - 0.5 ATR）
- 仓位与置信度关联

#### 5. 模块化设计
- 分析器和状态机职责清晰
- 证据驱动决策，易于调试
- 配置参数集中管理

### 10.2 潜在局限性

#### 1. 参数敏感性
- 多个阈值参数需要精心调优
- 不同市场环境可能需要不同配置
- **建议**：通过回测优化参数

#### 2. 固定阶段序列
- 当前只支持一条主路径（INITIAL → PULLBACK → CONSOLIDATION → REIGNITION → SIGNAL）
- 无法处理非典型模式（如直接启动、双底等）
- **建议**：未来可增加更多转换路径

#### 3. 单一信号类型
- 目前仅支持 REIGNITION_BUY（再启动买入）
- 不支持其他模式（如突破回踩、底部启动等）
- **建议**：扩展 SignalType

#### 4. 时间窗口固定
- 各阶段的超时限制是固定的
- 未考虑不同股票的周期差异
- **建议**：引入动态超时（基于历史数据）

---

## 总结与实践建议

### 核心判断流程概览

```
Entry 创建
    ↓
每日评估循环：
    ├─ 更新价格追踪
    ├─ 三维度分析（价格模式 + 波动率 + 成交量）
    ├─ 聚合证据
    ├─ 驱动状态机
    │   ├─ 全局检查（过期/失败）
    │   ├─ 阶段特定评估
    │   └─ 执行转换 / 保持
    └─ 如果到达 SIGNAL 阶段 → 生成买入信号
```

### 关键成功因素

**要达到买入信号，Entry 必须**：
1. 回调幅度适中（< 1.5 ATR）
2. 找到有效支撑（至少 2 次测试）
3. 波动率收缩（convergence_score >= 0.5）
4. 放量突破企稳区间（volume >= 1.5x baseline）
5. 确认期维持突破状态（默认 1 天）
6. 全程不超过 30 天观察期

### 实践建议

#### 1. 参数调优
- 使用回测数据验证配置有效性
- 根据市场环境选择 default / conservative / aggressive 配置
- 监控各阶段停留时间分布，调整超时参数

#### 2. 监控指标
- **转换成功率**：各阶段转换到下一阶段的比例
- **平均耗时**：从入池到信号的平均天数
- **失败原因分布**：统计哪种失败最常见

#### 3. 风险管理
- 严格执行止损（建议使用动态追踪止损）
- 遵守仓位限制
- 关注置信度低的信号（< 0.6 考虑跳过）

#### 4. 扩展方向
- 增加更多信号类型（突破回踩、底部启动）
- 引入机器学习优化置信度计算
- 动态调整超时参数

---

## 附录：代码位置索引

| 组件 | 文件路径 |
|------|---------|
| 阶段枚举 | `BreakoutStrategy/daily_pool/models/phase.py` |
| Entry 数据结构 | `BreakoutStrategy/daily_pool/models/entry.py` |
| 信号数据结构 | `BreakoutStrategy/daily_pool/models/signal.py` |
| 阶段历史 | `BreakoutStrategy/daily_pool/models/history.py` |
| 状态机核心 | `BreakoutStrategy/daily_pool/state_machine/machine.py` |
| 证据聚合 | `BreakoutStrategy/daily_pool/state_machine/evidence.py` |
| 价格模式分析器 | `BreakoutStrategy/daily_pool/analyzers/price_pattern.py` |
| 波动率分析器 | `BreakoutStrategy/daily_pool/analyzers/volatility.py` |
| 成交量分析器 | `BreakoutStrategy/daily_pool/analyzers/volume.py` |
| 评估器 | `BreakoutStrategy/daily_pool/evaluator/daily_evaluator.py` |
| 池管理器 | `BreakoutStrategy/daily_pool/manager/pool_manager.py` |
| 配置定义 | `BreakoutStrategy/daily_pool/config/config.py` |
| 默认配置 | `configs/daily_pool/default.yaml` |

---

**报告完成日期**：2026-01-04
**分析目标**：Daily Pool 完整判断流程
**代码版本**：基于当前 pure_daily 分支
