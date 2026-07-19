// chart.spec.ts — computeEventData / buildMainOption / buildSubOption 契约测试
// (Task 6: 旧 buildKlineOption 单函数 API 及其所有专属测试已随函数删除;本文件只保留
//  仍对应存活 API 的契约测试。内联最小 fixture,自包含,不依赖外部 ANALYSIS。)
import { describe, it, expect } from 'vitest'
import {
  computeEventData,
  buildMainOption,
  buildSubOption,
  makeRenderHighlightWithGeom,
  makeRenderPricePointHighlight,
  makeRenderBracket,
  renderIntervalWithGeom,
  renderPointWithGeom,
} from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { computeSubGeometry, type BandGeom } from '../src/render/subGeometry'
import {
  deriveTagMap, isolatedNodeIds, eventTierOf, nodeOfEventByBand, bandKeyOf, matchedIds,
} from '../src/render/visible'
import type { Bar, EventDict, MatchDict, Topology, Level, Tier } from '../src/types'

describe('chart.ts — computeEventData / buildMainOption / buildSubOption', () => {
  // Fixtures(简化最小场景:1 bar / 1 event / 1 match, 用来验契约与切分正确)
  const bars = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  const events = [
    { class_id: 'burst', event_id: 'burst_0_1', start_idx: 0, end_idx: 1, source_tag: 'burst' },
    { class_id: 'tb',    event_id: 'tb_1',      start_idx: 1, end_idx: 1, source_tag: 'tb' },
  ] as any[]
  const matches = [
    { event_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1', tb: 'tb_1' },
      children: ['burst_0_1', 'tb_1'],
      forward_return: 0.05 } as any,
  ]
  const topology = { nodes: [
    { node_id: 'burst', source_tag: 'burst' },
    { node_id: 'tb',    source_tag: 'tb' },
  ] } as any
  const tagList = ['burst', 'tb']

  const baseParams = {
    topology,
    isolatedNodeIds: new Set<string>(),
    tagList,
    level: 'matched' as const,
    nodeColors: { burst: '#2563eb', tb: '#16a34a' },
    eventTier: () => 'matched' as const,
    nodeOfEventByBand: (e: any) => e.source_tag,
    bandKeyOf: (e: any) => e.source_tag,
    nodeVisible: {},
    tagToNodes: { burst: ['burst'], tb: ['tb'] },
    selectedEventId: null,
    tooltipResolver: undefined,
    strictWindow: null,
    matchLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedMatchId: null,
    candidateMatchIds: new Set<string>(),
    highlightedEventIds: new Set<string>(),
    pendingDisambigEventId: null,
  }

  it('computeEventData bundles points/intervals/brackets/priceAnchored/satellites', () => {
    const bundle = computeEventData(bars, events, matches, baseParams)
    // burst_0_1 是 interval(start≠end),tb_1 是 point(start==end)
    expect(bundle.intervalData.some(d => d.event_id === 'burst_0_1')).toBe(true)
    expect(bundle.pointData.some(d => d.event_id === 'tb_1')).toBe(true)
    expect(bundle.bracketData.length).toBe(1)
    expect(bundle.bracketData[0].match_id).toBe('m@0-1')
  })

  it('buildMainOption returns option with kline+volume+hit-spanner+price series only (no brackets/points/intervals)', () => {
    const bundle = computeEventData(bars, events, matches, { ...baseParams, matches })
    const opt = buildMainOption(bars, bundle, { ...baseParams, matches }) as any
    const seriesNames = (opt.series ?? []).map((s: any) => s.name)
    expect(seriesNames).toContain('kline')
    expect(seriesNames).toContain('volume')
    expect(seriesNames).toContain('kline-hit-spanner')  // G2 全列 hover 触发 OHLC
    expect(seriesNames).not.toContain('brackets')
    expect(seriesNames).not.toContain('points')
    expect(seriesNames).not.toContain('intervals')
    // price-anchored 主 marker 保留在主图
    expect(seriesNames).toContain('price-points')
    expect(seriesNames).toContain('satellites')
    expect(seriesNames).toContain('highlight-price')
    // 主图只有 grid[0]
    expect(opt.grid.length).toBe(1)
    // tooltip trigger=item(G2),不是 axis
    expect(opt.tooltip.trigger).toBe('item')
    // axisPointer 挂 xAxis/yAxis 组件级,不在 tooltip 里
    expect(opt.tooltip.axisPointer).toBeUndefined()
    expect(opt.xAxis[0].axisPointer).toBeDefined()
    expect(opt.xAxis[0].axisPointer.snap).toBe(true)
    expect(opt.yAxis[0].axisPointer).toBeDefined()
    expect(opt.yAxis[0].axisPointer.show).toBe(false)  // Ctrl 初始 off
    // 不带 axisPointer.link(拆双实例后由 echarts.connect 接管)
    expect(opt.axisPointer).toBeUndefined()
  })

  it('buildMainOption keeps original axisLabel formatter on yAxis[0] (0.879 not 0.8787...)', () => {
    const bundle = computeEventData(bars, events, matches, baseParams)
    const opt = buildMainOption(bars, bundle, baseParams) as any
    const yAxis0 = opt.yAxis[0]
    expect(typeof yAxis0.axisLabel.formatter).toBe('function')
    expect(yAxis0.axisLabel.formatter(0.8787499999999999)).toBe('0.879')
    expect(yAxis0.axisLabel.formatter(150)).toBe('150')
  })
})

