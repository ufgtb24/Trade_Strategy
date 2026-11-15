// chart.spec.ts — computeEventData / buildMainOption / buildSubOption 契约测试
// (Task 6: 旧 buildKlineOption 单函数 API 及其所有专属测试已随函数删除;本文件只保留
//  仍对应存活 API 的契约测试。内联最小 fixture,自包含,不依赖外部 ANALYSIS。)
import { describe, it, expect } from 'vitest'
import {
  computeEventData,
  buildMainOption,
  buildSubOption,
  makeRenderSelection,
  makeRenderPriceFrame,
  makeRenderBracket,
  SELECTION_SERIES,
  renderIntervalWithGeom,
  renderPointWithGeom,
} from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { MARK_ENLARGE_Y, NO_HIGHLIGHT, POINT_ENLARGE_Y, RELATED_EDGE_DARKEN, RELATED_EDGE_W, highlightOf,
         type Highlight } from '../src/render/selHighlight'
import { BAND_LANE_GAP, MARK_GROW } from '../src/render/subGeometry'
import { darken } from '../src/render/colors'
import { foldBand } from '../src/render/fold'
import { boundEvents, hitOrderOf, usingIndex } from '../src/render/walk'
import { makeWorld, type WorldCtx } from '../src/render/selWorld'
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
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
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
    expect(seriesNames).toContain('selection-price')
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
// 旧 buildKlineOption 已删,这些行为现活在 computeEventData / buildMainOption / buildSubOption 里;
// fixture 复刻自 95f5554 版 chart.spec.ts 的 5-node 拓扑
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

  // ── 3. 选中后的粗框、外层底线、照常 / 画淡 + z-order ──
  describe('3. selection frame / underline / dim + z-order', () => {
    const hlOf = (over: Partial<Highlight>): Highlight => ({ ...NO_HIGHLIGHT, ...over })
    const sel = (instanceId: string): Highlight['focus'] => ({ kind: 'event', instanceId })

    it('makeRenderSelection:band 上的点外扩描深边(2.5、不填色、无阴影);格框高随档位、底对齐;外层底线压在行底', () => {
      const bandGeom: BandGeom[] = [{ top: 20, h: 40, laneCount: 1 }]
      const api: any = { value: () => 0, coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0], size: () => [10, 0] }
      const render = (it: any) => makeRenderSelection([it], bandGeom)({ dataIndex: 0 }, api) as any
      const pt = render({ kind: 'frame', target: 'band', shape: 'point', value: [10, 10, 0, 0, 1, 1] })
      expect(pt.type).toBe('polygon')
      expect(pt.style).toEqual({ fill: 'none', stroke: '#1e293b', lineWidth: 2.5 })
      expect(pt.style.shadowBlur).toBeUndefined()
      expect(pt.silent).toBe(true)
      // lane0 centerY = 20 + 4 + 3.5 = 27.5;半宽 = max(5, min(20, 10*0.35)) = 5;各顶点外推 1.5(横向 3)
      expect(pt.shape.points).toEqual([[100, 27.5 + 4 + 3], [100 - 5 - 3, 27.5 - 3 - 1.5], [100 + 5 + 3, 27.5 - 3 - 1.5]])

      const mark = render({ kind: 'frame', target: 'band', shape: 'mark', value: [20, 20, 0, 0, 1, 0.4] })
      // 格高 = 7*0.4 = 2.8,底对齐 lane 底(24+7=31);框外扩 1.5
      expect(mark.shape.y).toBeCloseTo(31 - 2.8 - 1.5)
      expect(mark.shape.height).toBeCloseTo(2.8 + 3)
      expect(mark.style).toEqual({ fill: 'none', stroke: '#1e293b', lineWidth: 2.5 })

      const under = render({ kind: 'under', target: 'band', value: [10, 20, 0, 0, 1] })
      // 横跨起点中心 −0.4 根到终点中心 +0.4 根;压在 lane 底(31)上,高 2.5
      expect(under.shape).toEqual({ x: 96, y: 30, width: 108, height: 2.5 })
      expect(under.style.fill).toBe('#1e293b')
    })

    it('makeRenderSelection:hits 行的格位粗框、一族底线;个数压在竖线上面、描白边;只有一次、没留个数行、K 线比数字窄时不写', () => {
      const api: any = { value: () => 0, coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0], size: () => [10, 0] }
      const tops = [30]
      const render = (it: any, laneTops?: number[]) =>
        makeRenderSelection([it], [], 1, 4, laneTops)({ dataIndex: 0 }, api) as any
      const frame = render({ kind: 'frame', target: 'hits', value: [10, 10, 0] }, tops)
      expect(frame.shape).toEqual({ x: 94.5, y: 28.5, width: 11, height: 10 })
      expect(frame.style).toEqual({ fill: 'none', stroke: '#1e293b', lineWidth: 2.5 })
      const under = render({ kind: 'under', target: 'hits', value: [10, 20, 0] }, tops)
      expect(under.shape).toEqual({ x: 96, y: 36, width: 108, height: 2.5 })
      const count = render({ kind: 'count', target: 'hits', value: [10, 10, 0], n: 2, dim: false }, tops)
      expect(count.type).toBe('text')
      expect(count.style).toMatchObject({ text: '2', x: 100, y: 29, verticalAlign: 'bottom', fill: '#111111', stroke: '#ffffff' })
      expect(count.style.opacity).toBeUndefined()
      // 画淡只淡数字:白边不透明(竖线不从淡了的数字里透出来)
      const dimmed = render({ kind: 'count', target: 'hits', value: [10, 10, 0], n: 2, dim: true }, tops).style
      expect([dimmed.fill, dimmed.stroke, dimmed.opacity]).toEqual(['rgba(17, 17, 17, 0.5)', '#ffffff', undefined])
      expect(render({ kind: 'count', target: 'hits', value: [10, 10, 0], n: 2 }).children).toEqual([])   // 没留个数行
      expect(render({ kind: 'count', target: 'hits', value: [10, 10, 0], n: 1 }, tops).children).toEqual([])   // 只有一次
      const narrow = makeRenderSelection([{ kind: 'count', target: 'hits', value: [10, 10, 0], n: 2 }], [], 1, 4, tops)(
        { dataIndex: 0 }, { ...api, size: () => [3, 0] }) as any
      expect(narrow.children).toEqual([])                                                     // 一根 3px,比数字窄
      // 行的顶照 laneTops 取(有个数行时行距不等):第二行顶在 30,数字下沿在 30 − 1
      expect(render({ kind: 'count', target: 'hits', value: [10, 10, 1], n: 2 }, [4, 30]).style.y).toBe(30 - 1)
      expect(render({ kind: 'count', target: 'hits', value: [10, 10, 0], n: 2 }, [4, 30]).style.y).toBe(4 - 1)
    })

    it('makeRenderPriceFrame:bo 盒外扩描深边、不填色;外层底线画在盒下', () => {
      const api: any = { value: () => 0, coord: () => [100, 200] }
      const mk = (kind: 'frame' | 'under') => makeRenderPriceFrame([
        { value: [0, 0], anchorY: 1, text: '[1]', kind },
      ])({ dataIndex: 0 }, api) as any
      const f = mk('frame')
      expect(f.type).toBe('rect')
      expect(f.style).toEqual({ fill: 'none', stroke: '#1e293b', lineWidth: 2.5 })
      expect(f.shape.r).toBe(5.5)            // BO_BOX_RADIUS(4) + 外扩 1.5
      const u = mk('under')
      expect(u.shape.y).toBeGreaterThan(f.shape.y + f.shape.height - 1.5)
      expect(u.style.fill).toBe('#1e293b')
    })

    it('computeEventData:选中的 event 出一条粗框;外层 event 出底线;价格区 node 走主图那一份', () => {
      const input = makeInput('detected', {
        highlight: hlOf({ focus: sel('tb16#0'), under: { ...NO_HIGHLIGHT.under, events: new Set(['burst1#0', 'bo9#0']) } }),
      })
      const bundle = computeEventData(bars, events, hits, input)
      const frames = bundle.frameData.filter((d: any) => d.kind !== 'count')
      expect(frames).toEqual([
        { kind: 'frame', target: 'band', shape: 'point', value: [16, 16, 0, 3, 4, 1, 1], instance_id: 'tb16#0' },
        { kind: 'under', target: 'band', value: [10, 15, 0, 2, 4], instance_id: 'burst1#0' },
      ])
      expect(bundle.framePriceData.map((d: any) => [d.instance_id, d.kind])).toEqual([['bo9#0', 'under']])
    })

    it('computeEventData:有关的三角、格、条竖直放大(value[6]),粗框跟着同一倍数;无关的、两个灰档里都不放大', () => {
      const related = hlOf({ focus: sel('tb16#0'), appRelated: new Set(['tb16#0', 'burst1#0', 'bo9#0']) })
      const b = computeEventData(bars, events, hits, makeInput('in_hit', { highlight: related }))
      const v6 = (arr: any[], id: string) => arr.find((d: any) => d.instance_id === id).value[6]
      expect(v6(b.pointData, 'tb16#0')).toBe(POINT_ENLARGE_Y)
      expect(v6(b.intervalData, 'burst1#0')).toBe(MARK_ENLARGE_Y)
      expect(v6(b.intervalData, 'down1#0')).toBe(1)                     // 无关的
      expect(b.frameData.find((d: any) => d.kind === 'frame').value[6]).toBe(POINT_ENLARGE_Y)
      // 灰档:格高、三角大小表示档位,有关的也不放大
      const g = computeEventData(bars, events, hits, makeInput('detected', { highlight: related }))
      expect(v6(g.pointData, 'tb16#0')).toBe(1)
      expect(v6(g.intervalData, 'burst1#0')).toBe(1)
      expect(g.pricePointData.find((d: any) => d.instance_id === 'bo9#0').sy).toBe(1)
    })

    it('renderIntervalWithGeom:格放大后往上长,底不动、长进行间空隙但留一道缝', () => {
      const geom = [{ top: 0, h: 60 }] as any
      const mk = (sy: number) => renderIntervalWithGeom({}, {
        coord: ([x]: number[]) => [x * 10, 0], size: () => [10, 0], style: () => ({}),
        value: (i: number) => [5, 5, 1, 0, 1, 1, sy][i],
      }, geom, 1) as any
      const [a, b] = [mk(1).shape, mk(MARK_ENLARGE_Y).shape]
      expect(b.y + b.height).toBeCloseTo(a.y + a.height)                 // 底对齐不动
      expect(b.height - a.height).toBeGreaterThan(0)
      expect(b.height - a.height).toBeLessThan(BAND_LANE_GAP)            // 不长满空隙,和上一行之间留缝
    })

    it('renderPointWithGeom:放大只改高、不改宽', () => {
      const geom = [{ top: 0, height: 40 }] as any
      const mk = (sy: number) => renderPointWithGeom({}, {
        coord: () => [100, 0], size: () => [10, 0], style: () => ({}),
        value: (i: number) => [5, 5, 0, 0, 1, 1, sy][i],
      }, geom, 1) as any
      const [a, b] = [mk(1).shape.points, mk(POINT_ENLARGE_Y).shape.points]
      expect(b[2][0] - b[1][0]).toBeCloseTo(a[2][0] - a[1][0])            // 宽不变
      expect(b[0][1] - b[1][1]).toBeCloseTo((a[0][1] - a[1][1]) * POINT_ENLARGE_Y)   // 高 ×1.4
    })

    it('computeEventData:有关的照常,app 那一边其余的画淡(不透明度 0.5);没选中时一个都不淡', () => {
      const plain = computeEventData(bars, events, hits, makeInput('detected'))
      expect([...plain.intervalData, ...plain.pointData].every((d: any) => d.itemStyle.opacity === undefined)).toBe(true)
      expect(plain.pricePointData.every((d: any) => d.dim === false)).toBe(true)

      const input = makeInput('detected', {
        highlight: hlOf({ focus: sel('tb16#0'), dimApp: true, appEvents: new Set(['tb16#0', 'burst1#0']) }),
      })
      const bundle = computeEventData(bars, events, hits, input)
      const op = (id: string) => [...bundle.intervalData, ...bundle.pointData].find((d: any) => d.instance_id === id).itemStyle.opacity
      expect(op('burst1#0')).toBeUndefined()
      expect(op('tb16#0')).toBeUndefined()
      expect(op('down1#0')).toBe(0.5)
      expect(bundle.pricePointData.find((d: any) => d.instance_id === 'bo9#0').dim).toBe(true)
      expect(bundle.familyLineData.find((d: any) => d.family_key.startsWith('down@')).dim).toBe(true)
      // hits 行:这一次没被牵出,也不在同一层 → 画淡
      expect(bundle.bracketData.every((d: any) => d.dim === true)).toBe(true)
      expect(bundle.bracketLineData.every((d: any) => d.dim === true)).toBe(true)
    })

    it('buildMainOption:价格区粗框 selection-price z(21) > price-points z(12),不接鼠标;旧的放大复本系列已删', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      const opt = buildMainOption(bars, bundle, input) as any
      const S = (name: string) => opt.series.find((s: any) => s.name === name)
      expect(S('selection-price').z).toBe(21)
      expect(S('selection-price').silent).toBe(true)
      expect(S('price-points').z).toBe(12)
      expect(S('highlight-price')).toBeUndefined()
      expect(S('satellites')).toBeUndefined()
    })

    it('buildSubOption:粗框、底线、个数那一层压在当前日竖线(最下层)上面、轨名下面;不再有闪烁动画', () => {
      const input = makeInput('detected')
      const bundle = computeEventData(bars, events, hits, input)
      const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1, 1, 1] })
      const subOpt = buildSubOption(bars, bundle, subGeom, input, 800) as any
      const S = (name: string) => subOpt.series.find((s: any) => s.name === name)
      expect(S('highlight')).toBeUndefined()
      expect(S(SELECTION_SERIES).z).toBe(31)
      expect(S(SELECTION_SERIES).z).toBeGreaterThan(S('current-day').z)
      expect(S(SELECTION_SERIES).silent).toBe(true)
      expect(subOpt.series.every((s: any) => s.animation !== true)).toBe(true)
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
  HITS_FILL,
  DIVIDER_GAP,
  SUB_GRID_RIGHT,
  SUB_ROW_LEFT,
  SUB_TITLE_LEFT,
  SUB_TITLE_Z,
} from '../src/render/subGeometry'

