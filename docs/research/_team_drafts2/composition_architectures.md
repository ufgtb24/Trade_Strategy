# 灵活组合走势特征的替代架构调研

> 立题：在前一轮研究确立 MATCH_RECOGNIZE 为「事件级 pattern 匹配」最优解后，焦点转向另一个正交问题 ——
>
> **是否存在更适合「灵活组合 / 编排走势特征」的架构范式？**（即把"特征"抽象为可组合的一阶对象本身的范式）
>
> 注意区别：MATCH_RECOGNIZE 解决「pattern 匹配的语言」；本轮关注「特征定义的可组合性」。这两个抽象层正交 —— MR 内部的 DEFINE 段仍然要写成"扁平谓词"，复用、抽象、嵌套都依赖宿主语言。
>
> 本轮覆盖 7 类范式（深入 4，简评 3），全部为前序未涵盖：Behavior Trees / Reactive Streams (FRP) / Dataflow Graphs / Parser Combinators / HFSM-GOAP / Petri Nets / Monadic DSL。
>
> 工具与文献：context7 查询 RxPY (`/reactivex/rxpy`)、Py Trees (`/websites/py-trees_readthedocs_io_en_devel`)、Dask (`/dask/dask`)；其余范式走概念性评估。

---

## 0. 评估框架

「组合走势特征」需要回答三个问题：

1. **特征是不是一阶对象？** 能否被赋值、传参、返回、嵌套？
2. **组合算子是什么？** 顺序、并行、备选、装饰、聚合……是否原生支持？
3. **怎样喂给 mining 流水线？** 可否参数化生成、bit-pack 评估、Optuna 搜索？

下面对每个范式按这三个问题展开，并给出与 Condition_Ind / MATCH_RECOGNIZE 的对照。

---

## 1. Behavior Trees（BT）

> context7 来源：Py Trees 文档（`/websites/py-trees_readthedocs_io_en_devel`），核心证据来自 `Sequence` / `Selector` / `Parallel` / `Decorator` / `Blackboard` 模块。

### 抽象本质（一句话）

**每个特征是一个返回 `SUCCESS / FAILURE / RUNNING` 三态状态码的可 tick 节点；组合子是 Sequence（顺序与）/ Selector（备选或）/ Parallel（并行）/ Decorator（包装）。** 整个特征图是一棵自上而下被 tick 的树，每根 bar tick 一次根节点。

### 用户 4 特征如何编排（具体例子）

```text
Selector(memory=False)                                     # 备选：满足任何一个 strategy 都 OK（暂时只 1 个）
└── Sequence(memory=False, name="MultiBO_VolStep")
    ├── PreCondition[FlatMA40_in_lookback]                 # 特征 3：MA40 水平
    ├── Decorator[CountAtLeast(2, window=15)]
    │   └── Sequence
    │       ├── BO_Detected
    │       └── Volume > 1.5x
    │                                                      # 特征 1+2：15 天内 ≥ 2 次放量 BO
    └── Decorator[Eventually(within=10)]
        └── PostCondition[Step_Above_Resistance]           # 特征 4：之后 10 天台阶
```

要点：
- `Sequence` 的 `memory=True` 会让 RUNNING 的子节点在下一 tick 直接续上，**天然实现"事件流上的状态机"**（py-trees Sequence 实现：第 50-95 行 tick 函数 + memory 字段）
- `Decorator` 是装饰器节点，一阶包装任意子节点 —— "在窗口 W 内至少 K 次"、"取反"、"超时失败"等都是 Decorator
- `Blackboard` 是黑板共享存储，跨节点传 `last_bo_ts`、`bo_count` 等中间值

### vs Condition_Ind 的优势

