# Path 2 框架规范(Spec)

> **版本**:v0.1(2026-05-12);**§9 附 v0.2 反馈**(2026-05-16,协议层 plan 阶段实现回写)
> **状态**:协议层已实现并通过两阶段 review;v0.1 正文保持原样,实测发现的偏差/补强集中记于 **§9**(read v0.1 时凡涉及 §1.3 / §5.1 请并看 §9)
> **目的**:精确定义 Path 2 的协议表面 — Event、Detector、关系算子、TemporalEdge、schema 不变式。开发者**只读本文档即可实现 Path 2**,不需要回头看研究 / 教程类文档。
>
> **范围声明**:Path 2 是独立的事件表达框架。本规范**不涉及** mining / TPE / 因子框架 / FactorInfo / FeatureCalculator 等概念 — 那些属于既有因子框架的下游优化措施。Path 2 的下游流水线(若需要)另作规范。

---

## 0. 范围

### 0.1 本规范涵盖

- `Event` 协议(基类、必有字段、子类化规则、不变性)
- `Detector` 协议(接口、产出契约、状态管理)
- 5 个关系算子(`Before` / `At` / `After` / `Over` / `Any`)
- 1 个组合子(`Pattern.all`)
- `TemporalEdge` 数据类
- "Row 落地 = 字段完成"不变式的精确含义
- 层级命名约定(`L1/L2/L3`)的语义

### 0.2 本规范不涵盖(留给 plan 决定)

- stdlib 内容(常用 Event 类、Detector 模板、Pattern 组合子集合)
- DSL 层(可选语法糖,叠在协议之上)
- 持久化 / 序列化格式
- 并发模型(默认单线程,不规定)
- 与现有 `BreakoutStrategy/` 代码的集成方式
- 性能调优(具体实现可选用单调双指针等优化)

---

## 1. 核心类型与协议

### 1.1 `Event` 协议

```python
from abc import ABC
from dataclasses import dataclass
from typing import Mapping, Optional, List

@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。"""

    event_id: str           # 持久身份,在同一 Detector 单次 run 内必须唯一
    start_idx: int          # 事件起始 bar(含)
    end_idx: int            # 事件结束 bar(含)
```

#### 1.1.1 必有字段

| 字段 | 类型 | 语义 |
|---|---|---|
| `event_id` | `str` | 持久标识。**同一 Detector 单次 run 内唯一**;跨 Detector / 跨 run 不要求唯一。**推荐**格式 `<kind>_<idx>` 或 `<kind>_<start_idx>_<end_idx>`,但格式不在协议层面强制 |
| `start_idx` | `int` | 事件起始 bar 序号(含)。单 bar 事件 `start_idx == end_idx` |
| `end_idx` | `int` | 事件结束 bar 序号(含)。**要求 `start_idx <= end_idx`** |

#### 1.1.2 不变性

- **Event 必须是 `@dataclass(frozen=True)`**。一旦被 Detector yield,字段不可再改
- 这是 "Row 落地 = 字段完成" 不变式的实现保证(详见 §3.1)
- **frozen 一致性由 Python `@dataclass` 在装饰期原生强制**:非 frozen 子类继承 frozen `Event` 在类定义时即抛 `TypeError: cannot inherit non-frozen dataclass from a frozen one`,比任何协议层自检更早更强;故协议层**不写** frozen 自检(原 v0.1 设想的 `__init_subclass__`/`__post_init__` 自检为不可达死代码)。动态 `setattr` 由 frozen dataclass 原生抛 `FrozenInstanceError`

#### 1.1.3 子类化规则

- 必须继承 `Event` 并保持 `@dataclass(frozen=True)`
- 子类自由添加业务字段(`drought: float`、`vol_spike: bool`、`children: List[Event]` 等)
- 子类**不应**重写 `event_id` / `start_idx` / `end_idx` 字段
- 子类**不应**添加 Python `__init__` 自定义逻辑(`@dataclass(frozen=True)` 已生成);如需派生字段用 `@property`

#### 1.1.4 `features` 派生字典(可选属性)

```python
@property
def features(self) -> Mapping[str, float]:
    """该事件的所有数值字段的 dict 视图。
    实现可选:默认行为是返回所有 float / int 类型字段。
    用途:用于结构化引用(`event.features['drought']`)而不是属性访问;在序列化、UI 显示、调试时统一接口。"""
```

- `features` 是 Event 子类的**可选**属性
- 实现 base class 可提供默认 `features` 自动从 dataclass fields 提取所有 numeric 字段
- **不是协议强制要求** — 子类直接用属性访问(`event.drought`)也合法

