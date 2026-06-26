// chart.spec.ts — 新签名测试(3-grid + band×lane + bo 密度层 + bandLabels + 三档 level 门控)
// 内联 5-node fixture,自包含,不依赖外部 ANALYSIS。
import { describe, it, expect } from 'vitest'
import { buildKlineOption, type BandRenderInput } from '../src/render/chart'
import { colorOf } from '../src/render/colors'
import {
  bandKeyOf, roleOfEventByBand, deriveTagMap, isolatedNodeIds, eventTierOf, matchedIds,
  renderGridOf,
} from '../src/render/visible'
import type { Topology, EventDict, MatchDict, Level, Bar } from '../src/types'

// ── 5-node topology ────────────────────────────────────────────────────────
const TOPOLOGY: Topology = {
  nodes: [
    { node_id: 'down',  class_id: 'trend', label: '下跌段', source_tag: 'trend0', where_rules: [] },
    { node_id: 'side',  class_id: 'trend', label: '横盘段', source_tag: 'trend1', where_rules: [] },
    { node_id: 'bo',    class_id: 'bo',    label: '',       source_tag: 'bo',
      render_grid: 'price',                                              // ★ 新增
      where_rules: [] },
    { node_id: 'burst', class_id: 'burst', label: '爆发段', source_tag: 'burst',  where_rules: [] },
    { node_id: 'tb',    class_id: 'tb',    label: '回踩',   source_tag: 'tb',     where_rules: [] },
  ],
  edges: [
    { src: 'down',  dst: 'burst', kind: 'TemporalEdge',    rule: 'before' },
    { src: 'side',  dst: 'burst', kind: 'ContainmentEdge', rule: 'contains' },
    { src: 'burst', dst: 'tb',    kind: 'TemporalEdge',    rule: 'gap=1' },
    // bo 节点孤立(无边):isolated
  ],
}

// ── events ─────────────────────────────────────────────────────────────────
const EVENTS: EventDict[] = [
  // intervals
  { class_id: 'trend', event_id: 'down1',  source_tag: 'trend0', start_idx: 1,  end_idx: 6  },
  { class_id: 'trend', event_id: 'side1',  source_tag: 'trend1', start_idx: 4,  end_idx: 12 },
  { class_id: 'burst', event_id: 'burst1', source_tag: 'burst',  start_idx: 10, end_idx: 15 },
  // points: bo(多个)
  { class_id: 'bo', event_id: 'bo9',  source_tag: 'bo', start_idx: 9,  end_idx: 9,
    referenced_points: [[5, 12.5, 'pk0'], [7, 13.0, 'pk1']] },
  { class_id: 'bo', event_id: 'bo11', source_tag: 'bo', start_idx: 11, end_idx: 11 },
  // tb point
  { class_id: 'tb', event_id: 'tb16', source_tag: 'tb', start_idx: 16, end_idx: 16 },
  // detected-only: 未匹配、未 qualified
  { class_id: 'bo', event_id: 'boX',  source_tag: 'bo', start_idx: 20, end_idx: 20 },
]

// ── matches ────────────────────────────────────────────────────────────────
const MATCHES: MatchDict[] = [
  {
    event_id: 'm1', start_idx: 1, end_idx: 16,
    role_index: { down: 'down1', side: 'side1', burst: 'burst1', tb: 'tb16' },
    children: ['down1', 'side1', 'burst1', 'tb16'],
    predicate_trace: { where_results: {}, edge_results: {} },
  },
]

// ── helper: build BandRenderInput ─────────────────────────────────────────
function makeInput(level: Level, roleColors: Record<string, string>): BandRenderInput {
  const { tagToNodes, tagList } = deriveTagMap(TOPOLOGY.nodes)
  const isolated = isolatedNodeIds(TOPOLOGY)
  const mIds = matchedIds(MATCHES)
  const qualifiedIds = new Set<string>()   // 无 diag → 无 qualified events

  return {
    topology: TOPOLOGY,
    isolatedNodeIds: isolated,
    tagList,
    level,
    roleColors,
    eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
    roleOfEventByBand: (e) => roleOfEventByBand(e, tagToNodes, tagList),
    bandKeyOf: (e) => bandKeyOf(e, tagList),
  }
}

