# path2_web_ui 股票代码搜索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `path2_web_ui` 股票列表加前缀式代码搜索 + 全局字符转发(打开 UI 后直接键入代码即定位股),同时把 KlineChart 单字母 `B` 快捷键让位到 `Shift+B`。

**Architecture:** 派生链尾追一段 `startsWith` filter 串进 `filteredSortedRows`;`SidebarResultList` 顶部加搜索输入框 + 数量提示 + 清空;capture 阶段全局 `keydown` 监听把字母/数字/`.`/`-` 转发到搜索框并聚焦;`KlineChart` 的 brush toggle 键改成 `Shift+B` 让出字符流。

**Tech Stack:** Vue 3 (Composition + `<script setup>`),Pinia,TypeScript,vitest + jsdom,`@vue/test-utils`,Playwright(e2e)。

## Global Constraints

- 后端零改动;前端改动限定在 `path2_web_ui/src/stores/view.ts` + `path2_web_ui/src/components/SidebarResultList.vue` + `path2_web_ui/src/components/KlineChart.vue`。
- 全部前端命令在目录 `path2_web_ui/` 下运行(以下命令中隐含 `cd path2_web_ui`;每条 Bash 命令请前置 `cd path2_web_ui &&` 或事先切目录)。
- 单元测试用 `npx vitest run <path>`;端到端用 `npx playwright test <path>`。
- TDD:每个 task 先写失败测试、验红,再最小实现让其转绿,再 commit。
- 字符转发范围恰为正则 `/^[a-zA-Z0-9.\-]$/`;修饰键(ctrl/meta/alt)、`isComposing`、非法字符键均放行。
- store 派生保持既有响应式,不改 `sortedRows` / `unionRows` 语义;只在 `filteredSortedRows` 尾追一段 AND filter。
- 参考锁定源:`docs/superpowers/specs/2026-07-14-symbol-search-design.md`

---

## File Structure

- **Modify** `path2_web_ui/src/stores/view.ts`
  - 加 state `symbolQuery: Ref<string>`
  - 加 action `setSymbolQuery(q)` / `clearSymbolQuery()`
  - `filteredSortedRows` 尾追前缀 filter
  - `loadScanFile` / `clearScanFile` / `setActivePattern` 三处调 `clearSymbolQuery()`
  - export 表补 `symbolQuery`、`setSymbolQuery`、`clearSymbolQuery`

- **Modify** `path2_web_ui/src/components/SidebarResultList.vue`
  - 顶部加 `<div class="search-bar">`(在 `.preview-bar` 之上):`<input>`、数量提示、清空 `×`
  - `onArrowKey` 去掉输入框守卫
  - `onDocKey` 扩容:Esc 在搜索框有值时清 query、已空则 blur(优先级高于关字段菜单)
  - 加 `onGlobalCharKey`(capture 阶段挂 `document.addEventListener('keydown', ..., true)`),`onBeforeUnmount` 反注册

- **Modify** `path2_web_ui/src/components/KlineChart.vue`
  - `onKeyDown` 的 `(e.key === 'b' || e.key === 'B')` 分支换成 `(e.key === 'B' && e.shiftKey)`

- **Add** `path2_web_ui/tests/view.symbol-search.spec.ts`(view store 单元测试)
- **Extend** `path2_web_ui/tests/components.sidebar-result-list.spec.ts`(组件测试新增 describe 块)
- **Extend** `path2_web_ui/tests/components.kline-band-zoom-handlers.spec.ts` 或另建 `tests/components.kline-brush-key.spec.ts`(此处按后者建新文件,避免动无关文件)
- **Add** `path2_web_ui/e2e/symbol-search.spec.ts`(Playwright smoke)

---

## Task 1: view store — symbolQuery + 派生 filter + 三处 reset

**Files:**
- Modify: `path2_web_ui/src/stores/view.ts`
- Test: `path2_web_ui/tests/view.symbol-search.spec.ts`(新建)

**Interfaces:**
- Consumes: 现有 `useViewStore` 的 `loadScanFile(file)`、`setActivePattern(pid)`、`clearScanFile()`、`sortedRows`、`filteredSortedRows`、`visiblePatterns`
- Produces:
  - state `symbolQuery: string`(初始 `''`)
  - action `setSymbolQuery(q: string): void`
  - action `clearSymbolQuery(): void`
  - `filteredSortedRows` 语义:AND 追加 `q === '' || row.symbol.toLowerCase().startsWith(q)`(q 已 trim + lowercase)

---

- [ ] **Step 1: 写失败测试(view store)**

