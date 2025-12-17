# Bonus Combination Analysis Report

Sample size: **9791** breakout events

> 本报告分析各种 Bonus（加分因子）对突破后股价表现的影响。每个 Bonus 代表突破发生时的一个有利特征（如放量、历史阻力密集等），level 越高表示该特征越突出。我们想知道：哪些特征真正预示了更好的突破后涨幅？哪些组合效果最佳？

## 0. Label Overview (label_10_40)

> **label_10_40** 是突破后的实际涨幅，具体含义是突破后第10~40个交易日内的最大收益（相对突破价格的倍数）。它是我们衡量"突破质量好不好"的标尺。下方表格展示了所有突破事件涨幅的基本统计：
> - **Mean（均值）**：所有突破的平均涨幅
> - **Median（中位数）**：排在正中间的涨幅，比均值更能反映"典型"水平（不受极端值影响）
> - **Std（标准差）**：涨幅的波动程度，越大说明结果越分散、不确定性越高
> - **Min / Max**：最差和最好的情况

| Metric | Value |
| --- | --- |
| Mean | 0.2584 |
| Median | 0.1613 |
| Std | 0.3309 |
| Min | -0.1478 |
| Max | 4.9415 |

## 1. Single Factor Analysis

> **目的**：逐个考察每个 Bonus 因子，看它单独对涨幅有没有影响、影响有多大。就像体检逐项检查一样，先弄清每个因子的"单兵作战能力"。

### 1.1 Spearman Correlation (bonus level vs label)

> **Spearman 相关系数**衡量两个变量之间的单调关系（即"一个变大，另一个是否也倾向于变大"），不要求两者是线性关系，适合我们这种 level 是离散等级的数据。
> - **spearman_r**：相关系数，范围 -1 到 1。正值表示 bonus level 越高，涨幅越好；负值表示反而越差。绝对值越大关联越强
> - **p_value**：这个关联"碰巧出现"的概率。p 值越小，说明结果越可信。带星号 \* 的表示统计上显著（不太可能是偶然）
> - 实操参考：r > 0 且带 \*\*\* 的因子是值得关注的正面信号

| bonus | spearman_r | p_value | significance |
| --- | --- | --- | --- |
| Height | 0.3044 | 0.0000 | *** |
| DayStr | 0.1590 | 0.0000 | *** |
| Volume | 0.1320 | 0.0000 | *** |
| PK-Mom | 0.0962 | 0.0000 | *** |
| Drought | 0.0918 | 0.0000 | *** |
| PBM | 0.0396 | 0.0001 | *** |
| Streak | -0.1936 | 0.0000 | *** |
| Age | - | - |  |
| Tests | - | - |  |
| Overshoot | - | - |  |
| PeakVol | - | - |  |

> \* p<0.05, \*\* p<0.01, \*\*\* p<0.001

### 1.2 Label Distribution by Bonus Level

> 下面逐个展示每个 Bonus 在不同 level 下的涨幅分布。每张表的列含义：
> - **level**：该 Bonus 的等级（0 = 未触发，1/2/3 = 逐级增强）
> - **count**：该等级的样本数量
> - **mean / median**：该等级下突破后涨幅的平均值和中位数。重点看 median，它不受极端值干扰
> - **q25 / q75**：25% 分位和 75% 分位，表示"中间 50% 的突破"涨幅区间。区间越窄说明结果越稳定
>
> **怎么看**：如果某个 Bonus 的 level 从 0 → 1 → 2 时 median 明显递增，说明这个因子越强、突破后表现越好。

#### Age

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9791.0000 | 0.2584 | 0.1613 | 0.3309 | 0.0873 | 0.3101 |


#### Tests

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9791.0000 | 0.2584 | 0.1613 | 0.3309 | 0.0873 | 0.3101 |


#### Volume

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9064.0000 | 0.2434 | 0.1560 | 0.2958 | 0.0851 | 0.2998 |
| 1.0000 | 387.0000 | 0.4377 | 0.2365 | 0.6320 | 0.1333 | 0.4381 |
| 2.0000 | 340.0000 | 0.4558 | 0.2800 | 0.5351 | 0.1484 | 0.5575 |


