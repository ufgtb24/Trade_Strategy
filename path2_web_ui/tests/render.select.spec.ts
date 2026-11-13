// 选中与按键走动:两根轴(← / → 跨天、↑ / ↓ 同一天)同一个判断——里面两个以上就进去;否则同一层有别的就换到旁边;
// 两样都没有、里面只有一个就进那一个;都没有不响应。八种东西逐格验。
import { describe, it, expect } from 'vitest'
import type { EventDict, HitDict } from '../src/types'
import { foldBand } from '../src/render/fold'
import { boundEvents, hitOrderOf, usingIndex } from '../src/render/walk'
import { bandCells, lineDayOf, makeWorld, type WorldCtx } from '../src/render/selWorld'
import { mergedHit, slot, step, up, type Axis, type Sel, type SelPath } from '../src/render/select'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// 起点 0 的一族:13、14 两天各有两种阶跃切法(a = 一根 S10,b = 两根 S11),15 只有一根那种;16 那天的 today 没成 hit。
// 起点 30 的一族只有一次 hit、买在 35。
const O = ev('old_plat', 0, 9)
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15), T16 = ev('today', 16, 16)
const T35 = ev('today', 35, 35)
const X = ev('solo', 31, 33)                       // 这条 band 上只有它,只被 35 那次用到
const kids = (s: EventDict, t: EventDict, extra: EventDict[] = []) =>
  ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id], extra: extra.map(e => e.instance_id) })
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

function ctxOf(over: Partial<WorldCtx> = {}): WorldCtx {
  const byId = new Map(EVENTS.map(e => [e.instance_id, e]))
  const hitsById = new Map(HITS.map(h => [h.hit_id, h]))
  return {
    hits: HITS, hitsById, byId, endNode: 'plateau.today', hitOrder: hitOrderOf(HITS), using: usingIndex(HITS, EVENTS),
    bound: id => boundEvents(hitsById.get(id)!, byId), bandOf: e => e.node_id,
    bandFamilies: band => foldBand(EVENTS.filter(e => e.node_id === band),
      { band, isPoint: POINT.has(band), tierOf: () => 'in_hit', level: 'detected' }),
    feedbacks: [], samples: [], boxes: [], lineDay: null, ...over,
  }
}

const FAM0: Sel = { kind: 'hit_family', familyKey: 'hits@0' }
const FAM30: Sel = { kind: 'hit_family', familyKey: 'hits@30' }
const buy = (day: number): Sel => ({ kind: 'buy', day })
const h = (hitId: string, day: number): Sel => ({ kind: 'hit', hitId, day })
const e = (x: EventDict): Sel => ({ kind: 'event', instanceId: x.instance_id })
const node = (band: string): Sel => ({ kind: 'node', band })

/** 键槽写成字:`into buys ×3`、`buys 1/3`、`—` */
function slotText(path: SelPath, axis: Axis, ctx: WorldCtx): string {
  const s = slot(path, axis, makeWorld(ctx))
  return s.mode === 'into' ? `into ${s.noun} ×${s.n}` : s.mode === 'pos' ? `${s.noun} ${s.k}/${s.n}` : '—'
}
const go = (path: SelPath, axis: Axis, dir: -1 | 1, ctx: WorldCtx) => step(path, axis, dir, makeWorld(ctx)).path

