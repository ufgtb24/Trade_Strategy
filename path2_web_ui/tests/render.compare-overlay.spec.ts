// compare 叠画(render/compareOverlay.ts + annotateLanes.ts 的 compare 系列)与 tier tag(render/tierTags.ts、
// chart.ts 的 tier-tags 系列):event 叠到 mapping 对到的特征轨上(没有框的特征另起一条),hit 叠到 bracket 轨上、
// 排在样本跨度下面;档位色;tiers 开着才挂 qualified_only / detected_only;第一段不挂任何对照 tag。
import { describe, it, expect } from 'vitest'
import { buyDaysOf, compareLanes, laneRowsFor, packHits } from '../src/render/compareOverlay'
import {
  APP_AMBER, APP_BAR_H, APP_ROW_H, INK, LANE_PAD, appBarY, bracketGeometry, buildAnnotateSubOption, laneGeometry,
} from '../src/render/annotateLanes'
import { nextStarts, tierTagOf, tierTagShape, tierTagWidth, TIER_TAG_TIP } from '../src/render/tierTags'
import { computeEventData, buildSubOption } from '../src/render/chart'
import { computeSubGeometry } from '../src/render/subGeometry'
import type { Lane } from '../src/annotate/model'
import type { EventDict, HitDict, Tier } from '../src/types'

const ev = (node: string, s: number, e: number, k = 0): EventDict =>
  ({ instance_id: `${node}@${s}-${e}#${k}`, node_id: node, instance_idx: k, start_idx: s, end_idx: e })
const box = (id: string, feature: string | null, start: string, end: string) => ({ id, feature, start, end })
const DATES = Array.from({ length: 12 }, (_, i) => `2025-01-${String(i + 2).padStart(2, '0')}`)

const BASE: Lane[] = [
  { key: 'w-a', parent: null, rows: 1, boxes: [{ box: box('b1', 'w-a', DATES[1], DATES[4]), row: 0 }] },
  { key: 'w-b', parent: null, rows: 1, boxes: [{ box: box('b2', 'w-b', DATES[6], DATES[7]), row: 0 }] },
  { key: null, parent: null, rows: 1, boxes: [{ box: box('b3', null, DATES[0], DATES[0]), row: 0 }] },
]
const TIER: Record<string, Tier> = { 'x@1-3#0': 'in_hit', 'x@2-6#0': 'qualified', 'y@8-8#0': 'detected', 'z@5-5#0': 'detected' }
const tierOf = (e: EventDict) => TIER[e.instance_id] ?? 'detected'

