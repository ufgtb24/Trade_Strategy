# Path 2 API 参考手册

> **版本**:v0.1(2026-05-15)
> **对齐**:`path2_spec.md` v0.1
> **目的**:以 API 为中心的速查手册。每个 API 给出**签名 + 概念 + 参数 + 用法 + 陷阱**。看完后能脱离教程查任意 API。
> **建议阅读顺序**:先 `path2_tutorial.md` 建心智模型 → 再查本手册。
>
> **范围**:本手册只覆盖**协议层 API**(spec §1 + §2)。stdlib(常用 Event/Detector 模板)与 DSL 层(若做)另作文档。

---

## 0. 概念总览

### 0.1 三层叙事

Path 2 的全部 API 围绕三个角色:

| 角色 | 性质 | API |
|---|---|---|
| **Event** | 名词(一行结构化数据) | `Event` 基类、必有字段(`event_id` / `start_idx` / `end_idx`)、可选容器字段(`children` / `parent`) |
| **Detector** | 动词(把数据/事件流变成上层事件) | `Detector` 协议、`detect()` 方法、yield 时序约束、完整性约束 |
| **Pattern** | 形容词(描述事件之间的约束) | **5 个关系算子** + **1 个组合子** + `TemporalEdge` 声明类型 |

**关键**:Pattern **不是一个类**,是一个**判定函数** — 由关系算子 + `Pattern.all` 组合而来,返回 `bool`,绑定一条事件流来评估。

### 0.2 API 全集(本手册的协议层 10 项)

| 类型 | API | 一句话 |
|---|---|---|
| 核心类型 | `Event` | 事件 row 的基类(frozen dataclass) |
| 核心类型 | `Detector` | 产出事件的协议 |
| 核心类型 | `TemporalEdge` | 声明两端点标签间的时序边约束 |
| 驱动 | `run(detector, *source)` | 推荐驱动:套安全网驱动 Detector(见 §1.4) |
| 关系算子 | `Before(anchor, predicate, window)` | anchor 之前 N bar 内满足 |
| 关系算子 | `At(anchor, predicate)` | anchor 自身满足 |
| 关系算子 | `After(anchor, predicate, window)` | anchor 之后 N bar 内满足 |
| 关系算子 | `Over(events, attribute, reduce, op, thr)` | 容器 reduce 后比较 |
| 关系算子 | `Any(events, predicate)` | 容器至少一个满足 |
| 组合子 | `Pattern.all(*predicates)` | AND 组合成最终 predicate |

**协议层就这 10 个**;其他都是用户自定义的子类 / Detector / Pattern 函数。另有 stdlib(经 `path2/__init__` 出口,不属本手册协议层范围):

- **标准 PatternDetector**:`Chain`/`Dag`/`Kof`/`Neg` + `PatternMatch`,消费 `TemporalEdge` 声明——见 `path2_spec.md` §7.1 与算法权威 `docs/research/path2_algo_core_redesign.md`。
- **便利层**:`BarwiseDetector`(逐 bar 单点扫描模板,子类只实现 `emit(df, i) -> Optional[Event]`,主循环 + None 过滤归模板;零领域假设/零跨事件校验)+ `span_id(kind, s, e)`(单点 `s==e` → `kind_s`,区间 → `kind_s_e`)——见 `docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`。stdlib **不提供任何 Event 子类**(领域字段使用方私有不可预沉淀),**不提供"窗口内 ≥N"detector**(滑动动态计数,`Kof` 边松弛不覆盖,见该 spec 写回横幅)。

---

## 1. 核心类型

### 1.1 `Event`

#### 签名

```python
from abc import ABC
from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class Event(ABC):
    event_id: str           # 持久身份
    start_idx: int          # 起始 bar(含)
    end_idx: int            # 结束 bar(含)
```

#### 概念

事件是 Path 2 中**唯一**的数据载体 — 一行结构化、不可变、字段齐全的 row。所有具体形态的事件类(`BO`、`VolSpike`、`L2Cluster` …)都继承自 `Event`。

#### 必有字段

