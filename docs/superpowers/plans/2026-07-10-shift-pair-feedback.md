# 入口 D shift+click 等待期反馈 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 path2_web_ui 入口 D(shift+click 两个 event 做 pair 查询)在第 1 击落下后到第 2 击前的等待期给出视觉反馈(banner + marker 高亮),Esc/空白 click 单一入口取消。

**Architecture:** 复用 `CandidateStatusBar` 位置(主副图 divider 与 sub-outer 之间的 16px 独立行)与样式(`#fbbf24` 金黄字/深底);新增独立组件 `ShiftPairBanner.vue` 与其排他;marker 高亮通过 `render/chart.ts::BandRenderInput` 增字段 `shiftSelectedEventIds`,在既有 4 种 marker series (points/intervals/price-points/satellites) 数据装配时叠加 `borderColor='#fbbf24' + borderWidth=2`;Esc / 空白 click 均已调 `view.clearFocus()`,补丁其内部一并清 `shiftSelectedEvents`。

**Tech Stack:** Vue 3(script setup + Composition API)· Pinia · ECharts · Vitest + @vue/test-utils · Playwright(MCP)· TypeScript · uv(Python 后端)。

## Global Constraints

- **Spec 源文件**:`docs/superpowers/specs/2026-07-10-shift-pair-feedback-design.md`(所有决策以此为准)
- **subagent 模型选择**(用户约定 `CLAUDE.md`):Implementer 一律 `sonnet`(禁 haiku);Reviewer(Spec / Code Quality / Final)一律 `opus`
- **Playwright 卫生**:每次用 playwright MCP 后任务收尾清空 `.playwright-mcp/*`(保留目录)
- **Playwright 截图默认**:`browser_resize(2560, 1440)` + `scale="device"`;整页 `fullPage=True`,元素细节 `target=<selector>` + `fullPage=False`
- **色规**:`#fbbf24`(banner 字色 + marker 描边)、`rgba(15,23,42,0.92)`(banner 背景),必须与既有 `.candidate-banner` 视觉字节等价
- **banner 文本**(逐字复制,不可改写):`入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消`
- **不新增依赖**:纯前端改动,不引入新 npm 包
- **YAGNI 排除**(不做):pair query loading 反馈 · banner × 关闭按钮 · 手势教程 tooltip · marker 高亮动画 · 公共 banner CSS 抽层
- **verification-before-completion**:每 Task 收尾必须真跑相关命令并观察输出通过后才 commit;不得凭"应该没问题"提交
- **验证 gate**(最终 Task 6):全套 `vitest` 绿(基线 513 tests 无回归)+ `vue-tsc --noEmit` 无错 + `vite build` 绿 + Playwright 5 场景截图证明视觉正确
- **CWD 约定**:除非 Task 里显式 `cd /home/yu/PycharmProjects/Trade_Strategy`,所有 Bash 命令的 CWD 都是 `/home/yu/PycharmProjects/Trade_Strategy/path2_web_ui`

---

## File Structure

**Create**:
- `path2_web_ui/src/components/ShiftPairBanner.vue` — 独立 banner 组件(v-if 排他 CandidateStatusBar)
- `path2_web_ui/tests/components/ShiftPairBanner.spec.ts` — banner 组件测(v-if 判据 + 文本 + 样式类)
- `path2_web_ui/e2e/shift-pair-feedback.spec.ts` — Playwright 5 场景 e2e

**Modify**:
- `path2_web_ui/src/stores/view.ts` — 追加 `shiftPairPending` / `shiftSelectedEventIds` 派生 + `clearShiftSelection` action + `clearFocus` 补丁清 shift
- `path2_web_ui/src/render/chart.ts` — `BandRenderInput` 加 `shiftSelectedEventIds` 字段 + `computeEventData` 4 series marker 装配时叠加 borderColor
- `path2_web_ui/src/components/KlineChart.vue` — template 挂 `<ShiftPairBanner />`(排在 CandidateStatusBar 之后) + storeToRefs 拿 `shiftSelectedEventIds` + 传给 BandRenderInput
- `path2_web_ui/tests/stores.focus-actions.spec.ts` — 补 clearFocus 清 shiftSelectedEvents 断言
- `path2_web_ui/tests/stores.focus-derivations.spec.ts` — 补 shiftPairPending / shiftSelectedEventIds 派生正确性
- `path2_web_ui/tests/components.kline-click.spec.ts` — 补 handleChartClick 空白 click 时 shift 被清

---

### Task 1: Store 层派生 + action + clearFocus 补丁

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts` — 在既有 `clearFocus` / return export 位置追加
- Modify: `path2_web_ui/tests/stores.focus-derivations.spec.ts` — 追加 shiftPairPending / shiftSelectedEventIds 测试
- Modify: `path2_web_ui/tests/stores.focus-actions.spec.ts` — 追加 clearFocus 清 shift 断言

**Interfaces produced**(下游 Task 消费):
```ts
// view store 追加
shiftPairPending:      ComputedRef<boolean>              // true ↔ shiftSelectedEvents.length === 1
shiftSelectedEventIds: ComputedRef<ReadonlySet<string>>  // Set(shiftSelectedEvents.map(e => e.event_id))
clearShiftSelection:   () => void                        // 仅清 shiftSelectedEvents = []
// 修改 clearFocus 语义:内部末尾调 clearShiftSelection()
```

**Interfaces consumed**: 无(纯 store 内部)

- [ ] **Step 1: 追加派生测试(RED)**

在 `path2_web_ui/tests/stores.focus-derivations.spec.ts` 末尾 `})` 前追加:

```typescript
  it('shiftPairPending: length ∈ {0,1,2} 三态派生', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftPairPending).toBe(false)           // length=0
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    expect(view.shiftPairPending).toBe(true)            // length=1
    view.setShiftSelectedEvents([
      { event_id: 'e_bo_1', class_id: 'BO', source: 'main' },
      { event_id: 'e_ta_1', class_id: 'TA', source: 'main' },
    ])
    expect(view.shiftPairPending).toBe(false)           // length=2
  })

  it('shiftSelectedEventIds: Set 派生正确', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    expect(view.shiftSelectedEventIds.size).toBe(0)
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    expect(view.shiftSelectedEventIds.has('e_bo_1')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(1)
    view.setShiftSelectedEvents([
      { event_id: 'e_bo_1', class_id: 'BO', source: 'main' },
      { event_id: 'e_ta_1', class_id: 'TA', source: 'main' },
    ])
    expect(view.shiftSelectedEventIds.has('e_bo_1')).toBe(true)
    expect(view.shiftSelectedEventIds.has('e_ta_1')).toBe(true)
    expect(view.shiftSelectedEventIds.size).toBe(2)
  })

  it('clearShiftSelection: 仅清 shiftSelectedEvents,不动 focus/candidate', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    view.focusedEventId = 'e_ta_1'
    view.clearShiftSelection()
    expect(view.shiftSelectedEvents.length).toBe(0)
    expect(view.focusedEventId).toBe('e_ta_1')          // focus 未被清
  })
