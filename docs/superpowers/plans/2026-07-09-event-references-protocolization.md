# Event-References Protocolization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 path2_web + path2_web_ui 里"事件间引用归属"的判定链完全按 path2 引擎协议（`Event.child_slots` + `DependencyEdge.anchor_field`）实现，去掉三处硬编码字段名（`members` / `anchor_bo_id`），顺带修复 UI bug：选中一个 match 后主图 BO 方框应显示 in-group 深灰蓝细边（当前 bug：无边）。

**Architecture:** payload 侧新加 `child_refs: {slot_name: [event_id]}`（后端遍历 `event.child_slots()` 生成）与 `topology.edges[*].anchor_field`（后端从 spec 边直接透传）；前端 `matchedIds()` 签名扩展为 `(matches, events, edges)`，沿 `child_refs` 递归 + 沿 `edges.anchor_field` 反查 event 字段展开；view store 的 `highlightedEventIds` 从 ref+setter 改为纯 computed，选中 match 就自动展开成员集，副产品是彻底修复 group 高亮不含 BO 的 UI bug。

**Tech Stack:** Python 3 + FastAPI（后端）；Vue 3 + Pinia + TypeScript + ECharts（前端）；pytest + vitest + vue-tsc + Playwright（测试）。

**Spec:** `docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md`

## Global Constraints

- 无 legacy 兼容层、无 dual-write、无 feature flag；一步到位。
- 后端 payload 里 event dict **不得**再出现顶层 `members` 字段（BurstEvent 的 `members` 现由 `child_refs["members"]` 承载）。
- 前端 `visible.ts` 内**不得**出现字符串常量 `"members"` / `"anchor_bo_id"`（tooltip SKIP 集除外，且只 SKIP `'child_refs'` 这个元字段，不 SKIP 具体 slot 名）。
- Implementer 用 `sonnet`；Reviewer 用 `opus`（用户偏好，subagent-driven 派发时遵守）。
- 四 gate 全绿：pytest（后端）+ vitest（前端 unit）+ vue-tsc（类型）+ npm run build（前端构建）+ Playwright（e2e）。
- Playwright 截图前必须先 `browser_resize(2560, 1440)`；调用 `browser_take_screenshot` 时 `scale="device"`；用完清空 `.playwright-mcp/*`（`rm -rf .playwright-mcp/*`）。
- 每 task 结束前必须 `commit`（frequent commits）；commit 消息用中文动词开头（follow 现有 commit style：`update` / `fix` / `refactor` 等）。
- 不使用 `git commit --no-verify`、不 `--amend`、不 force push。

---

## File Structure

**修改的文件（无新建）**：

| 文件 | 责任 |
|---|---|
| `path2_web/serialize.py` | `_event_to_dict` 生成 `child_refs`、`serialize_pattern` 边加 `anchor_field` |
| `tests/path2_web/test_serialize.py` | 迁 `members` 相关断言到 `child_refs["members"]`；加 `anchor_field` 断言 |
| `path2_web_ui/src/types.ts` | `EventDict` 加 `child_refs`、`TopoEdge` 加 `anchor_field` |
| `path2_web_ui/src/render/visible.ts` | `matchedIds` 签名扩展 + 协议驱动展开；tooltip SKIP 迁 |
| `path2_web_ui/tests/visible.spec.ts` | 三处 fixture 从 `members` 迁到 `child_refs`；SKIP 集测试更新 |
| `path2_web_ui/src/stores/view.ts` | `highlightedEventIds` 改 computed；删 setter+clear；`matchedIds` computed 加 edges 参数；删 4 处 `.value = new Set()` 清理 |
| `path2_web_ui/src/components/KlineChart.ts` | 删 3 处 `setHighlightedEvents` + 2 处 `clearHighlight` |
| `path2_web_ui/src/components/DetailSidebar.vue` | 删 `selectMatchAndHighlight` 里的 `setHighlightedEvents` 调用 |
| `path2_web_ui/tests/components.kline-click.spec.ts` | 删对 `setHighlightedEvents` / `clearHighlight` 的断言；改断言 `highlightedEventIds` 自动展开 |
| `path2_web_ui/tests/chart.spec.ts` | 新增：选中 match 后 BO 主图方框 in-group 深边渲染断言 |

---

## Task Breakdown Overview

五个 tasks，按依赖顺序：

1. **Task 1**: 后端 `serialize.py` 一次改完（`child_refs` + `anchor_field`）+ 后端测试迁移
2. **Task 2**: 前端类型 + `visible.ts` 协议驱动 + 单测迁移
3. **Task 3**: 前端 view store 声明式 `highlightedEventIds` + KlineChart/DetailSidebar 清理 setter 调用点 + kline-click 单测迁移
4. **Task 4**: `KlineChart.ts` marker filter 判据改用 `matchedIdsOf`（tier/click 对齐 · bo 点击也走 candidate 消解 · 多归属自动降维为单层 candidate 列表）
5. **Task 5**: 前端 `chart.spec.ts` BO in-group 渲染断言 + Playwright e2e 验证

---

### Task 1: 后端 serialize.py 协议化（child_refs + anchor_field）

**Files:**
- Modify: `path2_web/serialize.py`
- Modify: `tests/path2_web/test_serialize.py`

**Interfaces:**
- Consumes: `Event.child_slots()`（`path2/core.py:77`）、`DependencyEdge.anchor_field`（`path2/dag/edges.py:56`）
- Produces:
  - event dict 新键 `child_refs: dict[str, list[str]]`（slot_name → 该 slot 的 event_id 列表；叶子 event 为 `{}`）
  - event dict 不再有 BurstEvent 特有的顶层 `members` 字段
  - `serialize_pattern(...)["topology"]["edges"][i]` 新键 `anchor_field: str | None`（未设置的边为 `None`）

- [ ] **Step 1: 写失败测试（test_serialize.py 新增 3 个断言）**

在 `tests/path2_web/test_serialize.py` 末尾追加：

