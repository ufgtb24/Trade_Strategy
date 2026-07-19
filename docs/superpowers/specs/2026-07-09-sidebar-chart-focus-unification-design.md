# Sidebar-Chart Focus Unification Design

**Date**: 2026-07-09
**Scope**: `path2_web_ui/src/stores/view.ts` + `path2_web_ui/src/components/{KlineChart.ts,DetailSidebar.vue}` + tests

## 1. 目标

把 sidebar / 主图 / 副图 三处的**选中态与联动**统一到单一心智模型:

- 两处 event 点击(副图/主图 event marker 与 sidebar 候选表 event 行)**底层复用同一条判定路径**;bracket 点击等价于 sidebar「命中匹配」某行点击。
- sidebar 视图按**焦点意图**(match-focus / event-focus)分化:bracket 触发的焦点展开「匹配 trace」;event 触发的焦点只展开该 event 所在 role 的候选表,不展开 trace。
- 「命中匹配」列表如实反映 event 所属的**所有** matches(信息层),多归属 pending 状态同时高亮多行;主图/副图 group 黑框只在 disambig 后单亮(视觉层)。
- level 门控在选中 event 时**自动降到刚好能容纳该 event 的档**,消除"sidebar 选了个 event 图上没反应"的手感断层。
- 候选表**就地**展开在漏斗当前展开行的下方(不再另开"xx 候选"通用区)。

**验收信号**:
- `view.focusMatch(mid)` / `view.focusEvent(eid)` / `view.clearFocus()` 三个 action 承担现有 6 处点击(3 处 KlineChart · 3 处 DetailSidebar)的选中操作,消除现有 `selectMatch` / `selectRole` / `selectEvent` / `clearSelection` 分叉。
- 6 个派生 computed(`selected` / `selectedMatch` / `selectedMatchId` / `selectedEventId` / `highlightedEventIds` / `markedMatchIds` / `markedEventIds` / `expandedNodeId` / `showTrace`)从 `focusedMatchId` + `focusedEventId` + `candidateMatchIds` + `pendingDisambigEventId` 上派生;渲染层(chart.ts / KlineChart.vue / DetailSidebar 模板)零逻辑改动。
- sidebar 候选表移入漏斗行循环体、按 `expandedNodeId` 就地展开;「匹配 trace」按 `showTrace` 显示;多归属时命中匹配列表所有 candidate 行同时黄底 + 候选表 pending 行黄底。
- 选 detected/qualified tier event 时 `level` 自动降;e2e 覆盖 bracket click / event marker 唯一归属 / event marker 多归属 / sidebar 命中匹配→反打副图 bracket / sidebar 候选表 detected event → level 自动降 五个场景。

## 2. 背景

### 2.1 现状(commit HEAD)

**状态字段**:
```
selected: {kind:'match', matchId} | {kind:'role', nodeId} | null   // 3 kind 复合
selectedEventId: string | null                                     // event focus
candidateMatchIds: ReadonlySet<string>                             // 多归属候选(副轴)
pendingDisambigEventId: string | null                              // 多归属 pending(副轴)
level: 'matched' | 'qualified' | 'detected'                        // 全局门控
```

**Actions**: `selectMatch(id|null)` · `selectRole(nodeId)` · `selectEvent(id|null)` · `clearSelection()` · `setCandidateMatches(ids[])` · `clearCandidates()` · `setPendingDisambig(eid|null)` · `setLevel(l)`.

**6 处消费点**:
- `KlineChart.ts::handleChartClick` 空白 / brackets / MARKER_SERIES 三分支(8 行 4 分支的 marker 归属判定内联在这里)
- `DetailSidebar.vue` 里 `selectCandidateRow` / `selectMatchRow` / `selectRoleEvent`

**sidebar 视图现状**:
- 「命中匹配」列表 analysis 就绪常驻;`.match-row--selected` 判据 `selected.kind==='match' && matchId==='...'`
- 「匹配 trace」`v-if="selected?.kind==='match' && selectedMatch"` —— **只要 selectedMatch 存在就展**,包括 marker 唯一归属场景
- 「候选表」`v-if="expandedNode && diag"` 在漏斗列表下方通用位置,内容是 `diag.roles[expandedNode].attr`
- `watch(selected)`:`kind==='role'` → 展开 expandedNode;`kind==='match'` → 收 expandedNode + 滚到 trace

