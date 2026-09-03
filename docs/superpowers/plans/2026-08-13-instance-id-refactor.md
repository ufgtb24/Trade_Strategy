# event_id 全面实例化重构实施计划(instance_id 契约)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**本 plan 中所有项目内路径均相对 repo root。**

**Goal:** 消灭 event_id 与 class_id 字符串体系,事件标识统一为 instance_id = (node_id, span, 流序) 编码,引用协议全实例化。

**Architecture:** 引擎物化标注先行(Event 类改字段 + run_streams 出口标注,编号前置引擎),dag 内部消费点迁移(match_id 取代 match 的 event_id),web 纯投影层重写(serialize/diagnose/eval_runner),前端类型与全部消费点实例化(focusEvent 单入口、selectedInstanceId、band 按 node),最后全量回归 + 真实数据验收。不兼容旧 scan 文件。

**Tech Stack:** Python(path2 引擎/path2_web)/ Vue3 + TS(前端)/ pytest / vitest / vue-tsc / vite

**Spec:** docs/superpowers/specs/2026-08-13-instance-id-refactor.md(本 plan 的实施契约唯一出处;设计讨论背景见 docs/research/2026-08-13_instance-id-design.md)

## Global Constraints

1. **契约形态**(spec §1):事件行字段 = `instance_id`、`node_id`、`instance_idx` + 属性平铺;删除 event_id/source_tag/instance_key/class_id。instance_id = `span_id(node_id, start, end) + "#" + str(instance_idx)`,恒输出(单实例 `#0`)。
2. **编号同源**:instance_idx 由引擎物化标注唯一产出(桶 = (node_id, start_idx, end_idx),组内流序);serialize/diagnose/eval_runner 一律读标注字段,禁止各自编号(_InstanceIndexer 删除)。
3. **引用协议全实例化**:match.node_index 值 = instance_id 字符串;match.children / child_refs = instance_id 列表;无身份级引用残留。
4. **match 标识**:PatternMatch 删除 event_id,新增 `match_id`;reify 构造 `f"{pattern_id}@{start}-{end}#{node_bits}"`,node_bits 用 instance_id;碰撞消歧按 match_id,后缀规则不变。
5. **class_id 消灭**(spec §1a):注册表/`__init_subclass__` 强制声明删除;类型用 Python 类(event_cls/isinstance/`__name__`/is_point);序列化无 class 字段;summarize 按 node_id 统计;样式配置键 = node_id。
6. **前端**:focusEvent 单入口 `focusEvent(instanceId: string)`;selectedEventId/focusedEventId/focusedEventKey 统一为 selectedInstanceId/focusedInstanceId;band 分组键 = node_id;无 event_key 拼接与解析。
7. **测试先 RED 后 GREEN**;既有断言修改(契约升级必然同步)先复核推演,禁止盲改断言语义;全中文注释/UI;入口脚本不使用 argparse(本 plan 无新入口)。
8. **执行纪律**:每 task 跑绿再 commit 到实施分支;BLOCKED 或 plan 文本与实际冲突按 subagent-driven 流程处理,无法裁决才停下汇报。

---

### Task 1: 引擎 Event 类改造 + annotate_instances 物化标注

**Files:**
- Modify: `path2/core.py`(Event 类 :43-125)
- Modify: `path2/dag/engine.py`(`run_streams` :88-110 出口 + 新增 `annotate_instances`)
- Test: `tests/path2/test_core.py`、`tests/path2/dag/test_engine.py`(以实际文件名为准,grep 定位)

**Interfaces:**
- Consumes: 现状 `Event`(event_id kw_only 字段 + `__post_init__` 自动推导 + `_CLASS_ID_REGISTRY`/`__init_subclass__` 强制 class_id);`span_id(kind, start, end)`(core.py:32)
- Produces: `Event.node_id: Optional[str]` / `instance_idx: int` / `instance_id: Optional[str]`(kw_only,默认 None/0/None);`annotate_instances(streams: dict, spec) -> None`(engine.py 导出);Task 2/3/5 全部依赖

- [ ] **Step 1: 写失败测试(标注语义)**

在 engine 测试文件新增:

```python
def test_annotate_instances_assigns_ids():
    """物化标注:流内事件注入 node_id/instance_idx/instance_id,单实例恒 #0。"""
    from path2.dag.engine import annotate_instances
    from path2.dag.spec import PatternSpec
    # 用既有 engine 测试的 spec 构造(grep 复用);若最小化:
    spec = PatternSpec(nodes=[...], edges=())   # 按既有 fixture 构造
    ev = Ev(start_idx=5, end_idx=5, confirm_idx=5)
    streams = {"tb": [ev]}
    annotate_instances(streams, spec)
    assert ev.node_id == "tb"
    assert ev.instance_idx == 0
    assert ev.instance_id == "tb_5#0"

def test_annotate_instances_multi_instance_same_span():
    """同 node 同 span 多实例:流序编号 #0/#1(APCX 形态)。"""
    e0 = Ev(start_idx=293, end_idx=293, confirm_idx=293)
    e1 = Ev(start_idx=293, end_idx=293, confirm_idx=293)
    annotate_instances({"tb": [e0, e1]}, spec)
    assert e0.instance_id == "tb_293#0"
    assert e1.instance_id == "tb_293#1"

def test_annotate_instances_interval_span():
    """区间事件:instance_id = node_start_end#idx。"""
    e = Ev(start_idx=282, end_idx=289, confirm_idx=289)
    annotate_instances({"burst": [e]}, spec)
    assert e.instance_id == "burst_282_289#0"

def test_annotate_instances_nested_child_inherits_node():
    """嵌套 child(不在流中)继承容器事件的 node_id,同桶计数。"""
    child = Ev(start_idx=1, end_idx=3, confirm_idx=3)
    parent = ContainerEv(start_idx=0, end_idx=5, confirm_idx=5, members=(child,))
    annotate_instances({"tb": [parent]}, spec)
    assert child.node_id == "tb"
    assert child.instance_id == "tb_1_3#0"
```

