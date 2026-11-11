// 侧栏 feedback 页(components/FeedbackPage.vue)与页签(AnnotationSidebar.vue):
// - 页签 feedback 只在 compare 有;离开 compare 时停在这页就退回 selection;
// - 当前 pattern 的全部反馈跨股票列出,按接口给的 red 排前、lost 其次、再按股票日期;行的颜色档、状态、
//   答案 / node / 理由;只列用户自己挑的(盲看标记不列);会话原因标签挂在 matched 或 lost 的行上(含不红的
//   redefined);会话段有问题时页头一行;loading;
// - 点一行:compare 里打开那只股票,图窗包住那段日期,选中那条(当前日竖线停在范围起点走图的默认聚焦,
//   挂上图在 tests/components/KlineChart.landing.spec.ts 里测);
// - 行上 delete 删掉那条。
// 后端换成内存里的假实现;别的读请求一律挂起。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnOp, AnnRead } from '../src/annotate/model'
import type { FeedbackStatusResp } from '../src/types'

const fake = vi.hoisted(() => ({
  read: null as any,
  batches: [] as any[],
  answer: null as any,
  mappings: [] as any[],
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
      const next = model.applyOps(fake.read, ops)
      const revs = structuredClone(fake.read.revs)
      ops.forEach((op, i) => { revs[op.kind][op.id] = `pc-batch-${fake.batches.length}#${i}` })
      fake.read = { ...next, revs }
      return { file: 'x.json', ...structuredClone(fake.read) }
    },
    getFeedbackStatus: async (): Promise<FeedbackStatusResp> =>
      structuredClone(fake.answer ?? { app: 'app1', app_ver: 'v1', items: [], reason: null }),
    getMappings: async () => structuredClone(fake.mappings),
  }
})

import AnnotationSidebar from '../src/components/AnnotationSidebar.vue'
import FeedbackPage from '../src/components/FeedbackPage.vue'
import { useAnnotationStore } from '../src/stores/annotation'
import { useAppLinkStore } from '../src/stores/appLink'
import { useFeedbackStore } from '../src/stores/feedback'
import { useLandingStore } from '../src/stores/landing'
import { useViewStore } from '../src/stores/view'
import { rangeLinkWindow } from '../src/annotate/directLinks'

// 默认是以前存下的带 answer 的形状(侧栏不显示 answer);f-pc-1、f-pc-5 是界面现在写出的不带 answer 的形状
const fbRec = (id: string, start: string, end: string, extra: Record<string, unknown> = {}) => {
  const { answer, ...rest } = { id, pattern: 'p', app_id: 'app1', app_ver: 'v0', start, end, target: 'range',
                                source: 'picked', answer: 'neg', note: `why ${id}`, ...extra } as any
  return (answer === undefined ? rest : { ...rest, answer }) as any
}

function annRead(): AnnRead {
  return {
    state: {
      machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }, { name: 'q' }],
      charts: [
        { symbol: 'BBB', boxes: [], samples: [], feedback: [
          fbRec('f-pc-1', '2025-01-06', '2025-01-08', { answer: undefined }),
          fbRec('f-pc-2', '2025-01-02', '2025-01-02', { target: 'point', answer: 'off_pattern', note: undefined,
                                                       nodes: ['plateau', 'step'] }),
        ] },
        { symbol: 'AAA', boxes: [], samples: [], feedback: [
          fbRec('f-pc-3', '2025-01-03', '2025-01-07'),
          fbRec('f-pc-4', '2025-01-09', '2025-01-10', { pattern: 'q' }),
          fbRec('f-pc-5', '2025-01-09', '2025-01-09', { target: 'point', answer: undefined }),
          fbRec('f-pc-6', '2025-01-10', '2025-01-10', { target: 'point', source: 'random' }),   // 盲看标记:不列
          fbRec('f-pc-7', '2025-01-02', '2025-01-03', { answer: 'off_pattern', nodes: ['step'], note: undefined }),
        ] },
      ],
    },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}

const item = (id: string, status: string | null, red: boolean, tag: string | null = null) =>
  ({ id, status, red, tag, reason: status === null ? 'no bars' : null })

async function settle() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0))
  await flushPromises()
}

