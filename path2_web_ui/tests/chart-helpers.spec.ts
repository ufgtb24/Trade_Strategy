import { describe, it, expect } from 'vitest'
import { buildShadingMarkArea } from '../src/render/chart'
import type { Bar } from '../src/types'

function mkBars(dates: string[]): Bar[] {
  return dates.map(d => ({ date: d, o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 }))
}

describe('buildShadingMarkArea', () => {
  it('returns null when scan window covers entire bars range', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-03')
    expect(out).toBeNull()
  })

  it('returns null when scan window covers a single bar exactly', () => {
    const bars = mkBars(['2024-01-01'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-01')
    expect(out).toBeNull()
  })

  it('returns left segment only when only left buffer exists', () => {
    // bars: [..., bar2(scan_start), bar3(scan_end)]
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'])
    const out = buildShadingMarkArea(bars, '2024-01-03', '2024-01-04')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(1)
    // 左段闭区间 [0, startIdx-1] = [0, 1]
    expect(out!.data[0][0]).toEqual({ xAxis: 0 })
    expect(out!.data[0][1]).toEqual({ xAxis: 1 })
  })

  it('returns right segment only when only right buffer exists', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'])
    const out = buildShadingMarkArea(bars, '2024-01-01', '2024-01-02')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(1)
    // 右段 [endIdx+1, last] = [2, 3]
    expect(out!.data[0][0]).toEqual({ xAxis: 2 })
    expect(out!.data[0][1]).toEqual({ xAxis: 3 })
  })

  it('returns both segments with off-by-one fix (startIdx/endIdx themselves in white)', () => {
    const bars = mkBars([
      '2024-01-01', '2024-01-02',                       // 左 buffer
      '2024-01-03', '2024-01-04', '2024-01-05',         // scan 窗
      '2024-01-06', '2024-01-07',                       // 右 buffer
    ])
    const out = buildShadingMarkArea(bars, '2024-01-03', '2024-01-05')
    expect(out).not.toBeNull()
    expect(out!.data).toHaveLength(2)
    // 左段 [0, 1] — 即 startIdx-1=1，bar[2](scan_start) 在白区
    expect(out!.data[0]).toEqual([{ xAxis: 0 }, { xAxis: 1 }])
    // 右段 [5, 6] — 即 endIdx+1=5，bar[4](scan_end) 在白区
    expect(out!.data[1]).toEqual([{ xAxis: 5 }, { xAxis: 6 }])
  })

  it('shading itemStyle is dev grey #808080 alpha 0.15', () => {
    const bars = mkBars(['2024-01-01', '2024-01-02', '2024-01-03'])
    const out = buildShadingMarkArea(bars, '2024-01-02', '2024-01-02')
    expect(out).not.toBeNull()
    expect(out!.itemStyle).toEqual({ color: '#808080', opacity: 0.15 })
  })
})

import { buildVolumeSeriesAndYAxis } from '../src/render/chart'

function mkBars2(items: Array<{ o: number; h: number; l: number; c: number; v: number }>): Bar[] {
  return items.map((b, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    o: b.o, h: b.h, l: b.l, c: b.c, v: b.v, rv: 1,
  }))
}

describe('buildVolumeSeriesAndYAxis', () => {
  it('uses visible-range vol_max for scale (not full bars max)', () => {
    const bars = mkBars2([
      { o: 10, h: 12, l: 9, c: 11, v: 1000 },   // visible
      { o: 11, h: 13, l: 10, c: 12, v: 2000 },  // visible
      { o: 12, h: 14, l: 11, c: 13, v: 5000 },  // NOT visible (big volume should NOT affect scale)
    ])
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, 0, 1)
    // displayHeight = priceRange / 0.8 = (13 - 9) / 0.8 = 5
    // displayBottom = 9 - 5 * 0.1 = 8.5
    // visVolMax = max(1000, 2000) = 2000
    // volScale = 5 * 0.2 / 2000 = 0.0005
    expect(yAxisOverride.min).toBeCloseTo(8.5, 9)
    expect(yAxisOverride.max).toBeCloseTo(13.5, 9)
    // bar[0]: value = 8.5 + 1000 * 0.0005 = 9.0
    expect(volSeries.data[0].value).toBeCloseTo(9.0, 9)
    // bar[1]: value = 8.5 + 2000 * 0.0005 = 9.5
    expect(volSeries.data[1].value).toBeCloseTo(9.5, 9)
    // bar[2] uses same scale (full bars data exists but viz uses visible scale)
    expect(volSeries.data[2].value).toBeCloseTo(8.5 + 5000 * 0.0005, 9)
  })

  it('color is up-grey when close>=open, down-grey when close<open', () => {
    const bars = mkBars2([
      { o: 10, h: 11, l: 9, c: 10, v: 100 },   // close==open => up
      { o: 10, h: 11, l: 9, c: 9.5, v: 100 },  // close<open => down
      { o: 10, h: 11, l: 9, c: 10.5, v: 100 }, // close>open => up
    ])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 2)
    expect((volSeries.data[0].itemStyle as any).color).toBe('#D3D3D3')
    expect((volSeries.data[1].itemStyle as any).color).toBe('#696969')
    expect((volSeries.data[2].itemStyle as any).color).toBe('#D3D3D3')
  })

  it('does not throw when vol_max is 0 (all-zero visible volumes)', () => {
    const bars = mkBars2([
      { o: 10, h: 11, l: 9, c: 10, v: 0 },
      { o: 10, h: 11, l: 9, c: 10, v: 0 },
    ])
    expect(() => buildVolumeSeriesAndYAxis(bars, 0, 1)).not.toThrow()
    const { volSeries, yAxisOverride } = buildVolumeSeriesAndYAxis(bars, 0, 1)
    // 兜底 visVolMax=1, 所有 value = displayBottom
    expect(volSeries.data.every(d => d.value === yAxisOverride.min)).toBe(true)
  })

  it('volume series uses borderColor black, borderWidth 0.5, opacity 0.8', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    const itemStyle = volSeries.data[0].itemStyle as any
    expect(itemStyle.borderColor).toBe('black')
    expect(itemStyle.borderWidth).toBe(0.5)
    expect(itemStyle.opacity).toBe(0.8)
  })

  it('volSeries config: type=bar, name=volume, xAxisIndex=0, yAxisIndex=0, barWidth=100%, z=1', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    expect(volSeries.type).toBe('bar')
    expect(volSeries.name).toBe('volume')
    expect(volSeries.xAxisIndex).toBe(0)
    expect(volSeries.yAxisIndex).toBe(0)
    expect(volSeries.barWidth).toBe('100%')
    expect(volSeries.z).toBe(1)
  })
})

