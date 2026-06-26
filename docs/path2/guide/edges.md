# 关系边（Edge）指南

## 这篇在讲什么

在 path2 里，你描述一段走势的方式，是先定义若干个"事件"（比如"一段下跌""一串突破""一次回踩"），再说清楚这些事件之间该有怎样的**关系**。

> 💡 一句话：**边（edge）就是"两个事件之间的一条规则"**。
>
> 比如"突破必须发生在下跌结束之后""回踩必须紧贴着突破的末尾"——这些"必须……"就是一条条边。

你可以把整段走势的声明想象成一张图：

- **事件**是图上的**节点**；
- **边**是连接节点的**箭头**，箭头上写着"它俩得满足什么关系"。

这张图就是 path2 说的 **DAG**（有向无环图）。你只要把节点和边声明好，引擎 `analyze(spec, df, params)` 就会自动去数据里找出所有同时满足这些规则的组合——**你不用手写任何匹配/搜索逻辑**。

这篇文档专门讲"边"：有哪几种、各自表达什么关系、怎么写、容易踩什么坑。读完你应该能看着一段走势的自然语言描述，把它翻译成几条边。

---

## 先建立直觉：一条边同时干两件事

每条边其实**同时**承担两个互不冲突的职责。理解这一点，后面就顺了。

1. **它定义了一个方向**（结构 / 拓扑职责）
   边总是写成 `src → dst`（源 → 目标）。这个方向决定了引擎"先找谁、再找谁"：引擎会**先确定 `src` 事件，再以它为锚点去缩小 `dst` 的搜索范围**。在可视化面板里，箭头也是按这个方向画的。

   > 💡 小贴士：方向不是随便定的。一般"先发生的 / 更大的 / 作为参照的"那个事件当 `src`，"后发生的 / 被约束的"那个当 `dst`。

2. **它定义了一条规则**（语义 / 关系职责）
   给定一对具体的候选事件（一个 `src`、一个 `dst`），这条边能判断"它俩的关系成不成立"。这个判断由每条边的 `satisfies` 方法完成。

引擎本身**不认识**任何具体边类型——它只通过统一的基类接口去调用每条边。这带来一个很实用的结论：**当你需要一种全新的关系时，只要加一个新的边子类即可，引擎核心一行都不用改。**

---

## 所有边共享的基类：DependencyEdge

在看具体的六种边之前，先认识它们共同的"父亲"。所有边都继承自 `DependencyEdge`：

```python
@dataclass(frozen=True)
class DependencyEdge(ABC):
    src: str   # 源节点 node_id
    dst: str   # 目标节点 node_id
```

两个最基本的字段就是 `src` 和 `dst`，都是节点 id（字符串），平时这就够用了。

> 💡 进阶（嵌套事件场景才会用到，初学可跳过）：有些事件内部还**装着更小的子事件**（比如一串突破聚合成的 `burst`，内部装着一个个 `bo`，详见后文）。这种时候，边的端点除了写节点 id 字符串，还可以写 `Child(node, key)`，把边连到"某个父事件内部的具名子事件"上——例如 `Child("burst", "first_bo")` 表示连到 burst 这串突破的**第一个 bo**。引擎会在内部把它归一化成一个隐藏的 `src_selector`/`dst_selector`（它们不参与边的身份判定）。当前示例 app 没用到这个能力（它的边都直接连整个事件），所以你大可先忽略它的存在。

> 💡 `frozen=True` 意思是这个对象一旦造出来就**不可改**。好处是它能安全地当字典的 key、放进 set，不用担心被偷偷改掉。

引擎只通过下面三个方法和每条边打交道。你**现在只需要记住第一个**，后两个是给引擎做性能优化用的，初学时可以先跳过（本文最后有专门一节展开）：