describe('键槽:八种东西 × 两根轴', () => {
  const SAMPLES = [{ id: 's1', day: 13, hitIds: ['b13', 'a13'], pairedHitId: 'b13' }, { id: 's2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }, { id: 's3', day: 17, hitIds: [], pairedHitId: null }]
  const FEEDBACKS = [{ id: 'f1', hitIds: ['a13', 'b13', 'a14', 'b14'] }, { id: 'f2', hitIds: ['c35'] }]
  const ctx = ctxOf({ samples: SAMPLES, boxes: SAMPLES.map(s => ({ ...s, id: s.id.replace('s', 'x') })), feedbacks: FEEDBACKS })
  const rows: [string, SelPath, string, string][] = [
    ['一族,买点日 3 个', [FAM0], 'into buys ×3', '—'],
    ['一族,只有 1 个买点日、图上另有一族', [FAM30], 'hit_families 2/2', '—'],
    ['反馈,收进 2 个买点日', [{ kind: 'feedback', id: 'f1' }], 'into buys ×2', '—'],
    ['反馈,只收进 1 个买点日', [{ kind: 'feedback', id: 'f2' }], 'feedbacks 2/2', '—'],
    ['event,用到它的买点日 3 个', [node('step'), e(S10)], 'into buys ×3', '—'],
    ['event,只牵出 1 个买点日', [node('today'), e(T13)], 'events 1/5', '—'],
    ['event,没被 hit 用到', [node('today'), e(T16)], 'events 4/5', '—'],
    ['event,band 上只有它且牵出 1 天', [node('solo'), e(X)], 'into buys ×1', '—'],
    ['event,同一格叠着另一个', [node('plateau'), e(P13a)], 'events 1/4', 'events 1/2'],
    ['node,band 上 2 格', [node('step')], 'into events ×2', '—'],
    ['node,band 上 1 格', [node('solo')], 'into events ×1', '—'],
    ['node,band 上没有东西', [node('nothing')], '—', '—'],
    ['买点日,这天 2 次', [FAM0, buy(13)], 'buys 1/3', 'into hits ×2'],
    ['买点日,这天只有 1 次(合并)', [FAM0, buy(15)], 'buys 3/3', '—'],
    ['一次 hit', [FAM0, buy(13), h('b13', 13)], 'buys 1/3', 'hits 2/2'],
    ['样本,在场 2 次', [{ kind: 'sample', sampleId: 's1' }], 'samples 1/3', 'into hits ×2'],
    ['样本,在场 1 次', [{ kind: 'sample', sampleId: 's2' }], 'samples 2/3', 'into hits ×1'],
    ['样本,没有在场的', [{ kind: 'sample', sampleId: 's3' }], 'samples 3/3', '—'],
    ['框,在场 2 次', [{ kind: 'box', boxId: 'x1' }], 'boxes 1/3', 'into hits ×2'],
    ['框,在场 1 次', [{ kind: 'box', boxId: 'x2' }], 'boxes 2/3', 'into hits ×1'],
    ['样本里的一次 hit', [{ kind: 'sample', sampleId: 's1' }, h('b13', 13)], 'samples 1/3', 'hits 1/2'],
    ['挂在样本下面的 event', [{ kind: 'sample', sampleId: 's1' }, e(T16)], '—', '—'],
    ['什么都没选', [], '—', '—'],
  ]
  it.each(rows)('%s', (_name, path, day, stack) => {
    expect([slotText(path, 'day', ctx), slotText(path, 'stack', ctx)]).toEqual([day, stack])
  })
})

describe('按一下去哪', () => {
  it('一族:← / → 进到买点日,选中的是整天;在里面换天仍是整天,到头停', () => {
    const ctx = ctxOf()
    let p = go([FAM0], 'day', 1, ctx)
    expect(p).toEqual([FAM0, buy(13)])
    p = go(p, 'day', 1, ctx); p = go(p, 'day', 1, ctx)
    expect(p).toEqual([FAM0, buy(15)])
    expect(go(p, 'day', 1, ctx)).toEqual([FAM0, buy(15)])
  })

  it('进去落哪:竖线那天本身有就落它;否则按键方向最近的;那个方向没有取另一边最近的;没有竖线落第一个 / 最后一个', () => {
    expect(go([FAM0], 'day', -1, ctxOf({ lineDay: 14 }))).toEqual([FAM0, buy(14)])
    expect(go([FAM0], 'day', 1, ctxOf({ lineDay: 13.5 as number }))).toEqual([FAM0, buy(14)])
    expect(go([FAM0], 'day', 1, ctxOf({ lineDay: 20 }))).toEqual([FAM0, buy(15)])
    expect(go([FAM0], 'day', -1, ctxOf({ lineDay: 2 }))).toEqual([FAM0, buy(13)])
    expect(go([FAM0], 'day', -1, ctxOf())).toEqual([FAM0, buy(15)])
  })

  it('只有 1 个买点日的一族:← / → 换到旁边一族,不进那一天', () => {
    expect(go([FAM30], 'day', -1, ctxOf())).toEqual([FAM0])
    expect(go([FAM30], 'day', 1, ctxOf())).toEqual([FAM30])
  })

  it('买点日 ↓ 进到第 1 次、↑ 进到最后一次;在几次之间换,竖线那天不变', () => {
    const ctx = ctxOf()
    expect(go([FAM0, buy(13)], 'stack', 1, ctx)).toEqual([FAM0, buy(13), h('a13', 13)])
    expect(go([FAM0, buy(13)], 'stack', -1, ctx)).toEqual([FAM0, buy(13), h('b13', 13)])
    expect(go([FAM0, buy(13), h('a13', 13)], 'stack', 1, ctx)).toEqual([FAM0, buy(13), h('b13', 13)])
    expect(go([FAM0, buy(13), h('b13', 13)], 'stack', 1, ctx)).toEqual([FAM0, buy(13), h('b13', 13)])
  })

  it('一次 hit 换天:落旁边那天同一种切法的那次;那天只有一次也落到那一次,Esc 一下退回一族', () => {
    const ctx = ctxOf()
    const w = makeWorld(ctx)
    let p = go([FAM0, buy(13), h('b13', 13)], 'day', 1, ctx)
    expect(p).toEqual([FAM0, buy(14), h('b14', 14)])
    p = go(p, 'day', 1, ctx)
    expect(p).toEqual([FAM0, buy(15), h('a15', 15)])
    expect(slotText(p, 'stack', ctx)).toBe('—')
    expect(up(p, w)).toEqual([FAM0])                      // 15 那天只有这一次:那一天和它是同一样东西
    expect(up([FAM0, buy(14), h('b14', 14)], w)).toEqual([FAM0, buy(14)])
  })

  it('只有一次 hit 的买点日:显示、复制按那次 hit;↑ / ↓ 不响应', () => {
    const w = makeWorld(ctxOf())
    expect(mergedHit([FAM0, buy(15)], w)?.sel).toEqual(h('a15', 15))
    expect(mergedHit([FAM0, buy(13)], w)).toBeNull()
    expect(step([FAM0, buy(15)], 'stack', 1, w)).toMatchObject({ action: 'none', moved: false })
  })

  it('event 牵出两个以上买点日:← / → 进去;那天的几次里用到它的排第一;Esc 一层层退回', () => {
    const ctx = ctxOf()
    const w = makeWorld(ctx)
    let p = go([node('step'), e(S11)], 'day', 1, ctx)
    expect(p).toEqual([node('step'), e(S11), buy(13)])
    p = go(p, 'stack', 1, ctx)
    expect(p).toEqual([node('step'), e(S11), buy(13), h('b13', 13)])      // b13 用到 S11,排在 a13 前面
    expect(slotText(p, 'stack', ctx)).toBe('hits 1/2')
    p = go(p, 'day', 1, ctx)
    expect(p).toEqual([node('step'), e(S11), buy(14), h('b14', 14)])
    expect(up(up(up(p, w), w), w)).toEqual([node('step')])
  })

  it('event 只牵出一个买点日或没被用到:← / → 沿 band 换到旁边那格,不进那一天', () => {
    const ctx = ctxOf()
    let p = go([node('today'), e(T13)], 'day', 1, ctx)
    expect(p).toEqual([node('today'), e(T14)])
    p = go(go(p, 'day', 1, ctx), 'day', 1, ctx)
    expect(p).toEqual([node('today'), e(T16)])            // 没成 hit 的那格照样走得到
    expect(go(p, 'day', -1, ctx)).toEqual([node('today'), e(T15)])
  })

  it('沿 band 换时每格落同一个起点的那个;同一格叠着的 ↑ / ↓ 换', () => {
    const ctx = ctxOf()
    expect(go([node('plateau'), e(P13b)], 'day', 1, ctx)).toEqual([node('plateau'), e(P14a)])   // 14 那格同起点的第一个
    expect(go([node('plateau'), e(P13a)], 'stack', 1, ctx)).toEqual([node('plateau'), e(P13b)])
    expect(go([node('plateau'), e(P15a)], 'day', 1, ctx)).toEqual([node('plateau'), e(P35)])     // 这一串到头,换到另一个起点
  })

  it('band 上只有它一个、只牵出一天:← / → 进那一天', () => {
    expect(go([node('solo'), e(X)], 'day', 1, ctxOf())).toEqual([node('solo'), e(X), buy(35)])
  })

  it('node:← / → 进到 band 上离竖线最近的那格', () => {
    expect(go([node('step')], 'day', 1, ctxOf({ lineDay: 11 }))).toEqual([node('step'), e(S11)])
    expect(go([node('today')], 'day', -1, ctxOf({ lineDay: 15 }))).toEqual([node('today'), e(T15)])
  })

  it('样本:← / → 换样本;↓ 进到在场的第 1 次(配对的排第一);停在 hit 上换样本落那边最像的,那边没有就落样本本身', () => {
    const samples = [{ id: 's1', day: 13, hitIds: ['b13', 'a13'], pairedHitId: 'b13' }, { id: 's2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }, { id: 's3', day: 17, hitIds: [], pairedHitId: null }]
    const ctx = ctxOf({ samples })
    const s = (id: string): Sel => ({ kind: 'sample', sampleId: id })
    expect(go([s('s1')], 'day', 1, ctx)).toEqual([s('s2')])
    let p = go([s('s1')], 'stack', 1, ctx)
    expect(p).toEqual([s('s1'), h('b13', 13)])
    expect(go([s('s2')], 'stack', 1, ctx)).toEqual([s('s2'), h('a15', 15)])
    p = go(p, 'day', 1, ctx)
    expect(p).toEqual([s('s2'), h('a15', 15)])
    expect(go(p, 'day', 1, ctx)).toEqual([s('s3')])
    expect(step([s('s3')], 'stack', 1, makeWorld(ctx))).toMatchObject({ action: 'none', moved: false })
  })

  it('框:← / → 换到旁边的框;↓ 进到框终点在场的那次', () => {
    const boxes = [{ id: 'x1', day: 13, hitIds: ['a13', 'b13'], pairedHitId: 'a13' }, { id: 'x2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }]
    const ctx = ctxOf({ boxes })
    const b = (id: string): Sel => ({ kind: 'box', boxId: id })
    expect(go([b('x1')], 'day', 1, ctx)).toEqual([b('x2')])
    expect(go([b('x1')], 'stack', 1, ctx)).toEqual([b('x1'), h('a13', 13)])
  })

  it('反馈:收进两个以上买点日就进去;只收进一个换到旁边一条反馈', () => {
    const feedbacks = [{ id: 'f1', hitIds: ['a13', 'b13', 'a14'] }, { id: 'f2', hitIds: ['c35'] }]
    const ctx = ctxOf({ feedbacks })
    const f = (id: string): Sel => ({ kind: 'feedback', id })
    expect(go([f('f1')], 'day', 1, ctx)).toEqual([f('f1'), buy(13)])
    expect(go([f('f2')], 'day', -1, ctx)).toEqual([f('f1')])
    // 从反馈进来的买点日:那个 ▼ 上的几次都在,收进来的排前面
    expect(makeWorld(ctx).members([f('f1'), buy(14)]).map(i => (i.sel as any).hitId)).toEqual(['a14', 'b14'])
  })

  it('什么都没选:两组键都不响应', () => {
    const w = makeWorld(ctxOf())
    expect(step([], 'day', 1, w)).toMatchObject({ action: 'none', moved: false })
    expect(step([], 'stack', 1, w)).toMatchObject({ action: 'none', moved: false })
    expect(up([], w)).toEqual([])
  })
})

describe('band 上的格、竖线落哪', () => {
  it('一天一格:几族在同一天结束的并在一格里', () => {
    const cells = bandCells(ctxOf().bandFamilies('plateau'))
    expect(cells.map(c => [c.day, c.members.length])).toEqual([[13, 2], [14, 2], [15, 1], [35, 1]])
  })

  it('竖线:买点日、hit 落那一天;event 落终点;样本 / 框落样本日 / 框终点;族、反馈、node 不带日子', () => {
    const ctx = ctxOf({ samples: [{ id: 's1', day: 13, hitIds: [], pairedHitId: null }], boxes: [{ id: 'x1', day: 9, hitIds: [], pairedHitId: null }] })
    const d = (s: Sel) => lineDayOf(s, ctx)
    expect([d(buy(14)), d(h('a14', 14)), d(e(S11)), d({ kind: 'sample', sampleId: 's1' }), d({ kind: 'box', boxId: 'x1' })])
      .toEqual([14, 14, 11, 13, 9])
    expect([d(FAM0), d({ kind: 'feedback', id: 'f1' }), d(node('step'))]).toEqual([null, null, null])
  })
})
