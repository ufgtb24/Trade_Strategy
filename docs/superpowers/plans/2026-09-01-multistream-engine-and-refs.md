# 多流引擎扩展 + 引用协议（ref_slots）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展 path2 引擎允许一个 detector 在一个 detect 调用内产出多条命名流，并通过 `ref_slots` 协议让同源多流之间的事件引用在标注后精确解析成 instance_id。

**Architecture:** 流的身份单位从「detector 实例」下移到「(detect 调用) × (命名流)」，node 依旧一对一绑定一条流。detector 用 `produces = {流名: event_cls}` 声明多流、`yield (流名, event)` 产出；`DEFAULT_STREAM=None` 把单流 detector 归一化成同一种形态（兼容支点，现存 NodeSpec 零改动）。物化键 `(id(detector), consumes_stream)` 形状不变、缓存值从 `list` 变 `{流名: list}`；`ref_slots()` 在全部流标注后统一翻译成 instance_id。`NodeSpec.solve` 一并落地（零边 pattern 加孤立 node 的硬阻断）。

**Tech Stack:** Python 3.12 · pytest（`uv run pytest`）· path2 dag 引擎

**Spec:** `docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`（本 plan 从 spec 论证，实施者两者都读）

## Global Constraints

> **本 plan 中所有项目内路径均相对 repo root。**

- 单流 detector 与现存全部 app **零改动、逐字等价**；每个 task 的提交前必须过全量回归 `uv run pytest tests/ -q`
- `DEFAULT_STREAM = None` 是兼容支点；`NodeSpec.produces_stream` 默认 `None`，现存 NodeSpec 不写一字即正确选中唯一流
- 物化键 `(id(detector), consumes_stream)` **形状不变**；**不得**把 `produces_stream` 加进键（会让同一 detector 完整扫两遍 = 1.80× 双跑）
- Detector Protocol 的 `produces` 必须放 `TYPE_CHECKING` 守卫内（runtime_checkable 会把任何显式属性纳入 isinstance 必须项，直接声明会破坏现有 conforming class）
- 注释/文档中文；frozen dataclass 修改字段一律用 `object.__setattr__`
- 测试命令：`uv run pytest <path> -x -q`；全量回归：`uv run pytest tests/ -q`
- 每个 task 的 commit 用独立 commit message（不 `git add .`，只加本 task 涉及的文件）

---

### Task 1: 协议地基 —— `stream_schema` / `DEFAULT_STREAM` / `produces` / `ref_slots`

**Files:**
- Modify: `path2/core.py`（Detector Protocol + Event 基类 + 新常量/函数）
- Test: `tests/path2/test_stream_schema.py`（新建）

**Interfaces:**
- Consumes: 无（最底层）
- Produces:
  - `DEFAULT_STREAM: Optional[str] = None`（core 层常量）
  - `stream_schema(det) -> Mapping[Optional[str], type]`（单流归一化为 `{None: det.event_cls}`；多流返回 `dict(det.produces)`；两者皆无 → ValueError）
  - `Detector` Protocol 的 `produces: ClassVar[Mapping[str, type]]`（TYPE_CHECKING 内）
  - `Event.ref_slots(self) -> Mapping[str, Tuple[Event, ...]]`（默认空）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/test_stream_schema.py
from dataclasses import dataclass
import pytest
from path2.core import DEFAULT_STREAM, Event, stream_schema


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


def test_single_flow_normalizes_to_default_stream():
    class D:
        event_cls = _E
        def detect(self, source): ...
    assert stream_schema(D()) == {DEFAULT_STREAM: _E}


def test_multi_flow_returns_produces():
    class D:
        produces = {"a": _E, "b": _E}
        def detect(self, source): ...
    assert stream_schema(D()) == {"a": _E, "b": _E}


def test_missing_both_raises():
    class D:
        def detect(self, source): ...
    with pytest.raises(ValueError, match="event_cls"):
        stream_schema(D())


def test_ref_slots_default_empty():
    assert _E().ref_slots() == {}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/test_stream_schema.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_STREAM' from 'path2.core'`

- [ ] **Step 3: 最小实现**

在 `path2/core.py` 的 Event 类内、`child_slots()` 之后加：

```python
    def ref_slots(self) -> Mapping[str, "Event | Tuple[Event, ...]"]:
        """引用槽位(翻译身份)。构成本事件引用的其他事件(跨流/同流)，
        标注阶段统一翻译成 instance_id。默认空。"""
        return {}
```

在 `Detector` Protocol 的 TYPE_CHECKING 块内加：

```python
        produces: ClassVar[Mapping[str, type]]   # ★ 多流声明;单流 detector 不写
```

在模块级（`@runtime_checkable class Detector` 之前或之后均可）加：

```python
DEFAULT_STREAM = None   # 「该 detector 的唯一流」的流名


def stream_schema(det) -> Mapping[Optional[str], type]:
    """detector → {流名: event_cls}。单流 detector 归一化成 {None: det.event_cls}。"""
    produces = getattr(det, "produces", None)
    if produces:
        return dict(produces)
    cls = getattr(det, "event_cls", None)
    if cls is None:
        raise ValueError("detector 必须声明 event_cls(单流)或 produces(多流)")
    return {DEFAULT_STREAM: cls}
```

