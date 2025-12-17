# 观察池评分系统重构研究报告：统一 Bonus 乘法模型与数据驱动阈值优化

> 版本: v2.0 | 日期: 2025-12-29
> 范围: 观察池买入条件评分系统架构优化

---

## Executive Summary

本报告深入分析了将观察池评分系统从当前的加权求和模型**全面迁移**到 Bonus 乘法模型的可行性，并设计了通过数据挖掘自动寻找最优阈值的完整方案。

**核心结论**：
1. **技术可行**：现有 BreakoutScorer 的 Bonus 模型已验证可行，扩展到买入评估场景架构上无障碍
2. **数据充足**：10,855 支股票的历史数据足以支持有效的参数优化和交叉验证
3. **价值显著**：解决价位敏感性问题，实现参数可解释、可调优、可适应市场变化
4. **风险可控**：通过股票分层、时间序列验证、参数稳定性分析可有效防止过拟合

---

## 一、当前评分系统分析

### 1.1 硬编码问题清单

经过对六个核心文件的完整分析，提取出所有硬编码的评分逻辑：

#### (A) price_confirm.py - 价格确认评估器

| 位置 | 硬编码值 | 问题描述 |
|------|---------|----------|
| L157 | `30 - excess * 1000` | 系数 1000 与股票价位无关，对低价股惩罚过重 |
| L163 | `70 - ratio * 40` | 回踩区间固定从 70 分降到 30 分 |
| L169 | `70 + ratio * 30` | 低于最优区间的分数曲线固定 |
| L173 | `return 100` | 最优区间满分，缺乏对边界情况的细分 |
| L182 | `100 - ratio * 50` | 追高区间惩罚系数固定 |
| L114 | `score=30` | 超过最大追高比例的固定低分 |

**核心问题**：线性插值的系数（如 40、30、50、1000）都是硬编码，且未考虑股票价位差异。

#### (B) time_window.py - 时间窗口评估器

| 位置 | 硬编码值 | 问题描述 |
|------|---------|----------|
| L32-37 | `window_scores` 字典 | optimal=1.0, acceptable=0.7, marginal=0.4, avoid=0.0 |
| L24-26 | `time(10, 0), time(11, 30)` | 最佳窗口固定 |
| L28 | `open_avoid_minutes: 30` | 开盘避让固定 30 分钟 |

#### (C) volume_verify.py - 成交量验证评估器

| 位置 | 硬编码值 | 问题描述 |
|------|---------|----------|
| L91 | `score=70` | 无基准时默认中等分数 |
| L174 | `return 10` | 极度缩量固定 10 分 |
| L178 | `10 + (ratio - 0.5) * 80` | 缩量区间分数曲线 |
| L182 | `50 + (ratio - 1.0) * 100` | 正常量能区间 |
| L186 | `70 + ... * 20` | 温和放量区间 |
| L190 | `90 + ... * 10` | 强放量区间 |

**核心问题**：量比阈值（0.5, 1.0, 1.2, 1.5, 2.0）和对应分数都是硬编码，且分段线性函数的斜率固定。

#### (D) risk_filter.py - 风险过滤评估器

| 位置 | 硬编码值 | 问题描述 |
|------|---------|----------|
| L120 | `score - 20` | 超时惩罚固定 20 分 |
| L133 | `score - 30` | 连续阴线惩罚固定 30 分 |
| L217 | `drop_pct < 0.02` | 巨量阴线的跌幅阈值 2% |
| L224 | `volume_ratio > 3.0` | 巨量阴线的量比阈值 3 倍 |

#### (E) composite.py - 组合评估器

| 位置 | 硬编码值 | 问题描述 |
|------|---------|----------|
| L157 | `0.5 + (quality_score/100) * 0.5` | 质量因子范围 0.5-1.0 |
| L273-282 | 仓位计算的分数阈值 | `score >= 80 -> 0.15` 等 |

#### (F) config.py - 配置数据类

| 配置项 | 默认值 | 备注 |
|--------|--------|------|
| min_breakout_margin | 0.01 (1%) | 价格确认下限 |
| max_breakout_margin | 0.02 (2%) | 价格确认上限 |
| pullback_tolerance | 0.03 (3%) | 回踩容忍度 |
| remove_threshold | 0.03 (3%) | 移出阈值 |
| max_chase_pct | 0.05 (5%) | 最大追高比例 |
| strong/normal buy threshold | 70/50 | 买入阈值 |

