# children 声明规范化收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「容器 event 必须声明 `children`」从半途状态收尾成完整不变式——测试跟上代码、引用翻译补齐递归、文档反映真实行为。

**Architecture:** 三处引擎改动（构造期校验 + 标注期硬失败 + 出口校验放开）已在工作区未提交，本 plan 先锚定它们，再补两件缺的：`_translate_refs` 递归下钻 `child_slots`（与标注对称），以及四个受影响测试的语义跟进。最后修三处已与代码脱节的文档陈述。

**Tech Stack:** Python 3.12 · pytest · uv · path2 dag 引擎

**Spec:** 本 plan 自带 §0 背景节（本轮讨论无独立 spec 文件）。

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**（`/home/yu/PycharmProjects/Trade_Strategy`）。
- 包管理一律 `uv run`，不直接调 `pytest` / `python`。
- 注释与文档用中文，与仓库现有风格一致。
- **文档只反映当前代码状态**：不写开发历史、不写未实现的设计。代码与文档冲突时以代码为准。
- 术语用 `path2/CONTEXT.md` 里定下的词：事件流、子结构 node、引用槽、物化、复合事件。**不要**写「定语」（应为 where）、`event_id` / `class_id`（已退役，用 `instance_id`）。

---

## §0 背景（实施者必读，本节是 spec）

### 这条不变式是什么

一个事件类若重写了 `child_slots()`（即它是**复合事件**容器），承载它的 `NodeSpec` 就**必须**声明 `children={槽名: 子node_id}`。声明的作用是给容器内的子事件命名——引擎标注身份时按这张表把子事件标成它自己的 node_id（如 `tb.segments` → `tb_seg`），前端据 `node_id` 分轨分色，诊断据它认出这是哪一层。

历史上缺声明会**静默兜底**：子事件继承容器的 node_id，跟容器同名同轨，前端分不出来。更糟的是 `_check_children_declarations` 开头写着 `if not node.children: continue`——**一个字都没声明的容器反而完全逃过检查**，只有声明了一半的才会被 C2 抓。约束在最需要它的地方失效。

### 工作区已有的三处改动（未提交）

**实施前先确认这三处已在**（Task 1 Step 1 有验证命令）。若不在（例如在干净 worktree 实施），Task 1 Step 2 给出完整补丁。

1. `path2/dag/spec.py` — 新增构造期校验 `_validate_children_declared()`，接在 `__post_init__` 校验链末尾。容器 event 的 node 没声明 `children` → 构造期 `ValueError`。
2. `path2/dag/engine.py::annotate_stream._annotate_children` — 删掉 `cmap.get(slot_name, nid)` 的兜底默认值，槽名不在声明表里直接 `ValueError`。这一步**不受 `RUNTIME_CHECKS` 门控**，生产路径同样硬失败。
3. `path2/dag/engine.py::_check_children_declarations` — 跳过条件从 `if not node.children or node.detector is None` 改成 `if node.detector is None`。叶子 node 的 declared 与 inst 都是空集，检查天然通过，不会误伤。

### 本 plan 要补的两件事

**一、`_translate_refs` 递归下钻。** 当前它只做两层遍历（`streams.values()` → 每个顶层事件），**不进 `child_slots`**。而标注（`_annotate_children`）是递归的。这个不对称的后果：子结构事件若定义 `ref_slots()`，它的引用**永远不会被翻译**，`ref_ids` 恒为空元组，`ref_ids_of(...)` 返回 `()`，where 里读出来就是「没有引用」——**静默失效**，与引用池外对象那条响亮报错的待遇完全相反。

决策（用户 2026-09-07 拍板）：**让翻译也递归下钻**，与标注对称。理由：不对称本身就是缺陷成因；翻译幂等，一个对象既在流里又在槽里被翻译两次无害；将来子结构 node 若升级成独立流，这版天然兼容、不用回头改。

**二、四个测试的语义跟进。** 见 Task 1，逐个点名。

### 起点基线（已实测，2026-09-07）

**基线锚定在提交 `ee92dee`（清理 apps）之上**——该提交删掉了 `bb_pk` / `bb_v0` / `bb_v3` 三个 app 与 `throwback_v3`。实施前先 `git log --oneline -1` 核对；若 HEAD 已前移，重跑下表两行取新基线，别沿用这里的数字。

| 命令 | 工作区状态 | 结果 |
|---|---|---|
| `uv run pytest tests/ -q` | 含三处改动 | **11 failed, 1108 passed, 2 skipped** |
| `uv run pytest tests/ -q` | `git checkout HEAD --` 那两个文件后 | **7 failed, 1112 passed, 2 skipped** |

**本 plan 里的测试代码与验收命令都在写作时实测过**：Task 2 的两个新测试实测红在断言上、递归实现实测转绿且全量零新增失败；Task 1 Step 8 的两个 C2 测试实测通过；关卡 3 的命令实测有输出。照抄即可。

**7 个既存失败**（与本 plan 无关，实施后必须原样保留，不许顺手修）：