创建 `path2_web_ui/tests/view.symbol-search.spec.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

function makeFile(symbols: string[]): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only', 'bbb'],
    per_pattern: {
      bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_role: 'bo' },
      bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_role: 'tb' },
    },
    scan: {
      scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
      workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
      dataset_dir: '/d', params: 'default',
      win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
    },
    results: symbols.map(s => ({
      symbol: s,
      per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
      },
    })),
  }
}

describe('view store · symbolQuery', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('empty query returns all rows (equivalence with legacy behavior)', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA', 'MSFT']))
    expect(v.symbolQuery).toBe('')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL', 'BAA', 'MSFT'])
  })

  it('prefix match is case-insensitive', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA', 'MSFT']))
    v.setSymbolQuery('aa')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL'])
  })

  it('prefix (not substring): "aa" does not match "BAA"', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA']))
    v.setSymbolQuery('aa')
    expect(v.filteredSortedRows.some(r => r.symbol === 'BAA')).toBe(false)
  })

  it('query is trimmed', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL']))
    v.setSymbolQuery('  aa  ')
    expect(v.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL'])
  })

  it('clearSymbolQuery restores full list', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL', 'BAA']))
    v.setSymbolQuery('aa')
    v.clearSymbolQuery()
    expect(v.symbolQuery).toBe('')
    expect(v.filteredSortedRows.length).toBe(3)
  })

  it('AND with visiblePatterns filter: pattern hidden AND query miss → hidden', () => {
    const v = useViewStore()
    // 构造:AAA 在 bo_only 命中 / bbb 不命中;BBB 在 bbb 命中 / bo_only 不命中
    const f: MultiScanResultFile = {
      pattern_ids: ['bo_only', 'bbb'],
      per_pattern: {
        bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_role: 'bo' },
        bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} } as any, end_role: 'tb' },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: 2, hits: 2, errors: 0, dataset_dir: '/d', params: 'default',
        win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20,
      },
      results: [
        { symbol: 'AAA', per_pattern: {
          bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
          bbb:     { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
        }},
        { symbol: 'BBB', per_pattern: {
          bo_only: { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
          bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.2 },
        }},
      ],
    }
    v.loadScanFile(f)
    v.setPatternsAllOff()
    v.togglePattern('bo_only')  // 只 visible bo_only
    // 无 query:visiblePatterns filter 保留 AAA(bo_only 命中),丢 BBB
    expect(v.filteredSortedRows.map(r => r.symbol)).toEqual(['AAA'])
    v.setSymbolQuery('bb')  // AND:AAA 前缀不匹配 → 全丢
    expect(v.filteredSortedRows).toEqual([])
  })

  it('loadScanFile resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA']))
    v.setSymbolQuery('xx')
    expect(v.symbolQuery).toBe('xx')
    v.loadScanFile(makeFile(['CC', 'CCC']))
    expect(v.symbolQuery).toBe('')
  })

  it('clearScanFile resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA']))
    v.setSymbolQuery('xx')
    v.clearScanFile()
    expect(v.symbolQuery).toBe('')
  })

  it('setActivePattern resets symbolQuery', () => {
    const v = useViewStore()
    v.loadScanFile(makeFile(['AA', 'AAPL']))
    v.setSymbolQuery('aa')
    v.setActivePattern('bbb')
    expect(v.symbolQuery).toBe('')
  })
})
```

- [ ] **Step 2: 验证测试失败**

```bash
cd path2_web_ui && npx vitest run tests/view.symbol-search.spec.ts
```

Expected: 全部 FAIL,`symbolQuery` / `setSymbolQuery` / `clearSymbolQuery` 未定义。

- [ ] **Step 3: 实现 store 变更**

编辑 `path2_web_ui/src/stores/view.ts`。

3.1 在 state 声明区(靠近 `sortByPid` / `sortDesc` 附近,即 `defineStore` 内的 `ref` 声明段)加:

```typescript
const symbolQuery = ref<string>('')
```

3.2 找到既有 `filteredSortedRows` 定义(约 205–209 行):

```typescript
const filteredSortedRows = computed<UnionRow[]>(() =>
  sortedRows.value.filter(row =>
    row.cells.some(c => visiblePatterns.value.has(c.pid) && c.matched)
  )
)
```

替换为:

```typescript
const filteredSortedRows = computed<UnionRow[]>(() => {
  const q = symbolQuery.value.trim().toLowerCase()
  return sortedRows.value.filter(row => {
    if (!row.cells.some(c => visiblePatterns.value.has(c.pid) && c.matched)) return false
    if (q === '') return true
    return row.symbol.toLowerCase().startsWith(q)
  })
})
```

3.3 在 actions 段(靠近 `setSort` 之类的简单 setter 附近)加两个 action:

```typescript
function setSymbolQuery(q: string) { symbolQuery.value = q }
function clearSymbolQuery() { symbolQuery.value = '' }
```

3.4 在 `loadScanFile` 函数体尾部(在 `initVisiblePatterns(f.pattern_ids)` 那行之前)插一句:

```typescript
symbolQuery.value = ''
```

3.5 在 `clearScanFile` 函数体尾部(在 `clearDetailCard()` 之前)插一句:

```typescript
symbolQuery.value = ''
```

3.6 在 `setActivePattern` 函数体尾部插一句(找到 `setActivePattern` 定义;若函数体简短,则在末尾追加):

```typescript
symbolQuery.value = ''
```

3.7 在 return 表(约 570–591 行)加导出:

```typescript
symbolQuery,
setSymbolQuery, clearSymbolQuery,
```

放置建议:把 `symbolQuery` 附加到与 state 相关的行(如 `visiblePatterns, visibleFields,` 之后),`setSymbolQuery, clearSymbolQuery` 附加到 `setPatternsAllOn, setPatternsAllOff, invertPatterns,` 之后。

- [ ] **Step 4: 验证测试全绿**

```bash
cd path2_web_ui && npx vitest run tests/view.symbol-search.spec.ts
```

Expected: 全部 PASS(8 项)。

- [ ] **Step 5: 跑全套 store 回归**

```bash
cd path2_web_ui && npx vitest run tests/view.multi.spec.ts tests/stores.spec.ts tests/stores.focus-actions.spec.ts tests/stores.focus-derivations.spec.ts tests/stores.panels.spec.ts tests/stores.preview.spec.ts tests/stores.disambig.spec.ts tests/unionRows.spec.ts
```

Expected: 全部 PASS,无回归。

- [ ] **Step 6: Commit**

```bash
cd path2_web_ui && git add src/stores/view.ts tests/view.symbol-search.spec.ts && git commit -m "feat(view store): add symbolQuery state + prefix filter串 filteredSortedRows

- state: symbolQuery(初始 '')
- actions: setSymbolQuery / clearSymbolQuery
- filteredSortedRows 尾追 AND filter:trim().toLowerCase().startsWith
- reset hooks: loadScanFile / clearScanFile / setActivePattern 各清一次

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: SidebarResultList — search-bar UI + input + Esc + arrow guard removal

**Files:**
- Modify: `path2_web_ui/src/components/SidebarResultList.vue`
- Test: `path2_web_ui/tests/components.sidebar-result-list.spec.ts`(追加 describe 块)

**Interfaces:**
- Consumes: Task 1 的 `symbolQuery`、`setSymbolQuery`、`clearSymbolQuery`
- Produces:
  - template 顶部新增 `.search-bar`(scanFile 非空才显示):`<input ref="searchInputEl" data-testid="symbol-search" />` + count `<span data-testid="symbol-search-count">` + `<button data-testid="symbol-search-clear">×</button>`
  - `onArrowKey` 去掉输入框守卫(保留 IME 守卫)
  - `onDocKey` 优先处理搜索框内的 Esc

---

- [ ] **Step 1: 写失败测试**

在 `path2_web_ui/tests/components.sidebar-result-list.spec.ts` **末尾**追加 describe 块(不动既有的 describe):

```typescript
import { nextTick } from 'vue'

describe('SidebarResultList · symbol search UI', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function makeMultiFile(symbols: string[]): MultiScanResultFile {
    return {
      pattern_ids: ['bo_only'],
      per_pattern: {
        bo_only: {
          pattern_spec: { pattern_id: 'bo_only', roles: [], edges: [], event_styles: {} } as any,
          end_role: 'tb',
        },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
        dataset_dir: '/d', params: 'default',
        win_start: '2024-01-01', win_end: '2024-06-30', label_horizon: 5,
      },
      results: symbols.map(s => ({
        symbol: s,
        per_pattern: {
          bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        },
      })),
    }
  }

  it('search bar hidden when scanFile is null', async () => {
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    expect(w.find('[data-testid="symbol-search"]').exists()).toBe(false)
    w.unmount()
  })

  it('search bar visible after loadScanFile', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    expect(w.find('[data-testid="symbol-search"]').exists()).toBe(true)
    w.unmount()
  })

  it('typing in input updates view.symbolQuery + list narrows', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    input.value = 'aa'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    expect(view.symbolQuery).toBe('aa')
    expect(view.filteredSortedRows.map(r => r.symbol).sort()).toEqual(['AA', 'AAPL'])
  })

  it('count reads filteredSortedRows.length / sortedRows.length', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    view.setSymbolQuery('aa')
    await flushPromises()
    const count = w.get('[data-testid="symbol-search-count"]').text()
    expect(count).toBe('2 / 3')
    w.unmount()
  })

  it('clear button appears only when query non-empty, click clears query', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    expect(w.find('[data-testid="symbol-search-clear"]').exists()).toBe(false)
    view.setSymbolQuery('aa')
    await flushPromises()
    const clearBtn = w.get('[data-testid="symbol-search-clear"]')
    await clearBtn.trigger('click')
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('Esc with non-empty query: clears query (does not blur)', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    input.focus()
    view.setSymbolQuery('aa')
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('Esc with empty query: blurs input', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    input.focus()
    expect(document.activeElement).toBe(input)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.activeElement).not.toBe(input)
    w.unmount()
  })

  it('ArrowDown while search input focused still cycles selected symbol', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
    view.selectSymbol('AA')
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    input.focus()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    await flushPromises()
    expect(view.symbol).toBe('AAPL')
    w.unmount()
  })
})
```

- [ ] **Step 2: 验证测试失败**

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts
```

