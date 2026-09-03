# 实战范例：bottom_burst

> 这是一篇**手把手教学**。如果你第一次接触 path2，建议从头读到尾——我们会从"想描述一种股票走势"这个最朴素的念头出发，一步步看它如何变成一段可以扫描全市场的声明式代码。读完你应该能照葫芦画瓢，自己写出一个新走势包。

本篇以 `path2_apps/bottom_burst/dag_spec.py` 为蓝本，完整走一遍：

1. **先搞懂要描述什么** —— "底部反转突破爆发"这个走势，用人话拆成 7 条约束
2. **path2 的世界观** —— 节点 / 边 / where / 嵌套事件，四个核心概念各是什么、解决什么问题
3. **节点映射** —— 5 个 `NodeSpec` 怎么承载这 7 条约束
4. **边映射** —— 3 条类型化边在表达什么关系
5. **`build_pattern` 工厂逐行解读**
6. **调用 `analyze`、读取结果**

> 💡 **一个先打的预防针**：这个走势里有"一连串密集突破点"这种东西。在 path2 里，**一串密集的同类事件可以聚合成一个一等的"宽事件"**——本篇里它叫 `BurstEvent`，由一个专门的探测器 `BurstDetector` 在扫描时把散点突破打包而成。这样"那一整串突破"就和"一段下跌""一段横盘"一样，是一个可以被引用、被画在图上、被一条条件整体检查的实体。这是本篇最核心的新概念，第二节会展开。

---

## 零、先建立直觉：path2 在做什么？

一句话：**path2 让你"用文字描述一种股票走势的形状"，然后它替你去历史数据里把这种形状找出来。**

打个比方。假设你想找"先跌一波、然后在底部横盘、横盘期间连续放量突破、最后回踩确认"这种经典反转走势。如果手写代码，你得自己遍历 K 线、维护一堆状态机、拼各种 if-else——又臭又长还容易错。

path2 换了个思路：你只需要**声明**这个走势"长什么样"（由哪些片段组成、片段之间有什么先后/包含关系），剩下的"怎么在数据里把它匹配出来"全部交给框架引擎。你写的是**规格说明（spec）**，不是匹配算法。

> 💡 **一句话总结**：你负责"描述形状"，path2 负责"找到形状"。本篇就是带你写出一份这样的形状描述。

---

## 一、先搞懂要描述什么：7 条业务约束

在写任何代码之前，先把"底部反转突破爆发"这个走势用大白话讲清楚。它描述的是这样一个故事：

> 一只股票先经历**一段明显下跌**，跌到底后开始**横盘震荡**；在横盘期间，价格**密集地、连续地向上突破**前期高点；最后一次突破之后，价格**回踩确认**了支撑，没有破位。

把这个故事拆成 7 条可以判定真假的约束（后面我们会一条条把它们落到代码里）：

| 编号 | 业务含义（人话） | 涉及字段/阈值 |
|------|----------|---------------|
| ① | 连续突破的**第一个突破点**，必须落在一段横盘区间里 | `TrendSegment.regime == "sideways"` |
| ② | 连续突破的**数量**不能太少 | `BurstEvent.count >= MIN_BOS`（默认 3） |
| ③ | 第一个突破点，距离上一次突破**隔了足够久**（久旱逢甘露，说明这是新一轮启动） | `BurstEvent.first_drought >= THR_DROUGHT`（默认 40） |
| ④ | 横盘之前，必须先有一段**足够深的下跌** | `TrendSegment.regime == "down"` ∧ `drawdown >= pred4_min_drawdown`（默认 0.25），且这段下跌在第一个突破点前 `pred4_lookback_bars`（默认 120）根 K 线之内 |
| ⑤ | 这一连串突破，覆盖的**不同前期高点（peak）**数量不能太少 | `BurstEvent.distinct_pk >= THR_PK`（默认 3） |
| ⑥ | 这串突破里，**至少有一次是放量的**（成交量倍数足够大） | `BurstEvent.max_vol_ratio >= THR_VOL`（默认 3.0） |
| ⑦ | 最后一次突破之后，**紧接着出现回踩确认** | `ThrowbackEvent.confirmed == True`，且紧跟最后一个 bo（间隔 = 1） |

> 💡 注意 ②③⑤⑥ 这四条都在描述"那一整串突破"的集体属性（一共几次、第一次旱了多久、覆盖几个高点、有没有放量）。在新模型里，这一整串突破就是一个 `BurstEvent` 宽事件，这四个集体属性在扫描时就被预先算好、存成了它自己的字段（`count` / `first_drought` / `distinct_pk` / `max_vol_ratio`）。所以这四条不再是"对一串散点做聚合判断"，而是"读这个宽事件的一个普通字段"——第三节会看到它们就是几条朴素的 `where` 条件。

> ⚠️ **常见坑**：这 7 条里，有的是在说"单个片段自己的属性"（比如 ②③⑤⑥ 都在描述突破串本身），有的是在说"两个片段之间的关系"（比如 ① 是"突破落在横盘里"、④ 是"下跌在突破之前不远处"、⑦ 是"回踩紧跟突破"）。**记住这个区分**——它正好对应 path2 的两个核心概念，下一节就讲。

---

## 二、path2 的世界观：节点、边、where

要把上面 7 条约束写成 path2 声明，你只需要理解三个概念。我们先讲它们各自**是什么、解决什么问题**，再讲怎么写。

### 概念 1：节点（NodeSpec）—— "走势里的一个片段"

**节点就是走势里的一个组成片段。** 比如"那段下跌"是一个节点，"那段横盘"是一个节点，"那一整串突破"是一个节点，"那次回踩"是一个节点，此外还有一个产出全部单点突破、当上游原料的"突破流"节点。我们这个走势由 5 个节点组成——下一节会逐个看，其中"突破流" `bo` 比较特殊，是个不直接连边的孤立流源（专门产出散点突破，喂给"突破串"和"回踩"当原料）。

