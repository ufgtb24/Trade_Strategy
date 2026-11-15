// 选中后图上怎么画(render/selHighlight.ts):粗框框谁、外层底线画在谁下面、哪些照常、哪一边画淡。
// 「同一天叠着几次只算 ↓ 第一个」与走动(render/selWorld.ts 的 members)同源,这里逐种选中把结果钉死。
import { describe, it, expect } from 'vitest'
import type { EventDict, HitDict } from '../src/types'
import { foldBand } from '../src/render/fold'
import { boundEvents, hitOrderOf, usingIndex } from '../src/render/walk'
import { makeWorld, type AnchorRow, type WorldCtx } from '../src/render/selWorld'
import type { Sel, SelPath } from '../src/render/select'
import {
  DIM_APP_OPACITY, DIM_USER_OPACITY, NO_HIGHLIGHT, POINT_ENLARGE_Y, dimOpacity, eventMarkDim, highlightOf, hitMarkDim,
  isFocus, MARK_ENLARGE_Y, markScaleY, userMarkDim, hitMarkGrows, isRelatedMark, relatedEdgeRect,
  RELATED_EDGE_DARKEN, RELATED_EDGE_MIN_W, RELATED_EDGE_W, type Highlight,
} from '../src/render/selHighlight'
import { darken } from '../src/render/colors'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// 起点 0 的一族:13、14 两天各有两种阶跃切法(a = 一根 S10,b = 两根 S11),15 只有一根那种;16 那天的 today 没成 hit。
// 起点 30 的一族只有一次 hit、买在 35。S10 被 13、14、15 三个买点日的 hit 用到;T13 被 13 那天的两次用到。
const O = ev('old_plat', 0, 9)
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15), T16 = ev('today', 16, 16)
const T35 = ev('today', 35, 35)
const X = ev('solo', 31, 33)
const kids = (s: EventDict, t: EventDict) => ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id] })
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

// s1:样本日 13,在场两次、配对的是 b13(排第一);s4:样本日 14,配对的 event 没进 hit(pairedHitId 为空),在场的仍有两次;
// s3:样本日没有在场 hit。框 x1 终点 13,配对 a13。
const SAMPLES: AnchorRow[] = [
  { id: 's1', day: 13, hitIds: ['b13', 'a13'], pairedHitId: 'b13' },
  { id: 's4', day: 14, hitIds: ['a14', 'b14'], pairedHitId: null },
  { id: 's3', day: 17, hitIds: [], pairedHitId: null },
]
const BOXES: AnchorRow[] = [{ id: 'x1', day: 13, hitIds: ['a13', 'b13'], pairedHitId: 'a13' }]
const FEEDBACKS = [{ id: 'f1', hitIds: ['a13', 'b13', 'a14', 'b14'] }, { id: 'f3', hitIds: [] }]
const MEMBERS: Record<string, string[]> = { s1: ['bx1', 'bx2'], s4: [], s3: [] }

function ctx(over: Partial<WorldCtx> = {}) {
  const byId = new Map(EVENTS.map(e => [e.instance_id, e]))
  const hitsById = new Map(HITS.map(h => [h.hit_id, h]))
  const wctx: WorldCtx = {
    hits: HITS, hitsById, byId, endNode: 'plateau.today', hitOrder: hitOrderOf(HITS), using: usingIndex(HITS, EVENTS),
    bound: id => boundEvents(hitsById.get(id)!, byId), bandOf: e => e.node_id,
    bandFamilies: band => foldBand(EVENTS.filter(e => e.node_id === band),
      { band, isPoint: POINT.has(band), tierOf: () => 'in_hit', level: 'detected' }),
    feedbacks: FEEDBACKS, samples: SAMPLES, boxes: BOXES, lineDay: null, ...over,
  }
  return { world: makeWorld(wctx), wctx, memberBoxes: (id: string) => MEMBERS[id] ?? [] }
}
const hl = (path: SelPath, over: Partial<WorldCtx> = {}): Highlight => highlightOf(path, ctx(over))

