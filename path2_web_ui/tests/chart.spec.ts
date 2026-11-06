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
  deriveTagMap, isolatedNodeIds, eventTierOf, nodeOfEventByBand, bandKeyOf, inHitIds,
} from '../src/render/visible'
import type { Bar, EventDict, HitDict, Topology, Level, Tier } from '../src/types'

describe('chart.ts — computeEventData / buildMainOption / buildSubOption', () => {
  // Fixtures(简化最小场景:1 bar / 1 event / 1 hit, 用来验契约与切分正确)
  const bars = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  const events = [
    { instance_id: 'burst_0_1#0', node_id: 'burst', start_idx: 0, end_idx: 1 },
    { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 1, end_idx: 1 },
  ] as any[]
  const hits = [
    { hit_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1#0', tb: 'tb_1#0' },
      children: ['burst_0_1#0', 'tb_1#0'],
      forward_return: 0.05 } as any,
  ]
  const topology = { nodes: [
    { node_id: 'burst' },
    { node_id: 'tb', is_point: true },
  ] } as any
  const tagList = ['burst', 'tb']

  const baseParams = {
    topology,
    isolatedNodeIds: new Set<string>(),
    tagList,
    level: 'in_hit' as const,
    nodeColors: { burst: '#2563eb', tb: '#16a34a' },
    eventTier: () => 'in_hit' as const,
    nodeOfEventByBand: (e: any) => e.node_id,
    bandKeyOf: (e: any) => e.node_id,
    nodeVisible: {},
    tagToNodes: { burst: ['burst'], tb: ['tb'] },
    selectedInstanceId: null,
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
    candidateHitIds: new Set<string>(),
    highlightedEventIds: new Set<string>(),
    pendingDisambigInstanceId: null,
  }

  it('computeEventData bundles points/intervals/brackets/priceAnchored(satellites 已删)', () => {
    const bundle = computeEventData(bars, events, hits, baseParams)
    // burst_0_1 是 interval;tb_1 是 point——按拓扑 node 的 is_point 声明,不按单个实例的起止
    expect(bundle.intervalData.some(d => d.instance_id === 'burst_0_1#0')).toBe(true)
    expect(bundle.pointData.some(d => d.instance_id === 'tb_1#0')).toBe(true)
    expect(bundle.bracketData.length).toBe(1)
    expect(bundle.bracketData[0].hit_id).toBe('m@0-1')
  })

  it('buildMainOption returns option with kline+volume+hit-spanner+price series only (no brackets/points/intervals)', () => {
    const bundle = computeEventData(bars, events, hits, { ...baseParams, hits })
    const opt = buildMainOption(bars, bundle, { ...baseParams, hits }) as any
    const seriesNames = (opt.series ?? []).map((s: any) => s.name)
    expect(seriesNames).toContain('kline')
    expect(seriesNames).toContain('volume')
    expect(seriesNames).toContain('kline-hit-spanner')  // G2 全列 hover 触发 OHLC
    expect(seriesNames).not.toContain('brackets')
    expect(seriesNames).not.toContain('points')
    expect(seriesNames).not.toContain('intervals')
    // price-anchored 主 marker 保留在主图;卫星 pk 通道已删(Task 7)
    expect(seriesNames).toContain('price-points')
    expect(seriesNames).not.toContain('satellites')
    expect(seriesNames).toContain('highlight-price')
    // 主图两个 grid:K 线区 + 下方成交量带
    expect(opt.grid.length).toBe(2)
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
    const bundle = computeEventData(bars, events, hits, baseParams)
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
      { node_id: 'down',  where_rules: [] },
      { node_id: 'side',  where_rules: [] },
      { node_id: 'bo',    render_grid: 'price', where_rules: [] },
      { node_id: 'burst', where_rules: [] },
      { node_id: 'tb',    is_point: true, where_rules: [] },
    ],
    edges: [
      { src: 'down',  dst: 'burst', kind: 'TemporalEdge',    rule: 'before' },
      { src: 'side',  dst: 'burst', kind: 'ContainmentEdge', rule: 'contains' },
      { src: 'burst', dst: 'tb',    kind: 'TemporalEdge',    rule: 'gap=1' },
      // bo 节点孤立(无边):render_grid=price 独立于图结构
    ],
  }

  const events: EventDict[] = [
    { instance_id: 'down1#0',  node_id: 'down',  start_idx: 1,  end_idx: 6  },
    { instance_id: 'side1#0',  node_id: 'side',  start_idx: 4,  end_idx: 12 },
    { instance_id: 'burst1#0', node_id: 'burst', start_idx: 10, end_idx: 15 },
    { instance_id: 'bo9#0', node_id: 'bo', start_idx: 9,  end_idx: 9,
      ref_ids: { broken: ['pk0#0', 'pk1#0'] } } as any,
    { instance_id: 'bo11#0', node_id: 'bo', start_idx: 11, end_idx: 11 },
    { instance_id: 'tb16#0', node_id: 'tb', start_idx: 16, end_idx: 16 },
    // detected-only:未 in_hit、未 qualified
    { instance_id: 'boX#0', node_id: 'bo', start_idx: 20, end_idx: 20 },
    // pk 三态合成/text 派生的引用目标:不在 topology 里(band 不可见,不进任何 output 通道),
    // 只为给 bo9 的 ref_ids.broken 提供 pk_id 反查源(契约 C4/C5,合成发生在 filtered 之前)。
    { instance_id: 'pk0#0', node_id: 'pk_ghost', start_idx: 0, end_idx: 0, peak_idx: 0, pk_id: 0 } as any,
    { instance_id: 'pk1#0', node_id: 'pk_ghost', start_idx: 0, end_idx: 0, peak_idx: 0, pk_id: 1 } as any,
  ] as any[]

  const hits: HitDict[] = [
    {
      hit_id: 'm1', start_idx: 1, end_idx: 16,
      node_index: { down: 'down1#0', side: 'side1#0', burst: 'burst1#0', tb: 'tb16#0' },
      children: ['down1#0', 'side1#0', 'burst1#0', 'tb16#0'],
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
    const mIds = inHitIds(hits, events, topology.edges)
    const qualifiedIds = new Set<string>()
    return {
      topology, isolatedNodeIds: isolated, tagList, level, nodeColors,
      eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e),
      nodeVisible: {},
      tagToNodes,
      selectedInstanceId: null,
      ...overrides,
    }
  }

  // ── 1. level gating: RANK(in_hit>qualified>detected) + boX exclusion at in_hit (chart.ts:110-113) ──
  describe('1. level gating — RANK + boX exclusion at in_hit level', () => {
    it('RANK: level=qualified admits in_hit+qualified tiers, excludes detected-only', () => {
      const stub: EventDict[] = [
        { instance_id: 'eDetected#0',  node_id: 'tb', start_idx: 1, end_idx: 1 },
        { instance_id: 'eQualified#0', node_id: 'tb', start_idx: 2, end_idx: 2 },
        { instance_id: 'eInHit#0',   node_id: 'tb', start_idx: 3, end_idx: 3 },
      ] as any[]
      const tierOf = (e: EventDict): Tier =>
        e.instance_id === 'eInHit#0' ? 'in_hit' : e.instance_id === 'eQualified#0' ? 'qualified' : 'detected'
      const input = makeInput('qualified', { eventTier: tierOf })
      const bundle = computeEventData(bars, stub, [], input)
      const ids = bundle.pointData.map((d) => d.instance_id)
      expect(ids).toContain('eInHit#0')
      expect(ids).toContain('eQualified#0')
      expect(ids).not.toContain('eDetected#0')
    })

    it('level=in_hit: boX (detected-only bo event) excluded from pricePointData; in_hit events remain', () => {
      const input = makeInput('in_hit')
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.pricePointData.map((d) => d.instance_id)).not.toContain('boX#0')
      expect(bundle.intervalData.map((d) => d.instance_id))
        .toEqual(expect.arrayContaining(['down1#0', 'side1#0', 'burst1#0']))
      expect(bundle.pointData.map((d) => d.instance_id)).toContain('tb16#0')
    })

    it('level=detected: boX (and all other tiers) included in pricePointData', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.pricePointData.map((d) => d.instance_id)).toEqual(
        expect.arrayContaining(['bo9#0', 'bo11#0', 'boX#0']),
      )
    })
  })

  // ── 2. render_grid routing + bo 盒文本(ref_ids.broken→pk_id 派生,卫星 pk 通道 hasPks 已删,Task 7) ──
  describe('2. render_grid routing + bo 盒文本(ref_ids.broken 派生,hasPks 已删)', () => {
    it('bo events (render_grid=price) 不进入 grid2 pointData;时间锚定 tb16 仍走 pointData', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      const boInPointData = bundle.pointData.filter((d) => ['bo9#0', 'bo11#0', 'boX#0'].includes(d.instance_id))
      expect(boInPointData.length).toBe(0)
      expect(bundle.pointData.some((d) => d.instance_id === 'tb16#0')).toBe(true)
    })

    it('pricePointData 含全部 3 个 bo 事件(value[0]=start_idx);text 取自 ref_ids.broken 查 pk_id([0,1] / "[]" 兜底)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.pricePointData.map((d) => d.instance_id).sort()).toEqual(['bo11#0', 'bo9#0', 'boX#0'])
      const bo9 = bundle.pricePointData.find((d) => d.instance_id === 'bo9#0')!
      const bo11 = bundle.pricePointData.find((d) => d.instance_id === 'bo11#0')!
      expect(bo9.value[0]).toBe(9)
      expect(bo9.anchorY).toBe(bars[9].h)
      expect(bo9.text).toBe('[0,1]')
      expect(bo11.text).toBe('[]')
    })

    it('satelliteData 通道已删(Task 7):pricePointData 不携带 hasPks 字段', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      // 卫星 pk 通道整体移除 → bundle 不再有 satelliteData 键
      expect((bundle as any).satelliteData).toBeUndefined()
      for (const d of bundle.pricePointData) {
        expect((d as any).hasPks).toBeUndefined()
      }
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
          [{ value: [0, 0, 0, 0, 1], instance_id: 'e1', itemStyle: { color: '#22c55e' }, kind, shape: 'point' as const }],
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

    it('makeRenderHighlightWithGeom: extent 空心细框(族起点→成员终点,不填色);mark 框住那一格(高随档位、底对齐)', () => {
      const bandGeom: BandGeom[] = [{ top: 20, h: 40, laneCount: 1 }]
      const fakeApi: any = {
        value: (i: number) => [10, 20][i] ?? 0,
        coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
        size: () => [10, 0],
      }
      const ext = makeRenderHighlightWithGeom(
        [{ value: [10, 20, 0, 0, 1], instance_id: 'e1', itemStyle: { color: '#3b82f6' }, kind: 'focus', shape: 'extent' }],
        bandGeom,
      )({ dataIndex: 0 }, fakeApi) as any
      expect(ext.type).toBe('rect')
      // 横向:起点中心 −0.4 根 −1 到终点中心 +0.4 根 +1(unitW=10);竖向:lane 顶 24 −1.5、高 7+3
      expect(ext.shape).toEqual({ x: 95, y: 22.5, width: 110, height: 10 })
      expect(ext.style.fill).toBe('none')          // 空心:实心复本会盖住族行里后面的格子
      expect(ext.style.stroke).toBe('#1e293b')
      expect(ext.style.lineWidth).toBe(1.5)
      expect(ext.silent).toBe(true)

      const mark = makeRenderHighlightWithGeom(
        [{ value: [20, 20, 0, 0, 1, 0.4], instance_id: 'e1', itemStyle: { color: '#d1d5db' }, kind: 'focus', shape: 'mark' }],
        bandGeom,
      )({ dataIndex: 0 }, { ...fakeApi, value: (i: number) => [20, 20][i] ?? 0 }) as any
      // 格高 = 7*0.4 = 2.8,底对齐 lane 底(24+7=31);框外扩 1.5
      expect(mark.shape.y).toBeCloseTo(31 - 2.8 - 1.5)
      expect(mark.shape.height).toBeCloseTo(2.8 + 3)
      expect(mark.style.fill).toBe('none')
      expect(mark.style.lineWidth).toBe(2.5)
      expect(mark.keyframeAnimation).toBeUndefined()
      const pend = makeRenderHighlightWithGeom(
        [{ value: [20, 20, 0, 0, 1, 1], instance_id: 'e1', kind: 'pendingDisambig', shape: 'mark' }],
        bandGeom,
      )({ dataIndex: 0 }, { ...fakeApi, value: (i: number) => [20, 20][i] ?? 0 }) as any
      expect(pend.keyframeAnimation).toMatchObject({ duration: 1200, loop: true })
    })

    // 主图 bo 盒放大版:实心版会遮住本体文字 → 必须重画盒+文本(字号不变)。
    // 2026-07-08 改:group/focus 保 node/tier 分色(itemStyle.color) + 细/粗深边、shadow;
    // 文字统一深灰蓝(橙/灰底皆可读);pending 白底+闪烁分层用 color 而非 tier bg,文字统一深灰蓝。
    it('makeRenderPricePointHighlight: 放大盒+text 重画 — group node色+细深边, focus node色+粗深边, pending 白底+闪', () => {
      const fakeApi: any = { value: () => 0, coord: () => [100, 200] }
      const mk = (kind: 'group' | 'focus' | 'pendingDisambig') =>
        makeRenderPricePointHighlight([
          { value: [0, 0], instance_id: 'e1', anchorY: 1, text: '[1]',
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
        { instance_id: 'eGroup#0',   node_id: 'tb', start_idx: 1, end_idx: 1 },
        { instance_id: 'ePending#0', node_id: 'tb', start_idx: 2, end_idx: 2 },
        { instance_id: 'eFocus#0',   node_id: 'tb', start_idx: 3, end_idx: 3 },
      ] as any[]
      const input = makeInput('detected', {
        // 实例流:highlightedEventIds 集合元素为 instance_id 字符串(marker 的 instance_id 匹配)
        highlightedEventIds: new Set(['eGroup#0']),
        pendingDisambigInstanceId: 'ePending#0',
        // 1 归属:合并 ref(selectedInstanceId)= focusedInstanceId;focus 响应当前聚焦实例
        selectedInstanceId: 'eFocus#0',
        focusedInstanceId: 'eFocus#0',
      })
      const bundle = computeEventData(bars, stub, [], input)
      expect(bundle.highlightData.map((d: any) => d.kind)).toEqual(['group', 'pendingDisambig', 'focus'])
      expect(bundle.highlightData.map((d: any) => d.instance_id)).toEqual(['eGroup#0', 'ePending#0', 'eFocus#0'])
    })

    // 被点 marker 同属 highlight 集合(点击链路必然如此):若同时出 group + focus
    // 两层同坐标实心放大版,阴影叠加会让被点者投影明显深于组员。
    // 故 group 条目跳过焦点实例,被点 marker 由 focus 条目独家表达。
    it('焦点实例 ∈ highlightedEventIds 时只出 focus 条目,不出 group 条目', () => {
      const stub: EventDict[] = [
        { instance_id: 'eSel#0',   node_id: 'tb', start_idx: 1, end_idx: 1 },
        { instance_id: 'eOther#0', node_id: 'tb', start_idx: 2, end_idx: 2 },
      ] as any[]
      const input = makeInput('detected', {
        // 实例流:instance_id 集合;1 归属合并 ref(selectedInstanceId)= focusedInstanceId;
        // group 排除仍按 focusedInstanceId 精确(同值)
        highlightedEventIds: new Set(['eSel#0', 'eOther#0']),
        selectedInstanceId: 'eSel#0',
        focusedInstanceId: 'eSel#0',
      })
      const bundle = computeEventData(bars, stub, [], input)
      const ofSel = bundle.highlightData.filter((d: any) => d.instance_id === 'eSel#0')
      expect(ofSel.map((d: any) => d.kind)).toEqual(['focus'])
      const ofOther = bundle.highlightData.filter((d: any) => d.instance_id === 'eOther#0')
      expect(ofOther.map((d: any) => d.kind)).toEqual(['group'])
    })

    // 0 归属(detected/qualified marker click,不在任何 hit)也须画 focus 黑框:
    // focusEvent 走 0 归属分支设 selectedInstanceId、focusedInstanceId=null;chart 的
    // selectedInstanceId 参数=合并 ref(=该实例),focus 分支须响应它,否则点击不出黑框。
    it('0 归属(selectedInstanceId 非空 / focusedInstanceId null)marker 也画 focus 黑框', () => {
      const stub: EventDict[] = [
        { instance_id: 'eSel#0', node_id: 'tb', start_idx: 1, end_idx: 1 },
      ] as any[]
      const input = makeInput('detected', {
        selectedInstanceId: 'eSel#0',
        focusedInstanceId: null,
      })
      const bundle = computeEventData(bars, stub, [], input)
      expect(bundle.highlightData.filter((d: any) => d.instance_id === 'eSel#0').map((d: any) => d.kind)).toEqual(['focus'])
    })

    it('buildMainOption: highlight-price z(21) > price-points z(12);satellites 系列已删(Task 7)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      const opt = buildMainOption(bars, bundle, input) as any
      const S = (name: string) => opt.series.find((s: any) => s.name === name)
      expect(S('highlight-price').z).toBe(21)
      expect(S('price-points').z).toBe(12)
      expect(S('satellites')).toBeUndefined()
      expect(S('highlight-price').z).toBeGreaterThan(S('price-points').z)
    })

    // keyframeAnimation 受 series 级 isAnimationEnabled() 闸控(实测):
    // 顶层 animation:false 会连带跳过闪烁 → 两 highlight 系列必须显式 animation:true。
    it('highlight 系列显式 animation:true(顶层 animation:false 下 keyframeAnimation 才生效)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      const mainOpt = buildMainOption(bars, bundle, input) as any
      expect(mainOpt.animation).toBe(false)
      expect(mainOpt.series.find((s: any) => s.name === 'highlight-price').animation).toBe(true)

      const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1, 1, 1] })
      const subOpt = buildSubOption(bars, bundle, subGeom, input, 800) as any
      expect(subOpt.animation).toBe(false)
      expect(subOpt.series.find((s: any) => s.name === 'highlight').animation).toBe(true)
    })
  })

  // ── 4. endNode → bracketData.instance_id (chart.ts:200-204, §7-4) ──
  describe('4. endNode → bracketData.instance_id', () => {
    it('endNode 缺省时 bracketData 只带 hit_id 不带 instance_id(向后兼容)', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.bracketData.length).toBeGreaterThan(0)
      for (const d of bundle.bracketData) {
        expect(d.hit_id).toBe('m1')
        expect(d.instance_id).toBeUndefined()
      }
    })

    it("endNode='tb' 时 bracketData.instance_id = node_index.tb(instance_id 字符串直用)", () => {
      const input = makeInput('detected', { endNode: 'tb' })
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.bracketData[0].instance_id).toBe('tb16#0')
    })

    it('endNode 指向不存在的 node 时 instance_id 安全降级为 undefined(不崩溃)', () => {
      const input = makeInput('detected', { endNode: 'nonexistent' })
      expect(() => computeEventData(bars, events, hits, input)).not.toThrow()
      const bundle = computeEventData(bars, events, hits, input)
      expect(bundle.bracketData[0].instance_id).toBeUndefined()
    })

    it('node_index 值已是 instance_id 字符串时直用(实例流契约)', () => {
      const refHits: HitDict[] = [{
        hit_id: 'mk', start_idx: 1, end_idx: 16,
        node_index: { tb: 'tb16#0', down: 'down1#0', side: 'side1#0', burst: 'burst1#0' },
        children: ['down1#0', 'side1#0', 'burst1#0', 'tb16#0', 'tb18#0'],
        predicate_trace: { where_results: {}, edge_results: {} },
      }]
      const input = makeInput('detected', { endNode: 'tb' })
      const bundle = computeEventData(bars, events, refHits, input)
      expect(bundle.bracketData[0].instance_id).toBe('tb16#0')
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
  const hitsLabelVisible = true
  const chartSubWidth = 800
  const expectedRectWidth = chartSubWidth - SUB_GRID_LEFT - SUB_GRID_RIGHT  // 728

  it('returns non-empty array of graphic elements', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    expect(Array.isArray(g)).toBe(true)
    expect(g.length).toBeGreaterThan(0)
  })

  it('contains exactly 1 subDivider rect', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const dividers = g.filter((e: any) => e.type === 'rect' && e.style?.fill === SUB_DIVIDER_COLOR)
    expect(dividers.length).toBe(1)
    expect(dividers[0].top).toBe(dividerY - SUB_DIVIDER_H / 2)
    expect(dividers[0].left).toBe(SUB_GRID_LEFT)
    expect(dividers[0].shape.width).toBe(expectedRectWidth)
    expect(dividers[0].shape.height).toBe(SUB_DIVIDER_H)
    expect(dividers[0].z).toBe(2)
  })

  it('contains 2 zebra rects (one per band)', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
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
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
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
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
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

  it('contains 1 hitsLabel when hitsLabelVisible=true', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const hits = g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits')
    expect(hits.length).toBe(1)
    // hits label 靠 bracket 区上边(BAND_TOP_PAD,与 bandLabels 顶 pad 对称),同款 verticalAlign:'top'
    expect(hits[0].top).toBe(BAND_TOP_PAD)
    expect(hits[0].left).toBe(SUB_GRID_LEFT + 2)
    expect(hits[0].style.fontSize).toBe(13)
    expect(hits[0].textVerticalAlign).toBe('top')
    expect(hits[0].textAlign).toBe('left')
    expect(hits[0].z).toBe(5)
  })

  it('omits hitsLabel when hitsLabelVisible=false', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, false, chartSubWidth)
    const hits = g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits')
    expect(hits.length).toBe(0)
  })

  it('handles empty bandGeom (0 bands) gracefully', () => {
    const g = buildSubDecorGraphics([], dividerY, bracketH, [], hitsLabelVisible, chartSubWidth)
    // 空 bandGeom → 无 zebra、无 bandLabel、无 band-inner splitLine
    expect(g.filter((e: any) => e.type === 'rect' && (e.style?.fill === 'rgba(0,0,0,0.03)' || e.style?.fill === 'rgba(0,0,0,0)')).length).toBe(0)
    expect(g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits').length).toBe(1)
    expect(g.filter((e: any) => e.type === 'rect' && e.style?.fill === SUB_DIVIDER_COLOR).length).toBe(1)
  })

  it('all elements marked silent to avoid stealing hover events from data series', () => {
    const g = buildSubDecorGraphics(bandGeom, dividerY, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    g.forEach((e: any) => {
      expect(e.silent).toBe(true)
    })
  })

  it('lane 分隔线 y 乘 zoomFactor(z=2 错位修复)+ hitsLabel 顶 pad', () => {
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
    // hitsLabel 顶 pad:top = BAND_TOP_PAD(4) = 4
    const label = g2.find((el: any) => el.style?.text === 'hits')
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
    { instance_id: 'burst_0_1#0', node_id: 'burst', start_idx: 0, end_idx: 1 },
    { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 1, end_idx: 1 },
  ] as any[]
  const hits = [
    { hit_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1#0', tb: 'tb_1#0' },
      children: ['burst_0_1#0', 'tb_1#0'],
      forward_return: 0.05 } as any,
  ]
  const topology = { nodes: [
    { node_id: 'burst' },
    { node_id: 'tb' },
  ] } as any
  const tagList = ['burst', 'tb']
  const baseParams = {
    topology,
    isolatedNodeIds: new Set<string>(),
    tagList,
    level: 'in_hit' as const,
    nodeColors: { burst: '#2563eb', tb: '#16a34a' },
    eventTier: () => 'in_hit' as const,
    nodeOfEventByBand: (e: any) => e.node_id,
    bandKeyOf: (e: any) => e.node_id,
    nodeVisible: {},
    tagToNodes: { burst: ['burst'], tb: ['tb'] },
    selectedInstanceId: null,
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
    candidateHitIds: new Set<string>(),
    highlightedEventIds: new Set<string>(),
    pendingDisambigInstanceId: null,
  }
  const chartSubWidth = 800

  it('option.graphic is populated by buildSubDecorGraphics', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    expect(Array.isArray(opt.graphic)).toBe(true)
    expect(opt.graphic.length).toBeGreaterThan(0)
    // 至少含: 1 subDivider + 2 zebra + 2 bandLabels + 1 hitsLabel = 6
    expect(opt.graphic.length).toBeGreaterThanOrEqual(6)
  })

  it('option.series no longer contains decor series (bandZebra / subDivider / hitsLabel / bandLabels)', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    const seriesNames = opt.series.map((s: any) => s.name)
    expect(seriesNames).not.toContain('bandZebra')
    expect(seriesNames).not.toContain('subDivider')
    expect(seriesNames).not.toContain('hitsLabel')
    expect(seriesNames).not.toContain('bandLabels')
  })

  it('option.series still contains data-driven decor consumers (brackets / points / intervals / highlight)', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
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
    const bundle = computeEventData(bars, events, hits, baseParams as any)
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
      { node_id: 'down', where_rules: [] },
      { node_id: 'bo',   render_grid: 'price', where_rules: [] },
      { node_id: 'tb',   is_point: true, where_rules: [] },
    ],
    edges: [],
  }
  const events: EventDict[] = [
    { instance_id: 'down1#0', node_id: 'down', start_idx: 1, end_idx: 6 },
    { instance_id: 'bo9#0',   node_id: 'bo',   start_idx: 9, end_idx: 9 },
    { instance_id: 'tb16#0',  node_id: 'tb',   start_idx: 16, end_idx: 16 },
  ] as any[]
  const bars: Bar[] = Array.from({ length: 20 }, (_, i) => ({
    date: `2025-02-${String(i + 1).padStart(2, '0')}`,
    o: 10 + i, h: 11 + i, l: 9 + i, c: 10.5 + i, v: 1000, rv: 0,
  }))

  function makeInput(): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)   // ['down','bo','tb']
    return {
      topology, isolatedNodeIds: isolatedNodeIds(topology), tagList,
      level: 'detected', nodeColors: {},
      eventTier: () => 'detected' as Tier,
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e),
      nodeVisible: {}, tagToNodes, selectedInstanceId: null,
    }
  }

  it('computeEventData: band 索引按剔除 bo 后的列表编码(down=0, tb=1, nBands=2)', () => {
    const bundle = computeEventData(bars, events, [], makeInput())
    const down1 = bundle.intervalData.find((d: any) => d.instance_id === 'down1#0')!
    expect(down1.value[3]).toBe(0)   // band
    expect(down1.value[4]).toBe(2)   // nBands:不含 bo
    const tb16 = bundle.pointData.find((d: any) => d.instance_id === 'tb16#0')!
    // pointData.value 新 shape (spec 2026-07-13):[start, start, lane, band, nBands]
    expect(typeof tb16.value[2]).toBe('number')   // lane (>=0, 具体值取决于同 band 内 pack 顺序)
    expect(tb16.value[3]).toBe(1)                  // band:tagList 空间本应是 2
    expect(tb16.value[4]).toBe(2)                  // nBands
    // bo 事件仍走主图 pricePointData,不进副图
    expect(bundle.pricePointData.map((d: any) => d.instance_id)).toContain('bo9#0')
    expect(bundle.pointData.map((d: any) => d.instance_id)).not.toContain('bo9#0')
  })

  it('buildSubOption: graphic bandLabels 只含非-price tag(无 bo 空轨标签)', () => {
    const input = makeInput()
    const bundle = computeEventData(bars, events, [], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const labelTexts = opt.graphic
      .filter((e: any) => e.type === 'text')
      .map((e: any) => e.style?.text)
    expect(labelTexts).toContain('down')
    expect(labelTexts).toContain('tb')
    expect(labelTexts).not.toContain('bo')
  })

  it('全 price 拓扑(bo_only 场景):副图零 band、零 bandLabel', () => {
    const topoAllPrice: Topology = {
      nodes: [{ node_id: 'bo', render_grid: 'price', where_rules: [] }],
      edges: [],
    }
    const { tagToNodes, tagList } = deriveTagMap(topoAllPrice.nodes)
    const input: BandRenderInput = {
      topology: topoAllPrice, isolatedNodeIds: isolatedNodeIds(topoAllPrice), tagList,
      level: 'detected', nodeColors: {},
      eventTier: () => 'detected' as Tier,
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e),
      nodeVisible: {}, tagToNodes, selectedInstanceId: null,
    }
    const boEvents = [{ instance_id: 'bo9#0', node_id: 'bo', start_idx: 9, end_idx: 9 }] as any[]
    const bundle = computeEventData(bars, boEvents, [], input)
    expect(bundle.pointData.length).toBe(0)
    expect(bundle.intervalData.length).toBe(0)
    expect(bundle.pricePointData.map((d: any) => d.instance_id)).toEqual(['bo9#0'])
    const subGeom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const labelTexts = opt.graphic.filter((e: any) => e.type === 'text').map((e: any) => e.style?.text)
    expect(labelTexts).not.toContain('bo')
  })
})