| 方法 | 一句话说明 |
|---|---|
| `satisfies(e_src, e_dst) -> bool` | **核心**：这一对具体事件的关系成不成立？ |
| `feasible_window(e_src) -> (lo, hi)` | 给引擎的剪枝提示：在 `src` 已知时，`dst` 的起点大致能落在哪个区间，好让引擎少搜一点 |
| `signature_fields() -> tuple[str, ...]` | 如实申报：上面两个方法到底用到了 `src` 的哪些字段 |

基类对后两个方法给了"什么都不做"的默认值：`feasible_window` 默认返回 `(-inf, +inf)`（不剪枝），`signature_fields` 默认返回空元组。子类按需覆盖。

> 你现在应该理解了：**边 = `src→dst` 方向 + 一条 `satisfies` 规则。** 接下来逐个看六种现成的边。

---

## 六种现成的边

下面六种边覆盖了绝大多数常见关系。每一节都先讲"什么场景下用它"，再讲"怎么写"，最后提醒坑。

### 1. TemporalEdge —— 时序边（"B 在 A 之后"）

**什么时候用它**：当你想说"事件 B 必须发生在事件 A 结束之后"，并且想限定"隔多远"。这是最常用的一种边。

**它在判断什么**：B 的起点离 A 的终点有多远，这个"距离"叫 `gap`：

```
gap = e_dst.start_idx − e_src.end_idx     要求落在  [min_gap, max_gap] 之间
```

把它想成"A 结束后，给 B 划一个允许出场的时间窗口"。

```python
@dataclass(frozen=True)
class TemporalEdge(DependencyEdge):
    min_gap: int = 0
    max_gap: float = math.inf
    strict: bool = field(default=False, kw_only=True)
```

**怎么调这几个参数**

| 参数 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `min_gap` | `int` | `0` | gap 的下界（含）。`0` 表示 B 可以紧贴着 A 结束就开始 |
| `max_gap` | `float` | `math.inf` | gap 的上界（含）。填一个有限值就能限制"最多隔多远"（即回看窗口） |
| `strict` | `bool` | `False` | **只能用关键字传**。`True` 启用 next 语义（中间不许夹同类 dst），引擎在 Phase 2 实现 |

**先从几个例子感受一下**：

```python
# B 在 A 结束后的任意时刻都行（不限距离）—— 全用默认
TemporalEdge("a", "b")

# B 必须紧接在 A 之后（恰好下一根 bar）
TemporalEdge("a", "b", min_gap=1, max_gap=1)

# B 必须在 A 结束后 120 根 bar 以内出现
TemporalEdge("a", "b", min_gap=1, max_gap=120)
```

> ⚠️ 常见坑一：**`strict` 必须用关键字传**。它被刻意设成 keyword-only，就是为了防止你把它和前面的 `min_gap`/`max_gap` 位置参数顺序搞错。
>
> ```python
> TemporalEdge("a", "b", 1, 100, True)                      # ❌ TypeError
> TemporalEdge("a", "b", min_gap=1, max_gap=100, strict=True)  # ✅
> ```

> ⚠️ 常见坑二：**gap 区间不能乱填**。构造时 `__post_init__` 会校验 `min_gap >= 0` 且 `min_gap <= max_gap`，违反就抛 `ValueError`。
>
> ```python
> TemporalEdge("a", "b", min_gap=-1)             # ❌ ValueError
> TemporalEdge("a", "b", min_gap=10, max_gap=5)  # ❌ ValueError
> ```

（给引擎看的细节：`feasible_window` 返回 `[e_src.end_idx + min_gap, e_src.end_idx + max_gap]`，`signature_fields` 是 `('end_idx',)`。这些你写 app 时用不到，了解即可。）

---

### 2. ContainmentEdge —— 包含边（"大区间套小区间"）

**什么时候用它**：当你想说"小事件必须发生在某个大区间里头"。典型场景是"突破必须落在某一段横盘区间之内"。

**它在判断什么**：`src` 这段区间，把 `dst` 这段区间整个**包住**：

```
e_src.start_idx <= e_dst.start_idx   AND   e_dst.end_idx <= e_src.end_idx
```

