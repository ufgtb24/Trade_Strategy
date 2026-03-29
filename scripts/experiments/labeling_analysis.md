# Impact 标注 vs 公式差异分析

## 概览

- 标注场景总数: 43
- sentiment 方向匹配率: 37/43 (86%)
- MAD (Mean Absolute Deviation): 0.1993
- 最大偏差场景: ID 42 (diff=+0.97, AI=-0.72, Formula=+0.25)

## 当前公式参数

| 参数 | 值 | 说明 |
|------|-----|------|
| _LA | 1.02 | rho 损失厌恶系数 |
| _W0_RHO | 0.1 | neutral 在 rho 分母中的权重 |
| _DELTA | 0.1 | 死区阈值 |
| _CAP | 1.0 | sufficiency 饱和上界 |
| _K | 0.55 | evidence 饱和速度 |
| _SCARCITY_N | 3 | 方向性新闻最少条数阈值 |
| _GAMMA | 0.4 | positive 被 negative 反对的惩罚 |
| _OPP_NEG | 0.2 | negative 被 positive 反对的惩罚 |
| _BETA | 2.2 | negative certainty 放大 |
| _BETA_POS | 1.15 | positive certainty 放大 |
| _K_NEU | 2.47 | pure neutral 饱和速度 |
| _CONFLICT_POW | 3.0 | 冲突型 neutral balance 幂次 |
| _CONFLICT_CAP | 0.15 | 冲突型 neutral confidence 天花板 |

## 逐场景对比

| ID | AI Sent | AI Score | Fm Sent | Fm Score | Diff | |Diff| | 分析 |
|----|---------|----------|---------|----------|------|--------|------|
|  1 | positive | +0.55   | positive | +0.28   | -0.27 | 0.27   | 中偏差; scarcity=0.33 |
|  2 | negative | -0.75   | negative | -0.28   | +0.47 | 0.47   | 大偏差; scarcity=0.33 |
|  3 | negative | -0.15   | negative | -0.10   | +0.05 | 0.05   | scarcity=0.33 |
|  4 | negative | -0.05   | negative | -0.03   | +0.02 | 0.02   | scarcity=0.33 |
|  5 | positive | +0.22   | positive | +0.20   | -0.02 | 0.02   | scarcity=0.33 |
|  6 | positive | +0.57   | positive | +0.41   | -0.16 | 0.16   | 中偏差; scarcity=0.67 |
|  7 | negative | -0.48   | negative | -0.40   | +0.08 | 0.08   | scarcity=0.67 |
|  8 | positive | +0.10   | positive | +0.19   | +0.09 | 0.09   | scarcity=0.67 |
|  9 | negative | -0.72   | negative | -0.43   | +0.29 | 0.29   | 中偏差; scarcity=0.67 |
| 10 | positive | +0.78   | positive | +0.45   | -0.33 | 0.33   | 大偏差 |
| 11 | negative | -0.68   | negative | -0.40   | +0.28 | 0.28   | 中偏差 |
| 12 | positive | +0.85   | positive | +0.70   | -0.15 | 0.15   | — |
| 13 | negative | -0.20   | positive | +0.12   | +0.32 | 0.32   | **方向不一致**: AI=negative, Fm=positive; 大偏差 |
| 14 | negative | -0.12   | negative | -0.12   | +0.00 | 0.00   | — |
| 15 | positive | +0.42   | positive | +0.47   | +0.05 | 0.05   | — |
| 16 | negative | -0.62   | negative | -0.60   | +0.02 | 0.02   | — |
| 17 | negative | -0.80   | negative | -0.53   | +0.27 | 0.27   | 中偏差 |
| 18 | neutral  | +0.00   | neutral  | +0.00   | +0.00 | 0.00   | scarcity=0.00 |
| 19 | positive | +0.35   | positive | +0.69   | +0.34 | 0.34   | 大偏差 |
| 20 | positive | +0.12   | positive | +0.27   | +0.15 | 0.15   | 中偏差 |
| 21 | positive | +0.06   | positive | +0.09   | +0.03 | 0.03   | — |
| 22 | neutral  | -0.05   | neutral  | +0.00   | +0.05 | 0.05   | — |
| 23 | negative | -0.85   | negative | -0.54   | +0.31 | 0.31   | 大偏差 |
| 24 | positive | +0.10   | positive | +0.15   | +0.05 | 0.05   | scarcity=0.67 |
| 25 | neutral  | -0.02   | neutral  | +0.00   | +0.02 | 0.02   | scarcity=0.67 |
| 26 | positive | +0.52   | positive | +0.69   | +0.17 | 0.17   | 中偏差 |
| 27 | negative | -0.18   | neutral  | +0.00   | +0.18 | 0.18   | **方向不一致**: AI=negative, Fm=neutral; 中偏差 |
| 28 | negative | -0.35   | negative | -0.60   | -0.25 | 0.25   | 中偏差 |
| 29 | positive | +0.40   | negative | -0.22   | -0.62 | 0.62   | **方向不一致**: AI=positive, Fm=negative; 大偏差 |
| 30 | positive | +0.50   | positive | +0.55   | +0.05 | 0.05   | — |
| 31 | negative | -0.40   | negative | -0.26   | +0.14 | 0.14   | — |
| 32 | negative | -0.38   | negative | -0.21   | +0.17 | 0.17   | 中偏差 |
| 33 | positive | +0.38   | negative | -0.20   | -0.58 | 0.58   | **方向不一致**: AI=positive, Fm=negative; 大偏差 |
| 34 | positive | +0.30   | positive | +0.30   | +0.00 | 0.00   | — |
| 35 | negative | -0.88   | negative | -0.44   | +0.44 | 0.44   | 大偏差 |
| 36 | positive | +0.48   | positive | +0.58   | +0.10 | 0.10   | — |
| 37 | positive | +0.57   | positive | +0.33   | -0.24 | 0.24   | 中偏差; scarcity=0.67 |
| 38 | neutral  | -0.03   | neutral  | +0.00   | +0.03 | 0.03   | — |
| 39 | positive | +0.58   | positive | +0.51   | -0.07 | 0.07   | — |
| 40 | negative | -0.20   | negative | -0.27   | -0.07 | 0.07   | — |
| 41 | negative | -0.42   | positive | +0.12   | +0.54 | 0.54   | **方向不一致**: AI=negative, Fm=positive; 大偏差 |
| 42 | negative | -0.72   | positive | +0.25   | +0.97 | 0.97   | **方向不一致**: AI=negative, Fm=positive; 大偏差 |
| 43 | negative | -0.50   | negative | -0.65   | -0.15 | 0.15   | 中偏差 |

