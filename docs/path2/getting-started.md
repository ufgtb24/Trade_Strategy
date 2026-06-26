# path2 入门：从零跑通你的第一个走势匹配

欢迎！如果你是第一次接触 path2，这篇文档就是为你写的。读完之后，你将能独立写出一段「描述某种 K 线走势、然后让程序在数据里自动找出它」的代码——全程不需要预先懂任何理论。

---

## 0. path2 是什么？（先建立直觉）

一句话：**path2 是一个让你"用搭积木的方式描述一种走势形态，再让引擎到行情数据里把它找出来"的框架。**

打个比方。假设你想在一大段股价走势里，找出这样的画面：

> "先有一段明显的下跌，跌完之后不久，冒出一个放量突破。"

如果让你手写代码去找，你得自己遍历每根 K 线、自己算下跌幅度、自己判断哪里是突破、还要算两者之间隔了多远——又繁琐又容易错。

path2 的思路完全不同：**你只负责"说清楚你要什么"，剩下的"怎么找"交给引擎。** 你把上面那句话拆成几块"积木"：

- 一块叫"下跌段"的积木
- 一块叫"突破点"的积木
- 一根连接它俩的"时间先后"约束（突破要在下跌之后不久出现）

把这几块拼成一张图（这张图就是后面会讲的 **PatternSpec**），交给引擎，引擎就会在你的数据里逐一搜索、把所有符合的画面都返回给你。

> 💡 **小贴士**：path2 是一个**独立的事件表达框架**。它跟项目里 BreakoutStrategy 那套选股/因子/挖掘的东西没有任何关系，你不需要了解那些概念。这里所有的"积木"都是自包含的。

**你现在应该理解了**：path2 = 声明式地描述走势 + 引擎自动匹配。下面我们就一步步把上面这个例子真正跑起来。

---

## 1. 准备运行环境

