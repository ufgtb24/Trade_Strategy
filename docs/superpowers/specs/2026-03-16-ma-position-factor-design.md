# MA Position Factor (`ma_pos`) Design Spec

## Summary

新增环境因子 `ma_pos`（均线位置），衡量突破时价格相对于 N 日均线的溢价率，反映中期动量积累强度。经 128K 突破样本实证验证，ma_pos_20 是所有均线候选因子中预测力最强的（Spearman rho=+0.18, 三分位 High/Low 收益比 3.4x）。

## 因子定义

| 属性 | 值 |
|------|-----|
| key | `ma_pos` |
| name | `MA Position` |
| cn_name | `均线位置` |
| default_thresholds | `(0.05, 0.10, 0.20)` |
| default_values | `(1.1, 1.2, 1.35)` |
| category | `context` |
| is_discrete | `False` |
| has_nan_group | `False` |
| mining_mode | `gte`（越大越好） |
| unit | `%` |
| display_transform | `pct100` |
| zero_guard | `True` |
| nullable | `False` |
| sub_params | `SubParamDef('period', 'ma_pos_period', int, 20, (10, 50), 'MA period')` |

**语义**：突破日收盘价相对于 N 日简单移动平均线的百分比溢价。值越大，说明突破前中期动量积累越强。

**公式**：
```
MA_N[idx] = mean(close[idx-N+1 : idx+1])
ma_pos = close[idx] / MA_N[idx] - 1.0
```
默认 N=20，mining 可在 10-50 范围搜索最优周期。

## 研究过程与发现

### 研究方法

由两个 Tommy agent 组成 team 协作分析：
- **quant-analyst**：从量化金融理论提出 5 个候选方案
- **data-analyst**：用 5,904 只美股、128,374 个突破样本进行实证验证

### 候选方案与验证结果

| 候选因子 | 公式 | 理论预测 | 实证结果 (rho, label_20) | 结论 |
|---------|------|---------|------------------------|------|
| ma_pos_20 | close/MA20 - 1 | 未重点推荐 | **+0.1844*** | **采纳** |
| ma_pos_50 | close/MA50 - 1 | lte(回归风险) | +0.1172* (gte) | 与 ma_pos_20 相关 0.72, 冗余 |
| ma_slope_20 | MA20 变化率 | gte | +0.0331* (微弱) | 放弃 |
| ma_slope_50 | MA50 变化率 | **gte(趋势健康)** | **-0.0215 (反向/U型)** | 放弃 |
| ma_cross | 金叉新鲜度 | gte | +0.0000 (无效) | 放弃 |
| ma_align | 多头排列 | **gte(趋势确认)** | **-0.0523 (负相关)** | 放弃 |

### 关键发现：理论与数据的三大分歧

#### 1. 多头排列(ma_align)是负相关的

完美多头排列（close > MA20 > MA50）的突破 20 日收益 11.6%，非多头排列的反而达 15.8%。

**解释**：多头排列是"趋势已成熟"的信号。突破交易的超额收益来自 surprise（超出市场预期），而非 confirmation（确认已有趋势）。逆势环境下的突破触发空头回补，产生更大涨幅。

#### 2. MA50 斜率(ma_slope_50)呈 U 型

MA50 斜率极负（下跌趋势中的逆势突破）和极正（强趋势加速突破）收益都高，中间段最差。U 型结构不适合现有的单调阈值系统。

#### 3. 均线偏离是 gte 而非 lte

价格远离 MA20 不意味着均值回归风险——在突破（regime change）场景下，动量效应主导。ma_pos_20 高 = 突破前 20 天累积买方力量强 = 后续惯性更大。

### ma_pos_20 三分位分组收益

| 分位 | 样本量 | 5日最高收益 | 10日最高收益 | 20日最高收益 |
|------|--------|-----------|------------|------------|
| Low | 42,792 | 2.3% | 4.0% | 6.6% |
| Mid | 42,790 | 3.5% | 6.1% | 10.0% |
| **High** | **42,792** | **7.8%** | **13.0%** | **22.2%** |

High vs Low t-test: t=35.85 (5d), t=44.76 (10d), t=20.22 (20d), 全部 p < 0.001。

### 与现有因子的互补性

| 现有因子 | 时间尺度 | 维度 | 与 ma_pos 的区别 |
|---------|---------|------|----------------|
| `day_str` | 1 天 | 突破日强度(σ) | 仅当天涨幅/跳空 |
| `pbm` | 5 天 | 路径效率型动量(σN) | 含位移/路径效率维度 |
| `overshoot` | 5 天 | 短期超涨(σ) | 波动率标准化的绝对涨幅 |
| **`ma_pos`** | **~20 天** | **位移型动量(%)** | **相对 MA 的百分比位置** |

ma_pos 填补了 "5 天 → 50 天" 之间的中期动量空白。

### 为什么只选 ma_pos_20 不加 ma_pos_50

- ma_pos_20 效应更强（rho 0.18 vs 0.12）
- 两者相关性 0.72，增量信息有限
- 通过 sub_param `period` (范围 10-50) 让 mining 自动搜索最优周期，优于注册两个冗余因子

## 架构决策

### 计算方式：直接读取 df 已有列

系统已通过 `TechnicalIndicators.add_indicators(df)` 预计算 `ma_20` 和 `ma_50` 列。`ma_pos` 的计算只需：

```python
ma_col = f"ma_{period}"  # 默认 "ma_20"
if ma_col in df.columns:
    ma_val = df[ma_col].iloc[idx]
    if pd.notna(ma_val) and ma_val > 0:
        return row["close"] / ma_val - 1.0
return 0.0
```

**不需要像 `atr_series` 那样预计算传入**——直接从 df 读取即可。

但需注意：当 sub_param `period` 不是 20 或 50 时，df 中没有对应的 `ma_N` 列。此时需在 `_calculate_ma_pos()` 内部用 `df["close"].rolling(period).mean()` 动态计算。

### sub_param `period` 的处理

参照现有的 `pk_lookback`、`continuity_lookback` 模式：
- 在 `FeatureCalculator.__init__` 中从 config 读取 `self.ma_pos_period`
- `_calculate_ma_pos()` 使用 `self.ma_pos_period` 作为周期

## 改动文件清单

### 1. `BreakoutStrategy/factor_registry.py`
- 注册 `ma_pos` 因子（FactorInfo + SubParamDef）

### 2. `BreakoutStrategy/analysis/breakout_detector.py`
- `Breakout` dataclass 新增 `ma_pos: float = 0.0` 字段

### 3. `BreakoutStrategy/analysis/features.py`
- `__init__` 新增 `self.ma_pos_period` 从 config 读取
- 新增 `_calculate_ma_pos(self, df, idx)` 方法
- `enrich_breakout()` 中调用并赋值到 Breakout 构造器

## 验证

1. 运行突破检测流程，确认 Breakout 对象 `ma_pos` 字段有合理值（大多数 > 0）
2. 确认 mining 管道能自动处理新因子（YAML 自动生成默认条目）
3. 确认 UI 参数编辑器自动显示 ma_pos 配置控件
