# path2 文档入口

## 先用一句话告诉你 path2 是什么

你有一张 K 线表（DataFrame），你心里有一个"走势长什么样算数"的想法——比如"先一路下跌，再横盘震荡，然后连续几次放量突破，最后回踩确认"。

**path2 让你把这个想法直接"写下来"，剩下的检测、求解、整理结果，全交给引擎。**

你不需要手写一堆嵌套的 `for` 循环去配对各种事件、判断它们的先后和包含关系。你只要声明清楚"我要哪些事件、它们之间是什么关系"，path2 就替你把这张图跑通。

> 💡 一句话总结：**path2 = 用声明式的"图"来描述多段走势的组合，引擎负责把它从数据里找出来。**

⚠️ path2 是一个**独立的事件表达框架**。它和任何选股流水线、因子体系、参数优化都**没有关系**——它只做一件事：在时序数据上识别"多段事件的结构性组合"。读这份文档时，请不要把它往那些方向联想。

---

## 三个核心概念：名词、动词、和把它们拼起来的"图"

path2 的世界里只有三类东西。我们先用大白话各点一句，再逐个展开。

- **Event（事件）** = 名词。数据上的"一段东西"，比如"这一段是下跌"。
- **Detector（检测器）** = 动词。负责"从数据里把某类事件找出来"的零件。
- **PatternSpec（模式声明）** = 把多个事件用关系连起来的一张"图"，也就是你想表达的完整走势。

下面逐个讲清楚。

### Event：数据上的一段命名区间

**Event 就是"时间轴上的一段"**，它知道自己从哪根 K 线开始、到哪根 K 线结束。可以把它想成给一段走势贴的一张标签纸："第 30 根到第 50 根，这是一段下跌"。

它只有三个最基本的字段：

```python
@dataclass(frozen=True)
class Event(ABC):
    event_id: str      # 这一段的唯一名字
    start_idx: int     # 起始 K 线下标（含）
    end_idx: int       # 结束 K 线下标（含）
```

所有具体的事件类型——`BOEvent`（突破点）、`TrendSegment`（趋势段）、`Platform`（平台）……——都继承自 `Event`，并且都是**冻结的 dataclass**（`frozen=True`，建好就不能改字段）。

> 💡 小贴士：`start_idx` 和 `end_idx` 都是**闭区间**（两端都包含在内）。

> 💡 基类还提供了一套 `child` / `children` / `descendant_leaves` 嵌套协议，让一个事件能装着更小的子事件（见后文「嵌套事件」一节）。对**叶子事件**（如 `BOEvent`、`TrendSegment`）来说它们默认返回空、毫无影响——你可以先当它不存在。

### Detector：把某一类事件找出来的"生产者"

**Detector 就是一台专门找某种事件的机器。** 你喂给它数据（或上游事件流），它源源不断地吐出一类 `Event`。

写一个 Detector 只需要实现一个方法：`detect(source) -> Iterator[Event]`——拿到输入，逐个产出事件。

实际驱动 Detector 时，推荐用 `run(detector, *source)` 这个入口，而不是直接调 `detect`。`run` 除了帮你跑起来，还会在 `RUNTIME_CHECKS` 模式下顺便校验产出的合法性（比如端点是否升序、`event_id` 是否唯一），帮你早点抓到 bug：

```python
from path2 import run
from path2.atoms.breakout import BODetector

for event in run(BODetector(), df):   # 把整张 df 喂给突破检测器
    print(event)
```

> 💡 你现在应该理解了：**Event 是结果，Detector 是产出结果的零件。** 接下来要解决的问题是——怎么把好几个 Detector 的产物，按你想要的关系拼成一个完整走势？这就是下一节的 PatternSpec。

### PatternSpec：把事件们"连成一张图"

到这里，单个事件你会找了。但真正有意义的走势往往是**好几段事件按特定关系组合**出来的。`PatternSpec` 就是你用来描述这种组合的声明。

**把它想象成一张关系图：**
- 图上的每个**节点（NodeSpec）**代表"我需要这样一段事件"（什么角色、用哪个 detector 去找、还要满足什么额外条件）。
- 节点之间的**边（DependencyEdge）**代表"这两段事件之间得是什么关系"（谁在谁前面、谁包含谁……）。

