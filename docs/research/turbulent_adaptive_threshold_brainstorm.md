# Turbulent Filter 自适应阈值头脑风暴报告

> 日期: 2026-02-07
> 参与: 4 Tommy agents 并行分析 + team-lead 整合
> 数据基础: datasets/pkls/ 美股历史数据 (2000-10574 只股票样本)

---

## 一、问题陈述

### 现状
```python
amplitude = (max(High) - min(Low)) / min(Low)  # lookback=42 交易日
turbulent = amplitude >= 0.8  # 固定阈值 80%
```

### 核心矛盾
用户的**核心交易标的是 $1-$10 低价股**，但固定 80% 阈值对低价股系统性误杀：

| 价格段 | 被 80% 过滤比例 | 中位数 amplitude |
|--------|---------------|-----------------|
| $0-2   | **72.5-80.5%** | 106-205%       |
| $2-5   | **35-39.5%**   | 42-63%         |
| $5-10  | **19.5-20.1%** | 28-34%         |
| $10-20 | 8.6-9.4%      | 16-17%         |
| $20-50 | 2.7-2.8%      | 9-10%          |
| $50+   | 1.9-3.3%      | 13-16%         |

**$1-$10 低价股有约 32% 被过滤，而 $50+ 仅 ~3%。误杀比高达 10 倍。**

### 根因分析
amplitude 的两层问题：
1. **概念偏差**: amplitude 衡量"价格区间跨度"(range)，不是"方向性运动"(directional surge)。低价股在区间内反复震荡也会被标记
2. **价位敏感**: 低价股天然波动率更高（tick size 效应、投机性、流动性差），任何百分比指标都会天然偏高

---

## 二、四种方案深度分析

### 方案 A: 基于波动率的自适应阈值

**核心思路**: `normalized_amp = amplitude / (daily_vol × √lookback)`，score > k 则标记。

**实证结论**:
- 将各价位标记率差距从 38.7× 缩小到 ~13×
- **致命缺陷 — 高波动免疫**: $1-$10 高波动+高振幅股票中，**78.8% 逃脱 k=5 过滤**
- 原因：低价股天然高波动，用自身波动率标准化后，真正的暴涨暴跌被"解释掉了"
- 案例: AACG ($1.27) amplitude=143%，因 daily_vol=13.6% 而 normalized_amp=1.62，远低于阈值
- pre-period vol 变体改善有限（72.7% 逃逸率）

**评价**: ❌ 不适合用户场景。用户的目标股恰好是高波动群体，vol-normalization 会放过真正该过滤的股票。

---

### 方案 B: 基于百分位数的动态阈值

**核心思路**: 每次扫描计算 amplitude 的 P95 作为动态阈值，或按价格分组计算。

**实证结论**:
- 分组 P95 将 $1-$10 过滤率从 31.9% 降至 5.0%
- **致命缺陷 — 批次依赖**: 全局 P95 的 CV=0.25，范围从 132% 到 852%
- 同一只股票在不同扫描批次中可能时而 turbulent 时而不是
- N<50 时 CV>0.6，完全不可靠
- 预计算改良版（基于历史大样本预算各 tier P95）**退化为"数据驱动的分段固定阈值"**

**评价**: ⚠️ 方向正确（用统计分布定义异常），但实时计算方案不可用。预计算版本有价值但本质是"换个方式得到分段阈值"。

---

### 方案 C: 重新定义"超涨"的度量指标

**核心洞察**: amplitude 混淆了两种现象——
1. 高振荡 (oscillation): 在区间内反复波动，range 大但无方向 → **不应标记**
2. 单方向剧烈运动 (directional surge): 快速拉升或暴跌 → **应该标记**

**9 种替代指标实证对比**:

| 指标 | 与 log(price) 相关性 | Cross-tier CV | 评价 |
|------|--------------------:|:------------:|------|
| amplitude (现状) | -0.227 | 1.225 | 基准 |
| **max_runup** | **-0.187** | **1.135** | ✅ 最佳单指标 |
| max_drawdown | -0.737 | 0.887 | ❌ 极度价位偏差 |
| max_directional | -0.187 | — | 被 drawdown 拉低 |
| max_slope_5d | -0.257 | — | 过敏于单日事件 |
| volume_anomaly | -0.196 | — | 伴随现象，非本质 |
| atr_ratio | -0.469 | — | amplitude 的每日版 |
| realized_vol | -0.665 | 0.919 | ❌ 衡量波动性非方向 |
| **amp/own_vol** | -0.266 | **0.171** | ✅ 最佳跨价位一致性 |
| intra-tier z-score | **-0.003** | — | ✅ 完美价位免疫，需预定义 tier |

**关键发现**: max_runup >= 0.8 标记的 291 只股票是 amplitude >= 0.8 标记的 346 只的**真子集**。amplitude 额外多标记的 55 只全是"仅高振荡"的低价股（false positives）。

**评价**: ✅ max_runup 作为底层指标替换 amplitude，语义更准确、false positive 减少 16%、实现极简（5 行代码）。

---

### 方案 D: 渐进式降权替代二值判断

**核心思路**: 将 `turbulent: bool` 改为 `decay_weight: float`，权重随 amplitude 平滑衰减。

**三种衰减函数对比** (amp=0.79 vs 0.81 的权重差):

| 函数 | 差值 | 特点 |
|------|------|------|
| Binary (现状) | **1.0000** | 悬崖效应 |
| 线性 | 0.0286 | 简单但有拐点 |
| Sigmoid | 0.0400 | 数学最平滑 |
| **分段线性** | **0.0333** | 语义最清晰 |

**推荐分段线性**: 三段语义 — 安全区(weight=1.0) / 过渡区(线性衰减) / 危险区(weight=0.0)

**关键洞察**: 与自适应阈值组合时，用 **归一化 amplitude** 可完全消除价格偏差：
```
normalized = amplitude / adaptive_threshold(price)
weight = decay(normalized)  # 参数固定，与价格无关
```

**评价**: ✅ 不是独立方案，但作为增强组件解决悬崖效应，与任何方案正交组合。

---

## 三、方案对比总结

| 维度 | A: 波动率 | B: 百分位 | C: 替代指标 | D: 渐进降权 |
|------|----------|----------|-----------|-----------|
| 低价股友好度 | 差（免疫78.8%） | 好 | 中-好 | 不独立 |
| 新增参数 | 2 (vol_window, k) | 1-2 (percentile, tiers) | 0 (替换) | 2 (start, end) |
| 实现复杂度 | 低-中 | 中 | **极低** | 低 |
| 可解释性 | 中 | 中 | **高** | 高 |
| 批次稳定性 | 稳定 | **不稳定** | 稳定 | 稳定 |
| 独立可用 | 否 | 有条件 | **是** | 否 |
| 系统兼容性 | 好 | 需改动 | **极好** | 好 |

---

## 四、推荐组合方案

### 最终推荐: C + B(预计算) + D 三层组合

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: 度量替换 (方案C)                             │
│   max_runup 替代 amplitude                           │
│   → 消除"高振荡误标记"问题，减少16% false positives   │
├─────────────────────────────────────────────────────┤
│ Layer 2: 数据驱动分层阈值 (方案B预计算版)              │
│   基于历史大样本，按价格 tier 预计算 P95 阈值          │
│   → 消除价位系统性偏差                                │
├─────────────────────────────────────────────────────┤
│ Layer 3: 渐进式降权 (方案D)                           │
│   分段线性衰减函数                                    │
│   → 消除悬崖效应，提供平滑过渡                         │
└─────────────────────────────────────────────────────┘
```

### 为什么这样组合

每层解决一个独立子问题：

| 子问题 | 解决层 | 效果 |
|--------|--------|------|
| amplitude 混淆振荡和超涨 | Layer 1 (max_runup) | 语义修正 |
| 不同价位的标记率差异 | Layer 2 (分层阈值) | 公平性修正 |
| 阈值边界的悬崖效应 | Layer 3 (渐进降权) | 平滑修正 |

三层正交，移除任何一层不影响其他层的功能。

### 具体实现设计

#### Layer 1: max_runup 计算

```python
def calculate_max_runup(df_slice: pd.DataFrame, lookback_days: int) -> float:
    """计算 lookback 窗口内的最大涨幅（从累积最低到后续最高）。

    替代 amplitude，仅捕获方向性上涨运动，不受区间震荡干扰。
    """
    window = df_slice.iloc[-lookback_days:] if len(df_slice) > lookback_days else df_slice
    high_col = "High" if "High" in window.columns else "high"
    low_col = "Low" if "Low" in window.columns else "low"

    highs = window[high_col].values
    lows = window[low_col].values

    cum_min = np.minimum.accumulate(lows)
    cum_min[cum_min <= 0] = np.nan  # 防止除零
    runups = (highs - cum_min) / cum_min

    return float(np.nanmax(runups)) if len(runups) > 0 else 0.0