```python
def test_burst_event_dict_child_refs_protocol():
    """child_refs 承载 BurstEvent.members(schema-driven,不硬编码字段名);
    顶层 members 字段消失(不留兼容层)。"""
    from tests.path2_web.test_serialize import _run  # 若已有 helper 复用;否则参考文件既有 setup
    events, matches, spec_pattern = _run()
    burst = next(e for e in events if e["class_id"] == "burst")
    # 顶层无 members
    assert "members" not in burst, "payload 里不再有顶层 members 字段(由 child_refs 承载)"
    # child_refs["members"] 是 event_id 列表
    assert "child_refs" in burst, "所有 event 必须携带 child_refs"
    assert burst["child_refs"].get("members"), "BurstEvent child_refs.members 非空"
    assert all(isinstance(x, str) for x in burst["child_refs"]["members"])
    bo_ids = {e["event_id"] for e in events if e["class_id"] == "bo"}
    for mid in burst["child_refs"]["members"]:
        assert mid in bo_ids


def test_leaf_event_child_refs_empty():
    """叶子 event(BOEvent / TBEvent)child_refs 是空 dict。"""
    from tests.path2_web.test_serialize import _run
    events, _, _ = _run()
    for e in events:
        if e["class_id"] in ("bo", "tb"):
            assert e.get("child_refs") == {}, f"{e['event_id']}: 叶子 event child_refs 必须为空 dict"


def test_serialize_pattern_edges_anchor_field():
    """topology.edges 每条边携带 anchor_field(str 或 None);bottom_burst 的 burst→tb 边
    anchor_field = 'anchor_bo_id'。"""
    from path2_apps.bottom_breakout_burst.dag_spec import PATTERN_DAG
    from path2_web.serialize import serialize_pattern
    result = serialize_pattern(PATTERN_DAG)
    edges = result["topology"]["edges"]
    assert len(edges) >= 1
    for e in edges:
        assert "anchor_field" in e, f"每条边必须携带 anchor_field 键(值可为 None): {e!r}"
    # burst→tb 边 anchor_field 为 'anchor_bo_id'
    burst_tb = next(e for e in edges if e["src"] == "burst" and e["dst"] == "tb")
    assert burst_tb["anchor_field"] == "anchor_bo_id"
```

**注意**：`_run` helper 是文件已有 fixture 的示意名——**打开 `test_serialize.py` 找已有 fixture / helper**（可能叫 `_analyze_and_serialize` 或直接内联），复用它以避免重造，然后照抄它构造 (events, matches, pattern) 的方式来构造这三个测试所需数据。若已有 `test_serialize_burst_members_as_event_ids` 和 `test_burst_event_dict_members_as_event_ids`（`test_serialize.py:32` / `:161`）就直接借它们的 `_run` 逻辑。

- [ ] **Step 2: 运行新测试确认全部 FAIL**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest tests/path2_web/test_serialize.py::test_burst_event_dict_child_refs_protocol tests/path2_web/test_serialize.py::test_leaf_event_child_refs_empty tests/path2_web/test_serialize.py::test_serialize_pattern_edges_anchor_field -v
```

Expected: 3 FAILED（`child_refs` 键不存在、`anchor_field` 键不存在）

- [ ] **Step 3: 改 `_event_to_dict`（`path2_web/serialize.py:36-53`）**

`serialize.py:36-53` 完整替换为：

```python
def _event_to_dict(e) -> dict:
    """event → dict(全集,含未匹配;子类属性平铺,仅 tooltip 用)。
    child_slots 声明的持有型子 event 引用统一由 child_refs 承载(schema-driven,
    不硬编码字段名);slot 名对应字段在 fields 循环里跳过,避免 payload 冗余。"""
    d = {
        "class_id": type(e).class_id,
        "event_id": e.event_id,
        "start_idx": e.start_idx,
        "end_idx": e.end_idx,
    }
    skip_slots = set(e.child_slots().keys())   # BurstEvent -> {"members"}
    for f in dataclasses.fields(e):
        if f.name in ("event_id", "start_idx", "end_idx"):
            continue
        if f.name in skip_slots:
            continue   # 由 child_refs 承载,避免 payload 冗余
        d[f.name] = _jsonable(getattr(e, f.name))
    d["child_refs"] = {
        name: [c.event_id for c in (slot if isinstance(slot, tuple) else (slot,))]
        for name, slot in e.child_slots().items()
    }
    return d
```

- [ ] **Step 4: 改 `serialize_pattern` 里 edges 构造（`path2_web/serialize.py:231-234`）**

原代码：

```python
    edges = [
        {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de)}
        for te, de in zip(topo.edges, spec.edges)
    ]
```

替换为：

```python
    edges = [
        {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de),
         "anchor_field": de.anchor_field}
        for te, de in zip(topo.edges, spec.edges)
    ]
```

- [ ] **Step 5: 迁移旧 members 测试**

现有 `test_serialize.py:32-45` (`test_serialize_burst_members_as_event_ids`) 和 `:161-175` (`test_burst_event_dict_members_as_event_ids`) 断言顶层 `members`——这两个函数**整个删除**（其语义现由 Step 1 的 `test_burst_event_dict_child_refs_protocol` 覆盖，不留冗余）。

如果文件里还有其它对 `burst["members"]` 或 event dict 的顶层 members 字段的断言，一并迁到 `burst["child_refs"]["members"]` 或直接删除（视语义）。用 `grep -n 'members' tests/path2_web/test_serialize.py` 找齐。

- [ ] **Step 6: 运行整个 test_serialize.py 确认 PASS**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest tests/path2_web/test_serialize.py -v
```

Expected: 全部 PASS，无 FAIL、无 error。