| 维度 | Condition_Ind | Behavior Tree |
|---|---|---|
| 顺序约束 | 没有（exp 只是窗口） | **Sequence 原生** |
| 备选 | 没有 | **Selector 原生** |
| 装饰器复用 | 没有，要每写一个新 cond | **Decorator 一阶**：`Inverter`、`Timeout`、`Repeat`、`OneShot` 都是可复用包装 |
| 状态语义 | 只有 valid bool | **三态 SUCCESS/FAILURE/RUNNING**：RUNNING 就是"还在等待中"——非常贴合"等待 post-BO 台阶形成"这种语义 |
| 复合谓词的可视化 | 没有 | py-trees 自带 graphviz dot 输出 |

`Sequence(memory=True)` 的语义恰好补上了 Condition_Ind 最大缺口：**"前置条件 1 触发后，等条件 2 触发"** 这种顺序状态机不需要手写 last_meet_pos 索引。

### vs MATCH_RECOGNIZE 的优势

MR 是"扁平 PATTERN + DEFINE"，复用谓词只能靠 SQL view 或字符串拼接。BT 提供的优势在另一个维度：

1. **节点是一阶对象**：可以工厂化生成、运行时组合、参数化绑定。一个 `BOSequence(window, count, vol_ratio)` 工厂可以 instantiate 成不同节点塞到不同位置 —— MR 做不到（PATTERN 是字符串 DSL）。
2. **Decorator 是真正的 HOC（high-order combinator）**：`Inverter(child)`、`Timeout(seconds, child)`、`Throttle(rate, child)`，组合方式无限。MR 的 quantifier 是固定语法集（`*+?{n,m}`）。
3. **三态语义对接 live 流式**：`RUNNING` 一档就是"还没失败也还没成立"，直接对应 mining 中的 `unavailable=True`。MR 是离散匹配，没有这一档。
4. **运行时改图**：BT 树可以热插拔节点，A/B 测试两个特征定义。MR 是声明式 query，必须重启引擎。

### 代价

- **生态**：py-trees 主要面向机器人/游戏，金融/时序应用极少；要把它当 backbone 必须自研 `BO_Detected` / `Volume_Ratio` / `Step_Above_Resistance` 等领域节点 —— 这是必然的迁移成本。
- **学习曲线**：策略开发者需要理解三态语义 + tick 周期 + Blackboard 共享。比"写一个 SQL pattern"陡。
- **与现有 mining 流水线契合度**：每个节点的"参数"可以是 Optuna 搜索维度，但 bit-packed AND 矩阵失效（节点输出是三态而非 bool）。可以折中："只用叶子节点输出 bool 给 mining，复合节点结构由人工定义"——这是合理的中间形态。
- **Tick 频率与回测**：BT 假设固定频率 tick，与 K 线回放天然契合，但要把"BO 事件触发"映射成"在该 bar tick 时叶子节点返回 SUCCESS"，需要一层适配。

### 关键限制

- **缺少时间窗的一阶语义**：BT 没有"过去 N 根 bar 内"这种内建算子，要靠 Decorator 自己写；这是 MR/CEP 的强项。
- **mining 自动模板化困难**：BT 树的"形状"本身是组合搜索空间，比"PATTERN 字符串"更难穷举。如果未来要 mining 自动发现复合特征结构，BT 比 MR 困难。
- **不擅长"事件正则的 quantifier 上下界搜索"**：`Decorator[CountAtLeast]` 是参数化的，但要枚举 `(2,5), (3,5), (3,7)...` 等组合，MR 的 `{n,m}` 在 SQL 里更直观。

---

## 2. Reactive Streams / FRP（Functional Reactive Programming）

> context7 来源：RxPY 4.x 文档（`/reactivex/rxpy`），核心证据：`combine_latest` / `with_latest_from` / `window` / `compose`(pipe) / `Subject` / Hot vs Cold 等模块。

### 抽象本质（一句话）

**每个特征是一个 Observable（事件流），用纯函数 operator (`map` / `filter` / `combine_latest` / `window` / `debounce` / `scan`) 做声明式组合；特征 ≡ stream，组合 ≡ stream-of-streams 上的代数。**

### 用户 4 特征如何编排（具体例子）

