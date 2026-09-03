import { describe, it, expect } from 'vitest'
import { matchedIds, resolveTooltipData } from '../src/render/visible'
import {
  bandKeyOf, deriveTagMap, isolatedNodeIds, isQualifiedRow,
  qualifiedIdsOf, eventTierOf, nodeOfEventByBand, isBandVisible,
  renderGridOf, subBandTagList,
} from '../src/render/visible'
import type { TopoNode, TopoEdge, EventDict, MatchDict, AttrRow, Diagnostics, Bar } from '../src/types'
import { ANALYSIS } from './fixtures'

const { matches } = ANALYSIS

describe('matchedIds', () => {
  it('matchedIds = union of all node_index 精确实例(instance_id 字符串直加)', () => {
    const s = matchedIds(matches, ANALYSIS.events, [])
    expect(s.has('bo_9#0')).toBe(true)
    expect(s.has('bo_20#0')).toBe(false)
  })

  it('沿 child_refs.members 递归展开:matched composite event 的 constituent 也进 matched 集(协议驱动、非字段名)', () => {
    const matches: MatchDict[] = [{ match_id: 'm1', start_idx: 0, end_idx: 10,
      node_index: { burst: 'burst_1_5#0' }, children: ['burst_1_5#0'], predicate_trace: null }]
    const events: EventDict[] = [
      { instance_id: 'burst_1_5#0', node_id: 'burst', instance_idx: 0, start_idx: 1, end_idx: 5,
        child_refs: { members: ['bo_1#0', 'bo_3#0', 'bo_5#0'] } },
      { instance_id: 'bo_1#0', node_id: 'bo', instance_idx: 0, start_idx: 1, end_idx: 1, child_refs: {} },
      { instance_id: 'bo_3#0', node_id: 'bo', instance_idx: 0, start_idx: 3, end_idx: 3, child_refs: {} },
      { instance_id: 'bo_5#0', node_id: 'bo', instance_idx: 0, start_idx: 5, end_idx: 5, child_refs: {} },
      { instance_id: 'bo_99#0', node_id: 'bo', instance_idx: 0, start_idx: 99, end_idx: 99, child_refs: {} },
    ]
    const s = matchedIds(matches, events, [])
    expect(s.has('burst_1_5#0')).toBe(true)
    expect(s.has('bo_1#0')).toBe(true)
    expect(s.has('bo_3#0')).toBe(true)
    expect(s.has('bo_5#0')).toBe(true)
    expect(s.has('bo_99#0')).toBe(false)  // 不在 child_refs.members
  })

  it('沿 edges.anchor_field 反查:tb.anchor_bo_id 引用的 bo 也进 matched 集(默认 expandAnchor)', () => {
    const matches: MatchDict[] = [{ match_id: 'm1', start_idx: 0, end_idx: 10,
      node_index: { tb: 'tb_7#0' }, children: ['tb_7#0'], predicate_trace: null }]
    const events: EventDict[] = [
      { instance_id: 'tb_7#0', node_id: 'tb', instance_idx: 0, start_idx: 7, end_idx: 7,
        child_refs: {}, anchor_bo_id: 'bo_5#0' },
      { instance_id: 'bo_5#0', node_id: 'bo', instance_idx: 0, start_idx: 5, end_idx: 5, child_refs: {} },
    ]
    const edges: TopoEdge[] = [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }]
    const s = matchedIds(matches, events, edges)
    expect(s.has('tb_7#0')).toBe(true)
    expect(s.has('bo_5#0')).toBe(true)
  })

  it('实例级展开:同 (node,span) 多实例(instance_idx #0/#1)各进集、互不覆盖;node_index 精确引用两实例', () => {
    const matches: MatchDict[] = [{ match_id: 'm1', start_idx: 0, end_idx: 10,
      node_index: { tb: 'tb_266#0', tb2: 'tb_266#1' },
      children: ['tb_266#0', 'tb_266#1'], predicate_trace: null }]
    const events: EventDict[] = [
      { instance_id: 'tb_266#0', node_id: 'tb', instance_idx: 0, start_idx: 266, end_idx: 266,
        child_refs: {}, anchor_bo_id: 'bo_5#0' },
      { instance_id: 'tb_266#1', node_id: 'tb', instance_idx: 1, start_idx: 266, end_idx: 266,
        child_refs: {}, anchor_bo_id: 'bo_6#0' },
      { instance_id: 'bo_5#0', node_id: 'bo', instance_idx: 0, start_idx: 5, end_idx: 5, child_refs: {} },
      { instance_id: 'bo_6#0', node_id: 'bo', instance_idx: 0, start_idx: 6, end_idx: 6, child_refs: {} },
    ]
    const edges: TopoEdge[] = [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }]
    const s = matchedIds(matches, events, edges)
    expect(s.has('tb_266#0')).toBe(true)
    expect(s.has('tb_266#1')).toBe(true)
    // node_index 精确引用 #0/#1 → 两实例都进集;各实例 anchor 的 bo 各进集(不串)
    expect(s.has('bo_5#0')).toBe(true)
    expect(s.has('bo_6#0')).toBe(true)
  })

  it('events/edges 为空数组:无实例可展开 → 空集(node_index 无引用)', () => {
    const ms: MatchDict[] = [{ match_id: 'M1', start_idx: 1, end_idx: 5, children: ['burst_1_5#0'], node_index: {}, predicate_trace: null }]
    const s = matchedIds(ms, [], [])
    expect(s.size).toBe(0)
  })

  it('matchedIds 初始集按 node_index 精确实例(非身份展开)', () => {
    // 构造:两个 match,node_index 分别引用 tb_293 的 #0 / #1(APCX 形态)
    const m0 = { match_id: 'bb@0-3', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#0', tb: 'tb_293#0' },
                 children: ['burst_0_2#0', 'tb_293#0'], predicate_trace: null } as MatchDict
    const m1 = { match_id: 'bb@0-3b', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#1', tb: 'tb_293#1' },
                 children: ['burst_0_2#1', 'tb_293#1'], predicate_trace: null } as MatchDict
    const events = [
      { instance_id: 'tb_293#0', node_id: 'tb', instance_idx: 0, start_idx: 293, end_idx: 293, child_refs: {} } as EventDict,
      { instance_id: 'tb_293#1', node_id: 'tb', instance_idx: 1, start_idx: 293, end_idx: 293, child_refs: {} } as EventDict,
    ]
    const s = matchedIds([m0, m1], events, [])
    expect(s.has('tb_293#0')).toBe(true)
    expect(s.has('tb_293#1')).toBe(true)   // 两实例各被引用 → 都进集
  })

  it('matchedIds 未被引用的实例不进集', () => {
    // 同 (node,span) 3 实例,只有 #0/#1 被引用 → #2 不进集
    const events = [
      { instance_id: 'tb_1#0', node_id: 'tb', instance_idx: 0, start_idx: 1, end_idx: 1, child_refs: {} } as EventDict,
      { instance_id: 'tb_1#1', node_id: 'tb', instance_idx: 1, start_idx: 1, end_idx: 1, child_refs: {} } as EventDict,
      { instance_id: 'tb_1#2', node_id: 'tb', instance_idx: 2, start_idx: 1, end_idx: 1, child_refs: {} } as EventDict,
    ]
    const m = { match_id: 'bb@1-1', start_idx: 1, end_idx: 1,
                node_index: { tb: 'tb_1#1' },
                children: ['tb_1#1'], predicate_trace: null } as MatchDict
    const s = matchedIds([m], events, [])
    expect(s.has('tb_1#0')).toBe(false)   // 身份展开的旧行为会进 #0;精确引用不进
    expect(s.has('tb_1#1')).toBe(true)
  })
})

