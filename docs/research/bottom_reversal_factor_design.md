# 底部反转因子设计研究报告

## 问题背景

当前 `ma_pos` 因子仅计算 `close / MA_N - 1.0`（溢价率），这是一个静态标量，存在根本性缺陷：

| 市场状态 | ma_pos 值 | 突破质量 | 能否区分？ |
|---------|----------|---------|----------|
| 底部刚启动，价格接近均线 | ~0 (小正数) | **最好** | ❌ |
| 高位横盘贴着均线运行 | ~0 | 一般 | ❌ |
| 高位远离均线 | 大正数 | 差 | ✅ |
| 下跌中，价格在均线下方 | 负数 | 最差 | ✅ |

**核心问题**：ma_pos 无法区分"底部反转启动"和"高位无趋势横盘"——两者的 ma_pos 值可能完全相同，但突破后的涨幅天差地别。

**用户观察**：上涨最多的突破就是从底部启动的突破。需要设计因子锁定这种模式。

---

## 研究方法

由两个独立研究方向并行探索：
- **均线方向**：MA曲率、斜率转向、双均线收敛
- **非均线方向**：回撤恢复度、波动率压缩、价格百分位、动量反转等

---

## 全部候选方案一览

| # | 方案名 | 来源 | 信息维度 | 与现有因子正交性 | 实现复杂度 | 底部捕捉力 |
|---|-------|------|---------|---------------|----------|----------|
| A | MA曲率 (ma_curve) | 均线 | 趋势动力学(加速度) | 高 | 简单 | 中高 |
| B | MA斜率转向 | 均线 | 趋势变化量 | 中高 | 中 | 中高 |
| C | 双MA收敛 | 均线 | 趋势结构 | 中 | 简单 | 中 |
| D | 回撤恢复度 (dd_recov) | 非均线 | 价格结构位置 | **很高** | 简单 | **很高** |
| E | 波动率压缩 (vol_squeeze) | 非均线 | 波动率模式 | **很高** | 简单 | 高 |
| F | 价格百分位 | 非均线 | 分布位置 | 高 | 极简 | 中 |

淘汰理由：
- **B (斜率转向)**：与 A (曲率) 数学高度相关，参数更多(3个)，信息增量有限
- **C (双MA收敛)**：对横盘假信号敏感，与 ma_pos 有部分信息重叠
- **F (价格百分位)**：dd_recov 的退化版本，后者包含更丰富的"高点-低点-恢复"三段叙事

---

## 最终推荐方案

### 推荐组合：dd_recov + ma_curve

两个因子分别从两个正交维度锁定底部反转：

| 维度 | dd_recov | ma_curve |
|------|---------|---------|
| 回答的问题 | 价格**从哪里**来？在回撤-恢复周期的什么位置？ | 趋势**正在往哪个方向**加速？拐点是否已形成？ |
| 物理类比 | 位移/位置 | 加速度 |
| 典型底部启动值 | 0.08~0.15 (深回撤 × 适度恢复) | >0.05 (均线从凹变凸) |
| 典型非底部值 | ~0 (高位运行无回撤) | ~0 (横盘) 或 <0 (下跌加速) |

组合威力：dd_recov 高 + ma_curve 正 = **高置信度的底部反转信号**

### 备选第三因子：vol_squeeze

如果两因子组合的 mining 效果仍不理想，vol_squeeze 提供完全独立的第三维度（波动率模式），可作为第三个因子加入。

---

## 详细设计

### 因子1: dd_recov（回撤恢复度）

#### 核心思想

直接度量"价格从高点回撤后恢复了多少"。通过 `drawdown × recovery_ratio` 的乘积，在"回撤深且恢复到中间位置"时自然取最大值——这正是底部启动的甜蜜点。

#### 计算公式

