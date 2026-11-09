// 落到 compare 的某一天(stores/landing.ts)走图的默认聚焦(KlineChart.vue):挂上真的 KlineChart,K 线、跑 app、
// 标注、mapping 由内存里的假后端给,看当前日竖线落在哪。
// - 落在 compare 的链接 / 侧栏 feedback 页点一行:竖线停在那天,压过默认聚焦本来要挑的样本;选中那条反馈;
// - 换股票时现算结果先到、K 线后到,或反过来,都落在那天;落下以后就消费掉,之后的默认聚焦照旧挑样本;
// - app 没跑成(默认聚焦不会发生):K 线一到由 landing 自己落;
// - 落下之前换了股票:作废。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnRead } from '../../src/annotate/model'
import type { EventDict, HitDict } from '../../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

// 30 根 K 线:2025-01-01 ~ 2025-01-30(按日历日连着排,够用)
const DATES = Array.from({ length: 30 }, (_, i) => `2025-01-${String(i + 1).padStart(2, '0')}`)
const BARS = DATES.map(date => ({ date, o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 }))

const ev = (node: string, s: number, e: number, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#0`, node_id: node, instance_idx: 0, start_idx: s, end_idx: e, child_refs })
// 买点 node = plateau.today:一次 hit,第 4 根买(样本 2025-01-05 正好在这天)
const T4 = ev('today', 4, 4)
const P4 = ev('plateau', 0, 4, { today: [T4.instance_id] })
const HITS: HitDict[] = [{ hit_id: 'h4', start_idx: 0, end_idx: 4, node_index: { plateau: P4.instance_id }, children: [] }]
const preview = (app: string) => ({
  analysis: { events: [T4, P4], hits: HITS }, summary: {},
  pattern_spec: { pattern_id: app, event_styles: {}, debug_enabled_nodes: [], topology: { edges: [], nodes: [
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
  ] } },
  scan: { start_date: '1900-01-01', end_date: '2025-12-31', win_start: '1899-09-01', win_end: '2025-12-31',
          label_horizon: 20, end_node: 'plateau.today', app_ver: 'v1' },
})

const fake = vi.hoisted(() => ({
  read: null as any,
  barsGate: null as Promise<void> | null,
  previewGate: null as Promise<void> | null,
  previewFails: false,
}))

vi.mock('../../src/api', async (orig) => {
  const m: Record<string, any> = await orig()
  const out: Record<string, any> = Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' && /^[a-z]/.test(k) ? vi.fn(() => new Promise(() => {})) : v]))
  return {
    ...out,
    saveWcMirror: async () => ({ ok: true }), clearWcMirror: async () => ({ ok: true }),
    getAnnotations: async () => structuredClone(fake.read),
    getMappings: async () => [{ app: 'app1', pattern: 'p', features: {}, problem: null, session: null, session_problem: null }],
    getSymbols: async () => ['AAA', 'BBB'],
    getAllOhlc: async (symbol: string) => {
      if (fake.barsGate) await fake.barsGate
      return { symbol, bars: BARS }
    },
    getPreview: async (app: string) => {
      if (fake.previewGate) await fake.previewGate
      if (fake.previewFails) throw new Error('preview failed')
      return preview(app)
    },
    getFeedbackStatus: async () => ({ app: 'app1', app_ver: 'v1', items: [], reason: null }),
    getPeaks: async () => [],
  }
})

function makeFakeChart() {
  const zr = { on: vi.fn(), off: vi.fn() }
  return {
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), clear: vi.fn(),
    on: vi.fn(), off: vi.fn(), getZr: () => zr, getOption: () => ({}),
    dispatchAction: vi.fn(), convertToPixel: () => [0, 0], convertFromPixel: () => [0, 0],
    getWidth: () => 800, getHeight: () => 600, containPixel: () => false,
  }
}
vi.mock('echarts', () => ({ init: vi.fn(() => makeFakeChart()) }))

import KlineChart from '../../src/components/KlineChart.vue'
import FeedbackPage from '../../src/components/FeedbackPage.vue'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useAppLinkStore } from '../../src/stores/appLink'
import { useCompareStore } from '../../src/stores/compare'
import { useDirectLinkStore } from '../../src/stores/directLinks'
import { useFeedbackStore } from '../../src/stores/feedback'
import { dayIndexOnOrAfter, useLandingStore } from '../../src/stores/landing'
import { useViewStore } from '../../src/stores/view'

const SAMPLE_DAY = 4                                   // 样本 2025-01-05:默认聚焦本来要挑它

function annRead(): AnnRead {
  const fb = (id: string, start: string, end: string) => ({
    id, pattern: 'p', app_id: 'app1', app_ver: 'v0', start, end, target: 'range', source: 'picked',
    answer: 'neg', note: 'why' })
  const chart = (symbol: string, feedback: any[]) => ({
    symbol, boxes: [], feedback,
    samples: [{ id: `s-${symbol}`, date: DATES[SAMPLE_DAY], pattern: 'p', judgment: 'pos', members: [] }],
  })
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }],
             charts: [chart('AAA', []), chart('BBB', [fb('f-pc-1', DATES[20], DATES[24])])] },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  } as any
}

async function settle() {
  for (let i = 0; i < 6; i++) {
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
  }
}

/** 标注、mapping 读好,当前 pattern p,图挂上;open 给了就在 compare 里打开那只股票(app 跑完、默认聚焦做完)。 */
async function setup(open: string | null = 'AAA') {
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const appLink = useAppLinkStore()
  await appLink.load()
  const view = useViewStore()
  const w = mount(KlineChart)
  if (open) {
    view.openSymbol(open)
    await settle()
    appLink.setMode('compare')
    await settle()
  }
  return { ann, appLink, view, w, cmp: useCompareStore(), fb: useFeedbackStore(), landing: useLandingStore() }
}