describe('compare:event 叠到哪条轨、哪一行', () => {
  const events = [ev('x', 1, 3), ev('x', 2, 6), ev('y', 8, 8), ev('z', 5, 5), ev('u', 0, 1)]

  it('mapping 对到的特征轨上画那个 node 的 event;没进 mapping 的 node、不在词表里的特征不画', () => {
    const { lanes, app } = compareLanes(BASE, { 'w-a': 'x', 'w-zz': 'u' }, events, tierOf, f => f !== 'w-zz')
    expect(lanes.map(l => l.key)).toEqual(['w-a', 'w-b', null])
    expect(app[0].events.map(e => [e.node, e.start, e.end, e.tier, e.row])).toEqual([
      ['x', 1, 3, 'in_hit', 0], ['x', 2, 6, 'qualified', 1]])   // 交叠的分两行
    expect(app[0].rows).toBe(2)
    expect([app[1].events, app[2].events]).toEqual([[], []])
    expect(lanes[0].rows).toBe(Math.max(1, laneRowsFor(2)))
    expect(lanes[0].boxes).toBe(BASE[0].boxes)                   // 框不动
  })

  it('这张图上没有框、却有 event 的特征另起一条轨,排在特征轨之后、unnamed 之前(按 event 先后);几个特征对同一个 node 各画一份', () => {
    const { lanes, app } = compareLanes(BASE, { 'w-a': 'x', 'w-c': 'y', 'w-d': 'z', 'w-e': 'x' }, events, tierOf, () => true)
    expect(lanes.map(l => [l.key, l.boxes.length])).toEqual([
      ['w-a', 1], ['w-b', 0 + 1], ['w-e', 0], ['w-d', 0], ['w-c', 0], [null, 1]])
    expect(app[2].events.map(e => e.id)).toEqual(['x@1-3#0', 'x@2-6#0'])
    expect(app[3].events.map(e => e.node)).toEqual(['z'])
    expect(lanes.every(l => l.rows >= 1)).toBe(true)
  })

  it('只显示、不进求解的 node 不分档(不挂 tier tag)', () => {
    const { app } = compareLanes(BASE, { 'w-a': 'x', 'w-b': 'y' }, events, tierOf, () => true, new Set(['y']))
    expect(app[0].events.every(e => e.tiered)).toBe(true)
    expect(app[1].events.map(e => e.tiered)).toEqual([false])
  })

  it('hit 各自分行', () => {
    const ms = [{ hit_id: 'm0', start_idx: 1, end_idx: 3 }, { hit_id: 'm1', start_idx: 2, end_idx: 4 },
                { hit_id: 'm2', start_idx: 5, end_idx: 5 }] as HitDict[]
    const { rows, placed } = packHits(ms)
    expect(rows).toBe(2)
    expect(placed.map(h => [h.id, h.row])).toEqual([['m0', 0], ['m1', 1], ['m2', 0]])
  })

  it('hit 的买入日照 eval_meta 的 end_node 取:node 取它的 event 跨度,node.slot 取 slot 里 child 的跨度并起来', () => {
    const tb: EventDict = { ...ev('tb', 4, 12), child_refs: { segments: ['seg@5-6#0', 'seg@9-9#0'] } }
    const evs = [tb, ev('seg', 5, 6), ev('seg', 9, 9), ev('burst', 2, 3)]
    const m = { hit_id: 'm0', start_idx: 2, end_idx: 12, node_index: { tb: tb.instance_id, burst: 'burst@2-3#0' } } as unknown as HitDict
    const byId = new Map(evs.map(e => [e.instance_id, e]))
    expect(buyDaysOf(m, byId, 'tb.segments')).toEqual([5, 6, 9])
    expect(buyDaysOf(m, byId, 'burst')).toEqual([2, 3])
    expect(buyDaysOf(m, byId, 'nope')).toEqual([])
    expect(buyDaysOf(m, byId, null)).toEqual([])
    expect(packHits([m], evs, 'tb.segments').placed[0].buys).toEqual([5, 6, 9])
    expect(packHits([m]).placed[0].buys).toEqual([])
  })
})