(fixture 事件类用测试内定义的 Ev 子类;ContainerEv 带 child_slots 返回 {"members": members}。若既有测试已有同构 fixture,grep 复用。)

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `uv run pytest tests/path2/dag/test_engine.py -q -k annotate`
Expected: FAIL(annotate_instances 未定义)

- [ ] **Step 3: 实现 Event 类改造**

`path2/core.py`:删除 `_CLASS_ID_REGISTRY`、`__init_subclass__`(整段)、`class_id` ClassVar;Event 字段改:

```python
@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。

    子类契约:必须 @dataclass(frozen=True);若自定义 __post_init__,
    必须调用 super().__post_init__()。

    confirm_idx: (保留现状 docstring 主体,不动)

    node_id / instance_idx / instance_id:物化标注(engine.annotate_instances)
    注入。detector 构造阶段为 None/0/None;物化后恒非 None。instance_id =
    span_id(node_id, start, end) + "#" + str(instance_idx),桶 (node_id, start,
    end) 内流序从 0 起——instance_id 契约唯一出处,禁止各处自行构造。
    """
    node_id: Optional[str] = field(kw_only=True, default=None)
    instance_idx: int = field(kw_only=True, default=0)
    instance_id: Optional[str] = field(kw_only=True, default=None)
    start_idx: int
    end_idx: int
    confirm_idx: int = field(kw_only=True)

    is_point: ClassVar[bool] = False

    def __post_init__(self) -> None:
        # (删除 event_id 自动推导块;其余校验逻辑保留现状)
        if not config.RUNTIME_CHECKS:
            return
        # ...(保留 start_idx/end_idx/confirm_idx/NaN 校验,原文不动)
```

`span_id` 保留原文不动(docstring 的 kind 说明改为「kind 取 node_id」)。

- [ ] **Step 4: 实现 annotate_instances + run_streams 出口接线**

`path2/dag/engine.py` 新增(置于 `assign_auto_source_tags` 附近;本 task 不删 assign_auto_source_tags,Task 2 删):

```python
def annotate_instances(streams, spec) -> None:
    """物化标注(instance_id 契约唯一出处):给每条流的事件注入 node_id/
    instance_idx/instance_id。桶 = (node_id, start_idx, end_idx),组内按流序
    从 0 起;嵌套 child(如 tb.segments,不在任何流)递归继承容器事件的
    node_id、用同一桶计数补标。共享 detector 多 node:首现 node 获胜
    (已标注跳过)。"""
    counts: dict = {}   # (node_id, start, end) -> 已分配数

    def _annotate(e, nid: str) -> None:
        if e.node_id is not None:
            return
        key = (nid, e.start_idx, e.end_idx)
        idx = counts.get(key, 0)
        object.__setattr__(e, "node_id", nid)
        object.__setattr__(e, "instance_idx", idx)
        object.__setattr__(e, "instance_id",
                           f"{span_id(nid, e.start_idx, e.end_idx)}#{idx}")
        counts[key] = idx + 1

    for nid, events in streams.items():
        for e in events:
            _annotate(e, nid)
    for nid, events in streams.items():       # 递归补标嵌套 child
        for e in events:
            for slot in e.child_slots().values():
                members = slot if isinstance(slot, tuple) else (slot,)
                for c in members:
                    _annotate(c, nid)
```

`run_streams` 末尾:`_check_children_declarations(spec, streams)` 之后加 `annotate_instances(streams, spec)`(diagnose 与 analyze 共用 run_streams,标注自动双覆盖)。

- [ ] **Step 5: 跑测试确认 PASS + 本 task 范围回归**

Run: `uv run pytest tests/path2/dag/test_engine.py -q -k annotate` 与 `uv run pytest tests/path2/ -q -k "engine or core"`

Expected: 新测试 PASS。**注意**:Event 删除 event_id/class_id 后,大量引擎测试会红(构造事件传 event_id= 参数、断言 event_id)——本 task 只修 test_engine 与 test_core 内的相关行(参数删除、断言改 instance_id 或 node_id),其余文件的红留给 Task 2/3 修。若 test_core/test_engine 外有连带 import 错误,记录到报告。

- [ ] **Step 6: Commit**

```bash
git add path2/core.py path2/dag/engine.py tests/path2/test_core.py tests/path2/dag/test_engine.py
git commit -m "feat: Event 标识改造(node_id/instance_idx/instance_id)+ annotate_instances 物化标注"
```

---

### Task 2: atoms + stdlib 清理(source_tag/event_id 传参/class_id 声明消灭)

**Files:**
- Modify: `path2/atoms/trend.py`、`throwback.py`、`throwback_v0.py`、`throwback_v1.py`、`throwback_v3.py`、`breakout.py`、`platform.py`、`distribution.py`、其余 atoms
- Modify: `path2/stdlib/_ids.py`、`templates.py`
- Modify: `path2/dag/engine.py`(删除 `assign_auto_source_tags` 与其调用)
- Test: `tests/path2/atoms/`、`tests/path2/stdlib/`