const FAM0: Sel = { kind: 'hit_family', familyKey: 'hits@0' }
const buy = (day: number): Sel => ({ kind: 'buy', day })
const h = (hitId: string, day: number): Sel => ({ kind: 'hit', hitId, day })
const e = (x: EventDict): Sel => ({ kind: 'event', instanceId: x.instance_id })
const sample = (id: string): Sel => ({ kind: 'sample', sampleId: id })
const box = (id: string): Sel => ({ kind: 'box', boxId: id })
const fbk = (id: string): Sel => ({ kind: 'feedback', id })
const id = (x: EventDict) => x.instance_id
/** band 上一格的成员:plateau 13 那一格并着两种切法 */
const CELL_P13 = [id(P13a), id(P13b)]
/** hits 行 13 那一格(两次共用一格、一个 ▼) */
const hitsCell13 = (x: Highlight) => hitMarkDim(x, 'hits@0', ['a13', 'b13'], [13])

describe('selHighlight · 什么都没选中', () => {
  it('什么都不淡,没有粗框、底线', () => {
    const x = hl([])
    expect(x).toBe(NO_HIGHLIGHT)
    expect([x.dimApp, x.dimUser, x.focus, x.focusSlot]).toEqual([false, false, null, null])
    expect(eventMarkDim(x, [id(S11)])).toBe(false)
    expect(hitMarkDim(x, 'hits@30', ['c35'], [35])).toBe(false)
    expect(userMarkDim(x, 'box', 'bx9')).toBe(false)
  })
})

describe('selHighlight · 选中 event', () => {
  it('被同一天两次 hit 用到:只亮 ↓ 第一个的组成;hits 那格照常;另一次的组成画淡', () => {
    const x = hl([e(T13)])
    expect([...x.ledHits]).toEqual(['a13'])
    expect(x.dimApp).toBe(true)
    expect(hitsCell13(x)).toBe(false)                 // 同一天共用的一格:有一次照常就照常
    expect(eventMarkDim(x, [id(S10)])).toBe(false)    // a13 的阶跃
    expect(eventMarkDim(x, [id(S11)])).toBe(true)     // b13 的阶跃:另一次的组成
    expect(eventMarkDim(x, CELL_P13)).toBe(false)     // 两种切法并在一格,有一个照常就照常
    expect(hitMarkDim(x, 'hits@30', ['c35'], [35])).toBe(true)
    expect(x.dimUser).toBe(false)                     // 用户那边没有有关的:原样不动
    expect(userMarkDim(x, 'box', 'bx1')).toBe(false)
  })

  it('路径就它一节:没有外层、哪儿都不画底线;同一层(这条 band 上别的格)不另外照常,无关就画淡', () => {
    const x = hl([e(T13)])
    expect(isFocus(x, 'event', id(T13))).toBe(true)
    expect([x.under.events.size, x.under.families.size, x.under.slots.length]).toEqual([0, 0, 0])
    expect(eventMarkDim(x, [id(T14)])).toBe(true)     // 同一层:和 a13 无关,画淡
    expect(eventMarkDim(x, [id(T16)])).toBe(true)
    expect(eventMarkDim(x, [id(P14b)])).toBe(true)
    expect(hitMarkDim(x, 'hits@0', ['a14', 'b14'], [14])).toBe(true)
  })

  it('外层的 event 照常;同一层是有关的(牵出的 hit 用到)才照常', () => {
    const x = hl([e(S10), buy(13)])
    expect([...x.under.events]).toEqual([id(S10)])
    expect(eventMarkDim(x, [id(S10)])).toBe(false)    // 外层,也是 a13 的组成
    expect(eventMarkDim(x, [id(S11)])).toBe(true)     // 同一层(这条 band 上另一格),b13 没算上:画淡
  })

  it('被不同日子的几次 hit 用到的子段:每个买点日各一次', () => {
    const x = hl([e(S10)])
    expect([...x.ledHits].sort()).toEqual(['a13', 'a14', 'a15'])
    for (const [ids, day] of [[['a13', 'b13'], 13], [['a14', 'b14'], 14], [['a15'], 15]] as const) {
      expect(hitMarkDim(x, 'hits@0', ids, [day])).toBe(false)
    }
    expect(eventMarkDim(x, [id(P14b)])).toBe(true)    // 14 那天另一种切法
    expect(eventMarkDim(x, [id(T15)])).toBe(false)
    expect(hitMarkDim(x, 'hits@30', ['c35'], [35])).toBe(true)
  })

  it('没进任何 hit、也没有子事件的 event:app 那边不淡', () => {
    const x = hl([e(T16)])
    expect([x.ledHits.size, x.dimApp]).toEqual([0, false])
    expect(eventMarkDim(x, [id(S11)])).toBe(false)
    expect(hitMarkDim(x, 'hits@30', ['c35'], [35])).toBe(false)
  })

  it('选中的 event 在当前档位下画不出来:它那条 band 记作 hidden', () => {
    const x = hl([e(X)], {
      bandFamilies: band => (band === 'solo' ? [] : foldBand(EVENTS.filter(v => v.node_id === band),
        { band, isPoint: POINT.has(band), tierOf: () => 'in_hit', level: 'detected' })),
    })
    expect(x.hiddenBand).toBe('solo')
    expect(hl([e(T13)]).hiddenBand).toBeNull()
  })
})