### 2.2 五个诉求(问题 5 已在 [event-references-protocolization commit 3782cb6] 解决,不在本 spec 范围)

1. 候选表就地展开在漏斗行下方,不新开"xx 候选"通用区。
2. sidebar 候选表 event 点击 = marker 点击,底层复用同一函数(含多归属判定)。
3. sidebar 视图按点击来源分化:
   - bracket click → 显示「命中匹配」+「匹配 trace」
   - event marker click → 展开该 event 所在 role 的候选表并高亮该 event;不展 trace
   - sidebar「命中匹配」某行 click = bracket click(反打副图 bracket + trace 展开)
4. sidebar 选中的 event 若不在当前 level 门控内,主图/副图自动降 level 让其可见。

### 2.3 内在根源(为什么要一起改)

现有 `selected`(match/role)+ `selectedEventId` 双轴不对齐:
- 「匹配 trace」判据 `selected.kind==='match'` 只看 match 焦点,不看 event 焦点 → 唯一归属场景 event marker click 触发 selectMatch(m)+selectEvent(eid) → 落到「展 trace」→ **违反诉求 3**。
- 两处 event 点击(marker vs sidebar 候选表)分别在 `handleChartClick` 和 `selectCandidateRow` 里各自写归属分支,`selectCandidateRow` 只做 `clearCandidates + selectEvent(eid)`,没走归属判定 → **违反诉求 2**。
- level 与选中互不知情 → **违反诉求 4**。
- 候选表 template 挂在 v-for 外的 outer scope → **违反诉求 1**。

单点修补每一处会让 selected/selectedEventId 双轴的判据分叉更多。本 spec 把状态字段收敛(去 selected 复合 kind、留 `focusedMatchId`/`focusedEventId` 两条正交焦点轴)、把 6 处消费复用到 3 个 action。渲染层(chart.ts / 组件模板)通过派生 computed 保持导出符号名不变,零逻辑改动。

## 3. 设计

### 3.1 状态模型收敛

**状态字段**:
```ts
focusedMatchId:        string | null              // 原 selected.kind==='match' 折成单值
focusedEventId:        string | null              // 原 selectedEventId,改名对齐
candidateMatchIds:     ReadonlySet<string>        // 副轴(不动)
pendingDisambigEventId: string | null             // 副轴(不动)
level:                 'matched'|'qualified'|'detected'  // 加 auto-follow(§3.4)
hoveredEventId:        string | null              // 不动
manualExpandedNode:    string | null              // sidebar 手动 toggle 兜底(用户点漏斗行)
```

**删除**:`selected` 的 `'role'` 分支——通过 `focusedEventId` 派生 event 所在 role 展开。

**派生 computed**(渲染层零改动):
```ts
selected            = focusedMatchId ? {kind:'match', matchId:focusedMatchId} : null
selectedMatch       = matches.find(m => m.event_id === focusedMatchId)
selectedMatchId     = focusedMatchId
selectedEventId     = focusedEventId
highlightedEventIds = focusedMatchId 存在 ? matchedIdsOf([selectedMatch], events, edges) : ∅
showTrace           = focusedMatchId !== null && focusedEventId === null   // 唯一 trace 展开判据
expandedNodeId      = (focusedEventId ?? pendingDisambigEventId)
                      ? roleOfEventByBand(该 event, tagMap.tagToNodes, tagMap.tagList)
                      : manualExpandedNode
markedMatchIds      = focusedMatchId ? {focusedMatchId}
                      : candidateMatchIds.size ? candidateMatchIds   // 多归属如实反映所有归属
                      : ∅
markedEventIds      = focusedEventId ? {focusedEventId}
                      : pendingDisambigEventId ? {pendingDisambigEventId}   // 多归属 pending 反馈
                      : ∅
```

**语义分层**:
- **信息层**(sidebar 命中匹配列表 / 候选表 pending 行):如实反映所有归属;多归属时多行同亮;点行 = disambig 入口。
- **视觉层**(主/副图 group 黑框 / focus event 深边):group 语义唯一;多归属时不亮 group;disambig 后收敛到单 group + focus event。

### 3.2 六种交互场景一致性

