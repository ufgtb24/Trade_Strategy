# rho 与 confidence 在 sentiment_score 中的角色分析

> 2026-04-07 | Agent Team 研究（数学分析师 + 金融分析师交叉讨论）

## 背景

用户观察到 sentiment 模块输出中 `sentiment_score` 与 `confidence` 值相同（正面场景下），
提出疑问：rho 的数值（幅度）是否应更直接地反映在 sentiment_score 中？

### 当前公式链

```
Step 1: rho = (w_p_emph - w_n_emph × LA) / (w_p_emph + w_n_emph × LA + neu_tw × W0_RHO)
        rho ∈ [-1, 1]，加权极性分数

Step 2: sentiment 标签
        |rho| > DELTA(0.07) → positive/negative
        |rho| ≤ DELTA → neutral

Step 3: confidence（正/负分支）
        certainty = min(|rho| × 1.54, 1.0)          # CERT_BOOST=0.54
        sufficiency = (1 - exp(-evidence / K)) × scarcity
        opp_penalty = GAMMA × (opposing_emph / total_emph)
        confidence = certainty × sufficiency × (1 - opp_penalty)
        负面分支额外 × NEG_AMP(1.40)

Step 4: sentiment_score = sign(rho) × confidence
```

## 分析过程

### 方案对比

| 方案 | 公式 | 特点 |
|------|------|------|
| **Current** | sign(rho) × confidence | rho 幅度通过 certainty 间接进入，被 cap 和 sign() 截断 |
| **Proposal B** | rho × sufficiency × (1-opp) | 去掉 certainty 层，rho 直接参与 |
| **路径 2** | \|rho\|^ALPHA × sign(rho) × sufficiency × (1-opp) | 幂律映射，ALPHA<1 压缩动态范围 |

### 关键数学发现

**在 certainty 未 cap 的区间（|rho| < 0.649，约 66% 的场景），Proposal B 与 Current 的差异是精确的常数缩放因子 1/1.54 = 0.6494，零排序变化。**

这意味着：certainty 层在多数场景中确实只是 rho 的线性缩放，是语义冗余的。但这也意味着去掉它只改变绝对尺度，不改变排序——收益不值得重校准阈值的代价。

### 发现的真实缺陷

#### 缺陷 1：opp_penalty double-counting（双方一致认为最高优先级）

负面新闻同时通过两条路径抑制 score：
1. 拉低 rho → 降低 certainty
2. 增大 opp_penalty → 直接乘法惩罚

两条路径使用相同的 emphasized weights，导致同一信号被惩罚两次。

数值验证：10 条正面 + 1 条 high 负面时，总抑制 42%，其中 opp_penalty 额外贡献 16.2%。当前数值"恰好合理"是两个偏差互相抵消的巧合，不应依赖。

#### 缺陷 2：certainty 硬 cap

`certainty = min(|rho| × 1.54, 1.0)` 在 |rho| ≥ 0.649 时截断为 1.0。rho=0.65 与 rho=0.95 在 certainty 维度不可区分。虽然高 rho 区间的分辨率对风控决策边际价值有限，但 tanh 映射能零成本保留信息。

#### 缺陷 3：死区边界一阶不连续

rho=0.069 → score=0，rho=0.071 → score=+confidence。存在跳变。实践中影响有限，但修复成本极低。

## 结论：推荐修复方案

双方最终立场高度收敛。推荐定向修复而非推翻公式结构。

### 修复后完整公式链

```
Step 1: rho（不变）
   rho = (w_p_emph - w_n_emph × LA) / (w_p_emph + w_n_emph × LA + neu_tw × W0_RHO)

Step 2: sentiment 标签（不变，仅用于显示/日志，不参与 score 计算）
   |rho| > DELTA → positive/negative, 否则 neutral

Step 3: confidence（三项修复）
   certainty = tanh(K_TANH × |rho|)                    ← 修复: 替代 min 硬截断
   sufficiency = (1 - exp(-evidence / K)) × scarcity    （不变）
   opp_penalty = GAMMA × (w_n_raw / w_total_raw)        ← 修复: raw 替代 emph
   confidence = certainty × sufficiency × (1 - opp_penalty)

Step 4: score 计算（不再依赖死区分支）               ← 修复: 统一路径
   if n_dir == 0:  score = 0                             # 纯 neutral
   elif rho >= 0:  score = +confidence                   # 正面（含弱正面）
   else:           score = -confidence × NEG_AMP         # 负面（含弱负面）
```

### 修复 1：opp_penalty double-counting（P0，最高优先级）

负面新闻同时通过两条路径抑制 score：拉低 rho（通过 certainty 传导）和增大 opp_penalty。两条路径使用相同的 emphasized weights，同一信号被惩罚两次。