describe('buildSubDecorGraphics — Task 3', () => {
  // fixture: 2 bands, laneCount = [1, 3]; bracketH=6 (1 bracket lane); chartSubWidth=800
  const bandGeom = [
    { top: 22, h: 21, laneCount: 1 },      // band 0: no inner splitLine (laneCount=1)
    { top: 43, h: 35, laneCount: 3 },      // band 1: 2 inner splitLines (between 3 lanes)
  ]
  const bracketH = 6
  const bandLabelTexts = ['bo', 'burst']
  const hitsLabelVisible = true
  const chartSubWidth = 800
  const expectedRectWidth = chartSubWidth - SUB_ROW_LEFT - SUB_GRID_RIGHT  // 784:行从容器最左起,盖住左边的轨名栏

  it('returns non-empty array of graphic elements', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    expect(Array.isArray(g)).toBe(true)
    expect(g.length).toBeGreaterThan(0)
  })

  it('轨名不接鼠标、不描边(node 不能选中)', () => {
    const labels = (g: any[]) => g.filter((e) => e.type === 'text' && ['bo', 'burst'].includes(e.style.text))
    const plain = labels(buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth))
    expect(plain.map((e) => e.silent)).toEqual([true, true])
    expect(plain.every((e) => e.onclick === undefined && e.style.borderWidth === undefined)).toBe(true)
  })

  it('hits 区垫浅黄底、一直铺到第一条 band 的顶;hits 与 band 之间不画分隔线', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const bg = g.filter((e: any) => e.type === 'rect' && e.style?.fill === HITS_FILL)
    expect(bg.length).toBe(1)
    expect(bg[0].top).toBe(0)
    expect(bg[0].left).toBe(SUB_ROW_LEFT)
    expect(bg[0].shape.width).toBe(expectedRectWidth)
    expect(bg[0].shape.height).toBe(bracketH + DIVIDER_GAP)
    expect(bg[0].z).toBe(1)
    expect(g.filter((e: any) => e.type === 'rect' && e.style?.fill === '#94a3b8')).toHaveLength(0)
    // 没有 hit 时不垫
    const none = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, false, chartSubWidth)
    expect(none.filter((e: any) => e.type === 'rect' && e.style?.fill === HITS_FILL)).toHaveLength(0)
    // compare:hits 区顶是两区之间的分界线,底从那里起
    const cmp = buildSubDecorGraphics(bandGeom, 60, bandLabelTexts, true, chartSubWidth, 1, {}, [], 46, [], 40)
    const cbg = cmp.find((e: any) => e.type === 'rect' && e.style?.fill === HITS_FILL)
    expect([cbg.top, cbg.shape.height]).toEqual([40, 60 + DIVIDER_GAP - 40])
  })

  it('contains 2 zebra rects (one per band)', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const zebras = g.filter((e: any) => e.type === 'rect' && (e.style?.fill === 'rgba(0,0,0,0.08)' || e.style?.fill === 'rgba(0,0,0,0)'))
    expect(zebras.length).toBe(2)
    // band 0 (bi=0): fill 'rgba(0,0,0,0.08)'
    const band0Zebra = zebras.find((e: any) => e.top === bandGeom[0].top)
    expect(band0Zebra).toBeDefined()
    expect(band0Zebra!.style.fill).toBe('rgba(0,0,0,0.08)')
    expect(band0Zebra!.shape.height).toBe(bandGeom[0].h)
    expect(band0Zebra!.z).toBe(1)
    // band 1 (bi=1): fill transparent
    const band1Zebra = zebras.find((e: any) => e.top === bandGeom[1].top)
    expect(band1Zebra).toBeDefined()
    expect(band1Zebra!.style.fill).toBe('rgba(0,0,0,0)')
  })

  it('band 里行与行之间不画线:除 zebra 与 hits 底外没有全宽 rect', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const fullWidth = g.filter((e: any) => e.type === 'rect' && e.shape?.width === expectedRectWidth)
    expect(fullWidth.length).toBe(bandGeom.length + 1)
  })

  it('子 node 的轨名缩进、挂 ├ / └;根不挂', () => {
    const geom3 = [{ top: 22, h: 21, laneCount: 1 }, { top: 43, h: 21, laneCount: 1 }, { top: 64, h: 21, laneCount: 1 }]
    const g = buildSubDecorGraphics(geom3, bracketH, ['plateau', 'step', 'today'], false, chartSubWidth, 1, {}, [],
                                    BAND_TOP_PAD, [{ depth: 0, last: false }, { depth: 1, last: false }, { depth: 1, last: true }])
    const texts = g.filter((e: any) => e.type === 'text').map((e: any) => [e.style.text, e.left])
    expect(texts.map((t: any) => t[0])).toEqual(['plateau', '├ step', '└ today'])
    expect(texts[1][1]).toBeGreaterThan(texts[0][1])
    expect(texts[2][1]).toBe(texts[1][1])
  })

  it('contains 2 bandLabel texts, one per band, aligned to band top (top pad)', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const labels = g.filter((e: any) => e.type === 'text' && ['bo', 'burst'].includes(e.style?.text))
    expect(labels.length).toBe(2)
    const boLabel = labels.find((e: any) => e.style.text === 'bo')
    // top = band 顶 + BAND_TOP_PAD;verticalAlign:'top' → label 顶部锚点在 band 顶部内边距
    // 单/多 lane 视觉统一(不再随 band 高度浮到中间/下半)。
    expect(boLabel!.top).toBe(bandGeom[0].top + BAND_TOP_PAD)
    expect(boLabel!.left).toBe(SUB_TITLE_LEFT)        // 轨名写在左边的轨名栏里,不留白
    expect(boLabel!.style.fontSize).toBe(13)
    // ⚠ textAlign/textVerticalAlign 必须在元素顶层(不是 style 内)——style 是 zrender TextStyle,
    // 键名是 align/verticalAlign,写 textVerticalAlign 会被无视。
    expect(boLabel!.textVerticalAlign).toBe('top')
    expect(boLabel!.textAlign).toBe('left')
    expect(boLabel!.z).toBe(SUB_TITLE_Z)              // 压在记号上面,垫这一行的底色
    expect(boLabel!.style.backgroundColor).toBe('#ebebeb')
    const burstLabel = labels.find((e: any) => e.style.text === 'burst')
    expect(burstLabel!.top).toBe(bandGeom[1].top + BAND_TOP_PAD)
  })

  it('contains 1 hitsLabel when hitsLabelVisible=true', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    const hits = g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits')
    expect(hits.length).toBe(1)
    // hits label 靠 bracket 区上边(BAND_TOP_PAD,与 bandLabels 顶 pad 对称),同款 verticalAlign:'top'
    expect(hits[0].top).toBe(BAND_TOP_PAD)
    expect(hits[0].left).toBe(SUB_TITLE_LEFT)
    expect(hits[0].style.fontSize).toBe(13)
    expect(hits[0].textVerticalAlign).toBe('top')
    expect(hits[0].textAlign).toBe('left')
    expect(hits[0].z).toBe(SUB_TITLE_Z)
  })

  it('omits hitsLabel when hitsLabelVisible=false', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, false, chartSubWidth)
    const hits = g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits')
    expect(hits.length).toBe(0)
  })

  it('handles empty bandGeom (0 bands) gracefully', () => {
    const g = buildSubDecorGraphics([], bracketH, [], hitsLabelVisible, chartSubWidth)
    // 空 bandGeom → 无 zebra、无 bandLabel、无 band-inner splitLine
    expect(g.filter((e: any) => e.type === 'rect' && (e.style?.fill === 'rgba(0,0,0,0.08)' || e.style?.fill === 'rgba(0,0,0,0)')).length).toBe(0)
    expect(g.filter((e: any) => e.type === 'text' && e.style?.text === 'hits').length).toBe(1)
    expect(g.filter((e: any) => e.type === 'rect' && e.style?.fill === HITS_FILL).length).toBe(1)
  })

  it('all elements marked silent to avoid stealing hover events from data series', () => {
    const g = buildSubDecorGraphics(bandGeom, bracketH, bandLabelTexts, hitsLabelVisible, chartSubWidth)
    g.forEach((e: any) => {
      expect(e.silent).toBe(true)
    })
  })

  it('hitsLabel 顶 pad', () => {
    const bandGeom = [{ top: 50, h: 60, laneCount: 2 }]
    const g2 = buildSubDecorGraphics(bandGeom, 26, ['burst'], true, 800, 2)
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
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
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

  it('option.series still contains data-driven decor consumers (brackets / points / intervals / selection)', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    const seriesNames = opt.series.map((s: any) => s.name)
    // brackets / points / intervals / selection 保留（真数据驱动）
    expect(seriesNames).toContain('brackets')
    expect(seriesNames).toContain('points')
    expect(seriesNames).toContain('intervals')
    expect(seriesNames).toContain(SELECTION_SERIES)
  })

  it('grid[0].left / right consume SUB_GRID_LEFT / SUB_GRID_RIGHT constants', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    expect(opt.grid[0].left).toBe(56)   // SUB_GRID_LEFT
    expect(opt.grid[0].right).toBe(16)  // SUB_GRID_RIGHT
  })

  it('记号都裁在 grid 里:伸出图窗的格、条、底线、hit 行不画进左边的轨名栏', () => {
    const bundle = computeEventData(bars, events, hits, baseParams as any)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1] })
    const opt = buildSubOption(bars, bundle, subGeom, baseParams as any, chartSubWidth) as any
    const custom = opt.series.filter((x: any) => x.type === 'custom')
    expect(custom.length).toBeGreaterThan(0)
    for (const x of custom) expect([x.name, x.clip]).toEqual([x.name, true])
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
      nodeVisible: {}, tagToNodes,
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
      nodeVisible: {}, tagToNodes,
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