```python
def _calculate_dd_recov(self, df: pd.DataFrame, idx: int) -> float:
    """
    回撤恢复度：drawdown * recovery_ratio

    在 lookback 窗口内找到最高点，然后：
    - drawdown = (peak - current) / peak   # 当前距高点还有多远
    - recovery = (current - trough) / (peak - trough)  # 从最低点恢复了多少
    - 输出 = drawdown * recovery

    乘积设计的直觉：
    - 高位运行（drawdown≈0）-> 输出≈0
    - 底部未恢复（recovery≈0）-> 输出≈0
    - 深度回撤+适度恢复（甜蜜点）-> 输出最大
    """
    lookback = self.dd_recov_lookback  # 默认 252
    start = max(0, idx - lookback)

    highs = df["high"].values[start:idx + 1]
    peak_local_idx = np.argmax(highs)
    peak_price = highs[peak_local_idx]
    peak_abs_idx = start + peak_local_idx

    current_price = df["close"].values[idx]

    # 无回撤（当前就是最高点）-> 非底部
    if peak_price <= 0 or current_price >= peak_price:
        return 0.0

    drawdown = (peak_price - current_price) / peak_price

    # 从 peak 之后的最低点
    trough_price = df["low"].values[peak_abs_idx:idx + 1].min()
    range_total = peak_price - trough_price
    if range_total <= 0:
        return 0.0

    recovery_ratio = (current_price - trough_price) / range_total

    return drawdown * recovery_ratio
```

#### 数值示例

| 场景 | 价格轨迹 | drawdown | recovery | dd_recov | 解读 |
|------|---------|----------|----------|----------|------|
| **底部启动（甜蜜点）** | 100→40→75 | 0.25 | 0.58 | **0.145** | 深回撤+良好恢复 |
| 底部启动（早期） | 100→60→75 | 0.25 | 0.375 | 0.094 | 回撤中等，恢复中等 |
| 已完全恢复 | 100→60→95 | 0.05 | 0.875 | 0.044 | drawdown已很小 |
| 高位运行 | 100→95→96 | 0.04 | 0.20 | 0.008 | 无显著回撤 |
| 底部未恢复 | 100→40→42 | 0.58 | 0.033 | 0.019 | recovery太低 |

#### 因子注册配置

```python
FactorInfo('dd_recov', 'Drawdown Recovery', '回撤恢复度',
           (0.04, 0.08, 0.12), (1.15, 1.25, 1.40),
           category='context',
           unit='', display_transform='round2', zero_guard=True,
           sub_params=(
               SubParamDef('lookback', 'dd_recov_lookback', int, 252,
                           (60, 504), 'Lookback window for peak detection'),
           ))
```

#### 与现有因子互补性

- vs `drought`：drought 只看时间间隔，dd_recov 度量价格结构位置，**完全正交**
- vs `pk_mom`：pk_mom 30天局部 V 型凹陷，dd_recov 252天大级别位置，**时间尺度不同**
- vs `ma_pos`：ma_pos 不含"从哪里跌下来、恢复多少"的信息，**维度不同**
- vs `pbm`：pbm 是 5 天短期动量，完全不涉及底部判断

---

### 因子2: ma_curve（MA曲率）

#### 核心思想

均线的二阶导数（曲率）直接刻画趋势变化的拐点。底部反转 = 下跌减速 → 触底 → 开始上行，对应曲率从负变正（凹函数 → 凸函数）。

与 ma_pos 的关系：ma_pos 衡量**位置**（价格在均线上方还是下方），ma_curve 衡量**加速度**（趋势正在加速还是减速）——运动学中的位移 vs 加速度，信息完全互补。

#### 计算公式

```python
def _calculate_ma_curve(self, df: pd.DataFrame, idx: int) -> float:
    """
    MA 曲率因子：均线二阶导数的归一化值

    正值 = 均线正在加速上行（或下跌正在减速）-> 底部反转信号
    零   = 均线斜率不变（匀速趋势或平盘）
    负值 = 均线正在加速下行（或上行正在减速）-> 顶部信号
    """
    period = self.ma_curve_period   # 默认 20
    smooth = self.ma_curve_smooth   # 默认 5

    min_bars = period + smooth + 1
    if idx < min_bars:
        return 0.0

    # Step 1: 获取 MA 序列（需要 smooth+2 个值）
    ma_col = f"ma_{period}"
    if ma_col in df.columns:
        ma_series = df[ma_col].iloc[idx - smooth - 1: idx + 1].values
    else:
        close = df["close"].values
        ma_series = np.array([
            close[i - period + 1: i + 1].mean()
            for i in range(idx - smooth - 1, idx + 1)
        ])

    if np.any(np.isnan(ma_series)):
        return 0.0

    # Step 2: 一阶导数（日差分）
    d1 = np.diff(ma_series)  # 长度 = smooth + 1

    # Step 3: 二阶导数（一阶导数的差分，取均值平滑）
    d2 = np.diff(d1)         # 长度 = smooth
    curvature = np.mean(d2)

    # Step 4: 归一化（除以 MA 值，乘以 period² 还原为无量纲）
    ma_current = ma_series[-1]
    if ma_current <= 0:
        return 0.0

    return (curvature / ma_current) * (period ** 2)
```

