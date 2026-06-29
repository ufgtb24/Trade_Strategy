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
