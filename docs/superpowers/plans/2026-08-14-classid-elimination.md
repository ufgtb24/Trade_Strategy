# class_id 彻底清除（统一到 node_id）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 repo 内 class_id 概念的全部三源头（TopoNode 死字段 / GateFailure 类名 / debug class 门），身份统一到 node_id/instance_id 双轴，顺手修复右键 debug 双 bug。

**Architecture:** 后端自底向上（身份字段 → 注入/防护 → debug 门 → web 契约）→ 前端契约同步 → 文档/skill 清理 → e2e 验收。GateFailure 的 node_id 由 gate_collector per-node wrapper 注入（detector 作者零感知）；共享产-gate detector 用挂雷式延迟 raise 防护。

**Tech Stack:** Python 3.12 (dataclasses frozen) / FastAPI / Vue3 + TypeScript + Pinia + vitest / pytest

**Spec:** `docs/superpowers/specs/2026-08-14-classid-elimination.md`（binding authority，本 plan 从它论证；研究全文 `docs/research/2026-08-14_classid-elimination-study/final_report.md`）

## Global Constraints

- 本 plan 中所有项目内路径均相对 repo root。
- 分支：`instance-id-refactor`（延续未并 master；每个 Task 结束 commit；全部完成后 push 该分支到 origin，**禁止开 PR**）。
- 实施模型：implementer=sonnet / reviewer=opus（subagent-driven 既有约定）。
- baseline（勿修）：后端 pytest 0 failed / 2 skipped；前端 vitest 4 failed（sidebar-result-list，pre-existing）+ vue-tsc 0 + build success。
- GateFailure 不落盘（serialize 零输出 failed_attempts）→ 无 scan 文件迁移；APCX fixture 事件行本就无 class_id，`path2_web_ui/tests/fixtures/apcx-instance-id-acceptance.json` 不动。
- 终态验收锚（Task 5 执行）：`grep -rn "class_id" path2/ path2_web/ path2_apps/ path2_web_ui/src/ scripts/ .claude/skills/authoring-path2-detector/ .claude/skills/diagnose-event/` → **零命中**。
- UI 文案与注释一律中文。
- `datasets/pkls/APCX.pkl` 存在（Task 5 e2e 用）。
- 运行后端测试统一 `uv run pytest <path> -x -q`；前端统一在 `path2_web_ui/` 内 `npx vitest run <path>` / `npx vue-tsc --noEmit` / `npx vite build`。

---

### Task 1: GateFailure 身份字段 + gate_collector 注入/挂雷 + scope=time 契约 node 化

**Files:**
- Modify: `path2/dag/gate_failure.py`（GateFailure 删 class_id、加 node_id）
- Modify: `path2/atoms/breakout.py`、`path2/atoms/throwback.py`、`path2/atoms/throwback_v0.py`、`path2/atoms/throwback_v1.py`、`path2/atoms/throwback_v3.py`（仅 GateFailure 构造点的 class_id kwarg）
- Modify: `path2_web/gate_collector.py`（per-node wrapper + 挂雷）
- Modify: `path2_web/diagnose.py`（TimePayload.all_classes→all_nodes、Query.event_class→node、过滤 gf.node_id）
- Modify: `path2_web/api.py`（/diagnose 端点删 event_class 参数与 Query 传参；DEBUG_EVENT_CLASS 通道本 task **不动**——Task 2）
- Test: `tests/path2_web/test_gate_collector_node_id.py`（新建）
- Test: 既有 `tests/path2_web/` 下引用 `all_classes`/`event_class`/`gf.class_id` 的测试同步改（先 `grep -rln "all_classes\|event_class\|\.class_id" tests/path2_web/ tests/path2/` 定位）

**Interfaces:**
- Consumes: `GateFailure`（frozen dataclass，现有 13 生产构造点全 kwargs 形态）
- Produces: `GateFailure.node_id: str = ''`（构造时可省，gate_collector 注入）；`attach_and_collect(spec) -> GateCollector`（签名不变，行为=per-node 注入+共享挂雷）；`TimePayload.all_nodes: List[str]`；`Query.node: Optional[str]`（替代 event_class）；`/diagnose?scope=time` 请求参数 `node`（替代 event_class）