describe('selHighlight · 选中买点日 / 一次 hit / 一族', () => {
  it('买点日(这天叠两次):▼ 那一格位有粗框;只亮 ↓ 第一个的组成;侧栏这两行黑粗边、只第一次挂蓝条', () => {
    const x = hl([FAM0, buy(13)])
    expect(x.focusSlot).toEqual({ familyKey: 'hits@0', day: 13 })
    expect([...x.ledHits]).toEqual(['a13'])
    expect([...x.frameHits].sort()).toEqual(['a13', 'b13'])
    expect(eventMarkDim(x, [id(S10)])).toBe(false)
    expect(eventMarkDim(x, [id(S11)])).toBe(true)
    expect([...x.under.families]).toEqual(['hits@0'])  // 外层一族:那一行底线
    // 同一层(图上别的族、这一族别的买点日)不另外照常:和它无关,画淡
    expect(hitMarkDim(x, 'hits@30', ['c35'], [35])).toBe(true)
    expect(hitMarkDim(x, 'hits@0', ['a15'], [15])).toBe(true)
    expect(hitMarkDim(x, 'hits@0', ['a13', 'b13'], [13])).toBe(false)   // 选中的这一天
  })

  it('一次 hit:只它的组成照常;外层一族有底线,买点日的底线落在同一格位', () => {
    const x = hl([FAM0, buy(13), h('b13', 13)])
    expect(isFocus(x, 'hit', 'b13')).toBe(true)
    expect(x.focusSlot).toEqual({ familyKey: 'hits@0', day: 13 })
    expect([...x.ledHits]).toEqual(['b13'])
    expect([...x.frameHits]).toEqual(['b13'])
    expect(eventMarkDim(x, [id(S11)])).toBe(false)
    expect(eventMarkDim(x, [id(S10)])).toBe(true)
    expect([...x.under.families]).toEqual(['hits@0'])
    expect(x.under.slots).toEqual([{ familyKey: 'hits@0', day: 13 }])
  })

  it('只有一次 hit 的买点日按那次 hit 画:粗框与外层买点日的底线同一格位', () => {
    const x = hl([FAM0, buy(15)])
    expect(isFocus(x, 'hit', 'a15')).toBe(true)
    expect(x.focusSlot).toEqual({ familyKey: 'hits@0', day: 15 })
    expect(x.under.slots).toEqual([{ familyKey: 'hits@0', day: 15 }])
  })

  it('一族:粗框框整行;每个买点日只算 ↓ 第一个;侧栏全族黑粗边', () => {
    const x = hl([FAM0])
    expect(isFocus(x, 'hit_family', 'hits@0')).toBe(true)
    expect([...x.ledHits].sort()).toEqual(['a13', 'a14', 'a15'])
    expect([...x.frameHits].sort()).toEqual(['a13', 'a14', 'a15', 'b13', 'b14'])
    expect(eventMarkDim(x, [id(S11)])).toBe(true)
    expect(x.under.families.size).toBe(0)
  })
})

