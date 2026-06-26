# path2 API Reference

> 这是一份**速查手册**。如果你是第一次接触 path2，建议先读完本页开头的「5 分钟先建立直觉」，对整体心智模型有个印象，再把后面的分节表格当字典来查——遇到某个类、某个字段不确定时翻回来对照即可。

---

## 5 分钟先建立直觉

path2 是一个**独立的"走势表达"框架**。它要解决的问题很具体：

> 你脑子里有一个 K 线走势的"故事"——比如"先有一段大跌，然后在底部横盘，横盘里连续突破了好几个高点，最后还回踩确认了一下"。
> path2 让你把这个故事**用代码声明出来**，然后丢给一段历史 K 线，它会告诉你：这段 K 线里，哪些位置真的发生了这个故事。

要表达这种"故事"，path2 用四个核心概念，按从下到上的顺序：

> 🧩 **进阶预告（嵌套事件）**：path2 里一个事件内部还能装更小的事件——比如"一串密集突破"本身被打包成**一个**宽事件，内部装着组成它的那一根根突破。这叫**嵌套事件（composite event）**。它让"这一串"终于能像普通事件那样被引用、被画在图上、被一个条件整体检查。本文档里 `BurstEvent`（§8）就是它最典型的例子；如果你第一遍读时被它绕到了，记住这一句话就够：**嵌套事件 = 一个事件，肚子里还装着一组子事件。**


1. **Event（事件）**——故事里的一个"情节片段"。比如"一段下跌"是一个 Event，"一次突破"是一个 Event。每个 Event 都知道自己在 K 线里**从第几根 bar 到第几根 bar**（`start_idx` / `end_idx`）。
   *打个比方*：Event 就像电影里的一个镜头，有明确的起止时间码。

2. **Detector（探测器）**——一台"情节生产机"。喂给它一段 K 线 DataFrame，它就吐出一串某种类型的 Event。比如 `BODetector` 专门吐"突破"事件，`TrendSegmentDetector` 专门吐"趋势段"事件。
   *打个比方*：Detector 像一个专职剪辑师，只负责从原片里剪出某一类镜头。

3. **PatternSpec（模式声明）**——你把整个"故事"写下来的地方。它说明：这个故事由哪几个角色（节点）组成、角色之间有什么先后/包含关系（边）。它是**纯数据**，不含任何匹配算法。
   *打个比方*：PatternSpec 就是剧本——只描述"谁先出场、谁包着谁"，不负责真正去演。

4. **analyze()（匹配引擎入口）**——真正去"对剧本找演员"的导演。你把剧本（PatternSpec）和一段 K 线交给它，它返回 **AnalysisResult**，里面装着所有命中的故事实例。

一句话串起来：**Detector 产出 Event 流 → PatternSpec 声明它们怎么组合成一个故事 → analyze() 在 K 线上找出所有符合的实例。**

> 💡 **你现在应该理解了**：path2 的核心分工是"生产事件"（Detector）和"组合事件"（PatternSpec + 引擎）两件事。下面所有的类，都是围绕这两件事的细节展开。

本文档按模块分节，覆盖所有公共符号。所有代码示例以 `path2_apps/bottom_breakout_burst`（一个真实走势包：底部连续突破）为参照。

---

## 目录

