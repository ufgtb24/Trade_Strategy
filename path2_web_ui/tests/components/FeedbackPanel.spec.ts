// 反馈作答面板(FeedbackPanel.vue):一打开就是完整的面板(没有「先选答案」)——issues(有可挑的才出)、nodes
// (node 按钮,文字同 band 表头、悬停写 mapping 原话并通知父组件加亮;点任一个后光标进 note)、note(多行文本区,必填);
// 以前存下的带 answer / dag 的记录照样打得开,面板上不出这两样;
// 已有记录多 delete / redraw、pos sample inside、app 还在跑时写 app running;
// 按键(Enter 保存、Shift+Enter 不截、Esc 只关面板、输入法组字不截、焦点在按钮上 Enter 也是保存);
// 点面板外就关(每次打开后隔一轮才挂上)、不抢焦点。后端换成内存里的假实现(同 stores.feedback.spec.ts)。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnOp, AnnRead, AnnState } from '../../src/annotate/model'
import type { EventDict, HitDict } from '../../src/types'

const fake = vi.hoisted(() => ({
  read: null as any,
  batches: [] as any[],
  n: 0,
  previewGate: null as Promise<void> | null,
}))

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
const S2 = ev('step', 2, 2), T4 = ev('today', 4, 4), T6 = ev('today', 5, 6)
const P4 = ev('plateau', 0, 4, 0, { step: [S2.instance_id], today: [T4.instance_id] })
const P6 = ev('plateau', 0, 6, 0, { step: [S2.instance_id], today: [T6.instance_id] })
const hit = (id: string, p: EventDict): HitDict =>
  ({ hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id }, children: [] })
const PREVIEW = {
  analysis: { events: [S2, T4, T6, P4, P6], hits: [hit('h4', P4), hit('h6', P6)] },
  pattern_spec: { pattern_id: 'app1', event_styles: {}, debug_enabled_nodes: [], topology: { edges: [], nodes: [
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'step', where_rules: [], parent_refs: [['plateau', 'step']] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
  ] } },
  scan: { end_node: 'plateau.today', app_ver: 'v1' },
  summary: {},
}

vi.mock('../../src/api', async (orig) => {
  const m: Record<string, any> = await orig()
  const model = await vi.importActual<typeof import('../../src/annotate/model')>('../../src/annotate/model')
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
    getFeedbackStatus: async () => ({ app: 'app1', app_ver: 'v1', items: [], reason: null }),
    getMappings: async () => [{ app: 'app1', pattern: 'p', features: {}, problem: null,
                                notes: { step: '旧平台里的那一步', plateau: '整体都不像' } }],
    getPreview: async () => {
      if (fake.previewGate) await fake.previewGate
      return structuredClone(PREVIEW)
    },
  }
})

import FeedbackPanel from '../../src/components/FeedbackPanel.vue'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useViewStore } from '../../src/stores/view'
import { useFeedbackStore } from '../../src/stores/feedback'
import { useAppLinkStore } from '../../src/stores/appLink'

const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09', '2025-01-10']

function annRead(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}
const withRecord = () => annRead({ charts: [{ symbol: 'AAA', boxes: [], samples: [
  { id: 's-pc-1', date: '2025-01-09', pattern: 'p', judgment: 'pos', members: [] },
], feedback: [
  { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-08', end: '2025-01-09', target: 'range',
    source: 'picked', answer: 'neg', note: '太高了' } as any,      // 以前存下的带 answer 的记录
] }] })

async function settle() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0))
  await flushPromises()
}

/** 标注读好、当前 pattern p、AAA 打开并进 compare(app 跑完,除非 previewGate 挡着)。 */
async function setup(read: AnnRead = annRead()) {
  fake.read = read
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const view = useViewStore()
  view.symbol = 'AAA'
  view.barDates = DATES
  const appLink = useAppLinkStore()
  await appLink.load()
  const fb = useFeedbackStore()
  view.mode = 'compare'
  await settle()
  return { ann, view, fb, appLink }
}

const AT = { x: 100, y: 200 }
const RANGE = { symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'range' as const }
const featureOf = (n: string) => (n === 'step' ? '一步' : null)