#### PK-Mom

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 3564.0000 | 0.2307 | 0.1433 | 0.2882 | 0.0744 | 0.2763 |
| 1.0000 | 1.0000 | 0.0345 | 0.0345 | - | 0.0345 | 0.0345 |
| 2.0000 | 6226.0000 | 0.2743 | 0.1731 | 0.3521 | 0.0959 | 0.3272 |


#### Streak

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 3308.0000 | 0.3071 | 0.1956 | 0.3883 | 0.1045 | 0.3615 |
| 1.0000 | 3741.0000 | 0.2684 | 0.1732 | 0.3262 | 0.0947 | 0.3247 |
| 2.0000 | 2742.0000 | 0.1860 | 0.1128 | 0.2364 | 0.0666 | 0.2309 |


#### PBM

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 6923.0000 | 0.2570 | 0.1588 | 0.3393 | 0.0855 | 0.3023 |
| 1.0000 | 1898.0000 | 0.2481 | 0.1606 | 0.2932 | 0.0887 | 0.3118 |
| 2.0000 | 970.0000 | 0.2889 | 0.1952 | 0.3391 | 0.0988 | 0.3592 |


#### Overshoot

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9791.0000 | 0.2584 | 0.1613 | 0.3309 | 0.0873 | 0.3101 |


#### DayStr

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 7428.0000 | 0.2345 | 0.1493 | 0.2960 | 0.0816 | 0.2829 |
| 1.0000 | 1345.0000 | 0.3147 | 0.2004 | 0.3964 | 0.1072 | 0.3818 |
| 2.0000 | 1018.0000 | 0.3587 | 0.2282 | 0.4343 | 0.1262 | 0.4129 |


#### PeakVol

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9791.0000 | 0.2584 | 0.1613 | 0.3309 | 0.0873 | 0.3101 |


#### Drought

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 9022.0000 | 0.2506 | 0.1576 | 0.3192 | 0.0855 | 0.3019 |
| 1.0000 | 306.0000 | 0.3753 | 0.2520 | 0.4145 | 0.1289 | 0.4429 |
| 2.0000 | 323.0000 | 0.3221 | 0.2127 | 0.4030 | 0.1108 | 0.4009 |
| 3.0000 | 140.0000 | 0.3620 | 0.1862 | 0.5420 | 0.0998 | 0.4430 |


#### Height

| level | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | 5429.0000 | 0.1920 | 0.1261 | 0.2347 | 0.0720 | 0.2289 |
| 1.0000 | 3347.0000 | 0.3119 | 0.2146 | 0.3554 | 0.1089 | 0.3728 |
| 2.0000 | 803.0000 | 0.4166 | 0.2647 | 0.5153 | 0.1535 | 0.4910 |
| 3.0000 | 212.0000 | 0.5158 | 0.3394 | 0.5755 | 0.1826 | 0.6159 |


## 2. Pattern Analysis

> **目的**：看不同"突破模式"（pattern）之间表现有没有差异。每次突破会被自动归类为一种模式（如 power_historical、momentum 等），这里检验这些分类是否真的对应不同的涨幅水平。

### 2.1 Label by Pattern

> 各模式按中位数涨幅从高到低排列。重点关注 count 较大（样本充足）且 median 较高的模式。

| pattern | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- |
| power_breakout | 190 | 0.5655 | 0.3143 | 0.7313 | 0.1910 | 0.6561 |
| deep_rebound | 590 | 0.4152 | 0.2727 | 0.4877 | 0.1540 | 0.4945 |
| high_resistance | 235 | 0.3891 | 0.2581 | 0.4100 | 0.1492 | 0.5295 |
| volume_surge | 176 | 0.3719 | 0.2244 | 0.4246 | 0.1224 | 0.4371 |
| momentum | 5516 | 0.2531 | 0.1618 | 0.3114 | 0.0916 | 0.3035 |
| dormant_breakout | 102 | 0.2202 | 0.1594 | 0.1940 | 0.0845 | 0.3101 |
| trend_continuation | 2655 | 0.2011 | 0.1283 | 0.2328 | 0.0689 | 0.2485 |
| basic | 327 | 0.2094 | 0.1261 | 0.2984 | 0.0677 | 0.2601 |