```python
import reactivex as rx
from reactivex import operators as ops

bars = Subject()                                            # 输入：bar 事件流

# 原子 stream
ma40_slope     = bars.pipe(ops.scan(rolling_slope, 40))
flat_ma40      = ma40_slope.pipe(ops.map(lambda s: abs(s) < EPS))   # 特征 3
bo_event       = bars.pipe(ops.filter(is_bo))
hi_vol         = bars.pipe(ops.filter(lambda b: b.vol_ratio > 1.5))
hi_vol_bo      = bo_event.pipe(ops.with_latest_from(hi_vol),       # 特征 1+2
                                ops.filter(lambda x: x[1]))

# 复合：在 15 根 bar 窗口内出现 ≥ 2 次 hi_vol_bo
bo_cluster     = hi_vol_bo.pipe(
    ops.window_with_count(15),
    ops.flat_map(lambda w: w.pipe(ops.count())),
    ops.filter(lambda c: c >= 2),
)

# 复合:特征 1+2+3 同时
pre_event      = rx.combine_latest(flat_ma40, bo_cluster).pipe(
    ops.filter(lambda x: x[0] and x[1])
)

# 特征 4：pre_event 触发后，等 10 根 bar 都满足 step_up
final_signal   = pre_event.pipe(
    ops.flat_map(lambda _: bars.pipe(
        ops.take(10),
        ops.all(lambda b: b.low > resistance)
    )),
    ops.filter(lambda ok: ok)
)
```

要点（对照 context7 RxPY 文档）：
- `combine_latest(A, B)` 在任一上游发射时，emit 最新对组合。
- `with_latest_from(B)` 只在 source 发射时才合并 —— 这是 BO 触发因子的天然语义（"BO 出现时取当时的 vol_ratio"）。
- `pipe(ops.compose(...))` 允许把"长度 > 5 的特征"封装为可复用 operator —— **特征作为函数级一阶对象的关键**。
- `Subject` 提供 hot stream 入口；`window_with_count` / `window_with_time` 是事件聚集的原生算子。

### vs Condition_Ind 的优势

| 维度 | Condition_Ind | Reactive Streams |
|---|---|---|
| 特征作为一阶对象 | 不是（Indicator 实例与 Cerebro 强耦合） | **Observable 是值**：可传参、可返回、可缓存 |
| 时间窗 | exp 单位是 bar 数，硬编码 | `window_with_count` / `window_with_time` 双语义自由 |
| 复用 | 几乎没有；嵌套要写新类 | `pipe(common_operator())` 任意组合 |
| 状态共享 | 各 Indicator 实例字段 | `share()` / `replay()` 多订阅者共享 |
| 顺序 | 没有 | `flat_map`(switch_map) 自然实现 "A 触发后等 B" |

最大的飞跃是**特征 = 函数 = 值**这一抽象。Condition_Ind 把"特征"绑死在类里；Rx 把它解放为一阶值，于是可以写 higher-order 工厂、把特征列表做 reduce、用 functools.partial 绑定参数等等。

### vs MATCH_RECOGNIZE 的优势

1. **代码层组合 vs DSL 层组合**：MR 的 PATTERN 是字符串 DSL；Rx 是 Python 表达式。可以用 `if cfg.use_step_check: pipeline = pipeline.pipe(ops.flat_map(...))` 这种条件组合 —— MR 必须字符串拼。
2. **多 sink 共享**：同一特征流可以同时供给"信号触发"、"日志"、"UI 渲染"、"label 生成"4 个下游，不重复计算。MR 是单一 query 出口。
3. **延迟 / 节流原生**：`debounce`、`throttle`、`sample`、`buffer_with_time` —— live 端处理"信号防抖"、"批量 UI 刷新"等开箱即用。MR 没有这一层。
4. **抽象层次更高**：Rx 的 operator 不区分 "特征 / 状态 / 触发"，统一为 stream transformation；这与 mining 的 batch 视角天然桥接（同一段代码，offline 喂 `from_iterable(historical_bars)`，live 喂 `Subject()`）。

