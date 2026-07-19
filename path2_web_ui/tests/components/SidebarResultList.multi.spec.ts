import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SidebarResultList from '../../src/components/SidebarResultList.vue'
import { useViewStore, SYMBOL_SORT_KEY } from '../../src/stores/view'

const emptyAnalysis = { events: [], matches: [] }
const file = {
  pattern_ids: ['bo_only', 'bbb'],
  per_pattern: {
    bo_only: { pattern_spec: { pattern_id: 'bo_only', topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'bo' },
    bbb:     { pattern_spec: { pattern_id: 'bbb',     topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'tb' },
  },
  scan: { scan_ts: '20260627T120000', start_date: '2024-01-01', end_date: '2024-06-30',
          workers: 1, scanned: 2, hits: 2, errors: 0, dataset_dir: '/d', params: 'd',
          win_start: '2023-09-01', win_end: '2024-07-15', label_horizon: 20 },
  results: [
    { symbol: 'AAA', per_pattern: {
      bo_only: { summary: { matches: 2 }, analysis: emptyAnalysis, max_forward_return: 0.34 },
      bbb:     { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.10 },
    }},
    { symbol: 'BBB', per_pattern: {
      bo_only: { summary: { matches: 1 }, analysis: emptyAnalysis, max_forward_return: 0.50 },
      bbb:     { summary: { matches: 0 }, analysis: emptyAnalysis, max_forward_return: null },
    }},
  ],
}

describe('SidebarResultList — pattern × field columns', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('renders 2 columns per pattern (num + fr) with data-col-* attrs', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const ths = w.findAll('th[data-col-pid]')
    const keys = ths.map(th => `${th.attributes('data-col-pid')}_${th.attributes('data-col-field')}`)
    expect(keys).toEqual(['bo_only_num', 'bo_only_fr', 'bbb_num', 'bbb_fr'])
  })

  it('cell num 显 0 when matches=0; cell fr 显 — when null', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const bbbNum = w.find('td[data-cell-pid="bbb"][data-cell-field="num"][data-symbol="BBB"]')
    expect(bbbNum.text()).toBe('0')
    const bbbFr = w.find('td[data-cell-pid="bbb"][data-cell-field="fr"][data-symbol="BBB"]')
    expect(bbbFr.text()).toBe('—')
  })

  it('cell fr 格式化为 +5.2% / −1.3%', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const aaaFr = w.find('td[data-cell-pid="bo_only"][data-cell-field="fr"][data-symbol="AAA"]')
    expect(aaaFr.text()).toBe('+34.0%')
  })

  it('matched 类只在 num > 0 时加(num=0 无 matched;num>0 时 num 与 fr 双染)', () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const bbbNumBBB = w.find('td[data-cell-pid="bbb"][data-cell-field="num"][data-symbol="BBB"]')
    const bbbFrBBB  = w.find('td[data-cell-pid="bbb"][data-cell-field="fr"][data-symbol="BBB"]')
    expect(bbbNumBBB.classes()).not.toContain('matched')
    expect(bbbFrBBB.classes()).not.toContain('matched')
    const aaaBoNum = w.find('td[data-cell-pid="bo_only"][data-cell-field="num"][data-symbol="AAA"]')
    const aaaBoFr  = w.find('td[data-cell-pid="bo_only"][data-cell-field="fr"][data-symbol="AAA"]')
    expect(aaaBoNum.classes()).toContain('matched')
    expect(aaaBoFr.classes()).toContain('matched')
  })

  it('togglePattern hides both num and fr columns of that pid', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.togglePattern('bbb')
    const w = mount(SidebarResultList)
    const ths = w.findAll('th[data-col-pid]')
    const pids = new Set(ths.map(th => th.attributes('data-col-pid')))
    expect(pids.has('bbb')).toBe(false)
    expect(pids.has('bo_only')).toBe(true)
  })

  it('toggleField hides all _num columns globally', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.toggleField('num')                  // 现只剩 fr
    const w = mount(SidebarResultList)
    const ths = w.findAll('th[data-col-pid]')
    for (const th of ths) {
      expect(th.attributes('data-col-field')).toBe('fr')
    }
  })

  it('right-click on header dispatches @contextmenu.prevent and opens fields menu', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    // symbol header 也可触发
    const symTh = w.find('th.sym')
    await symTh.trigger('contextmenu')
    expect(w.find('.field-menu').exists()).toBe(true)
    // 菜单里两 checkbox
    const checks = w.findAll('.field-menu input[type="checkbox"]')
    expect(checks.length).toBe(2)
  })

  it('click checkbox in fields menu invokes toggleField', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.find('th.sym').trigger('contextmenu')
    const numCheck = w.find('.field-menu input[data-field="num"]')
    await numCheck.setValue(false)
    expect(v.visibleFields.has('num')).toBe(false)
  })

  it('click sort on _num header sets sortByPid = ${pid}_num', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    const boNumTh = w.find('th[data-col-pid="bo_only"][data-col-field="num"]')
    await boNumTh.trigger('click')
    expect(v.sortByPid).toBe('bo_only_num')
  })
})

