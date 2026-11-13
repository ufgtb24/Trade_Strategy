// compare 下对选中的那一个打开反馈面板(KlineChart.vue):挂上真的 KlineChart,K 线、跑 app、标注、mapping 由内存里的
// 假后端给,echarts 换成假图(x 轴:第 i 根 K 线中心在 100 + 10·i 像素)。
// - Enter(不带修饰键、非组字、不是按住不放的重复)对选中的那一个打开;焦点停在别处的按钮、链接上也照样开(截下默认、
//   放掉那个焦点),在下拉框、输入框里时不开;不能作答时不做事、不吞键(按钮照常吃 Enter);
// - 按住 Enter:第一下打开,后面的重复不会顺手把它存了;
// - 显示栏最右的 feedback 按钮:没选中 / 不能作答时灰,能作答时亮,点了打开;面板开着时是按下的样子,再点关掉;
// - 面板开着时竖带(feedback-selected-band)画面板管的那段日期,压过选中的那条反馈;关了回到选中的反馈;
// - 改起止的手势只认画出来的那条竖带:面板开着、对着的不是选中的那条反馈时,选中那条的边不能拖;
// - 面板的默认落点由图表量好给面板(anchor):竖带的左右、显示栏的上沿、图表区的左右;
// - 侧栏卡片的 edit:图上有那条记号就选中并打开它;
// - app 还没跑完(compare 下现算结果没回来):按钮灰、Enter 不开(选中本身已能作答也一样);
// - app 模式没有按钮,Enter 不开。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnRead } from '../../src/annotate/model'
import type { EventDict, HitDict } from '../../src/types'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

// 30 根 K 线:2025-01-01 ~ 2025-01-30(按日历日连着排,够用)
const DATES = Array.from({ length: 30 }, (_, i) => `2025-01-${String(i + 1).padStart(2, '0')}`)
const BARS = DATES.map(date => ({ date, o: 10, h: 11, l: 9, c: 10, v: 1000, rv: 1 }))

const ev = (node: string, s: number, e: number, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#0`, node_id: node, instance_idx: 0, start_idx: s, end_idx: e, child_refs })
// 买点 node = plateau.today:一族 hits@0,h4 买第 4 根、h8 买第 8 根
const T4 = ev('today', 4, 4), T8 = ev('today', 8, 8)
const P4 = ev('plateau', 0, 4, { today: [T4.instance_id] })
const P8 = ev('plateau', 0, 8, { today: [T8.instance_id] })
const HITS: HitDict[] = [
  { hit_id: 'h4', start_idx: 0, end_idx: 4, node_index: { plateau: P4.instance_id }, children: [] },
  { hit_id: 'h8', start_idx: 0, end_idx: 8, node_index: { plateau: P8.instance_id }, children: [] },
]
const preview = (app: string) => ({
  analysis: { events: [T4, T8, P4, P8], hits: HITS }, summary: {},
  pattern_spec: { pattern_id: app, event_styles: {}, debug_enabled_nodes: [], topology: { edges: [], nodes: [
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
  ] } },
  scan: { start_date: '1900-01-01', end_date: '2025-12-31', win_start: '1899-09-01', win_end: '2025-12-31',
          label_horizon: 20, end_node: 'plateau.today', app_ver: 'v1' },
})

const fake = vi.hoisted(() => ({
  read: null as any,
  previewGate: null as Promise<void> | null,
  // 假图:按 init 的先后记下(先主图后副图);zr 上挂的处理器、设过的鼠标样式;主图 K 线区算不算点中
  charts: [] as { zr: Record<string, ((e: any) => void)[]>; cursor: string[] }[],
  containMain: false,
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
    getSymbols: async () => ['AAA'],
    getAllOhlc: async (symbol: string) => ({ symbol, bars: BARS }),
    getPreview: async (app: string) => {
      if (fake.previewGate) await fake.previewGate
      return preview(app)
    },
    getFeedbackStatus: async () => ({ app: 'app1', app_ver: 'v1', items: [], reason: null }),
    getPeaks: async () => [],
  }
})

// 假图:x 轴第 i 根 K 线的中心在 100 + 10·i(竖带的像素由它换算)
const X0 = 100, BW = 10
function makeFakeChart() {
  const rec = { zr: {} as Record<string, ((e: any) => void)[]>, cursor: [] as string[] }
  fake.charts.push(rec)
  const zr = {
    on: (ev: string, h: (e: any) => void) => { (rec.zr[ev] ??= []).push(h) },
    off: vi.fn(),
    setCursorStyle: (c: string) => { rec.cursor.push(c) },
  }
  return {
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), clear: vi.fn(),
    on: vi.fn(), off: vi.fn(), getZr: () => zr, getOption: () => ({}),
    dispatchAction: vi.fn(),
    convertToPixel: (_f: unknown, v: unknown) => (typeof v === 'number' ? X0 + BW * v : [0, 0]),
    convertFromPixel: () => [0, 0],
    getWidth: () => 800, getHeight: () => 600,
    containPixel: (f: any) => fake.containMain && f?.gridIndex === 0,
  }
}
vi.mock('echarts', () => ({ init: vi.fn(() => makeFakeChart()) }))

