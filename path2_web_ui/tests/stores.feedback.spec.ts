// feedback store:状态的重取时机(进 compare、换 pattern、存删反馈后、app 重跑、窗口拿到焦点;只认最后一次)
// 与作答面板(查重、打开已有的、草稿、保存、自动关)、拖竖带边改起止(resize)、面板派生量(pos sample inside、node 按钮)。
// 面板没有「先选答案」:只点 node / 写 note;存出去的值不带 answer、不带 dag。以前存下的带这两个键的记录
// (fbRec 默认就是这种:off_pattern + node、没写 note)照样打得开、能被挑去共享,保存后改写成不带这两个键的形状。
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
  source: 'picked', answer: 'off_pattern', nodes: ['step'], family_start: '2025-01-02', ...extra }) as any

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
    fake.answer = { app: 'app1', app_ver: 'v1', reason: null, items: [{ id: 'old', status: 'unmatched', tag: null, red: false, reason: null }] }
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
    expect(fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })).toBe(true)
    fb.setNote('太晚')
    expect(fb.save()).toBe(true)
    expect(fb.panel).toBeNull()
    await ann.flushed()
    await vi.waitFor(() => expect(fake.calls.length).toBe(n + 1))
    expect(fake.batches.at(-1)[0]).toEqual({ kind: 'feedback', id: 'f-pc-10', base: null,
      value: { id: 'f-pc-10', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-08',
               end: '2025-01-08', target: 'point', source: 'picked', note: '太晚' } })
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
                      nodes: undefined, family_start: undefined }),
  ] }] })

  it('不在 compare 不开;新范围开空白草稿,family 带起点', async () => {
    const { view, fb } = await setup()
    expect(fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })).toBe(false)
    await enterCompare(view)
    expect(fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'family', family_start: '2025-01-02' })).toBe(true)
    expect(fb.panel).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'family',
                               family_start: '2025-01-02', note: '', nodes: [] })
    expect(fb.problems).toEqual(['note'])
    expect(fb.panelIssues).toEqual([])                  // 还没有别的反馈:没有可挑的
  })

  it('同范围已有反馈:直接打开那条(预填);点记号按编号打开;盲看标记、别的 pattern 的不开', async () => {
    const { ann, view, fb } = await setup(twoRecords())
    await enterCompare(view)
    expect(fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })).toBe(true)
    expect(fb.panel).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'family',
      family_start: '2025-01-02', editingId: 'f-pc-1', note: '', nodes: ['step'], link: 'f-pc-1' })
    fb.close()
    expect(fb.open({ id: 'f-pc-1' })).toBe(true)
    expect(fb.panel?.editingId).toBe('f-pc-1')
    expect(fb.switchTo({ id: 'f-pc-2' })).toBe(false)
    expect(fb.open({ symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' })).toBe(true)
    expect(fb.panel?.editingId).toBeUndefined()
    fb.close()
    ann.setCurrentPattern('q')
    expect(fb.open({ id: 'f-pc-1' })).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('草稿:一打开就能点 node、写 note;node 可多选、再点拿掉;只点 node 不写 note 存不了;只写 note 就能存', async () => {
    const { ann, view, fb } = await setup()
    await enterCompare(view)
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })
    expect(fb.problems).toEqual(['note'])
    expect(fb.save()).toBe(false)
    fb.toggleNode('step')
    fb.toggleNode('today')
    fb.toggleNode('step')
    expect(fb.panel?.nodes).toEqual(['today'])
    expect(fb.problems).toEqual(['note'])               // 只点 node 不够
    expect(fb.save()).toBe(false)
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    fb.setNote('   ')
    expect(fb.problems).toEqual(['note'])
    fb.toggleNode('today')                              // 一个 node 都不点
    fb.setNote(' 不像 ')
    expect(fb.problems).toEqual([])
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-10', base: null, value: {
      id: 'f-pc-10', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-08', end: '2025-01-09',
      target: 'range', source: 'picked', note: '不像' } }]])
    // 点了 node 再写 note:值里带 nodes,照旧没有 answer、dag
    fb.open({ symbol: 'AAA', start: '2025-01-09', end: '2025-01-10', target: 'range' })
    fb.toggleNode('step')
    fb.toggleNode('plateau')
    fb.setNote('阶跃太小')
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches[1][0].value).toMatchObject({ note: '阶跃太小', nodes: ['step', 'plateau'] })
    expect(Object.keys(fake.batches[1][0].value)).toEqual(
      ['id', 'symbol', 'pattern', 'app_id', 'app_ver', 'start', 'end', 'target', 'source', 'note', 'nodes'])
  })

  describe('以前存下的带 answer 的记录', () => {
    // f-pc-1:neg + note;f-pc-2:off_pattern + node、没写 note;f-pc-3:off_pattern + node + dag + note
    const olds = () => {
      const r = annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
        fbRec('f-pc-1', { target: 'point', start: '2025-01-08', end: '2025-01-08', answer: 'neg', note: '追高',
                          nodes: undefined, family_start: undefined }),
        fbRec('f-pc-2', { target: 'point', start: '2025-01-09', end: '2025-01-09', family_start: undefined }),
        fbRec('f-pc-3', { target: 'point', start: '2025-01-10', end: '2025-01-10', family_start: undefined,
                          note: '关系不对', dag: true }),
      ] }] })
      r.revs.feedback = { 'f-pc-1': 'r1', 'f-pc-2': 'r2', 'f-pc-3': 'r3' }
      return r
    }
    const KEYS = ['id', 'symbol', 'pattern', 'app_id', 'app_ver', 'start', 'end', 'target', 'source']

    it('neg + note:预填理由;什么都没改按保存也写一条,值里没有 answer', async () => {
      const { ann, view, fb } = await setup(olds())
      await enterCompare(view)
      expect(fb.open({ id: 'f-pc-1' })).toBe(true)
      expect(fb.panel).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point',
                                 editingId: 'f-pc-1', note: '追高', nodes: [], link: 'f-pc-1' })
      expect(fb.problems).toEqual([])
      expect(fb.save()).toBe(true)
      await ann.flushed()
      expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'r1', value: {
        id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-08', end: '2025-01-08',
        target: 'point', source: 'picked', note: '追高' } }]])
    })

    it('off_pattern + node、没写 note:预填 node;不补 note 存不了,补了才存,值里没有 answer', async () => {
      const { ann, view, fb } = await setup(olds())
      await enterCompare(view)
      fb.open({ id: 'f-pc-2' })
      expect(fb.panel).toMatchObject({ editingId: 'f-pc-2', note: '', nodes: ['step'] })
      expect(fb.problems).toEqual(['note'])
      expect(fb.save()).toBe(false)
      expect(fake.batches).toEqual([])
      fb.setNote('阶跃不算数')
      expect(fb.save()).toBe(true)
      await ann.flushed()
      expect(fake.batches[0][0].value).toMatchObject({ id: 'f-pc-2', note: '阶跃不算数', nodes: ['step'] })
      expect(Object.keys(fake.batches[0][0].value)).toEqual([...KEYS, 'note', 'nodes'])
    })

    it('off_pattern + node + dag + note:预填 node 与理由,面板上没有 dag;保存后值里没有 answer、没有 dag', async () => {
      const { ann, view, fb } = await setup(olds())
      await enterCompare(view)
      fb.open({ id: 'f-pc-3' })
      expect(fb.panel).toMatchObject({ editingId: 'f-pc-3', note: '关系不对', nodes: ['step'] })
      expect(fb.panel).not.toHaveProperty('dag')
      expect(fb.panel).not.toHaveProperty('answer')
      expect(fb.save()).toBe(true)
      await ann.flushed()
      expect(fake.batches[0][0].value).toEqual({ id: 'f-pc-3', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1',
        start: '2025-01-10', end: '2025-01-10', target: 'point', source: 'picked', note: '关系不对', nodes: ['step'] })
      // 存完再打开:读回来的那条已经没有这两个键
      const back = ann.state!.charts[0].feedback!.find(f => f.id === 'f-pc-3')!
      expect('answer' in back).toBe(false)
      expect('dag' in back).toBe(false)
    })

    it('resize 写了 note 的:直接存,同编号覆盖成不带 answer、dag 的 range', async () => {
      const { ann, view, fb } = await setup(olds())
      await enterCompare(view)
      expect(fb.resize('f-pc-3', '2025-01-07', '2025-01-10')).toBe('saved')
      expect(fb.panel).toBeNull()
      await ann.flushed()
      expect(fake.batches[0][0]).toMatchObject({ id: 'f-pc-3', base: 'r3' })
      expect(fake.batches[0][0].value).toEqual({ id: 'f-pc-3', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1',
        start: '2025-01-07', end: '2025-01-10', target: 'range', source: 'picked', note: '关系不对', nodes: ['step'] })
    })

    it('resize 没写 note 的:存不了,在松开处打开它的面板、范围换成新的;补了 note 才存', async () => {
      const { ann, view, fb } = await setup(olds())
      await enterCompare(view)
      expect(fb.resize('f-pc-2', '2025-01-08', '2025-01-10')).toBe('panel')
      expect(fake.batches).toEqual([])
      expect(fb.panel).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'range',
                                 editingId: 'f-pc-2', note: '', nodes: ['step'], link: 'f-pc-2' })
      expect(fb.problems).toEqual(['note'])
      fb.setNote('阶跃不算数')
      expect(fb.save()).toBe(true)
      await ann.flushed()
      expect(fake.batches[0][0].value).toMatchObject({ id: 'f-pc-2', start: '2025-01-08', end: '2025-01-10',
                                                       target: 'range', note: '阶跃不算数', nodes: ['step'] })
      expect(Object.keys(fake.batches[0][0].value)).toEqual([...KEYS, 'note', 'nodes'])
    })
  })

  it('edit 的请求:提了由图表接下并消费掉;换股票作废', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    expect(fb.takeEditRequest()).toBeNull()
    fb.requestEdit('f-pc-1')
    expect(fb.editRequest).toBe('f-pc-1')
    expect(fb.takeEditRequest()).toBe('f-pc-1')
    expect(fb.editRequest).toBeNull()
    fb.requestEdit('f-pc-1')
    view.symbol = 'BBB'
    await nextTick()
    expect(fb.editRequest).toBeNull()
  })

  it('resize:note、node 不变,同编号覆盖,target 改 range、去掉 family_start;面板正开着这一条时关掉、草稿不存', async () => {
    const r = twoRecords()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], note: '不像' }
    r.revs.feedback = { 'f-pc-1': 'pc-batch-0#0' }
    const { ann, view, fb } = await setup(r)
    await enterCompare(view)
    fb.open({ id: 'f-pc-1' })
    fb.setNote('草稿里改的字')
    expect(fb.resize('f-pc-1', '2025-01-07', '2025-01-10')).toBe('saved')
    expect(fb.panel).toBeNull()
    await ann.flushed()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'pc-batch-0#0', value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-07', end: '2025-01-10',
      target: 'range', source: 'picked', note: '不像', nodes: ['step'] } }]])
  })

  it('resize 不存的情形:和另一条同范围(same);不在 compare、盲看标记、别的 pattern 的、找不到的(null)', async () => {
    const r = twoRecords()
    r.state.charts[0].feedback!.push(fbRec('f-pc-3', { target: 'point', start: '2025-01-07', end: '2025-01-07',
                                                       note: '太早', family_start: undefined }))
    const { ann, view, fb } = await setup(r)
    expect(fb.resize('f-pc-3', '2025-01-07', '2025-01-08')).toBeNull()        // 还在 annotate
    await enterCompare(view)
    expect(fb.resize('f-pc-3', '2025-01-08', '2025-01-09')).toBe('same')      // f-pc-1 就是这一段
    expect(fb.resize('f-pc-2', '2025-01-09', '2025-01-10')).toBeNull()        // 盲看标记
    expect(fb.resize('f-pc-9', '2025-01-09', '2025-01-10')).toBeNull()
    ann.setCurrentPattern('q')
    expect(fb.resize('f-pc-3', '2025-01-07', '2025-01-08')).toBeNull()
    await ann.flushed()
    expect(fake.batches).toEqual([])
    expect(fb.panel).toBeNull()
  })

  it('换股票、换模式关面板;app 重跑关面板', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.symbol = 'BBB'
    await nextTick()
    expect(fb.panel).toBeNull()
    view.symbol = 'AAA'
    await nextTick()
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.setLinkedRun(run())
    await nextTick()
    expect(fb.panel).toBeNull()
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    view.mode = 'app'
    await nextTick()
    expect(fb.panel).toBeNull()
  })

  it('opens:每打开一次加一(含关旧开新、打开已有的);没打开成不加', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    const n = fb.opens
    fb.open({ symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' })
    fb.open({ id: 'f-pc-1' })
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-09', target: 'range' })   // 同范围:打开那条
    expect(fb.opens).toBe(n + 3)
    fb.open({ id: 'f-pc-2' })                                                              // 盲看标记:不开
    expect(fb.opens).toBe(n + 3)
  })

  it('派生量:范围里的正样本;node 按钮取范围里买的 hit 绑定的 node 及子孙 node,已选的旧 node 留在最后', async () => {
    const { view, fb } = await setup(twoRecords())
    await enterCompare(view)
    fb.open({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    expect(fb.panelPosInside).toBe(false)
    expect(fb.panelNodes).toEqual(['plateau', 'step', 'step_seg', 'today'])
    fb.open({ symbol: 'AAA', start: '2025-01-09', end: '2025-01-10', target: 'range' })
    expect(fb.panelPosInside).toBe(true)
    fb.toggleNode('gone')
    expect(fb.panelNodes).toEqual(['plateau', 'step', 'step_seg', 'today', 'gone'])
    fb.open({ symbol: 'AAA', start: '2025-01-02', end: '2025-01-07', target: 'range' })
    expect(fb.panelNodes).toEqual([])
  })
})

describe('选中的那一个能不能作答(selTarget)与对它打开(openSelected)', () => {
  // 夹具:h4 买在第 4 根(2025-01-08)、h6 买在第 5、6 根(01-09、01-10),两次 hit 起点都是第 0 根(同一族 hits@0)
  const FAM = 'hits@0'
  const withRecords = () => annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
    fbRec('f-pc-1', { note: '不像' }),                                                    // 当前 pattern、用户自己挑的
    fbRec('f-pc-2', { source: 'random', target: 'point', start: '2025-01-10', end: '2025-01-10', answer: 'pos',
                      nodes: undefined, family_start: undefined }),                      // 盲看标记
    fbRec('f-pc-3', { pattern: 'q', target: 'point', start: '2025-01-09', end: '2025-01-09', family_start: undefined }),
  ] }] })

  it('没选中、不在 compare:null;openSelected 不开', async () => {
    const { view, fb } = await setup(withRecords())
    view.clickBuyDay(FAM, 4)
    expect(fb.selTarget).toBeNull()                     // 还在 annotate
    expect(fb.openSelected()).toBe(false)
    await enterCompare(view)
    view.setPath([])
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('买点日 → 那一天的 point;openSelected 打开它', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.clickBuyDay(FAM, 4)
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
    const n = fb.opens
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point', note: '', nodes: [] })
    expect(fb.opens).toBe(n + 1)
  })

  it('买点日上的一次 hit → 那一天;day 不是这次 hit 的买点日(从样本、框走进去的那次)→ null', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.setPath([{ kind: 'hit_family', familyKey: FAM }, { kind: 'buy', day: 6 }, { kind: 'hit', hitId: 'h6', day: 6 }])
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' })
    view.setPath([{ kind: 'sample', sampleId: 's-pc-1' }, { kind: 'hit', hitId: 'h6', day: 4 }])
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    expect(fb.panel).toBeNull()
    view.setPath([{ kind: 'sample', sampleId: 's-pc-1' }, { kind: 'hit', hitId: 'h4', day: 4 }])
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-08', target: 'point' })
  })

  it('一族 → family:范围是全部买点日的最早到最晚,另带族起点', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.clickFamilyLine(FAM)
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'family',
                                   family_start: '2025-01-02' })
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ start: '2025-01-08', end: '2025-01-10', target: 'family', family_start: '2025-01-02' })
    expect(fb.panel?.editingId).toBeUndefined()
  })

  it('一族的范围和已有的一条相同:openSelected 打开那条(防重复)', async () => {
    const r = withRecords()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], end: '2025-01-10' }
    const { view, fb } = await setup(r)
    await enterCompare(view)
    view.clickFamilyLine(FAM)
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel?.editingId).toBe('f-pc-1')
  })

  it('一条反馈:这张图当前 pattern 用户自己挑的 → {id},打开那条;盲看标记、别的 pattern 的 → null', async () => {
    const { ann, view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.clickFeedback({ id: 'f-pc-1' })
    expect(fb.selTarget).toEqual({ id: 'f-pc-1' })
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', note: '不像', nodes: ['step'] })
    fb.close()
    view.clickFeedback({ id: 'f-pc-2' })
    expect(fb.selTarget).toBeNull()
    view.clickFeedback({ id: 'f-pc-3' })
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    view.clickFeedback({ id: 'f-pc-9' })                // 找不到的
    expect(fb.selTarget).toBeNull()
    // 换到 q:f-pc-3 成了当前 pattern 的,f-pc-1 不再是
    ann.setCurrentPattern('q')
    view.clickFeedback({ id: 'f-pc-3' })
    expect(fb.selTarget).toEqual({ id: 'f-pc-3' })
    view.clickFeedback({ id: 'f-pc-1' })
    expect(fb.selTarget).toBeNull()
  })

  it('event、node、样本、框:null', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.focusMark([T4.instance_id])
    expect(view.selLast?.kind).toBe('event')
    expect(fb.selTarget).toBeNull()
    view.selectNode('today')
    expect(view.selLast?.kind).toBe('node')
    expect(fb.selTarget).toBeNull()
    view.setPath([{ kind: 'sample', sampleId: 's-pc-1' }])
    expect(fb.selTarget).toBeNull()
    view.setPath([{ kind: 'box', boxId: 'b-pc-1' }])
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('反馈不在这张图上(别的股票上的、同 pattern 用户自己挑的那条):null', async () => {
    const r = withRecords()
    r.state.charts.push({ symbol: 'BBB', boxes: [], samples: [], feedback: [fbRec('f-pc-7', { note: '别处' })] })
    const { view, fb } = await setup(r)
    await enterCompare(view)
    view.clickFeedback({ id: 'f-pc-7' })
    expect(view.selLast).toEqual({ kind: 'feedback', id: 'f-pc-7' })
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    expect(fb.panel).toBeNull()
  })

  // 没有 ▼ 的族不发起反馈;point 只落在买点日上。买点日和画 ▼ 同一口径:hit 里解析不到买点 node 时没有买点日
  // (不退到 hit 的终点)。
  it('没有 ▼ 的族、没有买点日的那次 hit、没有 hit 在那天买的「买点日」:不能作答(null)', async () => {
    const { view, fb } = await setup(withRecords())
    view.mode = 'compare'
    await nextTick()
    // 两次 hit 都没有买点 node 的 event:hits 行上画不出 ▼
    const bare = (id: string, e: number): HitDict => ({ hit_id: id, start_idx: 0, end_idx: e, node_index: {}, children: [] })
    view.setLinkedRun({ ...run(), analysis: { events: [S2, T4, T6, P4, P6], hits: [bare('n4', 4), bare('n6', 6)] } })
    await settle()
    view.clickFamilyLine(FAM)
    expect(view.selLast).toEqual({ kind: 'hit_family', familyKey: FAM })
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    view.clickHitCell(FAM, ['n6'])
    expect(view.selLast?.kind).toBe('hit')
    expect(fb.selTarget).toBeNull()
    view.setPath([{ kind: 'hit_family', familyKey: FAM }, { kind: 'buy', day: 6 }])
    expect(fb.selTarget).toBeNull()
    expect(fb.openSelected()).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('买点日那一节:当天有 hit 买才给 point;路径上写着的日子没有 hit 在那天买时为 null', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.setPath([{ kind: 'hit_family', familyKey: FAM }, { kind: 'buy', day: 5 }])
    expect(fb.selTarget).toEqual({ symbol: 'AAA', start: '2025-01-09', end: '2025-01-09', target: 'point' })
    view.setPath([{ kind: 'hit_family', familyKey: FAM }, { kind: 'buy', day: 3 }])     // 第 3 根没有 hit 买
    expect(fb.selTarget).toBeNull()
    view.setPath([{ kind: 'hit_family', familyKey: FAM }, { kind: 'buy', day: 6 }, { kind: 'hit', hitId: 'h4', day: 6 }])
    expect(fb.selTarget).toBeNull()                     // h4 只在第 4 根买
  })

  it('只看路径最里面那一节:族里走到一次 hit 是 point,退回族又是 family', async () => {
    const { view, fb } = await setup(withRecords())
    await enterCompare(view)
    view.focusHit('h6', { day: 5 })
    expect(fb.selTarget).toMatchObject({ start: '2025-01-09', end: '2025-01-09', target: 'point' })
    view.clickFamilyLine(FAM)
    expect(fb.selTarget).toMatchObject({ target: 'family' })
  })
})

describe('对选中打开的面板,按键走动后的去留(按打开时路径上的反馈与族比)', () => {
  // 第 5 根有两次 hit 买(h5、h6),第 6 根只有 h6;X 是一段 range(第 3~6 根),Y 是第 5 根上的一条 point
  const T5 = ev('today', 5, 5)
  const P5 = ev('plateau', 0, 5, 0, { step: [S2.instance_id], today: [T5.instance_id] })
  const run3 = () => ({ ...run(), analysis: { events: [S2, T4, T5, T6, P4, P5, P6],
                                              hits: [hit('h4', P4), hit('h5', P5), hit('h6', P6)] } })
  const read = () => annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
    fbRec('f-pc-1', { target: 'range', start: '2025-01-07', end: '2025-01-10', note: 'X', nodes: undefined,
                      family_start: undefined, answer: undefined }),
    fbRec('f-pc-2', { target: 'point', start: '2025-01-09', end: '2025-01-09', note: 'Y', nodes: undefined,
                      family_start: undefined, answer: undefined }),
    // 以前存下的、没写 note 的一条(第 4 根):改起止存不了,要打开面板补 note
    fbRec('f-pc-3', { target: 'point', start: '2025-01-08', end: '2025-01-08', family_start: undefined }),
  ] }] })
  async function ready() {
    const r = await setup(read())
    r.view.mode = 'compare'
    await nextTick()
    r.view.setLinkedRun(run3())
    await settle()
    return r
  }

  it('路径 [反馈 X › 买点日 d],d 上已有反馈 Y:Enter 打开的是 Y;↓ 进同一天的某次 hit、再 ↓ 换一次,面板留着;→ 走出那一天就关', async () => {
    const { view, fb } = await ready()
    view.setPath([{ kind: 'feedback', id: 'f-pc-1' }, { kind: 'buy', day: 5 }])
    await nextTick()
    expect(fb.selectedId).toBe('f-pc-1')
    expect(fb.openSelected()).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-2', start: '2025-01-09', end: '2025-01-09' })   // 同范围防重复
    expect(view.stepStack(1)).toBe(true)
    await nextTick()
    expect(view.selPath.map(x => x.kind)).toEqual(['feedback', 'buy', 'hit'])
    expect(fb.panel?.editingId).toBe('f-pc-2')
    const first = view.selLast
    expect(view.stepStack(1)).toBe(true)
    await nextTick()
    expect(view.selLast).not.toEqual(first)
    expect(fb.panel?.editingId).toBe('f-pc-2')
    view.stepPos(1)
    await nextTick()
    expect(view.currentDay).toBe(6)
    expect(fb.panel).toBeNull()
  })

  it('改起止打开的面板(resize 得 panel)不沿用上一次 Enter 记下的来路:→ 进到它范围里的买点日,面板留着', async () => {
    const { view, fb } = await ready()
    view.setPath([{ kind: 'feedback', id: 'f-pc-1' }, { kind: 'buy', day: 5 }])
    expect(fb.openSelected()).toBe(true)                // 来路记成「路径上有反馈 X」
    fb.close()
    view.clickBuyDay('hits@0', 4)
    await nextTick()
    expect(fb.resize('f-pc-3', '2025-01-08', '2025-01-10')).toBe('panel')
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-3', start: '2025-01-08', end: '2025-01-10', target: 'range' })
    view.stepPos(1)
    await nextTick()
    expect(view.currentDay).toBe(5)
    expect(view.selPath.some(x => x.kind === 'feedback')).toBe(false)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-3' })
  })

  it('不经选中直接打开的(拖选、侧栏 edit):照旧按面板自己的那条反馈比,路径上换成别的反馈就关', async () => {
    const { view, fb } = await ready()
    view.setPath([{ kind: 'feedback', id: 'f-pc-1' }, { kind: 'buy', day: 5 }])
    expect(fb.open({ id: 'f-pc-2' })).toBe(true)
    view.stepStack(1)
    await nextTick()
    expect(view.selPath.map(x => x.kind)).toEqual(['feedback', 'buy', 'hit'])
    expect(fb.panel).toBeNull()
  })
})

