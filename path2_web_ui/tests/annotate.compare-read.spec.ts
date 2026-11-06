// compare 的读数(annotate/compareRead.ts):样本日 / 框终点那天在场的 event、配对规则、match 与 ▲ 旁的记号、
// diagnose 的行(只给档位与没过的 where 名)、←/→ 在样本间走、进 compare 时默认聚焦哪个样本。夹具是小合成数据。
import { describe, it, expect } from 'vitest'
import {
  dayEvents, defaultFocus, diagnoseRows, matchMark, matchOf, pairOn, stepSample,
} from '../src/annotate/compareRead'
import type { Diagnostics, EventDict, HitDict, Tier } from '../src/types'

const ev = (node: string, s: number, e: number, k = 0, extra: Partial<EventDict> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${k}`, node_id: node, instance_idx: k, start_idx: s, end_idx: e, confirm_idx: e, ...extra })
const hit = (id: string, node: string, e: EventDict): HitDict =>
  ({ hit_id: id, start_idx: e.start_idx, end_idx: e.end_idx, node_index: { [node]: e.instance_id }, children: [e.instance_id] })

// 第 20 天:起点 10 的一族有两个阶跃前缀,两个都进了 hit;起点 2 的一族一个,只检测到;起点 10 那族第 21 天还有一个
const stepA = ev('step', 15, 15), stepB = ev('step', 15, 16), stepOld = ev('step', 8, 8)
const p1 = ev('plateau', 10, 20, 0, { child_refs: { step: [stepA.instance_id] } })
const p2 = ev('plateau', 10, 20, 1, { child_refs: { step: [stepB.instance_id] } })
const pOld = ev('plateau', 2, 20, 0, { child_refs: { step: [stepOld.instance_id] } })
const pNext = ev('plateau', 10, 21, 0, { child_refs: { step: [stepA.instance_id] } })
const EVENTS = [stepA, stepB, stepOld, p1, p2, pOld, pNext]
const HITS = [hit('h1', 'plateau', p1), hit('h2', 'plateau', p2), hit('h3', 'plateau', pNext)]
const IN_HIT = new Set([p1, p2, pNext].map(e => e.instance_id))
const tierOf = (e: EventDict): Tier => (IN_HIT.has(e.instance_id) ? 'in_hit' : 'detected')
const TOL = { pos: 3, neg: 1, sub: 2 }   // 调用方传路由带出的值;这里取 spec 第 10 节的默认
const DIAG: Diagnostics = {
  symbol: 'X', pattern_id: 'p', note: '',
  nodes: { plateau: { rel: [], attr: [
    { instance_id: pOld.instance_id, node_id: 'plateau', start_idx: 2, end_idx: 20, clauses: {
      old_flat: { satisfied: true, measured: 0.5, op: '<=', threshold: 1.2, label: 'x' } as any,
      new_hold: { satisfied: false, measured: 0.1, op: '>=', threshold: 0.3, label: 'x' } as any,
      new_calm: { satisfied: false, measured: 0.9, op: '<=', threshold: 0.6, label: 'x' } as any } },
  ] } },
}

describe('那天在场的 event', () => {
  it('复合事件取终点在那天的;跨度型取盖住那天且已确认的;确认根晚于那天的不算', () => {
    expect(dayEvents(EVENTS, 'plateau', 20).map(e => e.instance_id).sort()).toEqual(
      [p1, p2, pOld].map(e => e.instance_id).sort())
    const seg = ev('seg', 5, 30, 0, { confirm_idx: 6 }), late = ev('seg', 18, 30, 0, { confirm_idx: 25 })
    expect(dayEvents([seg, late], 'seg', 20)).toEqual([seg])
  })
})

describe('配对', () => {
  it('那天有 hit:取 hit 绑定的 event,几个 hit 时取结果里在前的', () => {
    const p = pairOn(20, 'plateau', EVENTS, HITS, tierOf)
    expect(p.event?.instance_id).toBe(p1.instance_id)
    expect(p.hitId).toBe('h1')
    expect(p.present).toHaveLength(3)
  })
  it('给了子框:取子段和子框对上的那个(子段终点在子框终点前后 2 根内)', () => {
    const p = pairOn(20, 'plateau', EVENTS, HITS, tierOf, { subBox: { box: { start: 16, end: 16, slot: 'step' }, tol: TOL.sub } })
    expect(p.event?.instance_id).toBe(p2.instance_id)
    expect(p.hitId).toBe('h2')
  })
  it('子框一个都对不上:当没给子框,照「当天 hit → 最深档」在全部在场的 event 里挑', () => {
    const far = { box: { start: 2, end: 3, slot: 'step' }, tol: TOL.sub }
    const p = pairOn(20, 'plateau', EVENTS, HITS, tierOf, { subBox: far })
    expect(p.event?.instance_id).toBe(p1.instance_id)
    expect(p.hitId).toBe('h1')
    const q = pairOn(20, 'plateau', EVENTS, [], tierOf, { subBox: far })
    expect(q.event?.instance_id).toBe(p1.instance_id)   // 最深档 in_hit、起点最晚的那族,结果里在前的
    expect(q.hitId).toBeNull()
  })
  it('没有 hit:取最深档,同档取起点最晚的', () => {
    const a = ev('plateau', 3, 40), b = ev('plateau', 7, 40), c = ev('plateau', 1, 40)
    const t = (e: EventDict): Tier => (e === c ? 'qualified' : 'detected')
    expect(pairOn(40, 'plateau', [a, b, c], [], t).event).toBe(c)
    expect(pairOn(40, 'plateau', [a, b], [], () => 'detected').event).toBe(b)
  })
  it('那天一个都没有:event 为 null', () => {
    const p = pairOn(19, 'plateau', EVENTS, HITS, tierOf)
    expect(p.event).toBeNull()
    expect(p.present).toEqual([])
  })
})

describe('match', () => {
  const buy = new Map([['h1', [20]], ['h2', [20]], ['h3', [21]]])
  const buyDaysOf = (h: HitDict) => buy.get(h.hit_id) ?? []
  it('取离样本日最近的买点;正样本 tol.pos 根内算 matched,负样本 tol.neg 根', () => {
    expect(matchOf(20, 'pos', HITS, buyDaysOf, TOL)).toEqual({ state: 'matched', hitId: 'h1', offset: 0 })
    expect(matchOf(18, 'pos', HITS, buyDaysOf, TOL)).toEqual({ state: 'matched', hitId: 'h1', offset: 2 })
    expect(matchOf(18, 'neg', HITS, buyDaysOf, TOL)).toEqual({ state: 'unmatched', hitId: null, offset: null })
    expect(matchOf(24, 'pos', HITS, buyDaysOf, TOL)).toEqual({ state: 'matched', hitId: 'h3', offset: -3 })
    expect(matchOf(25, 'pos', HITS, buyDaysOf, TOL).state).toBe('unmatched')
    expect(matchOf(18, 'neg', HITS, buyDaysOf, { ...TOL, neg: 2 }).state).toBe('matched')
  })
  it('▲ 旁的记号:app 与用户的判断一致写 ✓,不一致写 ✗', () => {
    const m = { state: 'matched', hitId: 'h1', offset: 0 } as const
    const u = { state: 'unmatched', hitId: null, offset: null } as const
    expect([matchMark('pos', m), matchMark('pos', u), matchMark('neg', m), matchMark('neg', u)]).toEqual(['✓', '✗', '✗', '✓'])
  })
})

describe('diagnose 的行', () => {
  it('配对的在最前,其余按档位、起点;同族同格才有消歧标签;只给档位和没过的 where 名', () => {
    const p = pairOn(20, 'plateau', EVENTS, HITS, tierOf)
    const label = (e: EventDict) => `step → ${e === p1 ? 15 : 16}`
    const rows = diagnoseRows(p, DIAG, tierOf, label)
    expect(rows.map(r => [r.instanceId, r.member, r.level, r.failed, r.paired])).toEqual([
      [p1.instance_id, 'step → 15', 'in_hit', [], true],
      [p2.instance_id, 'step → 16', 'in_hit', [], false],
      [pOld.instance_id, null, 'detected', ['new_hold', 'new_calm'], false],
    ])
    expect(JSON.stringify(rows)).not.toMatch(/measured|threshold|0\.9|1\.2/)
  })
})

describe('样本之间走、默认聚焦', () => {
  const S = [{ id: 'c', day: 30 }, { id: 'a', day: 10 }, { id: 'b', day: 20 }]
  it('←/→ 按样本日走,到头不动;当前不在列表里时从头或尾开始', () => {
    expect(stepSample(S, 'a', 1)).toBe('b')
    expect(stepSample(S, 'c', 1)).toBe('c')
    expect(stepSample(S, 'b', -1)).toBe('a')
    expect(stepSample(S, null, 1)).toBe('a')
    expect(stepSample(S, null, -1)).toBe('c')
    expect(stepSample([], null, 1)).toBeNull()
  })
  it('进 compare:已有选中的样本就用它,否则取离图窗中心最近的', () => {
    expect(defaultFocus(S, 'c', 11)).toBe('c')
    expect(defaultFocus(S, 'zz', 18)).toBe('b')
    expect(defaultFocus([], null, 5)).toBeNull()
  })
})
