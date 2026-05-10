# 入口一覆盖测试 — 7 特征复合形态的可表达性

> 研究单位:cind-edge-cases agent team(higher-event-modeler / non-causal-factor-modeler / team-lead)
> 完成日期:2026-05-10
> 引用底稿:[`_team_drafts5/higher_event_on_entrance1.md`](_team_drafts5/higher_event_on_entrance1.md)、[`_team_drafts5/non_causal_factor_on_entrance1.md`](_team_drafts5/non_causal_factor_on_entrance1.md)
> 关联文档:[`cind_compute_layer_design.md`](cind_compute_layer_design.md)(本文是其覆盖测试)

---

## 0. 摘要

**用户的两个挑战**:用一个具体的 7 特征复合形态测试入口一架构的边界 —
1. **高层事件**:"BO 簇" 是比 BO 更高一层的事件,簇内 BO 是被审视者。入口一(BO 仍是评估单位)能否容纳?
2. **非因果因子**:特征 7"BO 之后稳定到平台"是 post-BO 的非因果信息。入口一能否支持 BO 拥有这种 lookforward 因子?

**团队结论**(一句话):

> **能,7 个特征全部闭合**,但要承认两件事:
>
> (a) **特征 4(簇累计破 pk 数)需要跨层协作** — EventChain 出簇 id,因子层用 detector 引用做 `broken_peaks` reduce。这不是新破绽,正是 [cind_compute_layer_design.md §1.2](cind_compute_layer_design.md) 早就承认的"两个范畴各管各的边界"。
>
> (b) **特征 7(post-BO 平台)走 lookforward 因子 + `unavailable=True` 三态** — BO 当日发 candidate signal,K 天后 daily_runner 重跑自动 refresh 为 confirmed signal。这与现有 `nullable=True` 因子(volume / pbm / pk_mom)契约**完全一致**,框架不需要新概念。
>
> 与入口二的 Platform-as-Event 方案在 K 天后 confirmed signal 上**等价**,但入口一在 K 天内保留 candidate 可见性、mining 流水线零改动、侵入性显著更小 — 应作为首选。

---

## 1. 用户的 7 特征形态

```
1. 企稳(BO 之前股价稳定)
2. 连续突破(短期内多个 BO 聚集成簇)
3. 簇内第一个 BO 的 drought 较大(此前长期无 BO,"开闸"特征)
4. 簇累计突破 ≥ N 个 pk(累积"啃完阻力"程度)
5. 放量(可能发生在簇内任一 BO)
6. 最后一个 BO 之前股价未超涨(整体未拉升过快)
7. 最后一个 BO 之后稳定到平台(post-BO 非因果)
```

**用户的 framing**:"连续突破的判断是比 BO 更高一层的事件,BO 成为被审视者"。

**入口一的工程视角**(higher-event-modeler 给出的诚实判断):
- 评估单位仍然是 BO(每个 BO 一行)
- "簇属性"以 EventChain 计算 → 广播投影到簇内每个 BO 作为因子
- 这两个描述**在数学上等价**,但**产品语义不等价** — 如果未来需要 mining"簇级 PnL""簇级 hit rate"以簇为统计单位,入口一开始绷紧;**当前需求是"用簇属性挑出更优的 BO 入场点",评估单位仍是 BO,入口一够用**

---

## 2. 特征 1-6 的具体表达(高层事件 → BO 因子)

### 2.1 簇 id 识别(共享 EventChain)

```python
def assign_cluster_id(is_bo: pd.Series, K: int = 7) -> pd.Series:
    """簇定义:相邻 BO 间隔 ≤ K 天属同簇。
    返回:BO 当根 → 簇 id;非 BO 根 → NaN。"""
    bo_idx = np.flatnonzero(is_bo.values)
    if len(bo_idx) == 0:
        return pd.Series(np.nan, index=is_bo.index)
    gaps = np.diff(bo_idx)
    new_cluster = np.r_[0, (gaps > K).astype(int)]
    cluster_id_at_bo = new_cluster.cumsum()
    out = pd.Series(np.nan, index=is_bo.index)
    out.iloc[bo_idx] = cluster_id_at_bo
    return out
```

封装为 `ClusterChain(deps=[bo_chain], K=7)`,作为下游所有簇属性因子的依赖。

### 2.2 投影选择 — 选项 A(广播到簇内所有 BO)

higher-event-modeler 直接判定选 A,理由:
- 簇属性对**簇内任意 BO 都成立**,是"环境属性"非"终点属性"
- 选项 B(只投到最后一个 BO)依赖未来信息(后面是否还有 BO 不可知 → 违反 causality)
- 调试视角:每个 BO row 直接看 cluster_id / cluster_size 一目了然,不用回溯

