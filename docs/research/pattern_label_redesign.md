# 突破模式分类重设计方案 (pattern_label v2)

**日期**: 2026-02-15
**分析师**: Claude Opus 4.6 (Tom)
**源码依据**: `BreakoutStrategy/analysis/breakout_scorer.py` (`_classify_pattern`, L799-853)
**统计依据**: `docs/statistics/bonus_combination_report.md` (n=9810)
**关联文档**: `docs/research/bonus_system_gap_analysis.md`, `docs/research/pattern_classification_analysis.md`

---

## Executive Summary

当前 `_classify_pattern()` 以 Age 和 Tests 作为核心分类轴（所有混合模式均要求 age_level >= 2），但统计分析已证明这两个因子对突破后收益无显著预测力。本方案基于经过 n=9810 验证的有效因子重构分类体系，核心变化如下：

1. **移除** Age/Tests 作为分类轴 -- 它们的 Spearman r 几乎为零，不应决定突破的"类型"
2. **引入** Volume + PBM + DayStr 三核心正向因子的组合作为分类基础
3. **将 Streak 从"趋势延续"语义反转为"频繁突破降级"标记** -- 数据证明它是最强负信号
4. **拆分"momentum"超大类** -- 旧方案中 momentum 占 58%（5685/9810），新方案将其分散到多个有意义的子类
5. 最终产出 **8 个模式**，每个都有清晰的市场叙事和数据支撑

预期效果：新方案将具备更好的区分度 -- 高收益组（Volume/PBM/DayStr 驱动的模式）的 median 预期达 0.20-0.30，低收益组（Streak 降级或无因子触发）的 median 预期在 0.10-0.13。

---

## 一、设计原则与方法论

### 1.1 核心原则

1. **用数据选因子，用因子建模式** -- 不是从 top 组合反推模式（过拟合），而是基于因子层面的统计显著性（n=9810）构建分类
2. **每个分类轴必须有统计支撑** -- Spearman 显著（p < 0.001）或 RF 重要性排名前列
3. **模式应有可解释的市场叙事** -- 不追求数学最优分组，确保交易者能理解每个模式的含义
4. **奥卡姆剃刀** -- 最少的模式数量覆盖最大的信息区分度

### 1.2 因子选择依据

**纳入分类体系的因子**（按区分力排序）：

| 因子 | Spearman r | RF 重要性 | 角色 | 纳入理由 |
|------|-----------|----------|------|---------|
| Streak | -0.1988*** | 0.2178 | **反向信号** | 绝对值最大的相关因子，频繁突破 = 收益下降 43% |
| Volume | +0.1363*** | 0.3582 | **核心正向** | RF 重要性第一，放量突破的 median 翻倍（0.15 -> 0.29） |
| PBM | +0.1730*** | 0.1778 | **核心正向** | Spearman 最高的正相关因子 |
| DayStr | +0.1659*** | 0.0855 | **核心正向** | 突破日本身的强度信号 |
| PK-Mom | +0.0998*** | 0.0331 | **辅助正向** | 近期凹陷深度，中等效果 |
| Drought | +0.0927*** | 0.0512 | **辅助正向** | 非线性，level 1 最佳（median 0.2489） |

**不纳入分类体系的因子**：

| 因子 | 原因 |
|------|------|
| Age | r = -0.0223，各 level median 几乎无差异（0.1514~0.1783），不具备区分力 |
| Tests | r = +0.0039, p = 0.70，完全不显著 |
| PeakVol | 效果不稳定，level 1 反而低于 level 0 |
| Overshoot | 角色矛盾（设计为惩罚但触发者 median 更高），属于幸存者偏差 |

### 1.3 关于 Age/Tests 在评分模型中的保留

**重要说明**：本方案仅重构 `_classify_pattern()` 的分类逻辑，不涉及评分模型的因子增减。Age/Tests 在评分乘法模型中保留（建议降权至近乎中性），但不再作为分类轴。这与 `docs/research/bonus_system_gap_analysis.md` 的建议一致 -- "降权保留，支撑 level 计算但不影响分类"。

---

## 二、新分类体系设计

### 2.1 设计思路：三层判定结构

```
Layer 1: Streak 降级检查（反向因子，优先截断）
  |
  +-- streak_level >= 1 且无强正向因子 --> 降级模式
  |
Layer 2: 核心正向因子组合（Volume, PBM, DayStr 的交互）
  |
  +-- 多因子共振 --> 混合模式
  +-- 单因子主导 --> 单一模式
  |
Layer 3: 辅助因子补充（PK-Mom, Drought）
  |
  +-- 辅助因子触发 --> 辅助模式
  +-- 无任何因子 --> 兜底模式
```

