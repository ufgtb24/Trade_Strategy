# 联合信号判断系统 v2 (Composite Signal Judgment)

> 状态：设计中 (Planning) | 创建日期：2026-02-05
> 前序版本：[v1 PLAN](16_联合信号判断系统_PLAN.md)

## 一、概述

### 1.1 v1 的局限性

v1 设计了一个基于四维基础分 + 组合模式加分的评分体系，但存在以下问题：

1. **信号等权计数**：B(pk_num=1) 和 B(pk_num=3) 被同等对待，丢失了信号自身强度信息
2. **缺少超涨过滤**：超涨股产生大量 B/V/Y 信号，信号多 ≠ 适合买入
3. **顺序语义被拆分为加分项**：v1 的 Synergy Bonus 只能加分（正值），无法表达 BD（突破后双底=突破失败）这类负面模式
4. **与 PRD 理念的冲突**：引入了评分权重系统，偏离了"简单信号计数 > 多维评分"的初衷

### 1.2 v2 核心改进

基于用户对实际交易的新观察，v2 做出以下关键调整：

| 观察 | v1 处理方式 | v2 改进 |
|------|-----------|---------|
| 超涨后信号变多但不适合买入 | 未处理 | 超涨过滤：B/V/Y 不计入，D 免疫 |
| BD 和 DB 代表不同市场情绪 | Synergy Bonus（只加分） | 序列语义维度（可正可负） |
| B 的 pk_num 代表突破力度 | 等权计数（=1） | 加权计数：B(3) 贡献度=3 |
| D 的 tr_num 代表底部可靠性 | 等权计数（=1） | 加权计数：D(2) 贡献度=2 |

### 1.3 设计原则

- **简洁可解释**：每个维度对应明确的市场机制
- **加法模型**：各维度独立可追溯，避免黑箱
- **渐进复杂度**：先实现核心（加权计数+超涨过滤），再逐步扩展
- **参数可控**：核心参数 ≤ 19 个
- **向后兼容**：`composite.enabled = false` 时行为与当前系统完全一致

---

## 二、三层流水线架构

```
┌─────────────────────────────────────────────────────────┐
│ Layer 0: Signal Detection（现有系统，不修改）               │
│   B/V/Y/D 四个检测器并行检测 → List[AbsoluteSignal]      │
│   (含 details: pk_num, tr_num, volume_ratio, sigma)      │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Signal Enhancement（新增：信号增强层）            │
│                                                          │
│  Stage 1.1: 超涨检测 (Overextended Detection)            │
│    对每个 B/V/Y 信号，检查发生日的累计涨幅               │
│    超涨 → 标记 overextended=true，不计入有效计数          │
│    D 信号免疫（双底意味着已回落）                          │
│                                                          │
│  Stage 1.2: 强度计算 (Intensity Calculation)             │
│    根据 pk_num/tr_num/volume_ratio/sigma 计算权重         │
│    写入 signal.strength                                   │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Multi-Dimensional Scoring（新增：多维评分层）     │
│                                                          │
│  5 个独立维度评分：                                       │
│  [Strength] [Diversity] [Cluster] [Recency] [Sequence]   │
│       ↓          ↓          ↓         ↓          ↓       │
│                  加权求和 → CompositeScore                │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Grading（新增：分级输出层）                       │
│  CompositeScore.total → A/B/C/D 分级                     │
│  附带可解释的分级理由                                     │
└─────────────────────────────────────────────────────────┘
```

**为什么需要"信号增强层"？**

超涨检测需要访问价格数据（df），而聚合器只接收信号列表。因此增强逻辑在 `scan_single_stock()` 中执行（此处有 df_slice），让信号在进入聚合器之前就携带完整的强度和超涨标记信息。

---

## 三、Layer 1：信号增强

### 3.1 超涨检测 (Overextended Detection)

#### 核心问题

用户观察：当股票从底部暴涨后，会密集产生 B（连续突破多个阻力位）、V（频繁放量）、Y（连续大阳线）信号。这些信号的物理形态"合格"，但买入价值极低——**信号语义因价格环境而变质**。

#### 超涨定义

```
rally_ratio = (signal_close - window_low) / window_low

其中：
  signal_close = 信号发生日的收盘价
  window_low   = 信号发生日前 rally_lookback 个交易日内的最低收盘价

超涨判定：rally_ratio >= rally_threshold
```

**为什么用原始累计涨幅而非波动率标准化？**

超涨是一个**绝对风险概念**。不管股票波动率多高，从底部涨了 60% 后再追入的风险都是实实在在的。波动率标准化反而会让高波动股"逃过"超涨判定。

#### 各信号类型的处理规则

