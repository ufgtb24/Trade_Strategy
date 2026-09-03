# 交错标注重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `annotate_instances` 从「全部 detect 完成后统一标注」改为「按拓扑序逐 node detect 完立刻标注」,使下游 detector 在 detect 阶段就能读到上游的 `instance_id`,从而让 `anchor_bo_id` 从 span 坐标升级为真实 instance_id,并彻底删除遗留的 `span_id` 函数,让整个计算只存在 instance_id 一种身份串。

**Architecture:** run_streams 的 detector 循环已按 `detector_topo_order`(无环 DAG 拓扑序)迭代。把 `annotate_instances` 挪进循环、每填一条 `streams[nid]` 就标注该流(bucket 计数器跨迭代保留),则任何 node 的 detector detect 时其 consumes_stream 链上的上游已带 instance_id。对象在 app 层经 `members`/`child_slots` 共享引用(已验证非拷贝),故标注沿对象图传播。anchor 机制随之统一到 instance_id,span_id 失去全部消费方后被删除。

**Tech Stack:** Python 3.11 + pytest(后端,`uv run pytest`);Vue3 + TypeScript + vitest + vue-tsc + vite build(前端,`cd path2_web_ui && npx vitest run` / `npx vue-tsc --noEmit` / `npx vite build`)。

**Spec:** `docs/superpowers/specs/2026-08-13-interleaved-annotate-span-id-elimination.md`(binding authority,本 plan 从它论证)。分析/权衡/来由见 research doc `docs/research/2026-08-13_interleaved-annotate-span-id-elimination.md`。三者冲突以 spec 为准。

**本 plan 中所有项目内路径均相对 repo root。**

## Global Constraints

- 后端跑 `uv run pytest`;前端三绿 `cd path2_web_ui && npx vitest run` + `npx vue-tsc --noEmit` + `npx vite build`。
- **pre-existing baseline(勿修,验收时核对不新增失败)**:后端 6 failed = `tests/path2/atoms/test_throwback_debug_anchor_kinds.py` 4 + `tests/path2_apps/bb_v1/`/`bb_v3/` 的 `p2.yaml` 2;前端 4 failed = `sidebar-result-list`。
- 测试纪律:先 RED 后 GREEN。既有断言修改属契约升级 fixture 同步——按本 plan 给出的精确 pattern 改,禁止盲改断言语义。
- 全中文注释/UI;Event 子类字段语义注释保持中文。
- instance_id 契约不变:`span_id(node_id, start, end) + "#" + instance_idx`,桶 `(node_id, start, end)` 内流序从 0 起。交错标注必须产出与现行批量标注**逐字一致**的 instance_id(由既有 multi-instance 测试 + 新增回归测试钉死)。
- 共享 detector 多 node(休眠特性):交错标注下首现 node 标注、其余 first-writer-wins 跳过,行为不变。
- 每个 task 跑绿再 commit 到实施分支 `instance-id-refactor`。

## File Structure

后端:
- `path2/dag/engine.py` — `run_streams` 循环内嵌逐流标注;`annotate_instances` 重构为逐流版本(Task 1)+ 内联塌缩规则(Task 2)。
- `path2/dag/edges.py` — `DependencyEdge._anchor_ok` 改比 `instance_id`(Task 1);删 `span_id` import(Task 2)。
- `path2/atoms/throwback.py` / `throwback_v0.py` / `throwback_v1.py` / `throwback_v3.py` — `anchor_bo_id = last_bo.instance_id`(Task 1);删 `span_id` import + 字段 docstring 更新。
- `path2/core.py` — 删 `span_id` 函数 + Event docstring 更新(Task 2)。
- `path2/stdlib/_ids.py` + `path2/stdlib/__init__.py` — 删 `span_id` re-export(Task 2)。
- `path2/dag/spec.py` — docstring 更新(Task 2)。

前端:
- `path2_web_ui/src/stores/view.ts` — `findBoBar` 坍缩为纯精确匹配;删 `parseSpanId` import/re-export(Task 3)。
- `path2_web_ui/src/render/visible.ts` — `matchedIds` 的 `resolveAnchor` 坍缩为 byId 直连;删 `parseSpanId` import(Task 3)。
- `path2_web_ui/src/shared/span.ts` — 两消费方切直连后删(Task 3)。
- `outputs/path2_web/scans/apcx-instance-id-acceptance.json` — 新后端重算(Task 4)。

测试(契约升级 + 新增):
- 7 个既有测试文件 fixture 升级(Task 1);1 个新增回归测试(Task 1);前端 fixture(Task 3)。

---

## Task 1: 交错标注 + anchor 实例化(后端协调原子改动)

**这是 load-bearing 的协调改动**:`annotate_instances` 进循环(让 detect 期拿到上游 instance_id)、`_anchor_ok` 改比 instance_id、4 个 throwback atom 改写 instance_id anchor、相关测试 fixture 同步——这些**必须同 task 落地**(任何子集单独落地都会产生 anchor 两端语义不一致的中途红:一端 span 一端 instance_id ⇒ `_anchor_ok` 恒 False ⇒ match 全断)。

