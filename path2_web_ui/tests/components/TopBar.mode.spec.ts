// 顶栏 mode:annotate / compare / app 三档,当前 pattern 没有 app(或还没打开股票)时 compare、app 变灰;
// compare、现算的 app 下旁边写 app 的名字,悬停列出 mapping 的每一行。tiers:app、compare 下可用,默认开。
// compare 下用代码输入、random 换图留在 compare;从扫描结果的 app 出发落在 annotate。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TopBar from '../../src/components/TopBar.vue'
import { useViewStore } from '../../src/stores/view'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useAppLinkStore } from '../../src/stores/appLink'

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT'])),
  getRandom: vi.fn(() => Promise.resolve({ symbol: 'MSFT', start: '2023-01-03', end: '2023-12-28' })),
  getRally: vi.fn(() => Promise.resolve([])),
  getPeaks: vi.fn(() => Promise.resolve([])),
  getMappings: vi.fn(() => Promise.resolve([
    { app: 'bo_only', pattern: 'P', features: { 'w-pc-1': 'bo', 'w-pc-9': 'bo' }, problem: null },
    { app: 'bad', pattern: 'BAD', features: {}, problem: 'node not in app bad: x' },
  ])),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [] }, summary: {},
    pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_nodes: [] },
    scan: { win_start: '1899-09-01', win_end: '2025-12-31', end_node: 'bo' },
  })),
  getDiagnose: vi.fn(() => Promise.resolve({ nodes: {} })),
  getAnnotations: vi.fn(() => new Promise(() => {})),
  postAnnotationBatch: vi.fn(),
}))

async function mountIt(pattern: string | null) {
  const w = mount(TopBar)
  const links = useAppLinkStore()
  await links.load()
  useAnnotationStore().setCurrentPattern(pattern)
  await flushPromises()
  return { w, view: useViewStore(), links }
}
const btn = (w: any, m: string) => w.get(`[data-testid="mode-${m}"]`)

describe('TopBar · mode 与 tiers', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('annotate 下:annotate 按下;没有 app 时 compare、app 变灰,悬停说明原因;tiers 变灰', async () => {
    const { w, view } = await mountIt('NONE')
    view.openSymbol('AAPL')
    await flushPromises()
    expect(btn(w, 'annotate').classes()).toContain('on')
    for (const m of ['compare', 'app']) {
      expect(btn(w, m).attributes('disabled')).toBeDefined()
      expect(btn(w, m).classes()).toContain('off')
      expect(btn(w, m).attributes('title')).toContain('the current pattern has no app')
    }
    expect(w.get('[data-testid="tiers"]').attributes('disabled')).toBeDefined()
    expect((w.get('[data-testid="tiers"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('mapping 有问题:变灰,悬停写出问题', async () => {
    const { w, view } = await mountIt('BAD')
    view.openSymbol('AAPL')
    await flushPromises()
    expect(btn(w, 'compare').attributes('title')).toContain('node not in app bad: x')
  })

  it('有 app 但还没打开股票:变灰;打开之后可点,点 compare → compare,旁边写 app 名,悬停列出 mapping', async () => {
    const { w, view } = await mountIt('P')
    expect(btn(w, 'compare').attributes('disabled')).toBeDefined()
    expect(btn(w, 'compare').attributes('title')).toBe('open a symbol first')
    view.openSymbol('AAPL')
    await flushPromises()
    expect(btn(w, 'compare').attributes('disabled')).toBeUndefined()
    await btn(w, 'compare').trigger('click')
    await flushPromises()
    expect(view.mode).toBe('compare')
    expect(btn(w, 'compare').classes()).toContain('on')
    const id = w.get('[data-testid="linked-app"]')
    expect(id.text()).toBe('bo_only')
    expect(id.attributes('title')).not.toContain('w-pc-1')            // 不显示 mapping
    expect(w.get('[data-testid="tiers"]').attributes('disabled')).toBeUndefined()
    await btn(w, 'app').trigger('click')
    expect([view.mode, view.appSource]).toEqual(['app', 'linked'])
    await w.get('[data-testid="tiers"]').setValue(false)
    expect(view.tiers).toBe(false)
    await btn(w, 'annotate').trigger('click')
    expect(view.mode).toBe('annotate')
    expect(w.find('[data-testid="linked-app"]').exists()).toBe(false)
  })

  it('compare 下用代码输入、random 换图:留在 compare;扫描结果的 app 下用代码输入:落在 annotate', async () => {
    const { w, view, links } = await mountIt('P')
    view.openSymbol('AAPL')
    links.setMode('compare')
    await flushPromises()
    const input = w.get('[data-testid="symbol-input"]')
    await input.setValue('MSFT')
    await input.trigger('keydown', { key: 'Enter' })
    expect([view.symbol, view.mode]).toEqual(['MSFT', 'compare'])
    await w.get('[data-testid="random-button"]').trigger('click')
    await flushPromises()
    expect(view.mode).toBe('compare')
    view.selectSymbol('AAPL')
    await flushPromises()
    await input.setValue('MSFT')
    await input.trigger('keydown', { key: 'Enter' })
    expect([view.symbol, view.mode]).toEqual(['MSFT', 'annotate'])
  })

  it('扫描结果的 app(从扫描列表选股):app 按下;点它不换来源', async () => {
    const { w, view } = await mountIt('NONE')
    view.selectSymbol('AAPL')
    await flushPromises()
    expect(btn(w, 'app').classes()).toContain('on')
    expect(btn(w, 'app').attributes('disabled')).toBeUndefined()
    await btn(w, 'app').trigger('click')
    expect([view.mode, view.appSource]).toEqual(['app', 'scan'])
  })
})
