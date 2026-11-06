// 副图折叠的纯函数:认族、梳子 / 整条、档位筛选、hit 折叠与买入日、同一格成员的区分标签。
import { describe, it, expect } from 'vitest'
import {
  buyDaysOf, familyKeyOf, foldBand, foldHits, formatMemberLabel, hitLabels, memberLabels,
} from '../src/render/fold'
import type { EventDict, HitDict, Tier } from '../src/types'

function ev(node: string, s: number, e: number, idx = 0, extra: Partial<EventDict> = {}): EventDict {
  return { instance_id: `${node}@${s}-${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, ...extra }
}

function fold(events: EventDict[], tiers: Record<string, Tier>, level: 'detected' | 'qualified' | 'in_hit' = 'detected',
              extra: { isPoint?: boolean; levelImmune?: boolean } = {}) {
  return foldBand(events, {
    band: 'p', isPoint: extra.isPoint ?? false, level, levelImmune: extra.levelImmune,
    tierOf: (e) => tiers[e.instance_id] ?? 'detected',
  })
}

describe('foldBand — 认族', () => {
  it('同起点折成一族,起点不同不折;族按起点升序,键 = band@起点', () => {
    const fs = fold([ev('p', 5, 9), ev('p', 0, 3), ev('p', 0, 4), ev('p', 5, 7)], {})
    expect(fs.map(f => f.key)).toEqual(['p@0', 'p@5'])
    expect(fs.map(f => [f.start, f.end])).toEqual([[0, 4], [5, 9]])
    expect(familyKeyOf('p', 5)).toBe('p@5')
  })

  it('终点相同、起点不同的两段不合并', () => {
    const fs = fold([ev('p', 0, 9), ev('p', 3, 9)], {})
    expect(fs).toHaveLength(2)
    expect(fs.every(f => !f.multi && f.marks[0].kind === 'bar')).toBe(true)
  })
})

describe('foldBand — 梳子与整条', () => {
  it('单成员族是一根整条 [起点, 终点]', () => {
    const [f] = fold([ev('p', 2, 6)], { 'p@2-6#0': 'qualified' })
    expect(f.multi).toBe(false)
    expect(f.marks).toEqual([{ kind: 'bar', start: 2, end: 6, memberIds: ['p@2-6#0'], tier: 'qualified' }])
  })

  it('多成员族每个不同终点一格,格只占终点那一根', () => {
    const [f] = fold([ev('p', 0, 3), ev('p', 0, 5), ev('p', 0, 4)], {})
    expect(f.multi).toBe(true)
    expect(f.marks.map(m => [m.kind, m.start, m.end])).toEqual([['cell', 3, 3], ['cell', 4, 4], ['cell', 5, 5]])
    expect(f.memberIds).toEqual(['p@0-3#0', 'p@0-4#0', 'p@0-5#0'])
  })

  it('梳子还是整条按筛选前的成员数:in_hit 档下只剩一个成员的族仍是一格,不变回整条', () => {
    const tiers: Record<string, Tier> = { 'p@0-5#0': 'in_hit' }
    const [f] = fold([ev('p', 0, 3), ev('p', 0, 4), ev('p', 0, 5)], tiers, 'in_hit')
    expect(f.multi).toBe(true)
    expect(f.marks).toEqual([{ kind: 'cell', start: 5, end: 5, memberIds: ['p@0-5#0'], tier: 'in_hit' }])
  })

  it('筛选后族的右端缩到剩下成员的最大终点;筛空的族丢掉', () => {
    const tiers: Record<string, Tier> = { 'p@0-3#0': 'qualified', 'p@0-4#0': 'in_hit' }
    const fs = fold([ev('p', 0, 3), ev('p', 0, 4), ev('p', 0, 9), ev('p', 6, 8)], tiers, 'qualified')
    expect(fs).toHaveLength(1)
    expect([fs[0].start, fs[0].end]).toEqual([0, 4])
    expect(fs[0].marks.map(m => m.end)).toEqual([3, 4])
  })

  it('只显示、不求解的 node 不受档位筛选', () => {
    const fs = fold([ev('p', 0, 3), ev('p', 0, 4)], {}, 'in_hit', { levelImmune: true })
    expect(fs[0].memberIds).toHaveLength(2)
  })

  it('跨度完全相同的成员落在同一格:格取最深的档,成员顺序深 → 浅,同档按输入顺序', () => {
    const a = ev('p', 0, 4, 0), b = ev('p', 0, 4, 1), c = ev('p', 0, 4, 2), d = ev('p', 0, 2)
    const tiers: Record<string, Tier> = { [a.instance_id]: 'detected', [b.instance_id]: 'in_hit', [c.instance_id]: 'detected' }
    const [f] = fold([a, b, c, d], tiers)
    expect(f.marks.map(m => m.end)).toEqual([2, 4])
    expect(f.marks[1].tier).toBe('in_hit')
    expect(f.marks[1].memberIds).toEqual([b.instance_id, a.instance_id, c.instance_id])
    expect(f.memberIds).toEqual([d.instance_id, b.instance_id, a.instance_id, c.instance_id])
  })

  it('声明为点的 node 每族一个点记号,档位取最深(成员深 → 浅)', () => {
    const a = ev('t', 7, 7, 0), b = ev('t', 7, 7, 1)
    const [f] = fold([a, b], { [b.instance_id]: 'qualified' }, 'detected', { isPoint: true })
    expect(f.marks).toEqual([{ kind: 'point', start: 7, end: 7, memberIds: [b.instance_id, a.instance_id], tier: 'qualified' }])
  })

  it('没声明为点的 node,单根实例也是一根整条(不看实例自身跨度)', () => {
    const [f] = fold([ev('p', 7, 7)], {})
    expect(f.isPoint).toBe(false)
    expect(f.marks[0].kind).toBe('bar')
  })
})

// new_step 式的夹具:容器 plateau 引用 step / today 子段,hit 的买点 = plateau.today
const steps = [ev('step', 10, 10), ev('step', 10, 11)]
const todays = [ev('today', 13, 13), ev('today', 14, 14)]
const plats = [
  ev('plateau', 0, 13, 0, { child_refs: { step: [steps[0].instance_id], today: [todays[0].instance_id] } }),
  ev('plateau', 0, 13, 1, { child_refs: { step: [steps[1].instance_id], today: [todays[0].instance_id] } }),
  ev('plateau', 0, 14, 0, { child_refs: { step: [steps[0].instance_id], today: [todays[1].instance_id] } }),
]
const allEvents = [...steps, ...todays, ...plats]
const byId = new Map(allEvents.map(e => [e.instance_id, e]))
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id }, children: [p.instance_id],
})
const hits = [hit('h2', plats[2]), hit('h0', plats[0]), hit('h1', plats[1]),
              { hit_id: 'h9', start_idx: 3, end_idx: 6, node_index: {}, children: [] }]

describe('buyDaysOf', () => {
  it('node.slot:取 slot 里 child event 跨度的每一根', () => {
    expect(buyDaysOf(hits[0], byId, 'plateau.today')).toEqual([14])
  })
  it('node:取这个 node 的 event 本身的跨度', () => {
    const q = ev('q', 2, 4)
    const m: HitDict = { hit_id: 'x', start_idx: 2, end_idx: 4, node_index: { q: q.instance_id }, children: [q.instance_id] }
    expect(buyDaysOf(m, new Map([[q.instance_id, q]]), 'q')).toEqual([2, 3, 4])
  })
  it('没有 endNode、或解析不到 → 空', () => {
    expect(buyDaysOf(hits[0], byId, null)).toEqual([])
    expect(buyDaysOf(hits[3], byId, 'plateau.today')).toEqual([])
  })
})

describe('foldHits', () => {
  it('hit 同起点折成一族;族内按终点、同终点按输入顺序;买入日带买在这天的 hit', () => {
    const fs = foldHits(hits, allEvents, 'plateau.today')
    expect(fs.map(f => f.key)).toEqual(['hits@0', 'hits@3'])
    const [f, g] = fs
    expect(f.multi).toBe(true)
    expect(f.hitIds).toEqual(['h0', 'h1', 'h2'])
    expect(f.marks).toEqual([
      { kind: 'cell', start: 13, end: 13, hitIds: ['h0', 'h1'] },
      { kind: 'cell', start: 14, end: 14, hitIds: ['h2'] },
    ])
    expect(f.buys).toEqual([{ day: 13, hitIds: ['h0', 'h1'] }, { day: 14, hitIds: ['h2'] }])
    // bracket 一律画梳子:只有一次 hit 的族也是终点一格(不画整条琥珀条)
    expect(g.marks).toEqual([{ kind: 'cell', start: 6, end: 6, hitIds: ['h9'] }])
    expect(g.buys).toEqual([])
  })
})

describe('memberLabels / hitLabels', () => {
  it('① 第一个跨度不同的子段槽:标签取那个子段的终点', () => {
    const ls = memberLabels([plats[0].instance_id, plats[1].instance_id], byId, [])
    expect(ls).toEqual([
      { via: 'step', ref_id: steps[0].instance_id, idx: 10 },
      { via: 'step', ref_id: steps[1].instance_id, idx: 11 },
    ])
    expect(formatMemberLabel(ls[1], Array.from({ length: 20 }, (_, i) => `d${i}`))).toBe('step → d11')
  })

  it('② 子段分不开时看锚字段,idx 取被锚事件的起点', () => {
    const bo1 = ev('bo', 3, 3), bo2 = ev('bo', 5, 5)
    const a = ev('tb', 8, 12, 0, { anchor_bo_id: bo1.instance_id }), b = ev('tb', 8, 12, 1, { anchor_bo_id: bo2.instance_id })
    const m = new Map([bo1, bo2, a, b].map(e => [e.instance_id, e]))
    expect(memberLabels([a.instance_id, b.instance_id], m, ['anchor_bo_id']).map(l => [l.via, l.idx]))
      .toEqual([['anchor_bo_id', 3], ['anchor_bo_id', 5]])
  })

  it('③ 还分不开就用 instance_id;一个成员也用 instance_id', () => {
    const a = ev('x', 1, 2, 0), b = ev('x', 1, 2, 1)
    const m = new Map([a, b].map(e => [e.instance_id, e]))
    expect(memberLabels([a.instance_id, b.instance_id], m, []).map(l => l.via)).toEqual(['instance_id', 'instance_id'])
    expect(memberLabels([a.instance_id], m, [])[0]).toEqual({ via: 'instance_id', ref_id: a.instance_id, idx: null })
    expect(formatMemberLabel({ via: 'instance_id', ref_id: 'x#0', idx: null }, [])).toBe('instance_id: x#0')
  })

  it('hitLabels:按拓扑 node 顺序找第一个绑定实例不全相同的 node,对它调 memberLabels', () => {
    const hm = new Map(hits.map(h => [h.hit_id, h]))
    expect(hitLabels(['h0', 'h1'], hm, byId, ['plateau', 'step'], []).map(l => [l.via, l.idx]))
      .toEqual([['step', 10], ['step', 11]])
    expect(hitLabels(['h0'], hm, byId, ['plateau'], [])).toEqual([{ via: 'hit_id', ref_id: 'h0', idx: null }])
  })
})