**Interfaces:**
- Consumes: Task 1 的 Event 新字段(无 event_id 参数可传)
- Produces: atoms 零 source_tag/event_id/class_id 引用;engine 无 assign_auto_source_tags;后续 task 的干净基线

- [ ] **Step 1: 全量定位残留**

Run: `grep -rn "event_id=\|source_tag\|class_id" path2/atoms path2/stdlib path2/dag/engine.py | grep -v test`
Expected: 登记全部残留点到本 task 报告(trend.py 的 source_tag 参数与 `span_id(self.source_tag or ...)` 构造、各 throwback 的显式 event_id 传参、templates/_ids 的复合 id 构造等)。

- [ ] **Step 2: 写失败测试(构造不再需要/允许旧参数)**

在 atoms 测试中把「构造事件带 source_tag/event_id 参数」的既有用例改为新形态后跑红验证(至少一处):

```python
def test_trend_event_has_no_source_tag_param():
    """trend detector 不再接受 source_tag;事件构造不再传 event_id。"""
    det = TrendSegmentDetector(eps=0.01)          # 按现状构造签名删 source_tag 后
    events = list(det.detect(df))                  # 或 detect(stream, df),按现状
    for e in events:
        assert e.instance_id is None               # detector 阶段未标注(物化后才有)
        assert e.node_id is None
```

Run: `uv run pytest tests/path2/atoms/ -q -k "source_tag"`
Expected: FAIL(TrendSegmentDetector 仍收 source_tag)

- [ ] **Step 3: 迁移实现**

逐文件:
- `trend.py`:删除 `source_tag` 构造参数与 `self.source_tag` 属性;`event_id=span_id(self.source_tag or self.event_cls.class_id, ...)` 构造行删除(Event 已无 event_id 参数);docstring 同步。
- `throwback*/breakout/...`:删除显式 `event_id=...` 传参(逃生舱用法全删);若有 `class_id` ClassVar 声明删除。
- `stdlib/_ids.py`/`templates.py`:复合 id 构造(event_id 显式传参)删除;`span_id` 引用保留(core.py 的)。
- `engine.py`:删除 `assign_auto_source_tags` 函数与 `run_streams` 里的调用行。

- [ ] **Step 4: 跑绿 + atoms 全量回归**

Run: `uv run pytest tests/path2/atoms/ tests/path2/stdlib/ -q`
Expected: 全绿(既有断言凡引用 event_id/source_tag/class_id 的,先复核再按新语义改:构造断言 → node_id/instance_id 为 None 或删除;显示断言 → `__name__`)。

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/ path2/stdlib/ path2/dag/engine.py tests/path2/atoms/ tests/path2/stdlib/
git commit -m "refactor: atoms/stdlib 消灭 source_tag 与 event_id/class_id 引用"
```

---

### Task 3: dag 内部迁移(match_id + 求解/物化/校验/诊断消费点)

**Files:**
- Modify: `path2/dag/result.py`(PatternMatch :49-64、AnalysisResult 校验 :85-88)
- Modify: `path2/dag/_reify.py`(node_bits/match 构造 :73-80)
- Modify: `path2/dag/engine.py`(`_node_bits_of` :113-116、analyze 消歧 :135-153)
- Modify: `path2/dag/_solve.py`(:285 多实例判定)
- Modify: `path2/dag/edges.py`、`diagnose.py`、`spec.py`、`runner.py`(event_id/class_id 残留)
- Test: `tests/path2/dag/`

**Interfaces:**
- Consumes: Task 1 的 instance_id/annotate_instances;Task 2 的干净 atoms
- Produces: `PatternMatch.match_id: str`;analyze 产物含标注后事件;dag 层零 event_id/class_id/source_tag 引用;Task 4/5 依赖

- [ ] **Step 1: 写失败测试(match_id)**

在 result/reify 测试文件新增:

```python
def test_match_id_uses_instance_ids():
    """match_id 的 node_bits 段用 instance_id(标注后),不再用 event_id。"""
    # 构造:跑 engine.analyze 最小 spec(复用既有 dag 测试 fixture)
    res = analyze(spec, df, params)
    for m in res.matches:
        assert hasattr(m, "match_id") and m.match_id
        assert not hasattr(m, "event_id")          # Event 无此字段,PatternMatch 也不该有
        bits = {e.instance_id for e in m.node_index.values()}
        for b in bits:
            assert b is not None and "#" in b      # instance_id 恒带 #idx
```

Run: `uv run pytest tests/path2/dag/ -q -k match_id`
Expected: FAIL(PatternMatch 仍继承 event_id、无 match_id)

- [ ] **Step 2: 迁移实现**

`result.py`:
```python
@dataclass(frozen=True)
class PatternMatch(Event):
    """一次完整命中。继承 Event(start_idx/end_idx/confirm_idx)。match_id 为
    match 唯一键(instance_id 契约:bits 段用各 node 实例键)。"""
    match_id: str = ""
    pattern_id: str = ""
    node_index: Optional[Mapping[str, Event]] = None
    children: Tuple[Event, ...] = ()
    predicate_trace: Optional[PredicateTrace] = None
    # __post_init__:super().__post_init__() 后保留展平不变式校验(原文不动)
```
AnalysisResult 校验(:85-88)改:
```python
        # instance_id 契约:物化标注后 instance_id 唯一;重复 = 标注 bug 或
        # detector 重复 evaluate 的信号。
        for i, a in enumerate(self.events):
            for b in self.events[i + 1:]:
                assert not (a.instance_id == b.instance_id and a == b), \
                    f"res.events 同 instance_id 完全重复对象: {a.instance_id}"