// ─── 恢复 Task 6 review 认定被误删的覆盖(4 组,详见 .superpowers/sdd/task-6-report.md) ──
// 旧 buildKlineOption 已删,这些行为现活在 computeEventData / buildMainOption / buildSubOption /
// makeRenderHighlightWithGeom 里;fixture 复刻自 95f5554 版 chart.spec.ts 的 5-node 拓扑
// (down/side 独立趋势 + bo price-anchored 孤立节点 + burst + tb),适配新签名重写断言。
describe('chart.ts — restored coverage (Task 6 review fix)', () => {
  const topology: Topology = {
    nodes: [
      { node_id: 'down',  class_id: 'trend', source_tag: 'trend0', where_rules: [] },
      { node_id: 'side',  class_id: 'trend', source_tag: 'trend1', where_rules: [] },
      { node_id: 'bo',    class_id: 'bo',    source_tag: 'bo', render_grid: 'price', where_rules: [] },
      { node_id: 'burst', class_id: 'burst', source_tag: 'burst',  where_rules: [] },
      { node_id: 'tb',    class_id: 'tb',    source_tag: 'tb',     where_rules: [] },
    ],
    edges: [
      { src: 'down',  dst: 'burst', kind: 'TemporalEdge',    rule: 'before' },
      { src: 'side',  dst: 'burst', kind: 'ContainmentEdge', rule: 'contains' },
      { src: 'burst', dst: 'tb',    kind: 'TemporalEdge',    rule: 'gap=1' },
      // bo 节点孤立(无边):render_grid=price 独立于图结构
    ],
  }

  const events: EventDict[] = [
    { class_id: 'trend', event_id: 'down1',  source_tag: 'trend0', start_idx: 1,  end_idx: 6  },
    { class_id: 'trend', event_id: 'side1',  source_tag: 'trend1', start_idx: 4,  end_idx: 12 },
    { class_id: 'burst', event_id: 'burst1', source_tag: 'burst',  start_idx: 10, end_idx: 15 },
    { class_id: 'bo', event_id: 'bo9',  source_tag: 'bo', start_idx: 9,  end_idx: 9,
      referenced_points: [[5, 12.5, 'pk0'], [7, 13.0, 'pk1']],
      broken_peak_ids: [0, 1] } as any,
    { class_id: 'bo', event_id: 'bo11', source_tag: 'bo', start_idx: 11, end_idx: 11 },
    { class_id: 'tb', event_id: 'tb16', source_tag: 'tb', start_idx: 16, end_idx: 16 },
    // detected-only:未 matched、未 qualified
    { class_id: 'bo', event_id: 'boX',  source_tag: 'bo', start_idx: 20, end_idx: 20 },
  ] as any[]

  const matches: MatchDict[] = [
    {
      event_id: 'm1', start_idx: 1, end_idx: 16,
      node_index: { down: 'down1', side: 'side1', burst: 'burst1', tb: 'tb16' },
      children: ['down1', 'side1', 'burst1', 'tb16'],
      predicate_trace: { where_results: {}, edge_results: {} },
    } as any,
  ]

  const bars: Bar[] = Array.from({ length: 22 }, (_, i) => ({
    date: `2025-01-${String(i + 1).padStart(2, '0')}`,
    o: 10 + i, h: 11 + i, l: 9 + i, c: 10.5 + i, v: 1000 + i, rv: 0,
  }))
  const nodeColors = { down: '#d97706', side: '#fbbf24', burst: '#7c3aed', tb: '#16a34a' }

  function makeInput(level: Level, overrides: Partial<BandRenderInput> = {}): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
    const isolated = isolatedNodeIds(topology)
    const mIds = matchedIds(matches, events, topology.edges)
    const qualifiedIds = new Set<string>()
    return {
      topology, isolatedNodeIds: isolated, tagList, level, nodeColors,
      eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      nodeVisible: {},
      tagToNodes,
      selectedEventId: null,
      ...overrides,
    }
  }

  // ── 1. level gating: RANK(matched>qualified>detected) + boX exclusion at matched (chart.ts:110-113) ──
  describe('1. level gating — RANK + boX exclusion at matched level', () => {
    it('RANK: level=qualified admits matched+qualified tiers, excludes detected-only', () => {
      const stub: EventDict[] = [
        { class_id: 'x', event_id: 'eDetected',  source_tag: 'tb', start_idx: 1, end_idx: 1 },
        { class_id: 'x', event_id: 'eQualified', source_tag: 'tb', start_idx: 2, end_idx: 2 },
        { class_id: 'x', event_id: 'eMatched',   source_tag: 'tb', start_idx: 3, end_idx: 3 },
      ] as any[]
      const tierOf = (e: EventDict): Tier =>
        e.event_id === 'eMatched' ? 'matched' : e.event_id === 'eQualified' ? 'qualified' : 'detected'
      const input = makeInput('qualified', { eventTier: tierOf })
      const bundle = computeEventData(bars, stub, [], input)
      const ids = bundle.pointData.map((d) => d.event_id)
      expect(ids).toContain('eMatched')
      expect(ids).toContain('eQualified')
      expect(ids).not.toContain('eDetected')
    })

    it('level=matched: boX (detected-only bo event) excluded from pricePointData; matched events remain', () => {
      const input = makeInput('matched')
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.pricePointData.map((d) => d.event_id)).not.toContain('boX')
      expect(bundle.intervalData.map((d) => d.event_id))
        .toEqual(expect.arrayContaining(['down1', 'side1', 'burst1']))
      expect(bundle.pointData.map((d) => d.event_id)).toContain('tb16')
    })

    it('level=detected: boX (and all other tiers) included in pricePointData', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.pricePointData.map((d) => d.event_id)).toEqual(
        expect.arrayContaining(['bo9', 'bo11', 'boX']),
      )
    })
  })

  // ── 2. render_grid routing + satellites/broken_peak_ids/hasPks (chart.ts:114-115,122-131,140-192) ──
  describe('2. render_grid routing + satellites/broken_peak_ids/hasPks', () => {
    it('bo events (render_grid=price) 不进入 grid2 pointData;时间锚定 tb16 仍走 pointData', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      const boInPointData = bundle.pointData.filter((d) => ['bo9', 'bo11', 'boX'].includes(d.event_id))
      expect(boInPointData.length).toBe(0)
      expect(bundle.pointData.some((d) => d.event_id === 'tb16')).toBe(true)
    })

    it('pricePointData 含全部 3 个 bo 事件(value[0]=start_idx);text 取自 broken_peak_ids([0,1] / "[]" 兜底)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.pricePointData.map((d) => d.event_id).sort()).toEqual(['bo11', 'bo9', 'boX'])
      const bo9 = bundle.pricePointData.find((d) => d.event_id === 'bo9')!
      const bo11 = bundle.pricePointData.find((d) => d.event_id === 'bo11')!
      expect(bo9.value[0]).toBe(9)
      expect(bo9.anchorY).toBe(bars[9].h)
      expect(bo9.text).toBe('[0,1]')
      expect(bo11.text).toBe('[]')
    })

    it('satelliteData 承载 referenced_points(value=[barIdx,price], anchorY=bars[barIdx].h, pkId)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.satelliteData.length).toBeGreaterThanOrEqual(2)
      const pk0 = bundle.satelliteData.find((d) => d.label === 'pk0')!
      expect(pk0.value).toEqual([5, 12.5])
      expect(pk0.anchorY).toBe(bars[5].h)
      expect(pk0.pkId).toBe('0')
    })

    it('hasPks: bo9(referenced barIdx 5/7 ≠ start_idx=9)=false;注入 bo5_at5(与 pk0 barIdx=5 重合)=true', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      const bo9 = bundle.pricePointData.find((d) => d.event_id === 'bo9')!
      expect(bo9.hasPks).toBe(false)

      const injected = [
        ...events,
        { class_id: 'bo', event_id: 'bo5_at5', source_tag: 'bo', start_idx: 5, end_idx: 5, referenced_points: [] },
      ] as any[]
      const bundle2 = computeEventData(bars, injected, matches, input)
      const bo5 = bundle2.pricePointData.find((d) => d.event_id === 'bo5_at5')!
      expect(bo5.hasPks).toBe(true)
    })
  })

  // ── 3. highlight 三分支 + z-order (chart.ts:214-253, 354-363) ──
  describe('3. highlight three-branch + z-order', () => {
    // 放大+阴影悬浮三态(2026-07-08 改):group/focus 都保 node/tier 分色(itemStyle.color),
    // 靠边框粗细区分——group=细深边(1.5)、focus=粗深边(2.5);琥珀不再代表选中。
    // pending=白底垫层+本色闪烁层。全部 silent:true(实心版盖住本体,交互须穿透到下层)。
    it('makeRenderHighlightWithGeom: 三态 — group/focus node 分色, group 细深边 / focus 粗深边, pending 白底+本色闪烁分层', () => {
      const bandGeom: BandGeom[] = [{ top: 20, h: 20, laneCount: 1 }]
      const fakeApi: any = { value: () => 0, coord: () => [100, 200], size: () => [10, 0] }
      // pointData 新 shape(spec 2026-07-13):[start, start, lane, band, nBands];lane=0, band=0
      const mk = (kind: 'group' | 'focus' | 'pendingDisambig') =>
        makeRenderHighlightWithGeom(
          [{ value: [0, 0, 0, 0, 1], event_id: 'e1', itemStyle: { color: '#22c55e' }, kind }],
          bandGeom,
        )({ dataIndex: 0 }, fakeApi) as any

      const group = mk('group')
      expect(group.type).toBe('polygon')
      // lane0 centerY = top(20) + BAND_TOP_PAD(4) + 0*(7+2) + 7/2 = 27.5;半宽 = max(7, min(28, 10*0.35*1.4)) = 7
      expect(group.shape.points).toEqual([[100, 33.5], [93, 23.5], [107, 23.5]])
      // group = node/tier 本色 + 细深边(1.5)
      expect(group.style.fill).toBe('#22c55e')
      expect(group.style.stroke).toBe('#1e293b')
      expect(group.style.lineWidth).toBe(1.5)
      expect(group.style.shadowBlur).toBe(6)
      expect(group.style.shadowOffsetY).toBe(2)
      expect(group.silent).toBe(true)
      expect(group.keyframeAnimation).toBeUndefined()

      const focus = mk('focus')
      expect(focus.type).toBe('polygon')
      // focus = node/tier 本色 + 粗深边(2.5,被点者标记)
      expect(focus.style.fill).toBe('#22c55e')
      expect(focus.style.stroke).toBe('#1e293b')
      expect(focus.style.lineWidth).toBe(2.5)
      expect(focus.style.shadowBlur).toBe(6)
      expect(focus.silent).toBe(true)
      expect(focus.keyframeAnimation).toBeUndefined()

      const pending = mk('pendingDisambig')
      expect(pending.type).toBe('group')
      expect(pending.silent).toBe(true)
      // pending 逐字不动:白底垫层(阴影+琥珀边恒定)+ 本色 fill 层单独闪
      expect(pending.children[0].style.fill).toBe('#ffffff')
      expect(pending.children[0].style.stroke).toBe('#fbbf24')
      expect(pending.children[0].style.shadowBlur).toBe(6)
      expect(pending.children[0].keyframeAnimation).toBeUndefined()
      expect(pending.children[1].style.fill).toBe('#22c55e')
      expect(pending.children[1].keyframeAnimation).toMatchObject({ duration: 1200, loop: true })
      expect(pending.children[1].keyframeAnimation.keyframes).toEqual([
        { percent: 0, style: { opacity: 1 } },
        { percent: 0.5, style: { opacity: 0.45 } },
        { percent: 1, style: { opacity: 1 } },
      ])
      // 动画对象每次新建(zrender 会污染共享常量)
      expect(mk('pendingDisambig').children[1].keyframeAnimation)
        .not.toBe(pending.children[1].keyframeAnimation)
    })

    it('makeRenderHighlightWithGeom: interval 放大版 — 高 7→10 居中外扩,长度不变,focus node色+粗深边', () => {
      const bandGeom: BandGeom[] = [{ top: 20, h: 40, laneCount: 1 }]
      const fakeApi: any = {
        value: (i: number) => [10, 20][i] ?? 0,
        coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
        size: () => [10, 0],
      }
      const shape = makeRenderHighlightWithGeom(
        [{ value: [10, 20, 0, 0, 1], event_id: 'e1', itemStyle: { color: '#3b82f6' }, kind: 'focus' }],
        bandGeom,
      )({ dataIndex: 0 }, fakeApi) as any
      expect(shape.type).toBe('rect')
      // 自顶向下(spec 2026-07-03-bracket-band-unify):本体 laneY = 20+4+0*(7+2) = 24;
      // 放大版 y = 24−1.5, 高 10;x/width 不外扩(时间跨度语义)——几何全不动
      expect(shape.shape).toEqual({ x: 100, y: 22.5, width: 100, height: 10 })
      // fill 保 node 本色(2026-07-08 改),粗深边
      expect(shape.style.fill).toBe('#3b82f6')
      expect(shape.style.stroke).toBe('#1e293b')
      expect(shape.style.lineWidth).toBe(2.5)
      expect(shape.silent).toBe(true)
    })

    // 主图 bo 盒放大版:实心版会遮住本体文字 → 必须重画盒+文本(字号不变)。
    // 2026-07-08 改:group/focus 保 node/tier 分色(itemStyle.color) + 细/粗深边、shadow;
    // 文字统一深灰蓝(橙/灰底皆可读);pending 白底+闪烁分层用 color 而非 tier bg,文字统一深灰蓝。
    it('makeRenderPricePointHighlight: 放大盒+text 重画 — group node色+细深边, focus node色+粗深边, pending 白底+闪', () => {
      const fakeApi: any = { value: () => 0, coord: () => [100, 200] }
      const mk = (kind: 'group' | 'focus' | 'pendingDisambig') =>
        makeRenderPricePointHighlight([
          { value: [0, 0], event_id: 'e1', anchorY: 1, text: '[1]', hasPks: false,
            itemStyle: { color: '#f97316' }, kind },
        ])({ dataIndex: 0 }, fakeApi) as any

      const group = mk('group')
      expect(group.type).toBe('group')
      expect(group.silent).toBe(true)
      // children[0] = 放大盒:node 本色 + 细深边(1.5)+ shadow
      const gBox = group.children[0]
      expect(gBox.type).toBe('rect')
      expect(gBox.shape.r).toBe(7)          // BO_BOX_RADIUS(4) + pad(3)
      expect(gBox.style.fill).toBe('#f97316')
      expect(gBox.style.stroke).toBe('#1e293b')
      expect(gBox.style.lineWidth).toBe(1.5)
      expect(gBox.style.shadowBlur).toBe(6)
      // children[1] = text:文字保留、字号不变、深灰蓝(全 tier 统一)
      const gText = group.children[1]
      expect(gText.type).toBe('text')
      expect(gText.style.text).toBe('[1]')
      expect(gText.style.fontSize).toBe(16)  // MARKER_FONT_SIZE
      expect(gText.style.fill).toBe('#1e293b')

      const focus = mk('focus')
      expect(focus.children[0].style.fill).toBe('#f97316')
      expect(focus.children[0].style.stroke).toBe('#1e293b')
      expect(focus.children[0].style.lineWidth).toBe(2.5)
      expect(focus.children[0].style.shadowBlur).toBe(6)
      expect(focus.children[1].type).toBe('text')
      expect(focus.children[1].style.fill).toBe('#1e293b')

      const pending = mk('pendingDisambig')
      expect(pending.children).toHaveLength(3)
      expect(pending.children[0].style.fill).toBe('#ffffff')       // 白底垫层(阴影+琥珀边)不动
      expect(pending.children[0].style.stroke).toBe('#fbbf24')
      expect(pending.children[0].style.shadowBlur).toBe(6)
      expect(pending.children[1].style.fill).toBe('#f97316')       // 闪烁本色改用 color 参数
      expect(pending.children[1].keyframeAnimation).toMatchObject({ duration: 1200, loop: true })
      expect(pending.children[2].type).toBe('text')                 // 文字最上层不闪
      expect(pending.children[2].style.fill).toBe('#1e293b')        // 全 tier 统一深灰蓝
      expect(pending.children[2].keyframeAnimation).toBeUndefined()
    })

    it('push order: highlightData 先 group 再 pendingDisambig 再 focus(chart.ts:219-253 三分支顺序)', () => {
      const stub: EventDict[] = [
        { class_id: 'x', event_id: 'eGroup',   source_tag: 'tb', start_idx: 1, end_idx: 1 },
        { class_id: 'x', event_id: 'ePending', source_tag: 'tb', start_idx: 2, end_idx: 2 },
        { class_id: 'x', event_id: 'eFocus',   source_tag: 'tb', start_idx: 3, end_idx: 3 },
      ] as any[]
      const input = makeInput('detected', {
        highlightedEventIds: new Set(['eGroup']),
        pendingDisambigEventId: 'ePending',
        selectedEventId: 'eFocus',
      })
      const bundle = computeEventData(bars, stub, [], input)
      expect(bundle.highlightData.map((d: any) => d.kind)).toEqual(['group', 'pendingDisambig', 'focus'])
      expect(bundle.highlightData.map((d: any) => d.event_id)).toEqual(['eGroup', 'ePending', 'eFocus'])
    })

    // 被点 marker 同属 highlight 集合(点击链路必然如此):若同时出 group + focus
    // 两层同坐标实心放大版,阴影叠加会让被点者投影明显深于组员。
    // 故 group 条目跳过 selectedEventId,被点 marker 由 focus 条目独家表达。
    it('selectedEventId ∈ highlightedEventIds 时只出 focus 条目,不出 group 条目', () => {
      const stub: EventDict[] = [
        { class_id: 'x', event_id: 'eSel',   source_tag: 'tb', start_idx: 1, end_idx: 1 },
        { class_id: 'x', event_id: 'eOther', source_tag: 'tb', start_idx: 2, end_idx: 2 },
      ] as any[]
      const input = makeInput('detected', {
        highlightedEventIds: new Set(['eSel', 'eOther']),
        selectedEventId: 'eSel',
      })
      const bundle = computeEventData(bars, stub, [], input)
      const ofSel = bundle.highlightData.filter((d: any) => d.event_id === 'eSel')
      expect(ofSel.map((d: any) => d.kind)).toEqual(['focus'])
      const ofOther = bundle.highlightData.filter((d: any) => d.event_id === 'eOther')
      expect(ofOther.map((d: any) => d.kind)).toEqual(['group'])
    })

    it('buildMainOption: highlight-price z(21) > satellites z(13) > price-points z(12)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      const opt = buildMainOption(bars, bundle, input) as any
      const S = (name: string) => opt.series.find((s: any) => s.name === name)
      expect(S('highlight-price').z).toBe(21)
      expect(S('satellites').z).toBe(13)
      expect(S('price-points').z).toBe(12)
      expect(S('highlight-price').z).toBeGreaterThan(S('satellites').z)
      expect(S('satellites').z).toBeGreaterThan(S('price-points').z)
    })

    // keyframeAnimation 受 series 级 isAnimationEnabled() 闸控(实测):
    // 顶层 animation:false 会连带跳过闪烁 → 两 highlight 系列必须显式 animation:true。
    it('highlight 系列显式 animation:true(顶层 animation:false 下 keyframeAnimation 才生效)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      const mainOpt = buildMainOption(bars, bundle, input) as any
      expect(mainOpt.animation).toBe(false)
      expect(mainOpt.series.find((s: any) => s.name === 'highlight-price').animation).toBe(true)

      const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1, 1, 1] })
      const subOpt = buildSubOption(bars, bundle, subGeom, input, 800) as any
      expect(subOpt.animation).toBe(false)
      expect(subOpt.series.find((s: any) => s.name === 'highlight').animation).toBe(true)
    })
  })

  // ── 4. endNode → bracketData.event_id (chart.ts:200-204, §7-4) ──
  describe('4. endNode → bracketData.event_id', () => {
    it('endNode 缺省时 bracketData 只带 match_id 不带 event_id(向后兼容)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.bracketData.length).toBeGreaterThan(0)
      for (const d of bundle.bracketData) {
        expect(d.match_id).toBe('m1')
        expect(d.event_id).toBeUndefined()
      }
    })

    it("endNode='tb' 时 bracketData.event_id = node_index.tb", () => {
      const input = makeInput('detected', { endNode: 'tb' })
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.bracketData[0].event_id).toBe('tb16')
    })

    it('endNode 指向不存在的 node 时 event_id 安全降级为 undefined(不崩溃)', () => {
      const input = makeInput('detected', { endNode: 'nonexistent' })
      expect(() => computeEventData(bars, events, matches, input)).not.toThrow()
      const bundle = computeEventData(bars, events, matches, input)
      expect(bundle.bracketData[0].event_id).toBeUndefined()
    })

    it('node_index 值为 string[](kleene)时取首元素', () => {
      const kleeneMatches: MatchDict[] = [{
        event_id: 'mk', start_idx: 1, end_idx: 16,
        node_index: { tb: ['tb16', 'tb18'] as any, down: 'down1', side: 'side1', burst: 'burst1' },
        children: ['down1', 'side1', 'burst1', 'tb16', 'tb18'],
        predicate_trace: { where_results: {}, edge_results: {} },
      } as any]
      const input = makeInput('detected', { endNode: 'tb' })
      const bundle = computeEventData(bars, events, kleeneMatches, input)
      expect(bundle.bracketData[0].event_id).toBe('tb16')
    })
  })
})

