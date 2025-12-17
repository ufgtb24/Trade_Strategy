# 突破模式 (Breakout Patterns) 完整参考文档

> **生成日期**: 2026-02-11
> **数据来源**: `BreakoutStrategy/analysis/breakout_scorer.py` (_classify_pattern 方法, L754-803)
> **UI 展示位置**: Score Detail Tooltip (`BreakoutStrategy/UI/charts/components/score_tooltip.py`, L130-140)

---

## 概述

系统共定义 **9 种突破模式**，由 `BreakoutScorer._classify_pattern()` 在评分完成后自动分类。分类依据是各 [Bonus](bonus_system_guide.md) 因子的触发级别 (level)，不影响评分本身，仅作为下游策略的维度标签。

**分类优先级**: 混合模式 > 单一模式 > 兜底模式

在 UI 中，模式标签以 `[pattern_name]` 格式显示在 Score Detail Tooltip 的标题栏右侧（`basic` 模式不显示）。

### UI 缩写对照表

图表突破标记上以缩写形式显示模式标签（如 "72 MOM"），定义于 `markers.py:144-152`：

| 模式名称 | 缩写 |
|----------|------|
| `momentum` | **MOM** |
| `historical` | **HIST** |
| `volume_surge` | **VOL** |
| `dense_test` | **TEST** |
| `trend_continuation` | **TREND** |
| `deep_rebound` | **D.REB** |
| `power_historical` | **P.HIST** |
| `grind_through` | **GRIND** |
| `basic` | _(不显示)_ |

---

## 维度代号说明

文档使用 A-F 代号来简称各评分维度，混合模式用 `+` 连接表示多维度同时满足：

