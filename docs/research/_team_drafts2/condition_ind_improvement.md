# `Condition_Ind` 改进空间评估

> 评估对象：`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py`（核心实现仅 ~60 行）
> 视角：base 接口的设计缺陷、可落地的改进 API、与 BO 因子框架的关系
> 不重复 `_team_drafts/condition_ind_analysis.md` 已述内容（语义模型、嵌套链证据、与 BO 框架的"扁平 vs 时序"对比）

---

## 0. 一个先于"缺陷分析"的关键诊断

`grep -r "class Result_ind" new_trade` 返回 0 行。换句话说：

- `wide_scr.py:48`、`wide_scr.py:88` 用到的 `Result_ind`，
- `wide_scr.py:78` 用到的 `Hole_St`，
- `wide_scr.py:37` 用到的 `MA_Converge`，
- `wide_scr.py:4` 的 `from screener.state_inds.Condition_ind import ...` 整个模块路径，

**全部已不存在**。`scrs_train/define_scr/train_before_hole.py:46`、`dyn_hole.py:46` 仍在引用 `Condition_ind` 模块名，但目录里没有这个文件。

这说明历史上确实存在过一个"全功能扩展版" `Condition_Ind`（带 `keep`/`keep_prop`/`exp_cond`/`relaxed` 字段），但它**没能稳定为可复用的 base API**，要么被删了要么被分散重写到各业务子类里。base.py 留下的 60 行只是"语义最小子集"，并不能跑用户用例代码（wide_scr.py 实际跑不起来）。

**这是评价"改进空间"的最核心证据**：扩展不是"想加什么"，而是"已经加过、加偏了、又退回来了"。下面的缺陷分析里，凡是涉及 `keep`/`exp_cond`/`relaxed` 的，都不是 hypothetical，是**实战代码已经塞进去的语义维度，但没找到合适的接口承载**。

---

## A. 现有设计的缺陷（不留情面版）

### A1. 三个并行数组的状态散落 — 状态没有抽象

**代码现象**（`base.py:20-22`）：

```python
self.last_meet_pos = [float('-inf')] * len(conds)
self.scores        = [0] * len(conds)
self.must_pos      = [i for i, c in enumerate(conds) if c['must']]
```

三个 list 用相同的下标 `i` 串起来，没有任何结构体把它们绑在一起。`local_next` 子类如果想看"cond_3 上次满足距今多少根"，只能 `len(self) - self.last_meet_pos[3]` — 完全靠下标对齐，而 `conds` 列表本身又是 dict 的 list，再多一层下标。

**实战代价**：

- 序列化困难（要把 `last_meet_pos[]` + `scores[]` + `conds[]` + 子 indicator 状态全部冻结，没有统一边界）
- 测试困难（无法对单个 cond 的"窗口状态"做 unit test，必须跑完整 backtrader cerebro）
- 调试困难（user 在 `wide_scr.py:88` 这种 4 层嵌套结构里想知道"为什么这一根 valid=False"，要逐层 print 每个 cond 的 `scores[i]` — 无 introspection API）

### A2. `min_score` 是数值门槛，无法表达结构化的 OR / k-of-n

**代码现象**（`base.py:50`）：

```python
if sum(self.scores) >= self.p.min_score and all(np.array(self.scores)[self.must_pos]):
```

聚合逻辑被钉死成"所有 must 都满足 + 总分 ≥ 门槛"。

**它表达不出的结构**：

- "至少满足 cond_A 和 cond_B 中的一个"（结构化 OR） — 必须把 A、B 都设成 must=False，再拉低 min_score，但这就**污染了其它非 must 条件的语义**
- "cond_A 和 cond_B 至少有 2 个，再加 cond_C 必须满足" — k-of-n 只能用计数硬塞
- "cond_A 满足时 cond_B 不必，cond_A 不满足时 cond_B 必须" — 条件依赖完全无法表达

**实战触发**：用户当前 4 特征规律里"短期内多个 BO + 放量"是个典型的 k-of-n + must 混合，base.py 的 `min_score` 处理不了，所以产线必须自己包一个 `Vol_cond` 把"BO 计数"硬编码进 `local_next`（`functional_ind.py:485`）。**每出现一种新的聚合方式就要新建一个子类**，这是接口缺陷被外推为类爆炸。

### A3. `causal` 命名严重误导

**代码现象**（`base.py:30, 45`）：