const nodes: TopoNode[] = [
  { node_id: 'down', where_rules: [] },
  { node_id: 'side', where_rules: [] },
  { node_id: 'bo', where_rules: [] },
  { node_id: 'burst', where_rules: [] },
  { node_id: 'tb', where_rules: [] },
]
const edges: TopoEdge[] = [
  { src: 'down', dst: 'burst', kind: 'TemporalEdge', rule: '' },
  { src: 'side', dst: 'burst', kind: 'StartContainmentEdge', rule: '' },
  { src: 'burst', dst: 'tb', kind: 'TemporalEdge', rule: '' },
]
const ev = (instanceId: string, nodeId: string): EventDict =>
  ({ instance_id: instanceId, node_id: nodeId, instance_idx: 0, start_idx: 0, end_idx: 0, child_refs: {} })

describe('visible §3 band/tier', () => {
  it('isolatedNodeIds = 无边 node = {bo}', () => {
    expect(isolatedNodeIds({ nodes, edges })).toEqual(new Set(['bo']))
  })
  it('deriveTagMap: node→nodes & 有序 bandList(按 node_id 分组)', () => {
    const { tagToNodes, tagList } = deriveTagMap(nodes)
    expect(tagToNodes['down']).toEqual(['down'])
    expect(tagList).toEqual(['down', 'side', 'bo', 'burst', 'tb'])
  })
  it('bandKeyOf: 返回 event.node_id(band 分组键)', () => {
    expect(bandKeyOf(ev('burst_1_9#0', 'burst'))).toBe('burst')
  })
  it('isQualifiedRow: 全 clause satisfied / 空 clauses vacuous 真', () => {
    const pass: AttrRow = { instance_id: 'x_0#0', node_id: 'x', start_idx: 0, end_idx: 0, clauses: { a: { satisfied: true, measured: 1, op: '>=', threshold: 0 } } }
    const fail: AttrRow = { ...pass, clauses: { a: { ...pass.clauses.a, satisfied: false } } }
    const empty: AttrRow = { ...pass, clauses: {} }
    expect(isQualifiedRow(pass)).toBe(true)
    expect(isQualifiedRow(fail)).toBe(false)
    expect(isQualifiedRow(empty)).toBe(true)
  })
  it('eventTierOf: matched > qualified > detected', () => {
    const matched = new Set(['m1#0']); const qualified = new Set(['t1#0'])
    expect(eventTierOf(ev('m1#0', 'burst'), matched, qualified)).toBe('matched')
    expect(eventTierOf(ev('t1#0', 'burst'), matched, qualified)).toBe('qualified')
    expect(eventTierOf(ev('d1#0', 'burst'), matched, qualified)).toBe('detected')
  })
  it('eventTierOf 按实例级判定:同 (node,span) 不同实例可不同档', () => {
    // 实例化契约:matched 集元素为 instance_id;#0 实例 matched、#1 实例仅 detected
    const matched = new Set(['tb_266#0'])
    const qualified = new Set<string>()
    const e0 = { ...ev('tb_266#0', 'tb') }
    const e1 = { ...ev('tb_266#1', 'tb') }
    expect(eventTierOf(e0, matched, qualified)).toBe('matched')
    expect(eventTierOf(e1, matched, qualified)).toBe('detected')
  })
  it('eventTierOf qualified 实例级判定:matched/qualified 集均 instance_id,同 (node,span) 两实例可不同档', () => {
    const matched = new Set<string>()
    const qualified = new Set(['tb_266#0'])
    const e0 = { ...ev('tb_266#0', 'tb') }
    const e1 = { ...ev('tb_266#1', 'tb') }
    expect(eventTierOf(e0, matched, qualified)).toBe('qualified')
    expect(eventTierOf(e1, matched, qualified)).toBe('detected')  // 仅 #0 实例 qualified,#1 各判各的
  })
  it('nodeOfEventByBand: node_id → 单 node(1:1)', () => {
    const { tagToNodes, tagList } = deriveTagMap(nodes)
    expect(nodeOfEventByBand(ev('burst_1_9#0', 'burst'), tagToNodes, tagList)).toBe('burst')
  })
  it('qualifiedIdsOf: ⋃_node { 全 satisfied 行 },跨 node 并集;排除 fail 行;null→空', () => {
    const okRow = (id: string): AttrRow =>
      ({ instance_id: id, node_id: 'n', start_idx: 0, end_idx: 0, clauses: { a: { satisfied: true, measured: 1, op: '>=', threshold: 0 } } })
    const failRow = (id: string): AttrRow =>
      ({ instance_id: id, node_id: 'n', start_idx: 0, end_idx: 0, clauses: { a: { satisfied: false, measured: 0, op: '>=', threshold: 1 } } })
    const diag: Diagnostics = {
      symbol: 'X', pattern_id: 'p', note: '',
      nodes: {
        down:  { attr: [okRow('d1#0'), failRow('d2#0')], rel: [] },   // d1 进集,d2 排除
        burst: { attr: [okRow('b1#0')],                rel: [] },   // 跨 node 并集
      },
    }
    const qualified = qualifiedIdsOf(diag)
    expect(qualified).toEqual(new Set(['d1#0', 'b1#0']))   // instance_id 直集(attr 行恒带 instance_id)
    expect(qualified.has('d2#0')).toBe(false)                        // 有 satisfied:false → 排除
    expect(qualifiedIdsOf(null)).toEqual(new Set())                  // null → 空集
  })
  it('qualifiedIdsOf 实例级:同 (node,span) 两实例可不同档', () => {
    const diag = {
      symbol: 'X', pattern_id: 'bb_v1', note: '',
      nodes: { tb: { attr: [
        { instance_id: 'tb_293#0', node_id: 'tb', start_idx: 293, end_idx: 293,
          clauses: { c1: { cid: 'c1', measured: 1, op: '>=', threshold: 0, satisfied: true, kind: null } } },
        { instance_id: 'tb_293#1', node_id: 'tb', start_idx: 293, end_idx: 293,
          clauses: { c1: { cid: 'c1', measured: 0, op: '>=', threshold: 1, satisfied: false, kind: null } } },
      ], rel: [] } } } as unknown as Diagnostics
    const q = qualifiedIdsOf(diag)
    expect(q.has('tb_293#0')).toBe(true)
    expect(q.has('tb_293#1')).toBe(false)   // 事件级旧行为会全进或全不进
  })
  it('renderGridOf: bo 节点声明 price → 返回 price', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.node_id
    expect(renderGridOf(ev('bo_9#0', 'bo'), topoWithBoPrice, bandKeyOfFn)).toBe('price')
  })

  it('renderGridOf: tb 节点未声明 → fallback time', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.node_id
    expect(renderGridOf(ev('tb_16#0', 'tb'), topoWithBoPrice, bandKeyOfFn)).toBe('time')
  })

  it('renderGridOf: bandKey 匹配不到 TopoNode → fallback time', () => {
    const topoEmpty = { nodes: [], edges: [] }
    const bandKeyOfFn = (e: EventDict) => e.node_id
    expect(renderGridOf(ev('ghost_1#0', 'ghost'), topoEmpty, bandKeyOfFn)).toBe('time')
  })

  it('bandKeyOf 无回退:band 分组键恒为 node_id(无 source_tag/前缀/class_id 逻辑)', () => {
    expect(bandKeyOf(ev('trend0_5#0', 'down'))).toBe('down')
    expect(bandKeyOf(ev('bo_9#0', 'bo'))).toBe('bo')
  })
})