**为什么 Streak 优先判定？**

Streak 是唯一的反向因子（r = -0.1988），且 RF 重要性排名第二（0.2178）。当一个突破处于频繁突破状态时，无论其他因子多好，这个结构性特征都会显著拉低后续收益。统计证据：
- Streak level 0: median = 0.1956
- Streak level 2: median = 0.1120（下降 43%）

但关键细节是：**不是所有 streak 突破都差**。从交互效应看，Volume + Streak 的交互效应为 0.1950（正），说明放量的连续突破仍可能有好表现。因此 Streak 降级应该是有条件的 -- 只有在缺乏强正向因子对冲时才降级。

### 2.2 八个模式定义

#### Tier 1: 放量驱动模式（Volume 主导，预期 median 0.23-0.30）

**模式 1: `power_surge` -- 放量+动量共振**
- 条件: `vol_level >= 1 AND pbm_level >= 2`
- 市场叙事: 突破前持续蓄力（PBM 高）+ 突破时资金大举涌入（Volume 高）。这是买方主力最明确的入场信号 -- 既有耐心的蓄势（突破前涨势强劲），又有果断的进攻（放量突破）。对应统计中最强正交互 Volume+PBM (effect = 0.2114)。
- 数据支撑: Volume level>=1 共 708 个，其中 PBM level>=2 约占 45% (基于 n_both=317)。预期 n 约 300-320。
- 预期 median: ~0.25-0.30（Volume level 2 median 0.29 + PBM level 2 median 0.22 的交互增强）

**模式 2: `volume_breakout` -- 纯放量突破**
- 条件: `vol_level >= 1`（排除已被 power_surge 捕获的样本）
- 市场叙事: 突破日成交量显著放大，说明有催化剂驱动。可能是财报、行业新闻或机构资金介入。放量是突破有效性的最强单因子验证。
- 数据支撑: Volume level>=1 共 708，减去 power_surge ~320，剩余约 380-400。
- 预期 median: ~0.20-0.23（Volume level 1 median 0.2326）

#### Tier 2: 动量驱动模式（PBM/DayStr 主导，预期 median 0.18-0.23）

**模式 3: `strong_momentum` -- 强势蓄力+强突破日**
- 条件: `pbm_level >= 2 AND daystr_level >= 1`（且 vol_level == 0，未被 Tier 1 捕获）
- 市场叙事: 虽然成交量未明显放大，但突破前涨势强劲且突破日本身力度很大（日内涨幅或跳空幅度显著）。这代表"价格驱动"型突破 -- 市场用价格而非成交量表达方向。
- 数据支撑: PBM level 2 共 2863，DayStr level>=1 共 2342。去除 Volume>=1 后的交集，估算约 500-700。
- 预期 median: ~0.20-0.22（PBM level 2 median 0.2176, DayStr level 1 median 0.2011）

**模式 4: `momentum` -- 蓄力突破**
- 条件: `pbm_level >= 2`（排除已被前面模式捕获的样本）
- 市场叙事: 突破前有显著的涨势积累（过去 N 天的标准化涨幅明显）。价格从低位一路爬升到阻力位附近，积蓄了足够动能后完成突破。这是最经典的"蓄力突破"形态。
- 数据支撑: PBM level 2 共 2863，减去 power_surge (~300) 和 strong_momentum (~600)，剩余约 1900-2000。
- 预期 median: ~0.18-0.20（PBM level 2 原始 median 0.2176，但去除 Volume 和 DayStr 叠加后会略低）

#### Tier 3: 辅助因子模式（PK-Mom / Drought 主导，预期 median 0.17-0.25）

**模式 5: `dip_recovery` -- 凹陷反弹**
- 条件: `pk_mom_level >= 2 AND pbm_level < 2 AND vol_level == 0`（避免与 Tier 1/2 重叠）
- 市场叙事: 近期峰值附近出现深度回调后反弹突破。价格先探底再回升突越前高，形成 V 型或 U 型反转。PK-Mom 高意味着从谷底到突破的幅度很大，买方在恐慌后重新掌控了局面。
- 数据支撑: PK-Mom level 2 共 6199，但大部分会被 PBM 或 Volume 先行捕获。去除 Tier 1/2 后的纯 PK-Mom 主导样本，估算约 800-1200。
- 预期 median: ~0.17-0.18（PK-Mom level 2 median 0.1739，但独立时效果中等）