为什么要用"图"这种形式？因为它把"事件本身的条件"和"事件之间的关系"彻底分开了，你声明时一目了然，引擎也能据此自动决定先找谁、再用谁去收窄下一个的搜索范围。

一个 `PatternSpec` 由三部分组成（这里先看懂含义，详细字段后面会反复用到）：

| 部分 | 它是什么 |
|------|---------|
| `nodes: Tuple[NodeSpec, ...]` | 图上的节点。每个节点 = 一个角色（`node_id`）+ 一个 detector + 可选的一元条件（`where`） |
| `edges: Tuple[DependencyEdge, ...]` | 节点之间的有向关系边（时序 / 包含 / 起点包含 / 交叠 / 同段 / 否定，共 6 种） |
| `root: str` | 历史保留的退化字段。须填一个合法 `node_id`，但**当前引擎并不读它**——匹配从哪里铺开，由引擎按图结构自动决定，不以 `root` 为起点 |

> ⚠️ 注意区分"两种条件"：节点上的 `where` 管的是**单段事件自己**满足什么（比如"这段下跌的回撤要 ≥ 0.25"）；边管的是**两段事件之间**的关系（比如"突破要在下跌结束后 120 根 K 线内出现"）。这条分工线（一元 vs 二元）是整个框架的设计骨架，务必记牢。

---

## 六种关系边：节点之间能有哪些关系

边（`DependencyEdge`）回答的问题永远是同一个：**"src 这段事件和 dst 那段事件之间，是什么关系？"** 方向 `src → dst` 既是关系方向，也是引擎"先绑 src、再据此收窄 dst"的推进方向。

path2 提供了 6 种现成的边，覆盖了走势里最常见的几种关系。先看懂它们各自表达什么：

| 边类型 | 关系语义 | 什么时候用 |
|--------|---------|-----------|
| `TemporalEdge(src, dst, min_gap, max_gap)` | dst 在 src 之后，且间隔满足 `dst.start_idx − src.end_idx ∈ [min_gap, max_gap]` | 表达"先 A 后 B、相隔多久" |
| `ContainmentEdge(src, dst)` | src 完整包住 dst（`src.start ≤ dst.start` 且 `dst.end ≤ src.end`） | 一个大背景段里套着一个子事件 |
| `StartContainmentEdge(src, dst)` | src 只包住 dst 的**起点**（`src.start ≤ dst.start ≤ src.end`），dst 的终点不受约束 | 一个宽事件只需"开头落在背景段里"，至于它后面延伸到哪不管 |
| `OverlapEdge(src, dst)` | dst 从 src 内部某处起，一直延伸到 src 结束之后（两段部分交叠） | 表达"接力式"的部分重叠 |
| `EqualsEdge(src, dst)` | src 和 dst 占据**完全相同**的区间 | 同一段上叠加的两种不同事件 |
| `NegationEdge(src, dst, min_gap, max_gap)` | 在 src 锚定的窗口内**禁止**出现满足条件的 dst | 排除干扰、表达"这段时间里不能有……" |

> 💡 小贴士：`ContainmentEdge` / `StartContainmentEdge` / `OverlapEdge` / `EqualsEdge` 这四种纯靠区间几何判断，不带参数。`TemporalEdge` 和 `NegationEdge` 因为要描述"间隔范围"，所以带 `min_gap`（默认 `0`）和 `max_gap`（默认 `math.inf`）。

> 💡 `StartContainmentEdge` 和 `ContainmentEdge` 容易混：`ContainmentEdge` 要求 dst **整段**都被 src 包住（连 `dst.end ≤ src.end` 也得满足）；`StartContainmentEdge` **只看起点**——dst 从哪儿开始要落在 src 里，但 dst 的尾巴可以伸到 src 外面。当 dst 是一个宽事件、你又只关心"它是不是从某个背景段里起步"时，用后者；下面的完整示例里 `side → burst` 正是这种情况。

