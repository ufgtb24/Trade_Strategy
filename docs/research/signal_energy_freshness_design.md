# 信号能量鲜度设计方案

> 日期: 2026-02-08
> 参与: 3 Tommy agents 并行分析 + team-lead 整合
> 问题起源: VTGN 案例 — weighted_sum=9.0 但已完成派发，能量耗尽

---

## 一、问题陈述

### 现状

```python
weighted_sum = sum(signal.strength for signal in signals)  # lookback=42 交易日内全部等权
```

### 核心缺陷

当前系统将信号视为**静态标记**，但信号实际上代表**势能**——它会随着价格运动被释放和耗散。

**VTGN 案例**:

| 指标 | 值 | 问题 |
|------|-----|------|
| weighted_sum | 9.0 | 排名极高 |
| 信号序列 | D → V → V → | 看似强势 |
| amplitude | 0.5 | 未触发 turbulent (< 0.8) |
| 实际走势 | 暴涨→派发→暴跌 | scan_date 时能量已耗尽 |

**根因**: `weighted_sum = Σ(strength)` 丢弃了所有**轨迹信息**——信号发生后价格去了哪里、回来了多少、当前在什么位置。

### 缺失的信息维度

| 维度 | 当前系统 | 需要的 |
|------|---------|--------|
| 信号后价格走势 | 不跟踪 | 涨了多少？回撤了多少？ |
| 信号价格 vs 当前价格 | 不比较 | 信号"论点"是否仍成立？ |
| 窗口内价格结构 | 仅 amplitude | 是正在拉升、已完成派发、还是底部蓄力？ |

---

## 二、三个代理的分析结论

### Agent-1: 能量耗散概念框架

**核心洞察**: 信号 = 势能。势能通过两步耗散：
1. **Realization (实现)**: 信号后价格上涨多少 → 势能转化为动能
2. **Retracement (回撤)**: 上涨后又跌回多少 → 动能消耗殆尽

```
realization = (peak_after - signal_price) / signal_price
retracement = (peak_after - current_price) / (peak_after - signal_price)
freshness = clip(1.0 - realization × retracement, 0, 1)
```

**关键边界**: `retracement > 1.0` → 价格跌破信号价 → 信号论点失效 → freshness = 0

### Agent-2: 信号有效性衰减机制

**核心设计**: Price Round-Trip Ratio (PRTR)

动量信号 (B/V/Y):
```
rise = peak_after_signal - signal_price
giveback = peak_after_signal - current_price
prtr = clip(giveback / rise, 0, 1)
price_decay = 1.0 - prtr^alpha  # alpha=1.5
```

支撑信号 (D): 基于价格接近度，底部附近保持有效

时间衰减: `time_decay = 0.5^(days / half_life)`，half_life=30

**VTGN 结果**: 9.0 → ~2.2（两个 V 归零，D 部分保留）

### Agent-3: 派发完成检测

**核心设计**: 3 条件合取

```python
distribution_complete = (
    peak_recency >= 0.60      # 峰值在窗口前 40% 位置
    and drawdown >= 0.35      # 从峰值回撤 ≥ 35%
    and position_ratio <= 0.30 # 当前价在窗口下 30%
)
```

**VTGN**: peak_recency=0.74, drawdown=0.75, position=0.10 → 正确检测

---

## 三、方案整合与对比

### 三种方法的关系

| 维度 | Agent-1 (freshness) | Agent-2 (PRTR decay) | Agent-3 (distribution) |
|------|---------------------|---------------------|----------------------|
| 粒度 | 逐信号 | 逐信号 + 时间衰减 | 窗口级 |
| 机制 | 乘法因子 | 乘法因子 | 布尔过滤 |
| 参数 | 0 个 | 2 个 (alpha, half_life) | 3 个 (阈值) |
| 信号类型区分 | 无 | 有 (D vs BVY) | 无 |
| 计算复杂度 | O(signals × days) | O(signals × days) | O(days) |

**关键观察**: Agent-1 和 Agent-2 在数学上高度相似（都是 "涨了多少 × 跌回多少"），Agent-2 增加了：
- D 信号的独立逻辑（底部支撑不应被涨幅衰减）
- 时间衰减（远期信号自然降权）
- 非线性曲线 (alpha=1.5)，容忍正常回调

---

## 四、推荐方案: PRTR 信号鲜度 + 派发检测标记

### 设计原则