### 1.2 现有模型的根本性缺陷

**问题 1：价位不敏感**

```python
# price_confirm.py:156-157
excess = abs(margin) - pullback
return max(0, 30 - excess * 1000)  # 系数 1000 对所有股票一视同仁
```

- $5 股票波动 1% = $0.05（常见）
- $500 股票波动 1% = $5.00（显著）
- 同样的百分比偏离，对不同价位股票的意义完全不同

**问题 2：线性假设不成立**

当前评分假设指标与成功概率是线性关系，但实际上：
- 量比从 1.0 到 1.5 的边际效用，可能远大于从 2.0 到 2.5
- 这是典型的边际效用递减规律

**问题 3：权重归一化的局限**

```python
# 当前加权模型
total_score = time_score * 0.20 + price_score * 0.30 + volume_score * 0.25 + quality_score * 0.25
```

加权求和模型要求权重归一化，导致：
- 某维度极差时，其他维度的高分可以"补救"
- 无法表达"某条件必须满足"的硬约束

---

## 二、BreakoutScorer Bonus 模型分析

### 2.1 设计模式提取

现有的 `BreakoutScorer` 实现了成熟的 Bonus 乘法模型：

```
总分 = BASE × age_bonus × test_bonus × height_bonus × peak_volume_bonus ×
       volume_bonus × gap_bonus × pbm_bonus × momentum_bonus
```

**核心设计要素**：

1. **基准分 (BASE)**：存在有效突破这件事本身的价值（默认 50）

2. **阶梯阈值配置**：每个 Bonus 有多级阈值
   ```python
   age_bonus_thresholds = [21, 63, 252]  # 1月, 3月, 1年
   age_bonus_values = [1.15, 1.30, 1.50]
   ```

3. **统一的 Bonus 计算接口**：
   ```python
   def _get_bonus_value(self, value, thresholds, bonus_values) -> tuple[float, int]:
       """返回 (bonus_multiplier, triggered_level)"""
   ```

4. **BonusDetail 数据类**：记录每个因子的详细信息
   ```python
   @dataclass
   class BonusDetail:
       name: str           # 显示名称
       raw_value: float    # 原始数值
       unit: str           # 单位
       bonus: float        # bonus 乘数
       triggered: bool     # 是否触发
       level: int          # 触发级别
   ```

5. **配置外化**：所有阈值和乘数都从 YAML 配置读取

### 2.2 Bonus 模型的数学优势

| 特性 | 加法模型 | 乘法模型 |
|------|---------|---------|
| 公式 | `sum(score_i * weight_i)` | `base * prod(bonus_i)` |
| 权重约束 | 必须归一化 | 无需归一化 |
| 极值处理 | 高分可补救低分 | 任一 bonus=0 则总分=0 |
| 边际效用 | 固定 | 可通过阈值设计体现递减 |
| 可解释性 | "贡献了 X%" | "放大了 X 倍" |

**乘法模型更符合交易逻辑**：
- "所有条件都满足" 比 "平均得分高" 更重要
- 某一维度极差（如跌破阈值）应该直接否决，而非被平均

---

## 三、统一 Bonus 评分系统设计

### 3.1 股票分层机制

#### 3.1.1 分层维度与边界

**维度 1：价位层 (Price Tier)**
```
low_price:    $0 - $20     (大量小票，波动大，流动性差)
mid_price:    $20 - $100   (主流交易标的)
high_price:   $100 - $500  (蓝筹股，波动相对稳定)
mega_price:   $500+        (超高价股，如 AMZN、BRK.A)
```

**维度 2：波动率层 (Volatility Tier)**
```
low_vol:      ATR% < 2%    (低波动，如公用事业)
mid_vol:      ATR% 2%-5%   (正常波动)
high_vol:     ATR% > 5%    (高波动，如科技成长股)
```

#### 3.1.2 分层配置示例