// ---------- bracket:一族 hit 一行;记号琥珀满高,▼ 黑;选中的粗框、个数在 selection 系列(见上面第 3 节) ----------
describe('makeRenderBracket — 记号、买入日、画淡', () => {
  const fakeApi: any = {
    value: (i: number) => [10, 20, 0, 1][i] ?? 0,
    coord: ([v]: [number, number]) => [v === 10 ? 100 : v === 5 ? 50 : 200, 0],
    size: () => [10, 0],
  }
  const mk = (item: any, api = fakeApi) => makeRenderBracket([item], 1.0)({ dataIndex: 0 }, api) as any
  const mark = { hit_id: 'm1', hit_ids: ['m1'], kind: 'mark' as const }

  it('普通:琥珀满高,横向起点中心 −0.4 根到终点中心 +0.4 根,无描边、不加任何框', () => {
    const g = mk(mark)
    expect(g.children).toHaveLength(1)
    expect(g.children[0].shape).toEqual({ x: 96, y: 4, width: 108, height: 7 })
    expect(g.children[0].style.fill).toBe('#fbbf24')
    expect(g.children[0].style.stroke).toBeUndefined()
    expect(g.children[0].style.opacity).toBeUndefined()
  })

  it('画淡:格与 ▼ 只降不透明度(0.5),颜色不变', () => {
    expect(mk({ ...mark, dim: true }).children[0].style).toMatchObject({ fill: '#fbbf24', opacity: 0.5 })
    expect(mk({ hit_id: 'm1', hit_ids: ['m1'], kind: 'buy', dim: true }).style).toEqual({ fill: '#111111', opacity: 0.5 })
  })

  it('买入日 ▼:黑色三角;并了几次 hit 时 ▼ 也不变(个数画在 selection 系列里)', () => {
    const buy = mk({ hit_id: 'm1', hit_ids: ['m1'], kind: 'buy' })
    expect(buy.type).toBe('polygon')
    expect(buy.style.fill).toBe('#111111')
    expect(mk({ hit_id: 'm1', hit_ids: ['m1', 'm2'], kind: 'buy' }).shape).toEqual(buy.shape)
  })

  it('行的顶照 laneTops 取(有个数行时行距不等)', () => {
    const lane1 = { ...fakeApi, value: (i: number) => [10, 20, 1, 1][i] ?? 0 }
    const g = makeRenderBracket([mark], 1, 4, [4, 30])({ dataIndex: 0 }, lane1) as any
    expect(g.children[0].shape.y).toBe(30)
  })

  it('zoomFactor:top = 4 + lane·9z,高 7z;不传 z 与 z=1 相同', () => {
    const api = { ...fakeApi, value: (i: number) => [10, 20, 1, 1][i] ?? 0 }
    const g2 = makeRenderBracket([mark], 2)({ dataIndex: 0 }, api) as any
    expect(g2.children[0].shape.y).toBe(4 + 1 * 9 * 2)
    expect(g2.children[0].shape.height).toBe(14)
    const g0 = makeRenderBracket([mark])({ dataIndex: 0 }, api) as any
    const g1 = makeRenderBracket([mark], 1.0)({ dataIndex: 0 }, api) as any
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

  it('makeRenderSelection(items, bandGeom, 2) 点的粗框:三角偏移 +4/-3 按 factor,各顶点外推 1.5;lane 决定 centerY', () => {
    const fakeApi: any = { value: () => 0, coord: () => [100, 200], size: () => [10, 0] }
    // band top=20 h=20 → lane0 centerY = 20 + 4 + 7*z/2;z=2 → 31
    const items = [{ kind: 'frame' as const, target: 'band' as const, shape: 'point' as const, value: [0, 0, 0, 0, 1, 1] }]
    const shape = makeRenderSelection(items, [{ top: 20, h: 20, laneCount: 1 }], 2)({ dataIndex: 0 }, fakeApi) as any
    expect(shape.shape.points[0][1]).toBe(31 + 8 + 3)   // 42
    expect(shape.shape.points[1][1]).toBe(31 - 6 - 1.5) // 23.5
    // 不传 z(=1):centerY = 24 + 3.5 = 27.5
    const shape1 = makeRenderSelection(items, [{ top: 20, h: 20, laneCount: 1 }])({ dataIndex: 0 }, fakeApi) as any
    expect(shape1.shape.points[0][1]).toBe(27.5 + 4 + 3)
    expect(shape1.shape.points[1][1]).toBe(27.5 - 3 - 1.5)
  })

  it('makeRenderSelection(items, bandGeom, 2) 格的粗框与外层底线:自顶向下,高按 z', () => {
    const bg = [{ top: 20, h: 40, laneCount: 1 }]
    const fakeApi: any = {
      value: (i: number) => [10, 20, 0, 0, 1][i] ?? 0,
      coord: ([v]: [number, number]) => [v === 10 ? 100 : 200, 0],
      size: () => [10, 0],
    }
    // 格,z=2,满高:laneH=14,y = 24+14−14−1.5 = 22.5,height = 14+3
    const m = makeRenderSelection([{ kind: 'frame', target: 'band', shape: 'mark', value: [10, 20, 0, 0, 1, 1] }], bg, 2)(
      { dataIndex: 0 }, fakeApi) as any
    expect(m.shape.y).toBe(22.5)
    expect(m.shape.height).toBe(17)
    // 底线,z=2:压在 lane 底(24+14)上
    const u = makeRenderSelection([{ kind: 'under', target: 'band', value: [10, 20, 0, 0, 1] }], bg, 2)(
      { dataIndex: 0 }, fakeApi) as any
    expect(u.shape.y).toBe(24 + 14 - 1)
  })

  it('buildSubOption 从 input.zoomFactor 消费并透传:selection 系列在', () => {
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
        ...overrides,
      }
    }

    const input = makeInput('detected', { zoomFactor: 2 } as any)
    const bundle = computeEventData(bars, events, hits, input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [1, 1, 1, 1] }, 2)
    const opt = buildSubOption(bars, bundle, subGeom, input, 800) as any
    expect(opt.series.find((s: any) => s.name === SELECTION_SERIES)).toBeTruthy()
    // 无法直接断 zoomFactor 值(renderItem 是闭包);
    // 但 sub option 顶层 subCanvasH 应按 factor=2 涨:与 subGeom.subCanvasH 一致(通过 subGeom 已注入)
    expect(subGeom.subCanvasH).toBeGreaterThan(20)
  })
})