注意这里用的是 `<=`，所以**端点贴边也算包含**——`dst` 跟 `src` 共用起点或共用终点时，仍然满足。

```python
@dataclass(frozen=True)
class ContainmentEdge(DependencyEdge):
    src: str   # 外层（更大）区间
    dst: str   # 内层（被包含）区间
```

没有额外参数，只有 `src` / `dst`。

```python
# 小事件 inner 必须整段落在大区间 outer 之内（outer 是大区间）
ContainmentEdge("outer", "inner")
```

> 💡 如果你只想约束小事件的**起点**落进大区间、不在乎它的终点是否也在里头，那要用的是下一节的 `StartContainmentEdge`，别用这里的整体包含。

> ⚠️ 常见坑：**方向规定是"大 → 小"**，即 `src` 是外层大区间，`dst` 是被包住的小区间。如果你想表达"A 被 B 包住"，要写成 `ContainmentEdge(src="b", dst="a")`。写反了不会报错，但语义就反了，结果会悄悄出错。

（给引擎看的细节：`feasible_window` 返回 `[e_src.start_idx, e_src.end_idx]`，`signature_fields` 是 `('start_idx', 'end_idx')`。）

---

### 3. StartContainmentEdge —— 起点包含边（"只要起点落进来就行"）

**什么时候用它**：当你只关心"**小事件的起点**落在大区间里"，而**不在乎小事件的终点是不是也在里头**。

典型场景：一段横盘区间里冒出一串密集突破。你想要求"这串突破是从横盘段**内部**开始的"，但这串突破完全可能一路冲出横盘段的尾部——这种"头在里、尾可以在外"的关系，`ContainmentEdge`（要求整体被包住）就太严了，正是 `StartContainmentEdge` 的用武之地。

**它在判断什么**：`dst` 的起点落在 `src` 区间内，**终点不管**：

```
e_src.start_idx <= e_dst.start_idx <= e_src.end_idx
```

```python
@dataclass(frozen=True)
class StartContainmentEdge(DependencyEdge):
    src: str   # 外层区间
    dst: str   # 起点要落进 src 的事件
```

没有额外参数。

```python
# 横盘段 side 必须包住突破爆发 burst 的起点（burst 的尾巴可以冲出 side）
StartContainmentEdge("side", "burst")
```

**它和 ContainmentEdge 的区别**，就差最后那一条：

| | 约束 `dst.start` 落进来 | 还约束 `dst.end` 落进来 |
|---|---|---|
| `ContainmentEdge`（整体包含） | ✅ `src.start <= dst.start` | ✅ `dst.end <= src.end` |
| `StartContainmentEdge`（只管起点） | ✅ `src.start <= dst.start <= src.end` | ❌ 不约束 |

> 💡 一句话记法：`ContainmentEdge` 要求"小事件整段都在里面"，`StartContainmentEdge` 只要求"小事件**从里面出发**"。

（给引擎看的细节：`feasible_window` 返回 `[e_src.start_idx, e_src.end_idx]`，`signature_fields` 是 `('start_idx', 'end_idx')`。这个窗口只约束 `dst.start`、不依赖 `dst.end`，对 `dst.start` 是充要的，不会漏匹配。）

---

### 4. OverlapEdge —— 部分交叠边（"两段错位叠在一起"）

**什么时候用它**：当两段区间**有重叠、但又各有各的起点和终点**，谁也不包谁。比如 A 的后半段和 B 的前半段叠在一起。

**它在判断什么**：`dst` 从 `src` 内部某处开始，一直延伸到 `src` 结束之后——也就是 `src` 的"后端"被 `dst` 压住了：

```
e_src.start_idx < e_dst.start_idx < e_src.end_idx   AND   e_src.end_idx < e_dst.end_idx
```

> ⚠️ 注意：这里三个不等号**全是严格小于（`<`）**，所以**端点重合就不算交叠**。

