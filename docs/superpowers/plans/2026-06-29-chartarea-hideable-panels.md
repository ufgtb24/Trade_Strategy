# ChartArea 三处可隐藏面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ChartArea 的拓扑面板 / 调试侧栏 / dataZoom slider 三处独立可隐藏,默认全隐,状态 localStorage 持久化,只见 K 线主图+副图。

**Architecture:** 新增 pinia `panels` store 持有三个 bool + 自动 persist;ChartArea 用 `v-if` + 动态 grid-template-columns 响应;KlineChart 把 `panels.showSlider` 通过 `BandRenderInput.sliderShow` 串到 ECharts `dataZoom[1].show`(保留 inside zoom)。所有改动**仅前端**,后端零改。

**Tech Stack:** Vue 3 + pinia + ECharts 5,vitest + @vue/test-utils,Playwright(端到端实测)。

**Spec:** [docs/superpowers/specs/2026-06-29-chartarea-hideable-panels-design.md](../specs/2026-06-29-chartarea-hideable-panels-design.md)

## Global Constraints

- 仅改 `path2_web_ui/`,**后端零改**
- 三个面板默认全隐(localStorage 无 key 或解析失败 → 全 false)
- localStorage key 固定:`'path2_web_ui.panels.v1'`
- 三 chip 复用现有 `.level-btn` CSS 类,**不新增样式概念**
- 隐 slider 时**必须保留 inside zoom**(鼠标滚轮 + 拖选区域仍可用);仅 slider UI 隐
- 现有 258 测试零回归;每 task 结束三 gate 绿:`npx vitest run` + `npx vue-tsc -b` + `npx vite build`
- 全程不动 `prompts/command.md` 和其他与本任务无关的已 dirty 文件(`SidebarScanPanel.vue` 等)
- Playwright 卫生:本计划末尾的端到端实测如用了 `.playwright-mcp/`,完成后清空(`rm -rf /home/yu/PycharmProjects/Trade_Strategy/.playwright-mcp/*`,保目录本身)
- Commit 消息中文 imperative;每 task 一 commit;末尾按本项目约定追加 `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- 不使用 `--no-verify` / `--no-gpg-sign`

---

## File Structure

新建:
- `path2_web_ui/src/stores/panels.ts` — 三 bool ref + localStorage 复原/持久化 + toggle action
- `path2_web_ui/tests/stores.panels.spec.ts` — panels store 单元测试
- `path2_web_ui/tests/components/ChartArea.panels.spec.ts` — ChartArea 组件测试(三 chip + v-if)
- `path2_web_ui/tests/render.chart.slider.spec.ts` — `buildKlineOption` 的 sliderShow 单测

修改:
- `path2_web_ui/src/components/ChartArea.vue` — 加三 chip + v-if + 动态 grid + 修脆弱 `:nth-child(2)` CSS
- `path2_web_ui/src/components/KlineChart.vue` — render() 传 sliderShow + watch 加 showSlider
- `path2_web_ui/src/render/chart.ts` — `BandRenderInput.sliderShow?: boolean`,dataZoom[1] 加 `show`
- `path2_web_ui/tests/components/ChartArea.spec.ts` — 更新被新 chip 数量打破的 "renders 3 level options" 测试

---

## Task 1: panels store

**Files:**
- Create: `path2_web_ui/src/stores/panels.ts`
- Create: `path2_web_ui/tests/stores.panels.spec.ts`

**Interfaces:**
- Consumes: (无,孤立 store)
- Produces:
  - `usePanelsStore()` → store with refs `showTopology: Ref<boolean>`, `showSidebar: Ref<boolean>`, `showSlider: Ref<boolean>` and action `toggle(key: 'topology' | 'sidebar' | 'slider'): void`
  - localStorage key: `'path2_web_ui.panels.v1'`,value 是 JSON `{topology: bool, sidebar: bool, slider: bool}`
  - 首次访问 / key 缺失 / JSON 解析失败 → 全 false
  - 任一 ref 变化触发 persist(`localStorage.setItem` 抛出时静默)

- [ ] **Step 1: Write failing tests**

`path2_web_ui/tests/stores.panels.spec.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'
import { usePanelsStore } from '../src/stores/panels'

