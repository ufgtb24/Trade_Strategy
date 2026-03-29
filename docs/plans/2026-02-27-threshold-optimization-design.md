# 组合模板阈值优化系统 — 设计文档

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 通过数据驱动的多阶段流水线，搜索最优 bonus 因子阈值，使组合模板挖掘的 Top-K median 收益最大化。

**Architecture:** 四阶段流水线（逻辑排除 → 因子筛选 → 双引擎搜索 → 验证输出），新建单一脚本 `scripts/analysis/optimize_thresholds.py`，复用现有 `generate_templates()` 作为内层评估函数。贪心法提供初始解，Optuna TPE 全局搜索并以贪心解做 warm start。

**Tech Stack:** Python, pandas, numpy, optuna, scipy, 现有 `_analysis_functions.py` 常量

---

## 背景

### 问题

`auto_correct_bonus.py` 对 11 个因子独立优化阈值，优化目标是「单因子 level 与 label 单调性」。这在组合模板挖掘场景下导致：
- 触发率膨胀（Volume 91%, Overshoot 91%, Streak 99%）
- 精英子集被稀释（平均触发因子从 3.11 → 6.03）
- Top1 median 从 0.6037（bk 阈值）下降到 0.3750

### 目标

找到一组阈值，使 `generate_templates()` 产出的 Top-K 模板 median 最高、样本量合理。

### 约束

- 仅用于组合模板挖掘（与生产 Scorer 的 `all_bonus.yaml` 解耦）
- 直接产出 `configs/params/bonus_filter.yaml`（格式兼容现有 UI）
- 利用现有 `generate_templates()` 的 bit-packed 评估（~4.4ms/次）

---

## 设计

### 总览

```
Stage 0: 逻辑排除
    └── Overshoot（前瞻偏差）→ 排除

Stage 1: 因子筛选（Bootstrap 方法）
    ├── bk 阈值 → generate_templates → top-30 (count>=10)
    ├── q70 均匀阈值 → generate_templates → top-30 (count>=10)
    ├── 计算因子加权频率 + lift
    └── lift > 1.0 → 候选活跃因子

Stage 2: 时序验证
    ├── 前 70% / 后 30% 各跑 Stage 1
    ├── AUC 作为辅助诊断（非筛选门控）
    └── 两窗口交集 → 最终活跃因子

Stage 3: 双引擎串行搜索
    ├── 3a: 贪心 beam search（秒级）→ top-3 初始解
    └── 3b: Optuna TPE 多目标（嵌套 generate_templates, 3000 trials ~15s）
        ├── 贪心解做 warm start (study.enqueue_trial)
        ├── 目标: top-5 combo avg median + viable_count
        └── 约束: 单因子触发率 ∈ [3%, 50%]

Stage 4: 验证 + 输出
    ├── Bootstrap 稳定性评分
    ├── Pareto 前沿 knee point 选择
    └── 输出: bonus_filter.yaml
```

### Stage 0: 逻辑排除

**排除 Overshoot**：`overshoot_ratio = gain_5d / (annual_vol / √50.4)`，而 `label_10_40` 包含突破后 5-40 天收益，与 `gain_5d` 共享 5 天窗口（Spearman r=0.378）。这是前瞻偏差，不是因果信号。

实现：从 `BONUS_COLS` 中移除 `overshoot_level`，后续阶段不参与。

### Stage 1: Bootstrap 因子筛选

**核心思想**：不用单因子 AUC 筛选（会遗漏 PBM 等「单独弱但组合强」的因子），而是直接从 `generate_templates()` 输出中提取高频因子。

**步骤**：

1. **准备两套阈值**：
   - **bk 阈值**：从 `configs/params/all_bonus_bk.yaml` 读取
   - **q70 均匀阈值**：对每个因子，取 CSV 中原始值的 q70 分位数作为单一阈值（即 top-30% 触发）

2. **对每套阈值**：
   - 用阈值重算所有 level 列（复用 `get_level()` 逻辑）
   - 调用 `generate_templates(df, min_count=10)` 生成组合
   - 取 top-30 模板（按 median 降序）

3. **计算因子频率与 lift**：
   ```
   对每个因子 f:
     top_freq(f) = f 在 top-30 模板中出现的加权次数 / top-30 总数
       加权 = 出现在 rank 1-10 权重 3，rank 11-20 权重 2，rank 21-30 权重 1
     all_freq(f) = f 在所有模板中出现的比例
     lift(f) = top_freq(f) / all_freq(f)
   ```

4. **筛选**：`lift > 1.0` 的因子 → 候选活跃因子

### Stage 2: 时序验证

**目的**：防止因子筛选过拟合。

**步骤**：