const bars = Array.from({ length: 22 }, (_, i) => ({
  date: `2025-01-${String(i + 1).padStart(2, '0')}`,
  o: 10 + i, h: 11 + i, l: 9 + i, c: 10.5 + i, v: 1000 + i, rv: 0,
}))
const roleColors = { down: '#d97706', side: '#fbbf24', burst: '#7c3aed', tb: '#16a34a' }

// Task 7: grid 3→2。旧"3-grid band×lane"测试更新至新 2-grid 架构。
describe('buildKlineOption — 2-grid band×lane (Task 7)', () => {
  const input = makeInput('detected', roleColors)
  const opt = buildKlineOption(bars, EVENTS, MATCHES, input)
  const series = opt.series as any[]
  const S = (name: string) => series.find((s: any) => s.name === name)

  // ── 1. grid / dataZoom 结构 ──────────────────────────────────────────────
  it('has 2 grids (grid0 价格+volume叠加, grid1 markers)', () => {
    expect((opt.grid as any[]).length).toBe(2)
  })

  it('dataZoom links 2 xAxis (no buffer → start=0, end=100)', () => {
    const dz = opt.dataZoom as any[]
    expect(dz[0].xAxisIndex).toEqual([0, 1])
    expect(dz[1].xAxisIndex).toEqual([0, 1])
    // 无 strictWindow → start=0, end=100
    expect(dz[0].start).toBe(0)
    expect(dz[0].end).toBe(100)
  })

  // ── 2. candlestick data 格式 ─────────────────────────────────────────────
  it('candlestick data=[o,c,l,h]', () => {
    const candle = S('kline')
    expect(candle.data[0]).toEqual([bars[0].o, bars[0].c, bars[0].l, bars[0].h])
  })

  it('volume bound to grid0 (xAxisIndex=0, yAxisIndex=0) via buildVolumeSeriesAndYAxis', () => {
    const vol = S('volume')
    expect(vol.xAxisIndex).toBe(0)
    expect(vol.yAxisIndex).toBe(0)
  })

  // ── 3. yAxis 结构 ────────────────────────────────────────────────────────
  it('has 3 yAxes: price+volume(0) + hidden-bracket(1) + hidden-marker(2)', () => {
    const yAxis = opt.yAxis as any[]
    expect(yAxis.length).toBe(3)
    // 价格轴 grid0 (含 volume 叠加 min/max)
    expect(yAxis[0].gridIndex).toBe(0)
    // hidden bracket 轴 grid0
    expect(yAxis[1].gridIndex).toBe(0)
    expect(yAxis[1].show).toBe(false)
    // hidden marker 轴 grid1
    expect(yAxis[2].gridIndex).toBe(1)
    expect(yAxis[2].show).toBe(false)
  })

  it('kline binds price yAxis(0); points/intervals bind hidden-marker yAxis(2); brackets bind hidden-bracket yAxis(1)', () => {
    expect(S('kline').yAxisIndex).toBe(0)
    expect(S('points').yAxisIndex).toBe(2)
    expect(S('intervals').yAxisIndex).toBe(2)
    expect(S('brackets').yAxisIndex).toBe(1)
  })

  it('points/intervals/bandLabels use grid1 xAxis(1); brackets use grid0 xAxis(0)', () => {
    expect(S('points').xAxisIndex).toBe(1)
    expect(S('intervals').xAxisIndex).toBe(1)
    expect(S('bandLabels').xAxisIndex).toBe(1)
    expect(S('brackets').xAxisIndex).toBe(0)
  })

  // ── 4. intervals value 含 [start, end, lane, band, nBands] ───────────────
  it('interval value=[start_idx, end_idx, lane, band, nBands]', () => {
    const iv = S('intervals')
    const down1 = (iv.data as any[]).find((d: any) => d.event_id === 'down1')
    expect(down1).toBeDefined()
    expect(down1.value[0]).toBe(1)                     // start_idx
    expect(down1.value[1]).toBe(6)                     // end_idx
    expect(typeof down1.value[2]).toBe('number')        // lane
    expect(typeof down1.value[3]).toBe('number')        // band
    expect(typeof down1.value[4]).toBe('number')        // nBands
    // nBands = tagList.length = 5 (trend0/trend1/bo/burst/tb)
    expect(down1.value[4]).toBe(5)
    // band = tagList.indexOf('trend0') = 0
    expect(down1.value[3]).toBe(0)
  })

  // ── 5. points value 含 [start, start, band, nBands] (tb16 example, bo goes to price-points) ──
  it('point value=[start_idx, start_idx, band, nBands]', () => {
    const pts = S('points')
    // bo9 is render_grid='price' → goes to price-points, not here; use tb16 as example
    const tb16 = (pts.data as any[]).find((d: any) => d.event_id === 'tb16')
    expect(tb16).toBeDefined()
    expect(tb16.value[0]).toBe(16)    // start_idx
    expect(tb16.value[1]).toBe(16)    // start_idx (same as end for point)
    expect(typeof tb16.value[2]).toBe('number')   // band
    expect(typeof tb16.value[3]).toBe('number')   // nBands
    // tb band = tagList.indexOf('tb') = 4
    expect(tb16.value[2]).toBe(4)
    expect(tb16.value[3]).toBe(5)
    // price-points series has bo9 with value=[start_idx, y_price]
    const pp = S('price-points')
    const bo9 = (pp.data as any[]).find((d: any) => d.event_id === 'bo9')
    expect(bo9).toBeDefined()
    expect(bo9.value[0]).toBe(9)
  })

  // ── 6. brackets count == matches.length ──────────────────────────────────
  it('brackets data.length == matches.length, ordinal=1 for first', () => {
    const br = S('brackets')
    expect(br.data.length).toBe(MATCHES.length)
    expect((br.data as any[])[0].value[3]).toBe(1)  // ordinal 1-based
  })

  // ── 7. bandLabels series 存在,文字来自 topology.nodes ────────────────────
  it('bandLabels series exists with label text from topology.nodes', () => {
    const bl = S('bandLabels')
    expect(bl).toBeDefined()
    // tagList=[trend0,trend1,bo,burst,tb],共 5 条 label
    expect((bl.data as any[]).length).toBe(5)
    // bo label='' → 显示 'bo'(node.label || node.node_id)
    const boLabel = (bl.data as any[]).find((d: any) => d.text === 'bo')
    expect(boLabel).toBeDefined()
    // down label='下跌段'
    const downLabel = (bl.data as any[]).find((d: any) => d.text === '下跌段')
    expect(downLabel).toBeDefined()
  })

  // ── 8. colorOf 接入:matched interval 的色 === roleColors[其 band-role] ───
  it('matched interval color == roleColors[role]', () => {
    const iv = S('intervals')
    const down1 = (iv.data as any[]).find((d: any) => d.event_id === 'down1')
    // down1 是 matched,roleOfEventByBand → 'down' → roleColors['down']='#d97706'
    expect(down1.itemStyle.color).toBe(roleColors['down'])
  })

  it('matched point (tb16) color == roleColors[tb]', () => {
    const pts = S('points')
    const tb16 = (pts.data as any[]).find((d: any) => d.event_id === 'tb16')
    expect(tb16.itemStyle.color).toBe(roleColors['tb'])
  })

  // ── 9. detected-only event 的 colorOf → 浅灰(detected tier) ─────────────
  it('detected-only event boX gets detected color (#d1d5db) at level=detected', () => {
    // boX is render_grid='price' → goes to price-points (not grid2 points)
    const pp = S('price-points')
    const boX = (pp.data as any[]).find((d: any) => d.event_id === 'boX')
    expect(boX).toBeDefined()
    // colorOf('detected', ...) = '#d1d5db'
    expect(boX.itemStyle.color).toBe(colorOf('detected', null, roleColors))
    expect(boX.itemStyle.color).toBe('#d1d5db')
  })

  // ── 10. level 门控 teeth ──────────────────────────────────────────────────
  it('level=matched: detected-only event boX is not rendered', () => {
    const input2 = makeInput('matched', roleColors)
    const opt2 = buildKlineOption(bars, EVENTS, MATCHES, input2)
    const pts = (opt2.series as any[]).find((s: any) => s.name === 'points')
    const boX = (pts.data as any[]).find((d: any) => d.event_id === 'boX')
    expect(boX).toBeUndefined()   // level 门控:detected 不画
  })

  it('level=detected: all events rendered including boX', () => {
    // boX is render_grid='price' → goes to price-points, not grid2 points
    const pp = S('price-points')
    const boX = (pp.data as any[]).find((d: any) => d.event_id === 'boX')
    expect(boX).toBeDefined()
  })

  it('level=matched: only matched events present (intervals contain down1,side1,burst1)', () => {
    const input2 = makeInput('matched', roleColors)
    const opt2 = buildKlineOption(bars, EVENTS, MATCHES, input2)
    const iv = (opt2.series as any[]).find((s: any) => s.name === 'intervals')
    const ids = (iv.data as any[]).map((d: any) => d.event_id)
    expect(ids).toContain('down1')
    expect(ids).toContain('side1')
    expect(ids).toContain('burst1')
    // bo9/bo11 是 matched(在 children 里 → 但 role_index 里 bo 不在 MATCHES的 role_index ─ 实际 bo 不在5-node MATCHES里)
    // 检查 boX 不在点数据里
    const pts = (opt2.series as any[]).find((s: any) => s.name === 'points')
    const ptIds = (pts.data as any[]).map((d: any) => d.event_id)
    expect(ptIds).not.toContain('boX')
  })

  // ── 11. pointData / pricePointData / intervalData 含 event_id(click 分支依赖) ─
  it('price-points items carry event_id (click branch depends on it)', () => {
    // bo9 is render_grid='price' → in price-points series
    const pp = S('price-points')
    const bo9 = (pp.data as any[]).find((d: any) => d.event_id === 'bo9')
    expect(bo9).toBeDefined()
    expect(bo9.event_id).toBe('bo9')
  })

  it('intervalData items carry event_id (click branch depends on it)', () => {
    const iv = S('intervals')
    const down1 = (iv.data as any[]).find((d: any) => d.event_id === 'down1')
    expect(down1).toBeDefined()
    expect(down1.event_id).toBe('down1')
  })
})