### 2.2 Kruskal-Wallis Test (global non-parametric ANOVA)

> **Kruskal-Wallis 检验**回答一个问题："这些模式之间的涨幅差异是真实的，还是随机波动造成的假象？"
> - **H statistic**：差异程度的量化值，越大说明组间差距越明显
> - **p-value**：如果 p < 0.05（带 \*），说明至少有两个模式之间存在统计上显著的差异；如果 p > 0.05，则各模式的差异可能只是噪音

- H statistic: 522.6818
- p-value: 0.0000 ***

### 2.3 Pairwise Mann-Whitney U Tests (patterns with n>=20)

> 上面是"整体有没有差异"，这里进一步两两比较，找出具体是哪两个模式之间不同。
> - **Mann-Whitney U 检验**：比较两组数据谁的值倾向于更大，不需要数据服从正态分布
> - p_value 带 \* 的行表示这两个模式之间的涨幅差异是显著的

| pattern_a | pattern_b | u_stat | p_value | significance |
| --- | --- | --- | --- | --- |
| deep_rebound | trend_continuation | 1126935.0000 | 0.0000 | *** |
| deep_rebound | momentum | 2144394.5000 | 0.0000 | *** |
| power_breakout | trend_continuation | 385176.0000 | 0.0000 | *** |
| deep_rebound | basic | 138721.0000 | 0.0000 | *** |
| high_resistance | trend_continuation | 442012.5000 | 0.0000 | *** |
| momentum | trend_continuation | 8373536.5000 | 0.0000 | *** |
| power_breakout | basic | 47432.0000 | 0.0000 | *** |
| power_breakout | momentum | 745289.5000 | 0.0000 | *** |
| high_resistance | basic | 54310.0000 | 0.0000 | *** |
| high_resistance | momentum | 840062.0000 | 0.0000 | *** |
| volume_surge | trend_continuation | 310492.0000 | 0.0000 | *** |
| power_breakout | dormant_breakout | 13990.5000 | 0.0000 | *** |
| volume_surge | basic | 38207.5000 | 0.0000 | *** |
| deep_rebound | dormant_breakout | 40446.0000 | 0.0000 | *** |
| high_resistance | dormant_breakout | 15842.0000 | 0.0000 | *** |
| volume_surge | momentum | 583497.0000 | 0.0000 | *** |
| momentum | basic | 1030367.0000 | 0.0000 | *** |
| power_breakout | volume_surge | 20434.5000 | 0.0002 | *** |
| volume_surge | dormant_breakout | 10968.5000 | 0.0020 | ** |
| power_breakout | deep_rebound | 63228.0000 | 0.0079 | ** |
| power_breakout | high_resistance | 25583.5000 | 0.0097 | ** |
| dormant_breakout | trend_continuation | 153615.5000 | 0.0210 | * |
| dormant_breakout | basic | 18997.0000 | 0.0339 | * |
| deep_rebound | volume_surge | 57338.5000 | 0.0355 | * |
| high_resistance | volume_surge | 22504.5000 | 0.1259 |  |
| deep_rebound | high_resistance | 70197.0000 | 0.7779 |  |
| momentum | dormant_breakout | 284644.0000 | 0.8376 |  |
| trend_continuation | basic | 434350.0000 | 0.9860 |  |


## 3. Combination Analysis (Core)

> **目的**：这是报告的核心部分。单个因子的影响可能不大，但多个因子同时出现时可能产生"共振"效应。这里把每个 Bonus 简化为"有/无"（level > 0 即算触发），然后统计每种触发组合对应的涨幅表现。

Total unique combinations: 92

Combinations with n >= 20: 45

### 3.1 Label by Number of Triggered Bonuses