describe('subBandTagList', () => {
  const node = (nid: string, grid?: 'price' | 'time'): TopoNode =>
    ({ node_id: nid, where_rules: [], ...(grid ? { render_grid: grid } : {}) })

  it('render_grid=price 的 tag 被剔除,其余保序', () => {
    const topo = { nodes: [node('bo', 'price'), node('burst'), node('tb', 'time')], edges: [] }
    expect(subBandTagList(['bo', 'burst', 'tb'], topo)).toEqual(['burst', 'tb'])
  })

  it('无 render_grid 字段 → 缺省 time,保留(与 renderGridOf 缺省一致)', () => {
    const topo = { nodes: [node('a'), node('b')], edges: [] }
    expect(subBandTagList(['a', 'b'], topo)).toEqual(['a', 'b'])
  })

  it('全 price → 空列表(bo_only 场景:副图无 band)', () => {
    const topo = { nodes: [node('bo', 'price')], edges: [] }
    expect(subBandTagList(['bo'], topo)).toEqual([])
  })

  it('tag 匹配不到 node → 缺省 time,保留', () => {
    const topo = { nodes: [], edges: [] }
    expect(subBandTagList(['ghost'], topo)).toEqual(['ghost'])
  })
})

describe('isBandVisible', () => {
  const tagToNodes: Record<string, string[]> = {
    down:   ['down'],
    burst:  ['burst'],
    bo:     ['bo'],
  }

  it('nodeVisible 未传 → 所有 band 可见', () => {
    expect(isBandVisible('burst', undefined, tagToNodes)).toBe(true)
    expect(isBandVisible('down', undefined, tagToNodes)).toBe(true)
  })
  it('tagToNodes 无该 band 条目(空 nodeIds) → 可见', () => {
    expect(isBandVisible('unknown_band', { down: false }, tagToNodes)).toBe(true)
  })
  it('band 内所有 node 均 nodeVisible===false → 不可见', () => {
    expect(isBandVisible('burst', { burst: false }, tagToNodes)).toBe(false)
  })
  it('band 内任一 node nodeVisible!==false → 可见', () => {
    // 一个多 node 分组:一个 false,一个未设(undefined=可见)
    const twoNodes: Record<string, string[]> = { g: ['down', 'side'] }
    expect(isBandVisible('g', { down: false }, twoNodes)).toBe(true)
    expect(isBandVisible('g', { down: false, side: false }, twoNodes)).toBe(false)
  })
  it('nodeVisible 为空对象(缺键) → 全部视为可见', () => {
    expect(isBandVisible('burst', {}, tagToNodes)).toBe(true)
  })
})