import KlineChart from '../../src/components/KlineChart.vue'
import FeedbackPanel from '../../src/components/FeedbackPanel.vue'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useAppLinkStore } from '../../src/stores/appLink'
import { useFeedbackStore } from '../../src/stores/feedback'
import { useViewStore } from '../../src/stores/view'

function annRead(): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'p' }],
             charts: [{ symbol: 'AAA', boxes: [], samples: [], feedback: [
               { id: 'f-pc-1', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: DATES[7], end: DATES[9],
                 target: 'range', source: 'picked', note: 'why' } as any,
               { id: 'f-pc-2', pattern: 'p', app_id: 'app1', app_ver: 'v0', start: DATES[8], end: DATES[8],
                 target: 'point', source: 'picked', note: 'late' } as any,
             ] }] },
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

// jsdom 不排版:主图宽、图表区与显示栏的矩形由这里给
const WRAP = { left: 200, top: 50, right: 1200, bottom: 750 }
const BAR_TOP = 480
const MAIN_W = 1000
let restore: (() => void) | null = null
/** 主图宽 mainW;kline-wrap 与主图同占 WRAP 的矩形(主图与图表区左边对齐),显示栏上沿在 BAR_TOP */
function stubLayout(mainW = MAIN_W) {
  const cw = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth')!
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get(this: HTMLElement) { return this.classList?.contains('main-chart') ? mainW : cw.get!.call(this) },
  })
  const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const r = this.classList.contains('kline-wrap-v2') || this.classList.contains('main-chart') ? WRAP
      : this.getAttribute('data-testid') === 'walk-bar' ? { left: WRAP.left, top: BAR_TOP, right: WRAP.right, bottom: BAR_TOP + 20 }
        : { left: 0, top: 0, right: 0, bottom: 0 }
    return { ...r, x: r.left, y: r.top, width: r.right - r.left, height: r.bottom - r.top, toJSON: () => ({}) } as DOMRect
  })
  restore = () => {
    delete (HTMLElement.prototype as any).clientWidth
    rect.mockRestore()
  }
}

let w: VueWrapper<any> | null = null
/** 标注、mapping 读好,当前 pattern p,图挂上,在 compare 里打开 AAA(app 跑完)。 */
async function setup(mode: 'compare' | 'app' = 'compare') {
  const ann = useAnnotationStore()
  await ann.load()
  ann.setCurrentPattern('p')
  const appLink = useAppLinkStore()
  await appLink.load()
  const view = useViewStore()
  w = mount(KlineChart, { attachTo: document.body })
  view.openSymbol('AAA')
  await settle()
  appLink.setMode(mode)
  await settle()
  return { ann, appLink, view, fb: useFeedbackStore() }
}