- [ ] **Step 1: 写失败测试**（新文件 `tests/path2_web/test_gate_collector_node_id.py`）

```python
"""gate_collector per-node wrapper 注入 node_id + 挂雷式共享防护(spec 2026-08-14 §2.2)。

- wrapper 注入:非共享 detector 的 gf 进 collector 后 node_id == 所属 node
- 非法共享:同一产 gate detector 挂 2 node,首条 gf 到达即 raise(文案含修法关键词)
- 合法共享:不 emit gf 的 detector(如 TrendSegmentDetector 场景)挂 2 node,雷永不动零差异
"""
from dataclasses import dataclass
from typing import Callable, Optional

import pytest

from path2.dag.gate_failure import GateFailure
from path2_web.gate_collector import attach_and_collect


@dataclass
class _FakeNode:
    node_id: str
    detector: object = None


class _FakeSpec:
    def __init__(self, nodes):
        self.nodes = nodes


def _mk_gf() -> GateFailure:
    # minimal 构造;measured/threshold 形态可参考既有 gate_failure 测试,此处仅占位
    return GateFailure(
        failure_event_window=(1, 2), start_idx=1, gate_idx=2, anchor_bar=1,
        gate_name='g', measured=('x', 1.0), threshold=1, op='>=',
        threshold_param=None, evaluation_lookback=None, symbol='TEST')


class _GateDetector:
    """产 gate failure 的假 detector(on_gate 由 attach 挂载)。"""
    def __init__(self):
        self.on_gate: Optional[Callable] = None

    def emit(self):
        self.on_gate(_mk_gf())


class _SilentDetector:
    """不产 gate failure 的假 detector(合法共享场景,如 Trend)。"""
    def __init__(self):
        self.on_gate: Optional[Callable] = None


def test_wrapper_injects_node_id():
    det_a, det_b = _GateDetector(), _GateDetector()
    spec = _FakeSpec([_FakeNode('bo', det_a), _FakeNode('tb', det_b)])
    collector = attach_and_collect(spec)
    det_a.emit(); det_b.emit(); det_b.emit()
    assert [g.node_id for g in collector.snapshot()] == ['bo', 'tb', 'tb']


def test_shared_gate_detector_raises_on_first_gf():
    det = _GateDetector()
    spec = _FakeSpec([_FakeNode('down', det), _FakeNode('side', det)])
    attach_and_collect(spec)
    with pytest.raises(RuntimeError, match='一 node 一实例'):
        det.emit()


def test_shared_silent_detector_zero_behavior_diff():
    det = _SilentDetector()
    spec = _FakeSpec([_FakeNode('down', det), _FakeNode('side', det)])
    collector = attach_and_collect(spec)
    assert collector.snapshot() == ()   # 不 emit gf → 雷永不动
```

注：若 `GateFailure` 现有构造校验（`__post_init__` 对 measured 的处理）拒绝 `('x', 1.0)`，参考 `tests/path2/` 下既有 GateFailure 测试的 measured 构造方式改 `_mk_gf`（语义不变：合法可构造的最小 gf）。

- [ ] **Step 2: 跑测试确认 RED**

Run: `uv run pytest tests/path2_web/test_gate_collector_node_id.py -x -q`
Expected: FAIL（`node_id` 不存在 / snapshot 顺序不符 / 共享不 raise）

- [ ] **Step 3: gate_failure.py 字段变更**

在 `path2/dag/gate_failure.py`：
1. 删除字段行 `    class_id: str   # detector event 类的 Python 类名(event_cls.__name__);spec:类型用 Python 类`（:65）及其 docstring 描述行。
2. 在默认值区（`symbol: str` 之后、`code_location: str = ''` 之前）新增：

```python
    # 追加字段, 带默认值 → 既有 kwargs 构造点全兼容(先例:code_location)
    node_id: str = ''   # 所属 node_id(gate_collector per-node wrapper 注入;detector 构造阶段为空)
```

- [ ] **Step 4: atoms 删 GateFailure 构造点的 class_id kwarg**