describe('resolveTooltipData', () => {
  const bars: Bar[] = [
    { date: '2024-03-01', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-02', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-03', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-04', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-05', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
    { date: '2024-03-06', o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 },
  ]
  const events: EventDict[] = [
    { instance_id: 'd1#0', node_id: 'down', instance_idx: 0, start_idx: 0, end_idx: 5, drawdown: 0.42 } as any,
    { instance_id: 'b1#0', node_id: 'burst', instance_idx: 0, start_idx: 1, end_idx: 1, count: 3, first_drought: 0,
      child_refs: { members: ['bo_x#0', 'bo_y#0'] }, ref_ids: {} } as any,
    { instance_id: 'b2#0', node_id: 'burst', instance_idx: 0, start_idx: 2, end_idx: 4, count: 5, max_bar_vol_ratio: 2.6378544926831706 } as any,
  ]
  const diag: Diagnostics = {
    symbol: 'X', pattern_id: 'p', note: '',
    nodes: {
      down: {
        attr: [{ instance_id: 'd1#0', node_id: 'down', start_idx: 0, end_idx: 5,
          clauses: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } }],
        rel: [],
      },
      bo_burst: {
        attr: [{ instance_id: 'b1#0', node_id: 'bo_burst', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: false, measured: 0, op: '>=', threshold: 20 },
            count: { satisfied: true, measured: 3, op: '>=', threshold: 2 },
          } }],
        rel: [],
      },
      tb_burst: {
        attr: [{ instance_id: 'b1#0', node_id: 'tb_burst', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: true, measured: 0, op: '>=', threshold: 0 },
          } }],
        rel: [],
      },
    },
  }

  it('返回结构含 identity / clauses / raw 三键', () => {
    const r = resolveTooltipData('d1#0', diag, events, bars)
    expect(Object.keys(r).sort()).toEqual(['clauses', 'identity', 'raw'])
  })

  it('identity.nodes 单 node 时返回单元素数组', () => {
    const r = resolveTooltipData('d1#0', diag, events, bars)
    expect(r.identity.nodes).toEqual(['down'])
  })

  it('identity.nodes 多 node 时返回多元素数组（按 diag.nodes 插入顺序）', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    expect(r.identity.nodes).toEqual(['bo_burst', 'tb_burst'])
  })

  it('identity.nodes 零 node 时返回空数组', () => {
    const r = resolveTooltipData('b2#0', diag, events, bars)
    expect(r.identity.nodes).toEqual([])
  })

  it('identity 区间事件 dateStart/End 均填日期', () => {
    const r = resolveTooltipData('d1#0', diag, events, bars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('2024-03-06')
  })

  it('identity point 事件 dateEnd 为 null', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)   // b1 start_idx=end_idx=1
    expect(r.identity.dateStart).toBe('2024-03-02')
    expect(r.identity.dateEnd).toBe(null)
  })

  it('identity 区间事件 dateEnd 为 end_idx 对应日期', () => {
    const r = resolveTooltipData('b2#0', diag, events, bars)   // b2 start_idx=2, end_idx=4
    expect(r.identity.dateStart).toBe('2024-03-03')
    expect(r.identity.dateEnd).toBe('2024-03-05')
  })

  it('identity bars 越界时 fallback 到原索引字符串', () => {
    const shortBars: Bar[] = [bars[0]]
    const r = resolveTooltipData('d1#0', diag, events, shortBars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('5')   // end_idx=5 越界
  })

  it('identity.eventId 直返参数(值=instanceId)', () => {
    const r = resolveTooltipData('d1#0', diag, events, bars)
    expect(r.identity.eventId).toBe('d1#0')
  })

  it('clauses 失败 ✗ 排在满足 ✓ 之前', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    const sats = r.clauses.map((c) => c.satisfied)
    const firstSat = sats.indexOf(true)
    const lastUnsat = sats.lastIndexOf(false)
    expect(lastUnsat).toBeLessThan(firstSat)
  })

  it('clauses 多 node 同 cid 各保留一行（不覆盖）', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    const firstDroughtRows = r.clauses.filter((c) => c.cid === 'first_drought')
    expect(firstDroughtRows.length).toBe(2)   // bo_burst 一条 + tb_burst 一条
    const nodes = firstDroughtRows.map((c) => c.node).sort()
    expect(nodes).toEqual(['bo_burst', 'tb_burst'])
    const thresholds = firstDroughtRows.map((c) => c.threshold).sort()
    expect(thresholds).toEqual([0, 20])
  })

  it('clauses 单 node cid 只有一条', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    const countRows = r.clauses.filter((c) => c.cid === 'count')
    expect(countRows.length).toBe(1)
    expect(countRows[0].node).toBe('bo_burst')
  })

  it('raw 排除 SKIP 集（instance_id/node_id/instance_idx/start_idx/end_idx/child_refs/ref_ids）', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    expect('instance_id' in r.raw).toBe(false)
    expect('node_id' in r.raw).toBe(false)
    expect('instance_idx' in r.raw).toBe(false)
    expect('start_idx' in r.raw).toBe(false)
    expect('end_idx' in r.raw).toBe(false)
    expect('child_refs' in r.raw).toBe(false)
    expect('ref_ids' in r.raw).toBe(false)   // 回归:ref_ids 是对象值,漏跳过会在 tooltip 渲成 [object Object]
  })

  it('raw 去重 clauses 已引用 cid（cid 名 ↔ 字段名命中时移除 raw 那份）', () => {
    const r = resolveTooltipData('b1#0', diag, events, bars)
    // b1 字段含 count + first_drought；diag 里 bo_burst 也评估 first_drought + count
    expect('first_drought' in r.raw).toBe(false)
    expect('count' in r.raw).toBe(false)
  })

  it('raw 保留 clauses 未引用的字段', () => {
    const r = resolveTooltipData('b2#0', diag, events, bars)
    // b2 不在任何 node 的 attr 表 → clauses 为空 → raw 保留全部非 SKIP 字段
    expect(r.raw.count).toBe(5)
    expect(r.raw.max_bar_vol_ratio).toBeCloseTo(2.6378544926831706, 10)
  })

  it('未知 instance_id → 空 clauses / 空 raw / identity 仅 eventId 有值', () => {
    const r = resolveTooltipData('zzz#0', diag, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.raw).toEqual({})
    expect(r.identity.eventId).toBe('zzz#0')
    expect(r.identity.nodes).toEqual([])
  })

  it('diag === null → 空 clauses，identity / raw 正常', () => {
    const r = resolveTooltipData('d1#0', null, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.identity.eventId).toBe('d1#0')
    expect(r.identity.nodes).toEqual([])   // 无 diag 无 node
    expect(r.raw.drawdown).toBe(0.42)
  })
})