// ── D2: highlight overlay ─────────────────────────────────────────────────────
describe('buildKlineOption — D2 highlight overlay', () => {
  const baseInput = makeInput('detected', roleColors)

  it('no highlight series data when selectedEventId=null', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: null })
    const hl = (opt.series as any[]).find((s: any) => s.name === 'highlight')
    // series 存在但 data 应为空
    expect(hl).toBeDefined()
    expect((hl.data as any[]).length).toBe(0)
  })

  it('no highlight series data when selectedEventId is unknown', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: 'nonexistent_id' })
    const hl = (opt.series as any[]).find((s: any) => s.name === 'highlight')
    expect(hl).toBeDefined()
    expect((hl.data as any[]).length).toBe(0)
  })

  it('highlight-price series has z higher than price-points and satellites when selectedEventId matches a bo event', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: 'bo9' })
    const series = opt.series as any[]
    const hlPrice = series.find((s: any) => s.name === 'highlight-price')
    const pp = series.find((s: any) => s.name === 'price-points')
    const sat = series.find((s: any) => s.name === 'satellites')
    expect(hlPrice).toBeDefined()
    expect(hlPrice.z).toBeGreaterThan(pp.z)
    expect(hlPrice.z).toBeGreaterThan(sat.z)
  })

  it('bo9 (price-anchored): grid2 highlight is EMPTY; highlight-price has the entry', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: 'bo9' })
    const series = opt.series as any[]
    // grid2 highlight must be empty — bo goes to grid0 only
    const hl = series.find((s: any) => s.name === 'highlight')
    expect((hl.data as any[]).length).toBe(0)
    // highlight-price must have exactly one entry for bo9
    const hlPrice = series.find((s: any) => s.name === 'highlight-price')
    expect(hlPrice).toBeDefined()
    expect(hlPrice.data.length).toBe(1)
    const item = hlPrice.data[0]
    expect(item.event_id).toBe('bo9')
    // value encoding = [start_idx, y_price] matching pricePointData
    expect(item.value[0]).toBe(9)
    expect(item.value[1]).toBeCloseTo(bars[9].h * 1.005, 5)
  })

  it('highlight data has correct event_id and kind=interval for an interval event', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: 'down1' })
    const hl = (opt.series as any[]).find((s: any) => s.name === 'highlight')
    expect(hl.data.length).toBe(1)
    const item = hl.data[0]
    expect(item.event_id).toBe('down1')
    expect(item.kind).toBe('interval')
    // value encoding matches intervalData: [start_idx, end_idx, lane, band, nBands]
    expect(item.value[0]).toBe(1)
    expect(item.value[1]).toBe(6)
  })

  it('no selectedEventId → highlight series present but data empty', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const hl = (opt.series as any[]).find((s: any) => s.name === 'highlight')
    expect(hl).toBeDefined()
    expect((hl.data as any[]).length).toBe(0)
  })

  it('selectedEventId not in current level → no highlight data (level=matched, boX detected-only)', () => {
    const matchedInput = makeInput('matched', roleColors)
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...matchedInput, selectedEventId: 'boX' })
    const hl = (opt.series as any[]).find((s: any) => s.name === 'highlight')
    expect((hl.data as any[]).length).toBe(0)
  })

  it('highlight-price is empty when no selectedEventId', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const hlPrice = (opt.series as any[]).find((s: any) => s.name === 'highlight-price')
    expect(hlPrice).toBeDefined()
    expect((hlPrice.data as any[]).length).toBe(0)
  })

  it('interval event: grid2 highlight filled, highlight-price empty (no double-render)', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, selectedEventId: 'down1' })
    const series = opt.series as any[]
    const hl = series.find((s: any) => s.name === 'highlight')
    const hlPrice = series.find((s: any) => s.name === 'highlight-price')
    expect(hl.data.length).toBe(1)
    expect(hl.data[0].event_id).toBe('down1')
    // highlight-price must be empty — down1 is time-anchored
    expect((hlPrice.data as any[]).length).toBe(0)
  })
})