// ---------- hits 行的选中装配:粗框在 selection 系列的那一格位上,牵出的照常、其余画淡 ----------
describe('buildSubOption — hits 行的选中装配', () => {
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

  it('选中这次 hit:粗框出在 selection 系列它那一格位上;格本身不加框、照常', () => {
    const highlight: Highlight = { ...NO_HIGHLIGHT, focus: { kind: 'hit', hitId: 'm@0-1', day: 1 },
      focusSlot: { familyKey: 'hits@0', day: 1 }, appHits: new Set(['m@0-1']), dimApp: true }
    const g = bracketGroup(makeInput({ selectedHitId: 'm@0-1', highlight }))
    expect(g.children).toHaveLength(1)
    expect(g.children[0].style).toEqual({ fill: '#fbbf24' })
    const bundle = computeEventData(bars, events, hits, makeInput({ highlight }))
    expect(bundle.frameData).toEqual([{ kind: 'frame', target: 'hits', value: [1, 1, 0], family_key: 'hits@0', buy_day: 1,
                                        grow: false }])
  })

  it('牵出的 hit:那一格底不动、往上长 MARK_GROW,加一圈贴边细边(琥珀深一档);粗框跟着变高后的格', () => {
    const highlight: Highlight = { ...NO_HIGHLIGHT, focus: { kind: 'hit', hitId: 'm@0-1', day: 1 },
      focusSlot: { familyKey: 'hits@0', day: 1 }, appHits: new Set(['m@0-1']), ledHits: new Set(['m@0-1']), dimApp: true }
    const plain = bracketGroup(makeInput({})).children[0]
    const g = bracketGroup(makeInput({ selectedHitId: 'm@0-1', highlight })).children[0]
    // 外沿:顶上移 MARK_GROW、底不动;细边往里收半个边宽
    expect(g.shape.y + g.shape.height + RELATED_EDGE_W / 2).toBeCloseTo(plain.shape.y + plain.shape.height)
    expect(g.shape.y - RELATED_EDGE_W / 2).toBeCloseTo(plain.shape.y - MARK_GROW)
    expect(g.style).toEqual({ fill: '#fbbf24', stroke: darken('#fbbf24', RELATED_EDGE_DARKEN), lineWidth: RELATED_EDGE_W })
    const bundle = computeEventData(bars, events, hits, makeInput({ highlight }))
    expect(bundle.frameData[0].grow).toBe(true)
  })

  it('选中的东西没牵出这次 hit、app 那边又有有关的:这一格画淡', () => {
    const highlight: Highlight = { ...NO_HIGHLIGHT, focus: { kind: 'event', instanceId: 'burst_0_1#0' },
      appEvents: new Set(['burst_0_1#0']), dimApp: true }
    const g = bracketGroup(makeInput({ highlight }))
    expect(g.children[0].style).toEqual({ fill: '#fbbf24', opacity: 0.5 })
  })
})