const btn = () => w!.find('[data-testid="sel-feedback"]')
const band = () => w!.find('[data-testid="feedback-selected-band"]')
const bandPx = () => {
  const s = (band().element as HTMLElement).style
  return { left: parseFloat(s.left), width: parseFloat(s.width) }
}
/** 第 i0 ~ i1 根 K 线的竖带(相对 kline-wrap):整根 K 线对齐 */
const spanPx = (i0: number, i1: number) => ({ left: X0 + BW * i0 - BW / 2, width: BW * (i1 - i0 + 1) })
const enter = (target: EventTarget = document.body, init: KeyboardEventInit = {}) => {
  const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(e)
  return e
}

beforeEach(() => {
  setActivePinia(createPinia())
  fake.read = annRead()
  fake.previewGate = null
  fake.charts = []
  fake.containMain = false
  localStorage.clear()
  history.replaceState(null, '', '/')
  document.body.innerHTML = ''
  stubLayout()
})
afterEach(() => {
  w?.unmount()
  w = null
  restore?.()
  restore = null
})

describe('KlineChart · 对选中的那一个打开反馈面板', () => {
  it('前提:compare 下 app 跑完,显示栏有 feedback 按钮', async () => {
    const { view } = await setup()
    expect(view.mode).toBe('compare')
    expect(view.linkedRun).not.toBeNull()
    expect(btn().exists()).toBe(true)
  })

  it('Enter:选中买点日时打开 point 面板并吞掉这一下;按钮从 on 变成按下的样子', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    await settle()
    expect(btn().attributes('disabled')).toBeUndefined()
    expect(btn().classes()).not.toContain('on')
    const e = enter()
    expect(e.defaultPrevented).toBe(true)
    expect(fb.panel).toMatchObject({ symbol: 'AAA', start: DATES[4], end: DATES[4], target: 'point' })
    await settle()
    expect(w!.find('[data-testid="feedback-panel"]').exists()).toBe(true)
    expect(btn().classes()).toContain('on')
    expect(btn().attributes('aria-pressed')).toBe('true')
  })

  it('Enter:一族打开 family 面板;一条反馈打开那条', async () => {
    const { view, fb } = await setup()
    view.clickFamilyLine('hits@0')
    enter()
    expect(fb.panel).toMatchObject({ start: DATES[4], end: DATES[8], target: 'family', family_start: DATES[0] })
    fb.close()
    view.clickFeedback({ id: 'f-pc-1' })
    enter()
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', start: DATES[7], end: DATES[9] })
  })

  it('app 还没跑完:选中的反馈本身能作答,按钮仍灰、Enter 不开不吞键;跑完后才开', async () => {
    let release!: () => void
    fake.previewGate = new Promise<void>(r => { release = r })
    const { view, fb } = await setup()
    expect(view.mode).toBe('compare')
    expect(view.linkedRun).toBeNull()
    view.clickFeedback({ id: 'f-pc-1' })
    await settle()
    expect(fb.selTarget).toEqual({ id: 'f-pc-1' })      // 挡住它的只有「app 跑完」这一条
    expect(btn().attributes('disabled')).toBeDefined()
    expect(btn().classes()).toContain('off')
    expect(enter().defaultPrevented).toBe(false)
    expect(fb.panel).toBeNull()
    release()
    await settle()
    expect(view.linkedRun).not.toBeNull()
    expect(btn().attributes('disabled')).toBeUndefined()
    expect(enter().defaultPrevented).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1' })
  })

  it('不能作答(没选中、选中的是 event / node):Enter 不开、不吞键,按钮灰', async () => {
    const { view, fb } = await setup()
    expect(btn().attributes('disabled')).toBeDefined()
    expect(btn().classes()).toContain('off')
    expect(enter().defaultPrevented).toBe(false)
    expect(fb.panel).toBeNull()
    view.focusMark([T4.instance_id])
    await settle()
    expect(view.selLast?.kind).toBe('event')
    expect(btn().attributes('disabled')).toBeDefined()
    expect(enter().defaultPrevented).toBe(false)
    view.selectNode('today')
    await settle()
    expect(enter().defaultPrevented).toBe(false)
    expect(fb.panel).toBeNull()
  })

  it('焦点在下拉框、输入框、文本区里时 Enter 归它们,不开;带修饰键、组字中、按住不放的重复不开', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    for (const tag of ['select', 'input', 'textarea']) {
      const el = document.createElement(tag)
      document.body.appendChild(el)
      expect(enter(el).defaultPrevented).toBe(false)
      expect(fb.panel).toBeNull()
    }
    for (const init of [{ shiftKey: true }, { ctrlKey: true }, { altKey: true }, { metaKey: true },
                        { isComposing: true }, { keyCode: 229 }, { repeat: true }]) {
      expect(enter(document.body, init).defaultPrevented).toBe(false)
      expect(fb.panel).toBeNull()
    }
    enter()
    expect(fb.panel).not.toBeNull()
  })

  it('焦点停在别处的按钮、链接上:能作答时照样开面板,截下浏览器默认(不「点」那个按钮),放掉那个焦点', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    for (const tag of ['button', 'a']) {
      const el = document.createElement(tag)
      if (tag === 'a') el.setAttribute('href', '#x')
      const clicked = vi.fn()
      el.addEventListener('click', clicked)
      document.body.appendChild(el)
      el.focus()
      expect(document.activeElement).toBe(el)
      expect(enter(el).defaultPrevented).toBe(true)
      expect(fb.panel).toMatchObject({ start: DATES[4], end: DATES[4], target: 'point' })
      expect(document.activeElement).not.toBe(el)
      expect(clicked).not.toHaveBeenCalled()
      fb.close()
    }
  })

  it('焦点在对话框、pattern 选择框、右键菜单里的按钮上:不接(不开、不截默认、焦点留着),别处的按钮照旧开', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    const wraps: [string, (el: HTMLElement) => void][] = [
      ['div', el => el.classList.add('backdrop')],
      ['div', el => el.setAttribute('role', 'dialog')],
      ['dialog', el => el.setAttribute('open', '')],
      ['div', el => el.classList.add('pattern-picker')],
      ['div', el => el.classList.add('driver-menu')],
    ]
    for (const [tag, mark] of wraps) {
      const box = document.createElement(tag)
      mark(box)
      const inner = document.createElement('div')            // 按钮可以在里面好几层
      const b = document.createElement('button')
      inner.appendChild(b)
      box.appendChild(inner)
      document.body.appendChild(box)
      b.focus()
      expect(document.activeElement).toBe(b)
      expect(enter(b).defaultPrevented).toBe(false)
      expect(document.activeElement).toBe(b)
      expect(fb.panel).toBeNull()
    }
    const plain = document.createElement('button')
    document.body.appendChild(plain)
    plain.focus()
    expect(enter(plain).defaultPrevented).toBe(true)
    expect(fb.panel).not.toBeNull()
  })

  it('焦点在按钮上、选中的东西不能作答:不接,按钮照常吃 Enter(不截默认、焦点留着)', async () => {
    const { view, fb } = await setup()
    view.focusMark([T4.instance_id])                    // event:不能作答
    const el = document.createElement('button')
    document.body.appendChild(el)
    el.focus()
    expect(enter(el).defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(el)
    expect(fb.panel).toBeNull()
  })

  it('按住 Enter:第一下打开,后面的自动重复不保存(那条理由写着、按一下就能存),面板留着;松开再按一下才存', async () => {
    const { ann, view, fb } = await setup()
    view.clickFeedback({ id: 'f-pc-1' })
    await settle()
    const save = vi.spyOn(ann, 'saveFeedback')
    expect(enter().defaultPrevented).toBe(true)
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1', note: 'why' })
    const n = fb.opens
    await settle()                                       // 面板挂上了(它在捕获阶段截 Enter)
    expect(w!.find('[data-testid="feedback-panel"]').exists()).toBe(true)
    for (let i = 0; i < 5; i++) expect(enter(document.body, { repeat: true }).defaultPrevented).toBe(true)
    await settle()
    expect(save).not.toHaveBeenCalled()
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1' })
    expect(fb.opens).toBe(n)
    enter()
    await settle()
    expect(save).toHaveBeenCalledTimes(1)
    expect(fb.panel).toBeNull()
    // 面板关着时,按住不放的重复也不会再打开
    enter(document.body, { repeat: true })
    expect(fb.panel).toBeNull()
  })

  it('面板开着时 Enter 不在这里再开(归面板保存)', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    enter()
    const n = fb.opens
    view.clickBuyDay('hits@0', 8)                        // 不经面板的「点外面就关」,直接换选中
    await settle()
    enter()
    expect(fb.opens).toBe(n)
  })

  it('显示栏的 feedback 按钮:点了打开,再点关掉(不存)', async () => {
    const { ann, view, fb } = await setup()
    view.clickBuyDay('hits@0', 8)
    await settle()
    await btn().trigger('click')
    expect(fb.panel).toMatchObject({ start: DATES[8], end: DATES[8], target: 'point' })
    fb.setNote('草稿')
    await settle()
    await btn().trigger('click')
    expect(fb.panel).toBeNull()
    await ann.flushed()
    expect(ann.state!.charts[0].feedback).toHaveLength(2)      // 没存(还是预置的那两条)
  })

  it('面板开着时按下显示栏的 feedback 按钮不触发「点外面就关」,点击由按钮自己关', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 4)
    await settle()                                       // 按钮先亮起来(灰的时候点不了)
    await btn().trigger('click')
    expect(fb.panel).not.toBeNull()
    await settle()                                       // 面板「点外面就关」的监听已挂上
    const down = (el: Element) => el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    down(btn().element)
    await settle()                                       // 点面板外是延后关:等它那一轮过去
    expect(fb.panel).not.toBeNull()
    await btn().trigger('click')
    expect(fb.panel).toBeNull()
    // 对照:监听确实挂着,按在别处就关
    await btn().trigger('click')
    await settle()
    down(document.body)
    await settle()
    expect(fb.panel).toBeNull()
  })
})

