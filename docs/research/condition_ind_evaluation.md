# Condition_Ind 结构性评估 — 与 BO 因子框架的关系、改进空间、替代架构

> 研究单位：condition-ind-eval agent team（overlap-mapper / condition-ind-improver / composition-arch-researcher / team-lead）
> 完成日期：2026-05-09
> 评估对象：`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py`（约 60 行）
> 引用底稿：`_team_drafts2/overlap_mapping.md`、`_team_drafts2/condition_ind_improvement.md`、`_team_drafts2/composition_architectures.md`
> 前序研究：[composite_pattern_architecture.md](composite_pattern_architecture.md)（同目录）

---

## 0. 摘要

针对用户的三个问题，团队结论：

| 用户问题 | 团队结论（一句话） |
|---|---|
| **1. Condition_Ind 与 BO 因子框架的关系，是否重叠冗余？** | **几乎不重叠**。两者在时间轴和评估单位上正交（事件 vs bar、AND-of-scalars vs AND-of-temporal-windows）。表面上重叠的"时间窗"和"AND"在语义上完全不同，**不互冗余**。 |
| **2. Condition_Ind 是否有改进提升的空间？** | **大量 — 但是不要在 new_trade 仓库里改它**。它的 base.py 60 行只是一个未稳定的最小骨架，产线扩展（`Result_ind`/`Hole_St`/`MA_Converge`）已**全部消失**，证明全功能扩展在产线上失败了。对 Trade_Strategy 而言，正确做法是**只吸收它没解决的那一类需求维度**（窗口 quantifier 聚合），不要照抄它的 API 形状。 |
| **3. 是否有更好的架构？** | **有，但不是当下答案**。Reactive Streams (FRP) 是 Condition_Ind 概念上的"自然演化方向"（Indicator+valid → Observable，exp → window_with_count，等等），但在金融生产环境**缺成功案例**，落地有重演 new_trade 失败模式的风险。Behavior Trees / Parser Combinators 各有亮点但没有更优。**当下不引入任何新顶层架构**。 |

**最终行动建议**（一句话）：在 [BreakoutStrategy/analysis/](../../BreakoutStrategy/analysis/) 下新增一个 `window_aggregator.py`，提供 4 个纯 NumPy 工具函数（`hit_in_window` / `count_in_window` / `ratio_in_window` / `all_in_window`，约 80 行），供新增的窗口聚合类因子（如 `ma_flat`）内部调用 — 这是 Condition_Ind 真正能贡献给 Trade_Strategy 的全部价值，**不引入任何新架构层**。

**与前序研究的关系**：这份研究**精确化**了前序研究 [composite_pattern_architecture.md](composite_pattern_architecture.md) 的 Stage 2 中间形态 — 把"`ChainCondition` + `post_event_lookforward` 因子"进一步收紧为"4 个工具函数 + 现有 factor 框架的扩展"，避免引入"独立 ChainCondition class"这一新概念。

---

## 1. 团队收敛过程（三方立场如何变化）

研究采用两轮工作流：phase 1 各自独立分析，phase 2 互相挑战。最终立场显著收敛 — 这是研究真正的可信度来源。

| 专家 | Phase 1 立场 | Phase 2 修正后立场 |
|------|------|------|
| **overlap-mapper** | 80-150 行 ChainCondition wrapper 作为 BO factor 私有实现 | **进一步收紧** — 不要 class wrapper，4 个工具函数即可（80 行） |
| **condition-ind-improver** | v2 全套（B1 状态封装 + B2 Quantifier + B3 CarryAttr + B4 脱离 backtrader）| **大幅收敛** — 撤回 B4（Trade_Strategy 本来就不用 backtrader）；承认 B3 是 hypothetical；只保留 B2 内核，以 overlap-mapper 的工具函数形式落地 |
| **composition-arch-researcher** | Rx + MR + Dask 3 层架构作为顶层 | **修订为 research direction** — overlap-mapper 在当下场景里是对的；3 层架构是远期演化方向不是 production 推荐 |