每个节点回答三个问题：

- **它是什么角色？** —— 用一个 `node_id` 字符串命名（如 `"down"` / `"side"` / `"bo"` / `"tb"`）。
- **这种片段从哪来？** —— 每个节点自带一个 **detector（探测器）**，detector 负责扫 K 线、源源不断地产出这一类"原始事件"。比如 `TrendSegmentDetector` 会把整段行情切成一段段趋势（下跌段、横盘段、上涨段）。
- **要满足什么条件？** —— 用 `where` 给这个片段加过滤条件（详见概念 3）。

> 💡 detector 产出的是**未经筛选的原始事件流**。比如 `TrendSegmentDetector` 会吐出所有趋势段，但我们的 `down` 节点只想要其中"下跌且跌得够深"的那些——筛选靠 `where`。

### 概念 2：边（Edge）—— "两个片段之间的关系"

**边描述两个节点之间的关系。** 光有片段还不够，走势的关键在于片段之间的**先后顺序和位置关系**。比如：

- "下跌"必须在"突破"**之前**（先后关系）；
- "突破"必须落在"横盘"**里面**（包含关系）；
- "回踩"必须**紧跟**在"突破"之后（先后关系，且间隔精确）。

path2 把这些关系做成了**类型化的边**——不同种类的关系用不同的边类，比如：

- `TemporalEdge`（时序边）：表达"A 结束后，B 在 [min_gap, max_gap] 根 K 线内开始"这种**先后+间隔**关系。
- `ContainmentEdge`（包含边）：表达"A 区间**包住**了 B 区间"这种**包含**关系。

> 💡 **为什么要分成不同的边类？** 因为引擎对每种关系有专门的高效判定和剪枝逻辑。你只管选对边类、填好参数，引擎自然知道怎么快速匹配。框架里还有 `OverlapEdge`（部分交叠）/ `EqualsEdge`（完全同段）/ `NegationEdge`（禁止存在）等其它边类，本走势用不到，先不展开。

### 概念 3：where —— "给单个片段加的过滤条件"

**`where` 是挂在节点上的"一元谓词"**——所谓"一元"，就是它只看**一个**片段自己的属性，不涉及别的片段。

回忆第一节那个"常见坑"：约束有两类。

- **"片段自己的属性"** → 用 **`where`**（节点上）。比如"这段下跌的 `drawdown >= 0.25`"、"这段趋势的 `regime == 'down'`"。
- **"两个片段之间的关系"** → 用 **边**。比如"下跌在突破之前不远处"。

这就是 path2 设计的脊梁——**`where`（一元，看单个片段）和边（二元，看一对片段）正交分工**，互不越界。理解了这条分工线，你就理解了 path2 的一大半。

`where` 的具体条件用 `W.*` 系列工厂函数来写（来自 `path2.dag.where` 模块，习惯导入为 `W`）：

本走势里，每个 `where` 条件都只是"读这个片段的某个字段，和一个阈值比一比"。最常用、也是本走势**唯一**用到的写法就一种：

| 写法 | 含义 | 用在哪 |
|------|------|--------|
| `W.attr("regime", "==", "down")` | 这个片段的 `regime` 字段 == `"down"` | 任意节点，读片段自身字段 |
| `W.attr("first_drought", ">=", 40)` | 这个片段的 `first_drought` 字段 >= 40 | 同上，阈值改成数值即可 |

`W.attr(字段名, 比较符, 阈值)` 就够覆盖本走势所有的 `where`——不管这个字段是"一段下跌的回撤幅度"，还是"一整串突破里第一次旱了多久"，统一都是"读一个字段、比一个阈值"。后面会看到，**正是因为"那一串突破"已经被聚合成了一个带现成字段的 `BurstEvent`，描述它的集体属性才能这么朴素**。

> 💡 **小贴士**：`W.*` 这一层故意做得很小、很封闭（奥卡姆剃刀）——只覆盖业务真正用到的几个算子。你不会在这里看到方向性/区间类算子，因为那些都被"边"吸收掉了。

> 📎 **旁注（进阶，本走势用不到）**：框架里 `W.*` 其实还有一组"序列聚合"谓词——`W.first` / `W.last` / `W.count` / `W.any` / `W.distinct` 等，专门用来对**一个节点绑定的一整串事件**做"看第一个 / 看有没有某个 / 去重计数"这类判断。它们服务的是框架的另一条路线（Kleene 闭包，见第三节末的现状说明）。本走势因为把"一串突破"直接聚合成了 `BurstEvent` 宽事件、属性都成了现成字段，所以一个序列聚合谓词都不需要——全部用 `W.attr` 直读即可。

### 概念 4：嵌套事件（`BurstEvent`）—— "把一串密集事件打包成一个宽事件"

走势里大多数片段是"一个东西"：一段下跌、一段横盘、一次回踩。但"连续突破"不一样——它天生是**一连串**密集的突破点，而不是单独一个。

**path2 的做法是：把这一连串密集的同类事件，聚合成一个一等的"宽事件"。** 在本走势里它就是 `BurstEvent`：

- 它有自己的起点和终点——`start_idx` = 串里**第一个**突破的位置，`end_idx` = 串里**最后一个**突破的位置；
- 它内部用一个 `members` 字段，装着组成它的那些单点突破事件（完整对象，不是 id）；
- 它在被探测出来的同时，就把"这一串"的几个集体属性预先算好、存成普通字段：`count`（一共几次突破）、`first_drought`（第一次旱了多久）、`distinct_pk`（覆盖几个不同高点）、`max_vol_ratio`（最大放量倍数）。

