# 入口一能否支持 BO 拥有非因果因子

> 研究单位：cind-edge-cases team / Tom
> 完成日期：2026-05-10
> 关联文档：[`cind_compute_layer_design.md`](../cind_compute_layer_design.md)、[`cind_chain_mechanism_revisited.md`](../cind_chain_mechanism_revisited.md)、[`composite_pattern_architecture.md`](../composite_pattern_architecture.md) §3.1

---

## 0. 一句话结论

**能。**入口一支持 BO 拥有 lookforward 因子，**但不是用魔法绕过物理时延，而是把"K 根 bar 后才有值"显式表达为 `unavailable=True` 三态 + Optional 标量字段**。该方案在 mining/dev/live 三场景下行为统一，与 `Platform-as-Event` 在产出上**等价**，但**入口一的 lookforward 因子方案侵入性显著更小**，应作为首选；只有当用户决定"以平台形成而非 BO 作为统计单位"时,才升级为入口二的多事件主干。

---

## 1. `TemporalFactorInfo` 的具体设计

### 1.1 字段扩展（基于现有 `FactorInfo`）

```python
@dataclass(frozen=True)
class TemporalFactorInfo(FactorInfo):
    """链式因子（来自 EventChain）。在 FactorInfo 基础上加 3 个字段。"""
    chain: 'EventChain'                                 # 因子的事件链定义
    causality: Literal['causal', 'lookforward'] = 'causal'
    lookforward_bars: int = 0                           # 因果性=lookforward 时,需要 BO 之后多少根 bar
```

**`causality` 语义**：类型级元数据，`enrich_breakout` 路由到不同执行路径；mining label 校验也用它来防止 leakage（causal 因子参与所有 BO，lookforward 因子在 BO 后 K 根不足时**强制 unavailable**）。

**`lookforward_bars` 语义**：等同于 `K`。`platform_post_bo` 的 K=10 表示因子需要 BO 当日 + 之后 10 根 bar 才能算出。

### 1.2 `evaluate_at(df, idx, mode)` 伪代码

```python
class EventChain:
    causality: Literal['causal', 'lookforward'] = 'causal'
    lookforward_bars: int = 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """整段 series。lookforward 链最后 K 根自然为 NaN（pandas rolling 的天然行为）。"""
        ...

    def evaluate_at(self, df, idx, mode: Literal['training', 'live']) -> Optional[float]:
        series = self.evaluate_batch(df)
        if self.causality == 'causal':
            v = series.iloc[idx]
            return None if pd.isna(v) else float(v)

        # lookforward
        bars_after = len(df) - 1 - idx
        if bars_after < self.lookforward_bars:
            # 物理时延约束触发
            return None  # → unavailable=True 路径
        v = series.iloc[idx + self.lookforward_bars]
        return None if pd.isna(v) else float(v)
```

**关键不变量**：`evaluate_at` 在 mining/dev/live **同一份代码、同一份 df**，差别只是 `idx` 和 df 的右边界 — `mode` 参数当前不影响返回值（`training` 和 `live` 都受同样的物理时延约束）。保留 `mode` 形参只为未来扩展（例如 mining 可对 incomplete 样本告警）。

---

## 2. BO 当日评分这个不变量是否被破坏

### 2.1 严格说法

**不变量没有被破坏，但需要重新阐述**：BO 当日**仍然评分**，只是该 BO 的 `quality_score` 在**当日是 partial、K 天后 refresh 为 complete**。这正是 `Breakout` dataclass 已有的 `Optional[float]` + `FactorDetail.unavailable=True` 三态机制的自然延展。

### 2.2 三个候选设计的对比

| 选项 | 当日行为 | K 天后行为 | 与现有约定的一致性 |
|---|---|---|---|
| **(a) partial score + refresh** | platform 因子 unavailable=True，乘子=1.0；BO 当日给 partial quality_score | K 天后 refresh，platform 因子 available；quality_score 重算为 complete | **完全契合** — 与 `volume`/`pbm` 等 nullable=True 的 lookback 不足处理一致 |
| (b) 等 K 天后才首次 score | BO 当日不发信号 | K 天后才有第一份 quality_score | 破坏"信号实时可发"约定；breakout 对象生成与评分**绑定** |
| (c) 双信号（prediction + confirmation） | 当日发"prediction"，标记 unconfirmed | K 天后发"confirmation" | 信号语义被分裂；UI 与下游消费者要全部改造 |

