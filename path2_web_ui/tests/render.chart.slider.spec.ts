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

describe('buildKlineOption — grid geometry follows sliderShow', () => {
  it('default (sliderShow undefined) keeps historical geometry: grid0 72%, grid1 top 76% / height 18%', () => {
    const opt: any = buildKlineOption(BARS, [], [], baseInput())
    expect(opt.grid[0].height).toBe('72%')
    expect(opt.grid[1].top).toBe('76%')
    expect(opt.grid[1].height).toBe('18%')
  })

  it('sliderShow=false expands grid0 to 80% and pushes grid1 to 84% / height 16% (主图+副图占满到底)', () => {
    const opt: any = buildKlineOption(BARS, [], [], { ...baseInput(), sliderShow: false })
    expect(opt.grid[0].height).toBe('80%')
    expect(opt.grid[1].top).toBe('84%')
    expect(opt.grid[1].height).toBe('16%')
  })

  it('sliderShow=true matches default geometry', () => {
    const opt: any = buildKlineOption(BARS, [], [], { ...baseInput(), sliderShow: true })
    expect(opt.grid[0].height).toBe('72%')
    expect(opt.grid[1].top).toBe('76%')
    expect(opt.grid[1].height).toBe('18%')
  })
})

describe('buildKlineOption — zoomOverride', () => {
  it('no zoomOverride → 走 strictWindow 默认(无 buffer = 全集 0..100)', () => {
    const opt: any = buildKlineOption(BARS, [], [], baseInput())
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
    expect(opt.dataZoom[1].start).toBe(0)
    expect(opt.dataZoom[1].end).toBe(100)
  })

  it('zoomOverride 传入则覆盖 strictWindow 默认(同时作用 inside + slider)', () => {
    const opt: any = buildKlineOption(BARS, [], [], {
      ...baseInput(),
      zoomOverride: { start: 30, end: 70 },
    })
    expect(opt.dataZoom[0].start).toBe(30)
    expect(opt.dataZoom[0].end).toBe(70)
    expect(opt.dataZoom[1].start).toBe(30)
    expect(opt.dataZoom[1].end).toBe(70)
  })

  it('zoomOverride=null → 等价于不传(走 strictWindow 默认)', () => {
    const opt: any = buildKlineOption(BARS, [], [], { ...baseInput(), zoomOverride: null })
    expect(opt.dataZoom[0].start).toBe(0)
    expect(opt.dataZoom[0].end).toBe(100)
  })
})