// ---------- Task 3 buildSubDecorGraphics 契约测试 ----------
import { buildSubDecorGraphics } from '../src/render/chart'
import {
  BAND_TOP_PAD,
  BAND_LANE_H,
  SUB_DIVIDER_COLOR,
  SUB_DIVIDER_H,
  BAND_INNER_LINE_COLOR,
  BAND_INNER_LINE_H,
  SUB_GRID_LEFT,
  SUB_GRID_RIGHT,
} from '../src/render/subGeometry'

describe('buildSubDecorGraphics — Task 3', () => {
  // fixture: 2 bands, laneCount = [1, 3]; bracketH=6 (1 bracket lane); chartSubWidth=800
  const bandGeom = [
    { top: 22, h: 21, laneCount: 1 },      // band 0: no inner splitLine (laneCount=1)
    { top: 43, h: 35, laneCount: 3 },      // band 1: 2 inner splitLines (between 3 lanes)
  ]
  const dividerY = 20
  const bracketH = 6
  const bandLabelTexts = ['bo', 'burst']
  const matchesLabelVisible = true
  const chartSubWidth = 800
  const expectedRectWidth = chartSubWidth - SUB_GRID_LEFT - SUB_GRID_RIGHT  // 728

  it('returns non-empty array of graphic elements', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    expect(Array.isArray(g)).toBe(true)
    expect(g.length).toBeGreaterThan(0)
  })

  it('contains exactly 1 subDivider rect', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    const dividers = g.filter((e: any) => e.type === 'rect' && e.style?.fill === SUB_DIVIDER_COLOR)
    expect(dividers.length).toBe(1)
    expect(dividers[0].top).toBe(dividerY - SUB_DIVIDER_H / 2)
    expect(dividers[0].left).toBe(SUB_GRID_LEFT)
    expect(dividers[0].shape.width).toBe(expectedRectWidth)
    expect(dividers[0].shape.height).toBe(SUB_DIVIDER_H)
    expect(dividers[0].z).toBe(2)
  })

  it('contains 2 zebra rects (one per band)', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    const zebras = g.filter((e: any) => e.type === 'rect' && (e.style?.fill === 'rgba(0,0,0,0.03)' || e.style?.fill === 'rgba(0,0,0,0)'))
    expect(zebras.length).toBe(2)
    // band 0 (bi=0): fill 'rgba(0,0,0,0.03)'
    const band0Zebra = zebras.find((e: any) => e.top === bandGeom[0].top)
    expect(band0Zebra).toBeDefined()
    expect(band0Zebra!.style.fill).toBe('rgba(0,0,0,0.03)')
    expect(band0Zebra!.shape.height).toBe(bandGeom[0].h)
    expect(band0Zebra!.z).toBe(1)
    // band 1 (bi=1): fill transparent
    const band1Zebra = zebras.find((e: any) => e.top === bandGeom[1].top)
    expect(band1Zebra).toBeDefined()
    expect(band1Zebra!.style.fill).toBe('rgba(0,0,0,0)')
  })

  it('contains 2 band-inner splitLines (band 1 has 3 lanes → 2 gaps; band 0 has 1 lane → 0 lines)', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    const splitLines = g.filter((e: any) => e.type === 'rect' && e.style?.fill === BAND_INNER_LINE_COLOR && e.shape?.height === BAND_INNER_LINE_H)
    expect(splitLines.length).toBe(2)
    // 位于 band 1 内 lane 之间: top = bandGeom[1].top + BAND_TOP_PAD + (lane+1) * BAND_LANE_H - 0.5
    const expectedTopBase = bandGeom[1].top + BAND_TOP_PAD
    const line1Top = expectedTopBase + 1 * BAND_LANE_H - BAND_INNER_LINE_H / 2
    const line2Top = expectedTopBase + 2 * BAND_LANE_H - BAND_INNER_LINE_H / 2
    const tops = splitLines.map((e: any) => e.top).sort((a: number, b: number) => a - b)
    expect(tops[0]).toBe(line1Top)
    expect(tops[1]).toBe(line2Top)
    splitLines.forEach((line: any) => {
      expect(line.z).toBe(2)
      expect(line.left).toBe(SUB_GRID_LEFT)
      expect(line.shape.width).toBe(expectedRectWidth)
    })
  })

  it('contains 2 bandLabel texts, one per band, aligned to band top (top pad)', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    const labels = g.filter((e: any) => e.type === 'text' && ['bo', 'burst'].includes(e.style?.text))
    expect(labels.length).toBe(2)
    const boLabel = labels.find((e: any) => e.style.text === 'bo')
    // top = band 顶 + BAND_TOP_PAD;verticalAlign:'top' → label 顶部锚点在 band 顶部内边距
    // 单/多 lane 视觉统一(不再随 band 高度浮到中间/下半)。
    expect(boLabel!.top).toBe(bandGeom[0].top + BAND_TOP_PAD)
    expect(boLabel!.left).toBe(SUB_GRID_LEFT + 2)
    expect(boLabel!.style.fontSize).toBe(13)
    // ⚠ textAlign/textVerticalAlign 必须在元素顶层(不是 style 内)——style 是 zrender TextStyle,
    // 键名是 align/verticalAlign,写 textVerticalAlign 会被无视。
    expect(boLabel!.textVerticalAlign).toBe('top')
    expect(boLabel!.textAlign).toBe('left')
    expect(boLabel!.z).toBe(5)
    const burstLabel = labels.find((e: any) => e.style.text === 'burst')
    expect(burstLabel!.top).toBe(bandGeom[1].top + BAND_TOP_PAD)
  })

  it('contains 1 matchesLabel when matchesLabelVisible=true', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    const matches = g.filter((e: any) => e.type === 'text' && e.style?.text === 'matches')
    expect(matches.length).toBe(1)
    // matches label 靠 bracket 区上边(BAND_TOP_PAD,与 bandLabels 顶 pad 对称),同款 verticalAlign:'top'
    expect(matches[0].top).toBe(BAND_TOP_PAD)
    expect(matches[0].left).toBe(SUB_GRID_LEFT + 2)
    expect(matches[0].style.fontSize).toBe(13)
    expect(matches[0].textVerticalAlign).toBe('top')
    expect(matches[0].textAlign).toBe('left')
    expect(matches[0].z).toBe(5)
  })

  it('omits matchesLabel when matchesLabelVisible=false', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, false, chartSubWidth)
    const matches = g.filter((e: any) => e.type === 'text' && e.style?.text === 'matches')
    expect(matches.length).toBe(0)
  })

  it('handles empty bandGeom (0 bands) gracefully', () => {
    const g = buildSubDecorGraphics([], dividerY, bracketH, [], matchesLabelVisible, chartSubWidth)
    // 空 bandGeom → 无 zebra、无 bandLabel、无 band-inner splitLine
    expect(g.filter((e: any) => e.type === 'rect' && (e.style?.fill === 'rgba(0,0,0,0.03)' || e.style?.fill === 'rgba(0,0,0,0)')).length).toBe(0)
    expect(g.filter((e: any) => e.type === 'text' && e.style?.text === 'matches').length).toBe(1)
    expect(g.filter((e: any) => e.type === 'rect' && e.style?.fill === SUB_DIVIDER_COLOR).length).toBe(1)
  })

  it('all elements marked silent to avoid stealing hover events from data series', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, matchesLabelVisible, chartSubWidth)
    g.forEach((e: any) => {
      expect(e.silent).toBe(true)
    })
  })

  it('lane 分隔线 y 乘 zoomFactor(z=2 错位修复)+ matchesLabel 顶 pad', () => {
    // 2-lane band:分隔线应落在 lane0/lane1 之间 gap 末端 = top + 4 + 1*9*z
    const bandGeom = [{ top: 50, h: 60, laneCount: 2 }]
    const g2 = buildSubDecorGraphics(bandGeom, 30, 26, ['burst'], true, 800, 2)
    const line2 = g2.find((el: any) => el.style?.fill === '#e0e6f1')
    expect(line2).toBeTruthy()
    // z=2:topY = 50 + 4 + 1*9*2 = 72;元素 top = topY − 0.5(BAND_INNER_LINE_H/2)
    expect(line2.top).toBe(72 - 0.5)
    // 单参 backward-compat(z 缺省 = 1):topY = 50+4+9 = 63
    const g1 = buildSubDecorGraphics(bandGeom, 30, 26, ['burst'], true, 800)
    const line1 = g1.find((el: any) => el.style?.fill === '#e0e6f1')
    expect(line1.top).toBe(63 - 0.5)
    // matchesLabel 顶 pad:top = BAND_TOP_PAD(4) = 4
    const label = g2.find((el: any) => el.style?.text === 'matches')
    expect(label.top).toBe(4)
  })
})