// ---------- bracket:一族 hit 一行;记号琥珀满高,选中 = 跨度空心框 + 记号深边框,候选 = 细实线框 ----------
describe('makeRenderBracket — 记号、选中、候选、买入日', () => {
  const fakeApi: any = {
    value: (i: number) => [10, 20, 0, 1][i] ?? 0,
    coord: ([v]: [number, number]) => [v === 10 ? 100 : v === 5 ? 50 : 200, 0],
    size: () => [10, 0],
  }
  const mk = (item: any, selected: string | null, candidates = new Set<string>(), focus = false, api = fakeApi) =>
    makeRenderBracket([item], selected, candidates, 1.0, focus)({ dataIndex: 0 }, api) as any
  const mark = { hit_id: 'm1', hit_ids: ['m1'], kind: 'mark' as const, family_start: 10 }

  it('普通:琥珀满高,横向起点中心 −0.4 根到终点中心 +0.4 根,无描边', () => {
    const g = mk(mark, null)
    expect(g.children).toHaveLength(1)
    expect(g.children[0].shape).toEqual({ x: 96, y: 4, width: 108, height: 7 })
    expect(g.children[0].style.fill).toBe('#fbbf24')
    expect(g.children[0].style.stroke).toBeUndefined()
  })

  it('选中:记号深边框(点 bracket 本身粗 2.5、点组内 marker 细 1.5)+ 阴影;族起点早于记号时另画跨度空心框', () => {
    const member = mk(mark, 'm1')
    const box = member.children[member.children.length - 1]
    expect(box.style.fill).toBe('none')
    expect(box.style.stroke).toBe('#1e293b')
    expect(box.style.lineWidth).toBe(1.5)
    expect(box.style.shadowBlur).toBe(6)
    expect(mk(mark, 'm1', new Set(), true).children.at(-1).style.lineWidth).toBe(2.5)
    // family_start == 记号起点:不画跨度框(和记号重合)
    expect(member.children).toHaveLength(2)
    const inFamily = mk({ ...mark, family_start: 5 }, 'm1')
    expect(inFamily.children).toHaveLength(3)
    const ext = inFamily.children[1]
    expect(ext.style.fill).toBe('none')
    expect(ext.style.lineWidth).toBe(1.5)
    expect(ext.shape.x).toBe(50 - 4 - 1)
  })

  it('候选:细实线框,不用虚线(虚线只表示用户画的),不闪', () => {
    const cand = mk(mark, null, new Set(['m1']))
    const box = cand.children[1]
    expect(box.style.stroke).toBe('#1e293b')
    expect(box.style.lineWidth).toBe(1.5)
    expect(box.style.lineDash).toBeUndefined()
    expect(cand.keyframeAnimation).toBeUndefined()
  })

  it('买入日 ▼:黑色三角', () => {
    const buy = mk({ hit_id: 'm1', hit_ids: ['m1'], kind: 'buy' }, null)
    expect(buy.type).toBe('polygon')
    expect(buy.style.fill).toBe('#111111')
  })

  it('zoomFactor:top = 4 + lane·9z,高 7z;不传 z 与 z=1 相同', () => {
    const api = { ...fakeApi, value: (i: number) => [10, 20, 1, 1][i] ?? 0 }
    const g2 = makeRenderBracket([mark], null, new Set(), 2)({ dataIndex: 0 }, api) as any
    expect(g2.children[0].shape.y).toBe(4 + 1 * 9 * 2)
    expect(g2.children[0].shape.height).toBe(14)
    const g0 = makeRenderBracket([mark], null, new Set())({ dataIndex: 0 }, api) as any
    const g1 = makeRenderBracket([mark], null, new Set(), 1.0)({ dataIndex: 0 }, api) as any
    expect(g0.children[0].shape).toEqual(g1.children[0].shape)
  })
})

