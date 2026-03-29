# 非单调因子检测与双向因子设计方案研究

## Executive Summary

本研究回答一个通用性问题：当因子与 label 的关系不是全局单调的（U 形、倒 U 形、分段效应），现有基于全局 Spearman 的 `diagnose_direction` 会如何失效？应该用什么方法检测非单调性？如果检测到非单调因子，pipeline 应该如何处理？

**核心结论**：

1. **检测方法**：推荐"分段 Spearman 符号翻转检测"作为 `diagnose_direction` 的增量补充，计算成本极低（O(n)），可解释性强，且能直接给出分段方向。
2. **处理方案**：推荐"方案 1: 因子拆分注册"——将非单调因子注册为两个独立子因子（`xxx_high` + `xxx_low`），pipeline 零改动，BreakoutScorer 零改动，且完全兼容未来新增非单调因子。
3. **方案 3（仅诊断不自动处理）** 作为最小可行的第一步，适合当前阶段：先让 `diagnose_direction` 能识别和报告非单调性，人工决策是否需要拆分。

---

## Part A: 非单调性检测方法研究

### A.1 全局 Spearman 的失效模式

全局 Spearman 相关系数衡量的是**单调**关联强度。当因子与 label 的关系非单调时，存在三种典型失效模式：

| 失效模式 | 真实关系 | Spearman 表现 | 后果 |
|----------|---------|--------------|------|
| **U 形** | 低值好 + 高值好，中间差 | r ≈ 0（正负抵消） | 被判为 `weak`，整个因子被浪费 |
| **倒 U 形** | 中间值好，两端差 | r ≈ 0 | 同上 |
| **分段效应** | 低值段负相关，高值段正相关（或反之） | r 的符号取决于哪段数据量更大 | 方向可能被分配为占主导数量的段的方向，另一段的信号被忽略 |

具体到本系统：
- 如果一个因子是"适量好、过量差"（如假设性的 volume：适度放量好，极端放量可能是出货），全局 Spearman 可能给出 `r > 0`（因为大部分高量突破确实好），但极端高量段的惩罚效应被淹没。
- 当前 streak 在数据中表现为纯单调递减（r = -0.0506），不存在非单调问题。但这个诊断框架需要能处理未来可能出现的非单调因子。

### A.2 替代方法评估

#### 方法 1: 分段 Spearman（Piecewise Spearman）

**原理**：按因子值的分位数（如三分位或四分位）将数据切分为若干段，各段分别计算 Spearman 相关系数，检测符号是否翻转。

**适用性分析**：

| 维度 | 评价 |
|------|------|
| 计算成本 | **极低**。对 14000 条数据，3-4 段的 Spearman 计算总耗时 < 1ms/因子 |
| 样本量要求 | 每段约 3500-4700 条（14000 / 3 或 4），远超 Spearman 的最低要求 |
| 可解释性 | **极强**。直接给出"低段 r=-0.08, 高段 r=+0.05"，人可以直接理解 |
| 实现复杂度 | **极低**。约 15 行代码 |
| 方向建议能力 | **直接可用**。各段的符号直接对应 gte/lte 方向 |

**判定规则**：
- 若所有段的 Spearman 符号一致 → 全局单调，使用全局 Spearman 的方向
- 若段间符号翻转 → 非单调，标记为 `non_monotonic`
- 翻转点位置直接给出拆分建议（如"在 P50 处翻转"）

**推荐指数**：★★★★★

#### 方法 2: 距离相关（Distance Correlation, dcor）

**原理**：衡量两个变量之间的任意（非线性）统计依赖关系。dcor = 0 当且仅当两变量独立。

**适用性分析**：

| 维度 | 评价 |
|------|------|
| 计算成本 | **高**。朴素算法 O(n^2)，14000 条约需 2-5 秒/因子。快速近似 O(n log n) 可降到 ~100ms |
| 样本量要求 | 充足 |
| 可解释性 | **差**。只给出"有关联"或"无关联"，不给方向，不给形状 |
| 实现复杂度 | 需要 `dcor` 库 |
| 方向建议能力 | **无**。完全不给方向信息 |