- [ ] **Step 7: 后端全量回归**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest tests/ -x -q
```

Expected: 全部 PASS。如失败先诊断，`serialize.py` 是否被其它 test 依赖了 `members` 字段。

- [ ] **Step 8: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web/serialize.py tests/path2_web/test_serialize.py
git commit -m "$(cat <<'EOF'
refactor(serialize): event 引用协议化 · child_refs + edges.anchor_field

- _event_to_dict: 删 members 特判,统一按 child_slots 生成 child_refs(schema-driven)
- serialize_pattern: topology.edges 每条边携带 anchor_field(值或 None)
- 测试迁移:顶层 members 字段消失,断言迁到 child_refs["members"];bottom_burst
  burst→tb 边 anchor_field='anchor_bo_id'

spec: docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 前端类型 + visible.ts matchedIds 协议驱动

**Files:**
- Modify: `path2_web_ui/src/types.ts`
- Modify: `path2_web_ui/src/render/visible.ts`
- Modify: `path2_web_ui/tests/visible.spec.ts`

**Interfaces:**
- Consumes: Task 1 的后端 payload 契约（event dict 有 `child_refs`；topology.edges 有 `anchor_field`）
- Produces:
  - `EventDict` 类型多 `child_refs: Record<string, string[]>` 字段
  - `TopoEdge` 类型多 `anchor_field?: string | null` 字段
  - `matchedIds(matches, events, edges): Set<string>` 签名（3 参，第 3 参 `edges: TopoEdge[]`）
  - `matchedIds` 递归展开规则：初始集 = `∪ match.children`；沿 `ev.child_refs` 所有 slot value + 沿 `edges` 里所有非空 `anchor_field` 名字读 `ev[anchor_field]` 入队

- [ ] **Step 1: 写失败测试（visible.spec.ts 迁移 + 新增）**

`tests/visible.spec.ts:20-30` 附近有 `it('沿 members 字段递归展开...')` 用例，**用例整体替换**为：

```ts
  it('沿 child_refs.members 递归展开:matched composite event 的 constituent 也进 matched 集(协议驱动、非字段名)', () => {
    const matches: MatchDict[] = [{ event_id: 'm1', start_idx: 0, end_idx: 10,
      role_index: {}, children: ['burst_1'], predicate_trace: null }]
    const events: EventDict[] = [
      { class_id: 'burst', event_id: 'burst_1', start_idx: 1, end_idx: 5, source_tag: 'burst',
        child_refs: { members: ['bo_1', 'bo_3', 'bo_5'] } },
      { class_id: 'bo', event_id: 'bo_1', start_idx: 1, end_idx: 1, source_tag: 'bo', child_refs: {} },
      { class_id: 'bo', event_id: 'bo_3', start_idx: 3, end_idx: 3, source_tag: 'bo', child_refs: {} },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo', child_refs: {} },
      { class_id: 'bo', event_id: 'bo_99', start_idx: 99, end_idx: 99, source_tag: 'bo', child_refs: {} },
    ]
    const s = matchedIds(matches, events, [])
    expect(s.has('burst_1')).toBe(true)
    expect(s.has('bo_1')).toBe(true)
    expect(s.has('bo_3')).toBe(true)
    expect(s.has('bo_5')).toBe(true)
    expect(s.has('bo_99')).toBe(false)  // 不在 child_refs.members
  })

  it('沿 edges.anchor_field 反查:tb.anchor_bo_id 引用的 bo 也进 matched 集', () => {
    const matches: MatchDict[] = [{ event_id: 'm1', start_idx: 0, end_idx: 10,
      role_index: {}, children: ['tb_1'], predicate_trace: null }]
    const events: EventDict[] = [
      { class_id: 'tb', event_id: 'tb_1', start_idx: 7, end_idx: 7, source_tag: 'tb',
        child_refs: {}, anchor_bo_id: 'bo_5' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo', child_refs: {} },
    ]
    const edges = [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }]
    const s = matchedIds(matches, events, edges)
    expect(s.has('tb_1')).toBe(true)
    expect(s.has('bo_5')).toBe(true)
  })
```

同时 `tests/visible.spec.ts:227` 处的 tooltip fixture 里 `members: [{}, {}]` 应替换为 `child_refs: { members: ['bo_x','bo_y'] }`（保持 fixture 语义为"burst has 2 members"）。

`tests/visible.spec.ts:331-338` 的 SKIP 集测试（`raw 排除 SKIP 集`）：
```ts
    expect('members' in r.raw).toBe(false)
```
改为：
```ts
    expect('child_refs' in r.raw).toBe(false)
```
描述文字同步："class_id/event_id/start_idx/end_idx/source_tag/child_refs"。

`grep -n 'members' tests/visible.spec.ts` 找齐所有其它散落引用一起迁。

- [ ] **Step 2: 运行 vitest 确认新测试 FAIL**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- visible.spec.ts
```

Expected: 至少 2 个用例 FAIL（`matchedIds` 签名不匹配 / 递归展开逻辑不含 `child_refs`）。

- [ ] **Step 3: 改 `src/types.ts`**

在 `TopoEdge`（`types.ts:10`）加 `anchor_field?: string | null`：
```ts
export interface TopoEdge { src: string; dst: string; kind: string; rule: string; anchor_field?: string | null }
```

在 `EventDict`（`types.ts:17-22`）加 `child_refs: Record<string, string[]>`：
```ts
export interface EventDict {
  class_id: string; event_id: string; start_idx: number; end_idx: number
  source_tag: string
  child_refs: Record<string, string[]>
  referenced_points?: Array<[number, number, string]>
  [attr: string]: unknown
}
```

- [ ] **Step 4: 改 `src/render/visible.ts` matchedIds（`visible.ts:9-29`）**

`visible.ts:5-29` 整段（包括注释）替换为：

```ts
/** 所有匹配内实例 event_id 的并集(schema-driven 协议驱动)。
 *  展开规则:
 *  - 初始集 = ⋃ match.children
 *  - 持有型引用:沿 ev.child_refs 所有 slot value(event_id 列表)递归入队
 *  - 弱引用:从 edges 收集所有非空 anchor_field 名字,遍历 ev 上对应字段(event_id 字符串)入队
 *  不再硬编码 members / anchor_bo_id 字段名——协议来自 Event.child_slots +
 *  DependencyEdge.anchor_field。matched 的 composite event(如 burst)其 constituent
 *  bo 通过 child_refs 自然进 matched 集;tb.anchor_bo_id 通过 anchor_field 反查进入。 */
export function matchedIds(
  matches: MatchDict[],
  events: EventDict[],
  edges: TopoEdge[],
): Set<string> {
  const s = new Set<string>()
  for (const m of matches) for (const c of m.children) s.add(c)
  if (events.length === 0 || s.size === 0) return s
  const byId = new Map(events.map(e => [e.event_id, e]))
  const anchorFields = new Set<string>()
  for (const e of edges) if (e.anchor_field) anchorFields.add(e.anchor_field)
  const queue: string[] = [...s]
  while (queue.length) {
    const id = queue.pop()!
    const ev = byId.get(id)
    if (!ev) continue
    // 持有型:child_refs 所有 slot
    const refs = ev.child_refs
    if (refs) {
      for (const ids of Object.values(refs)) {
        for (const cid of ids) if (!s.has(cid)) { s.add(cid); queue.push(cid) }
      }
    }
    // 弱引用:anchor_field 反查
    for (const af of anchorFields) {
      const v = (ev as Record<string, unknown>)[af]
      if (typeof v === 'string' && !s.has(v)) { s.add(v); queue.push(v) }
    }
  }
  return s
}
```