```

`_reify.py`:
```python
    node_bits = "|".join(f"{nid}:{e.instance_id}" for nid, e in sorted(assign.items()))
    ...
        match_id=f"{plan.pattern_id}@{start}-{end}#{node_bits}",
```
`engine.py`:`_node_bits_of` 改 `f"{nid}:{e.instance_id}"`;analyze 消歧组键 `m.match_id`、后缀 `f"{m.match_id}#{idx}"`、断言注释同步。

`_solve.py:285`:`if len({e.event_id for e in s}) < len(s)` → `if any(e.instance_idx > 0 for e in s)`(注释同步)。

`edges.py`/`diagnose.py`/`spec.py`/`runner.py`:grep 残留逐处迁移(event_id 字符串比较 → instance_id;class_id → `__name__` 或 Python 类;spec 的 event_cls 归一化逻辑保留,class_id 引用删)。

- [ ] **Step 3: 跑绿 + dag 全量回归**

Run: `uv run pytest tests/path2/dag/ -q`
Expected: 全绿(既有断言先复核再同步:match event_id 断言 → match_id;事件 event_id 断言 → instance_id)。

- [ ] **Step 4: Commit**

```bash
git add path2/dag/ tests/path2/dag/
git commit -m "refactor: dag 层 instance_id 契约(match_id + 求解/物化/校验消费点迁移)"
```

---

### Task 4: 引擎侧残留清理(debug_ctx/gate_failure/eval)+ 引擎全量绿

**Files:**
- Modify: `path2/debug_ctx.py`、`path2/dag/gate_failure.py`、`path2/eval.py`
- Test: `tests/path2/` 全量

**Interfaces:**
- Consumes: Task 1-3 全部
- Produces: `uv run pytest tests/path2/ -q` 全绿(引擎层收口);Task 5 的干净基线

- [ ] **Step 1: 定位残留**

Run: `grep -rn "event_id\|source_tag\|class_id" path2/ --include="*.py" | grep -v test`
Expected: 仅剩 debug_ctx/gate_failure/eval(以及任何 Task 3 遗漏),登记到报告。

- [ ] **Step 2: 迁移 + 全量回归**

逐处迁移(class_id → `__name__`;event_id → instance_id 或 node_id 按语义),然后:

Run: `uv run pytest tests/path2/ -q`
Expected: 全绿(引擎层收口;既有断言同步先复核再改,规则同前)。

- [ ] **Step 3: Commit**

```bash
git add path2/ tests/path2/
git commit -m "refactor: 引擎侧残留清理(debug_ctx/gate_failure/eval)+ 引擎全量绿"
```

---

### Task 5: web serialize 重写(纯投影)

**Files:**
- Modify: `path2_web/serialize.py`(`_InstanceIndexer` :38-62 删除、`_event_to_dict`、`_match_to_dict` :132-145、`serialize_analysis` :148-188、`summarize` :191-198、静态层样式键)
- Test: `tests/path2_web/test_serialize.py`

**Interfaces:**
- Consumes: Task 1-4(事件已带 instance_id/node_id/instance_idx;match 带 match_id)
- Produces: 事件行 `{instance_id, node_id, instance_idx, start_idx, end_idx, confirm_idx?, child_refs: {slot: [instance_id]}, ...属性平铺}`;match 行 `{match_id, start_idx, end_idx, node_index: {nid: instance_id}, children: [instance_id], predicate_trace}`;无 source_tag/instance_key/event_id/class_id。Task 7 前端消费

- [ ] **Step 1: 写失败测试**

在 test_serialize.py 新增(复用既有 _analyze_dup_stream 双实例构造,断言改新契约):

```python
def test_serialize_events_instance_id_contract():
    """事件行新契约:instance_id/node_id/instance_idx 恒在;无 event_id/
    source_tag/instance_key/class_id。"""
    payload = serialize_analysis(res)          # res = 既有构造
    for r in payload["events"]:
        assert set(["instance_id", "node_id", "instance_idx"]) <= set(r)
        assert "#" in r["instance_id"]         # 恒带 #idx
        for banned in ("event_id", "source_tag", "instance_key", "class_id"):
            assert banned not in r, f"{banned} 残留"

def test_serialize_match_instance_refs():
    """match 行:node_index 值为 instance_id 字符串;children 全实例化;match_id。"""
    payload = serialize_analysis(res)
    for m in payload["matches"]:
        assert "match_id" in m and "event_id" not in m
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, str) and "#" in ref
        for c in m["children"]:
            assert isinstance(c, str) and "#" in c

def test_serialize_child_refs_instanced():
    """事件行 child_refs 值全实例化(instance_id 列表)。"""
    payload = serialize_analysis(res)
    for r in payload["events"]:
        for slot, ids in (r.get("child_refs") or {}).items():
            for i in ids:
                assert isinstance(i, str) and "#" in i