```yaml
stock_tiers:
  # === 低价股 ($0-20) ===
  low_price:
    price_range: [0, 20]
    atr_multiplier: 1.5  # ATR 相关阈值放宽 50%

    price_bonus:
      thresholds: [0.3, 0.7, 1.0]  # ATR 倍数
      values: [1.15, 1.25, 1.35]

    volume_bonus:
      thresholds: [2.0, 3.0, 5.0]  # 量比（更高要求过滤噪音）
      values: [1.10, 1.20, 1.35]

    risk_penalty:
      drop_threshold_atr: 2.0  # 跌破 2 倍 ATR 才触发

  # === 中价股 ($20-100) ===
  mid_price:
    price_range: [20, 100]
    atr_multiplier: 1.0

    price_bonus:
      thresholds: [0.5, 1.0, 1.5]
      values: [1.15, 1.30, 1.45]

    volume_bonus:
      thresholds: [1.5, 2.0, 3.0]
      values: [1.15, 1.25, 1.35]

    risk_penalty:
      drop_threshold_atr: 1.5

  # === 高价股 ($100-500) ===
  high_price:
    price_range: [100, 500]
    atr_multiplier: 0.8  # ATR 阈值收紧

    price_bonus:
      thresholds: [0.7, 1.2, 2.0]
      values: [1.20, 1.35, 1.50]

    volume_bonus:
      thresholds: [1.2, 1.5, 2.0]
      values: [1.15, 1.30, 1.40]

    risk_penalty:
      drop_threshold_atr: 1.2
```

### 3.2 Bonus 因子设计

#### 3.2.1 时间窗口 Bonus (time_bonus)

```python
@dataclass
class TimeBonusConfig:
    period_bonuses: Dict[str, float] = field(default_factory=lambda: {
        'optimal': 1.20,      # 最佳时段加成 20%
        'acceptable': 1.00,   # 可接受时段无加成
        'marginal': 0.80,     # 边际时段惩罚 20%
        'avoid': 0.00,        # 避开时段 -> 总分归零（直接否决）
    })
```

#### 3.2.2 价格确认 Bonus (price_bonus) - 关键改进

**核心改进：使用 ATR 标准化消除价位敏感性**

```python
def calculate_price_bonus(
    current_price: float,
    reference_price: float,
    atr: float,
    tier_config: TierConfig
) -> BonusDetail:
    """
    计算价格确认 Bonus

    ATR 标准化：
    deviation_atr = (current_price - reference_price) / atr

    效果：
    - $5 股票 ATR=$0.50，涨 $0.25 = 0.5 ATR
    - $500 股票 ATR=$10，涨 $5 = 0.5 ATR
    - 同样的 0.5 ATR 偏离，获得相同的评价
    """
    deviation_atr = (current_price - reference_price) / atr

    # 应用层级的 ATR 调整系数
    adjusted_deviation = deviation_atr / tier_config.atr_multiplier

    cfg = tier_config.price_bonus

    # 检查是否跌破（直接否决）
    if adjusted_deviation < -cfg.drop_threshold_atr:
        return BonusDetail("Price", deviation_atr, "xATR", 0.00, False, -1)

    # 检查是否追高
    if adjusted_deviation > cfg.chase_threshold_atr:
        return BonusDetail("Price", deviation_atr, "xATR", cfg.chase_penalty, False, -2)

    # 正常区间：使用阈值配置
    bonus, level = get_bonus_from_thresholds(
        adjusted_deviation,
        cfg.thresholds,
        cfg.values
    )

    return BonusDetail("Price", deviation_atr, "xATR", bonus, bonus > 1.0, level)
```

**配置示例**：
```yaml
price_bonus:
  # 基于 ATR 的价格偏离区间
  optimal_range:
    min_atr: 0.3   # 最优区间下限：+0.3 ATR
    max_atr: 1.0   # 最优区间上限：+1.0 ATR
    bonus: 1.30    # 最优区间 bonus

  chase_penalty:
    threshold_atr: 2.0  # 超过 +2.0 ATR 视为追高
    penalty: 0.60       # 追高惩罚（乘以 0.6）

  drop_penalty:
    threshold_atr: -1.5  # 跌破 -1.5 ATR
    penalty: 0.00        # 直接否决（触发移出）
```

#### 3.2.3 成交量确认 Bonus (volume_bonus)

```python
@dataclass
class VolumeBonusConfig:
    thresholds: List[float] = field(default_factory=lambda: [1.5, 2.0, 3.0])
    values: List[float] = field(default_factory=lambda: [1.15, 1.25, 1.40])

    shrink_threshold: float = 0.8
    shrink_penalty: float = 0.70
```

#### 3.2.4 质量继承 Bonus (quality_bonus)