| 信号 | 超涨期间处理 | 理由 |
|------|-------------|------|
| **B** | 标记 `overextended=true`，不计入有效计数 | 突破的买入价值在超涨后消失 |
| **V** | 标记 `overextended=true`，不计入有效计数 | 可能是出货信号而非入场信号 |
| **Y** | 标记 `overextended=true`，不计入有效计数 | 趋势末端的亢奋信号 |
| **D** | **免疫**，不检测超涨 | D 信号要求 TR1 为 126 日最低点，本身意味着已深度回调 |

**为什么是二值过滤（计入/不计入）而非衰减系数？**

PRD 核心理念："简单信号计数 > 多维评分"、"评分系统依赖人为权重，容易过拟合"。信号要么有效要么无效，**不存在"0.3个信号"**。二值判断与"绝对信号"的精神一致。被标记的信号仍然保留在信号列表中（UI 可展示），只是不计入有效计数。

#### 参数设计

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `rally_threshold` | 0.6 (60%) | 超涨阈值 |
| `rally_lookback` | 42 | 回看天数（复用 aggregator.lookback_days） |

**rally_threshold = 0.6 的选择理由**：
- 42 个交易日（约 2 个月）涨 60%，年化约 520%
- 正常强势突破（10-30% 涨幅）不会触发
- 只有真正的暴涨（多日连续涨停、单日翻倍后继续拉升等）才会达到

#### 边界情况

| 场景 | 处理 |
|------|------|
| **Gap Up 后盘整** | 盘整超过 lookback 天数后，window_low 更新为盘整区底部，不受影响 |
| **底部反弹 60%** | 虽是正常反转，但 42 天涨 60% 的追入风险仍高；等 D 信号触发更安全 |
| **慢牛行情** | 日均 0.5%，42 天约 23%，远低于 60% 阈值 |

### 3.2 强度加权 (Intensity Weighting)

#### 核心思想

v1 中所有信号等权（strength=1.0）。v2 让信号的内在属性反映其实际强度：

- **B(pk_num=3)**：一次穿越 3 个历史阻力位，每个被穿越的阻力位从"阻力"翻转为"支撑"，效应可叠加
- **D(tr_num=2)**：底部被 2 次支撑测试确认，可靠性线性增加
- **V(volume_ratio=9.0)**：3 倍基准量，放量程度更极端
- **Y(sigma=5.0)**：波动率的 2 倍基准，涨幅更激进

#### 加权公式

```python
def calculate_signal_weight(signal: AbsoluteSignal) -> float:
    """
    计算单个信号的加权贡献度。

    基准贡献度 = 1.0（与原始等权计数兼容）。
    强度指标将贡献度提升至 [1.0, cap] 的范围。
    """
    d = signal.details

    if signal.signal_type == SignalType.BREAKOUT:
        return min(d.get("pk_num", 1), cap_B)              # [1, 5]

    elif signal.signal_type == SignalType.DOUBLE_TROUGH:
        return min(d.get("tr_num", 1), cap_D)              # [1, 4]

    elif signal.signal_type == SignalType.HIGH_VOLUME:
        return min(d.get("volume_ratio", base_V) / base_V, cap_V)  # [1.0, 3.0]

    elif signal.signal_type == SignalType.BIG_YANG:
        return min(d.get("sigma", base_Y) / base_Y, cap_Y)  # [1.0, 2.5]

    return 1.0
```

#### 权重范围与参数

| 信号 | 强度来源 | 公式 | 范围 | cap | 理由 |
|------|---------|------|------|-----|------|
| B | pk_num | `min(pk_num, 5)` | [1, 5] | 5 | 每层阻力位代表一批历史套牢盘的解套压力，可线性叠加 |
| D | tr_num | `min(tr_num, 4)` | [1, 4] | 4 | 42 天窗口内 tr_num 难超 3-4（每次支撑测试需时间） |
| V | volume_ratio | `min(ratio/3.0, 3.0)` | [1.0, 3.0] | 3.0 | 极端高量（20x+）往往是异常事件，cap 防异常值干扰 |
| Y | sigma | `min(sigma/2.5, 2.5)` | [1.0, 2.5] | 2.5 | 与 V 同理，sigma 过高可能是消息驱动的一次性事件 |

**退化验证**：当 pk_num=1, tr_num=1, volume_ratio=3.0, sigma=2.5 时，所有权重均为 1.0，`weighted_score` = `signal_count`。与现有行为完全兼容。

#### 为什么 B/D 用线性映射、V/Y 用归一化映射？

- pk_num 和 tr_num **本身就是自然计数**（穿越了几个峰值、被确认了几次），直接作为权重语义清晰
- volume_ratio 和 sigma **是连续值且量纲不同**（量比 vs 标准差倍数），需要除以各自的触发阈值（base）进行归一化，使 "刚好触及阈值" = 权重 1.0

