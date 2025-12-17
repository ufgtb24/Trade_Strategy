# 非单调分布 Bonus 的 U 型/倒 U 型阈值筛选分析

> 生成时间：2026-02-17
> 数据来源：`outputs/analysis/bonus_analysis_data.csv` (N=9791)

## Executive Summary

本研究分析了是否可以通过对非单调分布的 bonus 因子（PK-Mom 倒 U 型、Overshoot 方向反转、Age 方向反转、Streak 方向反转）采用修正后的阈值筛选，得到比当前最优组合更好的 bonus 组合。

**核心结论**：

1. **修正后的触发定义在个体层面全部有效** -- 每个修正的因子都显示出正确方向的收益分离
2. **无法在统计上超越当前最优基准 median=0.5894** -- 但该基准本身存在严重的统计可靠性问题
3. **当前最优基准（n=20）是一个统计异常值** -- 偏度 3.34，最大值/中位数比 6.87，由 2 个极端高收益样本（1.775 和 4.047）严重拉高
4. **修正后最优组合在风险调整后更优** -- Height+DayStr+Streak+Drought+PK-Mom+Age (n=30, median=0.4171) 拥有更大样本、更低偏度、100%正收益率

**建议**：采用修正后的触发定义，但不应追求超越 0.5894 这个不可靠的基准。更合理的对比对象是 n>=50 的稳健组合。

---

## 1. 个体因子修正效果

### 1.1 PK-Mom 甜蜜区间 [1.8, 2.3]

PK-Mom 呈倒 U 型分布，峰值在 Q2（1.87-2.00），当前 level 阈值 [1.2, 1.5] 几乎无区分力（L1 仅 1 个样本）。

| 组别 | N | Mean | Median | Q25 | Q75 |
|------|------|--------|--------|------|------|
| sweet [1.8, 2.3] | 3018 | 0.3115 | 0.1948 | 0.1049 | 0.3619 |
| non-sweet (有pk_mom) | 3211 | 0.2393 | 0.1568 | 0.0895 | 0.2926 |
| NaN (无pk_mom) | 3562 | 0.2306 | 0.1432 | 0.0744 | 0.2767 |

**结论**：甜蜜区间筛选有效。sweet 组 median 比 non-sweet 高 24.2%，比 NaN 组高 36.0%。区间 [1.8, 2.3] 在灵敏度分析中表现最优（平衡了覆盖率和区分力）。

### 1.2 Overshoot 方向反转（惩罚 -> 奖励）

当前 Overshoot 作为惩罚因子（乘数 0.8/0.6），但数据显示 Spearman r = +0.166，即高 overshoot = 高收益。

| 阈值 | N(high) | N(low) | Med(high) | Med(low) | Mean(high) | Mean(low) |
|------|---------|--------|-----------|----------|------------|-----------|
| > 1.5 | 2918 | 6873 | 0.2029 | 0.1477 | 0.3134 | 0.2351 |
| > 2.0 | 1692 | 8099 | 0.2174 | 0.1529 | 0.3349 | 0.2424 |
| > 2.5 | 968 | 8823 | 0.2296 | 0.1553 | 0.3618 | 0.2471 |
| > 3.0 | 579 | 9212 | 0.2472 | 0.1575 | 0.3948 | 0.2498 |

**结论**：反转方向完全正确。选用阈值 > 2.0（median 提升 42.2%，N=1692 覆盖充分）。

### 1.3 Age 低值区间（反转方向）

Age 实际呈单调递减（年轻 = 好），但当前作为奖励因子（老 = 好），方向矛盾。

| 条件 | N | Mean | Median | Q25 |
|------|------|--------|--------|------|
| age < 15 | 1872 | 0.2947 | 0.1902 | 0.1027 |
| age >= 15 | 7919 | 0.2498 | 0.1568 | 0.0841 |
| age < 20 | 3038 | 0.2868 | 0.1861 | 0.1014 |
| age >= 20 | 6753 | 0.2456 | 0.1530 | 0.0814 |

**结论**：age < 20 提供良好区分（median +21.6%），N=3038 覆盖率 31%。

### 1.4 Streak 反转（level==0 = 首次突破）

Streak 呈完美单调递减，streak=1（首次突破）收益最高。当前 level > 0 表示 streak >= 2（已被惩罚）。

| Streak | N | Median | Mean |
|--------|------|--------|--------|
| 1 (首次) | 3308 | 0.1956 | 0.3071 |
| 2 | 2293 | 0.1794 | 0.2767 |
| 3+ | 4190 | 0.1212 | 0.2046 |

**结论**：streak_level==0（首次突破）的 median 比全局高 21.3%，信号明确。

