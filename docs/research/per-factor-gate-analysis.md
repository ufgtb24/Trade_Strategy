# Per-Factor Gate 重构提案：第一性原理论证报告

> 生成日期：2026-04-15
> 范围：`BreakoutStrategy/analysis/breakout_detector.py`、`features.py`、`factor_registry.py`、`breakout_scorer.py`、`mining/`、`UI/charts/components/score_tooltip.py`
> 结论预览：**支持改，但需按"最小改动 + 扩展 nullable 语义 + 模板匹配语义明确化"三步走**

---

## 1. 问题与提案总结

**现状**：`BreakoutDetector._check_breakouts` 顶端以 `current_idx < self.max_buffer` 为全局硬门槛（当前 `max_buffer=252`，由 `overshoot/day_str/pbm` 间接依赖 `annual_volatility` 驱动）。门槛未过 → 不产生 `BreakoutInfo`、不写 `breakout_history`、`active_peaks` 不更新。这让"BO 的诞生"成为 lookback 最苛刻因子的人质：idx∈[0,252) 的一切真实突破被整体吞掉，连带污染 drought/streak 的历史。

**提案**：把 gate 从 BO 级下沉到因子级——"某因子 lookback 不满足" 仅意味着**该因子对该 BO 无效**，不影响 BO 存在，不影响其他因子触发。

**核心判断**：提案在概念上是正确的解耦方向，实现代价低，主要收益是让 idx<max_buffer 区段不再成为数据盲区（对历史数据回测、以及冷启动/短 IPO 样本特别重要）。风险集中在"模板匹配语义如何解释因子缺失"——需要明确选择 **missing-as-fail**（推荐，兼容现有语义）。

---

## 2. 概念分解正交性分析

### 2.1 "突破是否成立" 是纯局部判断

审视 `_check_breakouts`（detector:553-624）：核心逻辑是 `breakout_price > peak.price * (1 + exceed_threshold)`，操作对象是 `self.active_peaks` 与当前 bar 的价格。**突破的本体只依赖**：

- 当前 bar 的 OHLC
- `active_peaks` 内存状态（由历次 `_detect_peak_in_window` 累积，peak 检测本身只需要 `total_window` 大小的局部窗口，默认 10）

**不依赖**：252-day 波动率、63-day 平均成交量、任何因子指标。当前 gate 把 BO 事件和因子计算绑定，是**实现细节上溢**，而不是本质耦合。

### 2.2 "因子能否计算" 与"BO 是否存在" 正交

逐个审视 `FACTOR_REGISTRY`（factor_registry.py:83-195）的 buffer 来源：

| factor | buffer | 本质依赖 |
|---|---|---|
| age/test/height/peak_vol | 0 | 只读 `broken_peaks` 属性（来自 detector），无 df lookback |
| volume | 63 | `_calculate_volume_ratio` 用 63 天均量 |
| overshoot/day_str/pbm | 252 | 间接依赖 `_calculate_annual_volatility`（252d std） |
| streak | 0 | 读 `detector.breakout_history`（detector 状态） |
| drought | 0 | 读 `detector.get_days_since_last_breakout`（detector 状态） |
| pk_mom | 44 | pk_lookback(30) + atr_period(14) |
| pre_vol | 73 | vol_ratio rolling(63) + pre_vol_window(10) |
| ma_pos | 20 | MA 20 |
| dd_recov/ma_curve | 252/50 | 当前 INACTIVE |

**关键观察**：**所有 buffer 来源都是"df 历史窗口长度"**（波动率、均量、均线、ATR），**没有因子的 buffer 间接依赖突破历史本身**。streak/drought 虽然读 detector 状态，但那是当前 bar 时刻的快照，不是"需要 N 根历史 bar"意义上的 lookback——它们的 buffer=0 是合理的。

**结论**：两个概念确实正交。把 gate 下沉到因子级不会造成"因子计算反过来破坏 BO 检测"的循环依赖风险。

### 2.3 一个重要的次级效应