**模式 6: `dormant_awakening` -- 沉寂觉醒**
- 条件: `drought_level >= 1`（且未被前面模式捕获）
- 市场叙事: 股票长时间未产生突破信号后突然觉醒。长期沉寂代表市场对该股关注度下降，当突破终于发生时，往往意味着基本面出现了新的变化。统计显示适度沉寂（60-80 交易日）后的突破效果最佳。
- 数据支撑: Drought level>=1 共 763，但部分会被 Volume/PBM 先捕获。纯 Drought 主导约 200-400。
- 预期 median: ~0.19-0.25（Drought level 1 median 0.2489，是所有辅助因子中表现最好的）

#### Tier 4: 降级与兜底模式（预期 median 0.10-0.14）

**模式 7: `crowded_breakout` -- 拥挤突破（Streak 降级）**
- 条件: `streak_level >= 1 AND vol_level == 0 AND pbm_level < 2`（高频突破且无强正向因子对冲）
- 市场叙事: 该股近期频繁产生突破信号，意味着阻力位密集且间距小。频繁突破稀释了每次突破的意义，同时积累了大量短线获利盘。如果此时还没有放量或强蓄力来支撑，后续表现堪忧。
- 设计理由: Streak 是反向因子（r = -0.1988），但 Volume+Streak 交互为正（0.1950），所以放量的连续突破不应被降级。仅当 Streak 触发且缺乏 Volume/PBM 对冲时才归入此类。
- 数据支撑: Streak level>=1 共 6522，去除有 Volume 或 PBM 对冲的（估算 60-70%），剩余约 1500-2000。
- 预期 median: ~0.10-0.12（Streak level 2 median 0.1120，纯 Streak 组合的 median 0.0995）

**模式 8: `basic` -- 基础突破（兜底）**
- 条件: 不满足以上任何模式
- 市场叙事: 突破发生了，但没有任何经过验证的有效因子提供额外的质量信号。这是一个"中性"的突破 -- 不特别好也不特别差。
- 数据支撑: 所有因子都未触发的样本 n=77（median 0.1238），加上仅触发了 DayStr level 1 或 PK-Mom level 1 等弱信号的样本。估算约 300-500。
- 预期 median: ~0.13-0.14

### 2.3 模式全景矩阵

| # | 模式 | 核心条件 | 市场叙事 | 预期 n | 预期 median | UI 缩写 |
|---|------|---------|---------|--------|------------|--------|
| 1 | `power_surge` | Vol>=1 + PBM>=2 | 放量+动量共振 | ~300 | ~0.27 | POWER |
| 2 | `volume_breakout` | Vol>=1 | 纯放量突破 | ~400 | ~0.22 | VOL |
| 3 | `strong_momentum` | PBM>=2 + DayStr>=1 | 强势蓄力+强突破日 | ~600 | ~0.21 | S.MOM |
| 4 | `momentum` | PBM>=2 | 蓄力突破 | ~1900 | ~0.19 | MOM |
| 5 | `dip_recovery` | PK-Mom>=2 | 凹陷反弹 | ~1000 | ~0.17 | DIP |
| 6 | `dormant_awakening` | Drought>=1 | 沉寂觉醒 | ~300 | ~0.22 | DORMT |
| 7 | `crowded_breakout` | Streak>=1 (无对冲) | 拥挤突破 | ~1800 | ~0.11 | CROWD |
| 8 | `basic` | (无) | 基础突破 | ~400 | ~0.13 | -- |
| | | | **合计** | ~6700* | | |

*注：预期 n 的总和约 6700，与 9810 存在差距。这是因为各因子 level 分布存在大量重叠，实际的排他分配需要通过回测精确计算。上述估算基于因子触发率的近似推断，最终分布需回测验证。

### 2.4 关键设计决策

#### 决策 1: 混合模式是否保留？

**保留，但基于有效因子组合。** 唯一保留的混合模式是 `power_surge`（Volume + PBM），因为：
- 这是统计上最强的正交互（effect = 0.2114）
- 两个核心正向因子的叠加有清晰的市场逻辑：蓄力 + 放量
- 样本量足够（n_both = 317）

不保留旧方案中的 deep_rebound (PK-Mom + Age)、power_historical (Volume + Age)、grind_through (Age + Tests) -- 因为这些混合模式的另一半 (Age/Tests) 已被证明无效。power_historical 在旧方案中 median 最高（0.2981），但 Mann-Whitney 测试显示它与 volume_surge (0.2778) 无显著差异 (p = 0.52)，证明 Age 在其中不提供附加价值。

#### 决策 2: Streak 如何体现？