Run: `grep -n "class_id=" path2/atoms/breakout.py path2/atoms/throwback.py path2/atoms/throwback_v0.py path2/atoms/throwback_v1.py path2/atoms/throwback_v3.py`
区分两类命中（看上下文）：`GateFailure(...)` 构造内的 `class_id=XXX.__name__,` 行 → **删除该行**；`debug_break(...)` 调用内的 → **本 task 不动**（Task 2 处理）。
Expected: GateFailure 构造点全清（约 13 处），debug_break 埋点保留。

- [ ] **Step 5: gate_collector.py 实现 wrapper + 挂雷**

替换 `attach_and_collect`（:37-45）为：

```python
def attach_and_collect(spec) -> GateCollector:
    """遍历 spec.nodes,给每个 node.detector.on_gate 挂 per-node wrapper:收到 GateFailure
    后 replace 注入 node_id 再进 collector(detector 作者零感知,链式兼容 detect 内层包装)。

    共享防护(spec 2026-08-14 §2.2,挂雷式):同一 detector 对象被 ≥2 node 引用时,覆盖挂
    _boom —— 该 detector 首条 gate failure 到达即 raise。产 gate failure 的 detector 须
    一 node 一实例(gf.node_id 归属在共享下无真值);不 emit gf 的 detector(如
    TrendSegmentDetector 合法共享)雷永不动,零误杀。子结构 node(produced_by 非空)无
    detector,跳过(无 GateFailure 源头)。"""
    import dataclasses

    collector = GateCollector()

    def make_wrapper(nid: str):
        def _wrap(gf: GateFailure) -> None:
            collector.add(dataclasses.replace(gf, node_id=nid))
        return _wrap

    def make_boom(det):
        def _boom(_gf: GateFailure) -> None:
            raise RuntimeError(
                f"detector {type(det).__name__} 被多个 node 共享且产出了 gate failure;"
                f"产 gate failure 的 detector 须一 node 一实例。"
                f"请为每个 node 构造独立 detector 实例。")
        return _boom

    seen: set[int] = set()
    for node in spec.nodes:
        if node.detector is None:
            continue
        key = id(node.detector)
        if key in seen:
            node.detector.on_gate = make_boom(node.detector)
        else:
            seen.add(key)
            node.detector.on_gate = make_wrapper(node.node_id)
    return collector
```

同步更新模块 docstring（:10-12"同一 detector 对象可能被多个 node 共享…天然幂等"一段改为：共享 detector 若产 gate failure 会被挂雷式防护拦截 raise；不产 gf 的共享（Trend 场景）不受影响）。

- [ ] **Step 6: diagnose.py 契约 node 化**

`path2_web/diagnose.py`：
1. `TimePayload`（:174-182）：docstring 中 "all_classes:…event 类名 __name__ 全集…过滤契约面是 gf.class_id(其值已迁为 event_cls.__name__,Task 4)" 改写为 "all_nodes:该 pattern 全部 node_id 全集——前端下拉选项锚,让『存在但本区间无失败』的 node 可见(置灰)而非消失。过滤契约面是 gf.node_id(gate_collector wrapper 注入),故 all_nodes 取 spec node_id 与之对齐"；字段 `all_classes: List[str]` → `all_nodes: List[str]`。
2. `_derive_time_response` 内（:199-203）：注释与计算改为：

```python
    # node 全集:该 pattern 全部 node(含子结构 node)——取 spec node_id(与 GateFailure.node_id
    # 的注入值同源);前端下拉据此显示"存在但本区间无失败"的选项(置灰)。
    spec_nodes = spec.nodes if spec is not None else ()
    all_nodes = sorted({n.node_id for n in spec_nodes})
```

（下文两处 `TimePayload(..., all_classes=all_classes)` 相应改 `all_nodes=all_nodes`。）
3. 过滤（:214-215）：

```python
    def _node_ok(gf: GateFailure) -> bool:
        return query.node is None or gf.node_id == query.node
```

（`filtered` 列表推导里 `_class_ok(gf)` 改 `_node_ok(gf)`。）
4. `Query` dataclass（本文件内定义，先 `grep -n "class Query" path2_web/diagnose.py` 定位）：字段 `event_class` → `node`；全文件 `grep -n "event_class" path2_web/diagnose.py` 其余消费点同步。

- [ ] **Step 7: api.py 删 scope=time 的 event_class 参数**

