# 怎样声明一个走势模式（Pattern）

## 先搞清楚：这篇文档解决什么问题？

假设你盯着一只股票的 K 线图，心里有一个走势的「故事」想让程序帮你找出来，比如：

> 「先是一段大幅下跌，跌完之后在底部连续几次放量突破，最后一次突破后还回踩确认了一下。」

`path2.dag` 就是让你**用代码把这个故事写下来**，然后让程序在历史行情里自动把符合这个故事的片段全部捞出来。

这篇文档教你怎么把脑子里的「走势故事」翻译成 `path2.dag` 的声明。你不需要预先懂什么「事件框架」「DAG 匹配」之类的理论——我们会从一个最小的例子讲起，边写边解释。

---

## 一分钟建立直觉：几样零件

把一个走势故事拆开看，其实只有这么几种零件：

| 故事里的成分 | 对应的零件 | 一句话说明 |
|------------|-----------|-----------|
| 故事里的「角色」（下跌段、突破点、回踩……） | **`NodeSpec`** | 一个角色：谁来产生这种事件、它要满足什么条件 |
| 某个角色其实是「一串」而不是「一个」（连续多次突破） | **嵌套事件**（推荐）/ **`KleeneSpec`** | 把「一串」打包成一个宽事件、或让节点直接绑一串散点 |
| 对单个角色自身的要求（这段下跌回撤要够大） | **`W.*` 谓词** | 检查角色自己的属性，比如「回撤 ≥ 25%」 |
| 角色之间的先后/包含关系（下跌完才突破） | **类型化边** | 描述两个角色之间的关系，比如「A 结束后 N 根 K 线内出现 B」 |

最后，把这些零件全部装进一个 **`PatternSpec`** 容器里，交给 `analyze()` 去跑，它就会把所有符合的片段还给你。

> 💡 记住这个分工口诀：**节点管「角色自己长什么样」，边管「角色之间什么关系」**。这是整个框架的脊梁，后面反复会用到。

---

## 1. 从最小例子上手

我们先不追求复杂，只表达一个最简单的故事：

> 「一段下跌结束后，1 到 120 根 K 线之内出现一个突破点。」

这里有两个角色（下跌段、突破点）和一条关系（下跌在前、突破在后）。代码长这样：

```python
from path2.dag import (
    NodeSpec, PatternSpec, TemporalEdge,
    where as W, analyze,
)
from path2.atoms.breakout import BODetector
from path2.atoms.trend import TrendSegmentDetector

def build_pattern(params):
    nodes = (
        NodeSpec(
            node_id="down",
            detector=TrendSegmentDetector(**params.trend_kwargs()),
            where=(("regime", W.attr("regime", "==", "down")),),
            label="下跌段",
        ),
        NodeSpec(
            node_id="bo",
            detector=BODetector(**params.bo_kwargs()),
            label="突破点",
        ),
    )
    edges = (
        TemporalEdge("down", "bo", min_gap=1, max_gap=120),
    )
    return PatternSpec(
        pattern_id="my_pattern",
        display_name="示例走势",
        nodes=nodes,
        edges=edges,
        root="bo",
    )

result = analyze(build_pattern(params), df, params)
for m in result.matches:
    print(m.role_index["down"], m.role_index["bo"])
```

哪怕你还没看懂每个字段，也能从结构上读出故事：

- `nodes` 里声明了两个角色：`"down"`（下跌段）和 `"bo"`（突破点）。
- `down` 角色加了一个条件：它的 `regime` 属性必须等于 `"down"`（即这一段确实是下跌）。
- `edges` 里那条 `TemporalEdge("down", "bo", min_gap=1, max_gap=120)` 就是「下跌之后 1–120 根 K 线内出现突破」这层关系。
- 最后装进 `PatternSpec` 交给 `analyze()`，结果里的每个 `m` 就是命中的一个完整片段，`m.role_index["down"]` 取出这次命中里扮演下跌段的那个事件。

> ✅ **你现在应该理解了**：声明一个 pattern = 列出角色（`NodeSpec`）+ 列出角色间的关系（边）+ 装进 `PatternSpec`。接下来我们把每个零件讲透。

---

## 2. `NodeSpec`：声明一个角色

`NodeSpec` 回答的问题是：「这个角色由谁产生？它自己要满足什么条件？」

先看它的全部字段，**不用背，看完下面逐个讲解再回头查**：

```python
@dataclass(frozen=True)
class NodeSpec:
    node_id:          str
    detector:         object
    where:            Tuple[Tuple[str, WherePredicate], ...] = ()
    kleene:           Optional[KleeneSpec] = None
    consumes_stream:  Optional[str] = None
    label:            str = ""
```

下面按「最常用 → 进阶」的顺序讲。

### `node_id` —— 角色的名字

这是角色在整个拓扑里的**唯一名字**。它有两个作用：

1. 你在边里引用角色时用它（比如 `TemporalEdge("down", "bo", ...)` 里的 `"down"`、`"bo"`）。
2. 命中结果里用它来取出对应事件：`m.role_index["down"]`。

💡 **同一种 detector 可以扮演不同角色**，只要给不同的 `node_id` 就行。比如同样是趋势段检测器，一个扮演下跌、一个扮演横盘：

```python
# 两个 TrendSegmentDetector 实例——一个扮演下跌，一个扮演横盘
NodeSpec("down", TrendSegmentDetector(**p.trend_kwargs()),
         where=(("regime", W.attr("regime", "==", "down")),))
NodeSpec("side", TrendSegmentDetector(**p.trend_kwargs()),
         where=(("regime", W.attr("regime", "==", "sideways")),))
```