三方在 phase 2 都做了诚实的让步。最终共识：**最小可行整合 = 4 个工具函数**，其余全部进 research bin。

---

## 2. 概念层映射 — 两套架构正交

来自 overlap-mapper 的精确表格（详见底稿）：

| 维度 | BO 因子框架 | Condition_Ind | 关系 |
|------|------|------|------|
| 事件 / 评估单位 | "一次突破"，事件离散化 | "一根 K 线"，bar-stream 稠密 | **冲突** — 两者的"行"不在同一时间轴 |
| 单一原子条件 | factor（事件级标量） | cond（bar 级布尔/数值） | **互补** — 原子性在不同粒度 |
| 阈值 | 多档 + YAML 外置 + Optuna 可搜 | 硬编码进类参数 | **互补** — 这是 BO 能跑 mining、Condition_Ind 不能的根因 |
| 时间窗口 | `lookback`：窗口聚合标量化 | `exp`：OR-over-time 布尔 | **互补但易混淆**（详见 §3.1）|
| 触发判定 | `level > 0` 横截面布尔向量 | `last_meet_pos` 滑动窗口布尔向量 | **互补** |
| 组合（AND/OR）| bit-packed AND only | AND + min_score 软门槛 + 嵌套 | **重叠 + 互补**（详见 §3.2）|
| 评分输出 | 连续乘数 → mining median 优劣度 | 仅二值 valid line | **冲突** — Condition_Ind 缺"分数化"，天然不与 mining 工作流契合 |
| **嵌套层级** | **不支持**（factor 是平的） | **支持**（cond.ind 可以是另一个 Condition_Ind） | **Condition_Ind 独有** |
| 状态持久化 | detector 层（峰值） | 每个 cond 层（满足时刻 + 状态机） | **互补** |
| 流式 vs 批处理 | 增量 + 批量都跑同一份代码 | 必须流式（backtrader 框架强制） | 重叠但 BO 框架已分离两种模式 |

**关键判断**：表面上重叠的"时间窗"和"AND"在语义上完全不同（详见 §3）。两套架构在时间轴和评估单位上**正交** — 这是为什么"是否冗余"的答案是"不冗余"。

---

## 3. 重叠点的精确分析 — 不冗余

### 3.1 时间窗口：`lookback` vs `exp` 不等价

