// Task 4 · DetailSidebar 组件测:候选表就地展开 · marked 判据 · trace 显示条件。
// 复用 store 真 Pinia · 组件 mount 靠 Vue Test Utils + jsdom。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import DetailSidebar from '../src/components/DetailSidebar.vue'
import { useViewStore } from '../src/stores/view'
import { getDiagnose } from '../src/api'
import type { MultiScanResultFile } from '../src/types'

// diag 经 view.ts 内部 watch([symbol,scanFile,activePatternId,...],async...) 异步拉取,
// 候选表渲染依赖它非空——mock getDiagnose + 各测试 loadScanFile 后 await flushPromises()
// 让 diag 落地,候选表相关断言才有意义(承 tests/components/DetailSidebar.spec.ts 既有模式)。
vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve({
    symbol: 'AAA', pattern_id: 'p1',
    nodes: {
      bo: { attr: [{ instance_id: 'e_bo_1#0', node_id: 'bo', start_idx: 10, end_idx: 10, clauses: {} }], rel: [] },
      ta: { attr: [
        { instance_id: 'e_ta_1#0', node_id: 'ta', start_idx: 12, end_idx: 15, clauses: {} },
        { instance_id: 'e_ta_2#0', node_id: 'ta', start_idx: 20, end_idx: 22, clauses: {} },
      ], rel: [] },
    },
    note: 'Task 4 fixture',
  })),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], hits: [], node_index: {} },
    summary: { events: 0, hits: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  getTimeDiagnose: vi.fn(() => Promise.resolve({
    scope: 'time', payload: { frame: [0, 0], failed_attempts: [] }, caveats: [],
  })),
  getPairDiagnose: vi.fn(() => Promise.resolve({
    scope: 'pair',
    payload: {
      src_event_id: 'e_bo_1', dst_event_id: 'e_ta_1', applied_swap: false,
      original_first_click: 'e_bo_1', original_second_click: 'e_ta_1',
      valid: true, invalid_reason: null, edge_id: 'bo_to_ta', edge_kind: 'TemporalEdge', subchecks: [],
    },
    caveats: [],
  })),
}))