| 字段 | 类型 | 语义 |
|---|---|---|
| `event_id` | `str` | 同一 Detector 单次 run 内**唯一**。推荐格式 `<kind>_<start_idx>_<end_idx>` 或 `<kind>_<i>`,**不在协议层面强制** |
| `start_idx` | `int` | 事件起始 bar 序号(含) |
| `end_idx` | `int` | 事件结束 bar 序号(含)。**必须** `start_idx <= end_idx`;单 bar 事件两者相等 |

#### 可选容器/引用字段(协议约定名)

| 字段名 | 类型 | 用于 | 约束 |
|---|---|---|---|
| `children` | `List[Event]` | **聚合事件**(L2/L3) 持下层组成员 | 必须**按 `start_idx` 升序** |
| `parent` | `Event` | **派生事件** 反向引用上层 | `parent.end_idx <= self.start_idx` |

这两个名字是**协议约定**(用别的名字也行,但用这俩名更便于跨实现复用 stdlib)。

#### 子类化规则

```python
@dataclass(frozen=True)              # ① 必须 frozen
class BO(Event):
    drought: float                   # ② 业务字段自由加
    broken_peaks: List[int]
    vol_spike: bool
    # 不要重写 event_id / start_idx / end_idx
    # 不要加 __init__(@dataclass 已生成);用 @property 表达派生字段
```

| 规则 | 说明 |
|---|---|
| 必须 `@dataclass(frozen=True)` | 一旦 yield,字段不可改 — 这是"Row 落地 = 字段完成"不变式的实现保证 |
| 自由加业务字段 | `drought: float`、`vol_spike: bool`、`children: List[Event]` … |
| 不重写必有字段 | `event_id` / `start_idx` / `end_idx` 由 base class 提供 |
| 不要 `__init__` | dataclass 已生成;派生字段用 `@property` |

#### 用法示例

```python
# 例 1:单 bar 原子事件
@dataclass(frozen=True)
class VolSpike(Event):
    ratio: float

vs = VolSpike(event_id="vol_42", start_idx=42, end_idx=42, ratio=2.3)

# 例 2:多 bar 聚合事件
@dataclass(frozen=True)
class Cluster(Event):
    children: List[Event]            # 协议约定:按 start_idx 升序

# 例 3:派生事件
@dataclass(frozen=True)
class SecondLaunch(Event):
    parent: Event                    # 协议约定:parent.end_idx <= self.start_idx
    relaunch_strength: float
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 用 `@dataclass` 没加 `frozen=True` | base class 应在 `__init_subclass__` 抛 `TypeError` |
| yield 后修改字段(`event.x = ...`) | frozen 阻止;违反"Row 落地 = 字段完成" |
| `start_idx > end_idx` | 应在 `__post_init__` 抛 `ValueError` |
| `children` 不按 `start_idx` 升序 | 违反 §3.3;实现层 runtime check(可选) |

---

### 1.2 `Detector`

#### 签名

```python
from typing import Protocol, Iterator, Any

class Detector(Protocol):
    def detect(self, source: Any) -> Iterator[Event]:
        ...
```

#### 概念

Detector 是**唯一会产出 Event 的东西**。无论从原始 `df` 造 L1 原子事件,还是从下层事件流聚合 L2,从 L2 派生 L3 — 都是 Detector。形态上就是一个**有状态的 generator**。

#### 接口约定

| 项 | 约定 |
|---|---|
| 方法 | 单个 `detect(self, source) -> Iterator[Event]` |
| source 类型 | **L1**:类 DataFrame 对象;**L2+**:`Iterable[Event]`(可附加 `df` 作第二参数) |
| 返回 | `Iterator[Event]`(generator 函数即可) |

#### 两条核心契约

**契约 1 — yield 时序**:必须按 `end_idx` 升序 yield(`end_idx` 相同时任意顺序)。下游消费时无需重排序。

**契约 2 — 完整性**:yield 出来的 Event,**所有字段都必须已就绪**(无 `NaN` / `None` / sentinel)。
- 若某字段需要"看后 K bar"才能算(如 post-window 平台度),Detector **等 K bar 观察完才 yield**
- 不允许"先 yield partial,稍后补字段"

#### 状态管理

- Detector **可以有状态**(FSM、滑窗、buffer)
- **状态在 `detect()` 内部局部变量里**,而不是 `self.*` — 避免跨调用泄漏

#### 用法示例

```python
# 例 1:逐 bar 触发型(无状态)
class VolSpikeDetector:
    def detect(self, df):
        for i in range(20, len(df)):
            ratio = df.vol[i] / df.vol[i-20:i].mean()
            if ratio > 2.0:
                yield VolSpike(event_id=f"vol_{i}", start_idx=i, end_idx=i, ratio=ratio)