```

Run: `uv run pytest tests/path2_web/test_serialize.py -q -k "instance_id_contract or instance_refs or child_refs_instanced"`
Expected: FAIL(现状行仍输出旧字段)

- [ ] **Step 2: 重写 serialize_analysis**

- 删除 `_InstanceIndexer` 类与 `from path2.dag.engine import assign_auto_source_tags` import。
- `_event_to_dict(e)`:事件行改 `instance_id`/`node_id`/`instance_idx` + 属性平铺;`child_refs` 值用 `c.instance_id`;删 event_id/source_tag/instance_key/class_id 输出。
- `_match_to_dict(m)`:删 indexer 参数,`"match_id": m.match_id`,`node_index: {nid: e.instance_id}`(字符串),`children: [e.instance_id]`。
- `serialize_analysis`:删 tags/_band/indexer 逻辑;child 挖取(extra 段)seen 键改 `id(c)`,挖取行同新契约。
- `summarize(res)`:按 node_id 统计(`{e.node_id: count}` ∪ `{"matches": n}`;node_id None 的事件(未标注)跳过)。
- 静态层(_event_styles/_PALETTE):样式键从 class_id 改 node_id(分配规则同现状:按 topology.nodes 首现序 setdefault)。

- [ ] **Step 3: 跑绿 + path2_web 全量回归**

Run: `uv run pytest tests/path2_web/ -q`
Expected: 全绿(既有断言先复核再同步:事件行 event_id 断言 → instance_id;node_index 对象断言 → 字符串;summarize 键断言 → node_id;同源对拍测试(test_diagnose_instance_key)等跨文件红留给 Task 6)。

- [ ] **Step 4: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize.py
git commit -m "feat: serialize 重写为 instance_id 纯投影(删 indexer/source_tag/class 字段)"
```

---

### Task 6: web diagnose + eval_runner/scan/api 迁移

**Files:**
- Modify: `path2_web/diagnose.py`(`_attr_row`、`_rel_row`、`serialize_diagnostics`)
- Modify: `path2_web/eval_runner.py`(upstream_key 拼项)、`path2_web/scan.py`、`path2_web/api.py`(event_id/class_id 残留)
- Test: `tests/path2_web/` 全量

**Interfaces:**
- Consumes: Task 5 的新事件行契约;Task 1 的物化标注(diagnose 与 analyze 共用 run_streams,标注自动同源)
- Produces: attr 行 `{instance_id, node_id, start_idx, end_idx, clauses}`;rel 行 src/dst 与 example_failed_pairs 用 instance_id;web 层全绿

- [ ] **Step 1: 定位残留 + 写失败测试**

Run: `grep -rn "event_id\|source_tag\|class_id\|instance_key\|_InstanceIndexer" path2_web/ --include="*.py" | grep -v test`
Expected: 登记残留点。

在 diagnose 测试新增:
```python
def test_diag_attr_row_instance_id():
    """attr 行新契约:instance_id/node_id;无 event_id/instance_key。"""
    d = serialize_diagnostics(_diagnose(spec, df, None))
    for node in d["nodes"].values():
        for r in node["attr"]:
            assert "#" in r["instance_id"]
            assert "node_id" in r
            for banned in ("event_id", "instance_key"):
                assert banned not in r
```

Run: `uv run pytest tests/path2_web/ -q -k "instance_id"`
Expected: FAIL

- [ ] **Step 2: 迁移实现**

- `diagnose.py`:`_attr_row(row)` → `{"instance_id": row.event.instance_id, "node_id": row.event.node_id, "start_idx": ..., "end_idx": ..., "clauses": ...}`;`_rel_row` 的 ok_src_ids 用 `e.instance_id`;`serialize_diagnostics` 删 indexer 构造;dag/diagnose.py 的 example pairs(诊断内部)已由 Task 3 迁移。
- `eval_runner.py`:upstream_key 惰性 `#idx` 拼项改直接 `e.instance_id`(读内存对象)。
- `scan.py`/`api.py`:event_id/class_id 残留按语义迁移(诊断请求参数、params 校验消息等;api 的 diagnose_symbol 路径不变——标注已内建于 run_streams)。

- [ ] **Step 3: 跑绿 + path2_web 全量回归**

Run: `uv run pytest tests/path2_web/ -q`
Expected: 全绿(含 Task 5 遗留的跨文件红,如 test_diagnose_instance_key 的同源对拍改为 instance_id 断言)。

- [ ] **Step 4: Commit**

```bash
git add path2_web/ tests/path2_web/
git commit -m "feat: diagnose/eval_runner 迁移 instance_id 契约(web 层全绿)"
```

---

### Task 7: 前端 types + fixtures + visible.ts 实例化

**Files:**
- Modify: `path2_web_ui/src/types.ts`(EventDict/MatchDict/AttrRow/Diagnostics 等)
- Modify: `path2_web_ui/src/render/visible.ts`(matchedIds/qualifiedIdsOf/eventTierOf/resolveTooltipData/deriveTagMap/bandKeyOf)
- Modify: `path2_web_ui/tests/fixtures.ts` + 全 spec 的 fixture(约 27 文件)
- Test: `path2_web_ui/tests/`(visible.spec、render.visible.spec、render.chart-tooltip.spec 等)

**Interfaces:**
- Consumes: Task 5/6 的新契约行
- Produces: 类型(spec §5 的 EventDict/MatchDict/AttrRow);`instanceKeyOf` 删除,统一用 `instance_id`;band 分组键 = node_id;Task 8-10 依赖

- [ ] **Step 1: 全库定位消费点**

Run: `grep -rn "event_id\|source_tag\|class_id\|event_key\|instance_key" path2_web_ui/src --include="*.ts" --include="*.vue" | grep -v "\.spec"` 与 `grep -rln "event_id\|node_index" path2_web_ui/tests/`
Expected: 登记 src 消费点清单与 tests fixture 文件清单到报告(本 task 只动 types/visible/fixtures,chart/view/store 留给 Task 8-10;注意 fixture 同步会导致其他逻辑 spec 红——**本 task 用「逻辑未改但 fixture 已新」的中间态说明并在报告中记录**,只保证 visible 相关 spec 绿;或者按下面 Step 3 的边界处理)。