> 💡 注意上面是**两个独立的** `TrendSegmentDetector` 实例（各 `new` 一个）。它们产出的事件 `class_id` 都是 `"trend"`，`event_id` 前缀会撞。引擎会自动帮你消歧——给它们分别加 `trend0` / `trend1` 前缀。这件事不用你操心，详见后面的 [`source_tag` 自动消歧](#source_tag同类多实例自动消歧) 一节。

> 💡 **面板靠什么认事件类型？** 旧版本 `NodeSpec` 有个 `event_type` 字段专门干这事，现已删除。现在面板上色 / 调试认事件，统一靠 detector 产出事件的 `class_id`（`detector.event_cls.class_id`，`to_topology()` 直接读它），不再需要你手填类型名。

### `detector` —— 谁来产生这种事件

填一个 detector 实例（实现了 `Detector` 协议的生产者）。引擎会**自动**调用它来产生候选事件流。

⚠️ **常见坑：不要自己手动跑 detector**。引擎会按依赖顺序帮你编排好，你只管把 detector 实例交给 `NodeSpec`：

```python
# 错误：不要手动 run
events = list(run(BODetector(**p.bo_kwargs()), df))

# 正确：交给 NodeSpec，引擎自动编排
NodeSpec("bo", BODetector(**p.bo_kwargs()))
```

### `where` —— 对这个角色「自己」的要求

这是最常用的字段之一。它的作用是：**过滤掉不符合条件的候选事件**，只保留满足要求的。

格式是一串 `(clause_id, fn)` 元组，多条之间是「且（AND）」的关系——必须全部满足：

```python
where=(
    ("drought_ok", W.attr("drought", ">=", 60)),
    ("vol_ok",     W.attr("vol_ratio", ">=", 2.0)),
)
```

- `clause_id`（如 `"drought_ok"`）是你给这条约束起的名字，纯粹用于诊断——命中后你能在 `predicate_trace` 里按这个名字查「这条约束过没过」。**同一个 node 内 `clause_id` 必须唯一**：它是诊断结果里的 key，重名会互相覆盖，所以 `PatternSpec` 构造时就会抛 `ValueError` 拦下；不同 node 之间可以重名。
- `fn` 是实际的判断函数，通常用下一章讲的 `W.*` 工厂来生成。

⚠️ **划重点：`where` 只能看角色「自己」的属性，不能看跨角色的关系**。「这段下跌的回撤够不够大」是看自己，可以放 `where`；「下跌和突破之间隔了几根 K 线」是跨角色关系，必须用边来表达（见第 7 节）。这正是前面那句口诀——节点管自己，边管关系。

默认值 `()` 表示不加任何约束，接受所有候选。

> 💡 关于 `fn` 的签名：每个 `fn` 形如 `(event_or_seq, ctx) -> bool`。对普通节点，第一个参数是单个事件；对 Kleene 节点（§4 讲），第一个参数是整串事件。绝大多数情况你不用关心这个细节，因为 `W.*` 已经帮你封装好了。

### `kleene` —— 这个角色是「一串」吗？

默认 `None`，表示这个角色是「一个」事件。如果这个角色实际上是「一串连续同类事件」（比如「连续多次突破」），有两种表达办法：优先把这一串聚合成**嵌套事件**（推荐，见 §3），或者在这里填一个 `KleeneSpec` 让节点直接绑一串散点（见 §4）。

### `consumes_stream` —— 这个 detector 吃哪份数据？

默认 `None`，表示 detector 直接消费原始行情 `df`。

但有些 detector 需要「先有别的事件才能工作」。典型例子：识别「回踩」的 `ThrowbackDetector` 必须先知道突破点在哪，才能判断价格有没有回踩到突破位。这时就让它消费**上游节点产出的事件流**——把 `consumes_stream` 填成那个上游节点的 `node_id`：

```python
NodeSpec(
    "tb",
    ThrowbackDetector(**p.throwback_kwargs()),
    consumes_stream="bo",   # 消费 bo 节点的事件流，而不是原始 df
    label="回踩确认",
)
```

💡 你只需要声明这一行依赖关系，引擎就会自动算出「得先跑 bo、再跑 tb」的执行顺序，不用你操心。

### `label` —— 给人看的名字

人类可读的名称，用于面板显示和调试，对匹配逻辑没有任何影响。默认空字符串。建议都填上，调试时一目了然。

### `source_tag`：同类多实例自动消歧

> ℹ️ **注意它不是 `NodeSpec` 字段**（所以没出现在上面那张字段表里），而是 **detector 实例上的字段**。放在这一节讲，只是因为它紧接着上面「一身多角」的话题。

这一段讲一个你**不用自己动手、但最好知道**的机制，免得调试时被 `event_id` 搞糊涂。

先说问题。前面提过「一身多角」——同一个 detector 类可以扮演多个角色。比如 `down` 和 `side` 各自 `new` 一个 `TrendSegmentDetector`：

```python
down_det = TrendSegmentDetector(**p.trend_kwargs())
side_det = TrendSegmentDetector(**p.trend_kwargs())   # 两个独立实例
```

每个事件都有一个全局唯一的 `event_id`，它由「前缀 + 区间」拼成，前缀默认取事件的 `class_id`。麻烦在于：这两个实例产出的事件 `class_id` 都是 `"trend"`，于是两段恰好落在同一区间的下跌/横盘事件，`event_id` 就会**撞**（框架要求全局唯一，撞了会出问题）。

`source_tag` 就是为此准备的「前缀替身」——它是 detector 实例上的一个钩子，用来给这个实例的 `event_id` 换一个专属前缀（默认 `None` 时回退用 `class_id`）。

你**通常不用手动设**它。引擎在跑流之前会自动做一步消歧（`assign_auto_source_tags`）：

- 发现同一个 `class_id` 底下挂着**两个或更多不同的 detector 实例**时，
- 按它们在 `nodes` 里**首次出现的顺序**，给还没手动设过 `source_tag` 的实例，依次填上 `trend0` / `trend1` / …

于是上面那个例子里，`down` 产出的事件前缀变成 `trend0`、`side` 的变成 `trend1`，`event_id` 不再相撞。

> 💡 几个让你放心的细节：
> - **单实例 / 共享同一个对象 / 你已手动命名过** 的情况，引擎一律不碰——`event_id` 逐字保持原样（向后兼容），而且这步是幂等的。
> - 万一某个 detector 出现了多实例、却没有 `source_tag` 这个钩子，引擎会**直接报错**提醒你，而不是悄悄撞 `id`。

> ✅ **一句话总结 `NodeSpec`**：`node_id` 是角色名，`detector` 是事件来源，`where` 是对角色自己的过滤条件，`kleene` 决定它是一个还是一串，`consumes_stream` 决定它吃原始数据还是上游事件流，`source_tag`（一般自动）保证同类多实例不撞 `event_id`。

---

## 3. 当一个角色是「一串」事件——优先用嵌套事件

有时候一个角色天然就不是「一个点」，而是「一连串」。最典型的就是「**连续多次突破**」——你关心的不是某一次突破，而是「短时间内密集出现的好几次突破」这个整体。

path2 有两种表达「一串」的办法：

- **嵌套事件（推荐，本节讲）**——把「这一串」打包成**一个一等公民的宽事件**，让它像普通节点一样参与匹配。当前示例 app `bottom_breakout_burst` 走的就是这条路。
- **Kleene（仍是框架特性，下一节讲）**——让一个节点直接绑「一整串散点事件」，在求解期把序列拼出来。

> 💡 **怎么选？** 如果这一串能自然聚合成一个「有头有尾、有整体属性」的东西（比如「一段突破爆发」），优先用**嵌套事件**——它能被画在图上、被一条 `where` 整体检查、被边当作普通宽事件引用，最干净。只有当你确实想保留「松散的一串散点、连整体实体都不想造」时，才用 Kleene。

### 嵌套事件：让「这一串」变成一个实体

先讲为什么。以前在框架里，「一串突破点」只是一个 Kleene 节点绑着一串散落的 `bo`——**没有任何一个东西代表「这一串」本身**。你想问「这串突破一共涉及几个不同的峰」「这串里最大的成交量比是多少」，都得在求解期把整串遍历一遍才能算。

**嵌套事件**换了个思路：直接造一个新事件，让它把「这一串」装进自己肚子里。在示例 app 里，这个事件叫 `BurstEvent`（「突破爆发」）：

- 它是个**宽事件**：`start_idx` = 串里第一个 `bo` 的起点，`end_idx` = 串里最后一个 `bo` 的终点；
- 它内部用一个 `members` 字段，装着组成它的那一串 `BOEvent`（存的是完整事件对象，不是 id）；
- 它在**被检测出来的那一刻**，就顺手把几个整体属性算好、存成自己的普通字段：`count`（几个 bo）、`distinct_pk`（一共突破了几个不同的峰）、`max_vol_ratio`（最大成交量比）、`first_drought`（串首那个 bo 的干旱度）。

好处立竿见影：因为整体属性已经是它**自己的字段**了，写 `where` 时直接用最基础的 `W.attr` 读就行，不用任何「序列聚合」谓词：

```python
# burst 节点的 where 就是三条普通 W.attr（直读 BurstEvent 预算字段）
where=(
    ("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),  # 串首 drought
    ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),        # 累计突破几个不同峰
    ("vol_spike",     W.attr("max_vol_ratio", ">=", params.THR_VOL)),       # 最大成交量比
)
```

而且因为 `BurstEvent` 是个正常的宽事件，边可以直接连到它本体（`down→burst`、`side→burst`、`burst→tb`），不用再纠结「这串拿头还是拿尾去算关系」。

### 谁来造 `BurstEvent`？——`BurstDetector`

`BurstEvent` 不是凭空冒出来的，由一个专门的 detector 切串聚合而成：`BurstDetector`。它的工作方式很直接：

- **消费 `bo` 流**（`consumes_stream="bo"`，遵守独立性原则——它不自己 `new` 一个 `BODetector`，而是吃上游 `bo` 节点产出的事件流）；
- 把密集的 `bo` 切成一段一段「极大段」，每段打包成一个 `BurstEvent`；
- 切串口径是「贪心极大段」：按起点排序后单向扫，每个未消费的 `bo` 作段首，吸纳所有「起点距段首 ≤ `max_span`」的后续 `bo`，吃到不能再吃为止、不回头。

切串用到两个参数，它们走 **detector 的构造函数**（不是 `where`）：

```python
BurstDetector(
    max_span=params.burst_max_span,   # 成簇窗口：成员起点距段首 ≤ max_span
    min_bos=params.MIN_BOS,           # 段长下界：少于这么多个 bo 的段直接丢弃
)
# 实际写法用 params.burst_kwargs() 一把闭合上面两个参数
```

> ⚠️ **划清界限：什么走构造函数、什么走 `where`。** `max_span` / `min_bos` 是「怎么切串」的参数，走构造函数；而 `THR_DROUGHT` / `THR_PK` / `THR_VOL` 这些**阈值**是「切出来的串够不够格」的过滤条件，走 `burst` 节点的 `where`（如上）、**不传给 detector**。detector 只负责切串 + 算好那几个预算字段，把阈值判断留给 `where`。

### 任何事件都能嵌套：`Event` 基类的嵌套协议

嵌套不是 `BurstEvent` 专属的特例，而是 `Event` 基类提供的一套**通用协议**。任何事件想「装下别的事件」，覆写这几个方法即可：

- `child_slots()` —— 返回构成本事件的主要子事件（`BurstEvent` 返回 `{"members": (...)}`）。用于遍历 / 展平。
- `child(name)` —— 按名字取**单个**子事件。`BurstEvent` 支持 `child("first_bo")` / `child("last_bo")`，给边端点、selector 用。
- `children(name)` —— 按名字取**一组**子事件（`children("members")`）。
- `descendant_leaves` —— 递归展平，一直挖到没有子事件的原子事件为止。

> 💡 **这是「新增」、不是「改动」。** 叶子事件（像 `BOEvent` 这种最底层的原子事件）这几个方法都用基类默认实现——`child_slots()` 返回空、`child()/children()` 抛 `KeyError`，**行为完全不变**。只有 `BurstEvent` 这种 composite 事件才去覆写它们。`Event` 的核心三字段（`event_id`/`start_idx`/`end_idx`）一个没动。

---

## 4. `KleeneSpec`：另一条路——让节点直接绑「一串散点」

> ⚠️ **先读这里。** 当前示例 app `bottom_breakout_burst` 已经**改用上一节的嵌套事件**（`BurstEvent`）表达突破串，**不再用 Kleene**。但 Kleene **仍然是框架的完整特性、随时可用**——`KleeneSpec`、引擎的序列绑定、后面附录里那些 `W.first/last/count/any/distinct/reduce` 谓词全都健在。本节作为 **reference** 保留：如果你的「一串」不方便聚合成一个一等事件、就是想让一个节点直接绑一串散点，那就用 Kleene。**「某个 app 不用它」绝不等于「框架删了它」。**

### 什么场景需要它？

`KleeneSpec` 用来表达「一个节点绑一整串散点事件」。打个比方：普通节点像是从人群里挑出「一个人」，Kleene 节点像是挑出「一支连续走过来的队伍」，并把整支队伍当成一个整体来看待。

> 💡 「Kleene」这个名字来自正则表达式里的「Kleene 闭包」（就是那个表示「重复若干次」的 `*`）。你可以把它理解成「这个角色重复出现 N 次」。

引擎会从事件流里抠出一段满足约束的**连续子序列**，把**整段当作一个绑定单元**参与后续匹配。这带来一个重要后果：命中结果里，Kleene 节点对应的值是 `Tuple[Event, ...]`（一串），而不是单个事件。

### 它的字段

```python
@dataclass(frozen=True)
class KleeneSpec:
    min_count:          int = 1
    max_count:          float = math.inf
    span_from_first:    Optional[Tuple[int, float]] = None
    aggregate_where:    Tuple[Tuple[str, Callable[[Tuple, MatchContext], bool]], ...] = ()
    endpoint_for_edges: str = "first"
    greedy:             bool = True
```

下面逐个讲，依然按「最常用 → 进阶」排。

### `min_count` / `max_count` —— 这串至少 / 至多几个？

序列的数量下界（含）和上界（含）。`max_count` 默认 `math.inf`，即不限上限。

```python
# 至少 3 次突破，不限上限
KleeneSpec(min_count=3)

# 恰好 2–5 次突破
KleeneSpec(min_count=2, max_count=5)
```

### `span_from_first` —— 这串要「成簇」、不能拖太长

光「至少 3 次」还不够——如果这 3 次突破横跨半年，那根本不算「连续爆发」。`span_from_first` 就是给这串加一个**时间跨度窗口**，强制它们挤在一起。

格式是 `(lo, hi)`。引擎接纳一个新成员 `e` 的条件是：

```
e.start_idx − seq[0].start_idx ∈ [lo, hi]
```

⚠️ **注意锚点是「段首」`seq[0]`，不是相邻的前一个**。也就是说，所有成员都得离「第一个成员」不超过 `hi` 根 K 线，而不是「每个离前一个不超过 `hi`」。`None` 表示不约束跨度。

```python
# 所有突破点都必须距离首个突破点 20 根 K 线以内（挤成一簇）
KleeneSpec(min_count=3, span_from_first=(0, 20))
```

### `aggregate_where` —— 对「整串」的要求

`where` 看的是单个事件，而 `aggregate_where` 看的是**整串的统计性质**。比如「这串突破里，最大成交量比要超过 3」「累计突破了至少 3 个不同的峰」——这些都是要把整串看完才能算出来的。

格式和 `NodeSpec.where` 一样：`(clause_id, fn)` 的列表，AND 合取。区别在于这里的 `fn` 第一个参数永远是整串 `Tuple[Event, ...]`，所以要配合下一章里那些「吃序列」的 `W.*`（`W.count` / `W.any` / `W.distinct` / `W.reduce`）使用。

```python
KleeneSpec(
    min_count=3,
    aggregate_where=(
        ("distinct_pk", W.distinct("broken_peak_ids", ">=", 3)),   # 至少突破了 3 个不同峰
        ("vol_spike",   W.any("vol_ratio", ">=", 3.0)),            # 至少一次成交量 spike
    ),
)
```

> 💡 **`where` 还是 `aggregate_where`，怎么选？**
> - 你想看「这串的**第一个 / 最后一个**事件的某个属性」→ 放 `NodeSpec.where`，用 `W.first` / `W.last`。
> - 你想看「这串**整体**的统计性质」（数量、去重计数、是否存在某种事件、聚合值）→ 放 `aggregate_where`。
>
> 求值时机也不同：`where` 在组装序列的过程中逐轮过滤；`aggregate_where` 在整串确定后才执行一次。

### `endpoint_for_edges` —— 这串跟外面连边时，用头还是用尾？

进阶字段。当一条边连到这个 Kleene 节点时，引擎得拿这串里的**某一个事件**去算边的关系（一串没法整体参与「相隔几根 K 线」这种点对点的计算）。这个字段就是选「用哪个端点」：

- `"first"`（默认）：取**序列第一个**。适合「锚头部」的边。比如「下跌段 → 突破串」这条入边，关心的是下跌完到**第一次**突破隔多远。
- `"last"`：取**序列最后一个**。适合「锚尾部」的边。比如「突破串 → 回踩」这条出边，回踩当然是在**最后一次**突破之后才发生。

```python
# bo 串：出边（bo→tb）要锚在串尾——最后一次突破之后才回踩
KleeneSpec(
    min_count=3,
    span_from_first=(0, 20),
    endpoint_for_edges="last",
)
```

### `greedy` —— 尽量多吃还是够了就停？

- `True`（默认）：贪心，尽可能把这串延伸到最长（对标正则里的贪心量词）。
- `False`：最小满足，一旦达到 `min_count` 就停。

通常保持默认 `True` 即可。

> ✅ **一句话总结 `KleeneSpec`**：当一个角色是「连续一串」时用它，`min_count`/`max_count` 管数量、`span_from_first` 管「成簇别拖太长」、`aggregate_where` 管整串的统计条件、`endpoint_for_edges` 管这串跟外面连边时用头还是用尾。

---

## 5. `W.*` 谓词：怎么写「条件」

### 它是什么？

前面 `where` 和 `aggregate_where` 都需要你提供一个判断函数 `fn`。`W.*` 就是一组**帮你生成这些判断函数的工厂**。你写 `W.attr("drought", ">=", 60)`，它就返回一个「检查事件的 drought 属性是否 ≥ 60」的函数。

用法上推荐 `import path2.dag.where as W`，然后 `W.attr(...)` 这样调用。`path2.dag.where` 一共提供 10 个工厂函数。

> 💡 **省心的 None 安全语义**：所有 `W.*` 谓词在遇到属性值是 `None`（比如某个 Optional 字段没赋值，像 `BOEvent.drought` 可能为空）时，会**安全返回 `False`**，而不会抛 `TypeError`。等价于你手写 `x is not None and x >= thr` 的短路写法——但你不用自己写了。

我们按「先学会单个事件的，再学会整串的」顺序来。

### 5.1 给普通节点用的：`W.attr`

#### `W.attr(name, op, thr)` —— 检查单个事件的某个属性

这是最基础、最常用的一个。断言 `e.<name> op thr`，即「事件的 name 属性 与阈值 thr 满足 op 关系」。

`op` 的合法取值：`">="` `">"` `"<="` `"<"` `"=="` `"!="`（传别的会在构造时抛 `ValueError`）。

```python
# 突破点的 drought（干旱度）至少 60 根 K 线
W.attr("drought", ">=", 60)

# 趋势段的 regime 等于 "down"
W.attr("regime", "==", "down")

# 下跌段回撤幅度至少 25%
W.attr("drawdown", ">=", 0.25)
```

放进 `NodeSpec.where` 的样子：

```python
NodeSpec(
    "down",
    TrendSegmentDetector(**p.trend_kwargs()),
    where=(
        ("regime",   W.attr("regime", "==", "down")),
        ("drawdown", W.attr("drawdown", ">=", p.pred4_min_drawdown)),
    ),
)
```

> ✅ 只要你先掌握 `W.attr`，就已经能写出大部分单事件的过滤条件了。下面是给「一串」用的，等你真要写 Kleene 节点时再细看。

### 5.2 给 Kleene 节点用的（序列聚合谓词）

> 💡 下面这几个谓词专门服务 [Kleene 路径](#4-kleenespec另一条路让节点直接绑一串散点)——它们的 `fn` 都吃整串 `seq`。如果你用的是上一章的**嵌套事件**（`BurstEvent`），整串属性已经预算成宽事件的普通字段了，直接 `W.attr` 读即可，**用不到这一组**。这一组留给真用了 `KleeneSpec` 的场景。

这几个的 `fn` 都吃整串 `seq`，所以多数用在 `KleeneSpec.aggregate_where` 里（`W.first`/`W.last` 例外，见下）。

#### `W.first(name, op, thr)` —— 看串里第一个事件的属性

断言 `seq[0].<name> op thr`。用来约束「这串的开头长什么样」，比如「首次突破的 drought 要达标」。None 安全。

注意：虽然它吃整串，但它语义上是「过滤串首属性」，所以**放在 `NodeSpec.where` 里**：

```python
W.first("drought", ">=", 60)

NodeSpec(
    "bo",
    BODetector(**p.bo_kwargs()),
    where=(("first_drought", W.first("drought", ">=", p.THR_DROUGHT)),),
    kleene=KleeneSpec(min_count=3),
)
```

#### `W.last(name, op, thr)` —— 看串里最后一个事件的属性

断言 `seq[-1].<name> op thr`。约束「这串的结尾长什么样」。None 安全。同样放在 `NodeSpec.where`。

```python
# 突破串的最后一个突破点 vol_ratio 必须 >= 1.5
W.last("vol_ratio", ">=", 1.5)
```

#### `W.count(op, thr)` —— 看这串有多少个

断言 `len(seq) op thr`。这是「数量」约束的**另一种写法**，跟 `KleeneSpec.min_count` 作用重叠。

```python
# 序列长度 >= 3（等价于 KleeneSpec.min_count=3）
W.count(">=", 3)
```

> 💡 `KleeneSpec.min_count` 是引擎层的数量约束，`W.count` 是谓词层的数量约束，两者都生效，**一般二选一即可**。当你想把数量约束和别的聚合条件并排写在 `aggregate_where` 里时，用 `W.count` 比较顺手。

#### `W.any(name, op, thr)` —— 这串里「至少有一个」满足

断言序列中**至少一个**元素满足 `e.<name> op thr`（即 ∃ e ∈ seq）。用于「至少有一次满足某条件」。None 安全。

```python
# 突破串中至少一次突破的成交量比 >= 3.0
W.any("vol_ratio", ">=", 3.0)

KleeneSpec(
    min_count=3,
    aggregate_where=(
        ("vol_spike", W.any("vol_ratio", ">=", p.THR_VOL)),
    ),
)
```

#### `W.distinct(name, op, thr)` —— 这串一共涉及多少个「不同的」值

把序列里所有元素的 `e.<name>` 收集起来去重，然后断言「去重后的数量 op thr」。

💡 当属性值本身是 `tuple` / `list` / `set` 时会自动**展平（flatten）**。典型用途：`BOEvent.broken_peak_ids` 是一个 tuple（一次突破可能突破多个峰），用 `W.distinct` 就能问「这串突破累计突破了至少 N 个不同的峰」：

```python
# 突破串中累计突破了至少 3 个不同峰值
W.distinct("broken_peak_ids", ">=", 3)

KleeneSpec(
    min_count=3,
    aggregate_where=(
        ("distinct_pk", W.distinct("broken_peak_ids", ">=", p.THR_PK)),
        ("vol_spike",   W.any("vol_ratio", ">=", p.THR_VOL)),
    ),
)
```

#### `W.reduce(name, fn, op, thr)` —— 先聚合成一个数，再比较

先提取 `[e.<name> for e in seq]`，用你给的 `fn` 归约成一个标量，再断言 `fn(values) op thr`。适合 `max` / `sum` / `min` / 均值这类「先算个总数 / 极值再比」的场景。比较阶段 None 安全。

```python
import statistics

# 突破串中 vol_ratio 的最大值 >= 4.0
W.reduce("vol_ratio", max, ">=", 4.0)

# 突破串中 vol_ratio 的平均值 >= 2.0
W.reduce("vol_ratio", statistics.mean, ">=", 2.0)

# 突破串中 drought 之和 >= 200
W.reduce("drought", sum, ">=", 200)
```

### 5.3 组合用的：`W.all`

#### `W.all(*fns)` —— 把多个条件并成一个

把多个 `WherePredicate` 用短路 AND 合成一个谓词。相当于把好几条 `where` 子句揉成一条的语法糖。

主要用途：当某个**槽位只能放一个谓词**、但你想塞多个条件时（比如 `aggregate_where` 的某个 slot 里）：

```python
from path2.dag import where as W

KleeneSpec(
    min_count=3,
    aggregate_where=(
        ("combined", W.all(
            W.distinct("broken_peak_ids", ">=", 3),
            W.any("vol_ratio", ">=", 3.0),
        )),
    ),
)
```

💡 在 `NodeSpec.where` 里其实直接列多个 tuple 更易读，没必要硬用 `W.all`。

---

### 5.4 嵌套事件专用：`W.child` / `W.children`

这两个是给[嵌套事件](#嵌套事件让这一串变成一个实体)用的「**钻进子事件里检查**」组合子。

平时 `W.attr("count", ...)` 读的是事件**自己**的字段。但有时你想让父事件的 `where` 去检查它**某个命名 child** 的属性——比如「这串 burst 的**第一个 bo**（`first_bo`）的 drought 要 ≥ 60」。这就是 `W.child`：

```python
# 父事件命名 child "first_bo" 的 drought >= 60
W.child("first_bo", W.attr("drought", ">=", 60))
```

它做的事很简单：把内层谓词（这里是 `W.attr("drought", ">=", 60)`）作用到 `event.child("first_bo")` 取出的那个子事件上。内层可以是任何现有的一元谓词。

`W.children` 则是「对**一组** child 做聚合检查」——把一个序列聚合谓词（如 `W.distinct` / `W.any` / `W.count`）作用到 `event.children(key)` 取出的那一组子事件上：

```python
# 对父事件的 "members" 这组 child 做 distinct 计数
W.children("members", W.distinct("broken_peak_ids", ">=", 3))
```

> 💡 **什么时候才用它？** 在示例 app 里，`BurstEvent` 已经把 `first_drought` / `distinct_pk` 这些整体属性**预算成自己的普通字段**了，所以直接 `W.attr` 读最省事，用不到 `W.child`/`W.children`。这两个组合子是为「子事件属性没被预算成父字段、必须现场钻进去算」的更一般场景准备的。

---

### 5.5 进阶：便利层覆盖不到的「跨字段计算」怎么办

前面的 `W.*` 全是「**单**字段 op 阈值」——`W.attr("drawdown", ">=", 0.25)` 只比较一个字段。但有时你的条件要**拿同一个事件的好几个字段做运算、再比较**。

举个例子（下面的 `drawup` 字段是假设的，只为说明形态）：假设某个趋势事件除了 `drawdown`（回撤）还带一个 `drawup`（涨幅），你想表达「**净涨幅 = 涨幅 − 回撤，要大于 0.2，且这段是上涨**」：

```python
(e.drawup - e.drawdown) > 0.2 and e.regime == "up"
```

`W.*` 里**没有**这种「跨字段算术」的现成工厂——这是有意为之：算术是个无底洞（`a-b` 之后就是 `(a-b)/c`、`max(a,b)-min(c,d)`……），便利层只保留一组封闭的常用约束，不做成完整表达式语言。遇到这种需求，有两条路。

#### 方案 A：手写一个谓词（lambda 或函数）

`where` 的每一项，本质就是一个 `(event_or_seq, ctx) -> bool` 函数（见 §9），`W.*` 只是帮你**生成**这种函数的工厂。工厂不够用时，自己写一个即可，还能和 `W.*` 无缝混用：

```python
from path2.dag import where as W

NodeSpec(
    "up",
    TrendSegmentDetector(...),
    where=(
        ("regime",   W.attr("regime", "==", "up")),                 # 现成工厂能表达的，照用
        ("net_move", lambda e, ctx: (e.drawup - e.drawdown) > 0.2), # 跨字段算术，手写 lambda
    ),
)
```

几个要点：
- 第一个参数 `e` 就是待判定的事件（Kleene 节点则是整串 `seq`），直接读它的字段做任意运算。
- 第二个参数 `ctx` 这里**用不到**——你只读事件**自己的字段**，既不回看 K 线也不读动态阈值。但签名必须带上它（引擎统一按 `fn(e, ctx)` 调用）；用不到，放着不碰就行。
- 这样写**完全合规**：你只读了事件自己的字段，没去碰别的角色（没读 `ctx.bound`），没越过「一元约束只看自己」那条红线。

> ⚠️ 一个小代价：手写谓词在 `predicate_trace` 里只会留下一个「过 / 没过」的布尔值，**看不到 `drawup - drawdown` 到底算出来是多少**。要是你排查时想看到这个中间量，用下面的方案 B。

#### 方案 B：把派生量「升级」成事件的正式字段（推荐用于有业务含义的量）

如果 `drawup - drawdown` 是个**有名字、会反复用到**的业务概念（比如就叫「净涨幅 `net_move`」），更好的做法不是每次在 `where` 里现算，而是让**产生这个事件的 detector 在落地时就把它算好、写成事件的一个正式字段**。path2 的事件遵循「**事件一旦落地，所有字段就都已算完**」的约定（具体数值计算可借助 `path2.calc` 工具箱，见 building-blocks 指南）。

这样 `where` 就回到清清爽爽的声明式：

```python
# 前提：detector 落地 TrendSegment 时，已把 net_move 算好写进字段
where=(
    ("regime",   W.attr("regime",   "==", "up")),
    ("net_move", W.attr("net_move", ">",  0.2)),   # 又变回一句 W.attr
)
```

方案 B 的好处：
- **可复用**：任何节点都能直接 `W.attr("net_move", ...)`，不用到处重抄算式。
- **可追溯**：`net_move` 是正式字段，会出现在事件上，也能在 `predicate_trace`、面板里看到它的实际数值。
- **声明式**：`where` 保持「单字段比较」的统一风格，一眼就读懂。

#### 怎么选？

| 你的情况 | 用哪个 |
|---------|--------|
| 一次性、探索性的临时条件，没什么复用价值 | 方案 A（手写 lambda），最省事 |
| 有业务名字、会反复用、想在诊断 / 面板里看到这个量的值 | 方案 B（提为字段），最干净 |

一条经验法则：**要是同一个算式在好几处都靠手写 lambda 重复出现，那就是信号——该把它升级成事件的正式字段了（方案 B）。**

---

## 6. 速查：哪种约束放哪里、用哪个谓词

写多了你会越来越熟，但刚上手时可以对着这张表归位。这一节就是给你查的——**先理解前几节，再来查这张表**。

| 你想表达的约束 | 放在哪里 | 推荐谓词 |
|----------|----------|----------|
| 单个事件的属性过滤（普通节点） | `NodeSpec.where` | `W.attr` |
| 「一串」的整体属性（已聚合成嵌套事件字段，**推荐**） | `NodeSpec.where` | `W.attr`（直读 `count`/`distinct_pk`… 等预算字段） |
| 钻进某个命名 child 检查它的属性（嵌套事件） | `NodeSpec.where` | `W.child` / `W.children` |
| 一串里「第一个」事件的属性（Kleene 路径） | `NodeSpec.where` | `W.first` |
| 一串里「最后一个」事件的属性（Kleene 路径） | `NodeSpec.where` | `W.last` |
| 一串的数量约束（Kleene 路径） | `KleeneSpec.min_count` 或 `aggregate_where` 里 `W.count` | — |
| 一串里「至少一个」满足某条件（Kleene 路径） | `KleeneSpec.aggregate_where` | `W.any` |
| 一串涉及多少「不同的」值（Kleene 路径） | `KleeneSpec.aggregate_where` | `W.distinct` |
| 一串聚合成一个数后再比较（Kleene 路径） | `KleeneSpec.aggregate_where` | `W.reduce` |
| 把多条谓词合并成一条 | 任意位置 | `W.all` |
| 跨字段算术运算（如 `a - b > 阈值`） | `NodeSpec.where` | 手写 lambda，或把派生量提为事件字段（见 §5.5） |

> 💡 **经验法则**：「一串」的整体属性，优先做成**嵌套事件**的预算字段、用 `W.attr` 直读（最干净）；只有走 Kleene 路径、必须在求解期对序列现场聚合时，才用 `W.first/last/count/any/distinct/reduce` 这组序列谓词。后者里 `NodeSpec.where` 是「逐个候选过滤」，`aggregate_where` 是「整串确定后才算一次」。

---

## 7. 类型化边：声明角色之间的关系

前面讲的都是「角色自己」。现在讲角色**之间**的关系——这正是边的职责。

边描述「两个角色之间存在什么关系」，常见的有这几种：

- **`TemporalEdge`（时序边）**：表达「先后 + 间隔」。比如 `TemporalEdge("down", "burst", min_gap=1, max_gap=120)` 意思是「down 结束后，相隔 1 到 120 根 K 线内出现 burst」。
- **`ContainmentEdge`（包含边）**：表达「一个**整体**落在另一个的区间内」——要求小事件的起点**和终点**都落在大事件区间内（`dst.start >= src.start` 且 `dst.end <= src.end`）。
- **`StartContainmentEdge`（起点包含边）**：只要求小事件的**起点**落进大事件区间（`src.start <= dst.start <= src.end`），**不管小事件的终点**落在哪。

> 💡 **`ContainmentEdge` 和 `StartContainmentEdge` 差在哪？** 前者要求小事件**整段**被包住，后者只盯着小事件的**起点**。什么时候用后者？当小事件是个**宽事件、可能比大事件还长**、但你只关心「它从哪儿开始」时。示例 app 的 `side→burst` 就是这种情况：`burst` 是个宽事件（从首 bo 起点延伸到末 bo 终点），它末尾可能伸出横盘段之外；我们真正想表达的只是「这串突破**从横盘段里开始**」，所以用 `StartContainmentEdge("side", "burst")`。如果误用 `ContainmentEdge`，就会额外要求「末 bo 也落在横盘段内」，凭空收紧条件、改变命中结果。

> 💡 边只描述关系、不重复角色本身的条件。「这段下跌回撤够不够大」是角色自己的事（放 `where`）；「下跌和突破隔多远」才是边的事。再次呼应那句口诀：**节点管自己，边管关系**。

> 💡 当边连到一个 **Kleene 节点**（而非普通节点或嵌套宽事件）时，引擎会用前面讲的 `endpoint_for_edges` 来决定拿这串的头还是尾去算关系。注意这只在 Kleene 路径下触发——示例 app 的 `burst` 是个嵌套**宽事件**、有自己的 `start`/`end`，边直接连它本体，不走 `endpoint_for_edges`。

---

## 8. 完整声明示例：把上面所有零件拼起来

下面是一个真实走势 `bottom_breakout_burst`（底部反转突破爆发）的完整声明。它把 7 条业务约束全部写成了纯声明，用的就是上一章的**嵌套事件**路径。你现在应该能逐行读懂它了——注释里标了每行对应第几条约束：

```python
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, StartContainmentEdge
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.trend import TrendSegmentDetector
from path2.atoms.throwback import ThrowbackDetector

def build_pattern(params):
    down_det = TrendSegmentDetector(**params.trend_kwargs())
    side_det = TrendSegmentDetector(**params.trend_kwargs())   # down/side 各持独立实例
    nodes = (
        # bo：孤立的「密度流源层」——无 where、无边。
        #     既给 burst/tb 当输入流，又能独立扫描渲染（详见 §8 后面的说明）。
        NodeSpec(
            "bo",
            BODetector(**params.bo_kwargs()),
            label="突破点",
        ),
        # 约束④：前置下跌段（大幅回撤）
        NodeSpec(
            "down",
            down_det,
            where=(
                ("regime",   W.attr("regime",   "==", "down")),
                ("drawdown", W.attr("drawdown", ">=", params.pred4_min_drawdown)),
            ),
            label="下跌段",
        ),
        # 约束①：横盘背景段
        NodeSpec(
            "side",
            side_det,
            where=(("regime", W.attr("regime", "==", "sideways")),),
            label="横盘段",
        ),
        # 约束②③⑤⑥：突破爆发（BurstDetector 消费 bo 流，聚合成嵌套 BurstEvent）
        NodeSpec(
            "burst",
            BurstDetector(**params.burst_kwargs()),   # ② 切串下界 min_bos=MIN_BOS 在此生效
            where=(
                ("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),  # ③ 串首 drought
                ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),        # ⑤ 累计突破几个不同峰
                ("vol_spike",     W.attr("max_vol_ratio", ">=", params.THR_VOL)),       # ⑥ 最大成交量比
            ),
            consumes_stream="bo",
            label="突破爆发",
        ),
        # 约束⑦：末突破后回踩确认（消费 bo 流，吃 BOEvent）
        NodeSpec(
            "tb",
            ThrowbackDetector(**params.throwback_kwargs()),
            consumes_stream="bo",
            label="回踩确认",
        ),
    )
    edges = (
        # ④ 下跌段结束后 1–lookback 根 K 线内出现 burst
        TemporalEdge("down", "burst", min_gap=1, max_gap=params.pred4_lookback_bars),
        # ① burst.start（=首 bo 起点）落在横盘段区间内
        StartContainmentEdge("side", "burst"),
        # ⑦ burst 结束后第 1 根 K 线开始回踩（burst.end = 末 bo 终点）
        TemporalEdge("burst", "tb", min_gap=1, max_gap=1),
    )
    return PatternSpec(
        pattern_id="bottom_breakout_burst",
        display_name="底部反转突破爆发",
        nodes=nodes,
        edges=edges,
        root="burst",   # root 是退化字段、引擎不读，填任一合法 node_id 即可
    )
```

逐条对照一下 7 条约束的归宿，能看清「嵌套事件」把活儿分得多干净：

- **②**「至少 MIN_BOS 次突破」= `BurstDetector` 的切串下界 `min_bos`（构造参数，由 `burst_kwargs()` 闭合）。
- **③⑤⑥**「串首 drought / 累计不同峰 / 最大成交量比」= `burst` 节点三条普通 `W.attr`，直读 `BurstEvent` 预算好的字段。
- **①④** = 连到 `burst` 本体的两条边（`StartContainmentEdge` / `TemporalEdge`）+ `down`/`side` 各自的 `where`。
- **⑦** = `burst→tb` 的时序边。

> 💡 **`bo` 这个孤立节点是干嘛的？** 你会注意到 `bo` 节点既没有 `where`、也没有任何边连它——它是个**孤立 role**，只当「密度流源层」：一方面给 `burst`（切串）和 `tb`（评回踩）当输入流（它们都 `consumes_stream="bo"`），另一方面可以被独立扫描、把整条 K 线上的所有突破点都画出来。但因为它不参与任何形态约束，`analyze` 在出口会**自动把「只含 bo 这一个角色」的残缺命中丢掉**（这些是语义垃圾）。判据完全从 `spec.edges` 推出来——「没有任何边连的 role」就是孤立 role，不需要你做额外标记。所以 `bo` 既能当密度层展示、又不会污染真正的形态匹配。

跑匹配并读结果：

```python
from path2.dag.engine import analyze

result = analyze(build_pattern(params), df, params)

print(f"命中 {len(result.matches)} 次")

for m in result.matches:
    burst = m.role_index["burst"]       # 单个 BurstEvent（嵌套宽事件）
    tb_event = m.role_index["tb"]       # 单个 ThrowbackEvent
    down_seg = m.role_index["down"]     # 单个 TrendSegmentEvent

    # 整串 bo 在 burst 的 members 字段里；整体属性是它自己的字段
    print(f"  突破串长度={burst.count}, "
          f"区间=[{burst.start_idx}, {burst.end_idx}], "
          f"回踩确认={tb_event.start_idx}")
    first_bo = burst.members[0]         # 串里第一个 BOEvent（也可 burst.child("first_bo")）
```

> 💡 注意 `m.role_index["burst"]` 取出来是**一个** `BurstEvent`（嵌套宽事件），不是一串散点——整串 `bo` 装在它的 `members` 字段里，整体属性（`count`/`distinct_pk`/…）是它**自己的字段**。`bo` 节点因为是孤立 role、其残缺命中已被出口过滤，所以**不会**出现在任何 `role_index` 里。

---

## 9. `MatchContext`：谓词运行时的「环境」

写自定义谓词时偶尔会碰到 `ctx` 这个参数，这一节解释它是什么。

`MatchContext` 是引擎在匹配时构造、注入给每个谓词的「环境包」。**你只读它、不构造它**——构造是引擎的事。

```python
@dataclass(frozen=True)
class MatchContext:
    df:     object        # 完整行情 DataFrame，供回看历史数据
    params: object        # 传给 analyze() 的 params 对象，供读取阈值
    bound:  object = None # 已绑定节点的快照（当前 app 不使用，预留扩展）
```

绝大多数 `W.*` 谓词根本不碰 `ctx`，直接读事件属性就够了。只有当你写**自定义谓词**、需要回看 K 线（读 `ctx.df`）或读动态阈值（读 `ctx.params`）时才用得上：

```python
# 自定义谓词：事件前 20 根 K 线的成交量均值超过某阈值
def custom_vol_check(e, ctx):
    start = max(0, e.start_idx - 20)
    mean_vol = ctx.df["volume"].iloc[start:e.start_idx].mean()
    return mean_vol >= ctx.params.some_threshold

NodeSpec(
    "bo",
    BODetector(**p.bo_kwargs()),
    where=(("custom_vol", custom_vol_check),),
)
```

> 💡 自定义谓词的签名和 `W.*` 一样是 `(event_or_seq, ctx) -> bool`，所以你可以无缝混用 `W.*` 和自己写的函数。

---

## 10. `PatternSpec`：把一切装进总容器

`PatternSpec` 是最外层的容器，把所有节点、边、配置汇总成一个完整的 pattern。

```python
@dataclass(frozen=True)
class PatternSpec:
    pattern_id:         str
    display_name:       str
    nodes:              Tuple[NodeSpec, ...]
    edges:              Tuple[DependencyEdge, ...]
    root:               str
    event_styles:       Mapping[str, object] = field(default_factory=dict)
    stock_list_columns: Tuple[object, ...] = ()
```

💡 **构造时自动帮你查错**：`__post_init__` 在你构造 `PatternSpec` 的那一刻就做三类校验，有问题立刻抛 `ValueError`，不用等跑匹配才发现：

1. **DAG 合法性**：`root` 必须在 `nodes` 里；每条边的 `src`/`dst` 必须在 `nodes` 里；不能有环。
2. **Kleene 参数**：`min_count >= 1`；`min_count <= max_count`；`span_from_first` 的 lo/hi 合法；`endpoint_for_edges` 必须是 `"first"` 或 `"last"`。
3. **`consumes_stream` 引用**：填的 `node_id` 必须在 `nodes` 里。

### `to_topology()` —— 导出给面板画图

把 `nodes` / `edges` 零派生地直接转成 `PatternTopology`（由 `TopoNode` / `TopoEdge` 组成），供面板渲染「类型级 DAG 视图」：

```python
spec = build_pattern(params)
topo = spec.to_topology()

for node in topo.nodes:
    print(node.node_id, "class_id=", node.class_id, "kleene=", node.kleene)

for edge in topo.edges:
    print(edge.src, "->", edge.dst, "kind=", edge.kind)
```

`TopoNode.class_id` 取自 detector 产出事件的 `class_id`（`detector.event_cls.class_id`），面板按它给该角色上色。`TopoEdge.kind` 是边的子类名（如 `"TemporalEdge"` / `"StartContainmentEdge"`），面板按它分流渲染。

> 💡 `TopoNode.kleene` 只有在该节点真用了 `KleeneSpec` 时才是 `True`。示例 app 走的是嵌套事件路径、没有任何 Kleene 节点，所以它的所有节点 `kleene` 都是 `False`。

---

## 11. 读取匹配结果

`analyze(spec, df, params)` 返回一个 `AnalysisResult`：

```python
@dataclass(frozen=True)
class AnalysisResult:
    events:  Tuple[Event, ...]          # 所有节点流平铺（含未命中的候选事件）
    matches: Tuple[PatternMatch, ...]   # 命中结果列表
    spec:    object                     # 原始 PatternSpec（供面板 to_topology）
```

你最关心的是 `matches`。每个 `PatternMatch` 本身也是一个 `Event`（有 `event_id` / `start_idx` / `end_idx`），并额外带这些：

```python
@dataclass(frozen=True)
class PatternMatch(Event):
    pattern_id:      str
    role_index:      Optional[Mapping[str, RoleBinding]]  # node_id -> 实例或序列
    children:        Tuple[Event, ...]                    # role_index 展平，按 start_idx 升序
    predicate_trace: Optional[PredicateTrace]             # 逐谓词、逐边的诊断信息
```

`role_index` 的值类型（`RoleBinding`）取决于节点：

- 普通节点（含嵌套宽事件如 `burst`）：单个 `Event`（具体子类实例）。
- Kleene 节点：`Tuple[Event, ...]`（整个序列）。

### 排查命中细节：`predicate_trace`

调试时最有用的字段。它记录了本次命中里，每条 `where` 子句和每条边各自的求值结果——当你不确定「为什么这个片段命中了 / 那个属性到底是多少」时，靠它定位：

```python
trace = m.predicate_trace

# 查看 burst 节点各 where 子句过没过（key 就是你起的 clause_id）
print(trace.where_results["burst"])
# 例：{"first_drought": ClauseWitness(satisfied=True, measured=72, ...), ...}

# 查看 down->burst 这条边的实测情况
witness = trace.edge_results[("down", "burst")]
print(witness.measured)      # 实测 gap（隔了几根 K 线）
print(witness.satisfied)     # True
print(witness.src_instance)  # down 节点绑定的 TrendSegmentEvent
print(witness.dst_instance)  # burst 这个嵌套宽事件本体

# side->burst 这条起点包含边同理
print(trace.edge_results[("side", "burst")].satisfied)
```

> 💡 `where_results[nid]` 的每个值是一个 `ClauseWitness`，不是裸 `bool`。它在布尔上下文里直接当真值用（`if trace.where_results["burst"]["first_drought"]:` 照样工作），但还额外带着 `measured`（实测量）、`op`、`threshold`，方便你看清「这条到底过没过、实测多少、阈值多少」。

> ✅ **你现在应该能完整走通一遍了**：声明角色 → 加条件 → 连边 → 装进 `PatternSpec` → `analyze` → 从 `matches` 读结果 → 用 `predicate_trace` 调试。

---

## 附录：`W.*` 谓词速查表

这张表是写熟之后的速查参考。每个谓词的细节和例子见第 5 节。

| 函数 | 签名 | 适用场景 | 语义 |
|------|------|----------|------|
| `W.attr` | `(name, op, thr)` | 普通 / 嵌套宽事件 | `e.name op thr` |
| `W.child` | `(key, inner)` | 嵌套事件 | `inner(e.child(key))`：对命名单 child 套一元谓词 |
| `W.children` | `(key, agg)` | 嵌套事件 | `agg(e.children(key))`：对命名一组 child 套聚合谓词 |
| `W.first` | `(name, op, thr)` | Kleene 序列 | `seq[0].name op thr` |
| `W.last` | `(name, op, thr)` | Kleene 序列 | `seq[-1].name op thr` |
| `W.count` | `(op, thr)` | Kleene 序列 | `len(seq) op thr` |
| `W.any` | `(name, op, thr)` | Kleene 序列 | `∃ e∈seq: e.name op thr` |
| `W.distinct` | `(name, op, thr)` | Kleene 序列 | `len(set(e.name for e in seq)) op thr`，tuple/list/set 自动 flatten |
| `W.reduce` | `(name, fn, op, thr)` | Kleene 序列 | `fn([e.name for e in seq]) op thr` |
| `W.all` | `(*fns)` | 任意 | 多个谓词短路 AND 合取 |

`op` 合法值：`">="` `">"` `"<="` `"<"` `"=="` `"!="`（其他值在构造时抛 `ValueError`）。

所有谓词在属性值为 `None` 时安全返回 `False`。