> ⚠️ 常见坑：`NegationEdge` 的语义是**反着的**——它表达的是"禁区"。落在窗口里的 dst 是"违禁品"，引擎会因此判定这次匹配不成立。被它指向的 dst 节点不会进入最终结果（它是约束，不是结构的一部分）。`NegationEdge` 还可以传一个 `inner_predicate`，进一步限定"什么样的 dst 才算违禁"。

关于这六种边的完整语义、边界判定、以及怎么挑选，详见 [guide/edges.md](guide/edges.md)。

---

## 嵌套事件：当一串小事件本身就该被当成"一个事件"

到目前为止，每个节点绑的都是**单个**事件实例。但有时你真正关心的对象，是"**连续好几个**同类小事件凑成的一坨"——比如"短时间内连着放量突破好几次"，这一**串**突破才是你想找的东西。

最自然的做法，是把"这一串"本身做成**一个事件**。这就是**嵌套事件（composite Event）**：一个事件的肚子里，还装着更小的子事件。

### 为什么需要它

举个具体的：一串密集突破点（`bo`，每个 `bo` 都是一根 K 线上的单点突破）。

过去框架里没有一个"实体"代表**整串**——你只能把一串散点 `bo` 硬绑在一起，想检查"这一串整体的属性"（一共几个、放量峰值多高），或者想把"这一串"当成一段画在图上、让别的事件去和它建立关系，都很别扭——因为根本没有一个对象叫"这一串"。

**嵌套事件就是给"这一串"造一个一等公民。** 以突破爆发为例，框架里有 `BurstEvent`：

- 它是一个普通的 `Event`，有自己的 `start_idx`（= 串首 `bo` 的起点）和 `end_idx`（= 串尾 `bo` 的终点）——所以它就是一段**宽事件**，能像下跌段、横盘段一样被引用、被画出来、被边连接。
- 它内部用 `members` 字段（一个 tuple，**存完整的 `BOEvent` 对象，不是 id**）装着组成它的那些 `bo`。
- 它在被检测出来时，就顺手把几个**整串的统计量**算好存成普通字段——`count`（成员数）、`distinct_pk`（突破的不同峰值数）、`max_vol_ratio`（最大放量）、`first_drought`（串首干涸期）。这样节点的 `where` 想检查整串属性时，直接 `W.attr("distinct_pk", ">=", 3)` 读字段即可，不用每次去遍历 `members`。

> 💡 一句话：**`BurstEvent` 让"一串 bo"从一堆散点，变成一个可以被引用、被画图、被一个 `where` 整体检查的宽事件。**

### 谁来生产它：`BurstDetector`

宽事件也得有 detector 去产出。`BurstDetector` 就干这件事——它**消费 `bo` 流**（不自己去 new 一个 `BODetector`，遵守"detector 各管各、不互相创建"的独立性原则），把密集的 `bo` 切成一段段**极大段**，每段打包成一个 `BurstEvent`：

```python
NodeSpec("burst",
         BurstDetector(max_span=20, min_bos=3),   # 切串参数走构造函数
         where=(("first_drought", W.attr("first_drought", ">=", 40)),
                ("distinct_pk",   W.attr("distinct_pk",   ">=", 3)),
                ("vol_spike",     W.attr("max_vol_ratio", ">=", 3.0))),
         consumes_stream="bo", label="突破爆发")
```

切串的口径很直白：把 `bo` 按起点排序，从第一个没被吃掉的 `bo` 作段首，往后吸纳所有"起点距段首 ≤ `max_span`"的 `bo`，贪心取到不能再吸为止、不回头；一段里成员数 ≥ `min_bos` 才产出。

这里有个清爽的分工要记住：

- **`BurstDetector` 只负责"切串 + 算统计量"**，切串参数 `max_span` / `min_bos` 走构造函数。
- **真正的阈值过滤交给节点的 `where`**——`first_drought` / `distinct_pk` / `max_vol_ratio` 这些阈值写在 `where` 里读字段，不传给 detector。

也就是说：detector 把"一坨够密的 bo"端上来，`where` 再决定这坨够不够格当 `burst`。这正是全文那条"一元 `where` vs 二元 edge"分工线的体现——只不过这里 `where` 检查的是一个**嵌套宽事件的整体属性**。