> 最简单的问题："触发的 Bonus 越多，表现是否越好？"下表按触发数量汇总涨幅。如果 median 随触发数量递增，说明"多因子共振"确实有效。

| n_triggered | count | mean | median |
| --- | --- | --- | --- |
| 0.0000 | 145.0000 | 0.1508 | 0.1136 |
| 1.0000 | 1807.0000 | 0.1797 | 0.1186 |
| 2.0000 | 3407.0000 | 0.2248 | 0.1434 |
| 3.0000 | 2891.0000 | 0.2887 | 0.1881 |
| 4.0000 | 1223.0000 | 0.3599 | 0.2377 |
| 5.0000 | 295.0000 | 0.4580 | 0.2714 |
| 6.0000 | 23.0000 | 0.3436 | 0.2895 |


### 3.2 Top 10 Best Combinations (by median label, n>=20)

> 在所有至少出现 20 次的组合中，中位数涨幅最高的前 10 个。这些是历史上表现最好的 Bonus 搭配模式。
> - **combination**：触发的 Bonus 列表（如 "Volume+DayStr" 表示这两个同时触发）
> - **n_triggered**：触发了几个 Bonus
> - **count**：这种组合出现了多少次（样本量越大越可信）

| combination | n_triggered | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Volume+Streak+DayStr+Height | 4 | 33 | 0.6012 | 0.3759 | 0.7390 | 0.2221 | 0.6753 |
| PK-Mom+PBM+DayStr+Drought+Height | 5 | 22 | 0.3764 | 0.3506 | 0.2305 | 0.1869 | 0.5118 |
| PK-Mom+PBM+Drought+Height | 4 | 51 | 0.3979 | 0.3496 | 0.2733 | 0.1876 | 0.5407 |
| Volume+Streak+PBM+DayStr+Height | 5 | 77 | 0.4861 | 0.3117 | 0.4847 | 0.1818 | 0.6671 |
| PK-Mom+DayStr+Drought+Height | 4 | 86 | 0.4958 | 0.3086 | 0.6151 | 0.1820 | 0.5684 |
| Streak+PBM+DayStr+Height | 4 | 104 | 0.4051 | 0.3021 | 0.3662 | 0.1507 | 0.5472 |
| Volume+PK-Mom+DayStr+Drought+Height | 5 | 46 | 0.6302 | 0.2975 | 0.8687 | 0.1203 | 0.8224 |
| PBM+Height | 2 | 29 | 0.3697 | 0.2908 | 0.3620 | 0.1271 | 0.4566 |
| PK-Mom+Drought+Height | 3 | 105 | 0.4114 | 0.2811 | 0.5087 | 0.1412 | 0.4232 |
| Volume+PK-Mom+PBM+DayStr+Height | 5 | 21 | 0.3832 | 0.2732 | 0.3319 | 0.1640 | 0.4142 |


### 3.3 All Combinations (n>=20, sorted by median)

> 满足最小样本量要求的所有组合完整列表，按中位数涨幅从高到低排序。

