import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SidebarResultList from '../src/components/SidebarResultList.vue'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, PatternStats } from '../src/types'

const SAMPLE_STATS: PatternStats = {
  count: 10, mean: 0.05, min: -0.02, q25: 0.01,
  median: 0.05, q75: 0.08, max: 0.15, win_rate: 0.7,
}

function makeScanFile(pids: string[], withStats: boolean): MultiScanResultFile {
  const per_pattern: Record<string, any> = {}
  for (const pid of pids) {
    per_pattern[pid] = {
      pattern_spec: { pattern_id: pid, nodes: [], edges: [], event_styles: {} } as any,
      end_node: 'tb',
      ...(withStats ? { stats: SAMPLE_STATS } : {}),
    }
  }
  return {
    pattern_ids: pids,
    per_pattern,
    scan: {
      scan_ts: '20260713T120000',
      start_date: '2025-01-01', end_date: '2026-12-31', workers: 2,
      scanned: 0, hits: 0, errors: 0, dataset_dir: '', params: 'default',
      win_start: '2025-01-01', win_end: '2026-12-31', label_horizon: 5, first_passage_k: 2,
    },
    results: [],
  }
}

describe('SidebarResultList · hover tooltip', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('shows PatternStatsTooltip on hdr-pattern hover when stats present', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFile(['bo_only'], true))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    expect(th.exists()).toBe(true)
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    w.unmount()
  })

  it('does not mount tooltip when stats absent (old JSON)', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFile(['bo_only'], false))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(false)
    w.unmount()
  })

  it('hides tooltip on mouseleave', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFile(['bo_only'], true))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    await th.trigger('mouseleave')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(false)
    w.unmount()
  })

  it('multi-pattern hovers show tooltip for each pid independently', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFile(['bo_only', 'bottom_burst'], true))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th1 = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    const th2 = w.find('.col-pattern[data-pattern-pid="bottom_burst"]')
    expect(th1.exists() && th2.exists()).toBe(true)

    await th1.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    await th1.trigger('mouseleave')

    await th2.trigger('mouseenter')
    await flushPromises()
    expect(w.findComponent({ name: 'PatternStatsTooltip' }).exists()).toBe(true)
    w.unmount()
  })

  // ── Task 5 · 首次穿越块 hover 接线 ────────────────────────────────────────
  it('hover 的 pattern 有 first_passage_stats → tooltip 渲染首次穿越块', async () => {
    const view = useViewStore()
    const file = makeScanFile(['bo_only'], true)
    ;(file.per_pattern['bo_only'] as any).first_passage_stats = {
      up: 30, down: 10, both: 2, none: 3, n_match: 45, ratio: 0.75,
      random_up: 23, random_down: 22, random_both: 0, random_none: 0, random_n: 45, random_ratio: 0.511, k: 2,
    }
    view.loadScanFile(file)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    // 首次穿越块挂出(单组口径)· k 标注 + 命中集先涨比例可见
    expect(w.find('.stats-first-passage').exists()).toBe(true)
    const txt = w.find('.stats-first-passage').text()
    expect(txt).toContain('k=2')
    expect(txt).toContain('75%')     // ratio
    expect(txt).toContain('51%')     // random_ratio
    w.unmount()
  })

  it('hover 的 pattern 无 first_passage_stats → tooltip 不渲染首次穿越块(向后兼容)', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFile(['bo_only'], true))   // 无 first_passage_stats
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const th = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    await th.trigger('mouseenter')
    await flushPromises()
    expect(w.find('.stats-first-passage').exists()).toBe(false)
    w.unmount()
  })
})