#### 1.1.5 容器与引用字段

| 字段名 | 类型 | 出现场景 | 语义 |
|---|---|---|---|
| `children` | `List[Event]` | 聚合事件(L2 / L3 等)用 | 持有下层组成员,**必须按 `start_idx` 升序**(详见 §3.3) |
| `parent` | `Event` | 派生事件(L3 派生自 L2 / L1 等)用 | 反向引用上层事件 |

- 这两个字段名是**协议约定**(其他名字也行,但用这俩名字更利于跨实现复用 stdlib)
- 不是协议强制 — 子类可不使用,也可同时持有 `children` 和 `parent`(混合聚合 + 派生)

---

### 1.2 `Detector` 协议

```python
from typing import Protocol, Iterable, Iterator, Any

class Detector(Protocol):
    """从下层数据 / 事件流产生上层 Event 的生产者。"""

    def detect(self, source: Any) -> Iterator[Event]:
        """消费 source(df 或 Iterable[Event]),按时序 yield Event。
        每个 yield 出来的 Event 的所有字段都必须 ready(无 NaN / partial)。"""
        ...
```

#### 1.2.1 接口约定

- 单个方法 `detect(self, source) -> Iterator[Event]`
- `source` 类型:
  - **L1 Detector**:接受类 DataFrame 对象(`df`),通常含 `close / high / low / vol / ma20 / ...` 字段
  - **L2+ Detector**:接受 `Iterable[Event]`(下层事件流)。可附加 `df` 作第二参数访问原始数据
- 返回 `Iterator[Event]`(generator 函数即可)

#### 1.2.2 yield 时序约束

- **必须按 `end_idx` 升序 yield**(allow `end_idx` 相同时的任意顺序)
- 不允许 yield 一个 `end_idx` 已经小于上次 yield 的 Event 的事件
- 这保证下游消费时可以做"流式"处理而不必先排序

#### 1.2.3 完整性约束 — Detector 的核心契约

> **Detector 在 yield 一个 Event 之前,必须确保该 Event 的所有 features 字段已计算完毕**。

- 如果某字段需要"看后 K 个 bar"才能算出(例如 post-window 平台度),Detector 必须**等 K bar 观察完才 yield**
- 不允许 yield 出 features 字段为 `None` / `NaN` / sentinel 的 Event
- 不允许"先 yield 一个 partial Event,稍后再补字段"

#### 1.2.4 状态管理

- Detector **是有状态的**(可以维护 FSM、滑窗、buffer)
- **单次 `detect()` 调用内的状态独立**:同一个 Detector 实例对不同 source 调用 `detect()` 时,状态不应跨调用泄漏
- 实现建议:状态全部声明在 `detect()` 函数内部(局部变量),而非 `self.*`,以避免跨调用污染

#### 1.2.5 `run()` —— 推荐驱动

- `run(detector, *source)` 是驱动 Detector 的**推荐入口**:它包裹 `detector.detect(*source)`,在流上施加 §1.2.2 / §5.1 的**跨事件安全网**(`end_idx` 升序、`event_id` 单 run 唯一、yield 出的对象必须是 `Event`)
- **非强制**:直接 `MyDetector().detect(df)` 仍合法(保留极简心智模型),只是少了跨事件检查
- `*source` 变参支撑 L2+ 的 `detect(stream, df)` 形态;**流式不物化**(generator 边跑边查,内存只占去重所需的 `seen_ids`)
- 安全网整体受运行时开关门控(见 §5.1 "若 runtime check 开启";关闭时 `run()` 走 fast-path 零开销直通)
- §5.1 表中标注抛错位置为 "Detector wrapper" 的违规,即由 `run()` 这层检出

---

### 1.3 `TemporalEdge`

```python
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class TemporalEdge:
    """声明两个**端点标签**之间的时间关系约束(声明性 datatype,本身不计算)。"""

    earlier: str            # 较早端点的声明期标签(非 event_id)
    later: str              # 较晚端点的声明期标签(非 event_id)
    min_gap: int = 0        # 最小间隔(含),单位:bar
    max_gap: float = math.inf  # 最大间隔(含),单位:bar;math.inf 表示无上限
```

> **`earlier` / `later` 是声明期端点标签,不是 `event_id`。** 一条 `TemporalEdge` 声明的是"标签 X 的某事件"与"标签 Y 的某事件"之间的约束;消费它的 stdlib PatternDetector(`Chain`/`Dag`/`Kof`/`Neg`)在 run 时把每个标签解析到一条事件流,再据 gap 公式驱动匹配。协议层只定该 schema 与 gap 公式,不绑定标签如何解析(见 §7.1)。