describe('compare 的系列', () => {
  const events = [ev('x', 1, 3), ev('x', 2, 6), ev('y', 8, 8)]
  const { lanes, app } = compareLanes(BASE, { 'w-a': 'x', 'w-b': 'y' }, events, tierOf, () => true)
  const bg = bracketGeometry(3)
  const { geom } = laneGeometry(lanes, bg.top + bg.h)
  const hits = packHits([{ hit_id: 'm0', start_idx: 1, end_idx: 3 }] as HitDict[])
  const draw = (tiers: boolean) => buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
    lanes, geom, nameOf: f => f, selectedId: null, preview: null, draft: null, zoom: null, width: 800,
    bracket: { geom: bg, placed: [] },
    compare: { app, hits: hits.placed, hitRow0: 2, nodeColors: { x: '#1a80ba' }, tiers },
  }) as any
  const series = (opt: any, name: string) => opt.series.find((s: any) => s.name === name)
  const api = (row: any[]) => ({ size: () => [10], coord: ([i]: number[]) => [i * 10 + 5], value: (k: number) => row[k] })
  const cs = { x: 0, y: 0, width: 1000, height: 300 }

  it('只多出 event、tier tag、hit 三个系列,图上没有任何对照 tag 的字样', () => {
    const opt = draw(true)
    expect(opt.series.map((s: any) => s.name)).toEqual(
      ['annotation-boxes', 'annotation-brackets', 'compare-events', 'compare-tier-tags', 'compare-hits'])
    const texts = JSON.stringify(opt.graphic)
    for (const t of ['missing', 'matched', 'unmatched', 'connected', 'unmapped', 'excluded', 'chance_high', 'must']) {
      expect(texts).not.toContain(t)
    }
  })

  it('event:档位色(进了 hit 的画 node 本色,qualified 深灰,detected 浅灰),竖直居中在轨里,压在框下面', () => {
    const s = series(draw(true), 'compare-events')
    const fills = s.data.map((_: any, i: number) => s.renderItem({ dataIndex: i, coordSys: cs }, api(s.data[i])).style.fill)
    expect(fills).toEqual(['#1a80ba', '#9ca3af', '#d1d5db'])
    expect(s.data[0][2]).toBe(appBarY(geom[0], app[0].rows, 0).top)
    expect(s.data[1][2]).toBe(appBarY(geom[0], app[0].rows, 1).top)
    const blockTop = s.data[0][2], blockBottom = s.data[1][2] + APP_BAR_H
    expect(blockTop - (geom[0].top + LANE_PAD)).toBeCloseTo(geom[0].top + geom[0].h - LANE_PAD - blockBottom)   // 居中
    expect(s.z).toBeLessThan(series(draw(true), 'annotation-boxes').z)
    const el = s.renderItem({ dataIndex: 0, coordSys: cs }, api(s.data[0]))
    expect([el.shape.x, el.shape.width, el.style.lineDash]).toEqual([10, 30, undefined])   // 实心,和框一样占整根 K 线
    expect(s.tooltip.formatter({ dataIndex: 0 })).toContain('in_hit')       // 档位用 spec 4.3 的名字
    expect(s.tooltip.formatter({ dataIndex: 2 })).toContain('detected')
    expect(s.tooltip.formatter({ dataIndex: 0 })).not.toContain('x ·')     // 不写 node(那等于露出 mapping)
  })

  it('tiers 开着:灰条右端挂 qualified_only / detected_only,进了 hit 的不挂;关掉就一个都不挂', () => {
    const on = series(draw(true), 'compare-tier-tags')
    expect(on.data).toHaveLength(2)
    const tag = on.renderItem({ dataIndex: 1, coordSys: cs }, api(on.data[1]))
    expect(tag.children[1].style.text).toBe('detected_only')
    expect([tag.children[0].style.fill, tag.children[0].style.stroke]).toEqual(['#d1d5db', '#111'])
    expect(on.tooltip.formatter({ dataIndex: 0 })).toContain(TIER_TAG_TIP.qualified_only)
    expect(series(draw(false), 'compare-tier-tags').data).toEqual([])
  })

  it('tier tag 不压用户框的竖边:横跨框边就不挂', () => {
    // x@2-6 的条右端在第 6 根右边(x=70),框 b2 在 w-b 轨上;w-a 轨的框 b1 是第 1..4 根(x 10..50),不挡
    const s = series(draw(true), 'compare-tier-tags')
    expect(s.renderItem({ dataIndex: 0, coordSys: cs }, api(s.data[0])).children).toHaveLength(2)
    // y@8 在 w-b 轨,框 b2 是第 6..7 根:tag 从第 8 根右边起,不跨框边 → 挂;把框挪到第 8..10 根,tag 就跨了右边
    const lanes2 = lanes.map((l, i) => (i === 1 ? { ...l, boxes: [{ box: box('b2', 'w-b', DATES[8], DATES[10]), row: 0 }] } : l))
    const opt = buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
      lanes: lanes2, geom, nameOf: f => f, selectedId: null, preview: null, draft: null, zoom: null, width: 800,
      compare: { app, hits: [], hitRow0: 0, nodeColors: {}, tiers: true },
    }) as any
    const s2 = series(opt, 'compare-tier-tags')
    expect(s2.renderItem({ dataIndex: 1, coordSys: cs }, api(s2.data[1]))).toBeNull()   // null:删掉上次画的 tag
  })

  it('hit:bracket 轨上排在样本跨度的那几行下面,app 琥珀底、细黑实线边', () => {
    const s = series(draw(true), 'compare-hits')
    expect(s.data).toHaveLength(1)
    const rowTop = bg.top + LANE_PAD + 2 * 13 + (13 - 9) / 2
    expect(s.data[0][2]).toBe(rowTop)
    const el = s.renderItem({}, api(s.data[0]))
    expect([el.style.fill, el.style.stroke, el.style.lineDash]).toEqual([APP_AMBER, INK, undefined])
  })

  it('hit 条里每个买入日一个黑色 ▼,画在那根 K 线的中心', () => {
    const withBuys = [{ ...hits.placed[0], buys: [1, 3] }]
    const opt = buildAnnotateSubOption(DATES.map(date => ({ date } as any)), {
      lanes, geom, nameOf: f => f, selectedId: null, preview: null, draft: null, zoom: null, width: 800,
      bracket: { geom: bg, placed: [] },
      compare: { app, hits: withBuys, hitRow0: 2, nodeColors: { x: '#1a80ba' }, tiers: true },
    }) as any
    const s = series(opt, 'compare-hits')
    const el = s.renderItem({ dataIndex: 0 }, api(s.data[0]))
    expect(el.type).toBe('group')
    expect(el.children[0].style.fill).toBe(APP_AMBER)
    const tris = el.children.slice(1)
    expect(tris.map((t: any) => [t.type, t.style.fill, t.shape.points[2][0]])).toEqual([['polygon', INK, 15], ['polygon', INK, 35]])
    expect(s.tooltip.formatter({ dataIndex: 0 })).toContain('buy ×2')
  })
})