### 代价

- **学习曲线**：FRP 心智模型陡（hot vs cold、subject、scheduler、backpressure）。Rx 文档里"Hot and Cold Observables"专章讲这个差别。
- **调试困难**：链式 pipe 出错时栈极深，断点不友好。
- **mining 流水线衔接**：bit-packed AND 矩阵彻底失效，要改成"per-symbol stream replay → 命中事件累计"——单 trial 评估代价上升 1-2 个数量级（与 MR 同量级）。
- **生态**：RxPY 在金融/量化用得不多；社区主要在前端/IoT。但 RxPY 4.x 已经稳定（context7 显示 770 个代码片段、High reputation）。

### 关键限制

- **声明式但不是 DSL**：不能像 MR 那样把 pattern 字符串化、序列化、参数化生成。复杂的特征组合是 Python 代码，**mining 自动枚举特征图困难**。
- **流式偏好 push 模型**：要做"事后窗口"（特征 4）必须 buffer K bar 才发射，本质上仍然有 K bar 延迟（与 MR 物理等价）。
- **不适合做 quantifier 形态匹配**：要表达 `(BO ANY*?){2,5}` 这种正则模式，Rx 写法非常笨拙。**Rx 是组合层，不是模式匹配层**。

---

## 3. Dataflow Graphs / Computation Graphs

> context7 来源：Dask 文档（`/dask/dask`），核心证据：`dask.delayed` / 任务图 / `visualize` / scheduler 模块。TensorFlow / PyTorch 的 graph mode 同理。

### 抽象本质（一句话）

**每个特征是 DAG 中的一个节点，依赖关系通过 edge 显式表达；框架自动调度（topological order），自动并行、缓存中间结果、可视化。**

### 用户 4 特征如何编排（具体例子）

```python
import dask

# 原子节点（每个返回 numpy/pandas Series 对应于全 symbol 全时段）
ma40        = dask.delayed(compute_ma)(bars, 40)
ma40_slope  = dask.delayed(rolling_slope)(ma40, window=W)
flat_ma40   = dask.delayed(lambda s: s.abs() < EPS)(ma40_slope)        # 特征 3

bo_events   = dask.delayed(detect_bo)(bars)
hi_vol_bo   = dask.delayed(filter_vol)(bo_events, ratio=1.5)           # 特征 1+2
bo_cluster  = dask.delayed(rolling_count)(hi_vol_bo, window=15, min=2)

resistance  = dask.delayed(extract_resistance)(bo_cluster)
post_step   = dask.delayed(check_step_above)(bars, resistance, k=10)   # 特征 4

# 复合
pre_event   = dask.delayed(lambda a, b: a & b)(flat_ma40, bo_cluster)
signal      = dask.delayed(lambda p, s: p & s)(pre_event, post_step)

signal.visualize()     # 自动生成 graphviz DAG 图
result = signal.compute(scheduler="threads")
```

要点（对照 context7 Dask 文档）：
- `dask.delayed(f)(x, y)` 把函数调用转成 lazy node；依赖通过参数引用建立。
- `.visualize()` 直接出 graphviz 图（Dask 文档明示）。
- 同一中间节点（如 `ma40`）被多个下游引用时，**只计算一次自动 cache**。

### vs Condition_Ind 的优势

| 维度 | Condition_Ind | Dataflow Graph |
|---|---|---|
| 中间结果复用 | 不显式，重复计算多 | **自动**：DAG 节点自然 dedup |
| 并行 | 完全串行 tick | **自动调度并行** |
| 可视化 | 没有 | `visualize()` 一键 |
| 大规模计算 | 单 symbol 单线程 | Dask 原生分布式 |

特别是"中间结果复用"对 mining 流水线意义巨大——一个 50 因子的模板枚举，公共依赖（MA40、ATR、roll vol）只算一次而非 50 次。