/** 标注读好、当前 pattern p、AAA 打开在 compare(现算结果由测试直接放进 view);mapping 有 p 的 app。 */
async function setup() {
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const appLink = useAppLinkStore()
  await appLink.load()
  const view = useViewStore()
  view.openSymbol('AAA')
  view.mode = 'compare'
  view.setLinkedRun({ symbol: 'AAA', app: 'app1', analysis: { events: [], hits: [] } as any,
                      pattern_spec: {} as any, scan: {} as any })
  const fb = useFeedbackStore()
  await settle()
  return { ann, view, fb, appLink }
}

beforeEach(() => {
  setActivePinia(createPinia())
  fake.read = annRead()
  fake.batches = []
  fake.answer = { app: 'app1', app_ver: 'v1', reason: null, items: [
    item('f-pc-1', 'unmatched', false, 'for_tuning'),     // 常色:标签不挂
    item('f-pc-2', 'lost', false, 'unhandled'),
    item('f-pc-3', 'matched', true, 'not_worth'),
    item('f-pc-5', null, false),
    item('f-pc-7', 'matched', false, 'redefined'),        // 定义改过:matched 也不红,标签照挂
  ] }
  fake.mappings = [{ app: 'app1', pattern: 'p', features: {}, problem: null, session: null, session_problem: null }]
  localStorage.clear()
})
afterEach(() => { useFeedbackStore().$dispose() })