`path2_web/api.py` `/diagnose` 端点：
1. 签名（:276）删 `event_class: Optional[str] = None,`。
2. `Query(...)` 构造（:320-321）删 `event_class=event_class,`。
3. **不动** `:292-293`（`if event_class: os.environ["DEBUG_EVENT_CLASS"] = ...`）与 `:346` pop——它们引用已删的局部变量会 NameError！这两处一并删除（连同 :342 的 v4 注释行）；`DEBUG_BAR_RANGE`/`DEBUG_ANCHOR_KIND` 的 set/pop 保留。

- [ ] **Step 8: 同步既有测试 + 全量后端绿**

Run: `grep -rln "all_classes\|event_class\|\.class_id\|class_id=" tests/path2_web/ tests/path2/ tests/path2_apps/`
对命中文件：`all_classes`→`all_nodes`、`gf.class_id`→`gf.node_id`、Query/event 断言的 `event_class`→`node`、GateFailure 构造删 `class_id=` kwarg。**debug_break 埋点断言（含 `DEBUG_EVENT_CLASS`、`class_id=` 于 debug_break 调用）本 task 不动**——若这些文件因此仍红，说明它们测的是 Task 2 范围，记录文件名留给 Task 2，本 task 验收口径 = `test_gate_collector_node_id.py` 全绿 + 除 debug-class 相关文件外全绿。
Run: `uv run pytest tests/path2_web/ tests/path2/dag/test_gate_failure*.py -x -q` → GREEN；再 `uv run pytest -x -q`（全量），记录仅剩 debug-class 相关失败清单。

- [ ] **Step 9: Commit**

```bash
git add path2/dag/gate_failure.py path2/atoms/ path2_web/gate_collector.py path2_web/diagnose.py path2_web/api.py tests/path2_web/test_gate_collector_node_id.py tests/
git commit -m "feat: GateFailure 身份切 node_id(wrapper 注入+挂雷共享防护)+scope=time 契约 node 化"
```

---

### Task 2: debug 四门→三门（删 class 门）+ debug_enabled_nodes 改名

**Files:**
- Modify: `path2/debug_ctx.py`（删 class 门/_read_class_id/DEBUG_EVENT_CLASS；签名删 class_id）
- Modify: `path2/atoms/*.py`（30 处 debug_break 埋点删 class_id kwarg）
- Modify: `path2_web/serialize.py`（debug_enabled_classes→debug_enabled_nodes）
- Modify: `path2_web/api.py`（:245 backfill 字段名同步）
- Test: 既有 debug-class 相关测试文件（Task 1 Step 8 记录的清单 + `grep -rln "DEBUG_EVENT_CLASS\|debug_break\|debug_enabled_classes" tests/`）

**Interfaces:**
- Consumes: Task 1 后 atoms 已无 GateFailure class_id kwarg
- Produces: `debug_break(i: int, *, anchor_kind: str, stop_at_frame: Optional[Any] = None) -> None`（三门：`_DEBUG_MODE ∧ bar∈range ∧ anchor_kind`）；serialize pattern 契约字段 `debug_enabled_nodes: list[str]`（值不变 = node_id 去重拓扑序）

- [ ] **Step 1: 改造 test_debug_ctx 为三门 RED**

`grep -rln "DEBUG_EVENT_CLASS\|debug_break" tests/` 定位（重灾区：test_debug_ctx ~42 处 / test_v3_debug_anchor_kinds ~17 / test_diagnose_class_env ~21 / bb apps debug 测试）。修改方向：
1. 所有 `debug_break(...)` 调用删 `class_id=...` 实参。
2. 删 DEBUG_EVENT_CLASS 相关用例（env 设定/门匹配/门不匹配）；保留并确保存在"无 class 门"的正例（若原文件没有则新增，参考该文件现有 mock pydevd/breakpoint 的手法）：

```python
def test_no_class_gate_anchor_and_bar_sufficient(monkeypatch):
    """三门形态:DEBUG_ANCHOR_KIND + bar 命中即 fire,无任何 class 维度(spec 2026-08-14 §2.3)。"""
    # 参考 file 内既有 env/mock 手法:设 DEBUG_MODE=1/DEBUG_BAR_RANGE/DEBUG_ANCHOR_KIND,
    # monkeypatch pydevd.settrace 记录调用,调 debug_break(bar, anchor_kind='gate')
    # (无 class_id 参数),断言 settrace 被调用;再调 debug_break(bar, anchor_kind='end')
    # 断言不被调用。
```