const KEY = 'path2_web_ui.panels.v1'

describe('panels store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults all three to false when localStorage is empty', () => {
    const p = usePanelsStore()
    expect(p.showTopology).toBe(false)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(false)
  })

  it('toggle(key) flips that ref and persists to localStorage', async () => {
    const p = usePanelsStore()
    p.toggle('topology')
    await nextTick()
    expect(p.showTopology).toBe(true)
    const raw = localStorage.getItem(KEY)
    expect(raw).not.toBeNull()
    const obj = JSON.parse(raw!)
    expect(obj).toEqual({ topology: true, sidebar: false, slider: false })
  })

  it('restores all three bools from localStorage on init', () => {
    localStorage.setItem(KEY, JSON.stringify({ topology: true, sidebar: false, slider: true }))
    const p = usePanelsStore()
    expect(p.showTopology).toBe(true)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(true)
  })

  it('falls back to all false on corrupt JSON in localStorage', () => {
    localStorage.setItem(KEY, '{not-json')
    const p = usePanelsStore()
    expect(p.showTopology).toBe(false)
    expect(p.showSidebar).toBe(false)
    expect(p.showSlider).toBe(false)
  })

  it('toggle does not throw when localStorage.setItem throws (quota/private-mode)', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded')
    })
    const p = usePanelsStore()
    expect(() => p.toggle('sidebar')).not.toThrow()
    await nextTick()
    expect(p.showSidebar).toBe(true)
    expect(spy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/stores.panels.spec.ts`
Expected: FAIL — `Cannot find module '../src/stores/panels'`

- [ ] **Step 3: Implement panels store**

`path2_web_ui/src/stores/panels.ts`:

```ts
// 三个 UI 面板(Topology/Sidebar/Slider)的显隐 store,localStorage 持久化。
// 默认全隐(首次访问 / key 缺失 / JSON 解析失败均回落 false)。
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'path2_web_ui.panels.v1'

interface PanelsState {
  topology: boolean
  sidebar:  boolean
  slider:   boolean
}

function loadState(): PanelsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { topology: false, sidebar: false, slider: false }
    const obj = JSON.parse(raw)
    return {
      topology: !!obj.topology,
      sidebar:  !!obj.sidebar,
      slider:   !!obj.slider,
    }
  } catch {
    return { topology: false, sidebar: false, slider: false }
  }
}

export type PanelKey = 'topology' | 'sidebar' | 'slider'

export const usePanelsStore = defineStore('panels', () => {
  const init = loadState()
  const showTopology = ref(init.topology)
  const showSidebar  = ref(init.sidebar)
  const showSlider   = ref(init.slider)

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        topology: showTopology.value,
        sidebar:  showSidebar.value,
        slider:   showSlider.value,
      }))
    } catch { /* 配额满/隐私模式:静默吞,不阻塞 UI */ }
  }
  watch([showTopology, showSidebar, showSlider], persist)

  function toggle(key: PanelKey) {
    if (key === 'topology') showTopology.value = !showTopology.value
    else if (key === 'sidebar') showSidebar.value = !showSidebar.value
    else showSlider.value = !showSlider.value
  }

  return { showTopology, showSidebar, showSlider, toggle }
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/stores.panels.spec.ts`
Expected: PASS(5 tests)

- [ ] **Step 5: Full regression — vitest + tsc + build all green**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```
Expected:
- vitest:**263 passed**(258 旧 + 5 新)
- vue-tsc:0 errors
- vite build:成功

- [ ] **Step 6: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/stores/panels.ts path2_web_ui/tests/stores.panels.spec.ts
git commit -m "$(cat <<'EOF'
feat(web-ui): 新增 panels store 管理三 UI 面板显隐