**Files:**
- Modify: `path2/dag/engine.py:23-57`(annotate_instances 重构)、`engine.py:100-122`(run_streams 循环内嵌)
- Modify: `path2/dag/edges.py:18`(import)、`edges.py:46-48`(基类 docstring)、`edges.py:92-105`(`_anchor_ok`)
- Modify: `path2/atoms/throwback.py:48,271,336-340`;`throwback_v0.py:30,326,398-403`;`throwback_v1.py:34,353,445-450`;`throwback_v3.py:35,241,321-332`
- Modify(契约升级 fixture,详见 Step 5):`tests/path2/atoms/test_throwback_v3.py`、`tests/path2/atoms/test_throwback_event.py`、`tests/path2/atoms/test_throwback_v0_burst_anchor.py`、`tests/path2/atoms/test_throwback_v1_burst_anchor.py`、`tests/path2/atoms/test_tb_e2e_outcomes.py`、`tests/path2_web/test_diagnose_pair.py`、`tests/path2/dag/test_anchor_c1_off_fuzz.py`
- Create: `tests/path2/dag/test_anchor_same_span_disambiguation.py`

**Interfaces:**
- Consumes: instance_id 重构既有成果(事件已带 `instance_id/node_id/instance_idx`;`span_id` 函数仍在 core.py)。
- Produces: detect 期下游可读上游 `instance_id`;`anchor_bo_id` 恒为 instance_id 形态;`_anchor_ok` 按 instance_id 比较。`span_id` 此时仍剩 `engine.py:39` 一处真实调用(留给 Task 2 删)。

- [ ] **Step 1: 写失败测试 ① —— `_anchor_ok` 按 instance_id 区分同 span 实例(单元级)**

Create `tests/path2/dag/test_anchor_same_span_disambiguation.py`:

```python
# tests/path2/dag/test_anchor_same_span_disambiguation.py
"""同 span 上游多实例的 anchor 消歧回归(交错标注重构的核心收益证明)。

背景:重构前 anchor_bo_id 用 span 坐标,两个同 span 上游实例的 anchor 完全相等,
_anchor_ok 对交叉组合(A1-B2、A2-B1)全部放行 ⇒ match 虚增。重构后 anchor_bo_id
= 源 instance_id,_anchor_ok 按 instance_id 比较,交叉绑定被挡死。"""
from path2.atoms.breakout import BOEvent
from path2.atoms.throwback import ThrowbackEvent
from path2.dag.edges import TemporalEdge


def _edge():
    return TemporalEdge("bo", "tb", min_gap=1, max_gap=20, anchor_field="anchor_bo_id")


def test_anchor_ok_distinguishes_same_span_instances():
    """A1/A2 同 span、不同 instance_id;dst 锚 A1 ⇒ _anchor_ok(A1,dst)=True、(A2,dst)=False。"""
    a1 = BOEvent(start_idx=10, end_idx=10, confirm_idx=10, node_id="bo", instance_id="bo_10#0")
    a2 = BOEvent(start_idx=10, end_idx=10, confirm_idx=10, node_id="bo", instance_id="bo_10#1")
    dst = ThrowbackEvent(start_idx=12, end_idx=14, confirm_idx=12, anchor_bo_id="bo_10#0")
    e = _edge()
    assert e._anchor_ok(a1, dst) is True     # A1 是 dst 的源
    assert e._anchor_ok(a2, dst) is False     # A2 同 span 但不同实例 → 不应错绑(重构前此处为 True)
```

Run: `uv run pytest tests/path2/dag/test_anchor_same_span_disambiguation.py -q`
Expected: FAIL(`_anchor_ok(a2, dst)` 现行返 True,因 span_id(a1)==span_id(a2))

- [ ] **Step 2: 写失败测试 ② —— solve 级:同 span 上游不产生交叉 match(端到端)**

追加到同一文件:

```python
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.result import Event
from path2.dag.spec import PatternSpec
from path2.dag.engine import analyze  # noqa: F401  (确认 import 路径可用)


class _SrcEv(Event):
    """同 span 多实例的上游。"""
    is_point: bool = True


class _DstEv(Event):
    """锚定单个 src 的下游。anchor_to_src 存源 instance_id。"""
    is_point: bool = True
    anchor_to_src: str = ""


class _Canned:
    """不跑真实 detect,直接吐预算好的事件(同 test_anchor_c1_off_fuzz 套路)。"""
    def __init__(self, evs, cls):
        self._evs = evs
        self.event_cls = cls
    def detect(self, *source):
        return iter(self._evs)


def test_same_span_upstream_no_cross_match():
    """两个同 span src(S#0/S#1)各产一个 dst 锚定自己 ⇒ solve 恰好 2 match,无交叉。

    重构前:anchor 用 span,S#0/S#1 同 span ⇒ dst_a/dst_b 的 anchor 相等 ⇒ _anchor_ok
    对 (S#0,dst_a)/(S#0,dst_b)/(S#1,dst_a)/(S#1,dst_b) 全放行 ⇒ 4 match(含 2 交叉错绑)。
    重构后:dst 锚源 instance_id ⇒ 恰 2 match。"""
    s0 = _SrcEv(start_idx=10, end_idx=10, confirm_idx=10)
    s1 = _SrcEv(start_idx=10, end_idx=10, confirm_idx=10)   # 与 s0 同 span
    # dst 在 detect 期读 src.instance_id 写 anchor —— 须先标注 src(模拟交错标注效果)
    da = _DstEv(start_idx=15, end_idx=15, confirm_idx=15, anchor_to_src="src_10#0")
    db = _DstEv(start_idx=16, end_idx=16, confirm_idx=16, anchor_to_src="src_10#1")
    spec = PatternSpec(
        pattern_id="same_span_anchor",
        nodes=(NodeSpec("src", _Canned([s0, s1], _SrcEv)),
               NodeSpec("dst", _Canned([da, db], _DstEv))),
        edges=(TemporalEdge("src", "dst", min_gap=1, max_gap=20, anchor_field="anchor_to_src"),),
    )
    import pandas as pd
    df = pd.DataFrame({"open": [1]*20, "high": [1]*20, "low": [1]*20, "close": [1]*20, "volume": [1]*20})
    res = analyze(spec, df)
    # 重构前 4 match(交叉),重构后 2 match;边界严格 < 3 即可挡住交叉
    assert len(res.matches) == 2, f"期望 2 match(无交叉),实际 {len(res.matches)}"
```