`Mapping`、`Tuple`、`Optional`、`ClassVar` 已在 core.py 顶部 import（核实过）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/test_stream_schema.py -x -q && uv run pytest tests/path2/test_detector_protocol.py tests/path2/test_runner.py -q`
Expected: PASS（含现有 detector protocol 回归——确认 produces 在 TYPE_CHECKING 内不破坏 runtime_checkable）

- [ ] **Step 5: Commit**

```bash
git add path2/core.py tests/path2/test_stream_schema.py
git commit -m "feat(core): stream_schema/DEFAULT_STREAM 归一化 + produces 声明 + ref_slots 协议槽"
```

---

### Task 2: `run_bundle` + `_tagged`，`run()` 保留并显式拒多流

**Files:**
- Modify: `path2/runner.py`
- Test: `tests/path2/test_runner_bundle.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `DEFAULT_STREAM` / `stream_schema` / `Event`
- Produces:
  - `_tagged(detector, *source) -> Iterator[Tuple[Optional[str], Event]]`（单流裸 Event 归一化成 `(None, ev)`）
  - `run_bundle(detector, *source) -> Dict[Optional[str], List[Event]]`（声明驱动预填空流；RUNTIME_CHECKS 下按流做 end_idx 升序 + 身份去重检查；未声明流名硬错）
  - `run(detector, *source) -> Iterator[Event]`（原签名不变；多流 detector 显式 raise）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/test_runner_bundle.py
from dataclasses import dataclass
import pytest
from path2 import config
from path2.core import DEFAULT_STREAM, Event
from path2.runner import run, run_bundle


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Single:
    event_cls = _E
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield _E(start_idx=0, end_idx=0, confirm_idx=0)


class _Dual:
    produces = {"a": _E, "b": _E}
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield ("a", _E(start_idx=0, end_idx=0, confirm_idx=0))
        yield ("b", _E(start_idx=1, end_idx=1, confirm_idx=1))


def test_run_bundle_single_flow_normalizes():
    d = _Single()
    out = run_bundle(d, object())
    assert set(out) == {DEFAULT_STREAM}
    assert len(out[DEFAULT_STREAM]) == 1


def test_run_bundle_multi_flow_separates():
    d = _Dual()
    out = run_bundle(d, object())
    assert set(out) == {"a", "b"}
    assert len(out["a"]) == 1 and len(out["b"]) == 1


def test_run_bundle_unknown_stream_raises():
    class Bad:
        produces = {"a": _E}
        def detect(self, df):
            yield ("zz", _E(start_idx=0, end_idx=0, confirm_idx=0))
    with pytest.raises(ValueError, match="zz"):
        run_bundle(Bad(), object())


def test_run_multi_flow_rejected():
    with pytest.raises(ValueError, match="多流"):
        list(run(_Dual(), object()))
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/test_runner_bundle.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'run_bundle' from 'path2.runner'`

- [ ] **Step 3: 最小实现**

`path2/runner.py` 全文替换为：

```python
from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple

from path2 import config
from path2.core import DEFAULT_STREAM, Event, stream_schema


def _check_stream(events: List[Event], stream_name) -> None:
    """单条流的跨事件检查(原 run 的检查逻辑,按流调用)。"""
    last_end = None
    seen_by_id: dict[str, list[Event]] = {}
    for ev in events:
        if not isinstance(ev, Event):
            raise TypeError(f"Detector 必须 yield Event,得到 {type(ev).__name__}")
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}(流 {stream_name!r})")
        bucket = seen_by_id.setdefault(ev.instance_id, [])
        if any(prev == ev for prev in bucket):
            raise ValueError(f"instance_id 单 run 内完全重复对象:{ev.instance_id}")
        bucket.append(ev)
        last_end = ev.end_idx


def _tagged(detector, *source) -> Iterator[Tuple[Optional[str], Event]]:
    """统一线格式:单流 detector 的裸 Event 归一化成 (None, ev)。"""
    multi = bool(getattr(detector, "produces", None))
    for item in detector.detect(*source):
        yield (item if multi else (DEFAULT_STREAM, item))


def run_bundle(detector, *source) -> Dict[Optional[str], List[Event]]:
    """detector → {流名: [Event]}。声明驱动(空流也存在)。RUNTIME_CHECKS 下逐流校验。"""
    schema = stream_schema(detector)
    out: Dict[Optional[str], List[Event]] = {name: [] for name in schema}
    for name, ev in _tagged(detector, *source):
        if name not in out:
            raise ValueError(f"detector 产出未声明流名 {name!r}(声明 {set(schema)})")
        out[name].append(ev)
    if config.RUNTIME_CHECKS:
        for name, evs in out.items():
            _check_stream(evs, name)
    return out


def run(detector, *source) -> Iterator[Event]:
    """推荐的 Detector 驱动入口(单流)。多流 detector 显式拒绝,不静默拍平。"""
    if getattr(detector, "produces", None):
        raise ValueError("多流 detector 请用 run_bundle(detector, ...)(产 {流名: [Event]})")
    yield from run_bundle(detector, *source)[DEFAULT_STREAM]
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/test_runner_bundle.py tests/path2/test_runner.py -x -q && uv run pytest tests/path2/test_run_streams.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/runner.py tests/path2/test_runner_bundle.py
git commit -m "feat(runner): run_bundle/_tagged 多流入口,run 保留单流语义并显式拒多流"
```

---

### Task 3: `NodeSpec.produces_stream` + event_cls 按流反射

**Files:**
- Modify: `path2/dag/nodes.py`
- Test: `tests/path2/dag/test_nodes_multistream.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `stream_schema`；Task 2 的 `run_bundle`（本 task 只测声明，不跑引擎）
- Produces: `NodeSpec.produces_stream: Optional[str] = None`；`NodeSpec.event_cls` 从流 schema 反射（多流 node 不再依赖 `detector.event_cls`）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_nodes_multistream.py
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.nodes import NodeSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Dual:
    produces = {"a": _E, "b": _E}
    def detect(self, source): ...


class _Single:
    event_cls = _E
    def detect(self, source): ...


def test_single_flow_event_cls_unchanged():
    n = NodeSpec("x", _Single())
    assert n.event_cls is _E


