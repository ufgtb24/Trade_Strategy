# 数据驱动参数调优系统 - 设计方案

> 创建日期: 2025-12-12
> 状态: 设计阶段

## 一、问题诊断摘要

### 1.1 硬编码参数现状

| 分类 | 已配置化 | 硬编码 | 配置化占比 |
|------|---------|--------|-----------|
| 突破检测器 | 3 | 4 | 43% |
| 特征计算器 | 2 | 3 | 40% |
| 质量评分器 | 3组权重 | **28个阈值/分数** | 10% |
| 技术指标 | 0 | 7 | 0% |

**关键发现**: `quality_scorer.py` 中有28个硬编码的评分阈值和分数范围，这是调参的核心目标。

### 1.2 硬编码参数详细清单

#### breakthrough_detector.py

| 行号 | 参数名 | 值 | 用途 | 已配置化 |
|------|--------|-----|------|---------|
| 159 | window | 5 | 峰值识别窗口 | ✓ |
| 160 | exceed_threshold | 0.005 | 突破确认阈值(0.5%) | ✓ |
| 161 | peak_supersede_threshold | 0.03 | 峰值覆盖阈值(3%) | ✓ |
| 337 | window_start | 63 | 放量倍数历史窗口(63天) | ✗ |
| 346 | left_suppression_range | 60 | 压制天数最大回查天数 | ✗ |
| 356 | lookback_range | 60 | 相对高度历史回溯天数 | ✗ |
| 242 | cache_save_interval | 10 | 缓存保存间隔 | ✗ |

#### quality_scorer.py - 峰值评分

| 行号 | 参数名 | 值 | 用途 |
|------|--------|-----|------|
| 186 | quantity_score_range | (1,5,30,80) | 峰值数量评分范围 |
| 209 | cluster_size_3_score | 80 | 密集子集≥3基础分 |
| 212 | cluster_size_2_score | 60 | 密集子集=2基础分 |
| 214 | cluster_size_1_score | 40 | 密集子集=1基础分 |
| 217 | density_bonus_1pct | 20 | 密集度<1%加成 |
| 219 | density_bonus_3pct | 10 | 密集度<3%加成 |
| 226 | diversity_bonus | 10 | 多样性加成 |
| 235 | density_threshold | 0.03 | 密集度阈值(3%) |
| 306 | max_quality_80_bonus | 10 | 最高质量≥80加成 |
| 308 | max_quality_70_bonus | 5 | 最高质量≥70加成 |
| 315 | consistency_60_2pk | 10 | 一致性加成(≥60且≥2峰) |
| 317 | consistency_50_3pk | 5 | 一致性加成(≥50且≥3峰) |
| 378 | peak_volume_surge_range | (2.0,5.0) | 峰值放量评分范围 |
| 390 | peak_candle_change_range | (0.05,0.10) | 峰值K线涨跌幅范围 |
| 403 | peak_suppression_days_range | (30,60) | 峰值压制时间范围 |
| 415 | peak_relative_height_range | (0.05,0.10) | 峰值相对高度范围 |

#### quality_scorer.py - 突破评分

| 行号 | 参数名 | 值 | 用途 |
|------|--------|-----|------|
| 451 | bt_price_change_range | (0.03,0.06) | 突破价格变化范围 |
| 463 | bt_gap_up_range | (0.01,0.02) | 突破跳空范围 |
| 475 | bt_volume_surge_range | (2.0,5.0) | 突破放量范围 |
| 487 | bt_continuity_days_range | (3,5) | 突破连续性范围 |

#### features.py

| 行号 | 参数名 | 值 | 用途 | 已配置化 |
|------|--------|-----|------|---------|
| 25 | stability_lookforward | 10 | 稳定性评估天数 | ✓ |
| 26 | continuity_lookback | 5 | 连续性评估天数 | ✓ |
| 111 | candle_type_threshold | 0.01 | K线类型分类阈值 | ✗ |
| 129 | volume_window | 63 | 放量计算历史窗口 | ✗ |

### 1.3 现有数据收集能力

- **有**: `stability_score` (10天内不跌破峰值的比例，0-100分)
- **缺**: 真正的涨幅追踪 (最大涨幅、涨幅天数、回撤等)
- **缺**: 标签数据持久化机制

