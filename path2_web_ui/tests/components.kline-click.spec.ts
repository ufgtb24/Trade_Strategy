import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { SCAN_FILE } from './fixtures'
import type { EventDict, MatchDict, MultiScanResultFile, SerializedPattern } from '../src/types'

vi.mock('../src/api', () => ({ saveWcMirror: async () => ({ ok: true } as any), clearWcMirror: async () => ({ ok: true } as any),
  getDiagnose: vi.fn(() => Promise.resolve(null)),
  getPreview: vi.fn(() => Promise.resolve({
    analysis: { events: [], matches: [], node_index: {} },
    summary: { events: 0, matches: 0 },
    pattern_spec: {} as any, scan: {} as any,
  })),
  listScans: vi.fn(() => Promise.resolve([])),
  loadScan: vi.fn(() => Promise.resolve({} as any)),
  deleteScan: vi.fn(() => Promise.resolve({ ok: true })),
  cancelScan: vi.fn(() => Promise.resolve({ ok: true })),
  // Task 18 · 入口 D:handleShiftClick 第 2 击经 view.triggerPairQuery 调此 fetch helper
  getTimeDiagnose: vi.fn(() => Promise.resolve({
    scope: 'time', payload: { frame: [0, 0], failed_attempts: [] }, caveats: [],
  })),
  getPairDiagnose: vi.fn(() => Promise.resolve({
    scope: 'pair',
    payload: {
      src_event_id: 'bo_1', dst_event_id: 'tb_1', applied_swap: false,
      original_first_click: 'bo_1', original_second_click: 'tb_1',
      valid: true, invalid_reason: null, edge_id: 'bo_to_tb', edge_kind: 'TemporalEdge', subchecks: [],
    },
    caveats: [],
  })),
}))

vi.mock('../src/stores/config', () => ({
  useConfigStore: vi.fn(() => ({ config: null })),
}))

/** Task 3(highlightedEventIds 协议化)辅助:highlightedEventIds 现在是依赖
 * selectedMatch(→ effectiveAnalysis.matches)的 computed,不再能靠 setHighlightedEvents
 * 直接注入。这里把 handleChartClick 用到的 ad-hoc matches 数组塞进 store(loadScanFile),
 * 让 selectedMatch 能在 effectiveAnalysis.matches 里查到同一个 match_id。edges 留空:
 * 这里只验证「flat children 直接进 matchedIds 初始并集」,不涉及 child_refs/anchor_field
 * 展开(那部分由文件末尾的 Task 3 协议派生专项测试覆盖)。
 * 【实例化】events 从 matches.children 动态生成:children 引用的事件必须在事件全集里
 * (children 已是 instance_id 列表),matchedIds 的实例集才有实例可落。 */
function seedMatches(view: ReturnType<typeof useViewStore>, matches: any[]): void {
  const instanceIds = [...new Set(matches.flatMap((m: any) => m.children))]
  const events = instanceIds.map(id => ({ node_id: 'x', instance_id: id,
                                          start_idx: 0, end_idx: 1, child_refs: {} }))
  view.loadScanFile({
    pattern_ids: ['p'],
    per_pattern: { p: { pattern_spec: { pattern_id: 'p', topology: { nodes: [], edges: [] }, event_styles: {} }, end_node: 'x' } },
    scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
            scanned: 1, hits: 1, errors: 0, dataset_dir: '', params: '',
            win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
    results: [{ symbol: 'S', per_pattern: { p: { summary: { matches: matches.length }, analysis: { events, matches }, max_forward_return: null } } }],
  } as any)
  view.symbol = 'S'
  view.activePatternId = 'p'
}

/** Task 6 实例绑定 fixture:APCX 形态双入口同款(与 stores.focus-actions.spec.ts::makeDualEntryFixture
 * 逐字同构,独立复制避免跨文件耦合)——两 match 的 node_index 分别引用 tb_v1_293 #0/#1。 */