def test_multi_flow_selects_stream():
    n = NodeSpec("pk", _Dual(), produces_stream="a")
    assert n.event_cls is _E


def test_multi_flow_unknown_stream_raises():
    with pytest.raises(ValueError, match="无流"):
        NodeSpec("pk", _Dual(), produces_stream="zz")


def test_substructure_produces_stream_must_be_none():
    with pytest.raises(ValueError, match="produces_stream"):
        NodeSpec("seg", event_cls=_E, produced_by="p", produces_stream="a")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_nodes_multistream.py -x -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'produces_stream'`

- [ ] **Step 3: 最小实现**

`path2/dag/nodes.py`：
- 加字段 `produces_stream: Optional[str] = None`（在 `consumes_stream` 之后）。
- `__post_init__` 的 event_cls 归一化改为：

```python
        if self.detector is not None:
            from path2.core import stream_schema
            schema = stream_schema(self.detector)
            if self.produces_stream not in schema:
                raise ValueError(
                    f"NodeSpec({self.node_id!r}): detector 无流 {self.produces_stream!r}"
                    f"(声明 {set(schema)})")
            object.__setattr__(self, "event_cls", schema[self.produces_stream])
            if self.produced_by is not None:
                raise ValueError(f"NodeSpec({self.node_id!r}): detector 与 produced_by 互斥")
```

- 子结构 node 分支（`elif self.event_cls is None`）前加守卫：`produces_stream` 必须为 None。

```python
        else:
            if self.produces_stream is not None:
                raise ValueError(
                    f"NodeSpec({self.node_id!r}): 子结构 node(无 detector)的 "
                    f"produces_stream 必须是 None")
            if self.event_cls is None:
                raise ValueError(...)  # 原有报错保留
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_nodes_multistream.py -x -q && uv run pytest tests/path2/dag/ -q`
Expected: PASS（现有 dag 测试确认单流路径逐字等价）

- [ ] **Step 5: Commit**

```bash
git add path2/dag/nodes.py tests/path2/dag/test_nodes_multistream.py
git commit -m "feat(dag): NodeSpec.produces_stream 按流反射 event_cls,单流零改动"
```

---

### Task 4: `run_streams` 兄弟一次填完（物化键不变）

**Files:**
- Modify: `path2/dag/engine.py`（`run_streams` 主循环）
- Test: `tests/path2/dag/test_engine_multistream.py`（新建）

**Interfaces:**
- Consumes: Task 2 `run_bundle`；Task 3 `produces_stream`/`stream_schema`
- Produces: `run_streams` 支持多流 detector：同一 (id(det), consumes) 的全部兄弟 node 一次填完 + 立刻标注；物化键 `(id(detector), consumes_stream)` 形状不变

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_engine_multistream.py
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Dual:
    """同一趟产两条流;产 'a' 两个、'b' 一个。计数验证只跑一次。"""
    produces = {"a": _E, "b": _E}
    def __init__(self): self.calls = 0
    def detect(self, df):
        self.calls += 1
        yield ("a", _E(start_idx=0, end_idx=0, confirm_idx=0))
        yield ("a", _E(start_idx=1, end_idx=1, confirm_idx=1))
        yield ("b", _E(start_idx=2, end_idx=2, confirm_idx=2))


def _df():
    import pandas as pd
    return pd.DataFrame({"open": [1,2,3], "high": [1,2,3], "low": [1,2,3],
                         "close": [1,2,3], "volume": [1,1,1]})


def test_multistream_both_nodes_filled():
    det = _Dual()
    spec = PatternSpec("p", nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("b", det, produces_stream="b"),
    ])
    streams = run_streams(spec, _df())
    assert len(streams["a"]) == 2 and len(streams["b"]) == 1
    assert det.calls == 1          # ★ 同一 detect 调用只跑一次
    assert all(e.instance_id is not None for e in streams["a"] + streams["b"])
    assert streams["a"][0].node_id == "a" and streams["b"][0].node_id == "b"


def test_multistream_unknown_stream_raises():
    det = _Dual()
    spec = PatternSpec("p", nodes=[
        NodeSpec("a", det, produces_stream="a"),
        NodeSpec("x", det, produces_stream="zz"),
    ])
    with pytest.raises(ValueError, match="zz"):
        run_streams(spec, _df())
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_engine_multistream.py -x -q`
Expected: FAIL — `KeyError: 'b'`（现状只物化一条流，b node 取不到）

- [ ] **Step 3: 最小实现**

`path2/dag/engine.py` 的 `run_streams` 主循环（127-138 行）改为：

