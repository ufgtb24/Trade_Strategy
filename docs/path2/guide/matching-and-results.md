# 匹配与结果指南

这篇文档教你做三件事：**用一句话把一种"走势"描述出来 → 让引擎在 K 线上找到它 → 把找到的结果读出来**。

读之前你不需要懂任何"事件框架"或"图匹配"理论。我们会从一个最小的例子起步，一步步把概念补齐，密集的字段表都放在最后供你查阅。

> 📖 阅读建议：第 1～2 节读懂 path2 在干什么；第 3～6 节学怎么把一种走势"写"出来；第 7～10 节学怎么把结果"读"出来。

---

## 1. path2 解决的是什么问题？

假设你脑子里有一种走势：「先有一个**突破点**，突破之后 10 根 K 线内出现一次**回踩**」。

人能一眼看出这种形态，但要让程序在成千上万根 K 线里自动找出来，你得回答两个问题：

1. **"突破点"和"回踩"分别长什么样？** —— 这是**识别单个事件**的问题。
2. **它们之间要满足什么关系？**（回踩必须在突破之后、10 根之内）—— 这是**事件之间关系**的问题。

path2 把这两件事分开：

- 你用 **detector**（探测器）负责"识别单个事件"——比如一个 `BODetector` 专门在 K 线上找突破点。
- 你用一份 **`PatternSpec`**（模式声明）把"事件 + 事件之间的关系"用声明的方式写下来。
- 引擎的 `analyze()` 读这份声明，自动在 K 线里把符合的组合全找出来。

> 💡 一句话总结：**detector 找点，`PatternSpec` 描述点与点的关系，`analyze()` 负责把符合的组合捞出来。** 你只写"声明"，不写搜索逻辑。

把一种走势的完整声明（用到的所有节点 + 关系 + 搜索策略）打包在一起，就叫一个 **走势包**。`PatternSpec` 就是这个走势包的"说明书"。

---

## 2. 最小可感知的例子：跑一次 analyze

先不管细节，感受一下调用长什么样：

```python
from path2.dag.engine import analyze, matches

result = analyze(spec, df, params=None)   # -> AnalysisResult，含全部命中
hit    = matches(spec, df, params=None)   # -> bool，只问"有没有命中过"
```

- `spec` 是你写的那份走势说明书（`PatternSpec`，下一节就教怎么写）。
- `df` 是一段 K 线行情（DataFrame）。
- `params` 是运行时参数，先填 `None`，第 5 节会讲它的用处。

`analyze` 返回一个 `AnalysisResult`，里面装着"找到了几次、每次具体是哪些 K 线"。
`matches` 是个偷懒的快捷方式，只告诉你"到底有没有找到过"，等价于 `len(analyze(...).matches) > 0`。

> 💡 小贴士：`analyze` 是引擎**唯一**的公开入口，你永远不需要手动去调用某个 detector，引擎会替你按正确顺序跑好它们。

### analyze 内部做了什么（先了解，不必背）

引擎内部分四步走，知道有这么回事即可，遇到问题时方便定位：

| 阶段 | 它在做什么 |
|------|-----------|
| 1. 跑 detector | 按依赖顺序把每个节点的 detector 跑一遍，得到各自的事件流。根节点直接看 `df`；下游节点看上游产出的事件流 + `df`（第 3 节讲"上游/下游"）。 |
| 2. compile_plan | 把你的 `spec` 编译成一张内部约束图。 |
| 3. 求解 | 枚举所有满足约束的合法绑定，按 leaf event 跨 prefix 去重。 |
| 4. reify | 把每个合法组合物化成一个 `PatternMatch`（一条命中记录），并收集所有事件流。 |

你现在应该理解了：**你只负责写 `spec`，这四步引擎全包。** 下面开始学怎么写 `spec`。

---

## 3. 怎么写一份走势声明：PatternSpec

`PatternSpec` 就是把"哪些事件 + 它们之间什么关系"打包成一个对象。它有两个核心部件：

- **`nodes`（节点）**：每个节点代表走势里的一个"角色"。比如"突破点"是一个节点，"回踩"是另一个节点。
- **`edges`（边）**：每条边代表两个角色之间的一种关系。比如"回踩在突破之后 10 根内"就是一条边。

节点 + 边，连起来就是一张有向图（DAG）。你可以把它想象成一张"剧本关系图"：每个角色是一个圈，角色之间的要求是连线。

> 💡 比喻：`nodes` 是演员表，`edges` 是剧情约束（谁必须在谁之后出场、谁必须把谁包在里面）。引擎就是按这张剧本去 K 线里选角。

### 先看一个完整声明长什么样

```python
from path2.dag.spec import PatternSpec

spec = PatternSpec(
    pattern_id="bottom_burst", # 走势的唯一标识（英文 id）
    display_name="底部反转突破爆发",       # 给人看的名字（面板展示）
    nodes=(...),                         # 演员表：Tuple[NodeSpec, ...]
    edges=(...),                         # 剧情约束：Tuple[DependencyEdge, ...]
    root="burst",                        # 退化字段，填一个合法 node_id 即可（见下）
)
```

最少只需要填前 5 个字段（`pattern_id` / `display_name` / `nodes` / `edges` / `root`），其余都有默认值。

> ⚠️ 关于 `root`：它是 `PatternSpec` 的必填字段，构造时会校验它必须是 `nodes` 里某个节点的 `node_id`。但**当前引擎求解时并不读它**——引擎是按图的连通分量（WCC）+ LEF-DFS 推进的，不需要一个单一的"起点角色"。所以你只需随便填一个合法的 `node_id`（当前示例 app 填的是 `"burst"`），不必纠结"从哪个角色起手"。

### 构造时会自动帮你查错

`PatternSpec` 在你创建它的那一刻（`__post_init__`）就自动做三类体检，发现问题立刻抛 `ValueError`，不会让你带着错误声明跑到一半才崩：

