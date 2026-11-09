// 反馈作答面板(FeedbackPanel.vue):初始两个按钮、点 neg 展开 note 并把光标放进去、off_pattern 展开分段按钮
// (文字同 band 表头、悬停写 mapping 原话并通知父组件加亮)、已有记录多 delete / redraw、pos sample inside、
// app 还在跑时写 app running;按键(Enter 保存、Esc 只关面板、输入法组字不截、焦点在按钮上 Enter 也是保存);
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
    source: 'picked', answer: 'neg', note: '太高了' } as any,
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
  it('新范围:页头写股票、范围、target;初始只有 neg / off_pattern 两个按钮;不抢焦点', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    expect(w!.get('[data-testid="feedback-symbol"]').text()).toBe('AAA')
    expect(w!.get('[data-testid="feedback-span"]').text()).toBe('2025-01-08 – 2025-01-10')
    expect(w!.get('[data-testid="feedback-target"]').text()).toBe('range')
    expect(w!.findAll('button').map(b => b.text())).toEqual(['neg', 'off_pattern'])
    for (const t of ['feedback-note', 'feedback-segments', 'feedback-save', 'feedback-delete', 'feedback-redraw',
                     'feedback-pos-inside', 'feedback-blocked', 'feedback-problems']) expect(has(t)).toBe(false)
    expect(document.activeElement).toBe(document.body)
    // 按钮按下不夺焦点
    const neg = w!.get('[data-testid="feedback-answer-neg"]').element
    const md = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    neg.dispatchEvent(md)
    expect(md.defaultPrevented).toBe(true)
  })

  it('点 neg:展开 note 并把光标放进去;没写理由时保存不了,标出缺 note', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-answer-neg"]').trigger('click')
    await flushPromises()
    const note = w!.get('[data-testid="feedback-note"]')
    expect(document.activeElement).toBe(note.element)
    expect(has('feedback-segments')).toBe(false)
    await w!.get('[data-testid="feedback-save"]').trigger('click')
    expect(w!.get('[data-testid="feedback-problems"]').find('[data-problem="note"]').exists()).toBe(true)
    expect(fb.panel).not.toBeNull()
    expect(fake.batches).toEqual([])
  })

  it('点 off_pattern:展开分段按钮(范围里买的 hit 绑定的 node 及子 node,文字 = node 名 + 特征名,悬停写 mapping 原话)与可选 note;不移焦点', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-answer-off_pattern"]').trigger('click')
    await flushPromises()
    const segs = w!.findAll('[data-testid="feedback-segment"]')
    expect(segs.map(s => s.attributes('data-node'))).toEqual(['plateau', 'step', 'today'])
    expect(segs[1].text()).toBe('step一步')
    expect(segs[1].find('.ann-biz').text()).toBe('一步')
    expect(segs[0].attributes('title')).toBe('整体都不像')
    expect(segs[1].attributes('title')).toBe('旧平台里的那一步')
    expect(w!.get('[data-testid="feedback-note"]').attributes('placeholder')).toBe('optional')
    expect(document.activeElement).toBe(document.body)
    await segs[1].trigger('click')
    expect(fb.panel?.segments).toEqual(['step'])
    expect(w!.findAll('[data-testid="feedback-segment"]')[1].classes()).toContain('on')
    // 悬停:通知父组件加亮那条 band,离开即取消
    await segs[1].trigger('mouseenter')
    await segs[1].trigger('mouseleave')
    expect(w!.emitted('hover-segment')).toEqual([['step'], [null]])
  })

  it('已有记录:预填,多 delete 与 redraw;范围里有正样本时写 pos sample inside', async () => {
    const { fb, ann } = await setup(withRecord())
    fb.open(AT, { id: 'f-pc-1' })
    await mountPanel()
    expect(has('feedback-delete')).toBe(true)
    expect(has('feedback-redraw')).toBe(true)
    expect(has('feedback-pos-inside')).toBe(true)
    expect(w!.get('[data-testid="feedback-answer-neg"]').classes()).toContain('on')
    expect((w!.get('[data-testid="feedback-note"]').element as HTMLInputElement).value).toBe('太高了')
    expect(document.activeElement).toBe(document.body)
    // redraw:关面板、点亮 feedback 工具,答案带进下一次拖选
    await w!.get('[data-testid="feedback-redraw"]').trigger('click')
    expect(fb.panel).toBeNull()
    expect(ann.tool).toBe('feedback')
    expect(fb.carry).toMatchObject({ editingId: 'f-pc-1', answer: 'neg', note: '太高了' })
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

describe('FeedbackPanel · 按键', () => {
  it('Enter 保存(写一条 range 反馈)并关面板;输入法组字中的 Enter 不截', async () => {
    const { fb, ann } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-answer-neg"]').trigger('click')
    await flushPromises()
    const note = w!.get('[data-testid="feedback-note"]')
    await note.setValue('还在跌')
    expect(key('Enter', { isComposing: true }, note.element)).toBe(true)     // 没被 preventDefault
    expect(key('Enter', { keyCode: 229 }, note.element)).toBe(true)
    expect(fb.panel).not.toBeNull()
    expect(key('Enter', {}, note.element)).toBe(false)
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)).toEqual([expect.objectContaining({ kind: 'feedback', value: expect.objectContaining({
      symbol: 'AAA', start: '2025-01-08', end: '2025-01-10', target: 'range', answer: 'neg', note: '还在跌',
      pattern: 'p', app_id: 'app1', app_ver: 'v1', source: 'picked' }) })])
    expect(ann.tool).toBeNull()
  })

  it('焦点在面板的按钮上时 Enter 也是保存(浏览器默认的「点按钮」被截下)', async () => {
    const { fb } = await setup()
    fb.open(AT, RANGE)
    await mountPanel()
    await w!.get('[data-testid="feedback-answer-off_pattern"]').trigger('click')
    await w!.findAll('[data-testid="feedback-segment"]')[0].trigger('click')
    const btn = w!.get('[data-testid="feedback-answer-neg"]').element as HTMLButtonElement
    btn.focus()
    const bubbled = vi.fn()
    window.addEventListener('keydown', bubbled)
    expect(key('Enter', {}, btn)).toBe(false)
    window.removeEventListener('keydown', bubbled)
    expect(bubbled).not.toHaveBeenCalled()                 // 截下后不再往下传
    await settle()
    expect(fb.panel).toBeNull()
    expect(fake.batches.at(-1)?.[0].value).toMatchObject({ answer: 'off_pattern', segments: ['plateau'] })
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
    press(w!.get('[data-testid="feedback-answer-neg"]').element)
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