describe('KlineChart · 面板开着时的竖带与落点', () => {
  it('竖带画面板管的那段日期;关了回到选中的那条反馈', async () => {
    const { view, fb } = await setup()
    view.clickFeedback({ id: 'f-pc-1' })
    await settle()
    expect(fb.selectedId).toBe('f-pc-1')
    expect(band().exists()).toBe(true)
    expect(bandPx()).toEqual(spanPx(7, 9))
    // 选中的反馈还在,对另一天打开面板:竖带换成面板那一天
    fb.open({ symbol: 'AAA', start: DATES[4], end: DATES[4], target: 'point' })
    await settle()
    expect(fb.selectedId).toBe('f-pc-1')
    expect(bandPx()).toEqual(spanPx(4, 4))
    fb.close()
    await settle()
    expect(bandPx()).toEqual(spanPx(7, 9))
  })

  it('没选中反馈时:面板开着有竖带,关了没有', async () => {
    const { view, fb } = await setup()
    view.clickFamilyLine('hits@0')
    await settle()
    expect(band().exists()).toBe(false)
    enter()
    await settle()
    expect(bandPx()).toEqual(spanPx(4, 8))
    fb.close()
    await settle()
    expect(band().exists()).toBe(false)
  })

  it('面板的 anchor:竖带的左右(视口坐标)、显示栏上沿、图表区左右;面板关了再开照样量', async () => {
    const { view, fb } = await setup()
    view.clickBuyDay('hits@0', 8)
    enter()
    await settle()
    const s = spanPx(8, 8)
    const anchor = () => w!.findComponent(FeedbackPanel).props('anchor')
    expect(anchor()).toEqual({ band: { left: WRAP.left + s.left, right: WRAP.left + s.left + s.width },
                               bottom: BAR_TOP, left: WRAP.left, right: WRAP.right })
    fb.close()
    await settle()
    view.clickFamilyLine('hits@0')
    enter()
    await settle()
    const f = spanPx(4, 8)
    expect(anchor()).toMatchObject({ band: { left: WRAP.left + f.left, right: WRAP.left + f.left + f.width } })
  })

  it('竖带整段在图区外:没有竖带,anchor 的 band 为 null(面板落在图表区正中)', async () => {
    restore?.()
    stubLayout(300)                                      // 主图只有 300 宽:图区右边到 284,第 20 根(中心 300)之后都在外面
    const { fb } = await setup()
    fb.open({ symbol: 'AAA', start: DATES[20], end: DATES[22], target: 'range' })
    await settle()
    expect(band().exists()).toBe(false)
    expect(w!.findComponent(FeedbackPanel).props('anchor')).toEqual({ band: null, bottom: BAR_TOP, left: WRAP.left,
                                                                       right: WRAP.right })
  })
})

