// compare 下 hits 行的点击(spec 6.13):点 ▼ / 点那一列有 ▼ 的格 / 点一族 / 点反馈记号各发起什么反馈,
// 焦点照旧怎么走,以及交给 feedback store 后面板的状态。后端换成内存里的假实现(同 stores.feedback.spec.ts)。
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
import { feedbackClickTarget, handleAppClick } from '../src/components/KlineChart'
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
const click = (seriesName: string, data: any) => ({ seriesName, data, event: { event: { clientX: 30, clientY: 40 } } })

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
  return handleAppClick(p, HITS, view, { comparing: view.comparing, compareReady, dates: DATES, symbol: 'AAA',
                                         selectBox: (id) => ann.selectBox(id), feedback: fb })
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})
afterEach(() => { useFeedbackStore().$dispose() })

describe('feedbackClickTarget:三种对象落成一段日期', () => {
  it('▼ → point,那天(K 线下标换成日期)', () => {
    expect(feedbackClickTarget(click('brackets', buyRec(5)), DATES, 'AAA'))
      .toEqual({ symbol: 'AAA', start: DATES[5], end: DATES[5], target: 'point' })
  })

  it('格:那一列有 ▼ → point;没有 → 不发起', () => {
    expect(feedbackClickTarget(click('brackets', cellRec(6)), DATES, 'AAA'))
      .toEqual({ symbol: 'AAA', start: DATES[6], end: DATES[6], target: 'point' })
    expect(feedbackClickTarget(click('brackets', cellRec(8)), DATES, 'AAA')).toBeNull()
  })

  it('族那一行 → family:范围 = 全部 ▼ 最早 ~ 最晚,family_start = 族起点日期;没有 ▼ 的族不发起', () => {
    const line = bundle.bracketLineData[0]
    expect(feedbackClickTarget(click('bracket-lines', line), DATES, 'AAA'))
      .toEqual({ symbol: 'AAA', start: DATES[4], end: DATES[7], target: 'family', family_start: DATES[0] })
    expect(feedbackClickTarget(click('bracket-lines', { ...line, buy_days: [] }), DATES, 'AAA')).toBeNull()
  })

  it('反馈记号 → 那条的编号;别的系列、没有股票时不发起', () => {
    expect(feedbackClickTarget(click(FEEDBACK_SERIES, { feedback_id: 'f-pc-1' }), DATES, 'AAA')).toEqual({ id: 'f-pc-1' })
    expect(feedbackClickTarget(click('intervals', { instance_id: 'x' }), DATES, 'AAA')).toBeNull()
    expect(feedbackClickTarget(click('brackets', buyRec(5)), DATES, null)).toBeNull()
    expect(feedbackClickTarget(null, DATES, 'AAA')).toBeNull()
  })
})

describe('compare 下的点击:焦点照旧,面板交给 feedback store', () => {
  it('点 ▼:照旧 focusBuyDay(当前日落在那天),并在点击处打开 point 面板', async () => {
    const { view, fb } = await setup()
    expect(compareClick(click('brackets', buyRec(5)), view, fb)).toBe(true)
    expect(view.currentDay).toBe(5)
    expect(view.activeFamilyKey).toBe('hits@0')
    expect(fb.panel).toMatchObject({ x: 30, y: 40, symbol: 'AAA', start: DATES[5], end: DATES[5], target: 'point' })
    expect(fb.panel?.editingId).toBeUndefined()
  })

  it('点格:照旧 focusHits(选中那次 hit);那一列有 ▼ 才开面板', async () => {
    const { view, fb } = await setup()
    compareClick(click('brackets', cellRec(8)), view, fb)
    expect(view.selectedHitId).toBe('h8')
    expect(fb.panel).toBeNull()
    compareClick(click('brackets', cellRec(4)), view, fb)
    expect(view.selectedHitId).toBe('h4')
    expect(fb.panel).toMatchObject({ start: DATES[4], end: DATES[4], target: 'point' })
  })

  it('点族:只设当家行(不进待选、不改选中的 hit),返回 true;打开 family 面板', async () => {
    const { view, fb } = await setup()
    view.focusHit('h6')
    expect(compareClick(click('bracket-lines', bundle.bracketLineData[0]), view, fb)).toBe(true)
    expect(view.activeFamilyKey).toBe('hits@0')
    expect(view.selectedHitId).toBe('h6')
    expect(view.candidateHitIds.size).toBe(0)
    expect(fb.panel).toMatchObject({ start: DATES[4], end: DATES[7], target: 'family', family_start: DATES[0] })
  })

  it('点中 app 的东西取消框的选中;app 还没跑完可对照时不开面板,焦点照旧', async () => {
    const box = { id: 'b-pc-1', feature: null, start: DATES[1], end: DATES[3] }
    const { ann, view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [box], samples: [] }] }))
    ann.selectBox('b-pc-1')
    compareClick(click('bracket-lines', bundle.bracketLineData[0]), view, fb)
    expect(ann.selectedBoxId).toBeNull()
    fb.close()
    compareClick(click('brackets', buyRec(6)), view, fb, false)
    expect(view.currentDay).toBe(6)
    expect(fb.panel).toBeNull()
  })

  it('同范围已有反馈:点 ▼ 打开那条;点记号打开那条并选中', async () => {
    const rec = { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: DATES[5], end: DATES[5],
                  target: 'point', source: 'picked', answer: 'neg', note: 'late' }
    const { view, fb } = await setup(annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [rec as any] }] }))
    compareClick(click('brackets', buyRec(5)), view, fb)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', answer: 'neg', note: 'late' })
    fb.close()
    expect(compareClick(click(FEEDBACK_SERIES, { value: [5, 5, 0], feedback_id: 'f-pc-1' }), view, fb)).toBe(true)
    expect(fb.selectedId).toBe('f-pc-1')
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', start: DATES[5] })
  })
})
