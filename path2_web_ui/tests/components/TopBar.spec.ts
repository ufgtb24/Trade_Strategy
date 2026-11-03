// 顶栏 symbol:回车打开(落在 annotate);列表里没有 → not_found,不动当前的图。
// rally:展开大涨段清单,点一行打开那段涨之前的图;random:随机给一段图。两处进来都落在 annotate
// ref:参照层 peaks 的复选框,默认关,只在 annotate / compare 下可用,换股票自动关
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TopBar from '../../src/components/TopBar.vue'
import { useViewStore } from '../../src/stores/view'
import * as api from '../../src/api'

const RALLY = [
  { symbol: 'MSFT', date: '2024-03-01', peak_date: '2024-03-20', rise: 0.5, rel: 2.5,
    view_start: '2023-09-12', view_end: '2024-04-26' },
  { symbol: 'AAPL', date: '2025-01-02', peak_date: '2025-02-10', rise: 1.2, rel: 3.1,
    view_start: '2024-07-11', view_end: '2025-02-28' },
]

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT'])),
  getRally: vi.fn(() => Promise.resolve(RALLY)),
  getRandom: vi.fn(() => Promise.resolve({ symbol: 'MSFT', start: '2023-01-03', end: '2023-12-28' })),
  getPeaks: vi.fn(() => Promise.resolve([{ date: '2025-01-03', price: 12, end: '2025-01-07' }])),
}))

async function mountIt() {
  const w = mount(TopBar)
  await flushPromises()
  return { w, view: useViewStore(), input: w.get('[data-testid="symbol-input"]') }
}

describe('TopBar · symbol', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('字段名 symbol;股票列表进输入提示', async () => {
    const { w } = await mountIt()
    expect(w.text()).toContain('symbol')
    expect(w.findAll('datalist option').map(o => o.attributes('value'))).toEqual(['AAPL', 'MSFT'])
  })

  it('输入代码回车 → 打开它、落在 annotate', async () => {
    const { w, view, input } = await mountIt()
    view.mode = 'app'
    await input.setValue(' msft ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(view.symbol).toBe('MSFT')
    expect(view.mode).toBe('annotate')
    expect((input.element as HTMLInputElement).value).toBe('MSFT')
    expect(w.find('[data-testid="symbol-status"]').exists()).toBe(false)
  })

  it('列表里没有 → not_found,当前的图不动;再改输入提示消失', async () => {
    const { w, view, input } = await mountIt()
    view.openSymbol('AAPL')
    await flushPromises()
    await input.setValue('NEW26')
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.get('[data-testid="symbol-status"]').text()).toBe('not_found')
    expect(view.symbol).toBe('AAPL')
    await input.setValue('MSF')
    expect(w.find('[data-testid="symbol-status"]').exists()).toBe(false)
  })

  it('输入框显示当前打开的股票(从扫描列表换股时跟着变)', async () => {
    const { view, input } = await mountIt()
    view.selectSymbol('AAPL')
    await flushPromises()
    expect((input.element as HTMLInputElement).value).toBe('AAPL')
  })
})