| combination | n_triggered | count | mean | median | std | q25 | q75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Volume+Streak+DayStr+Height | 4 | 33 | 0.6012 | 0.3759 | 0.7390 | 0.2221 | 0.6753 |
| PK-Mom+PBM+DayStr+Drought+Height | 5 | 22 | 0.3764 | 0.3506 | 0.2305 | 0.1869 | 0.5118 |
| PK-Mom+PBM+Drought+Height | 4 | 51 | 0.3979 | 0.3496 | 0.2733 | 0.1876 | 0.5407 |
| Volume+Streak+PBM+DayStr+Height | 5 | 77 | 0.4861 | 0.3117 | 0.4847 | 0.1818 | 0.6671 |
| PK-Mom+DayStr+Drought+Height | 4 | 86 | 0.4958 | 0.3086 | 0.6151 | 0.1820 | 0.5684 |
| Streak+PBM+DayStr+Height | 4 | 104 | 0.4051 | 0.3021 | 0.3662 | 0.1507 | 0.5472 |
| Volume+PK-Mom+DayStr+Drought+Height | 5 | 46 | 0.6302 | 0.2975 | 0.8687 | 0.1203 | 0.8224 |
| PBM+Height | 2 | 29 | 0.3697 | 0.2908 | 0.3620 | 0.1271 | 0.4566 |
| PK-Mom+Drought+Height | 3 | 105 | 0.4114 | 0.2811 | 0.5087 | 0.1412 | 0.4232 |
| Volume+PK-Mom+PBM+DayStr+Height | 5 | 21 | 0.3832 | 0.2732 | 0.3319 | 0.1640 | 0.4142 |
| Volume+PK-Mom+Streak+DayStr+Height | 5 | 42 | 0.5065 | 0.2617 | 0.6358 | 0.1683 | 0.5487 |
| Volume+PK-Mom+DayStr+Height | 4 | 159 | 0.3718 | 0.2616 | 0.4588 | 0.1540 | 0.4013 |
| Streak+DayStr+Height | 3 | 95 | 0.3776 | 0.2471 | 0.4707 | 0.1335 | 0.4446 |
| PK-Mom+Height | 2 | 452 | 0.3438 | 0.2394 | 0.3559 | 0.1304 | 0.4282 |
| PK-Mom+PBM+DayStr+Height | 4 | 80 | 0.3818 | 0.2335 | 0.5017 | 0.1270 | 0.4385 |
| PK-Mom+Streak+PBM+DayStr+Height | 5 | 65 | 0.3015 | 0.2323 | 0.2254 | 0.1545 | 0.3690 |
| Streak+PBM+Height | 3 | 371 | 0.3182 | 0.2319 | 0.3117 | 0.1116 | 0.3904 |
| PK-Mom+PBM+Height | 3 | 142 | 0.3058 | 0.2300 | 0.2922 | 0.1280 | 0.3866 |
| PK-Mom+DayStr+Drought | 3 | 85 | 0.2858 | 0.2282 | 0.2602 | 0.1288 | 0.3730 |
| DayStr+Height | 2 | 26 | 0.2864 | 0.2254 | 0.2440 | 0.0960 | 0.4052 |
| Volume+PK-Mom+DayStr | 3 | 41 | 0.4609 | 0.2228 | 0.6991 | 0.1073 | 0.4057 |
| PK-Mom+DayStr+Height | 3 | 311 | 0.3291 | 0.2219 | 0.3697 | 0.1191 | 0.3978 |
| PK-Mom+Streak+DayStr+Height | 4 | 172 | 0.3202 | 0.2179 | 0.3051 | 0.1298 | 0.3791 |
| Height | 1 | 56 | 0.3254 | 0.2125 | 0.3323 | 0.1147 | 0.3719 |
| PK-Mom+Streak+PBM+Height | 4 | 350 | 0.2740 | 0.2000 | 0.2683 | 0.1139 | 0.3603 |
| PK-Mom+Streak+Height | 3 | 817 | 0.3086 | 0.1996 | 0.4091 | 0.1011 | 0.3566 |
| Streak+Height | 2 | 467 | 0.2600 | 0.1761 | 0.2897 | 0.0873 | 0.3439 |
| PK-Mom+Drought | 2 | 155 | 0.2343 | 0.1647 | 0.2123 | 0.0983 | 0.2997 |
| Streak+PBM+DayStr | 3 | 52 | 0.2141 | 0.1587 | 0.1817 | 0.1087 | 0.2277 |
| PK-Mom | 1 | 436 | 0.2371 | 0.1582 | 0.3107 | 0.0900 | 0.2770 |
| Streak+DayStr | 2 | 108 | 0.2460 | 0.1572 | 0.2920 | 0.0830 | 0.2799 |
| PK-Mom+PBM+DayStr | 3 | 47 | 0.2290 | 0.1555 | 0.1989 | 0.0908 | 0.2966 |
| PK-Mom+DayStr | 2 | 247 | 0.2233 | 0.1552 | 0.2329 | 0.0895 | 0.2557 |
| PK-Mom+Streak+DayStr | 3 | 130 | 0.2051 | 0.1454 | 0.1856 | 0.0910 | 0.2538 |
| DayStr | 1 | 48 | 0.3077 | 0.1405 | 0.6152 | 0.0759 | 0.2755 |
| Drought | 1 | 43 | 0.1951 | 0.1398 | 0.1698 | 0.0757 | 0.2501 |
| PK-Mom+PBM+Drought | 3 | 45 | 0.1925 | 0.1282 | 0.2018 | 0.0950 | 0.2184 |
| PK-Mom+PBM | 2 | 142 | 0.1893 | 0.1266 | 0.1565 | 0.0803 | 0.2645 |
| PK-Mom+Streak+PBM | 3 | 528 | 0.1756 | 0.1255 | 0.1698 | 0.0761 | 0.2128 |
| PK-Mom+Streak+PBM+DayStr | 4 | 48 | 0.1735 | 0.1246 | 0.1387 | 0.0865 | 0.2168 |
| PK-Mom+Streak | 2 | 1217 | 0.1836 | 0.1152 | 0.2263 | 0.0689 | 0.2222 |
| None | 0 | 145 | 0.1508 | 0.1136 | 0.1363 | 0.0630 | 0.1915 |
| Streak+PBM | 2 | 472 | 0.1678 | 0.1102 | 0.1842 | 0.0632 | 0.2131 |
| Streak | 1 | 1180 | 0.1476 | 0.1019 | 0.1556 | 0.0615 | 0.1804 |
| PBM | 1 | 43 | 0.1351 | 0.1005 | 0.1363 | 0.0551 | 0.1618 |