```python
if 'causal' not in cond:
    cond['causal'] = False
...
cond['ind'].valid[-1 if cond['causal'] else 0]
```

这个字段控制的是"是否消费同根的子 valid"，**和因果性无关**（在 backtrader 的依赖求值顺序下，同根的子 valid 已经算完，不构成未来数据泄漏）。底稿 §一.causal=False 真实含义已经讲清楚 — 它是"嵌套链时延堆积控制"。

**实战代价**：

- 新人第一次看到 `causal=False` 几乎一定理解成"允许窥视未来" — 这是教材级误解
- 实际上**所有产线代码都默认 `causal=False`**（见 `wide_scr.py:50, 52, 53, 71, 88`），只有 base 里的 default 是 False，这个默认值是对的，但字段名错了 — 等于把"反直觉的事"用"反直觉的名字"挡住，劝退所有合作者
- `wide_scr.py:88` 单层嵌套都要写 `causal=False`，作者自己都不再相信"causal=True 是默认安全选项"

**正确命名**：`use_self_bar` 或 `same_bar_consume` 或干脆 `delay_one_bar=False`。

### A4. 缺 quantifier — 计数 / 比例 / 全持续都没有原生支持

**代码现象**：base.py 只有一个 `exp` 字段，语义是"过去 exp 根中**任意一根**满足即视为现在仍有效"（hit-in-window）。

**它表达不出的 quantifier**：

| 语义 | base.py 怎么写 | 应该的写法 |
|---|---|---|
| 过去 N 根中**至少 k 根**满足 | 不行 — 只能间接靠 `min_score` 里塞重复条件 | `count_in_window(N, k)` |
| 过去 N 根中**满足比例** ≥ p | 不行 | `ratio_in_window(N, p)`（产线已扩展为 `keep`+`keep_prop`） |
| 过去 N 根**全部**满足 | 不行 | `all_in_window(N)` |
| 第一次满足后**保持** N 根 | 不行 | `latch_for(N)` |

`wide_scr.py:50` 的 `keep:40, keep_prop:0.7` 就是 `ratio_in_window(40, 0.7)` 的产线扩展 — 但这字段没被 base.py 支持，意味着**子类必须重新解析 conds dict** 自己实现，每个子类都重写一遍。这就是 A1 + A4 的耦合恶果：状态散落 + 没有 quantifier 抽象 = 没办法"加一个新 quantifier 一次解决所有子类"。

### A5. base 接口与产线扩展接口已**事实上不一致**

**代码现象**：

- base.py 接受的 cond 字段：`{ind, exp, must, causal}`（`base.py:24-31`）
- 产线代码（`wide_scr.py:48-76`、`scrs_train/define_scr/dyn_hole.py:48-68`）实际写的字段：`{ind, exp, must, causal, keep, keep_prop, exp_cond, relaxed}`

后者多出来的 4 个字段在 base.py 的 `next()` 里**没有任何代码读它们**。这意味着：

- 要么产线用的是另一个被删掉的扩展版 `Condition_ind.py`（前面 §0 已确认），
- 要么这些字段被某个中间子类（如已被删除的 `Result_ind`）单独解析

无论哪种，**base.py 都不是 production interface 的真实定义** — 它是 history 残骸。任何今天想"基于 base.py 改进"的人，第一步就是要还原那个不存在的 production 版本，这是巨大的技术债。

### A6. 缺"跨条件的状态传递" — 事件之间无引用关系

**代码现象**（`base.py:40-55`）：每个 cond 在 `next` 里是**独立打分**的：判断"cond_i 自己的 valid 是否在 exp 窗口内"，cond_i 和 cond_j 之间没有任何引用通道。

**它表达不出**：

- "cond_B 满足的那根 bar 上，cond_A 当时的 strength 值"（事件时序的属性 carry-over）
- MATCH_RECOGNIZE 的 `LAST(BO.resistance)` — 在后续条件里引用前一个事件的标量
- 用户规律 4："最后一个 BO 后，股价高于**那个 BO** 的阻力位" — 需要把 BO 事件的 `resistance` 字段携带到下游条件

**唯一的 workaround**：让 cond_j 的 ind 内部直接持有 cond_i 的引用（破坏封装），或全部存到全局 dict 里靠时间戳查找（性能灾难）。`Hole_St`（`backup_ind.py:132`）就是用 `rv=vol_cond` 这种"硬塞引用"的方式表达"放量后的状态机" — 可以用，但每次新规律都要写一个新类，**完全失去了"组合式"价值**。