```python
@dataclass(frozen=True)
class OverlapEdge(DependencyEdge):
    src: str   # 前侧区间（后端被叠压）
    dst: str   # 后侧区间（从 src 内部起始）
```

没有额外参数。

```python
# A 的后端被 B 叠压
OverlapEdge("a", "b")

# 想表达反过来（B 的后端被 A 叠压）？把两个参数对调即可，不需要另一种边
OverlapEdge("b", "a")
```

> 💡 小贴士：交叠是有方向的，但"镜像方向"不用专门发明新边——直接把 `src`/`dst` 对调读就行。

> ⚠️ 常见坑：**端点贴边不满足 OverlapEdge**。如果 `dst.start_idx` 恰好等于 `src.start_idx` 或 `src.end_idx`，`satisfies` 会返回 `False`。需要"贴边也算"的关系，请改用 `ContainmentEdge`（含端点）或 `EqualsEdge`（完全重合）。

（给引擎看的细节：`feasible_window` 返回 `[e_src.start_idx + 1, e_src.end_idx - 1]`，`signature_fields` 是 `('start_idx', 'end_idx')`。这个窗口对 `dst.start` 是双侧充要的，已通过大量 fuzz 验证。）

---

### 5. EqualsEdge —— 同段边（"两个事件占同一段"）

**什么时候用它**：当两个**不同类型**的事件，其实落在**完全相同的一段区间**上，你想对同一段同时施加两套约束。比如同一段区间上既要它是"某种形态"，又要它满足"某个数值条件"。

**它在判断什么**：`src` 和 `dst` 的起点、终点完全一致：

```
e_dst.start_idx == e_src.start_idx   AND   e_dst.end_idx == e_src.end_idx
```

```python
@dataclass(frozen=True)
class EqualsEdge(DependencyEdge):
    src: str
    dst: str
```

没有额外参数。

```python
# 事件 X 和事件 Y 必须覆盖完全相同的区间
EqualsEdge("x", "y")
```

> ⚠️ 进阶坑（app 开发者一般不用手动处理，但要知道有这回事）：
>
> `EqualsEdge` 的 `feasible_window` 返回的是一个**点区间** `(e_src.start_idx, e_src.start_idx)`——它把 `dst.start` **死死钉**在 `src.start` 上，而**不是**一个"可以再放宽的下界"。
>
> 这跟引擎一项叫 C1 的"等-end 塌缩"优化会打架：如果在 `EqualsEdge` 的 `src` 节点上还开着 C1，就会漏匹配。引擎会自动识别需要关掉 C1 的节点并替你处理掉——`EqualsEdge.src` 就是其中一种情形（嵌套子事件作边端点等场景也会触发，引擎一并自动处理）。所以你写 app 时完全不用管，**但千万别把这个点区间当成普通的"起始下界"去理解**。

---

### 6. NegationEdge —— 否定边（"这段时间里禁止出现某事件"）

**什么时候用它**：当你的规则是"**不许**发生某事"。比如"某段走势结束后 20 根 bar 内，不许出现一次反向突破"。前面四种边都是"必须满足"，这一种相反，是"必须不出现"。

**它在判断什么**：以 `src` 的终点为锚，划出一个**禁止窗口**；只要这个窗口里出现满足条件的 `dst`，就算"违禁"。

```
禁止窗口： dst.start_idx − src.end_idx ∈ [min_gap, max_gap]
```

```python
@dataclass(frozen=True)
class NegationEdge(DependencyEdge):
    src: str
    dst: str
    min_gap: int = 0
    max_gap: float = math.inf
    inner_predicate: Optional[Callable[[Event], bool]] = None
```

**参数**

| 参数 | 类型 | 默认 | 含义 |
|---|---|---|---|
| `min_gap` | `int` | `0` | 禁止窗口起点，相对 `src.end_idx` 的偏移（含） |
| `max_gap` | `float` | `math.inf` | 禁止窗口终点偏移（含） |
| `inner_predicate` | `Optional[Callable[[Event], bool]]` | `None` | 额外的"哪种才算违禁"过滤器。`None` 时窗口内**任何** dst 都算违禁；给了函数时，**只有同时满足这个函数的** dst 才算违禁，其余放行 |