```
tests/path2/atoms/test_throwback_v4.py::TestStable::test_new_high_arm_exit
tests/path2/atoms/test_throwback_v4.py::TestStable::test_weak_exit_reentry
tests/path2/atoms/test_throwback_v4.py::TestGlobalBreak::test_ratchet_chain_then_break
tests/path2/atoms/test_throwback_v4.py::TestGates::test_no_gate_on_normal_exits
tests/path2/test_self_contained.py::test_no_breakoutstrategy_imports_in_path2
tests/path2_apps/bb_v1/test_bb_v1.py::test_params_yaml_has_peak_age_min
tests/scripts/test_data_download.py::test_transport_timeout_goes_through_cooldown
```

**4 个规范化引入的新失败**（Task 1 要清零）：

```
tests/path2/atoms/test_throwback_v1_dag_integration.py::TestDagIntegration::test_day_drop_where_filters_match_and_node_index_span
tests/path2/dag/test_children_checks.py::test_c2_undeclared_instance_slot_raises
tests/path2/dag/test_engine_annotate.py::test_annotate_stream_nested_child_inherits_node
tests/path2/dag/test_multilayer.py::test_multilayer_chain_and_double_identity
```

### 不在本 plan 范围内

- **不改任何 `path2_apps/` 下的 app**。四个存活 app（`bottom_burst` / `bb_v1` / `bo_only` / `try_conplex_where`）的容器 node 全都已声明 `children`（已实测，见关卡 3），规范化对它们逐字等价（`cmap.get(k, nid)` 的默认值从来没被取用过）。
- **不改前端**。`bandKeyOf = e.node_id` 与调色板分配都不受影响。
- **不把 `tb_seg` 改成独立流**。那是另一个量级的设计变更，本轮只讨论过可行性，不实施。

---

## Task 1: 规范化落地 + 四个测试的语义跟进

**Files:**
- Verify/Apply: `path2/dag/spec.py`, `path2/dag/engine.py`（三处改动，见 §0）
- Modify: `tests/path2/atoms/test_throwback_v1_dag_integration.py:100`
- Modify: `tests/path2/dag/test_multilayer.py:95-98`
- Modify: `tests/path2/dag/test_engine_annotate.py:54-63`, `:78-79`
- Modify: `tests/path2/dag/test_children_checks.py:67-84`

**Interfaces:**
- Consumes: 无（本 task 是起点）
- Produces: `_annotate_children` 缺声明时抛 `ValueError`，消息形如 `node 'tb': child 槽 'members' 未在 children 声明中`；`PatternSpec` 构造期抛 `ValueError`，消息形如 `NodeSpec('burst'): event_cls BurstEvent 是容器(重写 child_slots),必须声明 children`。Task 2 的测试会依赖前者不误伤合法路径。

**这一轮凭什么算做对了：前后红点差分。** 本 task 不新增行为，只是让测试追上已有代码。证据是那 4 个失败归零、7 个既存失败原样不动。TDD 不适用——被测行为已经存在了。

- [ ] **Step 1: 确认三处改动是否已在工作区**

Run:
```bash
grep -n "_validate_children_declared" path2/dag/spec.py
grep -n "未在 children 声明中" path2/dag/engine.py
grep -n "if node.detector is None:" path2/dag/engine.py
```

Expected: 三条都有命中（`spec.py` 两处：调用点在 `__post_init__` 校验链、定义在 `_validate_children_declared`）。**三条都命中 → 跳到 Step 3。** 任何一条无命中 → 执行 Step 2。

- [ ] **Step 2: （仅当 Step 1 有缺失时）应用三处改动**

`path2/dag/spec.py` — 在 `__post_init__` 的校验链末尾加一行调用：

```python
        self._validate_streams_bound()  # ★ 新增(契约 C3):多流 detector 的每条流都必须被 node 认领
        self._validate_children_declared()  # ★ 容器 event 必须声明 children
```

并在 `_validate_substructure` 之后加入方法定义：

```python
    def _validate_children_declared(self) -> None:
        """容器 event(重写 child_slots)的 node 必须声明 children。"""
        from path2.core import Event
        for n in self.nodes:
            cls = n.event_cls
            if cls is None or getattr(cls, "child_slots", Event.child_slots) is Event.child_slots:
                continue
            if not n.children:
                raise ValueError(
                    f"NodeSpec({n.node_id!r}): event_cls {cls.__name__} 是容器"
                    f"(重写 child_slots),必须声明 children")
```

`path2/dag/engine.py::annotate_stream._annotate_children` — 把兜底改成硬失败：

```python
    def _annotate_children(e, nid: str) -> None:   # 递归补标嵌套 child
        cmap = cmap_all.get(nid, {})
        for slot_name, slot in e.child_slots().items():
            if slot_name not in cmap:
                raise ValueError(
                    f"node {nid!r}: child 槽 {slot_name!r} 未在 children 声明中")
            child_nid = cmap[slot_name]
```

`path2/dag/engine.py::_check_children_declarations` — 放开跳过条件：

```python
    for nid, events in streams.items():
        node = by_id[nid]
        if node.detector is None:
            continue
```

- [ ] **Step 3: 记录本 task 起点红点**

Run: `uv run pytest tests/path2/dag/ tests/path2/atoms/test_throwback_v1_dag_integration.py -q 2>&1 | tail -8`