### A7. 输出只有一条 `valid` — 单通道无法返回结构化结果

**代码现象**：`lines = ('valid',)`（`base.py:8`）。

`valid` 在源码里同时承担两种语义：

- bool（true/false 是否匹配）
- float（`signal[0]` 的强度 — 见 `base.py:51`）

这意味着**无法同时返回**：

- "是否匹配"
- "score（多少 must/optional 满足了）"
- "matched_conds（哪些 cond 命中了）"
- "match_window（匹配的时间区间）"

实战代价：调试要看"为什么 valid=False"，没有结构化输出，只能在每个子 cond 里塞 `print` — `BreakoutPullbackEntry.log_debug`（`functional_ind.py:67`）就是这么实现的。**调试体验是 print-driven 而不是 introspection-driven**。

### A8. 流式订阅与批处理脱节

**代码现象**：`Condition_Ind` 继承 `bt.Indicator`（`base.py:7`），这意味着**它的整个生命周期绑死在 backtrader Cerebro 里** — 必须有 `data feed`、`addminperiod`、Cerebro 的 next-loop 驱动才能跑。

**它表达不出 / 做不到**：

- 对一个已经存在的 pandas DataFrame 一次性扫描"哪些 bar 上 valid=True"（必须 wrap 成 PandasData feed + cerebro.run，开销巨大）
- 嵌入到 mining 流水线（mining 需要的是"给定 N 个 BO 事件，每个事件返回 cond_chain_score" — 是事件级 batch 而不是 bar 级 stream）
- 单元测试（要造 fake DataFeed，无法直接 `cond.evaluate(df, idx) -> bool`）

底稿 §四.4.3 已经把这个工程冲突点出来了，但底稿说的是"它不适合 mining 流水线"，**这里更狠一层**：它甚至不适合任何不绑 backtrader 的场景，包括纯 NumPy 的批处理、Jupyter 探索、Python REPL 调试。**`bt.Indicator` 继承是它最大的工程债**。

### A9. 各子类可见的副作用：每条规律都新写一个状态机子类

数一下产线 `state_inds/` 目录里 `Condition_Ind` 的子类：`BreakoutPullbackEntry`、`PriceStability`、`Vol_cond`、`Vol_cond_realtime`、`MA_CrossOver`、`MA_BullishAlign`、`Simple_MA_BullishAlign`、`Narrow_bandwidth`、`Narrow_realtime`、`MA_EarlyBullish`、`MACD_CrossOver`、`MACD_ZeroCross`、`OBV_Divergence`、`Compare`、`Duration`、`Empty_Ind`、`Regression`、`MA_Converge0`、`MA_Converge`、`MAParallel`、`BuyPoint`、`OBV_platform`、`BBand_converge`...

20+ 个子类里，**绝大部分** `local_next` 就是几行 if-else（典型如 `Compare`、`MA_BullishAlign`、`Narrow_bandwidth`），它们之所以要新开一个类，是因为没有"用 DSL 表达原子条件"的途径。**这等价于 SQL 数据库每写一个 WHERE 都要新建一个 view** — 接口表达力不足把组合性外推成了类爆炸。

---

## B. 重要的改进设计（API 草案）

挑 4 个最关键的缺陷给出可落地的设计 — 每个都是"接口形状 + 解决了什么 + 代价"。

### B1. 把状态封装为 `WindowState`，cond 配置变成 `dataclass`

**新接口**：

```python
@dataclass(frozen=True)
class CondSpec:
    """Pure 配置 — 不含任何运行时状态。可序列化、可比较、可哈希。"""
    ind: HasValid                     # 任何带 .valid 序列的对象（不绑 bt.Indicator）
    quantifier: Quantifier            # 见 B2 — 替换 exp + keep + keep_prop
    role: Literal['must', 'optional', 'forbid'] = 'must'
    weight: float = 1.0               # 用于 score 聚合
    name: str | None = None           # 用于 introspection / debug
    delay_one_bar: bool = False       # 替换 causal,语义清晰

@dataclass
class WindowState:
    """运行时状态 — 每个 cond 一份。"""
    last_meet_pos: int = -math.inf
    history: deque = field(default_factory=deque)   # 用于 quantifier 回溯
    score: float = 0.0
    fired_this_bar: bool = False

class ConditionInd:
    """不再继承 bt.Indicator — 见 B4。"""
    def __init__(self, specs: list[CondSpec], aggregator: Aggregator):
        self._specs = specs
        self._states = [WindowState() for _ in specs]
        self._aggregator = aggregator
```