### 2.3 6 个特征的具体路径

| 特征 | 路径 | 实现 | 闭合度 |
|---|---|---|---|
| **1 企稳** | 标量因子(原生) | `_calculate_pre_bo_stability(df, idx, window=20, max_dev=0.03)` — 与簇无关,直接走 `_calculate_*` | ✅ 完全闭合 |
| **2 簇内 BO 数** | EventChain → Adapter | `cluster_id.groupby(cluster_id).transform('size').where(is_bo)` | ✅ 完全闭合 |
| **3 簇首 drought** | EventChain → Adapter | `drought_at_bo.where(is_bo).groupby(cluster_id).transform('first')` | ✅ 完全闭合 |
| **4 簇累计破 pk 数** | **跨层** | EventChain 出簇 id + 因子层 reduce `broken_peaks` | ⚠️ 跨层,诚实分工 |
| **5 簇内放量** | EventChain → Adapter | `vol_spike.where(is_bo).groupby(cluster_id).transform('any')` | ✅ 完全闭合 |
| **6 簇前未超涨** | EventChain → Adapter | 簇首 BO 之前 M 天累计涨幅 < 阈值;用 `transform('first')` 拿簇首位置 | ✅ 完全闭合 |

### 2.4 特征 4 的跨层方案(入口一的诚实代价)