```python
# 禁止：src 结束后窗口内出现任何 dst 事件
NegationEdge("anchor", "forbidden")

# 禁止：src 结束后 20 bar 内出现 vol_ratio >= 3.0 的 dst，其余放行
NegationEdge(
    "anchor", "candidate",
    max_gap=20,
    inner_predicate=lambda e: e.vol_ratio >= 3.0,
)
```

> ⚠️ 常见坑一：**`satisfies` 的含义在这里是反的！**
>
> 对前面四种边，`satisfies` 返回 `True` 表示"关系成立、是好事"。但对 `NegationEdge`，`satisfies` 返回 `True` 表示"**这个 dst 违禁了**"。引擎用全称量词来消费它：
>
> ```
> 这条边成立  ⟺  禁止窗口内的每一个 e_dst 都【不】违禁
> ```
>
> 所以如果你调试时直接调 `edge.satisfies(a, b)` 看到 `True`，别误会——它的意思是"`b` 是个被禁的事件，因此这条边其实**不成立**"。

> ⚠️ 常见坑二：**被禁的 dst 不会出现在结果里**。`NegationEdge` 的 `dst` 是一个"约束"，不是走势的结构成员。命中后，`PatternMatch.role_index` 里**不会**有这个 dst 节点的绑定，`children` 里也找不到它。

> 💡 实现说明：`NegationEdge` 没有自己的 `feasible_window` / `signature_fields`，沿用基类默认（`(-inf, +inf)` 不剪枝、空元组），所以它不参与候选剪枝。

---

## 选边速查：我该用哪种？

看着自然语言需求，对号入座：

```
你想表达的关系                        选用的边
──────────────────────────────────────────────────────────────
A 结束后，B 在时序上跟随               TemporalEdge("A", "B")
A 结束后，B 紧接（gap=1）             TemporalEdge("A", "B", min_gap=1, max_gap=1)
A 区间包含 B 区间                      ContainmentEdge("A", "B")    ← A 是大区间
B 区间包含 A 区间                      ContainmentEdge("B", "A")    ← B 是大区间
A 区间只需包住 B 的起点（B 尾可在外） StartContainmentEdge("A", "B")  ← 只管起点
A 后端被 B 叠压（部分交叠）            OverlapEdge("A", "B")
B 后端被 A 叠压（镜像）                OverlapEdge("B", "A")
A 与 B 完全同段                        EqualsEdge("A", "B")
某窗口内禁止出现 B                     NegationEdge("anchor", "B")
某窗口内禁止特定属性的 B               NegationEdge("anchor", "B", inner_predicate=...)
```

---

## 完整示例：把三条边拼成一段走势

我们用真实的 `path2_apps/bottom_breakout_burst/dag_spec.py` 收尾。这个 app 想表达的走势用一句话说就是：**先有一段下跌，然后在一段横盘里冒出一串密集突破爆发，最后回踩确认**。我们来看它怎么用三条边把这句话拼出来。

**先理清楚两个关键事件**（这是看懂下面边为什么那么连的前提）：

- **`bo`（突破点）**：单个突破，是一个"点事件"（起点 == 终点 == 突破那根 bar）。
- **`burst`（突破爆发）**：把一串挨得很近的 `bo` **打包聚合成的一个"宽事件"**——它的起点是这串里**第一个 bo** 的起点、终点是**最后一个 bo** 的终点，内部用 `members` 装着组成它的那些 `bo`，并且在生成时就把"突破了几个、涉及几个不同的峰、最大放量比、首个突破前枯了多久"这几个数算好存成字段，供 `where` 直接读。`burst` 由 `BurstDetector` 消费 `bo` 流切串得到——它是一种**嵌套事件**（一个事件内部还装着更小的事件）。