**用途**：适合作为"是否存在任何关联"的预筛工具，但不能替代方向诊断。

**推荐指数**：★★☆☆☆

#### 方法 3: 互信息（Mutual Information, MI）

**原理**：基于信息论，衡量一个变量对另一个变量的信息量。能捕获任意非线性关系。

**适用性分析**：

| 维度 | 评价 |
|------|------|
| 计算成本 | **中**。sklearn 的 `mutual_info_regression` 约 50-200ms/因子（14000 条） |
| 样本量要求 | 充足，但对离散因子（如 streak，值域仅 [1,9]）敏感，需要合适的 bin 策略 |
| 可解释性 | **差**。MI 值没有上界归一化（除非用 NMI），且不给方向 |
| 实现复杂度 | sklearn 内置，简单 |
| 方向建议能力 | **无** |

**推荐指数**：★★☆☆☆

#### 方法 4: 最大信息系数（Maximal Information Coefficient, MIC）

**原理**：MI 的归一化版本，通过网格优化找到最大互信息，值域 [0,1]。

**适用性分析**：

| 维度 | 评价 |
|------|------|
| 计算成本 | **高**。O(n^1.6) 或更高，14000 条约 1-3 秒/因子 |
| 样本量要求 | 充足 |
| 可解释性 | **中**。MIC 值可归一化比较，但不给方向 |
| 实现复杂度 | 需要 `minepy` 库 |
| 方向建议能力 | **无** |

MIC - Spearman^2 > 0 可作为非线性检测指标（MINE 统计量的一种），但仍不给方向。

**推荐指数**：★★★☆☆（作为补充检测手段有价值）

#### 方法 5: 分位数回归 / GAM

**原理**：拟合因子与 label 的非参数关系曲线，观察曲线形状。

**适用性分析**：

| 维度 | 评价 |
|------|------|
| 计算成本 | **中高**。GAM 拟合约 0.5-2 秒/因子，分位数回归类似 |
| 样本量要求 | 充足 |
| 可解释性 | **极强**。直接给出关系曲线，可视化最佳 |
| 实现复杂度 | **高**。需要 `pygam` 或 `statsmodels`，且需要处理平滑参数选择 |
| 方向建议能力 | **间接可用**。通过曲线斜率判断方向 |

适合深入研究单个因子，但不适合批量自动诊断。

**推荐指数**：★★★☆☆（研究工具，不适合自动化管线）

### A.3 推荐方案

**主推荐：分段 Spearman 符号翻转检测**

理由：
1. 计算成本最低（所有因子合计 < 10ms），适合批量运行
2. 可解释性最强，直接给出段方向
3. 实现复杂度最低（约 15 行核心代码）
4. 与现有 `diagnose_direction` 的 Spearman 逻辑无缝衔接——先算全局 Spearman，再做分段检查
5. 对 14000 条样本量，三分位切分每段 ~4700 条，统计功效充足

**补充推荐**：MIC - Spearman^2 作为非线性强度指标。当分段 Spearman 检测到翻转时，可用 MIC 确认非线性关联的强度。但这是可选的增强，不是必须的。

**分段 Spearman 伪代码**：

```python
def detect_non_monotonicity(raw: np.ndarray, labels: np.ndarray,
                             n_segments: int = 3, flip_threshold: float = 0.02):
    """
    分段 Spearman 非单调性检测。

    Returns:
        {is_non_monotonic, segments: [{quantile_range, spearman_r, n_samples}],
         flip_point_quantile}
    """
    quantiles = np.linspace(0, 1, n_segments + 1)
    boundaries = np.quantile(raw, quantiles)

    segment_results = []
    for i in range(n_segments):
        mask = (raw >= boundaries[i]) & (raw < boundaries[i+1])
        if i == n_segments - 1:  # 最后一段包含右端点
            mask = (raw >= boundaries[i]) & (raw <= boundaries[i+1])
        seg_raw, seg_labels = raw[mask], labels[mask]
        if len(seg_raw) > 10:
            r, p = spearmanr(seg_raw, seg_labels)
            segment_results.append({
                'quantile_range': (quantiles[i], quantiles[i+1]),
                'spearman_r': r, 'n_samples': len(seg_raw)
            })

    # 检测符号翻转
    signs = [np.sign(s['spearman_r']) for s in segment_results
             if abs(s['spearman_r']) > flip_threshold]
    is_non_monotonic = len(set(signs)) > 1

    return {'is_non_monotonic': is_non_monotonic, 'segments': segment_results}
```

