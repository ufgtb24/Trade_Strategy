import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import DetailSidebar from '../../src/components/DetailSidebar.vue'
import { useViewStore } from '../../src/stores/view'
import * as api from '../../src/api'
import type { MultiScanResultFile, Diagnostics } from '../../src/types'

// ─── Inline 5-node fixture ───────────────────────────────────────────────────
// 拓扑: down(trend0) / side(trend1) / bo(bo — 孤立,无边) / burst(burst) / tb(tb)
// 边: down→burst / side→burst / burst→tb  (bo 无边 = 流源)
const INLINE_SCAN: MultiScanResultFile = {
  pattern_ids: ['test_pattern'],
  per_pattern: {
    test_pattern: {
      pattern_spec: {
        pattern_id: 'test_pattern',
        topology: {
          nodes: [
            { node_id: 'down',  class_id: 'trend', source_tag: 'trend0', where_rules: [{ clause_id: 'drawdown', op: '>=', threshold: 0.30 }] },
            { node_id: 'side',  class_id: 'trend', source_tag: 'trend1', where_rules: [] },
            { node_id: 'bo',    class_id: 'bo',    source_tag: 'bo',     where_rules: [] },
            { node_id: 'burst', class_id: 'burst', source_tag: 'burst',  where_rules: [{ clause_id: 'vol', op: '>=', threshold: 2.0 }] },
            { node_id: 'tb',    class_id: 'tb',    source_tag: 'tb',     where_rules: [] },
          ],
          edges: [
            { src: 'down',  dst: 'burst', kind: 'TemporalEdge',    rule: 'before' },
            { src: 'side',  dst: 'burst', kind: 'ContainmentEdge', rule: 'contains' },
            { src: 'burst', dst: 'tb',    kind: 'TemporalEdge',    rule: 'gap=1' },
          ],
        },
        event_styles: { trend: '#f59e0b', bo: '#2563eb', burst: '#7c3aed', tb: '#16a34a' },
      },
      end_role: 'tb',
    },
  },
  scan: {
    scan_ts: '20260609T120000', start_date: '2025-01-01', end_date: '2025-12-31',
    workers: 8, scanned: 100, hits: 1, errors: 0, dataset_dir: '/x', params: 'default',
    win_start: '2025-01-01', win_end: '2025-12-31', label_horizon: 20,
  },
  results: [
    {
      symbol: 'TEST',
      per_pattern: {
        test_pattern: {
          summary: { trend: 4, bo: 3, burst: 2, tb: 1, matches: 1 },
          analysis: {
            events: [
              // trend0 band: down 事件 2 个 (down1 匹配, down2 仅 qualified)
              { class_id: 'trend', event_id: 'down1',  source_tag: 'trend0', start_idx: 1,  end_idx: 6,  drawdown: 0.42 },
              { class_id: 'trend', event_id: 'down2',  source_tag: 'trend0', start_idx: 10, end_idx: 15, drawdown: 0.20 },
              // trend1 band: side 事件 2 个 (side1 匹配, side2 detected only)
              { class_id: 'trend', event_id: 'side1',  source_tag: 'trend1', start_idx: 4,  end_idx: 12 },
              { class_id: 'trend', event_id: 'side2',  source_tag: 'trend1', start_idx: 20, end_idx: 28 },
              // bo band: 3 点事件 (无边 → 流源)
              { class_id: 'bo', event_id: 'bo9',  source_tag: 'bo', start_idx: 9,  end_idx: 9 },
              { class_id: 'bo', event_id: 'bo11', source_tag: 'bo', start_idx: 11, end_idx: 11 },
              { class_id: 'bo', event_id: 'bo20', source_tag: 'bo', start_idx: 20, end_idx: 20 },
              // burst band: 1 匹配
              { class_id: 'burst', event_id: 'burst1', source_tag: 'burst', start_idx: 13, end_idx: 13, vol: 3.1 },
              // tb band: 1 匹配
              { class_id: 'tb', event_id: 'tb14', source_tag: 'tb', start_idx: 14, end_idx: 14 },
            ],
            matches: [
              {
                event_id: 'm1', start_idx: 1, end_idx: 14,
                role_index: { down: 'down1', side: 'side1', burst: 'burst1', tb: 'tb14' },
                children: ['down1', 'side1', 'burst1', 'tb14', 'bo9', 'bo11'],
                predicate_trace: {
                  where_results: {
                    down:  { drawdown: { satisfied: true,  measured: 0.42, op: '>=', threshold: 0.30 } },
                    burst: { vol:      { satisfied: true,  measured: 3.1,  op: '>=', threshold: 2.0  } },
                  },
                  edge_results: {
                    'down→burst':  { satisfied: true, measured: 7,  src: 'down1',  dst: 'burst1' },
                    'burst→tb':    { satisfied: true, measured: 1,  src: 'burst1', dst: 'tb14' },
                  },
                },
              },
            ],
          },
          max_forward_return: null,
        },
      },
    },
  ],
}

