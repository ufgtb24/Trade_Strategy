# 计算层架构 — 入口选择 + 接口设计

> 研究单位:cind-compute-arch agent team(structure-comparator / compute-interface-architect / team-lead)
> 完成日期:2026-05-10
> 引用底稿:[`_team_drafts4/structure_comparison.md`](_team_drafts4/structure_comparison.md)、[`_team_drafts4/compute_interface_design.md`](_team_drafts4/compute_interface_design.md)
> 关联文档:[`cind_chain_mechanism_revisited.md`](cind_chain_mechanism_revisited.md)(本文细化其计算层落地)
> **范围**:**搁置挖矿议题**(Optuna / bit-packed AND / OOS),只聚焦"能否正确算出结果"
>
> **⚠️ 方法论修正通知(2026-05-10 后续研究)**:本文推荐路径一(BO 主干 + EventChain 作因子)是在**考虑改造成本**前提下的工程性价比推荐。剥离改造成本、纯第一性原理评估见 [`path1_vs_path2_pure_firstprinciples.md`](path1_vs_path2_pure_firstprinciples.md)(cind-pure-firstprinciples team) — 那份研究的结论是**多级事件框架(L1 BO + L2 簇 + L3 平台)更胜一筹**。本文的"路径一是最简形态"在加上"考虑改造成本"约束后才成立;两份研究**都正确,但前提不同**。最终架构决策应在了解两个视角后做出。

---

## 0. 摘要

**用户两个问题**:

> Q1:入口一(EventChain 作因子,BO 框架是主干)vs 入口二(BO 下沉为 EventChain 原子事件,EventChain 是主干)— 哪个更好?
>
> Q2:因子计算(`FeatureCalculator._calculate_*`)与 EventChain 计算(`evaluate_batch`)— 是否应统一接口?

**团队结论**(一句话):

> **入口一为主干,EventChain 通过单向 Adapter 接入因子注册表**;**两套计算接口并存,不强行统一** — 因子是"BO-anchored scalar"范畴,EventChain 是"t-indexed series"范畴,**它们是两个范畴**,不是同一范畴的特例。强行统一(把因子升格为 series)会让 9 个核心因子的算力膨胀 200-500 倍,且 `pk_mom` / `dd_recov` 这类"双锚点动态段切片"找不到等价表达。

---

## 1. 入口选择(Q1)— 入口一为主干,但保留入口二作为子集

### 1.1 三个扩展例子的对比

| 例子 | 入口一(BO 主干) | 入口二(EventChain 主干) | 谁更省 |
|------|---|---|---|
| **MA 平稳因子** | EventChain 输出 series → `iloc[bo_idx]` → 标量。`BreakoutDetector`、`FeatureCalculator` 不动,新增 1 个 `FactorInfo` 条目 | EventChain 输出 series,但要"投影回 bo_idx",**等于走入口一** | **入口一** |
| **Platform 作新事件源** | 不可表达 — 必须开第二条独立 detector 流水线,与 BO 流不通信,无法表达"Platform 之后某天 BO" | `PlatformDetector` 与 `BreakoutDetector` 平级,事件 schema 统一可交叉 | **入口二** |
| **三级派生**("BO 之后 Platform 形成 → Step 二次确认") | 破产 — `Breakout` dataclass 字段全是标量,没有"未来事件占位符"。三 detector 平行无法表达事件次序 | `chain_l3 = step.after(platform.after(bo, exp=20), exp=10)`,在已有抽象内闭合 | **入口二** |

**两胜一负**给入口二,**但入口二的胜利建立在"已经付了 EventDetector 抽象代价"的前提上** — 把 `BreakoutDetector` 退役为子类、新增 `EventDetector` 抽象、改 `daily_runner.py` 调度心智、产出 schema 级变更。这是结构级改造。

### 1.2 真子集关系(双向不对称)

读完 `BreakoutStrategy/analysis/features.py` 和 `breakout_detector.py` 后的结构性事实:

| 维度 | 子集关系 |
|------|---|
| **事件流编排** | **入口一 ⊂ 入口二**(入口一是入口二的"BO 唯一事件源"特例)|
| **事件级特征工程** | **入口二 ⊄ 入口一**(入口二缺乏 BO 锚点 + `broken_peaks` 元数据,无法表达 9 个家族 B/C/D 因子)|

**入口二无法表达的 3 类**:

1. **BO 锚点的双锚段切片**:`pk_mom`([features.py:471](../../BreakoutStrategy/analysis/features.py#L471))窗口是 `[peak_idx, breakout_idx]`,**peak_idx 数据驱动**。每个 t 都要 ad-hoc 找"距 t 最近的 broken peak",相当于在每个 t 把 detector 跑一遍 — 语义闭环混乱
2. **BO 锚点的可变窗口 reduce**:`dd_recov`([features.py:802](../../BreakoutStrategy/analysis/features.py#L802))用 `np.argmax(highs)` 找窗口内极值位置 → 从该位置开始切第二段。t-relative rolling 表达不出"动态找极值位置 → 二段切片"
3. **事件级元数据特征**:`age / test / peak_vol / height` 4 个因子从 `broken_peaks` 列表 reduce 出来,依赖 `BreakoutInfo.broken_peaks` 这个 BO-specific 数据结构,完全在 EventChain 抽象之外

**结论**:**不存在单向真子集,二者各有不可替代的范畴**。

### 1.3 入口二的"主干换人"是真换还是包装?

**不是真换**。`BreakoutDetector.evaluate_batch` 内部仍依赖现有增量峰值检测(`active_peaks` / `_check_breakouts`,见 [breakout_detector.py:560](../../BreakoutStrategy/analysis/breakout_detector.py#L560))。BO 框架(峰值维护 + 突破判定)只是被**包装**成 `EventDetector` 接口,核心算法没动。

所以入口二的更准确描述不是"BO 框架被纳入 EventChain",而是"BO 框架与其他形态检测器**共用 EventDetector 抽象**,EventChain 是这些检测器之上的组合层"。

反过来,入口一里的 BO 也不是真主干 — `enrich_breakout` 已经开始通过 `vol_ratio_series` / `atr_series` 这种"预计算 series → bo_idx 取值"模式消费 t-indexed 表达([features.py:217-228](../../BreakoutStrategy/analysis/features.py#L217-L228))。**这正是 EventChain 形态的雏形**。

**真实情况**:**两种入口在 EventChain 作为计算原语的层面是统一的**;差异只在"事件锚点的归属"。

### 1.4 计算层结构的最终判定

**入口一为主干 + 入口二的能力作为子集嵌入**:

- 主干:BO 框架(`BreakoutDetector` + `FeatureCalculator` + `FACTOR_REGISTRY`)保留不动
- EventChain 通过**单向 Adapter** 接入因子注册表,产生入口一的"链式因子"
- **多事件流编排能力**(入口二的核心价值)以 `EventChain.after(prev, exp)` **算子**形式表达,作为入口一的扩展,**不需要新主干**
- 仅当业务决定"BO 不再是唯一主事件"(产品决策,非技术演化)时,才考虑切换到入口二真正的"EventDetector 抽象 + 多 detector 平级"形态

---

## 2. 计算接口(Q2)— 不统一,两套接口 + 单向 Adapter

### 2.1 现有因子计算的 5 个家族(实证读 `features.py` 后)

| 家族 | 例子 | 内部形态 | 能否 series 化? |
|---|---|---|---|
| **A. 单点取数** | `_classify_type`、`_calculate_age` | 直接读 bo_idx 的 row 或 broken_peaks 元数据 | 不需要 — 本身就是单点 |
| **B. BO 之前一段窗口 reduce**(主力)| `_calculate_volume_ratio`、`_calculate_pre_vol`、`_calculate_pbm`、`_calculate_dd_recov` | 切片 `df.iloc[idx-N:idx]` 做 mean/max/sum/argmax,**N 各因子不同** | 部分能(`volume`、`pbm`)— 但要给每个 N 写一份 t-indexed rolling;部分不能(`dd_recov` 的二段切片) |
| **C. 双锚点段切片** | `_calculate_pk_momentum` | 段长度由 `peak_idx` 与 `breakout_idx` 数据驱动 | **不能** — peak_idx 是 detector 输出,t-indexed 不存在 |
| **D. 显式波动率累计** | `_calculate_annual_volatility` | 252 日 std | 能,但已经是 stable 中间变量,无需重做 |
| **E. 已 vectorized 共享中间变量** | `precompute_vol_ratio_series`、`atr_series` | `rolling().mean().shift(1)` → 下游 `iloc[bo_idx]` | **已经是 series-then-pick 形态** |

**关键观察**:家族 B 是大头(`volume`/`pre_vol`/`pbm`/`dd_recov`/`pk_mom`/`ma_pos`/`ma_curve`/`day_str`/`overshoot` 共 9 个),它们的窗口左端点是 `idx - N`,**N 各因子不同,语义不同**。**不存在一个统一的 series 让所有因子去取 iloc** — 因为每个因子是不同的 series。

### 2.2 强行统一(方案 A:全部升级为 series)的代价

**直接驳回**。三条致命缺陷:

1. **算力膨胀 200-500 倍**:典型 252 bar/年 vs 几个 BO/年。家族 B、C、D 改 series 后扫描器从"BO 级 enrich"变成"全 bar 级因子表",10 年扫描算力翻 200-500x
2. **`pk_mom` 无法 series 化**:peak_idx 是数据驱动,每个 t 都要重跑 detector — 语义闭环混乱
3. **接口污染**:`FactorDetail` / `ScoreBreakdown` / `Breakout` dataclass 全是标量字段。改 series 后还要再附加"pick at bo_idx"层,等于把单向 Adapter 反过来做一遍

**驳回根基**:把"BO-anchored scalar"硬塞进"t-indexed series"是用错抽象。**因子的本质是"事件级特征",不是"指标时间序列"**。

### 2.3 推荐方案 — 两套接口并存 + 单向 Adapter

```python
# === 因子接口(不动)===
class FeatureCalculator:
    def _calculate_<name>(self, df, idx, ...) -> Optional[float]:
        """BO-anchored scalar.调用方负责传入预计算的共享 series。"""

# === EventChain(新增,单一 batch 模式)===
class EventChain:
    name: str
    deps: list['EventChain']
    addminperiod: int = 0
    causality: Literal['causal'] = 'causal'

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """递归 evaluate deps,然后合成。LRU 缓存基于 id(df)。"""
        ...

# === 单向 Adapter:EventChain → 因子接口 ===
def factor_from_chain(
    chain: EventChain, *, nullable: bool = True,
) -> Callable[[pd.DataFrame, int], Optional[float]]:
    def _calc(df, idx):
        val = chain.evaluate_batch(df).iloc[idx]
        if pd.isna(val):
            return None if nullable else 0.0
        return float(val)
    return _calc
```

**FACTOR_REGISTRY 接入**:

```python
# 现有(不动):_calculate_pbm 直接挂 FactorInfo('pbm', ...)
# 新增:某个链式因子
plateau_chain = EventChain(name='plateau_3w', deps=[ma_smooth_chain], ...)
FACTOR_REGISTRY.append(
    TemporalFactorInfo('plateau', factor_from_chain(plateau_chain), ...)
)
```

### 2.4 为什么单向?反向 Adapter 不提供

**因子 → series 的反向 Adapter 没有正确语义**。

- 因子接口期望"事件锚点已知"(`bo_info`)
- 把它强行升格为 series 需要"对每个 t 都假装 bo_idx=t",但因子内部用的是 `broken_peaks` / `peak_idx` 这些 BO-specific 元数据,**离开 BO 上下文就没意义**

单向 Adapter 是**方向性正确**,不是设计缺陷。

### 2.5 状态管理

| 计算单元 | Stateless? | 缓存策略 |
|---|---|---|
| 因子 `_calculate_*` | 是 | BO 级共享 series(`atr_series` / `vol_ratio_series`)通过参数传入,无内部缓存 |
| EventChain | 否(deps 重用)| `id(df)` 做 LRU 缓存,scope 为单次 `enrich_breakout`,换 symbol 自动失效 |

不需要全局 cache infra。

---

## 3. 综合架构 — 计算层四层视图

```
┌──────────────────────────────────────────────────────────┐
│ 消费层(scorer / live UI / mining)                        │
│   消费 Breakout dataclass 的标量字段                      │
└──────────────────────────────────────────────────────────┘
                       ↑ Breakout(13+ 标量因子)
┌──────────────────────────────────────────────────────────┐
│ 因子层(FACTOR_REGISTRY + FeatureCalculator)             │
│                                                            │
│   两类条目:                                               │
│   - 标量因子(现有 13 个,_calculate_* 形态)             │
│   - 链式因子(TemporalFactorInfo,通过 factor_from_chain)│
│                                                            │
│   接口契约:(df, bo_idx) → Optional[float]               │
└──────────────────────────────────────────────────────────┘
                       ↑ 单向 Adapter
┌──────────────────────────────────────────────────────────┐
│ EventChain 计算层(新增)                                 │
│                                                            │
│   - 原子 chain:`ma_smooth`、`vol_burst`、`is_bo`         │
│   - 复合算子:`.and_()`、`.or_()`、`.after(prev, exp)`    │
│   - 持续/过期:`expires_within`、`state_persistent`       │
│                                                            │
│   接口契约:df → pd.Series                                 │
│   状态:deps 缓存(id(df) LRU)                            │
└──────────────────────────────────────────────────────────┘
                       ↑ 数据
┌──────────────────────────────────────────────────────────┐
│ DataFrame 层(原始 K 线 + 预计算共享 series)             │
│   close / open / high / low / volume / atr / vol_ratio   │
└──────────────────────────────────────────────────────────┘
```

### 各层的 owner

- **因子层**:已存在,主干。EventChain 链式因子作为新成员加入,但**不取代** `_calculate_*` 标量因子
- **EventChain 层**:新增,与因子层平级**作为可选的因子来源**
- **DataFrame 层**:不动

### 入口二的能力如何表达?

入口二的真正价值是"事件流编排"。在四层架构下,这个能力以 **EventChain 算子**形式存在:

```python
# 三级派生:BO → Platform → Step
bo_chain = EventChain.from_detector(BreakoutDetector(...))   # is_bo 时序
plateau = plateau_chain.after(bo_chain, exp=20)              # BO 后 20 天内 plateau
step = step_chain.after(plateau, exp=10)                     # plateau 后 10 天内 step

# 把 step 作为 BO 的因子(入口一消费)
FACTOR_REGISTRY.append(
    TemporalFactorInfo('post_bo_step_confirmed', factor_from_chain(step), ...)
)
```

**多级派生在 EventChain 算子内闭合,无需新增主干**。当且仅当业务决定"事件 row 不再以 BO 为锚"(产品决策),才需要把入口二做成真正的多 detector 主干。

---

## 4. 落地形态 — 最小可行 API

```python
# === 模块 1:event_chain.py(新增)===
class EventChain:
    name: str
    deps: list['EventChain'] = field(default_factory=list)
    addminperiod: int = 0
    causality: Literal['causal'] = 'causal'

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series: ...

    # 复合算子
    def and_(self, other: 'EventChain') -> 'EventChain': ...
    def or_(self, other: 'EventChain') -> 'EventChain': ...
    def after(self, prev: 'EventChain', exp: int) -> 'EventChain':
        """prev 在过去 exp 根内发生过 → 当前 self 触发"""
        ...

    # 持续/过期原语
    def expires_within(self, exp: int) -> 'EventChain': ...
    def state_persistent(self, n: int, mode='all'|'ratio'|'consecutive', threshold=1.0): ...

# === 模块 2:event_chain_factor.py(新增)===
def factor_from_chain(chain, *, nullable=True) -> Callable: ...

# === 模块 3:factor_registry.py(append 新条目类型)===
@dataclass(frozen=True)
class TemporalFactorInfo(FactorInfo):
    chain: EventChain  # 直接引用 chain 实例,enrich_breakout 自动 adapter

# === 模块 4:features.py(enrich_breakout 加路由)===
def enrich_breakout(self, breakout: Breakout, df: pd.DataFrame, ...):
    for fi in active_factors:
        if isinstance(fi, TemporalFactorInfo):
            value = factor_from_chain(fi.chain)(df, breakout.idx)
        else:
            value = self._calculate_dispatch(fi.key, df, breakout.idx, ...)  # 现有路径
        setattr(breakout, fi.attr, value)
```

**侵入性**:`features.py:enrich_breakout` 加一个 isinstance 分支(约 5 行)+ `factor_registry.py` 加 `TemporalFactorInfo` 子类(约 10 行)+ 新增 `event_chain.py` 模块(估计 200-300 行,含算子和原语)。**`BreakoutDetector` / 现有 16 个 `_calculate_*` 完全不动**。

---

## 5. 与上一份研究的关系

[`cind_chain_mechanism_revisited.md`](cind_chain_mechanism_revisited.md) 在架构层给出了"四层工具集 + EventChain 第 2.5 层"的方向。本文细化:

| 上文方向 | 本文细化 |
|---|---|
| EventChain 第 2.5 层 | **作为因子来源**(入口一消费),通过单向 Adapter 接入 FACTOR_REGISTRY |
| Mining 流水线两个接入路径(因子标量 / 事件 row)| 计算层只需路径 A(因子标量);路径 B(事件 row)是入口二切换的产物,**当前不做** |
| `kind: event\|state` 显式 schema | 仍然有效,作为 EventChain 内部子语义 |
| `causality` 类型级强制声明 | 仍然有效,在 `TemporalFactorInfo` 上声明 |

**关键修订**(对上文 §6 Stage 2.3 的进一步明确):"PlatformDetector + EventDetector 抽象"这一阶段被进一步降低优先级 — 在入口一为主干的当前架构下,Platform 只需写成一个 `EventChain`,作为 BO 因子("BO 当根是否处于平台中"或"过去 N 日内是否出现 platform"),**不需要新写 detector**。

---

## 6. 一句话总结

> **入口一为主干,EventChain 作为新型因子来源接入因子注册表;两套计算接口(标量因子 + EventChain 时序)并存,通过单向 Adapter 桥接 — 这是用奥卡姆剃刀剃过的最简形态**。入口二的"多事件流编排"以 `EventChain.after()` 算子形式存在于入口一内部,作为子集而非取代;真正切换到入口二需要业务上放弃"BO 是唯一主事件"的产品决策。

---

## 7. 引用与延伸阅读

### 团队底稿
- [`_team_drafts4/structure_comparison.md`](_team_drafts4/structure_comparison.md) — structure-comparator(三个扩展例子 + 真子集分析 + 代码侵入性)
- [`_team_drafts4/compute_interface_design.md`](_team_drafts4/compute_interface_design.md) — compute-interface-architect(因子 5 家族实证 + 强行统一的代价 + 单向 Adapter 设计)

### 关键代码
- [`BreakoutStrategy/analysis/features.py`](../../BreakoutStrategy/analysis/features.py) — `FeatureCalculator` 全部 `_calculate_*` 方法
- [`BreakoutStrategy/factor_registry.py`](../../BreakoutStrategy/factor_registry.py) — 因子元数据
- [`BreakoutStrategy/analysis/breakout_detector.py`](../../BreakoutStrategy/analysis/breakout_detector.py) — BO 检测主干

### 上一团队研究
- [`cind_chain_mechanism_revisited.md`](cind_chain_mechanism_revisited.md) — 整体架构方向(本文细化其计算层落地)

---

**报告结束。**