---

## Part B: 双向因子设计方案对比

### 前提：架构约束回顾

| 约束 | 来源 | 说明 |
|------|------|------|
| `build_triggered_matrix` 一因子一列 | threshold_optimizer.py:28-53 | bit-packed 编码，每个因子占一个 bit 位 |
| `BreakoutScorer` 不读 mode | breakout_scorer.py:143-168 | 通过 values 编码方向（< 1.0 = 惩罚） |
| `BreakoutScorer` 只用 `>=` 比较 | breakout_scorer.py:161 | 所有因子统一 `value >= threshold` |
| `FactorInfo.mining_mode` 仅服务于挖掘管线 | factor_registry.py:42 | 评分时完全忽略 |
| TPE 搜索空间 = 所有活跃因子的笛卡尔积 | threshold_optimizer.py:306-315 | 因子数直接影响搜索维度 |

### 方案 1: 因子拆分注册

**核心思路**：将一个非单调因子（如假设性的双向 `xxx`）注册为两个独立因子 `xxx_high`（mining_mode='gte'）和 `xxx_low`（mining_mode='lte'），共享同一个原始计算值。

**实现方式**：

```python
# factor_registry.py 中注册两个虚拟因子
FactorInfo('xxx_high', 'XXX High', 'XXX高值端',
           (threshold_h,), (1.2,),   # 高值奖励
           mining_mode='gte', ...),
FactorInfo('xxx_low', 'XXX Low', 'XXX低值端',
           (threshold_l,), (0.8,),   # 低值惩罚（或奖励，取决于语义）
           mining_mode='lte', ...),
```

**需要解决的问题**：

1. **共享 raw value**：两个子因子在 `features.py` 中需要从同一个原始值计算。方案：在 `FactorInfo` 中增加 `source_key` 字段，`prepare_raw_values` 中检测到 `source_key` 时读取源因子列。或者更简单地：两个子因子的 `_calculate_xxx()` 方法直接复制同一个值到 Breakout 的两个属性上。

2. **TPE 搜索空间膨胀**：增加一个因子 → 搜索空间 +1 维。但对 TPE 而言，维度从 12 → 13 的影响很小，TPE 的效率在 20 维以内都还可以。

3. **两个子因子阈值冲突**：`xxx_high` 的阈值 T_h 和 `xxx_low` 的阈值 T_l 可能出现 T_l > T_h，导致区间 [T_l, T_h] 的样本同时被两个子因子触发。这实际上是期望行为——中间段可以同时触发两个子因子，被双重奖励/惩罚。如果不期望重叠，可以在 TPE 的 objective 中加入约束。

**优劣势**：

| 维度 | 评价 |
|------|------|
| Pipeline 改动量 | **零**。build_triggered_matrix、fast_evaluate、decode_templates 全部不变 |
| BreakoutScorer 改动量 | **零**。两个子因子各自独立走 `_compute_factor` |
| YAML 配置 | 自然扩展，两个独立的 `xxx_high_factor` 和 `xxx_low_factor` 条目 |
| 可扩展性 | **极强**。未来新非单调因子只需注册两个 FactorInfo |
| 语义清晰度 | **高**。每个子因子有明确的单向语义 |
| 搜索效率 | 轻微下降（+1 维），可接受 |
| 缺点 | 两个子因子共享原始值需要在 features.py / data_pipeline 中处理 |

### 方案 2: mining_mode='both' 双模式