含 localStorage('path2_web_ui.panels.v1') 持久化、首次/损坏回落全隐、
配额/隐私模式静默吞;为 ChartArea 三 chip toggle 提供状态源。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: chart.ts `sliderShow` 支持

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`(`BandRenderInput` 接口 + `buildKlineOption` 内 dataZoom)
- Create: `path2_web_ui/tests/render.chart.slider.spec.ts`

**Interfaces:**
- Consumes: (Task 1 的 panels store 在本 task 不直接消费,Task 3 才接入)
- Produces:
  - `BandRenderInput.sliderShow?: boolean`(可选,默认 true,保现有调用零回归——`tests/labels.spec.ts` 不传也工作)
  - `buildKlineOption(...)` 输出的 `option.dataZoom[1].show === input.sliderShow ?? true`,`dataZoom[0]`(inside)永远无 show 字段(默认 enabled)

- [ ] **Step 1: Write failing tests**

`path2_web_ui/tests/render.chart.slider.spec.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { buildKlineOption } from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import type { Bar } from '../src/types'

function baseInput(): BandRenderInput {
  return {
    topology: { nodes: [], edges: [] } as any,
    isolatedNodeIds: new Set(),
    tagList: [],
    level: 'matched',
    roleColors: {},
    eventTier: () => 'matched',
    roleOfEventByBand: () => null,
    bandKeyOf: () => '',
  }
}

const BARS: Bar[] = [
  { date: '2024-01-01', o: 1, h: 2, l: 1, c: 2, v: 100, rv: 0.1 },
  { date: '2024-01-02', o: 2, h: 3, l: 2, c: 3, v: 200, rv: 0.2 },
]

describe('buildKlineOption — dataZoom slider show toggle', () => {
  it('omits show field by default (slider visible, backward-compatible)', () => {
    const opt: any = buildKlineOption(BARS, [], [], baseInput())
    const zooms = opt.dataZoom
    expect(zooms).toHaveLength(2)
    expect(zooms[0].type).toBe('inside')
    expect(zooms[0].show).toBeUndefined()
    expect(zooms[1].type).toBe('slider')
    // 默认 sliderShow=true → slider.show=true
    expect(zooms[1].show).toBe(true)
  })

  it('sliderShow=false hides slider, keeps inside zoom enabled', () => {
    const opt: any = buildKlineOption(BARS, [], [], { ...baseInput(), sliderShow: false })
    const zooms = opt.dataZoom
    expect(zooms[0].type).toBe('inside')
    expect(zooms[0].show).toBeUndefined()
    expect(zooms[1].type).toBe('slider')
    expect(zooms[1].show).toBe(false)
  })

  it('sliderShow=true explicit → slider visible', () => {
    const opt: any = buildKlineOption(BARS, [], [], { ...baseInput(), sliderShow: true })
    expect(opt.dataZoom[1].show).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/render.chart.slider.spec.ts`
Expected: FAIL — `dataZoom[1].show` 当前未定义(因接口未加 sliderShow,buildKlineOption 也未写 show 字段)

- [ ] **Step 3: Modify `BandRenderInput` 加 sliderShow**

`path2_web_ui/src/render/chart.ts`,定位 `export interface BandRenderInput { ... }`(约 line 22-41),在 `matchLabel?` 之后追加:

```ts
  // ── 缓冲窗/label 扩展(均可选,旧调用零改动) ──────────────────────────────────
  strictWindow?: { startIdx: number; endIdx: number } | null   // 严格窗边界(bar 索引);缺省不画
  matchLabel?: (matchId: string) => string | null              // match 归属带 tooltip 行;null 不显示
  // ── dataZoom slider 显隐(可选,默认 true=显示,与历史行为一致) ──────────────
  sliderShow?: boolean
}
```

- [ ] **Step 4: Modify `buildKlineOption` 把 sliderShow 串到 dataZoom**

`path2_web_ui/src/render/chart.ts`,定位 `const { topology, tagList, ... matchLabel } = input`(约 line 47-49),把 `sliderShow` 解构进来。然后定位 dataZoom 数组(约 line 275-278):

修改前:
```ts
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd },
    ],
```

修改后:
```ts
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: zoomEnd },
      { type: 'slider', xAxisIndex: [0, 1], top: '92%', start: zoomStart, end: zoomEnd,
        show: sliderShow ?? true },
    ],