```python
def calculate_quality_bonus(quality_score: float) -> BonusDetail:
    """
    将 0-200 范围的突破质量评分转换为 bonus 乘数

    quality_score < 50:   惩罚 (bonus < 1.0)
    quality_score = 50:   无加成 (bonus = 1.0)
    quality_score > 50:   加成 (bonus > 1.0)
    """
    if quality_score < 50:
        bonus = 0.5 + (quality_score / 50) * 0.5  # 0.5 - 1.0
    elif quality_score < 100:
        bonus = 1.0 + ((quality_score - 50) / 50) * 0.3  # 1.0 - 1.3
    else:
        bonus = 1.3 + ((min(quality_score, 200) - 100) / 100) * 0.3  # 1.3 - 1.6

    return BonusDetail("Quality", quality_score, "pt", bonus, bonus > 1.0, 0)
```

#### 3.2.5 风险惩罚因子 (risk_penalty)

```python
@dataclass
class RiskPenaltyConfig:
    # 跌破惩罚（基于 ATR）
    drop_penalty_tiers: List[Tuple[float, float]] = field(default_factory=lambda: [
        (1.0, 0.90),   # 跌破 1.0 ATR -> 惩罚 10%
        (1.5, 0.70),   # 跌破 1.5 ATR -> 惩罚 30%
        (2.0, 0.00),   # 跌破 2.0 ATR -> 移出
    ])

    # 跳空惩罚
    gap_penalty_tiers: List[Tuple[float, float]] = field(default_factory=lambda: [
        (1.5, 0.85),   # 跳空 > 1.5 ATR -> 惩罚 15%
        (2.5, 0.50),   # 跳空 > 2.5 ATR -> 惩罚 50%
        (4.0, 0.00),   # 跳空 > 4.0 ATR -> 跳过
    ])

    # 持仓天数惩罚
    holding_penalty_tiers: List[Tuple[int, float]] = field(default_factory=lambda: [
        (15, 0.95),    # > 15 天 -> 惩罚 5%
        (25, 0.85),    # > 25 天 -> 惩罚 15%
        (35, 0.70),    # > 35 天 -> 惩罚 30%
    ])

    # 连续阴线惩罚
    red_candle_penalty_tiers: List[Tuple[int, float]] = field(default_factory=lambda: [
        (3, 0.90),     # 3 根阴线 -> 惩罚 10%
        (4, 0.75),     # 4 根阴线 -> 惩罚 25%
        (5, 0.50),     # 5 根阴线 -> 惩罚 50%
    ])
```

### 3.3 综合评分公式

```
BuyScore = BASE
         × time_bonus
         × price_bonus
         × volume_bonus
         × quality_bonus
         × risk_penalty

其中：
- BASE = 50（存在有效买入机会这件事的基础价值）
- time_bonus >= 0（避开时段为 0，即直接否决）
- price_bonus > 0（跌破阈值为 0，即直接否决）
- volume_bonus >= 0.5
- quality_bonus: 0.5 - 1.6
- risk_penalty: 0.0 - 1.0（多重风险因子相乘）
```

**决策阈值**：
```yaml
decision_thresholds:
  strong_buy: 60    # 总分 >= 60
  normal_buy: 45    # 总分 >= 45
  hold: 30          # 总分 >= 30，继续观察
  remove: 0         # 任一关键 bonus = 0 触发
```

---

## 四、数据挖掘调参方案

### 4.1 训练数据准备

#### 4.1.1 样本定义

**正样本 (成功买入)**：
```python
def is_successful_buy(
    entry_date: date,
    entry_price: float,
    future_prices: pd.DataFrame,
    config: SuccessCriteriaConfig
) -> bool:
    """
    成功标准（任一满足）：
    1. N 天内最高收益 > X%
    2. N 天内收盘价收益 > Y%

    失败标准：
    1. N 天内跌破止损线
    2. 最大回撤 > Z%
    """
```

**配置示例**：
```yaml
success_criteria:
  holding_days: 10      # 评估窗口
  target_gain: 0.08     # 目标收益 8%
  min_close_gain: 0.03  # 最小收盘收益 3%
  stop_loss: 0.05       # 止损线 5%

  # ATR 标准化版本（推荐）
  target_gain_atr: 2.0  # 目标收益 2 倍 ATR
  stop_loss_atr: 1.5    # 止损 1.5 倍 ATR
```