Expected: 新增 8 项 FAIL(input 不存在 / 数量文本 mismatch / Esc / Arrow 断言不成立);既有 hover tooltip 部分仍 PASS。

- [ ] **Step 3: 实现组件变更**

编辑 `path2_web_ui/src/components/SidebarResultList.vue`。

3.1 template 顶部,`<div class="list" ref="listEl">` 内的第一个子元素之前,插入(即紧接 `<div class="list" ref="listEl">` 后):

```vue
    <div v-if="scanFile" class="search-bar">
      <input ref="searchInputEl" type="text"
             data-testid="symbol-search"
             :value="symbolQuery"
             @input="onSearchInput"
             placeholder="搜索 symbol…"
             spellcheck="false" autocomplete="off" />
      <span class="count" data-testid="symbol-search-count">
        {{ filteredSortedRows.length }} / {{ sortedRows.length }}
      </span>
      <button v-if="symbolQuery" class="clear"
              data-testid="symbol-search-clear"
              @click="onClearSearch">×</button>
    </div>
```

3.2 `<script setup>` 的 `storeToRefs` 解构行(约 130–132 行)加 `symbolQuery`:

```typescript
const { scanFile, symbol, preview, previewEnabled, previewLoading, previewError,
        patternIds, sortedRows, filteredSortedRows, sortByPid, sortDesc,
        visiblePatterns, visibleFields, symbolQuery } = storeToRefs(view)
```

3.3 加 ref 与 handler(放在 `const canRefresh = computed(...)` 上方或紧邻 `onCloseError` 附近):

```typescript
const searchInputEl = ref<HTMLInputElement | null>(null)
function onSearchInput(e: Event) {
  view.setSymbolQuery((e.target as HTMLInputElement).value)
}
function onClearSearch() {
  view.clearSymbolQuery()
  searchInputEl.value?.focus()
}
```

3.4 修改 `onArrowKey`:去掉输入框守卫。找到:

```typescript
  const t = e.target as HTMLElement | null
  if (t && t.closest('input, textarea, select, [contenteditable="true"]')) return
```

改成:

```typescript
  // 搜索框 focus 时 ArrowUp/Down 仍切股(input 内光标已在末尾无意义)
  // 只保留 IME 守卫(顶部已有 e.isComposing)
```

即删除这两行的守卫(保留 IME 守卫和字段菜单守卫)。

3.5 修改 `onDocKey`。找到:

```typescript
function onDocKey(e: KeyboardEvent) {
  if (e.key === 'Escape') fieldsMenu.open = false
}
```

替换为:

```typescript
function onDocKey(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  // 搜索框内的 Esc:非空清 query;已空 blur。优先级高于关字段菜单。
  if (document.activeElement === searchInputEl.value) {
    if (symbolQuery.value !== '') {
      view.clearSymbolQuery()
    } else {
      searchInputEl.value?.blur()
    }
    return
  }
  if (fieldsMenu.open) fieldsMenu.open = false
}
```

3.6 加 css(scoped `<style>` 段末尾):

```css
.search-bar { display: flex; align-items: center; gap: 6px;
              padding: 6px 10px; border-bottom: 1px solid #e5e7eb;
              background: #fff; }
.search-bar input { flex: 1; min-width: 0; padding: 3px 6px;
                    font-size: 12px; border: 1px solid #cbd5e1;
                    border-radius: 3px; }
.search-bar .count { font-size: 11px; color: #64748b; white-space: nowrap; }
.search-bar .clear { padding: 0 6px; font-size: 14px; line-height: 1;
                     border: 1px solid #cbd5e1; background: #fff;
                     cursor: pointer; border-radius: 3px; }
.search-bar .clear:hover { background: #f1f5f9; }
```

- [ ] **Step 4: 验证测试全绿**

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts
```

Expected: 全部 PASS(既有 hover tooltip + 新增 8 项)。

- [ ] **Step 5: 跑组件回归**

```bash
cd path2_web_ui && npx vitest run tests/components.candidate-status-bar.spec.ts tests/components.crosshair-overlay.spec.ts tests/components.detail-sidebar.spec.ts tests/components.pattern-stats-tooltip.spec.ts
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
cd path2_web_ui && git add src/components/SidebarResultList.vue tests/components.sidebar-result-list.spec.ts && git commit -m "feat(SidebarResultList): add symbol search bar + Esc handling + arrow-key guard removal