> 说明:本测试 src 事件经 run_streams 交错标注后获得 `src_10#0`/`src_10#1`;dst 的 `anchor_to_src` 已写成对应 instance_id。dst detector 是 `_Canned`(不真 detect),其 anchor 值是预算的——这模拟了「真实 detector 在交错标注后读到 src.instance_id 并写入」的效果,聚焦验证 solve 端 `_anchor_ok` 的消歧。`_SrcEv.is_point`/`_DstEv.is_point` 使 instance_id 形态为 `src_10#idx`(点塌缩)。

Run: `uv run pytest tests/path2/dag/test_anchor_same_span_disambiguation.py -q`
Expected: FAIL(两个测试:① `_anchor_ok` span 不分;② 4 match 而非 2)

- [ ] **Step 3a: 写编号不变式 characterization 测试(重构前代码先确认 GREEN,锚定 3b 不改编号)**

spec §4 要求交错标注产出与原批量标注**逐字一致**的 instance_id。本测试锚定该不变式——属 characterization(钉既有行为),**非 RED-first**:在重构前代码上跑必须 GREEN,Step 3b 交错后必须保持 GREEN。若 3b 后转红,即编号被改,须修。

追加到 `tests/path2/dag/test_anchor_same_span_disambiguation.py`(复用 Step 2 已定义的 `_SrcEv`/`_DstEv`/`_Canned` 与 import):

```python
def test_interleave_instance_numbering_unchanged():
    """交错标注必须产出与批量标注逐字一致的 instance_id(characterization:重构前代码亦绿)。
    锚定:同 node 同 span → #0/#1 流序;同 node 不同 span → 各自 #0;多 node 各自独立计数。"""
    a_events = [
        _SrcEv(start_idx=10, end_idx=10, confirm_idx=10),   # src_10#0
        _SrcEv(start_idx=10, end_idx=10, confirm_idx=10),   # src_10#1(同 span 第二条)
        _SrcEv(start_idx=20, end_idx=20, confirm_idx=20),   # src_20#0(不同 span 重置)
    ]
    spec = PatternSpec(
        pattern_id="numbering_invariant",
        nodes=(NodeSpec("src", _Canned(a_events, _SrcEv)),
               NodeSpec("dst", _Canned([_DstEv(start_idx=15, end_idx=15, confirm_idx=15)], _DstEv))),
        edges=(TemporalEdge("src", "dst", min_gap=1, max_gap=20),),   # 无 anchor,纯验编号
    )
    import pandas as pd
    df = pd.DataFrame({"open": [1]*20, "high": [1]*20, "low": [1]*20, "close": [1]*20, "volume": [1]*20})
    res = analyze(spec, df)
    assert sorted(e.instance_id for e in res.events if e.node_id == "src") == ["src_10#0", "src_10#1", "src_20#0"]
    assert [e.instance_id for e in res.events if e.node_id == "dst"] == ["dst_15#0"]
```

Run: `uv run pytest tests/path2/dag/test_anchor_same_span_disambiguation.py::test_interleave_instance_numbering_unchanged -q`
Expected: **GREEN**(当前批量标注代码即产出这些 instance_id)。若红,先核对编号理解再继续。

- [ ] **Step 3b: engine.py —— `annotate_instances` 重构 + run_streams 循环内嵌**

把 `annotate_instances(streams, spec)` 重构为「逐流标注 + 持久计数器」,并在 `run_streams` 的 detector 循环内**每填一条流就标注**。

`path2/dag/engine.py` 当前 `run_streams`(line 100-122)末尾的 `annotate_instances(streams, spec)` 调用删除;改为循环内逐流调用。重构后的形态:

```python
def annotate_stream(counts: dict, nid: str, events) -> None:
    """标注单条流(含其嵌套 child):桶 (nid, start, end) 内流序从 0 起。
    counts 跨流持久(键含 nid,跨 node 不串扰);首现 node 获胜(已标注跳过)。
    行为与原批量 annotate_instances 逐字一致——只是调用点从循环外挪入循环内。"""
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

    def _annotate_children(e, nid: str) -> None:
        for slot in e.child_slots().values():
            members = slot if isinstance(slot, tuple) else (slot,)
            for c in members:
                if c.node_id is not None:
                    continue
                _annotate(c, nid)
                _annotate_children(c, nid)

    for e in events:
        _annotate(e, nid)
    for e in events:
        _annotate_children(e, nid)


def run_streams(spec, df, params=None):
    """阶段1:detector 依赖排序 + 跑流。返回 {node_id: [Event]}。
    交错标注:每条流 detect 完立刻标注,使下游 detector 在 detect 期即可读上游 instance_id
    (anchor_bo_id 据此写真实 instance_id,而非 span 回退)。计数器跨迭代持久。"""
    by_id = {n.node_id: n for n in spec.nodes}
    streams = {}
    materialized = {}
    counts: dict = {}   # 标注桶计数器,跨流持久
    for nid in detector_topo_order(spec.nodes):
        node = by_id[nid]
        if node.detector is None:
            continue
        key = (id(node.detector), node.consumes_stream)
        if key not in materialized:
            if node.consumes_stream is None:
                materialized[key] = list(run(node.detector, df))
            else:
                materialized[key] = list(run(node.detector, streams[node.consumes_stream], df))
        streams[nid] = materialized[key]
        annotate_stream(counts, nid, streams[nid])   # ★ 交错:detect 完立刻标注这条流
    _check_children_declarations(spec, streams)
    return streams
```

保留旧 `annotate_instances(streams, spec)` 函数定义?**删除**——grep 确认其唯一真实调用点是旧 run_streams:121(docstring 提及不算)。删函数 + 删调用。

> 注意:`_check_children_declarations` 仍放循环外(需全部流);它读 `e.child_slots()` 与标注无关,行为不变。共享 detector 多 node:`materialized` 去重使多 nid 指向同一 list,`annotate_stream` 首次标注后其余 nid 的事件已 `node_id is not None` 跳过——首现 node 获胜,与原行为一致。

Run: `uv run pytest tests/path2/dag/ -q -k "anchor or annotate or instance or multi"`
Expected: **编号不变式测试(Step 3a)保持 GREEN**(交错未改编号);既有标注/多实例测试仍绿;Step 1/2 的 anchor 消歧测试仍红(因 _anchor_ok 还没改、throwback 还写 span)。

- [ ] **Step 4: edges.py —— `_anchor_ok` 改比 instance_id**

`path2/dag/edges.py`:

(a) `DependencyEdge` 类 docstring(line 46-48)把「身份 = span_id(...)」改为「身份 = src_ep.instance_id(交错标注后 detect 期即非 None)」。

(b) `_anchor_ok`(line 92-105)改为:

```python
    def _anchor_ok(self, src_ep: Event, e_dst: Event) -> bool:
        """anchor 复核:dst 端 anchor_field 等于 src 端身份(src_ep.instance_id)。
        anchor 语义 =「dst 的锚点事件就是 src」;交错标注使 src_ep 经 endpoint() 投影到
        child(last_bo 等)后其 instance_id 在 detect 期即就位、solve 期恒非 None。
        集合字段(tuple/list/set/frozenset)按包含语义;标量按相等。
        anchor_field=None 时恒 True。"""
        if self.anchor_field is None:
            return True
        src_v = src_ep.instance_id
        dst_v = getattr(e_dst, self.anchor_field)
        if isinstance(dst_v, (tuple, list, set, frozenset)):
            return src_v in dst_v
        return dst_v == src_v
```

(c) 删 `from path2.core import Event, span_id` 中的 `span_id`,改为 `from path2.core import Event`(line 18)。**注意**:本 step 只删 edges.py 的 span_id 消费;core.py 的 `span_id` 函数本身留给 Task 2 删(engine.py:39 仍调用)。`anchor_src_field` 字段(line 58)保留不动(已退役、零消费)。

Run: `uv run pytest tests/path2/dag/test_anchor_same_span_disambiguation.py tests/path2/dag/test_diagnose_anchor_ok.py tests/path2/dag/test_anchor_c1_off_fuzz.py -q`
Expected: Step 1/2 新测试部分转绿(_anchor_ok 已改);但 test_diagnose_anchor_ok / test_anchor_c1_off_fuzz 因 fixture 仍 span 形态会红(Step 5/6 修)。

- [ ] **Step 5: 4 个 throwback atom —— `anchor_bo_id = last_bo.instance_id`**

逐文件把 `src_id = (last_bo.instance_id if ... else span_id(...))` 改为 `src_id = last_bo.instance_id`,并删该文件 `span_id` import、更新字段 docstring。**模式统一**(4 文件同形):

`throwback.py:48` `from path2.core import Event, span_id` → `from path2.core import Event`;`:336-337` 改为:
```python
            src_id = bo.instance_id
```
`:271` 字段 docstring 「检测阶段回退 span_id(类型名, span)」→ 「交错标注后取源 bo 的 instance_id(detect 期 bo 已标注);同窗口多 bo 各带单来源」。

`throwback_v0.py:30` 删 span_id import;`:398-399` → `src_id = last_bo.instance_id`;`:326` docstring 同上。

`throwback_v1.py:34` 删 span_id import;`:445-446` → `src_id = last_bo.instance_id`;`:353` docstring 同上。

`throwback_v3.py:35` 删 span_id import;`:321-322` → `src_id = last_bo.instance_id`;`:241` docstring 同上。

> 语义保证:交错标注后,detect 期 `last_bo.instance_id` 恒非 None(bo 在 tb 之前标注)。无 fallback。

Run: `uv run pytest tests/path2/atoms/ -q -k "throwback or tb"`
Expected: 多数 throwback 测试红(直接调 detect() 的 fixture bo 未带 instance_id ⇒ anchor=None,断言不匹配)——这正是 Step 6 要修的契约升级。