describe('selHighlight · 选中样本 / 框 / 反馈', () => {
  it('样本:配对那次照常、同一天另一次的组成淡;用户那边非成员框淡', () => {
    const x = hl([sample('s1')])
    expect([...x.ledHits]).toEqual(['b13'])
    expect(eventMarkDim(x, [id(S11)])).toBe(false)
    expect(eventMarkDim(x, [id(S10)])).toBe(true)
    expect(hitsCell13(x)).toBe(false)
    expect(x.dimUser).toBe(true)
    expect(userMarkDim(x, 'box', 'bx1')).toBe(false)
    expect(userMarkDim(x, 'box', 'bx9')).toBe(true)
    expect(userMarkDim(x, 'sample', 's4')).toBe(true)      // 别的样本是同一层,不另外照常:画淡
    expect(userMarkDim(x, 'sample', 's1')).toBe(false)     // 选中的样本
    expect(userMarkDim(x, 'feedback', 'f1')).toBe(true)
  })

  it('样本的配对 event 没进 hit、那天另有在场 hit:亮在场的第一次', () => {
    const x = hl([sample('s4')])
    expect([...x.ledHits]).toEqual(['a14'])
    expect(eventMarkDim(x, [id(P14a)])).toBe(false)
    expect(eventMarkDim(x, [id(P14b)])).toBe(true)
    expect(x.dimUser).toBe(false)                          // 没有成员框:用户那边原样
  })

  it('样本日没有在场 hit、也没有成员框:两边都不淡', () => {
    const x = hl([sample('s3')])
    expect([x.dimApp, x.dimUser]).toEqual([false, false])
  })

  it('样本 › 一次 hit:样本是外层(跨度下底线),用户那边没有有关的、原样不动', () => {
    const x = hl([sample('s1'), h('a13', 13)])
    expect([...x.under.samples]).toEqual(['s1'])
    expect(x.dimUser).toBe(false)
    expect(eventMarkDim(x, [id(S10)])).toBe(false)
    expect(eventMarkDim(x, [id(S11)])).toBe(true)
  })

  it('框:配对那次照常;框没有组成,用户那边原样', () => {
    const x = hl([box('x1')])
    expect([...x.ledHits]).toEqual(['a13'])
    expect(x.dimUser).toBe(false)
    expect(isFocus(x, 'box', 'x1')).toBe(true)
  })

  it('反馈:收进来的每个买点日一次,收进它的排前面;没收进 hit 的反馈不淡', () => {
    const x = hl([fbk('f1')])
    expect([...x.ledHits].sort()).toEqual(['a13', 'a14'])
    expect(eventMarkDim(x, [id(S11)])).toBe(true)
    expect(userMarkDim(x, 'feedback', 'f1')).toBe(false)
    const y = hl([fbk('f3')])
    expect([y.dimApp, y.dimUser]).toEqual([false, false])
  })

  it('反馈 › 买点日:反馈是外层(记号下底线),不淡', () => {
    const x = hl([fbk('f1'), buy(14)])
    expect([...x.under.feedbacks]).toEqual(['f1'])
    expect(x.focusSlot).toEqual({ familyKey: 'hits@0', day: 14 })
    expect([...x.ledHits]).toEqual(['a14'])
  })
})