### 1.4 配置管理架构

现有三层架构成熟可复用：
```
File (YAML) → Memory (UIParamLoader) → Editor (UI)
```

---

## 二、系统设计方案

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          数据驱动参数调优系统                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ 1.参数配置化 │ →  │ 2.标签收集器 │ →  │ 3.优化引擎  │                 │
│  │             │    │             │    │             │                 │
│  │ YAML配置    │    │ 涨幅追踪    │    │ 贝叶斯优化  │                 │
│  │ 参数Schema  │    │ 数据持久化  │    │ 网格搜索    │                 │
│  │ UI编辑器   │    │ 历史回看    │    │ 评估指标    │                 │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         │                  │                  │                        │
│         └──────────────────┴──────────────────┘                        │
│                            │                                           │
│                    ┌───────▼───────┐                                  │
│                    │  4.评估仪表盘  │                                  │
│                    │               │                                  │
│                    │  参数版本对比  │                                  │
│                    │  收益分布图   │                                  │
│                    │  A/B测试结果  │                                  │
│                    └───────────────┘                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 2.2 模块1：参数配置化

#### 2.2.1 新增配置文件结构

```yaml
# configs/analysis/params/scoring_params.yaml (新文件)

# ==================== 峰值特征评分参数 ====================
peak_scoring:
  # 放量倍数评分范围
  volume_surge:
    low: 2.0      # 2倍以下得0分
    high: 5.0     # 5倍以上得100分

  # K线涨跌幅评分范围
  candle_change:
    low: 0.05     # 5%以下得0分
    high: 0.10    # 10%以上得100分

  # 压制天数评分范围
  suppression_days:
    low: 30       # 30天以下得0分
    high: 60      # 60天以上得100分

  # 相对高度评分范围
  relative_height:
    low: 0.05     # 5%以下得0分
    high: 0.10    # 10%以上得100分

# ==================== 突破特征评分参数 ====================
breakthrough_scoring:
  # 价格变化评分范围
  price_change:
    low: 0.03     # 3%以下得0分
    high: 0.06    # 6%以上得100分

  # 跳空评分范围
  gap_up:
    low: 0.01     # 1%以下得0分
    high: 0.02    # 2%以上得100分

  # 放量倍数评分范围
  volume_surge:
    low: 2.0      # 2倍以下得0分
    high: 5.0     # 5倍以上得100分

  # 连续性评分范围
  continuity_days:
    low: 3        # 3天以下得0分
    high: 5       # 5天以上得100分

# ==================== 阻力位质量评分参数 ====================
resistance_scoring:
  # 峰值数量评分范围
  quantity:
    min: 1        # 1个峰值时得30分
    max: 5        # 5+个峰值时得80分
    low_score: 30
    high_score: 80

  # 密集度评分参数
  density:
    threshold: 0.03          # 3%内视为密集
    cluster_3_score: 80      # ≥3个密集峰值
    cluster_2_score: 60      # =2个密集峰值
    cluster_1_score: 40      # =1个峰值
    bonus_1pct: 20           # <1%密集度加成
    bonus_3pct: 10           # <3%密集度加成
    diversity_bonus: 10      # 有密集+分散时加成

  # 质量评分参数
  quality:
    max_80_bonus: 10         # 最高质量≥80加成
    max_70_bonus: 5          # 最高质量≥70加成
    consistency_60_2pk: 10   # 最低≥60且≥2峰加成
    consistency_50_3pk: 5    # 最低≥50且≥3峰加成

# ==================== 通用计算参数 ====================
common:
  volume_lookback: 63        # 放量计算回看天数
  suppression_lookback: 60   # 压制天数计算范围
  height_lookback: 60        # 相对高度计算范围
  candle_type_threshold: 0.01 # K线类型分类阈值
```

#### 2.2.2 参数Schema扩展

```python
# BreakthroughStrategy/UI/config/param_editor_schema.py 扩展

SCORING_PARAM_CONFIGS = {
    "peak_scoring": {
        "volume_surge": {
            "type": dict,
            "is_range_param": True,
            "children": {
                "low": {"type": float, "range": (1.0, 10.0), "default": 2.0},
                "high": {"type": float, "range": (2.0, 20.0), "default": 5.0}
            }
        },
        # ... 其他参数
    },
    "breakthrough_scoring": { ... },
    "resistance_scoring": { ... },
    "common": { ... }
}
```