let w: VueWrapper<any> | null = null
async function mountPanel() {
  w = mount(FeedbackPanel, { props: { featureOf }, attachTo: document.body })
  await flushPromises()
  return w
}
const has = (tid: string) => w!.find(`[data-testid="${tid}"]`).exists()
const key = (k: string, init: KeyboardEventInit = {}, target: EventTarget = document.body) =>
  target.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...init }))
const press = (target: Element, type = 'mousedown') =>
  target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true }))

beforeEach(() => {
  setActivePinia(createPinia())
  fake.batches = []
  fake.n = 0
  fake.previewGate = null
  localStorage.clear()
  document.body.innerHTML = ''
})
afterEach(() => {
  w?.unmount()
  w = null
  useFeedbackStore().$dispose()
})

describe('FeedbackPanel · 样子', () => {
  it('新范围:页头写股票、范围、target;一打开就有 nodes 与 note 两行和 save,没有答案按钮、没有 dag;不抢焦点', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    expect(w!.get('[data-testid="feedback-symbol"]').text()).toBe('AAA')
    expect(w!.get('[data-testid="feedback-span"]').text()).toBe('2025-01-08 – 2025-01-10')
    expect(w!.get('[data-testid="feedback-target"]').text()).toBe('range')
    expect(w!.findAll('button').map(b => b.text())).toEqual(['plateau', 'step一步', 'today', 'save'])
    expect(w!.findAll('.fb-kv > .ann-k').map(k => k.text())).toEqual(['nodes', 'note'])       // 没有可挑的 issue:不出 issues 行
    for (const t of ['feedback-note', 'feedback-nodes', 'feedback-save']) expect(has(t)).toBe(true)
    for (const t of ['feedback-answer-neg', 'feedback-answer-off_pattern', 'feedback-dag', 'feedback-issues',
                     'feedback-delete', 'feedback-redraw', 'feedback-pos-inside', 'feedback-blocked',
                     'feedback-problems', 'feedback-share']) expect(has(t)).toBe(false)
    expect(w!.text()).not.toMatch(/answer|off_pattern|\bneg\b|dag/)
    expect(document.activeElement).toBe(document.body)                       // 打开时不抢焦点,光标也不进 note
    // 按钮按下不夺焦点
    const btn = w!.findAll('[data-testid="feedback-node"]')[0].element
    const md = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    btn.dispatchEvent(md)
    expect(md.defaultPrevented).toBe(true)
  })

  it('固定文字的悬停:nodes 说点它是什么意思,note 说必填', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    const keys = w!.findAll('.fb-kv > .ann-k')
    expect(keys[0].attributes('title')).toBe("where the problem sits: nodes the app's buys here are bound to, and their "
      + 'child nodes; pick any number, or none if it is not on any one node or you cannot tell')
    expect(keys[1].attributes('title')).toBe('what is wrong with buying here, in your own words; required')
    expect(w!.get('[data-testid="feedback-note"]').attributes('placeholder')).toBe('required')
  })

  it('node 按钮:范围里买的 hit 绑定的 node 及子 node,文字 = node 名 + 特征名,悬停写 mapping 原话;可多选;点上或点掉后光标进 note', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    const btns = () => w!.findAll('[data-testid="feedback-node"]')
    expect(btns().map(s => s.attributes('data-node'))).toEqual(['plateau', 'step', 'today'])
    expect(btns()[1].text()).toBe('step一步')
    expect(btns()[1].find('.ann-biz').text()).toBe('一步')
    expect(btns()[0].attributes('title')).toBe('整体都不像')
    expect(btns()[1].attributes('title')).toBe('旧平台里的那一步')
    const note = w!.get('[data-testid="feedback-note"]').element
    expect(document.activeElement).toBe(document.body)
    await btns()[1].trigger('click')
    expect(fb.panel?.nodes).toEqual(['step'])
    expect(btns()[1].classes()).toContain('on')
    expect(document.activeElement).toBe(note)                               // 点上:光标进 note
    await btns()[2].trigger('click')                                        // 光标在 note 里不妨碍接着多选
    expect(fb.panel?.nodes).toEqual(['step', 'today'])
    ;(document.activeElement as HTMLElement).blur()
    await btns()[1].trigger('click')                                        // 点掉:光标也进 note
    expect(fb.panel?.nodes).toEqual(['today'])
    expect(document.activeElement).toBe(note)
    // 悬停:通知父组件加亮那条 band,离开即取消
    await btns()[1].trigger('mouseenter')
    await btns()[1].trigger('mouseleave')
    expect(w!.emitted('hover-node')).toEqual([['step'], [null]])
  })

  it('只点 node 不写 note:存不了,标出缺 note;写了就能存,值里没有 answer、dag', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.findAll('[data-testid="feedback-node"]')[1].trigger('click')
    await w!.get('[data-testid="feedback-save"]').trigger('click')
    const need = w!.get('[data-testid="feedback-problems"]')
    expect(need.findAll('[data-problem]').map(x => [x.attributes('data-problem'), x.text(), x.attributes('title')]))
      .toEqual([['note', 'note', 'write a note first']])
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    await w!.get('[data-testid="feedback-note"]').setValue('阶跃太小')
    expect(has('feedback-problems')).toBe(false)
    await w!.get('[data-testid="feedback-save"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)?.[0].value).toEqual({ id: 'f-pc-10', symbol: 'AAA', pattern: 'p', app_id: 'app1',
      app_ver: 'v1', start: '2025-01-08', end: '2025-01-10', target: 'range', source: 'picked', note: '阶跃太小',
      nodes: ['step'] })
  })

  it('一个 node 都不点、只写 note:能存,值里没有 nodes', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-note"]').setValue('整体不像')
    await w!.get('[data-testid="feedback-save"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)?.[0].value).toMatchObject({ note: '整体不像' })
    for (const k of ['nodes', 'answer', 'dag']) expect(fake.batches.at(-1)?.[0].value).not.toHaveProperty(k)
  })

  it('这段里 app 没买:没有 node 可点,nodes 一行写灰字 none', async () => {
    const r = withRecord()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], start: '2025-01-02', end: '2025-01-03' } as any
    const { fb } = await setup(r)
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    expect(w!.findAll('[data-testid="feedback-node"]')).toHaveLength(0)
    const row = w!.get('[data-testid="feedback-nodes"]')
    expect(row.text()).toBe('none')
    expect(row.get('span').classes()).toContain('ann-nil')
  })

  it('note 是多行文本区(长文字换行),testid 不变', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    const note = w!.get('[data-testid="feedback-note"]')
    expect(note.element.tagName).toBe('TEXTAREA')
    expect(note.classes()).toContain('ann-area')
    await note.setValue('第一行\n第二行')
    expect(fb.panel?.note).toBe('第一行\n第二行')
  })

  it('条件都满足却没存成:兜底写 not saved;草稿一改就撤掉', async () => {
    const { fb, ann } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-note"]').setValue('还在跌')
    const spy = vi.spyOn(ann, 'saveFeedback').mockReturnValue(null)
    await w!.get('[data-testid="feedback-save"]').trigger('click')
    expect(w!.get('[data-testid="feedback-blocked"]').text()).toBe('not saved')
    await w!.get('[data-testid="feedback-note"]').setValue('还在跌,量也不够')
    expect(has('feedback-blocked')).toBe(false)
    spy.mockRestore()
  })

  it('补齐缺的东西之后不挂 not saved', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-save"]').trigger('click')            // 缺 note:没存
    expect(has('feedback-problems')).toBe(true)
    await w!.get('[data-testid="feedback-note"]').setValue('还在跌')
    expect(has('feedback-problems')).toBe(false)
    expect(has('feedback-blocked')).toBe(false)
  })

  it('已有记录(以前存下的 neg + note):预填理由,多 delete 与 redraw;范围里有正样本时写 pos sample inside;面板上没有答案', async () => {
    const { fb, ann } = await setup(withRecord())
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    expect(has('feedback-delete')).toBe(true)
    expect(has('feedback-redraw')).toBe(true)
    expect(has('feedback-pos-inside')).toBe(true)
    expect(has('feedback-answer-neg')).toBe(false)
    expect(w!.text()).not.toMatch(/answer|\bneg\b|undefined/)
    expect((w!.get('[data-testid="feedback-note"]').element as HTMLTextAreaElement).value).toBe('太高了')
    expect(w!.findAll('[data-testid="feedback-node"].on')).toHaveLength(0)
    expect(document.activeElement).toBe(document.body)
    expect(w!.get('[data-testid="feedback-redraw"]').attributes('title'))
      .toBe("drag a new range on the chart; the note and nodes come along and replace this feedback's range")
    // redraw:关面板、点亮 feedback 工具,理由带进下一次拖选
    await w!.get('[data-testid="feedback-redraw"]').trigger('click')
    expect(fb.panel).toBeNull()
    expect(ann.tool).toBe('feedback')
    expect(fb.carry).toEqual({ editingId: 'f-pc-1', note: '太高了', nodes: [], link: 'f-pc-1' })
  })

  it('以前存下的 off_pattern + node、没写 note:node 预填点上;不补 note 存不了,补了就存成不带 answer 的', async () => {
    const r = withRecord()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], answer: 'off_pattern', note: undefined,
                                       nodes: ['step', 'gone_node'] } as any
    r.revs.feedback = { 'f-pc-1': 'r1' }
    const { fb } = await setup(r)
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    const btns = w!.findAll('[data-testid="feedback-node"]')
    expect(btns.map(b => [b.attributes('data-node'), b.classes().includes('on'), b.classes().includes('gone')]))
      .toEqual([['plateau', false, false], ['step', true, false], ['today', false, false], ['gone_node', true, true]])
    expect(btns[3].attributes('title')).toBe('not in the current app')       // 记录里有、当前 app 已没有:排最后、虚线框
    expect((w!.get('[data-testid="feedback-note"]').element as HTMLTextAreaElement).value).toBe('')
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    expect(w!.get('[data-testid="feedback-problems"]').findAll('[data-problem]').map(x => x.attributes('data-problem')))
      .toEqual(['note'])
    await w!.get('[data-testid="feedback-note"]').setValue('阶跃不算数')
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'r1', value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-08', end: '2025-01-09',
      target: 'range', source: 'picked', note: '阶跃不算数', nodes: ['step', 'gone_node'] } }]])
  })

  it('以前存下的 off_pattern + node + dag + note:预填 node 与理由,没有 dag 按钮;什么都不改按 Enter 也存成不带 answer、dag 的', async () => {
    const r = withRecord()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], answer: 'off_pattern', note: '关系不对',
                                       nodes: ['step'], dag: true } as any
    r.revs.feedback = { 'f-pc-1': 'r1' }
    const { fb } = await setup(r)
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    expect(has('feedback-dag')).toBe(false)
    expect(w!.text()).not.toMatch(/answer|off_pattern|dag|undefined/)
    expect(w!.findAll('[data-testid="feedback-node"].on').map(b => b.attributes('data-node'))).toEqual(['step'])
    expect((w!.get('[data-testid="feedback-note"]').element as HTMLTextAreaElement).value).toBe('关系不对')
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toEqual([[{ kind: 'feedback', id: 'f-pc-1', base: 'r1', value: {
      id: 'f-pc-1', symbol: 'AAA', pattern: 'p', app_id: 'app1', app_ver: 'v1', start: '2025-01-08', end: '2025-01-09',
      target: 'range', source: 'picked', note: '关系不对', nodes: ['step'] } }]])
  })

  it('delete:删掉那条并关面板', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    await w!.get('[data-testid="feedback-delete"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)).toEqual([expect.objectContaining({ kind: 'feedback', id: 'f-pc-1', value: null })])
  })

  it('app 还在跑:写 app running;Enter 不存、面板留着(缺的东西为空)', async () => {
    let release!: () => void
    fake.previewGate = new Promise<void>(r => { release = r })
    const { fb, view, appLink } = await setup(withRecord())
    expect(view.linkedRun).toBeNull()
    expect(appLink.runStatus).toBe('loading')
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    expect(w!.get('[data-testid="feedback-blocked"]').text()).toBe('app running')
    key('Enter')
    await flushPromises()
    expect(fb.panel).not.toBeNull()
    expect(fb.problems).toEqual([])
    expect(fake.batches).toEqual([])
    expect(w!.get('[data-testid="feedback-blocked"]').text()).toBe('app running')
    release()
  })
})