**核心思路**：FactorInfo 支持 `mining_mode='both'`，TPE 为该因子搜索两个阈值 (lo, hi)，触发条件为 `value <= lo OR value >= hi`（两端触发）或 `lo <= value <= hi`（区间触发）。

**需要改动的组件**：

1. **`build_triggered_matrix`**：当前一因子一列。`both` 模式需要一因子两列（high_triggered, low_triggered），或者用一列编码三态（0=未触发, 1=低端触发, 2=高端触发）。但 bit-packed 编码不支持三态。
   - 方案 A：拆成两列 → 实质与方案 1 相同，但不在注册层拆分
   - 方案 B：使用两个 bit 位 → 需要修改 powers 编码、decode_templates 等

2. **TPE 搜索空间**：需要为 `both` 因子生成两个参数 `key_lo` 和 `key_hi`，并加约束 `lo < hi`。Optuna 支持条件参数，但增加了搜索复杂度。

3. **`fast_evaluate` / `decode_templates`**：bit-packed 逻辑需要适配多 bit 因子。

4. **`load_factor_modes`**：需要处理 `both` 模式，返回更复杂的结构（而非简单的 negative_factors 集合）。

5. **`param_writer`**：需要为 `both` 因子写两个阈值和对应 values。

**优劣势**：

| 维度 | 评价 |
|------|------|
| Pipeline 改动量 | **大**。build_triggered_matrix、fast_evaluate、decode_templates、load_factor_modes、param_writer 均需修改 |
| BreakoutScorer 改动量 | **大**。需要支持区间比较或双端比较，打破当前"统一 >= "的设计 |
| YAML 配置 | 需要新的 `thresholds_lo` / `thresholds_hi` 结构 |
| 可扩展性 | 中。框架改好后新增因子方便，但初始改动大 |
| 语义清晰度 | **中**。`both` 模式的触发语义需要额外文档 |
| 搜索效率 | 与方案 1 相同（本质上都是 +1 维） |
| 缺点 | **侵入性高**，触及 pipeline 多个核心函数 |

### 方案 3: diagnose_direction 增强（仅诊断）

**核心思路**：在 `diagnose_direction` 中增加分段 Spearman 检测，自动识别非单调因子并标记为 `non_monotonic`，但不自动处理——输出到诊断报告中，提示人工决策。

**需要改动的组件**：

1. **`diagnose_direction`**：增加约 20 行分段 Spearman 逻辑，在 direction 结果中增加 `non_monotonic` 标记和分段详情。

2. **其余 pipeline**：不变。

**实现**：

```python
# 在 diagnose_direction 的正常 Spearman 判定后，追加：
if abs(r) < weak_threshold:
    # 全局 Spearman 弱 → 可能是非单调
    segments = detect_non_monotonicity(valid_raw, valid_labels)
    if segments['is_non_monotonic']:
        direction = 'non_monotonic'
        # mode 仍取占主导的方向，但标记非单调
```

**优劣势**：

| 维度 | 评价 |
|------|------|
| Pipeline 改动量 | **极小**。仅 diagnose_direction 增加 ~20 行 |
| BreakoutScorer 改动量 | **零** |
| 可扩展性 | **低**。只能诊断，不能自动处理 |
| 实现复杂度 | **极低** |
| 缺点 | 不解决自动化问题，需要人工介入 |
| 优点 | **风险最低**，适合作为第一步 |

### 方案 4: 区间触发评分

**核心思路**：保持单因子注册，但在 `BreakoutScorer` 中支持区间模式 `lo <= value <= hi`。

**可行性分析**：

根据对 `breakout_scorer.py` 的分析，`BreakoutScorer._get_factor_value` 使用统一的 `>=` 比较，且完全不读 mode 字段。要支持区间模式：

1. 需要修改 `_get_factor_value` 的比较逻辑
2. 需要在 `_factor_configs` 中读取 mode 字段
3. 打破"统一 >= "的设计理念（breakout_scorer.py 第 12 行注释）

更关键的问题：**挖掘管线与评分器的解耦**。当前设计中，mode 只服务于挖掘管线（TPE 搜索方向），评分器通过 values 编码方向。区间模式需要在评分器中引入 mode 概念，破坏了这种解耦。