- top search-bar(scanFile 存在时显示):input + count '{f}/{s}' + clear × 按钮
- Esc 在搜索框内:非空清 query / 已空 blur(优先级高于关字段菜单)
- ArrowUp/Down 去掉输入框守卫(搜索框 focus 时仍切股)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: SidebarResultList — 全局字符转发 handler

**Files:**
- Modify: `path2_web_ui/src/components/SidebarResultList.vue`
- Test: `path2_web_ui/tests/components.sidebar-result-list.spec.ts`(追加 describe 块)

**Interfaces:**
- Consumes: Task 2 的 `searchInputEl`、`view.setSymbolQuery`、`view.symbolQuery`
- Produces: `onGlobalCharKey(e)` 在 `document.addEventListener('keydown', ..., true)` 中挂载

---

- [ ] **Step 1: 写失败测试**

在 `tests/components.sidebar-result-list.spec.ts` 追加 describe 块:

```typescript
describe('SidebarResultList · global char forwarding', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function scanFile(symbols: string[]): MultiScanResultFile {
    return {
      pattern_ids: ['bo_only'],
      per_pattern: {
        bo_only: {
          pattern_spec: { pattern_id: 'bo_only', roles: [], edges: [], event_styles: {} } as any,
          end_role: 'tb',
        },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
        dataset_dir: '/d', params: 'default',
        win_start: '2024-01-01', win_end: '2024-06-30', label_horizon: 5,
      },
      results: symbols.map(s => ({
        symbol: s,
        per_pattern: {
          bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.1 },
        },
      })),
    }
  }

  function fireKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...opts }))
  }

  it('typing "a" while body has focus: input gets focus + query becomes "a"', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA', 'AAPL']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    ;(document.body as HTMLElement).focus?.()
    fireKey('a')
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    expect(document.activeElement).toBe(input)
    expect(view.symbolQuery).toBe('a')
    w.unmount()
  })

  it('typing "1" is forwarded (digits accepted)', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('1')
    await flushPromises()
    expect(view.symbolQuery).toBe('1')
    w.unmount()
  })

  it('typing "." and "-" are forwarded', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('.')
    fireKey('-')
    await flushPromises()
    expect(view.symbolQuery).toBe('.-')
    w.unmount()
  })

  it('modifier keys (ctrl+a) are not forwarded', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('a', { ctrlKey: true })
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('non-alphanumeric key (space) is not forwarded', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey(' ')
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('scanFile null: chars not forwarded', async () => {
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('a')
    await flushPromises()
    // 无 scanFile 时 search input 都不渲染,symbolQuery 保持 ''
    const view = useViewStore()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('activeElement is an unrelated input outside listEl → not forwarded', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const outside = document.createElement('input')
    document.body.appendChild(outside)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    outside.focus()
    expect(document.activeElement).toBe(outside)
    fireKey('a')
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    expect(document.activeElement).toBe(outside)
    document.body.removeChild(outside)
    w.unmount()
  })

  it('IME composing key not forwarded', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'a', bubbles: true, isComposing: true,
    }))
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('already focused in searchInputEl: handler returns, browser default input handles typing', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const input = w.get('[data-testid="symbol-search"]').element as HTMLInputElement
    input.focus()
    // 焦点已在 input,handler 应 return 且 view.symbolQuery 不被手工追加
    fireKey('x')
    await flushPromises()
    // 我们不模拟浏览器 default input 事件路由,只断言 handler 未手工追加
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })
})
```

- [ ] **Step 2: 验证测试失败**

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts -t "global char forwarding"
```

Expected: 9 项全 FAIL(handler 尚未挂载)。

- [ ] **Step 3: 实现全局 handler**

编辑 `path2_web_ui/src/components/SidebarResultList.vue`。

3.1 在 `<script setup>` 里加 handler(建议放在其他 handler 附近,如 `onDocClick` / `onDocKey` 后):

```typescript
const CHAR_RE = /^[a-zA-Z0-9.\-]$/

function onGlobalCharKey(e: KeyboardEvent) {
  if (!scanFile.value) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (e.isComposing) return
  const ae = document.activeElement as HTMLElement | null
  // 活动元素守卫:焦点在 body 或列表面板内才劫持;对话框 / 其他面板一律放行
  if (ae !== null && ae !== document.body && !(listEl.value?.contains(ae))) return
  if (e.key.length !== 1 || !CHAR_RE.test(e.key)) return
  const input = searchInputEl.value
  if (!input) return
  if (ae === input) return  // 已 focus 在搜索框,让浏览器默认输入生效
  input.focus()
  view.setSymbolQuery(view.symbolQuery + e.key)
  e.preventDefault()
}
```

3.2 修改 `onMounted`(约 283 行)追加:

```typescript
  document.addEventListener('keydown', onGlobalCharKey, true)   // capture 阶段,先于组件级 window keydown