`broken_peaks` 是 `BreakoutInfo` 的成员(见 [breakout_detector.py:57](../../BreakoutStrategy/analysis/breakout_detector.py#L57)),**不是 t-indexed series**,EventChain 拿不到。

诚实方案:**EventChain 只输出簇 id,因子层做 broken_peaks 累计**:

```python
def _calculate_cluster_pk_total(self, breakout_info, idx, detector, cluster_id_series):
    """走 _calculate_* 路径,但参数包含 cluster_id_series + detector 引用。
    遍历当前簇内所有 BO,sum(b.broken_peaks 长度)。"""
    cur_cid = cluster_id_series.iloc[idx]
    if pd.isna(cur_cid):
        return None
    total = 0
    for b in detector.iter_breakouts_in_cluster(cur_cid, cluster_id_series):
        total += len(b.broken_peaks)
    return total
```

**不要做的事**:
- 不要把 `broken_peaks` 灌进 EventChain — 会污染"t-indexed series"的范畴边界
- 不要把"簇 row"作为新数据结构引入 — 那是入口二的工作

**要做的事**:
- 给 `BreakoutDetector` 增加辅助方法 `iter_breakouts_in_cluster(cluster_id, series)`
- 在 `FeatureCalculator` 开辟"cluster-aware 标量因子"分组(参数包含 `cluster_id_series`)

**这是入口一架构的设计前提**:因子是"BO-anchored scalar"范畴,EventChain 是"t-indexed series"范畴,**它们是两个范畴**。特征 4 涉及"簇语义 × BO 元数据"的交叉,跨层 join 是更自然的方向 — 因子层本来就持有 detector 引用 + BO 历史。

### 2.5 关键 framing 澄清

用户:"BO 簇是更高层事件,BO 是被审视者"
入口一工程:"EventChain 识别簇 → 簇属性 broadcast 到 BO 因子"

**两者数学等价,产品语义不等价**:
- 当前需求(用簇属性挑更优 BO 入场点) → 入口一够用
- 未来需求(以簇为评估单位 mining) → 必须升级到入口二

---

## 3. 特征 7 的具体表达(非因果因子)

### 3.1 `TemporalFactorInfo` 字段扩展

```python
@dataclass(frozen=True)
class TemporalFactorInfo(FactorInfo):
    chain: 'EventChain'
    causality: Literal['causal', 'lookforward'] = 'causal'
    lookforward_bars: int = 0  # K
```

### 3.2 `evaluate_at` 在 lookforward 因子上的行为

```python
def evaluate_at(self, df, idx, mode):
    series = self.evaluate_batch(df)
    if self.causality == 'causal':
        v = series.iloc[idx]
        return None if pd.isna(v) else float(v)

    # lookforward
    bars_after = len(df) - 1 - idx
    if bars_after < self.lookforward_bars:
        return None  # → unavailable=True,scorer multiplier=1.0
    v = series.iloc[idx + self.lookforward_bars]
    return None if pd.isna(v) else float(v)
```

**关键不变量**:三场景(mining / dev / live)**共享同一份代码、同一份 df**,差别只是 idx 和 df 的右边界。`mode` 参数仅用于未来扩展(例如 mining 对 incomplete 样本告警),当前不影响返回值。

### 3.3 BO 当日评分这个不变量是否被破坏

**严格说法**:**不变量没有被破坏,但需要重新阐述** —— BO 当日**仍然评分**,只是该 BO 的 quality_score 在**当日是 partial、K 天后 refresh 为 complete**。

**这正是 `Breakout` dataclass 已有的 `Optional[float]` + `FactorDetail.unavailable=True` 三态机制的自然延展**:
- `volume / pbm / pk_mom` 等因子在 lookback 不足时已经 `nullable=True`、`multiplier=1.0`
- lookforward 因子在 K 天前 unavailable 状态**与 lookback 不足时一模一样**,框架不需要新增三态

### 3.4 mining / dev / live 三场景统一行为

| 场景 | df 右边界 | 对 idx=`bo_idx` 的 BO | `platform_post_bo` 值 | 备注 |
|---|---|---|---|---|
| **mining**(历史回测) | 历史末日 | `evaluate_at(df, bo_idx, 'training')` | 总能算出 → float | 与 label 一致:mining 默认要求 `bars_after >= K`,否则 BO 不进 trial |
| **dev**(拖时间轴) | 用户指定的 right_edge | `evaluate_at(df, bo_idx, 'training')` | bars_after≥K → float;否则 → None | UI 应显示"待观测 K 天"而非空白 |
| **live**(每日 batch refresh) | today | 最新 BO 的 `bo_idx ≈ len(df)-1` | None(unavailable) | K 天后下一次 daily run 自动 refresh |

**统一行为**:三场景共享同一份 `evaluate_at`,`unavailable=True` 不分 mode。差异**只在 df 的右边界**。

### 3.5 Live 端的"诚实产品语义"

对于 K=10 的 `platform_post_bo`:

- **D 日(BO 当日)**:发信号 "**candidate breakout** at $X,quality_score=72(partial:未含 platform 验证)"
- **D+1 ... D+9**:daily_runner 重跑,quality_score 微调(其他 causal 因子不变,platform 仍 unavailable)
- **D+10**:`evaluate_at` 落值 → `platform_post_bo = 0.85` → scorer 把 multiplier 从 1.0 替换为 1.20 → quality_score **从 72 跳到 86** → "**confirmed breakout**, +platform"

这是**两段信号**的产品语义,但**实现上没有特殊代码** — 只是因为 `daily_runner` 每天对最新 df 重跑同一份 `enrich_breakout + score_breakout`,自动产生这种"信号随时间增强"的效果。

### 3.6 物理时延的承认

**用户给的理解完全正确**:lookforward 因子在入口一里**不是逃避物理时延,而是承认它 + 把它做成显式三态**。任何架构(入口一 / 入口二 / MATCH_RECOGNIZE)都满足同一物理事实 — **第 K 根 bar 不存在时,post-BO 信息就是不存在**。

---

## 4. 入口一 vs Platform-as-Event 的等价性矩阵

| 场景 | 入口一 + lookforward 因子 | Platform-as-Event(入口二) |
|---|---|---|
| **mining** | 每个 BO 一行,带 `platform_post_bo`(可空)。Trial 模板可包含或不含此因子 | 每个 platform 一行(统计单位变更);BO 退化为前置元数据 |
| **dev** | 拖时间轴,所有 BO 都可见,platform 因子按 right_edge 状态 None/有值 | 必须等 platform 形成才有 row,BO 单独可见性丢失 |
| **live** | candidate signal 在 BO 当日发,K 天后 refresh 为 confirmed | 信号在 platform 形成时(BO 后第 K 天)才发,**主动延迟 K 天** |
| **产出粒度** | 每个 BO 都有 score | 只有形成 platform 的 BO 才有 row |

**结论**:**两个方案在 K 天后的 confirmed signal 上等价**,差别在:

1. **K 天内的可见性**:入口一保留 candidate;Platform-as-Event 完全沉默
2. **统计单位**:入口一仍是 BO;Platform-as-Event 把 BO 退化为前置元数据
3. **mining 流水线**:入口一不动;Platform-as-Event 要新建 PlatformDetector + 整套因子注册表 + Optuna trial

**优选入口一 + lookforward 因子**:
- 侵入性小(扩 3 字段 + enrich 路由 ~15-20 行)
- 保留 candidate 可见性
- mining 现状不动
- K 是因子本地参数,不污染主干(`platform_3w` 与 `step_2w` 可共存,各自不同 K)

**仅当**业务决定"BO 不再是唯一主事件、Platform 才是真正的交易锚"(产品决策、非技术演化)时,才升级到 Platform-as-Event。

---

## 5. 完整 7 特征的入口一表达汇总

| 特征 | 路径 | 因子类型 | 闭合度 |
|---|---|---|---|
| 1 企稳 | 标量因子(原生) | `pre_bo_stability` | ✅ 完全闭合 |
| 2 簇内 BO 数 | EventChain → Adapter | `cluster_size` (causal) | ✅ 完全闭合 |
| 3 簇首 drought | EventChain → Adapter | `cluster_first_drought` (causal) | ✅ 完全闭合 |
| 4 簇累计破 pk 数 | **跨层**(EventChain 出簇 id + 因子层 reduce broken_peaks) | `cluster_pk_total` (cluster-aware 标量) | ⚠️ 跨层,诚实分工 |
| 5 簇内放量 | EventChain → Adapter | `vol_burst_in_cluster` (causal) | ✅ 完全闭合 |
| 6 簇前未超涨 | EventChain → Adapter | `pre_cluster_overshoot` (causal) | ✅ 完全闭合 |
| 7 BO 后平台 | EventChain → Adapter,**lookforward** | `platform_post_bo` (lookforward, K=10) | ✅ 通过 unavailable 三态 |

**7/7 全部闭合**。其中:
- 6 个 causal 因子在 BO 当日全部可计算
- 1 个 lookforward 因子在 K 天前 unavailable=True、K 天后 daily_runner 自动 refresh
- 1 个跨层因子(特征 4)在 EventChain + 因子层协作下闭合

---

## 6. 用户两个挑战的最终答复

### Q1:入口一(BO 仍是评估单位)能否容纳"高层事件"(BO 簇)?

**能。** "簇是更高层事件"的 framing 在工程上落地为"EventChain 识别簇 → 簇属性广播到簇内每个 BO 作为因子"。BO 仍然是评估单位,只是因子来源变成了"以簇为视角的统计量"。

**唯一的诚实代价**:特征 4(簇累计破 pk 数)需要跨层 — EventChain 出簇 id,因子层用 detector 引用做 `broken_peaks` reduce。这不是新破绽,而是 [cind_compute_layer_design.md §1.2](cind_compute_layer_design.md) 早就承认的"两个范畴"的体现。

**真正升级到入口二的触发条件**:业务上要求以簇为统计单位(簇级 PnL / hit rate)。当前需求(用簇属性挑更优 BO 入场点)不触发。

### Q2:入口一能否支持 BO 拥有非因果(lookforward)因子?

**能。** 通过 `TemporalFactorInfo.causality='lookforward'` + `lookforward_bars=K` 类型级声明,`evaluate_at` 在 K 天前返回 None(`unavailable=True`),K 天后返回 float。

**不变量没破坏**,只是评分语义从"一次性写入"扩展为"随 df 右边界推进而 refresh"。**承载工具是现有 `Optional` 字段 + `FactorDetail.unavailable=True` 三态**,与 `volume / pbm / pk_mom` 等 lookback 不足时的契约**完全一致**。

**Live 端的 candidate→confirmed 两段信号是 daily_runner 重跑的副产物**,不需要特殊代码。

---

## 7. 引用与延伸阅读

### 团队底稿
- [`_team_drafts5/higher_event_on_entrance1.md`](_team_drafts5/higher_event_on_entrance1.md) — higher-event-modeler(簇识别 + 6 特征伪代码 + 跨层方案)
- [`_team_drafts5/non_causal_factor_on_entrance1.md`](_team_drafts5/non_causal_factor_on_entrance1.md) — non-causal-factor-modeler(lookforward 设计 + 三场景统一 + 与 Platform-as-Event 等价性)

### 关联研究
- [`cind_compute_layer_design.md`](cind_compute_layer_design.md) — 入口一最终架构(本文是其覆盖测试)
- [`cind_chain_mechanism_revisited.md`](cind_chain_mechanism_revisited.md) — EventChain 整体设计 + `causality` 字段定义
- [`composite_pattern_architecture.md`](composite_pattern_architecture.md) §3.1 — 物理时延约束

### 关键代码
- [`BreakoutStrategy/factor_registry.py`](../../BreakoutStrategy/factor_registry.py) — `FactorInfo` 当前字段
- [`BreakoutStrategy/analysis/features.py`](../../BreakoutStrategy/analysis/features.py) — `_calculate_*` + `Breakout` dataclass
- [`BreakoutStrategy/analysis/breakout_scorer.py:194-198`](../../BreakoutStrategy/analysis/breakout_scorer.py#L194-L198) — `unavailable=True` + `multiplier=1.0` 处理
- [`BreakoutStrategy/analysis/breakout_detector.py:57`](../../BreakoutStrategy/analysis/breakout_detector.py#L57) — `BreakoutInfo.broken_peaks`
- [`BreakoutStrategy/live/pipeline/daily_runner.py`](../../BreakoutStrategy/live/pipeline/daily_runner.py) — 每日 batch refresh

---

**报告结束。**
