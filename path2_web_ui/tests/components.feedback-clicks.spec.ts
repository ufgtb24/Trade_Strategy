// compare 下 hits 行的点击(spec 6.13):点 ▼ / 点格 / 点一族 / 点反馈记号只改选中、不开面板;选中之后
// 对它打开(stores/feedback.ts 的 openSelected,Enter 与显示栏 feedback 按钮走的就是它)得到什么范围;
// 焦点照旧怎么走,面板开着时按键挪了选中之后的去留。后端换成内存里的假实现(同 stores.feedback.spec.ts)。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnOp, AnnRead, AnnState } from '../src/annotate/model'
import type { EventDict, HitDict } from '../src/types'

const fake = vi.hoisted(() => ({ read: null as any }))

vi.mock('../src/api', async (orig) => {
  const m: Record<string, any> = await orig()
  const model = await vi.importActual<typeof import('../src/annotate/model')>('../src/annotate/model')
  const out: Record<string, any> = Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' && /^[a-z]/.test(k) ? vi.fn(() => new Promise(() => {})) : v]))
  return {
    ...out,
    getAnnotations: async () => structuredClone(fake.read),
    postAnnotationBatch: async (ops: AnnOp[]) => {
      fake.read = { ...model.applyOps(fake.read, ops), revs: fake.read.revs }
      return { file: 'pc-batch-1.json', ...structuredClone(fake.read) }
    },
    getFeedbackStatus: async () => ({ app: 'app1', app_ver: 'v1', items: [], reason: null }),
  }
})

import { useAnnotationStore } from '../src/stores/annotation'
import { useViewStore } from '../src/stores/view'
import { useFeedbackStore } from '../src/stores/feedback'
import { useAppLinkStore } from '../src/stores/appLink'
import { useCompareStore } from '../src/stores/compare'
import { feedbackMarkOf, handleAppClick } from '../src/components/KlineChart'
import { computeEventData } from '../src/render/chart'
import { FEEDBACK_SERIES } from '../src/render/feedbackStrip'

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09', '2025-01-10',
               '2025-01-13', '2025-01-14']
const bars = DATES.map(date => ({ date, o: 1, h: 1, l: 1, c: 1, v: 1, rv: 1 }))

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
// 买点 node = plateau.today:一族 hits@0,h4 买第 4 根、h6 买第 5、6 根;h8 终点 8、买点 7(格那一列没有 ▼)
const T4 = ev('today', 4, 4), T6 = ev('today', 5, 6), T7 = ev('today', 7, 7)
const P4 = ev('plateau', 0, 4, 0, { today: [T4.instance_id] })
const P6 = ev('plateau', 0, 6, 0, { today: [T6.instance_id] })
const P8 = ev('plateau', 0, 8, 0, { today: [T7.instance_id] })
const hit = (id: string, p: EventDict): HitDict =>
  ({ hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id }, children: [] })
const EVENTS = [T4, T6, T7, P4, P6, P8]
const HITS = [hit('h4', P4), hit('h6', P6), hit('h8', P8)]

const run = () => ({
  symbol: 'AAA', app: 'app1', analysis: { events: EVENTS, hits: HITS },
  pattern_spec: { pattern_id: 'app1', event_styles: {}, debug_enabled_nodes: [], topology: { edges: [], nodes: [
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
  ] } },
  scan: { end_node: 'plateau.today', app_ver: 'v1' } as any,
}) as any

const bundle = computeEventData(bars as any, EVENTS, HITS, {
  topology: run().pattern_spec.topology, isolatedNodeIds: new Set(), tagList: [], level: 'detected', nodeColors: {},
  eventTier: () => 'in_hit', nodeOfEventByBand: (e: EventDict) => e.node_id, bandKeyOf: (e: EventDict) => e.node_id,
  tagToNodes: {}, endNode: 'plateau.today',
} as any)
const buyRec = (day: number) => bundle.bracketData.find((d: any) => d.kind === 'buy' && d.buy_day === day)
const cellRec = (end: number) => bundle.bracketData.find((d: any) => d.kind === 'mark' && d.value[0] === end)
const click = (seriesName: string, data: any) => ({ seriesName, data })