### 3.3 数据模型变更

`AbsoluteSignal.details` 新增字段：

```python
details = {
    ...  # 原有字段不变
    "overextended": False,     # bool: 是否处于超涨状态
    "rally_ratio": 0.0,        # float: 窗口内累计涨幅（仅 B/V/Y）
}
```

`AbsoluteSignal.strength` 字段：从默认的 1.0 更新为加权值（复用现有字段，无需修改模型定义）。

### 3.4 增强流程伪代码

```python
# 在 scan_single_stock() 中，支撑分析之后、过滤之前执行
def enhance_signals(df_slice, signals, config):
    """信号增强：超涨标记 + 强度加权"""
    overext_cfg = config.get("overextended_filter", {})
    weight_cfg = config.get("weighting", {})

    for signal in signals:
        # Step 1: 超涨检测（D 信号免疫）
        if signal.signal_type != SignalType.DOUBLE_TROUGH:
            is_overext, ratio = detect_overextended(
                df_slice, signal.date,
                overext_cfg.get("rally_threshold", 0.6),
                overext_cfg.get("rally_lookback", 42),
            )
            signal.details["overextended"] = is_overext
            signal.details["rally_ratio"] = round(ratio, 3)
        else:
            signal.details["overextended"] = False
            signal.details["rally_ratio"] = 0.0

        # Step 2: 强度加权
        signal.strength = calculate_signal_weight(signal, weight_cfg)
```

---

## 四、Layer 2：多维评分

### 4.1 总体公式

```
Composite Score = w1*Strength + w2*Diversity + w3*Cluster + w4*Recency + w5*Sequence

各维度取值范围: [0, 100]（Sequence 可为负值，范围 [-20, 100]）
```

### 4.2 维度 1：加权信号强度 (Weighted Strength Score)

**替代 v1 的 Count Score**。核心改进：信号不再等权，且排除超涨信号。

```
effective_signals = [s for s in signals if not s.details.get("overextended", False)]
weighted_sum = sum(s.strength for s in effective_signals)
Strength Score = min(weighted_sum / strength_cap, 1.0) × 100

参数: strength_cap = 6.0
```

**为什么 cap = 6.0？** 一个理想的强信号组合：B(pk_num=2) + D(tr_num=2) + V + Y = 2+2+1+1 = 6。达到此水平即满分。

### 4.3 维度 2：信号多样性 (Diversity Score)

```
unique_types = 有效信号（非超涨）中不重复的信号类型数
Diversity Score = (unique_types / 4) × 100
```

市场逻辑：4 种信号捕捉 4 个独立维度（价格结构/资金流动/市场情绪/底部形态），多维共振 = 多个独立因素指向同一方向。

### 4.4 维度 3：信号聚集度 (Cluster Score)

```
Cluster Score = (1 - avg_gap / max_gap) × 100，clamp to [0, 100]

avg_gap = 有效信号间的平均间隔（交易日）
max_gap = lookback_days / 2 = 21

特殊情况：仅 1 个有效信号时，Cluster Score = 0
```

市场逻辑：信号聚集意味着多个事件短时间内密集发生，对应主力资金集中建仓或催化剂密集释放。

### 4.5 维度 4：信号时效性 (Recency Score)

```
Recency Score = weighted_mean_decay × 100

weighted_mean_decay = sum(ew(s) × decay(s)) / sum(ew(s))

  ew(s)    = s.strength（信号的有效权重）
  decay(s) = exp(-λ × age(s))
  age(s)   = scan_date - signal_date（交易日）
  λ        = 0.07（半衰期约 10 个交易日）
```

**v2 改进**：用加权均值替代 v1 的简单均值——更强的信号（pk_num=3）如果更近期出现，Recency Score 提升更显著。

| 信号年龄 | 衰减权重 |
|---------|---------|
| 0 天（当天） | 1.00 |
| 7 天 | 0.61 |
| 14 天 | 0.37 |
| 21 天 | 0.23 |
| 42 天 | 0.05 |

### 4.6 维度 5：序列语义 (Sequence Score) — 新增

**替代 v1 的 Synergy Bonus**，成为独立维度，可正可负。

#### 序列模式定义

| 模式 | 含义 | 基础分 | 最大间隔 |
|------|------|-------|---------|
| **D → B** | 双底后突破（底部反转确认） | +25 | 30 天 |
| **D → V** | 双底后放量（资金确认底部） | +15 | 21 天 |
| **D → Y** | 双底后大阳（情绪确认底部） | +12 | 21 天 |
| **B → V** | 突破放量（量价配合） | +15 | 5 天 |
| **V → B** | 放量后突破（资金先行） | +12 | 5 天 |
| **B → D** | 突破后双底（突破失败回落） | **-10** | 42 天 |