#### 1.3.1 gap 的精确定义

```
gap = later.start_idx - earlier.end_idx
```

| 约束 | 含义 |
|---|---|
| `min_gap = 0` | later 可与 earlier 同 bar 或紧接其后(`later.start_idx >= earlier.end_idx`) |
| `min_gap = 1` | later 必须严格在 earlier 之后(中间至少 1 个 bar 间隔) |
| `max_gap = N` | later 必须在 earlier 之后不超过 N 个 bar(`later.start_idx - earlier.end_idx <= N`) |
| `max_gap = math.inf` | 无上限(等价于"earlier 一旦发生,永远是有效前置") |

#### 1.3.2 不变性

- `TemporalEdge` 必须 `@dataclass(frozen=True)`,可作为字典 key 使用
- 多个 Detector 之间可共享同一 `TemporalEdge` 实例

---

## 2. 关系算子(形式定义)

所有关系算子都是**纯函数**,无副作用,返回 `bool` 或 `Callable[..., bool]`。

### 2.1 `Before(anchor, predicate, window)`

```python
def Before(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
```

**语义**:anchor 之前 `window` 个 bar 内,某个时刻满足 `predicate`。

- **两种 predicate 形态**:
  - `predicate(idx: int) -> bool`:对 bar 索引求值(需在 Detector / Pattern 上下文有 `df` 可访问)
  - `predicate(event: Event) -> bool`:配合 `stream` 参数,对事件流求值(返回 True iff 存在 event in stream 满足 anchor.start_idx - window <= event.end_idx < anchor.start_idx 且 predicate(event))
- **窗口边界**:`[anchor.start_idx - window, anchor.start_idx)`(左闭右开,不含 anchor 自身)
- **window=0**:返回 False(空窗口)

### 2.2 `At(anchor, predicate)`

```python
def At(anchor: Event, predicate: Callable[[Event], bool]) -> bool:
    return predicate(anchor)
```

**语义**:anchor 自身满足 predicate。等价于 `predicate(anchor)`,提供 `At` 是为表达对称(Before / At / After 三件套)。

### 2.3 `After(anchor, predicate, window, stream=None)`

**语义**:anchor 之后 `window` 个 bar 内,某个时刻满足 `predicate`。

- 与 `Before` 对称
- 窗口边界:`(anchor.end_idx, anchor.end_idx + window]`(左开右闭,不含 anchor 自身)
- **重要**:由于 Path 2 的"Row 落地 = 字段完成"约束,如果 anchor 自身已经是 Detector yield 出来的事件,**它的 features 已包含 lookforward window 信息**。`After` 算子通常用在**跨事件流**判断,例如 "BO 之后 5 bar 内 vol 流是否有 spike"

### 2.4 `Over(events, attribute, reduce, op, thr)`

```python
def Over(
    events: Iterable[Event],
    attribute: str,
    reduce: Callable[[Iterable], Any],
    op: str,           # '>=' / '>' / '<=' / '<' / '==' / '!='
    thr: Any,
) -> bool:
```

**语义**:对 `events` 中每个 e 取 `getattr(e, attribute)`,经 `reduce` 聚合,与 `thr` 用 `op` 比较。

- `events` 可以是 list、generator、`e.children` 等任何 Iterable
- `attribute` 必须是 Event 上存在的字段名
- 若 attribute 是 list / sequence(如 `broken_peaks`),reduce 函数应处理:常用 `reduce=lambda xs: sum(len(x) for x in xs)` 表达"累计长度"

### 2.5 `Any(events, predicate)`

```python
def Any(events: Iterable[Event], predicate: Callable[[Event], bool]) -> bool:
    return any(predicate(e) for e in events)
```

**语义**:容器中至少一个事件满足 predicate。`predicate` 默认可为 `lambda e: True`(只要存在事件)。

### 2.6 `Pattern.all(*predicates)`

```python
class Pattern:
    @staticmethod
    def all(*predicates: Callable[[Event], bool]) -> Callable[[Event], bool]:
        def combined(event: Event) -> bool:
            return all(p(event) for p in predicates)
        return combined
```

**语义**:返回一个组合 predicate,候选事件需满足全部 predicates(AND)。

**用法**:作为 Pattern 顶层组合 — `pattern = Pattern.all(p1, p2, p3); pattern(candidate)` 返回 bool。