function annRead(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}

async function settle() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0))
}

/** 标注读好、当前 pattern 为 p、AAA 在 compare 下跑完了 app。 */
async function setup(read: AnnRead = annRead()) {
  fake.read = read
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const view = useViewStore()
  view.symbol = 'AAA'
  view.barDates = DATES
  const fb = useFeedbackStore()
  view.mode = 'compare'
  await nextTick()
  view.setLinkedRun(run())
  await settle()
  return { ann, view, fb }
}

/** KlineChart.vue 的 onAppClick:同一个 handleAppClick,上下文照它接(compare、app 跑完可对照)。 */
function compareClick(p: any, view: ReturnType<typeof useViewStore>, fb: ReturnType<typeof useFeedbackStore>,
                      compareReady = true) {
  const ann = useAnnotationStore()
  return handleAppClick(p, HITS, view, { comparing: view.comparing, compareReady,
                                         selectBox: (id) => ann.selectBox(id), feedback: fb })
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})
afterEach(() => { useFeedbackStore().$dispose() })

describe('feedbackMarkOf:点中的是不是反馈带记号', () => {
  it('反馈记号 → 那条的编号;别的系列、记号上没有编号、没点中时为 null', () => {
    expect(feedbackMarkOf(click(FEEDBACK_SERIES, { feedback_id: 'f-pc-1' }))).toBe('f-pc-1')
    expect(feedbackMarkOf(click(FEEDBACK_SERIES, {}))).toBeNull()
    expect(feedbackMarkOf(click('brackets', buyRec(5)))).toBeNull()
    expect(feedbackMarkOf(click('bracket-lines', bundle.bracketLineData[0]))).toBeNull()
    expect(feedbackMarkOf(click('intervals', { instance_id: 'x', feedback_id: 'f-pc-1' }))).toBeNull()
    expect(feedbackMarkOf(null)).toBeNull()
  })
})

