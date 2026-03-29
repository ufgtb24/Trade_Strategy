# 分层阈值挖掘设计方案

## Executive Summary

当前阈值挖掘管线 (`threshold_optimizer`) 对 $1-10 全价格区间的 9810 条数据统一优化，产出一套全局阈值。但不同价格区间的 label median 差异显著（$1-3: 0.254, $3-5: 0.192, $5-7: 0.134, $7-10: 0.093），全局优化的阈值会被高回报的低价股主导，对 $7-10 区间的选择力不足。

本方案在**最小改动**前提下，为挖掘管线添加**价格分层**能力：按价格区间分别运行阈值优化，产出分层参数，并在生产评分器中按突破价格路由到对应参数。

**核心设计原则**：在 `pipeline.py` 层添加循环，复用 `threshold_optimizer.main()` 的全部搜索逻辑；扩展 YAML 格式而非重写；保持全局/分层可切换。

---

## 1. 分层策略：2 层方案

### 1.1 为什么不用 4 层

| 方案 | 分层 | 最小区间样本量 | 优缺点 |
|------|------|--------------|--------|
| 2 层 | $1-5, $5-10 | ~4274 | 数据充足, 两层差异已显著 |
| 3 层 | $1-3, $3-7, $7-10 | ~1613 | $7-10 偏少, 但勉强可行 |
| 4 层 | $1-3, $3-5, $5-7, $7-10 | ~1613 | 颗粒度过细, 最小区间仅 1613 条 |

**推荐 2 层**。理由：

1. **数据量安全**: $5-10 区间有 4274 条, $1-5 有 5536 条，两层都远超 `min_count=20` 的最低要求
2. **统计显著性**: 两层的 label median 差异足够大 ($1-5: ~0.22 vs $5-10: ~0.12)，优化空间明确
3. **过拟合控制**: 分层越多，每层数据越少，过拟合风险越大。2 层是精度与稳健性的最佳平衡点
4. **Optuna 搜索效率**: 每层仍有 4000-5500 样本，TPE 搜索空间探索充分

### 1.2 分层边界配置

```yaml
# pipeline.py 中的分层配置
price_tiers:
  - name: "low"      # $1-5
    min_price: 0.0
    max_price: 5.0
  - name: "high"     # $5-10
    min_price: 5.0
    max_price: 999.0
```

分层边界设为 $5 的理由：
- $5 是美股常见的 penny stock 分界线 (SEC/FINRA 定义)
- 恰好将 9810 条数据近似等分（5536 vs 4274）
- $5 以下和以上的流动性特征、波动率模式有本质差异

---

## 2. 改动文件清单

### 2.1 需要修改的文件（4 个）

| 文件 | 改动内容 | 改动量 |
|------|---------|--------|
| `pipeline.py` | 添加分层循环逻辑 + 分层配置 | ~50 行 |
| `param_writer.py` | 支持读取分层 `bonus_filter.yaml`，生成分层 `all_bonus_mined.yaml` | ~40 行 |
| `breakout_scorer.py` | `__init__` 接受分层配置，`score_breakout` 按价格路由 | ~30 行 |
| `param_loader.py` | `get_scorer_params()` 解析分层 YAML 格式 | ~20 行 |

### 2.2 不需要修改的文件

| 文件 | 原因 |
|------|------|
| `threshold_optimizer.py` | 核心搜索逻辑完全复用，仅接收不同的 DataFrame 子集 |
| `template_generator.py` | 输出格式不变，被 pipeline 调用时传入子集即可 |
| `factor_registry.py` | 因子定义不变 |
| `data_pipeline.py` | DataFrame 构建逻辑不变，价格列已存在 |
| `factor_diagnosis.py` | 方向修正是全局操作，无需分层 |

---

## 3. 各文件详细改动设计

### 3.1 `pipeline.py` — 添加分层编排

**改动策略**: 在 Step 3（阈值优化）处引入分层循环。Step 1/2 保持不变（全局数据构建和方向修正），Step 4（参数合并）适配分层输出。

