# 信号系统-评分系统-模式分类 三系统融合架构设计报告

**日期**: 2026-02-10
**分析师**: architect (Tom)

---

## Executive Summary

当前项目存在两个独立演化的分析体系：**评分系统**（`simple-pool` 分支，Bonus 乘法模型，11 个乘数因子）和**信号系统**（`combined` 分支，4 类绝对信号 B/V/Y/D + freshness 衰减）。经深入分析代码结构、语义重叠和项目状态后，核心结论如下：

**推荐方案：部分融合 — 信号系统作为评分系统的"时间维度扩展层"**

- 不做全融合（两套系统合并成一套），也不保持完全独立
- 评分系统保持为"突破质量评估"的核心引擎，负责突破当日的多维度打分
- 信号系统作为"时间维度分析层"，负责突破前后的事件追踪和鲜度计算
- 模式分类作为评分系统的后处理标签，约 50 行代码
- Simple Pool 作为下游消费者，通过统一的 `EnrichedBreakout` 接口接入

**分支策略推荐：基于 combined，合并 simple-pool**

- 经实测，`git merge` 无冲突
- combined 拥有完整的信号系统 + 测试用例 + P0/P1 已实现的改进
- simple-pool 的增量（评分修复 + Simple Pool 模块）可干净合入

---

## 一、融合价值判断

### 1.1 全融合 vs 保持独立 vs 部分融合

| 维度 | 全融合 | 保持独立 | **部分融合（推荐）** |
|------|--------|---------|---------------------|
| 信息完整度 | 最高 | 低（信息割裂） | **高（互补整合）** |
| 实现复杂度 | 极高（重写两系统） | 零 | **低-中（接口层对接）** |
| 维护成本 | 中（一套代码） | 高（两套独立演化） | **中低（解耦但有标准接口）** |
| 与 MVP 理念契合 | 差（大范围重构） | 好（不动现有代码） | **好（增量式接入）** |
| 回测验证难度 | 极高 | 低 | **中（可分层验证）** |

**结论：部分融合。** 理由：

1. **75% 互补**：两套系统仅 25% 语义重叠，大部分维度互补而非冗余。全融合意味着把两个差异很大的系统硬塞成一个，结构上不合理。
2. **职责天然分离**：评分系统回答"这个突破有多好"（静态质量），信号系统回答"这只股票现在有什么事件在发生"（动态叙事）。这是两个不同的问题。
3. **部分融合的信息增益 / 复杂度比最高**：通过一个轻量级桥接层（~100 行），就能将两套系统的信息合流到下游消费者。

### 1.2 融合的信息增益：实例分析

以一个具体突破场景说明三种情况下获得的信息差异：

**场景：ACME 股票，2025-12-15 突破 $50 阻力位**

#### 仅评分系统

```
ScoreBreakdown:
  total_score: 89.7
  bonuses: Age(252d, 1.50x) + Tests(3x, 1.25x) + Volume(2.1x, 1.15x)
           + PBM(0.002, 1.15x) - Overshoot(2.5σ, 1.0x)
  → 知道什么：这是一个高质量的远期阻力突破（历史1年、测试3次、放量）
  → 不知道什么：
    - 突破前有没有双底支撑？
    - 突破后这些信号的"能量"还剩多少？（过了20天还排在前面吗？）
    - 突破前几天有没有其他放量/大阳线事件叠加？
    - 走势是否已经过热（amplitude 层面）？
```

#### 仅信号系统

```
SignalStats:
  weighted_sum: 5.2
  sequence_label: "D(2) → V → B(3) → Y"
  freshness: {B: 0.85, V: 0.72, Y: 0.68, D: 0.95}
  turbulent: False
  → 知道什么：在lookback窗口内出现了4类事件的叠加，双底先于突破出现，
    各信号的鲜度仍然较高，走势不过热
  → 不知道什么：
    - 被突破的阻力位有多"老"（252天 vs 21天的阻力位意义完全不同）
    - 阻力位的相对高度是多少？
    - 突破前的涨势动量（PBM）如何？
    - 峰值处的成交量是否异常放大？
    - 这是连续第几次突破（streak）？
```

