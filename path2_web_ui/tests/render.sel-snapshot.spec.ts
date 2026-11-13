// 选中的那一个写成什么字:显示栏的九格(kind / node / date / name / diff / in、两个键槽、Esc)与选中卡的
// buys / hits / nodes / family / id、复制行的后半段。三处读同一份,所以这里逐种东西把字钉死。
import { describe, it, expect } from 'vitest'
import type { EventDict, HitDict } from '../src/types'
import { foldBand } from '../src/render/fold'
import { boundEvents, hitOrderOf, usingIndex } from '../src/render/walk'
import { makeWorld, type WorldCtx } from '../src/render/selWorld'
import type { Sel, SelPath } from '../src/render/select'
import { identityText, slotText, snapshotOf, type SnapCtx } from '../src/render/selSnapshot'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// 起点 0 的一族:13、14 两天各有两种阶跃切法(a = 一根 S10,b = 两根 S11),15 只有一根那种;16 那天的 today 没成 hit。
// 起点 30 的一族只有一次 hit、买在 35。
const O = ev('old_plat', 0, 9)
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15), T16 = ev('today', 16, 16)
const T35 = ev('today', 35, 35)
const X = ev('solo', 31, 33)
const kids = (s: EventDict, t: EventDict) =>
  ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id] })
const P13a = ev('plateau', 0, 13, 0, kids(S10, T13)), P13b = ev('plateau', 0, 13, 1, kids(S11, T13))
const P14a = ev('plateau', 0, 14, 0, kids(S10, T14)), P14b = ev('plateau', 0, 14, 1, kids(S11, T14))
const P15a = ev('plateau', 0, 15, 0, kids(S10, T15))
const P35 = ev('plateau', 30, 35, 0, { today: [T35.instance_id], extra: [X.instance_id] })
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})
const HITS = [hit('a13', P13a), hit('b13', P13b), hit('a14', P14a), hit('b14', P14b), hit('a15', P15a), hit('c35', P35)]
const EVENTS = [O, S10, S11, T13, T14, T15, T16, T35, X, P13a, P13b, P14a, P14b, P15a, P35]
const POINT = new Set(['today'])
// 下标 0 = 2024-01-01,逐日排:13 → 01-14,14 → 01-15,15 → 01-16,35 → 02-05
const DATES = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2024, 0, 1 + i)).toISOString().slice(0, 10))

