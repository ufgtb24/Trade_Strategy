import { describe, it, expect } from 'vitest'
import { matchedIds, resolveTooltipData } from '../src/render/visible'
import {
  bandKeyOf, deriveTagMap, isolatedNodeIds, isQualifiedRow,
  qualifiedIdsOf, eventTierOf, roleOfEventByBand, isBandVisible,
  renderGridOf, subBandTagList,
} from '../src/render/visible'
import type { TopoNode, TopoEdge, EventDict, AttrRow, Diagnostics, Bar } from '../src/types'
import { ANALYSIS } from './fixtures'

const { matches } = ANALYSIS

describe('matchedIds', () => {
  it('matchedIds = union of all children', () => {
    const s = matchedIds(matches)
    expect(s.has('bo9')).toBe(true)
    expect(s.has('boX')).toBe(false)
  })

  it('沿 members 字段递归展开:matched composite event 的 constituent 也进 matched 集', () => {
    const events: EventDict[] = [
      { class_id: 'burst', event_id: 'burst_1_5', start_idx: 1, end_idx: 5, source_tag: 'burst',
        members: ['bo_1', 'bo_3', 'bo_5'] },
      { class_id: 'bo', event_id: 'bo_1', start_idx: 1, end_idx: 1, source_tag: 'bo' },
      { class_id: 'bo', event_id: 'bo_3', start_idx: 3, end_idx: 3, source_tag: 'bo' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo' },
      { class_id: 'bo', event_id: 'bo_99', start_idx: 99, end_idx: 99, source_tag: 'bo' },  // 不在 burst.members
    ]
    const ms = [{ event_id: 'M1', start_idx: 1, end_idx: 5, children: ['burst_1_5'], role_index: {}, predicate_trace: null }]
    const s = matchedIds(ms, events)
    expect(s.has('burst_1_5')).toBe(true)
    expect(s.has('bo_1')).toBe(true)
    expect(s.has('bo_3')).toBe(true)
    expect(s.has('bo_5')).toBe(true)
    expect(s.has('bo_99')).toBe(false)
  })

  it('沿 anchor_bo_id 字段展开:tb 的 anchor_bo_id 进入 matched 集', () => {
    const events: EventDict[] = [
      { class_id: 'tb', event_id: 'tb_6', start_idx: 6, end_idx: 6, source_tag: 'tb', anchor_bo_id: 'bo_5' },
      { class_id: 'bo', event_id: 'bo_5', start_idx: 5, end_idx: 5, source_tag: 'bo' },
    ]
    const ms = [{ event_id: 'M1', start_idx: 5, end_idx: 6, children: ['tb_6'], role_index: {}, predicate_trace: null }]
    const s = matchedIds(ms, events)
    expect(s.has('tb_6')).toBe(true)
    expect(s.has('bo_5')).toBe(true)
  })

  it('不传 events:退化为旧行为(仅 children)', () => {
    const ms = [{ event_id: 'M1', start_idx: 1, end_idx: 5, children: ['burst_1_5'], role_index: {}, predicate_trace: null }]
    const s = matchedIds(ms)
    expect(s.size).toBe(1)
    expect(s.has('burst_1_5')).toBe(true)
  })
})

const nodes: TopoNode[] = [
  { node_id: 'down', class_id: 'trend', where_rules: [], source_tag: 'trend0' },
  { node_id: 'side', class_id: 'trend', where_rules: [], source_tag: 'trend1' },
  { node_id: 'bo',   class_id: 'bo',    where_rules: [], source_tag: 'bo' },
  { node_id: 'burst',class_id: 'burst', where_rules: [], source_tag: 'burst' },
  { node_id: 'tb',   class_id: 'tb',    where_rules: [], source_tag: 'tb' },
]
const edges: TopoEdge[] = [
  { src: 'down', dst: 'burst', kind: 'TemporalEdge', rule: '' },
  { src: 'side', dst: 'burst', kind: 'StartContainmentEdge', rule: '' },
  { src: 'burst', dst: 'tb', kind: 'TemporalEdge', rule: '' },
]
const ev = (id: string, st: string): EventDict =>
  ({ class_id: id.split('_')[0], event_id: id, start_idx: 0, end_idx: 0, source_tag: st })

describe('visible §3 band/tier', () => {
  it('isolatedNodeIds = 无边 node = {bo}', () => {
    expect(isolatedNodeIds({ nodes, edges })).toEqual(new Set(['bo']))
  })
  it('deriveTagMap: tag→nodes & 有序 tagList', () => {
    const { tagToNodes, tagList } = deriveTagMap(nodes)
    expect(tagToNodes['trend0']).toEqual(['down'])
    expect(tagList).toEqual(['trend0', 'trend1', 'bo', 'burst', 'tb'])
  })
  it('bandKeyOf: 直读 source_tag 优先', () => {
    expect(bandKeyOf(ev('burst_1_9', 'burst'), ['trend0','trend1','bo','burst','tb'])).toBe('burst')
  })
  it('isQualifiedRow: 全 clause satisfied / 空 clauses vacuous 真', () => {
    const pass: AttrRow = { event_id: 'x', start_idx: 0, end_idx: 0, clauses: { a: { satisfied: true, measured: 1, op: '>=', threshold: 0 } } }
    const fail: AttrRow = { ...pass, clauses: { a: { ...pass.clauses.a, satisfied: false } } }
    const empty: AttrRow = { ...pass, clauses: {} }
    expect(isQualifiedRow(pass)).toBe(true)
    expect(isQualifiedRow(fail)).toBe(false)
    expect(isQualifiedRow(empty)).toBe(true)
  })
  it('eventTierOf: matched > qualified > detected', () => {
    const matched = new Set(['m1']); const qualified = new Set(['m1', 't1'])
    expect(eventTierOf(ev('m1','burst'), matched, qualified)).toBe('matched')
    expect(eventTierOf(ev('t1','burst'), matched, qualified)).toBe('qualified')
    expect(eventTierOf(ev('d1','burst'), matched, qualified)).toBe('detected')
  })
  it('roleOfEventByBand: tag→单 node', () => {
    const { tagToNodes, tagList } = deriveTagMap(nodes)
    expect(roleOfEventByBand(ev('burst_1','burst'), tagToNodes, tagList)).toBe('burst')
  })
  it('qualifiedIdsOf: ⋃_role { 全 satisfied 行 },跨 role 并集;排除 fail 行;null→空', () => {
    const okRow = (id: string): AttrRow =>
      ({ event_id: id, start_idx: 0, end_idx: 0, clauses: { a: { satisfied: true, measured: 1, op: '>=', threshold: 0 } } })
    const failRow = (id: string): AttrRow =>
      ({ event_id: id, start_idx: 0, end_idx: 0, clauses: { a: { satisfied: false, measured: 0, op: '>=', threshold: 1 } } })
    const diag: Diagnostics = {
      symbol: 'X', pattern_id: 'p', note: '',
      roles: {
        down:  { attr: [okRow('d1'), failRow('d2')], rel: [] },   // d1 进集,d2 排除
        burst: { attr: [okRow('b1')],                rel: [] },   // 跨 role 并集
      },
    }
    const qualified = qualifiedIdsOf(diag)
    expect(qualified).toEqual(new Set(['d1', 'b1']))
    expect(qualified.has('d2')).toBe(false)                          // 有 satisfied:false → 排除
    expect(qualifiedIdsOf(null)).toEqual(new Set())                  // null → 空集
  })
  it('renderGridOf: bo 节点声明 price → 返回 price', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', source_tag: 'bo',
          render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', class_id: 'tb', source_tag: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('bo9', 'bo'), topoWithBoPrice, bandKeyOfFn)).toBe('price')
  })

  it('renderGridOf: tb 节点未声明 → fallback time', () => {
    const topoWithBoPrice = {
      nodes: [
        { node_id: 'bo', class_id: 'bo', source_tag: 'bo',
          render_grid: 'price' as const, where_rules: [] },
        { node_id: 'tb', class_id: 'tb', source_tag: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('tb1', 'tb'), topoWithBoPrice, bandKeyOfFn)).toBe('time')
  })

  it('renderGridOf: bandKey 匹配不到 TopoNode → fallback time', () => {
    const topoEmpty = { nodes: [], edges: [] }
    const bandKeyOfFn = (e: EventDict) => e.source_tag
    expect(renderGridOf(ev('x1', 'ghost'), topoEmpty, bandKeyOfFn)).toBe('time')
  })

  it('bandKeyOf fallback: source_tag 空 → 前缀匹配 / 最长前缀 / class_id 兜底', () => {
    const tags = ['trend0', 'trend1', 'bo', 'burst', 'tb']
    // ① source_tag 为空串,靠 event_id 前缀匹配
    expect(bandKeyOf(ev('trend0_5', ''), tags)).toBe('trend0')
    // ② 最长前缀优先(歧义:'bo_' 与 'bo_burst_' 同时匹配 → 取更长的)
    expect(bandKeyOf(ev('bo_burst_3', ''), ['bo', 'bo_burst', 'tb'])).toBe('bo_burst')
    // ③ 都不匹配 → 回退 class_id(此处 class_id = 'xyz')
    expect(bandKeyOf(ev('xyz_9', ''), tags)).toBe('xyz')
  })
})

describe('subBandTagList', () => {
  const node = (nid: string, tag: string, grid?: 'price' | 'time'): TopoNode =>
    ({ node_id: nid, class_id: nid, source_tag: tag, where_rules: [],
       ...(grid ? { render_grid: grid } : {}) })

  it('render_grid=price 的 tag 被剔除,其余保序', () => {
    const topo = { nodes: [node('bo', 'bo', 'price'), node('burst', 'burst'), node('tb', 'tb', 'time')], edges: [] }
    expect(subBandTagList(['bo', 'burst', 'tb'], topo)).toEqual(['burst', 'tb'])
  })

  it('无 render_grid 字段 → 缺省 time,保留(与 renderGridOf 缺省一致)', () => {
    const topo = { nodes: [node('a', 'ta'), node('b', 'tb')], edges: [] }
    expect(subBandTagList(['ta', 'tb'], topo)).toEqual(['ta', 'tb'])
  })

  it('全 price → 空列表(bo_only 场景:副图无 band)', () => {
    const topo = { nodes: [node('bo', 'bo', 'price')], edges: [] }
    expect(subBandTagList(['bo'], topo)).toEqual([])
  })

  it('tag 匹配不到 node → 缺省 time,保留', () => {
    const topo = { nodes: [], edges: [] }
    expect(subBandTagList(['ghost'], topo)).toEqual(['ghost'])
  })
})

describe('isBandVisible', () => {
  const tagToNodes: Record<string, string[]> = {
    trend0: ['down'],
    burst:  ['burst'],
    bo:     ['bo'],
  }

  it('roleVisible 未传 → 所有 band 可见', () => {
    expect(isBandVisible('burst', undefined, tagToNodes)).toBe(true)
    expect(isBandVisible('trend0', undefined, tagToNodes)).toBe(true)
  })
  it('tagToNodes 无该 band 条目(空 nodeIds) → 可见', () => {
    expect(isBandVisible('unknown_band', { down: false }, tagToNodes)).toBe(true)
  })
  it('band 内所有 node 均 roleVisible===false → 不可见', () => {
    expect(isBandVisible('burst', { burst: false }, tagToNodes)).toBe(false)
  })
  it('band 内任一 node roleVisible!==false → 可见', () => {
    // trend0 有两个 node:一个 false,一个未设(undefined=可见)
    const twoNodes: Record<string, string[]> = { trend0: ['down', 'side'] }
    expect(isBandVisible('trend0', { down: false }, twoNodes)).toBe(true)
    expect(isBandVisible('trend0', { down: false, side: false }, twoNodes)).toBe(false)
  })
  it('roleVisible 为空对象(缺键) → 全部视为可见', () => {
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
    { class_id: 'trend', event_id: 'd1', start_idx: 0, end_idx: 5, source_tag: 'trend0', drawdown: 0.42 } as any,
    { class_id: 'burst', event_id: 'b1', start_idx: 1, end_idx: 1, source_tag: 'burst', count: 3, first_drought: 0, members: [{}, {}] } as any,
    { class_id: 'burst', event_id: 'b2', start_idx: 2, end_idx: 4, source_tag: 'burst', count: 5, max_bar_vol_ratio: 2.6378544926831706 } as any,
  ]
  const diag: Diagnostics = {
    symbol: 'X', pattern_id: 'p', note: '',
    roles: {
      down: {
        attr: [{ event_id: 'd1', start_idx: 0, end_idx: 5,
          clauses: { drawdown: { satisfied: true, measured: 0.42, op: '>=', threshold: 0.30 } } }],
        rel: [],
      },
      bo_burst: {
        attr: [{ event_id: 'b1', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: false, measured: 0, op: '>=', threshold: 20 },
            count: { satisfied: true, measured: 3, op: '>=', threshold: 2 },
          } }],
        rel: [],
      },
      tb_burst: {
        attr: [{ event_id: 'b1', start_idx: 1, end_idx: 1,
          clauses: {
            first_drought: { satisfied: true, measured: 0, op: '>=', threshold: 0 },
          } }],
        rel: [],
      },
    },
  }

  it('返回结构含 identity / clauses / raw 三键', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(Object.keys(r).sort()).toEqual(['clauses', 'identity', 'raw'])
  })

  it('identity.roles 单 role 时返回单元素数组', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.roles).toEqual(['down'])
  })

  it('identity.roles 多 role 时返回多元素数组（按 diag.roles 插入顺序）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    expect(r.identity.roles).toEqual(['bo_burst', 'tb_burst'])
  })

  it('identity.roles 零 role 时返回空数组', () => {
    const r = resolveTooltipData('b2', diag, events, bars)
    expect(r.identity.roles).toEqual([])
  })

  it('identity 区间事件 dateStart/End 均填日期', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('2024-03-06')
  })

  it('identity point 事件 dateEnd 为 null', () => {
    const r = resolveTooltipData('b1', diag, events, bars)   // b1 start_idx=end_idx=1
    expect(r.identity.dateStart).toBe('2024-03-02')
    expect(r.identity.dateEnd).toBe(null)
  })

  it('identity 区间事件 dateEnd 为 end_idx 对应日期', () => {
    const r = resolveTooltipData('b2', diag, events, bars)   // b2 start_idx=2, end_idx=4
    expect(r.identity.dateStart).toBe('2024-03-03')
    expect(r.identity.dateEnd).toBe('2024-03-05')
  })

  it('identity bars 越界时 fallback 到原索引字符串', () => {
    const shortBars: Bar[] = [bars[0]]
    const r = resolveTooltipData('d1', diag, events, shortBars)
    expect(r.identity.dateStart).toBe('2024-03-01')
    expect(r.identity.dateEnd).toBe('5')   // end_idx=5 越界
  })

  it('identity.eventId 直返参数', () => {
    const r = resolveTooltipData('d1', diag, events, bars)
    expect(r.identity.eventId).toBe('d1')
  })

  it('clauses 失败 ✗ 排在满足 ✓ 之前', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const sats = r.clauses.map((c) => c.satisfied)
    const firstSat = sats.indexOf(true)
    const lastUnsat = sats.lastIndexOf(false)
    expect(lastUnsat).toBeLessThan(firstSat)
  })

  it('clauses 多 role 同 cid 各保留一行（不覆盖）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const firstDroughtRows = r.clauses.filter((c) => c.cid === 'first_drought')
    expect(firstDroughtRows.length).toBe(2)   // bo_burst 一条 + tb_burst 一条
    const roles = firstDroughtRows.map((c) => c.role).sort()
    expect(roles).toEqual(['bo_burst', 'tb_burst'])
    const thresholds = firstDroughtRows.map((c) => c.threshold).sort()
    expect(thresholds).toEqual([0, 20])
  })

  it('clauses 单 role cid 只有一条', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    const countRows = r.clauses.filter((c) => c.cid === 'count')
    expect(countRows.length).toBe(1)
    expect(countRows[0].role).toBe('bo_burst')
  })

  it('raw 排除 SKIP 集（class_id/event_id/start_idx/end_idx/source_tag/members）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    expect('class_id' in r.raw).toBe(false)
    expect('event_id' in r.raw).toBe(false)
    expect('start_idx' in r.raw).toBe(false)
    expect('end_idx' in r.raw).toBe(false)
    expect('source_tag' in r.raw).toBe(false)
    expect('members' in r.raw).toBe(false)
  })

  it('raw 去重 clauses 已引用 cid（cid 名 ↔ 字段名命中时移除 raw 那份）', () => {
    const r = resolveTooltipData('b1', diag, events, bars)
    // b1 字段含 count + first_drought；diag 里 bo_burst 也评估 first_drought + count
    expect('first_drought' in r.raw).toBe(false)
    expect('count' in r.raw).toBe(false)
  })

  it('raw 保留 clauses 未引用的字段', () => {
    const r = resolveTooltipData('b2', diag, events, bars)
    // b2 不在任何 role 的 attr 表 → clauses 为空 → raw 保留全部非 SKIP 字段
    expect(r.raw.count).toBe(5)
    expect(r.raw.max_bar_vol_ratio).toBeCloseTo(2.6378544926831706, 10)
  })

  it('未知 event_id → 空 clauses / 空 raw / identity 仅 eventId 有值', () => {
    const r = resolveTooltipData('zzz', diag, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.raw).toEqual({})
    expect(r.identity.eventId).toBe('zzz')
    expect(r.identity.roles).toEqual([])
  })

  it('diag === null → 空 clauses，identity / raw 正常', () => {
    const r = resolveTooltipData('d1', null, events, bars)
    expect(r.clauses).toEqual([])
    expect(r.identity.eventId).toBe('d1')
    expect(r.identity.roles).toEqual([])   // 无 diag 无 role
    expect(r.raw.drawdown).toBe(0.42)
  })
})