Expected: 恰好 4 failed，且就是 §0 列出的那 4 个（`test_day_drop_where_filters_match_and_node_index_span` / `test_c2_undeclared_instance_slot_raises` / `test_annotate_stream_nested_child_inherits_node` / `test_multilayer_chain_and_double_identity`）。把实际输出记进 task 笔记。

- [ ] **Step 4: 补 `test_throwback_v1_dag_integration.py` 的 children 声明**

这个 spec 用 `_FakeBurst` 产 `BurstEvent`（容器，`child_slots` 返回 `{"members": ...}`），`bo` node 已存在于同一 spec，属于「引用已有独立 node」那种情况。

`tests/path2/atoms/test_throwback_v1_dag_integration.py:100`，改：

```python
        burst_node = NodeSpec("burst", detector=_FakeBurst([burst1, burst2]), consumes_stream="bo")
```

为：

```python
        burst_node = NodeSpec("burst", detector=_FakeBurst([burst1, burst2]),
                              consumes_stream="bo", children={"members": "bo"})
```

- [ ] **Step 5: 补 `test_multilayer.py` 的两处 children 声明**

三级链 bo→burst→super，两个容器都要声明；两个槽引用的都是已存在的独立 node。

`tests/path2/dag/test_multilayer.py:95-98`，改：

```python
    burst_node = NodeSpec("burst", BurstDetector(gap_max=5, min_bos=3),
                          consumes_stream="bo")
    super_node = NodeSpec("super", SuperDetector(),
                          consumes_stream="burst")
```

为：

```python
    burst_node = NodeSpec("burst", BurstDetector(gap_max=5, min_bos=3),
                          consumes_stream="bo", children={"members": "bo"})
    super_node = NodeSpec("super", SuperDetector(),
                          consumes_stream="burst", children={"members": "burst"})
```

- [ ] **Step 6: 把 `test_annotate_stream_nested_child_inherits_node` 改成测新行为**

这个测试测的正是被删掉的兜底继承，不能靠补声明救——它的**主张本身**已经作废了。整个替换掉（`tests/path2/dag/test_engine_annotate.py:54-63`）：

```python
def test_annotate_stream_undeclared_slot_raises():
    """无 children 声明:标注期直接 ValueError(不再兜底继承容器 node_id)。
    这一步不受 RUNTIME_CHECKS 门控,生产路径同样硬失败。"""
    child = _Ev(start_idx=1, end_idx=3, confirm_idx=3)
    parent = _ContainerEv(start_idx=0, end_idx=5, confirm_idx=5, members=(child,))
    with pytest.raises(ValueError, match="未在 children 声明中"):
        annotate_stream({}, "tb", [parent])
    # 容器自身已先于 child 标注完(第一遍循环),child 未获身份
    assert parent.node_id == "tb"
    assert child.node_id is None
```

确认文件顶部已 `import pytest`；没有就加。

- [ ] **Step 7: 修 `test_annotate_stream_declaration_partial_slot_coverage` 的过时 docstring**

该测试（`tests/path2/dag/test_engine_annotate.py:78`）仍然通过——它构造的容器只有 `members` 一个槽且已声明覆盖，走不到未覆盖分支。但 docstring 的第二半句已经与代码矛盾。只改 docstring，**不动测试体**：

```python
def test_annotate_stream_declaration_partial_slot_coverage():
    """同一槽的多个成员按槽整体取声明名,逐成员各自入 (子node_id, span) 桶编号。
    (未覆盖槽现已硬失败,见 test_annotate_stream_undeclared_slot_raises。)"""
```

- [ ] **Step 8: 重新定位 C2 测试**

`test_c2_undeclared_instance_slot_raises` 现在被更早的标注期 `ValueError` 抢先，拿不到 C2 的 `RuntimeError`。

**但 C2 不是死代码**：`run_streams` 对 preset 里的 node 整条跳过检测与标注（`if node.detector is None or nid in streams: continue`），所以预置流的容器事件**不经过** `_annotate_children`；出口的 `_check_children_declarations` 是这条路径上唯一的防线。把测试拆成两个，各守一条路径（替换 `tests/path2/dag/test_children_checks.py:67-84` 整个函数）：

```python
def test_undeclared_instance_slot_raises_at_annotate():
    """正常路径:实例有未声明槽 → 标注期 ValueError(早于出口 C2)。"""
    @dataclass(frozen=True)
    class ExtraBox(Event):
        def child_slots(self):
            return {"members": (), "extra": ()}

    class ExtraDetector:
        event_cls = ExtraBox

        def detect(self, df):
            yield ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)

    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("box", ExtraDetector(), children={"members": "inner"}),
        NodeSpec("inner", event_cls=Inner)), edges=())
    with pytest.raises(ValueError, match="未在 children 声明中"):
        analyze(spec, df=object())


def test_c2_undeclared_instance_slot_raises_on_preset():
    """preset 路径:预置流跳过检测与标注,出口 C2 是唯一防线 → RuntimeError。"""
    from path2.dag.engine import run_streams

    @dataclass(frozen=True)
    class ExtraBox(Event):
        def child_slots(self):
            return {"members": (), "extra": ()}

    class ExtraDetector:
        event_cls = ExtraBox

        def detect(self, df):
            yield ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)

    spec = PatternSpec(pattern_id="t", nodes=(
        NodeSpec("box", ExtraDetector(), children={"members": "inner"}),
        NodeSpec("inner", event_cls=Inner)), edges=())
    # 预置一个已带身份的容器实例(模拟上一次 run_streams 的返回值)
    preset_box = ExtraBox(start_idx=0, end_idx=1, confirm_idx=1)
    object.__setattr__(preset_box, "node_id", "box")
    object.__setattr__(preset_box, "instance_idx", 0)
    object.__setattr__(preset_box, "instance_id", "box_0_1#0")
    with pytest.raises(RuntimeError, match="未声明"):
        run_streams(spec, df=object(), preset={"box": [preset_box]})
```