1. 按日期排序，前 70% 为训练集、后 30% 为测试集
2. 分别在训练集和测试集上运行 Stage 1
3. **AUC 辅助诊断**：对候选因子计算 AUC（区分精英 vs 非精英），作为参考但不做硬门控
4. **最终活跃因子** = 在训练集和测试集中 lift 均 > 1.0 的因子

### Stage 3: 双引擎串行搜索

#### 3a: 贪心 Beam Search

**搜索空间**：仅活跃因子，每因子搜索 ~20 个候选阈值（原始值分位数）。

**算法**：
```
Step 1: 对活跃因子中判别力最强的因子（lift 最高），搜索最优单阈值
  → 使子集 median 最大化（子集 = 满足阈值条件的样本）
  → 保留 top-3 路径 (beam width = 3)

Step 2: 在每条路径的子集上，搜索最优第二因子 + 阈值
  → 再保留 top-3

Step 3-K: 重复，直到子集 < min_count 或 median 不再提升

输出: top-3 阈值组合 + 对应的 generate_templates() 结果
```

**注意**：贪心法使用**子集 median** 作为目标（不嵌套 generate_templates），因为它是条件化逐步收缩子集，这与 generate_templates 的全局组合枚举是不同的搜索范式。

#### 3b: Optuna TPE 多目标搜索

**搜索空间**：

```python
for factor in ACTIVE_FACTORS:
    # 每因子 1-2 个阈值（由 Stage 1 的阈值数量决定）
    t1 = trial.suggest_float(f"{factor}_t1", lo, hi)
    # 可选 t2（若原始因子有 3+ 个有效 level）
    t2 = trial.suggest_float(f"{factor}_t2", t1 + eps, hi2)
```

搜索边界：由 Stage 1 中两套阈值的观察范围确定（取各因子原始值的 [q10, q90]）。

**目标函数**（嵌套 generate_templates）：

```python
def objective(trial):
    # 1. 从 trial 获取阈值
    thresholds = extract_thresholds(trial, ACTIVE_FACTORS)

    # 2. 用新阈值重算 level
    df_copy = recalculate_levels(df, thresholds)

    # 3. 调用 generate_templates（核心评估）
    templates = generate_templates(df_copy, min_count=10)

    # 4. 计算目标
    if len(templates) < 5:
        return 0.0, 0

    top_5_median = np.mean([t['median'] for t in templates[:5]])
    viable_count = len([t for t in templates if t['count'] >= 20])

    # 5. 触发率约束
    for factor in ACTIVE_FACTORS:
        rate = (df_copy[f"{factor}_level"] > 0).mean()
        if rate > 0.50 or rate < 0.03:
            return 0.0, 0  # 违反约束

    return top_5_median, viable_count  # 两个目标都 maximize
```

**Warm start**：
```python
study = optuna.create_study(directions=["maximize", "maximize"])

# 注入贪心法的 top-3 解
for greedy_solution in greedy_results:
    study.enqueue_trial(greedy_solution.to_optuna_params())

study.optimize(objective, n_trials=3000)  # ~15s (3000 * 5ms)
```

### Stage 4: 验证 + 输出

1. **Bootstrap 稳定性**：对 Pareto 前沿的候选解，重采样 1000 次计算 median 的 95% CI
2. **选择最终解**：
   - 从 Pareto 前沿中选择 knee point（median 和 viable_count 的帕累托最优折中点）
   - 或选择 stability score 最高的解（`stability = 1 - CI_width / median`）
3. **输出**：用最终阈值调用 `generate_templates()` + `build_yaml_output()`，写入 `configs/params/bonus_filter.yaml`

---

## 文件设计

### 新建文件

| 文件 | 职责 |
|------|------|
| `scripts/analysis/optimize_thresholds.py` | 四阶段流水线主脚本 |

### 复用文件

| 文件 | 复用内容 |
|------|---------|
| `scripts/analysis/optimize_bonus_filter.py` | `generate_templates()`, `build_yaml_output()`, `print_summary()` |
| `scripts/analysis/_analysis_functions.py` | `BONUS_COLS`, `BONUS_DISPLAY`, `LABEL_COL` |
| `scripts/analysis/bonus_combination_analysis.py` | `get_level()` |
| `configs/params/all_bonus_bk.yaml` | bk 阈值（Stage 1 输入） |

### 不修改的文件

- `configs/params/all_bonus.yaml` — 生产 Scorer 配置，本流程不触碰
- `scripts/analysis/auto_correct_bonus.py` — 现有单因子校准，保持独立

---

## 函数设计