3. `test_diagnose_class_env.py` 整文件测的是 DEBUG_EVENT_CLASS env 通道——**删除该文件**（通道已删）。

- [ ] **Step 2: 跑测试确认 RED**

Run: `uv run pytest tests/path2/test_debug_ctx.py -x -q`（或 Step 1 定位的主文件）
Expected: FAIL（debug_break 仍要求 class_id kwarg → TypeError）

- [ ] **Step 3: debug_ctx.py 三门化**

`path2/debug_ctx.py`：
1. 模块 docstring 删 DEBUG_EVENT_CLASS 两行（:6-7）。
2. 删 `_read_class_id`（:34-37）。
3. 签名（:40）改：

```python
def debug_break(i: int, *, anchor_kind: str,
                stop_at_frame: Optional[Any] = None) -> None:
```

4. docstring：v4 段（:44-47）改"双 required keyword-only 参数"为单参数描述（anchor_kind 5 元 enum 保留），删 class_id 行；判据（:50-53）改为：

```
    判据(短路顺序):
      _DEBUG_MODE ∧ bar in range
        ∧ (DEBUG_ANCHOR_KIND 未设 or 匹配 anchor_kind)
```

（删 class 门两行。）
5. 删 class 门（:79-81 三行 `required_cid = ...` / `if required_cid ...` / `return`）。

- [ ] **Step 4: atoms 30 埋点删 class_id kwarg**

Run: `grep -n "class_id=" path2/atoms/*.py`
现在剩余命中应全部是 debug_break 埋点 → 删除各 `class_id=XXX.__name__` kwarg（含 `throwback_v1.py:120` 的 `debug_break(gate_idx, anchor_kind='gate', class_id=..., stop_at_frame=...)` 形态，删中间 kwarg 保留其余）。
Expected: `grep -c "class_id=" path2/atoms/*.py` 全部为 0。

- [ ] **Step 5: serialize.py + api.py 改名 debug_enabled_nodes**

`path2_web/serialize.py`（:267-284）：局部变量与返回键 `debug_enabled_classes` → `debug_enabled_nodes`（注释同步："v4 契约 C:派生 debug_enabled_nodes(has_debug_hooks=True 的 detector 的 node_id 去重,拓扑序)"）。
`path2_web/api.py:245`：`pattern_spec["debug_enabled_classes"] = fresh["debug_enabled_classes"]` 两处键名 → `debug_enabled_nodes`。

- [ ] **Step 6: 测试同步 + 全量后端绿**

`grep -rln "debug_enabled_classes" tests/ path2_web_ui/` 后端侧改 `debug_enabled_nodes`（前端 types.ts 归 Task 3）。
Run: `uv run pytest -x -q`（全量）
Expected: 0 failed / 2 skipped（Task 1 记录的 debug-class 失败清单全部转绿）。

- [ ] **Step 7: Commit**

```bash
git add path2/debug_ctx.py path2/atoms/ path2_web/serialize.py path2_web/api.py tests/
git commit -m "feat: debug 四门→三门删 class 门(30 埋点)+debug_enabled_nodes 改名,顺手修复右键 debug 双 bug"
```

---

### Task 3: 前端契约同步（node 化 + 双 bug 前端侧 + 命名链）