- [ ] **Step 2: 更新类型**

`src/types.ts`(spec §5 逐字):
```ts
export interface EventDict {
  instance_id: string; node_id: string; instance_idx: number
  start_idx: number; end_idx: number; confirm_idx?: number
  child_refs?: Record<string, string[]>
  // ...其余属性平铺字段保留;删除 event_id/source_tag/class_id
}
export interface MatchDict {
  match_id: string
  start_idx: number; end_idx: number
  node_index: Record<string, string>      // nid -> instance_id
  children: string[]
  predicate_trace?: unknown
}
export interface AttrRow {
  instance_id: string; node_id: string
  start_idx: number; end_idx: number
  clauses: Record<string, ClauseWitness>
}
```
TopoNode/Diagnostics 的 source_tag/event_id 字段按同规则迁移(node 分组键 node_id);`NodeRef` 删除。

- [ ] **Step 3: visible.ts 实例化**

- `instanceKeyOf` 删除;所有复合键逻辑改为直接 `instance_id`。
- `matchedIds(matches, events, edges, opts)`:初始集 `for (const ref of Object.values(m.node_index)) s.add(ref)`(字符串直加);child_refs/anchor 展开——**child_refs 已实例化,展开 = 直加字符串**,不再身份展开(byEventId 反查删除);anchor 反查字段值若是 instance_id 直加。docstring 同步。
- `qualifiedIdsOf(diag)`:集合元素 `row.instance_id`。
- `eventTierOf(e, matched, qualified)`:两档都 `has(e.instance_id)`。
- `resolveTooltipData(instanceId: string, diag, events, bars)`:attr 行 find `r.instance_id === instanceId`;identity 组装 `events.find(e => e.instance_id === instanceId)`。
- `deriveTagMap` → 按 `node_id` 分组(函数名可保留或改 deriveNodeMap;改名前 grep 调用点同步)。
- `bandKeyOf(e)` → 返回 `e.node_id`。
- render_grid 反查:`source_tag → TopoNode.render_grid` 改 `node_id → render_grid`。

- [ ] **Step 4: fixture 全量同步 + visible 相关 spec 绿**

`tests/fixtures.ts` 及全部 spec 的 fixture 机械迁移:
- 事件行:`event_id: 'tb_v1_293'` → `instance_id: 'tb_293#0', node_id: 'tb', instance_idx: 0`(删除 source_tag/class_id/instance_key 字段)
- match:`event_id` → `match_id`;`node_index: { burst: { event_id, idx } }` → `{ burst: 'burst_282_289#0' }`;children 值加 `#0`
- attr 行:instance_key → instance_id/node_id
- 断言同步先复核再改(机械规则:`=== 'xxx'` → instance_id 形态;`node_index[nid].event_id` → `node_index[nid]`)

Run: `cd path2_web_ui && npx vitest run tests/visible.spec.ts tests/render.visible.spec.ts tests/render.chart-tooltip.spec.ts && npx vue-tsc --noEmit`
Expected: visible 相关全绿;tsc 若因未迁移的 store/chart 报错,按报告记录(它们属 Task 8-10,tsc 全绿放到 Task 10 收口——**例外**:若 tsc 报错量使后续 task 无法定位,可先把调用点签名做最小 stub,以报告为准)。

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/render/visible.ts path2_web_ui/tests/
git commit -m "feat: 前端类型与 visible 实例化(instance_id 契约, band 按 node)"
```

---

### Task 8: 前端 view.ts 实例化(单入口 focusEvent)

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Test: `path2_web_ui/tests/stores.focus-actions.spec.ts`、`stores.disambig.spec.ts`、`stores.focus-derivations.spec.ts`、`stores.spec.ts`

**Interfaces:**
- Consumes: Task 7 的 EventDict/MatchDict;Task 5 的 node_index 字符串
- Produces: `focusEvent(instanceId: string)` 单入口;`selectedInstanceId`/`focusedInstanceId: Ref<string | null>`;无 focusedEventId/focusedEventKey/pendingDisambigEventId 的事件级形态(candidates 保持 match_id 集合);Task 9/10 依赖

- [ ] **Step 1: 写失败测试(单入口语义)**

```ts
it('focusEvent 单入口:按 instance_id 直选/待选择', () => {
  // fixture:两 match 分别引用 tb_293#0 / tb_293#1(APCX 形态,node_index 字符串)
  view.focusEvent('tb_293#0')
  expect(view.focusedMatchId).toBe(m0.match_id)      // 直选,无待选择
  expect(view.pendingDisambigEventId).toBeNull()
  view.focusEvent('tb_293#1')
  expect(view.focusedMatchId).toBe(m1.match_id)
})