#### 间隔衰减

```
pattern_score = base_score × (1 - gap_days / max_gap × 0.5)

示例：D → B 间隔 10 天
score = 25 × (1 - 10/30 × 0.5) = 25 × 0.833 = 20.8
```

#### 多信号共振加分

```
条件：7 个交易日内出现 ≥ 3 种信号类型
加分：+20
```

#### Sequence Score 计算

```
raw_sequence = sum(pattern_scores) + resonance_bonus
Sequence Score = clamp(raw_sequence, -20, 100)
```

**为什么 BD 是负分？** v1 的 Synergy Bonus 只能加分，无法表达"突破后才双底 = 突破可能失败"。BD 意味着价格先突破后又回落形成双底，暗示突破缺乏后续支撑。虽然 D 最终确认了新支撑，但整体模式的可靠性低于 DB。

### 4.7 权重配置

```yaml
weights:
  strength: 0.30    # 加权信号强度（最核心）
  diversity: 0.20   # 信号多样性
  cluster: 0.15     # 信号聚集度
  recency: 0.20     # 信号时效性
  sequence: 0.15    # 序列语义
```

**权重选择逻辑**：
- Strength 最高（0.30）：信号强度是最直接的买入依据
- Diversity 和 Recency 次之（0.20）：多样性保证多角度确认，时效性保证相关性
- Cluster 和 Sequence 较低（0.15）：辅助判断维度，不应主导排序

---

## 五、Layer 3：分级输出

### 5.1 分级定义

| 等级 | 分数范围 | 含义 | 典型特征 | 行动建议 |
|------|---------|------|---------|---------|
| **A** (Strong Buy) | ≥ 70 | 强信号 | 多种强信号近期密集出现，序列逻辑一致 | 优先关注，考虑入池 |
| **B** (Buy) | 55-69 | 信号充足 | 多个信号但强度/时效/逻辑不完美 | 值得分析，条件入池 |
| **C** (Watch) | 40-54 | 观望 | 信号较少或较弱或较远 | 加入观察，等待更多信号 |
| **D** (Weak) | < 40 | 弱信号 | 信号稀疏、过期或逻辑矛盾 | 暂不关注 |

### 5.2 分级解释输出

每个股票附带可解释的评分分解：

```
AAPL | Grade A (72.1) | Seq: D -> B(3) -> V
  Strength:  30.0/30  [weighted sum=7.2, 3 effective / 5 total]
  Diversity: 15.0/20  [3 types: B,V,D]
  Cluster:    7.4/15  [avg gap=10.7d]
  Recency:    9.6/20  [weighted avg decay=0.48]
  Sequence:  10.1/15  [D→B(+20.8)]
  Overextended: 2 signals filtered (B, Y)
```

### 5.3 与 Simple Pool 的协同

```
Layer 1 (信号扫描 + 联合评分)
  问题: "这只股票是否值得关注？"
  输出: Grade A/B/C/D

Layer 2 (Simple Pool 即时判断)
  问题: "现在是否是买入时机？"
  输入: Grade >= C 的股票

入池建议:
  Grade A → 自动推荐入池
  Grade B → 推荐入池
  Grade C → 手动入池
  Grade D → 不建议入池
```

---

## 六、顺序标签 (Sequence Label)

### 6.1 设计理由

加权计数解决**排序**问题（定量），顺序标签解决**理解**问题（定性）。两者分离，互不干扰。

### 6.2 标签生成

信号按日期升序排列，强度指标附加在类型代码后：

```python
def generate_sequence_label(signals: List[AbsoluteSignal]) -> str:
    sorted_signals = sorted(signals, key=lambda s: s.date)
    parts = []
    for s in sorted_signals:
        if s.signal_type == SignalType.BREAKOUT:
            pk = s.details.get("pk_num", 1)
            label = f"B({pk})" if pk > 1 else "B"
        elif s.signal_type == SignalType.DOUBLE_TROUGH:
            tr = s.details.get("tr_num", 1)
            label = f"D({tr})" if tr > 1 else "D"
        else:
            label = s.signal_type.value  # "V" or "Y"

        # 超涨信号用方括号标记
        if s.details.get("overextended", False):
            label = f"[{label}]"

        parts.append(label)
    return " → ".join(parts)
```

### 6.3 示例输出

| 标签 | 含义 |
|------|------|
| `D → B(3) → V` | 双底后三重突破，伴随放量（教科书级） |
| `B(2) → D(2)` | 双重突破后回踩，底部二次确认 |
| `V → Y → B` | 放量大阳后突破（量价情绪三重确认） |
| `D → [B] → [V]` | 双底后突破和放量，但处于超涨状态（B/V 不计入） |
| `D(2) → B(3)` | 双底二次确认后三重突破（weighted_score = 2+3 = 5） |