### vs MATCH_RECOGNIZE 的优势

1. **抽象层与执行层解耦**：DAG 是结构化表示，scheduler 可以是 single-thread / multi-thread / distributed —— 同一段代码 transparent。MR 必须 bind 引擎。
2. **图可被检视和操作**：可以遍历 DAG、修剪、合并、做 cost-based 优化。**这是任何 mining 自动化的关键基础设施**——Dask 的 high-level optimizer 就是干这个。MR 引擎内部黑盒。
3. **特征 = 节点 = 一阶对象**：可以 pickle、可以序列化为 JSON、可以保存到 DB。MR 是字符串 query。
4. **天然适合 vectorized batch**：mining 的 bit-pack 评估本质上就是 DAG 上的 `&` 节点，Dask 的"延迟图 + 并行 reduce"几乎是为这场景生的。

### 代价

- **范式不匹配 pattern matching**：DAG 是"批数据 → 批数据"的转换，不擅长"事件正则匹配"。要做"15 天内 ≥ 2 次 BO"得自己写 `rolling_count`，不会比手写优雅。
- **没有时序语义内建**：dataflow 默认假设节点输入是数据集合（NumPy array），不是事件流。"窗口"、"顺序"等概念要手写。
- **学习曲线**：Dask delayed 简单，但如果用 Dask Bag / Dask Array / 自定义 collection 会陡。

### 关键限制

- **不是 pattern matching 工具**：用 dataflow 描述"FLAT{5,} BO{2,5} STEP{10,}"会非常痛苦——这就是 MR 该做的事情。
- **静态图为主**：动态图（每根 bar 改图结构）需要 PyTorch eager 模式之类，但那基本就退化成 Python 控制流，DAG 优势消失。
- **过强的 batch 心智**：live 流式触发与 dataflow 的"compute() 一次性出结果"不天然契合，要专门设计增量重算。

---

## 4. Parser Combinators 应用于时间序列

> 没有现成 Python 库专门做时间序列 parser combinator；概念性候选包括 Haskell `Parsec` / Python `parsimonious` / Scala `fastparse` 思路迁移到事件流。

### 抽象本质（一句话）

**把"形态"看成可解析的"语言"，把 bar 流看成 token 流；每个特征是一个 `Parser`，组合子是 `seq`、`choice`、`many`、`optional`、`look_ahead`、`back_track` 等。**

### 用户 4 特征如何编排（伪代码 — 类 fastparse / parsec 风格）

```python
flat_window   = Parser.satisfy(lambda b: abs(b.ma40_slope) < EPS).at_least(5)
bo            = Parser.satisfy(lambda b: b.is_bo and b.vol_ratio > 1.5)
any_bar       = Parser.satisfy(lambda _: True)
bo_cluster    = (bo + (any_bar.many() + bo).at_least(1).at_most(4))   # 2..5 BOs
step          = Parser.satisfy(
    lambda b, ctx: b.low > ctx.last_bo_resistance
).at_least(10)

pattern = flat_window + bo_cluster + step                              # 全模式

# 在 bar 流上 scan
for match in pattern.scan(bar_stream):
    emit_signal(match)
```

要点：
- `+` 是 `seq`；`|` 是 `choice`；`many()` 是 `*`；`at_least(n)` 是 `{n,}`；`look_ahead` 实现"零宽断言"。
- Parser 可以**保留上下文**（`ctx`，跨 parser 传递 `last_bo_resistance` 等）——这正是 MR 的 `LAST(BO.resistance)` 在代码层的等价物。
- Parser 是一阶对象，可工厂化、可参数化、可 reduce：`seq([p1, p2, p3])` vs MR 的字符串拼接。

### vs Condition_Ind 的优势

完全包含 + 真超集：
- 顺序：`p1 + p2` 原生
- 计数：`many() / at_least() / at_most()` 原生
- 备选：`p1 | p2` 原生
- 嵌套：parser 之间任意组合