---

## 3. Schema 不变式

### 3.1 "Row 落地 = 字段完成"不变式

**精确含义**:

> 任何被 Detector yield 出来的 Event,**其每个 dataclass 字段都已 ready** — 不存在 `None`(对必有字段)、`NaN`(对 float 字段)、或表示"尚未确定"的 sentinel 值。

**保证机制**(协议层强制):
- Event 是 `@dataclass(frozen=True)`,字段一旦构造不能再改 → 不存在"先 yield 后补"
- Detector 内部状态机必须**等所有 post-window 观察完才 yield** → 保证字段在构造时就有值

**违反检测**(实现建议):
- base class `Event.__post_init__` 可加 runtime check:扫所有 float 字段,有 NaN 抛 `ValueError`
- 必有字段(`event_id` 等)若值为 `None` 抛 `TypeError`
- 此检查是**调试期可选**,生产可关闭

### 3.2 时间区间约束

| 不变式 | 适用对象 |
|---|---|
| `start_idx <= end_idx` | 任意 Event |
| `start_idx >= 0` | 任意 Event |
| `end_idx < len(df)` | 任意 Event(隐式,实现层校验) |

### 3.3 `children` 时序约束

若 Event 有 `children: List[Event]` 字段,则:

- `children` 必须**按 `start_idx` 升序排列**
- 等价:`children[0]` 是时间最早的成员,`children[-1]` 是时间最晚的
- `children` 中每个成员的 `[start_idx, end_idx]` 区间应落在父事件的 `[start_idx, end_idx]` 内(实现层校验,可选)

### 3.4 `parent` 时序约束

若 Event 有 `parent: Event` 字段,则:

- `parent.end_idx <= self.start_idx`(parent 必须先于当前事件完成)
- 等价于:派生事件不能"先于"它派生自的事件存在

---

## 4. 层级命名约定

| 前缀 | 含义 | 是否强制 |
|---|---|---|
| `L1` | 原子事件 — 由原始数据(`df`)直接产生 | **可选**(命名提示) |
| `L2` | 聚合事件 — 由若干 L1 通过 `children` 组合 | **可选** |
| `L3` | 派生事件 — 由 L2 / L1 通过 `parent` 派生 | **可选** |
| `L4+` | 任意更高层 | **可选** |

**关键**:层数无上限。`children: List[Event]` 与 `parent: Event` 都是泛 Event 类型,不强制类型匹配 — 可以"L2 的 L2 的 L2"(无限递归)、可以"L3 的 parent 是 L1"(跨层引用)。

`L0` **不存在** — 原始 K 线数据不是 Event。

---

## 5. 错误处理

### 5.1 必须报错的违规

| 违规 | 错误类型 | 抛错位置 |
|---|---|---|
| Event 子类没用 `@dataclass(frozen=True)` | `TypeError` | Python `@dataclass` 装饰期原生强制(见 §1.1.2) |
| `start_idx` / `end_idx` 非 `int` | `TypeError` | `Event.__post_init__` |
| `start_idx` / `end_idx` 为 `bool`(`bool ⊂ int` 仍显式拒绝)| `TypeError` | `Event.__post_init__` |
| `start_idx > end_idx` | `ValueError` | `Event.__post_init__` |
| Detector yield 出 Event 的某 float 字段是 NaN(若 runtime check 开启)| `ValueError` | `Event.__post_init__` |
| Detector yield 顺序不符 `end_idx` 升序(若 runtime check 开启)| `ValueError` | `run()`(Detector wrapper)|
| 同一 Detector 单次 run 内 `event_id` 重复(若 runtime check 开启)| `ValueError` | `run()`(Detector wrapper)|
| `run()` yield 出非 `Event` 对象(若 runtime check 开启)| `TypeError` | `run()`(Detector wrapper)|
| `TemporalEdge` `min_gap < 0` 或 `min_gap > max_gap` | `ValueError` | `TemporalEdge.__post_init__` |

### 5.2 不必报错(行为未定义)

- 跨 Detector / 跨 run 的 event_id 冲突
- `children` 顺序错乱(规范说"必须升序",但 runtime check 是可选)
- `parent.end_idx > self.start_idx`(同上)

---

## 6. 实现层非协议规定(供参考,不强制)

以下属于实现细节,不在协议层面规定:

- Event 子类的字段命名风格(`snake_case` vs `camelCase`)
- Detector 内部状态机的具体写法(FSM / 单调双指针 / buffer)
- `features` 属性的具体实现(自动提取 vs 显式定义)
- 性能优化(单调双指针 vs 朴素 O(n²))
- 数据源访问(Detector 怎么访问 `df.close[i]`)