---

## 七、信号组合语义参考

### 7.1 关键组合分析

| 组合 | 市场叙事 | 可靠性 | 说明 |
|------|---------|--------|------|
| **DB** | 底部确认 → 突破 | ★★★★★ | 经典底部反转+趋势启动。D 提供下行保护，B 确认上行方向 |
| **BD** | 突破 → 回踩确认 | ★★★★☆ | 突破后回踩原阻力位（现为支撑），D 确认支撑翻转 |
| **BV** | 放量突破 | ★★★★☆ | 量价齐升，突破有资金支撑。B+V 间隔 ≤3 天视为同步 |
| **VB** | 量在价先 | ★★★☆☆ | 资金先行介入后突破。需结合 V 当天价格方向判断 |
| **VDB** | 底部放量+双底+突破 | ★★★★★ | 完整的底部构建→趋势启动叙事 |
| **BVD** | 放量突破+回踩 | ★★★★☆ | B+V 放量突破后 D 回踩确认支撑 |
| **DBVY** | 全信号覆盖 | ★★★★★+ | 极罕见，四重共振 |

### 7.2 V 信号的特殊位置性

V 可能出现在 B 的附近任何位置（前/后/同日），只要不是超涨状态，都是正面信号：
- V 在 B 前：资金先行介入
- V 与 B 同步：量价齐升
- V 在 B 后：突破确认放量

---

## 八、评分计算示例

### 场景 1：强信号股票（无超涨）

**42 天窗口内的信号：**

| 日期 | 信号 | 距 scan_date | 强度指标 | strength |
|------|------|-------------|---------|----------|
| D-35 | D | 35 天 | tr_num=2 | 2.0 |
| D-15 | V | 15 天 | volume_ratio=5.0 | 1.67 |
| D-5  | B | 5 天  | pk_num=2 | 2.0 |
| D-3  | Y | 3 天  | sigma=3.5 | 1.40 |

**计算过程：**

```
1. Strength: weighted_sum = 2.0+1.67+2.0+1.40 = 7.07
   score = min(7.07/6, 1.0) × 100 = 100.0

2. Diversity: 4/4 × 100 = 100.0

3. Cluster: gaps=[20, 10, 2], avg=10.67
   score = (1 - 10.67/21) × 100 = 49.2

4. Recency: (加权均值)
   D: 2.0 × exp(-0.07×35) = 2.0 × 0.085 = 0.17
   V: 1.67 × exp(-0.07×15) = 1.67 × 0.35 = 0.58
   B: 2.0 × exp(-0.07×5) = 2.0 × 0.70 = 1.40
   Y: 1.40 × exp(-0.07×3) = 1.40 × 0.81 = 1.13
   weighted_mean = (0.17+0.58+1.40+1.13) / (2.0+1.67+2.0+1.40) = 3.28/7.07 = 0.464
   score = 46.4

5. Sequence:
   D→B: gap=30, score = 25 × (1 - 30/30 × 0.5) = 12.5
   D→V: gap=20, score = 15 × (1 - 20/21 × 0.5) = 7.9
   多信号共振: D-5~D-2 有 B,Y (2种 < 3), 不满足
   score = 20.4

6. Total = 0.30×100 + 0.20×100 + 0.15×49.2 + 0.20×46.4 + 0.15×20.4
         = 30.0 + 20.0 + 7.4 + 9.3 + 3.1
         = 69.8 → Grade B

Sequence Label: D(2) → V → B(2) → Y
```

### 场景 2：超涨股票

**42 天窗口内的信号：**

| 日期 | 信号 | 距 scan_date | 强度指标 | rally_ratio | overextended |
|------|------|-------------|---------|-------------|-------------|
| D-30 | V | 30 天 | ratio=4.0 | 0.10 | false |
| D-20 | B | 20 天 | pk_num=2 | 0.25 | false |
| D-10 | Y | 10 天 | sigma=4.0 | 0.50 | false |
| D-5  | B | 5 天  | pk_num=3 | 0.75 | **true** |
| D-3  | V | 3 天  | ratio=8.0 | 0.80 | **true** |

**有效信号**：V(D-30) + B(D-20) + Y(D-10) = 3 个

**计算过程：**

