# 入口一 vs 入口二 — 计算层结构对比

> 范围:**纯计算层**(扩展性 / 灵活性 / 覆盖面 / 代码侵入性)。**不讨论挖矿、Optuna、bit-packed AND、OOS 验证。**只回答:对一段历史 K 线,两种入口能否正确算出结果(date, value),以及加新形态时谁更顺。

---

## 0. 决断(TL;DR)

**入口一(EventChain 作因子,BO 框架是主干)是当前应保留的主干;入口二(EventChain 是主干,BO 退化为原子事件)在计算层是入口一的真超集,但代价是把整个事件域抽象成一等公民,对现有代码的侵入是结构级的。**

- 在三类扩展例子中,**入口一**有 1 个例子需新增抽象(MA 平稳),**入口二**有 1 个例子需新增抽象(BO-as-event-source 的退役工作);第 3 个例子(三级派生)入口二闭合,入口一需要把"中间事件"伪装成因子。
- 同一条 EventChain `平台形成` 在两个入口下**都能被消费**,但**只有入口一是无损的**。入口二消费时丢失了"BO 锚点"这个标量上下文 — 现有 16 个 `_calculate_*` 因子里至少 7 个的窗口语义是 BO-anchored,无法被 EventChain 的 t-indexed series 表达。
- **真子集关系:入口一 ⊂ 入口二(在事件覆盖面上),但 入口二 ⊄ 入口一(在因子表达面上)。** 二者各有不可替代的范畴 — 入口一是事件级特征工程,入口二是事件流编排。
- **结论与搭档 compute-interface-architect 收口一致:采纳"入口一为主干,EventChain 通过单向 Adapter 接入因子注册表",入口二的能力作为子集嵌入,而不是反过来取代主干。**

---

## 1. 三个扩展例子,具体看

### 例 1:加"MA 平稳"判定(连续 N 日 MA20 斜率 < ε)

**入口一 (EventChain 作因子)**:

```python
# 新增 EventChain
ma_smooth_chain = EventChain(
    name='ma_smooth_20',
    addminperiod=22,
    compute=lambda df: (
        df['close'].rolling(20).mean().diff().abs()
        .rolling(N).max().lt(EPS)
    ),
)
# 单向 Adapter 注册成因子
FACTOR_REGISTRY.append(FactorInfo('ma_smooth', ...))
# enrich_breakout 路由:series.iloc[bo_idx] -> scalar bool
```

改动量:`factor_registry.py` 加 1 个 `FactorInfo` + 1 个 `EventChain` 实例 + 路由 1 行。**`BreakoutDetector` / `FeatureCalculator` 不动**,新形态完全在新增层闭合。

**入口二 (BO 下沉为事件)**:

```python
# 也是新增 EventChain,但下游消费者是 EventDispatcher
ma_smooth_chain = EventChain(name='ma_smooth_20', ...)
# 不进 FACTOR_REGISTRY;由 dispatcher 决定要不要把它的上升沿当事件 row
```

如果只是想要"BO 当日 MA 是否平稳"这个特征 — 入口二必须把它再"投影回 BO 锚点":等于在 EventChain 主干外再做一次 series.iloc[bo_idx],这正是入口一的形态。**入口二在这里反而绕路。**

**结论 1**:对单点取值类形态特征,入口一更顺。

### 例 2:加"Platform 形成"事件(N 日窗口 Hi/Lo 区间紧 + Vol 萎缩)

**入口一 (EventChain 作因子)**:

只能表达"BO 当日是否处于平台中"(`series.iloc[bo_idx]`),**不能表达"今天 Platform 刚形成"作为一个新事件源**。如果业务需要"Platform 形成日 → 触发某流程",入口一没有承载这种事件的位置 — `BreakoutDetector` 是封死的、专门检测 BO 的。

要表达,必须新写 `PlatformDetector`,然后在主干外维护第二条独立的事件流 — 但两条事件流互不通信,无法表达"Platform 形成 → 之后某天 BO"这种次序条件。

**入口二 (BO 下沉为事件)**:

```python
class EventDetector(Protocol):
    def evaluate_batch(self, df) -> pd.Series: ...   # bool series, True=该 bar 是事件

class PlatformDetector(EventDetector):
    def evaluate_batch(self, df):
        return platform_chain.evaluate_batch(df).diff().eq(1)  # 上升沿

class BreakoutDetector(EventDetector):
    def evaluate_batch(self, df):
        # 包装现有增量逻辑,产出 is_bo bool series
        ...
```

`PlatformDetector` 与 `BreakoutDetector` 平级,事件 row schema 统一,事件之间可以交叉(`platform_event ∧ later bo_event`)。**入口二在这里闭合,且没有重写 BO 检测逻辑(只是包了一层 batch 适配)。**

**结论 2**:对"以新形态作为新事件源"的扩展,入口二更顺。但代价是要**预先**抽象出 `EventDetector` 基类并把 `BreakoutDetector` 退役下来,这是结构级改造。