- **DAG 校验**：`root` 必须在 `nodes` 里；每条边的两端都得是已声明的节点；整张图不能有环。
- **Kleene 校验**：见第 3.4 节，针对用了 `kleene` 的节点检查数量/跨度合法。
- **detector 依赖校验**：节点的 `consumes_stream` 如果引用了上游，那个上游必须真的存在。

> 💡 小贴士：这意味着你的声明只要能成功构造出来，结构上就已经是合法的了。

`PatternSpec` 的完整字段表见 [附录 A](#附录-apatternspec-完整字段)，先继续往下学节点怎么写。

---

## 3.1 节点：NodeSpec

每个 `NodeSpec` 描述一个"角色"——它用哪个 detector 找事件、对事件有什么额外要求、输入从哪来。

我们先看两种最常见的节点；"绑一串事件"的两种进阶写法（嵌套事件 / Kleene）放在 §3.2、§3.4 单独讲。

### 类型一：普通单实例节点（最常见）

绑定**一个**事件。比如"一个突破点"：

```python
from path2.dag.nodes import NodeSpec

bo_node = NodeSpec(
    node_id="bo",                    # 这个角色的唯一名字
    detector=BODetector(...),        # 用哪个 detector 找这种事件
    where=(
        ("vol_filter", lambda e, ctx: e.volume >= ctx.params.min_vol),
    ),
    consumes_stream=None,            # None = 根节点，detector 直接看 df
    label="突破点",                   # 给人看的名字
)
```

`where` 是对这个事件本身的额外筛选条件（第 5 节细讲），可以先留空 `()`。

> 💡 你可能注意到这里没写"事件类型"。这是有意的：一个节点产出什么类型的事件，由它绑定的 `detector` 自带（`detector.event_cls.class_id`），不需要在 `NodeSpec` 里重复声明，面板上色也直接读这个 `class_id`。换句话说，"用哪个 detector"就已经决定了"产什么事件"。

### 类型二：消费者节点（依赖上游事件流）

有的事件不是直接从 K 线上找，而是**基于另一类事件再找**。比如"回踩"必须先有突破，回踩 detector 需要拿到上游的突破事件流才能工作。这种节点用 `consumes_stream` 指明它吃谁的产出：

```python
tb_node = NodeSpec(
    node_id="throwback",
    detector=ThrowbackDetector(...),
    consumes_stream="bo",            # 吃 "bo" 节点产出的事件流
    label="回踩",
)
```

- `consumes_stream=None` → **根节点**，detector 只看 `df`。
- `consumes_stream="bo"` → **消费者节点**，detector 拿到 `bo` 的事件流 + `df` 一起看。

> 💡 一句话总结：`consumes_stream` 决定的是"这个 detector 的输入从哪来"，引擎会据此排好运行顺序——先跑被依赖的，再跑依赖它的。

`NodeSpec` 完整字段表见 [附录 B](#附录-bnodespec-字段)。

---

## 3.2 嵌套事件：让"一串事件"成为一个一等公民

有时你关心的不是一个孤立的事件，而是**密集的一串**——比如"底部连续突破好几次"。你想把这"一整串"当成一个整体来引用：在图上画出它的范围、给它加 `where` 条件（"这串里至少 3 次"、"成交量峰值够大"）、让别的角色和它建立关系。

但散点事件做不到这件事：一串 `bo` 只是一堆零散的点，没有任何一个对象代表"这一整串"。

**嵌套事件**就是为此而生：把一串小事件**打包成一个大事件**，这个大事件是货真价实的一等公民 `Event`。

> 💡 一句话：嵌套事件 = "一个事件内部还装着更小的子事件"。整串有了自己的身份，就能像普通宽事件一样被引用、被画、被加条件。

### 例子：BurstEvent（一串突破聚合成的"爆发"）

`BurstEvent`（突破爆发）就是这样一个嵌套事件。它把密集的一串 `BOEvent`（单点突破）聚合成一个宽事件：

- 它有自己的 `start_idx`（= 串首 bo 的起点）和 `end_idx`（= 串尾 bo 的终点），所以在图上它是一段有宽度的区间，不再是孤点。
- 它内部用 `members` 字段（一个 tuple，**存完整的 `BOEvent` 对象**，不是 id）装着组成它的那些突破点。
- 它在被探测出来的那一刻，就顺手把几个**整串的聚合属性**算好、存成普通字段：`count`（串里几个突破）、`distinct_pk`（突破了几个不同的峰）、`max_vol_ratio`（成交量峰值）、`first_drought`（串首突破前的"干旱期"长度）。

这样一来，你想对"整串"加条件，直接用 `where` 读这几个字段即可（比如 `W.attr("count", ">=", 3)`），不必每次去遍历 `members`。

> 锚点：`path2/atoms/breakout.py` 的 `BurstEvent`。

### 怎么把一串散点聚合成嵌套事件：BurstDetector

`BurstEvent` 不是凭空出现的，它由一个专门的 detector —— `BurstDetector` —— 生产出来。它的工作是：**消费上游的 `bo` 流，把密集的 bo 切成一段一段，每段打包成一个 `BurstEvent`**。

```python
from path2.atoms.breakout import BurstDetector
from path2.dag import where as W

# 消费 bo 流，切串聚合成 BurstEvent
burst_node = NodeSpec(
    node_id="burst",
    detector=BurstDetector(max_span=20, min_bos=3),   # 切串参数走构造函数
    where=(
        ("count_floor", W.attr("count", ">=", 3)),    # 对整串的条件 = 直读预算字段
    ),
    consumes_stream="bo",                              # 吃 "bo" 节点产出的流
    label="突破爆发",
)
```

> 💡 此处 `W.attr("count", ">=", 3)` 是演示用的最简条件。真实 app 用的是 `first_drought` / `distinct_pk` / `max_vol_ratio` 三条，见 §6.5。

它内部的切串口径很直白：把 bo 按位置排好序，从第一个未用过的 bo 起手当"段首"，往后吸纳所有"起点距段首 ≤ `max_span`"的后续突破，贪心地吃成极大的一段、不回头；段长 ≥ `min_bos` 才算数、产出一个 `BurstEvent`。

注意这里的分工：

- **`BurstDetector` 只负责"切串 + 算好聚合标量"**，切串参数（`max_span` 怎么算密集、`min_bos` 最少几个）走它的构造函数。
- **真正的阈值过滤交给 `burst` 节点的 `where`**——比如"这串至少突破 3 个不同的峰"用 `W.attr("distinct_pk", ">=", 3)`，直读预算字段。阈值走 `where`，不传给 detector。

> 💡 为什么 detector 不自己去 K 线上找 bo、非要"消费 bo 流"？这是 path2 的一条原则：detector 之间靠**数据流水线**协作，谁产的事件谁负责，下游不重复造轮子。`BurstDetector` 不自己 new 一个 `BODetector`，而是吃别人产好的 bo 流（靠 `consumes_stream="bo"` 声明这层依赖）。
> 锚点：`path2/atoms/breakout.py` 的 `BurstDetector`。

### 嵌套是 Event 基类的通用能力

嵌套不是 `BurstEvent` 的专属把戏，而是 `Event` 基类提供的一套**通用协议**——任何事件都可以选择内部装着子事件。基类为此新增了几个方法（叶子事件默认返回空，行为完全不变）：

| 方法 | 它做什么 |
|------|---------|
| `child_slots()` | 返回"构成本事件的主要子事件集"，用来展平/遍历；叶子事件返回空 `{}` |
| `child(name)` | 按名字取**单个**子事件，如 `'first_bo'` / `'last_bo'`，给边端点 / selector 用 |
| `children(name)` | 按名字取**一组**子事件，如 `members` |
| `descendant_leaves` | 一路递归展开，直到拿到最底层、不再嵌套的原子事件 |

> 💡 这套协议的价值：当一个角色绑定的是个嵌套事件时，你既能把它当一个整体（用它的 `start`/`end` 和聚合字段），又能在需要时钻进去拿某个具体子事件（比如让一条边连到"串首那个 bo"而不是整串）。
> 锚点：`path2/core.py` 的 `child_slots` / `child` / `children` / `descendant_leaves`。

---

## 3.3 source_tag：同一种 detector 用了多个实例时，怎么不撞车

有时一种走势里会**多次用到同一个 detector 类**，只是扮演不同角色。比如当前示例 app 里，"下跌段"和"横盘段"都用 `TrendSegmentDetector`，各自实例化一个对象、配不同的 `where`。

这会引出一个小问题：两个实例产出的事件 `class_id` 都是 `'trend'`，而事件的 `event_id` 默认拿 `class_id` 当前缀——两边就会撞 id。

`source_tag` 就是 detector 上的一个"前缀钩子"，用来给同一类 detector 的不同实例区分身份（默认 `None` 时回退用 `class_id`）。你通常**不需要手动设它**：引擎在跑流之前会自动跑一步 `assign_auto_source_tags`，发现"同一个 `class_id` 下有 ≥2 个不同的 detector 对象"时，按它们在 `nodes` 里首次出现的顺序自动编号 —— `trend0`、`trend1`……让 event_id 前缀不再相撞。

> 💡 这一步是幂等且向后兼容的：只用一个实例、多个角色共享同一个对象、或你已经手动命过名的情况，它都不动，event_id 逐字不变。
> 锚点：`path2/dag/engine.py` 的 `assign_auto_source_tags`。

---

## 3.4 KleeneSpec：另一种"绑一串"的底层机制

除了把一串聚合成嵌套事件（§3.2），框架还提供一种更底层的方式让**一个角色直接绑定一串散点事件**——叫 **Kleene 节点**。给 `NodeSpec` 配上 `kleene=KleeneSpec(...)`，这个角色就从"绑一个"变成"绑一串"，引擎会在求解时从事件流里取一个连续子序列整段绑上。

> 💡 "Kleene"这个词来自正则里的 `*`（零或多个），你可以理解成"这个角色匹配一串，而不是一个"。

> ⚠️ **嵌套事件 vs Kleene，怎么选？** 二者都能表达"一串"，但出发点不同：
> - **嵌套事件**（§3.2）把"一串"在 **detect 期**就聚合成一个真正的对象（如 `BurstEvent`），整串有自己的身份、能被画、聚合属性是普通字段。当前示例 app `bottom_burst` 表达"一串突破"用的就是它，**不再用 Kleene**。
> - **Kleene** 不造新对象，而是在 **求解期**把散点流绑成序列，整串的属性靠 `aggregate_where` 现场聚合。适合"你确实想让一个角色绑一串散点、又不想专门为它写一个聚合 detector"的场合。
>
> 简单说：想让"一串"成为图上的一等公民、能被引用 → 用嵌套事件；只是临时把一串散点绑一起判个数量/聚合 → Kleene 更轻。**Kleene 仍是框架完整支持的机制**，只是当前唯一的 app 选了嵌套这条更干净的路。

```python
from path2.dag.nodes import NodeSpec, KleeneSpec

# 仅为讲解 Kleene 语义 —— 当前示例 app 不这么写一串突破，它用嵌套 BurstEvent
seq_node = NodeSpec(
    node_id="seq",
    detector=SomeAtomDetector(...),
    kleene=KleeneSpec(
        min_count=3,                           # 这一串至少 3 个事件
        max_count=float("inf"),                # 上界（当前引擎只支持 inf）
        span_from_first=(0, 20),               # 每个成员距"段首"≤ 20 根 bar
        aggregate_where=(
            ("min3", lambda seq, ctx: len(seq) >= 3),   # 对整串的额外条件
        ),
        endpoint_for_edges="first",            # 外层边连到这一串时，用段首参与判定
        greedy=True,                           # 贪心：尽量多吃（当前唯一支持值）
    ),
    consumes_stream=None,
    label="一串同类事件",
)
```

逐个理解几个容易困惑的字段：

- **`min_count`**：这一串至少要有几个成员，必须 `>= 1`。
- **`span_from_first`**：形如 `(lo, hi)`，约束每个成员相对**段首**的位置跨度（不是相邻成员之间的间隔，而是相对第一个成员）。引擎接纳成员 `e` 的条件是 `e.start − 段首.start` 落在这个区间内。填 `None` 表示不约束。
- **`aggregate_where`**：对**整串**（而不是单个成员）的条件，函数签名是 `fn(tuple[Event,...], MatchContext) -> bool`，多个条件之间 AND 合取。
- **`endpoint_for_edges`**：当外层有边连到这个 Kleene 节点时，到底拿这一串的哪一端去判关系？`'first'`=段首，`'last'`=段尾。

> ⚠️ 当前引擎的限制（硬规定）：只支持 `greedy=True` 且 `max_count=math.inf` 的形状，也就是"给一个数量下界，然后贪心吃成极大的一段"。配成别的形状（比如 `greedy=False`）会在运行时抛 `NotImplementedError`，**不会**悄悄给你一个错误结果。

`KleeneSpec` 完整字段表见 [附录 C](#附录-ckleenespec-字段)。

---

## 4. 边：描述事件之间的关系

边（`DependencyEdge` 的各个子类）是走势声明的另一半——它说明两个角色之间要满足什么关系。

每条边都有方向 `src → dst`，这个方向同时定义了三件事：

1. 拓扑顺序（`src` 排在 `dst` 前面）；
2. 引擎搜索时的推进方向（先定 `src`，再据此收窄 `dst` 的候选）；
3. 面板上箭头的指向。

> 💡 比喻：一条边就像剧本里的一句要求"B 必须在 A 之后出场"。`src` 是 A，`dst` 是 B，箭头从 A 指向 B。

path2 提供 6 种关系。下面按从最常用到最特殊的顺序介绍。

### TemporalEdge — 时序边（最常用）

含义：**dst 在 src 结束之后某个时间窗内开始。** 用 `gap`（间隔的 bar 数）来界定。

判定公式：`dst.start_idx − src.end_idx ∈ [min_gap, max_gap]`

```python
from path2.dag.edges import TemporalEdge

# 回踩在突破结束后 0~10 根 bar 内开始
TemporalEdge(src="bo", dst="throwback", min_gap=0, max_gap=10)

# strict=True：next 语义（这个窗口里没有更早的同类 dst 抢先）
TemporalEdge(src="bo", dst="throwback", min_gap=0, max_gap=10, strict=True)
```

> ⚠️ 常见坑：`strict` 是 **keyword-only** 参数（必须写成 `strict=True`，不能按位置传）。这是故意设计的，防止你把它和前面的 `min_gap`/`max_gap` 位置参数搞错位。
> 另外注意：`min_gap` 必须 `>= 0`，否则构造时就报错。

### ContainmentEdge — 包含边

含义：**src 这个大区间把 dst 这个小区间整个包住。** 比如"一段趋势区间里包含某个突破点"。

判定公式：`src.start <= dst.start` 且 `dst.end <= src.end`（端点相等也算包含）。

```python
from path2.dag.edges import ContainmentEdge

# trend 区间包含 bo 事件
ContainmentEdge(src="trend", dst="bo")
```

> 💡 规范方向永远是"大区间 `src` → 小区间 `dst`"。

### StartContainmentEdge — 起点包含边

含义：**只要求 dst 的"起点"落进 src 区间内，不管 dst 的"终点"伸到哪。**

判定公式：`src.start <= dst.start <= src.end`（注意：**没有** `dst.end <= src.end` 这一条）。

```python
from path2.dag.edges import StartContainmentEdge

# side 这段横盘里，只需把 burst 的起点框住（burst 的尾巴可以伸出去）
StartContainmentEdge(src="side", dst="burst")
```

它和上面的 `ContainmentEdge` 长得很像，区别就一条：`ContainmentEdge` 要求 dst **整体**被包住（连尾巴 `dst.end <= src.end` 也得在里面），而 `StartContainmentEdge` **只管起点**。

> 💡 什么时候需要它？当 dst 是个**宽事件**、你只在乎"它从 src 内部起步"、不在乎它后来伸出去多远时。比如当前示例 app 里的 `side → burst`：横盘段只需要"突破爆发是从横盘里开始的"，而这串爆发本身可能延伸到横盘段结束之后——这时用 `ContainmentEdge` 会过严（强行要求爆发整段不超出横盘），用 `StartContainmentEdge` 才精确。

### OverlapEdge — 部分交叠边

含义：**dst 从 src 内部某处起步，但延伸到了 src 结束之后**（两者部分重叠，dst 把 src 的尾巴叠住）。

判定公式：`src.start < dst.start < src.end < dst.end`

```python
from path2.dag.edges import OverlapEdge

OverlapEdge(src="phase1", dst="phase2")
```

### EqualsEdge — 同段边

含义：**两个不同类型的事件占据完全相同的时间区间。** 比如同一段时间既被判为"趋势"又被判为"平台"。

判定公式：`src.start_idx == dst.start_idx` 且 `src.end_idx == dst.end_idx`

```python
from path2.dag.edges import EqualsEdge

EqualsEdge(src="trend", dst="platform")
```

> 💡 给你交代一个内部细节（用不到也没关系）：引擎为了不漏掉同段匹配，会对所有当过 `EqualsEdge` 之 `src` 的节点关闭一项叫 C1 的去重优化。`PatternSpec.eq_src_nodes()` 就是提供这个判据集合给引擎用的。你不用手动做任何事。

### NegationEdge — 否定边（"禁止出现"）

前四种边都是"要求某种关系成立"，否定边相反——它要求**某个时间窗里不许出现满足条件的 dst**。

含义：**在 src 锚定的那段窗口内，禁止存在任何满足条件的 dst 事件。**（这是个"全称量词"约束：窗口里所有 dst 都不违禁，这条边才算满足。）

```python
from path2.dag.edges import NegationEdge

# bo 结束后 0~5 根 bar 内，不许有任何 ThrowbackEvent
NegationEdge(src="bo", dst="throwback", min_gap=0, max_gap=5)

# 加 inner_predicate：只有"大幅回调"的 throwback 才算违禁
NegationEdge(
    src="bo",
    dst="throwback",
    min_gap=0,
    max_gap=5,
    inner_predicate=lambda e: e.depth >= 0.05,
)
```

- `min_gap` / `max_gap` 界定禁区窗口：`min_gap <= dst.start − src.end <= max_gap`。
- `inner_predicate` 是个可选的额外过滤；填 `None` 表示窗口内**任何** dst 都构成违禁。

> ⚠️ 否定边的两个特殊之处，务必记住：
> 1. 它的 `dst` 节点**不会**进入命中结果的 `role_index`/`children`——它只是个约束，不是走势的结构成员。
> 2. 它的 `satisfies` 语义是**反转**的：`satisfies` 返回 `True` 表示该 dst"落入禁区、构成违禁"。引擎用全称量词消费——只有所有 dst 都不违禁，这条边才满足。

各种边的完整字段表见 [附录 D](#附录-d边类型字段)。

---

## 5. where 谓词：给单个角色加筛选条件

光靠 detector 找出来的事件可能太宽泛，你常常想再过滤一道，比如"这个突破点的成交量得够大"。这就是 `where` 的用途。

**`where` 是节点级的一元谓词**——"一元"的意思是它**只能看一个候选自己**的属性，或者运行时参数 `ctx.params`，**不能**去看别的角色绑定了什么。

```python
# where 函数签名：(候选, MatchContext) -> bool
#   普通节点：候选是单个 Event
#   Kleene 节点：候选是 Tuple[Event, ...]（整串一起判）

def vol_check(e, ctx):
    return e.volume >= ctx.params.min_vol

node = NodeSpec(
    node_id="bo",
    detector=BODetector(...),
    where=(
        ("vol_filter", vol_check),                                   # (clause_id, fn)
        ("price_filter", lambda e, ctx: e.close >= ctx.params.min_price),
    ),
)
```

`where` 是一串 `(clause_id, fn)` 二元组，多个子句之间 AND 合取（全过才算通过）。`clause_id` 是给这个条件起的名字，将来诊断时（第 9 节）会按这个名字告诉你哪条过了、哪条没过。

### ctx.params 与 MatchContext

`where` 函数的第二个参数 `ctx` 是个 `MatchContext`，它带着你判定时可能需要的环境：

| 字段 | 它是什么 |
|------|---------|
| `df` | 完整的 K 线 DataFrame，让 `where` 能回看历史数据 |
| `params` | 就是你调用 `analyze(spec, df, params)` 时传进去的那个 `params`，常用来放阈值 |
| `bound` | 跨节点绑定（当前 app 不用，见下方红线） |

这下你明白第 2 节那个 `params` 的用处了：把阈值（比如 `min_vol`）放进 `params`，`where` 就能通过 `ctx.params.min_vol` 读到，免得把阈值写死在代码里。

> ⚠️ 红线——`where` 里严禁读 `ctx.bound`。 `bound` 是别的节点的绑定实例。`where` 设计上只许看"自己"。引擎在剪枝阶段会用一个叫 `_TRIPWIRE` 的哨兵把 `bound` 顶替掉，你一旦去读它就会立刻抛 `RuntimeError`。需要"角色之间"的关系，请用边（第 4 节），不要用 `where`。

> 💡 一句话总结：**`where` 管"一个角色自己合不合格"，边管"两个角色之间的关系"。** 这条分工是整个设计的脊梁，别越界。

---

## 6. 一个完整的真实例子：bottom_burst

前面都是零碎的语法片段，这里给你一份**与代码一致的完整范例**——这就是当前示例 app `bottom_burst`（"底部反转突破爆发"）的真实写法，把前面学的节点、嵌套事件、6 种边、where 全用上了。

它要表达的走势是：**先有一段大幅下跌，转入横盘，然后从横盘里冒出一串密集突破（爆发），最后突破后回踩确认。**

整个 spec 是 **5 个节点 + 3 条边**：

| 节点 | 角色 | detector | 输入 | 说明 |
|------|------|----------|------|------|
| `bo` | 突破点（孤立流源） | `BODetector` | `df` | 单点突破，**没有任何边连它**——只当"密度流源层"：给 `burst`/`tb` 当输入流，也可独立画在 K 线上 |
| `down` | 下跌段 | `TrendSegmentDetector`（实例一，自动得 `source_tag` `trend0`） | `df` | `where`: `regime=='down'` 且 `drawdown >= 阈值` |
| `side` | 横盘段 | `TrendSegmentDetector`（实例二，`trend1`） | `df` | `where`: `regime=='sideways'` |
| `burst` | 突破爆发（嵌套事件） | `BurstDetector` | `bo` 流 | 消费 bo 流切串聚合成 `BurstEvent`；`where` 直读预算字段：`first_drought` / `distinct_pk` / `max_vol_ratio` |
| `tb` | 回踩确认 | `ThrowbackDetector` | `bo` 流 | 吃 `BOEvent`（不是 `BurstEvent`），仅 confirmed 时产事件 |

3 条边全部连到 `burst` 这个宽事件本体：

| 边 | 类型 | 含义 |
|----|------|------|
| `down → burst` | `TemporalEdge(min_gap=1, max_gap=lookback)` | burst 之前 lookback 根内有一段大幅下跌 |
| `side → burst` | `StartContainmentEdge` | burst 的起点落在横盘段内（爆发从横盘里起步） |
| `burst → tb` | `TemporalEdge(min_gap=1, max_gap=1)` | burst 末根（= 串尾 bo 终点）的下一根开始回踩 |

> 💡 注意 `burst` 是个普通的单实例（ONCE）节点，不是 Kleene 节点——"一串突破"的复数性已经被 `BurstEvent` 这个嵌套事件吸收掉了，对图来说它就是一个有宽度的事件。

### 孤立流源 bo：为什么它不进任何命中

你可能会奇怪：`bo` 是个节点，却没有任何边连它，那它算哪门子"角色"？

这是有意的。`bo` 在这里只扮演**"密度流源层"**：它的作用一是给 `burst`/`tb` 当原料（它们 `consumes_stream="bo"`），二是可以独立地画在 K 线上（把所有突破点都标出来）。但它**本身不参与任何形态约束**。

引擎对这种"图里没有任何边连它"的节点（叫**孤立 role**）有专门处理：如果不管，每个孤立的 bo 都会自成一个"只含 bo 这一个角色"的残缺命中——一堆语义垃圾。所以 `analyze` 在出口处会**自动识别出孤立 role**（从 `spec.edges` 推：哪些 `node_id` 从没在任何边里出现过），然后**丢弃那些"只含孤立 role"的残缺命中**。

> 💡 效果：`bo` 既能作为一层独立的密度信息被扫描、渲染出来，又不会污染真正的形态匹配——你拿到的 `matches` 里，每一条都是凑齐了 down/side/burst/tb 关系的完整命中，不会冒出"只有一个孤零零 bo"的假命中。
> 锚点：`path2/dag/engine.py` 出口的孤立 role 推导 + 过滤。

---

到这里，**怎么写 `spec`** 你已经齐活了：节点（普通 / 嵌套事件 / 消费者 / Kleene）、边（6 种关系）、where 筛选、选择策略。下面学**怎么读结果**。

---

## 7. 读结果第一步：AnalysisResult

`analyze()` 返回的 `AnalysisResult` 是结果的总入口，结构很简单：

```python
result = analyze(spec, df, params)

# 1) 所有节点产出的事件流（含中间节点），平铺在一起 —— 适合在图上标原始事件
for event in result.events:
    print(event.event_id, event.start_idx, event.end_idx)

# 2) 全部命中
print(f"共命中 {len(result.matches)} 次")

# 3) 原始声明 —— 面板要画拓扑图时从这里拿
topo = result.spec.to_topology()
```

| 字段 | 类型 | 它是什么 |
|------|------|---------|
| `events` | `Tuple[Event, ...]` | 所有节点事件流的并集（平铺合并），供面板标注原始事件 |
| `matches` | `Tuple[PatternMatch, ...]` | 全部命中；空 tuple 表示一次没命中 |
| `spec` | `PatternSpec` | 你传进去的那份声明，面板可由它调 `to_topology()` 画拓扑（第 10 节） |

> 💡 区分清楚：`events` 是"找到的所有零散事件点"，`matches` 是"把这些点按你的声明拼成的完整命中"。一个完整命中里通常包含好几个事件。

---

## 8. 读单条命中：PatternMatch 与 role_index

`result.matches` 里每一项是一个 `PatternMatch`，代表一次完整命中。它**继承自 `Event`**，所以自带位置信息：

```python
match = result.matches[0]

print(match.event_id)    # 格式固定为 '<pattern_id>@<start_idx>-<end_idx>'
print(match.start_idx)   # 这次命中跨度的起始 bar 索引
print(match.end_idx)     # 这次命中跨度的结束 bar 索引
print(match.pattern_id)  # 等于你声明里的 PatternSpec.pattern_id
```

### role_index：哪个角色绑到了哪个事件

一次命中是"每个角色各自绑了一个（或一串）具体事件"。`role_index` 就是这张"角色 → 实际绑定"的对照表，键是 `node_id`：

- **普通节点**（`kleene=None`）：值是**单个 `Event`**。
- **Kleene 节点**（`kleene` 非 `None`）：值是 **`Tuple[Event, ...]`**（一串事件）。

```python
# 普通节点：拿到单个事件
burst_event = match.role_index["burst"]
print(burst_event.start_idx, burst_event.end_idx)

# Kleene 节点：拿到一串事件（tuple）
seq = match.role_index["seq"]
print(f"绑了 {len(seq)} 个事件")
for e in seq:
    print(f"  bar {e.start_idx}-{e.end_idx}")
```

> ⚠️ 常见坑：读 `role_index` 的值前，先用 `isinstance(binding, tuple)` 判断是普通节点还是 Kleene 节点，否则你可能对一个 tuple 调用 `.start_idx`。
>
> 注意：当前示例 app `bottom_burst` 全是单实例（ONCE）节点，`role_index` 的值都是**单个 `Event`**——包括 `burst`，它虽然内部装着一串 bo，但它本身是一个 `BurstEvent` 对象，不是 tuple。上面的 tuple 分支只在你**真的用了 Kleene 节点**时才会出现。

### children：所有绑定实例的扁平视图

`children` 是把 `role_index` 里所有值（Kleene 的会展开成单个元素）摊平、按 `start_idx` 升序排好的一个列表。

```python
for child in match.children:
    print(child.event_id)
```

> 💡 `children` 和 `role_index` 指向的是**同一批对象**（`id` 一致），`children` 只是排好序的扁平视图。需要"按角色看"用 `role_index`，需要"按时间顺序遍历所有事件"用 `children`，**别两边都遍历**做重复处理。
> 注意：否定边（`NegationEdge`）的 `dst` 是约束、不是成员，所以**不会**出现在 `role_index`/`children` 里。

### 完整遍历模板

```python
for match in result.matches:
    print(f"命中 {match.pattern_id}：bar {match.start_idx}→{match.end_idx}")
    for node_id, binding in match.role_index.items():
        if isinstance(binding, tuple):
            print(f"  [{node_id}] {len(binding)} 个事件")        # Kleene 节点
        else:
            print(f"  [{node_id}] bar {binding.start_idx}-{binding.end_idx}")  # 普通节点
```

---

## 9. 诊断命中：predicate_trace 与 EdgeWitness

有时你想知道"这次命中**为什么**成立"——每个 `where` 条件过没过、每条边量出来的间隔是多少。这些"判定过程的留痕"放在 `match.predicate_trace` 里。

> 💡 用途：把 `where_results` 渲染成节点上的"✅/❌"，把边的 `measured` 渲染成边标签。调参时它能帮你看清是哪一步卡住了、卡在什么数值——比如边标签显示"间隔 3 bar"，节点条件显示"实测 42 ≥ 阈值 40 ✅"。

```python
trace = match.predicate_trace
if trace is None:
    print("没有 trace")
else:
    # where_results：node_id → {clause_id: ClauseWitness}
    for node_id, clauses in trace.where_results.items():
        for clause_id, w in clauses.items():
            # w 是 ClauseWitness：能直接当布尔用（实现了 __bool__），也能拿实测细节
            print(f"  {node_id}.{clause_id}: {'通过' if w else '未通过'}"
                  f"（实测 {w.measured} {w.op} 阈值 {w.threshold}）")

    # edge_results：(src, dst) → EdgeWitness
    for (src, dst), witness in trace.edge_results.items():
        print(f"  边 {src}→{dst}: gap={witness.measured:.1f} bar")
        print(f"    src 实例: bar {witness.src_instance.start_idx}-{witness.src_instance.end_idx}")
        print(f"    dst 实例: bar {witness.dst_instance.start_idx}-{witness.dst_instance.end_idx}")
```

### PredicateTrace 里有什么

| 字段 | 类型 | 它是什么 |
|------|------|---------|
| `where_results` | `Mapping[str, Mapping[str, ClauseWitness]]` | `node_id → {clause_id: ClauseWitness}`，每个 `where` 子句的判定见证（见下） |
| `edge_results` | `Mapping[Tuple[str, str], EdgeWitness]` | `(src, dst) → EdgeWitness`；**`NegationEdge` 不收录** |

### ClauseWitness：一条 where 子句的"判定见证"

`where_results` 里每个值不是裸 `bool`，而是一个 `ClauseWitness`，它除了告诉你"过没过"，还带着**实测值和阈值**——这正是调参时最有用的信息（看清"差多少才过"）：

| 字段 | 类型 | 它是什么 |
|------|------|---------|
| `satisfied` | `bool` | 这条子句过没过 |
| `measured` | `object` | 实测值（`W.*` 谓词产出，如算出来的 `first_drought` 值）；组合子 / 无 measure 时为 `None` |
| `op` | `object` | 比较算子（`">="` / `"=="` …）；组合子时 `None` |
| `threshold` | `object` | 阈值；组合子时 `None` |
| `aggregate` | `bool` | `True` 表示这条来自 `KleeneSpec.aggregate_where`（整串聚合判定） |

> 💡 `ClauseWitness` 实现了 `__bool__`（等于它的 `satisfied`），所以你想偷懒时直接 `if w:` 当布尔用也行，向后兼容；想看细节时再读 `w.measured` / `w.op` / `w.threshold`。

### EdgeWitness：一条边的"实证两端"

`EdgeWitness` 记录这条边在这次命中里具体连了哪两个实例、量出来多少：

| 字段 | 类型 | 它是什么 |
|------|------|---------|
| `satisfied` | `bool` | 这条边在本次命中里是否满足 |
| `src_instance` | `Event` | src 端绑定实例（Kleene 节点取 `endpoint_for_edges` 指定的那一端） |
| `dst_instance` | `Event` | dst 端绑定实例（Kleene 取段首） |
| `measured` | `float` | 实测量，对所有**正向**边统一为 `dst.start_idx − src.end_idx`（bar 数）；负值表示两端区间有 overlap |

> ⚠️ `edge_results` 只收录正向边。`NegationEdge` 是"禁止出现"的约束，没有"两端实例"可留痕，所以不在里面。

---

## 10. to_topology()：给面板/UI 画图用

面板要画那张"角色圈 + 关系箭头"的拓扑图时，并不需要去翻你的内部声明，而是调 `PatternSpec.to_topology()`——它把 `nodes`/`edges` 原样直投成一份面板友好的 `PatternTopology`，**不做任何反推**。

```python
topo = result.spec.to_topology()   # -> PatternTopology

# 节点
for node in topo.nodes:
    print(node.node_id)      # 节点唯一标识
    print(node.class_id)     # 事件类型字符串（= detector.event_cls.class_id），面板据此上色
    print(node.label)        # 人类可读名称
    print(node.kleene)       # bool：是不是 Kleene 节点

# 边
for edge in topo.edges:
    print(edge.src, "->", edge.dst)
    print(edge.kind)         # 边子类名，面板按此选箭头样式
```

这是一份纯数据契约，详细字段见 [附录 E](#附录-eto_topology-数据契约)。

### 面板消费示例

```python
topo = result.spec.to_topology()
styles = result.spec.event_styles      # node_id → 渲染样式（引擎不读，纯给面板）

# 画节点：Kleene 节点用方块，普通节点用圆圈
for node in topo.nodes:
    style = styles.get(node.node_id, {})
    color = style.get("color", "#999")
    shape = "rect" if node.kleene else "circle"
    render_node(node.node_id, node.label, color, shape)

# 画边：按 kind 分流箭头样式
arrow_style = {
    "TemporalEdge":          "solid",
    "ContainmentEdge":       "dashed",
    "StartContainmentEdge":  "dash-dot",
    "OverlapEdge":           "dotted",
    "EqualsEdge":            "double",
    "NegationEdge":          "red-solid",
}
for edge in topo.edges:
    render_edge(edge.src, edge.dst, arrow_style[edge.kind])
```

---

至此你应该能：**写出一份 `PatternSpec`、跑 `analyze`、读懂每一条命中、并把它画到面板上**。下面是字段速查附录，需要时再翻。

---

## 附录 A：PatternSpec 完整字段

> 这是一张速查表，配合第 3 节阅读。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pattern_id` | `str` | 必填 | 走势唯一标识，用于 `PatternMatch.pattern_id` |
| `display_name` | `str` | 必填 | 人类可读名称，供面板展示 |
| `nodes` | `Tuple[NodeSpec, ...]` | 必填 | 全部节点；引擎按拓扑序调用各节点 detector |
| `edges` | `Tuple[DependencyEdge, ...]` | 必填 | 全部有向依赖边 |
| `root` | `str` | 必填 | 退化字段：构造时校验须是合法 `node_id`，但当前引擎求解不读它（求解基于 WCC / LEF-DFS，不需要单一根），随便填一个合法 `node_id` 即可 |
| `event_styles` | `Mapping[str, object]` | `{}` | `node_id` → 渲染样式，仅供面板，引擎忽略 |
| `stock_list_columns` | `Tuple[object, ...]` | `()` | 面板股票列表列规格，仅供面板，引擎忽略 |

**构造时自动校验（`__post_init__`，违反即抛 `ValueError`）：**

- DAG 校验：`root` 须在 `nodes` 中；边的 `src`/`dst` 须在 `nodes` 中；节点图无环。
- Kleene 校验：`min_count >= 1`；`min_count <= max_count`；`span_from_first` 的 `lo` 非负且 `lo <= hi`；`endpoint_for_edges` 须为 `'first'` 或 `'last'`。
- detector DAG 校验：`consumes_stream` 若非 `None`，须指向已声明的 `node_id`。

---

## 附录 B：NodeSpec 字段

> 速查表，配合第 3.1 节阅读。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `node_id` | `str` | 必填 | 拓扑唯一键；同一 detector 以不同角色出现时用不同 `node_id` |
| `detector` | 任意对象 | 必填 | 实现 path2 Detector 协议的事件生产者；引擎通过 `run()` 调用，app 不手动调用。该 detector 的 `event_cls.class_id` 即此节点的事件类型，供 `to_topology` / 面板上色（不在 `NodeSpec` 里单独声明） |
| `where` | `Tuple[Tuple[str, WherePredicate], ...]` | `()` | 节点级一元谓词列表，形如 `(clause_id, fn)`，AND 合取 |
| `kleene` | `Optional[KleeneSpec]` | `None` | `None`=普通单实例；非 `None`=绑一串事件 |
| `consumes_stream` | `Optional[str]` | `None` | `None`=根节点（消费 `df`）；否则填上游节点 `node_id` |
| `label` | `str` | `""` | 人类可读名称，投影到 `TopoNode.label` |

---

## 附录 C：KleeneSpec 字段

> 速查表，配合第 3.4 节阅读。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `min_count` | `int` | `1` | 闭包成员数下界（须 `>= 1`） |
| `max_count` | `float` | `math.inf` | 闭包成员数上界；当前引擎只支持 `math.inf`（贪心极大段） |
| `span_from_first` | `Optional[Tuple[int, float]]` | `None` | 成员相对段首的绝对跨度窗 `(lo, hi)`；`None` 不约束 |
| `aggregate_where` | `Tuple[Tuple[str, Callable], ...]` | `()` | 整串聚合谓词列表，`fn(tuple[Event,...], MatchContext) -> bool`，AND 合取 |
| `endpoint_for_edges` | `str` | `"first"` | 外层边连接本节点时取 `'first'`（段首）或 `'last'`（段尾）参与 `satisfies` |
| `greedy` | `bool` | `True` | 贪心极大段；`False` 会抛 `NotImplementedError` |

---

## 附录 D：边类型字段

> 速查表，配合第 4 节阅读。所有边都继承自 `DependencyEdge`，共有 `src` / `dst` 两个必填字段。

**TemporalEdge**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `min_gap` | `0` | `dst.start − src.end` 最小间隔（bar 数），须 `>= 0` |
| `max_gap` | `math.inf` | 最大间隔（bar 数） |
| `strict` | `False` | `True`=next 语义；**keyword-only 参数** |

**ContainmentEdge** / **StartContainmentEdge** / **OverlapEdge** / **EqualsEdge**：只有 `src` / `dst`，无额外字段，关系由各自的 `satisfies` 公式定义（见第 4 节）。其中 `StartContainmentEdge` 只约束 `dst.start ∈ [src.start, src.end]`，不约束 `dst.end`。

**NegationEdge**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `min_gap` | `0` | 禁区起点：`dst.start − src.end >= min_gap` |
| `max_gap` | `math.inf` | 禁区终点：`dst.start − src.end <= max_gap` |
| `inner_predicate` | `None` | 额外一元过滤 `fn(Event) -> bool`；`None`=窗口内所有 `dst` 均违禁 |

---

## 附录 E：to_topology 数据契约

> 速查表，配合第 10 节阅读。

**PatternTopology**

| 字段 | 类型 | 说明 |
|------|------|------|
| `nodes` | `Tuple[TopoNode, ...]` | 节点投影列表 |
| `edges` | `Tuple[TopoEdge, ...]` | 边投影列表 |

**TopoNode**

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | `str` | 与 `NodeSpec.node_id` 一致 |
| `class_id` | `str` | 与 `detector.event_cls.class_id` 一致，面板据此上色 |
| `label` | `str` | 人类可读名称，默认空串 |
| `kleene` | `bool` | 是否为 Kleene 节点（`NodeSpec.kleene is not None`） |

**TopoEdge**

| 字段 | 类型 | 说明 |
|------|------|------|
| `src` | `str` | 源节点 `node_id` |
| `dst` | `str` | 目标节点 `node_id` |
| `kind` | `str` | 边子类名（`'TemporalEdge'` / `'ContainmentEdge'` / `'StartContainmentEdge'` / `'OverlapEdge'` / `'EqualsEdge'` / `'NegationEdge'`），面板按此分流渲染箭头样式 |

---

## 附录 F：RoleBinding 类型别名

> 配合第 8 节阅读。

```python
from path2.dag.result import RoleBinding
# RoleBinding = Union[Event, Tuple[Event, ...]]
#   普通节点：Event
#   Kleene 节点：Tuple[Event, ...]
```

`RoleBinding` 是 `role_index` 中每个节点槽位绑定值的类型。读取时用 `isinstance(binding, tuple)` 区分两种情况。