| 交互来源 | focusedMatchId | focusedEventId | candidateMatchIds | showTrace | 主/副图 group | 命中匹配 marked | 候选表 marked |
|---------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 副图 bracket click | m | null | ∅ | **展** | 亮 m | {m} 单行 | ∅ |
| event marker(唯一 m) | m | eid | ∅ | 不展 | 亮 m | {m} 单行 | {eid} |
| event marker(0 归属) | null | eid | ∅ | 不展 | ∅ | ∅ | {eid} |
| event marker(多归属) | null | null | {m₁,m₂,...} | 不展 | ∅(待 disambig) | {m₁,m₂,...} 多行同亮 | {eid} pending 行 |
| sidebar 候选表 event | 走 focusEvent(eid) 走同一 4 分支 | | | | | | |
| sidebar 命中匹配 某行 | m | null | ∅ | 展 | 亮 m | {m} 单行 | ∅ |
| sidebar trace role 行 | 走 focusEvent(eid) 走同一 4 分支 | | | | | | |

### 3.3 三个统一 action + 6 处消费

```ts
// stores/view.ts
function focusMatch(matchId: string): void {
  focusedMatchId.value = matchId
  focusedEventId.value = null
  manualExpandedNode.value = null   // 收候选表,对齐现有 watch(selected) kind==='match' → expandedNode=null
  clearCandidates()
}

function focusEvent(eventId: string): void {
  void triggerCandidateQuery(eventId)                  // scope=candidate 淘汰路径,fire-and-forget
  const matches = effectiveAnalysis.value?.matches ?? []
  const events  = effectiveAnalysis.value?.events  ?? []
  const edges   = effectivePattern.value?.topology.edges ?? []
  const ms = matches.filter(m => matchedIdsOf([m], events, edges).has(eventId))

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
  autoFollowLevel(eventId)                             // §3.4
}

function clearFocus(): void {
  focusedMatchId.value = null
  focusedEventId.value = null
  clearCandidates()
}
```

**6 处消费改造**:

| 位置 | 改后代码 |
|------|---------|
| `KlineChart.ts::handleChartClick` — 空白 | `view.clearFocus()` |
| `KlineChart.ts::handleChartClick` — brackets | `view.focusMatch(p.data.match_id)` |
| `KlineChart.ts::handleChartClick` — MARKER_SERIES | `view.focusEvent(p.data.event_id)` |
| `DetailSidebar::selectMatchRow(mid)` | `view.focusMatch(mid)` |
| `DetailSidebar::selectRoleEvent(val)` — trace role 行 | `view.focusEvent(roleEventId(val))` |
| `DetailSidebar::selectCandidateRow(eid)` — 候选表行 | `view.focusEvent(eid)` |

**旧 store API 全删**(测试同步改):`selectMatch` / `selectRole` / `selectEvent` / `clearSelection`;`setCandidateMatches` / `setPendingDisambig` / `clearCandidates` 保留(focusEvent 内部使用)。

**初始化 4 处**(`loadScanFile` / `clearScanFile` / `selectSymbol` / `setActivePattern`)统一改成调 `clearFocus()`。

### 3.4 sidebar 视图分化(问题 1 / 3-1 / 3-2 / 3-3)

**a) 候选表就地展开**(问题 1) — DetailSidebar template 结构:
```html
<template v-if="effectivePattern && effectiveAnalysis">
  <h3>角色漏斗</h3>
  <div v-for="node in effectivePattern.topology.nodes" :key="node.node_id">
    <div class="funnel-row" @click="!isolated.has(node.node_id) && toggleExpand(node.node_id)"
         :class="{ 'funnel-row--selected': expandedNodeId === node.node_id && !isolated.has(node.node_id) }">
      <!-- ... 漏斗内容 ... -->
    </div>
    <!-- 就地展开:候选表跟在当前展开的 funnel-row 下方(不再挂在 v-for 外) -->
    <div v-if="expandedNodeId === node.node_id && !isolated.has(node.node_id) && diag"
         class="candidate-table-wrap">
      <div class="candidate-table-title">{{ node.node_id }} 候选</div>
      <table class="candidate-table" v-if="expandedRoleAttr(node.node_id).length">
        <!-- ... 现有 thead / tbody / tr / td 原样搬 ... -->
      </table>
      <div v-else class="hint">无候选数据</div>
    </div>
  </div>
</template>
```
`expandedRoleAttr` 从 computed(单参数依赖)改成小函数 `(nodeId) => diag.roles[nodeId]?.attr ?? []`。