```python
    siblings: dict = {}   # (id(det), consumes) -> [NodeSpec] 按声明序
    for n in spec.nodes:
        if n.detector is not None:
            siblings.setdefault((id(n.detector), n.consumes_stream), []).append(n)

    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None or nid in streams:
            continue                                # 后者:已被兄弟那一趟填好
        key = (id(node.detector), node.consumes_stream)      # ★ 键不变:detect 调用的身份
        if key not in materialized:
            from path2.runner import run_bundle
            if node.consumes_stream is None:
                materialized[key] = run_bundle(node.detector, df)
            else:
                materialized[key] = run_bundle(node.detector, streams[node.consumes_stream], df)
        bundle = materialized[key]
        for sib in siblings[key]:                   # ★ 同一调用的全部兄弟一次填完 + 立刻标注
            if sib.node_id in streams:
                continue
            if sib.produces_stream not in bundle:
                raise ValueError(f"node {sib.node_id!r}: detector 无流 {sib.produces_stream!r}")
            streams[sib.node_id] = bundle[sib.produces_stream]
            annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_engine_multistream.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS（全量回归确证单流 app 观测等价）

- [ ] **Step 5: Commit**

```bash
git add path2/dag/engine.py tests/path2/dag/test_engine_multistream.py
git commit -m "feat(engine): run_streams 兄弟一次填完,物化键不变,多流各归各 node"
```

---

### Task 5: `ref_slots` 翻译阶段（统一标注后翻译）

**Files:**
- Modify: `path2/dag/engine.py`（`run_streams` 循环后加翻译步骤）
- Test: `tests/path2/dag/test_engine_multistream.py`（追加）

**Interfaces:**
- Consumes: Task 1 `Event.ref_slots()`；Task 4 完成后的 `run_streams` 多流物化
- Produces: 所有流的 `ref_slots()` 被翻译成 `{槽名}_ref_ids`（Tuple[str, ...]，存被引用事件 instance_id）；引用事件池外对象 → ValueError

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_engine_multistream.py 追加
def test_ref_slots_translated_to_instance_ids():
    # note 事件引用 high 事件:同源两流,标注后 note.ref_slots()['anchor'] 应翻成 high 的 instance_id
    from path2.core import Event as _EventBase

    @dataclass(frozen=True)
    class _Pair(_EventBase):
        start_idx: int = 0
        end_idx: int = 0
        confirm_idx: int = 0
        anchor_refs: Tuple[Event, ...] = ()
        def ref_slots(self):
            return {"anchor": self.anchor_refs} if self.anchor_refs else {}

    class _RefDet:
        produces = {"hi": _Pair, "note": _Pair}
        def detect(self, df):
            hi = _Pair(start_idx=0, end_idx=0, confirm_idx=0)
            yield ("hi", hi)
            yield ("note", _Pair(start_idx=1, end_idx=1, confirm_idx=1, anchor_refs=(hi,)))

    det = _RefDet()
    spec = PatternSpec("p", nodes=[
        NodeSpec("hi", det, produces_stream="hi"),
        NodeSpec("note", det, produces_stream="note"),
    ])
    streams = run_streams(spec, _df())
    note = streams["note"][0]
    hi = streams["hi"][0]
    assert note.anchor_ref_ids == (hi.instance_id,)
    assert hi.instance_id is not None


def test_ref_slots_outside_pool_raises():
    @dataclass(frozen=True)
    class _E2(Event):
        start_idx: int = 0
        end_idx: int = 0
        confirm_idx: int = 0
        refs: Tuple[Event, ...] = ()
        def ref_slots(self):
            return {"r": self.refs} if self.refs else {}

    orphan = _E2(start_idx=99, end_idx=99, confirm_idx=99)   # 不在任何流里
    class _BadDet:
        produces = {"x": _E2}
        def detect(self, df):
            yield ("x", _E2(start_idx=0, end_idx=0, confirm_idx=0, refs=(orphan,)))

    spec = PatternSpec("p", nodes=[NodeSpec("x", _BadDet(), produces_stream="x")])
    with pytest.raises(ValueError, match="instance_id"):
        run_streams(spec, _df())
```

（文件顶部补 `from typing import Tuple` 与 `from path2.core import Event` 若未引入。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_engine_multistream.py -x -q`
Expected: FAIL — `AttributeError: '...' object has no attribute 'anchor_ref_ids'`（翻译阶段尚未实现）

- [ ] **Step 3: 最小实现**

`run_streams` 在兄弟循环之后、`_check_children_declarations` 之前加翻译步骤：

```python
    _translate_refs(streams)
    _check_children_declarations(spec, streams)
    return streams
```

新增模块级函数：

```python
def _translate_refs(streams) -> None:
    """统一翻译阶段:所有流标注完后,把各事件的 ref_slots() 对象引用翻译成 instance_id,
    写入 {槽名}_ref_ids。引用事件池外对象(instance_id 仍为 None)视为 detect bug,报错。"""
    for events in streams.values():
        for e in events:
            slots = e.ref_slots()
            if not slots:
                continue
            for slot_name, refs in slots.items():
                ids = []
                for ref in refs:
                    if ref.instance_id is None:
                        raise ValueError(
                            f"引用事件未被物化标注(事件池外):{type(ref).__name__} "
                            f"@bar {ref.start_idx}(ref_slots['{slot_name}'])")
                    ids.append(ref.instance_id)
                object.__setattr__(e, f"{slot_name}_ref_ids", tuple(ids))
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_engine_multistream.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/dag/engine.py tests/path2/dag/test_engine_multistream.py
git commit -m "feat(engine): ref_slots 标注后统一翻译成 instance_id,事件池外引用报错"
```

---

### Task 6: A6/A7 —— spec 校验改读 node 级 `event_cls`

**Files:**
- Modify: `path2/dag/spec.py`（`_validate_anchor` 185-204 行、`_validate_render_grid` 206-225 行）
- Test: `tests/path2/dag/test_spec_multistream.py`（新建）

**Interfaces:**
- Consumes: Task 3 让 `NodeSpec.event_cls` 已按流反射到 node 上（今天就等价）
- Produces: 两处校验不再 `detector.event_cls`，改 `node.event_cls`（多流下 detector 级 event_cls 无意义）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_spec_multistream.py
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _Pt(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    is_point = True


class _Dual:
    produces = {"a": _Pt, "b": _Pt}
    def detect(self, source): ...


def test_render_grid_price_validates_node_event_cls():
    # 多流 detector 无 event_cls 属性;若不改读 node 级,此 spec 会被误判 event_cls 缺失
    # 校验在 PatternSpec.__post_init__ 触发;不抛错即通过
    PatternSpec("p", nodes=[
        NodeSpec("a", _Dual(), produces_stream="a", render_grid="price"),
        NodeSpec("b", _Dual(), produces_stream="b"),
    ])
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_spec_multistream.py -x -q`
Expected: FAIL — 校验抛错（多流 detector 无 `event_cls` 属性）

- [ ] **Step 3: 最小实现**