```

在 `path2_web_ui/tests/stores.focus-actions.spec.ts` 末尾 `})` 前追加:

```typescript
  it('clearFocus 补丁: 一并清 shiftSelectedEvents', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ event_id: 'e_bo_1', class_id: 'BO', source: 'main' }])
    view.focusedEventId = 'e_ta_1'
    view.clearFocus()
    expect(view.focusedEventId).toBeNull()
    expect(view.shiftSelectedEvents.length).toBe(0)      // shift 也被清
  })
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/stores.focus-derivations.spec.ts tests/stores.focus-actions.spec.ts 2>&1 | tail -30
```

Expected: 4 个新用例 FAIL(`shiftPairPending is undefined` / `shiftSelectedEventIds is undefined` / `clearShiftSelection is not a function` / `shiftSelectedEvents.length` 不为 0)

- [ ] **Step 3: 实现 store 补丁**

编辑 `path2_web_ui/src/stores/view.ts`,做 3 处改动:

**改动 A**:在 `clearFocus` 函数(当前调 `clearCandidates()` 处)之前找到定义,追加 `clearShiftSelection()` 调用:

原:
```typescript
  function clearFocus(): void {
    focusedMatchId.value = null
    focusedEventId.value = null
    clearCandidates()
  }
```

改为:
```typescript
  function clearFocus(): void {
    focusedMatchId.value = null
    focusedEventId.value = null
    clearCandidates()
    clearShiftSelection()
  }
```

**改动 B**:在 `setShiftSelectedEvents` 定义**之后**(约 view.ts:391 后),追加新 action 与派生:

```typescript
  function clearShiftSelection(): void {
    shiftSelectedEvents.value = []
  }
  const shiftPairPending = computed<boolean>(() => shiftSelectedEvents.value.length === 1)
  const shiftSelectedEventIds = computed<ReadonlySet<string>>(
    () => new Set(shiftSelectedEvents.value.map(e => e.event_id))
  )
```

**改动 C**:在 store 的 `return { ... }` 里(view.ts 末尾)追加导出:

原(节选):
```typescript
    setShiftSelectedEvents, clearDetailCard, triggerTimeQuery, triggerPairQuery,
```

改为(在同行或紧邻行加入 4 个新导出):
```typescript
    setShiftSelectedEvents, clearShiftSelection, clearDetailCard, triggerTimeQuery, triggerPairQuery,
    shiftPairPending, shiftSelectedEventIds,
```

(若 return 对象按分组组织,`shiftPairPending`/`shiftSelectedEventIds` 加到派生 computed 组;`clearShiftSelection` 加到 action 组;保持既有分组风格。)

- [ ] **Step 4: 跑测试确认新增通过 + 全套无回归**

```bash
npx vitest run tests/stores.focus-derivations.spec.ts tests/stores.focus-actions.spec.ts 2>&1 | tail -20
```

Expected: 全绿(新增 4 个 + 原有全部)

```bash
npx vitest run 2>&1 | tail -8
```

Expected: 513 + 4 = 517 tests passed(或不同基线数,只要相对基线增加 4 个且 0 fail);检查最后一行 `Tests <N> passed (<N>)`。

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出(0 error)

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/stores/view.ts path2_web_ui/tests/stores.focus-derivations.spec.ts path2_web_ui/tests/stores.focus-actions.spec.ts
git commit -m "$(cat <<'EOF'
feat(view store): shift-pair 派生 + clearFocus 清 shift 补丁

- shiftPairPending / shiftSelectedEventIds 派生
- clearShiftSelection action(职责单一)
- clearFocus 补丁: 一并清 shiftSelectedEvents

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: ShiftPairBanner 组件 + 组件测

**Files:**
- Create: `path2_web_ui/src/components/ShiftPairBanner.vue`
- Create: `path2_web_ui/tests/components/ShiftPairBanner.spec.ts`

**Interfaces consumed**(from Task 1):
- `shiftPairPending: ComputedRef<boolean>`
- `candidateMatchIds: ComputedRef<ReadonlySet<string>>`(既有,view.ts:509 附近)

**Interfaces produced**:
- `ShiftPairBanner.vue` — 无 props / 无 emit,自读 store;v-if=`shiftPairPending && candidateMatchIds.size === 0`

- [ ] **Step 1: 写组件测试(RED)**

创建 `path2_web_ui/tests/components/ShiftPairBanner.spec.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ShiftPairBanner from '../../src/components/ShiftPairBanner.vue'
import { useViewStore } from '../../src/stores/view'