**优劣势**：

| 维度 | 评价 |
|------|------|
| Pipeline 改动量 | **中**。threshold_optimizer 需要搜索两个阈值 |
| BreakoutScorer 改动量 | **大**。需要引入 mode 感知，打破"统一 >= "设计 |
| 可扩展性 | **中** |
| 缺点 | 破坏评分器的设计理念 |

### 方案对比总表

| 维度 | 方案 1 (拆分注册) | 方案 2 (mode=both) | 方案 3 (仅诊断) | 方案 4 (区间评分) |
|------|:-:|:-:|:-:|:-:|
| Pipeline 改动 | 无 | 大 | 极小 | 中 |
| Scorer 改动 | 无 | 大 | 无 | 大 |
| YAML 改动 | 自然扩展 | 新结构 | 无 | 中 |
| 自动化程度 | 完全自动 | 完全自动 | 需人工 | 完全自动 |
| 可扩展性 | 强 | 中 | 弱 | 中 |
| 语义清晰度 | 高 | 中 | 高 | 低 |
| 实现风险 | 低 | 高 | 极低 | 中 |
| 搜索维度影响 | +1 | +1 | 无 | +1 |

---

## Part C: 综合推荐

### 推荐策略：分阶段实施

#### 第一阶段（立即可做）：方案 3 — diagnose_direction 增强

**理由**：
1. 改动极小（~20 行），风险为零
2. 立即获得非单调性的诊断能力
3. 为后续决策提供数据支撑——先看看当前 13 个因子中到底有几个是非单调的
4. 如果诊断结果表明大部分因子都是单调的（当前数据已经暗示了这一点），那么可能根本不需要第二阶段

**具体改动**：
- `factor_diagnosis.py` 中 `diagnose_direction` 函数增加分段 Spearman 检测
- 对全局 Spearman 判为 `weak` 的因子，追加非单调性检查
- 输出增加 `segments` 字段，包含各分段的 Spearman 值
- `direction` 可能的值从 `{positive, negative, weak, override}` 扩展为 `{positive, negative, weak, non_monotonic, override}`

#### 第二阶段（按需实施）：方案 1 — 因子拆分注册

**触发条件**：第一阶段诊断确认存在需要双向处理的因子。

**理由**：
1. Pipeline 零改动，是所有自动化方案中侵入性最小的
2. BreakoutScorer 零改动，保持"统一 >= "的设计理念
3. 每个子因子有独立、清晰的单向语义
4. 未来新增非单调因子只需在 `FACTOR_REGISTRY` 中多注册一条，无需改框架
5. TPE 搜索维度从 N → N+1，对当前 12-13 因子的规模影响可忽略

**实现要点**：
- 在 `FactorInfo` 中增加可选的 `source_key` 字段（默认 None，表示自身就是源）
- `prepare_raw_values` 中：若 `fi.source_key` 非空，读取 `df[fi.source_key]` 而非 `df[fi.key]`
- `features.py` 中：子因子共享计算，将同一个值写入 Breakout 对象的两个属性
- `data_pipeline.build_dataframe` 中：同样基于 `source_key` 读取原始值

**不推荐方案 2 和方案 4 的理由**：
- 方案 2 需要修改 build_triggered_matrix 的 bit-packed 编码、fast_evaluate、decode_templates、load_factor_modes、param_writer 等 5+ 个函数，侵入性过高
- 方案 4 破坏 BreakoutScorer "通过 values 编码方向、统一 >= 比较"的核心设计理念，引入了评分器对 mode 字段的依赖

### 成功标准

1. **第一阶段**：`diagnose_direction` 能正确识别非单调因子，输出分段 Spearman 详情
2. **第二阶段**：拆分后的子因子能被 TPE 独立优化，且最终产出的模板质量不低于单因子版本
3. **通用性**：新增任意非单调因子时，只需修改 `FACTOR_REGISTRY`，不需要触碰 pipeline 或 scorer 代码