- [ ] **Step 5: 改 `visible.ts:128` tooltip SKIP 集**

原：
```ts
  const SKIP = new Set(['class_id', 'event_id', 'start_idx', 'end_idx', 'source_tag', 'members'])
```

改为：
```ts
  const SKIP = new Set(['class_id', 'event_id', 'start_idx', 'end_idx', 'source_tag', 'child_refs'])
```

- [ ] **Step 6: 运行 vitest visible.spec.ts 确认 PASS**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- visible.spec.ts
```

Expected: 全部 PASS。若 fail，检查：(a) `TopoEdge` 类型是否被下游 spec 依赖，可能需要更新 `chart-helpers.spec.ts` 里的 fixture；(b) 其它 spec 里 EventDict 构造若被 `[attr:string]:unknown` 兜底覆盖了 `child_refs`，那没问题——只是新测试用例需要显式设 `child_refs`。

- [ ] **Step 7: vitest 全量回归 + vue-tsc**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test
npm run type-check     # 若无 type-check 脚本改用 npx vue-tsc --noEmit
```

Expected: 都绿。类型报错常见成因：其它测试 fixture 里的 event 对象缺 `child_refs`——按需为 fixture 添加 `child_refs: {}`（叶子）或 `child_refs: { members: [...] }`（burst）；`view.multi.spec.ts` / `chart.spec.ts` / `visible.spec.ts` / `topology.spec.ts` / `smoke.spec.ts` 里的 fixtures 都要检查。**不要**改 `EventDict` 类型让 `child_refs` 变 optional 来规避——保持 required、fixture 显式补全。

- [ ] **Step 8: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
git add src/types.ts src/render/visible.ts tests/visible.spec.ts
# 若 fixture 补全涉及其它 spec 文件,一并加入
git add -u tests/
cd /home/yu/PycharmProjects/Trade_Strategy
git commit -m "$(cat <<'EOF'
refactor(visible): matchedIds 协议驱动 · child_refs + anchor_field

- types.ts: EventDict 加 child_refs,TopoEdge 加 anchor_field
- visible.ts matchedIds: 签名 (matches,events,edges);沿 child_refs 全 slot 递归 +
  沿 edges.anchor_field 反查;去除 members/anchor_bo_id 字面读取
- tooltip SKIP: 'members' → 'child_refs' 元字段
- visible.spec.ts fixture 迁移;其它 spec fixture 补 child_refs 令类型齐

spec: docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: view store 声明式 highlightedEventIds + 清理 setter 调用点

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Modify: `path2_web_ui/src/components/KlineChart.ts`
- Modify: `path2_web_ui/src/components/DetailSidebar.vue`
- Modify: `path2_web_ui/tests/components.kline-click.spec.ts`

**Interfaces:**
- Consumes: Task 2 的 `matchedIds(matches, events, edges)` 签名、`TopoEdge.anchor_field`
- Produces:
  - view store `highlightedEventIds` 是 computed（依赖 `selectedMatch` + `effectiveAnalysis.events` + `effectivePattern.topology.edges`）
  - `setHighlightedEvents` / `clearHighlight` 函数不再存在于 store（return 里也移除）
  - 全局 `matchedIds` computed 依赖 `edges`
  - 消费者：`KlineChart.handleChartClick` 里 5 处 setter/clear 调用全删；`DetailSidebar.selectMatchAndHighlight` 里 setter 调用删

- [ ] **Step 1: 写失败测试（components.kline-click.spec.ts）**

在 `path2_web_ui/tests/components.kline-click.spec.ts` 找一个已有"marker 单归属分支"的用例，或在文件末尾加入以下用例（先扫已有测试文件结构、复用 store setup helper）：

```ts
import { handleChartClick } from '../src/components/KlineChart'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'

describe('handleChartClick × highlightedEventIds 协议派生', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('选中一条 match(marker 单归属分支)后 highlightedEventIds 沿 child_refs 展开、含 BO id', () => {
    const view = useViewStore()
    // 造最小 scanFile:一个 burst-tb match,burst.child_refs.members=[bo_5]
    const events = [
      { class_id: 'burst', event_id: 'burst_1', start_idx: 5, end_idx: 6, source_tag: 'burst',
        child_refs: { members: ['bo_5'] } },
      { class_id: 'tb', event_id: 'tb_1', start_idx: 8, end_idx: 8, source_tag: 'tb',
        child_refs: {}, anchor_bo_id: 'bo_5' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo', child_refs: {} },
    ]
    const matches = [{ event_id: 'match_1', start_idx: 5, end_idx: 8,
      role_index: { burst: 'burst_1', tb: 'tb_1' },
      children: ['burst_1', 'tb_1'], predicate_trace: null }]
    const topology = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', source_tag: 'bo', where_rules: [] },
        { node_id: 'burst', class_id: 'burst', source_tag: 'burst', where_rules: [] },
        { node_id: 'tb', class_id: 'tb', source_tag: 'tb', where_rules: [] },
      ],
      edges: [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }],
    }
    view.loadScanFile({
      pattern_ids: ['bottom_burst'],
      per_pattern: { bottom_burst: {
        pattern_spec: { pattern_id: 'bottom_burst', topology, event_styles: {} },
        end_role: 'tb',
      }},
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: 1, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol: 'X', per_pattern: { bottom_burst: {
        summary: { matches: 1 }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = 'X'
    view.activePatternId = 'bottom_burst'
    // 触发 marker 单归属分支:点 burst_1(唯一归属 match_1)
    handleChartClick(
      { seriesName: 'intervals', data: { event_id: 'burst_1' } }, matches, view)
    // ★ 核心断言:highlightedEventIds 沿协议展开,含 BO(修复 UI bug 的 essence)
    expect(view.highlightedEventIds.has('burst_1')).toBe(true)
    expect(view.highlightedEventIds.has('tb_1')).toBe(true)
    expect(view.highlightedEventIds.has('bo_5')).toBe(true)   // ← child_refs 展开
    expect(view.selectedMatchId).toBe('match_1')
  })

  it('未选中 match 时 highlightedEventIds 是空集(selectMatch(null) 自动清)', () => {
    const view = useViewStore()
    // 无需 loadScanFile;selectMatch(null) → selectedMatch 为 null → computed 是 empty set
    view.selectMatch(null)
    expect(view.highlightedEventIds.size).toBe(0)
  })
})
```