**这两个测试已在 plan 写作时实测通过**（preset 构造满足 `_check_preset` 的三条要求：键是 detector node、事件带 `instance_id` 与 `node_id`、`node_id` 在 detector node 集合内）。照抄即可，不必调整。

- [ ] **Step 9: 跑覆盖本 task 改动的测试**

Run: `uv run pytest tests/path2/dag/ tests/path2/atoms/test_throwback_v1_dag_integration.py -q 2>&1 | tail -8`

Expected: **0 failed**。（全量与验收关卡由控制端在末尾统一跑，本 task 不跑全量。）

- [ ] **Step 10: Commit**

```bash
git add path2/dag/spec.py path2/dag/engine.py tests/path2/dag/ tests/path2/atoms/test_throwback_v1_dag_integration.py
git commit -m "feat(dag): children 声明成为硬约束——删兜底继承,放开出口校验跳过条件

容器 event(重写 child_slots)的 node 必须声明 children:构造期校验 + 标注期
硬失败(不受 RUNTIME_CHECKS 门控)。原先漏声明会静默让子事件继承容器 node_id,
且 _check_children_declarations 的 'not node.children' 跳过条件让完全未声明的
容器逃过全部检查。

测试跟进:两处补声明(引用已有独立 node),兜底继承的测试改为断言 ValueError,
C2 测试重新定位到 preset 路径(预置流跳过标注,出口校验是唯一防线)。"
```

---

## Task 2: `_translate_refs` 递归下钻 child_slots

**Files:**
- Modify: `path2/dag/engine.py:71-92`（`_translate_refs`）
- Test: `tests/path2/dag/test_translate_refs_nested.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `children` 硬约束（本 task 的测试 spec 必须声明 `children`，否则构造期就炸）
- Produces: `_translate_refs` 递归遍历 `child_slots`，子结构事件的 `ref_slots()` 被正常翻译进 `ref_ids`

**这一轮凭什么算做对了：TDD，且 RED 必须红在断言上。** 新测试在改动前应该红在 `assert seg.ref_ids_of("cites") == (...)` 这一行（实际拿到 `()`），**不是**红在 `ImportError` / `AttributeError`。红在导入或属性上只证明代码不存在，不证明断言有牙齿——若首次运行红在别处，先把测试修到红在断言上再继续。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/dag/test_translate_refs_nested.py`：

```python
"""_translate_refs 递归下钻 child_slots:子结构事件的引用槽也被翻译。

背景:标注(_annotate_children)是递归的,翻译原先只遍历 streams 里的顶层事件。
这个不对称让子结构事件的 ref_slots() 静默失效——ref_ids 恒为空,where 读出来
就是「没有引用」,与引用池外对象那条响亮报错的待遇相反。
"""
from dataclasses import dataclass
from typing import Tuple

from path2.core import Event
from path2.dag.engine import analyze
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class Anchor(Event):
    """被引用的独立事件。"""
    pass


@dataclass(frozen=True)
class Seg(Event):
    """子结构事件:自己带引用槽,指向 Anchor。"""
    cites: Tuple[Event, ...] = ()

    def ref_slots(self):
        return {"cites": self.cites} if self.cites else {}


@dataclass(frozen=True)
class Container(Event):
    """复合事件容器:segments 槽装 Seg。"""
    segments: Tuple[Seg, ...] = ()

    def child_slots(self):
        return {"segments": self.segments}


class AnchorDetector:
    event_cls = Anchor

    def detect(self, df):
        yield Anchor(start_idx=0, end_idx=0, confirm_idx=0)


class ContainerDetector:
    """消费 anchor 流,产一个容器,容器内的段引用那个 anchor。"""
    event_cls = Container

    def detect(self, anchor_stream, df):
        anchors = tuple(anchor_stream)
        seg = Seg(start_idx=2, end_idx=4, confirm_idx=2, cites=anchors)
        yield Container(start_idx=2, end_idx=4, confirm_idx=2, segments=(seg,))


def _spec():
    return PatternSpec(
        pattern_id="t_nested_refs",
        nodes=(
            NodeSpec("anchor", AnchorDetector()),
            NodeSpec("box", ContainerDetector(), consumes_stream="anchor",
                     children={"segments": "seg"}),
            NodeSpec("seg", event_cls=Seg),
        ),
        edges=(),
    )


def test_nested_child_ref_slots_translated():
    """子结构事件的引用槽被翻译成 instance_id(递归下钻)。"""
    res = analyze(_spec(), df=object())
    boxes = [e for e in res.events if isinstance(e, Container)]
    assert len(boxes) == 1, f"应有 1 个容器,got {len(boxes)}"
    seg = boxes[0].segments[0]
    # 段自身已被标注(标注本来就递归)
    assert seg.node_id == "seg"
    # ★ 核心断言:段的引用槽被翻译(改动前恒为空元组)
    assert seg.ref_ids_of("cites") == ("anchor_0#0",), (
        f"子结构事件的 ref_slots 未被翻译,got {seg.ref_ids_of('cites')!r}")


def test_toplevel_ref_slots_still_translated():
    """回归:顶层事件的引用槽照常翻译(递归不能把原路径弄坏)。"""

    @dataclass(frozen=True)
    class Citer(Event):
        cites: Tuple[Event, ...] = ()

        def ref_slots(self):
            return {"cites": self.cites} if self.cites else {}

    class CiterDetector:
        event_cls = Citer

        def detect(self, anchor_stream, df):
            yield Citer(start_idx=3, end_idx=3, confirm_idx=3,
                        cites=tuple(anchor_stream))

    spec = PatternSpec(
        pattern_id="t_toplevel_refs",
        nodes=(NodeSpec("anchor", AnchorDetector()),
               NodeSpec("citer", CiterDetector(), consumes_stream="anchor")),
        edges=(),
    )
    res = analyze(spec, df=object())
    citers = [e for e in res.events if isinstance(e, Citer)]
    assert citers[0].ref_ids_of("cites") == ("anchor_0#0",)
```