```

且 input 解构处:
```ts
  const { topology, tagList, level, roleColors, eventTier, roleOfEventByBand, bandKeyOf,
          roleVisible, tagToNodes,
          selectedEventId, tooltipResolver, strictWindow, matchLabel, sliderShow } = input
```

- [ ] **Step 5: Run new tests to verify they pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/render.chart.slider.spec.ts`
Expected: PASS(3 tests)

- [ ] **Step 6: Full regression**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```
Expected:
- vitest:**266 passed**(263 + 3)
- vue-tsc:0 errors;**关键**:`tests/labels.spec.ts` 等不传 sliderShow 的调用方仍编译通过
- vite build:成功

- [ ] **Step 7: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/render.chart.slider.spec.ts
git commit -m "$(cat <<'EOF'
feat(web-ui): chart.ts buildKlineOption 支持 sliderShow 控制 dataZoom slider

BandRenderInput 新增可选 sliderShow(默认 true 保旧调用零回归);仅切 slider
UI 显隐,inside zoom 永远 enabled。为 Task 3 接入 panels.showSlider 做准备。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: ChartArea 三 chip + v-if + 动态 grid + 修脆弱 CSS

**Files:**
- Modify: `path2_web_ui/src/components/ChartArea.vue`(template + script + style)
- Modify: `path2_web_ui/tests/components/ChartArea.spec.ts`(更新 "renders 3 level options" 被新 chip 数量打破的断言)
- Create: `path2_web_ui/tests/components/ChartArea.panels.spec.ts`

**Interfaces:**
- Consumes: Task 1 的 `usePanelsStore`(refs `showTopology` / `showSidebar` / `showSlider`,action `toggle(key)`)
- Produces:
  - DOM 中三个 chip 按钮的 `data-testid` = `panel-toggle-topology` / `panel-toggle-sidebar` / `panel-toggle-slider`
  - `.chart-area` 在 sidebar 隐藏时附加 class `no-sidebar`
  - row1 Topology 用 `<div class="topology-row">` 包装(消除 `:nth-child(2)` 脆弱选择器)

- [ ] **Step 1: Write failing component test**

`path2_web_ui/tests/components/ChartArea.panels.spec.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ChartArea from '../../src/components/ChartArea.vue'
import { usePanelsStore } from '../../src/stores/panels'

function mountIt() {
  const wrapper = mount(ChartArea, {
    global: {
      stubs: {
        KlineChart: true,
        DetailSidebar: true,
        TopologyControl: true,
      },
    },
  })
  const panels = usePanelsStore()
  return { wrapper, panels }
}

describe('ChartArea — panel toggle chips', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('renders three panel-toggle chips in level-bar (testids)', () => {
    const { wrapper } = mountIt()
    expect(wrapper.find('[data-testid="panel-toggle-topology"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-toggle-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="panel-toggle-slider"]').exists()).toBe(true)
  })

  it('by default: TopologyControl + DetailSidebar are not rendered; .no-sidebar class on .chart-area', () => {
    const { wrapper } = mountIt()
    expect(wrapper.findComponent({ name: 'TopologyControl' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'DetailSidebar' }).exists()).toBe(false)
    expect(wrapper.find('.chart-area').classes()).toContain('no-sidebar')
  })

  it('clicking topology chip mounts TopologyControl and adds active class', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-topology"]')
    await chip.trigger('click')
    expect(panels.showTopology).toBe(true)
    expect(chip.classes()).toContain('active')
    expect(wrapper.findComponent({ name: 'TopologyControl' }).exists()).toBe(true)
  })

  it('clicking sidebar chip mounts DetailSidebar and removes .no-sidebar', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-sidebar"]')
    await chip.trigger('click')
    expect(panels.showSidebar).toBe(true)
    expect(chip.classes()).toContain('active')
    expect(wrapper.findComponent({ name: 'DetailSidebar' }).exists()).toBe(true)
    expect(wrapper.find('.chart-area').classes()).not.toContain('no-sidebar')
  })

  it('clicking slider chip toggles panels.showSlider (no DOM mount, render-side concern)', async () => {
    const { wrapper, panels } = mountIt()
    const chip = wrapper.get('[data-testid="panel-toggle-slider"]')
    await chip.trigger('click')
    expect(panels.showSlider).toBe(true)
    expect(chip.classes()).toContain('active')
  })
})
```

- [ ] **Step 2: Run new test — verify failure**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/components/ChartArea.panels.spec.ts`
Expected: FAIL — 找不到 `data-testid="panel-toggle-topology"`