## 4. Interaction Effects

> **目的**：检验两个 Bonus 之间是否存在"1+1>2"（正交互）或"1+1<2"（负交互）效应。比如 Volume 和 DayStr 单独看都不错，但同时出现时效果是相加还是相乘？
>
> **计算方法**：用"A和B同时触发"时的平均涨幅，减去"只有A或只有B触发"时的平均涨幅。
> - 正值 → 两者搭配有增益效果（协同增强）
> - 负值 → 两者搭配反而不如单独出现（互相抵消）
> - 接近 0 → 没有明显交互，各自独立发挥作用

### 4.1 Interaction Matrix

> 矩阵中每个格子是对应两个 Bonus 的交互效应值。正值越大说明协同越强，负值越大说明互相抵消越严重。

| Bonus | Age | Tests | Volume | PK-Mom | Streak | PBM | Overshoot | DayStr | PeakVol | Drought | Height |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Age | 0.0000 | - | - | - | - | - | - | - | - | - | - |
| Tests | - | 0.0000 | - | - | - | - | - | - | - | - | - |
| Volume | - | - | 0.0000 | 0.1872 | 0.1905 | 0.1971 | - | 0.1145 | - | 0.1929 | 0.1647 |
| PK-Mom | - | - | 0.1872 | 0.0000 | -0.0325 | -0.0241 | - | 0.0601 | - | 0.1026 | 0.0997 |
| Streak | - | - | 0.1905 | -0.0325 | 0.0000 | 0.0132 | - | 0.0820 | - | - | 0.0857 |
| PBM | - | - | 0.1971 | -0.0241 | 0.0132 | 0.0000 | - | 0.0698 | - | 0.0328 | 0.0527 |
| Overshoot | - | - | - | - | - | - | 0.0000 | - | - | - | - |
| DayStr | - | - | 0.1145 | 0.0601 | 0.0820 | 0.0698 | - | 0.0000 | - | 0.0946 | 0.0812 |
| PeakVol | - | - | - | - | - | - | - | - | 0.0000 | - | - |
| Drought | - | - | 0.1929 | 0.1026 | - | 0.0328 | - | 0.0946 | - | 0.0000 | 0.1356 |
| Height | - | - | 0.1647 | 0.0997 | 0.0857 | 0.0527 | - | 0.0812 | - | 0.1356 | 0.0000 |


### 4.2 Top Positive Interactions