`path2/dag/spec.py`：
- `_validate_anchor`（185 行）：`dst_node.detector.event_cls` → `dst_node.event_cls`
- `_validate_render_grid`（206 行）：`getattr(n.detector, "event_cls", None)` → `n.event_cls`

（校验全部在 `__post_init__` 触发，测试用构造即校验，无独立 `validate()` 方法。）

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_spec_multistream.py -x -q && uv run pytest tests/path2/dag/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/dag/spec.py tests/path2/dag/test_spec_multistream.py
git commit -m "fix(dag): spec 校验改读 node 级 event_cls,拆掉绕过 node 直读 detector"
```

---

### Task 7: 禁止「自喂」

**Files:**
- Modify: `path2/dag/spec.py`（新增校验）
- Test: `tests/path2/dag/test_spec_multistream.py`（追加）

**Interfaces:**
- Consumes: 无新依赖
- Produces: `PatternSpec` 校验拒绝「node 的 consumes_stream 指向共享同一 detector 的 node」

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_spec_multistream.py 追加
def test_self_feed_rejected():
    class _Dual2:
        produces = {"a": _Pt, "b": _Pt}
        def detect(self, source): ...

    det = _Dual2()
    with pytest.raises(ValueError, match="自喂|同一 detector"):
        PatternSpec("p", nodes=[
            NodeSpec("a", det, produces_stream="a"),
            NodeSpec("b", det, produces_stream="b", consumes_stream="a"),   # 共享同一 detector → 自喂
        ])
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_spec_multistream.py::test_self_feed_rejected -x -q`
Expected: FAIL — 当前不抛错

- [ ] **Step 3: 最小实现**

`path2/dag/spec.py` 新增校验（挂在现有校验链，先 grep 现有入口命名，如 `_validate` / `validate`，按现有模式追加）：

```python
    def _validate_no_self_feed(self) -> None:
        """禁止「自喂」:node X 的 consumes_stream 指向与 X 共享同一 detector 的 node。
        多流下最可能的误写是让 bo 节点 consumes_stream='pk' 以为读同趟 pk 流;
        实际那是 (id(det),'pk') 的第二次 detect 调用,白跑一整趟。"""
        det_of = {}
        for n in self.nodes:
            if n.detector is not None:
                det_of.setdefault(id(n.detector), []).append(n.node_id)
        for n in self.nodes:
            if n.consumes_stream is not None and n.detector is not None:
                if n.consumes_stream in det_of.get(id(n.detector), []):
                    raise ValueError(
                        f"NodeSpec({n.node_id!r}): consumes_stream={n.consumes_stream!r} "
                        f"指向共享同一 detector 的 node(自喂;会触发第二次 detect 调用)")
```

在现有校验入口（grep 到的 `validate` 或 `__post_init__` 调用链）加 `self._validate_no_self_feed()`。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_spec_multistream.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS（确认现存 6 个 app 无人自喂，零误杀）

- [ ] **Step 5: Commit**

```bash
git add path2/dag/spec.py tests/path2/dag/test_spec_multistream.py
git commit -m "feat(dag): 禁止 consumes_stream 指向共享同一 detector 的 node(自喂)"
```

---

### Task 8: `GateFailure.stream` 字段

**Files:**
- Modify: `path2/dag/gate_failure.py`
- Test: `tests/path2/dag/test_gate_failure_stream.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `GateFailure.stream: Optional[str] = None`（追加带默认值字段,既有 kwargs 构造点全兼容,先例 `code_location`）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_gate_failure_stream.py
from path2.dag.gate_failure import GateFailure
from path2.dag.gate_failure import MeasuredKindAware


def _gf(**kw):
    base = dict(
        failure_event_window=(0, 0), start_idx=0, gate_idx=0, anchor_bar=0,
        gate_name="g", measured=MeasuredKindAware(kind="count", value=1, label="x"),
        threshold=1, op=None, threshold_param=None,
    )
    base.update(kw)
    return GateFailure(**base)


def test_stream_default_none():
    assert _gf().stream is None       # 既有构造点不传 stream → 兼容


def test_stream_explicit():
    assert _gf(stream="pk").stream == "pk"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_gate_failure_stream.py -x -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'stream'`

- [ ] **Step 3: 最小实现**

`path2/dag/gate_failure.py` 在 `node_id` 字段附近加（带默认值,沿用「追加字段,带默认值」既有注释做法）:

```python
    stream: Optional[str] = None   # 所属命名流(gate_collector 路由用;单流恒 None)
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_gate_failure_stream.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/dag/gate_failure.py tests/path2/dag/test_gate_failure_stream.py
git commit -m "feat(dag): GateFailure.stream 字段(带默认值,既有构造点兼容)"
```

---

### Task 9: `gate_collector` 路由表（`(detector, 流名) → node_id`）

**Files:**
- Modify: `path2_web/gate_collector.py`
- Test: `tests/path2_web/test_gate_collector_multistream.py`（新建）

**Interfaces:**
- Consumes: Task 8 `GateFailure.stream`；Task 3 `produces_stream`；Task 1 `stream_schema`
- Produces: `attach_and_collect` 从 per-detector wrapper 改为 `(detector, 流名) → node_id` 路由表;单流路径逐字等价;同一流多 node 绑定挂雷;未绑流挂载期报错

- [ ] **Step 1: 写失败测试**