- [ ] **Step 3: Update ChartArea.vue**

完整覆写 `path2_web_ui/src/components/ChartArea.vue`:

```vue
<template>
  <div class="chart-area" :class="{ 'no-sidebar': !showSidebar }">
    <!-- row0: 全局 level 控件 + 三 panel toggle chip -->
    <div class="level-bar" data-testid="level-control">
      <button
        v-for="opt in LEVEL_OPTIONS"
        :key="opt.value"
        :class="['level-btn', { active: level === opt.value }]"
        :title="opt.title"
        @click="view.setLevel(opt.value)"
      >{{ opt.label }}</button>
      <select :value="view.activePatternId ?? ''"
              data-role="active-pattern"
              @change="onActivePatternChange"
              class="active-pattern-select"
              v-if="view.patternIds.length > 0">
        <option v-for="pid in view.patternIds" :key="pid" :value="pid">
          {{ pid }}
        </option>
      </select>
      <span class="spacer" />
      <button
        v-for="t in PANEL_TOGGLES"
        :key="t.key"
        :class="['level-btn', 'panel-toggle', { active: panels[t.refKey] }]"
        :data-testid="`panel-toggle-${t.key}`"
        :title="t.title"
        @click="panels.toggle(t.key)"
      >{{ t.label }}</button>
    </div>
    <!-- row1: 拓扑控制(可隐藏,wrapper .topology-row 让 CSS 精准跨列) -->
    <div v-if="showTopology" class="topology-row">
      <TopologyControl @hover-role="onHoverRole" />
    </div>
    <!-- row2: K线 + 诊断侧栏(侧栏可隐藏) -->
    <KlineChart />
    <DetailSidebar v-if="showSidebar" />
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import TopologyControl from './TopologyControl.vue'
import KlineChart from './KlineChart.vue'
import DetailSidebar from './DetailSidebar.vue'
import { useViewStore } from '../stores/view'
import { usePanelsStore, type PanelKey } from '../stores/panels'
import type { Level } from '../types'

const view = useViewStore()
const { level } = storeToRefs(view)
const panels = usePanelsStore()
const { showTopology, showSidebar } = storeToRefs(panels)

const LEVEL_OPTIONS: { value: Level; label: string; title: string }[] = [
  { value: 'matched', label: 'Matched',  title: '仅显示命中 match 的事件' },
  { value: 'qualified',  label: 'Qualified',   title: '显示命中 match 或参与诊断 trace 的事件' },
  { value: 'detected', label: 'Detected', title: '显示所有被 detector 检出的事件' },
]

const PANEL_TOGGLES: { key: PanelKey; refKey: 'showTopology' | 'showSidebar' | 'showSlider'; label: string; title: string }[] = [
  { key: 'topology', refKey: 'showTopology', label: 'Topology', title: '显示/隐藏拓扑面板' },
  { key: 'sidebar',  refKey: 'showSidebar',  label: 'Sidebar',  title: '显示/隐藏右侧诊断侧栏' },
  { key: 'slider',   refKey: 'showSlider',   label: 'Slider',   title: '显示/隐藏 K 线下方缩放滑块' },
]

function onHoverRole(_nodeId: string | null) { /* 高亮交互留 KlineChart 内部增强 */ }

function onActivePatternChange(e: Event) {
  view.setActivePattern((e.target as HTMLSelectElement).value)
}
</script>

<style scoped>
/* grid 列数由 .no-sidebar 切换;row1 用 .topology-row 精准跨列(避开脆弱 nth-child) */
.chart-area {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto auto 560px;
  gap: 0;
}
.chart-area.no-sidebar { grid-template-columns: 1fr; }
.level-bar, .chart-area > .topology-row { grid-column: 1 / -1; }

.level-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a4a;
}
.spacer { flex: 1; }

.level-btn {
  padding: 3px 14px;
  border: 1px solid #3a3a5a;
  border-radius: 4px;
  background: transparent;
  color: #aaa;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.level-btn:hover { background: #2a2a4a; color: #ddd; }
.level-btn.active { background: #4a4aaa; color: #fff; border-color: #6a6acc; }

.active-pattern-select { margin-left: 8px; font-size: 12px; padding: 2px 4px; }
</style>
```