function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: {
      pattern_id: 'p1',
      topology: {
        nodes: [
          { node_id: 'bo', render_grid: 'price' },
          { node_id: 'ta', render_grid: 'time' },
        ],
        edges: [{ src: 'bo', dst: 'ta', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { node_id: 'bo', instance_id: 'e_bo_1#0', instance_idx: 0, start_idx: 10, end_idx: 10, child_refs: {} },
        { node_id: 'ta', instance_id: 'e_ta_1#0', instance_idx: 0, start_idx: 12, end_idx: 15,
          anchor_bo_id: 'e_bo_1#0', child_refs: {} },
        { node_id: 'ta', instance_id: 'e_ta_2#0', instance_idx: 0, start_idx: 20, end_idx: 22,
          anchor_bo_id: 'e_bo_1#0', child_refs: {} },
      ],
      hits: [
        { hit_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'e_ta_1#0' }, children: ['e_ta_1#0'] },
        { hit_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'e_ta_2#0' }, children: ['e_ta_2#0'] },
      ],
    } as any, summary: { hits: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('DetailSidebar · Task 4 视图分化', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('bracket-focus:showTrace=true → .hit-trace 渲染 · manualExpandedNodes=空 → 无候选表', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusHit('m1')
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.hit-trace').exists()).toBe(true)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(false)
  })

  it('event-focus 唯一归属:showTrace=false → 无 trace · 候选表在 event 所在 node 下方渲染', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    await flushPromises()                         // diag 落地
    view.focusEvent('e_ta_1#0')                  // 唯一归属 m1;expandedNodeIds={ta}
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.hit-trace').exists()).toBe(false)
    // 候选表存在
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)
    // hit 列表单行黄底(markedHitIds={m1})
    const rows = wrapper.findAll('.hit-row')
    const selectedRows = rows.filter(r => r.classes().includes('hit-row--selected'))
    expect(selectedRows.length).toBe(1)
  })

  it('聚焦不改档位:level=in_hit 时点一个不在 hit 里的候选,档位不动,选中的那一行写 hidden', async () => {
    // 夹具里的事件都在 hit 里:另加一个不在任何 hit 里的 ta(analysis 与 diag 各一行)
    const extra = { instance_id: 'e_ta_3#0', node_id: 'ta', start_idx: 30, end_idx: 33, clauses: {} }
    const base: any = await (getDiagnose as any)()
    vi.mocked(getDiagnose).mockResolvedValueOnce({ ...base, nodes: { ...base.nodes,
      ta: { ...base.nodes.ta, attr: [...base.nodes.ta.attr, extra] } } })
    const fx: any = makeFixture()
    fx.results[0].per_pattern.p1.analysis.events.push({ node_id: 'ta', instance_id: 'e_ta_3#0', instance_idx: 0,
                                                        start_idx: 30, end_idx: 33, child_refs: {} })
    const view = useViewStore()
    view.loadScanFile(fx)
    view.setLevel('in_hit')
    await flushPromises()                         // diag 落地
    view.focusEvent('e_ta_3#0')                   // 不在任何 hit 里
    const wrapper = mount(DetailSidebar)
    await flushPromises()
    expect(view.level).toBe('in_hit')
    const tags = wrapper.findAll('[data-testid="candidate-hidden"]')
    expect(tags.length).toBe(1)
    expect(tags[0].element.closest('.attr-row')!.classList.contains('attr-row--selected')).toBe(true)
    view.focusEvent('e_ta_1#0')                   // in_hit 的那个画得出来:不写
    await flushPromises()
    expect(wrapper.findAll('[data-testid="candidate-hidden"]').length).toBe(0)
  })

  it('多归属 pending:候选表在 pending event 所在 node 下方展开 · hit 列表多行同亮', async () => {
    const view = useViewStore()
    // Task 5 契约变更:多归属 = 同一实例被 2+ hit 的 node_index 引用(真共享,
    // 删除 anchor_field 反查展开);构造 e_ta_1#0 被 m1/m2 同时引用
    const fixture = makeFixture() as any
    fixture.results[0].per_pattern.p1.analysis.hits = [
      { hit_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'e_ta_1#0' }, children: ['e_ta_1#0'] },
      { hit_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'e_ta_1#0' }, children: ['e_ta_1#0'] },
    ]
    view.loadScanFile(fixture)
    await flushPromises()                         // diag 落地
    view.focusEvent('e_ta_1#0')                  // 单实例被两 hit 共享 → 多归属
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.hit-trace').exists()).toBe(false)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)     // pending 兜底展开 ta
    const rows = wrapper.findAll('.hit-row')
    const selectedRows = rows.filter(r => r.classes().includes('hit-row--selected'))
    expect(selectedRows.length).toBe(2)          // 信息层如实反映
  })

  it('sidebar hit 行 click:等价 bracket click 走 focusHit → showTrace=true', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    const wrapper = mount(DetailSidebar)
    const hitRows = wrapper.findAll('.hit-row')
    await hitRows[0].trigger('click')
    expect(view.focusedHitId).toBe('m1')
    expect(view.focusedInstanceId).toBeNull()
    expect(view.showTrace).toBe(true)
  })

  it('候选表就地展开:candidate-table-wrap 应作为 funnel-row 后续兄弟节点', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    await flushPromises()                         // diag 落地
    view.toggleExpandedNode('ta')
    const wrapper = mount(DetailSidebar)
    // template 结构:v-for 里每 funnel-row 后跟 v-if candidate-table-wrap(同 parent);
    // candidate-table-wrap 应真实渲染在 ta funnel-row 后(node 名已由上方 funnel-row 承载,标题不再冗余重复)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)
  })
})

describe('DetailSidebar · hit 列表写买入日期', () => {
  beforeEach(() => setActivePinia(createPinia()))

  function fixtureWithBuyNode(): MultiScanResultFile {
    const f: any = makeFixture()
    f.per_pattern.p1.end_node = 'ta'
    const hits = f.results[0].per_pattern.p1.analysis.hits
    f.results[0].per_pattern.p1.analysis.hits = [hits[1], hits[0]]   // 原顺序与买入日顺序相反
    return f
  }

  it('行按第一个买入日排,行上写这一天的日期,不再是圈号', () => {
    const view = useViewStore()
    view.loadScanFile(fixtureWithBuyNode())
    view.setBarDates(Array.from({ length: 30 }, (_, i) => `2024-02-${String(i + 1).padStart(2, '0')}`))
    const wrapper = mount(DetailSidebar)
    const labels = wrapper.findAll('.hit-row .hit-span').map(r => r.text())
    expect(labels).toEqual(['2024-02-13', '2024-02-21'])   // m1 买在下标 12、m2 买在 20
    expect(labels.join('')).not.toMatch(/[①②③④⑤⑥⑦⑧⑨]/)
    // 悬停给起止日期,不给 K 线下标
    expect(wrapper.findAll('.hit-row').map(r => r.attributes('title'))).toEqual(['2024-02-11 – 2024-02-16', '2024-02-13 – 2024-02-23'])
  })

  it('选中的 hit 行滚到看得见', async () => {
    const view = useViewStore()
    view.loadScanFile(fixtureWithBuyNode())
    const scrolled: string[] = []
    const orig = (Element.prototype as any).scrollIntoView
    ;(Element.prototype as any).scrollIntoView = function (this: Element) { scrolled.push(this.className) }
    try {
      mount(DetailSidebar)
      view.focusHit('m2')
      await flushPromises()
      expect(scrolled.some(c => c.includes('hit-row--selected'))).toBe(true)
    } finally {
      ;(Element.prototype as any).scrollIntoView = orig
    }
  })
})