// ── D2: tooltipResolver ───────────────────────────────────────────────────────
// Task 7 以后: 全局 tooltip = axis-trigger bar formatter (buildBarTooltipFormatter)
// marker 的 event/clause 信息 → 各 marker series 的 series-level tooltip.formatter
// (来自 buildMarkerTooltipFormatter)。以下测试已更新至新架构。
describe('buildKlineOption — D2 tooltipResolver', () => {
  const baseInput = makeInput('detected', roleColors)

  const stubResolver = (eventId: string) => ({
    clauses: {
      clause_a: { measured: 42, op: '>=', threshold: 10, satisfied: true },
      clause_b: { measured: 3,  op: '<',  threshold: 5,  satisfied: true },
    },
    raw: {
      start_idx: 9,
      source_tag: 'bo',
      members: ['bo_child1', 'bo_child2'],   // 故意混入 members
    } as Record<string, unknown>,
  })

  it('global tooltip is axis-trigger (bar formatter) regardless of tooltipResolver', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const tt = opt.tooltip as any
    // Task 7: 全局 tooltip 改为 axis-trigger bar tooltip
    expect(tt.trigger).toBe('axis')
    expect(typeof tt.formatter).toBe('function')
  })

  it('marker series tooltip is undefined when tooltipResolver not provided', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, baseInput)
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    // 无 tooltipResolver → markerTooltip=undefined → series.tooltip=undefined
    expect(points.tooltip).toBeUndefined()
  })

  it('marker series tooltip.formatter exists when tooltipResolver provided', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    expect(points.tooltip).toBeDefined()
    expect(typeof points.tooltip.formatter).toBe('function')
  })

  it('marker series formatter returns clause info when params has event_id', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    const result: string = formatter({ data: { event_id: 'bo9' } })
    expect(result).toContain('clause_a')
    expect(result).toContain('42')
    expect(result).toContain('✓')
  })

  it('marker series formatter result does NOT contain members key', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    const result: string = formatter({ data: { event_id: 'bo9' } })
    expect(result).not.toContain('members')
  })

  it('marker series formatter returns empty string when no event_id in params', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    expect(formatter({ data: {} })).toBe('')
    expect(formatter({ data: null })).toBe('')
    expect(formatter(null)).toBe('')
  })

  it('marker series formatter includes raw fields (excluding members)', () => {
    const opt = buildKlineOption(bars, EVENTS, MATCHES, { ...baseInput, tooltipResolver: stubResolver })
    const series = opt.series as any[]
    const points = series.find((s: any) => s.name === 'points')
    const formatter = points.tooltip.formatter
    const result: string = formatter({ data: { event_id: 'bo9' } })
    expect(result).toContain('start_idx')
    expect(result).toContain('source_tag')
    expect(result).not.toContain('members')
  })
})

