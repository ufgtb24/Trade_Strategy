# path2 因果闸落地改造 · 指导文档

> **用途**：第二轮工作流设计期间，对 path2 引擎进行以下改动。
> 改动遵循 `feedback.md` §0 的"尺子作用域裁定"与 §1 的技术论证。
> 改动是**局部、增量、可独立验收**的，不涉及架构重整。

---

## 为什么要改

### 问题：因果依赖的知识分散在消费者侧

**现状**：不同 event 的"可以买入的那根 bar"各不相同：

| event | 合法买点在 | 现在如何知道 |
|---|---|---|
| `BurstEvent` | `end_idx`（最后一个成员） | 约定在文档里，消费者自己记 |
| `ThrowbackEvent` | `start_idx`（确认那根） | `start_idx` 语义被重载为"确认点"，需看 docstring |
| `TrendSegment` | `end_idx`（趋势终点） | 约定在文档里 |
| 点事件 | 唯一的 `idx` | 推断 |

每个拿 event 做买点的人，都得先弄清"这个 event 的买点在哪根上"。**知识分散、容易出错**——用错的那个字段（比如 burst 的 `start_idx`）不会报错，只是拿到前瞻偏差的结果。

**A.3 的教学例子**：同一个"删 tb"的结构改动，买点锚在"事件成立那根"得 0.075；锚在"事件开始那根"得 **0.436**（\|z\|=17.8，三道硬门全过，等于回到过去买）。**而现成的评估骨架默认取的就是错的那个。**

### 约定落到引擎而不是文档

**目标**：让每个 event 自己声明"我在哪一根上算确认成立"，消费者直接用这个声明，不需要记任何约定。

---

## confirm_idx 的语义与确定标准（协议定义）

> 这一节是 spec 的核心。`confirm_idx` 该取什么值，由这里定义的标准裁决，不由"哪个值碰巧安全"决定。代码实现（下一节）只是把这套标准落地。

### 语义定义

**`confirm_idx` = detector 能够首次判定"事件成立"的那根 bar。**

精确表述：站在 `confirm_idx` 这根收盘时，**只读 ≤ confirm_idx 的数据，就足以确定本事件已经发生**。`confirm_idx` 之后到 `end_idx` 的数据是事件成立后才产生的（后续走势、验证窗口），不属于"判定事件成立"的依据。

### 核心区分：成立条件 vs 观察窗口

这是确定 `confirm_idx` 的全部依据。一个跨度事件有两个容易混淆的时间概念：

| 概念 | 含义 | 决定什么 |
|---|---|---|
| **成立条件** | detector 必须观察到什么，才能说"这个事件发生了" | **confirm_idx** |
| **观察窗口**（`end_idx`） | 事件成立后，用来跟踪后续表现 / 验证买点的窗口 | `end_idx`（与 confirm_idx 无必然关系） |

**`confirm_idx` 跟踪的是成立条件，不是观察窗口。** 一个 event 的 `end_idx` 可以远在成立条件满足之后——那段时间只是在观察，不是在判定。

### 自检判据

对每个 detector，问自己一个问题：

> **砍掉 `end_idx` 这根（及之后的所有 bar），我还能不能判定事件成立？**
> - **能** ⟹ `confirm_idx < end_idx`（终点只是观察窗口）
> - **不能** ⟹ `confirm_idx = end_idx`（终点是成立条件的一部分）

### 用标准解释：为什么 tb 与 burst 不同

这两个值的分歧不是"tb 特殊"，是同一条标准在不同检测逻辑下的自然结果：

**BurstEvent**：成立条件 = "前缀长度 ≥ min_bos"。这个条件在**最后一个成员 bo** 那根才满足——没看到那根，不知道前缀够不够长。**成立条件本身包含"看到区间终点"**，所以 `confirm_idx = end_idx`。

**ThrowbackEvent**：成立条件 = "突破后回踩、止跌企稳"。这个条件在企稳信号出现的那根（`start_idx`）就满足了。`end_idx` 是"大涨前一根 / 破位前一根 / timeout"——是**观察窗口**，不是成立条件。如果等到 `end_idx` 才确认事件成立，已经错过买点（买点就该在企稳那一刻进）。所以 `confirm_idx = start_idx`。