describe('issue:几处反馈共享同一份内容', () => {
  // 全是以前存下的带 answer 的记录:AAA 上两条(f-pc-1 off_pattern [step]、没写 note;f-pc-3 neg「太晚」),
  // BBB 上两条共享 i-pc-4 的 neg(f-pc-5、f-pc-6「追高」),CCC 上一条别的 pattern 的带 i-pc-9
  const shared = () => {
    const r = annRead({ charts: [
      { symbol: 'AAA', boxes: [], samples: [], feedback: [
        fbRec('f-pc-1'),
        fbRec('f-pc-3', { target: 'point', start: '2025-01-07', end: '2025-01-07', answer: 'neg', note: '太晚',
                          nodes: undefined, family_start: undefined }),
      ] },
      { symbol: 'BBB', boxes: [], samples: [], feedback: [
        fbRec('f-pc-5', { target: 'point', start: '2025-01-06', end: '2025-01-06', answer: 'neg', note: '追高',
                          nodes: undefined, family_start: undefined, issue: 'i-pc-4' }),
        fbRec('f-pc-6', { target: 'point', start: '2025-01-08', end: '2025-01-08', answer: 'neg', note: '追高',
                          nodes: undefined, family_start: undefined, issue: 'i-pc-4' }),
      ] },
      { symbol: 'CCC', boxes: [], samples: [], feedback: [
        fbRec('f-pc-7', { pattern: 'q', target: 'point', start: '2025-01-06', end: '2025-01-06', answer: 'neg', note: 'x',
                          nodes: undefined, family_start: undefined, issue: 'i-pc-9' }),
      ] },
    ] })
    r.revs.feedback = { 'f-pc-1': 'r1', 'f-pc-3': 'r3', 'f-pc-5': 'r5', 'f-pc-6': 'r6', 'f-pc-7': 'r7' }
    return r
  }
  const POINT = { symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' as const }
  const ops = () => fake.batches.at(-1)!.map((o: any) => [o.id, o.base, o.value?.issue ?? null, o.value?.note ?? null])

  it('列表:一打开就有;当前 pattern 的各组不按答案筛,最近用过的在前;处数照组里的', async () => {
    const { view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    expect(fb.panelIssues.map(g => [g.key, g.issue, g.note, g.nodes, g.rows.length]))
      .toEqual([['i-pc-4', 'i-pc-4', '追高', [], 2], ['f-pc-3', null, '太晚', [], 1], ['f-pc-1', null, '', ['step'], 1]])
    expect(fb.panelIssue).toBeNull()                    // 新标一处:不连任何 issue
    expect(fb.placesById).toEqual({ 'f-pc-1': 1, 'f-pc-3': 1, 'f-pc-5': 2, 'f-pc-6': 2 })
  })

  it('新标一处挑一条已有 issue:内容填好,保存就带同一个 issue 值,别的处不动', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('i-pc-4')
    expect(fb.panel).toMatchObject({ note: '追高', nodes: [], link: 'i-pc-4' })
    expect(fb.panelIssue?.key).toBe('i-pc-4')
    expect([fb.panelNeedsChoice, fb.panelPlaces]).toEqual([false, 3])
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches).toHaveLength(1)
    expect(ops()).toEqual([['f-pc-10', null, 'i-pc-4', '追高']])
    expect(fake.batches[0][0].value).not.toHaveProperty('answer')            // 挑的是以前存下的 issue,存的这一处照样不带 answer
  })

  it('头一回共享一条还不带 issue 值的:现取一个值(同机器名最大序号加一,别的 pattern 的也算),同一批给原来那条补上', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('f-pc-3')
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches).toHaveLength(1)
    expect(ops()).toEqual([['f-pc-10', null, 'i-pc-10', '太晚'], ['f-pc-3', 'r3', 'i-pc-10', '太晚']])
    // 原来那条多了 issue、拿掉了以前存下的 answer(同一批里改写的每一条都不带 answer),其余原样
    expect(fake.batches[0][1].value).toEqual({ id: 'f-pc-3', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v0',
      start: '2025-01-07', end: '2025-01-07', target: 'point', source: 'picked', note: '太晚', issue: 'i-pc-10' })
  })

  it('挑了又改字:要先问;没选不存;all 各处一批改完(各用各的 base、别的字段不动)', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('i-pc-4')
    fb.setNote('追高,量也不够')
    expect(fb.panelNeedsChoice).toBe(true)
    expect(fb.problems).toEqual([])
    expect(fb.save()).toBe(false)
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    expect(fb.save('all')).toBe(true)
    await ann.flushed()
    expect(fake.batches).toHaveLength(1)
    expect(ops()).toEqual([['f-pc-10', null, 'i-pc-4', '追高,量也不够'], ['f-pc-5', 'r5', 'i-pc-4', '追高,量也不够'],
                           ['f-pc-6', 'r6', 'i-pc-4', '追高,量也不够']])
    expect(fake.batches[0][1].value).toMatchObject({ symbol: 'BBB', app_ver: 'v0', start: '2025-01-06' })
    // all:别的处是以前存下的带 answer 的,这一批里都改写成不带 answer 的
    for (const op of fake.batches[0]) expect(op.value).not.toHaveProperty('answer')
  })

  it('挑了又改字选 only_this:这一处不带 issue 值,别的处不动', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('i-pc-4')
    fb.setNote('这次是别的原因')
    expect(fb.save('only_this')).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-10', null, null, '这次是别的原因']])
    expect(fake.batches[0][0].value).not.toHaveProperty('issue')
  })

  it('打开已有的一处:连着自己的 issue;内容没变直接存;改了才问;只有这一处的改了不问', async () => {
    const { ann, view, fb } = await setup(shared())
    view.symbol = 'BBB'
    await nextTick()
    view.mode = 'compare'
    await nextTick()
    view.setLinkedRun(run('BBB'))
    await settle()
    fb.open({ id: 'f-pc-5' })
    expect(fb.panel?.link).toBe('i-pc-4')
    expect(fb.panelIssues.map(g => g.key)).toEqual(['i-pc-4', 'f-pc-3', 'f-pc-1'])     // 自己那组还有别的处:列着
    expect([fb.panelNeedsChoice, fb.panelPlaces]).toEqual([false, 2])
    expect(fb.save()).toBe(true)                                             // 没改:直接存(刷新 app_ver、拿掉 answer)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-5', 'r5', 'i-pc-4', '追高']])                // 同组的 f-pc-6 还带着 answer:不动,不算内容不同
    expect(fake.batches[0][0].value).not.toHaveProperty('answer')
    fb.open({ id: 'f-pc-5' })
    fb.setNote('追高了')
    expect(fb.panelNeedsChoice).toBe(true)
    expect(fb.save()).toBe(false)
    expect(fb.save('all')).toBe(true)
    await ann.flushed()
    expect(ops().map((o: any[]) => [o[0], o[2], o[3]])).toEqual([['f-pc-5', 'i-pc-4', '追高了'], ['f-pc-6', 'i-pc-4', '追高了']])
  })

  it('只有这一处的 issue:不在列表里,改了不问,照旧不带 issue 值', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open({ id: 'f-pc-3' })
    expect(fb.panel?.link).toBe('f-pc-3')
    expect(fb.panelIssues.map(g => g.key)).toEqual(['i-pc-4', 'f-pc-1'])
    fb.setNote('太晚了')
    expect(fb.panelNeedsChoice).toBe(false)
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-3', 'r3', null, '太晚了']])
  })

  it('挑一个以前存下的、没写 note 的 issue:不补存不了;补了以后问 all / only this', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('f-pc-1')
    expect(fb.panel).toMatchObject({ note: '', nodes: ['step'], link: 'f-pc-1' })
    expect(fb.problems).toEqual(['note'])
    expect(fb.panelNeedsChoice).toBe(false)                                  // 内容还和它一样(都没 note):先缺的是 note
    expect(fb.save()).toBe(false)
    expect(fb.save('all')).toBe(false)                                       // 没写 note:选了 all 也不存
    expect(fake.batches).toEqual([])
    fb.setNote('阶跃不算数')
    expect(fb.problems).toEqual([])
    expect([fb.panelNeedsChoice, fb.panelPlaces]).toEqual([true, 2])         // 补了 note 就和原来那处不同了:要问
    expect(fb.save()).toBe(false)
    expect(fb.save('all')).toBe(true)
    await ann.flushed()
    // all:原来那处也补上 note、带上现取的 issue 值,并改写成不带 answer 的
    expect(fake.batches).toHaveLength(1)
    expect(ops()).toEqual([['f-pc-10', null, 'i-pc-10', '阶跃不算数'], ['f-pc-1', 'r1', 'i-pc-10', '阶跃不算数']])
    expect(fake.batches[0][1].value).toEqual({ id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v0',
      start: '2025-01-08', end: '2025-01-09', target: 'family', source: 'picked', note: '阶跃不算数', nodes: ['step'],
      issue: 'i-pc-10', family_start: '2025-01-02' })
  })

  it('挑一个以前存下的、没写 note 的 issue,补了 note 选 only this:这一处另立,原来那处原样(仍带 answer)', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('f-pc-1')
    fb.setNote('阶跃不算数')
    expect(fb.save('only_this')).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-10', null, null, '阶跃不算数']])
    expect(fake.batches[0][0].value).toMatchObject({ nodes: ['step'] })
    expect(ann.state!.charts[0].feedback!.find(f => f.id === 'f-pc-1')).toMatchObject({ answer: 'off_pattern' })
  })

  it('改指:已有的一处从列表挑另一条,内容变成那条的,保存后带那条的 issue 值;原来那组别的处不动', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open({ id: 'f-pc-3' })
    fb.pickIssue('i-pc-4')
    expect(fb.panel).toMatchObject({ note: '追高', link: 'i-pc-4' })
    expect(fb.panelNeedsChoice).toBe(false)
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-3', 'r3', 'i-pc-4', '追高']])
  })

  it('再点已连着的那条 = 不再共享:内容留着,保存不带 issue 值', async () => {
    const { ann, view, fb } = await setup(shared())
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('i-pc-4')
    fb.pickIssue('i-pc-4')
    expect(fb.panel).not.toHaveProperty('link')
    expect(fb.panel?.note).toBe('追高')
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-10', null, null, '追高']])
  })

  it('以前存下的带 dag 的 issue 也能挑:只填 node 与 note;保存后两处都不带 answer、dag;resize 保留 issue', async () => {
    const r = shared()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], note: '关系不对', dag: true }
    const { ann, view, fb } = await setup(r)
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('f-pc-1')
    expect(fb.panel).toMatchObject({ note: '关系不对', nodes: ['step'], link: 'f-pc-1' })
    expect(fb.panel).not.toHaveProperty('dag')
    expect(fb.panelNeedsChoice).toBe(false)                                  // dag 不算内容:没改,不问
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(fake.batches[0].map((o: any) => [o.id, o.value.issue, o.value.nodes, 'dag' in o.value, 'answer' in o.value]))
      .toEqual([['f-pc-10', 'i-pc-10', ['step'], false, false], ['f-pc-1', 'i-pc-10', ['step'], false, false]])
    // 拖那条新的竖带的边:issue 值还在,同 issue 的别处不动
    expect(fb.resize('f-pc-10', '2025-01-09', '2025-01-10')).toBe('saved')
    await ann.flushed()
    expect(fake.batches).toHaveLength(2)
    expect(fake.batches[1].map((o: any) => [o.id, o.value.issue, o.value.start, o.value.target]))
      .toEqual([['f-pc-10', 'i-pc-10', '2025-01-09', 'range']])
  })

  it('新旧混在一个 issue 里:一处已改写成不带 answer,另一处还带着;内容相同直接存,不问', async () => {
    const r = shared()
    const { answer: _a, ...plain } = r.state.charts[1].feedback![0] as any          // f-pc-5 已是不带 answer 的
    r.state.charts[1].feedback![0] = plain
    const { ann, view, fb } = await setup(r)
    await enterCompare(view)
    fb.open(POINT)
    fb.pickIssue('i-pc-4')
    expect([fb.panelNeedsChoice, fb.panelPlaces]).toEqual([false, 3])
    expect(fb.save()).toBe(true)
    await ann.flushed()
    expect(ops()).toEqual([['f-pc-10', null, 'i-pc-4', '追高']])
  })
})
