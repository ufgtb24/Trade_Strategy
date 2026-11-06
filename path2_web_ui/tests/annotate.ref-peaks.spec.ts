// 参照层 peaks:峰线系列(深灰细实线,从峰那根画到第一次被突破的那根,不碰配色规范里有意义的颜色);
// 开关(默认关、只在 annotate / compare 下可用、换股票和切到 app 自动关、只认最后一次要的峰)。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { PEAK_LINE, PEAK_LINE_W, PEAKS_SERIES, peaksSeries } from '../src/render/refLayers'
import { INK } from '../src/render/annotateLanes'
import { REF_MODES, useRefLayerStore } from '../src/stores/refLayers'
import { useViewStore } from '../src/stores/view'
import * as api from '../src/api'

vi.mock('../src/api', () => ({
  getPeaks: vi.fn((symbol: string) => Promise.resolve(
    symbol === 'FLAT' ? [] : [{ date: '2025-01-03', price: 12, end: '2025-01-07' }])),
}))

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']

describe('峰线系列', () => {
  it('每个峰一条:从峰那根到 end 那根,高度是峰价;图上没有的日期跳过', () => {
    const s: any = peaksSeries(DATES, [
      { date: '2025-01-03', price: 12, end: '2025-01-07' },
      { date: '2025-01-06', price: 11, end: '2025-01-08' },
      { date: '2024-12-31', price: 13, end: '2025-01-06' },
    ])
    expect(s.name).toBe(PEAKS_SERIES)
    expect(s.data).toEqual([[1, 3, 12], [2, 4, 11]])
    const api = { coord: ([i, y]: number[]) => [i * 10 + 5, 100 - y], value: (k: number) => s.data[0][k] }
    const el = s.renderItem({}, api)
    expect(el).toEqual({ type: 'line', shape: { x1: 15, y1: 88, x2: 35, y2: 88 },
                         style: { stroke: PEAK_LINE, lineWidth: PEAK_LINE_W } })
    expect(el.style.lineDash).toBeUndefined()                   // 实线:虚线只表示用户画的
    expect(s.silent).toBe(true)
    expect(s.z).toBeGreaterThan(2)                              // 压在 K 线(z 2)上面
    expect(peaksSeries(DATES, []).data).toEqual([])
  })

  it('深灰,不是配色规范里有意义的颜色,也不是框和文字的黑', () => {
    const taken = ['#47b262', '#eb5454', '#93c5fd', '#f2c25c', '#d55e00', '#9ca3af', '#d1d5db', '#b4bac2', INK.toLowerCase()]
    expect(taken).not.toContain(PEAK_LINE.toLowerCase())
  })
})

describe('参照层开关', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it('默认关;打开 → 向后端要这只股票的峰', async () => {
    const view = useViewStore()
    const refs = useRefLayerStore()
    view.openSymbol('AAPL')
    expect(refs.peaks).toBe(false)
    expect(refs.available).toBe(true)
    void refs.setPeaks(true)
    expect(refs.status).toBe('loading')
    await flushPromises()
    expect(api.getPeaks).toHaveBeenCalledWith('AAPL')
    expect(refs.peaks).toBe(true)
    expect(refs.lines).toHaveLength(1)
    expect(refs.status).toBeNull()
    void refs.setPeaks(false)
    expect([refs.peaks, refs.lines, refs.status]).toEqual([false, [], null])
  })

  it('换股票自动关;同一只股票换一段不关', async () => {
    const view = useViewStore()
    const refs = useRefLayerStore()
    view.openSymbol('AAPL')
    await refs.setPeaks(true)
    view.openSymbol('AAPL', { start: '2025-01-02', end: '2025-01-08' })
    await flushPromises()
    expect(refs.peaks).toBe(true)
    view.openSymbol('MSFT')
    await flushPromises()
    expect([refs.peaks, refs.lines, refs.status]).toEqual([false, [], null])
  })

  it('只在 annotate / compare 下可用;切到 app 自动关,回来仍是关的', async () => {
    expect(REF_MODES).toEqual(['annotate', 'compare'])
    const view = useViewStore()
    const refs = useRefLayerStore()
    expect(refs.available).toBe(false)                          // 还没打开股票
    view.openSymbol('AAPL')
    await refs.setPeaks(true)
    view.selectSymbol('AAPL')                                    // 从扫描列表选股 = app
    await flushPromises()
    expect([refs.available, refs.peaks]).toEqual([false, false])
    await refs.setPeaks(true)                                    // app 下打不开
    expect(refs.peaks).toBe(false)
    expect(api.getPeaks).toHaveBeenCalledTimes(1)
    view.enterAnnotate()
    await flushPromises()
    expect([refs.available, refs.peaks]).toEqual([true, false])
  })

  it('没有峰 → empty;没要到 → load_failed', async () => {
    const view = useViewStore()
    const refs = useRefLayerStore()
    view.openSymbol('FLAT')
    await refs.setPeaks(true)
    expect([refs.peaks, refs.status]).toEqual([true, 'empty'])
    vi.mocked(api.getPeaks).mockImplementationOnce(() => Promise.reject(new Error('503')))
    view.openSymbol('DOWN')
    await refs.setPeaks(true)
    expect([refs.peaks, refs.lines, refs.status]).toEqual([true, [], 'load_failed'])
  })

  it('要的时候换了股票:回来的峰不用', async () => {
    let resolveSlow: (v: any) => void = () => {}
    vi.mocked(api.getPeaks).mockImplementationOnce(() => new Promise((r) => { resolveSlow = r }))
    const view = useViewStore()
    const refs = useRefLayerStore()
    view.openSymbol('SLOW')
    const pending = refs.setPeaks(true)
    view.openSymbol('MSFT')
    await flushPromises()
    resolveSlow([{ date: '2025-01-03', price: 12, end: '2025-01-07' }])
    await pending
    expect([refs.peaks, refs.lines, refs.status]).toEqual([false, [], null])
  })
})