> 💡 **用人话讲它解决了什么**：有了 `BurstEvent`，"那一整串突破"终于像"一段下跌""一段横盘"一样，是一个**可以被引用、可以被画在图上、可以被一条 `where` 整体检查属性**的实体。约束 ②③⑤⑥ 描述的就是这一整串的集体属性——现在它们只是读 `BurstEvent` 的四个现成字段而已。

> 💡 这就是"嵌套事件"（composite event）：一个事件内部还装着更小的子事件（`BurstEvent` 里装着一串 `BOEvent`）。负责把散点突破打包成 `BurstEvent` 的，是一个叫 `BurstDetector` 的探测器——第三节会看到它怎么写。

**你现在应该理解了**：节点=片段、边=片段间关系、where=片段自身条件、嵌套事件=把一串密集同类事件打包成一个可整体引用的宽事件。带着这四个概念，我们开始把 7 条约束逐一落地。

---

## 三、节点映射：5 个 NodeSpec

我们的走势由 5 个节点组成：`bo`（单点突破流）、`down`（下跌段）、`side`（横盘段）、`burst`（突破爆发，把 `bo` 聚合成的宽事件）、`tb`（回踩确认）。它们的关系长这样：

```
            (bo —— 孤立流源层，不参与连边)
                  │  consumes（喂给 burst / tb 当原料）
                  ▼
down ──TemporalEdge──► burst ──TemporalEdge──► tb
                        ▲
side ─StartContainment──┘
```

读法：

- **真正连成走势的是 `burst`**——`down`（下跌）在 `burst` 之前，`side`（横盘）包住 `burst` 的起点，`burst` 之后紧跟 `tb`（回踩）。这三条关系就是三条边。
- **`bo` 是个"孤立流源层"**——它自己不连任何边，只负责产出全部单点突破，再把这条突破流"喂"给 `burst`（用来切串聚合）和 `tb`（用来逐个评估回踩）。一句大白话：`bo` 是上游原料厂，不直接出现在走势的骨架里，但 `burst` 和 `tb` 都靠它供料。

> 💡 为什么 `bo` 不连边、却还留它一个节点？因为我们既想用它当原料（喂 `burst`/`tb`），也想能单独把所有突破点画在 K 线上。引擎对这种"没有任何边连它"的孤立节点有专门处理（见本节末"`bo` 节点"小节），既不让它污染走势匹配、又能让它独立扫描渲染。

下面逐个节点看。

### 节点 `down`（下跌段，承载约束 ④）

```python
NodeSpec(
    "down",
    TrendSegmentDetector(**params.trend_kwargs()),
    where=(
        ("regime",   W.attr("regime",   "==", "down")),
        ("drawdown", W.attr("drawdown", ">=", params.pred4_min_drawdown)),
    ),
    label="下跌段",
)
```

逐个字段解读：

- 第一个参数 `"down"` 是 **node_id**（这个节点的角色名）。
- `TrendSegmentDetector(...)` 是这个节点的 **detector**：它逐根看 K 线的均线变化，把行情切成一段段连续的趋势，每段产出一个 `TrendSegment`，自带 `regime`（`"down"` / `"sideways"` / `"up"`）和 `drawdown`（这段的回撤幅度）。
- `where` 是节点级过滤条件，多条之间是 **AND（且）** 关系：只有**同时**满足 `regime == "down"` 且 `drawdown >= 0.25` 的趋势段，才算合格的"下跌段"。

> 💡 你可能注意到 `NodeSpec` 并没有写"这个节点产出什么类型的事件"。**不需要写**——事件类型的身份由 detector 自己声明（`detector.event_cls.class_id`，本例是 `TrendSegment` 的 `"trend"`），面板上色等都从这里取，无需在 `NodeSpec` 里重复声明。

> ⚠️ 注意：约束 ④ 里还有"在突破前 120 根内"这半句——那是**两个片段之间的关系**，不属于 `where`，而是由后面 `TemporalEdge(down -> burst, max_gap=120)` 这条边来承载（见第四节）。`where` 这里只管"这段下跌自己跌得够不够深"。

### 节点 `side`（横盘段，承载约束 ①）

```python
NodeSpec(
    "side",
    TrendSegmentDetector(**params.trend_kwargs()),
    where=(
        ("regime", W.attr("regime", "==", "sideways")),
    ),
    label="横盘段",
)
```

这里有个值得停下来体会的点：**`side` 和 `down` 用的是同一类 detector（都是 `TrendSegmentDetector`），但它们各自 `new` 了一个独立的 detector 实例**——在工厂里就是：

```python
down_det = TrendSegmentDetector(**params.trend_kwargs())
side_det = TrendSegmentDetector(**params.trend_kwargs())
```

为什么要各持一个独立实例、而不是共用一个？因为这两条趋势流要扮演不同角色（一条筛横盘、一条筛下跌），独立实例让分轨更清晰。引擎在第一阶段会让这两个节点**各自跑一遍** detector，得到两条趋势段流：一条用 `regime == "sideways"` 过滤出横盘段，另一条用 `regime == "down"` 过滤出下跌段，互不干扰。

> 💡 **这里有一个引擎自动替你处理的小机制**：`down` 和 `side` 的 detector 是同一类，产出的事件类型 id 都是 `"trend"`——如果不管，两条流产出的事件 id 前缀就会相撞。**引擎在跑流之前会自动发现"同一类 detector 出现了两个实例"，给它们自动编号 `trend0` / `trend1`**（这个 id 前缀钩子叫 `source_tag`），让两条流的事件 id 不打架。你**不需要手写**任何编号——单实例、共用同一实例、或你手动命名过的情况，引擎都不会去动。这属于"引擎替你兜底"的背景机制，知道有这回事即可。

同理，约束 ① 的"突破落在横盘内"这半句是**关系**，由 `StartContainmentEdge(side -> burst)` 那条边承载，不在 `where` 里。

### 节点 `bo`（单点突破流源，不直接承载约束）