#### 直觉解释

以 MA20 为例，过去 7 天的 MA20 值为 [100, 99.8, 99.7, 99.65, 99.65, 99.70, 99.80]:
- 一阶导数（斜率）: [-0.2, -0.1, -0.05, 0, +0.05, +0.10]
- 二阶导数（曲率）: [+0.1, +0.05, +0.05, +0.05, +0.05]
- 平均曲率 > 0 → **均线正在从下跌转为上行，底部反转信号**

对比横盘：MA 值几乎不变 → 曲率 ≈ 0（正确区分底部反转 vs 横盘）

#### 因子注册配置

```python
FactorInfo('ma_curve', 'MA Curvature', 'MA曲率',
           (0.05, 0.15, 0.30), (1.15, 1.25, 1.40),
           category='context',
           unit='', display_transform='round2', zero_guard=True,
           sub_params=(
               SubParamDef('period', 'ma_curve_period', int, 20,
                           (10, 50), 'MA period for curvature calculation'),
               SubParamDef('smooth', 'ma_curve_smooth', int, 5,
                           (3, 10), 'Smoothing window for 2nd derivative'),
           ))
```

---

### 备选因子: vol_squeeze（波动率压缩度）

#### 核心思想

底部盘整的物理特征是波动率压缩（市场分歧减少），突破时波动率扩张。"先压后爆"是底部启动的经典信号。**系统中目前没有波动率模式因子**（annual_volatility 仅作标准化分母），这填补完全空白的维度。

#### 计算公式

```python
def _calculate_vol_squeeze(self, df: pd.DataFrame, idx: int) -> float:
    """
    波动率压缩度 = max(0, 1 - short_vol / long_vol)

    0    = 无压缩（近期波动率 >= 中期）
    0.3  = 轻度压缩
    0.5+ = 显著压缩（底部盘整特征明显，预示大行情）
    """
    short_w = self.vol_squeeze_short   # 默认 10
    long_w = self.vol_squeeze_long     # 默认 60

    if idx < long_w:
        return 0.0

    close = df["close"].values
    short_rets = np.diff(close[idx - short_w:idx + 1]) / close[idx - short_w:idx]
    long_rets = np.diff(close[idx - long_w:idx + 1]) / close[idx - long_w:idx]

    short_vol = np.std(short_rets)
    long_vol = np.std(long_rets)

    if long_vol <= 0:
        return 0.0

    return max(0.0, 1.0 - short_vol / long_vol)
```

#### 因子注册配置

```python
FactorInfo('vol_sqz', 'Volatility Squeeze', '波动率压缩',
           (0.20, 0.40), (1.10, 1.20),
           category='context',
           unit='', display_transform='round2',
           sub_params=(
               SubParamDef('short', 'vol_squeeze_short', int, 10,
                           (5, 20), 'Short-term volatility window'),
               SubParamDef('long', 'vol_squeeze_long', int, 60,
                           (30, 120), 'Long-term volatility window'),
           ))
```

---

## 关于 ma_pos 的处置建议

**建议保留 ma_pos，但重新定位其角色**：

- ma_pos 衡量"价格距均线多远"，作为过热/过冷的粗略指标仍有价值
- ma_curve 不是 ma_pos 的替代品，而是补充——一个衡量位置，一个衡量加速度
- 如果mining验证 ma_pos 确实无区分力，再考虑将其加入 INACTIVE_FACTORS

---

## 实施优先级

| 优先级 | 因子 | 理由 |
|-------|------|------|
| P0 | dd_recov | 最直接回答"底部启动"问题，信息完全独立，实现简单 |
| P1 | ma_curve | 从动力学角度补充，替代 ma_pos 的不足，参数少 |
| P2 | vol_squeeze | 如果前两个mining效果不够，加入第三维度 |

建议先实现 P0+P1，跑一轮 mining 验证效果后再决定是否需要 P2。

---

## 与 chart 图形的对照验证

回看用户提供的两张典型底部启动图：