#### 部分融合后

```
EnrichedBreakout:
  === 评分层（突破质量） ===
  quality_score: 89.7
  pattern_label: "grind_through"  (B+D 磨穿防线)
  bonuses: [Age 1.50, Tests 1.25, Volume 1.15, PBM 1.15, ...]

  === 信号层（时间维度） ===
  signal_context:
    sequence_label: "D(2) → V → B(3) → Y"
    total_weighted_sum: 5.2
    freshness_weighted_sum: 4.1  (鲜度调整后)
    turbulent: False
    signal_details: [
      {type: D, date: 12-01, strength: 2, freshness: 0.95},
      {type: V, date: 12-10, strength: 1, freshness: 0.72},
      {type: B, date: 12-15, strength: 3, freshness: 0.85},
      {type: Y, date: 12-15, strength: 1, freshness: 0.68},
    ]

  → 完整信息：
    1. 突破质量高（89.7分，远期阻力+密集测试 = 磨穿防线模式）
    2. 突破前有双底支撑（D信号先于B信号出现）
    3. 突破日多事件叠加（B+V+Y 同日）
    4. 信号能量仍充足（freshness均>0.65）
    5. 走势未过热（非turbulent）
    6. 结论：高质量突破 + 多重确认 + 能量充足 → 强候选
```

**信息增益量化**：
- 评分系统独有的 5 个维度（Age、Height、PeakVol、PBM、Gap-Vol）提供了信号系统无法给出的阻力属性深度
- 信号系统独有的 7 个维度（D双底、非突破日放量/大阳线、sequence叙事、freshness衰减、turbulent过滤、支撑验证）提供了评分系统缺失的时间轴信息
- 融合后覆盖 **突破前（蓄力证据链）→ 突破日（高度重叠可简化）→ 突破后（能量追踪）** 三个时间维度

---

## 二、架构方案设计

### 2.1 数据流总览

```
原始 OHLCV 数据 (datasets/pkls/*.pkl)
         │
         ├──────────────────┐
         ▼                  ▼
   ┌──────────────┐   ┌───────────────┐
   │ analysis/     │   │ signals/       │
   │ PeakDetector  │   │ 4类检测器     │
   │ BreakoutDet.  │   │ B/V/Y/D       │
   │ BreakoutScorer│   │ + Freshness   │
   └──────┬───────┘   └──────┬────────┘
          │                   │
          ▼                   ▼
   ScoreBreakdown       SignalStats
   (quality_score,      (weighted_sum,
    bonuses,             sequence_label,
    broken_peaks)        freshness,
          │              turbulent)
          │                   │
          └─────────┬─────────┘
                    ▼
            ┌──────────────┐
            │ 融合桥接层    │
            │ (EnrichBridge)│
            │ + 模式分类    │
            └──────┬───────┘
                   ▼
           EnrichedBreakout
           (unified interface)
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
    Simple Pool   UI      回测引擎
    (入池+排序)  (展示)   (分组统计)
```

### 2.2 融合点设计：保持独立 + 桥接层

**不合并任何现有组件。** 两套系统各自独立运行，通过一个轻量桥接层整合输出。

| 组件 | 归属 | 融合后状态 | 理由 |
|------|------|-----------|------|
| PeakDetector | analysis | **不变** | 评分系统基础，无需改动 |
| BreakoutDetector | analysis | **不变** | 评分系统基础 |
| BreakoutScorer | analysis | **小改**：新增 pattern_label | 仅后处理，不改评分逻辑 |
| B/V/Y/D 检测器 | signals | **不变** | 信号系统基础 |
| SignalAggregator | signals | **不变** | 信号聚合逻辑完整 |
| Freshness | signals/composite | **不变** | 已在 combined 实现 |
| **EnrichBridge** | **新增** | ~100 行 | 桥接两套输出 |
| Simple Pool | simple_pool | **小改**：接受 EnrichedBreakout | 扩展入池接口 |

**关键原则：融合发生在数据层，不在逻辑层。** 两套系统各自计算，然后在输出端合流。

### 2.3 核心数据结构定义

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Any