describe('FeedbackPanel · issue', () => {
  const RANGE2 = { symbol: 'AAA', start: '2025-01-10', end: '2025-01-10', target: 'point' as const }
  const issues = () => w!.findAll('[data-testid="feedback-issue"]')

  it('一打开就列出已有的 issue(排在 nodes 之上);点一条:note 填好、那条加黑边,不夺焦点、不动焦点;再点不再共享', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    expect(w!.findAll('.fb-kv > .ann-k').map(k => k.text())).toEqual(['issues', 'nodes', 'note'])
    expect(w!.findAll('.fb-kv > .ann-k')[0].attributes('title')).toBe('issues already written under this pattern, '
      + 'across symbols, latest first; pick one to share it here: its nodes and note fill in')
    expect(issues().map(b => [b.attributes('data-key'), b.attributes('data-places'), b.text()]))
      .toEqual([['f-pc-1', '1', '太高了places 1']])                 // 以前存下的 neg:不写答案
    expect(issues()[0].find('.ann-biz').text()).toBe('太高了')     // 用户写的:正常字体浅灰底
    expect(issues()[0].classes()).not.toContain('on')
    const md = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    issues()[0].element.dispatchEvent(md)
    expect(md.defaultPrevented).toBe(true)
    await issues()[0].trigger('click')
    expect(fb.panel).toMatchObject({ note: '太高了', link: 'f-pc-1' })
    expect(issues()[0].classes()).toContain('on')
    expect((w!.get('[data-testid="feedback-note"]').element as HTMLTextAreaElement).value).toBe('太高了')
    expect(document.activeElement).toBe(document.body)            // 挑 issue 不动焦点
    expect(has('feedback-share')).toBe(false)
    expect(has('feedback-save')).toBe(true)
    // 再点一次:不再共享,内容留着
    await issues()[0].trigger('click')
    expect(issues()[0].classes()).not.toContain('on')
    expect(fb.panel?.note).toBe('太高了')
    expect(fb.panel).not.toHaveProperty('link')
  })

  it('issue 一条:点出的 node 小标签在前、理由、处数;以前存下的带 dag 的不出 dag 标签', async () => {
    const r = withRecord()
    r.state.charts[0].feedback!.push({ id: 'f-pc-2', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: '2025-01-07',
      end: '2025-01-07', target: 'point', source: 'picked', answer: 'off_pattern', note: '关系不对',
      nodes: ['step', 'today'], dag: true } as any)
    const { fb } = await setup(r)
    fb.open(AT, RANGE2)
    await mountPanel()
    expect(issues().map(b => b.attributes('data-key'))).toEqual(['f-pc-2', 'f-pc-1'])      // 最近用过的在前
    expect(issues()[0].findAll('.fb-chip').map(c => c.text())).toEqual(['step', 'today'])
    expect(issues()[0].text()).toBe('steptoday关系不对places 1')
    await issues()[0].trigger('click')
    expect(fb.panel).toMatchObject({ note: '关系不对', nodes: ['step', 'today'], link: 'f-pc-2' })
    expect(w!.findAll('[data-testid="feedback-node"].on').map(b => b.attributes('data-node'))).toEqual(['step', 'today'])
  })

  it('挑一条后直接 Enter:两处带同一个 issue 值(原来那条同批补上,并改写成不带 answer 的)', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    await issues()[0].trigger('click')
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toHaveLength(1)
    expect(fake.batches[0].map((o: any) => [o.id, o.value.issue, o.value.note, 'answer' in o.value]))
      .toEqual([['f-pc-10', 'i-pc-1', '太高了', false], ['f-pc-1', 'i-pc-1', '太高了', false]])
  })

  it('挑了又改字:save 换成 shared by n places + all / only this;Enter 不存、提示要选;only this 只存这一处', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    await issues()[0].trigger('click')
    await w!.get('[data-testid="feedback-note"]').setValue('太高了,量也不够')
    expect(has('feedback-save')).toBe(false)
    expect(w!.get('[data-testid="feedback-share-count"]').text()).toBe('shared by 2 places')
    expect(w!.get('[data-testid="feedback-share-count"]').attributes('title'))
      .toBe('places using this issue, this one included; the note or nodes here differ from the other places')
    expect(w!.get('[data-testid="feedback-share"]').findAll('button').map(b => b.text())).toEqual(['all', 'only this'])
    expect(w!.get('[data-testid="feedback-share-all"]').attributes('title'))
      .toBe('change every place of this issue to the note and nodes written here')
    expect(has('feedback-problems')).toBe(false)                  // 还没试过保存:不标
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    expect(w!.get('[data-testid="feedback-problems"]').findAll('[data-problem]').map(x => [x.attributes('data-problem'), x.text()]))
      .toEqual([['choice', 'all | only this']])
    expect(has('feedback-blocked')).toBe(false)                   // 不算没存成
    await w!.get('[data-testid="feedback-share-only"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toHaveLength(1)
    expect(fake.batches[0]).toHaveLength(1)
    expect(fake.batches[0][0].value).toMatchObject({ id: 'f-pc-10', note: '太高了,量也不够' })
    expect(fake.batches[0][0].value).not.toHaveProperty('issue')
  })

  it('挑了又改 node(note 没动):也要问', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    await issues()[0].trigger('click')
    expect(has('feedback-share')).toBe(false)
    await w!.findAll('[data-testid="feedback-node"]')[0].trigger('click')
    expect(has('feedback-share')).toBe(true)
    await w!.findAll('[data-testid="feedback-node"]')[0].trigger('click')    // 点掉:又和它一样了
    expect(has('feedback-share')).toBe(false)
  })

  it('all:各处同一批改掉(以前存下的那处一并改写成不带 answer 的);改回原样后那一行消失、save 回来', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    await issues()[0].trigger('click')
    const note = w!.get('[data-testid="feedback-note"]')
    await note.setValue('太高了,量也不够')
    expect(has('feedback-share')).toBe(true)
    await note.setValue(' 太高了 ')                                // 只差首尾空白:不算改
    expect(has('feedback-share')).toBe(false)
    expect(has('feedback-save')).toBe(true)
    await note.setValue('太高了,量也不够')
    await w!.get('[data-testid="feedback-share-all"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toHaveLength(1)
    expect(fake.batches[0].map((o: any) => [o.id, o.value.issue, o.value.note, 'answer' in o.value]))
      .toEqual([['f-pc-10', 'i-pc-1', '太高了,量也不够', false], ['f-pc-1', 'i-pc-1', '太高了,量也不够', false]])
  })

  it('缺东西时点 all 也不存,照常标出缺什么', async () => {
    const { fb } = await setup(withRecord())
    fb.open(AT, RANGE2)
    await mountPanel()
    await issues()[0].trigger('click')
    await w!.findAll('[data-testid="feedback-node"]')[0].trigger('click')    // 改了 node:要问
    await w!.get('[data-testid="feedback-note"]').setValue('')
    await w!.get('[data-testid="feedback-share-all"]').trigger('click')
    await settle()
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    expect(w!.get('[data-testid="feedback-problems"]').findAll('[data-problem]').map(x => x.attributes('data-problem')))
      .toEqual(['note'])
  })

  it('挑一个以前存下的、没写 note 的 issue:不补存不了;补了以后换成 all / only this', async () => {
    const r = withRecord()
    r.state.charts[0].feedback![0] = { ...r.state.charts[0].feedback![0], answer: 'off_pattern', note: undefined,
                                       nodes: ['step'] } as any
    r.revs.feedback = { 'f-pc-1': 'r1' }
    const { fb } = await setup(r)
    fb.open(AT, RANGE2)
    await mountPanel()
    expect(issues()[0].text()).toBe('stepplaces 1')               // 没写理由:只有 node 与处数
    await issues()[0].trigger('click')
    expect(has('feedback-share')).toBe(false)
    expect(key('Enter')).toBe(false)
    await settle()
    expect(fake.batches).toEqual([])
    expect(w!.get('[data-testid="feedback-problems"]').findAll('[data-problem]').map(x => x.attributes('data-problem')))
      .toEqual(['note'])
    await w!.get('[data-testid="feedback-note"]').setValue('阶跃不算数')
    expect(has('feedback-save')).toBe(false)
    expect(w!.get('[data-testid="feedback-share-count"]').text()).toBe('shared by 2 places')
    await w!.get('[data-testid="feedback-share-all"]').trigger('click')
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches).toHaveLength(1)
    expect(fake.batches[0].map((o: any) => [o.id, o.base, o.value.issue, o.value.note, o.value.nodes, 'answer' in o.value]))
      .toEqual([['f-pc-10', null, 'i-pc-1', '阶跃不算数', ['step'], false],
                ['f-pc-1', 'r1', 'i-pc-1', '阶跃不算数', ['step'], false]])
  })
})