- [ ] **Step 2: 跑测试确认红在断言上**

Run: `uv run pytest tests/path2/dag/test_translate_refs_nested.py -v`

Expected（已实测）: `1 failed, 1 passed`。`test_nested_child_ref_slots_translated` FAIL，失败行是那句 `assert seg.ref_ids_of("cites") == ("anchor_0#0",)`，报文逐字为：

```
E       AssertionError: 子结构事件的 ref_slots 未被翻译,got ()
E       assert () == ('anchor_0#0',)
```

`test_toplevel_ref_slots_still_translated` 应当 **PASS**（原路径本来就对）。

若前者红在别处（导入错误、`AttributeError`、构造期 `ValueError`），**先修测试再往下走**——红的位置不对就不构成证据。

- [ ] **Step 3: 改 `_translate_refs` 为递归**

`path2/dag/engine.py:71-92` 整个函数替换为：

```python
def _translate_refs(streams) -> None:
    """统一翻译阶段:所有流标注完后,把各事件的 ref_slots() 对象引用翻译成 instance_id,
    写入 Event.ref_ids(按槽名字典序排列的 (槽名,(instance_id,...)) 对)。引用事件
    池外对象(instance_id 仍为 None)视为 detect bug,报错。

    递归下钻 child_slots——与标注(_annotate_children)对称:子结构事件(如 tb 的
    企稳段)不出现在 streams 里,只活在容器的槽内,不下钻就会让它的引用槽静默失效
    (ref_ids 恒空,与「引用池外对象」的响亮报错待遇相反)。同一对象既在流里又在
    容器槽里(burst.members→bo 形态)只翻译一次,由 seen 去重;翻译本身幂等。"""
    seen: set = set()

    def _translate(e) -> None:
        if id(e) in seen:
            return
        seen.add(id(e))
        slots = e.ref_slots()
        if slots:
            pairs = []
            for slot_name, refs in slots.items():
                refs = (refs,) if isinstance(refs, Event) else refs   # 归一化单-Event 槽位(与 annotate_stream 一致)
                ids = []
                for ref in refs:
                    if ref.instance_id is None:
                        raise ValueError(
                            f"引用的事件没有 instance_id(不在任何已绑定流里):{type(ref).__name__} "
                            f"@bar {ref.start_idx}(ref_slots[{slot_name}]);PatternSpec 已校验全绑定,"
                            f"此处只剩 detect 引用了池外对象")
                    ids.append(ref.instance_id)
                pairs.append((slot_name, tuple(ids)))
            object.__setattr__(e, "ref_ids", tuple(sorted(pairs)))
        for slot in e.child_slots().values():
            members = slot if isinstance(slot, tuple) else (slot,)
            for c in members:
                _translate(c)

    for events in streams.values():
        for e in events:
            _translate(e)
```

- [ ] **Step 4: 跑测试确认转绿**

Run: `uv run pytest tests/path2/dag/test_translate_refs_nested.py -v`

Expected: 2 passed。

- [ ] **Step 5: 跑覆盖本 task 改动的测试**

Run: `uv run pytest tests/path2/dag/ tests/path2/test_event.py -q 2>&1 | tail -5`

Expected: 0 failed。（`tests/path2/dag/` 含 `test_children_checks.py` / `test_multilayer.py` / `_oracle.py` 驱动的一批嵌套事件用例，是递归改动的主要回归面。）

- [ ] **Step 6: Commit**