```python
def main():
    # ── 配置 ──
    adapt_newscan = False
    need_optimization = True

    # 分层挖掘配置
    tiered_mode = True  # False: 全局模式（向后兼容）
    price_tiers = [
        {"name": "low",  "min_price": 0.0, "max_price": 5.0},
        {"name": "high", "min_price": 5.0, "max_price": 999.0},
    ]

    # ... 路径配置不变 ...

    # Step 1/2 不变

    # ── Step 3/4: 阈值优化 ──
    if tiered_mode:
        import pandas as pd
        df_all = pd.read_csv(analysis_csv)

        tier_results = {}
        for tier in price_tiers:
            print(f"\n{'=' * 60}")
            print(f"[Pipeline] Step 3: 分层优化 - {tier['name']} "
                  f"(${tier['min_price']}-${tier['max_price']})")
            print(f"{'=' * 60}")

            # 按价格过滤
            mask = (df_all['price'] >= tier['min_price']) & (df_all['price'] < tier['max_price'])
            df_tier = df_all[mask].reset_index(drop=True)
            print(f"  Tier samples: {len(df_tier)}")

            # 写临时 CSV（threshold_optimizer.main 接收 CSV 路径）
            tier_csv = analysis_csv.replace('.csv', f'_tier_{tier["name"]}.csv')
            df_tier.to_csv(tier_csv, index=False)

            # 复用 threshold_optimizer.main，checkpoint 路径分开
            tier_filter_yaml = bonus_filter_yaml.replace('.yaml', f'_tier_{tier["name"]}.yaml')
            tier_report = str(mining_report).replace('.md', f'_tier_{tier["name"]}.md') if mining_report else None

            from BreakoutStrategy.mining.threshold_optimizer import main as opt_main
            opt_main(
                input_csv=tier_csv,
                bonus_yaml=all_bonus_yaml,
                output_yaml=tier_filter_yaml,
                report_name=tier_report,
            )
            tier_results[tier['name']] = tier_filter_yaml

        # 合并分层结果到一个 bonus_filter.yaml
        _merge_tier_filters(tier_results, price_tiers, bonus_filter_yaml)
    else:
        # 全局模式（原有逻辑不变）
        from BreakoutStrategy.mining.threshold_optimizer import main as opt_main
        opt_main(...)

    # Step 4 不变（param_writer 读取合并后的 bonus_filter.yaml）
```

**关键设计**: `threshold_optimizer.main()` 的函数签名不变，接收的 CSV 已经是子集。唯一需要调整的是 Optuna checkpoint 路径（各层分开，避免冲突）。

### 3.2 `bonus_filter.yaml` — 分层格式草案

**方案 A（推荐）：顶层 `tiers` 结构**

```yaml
_meta:
  version: 4                    # 版本升级
  tiered: true                  # 标记为分层模式
  tiers: ["low", "high"]
  generated_at: '2026-03-04T...'
  # ... 其余元数据 ...

tiers:
  low:
    price_range: [0.0, 5.0]
    sample_size: 5536
    baseline_median: 0.2228
    optimization:
      thresholds:
        Age: 18.5
        Volume: 3.2
        # ...
      shrinkage_score: 0.42
    templates:
      - name: Volume+Streak+Height
        factors: [Volume, Streak, Height]
        count: 45
        median: 0.55
        q25: 0.28
      # ...

  high:
    price_range: [5.0, 999.0]
    sample_size: 4274
    baseline_median: 0.1167
    optimization:
      thresholds:
        Age: 12.0
        Volume: 6.8
        # ...
      shrinkage_score: 0.28
    templates:
      - name: Streak+PeakVol+Height
        factors: [Streak, PeakVol, Height]
        count: 38
        median: 0.32
        q25: 0.15
      # ...

# 向后兼容：保留全局 templates（可选）
templates: []
```

**为什么不用方案 B（每层独立文件）**: 管理复杂度高，param_writer 需要知道文件列表，且 UI 参数编辑器需要改动更多。单文件内分层更易维护。

### 3.3 `all_bonus_mined.yaml` — 分层参数格式

```yaml
# 分层模式
_tier_config:
  enabled: true
  price_key: "price"          # Breakout 对象中的价格字段
  tiers:
    - name: "low"
      min_price: 0.0
      max_price: 5.0
    - name: "high"
      min_price: 5.0
      max_price: 999.0

# 各层独立的 quality_scorer 参数
quality_scorer_tiers:
  low:
    age_bonus:
      enabled: true
      mode: lte
      thresholds: [18.5]
      values: [1]
    volume_bonus:
      enabled: true
      mode: gte
      thresholds: [3.2]
      values: [1]
    # ... 其余因子 ...

  high:
    age_bonus:
      enabled: true
      mode: lte
      thresholds: [12.0]
      values: [1]
    volume_bonus:
      enabled: true
      mode: gte
      thresholds: [6.8]
      values: [1]
    # ... 其余因子 ...

# 向后兼容：全局 quality_scorer 保留（tiered=false 时使用）
breakout_detector: { ... }    # 不变
general_feature: { ... }      # 不变
quality_scorer: { ... }       # 全局参数，分层关闭时使用
```