**关键**:
- `<div class="topology-row">` 包装 TopologyControl,让 CSS `.chart-area > .topology-row { grid-column: 1 / -1 }` 精准跨列;v-if 移除时,wrapper 也消失,不会有错位风险
- 原 `grid-column: 1 / 3` 改为 `1 / -1`,在 1 列或 2 列模板下都正确跨满
- `<span class="spacer" />` 用 `flex: 1` 把后续 chip 推到 level-bar 最右端

- [ ] **Step 4: Run new panels test — verify pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui && npx vitest run tests/components/ChartArea.panels.spec.ts`
Expected: PASS(5 tests)

- [ ] **Step 5: 更新被打破的旧 ChartArea.spec.ts**

`path2_web_ui/tests/components/ChartArea.spec.ts` 中,第一个 it `renders 3 level options` 现在会失败(level-control div 下有 6 个 button:3 level + 3 panel toggle)。需要把 "查所有 button" 改成 "只查 level 按钮"。

定位:line 24-33 附近的 `it('renders 3 level options (matched / qualified / detected)', () => { ... })`。

修改:把 `const buttons = ctrl.findAll('button')` 改成只过滤非 panel-toggle 的按钮。

修改前:
```ts
  it('renders 3 level options (matched / qualified / detected)', () => {
    const { wrapper } = mountIt()
    const ctrl = wrapper.get('[data-testid="level-control"]')
    const buttons = ctrl.findAll('button')
    expect(buttons.length).toBe(3)
    const labels = buttons.map((b) => b.text())
    expect(labels).toContain('Matched')
    expect(labels).toContain('Qualified')
    expect(labels).toContain('Detected')
  })
```

修改后:
```ts
  it('renders 3 level options (matched / qualified / detected)', () => {
    const { wrapper } = mountIt()
    const ctrl = wrapper.get('[data-testid="level-control"]')
    // 过滤掉 panel-toggle chip(新增 Topology/Sidebar/Slider),只看 level 按钮
    const levelButtons = ctrl.findAll('button').filter(
      (b) => !(b.attributes('data-testid') ?? '').startsWith('panel-toggle')
    )
    expect(levelButtons.length).toBe(3)
    const labels = levelButtons.map((b) => b.text())
    expect(labels).toContain('Matched')
    expect(labels).toContain('Qualified')
    expect(labels).toContain('Detected')
  })
```

**注意**:第三个 it `clicking "Detected" updates store.level and moves active class`(line 42-52)用 `wrapper.findAll('.level-btn')` 后通过 `b.text() === 'Detected'` 过滤——这条**仍能工作**(text 过滤不依赖数量)。第二个 it `defaults to "matched" active`(line 35-40)断言 `.level-btn.active` 长度=1——panels 默认全 false 没有 active panel chip,Matched 仍是唯一 active,**仍能工作**。不要改这两个。

- [ ] **Step 6: Full regression**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```
Expected:
- vitest:**271 passed**(266 + 5 新);旧 ChartArea.spec.ts 三条全绿(更新过的那条 + 未动的两条)
- vue-tsc:0 errors
- vite build:成功

- [ ] **Step 7: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/ChartArea.vue \
        path2_web_ui/tests/components/ChartArea.spec.ts \
        path2_web_ui/tests/components/ChartArea.panels.spec.ts
git commit -m "$(cat <<'EOF'
feat(web-ui): ChartArea 三 panel toggle chip + v-if 可隐藏 + 动态 grid