```
1. Strength: weighted_sum = 1.33+2.0+1.60 = 4.93  (排除了超涨的 B+V)
   score = min(4.93/6, 1.0) × 100 = 82.2

2. Diversity: 3/4 × 100 = 75.0

3. Cluster: gaps=[10, 10], avg=10
   score = (1 - 10/21) × 100 = 52.4

4. Recency:
   V: 1.33 × exp(-0.07×30) = 1.33 × 0.12 = 0.16
   B: 2.0 × exp(-0.07×20) = 2.0 × 0.25 = 0.50
   Y: 1.60 × exp(-0.07×10) = 1.60 × 0.50 = 0.80
   weighted_mean = 1.46/4.93 = 0.296
   score = 29.6

5. Sequence:
   V→B: gap=10, max_gap=5, 超出 → 不匹配
   score = 0

6. Total = 0.30×82.2 + 0.20×75.0 + 0.15×52.4 + 0.20×29.6 + 0.15×0
         = 24.7 + 15.0 + 7.9 + 5.9 + 0
         = 53.5 → Grade C

Sequence Label: V → B(2) → Y → [B(3)] → [V]
```

对比：如果不做超涨过滤，5 个信号全部计入，weighted_sum = 1.33+2.0+1.60+3.0+2.67 = 10.6，排名会远高于实际合理值。

---

## 九、数据模型

### 9.1 CompositeScore（新增）

```python
@dataclass
class CompositeScore:
    """联合评分结果"""
    total: float                    # 加权总分

    # 各维度原始分
    strength_score: float           # [0, 100]
    diversity_score: float          # [0, 100]
    cluster_score: float            # [0, 100]
    recency_score: float            # [0, 100]
    sequence_score: float           # [-20, 100]

    # 各维度加权后贡献
    strength_contrib: float
    diversity_contrib: float
    cluster_contrib: float
    recency_contrib: float
    sequence_contrib: float

    # 详细信息
    detected_patterns: List[str]    # e.g., ["D→B(+20.8)", "D→V(+7.9)"]
    sequence_label: str             # e.g., "D(2) → B(3) → V"
    weighted_signal_sum: float      # 加权信号强度总和
    effective_signal_count: int     # 有效信号数（非超涨）
    total_signal_count: int         # 总信号数（含超涨）
    overextended_count: int         # 超涨信号数
```

### 9.2 SignalStats 扩展

```python
@dataclass
class SignalStats:
    symbol: str
    signal_count: int               # 保持不变（向后兼容）
    signals: List[AbsoluteSignal]
    latest_signal_date: date
    latest_price: float

    # === v2 新增 ===
    composite_score: Optional[CompositeScore] = None
    grade: Optional[str] = None     # "A" / "B" / "C" / "D"
```

---

## 十、模块结构

```
BreakoutStrategy/signals/
├── composite/                      # 新增：联合评分子包
│   ├── __init__.py                 # 模块导出
│   ├── enhancer.py                 # SignalEnhancer（Layer 1：超涨检测 + 强度加权）
│   ├── scorer.py                   # CompositeScorer（Layer 2 + 3：五维评分 + 分级）
│   └── sequence.py                 # SequenceAnalyzer（序列语义分析）
├── models.py                       # 修改：新增 CompositeScore，扩展 SignalStats
├── aggregator.py                   # 修改：集成 CompositeScorer
├── scanner.py                      # 修改：集成 SignalEnhancer
├── factory.py                      # 修改：新增 create_enhancer / create_scorer
└── ... (其他文件不变)
```

### 10.1 各模块职责

| 模块 | 类 | 职责 |
|------|-----|------|
| `enhancer.py` | `SignalEnhancer` | 超涨检测 + 强度计算 → 更新 signal.strength 和 details |
| `scorer.py` | `CompositeScorer` | 5 维评分 + 加权求和 + 分级判断 |
| `sequence.py` | `SequenceAnalyzer` | 序列模式检测 + 共振检测 + 标签生成 |

### 10.2 调用关系

```
scanner.py :: scan_single_stock()
    ↓ 检测后调用
    SignalEnhancer.enhance(df_slice, signals)   # 原地更新 signal.strength + details

aggregator.py :: SignalAggregator.aggregate()
    ↓ 分组后调用
    CompositeScorer.score(signals, scan_date)   # 返回 CompositeScore
        ↓ 内部调用
        SequenceAnalyzer.analyze(signals)       # 返回 (score, patterns, label)
```

---

## 十一、配置规范

### 11.1 配置文件路径

`configs/signals/composite_scoring.yaml`

### 11.2 完整配置