**b) 手动 toggle 兜底** — `manualExpandedNode` 保留 local ref,`toggleExpand(nodeId)` 只写 `manualExpandedNode`,`expandedNodeId` 派生优先跟随焦点/pending event,fallback 到 manual:
```ts
function toggleExpand(nodeId: string) {
  manualExpandedNode.value = manualExpandedNode.value === nodeId ? null : nodeId
}
```
派生优先级:`focusedEventId ?? pendingDisambigEventId`(即多归属 pending 时也追随)→ 展开该 event 所在 role;`focusedEventId` / `pendingDisambigEventId` 都空 → fallback 到 `manualExpandedNode`。这样 §3.4(e) 候选表 pending 行黄底信号在多归属时天然与 role 展开对齐(不然黄底在收起的 role 里看不到)。

**c) 常驻 vs 条件区**(问题 3-1):
- 角色漏斗 · 命中匹配列表:analysis 就绪常驻(不变)
- 匹配 trace:`v-if="showTrace && selectedMatch"` ← 唯一改动

**d) 命中匹配"选中"样式判据**(问题 3-3 反打 + 多归属如实反映):
```html
<div class="match-row"
     :class="{ 'match-row--selected': markedMatchIds.has(m.event_id) }">
```
单场景/多归属场景视觉自动统一;点某行触发 `selectMatchRow(mid) → focusMatch(mid)`,自动:
- `focusedMatchId=mid, focusedEventId=null` → `showTrace=true` → trace 展开
- `selectedMatchId` 派生驱动副图 bracket focus 高亮(现有 `makeRenderBracket` 逻辑)
- 副图 bracket 显示自动同步(用户"跳到 bracket 视图")

**e) 候选表行 marked 判据**(候选表 pending 行黄底):
```html
<tr class="attr-row"
    :class="{ 'attr-row--selected': markedEventIds.has(row.event_id) }">
```

**f) 遗留 `watch(selected)`**:原本用来同步 expandedNode + 滚到 trace。expandedNode 已 computed 派生 → 该分支删除。scrollIntoView 仍需要,改成 `watch([showTrace, focusedMatchId], (curr) => { if (showTrace.value && traceEl.value?.scrollIntoView) nextTick(...) })`。

### 3.5 level auto-follow(问题 4)

`focusEvent(eid)` 内部自动降 level 到 `eventTier(eid)`,当且仅当当前 level 更严:
```ts
function autoFollowLevel(eventId: string): void {
  const ev = effectiveAnalysis.value?.events.find(e => e.event_id === eventId)
  if (!ev) return
  const evTier = eventTier(ev)
  const RANK: Record<Level, number> = { matched: 2, qualified: 1, detected: 0 }
  if (RANK[evTier] < RANK[level.value]) setLevel(evTier)   // 静默切
}
```

**语义**: 单向"放松门控"—— level 只降不升。选中 matched event 时 level 不变(任何档都包含);选中 qualified event + 当前 level=matched → setLevel('qualified');选中 detected event + 当前 level=matched/qualified → setLevel('detected')。

**调用点**: 仅 `focusEvent(eid)`;`focusMatch(mid)` 不调用(bracket 在副图永远显,match 里 events 一般是 matched tier)。

## 4. 迁移与实施

### 4.1 5 task 拆分(单 plan / 单 session / subagent-driven / 不拆段)

| # | 目标 | 主要文件 | 单 task 结束时全绿门 |
|---|------|---------|-------------------|
| 1 | 状态字段收敛(`focusedMatchId` / `focusedEventId` / `manualExpandedNode`)+ 6 个派生 computed;`selected` 从 ref 变 computed 派生;`selectedMatch` / `selectedMatchId` / `selectedEventId` / `highlightedEventIds` 派生对齐 | `stores/view.ts` | vitest 单元测(派生一致);vue-tsc |
| 2 | `focusMatch` / `focusEvent` / `clearFocus` + `autoFollowLevel` 抽提;初始化 4 处改 `clearFocus`;废弃 `selectMatch` / `selectRole` / `selectEvent` / `clearSelection`;`setCandidateMatches` / `setPendingDisambig` / `clearCandidates` / `setLevel` 保留 | `stores/view.ts` | 归属 4 分支 + level auto-follow 单元测;vue-tsc |
| 3 | KlineChart.ts `handleChartClick` 3 分支替换成 `view.focusMatch / focusEvent / clearFocus` | `components/KlineChart.ts` | 现有 `chart.spec.ts` 复用 + 补 focus 联动断言 |
| 4 | DetailSidebar 6 处消费改造 + `expandedNodeId` 派生 + 候选表就地展开 template + trace `v-if="showTrace"` + `markedMatchIds` / `markedEventIds` 判据 | `components/DetailSidebar.vue` | 新增/扩展 sidebar 组件测(候选表就地展开 / marked 判据 / trace 条件);vue-tsc;build |
| 5 | Playwright e2e 端到端 5 场景 | `tests/*.spec.ts` | e2e 5 场景全绿 |