describe('TopBar · rally / random', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('rally:展开才取清单;按 rise 降序;点表头换序;点一行 → 打开它、落在 annotate、停在那段的图窗、清单收起', async () => {
    const { w, view } = await mountIt()
    expect(api.getRally).not.toHaveBeenCalled()
    view.mode = 'app'
    await w.get('[data-testid="rally-button"]').trigger('click')
    await flushPromises()
    const rows = () => w.findAll('[data-testid="rally-row"]').map(r => r.attributes('data-symbol'))
    expect(rows()).toEqual(['AAPL', 'MSFT'])
    expect(w.findAll('th').map(t => t.text().replace(/[▲▼]/, ''))).toEqual(['symbol', 'date', 'rise'])
    await w.get('[data-testid="rally-sort-symbol"]').trigger('click')
    expect(rows()).toEqual(['AAPL', 'MSFT'])
    await w.get('[data-testid="rally-sort-symbol"]').trigger('click')
    expect(rows()).toEqual(['MSFT', 'AAPL'])
    await w.get('[data-testid="rally-row"][data-symbol="MSFT"]').trigger('click')
    expect(view.mode).toBe('annotate')
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-09-12', end: '2024-04-26' })
    expect(w.get('[data-testid="rally-list"]').isVisible()).toBe(false)
    // 再展开:不重取,当前打开的那行标出来
    await w.get('[data-testid="rally-button"]').trigger('click')
    expect(api.getRally).toHaveBeenCalledTimes(1)
    expect(w.get('[data-testid="rally-row"][data-symbol="MSFT"]').classes()).toContain('current')
    expect(w.get('[data-testid="rally-row"][data-symbol="AAPL"]').classes()).not.toContain('current')
  })

  it('rally:清单为空 → empty;取失败 → load_failed', async () => {
    vi.mocked(api.getRally).mockImplementationOnce(() => Promise.resolve([]))
    const { w } = await mountIt()
    await w.get('[data-testid="rally-button"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="rally-status"]').text()).toBe('empty')

    setActivePinia(createPinia())
    vi.mocked(api.getRally).mockImplementationOnce(() => Promise.reject(new Error('x')))
    const second = await mountIt()
    await second.w.get('[data-testid="rally-button"]').trigger('click')
    await flushPromises()
    expect(second.w.get('[data-testid="rally-status"]').text()).toBe('load_failed')
  })

  it('random:打开随机的那段、落在 annotate;股票池为空 → empty', async () => {
    const { w, view, input } = await mountIt()
    view.mode = 'app'
    await w.get('[data-testid="random-button"]').trigger('click')
    await flushPromises()
    expect(view.mode).toBe('annotate')
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-01-03', end: '2023-12-28' })
    expect((input.element as HTMLInputElement).value).toBe('MSFT')
    vi.mocked(api.getRandom).mockImplementationOnce(() => Promise.reject({ status: 404 }))
    await w.get('[data-testid="random-button"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="random-status"]').text()).toBe('empty')
    expect(w.find('[data-testid="symbol-status"]').exists()).toBe(false)
    expect(view.symbol).toBe('MSFT')
  })
})

describe('TopBar · ref', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  const box = (w: any) => w.get('[data-testid="ref-peaks"]').element as HTMLInputElement

  it('字段名 ref,复选框 peaks;默认关;还没打开股票时不能勾', async () => {
    const { w } = await mountIt()
    expect(w.get('[data-testid="ref-group"]').text()).toBe('refpeaks')
    expect([box(w).checked, box(w).disabled]).toEqual([false, true])
  })

  it('annotate 下勾上 → 要峰;换股票 → 自动取消勾选', async () => {
    const { w, view } = await mountIt()
    view.openSymbol('AAPL')
    await flushPromises()
    expect(box(w).disabled).toBe(false)
    await w.get('[data-testid="ref-peaks"]').setValue(true)
    await flushPromises()
    expect(api.getPeaks).toHaveBeenCalledWith('AAPL')
    expect(box(w).checked).toBe(true)
    view.openSymbol('MSFT')
    await flushPromises()
    expect(box(w).checked).toBe(false)
  })

  it('app 下变灰、不能勾', async () => {
    const { w, view } = await mountIt()
    view.openSymbol('AAPL')
    await flushPromises()
    await w.get('[data-testid="ref-peaks"]').setValue(true)
    view.selectSymbol('AAPL')
    await flushPromises()
    expect([box(w).checked, box(w).disabled]).toEqual([false, true])
    expect(w.get('[data-testid="ref-group"] label').classes()).toContain('off')
  })

  it('没有峰 → empty;没要到 → load_failed', async () => {
    const { w, view } = await mountIt()
    view.openSymbol('AAPL')
    await flushPromises()
    vi.mocked(api.getPeaks).mockImplementationOnce(() => Promise.resolve([]))
    await w.get('[data-testid="ref-peaks"]').setValue(true)
    await flushPromises()
    expect(w.get('[data-testid="ref-status"]').text()).toBe('empty')
    await w.get('[data-testid="ref-peaks"]').setValue(false)
    expect(w.find('[data-testid="ref-status"]').exists()).toBe(false)
    vi.mocked(api.getPeaks).mockImplementationOnce(() => Promise.reject(new Error('503')))
    await w.get('[data-testid="ref-peaks"]').setValue(true)
    await flushPromises()
    expect(w.get('[data-testid="ref-status"]').text()).toBe('load_failed')
  })
})
