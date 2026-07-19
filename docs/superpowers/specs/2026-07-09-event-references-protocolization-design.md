# Event-References Protocolization Design

**Date**: 2026-07-09
**Scope**: `path2_web/serialize.py` + `path2_web_ui/` (types + visible.ts + view store + tests)

## 1. 目标

把 path2_web + path2_web_ui 里"事件间引用归属"的判定链完全按 path2 引擎协议实现，去掉三处硬编码字段名（`members` 特判、前端 `members` / `anchor_bo_id` 字面读、tooltip SKIP 里的 `'members'`），并顺带修一个已知 UI bug：**选中一个 match 后主图 BO 方框不显示 in-group 深边**（跟颜色通道语义不一致）。

**验收信号**：
- 后端 `_event_to_dict` / `serialize_pattern` 里不再出现字符串常量 `"members"` / `"anchor_bo_id"`；
- 前端 `visible.ts` 不再出现 `.members` / `.anchor_bo_id` 字段名读取；
- 端到端：选中 match 后主图 BO 方框有 in-group 深灰蓝细边（当前是无边 bug）。

## 2. 背景

### 2.1 引擎侧已有协议

- `Event.child_slots(self) -> Mapping[str, Event | Tuple[Event, ...]]`（`path2/core.py:77`）
  基类协议方法，子类覆写声明自己**持有**的子 event 引用。BurstEvent 覆写为 `{"members": self.members}`。叶子 event 返回 `{}`。
- `DependencyEdge.anchor_field: Optional[str]`（`path2/dag/edges.py:56`）
  边侧字段，声明 dst event 上"锚点字段名"用于跟 src event 复核身份。当前唯一实例：`TemporalEdge(Child("burst","last_bo"), "tb", anchor_field="anchor_bo_id")`（`path2_apps/bottom_breakout_burst/dag_spec.py:56`）。
- `NodeSpec.consumes_stream: Optional[str]`（`path2/dag/nodes.py:34`）
  detector 输入流声明，跟"某个 event 是否属于某个 match"**无关**——本次设计明确不进入判定。

### 2.2 现状硬编码点（要清理）

| 位置 | 硬编码内容 |
|---|---|
| `path2_web/serialize.py:47-52` | `if f.name == "members"` 特判扁平化为 event_id 列表 |
| `path2_web_ui/src/render/visible.ts:19-27` | `ev.members` / `ev.anchor_bo_id` 字面读取 + 递归入队 |
| `path2_web_ui/src/render/visible.ts:128` | tooltip SKIP 集合硬编码 `'members'` |

### 2.3 UI Bug（会作为 essence 一并修复）

选中一个 match 时：
- **颜色通道**（`matchedIds` computed）沿 `members` 展开，BO 显示为 role 色（matched tier）✅
- **边框通道**（`highlightedEventIds` 用 `match.children`）不展开 members，BO 无 in-group 深边 ❌

现象：主图 `[7]` 方框绿底但无深边，与副图 in-group markers 不一致。根因是两条通道用两套判据，本次 spec 把它们统一到同一份 `matchedIds()` 展开逻辑。

## 3. 设计

### 3.1 协议映射（总览）

| 引用类型 | 引擎协议 | 后端 payload 承载 | 前端消费 |
|---|---|---|---|
| **持有型子引用** | `Event.child_slots()` | event dict 加 `child_refs: {slot_name: [event_id, ...]}` | 遍历 `ev.child_refs` 所有 slot value 递归入队 |
| **锚点弱引用** | `DependencyEdge.anchor_field` | topology edge 元素加 `anchor_field?: string | null` | 从 pattern.topology.edges 反查所有非空 anchor_field 名字，读 event 上对应字段入队 |
| ~~detector 流消费~~ | ~~`consumes_stream`~~ | — | 不参与归属判定 |

### 3.2 后端改动（`path2_web/serialize.py`）

**A. `_event_to_dict` 改写**

删除 `members` 特判（当前 line 47-52）：

```python
# 删除：
if (f.name == "members" and isinstance(val, tuple) and val
        and hasattr(val[0], "event_id")):
    d[f.name] = [m.event_id for m in val]
```

fields 循环里跳过所有 `child_slots` 已声明的 slot key（避免与 child_refs 冗余、字段类型混乱）：

```python
skip_slots = set(e.child_slots().keys())   # BurstEvent -> {"members"}
for f in dataclasses.fields(e):
    if f.name in ("event_id", "start_idx", "end_idx"):
        continue
    if f.name in skip_slots:
        continue     # 由 child_refs 承载
    d[f.name] = _jsonable(getattr(e, f.name))
```

序列化尾部加 `child_refs`：

```python
d["child_refs"] = {
    name: [c.event_id for c in (slot if isinstance(slot, tuple) else (slot,))]
    for name, slot in e.child_slots().items()
}
```