**推论**：未来若出现一个成立条件在区间中点满足、终点也是观察窗口的 detector，它的 `confirm_idx` 就该落在中点。标准是统一的，取值随检测逻辑变。

### 这个标准规定在代码库的哪个位置

**协议层 —— `path2/core.py` 的 `Event` 基类 docstring。**

理由：`confirm_idx` 是引擎协议（每个 event 都要回答），协议的定义只能在协议层。**不该散落到**：各 atoms 文件（那是实现，不是协议）、评估器（那是消费者）、研究文档（那是临时的）。

每个 detector 的 docstring 再补一句本类的 `confirm_idx` 取值及理由（局部说明，接在协议定义之后）。

#### `Event` 基类 docstring 示例文本（实施时照此写进 `core.py`）

```python
class Event(ABC):
    """所有走势事件的冻结基类。

    ...
    confirm_idx: int  — 事件被确认成立的 bar 索引。

        语义：站在 confirm_idx 这根收盘时，只读 ≤ confirm_idx 的数据，
        就足以确定本事件已经发生。confirm_idx 之后到 end_idx 的数据
        是事件成立后才产生的（后续走势、验证窗口），不参与"判定成立"。

        确定标准 —— 区分两个概念：
          · 成立条件：detector 必须观察到什么才能说"事件发生了"。
            confirm_idx 跟踪它。
          · 观察窗口（end_idx）：事件成立后跟踪后续表现的窗口。
            与 confirm_idx 无必然关系。

        自检：砍掉 end_idx（及之后所有 bar）还能不能判定事件成立？
          能  → confirm_idx < end_idx（终点只是观察窗口）
          不能 → confirm_idx = end_idx（终点是成立条件的一部分）

        必填，每个子类显式声明。约束：start_idx ≤ confirm_idx ≤ end_idx。
    """
```

---

## 改动一：加 `confirm_idx` 字段

### 设计原则：必填，每个子类显式声明

**`confirm_idx` 是引擎协议的一部分 ⟹ 它是必填字段，没有默认值。** 每个 Event 子类都必须显式声明自己的 `confirm_idx`。

**为什么不用默认值**：默认值（哪怕是"保守的 end_idx"）会把"哪些 event 该用 end_idx"这个判断藏回基类里——这跟我们要治的病（知识分散在消费者侧）是同一种病，只是藏深了一层。必填 + 显式声明，才能逼每个 detector 作者回答"我的事件在哪根上算成立"——这正是加这个字段的目的。

### 各子类的 confirm_idx 取值（已核实语义）

| 子类 | 类型 | confirm_idx | 理由 |
|---|---|---|---|
| `BOEvent` | 点 (`is_point=True`) | `start_idx`（=`end_idx`=i） | 单根 bar，那根就确认 |
| `Distribution` | 点 (`start_idx==end_idx`) | `start_idx` | 同上 |
| `BurstEvent` | 跨度·前缀物化 | `end_idx` | 前缀物化：每个实例在其最后一个成员 bo（= `end_idx`）那根 emit，那根就是确认点。注意一串 N 个 bo（N>min_bos）会产生多个实例，每个实例的 `end_idx` 不同，各自的 confirm_idx = 各自的 end_idx |
| `TrendSegment` | 跨度·retrospective | `end_idx` | regime 切换时才确认完整区段 |
| `Platform` | 跨度·retrospective | `end_idx` | 价格走出平台才确认 |
| `ThrowbackEvent` | 跨度·确认类 | `start_idx` | start_idx 本就是确认点（恢复几何含义后仍如此） |
| `PatternMatch` | 跨度·聚合体(dag 层) | `end_idx` | 所有 constituent event 物化后整个 match 才确认。**spec 初稿漏列此行,实施时发现 `PatternMatch` 也继承 `Event`(`result.py:49`)而补上** |

**没有一个等于"碰巧的默认值"——每个都是该被显式声明的语义决定。**