// inline diag: down 有 2 行(down1 满足=qualified, down2 未满足);burst 有 1 行
const INLINE_DIAG: Diagnostics = {
  symbol: 'TEST',
  pattern_id: 'test_pattern',
  roles: {
    down: {
      attr: [
        { event_id: 'down1', start_idx: 1,  end_idx: 6,
          clauses: { drawdown: { satisfied: true,  measured: 0.42, op: '>=', threshold: 0.30 } } },
        { event_id: 'down2', start_idx: 10, end_idx: 15,
          clauses: { drawdown: { satisfied: false, measured: 0.20, op: '>=', threshold: 0.30 } } },
      ],
      rel: [],
    },
    side: {
      attr: [
        { event_id: 'side1', start_idx: 4, end_idx: 12, clauses: {} },
      ],
      rel: [],
    },
    burst: {
      attr: [
        { event_id: 'burst1', start_idx: 13, end_idx: 13,
          clauses: { vol: { satisfied: true, measured: 3.1, op: '>=', threshold: 2.0 } } },
      ],
      rel: [],
    },
    tb: {
      attr: [
        { event_id: 'tb14', start_idx: 14, end_idx: 14, clauses: {} },
      ],
      rel: [],
    },
  },
  note: '单 role 局部诊断',
}

// ─── Setup helper ────────────────────────────────────────────────────────────
function setupStore() {
  const v = useViewStore()
  vi.spyOn(api, 'getDiagnose').mockResolvedValue(INLINE_DIAG)
  v.loadScanFile(INLINE_SCAN)
  v.selectSymbol('TEST')
  return v
}

