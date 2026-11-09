// feedback store:状态的重取时机(进 compare、换 pattern、存删反馈后、app 重跑、窗口拿到焦点;只认最后一次)
// 与作答面板(查重、打开已有的、草稿、保存、redraw、自动关)、面板派生量(pos sample inside、分段按钮)。
// 后端换成内存里的假实现(同 stores.annotation.spec.ts);别的读请求一律挂起。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnOp, AnnRead, AnnState } from '../src/annotate/model'
import type { EventDict, FeedbackStatusResp, HitDict } from '../src/types'

const fake = vi.hoisted(() => ({
  read: null as any,
  batches: [] as any[],
  n: 0,
  calls: [] as string[],
  // 下一次状态请求的回答;给了 gate 就等它放行再回
  answer: null as any,
  gate: null as Promise<void> | null,
}))

vi.mock('../src/api', async (orig) => {
  const m: Record<string, any> = await orig()
  const model = await vi.importActual<typeof import('../src/annotate/model')>('../src/annotate/model')
  const out: Record<string, any> = Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' && /^[a-z]/.test(k) ? vi.fn(() => new Promise(() => {})) : v]))
  return {
    ...out,
    getAnnotations: async () => structuredClone(fake.read),
    postAnnotationBatch: async (ops: AnnOp[]) => {
      fake.batches.push(structuredClone(ops))
      const stem = `pc-batch-${++fake.n}`
      const next = model.applyOps(fake.read, ops)
      const revs = structuredClone(fake.read.revs)
      ops.forEach((op, i) => { revs[op.kind][op.id] = `${stem}#${i}` })
      fake.read = { ...next, revs }
      return { file: `${stem}.json`, ...structuredClone(fake.read) }
    },
    getFeedbackStatus: async (pattern: string): Promise<FeedbackStatusResp> => {
      fake.calls.push(pattern)
      const answer = fake.answer ?? { app: 'app1', app_ver: 'v1', items: [], reason: null }
      const gate = fake.gate
      if (gate) await gate
      return structuredClone(answer)
    },
  }
})

import { useAnnotationStore } from '../src/stores/annotation'
import { useViewStore } from '../src/stores/view'
import { useFeedbackStore } from '../src/stores/feedback'

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09', '2025-01-10']

// plateau 容器引用 step(其下还有孙 node step_seg)/ today;买点 node = plateau.today,第 4、5、6 根买
const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
const S2 = ev('step', 2, 2), T4 = ev('today', 4, 4), T6 = ev('today', 5, 6)
const P4 = ev('plateau', 0, 4, 0, { step: [S2.instance_id], today: [T4.instance_id] })
const P6 = ev('plateau', 0, 6, 0, { step: [S2.instance_id], today: [T6.instance_id] })
const hit = (id: string, p: EventDict): HitDict =>
  ({ hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id }, children: [] })

const run = (symbol = 'AAA') => ({
  symbol, app: 'app1',
  analysis: { events: [S2, T4, T6, P4, P6], hits: [hit('h4', P4), hit('h6', P6)] },
  pattern_spec: { pattern_id: 'app1', event_styles: {}, debug_enabled_nodes: [], topology: { edges: [], nodes: [
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'step', where_rules: [], parent_refs: [['plateau', 'step']] },
    { node_id: 'step_seg', where_rules: [], parent_refs: [['step', 'seg']] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
    { node_id: 'other', where_rules: [] },
  ] } },
  scan: { end_node: 'plateau.today', app_ver: 'v1' } as any,
}) as any

const fbRec = (id: string, extra: Record<string, unknown> = {}) => ({
  id, pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-08', end: '2025-01-09', target: 'family',
  source: 'picked', answer: 'off_pattern', segments: ['step'], family_start: '2025-01-02', ...extra }) as any

function annRead(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }, { name: 'q' }], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}

/** 标注读好、当前 pattern 为 p、AAA 已打开(还在 annotate);feedback store 已建。 */
async function setup(read: AnnRead = annRead()) {
  fake.read = read
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const view = useViewStore()
  view.symbol = 'AAA'
  view.barDates = DATES
  const fb = useFeedbackStore()
  await settle()
  return { ann, view, fb }
}