- [ ] **Step 6: 契约升级 fixture —— 直接调 detect() 的测试(bo fixture 带 instance_id)**

**Pattern(统一适用)**:这些测试绕过 run_streams、直接 `ThrowbackDetectorX().detect([_burst(_bo(idx))], df)`,bo 的 `instance_id` 默认 None。重构后 detector 写 `last_bo.instance_id`,故 fixture 的 bo 必须带 instance_id(镜像交错标注效果),断言改为「anchor 等于源 bo 的 instance_id」(format-agnostic,最稳健)。

(a) `tests/path2/atoms/test_throwback_v3.py`:`_bo`(line 36)改为:
```python
def _bo(idx):
    return BOEvent(start_idx=idx, end_idx=idx, confirm_idx=idx, instance_id=f"bo_{idx}#0")
```
`:273` 断言 `assert e.anchor_bo_id == "BOEvent_14"` → `assert e.anchor_bo_id == "bo_14#0"`(= `_bo(14).instance_id`)。

(b) `tests/path2/atoms/test_throwback_event.py`:定位该文件 `_bo` helper(同 `(a)` 加 `instance_id=f"bo_{idx}#0"`);断言改:
- `:90` `== "BOEvent_10"` → `== "bo_10#0"`
- `:114` `["BOEvent_12", "BOEvent_10"]` → `["bo_12#0", "bo_10#0"]`
- `:221` `{"BOEvent_131", "BOEvent_132"}` → `{"bo_131#0", "bo_132#0"}`

(c) `tests/path2/atoms/test_throwback_v0_burst_anchor.py`:该文件 `_bo`/bo fixture 加 instance_id;`:60` `== "BOEvent_19"` → `== "bo_19#0"`;`:76` `== "BOEvent_6"` → `== "bo_6#0"`(按实际 last_bo 的 idx 校准——先读该测试确认 last_bo 是哪个 bo,idx 以源 bo 为准)。

(d) `tests/path2/atoms/test_throwback_v1_burst_anchor.py`:同 (c);`:68` `→ "bo_19#0"`;`:84` `→ "bo_6#0"`(同上,先读校准 idx)。

(e) `tests/path2/atoms/test_tb_e2e_outcomes.py:89-90`:注释「检测阶段回退 span_id」改为「交错标注后取源 bo instance_id」;`by_anchor = {e.anchor_bo_id: e for e in events}` 逻辑不变(anchor 仍唯一区分各源 bo),仅注释更新。若该测试 bo fixture 也直调 detect 需带 instance_id,一并加。

> 纯构造测试(`test_throwback_event.py:29-76` 用字面 `anchor_bo_id="bo_20"` 构造 ThrowbackEventV1、`test_throwback_v2.py:7,12` 同)不调 detect、不经 _anchor_ok,**不改**。

- [ ] **Step 7: 契约升级 fixture —— 合成 _anchor_ok 测试**

(a) `tests/path2_web/test_diagnose_pair.py`:`_bbb_fixture()` 中 bo_b 已设 `instance_id="bo_b"`(line 53)。tb 的 `anchor_bo_id` 须等于「burst→tb 边 src 投影(last_bo=bo_b)的 instance_id」= `"bo_b"`。`:51` 与 `:54` 的 `anchor_bo_id="BOEvent_15"` → `anchor_bo_id="bo_b"`。`:42-43` 注释「span 身份 ... BOEvent_15」→「交错标注后 anchor_bo_id = 源 bo 的 instance_id(bo_b)」。`:12` docstring 「锚定 burst.last_bo.event_id」→ 「锚定 burst.last_bo.instance_id」。

(b) `tests/path2/dag/test_anchor_c1_off_fuzz.py:_build_anchor_spec`(line 49-70):src 事件经 run_streams 标注后获 instance_id,dst 的 `anchor_to_src` 须等于对应 src 的 instance_id。该测试 bypass run_streams(直接构造 streams),故须手工给 src 带 instance_id。`line 50-53` 改为:
```python
    for i in range(n_src):
        src = WideSrcEvent(start_idx=i, end_idx=10, confirm_idx=i,
                           node_id="src", instance_id=f"src_{i}_10#0")
        dst = DstEvent(start_idx=15, end_idx=15, confirm_idx=15, anchor_to_src=f"src_{i}_10#0")
        src_events.append(src); dst_events.append(dst)
```
删该文件 `span_id` import(WideSrcEvent 是区间事件,start=i≠end=10 ⇒ instance_id 形态 `src_{i}_10`)。该测试断言 c1_off 仍含 "src"(B4.3 anchor 边 src)——anchor_field 仍在,断言不变。

- [ ] **Step 8: 跑全量后端回归 + 核对 baseline**

Run: `uv run pytest tests/path2/ tests/path2_apps/ tests/path2_web/ -q`
Expected: 全绿除 baseline 6(throwback_debug_anchor_kinds 4 + bb_v1/bb_v3 p2.yaml 2)。**重点核对**:`test_throwback_debug_anchor_kinds`(4 个 pre-existing fail)的失败形态——若 anchor 改动使其行为变化(转绿或失败形态变),在 report 记录但**不作为本 task 目标修复**(baseline 容许);只要不出现 baseline 之外的新失败即可。