```

3.3 修改 `onBeforeUnmount`(约 301 行)追加:

```typescript
  document.removeEventListener('keydown', onGlobalCharKey, true)
```

- [ ] **Step 4: 验证测试全绿**

```bash
cd path2_web_ui && npx vitest run tests/components.sidebar-result-list.spec.ts
```

Expected: 既有 hover tooltip + Task 2 8 项 + Task 3 9 项 全 PASS。

- [ ] **Step 5: Commit**

```bash
cd path2_web_ui && git add src/components/SidebarResultList.vue tests/components.sidebar-result-list.spec.ts && git commit -m "feat(SidebarResultList): global char-forwarding handler auto-focus search

- capture 阶段监听 document keydown;字母/数字/./-单字符键
- 守卫序:scanFile / 修饰键 / isComposing / 焦点在 body 或 listEl 内
- 命中:focus + view.symbolQuery += e.key + preventDefault
- 已在搜索框内则放行浏览器默认输入

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: KlineChart — 字母 B 改成 Shift+B

**Files:**
- Modify: `path2_web_ui/src/components/KlineChart.vue`
- Test: `path2_web_ui/tests/components.kline-brush-key.spec.ts`(新建)

**Interfaces:**
- Consumes: 无
- Produces: `KlineChart` 内 `onKeyDown` 的 B 分支只在 `e.shiftKey === true` 时才 toggle brush;单字符 `b` / `B` 均不再消费。

---

- [ ] **Step 1: 写失败测试**

新建 `path2_web_ui/tests/components.kline-brush-key.spec.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'

// 单独测 KlineChart 里 B 快捷键分支的行为;不 mount 整个 KlineChart(它依赖 ECharts 初始化重、
// jsdom 下 canvas/DOMRect 会崩)。改用小型 harness:抽出 onKeyDown 的判定逻辑做纯函数测试。
// 具体:在实施步骤里在 KlineChart.vue 内部把 B 判定改为下列纯函数,再在此测调用它。

import { isBrushToggleKey } from '../src/components/KlineChart.vue?vue-block=script'
// ↑ vitest 目前无法从 SFC 直接 named-import 内部函数,故实施时将 isBrushToggleKey
//   拆到 sibling 文件 src/components/klineBrushKey.ts 并 re-export。

describe('KlineChart · brush toggle key = Shift+B', () => {
  it('Shift+B → true', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(true)
  })
  it('单字符 b → false', () => {
    expect(isBrushToggleKey({ key: 'b', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('单字符 B → false(无 shift 修饰,虽然 CapsLock 可能导致大写)', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Ctrl+Shift+B → false(有其他修饰)', () => {
    expect(isBrushToggleKey({ key: 'B', shiftKey: true, ctrlKey: true, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
  it('Shift+A → false(键不对)', () => {
    expect(isBrushToggleKey({ key: 'A', shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent)).toBe(false)
  })
})
```

- [ ] **Step 2: 验证测试失败**

```bash
cd path2_web_ui && npx vitest run tests/components.kline-brush-key.spec.ts
```

Expected: FAIL,`isBrushToggleKey` 模块不存在。

- [ ] **Step 3: 实现拆分 + 键位修改**

3.1 新建 `path2_web_ui/src/components/klineBrushKey.ts`:

```typescript
// KlineChart 里 brush toggle 快捷键判定(从 onKeyDown 抽出以便单测)。
// 语义:严格 Shift+B(不接受裸 b / B,不接受与 Ctrl/Meta/Alt 组合)。
export function isBrushToggleKey(e: KeyboardEvent): boolean {
  return e.key === 'B' && e.shiftKey === true
      && !e.ctrlKey && !e.metaKey && !e.altKey
}
```

3.2 修改 `tests/components.kline-brush-key.spec.ts` 顶部 import 改为:

```typescript
import { isBrushToggleKey } from '../src/components/klineBrushKey'
```

3.3 编辑 `path2_web_ui/src/components/KlineChart.vue`,`<script setup>` 段(靠近顶部 import 区)加:

```typescript
import { isBrushToggleKey } from './klineBrushKey'
```

3.4 找到 `onKeyDown`(约 379–397 行):

```typescript
function onKeyDown(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  // 输入框内不响应任何全局快捷键(承 Esc/B 共用同一守卫)。
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  // B / b:切换框选光标态(与按钮 toggleBrush 同一路径 · 双向 toggle)。
  if ((e.key === 'b' || e.key === 'B') && !e.ctrlKey && !e.metaKey && !e.altKey) {
    toggleBrush()
    e.preventDefault()
    return
  }
  if (e.key !== 'Escape') return
  ...
}
```