@dataclass
class SignalContext:
    """
    信号系统分析结果的摘要

    来自 signals/ 模块的输出，被桥接层提取并附加到 Breakout 上。
    """
    sequence_label: str                    # 信号序列标签，如 "D(2) → B(3) → V"
    signal_count: int                      # lookback 窗口内信号总数
    weighted_sum: float                    # 原始加权强度和
    freshness_weighted_sum: float          # 鲜度调整后的加权强度和
    turbulent: bool                        # 是否异常走势
    amplitude: float                       # max_runup 值

    # 各信号的鲜度快照
    signal_freshness: Dict[str, float] = field(default_factory=dict)
    # 完整信号列表（供详细展示）
    signals: List[Any] = field(default_factory=list)


@dataclass
class EnrichedBreakout:
    """
    融合后的突破分析结果

    这是下游消费者（Simple Pool, UI, 回测引擎）的统一接口。
    由 EnrichBridge 负责构建。

    不继承 Breakout，而是引用它，保持组合优于继承。
    """
    # === 标识 ===
    symbol: str
    breakout_date: date
    breakout_price: float

    # === 评分层（来自 analysis/breakout_scorer） ===
    quality_score: float
    score_breakdown: Any  # ScoreBreakdown 对象
    pattern_label: str = "basic"  # 模式分类标签

    # === 信号层（来自 signals/，可选） ===
    signal_context: Optional[SignalContext] = None

    # === 原始引用（供需要完整数据的下游使用） ===
    breakout_ref: Any = None     # 原始 Breakout 对象
    signal_stats_ref: Any = None # 原始 SignalStats 对象

    # === 派生属性 ===

    @property
    def has_signal_context(self) -> bool:
        """是否附加了信号系统分析"""
        return self.signal_context is not None

    @property
    def composite_rank_score(self) -> float:
        """
        复合排序分数

        用于 Simple Pool 入池排序。
        当信号上下文可用时，综合考虑评分和信号鲜度；
        否则退化为纯评分。
        """
        base = self.quality_score
        if self.signal_context is not None:
            # 信号鲜度加权：如果信号能量充足，给予加成
            # 如果信号已衰减，给予折扣
            # freshness_weighted_sum / weighted_sum = 平均鲜度
            sc = self.signal_context
            if sc.weighted_sum > 0:
                avg_freshness = sc.freshness_weighted_sum / sc.weighted_sum
            else:
                avg_freshness = 1.0

            # turbulent 惩罚
            if sc.turbulent:
                base *= 0.5

            # 鲜度调制：[0.7, 1.1] 范围
            freshness_factor = 0.7 + 0.4 * avg_freshness
            base *= freshness_factor

        return base
```

### 2.4 重叠消除策略

两套系统在**突破当日成交量和K线形态**上有约 25% 重叠。具体处理：

| 重叠维度 | 评分系统 | 信号系统 | 消除策略 |
|---------|---------|---------|---------|
| 突破日成交量 | `volume_bonus` (volume_surge_ratio) | B信号的 `volume_ratio` | **各保留，不消重**。角度不同：评分侧重"放大倍数对阻力突破的意义"，信号侧重"是否出现超大成交量事件" |
| 突破日K线形态 | `idr_vol_bonus` (日内涨幅/σ) | Y信号 (大阳线/σ) | **各保留**。计算方式近似但用途不同：评分用作乘数影响总分，信号用作事件检测 |
| 峰值穿越 | `test_bonus` (簇内峰数) | B信号 `pk_num` | **各保留**。评分用聚类后的簇，信号直接计数，维度不完全相同 |
| 超涨/走势过热 | `overshoot_penalty` | `turbulent` | **各保留但设计互补路径**。overshoot 惩罚短期（5日σ），turbulent 检测中期（lookback窗口max_runup） |

**为什么不消重？**

核心理由：**重叠不是冗余。** 虽然 `idr_vol_bonus` 和 Y 信号都检测大阳线，但它们在不同的评估框架中扮演不同角色：
- 在评分框架中，`idr_vol_bonus` 是 11 个乘数之一，影响 quality_score 的排序
- 在信号框架中，Y 是 4 类事件之一，影响 sequence_label 和 weighted_sum

强行消重（例如"如果 Y 信号存在则 idr_vol_bonus 固定为 1.0"）反而会引入两套系统之间的耦合。**保持独立计算、独立输出、在桥接层合流**是最简洁的设计。

### 2.5 Simple Pool 接入融合系统

Simple Pool 当前通过 `add_entry_from_breakout()` 接入，仅使用 `quality_score` 和基本价格信息。融合后的接入方式：

```python
# 当前接口（不变，向后兼容）
manager.add_entry_from_breakout(breakout)