```python
# tests/path2_web/test_gate_collector_multistream.py
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.gate_collector import GateCollector, attach_and_collect, detach


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


def _gf(stream=None):
    return GateFailure(
        failure_event_window=(0, 0), start_idx=0, gate_idx=0, anchor_bar=0,
        gate_name="g", measured=MeasuredKindAware(kind="count", value=1, label="x"),
        threshold=1, op=None, threshold_param=None, stream=stream)


def test_single_flow_node_id_injected():
    class S:
        event_cls = _E
        def detect(self, source): ...
    det = S()
    spec = PatternSpec("p", nodes=[NodeSpec("bo", det)])
    collector = attach_and_collect(spec)
    det.on_gate(_gf())                       # 单流 gf.stream=None
    detach(spec)
    assert [f.node_id for f in collector.failures] == ["bo"]


def test_multi_flow_routes_by_stream():
    class D:
        produces = {"bo": _E, "pk": _E}
        def __init__(self): self.on_gate = None
        def detect(self, source): ...
    det = D()
    spec = PatternSpec("p", nodes=[
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk"),
    ])
    collector = attach_and_collect(spec)
    det.on_gate(_gf(stream="pk"))            # ★ pk 流的 gate → pk node
    det.on_gate(_gf(stream="bo"))            # bo 流的 gate → bo node
    detach(spec)
    assert [f.node_id for f in collector.failures] == ["pk", "bo"]
    assert collector.failures[0].stream == "pk"


def test_unbound_stream_attach_raises():
    class D:
        produces = {"bo": _E, "pk": _E}
        def detect(self, source): ...
    det = D()
    spec = PatternSpec("p", nodes=[NodeSpec("bo", det, produces_stream="bo")])
    with pytest.raises(ValueError, match="pk"):
        attach_and_collect(spec)             # pk 声明了但无 node 绑定 + 挂 collector → 报错
    detach(spec)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_web/test_gate_collector_multistream.py -x -q`
Expected: FAIL — `test_multi_flow_routes_by_stream` 挂雷（多 node 共享 detector 时现状 `_boom` raise）

- [ ] **Step 3: 最小实现**

`path2_web/gate_collector.py` 的 `attach_and_collect` 重写（保留 `GateCollector` / `detach` 不变）:

```python
def attach_and_collect(spec) -> GateCollector:
    """遍历 spec.nodes,给每个 detector 挂 per-call wrapper:收到 GateFailure 后按
    (detector, 流名) 路由表注入 node_id 再进 collector。单流路径与旧 per-node wrapper 逐字相同。

    挂雷收窄为「同一条流被 ≥2 node 绑定」(原「同一 detector 被 ≥2 node 引用」)。
    挂载期校验:诊断路径(挂 collector)下,声明但未被任何 node 绑定的流 → 报错,
    防「gf 无处归属」静默丢失。"""
    from path2.core import stream_schema
    collector = GateCollector()
    routes: dict[int, dict[Optional[str], list[str]]] = {}
    for node in spec.nodes:
        if node.detector is None:
            continue
        routes.setdefault(id(node.detector), {}).setdefault(
            node.produces_stream, []).append(node.node_id)
    for det_id, by_stream in routes.items():
        unbound = set(stream_schema(_det_of(spec, det_id))) - set(by_stream)
        if unbound:
            raise ValueError(
                f"detector 声明流未被任何 node 绑定,其 gate failure 将无处归属:"
                f"{sorted(unbound)};请为它建 node 或改用不产 gf 的配置")
    def make_route(det_id):
        def _route(gf: GateFailure) -> None:
            nids = routes[det_id].get(gf.stream)
            if not nids:
                if config.RUNTIME_CHECKS:
                    raise ValueError(f"gate failure 流 {gf.stream!r} 无绑定 node")
                return
            if len(nids) > 1:
                raise RuntimeError(
                    f"流 {gf.stream!r} 被 {len(nids)} 个 node 绑定,gate failure 归属无真值;"
                    f"请每流一 node")
            collector.add(dataclasses.replace(gf, node_id=nids[0]))
        return _route
    seen: set[int] = set()
    for node in spec.nodes:
        if node.detector is None:
            continue
        det_id = id(node.detector)
        if det_id not in seen:
            seen.add(det_id)
            node.detector.on_gate = make_route(det_id)
    return collector
```

> 需 `_det_of(spec, det_id)` 辅助:按 det_id 找回一个 detector 实例(用于 stream_schema)。实现可在 routes 构造时顺带存 `first_det[det_id] = node.detector`。`config` / `dataclasses` / `Optional` 已在 gate_collector 作用域可及(核实后补 import)。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2_web/test_gate_collector_multistream.py -x -q && uv run pytest tests/path2_web/ tests/path2/test_run_streams.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/gate_collector.py tests/path2_web/test_gate_collector_multistream.py
git commit -m "feat(gate_collector): (detector,流名)→node_id 路由表,挂雷收窄为同流多 node,未绑流挂载期报错"
```

---

### Task 10: `NodeSpec.solve` + `bound_ids` 判据

**Files:**
- Modify: `path2/dag/nodes.py`（加字段）、`path2/dag/_solve.py`（bound_ids 判据）
- Test: `tests/path2/dag/test_solve_flag.py`（新建）

**Interfaces:**
- Consumes: Task 3 已让 `produces_stream` 生效
- Produces: `NodeSpec.solve: bool = True`;`bound_ids` 加 `and nodes[nid].solve`（零边 pattern 的孤立 node 可声明 `solve=False` 退出求解）

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/dag/test_solve_flag.py
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag._solve import compile_plan
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _D:
    event_cls = _E
    def detect(self, source): ...


def test_solve_false_excluded_from_bound():
    det = _D()
    spec = PatternSpec("p", nodes=[
        NodeSpec("bo", det),
        NodeSpec("pk", det, solve=False),     # 零边 pattern:pk 声明不参与求解
    ])
    plan = compile_plan(spec)
    comps = [set(w.comp) for w in plan.wcc_plans]
    assert any("bo" in c for c in comps)
    assert all("pk" not in c for c in comps)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_solve_flag.py -x -q`
Expected: FAIL — `TypeError: NodeSpec() got an unexpected keyword argument 'solve'`