**Files:**
- Modify: `path2_web_ui/src/api.ts`（getTimeDiagnose 删 eventClass）
- Modify: `path2_web_ui/src/types.ts`（TimePayload.all_nodes / debug_enabled_nodes / 注释）
- Modify: `path2_web_ui/src/stores/view.ts`（currentTimeEventClass→currentDiagnoseNode、triggerEventDebug 删 eventClass 实参、DEBUG_ENABLED_CLASSES→DEBUG_ENABLED_NODES、triggerTimeQuery 注释）
- Modify: `path2_web_ui/src/components/FailedAttemptsCard.vue`（node_id 显示 + node filter + props/emit）
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`（debug 卡片 node_id + 过滤链命名）
- Modify: `path2_web_ui/src/components/KlineChart.vue`（透传处命名，`grep -n "currentTimeEventClass\|eventClass" path2_web_ui/src/components/KlineChart.vue` 定位）
- Test: `path2_web_ui/tests/` 下 `grep -rln "eventClass\|class_id\|all_classes\|currentTimeEventClass\|className\|debug_enabled_classes" tests/` 命中文件

**Interfaces:**
- Consumes: Task 1 后端契约（`node` 参数 / `all_nodes` / gf.node_id）；Task 2（DEBUG_EVENT_CLASS 通道已删、debug_enabled_nodes）
- Produces: 前端类型与后端契约同名同义（TimePayload.all_nodes、debug_enabled_nodes）；FailedAttemptsCard props `node: string` / emit `update:node`

- [ ] **Step 1: 改前端测试 RED**

对 Step Files 列出的测试文件：fixture 里 TimePayload 的 `all_classes`→`all_nodes`；断言 `a.class_id`→`a.node_id`；`eventClass`/`update:event-class`→`node`/`update:node`；`debugTarget.className`→`node_id`；`triggerEventDebug` 相关断言（KlineChart-debug-menu.spec）删第 7 参断言。
Run: `(cd path2_web_ui && npx vitest run)` → 相关用例 FAIL（组件尚未改）。

- [ ] **Step 2: api.ts**

`getTimeDiagnose`（:72-89）：签名删 `eventClass?: string,`；url 拼 `+ (eventClass ? ...)` 行删；函数头注释（:70-71）"eventClass 可选(按事件类名二次过滤)" 删。

- [ ] **Step 3: view.ts**

1. `const currentTimeEventClass = ref<string>('')`（:246）→ `const currentDiagnoseNode = ref<string>('')`，全文件 `grep -n "currentTimeEventClass" src/stores/view.ts` 消费点（含 :763 清零）同步。
2. `triggerTimeQuery`（:773-785）：注释"入口 A 请求恒不带 event_class…"改为"入口 A 请求恒不带 node 过滤(过滤是纯前端显示层,重新请求会让后端 node 过滤返回子集 → failedNodes 坍缩 → 下拉其他 node 置灰)"；getTimeDiagnose 调用参数位相应前移（删 eventClass 位）。
3. `triggerEventDebug`（:825 区域，`grep -n "triggerEventDebug" src/stores/view.ts`）：调用 `getTimeDiagnose(anchor.bar, anchor.bar, event.node_id, ...)` 的**第 7 实参（eventClass 位）删除**——双 bug 前端侧修复点（d64083be 曾误传 node_id 到 class 门）。
4. `DEBUG_ENABLED_CLASSES`（:127）→ `DEBUG_ENABLED_NODES`，注释（:124-126）"D8 · DEBUG_ENABLED_…" 同步。
5. debugTarget 构造处若有 `className` 字段 → 改 `node_id`（值 = event.node_id）。

- [ ] **Step 4: types.ts**

`grep -n "all_classes\|debug_enabled_classes\|event_class" src/types.ts`：TimePayload 字段 `all_classes: string[]` → `all_nodes: string[]`；`debug_enabled_classes` → `debug_enabled_nodes`（注释"字段名沿袭旧名,值已是 node_id"改为"debug 断点启用的 node_id 列表"）；:165 附近 scope=time 载荷注释同步。

- [ ] **Step 5: FailedAttemptsCard.vue**

script：props `eventClass: string` → `node: string`；emit `(e: 'update:node', v: string)`；过滤 `a.class_id === props.eventClass` → `a.node_id === props.node`；`failedClasses`→`failedNodes`（值 = `payload.failed_attempts` 的 gf.node_id 集）；`classOptions`→`nodeOptions`（源 `payload.all_classes`→`payload.all_nodes`）；残留保护 watch 同步命名。
template：header `<select class="event-class-filter" ...>` 逻辑不变（class 名 CSS 可留）；attempt 行 `<span class="class-id">{{ a.class_id }}</span>` → `<span class="node-id">{{ a.node_id }}</span>`（scoped CSS 选择器 `.class-id` 同步 `.node-id`）。
DetailSidebar.vue：`:event-class="view.currentTimeEventClass"` → `:node="view.currentDiagnoseNode"`、`@update:event-class="onTimeEventClassChange"` → `@update:node="onDiagnoseNodeChange"`；`onTimeEventClassChange` 函数体 `view.currentTimeEventClass = v` → `view.currentDiagnoseNode = v`；watch（:395）同步；debug 卡片 `Debugging <b>{{ debugTarget.className }}</b>` → `<b>{{ debugTarget.node_id }}</b>`（:36）。

- [ ] **Step 6: 三绿**

Run: `(cd path2_web_ui && npx vitest run)` → 除 baseline 4 failed（sidebar-result-list）外全过；`npx vue-tsc --noEmit` → 0；`npx vite build` → success。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/ path2_web_ui/tests/
git commit -m "feat: 前端契约 node 化(node_id 显示/node 过滤/命名链)+右键 debug 删 eventClass 实参"
```