/** 进 compare,放进 AAA 的现算结果(appLink 跑 app 的那一步由测试直接做)。 */
async function enterCompare(view: ReturnType<typeof useViewStore>) {
  view.mode = 'compare'
  await nextTick()
  view.setLinkedRun(run())
  await settle()
}

async function settle() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0))
}

const AT = { x: 100, y: 200 }

beforeEach(() => {
  setActivePinia(createPinia())
  fake.batches = []
  fake.n = 0
  fake.calls = []
  fake.answer = null
  fake.gate = null
  localStorage.clear()
})
// 每个用例的 store 用完拆掉:它挂在 window 上的 focus 监听一并拿掉,不让上一个用例的 store 跟着去取
afterEach(() => { useFeedbackStore().$dispose() })

describe('状态的重取时机', () => {
  it('annotate 下不取;进 compare 取当前 pattern 的,照接口存 status、tag、red', async () => {
    const { view, fb } = await setup()
    expect(fake.calls).toEqual([])
    fake.answer = { app: 'app1', app_ver: 'v1', reason: null,
      items: [{ id: 'f-pc-1', status: 'matched', tag: 'for_tuning', red: true, reason: null }] }
    await enterCompare(view)
    expect(fake.calls.length).toBeGreaterThanOrEqual(1)
    expect(fake.calls.every(p => p === 'p')).toBe(true)
    expect(fb.statusById).toEqual({ 'f-pc-1': { status: 'matched', tag: 'for_tuning', red: true, reason: null } })
    expect([fb.app, fb.appVer, fb.loading]).toEqual(['app1', 'v1', false])
  })

  it('store 建起来时已在 compare:马上取一次', async () => {
    fake.read = annRead()
    const ann = useAnnotationStore()
    await ann.load()
    ann.setCurrentPattern('p')
    const view = useViewStore()
    view.symbol = 'AAA'
    view.mode = 'compare'
    useFeedbackStore()
    await settle()
    expect(fake.calls).toEqual(['p'])
  })

  it('换 pattern、app 重跑、窗口拿到焦点都重取;app 重跑开始时清掉旧结果那一下不取', async () => {
    const { ann, view } = await setup()
    await enterCompare(view)
    let n = fake.calls.length
    ann.setCurrentPattern('q')
    await settle()
    expect(fake.calls.slice(n)).toEqual(['q'])
    n = fake.calls.length
    view.setLinkedRun(null)
    await settle()
    expect(fake.calls.length).toBe(n)
    view.setLinkedRun(run())
    await settle()
    expect(fake.calls.slice(n)).toEqual(['q'])
    n = fake.calls.length
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(fake.calls.slice(n)).toEqual(['q'])
    view.mode = 'annotate'
    await settle()
    n = fake.calls.length
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(fake.calls.length).toBe(n)                // 不在 compare 不取
  })

  it('几处同时触发只取一次;连着取时只认最后一次的结果', async () => {
    const { ann, view, fb } = await setup()
    await enterCompare(view)
    const n = fake.calls.length
    ann.setCurrentPattern('q')
    view.setLinkedRun(run())
    window.dispatchEvent(new Event('focus'))
    await settle()
    expect(fake.calls.length).toBe(n + 1)

    let release!: () => void
    fake.gate = new Promise<void>(r => { release = r })
    fake.answer = { app: 'app1', app_ver: 'v1', reason: null, items: [{ id: 'old', status: 'lost', tag: null, red: false, reason: null }] }
    const first = fb.refresh()
    fake.gate = null
    fake.answer = { app: 'app1', app_ver: 'v2', reason: null, items: [{ id: 'new', status: 'unmatched', tag: null, red: false, reason: null }] }
    await fb.refresh()
    release()
    await first
    expect(Object.keys(fb.statusById)).toEqual(['new'])
    expect(fb.appVer).toBe('v2')
    expect(fb.loading).toBe(false)
  })

  it('存进、删出反馈之后重取(等还没存完的都存完)', async () => {
    const { ann, view, fb } = await setup()
    await enterCompare(view)
    let n = fake.calls.length
    expect(fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })).toBe(true)
    fb.setAnswer('neg')
    fb.setNote('太晚')
    expect(fb.save()).toBe(true)
    expect(fb.panel).toBeNull()
    await ann.flushed()
    await vi.waitFor(() => expect(fake.calls.length).toBe(n + 1))
    expect(fake.batches.at(-1)[0]).toMatchObject({ kind: 'feedback', id: 'f-pc-10', base: null,
      value: { symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', target: 'point', answer: 'neg', note: '太晚' } })
    n = fake.calls.length
    fb.select('f-pc-10')
    fb.remove('f-pc-10')
    expect(fb.selectedId).toBeNull()
    await ann.flushed()
    await vi.waitFor(() => expect(fake.calls.length).toBe(n + 1))
    expect(fake.batches.at(-1)).toEqual([{ kind: 'feedback', id: 'f-pc-10', base: 'pc-batch-1#0', value: null }])
  })
})

describe('作答面板', () => {
  const twoRecords = () => annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [
    { id: 's-pc-1', date: '2025-01-09', pattern: 'p', judgment: 'pos', members: [] },
  ], feedback: [
    fbRec('f-pc-1'),
    fbRec('f-pc-2', { source: 'random', target: 'point', start: '2025-01-10', end: '2025-01-10', answer: 'pos',
                      segments: undefined, family_start: undefined }),
  ] }] })

  it('不在 compare 不开;新范围开空白草稿,family 带起点', async () => {
    const { view, fb } = await setup()
    expect(fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })).toBe(false)
    await enterCompare(view)
    expect(fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'family', family_start: '2025-01-02' })).toBe(true)
    expect(fb.panel).toEqual({ x: 100, y: 200, symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'family',
                               family_start: '2025-01-02', note: '', segments: [] })
    expect(fb.problems).toEqual(['answer'])
  })

  it('同范围已有反馈:直接打开那条(预填);点记号按编号打开;盲看标记、别的 pattern 的不开', async () => {
    const { ann, view, fb } = await setup(twoRecords())
    await enterCompare(view)
    expect(fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })).toBe(true)
    expect(fb.panel).toEqual({ x: 100, y: 200, symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'family',
      family_start: '2025-01-02', editingId: 'f-pc-1', answer: 'off_pattern', note: '', segments: ['step'] })
    fb.close()
    expect(fb.open({ x: 1, y: 2 }, { id: 'f-pc-1' })).toBe(true)
    expect(fb.panel?.editingId).toBe('f-pc-1')
    expect(fb.switchTo(AT, { id: 'f-pc-2' })).toBe(false)
    expect(fb.open(AT, { symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' })).toBe(true)
    expect(fb.panel?.editingId).toBeUndefined()
    fb.close()
    ann.setCurrentPattern('q')
    expect(fb.open(AT, { id: 'f-pc-1' })).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('草稿:切到 neg 清掉分段;分段可多选、再点拿掉;保存条件没满足时不存', async () => {
    const { view, fb } = await setup()
    await enterCompare(view)
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })
    fb.setAnswer('off_pattern')
    expect(fb.problems).toEqual(['segments_or_note'])
    expect(fb.save()).toBe(false)
    fb.toggleSegment('step')
    fb.toggleSegment('today')
    fb.toggleSegment('step')
    expect(fb.panel?.segments).toEqual(['today'])
    expect(fb.problems).toEqual([])
    fb.setAnswer('neg')
    expect(fb.panel?.segments).toEqual([])
    expect(fb.problems).toEqual(['note'])
    expect(fb.save()).toBe(false)
    expect(fb.panel).not.toBeNull()
  })

  it('redraw:答案、理由、分段带进下一次拖选;保存时同编号覆盖,target 改 range、去掉 family_start', async () => {
    const r = twoRecords()
    r.revs.feedback = { 'f-pc-1': 'pc-batch-0#0' }
    const { ann, view, fb } = await setup(r)
    await enterCompare(view)
    fb.open(AT, { id: 'f-pc-1' })
    fb.setNote('不像')
    expect(fb.startRedraw()).toBe(true)
    expect(fb.panel).toBeNull()
    expect(fb.carry).toEqual({ editingId: 'f-pc-1', answer: 'off_pattern', note: '不像', segments: ['step'] })
    // 拖选之前点 ▼ 开的面板不用 carry
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    expect(fb.panel?.editingId).toBeUndefined()
    expect(fb.carry).not.toBeNull()
    fb.open({ x: 5, y: 6 }, { symbol: 'AAA', start: '2025-01-07', end: '2025-01-10', target: 'range' })
    expect(fb.carry).toBeNull()
    expect(fb.panel).toMatchObject({ x: 5, y: 6, target: 'range', editingId: 'f-pc-1', answer: 'off_pattern',
                                     note: '不像', segments: ['step'], carry: true })
    expect(fb.panel).not.toHaveProperty('family_start')
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'pc-batch-0#0', value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-07', end: '2025-01-10',
      target: 'range', source: 'picked', answer: 'off_pattern', note: '不像', segments: ['step'] } }]])
  })

  it('换股票、换模式关面板并放弃 redraw;app 重跑关面板', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    fb.open(AT, { id: 'f-pc-1' })
    fb.startRedraw()
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.symbol = 'BBB'
    await nextTick()
    expect([fb.panel, fb.carry]).toEqual([null, null])
    view.symbol = 'AAA'
    await nextTick()
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.setLinkedRun(run())
    await nextTick()
    expect(fb.panel).toBeNull()
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.mode = 'app'
    await nextTick()
    expect(fb.panel).toBeNull()
  })

  it('redraw 带来的东西只在 feedback 工具亮着时留着:工具以任何方式熄灭(Esc、再点、换成别的工具)都放弃', async () => {
    const { ann, view, fb } = await setup(twoRecords())
    await enterCompare(view)
    const redraw = async () => {
      fb.open(AT, { id: 'f-pc-1' })
      fb.startRedraw()
      ann.tool = 'feedback'
      await nextTick()
      expect(fb.carry?.editingId).toBe('f-pc-1')
    }
    await redraw()
    ann.tool = null
    await nextTick()
    expect(fb.carry).toBeNull()
    await redraw()
    ann.toggleTool('box')
    await nextTick()
    expect(fb.carry).toBeNull()
    // 拖完一次:先熄工具、再在同一段代码里 open,carry 被 open 用掉(watch 晚一步,不抢先清)
    await redraw()
    ann.tool = null
    fb.open(AT, { symbol: 'AAA', start: '2025-01-07', end: '2025-01-10', target: 'range' })
    await nextTick()
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', carry: true })
  })

  it('opens:每打开一次加一(含关旧开新、打开已有的);没打开成不加', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    const n = fb.opens
    fb.open(AT, { symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' })
    fb.open(AT, { id: 'f-pc-1' })
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })   // 同范围:打开那条
    expect(fb.opens).toBe(n + 3)
    fb.open(AT, { id: 'f-pc-2' })                                                              // 盲看标记:不开
    expect(fb.opens).toBe(n + 3)
  })

  it('派生量:范围里的正样本;分段按钮取范围里买的 hit 绑定的 node 及子孙 node,已选的旧 node 留在最后', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    fb.open(AT, { symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    expect(fb.panelPosInside).toBe(false)
    expect(fb.panelSegments).toEqual(['plateau', 'step', 'step_seg', 'today'])
    fb.open(AT, { symbol: 'AAA', start: '2025-01-09', end: '2025-01-10', target: 'range' })
    expect(fb.panelPosInside).toBe(true)
    fb.toggleSegment('gone')
    expect(fb.panelSegments).toEqual(['plateau', 'step', 'step_seg', 'today', 'gone'])
    fb.open(AT, { symbol: 'AAA', start: '2025-01-02', end: '2025-01-07', target: 'range' })
    expect(fb.panelSegments).toEqual([])
  })
})