- 叶子 event（`child_slots() == {}`）→ `child_refs = {}`
- BurstEvent → `child_refs = {"members": [bo_id1, bo_id2, ...]}`；payload 不再有顶层 `members` 字段

**B. `serialize_pattern` 里 edges 加 anchor_field**

```python
edges = [
    {"src": te.src, "dst": te.dst, "kind": te.kind, "rule": _edge_rule(de),
     "anchor_field": de.anchor_field}
    for te, de in zip(topo.edges, spec.edges)
]
```

`anchor_field` 未设置的 edge 输出 `None`（保持 shape 稳定，前端过滤空值）。

### 3.3 前端改动（`path2_web_ui/`）

**A. `src/types.ts`**

- `EventDict`：删任何显式 `members` 字段（如有），加：
  ```ts
  child_refs: Record<string, string[]>
  ```
- `TopoEdge`：加 `anchor_field?: string | null`

**B. `src/render/visible.ts` — `matchedIds` 改协议驱动**

签名扩展：
```ts
export function matchedIds(
  matches: MatchDict[],
  events: EventDict[],
  edges: TopoEdge[],
): Set<string>
```

递归展开：
1. 从 matches 收 `match.children` 入初始集
2. 沿 `ev.child_refs` 所有 slot value（`string[]`）递归入队
3. 沿 `edges` 收集所有非空 `anchor_field` 名字（Set），遍历 event 上对应字段（string）入队

**不再读**任何字面字段名 `members` / `anchor_bo_id`。函数注释同步更新（去掉现在写的"沿 members 和 anchor_bo_id 字段"表述）。

**C. `visible.ts:128` tooltip SKIP**

- 移除 `'members'`（payload 里已无此字段）
- 加 `'child_refs'`（新的元字段，tooltip 不平铺展示）

**D. `src/stores/view.ts` — 声明式对齐 group 高亮**

`highlightedEventIds` 从 ref+setter 改为 **computed** 声明式派生：

```ts
const highlightedEventIds = computed<ReadonlySet<string>>(() => {
  const m = selectedMatch.value
  if (!m) return new Set<string>()
  const events = effectiveAnalysis.value?.events ?? []
  const edges = effectivePattern.value?.topology.edges ?? []
  return matchedIdsOf([m], events, edges)
})
```

删除的 API + 调用点：
- `setHighlightedEvents(ids)` 函数定义
- `clearHighlight()` 函数定义
- `loadScanFile`/`clearScanFile`/`selectSymbol`/`setActivePattern` 里的 `highlightedEventIds.value = new Set()` 四处显式清理（selectedMatch 会随 clearSelection 自动置空）
- `KlineChart.ts` marker `ms.length===1` 分支的 `view.setHighlightedEvents(ms[0].children)`
- `KlineChart.ts` bracket 分支的 `view.setHighlightedEvents(...)`
- `KlineChart.ts` marker `ms.length===0` 分支的 `view.clearHighlight()`（合并到 `selectMatch(null)` 的自动派生里）
- `DetailSidebar.vue` `selectMatchAndHighlight` 内部对 setHighlightedEvents 的调用（如有）

**E. 全局 `matchedIds` computed 同步（`view.ts:445`）**

```ts
const matchedIds = computed<Set<string>>(() => matchedIdsOf(
  effectiveAnalysis.value?.matches ?? [],
  effectiveAnalysis.value?.events ?? [],
  effectivePattern.value?.topology.edges ?? []))
```

### 3.4 迁移方式

**一步到位、无 dual-write、无 legacy flag**：
- 后端 + 前端类型 + 前端逻辑 + tests 同 commit（或一组紧邻 commit）落地
- 无外部消费者，纯内部协议

### 3.5 marker click filter 协议对齐

**问题**：`highlightedEventIds` 声明式派生后，颜色/边框通道对齐了；但 `KlineChart.ts:99` 的 marker click filter 仍读 `m.children`（不含 bo，因 bo 是拓扑孤立无边 role），点 bo 走 `ms.length === 0` fallback——**tier=matched 的 event 点击行为与颜色通道再次不一致**（新出现的语义 gap）。

**改动**：filter 判据从 `m.children.includes(eventId)` 改为 `matchedIdsOf([m], events, edges).has(eventId)`。

```ts
// KlineChart.ts marker 分支
const events = view.effectiveAnalysis?.events ?? []
const edges = view.effectivePattern?.topology.edges ?? []
const ms = matches.filter((m) => matchedIdsOf([m], events, edges).has(eventId))
```

**语义**：
- bo / tb 通过 `child_refs` / `anchor_field` 内嵌引用时，点击可查出所属 match
- 单归属：直接 `selectMatch`（与 burst / tb 点击一致）
- **多归属**（bo 属于多个 burst → 多个 match，或 bo → burst → 该 burst 属于多个 match）：`ms.length > 1` 进 candidate 分支，UI 已有 candidate 消解面板承载。多级歧义在 `matchedIds` 递归展开时被扁平化为**单层 candidate 列表**，无需多级选择树
- 真无归属（qualified/detected tier 的 bo）：仍走 fallback