```yaml
# ============================================================
# 联合信号评分配置 (v2)
# ============================================================

# 总开关
enabled: true

# === Layer 1: 信号增强 ===

# 超涨过滤
overextended_filter:
  enabled: true
  rally_threshold: 0.6          # 超涨阈值（60%）
  rally_lookback: 42            # 回看天数（建议与 aggregator.lookback_days 一致）

# 信号强度加权
weighting:
  breakout_cap: 5               # B 信号 pk_num 权重上限
  trough_cap: 4                 # D 信号 tr_num 权重上限
  volume_base: 3.0              # V 信号 volume_ratio 基准值
  volume_cap: 3.0               # V 信号权重上限
  yang_base: 2.5                # Y 信号 sigma 基准值
  yang_cap: 2.5                 # Y 信号权重上限

# === Layer 2: 评分维度 ===

# 维度权重
weights:
  strength: 0.30
  diversity: 0.20
  cluster: 0.15
  recency: 0.20
  sequence: 0.15

# 维度参数
scoring:
  strength_cap: 6.0             # 信号强度封顶值
  cluster_max_gap: 21           # 聚集度最大间隔（交易日）
  time_decay_lambda: 0.07       # 时间衰减系数（半衰期 ~10 天）

  # 序列分析
  sequence:
    resonance_window: 7         # 共振检测窗口（交易日）
    resonance_min_types: 3      # 共振最少信号类型数
    resonance_bonus: 20         # 共振加分
    patterns:                   # 序列模式定义
      D_B: { score: 25, max_gap: 30 }
      D_V: { score: 15, max_gap: 21 }
      D_Y: { score: 12, max_gap: 21 }
      B_V: { score: 15, max_gap: 5  }
      V_B: { score: 12, max_gap: 5  }
      B_D: { score: -10, max_gap: 42 }

# === Layer 3: 分级阈值 ===
thresholds:
  A: 70                         # Strong Buy
  B: 55                         # Buy
  C: 40                         # Watch
  # < 40 = D (Weak)
```

### 11.3 参数总览

| # | 参数 | 默认值 | 层 | 说明 |
|---|------|--------|---|------|
| 1 | overextended.rally_threshold | 0.6 | L1 | 超涨阈值 |
| 2 | overextended.rally_lookback | 42 | L1 | 超涨回看天数 |
| 3 | weighting.breakout_cap | 5 | L1 | B 权重上限 |
| 4 | weighting.trough_cap | 4 | L1 | D 权重上限 |
| 5 | weighting.volume_base | 3.0 | L1 | V 基准量比 |
| 6 | weighting.volume_cap | 3.0 | L1 | V 权重上限 |
| 7 | weighting.yang_base | 2.5 | L1 | Y 基准 sigma |
| 8 | weighting.yang_cap | 2.5 | L1 | Y 权重上限 |
| 9 | weights.strength | 0.30 | L2 | 强度权重 |
| 10 | weights.diversity | 0.20 | L2 | 多样性权重 |
| 11 | weights.cluster | 0.15 | L2 | 聚集度权重 |
| 12 | weights.recency | 0.20 | L2 | 时效性权重 |
| 13 | weights.sequence | 0.15 | L2 | 序列权重 |
| 14 | scoring.strength_cap | 6.0 | L2 | 强度封顶 |
| 15 | scoring.cluster_max_gap | 21 | L2 | 聚集度参数 |
| 16 | scoring.time_decay_lambda | 0.07 | L2 | 衰减系数 |
| 17 | thresholds.A | 70 | L3 | A 级阈值 |
| 18 | thresholds.B | 55 | L3 | B 级阈值 |
| 19 | thresholds.C | 40 | L3 | C 级阈值 |

**总计 19 个参数**。序列模式定义 (patterns) 不计入参数预算——它们是语义定义而非可调参数。

---

## 十二、与现有系统的集成

### 12.1 修改范围

| 文件 | 修改类型 | 变更内容 |
|------|---------|---------|
| `models.py` | 扩展 | 新增 `CompositeScore` 类；`SignalStats` 增加 2 个 Optional 字段 |
| `scanner.py` | 小改（3-5 行） | `scan_single_stock()` 中增加增强器调用 |
| `aggregator.py` | 小改（5-8 行） | `aggregate()` 中增加评分和分级调用，排序逻辑变更 |
| `factory.py` | 扩展 | 新增 `create_enhancer()` 和 `create_scorer()` |
| `__init__.py` | 扩展 | 导出新增类型 |

**不修改的文件**：所有检测器 (detectors/)、support_analyzer.py、trough.py。

### 12.2 向后兼容

- `composite.enabled = false` 或配置缺失时，系统行为与当前完全一致
- `SignalStats.composite_score` 和 `grade` 均为 Optional，默认 None
- 有 composite_score 时按分数排序，无时按原始 signal_count 排序

### 12.3 集成点

**scanner.py**:

```python
def scan_single_stock(symbol, df, config, scan_date, skip_validation):
    # ... 现有: 检测信号 ...
    # ... 现有: 支撑分析 ...

    # === v2 新增: 信号增强 ===
    composite_config = config.get("composite", {})
    if composite_config.get("enabled", False):
        enhancer = _create_enhancer(composite_config)
        enhancer.enhance(df_slice, all_signals)

    # ... 现有: 过滤信号 ...
    return all_signals, filtered_signals, metadata
```