### 4.2 派生保底(为什么渲染层零改动)

- `selected` / `selectedMatch` / `selectedMatchId` / `selectedEventId` / `highlightedEventIds` 从 `ref` 变 `computed`,但导出符号名不变。KlineChart / DetailSidebar 用 `storeToRefs` 拿到的仍是响应式(computed 也 reactive)。
- KlineChart.vue 里 `input.selectedEventId` / `input.selectedMatchId` / `input.highlightedEventIds` 传入 chart.ts 的语义不变,`chart.ts::computeEventData` 及 `buildMainOption` / `buildSubOption` 一行不改。
- KlineChart.ts `handleChartClick` 签名不变,只把内部 3 分支改成 view action 调用。
- `.match-row--selected` / `.attr-row--selected` CSS class 不改;判据从 `selectedMatchId===m.event_id`/`selectedEventId===row.event_id` 换成 `markedMatchIds.has(...)`/`markedEventIds.has(...)`。

### 4.3 Task 1 前置 grep

grep `view.selected.value =` / `selected.value =` 全库确认所有 write 点,防止 ref→computed 转换时遗漏:
- `KlineChart.ts` 3 处(已计入 §3.3)
- `DetailSidebar.vue` 3 处(已计入 §3.3)
- `view.ts` 内 8-10 处(actions + 初始化);全部改成写 `focusedMatchId.value` / `focusedEventId.value`(Task 1)或迁到 Task 2 的 clearFocus 抽提

## 5. 非目标

- 不改后端 serialize / api / 拓扑序列化(protocolization 已在 2026-07-09 上一 spec 完成)
- 不改主/副图渲染算法(chart.ts 完全不动;marker tooltip / bracket renderer / candidate 虚线 / pending 闪烁全部沿用)
- 不改多归属歧义解决**流程本身**(candidate scope card + candidate bracket 虚线 + pending marker 闪烁 三件套沿用),只让 sidebar 命中匹配列表 + 候选表 pending 行**同步反映**该状态
- 不改 topology 面板 / brush 框选 / shift+click pair 查询 / candidate scope card / rejection chain / preview 相关模块
- 不改 level 门控 filter 算法(只加 autoFollowLevel 触发点)
- 不改 hoveredEventId / marker tooltip / bar tooltip
- 不加 level 变更 toast / 提示

## 6. 测试策略

### 6.1 单元(vitest)

**stores/view.ts 派生一致性**(Task 1):
- `selected` 派生:`focusedMatchId=null` → `null`;`focusedMatchId='m1'` → `{kind:'match', matchId:'m1'}`
- `selectedMatchId` / `selectedEventId` 等一一对齐
- `highlightedEventIds`:`focusedMatchId='m1'` + 无 event → 与 `matchedIdsOf([m1], events, edges)` 相等;`focusedMatchId=null` → `∅`
- `showTrace`:5 组场景(见 §3.2 表)覆盖
- `expandedNodeId`:`focusedEventId='e_bo_3'` → 该 event 所在 role;`focusedEventId=null, pendingDisambigEventId='e_bo_9'` → e_bo_9 所在 role(多归属场景 pending 兜底);`focusedEventId=null, pendingDisambigEventId=null, manualExpandedNode='bo'` → 'bo';全清 → null
- `markedMatchIds`:三态覆盖(bracket-focus 单值 / 多归属 candidates / 0 焦点空集)
- `markedEventIds`:两态覆盖(focus event 单值 / pending event 单值 / 双清)

**focusEvent 4 分支 + level auto-follow**(Task 2):
- ms.length===0 / 1 / >1 三分支状态变化
- level auto-follow:eventTier=detected + level=matched → setLevel('detected');eventTier=matched + level=matched → 无 op
- `focusMatch(mid)` / `clearFocus()` 状态变化
- `focusEvent` 内部 `triggerCandidateQuery` 被 stub 断言调用

