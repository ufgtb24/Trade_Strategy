// 选中与按键走动(store 层):点什么就选中什么;← / → 跨天(当前日竖线跟着挪)、↑ / ↓ 留在同一天(竖线不动)、
// Esc 往外退一层。选中的 hit / event、当前日由选中的那条路径统一写到渲染层读的那几个量上。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { slotText } from '../src/render/selSnapshot'
import type { Sel } from '../src/render/select'
import type { EventDict, HitDict, MultiScanResultFile } from '../src/types'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// new_step 式:旧平台 O 被全部 hit 共用;两种阶跃切法 S10(一根)、S11(两根);13、14 两天各有两种切法,15 只有一根那种
const O = ev('old_plat', 0, 9)
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15), T16 = ev('today', 16, 16)
const kids = (s: EventDict, t: EventDict) => ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id] })
const P13a = ev('plateau', 0, 13, 0, kids(S10, T13)), P13b = ev('plateau', 0, 13, 1, kids(S11, T13))
const P14a = ev('plateau', 0, 14, 0, kids(S10, T14)), P14b = ev('plateau', 0, 14, 1, kids(S11, T14))
const P15a = ev('plateau', 0, 15, 0, kids(S10, T15))
const P16a = ev('plateau', 0, 16, 0, kids(S10, T16))   // 没成 hit
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})
const H = { a13: hit('a13', P13a), b13: hit('b13', P13b), a14: hit('a14', P14a), b14: hit('b14', P14b), a15: hit('a15', P15a) }
const DATES = Array.from({ length: 20 }, (_, i) => `2024-11-${String(i + 1).padStart(2, '0')}`)

function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: {
      end_node: 'plateau.today',
      pattern_spec: {
        pattern_id: 'p1',
        topology: {
          nodes: [
            { node_id: 'plateau', render_grid: 'time', where_rules: [] },
            { node_id: 'old_plat', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'step', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
          ],
          edges: [],
        },
        event_styles: {},
      },
    } },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [O, S10, S11, T13, T14, T15, T16, P13a, P13b, P14a, P14b, P15a, P16a],
      hits: Object.values(H),
    }, summary: { hits: 5 } } } }],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
  } as any
}

const FAM: Sel = { kind: 'hit_family', familyKey: 'hits@0' }
const buy = (day: number): Sel => ({ kind: 'buy', day })
const h = (hitId: string, day: number): Sel => ({ kind: 'hit', hitId, day })
const e = (x: EventDict): Sel => ({ kind: 'event', instanceId: x.instance_id })
const node = (band: string): Sel => ({ kind: 'node', band })