**aggregator.py**:

```python
class SignalAggregator:
    def __init__(self, lookback_days=42, composite_config=None):
        self.lookback_days = lookback_days
        self.scorer = CompositeScorer(composite_config) if composite_config else None

    def aggregate(self, all_signals, scan_date):
        # ... 现有: 分组统计 ...

        # === v2 新增: 评分和分级 ===
        if self.scorer:
            for stats in stats_list:
                stats.composite_score = self.scorer.score(stats.signals, scan_date)
                stats.grade = self.scorer.grade(stats.composite_score.total)

        # 排序
        if self.scorer:
            stats_list.sort(key=lambda s: s.composite_score.total, reverse=True)
        else:
            stats_list.sort(key=lambda s: s.signal_count, reverse=True)

        return stats_list
```

---

## 十三、实现路线图

### Phase 1：信号增强 (MVP)

- [ ] 实现 `composite/enhancer.py`
  - `calculate_signal_weight()` — 强度加权（pk_num, tr_num, volume_ratio, sigma）
  - `detect_overextended()` — 超涨检测
  - `enhance()` — 原地更新 signal.strength 和 details
- [ ] 在 `scanner.py` 中集成增强器
- [ ] 扩展 `models.py`（CompositeScore）
- [ ] 扩展 `factory.py`（create_enhancer）
- [ ] 单元测试：验证 B(pk_num=3).strength == 3.0

### Phase 2：核心评分（4 维度）

- [ ] 实现 `composite/scorer.py` — Strength/Diversity/Cluster/Recency
- [ ] 实现分级判断
- [ ] 在 `aggregator.py` 中集成评分器
- [ ] YAML 配置文件
- [ ] 单元测试 + 集成测试

### Phase 3：序列分析

- [ ] 实现 `composite/sequence.py`
  - 模式检测 (D→B, B→V 等)
  - 多信号共振检测
  - 顺序标签生成
- [ ] 集成到 `scorer.py`
- [ ] 单元测试：构造 DB 和 BD 序列，验证分数差异

### Phase 4：UI 集成 + 验证

- [ ] 股票列表增加 Grade / Score / Sequence Label 列
- [ ] K 线图表中超涨信号用半透明/灰色区分显示
- [ ] Composite Score 详情面板
- [ ] 回测验证：对比 v1 (count only) 和 v2 (composite) 的选股效果
- [ ] 参数微调

---

## 十四、设计决策记录

### D1: 超涨用二值过滤 vs 衰减系数

**决策**：二值过滤（计入/不计入）

**理由**：系统 PRD 明确写道"评分系统依赖人为权重，容易过拟合"、"简单信号计数更直观"。衰减系数本质上是把信号计数变成加权评分系统，"0.3 个信号"没有物理含义。信号要么有效要么无效，这与"绝对信号"的精神一致。

### D2: pk_num/tr_num 直接做乘数 vs 加分

**决策**：直接做乘数（`strength = pk_num`）

**理由**：pk_num=3 意味着突破了 3 层阻力位，市场力量本质上就是 3 倍量级。每层阻力位代表一批历史套牢盘的解套压力，突破 3 层就是消化了 3 层卖压，效应可线性叠加。

### D3: Sequence 作为独立维度 vs Synergy Bonus

**决策**：独立维度

**理由**：v1 的 Synergy Bonus 只能加分（正值），无法表达 BD（突破后双底）应该减分的语义。作为独立维度，Sequence Score 可正可负，更准确地反映信号序列的市场含义。

### D4: Recency 使用加权均值 vs 简单均值

**决策**：加权均值（按 signal.strength 加权）

**理由**：如果 B(pk_num=3) 在近期出现，它对时效性的贡献应更大。简单均值会被弱信号的旧衰减值拉低，掩盖近期强信号的重要性。

### D5: 信号类型本身不赋不同基础权重

**决策**：`base_weight(B) = base_weight(V) = base_weight(Y) = base_weight(D) = 1.0`

**理由**：PRD 核心哲学"不依赖人为参数"。不同类型捕捉不同维度（价格/资金/情绪/形态），没有理由认为哪个维度固定更重要。信号强弱由内在属性（pk_num, sigma 等）决定。

### D6: D 信号免疫超涨过滤

**决策**：D 信号始终保留，不检测超涨

**理由**：D 信号要求 TR1 为 126 日最低点，信号本身就意味着价格已从高位深度回调。D 信号的存在是"超涨已结束"的证据。

---

**文档版本**：v2.0
**作者**：Claude (多代理协作 — Tommy × 3)
**审核状态**：待审核