### 3.4 `param_writer.py` — 适配分层

```python
def build_mined_params(base_yaml_path, filter_yaml_path):
    """合并逻辑扩展：检测 bonus_filter.yaml 是否为分层格式"""
    with open(filter_yaml_path) as f:
        filter_data = yaml.safe_load(f)

    meta = filter_data.get('_meta', {})

    if meta.get('tiered', False):
        return _build_tiered_params(base_yaml_path, filter_data)
    else:
        # 原有全局逻辑不变
        return _build_global_params(base_yaml_path, filter_data)


def _build_tiered_params(base_yaml_path, filter_data):
    """分层模式：为每个 tier 生成独立的 quality_scorer 配置"""
    with open(base_yaml_path) as f:
        base = yaml.safe_load(f)

    tiers_data = filter_data.get('tiers', {})
    tier_configs = {}
    all_applied = []

    for tier_name, tier_info in tiers_data.items():
        thresholds = tier_info.get('optimization', {}).get('thresholds', {})
        # 复用现有 _apply_thresholds 逻辑
        tier_qs = _apply_thresholds_to_qs(base['quality_scorer'], thresholds)
        tier_configs[tier_name] = tier_qs
        all_applied.extend(list(thresholds.keys()))

    # 构建输出结构
    result = dict(base)  # 保留 breakout_detector, general_feature
    result['_tier_config'] = {
        'enabled': True,
        'price_key': 'price',
        'tiers': [
            {'name': name, **tier_info['price_range']}
            for name, tier_info in tiers_data.items()
        ]
    }
    result['quality_scorer_tiers'] = tier_configs
    # 保留全局 quality_scorer 作为 fallback

    return result, list(set(all_applied))
```

### 3.5 `breakout_scorer.py` — 价格路由

**改动最小的方案**: 在 `__init__` 中检测分层配置，维护一个 `{tier_name: tier_config}` 字典。`score_breakout` 根据 `breakout.price` 路由到对应层的参数。

```python
class BreakoutScorer:
    def __init__(self, config=None):
        if config is None:
            config = {}

        # 分层配置检测
        tier_config = config.get('_tier_config', {})
        self._tiered = tier_config.get('enabled', False)

        if self._tiered:
            self._tier_boundaries = [
                (t['min_price'], t['max_price'], t['name'])
                for t in tier_config.get('tiers', [])
            ]
            self._tier_scorers = {}
            tier_params = config.get('quality_scorer_tiers', {})
            for tier_name, tier_qs in tier_params.items():
                # 构造完整 config 给内部初始化
                tier_full_config = dict(config)
                tier_full_config.update(tier_qs)
                # 用同一个类初始化（非递归，因为 tier_full_config 不含 _tier_config）
                self._tier_scorers[tier_name] = BreakoutScorer(tier_full_config)
        else:
            self._tier_boundaries = []
            self._tier_scorers = {}

        # 原有初始化逻辑不变（作为 fallback 或全局模式）
        # ... self.age_bonus_thresholds = ... (全部保留)

    def _get_tier_scorer(self, price: float) -> 'BreakoutScorer':
        """根据价格返回对应层的 scorer，找不到则返回 self（全局 fallback）"""
        for min_p, max_p, name in self._tier_boundaries:
            if min_p <= price < max_p:
                return self._tier_scorers.get(name, self)
        return self  # fallback to global

    def score_breakout(self, breakout):
        """评估突破质量（支持分层路由）"""
        if self._tiered:
            tier_scorer = self._get_tier_scorer(breakout.price)
            return tier_scorer.score_breakout(breakout)

        # 原有逻辑不变
        breakdown = self.get_breakout_score_breakdown_bonus(breakout)
        breakout.quality_score = breakdown.total_score
        breakout.pattern_label = breakdown.pattern_label
        return breakdown.total_score
```

**关键设计**:
- 分层 scorer 用**组合模式**实现：顶层 scorer 持有 N 个子 scorer 实例
- 子 scorer 的初始化完全复用 `__init__` 的原有逻辑（因为传入的 config 不含 `_tier_config`，不会递归）
- `score_breakout` 仅在顶层做一次路由，子 scorer 的 `score_breakout` 走原有逻辑

### 3.6 `param_loader.py` — 解析分层 YAML