describe('DetailSidebar (5-node: pattern roles + stream-source)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── 断言 1: 漏斗总览结构 ──────────────────────────────────────────────────
  it('渲染漏斗行(pattern roles)和密度徽标行(bo 流源)', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    const text = w.text()

    // pattern roles 有 detected ▸ qualified ▸ matched 漏斗
    expect(text).toContain('▸')   // 漏斗收窄符

    // bo 是孤立流源 → 密度徽标行,含"原始检测"
    expect(text).toContain('原始检测')

    // bo 行不含 matched 漏斗:断言 text 在 bo 相关位置包含"原始检测 3"(3 个 bo 点事件)
    // 通过查找密度徽标的具体数字验证
    expect(text).toContain('原始检测 3')
  })

  // ── 断言 2: bo 不含 matched 漏斗 ─────────────────────────────────────────
  it('bo 徽标行不含 matched 漏斗(无 ▸ 符号嵌套在 bo 行)', async () => {
    setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 找 bo 行的 DOM — isolated node 没有 expand-icon(▲▼)
    const funnelRows = w.findAll('.funnel-row')
    // bo 行应包含"原始检测",不含 expand-icon
    const boRow = funnelRows.find(r => r.text().includes('原始检测'))
    expect(boRow).toBeTruthy()
    // bo 行内没有漏斗 expand icon
    expect(boRow!.find('.expand-icon').exists()).toBe(false)
  })

  // ── 断言 3: 点 pattern role 行 → 候选表展开 ─────────────────────────────
  it('点 down 行展开候选表,显示 clause 列和 attr 行', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 找 down 漏斗行并点击
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))
    expect(downRow).toBeTruthy()
    await downRow!.trigger('click')

    const text = w.text()
    // 候选表出现
    expect(w.find('.candidate-table-wrap').exists()).toBe(true)
    // down 的 clause: drawdown
    expect(text).toContain('drawdown')
    // down1 的行: 0.42
    expect(text).toContain('0.42')
  })

  // ── 断言 4: 双向高亮 — 点候选表行 → selectEvent ─────────────────────────
  it('点候选表行 → selectedEventId 更新', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 展开 down 候选表
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    await downRow.trigger('click')

    // 点 down1 的 attr-row
    const attrRows = w.findAll('.attr-row')
    const down1Row = attrRows.find(r => r.text().includes('1-6'))
    expect(down1Row).toBeTruthy()
    await down1Row!.trigger('click')

    expect(v.selectedEventId).toBe('down1')
  })

  // ── 断言 5: 双向高亮 — selectedEventId 反映到高亮 class ─────────────────
  it('设 selectedEventId 后对应行有 attr-row--selected class', async () => {
    const v = setupStore()
    v.selectEvent('down1')
    const w = mount(DetailSidebar)
    await flushPromises()

    // 展开 down 候选表才能看到行
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    await downRow.trigger('click')

    const attrRows = w.findAll('.attr-row')
    const down1Row = attrRows.find(r => r.text().includes('1-6'))
    expect(down1Row).toBeTruthy()
    expect(down1Row!.classes()).toContain('attr-row--selected')
  })

  // ── 断言 6: per-match trace 在 selectMatch 后渲染 ────────────────────────
  it('selectMatch 后渲染 trace(where_results + edge_results)', async () => {
    const v = setupStore()
    v.selectMatch('m1')
    const w = mount(DetailSidebar)
    await flushPromises()

    const text = w.text()
    // where trace: down 的 drawdown
    expect(text).toContain('drawdown')
    expect(text).toContain('0.42')
    // edge trace
    expect(text).toContain('down→burst')
  })

  // ── 断言 7: 计数正确性 ───────────────────────────────────────────────────
  it('matched 计数正确:down matched=1 / burst matched=1', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // matchedIds = children of m1 = ['down1','side1','burst1','tb14','bo9','bo11']
    // trend0 band events = ['down1','down2']  → matched in trend0 = 1 (down1)
    // burst band events  = ['burst1']         → matched in burst  = 1

    // 找 down 漏斗行:格式为 detected ▸ qualified ▸ matched
    // detected=2(down1+down2), qualified=1(down1,因为 down1 满足 clauses), matched=1(down1)
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    const downText = downRow.text()
    // 确认包含 2 ▸ ... ▸ 1  (detected=2, matched=1)
    const nums = downText.match(/\d+/g)?.map(Number) ?? []
    expect(nums).toContain(2)   // detected=2
    expect(nums).toContain(1)   // matched=1

    // burst 行: detected=1, matched=1
    const burstRow = funnelRows.find(r => r.text().includes('burst'))!
    const burstNums = burstRow.text().match(/\d+/g)?.map(Number) ?? []
    expect(burstNums).toContain(1)  // both detected and matched = 1
  })

  // ── 断言 8: bo 密度计数 = 3 ──────────────────────────────────────────────
  it('bo 流源密度 = 3(bo9/bo11/bo20)', async () => {
    setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    const funnelRows = w.findAll('.funnel-row')
    const boRow = funnelRows.find(r => r.text().includes('原始检测'))!
    expect(boRow.text()).toContain('原始检测 3')
  })

  // ── 断言 9: 命中匹配列表渲染 + forward_return 显示 ─────────────────────
  it('命中匹配列表渲染,有 forward_return 时显示 ret_N 行', async () => {
    // 构造带 label_horizon + forward_return 的 scan file
    const baseResult = INLINE_SCAN.results[0].per_pattern.test_pattern
    const scanWithLabel = {
      ...INLINE_SCAN,
      scan: { ...INLINE_SCAN.scan, label_horizon: 20 },
      results: [
        {
          symbol: 'TEST',
          per_pattern: {
            test_pattern: {
              ...baseResult,
              analysis: {
                ...baseResult.analysis,
                matches: [
                  { ...baseResult.analysis.matches[0], forward_return: 0.05 },
                ],
              },
            },
          },
        },
      ],
    }
    const v = useViewStore()
    vi.spyOn(api, 'getDiagnose').mockResolvedValue(INLINE_DIAG)
    v.loadScanFile(scanWithLabel as any)
    v.selectSymbol('TEST')
    const w = mount(DetailSidebar)
    await flushPromises()

    // 命中匹配列表应可见
    expect(w.find('.match-row').exists()).toBe(true)
    // forward_return 行可见
    expect(w.find('.match-ret').exists()).toBe(true)
    expect(w.find('.ret-pos').exists()).toBe(true)  // 0.05 >= 0 → 绿色
    expect(w.text()).toContain('ret_20')
  })

  // ── 断言 10: selectMatch 后 expandedNode 收起(trace 可见) ─────────────
  it('展开候选表后 selectMatch → 候选表收起,trace section 可见', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 先展开 down 候选表
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    await downRow.trigger('click')
    expect(w.find('.candidate-table-wrap').exists()).toBe(true)

    // 选中 match → 候选表收起,match-trace 可见
    v.selectMatch('m1')
    await flushPromises()

    expect(w.find('.candidate-table-wrap').exists()).toBe(false)
    expect(w.find('.match-trace').exists()).toBe(true)
  })

  // ── 断言 11: 点命中匹配行 → selectMatch + setHighlightedEvents(children) + clearCandidates ──
  it('点命中匹配行 → selected=match + 组高亮 + 候选清空', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    const matchRows = w.findAll('.match-row')
    expect(matchRows.length).toBeGreaterThan(0)
    await matchRows[0].trigger('click')

    expect(v.selected?.kind).toBe('match')
    expect((v.selected as any)?.matchId).toBe('m1')
    // 组高亮:children of m1 = ['down1', 'side1', ...]
    expect([...v.highlightedEventIds]).toEqual(expect.arrayContaining(['down1', 'side1']))
    // 候选清空:clearCandidates → candidateMatchIds = empty Set
    expect(v.candidateMatchIds.size).toBe(0)
    // selectedEventId 不改动(保持 null)
    expect(v.selectedEventId).toBeNull()
  })
})
