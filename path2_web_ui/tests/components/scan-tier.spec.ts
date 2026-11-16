// 顶栏 mode 四档 annotate / compare / app │ scan,以及扫描专用的按键和控件只在 scan 档起作用:
// - 顶栏:四个按钮、scan 前一道竖线;没有 app 时 compare、app 灰,scan 照样能点;有 app 时 app 是现算、scan 是扫描结果;
// - no_scan:没加载扫描时点 scan,图区写 no_scan、股票不带过去;在 scan 里删掉当前扫描也落到这里;
// - 扫描列表的敲字母搜股票、PageUp / PageDown 切股,Shift+P 参数抽屉,休眠草稿横幅:前三档不起作用,scan 档照旧。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TopBar from '../../src/components/TopBar.vue'
import ChartArea from '../../src/components/ChartArea.vue'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore } from '../../src/stores/view'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useAppLinkStore } from '../../src/stores/appLink'
import type { MultiScanResultFile } from '../../src/types'
import { SCAN_FILE } from '../fixtures'

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT', 'NVDA', 'TSLA'])),
  getRandom: vi.fn(() => Promise.resolve({ symbol: 'MSFT', start: '2023-01-03', end: '2023-12-28' })),
  getRally: vi.fn(() => Promise.resolve([])),
  getPeaks: vi.fn(() => Promise.resolve([])),
  getMappings: vi.fn(() => Promise.resolve([
    { app: 'bo_only', pattern: 'P', features: { 'w-pc-1': 'bo' }, problem: null },
  ])),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], hits: [] }, summary: {},
    pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {}, debug_enabled_nodes: [] },
    scan: { win_start: '1899-09-01', win_end: '2025-12-31', end_node: 'bo' },
  })),
  getDiagnose: vi.fn(() => Promise.resolve({ nodes: {} })),
  getAnnotations: vi.fn(() => new Promise(() => {})),
  getFeedbackStatus: vi.fn(() => new Promise(() => {})),
  postAnnotationBatch: vi.fn(),
}))

const DrawerStub = { name: 'WorkingCopyDrawer', template: '<div></div>', props: { open: Boolean } }
const STUBS = { KlineChart: true, DetailSidebar: true, TopologyControl: true, AnnotationSidebar: true,
                AnnotationNotices: true, WorkingCopyDrawer: DrawerStub }

/** SCAN_FILE 的结果换成这几只股票(顺序即扫描列表的默认顺序)。 */
function scanOf(symbols: string[]): MultiScanResultFile {
  return { ...SCAN_FILE, results: symbols.map(s => ({ ...SCAN_FILE.results[0], symbol: s })) }
}

const mounted: VueWrapper[] = []
function keep<T extends VueWrapper>(w: T): T { mounted.push(w); return w }
const btn = (w: VueWrapper, m: string) => w.get(`[data-testid="mode-${m}"]`)
function fireKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...opts })
  document.dispatchEvent(e)
  return e
}

/** 顶栏 + 图区,当前 pattern 是 pattern(P 有 app bo_only,别的没有)。 */
async function mountPage(pattern: string) {
  const top = keep(mount(TopBar))
  const area = keep(mount(ChartArea, { global: { stubs: STUBS } }))
  const links = useAppLinkStore()
  await links.load()
  useAnnotationStore().setCurrentPattern(pattern)
  await flushPromises()
  return { top, area, view: useViewStore(), links }
}