function makeDualEntryFixture(events: EventDict[], matches: MatchDict[]): MultiScanResultFile {
  const pattern: SerializedPattern = {
    pattern_id: 'p1',
    topology: {
      nodes: [
        { node_id: 'burst', render_grid: 'time' },
        { node_id: 'tb', render_grid: 'time' },
      ],
      edges: [],
    },
    event_styles: {},
  } as any
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: pattern } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events, matches,
    } as any, summary: { matches: matches.length } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('KlineChart click handler (Task 9 实例化)', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('marker 点击按 instance_id 直选(无解析)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    // APCX 形态(Task 5 同款):两 match 的 node_index 分别引用 tb_v1_293 #0/#1(各属一个 match)。
    // marker data 恒带 instance_id(含 #idx),点击直接 focusEvent(instance_id) 精确直选。
    const m0 = { match_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#0', tb: 'tb_v1_293#0' },
                 children: ['burst_0_2#0', 'tb_v1_293#0'], predicate_trace: null } as MatchDict
    const m1 = { match_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293b', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#1', tb: 'tb_v1_293#1' },
                 children: ['burst_0_2#1', 'tb_v1_293#1'], predicate_trace: null } as MatchDict
    const events: EventDict[] = [
      { instance_id: 'tb_v1_293#0', node_id: 'tb', instance_idx: 0, start_idx: 12, end_idx: 15, child_refs: {} },
      { instance_id: 'tb_v1_293#1', node_id: 'tb', instance_idx: 1, start_idx: 20, end_idx: 22, child_refs: {} },
      { instance_id: 'burst_0_2#0', node_id: 'burst', instance_idx: 0, start_idx: 8, end_idx: 8, child_refs: {} },
      { instance_id: 'burst_0_2#1', node_id: 'burst', instance_idx: 1, start_idx: 8, end_idx: 8, child_refs: {} },
    ]
    view.loadScanFile(makeDualEntryFixture(events, [m0, m1]))
    // marker data 带 instance_id('tb_v1_293#0'):点 #0 实例
    handleChartClick(
      { seriesName: 'points', data: { instance_id: 'tb_v1_293#0' } },
      [], view,
    )
    expect(view.focusedMatchId).toBe(m0.match_id)   // 直选引用 #0 的 match
    expect(view.focusedInstanceId).toBe('tb_v1_293#0')
    expect(view.pendingDisambigInstanceId).toBeNull()  // 不再弹待选择
    // 点 #1 实例 → 直选引用 #1 的 match(验证 instance_id 不是写死 0)
    handleChartClick(
      { seriesName: 'points', data: { instance_id: 'tb_v1_293#1' } },
      [], view,
    )
    expect(view.focusedMatchId).toBe(m1.match_id)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('marker click with ms.length === 0 → 只聚焦实例(selectedInstanceId)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [{ match_id: 'm1', children: ['e_other#0'], start_idx: 0, end_idx: 1, node_index: {}, predicate_trace: null }]
    handleChartClick({ seriesName: 'points', data: { instance_id: 'e_solo#0' } }, matches, view)
    expect(view.selectedInstanceId).toBe('e_solo#0')
    expect(view.focusedInstanceRef).toBe('e_solo#0')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  // unmatched marker(qualified/detected)与已选中 group 互斥:
  // 三条 marker 归属分支(===0 / ===1 / >1)都必须先清旧 group 再按新归属重设——
  // 此前 ms.length===0 漏清,导致点灰色 marker 后旧 group 高亮残留、与新 focus 共存。
  it('marker click with ms.length === 0 顺手清旧 group(与已选 group 互斥)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [{ match_id: 'm1', children: ['eA#0', 'eB#0'], start_idx: 0, end_idx: 1,
      // 实例流契约(Task 4):matchedIds 初始集来自 node_index 精确实例引用(非 children 身份展开)
      node_index: { n0: 'eA#0', n1: 'eB#0' }, predicate_trace: null }]
    seedMatches(view, matches)   // 落地真实 match 数据,让 focusMatch 真正派生非空 highlightedEventIds(而非 tautological 0)
    view.focusMatch('m1')
    view.focusEvent('eA#0')
    expect(view.highlightedEventIds.size).toBeGreaterThan(0)   // arrange 阶段显式确认"旧 group"确实非空
    handleChartClick({ seriesName: 'points', data: { instance_id: 'e_orphan#0' } }, matches, view)
    expect(view.focusedInstanceRef).toBe('e_orphan#0')
    expect(view.selectedMatchId).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click with ms.length === 1 → 直选 match + 精确聚焦实例', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [{ match_id: 'm1', children: ['eA#0', 'eB#0', 'eC#0'], start_idx: 0, end_idx: 1,
      node_index: { n0: 'eA#0', n1: 'eB#0', n2: 'eC#0' }, predicate_trace: null }]
    seedMatches(view, matches)
    handleChartClick({ seriesName: 'intervals', data: { instance_id: 'eA#0' } }, matches, view)
    expect(view.selectedMatchId).toBe('m1')
    expect(view.highlightedEventIds.size).toBe(3)
    expect(view.focusedInstanceId).toBe('eA#0')
    expect(view.focusedInstanceRef).toBe('eA#0')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click with ms.length > 1 → candidate + pendingDisambigInstanceId (no selected)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { match_id: 'm1', children: ['eShared#0', 'eA#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eShared#0', n1: 'eA#0' }, predicate_trace: null },
      { match_id: 'm3', children: ['eShared#0', 'eB#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eShared#0', n1: 'eB#0' }, predicate_trace: null },
      { match_id: 'm5', children: ['eShared#0', 'eC#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eShared#0', n1: 'eC#0' }, predicate_trace: null },
    ]
    seedMatches(view, matches)   // focusEvent 内部改读 view.effectiveAnalysis(Task 3),不再直读传入的 matches 参数
    handleChartClick({ seriesName: 'points', data: { instance_id: 'eShared#0' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(3)
    expect(view.candidateMatchIds.has('m1')).toBe(true)
    expect(view.candidateMatchIds.has('m3')).toBe(true)
    expect(view.candidateMatchIds.has('m5')).toBe(true)
    expect(view.pendingDisambigInstanceId).toBe('eShared#0')
    expect(view.selectedMatchId).toBeNull()
    expect(view.focusedInstanceRef).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  it('idempotent: click same multi-match event twice keeps candidate', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { match_id: 'm1', children: ['eShared#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eShared#0' }, predicate_trace: null },
      { match_id: 'm2', children: ['eShared#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eShared#0' }, predicate_trace: null },
    ]
    seedMatches(view, matches)   // focusEvent 内部改读 view.effectiveAnalysis(Task 3),不再直读传入的 matches 参数
    handleChartClick({ seriesName: 'points', data: { instance_id: 'eShared#0' } }, matches, view)
    const sizeBefore = view.candidateMatchIds.size
    handleChartClick({ seriesName: 'points', data: { instance_id: 'eShared#0' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(sizeBefore)
    expect(view.pendingDisambigInstanceId).toBe('eShared#0')
  })

  it('bracket click on candidate match → finalize: setHighlighted + selectMatch + clearCandidates', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { match_id: 'm1', children: ['eA#0', 'eB#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eA#0', n1: 'eB#0' }, predicate_trace: null },
      { match_id: 'm3', children: ['eA#0', 'eC#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eA#0', n1: 'eC#0' }, predicate_trace: null },
    ]
    seedMatches(view, matches)
    // 先进 candidate
    handleChartClick({ seriesName: 'points', data: { instance_id: 'eA#0' } }, matches, view)
    expect(view.candidateMatchIds.size).toBe(2)
    // 再 click 候选中的 bracket m3
    handleChartClick({ seriesName: 'brackets', data: { match_id: 'm3' } }, matches, view)
    expect(view.selectedMatchId).toBe('m3')
    expect(view.highlightedEventIds.size).toBe(2)
    expect(view.highlightedEventIds.has('eA#0')).toBe(true)
    expect(view.highlightedEventIds.has('eC#0')).toBe(true)
    expect(view.candidateMatchIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  // 同一时刻只允许一个 marker 处于「当前被选中」:bracket 琥珀填充 与 event 琥珀边缘 不共存。
  // 场景:先点单归属 event marker(ms.length===1 分支 focusedInstanceId='eA#0') → 再点另一 bracket m2 →
  // 期望实例焦点被清,否则原 marker 的 focus 琥珀边留守,与新 bracket 的琥珀填充并存。
  it('bracket click 清实例焦点(防前次 marker focus 琥珀边遗留)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const matches = [
      { match_id: 'm1', children: ['eA#0', 'eB#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eA#0', n1: 'eB#0' }, predicate_trace: null },
      { match_id: 'm2', children: ['eC#0', 'eD#0'], start_idx: 0, end_idx: 1,
        node_index: { n0: 'eC#0', n1: 'eD#0' }, predicate_trace: null },
    ]
    seedMatches(view, matches)   // focusEvent 内部改读 view.effectiveAnalysis(Task 3),不再直读传入的 matches 参数
    // 步骤 1:点 eA(单归属 m1),此时 focusedInstanceRef='eA#0' + selectedMatchId='m1'
    handleChartClick({ seriesName: 'points', data: { instance_id: 'eA#0' } }, matches, view)
    expect(view.focusedInstanceRef).toBe('eA#0')
    expect(view.selectedMatchId).toBe('m1')
    // 步骤 2:切换点 bracket m2,期望焦点整体切换 —— selectedMatchId → 'm2' 且实例焦点 → null
    handleChartClick({ seriesName: 'brackets', data: { match_id: 'm2' } }, matches, view)
    expect(view.selectedMatchId).toBe('m2')
    expect(view.focusedInstanceRef).toBeNull()
  })

  it('handleChartClick 空白 click(seriesName 缺失)→ 清 shiftSelectedEvents', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    view.setShiftSelectedEvents([{ instance_id: 'e1#0', node_id: 'BO', source: 'main' }])
    expect(view.shiftSelectedEvents.length).toBe(1)
    handleChartClick(null, [], view)
    expect(view.shiftSelectedEvents.length).toBe(0)
  })

  it('handleChartClick MARKER_SERIES click → 不清 shiftSelectedEvents(走 focusEvent, 保留 pair 累积器)', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    view.setShiftSelectedEvents([{ instance_id: 'shift_e1#0', node_id: 'BO', source: 'main' }])
    // 触发 focusEvent 分支,instance_id 不必存在真 events
    handleChartClick(
      { seriesName: 'points', data: { instance_id: 'other_ev#0' } },
      [],
      view
    )
    // MARKER 分支 focusEvent 不清 shift(shift 累积器是独立通道)
    expect(view.shiftSelectedEvents.length).toBe(1)
  })
})