describe('compare 下的点击只选中、不开面板;选中之后对它打开得到什么范围', () => {
  it('点 ▼:选中那一族的这一天、当前日落在那天,不开面板;打开得 point(那天)', async () => {
    const { view, fb } = await setup()
    const n = fb.opens
    expect(compareClick(click('brackets', buyRec(5)), view, fb)).toBe(true)
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@0' }, { kind: 'buy', day: 5 }])
    expect(view.currentDay).toBe(5)
    expect(view.activeFamilyKey).toBe('hits@0')
    expect(fb.panel).toBeNull()
    expect(fb.opens).toBe(n)
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: DATES[5], end: DATES[5], target: 'point' })
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toEqual({ symbol: 'AAA', start: DATES[5], end: DATES[5], target: 'point', note: '', nodes: [] })
  })

  it('点格:那一列有 ▼ 时同点 ▼(那天);没有 ▼ 时选中格上那次 hit,作答落在它的买点日', async () => {
    const { view, fb } = await setup()
    compareClick(click('brackets', cellRec(4)), view, fb)
    expect(view.selectedHitId).toBe('h4')
    expect(fb.panel).toBeNull()
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: DATES[4], end: DATES[4], target: 'point' })
    // h8 终点 8、买点 7:格那一列没有 ▼,选中的是买点日 7 上的这次 hit
    compareClick(click('brackets', cellRec(8)), view, fb)
    expect(view.selectedHitId).toBe('h8')
    expect(view.selLast).toEqual({ kind: 'hit', hitId: 'h8', day: 7 })
    expect(fb.panel).toBeNull()
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: DATES[7], end: DATES[7], target: 'point' })
  })

  it('点族:选中换成那一族、退回整族(不选其中哪一次),竖线不动,返回 true,不开面板;打开得 family', async () => {
    const { view, fb } = await setup()
    view.focusHit('h6')
    const day = view.currentDay
    expect(compareClick(click('bracket-lines', bundle.bracketLineData[0]), view, fb)).toBe(true)
    expect(view.activeFamilyKey).toBe('hits@0')
    expect(view.selectedHitId).toBeNull()
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@0' }])
    expect(view.currentDay).toBe(day)
    expect(view.candidateHitIds.size).toBe(0)
    expect(fb.panel).toBeNull()
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ start: DATES[4], end: DATES[7], target: 'family', family_start: DATES[0] })
  })

  it('点中 app 的东西取消框的选中;app 还没跑完可对照时点记号不选中那条反馈,焦点照旧', async () => {
    const box = { id: 'b-pc-1', feature: null, start: DATES[1], end: DATES[3] }
    const rec = { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: DATES[5], end: DATES[5],
                  target: 'point', source: 'picked', note: 'late' }
    const { ann, view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [box], samples: [],
                                                              feedback: [rec as any] }] }))
    ann.selectBox('b-pc-1')
    compareClick(click('bracket-lines', bundle.bracketLineData[0]), view, fb)
    expect(ann.selectedBoxId).toBeNull()
    expect(fb.panel).toBeNull()
    compareClick(click('brackets', buyRec(6)), view, fb, false)
    expect(view.currentDay).toBe(6)
    expect(fb.panel).toBeNull()
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-pc-1' }), view, fb, false)
    expect(fb.selectedId).toBeNull()
    expect(fb.panel).toBeNull()
  })

  it('点记号:选中那条反馈(换掉原来选中的),不开面板;打开的是那条(预填);同范围的 ▼ 打开的也是那条', async () => {
    const rec = { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: DATES[5], end: DATES[5],
                  target: 'point', source: 'picked', answer: 'neg', note: 'late' }
    const { view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [rec as any] }] }))
    expect(compareClick(click(FEEDBACK_SERIES, { value: [5, 5, 0], feedback_id: 'f-pc-1' }), view, fb)).toBe(true)
    expect(fb.selectedId).toBe('f-pc-1')
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f-pc-1' }])
    expect(fb.panel).toBeNull()
    expect(fb.selTarget).toEqual({ id: 'f-pc-1' })
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', start: DATES[5], note: 'late' })
    expect('answer' in fb.panel!).toBe(false)             // 以前存下的 answer 不进面板
    fb.close()
    compareClick(click('brackets', buyRec(5)), view, fb)
    expect(fb.panel).toBeNull()
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', note: 'late' })
  })

  it('面板开着时点另一个 ▼:点击不换面板(关面板由面板自己的「点外面就关」做),选中换过去', async () => {
    const { view, fb } = await setup()
    compareClick(click('brackets', buyRec(5)), view, fb)
    fb.openSelected()
    const n = fb.opens
    compareClick(click('brackets', buyRec(4)), view, fb)
    expect(fb.opens).toBe(n)
    expect(fb.panel).toMatchObject({ start: DATES[5], end: DATES[5] })
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@0' }, { kind: 'buy', day: 4 }])
    expect(fb.selTarget).toMatchObject({ start: DATES[4], end: DATES[4] })
  })
})