当前全局 gate 的一个**隐性副作用**：idx<252 区段的 BO 不写入 `breakout_history`。这使 idx∈[252, 252+streak_window) 区间内 `get_recent_breakout_count` 偏小、`get_days_since_last_breakout` 偏大或返回 None（把"252 之前本该存在的近期突破"擦除了）。这不是设计意图，只是 gate 上移的附带损伤（features.py:624-667 的注释也隐晦承认了这点：history 不完整会污染 drought/streak）。

**per-factor gate 会自动修复这个 bug**：detector 不再有 gate → history 完整 → drought/streak 对任何 idx≥0 的 BO 都给出诚实结果。这是提案的**意外正收益**。

---

## 3. 下游模块影响分析

### 3.1 Scorer（`breakout_scorer.py`）

现有 `_compute_factor`（breakout_scorer.py:181-221）的处理链：`nullable 分支 → zero_guard → enabled → level 映射`。路径 180-196 已经把 `raw_value is None` 且 `fi.nullable=True` 的情况转为 `multiplier=1.0, level=0, triggered=False`，与"未触发"等价。

**per-factor gate 在 scorer 的语义层面**：因子缺失 = 未触发 = 乘法中性（×1.0）。数学上对总分无贡献，正是提案期望的效果。

**需要区分"缺失"和"未触发"吗？** 从评分结果看没必要：两者对总分的数学影响都是 ×1.0，不区分也不会误导打分。**但为了 tooltip 可解释性**（见 3.4），应在 `FactorDetail` 里新增一个 `unavailable: bool` 或引入一个 `status` 枚举（`triggered/not_triggered/unavailable`），这是低成本改动。

**必要动作**：
1. 把所有因子的 `nullable` 从"仅 drought/pk_mom"扩展为"所有活跃因子"（或新增 `can_be_missing` 字段；实质相同）。
2. `scanner._serialize_factor_fields`（scanner.py:28-39）已用 `fi.nullable` 判断是否写 None，只要 nullable 扩展即可自动适配。
3. scorer 端的 None 分支已存在，无需改写。

### 3.2 Mining

#### 3.2.1 阈值挖掘（`threshold_optimizer.py`）

当前路径：`prepare_raw_values` → 用 `df[key].fillna(0)` 把 None 填 0（data_pipeline.py:178）→ 参与阈值候选（percentile/quantile）→ `build_triggered_matrix` 以 `>= threshold` 判定触发。

**问题**：如果 per-factor gate 让 idx<buffer 的 BO 对 volume 为 None，`fillna(0)` 后 0 值会被当成"volume=0 的真实观察"进入分布统计。这会：

- 扭曲阈值候选的 percentile（额外多了一堆 0 拉低下端）
- 扭曲 `trigger_rate` 的分母（0 肯定 < 阈值，算"未触发"，稀释了真实 volume 的触发率信号）
- 扭曲 `factor_diag.yaml` 里各因子的分布统计

**正确做法**：挖掘阶段，每个因子应用**各自的**有效样本集（从该因子 None 的行中剔除），再做分位数、阈值搜索、trigger rate。

这是 `has_nan_group=True` flag 的自然扩展——从目前 drought/pk_mom 专用扩展为**所有因子通用**。`distribution_analysis.py:161` 已经对 `has_nan_group=True` 做了 NaN 分组统计，逻辑可复用。

**建议**：删除 `has_nan_group` 字段（或默认 True），因为在 per-factor gate 架构下，**任何因子都有合法的"缺失"状态**。

#### 3.2.2 模板枚举与 TPE 评估

`template_generator.generate_templates`（template_generator.py:43-99）：二值化基于 `df[col] > 0`，`col` 是 `{key}_level`。如果该行某因子 None 导致 level=0，模板会把它当"未触发"。这**恰好兼容 missing-as-fail 语义**。

`threshold_optimizer.build_triggered_matrix`：同上。

**但 baseline_median 计算**（template_generator.py:118 / threshold_optimizer.py:584）用的是**全体 BO 的 label 中位数**。per-factor gate 引入后，全体 BO 样本数增加（idx<252 的也进来了），而短 lookback 段的标签分布可能不同（例如早期 IPO 股票波动性特殊）。**baseline 会漂移**，但这是真实信号而不是 bug——模板的 lift 评估本来就应包含这部分。

### 3.3 Template Matching（最棘手的语义选择）