// ── render_grid 分流 + satellites ─────────────────────────────────────────────
describe('chart render_grid 分流 + satellites', () => {
  function buildInput(level: Level): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(TOPOLOGY.nodes)
    const isolated = isolatedNodeIds(TOPOLOGY)
    const mIds = matchedIds(MATCHES)
    return {
      topology: TOPOLOGY, isolatedNodeIds: isolated, tagList, level,
      roleColors: { down: '#f59e0b', side: '#f59e0b', burst: '#2563eb', tb: '#16a34a', bo: '#dc2626' },
      eventTier: (e) => eventTierOf(e, mIds, new Set()),
      roleOfEventByBand: (e) => roleOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
    }
  }

  it('bo 节点 render_grid=price → bo 事件不进 grid2 points 系列', () => {
    const opt: any = buildKlineOption(bars, EVENTS, MATCHES, buildInput('detected'))
    const points = opt.series.find((s: any) => s.name === 'points')
    expect(points).toBeTruthy()
    // grid2 points 不应包含 bo 事件 (它们去 price-points)
    const boInGrid2 = points.data.filter((d: any) =>
      ['bo9', 'bo11', 'boX'].includes(d.event_id)
    )
    expect(boInGrid2.length).toBe(0)
    // tb 仍在 grid2 points
    const tbInGrid2 = points.data.filter((d: any) => d.event_id === 'tb16')
    expect(tbInGrid2.length).toBe(1)
  })

  it('新 price-points 系列存在并包含 bo 事件 (yAxisIndex=0 → grid0)', () => {
    const opt: any = buildKlineOption(bars, EVENTS, MATCHES, buildInput('detected'))
    const pp = opt.series.find((s: any) => s.name === 'price-points')
    expect(pp).toBeTruthy()
    expect(pp.xAxisIndex).toBe(0)
    expect(pp.yAxisIndex).toBe(0)
    expect(pp.data.map((d: any) => d.event_id).sort()).toEqual(['bo11', 'bo9', 'boX'])
    // value = [start_idx, price-derived y]; y 应高于 bar high (bars[9].h = 11+9 = 20, so 20 * 1.005)
    const bo9row = pp.data.find((d: any) => d.event_id === 'bo9')
    expect(bo9row.value[0]).toBe(9)
    expect(bo9row.value[1]).toBeCloseTo(bars[9].h * 1.005, 5)
  })

  it('新 satellites 系列承载 bo.referenced_points (每点一条 record)', () => {
    const opt: any = buildKlineOption(bars, EVENTS, MATCHES, buildInput('detected'))
    const sat = opt.series.find((s: any) => s.name === 'satellites')
    expect(sat).toBeTruthy()
    expect(sat.xAxisIndex).toBe(0)
    expect(sat.yAxisIndex).toBe(0)
    // bo9 有 2 个 referenced_points (在 EVENTS fixture 里), 应在 satellites.data 中
    expect(sat.data.length).toBeGreaterThanOrEqual(2)
    const labels = sat.data.map((d: any) => d.label)
    expect(labels).toContain('pk0')
    expect(labels).toContain('pk1')
    // value = [bar_idx, price] 透传
    const pk0 = sat.data.find((d: any) => d.label === 'pk0')
    expect(pk0.value).toEqual([5, 12.5])
  })

  it('时间锚定事件 (tb / trend / burst) 仍走原 grid2 通道', () => {
    const opt: any = buildKlineOption(bars, EVENTS, MATCHES, buildInput('detected'))
    const points = opt.series.find((s: any) => s.name === 'points')
    const intervals = opt.series.find((s: any) => s.name === 'intervals')
    // tb 是 point → grid2 points
    expect(points.data.some((d: any) => d.event_id === 'tb16')).toBe(true)
    // burst / down / side 是 interval → grid2 intervals
    const intervalIds = intervals.data.map((d: any) => d.event_id)
    expect(intervalIds).toContain('burst1')
    expect(intervalIds).toContain('down1')
  })
})