// ─── Task 18 · 入口 D:shift+click 跨图累积(KlineChart.ts::handleShiftClick) ───────
// 纯函数 + 真 Pinia store,不 mount .vue/echarts(shift+click 经 native MouseEvent.shiftKey
// 判定的部分留在 KlineChart.vue,难 mock;这里只测已提炼出的累积器逻辑本身)。
describe('KlineChart shift+click accumulator (Task 18)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()   // getPairDiagnose 调用计数逐 test 独立(本 describe 内多测断言 toHaveBeenCalled*)
  })

  function setupStoreWithScan() {
    const view = useViewStore()
    view.loadScanFile(SCAN_FILE)
    view.selectSymbol('AAPL')
    return view
  }

  it('第 1 击选中 src · 第 2 击触发 pair-query · 第 3 击清空重来(保留新 src)', async () => {
    const view = setupStoreWithScan()
    const { handleShiftClick } = await import('../src/components/KlineChart')
    const api = await import('../src/api')

    handleShiftClick('bo9#0', 'bo', 'main', view)
    expect(view.shiftSelectedEvents).toHaveLength(1)
    expect(view.shiftSelectedEvents[0]).toEqual({ instance_id: 'bo9#0', node_id: 'bo', source: 'main' })

    handleShiftClick('tb16#0', 'tb', 'sub', view)
    expect(view.shiftSelectedEvents).toHaveLength(2)
    // Task 9:getPairDiagnose 尾参新增 paramsOverride;SCAN_FILE 无 params_snapshot(legacy)→
    // effectiveParamsOverride=null → ?? undefined → 显式 undefined 补位(exact-args 断言需要)
    expect(api.getPairDiagnose).toHaveBeenCalledWith(
      'bottom_burst', 'AAPL', '2025-01-01', '2025-12-31', 'bo9#0', 'tb16#0', undefined)

    handleShiftClick('burst_1#0', 'burst', 'sub', view)
    expect(view.shiftSelectedEvents).toHaveLength(1)
    expect(view.shiftSelectedEvents[0].instance_id).toBe('burst_1#0')
  })

  it('第 2 击落地后 activeDetailCard 切 pair · pairScopeResponse 落地', async () => {
    const view = setupStoreWithScan()
    const { handleShiftClick } = await import('../src/components/KlineChart')

    handleShiftClick('bo9#0', 'bo', 'main', view)
    handleShiftClick('tb16#0', 'tb', 'sub', view)
    await flushPromises()

    expect(view.activeDetailCard).toBe('pair')
    expect(view.pairScopeResponse).not.toBeNull()
  })

  it('缺 scanFile/symbol 时第 2 击不发请求(triggerPairQuery 早退防御)', async () => {
    const view = useViewStore()   // 未 loadScanFile
    const { handleShiftClick } = await import('../src/components/KlineChart')
    const api = await import('../src/api')

    handleShiftClick('a#0', 'bo', 'main', view)
    handleShiftClick('b#0', 'tb', 'sub', view)
    await flushPromises()

    expect(view.shiftSelectedEvents).toHaveLength(2)
    expect(api.getPairDiagnose).not.toHaveBeenCalled()
  })
})