const SAMPLES = [{ id: 's1', day: 13, hitIds: ['b13', 'a13'], pairedHitId: 'b13' }, { id: 's2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }, { id: 's3', day: 17, hitIds: [], pairedHitId: null }]
const BOXES = [{ id: 'x1', day: 13, hitIds: ['a13', 'b13'], pairedHitId: 'a13' }, { id: 'x2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }]
const FEEDBACKS = [
  { id: 'f1', hitIds: ['a13', 'b13', 'a14', 'b14'] },   // 一段日期,收进两个买点日
  { id: 'f2', hitIds: ['a15', 'c35'] },                  // 跨了两族
  { id: 'f3', hitIds: [] },                              // 段里 app 不买
]

function snapCtx(over: Partial<WorldCtx> = {}): SnapCtx {
  const byId = new Map(EVENTS.map(e => [e.instance_id, e]))
  const hitsById = new Map(HITS.map(h => [h.hit_id, h]))
  const wctx: WorldCtx = {
    hits: HITS, hitsById, byId, endNode: 'plateau.today', hitOrder: hitOrderOf(HITS), using: usingIndex(HITS, EVENTS),
    bound: id => boundEvents(hitsById.get(id)!, byId), bandOf: e => e.node_id,
    bandFamilies: band => foldBand(EVENTS.filter(e => e.node_id === band),
      { band, isPoint: POINT.has(band), tierOf: () => 'in_hit', level: 'detected' }),
    feedbacks: FEEDBACKS, samples: SAMPLES, boxes: BOXES, lineDay: null, ...over,
  }
  return {
    dates: DATES, wctx, world: makeWorld(wctx),
    nodeOrder: ['plateau', 'old_plat', 'step', 'today', 'solo'], anchorFields: [],
    featureOfBand: band => (band === 'step' ? '阶跃' : null),
    feedbackOf: id => (id === 'f1' ? { start: '2024-01-14', end: '2024-01-15', nodes: ['step', 'today'], familyStart: null }
      : id === 'f2' ? { start: '2024-01-16', end: '2024-02-05', nodes: [], familyStart: '2024-01-01' }
      : id === 'f3' ? { start: '2024-01-20', end: '2024-01-20', nodes: [], familyStart: null } : null),
    sampleOf: id => (id === 's1' ? { letter: 'a', judgment: 'pos', date: '2024-01-14' }
      : id === 's3' ? { letter: 'c', judgment: 'neg', date: '2024-01-18' } : null),
    boxOf: id => (id === 'x1' ? { feature: '站上新平台', start: '2024-01-01', end: '2024-01-14', node: 'plateau' }
      : id === 'x2' ? { feature: null, start: '2024-01-16', end: '2024-01-16', node: 'plateau' } : null),   // x2 没起名
  }
}

const FAM0: Sel = { kind: 'hit_family', familyKey: 'hits@0' }
const buy = (day: number): Sel => ({ kind: 'buy', day })
const h = (hitId: string, day: number): Sel => ({ kind: 'hit', hitId, day })
const e = (x: EventDict): Sel => ({ kind: 'event', instanceId: x.instance_id })
const node = (band: string): Sel => ({ kind: 'node', band })
const sample = (id: string): Sel => ({ kind: 'sample', sampleId: id })
const box = (id: string): Sel => ({ kind: 'box', boxId: id })
const fbk = (id: string): Sel => ({ kind: 'feedback', id })

const snap = (path: SelPath) => snapshotOf(path, snapCtx())!
/** 九格写成字(不适用的格是 null),顺序同显示栏 */
const bar = (path: SelPath) => {
  const s = snap(path)
  return { kind: s.kind, node: s.node, date: s.date, name: s.name, diff: s.diff, in: s.in,
           day: slotText(s.day), stack: slotText(s.stack), esc: s.esc }
}
/** 卡上由快照给的那几行 */
const card = (path: SelPath) => {
  const s = snap(path)
  return { buys: s.buys, hits: s.hits, nodes: s.nodes, family: s.family, id: s.id }
}

describe('什么都没选', () => {
  it('没有快照', () => {
    expect(snapshotOf([], snapCtx())).toBeNull()
  })
})

describe('hit 的一族', () => {
  it('九格:只有起点日期;← / → 会进到它的买点日;Esc 清空', () => {
    expect(bar([FAM0])).toEqual({
      kind: 'hit_family', node: null, date: '2024-01-01', name: null, diff: null, in: [],
      day: 'into buys ×3', stack: null, esc: 'clear',
    })
  })
  it('卡:牵出的买点日写首尾与个数,hit 写个数;它自己没有组成、编号', () => {
    expect(card([FAM0])).toEqual({
      buys: '2024-01-14…2024-01-16 ×3', hits: { head: '×5', lines: [] }, nodes: null, family: null, id: null,
    })
    expect(snap([FAM0]).copyTail).toBe('hit_family 2024-01-01 buys 2024-01-14…2024-01-16 ×3 hits ×5')
  })
})

describe('买点日', () => {
  it('这天两次:选中的是整天;↑ / ↓ 会进到这天的几次,Esc 退回一族', () => {
    expect(bar([FAM0, buy(13)])).toEqual({
      kind: 'buy', node: null, date: '2024-01-14', name: null, diff: null, in: ['hit_family 2024-01-01'],
      day: 'buys 1/3', stack: 'into hits ×2', esc: 'up: hit_family 2024-01-01',
    })
  })
  it('这天两次的卡:hits 写个数,逐次写它和另一次的区别;family 是这天所在那一族的起点', () => {
    expect(card([FAM0, buy(13)])).toEqual({
      buys: null, hits: { head: '×2', lines: ['step→2024-01-11', 'step→2024-01-12'] },
      nodes: null, family: '2024-01-01', id: null,
    })
    expect(snap([FAM0, buy(13)]).copyTail).toBe('buy 2024-01-14 hits ×2')
  })

  it('这天只有一次 hit:这一天就是那次 hit——kind 写 hit、那一天进 in;↑ / ↓ 不适用;Esc 一下退回一族', () => {
    expect(bar([FAM0, buy(15)])).toEqual({
      kind: 'hit', node: null, date: '2024-01-01→2024-01-16', name: null, diff: null,
      in: ['hit_family 2024-01-01', 'buy 2024-01-16'],
      day: 'buys 3/3', stack: null, esc: 'up: hit_family 2024-01-01',
    })
  })
  it('这天只有一次 hit 的卡与复制行按那次 hit 写', () => {
    expect(card([FAM0, buy(15)])).toEqual({
      buys: '2024-01-16 ×1', hits: null,
      nodes: ['plateau 2024-01-01→2024-01-16', 'old_plat 2024-01-01→2024-01-10', 'step 2024-01-11', 'today 2024-01-16'],
      family: '2024-01-01', id: 'a15',
    })
    expect(snap([FAM0, buy(15)]).copyTail).toBe('hit 2024-01-01→2024-01-16 buys 2024-01-16 ×1 [a15]')
  })
  it('停在只有一次的那一天上,和再进到那一次,写出来一模一样', () => {
    expect(snap([FAM0, buy(15), h('a15', 15)])).toEqual(snap([FAM0, buy(15)]))
  })
})

describe('一次 hit', () => {
  const path = [FAM0, buy(13), h('b13', 13)]
  it('九格:起止、它和同一天另一次的区别、属于哪一族哪一天;← / → 换天,↑ / ↓ 在这天的几次之间换,Esc 退回这一天', () => {
    expect(bar(path)).toEqual({
      kind: 'hit', node: null, date: '2024-01-01→2024-01-14', name: null, diff: 'step→2024-01-12',
      in: ['hit_family 2024-01-01', 'buy 2024-01-14'],
      day: 'buys 1/3', stack: 'hits 2/2', esc: 'up: buy 2024-01-14',
    })
  })
  it('卡:买点日就这一天;组成按拓扑里 node 的先后一行一个;带内部编号', () => {
    expect(card(path)).toEqual({
      buys: '2024-01-14 ×1', hits: null,
      nodes: ['plateau 2024-01-01→2024-01-14', 'old_plat 2024-01-01→2024-01-10', 'step 2024-01-11→2024-01-12', 'today 2024-01-14'],
      family: '2024-01-01', id: 'b13',
    })
    expect(snap(path).copyTail).toBe('hit 2024-01-01→2024-01-14 step→2024-01-12 buys 2024-01-14 ×1 [b13]')
    expect([snap(path).hitId, snap(path).instanceId]).toEqual(['b13', null])
  })
})

describe('event', () => {
  it('牵出好几天:← / → 会进到这些买点日;卡写首尾与个数', () => {
    const path = [node('step'), e(S10)]
    expect(bar(path)).toEqual({
      kind: 'event', node: 'step', date: '2024-01-11', name: null, diff: null, in: ['node step 阶跃'],
      day: 'into buys ×3', stack: null, esc: 'up: node step 阶跃',
    })
    expect(card(path)).toEqual({
      buys: '2024-01-14…2024-01-16 ×3', hits: { head: '×3', lines: [] }, nodes: null, family: null, id: S10.instance_id,
    })
    expect(snap(path).copyTail).toBe(`event step 2024-01-11 buys 2024-01-14…2024-01-16 ×3 hits ×3 [${S10.instance_id}]`)
    expect([snap(path).hitId, snap(path).instanceId]).toEqual([null, S10.instance_id])
  })

  it('只牵出一天:← / → 是沿 band 换到旁边那格,键槽写它是这条 band 上的第几格', () => {
    const path = [node('today'), e(T13)]
    expect(bar(path)).toEqual({
      kind: 'event', node: 'today', date: '2024-01-14', name: null, diff: null, in: ['node today'],
      day: 'events 1/5', stack: null, esc: 'up: node today',
    })
    expect(card(path)).toEqual({
      buys: '2024-01-14 ×1', hits: { head: '×2', lines: [] }, nodes: null, family: null, id: T13.instance_id,
    })
  })

  it('同一格叠着另一个:diff 写它们哪里不一样,↑ / ↓ 在这一格里换', () => {
    const s = bar([node('plateau'), e(P13b)])
    expect([s.date, s.diff, s.day, s.stack]).toEqual(['2024-01-01→2024-01-14', 'step→2024-01-12', 'events 1/4', 'events 2/2'])
  })

  it('没被任何 hit 用到:buys、hits 适用但是空,写 none;复制行不带这两段', () => {
    const path = [node('today'), e(T16)]
    expect(card(path)).toMatchObject({ buys: 'none', hits: { head: 'none', lines: [] } })
    expect(snap(path).copyTail).toBe(`event today 2024-01-17 [${T16.instance_id}]`)
  })
})

describe('node', () => {
  it('只有 node 与它对到的特征名;← / → 会进到 band 上的格;卡上都不适用', () => {
    expect(bar([node('step')])).toEqual({
      kind: 'node', node: 'step', date: null, name: '阶跃', diff: null, in: [],
      day: 'into events ×2', stack: null, esc: 'clear',
    })
    expect(card([node('step')])).toEqual({ buys: null, hits: null, nodes: null, family: null, id: null })
    expect(snap([node('step')]).copyTail).toBe('node step 阶跃')
  })
  it('没有对到特征的 node:name 不适用', () => {
    expect(bar([node('today')]).name).toBeNull()
    expect(snap([node('today')]).copyTail).toBe('node today')
  })
})

describe('反馈', () => {
  it('一段日期的反馈:node 写它点的几个 node,日期写起止;收进两个买点日就能进去', () => {
    expect(bar([fbk('f1')])).toEqual({
      kind: 'feedback', node: 'step,today', date: '2024-01-14→2024-01-15', name: null, diff: null, in: [],
      day: 'into buys ×2', stack: null, esc: 'clear',
    })
    expect(card([fbk('f1')])).toEqual({
      buys: '2024-01-14…2024-01-15 ×2', hits: { head: '×4', lines: [] }, nodes: null, family: null, id: 'f1',
    })
    expect(snap([fbk('f1')]).copyTail)
      .toBe('feedback step,today 2024-01-14→2024-01-15 buys 2024-01-14…2024-01-15 ×2 hits ×4 [f1]')
  })
  it('收进来的 hit 跨了两族:hits 另写跨了几族;一族的反馈带上那一族的起点', () => {
    expect(card([fbk('f2')])).toEqual({
      buys: '2024-01-16…2024-02-05 ×2', hits: { head: '×2 families ×2', lines: [] }, nodes: null,
      family: '2024-01-01', id: 'f2',
    })
  })
  it('段里 app 不买的反馈:buys、hits 写 none;只有一天的反馈日期只写那一天;没点 node 的反馈 node 写 none', () => {
    expect(bar([fbk('f3')])).toMatchObject({ kind: 'feedback', node: 'none', date: '2024-01-20', day: 'feedbacks 3/3' })
    expect(card([fbk('f3')])).toMatchObject({ buys: 'none', hits: { head: 'none', lines: [] } })
    expect(snap([fbk('f3')]).copyTail).toBe('feedback 2024-01-20 [f3]')
  })
  it('没点 node 的反馈:none 不进 in 的身份串、Esc 那一下的去处与复制行', () => {
    const s = bar([fbk('f2'), buy(15)])                 // 15 那天只有一次:按那次 hit 写,那一天也进 in
    expect([s.in, s.esc]).toEqual([['feedback 2024-01-16→2024-02-05', 'buy 2024-01-16'], 'up: feedback 2024-01-16→2024-02-05'])
    expect(bar([fbk('f2')]).node).toBe('none')
    expect(snap([fbk('f2')]).copyTail).toBe('feedback 2024-01-16→2024-02-05 buys 2024-01-16…2024-02-05 ×2 hits ×2 families ×2 [f2]')
  })

  it('从反馈进到它的买点日:in 写这条反馈,Esc 退回它', () => {
    expect(bar([fbk('f1'), buy(14)])).toMatchObject({
      kind: 'buy', date: '2024-01-15', in: ['feedback step,today 2024-01-14→2024-01-15'],
      day: 'buys 2/2', stack: 'into hits ×2', esc: 'up: feedback step,today 2024-01-14→2024-01-15',
    })
  })
})

describe('样本', () => {
  it('九格:样本日、字母与判断;← / → 换样本,↑ / ↓ 会进到样本日在场的几次', () => {
    expect(bar([sample('s1')])).toEqual({
      kind: 'sample', node: null, date: '2024-01-14', name: 'a pos', diff: null, in: [],
      day: 'samples 1/3', stack: 'into hits ×2', esc: 'clear',
    })
  })
  it('卡:hits 逐次写区别(配对的那次排第一);样本自己不牵出买点日', () => {
    expect(card([sample('s1')])).toEqual({
      buys: null, hits: { head: '×2', lines: ['step→2024-01-12', 'step→2024-01-11'] }, nodes: null, family: null, id: 's1',
    })
    expect(snap([sample('s1')]).copyTail).toBe('sample 2024-01-14 a pos hits ×2 [s1]')
  })
  it('样本日没有在场的 hit:hits 写 none,↑ / ↓ 不适用', () => {
    expect(bar([sample('s3')])).toMatchObject({ date: '2024-01-18', name: 'c neg', day: 'samples 3/3', stack: null })
    expect(card([sample('s3')]).hits).toEqual({ head: 'none', lines: [] })
    expect(snap([sample('s3')]).copyTail).toBe('sample 2024-01-18 c neg [s3]')
  })
  it('进到样本日在场的一次 hit:in 写这个样本,← / → 仍是换样本,Esc 退回样本', () => {
    expect(bar([sample('s1'), h('b13', 13)])).toEqual({
      kind: 'hit', node: null, date: '2024-01-01→2024-01-14', name: null, diff: 'step→2024-01-12',
      in: ['sample 2024-01-14 a pos'],
      day: 'samples 1/3', stack: 'hits 1/2', esc: 'up: sample 2024-01-14 a pos',
    })
  })
})

describe('框', () => {
  it('九格:对到的 node、起止、特征名;← / → 换框,↑ / ↓ 会进到框终点在场的几次', () => {
    expect(bar([box('x1')])).toEqual({
      kind: 'box', node: 'plateau', date: '2024-01-01→2024-01-14', name: '站上新平台', diff: null, in: [],
      day: 'boxes 1/2', stack: 'into hits ×2', esc: 'clear',
    })
  })
  it('没起名的框:name 写 none(适用但是空),复制行、in 的身份串里不带它', () => {
    expect(bar([box('x2')])).toMatchObject({ kind: 'box', node: 'plateau', date: '2024-01-16', name: 'none', day: 'boxes 2/2' })
    expect(snap([box('x2')]).copyTail).toBe('box plateau 2024-01-16 hits ×1 [x2]')
    expect(bar([box('x2'), h('a15', 15)]).in).toEqual(['box plateau 2024-01-16'])
  })

  it('卡与复制行', () => {
    expect(card([box('x1')])).toEqual({
      buys: null, hits: { head: '×2', lines: ['step→2024-01-11', 'step→2024-01-12'] }, nodes: null, family: null, id: 'x1',
    })
    expect(snap([box('x1')]).copyTail).toBe('box plateau 2024-01-01→2024-01-14 站上新平台 hits ×2 [x1]')
  })
})

describe('键槽与身份的写法', () => {
  it('键槽:会进去写 into 名词 ×n,在同一层写 名词 k/n,不适用为 null', () => {
    expect(slotText({ mode: 'into', noun: 'buys', k: null, n: 11 })).toBe('into buys ×11')
    expect(slotText({ mode: 'pos', noun: 'buys', k: 1, n: 11 })).toBe('buys 1/11')
    expect(slotText({ mode: 'none', noun: '', k: null, n: 0 })).toBeNull()
  })
  it('身份:种类、node、日期、叫法依次写,不适用的跳过', () => {
    expect(identityText({ kind: 'event', node: 'step', date: '2024-01-11', name: null })).toBe('event step 2024-01-11')
    expect(identityText({ kind: 'sample', node: null, date: '2024-01-14', name: 'a pos' })).toBe('sample 2024-01-14 a pos')
    expect(identityText({ kind: 'node', node: 'step', date: null, name: null })).toBe('node step')
    expect(identityText({ kind: 'feedback', node: 'none', date: '2024-01-20', name: null })).toBe('feedback 2024-01-20')
  })
})