```python
# === Stage 0 ===
EXCLUDED_FACTORS = ['overshoot_level']  # 前瞻偏差

# === Stage 1 ===
def load_bk_thresholds(yaml_path) -> dict[str, list[float]]:
    """从 all_bonus_bk.yaml 读取阈值配置"""

def compute_q70_thresholds(df, factor_raw_cols) -> dict[str, list[float]]:
    """对每个因子原始值取 q70 分位数作为单阈值"""

def recalculate_levels(df, thresholds) -> pd.DataFrame:
    """用给定阈值重算所有 level 列（返回 df 副本）"""

def compute_factor_lift(templates, top_k=30) -> dict[str, float]:
    """从模板列表计算因子加权频率和 lift"""

def stage1_factor_screening(df, bk_thresholds, q70_thresholds) -> list[str]:
    """Bootstrap 因子筛选，返回活跃因子列表"""

# === Stage 2 ===
def stage2_temporal_validation(df, bk_thresholds, q70_thresholds) -> list[str]:
    """时序验证，返回稳定活跃因子列表"""

# === Stage 3 ===
def stage3a_greedy_beam_search(df, active_factors, beam_width=3) -> list[dict]:
    """贪心 beam search，返回 top-3 解"""

def stage3b_optuna_search(df, active_factors, greedy_seeds, n_trials=3000) -> Study:
    """Optuna TPE 多目标搜索"""

# === Stage 4 ===
def stage4_validate_and_output(df, study, output_path) -> None:
    """Bootstrap 验证 + knee point 选择 + 写 YAML"""

# === Main ===
def main():
    """四阶段流水线入口"""
```

---

## 因子映射表

`_analysis_functions.py` 中的 level 列 → CSV 中原始值列 → YAML key 的映射：

| level 列 | 原始值列 | YAML key (bk) | 备注 |
|----------|---------|---------------|------|
| `height_level` | `max_height` | `height_bonus` | 核心因子 |
| `peak_vol_level` | `max_peak_volume` | `peak_volume_bonus` | |
| `volume_level` | `volume_surge_ratio` | `volume_bonus` | |
| `day_str_level` | 衍生: `max(idr/daily_vol, gap/daily_vol)` | `breakout_day_strength_bonus` | 衍生因子 |
| `drought_level` | `days_since_last_breakout` | `drought_bonus` | |
| `age_level` | `oldest_age` | `age_bonus` | |
| `streak_level` | `recent_breakout_count` | `streak_bonus` | 反向因子 |
| `pk_mom_level` | `pk_momentum` | `pk_momentum_bonus` | |
| `pbm_level` | `momentum` | `pbm_bonus` | AUC 低但组合 lift 高 |
| `test_level` | `test_count` | `test_bonus` | |
| `overshoot_level` | 衍生: `gain_5d / (annual_vol / √50.4)` | `overshoot_penalty` | **排除** |

---

## 衍生因子处理

两个因子的原始值不在 CSV 中直接存在，需在 `recalculate_levels()` 中特殊处理：

1. **DayStr**：`day_str_ratio = max(|intraday_change_pct|/daily_vol, |gap_up_pct|/daily_vol)`
   - CSV 中有 `intraday_change_pct`, `gap_up_pct`, `annual_volatility`
   - `daily_vol = annual_volatility / sqrt(252)`

2. **Overshoot**（已排除）：`overshoot_ratio = gain_5d / (annual_vol / √50.4)`

---

## 配置参数

所有参数声明在 `main()` 起始位置（遵循项目约定，不用 argparse）：

```python
def main():
    # === 配置 ===
    input_csv = "outputs/analysis/bonus_analysis_data.csv"
    bk_yaml = "configs/params/all_bonus_bk.yaml"
    output_yaml = "configs/params/bonus_filter.yaml"

    # Stage 1
    top_k_templates = 30         # 取 top-K 模板分析因子频率
    min_count_screening = 10     # 因子筛选阶段的最小样本量

    # Stage 2
    temporal_split = 0.7         # 前 70% 训练 / 后 30% 测试

    # Stage 3
    beam_width = 3               # 贪心 beam search 宽度
    n_trials = 3000              # Optuna 试验数
    min_count_final = 10         # 最终模板最小样本量
    trigger_rate_lo = 0.03       # 触发率下界
    trigger_rate_hi = 0.50       # 触发率上界
    top_k_objective = 5          # Optuna 目标: top-K median

    # Stage 4
    bootstrap_n = 1000           # Bootstrap 重采样次数
```

---

## 预期结果

| 指标 | 当前 bk | 当前 auto_correct | 优化后预期 |
|------|---------|-------------------|-----------|
| Top1 median | 0.6037 (n=21) | 0.3750 (n=?) | 0.40-0.55 |
| Top5 avg median | ~0.42 | ~0.33 | 0.35-0.45 |
| 有效模板数 | 128 | 171 | 80-150 |
| 触发率范围 | 2-67% | 12-99% | 3-50% |
| 活跃因子数 | 11 (含退化) | 11 (含退化) | 5-8 |

---

## 运行方式

```bash
uv run python scripts/analysis/optimize_thresholds.py
```

预期运行时间：< 30 秒（Stage 1-2 ~2s + Stage 3a ~3s + Stage 3b ~15s + Stage 4 ~5s）。