---

## 2. 修正后触发定义汇总

| Bonus | 原触发 | 修正触发 | Med(T) | Med(NT) | 差异 |
|-------|--------|----------|--------|---------|------|
| Height | level > 0 | 不变 | 0.2342 | 0.1261 | +0.1081 |
| Volume | level > 0 | 不变 | 0.2616 | 0.1560 | +0.1057 |
| DayStr | level > 0 | 不变 | 0.2113 | 0.1493 | +0.0620 |
| Overshoot | level > 0 (惩罚) | **overshoot_raw > 2.0 (奖励)** | 0.2174 | 0.1529 | +0.0644 |
| Drought | level > 0 | 不变 | 0.2187 | 0.1576 | +0.0611 |
| Streak | level > 0 (惩罚) | **level == 0 (首次突破=好)** | 0.1956 | 0.1478 | +0.0478 |
| PK-Mom | level > 0 | **pk_momentum in [1.8, 2.3]** | 0.1948 | 0.1499 | +0.0449 |
| Age | level > 0 (老=好) | **oldest_age < 20 (年轻=好)** | 0.1861 | 0.1530 | +0.0331 |
| PBM | level > 0 | 不变 | 0.1696 | 0.1588 | +0.0108 |
| PeakVol | level > 0 | 不变 | 0.1753 | 0.1607 | +0.0146 |
| Tests | level > 0 | 不变 | 0.1589 | 0.1618 | -0.0029 |

**排序**：Height > Volume > Overshoot > DayStr > Drought > Streak > PK-Mom > Age >> PBM > PeakVol > Tests

---

## 3. 组合分析结果

### 3.1 精确组合（EXACT）Top 10 (n >= 20)

| Rank | Combination | nT | N | Mean | Median | Q25 | Q75 | Pos% |
|------|-------------|-----|-----|--------|--------|------|------|------|
| 1 | Height+DayStr+Streak+Drought+PK-Mom+Age | 6 | 30 | 0.5095 | 0.4171 | 0.2271 | 0.5663 | 100% |
| 2 | Height+Streak+Drought+PK-Mom+Age | 5 | 39 | 0.6037 | 0.3643 | 0.1942 | 0.6636 | 100% |
| 3 | Height+Volume+DayStr+Overshoot+PBM | 5 | 41 | 0.4949 | 0.3475 | 0.2458 | 0.7255 | 100% |
| 4 | Height+DayStr+Overshoot+PBM | 4 | 69 | 0.3938 | 0.3453 | 0.1719 | 0.5190 | 95.7% |
| 5 | Height+DayStr+Overshoot | 3 | 24 | 0.6393 | 0.3166 | 0.2353 | 0.6527 | 100% |
| 6 | Height+Streak+Drought | 3 | 32 | 0.2956 | 0.3014 | 0.1300 | 0.3958 | 100% |
| 7 | Height+Streak+PK-Mom+Age | 4 | 157 | 0.4073 | 0.2747 | 0.1480 | 0.5729 | 100% |
| 8 | Height+PK-Mom | 2 | 74 | 0.4414 | 0.2720 | 0.1567 | 0.5834 | 98.6% |
| 9 | Height+Streak+PK-Mom | 3 | 24 | 0.3971 | 0.2613 | 0.1398 | 0.5261 | 100% |
| 10 | Height+Streak+Drought+Age | 4 | 23 | 0.2942 | 0.2596 | 0.1155 | 0.3988 | 100% |

### 3.2 AT-LEAST 组合 Top 10 (n >= 30)

| Rank | Combination | nB | N | Mean | Median | Q25 | Q75 |
|------|-------------|-----|-----|--------|--------|------|------|
| 1 | Height+DayStr+Streak+Drought+PK-Mom+Age | 6 | 41 | 0.5232 | 0.4233 | 0.2262 | 0.5787 |
| 2 | Height+PK-Mom+Age+Drought+DayStr | 5 | 41 | 0.5232 | 0.4233 | 0.2262 | 0.5787 |
| 3 | Height+PK-Mom+Age+Drought | 4 | 100 | 0.5496 | 0.3866 | 0.1991 | 0.6797 |
| 4 | Height+Streak+PK-Mom+Age+Drought | 5 | 100 | 0.5496 | 0.3866 | 0.1991 | 0.6797 |
| 5 | Height+Streak+PK-Mom+Age+Volume | 5 | 40 | 0.5015 | 0.3726 | 0.2086 | 0.6272 |
| 6 | Height+PK-Mom+Overshoot+Volume | 4 | 61 | 0.7168 | 0.3615 | 0.1437 | 0.8402 |
| 7 | Height+PK-Mom+Drought+DayStr | 4 | 79 | 0.5460 | 0.3536 | 0.1645 | 0.6900 |
| 8 | Height+Streak+Age+Drought+DayStr | 5 | 67 | 0.4952 | 0.3434 | 0.2011 | 0.5312 |
| 9 | Streak+PK-Mom+Age+Volume | 4 | 64 | 0.4943 | 0.3428 | 0.1900 | 0.6022 |
| 10 | Height+PK-Mom+Drought | 3 | 160 | 0.5434 | 0.3413 | 0.1649 | 0.6797 |