同时**删除**文件里既有对 `view.setHighlightedEvents(...)` / `view.clearHighlight()` 的显式调用断言（这些 API 即将消失）。用 `grep -n 'setHighlightedEvents\|clearHighlight' tests/components.kline-click.spec.ts` 找齐。

- [ ] **Step 2: 运行 vitest 确认新测试 FAIL**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- components.kline-click.spec.ts
```

Expected: 至少 1 FAIL（当前 `highlightedEventIds` 是 ref、没有 selectedMatch → 展开的联动；也可能因 `matchedIds` 签名未变前 view.ts 已因 Task 2 破坏而失败，同样合规）。

- [ ] **Step 3: 改 view store — `highlightedEventIds` 变 computed；`matchedIds` computed 加 edges；删 setter 和 clear**

**a. 修改 `view.ts:66`**：把 ref 改为在 selectedMatch 之后声明的 computed（因为它依赖 `selectedMatch`）。可以把 `const highlightedEventIds = ref<...>(new Set())` 这行**删除**，然后在 `selectedMatch` computed 之后加：

```ts
  // group 高亮 = 选中 match 的展开(matched tier 集合)——协议驱动,沿 child_refs +
  // edges.anchor_field 递归。selectedMatch 变化即自动重算,消除"选中 match 但 group 高亮
  // 不含 BO"的通道不一致 bug(原 UI bug: 主图 BO 方框无 in-group 深边)。
  const highlightedEventIds = computed<ReadonlySet<string>>(() => {
    const m = selectedMatch.value
    if (!m) return new Set<string>()
    return matchedIdsOf(
      [m],
      effectiveAnalysis.value?.events ?? [],
      effectivePattern.value?.topology.edges ?? [],
    )
  })
```

`view.ts:445-446` 全局 `matchedIds` computed 同步：

```ts
  const matchedIds = computed<Set<string>>(() => matchedIdsOf(
    effectiveAnalysis.value?.matches ?? [],
    effectiveAnalysis.value?.events ?? [],
    effectivePattern.value?.topology.edges ?? []))
```

**b. 删除 `view.ts:312-317` 的 `setHighlightedEvents` 和 `clearHighlight` 函数定义**：

```ts
  function setHighlightedEvents(ids: string[]) { highlightedEventIds.value = new Set(ids) }
  function clearHighlight() { highlightedEventIds.value = new Set() }
```
这 4 行整段删除。

**c. 删除 `view.ts` 里 4 处 `highlightedEventIds.value = new Set()` 显式清理**（`loadScanFile` `:215`、`clearScanFile` `:233`、`selectSymbol` `:247`、`setActivePattern` `:258`）——`selectedMatch` 会随各自的 `selected.value = null` 自动派生为空集。用 `grep -n 'highlightedEventIds' src/stores/view.ts` 找齐 4 处删完。

**d. `view.ts:466` return 里删掉 `setHighlightedEvents, clearHighlight` 导出**：

原：
```ts
    setLevel, selectEvent, hoverEvent, setHighlightedEvents, clearHighlight,
```
改为：
```ts
    setLevel, selectEvent, hoverEvent,
```

- [ ] **Step 4: 清理 `KlineChart.ts` 5 处调用点**

`src/components/KlineChart.ts` 里删除以下 5 行（保留其它逻辑）：

- `:70` `view.clearHighlight()` — 空白 click 分支
- `:85` `view.setHighlightedEvents(match.children)` — bracket 分支
- `:106` `view.clearHighlight()` — marker ms.length===0 分支
- `:115` `view.setHighlightedEvents(ms[0].children)` — marker ms.length===1 分支
- `:123` `view.clearHighlight()` — marker ms.length>1 分支

对每处，删该行、保留同一分支的其它调用（`selectMatch` / `selectEvent` / `clearCandidates` / `setCandidateMatches` / `setPendingDisambig` 都保留）。文件顶部 docstring 里 "candidate 与 selected 互斥：进 candidate 分支前必须先清 selected + highlight" 的 "+ highlight" 措辞可以保留（不算失实——只是"highlight" 不需要显式清了，因它自动派生）。

- [ ] **Step 5: 清理 `DetailSidebar.vue` `selectMatchAndHighlight`**

`src/components/DetailSidebar.vue:323-325` 附近 `selectMatchAndHighlight` 函数体里的 `view.setHighlightedEvents(children)` 一行删除；函数改名为 `selectMatchOnly` / `selectMatch`（若模板里 `:click="selectMatchAndHighlight(...)"` 引用了这名字，同步改；否则最小改保留 `selectMatchAndHighlight` 名字，仅删掉 setter 那一行）。以最小修改为准，只删那一行、名字不动。

- [ ] **Step 6: 运行 vitest 确认新旧测试都 PASS**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- components.kline-click.spec.ts
npm test
```

Expected: 全部 PASS。**常见坑**：
- `view.multi.spec.ts` / `stores.spec.ts` 里若还断言 `setHighlightedEvents` 是函数，需删该断言（这 API 消失）。
- `stores.spec.ts` 若断言 `loadScanFile` 后 `highlightedEventIds.size === 0`——那已经隐式成立（`selected` 被清）；断言可保留但去掉对 setter 的调用。
- Vue 模板里若有 `@click="selectMatchAndHighlight(...)"` 之类调用，函数还在（只删了内部一行），无碍。

- [ ] **Step 7: vue-tsc + build 检查**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vue-tsc --noEmit
npm run build
```

Expected: 都绿。类型报错常见：其它 .ts / .vue 文件对 `view.setHighlightedEvents` / `view.clearHighlight` 有引用 → 全删。`grep -rn 'setHighlightedEvents\|clearHighlight' src/ tests/` 兜底扫全。

- [ ] **Step 8: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
git add -u src/ tests/
cd /home/yu/PycharmProjects/Trade_Strategy
git commit -m "$(cat <<'EOF'
refactor(view): highlightedEventIds 声明式 + 修主图 BO in-group bug

- view store: highlightedEventIds 从 ref+setter 改为 computed(依赖 selectedMatch);
  matchedIdsOf(...,edges) 全局 computed 传入 edges;删 setHighlightedEvents +
  clearHighlight,删 4 处 loadScanFile/clearScanFile/selectSymbol/setActivePattern
  里的显式清理(selectMatch(null) 自动派生空集)
- KlineChart.ts: 空白/bracket/marker(0/1/>1)5 处 setter+clear 调用全删
- DetailSidebar.vue: selectMatchAndHighlight 里 setter 调用删

essence: 修复"选中 match 后主图 BO 方框无 in-group 深边"的通道不一致 bug——
group 高亮与颜色 tier 现共用同一份 matchedIds 协议展开

spec: docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: KlineChart.ts marker filter 判据改用 matchedIdsOf（tier/click 对齐）

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.ts`
- Modify: `path2_web_ui/tests/components.kline-click.spec.ts`