- [ ] **Step 3: 最小实现**

`path2/dag/nodes.py` 加字段:

```python
    solve: bool = True     # 是否参与求解匹配。False = 只显示不参与匹配(零边 pattern 的孤立 node 用)
```

`path2/dag/_solve.py` bound_ids 列表推导加一个条件（在 `nodes[nid].detector is not None` 之后）:

```python
                and nodes[nid].detector is not None      # 结构性守卫:子结构 node 无候选池
                and nodes[nid].solve                     # ★ solve=False:只显示不参与匹配
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/dag/test_solve_flag.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS（5 个 app 的 bo 节点 `solve=True` 默认,行为不变）

- [ ] **Step 5: Commit**

```bash
git add path2/dag/nodes.py path2/dag/_solve.py tests/path2/dag/test_solve_flag.py
git commit -m "feat(dag): NodeSpec.solve 声明只显示不参与匹配,bound_ids 判据加 gate"
```

---

### Task 11: B1 —— `debug_enabled_nodes` 改读 node 级 `event_cls`

**Files:**
- Modify: `path2_web/serialize.py`（`debug_enabled_nodes` 判据 275-282 行）
- Test: `tests/path2_web/test_serialize_multistream.py`（新建）

**Interfaces:**
- Consumes: Task 3 让 `NodeSpec.event_cls` 已反射到 node 上
- Produces: 多流 detector 的 node 不静默掉出 debug 列表

- [ ] **Step 1: 写失败测试**

```python
# tests/path2_web/test_serialize_multistream.py
from dataclasses import dataclass
from path2.core import Event
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.serialize import serialize_pattern