- **BO `lookback`**：在事件 t 当下，回看 `[t-lookback, t]` 这 `lookback+1` 根 bar，**聚合**出一个标量。例：`pre_vol` 取窗口内最大放量倍数（[features.py:911-931](../../BreakoutStrategy/analysis/features.py#L911-L931)）。**输出是 float**。
- **Condition_Ind `exp`**：每根 bar 上检查"过去 `exp` 根内是否有任一帧满足 cond"，**等价于 OR-over-time**（[base.py:48](file:///home/yu/PycharmProjects/new_trade/screener/state_inds/base.py#L48)）。**输出是 bool**。

**能否互相表达**：
- 用 `exp` 模拟 `lookback`：可以，但只能拿到"是否触发过"的布尔，丢失阈值梯度，无法被 Optuna 搜索
- 用 `lookback` 模拟 `exp`：可以，且更灵活 — 在 BO 框架里写一个新 factor `xxx_in_window`，内部用 `np.any(window_signal)` 即得 OR-over-time

**结论**：`exp` 的功能可被 BO 框架的"窗口聚合 factor"完全吸收（这正是本研究最终建议的方向），反向不成立。

### 3.2 组合 AND：bit-packed AND vs must-全 True 不等价

- BO 的 AND 在**事件横截面**上：N 个 factor triggered 向量做位与
- Condition_Ind 的 AND 在**时间维**上：每个 cond 在自己的时间窗内 OR-over-time，再 AND

**能否互相表达**：
- BO 不能编码"先 X 后 Y"或跨时点关系（前序主报告已确认）
- Condition_Ind 不能编码"恰好 N 次"和严格顺序（exp 是无序窗口，min_score 是 ≥）

**结论**：两套 AND 在不同时间维度运作，**不冗余**。Condition_Ind 比 BO 多"软同时性"；BO 比 Condition_Ind 多"挖出来的阈值可被 Optuna 调"。

### 3.3 各自的独有能力

**BO 框架独有**（Condition_Ind 完全没有）：
- bit-packed AND 模板挖掘（[threshold_optimizer.py:60-115](../../BreakoutStrategy/mining/threshold_optimizer.py#L60-L115)，~1ms 评估上千模板）
- Optuna TPE 阈值搜索
- Bootstrap CI 稳定性验证
- 批量打分（vector ready）
- 三态 unavailable 语义（`FactorDetail.unavailable` + `Optional[float]`）
- per-factor lookback SSOT（[features.py:107-143](../../BreakoutStrategy/analysis/features.py#L107-L143)）
- mining 流水线接口契约（factor_diag.yaml → filter.yaml → all_factor.yaml）
- 元数据驱动 UI

**Condition_Ind 独有**（BO 框架完全没有）：
- 嵌套层级 / 谓词复用（cond.ind 可以是另一个 Condition_Ind）
- OR-over-time（exp 软同时性）
- 状态机建模（如 `BreakoutPullbackEntry.state` 5 状态机）
- indicator-as-first-class（任何指标都是统一接口）
- `min_score` 软门槛
- 生产扩展属性（`keep`、`keep_prop`、`exp_cond`、`relaxed`）— **但见 §4.0**

---

## 4. Condition_Ind 的设计缺陷

### 4.0 一个先于"缺陷分析"的实证发现（来自 condition-ind-improver §0）

`grep -r "class Result_ind" new_trade` 返回 0 行。事实清单：
- [wide_scr.py:48](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L48) 用到的 `Result_ind` — **不存在**
- [wide_scr.py:78](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L78) 用到的 `Hole_St` — **不存在**
- [wide_scr.py:37](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L37) 用到的 `MA_Converge` — **不存在**
- [wide_scr.py:4](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L4) `from screener.state_inds.Condition_ind import ...` 整个模块路径 — **不存在**

**含义**：历史上确实存在过一个"全功能扩展版" `Condition_Ind`（带 `keep`/`keep_prop`/`exp_cond`/`relaxed` 字段），但它**没能稳定为可复用的 base API**，要么被删了要么被分散重写到各业务子类里。base.py 留下的 60 行只是"语义最小子集"。这是评价"改进空间"的最核心证据：**扩展不是"想加什么"，而是"已经加过、加偏了、又退回来了"**。

这个发现直接修订了对 Condition_Ind 的整体定位 — 它不是"成熟的可借鉴接口"，而是一个"未稳定的最小骨架"。它的产线扩展失败本身就是给我们的教训。

### 4.1 现有设计的关键缺陷（精简版）

来自 condition-ind-improver 的 A1-A9（详见底稿 `condition_ind_improvement.md`）。这里只列对 Trade_Strategy 有借鉴意义的：

| # | 缺陷 | 实战代价 | 启示 |
|---|---|---|---|
| **A1** | 三个并行数组 `last_meet_pos` / `scores` / `must_pos` 状态散落，无统一抽象 | 序列化困难、测试困难、调试 print-driven | Trade_Strategy 任何引入"窗口状态"的代码必须用 dataclass 封装 |
| **A2** | `min_score` 是数值门槛，无法表达结构化 OR / k-of-n / 条件依赖 | 每出现新聚合方式就新建一个子类 | Trade_Strategy 的 mining 把"组合"分配给外部模板枚举，避开了这个问题 |
| **A3** | `causal` 命名严重误导（实际是"是否消费同根的子 valid"） | 新人教材级误解；产线一律用 `causal=False` 把反直觉用反直觉名挡住 | 命名是工程债 — 任何引入到 Trade_Strategy 的概念都要明确命名 |
| **A4** | 缺 quantifier（计数 / 比例 / 全持续 / latch 都没有原生支持） | 产线必须自扩展 `keep`/`keep_prop`/`exp_cond`/`relaxed`，又没稳定下来（§4.0）| **这是 Trade_Strategy 真正可吸收的能力空白** |
| **A5** | base 接口与产线扩展接口已**事实上不一致** | base.py 不是 production interface 的真实定义 | 不要照搬 base.py 字段 |
| **A6** | 无"跨条件状态传递" — 事件之间无引用关系 | MR 的 `LAST(BO.resistance)` 等价物缺失 | 对应前序主报告 Stage 3 临界条件，当下不需要 |
| **A7** | 输出仅一条 `valid` 线，单通道无结构化结果 | 调试 print-driven 而非 introspection-driven | 任何吸收时都用 `Optional[float]` + `unavailable` 三态 |
| **A8** | 流式订阅与批处理脱节，绑死 backtrader | 无法对 DataFrame 一次性扫描，无法进 mining 流水线 | Trade_Strategy 本来就不用 backtrader，moot |
| **A9** | 类爆炸 — 每条规律新写状态机子类 | 接口缺陷外推为类爆炸 | 警告：任何引入"自定义复合谓词"的设计要防止类爆炸 |

### 4.2 真正可吸收的能力维度

经过 phase 2 收敛，团队一致认为：**只有 A4（Quantifier 抽象）是 Trade_Strategy 真正缺少的能力**。其它要么 Trade_Strategy 已经规避了（A8 backtrader、A2 组合外置）、要么是 hypothetical 需求（A6 跨条件引用）、要么是设计教训（A1 状态封装、A3 命名）。

---

## 5. 改进方向的取舍（improver B1-B4 经过团队挑战）

condition-ind-improver phase 1 提出 4 个改进方向。Phase 2 经过挑战后的最终评估：

| 改进 | Phase 1 ROI | Phase 2 修正 | Trade_Strategy 真需要吗？ |
|------|------|------|------|
| **B4 脱离 backtrader** | #1 | **撤回** | 不需要 — Trade_Strategy 本来就不用 backtrader |
| **B2 Quantifier 抽象** | #2 | **#1（唯一保留）** | **真需要** — 用户规律 1（多 BO 聚集）+ 规律 3（MA40 持续横盘）的硬需求 |
| **B1 状态封装（dataclass）** | #3 | **降为 B2 的副产物** | 不独立需要 — 简单工具函数无需封装 |
| **B3 跨条件状态传递（CarryAttr）** | 延后 | **延后到 Stage 3** | 不需要 — 对应前序主报告 Stage 3 临界（≥1 条强顺序 + 跨事件引用规律） |
| **结构化 Aggregator（KOfN/BoolExpr）** | (B2 子项) | **真不用** | BO 框架的事件聚合靠 mining 枚举 AND 模板，不需要在因子内部表达 OR/k-of-n |
| **AggregateResult 多通道输出** | (B2 子项) | **真不用** | mining 只看 matched bool；多通道是开发体验提升 |

**唯一保留**：**B2（Quantifier 抽象）**，且形态进一步降级 — 不需要 class，4 个工具函数即可。

---

## 6. 替代架构调研 — 为什么没有更优

来自 composition-arch-researcher 的 7 类调研（详见底稿 `composition_architectures.md`）。这里只给最终评判：

| 排名 | 范式 | 评判（phase 2 修正后） |
|------|------|------|
| 1 | **Reactive Streams (FRP / RxPY)** | 概念上是 Condition_Ind 的"自然演化方向"，但**金融生产案例缺失**。context7 查询 RxPY 770 个代码片段中**没有任何金融/量化案例**；已知 Rx 在金融主要用于 IO/订阅/事件分发层，**不是策略组合层**。落地有重演 new_trade 失败模式的风险。**当下不推荐**。 |
| 2 | **Behavior Trees** | Sequence+memory 状态机自然，Decorator 一阶可复用。但金融时序生态弱、缺时间窗内建算子、bit-packed 评估失效。**当下不推荐**。 |
| 3 | **Parser Combinators** | MR 在代码层的等价物，理论最强（任意 Python 函数 + 闭包复用），但 Python 时序 parser combinator 库**生态最弱**。如果未来要做 MR，可以在这条路径上自研。**研究方向，不是当下方案**。 |
| 4-7 | Dataflow / HFSM / Petri / Monadic | 不是"组合层"而是"执行后端"或与已淘汰范式重合。**不推荐**。 |

**核心修正**（来自 composition-arch-researcher phase 2）：

> 我把 3 层架构（Rx 组合 + MR 匹配 + Dask 后端）作为顶层定位**在当下是错的**。"特征组合作为顶层架构"在 Trade_Strategy 实际工作流里**找不到承载它的需求** — 当前只有 1 条复合规律，bit-packed mining 是真实硬资产，BO factor 已经是事件级标量不需要 stream 代数。

**临界条件**（什么时候 3 层架构才有真实需求 — 任一触发）：
- 第 ≥ 5 条复合规律且每条都需要新增一类窗口聚合 / 跨条件引用 / 状态机
- mining 开始挖"特征组合结构本身"（不止挖阈值，还挖"哪些原子条件以何种方式组合"）
- 多策略需要共享原子特征（5+ 策略都用"放量 BO + 平 MA"）

**现状离这三个临界点都很远**。

---

## 7. 推荐的最小整合方案 — 4 个工具函数

来自 overlap-mapper phase 2 修正后的最终方案。

### 7.1 实现

在 [BreakoutStrategy/analysis/](../../BreakoutStrategy/analysis/) 下新增一个 `window_aggregator.py`（约 80 行），提供 4 个纯函数：

```python
def hit_in_window(predicate: np.ndarray, window: int, idx: int) -> bool:
    """过去 window 根内是否有任一帧满足 predicate（OR-over-time）。"""

def count_in_window(predicate: np.ndarray, window: int, idx: int) -> int:
    """过去 window 根内 predicate 满足的次数。"""

def ratio_in_window(predicate: np.ndarray, window: int, idx: int) -> float:
    """过去 window 根内 predicate 满足的比例（0..1）。"""

def all_in_window(predicate: np.ndarray, window: int, idx: int) -> bool:
    """过去 window 根 predicate 是否全满足。"""
```

### 7.2 使用方式

新 factor `ma_flat`（前序研究 Stage 1 已建议）的 `_calculate_xxx` 内部调 `ratio_in_window` 实现"过去 W 天里 X% 的天斜率小"：

```python
def _calculate_ma_flat(df, idx, lookback=40, slope_thresh=0.0005, ratio_thresh=0.8):
    slopes_abs = np.abs(_compute_ma_slope_series(df, period=40))
    flat_predicate = slopes_abs < slope_thresh
    actual_ratio = ratio_in_window(flat_predicate, lookback, idx)
    return actual_ratio if actual_ratio >= ratio_thresh else 0.0
```

### 7.3 设计承诺

- **不引入新概念** — 不是 class 层级，是工具函数
- **不破坏 FACTOR_REGISTRY 契约** — `ma_flat` 是普通 factor，输出 `Optional[float]`，与 `FactorDetail.unavailable` 三态机制无缝衔接
- **mining bit-packed 不动** — `ma_flat` 是普通 binary factor，进 bit-packed AND 模板
- **比 ChainCondition class 更小**（80 行 vs 150 行），比 v2 远小（80 行 vs 数百行 + 多抽象层）
- **可测性最优**：`pytest` 5 行造个 NumPy 数组就能 assert 工具函数正确性

### 7.4 这条路径的本质

> 把 Condition_Ind 试图做但失败的"窗口 quantifier 抽象"以最朴素的形态吸收进 BO 框架，其它能力（嵌套、状态机、跨 cond 引用）放弃。

---

## 8. 演化路径（按时间尺度分层）

| 阶段 | 推荐方案 | 触发条件 |
|---|---|---|
| **当下（0-3 个月）** | overlap-mapper 的 `window_aggregator.py` 4 个工具函数 + 主报告 Stage 1 的 `ma_flat` 因子 | 已就绪 |
| **中期（3-12 个月，**条件触发**）** | 升级为 condition-ind-improver 的"轻量 ConditionInd v2"（B1+B2 = dataclass + 多 Quantifier 类型）| `window_aggregator` 工具函数被 ≥ 3 个 factor 内嵌使用，且模式开始重复时 |
| **远期（12+ 个月，条件触发）** | 走前序主报告 Stage 3 — MATCH_RECOGNIZE 风格事件正则匹配 | 前序主报告 §3.4 临界条件触发（≥ 2 条 post-event 规律 + 跨事件引用，或 ≥ 1 条强顺序角色规律） |
| **research bin** | composition-arch-researcher 的 Rx + MR + Dask 3 层架构 | 多策略 + 复合规律池 + mining 自动化结构挖掘三者同时出现 — 现在远未到 |

---

## 9. 决策清单（Action Items）

```
□ 1. 立即可做：在 BreakoutStrategy/analysis/ 下创建 window_aggregator.py，
     实现 4 个工具函数（hit / count / ratio / all_in_window）

□ 2. 立即可做：用 window_aggregator 作为 ma_flat 因子的内部实现工具
     （前序主报告 Stage 1 的具体实现细节）

□ 3. 不要做：不要引入 ChainCondition class
□ 4. 不要做：不要引入独立的 ConditionInd v2 抽象
□ 5. 不要做：不要引入 RxPY 或任何 stream 代数
□ 6. 不要做：不要立即启动 MATCH_RECOGNIZE 路径
□ 7. 不要做：不要把 backtrader 引入 Trade_Strategy（保持 pandas + NumPy 基线）

□ 8. 监控：window_aggregator 工具函数被 ≥ 3 个新 factor 调用时，
     重新评估是否升级为 ConditionInd v2 形态
```

---

## 10. 引用与延伸阅读

### 团队底稿（详细分析）
- [底稿 1 — 概念层映射 + 重叠/冗余精确分析](_team_drafts2/overlap_mapping.md)（overlap-mapper）
- [底稿 2 — Condition_Ind 缺陷与改进设计](_team_drafts2/condition_ind_improvement.md)（condition-ind-improver）
- [底稿 3 — 替代组合架构调研（FRP / Behavior Trees / Parser Combinators 等）](_team_drafts2/composition_architectures.md)（composition-arch-researcher）

### 前序研究
- [composite_pattern_architecture.md](composite_pattern_architecture.md) — 复合走势规律的因子架构选型（本研究的上游）

### 关键代码引用
- Condition_Ind 实现：[/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59](file:///home/yu/PycharmProjects/new_trade/screener/state_inds/base.py#L7-L59)
- 现行因子注册表：[BreakoutStrategy/factor_registry.py:70-256](../../BreakoutStrategy/factor_registry.py#L70-L256)
- 评分聚合：[BreakoutStrategy/analysis/breakout_scorer.py:253-288](../../BreakoutStrategy/analysis/breakout_scorer.py#L253-L288)
- 挖掘的 bit-packed AND：[BreakoutStrategy/mining/threshold_optimizer.py:60-115](../../BreakoutStrategy/mining/threshold_optimizer.py#L60-L115)
- Per-factor lookback SSOT：[BreakoutStrategy/analysis/features.py:107-143](../../BreakoutStrategy/analysis/features.py#L107-L143)
- 突破扫描模块文档：[.claude/docs/modules/突破扫描模块.md](../../.claude/docs/modules/突破扫描模块.md)
- 数据挖掘模块文档：[.claude/docs/modules/数据挖掘模块.md](../../.claude/docs/modules/数据挖掘模块.md)

---

**报告结束。**