**图1（长底盘整后逐步突破）**：
- dd_recov：价格从高点大幅回撤后恢复到中间位置 → 高值 ✅
- ma_curve：均线从下跌走平到上翘（曲率正值）→ 高值 ✅
- ma_pos：价格刚到均线上方 → 小正数 → **无法区分** ❌

**图2（底部急速启动）**：
- dd_recov：深度回撤后恢复到中间 → 高值 ✅
- ma_curve：均线急速转向 → 高值 ✅
- ma_pos：取决于均线周期，可能偏高 → **信号不明确** ❌

两个新因子在典型 case 上都能正确发出信号，而 ma_pos 无法做到。

---

## 设计复审：改进与修正

### 改进1: dd_recov 超涨误判修正 — 幂次衰减法

#### 问题

原公式 `dd_recov = drawdown * recovery` 展开为 `D0 * r * (1-r)`（其中 D0 为最大回撤率，r 为恢复比例），这是关于 r 的**对称二次函数**，峰值固定在 r=0.5。

关键缺陷：r=0.3（刚开始恢复）和 r=0.7（已经恢复大部分）给出相同的值。在"下跌→反弹→大幅上涨"场景中（如 100→40→85，r=0.75），dd_recov 仍然给出有意义的正值（0.113），但实际上此时追高风险已很大。

#### 解决方案：幂次衰减

将公式从 `r * (1-r)` 泛化为 `r * (1-r)^b`：

```python
dd_recov = drawdown * recovery_ratio * (1 - recovery_ratio) ** (decay_power - 1)
```

**推荐 decay_power = 3**（峰值位置 r* = 1/(1+b) = 0.25）

这是最小改动方案：当 decay_power=1 时完全退化为原公式，只需调整一个参数即可控制右侧衰减速度。

#### 不同 decay_power 的行为

| b | 峰值位置 r* | 区分度 (r=0.3 vs r=0.7) | 评价 |
|---|------------|------------------------|------|
| 1 | 0.500 | 1.0x（对称，无区分） | 原公式 |
| 2 | 0.333 | 2.3x | 保守改进 |
| **3** | **0.250** | **5.4x** | **推荐** |
| 4 | 0.200 | 12.7x | 激进 |

#### 关键场景对比 (b=3 vs 原公式)

以 peak=100, trough=40 为例：

| 场景 | 轨迹 | recovery | 原公式值 | b=3 值 | 变化 |
|------|------|----------|---------|--------|------|
| 底部早期（甜蜜点） | 100→40→55 | 0.25 | 0.113 | **0.063** | 仍高 ✅ |
| 恢复一半 | 100→40→70 | 0.50 | 0.150 | 0.038 | 被压低 ✅ |
| **追高** | **100→40→85** | **0.75** | **0.113** | **0.007** | **被压到极低** ✅ |
| **超高追高** | **100→40→90** | **0.833** | **0.083** | **0.002** | **几乎归零** ✅ |

追高场景从 0.083~0.113 被压到 0.002~0.007，有效消除误判。

#### 更新后的计算公式

```python
def _calculate_dd_recov(self, df: pd.DataFrame, idx: int) -> float:
    """
    回撤恢复度（幂次衰减版）

    dd_recov = drawdown * recovery * (1 - recovery)^(b-1)

    通过 decay_power (b) 控制右侧衰减速度：
    - b=1: 对称（原始版本）
    - b=3: 峰值在 r=0.25，r>0.5 快速衰减（推荐）
    """
    lookback = self.dd_recov_lookback       # 默认 252
    decay_power = self.dd_recov_decay_power  # 默认 3
    start = max(0, idx - lookback)

    highs = df["high"].values[start:idx + 1]
    peak_local_idx = np.argmax(highs)
    peak_price = highs[peak_local_idx]
    peak_abs_idx = start + peak_local_idx

    current_price = df["close"].values[idx]

    if peak_price <= 0 or current_price >= peak_price:
        return 0.0

    drawdown = (peak_price - current_price) / peak_price

    trough_price = df["low"].values[peak_abs_idx:idx + 1].min()
    range_total = peak_price - trough_price
    if range_total <= 0:
        return 0.0

    recovery_ratio = (current_price - trough_price) / range_total

    return drawdown * recovery_ratio * (1 - recovery_ratio) ** (decay_power - 1)
```