`bo` 节点最简单：它就是个原料厂。`BODetector` 逐根扫 K 线，每检测到一次突破就产出一个单点突破事件 `BOEvent`，没有任何 `where`、也不连任何边。

```python
NodeSpec("bo", BODetector(**params.bo_kwargs()))
```

`BODetector` 产出的 `BOEvent` 是**单点事件**（`start_idx == end_idx ==` 突破那根 K 线的索引），每个携带 `drought`（距上次突破隔了多少根）、`broken_peak_ids`（这次突破打穿了哪些前期高点，是个 tuple）、`vol_ratio`（成交量倍数）等字段。

它在走势里扮演两个角色，但**自己不参与任何形态约束**：

1. 当**原料**——这条突破流被喂给 `burst`（切串聚合成宽事件）和 `tb`（逐个评估回踩），见下文。
2. 当**可独立渲染的密度层**——因为它没连任何边，所有 `bo` 都能单独被扫描出来、画在 K 线上，方便人眼看"哪里突破密集"。

> 💡 **新概念：孤立流源 + 引擎自动过滤残缺匹配**。`bo` 这种"图里没有任何边连它"的节点，叫**孤立节点**。如果不管它，引擎会把每一个单独的 `bo` 候选都当成一次"匹配"（只含 `bo` 这一个角色、其它角色都缺席的残缺匹配），那是一堆语义垃圾。**引擎在出口处会自动识别出这种孤立节点（判据完全从你声明的边推出来，不需要你做任何标记），把"只含孤立节点"的残缺匹配丢掉。** 效果就是：`bo` 既能当原料、又能独立渲染，但**绝不会**污染真正的走势匹配。这又是一个"引擎替你兜底"的机制，你只管把 `bo` 声明成无 `where`、无边的普通节点即可。

### 节点 `burst`（突破爆发，承载约束 ②③⑤⑥）—— 本走势的核心宽事件

`down` / `side` / `bo` 都是从 K 线直接探测的"原始"片段。`burst` 不一样：它的原料不是 K 线，而是 `bo` 节点产出的那条突破流——它把密集的散点突破**切串、打包**成一个 `BurstEvent` 宽事件（就是第二节讲的嵌套事件）。

为什么需要它？因为约束 ②（突破数量 >= 3）、③（首次突破久旱）、⑤（覆盖 >= 3 个不同 peak）、⑥（至少一次放量）说的都不是单个突破，而是**整串突破的集体属性**。把这一串聚合成一个 `BurstEvent`、属性预先算成字段之后，这四条约束就退化成几条朴素的 `where`：

```python
NodeSpec(
    "burst",
    BurstDetector(**params.burst_kwargs()),
    where=(
        ("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),  # ③
        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),        # ⑤
        ("vol_spike",     W.attr("max_vol_ratio", ">=", params.THR_VOL)),       # ⑥
    ),
    consumes_stream="bo", label="突破爆发",
)
```

#### `BurstDetector` 做了什么

`BurstDetector` 是个**派生 detector**——它不自己造 `BODetector`（遵守"detector 之间互相独立"的原则），而是**消费 `bo` 流**（靠下面会讲的 `consumes_stream="bo"`），把密集的突破切成一段段，每段打包成一个 `BurstEvent`。切串的口径很直观：按位置排序后从前往后扫，每个还没归段的突破当段首，把"起点距段首不超过 `max_span` 根"的后续突破都吸进同一段；一段里突破数 >= `min_bos` 才产出一个 `BurstEvent`。

`BurstDetector` 在打包时就顺手把这一串的几个集体属性算好，存成 `BurstEvent` 的字段：`count`（突破数）、`first_drought`（串首突破的旱期）、`distinct_pk`（去重后覆盖几个高点）、`max_vol_ratio`（最大放量倍数）。

> ⚠️ **一个容易混的点：切串参数 vs 业务阈值，分两处**。
> - **切串参数**（`max_span` 怎么算"够密集"、`min_bos` 切串的最低条数）走 `BurstDetector` 的**构造函数**——它们决定"怎么切成一串"。其中 `min_bos` 取的就是顶层的 `MIN_BOS`（默认 3），这正是约束 ②。
> - **业务阈值**（`THR_DROUGHT` / `THR_PK` / `THR_VOL`）**不传给 detector**，而是走 `burst` 节点的 `where`——它们决定"切好的这一串够不够格"，对应约束 ③⑤⑥。

逐条对照约束：

- **约束 ②（`min_bos`）**：`BurstDetector(min_bos=MIN_BOS)` —— 只有突破数 >= 3 的段才会被打包成 `BurstEvent`。
- **约束 ③（`where`）**：`W.attr("first_drought", ">=", 40)` —— 直读 `BurstEvent.first_drought`（串首突破的旱期），要求 >= 40。
- **约束 ⑤（`where`）**：`W.attr("distinct_pk", ">=", 3)` —— 直读 `BurstEvent.distinct_pk`（这串覆盖的不同高点数，detect 期已去重算好），要求 >= 3。
- **约束 ⑥（`where`）**：`W.attr("max_vol_ratio", ">=", 3.0)` —— 直读 `BurstEvent.max_vol_ratio`（这串里最大的放量倍数），要求 >= 3.0。"至少一次放量"被等价表达成"最大放量倍数够大"。

> 💡 **回头看第二节那句"先为什么"**：正是因为有了 `BurstEvent` 这个宽事件、把"一串"的集体属性预先算成了字段，描述 ②③⑤⑥ 才能这么平铺直叙——全部是 `W.attr` 直读，一个序列聚合谓词都不用。这就是"嵌套事件"带来的表达力红利。

### 节点 `tb`（回踩确认，承载约束 ⑦）

```python
NodeSpec(
    "tb",
    ThrowbackDetector(**params.throwback_kwargs()),
    consumes_stream="bo",
    label="回踩确认",
)
```

