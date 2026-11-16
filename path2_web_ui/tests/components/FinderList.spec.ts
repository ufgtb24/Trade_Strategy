// 标注三档的左栏:找图清单 rally / random / charts(components/FinderList.vue、LeftPanel.vue):
// - 打开时落在 rally 页;rally 每行写这张图窗里标过的 pattern 名和框数,悬停 pattern 名列出样本;
// - random 页按抽的先后列出这次用顶栏 random 抽过的图,只在页面内存里(刷新即新的 store,为空;不写浏览器存储);
// - charts 页列出全部标过的股票;
// - 点一行、PageUp / PageDown 换图不换档(annotate、compare、现算的 app 各一条);
// - 焦点在单行、多行输入框、下拉框里时翻页键不切;scan 档里这里的翻页键不接;
// - compare 下左栏没有 app 的任何结果(扫描列表的命中、收益列都不出现);切到 scan 档、再切回来,页签还在。
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import FinderList from '../../src/components/FinderList.vue'
import LeftPanel from '../../src/components/LeftPanel.vue'
import TopBar from '../../src/components/TopBar.vue'
import { useViewStore } from '../../src/stores/view'
import { useAnnotationStore } from '../../src/stores/annotation'
import { useFinderStore } from '../../src/stores/finder'
import type { AnnRead, AnnState } from '../../src/annotate/model'
import type { RallyItem } from '../../src/types'
import { scanOf } from '../fixtures'
import * as api from '../../src/api'

const RALLY: RallyItem[] = [
  { symbol: 'MSFT', date: '2024-03-01', peak_date: '2024-03-20', rise: 0.5, rel: 2.5,
    view_start: '2023-09-12', view_end: '2024-04-26' },
  { symbol: 'AAPL', date: '2025-01-02', peak_date: '2025-02-10', rise: 1.2, rel: 3.1,
    view_start: '2024-07-11', view_end: '2025-02-28' },
  { symbol: 'NVDA', date: '2023-05-01', peak_date: '2023-06-01', rise: 0.3, rel: 2.0,
    view_start: '2022-11-01', view_end: '2023-06-30' },
]
const DRAWS = [
  { symbol: 'TSLA', start: '2023-01-03', end: '2023-12-28' },
  { symbol: 'AAPL', start: '2022-02-01', end: '2023-01-31' },
]

vi.mock('../../src/api', () => ({
  getSymbols: vi.fn(() => Promise.resolve(['AAPL', 'MSFT', 'NVDA', 'TSLA'])),
  getRally: vi.fn(() => Promise.resolve(RALLY)),
  getRandom: vi.fn(),
  getPeaks: vi.fn(() => Promise.resolve([])),
  getMappings: vi.fn(() => Promise.resolve([])),
  getAnnotations: vi.fn(() => new Promise(() => {})),
  getFeedbackStatus: vi.fn(() => new Promise(() => {})),
  postAnnotationBatch: vi.fn(),
}))

// MSFT:rally 图窗(2023-09-12..2024-04-26)里有 W底 的两个样本和一个框,窗外有一个 平台 样本;
// AAPL:只画了一个框(落在 rally 图窗里);TSLA:什么都没标
const STATE: AnnState = {
  machine: 'pc', data_fingerprint: null, features: [], patterns: [{ name: 'W底' }, { name: '平台' }],
  charts: [
    { symbol: 'MSFT',
      boxes: [{ id: 'b-pc-1', feature: null, start: '2024-02-01', end: '2024-02-20' }],
      samples: [{ id: 's-pc-1', date: '2024-02-20', pattern: 'W底', judgment: 'pos', members: [] },
                { id: 's-pc-2', date: '2023-12-01', pattern: 'W底', judgment: 'neg', members: [] },
                { id: 's-pc-3', date: '2024-08-01', pattern: '平台', judgment: 'pos', members: [] }] },
    { symbol: 'AAPL', boxes: [{ id: 'b-pc-2', feature: null, start: '2024-09-03', end: '2024-09-20' }], samples: [] },
  ],
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
afterEach(() => { while (mounted.length) mounted.pop()!.unmount(); document.body.innerHTML = '' })
beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function fireKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...opts })
  ;(document.activeElement ?? document).dispatchEvent(e)
  return e
}