遵循渐进式复杂度：**一个核心机制 + 一个辅助标记**，分 Phase 实现。

### 架构

```
┌──────────────────────────────────────────────────────┐
│ Layer 1: 信号鲜度计分 (PRTR)                          │
│   逐信号计算 price_decay × time_decay                 │
│   → 替代等权加总，精确反映每个信号的剩余价值            │
│   effective_sum = Σ(strength × price_decay × time_decay)│
├──────────────────────────────────────────────────────┤
│ Layer 2: 派发完成标记 (Distribution Flag)              │
│   窗口级几何检测，3 条件合取                            │
│   → 辅助标记，用于 UI 高亮和可选过滤                    │
│   与 turbulent 并列，非替代                             │
└──────────────────────────────────────────────────────┘
```

### 为什么这样组合

| 子问题 | 解决层 | 角色 |
|--------|--------|------|
| 单个信号的"能量已耗尽" | Layer 1 (PRTR) | **核心排序机制** |
| 整体走势"派发已完成" | Layer 2 (Distribution) | **辅助风险标记** |

- Layer 1 是**计分机制**：精细调整每个信号的权重，影响排序
- Layer 2 是**分类标记**：给用户一个宏观判断，可用于过滤
- 两层正交：Layer 1 可能给出 effective_sum=2.2（降低但非零），Layer 2 同时标记为"派发完成"让用户一目了然

---

## 五、详细设计

### 5.1 Layer 1: PRTR 信号鲜度

#### 核心函数

```python
def calculate_signal_freshness(
    signal: AbsoluteSignal,
    df_slice: pd.DataFrame,
    current_price: float,
    scan_date: date,
    alpha: float = 1.5,
    half_life: int = 30,
) -> float:
    """
    计算单个信号的鲜度因子 (0.0 ~ 1.0)。

    鲜度 = price_decay × time_decay

    Args:
        signal: 绝对信号
        df_slice: lookback 窗口的 OHLCV 数据
        current_price: scan_date 的收盘价
        scan_date: 扫描日期
        alpha: PRTR 曲线指数 (>1 容忍小回调, 惩罚大回撤)
        half_life: 时间衰减半衰期 (交易日)

    Returns:
        鲜度因子 [0.0, 1.0]
    """
    # === Price Decay ===
    price_decay = _calc_price_decay(signal, df_slice, current_price, alpha)

    # === Time Decay ===
    days_elapsed = _trading_days_between(signal.date, scan_date, df_slice)
    time_decay = 0.5 ** (days_elapsed / half_life)

    return price_decay * time_decay
```

#### 动量信号 (B/V/Y) 的 Price Decay

```python
def _calc_price_decay_momentum(
    signal: AbsoluteSignal,
    df_slice: pd.DataFrame,
    current_price: float,
    alpha: float,
) -> float:
    """
    动量信号的价格衰减: 基于 Price Round-Trip Ratio。

    rise = 信号后最高价 - 信号价
    giveback = 信号后最高价 - 当前价
    prtr = giveback / rise (0=没回, 1=完全往返)

    price_decay = 1.0 - prtr^alpha

    alpha > 1 使曲线凸起，容忍正常回调:
    - 30% 回撤 → 衰减仅 16% (prtr=0.3, decay=0.84)
    - 50% 回撤 → 衰减 35% (prtr=0.5, decay=0.65)
    - 80% 回撤 → 衰减 72% (prtr=0.8, decay=0.28)
    - 100% 往返 → 完全归零 (prtr=1.0, decay=0.00)
    """
    # 信号日期之后的最高价
    signal_idx = df_slice.index.get_indexer([signal.date], method="nearest")[0]
    after_slice = df_slice.iloc[signal_idx:]
    high_col = "High" if "High" in after_slice.columns else "high"
    peak_after = after_slice[high_col].max()

    rise = peak_after - signal.price
    if rise <= 0:
        # 信号后从未上涨 → 论点未被验证也未被否定
        # 如果当前价低于信号价，部分衰减
        if current_price < signal.price:
            drop_ratio = (signal.price - current_price) / signal.price
            return max(0.0, 1.0 - drop_ratio)
        return 1.0  # 信号价附近横盘，保持有效

    giveback = peak_after - current_price
    prtr = min(max(giveback / rise, 0.0), 1.0)
    return 1.0 - prtr ** alpha
```

#### 支撑信号 (D) 的 Price Decay