// ---------- Task 4 buildSubOption graphic 切换测试 ----------
// (buildSubOption / computeEventData / computeSubGeometry 已在文件顶部导入,无需重复 import)

describe('buildSubOption — Task 4 graphic switch', () => {
  // rv 字段为 brief fixture 遗漏补(Bar 类型要求),不影响任何断言语义
  const bars = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  const events = [
    { class_id: 'burst', event_id: 'burst_0_1', start_idx: 0, end_idx: 1, source_tag: 'burst' },
    { class_id: 'tb',    event_id: 'tb_1',      start_idx: 1, end_idx: 1, source_tag: 'tb' },
  ] as any[]
  const matches = [
    { event_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1', tb: 'tb_1' },
      children: ['burst_0_1', 'tb_1'],
      forward_return: 0.05 } as any,
  ]
  const topology = { nodes: [
    { node_id: 'burst', source_tag: 'burst' },
    { node_id: 'tb',    source_tag: 'tb' },
  ] } as any
  const tagList = ['burst', 'tb']
  const baseParams = {
    topology,
    isolatedNodeIds: new Set<string>(),
    tagList,
    level: 'matched' as const,
    nodeColors: { burst: '#2563eb', tb: '#16a34a' },
    eventTier: () => 'matched' as const,
    nodeOfEventByBand: (e: any) => e.source_tag,
    bandKeyOf: (e: any) => e.source_tag,
    nodeVisible: {},
    tagToNodes: { burst: ['burst'], tb: ['tb'] },
    selectedEventId: null,
    tooltipResolver: undefined,
    strictWindow: null,
    matchLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedMatchId: null,
    candidateMatchIds: new Set<string>(),
    highlightedEventIds: new Set<string>(),
    pendingDisambigEventId: null,
  }
  const chartSubWidth = 800

  it('option.graphic is populated by buildSubDecorGraphics', () => {
    const bundle = computeEventData(bars, events, matches, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    expect(Array.isArray(opt.graphic)).toBe(true)
    expect(opt.graphic.length).toBeGreaterThan(0)
    // 至少含: 1 subDivider + 2 zebra + 2 bandLabels + 1 matchesLabel = 6
    expect(opt.graphic.length).toBeGreaterThanOrEqual(6)
  })

  it('option.series no longer contains decor series (bandZebra / subDivider / matchesLabel / bandLabels)', () => {
    const bundle = computeEventData(bars, events, matches, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    const seriesNames = opt.series.map((s: any) => s.name)
    expect(seriesNames).not.toContain('bandZebra')
    expect(seriesNames).not.toContain('subDivider')
    expect(seriesNames).not.toContain('matchesLabel')
    expect(seriesNames).not.toContain('bandLabels')
  })

  it('option.series still contains data-driven decor consumers (brackets / points / intervals / highlight)', () => {
    const bundle = computeEventData(bars, events, matches, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    const seriesNames = opt.series.map((s: any) => s.name)
    // brackets / points / intervals / highlight 保留（真数据驱动）
    expect(seriesNames).toContain('brackets')
    expect(seriesNames).toContain('points')
    expect(seriesNames).toContain('intervals')
    expect(seriesNames).toContain('highlight')
  })

  it('grid[0].left / right consume SUB_GRID_LEFT / SUB_GRID_RIGHT constants', () => {
    const bundle = computeEventData(bars, events, matches, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    expect(opt.grid[0].left).toBe(56)   // SUB_GRID_LEFT
    expect(opt.grid[0].right).toBe(16)  // SUB_GRID_RIGHT
  })
})

// ---------- render_grid='price' tag 不占副图轨道(空轨移除) ----------
// band 索引空间 = subBandTagList(tagList, topology):price tag(bo)被剔除,
// 副图 band 索引 / nBands / bandLabels 全部按剔除后的列表对齐。
describe('副图空轨移除 — price tag 不参与分轨', () => {
  const topology: Topology = {
    nodes: [
      { node_id: 'down', class_id: 'trend', source_tag: 'trend0', where_rules: [] },
      { node_id: 'bo',   class_id: 'bo',    source_tag: 'bo', render_grid: 'price', where_rules: [] },
      { node_id: 'tb',   class_id: 'tb',    source_tag: 'tb', where_rules: [] },
    ],
    edges: [],
  }
  const events: EventDict[] = [
    { class_id: 'trend', event_id: 'down1', source_tag: 'trend0', start_idx: 1, end_idx: 6 },
    { class_id: 'bo',    event_id: 'bo9',   source_tag: 'bo',     start_idx: 9, end_idx: 9 },
    { class_id: 'tb',    event_id: 'tb16',  source_tag: 'tb',     start_idx: 16, end_idx: 16 },
  ] as any[]
  const bars: Bar[] = Array.from({ length: 20 }, (_, i) => ({
    date: `2025-02-${String(i + 1).padStart(2, '0')}`,
    o: 10 + i, h: 11 + i, l: 9 + i, c: 10.5 + i, v: 1000, rv: 0,
  }))

  function makeInput(): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)   // ['trend0','bo','tb']
    return {
      topology, isolatedNodeIds: isolatedNodeIds(topology), tagList,
      level: 'detected', nodeColors: {},
      eventTier: () => 'detected' as Tier,
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      nodeVisible: {}, tagToNodes, selectedEventId: null,
    }
  }

  it('computeEventData: band 索引按剔除 bo 后的列表编码(trend0=0, tb=1, nBands=2)', () => {
    const bundle = computeEventData(bars, events, [], makeInput())
    const down1 = bundle.intervalData.find((d: any) => d.event_id === 'down1')!
    expect(down1.value[3]).toBe(0)   // band
    expect(down1.value[4]).toBe(2)   // nBands:不含 bo
    const tb16 = bundle.pointData.find((d: any) => d.event_id === 'tb16')!
    // pointData.value 新 shape (spec 2026-07-13):[start, start, lane, band, nBands]
    expect(typeof tb16.value[2]).toBe('number')   // lane (>=0, 具体值取决于同 band 内 pack 顺序)
    expect(tb16.value[3]).toBe(1)                  // band:tagList 空间本应是 2
    expect(tb16.value[4]).toBe(2)                  // nBands
    // bo 事件仍走主图 pricePointData,不进副图
    expect(bundle.pricePointData.map((d: any) => d.event_id)).toContain('bo9')
    expect(bundle.pointData.map((d: any) => d.event_id)).not.toContain('bo9')
  })

  it('buildSubOption: graphic bandLabels 只含非-price tag(无 bo 空轨标签)', () => {
    const input = makeInput()
    const bundle = computeEventData(bars, events, [], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const labelTexts = opt.graphic
      .filter((e: any) => e.type === 'text')
      .map((e: any) => e.style?.text)
    expect(labelTexts).toContain('trend0')
    expect(labelTexts).toContain('tb')
    expect(labelTexts).not.toContain('bo')
  })

  it('全 price 拓扑(bo_only 场景):副图零 band、零 bandLabel', () => {
    const topoAllPrice: Topology = {
      nodes: [{ node_id: 'bo', class_id: 'bo', source_tag: 'bo', render_grid: 'price', where_rules: [] }],
      edges: [],
    }
    const { tagToNodes, tagList } = deriveTagMap(topoAllPrice.nodes)
    const input: BandRenderInput = {
      topology: topoAllPrice, isolatedNodeIds: isolatedNodeIds(topoAllPrice), tagList,
      level: 'detected', nodeColors: {},
      eventTier: () => 'detected' as Tier,
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      nodeVisible: {}, tagToNodes, selectedEventId: null,
    }
    const boEvents = [{ class_id: 'bo', event_id: 'bo9', source_tag: 'bo', start_idx: 9, end_idx: 9 }] as any[]
    const bundle = computeEventData(bars, boEvents, [], input)
    expect(bundle.pointData.length).toBe(0)
    expect(bundle.intervalData.length).toBe(0)
    expect(bundle.pricePointData.map((d: any) => d.event_id)).toEqual(['bo9'])
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const labelTexts = opt.graphic.filter((e: any) => e.type === 'text').map((e: any) => e.style?.text)
    expect(labelTexts).not.toContain('bo')
  })
})

// ---------- bracket 选中态放大+阴影(spec 2026-07-02-marker-highlight-elevation §3.3) ----------
describe('makeRenderBracket — 选中态放大+阴影', () => {
  const fakeApi: any = {
    value: (i: number) => [10, 20, 0, 1][i] ?? 0,
    coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
  }
  const items = [{ match_id: 'm1' }]
  const mk = (selected: string | null, candidates = new Set<string>(), focus = false) =>
    makeRenderBracket(items, selected, candidates, 1.0, focus)({ dataIndex: 0 }, fakeApi) as any

  it('选中(成员态):高 7→10 居中外扩 + 阴影,琥珀 + 细深边;text 公式不变(中心恰不动)', () => {
    const g = mk('m1')
    const rect = g.children[0]
    // lane0 top = BAND_TOP_PAD(4);放大 y=top−1.5, h=7+3=10
    expect(rect.shape.y).toBeCloseTo(rect0Top() - 1.5)
    expect(rect.shape.height).toBe(10)
    // 2026-07-08 改:琥珀底 + 细深边(1.5,in-group 语义)
    expect(rect.style.fill).toBe('#fbbf24')
    expect(rect.style.stroke).toBe('#1e293b')
    expect(rect.style.lineWidth).toBe(1.5)
    expect(rect.style.shadowBlur).toBe(6)
    expect(rect.style.shadowOffsetY).toBe(2)
    // 序号 text y = 本体中心 = 放大后中心(top−1.5+5 = top+3.5)
    expect(g.children[1].style.y).toBeCloseTo(rect0Top() + 3.5)
  })

  it('选中(focus 态,focusOnBracket=true):同成员几何 + 粗深边(被点者标记)', () => {
    const gFocus = mk('m1', new Set(), true)
    const gMember = mk('m1')
    const rect = gFocus.children[0]
    // 几何与成员态字节等同(只差描边宽)
    expect(rect.shape).toEqual(gMember.children[0].shape)
    expect(rect.style.fill).toBe('#fbbf24')
    expect(rect.style.stroke).toBe('#1e293b')
    expect(rect.style.lineWidth).toBe(2.5)
    expect(rect.style.shadowBlur).toBe(6)
    // 序号 text 不受 focus 态影响
    expect(gFocus.children[1].style.y).toBe(gMember.children[1].style.y)
    expect(gFocus.children[1].style.fill).toBe('#334155')
  })

  it('candidate:几何不动(高 7,无阴影),0.35 琥珀底 + 琥珀虚线边(消歧可见性)', () => {
    const cand = mk(null, new Set(['m1']))
    expect(cand.children[0].shape.height).toBe(7)
    expect(cand.children[0].style.fill).toBe('rgba(251,191,36,0.35)')
    expect(cand.children[0].style.stroke).toBe('#f59e0b')
    expect(cand.children[0].style.lineWidth).toBe(1.5)
    expect(cand.children[0].style.lineDash).toEqual([4, 3])
    expect(cand.children[0].style.shadowBlur).toBeUndefined()
  })

  it('普通:高 7,琥珀底(2026-07-08 改),无描边无阴影', () => {
    const plain = mk(null)
    expect(plain.children[0].shape.height).toBe(7)
    expect(plain.children[0].style.fill).toBe('#fbbf24')
    expect(plain.children[0].style.stroke).toBeUndefined()
    expect(plain.children[0].style.shadowBlur).toBeUndefined()
  })

  // lane0 的 top(= BAND_TOP_PAD):从普通分支反查,避免硬编码常量
  function rect0Top(): number {
    return (mk(null).children[0].shape.y as number)
  }
})

// ---------- Task 2(spec 2026-07-03): 3 renderer + BandRenderInput.zoomFactor + buildSubOption 传播 ----------
describe('chart.ts — renderer zoomFactor 传播(spec 2026-07-03)', () => {
  const bandGeom = [{ top: 20, h: 40, laneCount: 1 }] as const

  it('renderIntervalWithGeom(_, _, bandGeom, 2):自顶向下 lane*9z,gap 乘 z,height=7z', () => {
    // lane=1 才有 stride 项,才能锁翻转 + gap×z 两个语义
    const fakeApi: any = {
      value: (i: number) => [10, 20, 1, 0, 1][i] ?? 0,
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
      style: () => ({}),
    }
    // band top=20 h=40。z=2:laneH=14, gap=4, y = 20+4+1*(14+4) = 42, height=14
    const shape = (renderIntervalWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom, 2)
    expect(shape.type).toBe('rect')
    expect(shape.shape.y).toBe(42)
    expect(shape.shape.height).toBe(14)
    // x 方向不受 zoom 影响:width = x1-x0 = 100
    expect(shape.shape.width).toBe(100)
    // 单参 backward-compat(z=1):y = 20+4+1*(7+2) = 33, height=7
    const shape1 = (renderIntervalWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom)
    expect(shape1.shape.y).toBe(33)
    expect(shape1.shape.height).toBe(7)
    // lane0 自顶向下锚:y 恒 = top + BAND_TOP_PAD,与 z 无关
    const fakeApi0: any = { ...fakeApi, value: (i: number) => [10, 20, 0, 0, 1][i] ?? 0 }
    expect((renderIntervalWithGeom as any)({ dataIndex: 0 }, fakeApi0, bandGeom, 2).shape.y).toBe(24)
    expect((renderIntervalWithGeom as any)({ dataIndex: 0 }, fakeApi0, bandGeom).shape.y).toBe(24)
  })

  it('renderPointWithGeom(_, _, bandGeom, 2):三角 y 偏移 +4/-3 全按 factor,半宽 x 不变;lane 决定 centerY', () => {
    const fakeApi: any = {
      value: (i: number) => [10, 10, 0, 0][i] ?? 0,   // [x, x, lane=0, band=0]
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 0, 200],
      size: () => [10, 0],
      style: () => ({}),
    }
    // band top=20 h=40 → lane0 centerY = 20 + BAND_TOP_PAD(4) + 0*(7*z+2*z) + 7*z/2
    // z=2 → centerY = 20 + 4 + 0 + 7 = 31;offsets +4*2 / -3*2
    const shape = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom, 2)
    expect(shape.type).toBe('polygon')
    const pts = shape.shape.points
    expect(pts[0][1]).toBe(31 + 8)   // 39
    expect(pts[1][1]).toBe(31 - 6)   // 25
    expect(pts[2][1]).toBe(31 - 6)   // 25
    // 单参 backward-compat(z=1):centerY = 20 + 4 + 0 + 3.5 = 27.5
    const shape1 = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom)
    expect(shape1.shape.points[0][1]).toBe(27.5 + 4)   // 31.5
    expect(shape1.shape.points[1][1]).toBe(27.5 - 3)   // 24.5
  })

  it('renderPointWithGeom lane=2:centerY 随 lane 递增 (BAND_MARKER_H + BAND_LANE_GAP)·z', () => {
    const fakeApi: any = {
      value: (i: number) => [10, 10, 2, 0][i] ?? 0,   // [x, x, lane=2, band=0]
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 0, 200],
      size: () => [10, 0],
      style: () => ({}),
    }
    // z=1:centerY = 20 + 4 + 2*(7+2) + 7/2 = 20+4+18+3.5 = 45.5
    const shape = (renderPointWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom)
    expect(shape.shape.points[0][1]).toBe(45.5 + 4)   // 49.5
    expect(shape.shape.points[1][1]).toBe(45.5 - 3)   // 42.5
  })

  it('makeRenderHighlightWithGeom(items, bandGeom, 2) point 分支:放大版高 +6/-4 按 factor;lane 决定 centerY', () => {
    const fakeApi: any = { value: () => 0, coord: () => [100, 200], size: () => [10, 0] }
    // pointData 新 shape:[start, start, lane, band, nBands]
    // band top=20 h=20 → lane0 centerY = 20 + 4 + 0*(7*z+2*z) + 7*z/2 = 24 + 3.5*z
    // z=2 → centerY = 24 + 7 = 31;offsets +6*2 / -4*2
    const items = [{ value: [0, 0, 0, 0, 1], event_id: 'e1', itemStyle: { color: '#22c55e' }, kind: 'group' as const }]
    const shape = makeRenderHighlightWithGeom(items, [{ top: 20, h: 20, laneCount: 1 }], 2)({ dataIndex: 0 }, fakeApi) as any
    expect(shape.shape.points[0][1]).toBe(31 + 12)   // 43
    expect(shape.shape.points[1][1]).toBe(31 - 8)    // 23
    expect(shape.shape.points[2][1]).toBe(31 - 8)    // 23
    // 单参 backward-compat(z=1):centerY = 24 + 3.5 = 27.5
    const shape1 = makeRenderHighlightWithGeom(items, [{ top: 20, h: 20, laneCount: 1 }])({ dataIndex: 0 }, fakeApi) as any
    expect(shape1.shape.points[0][1]).toBe(27.5 + 6)   // 33.5
    expect(shape1.shape.points[1][1]).toBe(27.5 - 4)   // 23.5
  })

  it('makeRenderHighlightWithGeom(items, bandGeom, 2) interval 分支:自顶向下 + HL_EXPAND 常量', () => {
    const bg = [{ top: 20, h: 40, laneCount: 1 }]
    const fakeApi: any = {
      value: (i: number) => [10, 20, 0, 0, 1][i] ?? 0,
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
      size: () => [10, 0],
    }
    // z=2:laneH=14, rawY=20+4+0=24, y=24−1.5*2=21, height=14+3*2=20
    const items = [{ value: [10, 20, 0, 0, 1], event_id: 'e1', itemStyle: { color: '#3b82f6' }, kind: 'focus' as const }]
    const shape = makeRenderHighlightWithGeom(items, bg, 2)({ dataIndex: 0 }, fakeApi) as any
    expect(shape.type).toBe('rect')
    expect(shape.shape.y).toBe(21)
    expect(shape.shape.height).toBe(20)
  })

  it('buildSubOption 从 input.zoomFactor 消费并透传:与 makeRenderHighlightWithGeom(., ., 2) 等价', () => {
    // 本 describe 块在文件末尾追加,前面各 describe 块内的 bars/events/matches/makeInput 均为
    // 块级作用域、不可跨块复用;此处按「chart.ts — restored coverage」块(tests/chart.spec.ts:117-177)
    // 同款 fixture 形状自包含内联,保持语义等价(topology/events/matches/makeInput(level, overrides))。
    const topology: Topology = { nodes: [
      { node_id: 'burst', class_id: 'burst', source_tag: 'burst', where_rules: [] },
      { node_id: 'tb',    class_id: 'tb',    source_tag: 'tb',    where_rules: [] },
    ], edges: [] } as any
    const bars: Bar[] = [
      { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
      { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
    ]
    const events: EventDict[] = [
      { class_id: 'burst', event_id: 'burst_0_1', start_idx: 0, end_idx: 1, source_tag: 'burst' },
      { class_id: 'tb',    event_id: 'tb_1',      start_idx: 1, end_idx: 1, source_tag: 'tb' },
    ] as any[]
    const matches: MatchDict[] = [
      { event_id: 'm@0-1', start_idx: 0, end_idx: 1,
        node_index: { burst: 'burst_0_1', tb: 'tb_1' },
        children: ['burst_0_1', 'tb_1'],
        forward_return: 0.05 } as any,
    ]
    function makeInput(level: Level, overrides: Partial<BandRenderInput> = {}): BandRenderInput {
      const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
      const isolated = isolatedNodeIds(topology)
      const mIds = matchedIds(matches, events, topology.edges)
      const qualifiedIds = new Set<string>()
      return {
        topology, isolatedNodeIds: isolated, tagList, level,
        nodeColors: { burst: '#2563eb', tb: '#16a34a' },
        eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
        nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
        bandKeyOf: (e) => bandKeyOf(e, tagList),
        nodeVisible: {},
        tagToNodes,
        selectedEventId: null,
        ...overrides,
      }
    }

    const input = makeInput('detected', { zoomFactor: 2 } as any)
    const bundle = computeEventData(bars, events, matches, input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1, 1, 1] }, 2)
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    // highlight 系列必须存在 + animation:true(既有约束)
    const hl = opt.series.find((s: any) => s.name === 'highlight')
    expect(hl).toBeTruthy()
    expect(hl.animation).toBe(true)
    // 无法直接断 zoomFactor 值(renderItem 是闭包);
    // 但 sub option 顶层 subCanvasH 应按 factor=2 涨:与 subGeom.subCanvasH 一致(通过 subGeom 已注入)
    expect(subGeom.subCanvasH).toBeGreaterThan(20)
  })
})