describe('ShiftPairBanner', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shiftPairPending=false 时不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([])
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })

  it('shiftPairPending=true + candidateMatchIds 空 → 渲染 + 文本精确匹配', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ event_id: 'e1', class_id: 'BO', source: 'main' }])
    const wrapper = mount(ShiftPairBanner)
    const el = wrapper.find('.shift-pair-banner')
    expect(el.exists()).toBe(true)
    expect(el.text()).toBe('入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消')
  })

  it('shiftPairPending=true + candidateMatchIds 非空 → 排他,不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ event_id: 'e1', class_id: 'BO', source: 'main' }])
    view.candidateMatchIds = new Set(['m1']) as any
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })

  it('length=2 → shiftPairPending=false → 不渲染', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([
      { event_id: 'e1', class_id: 'BO', source: 'main' },
      { event_id: 'e2', class_id: 'TA', source: 'main' },
    ])
    const wrapper = mount(ShiftPairBanner)
    expect(wrapper.find('.shift-pair-banner').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/components/ShiftPairBanner.spec.ts 2>&1 | tail -15
```

Expected: FAIL — Cannot resolve `../../src/components/ShiftPairBanner.vue`

- [ ] **Step 3: 实现 ShiftPairBanner.vue**

创建 `path2_web_ui/src/components/ShiftPairBanner.vue`:

```vue
<template>
  <div v-if="shiftPairPending && candidateMatchIds.size === 0" class="shift-pair-banner">
    入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useViewStore } from '../stores/view'

const view = useViewStore()
const { shiftPairPending, candidateMatchIds } = storeToRefs(view)
</script>

<style scoped>
/* 与 CandidateStatusBar `.candidate-banner` 视觉字节等价(spec 2026-07-10 §决策 1)。
   两条 banner v-if 排他,同一位置最多一条,总占 16px,不影响 subGeometry。 */
.shift-pair-banner {
  height: 16px;
  line-height: 16px;
  padding: 0 8px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(15, 23, 42, 0.92);
  border-radius: 3px;
  user-select: none;
  pointer-events: none;
  flex-shrink: 0;
}
</style>
```

- [ ] **Step 4: 跑测试确认通过 + 全套无回归**

```bash
npx vitest run tests/components/ShiftPairBanner.spec.ts 2>&1 | tail -10
```

Expected: 4 tests passed

```bash
npx vitest run 2>&1 | tail -6
```

Expected: 全绿,tests 数比 Task 1 基线再 +4

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/ShiftPairBanner.vue path2_web_ui/tests/components/ShiftPairBanner.spec.ts
git commit -m "$(cat <<'EOF'
feat(ShiftPairBanner): 入口 D 沉默期反馈组件

v-if 排他 CandidateStatusBar(shiftPairPending × 无 candidate);
文本与样式复用 candidate-banner 视觉(#fbbf24 金黄字/深底)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: KlineChart 挂 banner + 空白 click 清 shift 集成测

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue` — template 挂 ShiftPairBanner + script import
- Modify: `path2_web_ui/tests/components.kline-click.spec.ts` — 追加 handleChartClick 空白 click 时 shift 被清

**Interfaces consumed**(from Tasks 1-2):
- `<ShiftPairBanner />` 无 props / 自读 store
- `view.clearFocus()` 已补丁清 shift(Task 1)

**Interfaces produced**: KlineChart.vue template 布局新增一行 banner(v-if 排他 → 不占额外高度)

- [ ] **Step 1: 写集成测试(RED)**

在 `path2_web_ui/tests/components.kline-click.spec.ts` 中找到 handleChartClick 相关 describe 块(约 line 78 附近有 `view.focusEvent('eA')` 的场景),在同 describe 末尾追加:

```typescript
  it('handleChartClick 空白 click(seriesName 缺失)→ 清 shiftSelectedEvents', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ event_id: 'e1', class_id: 'BO', source: 'main' }])
    expect(view.shiftSelectedEvents.length).toBe(1)
    handleChartClick(null, [], view)
    expect(view.shiftSelectedEvents.length).toBe(0)
  })

  it('handleChartClick MARKER_SERIES click → 不清 shiftSelectedEvents(走 focusEvent, 保留 pair 累积器)', () => {
    const view = useViewStore()
    view.setShiftSelectedEvents([{ event_id: 'shift_e1', class_id: 'BO', source: 'main' }])
    // 触发 focusEvent 分支,event_id 不必存在真 events
    handleChartClick(
      { seriesName: 'points', data: { event_id: 'other_ev' } },
      [],
      view
    )
    // MARKER 分支 focusEvent 不清 shift(shift 累积器是独立通道)
    expect(view.shiftSelectedEvents.length).toBe(1)
  })
```

(第二个测试是负面校验:确认只有 clearFocus 路径清 shift,MARKER click 路径不清——这与 spec §C 描述一致,handleShiftClick 与 handleChartClick 是解耦的两条路径。)

- [ ] **Step 2: 跑测试确认第一个通过、第二个也通过**

```bash
npx vitest run tests/components.kline-click.spec.ts 2>&1 | tail -15
```

Expected: 全绿(Task 1 clearFocus 补丁已经让第一个测试直接通过;第二个测试也是既有行为,应通过)。若失败,不要跳过——第一个失败意味着 Task 1 未落地或调用路径有变;第二个失败意味着 MARKER click 意外清了 shift,回溯 focusEvent 实现。

- [ ] **Step 3: 修改 KlineChart.vue template + import**

编辑 `path2_web_ui/src/components/KlineChart.vue`:

**改动 A**:template line 5 附近(`<CandidateStatusBar :matches=... />` 之后)插入:

原:
```vue
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
    <div class="sub-outer" :style="{ height: effectiveSubH + 'px' }" ref="subOuterEl">
```

改为:
```vue
    <CandidateStatusBar :matches="effectiveAnalysis?.matches ?? []" />
    <ShiftPairBanner />
    <div class="sub-outer" :style="{ height: effectiveSubH + 'px' }" ref="subOuterEl">
```

**改动 B**:script import(约 line 54,`import CandidateStatusBar from './CandidateStatusBar.vue'` 附近)追加:

原:
```typescript
import CandidateStatusBar from './CandidateStatusBar.vue'
```

改为:
```typescript
import CandidateStatusBar from './CandidateStatusBar.vue'
import ShiftPairBanner from './ShiftPairBanner.vue'
```

(ShiftPairBanner 无 props,无需其他改动。)

- [ ] **Step 4: 跑测试 + tsc + build 三绿**

```bash
npx vitest run 2>&1 | tail -6
```

Expected: 全绿(相对 Task 2 基线再 +2)

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出

```bash
npm run build 2>&1 | tail -5
```

Expected: `built in Xs`,无 error

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue path2_web_ui/tests/components.kline-click.spec.ts
git commit -m "$(cat <<'EOF'
feat(KlineChart): 挂 ShiftPairBanner + 空白 click 清 shift 集成测

banner 排在 CandidateStatusBar 之后,v-if 排他不叠加。空白 click 
现在同时清 focus / candidate / shift(clearFocus 单一入口)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: chart.ts marker 高亮通道

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts` — `BandRenderInput` 加字段 + `computeEventData` 4 series 装配叠加 borderColor
- Modify: `path2_web_ui/tests/components.kline-click.spec.ts` 或新增 `tests/render/chart.marker-highlight.spec.ts` — 单元测(见下 Step 1)

**Interfaces consumed**(from Task 1):
- `shiftSelectedEventIds: ReadonlySet<string>`

**Interfaces produced**:
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>` — 可选,undefined 或空集时零副作用
- `computeEventData()` 返回的 `pointData` / `intervalData` / `pricePointData` / `satelliteData` 中,选中 event 的 `itemStyle` 追加 `borderColor: '#fbbf24'` + `borderWidth: 2`

- [ ] **Step 1: 写单元测试(RED)**

创建 `path2_web_ui/tests/render/chart.marker-highlight.spec.ts`(若 `tests/render/` 不存在则 mkdir);若既有 chart.ts 测试文件已存在同目录习惯,追加到同文件:

```typescript
import { describe, it, expect } from 'vitest'
import { computeEventData } from '../../src/render/chart'
import type { BandRenderInput } from '../../src/render/chart'
import type { EventDict, MatchDict, Bar } from '../../src/types'

// 最小 fixture — 只覆盖 marker 装配路径。
function makeBars(n = 10): Bar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    o: 100, h: 105, l: 95, c: 102, v: 1000,
  }))
}

function makeInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
  return {
    topology: { nodes: [{ node_id: 'bo', source_tag: 'BO' }], edges: [] } as any,
    tagList: ['BO'],
    level: 'detected',
    roleColors: { bo: { detected: '#111', qualified: '#222', matched: '#333' } } as any,
    eventTier: () => 'detected',
    roleOfEventByBand: () => 'bo',
    bandKeyOf: () => 'BO',
    roleVisible: {},
    tagToNodes: { BO: ['bo'] },
    selectedEventId: null,
    ...overrides,
  } as BandRenderInput
}

const eBo: EventDict = {
  event_id: 'e_bo_1', event_type: 'BO', class_id: 'BO',
  start_idx: 3, end_idx: 3,
} as any

describe('computeEventData · shiftSelectedEventIds marker 高亮通道', () => {
  it('shiftSelectedEventIds undefined → 各 series itemStyle 不带 borderColor', () => {
    const bundle = computeEventData(makeBars(), [eBo], [], makeInput())
    const all = [...bundle.pointData, ...bundle.intervalData, ...bundle.pricePointData, ...bundle.satelliteData]
    for (const d of all) {
      expect(d.itemStyle?.borderColor).toBeUndefined()
    }
  })

  it('shiftSelectedEventIds 空集 → 同上,零副作用', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set() }))
    const all = [...bundle.pointData, ...bundle.intervalData, ...bundle.pricePointData, ...bundle.satelliteData]
    for (const d of all) {
      expect(d.itemStyle?.borderColor).toBeUndefined()
    }
  })

  it('shiftSelectedEventIds 含 e_bo_1 → 该 event 的 marker 数据带 #fbbf24 描边', () => {
    const bundle = computeEventData(makeBars(), [eBo], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const hit = [
      ...bundle.pointData, ...bundle.intervalData,
      ...bundle.pricePointData, ...bundle.satelliteData,
    ].find(d => d.event_id === 'e_bo_1')
    expect(hit).toBeDefined()
    expect(hit!.itemStyle.borderColor).toBe('#fbbf24')
    expect(hit!.itemStyle.borderWidth).toBe(2)
  })

  it('shiftSelectedEventIds 含 e_bo_1,其他 event 不受影响', () => {
    const eOther: EventDict = { ...eBo, event_id: 'e_other', start_idx: 5, end_idx: 5 } as any
    const bundle = computeEventData(makeBars(), [eBo, eOther], [],
      makeInput({ shiftSelectedEventIds: new Set(['e_bo_1']) }))
    const other = [
      ...bundle.pointData, ...bundle.intervalData,
      ...bundle.pricePointData, ...bundle.satelliteData,
    ].find(d => d.event_id === 'e_other')
    if (other) {
      expect(other.itemStyle?.borderColor).toBeUndefined()
    }
    // e_other 可能因几何分流不落在任何 series(fixture 简单),测试只要求"落在的话不带描边"
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -15
```

Expected: 4 测试中至少 2 个 FAIL(`shiftSelectedEventIds` 字段不存在或 marker 未叠加描边);第 1、2 个"undefined/空集不带 borderColor"可能已通过(基线本来就不带),但第 3、4 个必失败。

- [ ] **Step 3: 实现 chart.ts 补丁**

编辑 `path2_web_ui/src/render/chart.ts`:

**改动 A**:`BandRenderInput` interface(约 line 70-84 定义处),在 `pendingDisambigEventId?: string | null` 附近追加:

原(节选):
```typescript
  // ── Task 5: highlight 三分支(group / focus / pendingDisambig) ───────────────
  highlightedEventIds?: ReadonlySet<string>
  pendingDisambigEventId?: string | null
```

改为:
```typescript
  // ── Task 5: highlight 三分支(group / focus / pendingDisambig) ───────────────
  highlightedEventIds?: ReadonlySet<string>
  pendingDisambigEventId?: string | null
  // ── spec 2026-07-10: 入口 D shift+click 已选中 marker 描边高亮 ────────────
  shiftSelectedEventIds?: ReadonlySet<string>
```

**改动 B**:`computeEventData` 顶部的解构(约 line 105-108),追加:

原:
```typescript
  const { topology, tagList, level, roleColors, eventTier, roleOfEventByBand, bandKeyOf,
          roleVisible, tagToNodes, selectedEventId, endRole,
          highlightedEventIds: _highlightedEventIds,
          pendingDisambigEventId: _pendingDisambigEventId } = input
  const highlightedEventIds = _highlightedEventIds ?? new Set<string>()
  const pendingDisambigEventId = _pendingDisambigEventId ?? null
```

改为:
```typescript
  const { topology, tagList, level, roleColors, eventTier, roleOfEventByBand, bandKeyOf,
          roleVisible, tagToNodes, selectedEventId, endRole,
          highlightedEventIds: _highlightedEventIds,
          pendingDisambigEventId: _pendingDisambigEventId,
          shiftSelectedEventIds: _shiftSelectedEventIds } = input
  const highlightedEventIds = _highlightedEventIds ?? new Set<string>()
  const pendingDisambigEventId = _pendingDisambigEventId ?? null
  const shiftSelectedEventIds = _shiftSelectedEventIds ?? new Set<string>()
  const shiftItemStyleFor = (event_id: string, base: Record<string, unknown>) =>
    shiftSelectedEventIds.has(event_id)
      ? { ...base, borderColor: '#fbbf24', borderWidth: 2 }
      : base
```

**改动 C**:替换 4 处 `itemStyle` 装配为 helper 调用。

**pricePointData**(line 142-156):

原:
```typescript
    return {
      value: [e.start_idx, y],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
      anchorY, text, hasPks,
    }
```

改为:
```typescript
    return {
      value: [e.start_idx, y],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
      anchorY, text, hasPks,
    }
```

**satelliteData**(line 158-175):

原:
```typescript
      satelliteData.push({
        value: [barIdx, price],
        event_id: e.event_id,
        label,
        itemStyle: { color: eColor(e) },
        anchorY: anchorBar ? anchorBar.h : price,
        pkId,
      })
```

改为:
```typescript
      satelliteData.push({
        value: [barIdx, price],
        event_id: e.event_id,
        label,
        itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
        anchorY: anchorBar ? anchorBar.h : price,
        pkId,
      })
```

**intervalData**(line 178-183):

原:
```typescript
  const intervalData = packedIntervals.map((e) => ({
    value: [e.start_idx, e.end_idx, e.lane, e.band, e.nBands],
    event_id: e.event_id,
    tier: eventTier(e),
    itemStyle: { color: eColor(e) },
  }))
```

改为:
```typescript
  const intervalData = packedIntervals.map((e) => ({
    value: [e.start_idx, e.end_idx, e.lane, e.band, e.nBands],
    event_id: e.event_id,
    tier: eventTier(e),
    itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
  }))
```

**pointData**(line 185-194):

原:
```typescript
  const pointData = points.map((e) => {
    const band = subTags.indexOf(bandKeyOf(e))
    const nBands = subTags.length
    return {
      value: [e.start_idx, e.start_idx, band < 0 ? 0 : band, nBands],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: { color: eColor(e) },
    }
  })
```

改为:
```typescript
  const pointData = points.map((e) => {
    const band = subTags.indexOf(bandKeyOf(e))
    const nBands = subTags.length
    return {
      value: [e.start_idx, e.start_idx, band < 0 ? 0 : band, nBands],
      event_id: e.event_id,
      tier: eventTier(e),
      itemStyle: shiftItemStyleFor(e.event_id, { color: eColor(e) }),
    }
  })
```

- [ ] **Step 4: 跑测试确认通过 + 全套无回归**

```bash
npx vitest run tests/render/chart.marker-highlight.spec.ts 2>&1 | tail -10
```

Expected: 4 tests passed

```bash
npx vitest run 2>&1 | tail -6
```

Expected: 全绿(相对 Task 3 基线再 +4)

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/render/chart.marker-highlight.spec.ts
git commit -m "$(cat <<'EOF'
feat(chart): marker 装配层加入 shiftSelectedEventIds 描边通道

BandRenderInput 增 shiftSelectedEventIds 字段;4 种 marker series
(points/intervals/price-points/satellites) 统一在装配时叠加
borderColor=#fbbf24 + borderWidth=2,与既有 tier 色/highlight 通道
叠加不覆盖。undefined/空集时零副作用(向后兼容)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: KlineChart 传 shiftSelectedEventIds 到 render pipeline

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue` — storeToRefs 取 `shiftSelectedEventIds`;所有 `computeEventData` / `buildMainOption` / `buildSubOption` 调用点的 BandRenderInput 增字段

**Interfaces consumed**(from Tasks 1 & 4):
- `view.shiftSelectedEventIds: ComputedRef<ReadonlySet<string>>`
- `BandRenderInput.shiftSelectedEventIds?: ReadonlySet<string>`

**Interfaces produced**: KlineChart 组件在 render 时把 store 的 `shiftSelectedEventIds` 透传到 render/chart.ts,实现 UI 反馈闭环。

- [ ] **Step 1: 找到 KlineChart.vue 里 BandRenderInput 装配处**

```bash
grep -n "highlightedEventIds\|pendingDisambigEventId\|BandRenderInput\|computeEventData\|buildMainOption\|buildSubOption" path2_web_ui/src/components/KlineChart.vue | head -30
```

Expected: 定位所有透传点(与既有 `highlightedEventIds` / `pendingDisambigEventId` 传参处并列)

- [ ] **Step 2: 修改 KlineChart.vue storeToRefs 补一个字段**

在 `KlineChart.vue` script 里找到既有 `storeToRefs(view)` 的解构行(前面 grep 显示 line 61-62 附近有 `candidateMatchIds, highlightedEventIds, pendingDisambigEventId` 一起解构),追加 `shiftSelectedEventIds`:

原(节选):
```typescript
const { ..., candidateMatchIds, highlightedEventIds, pendingDisambigEventId } = storeToRefs(view)
```

改为:
```typescript
const { ..., candidateMatchIds, highlightedEventIds, pendingDisambigEventId, shiftSelectedEventIds } = storeToRefs(view)
```

- [ ] **Step 3: 每个 BandRenderInput 装配点追加 shiftSelectedEventIds**

grep 出所有 `pendingDisambigEventId: pendingDisambigEventId.value` 传参处(应有 1-2 处,和 `highlightedEventIds` 一起):

```bash
grep -n "pendingDisambigEventId:" path2_web_ui/src/components/KlineChart.vue
```

每个匹配行的紧邻位置追加 `shiftSelectedEventIds: shiftSelectedEventIds.value,` — 例如(节选,line 336-338 附近):

原:
```typescript
    candidateMatchIds: candidateMatchIds.value,
    highlightedEventIds: highlightedEventIds.value,
    pendingDisambigEventId: pendingDisambigEventId.value,
```

改为:
```typescript
    candidateMatchIds: candidateMatchIds.value,
    highlightedEventIds: highlightedEventIds.value,
    pendingDisambigEventId: pendingDisambigEventId.value,
    shiftSelectedEventIds: shiftSelectedEventIds.value,
```

**同样处理 KlineChart.vue 里 line 631 附近**(watch 依赖数组或第二处装配点),把 `shiftSelectedEventIds` 加进相邻位置:

原(节选):
```typescript
       selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigEventId,
```

改为:
```typescript
       selectedMatchId, candidateMatchIds, highlightedEventIds, pendingDisambigEventId, shiftSelectedEventIds,
```

(所有出现 `pendingDisambigEventId` 的 refs 数组、watch 依赖、object 属性组都要同步扩展。若不确定某位置是否需要,以 grep 结果为准逐个核对,与 `pendingDisambigEventId` 做**每一处并列**扩展。)

- [ ] **Step 4: 跑测试 + tsc + build 三绿**

```bash
npx vitest run 2>&1 | tail -6
```

Expected: 全绿(相对 Task 4 基线不再增加测试,行为验证在 e2e/Task 6)

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出(若报"shiftSelectedEventIds is not exported" 之类,说明 Task 1 store 的 return 遗漏该字段——回 Task 1 补)

```bash
npm run build 2>&1 | tail -5
```

Expected: `built in Xs`,无 error

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/components/KlineChart.vue
git commit -m "$(cat <<'EOF'
feat(KlineChart): 传 shiftSelectedEventIds 到 render pipeline

storeToRefs 取字段 + 所有 BandRenderInput 装配点透传,与既有
pendingDisambigEventId 逐位并列扩展,不改 render/chart.ts 契约。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Playwright e2e 5 场景 + 最终验收

**Files:**
- Create: `path2_web_ui/e2e/shift-pair-feedback.spec.ts` — Playwright 5 场景 e2e(实际驱动使用 playwright MCP;此文件保留脚本形式作为可重复回归)

**Interfaces consumed**(from Tasks 1-5):
- 前 5 个 Task 全部落地(banner + marker 高亮 + 取消手势 + 传参接线)

**Interfaces produced**: 端到端验收 gate(全套 vitest 绿 + tsc + build + Playwright 5 场景)

项目 e2e 基础设施:`@playwright/test` + `playwright.config.ts`(webServer 自动起前端)+ `e2e/ports.ts` 提供 `baseURL` + `window.__e2e` 全局暴露 view store / chartMain / chartSub。参考现有 spec 骨架:`e2e/marker-click-focus-highlight.spec.ts`(setupChart helper 现成可复用)、`e2e/miss-detection-walkthrough.spec.ts`(入口 A 端到端参考)。**shift+click 用 `@playwright/test` 原生 modifiers**:`page.mouse.click(x, y, { modifiers: ['Shift'] })` 或 `locator.click({ modifiers: ['Shift'] })`,不用合成事件。

- [ ] **Step 1: 启动后端**(前端由 playwright.config.ts webServer 自动起,不用手动开)

在项目根 `/home/yu/PycharmProjects/Trade_Strategy` 起后端:

```bash
uv run python scripts/run_path2_web.py &
```

Expected: 打印 uvicorn 启动信息(端口以 `configs/path2_web.yaml` 为准)

- [ ] **Step 2: 写 e2e spec 文件**

创建 `path2_web_ui/e2e/shift-pair-feedback.spec.ts`,参照 `marker-click-focus-highlight.spec.ts` 的 setupChart 惯例:

```typescript
import { test, expect } from '@playwright/test'
import { baseURL } from './ports'

/**
 * 入口 D shift+click 沉默期反馈 e2e(spec 2026-07-10-shift-pair-feedback-design)。
 *
 * 5 场景:
 *   1. 第 1 击 → banner + marker 描边(shiftPairPending=true)
 *   2. Esc → 全清(shiftSelectedEvents=[])
 *   3. 空白 click → 全清
 *   4. 第 2 击 → banner 消失 + PairDetailCard 出(activeDetailCard='pair')
 *   5. 第 3 击 → 重置回 1/2(banner 再次出现)
 *
 * 数据源固定:与 marker-click-focus-highlight.spec.ts 同扫描时戳 + 股。
 * shift+click 用 @playwright/test 原生 mouse.click({modifiers:['Shift']}),不合成事件。
 * 场景 1/2/3/5 用真实鼠标 shift+click;场景 4 需要真实数据里恰好有 pair 边 — 若 fixture
 * 里对应 pattern 有 pair 边,则真实驱动第 2 击;若没有,退化为断言 shift 累积器
 * length=2 + triggerPairQuery 被调(用 __e2e 直接观测),视觉证明 banner 消失即可。
 */

const SCAN_TS = '2026-06-30 17:52:56'
const TICKER = 'BTMWW'
const BANNER_TEXT = '入口 D · 已选 1/2 — 再 shift+click 一个 event / Esc 取消'

async function setupChart(page: import('@playwright/test').Page) {
  await page.setViewportSize({ width: 2560, height: 1440 })
  await page.goto(baseURL + '/')
  await page.getByRole('button', { name: '打开历史' }).click()
  await page.locator(`tr:has-text("${SCAN_TS}")`).click()
  await page.getByRole('button', { name: 'Open' }).click()
  await page.waitForTimeout(2500)

  // 切 pattern 到有 pair 边的候选(bottom_burst 参考 marker-click spec);若 fixture pattern
  // 对 pair 场景 4 支持不足,implementer 可换其它已知含 pair 边的 pattern_id。
  await page.waitForFunction(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement | null
    return !!sel && Array.from(sel.options).some((o) => o.value === 'bottom_burst')
  })
  await page.evaluate(() => {
    const sel = document.querySelector('main select') as HTMLSelectElement
    sel.value = 'bottom_burst'
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await page.evaluate((sym) => (window as any).__e2e?.view?.selectSymbol(sym), TICKER)
  await page.waitForTimeout(1500)
  await page.waitForFunction(() => {
    const e = (window as any).__e2e
    return !!(e && e.chartMain && e.chartSub && e.chartMain() && e.chartSub())
  })
}

async function firstMarkerXY(page: import('@playwright/test').Page): Promise<{ x: number; y: number; event_id: string }> {
  // 从副图 points series 取第一个 marker 的屏幕坐标(参 marker-click-focus-highlight.spec.ts 惯例)
  const info = await page.evaluate(() => {
    const sub = (window as any).__e2e.chartSub()
    const pts = sub.getOption().series.find((s: any) => s.name === 'points')
    const d = pts?.data?.[0]
    if (!d) return null
    const px = sub.convertToPixel({ seriesId: pts.id ?? undefined, seriesIndex: sub.getOption().series.indexOf(pts) }, d.value)
    const canvas = sub.getDom().querySelector('canvas')!
    const rect = canvas.getBoundingClientRect()
    return {
      x: rect.left + (Array.isArray(px) ? px[0] : 0),
      y: rect.top  + (Array.isArray(px) ? px[1] : 0),
      event_id: d.event_id as string,
    }
  })
  if (!info) throw new Error('no marker on subchart')
  return info
}

test.describe('入口 D shift+click 沉默期反馈', () => {
  test('场景 1: 第 1 击 → banner + marker 描边', async ({ page }) => {
    await setupChart(page)
    const m = await firstMarkerXY(page)
    await page.mouse.click(m.x, m.y, { modifiers: ['Shift'] })
    await expect(page.locator('.shift-pair-banner')).toHaveText(BANNER_TEXT)
    const bordered = await page.evaluate((eid) => {
      const sub = (window as any).__e2e.chartSub()
      const pts = sub.getOption().series.find((s: any) => s.name === 'points')
      const d = pts?.data?.find((x: any) => x.event_id === eid)
      return d?.itemStyle?.borderColor
    }, m.event_id)
    expect(bordered).toBe('#fbbf24')
  })

  test('场景 2: Esc 取消 → banner 消失 + shift 累积器空', async ({ page }) => {
    await setupChart(page)
    const m = await firstMarkerXY(page)
    await page.mouse.click(m.x, m.y, { modifiers: ['Shift'] })
    await expect(page.locator('.shift-pair-banner')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(0)
  })

  test('场景 3: 空白 click 取消 → banner 消失 + shift 累积器空', async ({ page }) => {
    await setupChart(page)
    const m = await firstMarkerXY(page)
    await page.mouse.click(m.x, m.y, { modifiers: ['Shift'] })
    await expect(page.locator('.shift-pair-banner')).toBeVisible()
    // 空白 click:在主图左上角(远离任何 marker)
    const mainCanvas = await page.locator('.main-chart canvas').first().boundingBox()
    if (!mainCanvas) throw new Error('main canvas not found')
    await page.mouse.click(mainCanvas.x + 20, mainCanvas.y + 20)
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(0)
  })

  test('场景 4: 第 2 击 → banner 消失(第 2 击后累积器 length=2 或 pair query 触发)', async ({ page }) => {
    await setupChart(page)
    const m1 = await firstMarkerXY(page)
    await page.mouse.click(m1.x, m1.y, { modifiers: ['Shift'] })
    await expect(page.locator('.shift-pair-banner')).toBeVisible()

    // 第 2 击:取 pointData 里第 2 个 marker 屏幕坐标
    const m2 = await page.evaluate(() => {
      const sub = (window as any).__e2e.chartSub()
      const pts = sub.getOption().series.find((s: any) => s.name === 'points')
      const d = pts?.data?.[1]
      if (!d) return null
      const px = sub.convertToPixel({ seriesIndex: sub.getOption().series.indexOf(pts) }, d.value)
      const canvas = sub.getDom().querySelector('canvas')!
      const rect = canvas.getBoundingClientRect()
      return { x: rect.left + px[0], y: rect.top + px[1] }
    })
    if (!m2) test.skip(true, 'fixture 副图 points 不足 2 个 marker,场景 4 无法真实驱动;实施时确认 fixture 或换 marker series')
    await page.mouse.click(m2!.x, m2!.y, { modifiers: ['Shift'] })

    // banner 应消失(shiftPairPending=false when length=2)
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(2)
  })

  test('场景 5: 第 3 击重置 → banner 再次出现', async ({ page }) => {
    await setupChart(page)
    const m1 = await firstMarkerXY(page)
    await page.mouse.click(m1.x, m1.y, { modifiers: ['Shift'] })
    // 场景 5 依赖场景 4 的 length=2 前置态;直接注入 shift 累积器 length=2,再触发第 3 击
    await page.evaluate(() => {
      const view = (window as any).__e2e.view
      view.setShiftSelectedEvents([
        { event_id: 'fake1', class_id: 'BO', source: 'main' },
        { event_id: 'fake2', class_id: 'BO', source: 'main' },
      ])
    })
    await expect(page.locator('.shift-pair-banner')).not.toBeVisible()
    // 第 3 击:再点 m1 位置
    await page.mouse.click(m1.x, m1.y, { modifiers: ['Shift'] })
    // handleShiftClick 第 3 击语义: 累积器重置为 [新元素] → length=1 → banner 再现
    await expect(page.locator('.shift-pair-banner')).toBeVisible()
    const len = await page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents.length)
    expect(len).toBe(1)
  })
})
```

**implementer 注意点**:
- `SCAN_TS` / `TICKER` / pattern 值取自 `marker-click-focus-highlight.spec.ts`,若这些常量在最近迁移中已变,以最新 e2e 常量为准
- 场景 4 若 fixture 副图 points 不足 2 个 marker,`test.skip(true, ...)` 跳过 + 记录到 commit;不硬造场景
- pair query 后端返回的 `PairDetailCard` 内容不必在 e2e 里断言(那是另一 spec 已覆盖的入口 D 主线);本 spec 只断 banner 消失 + shift 累积器 length=2
- 场景 5 用 `view.setShiftSelectedEvents` 直接注入 length=2 前置态,是为绕开场景 4 fixture 依赖;若场景 4 已通过,场景 5 也可以在同一 test 里链式跑

- [ ] **Step 3: 跑 e2e 确认全绿**

```bash
npx playwright test e2e/shift-pair-feedback.spec.ts 2>&1 | tail -30
```

Expected: 5 tests passed(或 4 passed + 1 skipped——场景 4 因 fixture);全 fail 需回溯前置 Task 而非硬压。

**若失败**:
- **banner 未出现** → 检查 Task 1 store `shiftPairPending` export;检查 Task 3 挂载
- **marker 描边缺失** → 检查 Task 4 chart.ts 4 处 map + Task 5 传参
- **Esc 未清 shift** → 检查 Task 1 clearFocus 补丁是否落
- **mouse.click 未触发 handleShiftClick** → 检查 KlineChart.vue::handleMaybeShiftClick 是否 shift+MARKER 分支消费成功(可能被 hover/zoom 拦截);用 `page.evaluate(() => (window as any).__e2e.view.shiftSelectedEvents)` 观测累积器

- [ ] **Step 4: MCP 视觉截图存证**(可选补充,不代替 Step 3 e2e 自动化):

若愿意用 playwright MCP 补一组视觉截图作为设计验收,按用户 CLAUDE.md 约定:
- `browser_resize(2560, 1440)`,`scale="device"`
- 整体布局用 `fullPage=True`
- banner + marker 细节 `target=".shift-pair-banner"` / `target=".main-chart"` + `fullPage=False`

任务收尾清空 `.playwright-mcp/*`(保留目录),见下 Step 5。

- [ ] **Step 5: 最终 gate — 三绿 + 清理 + Commit**

**verification-before-completion**:必须真跑,不得凭空断言。

```bash
npx vitest run 2>&1 | tail -6
```

Expected: 全绿,tests 数比初始基线(513)增加约 +10(Task 1~4 累计);记录最终 tests 数到 commit body。

```bash
npx vue-tsc --noEmit 2>&1 | tail -5
```

Expected: 无输出。

```bash
npm run build 2>&1 | tail -5
```

Expected: `built in Xs`,无 error。

**清理 .playwright-mcp/**(用户约定卫生):

```bash
cd /home/yu/PycharmProjects/Trade_Strategy && rm -rf .playwright-mcp/*
```

**关闭前后端**:

```bash
# 用 Ctrl+C 或 kill 关掉之前后台起的 vite / uvicorn 进程
```

**Commit e2e 文件**:

```bash
git add path2_web_ui/e2e/shift-pair-feedback.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): 入口 D shift+click 沉默期反馈 5 场景

第 1 击 banner+描边 / Esc / 空白 / 第 2 击 pair query / 第 3 击 reset。
@playwright/test 原生 mouse.click({modifiers:['Shift']}) 真实驱动。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 完成判据

累计验收:
- 全套 vitest 绿(基线 513 + 新增 ≥10)
- vue-tsc --noEmit 无 error
- npm run build 无 error
- Playwright 5 场景全通过(banner 出/隐、marker 描边、Esc/空白 click 清、第 2 击 pair query、第 3 击 reset)
- 6 commit(Tasks 1-6 各 1)

**未纳入**(spec §YAGNI 已锁,本 plan 不实施):
- pair query loading 反馈 · banner × 关闭按钮 · 手势教程 · marker 动画 · 公共 banner CSS 抽层

---

## Handoff

**执行方式**:subagent-driven(默认,用户 CLAUDE.md 明示)
**Implementer 模型**:sonnet(每 Task)
**Reviewer 模型**:opus(spec review / code quality / final review)
**验证约束**:每 Task 收尾必须真跑 `vitest` / `vue-tsc` / `npm run build` 相关命令并观察输出;Task 6 必须用 `npx playwright test` 真跑 5 场景 e2e(webServer 自动起前端,后端外部 `uv run python scripts/run_path2_web.py`),不得凭空断言"应该通过"