- [ ] **Step 9: Commit**

```bash
git add path2/dag/engine.py path2/dag/edges.py path2/atoms/throwback.py path2/atoms/throwback_v0.py path2/atoms/throwback_v1.py path2/atoms/throwback_v3.py tests/path2/dag/test_anchor_same_span_disambiguation.py tests/path2/atoms/test_throwback_v3.py tests/path2/atoms/test_throwback_event.py tests/path2/atoms/test_throwback_v0_burst_anchor.py tests/path2/atoms/test_throwback_v1_burst_anchor.py tests/path2/atoms/test_tb_e2e_outcomes.py tests/path2_web/test_diagnose_pair.py tests/path2/dag/test_anchor_c1_off_fuzz.py
git commit -m "feat: 交错标注 + anchor 实例化(run_streams 逐流标注, anchor_bo_id=instance_id, _anchor_ok 按 instance_id 消歧同 span 上游)"
```

---

## Task 2: 删除 span_id + 内联塌缩规则 + re-export 清理

Task 1 后 span_id 仅剩 `engine.py:39`(`annotate_stream` 内造 instance_id 前缀)一处真实调用。本 task 内联该规则、删函数与全部 re-export/docstring 残留。**纯死码清理,零行为变化**——靠 Task 1 已绿的全量回归钉死。

**Files:**
- Modify: `path2/dag/engine.py:15`(删 import)、`engine.py` annotate_stream 内 line 39(内联)
- Modify: `path2/core.py:28-36`(删 span_id 函数)、`core.py:70-73`(Event docstring)
- Modify: `path2/stdlib/_ids.py`(删转发)、`path2/stdlib/__init__.py:4,6,10`(删 re-export)
- Modify: `path2/dag/spec.py:190`(docstring)

**Interfaces:**
- Consumes: Task 1(span_id 仅剩 1 处真实调用)。
- Produces: 计算中无 span_id 函数;instance_id 前缀由 annotate_stream 内联塌缩规则产出。

- [ ] **Step 1: engine.py —— 内联塌缩规则 + 删 import**

`annotate_stream` 内 `_annotate` 的 instance_id 构造(line 39 区域)由:
```python
        object.__setattr__(e, "instance_id",
                           f"{span_id(nid, e.start_idx, e.end_idx)}#{idx}")
```
改为内联(点塌缩/区间):
```python
        prefix = f"{nid}_{e.start_idx}" if e.start_idx == e.end_idx else f"{nid}_{e.start_idx}_{e.end_idx}"
        object.__setattr__(e, "instance_id", f"{prefix}#{idx}")
```
`engine.py:15` `from path2.core import span_id` → 删除该行。

- [ ] **Step 2: core.py —— 删 span_id 函数 + 更新 Event docstring**

`core.py:28-36` 删整个 `span_id` 函数。`core.py:70-73` Event docstring「instance_id = span_id(node_id, start, end) + "#" + ...」改为「instance_id = `{node_id}_{start}[_{end}]}#{instance_idx}`(点事件塌缩 start、区间保留 start_end;规则内联于 engine.annotate_stream)」。

- [ ] **Step 3: stdlib —— 删 re-export**

`path2/stdlib/_ids.py`:删除 `from path2.core import span_id` 行与相关 docstring(span_id 转发说明);若该文件无其他内容则整文件留空或删(先读确认)。`path2/stdlib/__init__.py:6` 删 `from path2.stdlib._ids import span_id`;`:10` `__all__` 删 `"span_id"`;`:4` docstring 删 span_id 提及。

- [ ] **Step 4: spec.py docstring**

`path2/dag/spec.py:190`「src 端身份由 _anchor_ok 按 span_id(type(src_ep).__name__, span) 计算」→「src 端身份由 _anchor_ok 按 src_ep.instance_id 计算(交错标注后 detect 期即就位)」。

- [ ] **Step 5: 全量回归 + span_id 残留扫描**

Run: `grep -rn "span_id" path2/ --include=*.py`
Expected: **零命中**(docstring 也清)。若有残留,清掉。

Run: `uv run pytest tests/path2/ tests/path2_apps/ tests/path2_web/ -q`
Expected: 与 Task 1 收尾同结果(全绿除 baseline 6)——零行为变化。

- [ ] **Step 6: Commit**

```bash
git add path2/dag/engine.py path2/core.py path2/stdlib/_ids.py path2/stdlib/__init__.py path2/dag/spec.py
git commit -m "refactor: 删 span_id 函数 + 内联塌缩规则(交错标注后 anchor 已实例化, span_id 零消费方)"
```

---

## Task 3: 前端 anchor 双消费方切 instance_id 直连 + 测试同步 + 删 parseSpanId/span.ts

Task 1 后后端 `anchor_bo_id` 恒为 instance_id 形态(`bo_9#0`)。前端有**两个** anchor 消费方都建在「span 反查桥接(parseSpanId)」上,均需切 instance_id 直连:
1. `stores/view.ts::findBoBar`(debug 菜单 anchor→bar)— path ② span 反查成死路径。
2. `render/visible.ts::matchedIds` 的 `resolveAnchor`(K 线高亮集 anchor 展开,commit 9dcde36 修复)— span 反查分支成死路径。