**作为有条件的降级标记，而非独立模式。**

理由：
- Streak 是反向因子，不应作为"一种突破类型"（没有人追求频繁突破这种模式）
- 但当 Streak 与强正向因子共存时（如 Volume+Streak），正向因子的价值仍然成立
- 因此设计为"有条件降级"：仅当 Streak 触发且无 Volume/PBM 对冲时，才归入 `crowded_breakout`

这与旧方案的 `trend_continuation`（将 Streak 包装为正面叙事）形成鲜明对比 -- 数据证明"趋势延续"这个叙事是错误的。

#### 决策 3: 如何打碎 momentum 超大类？

旧方案中 momentum 占 58%（5685/9810），因为它仅依赖 PK-Mom >= 1 这一个条件。新方案通过三个机制拆分：

1. **提升 PBM 为主要动量分类轴**（替代 PK-Mom 的主导地位）：PBM 的 Spearman r (0.1730) 远高于 PK-Mom (0.0998)，且 RF 重要性也更高 (0.1778 vs 0.0331)
2. **PBM 与 DayStr 的交叉产生 strong_momentum**：将"蓄力+强突破日"从纯蓄力中分离
3. **PK-Mom 降格为辅助因子**：从旧方案中 momentum 的唯一判定条件，变为 `dip_recovery` 这个独立模式的条件

预期拆分结果：旧 momentum (5685) --> 新分布约为 power_surge (~300) + strong_momentum (~600) + momentum (~1900) + dip_recovery (~1000) + 部分流入 dormant_awakening 和 crowded_breakout。

#### 决策 4: basic 应覆盖多大比例？

**目标：5-10%（约 400-800 个样本）。**

旧方案 basic 仅 259 个（2.6%），但这是因为 PK-Mom 的低阈值 (level >= 1 即 >= 1.5) 把绝大多数样本吸入了 momentum。新方案中 basic 的条件是"无任何有效因子触发"，考虑到：
- 完全无因子触发: n=77
- 仅触发单个弱因子（DayStr level 1 或 PK-Mom level 1）: 估算约 300-400

预期 basic 占比约 4-8%，这是合理的 -- 它代表"没有特别值得注意的特征"这一信息。

---

## 三、优先级顺序与判定逻辑

### 3.1 优先级设计原则

优先级顺序基于两个标准：
1. **区分力优先**：高 median 和高统计显著性的因子条件先判定
2. **排他性保证**：每个突破只归入一个模式，且归入区分力最强的那个

### 3.2 判定流程图

```
输入: bonuses (List[BonusDetail])
  |
  v
[Step 1] Volume >= 1 AND PBM >= 2?
  |-- YES --> "power_surge"        (放量+动量共振)
  |-- NO  --> 继续
  v
[Step 2] Volume >= 1?
  |-- YES --> "volume_breakout"    (纯放量突破)
  |-- NO  --> 继续
  v
[Step 3] PBM >= 2 AND DayStr >= 1?
  |-- YES --> "strong_momentum"    (强势蓄力+强突破日)
  |-- NO  --> 继续
  v
[Step 4] PBM >= 2?
  |-- YES --> "momentum"           (蓄力突破)
  |-- NO  --> 继续
  v
[Step 5] Drought >= 1?
  |-- YES --> "dormant_awakening"  (沉寂觉醒)
  |-- NO  --> 继续
  v
[Step 6] PK-Mom >= 2?
  |-- YES --> "dip_recovery"       (凹陷反弹)
  |-- NO  --> 继续
  v
[Step 7] Streak >= 1?
  |-- YES --> "crowded_breakout"   (拥挤突破)
  |-- NO  --> 继续
  v
[Step 8] "basic"                   (基础突破)
```

### 3.3 优先级详解

**为什么 Volume 在最高优先级？**
- RF 重要性第一 (0.3582)
- Volume level 2 的 median (0.2923) 是所有单因子 level 中最高的
- 放量是催化剂驱动的最强信号，一旦出现，它定义了这次突破的本质

**为什么 PBM 优先于 PK-Mom？**
- PBM 的 Spearman r (0.1730) >> PK-Mom (0.0998)
- PBM 的 RF 重要性 (0.1778) >> PK-Mom (0.0331)
- PBM 度量的是突破前的整体涨势强度，PK-Mom 仅度量近期峰值附近的凹陷深度，前者信息量更大

**为什么 Drought 优先于 PK-Mom？**
- Drought level 1 的 median (0.2489) >> PK-Mom level 2 的 median (0.1739)
- Drought 虽然 Spearman r 略低，但其 level 1 的绝对收益水平更高
- 将 Drought 放在 PK-Mom 之前，确保这些高收益样本不被 PK-Mom 先行吸收