#### 2.2.3 配置文件分离策略

| 文件 | 职责 | 调整频率 |
|------|------|---------|
| `ui_params.yaml` | 检测器参数、权重 | 低 |
| `scoring_params.yaml` | 评分阈值、分数 | 高（调优目标） |
| `optimization_config.yaml` | 优化器参数 | 低 |

---

### 2.3 模块2：标签收集器

#### 2.3.1 数据结构设计

```python
# BreakthroughStrategy/analysis/label_collector.py (新文件)

@dataclass
class BreakthroughLabel:
    """突破点标签数据"""
    # 识别信息
    symbol: str
    breakthrough_date: date
    breakthrough_price: float
    quality_score: float

    # 后续表现（核心Label）
    max_gain_pct: float          # 最大涨幅 (%)
    max_gain_days: int           # 达到最高点的天数
    max_gain_price: float        # 最高价格

    # 回撤信息
    max_drawdown_pct: float      # 从最高点的最大回撤 (%)
    final_gain_pct: float        # 观察期结束时的涨幅 (%)

    # 风险指标
    holding_days: int            # 观察天数
    break_even_days: Optional[int]  # 首次回到突破价的天数

    # 元数据
    observation_end_date: date   # 观察期结束日期
    params_version: str          # 参数配置版本标识
```

#### 2.3.2 标签计算器

```python
class LabelCalculator:
    """计算突破点的后续表现标签"""

    def __init__(
        self,
        lookforward_days: int = 60,     # 观察期（交易日）
        early_stop_gain: float = 0.50,  # 提前结束涨幅阈值
        early_stop_loss: float = -0.20  # 提前结束亏损阈值
    ):
        self.lookforward_days = lookforward_days
        self.early_stop_gain = early_stop_gain
        self.early_stop_loss = early_stop_loss

    def calculate(
        self,
        df: pd.DataFrame,
        breakthrough_idx: int,
        symbol: str,
        quality_score: float
    ) -> Optional[BreakthroughLabel]:
        """
        计算单个突破点的标签

        Args:
            df: 完整OHLCV数据
            breakthrough_idx: 突破点索引
            symbol: 股票代码
            quality_score: 质量评分
        """
        bt_price = df.iloc[breakthrough_idx]['close']
        bt_date = df.iloc[breakthrough_idx]['date']

        # 获取后续数据
        future_start = breakthrough_idx + 1
        future_end = min(len(df), future_start + self.lookforward_days)

        if future_end <= future_start:
            return None  # 数据不足

        future_df = df.iloc[future_start:future_end]

        # 计算各项指标
        max_high = future_df['high'].max()
        max_gain_pct = (max_high - bt_price) / bt_price
        max_gain_idx = future_df['high'].argmax()
        max_gain_days = max_gain_idx + 1

        # 从最高点的回撤
        post_peak_df = future_df.iloc[max_gain_idx:]
        min_after_peak = post_peak_df['low'].min() if len(post_peak_df) > 0 else max_high
        max_drawdown_pct = (min_after_peak - max_high) / max_high

        # 最终涨幅
        final_price = future_df.iloc[-1]['close']
        final_gain_pct = (final_price - bt_price) / bt_price

        # 回本天数
        break_even_days = None
        below_entry = future_df[future_df['low'] < bt_price]
        if len(below_entry) > 0:
            first_below = below_entry.index[0]
            recovery = future_df.loc[first_below:][future_df['close'] >= bt_price]
            if len(recovery) > 0:
                break_even_days = recovery.index[0] - future_start + 1

        return BreakthroughLabel(
            symbol=symbol,
            breakthrough_date=bt_date,
            breakthrough_price=bt_price,
            quality_score=quality_score,
            max_gain_pct=max_gain_pct,
            max_gain_days=max_gain_days,
            max_gain_price=max_high,
            max_drawdown_pct=max_drawdown_pct,
            final_gain_pct=final_gain_pct,
            holding_days=len(future_df),
            break_even_days=break_even_days,
            observation_end_date=future_df.iloc[-1]['date'],
            params_version=self._get_params_version()
        )
```