# 新增接口（接受 EnrichedBreakout）
manager.add_entry_from_enriched(enriched_breakout)
```

新接口在 PoolEntry 中保存额外信息：

```python
@dataclass
class PoolEntry:
    # ... 现有字段不变 ...

    # === 新增：信号上下文摘要（可选，来自融合层） ===
    pattern_label: str = "basic"
    signal_sequence: str = ""
    signal_freshness_avg: float = 1.0
```

**影响范围极小**：
- `PoolEntry` 新增 3 个可选字段（有默认值，不破坏现有实例化）
- `SimplePoolManager` 新增 1 个方法
- `SimpleEvaluator` 无需改动（评估逻辑不依赖信号上下文）
- 信号上下文仅用于入池排序和展示，不影响买入信号生成逻辑

---

## 三、分支选择分析

### 3.1 两个分支的现状

**combined 分支**：
- 包含完整的 `signals/` 模块（24 个文件，~3000 行代码 + ~1500 行测试）
- 已实现 P0（max_runup 替代 amplitude）和 P1（PRTR 信号鲜度）
- 包含 `analysis/support_analyzer.py`（424 行，B/D 信号支撑分析）
- 有完善的测试覆盖（9 个测试文件）
- 比 simple-pool 多 ~25 个 commits

**simple-pool 分支**（当前活跃）：
- 包含 Simple Pool MVP 模块（7 个文件，~600 行）
- 包含评分系统的最新版本（breakout_scorer.py）
- 包含最新的数据处理适配（CSV 无头文件处理）
- 比 combined 多 1 个 commit（7d4c7b3: adaptive to no head csv file）
- 不包含 signals/ 模块和 support_analyzer

**共同祖先**：`b61c729`（两个分支在此分叉）

### 3.2 三种方案对比

#### 方案 a：基于 combined，合并 simple-pool

| 维度 | 评估 |
|------|------|
| 合并冲突 | **零冲突**（经 `git merge --no-commit` 实测验证） |
| 代码完整度 | combined 已有信号系统全部代码 + 测试 + P0/P1 改进 |
| 需要的额外工作 | 合并后在 combined 上获得 Simple Pool 模块和 CSV 适配 |
| 风险 | **极低** — 自动合并无冲突 |
| 后续工作基础 | **最佳** — 信号系统测试覆盖完善，可直接开始融合工作 |

#### 方案 b：基于 simple-pool，引入 combined 的信号模块

| 维度 | 评估 |
|------|------|
| 操作方式 | `git cherry-pick` 或手动复制 signals/ 目录 |
| 代码完整度 | 需要手动引入 24 个文件 + 420 行 support_analyzer |
| 需要的额外工作 | 大量 cherry-pick 或手动文件复制，容易遗漏依赖 |
| 风险 | **中** — cherry-pick 25 个 commit 容易出错，manual copy 可能遗漏 |
| 后续工作基础 | 差 — 可能需要反复调试依赖关系 |

#### 方案 c：新建分支从零集成

| 维度 | 评估 |
|------|------|
| 必要性 | **完全不必要** — 两分支无冲突可直接合并 |
| 额外工作 | 大量重复劳动 |
| 风险 | 中 — 手动操作易出错 |

### 3.3 明确推荐：方案 a — 基于 combined 合并 simple-pool

**理由**：

1. **零冲突**：实测 `git merge` 完全自动化，无需人工干预
2. **combined 的存量价值大**：25 个 commit 包含完整信号系统、测试用例、P0/P1 改进。这些是融合的基础设施
3. **simple-pool 的增量小**：仅 1 个新 commit（CSV 适配）+ Simple Pool 模块（已在共同祖先之后添加）
4. **测试覆盖**：combined 的 9 个测试文件（~1500 行）确保信号系统的正确性，这是手动复制无法获得的保障

**操作步骤**：

```bash
# 1. 切换到 combined 分支
git checkout combined