// 一次 hit 买好几天、hit 终点不是买点日的 app:买点 node 是 tb,它跨的每一天都是买入日;hits 行的格在各次 hit 的终点。
// 三次 hit 同起点 0、都用到 base;族内先后 g(终点 8)、k(终点 9)、hh(终点 10)。
// 买入日:5、6 只有 hh;7 有 g、hh;8 有 g、k、hh;9、10 只有 hh。k 只买在 8,那天排在 g 后面,哪天都没算上。
describe('selHighlight · 一次 hit 买好几天、终点不是买点日', () => {
  const B = ev('base', 0, 4)
  const TBH = ev('tb', 5, 10), TBG = ev('tb', 7, 8), TBK = ev('tb', 8, 8)
  const mk = (hid: string, end: number, tb: EventDict): HitDict => ({
    hit_id: hid, start_idx: 0, end_idx: end, node_index: { base: B.instance_id, tb: tb.instance_id },
    children: [B.instance_id, tb.instance_id],
  })
  const MH = [mk('hh', 10, TBH), mk('g', 8, TBG), mk('k', 9, TBK)]
  const ME = [B, TBH, TBG, TBK]
  const mctx = () => {
    const byId = new Map(ME.map(x => [x.instance_id, x]))
    const hitsById = new Map(MH.map(x => [x.hit_id, x]))
    const wctx: WorldCtx = {
      hits: MH, hitsById, byId, endNode: 'tb', hitOrder: hitOrderOf(MH), using: usingIndex(MH, ME),
      bound: hid => boundEvents(hitsById.get(hid)!, byId), bandOf: x => x.node_id,
      bandFamilies: band => foldBand(ME.filter(x => x.node_id === band),
        { band, isPoint: false, tierOf: () => 'in_hit', level: 'detected' }),
      feedbacks: [], samples: [], boxes: [], lineDay: null,
    }
    return { world: makeWorld(wctx), wctx }
  }

  it('同一次 hit 在某天算上、某天没算上:取并集,它和它的组成照常', () => {
    const x = highlightOf([e(B)], mctx())
    // 5、6、9、10 算 hh,7、8 算 g(族内先后在前)
    expect([...x.ledHits].sort()).toEqual(['g', 'hh'])
    expect(eventMarkDim(x, [id(TBH)])).toBe(false)     // hh 在 7、8 两天没算上,组成照样照常
    expect(eventMarkDim(x, [id(TBG)])).toBe(false)
    expect(eventMarkDim(x, [id(TBK)])).toBe(true)      // k 哪天都没算上
  })

  it('同一天叠着的几次各有自己的终点格:没算上的那次终点格画淡,这天的 ▼ 共用、照常', () => {
    const x = highlightOf([e(B)], mctx())
    expect(hitMarkDim(x, 'hits@0', ['g', 'k', 'hh'], [8])).toBe(false)   // 8 那天的 ▼
    expect(hitMarkDim(x, 'hits@0', ['g'], [8])).toBe(false)              // g 的终点格(8)
    expect(hitMarkDim(x, 'hits@0', ['k'], [9])).toBe(true)               // k 的终点格(9):没算上,画淡
    expect(hitMarkDim(x, 'hits@0', ['hh'], [10])).toBe(false)            // hh 的终点格(10)
  })
})