**解决的问题**：A1（状态散落）+ A5（接口不一致）。

**代价**：
- 破坏向后兼容 — 老的 `dict-based conds` 全部要改写。可以提供一个 `from_legacy_dict()` 的桥接层降低迁移摩擦
- 增加心智 — 多了 `CondSpec` / `WindowState` / `Quantifier` / `Aggregator` 4 个概念，但这是把"散落在 60 行 + 各子类 self.* 里的隐藏概念"显式化，**总复杂度下降**

### B2. `Quantifier` 抽象 + 结构化 `Aggregator`

**新接口**：

```python
class Quantifier(Protocol):
    """决定一个 cond 在窗口内是否"激活"。"""
    def evaluate(self, history: deque, current_bar: int) -> bool: ...

# 内置实现 — 对应 base.py 里 exp 的语义和产线偷塞的扩展字段
class HitInWindow(Quantifier):       # = exp=N
    def __init__(self, n: int): self.n = n

class CountInWindow(Quantifier):     # 缺失能力 1
    def __init__(self, n: int, k: int): self.n, self.k = n, k

class RatioInWindow(Quantifier):     # = keep + keep_prop
    def __init__(self, n: int, p: float): self.n, self.p = n, p

class AllInWindow(Quantifier):       # 缺失能力 3
    def __init__(self, n: int): self.n = n

class LatchFor(Quantifier):          # 缺失能力 4 — "首次满足后保持 N 根"
    def __init__(self, n: int): self.n = n


class Aggregator(Protocol):
    """决定多个 cond 的组合判定 — 替换 base.py:50 的硬编码聚合。"""
    def aggregate(self, specs: list[CondSpec], states: list[WindowState]) -> AggregateResult

@dataclass
class AggregateResult:
    matched: bool
    score: float
    matched_conds: list[str]              # cond.name 列表
    failed_must: list[str]                # 调试用 — A1+A7 一起解决
    matched_window: tuple[int, int] | None = None

# 内置 Aggregator
class AllMustAndMinScore(Aggregator):     # = base.py 现有逻辑
    def __init__(self, min_score: float): ...

class KOfN(Aggregator):                   # 解决 A2 "结构化 OR"
    def __init__(self, k: int): ...

class WeightedThreshold(Aggregator):
    def __init__(self, threshold: float): ...

class BoolExpr(Aggregator):               # 终极方案 — DSL 表达任意布尔结构
    def __init__(self, expr: str):
        # expr 例如: "must:A AND (B OR C) AND COUNT(D, E, F) >= 2"
        ...
```

**解决的问题**：A2（结构化 OR / k-of-n）+ A4（quantifier 缺失）+ A7（结构化输出）。

**举例 — 用户 4 特征规律**：

```python
ConditionInd(
    specs=[
        CondSpec(ind=ma40_flat,    quantifier=RatioInWindow(40, 0.8),  name='ma_flat',  role='must'),
        CondSpec(ind=is_bo,        quantifier=CountInWindow(20, k=2),   name='multi_bo', role='must'),
        CondSpec(ind=vol_burst,    quantifier=HitInWindow(20),          name='vol_at_bo', role='must'),
    ],
    aggregator=AllMustAndMinScore(min_score=0)
)
# 输出: AggregateResult(matched=True, matched_conds=['ma_flat','multi_bo','vol_at_bo'], failed_must=[], ...)
```

**代价**：
- 引入 2 个新抽象（Quantifier / Aggregator），但**取代了 4 个产线字段**（`exp`/`keep`/`keep_prop`/`min_score`），净复杂度下降
- 每根 bar 多调一次 `quantifier.evaluate()` — 性能开销 < 5%（quantifier 内部 O(1) 摊销，用滑窗 deque 维护）

### B3. 跨条件状态传递 — `BindOn` + `LastValue`

**新接口**：