### 基类提供的通用嵌套协议

`BurstEvent` 之所以能暴露内部结构，是因为 `Event` 基类给所有事件准备了一套**嵌套协议**（普通叶子事件用不上、默认返回空，所以你完全不必为它们操心）：

- `child_slots()`——这个事件由哪些"主"子事件构成（用于展平 / 遍历）。叶子事件返回空字典。
- `child(name)`——按名字取**单个**子事件，例如 `'first_bo'` / `'last_bo'`（串首 / 串尾那个 `bo`）。给 selector、边端点用。
- `children(name)`——按名字取**一组**子事件，例如 `children("members")` 拿到整串 `bo`。
- `descendant_leaves`——一路递归展平到没有子事件的最底层 atom。

> 💡 叶子事件（普通 `BOEvent`、`TrendSegment`……）的行为**完全没变**——基类只是多了几个默认返回空的方法。嵌套协议只对真正装着子事件的复合事件（如 `BurstEvent`）才有意义。

---

## 完整示例：底部反转突破爆发

下面把前面所有概念串成一个真实可跑的 `PatternSpec`。这个走势想表达的是：**先有一段大幅下跌 → 随后横盘 → 横盘期间出现一串连续放量突破 → 突破后紧跟一次回踩确认。**

它有 **5 个节点**，跟着注释读，你会看到"节点 + where + 嵌套事件 + edges"是怎么协同的（节点构造统一用**关键字参数**写 `where=` / `consumes_stream=`，避免位置参数搞错）：

```python
from path2.dag import (
    NodeSpec, PatternSpec,
    TemporalEdge, StartContainmentEdge,
    where as W, analyze,
)
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.trend import TrendSegmentDetector
from path2.atoms.throwback import ThrowbackDetector

# down / side 各自实例化一个独立的 TrendSegmentDetector（角色不同、实例也不同）
down_det = TrendSegmentDetector(ma_period=20)
side_det = TrendSegmentDetector(ma_period=20)

spec = PatternSpec(
    pattern_id="bottom_breakout_burst",
    display_name="底部反转突破爆发",
    nodes=(
        # 节点 "bo"：单点突破事件。它是一个"孤立 role"——图里没有任何边连它，
        # 只作为密度流源层：给 burst / tb 当输入流，也能独立扫描 / 渲染。
        NodeSpec("bo", BODetector()),
        # 节点 "down"：一段下跌（regime=down 且回撤 >= 0.25）
        NodeSpec("down", down_det,
                 where=(("regime",   W.attr("regime", "==", "down")),
                        ("drawdown", W.attr("drawdown", ">=", 0.25))),
                 label="下跌段"),
        # 节点 "side"：一段横盘（独立的另一个 TrendSegmentDetector 实例）
        NodeSpec("side", side_det,
                 where=(("regime", W.attr("regime", "==", "sideways")),),
                 label="横盘段"),
        # 节点 "burst"：突破爆发。BurstDetector 消费 bo 流、切串聚合成一个嵌套宽事件 BurstEvent；
        # where 三条直接读整串统计量（first_drought / distinct_pk / max_vol_ratio）
        NodeSpec("burst",
                 BurstDetector(max_span=20, min_bos=3),
                 where=(("first_drought", W.attr("first_drought", ">=", 40)),
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", 3)),
                        ("vol_spike",     W.attr("max_vol_ratio", ">=", 3.0))),
                 consumes_stream="bo", label="突破爆发"),
        # 节点 "tb"：回踩确认。它也消费 bo 流（注意：吃的是单点 BOEvent，不是 BurstEvent）
        NodeSpec("tb", ThrowbackDetector(),
                 consumes_stream="bo", label="回踩确认"),
    ),
    edges=(
        # 下跌结束后 1~120 根内出现突破（burst 前 lookback 内有大幅下跌）
        TemporalEdge("down", "burst", min_gap=1, max_gap=120),
        # 横盘段要包住 burst 的"起点"（burst.start 落在横盘段内即可，尾巴不管）
        StartContainmentEdge("side", "burst"),
        # 突破爆发紧接着就是回踩（burst.end = 串尾 bo 的终点，末突破后一根开始回踩）
        TemporalEdge("burst", "tb", min_gap=1, max_gap=1),
    ),
    root="burst",   # 退化字段，引擎不读，填一个合法 node_id 即可
)

result = analyze(spec, df)
print(f"命中 {len(result.matches)} 次")
for m in result.matches:
    print(m.start_idx, m.end_idx, m.role_index.keys())
```