```python
def _calc_price_decay_support(
    signal: AbsoluteSignal,
    current_price: float,
) -> float:
    """
    支撑信号 (D) 的价格衰减: 基于价格位置接近度。

    D 信号代表底部支撑。其有效性取决于当前价格是否仍在支撑区域附近。

    - 当前价在信号价 ±20% 内 → 1.0 (支撑仍有效)
    - 当前价跌破信号价 10%+ → 0.1 (支撑失败)
    - 当前价涨超信号价 50%+ → 0.3 (已远离底部, 不再相关)
    - 中间区域线性插值
    """
    if signal.price <= 0:
        return 0.0

    price_ratio = current_price / signal.price

    if 0.9 <= price_ratio <= 1.2:
        return 1.0  # 在支撑区域附近
    elif price_ratio < 0.9:
        # 跌破支撑，快速衰减
        return max(0.1, 1.0 - (0.9 - price_ratio) / 0.2)
    else:
        # 远离底部，逐步衰减
        return max(0.3, 1.0 - (price_ratio - 1.2) / 0.5)
```

#### 路由函数

```python
def _calc_price_decay(signal, df_slice, current_price, alpha):
    """根据信号类型路由到对应的 price_decay 计算。"""
    if signal.signal_type == SignalType.DOUBLE_TROUGH:
        return _calc_price_decay_support(signal, current_price)
    else:
        return _calc_price_decay_momentum(signal, df_slice, current_price, alpha)
```

#### 替代 calc_effective_weighted_sum

```python
def calc_effective_weighted_sum(
    signals: List[AbsoluteSignal],
    turbulent: bool,
    df_slice: pd.DataFrame = None,
    current_price: float = None,
    scan_date: date = None,
) -> float:
    """
    计算有效加权强度总和。

    新逻辑:
    - 每个信号的 strength 乘以 freshness 因子
    - turbulent 仍然只保留 D 信号（与现有机制正交）

    向后兼容: 当 df_slice/current_price/scan_date 未提供时，
    退化为原始等权加总行为。
    """
    # 向后兼容：缺少数据时退化为原始行为
    use_freshness = (df_slice is not None and current_price is not None
                     and scan_date is not None)

    total = 0.0
    for s in signals:
        # turbulent 过滤（保持现有逻辑）
        if turbulent and s.signal_type != SignalType.DOUBLE_TROUGH:
            continue

        if use_freshness:
            freshness = calculate_signal_freshness(
                s, df_slice, current_price, scan_date
            )
        else:
            freshness = 1.0

        total += s.strength * freshness

    return round(total, 2)
```

### 5.2 Layer 2: 派发完成标记

```python
def detect_distribution_complete(
    df_slice: pd.DataFrame,
    lookback_days: int,
    peak_recency_threshold: float = 0.60,
    drawdown_threshold: float = 0.35,
    position_threshold: float = 0.30,
) -> bool:
    """
    检测 lookback 窗口内是否已完成"拉升→派发→暴跌"循环。

    三条件合取，确保高特异性:
    1. 峰值出现在窗口前部 (peak_recency >= 0.60)
    2. 从峰值大幅回撤 (drawdown >= 0.35)
    3. 当前价位在窗口低位 (position_ratio <= 0.30)

    Args:
        df_slice: 价格数据
        lookback_days: 回看天数
        peak_recency_threshold: 峰值位置阈值 (0=今天, 1=窗口起点)
        drawdown_threshold: 从峰值回撤阈值
        position_threshold: 当前价格位置阈值

    Returns:
        True 表示已完成派发
    """
    window = df_slice.iloc[-lookback_days:] if len(df_slice) > lookback_days else df_slice

    high_col = "High" if "High" in window.columns else "high"
    low_col = "Low" if "Low" in window.columns else "low"
    close_col = "Close" if "Close" in window.columns else "close"

    window_high = window[high_col].max()
    window_low = window[low_col].min()
    current_close = window[close_col].iloc[-1]

    if window_high <= window_low or window_high <= 0:
        return False

    # 峰值位置: 距离 scan_date 多远 (0=今天, 1=窗口起点)
    peak_idx = window[high_col].idxmax()
    peak_pos = window.index.get_loc(peak_idx)
    total_bars = len(window) - 1
    peak_recency = 1.0 - (peak_pos / total_bars) if total_bars > 0 else 0.0

    # 从峰值回撤幅度
    drawdown = 1.0 - current_close / window_high

    # 当前价格在窗口中的位置 (0=最低, 1=最高)
    position_ratio = (current_close - window_low) / (window_high - window_low)

    return (
        peak_recency >= peak_recency_threshold
        and drawdown >= drawdown_threshold
        and position_ratio <= position_threshold
    )
```