```python
class CarryAttr:
    """声明"在 cond X 满足的那一根 bar 上，捕获 X.<attr> 的值，留给下游引用"。"""
    def __init__(self, source_cond_name: str, attr: str):
        self.source = source_cond_name
        self.attr = attr

# CondSpec 扩展一个 carries 字段
@dataclass(frozen=True)
class CondSpec:
    ...
    carries: list[str] = ()             # 暴露给下游的属性名

# 下游 cond 的 ind 在构造时声明绑定
class StepAbove(Atom):
    def __init__(self, ref: CarryAttr):
        self.ref = ref      # CarryAttr('multi_bo', 'last_resistance')

    def evaluate(self, ctx, idx) -> bool:
        # ctx 是聚合器维护的 cross-cond 上下文
        return ctx.last_value('multi_bo', 'last_resistance') < self.ctx.close[idx]
```

**解决的问题**：A6（事件间无引用）。

**举例 — MATCH_RECOGNIZE 的 `LAST(BO.resistance)`**：

```python
ConditionInd(
    specs=[
        CondSpec(ind=is_bo,           quantifier=CountInWindow(20, 2),   name='multi_bo', carries=['resistance'], role='must'),
        CondSpec(ind=StepAbove(ref=CarryAttr('multi_bo','resistance')),
                 quantifier=AllInWindow(15),                              name='step_up',  role='must'),
    ],
    aggregator=...
)
```

**解决的能力**：用户规律 4 的"BO 后股价稳定**在那个 BO 之上**" — 终于能引用前一事件的标量。

**代价**：
- 实现复杂度↑（要维护 cross-cond context dict + cond 之间的拓扑序求值）
- 引入"事件捕获时刻"的语义：`carries` 在哪个时刻 snapshot？默认是"cond 最后一次满足时" — 要在文档里讲清楚，否则会成为新的"causal"误解
- 但**这是 base.py 想做却做不到的最关键能力**，做不出来就只能停留在"独立散因子组合"的天花板

### B4. 脱离 backtrader — 双模接口

**新接口**：

```python
class ConditionInd:
    """两种使用模式，共享同一组 specs。"""

    # 模式 1: 批处理 — 给定 DataFrame 一次性扫描
    def scan(self, df: pd.DataFrame) -> pd.DataFrame:
        """返回 columns=['matched','score','matched_conds',...] 的 DataFrame, 同 idx 对齐 df。"""

    # 模式 2: 流式 — 一次喂一根 bar(可对接 backtrader / live feed)
    def feed_bar(self, bar: Bar) -> AggregateResult:
        """状态在 self._states 里推进。"""

    # 模式 3 (派生): backtrader 适配器 — 老代码无感切换
class BTAdapter(bt.Indicator):
    def __init__(self, ci: ConditionInd):
        self._ci = ci
    def next(self):
        result = self._ci.feed_bar(...)
        self.lines.matched[0] = float(result.matched)
        self.lines.score[0]   = result.score
```

**解决的问题**：A8（流式批处理脱节）+ A9（类爆炸 — 因为子类化 backtrader 的成本太高）。

**对 Trade_Strategy 的具体含义**：
- 立刻可以嵌入 mining 流水线 — `scan(df)` 一次返回某个 cond_chain 在所有 BO 事件上的命中向量
- 可以在 Jupyter 里 `ConditionInd(...).scan(df).head()` 直接调试，不需要 `cerebro.run()`
- 单元测试可以构造 5 行 fake df 直接 assert，不需要 mock backtrader

**代价**：
- backtrader 老代码必须用 `BTAdapter` 包一层 — 一次性迁移成本，但适配器只有 ~10 行
- 双模意味着**两条状态推进路径要保持一致** — 需要单元测试覆盖"scan(df) 的输出 == 逐 bar feed_bar 的输出累计"

---

## C. 改进后的 Condition_Ind v2 与 BO 因子框架的关系

### C1. v2 是否能成为"BO 因子框架的上层 pattern 语言"？

**答**：能成为"**事件级 pattern 表达层**"，但不能消解 BO 框架的核心价值。两者关系是**互补的两层**而不是"上下层覆盖"。

**v2 适合**：表达"在 BO 事件级别上的复合条件"。例如：
- "某个 BO 满足 X 的同时，过去 N 天还存在另一个 BO 满足 Y" — 用 `CountInWindow + CarryAttr` 自然
- "MA40 在 BO 之前 80% 的天保持横盘 + BO 当天放量 + BO 之后股价稳定" — 用 3 个 CondSpec + 不同 quantifier + carries 表达

**BO 框架适合**：mining 流水线里的"标量因子 AND 模板枚举 + Optuna 阈值搜索"。这是工程基线，bit-packed 矩阵 + Bootstrap CI 是它的硬资产。