```bash
git add path2/dag/engine.py tests/path2/dag/test_translate_refs_nested.py
git commit -m "fix(dag): _translate_refs 递归下钻 child_slots

翻译原先只遍历 streams 里的顶层事件,而标注(_annotate_children)是递归的。
这个不对称让子结构事件的 ref_slots() 静默失效:ref_ids 恒为空元组,where 读
出来就是「没有引用」,与引用池外对象的响亮报错待遇相反。

改为递归,seen 按对象身份去重(同一对象既在流里又在容器槽里只翻译一次)。"
```

---

## Task 3: 文档跟进（三处已与代码脱节的陈述）

**Files:**
- Modify: `path2/dag/engine.py`（`annotate_stream` docstring）
- Modify: `path2_web/serialize.py:219-227`（调色板注释块）
- Modify: `.claude/skills/authoring-path2-app/design-heuristics.md`（§B 新增一条）
- Modify: `.claude/skills/authoring-path2-app/SKILL.md`（`solve=False` 一节补半句）
- Modify: `.claude/skills/authoring-path2-detector/reference.md`（负知识清单补一条）

**Interfaces:**
- Consumes: Task 1 与 Task 2 的最终代码行为
- Produces: 无（纯文档）

**这一轮凭什么算做对了：人工来源核对 + 跑一遍覆盖测试确认没写坏。** 纯文档改动没有可断言的新行为，证据是每条陈述都能在代码里指到对应行，且引用的行号/命令仍然有效。

- [ ] **Step 1: 修 `annotate_stream` 的 docstring**

`path2/dag/engine.py::annotate_stream` 的 docstring 里这段已经作废（它描述的是被删掉的兜底）：

> children_of(...)= 未标注 child 的命名表:按容器槽名查映射,有声明 → 用声明的子结构 node_id(如 tb.segments → tb_seg);无声明/槽未覆盖 → 继承容器流 nid 兜底(旧 app 行为不变,声明即启用)。

替换为：

```
    children_of({node_id: {slot名: 子node_id}},spec 的 children 声明)= 未标注
    child 的命名表:按容器槽名查映射,标成声明的子结构 node_id(如 tb.segments →
    tb_seg)。槽名不在声明表里直接 ValueError——不再兜底继承容器 nid;这一步
    不受 RUNTIME_CHECKS 门控,生产路径同样硬失败。构造期另有
    PatternSpec._validate_children_declared 拦住「容器 node 一个槽都没声明」。
    声明漂移由 _check_children_declarations(C1/C3) 抓。已标注跳过保证"槽引用
    独立 node 实例"(burst.members→bo,独立流先物化先标注)不被重标。
```

- [ ] **Step 2: 修 `serialize.py` 的调色板注释**

`path2_web/serialize.py:219-227` 的槽位表漏了 `pk`（pk 加入后首现序整体后移一位），与 `tests/path2_apps/bottom_burst/test_dag_spec.py::TestEventStyles::test_palette_assigns_by_node_order` 实测的分配对不上。按实测结果改写槽位表：

```python
# event_styles 兜底调色板:PATTERN_DAG.event_styles 默认空,按 topology.nodes 里 node_id
# 首次出现顺序 setdefault(见 _event_styles),索引 i 就是"第 i 个新 node_id"。当前拓扑覆盖
# (apps 均无显式 event_styles 声明,全走兜底;bottom_burst 首现序 bo/pk/burst/tb/tb_seg):
#   [0] bo     (主图 price-anchored [ids] 方框)
#   [1] pk     (bottom_burst 的第二个 node_id;多流 bo detector 的 pk 流)
#   [2] burst  (副图 interval)
#   [3] tb     容器
#   [4] tb_seg 企稳段:与 bo 兜底绿(#16f943)拉开——同色会触发 deriveNodeColors 明度散开
#   [5..6]     未占用,给未来新 node_id 兜底(顺序即分配序,i % len 循环)
_PALETTE = ["#16f943", "#2563eb", "#FF1500", "#14b24e", "#7c3aed", "#0891b2", "#ca8a04"]
```

**核对方式**（改完必跑，确认注释与实际分配一致）：

Run: `uv run pytest tests/path2_apps/bottom_burst/test_dag_spec.py::TestEventStyles -q`

Expected: 1 passed，且该测试断言的 `{"bo": "#16f943", "pk": "#2563eb", "burst": "#FF1500", "tb": "#14b24e", "tb_seg": "#7c3aed"}` 与你写的槽位表逐项对应。

- [ ] **Step 3: `design-heuristics.md` §B 新增一条设计判据**

`.claude/skills/authoring-path2-app/design-heuristics.md` 的 §B 现有 5 条（第 5 条是「复合宽事件 vs 逐事件串」）。在其后新增第 6 条：