### 2.3 推荐 (a)

**理由**：

1. `FactorDetail.unavailable=True` 已存在（[breakout_scorer.py:34](../../../BreakoutStrategy/analysis/breakout_scorer.py#L34)），且评分时 `multiplier=1.0`、`triggered=False` 的处理已经写好（[breakout_scorer.py:194-198](../../../BreakoutStrategy/analysis/breakout_scorer.py#L194-L198)）。lookforward 因子在 K 天前的 unavailable 状态**与 lookback 不足时一模一样**，框架不需要新增三态。
2. 入口一的核心不变量 #1 是"统计单位 = BO"、#2 是"评分时刻 = BO 当日"、#3 是"信号实时可发"。(a) 全部满足，只是把"评分质量随时间提升"作为新维度加入 — 这个维度在 mining 中天然存在（label 也是 BO+max_days 后才确定）。
3. 与 `pk_mom` / `dd_recov` 的 `nullable=True` 是同一种契约；scorer 已经能正确处理一个因子缺席时的乘法模型。

**实现侵入性**：`Breakout` dataclass 新增 `platform_post_bo: Optional[float] = None`；`enrich_breakout` 在路由分支里调 `chain.evaluate_at(df, idx, mode)`；`live` 端在每日 daily_runner 的 step2_scan 后**自动**重算所有 K 天内的旧 BO 即可（已有的"全 DataFrame 重跑"是天然刷新机制，无需主动 refresh 接口）。

---

## 3. mining/dev/live 三场景下的具体行为

| 场景 | df 右边界 | 对一个 idx=`bo_idx` 的 BO | `platform_post_bo` 值 | 注 |
|---|---|---|---|---|
| **mining**（历史回测） | 历史末日（远 > bo_idx + K） | `evaluate_at(df, bo_idx, 'training')` | 总能算出 → float | 与 label 一致：mining 默认要求 `bars_after >= K`，否则 BO 不进 trial |
| **dev**（拖时间轴） | 用户指定的 right_edge | `evaluate_at(df, bo_idx, 'training')` | bars_after≥K → float；否则 → None（unavailable）| UI 应显示"待观测 K 天" 而非空白 |
| **live**（每日 batch refresh） | today | 最新 BO 的 `bo_idx ≈ len(df)-1`，bars_after≈0 | None（unavailable）| K 天后下一次 daily run 自动 refresh |

**统一行为**：三场景**共享同一份 `evaluate_at`**；`unavailable=True` 不分 mode。差异**只在 `df` 的右边界**。这正是 `cind_compute_layer_design.md` §3 四层架构想要的"事件 series 是统一货币，取样时刻分训练态/实时态"的精确落地。

**`Breakout.platform_post_bo` 的取值规则**：

- 三场景均使用 `Optional[float]` 类型签名
- `None` 表示"还没积累够 K 根 bar"，scorer 中 `unavailable=True`、`multiplier=1.0`
- 一旦右边界推进到 `bo_idx + K`，下一次重跑自动写入 float

---

## 4. 物理时延承认

**用户给的理解完全正确**。lookforward 因子在入口一里的支持**不是逃避物理时延，而是承认它 + 把它做成显式三态**。任何架构（入口一、入口二、MATCH_RECOGNIZE）都满足同一物理事实：**第 K 根 bar 不存在时，post-BO 信息就是不存在**。

### 4.1 live 端的"诚实产品语义"

对于 K=10 的 `platform_post_bo`：

- **D 日（BO 当日）**：发信号 "**candidate breakout** at $X，quality_score=72（partial：未含 platform 验证）"。UI 浮窗高亮 platform 因子为"待观测（剩余 10 个交易日）"。
- **D+1 ... D+9**：daily_runner 重跑，BO 仍在，quality_score 微调（其他 causal 因子不变，platform 仍 unavailable）。可选：UI 显示"距 platform 验证还有 N 天"。
- **D+10**：daily_runner 重跑 → `evaluate_at` 落值 → `platform_post_bo = 0.85`（举例）→ scorer 把它从 1.0 替换为 1.20 → quality_score **从 72 跳到 86**，UI 显示"**confirmed breakout**, +platform"。
- **D+11 之后**：BO 已 confirmed，quality_score 稳定。

这是**两段信号**的产品语义，但实现上**没有特殊代码** — 只是因为入口一的 live = 每日 batch refresh，每天对最新 df 重跑同一份 `enrich_breakout + score_breakout`，自动产生这种"信号随时间增强"的效果。

### 4.2 mining label 隐含表达 vs 显式 lookforward 因子

`composite_pattern_architecture.md` §3.2 给的低成本路径："label 已经隐含奖励事后稳定形态"。这条仍然有效 — **大多数情况下 lookforward 因子都不需要写**，因为 mining 自然会挖出"这套 causal 因子组合的 label 高"。

**仅当**用户要求"路径稳定" 作为 hard constraint（不只是统计偏好）时，才需要显式 `platform_post_bo`，让模板的 trigger 条件而非 label 来约束它。

---

## 5. 与 Platform-as-Event 方案的关系

### 5.1 等价性矩阵

| 场景 | 入口一 + lookforward 因子 | Platform-as-Event（入口二） |
|---|---|---|
| **mining** | 每个 BO 一行,带 `platform_post_bo`(可空)。Trial 模板可包含或不含此因子 | 每个 platform 一行（统计单位变更）；BO 退化为 platform 的"前置触发"元数据 |
| **dev** | 拖时间轴,所有 BO 都可见,platform 因子按 right_edge 状态而 None/有值 | 必须等 platform 形成才有 row,BO 单独可见性丢失（除非保留双 entity 流） |
| **live** | candidate signal 在 BO 当日发,K 天后 refresh 为 confirmed | 信号在 platform 形成时（BO 后第 K 天）才发,**主动延迟 K 天** |
| **产出粒度** | 每个 BO 都有 score | 只有形成 platform 的 BO 才有 row |

**结论**：**两个方案在 K 天后的 confirmed signal 上等价**，差别在：

1. **K 天内的可见性**：入口一保留 candidate；Platform-as-Event 完全沉默
2. **统计单位**：入口一仍是 BO；Platform-as-Event 把 BO 退化为前置元数据
3. **mining 流水线**：入口一不动；Platform-as-Event 要新建 PlatformDetector + 整套因子注册表 + Optuna trial

### 5.2 优选入口一 + lookforward 因子的理由

- **侵入性小**：仅扩 3 字段（`TemporalFactorInfo` + `Breakout.platform_post_bo`）+ enrich 路由（详见 `cind_compute_layer_design.md` §4，约 15-20 行）
- **保留 candidate 可见性**：BO 当日有 partial score，业务上"先看到再确认"的两段语义保留
- **mining 现状不动**：不必新建 PlatformDetector / 不必把 BO 降为子事件 / Optuna 流水线零改动
- **K 是因子本地参数，不污染主干**：每个 lookforward 因子可以有不同 K（platform_3w 与 step_2w 可共存）；Platform-as-Event 强制全局选定一个 K

**仅当**业务决定"BO 不再是唯一主事件、Platform 才是真正的交易锚"（产品决策、非技术演化）时，才升级到 Platform-as-Event。

---

## 6. 一句话总结

**入口一的"BO 当日评分"不变量在加入 lookforward 因子后依然成立** — 其中"评分"的语义从"一次性写入"扩展为"随 df 右边界推进而 refresh"，承载工具是 `Optional` 字段 + `FactorDetail.unavailable=True` 三态，与现有 `nullable=True` 因子完全一致；物理时延作为 `lookforward_bars` 显式声明，三场景共享同一份 `evaluate_at(df, idx)`，差别仅在 df 右边界。在产出等价的前提下，本方案对 Platform-as-Event 的优势是侵入性小、保留 candidate 可见性、mining 流水线零改动。