### 5.3 数据模型变更

```python
@dataclass
class SignalStats:
    symbol: str
    signal_count: int
    signals: List[AbsoluteSignal]
    latest_signal_date: date
    latest_price: float
    weighted_sum: float = 0.0            # 现在包含鲜度衰减
    sequence_label: str = ""
    amplitude: float = 0.0
    turbulent: bool = False
    distribution_complete: bool = False  # 新增: 派发完成标记
```

### 5.4 完整数据流

```
Scanner Worker
  │
  ├── 检测信号 (不变)
  ├── 计算 amplitude (不变)
  ├── 返回 df_slice (新增: 传递给 aggregator 用于鲜度计算)
  │
  └──→ Aggregator
        │
        ├── 每个信号: calculate_signal_freshness()      ← 新增
        ├── is_turbulent(amplitude)                      (不变)
        ├── calc_effective_weighted_sum(signals, turbulent,
        │       df_slice, current_price, scan_date)      ← 扩展
        ├── detect_distribution_complete(df_slice)        ← 新增
        │
        └── SignalStats:
              weighted_sum: float     # 含鲜度衰减
              distribution_complete: bool  # 派发标记
              (turbulent: bool 保留)
```

**注意: 数据流变更**

当前 scanner worker 不返回 df_slice（只返回 signals + amplitude）。
新方案需要在 worker 中计算鲜度，或将必要数据传递给 aggregator。

**推荐**: 在 worker 中完成鲜度计算，返回 `freshness_by_signal` 和 `distribution_complete`，
避免 pickle 大型 DataFrame 的进程间传输开销。

```python
# Worker 返回值扩展
def _scan_single_stock(...) -> Tuple[
    List[AbsoluteSignal],  # filtered_signals (signal.strength 已乘以 freshness)
    List[str],             # skipped
    Optional[str],         # skip_reason
    float,                 # amplitude
    bool,                  # distribution_complete  ← 新增
]:
```

---

## 六、VTGN 案例验证

### 输入数据 (推测)

```
VTGN lookback=42 天窗口:
- 前期: 底部 ~$1.5, D 信号 (day -35, price=$1.5)
- 中期: 暴涨至 ~$6.0, V 信号 (day -20, price=$3.0), V 信号 (day -15, price=$4.5)
- 后期: 暴跌回 ~$1.8
- scan_date: current_price = $1.8
```

### Layer 1: PRTR 逐信号计算

| 信号 | 类型 | price | strength | peak_after | price_decay | time_decay | freshness | effective |
|------|------|-------|----------|------------|-------------|------------|-----------|-----------|
| D | 支撑 | $1.5 | 5.0 | — | 1.0 (价格$1.8 在±20%内) | 0.5^(35/30)=0.45 | 0.45 | 2.23 |
| V | 动量 | $3.0 | 1.0 | $6.0 | rise=3.0, giveback=4.2, prtr=1.0 → 0.0 | 0.63 | 0.0 | 0.0 |
| V | 动量 | $4.5 | 1.0 | $6.0 | rise=1.5, giveback=4.2, prtr=1.0 → 0.0 | 0.71 | 0.0 | 0.0 |

**weighted_sum: 9.0 → 2.23**

### Layer 2: 派发完成检测

```
peak_recency = ~0.74 (峰值在窗口前 26% 位置)  >= 0.60 ✓
drawdown = 1 - 1.8/6.0 = 0.70                  >= 0.35 ✓
position_ratio = (1.8-1.5)/(6.0-1.5) = 0.07    <= 0.30 ✓

→ distribution_complete = True
```

### 综合效果

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| weighted_sum | 9.0 | 2.23 |
| turbulent | False | False (amplitude=0.5 < 0.8) |
| distribution_complete | — | **True** |
| 排名 | 极高 | 大幅降低 |
| UI 显示 | 绿色高亮 | 标记为派发完成 |

---

## 七、反面验证: 底部蓄力案例

### 场景: 低位横盘 + D 信号 + 近期 V 信号

```
股票 X lookback=42 天:
- 底部横盘 ~$2.0, D 信号 (day -25, price=$2.0, tr_num=3)
- 近期放量 V 信号 (day -3, price=$2.2)
- scan_date: current_price = $2.3
```