把 B 分支改为(注释同步更新):

```typescript
function onKeyDown(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  // 输入框内不响应任何全局快捷键(承 Esc/Shift+B 共用同一守卫)。
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  // Shift+B:切换框选光标态(与按钮 toggleBrush 同一路径 · 双向 toggle)。
  // 让位字母 B 给 SidebarResultList 全局字符转发(输代码即定位股)。
  if (isBrushToggleKey(e)) {
    toggleBrush()
    e.preventDefault()
    return
  }
  if (e.key !== 'Escape') return
  ...
}
```

3.5 若 template / 组件按钮 tooltip 里显示过 "B" 键提示,搜索 `title="B"` / `title="按 B` / `>B<` 字样并改成 `Shift+B`。执行前 grep 定位:

```bash
grep -n "'B'\|\"B\"\|按 *B\|(B)" path2_web_ui/src/components/KlineChart.vue
```

按结果决定是否改 template(若无匹配,跳过)。

- [ ] **Step 4: 验证测试全绿**

```bash
cd path2_web_ui && npx vitest run tests/components.kline-brush-key.spec.ts
```

Expected: 5 项全 PASS。

- [ ] **Step 5: 跑 KlineChart 相邻组件回归**

```bash
cd path2_web_ui && npx vitest run tests/components.kline-band-zoom.spec.ts tests/components.kline-band-zoom-handlers.spec.ts tests/components.kline-click.spec.ts
```

Expected: 全部 PASS(无回归)。

- [ ] **Step 6: 全套 typecheck + build**

```bash
cd path2_web_ui && npx vue-tsc -b && npx vite build
```

Expected: 无 TS 错;build 成功。

- [ ] **Step 7: Commit**

```bash
cd path2_web_ui && git add src/components/KlineChart.vue src/components/klineBrushKey.ts tests/components.kline-brush-key.spec.ts && git commit -m "refactor(KlineChart): brush toggle key: 单字符 B → Shift+B

- 抽 isBrushToggleKey 到 klineBrushKey.ts 便于单测
- 让位字母 B 给 SidebarResultList 全局字符转发(输代码即定位股)
- 单字符 b/B 不再消费;Ctrl+Shift+B 类组合也不消费(必须裸 Shift+B)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: E2E Playwright smoke(完整链路)

**Files:**
- Add: `path2_web_ui/e2e/symbol-search.spec.ts`

**Interfaces:**
- Consumes: Task 1–4 所有变更;后端(FastAPI 在 `apiBase`,即 `localhost:8000`)已在线 + 已有过至少一次命中扫描(或本测试触发一次)。
- Produces: 一条端到端 smoke,覆盖 spec §六 E2E 期望的五段:load → 键入 AA → 数量提示更新 → Esc 清空 → 按 ↓ 切股 → Shift+B 触发 brush toggle → 单字符 B 只吸到搜索框而不触发 brush。

**参考 `path2_web_ui/e2e/flow.spec.ts` 头部的 `ensureScanLoaded` 辅助函数**——这是本 codebase e2e 加载扫描数据的既有惯例(先查历史,无历史则触发扫描)。本 task 直接复制该辅助(不 export/共享,e2e 允许小重复)。

---

- [ ] **Step 1: 探已有 e2e 惯例(不 commit)**

只读参考:

```bash
head -55 path2_web_ui/e2e/flow.spec.ts
```

要复用的辅助:`openScanDialogAndSelectAll` + `ensureScanLoaded` 两函数。

- [ ] **Step 2: 写 smoke 测试**

新建 `path2_web_ui/e2e/symbol-search.spec.ts`:

```typescript
import { test, expect } from '@playwright/test'

// 前提:后端在 localhost:8000 在线;已有一次命中扫描(或本测试触发扫描)。
// 复用 flow.spec.ts 的 ensureScanLoaded 辅助模式(e2e 允许小重复)。

async function openScanDialogAndSelectAll(page: any) {
  await page.getByRole('button', { name: /扫描 ⚙/ }).click()
  await expect(page.locator('.pattern-list li').first()).toBeVisible({ timeout: 10_000 })
  await page.locator('.backdrop').getByRole('button', { name: '全选' }).click()
}

async function ensureScanLoaded(page: any) {
  await page.goto('/')
  await expect(page.locator('select')).toContainText('底部反转突破爆发')
  await page.getByRole('button', { name: /打开历史/ }).click()
  await expect(page.locator('.file-list, .state')).toBeVisible({ timeout: 5_000 })
  const rowCount = await page.locator('.file-list tbody tr').count()
  if (rowCount === 0) {
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.backdrop')).not.toBeVisible()
    await openScanDialogAndSelectAll(page)
    await page.getByRole('button', { name: /开始扫描/ }).click()
    await expect(page.locator('.done')).toBeVisible({ timeout: 180_000 })
    await page.getByRole('button', { name: /打开历史/ }).click()
    await expect(page.locator('.file-list')).toBeVisible({ timeout: 5_000 })
  }
  await page.locator('.file-list tbody tr').first().click()
  await page.getByRole('button', { name: /^Open$/ }).click()
  await expect(page.locator('[data-symbol]').first()).toBeVisible({ timeout: 30_000 })
}