describe('selHighlight · 有关的竖直放大', () => {
  const pt = (x: Highlight, ids: string[], level = 'in_hit') => markScaleY(x, ids, 'point', level)
  it('选中的、它的组成、牵出的 hit 的组成放大;同一层、没算上的那次、无关的不放大', () => {
    const x = hl([e(T13)])
    expect(pt(x, [id(T13)])).toBe(POINT_ENLARGE_Y)              // 选中的那一个
    const y = hl([FAM0, buy(13)])
    expect(pt(y, [id(T13)])).toBe(POINT_ENLARGE_Y)              // 牵出的 a13 的组成
    expect(markScaleY(y, [id(S10)], 'mark', 'in_hit')).toBe(MARK_ENLARGE_Y)   // 格:a13 的阶跃
    expect(markScaleY(y, [id(S11)], 'mark', 'in_hit')).toBe(1)  // 没算上的 b13 的阶跃
    expect(pt(y, [id(T14)])).toBe(1)                            // 同一层(别的买点日):无关,不放大
    expect(pt(y, [id(T35)])).toBe(1)                            // 无关的
    const z = hl([e(S10)])
    expect(pt(z, [id(T14)])).toBe(POINT_ENLARGE_Y)              // 用到 S10 的 a14 的组成
    expect(pt(z, [id(T16), id(T15)])).toBe(POINT_ENLARGE_Y)     // 并着的有一个有关就放大
    expect(pt(hl([]), [id(T13)])).toBe(1)                       // 什么都没选
  })
  it('两个灰档里不放大(格高、三角大小表示档位)', () => {
    const y = hl([FAM0, buy(13)])
    expect(pt(y, [id(T13)], 'qualified')).toBe(1)
    expect(markScaleY(y, [id(S10)], 'mark', 'detected')).toBe(1)
  })
})

describe('selHighlight · hits 行牵出的 hit 变高、有关的方块加细边', () => {
  it('hits 行:并着牵出的 hit(含选中的那一次)的格、▼、个数变高;别的不变;什么都没选不变', () => {
    const y = hl([FAM0, buy(13)])
    expect(hitMarkGrows(y, ['a13', 'b13'])).toBe(true)          // 这一天的 ▼:并着牵出的 a13
    expect(hitMarkGrows(y, ['b13'])).toBe(false)                // 没算上的那次
    expect(hitMarkGrows(y, ['a14', 'b14'])).toBe(false)         // 同一层的别的买点日
    expect(hitMarkGrows(hl([FAM0, buy(13), h('b13', 13)]), ['b13'])).toBe(true)   // 选中的那一次
    expect(hitMarkGrows(hl([]), ['a13'])).toBe(false)
  })
  it('band 上的方块:有一个是有关的就加细边(任何档);同一层、无关的不加', () => {
    const y = hl([FAM0, buy(13)])
    expect(isRelatedMark(y, [id(S10)])).toBe(true)
    expect(isRelatedMark(y, [id(S11), id(S10)])).toBe(true)
    expect(isRelatedMark(y, [id(S11)])).toBe(false)
    expect(isRelatedMark(hl([e(T13)]), [id(T13)])).toBe(true)    // 选中的那一个
    expect(isRelatedMark(hl([e(T13)]), [id(T14)])).toBe(false)   // 同一层
  })
  it('细边:1px、往里收半个边宽(外沿不变),颜色是方块本色深一档;窄于门槛、不加时原样', () => {
    const box = { x: 10, y: 20, width: 12, height: 14 }
    const on = relatedEdgeRect(box, '#1a80ba', true)
    expect(on.shape).toEqual({ x: 10.5, y: 20.5, width: 11, height: 13 })
    expect(on.stroke).toEqual({ stroke: darken('#1a80ba', RELATED_EDGE_DARKEN), lineWidth: RELATED_EDGE_W })
    expect(relatedEdgeRect(box, '#1a80ba', false)).toEqual({ shape: box, stroke: {} })
    expect(relatedEdgeRect({ ...box, width: RELATED_EDGE_MIN_W - 1 }, '#1a80ba', true).stroke).toEqual({})
    expect(darken('#1a80ba', 0.35)).toBe('#115379')            // 色相不变、深一档
    expect(darken('#fff', 0.5)).toBe('#808080')
    expect(darken('rgb(1,2,3)', 0.5)).toBe('rgb(1,2,3)')       // 认不出的写法原样
  })
})

describe('selHighlight · 画淡的程度只在一处', () => {
  it('app 那边 0.5、用户那边 0.28;照常为 1', () => {
    expect([DIM_APP_OPACITY, DIM_USER_OPACITY]).toEqual([0.5, 0.28])
    expect([dimOpacity('app', true), dimOpacity('user', true), dimOpacity('app', false)]).toEqual([0.5, 0.28, 1])
  })
})