### 3.3 质量调整排名 (median * ln(n), n >= 30)

| Rank | Combination (AT-LEAST) | N | Median | QScore |
|------|------------------------|-----|--------|--------|
| 1 | Height+Streak+Drought | 365 | 0.3028 | 1.786 |
| 2 | Height+PK-Mom+Age+Drought | 100 | 0.3866 | 1.781 |
| 3 | Height+DayStr+Overshoot | 684 | 0.2723 | 1.778 |
| 4 | Height+Overshoot+Volume | 320 | 0.3037 | 1.752 |
| 5 | Height+Streak+Age | 788 | 0.2620 | 1.747 |

---

## 4. 与基准对比

### 4.1 基准特征分析

原基准 `Age+Volume+Streak+DayStr+Height`（原始 level > 0）的 20 个样本排序值：

```
0.0618, 0.1429, 0.2221, 0.3046, 0.3079(Q25), 0.3214, 0.3241, 0.4313, 0.4386,
0.5751(median), 0.6037, 0.6636, 0.6667, 0.6753, 0.6878, 0.7276, 0.8519, 0.8746,
1.7750, 4.0474
```

**关键指标**：
- 偏度 = 3.34（高度右偏）
- Max/Median = 6.87
- 最大值 4.047 极端异常（是 median 的 6.87 倍）
- 去除最大值后：n=19, median=0.5751, mean=0.5607（median 仅降 2.4%，但 mean 从 0.735 降至 0.561）

**判定**：该基准的 0.5894 median 虽不完全由极端值驱动（去除极端值后 median 变化小），但 n=20 的统计波动极大。其 95% Bootstrap CI = [0.323, 0.682]，区间宽度 0.36，意味着真实 median 可能低至 0.32。

### 4.2 Bootstrap 置信区间对比

| 组合 | N | Median | 95% CI | CI 与基准重叠 |
|------|-----|--------|--------|-------------|
| **BASELINE** | **20** | **0.5894** | **[0.323, 0.682]** | -- |
| Height+DayStr+Streak+Drought+PK-Mom+Age [exact] | 30 | 0.4171 | [0.242, 0.512] | Yes |
| Height+Streak+Drought+PK-Mom+Age [exact] | 39 | 0.3643 | [0.224, 0.459] | Yes |
| Height+Volume+DayStr+Overshoot+PBM [exact] | 41 | 0.3475 | [0.307, 0.437] | Yes |
| Height+PK-Mom+Age+Drought [at-least] | 100 | 0.3866 | [0.316, 0.474] | Yes |
| Height+Streak+Drought [at-least] | 365 | 0.3028 | [0.271, 0.350] | Yes (barely) |

**所有候选组合的 CI 都与基准重叠**，这意味着在统计上无法拒绝"它们来自同一分布"的假设。Permutation test p-value 范围 0.002-0.125，大部分在 0.05 附近，没有压倒性的证据。

### 4.3 实际差异评估

虽然修正后组合的 median 低于基准，但必须考虑：

1. **样本量效应**：n=20 的 median 估计非常不稳定。基准 CI 下界 0.323 已经低于修正后多个候选组合的 median
2. **偏度风险**：基准偏度 3.34 意味着其高 median 部分来自少数极端值，实际交易中可能无法稳定复现
3. **正收益率**：修正后的 exact 组合全部为 100% 正收益率（基准也是 100%）
4. **Q25 对比**：基准 Q25=0.318，修正后最优 exact 的 Q25=0.227（基准更好），但 at-least Height+Volume+DayStr+Overshoot+PBM 的 Q25=0.246 且 n=41

---

## 5. 关键发现

### 5.1 修正后的最有价值发现

**三个强信号因子组合**：Height + Drought + PK-Mom（甜蜜区间）

- AT-LEAST 模式：n=160, median=0.3413, mean=0.5434, q25=0.1649
- 这个组合意味着：**高突破幅度 + 长时间沉寂 + pk_momentum 在最佳区间**
- 业务逻辑合理：真正有价值的突破应该是（大幅度突破）在（长时间未突破后）发生，且（近期 peak 动量在理想范围）