这个节点把上面已经出现过的概念**派生节点**讲透。

#### `consumes_stream` —— "我的原料不是 K 线，而是上游节点的产出"

通常一个 detector 的输入是原始的 OHLCV `DataFrame`。但 `ThrowbackDetector` 不一样：判断"是否回踩确认"必须**先知道在哪里突破**。所以它的输入是 `bo` 节点产出的 `BOEvent` 流，而不是原始 `df`。

`consumes_stream="bo"` 就是在声明这件事："我这个节点是**派生**的，请把 `bo` 节点的产出喂给我。" 引擎在第一阶段会按拓扑顺序，**先**跑 `bo`，**再**把 bo 流传给 `ThrowbackDetector` 去逐个评估。

> 💡 **注意 `tb` 吃的是 `bo` 流（单点突破事件），不是 `burst` 流（宽事件）**。回踩是逐个突破点向后看的，所以 `tb` 直接消费一颗颗 `BOEvent`。`burst` 同样 `consumes_stream="bo"`——`bo` 这一条流被 `burst` 和 `tb` 两个下游节点共同消费（`burst` 拿去切串，`tb` 拿去评回踩），这正是把 `bo` 设计成"孤立流源层"的意义。

`ThrowbackDetector` 对每个 `BOEvent` 向后扫描，**只在回踩确认成立时**才产出一个 `ThrowbackEvent`（回踩失败/超时的不产事件）。这个事件的 `start_idx = 触发它的 bo.end_idx + 1`（回踩窗的起点），`end_idx = trigger_idx`（实际确认的那根 K 线）。

> 💡 **一句话总结**：`consumes_stream` 让节点之间能"接力"——上游算出事件，下游拿去加工。`burst` 和 `tb` 都是靠它接 `bo` 这条流的下游。

### ⚠️ 一个重要澄清：Kleene 还在，只是本走势没用它

如果你读过 path2 早期的资料，可能见过一个叫 **Kleene 闭包**（`KleeneSpec`）的机制——它让"一个节点绑定的不是单个事件、而是一整串同类事件"，并在求解时对这一整串做聚合判断。早期版本的本走势，"那串突破"正是用 Kleene 节点表达的。

**现在本走势改用了嵌套事件（`BurstEvent` + `BurstDetector`），不再使用 Kleene。** 但请别误会成"Kleene 被删了"：

- **框架层面，Kleene 完整保留、仍然可用**：`KleeneSpec` 数据类、求解器里的串绑定逻辑、面板诊断对串的支持、以及那组序列聚合谓词（`W.first` / `W.last` / `W.count` / `W.any` / `W.distinct`）全都健在。你写别的走势时，如果一串事件**不适合**预先聚合成宽事件（比如串里成员要参与更复杂的逐个判断），完全可以继续用 Kleene。
- **应用层面，`bottom_burst` 这一个走势选择了嵌套事件这条更干净的路**：把"一串突破"直接打包成 `BurstEvent`、集体属性预算成现成字段，于是约束 ②③⑤⑥ 退化成几条 `W.attr` 直读，比当年的"序列聚合谓词"更直观。

> 💡 一句话：**Kleene 不是被废弃，是本走势刚好不需要它。** 选嵌套事件还是 Kleene，取决于你那串事件的属性能不能在探测期就一次性聚合好——能，就用嵌套事件（更简单）；不能，就用 Kleene。

---

## 四、边映射：3 条类型化边

节点讲完了，现在把它们用关系连起来。**三条边全部连到 `burst` 这个宽事件本体**（不是连到散点 `bo`），对应约束 ①④⑦ 里的"关系"部分：

```python
edges = (
    TemporalEdge("down", "burst", min_gap=1, max_gap=params.pred4_lookback_bars),  # ④
    StartContainmentEdge("side", "burst"),                                          # ①
    TemporalEdge("burst", "tb", min_gap=1, max_gap=1),                             # ⑦
)
```

> 💡 因为"那一串突破"现在是 `burst` 这一个宽事件（`start` = 首次突破位置、`end` = 末次突破位置），连边时直接拿这个宽事件本体去判关系即可——不用再像旧模型那样纠结"用串首还是串尾"。`burst.start` 天然就是首次突破，`burst.end` 天然就是末次突破，这正好对上各条边想要的语义。

### `TemporalEdge("down", "burst", min_gap=1, max_gap=120)` —— 下跌在突破之前不远处

`TemporalEdge` 表达"先后 + 间隔"。它判定的是：`burst.start_idx − down.end_idx ∈ [1, 120]`（`burst.start` 就是首次突破的位置）。

- `min_gap=1`：下跌段必须在首次突破**之前**就结束（严格在先，不能重叠）。
- `max_gap=120`：下跌段结束后，最多 120 根 K 线内必须出现首次突破，太久就不算"这波下跌的后续"了。
- 它和 `down` 节点的 `where` 合在一起，才完整表达约束 ④："首次突破之前 120 根内，存在一段回撤 >= 25% 的下跌段"——`where` 管"够深"，边管"在前面不远处"。

### `StartContainmentEdge("side", "burst")` —— 突破爆发的起点落在横盘里

这里用的不是普通的 `ContainmentEdge`，而是一个专门的**起点包含边** `StartContainmentEdge`。先讲它和普通包含边的区别：

- `ContainmentEdge`（普通包含边）要求小事件**整体**被大事件包住——既要 `小.start >= 大.start`，**还要** `小.end <= 大.end`。
- `StartContainmentEdge`（起点包含边）**只**要求小事件的**起点**落进大事件区间内（`大.start <= 小.start <= 大.end`），**不管小事件的终点**。

