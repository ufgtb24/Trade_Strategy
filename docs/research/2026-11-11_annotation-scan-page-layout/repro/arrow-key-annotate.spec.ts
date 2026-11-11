// 一次性核对(options 第 1 问):加载了扫描后,在 annotate / compare 里、焦点在文本框中按 ↓,会不会跳到扫描列表并切成扫描的 app。
// 在 scratchpad 的前端副本里跑(tests/ 下),不进仓库测试。
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SidebarResultList from '../src/components/SidebarResultList.vue'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

function makeMultiFile(symbols: string[]): MultiScanResultFile {
  return {
    pattern_ids: ['bo_only'],
    per_pattern: { bo_only: { pattern_spec: { pattern_id: 'bo_only', nodes: [], edges: [], event_styles: {} } as any, end_node: 'tb' } },
    scan: { scan_ts: '20260714T120000', start_date: '2024-01-01', end_date: '2024-06-30', workers: 1, scanned: symbols.length,
            hit_stocks: symbols.length, errors: 0, dataset_dir: '/d', params: 'default', win_start: '2024-01-01',
            win_end: '2024-06-30', label_horizon: 5, first_passage_k: 2 },
    results: symbols.map(s => ({ symbol: s, per_pattern: { bo_only: { summary: { hits: 1 }, analysis: { events: [], hits: [] }, max_forward_return: 0.1 } } })),
  } as any
}

function pressInTextarea(key: string) {
  const ta = document.createElement('textarea')
  ta.value = 'note'
  document.body.appendChild(ta)
  ta.focus()
  ta.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  const focused = document.activeElement === ta
  ta.remove()
  return focused
}

describe('有扫描时,标注文本框里按 ↑/↓', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  for (const m of ['annotate', 'compare'] as const) {
    it(`${m}:当前图不在列表里 → 跳到第一行、切成扫描的 app`, async () => {
      const view = useViewStore()
      view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
      view.openSymbol('CRNC')                     // 按代码打开:落在 annotate,扫描留着
      if (m === 'compare') view.enterLinked('compare')
      expect(view.mode).toBe(m)
      const w = mount(SidebarResultList, { attachTo: document.body })
      await flushPromises()
      expect(pressInTextarea('ArrowDown')).toBe(true)
      await flushPromises()
      expect([view.symbol, view.mode, view.appSource]).toEqual(['AA', 'app', 'scan'])
      w.unmount()
    })
  }

  it('annotate:当前图在列表里 → 跳到下一行', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
    view.openSymbol('AAPL')
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    pressInTextarea('ArrowDown')
    await flushPromises()
    expect([view.symbol, view.mode]).toEqual(['BAA', 'app'])
    w.unmount()
  })

  it('没加载扫描:不起作用', async () => {
    const view = useViewStore()
    view.openSymbol('CRNC')
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    pressInTextarea('ArrowDown')
    await flushPromises()
    expect([view.symbol, view.mode]).toEqual(['CRNC', 'annotate'])
    w.unmount()
  })

  it('输入法组字中(isComposing)不起作用', async () => {
    const view = useViewStore()
    view.loadScanFile(makeMultiFile(['AA', 'AAPL', 'BAA']))
    view.openSymbol('CRNC')
    const w = mount(SidebarResultList, { attachTo: document.body })
    await flushPromises()
    const ta = document.createElement('textarea'); document.body.appendChild(ta); ta.focus()
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, isComposing: true }))
    ta.remove()
    await flushPromises()
    expect([view.symbol, view.mode]).toEqual(['CRNC', 'annotate'])
    w.unmount()
  })
})