level-bar 右侧加 Topology/Sidebar/Slider 三 chip(复用 .level-btn 样式);
v-if 移除时 grid row1 塌缩;sidebar 隐时列模板由 2 列切 1 列(.no-sidebar 类)。
修复原 .chart-area > :nth-child(2) 在 Topology 隐藏后错位选中 KlineChart 的
脆弱 CSS,改用 .topology-row 包装类精准跨列。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: KlineChart 接 panels.showSlider

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`(import + render() 传 sliderShow + watch 加 showSlider)

**Interfaces:**
- Consumes: Task 1 的 `usePanelsStore` 的 `showSlider` ref;Task 2 的 `BandRenderInput.sliderShow`
- Produces: 切 `panels.showSlider` 时 KlineChart 重 render,ECharts dataZoom slider 即显/隐;inside zoom 永远保留

- [ ] **Step 1: Modify KlineChart.vue**

`path2_web_ui/src/components/KlineChart.vue`。

定位 import 区(约 line 1-14),在最后追加:
```ts
import { usePanelsStore } from '../stores/panels'
```

定位 `useViewStore()` 解构(line 16-17),在其后追加:
```ts
const panels = usePanelsStore()
const { showSlider } = storeToRefs(panels)
```
(确认 `storeToRefs` 已被 import;若没有,在原 `import { storeToRefs } from 'pinia'` 一行已经在了——保留原状)

定位 `function render()`(line 51-74)内 `const opt = buildKlineOption(...)` 调用(line 54-72),在 input 对象末尾追加 `sliderShow`。

修改前(input 对象内部最后两行):
```ts
      strictWindow: strictWindowIdx(),
      matchLabel,
    },
  )
```

修改后:
```ts
      strictWindow: strictWindowIdx(),
      matchLabel,
      sliderShow: showSlider.value,
    },
  )
```

定位 deep watch(约 line 177):
```ts
watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag], render, { deep: true })
```

修改为:
```ts
watch([effectiveAnalysis, roleVisible, level, roleColors, selectedEventId, diag, showSlider], render, { deep: true })
```

- [ ] **Step 2: Full regression**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/path2_web_ui
npx vitest run && npx vue-tsc -b && npx vite build
```
Expected:
- vitest:**271 passed**(零回归;本 task 无新测,Task 5 端到端实测做行为验证)
- vue-tsc:0 errors
- vite build:成功

- [ ] **Step 3: Commit**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
git add path2_web_ui/src/components/KlineChart.vue
git commit -m "$(cat <<'EOF'
feat(web-ui): KlineChart 接 panels.showSlider 控制 dataZoom slider 显隐

render() 将 panels.showSlider 经 BandRenderInput.sliderShow 传到
buildKlineOption;watch 数组加 showSlider 触发 re-render;inside zoom
(鼠标滚轮+拖选)永远保留,仅切 slider UI。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 端到端 playwright 实测(默认 / 全开 / 持久化)

**Files:**
- (无新建/修改源码;仅运行 + 截图 + 清场)

**Interfaces:** N/A(验收 task)

**目的:** 在真浏览器里走完三档场景,确认本次改动行为正确。**这是验收门,不通过则前面 task 有未发现的实施缺陷。**

- [ ] **Step 1: 启动后端 + 前端 dev server**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run python scripts/run_path2_web.py \
  > /tmp/web.log 2>&1 &
echo $! > /tmp/web.pid
sleep 8
tail -5 /tmp/web.log
```
Expected:日志看到 `VITE ... ready` + `Uvicorn running on http://127.0.0.1:8000`。

- [ ] **Step 2: Playwright 加载页面 + 打开最近一次扫描(应该是 4825 hits)**

通过 Playwright MCP(`mcp__plugin_playwright_playwright__browser_navigate` → `http://localhost:5173/`),然后:
1. snapshot 找到 "打开历史…" 按钮,click
2. 在 Scan Results dialog 中双击最新一行(应该是 4825 / 6048)
3. 等待扫描数据加载

- [ ] **Step 3: 验证默认状态(三档全隐)**