为什么这里要用起点包含边？业务上约束 ① 说的是"**第一个**突破点落在横盘里"——只关心首次突破的位置，不关心整串突破有没有冲出横盘。`burst.start` 就是首次突破的位置，所以我们只想约束 `burst.start` 落在横盘段里。如果用普通 `ContainmentEdge`，它会**额外**要求 `burst.end`（末次突破）也落在横盘内——这比原本的语义更严，会把"突破到后期已经走出横盘"的合法走势误杀掉。`StartContainmentEdge` 精确保留了"只看首次突破落在哪"这一层语义。

- 边的规范方向是**大区间 → 小事件**（`side` 包 `burst` 的起点），所以写成 `("side", "burst")`。
- 它判定的就是 `side.start_idx <= burst.start_idx <= side.end_idx`，完整表达约束 ①。

### `TemporalEdge("burst", "tb", min_gap=1, max_gap=1)` —— 回踩紧跟最后一次突破

又是一条 `TemporalEdge`，但 gap 卡死成 `[1, 1]`。它判定的是：`tb.start_idx − burst.end_idx ∈ [1, 1]`。

- 因为 `burst.end_idx` 就是**末次突破**的位置，所以这条边从"最后一次突破"起算，正合约束 ⑦ 想要的"回踩紧跟最后一次突破"。
- 还记得吗？`ThrowbackEvent.start_idx` 的定义恰好就是 `bo.end_idx + 1`。所以 `gap == 1` 不多不少，精确对齐了回踩窗的起点，完整表达约束 ⑦——"回踩紧紧贴着最后一次突破出现"。

> 💡 **你现在应该理解了**：约束里凡是"A 在 B 之前/之内/紧跟 B"这类话，都不写进 `where`，而是挑一条合适的边、填好参数。`where` 和边的分工到这里就完整闭环了。

---

## 五、`build_pattern` 工厂完整解读

把上面的节点和边拼起来，就是这只走势包的核心——`build_pattern` 工厂函数：

```python
# path2_apps/bottom_burst/dag_spec.py

def build_pattern(params: Params) -> PatternSpec:
    # down / side 各持一个独立的 TrendSegmentDetector 实例（激活引擎自动消歧 trend0/trend1）
    down_det = TrendSegmentDetector(**params.trend_kwargs())
    side_det = TrendSegmentDetector(**params.trend_kwargs())
    nodes = (
        # bo 孤立流源：无 where、无边，只当原料 + 可独立渲染（残缺 match 由引擎出口过滤）
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs())),

        NodeSpec("down",
                 down_det,
                 where=(("regime",   W.attr("regime",   "==", "down")),
                        ("drawdown", W.attr("drawdown", ">=", params.pred4_min_drawdown))),
                 label="下跌段"),

        NodeSpec("side",
                 side_det,
                 where=(("regime", W.attr("regime", "==", "sideways")),),
                 label="横盘段"),

        # burst 消费 bo 流切串聚合成 BurstEvent；②③⑤⑥ 全落在这里
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.THR_DROUGHT)),  # ③
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.THR_PK)),        # ⑤
                        ("vol_spike",     W.attr("max_vol_ratio", ">=", params.THR_VOL))),      # ⑥
                 consumes_stream="bo", label="突破爆发"),

        NodeSpec("tb",
                 ThrowbackDetector(**params.throwback_kwargs()),
                 consumes_stream="bo", label="回踩确认"),
    )
    edges = (
        TemporalEdge("down", "burst", min_gap=1, max_gap=params.pred4_lookback_bars),  # ④
        StartContainmentEdge("side", "burst"),                                          # ①
        TemporalEdge("burst", "tb", min_gap=1, max_gap=1),                             # ⑦
    )
    return PatternSpec(
        pattern_id="bottom_burst",
        display_name="底部反转突破爆发",
        nodes=nodes, edges=edges, root="burst",
    )
```

把代码读完，几个值得记住的要点：

- **为什么是个"工厂函数"而不是直接写死？** 因为所有阈值都来自传入的 `params`。同一份走势结构，喂不同的 `params` 就能生成不同松紧的扫描规格。`Params.trend_kwargs()` / `bo_kwargs()` / `throwback_kwargs()` 这几个辅助方法，把 `Params` 里带前缀的字段展开成 detector 的构造参数 dict，让 `Params` 保持为参数的唯一来源（SSoT）。
- **`root="burst"` 是什么？** 它是个**退化字段，引擎当前并不读取**，填任意一个合法的 `node_id` 即可（本走势填了 `"burst"`）。
- **构造时会自动体检。** `PatternSpec.__post_init__` 会在构造瞬间做几类校验：DAG 无环、每条边的端点都存在、`consumes_stream` 引用的节点合法（以及 Kleene 节点的基数/跨度合法——本走势没有 Kleene 节点，跳过）。任何违规会立即抛 `ValueError`，让你在写声明时就发现问题，而不是扫描到一半才崩。
- **工厂每次调用都返回新实例。** 适合批量扫描时按不同参数按需生成。此外模块顶层还有个常量 `PATTERN_DAG = build_pattern(Params.default())`，用于那些与具体参数无关的场景（比如下面会讲的拓扑投影 `to_topology()`）。

---

## 六、调用 `analyze`、读取结果

走势包写好了，怎么用？两个便利入口：`analyze`（要详细结果）和 `matches`（只要是/否）。

### 最简调用

```python
import pandas as pd
from path2_apps.bottom_burst.dag_spec import analyze, matches
from path2_apps.bottom_burst.params import Params

# df 是 OHLCV DataFrame，索引为整数行号（0, 1, 2, ...）
df: pd.DataFrame = ...

# 用默认参数扫描
result = analyze(df)  # 等价于 analyze(df, Params.default())
print(f"命中 {len(result.matches)} 次")

# 只需要是/否判断
if matches(df):
    print("该股存在 bottom_burst 走势")
```

### 自定义参数：放宽或收紧