describe('tier tag', () => {
  it('只有 qualified、detected 挂,进了 hit 的不挂', () => {
    expect([tierTagOf('in_hit'), tierTagOf('qualified'), tierTagOf('detected')]).toEqual([null, 'qualified_only', 'detected_only'])
  })
  it('同一行下一个的起点;不同行互不相干', () => {
    expect(nextStarts([{ key: 'a', start: 5, end: 6 }, { key: 'a', start: 0, end: 2 }, { key: 'b', start: 3, end: 3 },
                       { key: 'a', start: 9, end: 9 }])).toEqual([9, 5, -1, -1])
  })
  it('放不下(碰到下一个条或图右缘)不画;放得下贴在条右端、和条同高居中', () => {
    const w = tierTagWidth('qualified_only')
    expect(tierTagShape('qualified_only', 100, 10, 7, 100 + w)).toBeNull()
    const g = tierTagShape('qualified_only', 100, 10, 7, 1000)
    expect(g.children[0].shape.x).toBe(102)
    expect(g.children[0].shape.y + g.children[0].shape.height / 2).toBe(13.5)
  })
  it('app 模式的副图:tiers 开着才有 tier-tags 数据;只显示的 node、进了 hit 的不挂', () => {
    const topology = { nodes: [{ node_id: 'a', where_rules: [] }, { node_id: 'b', where_rules: [] },
                               { node_id: 'p', where_rules: [], solve: false }], edges: [] }
    const events = [ev('a', 0, 2), ev('a', 4, 5), ev('b', 1, 1), ev('p', 3, 4)]
    const tiers: Record<string, Tier> = { 'a@0-2#0': 'in_hit', 'a@4-5#0': 'qualified', 'b@1-1#0': 'detected' }
    const bars = DATES.slice(0, 8).map(date => ({ date, o: 1, h: 1, l: 1, c: 1, v: 1, rv: 1 }))
    const input: any = {
      topology, isolatedNodeIds: new Set(), tagList: ['a', 'b', 'p'], level: 'detected', nodeColors: {},
      eventTier: (e: EventDict) => tiers[e.instance_id] ?? 'detected', nodeOfEventByBand: (e: EventDict) => e.node_id,
      bandKeyOf: (e: EventDict) => e.node_id, tagToNodes: { a: ['a'], b: ['b'], p: ['p'] },
    }
    const bundle = computeEventData(bars, events, [], input)
    expect(bundle.tierTagData.map(d => [d.value[0], d.text, d.point])).toEqual([[4, 'qualified_only', false], [1, 'detected_only', true]])
    const geom = computeSubGeometry({ bracketLaneCount: 0, bandLaneCounts: [1, 1, 1] })
    const pick = (o: any) => o.series.find((s: any) => s.name === 'tier-tags').data
    expect(pick(buildSubOption(bars, bundle, geom, { ...input, tiers: true }, 800))).toHaveLength(2)
    expect(pick(buildSubOption(bars, bundle, geom, { ...input, tiers: false }, 800))).toEqual([])
  })
})

it('event 块的条高、行高同主视图副图', () => {
  expect([APP_BAR_H, APP_ROW_H]).toEqual([7, 9])
})