| 代号 | 维度名称 | 对应 Bonus 因子 | 核心含义 |
|------|---------|----------------|---------|
| **A** | 势能 | [PK-Mom](bonus_system_guide.md#11-pk-momentum-bonuspeak-凹陷深度) (pk_momentum) | 近期 peak 后的凹陷深度，反映 V 型反弹力度 |
| **B** | 历史 | [Age](bonus_system_guide.md#1-age-bonus阻力年龄) (oldest_age) | 被突破峰值的存在时长，反映阻力位的历史意义 |
| **C** | 放量 | [Volume](bonus_system_guide.md#5-volume-bonus突破放量) (volume_surge_ratio) | 突破日成交量相对均量的放大倍数 |
| **D** | 测试 | [Tests](bonus_system_guide.md#2-test-bonus测试次数) (test_count) | 阻力簇内被测试的峰值数量，反映阻力位被试探次数 |
| **E** | 连续 | [Streak](bonus_system_guide.md#7-streak-bonus连续突破) (recent_breakout_count) | 近期窗口内连续突破次数，反映趋势持续性 |
| **F** | 兜底 | — | 无特定维度触发，默认分类 |

> **示例**: `A+B` 表示"势能 + 历史"两个维度同时满足，对应 `deep_rebound`（深蹲远射）模式。

---

## 关键 Bonus 因子的 Level 定义

分类逻辑依赖以下 5 个 Bonus 的 `level` 值：

| Bonus 名称 | Level 0 (未触发) | Level 1 | Level 2 | Level 3 |
|------------|-----------------|---------|---------|---------|
| [**PK-Mom**](bonus_system_guide.md#11-pk-momentum-bonuspeak-凹陷深度) (近期peak凹陷深度) | pk_momentum < 1.5 | >= 1.5 | >= 2.0 | - |
| [**Age**](bonus_system_guide.md#1-age-bonus阻力年龄) (最老峰值年龄) | oldest_age < 21d | >= 21d (1月) | >= 63d (3月) | >= 252d (1年) |
| [**Tests**](bonus_system_guide.md#2-test-bonus测试次数) (测试次数/簇内峰值数) | test_count < 2 | - | >= 2 (注: level 从2起算因阈值=[2,3,4]) | >= 3 |
| [**Volume**](bonus_system_guide.md#5-volume-bonus突破放量) (突破日成交量放大倍数) | vol_ratio < 1.5x | >= 1.5x | >= 2.0x | - |
| [**Streak**](bonus_system_guide.md#7-streak-bonus连续突破) (近期连续突破次数) | count < 2 | >= 2 | >= 4 | - |

> **注**: [Tests bonus](bonus_system_guide.md#2-test-bonus测试次数) 的阈值为 [2, 3, 4]，因此 test_count=2 时 level=1，test_count=3 时 level=2。在分类逻辑中 `tests_level >= 1` 意味着至少 2 次测试，`tests_level >= 2` 意味着至少 3 次测试。

---

## 9 种突破模式详解

### 混合模式 (优先判定, 按顺序检查)

---

#### 1. deep_rebound

| 项目 | 内容 |
|------|------|
| **英文名称** | `deep_rebound` |
| **中文名称** | 深蹲远射 |
| **维度组合** | A+B（势能 + 历史） |
| **意义** | 价格在近期 peak 形成后经历深度回调（V型凹陷），随后反弹突破远期历史阻力位。结合了买方短期动能和长期格局转变，评分潜力最高。 |
| **判定条件** | `pk_mom_level >= 1` **AND** `age_level >= 2` |
| **具体阈值** | pk_momentum >= 1.5 (凹陷深度约 0.65 ATR) **且** 最老峰值年龄 >= 63 个交易日 (约 3 个月) |

**计算依据详解**:
- `pk_momentum = 1 + log(1 + D_atr)`，其中 `D_atr = (peak_price - trough_price) / ATR`
- trough_price 取 peak 和 breakout 之间区间的最低 low 价
- pk_momentum >= 1.5 意味着 D_atr >= e^0.5 - 1 ≈ 0.65 ATR 的凹陷深度
- oldest_age = breakout_index - 最老被突破峰值的 index (交易日计)

---

#### 2. power_historical

| 项目 | 内容 |
|------|------|
| **英文名称** | `power_historical` |
| **中文名称** | 放量历史突破 |
| **维度组合** | B+C（历史 + 放量） |
| **意义** | 以显著放量方式突破远期历史阻力位，通常由催化剂事件（财报、行业新闻等）驱动。强力突破叠加长期格局转变，但容易触发 [overshoot penalty](bonus_system_guide.md#8-overshoot-penalty超涨惩罚)。 |
| **判定条件** | `vol_level >= 1` **AND** `age_level >= 2` |
| **具体阈值** | 成交量放大倍数 >= 1.5x (对比前 63 日均量) **且** 最老峰值年龄 >= 63 个交易日 |

**计算依据详解**:
- volume_surge_ratio = 突破日成交量 / 过去 63 个交易日的平均成交量
- >= 1.5x 表示成交量至少放大 50%
- oldest_age 同上

---

#### 3. grind_through

| 项目 | 内容 |
|------|------|
| **英文名称** | `grind_through` |
| **中文名称** | 磨穿防线 |
| **维度组合** | B+D（历史 + 测试） |
| **意义** | 价格在远期阻力区反复测试多次后最终突破。多次测试说明阻力强度高且市场参与者充分，突破后假突破概率最低，是最稳健的突破类型。 |
| **判定条件** | `age_level >= 2` **AND** `tests_level >= 1` |
| **具体阈值** | 最老峰值年龄 >= 63 个交易日 **且** 最大阻力簇内峰值数 >= 2 |

**计算依据详解**:
- 测试次数 = 最大阻力簇内的峰值数量
- 阻力簇分组算法：贪心聚类，相邻峰值价差比例 <= 3% (cluster_density_threshold) 则归为同簇
- 簇选取策略：取峰值数量最多的簇

---

### 单一模式 (混合模式不满足时, 按顺序检查)

---

#### 4. momentum

| 项目 | 内容 |
|------|------|
| **英文名称** | `momentum` |
| **中文名称** | 势能突破 |
| **维度** | A（势能） |
| **意义** | 价格在近期 peak 形成后经历明显回调，形成"凹陷"，随后快速反弹突破。V 型反弹体现了强劲的买方力量，是短期动能驱动的突破。 |
| **判定条件** | `pk_mom_level >= 1` (且不满足任何混合模式) |
| **具体阈值** | pk_momentum >= 1.5 |

**计算依据详解**:
- pk_momentum 仅在 peak 与 breakout 间距 <= pk_lookback (默认 30 个交易日) 时计算
- 超出时间窗口返回 0.0 (不触发)
- pk_momentum = 1.0 表示有近期 peak 但无凹陷 (trough == peak)
- pk_momentum >= 1.5 表示中等凹陷 (D_atr ≈ 0.65 ATR)
- pk_momentum >= 2.0 表示深度凹陷 (D_atr ≈ 1.7 ATR)

---

#### 5. historical

| 项目 | 内容 |
|------|------|
| **英文名称** | `historical` |
| **中文名称** | 历史阻力突破 |
| **维度** | B（历史） |
| **意义** | 突破远期（至少 3 个月以上）历史阻力位，代表长期价格格局的转变。阻力位存在时间越长，突破后的意义越大（技术分析共识）。 |
| **判定条件** | `age_level >= 2` (且不满足任何混合模式) |
| **具体阈值** | 最老峰值年龄 >= 63 个交易日 (约 3 个月) |

**计算依据详解**:
- oldest_age = max(breakout_index - peak_index) for all broken_peaks
- [Age bonus](bonus_system_guide.md#1-age-bonus阻力年龄) 三级阈值: [21d, 63d, 252d] 对应 [1月, 3月, 1年]
- Level 2 要求 >= 63d，即至少 3 个月前形成的峰值

---

#### 6. volume_surge

| 项目 | 内容 |
|------|------|
| **英文名称** | `volume_surge` |
| **中文名称** | 放量爆发 |
| **维度** | C（放量） |
| **意义** | 突破日成交量显著放大，通常意味着有大量新资金入场或催化剂事件驱动。放量突破的有效性高于缩量突破（技术分析共识）。 |
| **判定条件** | `vol_level >= 1` (且不满足任何混合模式及上述单一模式) |
| **具体阈值** | 成交量放大倍数 >= 1.5x |

**计算依据详解**:
- volume_surge_ratio = 突破日 volume / mean(volume[idx-63 : idx])
- 使用过去 63 个交易日（约 3 个月）作为均量基准
- >= 1.5x 为 Level 1，>= 2.0x 为 Level 2
- 数据不足时（上市不满 63 天），使用实际可用数据计算均值

---

#### 7. dense_test

| 项目 | 内容 |
|------|------|
| **英文名称** | `dense_test` |
| **中文名称** | 密集测试 |
| **维度** | D（测试） |
| **意义** | 阻力位被多次测试后突破。密集测试表明多次试探形成了坚实的阻力/支撑转换区间，突破后该区间转为强支撑，假突破概率低。 |
| **判定条件** | `tests_level >= 2` (且不满足上述模式) |
| **具体阈值** | 最大阻力簇内峰值数 >= 3 |

**计算依据详解**:
- [Tests bonus](bonus_system_guide.md#2-test-bonus测试次数) 阈值: [2, 3, 4] 对应 Level [1, 2, 3]
- `tests_level >= 2` 要求 test_count >= 3，即至少 3 个峰值在同一阻力簇内
- 阻力簇判定：将所有被突破峰值按价格排序，相邻峰值价差/较低价 <= 3% 则归为同簇
- **注意**: 此模式要求 Level 2 (>=3次)，不同于 grind_through 混合模式中对 tests 的要求 (Level 1, >=2次)

---

#### 8. trend_continuation

| 项目 | 内容 |
|------|------|
| **英文名称** | `trend_continuation` |
| **中文名称** | 趋势延续 |
| **维度** | E（连续） |
| **意义** | 短期内连续发生多次突破，呈现阶梯式上涨态势。连续突破表明趋势强劲、多方力量持续占优，适合趋势跟踪策略。 |
| **判定条件** | `streak_level >= 1` (且不满足上述模式) |
| **具体阈值** | 近期连续突破次数 >= 2 (在 streak_window 内) |

**计算依据详解**:
- recent_breakout_count = streak_window (默认 20 个交易日) 内的突破次数（包括当前突破）
- 由 `BreakoutDetector.get_recent_breakout_count()` 计算
- 历史突破记录维护在 `breakout_history: List[BreakoutRecord]` 中
- [Streak bonus](bonus_system_guide.md#7-streak-bonus连续突破) 阈值: [2, 4] 对应 Level [1, 2]
- Level 1: >= 2 次 (20 个交易日内至少还有 1 次前序突破)
- Level 2: >= 4 次 (20 个交易日内至少还有 3 次前序突破)

---

### 兜底模式

---

#### 9. basic

| 项目 | 内容 |
|------|------|
| **英文名称** | `basic` |
| **中文名称** | 基础突破 |
| **维度** | F（兜底） |
| **意义** | 未触发任何特定模式条件的普通突破。可能是近期小幅度阻力位的低量突破，不具有显著特征，但仍通过了基本突破检测条件。 |
| **判定条件** | 上述 8 种模式均不满足 |
| **具体阈值** | 无额外条件。即: pk_mom_level=0 且 age_level<2 且 vol_level=0 且 tests_level<2 且 streak_level=0 |

**计算依据详解**:
- 不满足任何模式条件时的默认分类
- 在 UI 中 Score Detail Tooltip 不显示 `basic` 标签 (L130: `if breakdown.pattern_label and breakdown.pattern_label != "basic"`)
- 评分仅基于 base_score (50) 乘以可能触发的低级别 bonus

---

## 分类优先级流程图

```
                     START
                       |
         pk_mom_level>=1 AND age_level>=2 ?
            YES -> "deep_rebound" (A势能+B历史)
            NO  |
         vol_level>=1 AND age_level>=2 ?
            YES -> "power_historical" (B历史+C放量)
            NO  |
         age_level>=2 AND tests_level>=1 ?
            YES -> "grind_through" (B历史+D测试)
            NO  |
         pk_mom_level>=1 ?
            YES -> "momentum" (A势能)
            NO  |
         age_level>=2 ?
            YES -> "historical" (B历史)
            NO  |
         vol_level>=1 ?
            YES -> "volume_surge" (C放量)
            NO  |
         tests_level>=2 ?
            YES -> "dense_test" (D测试)
            NO  |
         streak_level>=1 ?
            YES -> "trend_continuation" (E连续)
            NO  |
         "basic" (F兜底)
```

---

## 模式间关系

### 互斥关系
- **momentum (A势能) vs trend_continuation (E连续)**: 强互斥。势能突破需要凹陷回调 (pk_momentum)，而趋势延续需要连续上涨 (streak)，两者在价格形态上矛盾。
- **deep_rebound (A势能+B历史) vs power_historical (B历史+C放量)**: 互斥于优先级判定顺序（deep_rebound 优先检查）。

### 叠加关系 (混合模式)
- **A势能+B历史 = deep_rebound**: 势能 + 历史，评分潜力最高
- **B历史+C放量 = power_historical**: 历史 + 放量，催化剂驱动的长期格局突破
- **B历史+D测试 = grind_through**: 历史 + 测试，最稳健的突破类型

### 包含关系
- 所有混合模式都包含 **age_level >= 2**（即 B历史维度的条件），因此 B历史 是混合模式的共同基础。

---

## 相关源码位置

| 内容 | 文件路径 | 行号 |
|------|---------|------|
| 分类主逻辑 | `BreakoutStrategy/analysis/breakout_scorer.py` | L754-803 |
| Bonus Level 计算 | `BreakoutStrategy/analysis/breakout_scorer.py` | L282-311 |
| 各 Bonus 阈值配置 | `BreakoutStrategy/analysis/breakout_scorer.py` | L117-188 |
| pk_momentum 计算 | `BreakoutStrategy/analysis/features.py` | L394-443 |
| volume_surge_ratio 计算 | `BreakoutStrategy/analysis/features.py` | L213-247 |
| streak 计算 | `BreakoutStrategy/analysis/breakout_detector.py` | L640-664 |
| 阻力簇分组 | `BreakoutStrategy/analysis/breakout_scorer.py` | L229-276 |
| UI 展示 (Tooltip) | `BreakoutStrategy/UI/charts/components/score_tooltip.py` | L130-140 |
| PoolEntry 存储 | `BreakoutStrategy/simple_pool/models.py` | L33 |
| 生产环境配置 | `configs/params/scan_params.yaml` | - |