async function mountFinder() {
  useAnnotationStore().server = readOf(STATE)
  const w = keep(mount(FinderList, { attachTo: document.body }))
  await flushPromises()
  return { w, view: useViewStore(), finder: useFinderStore() }
}
const rows = (w: VueWrapper, page: string) => w.findAll(`[data-testid="${page}-row"]`)
const cells = (w: VueWrapper, page: string, tid: string) =>
  rows(w, page).map(r => r.get(`[data-testid="${tid}"]`).text())
type Tier = 'annotate' | 'compare' | 'app'
function setTier(view: ReturnType<typeof useViewStore>, t: Tier) {
  if (t === 'app') { view.mode = 'app'; view.appSource = 'linked' } else view.mode = t
}
const tierOf = (view: ReturnType<typeof useViewStore>) =>
  (view.scanView ? 'scan' : view.mode)

describe('FinderList · 三页的内容', () => {
  it('打开时落在 rally 页:三个页签,rally 选中;按 rise 降序;一打开就取一次清单', async () => {
    const { w } = await mountFinder()
    expect(w.findAll('[role="tab"]').map(t => t.text())).toEqual(['rally', 'random', 'charts'])
    expect(w.get('[data-testid="finder-tab-rally"]').attributes('aria-selected')).toBe('true')
    expect(w.get('[data-testid="finder-page-rally"]').isVisible()).toBe(true)
    expect(w.get('[data-testid="finder-page-random"]').isVisible()).toBe(false)
    expect(rows(w, 'rally').map(r => r.attributes('data-symbol'))).toEqual(['AAPL', 'MSFT', 'NVDA'])
    expect(w.findAll('[data-testid="finder-page-rally"] th').map(t => t.text().replace(/[▲▼]/, '')))
      .toEqual(['symbol', 'date', 'rise', 'patterns', 'boxes'])
    expect(api.getRally).toHaveBeenCalledTimes(1)
  })

  it('rally:点表头换序,再点反向', async () => {
    const { w } = await mountFinder()
    await w.get('[data-testid="rally-sort-symbol"]').trigger('click')
    expect(rows(w, 'rally').map(r => r.attributes('data-symbol'))).toEqual(['AAPL', 'MSFT', 'NVDA'])
    await w.get('[data-testid="rally-sort-symbol"]').trigger('click')
    expect(rows(w, 'rally').map(r => r.attributes('data-symbol'))).toEqual(['NVDA', 'MSFT', 'AAPL'])
  })

  it('rally:清单为空 → empty;取失败 → load_failed', async () => {
    vi.mocked(api.getRally).mockImplementationOnce(() => Promise.resolve([]))
    const first = await mountFinder()
    expect(first.w.get('[data-testid="rally-status"]').text()).toBe('empty')
    first.w.unmount(); mounted.length = 0
    setActivePinia(createPinia())
    vi.mocked(api.getRally).mockImplementationOnce(() => Promise.reject(new Error('x')))
    const second = await mountFinder()
    expect(second.w.get('[data-testid="rally-status"]').text()).toBe('load_failed')
  })

  it('rally:标过按这一行的图窗算;只画了框的行有框数、没有 pattern 名;悬停 pattern 名列出样本', async () => {
    const { w } = await mountFinder()
    // AAPL 只画了框;MSFT 图窗里有 W底(窗外的 平台 不计)和一个框;NVDA 没标过
    expect(cells(w, 'rally', 'row-patterns')).toEqual(['', 'W底', ''])
    expect(cells(w, 'rally', 'row-boxes')).toEqual(['1', '1', ''])
    const msft = w.get('[data-testid="rally-row"][data-symbol="MSFT"] [data-testid="row-patterns"]')
    expect(msft.find('.chip').text()).toBe('W底')
    await msft.trigger('mouseenter')
    expect(w.findAll('[data-testid="finder-sample"]').map(r => r.findAll('td').map(td => td.text())))
      .toEqual([['2023-12-01', 'neg', 'W底'], ['2024-02-20', 'pos', 'W底']])
    await msft.trigger('mouseleave')
    expect(w.find('[data-testid="finder-samples"]').exists()).toBe(false)
    // 没有样本的格子悬停不弹
    await w.get('[data-testid="rally-row"][data-symbol="AAPL"] [data-testid="row-patterns"]').trigger('mouseenter')
    expect(w.find('[data-testid="finder-samples"]').exists()).toBe(false)
  })

  it('charts:全部标过的股票一只一行,只画了框的也在;写 pattern 名、正负样本数、框数', async () => {
    const { w } = await mountFinder()
    await w.get('[data-testid="finder-tab-charts"]').trigger('click')
    expect(w.get('[data-testid="finder-page-charts"]').isVisible()).toBe(true)
    expect(rows(w, 'charts').map(r => r.attributes('data-symbol'))).toEqual(['AAPL', 'MSFT'])
    expect(cells(w, 'charts', 'row-patterns')).toEqual(['', 'W底平台'])
    expect(cells(w, 'charts', 'row-pos')).toEqual(['', '2'])
    expect(cells(w, 'charts', 'row-neg')).toEqual(['', '1'])
    expect(cells(w, 'charts', 'row-boxes')).toEqual(['1', '1'])
  })

  it('random:按抽的先后列出顶栏 random 抽过的图;刷新(新的页面状态)后为空;不写浏览器存储', async () => {
    const lsBefore = JSON.stringify(Object.entries(localStorage).sort())
    const ssBefore = JSON.stringify(Object.entries(sessionStorage).sort())
    const { w, view } = await mountFinder()
    const top = keep(mount(TopBar))
    await flushPromises()
    for (const d of DRAWS) {
      vi.mocked(api.getRandom).mockImplementationOnce(() => Promise.resolve(d))
      await top.get('[data-testid="random-button"]').trigger('click')
      await flushPromises()
    }
    expect(view.symbol).toBe('AAPL')
    await w.get('[data-testid="finder-tab-random"]').trigger('click')
    expect(rows(w, 'random').map(r => [r.attributes('data-symbol'), r.attributes('data-start')]))
      .toEqual([['TSLA', '2023-01-03'], ['AAPL', '2022-02-01']])
    expect(rows(w, 'random')[1].classes()).toContain('current')     // 刚抽的这张是当前图
    expect(JSON.stringify(Object.entries(localStorage).sort())).toBe(lsBefore)
    expect(JSON.stringify(Object.entries(sessionStorage).sort())).toBe(ssBefore)

    // 刷新:新的页面状态,random 页为空,页签回到 rally
    w.unmount(); top.unmount(); mounted.length = 0
    setActivePinia(createPinia())
    const again = await mountFinder()
    expect(again.finder.draws).toEqual([])
    expect(again.finder.tab).toBe('rally')
    await again.w.get('[data-testid="finder-tab-random"]').trigger('click')
    expect(rows(again.w, 'random')).toHaveLength(0)
    expect(again.w.get('[data-testid="random-page-status"]').text()).toBe('empty')
  })
})

