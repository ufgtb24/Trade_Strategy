// 左右栏的收起与拖宽(components/ColumnEdge.vue、LeftPanel.vue、ChartArea.vue、columnKeys.ts;几何在 columnLayout.ts):
// - 左栏在四档里都能用箭头收起、点窄边打开;标注侧栏在 annotate、compare 里同样;app、scan 的诊断侧栏没有小箭头,
//   显隐照旧归 Sidebar 按钮;
// - Shift+L、Shift+R:焦点在单行、多行输入框、下拉框里不响应,不在时响应;Shift+R 在 app、scan 不起作用;
// - 右栏收着时选中不自动打开,打开时停在 selection 页、显示的是那个框;
// - 拖边:左栏按「拖出的宽度 ≤ 内容全宽」截露出宽度,拖到最窄停在固定宽度、不收起,拖过全宽记成全开;
//   右栏拖窄停在各自的最窄;三份宽度互不影响;收起、变窄只藏不拆。
// jsdom 没有排版:列被遮、没有横向滚动条、换到窄页露出宽度跟着缩、内容换行,这些真几何在 e2e/columns.spec.ts;
// 这里给 getBoundingClientRect 注入量出来的宽度,只核算出来的数。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ColumnEdge from '../../src/components/ColumnEdge.vue'
import LeftPanel from '../../src/components/LeftPanel.vue'
import ChartArea from '../../src/components/ChartArea.vue'
import { onColumnKey } from '../../src/components/columnKeys'
import { ANN_DEFAULT, ANN_MIN, DETAIL_DEFAULT, DETAIL_MIN, LEFT_MIN } from '../../src/components/columnLayout'
import { useViewStore } from '../../src/stores/view'
import { usePanelsStore } from '../../src/stores/panels'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useFinderStore } from '../../src/stores/finder'
import type { AnnRead, AnnState } from '../../src/annotate/model'
import { scanOf } from '../fixtures'

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT'])),
  getRally: vi.fn(() => Promise.resolve([])),
  getRandom: vi.fn(),
  getPeaks: vi.fn(() => Promise.resolve([])),
  getMappings: vi.fn(() => Promise.resolve([])),
  getAnnotations: vi.fn(() => new Promise(() => {})),
  getFeedbackStatus: vi.fn(() => new Promise(() => {})),
  postAnnotationBatch: vi.fn(),
}))

const STATE: AnnState = {
  machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'W底' }],
  charts: [{ symbol: 'MSFT', boxes: [{ id: 'b-pc-1', feature: null, start: '2024-02-01', end: '2024-02-20' }],
             samples: [{ id: 's-pc-1', date: '2024-02-20', pattern: 'W底', judgment: 'pos', members: [] }] }],
}
function readOf(state: AnnState): AnnRead {
  return {
    state, conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {}, feedback: {} }, next_seq: 10, ignored_files: [],
    membership: { gap: 20, near: 40 }, match: { pos: 3, neg: 1, sub: 2 },
  }
}