@dataclass(frozen=True)
class _E(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _Multi:
    produces = {"a": _E, "b": _E}
    has_debug_hooks = True
    def detect(self, source): ...


def test_multistream_node_in_debug_list():
    spec = PatternSpec("p", nodes=[
        NodeSpec("a", _Multi(), produces_stream="a"),
        NodeSpec("b", _Multi(), produces_stream="b"),
    ])
    assert "a" in serialize_pattern(spec)["debug_enabled_nodes"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_web/test_serialize_multistream.py -x -q`
Expected: FAIL — 多流 detector 无 `event_cls` 属性 → 掉出列表

- [ ] **Step 3: 最小实现**

`path2_web/serialize.py` 判据改:

```python
        if getattr(det_cls, "has_debug_hooks", False) and n.event_cls is not None:
```

（删掉 `hasattr(n.detector, "event_cls")`,改 `n.event_cls is not None`——Task 3 已把 event_cls 反射到 node 上。）

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2_web/test_serialize_multistream.py -x -q && uv run pytest tests/path2_web/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize_multistream.py
git commit -m "fix(serialize): debug_enabled_nodes 改读 node 级 event_cls,多流 node 不静默掉出"
```

---

### 延期项：A9 —— tune-gates 工具链同步（本期不实施）

**决策（2026-09-01 用户指示）**:本 plan **不实施** A9（`.claude/skills/tune-gates/multivar_core.py` 同步）。原因:另一 worktree 正在优化 tune-gates,双写会错乱。

**后果（明确接受,不是遗漏）**:多流引擎落地后,`multivar_core.py` 仍用旧 `run_streams` 复刻 + 旧「同一 detector 实例硬拒」,意味着:
- 多流兄弟共享 detector 会被 `multivar_core` 硬拒(调参工具认为非法);
- 若绕过硬拒,反转循环会算出与生产不同的流(静默口径分裂)。

**缓解**:本期无任何多流**真实 app**(pk 应用层延后,见研究目录待办),多流能力只被测试 fixture 消费——`multivar_core` 的旧逻辑对单流 app 行为不变,缺口在「无消费者」状态下无实际影响。

**补上时机(必须)**:满足以下任一即须先补 A9 再启用多流 app——
1. tune-gates 优化 worktree 合并后;或
2. 开始 pk 应用层(多流第一个真实消费者)之前。

**本延期对应的 spec 位置**:`docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md` §5.A A9、§10 风险 3。实施 A9 时的完整改法保留在 `docs/research/2026-08-31_pk-display-three-approaches/方案3_多stream引擎扩展.md` §3.9 与本段之下的原设计(见 git history,Task 12 的完整 TDD 步骤)。

---

### Task 12: 端到端多流 detector 样例（验收）

**Files:**
- Create: `tests/path2/dogfood_multistream.py`（多流 fixture detector）
- Create: `tests/path2/test_multistream_end_to_end.py`
- Modify: `tests/path2/fixtures/`（如需注册 fixture）

**Interfaces:**
- Consumes: 全部前置 Task
- Produces: 一个可复用的多流 detector 样例 + 端到端验收测试（spec §12 验收标准 2/3）

- [ ] **Step 1: 写 fixture + 失败测试**

```python
# tests/path2/dogfood_multistream.py
"""多流 fixture detector:同一趟产 'range'(区间)+ 'note'(点,引用 range)。"""
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple
import pandas as pd
from path2.core import Event


@dataclass(frozen=True)
class RangeEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


@dataclass(frozen=True)
class NoteEvent(Event):
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0
    anchor_refs: Tuple[Event, ...] = ()

    def ref_slots(self):
        return {"anchor": self.anchor_refs} if self.anchor_refs else {}


class RangeNoteDetector:
    """每 span 根产一个 range(该窗 high 最高点),随后 1 根内产 note 引用它。
    窗口不足时 emit gate(stream='range')。"""
    produces = {"range": RangeEvent, "note": NoteEvent}

    def __init__(self, span: int = 3, min_bars: int = 5):
        self.span, self.min_bars = span, min_bars
        self.on_gate = None

    def detect(self, df: pd.DataFrame) -> Iterator[Tuple[str, Event]]:
        highs = df["high"].to_numpy()
        for i in range(len(df)):
            if i < self.min_bars:
                self._gate("warmup", i, "窗口不足")
                continue
            if i % self.span == 0:
                lo = max(0, i - self.span)
                j = int(highs[lo:i + 1].argmax()) + lo
                rng = RangeEvent(start_idx=lo, end_idx=i, confirm_idx=i)
                yield ("range", rng)
                if i + 1 < len(df):
                    yield ("note", NoteEvent(start_idx=i + 1, end_idx=i + 1,
                                             confirm_idx=i + 1, anchor_refs=(rng,)))

    def _gate(self, gate_name, i, label):
        if self.on_gate is not None:
            from path2.dag.gate_failure import GateFailure, MeasuredKindAware
            self.on_gate(GateFailure(
                failure_event_window=(i, i), start_idx=i, gate_idx=i, anchor_bar=i,
                gate_name=gate_name, measured=MeasuredKindAware(kind="count", value=1, label=label),
                threshold=1, op=None, threshold_param=None, stream="range"))
```

```python
# tests/path2/test_multistream_end_to_end.py
"""端到端验收:多流 + ref_slots 翻译 + on_gate 归属 + solve=False。"""
from dataclasses import dataclass
import pandas as pd
import pytest
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.gate_collector import attach_and_collect, detach
from tests.path2.dogfood_multistream import RangeNoteDetector


def _df():
    n = 15
    base = list(range(1, n + 1))
    return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                         "low": [x - 0.5 for x in base], "close": base,
                         "volume": [1] * n})


def test_end_to_end_streams_refs_solve():
    det = RangeNoteDetector(span=3, min_bars=5)
    spec = PatternSpec("p", nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])
    streams = run_streams(spec, _df())
    # 两流各归各、ref 翻译成真 instance_id
    ranges, notes = streams["range"], streams["note"]
    assert ranges and notes
    assert notes[0].anchor_ref_ids == (ranges[0].instance_id,)
    # solve=False 的 note 不出现在 matches
    res = analyze(spec, _df())
    assert all("note" not in m.node_index for m in res.matches)


def test_end_to_end_gate_routes_to_range_node():
    det = RangeNoteDetector(span=3, min_bars=5)
    spec = PatternSpec("p", nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])
    collector = attach_and_collect(spec)
    _ = run_streams(spec, _df())          # detect 期 warmup 不足会 emit gate
    detach(spec)
    assert collector.failures
    assert all(f.node_id == "range" for f in collector.failures)
    assert all(f.stream == "range" for f in collector.failures)
```

（文件顶部补 `from path2.dag.engine import analyze, run_streams`。）

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/test_multistream_end_to_end.py -x -q`
Expected: FAIL — 依赖的协议未全部就位（按当前已完成的 Task 逐个对齐,本轮至少 `anchor_ref_ids` 未翻译/`solve` 未生效之一失败）

- [ ] **Step 3: 最小实现**

本 task 无新实现——它是「用已落地协议组装验收样例」。若某个断言失败指向协议 bug,回修对应 Task 的实现（TDD 收敛）。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `uv run pytest tests/path2/test_multistream_end_to_end.py -x -q && uv run pytest tests/ -q`
Expected: 端到端 PASS + 全量回归零回归

- [ ] **Step 5: Commit**

```bash
git add tests/path2/dogfood_multistream.py tests/path2/test_multistream_end_to_end.py
git commit -m "test(multistream): 端到端验收样例——多流 + ref_slots 翻译 + gate 归属 + solve"
```

---

### Task 13: 更新 authoring skills（收尾,代码稳定后）

**Files:**
- Modify: `.claude/skills/authoring-path2-detector/SKILL.md`
- Modify: `.claude/skills/authoring-path2-app/SKILL.md`

**Interfaces:**
- Consumes: 全部前置 Task 落地后的真实 API
- Produces: 两个 skill 补充「多流」章节,示例与实现一致

- [ ] **Step 1: 读现状 + 列补充点**

Read: `.claude/skills/authoring-path2-detector/SKILL.md` 与 `.claude/skills/authoring-path2-app/SKILL.md`。
补充点（基于本 plan 落地的真实 API）:
- detector:多流写法(`produces = {流名: event_cls}` + `yield (流名, event)`)、`ref_slots()` 引用槽位、何时用多流 vs 拆独立 detector(四格分类的 4b 格判据)
- app:`produces_stream` 声明、多流节点的拓扑语义(一 node 一流)、`NodeSpec.solve=False`(只显示不参与匹配)、多流 node 的 on_gate 归属(gate 按流路由)

- [ ] **Step 2: 补 detector skill**

在 `authoring-path2-detector` 的对应章节追加多流小节,示例代码**逐字引用**本 plan Task 13 的 `RangeNoteDetector`(或实现后真实存在的多流 detector),确保示例可运行。标注「多流 detector 单流入口 `run()` 会拒绝,用 `run_bundle()`」。

- [ ] **Step 3: 补 app skill**

在 `authoring-path2-app` 的节点声明章节追加 `produces_stream` 与 `solve` 的用法,含「零边 pattern 加孤立显示 node 必须 `solve=False`」的警示(否则 `serialize` KeyError)。

- [ ] **Step 4: 验证 skill 示例**

Run: `uv run pytest tests/path2/test_multistream_end_to_end.py -x -q`
Expected: PASS(确认 skill 引用的 API 与实现一致;skill 是文档,验证 = 示例所指 API 可运行)

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/authoring-path2-detector/SKILL.md .claude/skills/authoring-path2-app/SKILL.md
git commit -m "docs(skills): authoring-path2-{detector,app} 补多流/ref_slots/solve 章节,示例与实现一致"
```