**为什么 Streak (crowded_breakout) 放在倒数第二？**
- 设计意图是"有条件降级"：只有当一个 Streak 突破无法被任何正向因子捕获时，才归入降级类
- 如果一个 Streak 突破同时有 Volume（step 1/2 捕获）或 PBM（step 3/4 捕获），它会被分入正向模式而非降级
- 这实现了"Streak 降级仅在缺乏对冲时生效"的设计目标

---

## 四、伪代码实现

```python
def _classify_pattern(self, bonuses: List[BonusDetail]) -> str:
    """
    根据有效因子对突破进行模式分类（v2）

    设计原则：
    - 仅使用经过 n=9810 统计验证的有效因子作为分类轴
    - 移除 Age/Tests（无预测力），保留 Volume/PBM/DayStr/Streak/PK-Mom/Drought
    - Streak 作为有条件降级标记（仅在无强正向因子对冲时降级）
    - 优先级按因子区分力排序：Volume > PBM > DayStr > Drought > PK-Mom > Streak

    模式定义（按优先级）：
    - Tier 1 放量驱动: power_surge (Vol+PBM), volume_breakout (Vol)
    - Tier 2 动量驱动: strong_momentum (PBM+DayStr), momentum (PBM)
    - Tier 3 辅助因子: dormant_awakening (Drought), dip_recovery (PK-Mom)
    - Tier 4 降级/兜底: crowded_breakout (Streak无对冲), basic

    Args:
        bonuses: BonusDetail 列表

    Returns:
        模式标签字符串
    """
    b = {bonus.name: bonus for bonus in bonuses}

    # 提取各因子 level
    vol_level = b["Volume"].level if "Volume" in b else 0
    pbm_level = b["PBM"].level if "PBM" in b else 0
    daystr_level = b["DayStr"].level if "DayStr" in b else 0
    streak_level = b["Streak"].level if "Streak" in b else 0
    pk_mom_level = b["PK-Mom"].level if "PK-Mom" in b else 0
    drought_level = b["Drought"].level if "Drought" in b else 0

    # === Tier 1: 放量驱动 ===
    # 放量是 RF 重要性第一的因子，优先判定
    if vol_level >= 1:
        if pbm_level >= 2:
            return "power_surge"       # 放量+动量共振（最强正交互）
        return "volume_breakout"       # 纯放量突破

    # === Tier 2: 动量驱动 ===
    # PBM 是 Spearman 最高的正向因子
    if pbm_level >= 2:
        if daystr_level >= 1:
            return "strong_momentum"   # 强势蓄力+强突破日
        return "momentum"              # 蓄力突破

    # === Tier 3: 辅助因子 ===
    # Drought level 1 的 median (0.2489) 高于 PK-Mom level 2 (0.1739)
    if drought_level >= 1:
        return "dormant_awakening"     # 沉寂觉醒

    if pk_mom_level >= 2:
        return "dip_recovery"          # 凹陷反弹

    # === Tier 4: 降级与兜底 ===
    # Streak 降级：仅在缺乏 Volume/PBM 对冲时生效
    # （有 Volume 或 PBM 的 Streak 突破已在 Tier 1/2 中被正向分类）
    if streak_level >= 1:
        return "crowded_breakout"      # 拥挤突破（频繁突破降级）

    return "basic"                     # 基础突破
```

### 4.1 代码要点说明

1. **简洁性**: 整个分类逻辑不到 30 行有效代码，远少于旧版。没有任何嵌套的混合判定，只有一个 power_surge 需要两个条件。

2. **Streak 处理的隐式设计**: Streak 降级是"隐式"实现的 -- Streak>=1 的突破如果同时有 Volume>=1 或 PBM>=2，会在 Step 1-4 被分入正向模式，永远到不了 Step 7。只有"纯 Streak"（无正向因子对冲）才会落入 `crowded_breakout`。这比显式写 `streak_level >= 1 AND vol_level == 0 AND pbm_level < 2` 更简洁，且效果完全等价。

3. **PK-Mom 阈值提升至 level 2**: 旧方案用 level >= 1（pk_momentum >= 1.5），但 PK-Mom level 1 只有 1 个样本（统计报告中 count=1），实际上所有触发都是 level 2（count=6199）。将阈值设为 level >= 2 更准确。