而且**combinator 本身是 Python 代码**，比 Condition_Ind 的"嵌套 cond 字典"更简洁、更可类型化。

### vs MATCH_RECOGNIZE 的优势

这是本节最有价值的对照——**Parser Combinators 是 MR 在代码层的等价物，但更灵活**：

| 维度 | MATCH_RECOGNIZE | Parser Combinators |
|---|---|---|
| 表达层 | 字符串 DSL | Python 代码 |
| 复用 | 靠 SQL view（部分引擎不支持） | 函数 / 闭包 / 工厂自然复用 |
| 自定义谓词 | DEFINE 段 + 引擎内置 UDF | **任意 Python 函数**，无引擎限制 |
| 跨变量引用 | `LAST(BO.resistance)` —— 引擎实现 | 显式 ctx 传递，**完全可控** |
| 动态构造 | 字符串拼，易出错 | `seq(parsers)` 安全、类型化 |
| 调试 | SQL EXPLAIN —— 黑盒 | Python pdb，每个 parser 是值 |
| 序列化 | pattern 字符串 | parser 树可 pickle / JSON |

**Parser Combinators 在「表达力 + 灵活性」上同时压制 MR 与 Condition_Ind**。它是把 MR 的"事件正则"语义吸收到 Python 函数代数中。

### 代价

- **没有现成的金融/时序 parser combinator 库**：Parsec / parsimonious 是字符 / token 解析，要把 Bar 视为 token 需要自研一层适配（类似自研 MR 解释器的工作量，约 1-2 周）。
- **NFA 性能**：一旦支持回溯（`back_track`），最坏情况指数级 —— 与 MR 同样的"灾难性回溯"陷阱。
- **生态**：Python parser combinator 库（parsy、funcparserlib）小众，主要面向 DSL 解析，迁移到时序需要心智重塑。
- **mining 自动化**：parser 树可序列化但**不能字符串化为 SQL**，所以无法外包给成熟引擎；要 mining 自动枚举 parser 树结构，比枚举 MR PATTERN 更难（搜索空间是函数调用图）。

### 关键限制

- **缺少"事后窗口"语义糖**：要表达"事件后 10 根 bar 的台阶"必须把 step 也写成 parser 串接，与 MR 一致；但 parser combinator 没有 MR 的 `AFTER MATCH SKIP` 这种管理重叠匹配的语法糖，要自己写。
- **缺少时间窗算子**：`within(15 days)` 要靠 ctx 中带时间戳手写 guard。
- **不擅长流式增量**：经典 parser 假设输入是完整 token list；做 streaming parser 要改写为 incremental（tools 如 Earley parser 支持，但实现复杂度高）。

---

## 5. 简评

### 5.1 HFSM（层级有限状态机）/ GOAP（目标导向行动规划）

**HFSM**（用 hsm.js / transitions 这类库为代表）：把交易策略写成"层级状态机"，状态是"等待 BO"、"BO 已发生"、"等待台阶"、"已成立"。优势是**显式建模"等待中"状态**，对 live UI 友好；**与 BT 高度重叠**（BT 的 Sequence+memory 本质就是层级 FSM 的另一种写法）。劣势：状态膨胀严重（4 特征 × 多种 partial 状态可能十几个），可视化乱。**作为 BT 的弱替代**，没有独立优势。

**GOAP**（来自 F.E.A.R. 游戏 AI）：每个 action 有 precondition + effect，规划器 A* 搜索从 init state 到 goal state 的 action 链。**与"组合走势特征"不匹配** —— GOAP 是"动作规划"而非"模式识别"，反向意图（你描述目标，让规划器搜索路径）与本场景（你已知模式，要在数据流上识别）正交。**不推荐**。

### 5.2 Petri Nets

经典并发流程建模工具，由 Place（库所）+ Transition（变迁）+ Token 组成；Token 在 Place 间流动，Transition 触发条件是入口 Place 的 token 满足。