// ---------- Task 2(spec 2026-07-03): 3 renderer + BandRenderInput.zoomFactor + buildSubOption 传播 ----------
describe('chart.ts — renderer zoomFactor 传播(spec 2026-07-03)', () => {
  const bandGeom = [{ top: 20, h: 40, laneCount: 1 }] as const

  it('renderIntervalWithGeom(_, _, bandGeom, 2):自顶向下 lane*9z,gap 乘 z,height=7z', () => {
    // lane=1 才有 stride 项,才能锁翻转 + gap×z 两个语义
    const fakeApi: any = {
      value: (i: number) => [10, 20, 1, 0, 1][i] ?? 0,
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
      size: () => [10, 0],
      style: () => ({}),
    }
    // band top=20 h=40。z=2:laneH=14, gap=4, y = 20+4+1*(14+4) = 42, height=14
    const shape = (renderIntervalWithGeom as any)({ dataIndex: 0 }, fakeApi, bandGeom, 2)
    expect(shape.type).toBe('rect')
    expect(shape.shape.y).toBe(42)
    expect(shape.shape.height).toBe(14)
    // x 方向不受 zoom 影响:起点中心 −0.4 根到终点中心 +0.4 根(unitW=10)→ 96 .. 204
    expect(shape.shape.x).toBe(96)
    expect(shape.shape.width).toBe(108)
    // 档位按高度分(value[5]=0.4):高 14*0.4,底对齐 lane 底(42+14)
    const low = (renderIntervalWithGeom as any)({ dataIndex: 0 },
      { ...fakeApi, value: (i: number) => [10, 20, 1, 0, 1, 0.4][i] ?? 0 }, bandGeom, 2)
    expect(low.shape.height).toBeCloseTo(5.6)
    expect(low.shape.y).toBeCloseTo(42 + 14 - 5.6)
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
    const items = [{ value: [0, 0, 0, 0, 1], instance_id: 'e1', itemStyle: { color: '#22c55e' }, kind: 'group' as const,
                     shape: 'point' as const }]
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
    // extent,z=2:laneH=14, rawY=20+4+0=24, y=24−1.5*2=21, height=14+3*2=20
    const items = [{ value: [10, 20, 0, 0, 1], instance_id: 'e1', itemStyle: { color: '#3b82f6' }, kind: 'focus' as const,
                     shape: 'extent' as const }]
    const shape = makeRenderHighlightWithGeom(items, bg, 2)({ dataIndex: 0 }, fakeApi) as any
    expect(shape.type).toBe('rect')
    expect(shape.shape.y).toBe(21)
    expect(shape.shape.height).toBe(20)
    // mark,z=2,满高:y = 24+14−14−1.5 = 22.5, height = 14+3
    const markItems = [{ value: [10, 20, 0, 0, 1, 1], instance_id: 'e1', kind: 'focus' as const, shape: 'mark' as const }]
    const m = makeRenderHighlightWithGeom(markItems, bg, 2)({ dataIndex: 0 }, fakeApi) as any
    expect(m.shape.y).toBe(22.5)
    expect(m.shape.height).toBe(17)
  })

  it('buildSubOption 从 input.zoomFactor 消费并透传:与 makeRenderHighlightWithGeom(., ., 2) 等价', () => {
    // 本 describe 块在文件末尾追加,前面各 describe 块内的 bars/events/hits/makeInput 均为
    // 块级作用域、不可跨块复用;此处按「chart.ts — restored coverage」块(tests/chart.spec.ts:117-177)
    // 同款 fixture 形状自包含内联,保持语义等价(topology/events/hits/makeInput(level, overrides))。
    const topology: Topology = { nodes: [
      { node_id: 'burst', where_rules: [] },
      { node_id: 'tb',    is_point: true, where_rules: [] },
    ], edges: [] } as any
    const bars: Bar[] = [
      { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
      { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
    ]
    const events: EventDict[] = [
      { instance_id: 'burst_0_1#0', node_id: 'burst', start_idx: 0, end_idx: 1 },
      { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 1, end_idx: 1 },
    ] as any[]
    const hits: HitDict[] = [
      { hit_id: 'm@0-1', start_idx: 0, end_idx: 1,
        node_index: { burst: 'burst_0_1#0', tb: 'tb_1#0' },
        children: ['burst_0_1#0', 'tb_1#0'],
        forward_return: 0.05 } as any,
    ]
    function makeInput(level: Level, overrides: Partial<BandRenderInput> = {}): BandRenderInput {
      const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
      const isolated = isolatedNodeIds(topology)
      const mIds = inHitIds(hits, events, topology.edges)
      const qualifiedIds = new Set<string>()
      return {
        topology, isolatedNodeIds: isolated, tagList, level,
        nodeColors: { burst: '#2563eb', tb: '#16a34a' },
        eventTier: (e) => eventTierOf(e, mIds, qualifiedIds),
        nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
        bandKeyOf: (e) => bandKeyOf(e),
        nodeVisible: {},
        tagToNodes,
        selectedInstanceId: null,
        ...overrides,
      }
    }

    const input = makeInput('detected', { zoomFactor: 2 } as any)
    const bundle = computeEventData(bars, events, hits, input)
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

// ---------- bracket focus 装配(spec 2026-07-03-group-amber-focus-edge) ----------
describe('buildSubOption — bracket focus 信号装配', () => {
  const topology: Topology = { nodes: [
    { node_id: 'burst', where_rules: [] },
    { node_id: 'tb',    is_point: true, where_rules: [] },
  ], edges: [] } as any
  const bars: Bar[] = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  const events: EventDict[] = [
    { instance_id: 'burst_0_1#0', node_id: 'burst', start_idx: 0, end_idx: 1 },
    { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 1, end_idx: 1 },
  ] as any[]
  const hits: HitDict[] = [
    { hit_id: 'm@0-1', start_idx: 0, end_idx: 1,
      node_index: { burst: 'burst_0_1#0', tb: 'tb_1#0' },
      children: ['burst_0_1#0', 'tb_1#0'],
      forward_return: 0.05 } as any,
  ]
  function makeInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
    const isolated = isolatedNodeIds(topology)
    const mIds = inHitIds(hits, events, topology.edges)
    const qIds = new Set<string>()
    return {
      topology, isolatedNodeIds: isolated, tagList, level: 'detected' as Level,
      nodeColors: { burst: '#2563eb', tb: '#16a34a' },
      eventTier: (e) => eventTierOf(e, mIds, qIds),
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList),
      bandKeyOf: (e) => bandKeyOf(e),
      nodeVisible: {},
      tagToNodes,
      selectedInstanceId: null,
      ...overrides,
    }
  }
  const bracketFakeApi: any = {
    value: (i: number) => [0, 1, 0, 1][i] ?? 0,
    coord: ([v]: [number, number]) => [v === 0 ? 100 : 200, 0],
    size: () => [10, 0],
  }
  function bracketGroup(input: BandRenderInput) {
    const bundle = computeEventData(bars, events, hits, input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    const s = opt.series.find((x: any) => x.name === 'brackets')
    return s.renderItem({ dataIndex: 0 }, bracketFakeApi) as any
  }

  it('selectedHitId 有 + selectedInstanceId 空(点了 bracket 本身)→ focus:琥珀记号 + 粗深边框', () => {
    const g = bracketGroup(makeInput({ selectedHitId: 'm@0-1', selectedInstanceId: null }))
    expect(g.children[0].style.fill).toBe('#fbbf24')
    expect(g.children.at(-1).style.stroke).toBe('#1e293b')
    expect(g.children.at(-1).style.lineWidth).toBe(2.5)
  })

  it('selectedHitId 有 + selectedInstanceId 有(点了组内 marker)→ 成员:琥珀记号 + 细深边框', () => {
    const g = bracketGroup(makeInput({ selectedHitId: 'm@0-1', selectedInstanceId: 'burst_0_1#0' }))
    expect(g.children[0].style.fill).toBe('#fbbf24')
    expect(g.children.at(-1).style.stroke).toBe('#1e293b')
    expect(g.children.at(-1).style.lineWidth).toBe(1.5)
  })
})

// ── 子结构事件 band 路由(tb 段 → tb_seg 泳道;容器留 tb 泳道) ──────────────────
describe('computeEventData — 子结构段经引擎命名表 node_id 直落结构 node 泳道', () => {
  const cbBars = [
    { date: '2025-01-01', o: 10, c: 12, h: 13, l: 9, v: 1000, rv: 0 },
    { date: '2025-01-02', o: 12, c: 11, h: 12.5, l: 10, v: 800, rv: 0 },
  ]
  // 容器 tb_0_1 与两个段(方案 A:children 声明命名表把段直标 node_id='tb_seg')
  const cbEvents = [
    { instance_id: 'tb_0_1#0', node_id: 'tb', start_idx: 0, end_idx: 1,
      child_refs: { segments: ['tb_seg_0_0#0', 'tb_seg_1_1#0'] } },
    { instance_id: 'tb_seg_0_0#0', node_id: 'tb_seg', start_idx: 0, end_idx: 0, child_refs: {} },
    { instance_id: 'tb_seg_1_1#0', node_id: 'tb_seg', start_idx: 1, end_idx: 1, child_refs: {} },
  ] as any[]
  const cbTopology = { nodes: [
    { node_id: 'tb' },
    { node_id: 'tb_seg', parent_refs: [['tb', 'segments']] },
  ], edges: [] } as any
  const cbParams = {
    topology: cbTopology,
    isolatedNodeIds: new Set<string>(),
    tagList: ['tb', 'tb_seg'],
    level: 'in_hit' as const,
    nodeColors: { tb: '#D60000', tb_seg: '#16a34a' },
    eventTier: () => 'in_hit' as const,
    nodeOfEventByBand: (e: any) => e.node_id,
    bandKeyOf: (e: any) => e.node_id,                  // 段自带 node_id='tb_seg',直连即分轨
    nodeVisible: {},
    tagToNodes: { tb: ['tb'], tb_seg: ['tb_seg'] },
    selectedInstanceId: null,
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
    candidateHitIds: new Set<string>(),
    highlightedEventIds: new Set<string>(),
    pendingDisambigInstanceId: null,
  }

  it('段事件落 tb_seg 泳道(band=1)且用 tb_seg 的色;容器留 tb 泳道(band=0)用 tb 色', () => {
    const bundle = computeEventData(cbBars, cbEvents, [], cbParams as any)
    // subTags = ['tb','tb_seg'](render_grid 缺省 'time,均进副图)
    const seg0 = bundle.intervalData.find((d: any) => d.instance_id === 'tb_seg_0_0#0')
    const seg1 = bundle.intervalData.find((d: any) => d.instance_id === 'tb_seg_1_1#0')
    // 单 bar 段(start==end)走 pointData
    const segRec = seg0 ?? bundle.pointData.find((d: any) => d.instance_id === 'tb_seg_0_0#0')
    const segRec2 = seg1 ?? bundle.pointData.find((d: any) => d.instance_id === 'tb_seg_1_1#0')
    expect(segRec).toBeDefined()
    expect(segRec2).toBeDefined()
    expect(segRec.value[3]).toBe(1)                     // tb_seg 泳道序
    expect(segRec.itemStyle.color).toBe('#16a34a')      // tb_seg 的色,非 tb 红
    const cont = bundle.intervalData.find((d: any) => d.instance_id === 'tb_0_1#0')
    expect(cont).toBeDefined()
    expect(cont.value[3]).toBe(0)                       // 容器留 tb 泳道
    expect(cont.itemStyle.color).toBe('#D60000')
  })

  it('未声明 app 的段(node_id=tb,旧形态)→ 拓扑仅 tb → 全落 tb 泳道同色', () => {
    const legacyEvents = [
      { instance_id: 'tb_0_1#0', node_id: 'tb', start_idx: 0, end_idx: 1,
        child_refs: { segments: ['tb_0_0#0'] } },
      { instance_id: 'tb_0_0#0', node_id: 'tb', start_idx: 0, end_idx: 0, child_refs: {} },
    ] as any[]
    const noSegTopology = { nodes: [{ node_id: 'tb' }], edges: [] } as any
    const bundle = computeEventData(cbBars, legacyEvents, [],
      { ...cbParams, topology: noSegTopology, tagList: ['tb'],
        tagToNodes: { tb: ['tb'] } } as any)
    const cont = bundle.intervalData.find((d: any) => d.instance_id === 'tb_0_1#0')
    expect(cont.value[3]).toBe(0)
    // 段与容器同泳道同色(node_id 分组,无子结构 node 可落)
    const segRec = bundle.pointData.find((d: any) => d.instance_id === 'tb_0_0#0')
      ?? bundle.intervalData.find((d: any) => d.instance_id === 'tb_0_0#0')
    expect(segRec.value[3]).toBe(0)
    expect(segRec.itemStyle.color).toBe('#D60000')
  })
})