> 💡 为什么边连 `burst` 而不连单个 `bo`？因为我们想约束的是"**这一整串**突破"——它从哪开始、跟谁回踩，都是针对整串说的。`burst` 正是"这一整串"的**代表事件**，所以三条边全都连到它身上。至于 `bo` 本身，在这张图里是个**孤立节点**（不连任何边）：它只作为"密度流源"喂给 `burst` 和回踩去消费、顺带能单独画在 K 线上，**不参与任何形态匹配**（引擎在出口会自动丢掉那些"只凑出一个孤零零 bo"的残缺结果）。嵌套事件的完整讲解见[积木层指南（building-blocks.md）](./building-blocks.md)，这里只需记住"`burst` = 一整串突破的代表"。

```python
from path2.dag.edges import TemporalEdge, StartContainmentEdge

edges = (
    # 约束 ④：下跌段 down 结束后 1~lookback bar 内，出现突破爆发 burst
    TemporalEdge("down", "burst", min_gap=1, max_gap=params.pred4_lookback_bars),

    # 约束 ①：突破爆发 burst 的起点必须落在横盘段 side 区间内
    #         （只管起点 —— burst 的尾巴允许冲出 side，所以用 StartContainmentEdge 而非 ContainmentEdge）
    StartContainmentEdge("side", "burst"),

    # 约束 ⑦：burst 结束（= 末个 bo 的终点）后恰好隔 1 bar 开始回踩确认 tb
    TemporalEdge("burst", "tb", min_gap=1, max_gap=1),
)
```

这三条边，配上 `PatternSpec` 里声明的 `nodes`（`bo` / `down` / `side` / `burst` / `tb` 共 5 个节点），就构成了一段完整走势的 DAG。引擎 `analyze(spec, df, params)` 直接吃下去，**你不用写一行匹配逻辑**。

> 你现在应该能做到：拿到一句"下跌后底部连续突破、然后回踩确认"，把它拆成几个节点，再用合适的边把它们串起来——并且知道，当一组散点要被当成"整串"来约束时，先把它聚合成一个代表事件（如 `burst`），再让边去连这个代表事件。

---

## 进阶：feasible_window 与 signature_fields 的剪枝契约

> 这一节是写**自定义边子类**时才需要关心的底层约定。只写 app、只用现成六种边的话，可以跳过。

前面反复提到的这两个方法，是引擎做候选剪枝（一项叫 INV-C 的不变式）的关键。如果你要新写一种边，必须严格遵守下面两条，否则会**漏匹配**：

1. **剪枝只能走 `feasible_window`，不能藏在 `satisfies` 里。**
   `feasible_window` 只能基于 `e_src` 的字段去缩窄 `e_dst.start_idx` 的候选范围。你**不能**在 `satisfies` 里偷偷加一些 `feasible_window` 没覆盖到的缩窄逻辑——否则引擎以为某些候选不用看，就漏了。

2. **`signature_fields` 必须如实申报。**
   它要列全 `satisfies` / `feasible_window` 实际用到的 `src` 的所有字段。漏报字段会让引擎的签名不完整，同样触发漏匹配。

各子类的取值汇总（查阅用）：

| 边类型 | feasible_window 返回值 | signature_fields |
|---|---|---|
| `TemporalEdge` | `[src.end_idx + min_gap, src.end_idx + max_gap]` | `('end_idx',)` |
| `ContainmentEdge` | `[src.start_idx, src.end_idx]` | `('start_idx', 'end_idx')` |
| `StartContainmentEdge` | `[src.start_idx, src.end_idx]` | `('start_idx', 'end_idx')` |
| `OverlapEdge` | `[src.start_idx + 1, src.end_idx - 1]` | `('start_idx', 'end_idx')` |
| `EqualsEdge` | `(src.start_idx, src.start_idx)`（点区间） | `('start_idx', 'end_idx')` |
| `NegationEdge` | `(-inf, +inf)`（不剪枝） | `()` |
