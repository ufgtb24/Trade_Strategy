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

  it('clamps displayBottom to >= 0 when priceMin < priceRange/8 (低价股 bug 防回归)', () => {
    // priceMin=1, priceMax=10 → range=9, displayHeight=11.25, raw displayBottom=1-1.125=-0.125
    // 钳前 yAxis 含 0 会触发 volume bar 双向；钳到 0 后 0 ≤ yAxis.min，bar 单向
    const bars = mkBars2([
      { o: 2, h: 3, l: 1, c: 2, v: 1000 },
      { o: 5, h: 10, l: 4, c: 8, v: 500 },
    ])
    const { yAxisOverride, volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 1)
    expect(yAxisOverride.min).toBe(0)
    expect(yAxisOverride.max).toBeCloseTo(11.25, 9)
    // 所有 bar value ≥ 0（与 0 baseline 同向、单向往上）
    expect(volSeries.data.every(d => d.value >= 0)).toBe(true)
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

  it('volume series uses borderColor black, borderWidth 0.5, opacity 0.5', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    const itemStyle = volSeries.data[0].itemStyle as any
    expect(itemStyle.borderColor).toBe('black')
    expect(itemStyle.borderWidth).toBe(0.5)
    expect(itemStyle.opacity).toBe(0.5)
  })

  it('volSeries config: type=bar, name=volume, xAxisIndex=0, yAxisIndex=0, barWidth=100%, z=3', () => {
    const bars = mkBars2([{ o: 10, h: 11, l: 9, c: 10, v: 100 }])
    const { volSeries } = buildVolumeSeriesAndYAxis(bars, 0, 0)
    expect(volSeries.type).toBe('bar')
    expect(volSeries.name).toBe('volume')
    expect(volSeries.xAxisIndex).toBe(0)
    expect(volSeries.yAxisIndex).toBe(0)
    expect(volSeries.barWidth).toBe('100%')
    expect(volSeries.z).toBe(3)
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

describe('buildBarTooltipFormatter', () => {
  // G2: Ctrl mode Price label 移到 yAxis[0].axisPointer.label.formatter,不再在此 formatter

  it('normal mode shows 9 lines with 2 inline <hr/> dividers (hr merged into Open/Chg)', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    const lines = html.split('<br/>')
    expect(lines).toHaveLength(9)
    expect(lines[0]).toBe('Date: 2024-01-02')
    expect(lines[1]).toBe('Index: 1')
    expect(lines[2]).toBe('<hr/>Open:  10.50')
    expect(lines[3]).toBe('High:  12.00')
    expect(lines[4]).toBe('Low:   10.00')
    expect(lines[5]).toBe('Close: 11.55')
    // Chg = (11.55 - 10.50) / 10.50 * 100 = 10.00%
    expect(lines[6]).toBe('<hr/>Chg:   +10.00%')
    expect(lines[7]).toBe('Volume: 1,500,000')
    expect(lines[8]).toBe('RV:    1.50')
  })

  it('first bar shows Chg=N/A (no prev close)', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    const html = fmt([{ seriesName: 'kline', dataIndex: 0 }])
    expect(html).toContain('Chg:   N/A')
  })

  it('RV<=0 shows RV=N/A', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    // bar[2].rv = 0
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toContain('RV:    N/A')
  })

  it('Chg negative shows minus sign', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    // bar[2]: (11.00 - 11.55) / 11.55 * 100 ≈ -4.76%
    const html = fmt([{ seriesName: 'kline', dataIndex: 2 }])
    expect(html).toMatch(/Chg:\s+-4\.76%/)
  })

  it('Volume formatted with US thousand separators', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    const html = fmt([{ seriesName: 'kline', dataIndex: 1 }])
    expect(html).toContain('Volume: 1,500,000')
  })

  it('returns empty string when no kline series in params', () => {
    const fmt = buildBarTooltipFormatter(mkBars3())
    const html = fmt([{ seriesName: 'other', dataIndex: 0 }])
    expect(html).toBe('')
  })
})

import { buildMarkerTooltipFormatter } from '../src/render/chart'
import type { TooltipPayload } from '../src/render/chart'