#### 4.1.2 特征工程

```python
@dataclass
class BuySampleFeatures:
    # === 股票属性 ===
    symbol: str
    price: float
    price_tier: str
    atr: float
    atr_pct: float

    # === 价格确认特征（ATR 标准化）===
    price_deviation_atr: float
    distance_to_breakout_atr: float
    distance_to_peak_atr: float

    # === 成交量特征 ===
    volume_ratio: float
    volume_ratio_5d: float

    # === 时间特征 ===
    days_since_breakout: int
    days_in_pool: int

    # === 质量继承特征 ===
    breakout_quality_score: float

    # === 风险特征 ===
    consecutive_red_count: int
    gap_up_atr: float
    recent_drawdown_atr: float

    # === 标签 ===
    label: int  # 1=成功, 0=失败
    future_max_gain: float
```

### 4.2 阈值寻优方法

#### 4.2.1 方法对比

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| 网格搜索 | 简单直观，全局覆盖 | 计算量大 | 参数少 (<5) 的粗调 |
| 贝叶斯优化 | 样本效率高 | 可能局部最优 | 参数多 (5-20) 的精调 |
| 决策树挖掘 | 可解释性强 | 不直接优化目标 | 初始阈值探索 |

**推荐组合**：
1. 先用**决策树**挖掘初始阈值区间
2. 再用**贝叶斯优化**精调
3. 最后用**网格搜索**做局部验证

#### 4.2.2 决策树阈值挖掘

```python
def mine_thresholds_with_tree(
    X: pd.DataFrame,
    y: np.ndarray,
    feature_name: str,
    max_depth: int = 3
) -> List[float]:
    """
    使用决策树挖掘单特征的最佳阈值
    原理：决策树的分裂点就是自然阈值
    """
    tree = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=50)
    tree.fit(X[[feature_name]], y)

    # 提取分裂阈值
    thresholds = extract_split_thresholds(tree)
    return sorted(set(thresholds))
```

#### 4.2.3 贝叶斯优化

```python
def optimize_thresholds_bayesian(
    X: pd.DataFrame,
    y: np.ndarray,
    n_calls: int = 100
) -> BonusConfig:
    """使用贝叶斯优化寻找最佳阈值"""

    space = [
        # price_bonus 阈值
        Real(0.1, 0.5, name='price_t1'),
        Real(0.5, 1.0, name='price_t2'),
        Real(1.0, 2.0, name='price_t3'),
        # ... 其他参数
    ]

    def objective(params):
        config = params_to_config(params)
        scores = BonusBuyScorer(config).score_batch(X)
        y_pred = (scores >= config.normal_buy_threshold).astype(int)

        # 综合目标：F1 + 盈利因子
        f1 = f1_score(y, y_pred)
        profit_factor = calculate_profit_factor(y, y_pred)
        return -(0.5 * f1 + 0.5 * min(profit_factor / 2, 1))

    result = gp_minimize(objective, space, n_calls=n_calls)
    return params_to_config(result.x)
```

### 4.3 验证与防过拟合

#### 4.3.1 时间序列交叉验证

```python
def time_series_cross_validation(
    X: pd.DataFrame,
    y: np.ndarray,
    n_splits: int = 5
) -> Dict[str, List[float]]:
    """
    时间序列交叉验证
    确保训练集总是在测试集之前
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)

    for train_idx, test_idx in tscv.split(X):
        # 在训练集上优化
        optimized_config = optimize_thresholds(X.iloc[train_idx], y[train_idx])
        # 在测试集上评估
        test_metrics = evaluate(X.iloc[test_idx], y[test_idx], optimized_config)
```

#### 4.3.2 参数稳定性分析

```python
def parameter_stability_analysis(
    X: pd.DataFrame,
    y: np.ndarray,
    n_bootstrap: int = 50
) -> pd.DataFrame:
    """
    通过 bootstrap 采样多次优化，检查参数是否稳定
    CV (变异系数) < 0.2：参数稳定
    CV > 0.5：参数不稳定，可能过拟合
    """
```

### 4.4 股票分层调参