### 改什么

**`path2/core.py Event` 基类**：

```python
from dataclasses import field

@dataclass(frozen=True)
class Event(ABC):
    # ... 现有字段不变 ...

    # ★ 必填，kw_only 避开 dataclass 字段顺序约束
    confirm_idx: int = field(kw_only=True)
```

**`__post_init__` 加区间不变式**：

```python
def __post_init__(self):
    # ... 现有不变式不变 ...

    if not (self.start_idx <= self.confirm_idx <= self.end_idx):
        raise ValueError(
            f"confirm_idx={self.confirm_idx} 必须在 "
            f"[start_idx={self.start_idx}, end_idx={self.end_idx}] 内"
        )
```

**每个 Event 子类的构造点都要显式传 `confirm_idx=...`**（核实过的取值见上表）：

- `path2/atoms/breakout.py`：`BOEvent(...)` 加 `confirm_idx=i`（点事件，= `start_idx`）；`BurstEvent(...)` 加 `confirm_idx=end_idx`
- `path2/atoms/trend.py`：`TrendSegment(...)` 加 `confirm_idx=end`
- `path2/atoms/platform.py`：`Platform(...)` 加 `confirm_idx=end`
- `path2/atoms/distribution.py`：`Distribution(...)` 加 `confirm_idx=i`（点事件）
- `path2/atoms/throwback.py`：`ThrowbackEvent(...)` 加 `confirm_idx=start`（start_idx 本就是确认点）

### 为什么这样做

**`field(kw_only=True)`**（Python 3.10+）：让 `confirm_idx` 必须用 keyword 传入，且不受字段声明顺序约束——避开 dataclass "无默认字段不能跟在有默认字段后面"的脆性。现有子类构造全部已用 keyword args（`start_idx=...`），加一个 kw_only 必填字段不破坏调用。

**必填而非默认值**：这是协议一致性的要求。点事件的 `confirm_idx = idx` 虽然由定义确定，但显式写出来让协议统一——没有"有些子类声明、有些靠默认"的分裂。未来如果某个点事件需要延迟确认（比如等下一根 bar），显式声明让它容易改。

### 验证方式

**零 DIFF 验收**：

1. 全部 6 个 Event 子类的所有现有单元测试必须通过。
2. 运行全项目 `pytest`：预期零 regression。
3. **新增测试**：构造一个 `confirm_idx < start_idx` 的 event，预期 `__post_init__` raise。

**语义自检**（每个子类都显式声明了）：

- 点事件（`BOEvent`/`Distribution`）：`confirm_idx = start_idx = end_idx`
- 跨度·retrospective（`BurstEvent`/`TrendSegment`/`Platform`）：`confirm_idx = end_idx`
- 跨度·确认类（`ThrowbackEvent`）：`confirm_idx = start_idx`

**因果闸接上**（`path2_web/eval_runner.py` 或评估层）：

```python
for match in res.matches:
    ev = match.event
    # confirm_idx 是必填字段，不存在 None 的情况
    if match.buy_bar < ev.confirm_idx:
        raise AssertionError(
            f"因果闸失效：买点 bar={match.buy_bar} < "
            f"事件确认 bar={ev.confirm_idx} ({ev.__class__.__name__})"
        )
```

### 改动范围

| 文件 | 改动量 | 性质 |
|---|---|---|
| `path2/core.py` | ~10 行 | 基类加必填字段 + 不变式 |
| `path2/atoms/breakout.py` | ~10 行 | `BOEvent`/`BurstEvent` 构造点加 `confirm_idx=` |
| `path2/atoms/trend.py` | ~1 行 | 构造点加 `confirm_idx=end` |
| `path2/atoms/platform.py` | ~1 行 | 构造点加 `confirm_idx=end` |
| `path2/atoms/distribution.py` | ~1 行 | 构造点加 `confirm_idx=i` |
| `path2/atoms/throwback.py` | ~1 行 | 构造点加 `confirm_idx=start` |
| 评估层（因果闸接入） | ~10 行 | `_eval_ticker` 加 `start_idx < confirm_idx` 断言（必填，无 None 分支） |
| `path2/dag/result.py` + `_reify.py` | ~2 行 | **`PatternMatch` 也继承 `Event`**，构造点加 `confirm_idx=end`。spec 初稿写"0 行/不涉及"是错的，实施时发现 |
| 求解器（`_solve.py`） | 0 行 | 不涉及（`confirm_idx` 不进签名源/剪枝） |