describe('view store · 选中与 ← / →、↑ / ↓、Esc', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function setup() {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('detected')
    view.setBarDates(DATES)
    return view
  }
  /** 两个键槽上的字(不适用为 null) */
  const slots = (view: ReturnType<typeof useViewStore>) =>
    [slotText(view.selInfo!.day), slotText(view.selInfo!.stack)]

  it('点 ▼:选中这一天整体(不是其中哪一次),竖线落这天;↓ 进到这天的几次、在它们之间换(竖线不动);← / → 换天(竖线跟着挪)', () => {
    const view = setup()
    view.clickBuyDay('hits@0', 13)
    expect(view.selPath).toEqual([FAM, buy(13)])
    expect([view.selInfo!.kind, view.selInfo!.date]).toEqual(['buy', '2024-11-14'])
    expect(slots(view)).toEqual(['buys 1/3', 'into hits ×2'])
    expect(view.focusedHitId).toBeNull()                // 这天叠着两次:哪一次都不算选中
    expect(view.selDayHitIds).toEqual(['a13', 'b13'])
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('hits@0')
    view.stepStack(1)
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.stack)]).toEqual(['a13', 13, 'hits 1/2'])
    view.stepStack(1)
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.stack)]).toEqual(['b13', 13, 'hits 2/2'])
    view.stepStack(1)                                   // 到头不动
    expect(view.focusedHitId).toBe('b13')
    view.stepPos(1)                                     // 切法跟着走:b13(两根)→ b14(两根)
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.day)]).toEqual(['b14', 14, 'buys 2/3'])
    view.stepPos(1)                                     // 15 只有一根那种
    expect([view.focusedHitId, view.currentDay]).toEqual(['a15', 15])
    view.stepPos(1)                                     // 到头不动
    expect(view.focusedHitId).toBe('a15')
    expect(view.selPath[0]).toEqual(FAM)                // 按键一直在这一族里走
  })

  it('点 ▼ 而这天只有一次 hit:这一天就是那次 hit,直接选中它;↑ / ↓ 不适用', () => {
    const view = setup()
    view.clickBuyDay('hits@0', 15)
    expect(view.selPath).toEqual([FAM, buy(15)])
    expect([view.focusedHitId, view.selInfo!.kind, view.selInfo!.id]).toEqual(['a15', 'hit', 'a15'])
    expect(slots(view)).toEqual(['buys 3/3', null])
    view.stepStack(1)
    expect(view.selPath).toEqual([FAM, buy(15)])
  })

  it('已经进到这天的某一次,再点同一个 ▼:选中的回到这一天整体', () => {
    const view = setup()
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    expect(view.focusedHitId).toBe('a13')
    view.clickBuyDay('hits@0', 13)
    expect(view.selPath).toEqual([FAM, buy(13)])
    expect(view.focusedHitId).toBeNull()
  })

  it('点 band 上被几天共用的 step:选中的是这个 event,竖线落它的终点,用到它的 hit 画细框;→ 进到最近的买点日(整天),↓ 再进到用到它的那次', () => {
    const view = setup()
    view.focusMark([S10.instance_id])
    expect(view.selPath).toEqual([node('step'), e(S10)])
    expect([view.selectedInstanceId, view.focusedHitId, view.currentDay]).toEqual([S10.instance_id, null, 10])
    expect([view.selInfo!.kind, view.selInfo!.node, view.selInfo!.date]).toEqual(['event', 'step', '2024-11-11'])
    expect(slots(view)).toEqual(['into buys ×3', null])
    expect(view.selInfo!.hits!.head).toBe('×3')
    expect([...view.candidateHitIds].sort()).toEqual(['a13', 'a14', 'a15'])
    view.stepPos(1)                                     // 停在 13 这一天整体:这个 event 不再是选中的那一个,但还在用
    expect(view.selPath).toEqual([node('step'), e(S10), buy(13)])
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, null, 13])
    expect(view.pendingDisambigInstanceId).toBe(S10.instance_id)
    expect(view.selDayHitIds).toEqual(['a13', 'b13'])   // 这个 ▼ 上的两次都在,用到它的排第一
    view.stepStack(1)
    expect([view.focusedHitId, view.focusedInstanceId, view.currentDay]).toEqual(['a13', S10.instance_id, 13])
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect([...view.candidateHitIds].sort()).toEqual(['a13', 'a14', 'a15'])    // 进到某一次之后细框不消失
    view.stepPos(1)
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.day)]).toEqual(['a14', 14, 'buys 2/3'])
    expect(view.activeFamilyKey).toBeNull()             // 选中的不在 hits 的哪一族下面:不加粗哪一行的底线,靠细框和显示栏认
  })

  it('点了就是点的那个:从 event 走进某一天后点 ▼,选中换成那一族的这一天;再点回 event,选中的就是这个 event', () => {
    const view = setup()
    view.focusMark([S10.instance_id])
    view.stepPos(1); view.stepPos(1)                    // 14 那一天
    expect(view.selPath).toEqual([node('step'), e(S10), buy(14)])
    view.clickBuyDay('hits@0', 14)
    expect(view.selPath).toEqual([FAM, buy(14)])
    view.stepStack(1); view.stepStack(1)
    expect(view.focusedHitId).toBe('b14')
    view.focusMark([S10.instance_id])
    expect(view.selPath).toEqual([node('step'), e(S10)])
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, S10.instance_id, 10])
  })

  it('old_plat 被全部 hit 共用:牵出 5 次 hit、3 个买点日;进到某一天后那天叠着两次,↓ 在它们之间换', () => {
    const view = setup()
    view.focusMark([O.instance_id])
    expect([view.selInfo!.node, view.selInfo!.date]).toEqual(['old_plat', '2024-11-01→2024-11-10'])
    expect([view.selInfo!.buys, view.selInfo!.hits!.head]).toEqual(['2024-11-14…2024-11-16 ×3', '×5'])
    expect(slots(view)).toEqual(['into buys ×3', null])
    view.stepPos(1)
    expect(view.selDayHitIds).toEqual(['a13', 'b13'])
    expect(slots(view)).toEqual(['buys 1/3', 'into hits ×2'])
    view.stepStack(1); view.stepStack(1)
    expect(view.focusedHitId).toBe('b13')
  })

  it('进去落哪:竖线那天本身是买点日就落它;否则按键方向最近的;那个方向没有就取另一边最近的', () => {
    const view = setup()
    view.setCurrentDay(14)
    view.clickFamilyLine('hits@0')
    view.stepPos(-1)                                    // 竖线在 14,14 就是买点日:← 也先落它
    expect(view.selPath).toEqual([FAM, buy(14)])
    view.clearFocus()
    view.setCurrentDay(12)
    view.clickFamilyLine('hits@0')
    expect(view.currentDay).toBe(12)                    // 选中一族不挪竖线
    view.stepPos(1)
    expect(view.currentDay).toBe(13)
    view.clearFocus()
    view.setCurrentDay(18)
    view.clickFamilyLine('hits@0')
    view.stepPos(1)                                     // 右边没有买点日:落左边最近的
    expect([view.focusedHitId, view.currentDay]).toEqual(['a15', 15])
    view.clearFocus()
    view.setCurrentDay(2)
    view.clickFamilyLine('hits@0')
    view.stepPos(-1)                                    // 左边没有:落右边最近的
    expect(view.selPath).toEqual([FAM, buy(13)])
  })

  it('点 today 那种点(只牵出一天):选中的是这个 event;← / → 沿这条 band 换到旁边那格,↑ / ↓ 不适用', () => {
    const view = setup()
    view.focusMark([T13.instance_id])
    expect(view.selPath).toEqual([node('today'), e(T13)])
    expect([view.focusedHitId, view.selectedInstanceId]).toEqual([null, T13.instance_id])
    expect([view.selInfo!.buys, view.selInfo!.hits!.head]).toEqual(['2024-11-14 ×1', '×2'])
    expect(slots(view)).toEqual(['events 1/4', null])
    expect(view.stepPos(1)).toBe(true)
    expect([view.selectedInstanceId, view.currentDay]).toEqual([T14.instance_id, 14])
    expect(view.stepStack(1)).toBe(true)                // 有选中就接下,但不动
    expect(view.selPath).toEqual([node('today'), e(T14)])
  })

  it('点 plateau 那一格(两个成员):选中其中一个 event,↑ / ↓ 在这一格里换;← / → 沿 band 按格走,落同一个起点的;没进 hit 的格照样走得到', () => {
    const view = setup()
    view.focusMark([P13a.instance_id, P13b.instance_id])
    expect(view.selPath).toEqual([node('plateau'), e(P13a)])
    expect(view.activeFamilyKey).toBeNull()             // 选中 event 时,它那条 band 的族底线不加粗
    expect(slots(view)).toEqual(['events 1/4', 'events 1/2'])
    expect(view.selInfo!.diff).toBe('step→2024-11-11')
    view.stepStack(1)
    expect([view.selectedInstanceId, view.focusedHitId, view.currentDay]).toEqual([P13b.instance_id, null, 13])
    view.focusMark([P13a.instance_id, P13b.instance_id])     // 当前选中的就在点中的这一格里:不换
    expect(view.selectedInstanceId).toBe(P13b.instance_id)
    view.stepPos(1)
    expect([view.selectedInstanceId, view.currentDay]).toEqual([P14a.instance_id, 14])
    view.stepPos(1); view.stepPos(1)
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, P16a.instance_id, 16])
    expect(view.selPath[0]).toEqual(node('plateau'))
  })

  it('点族底线:一律退回整族(不选其中哪一天、哪一次),竖线不动;按键先落竖线那天', () => {
    const view = setup()
    view.clickFamilyLine('hits@0')
    expect(view.selPath).toEqual([FAM])
    expect(view.selInfo!.kind).toBe('hit_family')
    view.stepPos(-1)
    expect([view.focusedHitId, view.currentDay]).toEqual(['a15', 15])
    // 已选着这一族里的一次,再点底线:退回整族,竖线留在 15
    view.clickFamilyLine('hits@0')
    expect([view.focusedHitId, view.selPath, slotText(view.selInfo!.day), view.currentDay])
      .toEqual([null, [FAM], 'into buys ×3', 15])
    // 竖线那天就是一个买点日:→ 和 ← 都先落它
    view.stepPos(1)
    expect([view.focusedHitId, slotText(view.selInfo!.day)]).toEqual(['a15', 'buys 3/3'])
    view.clickFamilyLine('hits@0')
    view.stepPos(-1)
    expect([view.focusedHitId, slotText(view.selInfo!.day)]).toEqual(['a15', 'buys 3/3'])
    // 从点 ▼ 选中的一天退回整族
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    expect(view.focusedHitId).toBe('a13')
    view.clickFamilyLine('hits@0')
    expect([view.focusedHitId, view.selPath, view.currentDay]).toEqual([null, [FAM], 13])
  })

  it('点格(终点在这天的几次):当前那次在格里不换,否则落第一次;竖线落在它的买入日', () => {
    const view = setup()
    view.clickHitCell('hits@0', ['a14', 'b14'])
    expect([view.focusedHitId, view.currentDay]).toEqual(['a14', 14])
    view.stepStack(1)
    view.clickHitCell('hits@0', ['a14', 'b14'])
    expect(view.focusedHitId).toBe('b14')
  })

  it('点反馈记号:选中这条反馈,竖线不动;它收进来的是段里有买点的 hit,一族反馈另加起于它那个起点的整族', () => {
    const view = setup()
    view.setSelSources({ feedbacks: () => [
      { id: 'f1', start: '2024-11-16', end: '2024-11-17' },                              // 下标 15、16:只有 a15 买在段里
      { id: 'f2', start: '2024-11-19', end: '2024-11-20', family_start: '2024-11-01' },
      { id: 'f3', start: '2024-11-19', end: '2024-11-20' },                              // 段里 app 不买
    ] })
    view.setCurrentDay(12)
    view.clickFeedback({ id: 'f1' })
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f1' }])
    expect([view.focusedHitId, view.currentDay]).toEqual([null, 12])
    expect([...view.selHits.ids]).toEqual(['a15'])
    expect([...view.candidateHitIds]).toEqual(['a15'])                                   // 收进来的 hit 画细框
    expect([view.selInfo!.kind, view.selInfo!.buys, view.selInfo!.hits!.head]).toEqual(['feedback', '2024-11-16 ×1', '×1'])
    view.clickFeedback({ id: 'f2' })
    expect([...view.selHits.ids].sort()).toEqual(['a13', 'a14', 'a15', 'b13', 'b14'])
    expect([view.selInfo!.hits!.head, slotText(view.selInfo!.day)]).toEqual(['×5', 'into buys ×3'])
    view.clickFeedback({ id: 'f3' })
    expect(view.selHits.ids.size).toBe(0)
    expect([view.selInfo!.buys, view.selInfo!.hits!.head]).toEqual(['none', 'none'])
  })

  it('反馈收进两个以上买点日:← / → 进到其中一天,Esc 退回这条反馈', () => {
    const view = setup()
    view.setSelSources({ feedbacks: () => [{ id: 'f2', start: '2024-11-14', end: '2024-11-15' }] })
    view.clickFeedback({ id: 'f2' })
    view.stepPos(1)
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f2' }, buy(13)])
    expect(view.currentDay).toBe(13)
    view.stepUp()
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f2' }])
  })

  it('focusHit(侧栏 hits 列表):选中这一次,它属于它那一族的那个买点日,竖线落那天', () => {
    const view = setup()
    view.focusHit('b14')
    expect(view.selPath).toEqual([FAM, buy(14), h('b14', 14)])
    expect([view.focusedHitId, view.currentDay, slotText(view.selInfo!.stack)]).toEqual(['b14', 14, 'hits 2/2'])
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('点轨名:选中这条 band(一个 node),不选中任何 hit / event;← / → 进到 band 上的格', () => {
    const view = setup()
    view.selectNode('step')
    expect(view.selPath).toEqual([node('step')])
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, null, null])
    expect(slots(view)).toEqual(['into events ×2', null])
    view.stepPos(1)
    expect(view.selPath).toEqual([node('step'), e(S10)])
  })

  it('Esc 往外退一层:一次 hit → 这一天 → 一族 → 清空;没有选中时这一下不归它', () => {
    const view = setup()
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    expect(view.selPath).toEqual([FAM, buy(13), h('a13', 13)])
    expect(view.selInfo!.esc).toBe('up: buy 2024-11-14')
    expect(view.stepUp()).toBe(true)
    expect([view.selPath, view.focusedHitId, view.currentDay]).toEqual([[FAM, buy(13)], null, 13])
    expect(view.stepUp()).toBe(true)
    expect(view.selPath).toEqual([FAM])
    expect(view.selInfo!.esc).toBe('clear')
    expect(view.stepUp()).toBe(true)
    expect([view.selPath, view.selInfo, view.currentDay]).toEqual([[], null, null])
    expect(view.stepUp()).toBe(false)
  })

  it('Esc 从只有一次的那一天上退:那一天和那次 hit 是同一样东西,一下退回一族', () => {
    const view = setup()
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1)
    view.stepPos(1); view.stepPos(1)                    // 带着这一次走到 15,那天只有一次
    expect(view.selPath).toEqual([FAM, buy(15), h('a15', 15)])
    view.stepUp()
    expect(view.selPath).toEqual([FAM])
  })

  it('每走一步 moveSeq 加一;没有选中时按键不接', () => {
    const view = setup()
    expect(view.stepPos(1)).toBe(false)
    expect(view.stepStack(1)).toBe(false)
    view.clickBuyDay('hits@0', 13)
    const s = view.moveSeq
    view.stepPos(1)
    view.stepStack(1)
    expect(view.moveSeq).toBe(s + 2)
  })
})