```markdown
6. **子结构 node 想参与约束时的选择阶梯**:复合事件的 child(如 tb 的企稳段)默认
   只用于诊断与展示——它没有自己的事件流,也就没有候选池,`bound_ids` 的
   「detector 非空」那项会把它挡在求解外(`path2/dag/_solve.py`,注释原话「子结构
   node 无候选池」)。想让它进约束,按代价从小到大试:
   ① **容器加 `child()` 投影** → 边写 `Child("tb", "first_seg")`。`Child` 不引入新
      变量,`__post_init__` 把它归一化成 `dst="tb", dst_selector="first_seg"`,WCC 图
      看到的仍是纯 `tb`,搜索空间不变。样板:`BurstEvent.child("first_bo"/"last_bo")`
      (`path2/atoms/breakout.py`)。代价在剪枝——带 selector / anchor_field 的边会关掉
      对应端点的 C1(见 `_solve.py` 的 c1_off 五源表)。
   ② **升格成独立流**(detector 改 `produces` 多流,子事件自成一 node)——只有当子事件
      需要**自己被枚举、被候选筛选**时才值得。代价:求解空间乘上子事件数量;detector
      要为每条流各自维护 end_idx 升序(`run_bundle` 逐流跑 `_check_stream`);子事件
      从「容器的内部结构」变成一等事件,诊断 / web / eval 都按独立事件对待。
   判据不是「技术上能不能」,而是「它是否需要独立于容器被约束筛选」。`bo` 需要(突破
   本身是完整事件,burst 只是它的一层聚类),企稳段目前不需要(对外接口全由容器代言)。
```

- [ ] **Step 4: `SKILL.md` 的 `solve=False` 一节补半句**

`.claude/skills/authoring-path2-app/SKILL.md` 的「`solve=False`(只显示不参与匹配)」段落末尾追加：

```markdown
**三种「不参与求解」别混**:①**结构性出局**——子结构 node 无 detector 即无候选池
(`bound_ids` 的 `detector is not None` 那项);②**声明性出局**——有流有池但
`solve=False` 主动弃权(如 `pk`);③**拓扑性出局**——有池但在含边 pattern 里没连任何
边(K2 第一条,孤立即不属 pattern)。成因不同,排查方向也不同。
```

- [ ] **Step 5: `reference.md` 负知识清单补一条**

`.claude/skills/authoring-path2-detector/reference.md` 的「负知识清单」新增一条：

```markdown
- **多流下 `end_idx` 升序是逐流校验的**：`run_bundle` 对 `produces` 声明的每条流各跑一次
  `_check_stream`。把一个原本按容器排序的单流 detector 多流化时，每条流都要自己排好——
  子事件常常是逐父事件生成的、跨父交错，直接 yield 会在第二条流上撞升序校验。
- **容器 event 的 node 必须声明 `children`**：重写了 `child_slots()` 就是容器，`PatternSpec`
  构造期校验（`_validate_children_declared`）+ 标注期硬失败（`_annotate_children`，不受
  `RUNTIME_CHECKS` 门控）双重拦截。声明的槽名 → 子结构 node_id，子事件据此获得自己的身份
  与渲染轨道；漏声明不再静默继承容器 node_id。
```

- [ ] **Step 6: 跑一遍覆盖测试确认文档改动没写坏代码**

Run: `uv run pytest tests/path2_web/test_serialize.py tests/path2_apps/bottom_burst/ tests/path2/dag/test_engine_annotate.py -q 2>&1 | tail -5`

Expected: 0 failed。（`serialize.py` 与 `engine.py` 只改了注释/docstring，但两者都是被 import 的模块，跑一遍确认没有语法或缩进破坏。）

- [ ] **Step 7: Commit**

```bash
git add path2/dag/engine.py path2_web/serialize.py .claude/skills/
git commit -m "docs: children 硬约束的文档跟进 + 调色板注释纠偏

- annotate_stream docstring:删掉已作废的兜底继承描述
- serialize.py 调色板槽位表:补 pk(首现序整体后移),与 TestEventStyles 实测对齐
- design-heuristics §B.6:子结构 node 参与约束的选择阶梯(child() 投影 → 独立流)
- SKILL.md:三种「不参与求解」的区分(结构性/声明性/拓扑性)
- detector reference 负知识:多流逐流校验 end_idx 升序 + 容器必须声明 children"
```

---

## Task 4: 验收关卡（控制端执行，不派 implementer）

**这一节不派 implementer。** 由控制端在**代码最后一次改动之后**（含终审 fix wave）跑，记录实测输出作为交付证据。提前跑的结果只能当中途信息。

- [ ] **关卡 1:全量回归，新增失败为 0**

Run: `uv run pytest tests/ -q 2>&1 | tail -12`

Expected: **7 failed**，且失败清单与 §0 列出的 7 个既存失败**逐条相同**（不是只看数字——4 个规范化失败必须消失，7 个既存失败必须还在原位，任何一条新面孔都算回归）。passed 数应 ≥ 1112 + 新增测试数（Task 1 净 +1，Task 2 +2）。

- [ ] **关卡 2:bottom_burst 渲染契约不变**

Run: `uv run pytest tests/path2_apps/bottom_burst/ -q 2>&1 | tail -5`

Expected: 0 failed。其中 `TestEventStyles::test_palette_assigns_by_node_order` 断言的分配必须仍是
`{"bo": "#16f943", "pk": "#2563eb", "burst": "#FF1500", "tb": "#14b24e", "tb_seg": "#7c3aed"}`——
这是「规范化不改变界面」的直接证据：段仍标成 `tb_seg`、仍拿自己的槽位和颜色。