1. [path2 顶层 — 事件基类与驱动入口](#1-path2-顶层--事件基类与驱动入口)
2. [path2.dag.nodes — 怎么声明一个"角色"](#2-path2dagnodes--怎么声明一个角色)
3. [path2.dag.edges — 怎么声明角色之间的关系](#3-path2dagedges--怎么声明角色之间的关系)
4. [path2.dag.where — 给单个角色加条件的便利函数](#4-path2dagwhere--给单个角色加条件的便利函数)
5. [path2.dag.spec — 把角色和关系打包成完整故事](#5-path2dagspec--把角色和关系打包成完整故事)
6. [path2.dag.engine — 真正去匹配](#6-path2dagengine--真正去匹配)
7. [path2.dag.result — 匹配结果长什么样](#7-path2dagresult--匹配结果长什么样)
8. [path2.atoms — 开箱即用的 Detector 库](#8-path2atoms--开箱即用的-detector-库)
9. [path2.calc — 纯数值计算函数库](#9-path2calc--纯数值计算函数库)
10. [完整示例](#完整示例)

---

## 1. path2 顶层 — 事件基类与驱动入口

**这一节是什么**：path2 最底层的三个东西——所有事件的基类 `Event`、所有探测器要遵守的接口 `Detector`、以及把探测器跑起来的函数 `run`。写一个新走势包时，你几乎总会用到它们。

```python
from path2 import Event, Detector, run
```

---

### `Event`

**它是什么**：所有具体事件类的"祖先"。任何你想表达的情节片段（一次突破、一段趋势……）都得继承它。继承后，你的事件就自动拥有"我在 K 线哪段"这个能力。

```python
@dataclass(frozen=True)
class Event(ABC):
    event_id: str
    start_idx: int
    end_idx: int
```

它是**冻结的 dataclass**（`frozen=True`，构造后不可改），这保证了事件一旦产出就不会被下游偷偷篡改。

**写子类时的两条规矩**（违反会报错）：
- 子类必须也加 `@dataclass(frozen=True)`；
- 如果子类自定义了 `__post_init__`，第一行必须调用 `super().__post_init__()`，否则会跳过框架的合法性自检。

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | `str` | 事件唯一标识符，同一次 `run()` 内不允许重复 |
| `start_idx` | `int` | 事件在 df 中的起始行索引（含），须 >= 0 且 <= `end_idx` |
| `end_idx` | `int` | 事件在 df 中的结束行索引（含），须 >= `start_idx` |

> 💡 **小贴士**：单根 bar 的事件（如一次突破）令 `start_idx == end_idx` 即可——它依然是一个"有起止"的区间，只是长度为 1。

**怎么标识"我是哪种事件"——`class_id`**

每个 Event 子类必须声明一个**类级常量** `class_id`，作为这种事件的全局唯一名字（不是实例字段，是写在类上的字符串）：

```python
@dataclass(frozen=True)
class BOEvent(Event):
    class_id = "bo"      # 突破事件
    ...
```

实际项目里：`BOEvent.class_id == "bo"`、`TrendSegment.class_id == "trend"`、`BurstEvent.class_id == "burst"`、`ThrowbackEvent.class_id == "tb"`。

- 框架内部有一张 **class_id 注册表**：两个不同的类想用同一个 `class_id`，会在**类定义那一刻**就抛 `ValueError`（防你不小心撞名）。
- `class_id` 还充当事件 `event_id` 前缀、面板上色的依据（`to_topology()` 读的就是它，见 §5）。
- 这是事件唯一的"类型身份"。**path2 没有 `event_type()` 这种方法**——子类靠 `class_id` 标识自己，不靠类名小写。

**嵌套协议（composite event）**

Event 基类还提供了一组"打开内部结构"的方法，专门给**嵌套事件**（一个事件肚子里装着子事件，如 `BurstEvent` 装着一串 `BOEvent`）用：

| 方法 | 说明 |
|---|---|
| `child_slots()` | 返回这个事件的"主 child 集"（非冗余、用于展平遍历）。**叶子事件返回 `{}`** |
| `child(name)` | 按名字取**单个**子事件，如 `BurstEvent` 的 `'first_bo'` / `'last_bo'`（取串首/串尾那根突破）。给边的端点 selector 用 |
| `children(name)` | 按名字取**一组**子事件，如 `BurstEvent` 的 `'members'`（整串突破） |
| `descendant_leaves` | 递归展平到没有 child 的最底层 atom 事件 |

> 💡 **普通用户基本不用管这组方法**：如果你写的是一个普通"叶子"事件（一次突破、一段趋势），`child_slots()` / `descendant_leaves` 默认返回空，`child()` / `children()` 默认抛 `KeyError`——总之普通叶子事件你完全不必碰这组方法，行为和以前一样。**只有当你想做嵌套事件**（把一组子事件打包成一个父事件）时，才需要覆盖它们——`BurstEvent`（§8）就是范例。

---

### `Detector`

**它是什么**：一个"协议"（Protocol），规定了"凡是想当探测器的类，必须提供一个 `detect` 方法"。你不需要去 `继承` 它——只要你的类长得像它（有 `detect` 方法），就被当作合法的 Detector。

```python
@runtime_checkable
class Detector(Protocol):
    def detect(self, source: Any) -> Iterator[Event]: ...
```

`detect` 接收数据源（通常是 K 线 df），**逐个 yield 出 Event**。引擎不会直接调 `detect`，而是通过下面的 `run()` 来驱动它。

> 💡 **为什么用 Protocol 而不是基类**：这样写 Detector 更自由——你的类不必背上继承包袱，只要"行为像"就行（鸭子类型）。

---

### `run`

**它是什么 / 什么时候用**：把一个 Detector 真正跑起来、拿到事件流的标准入口。它在流式 yield 事件的同时，顺手帮你做几项"体检"，及早抓出 Detector 写错的 bug。

```python
def run(detector, *source) -> Iterator[Event]
```

当 `RUNTIME_CHECKS` 开启时，`run` 会跨事件检查：`end_idx` 必须升序、`event_id` 在单次 `run` 内唯一、yield 出来的必须是 `Event` 实例。任何一条不满足都会抛错。

| 参数 | 说明 |
|---|---|
| `detector` | 实现 Detector 协议的生产者实例 |
| `*source` | 传给 `detector.detect` 的数据源，通常是 `df`，或 `(上游事件流, df)` |

```python
from path2 import run
from path2.atoms.breakout import BODetector

bo_det = BODetector(total_window=10)
for event in run(bo_det, df):
    print(event.start_idx, event.vol_ratio)
```

> 💡 **小贴士**：日常写走势包时，你**通常不用手动调 `run`**——`analyze()` 会在内部替你把所有节点的 detector 都跑一遍。`run` 主要用于单独调试某个 detector。

---

## 2. path2.dag.nodes — 怎么声明一个"角色"

**这一节是什么**：故事里的每个"角色"叫一个 **节点（Node）**。这一节讲怎么声明节点——用 `NodeSpec`。如果某个角色不是"一个事件"而是"一串连续的同类事件"（比如"重复出现 N 次的那种角色"），框架还提供一个可选的 `KleeneSpec`。

> ℹ️ **关于 `KleeneSpec` 先说清一件事**：它是框架**仍然支持**的通用机制，但当前示例 app `bottom_breakout_burst` **已经不再用它**了——里面那个"密集突破串"改用了更干净的**嵌套事件** `BurstEvent`（§8）。如果你照着 `KleeneSpec` 去理解本 app，会对不上代码。下面会把这两条路讲清楚。

```python
from path2.dag import NodeSpec, KleeneSpec, MatchContext
```

> 先建立直觉：一个 `NodeSpec` = **「这个角色叫什么」+「它的事件从哪来」+「它要满足什么自身条件」**。三件事凑齐，一个角色就声明好了。

---

### `NodeSpec`

**它是什么**：一个角色的完整声明。把"角色名 + 绑定的 detector + 该角色自身要满足的约束 + 可选的成串规格"打包在一起。

```python
@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    detector: object
    where: Tuple[Tuple[str, WherePredicate], ...] = ()
    kleene: Optional[KleeneSpec] = None
    consumes_stream: Optional[str] = None
    label: str = ""
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_id` | `str` | 这个角色的唯一名字，后面在 `edges` 里用它来引用（`src`/`dst`） |
| `detector` | `object` | 这个角色的事件来源；引擎按 `consumes_stream` 决定调用 `detect(df)` 还是 `detect(上游流, df)`。事件类型由 `detector.event_cls.class_id` 提供（面板上色读它，见 §5） |
| `where` | `Tuple[Tuple[str, WherePredicate], ...]` | 该角色**自身**要满足的条件列表，多条之间是 AND（都要满足）；每条是 `(clause_id, fn)`。`clause_id` 同一 node 内须唯一（重复在 `PatternSpec` 构造时抛 `ValueError`），跨 node 可重名 |
| `kleene` | `Optional[KleeneSpec]` | `None` = 这个角色绑定**单个**事件；非 `None` = 绑定**一串**同类事件（框架仍支持的通用机制，当前示例 app 已不用，见下方 `KleeneSpec`） |
| `consumes_stream` | `Optional[str]` | `None` = 探测器直接吃 df 产事件；填某个上游 `node_id` = 吃那个节点产出的事件流（见下方"流源 / 消费者"） |
| `label` | `str` | 人类可读名（面板显示用），默认空字符串 |

> 💡 **注意 NodeSpec 没有 `event_type` 字段**：节点要展示成什么类型、面板怎么上色，全部由它绑的 detector 的 `event_cls.class_id` 决定——你不用、也不能再在 NodeSpec 上单独写事件类型。

> ⚠️ **常见坑（关于 `where`）**：`where` 里的条件只能看**这个角色自己**的属性，**绝对不能去读别的角色**（即不能读 `ctx.bound`）。"两个角色之间的关系"是边（edge）的活，不是 `where` 的活。引擎在剪枝阶段会用一个叫 `_TRIPWIRE` 的哨兵把 `bound` 替换掉，一旦你越界去读，立刻抛 `RuntimeError`。这条分工（一元约束归 `where`、二元关系归边）是整个框架的骨架，记牢它能少踩一大堆坑。

```python
from path2.dag import NodeSpec
from path2.dag.where import attr
from path2.atoms.breakout import BODetector

NodeSpec(
    node_id="bo",
    detector=BODetector(total_window=10),
    where=(
        ("vol_ok", attr("vol_ratio", ">=", 2.0)),
    ),
    label="突破点",
)
```

> 💡 **小贴士（一身多角）**：同一种 detector 可以扮演剧本里不同的角色。比如声明 `down`（下跌段）和 `side`（横盘段）两个角色——它们都用 `TrendSegmentDetector`、靠不同的 `where`（`regime=="down"` vs `=="sideways"`）区分。
> 在当前示例 app `bottom_breakout_burst` 里，`down` 和 `side` 用的是**两个各自独立的** `TrendSegmentDetector` 实例（不是同一个对象）。为什么要各持一份？这样引擎能自动给两边产出的事件打上不同的 `event_id` 前缀（`trend0` / `trend1`），避免它们的 id 撞车——这套"同类多实例自动消歧"机制叫 `source_tag`，详见 §8 `TrendSegmentDetector`。

---

### 流源 / 消费者（`consumes_stream`）

**一句话**：detector 之间可以排成一条**流水线**——最上游的 detector 直接吃原始 K 线，下游的 detector 吃上游 detector 吐出来的事件流，再加工。

`NodeSpec.consumes_stream` 就是声明"这个节点的 detector 吃什么"：

- `None`（默认）= 直接吃原始 df。这种节点叫**流源**（如 `bo` / `down` / `side`，它们从零扫 K 线）。
- 填某个上游 `node_id` = 吃那个节点产出的事件流。这种节点叫**消费者**（如 `burst` 和 `tb` 都填 `consumes_stream="bo"`，吃 `bo` 流）。

引擎据此自动排好 detector 的先后顺序，并决定怎么调它：流源调 `detect(df)`，消费者调 `detect(上游流, df)`。这就让你能把"突破 → 把突破切成串 / 评回踩"这样的加工链条声明出来，而不必让每个 detector 都从头扫一遍 df。

> 💡 引擎还顺手做了**去重**：同一个 detector 对象吃同一条上游流时只物化一次。多个节点共享同一个 detector 时，它们拿到的是同一份事件 list（不重复算）。

---

### `KleeneSpec`

**它是什么 / 什么时候用**：当一个角色不是"一个事件"而是"**连续的一串**同类事件"时，给它配 `KleeneSpec`。"Kleene 闭包"是个正则表达式术语，这里你可以理解成"重复 N 次的那种角色"。

配了 `KleeneSpec` 之后，引擎会从事件流里抓出一段**连续子序列**，把整段当成一个绑定单元，参与外层故事的匹配。相应地，这个角色在结果里的值就从"单个事件"升级为"一个事件元组"。

> ✅ **框架仍支持** ❌ **当前示例 app 不用**：`KleeneSpec` 这套"求解期把一串同类事件绑成序列"的机制依然健在、可用，适合你在**自己的走势包里**表达"重复出现 N 次的角色"。但 `bottom_breakout_burst` 里那个"密集突破串"已经换了一条路——改用嵌套事件 `BurstEvent`（由 `BurstDetector` 在产事件阶段就把一串突破打包成一个宽事件，见 §8）。两条路的取舍：Kleene 把"成串"留到匹配期再算；嵌套事件把"成串"提前到产出期算好，整串变成一个能被引用、能被画图、能被单个 `where` 整体检查的实体。下面的字段说明和示例**仅用于说明 Kleene 用法**，本 app 不这么写。

```python
@dataclass(frozen=True)
class KleeneSpec:
    min_count: int = 1
    max_count: float = math.inf
    span_from_first: Optional[Tuple[int, float]] = None
    aggregate_where: Tuple[Tuple[str, Callable[[Tuple, MatchContext], bool]], ...] = ()
    endpoint_for_edges: str = "first"
    greedy: bool = True
```

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `min_count` | `int` | `1` | 这串至少要有几个事件（含），须 >= 1 |
| `max_count` | `float` | `math.inf` | 这串最多几个（含）；引擎当前只支持 `math.inf`（填有限上界会抛 `NotImplementedError`） |
| `span_from_first` | `Optional[Tuple[int, float]]` | `None` | "成簇"窗口 `(lo, hi)`：要求每个成员满足 `e.start_idx - 串首.start_idx ∈ [lo, hi]`，即整串不能拉得太散；`None` 表示不约束 |
| `aggregate_where` | `Tuple[Tuple[str, Callable], ...]` | `()` | 对**整串**的聚合条件列表，多条 AND；每个 fn 签名是 `(seq: tuple, ctx: MatchContext) -> bool` |
| `endpoint_for_edges` | `str` | `"first"` | 外层的边连到这个成串节点时，取串的哪一端来算关系：`'first'` 取串首、`'last'` 取串尾 |
| `greedy` | `bool` | `True` | 贪心地取尽可能长的连续段（默认）；`False` 会抛 `NotImplementedError` |

> 💡 **`span_from_first` 怎么理解**：它管的是"这串事件要挤在一起"。比如 `(0, 20)` 意思是"从第一个成员算起，往后 20 根 bar 之内的同类事件才算同一串"——超出就不再纳入，保证"连续"是真的密集发生，而不是零零散散拖了一年。

> 💡 **`endpoint_for_edges` 怎么理解**：成串节点是一段区间，但边只能连一个点。这个字段就是回答"外层边连哪个点"——`'first'` 取串首、`'last'` 取串尾。

```python
# 仅示意 Kleene 用法（当前 app 不这么写）
from path2.dag import KleeneSpec
from path2.dag.where import count, distinct, any as W_any

KleeneSpec(
    min_count=3,
    span_from_first=(0, 20),
    aggregate_where=(
        ("min_len",   count(">=", 3)),
        ("dist_keys", distinct("broken_peak_ids", ">=", 3)),
        ("any_spike", W_any("vol_ratio", ">=", 3.0)),
    ),
    endpoint_for_edges="last",
)
```

---

### `MatchContext`

**它是什么**：每个 `where` 条件在求值时，都会拿到一个"上下文小包裹"，里面装着它可能需要的东西——完整的 K 线、运行时参数等。你**只读它、从不自己构造它**（`analyze()` 会替你造好并注入）。

```python
@dataclass(frozen=True)
class MatchContext:
    df: object
    params: object
    bound: object = None
```

| 字段 | 说明 |
|---|---|
| `df` | 完整行情 DataFrame，供 `where` 谓词回看历史数据 |
| `params` | 透传自 `analyze()` 的 `params` 参数，供 `where` 读取阈值 |
| `bound` | 跨节点 `where` 的预留扩展（当前 app 未使用），默认 `None` |

> ⚠️ 前面说过的坑再强调一次：剪枝期 `bound` 会被哨兵替换，`where` 里读它会抛错。把它当作"现在别碰"的字段即可。

---

### `WherePredicate`（类型别名）

**它是什么**：所有 `where` 条件函数的"统一长相"。任何节点级条件，本质都是一个"接收候选 + 上下文，返回真/假"的函数。

```python
WherePredicate = Callable[[Union[Event, Tuple[Event, ...]], MatchContext], bool]
```

它接受"已绑候选"（普通节点是单个 `Event`，Kleene 节点是 `Tuple[Event, ...]`）和 `MatchContext`，返回 `bool`。你一般不用手写它——第 4 节的便利函数（`attr`、`count` 等）会替你生成。

---

## 3. path2.dag.edges — 怎么声明角色之间的关系

**这一节是什么**：故事里的角色不是孤立的——"下跌**在**突破**之前**"、"横盘**包着**突破"。这些"角色之间的关系"就用**边（edge）**来声明。每种关系是一个边类。

```python
from path2.dag import (
    TemporalEdge, ContainmentEdge, StartContainmentEdge, OverlapEdge,
    EqualsEdge, NegationEdge,
)
```

> 先建立直觉：一条边永远是 `src → dst` 有方向的。这个方向同时定义了三件事：**谁先出场**（拓扑序，src 先）、**引擎按什么顺序去找候选**、**面板上箭头朝哪画**。所有边都是冻结 dataclass，可以当字典的 key。

下面六种边，先按"想表达什么关系"挑：

| 想表达的关系 | 用哪个边 |
|---|---|
| A 结束后过一段时间，B 才开始（先后） | `TemporalEdge` |
| 大区间 A 把小区间 B 整个包住（包含） | `ContainmentEdge` |
| 大区间 A 只包住小区间 B 的**起点**（不管 B 的终点） | `StartContainmentEdge` |
| B 从 A 内部开始、伸到 A 之后（部分交叠） | `OverlapEdge` |
| A 和 B 占据完全相同的区间（同段） | `EqualsEdge` |
| A 锚定的某个窗口内**禁止**出现 B（否定） | `NegationEdge` |

---

### `DependencyEdge`（抽象基类）

**它是什么**：所有边的共同祖先。你一般不直接用它，但了解它能帮你理解"为什么加一种新关系这么容易"——引擎只认基类的三个多态接口，对具体边类型零分支。

```python
@dataclass(frozen=True)
class DependencyEdge(ABC):
    src: str
    dst: str
    src_selector: Optional[str] = None   # compare=False，不参与边身份
    dst_selector: Optional[str] = None   # compare=False，不参与边身份
```

| 字段 | 说明 |
|---|---|
| `src` | 源节点 `node_id`（拓扑序上先于 `dst`） |
| `dst` | 目标节点 `node_id` |
| `src_selector` / `dst_selector` | 端点 selector：当你想让边连到的不是节点的"整个事件"，而是它**内部的某个子事件**时用（见下方 `Child`）。默认 `None` = 连整个事件 |

**端点也可以连到子事件——`Child` selector**

边的 `src` / `dst` 既可以传普通字符串（连整个事件），也可以传一个 `Child(node, key)`（连那个节点对应事件的某个**子事件**）：

```python
from path2.dag.edges import Child, ContainmentEdge

# Child 机制的通用演示：让边连到子事件，而非节点的整个事件
ContainmentEdge(src="window", dst=Child("combo", "first_leg"))
```

> ⚠️ **注意**：这是 `Child` 机制的通用演示，非本 app 真实边。本 app 的 `side → burst` 用 `StartContainmentEdge` 连 `burst` 本体（不用 `Child`）。

边在构造时（`__post_init__`）会自动把 `Child` 拆成 `(dst="burst", dst_selector="first_bo")`，所以 spec 的校验、拓扑图构建看到的依然是干净的字符串 `node_id`，而 selector 只在真正取端点事件时生效。selector **不参与边的身份**：两条只是 selector 不同、`src`/`dst` 相同的边，在拓扑图里算同一条边。

**三个多态接口**（每个子类各自实现，这就是它们的差异所在）：

| 方法 | 签名 | 说明 |
|---|---|---|
| `satisfies` | `(e_src: Event, e_dst: Event) -> bool` | 充要判定：给定一对候选，本边关系是否成立 |
| `feasible_window` | `(e_src: Event) -> tuple[float, float]` | 剪枝钩子：给定 `e_src`，返回 `e_dst.start_idx` 的可行区间 `[lo, hi]`，让引擎不用全表扫 |
| `signature_fields` | `() -> tuple[str, ...]` | 声明 `satisfies`/`feasible_window` 用到了 `e_src` 的哪些字段 |

> ⚠️ **常见坑**：`NegationEdge.satisfies` 返回 `True` 表示"违禁了"，语义和其它子类**正好相反**——其它边 `True` 表示"关系成立"。详见 `NegationEdge` 一节。

---

### `TemporalEdge`

**它是什么 / 什么时候用**：表达"先后"关系——`dst` 必须在 `src` 结束后的某个 gap 范围内开始。这是最常用的边。

```python
@dataclass(frozen=True)
class TemporalEdge(DependencyEdge):
    src: str
    dst: str
    min_gap: int = 0
    max_gap: float = math.inf
    strict: bool = field(default=False, kw_only=True)
```

判据是 `gap = dst.start_idx − src.end_idx`，要求 `gap ∈ [min_gap, max_gap]`。

| 字段 | 默认 | 说明 |
|---|---|---|
| `min_gap` | `0` | gap 下界（含），须 >= 0；填 `1` 就表示 dst 必须在 src 真正结束**之后**才开始 |
| `max_gap` | `math.inf` | gap 上界（含）；填有限值就约束了"回看窗口"有多长 |
| `strict` | `False` | `True` 启用 next 语义：src 与 dst 之间不能有更早的同类 dst（**仅限关键字传参**，防位置参数错位） |

> ⚠️ `min_gap < 0` 或 `min_gap > max_gap` 会在构造时直接抛 `ValueError`。

```python
# 下跌段结束后、突破爆发前 120 根 bar 内（爆发前不久有过大幅下跌）
TemporalEdge(src="down", dst="burst", min_gap=1, max_gap=120)

# 突破爆发结束（末根突破）后下一根 bar 就是回踩（gap 恰好为 1）
TemporalEdge(src="burst", dst="tb", min_gap=1, max_gap=1)
```

---

### `ContainmentEdge`

**它是什么 / 什么时候用**：表达"大区间包住小区间"。规范方向永远是 `src ⊇ dst`（src 是那个大的）。

```python
@dataclass(frozen=True)
class ContainmentEdge(DependencyEdge):
    src: str
    dst: str
```

`satisfies` 要求 `src.start_idx <= dst.start_idx` 且 `dst.end_idx <= src.end_idx`（端点重合也算包含）。

> 💡 **小贴士（方向别写反）**：如果你想说"A 被 B 包含"，那 B 才是大的，应写成 `ContainmentEdge(src="B", dst="A")`。永远把大区间放 `src`。

```python
# 横盘段包含某个子区间
ContainmentEdge(src="side", dst="inner")
```

---

### `StartContainmentEdge`

**它是什么 / 什么时候用**：表达"大区间只包住小区间的**起点**"——只要求 `dst` 的起点落在 `src` 区间内，**不管 `dst` 的终点伸到哪里**。规范方向同样是 `src ⊇ dst.start`（src 是那个大的）。

```python
@dataclass(frozen=True)
class StartContainmentEdge(DependencyEdge):
    src: str
    dst: str
```

`satisfies` 要求 `src.start_idx <= dst.start_idx <= src.end_idx`（只看 `dst.start`）。

> 💡 **和 `ContainmentEdge` 的区别**：`ContainmentEdge` 要求 `dst` **整体**被包住（还得 `dst.end <= src.end`）；`StartContainmentEdge` 只盯 `dst` 的起点，`dst` 的尾巴可以伸出 `src` 之外。

**为什么需要它（当前 app 的真实用法 `side → burst`）**：示例 app 要表达"突破爆发是在横盘段里**起步**的"。`burst` 是一个宽事件（起点=串首突破、终点=串尾突破），它的尾巴可能已经突出横盘段了。如果用 `ContainmentEdge` 会额外要求"串尾也落在横盘内"，这比"在横盘里起步"更严、会改变命中结果。`StartContainmentEdge` 只约束 `burst.start` 落在横盘段内，精确保留了想要的语义。

```python
# 横盘段里"起步"的突破爆发（只约束 burst 的起点落在 side 内）
StartContainmentEdge(src="side", dst="burst")
```

---

### `OverlapEdge`

**它是什么 / 什么时候用**：表达"部分交叠"——`dst` 从 `src` 内部某处开始，然后延伸到 `src` 结束之后（也就是 src 的后半截被 dst 盖住了）。

```python
@dataclass(frozen=True)
class OverlapEdge(DependencyEdge):
    src: str
    dst: str
```

精确语义：`src.start < dst.start < src.end` 且 `src.end < dst.end`（三个不等号**全是严格小于**）。所以端点重合**不**满足这条边。

```python
OverlapEdge(src="platform", dst="trend")
```

---

### `EqualsEdge`

**它是什么 / 什么时候用**：表达"同一段"——`src` 与 `dst` 占据**完全相同**的区间（`start_idx` 和 `end_idx` 都相等）。

```python
@dataclass(frozen=True)
class EqualsEdge(DependencyEdge):
    src: str
    dst: str
```

> ⚠️ **引擎内部细节（了解即可）**：为防止漏匹配，引擎会对所有 `EqualsEdge` 的 `src` 节点关闭一项叫 "C1 等-end 塌缩" 的优化。你不用做任何事，知道"用了 EqualsEdge 会让引擎在这些节点上更保守"即可。

---

### `NegationEdge`

**它是什么 / 什么时候用**：表达"**禁止**出现"——以 `src` 为锚，在它之后的某个时间窗口里，**不允许**出现满足条件的 `dst`。比如"突破之后 10 根内不许再砸破支撑"。

```python
@dataclass(frozen=True)
class NegationEdge(DependencyEdge):
    src: str
    dst: str
    min_gap: int = 0
    max_gap: float = math.inf
    inner_predicate: Optional[Callable[[Event], bool]] = None
```

`dst` 在这里是一个**约束**而非故事成员，所以它**不会进入** `role_index` / `children`。

> ⚠️ **最大的坑**：`NegationEdge.satisfies` 的语义是**反的**——返回 `True` 表示"这个 dst 落进了禁区，构成违禁"。引擎用"全称量词"消费它（窗口内**所有** dst 都不违禁，这条边才算通过）。

| 字段 | 默认 | 说明 |
|---|---|---|
| `min_gap` | `0` | 禁止窗口相对 `src.end_idx` 的起始偏移（含） |
| `max_gap` | `math.inf` | 禁止窗口的终止偏移（含） |
| `inner_predicate` | `None` | `None` = 窗口内任何 dst 都算违禁；非 `None` = 只有同时满足该谓词的 dst 才算违禁 |

---

## 4. path2.dag.where — 给单个角色加条件的便利函数

**这一节是什么**：第 2 节说过，节点的 `where` 需要一堆 `WherePredicate` 函数。手写这些函数很啰嗦，所以 path2 提供了一批"工厂函数"，调一下就生成一个现成的条件。**这一节就是这些工厂的菜单。**

```python
from path2.dag import where as W
# 或直接导入需要的
from path2.dag.where import attr, first, last, count, any, distinct, reduce, all
```

每个函数都返回一个 `WherePredicate: (event_or_seq, ctx) -> bool`，可直接塞进 `NodeSpec.where` 或 `KleeneSpec.aggregate_where`。

> 先建立直觉，按"你的角色是单事件还是一串"来挑：
> - **单事件角色** → 用 `attr`（比较单个事件的某属性）。
> - **成串角色（Kleene）** → 用 `first` / `last`（看首尾元素）、`count`（看串长）、`any`（存在一个满足）、`distinct`（去重计数）、`reduce`（自定义聚合）。
> - **想把多条拼起来** → 用 `all`。

> ℹ️ **当前示例 app 走的是哪条路**：`first` / `count` / `any` / `distinct` / `reduce` 这些"对一整串聚合"的谓词服务 **Kleene 路径**，框架仍支持。但 `bottom_breakout_burst` **没有 Kleene 节点**——它那个"密集突破串"的聚合属性（首根突破的回调间距 `first_drought`、打穿的不同峰数 `distinct_pk`、串内最大量比 `max_vol_ratio`）已经在 `BurstEvent` 产出阶段就算成了**普通字段**（见 §8）。所以 `burst` 节点的 `where` 直接用 `attr` 读这些字段即可，根本不用走序列聚合谓词。下面这些聚合谓词的示例**仅用于说明 Kleene 用法**。

> ⚠️ **共性细节**：所有比较函数遇到属性值为 `None` 时都**安全返回 `False`**（不会抛异常）。这对应像 `BOEvent.drought` / `vol_ratio` 这种可能没值的 Optional 字段。

---

### `attr`

**用于**：单个事件（非成串节点）。断言这个事件的某属性满足比较，即 `e.<name> op thr`。

```python
def attr(name: str, op: str, thr) -> WherePredicate
```

| 参数 | 说明 |
|---|---|
| `name` | Event 的属性名，如 `'vol_ratio'`、`'drought'` |
| `op` | 比较运算符字符串，合法值：`'>='`、`'>'`、`'<='`、`'<'`、`'=='`、`'!='` |
| `thr` | 比较阈值，类型需与属性值兼容 |

> ⚠️ `op` 不在合法集合里会抛 `ValueError`。

```python
("vol_ok", attr("vol_ratio", ">=", 2.0))
```

---

### `first`

**用于**：成串节点。断言**串首元素**的某属性满足比较，即 `seq[0].<name> op thr`。常用来约束"这串的开头"。

```python
def first(name: str, op: str, thr) -> WherePredicate
```

```python
# 仅示意 Kleene 用法：串首元素的某属性须 >= 阈值
("first_ok", first("drought", ">=", 60))
```

---

### `last`

**用于**：成串节点。断言**串尾元素**的某属性满足比较，即 `seq[-1].<name> op thr`。

```python
def last(name: str, op: str, thr) -> WherePredicate
```

---

### `count`

**用于**：成串节点。断言这串的**长度**满足比较，即 `len(seq) op thr`。常用来设"至少 N 个"的下界。

```python
def count(op: str, thr) -> WherePredicate
```

```python
# 仅示意 Kleene 用法：这串至少 3 个元素
("min_len", count(">=", 3))
```

---

### `any`

**用于**：成串节点。"存在"量化——断言串里**至少有一个**元素满足 `e.<name> op thr`（∃ e∈seq）。

```python
def any(name: str, op: str, thr) -> WherePredicate
```

```python
# 仅示意 Kleene 用法：串里至少有一个元素 vol_ratio >= 3.0
("any_spike", any("vol_ratio", ">=", 3.0))
```

---

### `distinct`

**用于**：成串节点。**去重计数**——把串里每个元素的 `e.<name>` 收集起来去重，断言去重后的数量满足 `op thr`。

```python
def distinct(name: str, op: str, thr) -> WherePredicate
```

> 💡 **小贴士**：当属性值本身是 `tuple`/`list`/`set` 时（例如 `BOEvent.broken_peak_ids`），会自动 flatten 后再去重。所以它能回答"这串事件一共覆盖了多少个**不同的** key"这种问题。

```python
# 仅示意 Kleene 用法：串里去重后至少 3 个不同 key
("dist_keys", distinct("broken_peak_ids", ">=", 3))
```

---

### `reduce`

**用于**：成串节点。**自定义聚合**——先取出 `[e.<name> for e in seq]`，用你给的 `fn`（如 `max`、`sum`）归约成一个标量，再断言这个标量满足 `op thr`。

```python
def reduce(name: str, fn: Callable, op: str, thr) -> WherePredicate
```

| 参数 | 说明 |
|---|---|
| `name` | Event 的属性名 |
| `fn` | 归约函数，接受列表返回标量，如 `max`、`sum` |
| `op` | 比较运算符字符串 |
| `thr` | 比较阈值 |

```python
from path2.dag.where import reduce
("max_vol", reduce("vol_ratio", max, ">=", 5.0))
```

---

### `all`

**用于**：把多个谓词用 AND 拼成一个。当你想在 `aggregate_where` 的**单个槽位**里塞多条约束时很方便。

```python
def all(*fns: WherePredicate) -> WherePredicate
```

```python
from path2.dag.where import all as W_all, count, distinct

("combined", W_all(count(">=", 3), distinct("broken_peak_ids", ">=", 3)))
```

---

## 5. path2.dag.spec — 把角色和关系打包成完整故事

**这一节是什么**：有了角色（`NodeSpec`）和关系（边），用 `PatternSpec` 把它们装进一个盒子，就成了一个完整的"故事声明"。这一节还讲它怎么投影成面板能渲染的拓扑图（`to_topology`）。

```python
from path2.dag import PatternSpec
```

---

### `PatternSpec`

**它是什么**：一个走势包对外的"剧本"。它是**纯数据**，不含任何匹配逻辑——`nodes + edges` 合起来就是一张类型级 DAG（有向无环图）。

```python
@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    display_name: str
    nodes: Tuple[NodeSpec, ...]
    edges: Tuple[DependencyEdge, ...]
    root: str
    event_styles: Mapping[str, object] = field(default_factory=dict)
    stock_list_columns: Tuple[object, ...] = ()
```

| 字段 | 说明 |
|---|---|
| `pattern_id` | 模式唯一标识符，会进 `PatternMatch.pattern_id` |
| `display_name` | 人类可读名，用于面板标题等 |
| `nodes` | 全部角色声明；**顺序不影响匹配**（引擎内部会按依赖拓扑序自己排） |
| `edges` | 全部边声明，定义角色间关系约束和 DAG 拓扑 |
| `root` | 起点角色，填一个合法的 `node_id` 即可（用于校验） |
| `event_styles` | `node_id → 样式对象`，供面板渲染，默认空 dict |
| `stock_list_columns` | 面板股票列表的列配置，默认空 tuple |

**构造时会自动做五类校验**（任何一项失败都抛 `ValueError`）：
1. **`node_id` 全局唯一**：`node_id` 是拓扑主键，重复会让求解层静默丢节点，所以先查重。
2. **DAG 合法性**：`root` 须在 `nodes` 中；每条边的端点须在 `nodes` 中；整图无环。
3. **Kleene 参数**：`min_count >= 1`；`min_count <= max_count`；`span_from_first` 非负且 `lo <= hi`；`endpoint_for_edges` 须为 `'first'` 或 `'last'`（只对配了 `kleene` 的节点检查）。
4. **detector DAG**：`consumes_stream` 引用的必须是已声明的 `node_id`。
5. **`where` clause_id 唯一**：同一个 node 内 `where` 各条的 `clause_id` 不能重名（跨 node 可重名）。

> 💡 **小贴士**：这些校验是你的好朋友——把剧本写错（比如边连到一个不存在的角色、或不小心连成了环），它会**立刻**在构造时报错，而不是等到匹配出诡异结果。

```python
PatternSpec(
    pattern_id="bottom_breakout_burst",
    display_name="底部反转突破爆发",
    # 五个角色：bo（孤立流源，不进任何边）/ down / side / burst（吃 bo 流）/ tb（吃 bo 流）
    nodes=(bo_node, down_node, side_node, burst_node, tb_node),
    edges=(
        # 三条边全部连到 burst 本体
        TemporalEdge(src="down", dst="burst", min_gap=1, max_gap=120),
        StartContainmentEdge(src="side", dst="burst"),
        TemporalEdge(src="burst", dst="tb", min_gap=1, max_gap=1),
    ),
    root="burst",   # 退化字段，引擎不读，填一个合法 node_id 即可
)
```

> 💡 **`root` 是个退化字段**：当前引擎并不读它（求解器自己按依赖拓扑序排节点），它只参与"必须是已声明 node"的校验。填任意一个合法 `node_id` 即可。

---

### `PatternSpec.to_topology`

**它是什么 / 什么时候用**：把 `nodes`/`edges` **零派生地直投**成面板要用的 `PatternTopology`（一组 `TopoNode` + `TopoEdge`）。面板拿它来画"角色之间的关系图"。"零派生"意味着它不做任何反推，所见即所得。

```python
def to_topology(self) -> PatternTopology
```

> 💡 `TopoEdge.kind` 就是边的子类名（如 `'TemporalEdge'`），面板据此决定箭头画成什么样式。

---

### `PatternTopology`

面板的类型级数据源，由 `to_topology()` 返回。

```python
@dataclass(frozen=True)
class PatternTopology:
    nodes: Tuple[TopoNode, ...]
    edges: Tuple[TopoEdge, ...]
```

---

### `TopoNode`

面板里的一个节点。

```python
@dataclass(frozen=True)
class TopoNode:
    node_id: str
    class_id: str
    label: str = ""
    kleene: bool = False
```

| 字段 | 说明 |
|---|---|
| `node_id` | 节点唯一标识，与 `NodeSpec.node_id` 一致 |
| `class_id` | 事件类型标识，由 `detector.event_cls.class_id` 填，面板据此上色 |
| `label` | 人类可读名称，默认空字符串 |
| `kleene` | 是否为成串（Kleene）节点；由 `NodeSpec.kleene is not None` 推出，默认 `False` |

---

### `TopoEdge`

面板里的一条有向边。

```python
@dataclass(frozen=True)
class TopoEdge:
    src: str
    dst: str
    kind: str
```

| 字段 | 说明 |
|---|---|
| `src` | 源节点 `node_id` |
| `dst` | 目标节点 `node_id` |
| `kind` | 边子类名，如 `'TemporalEdge'`、`'ContainmentEdge'`、`'NegationEdge'` |

---

## 6. path2.dag.engine — 真正去匹配

**这一节是什么**：前面都在"声明"，这一节是"执行"。`analyze()` 是你日常唯一需要调的入口——把剧本和 K 线给它，拿回所有命中。`matches()` 是它的"只问有没有"的便捷版。

```python
from path2.dag import analyze, matches
```

---

### `analyze`

**它是什么**：唯一公开的匹配入口。把 `PatternSpec` 跑在一段 K 线上，返回 `AnalysisResult`。

```python
def analyze(spec: PatternSpec, df, params=None) -> AnalysisResult
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `spec` | `PatternSpec` | 你声明的模式规格，含全部节点、边、匹配策略 |
| `df` | `DataFrame` | 行情 K 线 DataFrame，会传给所有 detector 和 `MatchContext` |
| `params` | `object` | 默认 `None`；运行时参数对象，透传进 `MatchContext.params` |

**内部四阶段流程**（你不用管，了解它有助于排查问题）：
1. 按 `consumes_stream` 的依赖顺序逐个跑各节点 detector：根节点调 `detect(df)`，消费上游流的节点调 `detect(上游流, df)`。（这一步还会先做一次"同类多实例自动消歧"，给同类 detector 编 `source_tag`，见 §8。）
2. `compile_plan` 把 `spec` 编译成约束图 `Plan`。
3. 调 `solve(plan, streams, ctx)` 求解：枚举所有满足 DAG 约束的绑定（回溯 DFS），按 leaf event 跨 prefix 去重（reachable-leaves always-on）。
4. `reify` 把求解结果物化成一个个 `PatternMatch`，并把全部事件流收齐。

**出口处还有一道"孤立角色"过滤**：有些角色在图里没有任何边连它（既不当 `src` 也不当 `dst`），比如示例 app 里的 `bo`——它只当"密度流源层"（给 `burst` / `tb` 当输入、并可独立渲染所有突破点），并不参与形态匹配。这种孤立角色每个候选都会自成一解，产出一堆"只含 `bo` 这一个角色、没凑成完整形态"的残缺命中。引擎在出口处会**从 `spec.edges` 自动推出**哪些节点无边，然后把"`role_index` 里只剩孤立角色"的残缺命中丢掉。判据完全从边推导，不需要你做任何标记。

```python
from path2.dag import analyze
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_apps.bottom_breakout_burst.params import Params

params = Params.default()
spec   = build_pattern(params)
result = analyze(spec, df, params)

print(f"命中次数: {len(result.matches)}")
for m in result.matches:
    print(m.start_idx, m.end_idx, m.role_index.keys())
```

---

### `matches`

**它是什么 / 什么时候用**：只想知道"这段 K 线到底有没有出现这个故事"，不关心细节时用它。返回 `bool`。

```python
def matches(spec: PatternSpec, df, params=None) -> bool
```

当且仅当 `analyze()` 至少命中一次时返回 `True`，等价于 `len(analyze(spec, df, params).matches) > 0`。

---

## 7. path2.dag.result — 匹配结果长什么样

**这一节是什么**：`analyze()` 返回的所有数据结构。读懂这一节，你才知道怎么从结果里把"突破了几次、回踩在哪根 bar"这些信息取出来。

```python
from path2.dag import AnalysisResult, PatternMatch, PredicateTrace, ClauseWitness, EdgeWitness
```

> 先建立直觉，自顶向下：`AnalysisResult` 装着一组 `PatternMatch`（每个是一次命中）；每个 `PatternMatch` 通过 `role_index` 告诉你"每个角色具体绑到了哪些事件"；如果开了诊断，`predicate_trace` 还会告诉你"每条 where、每条边到底过没过"。

---

### `AnalysisResult`

**它是什么**：`analyze()` 的返回值，也是走势包对外的顶层数据契约。

```python
@dataclass(frozen=True)
class AnalysisResult:
    events:  Tuple[Event, ...]
    matches: Tuple[PatternMatch, ...]
    spec:    object = None
```

| 字段 | 说明 |
|---|---|
| `events` | 所有节点流平铺后的**全量**事件（含中间节点产出，不只是最终命中用到的） |
| `matches` | 所有完整命中结果；空 tuple 表示没命中 |
| `spec` | 原始 `PatternSpec` 引用，面板可通过 `spec.to_topology()` 渲染拓扑视图 |

> 💡 **`events` vs `matches` 的区别**：`events` 是"所有探测到的零件"，`matches` 是"真正拼成完整故事的成品"。调试时看 `events` 能知道"是不是某种零件压根没产出来"。

---

### `PatternMatch`

**它是什么**：一次完整的命中。它本身**也是一个 `Event`**（继承自 `Event`，所以有 `event_id`/`start_idx`/`end_idx`），这意味着它可以反过来作为更上层故事的一个角色，支持嵌套。

```python
@dataclass(frozen=True)
class PatternMatch(Event):
    pattern_id:      str                                    = ""
    role_index:      Optional[Mapping[str, RoleBinding]]   = None
    children:        Tuple[Event, ...]                      = ()
    predicate_trace: Optional[PredicateTrace]               = None
```

| 字段 | 说明 |
|---|---|
| `pattern_id` | 来自 `PatternSpec.pattern_id`，标识本次命中属于哪个模式 |
| `role_index` | `node_id → 绑定实例`：普通（ONCE）节点值是单个 `Event`；Kleene 节点值是 `Tuple[Event, ...]`。（示例 app 没有 Kleene 节点，所有值都是单个 `Event`。也注意：被出口过滤掉的孤立角色——如 `bo`——压根不会出现在任何命中的 `role_index` 里。） |
| `children` | `role_index` 所有值展平后按 `start_idx` 升序排列，是 `role_index` 的冗余镜像，方便遍历 |
| `predicate_trace` | 富诊断信息（每条 where 子句和每条边的求值结果）；`None` 表示引擎没开 trace |

> 💡 **`role_index` 是你最常用的字段**：想取某个角色绑到的事件，就 `m.role_index["角色名"]`。普通角色拿到一个事件，成串角色拿到一个事件元组。

> ⚠️ **小贴士**：`children` 和 `role_index` 指向**同一批对象**（`id` 一致），`children` 只是展平视图，别把它当成另一份数据重复遍历。

```python
for m in result.matches:
    burst = m.role_index["burst"]    # ONCE 节点 → 单个 BurstEvent（嵌套事件）
    tb    = m.role_index["tb"]       # ONCE 节点 → ThrowbackEvent
    # 突破数从 burst 内部的 members 取（burst 是嵌套事件，装着那一串 BOEvent）
    print(f"突破数: {len(burst.members)}, 回踩确认 bar: {tb.end_idx}")
```

> 💡 **想拿"这一串突破"里的细节，就钻进 `burst` 这个嵌套事件**：`burst.members` 是组成它的那一串 `BOEvent`（完整对象），`burst.child('first_bo')` / `burst.child('last_bo')` 取首尾那根。注意 `bo` 角色本身不进 `match`（它是孤立流源、被出口过滤），所以**别**再去取 `m.role_index["bo"]`。

---

### `RoleBinding`（类型别名）

`role_index` 里每个槽位绑定值的类型：普通节点是单个 `Event`，Kleene 节点是 `Event` 元组。

```python
RoleBinding = Union[Event, Tuple[Event, ...]]
```

---

### `ClauseWitness`

**它是什么**：每条 `where` 子句在一次命中里留下的"判定 + 实测对照"——不只是"过没过"，还告诉你"实测值多少、和谁比、阈值多少"。

```python
@dataclass(frozen=True)
class ClauseWitness:
    satisfied: bool
    measured:  object = None
    op:        object = None
    threshold: object = None
    aggregate: bool   = False
```

| 字段 | 说明 |
|---|---|
| `satisfied` | 这条子句过没过 |
| `measured` | 实测值（由 `W.*` 谓词产出）；组合子或无可测量值时为 `None` |
| `op` | 比较算子（如 `">="`、`"=="`）；组合子时为 `None` |
| `threshold` | 阈值；组合子时为 `None` |
| `aggregate` | `True` 表示这条来自 Kleene 的整串聚合谓词 |

> 💡 **它能当布尔值直接用**：`ClauseWitness` 定义了 `__bool__`（等于 `satisfied`），所以旧写法 `if where_results[nid][cid]:` 照样能用——你既能拿它当"过没过"的真值，也能进一步读 `measured` / `threshold` 看细节。

---

### `PredicateTrace`

**它是什么 / 什么时候用**：一份"命中体检报告"。当你想知道"这次命中里，每条条件、每条边具体过没过、实测值是多少"时看它。调试和面板展示都靠它。

```python
@dataclass(frozen=True)
class PredicateTrace:
    where_results: Mapping[str, Mapping[str, ClauseWitness]]
    edge_results:  Mapping[Tuple[str, str], EdgeWitness]
```

| 字段 | 说明 |
|---|---|
| `where_results` | `node_id → {clause_id: ClauseWitness}`，每个节点各条 `where` 子句的逐条求值证据（`ClauseWitness` 可当真值用，见上） |
| `edge_results` | `(src_node_id, dst_node_id) → EdgeWitness`，每条边两端实例及实测值（`NegationEdge` 不收录） |

```python
trace = m.predicate_trace
w = trace.where_results["burst"]["first_drought"]
print(bool(w), w.measured, w.op, w.threshold)   # 过没过 + 实测值 + 算子 + 阈值
ew = trace.edge_results[("down", "burst")]
print(ew.measured)                               # 实测 gap bar 数
```

---

### `EdgeWitness`

**它是什么**：单条边的"实证记录"——它在本次命中里留下的两端实例和实测值。

```python
@dataclass(frozen=True)
class EdgeWitness:
    satisfied:    bool
    src_instance: Event
    dst_instance: Event
    measured:     float
```

| 字段 | 说明 |
|---|---|
| `satisfied` | 本条边在本次命中中是否满足（正向边恒 `True`） |
| `src_instance` | `src` 节点绑定实例（Kleene 节点取 `endpoint_for_edges` 指定的端点） |
| `dst_instance` | `dst` 节点绑定实例 |
| `measured` | 对**所有正向边统一**为 `dst.start_idx - src.end_idx`（gap 语义，bar 数）。`TemporalEdge` 为正间隔；`ContainmentEdge` / `StartContainmentEdge` / `OverlapEdge` / `EqualsEdge` 因 dst 起点落在 src 内部，此值通常 ≤0（`StartContainmentEdge` 只约束 `dst.start` ∈ `[src.start, src.end]`，同样 ≤0） |

---

## 8. path2.atoms — 开箱即用的 Detector 库

**这一节是什么**：path2 自带的一批"走势无关"的探测器和对应事件类。"走势无关"意思是它们不绑定任何具体业务故事——突破就是突破、趋势段就是趋势段，谁都能拿来当积木搭自己的剧本。这一节是它们的速查表。

```python
from path2.atoms.breakout    import BODetector, BOEvent, BurstDetector, BurstEvent
from path2.atoms.trend       import TrendSegmentDetector, TrendSegment
from path2.atoms.throwback   import ThrowbackDetector, ThrowbackEvent, evaluate_throwback, ThrowbackStrength, ThrowbackResult
from path2.atoms.platform    import PlatformDetector, Platform
from path2.atoms.distribution import DistributionDetector, Distribution
```

**两条贯穿全库的设计约定**：
- 所有 Detector 内部状态**不跨 `detect()` 调用**（每次 detect 入口都重置），所以同一个 detector 实例可以反复用在不同 df 上。
- 所有 Event 子类都是 `frozen=True`，容器字段一律用 `tuple` 而非 `list`（防被下游就地篡改）。

> 配对关系：每个 `XxxDetector` 产出对应的 `XxxEvent`（或 `Xxx`）。下面按"事件类 + 探测器"成对列出。

---

### `BOEvent`

**它是什么**：一次"突破"事件，发生在单根 bar 上（`start_idx == end_idx == BO bar` 的索引）。

```python
@dataclass(frozen=True)
class BOEvent(Event)
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `drought` | `Optional[int]` | 距上一次 BO 的 bar 间距；若本次是第一个 BO（无前序）则为 `None` |
| `pk_count` | `int` | 本次 BO 同时穿越的 peak 数量，默认 `0` |
| `broken_peak_ids` | `Tuple[int, ...]` | 被穿越的各 peak 的内部 `pk_id` 集合，默认空 tuple；`__post_init__` 会把传入的 list 自动转成 tuple |
| `vol_ratio` | `Optional[float]` | BO bar 当日成交量相对长期均量的倍数；均量尚未累积够 bar 时为 `None` |
| `peak_vol_max` | `float` | 被穿越的所有 peak 在其形成时刻的 `vol_ratio` 最大值，默认 `0.0` |

> ⚠️ **常见误解**：`drought=None` 表示"这是第一个 BO"，**不是**"回调天数未知"。

---

### `BODetector`

**它是什么**：基于滑窗 peak 识别的单点突破探测器。每根 bar 先在向左 `total_window` 根的窗口里尝试确认新 peak，再判断当前 bar 是否突破了已有 peak，命中就产出一个 `BOEvent`。

```python
class BODetector(BarwiseDetector)
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `total_window` | `int` | `10` | 向左回看 peak 的 bar 数（不含当前 bar） |
| `min_side_bars` | `int` | `2` | peak 两侧至少各需多少 bar 衬托，防边缘杂波；约束：`min_side_bars * 2 <= total_window` |
| `min_relative_height` | `float` | `0.05` | peak 相对窗口最低价的最低涨幅阈值 |
| `exceed_threshold` | `float` | `0.005` | BO 判定：当前 bar 度量价 > `peak_price * (1 + exceed_threshold)` 才算突破 |
| `peak_supersede_threshold` | `float` | `0.03` | 超额幅度超过此阈值则把该 peak 从 `active_peaks` 移除 |
| `vol_baseline_period` | `int` | `63` | 计算 `vol_ratio` 用的长期均量滚动窗口（个交易日） |
| `peak_measure` | `str` | `"body_top"` | 识别 peak 高点时的度量方式：`"high"` / `"close"` / `"body_top"` |
| `breakout_mode` | `str` | `"body_top"` | 判断当前 bar 是否突破时的度量方式，可选同上 |

> ⚠️ `min_side_bars * 2 > total_window` 会在构造时抛 `ValueError`；`peak_measure` / `breakout_mode` 传非法值同样抛 `ValueError`。

---

### `BurstEvent`

**它是什么（先讲人话）**：一串挤在一起的突破，被打包成**一个**宽事件。以前"一串突破"在框架里没有一个实体代表它——你只能在匹配期把一堆散点突破临时绑成序列。现在 `BurstEvent` 就是"这一串"本身：它有自己的起止（起点=串首突破的起点、终点=串尾突破的终点），肚子里装着组成它的那一根根突破。这样"这一串"终于能像普通事件一样被引用、被画在图上、被一个 `where` 条件整体检查。这就是**嵌套事件**最典型的样子。

```python
@dataclass(frozen=True)
class BurstEvent(Event):
    class_id = "burst"
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | `int` | 这串里有几根突破，默认 `0` |
| `distinct_pk` | `int` | 整串一共打穿了多少个**不同的**峰（去重计数），默认 `0` |
| `max_vol_ratio` | `float` | 串内各突破 `vol_ratio` 的最大值，默认 `0.0` |
| `first_drought` | `int` | 串首那根突破的"回调间距"（`drought`），默认 `0` |
| `members` | `Tuple[BOEvent, ...]` | 组成这串的那一根根突破**完整对象**（存实体，不是 id），默认空 tuple |

> 💡 **为什么要预先算好那四个标量字段**：`count` / `distinct_pk` / `max_vol_ratio` / `first_drought` 是在 `BurstEvent` 产出阶段就算好存成普通字段的。好处是——你想给 `burst` 加条件时，直接 `W.attr("first_drought", ">=", 40)` 读字段即可，不用每次都去遍历 `members` 重新聚合。

**它的嵌套协议**（覆盖了 §1 Event 的那组方法）：
- `child_slots()` → `{"members": (...)}`（这串突破就是它的主 child 集）；
- `children("members")` → 整串突破；
- `child("first_bo")` / `child("last_bo")` → 串首 / 串尾那根突破（给边的 `Child` 端点 selector 用）。

---

### `BurstDetector`

**它是什么（先讲人话）**：一台"切串机"——它消费突破流，把挤在一起的突破切成一段段，每段打包成一个 `BurstEvent`。

```python
class BurstDetector
```

它遵守 path2 的**独立性原则**：自己**不** new 一个 `BODetector`，而是声明 `consumes_stream="bo"` 去吃上游 `bo` 节点产出的突破流（见 §2 流源 / 消费者）。它只干两件事——**切串** + **算好那四个预算标量**；真正的阈值过滤（"回调间距够不够大""打穿的峰够不够多""量比够不够高"）交给 `burst` 节点的 `where` 去做。

**切串口径**（和旧 Kleene 求解器的内部切串逻辑完全一致）：把突破按 `(start_idx, end_idx)` 排好序后单向扫——每个还没被消费的突破当段首，往后吸纳"起点与段首起点之差 `<= max_span`"的后续突破，贪心取最长一段、不回头；一段长度 `>= min_bos` 才产出一个 `BurstEvent`。

```python
def __init__(self, max_span: int, min_bos: int)
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `max_span` | `int` | "成簇"窗口：后续突破的起点与段首起点之差超过它，就不再纳入同一串（保证这串是真挤在一起的） |
| `min_bos` | `int` | 一串至少要有几根突破才产出 |

> 💡 **构造参数只有"怎么切串"，没有"阈值"**：`max_span` / `min_bos` 是切串参数，走构造函数。那三个阈值（回调间距 / 峰数 / 量比）**不传给 detector**，而是写在 `burst` 节点的 `where` 里。在示例 app 里，`min_bos` 取的是顶层的 `MIN_BOS`（见 `params.burst_kwargs()`），和匹配口径保持一致。

---

### `TrendSegment`

**它是什么**：一段"连续保持同一趋势方向"的区间事件，`start_idx`/`end_idx` 是区段左右边界（含两端）。

```python
@dataclass(frozen=True)
class TrendSegment(Event)
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `regime` | `Literal["down", "sideways", "up"]` | 本区段的趋势方向，默认 `"sideways"` |
| `drawdown` | `float` | 区段内从最高点到最低点的振幅 `(seg_high - seg_low) / seg_high`，默认 `0.0` |

---

### `TrendSegmentDetector`

**它是什么**：逐 bar 看 SMA 的每根相对变化，经 hysteresis（迟滞）平滑后，把 K 线切成一段段连续的 `TrendSegment`。df 必须有 `close` 列。

```python
class TrendSegmentDetector
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `ma_period` | `int` | `20` | 计算 SMA 的回看周期；df 长度需 >= `ma_period + 1`，否则不产出任何事件 |
| `sideways_eps` | `float` | `0.0005` | SMA 相对变化绝对值低于此阈值时判为 sideways |
| `hysteresis_bars` | `int` | `3` | 切换 regime 需候选方向连续出现 `hysteresis_bars` 根 bar 才确认（迟滞，防抖） |
| `source_tag` | `str \| None` | `None` | 这个实例产出的事件 `event_id` 前缀（per-instance）。默认 `None` 时回退用 `class_id`（即 `"trend"`）。同类多实例时由引擎自动填，**一般不用手动传**（见下） |

> ⚠️ **小贴士**：末段（一直到 df 末尾）即使不完整也会被 yield 出来，调用方需自行判断要不要截断。

> 💡 **hysteresis 是什么**："迟滞"的意思是"别一看到方向变了就立刻翻脸"。要新方向连续坚持 `hysteresis_bars` 根才认账，避免趋势在临界点反复横跳。

**`source_tag` / 同类多实例自动消歧（先讲人话）**

问题来了：示例 app 里 `down` 和 `side` 各持一个**独立的** `TrendSegmentDetector` 实例，两边产出的事件 `class_id` 都是 `"trend"`，`event_id` 前缀也都想用 `"trend"`——这就会撞车。

`source_tag` 就是解药：它是 detector 实例上的 `event_id` 前缀钩子。`TrendSegment` 生成 `event_id` 时用的是 `source_tag or class_id` 作前缀，所以只要两个实例 `source_tag` 不同，id 就不会撞。

你通常**不用手动填**它——引擎在跑流之前会自动做这件事（`assign_auto_source_tags`）：

- 它发现"同一个 `class_id` 下有 ≥ 2 个**不同的** detector 对象"时，按节点首次出现的顺序，给那些没显式设过 `source_tag` 的实例自动编号 `trend0` / `trend1` ……
- **单实例、共享同一个对象、或你已经手动命名过**的情况，它一律不动——所以单实例 app 的 `event_id` 逐字不变、向后兼容；这步还是幂等的。
- 如果某个 detector 出现了多实例、却又没有 `source_tag` 这个钩子，引擎会**直接报错**（而不是静默撞 id），提醒你给它加上消歧支持。

---

### `ThrowbackStrength`

**它是什么**：回踩"强度"的元数据。它本身不影响"算不算回踩"，只是给确认了的回踩附上一份"成色描述"，由 `evaluate_throwback` 填充，挂在 `ThrowbackResult`/`ThrowbackEvent` 上。

```python
@dataclass(frozen=True)
class ThrowbackStrength
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `strongest` | `str` | 强度最高的单一信号名；优先级 `lower_shadow > gap_up > bullish > doji > close_up`；无信号时为 `'unknown'` |
| `prev_signals` | `Tuple[str, ...]` | 触发确认的"前一根" bar 命中的积极信号列表 |
| `cur_signals` | `Tuple[str, ...]` | 触发确认的"当前根" bar 命中的积极信号列表 |
| `max_stack` | `int` | prev/cur 两根 bar 中信号数量的最大值：`max(len(prev_signals), len(cur_signals))` |
| `axes_covered` | `int` | prev + cur 合集信号覆盖的独立分析轴数（1-4）：`intra_geom`/`intra_dir`/`inter_open`/`inter_close` |
| `tier` | `str` | 三档强度：`'strong'`（含强信号 **AND** `axes_covered >= 2`）/ `'medium'`（含强信号 **OR** `axes_covered >= 2`）/ `'weak'`（其余）；强信号集 = `{lower_shadow, gap_up}` |

---

### `ThrowbackResult`

**它是什么**：`evaluate_throwback` 的返回值。它是 `NamedTuple`，所以既能按字段名访问，也能像普通 tuple 那样解构。

```python
class ThrowbackResult(NamedTuple):
    confirmed:    bool
    trigger_idx:  Optional[int]
    strength:     Optional[ThrowbackStrength]
    status:       str
```

| 字段 | 说明 |
|---|---|
| `confirmed` | 是否确认回踩支撑 |
| `trigger_idx` | 触发确认（或破位）的 bar 索引；`timeout`/`no_strict_bo` 时为 `None` |
| `strength` | 仅 `confirmed=True` 时非 `None`，包含信号强度元数据 |
| `status` | 详细状态：`'confirmed'` / `'broken'` / `'timeout'` / `'no_strict_bo'` |

---

### `evaluate_throwback`

**它是什么 / 什么时候用**：判断"某一次突破之后有没有回踩确认"的核心函数。它对**单个** `BOEvent` 向前扫最多 `N` 根 bar 来下结论。这是个零状态的纯函数，可以脱离引擎单独调来做实验。

```python
def evaluate_throwback(
    bo: BOEvent,
    df: pd.DataFrame,
    *,
    N: int = 10,
    vol_ratio_min: float = 2.0,
    vol_window: int = 20,
    strict_mode: bool = False,
) -> ThrowbackResult
```

判据：锚点 = `high[bo_idx - 1]`；**必要条件** = 窗口内每根 bar 的 `low >= anchor`（不破位）；**充分条件** = 相邻 2 根 bar 各持有 >= 1 个积极信号。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `bo` | `BOEvent` | — | 待评估的突破事件 |
| `df` | `pd.DataFrame` | — | 原始 OHLCV DataFrame |
| `N` | `int` | `10` | 向前扫描的最大 bar 数（lookforward 窗口） |
| `vol_ratio_min` | `float` | `2.0` | 进入回踩检测的前置门槛：BO bar 的 `vol_ratio` 须 >= 此值 |
| `vol_window` | `int` | `20` | 判断 BO bar 是否为"严格放量阳线 BO"时，近 N 根原始成交量最大值的回看窗口 |
| `strict_mode` | `bool` | `False` | `True` 时要求 prev+cur 信号合集还须含 >= 1 个几何信号（doji 或 lower_shadow） |

> ⚠️ **小贴士**：前置条件（`_strict_bullish_burst_bo`）不满足时直接返回 `status='no_strict_bo'`，根本不进前向扫描。`broken` 时 `trigger_idx` 指向破位那根（非 `None`），可用于调试。

---

### `ThrowbackEvent`

**它是什么**：把"回踩确认"这件事**事件化**后的派生事件。只有 `confirmed`（确认成功）时才会被 `ThrowbackDetector` 产出。

```python
@dataclass(frozen=True)
class ThrowbackEvent(Event)
```

它的区间约定：`start_idx = bo.end_idx + 1`（回踩窗起点），`end_idx = trigger_idx`（实际确认那根）。

> 💡 **它的 `class_id` 是 `"tb"`**：和其它事件一样，`ThrowbackEvent` 靠类级常量 `class_id`（这里是 `"tb"`）标识自己——面板上色、`event_id` 前缀都基于它。

| 字段 | 类型 | 说明 |
|---|---|---|
| `anchor_bo_id` | `str` | 触发本回踩的 `BOEvent` 的 `event_id`，默认空字符串；用于面板画 bo→tb 有向边 |
| `trigger_idx` | `int` | 实际确认的 bar 索引（等于 `end_idx`），默认 `-1` |
| `strength` | `Optional[ThrowbackStrength]` | 回踩强度元数据，confirmed 时非 `None`，默认 `None` |
| `confirmed` | `bool` | 恒为 `True`（detector 只 emit confirmed 事件），默认 `True` |

---

### `ThrowbackDetector`

**它是什么**：一个"派生探测器"——它不直接吃 K 线产事件，而是**消费 bo 流**：对每个 BO 独立调一次 `evaluate_throwback`，只有 confirmed 的才产出 `ThrowbackEvent`。

```python
class ThrowbackDetector
```

它的 `detect` 是**双参数** `(bo_stream, df)`，与 path2 `run()` 的变参透传机制兼容。用它时要在 `NodeSpec` 里设置 `consumes_stream="bo"`，引擎才知道要把 bo 流喂进来。

> 这些参数仅限关键字传参（构造签名带 `*`）。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `N` | `int` | `10` | 前向扫描窗口，透传给 `evaluate_throwback` |
| `vol_ratio_min` | `float` | `2.0` | 前置放量门槛，透传给 `evaluate_throwback` |
| `vol_window` | `int` | `20` | 近期成交量最大值回看窗口，透传给 `evaluate_throwback` |
| `strict_mode` | `bool` | `False` | 几何信号严格模式，透传给 `evaluate_throwback` |

> ⚠️ **小贴士**：`detect()` 内部是先把全部 confirmed 事件收齐、按 `(end_idx, start_idx)` 排序后再一起 yield，**不是**实时流式 yield（因为 `trigger_idx` 随 bo 顺序可能乱序，必须排序才能满足 `run()` 的 end 升序不变式）。broken/timeout/no_strict_bo 的 BO 都被静默忽略。

```python
# 在 NodeSpec 中使用 ThrowbackDetector（消费 bo 流）
from path2.atoms.throwback import ThrowbackDetector
from path2.dag import NodeSpec

NodeSpec(
    node_id="tb",
    detector=ThrowbackDetector(N=10, vol_ratio_min=2.0),
    consumes_stream="bo",   # 消费 bo 节点产出的事件流（吃 BOEvent）
    label="回踩确认",
)
```

---

### `Platform`

**它是什么**：一段"窄幅震荡"（平台）区段事件，`start_idx`/`end_idx` 是平台起止 bar。

```python
@dataclass(frozen=True)
class Platform(Event)
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `atr_pct_mean` | `float` | 区段内 ATR/close 的均值（百分比形式），衡量平台内日内波动率，默认 `0.0` |
| `range_pct` | `float` | 区段最终宽度 `(max(high) - min(low)) / min(low)`，必然 <= `range_thr`，默认 `0.0` |

---

### `PlatformDetector`

**它是什么**：用"非重叠贪心扫窗"识别平台段——以 `window` 根为起始窗口，只要 `range_pct <= range_thr` 就不断往右扩；一旦再加一根会超阈值就停下、产出一个 `Platform`，指针直接跳到 `end+1`（保证段与段不重叠）。

```python
class PlatformDetector
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `window` | `int` | `10` | 平台识别的最小 bar 数（初始窗口大小） |
| `range_thr` | `float` | `0.05` | 平台宽度上限：`(max_high - min_low) / min_low <= range_thr` |
| `atr_period` | `int` | `14` | 计算 ATR 的回看周期，用于填 `Platform.atr_pct_mean` |

> ⚠️ df 行数 < `window` 时不产出任何事件。

---

### `Distribution`

**它是什么**：一根"高位派发" bar 事件（`start_idx == end_idx`），判据是"放量阴线 + 长上影"。

```python
@dataclass(frozen=True)
class Distribution(Event)
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `vol_ratio` | `float` | 本 bar 成交量相对长期均量的倍数，默认 `0.0` |
| `upper_shadow_ratio` | `float` | 上影线比例，默认 `0.0` |

---

### `DistributionDetector`

**它是什么**：逐 bar 检测派发 bar——当 `vol_ratio >= vol_threshold` **且** `close < open` **且** `upper_shadow_ratio >= upper_shadow_threshold` 三条全满足时产出 `Distribution`。

```python
class DistributionDetector(BarwiseDetector)
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `vol_threshold` | `float` | `3.0` | 放量倍数下限：`vol_ratio` 须 >= 此值 |
| `upper_shadow_threshold` | `float` | `0.5` | 上影线比例下限：`upper_shadow_ratio` 须 >= 此值 |
| `vol_baseline_period` | `int` | `63` | 计算 `vol_ratio` 用的长期均量滚动窗口（个交易日） |

---

## 9. path2.calc — 纯数值计算函数库

**这一节是什么**：一堆**纯数值函数**——它们和 `Event`/`Detector` 完全无关，输入 Series/标量、输出 Series/标量，可以单独拿来用。Detector 内部就靠它们算指标。当你写自己的 detector 或在 `where` 里做计算时会用到。

```python
from path2.calc.atr      import calculate_atr
from path2.calc.geometry import upper_shadow_ratio, lower_shadow_ratio, body_pct
from path2.calc.ma       import calculate_ma, calculate_ma_pos, calculate_ma_z_atr, calculate_ma_curve, calculate_ma_slope
from path2.calc.recovery import calculate_dd_recov
from path2.calc.rolling  import rolling_range_pct, rolling_std_pct
from path2.calc.stability import calculate_stability
from path2.calc.volume   import calculate_vol_ratio
```

> 💡 **共性提醒**：这些函数大多在前若干个 bar 输出 `NaN`（窗口还没攒够数据），并对停牌/坏数据（如除数为 0）做了 `NaN` 规整。用它们的结果时记得处理 `NaN`。

---

### `calculate_atr`

Wilder RMA 平滑的 ATR（平均真实波幅）。

```python
calculate_atr(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14
) -> pd.Series
```

TR = `max(H-L, |H-prev_C|, |L-prev_C|)`；第 `period` 个 bar 用算术均值初始化，之后递推。前 `period-1` 个 bar 输出 `NaN`。

| 参数 | 说明 |
|---|---|
| `highs` | 每日最高价序列 |
| `lows` | 每日最低价序列 |
| `closes` | 每日收盘价序列 |
| `period` | Wilder 平滑周期，默认 `14` |

> ⚠️ 输入序列长度小于 `period` 时返回全 `NaN` Series。

---

### `upper_shadow_ratio`

单根 K 线上影线占全振幅的比例：`(h - max(o, c)) / (h - l)`。`rng <= 0` 时返回 `0.0`。

```python
upper_shadow_ratio(o: float, h: float, l: float, c: float) -> float
```

---

### `lower_shadow_ratio`

单根 K 线下影线占全振幅的比例：`(min(o, c) - l) / (h - l)`。`rng <= 0` 时返回 `0.0`。

```python
lower_shadow_ratio(o: float, h: float, l: float, c: float) -> float
```

---

### `body_pct`

单根 K 线实体占全振幅的比例：`|c - o| / (h - l)`。`rng <= 0` 时返回 `0.0`。

```python
body_pct(o: float, h: float, l: float, c: float) -> float
```

---

### `calculate_ma`

简单移动平均（rolling mean）。前 `period-1` 个 bar 输出 `NaN`。

```python
calculate_ma(closes: pd.Series, period: int) -> pd.Series
```

---

### `calculate_ma_pos`

收盘价相对 MA 的相对位置：`(close - MA) / MA`。前 `period-1` 个 bar 为 `NaN`。

```python
calculate_ma_pos(closes: pd.Series, period: int) -> pd.Series
```

---

### `calculate_ma_z_atr`

ATR 归一化的 MA 偏离 z 值：`(close - MA) / atr.shift(1)`。用前一日 ATR 是为了避免 self-leakage（当前 bar 自己影响自己的归一化基准）。

```python
calculate_ma_z_atr(closes: pd.Series, atr: pd.Series, period: int) -> pd.Series
```

| 参数 | 说明 |
|---|---|
| `closes` | 收盘价序列 |
| `atr` | ATR 序列（通常由 `calculate_atr` 产出） |
| `period` | 均线周期 |

---

### `calculate_ma_curve`

MA 曲率（二阶差分归一化）：`(MA[t] - 2*MA[t-stride] + MA[t-2*stride]) / MA[t] * period^2`。

```python
calculate_ma_curve(closes: pd.Series, period: int, stride: int = 5) -> pd.Series
```

| 参数 | 说明 |
|---|---|
| `stride` | 二阶差分步长（bar 数），默认 `5` |

---

### `calculate_ma_slope`

每 bar 归一化斜率：`(MA[t] - MA[t-lookback]) / MA[t-lookback] / lookback`。输入是**已经算好的** MA Series。

```python
calculate_ma_slope(ma_series: pd.Series, lookback: int = 20) -> pd.Series
```

---

### `calculate_dd_recov`

回撤恢复度信号。在 `lookback` 窗口内找峰值，峰值后找谷值，计算 `drawdown × recovery × (1-recovery)^(decay_power-1)`，在 `recovery=best_recovery` 处取得极值。前 `lookback-1` 个 bar 为 `NaN`。

```python
calculate_dd_recov(
    closes: pd.Series,
    lookback: int = 252,
    best_recovery: float = 0.25
) -> pd.Series
```

| 参数 | 说明 |
|---|---|
| `lookback` | 回看窗口（bar 数），决定峰值搜索范围，默认 `252` |
| `best_recovery` | 信号峰值对应的恢复比例；`decay_power = 1 / best_recovery`，默认 `0.25` |

> ⚠️ peak 落在窗口最后一根（即当前 bar 就是峰值）时返回 `0.0`，因为无法定义 post-peak 谷值。

---

### `rolling_range_pct`

滚动窗口振幅占比：`(rolling_max(highs) - rolling_min(lows)) / rolling_min(lows)`。rolling min 为 0 时（停牌/坏数据）规整为 `NaN`。

```python
rolling_range_pct(highs: pd.Series, lows: pd.Series, period: int) -> pd.Series
```

---

### `rolling_std_pct`

收盘价滚动标准差占比：`rolling_std(closes, period) / closes`。衡量相对波动率。

```python
rolling_std_pct(closes: pd.Series, period: int) -> pd.Series
```

---

### `calculate_stability`

突破点后的价格稳定性：从 `peak_idx` 起 `lookforward` 根 bar（含 peak bar 自身）中，`low >= peak_price` 的比例（0~1）。越界时只统计可用 bar；可用 bar 为 0 时保守返回 `1.0`。

```python
calculate_stability(
    lows: pd.Series,
    peak_idx: int,
    peak_price: float,
    lookforward: int = 10
) -> float
```

| 参数 | 说明 |
|---|---|
| `lows` | 每日最低价序列 |
| `peak_idx` | 突破点的整数位置索引（iloc） |
| `peak_price` | 突破价（通常为突破点的收盘价或高点价） |
| `lookforward` | 向后观察的 bar 数（含 peak bar），默认 `10` |

---

### `calculate_vol_ratio`

量比：`volume / rolling_mean(volume, baseline_period).shift(1)`。用 `shift(1)` 是为了不让当前 bar 参与基线均量（避免 self-leakage）。零成交量基线（停牌段）规整为 `NaN`。前 `baseline_period` 个 bar 为 `NaN`。

```python
calculate_vol_ratio(volumes: pd.Series, baseline_period: int = 63) -> pd.Series
```

| 参数 | 说明 |
|---|---|
| `volumes` | 每日成交量序列 |
| `baseline_period` | 基线均量的滚动窗口大小，约 1 季度交易日，默认 `63` |

---

## 完整示例

读到这里，前面的概念该串成一条线了。下面是 `bottom_breakout_burst` 走势包的核心声明结构——它用 **五个 `NodeSpec`（五个角色）+ 三条类型化边** 表达一个"底部反转后密集突破爆发"的故事。先把五个角色的分工讲清楚：

- `bo`（突破点）：一个**孤立流源**——它在图里没有任何边连接，不参与形态匹配，只当"密度流源层"：一来给 `burst` / `tb` 当输入流，二来可以独立把所有突破点画到 K 线上。因为没边，它那种"只含 `bo` 一个角色"的残缺命中会被引擎出口过滤掉，所以 `bo` 不会出现在任何完整命中里（见 §6）。
- `down`（下跌段） / `side`（横盘段）：**各持一个独立的** `TrendSegmentDetector` 实例（不是同一个对象），靠不同的 `where` 扮演两个角色。各持独立实例是为了激活引擎的自动消歧，给两边事件打上 `trend0` / `trend1` 前缀（见 §8 `source_tag`）。
- `burst`（突破爆发）：一个**嵌套事件**角色。`BurstDetector` 消费 `bo` 流（`consumes_stream="bo"`），把密集突破切成串、每串聚合成一个 `BurstEvent`。它的三条 `where` 直接用 `W.attr` 读 `BurstEvent` 预先算好的预算字段（`first_drought` / `distinct_pk` / `max_vol_ratio`）。
- `tb`（回踩确认）：一个消费 `bo` 流的派生角色（`consumes_stream="bo"`，吃的是 `BOEvent`、不是 `BurstEvent`）。

三条边**全部连到 `burst` 本体**：下跌 → 突破爆发（时序，要求爆发前 `lookback` 内有大幅下跌）、横盘 ⊇ 突破爆发的起点（起点包含，要求爆发在横盘里起步）、突破爆发 → 回踩（紧邻时序，因为 `burst.end` 就是串尾突破，末突破之后紧接着回踩）。

```python
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, StartContainmentEdge
from path2.dag.spec  import PatternSpec
from path2.dag import where as W
from path2.atoms.breakout  import BODetector, BurstDetector
from path2.atoms.trend     import TrendSegmentDetector
from path2.atoms.throwback import ThrowbackDetector

def build_pattern(params):
    down_det = TrendSegmentDetector(**params.trend_kwargs())
    side_det = TrendSegmentDetector(**params.trend_kwargs())   # 与 down 各持独立实例
    nodes = (
        # bo：孤立流源（无边），既给 burst/tb 当输入流，又可独立渲染所有突破点
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs())),
        # 下跌段：regime==down 且 drawdown 够大
        NodeSpec("down",
                 down_det,
                 where=(("regime",   W.attr("regime", "==", "down")),
                        ("drawdown", W.attr("drawdown", ">=", params.pred4_min_drawdown))),
                 label="下跌段"),
        # 横盘段：regime==sideways
        NodeSpec("side",
                 side_det,
                 where=(("regime", W.attr("regime", "==", "sideways")),),
                 label="横盘段"),
        # 突破爆发：BurstDetector 切 bo 串聚合成 BurstEvent；where 直读预算字段
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),
                        ("vol_spike",     W.attr("max_vol_ratio", ">=", params.THR_VOL))),
                 consumes_stream="bo", label="突破爆发"),
        # 回踩确认：消费 bo 流（吃 BOEvent）
        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo", label="回踩确认"),
    )
    edges = (
        TemporalEdge("down", "burst", min_gap=1, max_gap=params.pred4_lookback_bars),
        StartContainmentEdge("side", "burst"),
        TemporalEdge("burst", "tb", min_gap=1, max_gap=1),
    )
    return PatternSpec(
        pattern_id="bottom_breakout_burst",
        display_name="底部反转突破爆发",
        nodes=nodes, edges=edges,
        root="burst",   # 退化字段，引擎不读，填合法 node_id 即可
    )
```

> 💡 **新模型里最反直觉的一点**：为什么 `bo` 明明产出了所有突破点，却不在任何 `match` 里？因为它是**孤立角色**——它不连任何边，只当"密度流源层"。形态匹配真正关心的是被 `BurstDetector` 聚合出来的 `burst`（那一串突破整体），以及它和下跌段、横盘段、回踩的关系。`bo` 就像"原材料"，被加工成 `burst` 后，原材料本身就退到幕后了。

> 💡 **你现在应该能做到**：拿到一个陌生走势包的 `PatternSpec`，逐个角色看它的 detector + where，逐条边看它表达的关系，在脑子里还原出它想找的那个"故事"。这就是读懂 path2 走势包的核心能力。