describe('SidebarResultList — filter全 0 行 + active row', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('renders only rows with at least one matched visible pattern', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)                   // file has AAA/BBB(bbb 全 0)from top-of-file fixture
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    // AAA: bo_only + bbb matched → keep. BBB: bo_only matched, bbb 0 → keep (matched via bo_only).
    expect(w.findAll('td.sym').map(td => td.text())).toEqual(['AAA', 'BBB'])
    // Now hide bo_only → only bbb visible;BBB.bbb matches=0 → BBB drop, AAA (bbb matches=1) keeps.
    v.togglePattern('bo_only')
    await w.vm.$nextTick()
    const symsAfter = w.findAll('td.sym').map(td => td.text())
    expect(symsAfter).toEqual(['AAA'])
  })

  it('renders zero rows when all patterns are hidden', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.setPatternsAllOff()
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const syms = w.findAll('td.sym').map(td => td.text())
    expect(syms).toEqual([])
  })

  it('applies .active class to selected row (视觉 bg 通过 CSS 覆盖,不测色值)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    v.selectSymbol('AAA')
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const activeRow = w.find('tr.active')
    expect(activeRow.exists()).toBe(true)
    expect(activeRow.find('td.sym').text()).toBe('AAA')
  })
})

describe('SidebarResultList — grouped header 两级结构', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('renders 2 header rows (pattern name row + field row)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const rows = w.findAll('thead tr')
    expect(rows.length).toBe(2)
    expect(rows[0].classes()).toContain('hdr-pattern')
    expect(rows[1].classes()).toContain('hdr-field')
  })

  it('renders one col-pattern th per visible pattern with correct colspan and data-pattern-pid', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const patternTh = w.findAll('thead tr.hdr-pattern th.col-pattern')
    expect(patternTh.length).toBe(v.visiblePatterns.size)
    patternTh.forEach(th => {
      expect(th.attributes('colspan')).toBe(String(v.visibleFields.size))
      const pid = th.attributes('data-pattern-pid')
      expect(pid).toBeTruthy()
      expect(v.visiblePatterns.has(pid!)).toBe(true)
    })
  })

  it('renders 2 sub-cell th (num+r{N}) per visible pattern with text "num" / "r<label_horizon>"', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const fieldTh = w.findAll('thead tr.hdr-field th.col')
    expect(fieldTh.length).toBe(2 * v.visiblePatterns.size)
    w.findAll('thead tr.hdr-field th.col-num').forEach(th => {
      expect(th.text()).toBe('num')
    })
    const expectedFrText = `r${file.scan.label_horizon}`
    w.findAll('thead tr.hdr-field th.col-fr').forEach(th => {
      expect(th.text()).toBe(expectedFrText)
    })
  })

  it('symbol th has rowspan=2 (corner cell)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const symTh = w.find('thead th.sym')
    expect(symTh.attributes('rowspan')).toBe('2')
  })

  it('col-pattern has no data-col-pid / data-col-field attrs (structural proof of 纯装饰)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const patternTh = w.find('thead tr.hdr-pattern th.col-pattern')
    expect(patternTh.attributes('data-col-pid')).toBeUndefined()
    expect(patternTh.attributes('data-col-field')).toBeUndefined()
    expect(patternTh.classes()).not.toContain('col')
  })

  it('col-pattern click does not mutate sortByPid (无 @click handler)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const before = v.sortByPid
    await w.find('thead tr.hdr-pattern th.col-pattern').trigger('click')
    expect(v.sortByPid).toBe(before)
  })

  it('sub-cell click still sorts (回归保护)', async () => {
    const v = useViewStore()
    v.loadScanFile(file as any)
    const w = mount(SidebarResultList)
    await w.vm.$nextTick()
    const numTh = w.find('thead tr.hdr-field th.col-num')
    const pid = numTh.attributes('data-col-pid')!
    await numTh.trigger('click')
    expect(v.sortByPid).toBe(`${pid}_num`)
  })

  // 两级 sticky 表头依赖 --hdr-row-h 精准等于第一行行高。硬编码 24px 与真实行高不符 →
  // 第二级 sticky 停在 24px、第一行还在延伸,露出缝(数据行透过)。动态测量修此契约。
  it('mount 后 --hdr-row-h 被写为实测 hdr-pattern 行高(动态测量,防两级 sticky 缝)', async () => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    const origBCR = HTMLElement.prototype.getBoundingClientRect
    HTMLElement.prototype.getBoundingClientRect = function () {
      if (this instanceof HTMLTableRowElement && this.classList.contains('hdr-pattern')) {
        return { height: 29, width: 100, top: 0, left: 0, bottom: 29, right: 100, x: 0, y: 0,
                 toJSON: () => ({}) } as DOMRect
      }
      return origBCR.call(this)
    }
    try {
      const v = useViewStore()
      v.loadScanFile(file as any)
      const w = mount(SidebarResultList)
      await w.vm.$nextTick()
      await w.vm.$nextTick()   // syncHdrRowH 在 onMounted 里用 nextTick 排队,拆两次跨帧
      const list = w.find('.list').element as HTMLElement
      expect(list.style.getPropertyValue('--hdr-row-h')).toBe('29px')
    } finally {
      HTMLElement.prototype.getBoundingClientRect = origBCR
      vi.unstubAllGlobals()
    }
  })
})