```python
def tier_specific_optimization(
    samples_df: pd.DataFrame,
    tier_column: str = 'price_tier'
) -> Dict[str, BonusConfig]:
    """对每个层级独立优化参数"""
    tier_configs = {}

    for tier in samples_df[tier_column].unique():
        tier_samples = samples_df[samples_df[tier_column] == tier]

        if len(tier_samples) < MIN_SAMPLES_PER_TIER:
            tier_configs[tier] = global_config.copy()
            continue

        tier_configs[tier] = optimize_thresholds_bayesian(
            tier_samples[feature_columns],
            tier_samples['label'].values
        )

    return tier_configs
```

---

## 五、实现方案设计

### 5.1 核心数据结构

```python
# bonus_config.py

@dataclass
class BonusThresholds:
    """单个 Bonus 的阈值配置"""
    thresholds: List[float]
    values: List[float]
    unit: str = ''

@dataclass
class TierConfig:
    """单个股票层级的完整配置"""
    name: str
    price_range: Tuple[float, float]
    atr_multiplier: float = 1.0

    time_bonus: TimeBonusConfig
    price_bonus: PriceBonusConfig
    volume_bonus: VolumeBonusConfig
    quality_bonus: QualityBonusConfig
    risk_penalty: RiskPenaltyConfig

@dataclass
class BonusBuyConfig:
    """买入评估的完整 Bonus 配置"""
    base_score: float = 50.0
    strong_buy_threshold: float = 60.0
    normal_buy_threshold: float = 45.0
    hold_threshold: float = 30.0

    tiers: Dict[str, TierConfig]
    default_tier: TierConfig

    def get_tier_config(self, price: float) -> TierConfig:
        """根据价格获取对应的层级配置"""
        for tier in self.tiers.values():
            if tier.price_range[0] <= price < tier.price_range[1]:
                return tier
        return self.default_tier
```

### 5.2 评分器实现

```python
# bonus_buy_scorer.py

class BonusBuyScorer:
    """买入条件评分器（Bonus 乘法模型）"""

    def __init__(self, config: BonusBuyConfig):
        self.config = config

    def score(
        self,
        entry: PoolEntry,
        current_bar: pd.Series,
        atr: float,
        context: Optional[dict] = None
    ) -> BuyScoreBreakdown:
        """计算买入评分"""
        tier_config = self.config.get_tier_config(current_bar['close'])

        bonuses = []
        bonuses.append(self._calc_time_bonus(context, tier_config))
        bonuses.append(self._calc_price_bonus(current_bar, entry, atr, tier_config))
        bonuses.append(self._calc_volume_bonus(context, tier_config))
        bonuses.append(self._calc_quality_bonus(entry, tier_config))
        bonuses.append(self._calc_risk_penalty(entry, current_bar, atr, context, tier_config))

        total_multiplier = 1.0
        for b in bonuses:
            total_multiplier *= b.bonus

        total_score = self.config.base_score * total_multiplier
        action, reason = self._determine_action(total_score, bonuses)

        return BuyScoreBreakdown(
            symbol=entry.symbol,
            base_score=self.config.base_score,
            total_score=total_score,
            bonuses=bonuses,
            tier_used=tier_config.name,
            action=action,
            reason=reason
        )
```

### 5.3 完整配置文件格式

```yaml
# configs/params/buy_bonus_params.yaml

base_score: 50.0
strong_buy_threshold: 60.0
normal_buy_threshold: 45.0
hold_threshold: 30.0

tiers:
  low_price:
    price_range: [0, 20]
    atr_multiplier: 1.5

    time_bonus:
      period_bonuses:
        optimal: 1.15
        acceptable: 1.00
        marginal: 0.85
        avoid: 0.00

    price_bonus:
      thresholds: [0.0, 0.2, 0.5, 0.8]
      values: [0.90, 1.00, 1.15, 1.25]
      chase_threshold_atr: 2.5
      chase_penalty: 0.60
      drop_threshold_atr: 2.0
      drop_penalty: 0.00

    volume_bonus:
      thresholds: [2.0, 3.0, 5.0]
      values: [1.10, 1.20, 1.35]
      shrink_threshold: 1.0
      shrink_penalty: 0.75

    quality_bonus:
      breakpoints: [[0, 0.50], [50, 1.00], [100, 1.25], [200, 1.50]]

    risk_penalty:
      drop_penalties: [[1.5, 0.90], [2.0, 0.70], [2.5, 0.00]]
      gap_penalties: [[2.0, 0.85], [3.0, 0.50], [5.0, 0.00]]
      holding_penalties: [[20, 0.95], [30, 0.85], [40, 0.70]]

  mid_price:
    price_range: [20, 100]
    atr_multiplier: 1.0
    # ... 中价股配置

  high_price:
    price_range: [100, 500]
    atr_multiplier: 0.8
    # ... 高价股配置
```

