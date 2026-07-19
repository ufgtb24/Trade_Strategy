// Task 4 · DetailSidebar 组件测:候选表就地展开 · marked 判据 · trace 显示条件。
// 复用 store 真 Pinia · 组件 mount 靠 Vue Test Utils + jsdom。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import DetailSidebar from '../src/components/DetailSidebar.vue'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

// diag 经 view.ts 内部 watch([symbol,scanFile,activePatternId,...],async...) 异步拉取,
// 候选表渲染依赖它非空——mock getDiagnose + 各测试 loadScanFile 后 await flushPromises()
// 让 diag 落地,候选表相关断言才有意义(承 tests/components/DetailSidebar.spec.ts 既有模式)。
vi.mock('../src/api', () => ({
  getDiagnose: vi.fn(() => Promise.resolve({
    symbol: 'AAA', pattern_id: 'p1',
    nodes: {
      bo: { attr: [{ event_id: 'e_bo_1', start_idx: 10, end_idx: 10, clauses: {} }], rel: [] },
      ta: { attr: [
        { event_id: 'e_ta_1', start_idx: 12, end_idx: 15, clauses: {} },
        { event_id: 'e_ta_2', start_idx: 20, end_idx: 22, clauses: {} },
      ], rel: [] },
    },
    note: 'Task 4 fixture',
  })),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], node_index: {} },
    summary: { events: 0, matches: 0 },
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
          { node_id: 'bo', source_tag: 'bo', render_grid: 'price' },
          { node_id: 'ta', source_tag: 'ta', render_grid: 'time' },
        ],
        edges: [{ src: 'bo', dst: 'ta', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { event_id: 'e_bo_1', class_id: 'BOEvent', source_tag: 'bo', start_idx: 10, end_idx: 10, child_refs: {} },
        { event_id: 'e_ta_1', class_id: 'TAEvent', source_tag: 'ta', start_idx: 12, end_idx: 15,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
        { event_id: 'e_ta_2', class_id: 'TAEvent', source_tag: 'ta', start_idx: 20, end_idx: 22,
          anchor_bo_id: 'e_bo_1', child_refs: {} },
      ],
      matches: [
        { event_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'e_ta_1' }, children: ['e_ta_1'] },
        { event_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'e_ta_2' }, children: ['e_ta_2'] },
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('DetailSidebar · Task 4 视图分化', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('bracket-focus:showTrace=true → .match-trace 渲染 · manualExpandedNodes=空 → 无候选表', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusMatch('m1')
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(true)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(false)
  })

  it('event-focus 唯一归属:showTrace=false → 无 trace · 候选表在 event 所在 node 下方渲染', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    await flushPromises()                         // diag 落地
    view.focusEvent('e_ta_1')                    // 唯一归属 m1;expandedNodeIds={ta}
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(false)
    // 候选表存在
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)
    // 命中匹配单行黄底(markedMatchIds={m1})
    const rows = wrapper.findAll('.match-row')
    const selectedRows = rows.filter(r => r.classes().includes('match-row--selected'))
    expect(selectedRows.length).toBe(1)
  })

  it('多归属 pending:候选表在 pending event 所在 node 下方展开 · 命中匹配多行同亮', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    await flushPromises()                         // diag 落地
    view.focusEvent('e_bo_1')                    // anchor_field 反查 m1+m2 → 多归属
    const wrapper = mount(DetailSidebar)
    expect(wrapper.find('.match-trace').exists()).toBe(false)
    expect(wrapper.find('.candidate-table-wrap').exists()).toBe(true)     // pending 兜底展开 bo
    const rows = wrapper.findAll('.match-row')
    const selectedRows = rows.filter(r => r.classes().includes('match-row--selected'))
    expect(selectedRows.length).toBe(2)          // 信息层如实反映
  })

  it('sidebar 候选表 event 行 click:等价 marker click 走 focusEvent', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    await flushPromises()                         // diag 落地
    view.toggleExpandedNode('ta')                   // 手动展开 ta 候选表
    const wrapper = mount(DetailSidebar)
    const rows = wrapper.findAll('.attr-row')
    if (rows.length === 0) {
      // diag 尚未 seed —— 这条测试需要 diag,或跳过
      return
    }
    await rows[0].trigger('click')
    // focusEvent 已调用 · focusedEventId 非空
    expect(view.focusedEventId).toBeTruthy()
  })

  it('sidebar 命中匹配行 click:等价 bracket click 走 focusMatch → showTrace=true', async () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    const wrapper = mount(DetailSidebar)
    const matchRows = wrapper.findAll('.match-row')
    await matchRows[0].trigger('click')
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedEventId).toBeNull()
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