- [ ] **关卡 3:四个 app 的 spec 全部仍可构造**

构造期新增了校验，任何 app 漏声明 `children` 都会在这里炸。

Run:
```bash
uv run python -c "
import importlib
apps = ['bottom_burst', 'bb_v1', 'bo_only', 'try_conplex_where']
for a in apps:
    m = importlib.import_module(f'path2_apps.{a}.dag_spec')
    spec = m.build_pattern(m.load_params())
    kids = {n.node_id: dict(n.children) for n in spec.nodes if n.children}
    print(f'{a}: {len(spec.nodes)} nodes, children={kids}')
"
```

Expected（已实测，逐字对照）:

```
bottom_burst: 5 nodes, children={'burst': {'members': 'bo'}, 'tb': {'segments': 'tb_seg'}}
bb_v1: 4 nodes, children={'burst': {'members': 'bo'}}
bo_only: 2 nodes, children={}
try_conplex_where: 4 nodes, children={'burst': {'members': 'bo'}}
```

- [ ] **关卡 4:git 状态干净**

Run: `git status --short`

Expected: 无未提交改动。plan 起点时工作区只有 `path2/dag/engine.py` 与 `path2/dag/spec.py` 两个 M（Task 1 会提交它们）；若实施期间出现别的 M/??，逐个确认是不是本 plan 该产出的东西。

---

## 留账（本 plan 不做，记录以免被当成遗漏）

- **`tb_seg` 升格成独立流**：本轮确认了技术可行（`ThrowbackDetectorV4` 改 `produces` 多流，`bo`/`burst` 是现成先例，"首现获胜"保证标注不打架），但没有需求驱动。触发信号是「想写一条边把某个段跟别的 node 关联起来」，届时先试 `Child("tb", ...)` 投影这条更轻的路（见 design-heuristics §B.6）。
- **`ThrowbackEventV4` 没有 `child()` 投影**：现在 `Child("tb", key)` 会撞 `Event.child` 默认的 `raise KeyError`。等真有边要写时再加。

### 实施期新增的留账（2026-09-07 执行本 plan 时发现，均不在本轮范围）

- **预置流 + 部分声明 + `RUNTIME_CHECKS` 关闭 = 一格无防线**（终审探针实测）。三道防线各守一条路径：构造期 `_validate_children_declared` 只判「一个槽都没声明」，不查槽名完整性；标注期硬失败 ungated 但预置流不经过它；出口 C1/C2/C3 受 `RUNTIME_CHECKS` 门控。三者交集处漏出这一格。现实中未暴露——唯一的生产 preset 使用者 tune-gates 四个入口都显式 `config.set_runtime_checks(True)`。要堵得把「部分声明」检查提到 ungated，是设计决策，本轮不做。
- **出口 C2 不递归**：`_check_children_declarations` 只看流内顶层事件，所以「嵌套容器的部分声明」在预置流路径上即使 checks 开着也不查，只有构造期能兜住它的「零声明」形态。
- **`bo` 与 `tb` 现在同为绿系且不会被自动拉开**：`pk` 插入调色板后 `tb` 拿到 `#14b24e`，与 `bo` 的 `#16f943` 都是绿；而 `deriveNodeColors` 只对**完全同值**的 hex 做明度散开，两个近似但不相等的绿不会被介入。非本轮引入（是 pk 加入时的连带位移），且不改前端是本轮的范围外约定。
- **`docs/research/**/repro/` 下十余处直接调 `annotate_stream` 的脚本现在必须自备正确的 `children_of`**：容器流传空表会硬失败。`stream_replay_equiv.py` 那份是对的（传了 `children_of`），可作样板；`generic_grid_cost.py` 那份已因别的原因（`spec.nodes[2]` 在 pk 加入后已是 burst 而非 tb）先行过期，属冻结的研究产物，不必修。
- **`_translate_refs` 递归的回归护栏缺口**：现有测试只覆盖「容器→子事件带引用槽」一层；**孙层**（子事件自己再有 `child_slots`）与**共享子事件被两个容器持有**这两种形状没有测试钉住，而它们正是 `seen` 去重真正起作用的场景。终审已用探针实测两种形状行为均正确（孙层拿到 `gc_3#0` 与正确的 `ref_ids`；共享子事件 `mid is mid2` 且只翻译一次），所以这是护栏缺口而非潜伏 bug。若要补，一个 `share=False/True` 的参数化测试可同时覆盖两种形状。
- **几处已知但判为可留账的小账**：`test_annotate_stream_declaration_partial_slot_coverage` 的测试名已与它测的东西脱节（硬失败后「部分覆盖」这条合法路径不存在了）；`test_children_checks.py` 里手工拼的 `instance_id` 字面量 `"box_0_1#0"` 复制了引擎的身份格式知识（当前不假绿，`_check_preset` 将来加格式校验时会成为沉默过期点）；`engine.py` 的 `seen: set = set()` 可标注为 `set[int]`（键是 `id(e)`）；`refs = (refs,) if isinstance(refs, Event) else refs` 行尾注释「与 annotate_stream 一致」措辞不准（那里判 `Event`，`annotate_stream` 归一化 child 槽判 `tuple`）。