const mounted: VueWrapper[] = []
function keep<T extends VueWrapper>(w: T): T { mounted.push(w); return w }
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  window.addEventListener('keydown', onColumnKey)
})
afterEach(() => {
  window.removeEventListener('keydown', onColumnKey)
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

type Tier = 'annotate' | 'compare' | 'app' | 'scan'
function setTier(t: Tier) {
  const view = useViewStore()
  if (t === 'scan') { view.loadScanFile(scanOf(['AAPL', 'MSFT'])); view.mode = 'app' }
  else if (t === 'app') { view.mode = 'app'; view.appSource = 'linked' }
  else view.mode = t
}
const tierOf = () => { const v = useViewStore(); return v.scanView ? 'scan' : v.mode }

/** 给元素注入量出来的宽度(jsdom 的 getBoundingClientRect 恒为 0)。 */
function fakeWidth(el: Element, width: number) {
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({ width } as DOMRect)
}
/** jsdom 没有 PointerEvent:用 MouseEvent 带上 pointerId。 */
const pointer = (type: string, clientX: number) =>
  Object.assign(new MouseEvent(type, { button: 0, clientX, bubbles: true, cancelable: true }), { pointerId: 1 })
/** 在边上按住、横向拖 dx、松开(指针事件,同真浏览器的顺序)。 */
async function dragEdge(edge: Element, dx: number) {
  edge.dispatchEvent(pointer('pointerdown', 500))
  edge.dispatchEvent(pointer('pointermove', 500 + dx / 2))
  edge.dispatchEvent(pointer('pointermove', 500 + dx))
  edge.dispatchEvent(pointer('pointerup', 500 + dx))
  await flushPromises()
}
function key(code: 'KeyL' | 'KeyR', target: Element | Document = document.activeElement ?? document) {
  const e = new KeyboardEvent('keydown', { key: code === 'KeyL' ? 'L' : 'R', code, shiftKey: true, bubbles: true, cancelable: true })
  target.dispatchEvent(e)
  return e
}

function mountLeft() {
  useAnnotationStore().server = readOf(STATE)
  return keep(mount(LeftPanel, { attachTo: document.body }))
}
function mountChart() {
  useAnnotationStore().server = readOf(STATE)
  return keep(mount(ChartArea, {
    attachTo: document.body,
    global: { stubs: { KlineChart: true, TopologyControl: true, DetailSidebar: { template: '<div class="sidebar" data-testid="detail-sidebar" />' } } },
  }))
}
const shown = (w: VueWrapper, tid: string) => w.get(`[data-testid="${tid}"]`).isVisible()

describe('ColumnEdge', () => {
  it('能收起的边:点箭头发 toggle;收起后整条窄边可点、不能拖;开着时点边本身不 toggle', async () => {
    const w = keep(mount(ColumnEdge, { props: { side: 'left', tid: 'e', collapsible: true, collapsed: false } }))
    expect(w.get('[data-testid="e-toggle"]').text()).toBe('‹')
    await w.get('[data-testid="e"]').trigger('click')
    expect(w.emitted('toggle')).toBeUndefined()
    await w.get('[data-testid="e-toggle"]').trigger('click')
    expect(w.emitted('toggle')).toHaveLength(1)
    await w.setProps({ collapsed: true })
    expect(w.get('[data-testid="e-toggle"]').text()).toBe('›')
    await w.get('[data-testid="e"]').trigger('click')
    expect(w.emitted('toggle')).toHaveLength(2)
    await dragEdge(w.get('[data-testid="e"]').element, 40)
    expect(w.emitted('dragstart')).toBeUndefined()
  })

  it('开着时拖:发 dragstart、相对按下处的位移、dragend;右栏箭头方向反过来;不能收起的边没有箭头', async () => {
    const w = keep(mount(ColumnEdge, { props: { side: 'right', tid: 'e', collapsible: true } }))
    expect(w.get('[data-testid="e-toggle"]').text()).toBe('›')
    await dragEdge(w.get('[data-testid="e"]').element, -60)
    expect(w.emitted('dragstart')).toHaveLength(1)
    expect(w.emitted('drag')!.map(a => a[0])).toEqual([-30, -60])
    expect(w.emitted('dragend')).toHaveLength(1)
    const plain = keep(mount(ColumnEdge, { props: { side: 'right', tid: 'p' } }))
    expect(plain.find('[data-testid="p-toggle"]').exists()).toBe(false)
  })
})

describe('左栏 · 收起', () => {
  for (const t of ['annotate', 'compare', 'app', 'scan'] as Tier[]) {
    it(`${t}:点箭头收起(只剩窄边),点窄边打开`, async () => {
      setTier(t)
      const w = mountLeft()
      await flushPromises()
      expect(tierOf()).toBe(t)
      expect(shown(w, 'left-clip')).toBe(true)
      await w.get('[data-testid="left-edge-toggle"]').trigger('click')
      expect(shown(w, 'left-clip')).toBe(false)
      expect(shown(w, 'left-edge')).toBe(true)
      expect(usePanelsStore().leftCollapsed).toBe(true)
      await w.get('[data-testid="left-edge"]').trigger('click')
      expect(shown(w, 'left-clip')).toBe(true)
      expect(usePanelsStore().leftCollapsed).toBe(false)
    })
  }

  it('只藏不拆:收起再打开,找图清单的页签还在,清单组件没有重挂', async () => {
    const w = mountLeft()
    await w.get('[data-testid="finder-tab-charts"]').trigger('click')
    const page = w.get('[data-testid="finder-page-charts"]').element
    await w.get('[data-testid="left-edge-toggle"]').trigger('click')
    await w.get('[data-testid="left-edge"]').trigger('click')
    expect(useFinderStore().tab).toBe('charts')
    expect(w.get('[data-testid="finder-page-charts"]').element).toBe(page)
    expect(shown(w, 'finder-page-charts')).toBe(true)
  })
})

describe('左栏 · 抽屉(注入量出来的宽度)', () => {
  /** 量到的:露出 exposed、内容全宽 full。 */
  function measured(w: VueWrapper, exposed: number, full: number) {
    fakeWidth(w.get('[data-testid="left-clip"]').element, exposed)
    fakeWidth(w.get('[data-testid="left-drawer"]').element, full)
  }
  const maxWidth = (w: VueWrapper) => (w.get('[data-testid="left-clip"]').element as HTMLElement).style.maxWidth

  it('没拖过时全开(不截);rally 页从全宽 348 往里拖 120:露出 228;拖出的宽度记下来', async () => {
    const w = mountLeft()
    expect(maxWidth(w)).toBe('')
    measured(w, 348, 348)
    await dragEdge(w.get('[data-testid="left-edge"]').element, -120)
    expect(usePanelsStore().leftWidth).toBe(228)
    expect(maxWidth(w)).toBe('228px')
  })

  it('拖到最窄就停在固定宽度,不收起', async () => {
    const w = mountLeft()
    measured(w, 348, 348)
    await dragEdge(w.get('[data-testid="left-edge"]').element, -600)
    expect(usePanelsStore().leftWidth).toBe(LEFT_MIN)
    expect(maxWidth(w)).toBe(`${LEFT_MIN}px`)
    expect(usePanelsStore().leftCollapsed).toBe(false)
    expect(shown(w, 'left-clip')).toBe(true)
  })

  it('往外拖到或超过内容全宽:记成全开(换到更宽的内容也全开)', async () => {
    const w = mountLeft()
    measured(w, 228, 348)
    await dragEdge(w.get('[data-testid="left-edge"]').element, 400)
    expect(usePanelsStore().leftWidth).toBeNull()
    expect(maxWidth(w)).toBe('')
  })

  it('三页、四档共用一个数:换页签、切到 scan 档,截的宽度不变;同一时刻只显示当前页(内容全宽按当前页定)', async () => {
    const w = mountLeft()
    measured(w, 348, 348)
    await dragEdge(w.get('[data-testid="left-edge"]').element, -100)
    for (const t of ['random', 'charts', 'rally']) {
      await w.get(`[data-testid="finder-tab-${t}"]`).trigger('click')
      expect(maxWidth(w)).toBe('248px')
      expect(['rally', 'random', 'charts'].filter(p => shown(w, `finder-page-${p}`))).toEqual([t])
    }
    setTier('scan')
    await flushPromises()
    expect(shown(w, 'scan-side')).toBe(true)
    expect(maxWidth(w)).toBe('248px')
  })
})

describe('右栏 · 收起与拖宽', () => {
  for (const t of ['annotate', 'compare'] as Tier[]) {
    it(`${t}:标注侧栏点箭头收起,点窄边打开`, async () => {
      setTier(t)
      const w = mountChart()
      expect(shown(w, 'annotation-sidebar')).toBe(true)
      await w.get('[data-testid="ann-edge-toggle"]').trigger('click')
      expect(shown(w, 'annotation-sidebar')).toBe(false)
      expect(shown(w, 'ann-edge')).toBe(true)
      await w.get('[data-testid="ann-edge"]').trigger('click')
      expect(shown(w, 'annotation-sidebar')).toBe(true)
    })
  }

  for (const t of ['app', 'scan'] as Tier[]) {
    it(`${t}:诊断侧栏有拖边、没有小箭头;显隐照旧归 Sidebar 按钮`, async () => {
      setTier(t)
      const w = mountChart()
      expect(w.find('[data-testid="detail-sidebar"]').exists()).toBe(false)
      expect(w.find('[data-testid="detail-edge"]').exists()).toBe(false)
      await w.get('[data-testid="panel-toggle-sidebar"]').trigger('click')
      expect(w.find('[data-testid="detail-sidebar"]').exists()).toBe(true)
      expect(w.find('[data-testid="detail-edge"]').exists()).toBe(true)
      expect(w.find('[data-testid="detail-edge-toggle"]').exists()).toBe(false)
      expect(w.find('[data-testid="ann-edge"]').exists()).toBe(false)
      await w.get('[data-testid="panel-toggle-sidebar"]').trigger('click')
      expect(w.find('[data-testid="detail-sidebar"]').exists()).toBe(false)
    })
  }

  it('右栏收着时选中框、选中样本都不自动打开;打开时停在 selection 页、显示的是最后选中的那个', async () => {
    const w = mountChart()
    const ann = useAnnotationStore()
    useViewStore().symbol = 'MSFT'
    await w.get('[data-testid="annotation-tab-features"]').trigger('click')
    await w.get('[data-testid="ann-edge-toggle"]').trigger('click')
    ann.selectSample('s-pc-1')
    await flushPromises()
    ann.selectBox('b-pc-1')
    await flushPromises()
    expect(usePanelsStore().annCollapsed).toBe(true)
    expect(shown(w, 'annotation-sidebar')).toBe(false)
    expect(ann.tab).toBe('selection')
    await w.get('[data-testid="ann-edge"]').trigger('click')
    expect(shown(w, 'annotation-sidebar')).toBe(true)
    expect(w.get('[data-testid="annotation-tab-selection"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="annotation-page-selection"] [data-testid="box-panel"]').exists()
      || w.get('[data-testid="annotation-page-selection"]').text().includes('2024-02-01')).toBe(true)
  })

  it('标注侧栏:没拖过 320;往左拖 80 变 400;拖窄停在最窄', async () => {
    const w = mountChart()
    const side = () => w.get('[data-testid="annotation-sidebar"]').element as HTMLElement
    expect(side().style.width).toBe(`${ANN_DEFAULT}px`)
    fakeWidth(side(), ANN_DEFAULT)
    await dragEdge(w.get('[data-testid="ann-edge"]').element, -80)
    expect(side().style.width).toBe('400px')
    fakeWidth(side(), 400)
    await dragEdge(w.get('[data-testid="ann-edge"]').element, 900)
    expect(usePanelsStore().annWidth).toBe(ANN_MIN)
    expect(side().style.width).toBe(`${ANN_MIN}px`)
    expect(usePanelsStore().annCollapsed).toBe(false)
  })

  it('诊断侧栏:没拖过 280;拖窄停在最窄;另记一份,不动标注侧栏和左栏的宽度', async () => {
    usePanelsStore().annWidth = ANN_MIN
    setTier('app')
    usePanelsStore().showSidebar = true
    const w = mountChart()
    await flushPromises()
    const detail = () => w.get('[data-testid="detail-sidebar"]').element as HTMLElement
    expect(detail().style.width).toBe(`${DETAIL_DEFAULT}px`)
    fakeWidth(detail(), DETAIL_DEFAULT)
    await dragEdge(w.get('[data-testid="detail-edge"]').element, 500)
    expect(usePanelsStore().detailWidth).toBe(DETAIL_MIN)
    expect(usePanelsStore().annWidth).toBe(ANN_MIN)
    expect(usePanelsStore().leftWidth).toBeNull()
  })

  it('最多半屏:往左拖过半屏停在半屏', async () => {
    const w = mountChart()
    fakeWidth(w.get('[data-testid="annotation-sidebar"]').element, ANN_DEFAULT)
    await dragEdge(w.get('[data-testid="ann-edge"]').element, -5000)
    expect(usePanelsStore().annWidth).toBe(Math.round(window.innerWidth / 2))
  })
})

describe('Shift+L / Shift+R', () => {
  function editables() {
    const input = document.createElement('input')
    const area = document.createElement('textarea')
    const select = document.createElement('select')
    select.appendChild(document.createElement('option'))
    document.body.append(input, area, select)
    return { input, area, select }
  }

  it('焦点在单行、多行输入框、下拉框里:两个键都不响应,也不吞掉按键', async () => {
    const panels = usePanelsStore()
    for (const el of Object.values(editables())) {
      el.focus()
      expect(document.activeElement).toBe(el)
      expect(key('KeyL', el).defaultPrevented).toBe(false)
      expect(key('KeyR', el).defaultPrevented).toBe(false)
      expect([panels.leftCollapsed, panels.annCollapsed]).toEqual([false, false])
    }
  })

  it('自绘下拉的菜单开着时也不响应', () => {
    const btn = document.createElement('button')
    btn.setAttribute('aria-expanded', 'true')
    document.body.append(btn)
    key('KeyL', document.body)
    expect(usePanelsStore().leftCollapsed).toBe(false)
  })

  it('焦点不在输入框里:Shift+L 收起 / 打开左栏,Shift+R 收起 / 打开标注侧栏,左右各管各', () => {
    const panels = usePanelsStore()
    expect(key('KeyL', document.body).defaultPrevented).toBe(true)
    expect([panels.leftCollapsed, panels.annCollapsed]).toEqual([true, false])
    key('KeyR', document.body)
    expect([panels.leftCollapsed, panels.annCollapsed]).toEqual([true, true])
    key('KeyL', document.body)
    expect([panels.leftCollapsed, panels.annCollapsed]).toEqual([false, true])
    key('KeyR', document.body)
    expect([panels.leftCollapsed, panels.annCollapsed]).toEqual([false, false])
  })

  it('compare 下 Shift+R 也起作用', () => {
    setTier('compare')
    key('KeyR', document.body)
    expect(usePanelsStore().annCollapsed).toBe(true)
  })

  for (const t of ['app', 'scan'] as Tier[]) {
    it(`${t}:Shift+R 不起作用,Shift+L 照常`, () => {
      setTier(t)
      expect(tierOf()).toBe(t)
      const panels = usePanelsStore()
      expect(key('KeyR', document.body).defaultPrevented).toBe(false)
      expect(panels.annCollapsed).toBe(false)
      key('KeyL', document.body)
      expect(panels.leftCollapsed).toBe(true)
    })
  }

  it('不带 Shift、带别的修饰键、按住连发都不接', () => {
    const panels = usePanelsStore()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', code: 'KeyL', bubbles: true }))
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'L', code: 'KeyL', shiftKey: true, ctrlKey: true, bubbles: true }))
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'L', code: 'KeyL', shiftKey: true, repeat: true, bubbles: true }))
    expect(panels.leftCollapsed).toBe(false)
  })
})