# 例 2:FSM 多阶段
class BPEntryDetector:
    def detect(self, df):
        state = 'idle'                              # 状态全在函数局部
        bo_high = bo_day = None
        for i in range(len(df)):
            if state == 'idle' and is_breakout(df, i):
                state = 'breakout_done'
                bo_high, bo_day = df.high[i], i
            elif state == 'breakout_done' and is_entry(df, i):
                yield BPEntry(event_id=f"bp_{bo_day}_{i}",
                              start_idx=bo_day, end_idx=i, bo_high=bo_high)
                state = 'idle'                      # 重置

# 例 3:消费下层事件流(L2)
class ClusterDetector:
    def detect(self, bo_stream, df, min_bos=3, max_span=30, post_window=10):
        bos = list(bo_stream)
        i = 0
        while i < len(bos):
            j = i
            while j < len(bos) and bos[j].end_idx - bos[i].end_idx <= max_span:
                j += 1
            members = bos[i:j]
            if len(members) >= min_bos:
                # 等 post_window bar 观察完才计算 post_platform(契约 2)
                post_plat = compute_platform(df, members[-1].end_idx,
                                             members[-1].end_idx + post_window)
                yield Cluster(event_id=f"cl_{members[0].event_id}_{members[-1].event_id}",
                              start_idx=members[0].start_idx,
                              end_idx=members[-1].end_idx,
                              children=members, post_platform=post_plat)
                i = j
            else:
                i += 1
```

> **便利件(stdlib,已就绪)**:例 1「逐 bar 触发型」是最高频样板,可用 `BarwiseDetector` 免写扫描主循环——子类只实现 `emit(self, df, i) -> Optional[Event]`(命中返回你的 Event 子类,否则 `None`);lookback 由 `emit` 内 `if i < N: return None` 自管,模板对 `i` 零领域假设、零跨事件校验。`event_id` 可用 `span_id(kind, s, e)`。例 2(FSM)/例 3(L2 簇,滑动计数)**无现成件**,仍按此处手写(`Kof` 边松弛不覆盖滑动 ≥N)。详见 `docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`。

#### 陷阱

| 错误 | 原因 |
|---|---|
| 状态写到 `self.*` | 跨 `detect()` 调用污染。应放局部 |
| yield 后还修字段(经由可变默认值) | 违反 frozen + 契约 2 |
| 字段含 `NaN` 也 yield | 违反契约 2;典型场景是 lookforward 没等够就 yield |
| yield 顺序乱(end_idx 倒退) | 违反契约 1 |

---

### 1.3 `TemporalEdge`

#### 签名

```python
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class TemporalEdge:
    earlier: str               # 较早端点的声明期标签(非 event_id)
    later: str                 # 较晚端点的声明期标签(非 event_id)
    min_gap: int = 0           # 最小间隔(含),单位:bar
    max_gap: float = math.inf  # 最大间隔(含);math.inf 无上限
```

#### 概念

`TemporalEdge` 是**声明性的时序约束 datatype**。它本身**不参与计算**,只描述"标签 X 的某事件与标签 Y 的某事件之间应满足什么样的间隔"。`earlier`/`later` 是**声明期端点标签,不是 `event_id`**;由消费的 stdlib PatternDetector(`Chain`/`Dag`/`Kof`/`Neg`)在 run 时把每个标签解析到一条事件流,据 gap 公式驱动匹配。

#### gap 精确定义

```
gap = later.start_idx - earlier.end_idx
```

| 设置 | 含义 |
|---|---|
| `min_gap=0` | later 可与 earlier 同 bar 紧接或紧后(`later.start_idx >= earlier.end_idx`) |
| `min_gap=1` | later **严格在 earlier 之后**,中间至少 1 bar 空隙 |
| `max_gap=N` | later 必须在 earlier 之后**不超过 N bar** |
| `max_gap=math.inf` | 无上限(等价于"earlier 一旦发生永远算前置") |

#### 用法示例

```python
# 声明:BO 之后 5 bar 内必须有 VolSpike
edge = TemporalEdge(earlier='bo', later='vol', min_gap=0, max_gap=5)