describe('按键挪了选中之后面板的去留:面板对着的那一块还包含当前那个就留着,出去了就关', () => {
  const rec = (id: string, s: number, e: number) => ({ id, pattern: 'p', app_id: 'app1', app_ver: 'v0',
    start: DATES[s], end: DATES[e], target: s === e ? 'point' : 'range', source: 'picked', note: 'x' })

  it('point 面板对着那一天:→ 换到旁边那天就关', async () => {
    const { view, fb } = await setup()
    compareClick(click('brackets', buyRec(5)), view, fb)
    fb.openSelected()
    expect(fb.panel).toMatchObject({ target: 'point', start: DATES[5] })
    view.stepPos(1)
    await nextTick()
    expect(view.currentDay).toBe(6)
    expect(fb.panel).toBeNull()
  })

  it('family 面板对着这一族:在这一族的买点日之间走,面板一直留着', async () => {
    const { view, fb } = await setup()
    compareClick(click('bracket-lines', bundle.bracketLineData[0]), view, fb)
    fb.openSelected()
    expect(fb.panel).toMatchObject({ target: 'family' })
    for (const day of [4, 5, 6, 7]) {
      view.stepPos(1)
      await nextTick()
      expect(view.currentDay).toBe(day)
      expect(fb.panel).toMatchObject({ target: 'family', family_start: DATES[0] })
    }
  })

  it('点记号打开的面板对着那条反馈:走进它收进来的买点日留着;换到旁边一条反馈就关', async () => {
    const { view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [],
      feedback: [rec('f-a', 5, 6) as any, rec('f-b', 7, 7) as any] }] }))
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-a' }), view, fb)
    fb.openSelected()
    expect(fb.panel).toMatchObject({ editingId: 'f-a' })
    view.stepPos(1)                                    // f-a 收进 5、6 两个买点日:进去
    await nextTick()
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f-a' }, { kind: 'buy', day: 5 }])
    expect(fb.panel).toMatchObject({ editingId: 'f-a' })
    view.stepPos(1)
    await nextTick()
    expect(view.currentDay).toBe(6)
    expect(fb.panel).toMatchObject({ editingId: 'f-a' })
    // 退回这条反馈,再换到旁边那条(它只收进一个买点日,所以 → 是换反馈):面板对着的是 f-a,关掉
    view.stepUp()
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-b' }), view, fb)
    expect(fb.panel).toMatchObject({ editingId: 'f-a' })            // 点只选中:面板还是 f-a 的
    fb.close()
    fb.openSelected()
    expect(fb.panel).toMatchObject({ editingId: 'f-b' })
    view.stepPos(-1)
    await nextTick()
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f-a' }])
    expect(fb.panel).toBeNull()
  })

  it('竖线没动、选中已经换成旁边一条反馈:面板对着的是打开时那条,关掉', async () => {
    // 两条反馈各只收进一个买点日:→ 是在两条反馈之间换,竖线不动
    const { view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [],
      feedback: [rec('f-a', 4, 4) as any, rec('f-b', 7, 7) as any] }] }))
    view.setCurrentDay(4)                              // 竖线就在 f-a 那一天上
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-a' }), view, fb)
    fb.openSelected()
    expect(fb.panel).toMatchObject({ editingId: 'f-a', start: DATES[4], end: DATES[4] })
    view.stepPos(1)
    await nextTick()
    expect([view.selPath, view.currentDay]).toEqual([[{ kind: 'feedback', id: 'f-b' }], 4])
    expect(fb.panel).toBeNull()
  })

  it('竖线没动、选中已经换成旁边一族:面板对着的是打开时那一族,关掉', async () => {
    const { view, fb } = await setup()
    // 两族各只买一天:起于 0 的那族买第 4 根,起于 2 的那族买第 7 根——← / → 是在两族之间换,竖线不动
    const P7 = ev('plateau', 2, 7, 0, { today: [T7.instance_id] })
    const hits = [hit('h4', P4), hit('g7', P7)]
    view.setLinkedRun({ ...run(), analysis: { events: [T4, T7, P4, P7], hits } })
    await settle()
    view.setCurrentDay(4)
    const line = { ...bundle.bracketLineData[0], buy_days: [4] }
    handleAppClick(click('bracket-lines', line) as any, hits, view, { comparing: true, compareReady: true,
      selectBox: () => {}, feedback: fb })
    expect(view.selPath).toEqual([{ kind: 'hit_family', familyKey: 'hits@0' }])
    expect(fb.panel).toBeNull()
    fb.openSelected()
    expect(fb.panel).toMatchObject({ target: 'family', family_start: DATES[0], start: DATES[4], end: DATES[4] })
    view.stepPos(1)
    await nextTick()
    expect([view.selPath, view.currentDay]).toEqual([[{ kind: 'hit_family', familyKey: 'hits@2' }], 4])
    expect(fb.panel).toBeNull()
  })
})