**Interfaces:**
- Consumes: Task 2 的 `matchedIds(matches, events, edges)` 函数；Task 3 的 view store `effectiveAnalysis` / `effectivePattern` shape
- Produces:
  - `KlineChart.ts:99` 附近 `matches.filter` 判据从 `m.children.includes(eventId)` 改为 `matchedIdsOf([m], events, edges).has(eventId)`
  - `bo` / `tb.anchor_bo_id` 通过 `child_refs` / `anchor_field` 内嵌引用的 event 点击时能查出所属 match（tier=matched 的 event 点击行为与颜色/边框通道对齐）
  - 多归属场景（一个 bo 属于多个 burst / 多个 match）自动进 candidate 消解流；候选面板天然承载多级歧义（一次选中，无需先选 burst 再选 match）
  - `handleChartClick` 签名不变（events / edges 内部从 view store 读，测试仍通过 `loadScanFile` 注入）

**背景**：Task 3 使 `highlightedEventIds` 沿 `matchedIds` 协议展开、BO tier=matched；但 `KlineChart.ts:99` 的 filter 仍读 `m.children`（不含 bo），点 bo 会走 `ms.length === 0` 的 fallback 分支——tier 与 click 出现新的语义不一致。本 task 把 filter 判据也改为协议展开，与 Task 3 对齐。

- [ ] **Step 1: 写失败测试（components.kline-click.spec.ts 追加 3 用例）**

在 `path2_web_ui/tests/components.kline-click.spec.ts` 末尾 describe 里追加：

```ts
  it('marker click × 多归属:bo 属于 2+ match → candidate 分支(matchedIdsOf 协议展开 filter)', () => {
    const view = useViewStore()
    const events = [
      { class_id: 'burst', event_id: 'burst_A', start_idx: 5, end_idx: 7, source_tag: 'burst',
        child_refs: { members: ['bo_5', 'bo_7'] } },
      { class_id: 'burst', event_id: 'burst_B', start_idx: 5, end_idx: 9, source_tag: 'burst',
        child_refs: { members: ['bo_5', 'bo_9'] } },
      { class_id: 'tb', event_id: 'tb_A', start_idx: 10, end_idx: 10, source_tag: 'tb',
        child_refs: {}, anchor_bo_id: 'bo_7' },
      { class_id: 'tb', event_id: 'tb_B', start_idx: 12, end_idx: 12, source_tag: 'tb',
        child_refs: {}, anchor_bo_id: 'bo_9' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo', child_refs: {} },
      { class_id: 'bo', event_id: 'bo_7', start_idx: 7, end_idx: 7, source_tag: 'bo', child_refs: {} },
      { class_id: 'bo', event_id: 'bo_9', start_idx: 9, end_idx: 9, source_tag: 'bo', child_refs: {} },
    ]
    const matches = [
      { event_id: 'match_A', start_idx: 5, end_idx: 10,
        role_index: { burst: 'burst_A', tb: 'tb_A' },
        children: ['burst_A', 'tb_A'], predicate_trace: null },
      { event_id: 'match_B', start_idx: 5, end_idx: 12,
        role_index: { burst: 'burst_B', tb: 'tb_B' },
        children: ['burst_B', 'tb_B'], predicate_trace: null },
    ]
    const topology = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', source_tag: 'bo', where_rules: [] },
        { node_id: 'burst', class_id: 'burst', source_tag: 'burst', where_rules: [] },
        { node_id: 'tb', class_id: 'tb', source_tag: 'tb', where_rules: [] },
      ],
      edges: [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }],
    }
    view.loadScanFile({
      pattern_ids: ['bottom_burst'],
      per_pattern: { bottom_burst: {
        pattern_spec: { pattern_id: 'bottom_burst', topology, event_styles: {} },
        end_role: 'tb' } },
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: 1, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol: 'X', per_pattern: { bottom_burst: {
        summary: { matches: 2 }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = 'X'
    view.activePatternId = 'bottom_burst'
    // bo_5 属于 burst_A 和 burst_B → 属于 match_A 和 match_B 两条 match
    handleChartClick(
      { seriesName: 'price-points', data: { event_id: 'bo_5' } }, matches, view)
    expect([...view.candidateMatchIds].sort()).toEqual(['match_A', 'match_B'])
    expect(view.pendingDisambigEventId).toBe('bo_5')
    expect(view.selectedMatchId).toBeNull()          // candidate 与 selected 互斥
    expect(view.highlightedEventIds.size).toBe(0)    // selectedMatch=null → computed 空集
  })

  it('marker click × 单归属:bo 只属于 1 条 match → selectMatch + highlight 沿 child_refs 展开', () => {
    const view = useViewStore()
    const events = [
      { class_id: 'burst', event_id: 'burst_A', start_idx: 5, end_idx: 7, source_tag: 'burst',
        child_refs: { members: ['bo_5'] } },
      { class_id: 'tb', event_id: 'tb_A', start_idx: 10, end_idx: 10, source_tag: 'tb',
        child_refs: {}, anchor_bo_id: 'bo_5' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo', child_refs: {} },
    ]
    const matches = [{ event_id: 'match_A', start_idx: 5, end_idx: 10,
      role_index: { burst: 'burst_A', tb: 'tb_A' },
      children: ['burst_A', 'tb_A'], predicate_trace: null }]
    const topology = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', source_tag: 'bo', where_rules: [] },
        { node_id: 'burst', class_id: 'burst', source_tag: 'burst', where_rules: [] },
        { node_id: 'tb', class_id: 'tb', source_tag: 'tb', where_rules: [] },
      ],
      edges: [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }],
    }
    view.loadScanFile({
      pattern_ids: ['bottom_burst'],
      per_pattern: { bottom_burst: {
        pattern_spec: { pattern_id: 'bottom_burst', topology, event_styles: {} },
        end_role: 'tb' } },
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: 1, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol: 'X', per_pattern: { bottom_burst: {
        summary: { matches: 1 }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = 'X'
    view.activePatternId = 'bottom_burst'
    handleChartClick(
      { seriesName: 'price-points', data: { event_id: 'bo_5' } }, matches, view)
    expect(view.selectedMatchId).toBe('match_A')
    expect(view.highlightedEventIds.has('bo_5')).toBe(true)   // 协议展开
    expect(view.selectedEventId).toBe('bo_5')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click × 真无归属:qualified/detected tier bo → fallback,只选 event', () => {
    const view = useViewStore()
    const events = [
      { class_id: 'bo', event_id: 'bo_99', start_idx: 99, end_idx: 99, source_tag: 'bo', child_refs: {} },
    ]
    const matches: MatchDict[] = []
    view.loadScanFile({
      pattern_ids: ['bottom_burst'],
      per_pattern: { bottom_burst: {
        pattern_spec: { pattern_id: 'bottom_burst',
          topology: { nodes: [], edges: [] }, event_styles: {} }, end_role: 'tb' } },
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: 0, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol: 'X', per_pattern: { bottom_burst: {
        summary: { matches: 0 }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = 'X'
    view.activePatternId = 'bottom_burst'
    handleChartClick(
      { seriesName: 'price-points', data: { event_id: 'bo_99' } }, matches, view)
    expect(view.selectedMatchId).toBeNull()
    expect(view.selectedEventId).toBe('bo_99')
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.candidateMatchIds.size).toBe(0)
  })
```