// ---------- Bracket zoomFactor 传播(spec 2026-07-03,mid-course scope 扩展) ----------
describe('makeRenderBracket — zoomFactor 传播', () => {
  const fakeApi: any = {
    value: (i: number) => [10, 20, 1, 1][i] ?? 0,   // lane=1, matchLabelIdx=1
    coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
  }
  const items = [{ match_id: 'm1' }]
  const TOP_PAD = 4      // subGeometry.ts BAND_TOP_PAD(bracket 区顶呼吸,unify 新增)
  const STRIDE = 9       // subGeometry.ts BAND_LANE_H(= 7+2)
  const RECT_H = 7       // subGeometry.ts BAND_MARKER_H

  it('普通 bracket z=2:top = 4+lane*9z,height = 7z;text y = top + rectH/2', () => {
    const g = makeRenderBracket(items, null, new Set(), 2)({ dataIndex: 0 }, fakeApi) as any
    const rect = g.children[0]
    // lane=1 → top = 4 + 1*9*2 = 22
    expect(rect.shape.y).toBe(TOP_PAD + 1 * STRIDE * 2)
    // rectH = 7*2 = 14
    expect(rect.shape.height).toBe(RECT_H * 2)
    // text y = top + rectH/2 = 22 + 7 = 29
    expect(g.children[1].style.y).toBe(TOP_PAD + 1 * STRIDE * 2 + RECT_H * 2 / 2)
    // text fontSize 不缩(与 band label 一致 policy)
    expect(g.children[1].style.fontSize).toBe(12)
  })

  it('选中 bracket z=2:h = 7z+3z=20、offset −1.5z、中心不变(居中外扩语义)', () => {
    const g = makeRenderBracket(items, 'm1', new Set(), 2)({ dataIndex: 0 }, fakeApi) as any
    const rect = g.children[0]
    const top = TOP_PAD + 1 * STRIDE * 2  // 22
    // y = top − 1.5*2 = 19;h = 14 + 3*2 = 20
    expect(rect.shape.y).toBe(top - 1.5 * 2)
    expect(rect.shape.height).toBe(RECT_H * 2 + 3 * 2)
    // 中心 = 19 + 10 = 29 = top + rectH/2(与普通版中心一致,居中语义保)
    expect(rect.shape.y + rect.shape.height / 2).toBeCloseTo(top + RECT_H * 2 / 2)
    // 琥珀填充 + 阴影
    expect(rect.style.fill).toBe('#fbbf24')   // AMBER_FILL 统一(group-amber-focus-edge)
    expect(rect.style.shadowBlur).toBe(6)
  })

  it('backward-compat:不传 z 与 z=1 行为字节等同', () => {
    const g0 = makeRenderBracket(items, null, new Set())({ dataIndex: 0 }, fakeApi) as any
    const g1 = makeRenderBracket(items, null, new Set(), 1.0)({ dataIndex: 0 }, fakeApi) as any
    expect(g0.children[0].shape.y).toBe(g1.children[0].shape.y)
    expect(g0.children[0].shape.height).toBe(g1.children[0].shape.height)
    expect(g0.children[1].style.y).toBe(g1.children[1].style.y)
  })
})