`template_matcher.match_breakout`（template_matcher.py:69-92）**当前已经是 missing-as-fail**：

```python
value = bo_data.get(factor)
if value is None:
    return False  # 模板对该 BO 不匹配
```

这个逻辑在现状下只对 drought/pk_mom 这两个 `nullable=True` 的因子生效。扩展到 per-factor gate 后，该分支会被更多因子走到。我们要问：**missing-as-fail 是否符合用户语义？**

三种选项对比：

| 选项 | 语义 | 对 idx<252 的 BO 的后果 | 兼容性 |
|---|---|---|---|
| **A. missing-as-fail** | "缺失即视为不满足条件" | 含 overshoot/day_str/pbm 的模板对 idx<252 的 BO 一律不匹配 | **与当前代码一致** |
| B. missing-as-abstain | "模板对此 BO 不表态"（从该模板的统计/匹配中剔除该 BO） | idx<252 的 BO 不进入依赖 volatility 因子的模板，但可能匹配纯 resistance 因子模板 | 需改 `match_breakout` 返回 tri-state，改 denominator |
| C. partial match | "按可用因子匹配" | idx<252 的 BO 若已命中 age+height 就算匹配，即便模板还有 overshoot 要求 | **危险**——等价于降低触发标准，破坏模板质量保证 |

**判断**：C 基本可以排除，因为模板 median/q25 是在"所有因子齐备"的假设下统计出的，partial match 会让 idx<252 的样本以宽松标准"蹭"进来，引入选择偏差。

A vs B 的差别是**统计语义**的：
- A 承认"缺失就是不合格"，保守。idx<252 区段的 BO 基本都会被高质量模板拒绝（因为高质量模板倾向于包含 volatility 因子），等价于在 matching 层重现了一个软性的 max_buffer。
- B 让每个模板自己管理有效样本集，理论上更干净。但实现上要给 `match_all_stocks` 返回三态（match/no-match/abstain），UI 和下游消费者都要相应改。

**推荐选项 A**，理由：
1. 代码**零改动**（match_breakout 已是此语义）。
2. 和模板统计方法自洽（模板的 count/median 是在齐备样本上统计的，A 等价于"用同样齐备标准判断新 BO"）。
3. 对 idx<252 BO 的"歧视"是**合理且保守的**——我们本来就对这段样本的评估能力有限。

#### 3.3.1 检查 check_compatibility 和 scan_params

`template_matcher.check_compatibility`（template_matcher.py:136-187）只比对 detector 和 feature 参数，不涉及 buffer 概念。无影响。

### 3.4 UI 显示（`score_tooltip.py`）

当前 `_format_value`（第 275-286 行）：`unit=='d'` 时无条件 `f"{int(value)}d"`。如果因子缺失被 scorer 映射为 `raw_value=0`（breakout_scorer.py:193 的 nullable 分支），tooltip 会显示 "0d"——和"drought=0 天（刚刚有突破）"无法区分。

**per-factor gate 让这问题从 drought 一个因子蔓延到所有 nullable 因子**。volume 缺失会显示 "0.0x"，pbm 缺失会显示 "0.00"，overshoot 缺失会显示 "0.0σ"——都是**误导性**的（看起来像"因子极差"，实际是"无法计算"）。

**建议**：
- 在 `FactorDetail` 引入 `unavailable: bool` 字段（scorer 设置）。
- tooltip 在 `unavailable=True` 时显示 `"—"` 或 `"N/A"`（附 tooltip 二级注释 "insufficient lookback"）。
- 这是独立的 UI 层 polish，不阻塞主方案落地，但强烈建议同步完成。

### 3.5 json_adapter & 向后兼容

`json_adapter.py:283` 已用 `bo_data.get("drought")`（自然 None-safe）。只要所有 nullable 因子都走类似路径，加载旧 JSON（其中 idx<252 的 BO 不存在）不会出错——新扫描会产生更多 BO，与旧 JSON 并存时可能有"同一股票不同次扫描 BO 数量不一"的现象。这是**语义变化**（扫描语义变了），建议在 `scan_metadata` 里增加 `gate_mode: 'per_factor' | 'bo_level'` 字段做标记，避免混淆。

---

## 4. 设计权衡：Strict Contract vs Adaptive Degradation