---

### Task 4: TopoNode.class_id 删字段 + 文档/残渣/skill 同步

**Files:**
- Modify: `path2/dag/spec.py`（TopoNode 删 class_id 字段）
- Modify: `path2_apps/bb_v0/__init__.py`、`path2_apps/bb_v1/__init__.py`、`path2_apps/bb_v1/dag_spec.py`、`path2_apps/bb_v3/__init__.py`、`path2_apps/bb_v3/dag_spec.py`、`path2_apps/try_conplex_where/dag_spec.py:50`、`path2_apps/bottom_burst/dag_spec.py:60`（docstring 过时 class_id 文案）
- Modify: `scripts/gate_burst_2x2.py:94`（e.class_id→e.node_id）
- Modify: `.claude/skills/authoring-path2-detector/reference.md`、`.claude/skills/diagnose-event/detectors/throwback.md`、`.claude/skills/diagnose-event/detectors/throwback_v3.md`
- Test: 全量回归（本 task 无新测试，验收 = 回归绿 + grep 收敛）

**Interfaces:**
- Consumes: 无（TopoNode.class_id 已实证全库零读者）
- Produces: 终态（Task 5 的 grep 清零在本 task 后应达成）

- [ ] **Step 1: spec.py 删 TopoNode.class_id**

`grep -n "class_id" path2/dag/spec.py` 定位 TopoNode（非 NodeSpec）的字段与注释（:19-21 附近），删字段行及其注释行（注释自述"class_id 体系已消灭,字段名保留供 web 消费"——已无消费）。
Run: `uv run pytest tests/path2/dag/ -x -q` → GREEN（零读者实证复核：若有测试断言该字段，随删）。

- [ ] **Step 2: apps docstring 5+ 处文案**

`grep -rn "class_id" path2_apps/`：docstring 中描述旧身份体系的 class_id 文案改为 node_id/instance_id 语境（如"事件按 class_id 标识"→"事件按 instance_id/node_id 标识"）；非注释代码命中则逐一判断（预期为零——NodeSpec 无 class_id 可传）。

- [ ] **Step 3: gate_burst_2x2.py 修 stale**

`scripts/gate_burst_2x2.py:94` `e.class_id` → `e.node_id`（现状运行必 AttributeError）。
Run: `uv run python scripts/gate_burst_2x2.py --help 2>&1 | head -5`（或读脚本 main 确认入口无 argparse——按项目约定该脚本参数在 main() 头部声明；做语法级验证 `uv run python -c "import ast; ast.parse(open('scripts/gate_burst_2x2.py').read())"` 即可，若脚本需要数据则不真跑）。

- [ ] **Step 4: skill 文档同步**

1. `.claude/skills/authoring-path2-detector/reference.md`：`grep -n "class_id" .claude/skills/authoring-path2-detector/reference.md`（含 :97-99 stale 节仍在教已消灭的旧体系）——重写这些节为 instance_id/node_id 契约；在 §4（detector 编写规范节）补一句："产 gate failure 的 detector 不可被多 node 共享（gate_collector attach 侧会 raise）；埋点只需 `debug_break(bar, anchor_kind=...)`，无 class 维度。"
2. `.claude/skills/diagnose-event/detectors/throwback.md` 与 `throwback_v3.md`：按类名组织的标题/索引改按 node_id 组织（如"ThrowbackEventV1 的 gate"→"tb node 的 gate"），正文 class_id 引用全改 node_id。