describe('反馈记号的粗边与竖带跟着图上的选中走;删掉选中的那条,选中清空', () => {
  const rec = (id: string, day: number) => ({ id, pattern: 'p', app_id: 'app1', app_ver: 'v0',
    start: DATES[day], end: DATES[day], target: 'point', source: 'picked', note: 'x' })
  // 两条反馈各只收进一个买点日:← / → 是在两条反馈之间换
  const two = () => annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [],
    feedback: [rec('f-a', 4) as any, rec('f-b', 7) as any] }] })

  it('点第一条的记号后按 →:图上选中的换成第二条,粗边与竖带(selectedId)也是第二条;← 再换回来', async () => {
    const { view, fb } = await setup(two())
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-a' }), view, fb)
    await nextTick()
    expect([view.selPath, fb.selectedId]).toEqual([[{ kind: 'feedback', id: 'f-a' }], 'f-a'])
    view.stepPos(1)
    await nextTick()
    expect([view.selPath, fb.selectedId]).toEqual([[{ kind: 'feedback', id: 'f-b' }], 'f-b'])
    view.stepPos(-1)
    await nextTick()
    expect(fb.selectedId).toBe('f-a')
  })

  it('选中换成别的东西(点了 ▼):反馈的粗边取消;点空白清空选中时不动它', async () => {
    const { view, fb } = await setup(two())
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-a' }), view, fb)
    view.clearFocus()
    await nextTick()
    expect(fb.selectedId).toBe('f-a')
    compareClick(click('brackets', buyRec(5)), view, fb)
    await nextTick()
    expect(fb.selectedId).toBeNull()
  })

  it('删掉图上选中的那条反馈:选中清空;正在它里面走时删它也一样;删别的一条不动选中', async () => {
    const { view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
      rec('f-a', 4) as any, rec('f-b', 7) as any,
      { ...rec('f-c', 5), end: DATES[6], target: 'range' } as any,          // 收进 5、6 两个买点日
    ] }] }))
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-a' }), view, fb)
    fb.remove('f-b')                                   // 删的不是选中的那条
    await nextTick()
    expect([view.selPath, fb.selectedId]).toEqual([[{ kind: 'feedback', id: 'f-a' }], 'f-a'])
    fb.remove('f-a')
    await nextTick()
    expect([view.selPath, view.selInfo, fb.selectedId]).toEqual([[], null, null])
    compareClick(click(FEEDBACK_SERIES, { feedback_id: 'f-c' }), view, fb)
    view.stepPos(1)                                    // 走进它收进来的买点日
    expect(view.selPath).toEqual([{ kind: 'feedback', id: 'f-c' }, { kind: 'buy', day: 5 }])
    fb.remove('f-c')
    await nextTick()
    expect([view.selPath, view.focusedHitId, fb.selectedId]).toEqual([[], null, null])
  })
})

describe('选着样本时存了别的东西', () => {
  it('存一条不相干的反馈、画一个不相干的框(保存各走完一个来回,读结果整份换新):样本的选中不清', async () => {
    useAppLinkStore().mappings = [{ app: 'app1', pattern: 'p', problem: null, features: {} }]
    const { ann, view } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], feedback: [],
      samples: [{ id: 's1', date: DATES[4], pattern: 'p', judgment: 'pos', members: [] } as any] }] }))
    const cmp = useCompareStore()
    expect(cmp.focusSample('s1')).toBe(true)
    await nextTick()
    const s1 = [{ kind: 'sample', sampleId: 's1' }]

    expect(ann.saveFeedback({ symbol: 'AAA', start: DATES[7], end: DATES[7], target: 'point', note: 'x' })).not.toBeNull()
    await ann.flushed()
    await nextTick()
    expect(fake.read.state.charts[0].feedback).toHaveLength(1)     // 确实存进去了
    expect([view.selPath, cmp.focusedSampleId]).toEqual([s1, 's1'])

    expect(ann.createBox('AAA', DATES[1], DATES[2], null)).not.toBeNull()
    await ann.flushed()
    await nextTick()
    expect(fake.read.state.charts[0].boxes).toHaveLength(1)
    expect([view.selPath, cmp.focusedSampleId]).toEqual([s1, 's1'])
  })
})