// ---------- 一次 hit 买好几天、终点不是买点日:hits 行的终点格只跟并着同一次 hit 的 ▼ 照常 ----------
// 三次 hit 同起点 0、都用到 base;买点 node 是 tb(跨的每一天都是买入日):hh 买 5~10、终点 10;g 买 7~8、终点 8;
// k 只买 8、终点 9。从 base 按 → 进到买点日 8:这天 g、k、hh 叠着,只算 g;同一层是 base 牵出的各买点日(5~10)。
describe('computeEventData — 一次 hit 买好几天时 hits 行的终点格', () => {
  const ev = (node: string, st: number, en: number): EventDict =>
    ({ instance_id: `${node}_${st}_${en}#0`, node_id: node, instance_idx: 0, start_idx: st, end_idx: en, child_refs: {} }) as any
  const B = ev('base', 0, 4), TBH = ev('tb', 5, 10), TBG = ev('tb', 7, 8), TBK = ev('tb', 8, 8)
  const mk = (hid: string, end: number, tb: EventDict): HitDict => ({
    hit_id: hid, start_idx: 0, end_idx: end, node_index: { base: B.instance_id, tb: tb.instance_id },
    children: [B.instance_id, tb.instance_id] }) as any
  const hits = [mk('hh', 10, TBH), mk('g', 8, TBG), mk('k', 9, TBK)]
  const events = [B, TBH, TBG, TBK]
  const bars: Bar[] = Array.from({ length: 12 }, (_, i) => ({
    date: `2025-01-${String(i + 1).padStart(2, '0')}`, o: 10, c: 11, h: 12, l: 9, v: 1000, rv: 0 }))
  const topology: Topology = { nodes: [
    { node_id: 'base', where_rules: [] }, { node_id: 'tb', where_rules: [] },
  ], edges: [] } as any

  it('没算上的那次:终点格落在别的买点日那一列时也画淡;那一列的 ▼ 照常;算上的与只并着自己那天 ▼ 的终点格照常', () => {
    const byId = new Map(events.map((x) => [x.instance_id, x]))
    const hitsById = new Map(hits.map((x) => [x.hit_id, x]))
    const wctx: WorldCtx = {
      hits, hitsById, byId, endNode: 'tb', hitOrder: hitOrderOf(hits), using: usingIndex(hits, events),
      bound: (hid) => boundEvents(hitsById.get(hid)!, byId), bandOf: (x) => x.node_id,
      bandFamilies: (band) => foldBand(events.filter((x) => x.node_id === band),
        { band, isPoint: false, tierOf: () => 'in_hit', level: 'detected' }),
      feedbacks: [], samples: [], boxes: [], lineDay: null,
    }
    const highlight = highlightOf(
      [{ kind: 'event', instanceId: B.instance_id }, { kind: 'buy', day: 8 }],
      { world: makeWorld(wctx), wctx })
    expect([...highlight.ledHits]).toEqual(['g'])
    const { tagToNodes, tagList } = deriveTagMap(topology.nodes)
    const mIds = inHitIds(hits, events, topology.edges)
    const input: BandRenderInput = {
      topology, isolatedNodeIds: isolatedNodeIds(topology), tagList, level: 'detected' as Level,
      nodeColors: {}, eventTier: (e) => eventTierOf(e, mIds, new Set()),
      nodeOfEventByBand: (e) => nodeOfEventByBand(e, tagToNodes, tagList), bandKeyOf: (e) => bandKeyOf(e),
      nodeVisible: {}, tagToNodes, endNode: 'tb', highlight,
    }
    const bundle = computeEventData(bars, events, hits, input)
    const cell = (hid: string) => bundle.bracketData.find((d: any) => d.kind === 'mark' && d.hit_ids.includes(hid))
    const buyAt = (day: number) => bundle.bracketData.find((d: any) => d.kind === 'buy' && d.buy_day === day)
    expect(cell('g').dim).toBe(false)          // 算上的那次
    expect(cell('k').dim).toBe(true)           // 没算上;终点 9 那一列的 ▼ 是 hh 的,不借
    expect(buyAt(9).dim).toBe(true)            // 9 是同一层的买点日:不另外照常,画淡
    expect(buyAt(8).dim).toBe(false)           // 选中的那天,▼ 共用、照常
    expect(cell('hh').dim).toBe(true)          // 终点 10 那一列的 ▼ 是同一层的格位:不另外照常
    expect([cell('g').grow, cell('k').grow, buyAt(8).grow, buyAt(9).grow]).toEqual([true, false, true, false])
    expect(bundle.frameData.filter((d: any) => d.kind === 'frame'))
      .toEqual([{ kind: 'frame', target: 'hits', value: [8, 8, 0], family_key: 'hits@0', buy_day: 8, grow: true }])
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
    tooltipResolver: undefined,
    strictWindow: null,
    hitLabel: () => null,
    sliderShow: true,
    zoomOverride: null,
    endNode: undefined,
    selectedHitId: null,
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

describe('computeEventData — band 格的悬停数据:并在这一格里的几个 event', () => {
  const bars = ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-06'].map(date =>
    ({ date, o: 1, c: 1, h: 1, l: 1, v: 1, rv: 0 }))
  // 同起点的一族:终点 2 一格(一个成员),终点 3 一格(两个成员,各被一次 hit 用到)
  const events = [
    { instance_id: 'S2#0', node_id: 'st', start_idx: 0, end_idx: 2, child_refs: {} },
    { instance_id: 'S3a#0', node_id: 'st', start_idx: 0, end_idx: 3, child_refs: {} },
    { instance_id: 'S3b#0', node_id: 'st', start_idx: 0, end_idx: 3, child_refs: {} },
  ] as any[]
  const hits = [
    { hit_id: 'h1', start_idx: 0, end_idx: 3, node_index: { st: 'S3a#0' }, children: ['S3a#0'], predicate_trace: null },
    { hit_id: 'h2', start_idx: 0, end_idx: 3, node_index: { st: 'S3b#0' }, children: ['S3b#0'], predicate_trace: null },
  ] as any[]
  const params = {
    topology: { nodes: [{ node_id: 'st' }], edges: [] }, isolatedNodeIds: new Set<string>(), tagList: ['st'],
    level: 'detected' as const, nodeColors: {}, eventTier: () => 'in_hit' as const,
    nodeOfEventByBand: (e: any) => e.node_id, bandKeyOf: (e: any) => e.node_id, nodeVisible: {},
    tagToNodes: { st: ['st'] },
  }

  it('两个成员的格逐行写 events j/m(只数 event,不按用到它的 hit 拆);一个成员的格不写;格上不带「这一族的第几个位置」', () => {
    for (const p of [{ ...params, endNode: 'st' }, params]) {     // 解析得到、解析不到买入日都一样
      const b = computeEventData(bars as any, events, hits, p as any)
      const recs = [...b.intervalData, ...b.pointData]
      const one = recs.find((d: any) => d.member_ids.includes('S2#0'))
      const two = recs.find((d: any) => d.member_ids.includes('S3a#0'))
      expect(one.stack).toBeUndefined()
      expect(two.stack).toEqual(['events 1/2', 'events 2/2'])
      expect([one.cell_k, one.cell_n, two.cell_k, two.cell_n]).toEqual([undefined, undefined, undefined, undefined])
    }
  })
})