```python
def get_scorer_params(self):
    """扩展：解析分层配置"""
    quality_params = self._params.get('quality_scorer', {})

    # 检测分层模式
    tier_config = self._params.get('_tier_config', {})
    if tier_config.get('enabled', False):
        validated = self._build_base_scorer_params(quality_params)
        validated['_tier_config'] = tier_config

        tier_params = self._params.get('quality_scorer_tiers', {})
        validated_tiers = {}
        for tier_name, tier_qs in tier_params.items():
            validated_tiers[tier_name] = self._build_bonus_params(tier_qs)
        validated['quality_scorer_tiers'] = validated_tiers
        return validated

    # 原有全局逻辑
    return self._build_full_scorer_params(quality_params)
```

---

## 4. 实现步骤（时序）

### Phase 1: 挖掘管线分层（离线）

1. **`pipeline.py`**: 添加 `tiered_mode` 开关和 `price_tiers` 配置，在 Step 3 处引入循环
2. **`pipeline.py`**: 实现 `_merge_tier_filters()` 函数，将各层 `bonus_filter_tier_X.yaml` 合并为单一 `bonus_filter.yaml`（v4 格式）
3. **`param_writer.py`**: 添加 `_build_tiered_params()`，识别 v4 格式并生成分层 `all_bonus_mined.yaml`

### Phase 2: 生产评分器分层（在线）

4. **`breakout_scorer.py`**: `__init__` 添加分层检测 + 子 scorer 初始化；`score_breakout` 添加价格路由
5. **`param_loader.py`**: `get_scorer_params()` 适配分层 YAML 解析

### Phase 3: 验证

6. 运行分层管线，检查每层阈值合理性
7. 对比全局 vs 分层在各价格区间的选择力（用现有回测框架）

---

## 5. `threshold_optimizer.py` 的 checkpoint 问题

当前 checkpoint 路径硬编码在 `main()` 内部：
```python
checkpoint_path = str(project_root / "outputs" / "optuna" / "mtpe_more_count.pkl")
```

分层模式下，每层需要独立的 checkpoint。有两种方案：

**方案 A（推荐）**：在 `pipeline.py` 循环中，调用 `opt_main()` 前，通过参数或环境变量传递 checkpoint 路径。但 `opt_main` 的 checkpoint_path 是内部变量。

**方案 B**：将 `checkpoint_path` 提升为 `main()` 的可选参数：

```python
def main(input_csv, bonus_yaml, output_yaml, report_name=None, checkpoint_path=None):
    # ...
    if checkpoint_path is None:
        checkpoint_path = str(project_root / "outputs" / "optuna" / "mtpe_more_count.pkl")
```

这是对 `threshold_optimizer.py` 唯一需要的改动（增加一个可选参数），改动极小且完全向后兼容。

---

## 6. 风险评估

### 6.1 数据量风险

| 分层 | 样本量 | `min_count=20` 可行性 | 备注 |
|------|--------|---------------------|------|
| $1-5 | 5536 | 充足 | 无风险 |
| $5-10 | 4274 | 充足 | 无风险 |
| $7-10 (如果 3 层) | 1613 | 边缘可行 | 模板数量会减少 |

2 层方案下无数据量风险。

### 6.2 过拟合风险

- 分层 = 参数空间翻倍。但每层仍有 4000+ 样本，且使用了 shrinkage + bootstrap 验证
- 建议分层后适当提高 `shrinkage_n0`（如从 80 提到 100），增强收缩力度
- 可通过时间 OOS 验证：用前 80% 数据挖掘，后 20% 验证

### 6.3 向后兼容风险

- **低**: `tiered_mode=False` 时完全走原有逻辑
- **低**: YAML v4 格式通过 `_meta.tiered` 字段区分，v3 文件无此字段，自动走全局路径
- **低**: `BreakoutScorer` 无 `_tier_config` 时行为不变

### 6.4 边界价格处理

价格恰好等于分界线（如 $5.00）的处理：使用 `min_price <= price < max_price` 半开区间，确保无遗漏无重叠。最后一层用 `max_price: 999.0` 兜底。

---

## 7. 总结

| 维度 | 方案 |
|------|------|
| 分层数 | 2 层（$1-5, $5-10） |
| 分层位置 | `pipeline.py` 循环层 |
| 核心搜索逻辑 | 完全复用 `threshold_optimizer.main()` |
| YAML 格式 | v3 → v4，添加 `tiers` 顶层键 |
| 生产路由 | `BreakoutScorer` 组合模式，按 `breakout.price` 路由 |
| 改动文件数 | 4 个（pipeline, param_writer, scorer, param_loader） |
| `threshold_optimizer.py` 改动 | 仅添加 `checkpoint_path` 可选参数（1 行） |
| 向后兼容 | 全局/分层通过配置开关切换 |
| 总新增代码 | 约 140 行 |