describe('SidebarResultList · symbol search UI', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function makeMultiFile(symbols: string[]): MultiScanResultFile {
    return {
      pattern_ids: ['bo_only'],
      per_pattern: {
        bo_only: {
          pattern_spec: { pattern_id: 'bo_only', nodes: [], edges: [], event_styles: {} } as any,
          end_node: 'tb',
        },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
        dataset_dir: '/d', params: 'default',
        win_start: '2024-01-01', win_end: '2024-06-30', label_horizon: 5, first_passage_k: 2,
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
    w.unmount()
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

describe('SidebarResultList · global char forwarding', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function scanFile(symbols: string[]): MultiScanResultFile {
    return {
      pattern_ids: ['bo_only'],
      per_pattern: {
        bo_only: {
          pattern_spec: { pattern_id: 'bo_only', nodes: [], edges: [], event_styles: {} } as any,
          end_node: 'tb',
        },
      },
      scan: {
        scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30',
        workers: 1, scanned: symbols.length, hits: symbols.length, errors: 0,
        dataset_dir: '/d', params: 'default',
        win_start: '2024-01-01', win_end: '2024-06-30', label_horizon: 5, first_passage_k: 2,
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
    // NOTE: two separate mounts, not two fireKey() calls on one mount.
    // Reason: after the 1st char auto-focuses the search input, jsdom does not
    // simulate native "insert character into focused input" for synthetic
    // (untrusted) KeyboardEvents (verified empirically) — real browsers gate
    // that default action on event.isTrusted too. So a 2nd fireKey() on the
    // same mount would hit the (correct, tested separately below) "already
    // focused → let browser handle it" bail and never actually land, which
    // would test an artifact of jsdom rather than CHAR_RE coverage. Remounting
    // resets activeElement to document.body, exercising the same
    // not-yet-focused forwarding path for each char while still accumulating
    // onto the same store's symbolQuery.
    const w1 = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('.')
    await flushPromises()
    w1.unmount()

    const w2 = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('-')
    await flushPromises()
    expect(view.symbolQuery).toBe('.-')
    w2.unmount()
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

  it('Shift+P is not forwarded to search (shift modifier)', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('P', { shiftKey: true })
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })

  it('Shift+B is not forwarded to search (brush toggle 让出,回归保障)', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('B', { shiftKey: true })
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

  it('Shift+B (brush hotkey) not forwarded to search', async () => {
    const view = useViewStore()
    view.loadScanFile(scanFile(['AA']))
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    fireKey('B', { shiftKey: true })
    await flushPromises()
    expect(view.symbolQuery).toBe('')
    w.unmount()
  })
})

describe('SidebarResultList · pattern 命中股票数', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  // makeScanFile 的 results 是空数组,这里补上两只股:
  // AAA 两个 pattern 都命中 · BBB 只命中 bo_only → bo_only=2, bbb=1
  function makeScanFileWithResults(): MultiScanResultFile {
    const f = makeScanFile(['bo_only', 'bbb'], false)
    f.results = [
      { symbol: 'AAA', per_pattern: {
        bo_only: { summary: { matches: 2 }, analysis: { events: [], matches: [] }, max_forward_return: 0.34 },
        bbb:     { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.10 },
      }},
      { symbol: 'BBB', per_pattern: {
        bo_only: { summary: { matches: 1 }, analysis: { events: [], matches: [] }, max_forward_return: 0.50 },
        bbb:     { summary: { matches: 0 }, analysis: { events: [], matches: [] }, max_forward_return: null },
      }},
    ]
    return f
  }

  it('第一级表头同时显示 pid 与命中股票数', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFileWithResults())
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()

    const thBo = w.find('.col-pattern[data-pattern-pid="bo_only"]')
    expect(thBo.text()).toContain('bo_only')
    expect(thBo.find('[data-testid="pattern-hit-count"]').text()).toBe('2')

    const thBbb = w.find('.col-pattern[data-pattern-pid="bbb"]')
    expect(thBbb.text()).toContain('bbb')
    expect(thBbb.find('[data-testid="pattern-hit-count"]').text()).toBe('1')

    w.unmount()
  })

  it('搜索过滤后表头计数不变', async () => {
    const view = useViewStore()
    view.loadScanFile(makeScanFileWithResults())
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()

    view.setSymbolQuery('AA')          // 只剩 AAA 一行
    await flushPromises()

    expect(view.filteredSortedRows.length).toBe(1)   // 搜索确实生效
    expect(w.find('.col-pattern[data-pattern-pid="bo_only"]')
            .find('[data-testid="pattern-hit-count"]').text()).toBe('2')
    w.unmount()
  })

  it('零命中的 pattern 显示 0', async () => {
    const f = makeScanFileWithResults()
    for (const r of f.results) (r.per_pattern as any).bbb.summary.matches = 0
    const view = useViewStore()
    view.loadScanFile(f)
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()

    expect(w.find('.col-pattern[data-pattern-pid="bbb"]')
            .find('[data-testid="pattern-hit-count"]').text()).toBe('0')
    w.unmount()
  })
})