这个例子里有几个细节值得专门点一下：

- **`burst` 是一个嵌套宽事件**：它不是某个单点，而是"一串 bo"聚合成的一段（`burst.start` = 串首 bo 的起点，`burst.end` = 串尾 bo 的终点）。所以三条边都连到 `burst` 这个**本体**上，而不是连到某个 bo 散点。也正因为它是宽事件，`side → burst` 用的是 `StartContainmentEdge`（只要求 `burst` 的起点落在横盘段内）——若改用 `ContainmentEdge`，会额外要求串尾 bo 也落在横盘段内，那就把命中范围改严了。

- **`down` / `side` 各持独立实例，引擎自动消歧 `event_id`**：两个节点都用 `TrendSegmentDetector`，但它们是**两个不同的对象**。两个实例产出的事件 `class_id` 都是 `'trend'`，如果 `event_id` 前缀都用 `'trend'` 就会撞。引擎在跑流前会自动处理这件事（见下方说明），给两个实例分别打上 `trend0` / `trend1` 前缀——**这件事你通常不用管**。

- **`bo` 是孤立流源层，半成品命中会被自动过滤**：`bo` 节点没有任何边连它，它只是一层"密度信号"——既给 `burst` / `tb` 当输入流，又能在 K 线上把所有 bo 单独画出来。但它不参与任何配对。如果不管它，引擎会吐出一堆"只含 bo 这一个角色、根本没凑成完整形态"的半成品命中（语义垃圾）。引擎在出口处会**自动把这些半成品过滤掉**（见下方说明），所以 `bo` 不会污染真正的形态匹配。

### 顺带一提：`source_tag` 自动消歧（多数情况你不用管）

承上：当同一个 detector 类被实例化成**两个不同对象**、又都产出同一 `class_id` 的事件时，它们的 `event_id` 前缀就会撞。引擎在跑流前（`run_streams` 顶部）会扫一遍：发现同一 `class_id` 有 ≥2 个不同 detector 对象，就按节点首现序，给那些没手动设过前缀的实例自动填 `trend0` / `trend1`（这个 per-instance 前缀钩子叫 `source_tag`，默认 `None` 时回退用 `class_id`）。

强调一下它的安全边界，免得你以为这是个负担：

- **单实例、共享同一个对象、或你已手动命名**的情况，它一律**不动**——是个 no-op，`event_id` 逐字向后兼容，且重复跑结果一致（幂等）。
- 只有"同类多实例"这一种情况才触发自动编号。
- 万一某个 detector 出现了多实例、却连 `source_tag` 钩子都没有，引擎会**直接报错**，而不是悄悄让 `event_id` 撞上。

### 顺带一提：孤立 role 与出口过滤

承上：`bo` 这种"图里没有任何边连它"的节点，叫**孤立 role**。引擎在 `analyze` 出口处会**自动**从 `spec.edges` 推算出哪些节点是孤立无边的，然后把"`role_index` 的角色全部落在孤立集合里"的命中——也就是那些只凑出 bo、没凑成完整形态的半成品——一律丢弃。判据完全从边自动推出，你不需要给 bo 做任何标记。

这套机制的价值：让 bo 可以舒舒服服地当一层**独立的密度流源**（既喂下游、又能单独渲染），同时一点也不污染真正的形态匹配。

逐条把这 7 个约束翻译成上面这张 DAG 的完整推导，见 [example-bottom-breakout-burst.md](example-bottom-breakout-burst.md)。

---

## 引擎给你什么：读懂返回结果

调用 `analyze(spec, df)` 得到一个 `AnalysisResult`，它有三样东西：