```

**改动**: 替换 `calculate_amplitude`，返回值语义相同（百分比浮点数）。

#### Layer 2: 数据驱动分层阈值

**预计算过程**（离线执行，结果写入配置）:
1. 加载全量历史数据，计算每只股票的 max_runup
2. 按价格分为 3 个 tier: `<$5`, `$5-$20`, `$20+`
3. 每个 tier 取 P95 作为 turbulent 阈值
4. 结果写入 `configs/signals/absolute_signals.yaml`

```yaml
# 预计算 turbulent 阈值 (基于历史 P95)
turbulent:
  thresholds:
    tier_1:  # < $5
      max_price: 5
      threshold: 3.40   # 预计算值，需实际数据验证
    tier_2:  # $5-$20
      max_price: 20
      threshold: 0.80   # 预计算值
    tier_3:  # $20+
      max_price: null
      threshold: 0.50   # 预计算值
  decay:
    start_ratio: 0.6    # 达到阈值的 60% 开始降权
    end_ratio: 1.5      # 达到阈值的 150% 完全归零
```

**运行时查找**:
```python
def get_turbulent_threshold(price: float, config: dict) -> float:
    """根据股票价格查找对应 tier 的 turbulent 阈值。"""
    for tier in config["thresholds"].values():
        if tier["max_price"] is None or price < tier["max_price"]:
            return tier["threshold"]
    return config["thresholds"]["tier_3"]["threshold"]
```

**为什么选 3 个 tier 而非更多**:
- 3 tier 足以覆盖低价/中价/高价的结构性差异
- 更多 tier（如 5-7 个）收益递减，但增加配置复杂度
- tier 边界用价格的自然断点（$5 是 SEC 对 penny stock 的定义，$20 是机构投资的常见门槛）

#### Layer 3: 渐进式降权

```python
def calc_decay_weight(max_runup: float, threshold: float,
                      start_ratio: float = 0.6,
                      end_ratio: float = 1.5) -> float:
    """分段线性衰减: 归一化后的 max_runup 决定降权幅度。

    - normalized < start_ratio: weight = 1.0 (安全区)
    - start_ratio <= normalized < end_ratio: 线性衰减 (过渡区)
    - normalized >= end_ratio: weight = 0.0 (危险区)
    """
    normalized = max_runup / threshold if threshold > 0 else 0.0
    if normalized < start_ratio:
        return 1.0
    if normalized >= end_ratio:
        return 0.0
    return 1.0 - (normalized - start_ratio) / (end_ratio - start_ratio)


def calc_effective_weighted_sum(signals: list,
                                max_runup: float,
                                threshold: float) -> float:
    """计算有效加权和: D 信号免疫，B/V/Y 按 decay_weight 降权。"""
    weight = calc_decay_weight(max_runup, threshold)
    d_sum = sum(s.strength for s in signals
                if s.signal_type == SignalType.DOUBLE_TROUGH)
    bvy_sum = sum(s.strength for s in signals
                  if s.signal_type != SignalType.DOUBLE_TROUGH)
    return d_sum + bvy_sum * weight