> 协同效应最强的组合——这些 Bonus 搭配在一起时表现远超单独出现。
> - **n_both**：两者同时触发的样本数（越多越可信）
> - **n_one_only**：只有其中一个触发的样本数

| bonus_a | bonus_b | effect | n_both | n_one_only |
| --- | --- | --- | --- | --- |
| Volume | PBM | 0.1971 | 223 | 3149 |
| Volume | Drought | 0.1929 | 102 | 1292 |
| Volume | Streak | 0.1905 | 307 | 6596 |
| Volume | PK-Mom | 0.1872 | 482 | 5990 |
| Volume | Height | 0.1647 | 519 | 4051 |
| Drought | Height | 0.1356 | 365 | 4401 |
| Volume | DayStr | 0.1145 | 580 | 1930 |
| PK-Mom | Drought | 0.1026 | 648 | 5700 |
| PK-Mom | Height | 0.0997 | 2999 | 4591 |
| DayStr | Drought | 0.0946 | 318 | 2496 |


### 4.3 Top Negative Interactions

> 互相抵消效应最强的组合——这些 Bonus 同时出现时反而不如单独出现。

| bonus_a | bonus_b | effect | n_both | n_one_only |
| --- | --- | --- | --- | --- |
| PK-Mom | Streak | -0.0325 | 3453 | 5804 |
| PK-Mom | PBM | -0.0241 | 1622 | 5851 |


## 5. Feature Importance (Tree Models)

> **目的**：用机器学习模型自动判断哪些 Bonus 因子对预测涨幅最重要。这是对前面人工分析的补充——让算法"自己说"哪些因子最有用。
>
> 使用了两种树模型：
> - **DecisionTree（决策树）**：像流程图一样逐步判断，每一步选一个最有区分力的因子来分组。简单直观但可能不稳定
> - **RandomForest（随机森林）**：同时训练 100 棵不同的决策树，综合它们的意见来判断。结果更稳定可靠
>
> **importance（重要性）**：该因子对预测的贡献占比，所有因子加起来 = 1.0。越高说明模型越依赖这个因子来做判断
>
> **R-squared（R²）**：模型用这些 Bonus levels 能解释多少涨幅的变化。0 = 完全没有解释力，1 = 完美预测。通常低于 0.1 说明这些因子单独来看解释力有限（但不代表没用，它们仍可作为筛选信号）

### 5.1 DecisionTree (max_depth=4)

R-squared: 0.0933

| feature | importance |
| --- | --- |
| Height | 0.6279 |
| Volume | 0.1705 |
| Streak | 0.0975 |
| Drought | 0.0501 |
| DayStr | 0.0417 |
| PBM | 0.0123 |
| Age | 0.0000 |
| Tests | 0.0000 |
| PK-Mom | 0.0000 |
| Overshoot | 0.0000 |
| PeakVol | 0.0000 |


### 5.2 RandomForest (n_estimators=100, max_depth=4)

R-squared: 0.1026

| feature | importance |
| --- | --- |
| Height | 0.5942 |
| Volume | 0.1553 |
| Streak | 0.0877 |
| Drought | 0.0659 |
| DayStr | 0.0522 |
| PBM | 0.0323 |
| PK-Mom | 0.0123 |
| Tests | 0.0000 |
| Age | 0.0000 |
| Overshoot | 0.0000 |
| PeakVol | 0.0000 |


## 6. Key Findings

> 以下是算法从上述分析中自动提取的要点摘要。

1. **Strongest single factor**: Height (Spearman r = 0.3044, p = 5.751e-209)
2. **Best combination**: Volume+Streak+DayStr+Height (median = 0.3759, n = 33)
3. **Optimal trigger count**: 6 bonuses triggered (median label = 0.2895)
4. **Strongest positive interaction**: Volume + PBM (effect = 0.1971)
5. **Most important feature (RF)**: Height (importance = 0.5942)
6. **Best pattern**: power_breakout (median = 0.3143, n = 190); **Worst**: basic (median = 0.1261, n = 327)
7. **Model R-squared**: DecisionTree = 0.0933, RandomForest = 0.1026 (bonus levels alone explain moderate variance)