4. **Drought 不设条件互斥**: 旧方案的 Drought 与 Age 有条件互斥设计（age_level >= 2 时 Drought 不生效），但新方案中 Age 不再参与分类判定。Drought 在评分模型中是否保留条件互斥是独立的设计决策，不影响分类逻辑。

---

## 五、与旧方案的迁移映射

### 5.1 旧模式 --> 新模式映射

| 旧模式 | 旧条件 | 预期流向 | 说明 |
|--------|--------|---------|------|
| `power_historical` (n=160) | Vol>=1 + Age>=2 | **volume_breakout** 或 **power_surge** | Age 条件被移除。有 PBM>=2 的流入 power_surge，其余流入 volume_breakout。|
| `volume_surge` (n=80) | Vol>=1 (且无 Age>=2) | **volume_breakout** 或 **power_surge** | 完全相同的逻辑，只是名称变更。|
| `deep_rebound` (n=515) | PK-Mom>=1 + Age>=2 | 分散到多个模式 | 有 Vol 的流入 Tier 1；有 PBM>=2 的流入 Tier 2；仅有 PK-Mom 的流入 dip_recovery；有 Streak 的可能流入 crowded_breakout。|
| `momentum` (n=5685) | PK-Mom>=1 | **大规模拆分** | 这是最大的变化。约 2500 个有 PBM>=2 的流入 momentum/strong_momentum/power_surge；约 1000 个仅有 PK-Mom>=2 的流入 dip_recovery；约 1500 个有 Streak 无对冲的流入 crowded_breakout；部分流入 dormant_awakening/basic。|
| `historical` (n=943) | Age>=2 (单一) | 分散到多个模式 | Age 不再是分类条件。有 Vol/PBM/PK-Mom 等的按各自条件分流；无任何有效因子的流入 basic。|
| `grind_through` (n=466) | Age>=2 + Tests>=1 | 分散到多个模式 | 同 historical，按有效因子条件重新分配。|
| `trend_continuation` (n=1605) | Streak>=1 | **crowded_breakout** 或升级 | 语义反转：旧方案将 Streak 包装为正面（趋势延续），新方案正确识别其负面本质。有 Volume 或 PBM 对冲的升级到 Tier 1/2，其余降级为 crowded_breakout。|
| `dormant_breakout` (n=89) | Drought>=1 | **dormant_awakening** | 几乎直接映射，仅名称微调。|
| `dense_test` (n=8) | Tests>=2 | 分散 | 样本极少，按各自有效因子条件重新分配。|
| `basic` (n=259) | 无因子触发 | **basic** | 直接映射。部分旧 basic 可能触发了新纳入的 DayStr 或 PBM 而升级。|

### 5.2 核心变化总结

| 维度 | 旧方案 | 新方案 | 变化原因 |
|------|--------|--------|---------|
| 分类轴 | Age, Tests, PK-Mom, Volume, Streak | Volume, PBM, DayStr, Drought, PK-Mom, Streak | 用有效因子替代无效因子 |
| 混合模式数量 | 3 个（均需 Age>=2） | 1 个（Volume+PBM） | 只保留有统计证据的交互 |
| 最大模式占比 | momentum 58% | momentum ~19% | 打碎超大类 |
| Streak 语义 | 正面（趋势延续） | **反面（拥挤降级）** | 数据驱动的根本矫正 |
| 总模式数 | 10 个 | 8 个 | 精简，移除无效模式 |

### 5.3 UI 缩写映射更新

以下是 `BreakoutStrategy/UI/charts/components/markers.py` 中 `pattern_abbr` 字典需要更新的映射：

```python
# 新方案的模式缩写映射
pattern_abbr = {
    "power_surge": "POWER",
    "volume_breakout": "VOL",
    "strong_momentum": "S.MOM",
    "momentum": "MOM",
    "dormant_awakening": "DORMT",
    "dip_recovery": "DIP",
    "crowded_breakout": "CROWD",
    # "basic" 不显示缩写（保持旧行为）
}
```

---

## 六、预期效果与风险评估

### 6.1 预期模式表现排序

基于因子统计数据推断的各模式 median 排序：

```
power_surge     (~0.27) >>>
dormant_awakening (~0.22) >
volume_breakout (~0.22) >
strong_momentum (~0.21) >
momentum        (~0.19) >
dip_recovery    (~0.17) >>
basic           (~0.13) >
crowded_breakout (~0.11)
```