# 声明:A → B → C 三段顺序的两条边
edges = [
    TemporalEdge(earlier='a', later='b', min_gap=0, max_gap=10),
    TemporalEdge(earlier='b', later='c', min_gap=0, max_gap=10),
]

# 这些边由 stdlib 标准 PatternDetector 消费(Chain/Dag/Kof/Neg,已就绪;见下方说明)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 把 `earlier` / `later` 当成具体 event 的 `event_id` | 它们是**声明期端点标签**;每个标签由消费的 PatternDetector 解析到一条事件流,对象级匹配在消费端做 |
| 把 `TemporalEdge` 当成可执行的检测器 | 它只是声明 — 必须由 PatternDetector 消费才会落到事件流 |
| `min_gap > max_gap` 或 `min_gap < 0` | `TemporalEdge.__post_init__` 直接抛 `ValueError`(构造点拦截) |

> **说明**:`TemporalEdge` 是**声明性 datatype**,本身不计算 — 必须有消费者读它的字段、按 §1.3.1 gap 公式驱动匹配,才会落到事件流。
>
> **消费者(已就绪)**:stdlib 标准 PatternDetector —— `Chain`(线性链)/ `Dag`(DAG 多入度)/ `Kof`(k 选 n)/ `Neg`(链 + 否定窗口)—— 已沉淀于 `path2/stdlib/`,经 `path2/__init__` 出口,统一产出 `PatternMatch`,**不允许用户自写**(见 `path2_spec.md` §7.1)。其约束推进核心是 **LEF-DFS**;复杂度是诚实账(Chain 近线性 headline,病态宽前沿 DAG 指数——非先前设想的"单调双指针 O(N)",已被实现轮证伪)。算法权威见 `docs/research/path2_algo_core_redesign.md`。**协议层只定 schema(`TemporalEdge` + gap 公式),不绑实现;用户写声明(`edges`),stdlib 跑执行**。
>
> **escape hatch**:标准件不够用时仍可降级——"A→B→C"类形态直接用嵌套 `Before` 算子(无需 `TemporalEdge`),或自写组合 Detector 接受 `edges: List[TemporalEdge]` 内部按 gap 公式逐对校验后 yield。理解协议层底盘是用好 stdlib 与降级的前提。

---

### 1.4 `run(detector, *source)` —— 推荐驱动

#### 概念

驱动 Detector 的推荐入口。包裹 `detector.detect(*source)`,在产出流上施加**跨事件安全网**:`end_idx` 升序、`event_id` 单 run 唯一、yield 出的对象必须是 `Event`。违规在源头即抛错(见 §1.2.2 / `path2_spec.md` §5.1),而非让脏数据流到下游。

- **非强制**:直接 `MyDetector().detect(df)` 仍合法(心智最简),只是少这层网
- `*source` 变参支撑 L2+ 的 `run(detector, stream, df)` 形态
- **流式不物化**:generator 边跑边查,内存只占去重所需的 `seen_ids`
- 安全网受运行时开关门控;关闭时 `run()` 走 fast-path 零开销直通(生产可关)

#### 用法示例

