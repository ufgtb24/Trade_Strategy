// annotate 模式的图:按代码取全部 K 线,主图只有 K 线 + 成交量,副图留空,没有 app 的产物和 app 的交互
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import KlineChart from '../../src/components/KlineChart.vue'
import { useViewStore } from '../../src/stores/view'
import * as api from '../../src/api'
import { SCAN_FILE } from '../fixtures'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const BARS = Array.from({ length: 30 }, (_, i) => ({
  date: `2025-12-${String(i + 1).padStart(2, '0')}`, o: 10, h: 11, l: 9, c: 10 + (i % 2), v: 1000 + i, rv: 1,
}))

vi.mock('../../src/api', () => ({
  saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getOhlc: vi.fn(() => Promise.resolve({ bars: [] })),
  getAllOhlc: vi.fn((symbol: string) => Promise.resolve({ symbol, bars: BARS })),
}))

const charts: any[] = []
function makeFakeChart() {
  const zr = { on: vi.fn(), off: vi.fn() }
  const c = {
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), clear: vi.fn(),
    on: vi.fn(), off: vi.fn(), getZr: () => zr, getOption: () => ({}),
    dispatchAction: vi.fn(), convertToPixel: () => [0, 0], getWidth: () => 800, getHeight: () => 600,
  }
  charts.push(c)
  return c
}
vi.mock('echarts', () => ({ init: vi.fn(() => makeFakeChart()) }))

describe('KlineChart · annotate', () => {
  beforeEach(() => { setActivePinia(createPinia()); charts.length = 0; vi.clearAllMocks() })

  it('按代码打开(扫描里也有这只):取全部 K 线;主图只有 K 线和成交量,app 的系列全空;副图清空', async () => {
    const view = useViewStore()
    view.loadScanFile(SCAN_FILE)                 // 扫描结果里 AAPL 有 app 产物
    const w = mount(KlineChart)
    await flushPromises()
    view.openSymbol('AAPL')
    await flushPromises()
    expect(api.getAllOhlc).toHaveBeenLastCalledWith('AAPL')
    const [main, sub] = charts
    const opt = main.setOption.mock.calls.filter((c: any[]) => c[1] === true).at(-1)[0]
    const byName = Object.fromEntries(opt.series.map((s: any) => [s.name, s]))
    expect(byName.kline.data).toHaveLength(BARS.length)
    expect(byName.volume.data).toHaveLength(BARS.length)
    for (const n of ['price-points', 'highlight-price', 'shift-veil-price']) expect(byName[n].data).toEqual([])
    expect(opt.grid).toHaveLength(2)
    expect(sub.clear).toHaveBeenCalled()
    // app 的交互入口不出现
    expect(w.find('.brush-toggle-wrap').exists()).toBe(false)
    expect(w.find('[data-symbol="AAPL"]').exists()).toBe(true)
  })

  it('右键不弹 driver 菜单', async () => {
    const view = useViewStore()
    const w = mount(KlineChart)
    view.openSymbol('AAPL')
    await flushPromises()
    await w.get('.main-chart').trigger('contextmenu')
    expect(w.find('.driver-menu').exists()).toBe(false)
  })

  it('连续换股:只认最后一次请求的 K 线', async () => {
    let resolveSlow: (v: any) => void = () => {}
    vi.mocked(api.getAllOhlc)
      .mockImplementationOnce(() => new Promise((r) => { resolveSlow = r }))   // 先发的 SLOW 慢
      .mockImplementationOnce((s: string) => Promise.resolve({ symbol: s, bars: BARS.slice(0, 5) }))
    const view = useViewStore()
    mount(KlineChart)
    await flushPromises()
    view.openSymbol('SLOW')
    await flushPromises()
    view.openSymbol('FAST')
    await flushPromises()
    resolveSlow({ symbol: 'SLOW', bars: BARS })
    await flushPromises()
    const main = charts[0]
    const last = main.setOption.mock.calls.filter((c: any[]) => c[1] === true).at(-1)[0]
    expect(last.series.find((s: any) => s.name === 'kline').data).toHaveLength(5)
  })
})