项目用 [uv](https://github.com/astral-sh/uv) 管理依赖，命令很简单：

```bash
# 首次：把依赖装好
uv sync

# 用项目环境跑你的脚本
uv run python my_script.py

# 或者进交互式 REPL 边写边试
uv run python
```

---

## 2. 第一步：给引擎喂一份数据（DataFrame）

引擎要在"数据"里找走势，所以第一件事是准备数据。

path2 里所有的检测器（detector，下面会解释）都只认一种输入：一个 **pandas DataFrame**。规矩只有两条，很好记：

- 行用整数下标（0, 1, 2, …），每一行就是一根 K 线；
- 至少要有这 5 列：`open`、`high`、`low`、`close`、`volume`。

下面我们造一段"假行情"来练手——它故意被设计成"先跌、再横盘、最后反弹"，方便我们待会儿能匹配到东西：

```python
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
n = 150

# 模拟一段先跌后横盘再反弹的行情
price_base = 100.0
closes = []
for i in range(n):
    if i < 50:
        closes.append(price_base * (1 - 0.003 * i))   # 下跌段
    elif i < 100:
        closes.append(closes[-1] * (1 + rng.uniform(-0.002, 0.002)))  # 横盘
    else:
        closes.append(closes[-1] * (1 + 0.004))        # 反弹

closes = np.array(closes)
df = pd.DataFrame({
    "open":   closes * (1 + rng.uniform(-0.005, 0.005, n)),
    "high":   closes * (1 + rng.uniform(0.003, 0.012, n)),
    "low":    closes * (1 - rng.uniform(0.003, 0.012, n)),
    "close":  closes,
    "volume": rng.integers(50_000, 500_000, n).astype(float),
})
```

**一句话总结**：数据就是一张行索引为整数、含 OHLCV 五列的表，一行一根 K 线。

---

## 3. 几个核心概念（先看懂，再上手）

在写代码之前，我们先认识 4 个角色。别担心，每个我都先用大白话告诉你"它是干嘛的"。

### detector（检测器）——"原料生产机"

**它是什么**：detector 是一个会扫一遍数据、然后"吐出"某一类事件的小机器。

比如：
- `TrendSegmentDetector` 扫一遍数据，把整段行情切成一段段"趋势区间"，每段标注它是 `down`（下跌）、`up`（上涨）还是 `sideways`（横盘）。
- `BODetector` 扫一遍数据，把每个"突破点"找出来。

你可以把 detector 想成榨汁机：丢进去一筐水果（DataFrame），它吐出一杯杯果汁（事件）。**你不用自己调用它**——后面引擎会替你调，你只需要在声明里指定"用哪台榨汁机"。

### Event（事件）——detector 吐出的"一颗果子"

**它是什么**：detector 产出的每一个东西就是一个 Event。它最基本的三个属性是：

- `event_id`：身份编号
- `start_idx`：起始 bar 下标
- `end_idx`：结束 bar 下标（单点事件如突破，`start_idx == end_idx`）

不同的 detector 产出不同子类的 Event，子类会带额外字段。比如 `TrendSegment`（趋势段事件）多带了 `regime`（下跌/横盘/上涨）和 `drawdown`（回撤幅度）；`BOEvent`（突破事件）多带了 `vol_ratio`（成交量倍数）等。

### NodeSpec（节点）——你模式里的一个"角色"

**它是什么**：NodeSpec 就是图里的一块积木，代表你模式中的一个角色。它回答两个问题：

1. "这个角色由哪台 detector 生产？"
2. "在它生产出来的一堆事件里，我只要满足什么条件的？"

第 2 点的"条件"，用 `where` 来写（下面 #4 细讲）。比如"下跌段"这个角色，就是"由 `TrendSegmentDetector` 生产，且 `regime == 'down'`、回撤 ≥ 20% 的那些事件"。

> 💡 **你不用告诉 NodeSpec 它产出什么类型的事件**。事件类型这种身份信息，引擎直接从你给的 detector 上读出来（每个 Event 子类有一个叫 `class_id` 的类属性，比如 `BOEvent.class_id == "bo"`、`BurstEvent.class_id == "burst"`），所以 NodeSpec 上**没有**「事件类型」这个字段，你只管说清"谁生产、满足什么 where"即可。

### 边（Edge）——连接两个角色的"约束绳"

**它是什么**：光有积木还不够，你得说清楚积木之间是什么关系。边就是连接两个 NodeSpec 的"约束绳"，规定它们在时间或空间上必须满足某种关系。

最常用的两种：

- **`TemporalEdge`（时序边）**：规定先后和间隔。比如"突破要出现在下跌结束后的 60 根 bar 之内"。
- **`ContainmentEdge`（包含边）**：规定一个区间套在另一个区间里。比如"突破点必须落在某段横盘区间的内部"。

### PatternSpec（模式）——把上面全装进一个盒子

**它是什么**：PatternSpec 就是最终那张完整的图——它把所有 NodeSpec（积木）和所有边（约束绳）打包成一个"模式声明"，这就是你交给引擎的东西。

> 💡 **设计上的关键分工**（理解了它，后面就不会混）：
> - **节点上的 `where`** 管"单个事件自己的属性"——比如这段下跌的回撤够不够深、这个突破的成交量够不够大。它只看一个事件。
> - **边** 管"两个事件之间的关系"——比如间隔多少 bar、谁包含谁。它看一对事件。
>
> 一个看"自己"，一个看"一对"，职责泾渭分明。

**你现在应该理解了**这 5 个词的关系：detector 生产 Event，NodeSpec 给某类 Event 取个角色名并加筛选条件，边把角色们的关系约束起来，PatternSpec 把这一切装成一张图。下面动手写。

---

## 4. 第二步：写出你的第一个 PatternSpec

我们先做最小版本：只要两个角色、一根边。

> **目标走势**：一段下跌（回撤 ≥ 20%），之后 60 根 bar 内出现一个放量突破（成交量倍数 ≥ 1.5）。

```python
from path2.atoms.trend import TrendSegmentDetector
from path2.atoms.breakout import BODetector
from path2.dag import (
    NodeSpec,
    PatternSpec,
    TemporalEdge,
    where as W,
)

spec = PatternSpec(
    pattern_id="down_then_bo",
    display_name="下跌后突破",
    nodes=(
        NodeSpec(
            "down",
            TrendSegmentDetector(ma_period=20),
            where=(
                ("regime",   W.attr("regime",   "==", "down")),
                ("drawdown", W.attr("drawdown", ">=", 0.20)),
            ),
            label="下跌段",
        ),
        NodeSpec(
            "bo",
            BODetector(total_window=10),
            where=(
                ("vol", W.attr("vol_ratio", ">=", 1.5)),
            ),
            label="突破点",
        ),
    ),
    edges=(
        TemporalEdge("down", "bo", min_gap=1, max_gap=60),
    ),
    root="down",
)
```

第一次看可能字段有点多，我们逐个拆开——**先理解，不用背**：

- **`node_id`**（第一个位置参数）：这个角色的唯一名字。后面边里写 `"down"`、`"bo"` 引用的就是它。
- **`detector`**（第二个位置参数）：指定这个角色用哪台"榨汁机"。注意你只是把 detector **传进去**，不用自己调用它。事件类型由引擎从这台 detector 自动读出（见上文 #3 的小贴士），你不需要、也没有字段去手填它。
- **`where`**：这个角色的筛选条件。格式是一串 `(clause_id, 谓词)`，多条之间是"且"（全部满足才算）。`clause_id` 是你给这条筛选起的名字（如 `"regime"`、`"vol"`），诊断结果时用它当 key——**同一个 node 内不能重名**（重了在构造 `PatternSpec` 时会直接报错提醒你）；不同 node 之间可以重复（两个 node 都叫 `"vol"` 没问题）。
- **`W.attr(name, op, thr)`**：最常用的筛选谓词，意思是"事件的 `name` 属性 `op` 阈值 `thr`"。比如 `W.attr("drawdown", ">=", 0.20)` = "回撤 ≥ 20%"。
- **`label`**：人类可读的名字，给面板显示用。
- **`TemporalEdge("down", "bo", min_gap=1, max_gap=60)`**：这根绳子要求 `bo.start_idx − down.end_idx ∈ [1, 60]`——也就是突破点开始的 bar，比下跌段结束的 bar 晚 1 到 60 根。
- **`root`**：填任意一个合法的 `node_id` 即可（引擎做校验用，不影响匹配结果）。

> ⚠️ **常见坑**：
> - `where` 的每一项是个**二元组** `(clause_id, 谓词)`，别只写谓词。
> - 即使只有一条 `where`，也要写成单元素元组，注意末尾那个逗号：`(("vol", W.attr(...)),)`。漏了逗号就不是元组了。

> 💡 **小贴士（None 很安全）**：有些字段可能是 `None`（比如 `BOEvent.vol_ratio` 在算不出时会是 `None`）。`W.attr` 遇到 `None` 会安全地返回 `False`（即"不满足"），**不会报错崩溃**。

---

## 5. 第三步：调用引擎

声明写好了，跑它只要一行：

```python
from path2.dag import analyze

result = analyze(spec, df)
```

`analyze(spec, df, params=None)` 是**唯一**的公开入口，返回一个 `AnalysisResult`。它替你做了所有脏活：

- **自动**按依赖顺序把所有节点的 detector 跑一遍、产出事件流——你**不需要**手动 `detector.detect(df)`。
- 然后在这些事件里搜索所有符合你 PatternSpec 的组合。

`params` 参数你现在可以忽略（传 `None` 或不传）。它的用途是：把任意运行时对象注入进去，供 `where` 谓词读取动态阈值。入门阶段用不到。

> 还有个布尔快捷方式：`from path2.dag import matches`，`matches(spec, df)` 等价于 `len(analyze(spec, df).matches) > 0`，只想知道"有没有命中"时很方便。

---

## 6. 第四步：读懂结果

`analyze` 返回的 `AnalysisResult` 有三样东西：

```python
result.events   # Tuple[Event, ...]  —— 所有节点产出的事件，平铺合在一起（可用来在图上标注原始事件）
result.matches  # Tuple[PatternMatch, ...]  —— 每命中一次就是一个 PatternMatch；没命中则是空 tuple
result.spec     # 你传进去的 PatternSpec 引用（可调 result.spec.to_topology() 拿可视化拓扑）
```

最关心的当然是 `result.matches`。每个命中是一个 `PatternMatch`，它本身也是一个 Event（所以有 `event_id` / `start_idx` / `end_idx`，分别是这次命中的编号和总区间）。

怎么从一次命中里把"那段下跌"和"那个突破"取出来？用 **`role_index`**——它是一个字典，`node_id → 绑定到的事件`：

```python
print(f"命中次数：{len(result.matches)}")

for m in result.matches:
    print(f"\n--- 命中 {m.event_id}  bar [{m.start_idx}, {m.end_idx}] ---")

    # role_index：用 node_id 取出这次命中里绑定的具体事件
    down_seg = m.role_index["down"]   # 一个 TrendSegment
    bo_event = m.role_index["bo"]     # 一个 BOEvent

    print(f"  下跌段: [{down_seg.start_idx}, {down_seg.end_idx}]  drawdown={down_seg.drawdown:.2%}")
    print(f"  突破点: bar={bo_event.start_idx}  vol_ratio={bo_event.vol_ratio}")
```

> 💡 **小贴士**：`role_index[node_id]` 取出的是**单个 Event**——前提是这个节点是普通节点。如果节点用了 Kleene（一次绑"一串"事件，是框架支持的高级特性，见 #11），取出来的就是一个事件元组 `Tuple[Event, ...]`。入门阶段、以及当前内置 app 都是普通节点（"一串突破"现在用嵌套事件表达，见 #10），放心当单个事件用。

### 想看"为什么命中/没命中"？看 predicate_trace

如果你想调试——比如某次本该命中却没命中——`PatternMatch` 还带了诊断信息：

```python
m.children         # 把所有绑定事件按 start_idx 升序展平的扁平视图（role_index 的派生）

trace = m.predicate_trace
if trace:
    # where_results: node_id -> {clause_id: 该条 where 是否通过}
    print(trace.where_results)
    # edge_results: (src_node_id, dst_node_id) -> EdgeWitness（这根边的实测情况）
    for (src, dst), witness in trace.edge_results.items():
        print(f"  边 {src}->{dst}  measured={witness.measured:.1f} bars")
```

`EdgeWitness` 记录了一根边在这次命中里的实证：`satisfied`（是否满足）、`src_instance` / `dst_instance`（边两端实际绑的事件）、`measured`（实测出来的 gap / overlap 数值）。

**你现在应该能**：跑出命中、从 `role_index` 取出每个角色的事件、并用 `predicate_trace` 排查细节了。

---

## 7. 第五步：再加一根边（ContainmentEdge 示例）

会了一根边，加第二根就很自然。假设我们想额外要求：**突破点必须落在某段横盘区间的内部**。

做两件事：(1) 新增一个 `side`（横盘段）角色；(2) 用 `ContainmentEdge` 把它和 `bo` 绑起来。

```python
from path2.dag import ContainmentEdge

spec2 = PatternSpec(
    pattern_id="down_side_bo",
    display_name="下跌-横盘-突破",
    nodes=(
        NodeSpec(
            "down",
            TrendSegmentDetector(ma_period=20),
            where=(
                ("regime",   W.attr("regime",   "==", "down")),
                ("drawdown", W.attr("drawdown", ">=", 0.20)),
            ),
            label="下跌段",
        ),
        NodeSpec(
            "side",
            TrendSegmentDetector(ma_period=20),
            where=(
                ("regime", W.attr("regime", "==", "sideways")),
            ),
            label="横盘段",
        ),
        NodeSpec(
            "bo",
            BODetector(total_window=10),
            where=(
                ("vol", W.attr("vol_ratio", ">=", 1.5)),
            ),
            label="突破点",
        ),
    ),
    edges=(
        TemporalEdge("down", "bo", min_gap=1, max_gap=60),  # bo 在 down 之后 60 bars 内
        ContainmentEdge("side", "bo"),                       # bo 落在 side 区间内
    ),
    root="down",
)

result2 = analyze(spec2, df)
print(f"命中次数：{len(result2.matches)}")
```

> 💡 **小贴士（包含边的方向）**：`ContainmentEdge` 的规范方向是「大区间 → 小区间」，写成 `ContainmentEdge("side", "bo")` 表示 `side.start ≤ bo.start` 且 `bo.end ≤ side.end`（即 bo 套在 side 里）。别写反了。

注意一个好玩的细节：`down` 和 `side` 各自**新建了一台** `TrendSegmentDetector`，因为 `where` 条件不同（一个要 `down`、一个要 `sideways`），它们成了两个不同的角色。这就是 `node_id` 存在的意义——同一种 detector 可以扮演多个角色。

> 💡 **当同一种 detector 被实例化多次时（自动消歧）**：上面 `down` 和 `side` 各持一台 `TrendSegmentDetector`，两台产出的事件 `class_id` 都是同一个，事件编号（`event_id`）前缀本来会撞车。引擎在跑流前会**自动**处理这件事：发现同一 `class_id` 有多台不同的 detector 时，按出现顺序给它们各编一个前缀（`trend0` / `trend1`），让编号不再相撞。这一切对你透明——你照常写两台 detector 即可，单台、或两个角色共享同一台对象、或你已手动命名的情况都不会被改动。

---

## 8. 完整可运行代码

把上面拼起来，下面这段可以直接 `uv run python quickstart.py` 跑：

```python
"""path2 最小 quickstart —— 可直接 uv run python quickstart.py 运行。"""
import numpy as np
import pandas as pd

from path2.atoms.trend import TrendSegmentDetector
from path2.atoms.breakout import BODetector
from path2.dag import (
    NodeSpec,
    PatternSpec,
    TemporalEdge,
    ContainmentEdge,
    analyze,
    where as W,
)


def main():
    # ── 1. 构造 DataFrame ──────────────────────────────────────────────
    rng = np.random.default_rng(42)
    n = 150
    price_base = 100.0
    closes = []
    for i in range(n):
        if i < 50:
            closes.append(price_base * (1 - 0.003 * i))
        elif i < 100:
            closes.append(closes[-1] * (1 + rng.uniform(-0.002, 0.002)))
        else:
            closes.append(closes[-1] * (1 + 0.004))
    closes = np.array(closes)
    df = pd.DataFrame({
        "open":   closes * (1 + rng.uniform(-0.005, 0.005, n)),
        "high":   closes * (1 + rng.uniform(0.003, 0.012, n)),
        "low":    closes * (1 - rng.uniform(0.003, 0.012, n)),
        "close":  closes,
        "volume": rng.integers(50_000, 500_000, n).astype(float),
    })

    # ── 2. 声明模式 ────────────────────────────────────────────────────
    spec = PatternSpec(
        pattern_id="down_side_bo",
        display_name="下跌-横盘-突破",
        nodes=(
            NodeSpec(
                "down",
                TrendSegmentDetector(ma_period=20),
                where=(
                    ("regime",   W.attr("regime",   "==", "down")),
                    ("drawdown", W.attr("drawdown", ">=", 0.20)),
                ),
                label="下跌段",
            ),
            NodeSpec(
                "side",
                TrendSegmentDetector(ma_period=20),
                where=(
                    ("regime", W.attr("regime", "==", "sideways")),
                ),
                label="横盘段",
            ),
            NodeSpec(
                "bo",
                BODetector(total_window=10),
                where=(
                    ("vol", W.attr("vol_ratio", ">=", 1.5)),
                ),
                label="突破点",
            ),
        ),
        edges=(
            TemporalEdge("down", "bo", min_gap=1, max_gap=60),
            ContainmentEdge("side", "bo"),
        ),
        root="down",
    )

    # ── 3. 运行引擎 ────────────────────────────────────────────────────
    result = analyze(spec, df)

    # ── 4. 读取结果 ────────────────────────────────────────────────────
    print(f"命中次数：{len(result.matches)}")
    print(f"所有节点产出事件数：{len(result.events)}")

    for m in result.matches:
        down_seg = m.role_index["down"]
        side_seg = m.role_index["side"]
        bo_event = m.role_index["bo"]

        print(f"\n命中 {m.event_id}  总区间 [{m.start_idx}, {m.end_idx}]")
        print(f"  下跌段  [{down_seg.start_idx:>3}, {down_seg.end_idx:>3}]"
              f"  drawdown={down_seg.drawdown:.2%}")
        print(f"  横盘段  [{side_seg.start_idx:>3}, {side_seg.end_idx:>3}]")
        print(f"  突破点  bar={bo_event.start_idx:>3}"
              f"  vol_ratio={bo_event.vol_ratio}")

    # 拓扑投影（供可视化面板）
    topo = result.spec.to_topology()
    print("\n--- 拓扑节点 ---")
    for node in topo.nodes:
        print(f"  {node.node_id}  class_id={node.class_id}  kleene={node.kleene}")
    print("--- 拓扑边 ---")
    for edge in topo.edges:
        print(f"  {edge.src} --[{edge.kind}]--> {edge.dst}")


if __name__ == "__main__":
    main()
```

运行：

```bash
uv run python quickstart.py
```

**到这里，你已经独立跑通了一个完整的 path2 匹配流程。** 下面是查阅性的速查表——不用通读，需要时回来翻即可。

---

## 9. 速查表（先看懂上文，再来查）

> 下面这几张表是"参考手册"性质的，把你可能用到的字段、边类型、谓词都列全了。新手不必背，按需查阅。

### 9.1 NodeSpec 的字段

字段顺序与 dataclass 定义一致（`node_id` / `detector` 是前两个位置参数，其余有默认值）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | `str` | 角色的唯一名字，在边的 `src` / `dst` 中引用 |
| `detector` | object | 事件生产者，引擎自动调用，无需手动跑 |
| `where` | `Tuple[(clause_id, fn), ...]` | 节点级一元谓词，多条之间 AND（默认空 `()`） |
| `kleene` | `KleeneSpec \| None` | `None`=单实例；非 `None`=绑一串事件（默认 `None`，框架高级特性，详见 #11） |
| `consumes_stream` | `str \| None` | `None`=消费原始 `df`；填某 `node_id`=消费该节点产出的事件流（默认 `None`，详见下文 9.1.1） |
| `label` | `str` | 人类可读名，面板显示用（默认空 `""`） |

> 事件类型**不在** NodeSpec 上声明——它由 `detector.event_cls.class_id` 自动得出（每个 Event 子类用类属性 `class_id` 标身份，如 `"bo"` / `"trend"` / `"burst"`）。

#### 9.1.1 consumes_stream：让 detector 之间串成流水线

默认情况下，每个 detector 都从头扫一遍原始 `df`（`consumes_stream=None`，称为「根 detector」，比如 `bo`、`down`、`side`）。但有时你想让一台 detector **吃另一个节点产出的事件流**，而不是从零再扫一遍数据——这时就把 `consumes_stream` 填成那个上游节点的 `node_id`。

引擎据此给 detector 排好先后顺序：根 detector 先跑、拿 `df`；消费者后跑、拿到上游那条事件流。这样 detector 就接成了一条数据流水线，避免重复扫描。

最典型的例子在内置 app `bottom_breakout_burst` 里：`burst`（把密集突破聚合成一串）和 `tb`（评估回踩）两个节点都写了 `consumes_stream="bo"`——它们都吃 `bo` 节点产出的突破事件流。

### 9.2 边类型

这一节列出所有边类型。每根边都规定一对事件 `(src, dst)` 必须满足的关系。

| 类 | 语义 | 典型用途 |
|----|------|---------|
| `TemporalEdge(src, dst, min_gap=0, max_gap=inf)` | `dst.start_idx − src.end_idx ∈ [min_gap, max_gap]` | 时序先后、lookback 窗口 |
| `ContainmentEdge(src, dst)` | `src.start ≤ dst.start` 且 `dst.end ≤ src.end`（大区间含**整个**小区间） | 小事件整体落在大区间内 |
| `StartContainmentEdge(src, dst)` | `src.start ≤ dst.start ≤ src.end`（只看 dst 的**起点**） | 只要求小事件的起点落在大区间内，不管它的尾巴伸到哪 |
| `OverlapEdge(src, dst)` | `src.start < dst.start < src.end < dst.end`（部分交叠） | dst 从 src 内部起、延伸到 src 之后 |
| `EqualsEdge(src, dst)` | `src` 与 `dst` 起止完全相同 | 同 bar 多维信号并发 |
| `NegationEdge(src, dst, min_gap=0, max_gap=inf, inner_predicate=None)` | `src` 锚定窗口内**禁止**出现满足条件的 `dst` | 排除干扰事件 |

> 💡 **`StartContainmentEdge` 和 `ContainmentEdge` 差在哪**：两者都要求小事件（dst）的**起点**落在大事件（src）区间内；区别是 `ContainmentEdge` **还**额外要求 dst 的**终点**也被 src 包住（`dst.end ≤ src.end`，即整体被包），而 `StartContainmentEdge` 不管 dst 的终点。当你只关心"某个宽事件的**起点**落在某段背景里"、却不想连带要求它的尾巴也缩在背景内时，就用 `StartContainmentEdge`。内置 app 里 `side → burst` 就用它——只要求那串突破的起点落在横盘段内，突破往后冲出横盘段是允许的。

> ⚠️ **NegationEdge 是"反着的"**：它表达的是"窗口里**不许**有这种 dst"。被它约束的 dst 是个约束条件，**不会**进入 `role_index` / `children`（它不是结构成员）。`min_gap`/`max_gap` 定义禁区窗口，`inner_predicate`（可选）进一步限定"什么样的 dst 才算违禁"。
>
> `TemporalEdge` 还有个 keyword-only 的 `strict` 参数（默认 `False`），置 `True` 表示 next 语义（src 与 dst 之间窗内不能有更早的同类 dst）。入门用不到。

### 9.3 where 谓词工厂（均从 `path2.dag.where` 导入，惯例 `import ... as W`）

这一节列出所有筛选谓词。**入门和当前内置 app 都只用 `W.attr`**——它就够你写绝大多数条件了。下面 `first` / `last` / `count` / `any` / `distinct` / `reduce` 这几个是「序列聚合」谓词，服务于 Kleene 节点（一个节点绑**一整串**事件，属高级特性，见 #11），入门可以完全跳过。

| 函数 | 适用节点 | 语义 |
|------|---------|------|
| `attr(name, op, thr)` | 普通节点 | `e.<name> op thr` |
| `first(name, op, thr)` | Kleene 节点（高级） | `seq[0].<name> op thr`（串首） |
| `last(name, op, thr)` | Kleene 节点（高级） | `seq[-1].<name> op thr`（串尾） |
| `count(op, thr)` | Kleene 节点（高级） | `len(seq) op thr`（串的长度） |
| `any(name, op, thr)` | Kleene 节点（高级） | `∃ e∈seq: e.<name> op thr`（存在一个满足） |
| `distinct(name, op, thr)` | Kleene 节点（高级） | 去重后数量 `op thr`（`name` 是 tuple 字段时会 flatten，如 `broken_peak_ids`） |
| `reduce(name, fn, op, thr)` | Kleene 节点（高级） | `fn([e.<name> for e in seq]) op thr`（自定义聚合） |
| `all(*fns)` | 通用 | 把多个谓词 AND 合取成一个 |

`op` 的合法取值：`">="` / `">"` / `"<="` / `"<"` / `"=="` / `"!="`。

> 💡 **小贴士**：所有谓词遇到属性值为 `None` 时都安全返回 `False`（不满足），绝不抛异常。所以像 `BOEvent.drought`、`vol_ratio` 这种可能为 `None` 的字段可以放心比较。

### 9.4 结果对象的关键字段

```python
result.events          # Tuple[Event, ...]  —— 所有节点事件流平铺
result.matches         # Tuple[PatternMatch, ...] —— 命中列表
result.spec            # PatternSpec 引用

m = result.matches[0]
m.event_id             # 本次命中的编号（继承自 Event）
m.start_idx            # 命中区间起点（= 所有绑定事件 start_idx 的最小值）
m.end_idx              # 命中区间终点（= 所有绑定事件 end_idx 的最大值）
m.pattern_id           # 该命中所属模式的 pattern_id
m.role_index           # {node_id: Event | Tuple[Event, ...]}  —— Kleene 节点取出的是序列
m.children             # role_index 展平后按 start_idx 升序的 Tuple[Event, ...]
m.predicate_trace      # PredicateTrace | None —— where / 边的求值诊断

# 拓扑投影（用于可视化面板）
topo = result.spec.to_topology()  # PatternTopology
topo.nodes   # Tuple[TopoNode, ...]  —— 每个 TopoNode 有 node_id / class_id / label / kleene
topo.edges   # Tuple[TopoEdge, ...]  —— 每个 TopoEdge 有 src / dst / kind（kind = 边的子类名）
```

---

## 10. 进阶：把"一串"事件打包成一个事件（嵌套事件）

### 先讲为什么——一串东西需要一个"身份"

回到开头那个例子。很多时候你要找的不是"一个突破"，而是"短时间内**密集冒出的一串**突破"——它们挤在一起，整体上才构成"突破爆发"这个画面。

问题来了：这一串突破，在框架里该怎么表示？一个个散点突破（`bo`）当然各自是一个 Event，但**整串**呢？谁来代表"这一串"？如果没有一个实体代表它，你就没法像引用一个普通宽事件那样去引用它、没法用一个 `where` 检查"整串的属性"（比如这串里出现过几个不同的峰、最大放量多少倍）、也没法把"这一串"整体画在图上。

path2 给出的答案是 **嵌套事件**（也叫复合 Event）：**一个事件内部还可以装着更小的子事件**。

### 是什么——BurstEvent

内置 app `bottom_breakout_burst` 就用这招把"一串突破"做成一个一等公民事件 `BurstEvent`（burst = 爆发）：

- 它有自己的 `start_idx`（= 串里**第一个** bo 的起点）和 `end_idx`（= 串里**最后一个** bo 的终点），所以它就是一个普普通通的"宽事件"，跟"下跌段""横盘段"地位一样，可以被边引用、被画在图上。
- 它内部用一个 `members` 字段装着组成它的那些 `BOEvent`（装的是**完整的事件对象**，不是 id）。
- 它在被生产出来时，就顺手把几个"整串的汇总指标"算好存成普通字段：`count`（串里有几个 bo）、`distinct_pk`（串里突破了几个不同的峰）、`max_vol_ratio`（串里最大放量倍数）、`first_drought`（串首那个 bo 的"久旱"长度）。这样你写 `where` 时直接 `W.attr("distinct_pk", ">=", 3)` 读这些字段就行，**不用每次自己去遍历 `members`**。

于是"这一串突破要满足什么"就退化成了对一个普通宽事件的普通 `where`——和你前面学的写法**完全一样**。

### 谁来生产它——BurstDetector

把散点 bo 切成一串、再打包成 `BurstEvent` 的，是一台叫 `BurstDetector` 的 detector。它有两个值得注意的点：

- 它**不自己去扫数据找突破**，而是 `consumes_stream="bo"`——**吃 `bo` 节点产出的突破流**（就是上文 9.1.1 讲的流水线）。这遵守"每种事件只由一种 detector 负责生产"的原则。
- 它的工作只有两件：把密集的 bo **切成极大的一段段**、每段打包成一个 `BurstEvent` 并算好那几个汇总指标。"切串"的参数（每个 bo 离串首多远算同一串 `max_span`、一串至少几个 bo 才算数 `min_bos`）走它的构造函数；而像"放量要够大""峰要够多"这种**阈值过滤**，统统不传给 detector，而是落在 burst 节点的 `where` 上。

### 怎么用——Event 基类的嵌套协议

任何 Event 都自带一套访问内部结构的方法（普通的叶子事件没有子事件，这些方法默认返回空，行为和以前完全一样）：

- `e.children("members")`——取出一组命名的子事件（如 `BurstEvent` 的整串 bo）。
- `e.child("first_bo")` / `e.child("last_bo")`——取出单个命名子事件（给边的"端点选择"用：你甚至能让一条边连到 burst 的"串首那个 bo"，而不是 burst 整体）。
- `e.child_slots()`——遍历用的主子事件集合。
- `e.descendant_leaves`——一路递归展平到最底层、没有子事件的原子事件。

> 入门你只要记住一句话就够：**"一串密集突破"现在是一个叫 `BurstEvent` 的宽事件，它内部装着那些 bo，整串的属性（峰数、放量、长度）当成它自己的字段用 `W.attr` 读。** 想看真实写法，去读 `path2_apps/bottom_breakout_burst/dag_spec.py` 的 `build_pattern`。

### 一个小补充：孤立 role 与"残缺命中"的过滤

在那个内置 app 里，`bo` 节点本身**不连任何边**——它只负责当"密度流源层"：给 `burst`（切串）和 `tb`（评回踩）当输入，同时也能被单独扫出来画在 K 线上（每个突破点一个标记）。一个不连任何边的节点叫**孤立 role**。

引擎在出口处会自动做一件事：如果某个命中**只**包含这种孤立 role、没凑成完整形态，它就是"残缺命中"（语义垃圾），会被丢弃。判断哪些节点是孤立的，引擎直接从你声明的边里推（哪些 `node_id` 从没在任何边上出现过），不需要你额外标注。**入门不必深究这一点**——只要知道"光有 `bo`、没凑齐其它角色的画面不会被当成命中"即可。

---

## 11. 下一步去哪学

当你想做更复杂的模式时：

- **把"一串"事件打包成一个事件（嵌套事件）**——比如"连续多个突破组成一簇爆发"：这是当前内置 app 的真实做法，去看 `path2_apps/bottom_breakout_burst/dag_spec.py` 里的 `build_pattern` 函数（上文 #10 已详解）。一串 bo 在那里是一个 `BurstEvent`，由 `BurstDetector` 消费 `bo` 流切串聚合而成。
- **让一个 detector 消费另一个节点的事件流（`consumes_stream`）**——同上文件里，`burst`（切串聚合）和 `tb`（评回踩）都写了 `consumes_stream="bo"`，靠它把 detector 接成数据流水线（上文 #9.1.1）。
- **绑"一串"事件（Kleene，框架的另一条路）**——除了嵌套事件，框架**还**支持用 Kleene 让"一个节点"直接绑"一整串"同类事件（配合 9.3 表里的 `first` / `last` / `count` / `any` / `distinct` 这些序列聚合谓词，以及 `KleeneSpec`）。它仍是框架的正式特性、随时可用；只是当前内置 app 选择了上面那条更干净的"嵌套事件"路、没有用它。如果你想试 Kleene，给某个 NodeSpec 传一个 `kleene=KleeneSpec(...)` 即可。
- **只想要布尔判断**——`from path2.dag import matches`，`matches(spec, df)` 直接告诉你"有没有命中"。

祝你玩得愉快！