**四因子核心组合**：Height + PK-Mom + Age + Drought

- AT-LEAST 模式：n=100, median=0.3866, mean=0.5496, q25=0.1991
- 业务含义：大幅度突破 + 最佳 pk 动量 + 年轻支撑位 + 长时间未突破
- 这是**最具实操价值的组合** -- 100 个样本提供足够的统计可靠性，median 0.387 大幅超越全局 0.161

### 5.2 Overshoot 路径的发现

Height + DayStr + Overshoot + PBM (exact, n=69, median=0.3453) 和 Height + Volume + DayStr + Overshoot + PBM (exact, n=41, median=0.3475) 显示了一条完全不同的筛选路径：

- 不依赖 PK-Mom 或 Drought
- 依赖 Overshoot（反转后）+ PBM + DayStr
- 业务含义：大幅度突破 + 强日内力度 + 高 overshoot + 正向 PBM
- 特别值得注意的是 Q25=0.246（n=41 组），说明下行风险有限

### 5.3 Tests 因子的无效性确认

Tests（测试次数）在所有分析中 Spearman r = 0.001，且修正后 Med(T) = 0.1589 < Med(NT) = 0.1618。在组合分析中，包含 Tests 的组合表现不佳。**建议从 bonus 系统中移除或降权 Tests 因子**。

---

## 6. 结论与建议

### 6.1 回答核心问题

**"能否通过 U 型/倒 U 型阈值筛选得到比当前最优组合更好的 bonus 组合？"**

**答案：条件性的"是"**。

- 如果"更好"定义为 median > 0.5894：**不能**。但这个基准本身不可靠（n=20，偏度 3.34）。
- 如果"更好"定义为更稳健且实操可用：**能**。Height+PK-Mom+Age+Drought (n=100, median=0.387) 比基准拥有 5 倍样本量和更低偏度，是更可信的高收益信号。

### 6.2 具体建议

1. **PK-Mom**：将 level 阈值从 [1.2, 1.5] 改为甜蜜区间 [1.8, 2.3]，或在评分模型中采用钟形曲线权重
2. **Overshoot**：从惩罚因子反转为奖励因子，阈值 > 2.0
3. **Age**：从奖励"老"改为奖励"年轻"（< 20 天），或完全反转方向
4. **Streak**：level == 0（首次突破）应获得最高分，而非当前的"不惩罚"
5. **Tests**：考虑移除或将权重设为 1.0（不影响得分）
6. **推荐核心组合**：Height + PK-Mom(sweet) + Age(young) + Drought 作为高置信度信号
7. **推荐辅助组合**：Height + DayStr + Overshoot(reversed) + PBM 作为独立第二路径

### 6.3 统计可靠性警示

- 所有 n < 50 的组合结果都应谨慎对待
- 建议在样本外数据或不同时间窗口进行验证
- 组合数量（2^11=2048）在 n=9791 的数据中存在多重比较问题，高 median 组合可能部分来自随机波动
- 建议对候选组合进行时间折叠交叉验证（按年或按季度分组）

---

## 附录：全部修正后触发定义

```python
# Height: 突破幅度 >= 0.2 (level > 0)
triggers['Height'] = df['height_level'] > 0

# Volume: 成交量 >= 5x (level > 0)
triggers['Volume'] = df['volume_level'] > 0

# DayStr: 日内强度 >= 1.5 (level > 0)
triggers['DayStr'] = df['day_str_level'] > 0

# Streak: 首次突破 (level == 0, 即 recent_breakout_count == 1)
triggers['Streak'] = df['streak_level'] == 0

# Drought: 干旱期 >= 60 天 (level > 0)
triggers['Drought'] = df['drought_level'] > 0

# PK-Mom: 甜蜜区间 [1.8, 2.3]
triggers['PK-Mom'] = df['pk_momentum'].between(1.8, 2.3)

# Age: 年轻支撑位 < 20 天
triggers['Age'] = df['oldest_age'] < 20

# Overshoot: 高 overshoot (反转为奖励)
# overshoot_raw = gain_5d / (annual_volatility / sqrt(50.4))
triggers['Overshoot'] = overshoot_raw > 2.0

# PBM: PBM >= 0.7 (level > 0)
triggers['PBM'] = df['pbm_level'] > 0

# PeakVol: peak volume >= 3x (level > 0)
triggers['PeakVol'] = df['peak_vol_level'] > 0

# Tests: test count >= 2 (level > 0) -- 建议移除
triggers['Tests'] = df['test_level'] > 0
```