---

## 7. Open Questions(留给 plan 阶段决定)

### 7.1 已确定项(不再 open)

- **消费 `TemporalEdge` 的标准 PatternDetector 系列**(`ChainPatternDetector` / `DagPatternDetector` / `KofPatternDetector` / `NegPatternDetector`)**必须**由 stdlib 沉淀,带**最优实现**,**不允许用户自写**(2026-05-15 用户明确)
  - 设计原则:协议层只定 schema(`TemporalEdge` + gap 公式),不绑实现;stdlib 提供带最优实现的标准消费者
  - 用户写**声明**(`edges`),stdlib 跑**执行**(策略选择 + 最优实现)
  - 详细清单与命名见 `path2_qa.md` Q1 备忘 B

### 7.2 待 plan 阶段决定

| 问题 | 影响 |
|---|---|
| stdlib 其余项 — 常用 Event 类 / Detector 模板 — 的具体清单与签名? | 决定开发者上手友好度,初步清单见 `path2_qa.md` Q1 备忘 B |
| DSL 层是否要做?做的话怎么 desugar 回协议? | 决定简单形态的紧凑度,见 `path2_qa.md` Q1 备忘 C |
| Detector 怎么访问 `df`?提供标准 `DataSource` 协议还是让用户自己管? | 决定 stdlib 设计 |
| `features` 属性默认实现是否要在 base class 提供? | 决定 stdlib 复杂度 |
| runtime check(NaN 防御、event_id 唯一性等)在生产环境是否默认关闭? | 决定 production overhead |
| 与现有 `BreakoutStrategy/` 代码的边界?(`Peak` / `Breakout` 等是否直接用现有定义?)| 决定集成范围,见 plan |

---

## 8. 版本与变更

- **v0.1**(2026-05-12):初稿。基于 `path2_advantages.md` / `path2_vs_condition_ind_coverage.md` / `framework_expressiveness_shootout.md` / `path2_tutorial.md` 的累计共识固化
- **v0.2**(2026-05-17):正式修订。协议层 + stdlib PatternDetector(`Chain`/`Dag`/`Kof`/`Neg`)两轮实现反馈**已并入正文**;原 §9 反馈表转为下方变更摘要
- 后续变更通过 plan 阶段的实现反馈推动 v0.2+

---

## 9. v0.2 变更摘要(已并入正文)

> v0.1→v0.2 的实测反馈已写入正文对应小节;本节仅留变更索引与实现产物指针(不再保留 "v0.1 原文 vs 实测" 历史对照表——正文即权威)。

- **偏差①(frozen)** → §1.1.2 / §5.1:frozen 由 Python `@dataclass` 装饰期原生强制,协议层不写自检(原 `__init_subclass__` 自检为不可达死代码)
- **偏差②(max_gap 类型)** → §1.3:`max_gap: float = math.inf`
- **补强卫语** → §5.1:`start_idx`/`end_idx` 非 int → `TypeError`;`run()` yield 非 `Event` → `TypeError`;`TemporalEdge` `min_gap<0`/`min_gap>max_gap` → `ValueError`
- **bool-as-idx(已决议=显式拒绝)** → §1.1.2 / §5.1:`type(idx) is bool → TypeError`(`bool ⊂ int`,语义错误;与 `features` 排除 bool 同源)。回归测试 `tests/path2/test_event.py`
- **`earlier`/`later` 语义澄清**(#3 stdlib 实测)→ §1.3:二者是声明期端点标签,非 `event_id`;由消费的 stdlib PatternDetector 解析到事件流
- **`run()` 推荐驱动** → 新增 §1.2.5

### 9.1 实现产物指针

- **协议层**:design `docs/superpowers/specs/2026-05-16-path2-protocol-layer-design.md`;plan `docs/superpowers/plans/2026-05-16-path2-protocol-layer.md`;代码 `path2/`(`config`/`core`/`operators`/`pattern`/`runner`)
- **dogfood 验证**:`docs/research/path2_dogfood_report.md`
- **stdlib PatternDetector(#3)**:design `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`;plan `docs/superpowers/plans/2026-05-16-path2-stdlib-pattern-detectors.md`;**算法权威 `docs/research/path2_algo_core_redesign.md`**(LEF-DFS §1-9 / Kof §10 / Neg §11);代码 `path2/stdlib/`

---

**规范结束。**