#### 2.3.3 持久化方案

```yaml
# outputs/labels/breakthrough_labels_v1.0.json

{
  "metadata": {
    "version": "1.0",
    "params_snapshot": {
      "scoring_params_hash": "abc123...",
      "detection_params_hash": "def456..."
    },
    "collection_date": "2025-12-12",
    "lookforward_days": 60,
    "total_samples": 1234
  },
  "labels": [
    {
      "symbol": "AAPL",
      "breakthrough_date": "2024-05-30",
      "quality_score": 75.5,
      "max_gain_pct": 0.156,
      "max_gain_days": 12,
      ...
    }
  ]
}
```

---

### 2.4 模块3：参数优化引擎

#### 2.4.1 优化目标定义

```python
# BreakthroughStrategy/optimization/objectives.py (新文件)

class OptimizationObjective:
    """优化目标函数"""

    @staticmethod
    def expected_return(labels: List[BreakthroughLabel], score_threshold: float) -> float:
        """
        期望收益：高分突破点的平均最大涨幅

        目标：最大化高质量突破点的预期收益
        """
        filtered = [l for l in labels if l.quality_score >= score_threshold]
        if not filtered:
            return -1.0
        return np.mean([l.max_gain_pct for l in filtered])

    @staticmethod
    def win_rate(labels: List[BreakthroughLabel], score_threshold: float,
                 profit_threshold: float = 0.05) -> float:
        """
        胜率：高分突破点中盈利的比例

        目标：提高高质量突破点的成功率
        """
        filtered = [l for l in labels if l.quality_score >= score_threshold]
        if not filtered:
            return 0.0
        winners = [l for l in filtered if l.max_gain_pct >= profit_threshold]
        return len(winners) / len(filtered)

    @staticmethod
    def sharpe_ratio(labels: List[BreakthroughLabel], score_threshold: float) -> float:
        """
        夏普比率：风险调整后收益

        目标：在控制风险的前提下最大化收益
        """
        filtered = [l for l in labels if l.quality_score >= score_threshold]
        if not filtered:
            return -1.0
        returns = [l.max_gain_pct for l in filtered]
        return np.mean(returns) / (np.std(returns) + 1e-6)

    @staticmethod
    def profit_factor(labels: List[BreakthroughLabel], score_threshold: float) -> float:
        """
        盈亏比：总盈利/总亏损
        """
        filtered = [l for l in labels if l.quality_score >= score_threshold]
        if not filtered:
            return 0.0
        gains = sum(l.max_gain_pct for l in filtered if l.max_gain_pct > 0)
        losses = abs(sum(l.max_gain_pct for l in filtered if l.max_gain_pct < 0))
        return gains / (losses + 1e-6)
```

#### 2.4.2 优化器实现

```python
# BreakthroughStrategy/optimization/optimizer.py (新文件)

from optuna import Trial, create_study

class ScoringParamsOptimizer:
    """评分参数优化器"""

    def __init__(
        self,
        labels: List[BreakthroughLabel],
        objective: str = "sharpe_ratio",
        score_threshold: float = 70.0,
        n_trials: int = 100
    ):
        self.labels = labels
        self.objective_fn = getattr(OptimizationObjective, objective)
        self.score_threshold = score_threshold
        self.n_trials = n_trials

    def _suggest_params(self, trial: Trial) -> dict:
        """定义参数搜索空间"""
        return {
            "peak_scoring": {
                "volume_surge": {
                    "low": trial.suggest_float("pk_vol_low", 1.0, 3.0),
                    "high": trial.suggest_float("pk_vol_high", 3.0, 10.0)
                },
                "candle_change": {
                    "low": trial.suggest_float("pk_chg_low", 0.02, 0.08),
                    "high": trial.suggest_float("pk_chg_high", 0.05, 0.15)
                },
                # ... 其他参数
            },
            "breakthrough_scoring": { ... },
            "resistance_scoring": { ... }
        }

    def _evaluate(self, params: dict) -> float:
        """
        评估一组参数

        重新计算所有突破点的质量评分，然后计算目标函数
        """
        # 用新参数重新评分
        scorer = QualityScorer(params)
        updated_labels = []
        for label in self.labels:
            # 重新计算该突破点的质量评分
            new_score = scorer.recalculate_score(label)
            updated_label = dataclasses.replace(label, quality_score=new_score)
            updated_labels.append(updated_label)

        # 计算目标函数
        return self.objective_fn(updated_labels, self.score_threshold)

    def optimize(self) -> dict:
        """执行优化"""
        study = create_study(direction="maximize")

        def objective(trial: Trial) -> float:
            params = self._suggest_params(trial)
            return self._evaluate(params)

        study.optimize(objective, n_trials=self.n_trials)

        return {
            "best_params": study.best_params,
            "best_value": study.best_value,
            "optimization_history": study.trials_dataframe()
        }
```

