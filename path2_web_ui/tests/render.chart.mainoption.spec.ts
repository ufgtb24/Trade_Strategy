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
    nodeColors: {},
    eventTier: () => 'matched',
    nodeOfEventByBand: () => null,
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

describe('buildMainOption — y 轴窗口跟随 zoomOverride(修 zoom-in 后 render 留白 bug)', () => {
  // 前低后高、价差悬殊的 10 根 bars:低价前段 h=2、高价后段 h=100。
  // 复现「zoom-in 到低价前段后全量 render → y 轴却按全窗 high 算 → K 线压底留白」。
  const wideBars: Bar[] = Array.from({ length: 10 }, (_, i) => {
    const lo = i < 5 ? 1 : 50
    const hi = i < 5 ? 2 : 100
    return { date: `2024-02-${String(i + 1).padStart(2, '0')}`, o: lo, h: hi, l: lo, c: hi, v: 100, rv: 1 }
  })
  const wideBundle = (input: BandRenderInput) => computeEventData(wideBars, [], [], input)

  it('zoomOverride 圈定低价前段 → yAxis.max 贴合可见窗(不回跳全局 high)', () => {
    // 可见窗 idx 0..3 全在低价段(h=2):displayHeight=(2-1)/0.8=1.25,
    // displayBottom=max(0,1-0.125)=0.875,displayTop=2.125。全局 high=100 → 全窗 max=123.75。
    const input = baseInput({ zoomOverride: { start: 0, end: 40 } })
    const opt: any = buildMainOption(wideBars, wideBundle(input), input)
    expect(opt.yAxis[0].max).toBeLessThan(10)          // 不得回跳到全局 high(123.75)
    expect(opt.yAxis[0].max).toBeCloseTo(2.125, 6)     // 贴合可见窗
  })

  it('无 zoomOverride → yAxis 覆盖全窗(既有行为不变)', () => {
    const input = baseInput()
    const opt: any = buildMainOption(wideBars, wideBundle(input), input)
    expect(opt.yAxis[0].max).toBeCloseTo(123.75, 6)    // 全窗 displayTop
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

describe('buildMainOption — symbolLabel title (K 线图内嵌 symbol,居中)', () => {
  it('symbolLabel="AAPL" → title.text="AAPL",left="center",top=6', () => {
    const input = baseInput({ symbolLabel: 'AAPL' })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect(opt.title).toBeDefined()
    expect(opt.title.text).toBe('AAPL')
    expect(opt.title.left).toBe('center')
    expect(opt.title.top).toBe(6)
  })

  it('symbolLabel=null → return 对象不含 title key(隐藏)', () => {
    const input = baseInput({ symbolLabel: null })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect('title' in opt).toBe(false)
  })

  it('symbolLabel="" 空字符串 → return 对象不含 title key(隐藏)', () => {
    const input = baseInput({ symbolLabel: '' })
    const opt: any = buildMainOption(bars, mkBundle(input), input)
    expect('title' in opt).toBe(false)
  })
})