```python
# 当前（double-counting）
opp_penalty = _GAMMA * (w_n_emph / (w_p_emph + w_n_emph))

# 修复：改用 raw weights，与 rho 输入解耦
opp_penalty = _GAMMA * (w_n / (w_p + w_n))
```

语义分离：rho 用 emphasized weights 做方向判定（极端事件非线性放大），opp_penalty 用 raw weights 做对立面比例评估（线性）。GAMMA/OPP_NEG 参数值暂不调整——raw weights 下 opp 绝对值通常小于 emphasized（extreme 不再放大），正好补偿 double-counting 的修复。

### 修复 2：certainty 硬 cap → tanh 映射（P1）

```python
# 当前
certainty = min(abs(rho) * (1 + _CERT_BOOST), 1.0)  # _CERT_BOOST=0.54

# 修复
_K_TANH = 2.0  # 替代 _CERT_BOOST
certainty = math.tanh(_K_TANH * abs(rho))
```

**选择 K_TANH=2.0 的理由**（经 14 场景 pipeline 验证优于 1.67）：

| |rho| | 当前 | tanh(1.67×) | tanh(2.0×) | 
|-------|------|-------------|------------|
| 0.10 | 0.154 | 0.166 | 0.197 |
| 0.30 | 0.462 | 0.462 | 0.537 |
| 0.50 | 0.770 | 0.695 | 0.762 |
| 0.70 | 1.000 | 0.814 | 0.885 |
| 1.00 | 1.000 | 0.931 | 0.964 |

k=2.0 效果：低 rho 区间适度抬升（混合信号更有区分度），高 rho 区间适度降低（保留分辨率），中间区间几乎不变。所有 14 个测试场景的风控阈值区间（PASS/POSITIVE BOOST/EXCLUDE/STRONG VETO）均未改变，无需重校准阈值。

### 修复 3：去除硬死区（P2）

不再需要额外的 soft_gate 参数。tanh 在 rho→0 时自然趋向 0，score 连续过渡：

```python
# 当前：三分支（positive / negative / neutral-conflict）
# 修复：统一为两分支，DELTA 仅用于标签显示
if n_dir == 0:
    confidence = 0.0                    # 纯 neutral
elif rho >= 0:
    # 正面分支（含 rho ∈ [0, DELTA] 的"弱正面"）
    certainty = math.tanh(_K_TANH * abs(rho))
    opp_penalty = _GAMMA * (w_n / (w_p + w_n)) if w_n > 0 else 0.0
    confidence = certainty * sufficiency * (1.0 - opp_penalty)
else:
    # 负面分支（含 rho ∈ [-DELTA, 0) 的"弱负面"）
    certainty = math.tanh(_K_TANH * abs(rho))
    opp_penalty = _OPP_NEG * (w_p / (w_p + w_n)) if w_p > 0 else 0.0
    confidence = certainty * sufficiency * (1.0 - opp_penalty) * _NEG_AMP
```

冲突型 neutral 分支（原 K_NEU, CONFLICT_POW, CONFLICT_CAP）可完全删除：rho≈0 时 tanh(2.0×0.05)=0.10，score 在 ±0.05 范围，与现有 score=0 差异极小且更能反映微弱方向偏好。

### 不推荐：去掉 certainty 层（Proposal B）

- 66% 场景中只是 0.649 常数缩放，零排序变化，需重校准所有下游阈值
- 混合信号区间 score 绝对值偏小，可能被噪声淹没
- tanh 替代已能解决 cap 问题，不需要推翻结构

### 保留备选：路径 2（|rho|^ALPHA）

如果 sentiment_score 未来从风控阈值升级为排序因子，记录为 v2 候选：

```python
amplified_rho = sign(rho) × |rho|^ALPHA    # ALPHA ∈ (0.5, 1.0)
adjusted_conf = sufficiency × (1 - opp_penalty) × [NEG_AMP if negative]
sentiment_score = amplified_rho × adjusted_conf
```

### 参数变更汇总

| 参数 | 旧值 | 新值 | 变更 |
|---|---|---|---|
| _CERT_BOOST | 0.54 | -- | **删除**（被 _K_TANH 替代） |
| _K_TANH | -- | 2.0 | **新增** |
| _K_NEU | 2.47 | -- | **删除**（neutral 分支移除） |
| _CONFLICT_POW | 3.0 | -- | **删除** |
| _CONFLICT_CAP | 0.15 | -- | **删除** |
| _GAMMA | 0.70 | 0.70 | 不变（输入改为 raw weights） |
| _OPP_NEG | 0.35 | 0.35 | 不变（输入改为 raw weights） |
| _DELTA | 0.07 | 0.07 | 保留（仅用于标签显示） |