# 2. 合并 simple-pool（无冲突）
git merge simple-pool -m "Merge simple-pool into combined: add Simple Pool MVP + CSV adapter"

# 3. 验证
python -m pytest BreakoutStrategy/signals/tests/ -v  # 信号系统测试
# (如有 Simple Pool 测试也一并运行)

# 4. 可选：重命名分支为更准确的名称
git branch -m combined unified  # 或其他合适的名称
```

---

## 四、分阶段实施路线图

考虑到以下已知的待办任务：
- **评分系统 3 个 bug 修复**：gap_vol/idr_vol 合并、overshoot 放宽、streak 扩展
- **combined 已完成的 P0/P1**：max_runup 替代 amplitude、PRTR 信号鲜度
- **融合工作**：桥接层、模式分类、Simple Pool 接入

### Phase 0：分支合并（0.5 天）

**目标**：将两个分支的代码统一到一个分支上。

```
操作：git checkout combined && git merge simple-pool
验证：运行现有测试，确保无回归
产出：统一代码库，包含信号系统 + 评分系统 + Simple Pool
```

### Phase 1：评分系统 bug 修复（1-2 天）

**目标**：修复 3 个已确认的高优先级数学问题。这些修复独立于融合工作，应最先完成以确保评分基础正确。

| 修复项 | 文件 | 改动 |
|--------|------|------|
| 合并 gap_vol + idr_vol | `breakout_scorer.py` L551-659, L880-893 | 取两者较大值作为 `breakout_day_strength_bonus` |
| 放宽 overshoot penalty | `breakout_scorer.py` L163-164 | `[0.7, 0.4]` → `[0.80, 0.60]` |
| 扩展 streak bonus | `breakout_scorer.py` L143-144 | `thresholds: [2]` → `[2, 4]`, `values: [1.20]` → `[1.20, 1.40]` |

**为什么最先做**：评分修复改变的是 quality_score 的数值分布，后续所有涉及 quality_score 的工作（模式分类阈值、Simple Pool 入池阈值、回测基线）都依赖于修复后的数值。

### Phase 2：模式分类标签（1 天）

**目标**：在评分系统中添加 `pattern_label`。

改动：
- `ScoreBreakdown` 新增 `pattern_label: Optional[str] = None`
- `BreakoutScorer` 新增 `_classify_pattern(bonuses)` 方法（~50 行）
- 在 `get_breakout_score_breakdown_bonus()` 末尾调用分类

**依赖 Phase 1**：模式分类基于 bonus level 判断，gap_vol/idr_vol 合并后 bonus 结构会变化。

### Phase 3：融合桥接层（1-2 天）

**目标**：实现 `EnrichBridge` 和 `EnrichedBreakout` 数据结构。

新增文件：
- `BreakoutStrategy/bridge.py`（或 `BreakoutStrategy/enrichment.py`），约 100 行

核心逻辑：
```python
class EnrichBridge:
    """
    融合桥接器

    将评分系统和信号系统的输出合流为 EnrichedBreakout。
    """

    def enrich(
        self,
        breakout: Breakout,
        score_breakdown: ScoreBreakdown,
        signal_stats: Optional[SignalStats] = None,
    ) -> EnrichedBreakout:
        """
        将评分和信号结果融合为统一输出

        Args:
            breakout: 原始突破对象
            score_breakdown: 评分分解
            signal_stats: 信号统计（可选，不可用时优雅降级）

        Returns:
            EnrichedBreakout
        """
        signal_context = None
        if signal_stats is not None:
            signal_context = self._extract_signal_context(signal_stats)

        return EnrichedBreakout(
            symbol=breakout.symbol,
            breakout_date=breakout.date,
            breakout_price=breakout.price,
            quality_score=score_breakdown.total_score,
            score_breakdown=score_breakdown,
            pattern_label=score_breakdown.pattern_label or "basic",
            signal_context=signal_context,
            breakout_ref=breakout,
            signal_stats_ref=signal_stats,
        )