### 4.1 当前设计的立场

`_calculate_annual_volatility` 的 `raise ValueError`（features.py:525-529）代表一种**"契约即保险丝"**哲学：宁可整条流水线炸，也不要让"短窗 std"这种近乎噪声的数字悄悄混进因子值。这个立场在**全局 gate 保证上游绝不越界**的前提下是合理的——契约永远不会触发，raise 只是防御性的最后一道栅栏。

### 4.2 新方案的本质不是"降级"而是"重新定义"

提案改为 `return None`——乍看是"悄悄降级"，但关键区别是：**None 不是退化的数值，而是"不可用"的显式标识**。它在类型上与一个糟糕的短窗 σ 不同：

- 坏的退化：`return std(returns[:5]) * sqrt(252)` —— 数值上无法与正常值区分，错误能传播下游而不被察觉。
- 正确的 None：`return None` —— 类型上和所有真实值不兼容，任何消费者都必须显式处理。

**结论**：per-factor gate 不是"削弱错误检测"，而是**重新划分"错误"和"正常缺失"的边界**。`idx < buffer` 在单股回测的自然边界段是**预期行为**（不是配置 bug），用 None 表达最合适。真正的配置错误（比如因子算法拼写错写了 252 为 2520）会表现为"所有 BO 都返回 None" —— 这种极端偏差在挖掘的 trigger_rate 监控中会立刻暴露。

### 4.3 如何区分"配置错误"和"自然边界"

- **配置错误的特征**：同一股票有充足 idx（>252）的 BO 也返回 None → 因子 trigger_rate 恒为 0 或 100%。
- **自然边界的特征**：仅 idx<buffer 段返回 None，其余正常 → trigger_rate 落在历史常态。

挖掘阶段的 `diagnose_log_scale` 和 `distribution_analysis` 都已按因子维度计算统计量，trigger_rate 监控天然能区分两种情况。**不需要专门的保险丝**。

---

## 5. 实现蓝图（伪代码级）

### 5.1 Detector 层：删除全局 gate

```python
# breakout_detector.py _check_breakouts
def _check_breakouts(self, current_idx, current_date):
    # 删除：if current_idx < self.max_buffer: return None
    # detector 永远检测，永远维护 history/peaks
    ...
```

`max_buffer` 字段和 `get_max_buffer()` 可保留（用于 UI/scan 的数据预处理 buffer_days 计算，那是 df 窗口需求，不是 BO gate），但**不再传给 detector 的 _check_breakouts 做门槛**。

### 5.2 Features 层：把 raise 改成 return None

```python
def _calculate_annual_volatility(self, df, idx):
    if idx < 252:
        return None  # 从 raise 改为显式缺失
    ...
```

`enrich_breakout` 的每个因子计算点需支持 None 传播：

```python
annual_volatility = self._calculate_annual_volatility(df, idx)  # 可能 None
day_str = self._calculate_day_str(...) if annual_volatility is not None else None
overshoot = self._calculate_overshoot(...) if annual_volatility is not None else None
pbm = self._calculate_pbm(...) if annual_volatility is not None else None
volume = self._calculate_volume_ratio(df, idx) if idx >= 63 else None
pre_vol = self._calculate_pre_breakout_volume(...) if idx >= 73 and vol_ratio_series is not None else None
pk_mom = self._calculate_pk_momentum(...) if idx >= 44 else None
ma_pos = self._calculate_ma_pos(df, idx) if idx >= 20 else None
```

**更优雅的做法**：在 `FeatureCalculator` 里建一个 `_factor_buffer_check(key, idx) -> bool` 的辅助，让每个因子 wrapper 统一走该检查。但第一版直接显式 if 更容易 review。

### 5.3 Registry 层：扩展 nullable

```python
# 把 FactorInfo.nullable 默认值改为 True，或者给所有涉及 lookback 的因子显式标 nullable=True
# has_nan_group 可以删除（或默认 True）
```

### 5.4 Scorer 层：新增 unavailable 标识

```python
@dataclass
class FactorDetail:
    ...
    unavailable: bool = False  # 新增

# _compute_factor 的 None 分支：
if raw_value is None:
    if fi.nullable:
        return FactorDetail(..., unavailable=True, triggered=False, multiplier=1.0)
```