describe('buildMarkerTooltipFormatter', () => {
  const emptyPayload: TooltipPayload = {
    identity: { nodes: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
    clauses: [],
    raw: {},
  }

  it('非 match 端点 + 非空 payload 渲染身份段 + 段头 Identity', () => {
    const resolver = (_eid: string): TooltipPayload => emptyPayload
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('<b>Identity</b>')
    expect(html).toContain('node: bo_burst')
    expect(html).toContain('time: 2024-03-15')
    expect(html).toContain('id:   b1')
  })

  it('match 端点 + event 信息：顶行 + 三段拼接（不再互斥）', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { nodes: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [{ cid: 'first_drought', node: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false }],
      raw: { count: 2 },
    })
    const matchLabel = (id: string) => `MATCH:${id}`
    const fmt = buildMarkerTooltipFormatter(resolver, matchLabel)
    const html = fmt({ data: { event_id: 'b1', match_id: 'm1' } })
    expect(html).toContain('Match: MATCH:m1')
    expect(html).toContain('<b>Identity</b>')
    expect(html).toContain('<b>Clauses</b>')
    expect(html).toContain('<b>Attributes</b>')
  })

  it('失败 clause 用 <b>...</b> 加粗', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { nodes: ['bo_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'first_drought', node: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false },
        { cid: 'count', node: 'bo_burst', measured: 3, op: '>=', threshold: 2, satisfied: true },
      ],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('<b>first_drought: 0 >= 20 ✗</b>')
    expect(html).toContain('count: 3 >= 2 ✓')
    expect(html).not.toContain('<b>count:')   // 满足行不加粗
  })

  it('浮点截到 4 位小数（measured 与 threshold 双向）', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { nodes: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'vol_spike', node: 'bo_burst',
          measured: 2.6378544926831706, op: '>=', threshold: 8, satisfied: false },
      ],
      raw: { max_bar_vol_ratio: 2.6378544926831706 },
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('2.6379')   // measured 截位
    expect(html).not.toContain('2.6378544926831706')   // 原始精度不应出现
    expect(html).toContain('max_bar_vol_ratio: 2.6379')   // raw 段也截位
  })

  it('多 node 同 cid 行末加 (in: <node>)', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { nodes: ['bo_burst', 'tb_burst'], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [
        { cid: 'first_drought', node: 'bo_burst', measured: 0, op: '>=', threshold: 20, satisfied: false },
        { cid: 'first_drought', node: 'tb_burst', measured: 0, op: '>=', threshold: 0, satisfied: true },
        { cid: 'count', node: 'bo_burst', measured: 3, op: '>=', threshold: 2, satisfied: true },
      ],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).toContain('first_drought: 0 >= 20 ✗ (in: bo_burst)')
    expect(html).toContain('first_drought: 0 >= 0 ✓ (in: tb_burst)')
    expect(html).toContain('count: 3 >= 2 ✓')
    expect(html).not.toContain('count: 3 >= 2 ✓ (in:')   // 单 node 不加后缀
  })

  it('零 node 时 identity.node 行省略', () => {
    const resolver = (_eid: string): TooltipPayload => ({
      identity: { nodes: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [],
      raw: {},
    })
    const fmt = buildMarkerTooltipFormatter(resolver, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('node:')
    expect(html).toContain('time: 2024-03-15')
    expect(html).toContain('id:   b1')
  })

  it('point 事件 time 单日期；区间事件 time 带箭头', () => {
    const resolverPoint = (_eid: string): TooltipPayload => ({
      identity: { nodes: [], dateStart: '2024-03-15', dateEnd: null, eventId: 'b1' },
      clauses: [], raw: {},
    })
    const resolverRange = (_eid: string): TooltipPayload => ({
      identity: { nodes: [], dateStart: '2024-03-15', dateEnd: '2024-03-30', eventId: 'b1' },
      clauses: [], raw: {},
    })
    expect(buildMarkerTooltipFormatter(resolverPoint, undefined)({ data: { event_id: 'b1' } }))
      .toContain('time: 2024-03-15')
    expect(buildMarkerTooltipFormatter(resolverPoint, undefined)({ data: { event_id: 'b1' } }))
      .not.toContain('→')
    expect(buildMarkerTooltipFormatter(resolverRange, undefined)({ data: { event_id: 'b1' } }))
      .toContain('time: 2024-03-15 → 2024-03-30')
  })

  it('clauses 段为空时段头 Clauses 不渲染', () => {
    const fmt = buildMarkerTooltipFormatter((_eid) => emptyPayload, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('<b>Clauses</b>')
  })

  it('raw 段为空时段头 Attributes 不渲染', () => {
    const fmt = buildMarkerTooltipFormatter((_eid) => emptyPayload, undefined)
    const html = fmt({ data: { event_id: 'b1' } })
    expect(html).not.toContain('<b>Attributes</b>')
  })

  it('match 端点但 matchLabel 返回 null 时不渲染顶行', () => {
    const resolver = (_eid: string): TooltipPayload => emptyPayload
    const matchLabel = (_id: string) => null
    const fmt = buildMarkerTooltipFormatter(resolver, matchLabel)
    const html = fmt({ data: { event_id: 'b1', match_id: 'm1' } })
    expect(html).not.toContain('Match:')
    expect(html).toContain('<b>Identity</b>')   // 但 event 三段仍渲染
  })

  it('params 为 null 或 data 缺失返回空串', () => {
    const fmt = buildMarkerTooltipFormatter(undefined, undefined)
    expect(fmt(null)).toBe('')
    expect(fmt({ data: undefined })).toBe('')
  })
})