// ─── Task 3 · highlightedEventIds 协议派生(修复"选中 match 后主图 BO 方框无 in-group 深边") ───
describe('handleChartClick × highlightedEventIds 协议派生', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('选中一条 match(marker 单归属分支)后 highlightedEventIds 沿 child_refs 展开、含 BO id', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    // 造最小 scanFile:一个 burst-tb match,burst.child_refs.members=[bo_5]
    const events = [
      { instance_id: 'burst_1#0', node_id: 'burst', start_idx: 5, end_idx: 6,
        child_refs: { members: ['bo_5#0'] } },
      { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 8, end_idx: 8,
        child_refs: {}, anchor_bo_id: 'bo_5#0' },
      { instance_id: 'bo_5#0', node_id: 'bo', start_idx: 5, end_idx: 5, child_refs: {} },
    ]
    const matches = [{ match_id: 'match_1', start_idx: 5, end_idx: 8,
      node_index: { burst: 'burst_1#0', tb: 'tb_1#0' },
      children: ['burst_1#0', 'tb_1#0'], predicate_trace: null }]
    const topology = {
      nodes: [
        { node_id: 'bo', where_rules: [] },
        { node_id: 'burst', where_rules: [] },
        { node_id: 'tb', where_rules: [] },
      ],
      edges: [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }],
    }
    view.loadScanFile({
      pattern_ids: ['bottom_burst'],
      per_pattern: { bottom_burst: {
        pattern_spec: { pattern_id: 'bottom_burst', topology, event_styles: {} },
        end_node: 'tb',
      }},
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: 1, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol: 'X', per_pattern: { bottom_burst: {
        summary: { matches: 1 }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = 'X'
    view.activePatternId = 'bottom_burst'
    // 触发 marker 单归属分支:点 burst_1(唯一归属 match_1)
    handleChartClick(
      { seriesName: 'intervals', data: { instance_id: 'burst_1#0' } }, matches, view)
    // ★ 核心断言:highlightedEventIds 沿协议展开,含 BO(修复 UI bug 的 essence)
    expect(view.highlightedEventIds.has('burst_1#0')).toBe(true)
    expect(view.highlightedEventIds.has('tb_1#0')).toBe(true)
    expect(view.highlightedEventIds.has('bo_5#0')).toBe(true)   // ← child_refs 展开
    expect(view.selectedMatchId).toBe('match_1')
  })

  it('未选中 match 时 highlightedEventIds 是空集(clearFocus 自动清)', () => {
    const view = useViewStore()
    // 无需 loadScanFile;clearFocus() → selectedMatch 为 null → computed 是 empty set
    view.clearFocus()
    expect(view.highlightedEventIds.size).toBe(0)
  })
})

// ─── Task 4 · marker filter 判据改用 matchedIdsOf(tier/click 对齐)─────────────
// Task 3 使 highlightedEventIds 沿 matchedIds 协议展开、BO tier=matched;但 KlineChart.ts
// 的 marker filter 仍读 m.children(不含 bo),点 bo 会走 fallback——tier 与 click 语义不一致。
// 本 describe 覆盖协议展开后 filter 的三分支:多归属 candidate / 单归属 select / 真无归属 fallback。
describe('handleChartClick × marker filter matchedIdsOf 协议展开(Task 4)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  /** Task 4 fixture helper:抽离三 it 共享的 loadScanFile 骨架(单 pattern/单 symbol/单 result,
   * end_node 固定 'tb'),只保留 events/matches/topology 具体差异按参数传入。
   * scan.hits/summary.matches 从 matches.length 派生(与各 it 原 inline 值一致:非空→hits=1)。*/
  function seedFullFixture(
    view: ReturnType<typeof useViewStore>,
    opts: { events: any[]; matches: MatchDict[]; topology: any; symbol?: string; activePatternId?: string },
  ): void {
    const { events, matches, topology, symbol = 'X', activePatternId = 'bottom_burst' } = opts
    view.loadScanFile({
      pattern_ids: [activePatternId],
      per_pattern: { [activePatternId]: {
        pattern_spec: { pattern_id: activePatternId, topology, event_styles: {} },
        end_node: 'tb' } },
      scan: { scan_ts: 't', start_date: '2024-01-01', end_date: '2024-12-31', workers: 1,
              scanned: 1, hits: matches.length > 0 ? 1 : 0, errors: 0, dataset_dir: '', params: '',
              win_start: '2024-01-01', win_end: '2024-12-31', label_horizon: 20 },
      results: [{ symbol, per_pattern: { [activePatternId]: {
        summary: { matches: matches.length }, analysis: { events, matches }, max_forward_return: null } } }],
    } as any)
    view.symbol = symbol
    view.activePatternId = activePatternId
  }

  it('marker click × 多归属:同一实例被 2+ match 的 node_index 引用 → candidate 分支', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    // Task 5 契约变更:归属只按 match.node_index 精确引用(删除 children/anchor 身份
    // 展开)。多归属 = 同一 instance_id 被 2+ match 引用(真共享实例)
    const events = [
      { instance_id: 'tb_shared#0', node_id: 'tb', start_idx: 10, end_idx: 10, child_refs: {} },
    ]
    const matches = [
      { match_id: 'match_A', start_idx: 5, end_idx: 10,
        node_index: { tb: 'tb_shared#0' },
        children: ['tb_shared#0'], predicate_trace: null },
      { match_id: 'match_B', start_idx: 5, end_idx: 12,
        node_index: { tb: 'tb_shared#0' },
        children: ['tb_shared#0'], predicate_trace: null },
    ]
    const topology = {
      nodes: [
        { node_id: 'tb', where_rules: [] },
      ],
      edges: [],
    }
    seedFullFixture(view, { events, matches, topology })
    // tb_shared 的 #0 实例被 match_A 与 match_B 的 node_index 同时引用 → 属于两条 match
    handleChartClick(
      { seriesName: 'price-points', data: { instance_id: 'tb_shared#0' } }, matches, view)
    expect([...view.candidateMatchIds].sort()).toEqual(['match_A', 'match_B'])
    expect(view.pendingDisambigInstanceId).toBe('tb_shared#0')
    expect(view.selectedMatchId).toBeNull()          // candidate 与 selected 互斥
    expect(view.highlightedEventIds.size).toBe(0)    // selectedMatch=null → computed 空集
  })

  it('marker click × 单归属:实例只被 1 条 match 的 node_index 引用 → selectMatch + highlight 沿 child_refs 展开', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const events = [
      { instance_id: 'burst_A#0', node_id: 'burst', start_idx: 5, end_idx: 7,
        child_refs: { members: ['bo_5#0'] } },
      { instance_id: 'tb_A#0', node_id: 'tb', start_idx: 10, end_idx: 10,
        child_refs: {}, anchor_bo_id: 'bo_5#0' },
      { instance_id: 'bo_5#0', node_id: 'bo', start_idx: 5, end_idx: 5, child_refs: {} },
    ]
    const matches = [{ match_id: 'match_A', start_idx: 5, end_idx: 10,
      node_index: { burst: 'burst_A#0', tb: 'tb_A#0' },
      children: ['burst_A#0', 'tb_A#0'], predicate_trace: null }]
    const topology = {
      nodes: [
        { node_id: 'bo', where_rules: [] },
        { node_id: 'burst', where_rules: [] },
        { node_id: 'tb', where_rules: [] },
      ],
      edges: [{ src: 'burst', dst: 'tb', kind: 'temporal', rule: '', anchor_field: 'anchor_bo_id' }],
    }
    seedFullFixture(view, { events, matches, topology })
    // 实例级入口(带 instance_id):tb_A#0 单实例被 match_A 的 node_index 精确引用 → 直选
    handleChartClick(
      { seriesName: 'price-points', data: { instance_id: 'tb_A#0' } }, matches, view)
    expect(view.selectedMatchId).toBe('match_A')
    expect(view.highlightedEventIds.has('bo_5#0')).toBe(true)   // 协议展开
    expect(view.focusedInstanceRef).toBe('tb_A#0')
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('marker click × 真无归属:qualified/detected tier bo → fallback,只选实例', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    const events = [
      { instance_id: 'bo_99#0', node_id: 'bo', start_idx: 99, end_idx: 99, child_refs: {} },
    ]
    const matches: MatchDict[] = []
    const topology = { nodes: [], edges: [] }
    seedFullFixture(view, { events, matches, topology })
    handleChartClick(
      { seriesName: 'price-points', data: { instance_id: 'bo_99#0' } }, matches, view)
    expect(view.selectedMatchId).toBeNull()
    expect(view.focusedInstanceRef).toBe('bo_99#0')
    expect(view.highlightedEventIds.size).toBe(0)
    expect(view.candidateMatchIds.size).toBe(0)
  })
})