describe('FeedbackPanel · 按键', () => {
  it('Enter 保存(写一条 range 反馈)并关面板;输入法组字中的 Enter 不截', async () => {
    const { fb, ann } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    const note = w!.get('[data-testid="feedback-note"]')
    await note.setValue('还在跌')
    expect(key('Enter', { isComposing: true }, note.element)).toBe(true)     // 没被 preventDefault
    expect(key('Enter', { keyCode: 229 }, note.element)).toBe(true)
    expect(fb.panel).not.toBeNull()
    expect(key('Enter', {}, note.element)).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)).toEqual([expect.objectContaining({ kind: 'feedback', value: {
      id: 'f-pc-10', symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'range', note: '还在跌',
      pattern: 'p', app_id: 'app1', app_ver: 'v1', source: 'picked' } })])
    expect(ann.tool).toBeNull()
  })

  it('Shift+Enter 不截(在 note 里换行),不保存;Enter 才保存', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    const note = w!.get('[data-testid="feedback-note"]')
    await note.setValue('还在跌')
    expect(key('Enter', { shiftKey: true }, note.element)).toBe(true)        // 没被 preventDefault
    await settle()
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
    expect(key('Enter', {}, note.element)).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
  })

  it('焦点在面板的按钮上时 Enter 也是保存(浏览器默认的「点按钮」被截下)', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-note"]').setValue('整体不像')
    await w!.findAll('[data-testid="feedback-node"]')[0].trigger('click')
    const btn = w!.findAll('[data-testid="feedback-node"]')[1].element as HTMLButtonElement
    btn.focus()
    const bubbled = vi.fn()
    window.addEventListener('keydown', bubbled)
    expect(key('Enter', {}, btn)).toBe(false)
    window.removeEventListener('keydown', bubbled)
    expect(bubbled).not.toHaveBeenCalled()                 // 截下后不再往下传
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)?.[0].value).toMatchObject({ note: '整体不像', nodes: ['plateau'] })
  })

  it('Esc 第一下只关面板:不熄工具、不往下传;组字中的 Esc 不截', async () => {
    const { fb, ann } = await setup()
    ann.tool = 'feedback'
    fb.open(AT, RANGE)
    await mountPanel()
    expect(key('Escape', { isComposing: true })).toBe(true)
    expect(fb.panel).not.toBeNull()
    const bubbled = vi.fn()
    window.addEventListener('keydown', bubbled)
    key('Escape')
    window.removeEventListener('keydown', bubbled)
    expect(bubbled).not.toHaveBeenCalled()
    expect(fb.panel).toBeNull()
    expect(ann.tool).toBe('feedback')
  })

  it('←/→ 不截;焦点在面板外的输入框里时 Enter 不截', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    expect(key('ArrowLeft')).toBe(true)
    const outside = document.createElement('input')
    document.body.appendChild(outside)
    expect(key('Enter', {}, outside)).toBe(true)
    expect(fb.panel).not.toBeNull()
  })
})

describe('FeedbackPanel · 点面板外就关', () => {
  it('打开后同一轮里的按下(打开它的那次点击、拖选松手后的 click)不关;之后点面板外关、点面板里不关', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    w = mount(FeedbackPanel, { props: { featureOf }, attachTo: document.body })   // 不等:同一轮里接着按下
    press(document.body)
    press(document.body, 'click')
    expect(fb.panel).not.toBeNull()
    await new Promise(r => setTimeout(r, 0))
    press(w!.get('[data-testid="feedback-note"]').element)
    expect(fb.panel).not.toBeNull()
    press(document.body)
    expect(fb.panel).toBeNull()
  })

  it('关旧开新(组件不卸载):新开的那一下同样不被外部点击关掉,之后照常', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await new Promise(r => setTimeout(r, 0))
    fb.open({ x: 300, y: 300 }, { symbol: 'AAA', start: '2025-01-09', end: '2025-01-09', target: 'point' })
    press(document.body)
    expect(fb.panel?.target).toBe('point')
    await new Promise(r => setTimeout(r, 0))
    press(document.body)
    expect(fb.panel).toBeNull()
  })
})