### Layer 1: PRTR 计算

| 信号 | 类型 | price | strength | price_decay | time_decay | freshness | effective |
|------|------|-------|----------|-------------|------------|-----------|-----------|
| D | 支撑 | $2.0 | 3.0 | 1.0 (价格$2.3 在+15%内) | 0.56 | 0.56 | 1.67 |
| V | 动量 | $2.2 | 1.0 | rise=$0.1, giveback=0 → prtr=0 → 1.0 | 0.93 | 0.93 | 0.93 |

**weighted_sum = 2.60** (保留大部分价值)

### Layer 2: 派发检测

```
peak_recency = ~0.07 (峰值在近期)  < 0.60 ✗

→ distribution_complete = False ✓ (未误杀)
```

---

## 八、参数清单

| 参数 | 层 | 推荐值 | 含义 | 可调 |
|------|-----|--------|------|------|
| alpha | L1 | 1.5 | PRTR 衰减曲线指数 (>1 容忍正常回调) | 是 |
| half_life | L1 | 30 | 时间衰减半衰期 (交易日) | 是 |
| peak_recency_threshold | L2 | 0.60 | 峰值位置阈值 | 是 |
| drawdown_threshold | L2 | 0.35 | 回撤幅度阈值 | 是 |
| position_threshold | L2 | 0.30 | 当前价格位置阈值 | 是 |

**核心参数**: alpha + half_life = 2 个 (Layer 1)
**辅助参数**: 3 个 (Layer 2, 可用默认值)

---

## 九、与 turbulent 的关系

| 维度 | turbulent | distribution_complete | PRTR freshness |
|------|-----------|----------------------|----------------|
| 粒度 | 窗口级 | 窗口级 | 逐信号 |
| 输出 | bool | bool | float per signal |
| 检测目标 | 价格振幅过大 | 完整拉升-派发周期 | 单个信号能量耗散 |
| 影响排序 | 是 (仅保留 D) | 否 (仅标记) | 是 (乘法衰减) |
| VTGN 覆盖 | **否** (amp=0.5<0.8) | **是** | **是** |

三者互补:
- **turbulent**: 高振幅极端风险控制 (保留)
- **distribution_complete**: 派发完成的宏观标记 (新增)
- **PRTR freshness**: 精细信号级计分调整 (新增, 核心)

---

## 十、实施路线图

### Phase 1: PRTR 信号鲜度 (核心)
**改动范围**: `composite.py`, `aggregator.py`, `scanner.py`
- 新增 `calculate_signal_freshness()` 及子函数
- 扩展 `calc_effective_weighted_sum()` (向后兼容)
- Worker 中计算 freshness 并应用到 strength
- **验证**: 对比 VTGN 等已知案例的 weighted_sum 变化

### Phase 2: 派发完成标记
**改动范围**: `composite.py`, `models.py`, `scanner.py`, `aggregator.py`
- 新增 `detect_distribution_complete()`
- `SignalStats` 添加 `distribution_complete` 字段
- Worker 中计算并返回
- **验证**: 检查标记准确率

### Phase 3: UI 集成
**改动范围**: `signal_scan_manager.py`, `stock_list_panel.py`, `ui_config.yaml`
- JSON 输出新增 `distribution_complete` 字段
- UI 新增"Distribution"列或颜色标记
- 可选: "Hide Distribution" 过滤器
- **验证**: UI 显示正确

### Phase 4: 参数调优 (可选)
- 在历史数据上回测不同 alpha/half_life 组合
- 优化 Layer 2 阈值

---

## 十一、风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| PRTR 对横盘股信号过度衰减 | 低 | 横盘时 rise≈0，prtr 无意义，fallback 返回 1.0 |
| time_decay 对远期强信号惩罚过重 | 中 | half_life=30 在 42 天窗口内衰减温和 (最远约 0.4) |
| Worker 进程间传输增加 | 低 | 在 worker 内完成计算，只传回标量结果 |
| 底部 D 信号被 time_decay 过度削弱 | 低 | D 的 price_decay 保持 1.0 弥补，综合仍有合理权重 |
| distribution 误标活跃下跌趋势 | 低 | peak_recency >= 0.60 排除近期暴跌 |

---

*报告生成: 2026-02-08 | 基于 3 Tommy agents 并行分析整合*