// ─── Task 3 · handleChartClick 3 分支迁移到 view.focus{Match,Event}/clearFocus ───
// 复用 Task 2(stores.focus-actions.spec.ts)同构 fixture:bo/ta 两 node,e_ta_1 唯一归属 m1,
// e_ta_2 唯一归属 m2 —— 与该文件已验证的 focusEvent('e_ta_1') 场景逐字一致。独立复制避免跨文件耦合
// (承本文件既有 seedMatches/seedFullFixture 的 per-describe 本地 fixture 惯例)。
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
        { instance_id: 'e_bo_1#0', node_id: 'bo', start_idx: 10, end_idx: 10, child_refs: {} },
        { instance_id: 'e_ta_1#0', node_id: 'ta', start_idx: 12, end_idx: 15,
          anchor_bo_id: 'e_bo_1#0', child_refs: {} },
        { instance_id: 'e_ta_2#0', node_id: 'ta', start_idx: 20, end_idx: 22,
          anchor_bo_id: 'e_bo_1#0', child_refs: {} },
        { instance_id: 'e_ta_3#0', node_id: 'ta', start_idx: 30, end_idx: 32,
          anchor_bo_id: 'e_bo_1#0', child_refs: {} },
      ],
      matches: [
        { match_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'e_ta_1#0' }, children: ['e_ta_1#0'] },
        { match_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'e_ta_2#0' }, children: ['e_ta_2#0'] },
        // e_ta_2 属于 m2;e_ta_3 不属于任何 match(0 归属)
      ],
    } as any, summary: { matches: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('handleChartClick · 焦点意图迁移(Task 3)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('空白 click → clearFocus:focusedMatchId/实例焦点 都清 · candidates 清', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    view.loadScanFile(makeFixture())              // 复用现有 fixture 或此文件顶部的 makeFixture
    view.setCandidateMatches(['m1', 'm2'])
    view.focusMatch('m1')
    handleChartClick(null, [], view)
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedInstanceRef).toBeNull()
    expect(view.candidateMatchIds.size).toBe(0)
  })

  it('bracket click → focusMatch:focusedMatchId=matchId · 实例焦点=null · manual 清空 · showTrace=true', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')                  // manual={bo}
    view.toggleExpandedNode('ta')                  // manual={bo,ta}(多展开)
    const matches = view.effectiveAnalysis!.matches
    handleChartClick(
      { seriesName: 'brackets', data: { match_id: 'm1' } },
      matches, view
    )
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedInstanceRef).toBeNull()
    expect(view.manualExpandedNodes.size).toBe(0)  // focusMatch collapse all
    expect(view.showTrace).toBe(true)
  })

  it('marker click 唯一归属 → focusEvent:焦点两非空 · showTrace=false', async () => {
    const view = useViewStore()
    const { handleChartClick } = await import('../src/components/KlineChart')
    view.loadScanFile(makeFixture())
    const matches = view.effectiveAnalysis!.matches
    handleChartClick(
      { seriesName: 'points', data: { instance_id: 'e_ta_1#0' } },
      matches, view
    )
    expect(view.focusedMatchId).toBe('m1')
    expect(view.focusedInstanceRef).toBe('e_ta_1#0')
    expect(view.showTrace).toBe(false)
  })
})