**贴合度评估**：
- "短期内多个 BO" → BO Place 的 token 计数 ≥ 2 触发 Transition
- "等台阶" → 进入 Step_Waiting Place
- "并发流" → 适合多 strategy 并行（每个 strategy 一个子网）

**优势**：天然描述"并发触发的事件流"；Token 数语义比 BT 三态更细粒度。**劣势**：(a) Python 生态（snakes、SNAKES、PetriNetX）研究级；(b) 形式化色彩重，工程师上手陡；(c) **不擅长事件正则的 quantifier**；(d) **抽象层次与 BT 重合度高，但学习曲线更陡**——没有显著优势就不推荐。

### 5.3 Computation Expressions / Monadic DSLs（F# / Haskell）

把特征流写成 monad，用 `do` notation / `for` comprehension 串接。例如 `Maybe`-monad 处理 unavailable，`State`-monad 处理跨 bar 状态，`Reader`-monad 注入参数。

**优势**：极致优雅 —— "组合是 monad bind"，解决了"特征作为可组合对象"的根本抽象问题。Haskell `Pipes` / `Conduit` 库就是事件流上的 monad。

**劣势**：(a) Python 没有 native monad 支持，要靠 `returns` 库或手写 generator —— **生态完全不在那一边**；(b) 团队成员若不熟函数式编程心智会非常痛苦；(c) 与 mining bit-packed 评估几乎不兼容。**理论最美但工程上不现实**。

---

## 6. 综合排序与判断

### 6.1 7 类范式按"灵活组合走势特征"贴合度排序

| 排名 | 范式 | 核心优势 | 主要代价 |
|---|---|---|---|
| **1** | **Reactive Streams (FRP / RxPY)** | 特征 = 一阶值，operator 极完整，offline/live 同代码，多 sink 共享 | 心智陡、与 bit-pack mining 不兼容 |
| **2** | **Behavior Trees** | Sequence+memory 自然实现"等待状态机"，三态语义贴合 unavailable，Decorator 一阶可复用 | 缺时间窗一阶算子、mining 自动化困难 |
| **3** | **Parser Combinators** | MR 表达力 + Python 灵活性，特征 = parser = 值 | 无现成时序库、引擎要自研、mining 自动枚举难 |
| 4 | Dataflow Graphs (Dask) | 中间结果自动复用、自动并行、可视化好 | 不擅长 pattern matching，是补充而非替代 |
| 5 | HFSM | 状态显式 | 与 BT 重合无独立价值 |
| 6 | Petri Nets | 并发优雅 | 生态弱 |
| 7 | Monadic DSL | 理论最优 | 工程不可行 |

### 6.2 哪一类最贴近"组合走势特征"的需求？

**Reactive Streams（FRP / RxPY）**——理由：

1. **唯一同时回答了三个问题的范式**：(a) 特征是 Observable 一阶值；(b) 组合算子全（map/filter/combine_latest/window/scan/flat_map）；(c) offline/live 同 API 衔接 mining 的桥梁存在（虽然不如 dataflow 直接）。
2. **本质对位准确**：用户描述的"组合走势特征"——"放量 BO + 平 MA + 聚集 + 台阶"——天然是"多个 stream 的代数组合"。Rx 的 `combine_latest` / `with_latest_from` / `window` 几乎一一对应这套语义。
3. **抽象层次最贴合 backtrader/Condition_Ind 的"指标即一阶对象"心智**——Rx 的 Observable 与 backtrader 的 Indicator 心智模型同源（都是可订阅的时序流），但 Rx 提供了远更完整的 operator 代数。

### 6.3 是否有"Condition_Ind 的自然演化方向"？

**Reactive Streams 是 Condition_Ind 的最自然演化方向**，且证据明确：