```

**关键设计决策**：
- `signal_stats` 是 Optional，保证在信号系统不可用时（例如回测引擎未集成信号扫描）仍可正常工作
- 桥接层是无状态的纯函数，不持有任何检测器或评分器实例

### Phase 4：Simple Pool 接入（0.5-1 天）

**目标**：Simple Pool 接受 EnrichedBreakout 输入，利用信号上下文优化入池决策。

改动：
- `PoolEntry` 新增 3 个可选字段
- `SimplePoolManager` 新增 `add_entry_from_enriched()` 方法
- 入池排序可选使用 `composite_rank_score`

### Phase 5：回测验证（2-3 天）

**目标**：验证融合后系统的有效性。

验证项：
1. 评分修复后分数分布变化（Phase 1 回归）
2. 模式分类与人工判断一致性 > 80%（Phase 2 验证）
3. composite_rank_score vs 纯 quality_score 的入池信号成功率对比（Phase 4 验证）
4. 按模式分组的 MFE/MAE 差异分析

### 路线图时间线

```
Week 1:
  Day 1: Phase 0 (分支合并) + Phase 1 开始 (评分修复)
  Day 2: Phase 1 完成 + Phase 2 (模式分类)
  Day 3: Phase 3 (桥接层)

Week 2:
  Day 4: Phase 3 完成 + Phase 4 (Simple Pool 接入)
  Day 5-7: Phase 5 (回测验证)
```

### 与 combined 分支已有任务的协调

| 任务来源 | 描述 | 在融合路线图中的位置 | 状态 |
|---------|------|---------------------|------|
| combined P0 | max_runup 替代 amplitude | **已完成**（在 combined 分支中） | done |
| combined P1 | PRTR 信号鲜度 | **已完成**（在 combined 分支中） | done |
| combined P2 | 分层 P95 阈值 | Phase 5 之后，数据驱动决定 | pending |
| scoring bug | gap_vol/idr_vol 合并 | **Phase 1** | todo |
| scoring bug | overshoot 放宽 | **Phase 1** | todo |
| scoring bug | streak 扩展 | **Phase 1** | todo |
| pattern report | 模式分类标签 | **Phase 2** | todo |
| 本报告 | 融合桥接层 | **Phase 3** | todo |
| 本报告 | Simple Pool 接入 | **Phase 4** | todo |

---

## 五、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| composite_rank_score 排序效果不如纯 quality_score | 中 | 中 | Phase 4 中 composite_rank_score 设为可选，可随时回退到纯评分排序 |
| 信号系统与评分系统的时间窗口不匹配 | 低 | 低 | lookback_days 可独立配置，桥接层按 symbol+date 匹配 |
| 模式分类阈值在评分修复后需要调整 | 中 | 低 | Phase 2 安排在 Phase 1 之后，基于修复后的分数设定阈值 |
| 融合增加 Simple Pool 的入池延迟 | 低 | 低 | 信号扫描是批量预计算，不在每日评估路径上 |

---

## 六、关键结论

1. **部分融合是最佳策略**。两套系统 75% 互补、25% 重叠的特征决定了不应全合并，也不应完全独立。桥接层 + 统一接口是复杂度最低、信息增益最高的方案。

2. **基于 combined 分支合并 simple-pool 是明确的最优选择**。零冲突风险、最完整的代码基础、最好的测试覆盖。

3. **评分修复必须在融合之前完成**。模式分类和 composite_rank_score 都依赖于正确的评分数值。

4. **融合桥接层应设计为可选层**。下游消费者（Simple Pool, UI）可以选择使用完整的 EnrichedBreakout，也可以只使用传统的 Breakout + ScoreBreakdown。这保证了增量式采用和风险可控。

5. **sequence_label（信号叙事）和 pattern_label（突破质量模式）是两个独立的分类维度**，不应互相替代。前者描述"发生了什么事件序列"，后者描述"这是什么类型的突破"。

---

*报告由 architect (Tom) 生成*
*基于 overlap-analyst 和 pattern-analyst 的前置分析*
*日期: 2026-02-10*