describe('FinderList · 按法', () => {
  it.each<Tier>(['annotate', 'compare', 'app'])('点一行换到那张图,留在 %s', async (tier) => {
    const { w, view } = await mountFinder()
    setTier(view, tier)
    await rows(w, 'rally')[1].trigger('click')                // MSFT
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-09-12', end: '2024-04-26' })
    expect(tierOf(view)).toBe(tier)
    expect(rows(w, 'rally')[1].classes()).toContain('current')
    await w.get('[data-testid="finder-tab-charts"]').trigger('click')
    await w.get('[data-testid="charts-row"][data-symbol="AAPL"]').trigger('click')
    expect(view.symbol).toBe('AAPL')
    expect(view.viewWindow).toBeNull()
    expect(tierOf(view)).toBe(tier)
  })

  it.each<Tier>(['annotate', 'compare', 'app'])('PageUp / PageDown 在当前页签里挨个翻,留在 %s', async (tier) => {
    const { w, view } = await mountFinder()
    setTier(view, tier)
    // 当前图不在这一页:从第一行起
    expect(fireKey('PageDown').defaultPrevented).toBe(true)
    expect(view.symbol).toBe('AAPL')
    fireKey('PageDown')
    expect(view.symbol).toBe('MSFT')
    fireKey('PageDown')
    fireKey('PageDown')                                      // 到头停住
    expect(view.symbol).toBe('NVDA')
    fireKey('PageUp')
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-09-12', end: '2024-04-26' })
    expect(tierOf(view)).toBe(tier)
    // 换到 charts 页签:在 charts 的行里翻
    await w.get('[data-testid="finder-tab-charts"]').trigger('click')
    fireKey('PageUp')
    expect(view.symbol).toBe('AAPL')
    expect(tierOf(view)).toBe(tier)
  })

  it('带修饰键的 PageUp / PageDown 不接', async () => {
    const { view } = await mountFinder()
    expect(fireKey('PageDown', { shiftKey: true }).defaultPrevented).toBe(false)
    expect(fireKey('PageDown', { ctrlKey: true }).defaultPrevented).toBe(false)
    expect(view.symbol).toBeNull()
  })

  it('自绘下拉(顶栏 pattern)的菜单开着时不切;关上后照常翻', async () => {
    const { view } = await mountFinder()
    view.openFromFinder('MSFT', { start: '2023-09-12', end: '2024-04-26' })
    const menu = document.createElement('button')
    menu.setAttribute('aria-expanded', 'true')
    document.body.appendChild(menu)
    menu.focus()
    expect(fireKey('PageDown').defaultPrevented).toBe(false)
    expect(view.symbol).toBe('MSFT')
    menu.setAttribute('aria-expanded', 'false')
    fireKey('PageDown')
    expect(view.symbol).toBe('NVDA')
  })

  it.each([
    ['单行输入框', '<input type="text">'],
    ['多行输入框', '<textarea></textarea>'],
    ['下拉框', '<select><option>a</option><option>b</option></select>'],
  ])('焦点在%s里时翻页键不切', async (_name, html) => {
    const { view } = await mountFinder()
    view.openFromFinder('MSFT', { start: '2023-09-12', end: '2024-04-26' })
    const host = document.createElement('div')
    host.innerHTML = html
    document.body.appendChild(host)
    ;(host.firstElementChild as HTMLElement).focus()
    expect(fireKey('PageDown').defaultPrevented).toBe(false)
    expect(fireKey('PageUp').defaultPrevented).toBe(false)
    expect(view.symbol).toBe('MSFT')
    // 焦点离开输入框后照常翻
    ;(document.activeElement as HTMLElement).blur()
    fireKey('PageDown')
    expect(view.symbol).toBe('NVDA')
  })

  it('scan 档里不接(左栏是扫描列表)', async () => {
    const { view } = await mountFinder()
    view.loadScanFile(scanOf(['AAPL', 'MSFT']))
    expect(view.scanView).toBe(true)
    const before = view.symbol
    expect(fireKey('PageDown').defaultPrevented).toBe(false)
    expect(view.symbol).toBe(before)
    expect(view.scanView).toBe(true)
    // 从清单换图的动作在 scan 档里什么都不做
    view.openFromFinder('NVDA')
    expect(view.symbol).toBe(before)
  })
})