test.describe('symbol search e2e', () => {
  test('empty state: search bar not rendered', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-testid="symbol-search"]')).toHaveCount(0)
  })

  test('after scan load: search bar visible + typing narrows list + Esc clears + Shift+B safe', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))

    await ensureScanLoaded(page)

    // 搜索框出现
    const search = page.locator('[data-testid="symbol-search"]')
    await expect(search).toBeVisible({ timeout: 10_000 })

    // 记录初始行数
    const initialCount = await page.locator('[data-symbol]').count()
    expect(initialCount).toBeGreaterThan(0)

    // 全局字符转发:body 焦点下按字符 'a',应自动 focus 搜索框且值为 'a'
    await page.locator('body').click({ position: { x: 5, y: 5 } })  // 先把焦点撞出可能的 input
    await page.keyboard.press('KeyA')
    await expect(search).toBeFocused()
    await expect(search).toHaveValue('a')

    // 列表数量下降或相等(过滤后 ≤ 初始)
    const afterCount = await page.locator('[data-symbol]').count()
    expect(afterCount).toBeLessThanOrEqual(initialCount)

    // 数量提示可见
    await expect(page.locator('[data-testid="symbol-search-count"]')).toBeVisible()

    // Esc 清空 query
    await page.keyboard.press('Escape')
    await expect(search).toHaveValue('')

    // Shift+B 回归入口 A:不抛错(brush toggle 生效或 no-op,不做视觉断言避免脆)
    await page.locator('body').click({ position: { x: 5, y: 5 } })
    await page.keyboard.press('Shift+KeyB')
    expect(errors).toEqual([])

    // 单字符 B(裸 b)应吸到搜索框而非触发 brush
    await page.locator('body').click({ position: { x: 5, y: 5 } })
    // 先清 query 保证起点为空
    await page.keyboard.press('Escape')
    await page.keyboard.press('KeyB')
    await expect(search).toBeFocused()
    await expect(search).toHaveValue('b')
    expect(errors).toEqual([])
  })
})
```

- [ ] **Step 3: 跑 e2e**

前置确认:后端服务在 `localhost:8000` 已启动(否则 `ensureScanLoaded` 会等超时)。若不确定:

```bash
curl -s http://localhost:8000/patterns > /dev/null && echo OK || echo "backend not up"
```

若返回 "backend not up",先手动起后端(参考项目根 `scripts/run_path2_web.py`);然后:

```bash
cd path2_web_ui && npx playwright test e2e/symbol-search.spec.ts --workers=1
```

Expected: 2 项 PASS(首个 empty-state 不依赖后端也应 PASS;第二个若无历史扫描则会触发一次真扫描,可能花 3 分钟)。

- [ ] **Step 4: Commit**

```bash
cd path2_web_ui && git add e2e/symbol-search.spec.ts && git commit -m "test(e2e): symbol search full flow — load → filter → Esc → Shift+B 回归

复用 flow.spec.ts 的 ensureScanLoaded 辅助:
- empty state:搜索框不渲染
- after scan:字符 a 自动 focus 搜索框 + 列表窄化 + Esc 清空
- Shift+B 不抛(brush toggle 回归)
- 单字符 b 吸到搜索框而非 brush

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 收尾验证(在 Task 5 完成后 holistic 前跑)

```bash
cd path2_web_ui && npm run test  # 全套 vitest
cd path2_web_ui && npx vue-tsc -b && npx vite build  # 类型 + 构建
```

Expected: 三绿(vitest 全 PASS + tsc 无错 + build 成功)。

---

## 附录 · 快速回顾

| Task | 改动文件 | 测试文件 | 测试项数(新增) |
|---|---|---|---|
| 1 | `src/stores/view.ts` | `tests/view.symbol-search.spec.ts` | 8 |
| 2 | `src/components/SidebarResultList.vue` | `tests/components.sidebar-result-list.spec.ts`(追加) | 8 |
| 3 | `src/components/SidebarResultList.vue` | `tests/components.sidebar-result-list.spec.ts`(追加) | 9 |
| 4 | `src/components/KlineChart.vue` + `src/components/klineBrushKey.ts` | `tests/components.kline-brush-key.spec.ts` | 5 |
| 5 | (无 src 改动) | `e2e/symbol-search.spec.ts` | 2(第 2 项覆盖完整链路) |