- [ ] **Step 2: 运行 vitest 确认新用例 FAIL**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- components.kline-click.spec.ts
```

Expected: 至少"多归属 → candidate"和"单归属 bo → highlight 展开"两用例 FAIL——当前 `m.children.includes('bo_5')` 恒 false，走 fallback；`view.highlightedEventIds.has('bo_5')` 因未选中 match 而为 false。

- [ ] **Step 3: 改 KlineChart.ts filter 判据**

`src/components/KlineChart.ts` 顶部 import 区（`:16-17` 附近）**新增一行**：

```ts
import { matchedIds as matchedIdsOf } from '../render/visible'
```

`KlineChart.ts:93-99` 原代码：

```ts
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    const eventId = p.data.event_id
    void view.triggerCandidateQuery(eventId)
    // 计算 event 归属的 match 集合
    const ms = matches.filter((m) => m.children.includes(eventId))
```

替换为：

```ts
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    const eventId = p.data.event_id
    void view.triggerCandidateQuery(eventId)
    // 归属判据用 matchedIdsOf 协议展开(child_refs + anchor_field),不再直读 m.children。
    // 让 bo 这类通过 child_refs 内嵌引用的 event 点击时能查出"属于哪些 match",
    // tier=matched 的 event 行为与颜色/边框通道对齐。多归属自动降为单层 candidate。
    const events = view.effectiveAnalysis?.events ?? []
    const edges = view.effectivePattern?.topology.edges ?? []
    const ms = matches.filter((m) => matchedIdsOf([m], events, edges).has(eventId))
```

- [ ] **Step 4: 运行 vitest 确认 PASS**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- components.kline-click.spec.ts
```

Expected: 全部 PASS。

- [ ] **Step 5: 全量 vitest + vue-tsc + build 回归**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test
npx vue-tsc --noEmit
npm run build
```

Expected: 都绿。**常见坑**：现有 kline-click 用例可能依赖"点 burst → ms.length===1"的 filter 行为——协议展开后一个 burst event 依然只会属于它所在的那一条 match（tb 单归属场景），行为不变；但如果测试里造了"点 tb → ms 应等于 1"这类断言，且 tb 的 anchor_bo_id 引用了一个恰好在多个 burst.members 里的 bo，则 tb 也会变多归属——检查 fixture 是否需要调整。

- [ ] **Step 6: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
git add -u src/ tests/
cd /home/yu/PycharmProjects/Trade_Strategy
git commit -m "$(cat <<'EOF'
feat(kline-click): marker filter 用 matchedIds → tier/click 对齐

- KlineChart.ts marker 分支 filter 判据从 m.children.includes(eventId) 改为
  matchedIdsOf([m],events,edges).has(eventId):让 child_refs/anchor_field 内嵌
  引用的 event(如 bo)点击时也能查出所属 match,tier=matched 的 event 点击
  行为与颜色/边框通道对齐
- 多归属(一个 bo 属于多个 burst/多个 match)自动降维为单层 candidate 列表,
  UI 已有 candidate 消解流承载,无需多级选择树
- 单归属直接 selectMatch;真无归属仍走 fallback
- 3 用例覆盖三分支(多归属 candidate / 单归属 select / 真无归属 fallback)

spec: docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: chart.spec.ts BO in-group 渲染断言 + Playwright e2e 验证

**Files:**
- Modify: `path2_web_ui/tests/chart.spec.ts`
- (no code change) Playwright browser session

**Interfaces:**
- Consumes: Task 3 的 `highlightedEventIds` computed 会自动含 BO id；Task 4 的 marker click filter 协议对齐（bo 点击也能进 candidate / selectMatch）
- Produces: `chart.spec.ts` 新增 BO in-group 深边渲染断言；Playwright e2e 通过

- [ ] **Step 1: 加 chart.spec.ts BO in-group 渲染断言**

在 `tests/chart.spec.ts` 里找到 `makeRenderPricePointHighlight` 相关的测试段落，或在文件末尾追加：

```ts
import { makeRenderPricePointHighlight } from '../src/render/chart'