#### 2.4.3 防过拟合策略

```python
class RobustOptimizer(ScoringParamsOptimizer):
    """带交叉验证的稳健优化器"""

    def __init__(
        self,
        labels: List[BreakthroughLabel],
        n_folds: int = 5,           # 时间序列交叉验证折数
        validation_ratio: float = 0.2,  # 最终验证集比例
        min_samples_per_fold: int = 50,
        **kwargs
    ):
        super().__init__(labels, **kwargs)
        self.n_folds = n_folds
        self.validation_ratio = validation_ratio
        self.min_samples_per_fold = min_samples_per_fold

        # 按时间排序并分割
        self.labels = sorted(labels, key=lambda x: x.breakthrough_date)
        self._split_data()

    def _split_data(self):
        """时间序列分割（不能随机打乱）"""
        n = len(self.labels)
        val_size = int(n * self.validation_ratio)

        self.train_labels = self.labels[:-val_size]
        self.val_labels = self.labels[-val_size:]

    def _cross_validate(self, params: dict) -> float:
        """时间序列交叉验证"""
        n = len(self.train_labels)
        fold_size = n // self.n_folds

        scores = []
        for i in range(self.n_folds - 1):
            # 训练集：前i+1个fold
            # 测试集：第i+2个fold
            train_end = (i + 1) * fold_size
            test_end = (i + 2) * fold_size

            test_labels = self.train_labels[train_end:test_end]
            if len(test_labels) < self.min_samples_per_fold:
                continue

            score = self._evaluate_on_subset(params, test_labels)
            scores.append(score)

        return np.mean(scores) if scores else -1.0

    def optimize(self) -> dict:
        """带验证的优化"""
        # 1. 在训练集上用交叉验证优化
        study = create_study(direction="maximize")

        def objective(trial: Trial) -> float:
            params = self._suggest_params(trial)
            return self._cross_validate(params)

        study.optimize(objective, n_trials=self.n_trials)
        best_params = study.best_params

        # 2. 在验证集上评估最终效果
        val_score = self._evaluate_on_subset(best_params, self.val_labels)
        train_score = study.best_value

        # 3. 检测过拟合
        overfit_ratio = (train_score - val_score) / (train_score + 1e-6)

        return {
            "best_params": best_params,
            "train_score": train_score,
            "validation_score": val_score,
            "overfit_ratio": overfit_ratio,
            "is_overfitted": overfit_ratio > 0.2  # 20%以上差异认为过拟合
        }
```

---

### 2.5 模块4：UI集成

#### 2.5.1 优化面板设计