```

### 完整数据流

```
Scanner worker
  │
  ├── 计算 max_runup (替代 amplitude)
  ├── 获取 latest_price
  │
  └──→ Aggregator
        │
        ├── 根据 price 查找 tier → threshold
        ├── calc_decay_weight(max_runup, threshold)
        ├── calc_effective_weighted_sum(signals, max_runup, threshold)
        │
        └── SignalStats:
              max_runup: float      # 替代 amplitude
              decay_weight: float   # 替代 turbulent: bool
              (turbulent: bool 保留用于 UI 展示, = decay_weight < 1.0)
```

### 效果预期

| 价格段 | 当前过滤率 | 预期过滤率 | 改善 |
|--------|-----------|-----------|------|
| $1-$5  | 35-72%    | ~5%       | 大幅改善 |
| $5-$10 | ~20%      | ~5%       | 显著改善 |
| $10-$20| ~9%       | ~5%       | 略微改善 |
| $20+   | ~3%       | ~5%       | 略微变严 |

目标: 各价位过滤率趋于一致（~5%），仅过滤同 tier 内最极端的股票。

---

## 五、方案 A（波动率）为什么不纳入

虽然 amp/own_vol 有最低的 cross-tier CV (0.171)，但存在**不可接受的高波动免疫问题**:
- $1-$10 高波动股票中 78.8% 逃脱过滤
- 这恰好是用户最关注的群体
- 本质矛盾: "用自身特征标准化"等于说"它一直这样所以这是正常的"，但用户的需求是"即使它一直波动，真正暴涨暴跌了我还是要标记"

分层 P95 方案（B 预计算版）达到类似的"分层适配"效果，且不存在免疫问题。

---

## 六、实施路线图

### Phase 1: Layer 1 (max_runup 替换)
- 改动: `composite.py` 中 `calculate_amplitude` → `calculate_max_runup`
- 风险: 极低，API 兼容，可先用现有阈值 0.8
- 验证: 对比替换前后的标记结果差异

### Phase 2: Layer 2 (分层阈值)
- 前置: 编写预计算脚本，跑全量数据得到各 tier P95
- 改动: 配置文件新增 tier 阈值；`composite.py` 新增查找逻辑
- 验证: 检查各价位过滤率是否趋于均匀

### Phase 3: Layer 3 (渐进降权)
- 改动: `composite.py` 和 `aggregator.py`，将 `turbulent: bool` 扩展为 `decay_weight: float`
- 验证: 检查边界案例的排序行为

### 可选 Phase 4: 定期更新阈值
- 每季度重新跑预计算脚本更新 tier 阈值
- 或引入自动化 CI 任务

---

## 七、参数清单

| 参数 | 来源 | 值 | 可调 |
|------|------|-----|------|
| lookback_days | 已有 | 42 | 是 |
| tier 边界 | 领域知识 | $5, $20 | 是 |
| tier 阈值 | **数据驱动** (P95) | 待计算 | 自动 |
| decay start_ratio | 设计决策 | 0.6 | 是 |
| decay end_ratio | 设计决策 | 1.5 | 是 |

**人为设定参数**: 4 个 (tier 边界 2 个 + decay 比例 2 个)
**数据驱动参数**: tier 阈值 (3 个，自动计算)

对比当前: 1 个人为参数 (AMPLITUDE_THRESHOLD=0.8)
新增净成本: +3 个人为参数，但换来各价位的公平对待。

---

## 八、风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| tier 边界选择不当 | 中 | 基于 SEC 定义和机构实践，有客观依据 |
| P95 阈值随市场环境变化 | 低 | 每季度更新；牛熊市差异不影响 tier 内相对排序 |
| max_runup 遗漏暴跌型超涨 | 低 | 暴跌本身不产生买入信号（D 信号免疫），实际影响小 |
| 渐进降权导致排序不直觉 | 低 | UI 显示 decay_weight 百分比，用户可直观理解 |

---

*报告生成: 2026-02-07 | 基于 4 Tommy agents 并行分析整合*