**正确组合方式**：
1. v2 输出"事件级 bool / score / matched_conds" → 注册为新的 BO 因子（`FACTOR_REGISTRY` 里多一行）
2. mining 仍然在 11+1 个标量因子上做 AND 模板枚举
3. v2 的内部复杂度对 mining 透明 — mining 看到的就是"这个事件 cond_chain_score = 0.85"

这就是底稿 §五"方案 A"的精确化 — 改进后的 v2 是这个方案的最佳实现层。

### C2. 还是说它本质上是另一种范式（流式 vs 批），无法消解差异？

**部分是,但 B4 已经消解了关键差异**。

- **改进前**：v1 是纯流式 — backtrader 强依赖 — 与 BO mining 的"事件级 batch"完全不在一条工程线上 — 必须 wrap 成"输出向量再做切片"，性能 + 可维护性都差
- **改进后**：v2 双模接口 — `scan(df)` 是 batch 模式，直接给 mining 用；`feed_bar()` 是 stream 模式，给 live 盯盘用 — **同一份 specs 两边复用**

剩下的真差异：**post-event 引用**（用户规律 4）在 batch 模式里天然好做（前后看自由），在 stream 模式里仍然只能延迟 K 根触发（与底稿 §3.1 的物理约束一致 — 这不是架构能解决的）。

### C3. 实际在 Trade_Strategy 里实现 v2，应该绑 backtrader 还是脱离？

**强烈建议脱离 backtrader，纯 NumPy/pandas 实现**（即 B4 的方案）。

理由：

1. **Trade_Strategy 的核心数据流不依赖 backtrader**：BreakoutDetector / FactorRegistry / mining / Optuna 全部基于 pandas DataFrame + NumPy。引入 backtrader 是"为了一个组件引入一个框架" — 反向污染
2. **mining 流水线需要 batch 评估**：`scan(df) -> (matched, score, ...)` 对齐 BO 事件 idx → 直接喂给 `BreakoutScorer` / `template_validator`，零摩擦
3. **live 盯盘场景可以用 incremental scan**：`scan_incremental(new_bars)` 在已有状态上推进 — 比 backtrader 的 cerebro 重启便宜得多
4. **测试性**：`pytest` 里 5 行造个 df 就能跑，不需要任何 fixture
5. **未来如果要升级到 MATCH_RECOGNIZE 风格**（底稿 Stage 3）：v2 的 `Quantifier` + `Aggregator` + `CarryAttr` 是 MR 的 DEFINE / MEASURES / quantifier 的天然映射 — 不需要再切换底层框架，直接在 v2 之上扩展 PATTERN AST 即可。**v2 是 Stage 2 → Stage 3 的最佳过渡基座**

**唯一保留 backtrader 的理由**：如果用户需要在 backtrader 里也能用（例如调试旧策略），写一个 `BTAdapter` 即可（B4 已示意，~10 行）。

---

## D. 最关键的 3 条优先级建议

如果只能改 3 件事，按 ROI 排序：

1. **B4（脱离 backtrader）**：单点收益最大 — 不脱离的话，所有其它改进都被关在 backtrader 沙盒里出不来
2. **B2（Quantifier + Aggregator）**：消除 base.py / 产线字段不一致这个最大的技术债，同时解决 quantifier 表达力 + 结构化 OR
3. **B1（状态封装）**：是 B2 / B3 的前置基础设施 — 不做的话 B2 / B3 都没法干净落地

B3（跨条件状态传递）是表达力天花板的关键，但也是最复杂、最容易做错的 — 可以放在 v2 v0.2 而不是 v0.1。

---

## E. 一句话结论

`Condition_Ind` base.py 的 60 行只是一个**未稳定的最小骨架**，产线已经偷塞了 4 个未文档化的扩展字段、删除了一整个 `Condition_ind.py` 模块、并以 20+ 个一次性子类的方式补全表达力 — 这是接口缺陷的副作用而不是设计成熟。一个干净的 v2（脱离 backtrader + Quantifier 抽象 + 结构化 Aggregator + 显式状态封装）能把它从"BO 框架的散因子之外的玩具"提升为"BO 框架可复用的事件级 pattern 表达层" — 但这只是 Stage 2 的中间形态，距离 MATCH_RECOGNIZE 风格的事件正则匹配仍有顶层 PATTERN AST 这一步。