### 5.5 Mining 层：有效样本集按因子区分

```python
# threshold_optimizer.stage3a_greedy_beam_search & stage3b
# 对每个因子，构建 valid_mask = ~df[key].isna()
# 计算分位数、trigger_rate 时用 valid_mask 过滤
```

关键改动点：`prepare_raw_values` 改成不 fillna（或者返回 `{key: (array, valid_mask)}` tuple），阈值搜索时只在有效样本上评估。

### 5.6 UI 层：N/A 显示

```python
# score_tooltip._format_value 外加一个分支
if factor.unavailable:
    return "N/A"  # 或 "—"
```

### 5.7 Scanner 序列化：None 透传

`_serialize_factor_fields`（scanner.py:28-39）已经根据 `fi.nullable` 正确处理。扩展 nullable 后自动兼容。

---

## 6. 风险与边界场景

### 6.1 所有因子 buffer=0

提案下等价于"没 gate"，完全正常——detector 无 gate，因子全部可算。这是 per-factor gate 最自然的退化。当前架构需 `get_max_buffer()` 返回 0，行为才等价；per-factor 架构下天然正确。

### 6.2 INACTIVE_FACTORS 改变后

当前 `get_max_buffer()` 会因活跃因子集变化而浮动（例如只开 age/height/streak → max_buffer=0 → detector 无 gate）。per-factor 方案下**根本没有这个联动**，每个因子独立判断 lookback。这是严格的进步：配置和行为的耦合被解除。

### 6.3 测试适配

`test_scanner_superseded.py:51` 传 `get_max_buffer()` 给 scanner。per-factor 架构下：

- scanner 仍可接受 `max_buffer` 参数（保持 API），但**不转发给 detector 作为 BO gate**，只用于 df 预处理 buffer（把足够历史加载进来）。
- 测试行为会变化：原本 idx<252 的 BO 不产生，新方案会产生（带部分因子 None）。若测试断言"恰好 N 个 BO"，数字会变。

**推荐**：测试应按新语义更新。原有的 "BO 数" 断言是对旧实现的 snapshot，没有稳定的功能意义。更好的测试是断言"idx>=252 的 BO 的因子字段与旧实现完全一致"+"idx<252 的 BO 出现，且依赖 volatility 的因子为 None"。

### 6.4 向后兼容的 JSON

旧 JSON 没有 idx<252 的 BO 记录。用户若重新扫描同一股票，会看到"该股票突然多了一批 BO"。解决：
- `scan_metadata` 新增 `gate_mode` 标记（per_factor vs bo_level）。
- 对比工具若发现 gate_mode 不同，提示"结果不可直接比较"。

旧 JSON 里 drought=None 的字段重新加载不会出问题（json_adapter 已 None-safe）。

### 6.5 BO 可能没有任何因子可算

极端 idx=0 的 BO（假设某种数据边角能触发）：所有 lookback>0 的因子都返回 None，仅 age/test/height/peak_vol/streak/drought 有值。scorer 算出的 total_score 基本是 base_score×1.0。这种"几乎没有因子贡献"的 BO 在模板匹配时会被 missing-as-fail 过滤掉——**行为上等价于旧架构把它 gate 掉了**，但在 history 里它还是个合法的突破事件（这是对的）。

### 6.6 Drought/Streak 的"诚实化"带来的 re-labeling

per-factor gate 让 detector history 跨越原 idx=252 边界完整。这意味着：
- idx=260 的 BO 的 drought 可能从"None（原 history 为空）"变成"8d（距 idx=252 那次真实突破 8 天）"。
- **drought/streak 的训练数据分布会变**。已训练的 filter.yaml 阈值可能不最优——需要重跑挖掘。

这不是 bug，是质量修复。预期正向影响：短 lookback 段的模板评估更诚实。

---

## 7. 结论与建议

### 7.1 总体判断：**支持采纳**