- [ ] **Step 5: grep 收敛确认 + 全量回归**

Run: `grep -rn "class_id" path2/ path2_web/ path2_apps/ path2_web_ui/src/ scripts/ .claude/skills/authoring-path2-detector/ .claude/skills/diagnose-event/`
Expected: **零命中**（若残留，逐一清除后重跑）。
Run: `uv run pytest -x -q`（0 failed/2 skipped）+ `(cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build)`（前端 baseline 三绿口径）。

- [ ] **Step 6: Commit**

```bash
git add path2/dag/spec.py path2_apps/ scripts/gate_burst_2x2.py .claude/skills/
git commit -m "chore: TopoNode.class_id 死字段删除+apps docstring/脚本残渣/skill 文档 node 化(概念死亡三层收口)"
```

---

### Task 5: e2e 验收（右键 debug 双 bug 修复 + 入口 A node_id 显示）+ push

**Files:**
- 无代码修改（验收 task；若 e2e 暴露问题，回到对应 task 修复后重跑本 task）

**Interfaces:**
- Consumes: Task 1-4 全部产出
- Produces: spec §3 验收 4/5 的 e2e 证据 + 分支 push

- [ ] **Step 1: 起后端**

Run: `uv run python scripts/path2/run_path2_web.py`（后台；确认其端口/启动方式——读脚本 main() 头部声明）。若需 debug 后端（DEBUG_MODE=1）另起，按脚本内声明的 env 方式。等待启动完成日志。

- [ ] **Step 2: 入口 A e2e（playwright）**

用 playwright MCP：打开前端 → 加载含 APCX 的 scan → 主图 brush 框选一段 → 断言 FailedAttemptsCard 出现且 attempt 行显示 `tb`/`bo`（node_id），下拉选项为 node_id 全集（无 `ThrowbackEventV1` 等类名）。截图留档。

- [ ] **Step 3: 右键 debug e2e（双 bug 修复验收）**

playwright：右键 tb marker → 菜单出现 entry/confirm/end 锚项 → 点任一锚 → 断言 debug 卡片显示 node_id（`tb`）且流程不再恒空（debug-done/断点释放提示出现；后端日志无 `DEBUG_EVENT_CLASS` 相关行为）。若 pydevd pause 无法自动化断言，以「/diagnose 响应 200 + 卡片正常流转 + 后端无 class 门匹配日志」为验收面，截图留档并注明。完成后 `(cd path2_web_ui && rm -rf .playwright-mcp/*)`（playwright 卫生约定）。

- [ ] **Step 4: 终态 grep 清零 + 双侧全量回归**

Run: `grep -rn "class_id" path2/ path2_web/ path2_apps/ path2_web_ui/src/ scripts/ .claude/skills/authoring-path2-detector/ .claude/skills/diagnose-event/` → 零命中（exit 1）
Run: `uv run pytest -q`（0 failed/2 skipped）；`(cd path2_web_ui && npx vitest run)`（4 failed baseline 其余全过）+ vue-tsc 0 + build success。

- [ ] **Step 5: Commit（若有 e2e 修复）+ push**

```bash
git push origin instance-id-refactor
```

停步，只报告分支名（沿用交付约定：**禁止开 PR**）。

---

## Self-Review 记录

- **Spec coverage**：spec §2.1→Task 4 Step 1；§2.2→Task 1；§2.3→Task 2；§2.4→Task 1/2（api+serialize+diagnose）；§2.5→Task 3；§2.6→Task 4；§2.7→Task 4 Step 4；§3 验收 1→Task 5 Step 4、验收 2/3→各 task 步骤内、验收 4/5→Task 5 Steps 2-3、验收 6→Task 1 Step 1、验收 7→grep 范围含 skill。无缺口。
- **Placeholder 扫描**：无 TBD/TODO；机械替换步骤均给 grep 命令 + 目标形态 + 验收口径。
- **类型一致性**：`node_id: str = ''`（Task 1）与 Task 3 前端 `a.node_id` 同名；`all_nodes`/`node`/`debug_enabled_nodes` 前后端一致；`debug_break` 新签名（Task 2）与 atoms 埋点删除（Task 2 Step 4）、测试（Step 1）一致。