想让扫描更宽松（命中更多）或更严格？改 `Params` 就行：

```python
params = Params(
    MIN_BOS=2,                # 放宽：最少 2 次连续突破
    THR_DROUGHT=30,           # 放宽：首 bo 间隔 >= 30 根
    pred4_min_drawdown=0.20,  # 放宽：前置下跌段 >= 20%
)
result = analyze(df, params)
```

### 遍历命中结果

`analyze` 返回一个 `AnalysisResult`，它有三个字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `events` | `Tuple[Event, ...]` | 所有节点流平铺（含**没命中**的 bo、TrendSegment 等原始事件） |
| `matches` | `Tuple[PatternMatch, ...]` | **每一次完整命中**对应一个 `PatternMatch` |
| `spec` | `PatternSpec`（默认 `None`） | 本次用的声明，可调用 `spec.to_topology()` |

每个 `PatternMatch` 里最有用的是 **`role_index`**——它是个字典，把每个 node_id 映射到这次命中里**实际绑定的那个事件（或那串事件）**。这正是你拿到"具体匹配到了哪段下跌、哪段横盘、哪几个突破"的地方：

```python
for m in result.matches:
    print(f"命中区间: [{m.start_idx}, {m.end_idx}]")

    # role_index: node_id -> 这次命中绑定的事件（本走势全是单实例）
    down_seg = m.role_index["down"]     # TrendSegment（单实例）
    side_seg = m.role_index["side"]     # TrendSegment（单实例）
    burst_ev = m.role_index["burst"]    # BurstEvent（单个宽事件，不是 tuple！）
    tb_ev    = m.role_index["tb"]       # ThrowbackEvent（单实例）

    print(f"  下跌段: [{down_seg.start_idx}, {down_seg.end_idx}]"
          f"  drawdown={down_seg.drawdown:.1%}")
    print(f"  横盘段: [{side_seg.start_idx}, {side_seg.end_idx}]")
    # 整串突破的集体属性，直读 BurstEvent 的现成字段；
    # 组成它的那些单点突破在 burst_ev.members 里
    print(f"  突破爆发: 共 {burst_ev.count} 次突破，"
          f"区间 [{burst_ev.start_idx}, {burst_ev.end_idx}]，"
          f"首 bo.drought={burst_ev.first_drought}，"
          f"覆盖 {burst_ev.distinct_pk} 个高点，"
          f"最大放量={burst_ev.max_vol_ratio:.1f}x")
    print(f"    首突破 idx={burst_ev.members[0].end_idx}，"
          f"末突破 idx={burst_ev.members[-1].end_idx}")
    print(f"  回踩确认: trigger_idx={tb_ev.trigger_idx}，"
          f"strength={tb_ev.strength.tier if tb_ev.strength else 'N/A'}")
```

> ⚠️ **常见坑**：`role_index["burst"]` 拿到的是**单个 `BurstEvent` 宽事件**，不是 tuple——它的集体属性（`count` / `first_drought` / `distinct_pk` / `max_vol_ratio`）都是现成字段直读，组成它的那些单点突破在 `burst_ev.members` 里（`members[0]` 是首突破、`members[-1]` 是末突破）。
>
> 另外 `role_index` 里**没有 `"bo"` 键**：`bo` 是孤立流源，不进任何完整命中（它的残缺 match 被引擎出口过滤掉了）。要看这次命中涉及的单点突破，从 `burst_ev.members` 拿；要看全图所有突破（含没命中的），从 `result.events` 里筛 `BOEvent`。

### 读取谓词实证（predicate_trace）—— 调试 / 做面板时用

如果你想知道"这次命中里，每条 `where`、每条边到底是怎么判过的"，`PatternMatch.predicate_trace` 把每一步的求值结果都留了痕，非常适合调试或给 UI 面板做可视化：

```python
m = result.matches[0]
trace = m.predicate_trace

# where 子句逐条结果：node_id -> {clause_id: 是否通过}
for node_id, clauses in trace.where_results.items():
    for clause_id, passed in clauses.items():
        print(f"  [{node_id}] {clause_id}: {'✓' if passed else '✗'}")

# 边实证（EdgeWitness）：留下了这条边判定时两端各是谁、实测 gap 多少
for (src, dst), witness in trace.edge_results.items():
    print(f"  edge {src}->{dst}: gap={witness.measured:.0f} bars"
          f"  (src.end={witness.src_instance.end_idx},"
          f"   dst.start={witness.dst_instance.start_idx})")
```

> 💡 `EdgeWitness.src_instance` / `dst_instance` 直接是参与这条边的事件本体。比如 `burst -> tb` 这条边，`src_instance` 就是那个 `BurstEvent`（它的 `end_idx` 正是末次突破的位置），`dst_instance` 就是 `ThrowbackEvent`——trace 里看到的实测 gap 就是这两者直接算出来的。

### 获取拓扑投影 —— 给面板画结构图

如果你只想要走势的**结构图**（有哪些节点、哪些边），而不关心具体某只股票的命中，用 `to_topology()`。它和参数无关，所以直接用模块级常量 `PATTERN_DAG` 即可：

```python
from path2_apps.bottom_burst.dag_spec import PATTERN_DAG

topo = PATTERN_DAG.to_topology()

for node in topo.nodes:
    # node.class_id 是该节点产出的事件类型 id（来自 detector.event_cls.class_id）
    kleene_mark = " [Kleene]" if node.kleene else ""
    print(f"  节点 {node.node_id} ({node.class_id}){kleene_mark}")

for edge in topo.edges:
    print(f"  边 {edge.src} --{edge.kind}--> {edge.dst}")
```

输出示例（本走势没有任何 Kleene 节点，所以不会出现 `[Kleene]` 标记）：