describe('页签', () => {
  it('feedback 页签只在 compare 有;离开 compare 时停在这页就退回 selection', async () => {
    const { view, ann } = await setup()
    const w = mount(AnnotationSidebar)
    const tabs = () => w.findAll('[role="tab"]').map(t => t.text())
    expect(tabs()).toEqual(['selection', 'features', 'pattern', 'feedback'])
    await w.get('[data-testid="annotation-tab-feedback"]').trigger('click')
    expect(ann.tab).toBe('feedback')
    expect(w.find('[data-testid="annotation-page-feedback"] [data-testid="feedback-page"]').exists()).toBe(true)
    view.enterAnnotate()
    await nextTick()
    expect(tabs()).toEqual(['selection', 'features', 'pattern'])
    expect(ann.tab).toBe('selection')
    w.unmount()
  })

  it('侧栏重新挂上时也核一次(compare → app → annotate 时侧栏是重挂的)', async () => {
    const { view, ann } = await setup()
    ann.tab = 'feedback'
    view.mode = 'app'
    await nextTick()
    view.enterAnnotate()
    const w = mount(AnnotationSidebar)
    await nextTick()
    expect(ann.tab).toBe('selection')
    expect(w.find('[data-testid="feedback-page"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('页内容', () => {
  it('当前 pattern 用户挑的跨股票全列;朱红、lost、其余排序;颜色档、状态、node / 理由;标签挂 matched 或 lost 的行', async () => {
    await setup()
    const w = mount(FeedbackPage)
    await settle()
    const rows = w.findAll('[data-testid="feedback-row"]')
    expect(rows.map(r => r.attributes('data-id'))).toEqual(['f-pc-3', 'f-pc-2', 'f-pc-7', 'f-pc-5', 'f-pc-1'])
    expect(rows.map(r => r.attributes('data-tone'))).toEqual(['red', 'lost', 'plain', 'plain', 'plain'])
    expect(rows[0].classes()).toContain('red')
    expect(rows[1].classes()).toContain('lost')
    // 都不和谁共享:一处一组,结构相同(组头写 node 与理由,下面一行写这一处)
    const groups = w.findAll('[data-testid="feedback-group"]')
    expect(groups.map(g => [g.attributes('data-key'), g.attributes('data-places')]))
      .toEqual([['f-pc-3', '1'], ['f-pc-2', '1'], ['f-pc-7', '1'], ['f-pc-5', '1'], ['f-pc-1', '1']])
    const head = (i: number, id: string) => groups[i].findAll(`[data-testid="${id}"]`).map(x => x.text())
    expect(head(0, 'feedback-row-node')).toEqual([])
    expect(head(0, 'feedback-row-nodes-none')).toEqual(['none'])                  // 一个 node 都没点:灰字 none
    expect(groups[0].get('[data-testid="feedback-row-nodes-none"]').classes()).toContain('ann-nil')
    expect(groups[0].get('[data-testid="feedback-row-nodes-none"]').attributes('title')).toBe('not on any one node, or not said')
    expect(head(0, 'feedback-row-note')).toEqual(['why f-pc-3'])
    expect(head(0, 'feedback-group-places')).toEqual(['places 1'])
    expect(head(0, 'feedback-group-matched')).toEqual(['matched 1'])
    expect(head(1, 'feedback-row-node')).toEqual(['plateau', 'step'])
    expect(head(1, 'feedback-row-nodes-none')).toEqual([])
    expect(head(1, 'feedback-row-note')).toEqual([])
    expect(head(1, 'feedback-group-matched')).toEqual(['matched 0'])
    const txt = (r: (typeof rows)[number], id: string) => r.findAll(`[data-testid="${id}"]`).map(x => x.text())
    expect(txt(rows[0], 'feedback-row-symbol')).toEqual(['AAA'])
    expect(txt(rows[0], 'feedback-row-range')).toEqual(['2025-01-03 – 2025-01-07'])
    expect(txt(rows[0], 'feedback-row-status')).toEqual(['matched'])
    expect(txt(rows[0], 'feedback-row-tag')).toEqual(['not_worth'])
    expect(txt(rows[0], 'feedback-row-note')).toEqual([])                         // 内容写在组头,不在每处那一行
    expect(txt(rows[1], 'feedback-row-range')).toEqual(['2025-01-02'])            // point:一天
    expect(txt(rows[1], 'feedback-row-tag')).toEqual(['unhandled'])
    // 定义改过:matched 了也是常色,标签说明为什么不红
    expect(txt(rows[2], 'feedback-row-status')).toEqual(['matched'])
    expect(txt(rows[2], 'feedback-row-tag')).toEqual(['redefined'])
    expect(txt(rows[3], 'feedback-row-status')).toEqual(['null'])                 // 读不到行情
    expect(rows[3].get('[data-testid="feedback-row-status"]').attributes('title')).toBe('no bars')
    expect(txt(rows[4], 'feedback-row-status')).toEqual(['unmatched'])
    expect(txt(rows[4], 'feedback-row-tag')).toEqual([])                          // unmatched 的行不挂标签
    expect(rows.every(r => r.find('[data-testid="feedback-row-delete"]').exists())).toBe(true)
    expect(w.find('[data-testid="feedback-session-problem"]').exists()).toBe(false)
    // 以前存下的记录上的 answer 不留痕:没有答案的 testid,整页没有这几个字
    expect(w.find('[data-testid="feedback-row-answer"]').exists()).toBe(false)
    expect(w.text()).not.toMatch(/off_pattern|\bneg\b|answer|dag|undefined/)
    w.unmount()
  })

  it('按 issue 分组:共享的几处在一组(跨股票),组头写处数与其中 app 还在买的处数;有朱红的组在前、其次有 lost 的', async () => {
    const charts = fake.read.state.charts
    // f-pc-1(BBB,unmatched)与 f-pc-5(AAA,状态读不到)、再加一条 f-pc-8(AAA,matched、朱红)共享 i-pc-1
    charts[0].feedback[0] = { ...charts[0].feedback[0], note: '共用的理由', issue: 'i-pc-1' }
    charts[1].feedback[2] = { ...charts[1].feedback[2], note: '共用的理由', issue: 'i-pc-1' }
    charts[1].feedback.push(fbRec('f-pc-8', '2025-01-08', '2025-01-08', { target: 'point', note: '共用的理由', issue: 'i-pc-1' }))
    fake.answer.items.push(item('f-pc-8', 'matched', true))
    const { fb } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    const groups = w.findAll('[data-testid="feedback-group"]')
    // 朱红的组(f-pc-3 单独;i-pc-1 里有 f-pc-8)在前,同档按组里排第一的那处(AAA 2025-01-03 先于 AAA 2025-01-08);再 lost;其余
    expect(groups.map(g => [g.attributes('data-key'), g.attributes('data-places')]))
      .toEqual([['f-pc-3', '1'], ['i-pc-1', '3'], ['f-pc-2', '1'], ['f-pc-7', '1']])
    const g = groups[1]
    expect(g.findAll('[data-testid="feedback-row"]').map(r => [r.attributes('data-id'), r.attributes('data-tone')]))
      .toEqual([['f-pc-8', 'red'], ['f-pc-5', 'plain'], ['f-pc-1', 'plain']])   // 组内:朱红在前,其余按股票、日期
    expect(g.findAll('[data-testid="feedback-row-symbol"]').map(x => x.text())).toEqual(['AAA', 'AAA', 'BBB'])
    expect(g.findAll('[data-testid="feedback-row-note"]').map(x => x.text())).toEqual(['共用的理由'])   // 内容只写一次
    expect(g.get('[data-testid="feedback-group-places"]').attributes('title')).toBe('places sharing this issue (same note and nodes)')
    expect(g.get('[data-testid="feedback-group-places"]').text()).toBe('places 3')
    expect(g.get('[data-testid="feedback-group-matched"]').text()).toBe('matched 1')
    expect(g.findAll('[data-testid="feedback-row-edit"]')).toHaveLength(3)
    // 行上 delete 只删这一处:组还在,少一处
    await g.get('[data-testid="feedback-row"][data-id="f-pc-5"] [data-testid="feedback-row-delete"]').trigger('click')
    await settle()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-5', base: null, value: null }]])
    const g2 = w.get('[data-testid="feedback-group"][data-key="i-pc-1"]')
    expect(g2.attributes('data-places')).toBe('2')
    expect(g2.findAll('[data-testid="feedback-row"]').map(r => r.attributes('data-id'))).toEqual(['f-pc-8', 'f-pc-1'])
    // 点组里的一处:照旧跳过去并选中那一处(只那一行加框)
    await g2.get('[data-testid="feedback-row"][data-id="f-pc-1"]').trigger('click')
    expect(fb.selectedId).toBe('f-pc-1')
    await nextTick()
    expect(w.findAll('[data-testid="feedback-row"].on').map(r => r.attributes('data-id'))).toEqual(['f-pc-1'])
    w.unmount()
  })

  it('页头:会话段有问题时一行 session ledger(悬停写全);状态正在取时 loading;没有反馈时 empty', async () => {
    fake.mappings = [{ app: 'app1', pattern: 'p', features: {}, problem: null, session: null,
                       session_problem: 'session.tags has unknown tags: wat' }]
    const { fb, ann } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    const head = w.get('[data-testid="feedback-session-problem"]')
    expect(head.text()).toBe('session ledger: session.tags has unknown tags: wat')
    expect(head.attributes('title')).toBe('session.tags has unknown tags: wat')
    fb.loading = true
    await nextTick()
    expect(w.find('[data-testid="feedback-loading"]').exists()).toBe(true)
    fb.loading = false
    ann.setCurrentPattern('q')
    await settle()
    expect(w.findAll('[data-testid="feedback-row"]').map(r => r.attributes('data-id'))).toEqual(['f-pc-4'])
    ann.setCurrentPattern(null)
    await nextTick()
    expect(w.find('[data-testid="feedback-empty"]').exists()).toBe(true)
    w.unmount()
  })
})

describe('点一行与删除', () => {
  it('点一行:compare 里打开那只股票,图窗包住那段日期,选中那条', async () => {
    const { view, fb } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    await w.get('[data-testid="feedback-row"][data-id="f-pc-1"]').trigger('click')
    expect(view.mode).toBe('compare')
    expect(view.symbol).toBe('BBB')
    expect(view.viewWindow).toEqual(rangeLinkWindow('2025-01-06', '2025-01-08'))
    expect(fb.selectedId).toBe('f-pc-1')
    await nextTick()
    expect(w.get('[data-testid="feedback-row"][data-id="f-pc-1"]').classes()).toContain('on')
    w.unmount()
  })

  it('同一只股票上点一行:不换股票,图窗照样挪过去', async () => {
    const { view } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    await w.get('[data-testid="feedback-row"][data-id="f-pc-3"]').trigger('click')
    expect([view.mode, view.symbol]).toEqual(['compare', 'AAA'])
    expect(view.viewWindow).toEqual(rangeLinkWindow('2025-01-03', '2025-01-07'))
    w.unmount()
  })

  it('行上 edit(在 delete 左边):同点一行落过去并选中;落下之后才请图表在那条记号旁打开面板', async () => {
    const { view, fb } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    const row = w.get('[data-testid="feedback-row"][data-id="f-pc-1"]')
    const btns = row.findAll('button')
    expect(btns.map(b => b.attributes('data-testid'))).toEqual(['feedback-row-edit', 'feedback-row-delete'])
    expect(btns[0].text()).toBe('edit')
    expect(btns[0].attributes('title')).toBe("open this feedback's panel on the chart")
    await btns[0].trigger('click')
    expect([view.mode, view.symbol]).toEqual(['compare', 'BBB'])
    expect(view.viewWindow).toEqual(rangeLinkWindow('2025-01-06', '2025-01-08'))
    expect(fb.selectedId).toBe('f-pc-1')
    await settle()
    expect(fb.editRequest).toBeNull()                       // 图还没落定:不提
    // 这张图的 K 线重读完、默认聚焦来问:落下那天,这时才提
    view.barDates = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']
    expect(useLandingStore().claim()).toBe(true)
    expect(fb.editRequest).toBe('f-pc-1')
    expect(fb.selectedId).toBe('f-pc-1')
    expect(fake.batches).toEqual([])
    w.unmount()
  })

  it('点一行不提 edit 的请求(只跳过去并选中)', async () => {
    const { view, fb } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    await w.get('[data-testid="feedback-row"][data-id="f-pc-1"]').trigger('click')
    view.barDates = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']
    expect(useLandingStore().claim()).toBe(true)
    expect(fb.editRequest).toBeNull()
    w.unmount()
  })

  it('组头的排法:第一行 node 小标签(没点写 none)与处数,第二行理由;以前存下的 answer、dag 不留痕', async () => {
    const charts = fake.read.state.charts
    charts[0].feedback[1] = { ...charts[0].feedback[1], note: '缺一段回踩', dag: true }      // f-pc-2:off_pattern、plateau、step + dag
    charts[1].feedback[0] = { ...charts[1].feedback[0], answer: 'off_pattern', dag: true }  // f-pc-3:off_pattern、只有 dag
    await setup()
    const w = mount(FeedbackPage)
    await settle()
    const row = (id: string) => w.get(`[data-testid="feedback-group"][data-key="${id}"]`)
    const head = (id: string) => row(id).findAll('.fb-ghead span[data-testid]').map(x => [x.attributes('data-testid'), x.text()])
    expect(head('f-pc-2')).toEqual([
      ['feedback-row-node', 'plateau'], ['feedback-row-node', 'step'],
      ['feedback-group-places', 'places 1'], ['feedback-group-matched', 'matched 0'],
      ['feedback-row-note', '缺一段回踩']])
    expect(head('f-pc-3')).toEqual([
      ['feedback-row-nodes-none', 'none'], ['feedback-group-places', 'places 1'], ['feedback-group-matched', 'matched 1'],
      ['feedback-row-note', 'why f-pc-3']])
    // 以前存下的「点了 node、没写理由」:只有第一行
    expect(head('f-pc-7')).toEqual([
      ['feedback-row-node', 'step'], ['feedback-group-places', 'places 1'], ['feedback-group-matched', 'matched 1']])
    // 界面现在写出的不带 answer 的一条:同一种排法
    expect(head('f-pc-1')).toEqual([
      ['feedback-row-nodes-none', 'none'], ['feedback-group-places', 'places 1'], ['feedback-group-matched', 'matched 0'],
      ['feedback-row-note', 'why f-pc-1']])
    expect(w.find('[data-testid="feedback-row-dag"]').exists()).toBe(false)
    expect(w.find('[data-testid="feedback-row-answer"]').exists()).toBe(false)
    expect(w.text()).not.toMatch(/off_pattern|\bneg\b|answer|dag|undefined/)
    w.unmount()
  })

  it('行上 delete:删掉那条(一批里一条删除),不跳图;选中的是它就清掉', async () => {
    const { view, fb } = await setup()
    const w = mount(FeedbackPage)
    await settle()
    fb.select('f-pc-1')
    await w.get('[data-testid="feedback-row"][data-id="f-pc-1"] [data-testid="feedback-row-delete"]').trigger('click')
    await settle()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: null, value: null }]])
    expect(view.symbol).toBe('AAA')
    expect(fb.selectedId).toBeNull()
    expect(w.findAll('[data-testid="feedback-row"]').map(r => r.attributes('data-id'))).not.toContain('f-pc-1')
    w.unmount()
  })
})