### 6.2 组件(vitest + jsdom)

**KlineChart.ts::handleChartClick**(Task 3):
- 三分支 dispatch 到正确 action(空白 → clearFocus;brackets → focusMatch;marker → focusEvent)
- 参数正确传递(match_id / event_id)

**DetailSidebar.vue**(Task 4):
- 候选表就地展开:`focusedEventId='e_bo_3'` → 该 role funnel-row 下方渲染 candidate-table-wrap;多归属场景(focusedEventId=null, pendingDisambigEventId='e_bo_9')→ e_bo_9 所在 role 展开(pending 兜底)
- 命中匹配"选中"样式:bracket-focus 单行黄底;多归属场景多行同时黄底
- 匹配 trace:`showTrace=true` 时 v-if 生效;`showTrace=false` 时 v-else(不渲染)
- 候选表 pending 行黄底:多归属场景下 pending event 行有 `.attr-row--selected`
- 手动 toggle:无 event focus 时 `toggleExpand('bo')` → `manualExpandedNode='bo'` → 候选表展开;有 event focus 时点漏斗行不覆盖派生(不 disruptive)

### 6.3 端到端(Playwright)

**5 场景**(Task 5):

1. **副图 bracket click**:选中 match → 主图 group 黑框亮 + 副图 bracket 深实边 + 命中匹配单行黄底 + 匹配 trace 展开
2. **副图 event marker(唯一归属)click**:主图 group 黑框亮 + focus event 更深边 + 命中匹配单行黄底 + trace **不展**
3. **副图 event marker(多归属)click**:主图/副图无 group 黑框 + 副图 candidate brackets 虚线琥珀 + pending marker 闪烁 + 命中匹配多行同亮 + 候选表 pending 行黄底
4. **sidebar 命中匹配某行 click**:等价于 bracket click,反打副图 bracket + trace 展开
5. **sidebar 候选表 detected event click** + 当前 level=matched:自动降 level 到 'detected';event 在主/副图中可见并 focus 亮

## 7. 风险与缓解

| 风险 | 缓解 |
|------|-----|
| `selected` 从 ref 变 computed → 外部若 `selected.value = ...` 会挂 | Task 1 首步 grep 全库 write 点(`view.selected.value =` / `selected.value =`);已知 8+ 处全部纳入 §3.3 / §4.3 |
| `expandedNodeId` 手动 vs 派生互相盖写 | 规约明确:`focusedEventId` 优先(派生),`manualExpandedNode` fallback;不允许 UI 双向绑定到 expandedNodeId(只读) |
| `focusEvent` 内 `triggerCandidateQuery` 是 fire-and-forget async;错误吞掉 | 沿用现有失败沉默模式(与 triggerTimeQuery / triggerPairQuery 一致);不阻塞归属判定 |
| level auto-follow 静默切换,用户不易觉察 | Out of scope(§5 明确不加 toast);后置观察决定是否加一次性 flash 提示 |
| 多归属场景 sidebar 命中匹配多行黄底 与 bracket-focus 单行黄底样式相同 | 用户已明确"信息层如实反映所有归属",视觉相同即语义;disambig 完成时收敛到单行,视觉转换即反馈 |

## 8. 术语约定

- **focused**: focusedMatchId / focusedEventId 两条正交焦点轴,`null` 表示无焦点
- **marked**: markedMatchIds / markedEventIds 派生,统一 sidebar「命中匹配」列表与候选表的"选中/pending" 视觉判据;信息层反映所有归属/pending
- **highlighted**: `highlightedEventIds` 派生,仅在 bracket-focus 单亮场景生效(多归属时为空);驱动主/副图 group 黑框视觉层
- **showTrace**: 匹配 trace 展开的唯一判据 = `focusedMatchId!==null && focusedEventId===null`
- **expandedNodeId**: 漏斗当前展开的 role node;`focusedEventId` 派生优先,`manualExpandedNode` fallback
- **信息层 vs 视觉层**: sidebar 列表(信息层)可如实反映多归属;主/副图 group(视觉层)需 disambig 收敛
- **auto-follow level**: `focusEvent` 内单向降 level(只放松不收紧),`focusMatch` 不触发