### 例 3:三级派生 — "BO 之后的 Platform 形成 → 之后的 Step 二次确认"

**入口一**:

破产。`Breakout` dataclass 的字段全是标量,没有"未来事件占位符"的位置。把 Platform 当因子可以(`bo_idx` 之后 N 日内是否出现 platform),但表达不了"Step 在 Platform **之后**" — 这需要一个**有序事件流**的概念,入口一没这个抽象。

要硬做,只能在 BO 之后再开一个独立 detector 跑 Platform,然后在 Platform 之后再开一个独立 detector 跑 Step,**三个事件流靠 idx 排序后再 join**,代码组织上是三条互不通信的流水线。

**入口二**:

```python
chain_l1 = bo_event_series  # is_bo
chain_l2 = platform_chain.after(chain_l1, exp=20)   # BO 后 20 日内的 Platform 上升沿
chain_l3 = step_chain.after(chain_l2, exp=10)       # 上述 Platform 后 10 日内的 Step
```

`.after(prev_event, exp)` 是天然的 EventChain 复合算子(本质是 `prev.expanding(within exp).any() & current.diff().eq(1)`)。三级派生在已有抽象内闭合,**这正是 Condition_Ind 的 R 算子(递归命名复用)的核心价值**(参见 `cind_chain_mechanism_revisited.md` §2.4)。

**结论 3**:多级派生事件场景,入口二决定性胜出。

### 三例小结

| 例子 | 入口一 | 入口二 | 谁更省代码 |
|---|---|---|---|
| 1. MA 平稳因子 | 1 个 FactorInfo + 1 个 EventChain | EventChain + 投影回 bo_idx(=入口一) | 入口一 |
| 2. Platform 作事件源 | 不可表达,需另起平行流 | 平级 EventDetector,闭合 | 入口二 |
| 3. 三级派生 | 不可表达 | `.after()` 算子直接闭合 | 入口二 |

**两胜一负**,但入口二的胜利建立在"已经付了 EventDetector 抽象代价"的前提上。

---

## 2. 灵活性 — 同一条 EventChain 双消费

考察 `平台形成` 这条 chain:

- **入口一消费**:`series.iloc[bo_idx]` → 标量 bool/float,作为 `Breakout.platform = ...` 字段。**无损**(单点取值,语义清晰)。
- **入口二消费**:`series.diff().eq(1)` → 上升沿 series → 产生 PlatformEvent row。**无损**(事件流原生)。

**这两种消费在两个入口下都成立,且 EventChain 的 batch 输出 `pd.Series` 是双方共同的最大公约数表达。**

**约束**:入口二的"主干换人"**不是真换主干**。原因 — 入口二的事件流里,BO 仍然是其中一种 `EventDetector`,且 `BreakoutDetector.evaluate_batch` 内部仍依赖现有增量峰值检测逻辑(`active_peaks` / `_check_breakouts` 见 `breakout_detector.py:560`)。BO 框架(峰值维护 + 突破判定)只是被**包装**成 EventDetector 接口,核心算法没动。所以入口二与其说"BO 框架被纳入 EventChain",不如说"BO 框架与其他形态检测器共用 EventDetector 抽象,EventChain 是这些检测器之上的组合层"。

**反过来,入口一里的 BO 也不是真主干** — `enrich_breakout` 已经开始通过 `vol_ratio_series`、`atr_series` 这种"预计算 series → bo_idx 取值"模式消费 t-indexed 表达(`features.py:217-228`)。这正是 EventChain 形态的雏形。**入口一其实已经在向入口二融合,只是 detector 仍专属于 BO。**

**结论**:两种入口在 EventChain **作为计算原语**的层面是统一的;差异只在"事件锚点的归属" — 入口一锚定在 BO,入口二让锚点可由任意 EventDetector 提供。

---

## 3. 覆盖面 — 真子集分析

### 入口一不能表达什么

1. **非 BO 锚点的事件流分析**:Platform / Step 等形态触发后的下游决策路径,无法在 BO 主干内承载。
2. **事件级的因果链**:三级派生(例 3)。
3. **"BO 不是主事件,Platform 才是主事件"的策略**:例如"Platform 形成日是建仓日,BO 仅作辅助过滤" — 入口一里 BO 是流水线的入口,无法绕开。

### 入口二不能表达什么

1. **BO 锚点的双锚段切片因子**:`pk_mom`(`features.py:471`)的窗口是 `[peak_idx, breakout_idx]`,其中 `peak_idx` 是数据驱动的(取距 BO 最近的 broken peak)。如果改成 t-indexed series 形态,每个 t 都要 ad-hoc 找"距 t 最近的 broken peak",**这相当于在每个 t 都把 detector 跑一遍**,语义闭环混乱且算力膨胀。
2. **BO 锚点的可变窗口 reduce 因子**:`dd_recov`(`features.py:802`)用 `np.argmax(highs)` + 从该位置切第二段。这种"动态找窗口内极值位置 → 二段切片"的语义,入口二的 t-relative rolling 表达不出。
3. **事件级元数据特征**:`age`(被突破峰值最老年龄)、`test`(阻力簇大小)、`broken_peaks` 列表 — 这些都依赖 `BreakoutInfo.broken_peaks` 这个 BO-specific 数据结构,不是 t-indexed 标量序列。`Breakout` dataclass 的 16 个标量字段(`breakout_detector.py:114-203`)里,`age / test / peak_vol / height` 4 个**只能从 broken_peaks 列表 reduce 出来**,完全在 EventChain 抽象之外。