## 差异根本原因分析

### 统计概要

- 中/大偏差场景 (|diff| >= 0.15): **22** 个
- 方向不匹配: **6** 个
- 公式偏高 (diff > 0.15): **14** 个
- 公式偏低 (diff < -0.15): **8** 个

### 1. 损失厌恶不足 (_LA 偏低)

受影响场景: [2, 9, 11, 13, 17, 23, 27, 31, 32, 35, 41, 42]

当前 _LA = 1.02，AI 标注显示同等配置下负面应约为正面的 1.3-1.5 倍。
公式在负面场景中系统性偏弱，说明 _LA 需要显著提高。

### 2. Scarcity 保护过弱或过强

受影响场景: [1, 2, 6, 9, 37]
当前 _SCARCITY_N = 3。这些场景在 scarcity 区间内且偏差较大。

### 3. Impact 非线性不足

公式使用线性 impact 映射 (negligible=0.05, low=0.20, medium=0.50, high=0.80, extreme=1.00)。
AI 标注认为 extreme 的影响应远大于多条 low/negligible 的总和。

含 extreme 的大偏差场景: [1, 2, 6, 9, 10, 11, 29, 33, 37, 42, 43]

### 4. Certainty 放大系数

当前 _BETA (negative) = 2.2, _BETA_POS (positive) = 1.15。
负面放大约为正面的 1.5 倍。

- 正面方向一致场景 (17 个): 公式平均偏差 = -0.012
- 负面方向一致场景 (16 个): 公式平均偏差 = +0.130

### 5. 冲突场景处理

Neutral 场景 (公式或AI): [18, 22, 25, 27, 38]
  - ID 18: AI=+0.00, Fm=+0.00, diff=+0.00
  - ID 22: AI=-0.05, Fm=+0.00, diff=+0.05
  - ID 25: AI=-0.02, Fm=+0.00, diff=+0.02
  - ID 27: AI=-0.18, Fm=+0.00, diff=+0.18
  - ID 38: AI=-0.03, Fm=+0.00, diff=+0.03


## 公式改进方向

### 参数调整建议

| 参数 | 当前值 | 调整方向 | 原因 |
|------|--------|----------|------|
| _LA | 1.02 | 大幅提高至 1.3-1.8 | 当前几乎无损失厌恶效果，AI 标注显示负面应为正面 1.3-1.5 倍 |
| _BETA | 2.2 | 可能需微调 | 需配合 _LA 调整后重新评估 |
| _BETA_POS | 1.15 | 可能需微调 | 同上 |
| _K | 0.55 | 评估 | sufficiency 饱和速度影响中等样本的评分上限 |
| _GAMMA | 0.4 | 评估 | positive 被反对的惩罚力度 |
| _OPP_NEG | 0.2 | 评估 | negative 被反对的惩罚力度 |

### 结构性问题

1. **_LA 过低是最大问题**: 当前 _LA=1.02 几乎等于 1.0，公式对正负面的处理近乎对称。AI 标注一致体现损失厌恶（同等配置负面绝对值约为正面 1.3-1.5 倍），公式需显著提高 _LA。
2. **Impact 非线性**: 公式使用 [0.05, 0.20, 0.50, 0.80, 1.00] 映射，梯度相对均匀。AI 标注认为 extreme 与其他等级的差距应更大（1 条 extreme > 多条 low/medium 之和），可考虑调整映射使其更非线性。
3. **评分天花板**: 公式受 _CAP 和指数饱和限制，实际最大 |score| 可能低于 AI 标注的极值（如 AI 给出 ±0.85-0.88）。需确认公式能覆盖足够的评分区间。