两者切直连后 `parseSpanId` 零消费方,删 `shared/span.ts`。一批建立在 span 形态契约上的测试同步改 instance_id 形态。

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`(findBoBar 坍缩 + 删 parseSpanId import/re-export + 注释)
- Modify: `path2_web_ui/src/render/visible.ts`(resolveAnchor 坍缩 + 删 parseSpanId import + matchedIds docstring)
- Delete: `path2_web_ui/src/shared/span.ts`(两消费方切直连后)
- Modify(测试改 instance_id 形态): `tests/stores.anchorsOf.spec.ts`、`tests/stores.triggerEventDebug.spec.ts`、`tests/stores.anchor-kind-mapping.spec.ts`、`tests/components.KlineChart-debug-menu.spec.ts`、`tests/render.visible.spec.ts`、`tests/components.kline-click.spec.ts`

**Interfaces:**
- Consumes: Task 1(后端 anchor_bo_id 恒 instance_id 形态)。
- Produces: 前端单一 instance_id 命名空间,两个 anchor 消费方均直连,parseSpanId/span.ts 删除。

**fixture 升级统一 pattern**:凡 `anchor_bo_id: 'BOEvent_X'` / `'BOEvent_X_Y'`(span 形态)→ 改 instance_id 形态 `'bo_X#0'` / `'bo_X_Y#0'`,**并确保该测试的 events 列表含一个 `instance_id` 与之相等的 bo 事件**(findBoBar/matchedIds 直连靠 byId 命中)。直测 parseSpanId 本身的用例删除(parseSpanId 已不存在)。

- [ ] **Step 1: view.ts —— findBoBar 坍缩 + 删 parseSpanId**

`view.ts:28-42` 改为(删 path ② span 反查):
```typescript
export function findBoBar(anchorBoIds: string | readonly string[], events: readonly any[]): number | null {
  const anchor: string = Array.isArray(anchorBoIds) ? anchorBoIds[0] ?? '' : anchorBoIds
  if (!anchor) return null
  // anchor_bo_id 恒为 instance_id 形态(后端交错标注后 detect 期写入),纯精确匹配
  const exact = events.find(x => x.instance_id === anchor)
  return exact?.end_idx ?? null
}
```
删 `view.ts:24-26` 的 `import { parseSpanId } from '../shared/span'` 与 `export { parseSpanId }`。

- [ ] **Step 2: visible.ts —— resolveAnchor 坍缩 + 删 parseSpanId**

`visible.ts:39-46` 的 `resolveAnchor` 改为(删 span 反查分支):
```typescript
  const resolveAnchor = (v: string): void => {
    if (byId.has(v)) enqueue(v)
  }
```
删 `visible.ts:4` 的 `import { parseSpanId } from '../shared/span'`。更新 `matchedIds` docstring(line 11-18、35-38)与 line 12 注释:删去「span 反查/检测阶段回退 span_id」表述,改为「anchor 字段值恒为 instance_id,byId 直连命中」。

- [ ] **Step 3: 删 span.ts + 零残留扫描**

确认 Step 1/2 后 `parseSpanId` 无消费方,删 `path2_web_ui/src/shared/span.ts`。
Run: `cd path2_web_ui && grep -rn "parseSpanId\|shared/span" src/`
Expected: 零命中。

- [ ] **Step 4: 测试改 instance_id 形态(6 文件)**

按上述 pattern 逐文件改:
- `tests/stores.anchorsOf.spec.ts`:删 `parseSpanId` import(:21)与整段 `describe('parseSpanId', ...)`(:41-54,parseSpanId 已删);findBoBar/anchor 用例(:85-130、146-161)的 span 形态 anchor 改 instance_id 形态 + 补匹配 bo 事件;文件 docstring(:14-17)改述新契约。
- `tests/stores.triggerEventDebug.spec.ts`:7 处 `anchor_bo_id:'BOEvent_30'`/`'BOEvent_30_33'`(:56、70、83、96、120、146、174)→ instance_id 形态;各用例 events 补匹配 bo。
- `tests/stores.anchor-kind-mapping.spec.ts:42`:`'BOEvent_50_90'` → instance_id 形态 + 补 bo。
- `tests/components.KlineChart-debug-menu.spec.ts:40、42、44`:`'BOEvent_30_33'` → instance_id 形态 + 补 bo。
- `tests/render.visible.spec.ts`:`TB_SPAN`/`BO_SPAN` fixture(:41-60,span 形态 anchor)+「span 反查命中同 span」用例改 instance_id 形态直连——该文件本就测 matchedIds anchor 展开,改后测 byId 直连命中。
- `tests/components.kline-click.spec.ts:532、534、536`:`'BOEvent_10'` → instance_id 形态 + 补 bo。

已是 instance_id 形态、**不改**:`focus-derivations`/`focus-actions`/`detail-sidebar`/`kline-click:353,468`/`visible.spec.ts`(均 `bo_x#0`)。

- [ ] **Step 5: 三绿**

Run: `cd path2_web_ui && npx vitest run`
Expected: 全绿除 baseline 4(sidebar-result-list)。

Run: `cd path2_web_ui && npx vue-tsc --noEmit`
Expected: 0 errors。