describe('KlineChart · 改起止只认画出来的那条竖带', () => {
  // f-pc-1 是第 7~9 根:竖带左边在第 7 根中心往左半根
  const LEFT_EDGE = X0 + BW * 7 - BW / 2
  const cursorAt = (x: number) => {
    const main = fake.charts[0]
    const n = main.cursor.length
    for (const h of main.zr.mousemove ?? []) h({ offsetX: x, offsetY: 50 })
    return main.cursor.length > n ? main.cursor.at(-1)! : null
  }

  it('选中 f-pc-1、feedback 工具亮着:它的边是 ew-resize;面板开着对的是它自己时照旧', async () => {
    const { ann, view, fb } = await setup()
    fake.containMain = true
    view.clickFeedback({ id: 'f-pc-1' })
    await settle()
    ann.tool = 'feedback'
    await settle()
    expect(cursorAt(LEFT_EDGE)).toBe('ew-resize')
    expect(cursorAt(LEFT_EDGE + 15)).toBe('crosshair')      // 竖带正中(第 8 根):离两边都远
    enter()                                              // 对选中的那条(f-pc-1)打开
    await settle()
    expect(fb.panel?.editingId).toBe('f-pc-1')
    expect(cursorAt(LEFT_EDGE)).toBe('ew-resize')
  })

  it('路径 [f-pc-1 › 第 8 根],面板打开的是那天的 f-pc-2(同范围防重复):f-pc-1 的边不能拖', async () => {
    const { ann, view, fb } = await setup()
    fake.containMain = true
    view.setPath([{ kind: 'feedback', id: 'f-pc-1' }, { kind: 'buy', day: 8 }])
    await settle()
    expect(fb.selectedId).toBe('f-pc-1')
    ann.tool = 'feedback'
    await settle()
    expect(cursorAt(LEFT_EDGE)).toBe('ew-resize')        // 面板没开:选中那条的边能拖
    enter()
    await settle()
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-2', start: DATES[8], end: DATES[8] })
    expect(fb.selectedId).toBe('f-pc-1')
    expect(bandPx()).toEqual(spanPx(8, 8))               // 画出来的竖带是面板那一天
    expect(cursorAt(LEFT_EDGE)).toBe('crosshair')
  })
})

describe('KlineChart · 侧栏卡片的 edit 与 app 模式', () => {
  it('edit:图上有那条记号就选中并打开它;没有的不开', async () => {
    const { fb } = await setup()
    fb.requestEdit('f-pc-1')
    await settle()
    expect(fb.selectedId).toBe('f-pc-1')
    expect(fb.panel).toMatchObject({ editingId: 'f-pc-1' })
    expect(fb.editRequest).toBeNull()
    fb.close()
    fb.requestEdit('f-pc-9')
    await settle()
    expect(fb.panel).toBeNull()
  })

  it('app 模式:显示栏没有 feedback 按钮,Enter 不开', async () => {
    const { view, fb } = await setup('app')
    expect(view.mode).toBe('app')
    expect(w!.find('[data-testid="walk-bar"]').exists()).toBe(true)
    expect(btn().exists()).toBe(false)
    view.clickBuyDay('hits@0', 4)
    expect(enter().defaultPrevented).toBe(false)
    expect(fb.panel).toBeNull()
  })
})
