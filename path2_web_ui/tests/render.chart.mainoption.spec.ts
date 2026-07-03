// render.chart.mainoption.spec.ts — sliderShow / zoomOverride / strictWindow on buildMainOption
// (Task 6 review fix group 5; 恢复自 95f5554 版 render.chart.slider.spec.ts,原测试对象是已删除
//  的 buildKlineOption 单函数,行为现活在 buildMainOption/buildSubOption — 主体已换成 chartMain,
//  故本文件不再叫 "slider",改名反映新调用对象。)
import { describe, it, expect } from 'vitest'
import { computeEventData, buildMainOption, buildSubOption } from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { computeSubGeometry } from '../src/render/subGeometry'
import type { Bar, Topology } from '../src/types'

const bars: Bar[] = [
  { date: '2024-01-01', o: 1, h: 2, l: 1, c: 2, v: 100, rv: 0.1 },
  { date: '2024-01-02', o: 2, h: 3, l: 2, c: 3, v: 200, rv: 0.2 },
  { date: '2024-01-03', o: 2, h: 3, l: 2, c: 3, v: 150, rv: 0.15 },
]

function baseInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
  return {
    topology: { nodes: [], edges: [] } as Topology,
    isolatedNodeIds: new Set(),
    tagList: [],
    level: 'matched',
    roleColors: {},
    eventTier: () => 'matched',
    roleOfEventByBand: () => null,
    bandKeyOf: () => '',
    ...overrides,
  }
}

function mkBundle(input: BandRenderInput) {
  return computeEventData(bars, [], [], input)
}

describe('buildMainOption — sliderShow toggles dataZoom[1].show + grid[0].bottom (chart.ts:309,342)', () => {
  it('sliderShow=true → dataZoom[1].show=true, grid[0].bottom=60', () => {
    const input = baseInput({ sliderShow: true })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(true)
    expect(opt.grid[0].bottom).toBe(60)
  })

  it('sliderShow=false → dataZoom[1].show=false, grid[0].bottom=20', () => {
    const input = baseInput({ sliderShow: false })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(false)
    expect(opt.grid[0].bottom).toBe(20)
  })

  it('sliderShow undefined → 默认等价 true(向后兼容,show=true, bottom=60)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[1].show).toBe(true)
    expect(opt.grid[0].bottom).toBe(60)
  })
})

describe('buildMainOption / buildSubOption — zoomOverride passthrough (chart.ts:274-275,378-379)', () => {
  it('无 zoomOverride → 走 strictWindow 默认(无 buffer = 全集 0..100)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
  })

  it('zoomOverride={start,end} → dataZoom[0].start/end 在 buildMainOption 与 buildSubOption 上均 passthrough', () => {
    const input = baseInput({ zoomOverride: { start: 30, end: 70 } })
    const bundle = mkBundle(input)
    const mainOpt: any = buildMainOption(bars, bundle, input)
    expect(mainOpt.dataZoom[0].start).toBe(30)
    expect(mainOpt.dataZoom[0].end).toBe(70)

    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const subOpt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    expect(subOpt.dataZoom[0].start).toBe(30)
    expect(subOpt.dataZoom[0].end).toBe(70)
  })

  it('zoomOverride=null → 等价于不传(走 strictWindow 默认)', () => {
    const input = baseInput({ zoomOverride: null })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
  })
})

describe('buildMainOption — strictWindow markArea shading (chart.ts:280,287)', () => {
  it('strictWindow 存在 → kline 系列带 markArea 灰阴影', () => {
    const input = baseInput({ strictWindow: { startIdx: 1, endIdx: 1 } })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    const kline = opt.series.find((s: any) => s.name === 'kline')
    expect(kline.markArea).toBeDefined()
    expect(kline.markArea.data.length).toBeGreaterThanOrEqual(1)
  })

  it('strictWindow 缺省 → kline 系列无 markArea(老行为)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    const kline = opt.series.find((s: any) => s.name === 'kline')
    expect(kline.markArea).toBeUndefined()
  })
})

describe('S1 fix: chartSub tooltip 挂 body + 删 markerTooltip 系列级冗余', () => {
  it('chartSub 顶层 tooltip 有 appendToBody: true + confine: true', () => {
    const input = baseInput()
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const option: any = buildSubOption(bars, mkBundle(input), subGeom, input, 800)
    expect((option.tooltip as any).appendToBody).toBe(true)
    expect((option.tooltip as any).confine).toBe(true)
  })

  it('chartSub 所有系列级 markerTooltip 不含 appendToBody(v5 系列级不生效,冗余删)', () => {
    const input = baseInput()
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const option: any = buildSubOption(bars, mkBundle(input), subGeom, input, 800)
    for (const s of (option.series || []) as any[]) {
      if (s.tooltip) {
        expect('appendToBody' in s.tooltip).toBe(false)
      }
    }
  })

  it('chartMain 所有系列级 markerTooltip 不含 appendToBody', () => {
    const input = baseInput()
    const option: any = buildMainOption(bars, mkBundle(input), input)
    for (const s of (option.series || []) as any[]) {
      if (s.tooltip) {
        expect('appendToBody' in s.tooltip).toBe(false)
      }
    }
  })
})