it('focusEvent 真共享:同 instance_id 被两 match 引用 → 待选择', () => {
  view.focusEvent('tb_s#0')      // m0/m1 的 node_index 都引用 tb_s#0
  expect(view.pendingDisambigEventId).toBe('tb_s#0')
  expect(view.candidateMatchIds.size).toBe(2)
})
```

Run: `cd path2_web_ui && npx vitest run -t "focusEvent 单入口"`
Expected: FAIL(现状 focusEvent(eventId, idx?) 双入口)

- [ ] **Step 2: 实现**

`view.ts`:
- 状态:`focusedMatchId`(保留)、`selectedInstanceId = ref<string | null>(null)`、`focusedInstanceId = ref<string | null>(null)`、`pendingDisambigInstanceId`(取代 pendingDisambigEventId)、`candidateMatchIds`(保留)。
- 删:`focusedEventId`、`focusedEventKey`、`matchesOfInstance`、身份级并集分支、instanceKeyOf 依赖。
- `focusEvent(instanceId: string)`:归属 = `matches.filter(m => Object.values(m.node_index).includes(instanceId))`;0 → 只聚焦(selectedInstanceId=instanceId);1 → 直选(focusedMatchId + focusedInstanceId=instanceId);≥2 → pending(candidates + pendingDisambigInstanceId=instanceId)。清空路径配套(所有 `focusedEventId.value = null` 处同步)。
- `autoFollowLevel(instanceId)`:ev 定位改 `events.find(e => e.instance_id === instanceId)`,按实例 tier。
- shift 选择/详情卡消费的 selectedEventId 迁移为 selectedInstanceId(派生 computed 同步);导出区同步。
- 侧栏调用点(DetailSidebar 的 selectNodeEvent/selectCandidateRow)在 Task 10 迁移;本 task 若 tsc 红,先做最小签名兼容(调用点传 instance_id),完整组件改造留 Task 10。

- [ ] **Step 3: 跑绿 + 三绿**

Run: `cd path2_web_ui && npx vitest run tests/stores.focus-actions.spec.ts tests/stores.disambig.spec.ts tests/stores.focus-derivations.spec.ts tests/stores.spec.ts && npx vue-tsc --noEmit`
Expected: 全绿(既有断言先复核再同步:双入口用例 → 单入口;分属/共享语义按新 fixture)。

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/
git commit -m "feat: view 单入口 focusEvent(instance_id)+ selected/focusedInstanceId"
```

---

### Task 9: 前端 chart.ts + KlineChart 组件实例化

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`、`path2_web_ui/src/render/colors.ts`、`path2_web_ui/src/render/topology.ts`
- Modify: `path2_web_ui/src/components/KlineChart.ts`、`KlineChart.vue`
- Test: `path2_web_ui/tests/chart.spec.ts`、`components.kline-click.spec.ts`、`render.chart-tooltip.spec.ts`

**Interfaces:**
- Consumes: Task 7 的 EventDict(instance_id/node_id);Task 8 的 focusedInstanceId/selectedInstanceId
- Produces: marker 数据项带 instance_id(取代 event_key);点击直接 `view.focusEvent(data.instance_id)`;tooltip `resolveTooltipData(instanceId, ...)`;group/focus 条目按 instance_id 匹配;colors/topology 按 node_id 配色

- [ ] **Step 1: 写失败测试**

```ts
it('marker 点击按 instance_id 直选(无解析)', () => {
  // fixture:marker data { instance_id: 'tb_293#0' }
  handleChartClick({ seriesName: 'points', data: { instance_id: 'tb_293#0' } }, [], view)
  expect(view.focusedMatchId).toBe(m0.match_id)
})
```

Run: `cd path2_web_ui && npx vitest run -t "marker 点击按 instance_id"`
Expected: FAIL(现状解析 event_key)

- [ ] **Step 2: 实现**

- `chart.ts`:pointData/intervalData/pricePointData/satelliteData 数据项 `event_key` → `instance_id`(值 = `e.instance_id`);group/focus 条目按 `instance_id` 匹配(删 focusedEventKey 拼接);`buildMarkerTooltipFormatter` 直接传 `data.instance_id` 给 resolver(删 `lastIndexOf('#')` 解析);bracket 的 `m.node_index?.[endNode]` 值即字符串直用;`computeEventData` 入参 focusedInstanceId。
- `KlineChart.ts`:`ChartClickPayload.data` 的 `event_id/event_key` → `instance_id`;marker 分支 `view.focusEvent(p.data.instance_id)`(无解析、无退化分支);brackets 分支不变(focusMatch)。
- `KlineChart.vue`:storeToRefs 换 focusedInstanceId/selectedInstanceId;tooltipResolver `(id: string) => resolveTooltipData(id, ...)`;watch 依赖清单同步。
- `colors.ts`/`topology.ts`:样式键 source_tag/class_id → node_id。

- [ ] **Step 3: 跑绿 + 相关 spec + tsc**

Run: `cd path2_web_ui && npx vitest run tests/chart.spec.ts tests/components.kline-click.spec.ts tests/render.chart-tooltip.spec.ts && npx vue-tsc --noEmit`
Expected: 全绿(既有断言先复核再同步)。

- [ ] **Step 4: Commit**

```bash
git add path2_web_ui/src/render/ path2_web_ui/src/components/KlineChart.ts path2_web_ui/src/components/KlineChart.vue path2_web_ui/tests/
git commit -m "feat: chart/KlineChart 实例化(marker 直传 instance_id, tooltip 按实例)"
```

---

### Task 10: 前端 DetailSidebar + 其余组件收口

**Files:**
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`、`PairListCard.vue`、`PairDetailCard.vue`、`FailedAttemptsCard.vue`、`KlineChart.debug-menu.ts`、`src/api.ts`
- Test: `path2_web_ui/tests/components.detail-sidebar.spec.ts`、`components/DetailSidebar.spec.ts`、`components.candidate-status-bar.spec.ts` 等全部剩余 spec

**Interfaces:**
- Consumes: Task 7-9 全部
- Produces: 前端全量三绿收口(vitest + vue-tsc + vite build);pre-existing 4 失败(sidebar-result-list)对照不变

- [ ] **Step 1: 定位残留**