| Condition_Ind 概念 | RxPY 等价 | 升级点 |
|---|---|---|
| Indicator 是带 valid line 的可订阅对象 | Observable 是带值的事件流 | 完全同构 |
| `cond['exp']` 滑动窗口 | `window_with_count(N)` / `buffer_with_time` | 双语义自由 |
| `must` 必选 | `combine_latest` + `filter` | 更显式 |
| `min_score` 计数 | `window().count() >= K` | 原生量化 |
| `causal=True` | hot Observable 默认 + 手动 buffer | 更灵活 |
| 嵌套 cond | `pipe(child_pipeline)` | 一阶值嵌套 |
| **缺顺序** | `flat_map(switch_map)` | **补齐** |
| **缺备选** | `merge` / `amb` | **补齐** |
| **缺 Decorator 复用** | `pipe(custom_op())` 任意函数 | **补齐** |

**Condition_Ind v2 = RxPY 重写 + 领域 operator 库**。心智模型是同一棵树的演化，只是 operator 集合从 5 个扩展到 50+，并且每个 operator 是数学纯净的。

### 6.4 如果用户做"Condition_Ind 替代"，最值得参考哪一类？

**双轨建议**：

- **代码层组合：Reactive Streams（RxPY 或自研轻量版）** —— 用于运行时定义、组合、订阅特征。生产路径首选。
- **结构层 mining：保留 Dataflow / Dask** —— 作为"中间结果复用 + 并行加速"的执行后端。Rx 的 pipe 内部可以委托给 Dask 任务图，做到 "API 是 Rx，引擎是 Dask"。

**MATCH_RECOGNIZE 仍然在更高的「pattern 形态识别」层有不可替代价值**——它和 Rx 不冲突，Rx 是组合层（"特征如何定义"），MR 是匹配层（"复合 pattern 如何识别"）。一个完整的 Condition_Ind v2 应该是：

```text
[Bar Stream]
   ↓
[Rx 层：原子特征 + 组合 → 复合 Indicator Stream]
   ↓
[MR 层：在 Indicator Stream 上写 PATTERN 做形态识别]
   ↓
[Mining：参数化 Rx pipeline + MR PATTERN 一起搜索]
```

Rx 取代 Condition_Ind 的"组合层"职能；MR 接管"形态匹配"职能；两者互补不冲突。这才是"自然演化方向"的全貌。

---

## 7. 结论一句话

> 对"灵活组合走势特征"这一目标，**Reactive Streams (FRP) 是 7 类范式中唯一能从根本上回答"特征 = 一阶可组合对象"的方案**，也是 Condition_Ind 的最自然演化方向。Behavior Trees 在"等待状态机"和"装饰器复用"上提供互补价值。Parser Combinators 是 MATCH_RECOGNIZE 的代码层等价物，理论上最强但生态最弱。Dataflow Graphs 是执行后端而非组合层。HFSM/Petri/Monadic 不推荐。
>
> **"Condition_Ind v2"的明确路径：用 RxPY-style 的 Observable + 领域 operator 库取代当前的 cond 字典 + Indicator 类**；保留 backtrader 的"指标即一阶对象"心智，获得 50+ operator 的组合代数、offline/live 同代码的开发体验、以及与 dataflow 后端 / MATCH_RECOGNIZE pattern 层的清晰分层。

---

## 8. 引用

- **Py Trees**：`/websites/py-trees_readthedocs_io_en_devel`，关键模块：`composites.Sequence(memory)`、`composites.Selector`、`composites.Parallel`、`decorators`、`Blackboard`。Sequence with memory 实现位于 `_modules/py_trees/composites.html`。
- **RxPY 4.x**：`/reactivex/rxpy`，关键 API：`reactivex.combine_latest`、`ops.with_latest_from`、`ops.window`、`reactivex.compose`(pipe)、`Subject`、Hot vs Cold 章节。
- **Dask**：`/dask/dask`，关键 API：`dask.delayed`、任务图 `visualize()`、Scheduling 章节。
- **前序团队报告**：
  - `docs/research/composite_pattern_architecture.md`
  - `docs/research/_team_drafts/alt_pattern_architectures.md`