**区分度提升**: 最佳模式 (power_surge, ~0.27) 与最差模式 (crowded_breakout, ~0.11) 之间的 median 差距约 0.16，相比旧方案中 power_historical (0.2981) 与 trend_continuation (0.1221) 的差距 0.176 相当。但新方案的关键优势在于：
- 高收益组涵盖了更多样本（power_surge+volume_breakout+strong_momentum+momentum ~3200 vs 旧方案 power_historical+volume_surge 240）
- 低收益组有明确的负面因子支撑（Streak 反向），不是 Age 这种伪信号

### 6.2 与旧方案对比的预期优势

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| 模式间 Mann-Whitney 显著性 | 部分模式无显著差异（historical vs basic, p=0.57） | 预期相邻 Tier 之间有显著差异 |
| 最大模式占比 | 58% (momentum) | ~19% (momentum)，信息熵更高 |
| 分类因子有效性 | Age r=-0.02, Tests r=+0.004 | 全部因子 p<0.001 |
| 反向因子处理 | Streak 被包装为正面 | Streak 正确识别为降级标记 |
| 混合模式基础 | Age 无附加价值 (p=0.52) | Volume+PBM 最强正交互 (effect=0.21) |

### 6.3 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 新模式间区分度不如预期 | 中 | 中 | 回测验证，若 Mann-Whitney 不显著则调整条件/合并模式 |
| PBM level 2 的阈值可能过高，导致 momentum 模式仍然偏大 | 中 | 低 | 可考虑增加 PBM level 1 (目前阈值 0.70) 的判定逻辑 |
| crowded_breakout 可能包含部分不该降级的样本 | 低 | 中 | 监控其中有 DayStr>=1 的子集表现，必要时细化条件 |
| dormant_awakening 样本量可能偏少 (<200) | 中 | 低 | 可接受，Drought 本身是稀有事件（触发率 ~8%） |
| 旧系统下游依赖 pattern_label 的代码需同步更新 | 确定 | 低 | 涉及 markers.py (缩写映射)、stock_list_panel.py、scan_manager.py、score_tooltip.py |

---

## 七、待验证假设

以下假设需要通过回测（基于现有 9810 个样本或未来增量数据）确认：

### H1: 新方案的模式间区分度优于旧方案

- **验证方法**: 对新方案的 8 个模式做 Kruskal-Wallis 检验 + pairwise Mann-Whitney
- **判定标准**: H 统计量 >= 236（旧方案的水平），且相邻 Tier 之间（如 volume_breakout vs momentum）的 Mann-Whitney p < 0.05
- **预期结果**: 旧方案中大量不显著的对比（historical vs basic p=0.57, grind_through vs trend_continuation p=0.29）在新方案中应消失

### H2: power_surge 是新方案中表现最好的模式

- **验证方法**: 统计 power_surge 的 median 和 q25/q75
- **判定标准**: median >= 0.25，且与 momentum 的 Mann-Whitney p < 0.01
- **预期结果**: Volume+PBM 共振组的 median 应在 0.25-0.30 之间

### H3: crowded_breakout 的 median 显著低于 basic

- **验证方法**: Mann-Whitney 检验 crowded_breakout vs basic
- **判定标准**: p < 0.05，crowded_breakout median < basic median
- **预期结果**: Streak 无对冲组应是最差的模式。如果不显著，可能需要将 Streak 降级条件收紧（如 streak_level >= 2）

### H4: 旧 momentum 超大类被有效拆分

- **验证方法**: 统计新方案中原属旧 momentum 的 5685 个样本的去向分布
- **判定标准**: 新 momentum 模式占比 < 25%（从 58% 下降），且分出的子类之间有显著 median 差异
- **预期结果**: 约 2000 个流入新 momentum，1000 个流入 dip_recovery，800 个流入 crowded_breakout，余下分散

### H5: Drought 的非线性特征在新分类中得到体现

- **验证方法**: 分别统计 dormant_awakening 中 drought level 1 和 level 2+ 的 median
- **判定标准**: level 1 的 median 高于 level 2+ 的 median（验证倒 U 型特征）
- **预期结果**: level 1 (~0.25) > level 2 (~0.22)，与单因子分析结论一致

### H6: 放量的 Streak 突破不被错误降级

- **验证方法**: 统计 Streak>=1 且 Volume>=1 的样本在新方案中被分入 power_surge/volume_breakout 的比例，及其 median
- **判定标准**: 这些样本的 median 应 >= 0.20（远高于 crowded_breakout 的 ~0.11）
- **预期结果**: 约 300 个放量 Streak 突破被分入 Tier 1，median 约 0.20-0.25

### H7: DayStr 作为 strong_momentum 的第二条件是否提供了足够的区分力