**采纳理由**：
1. **概念上正确**：BO 存在性与因子可计算性确实正交，现架构把它们耦合是实现污染。
2. **意外修复 bug**：detector history 不再被 gate 掉，drought/streak 对 idx<max_buffer 段的 BO 重新变诚实。
3. **解耦配置联动**：INACTIVE_FACTORS 变化不再间接改变 detector 行为（现架构下若加入新长 buffer 因子，整条流水线的 BO 分布都会漂移，debug 困难）。
4. **实现代价低**：核心改动约 10 处，语义边界清晰，可分阶段落地。
5. **strict contract 哲学不被削弱**：`return None` 是类型化的"不可用"信号，不是数值降级。

### 7.2 采纳条件

必须同步完成：
- **选择 missing-as-fail 作为模板匹配语义**（与现有 `match_breakout` 一致，零 UI/下游改动）。
- **所有 lookback 因子改为 nullable**（或把 `nullable` 作为默认行为）。
- **挖掘的 raw_values / 分位数 / trigger_rate 改为按因子 valid_mask 统计**（否则 factor_diag.yaml 会被 0 填充污染）。
- **UI tooltip 区分 N/A 与 0**（低优先，但强烈建议）。
- **scan_metadata 增加 `gate_mode` 字段**标记新旧语义（避免对比工具错解读）。

### 7.3 实施路径建议

**阶段 1（最小可行变更）**：
1. `_check_breakouts` 删除 `if current_idx < self.max_buffer: return None`。
2. `_calculate_annual_volatility` 的 raise 改为 return None。
3. `enrich_breakout` 对每个因子加 `idx < buffer` 的短路（return None）。
4. 所有涉及 lookback 的 FactorInfo 设 `nullable=True`。
5. 跑回归测试：idx≥252 的 BO 行为不变。

**阶段 2（挖掘适配）**：
6. `prepare_raw_values` 不 fillna；或新增 `prepare_raw_values_with_mask`。
7. `threshold_optimizer` 的分位数/TPE 目标使用 per-factor valid_mask。
8. 重跑挖掘，产出新 filter.yaml，验证 top-k 模板的 median 稳定性。

**阶段 3（UI/兼容）**：
9. `FactorDetail.unavailable` 新增字段，tooltip 显示 N/A。
10. `scan_metadata.gate_mode='per_factor'` 写入。
11. 更新 `test_scanner_superseded.py` 的断言语义。

### 7.4 反对意见的回应

可能的质疑："这会让错误检测能力变弱"。
回应：当前 raise 在**生产路径上永远不会触发**（因为 gate 保证了契约）。它只是防御性 assert。per-factor 架构下，"自然缺失"成为预期行为，用 None 表达就是类型化契约。真正的配置错误会以 trigger_rate 异常表现出来，监控链路不弱反强。

可能的质疑："现有 filter.yaml 的阈值是基于旧样本集算的"。
回应：对。需要重跑挖掘。这是一次性的数据迁移成本，不是架构的内在缺陷。

---

## 附录：改动点速查表

| 文件 | 位置 | 改动 |
|---|---|---|
| `breakout_detector.py` | 567-573 | 删除 `if current_idx < self.max_buffer: return None` |
| `breakout_detector.py` | 214-273 | `max_buffer` 参数保留但变为无作用（或移除） |
| `features.py` | 525-529 | `raise ValueError` → `return None` |
| `features.py` | 134-188 | 每个因子计算前加 `idx < buffer` 短路 |
| `features.py` | 490-491 (gain_window)、736、814 | 原有短路已是 `return 0.0`，改为 `return None` |
| `factor_registry.py` | FACTOR_REGISTRY | lookback 因子全部加 `nullable=True` |
| `breakout_scorer.py` | FactorDetail | 新增 `unavailable: bool` |
| `breakout_scorer.py` | 190-196 | nullable 分支设置 `unavailable=True` |
| `mining/data_pipeline.py` | 178 | `fillna(0)` 改为保留 NaN 或返回 mask |
| `mining/threshold_optimizer.py` | bounds/fast_evaluate | 按因子 valid_mask 计算分位数和 trigger_rate |
| `UI/charts/components/score_tooltip.py` | 275-286 | `_format_value` 支持 unavailable → "N/A" |
| `analysis/scanner.py` | scan_metadata 输出 | 新增 `gate_mode` 字段 |
| `tests/test_scanner_superseded.py` | 51 + 断言 | 更新为新语义 |