import { buildBarTooltipFormatter } from '../src/render/chart'

function mkBars3(): Bar[] {
  return [
    { date: '2024-01-01', o: 10.00, h: 11.00, l: 9.00, c: 10.50, v: 1000, rv: 0 },
    { date: '2024-01-02', o: 10.50, h: 12.00, l: 10.00, c: 11.55, v: 1500000, rv: 1.5 },
    { date: '2024-01-03', o: 11.55, h: 11.60, l: 10.80, c: 11.00, v: 800000, rv: 0 },
  ]
}

function mkCtrlState(pressed: boolean, y: number) {
  return { isPressed: () => pressed, mouseY: () => y }
}

describe('buildBarTooltipFormatter', () => {
  it('Ctrl mode returns single line "Price: {mouseY}" with 2 decimals', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(true, 12.345))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    expect(html).toBe('Price: 12.35')
  })

  it('normal mode shows 8 lines: Date/Open/High/Low/Close/Chg/Volume/RV', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    const lines = html.split('<br/>')
    expect(lines).toHaveLength(8)
    expect(lines[0]).toBe('Date: 2024-01-02')
    expect(lines[1]).toBe('Open:  10.50')
    expect(lines[2]).toBe('High:  12.00')
    expect(lines[3]).toBe('Low:   10.00')
    expect(lines[4]).toBe('Close: 11.55')
    // Chg = (11.55 - 10.50) / 10.50 * 100 = 10.00%
    expect(lines[5]).toBe('Chg:   +10.00%')
    expect(lines[6]).toBe('Volume: 1,500,000')
    expect(lines[7]).toBe('RV:    1.50')
  })

  it('first bar shows Chg=N/A (no prev close)', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 0 }])
    expect(html).toContain('Chg:   N/A')
  })

  it('RV<=0 shows RV=N/A', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    // bar[2].rv = 0
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toContain('RV:    N/A')
  })

  it('Chg negative shows minus sign', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    // bar[2]: (11.00 - 11.55) / 11.55 * 100 ≈ -4.76%
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toMatch(/Chg:\s+-4\.76%/)
  })

  it('Volume formatted with US thousand separators', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    expect(html).toContain('Volume: 1,500,000')
  })

  it('returns empty string when no kline series in params', () => {
    const fmt = buildBarTooltipFormatter(mkBars3(), mkCtrlState(false, 0))
    const html = fmt([{ seriesName: 'other', dataIndex: 0 }])
    expect(html).toBe('')
  })
})

import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { TooltipPayload } from '../src/render/chart'

describe('buildMarkerTooltipFormatter', () => {
  it('returns matchLabel when params.data has match_id', () => {
    const matchLabel = (id: string) => `MATCH:${id}`
    const fmt = buildMarkerTooltipFormatter(undefined, matchLabel)
    expect(fmt({ data: { match_id: 'm1' } })).toBe('MATCH:m1')
  })

  it('uses tooltipResolver clauses + raw, excludes "members" key', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      clauses: { c1: { measured: 5, op: '>=', threshold: 3, satisfied: true } },
      raw: { foo: 'bar', members: [1, 2, 3] },
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'e1' } })
    expect(html).toContain('c1: 5 >= 3 ✓')
    expect(html).toContain('foo: bar')
    expect(html).not.toContain('members')
  })

  it('returns empty when no event_id and no resolver', () => {
    const fmt = buildMarkerTooltipFormatter(undefined, undefined)
    expect(fmt({ data: {} })).toBe('')
  })
})