```python
from path2 import run

# L1:驱动单 Detector
events = list(run(MyL1Detector(), df))
matched = [e for e in events if my_pattern(e)]

# L2+:下层流 + df 作多 source
l2 = list(run(MyL2Detector(), run(MyL1Detector(), df), df))
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 用 `from path2.config import RUNTIME_CHECKS` 缓存开关 | import 期把布尔拷死,`set_runtime_checks()` 热切失效;须 `config.RUNTIME_CHECKS` 属性访问 |
| 期望 `run()` 校验"匹配完整性" | 它只管序 + id 唯一 + 类型;算法完整性是 stdlib/测试守护,不在协议运行时检查范围 |
| 关掉 runtime check 后仍期望抛 NaN/顺序错 | 关闭即零开销直通,所有跨事件检查跳过 |

---

## 2. 关系算子

> 所有关系算子都是**纯函数**,返回 `bool`。配合 `Pattern.all` 用 AND 组合,即可表达任意复杂的事件谓词。

### 2.1 `Before(anchor, predicate, window, stream=None)`

#### 签名

```python
def Before(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
```

#### 概念

判断:**anchor 之前 `window` 个 bar 的窗口内**,某个时刻满足 `predicate`。

#### 窗口边界

`[anchor.start_idx - window, anchor.start_idx)` — 左闭右开,**不含 anchor 自身**。

#### 两种 predicate 形态

| 形态 | predicate 签名 | 触发条件 |
|---|---|---|
| **形态 A — bar 索引** | `(idx: int) -> bool` | 窗口内**任一 bar** 求值 True |
| **形态 B — 事件流** | `(event: Event) -> bool` + `stream` | `stream` 中**任一事件**满足 `anchor.start_idx - window <= event.end_idx < anchor.start_idx` 且 `predicate(event)` |

#### 用法示例

```python
# 形态 A:BO 前 20 bar 内某天收盘 > MA20
Before(bo, predicate=lambda i: df.close[i] > df.ma20[i], window=20)

# 形态 B:BO 前 20 bar 内 vol_stream 里有 ratio >= 2 的事件
Before(bo, predicate=lambda v: v.ratio >= 2.0,
       window=20, stream=vol_stream)

# 用 Pattern.all 组合
pattern = Pattern.all(
    lambda bo: bo.drought >= 30,                                # At-like
    lambda bo: Before(bo, lambda i: df.close[i] > df.ma20[i],   # 历史条件
                      window=20),
)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| `window=0` 期望返回 True | 协议:`window=0` 返回 False(空窗口) |
| 形态 B 忘传 `stream` | predicate 是事件签名时**必须**传 stream |
| 期望窗口包含 anchor 自身 | 不含 — 想包含 anchor 用 `At` |

---

### 2.2 `At(anchor, predicate)`

#### 签名

```python
def At(anchor: Event, predicate: Callable[[Event], bool]) -> bool:
    return predicate(anchor)
```

#### 概念

判断 **anchor 自身**满足 `predicate`。等价于直接 `predicate(anchor)`。

提供 `At` 是为了表达**对称性** — 让 `Before / At / After` 三件套形成完整的时间轴语言。

#### 用法示例

```python
At(bo, lambda e: e.drought >= 30)
# 等价于 bo.drought >= 30

# 与 Before/After 联用
Pattern.all(
    lambda bo: Before(bo, lambda i: stable(df, i), window=20),  # 前置稳定
    lambda bo: At(bo, lambda e: e.drought >= 30),               # 当下高 drought
    lambda bo: After(bo, lambda v: v.ratio >= 2.0,              # 后续放量
                     window=5, stream=vol_stream),
)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 用 `At` 看 bar 索引的条件 | `At` 是 event-on-event;看 bar 直接用 `bo.field` 或外部访问 df |
| 觉得 `At` 比直接调 predicate 更省事 | 不省事,只是表达更对称。可以省略 `At` |

---

### 2.3 `After(anchor, predicate, window, stream=None)`

#### 签名与 `Before` 对称:

```python
def After(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
```

#### 概念

判断:**anchor 之后 `window` 个 bar 的窗口内**,某个时刻满足 `predicate`。

#### 窗口边界

`(anchor.end_idx, anchor.end_idx + window]` — 左开右闭,**不含 anchor 自身**。

#### ⚠ 重要语义

由于 Path 2 的"Row 落地 = 字段完成"约束:**如果 anchor 自身已是 Detector yield 出来的事件,它的 features 已包含 lookforward window 信息**(Detector 等够 K bar 才 yield)。

因此 `After` 通常用在**跨事件流**判断,例如 "BO 之后 5 bar 内 vol 流是否有 spike"。如果"BO 后 5 天放量"是 BO 自身的 feature,应在 BODetector 里算好,而不是在 Pattern 里用 `After`。

#### 用法示例

```python
# BO 之后 5 bar 内 vol_stream 中有放量事件
After(bo, predicate=lambda v: v.ratio >= 2.0,
      window=5, stream=vol_stream)

# 等价于(列表推导)
any(bo.end_idx < v.end_idx <= bo.end_idx + 5 and v.ratio >= 2.0
    for v in vol_stream)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 在 Pattern 里用 `After` 看 anchor 自身的未来 | 应该把该字段塞进 anchor 的 features,让 Detector 等够 |
| 期望窗口包含 anchor.end_idx | 不含 — 严格在 anchor 结束后 |

---

### 2.4 `Over(events, attribute, reduce, op, thr)`

#### 签名

```python
def Over(
    events: Iterable[Event],
    attribute: str,
    reduce: Callable[[Iterable], Any],
    op: str,             # '>=' / '>' / '<=' / '<' / '==' / '!='
    thr: Any,
) -> bool:
```

#### 概念

对容器中每个事件取 `attribute` → 经 `reduce` 聚合 → 与 `thr` 用 `op` 比较。

这是**容器级 reduce 算子** — 处理 `e.children` 或外部事件 list 时的批量统计。

#### 参数说明

| 参数 | 说明 |
|---|---|
| `events` | 任意 `Iterable[Event]`(如 `e.children`、列表推导出的子集) |
| `attribute` | Event 上存在的字段名(字符串) |
| `reduce` | 聚合函数(`sum`、`len`、`max`、`min`、`lambda`) |
| `op` | 比较运算符的字符串形式 |
| `thr` | 阈值 |

#### 用法示例

```python
# 例 1:簇内累计破峰数 >= 5
Over(events=cluster.children,
     attribute='broken_peaks',
     reduce=lambda xs: sum(len(x) for x in xs),
     op='>=', thr=5)

# 例 2:簇内 ratio 平均值 >= 2.5
Over(cluster.children, 'ratio',
     reduce=lambda xs: sum(xs)/len(xs), op='>=', thr=2.5)

# 例 3:簇内最大 drought >= 30
Over(cluster.children, 'drought', reduce=max, op='>=', thr=30)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| `attribute` 在某些 Event 子类上不存在 | 抛 `AttributeError`;若容器内类型异构需先过滤 |
| `reduce` 输出与 `thr` 类型不匹配 | 比较时类型不兼容报错;`reduce` 输出类型用户自己保证 |
| 用 `Over` 表达"至少一个满足" | 应该用 `Any`,语义更清晰 |

---

### 2.5 `Any(events, predicate)`

#### 签名

```python
def Any(events: Iterable[Event], predicate: Callable[[Event], bool]) -> bool:
    return any(predicate(e) for e in events)
```

#### 概念

容器中**至少一个**事件满足 predicate。

`predicate` 默认可写 `lambda e: True`,此时退化为"容器非空"。

#### 用法示例

```python
# 簇内是否有放量 BO
Any(cluster.children, lambda b: b.vol_spike)

# 历史 BO 流里是否有 drought >= 50 的(在某窗口内)
Any([b for b in bo_stream if b.start_idx >= cluster.start_idx - 60],
    lambda b: b.drought >= 50)

# 退化用法:容器是否非空
Any(cluster.children, lambda _: True)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 当 events 是 generator 时多次调用 Any | generator 单次耗尽;先转 list 再多次复用 |
| 需要"全部满足"用 `Any` | 用 `all(...)` 或定义 `All(events, predicate)`(stdlib 待补) |

---

## 3. 组合子

### 3.1 `Pattern.all(*predicates)`

#### 签名

```python
class Pattern:
    @staticmethod
    def all(*predicates: Callable[[Event], bool]) -> Callable[[Event], bool]:
        def combined(event: Event) -> bool:
            return all(p(event) for p in predicates)
        return combined
```

#### 概念

把多个 predicate(每个都是 `Event -> bool`)**AND 起来**,返回一个新的 predicate。

`Pattern.all` 是 Path 2 中**目前唯一**的 Pattern 组合子。它生产的就是一个普通 Python 函数,**可以**:

- 直接调用:`pat(event)` → bool
- 当作 filter:`[e for e in events if pat(e)]`
- 嵌套到更大的 Pattern.all 里

#### 用法示例

```python
# 一个典型 Pattern(对应 tutorial §6 的"7 特征"形态)
seven_features = Pattern.all(
    # 簇前企稳
    lambda c: c.pre_stability >= 0.8,
    # 簇大小
    lambda c: len(c.children) >= 3,
    # 首 BO drought 大
    lambda c: c.children[0].drought >= 30,
    # 累计破峰(Over)
    lambda c: Over(c.children, 'broken_peaks',
                   reduce=lambda xs: sum(len(x) for x in xs),
                   op='>=', thr=5),
    # 容器存在(Any)
    lambda c: Any(c.children, lambda b: b.vol_spike),
    # 末 BO 未超涨
    lambda c: c.children[-1].pre_overshoot <= 0.3,
    # 簇后平台
    lambda c: c.post_platform >= 0.7,
)

# 使用
clusters = list(ClusterDetector().detect(bos, df))
matched = [c for c in clusters if seven_features(c)]
```

#### 嵌套用法

```python
# Pattern.all 自身可以嵌套
chain_pattern = Pattern.all(
    seven_features,                        # 复用上面的
    lambda c: After(c, lambda v: v.ratio >= 3.0,
                    window=10, stream=vol_stream),
)
```

#### 陷阱

| 错误 | 原因 |
|---|---|
| 期望 OR 组合 | 当前只有 `Pattern.all`(AND);OR 自己写 `lambda e: p1(e) or p2(e)` |
| 把"对象方法"误传成 predicate | predicate 接收 `event` 作唯一参数;闭包外部变量(如 `df`、`vol_stream`)通过 lambda 捕获 |
| 顺序敏感 | `Pattern.all` 短路求值(`all()` 的特性) — 但 predicates 之间**无序**,语义上等价 |

---

## 4. API 速查表

### 4.1 关系算子对比

| 算子 | 看哪 | 看几 bar | predicate 接收 | 典型场景 |
|---|---|---|---|---|
| `Before(a, p, w)` | a 之前 | w bar | bar 索引 / 事件 | "BO 之前 20 天稳定" |
| `At(a, p)` | a 自身 | 1(自身) | 事件 | "BO 自身 drought≥30" |
| `After(a, p, w)` | a 之后 | w bar | bar 索引 / 事件 | "BO 之后 5 天 vol spike"(跨流) |
| `Over(es, attr, r, op, thr)` | 容器 | — | — | "簇内累计破峰≥5" |
| `Any(es, p)` | 容器 | — | 事件 | "簇内任一 BO 放量" |

### 4.2 核心类型对比

| 类型 | 是不是类 | 是 frozen 吗 | 主要场景 |
|---|---|---|---|
| `Event` | 抽象基类 | ✅ frozen dataclass | 所有具体事件类的父类 |
| `Detector` | Protocol(鸭子类型) | — | 用户自写的 detector class |
| `TemporalEdge` | frozen dataclass | ✅ | 声明事件间时序边(被组合 Detector 消费) |

### 4.3 字段约定对比

| 字段 | 必有 | 类型 | 约束 |
|---|---|---|---|
| `event_id` | ✅ | str | 同 Detector 单 run 内唯一 |
| `start_idx` / `end_idx` | ✅ | int | start ≤ end |
| `children` | 可选(聚合) | List[Event] | 按 start_idx 升序 |
| `parent` | 可选(派生) | Event | parent.end_idx ≤ self.start_idx |

### 4.4 常见组合骨架

```python
# 骨架 1:单事件流 + Pattern 筛选
events = list(MyDetector().detect(df))
matched = [e for e in events if my_pattern(e)]

# 骨架 2:多层 pipeline(L1 → L2 → L3)
l1 = list(L1Detector().detect(df))
l2 = list(L2Detector().detect(l1, df))
l3 = list(L3Detector().detect(l2, df))

# 骨架 3:多流 + 关系算子 + Pattern.all
bos = list(BODetector().detect(df))
vols = list(VolSpikeDetector().detect(df))

pat = Pattern.all(
    lambda bo: At(bo, lambda e: e.drought >= 30),
    lambda bo: Before(bo, lambda i: stable(df, i), window=20),
    lambda bo: After(bo, lambda v: v.ratio >= 2.0,
                     window=5, stream=vols),
)
matched = [bo for bo in bos if pat(bo)]
```

---

## 5. 与 spec 的对应

| 本手册章节 | spec 章节 |
|---|---|
| §1.1 Event | spec §1.1 |
| §1.2 Detector | spec §1.2 |
| §1.3 TemporalEdge | spec §1.3 |
| §2.1–2.5 关系算子 | spec §2.1–2.5 |
| §3.1 Pattern.all | spec §2.6 |
| Schema 不变式(本手册未单列) | spec §3 |

**如有冲突,以 spec 为准**。本手册是 spec 的"用法面"展开,不是 spec 的替代品。

---

**手册结束。**