- **验证方法**: 对比 strong_momentum (PBM>=2 + DayStr>=1) 与 momentum (PBM>=2 仅) 的 median
- **判定标准**: Mann-Whitney p < 0.05，strong_momentum median > momentum median
- **预期结果**: DayStr 叠加后 median 提升约 0.02-0.04。如果不显著，考虑合并这两个模式

---

## 八、实施建议

### 8.1 代码改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `BreakoutStrategy/analysis/breakout_scorer.py` | **核心改动** | `_classify_pattern()` 方法重写 |
| `BreakoutStrategy/UI/charts/components/markers.py` | 映射更新 | `pattern_abbr` 字典更新 |
| `BreakoutStrategy/UI/charts/components/score_tooltip.py` | 可能需更新 | 如果有模式名称的展示逻辑 |
| `BreakoutStrategy/UI/panels/stock_list_panel.py` | 可能需更新 | 股票列表中模式列的展示 |
| `BreakoutStrategy/UI/managers/scan_manager.py` | 可能需更新 | 扫描结果中的模式过滤逻辑 |
| `docs/explain/breakout_pattern_reference.md` | 文档更新 | 模式参考文档 |

### 8.2 建议实施步骤

1. **先回测验证** -- 在不修改代码的前提下，编写一个独立脚本，用新的分类逻辑对现有 9810 个样本重新分类，统计各模式的 median/count，验证 H1-H7
2. **确认后再改代码** -- 如果回测结果符合预期，再修改 `_classify_pattern()` 和下游 UI 代码
3. **渐进式切换** -- 可考虑先在 `_classify_pattern()` 中同时计算新旧标签（新标签存入 `pattern_label_v2`），保留旧标签一段时间以便对比

### 8.3 回测脚本建议

在 `scripts/analysis/bonus_combination_analysis.py` 的 `build_dataframe()` 基础上，新增一个 `classify_pattern_v2()` 函数，对每行数据应用新分类逻辑，然后按新模式分组统计。这比直接修改 scorer 更安全，且可以快速验证。

---

## 附录 A: 因子触发率与分布参考

来自 `docs/statistics/bonus_combination_report.md` 的关键数据：

| 因子 | Level 0 count | Level 1 count | Level 2 count | Level 3 count | 触发率 |
|------|:---:|:---:|:---:|:---:|:---:|
| Volume | 9102 | 383 | 325 | - | 7.2% |
| PBM | 5711 | 1236 | 2863 | - | 41.7% |
| DayStr | 7468 | 1345 | 997 | - | 23.9% |
| PK-Mom | 3610 | 1 | 6199 | - | 63.2% |
| Streak | 3288 | 3722 | 2800 | - | 66.5% |
| Drought | 9047 | 304 | 320 | 139 | 7.8% |

## 附录 B: 旧版 `_classify_pattern()` 完整代码

```python
# 文件: BreakoutStrategy/analysis/breakout_scorer.py, L799-853
def _classify_pattern(self, bonuses: List[BonusDetail]) -> str:
    b = {bonus.name: bonus for bonus in bonuses}

    pk_mom = b.get("PK-Mom")
    age = b.get("Age")
    tests = b.get("Tests")
    vol = b.get("Volume")
    streak = b.get("Streak")

    pk_mom_level = pk_mom.level if pk_mom else 0
    age_level = age.level if age else 0
    tests_level = tests.level if tests else 0
    vol_level = vol.level if vol else 0
    streak_level = streak.level if streak else 0

    # 混合模式优先判定
    if pk_mom_level >= 1 and age_level >= 2:
        return "deep_rebound"       # A+B 深蹲远射
    if vol_level >= 1 and age_level >= 2:
        return "power_historical"   # B+C 放量历史突破
    if age_level >= 2 and tests_level >= 1:
        return "grind_through"      # B+D 磨穿防线

    # 单一模式判定
    if pk_mom_level >= 1:
        return "momentum"           # A 势能突破
    if age_level >= 2:
        return "historical"         # B 历史阻力突破
    if vol_level >= 1:
        return "volume_surge"       # C 放量爆发
    if tests_level >= 2:
        return "dense_test"         # D 密集测试
    if streak_level >= 1:
        return "trend_continuation" # E 趋势延续

    drought = b.get("Drought")
    drought_level = drought.level if drought else 0
    if drought_level >= 1:
        return "dormant_breakout"   # G 沉寂突破

    return "basic"                  # F 基础突破
```

---

*报告由 Claude Opus 4.6 (Tom) 生成*
*分析方法: 因子级统计显著性驱动 + 第一性原理模式构建*
*日期: 2026-02-15*