通过 `browser_evaluate` 跑:
```js
() => {
  const topo = document.querySelector('.topology-row')  // wrapper 不存在=Topology 隐
  const side = document.querySelector('[class*="DetailSidebar"]') ||
               Array.from(document.querySelectorAll('aside, main *')).find(
                 el => el.textContent?.includes('DetailSidebar'))  // 简单存在检查
  const noSidebar = document.querySelector('.chart-area')?.classList.contains('no-sidebar')
  // ECharts slider 隐藏 → 不应有 type=slider 的可见 .ec-zoom 或类似;最稳是检查 chart instance
  // 仅核默认 panels store 状态
  const panelsRaw = localStorage.getItem('path2_web_ui.panels.v1')
  return {
    topology_dom_present: !!topo,
    no_sidebar_class: !!noSidebar,
    panels_storage: panelsRaw,
  }
}
```
Expected:
- `topology_dom_present === false`
- `no_sidebar_class === true`
- `panels_storage === null`(未点过任何 toggle)

- [ ] **Step 4: 验证三档全开 + localStorage 写入**

通过 snapshot 找到三个 chip(`[data-testid="panel-toggle-topology"]` 等)依次 click。然后跑 evaluate:
```js
() => {
  const topo = document.querySelector('.topology-row')
  const noSidebar = document.querySelector('.chart-area')?.classList.contains('no-sidebar')
  const panelsRaw = localStorage.getItem('path2_web_ui.panels.v1')
  return {
    topology_dom_present: !!topo,
    no_sidebar_class: !!noSidebar,
    panels_storage: panelsRaw && JSON.parse(panelsRaw),
  }
}
```
Expected:
- `topology_dom_present === true`
- `no_sidebar_class === false`
- `panels_storage === { topology: true, sidebar: true, slider: true }`

- [ ] **Step 5: 截图记录,确认无视觉破绽**

`browser_take_screenshot` 抓 viewport 全图。检查 K 线主图占满、Topology 在上、DetailSidebar 在右、底部 slider 出现。

- [ ] **Step 6: 验证持久化(刷新页面)**

`browser_navigate('http://localhost:5173/')` 重新加载;再次跑 Step 4 的 evaluate。Expected:三档仍开,localStorage 三 true。

- [ ] **Step 7: 验证默认场景(清 localStorage 后刷新)**

```js
() => { localStorage.removeItem('path2_web_ui.panels.v1'); }
```
然后 `browser_navigate` 刷新;跑 Step 3 evaluate。Expected:回到默认全隐。

- [ ] **Step 8: 清场**

```bash
kill -TERM $(cat /tmp/web.pid) 2>/dev/null
sleep 2
pkill -f "vite --port 5173" 2>/dev/null
pkill -f "path2_web.main" 2>/dev/null
sleep 1
rm -rf /home/yu/PycharmProjects/Trade_Strategy/.playwright-mcp/*
rm -f /tmp/web.log /tmp/web.pid
```

- [ ] **Step 9:(无 commit,本 task 不产代码;若步骤暴露问题则回前面 task 修)**

如果 Step 3-7 任一失败,定位是哪个 task 的实施 bug,回那个 task 修(改完仍重跑三 gate + 本 task)。**全过则收工**。

---

## Self-Review 结果(plan 作者自检)

- **Spec coverage**:spec §3(UI)→ Task 3;§4(store)→ Task 1;§5.1(ChartArea)→ Task 3;§5.2(KlineChart + chart.ts)→ Task 2 + Task 4;§8.1 store 单测 → Task 1;§8.2 组件测 → Task 3;§8.2 KlineChart slider 测 → Task 2(放 render 层更纯);§8.3 e2e → Task 5。全覆盖,无缺口。
- **Placeholder scan**:全部 step 有具体代码/命令/预期产出,无 TBD/TODO/"similar to"。
- **Type consistency**:`PanelKey = 'topology' | 'sidebar' | 'slider'` 在 Task 1 定义并 export,Task 3 import 使用;`sliderShow?: boolean` 在 Task 2 定义,Task 4 通过 `showSlider.value` 传值;`showTopology/showSidebar/showSlider` 三 ref 名称全 plan 一致。
- **细节修正**:Task 3 提示了**不要改**第二、三条已有测试(它们对新 chip 不敏感),只改第一条;Task 5 包含清场命令,符合 CLAUDE.md 的 Playwright 卫生约定。