describe('顶栏 mode 四档与 scan 档', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  afterEach(() => { while (mounted.length) mounted.pop()!.unmount() })

  describe('顶栏', () => {
    it('四个按钮都在,scan 前有一道竖线', async () => {
      const { top } = await mountPage('NONE')
      const group = top.get('[data-testid="mode-group"]')
      const order = group.findAll('[data-testid^="mode-"]').map(e => e.attributes('data-testid'))
      expect(order).toEqual(['mode-annotate', 'mode-compare', 'mode-app', 'mode-sep', 'mode-scan'])
    })

    it('没有 app:compare、app 灰,scan 可点', async () => {
      const { top, view } = await mountPage('NONE')
      view.openSymbol('AAPL')
      await flushPromises()
      for (const m of ['compare', 'app']) {
        expect(btn(top, m).attributes('disabled')).toBeDefined()
        expect(btn(top, m).classes()).toContain('off')
      }
      expect(btn(top, 'scan').attributes('disabled')).toBeUndefined()
      expect(btn(top, 'scan').classes()).not.toContain('off')
    })

    it('有 app:点 app 进的是现算(顶栏写着 app 名);点 scan 进的是扫描视图', async () => {
      const { top, view } = await mountPage('P')
      view.loadScanFile(scanOf(['AAPL', 'MSFT']))
      view.openSymbol('MSFT')
      await flushPromises()
      await btn(top, 'app').trigger('click')
      await flushPromises()
      expect([view.mode, view.appSource]).toEqual(['app', 'linked'])
      expect(btn(top, 'app').classes()).toContain('on')
      expect(top.get('[data-testid="linked-app"]').text()).toBe('bo_only')
      expect(btn(top, 'app').attributes('title')).toContain('run now on this symbol')
      await btn(top, 'scan').trigger('click')
      await flushPromises()
      expect([view.mode, view.appSource, view.symbol]).toEqual(['app', 'scan', 'MSFT'])
      expect(btn(top, 'scan').classes()).toContain('on')
      expect(btn(top, 'app').classes()).not.toContain('on')
      expect(top.find('[data-testid="linked-app"]').exists()).toBe(false)
    })
  })

  describe('no_scan', () => {
    it('没加载扫描时点 scan:图区写 no_scan,股票不带过去;有 app 时 compare、app 仍可点,回去是原来那只', async () => {
      const { top, area, view } = await mountPage('P')
      view.openSymbol('TSLA')
      await flushPromises()
      expect(area.find('[data-testid="no-scan"]').exists()).toBe(false)
      await btn(top, 'scan').trigger('click')
      await flushPromises()
      expect(area.get('[data-testid="no-scan"]').text()).toBe('no_scan')
      expect(view.symbol).toBeNull()
      expect((top.get('[data-testid="symbol-input"]').element as HTMLInputElement).value).toBe('')
      expect(btn(top, 'compare').attributes('disabled')).toBeUndefined()
      await btn(top, 'compare').trigger('click')
      await flushPromises()
      expect([view.mode, view.symbol]).toEqual(['compare', 'TSLA'])
      expect(area.find('[data-testid="no-scan"]').exists()).toBe(false)
    })

    it('在 scan 里删掉当前扫描:落到 no_scan,不回 annotate', async () => {
      const { top, area, view } = await mountPage('NONE')
      view.loadScanFile(scanOf(['AAPL', 'MSFT']))
      await flushPromises()
      expect(area.find('[data-testid="no-scan"]').exists()).toBe(false)
      view.clearScanFile()                    // 扫描历史对话框删掉当前扫描时调的就是它
      await flushPromises()
      expect(area.get('[data-testid="no-scan"]').text()).toBe('no_scan')
      expect(btn(top, 'scan').classes()).toContain('on')
      expect(view.symbol).toBeNull()
    })
  })

  describe('扫描列表的按键只在 scan 档', () => {
    async function mountList() {
      const list = keep(mount(SidebarResultList, { attachTo: document.body }))
      await flushPromises()
      const input = list.get('[data-testid="symbol-search"]').element as HTMLInputElement
      return { list, input, view: useViewStore() }
    }

    it('拦:前三档敲字母不进搜索框', async () => {
      const view = useViewStore()
      view.loadScanFile(scanOf(['AAPL', 'MSFT']))
      view.openSymbol('TSLA')
      const { input } = await mountList()
      ;(document.activeElement as HTMLElement | null)?.blur?.()
      const e = fireKey('a')
      await flushPromises()
      expect(view.symbolQuery).toBe('')
      expect(document.activeElement).not.toBe(input)
      expect(e.defaultPrevented).toBe(false)
    })

    it('放:scan 档敲字母照旧搜股票', async () => {
      const view = useViewStore()
      view.loadScanFile(scanOf(['AAPL', 'MSFT']))
      const { input } = await mountList()
      ;(document.activeElement as HTMLElement | null)?.blur?.()
      fireKey('m')
      await flushPromises()
      expect(view.symbolQuery).toBe('m')
      expect(document.activeElement).toBe(input)
    })

    it('拦:前三档 PageUp / PageDown 不切股、不离开当前档', async () => {
      const view = useViewStore()
      view.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      view.selectSymbol('MSFT')
      view.enterAnnotate()                    // 带着 MSFT 回 annotate(它在扫描列表里)
      await mountList()
      for (const key of ['PageDown', 'PageUp']) {
        const e = fireKey(key)
        await flushPromises()
        expect([view.mode, view.symbol]).toEqual(['annotate', 'MSFT'])
        expect(e.defaultPrevented).toBe(false)
      }
    })

    it('放:scan 档 PageUp / PageDown 照旧切股', async () => {
      const view = useViewStore()
      view.loadScanFile(scanOf(['AAPL', 'MSFT', 'NVDA']))
      await mountList()
      fireKey('PageDown')
      await flushPromises()
      expect([view.scanView, view.symbol]).toEqual([true, 'MSFT'])
      fireKey('PageUp')
      await flushPromises()
      expect(view.symbol).toBe('AAPL')
    })
  })

  describe('Shift+P 参数抽屉只在 scan 档', () => {
    const shiftP = () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', shiftKey: true }))

    it('拦:annotate、compare 里 Shift+P 不开抽屉', async () => {
      const { area, view, links } = await mountPage('P')
      view.loadScanFile(scanOf(['AAPL']))
      view.openSymbol('AAPL')
      await flushPromises()
      const drawer = area.findComponent({ name: 'WorkingCopyDrawer' })
      shiftP()
      await flushPromises()
      expect(drawer.props('open')).toBe(false)
      links.setMode('compare')
      await flushPromises()
      shiftP()
      await flushPromises()
      expect(drawer.props('open')).toBe(false)
    })

    it('放:scan 档 Shift+P 开关抽屉;开着离开 scan 档就关上', async () => {
      const { area, view } = await mountPage('NONE')
      view.loadScanFile(scanOf(['AAPL']))
      await flushPromises()
      const drawer = area.findComponent({ name: 'WorkingCopyDrawer' })
      shiftP()
      await flushPromises()
      expect(drawer.props('open')).toBe(true)
      shiftP()
      await flushPromises()
      expect(drawer.props('open')).toBe(false)
      shiftP()
      await flushPromises()
      view.enterAnnotate()
      await flushPromises()
      view.enterScan()
      await flushPromises()
      expect(drawer.props('open')).toBe(false)
    })
  })

  describe('扫描的休眠草稿横幅只在 scan 档', () => {
    function withDraft(): MultiScanResultFile {
      const f = scanOf(['AAPL'])
      localStorage.setItem(`p2wc:${f.scan.scan_ts}:${f.pattern_ids[0]}`, JSON.stringify({ dict: {}, baseline: {}, savedAt: 1 }))
      return f
    }

    it('拦:compare 里没有休眠草稿横幅', async () => {
      const { area, view, links } = await mountPage('P')
      view.loadScanFile(withDraft())
      view.openSymbol('AAPL')
      links.setMode('compare')
      await flushPromises()
      expect(view.dormantDrafts.length).toBe(1)
      expect(area.find('[data-testid="level-control"]').exists()).toBe(true)
      expect(area.find('[data-testid="dormant-banner"]').exists()).toBe(false)
    })

    it('放:scan 档横幅照常出现', async () => {
      const { area, view } = await mountPage('NONE')
      view.loadScanFile(withDraft())
      await flushPromises()
      expect(area.find('[data-testid="dormant-banner"]').exists()).toBe(true)
    })
  })
})