Run: `grep -rn "event_id\|event_key\|source_tag\|class_id\|instance_key\|selectedEventId\|focusedEventId\|focusedEventKey\|pendingDisambigEventId" path2_web_ui/src --include="*.ts" --include="*.vue"`
Expected: 登记残留点到报告,逐处迁移:
- DetailSidebar:侧栏 trace 行改为**实例列表**(每个 node_index 项一行:node 名 + instance_id);selectNodeEvent/selectCandidateRow 改传 instance_id 调 focusEvent;nodeEventId 相关删除。
- FailedAttemptsCard/KlineChart.debug-menu:class 显示改后端消息文本(后端已用 `__name__` 拼消息,前端只显示)。
- PairListCard/PairDetailCard/api.ts:event_id 字段引用 → instance_id/match_id。

- [ ] **Step 2: 三绿**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 全绿(4 个 sidebar-result-list pre-existing 失败对照确认无新增)。

- [ ] **Step 3: Commit**

```bash
git add path2_web_ui/src/ path2_web_ui/tests/
git commit -m "feat: 前端组件收口实例化(侧栏实例列表, 零 event_id/source_tag/class_id 残留)"
```

---

### Task 11: 全量回归 + 真实数据验收 + 报告

**Files:**
- Create: `docs/research/2026-08-13_instance-id-refactor/repro/final_report.md`
- 测试新增: `path2_web_ui/tests/instance-id-acceptance.spec.ts`(真实数据验收)

**Interfaces:**
- Consumes: Task 1-10 全部;真实数据 = 用新后端对 APCX 单股重算(同 marker 实例绑定验收的裁定:旧 scan 文件为新契约前产物,不兼容;用 `_scan_ticker_multi` 对 `datasets/pkls/APCX.pkl` 重算,窗口取旧 scan 元数据,固化为 `outputs/path2_web/scans/20260813T113000-instance-id.json` 之类的新文件,原历史文件不动)
- Produces: 验收报告 + 全量回归对照

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest tests/ -q`
Expected: 全绿或仅 pre-existing 名单(throwback debug anchor kinds 4 + bb_v1/bb_v3 p2.yaml 2——注意:本重构动引擎,pre-existing 名单可能变化,以实施前基线对照确认无新增为准,记录到报告)。

- [ ] **Step 2: 前端三绿**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 全绿(4 个 sidebar-result-list pre-existing 对照)。

- [ ] **Step 3: 真实数据验收(数据级断言)**

1. 用新后端对 APCX 单股重算,固化新契约格式文件。临时脚本(用完即删)参考形态:

```python
"""临时:APCX 单股重算,固化 instance_id 新契约验收数据。"""
import json
from path2_web.discovery import PatternRegistry
from path2_web.scan import _scan_ticker_multi
from path2_web.serialize import serialize_pattern
from path2_web.api import require_eval_meta
registry = PatternRegistry()
pid = "bb_v1"; mod = registry.get(pid)
p = mod.load_params() if hasattr(mod, "load_params") else None
specs = serialize_pattern(mod.build_pattern(p))
meta = require_eval_meta(mod, params=p)
symbol, per_pattern, fp, err = _scan_ticker_multi(
    "datasets/pkls/APCX.pkl", {pid: registry.module_path(pid)},
    "2025-01-01", "2026-01-01", "2024-09-19", "2026-03-08",
    {pid: meta["end_node"]}, 40,
    {pid: p.to_dict() if p is not None and hasattr(p, "to_dict") else None})
assert err is None and per_pattern is not None
out = {"symbol": symbol, "per_pattern": per_pattern}
Path("outputs/path2_web/scans/apcx-instance-id-acceptance.json").write_text(
    json.dumps(out, ensure_ascii=False))
```

(窗口参数取自旧 scan 元数据 outputs/path2_web/scans/20260813T005540.json 的 scan 节;固化为 `outputs/path2_web/scans/apcx-instance-id-acceptance.json`,原历史文件不动;验收测试加载该新文件。)
2. 新增 `path2_web_ui/tests/instance-id-acceptance.spec.ts` 加载该文件断言:
   - 事件行:`tb_293#0`/`tb_293#1` 两实例(node_id='tb'),各被一个 match 的 node_index 精确引用
   - `focusEvent('tb_293#0')` → 直选 match A;`focusEvent('tb_293#1')` → 直选 match B;无待选择
   - 真共享 fixture(同 instance_id 被两 match 引用)→ 待选择
   - 事件行无 event_id/source_tag/class_id/instance_key 字段
3. Run: `cd path2_web_ui && npx vitest run instance-id-acceptance.spec.ts` → PASS

- [ ] **Step 4: 写验收报告 + Commit**

报告内容:契约变更摘要(instance_id/match_id/class_id 消灭)、回归摘要(后端/前端对照)、真实数据验收结果、遗留观察(共享 detector 边界、pre-existing 名单变化如有)。

```bash
git add docs/research/2026-08-13_instance-id-refactor/ path2_web_ui/tests/instance-id-acceptance.spec.ts outputs/path2_web/scans/  # 验收数据文件按仓库先例 force-add
git commit -m "chore: instance_id 重构验收(真实 APCX 数据 + 全量回归 + 报告)"
```

---

## 实施完成判定

- 全部 11 个 task 完成且每 task commit 到实施分支;
- 前端三绿 + 后端 pytest 无新增失败(对照实施前基线);
- 真实数据验收通过(APCX 实例直选/真共享待选择/新契约字段);
- 验收报告入档。