**所以"谁是谁的真子集"**:

| 维度 | 关系 |
|---|---|
| 事件流编排 | **入口一 ⊂ 入口二**(入口一是入口二的"BO 唯一事件源"特例)|
| 事件级特征工程 | **入口二 ⊄ 入口一**(入口二缺乏 BO 锚点 + broken_peaks 元数据,无法表达 9 个家族 B/C/D 因子)|

**结论:不存在单向真子集,二者各有不可替代性。** 入口二在事件覆盖面更广,入口一在因子表达力上无法被替代(因为标量因子的范畴本身就不在 t-indexed series 的范畴内)。

---

## 4. 代码侵入性

### 入口一

- `factor_registry.py`:加 1 个 `TemporalFactorInfo` 子类(或直接复用 `FactorInfo`,新增 `chain_source: EventChain | None` 字段)
- `features.py:enrich_breakout`:加几行路由,把 chain factor 从 `series.iloc[bo_idx]` 取出
- `breakout_detector.py`:**完全不动**
- 新增层:`event_chain.py`(EventChain 类 + LRU 缓存)

**改动量级**:小。新增 1 个文件 + 2 个文件各加几行。现有 16 个 `_calculate_*` 不动,FACTOR_REGISTRY 现有 16 条不动。

### 入口二

- 新增 `EventDetector` Protocol(或基类)
- `BreakoutDetector` 退役为 `EventDetector` 子类:需要加 `evaluate_batch(df) -> Series[bool]` 的封装(把 incremental `add_bar` 跑完后再产出 is_bo series)
- 新增 `PlatformDetector` / 其他 EventDetector 实现
- 新增事件流编排层:`EventChain.after(prev)` / 多事件 join
- 上层调度(`live/pipeline/daily_runner.py`)要从"扫 BO" 改成"扫 events,然后按事件类型路由"

**改动量级**:中-大。涉及核心 detector 的接口换层,以及 daily_runner 的调度心智改变。**且并未消除 BO 框架的"标量因子计算" — 这部分仍要保留,等于增加了一个新抽象但旧抽象不能砍**。

### 现状基线参考

读 `live/pipeline/daily_runner.py` 现有形态:它已经是 batch-refresh(每日跑全量历史),所以"事件流"在 batch 形态下成立。但 daily_runner 当前的产出契约是"BO 列表 + Breakout 标量字段",改成"事件列表"是产出 schema 级变更,会牵动 UI / 持久化层。

### 侵入性结论

| 维度 | 入口一 | 入口二 |
|---|---|---|
| 现有代码改动 | 几乎零 | detector 重构 + dispatcher 重构 + 产出 schema 重构 |
| 新增抽象 | 1 个(EventChain)| 3 个(EventDetector / EventChain / EventComposer)|
| 未来扩展支撑(单点因子)| 强 | 中(需投影回锚点)|
| 未来扩展支撑(多事件流)| 弱(需另开平行流)| 强 |

---

## 5. 第一性原理收口

**计算单元的本质是"输入 → 输出"的形状契约。**

- 标量因子:`(df, bo_idx) → Optional[float]`。锚点是事件触发时刻,窗口左端点由 idx 反向推。
- EventChain:`df → Series`。锚点是每个 bar 自身,窗口语义是 t-relative。

**这是两个不同的范畴,不是同一个范畴的两个特例。** 入口一让 EventChain 通过 `iloc[bo_idx]` 投影到标量范畴,Adapter 是单向无损的。入口二让标量因子被迫升格为 series 形态,但 9 个家族 B/C/D 因子(volume/pre_vol/pbm/dd_recov/pk_mom/ma_pos/ma_curve/day_str/overshoot)的"BO-anchored 可变窗口"语义在 t-indexed series 里找不到等价表达 — 强行升格要么算力膨胀 200-500 倍,要么语义闭环混乱。

奥卡姆剃刀:**保留入口一作主干,通过单向 Adapter 把 EventChain 接入因子注册表;入口二的能力(多事件流编排)以 `EventChain.after()` 算子的形式作为入口一的子集存在,而不是反过来取代主干。** 这是与搭档 `compute_interface_design.md` 方案 B 的天然收口。

**唯一会让"入口二取代入口一"成立的场景**:业务上彻底放弃 BO 作为主事件锚点,改成多形态等权事件流(Platform 与 BO 平级)。这不是计算层的决策,是产品决策 — 一旦发生,入口二是必由之路;否则入口一更经济。