describe('LeftPanel · 随档换内容', () => {
  it('compare 下左栏只有找图清单,没有 app 的任何结果;scan 档是扫描列表;切回来页签还在', async () => {
    useAnnotationStore().server = readOf(STATE)
    const w = keep(mount(LeftPanel, { attachTo: document.body }))
    const view = useViewStore()
    view.loadScanFile(scanOf(['AAPL', 'MSFT']))              // 加载过扫描:落在 scan 档
    await flushPromises()
    expect(w.get('[data-testid="scan-side"]').isVisible()).toBe(true)
    expect(w.get('[data-testid="finder-list"]').isVisible()).toBe(false)

    await w.get('[data-testid="finder-tab-charts"]').trigger('click')
    view.enterLinked('compare')
    await flushPromises()
    expect(view.comparing).toBe(true)
    expect(w.get('[data-testid="finder-list"]').isVisible()).toBe(true)
    expect(w.get('[data-testid="scan-side"]').isVisible()).toBe(false)
    // 看得见的部分里没有扫描列表的命中、收益列,也没有它的行
    const shown = w.findAll('*').filter(e => e.isVisible())
    expect(shown.some(e => e.classes('has-hit') || e.classes('col-fr') || e.classes('col-num'))).toBe(false)
    expect(shown.some(e => e.element.matches('td.sym[data-symbol]'))).toBe(false)
    expect(w.get('[data-testid="finder-list"]').text()).not.toMatch(/r\d+|hit_stocks/)
    expect(w.get('[data-testid="finder-tab-charts"]').attributes('aria-selected')).toBe('true')

    view.enterScan()
    await flushPromises()
    expect(w.get('[data-testid="finder-list"]').isVisible()).toBe(false)
    view.enterAnnotate()
    await flushPromises()
    expect(w.get('[data-testid="finder-tab-charts"]').attributes('aria-selected')).toBe('true')
    expect(w.get('[data-testid="finder-page-charts"]').isVisible()).toBe(true)
  })
})