```
  节点 bo (bo)
  节点 down (trend)
  节点 side (trend)
  节点 burst (burst)
  节点 tb (tb)
  边 down --TemporalEdge--> burst
  边 side --StartContainmentEdge--> burst
  边 burst --TemporalEdge--> tb
```

> 💡 注意 `down` 和 `side` 的 `class_id` 都是 `trend`（它们用同一类 detector）。面板要分轨展示时，靠的是第二节讲的 `source_tag`（`trend0` / `trend1`）来区分这两条流，而不是 `class_id`。`[Kleene]` 标记这个字段框架里仍然保留——只是本走势把"一串突破"改用了嵌套事件 `burst`、没有任何 Kleene 节点，所以你在本例的输出里看不到它。

---

## 七、回头看：7 条约束的最终归宿（速查表）

> 这一节是**总结性速查表**。把前面六节学到的对应关系一次性列清——以后写新走势包时，可以直接照着这张"约束 → 用什么承载"的对照表来想。

| 约束 | 归宿 | 承载方式 |
|------|------|----------|
| ① burst 起点落横盘内 | `StartContainmentEdge("side", "burst")` + `side.where(regime=="sideways")` | 起点包含边 + 一元谓词 |
| ② 突破数量 >= MIN_BOS | `BurstDetector(min_bos=MIN_BOS)`（切串下界） | detector 切串参数 |
| ③ 首突破 drought >= THR_DROUGHT | `burst.where(W.attr("first_drought", ">=", THR_DROUGHT))` | 直读宽事件字段 |
| ④ 前置大幅下跌 + lookback 窗 | `TemporalEdge("down","burst", min_gap=1, max_gap=120)` + `down.where(regime=="down", drawdown>=0.25)` | 时序边 + 两条一元谓词 |
| ⑤ distinct peak >= THR_PK | `burst.where(W.attr("distinct_pk", ">=", THR_PK))` | 直读宽事件字段 |
| ⑥ ∃ bo vol_ratio >= THR_VOL | `burst.where(W.attr("max_vol_ratio", ">=", THR_VOL))` | 直读宽事件字段 |
| ⑦ 末 bo 后紧跟回踩确认 | `ThrowbackDetector(consumes_stream="bo")` + `TemporalEdge("burst","tb", min_gap=1, max_gap=1)` | 派生节点 + 时序边 |

读懂这张表，你就抓住了 path2 的精髓：**单个片段的条件靠 `where`，片段间的关系靠边，一串密集同类事件聚合成一个嵌套宽事件（`BurstEvent`）靠专门的 detector 切串，节点之间接力靠 `consumes_stream`。** 换一个走势，无非是换不同的片段、不同的关系、重新填这几个格子而已。

---

## 附录：相关符号速查

> 这是一张**纯查阅表**，列出本篇出现的所有符号及其出处。不用通读，需要时回来查。

| 符号 | 模块 | 用途 |
|------|------|------|
| `Params` | `path2_apps/bottom_burst/params.py` | 参数 SSoT，`default()` / `from_yaml()` 构造 |
| `build_pattern(params)` | `path2_apps/bottom_burst/dag_spec.py` | 参数化声明工厂 |
| `analyze(df, params)` | `path2_apps/bottom_burst/dag_spec.py` | 顶层便利入口，返回 `AnalysisResult` |
| `matches(df, params)` | `path2_apps/bottom_burst/dag_spec.py` | 布尔判断便利入口 |
| `PATTERN_DAG` | `path2_apps/bottom_burst/dag_spec.py` | 模块级 `PatternSpec` 常量（默认参数） |
| `NodeSpec` | `path2.dag.nodes` | 节点声明（角色 + detector + where + consumes_stream） |
| `consumes_stream`（`NodeSpec` 字段） | `path2.dag.nodes` | 声明本节点 detector 吃 df（`None`）还是上游某节点的事件流 |
| `TemporalEdge` | `path2.dag.edges` | 时序边（gap 约束） |
| `ContainmentEdge` | `path2.dag.edges` | 包含边（小事件整体被大区间包住） |
| `StartContainmentEdge` | `path2.dag.edges` | 起点包含边（只约束小事件起点落进大区间，不管终点）；本走势 `side→burst` 用 |
| `PatternSpec` | `path2.dag.spec` | 纯声明容器，`to_topology()` 投影 |
| `W.attr` | `path2.dag.where` | where 一元谓词工厂（读单个片段/宽事件的一个字段比阈值）；本走势全部 `where` 用它 |
| `AnalysisResult` | `path2.dag.result` | 引擎返回值（events / matches / spec） |
| `PatternMatch` | `path2.dag.result` | 单次命中（role_index / children / predicate_trace） |
| `BOEvent` | `path2.atoms.breakout` | 单点突破事件（drought / broken_peak_ids / vol_ratio） |
| `BurstEvent` | `path2.atoms.breakout` | 一串突破聚合成的嵌套宽事件（count / first_drought / distinct_pk / max_vol_ratio / members） |
| `BurstDetector` | `path2.atoms.breakout` | 消费 bo 流切串聚合成 `BurstEvent` 的派生 detector（`max_span` / `min_bos`） |
| `TrendSegment` | `path2.atoms.trend` | 趋势分段事件（regime / drawdown） |
| `ThrowbackEvent` | `path2.atoms.throwback` | 回踩确认事件（trigger_idx / strength / confirmed） |

> 📎 **本走势没用到、但框架仍提供的符号**（写别的走势可能会碰到）：`KleeneSpec`（`path2.dag.nodes`，"一个节点绑一整串同类事件"的 Kleene 闭包规格，本走势改用嵌套事件 `BurstEvent`、未用它）、以及一组序列聚合谓词 `W.first / W.last / W.count / W.any / W.distinct`（`path2.dag.where`，对一个节点绑定的整串事件做聚合判断，服务 Kleene 路径）。它们都还在框架里、仍可用，只是本示例不需要。