beforeEach(() => {
  setActivePinia(createPinia())
  fake.read = annRead()
  fake.barsGate = null
  fake.previewGate = null
  fake.previewFails = false
  localStorage.clear()
  history.replaceState(null, '', '/')
})
afterEach(() => { useFeedbackStore().$dispose() })

describe('dayIndexOnOrAfter', () => {
  it('交易日取它自己;不是交易日取之后的第一根;比最后一根还晚为 null', () => {
    const d = ['2025-01-02', '2025-01-03', '2025-01-06']
    expect(dayIndexOnOrAfter(d, '2025-01-03')).toBe(1)
    expect(dayIndexOnOrAfter(d, '2025-01-04')).toBe(2)
    expect(dayIndexOnOrAfter(d, '2024-12-31')).toBe(0)
    expect(dayIndexOnOrAfter(d, '2025-01-07')).toBeNull()
  })
})

describe('默认聚焦本身(对照)', () => {
  it('进 compare、app 跑完:没有待落的那天时,当前日落在离图窗中心最近的样本', async () => {
    const { view, cmp, w } = await setup('AAA')
    expect(view.mode).toBe('compare')
    expect(cmp.focusedSampleId).toBe('s-AAA')
    expect(view.currentDay).toBe(SAMPLE_DAY)
    w.unmount()
  })
})

describe('落在 compare 的链接', () => {
  it('页面打开就带着链接:落在 compare,竖线停在那天,不挑样本', async () => {
    const { view, cmp, w } = await setup(null)
    await useDirectLinkStore().follow('#symbol=aaa&date=2025-01-20&pattern=p&mode=compare')
    await settle()
    expect([view.mode, view.symbol]).toEqual(['compare', 'AAA'])
    expect(view.currentDay).toBe(19)
    expect(cmp.focusedSampleId).toBeNull()
    w.unmount()
  })

  it('那天晚于最后一根 K 线:不画竖线(也不挑样本)', async () => {
    const { view, cmp, w } = await setup('AAA')
    useLandingStore().land('AAA', { start: '2024-07-01', end: '2025-03-01' }, '2025-02-15')
    await settle()
    expect(view.currentDay).toBeNull()
    expect(cmp.focusedSampleId).toBeNull()
    w.unmount()
  })
})

describe('侧栏 feedback 页点一行', () => {
  it('换到另一只股票:现算结果后到 / K 线后到,竖线都停在范围起点,选中那条;落下后之后的默认聚焦照旧挑样本', async () => {
    for (const late of ['preview', 'bars'] as const) {
      setActivePinia(createPinia())
      fake.read = annRead()
      const { view, cmp, fb, w } = await setup('AAA')
      expect(view.currentDay).toBe(SAMPLE_DAY)
      const page = mount(FeedbackPage)
      await settle()
      let release!: () => void
      const gate = new Promise<void>(r => { release = r })
      if (late === 'preview') fake.previewGate = gate
      else fake.barsGate = gate
      await page.get('[data-testid="feedback-row"][data-id="f-pc-1"]').trigger('click')
      await settle()
      expect([view.mode, view.symbol], late).toEqual(['compare', 'BBB'])
      release()
      fake.previewGate = null
      fake.barsGate = null
      await settle()
      expect(view.currentDay, late).toBe(20)
      expect(cmp.focusedSampleId, late).toBeNull()
      expect(fb.selectedId, late).toBe('f-pc-1')
      // 已经消费掉:同一只股票换个图窗(K 线重读),默认聚焦照旧挑样本
      view.openSymbol('BBB', { start: '2024-07-01', end: '2025-03-01' })
      await settle()
      expect(view.currentDay, late).toBe(SAMPLE_DAY)
      page.unmount()
      w.unmount()
      useFeedbackStore().$dispose()
    }
  })

  it('同一只股票:不换股票,K 线按新图窗重读后竖线停在范围起点', async () => {
    fake.read.state.charts[0].feedback = [{ id: 'f-pc-2', pattern: 'p', app_id: 'app1', app_ver: 'v0',
      start: DATES[12], end: DATES[14], target: 'range', source: 'picked', answer: 'neg', note: 'why' }]
    const { view, w } = await setup('AAA')
    const page = mount(FeedbackPage)
    await settle()
    await page.get('[data-testid="feedback-row"][data-id="f-pc-2"]').trigger('click')
    await settle()
    expect([view.symbol, view.currentDay]).toEqual(['AAA', 12])
    page.unmount()
    w.unmount()
  })
})

describe('默认聚焦不会发生 / 作废', () => {
  it('app 没跑成:K 线一到,landing 自己把竖线落在那天', async () => {
    const { view, appLink, w } = await setup('AAA')
    fake.previewFails = true
    useLandingStore().land('BBB', { start: '2024-07-01', end: '2025-03-01' }, DATES[7])
    await settle()
    expect(appLink.runStatus).toBe('load_failed')
    expect([view.mode, view.symbol, view.currentDay]).toEqual(['compare', 'BBB', 7])
    w.unmount()
  })

  it('落下之前换了股票:作废,新股票照旧默认聚焦', async () => {
    const { view, w } = await setup('AAA')
    let release!: () => void
    fake.barsGate = new Promise<void>(r => { release = r })
    useLandingStore().land('BBB', { start: '2024-07-01', end: '2025-03-01' }, DATES[7])
    await settle()
    view.openSymbol('AAA')
    fake.barsGate = null
    release()
    await settle()
    expect(view.symbol).toBe('AAA')
    expect(view.currentDay).toBe(SAMPLE_DAY)
    expect(useLandingStore().claim()).toBe(false)
    w.unmount()
  })
})