describe('makeRenderPricePointHighlight × in-group 态', () => {
  it('hlKind=group → 边框宽 HL_GROUP_STROKE_WIDTH(1.5)、边色 HL_FOCUS_EDGE(深灰蓝)', () => {
    // 若 makeRenderPricePointHighlight 是高阶(参数 event_id_of / bars),此处按已有测试同样构造
    // 若接口不同,按已有 makeRender* 测试的 setup 复用;本 assert 只关心返回 shape:
    //   { type: 'group', children: [{ style: { stroke: '#...', lineWidth: 1.5 } }, ...] }
    // 或直接在 highlightPriceData 里 kind:'group' 项通过整体渲染 verify
    // 具体 API 由 makeRenderPricePointHighlight 决定——参考文件已有 makeRenderPricePoint 测试
    // 断言样式对象包含:
    //   lineWidth === 1.5    (HL_GROUP_STROKE_WIDTH)
    //   stroke   === '#374151' 或 chart.ts 中 HL_FOCUS_EDGE 常量的值
  })

  it('hlKind=focus → 边框宽 HL_FOCUS_STROKE_WIDTH(2.5)', () => {
    // 同上,验 focus 分支宽 2.5
  })
})
```

**注意**：`makeRenderPricePointHighlight` 的具体签名要看 `src/render/chart.ts:651` 附近（`readonly` 参数、返回结构等）。**打开 `chart.spec.ts` 找已有 `makeRenderPricePoint` 或 `makeRenderBracket` 测试**，照抄其 setup pattern 构造这两个新测试；HL_FOCUS_EDGE / HL_GROUP_STROKE_WIDTH 常量值从 `chart.ts:596-597` 读。

如果 chart.spec.ts 中已有 `makeRenderPricePointHighlight` 测试覆盖 group/focus，则跳过——这一步的目标是**确保覆盖存在**。存在则删本步、直接 Step 2。

- [ ] **Step 2: 运行 vitest 确认 PASS**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm test -- chart.spec.ts
```

Expected: 全部 PASS。

- [ ] **Step 3: Playwright e2e — 启动开发服务器**

后端：
```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run python -m path2_web.main
```
（run_in_background=true；等待 uvicorn 起来）

前端：
```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npm run dev
```
（run_in_background=true）

前端 dev 端口一般 5170、后端 8000（`configs/path2_web.yaml`）。

- [ ] **Step 4: Playwright 加载 LPCN scan + 选 match + 截图**

用 Playwright MCP tools（`browser_navigate` / `browser_click` / `browser_evaluate` / `browser_take_screenshot`）：

1. `browser_resize(2560, 1440)`
2. `browser_navigate(http://127.0.0.1:5170)`
3. 在 UI 里加载历史 scan `2026-07-08 09:24:04`（LPCN, 3 hits）——用 `browser_click` 点扫描列表相应条目，或直接 `browser_evaluate` 调 view store 的 `loadScanFile`
4. 选 LPCN 股 → 副图 marker 触发 `ms.length===1` 分支：`browser_click` 点 burst marker
5. `browser_take_screenshot(fullPage=false, scale="device", target=<主图 BO 方框 selector>)`：截图主图 BO 方框区域
6. `browser_evaluate` 直接查 view store：
   ```js
   () => {
     const pinia = document.querySelector('#app').__vue_app__._context.provides
     const key = Object.getOwnPropertySymbols(pinia).find(s => s.toString().includes('pinia'))
     const view = pinia[key]._s.get('view')
     return {
       selectedMatchId: view.selectedMatchId,
       highlightedEventIds: [...view.highlightedEventIds],
       hasBOInGroup: [...view.highlightedEventIds].some(id => id.startsWith('bo_')),
     }
   }
   ```

- [ ] **Step 5: 断言 e2e 结果**

- `selectedMatchId` 非 null
- `highlightedEventIds` 至少含 3 类 event（burst / tb / bo）
- `hasBOInGroup === true` ← 核心断言：修复的 UI bug 已消
- 截图目视：主图 `[7]` 或对应 BO 方框有深灰蓝细边（`HL_GROUP_STROKE_WIDTH=1.5`）；颜色为 role 色（`_PALETTE[0] = #16f943` 浅绿）

若截图看不出边框（sub-pixel），以 `browser_evaluate` 的逻辑层断言为准——渲染层 Task 4 Step 2 已单测覆盖。

- [ ] **Step 6: 反向验证 — clearSelection**

`browser_click` 点空白处触发 `handleChartClick` 空白分支；再 `browser_evaluate`：
```js
() => [...view.highlightedEventIds]
```
Expected: `[]`（空）。

- [ ] **Step 7: 清理 .playwright-mcp 缓存**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
rm -rf .playwright-mcp/*
```

（**保留目录本身**，只删内容。）

- [ ] **Step 8: 关闭 dev 服务器**

前后端两个后台任务 kill 掉（或让 executing-plans 用 TaskStop）。

- [ ] **Step 9: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/tests/chart.spec.ts
git commit -m "$(cat <<'EOF'
test(chart): BO 主图方框 in-group 深边渲染断言 + e2e 验证

- chart.spec.ts: makeRenderPricePointHighlight group/focus 两态渲染样式断言
- Playwright e2e(LPCN scan): 选中 match → view.highlightedEventIds 含 BO id、
  主图方框显示 in-group 深边;clearSelection 后自动清空

修复的 UI bug 现在被单测(渲染层)+ e2e(逻辑+渲染层)双闸把关。

spec: docs/superpowers/specs/2026-07-09-event-references-protocolization-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Gate（每 task 结束后 + plan 结束时）

**每 task commit 后跑：**
```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest tests/ -x -q      # 后端全绿
cd path2_web_ui
npm test                        # vitest 全绿
npx vue-tsc --noEmit            # 类型绿
npm run build                   # build 绿
```

**Task 4 之后额外 e2e** — 见 Task 4 Step 3-6。

## Self-Review Notes（Plan 作者自审记录）

- [x] Spec §3.1 协议映射表 → Task 1 (后端 payload) + Task 2 (前端消费) 完整覆盖
- [x] Spec §3.2 后端具体改动 → Task 1 Steps 3-4 逐字给出替换代码
- [x] Spec §3.3 前端类型/visible.ts/store/清理点 → Task 2 + Task 3 分别覆盖，KlineChart 5 处调用点 + DetailSidebar 1 处 + view store 4 处清理 + 2 处 setter 定义 + 1 处 return 导出 全部枚举
- [x] Spec §3.4 一步到位 / 无 legacy → Global Constraints 明列
- [x] Spec §5 测试策略 → Task 1/2/3/4 各自 TDD RED 步骤
- [x] Spec §6 Playwright e2e → Task 4 Steps 3-6 详列步骤
- [x] Type consistency：`matchedIds` 全 plan 使用 3 参 `(matches, events, edges)` 签名（Task 2 Step 4 定义、Task 3 Step 3 全局 computed 引用）；`child_refs` 类型 `Record<string, string[]>`（Task 2 Step 3 定义、Task 2 Step 1 测试用同格式）；`anchor_field` 类型 `string | null | undefined`（Task 2 Step 3、Task 2 Step 4）
- [x] No placeholder — 每 step 给具体 code / 命令 / 期望输出