### 5.4 调参流水线

```
scripts/optimization/
├── 01_extract_samples.py      # 样本提取
├── 02_compute_features.py     # 特征计算
├── 03_mine_thresholds.py      # 决策树阈值挖掘
├── 04_optimize_bayesian.py    # 贝叶斯优化
├── 05_validate_results.py     # 验证与稳定性分析
├── 06_generate_config.py      # 生成最终配置
└── run_pipeline.py            # 流水线入口
```

---

## 六、可行性与风险分析

### 6.1 技术可行性

| 评估维度 | 现状 | 结论 |
|----------|------|------|
| **数据量** | 10,855 支股票历史数据 | 足够支持分层调参 |
| **计算复杂度** | 贝叶斯优化 ~100 次迭代/层 | 可在数小时内完成 |
| **基础设施** | BreakoutScorer 已实现 Bonus 模型 | 架构可复用 |

**数据量评估**：
- 10,855 支股票 × 10 条目/股 × 10 天/条目 ≈ **100万样本**
- 按 4 个价位层分：每层约 **25万样本**，远超统计学习的最低要求

### 6.2 风险与缓解措施

| 风险 | 描述 | 缓解措施 |
|------|------|---------|
| **过拟合** | 参数过度适配历史 | 时间序列 CV + 稳定性分析 |
| **Regime Change** | 牛熊市参数不同 | 分 regime 调参 + 滚动更新 |
| **样本不平衡** | 成功样本可能较少 | 类别权重调整 + F-beta |
| **特征漂移** | ATR 等特征会变化 | 使用相对特征 + 动态分层 |

### 6.3 渐进式实施建议

| 阶段 | 内容 | 周期 |
|------|------|------|
| Phase 1 | 实现 Bonus 评分器作为影子系统，对比差异 | 2-4 周 |
| Phase 2 | 样本提取 + 特征工程 + 阈值优化 | 4-6 周 |
| Phase 3 | A/B 测试：部分股票使用新系统 | 4-8 周 |
| Phase 4 | 全面迁移，建立定期更新机制 | 2-4 周 |

---

## 七、结论与建议

### 7.1 核心结论

1. **技术可行**：将观察池评分系统迁移到 Bonus 乘法模型完全可行，BreakoutScorer 架构可直接复用

2. **价值显著**：
   - 解决价位敏感性问题（通过 ATR 标准化）
   - 实现参数可解释、可调优、可自动化优化
   - 乘法模型更符合交易逻辑（致命条件直接否决）

3. **数据充足**：100万+样本足以支持分层调参和可靠的交叉验证

4. **风险可控**：通过时间序列验证、参数稳定性分析、滚动更新机制可有效控制过拟合

### 7.2 实施优先级

| 优先级 | 任务 | 预计工时 | 价值 |
|--------|------|----------|------|
| P0 | ATR 标准化的价格确认 Bonus | 3-5 天 | 高 - 解决核心痛点 |
| P1 | 股票分层配置框架 | 2-3 天 | 高 - 架构基础 |
| P2 | 样本提取与特征工程 | 5-7 天 | 高 - 数据基础 |
| P3 | 贝叶斯优化流水线 | 5-7 天 | 中 - 自动化调参 |
| P4 | A/B 测试框架 | 3-5 天 | 中 - 验证机制 |

---

## 八、关键文件索引

```
# 现有评估系统（待重构）
BreakoutStrategy/observation/evaluators/components/price_confirm.py
BreakoutStrategy/observation/evaluators/components/time_window.py
BreakoutStrategy/observation/evaluators/components/volume_verify.py
BreakoutStrategy/observation/evaluators/components/risk_filter.py
BreakoutStrategy/observation/evaluators/composite.py
BreakoutStrategy/observation/evaluators/config.py

# 参考 Bonus 模型
BreakoutStrategy/analysis/breakout_scorer.py
configs/params/scan_params.yaml

# 数据集
datasets/pkls/ (10,855 支股票)
```

---

*报告完成。如需进一步细化任何部分的设计细节，请告知。*