Run: `cd path2_web_ui && npx vite build`
Expected: success。

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/src/render/visible.ts path2_web_ui/src/shared/span.ts path2_web_ui/tests/
git commit -m "refactor: 前端 anchor 双消费方(findBoBar+matchedIds)切 instance_id 直连, 删 parseSpanId/span.ts"
```

---

## Task 4: APCX 验收 fixture 新引擎重算 + e2e 验证

Task 1-3 后,用新后端对 APCX 单股重算,刷新固化验收 fixture(`outputs/path2_web/scans/apcx-instance-id-acceptance.json`,旧引擎产物含 span 形态 anchor_bo_id),并验证 `instance-id-acceptance.spec.ts` 在新 fixture 上通过。同 instance-id 重构 Task 11 套路(临时脚本用完即删,原历史 scan 文件不动)。

**Files:**
- Modify(重算覆盖): `outputs/path2_web/scans/apcx-instance-id-acceptance.json`
- Run(验证,不改): `path2_web_ui/tests/instance-id-acceptance.spec.ts`

**Interfaces:**
- Consumes: Task 1-3(新引擎 + 前端直连)。
- Produces: 新引擎下的 APCX 真实验收 fixture(anchor_bo_id 为 instance_id 形态)。

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest tests/path2/ tests/path2_apps/ tests/path2_web/ -q`
Expected: 全绿除 baseline 6(Task 1 已核对)。

- [ ] **Step 2: APCX 单股重算(临时脚本,用完即删)**

```python
"""临时:APCX 单股重算,固化交错标注新契约验收数据(anchor_bo_id=instance_id 形态)。"""
import json
from pathlib import Path
from path2_web.discovery import PatternRegistry
from path2_web.scan import _scan_ticker_multi
from path2_web.serialize import serialize_pattern
from path2_web.api import require_eval_meta
registry = PatternRegistry()
pid = "bb_v1"; mod = registry.get(pid)
p = mod.load_params() if hasattr(mod, "load_params") else None
serialize_pattern(mod.build_pattern(p))   # 触发 spec 序列化(校验新契约)
meta = require_eval_meta(mod, params=p)
symbol, per_pattern, fp, err = _scan_ticker_multi(
    "datasets/pkls/APCX.pkl", {pid: registry.module_path(pid)},
    "2025-01-01", "2026-01-01", "2024-09-19", "2026-03-08",
    {pid: meta["end_node"]}, 40,
    {pid: p.to_dict() if p is not None and hasattr(p, "to_dict") else None})
assert err is None and per_pattern is not None
Path("outputs/path2_web/scans/apcx-instance-id-acceptance.json").write_text(
    json.dumps({"symbol": symbol, "per_pattern": per_pattern}, ensure_ascii=False))
```

(窗口参数同 instance-id Task 11,取自旧 scan 元数据;覆盖固化为新契约格式;原历史 scan 文件不动。)`bb_v1` 是 instance-id Task 11 所用 pattern;若交错标注使 APCX 在 `bb_v1` 下的命中 instance_id 微变,以实际重算结果为准。

Run: `uv run python /tmp/recompute_apcx.py` → `git add -f outputs/path2_web/scans/apcx-instance-id-acceptance.json`(outputs 常被 gitignore,force-add 固化)→ 删临时脚本。

- [ ] **Step 3: 验收 spec + anchor 形态核对**

Run: `cd path2_web_ui && npx vitest run instance-id-acceptance.spec.ts`
Expected: PASS(tb_293#0/#1 双实例、focusEvent 直选、零 banned 字段)。

anchor 形态核对(新 fixture 应全为 instance_id 形态):
Run: `grep -o '"anchor_bo_id"[^,]*' outputs/path2_web/scans/apcx-instance-id-acceptance.json | grep 'BOEvent_'`
Expected: 零命中(全已 instance_id 形态)。

- [ ] **Step 4: Commit**

```bash
git add outputs/path2_web/scans/apcx-instance-id-acceptance.json
git commit -m "chore: APCX 验收 fixture 新引擎重算(交错标注, anchor_bo_id=instance_id 形态)"
```

---

## Self-Review 结论

- **Spec 覆盖**:设计文档「正解:交错标注」→ Task 1 Step 3b;「anchor 升级为 instance_id」→ Step 4/5;「连锁:span_id 可删」→ Task 2;「前端红利(两 anchor 消费方)」→ Task 3(findBoBar + visible.ts matchedIds)+ Task 4(验收 fixture 重算);「必须补的回归测试:同 span 上游」→ Task 1 Step 1/2;spec §4 编号不变式 → Task 1 Step 3a;spec §6 两消费方 → Task 3 Step 1/2。全覆盖。
- **Placeholder 扫描**:无 TBD;fixture 升级给精确 pattern + 逐文件行号(c/d 的 idx 标注「先读校准」是因 last_bo 取值需核对实际测试,非占位);前端 6 测试文件逐名列出 + 改动 pattern。
- **类型一致**:`annotate_stream(counts, nid, events)` 签名在 Step 3b 定义、run_streams 调用一致;`_anchor_ok` 改后 Step 1 测试与生产签名一致;`resolveAnchor` 坍缩后与 findBoBar 同款 byId 直连;instance_id 形态(`bo_{idx}#0` / `src_{i}_10#0`)与塌缩规则逐字对齐。
- **前端 scope 自查**:parseSpanId 有两个消费方(view.ts findBoBar + visible.ts resolveAnchor),Task 3 Step 1/2 均切直连后才删 span.ts;6 个 span 形态测试文件 + 验收 fixture 全覆盖,无遗漏。