净效果：11 个参数 → 8 个参数（删 4 增 1）。

### 场景验证（14 场景 pipeline 对比）

| 场景 | rho | 当前 score | 修复后 score | 风控区间 |
|------|-----|-----------|-------------|---------|
| 30 med pos | +1.000 | +0.565 | +0.545 | POSITIVE BOOST |
| 3 ext pos + 1 low neg | +0.943 | +0.725 | +0.673 | POSITIVE BOOST |
| 15p+7n+15u (med) | +0.230 | +0.156 | +0.189 | PASS |
| 15p+7n+15u (mix) | +0.169 | +0.119 | +0.151 | PASS |
| 5 ext neg | -1.000 | -1.136 | -1.095 | STRONG VETO |
| 10p(m)+3n(h)+5u | -0.061 | 0.000 | -0.081 | PASS |
| 5p(m)+5n(m)+10u | -0.098 | -0.098 | -0.126 | PASS |
| 20p+18n (med) | -0.063 | 0.000 | -0.081 | PASS |

所有场景的风控区间均未改变。混合信号场景分数略微提升（区分度更好），高 rho 场景略微降低（保留分辨率）。

## 对抗性验证（第二轮 Agent Team）

第二轮团队以对抗方式验证修复方案：辩护者用数值证明优越性，魔鬼代言人尽力寻找弱点。

### 数值证明的四个维度

**1. Double-counting 证明**（10 med pos + 2 high neg, rho=+0.138）

| 指标 | 当前 | 修复后 |
|---|---|---|
| opp_penalty | 0.2627 (emph) | 0.1697 (raw) |
| score | +0.0957 | +0.1368 |
| negative 总抑制 | 84.3% | 77.6% |

emphasis 将 high neg 的 opp_penalty 权重从 raw 比例 24.2% 膨胀至 emph 比例 37.5%，超额惩罚 55%。

**2. 硬 cap 证明**（rho=0.70 vs rho=0.95）

当前代码：两场景 certainty 均为 1.0，不可区分。修复后：0.884 vs 0.956，保留 8.2% 差异。

**3. 死区跳变证明**（rho=0.068 vs rho=0.087，差仅 0.019）

当前代码：score 从 0.000 跳到 +0.055（无穷比率）。修复后：0.055 → 0.070（连续）。

**4. 冲突型 neutral**（5 pos + 4 neg + 10 neutral, rho=-0.003）

当前代码：score = 0.000（信息全部丢失）。修复后：score = -0.004（保留微弱方向信号）。

### 魔鬼代言人的反驳评估

| 反驳维度 | 当前代码是否有优势 | 结论 |
|---|---|---|
| 低 rho 噪声放大 | 否 | tanh 放大的是真实信号，不是噪声 |
| 高 rho 达不到 1.0 | 微弱（最大 3.6%） | 实践中可忽略 |
| **extreme 对冲被削弱** | **有一定道理** | 但被 double-counting 理论缺陷抵消 |
| 冲突型 neutral 保护 | 否 | tanh 自然衰减隐式替代 CONFLICT_CAP |
| 参数灵活性降低 | 否 | 删除的参数不提供独特表达力 |
| 双重放大交互 | 微弱（最大 1.39x） | 绝对值仍很低，不影响决策 |

### 阈值跨越穷举验证

对 1~24 条新闻的全 impact 组合穷举，发现 387 个阈值跨越：

| 跨越方向 | 数量 | 风控影响 |
|---------|------|---------|
| **reject → pass（漏放）** | **0** | **最危险方向：零案例** |
| pass → reject（误拒） | 100 | 修复更保守（更安全） |
| pass ↔ positive_boost | 134 | 仅统计标记，无风控影响 |
| reject ↔ strong_reject | 152 | 两者都被排除，无泄漏 |

**因果分解**：100 个 pass→reject 跨越中，99 个仅由 tanh 驱动，0 个仅由 opp_penalty 驱动。opp_penalty 从 emph 改为 raw 几乎不造成阈值跨越。

### 验证结论

**修复方案在所有测试维度上均优于或等于当前代码，不存在风控漏洞。**

## 附：输出格式改进建议

（源自原始提问）当前输出中 sentiment_score 与 confidence 值相同导致混淆。建议重组为：

```
Summary:
  Sentiment: positive (+0.1443)
  Decomposition:
    Polarity (rho):  +0.2936
    Confidence:       0.1443  (= certainty × sufficiency × penalty)
    Score = sign(rho) × confidence
  Breakdown: positive=15 negative=7 neutral=15
```