// ── Dev UI replication (Task 7 integration) ───────────────────────────────────
describe('Dev UI replication (Task 7 integration)', () => {
  function mkBars(n: number): Bar[] {
    return Array.from({ length: n }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, '0')}`,
      o: 10, h: 11, l: 9, c: 10, v: 100, rv: 1,
    }))
  }

  // 复用现有 makeInput 但构造最小的 input(无事件/match 数据)
  function mkInput(override: Partial<BandRenderInput> = {}): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(TOPOLOGY.nodes)
    const isolated = isolatedNodeIds(TOPOLOGY)
    const mIds = matchedIds(MATCHES)
    const qualifiedIds = new Set<string>()
    return {
      topology: TOPOLOGY,
      isolatedNodeIds: isolated,
      tagList,
      level: 'detected',
      roleColors,
      eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
      roleOfEventByBand: (e) => roleOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      ...override,
    }
  }

  it('grid layout: 2 grids (was 3)', () => {
    const testBars = mkBars(10)
    const opt = buildKlineOption(testBars, [], [], mkInput())
    expect((opt.grid as any[]).length).toBe(2)
  })

  it('xAxis: 2 axes', () => {
    const testBars = mkBars(10)
    const opt = buildKlineOption(testBars, [], [], mkInput())
    expect((opt.xAxis as any[]).length).toBe(2)
  })

  it('dataZoom initial range locks to [startIdx, endIdx+1] / N * 100', () => {
    const testBars = mkBars(10)
    const opt = buildKlineOption(testBars, [], [], mkInput({ strictWindow: { startIdx: 2, endIdx: 7 } }))
    const dz0 = (opt.dataZoom as any[])[0]
    expect(dz0.start).toBeCloseTo(20, 5)   // 2/10*100
    expect(dz0.end).toBeCloseTo(80, 5)     // (7+1)/10*100
  })

  it('candlestick series carries markArea with two shading segments when buffer exists both sides', () => {
    const testBars = mkBars(10)
    const opt = buildKlineOption(testBars, [], [], mkInput({ strictWindow: { startIdx: 2, endIdx: 7 } }))
    const kline = (opt.series as any[]).find(s => s.name === 'kline')
    expect(kline.markArea).toBeDefined()
    expect(kline.markArea.data).toHaveLength(2)
  })

  it('global tooltip is axis-trigger with line axisPointer (cross would dup horizontal vs markLine close-lock)', () => {
    // 普通模式 axisPointer.type='line' 只画沿 axis 的指针(category x 上=竖线、无 y 横线);
    // 横线由 KlineChart.vue 在 candlestick 上挂 markLine 锁 close 单独画;
    // Ctrl 模式由 KlineChart.vue 切回 'cross' 让 ECharts 自带横线跟鼠标。
    // 历史 bug: 默认 'cross' + markLine 同时存在 → 两根横线同时显示。
    const testBars = mkBars(10)
    const opt = buildKlineOption(testBars, [], [], mkInput())
    expect((opt.tooltip as any).trigger).toBe('axis')
    expect((opt.tooltip as any).axisPointer.type).toBe('line')
  })
})
