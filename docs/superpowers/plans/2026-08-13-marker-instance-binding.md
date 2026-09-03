# Marker 与实例绑定实施计划(全链路实例级交互)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**本 plan 中所有项目内路径均相对 repo root。**

**Goal:** 让前端交互与判定全链路落到实例级——marker 点击绑定实例、tier 三档实例级、tooltip 显示所悬停实例自身的判定,待选择(pendingDisambig)只留给「同一实例被 ≥2 个 match 引用」的真共享场景。

**Architecture:** 契约层先行(后端 serialize 的 match node_index 对象化为 {event_id, idx}、diagnose 的 attr 行加 instance_key,均与既有 _InstanceIndexer 同源编号),然后前端类型与机械消费点适配,再改判定纯函数(visible.ts)与焦点语义(view.ts 双入口:实例级入口直选、身份级入口按归属并集),最后交互接线与全量验收。不兼容旧 scan 文件(无降级路径)。

**Tech Stack:** Python(path2_web serialize/diagnose)/ Vue3 + TS(前端)/ pytest / vitest / vue-tsc / vite

## Global Constraints

1. **契约形态**:match.node_index 值 = `{event_id: str, idx: int}` 对象(NodeRef);attr 行新增 `instance_key: str`(#0 起)。不兼容旧 scan 文件,不做运行时降级。
2. **编号同源**:node_index.idx / leaf.idx / 事件行 instance_key / attr 行 instance_key 必须同一编号约定(组内按流序从 0 起,`_InstanceIndexer` 语义),禁止各自编号。
3. **判定语义**:tier 三档(matched/qualified/detected)全部实例级;matchedIds 初始集从 node_index 取**精确实例**,递归展开(child_refs/anchor)保持身份级(展开该身份全部实例)。
4. **双入口语义**:focusEvent(eventId, idx?)——带 idx(实例级入口:marker 点击)按实例精确归属 0/1/≥2 三分支;不带 idx(身份级入口:侧栏 trace 行/候选表行)按身份下全部实例的归属并集(一致则直选、分属或共享则 pendingDisambig)。
5. **selectedEventId 保留**:事件级字段继续被 shift 选择/详情卡消费;焦点**判定**升级实例级(新增复合键焦点,chart 的 group/focus 条目按 event_key 匹配)。
6. **全中文注释/UI**;入口脚本不使用 argparse(本 plan 无新入口)。
7. **测试先 RED 后 GREEN**;既有断言修改(契约升级的 fixture 同步)先复核推演,不是盲改。
8. **模型纪律**(subagent-driven 执行时):Implementer 一律 sonnet(禁用 haiku);每 task Reviewer(spec + quality)一律 opus;final holistic review 用 opus。
9. **执行纪律**:每 task 跑绿再 commit 到实施分支;中途不 pause 问进度;BLOCKED 或 plan 文本与实际冲突按 subagent-driven 流程处理,无法裁决才停下汇报。

---

### Task 1: 后端 serialize — match node_index 对象化

**Files:**
- Modify: `path2_web/serialize.py:132-144`(`_match_to_dict`)+ `:186`(调用点)
- Test: `tests/path2_web/test_serialize.py`(新增测试;既有多实例测试复用)

**Interfaces:**
- Consumes: 现状 `_match_to_dict(m) -> dict`(node_index 值为 event_id 字符串);`_InstanceIndexer`(serialize.py:38-60,组内按流序编号)
- Produces: `_match_to_dict(m, indexer)` —— node_index 值升级为 `{"event_id": e.event_id, "idx": indexer.idx_of(e)}`;Task 3 前端消费该新形态

- [ ] **Step 1: 定位既有多实例测试构造**

Run: `grep -n "multi_instance\|instance_key\|leaf" tests/path2_web/test_serialize.py | head -20`
Expected: 找到 `test_serialize_events_multi_instance_rows` 与 `test_serialize_match_multi_instance_leaf`(实例流实施时新增),记录其事件构造方式(同 event_id 双实例 + 含 node_index 的 match 构造)到本 task 报告——Step 2 复用同一构造。

- [ ] **Step 2: 写失败测试(断言 node_index 对象化)**

在 `tests/path2_web/test_serialize.py` 新增(复用 Step 1 定位的既有构造,只加断言):

```python
def test_serialize_match_node_index_instanced():
    """match node_index 对象化:每节点 {event_id, idx},idx 与事件行 instance_key 同源。"""
    payload = serialize_analysis(res)          # res = Step 1 既有构造(同 event_id 双实例场景)
    matches = payload["matches"]
    ev_rows = {r["event_id"] + r.get("instance_key", ""): r for r in payload["events"]}
    for m in matches:
        for nid, ref in m["node_index"].items():
            assert isinstance(ref, dict), f"node_index[{nid}] 应为对象, 实为 {ref!r}"
            assert set(ref) == {"event_id", "idx"}, ref
            # 同源:该节点的 idx 与该事件在 events 行的 instance_key 一致
            key = ref["event_id"] + "#" + str(ref["idx"])
            assert key in ev_rows, f"{key} 不在事件行(instance_key 编号不同源)"
    # 双实例场景至少有一个 node 的 idx 能区分两个实例(APCX 形态)
    tb_refs = [ref for m in matches for nid, ref in m["node_index"].items() if ref["event_id"].startswith("tb_")]
    if len(tb_refs) >= 2:
        assert len({r["idx"] for r in tb_refs}) >= 2, "同 event_id 双实例的 idx 应区分"
```

(若既有构造不含 match 或双实例,按 `test_serialize_match_multi_instance_leaf` 的构造补齐 res:一个 AnalysisResult 含同 event_id 双事件 + 两个 node_index 引用它们的 match。)

- [ ] **Step 3: 跑测试确认 FAIL**

Run: `uv run pytest tests/path2_web/test_serialize.py -q -k "node_index_instanced"`
Expected: FAIL(node_index 值仍是字符串,isinstance dict 断言失败)

- [ ] **Step 4: 实现对象化**

修改 `path2_web/serialize.py`:

```python
def _match_to_dict(m, indexer) -> dict:
    """match → dict。node_index 实例化:每节点 {event_id, idx}(与事件行 instance_key
    同一编号函数,禁止各自编号)。"""
    return {
        "event_id": m.event_id,
        "start_idx": m.start_idx,
        "end_idx": m.end_idx,
        "node_index": {
            nid: {"event_id": e.event_id, "idx": indexer.idx_of(e)}
            for nid, e in (m.node_index or {}).items()
        },
        "children": [e.event_id for e in m.children],
        "predicate_trace": _trace_to_dict(m.predicate_trace) if m.predicate_trace else None,
    }
```

删除内嵌 `_node(v)` helper(不再使用)。调用点 `serialize_analysis`(:186):

```python
return {"events": out_events, "matches": [_match_to_dict(m, indexer) for m in res.matches]}
```

(`indexer` 在 serialize_analysis 内已构造于 :161——同一对象;若该行在函数作用域内不可见,改为在 :186 前构造或复用现有变量名,以实际代码为准,保证与事件行编号同一对象。)

- [ ] **Step 5: 跑测试确认 PASS + 回归**

Run: `uv run pytest tests/path2_web/test_serialize.py -q` 与 `uv run pytest tests/path2_web/ -q`
Expected: 新测试 PASS;既有序列化测试无回归(注意:既有断言 node_index 值为字符串的测试若存在,属契约升级的必然同步——先复核再改,改后与 Step 2 断言一致)

- [ ] **Step 6: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize.py
git commit -m "feat: serialize match node_index 对象化({event_id, idx}, 与 instance_key 同源)"
```

---

### Task 2: 后端 diagnose — attr 行加 instance_key

**Files:**
- Modify: `path2_web/diagnose.py:23-29`(`_attr_row`)+ `:42-56`(`serialize_diagnostics`)
- Test: `tests/path2_web/test_diagnose_pair.py` 或就近的 diagnose 测试文件(grep 定位)

**Interfaces:**
- Consumes: `serialize_diagnostics(diag)`(diag.nodes[nid].attr 的 row.event 为事件对象);serialize.py 的 `_InstanceIndexer` 编号语义
- Produces: attr 行新增 `instance_key: str`(与 serialize_analysis 事件行同源);Task 3 前端 AttrRow 消费

- [ ] **Step 1: 写失败测试(attr 行 instance_key + 同源对拍)**

在 diagnose 测试文件新增:

```python
def test_diag_attr_row_instance_key_matches_analysis():
    """attr 行 instance_key 与 serialize_analysis 事件行同源(同一事件同一编号)。"""
    # 构造:同一 (spec, df) 分别跑 diagnose 与 analyze 两条路径
    from path2_web.diagnose import _diagnose, serialize_diagnostics
    from path2_web.serialize import serialize_analysis
    from path2.dag.engine import analyze   # 实际入口以代码为准:grep analyze 在 path2/dag/engine.py
    diag = _diagnose(spec, df, None)
    d = serialize_diagnostics(diag)
    rows = [r for node in d["nodes"].values() for r in node["attr"]]
    assert all("instance_key" in r for r in rows), "attr 行缺 instance_key"
    # 同源:同一事件(同 event_id + 同 span)在两条路径的 instance_key 一致
    # 对拍:取一个多实例事件(或全部单实例),断言 attr 行的 (event_id, instance_key)
    # 与 analyze 后 serialize_analysis 的事件行一致
    ...  # 对拍实现见 Step 2 说明
```

(spec/df 构造:复用既有 diagnose 测试的 fixture——grep `_diagnose` 或 `diagnose_symbol` 在 tests/ 定位,复制其 spec 与 df 构造;数据文件用 `datasets/pkls/` 任意一只有多实例的标的,如 APCX 2025 窗口,或直接用既有测试的构造。)

- [ ] **Step 2: 同源对拍的正确实现方式**

同源对拍的核心:对同一标的,`serialize_diagnostics` 产出的 (event_id, instance_key) 与 `serialize_analysis`(analyze 后)的事件行 (event_id, instance_key) 一一一致。实现方式(以实际代码为准,两条路径都要能跑):

```python
# 伪代码骨架(按实际 API 调整):
# 1) 跑 analyze:res = run/analyze(spec, df, ...) → ser = serialize_analysis(res)
#    analysis_rows = {(r["event_id"], r["instance_key"]) for r in ser["events"]}
# 2) 跑 diagnose:diag = _diagnose(spec, df, None) → d = serialize_diagnostics(diag)
#    diag_rows = [(r["event_id"], r["instance_key"]) for node in d["nodes"].values() for r in node["attr"]]
# 3) 断言:diag_rows 的每个 (event_id, instance_key) 都在 analysis_rows 中(方向:diagnose 事件 ⊆ analyze 事件)
```

注意:若该断言失败(如 diagnose 路径事件顺序或集合与 analyze 不一致),说明 diagnose 内部从 diag 构造的编号与 events 全集不同源——此时改为在 `serialize_diagnostics` 加可选参数 `events=()`(默认空,从 diag 推导),diagnose_symbol 的调用点(api.py:316)若能拿到 result.events 则传入;scope=nodes 路径无法拿到 events 时,检查 `_diagnose` 内部是否有流全集可携带(如 diag 上挂 events)。**以同源对拍测试为裁决,不得跳过该测试**。

- [ ] **Step 3: 跑测试确认 FAIL**

Run: `uv run pytest <diagnose测试文件> -q -k "instance_key"`
Expected: FAIL(现状 attr 行无 instance_key)

- [ ] **Step 4: 实现 instance_key**

修改 `path2_web/diagnose.py`:

```python
def _attr_row(row, indexer) -> dict:
    return {
        "event_id": row.event.event_id,
        "instance_key": f"#{indexer.idx_of(row.event)}",   # 实例流:与 serialize_analysis 同源
        "start_idx": row.event.start_idx,
        "end_idx": row.event.end_idx,
        "clauses": {cid: _clause_to_dict(w) for cid, w in row.clauses.items()},
    }
```

`serialize_diagnostics` 内构造 indexer(从 diag.nodes 遍历 attr 行事件,同 _InstanceIndexer 逻辑——**复用 serialize.py 的 `_InstanceIndexer`**:`from path2_web.serialize import _InstanceIndexer`):

```python
def serialize_diagnostics(diag) -> dict:
    """... 实例流:attr 行 instance_key 由 diag 内部编号(与 serialize_analysis 同一
    _InstanceIndexer 约定,同源性由同源对拍测试裁决)。"""
    indexer = _InstanceIndexer(
        e for node in diag.nodes.values() for r in node.attr for e in [r.event]
    )
    return {
        "nodes": {
            nid: {
                "attr": [_attr_row(r, indexer) for r in rd.attr],
                ...
```

- [ ] **Step 5: 跑测试确认 PASS + 回归**

Run: `uv run pytest <diagnose测试文件> -q` 与 `uv run pytest tests/path2_web/ -q`
Expected: 新测试 PASS(含同源对拍);既有诊断测试无回归

- [ ] **Step 6: Commit**

```bash
git add path2_web/diagnose.py tests/path2_web/
git commit -m "feat: diagnose attr 行加 instance_key(与 serialize_analysis 同源编号)"
```

---

### Task 3: 前端类型升级 + node_index 消费点机械适配

**Files:**
- Modify: `path2_web_ui/src/types.ts:62-72`(MatchDict)、`:133-136`(AttrRow)
- Modify: `path2_web_ui/src/render/chart.ts:216`(bracket event_id)、`:1451-1460`(tooltip 组成段遍历)
- Modify: `path2_web_ui/src/components/DetailSidebar.vue:170`(v-for 遍历)、`:343`(nodeEventId)
- Test: `path2_web_ui/tests/fixtures.ts`(共享 fixture)+ 各 spec 的 node_index fixture(grep 全量)

**Interfaces:**
- Consumes: Task 1/2 的新契约(node_index NodeRef、attr instance_key)
- Produces: `NodeRef` 类型、MatchDict.node_index 对象化、AttrRow.instance_key 必填;tsc 三绿

- [ ] **Step 1: 全库定位 node_index 消费点与 fixture**

Run: `grep -rn "node_index" path2_web_ui/src --include="*.ts" --include="*.vue" | grep -v spec` 与 `grep -rln "node_index" path2_web_ui/tests/`
Expected: 登记全部 src 消费点(types/chart/DetailSidebar 等)与 tests fixture 文件清单(约 14 个 spec + fixtures.ts)到本 task 报告。

- [ ] **Step 2: 更新类型**

`path2_web_ui/src/types.ts`:

```ts
/** 实例流节点引用:event_id + 组内实例序号(与事件行 instance_key 同源)。 */
export interface NodeRef { event_id: string; idx: number }

export interface MatchDict {
  event_id: string; start_idx: number; end_idx: number
  node_index: Record<string, NodeRef>
  children: string[]
  // ...其余字段保持现状
}

export interface AttrRow {
  event_id: string; start_idx: number; end_idx: number
  instance_key: string          // 实例流契约:恒输出(#0 起)
  clauses: Record<string, ClauseWitness>
}
```

- [ ] **Step 3: src 消费点适配(机械,先复核再改)**

- `chart.ts:216`(bracket 的 event_id):
```ts
if (endNode) {
  const v = m.node_index?.[endNode]
  if (v) data.event_id = v.event_id
}
```
- `chart.ts:1451-1460`(tooltip 组成段;顺带删除 kleene 数组分支残留):
```ts
for (const [nodeKey, ref] of Object.entries(match.node_index)) {
  lines.push(`  ${nodeKey}: ${ref.event_id}`)
}
```
- `DetailSidebar.vue:170` 附近(v-for 显示):把显示的键从 `nodeKey`/原值改为 `ref.event_id`(以现状模板为准,先读模板再改)。
- `DetailSidebar.vue:343`(nodeEventId):
```ts
function nodeEventId(val: NodeRef): string | null {
  return val?.event_id ?? null
}
```
(签名按调用处实际类型调整;删除 `Array.isArray` kleene 分支)

- [ ] **Step 4: 测试 fixture 同步(契约升级,先复核再改)**

`path2_web_ui/tests/fixtures.ts` 及全部 spec 的 node_index 值从字符串升级为 NodeRef:
- 机械替换:`'xxx'` → `{ event_id: 'xxx', idx: 0 }`
- **先复核**:每个断言 `node_index[nid] === 'xxx'` 改为 `node_index[nid].event_id === 'xxx'`;若有断言涉及多实例(idx 区分),按 Task 4 后语义复核(本 task 先保证 fixture 与新类型一致、tsc 绿)
- AttrRow fixture:补 `instance_key: '#0'`(若既有 fixture 有 attr 行)

- [ ] **Step 5: 三绿验证**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 全绿(若既有测试因契约升级红,先复核是否必然同步——NodeRef 化是唯一变更点;禁止改断言语义)

- [ ] **Step 6: Commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/render/chart.ts path2_web_ui/src/components/DetailSidebar.vue path2_web_ui/tests/
git commit -m "feat: 前端 node_index 对象化类型与消费点适配(NodeRef, 删 kleene 残留)"
```

---

### Task 4: visible.ts 判定实例级(纯函数)

**Files:**
- Modify: `path2_web_ui/src/render/visible.ts`(`matchedIds` :26-81、`qualifiedIdsOf` :120-126、`eventTierOf` :131-135、`resolveTooltipData` :176+)
- Test: `path2_web_ui/tests/visible.spec.ts`、`path2_web_ui/tests/render.visible.spec.ts`、`path2_web_ui/tests/render.chart-tooltip.spec.ts`

**Interfaces:**
- Consumes: Task 3 的 NodeRef/instance_key 类型;match.node_index 对象化数据
- Produces: `matchedIds` 精确初始集;`qualifiedIdsOf` 复合键集;`eventTierOf` 全实例级;`resolveTooltipData(eventId, idx, diag, events, bars)`(签名加 idx,调用点 KlineChart.vue:457 在 Task 6 同步)

- [ ] **Step 1: 写失败测试(实例级判定)**

在 `tests/visible.spec.ts` 新增:

```ts
it('matchedIds 初始集按 node_index 精确实例(非身份展开)', () => {
  // 构造:两个 match,node_index 分别引用 tb_v1_293 的 #0 / #1(APCX 形态)
  const m0 = { event_id: 'bb@0-3', start_idx: 0, end_idx: 3,
               node_index: { burst: { event_id: 'burst_0_2', idx: 0 }, tb: { event_id: 'tb_v1_293', idx: 0 } },
               children: ['burst_0_2', 'tb_v1_293'] } as MatchDict
  const m1 = { event_id: 'bb@0-3b', start_idx: 0, end_idx: 3,
               node_index: { burst: { event_id: 'burst_0_2', idx: 1 }, tb: { event_id: 'tb_v1_293', idx: 1 } },
               children: ['burst_0_2', 'tb_v1_293'] } as MatchDict
  const events = [
    { event_id: 'tb_v1_293', instance_key: '#0', start_idx: 3, end_idx: 3 } as EventDict,
    { event_id: 'tb_v1_293', instance_key: '#1', start_idx: 3, end_idx: 3 } as EventDict,
  ]
  const s = matchedIds([m0, m1], events, [])
  expect(s.has('tb_v1_293#0')).toBe(true)
  expect(s.has('tb_v1_293#1')).toBe(true)   // 两实例各被引用 → 都进集
})

it('matchedIds 未被引用的实例不进集', () => {
  // 同身份 3 实例,只有 #0/#1 被引用 → #2 不进集
  const events = [
    { event_id: 'tb_x', instance_key: '#0', start_idx: 1, end_idx: 1 } as EventDict,
    { event_id: 'tb_x', instance_key: '#1', start_idx: 1, end_idx: 1 } as EventDict,
    { event_id: 'tb_x', instance_key: '#2', start_idx: 1, end_idx: 1 } as EventDict,
  ]
  const m = { event_id: 'bb@1-1', start_idx: 1, end_idx: 1,
              node_index: { tb: { event_id: 'tb_x', idx: 1 } },
              children: ['tb_x'] } as MatchDict
  const s = matchedIds([m], events, [])
  expect(s.has('tb_x#0')).toBe(false)   // 身份展开的旧行为会进 #0;精确引用不进
  expect(s.has('tb_x#1')).toBe(true)
})

it('qualifiedIdsOf 实例级:同身份两实例可不同档', () => {
  const diag = {
    symbol: 'X', pattern_id: 'bb_v1', note: '',
    nodes: { tb: { attr: [
      { event_id: 'tb_v1_293', instance_key: '#0', start_idx: 3, end_idx: 3,
        clauses: { c1: { cid: 'c1', measured: 1, op: '>=', threshold: 0, satisfied: true, kind: null } } },
      { event_id: 'tb_v1_293', instance_key: '#1', start_idx: 3, end_idx: 3,
        clauses: { c1: { cid: 'c1', measured: 0, op: '>=', threshold: 1, satisfied: false, kind: null } } },
    ], rel: [] } } } as unknown as Diagnostics
  const q = qualifiedIdsOf(diag)
  expect(q.has('tb_v1_293#0')).toBe(true)
  expect(q.has('tb_v1_293#1')).toBe(false)   // 事件级旧行为会全进或全不进
})
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd path2_web_ui && npx vitest run -t "matchedIds 初始集|未被引用|qualifiedIdsOf 实例级"`
Expected: FAIL(现状 matchedIds 按 children 身份展开全部实例、qualifiedIdsOf 单键集)

- [ ] **Step 3: 实现**

`visible.ts` 修改:

```ts
export function matchedIds(
  matches: MatchDict[],
  events: EventDict[],
  edges: TopoEdge[],
  opts: { expandAnchor?: boolean } = {},
): Set<string> {
  const expandAnchor = opts.expandAnchor ?? true
  const s = new Set<string>()
  if (events.length === 0) return s
  const byId = new Map(events.map(e => [instanceKeyOf(e), e]))
  // 单键索引:child_refs/anchor 的身份引用展开为该身份全部实例(视觉同身份)
  const byEventId = new Map<string, EventDict[]>()
  for (const e of events) {
    const arr = byEventId.get(e.event_id)
    if (arr) arr.push(e); else byEventId.set(e.event_id, [e])
  }
  const queue: string[] = []
  const enqueue = (singleId: string): void => {
    for (const inst of byEventId.get(singleId) ?? []) {
      const key = instanceKeyOf(inst)
      if (!s.has(key)) { s.add(key); queue.push(key) }
    }
  }
  // 实例流初始集:match.node_index 的【精确实例】引用(不是身份展开)——match 引用谁就是谁。
  for (const m of matches) {
    for (const ref of Object.values(m.node_index)) {
      const key = ref.event_id + '#' + ref.idx
      if (!s.has(key)) { s.add(key); queue.push(key) }
    }
  }
  if (s.size === 0) return s
  const anchorFields = expandAnchor
    ? new Set(edges.map(e => e.anchor_field).filter((x): x is string => !!x))
    : new Set<string>()
  while (queue.length) {
    const key = queue.pop()!
    const ev = byId.get(key)
    if (!ev) continue
    const refs = ev.child_refs
    if (refs) {
      for (const ids of Object.values(refs)) {
        for (const cid of ids) enqueue(cid)
      }
    }
    if (expandAnchor) {
      for (const af of anchorFields) {
        const v = (ev as Record<string, unknown>)[af]
        if (typeof v === 'string') {
          enqueue(v)
        } else if (Array.isArray(v)) {
          for (const vid of v) {
            if (typeof vid === 'string') enqueue(vid)
          }
        }
      }
    }
  }
  return s
}
```

(注:docstring 同步更新——初始集改精确实例、children 不再作初始集来源;`children` 字段保留作显示投影。)

```ts
/** ⋃_node { e ∈ diag.nodes[nid].attr : isQualifiedRow }。实例流:集合元素为
 *  (event_id, #idx) 复合键(attr 行恒带 instance_key)。 */
export function qualifiedIdsOf(diag: Diagnostics | null): Set<string> {
  const out = new Set<string>()
  if (!diag) return out
  for (const node of Object.values(diag.nodes))
    for (const row of node.attr)
      if (isQualifiedRow(row)) out.add(instanceKeyOf(row))
  return out
}

export function eventTierOf(e: EventDict, matched: Set<string>, qualified: Set<string>): Tier {
  if (matched.has(instanceKeyOf(e))) return 'matched'
  if (qualified.has(instanceKeyOf(e))) return 'qualified'
  return 'detected'
}
```

`resolveTooltipData` 升级(签名加 idx;实例定位与 attr 查找都按复合键):

```ts
export function resolveTooltipData(
  eventId: string,
  idx: number,
  diag: Diagnostics | null,
  events: EventDict[],
  bars: Bar[],
): TooltipPayload {
  const instanceKey = eventId + '#' + idx
  // clauses:attr 行按复合键取【该实例】的判定(多实例各判各的)
  for (const [nodeId, node] of Object.entries(diag.nodes)) {
    const row = node.attr.find((r) => instanceKeyOf(r) === instanceKey)
    ...
  }
  // identity:实例级取该实例
  const ev = events.find((e) => instanceKeyOf(e) === instanceKey)
  ...
}
```

(函数体其余逻辑保持不变,只改两处查找键。调用点 KlineChart.vue:457 的签名同步放 Task 6,本 task 先让新签名测试通过——**注意**:若 vue-tsc 因调用点签名不匹配报红,本 task 顺带同步该调用点(见 Step 5 说明)。)

- [ ] **Step 4: 跑测试确认 PASS**

Run: `cd path2_web_ui && npx vitest run -t "matchedIds 初始集|未被引用|qualifiedIdsOf 实例级"` 与 `npx vitest run tests/visible.spec.ts tests/render.visible.spec.ts`
Expected: 新测试 PASS;既有 visible 测试适配后全绿

- [ ] **Step 5: 既有断言复核与同步**

既有测试若断言 matchedIds 按身份展开全部实例(如「children 身份 → 两实例各进集」类用例),属契约语义变更——先复核:该用例断言的是「身份展开」旧行为,现应改为「node_index 精确引用」语义(按 Step 1 新测试口径)。若 `resolveTooltipData` 调用点(KlineChart.vue:457)导致 tsc 红,同步改为 `(eventId, idx)` 传参(该调用点的完整接线在 Task 6,此处只需签名兼容)。

- [ ] **Step 6: 三绿**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 全绿

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/render/visible.ts path2_web_ui/tests/
git commit -m "feat: visible 判定全实例级(matchedIds 精确初始集 + qualified 复合键 + tooltip 实例级)"
```

---

### Task 5: view.ts focusEvent 双入口 + 焦点实例级

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`(`focusEvent` :670-713、焦点状态 :218-229、导出 :1008)
- Modify: `path2_web_ui/src/render/chart.ts:228-271`(group 判定与 focus 条目改复合键)
- Modify: `path2_web_ui/src/components/KlineChart.vue:456`(computeEventData 传参)
- Test: `path2_web_ui/tests/stores.focus-actions.spec.ts`、`path2_web_ui/tests/stores.disambig.spec.ts`、`path2_web_ui/tests/stores.focus-derivations.spec.ts`

**Interfaces:**
- Consumes: Task 4 的 `instanceKeyOf`;NodeRef node_index
- Produces: `focusEvent(eventId: string, idx?: number)`(双入口);`focusedEventKey: Ref<string | null>`(复合键焦点,store 导出);chart 的 group/focus 判定消费 focusedEventKey

- [ ] **Step 1: 写失败测试(双入口语义)**

在 `tests/stores.focus-actions.spec.ts` 新增:

```ts
it('focusEvent 实例级入口:实例分属直选(不再待选择)', () => {
  // 构造:APCX 形态——两 match 的 node_index 分别引用 tb_v1_293 #0/#1
  const m0 = { event_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293', start_idx: 0, end_idx: 3,
               node_index: { burst: { event_id: 'burst_0_2', idx: 0 }, tb: { event_id: 'tb_v1_293', idx: 0 } },
               children: ['burst_0_2', 'tb_v1_293'] } as MatchDict
  const m1 = { event_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293b', start_idx: 0, end_idx: 3,
               node_index: { burst: { event_id: 'burst_0_2', idx: 1 }, tb: { event_id: 'tb_v1_293', idx: 1 } },
               children: ['burst_0_2', 'tb_v1_293'] } as MatchDict
  // store 注入 matches/events(按既有测试的注入方式)
  view.focusEvent('tb_v1_293', 0)
  expect(view.focusedMatchId).toBe(m0.event_id)          // 直选 match A
  expect(view.pendingDisambigEventId).toBeNull()          // 不再弹待选择
  view.focusEvent('tb_v1_293', 1)
  expect(view.focusedMatchId).toBe(m1.event_id)          // 直选 match B
})

it('focusEvent 实例级入口:真共享实例仍待选择', () => {
  // 同一 {event_id, idx} 被两 match 的 node_index 引用(真正的场景 B)
  const m0 = { event_id: 'bb@0-3a', start_idx: 0, end_idx: 3,
               node_index: { tb: { event_id: 'tb_s', idx: 0 } }, children: ['tb_s'] } as MatchDict
  const m1 = { event_id: 'bb@0-3b', start_idx: 0, end_idx: 3,
               node_index: { tb: { event_id: 'tb_s', idx: 0 } }, children: ['tb_s'] } as MatchDict
  view.focusEvent('tb_s', 0)
  expect(view.pendingDisambigEventId).toBe('tb_s')
  expect(view.candidateMatchIds.size).toBe(2)
})

it('focusEvent 身份级入口:身份下实例分属 → 待选择;单实例身份 → 直选', () => {
  // 分属:点侧栏身份行,两实例归属不同 match → 待选择
  view.focusEvent('tb_v1_293')                            // 不带 idx
  expect(view.pendingDisambigEventId).toBe('tb_v1_293')
  // 单实例身份:唯一归属 → 直选
  view.focusEvent('burst_0_2')                            // 单实例身份(只被 m0 引用)
  expect(view.focusedMatchId).toBe('bb@0-3#burst:burst_0_2|tb:tb_v1_293')
  expect(view.pendingDisambigEventId).toBeNull()
})
```

(store 注入方式以既有 focus-actions 测试为准——grep 其 setup 复用。)

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd path2_web_ui && npx vitest run -t "focusEvent 实例级入口|focusEvent 身份级入口"`
Expected: FAIL(现状 focusEvent(eventId) 按 children 身份展开判定,分属也走待选择)

- [ ] **Step 3: 实现 focusEvent 双入口**

`view.ts` 修改:

```ts
/** 实例的复合键 → 引用它的 match 列表(按 node_index 精确引用计数)。 */
function matchesOfInstance(matches: MatchDict[], eventId: string, idx: number): MatchDict[] {
  const key = eventId + '#' + idx
  return matches.filter(m =>
    Object.values(m.node_index).some(r => r.event_id + '#' + r.idx === key))
}

function focusEvent(eventId: string, idx?: number): void {
  const matches = effectiveAnalysis.value?.matches ?? []
  const events  = effectiveAnalysis.value?.events  ?? []
  const edges   = effectivePattern.value?.topology.edges ?? []

  // add 焦点 node 到展开集(不折叠其他 node)
  const ev = idx !== undefined
    ? events.find(e => instanceKeyOf(e) === eventId + '#' + idx)
    : events.find(e => e.event_id === eventId)
  if (ev) {
    const node = nodeOfEventByBand(ev, tagMap.value.tagToNodes, tagMap.value.tagList)
    if (node && !manualExpandedNodes.value.has(node)) {
      const s = new Set(manualExpandedNodes.value)
      s.add(node)
      manualExpandedNodes.value = s
    }
  }

  let ms: MatchDict[]
  if (idx !== undefined) {
    // 实例级入口(marker 点击):按实例精确归属
    ms = matchesOfInstance(matches, eventId, idx)
  } else {
    // 身份级入口(侧栏 trace 行/候选表行):身份下全部实例的归属并集
    const ids = new Set<string>()
    const insts = events.filter(e => e.event_id === eventId)
    for (const inst of insts) {
      const i = Number(inst.instance_key?.replace('#', '') ?? 0)
      for (const m of matchesOfInstance(matches, eventId, i)) ids.add(m.event_id)
    }
    ms = matches.filter(m => ids.has(m.event_id))
  }

  if (ms.length === 0) {
    focusedMatchId.value = null
    focusedEventId.value = eventId
    clearCandidates()
  } else if (ms.length === 1) {
    focusedMatchId.value = ms[0].event_id
    focusedEventId.value = eventId
    clearCandidates()
  } else {
    focusedMatchId.value = null
    focusedEventId.value = null
    setCandidateMatches(ms.map(m => m.event_id))
    setPendingDisambig(eventId)
  }
  autoFollowLevel(eventId)
}
```

焦点实例级状态(在焦点状态区新增):

```ts
/** 焦点复合键(实例级):marker 点击的精确实例;身份级入口无 idx 时为 null(事件级焦点)。 */
const focusedEventKey = ref<string | null>(null)
```

在 focusEvent 的直选/聚焦分支设置:`focusedEventKey.value = idx !== undefined ? eventId + '#' + idx : null`;clearFocus/focusMatch/clearCandidates 等清空路径同步清 `focusedEventKey.value = null`(grep `focusedEventId.value = null` 全部位置,逐处配套)。导出(:1008)加 `focusedEventKey`。

- [ ] **Step 4: chart.ts 焦点判定改复合键**

`chart.ts`(computeEventData 内):

```ts
// group 条目跳过焦点实例(被点 marker 由 focus 条目独家表达)
const inGroup = (d: { event_key: string }) =>
  highlightedEventIds.has(d.event_key) && d.event_key !== focusedEventKey
```

focus 条目(现状 :260-269 按 event_id find)改为按复合键 find:

```ts
if (focusedEventKey) {
  const selPoint = pointData.find((d) => d.event_key === focusedEventKey)
  if (selPoint) highlightData.push({ ...selPoint, kind: 'focus' as HlKind })
  else {
    const selInterval = intervalData.find((d) => d.event_key === focusedEventKey)
    if (selInterval) highlightData.push({ ...selInterval, kind: 'focus' as HlKind })
    else {
      const selPricePoint = pricePointData.find((d) => d.event_key === focusedEventKey)
      if (selPricePoint) highlightPriceData.push({ ...selPricePoint, kind: 'focus' as HlKind })
    }
  }
}
```

(computeEventData 入参加 `focusedEventKey`(复合键),KlineChart.vue:456 传 `view.focusedEventKey`。)

- [ ] **Step 5: 跑测试确认 PASS + 三绿**

Run: `cd path2_web_ui && npx vitest run -t "focusEvent" && npx vitest run tests/stores.focus-actions.spec.ts tests/stores.disambig.spec.ts tests/stores.focus-derivations.spec.ts && npx vue-tsc --noEmit`
Expected: 新测试 PASS;既有 focus/disambig 测试适配后全绿(既有「实例分属走待选择」类断言属语义变更,先复核按新语义改);tsc 绿

- [ ] **Step 6: 既有断言复核与同步**

既有 disambig 测试若断言「点击共享事件 → 待选择」,复核其 fixture:若用的是同 event_id 不同 idx 的实例(分属),按新语义改为断言直选;若同 idx 共享,断言保持待选择。既有 focus-derivations 的 selectedEventId 派生断言保持(selectedEventId 字段语义不变)。

- [ ] **Step 7: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/src/render/chart.ts path2_web_ui/src/components/KlineChart.vue path2_web_ui/tests/
git commit -m "feat: focusEvent 双入口(实例直选/身份并集)+ 焦点实例级(focusedEventKey)"
```

---

### Task 6: 交互接线 — 点击传实例 + tooltip 实例级

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.ts:12-16`(ChartClickPayload)、`:60-78`(handleChartClick)
- Modify: `path2_web_ui/src/components/KlineChart.vue:457`(tooltipResolver 传 idx)
- Test: `path2_web_ui/tests/components.kline-click.spec.ts`、`path2_web_ui/tests/render.chart-tooltip.spec.ts`

**Interfaces:**
- Consumes: Task 4 的 `resolveTooltipData(eventId, idx, ...)` 签名;Task 5 的 `focusEvent(eventId, idx?)`
- Produces: marker 点击经 `data.event_key` 解析为 (event_id, idx) 传入 focusEvent;tooltip 显示所悬停实例

- [ ] **Step 1: 写失败测试(点击传实例)**

在 `tests/components.kline-click.spec.ts` 新增:

```ts
it('marker 点击按 event_key 解析实例并直选(不分属待选择)', () => {
  // 构造与 Task 5 相同的 APCX 形态 store fixture
  // marker data 带 event_key: 'tb_v1_293#0'
  handleChartClick(
    { seriesName: 'points', data: { event_id: 'tb_v1_293', event_key: 'tb_v1_293#0' } },
    [], view,
  )
  expect(view.focusedMatchId).toBe(m0.event_id)   // 直选引用 #0 的 match
  expect(view.pendingDisambigEventId).toBeNull()
})
```

- [ ] **Step 2: 跑测试确认 FAIL**

Run: `cd path2_web_ui && npx vitest run -t "marker 点击按 event_key"`
Expected: FAIL(现状 handleChartClick 只传 event_id,focusEvent 身份级判定 → 分属走待选择)

- [ ] **Step 3: 实现**

`KlineChart.ts`:

```ts
export type ChartClickPayload = {
  seriesName?: string
  data?: { event_id?: string; match_id?: string; event_key?: string }
} | null

export function handleChartClick(
  p: ChartClickPayload,
  matches: MatchDict[],
  view: ReturnType<typeof useViewStore>,
): void {
  if (!p || !p.seriesName) {
    view.clearFocus()
    return
  }
  if (p.seriesName === 'brackets' && p.data?.match_id) {
    view.focusMatch(p.data.match_id)
    return
  }
  if (MARKER_SERIES.includes(p.seriesName) && p.data?.event_id) {
    // 实例流:marker 数据带 event_key 复合键(event_id#idx,event_id 不含 '#' 由契约保证)
    // → 解析实例传入 focusEvent(实例级入口,直选分属实例);event_key 缺失(理论不可达)
    // 时按身份级入口退化。
    const key = p.data.event_key
    if (key) {
      const hash = key.lastIndexOf('#')
      view.focusEvent(key.slice(0, hash), Number(key.slice(hash + 1)))
    } else {
      view.focusEvent(p.data.event_id)
    }
    return
  }
}
```

`KlineChart.vue:457`(tooltipResolver)——现状 `(id: string) => resolveTooltipData(id, diag, events, bars)`;tooltip 触发时能拿到 data 的 event_key 的,改为:

```ts
tooltipResolver: (id: string, idx?: number) =>
  resolveTooltipData(id, idx ?? 0, diag.value, effectiveAnalysis.value?.events ?? [], bars.value),
```

(以 KlineChart.vue 中 tooltip 触发与 resolver 的实际调用方式为准:若触发处已能拿到 `data.event_key`,解析 idx 传入;若只传 id,先读该段代码确认触发数据,补齐 event_key 传递——**目标是 tooltip 显示所悬停实例的判定**。)

- [ ] **Step 4: 跑测试确认 PASS + 三绿**

Run: `cd path2_web_ui && npx vitest run -t "marker 点击按 event_key|tooltip" && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 新测试 PASS;全量绿

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.ts path2_web_ui/src/components/KlineChart.vue path2_web_ui/tests/
git commit -m "feat: marker 点击绑定实例(event_key 解析)+ tooltip 实例级"
```

---

### Task 7: 全量回归 + 真实数据验收 + 报告

**Files:**
- Create: `docs/research/2026-08-13_marker-instance-binding/repro/final_report.md`(验收结果)

**Interfaces:**
- Consumes: Task 1-6 全部改动;真实 scan 数据 `outputs/path2_web/scans/20260813T005540.json`(APCX 双实例)
- Produces: 验收报告(直选/真共享/身份级入口三场景 + 回归摘要)

- [ ] **Step 1: 后端全量回归**

Run: `uv run pytest tests/ -q`
Expected: 全绿(或仅 pre-existing 失败名单:test_throwback_debug_anchor_kinds 4 个 + bb_v1/bb_v3 p2.yaml 2 个——与实施前对照确认无新增)

- [ ] **Step 2: 前端三绿**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 全绿(4 个 sidebar-result-list pre-existing 失败与实施前对照确认无新增)

- [ ] **Step 3: 真实数据验收(数据级断言)**

在 `path2_web_ui/tests/` 新增验收测试 `instance-binding-acceptance.spec.ts`(加载真实 scan json):

```ts
import scanJson from '../../outputs/path2_web/scans/20260813T005540.json'
it('APCX 真实数据:实例分属直选,身份级入口待选择,真共享待选择', () => {
  // 1) 从 scanJson 提取 APCX 的 analysis(events/matches),注入 store(按既有注入方式)
  // 2) 断言:tb_v1_293 有两实例(#0/#1),各被一个 match 的 node_index 精确引用
  // 3) focusEvent('tb_v1_293', 0) → focusedMatchId = 引用 #0 的 match,无待选择
  //    focusEvent('tb_v1_293', 1) → focusedMatchId = 引用 #1 的 match
  // 4) focusEvent('tb_v1_293')(身份级)→ pendingDisambigEventId = 'tb_v1_293'
  // 5) 构造真共享 fixture(同 idx 被两 match 引用)→ 仍待选择
})
```

(json import 方式以项目既有 spec 读 json 的先例为准;若 vitest 环境不便 import json,改为在测试内 fs.readFile + JSON.parse,路径相对 path2_web_ui/。)

- [ ] **Step 4: 跑验收测试确认 PASS**

Run: `cd path2_web_ui && npx vitest run instance-binding-acceptance.spec.ts`
Expected: PASS(三场景全部成立)

- [ ] **Step 5: 写验收报告**

在 `docs/research/2026-08-13_marker-instance-binding/repro/final_report.md` 记录:契约变更摘要、判定语义(三档实例级/双入口/待选择收窄)、回归摘要(后端/前端失败对照)、真实数据验收结果(APCX 直选 + 身份级待选择 + 真共享 fixture 待选择)、遗留观察(如有)。

- [ ] **Step 6: Commit**

```bash
git add docs/research/2026-08-13_marker-instance-binding/ path2_web_ui/tests/instance-binding-acceptance.spec.ts
git commit -m "chore: marker 实例绑定验收(真实 APCX 数据直选 + 回归全绿 + 报告)"
```

---

## 实施完成判定

- 全部 7 个 task(Task 1-7)完成且每 task commit 到实施分支;
- 前端三绿(vitest / vue-tsc / vite build)+ 后端 pytest 无新增失败;
- 真实数据验收通过(APCX 实例分属直选、身份级入口待选择、真共享仍待选择);
- 验收报告入档(docs/research/2026-08-13_marker-instance-binding/repro/final_report.md)。