describe('resolveTooltipData 组合子扁平化', () => {
  const witnessTree = {
    satisfied: false, measured: null, op: null, threshold: null,
    label: 'or',
    children: [
      { satisfied: false, measured: 3, op: '>=', threshold: 4, label: 'distinct_pk' },
      { satisfied: false, measured: 5.2, op: '>=', threshold: 8, label: 'max_bar_vol_ratio' },
    ],
  }
  const diag = {
    symbol: 's', pattern_id: 'p', note: '',
    nodes: {
      burst: {
        rel: [],
        attr: [{
          instance_id: 'ev1#0', node_id: 'burst', start_idx: 0, end_idx: 1,
          clauses: {
            pk_or_vol: witnessTree,
            first_drought: { satisfied: true, measured: 24, op: '>=', threshold: 20 },
          },
        }],
      },
    },
  } as unknown as Diagnostics

  it('顶层排序失败在前,子树紧跟父行且保持声明顺序', () => {
    const { clauses } = resolveTooltipData('ev1#0', diag, [], [])
    expect(clauses.map(c => c.cid)).toEqual(['pk_or_vol', 'distinct_pk', 'max_bar_vol_ratio', 'first_drought'])
    expect(clauses.map(c => c.depth)).toEqual([0, 1, 1, 0])
  })

  it('组合子行带 kind,叶子行 kind=null', () => {
    const { clauses } = resolveTooltipData('ev1#0', diag, [], [])
    expect(clauses[0].kind).toBe('or')
    expect(clauses[1].kind).toBeNull()
  })

  it('树线前缀:末子用 └、其余用 ├,顶层为空', () => {
    const { clauses } = resolveTooltipData('ev1#0', diag, [], [])
    expect(clauses.map(c => c.guide)).toEqual(['', '├ ', '└ ', ''])
  })

  it('树线在更深层延续:非末子往下补 │,末子往下补空格', () => {
    const deep = {
      symbol: 's', pattern_id: 'p', note: '',
      nodes: {
        burst: {
          rel: [],
          attr: [{
            instance_id: 'ev1#0', node_id: 'burst', start_idx: 0, end_idx: 1,
            clauses: {
              c: {
                satisfied: true, measured: null, op: null, threshold: null, label: 'or',
                children: [
                  {
                    satisfied: true, measured: null, op: null, threshold: null, label: 'and',
                    children: [{ satisfied: true, measured: 1, op: '>=', threshold: 0, label: 'a' }],
                  },
                  {
                    satisfied: true, measured: null, op: null, threshold: null, label: 'not',
                    children: [{ satisfied: false, measured: 2, op: '>=', threshold: 9, label: 'b' }],
                  },
                ],
              },
            },
          }],
        },
      },
    } as unknown as Diagnostics
    const { clauses } = resolveTooltipData('ev1#0', deep, [], [])
    // and 是非末子 → 其子行前缀补 │;not 是末子 → 其子行前缀补空格
    expect(clauses.map(c => c.guide)).toEqual(['', '├ ', '│ └ ', '└ ', '  └ '])
  })

  it('raw 去重覆盖子行字段(cid=label=字段名自动进去重集)', () => {
    const events = [{
      instance_id: 'ev1#0', node_id: 'burst', instance_idx: 0, start_idx: 0, end_idx: 1,
      distinct_pk: 3, other_field: 1,
    }] as unknown as EventDict[]
    const { raw } = resolveTooltipData('ev1#0', diag, events, [])
    expect(raw).not.toHaveProperty('distinct_pk')
    expect(raw).toHaveProperty('other_field')
  })
})