#### 更新后的因子注册配置

```python
FactorInfo('dd_recov', 'Drawdown Recovery', '回撤恢复度',
           (0.02, 0.04, 0.06), (1.15, 1.25, 1.40),
           category='context',
           unit='', display_transform='round2', zero_guard=True,
           sub_params=(
               SubParamDef('lookback', 'dd_recov_lookback', int, 252,
                           (60, 504), 'Lookback window for peak detection'),
               SubParamDef('decay_power', 'dd_recov_decay_power', int, 3,
                           (1, 6), 'Recovery decay power (1=symmetric, higher=more left-skewed)'),
           ))
```

注意：b=3 时值域缩小约 2.4x，阈值从 `(0.04, 0.08, 0.12)` 调整为 `(0.02, 0.04, 0.06)`，实际最优值需 mining 确定。

---

### 改进2: ma_curve 周期从 20 调整为 50

#### 问题

period=20 时，MA20 的响应时间约 10 天（半周期）。3-5 天的反弹就足以让 MA20 曲率转正，导致**几乎所有突破都会有正曲率** → 无区分力。

用户需要捕捉**季度级/年度级的大底反转**，而不是短期技术性反弹。

#### 不同周期对比

| 维度 | period=20 | period=30 | period=50 |
|------|-----------|-----------|-----------|
| 截止周期 | ~1个月 | ~1.5个月 | ~2.5个月（季度级） |
| 短期反弹灵敏度 | 极高（3-5天即触发） | 中等（需2-3周） | **低**（需1-2个月趋势变化） |
| 信噪比 | **极低** | 中等 | **高** |
| 与用户需求匹配度 | 差 | 中 | **最佳** |
| 预计算列可用 | `ma_20` ✅ | **无**，需动态计算 | `ma_50` ✅ |
| 额外计算开销 | 零 | 有 | **零** |

#### 推荐：period=50, smooth=3

**理由**：

1. **信噪比最高**：MA50 需要 ~25 天持续趋势变化才能让曲率显著转正，天然过滤短期假信号
2. **零额外开销**：直接复用已预计算的 `ma_50` 列
3. **smooth 减小到 3**：MA50 已足够平滑，二阶导数本身就稳定，smooth=5 只增加不必要滞后
4. **与 dd_recov 正交性最好**：dd_recov 快识别位置 + ma_curve(50) 确认大级别趋势反转
5. **归一化公式自适应**：`period^2` 乘子（50²/20² = 6.25）自动补偿更长周期的更小 raw curvature，阈值量级基本不变

#### 更新后的计算公式

```python
def _calculate_ma_curve(self, df: pd.DataFrame, idx: int) -> float:
    """
    MA 曲率因子：均线二阶导数的归一化值

    使用 MA50 捕捉季度级趋势拐点。
    正值 = 均线正在加速上行（或下跌正在减速）-> 大级别底部反转信号
    """
    period = self.ma_curve_period   # 默认 50（季度级）
    smooth = self.ma_curve_smooth   # 默认 3

    min_bars = period + smooth + 1
    if idx < min_bars:
        return 0.0

    ma_col = f"ma_{period}"
    if ma_col in df.columns:
        ma_series = df[ma_col].iloc[idx - smooth - 1: idx + 1].values
    else:
        close = df["close"].values
        ma_series = np.array([
            close[i - period + 1: i + 1].mean()
            for i in range(idx - smooth - 1, idx + 1)
        ])

    if np.any(np.isnan(ma_series)):
        return 0.0

    d1 = np.diff(ma_series)
    d2 = np.diff(d1)
    curvature = np.mean(d2)

    ma_current = ma_series[-1]
    if ma_current <= 0:
        return 0.0

    return (curvature / ma_current) * (period ** 2)
```

#### 更新后的因子注册配置

```python
FactorInfo('ma_curve', 'MA Curvature', 'MA曲率',
           (0.05, 0.15, 0.30), (1.15, 1.25, 1.40),
           category='context',
           unit='', display_transform='round2', zero_guard=True,
           sub_params=(
               SubParamDef('period', 'ma_curve_period', int, 50,
                           (20, 100), 'MA period for curvature calculation'),
               SubParamDef('smooth', 'ma_curve_smooth', int, 3,
                           (2, 10), 'Smoothing window for 2nd derivative'),
           ))
```