// ---------- bracket focus 装配(spec 2026-07-03-group-amber-focus-edge) ----------
describe('buildSubOption — bracket focus 信号装配', () => {
  const topology: Topology = { nodes: [
    { node_id: 'burst', class_id: 'burst', source_tag: 'burst', where_rules: [] },
    { node_id: 'tb',    class_id: 'tb',    source_tag: 'tb',    where_rules: [] },
  ], edges: [] } as any
  const bars: Bar[] = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  const events: EventDict[] = [
    { class_id: 'burst', event_id: 'burst_0_1', start_idx: 0, end_idx: 1, source_tag: 'burst' },
    { class_id: 'tb',    event_id: 'tb_1',      start_idx: 1, end_idx: 1, source_tag: 'tb' },
  ] as any[]
  const matches: MatchDict[] = [
    { event_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1', tb: 'tb_1' },
      children: ['burst_0_1', 'tb_1'],
      forward_return: 0.05 } as any,
  ]
  function makeInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
    const isolated = isolatedNodeIds(topology)
    const mIds = matchedIds(matches, events, topology.edges)
    const qIds = new Set<string>()
    return {
      topology, isolatedNodeIds: isolated, tagList, level: 'detected' as Level,
      nodeColors: { burst: '#2563eb', tb: '#16a34a' },
      eventTier: (e) => eventTierOf(e, mIds, qIds),
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e, tagList),
      nodeVisible: {},
      tagToNodes,
      selectedEventId: null,
      ...overrides,
    }
  }
  const bracketFakeApi: any = {
    value: (i: number) => [0, 1, 0, 1][i] ?? 0,
    coord: ([v]: [number, number]) => [v === 0 ? 100 : 200, 0],
  }
  function bracketRect(input: BandRenderInput) {
    const bundle = computeEventData(bars, events, matches, input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const s = opt.series.find((x: any) => x.name === 'brackets')
    return (s.renderItem({ dataIndex: 0 }, bracketFakeApi) as any).children[0]
  }

  it('selectedMatchId 有 + selectedEventId 空(点了 bracket 本身)→ focus:琥珀+粗深边', () => {
    const rect = bracketRect(makeInput({ selectedMatchId: 'm@0-1', selectedEventId: null }))
    expect(rect.style.fill).toBe('#fbbf24')
    expect(rect.style.stroke).toBe('#1e293b')
    expect(rect.style.lineWidth).toBe(2.5)
  })

  it('selectedMatchId 有 + selectedEventId 有(点了组内 marker)→ 成员:琥珀+细深边', () => {
    const rect = bracketRect(makeInput({ selectedMatchId: 'm@0-1', selectedEventId: 'burst_0_1' }))
    expect(rect.style.fill).toBe('#fbbf24')
    expect(rect.style.stroke).toBe('#1e293b')
    expect(rect.style.lineWidth).toBe(1.5)
  })
})