- `events`——所有节点的事件流平铺到一起（你声明的每个 detector 都跑了，这里是它们产出的全部事件）。其中会包含孤立流源层（如示例里的 `bo`）。注：**共享同一个 detector 的流会按身份去重、只计一遍**，不会因为多个节点指向同一份产出而重复堆叠。
- `matches`——真正的**命中**列表，每项是一个 `PatternMatch`。
- `spec`——把声明本身带回来（方便面板等下游使用）。

每个 `PatternMatch` 本身就**继承自 `Event`**（所以它也有 `start_idx` / `end_idx`），此外还带：

- `role_index`——`node_id → 绑定实例` 的映射。普通节点和嵌套节点都对应**单个 `Event`**（例如示例里的 `burst` 就是一个嵌套宽事件，它内部的成员 bo 通过 `event.children("members")` 取）。这是你"按角色取出命中里各段"的入口。
- `children`——这次命中里所有绑定实例的扁平列表（按 `start_idx` 升序）。
- `predicate_trace`——**可追溯的诊断**。它告诉你每个 `where` 子句在这次命中里通没通过（`where_results`），以及每条边的实测情况和两端实例（`edge_results` 里的 `EdgeWitness`，含实测 gap / overlap）。排查"为什么这里没命中 / 凭什么命中了"时，看它就对了。

关于 `analyze()` 调用、`AnalysisResult` / `PatternMatch` / `role_index` / `predicate_trace` / `to_topology()` 的完整契约，详见 [guide/matching-and-results.md](guide/matching-and-results.md)。

> 💡 一句话总结：**声明（PatternSpec）进，结果（AnalysisResult）出；结果里 `role_index` 让你按角色取段，`predicate_trace` 让你看清每一步通没通过。**

---

## 什么时候该用 path2

如果你遇到下面任一情况，path2 就是为你准备的：

- 你要在 K 线序列上识别**多段事件的结构性组合**（先下跌、再横盘、再连续突破、最后回踩）。
- 你想用**声明式的图**代替手写的嵌套循环，让"想表达什么"和"怎么找出来"解耦。
- 你需要**可追溯的诊断**：到底是哪个 `where` 没过、某条边实测的间隔是多少。
- 你想把走势结构投影成**拓扑视图**（`PatternSpec.to_topology()`）交给前端渲染。

---

## 文档地图

读完本页，按需深入：

| 文档 | 它讲什么 |
|------|---------|
| [getting-started.md](getting-started.md) | 5 分钟上手：从构造 DataFrame、写最小 `PatternSpec`、调引擎到读结果，全流程跑一遍 |
| [concepts.md](concepts.md) | 概念篇：Event / Detector / 图模型的来龙去脉 |
| [guide/building-blocks.md](guide/building-blocks.md) | 积木层指南：`path2.atoms` 探测器库（BO / Burst / Trend / Throwback / Platform / Distribution）与 `path2.calc` 纯数值函数逐个讲透 |
| [guide/edges.md](guide/edges.md) | 关系边指南：6 种 `DependencyEdge` 的结构职责与语义判定详解 |
| [guide/matching-and-results.md](guide/matching-and-results.md) | 匹配与结果：`analyze()` 与 `AnalysisResult` / `PatternMatch` / `role_index` / `predicate_trace` / `to_topology()` 契约 |
| [guide/authoring-patterns.md](guide/authoring-patterns.md) | 编写模式：把一组文字约束系统性地落成 DAG 声明的方法 |
| [example-bottom-breakout-burst.md](example-bottom-breakout-burst.md) | 完整 worked example：以 `bottom_breakout_burst` 为蓝本，走通 7 约束到 DAG 声明 |
| [api-reference.md](api-reference.md) | API 速查表：各类型、字段、默认值一览（写代码时随手查） |

---

## 快速安装与运行

```bash
uv sync
uv run python scripts/path2/run_path2_web.py   # 可视化 UI（扫描 + K 线走势图 + 拓扑面板 + 诊断侧栏）
```

这个脚本会同时拉起 FastAPI 后端（`127.0.0.1:8000`）和 Vite 前端（`127.0.0.1:5173`），界面在浏览器里打开。

依赖方面：**核心库只依赖 `pandas` 与 `numpy`**；web UI 后端用 FastAPI / uvicorn，前端用 Vue3 + Vite + ECharts。