**全程 match 逐字不变**，影响范围小，风险低。

---

## 不改什么（重要）

### ❌ 不改 tb 的 `start_idx` 语义（本轮保持现状）

本轮 `ThrowbackEvent.start_idx` **保持现有语义**（= 止跌企稳确认点），不"恢复几何含义"。确认职责由新增的 `confirm_idx` 承担，`confirm_idx = start_idx`（成立条件在 `start_idx` 满足，见「协议定义」节）。"恢复 `start_idx` 几何含义 + 消掉 `anchor_field`"是被否决的提案②，见 `feedback.md` §1。

### ❌ 不消掉 `anchor_field` 机制

**原因**：burst 的 `last_bo` 和 tb 锚定的 bo 是同一个 event 对象，DAG 边只能表达关系、不能表达同一性。`anchor_field` 比的是 `event_id`，这是结构等价方式。改成 `gap==0` 等于把"同一"降级编码成"位置巧合"，前提一破就静默错配。

而且项目正在往"多同 bar 同类事件"的方向走（`assign_auto_source_tags`），位置等价在前提上就更弱了。

### ❌ 不动 `assign_auto_source_tags` / `child_slots` 机制

现有 nested event 机制（`Child(node,key)` 端点选择器）是另一条线，与因果闸落地无关。tb 以后可以用 child 表达"被某个 bo 触发"，但那是一个独立的特性化，不是本改动的一部分。

---

## 实施清单

- [ ] `path2/core.py Event` 加 `confirm_idx` **必填**字段（`field(kw_only=True)`，无默认值）
- [ ] `Event.__post_init__` 加区间不变式（`start_idx ≤ confirm_idx ≤ end_idx`）
- [ ] `Event` docstring 写入 `confirm_idx` 的语义定义与确定标准（见本文「协议定义」节，含示例文本）
- [ ] 全部 6 个 Event 子类的构造点显式传 `confirm_idx=`，各取值见「各子类取值」表：
      `BOEvent`/`Distribution`=`start_idx`、`BurstEvent`/`TrendSegment`/`Platform`=`end_idx`、`ThrowbackEvent`=`start_idx`
- [ ] 每个 detector 的 docstring 补一句本类 `confirm_idx` 的取值理由（区分成立条件 vs 观察窗口）
- [ ] 验证：跑全项目 `pytest`，预期 zero regression（match 逐字不变）
- [ ] 新增测试：构造 `confirm_idx < start_idx` 的 event，预期 `__post_init__` raise
- [ ] 评估层接入因果闸：读取 `match.event.confirm_idx`（必填），判 `buy_bar >= confirm_idx`
- [ ] 文档：`final_report.md` A.3 补充说明（用新字段解释为什么 0.436 vs 0.075 的分歧不会再发生）

---

## 成功验收的标准

**代码层面**：

- 全部现有测试通过，零 DIFF。
- 新的 `__post_init__` 不变式被验证（`ThrowbackEvent` 会触它）。

**语义层面**：

- 任何消费者拿到一个 event，直接读 `ev.confirm_idx`，无需任何约定就能知道"这个 event 在哪一根上算确认成立"。
- 因果闸用一行 `buy_bar >= ev.confirm_idx` 捕获所有前瞻偏差，无需查表、无需按 detector 类型分情况。

**文档层面**：

- `path2/core.py` Event docstring 写清楚：`confirm_idx` 是"只读 ≤ 这一根就能判定事件成立"的 bar；**必填，每个子类按成立条件显式声明**（标准见「协议定义」节）。
- `final_report.md` A.3 补充：用新字段解释为什么不会再有 0.436 vs 0.075 的六倍分歧。