**签名不变**：`handleChartClick(p, matches, view)`——events / edges 内部从 view store 读，测试通过 `loadScanFile` 注入。

## 4. 非目标

- 不改 `Event.child_slots` / `DependencyEdge.anchor_field` 引擎协议本身
- 不改 pattern DAG 语义（bo 仍是孤立 role，不进 match.role_index）
- 不重构 `hoveredEventId` / `candidateMatchIds` 等其它 store 状态
- 不引入 event 元描述系统（"这个 event 有哪些字段"）——`child_slots` + `anchor_field` 已足够

## 5. 测试策略

### 5.1 后端（pytest）

- `tests/path2_web/test_serialize.py`（或对应文件）：
  - BurstEvent event dict：`"members" not in d`，`d["child_refs"] == {"members": [bo_id_1, bo_id_2, ...]}`
  - 叶子 event（BOEvent / TBEvent）：`d["child_refs"] == {}`
  - `serialize_pattern(...)["topology"]["edges"][0]["anchor_field"]` == `"anchor_bo_id"`（bottom_burst 的 tb 边）
  - 无 anchor 的边 `anchor_field` == `None`

### 5.2 前端（vitest）

- `tests/visible.spec.ts` `matchedIds`：
  - 沿 `child_refs.members` 递归展开（构造 fake burst event with child_refs）
  - 沿 edges.anchor_field 反查 tb.anchor_bo_id 入队
  - 无 child_refs 且无 anchor 的叶子 event → 只含 match.children
- `tests/chart.spec.ts` 新增：
  - 选中 match 后主图 BO 方框渲染断言 `lineWidth === HL_GROUP_STROKE_WIDTH` + `stroke === HL_FOCUS_EDGE`（当前 bug：无边）
- `tests/components.kline-click.spec.ts`：
  - 删除对 `setHighlightedEvents` 的断言（API 消失）
  - 保留"marker click 选中一条 match"的行为断言、验证 `highlightedEventIds`（现在是 computed）自动跟上
  - 新增（§3.5）：多归属 bo → candidate 分支；单归属 bo → selectMatch + highlight 沿 child_refs 展开；真无归属 bo → fallback（三分支覆盖）

### 5.3 Gate

pytest（后端）+ vitest（前端 unit）+ vue-tsc + build + playwright（e2e）四绿。

## 6. 端到端验证（Playwright）

**目标场景**：主图 BO 方框 in-group 深边（当前 bug 的验证靶）

**步骤**：
1. 加载 LPCN 历史 scan `2026-07-08 09:24:04`（3 hits）
2. 点副图任一 marker 触发 `ms.length===1` 分支，选中一条 match
3. 截图主图（`browser_resize(2560, 1440)` + `scale="device"` + `target=<BO 方框 selector>` `fullPage=false`）
4. 断言：BO 方框颜色 = role 色（绿；matched tier，之前就正确）**+** 边框 = 深灰蓝细边（`HL_GROUP_STROKE_WIDTH = 1.5` + `HL_FOCUS_EDGE`）
5. 反向断言：切换到别的 match / clearSelection，BO 方框回到无边默认态

**次要验证**：
- 副图 markers 的 in-group 高亮行为**不变**（回归靶）
- 现有多 pattern / 缓冲扫描等其它 UI 场景全部照旧（回归靶）

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `matchedIds` 签名变化引起编译错（3rd 参 edges） | vue-tsc 立即暴露；spec §3.3.E 已列出同步点 |
| 后端 `_event_to_dict` fields 循环里 skip_slots 漏了某些非 slot 但含 event 对象的字段（未来） | 目前 BurstEvent 唯一 case；未来新 event 类通过 `child_slots` 声明即可，无需改序列化 |
| `highlightedEventIds` 声明式派生后有场景需要"临时 highlight 但不改 selectedMatch" | 当前 3 处 setter 全是"选中 match 就展开成员"、一一对应；hover 是独立 `hoveredEventId` 通道；无风险场景 |
| Playwright BO 方框边框颜色断言不稳（sub-pixel / anti-alias） | 用 selector 抓 canvas 后 `evaluate` 直接读 ECharts option / 或直接查 `highlightedEventIds` computed value 断言逻辑层 |
| §3.5 filter 判据变 `matchedIdsOf` 后每次 marker click 触发 O(matches × 平均展开集大小) 展开 | 对 bottom_burst（typically <10 matches / 每 match 平均展开集 <20 events）可忽略；如未来 pattern 规模爆炸，可在 filter 前预缓存 per-match matchedIds Set |

## 8. Out of scope（备忘，不做）

- `consumes_stream` 语义变更（本次明确剔除出归属判定）
- pattern DAG 层面把 bo 塞进 `match.role_index`（保留 bo 孤立 role 的既有拓扑语义）
- 引入更通用的"event 元描述"系统（YAGNI）