```
┌─────────────────────────────────────────────────────────────┐
│  Parameter Optimization                            [X]      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─── Data Selection ───────────────────────────────────┐  │
│  │  Label File: [outputs/labels/v1.0.json     ▼]        │  │
│  │  Samples: 1,234  |  Date Range: 2023-01 ~ 2025-12    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── Optimization Settings ────────────────────────────┐  │
│  │  Objective:  [Sharpe Ratio ▼]                        │  │
│  │  Score Threshold: [70.0   ]  Trials: [100   ]        │  │
│  │  Cross Validation: [✓] 5-fold                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── Progress ─────────────────────────────────────────┐  │
│  │  [████████████████████░░░░░░░]  67/100 trials        │  │
│  │  Best Score: 1.234  |  Current: 1.156                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── Results ──────────────────────────────────────────┐  │
│  │  Train Score: 1.234  |  Val Score: 1.198             │  │
│  │  Overfit Ratio: 2.9% ✓                               │  │
│  │                                                       │  │
│  │  [View Best Params]  [Apply to Scorer]  [Export]     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│                           [Start Optimization]  [Cancel]    │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、实现路线图

### Phase 1: 参数配置化 (基础)

**目标**: 将所有硬编码参数提取到配置文件

**任务清单**:
1. 创建 `configs/analysis/params/scoring_params.yaml`
2. 修改 `QualityScorer.__init__()` 接受配置参数
3. 修改 `_linear_score()` 等方法从配置读取阈值
4. 扩展 `param_editor_schema.py` 支持评分参数
5. 更新 UI 参数编辑器支持新配置文件
6. 编写迁移脚本验证输出一致性

**验收标准**:
- 所有硬编码参数可通过 YAML 配置
- 默认配置产生与当前完全相同的评分结果

### Phase 2: 标签收集器 (数据)

**目标**: 为每个突破点记录后续表现

**任务清单**:
1. 实现 `BreakthroughLabel` 数据类
2. 实现 `LabelCalculator` 计算器
3. 扩展 `Breakthrough` 添加标签字段
4. 修改扫描流程自动收集标签
5. 实现 JSON 持久化
6. 添加历史数据批量标签生成脚本

**验收标准**:
- 扫描结果包含每个突破点的涨幅数据
- 标签数据可持久化和加载

### Phase 3: 优化引擎 (核心)

**目标**: 实现自动参数调优

**任务清单**:
1. 实现 `OptimizationObjective` 目标函数
2. 实现 `ScoringParamsOptimizer` 基础优化器
3. 实现 `RobustOptimizer` 交叉验证优化器
4. 添加优化结果持久化
5. 实现参数版本管理
6. 编写优化效果评估报告生成器

**验收标准**:
- 可自动搜索最优参数
- 有过拟合检测机制
- 优化结果可复现

### Phase 4: UI集成 (体验)

**目标**: 提供可视化调参界面

**任务清单**:
1. 创建优化对话框 UI
2. 实现优化进度展示
3. 添加参数对比功能
4. 添加结果导出功能
5. 集成到主菜单

**验收标准**:
- 用户可通过 UI 启动优化
- 可视化展示优化过程和结果

---

## 四、关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 配置文件分离 | 单独 `scoring_params.yaml` | 调优频率高，与检测参数解耦 |
| 优化算法 | Optuna (贝叶斯) | 效率高，支持剪枝，易于集成 |
| 防过拟合 | 时间序列CV | 股票数据有时间依赖性 |
| 目标函数 | 多指标可选 | 不同策略风格需要不同指标 |
| 标签观察期 | 60交易日 | 约3个月，平衡短期和中期 |

---

## 五、文件清单

### 新增文件

```
configs/analysis/params/scoring_params.yaml       # 评分参数配置
configs/analysis/params/optimization.yaml         # 优化器配置

BreakthroughStrategy/analysis/label_collector.py  # 标签收集器

BreakthroughStrategy/optimization/
├── __init__.py
├── objectives.py                                 # 目标函数
└── optimizer.py                                  # 优化引擎

BreakthroughStrategy/UI/dialogs/
└── optimization_dialog.py                        # 优化对话框

outputs/labels/                                   # 标签数据目录
```

### 修改文件

```
BreakthroughStrategy/analysis/quality_scorer.py   # 参数外部化
BreakthroughStrategy/analysis/features.py         # 添加标签计算
BreakthroughStrategy/UI/config/param_editor_schema.py  # 扩展schema
BreakthroughStrategy/UI/main.py                   # 添加优化菜单入口
```

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 标签数据不足 | 优化结果不可靠 | 最小样本量检查，警告提示 |
| 过拟合 | 实盘效果差 | 时间序列CV，独立验证集 |
| 计算耗时 | 用户体验差 | 后台异步执行，进度展示 |
| 参数版本混乱 | 结果不可复现 | 配置快照，版本哈希 |

---

## 七、后续扩展

1. **多目标优化**: 同时优化收益和风险
2. **在线学习**: 根据新数据持续调整参数
3. **A/B测试框架**: 新旧参数效果对比
4. **参数敏感性分析**: 识别关键参数
5. **自适应阈值**: 根据市场状态动态调整
