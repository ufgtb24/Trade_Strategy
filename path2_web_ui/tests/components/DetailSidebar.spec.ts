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
            { node_id: 'down',  where_rules: [{ clause_id: 'drawdown', op: '>=', threshold: 0.30 }] },
            { node_id: 'side',  where_rules: [] },
            { node_id: 'bo',    where_rules: [] },
            { node_id: 'burst', where_rules: [{ clause_id: 'vol', op: '>=', threshold: 2.0 }] },
            { node_id: 'tb',    where_rules: [] },
          ],
          edges: [
            { src: 'down',  dst: 'burst', kind: 'TemporalEdge',    rule: 'before' },
            { src: 'side',  dst: 'burst', kind: 'ContainmentEdge', rule: 'contains' },
            { src: 'burst', dst: 'tb',    kind: 'TemporalEdge',    rule: 'gap=1' },
          ],
        },
        event_styles: { down: '#f59e0b', side: '#f59e0b', bo: '#2563eb', burst: '#7c3aed', tb: '#16a34a' },
        debug_enabled_nodes: ['tb'],
      },
      end_node: 'tb',
    },
  },
  scan: {
    scan_ts: '20260609T120000', start_date: '2025-01-01', end_date: '2025-12-31',
    workers: 8, scanned: 100, hit_stocks: 1, errors: 0, dataset_dir: '/x', params: 'default',
    win_start: '2025-01-01', win_end: '2025-12-31', label_horizon: 20, first_passage_k: 2,
  },
  results: [
    {
      symbol: 'TEST',
      per_pattern: {
        test_pattern: {
          summary: { down: 2, side: 2, bo: 3, burst: 1, tb: 1, hits: 1 },
          analysis: {
            events: [
              // down band: 事件 2 个 (down1#0 进 hit, down2#0 仅 qualified)
              { node_id: 'down', instance_id: 'down1#0', instance_idx: 0, start_idx: 1,  end_idx: 6,  drawdown: 0.42, child_refs: {} },
              { node_id: 'down', instance_id: 'down2#0', instance_idx: 0, start_idx: 10, end_idx: 15, drawdown: 0.20, child_refs: {} },
              // side band: 事件 2 个 (side1#0 进 hit, side2#0 detected only)
              { node_id: 'side', instance_id: 'side1#0', instance_idx: 0, start_idx: 4,  end_idx: 12, child_refs: {} },
              { node_id: 'side', instance_id: 'side2#0', instance_idx: 0, start_idx: 20, end_idx: 28, child_refs: {} },
              // bo band: 3 点事件 (无边 → 流源)
              { node_id: 'bo', instance_id: 'bo9#0',  instance_idx: 0, start_idx: 9,  end_idx: 9, child_refs: {} },
              { node_id: 'bo', instance_id: 'bo11#0', instance_idx: 0, start_idx: 11, end_idx: 11, child_refs: {} },
              { node_id: 'bo', instance_id: 'bo20#0', instance_idx: 0, start_idx: 20, end_idx: 20, child_refs: {} },
              // burst band: 1 进 hit
              { node_id: 'burst', instance_id: 'burst1#0', instance_idx: 0, start_idx: 13, end_idx: 13, vol: 3.1,
                child_refs: { members: ['bo9#0', 'bo11#0'] } },
              // tb band: 1 进 hit
              { node_id: 'tb', instance_id: 'tb14#0', instance_idx: 0, start_idx: 14, end_idx: 14, child_refs: {} },
            ],
            hits: [
              {
                hit_id: 'm1', start_idx: 1, end_idx: 14,
                node_index: { down: 'down1#0', side: 'side1#0', burst: 'burst1#0', tb: 'tb14#0' },
                children: ['down1#0', 'side1#0', 'burst1#0', 'tb14#0', 'bo9#0', 'bo11#0'],
                predicate_trace: {
                  where_results: {
                    down:  { drawdown: { satisfied: true,  measured: 0.42, op: '>=', threshold: 0.30 } },
                    burst: { vol:      { satisfied: true,  measured: 3.1,  op: '>=', threshold: 2.0  } },
                  },
                  edge_results: {
                    'down→burst':  { satisfied: true, measured: { kind: 'gap', value: 7, label: 'gap' },  src: 'down1#0',  dst: 'burst1#0' },
                    'burst→tb':    { satisfied: true, measured: { kind: 'gap', value: 1, label: 'gap' },  src: 'burst1#0', dst: 'tb14#0' },
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

// inline diag: down 有 2 行(down1#0 满足=qualified, down2#0 未满足);burst 有 1 行
const INLINE_DIAG: Diagnostics = {
  symbol: 'TEST',
  pattern_id: 'test_pattern',
  nodes: {
    down: {
      attr: [
        { instance_id: 'down1#0', node_id: 'down', start_idx: 1,  end_idx: 6,
          clauses: { drawdown: { satisfied: true,  measured: 0.42, op: '>=', threshold: 0.30 } } },
        { instance_id: 'down2#0', node_id: 'down', start_idx: 10, end_idx: 15,
          clauses: { drawdown: { satisfied: false, measured: 0.20, op: '>=', threshold: 0.30 } } },
      ],
      rel: [],
    },
    side: {
      attr: [
        { instance_id: 'side1#0', node_id: 'side', start_idx: 4, end_idx: 12, clauses: {} },
      ],
      rel: [],
    },
    burst: {
      attr: [
        { instance_id: 'burst1#0', node_id: 'burst', start_idx: 13, end_idx: 13,
          clauses: { vol: { satisfied: true, measured: 3.1, op: '>=', threshold: 2.0 } } },
      ],
      rel: [],
    },
    tb: {
      attr: [
        { instance_id: 'tb14#0', node_id: 'tb', start_idx: 14, end_idx: 14, clauses: {} },
      ],
      rel: [],
    },
  },
  note: '单 node 局部诊断',
}

// ─── Setup helper ────────────────────────────────────────────────────────────
function setupStore() {
  const v = useViewStore()
  vi.spyOn(api, 'getDiagnose').mockResolvedValue(INLINE_DIAG)
  v.loadScanFile(INLINE_SCAN)
  v.selectSymbol('TEST')
  return v
}

describe('DetailSidebar (5-node: pattern nodes + stream-source)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── 断言 1: 漏斗总览结构 ──────────────────────────────────────────────────
  it('渲染漏斗行(pattern nodes)和密度徽标行(bo 流源)', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    const text = w.text()

    // pattern nodes 有 detected ▸ qualified ▸ in_hit 漏斗
    expect(text).toContain('▸')   // 漏斗收窄符

    // bo 是孤立流源 → 密度徽标行,含"原始检测"
    expect(text).toContain('原始检测')

    // bo 行不含 in_hit 漏斗:断言 text 在 bo 相关位置包含"原始检测 3"(3 个 bo 点事件)
    // 通过查找密度徽标的具体数字验证
    expect(text).toContain('原始检测 3')
  })

  // ── 断言 2: bo 不含 in_hit 漏斗 ─────────────────────────────────────────
  it('bo 徽标行不含 in_hit 漏斗(无 ▸ 符号嵌套在 bo 行)', async () => {
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

  // ── 断言 3: 点 pattern node 行 → 候选表展开 ─────────────────────────────
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

  // ── 断言 4: 双向高亮 — 点候选表行 → focusEvent ─────────────────────────
  it('点候选表行 → 选中那个 event', async () => {
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

    // 点候选表行等于点 band 上的它:选中的是这个 event(用到它的 m1 不算选中)
    expect(v.selectedInstanceId).toBe('down1#0')
    expect(v.focusedHitId).toBeNull()
  })

  // ── 断言 5: 双向高亮 — focusedInstanceId 反映到高亮 class ─────────────────
  it('设 focusedInstanceId 后对应行有 attr-row--selected class', async () => {
    const v = setupStore()
    v.focusedInstanceId = 'down1#0'   // 直写:纯测 markedEventIds 呈现,避开 focusEvent 归属判定副作用
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

  // ── 断言 6: per-hit trace 在 focusHit 后渲染 ────────────────────────
  it('focusHit 后渲染 trace(where_results + edge_results)', async () => {
    const v = setupStore()
    v.focusHit('m1')
    const w = mount(DetailSidebar)
    await flushPromises()

    const text = w.text()
    // where trace: down 的 drawdown
    expect(text).toContain('drawdown')
    expect(text).toContain('0.42')
    // edge trace
    expect(text).toContain('down→burst')
    // 硬伤 E · kind-aware measured 按 kind 加前缀(非硬编码 "gap=")
    expect(text).toContain('gap=7')
  })

  // ── 断言 7: 计数正确性 ───────────────────────────────────────────────────
  it('in_hit 计数正确:down in_hit=1 / burst in_hit=1(实例流复合键集合下不恒 miss)', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // inHitIds(复合键集)= children of m1 的实例键 = ['down1#0','side1#0','burst1#0','tb14#0','bo9#0','bo11#0']
    // trend0 band events = ['down1','down2']  → in_hit in trend0 = 1 (down1)
    // burst band events  = ['burst1']         → in_hit in burst  = 1

    // 找 down 漏斗行:格式为 detected ▸ qualified ▸ in_hit
    // detected=2(down1+down2), qualified=1(down1,因为 down1 满足 clauses), in_hit=1(down1)
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    const downText = downRow.text()
    // 精确序列断言:in_hit 段不被 qualified 段的数字掩盖(评审 C1 盲区:
    // 旧断言 nums.toContain(1) 在 in_hit=0 时仍通过)
    const nums = downText.match(/\d+/g)?.map(Number) ?? []
    expect(nums).toEqual([2, 1, 1])   // detected=2(down1+down2) · qualified=1(down1) · in_hit=1(down1)

    // burst 行: detected=1 · qualified=1(burst1 满足 vol) · in_hit=1
    const burstRow = funnelRows.find(r => r.text().includes('burst'))!
    const burstNums = burstRow.text().match(/\d+/g)?.map(Number) ?? []
    expect(burstNums).toEqual([1, 1, 1])
  })

  // ── 断言 7b: 候选表行 tier(rowTier)实例流下不降级 ────────────────────────
  it('候选表 down1 行 tier=in_hit:色条宽度 12px(in_hit 档,非 qualified 6px 降级)', async () => {
    setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 展开 down 候选表
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))
    await downRow!.trigger('click')

    // down1 是 m1 的 children(in_hit 实例),行色条宽度应取 in_hit 档 12px
    const attrRows = w.findAll('.attr-row')
    const down1Row = attrRows.find(r => r.text().includes('1-6'))   // down1: seg@1-6
    expect(down1Row).toBeTruthy()
    const cell = down1Row!.find('.cell-id')
    const borderLeft = cell!.attributes('style') ?? ''
    // 浏览器序列化为 kebab-case(border-left);12px = in_hit 档(in_hit 最宽,评审建议的
    // 色盲/低对比宽度信道),qualified 档为 6px
    expect(borderLeft).toContain('border-left: 12px solid')
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

  // ── 断言 9: hit 列表渲染 + forward_return 显示 ─────────────────────
  it('hit 列表渲染,有 forward_return 时显示 ret_N 行', async () => {
    // 构造带 label_horizon + forward_return 的 scan file
    const baseResult = INLINE_SCAN.results[0].per_pattern.test_pattern
    const scanWithLabel = {
      ...INLINE_SCAN,
      scan: { ...INLINE_SCAN.scan, label_horizon: 20, first_passage_k: 2 },
      results: [
        {
          symbol: 'TEST',
          per_pattern: {
            test_pattern: {
              ...baseResult,
              analysis: {
                ...baseResult.analysis,
                hits: [
                  { ...baseResult.analysis.hits[0], forward_return: 0.05 },
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

    // hit 列表应可见
    expect(w.find('.hit-row').exists()).toBe(true)
    // forward_return 行可见
    expect(w.find('.hit-ret').exists()).toBe(true)
    expect(w.find('.ret-pos').exists()).toBe(true)  // 0.05 >= 0 → 绿色
    expect(w.text()).toContain('ret_20')
  })

  // ── 断言 9b: hit 列表 forward_drawdown 显示(与 forward_return 同行,带 d_N 前缀) ──
  it('hit 列表渲染,有 forward_drawdown 时显示 d_N 行(带符号百分比)', async () => {
    const baseResult = INLINE_SCAN.results[0].per_pattern.test_pattern
    const scanWithDrawdown = {
      ...INLINE_SCAN,
      scan: { ...INLINE_SCAN.scan, label_horizon: 20, first_passage_k: 2 },
      results: [
        {
          symbol: 'TEST',
          per_pattern: {
            test_pattern: {
              ...baseResult,
              analysis: {
                ...baseResult.analysis,
                hits: [
                  { ...baseResult.analysis.hits[0], forward_return: 0.05, forward_drawdown: -0.08 },
                ],
              },
            },
          },
        },
      ],
    }
    const v = useViewStore()
    vi.spyOn(api, 'getDiagnose').mockResolvedValue(INLINE_DIAG)
    v.loadScanFile(scanWithDrawdown as any)
    v.selectSymbol('TEST')
    const w = mount(DetailSidebar)
    await flushPromises()

    // forward_drawdown 行可见(与 forward_return 同级 .hit-dd)
    expect(w.find('.hit-dd').exists()).toBe(true)
    expect(w.text()).toContain('d_20')
    expect(w.text()).toContain('-8.0%')
  })

  // ── 断言 10: focusHit 后 expandedNodeIds 清空(trace 可见) ─────────────
  it('展开候选表后 focusHit → 候选表收起,trace section 可见', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    // 先展开 down 候选表
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    await downRow.trigger('click')
    expect(w.find('.candidate-table-wrap').exists()).toBe(true)

    // 选中 hit → 候选表收起,hit-trace 可见
    v.focusHit('m1')
    await flushPromises()

    expect(w.find('.candidate-table-wrap').exists()).toBe(false)
    expect(w.find('.hit-trace').exists()).toBe(true)
  })

  // ── 断言 11b: 候选表行 click 把先前的选中整个换掉(互斥) ──
  it('候选表行 click 换掉先前的选中(先前选中的 hit、实例焦点都清)再选中它', async () => {
    const v = setupStore()
    // 先从 tb 走进用到它的那次 hit:选中 m1,实例焦点在 tb14
    v.focusEvent('tb14#0')
    v.stepPos(1)
    expect([v.focusedHitId, v.focusedInstanceId]).toEqual(['m1', 'tb14#0'])
    expect(v.candidateHitIds.size).toBe(1)
    const w = mount(DetailSidebar)
    await flushPromises()

    // 展开 down 候选表
    const funnelRows = w.findAll('.funnel-row')
    const downRow = funnelRows.find(r => r.text().includes('down'))!
    await downRow.trigger('click')

    // 点 down1 attr-row
    const attrRows = w.findAll('.attr-row')
    const down1Row = attrRows.find(r => r.text().includes('1-6'))!
    await down1Row.trigger('click')

    // 点了就是点的那个:先前的 hit 选中与实例焦点都清,选中的只有 down1#0
    expect(v.selPath).toEqual([{ kind: 'node', band: 'down' }, { kind: 'event', instanceId: 'down1#0' }])
    expect([v.focusedHitId, v.focusedInstanceId]).toEqual([null, null])
    expect(v.pendingDisambigInstanceId).toBeNull()
    expect(v.selectedInstanceId).toBe('down1#0')
  })

  // ── 断言 11: 点 hit 行 → 选中它 + 组高亮 + 它属于它那一族(不是从某个 event 走进来的) ──
  it('点 hit 行 → selected=hit + 组高亮 + 它属于它那一族', async () => {
    const v = setupStore()
    const w = mount(DetailSidebar)
    await flushPromises()

    const hitRows = w.findAll('.hit-row')
    expect(hitRows.length).toBeGreaterThan(0)
    await hitRows[0].trigger('click')

    expect(v.selected?.kind).toBe('hit')
    expect((v.selected as any)?.hitId).toBe('m1')
    // 组高亮:children of m1 = instance_id 列表
    expect([...v.highlightedEventIds]).toEqual(expect.arrayContaining(['down1#0', 'side1#0']))
    // 它属于它那一族:一族靠粗底线认,没有细框
    expect(v.candidateHitIds.size).toBe(0)
    expect(v.selPath[0]).toEqual({ kind: 'hit_family', familyKey: 'hits@1' })
    // 实例焦点不改动(保持 null)
    expect(v.focusedInstanceId).toBeNull()
  })
})

// ─── 组合子 clause 单元格(W.any / W.all / W.not_ 的递归 witness)──────────
// 候选表是 clause-per-column 密集网格,塞不下树 → 单元格只出 n/m(kind) 聚合,
// 逐分支明细挂 native title;完整缩进树在 K 线 hover tooltip(见 chart-helpers.spec.ts)。
describe('DetailSidebar — 组合子 clause 单元格', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  /** 2 层嵌套 witness:or → [distinct_pk, and → [max_bar_vol_ratio, not → first_drought]] */
  const NESTED_CLAUSES = {
    pk_or_vol: {
      satisfied: true, measured: null, op: null, threshold: null, label: 'or',
      children: [
        { satisfied: true, measured: 4, op: '>=', threshold: 3, label: 'distinct_pk' },
        {
          satisfied: true, measured: null, op: null, threshold: null, label: 'and',
          children: [
            { satisfied: true, measured: 5, op: '>=', threshold: 3, label: 'max_bar_vol_ratio' },
            {
              satisfied: true, measured: null, op: null, threshold: null, label: 'not',
              children: [
                { satisfied: false, measured: 45, op: '>=', threshold: 999, label: 'first_drought' },
              ],
            },
          ],
        },
      ],
    },
  }

  /** 顶层直接是 not 的 clause(单子分支) */
  const TOP_NOT_CLAUSES = {
    no_late_gap: {
      satisfied: true, measured: null, op: null, threshold: null, label: 'not',
      children: [{ satisfied: false, measured: 45, op: '>=', threshold: 999, label: 'first_drought' }],
    },
  }

  function diagWithCombinator(clauses: unknown): Diagnostics {
    const d = JSON.parse(JSON.stringify(INLINE_DIAG)) as Diagnostics
    ;(d.nodes.burst.attr[0] as any).clauses = JSON.parse(JSON.stringify(clauses))
    return d
  }

  async function mountExpandedBurst(clauses: unknown = NESTED_CLAUSES) {
    const v = useViewStore()
    vi.spyOn(api, 'getDiagnose').mockResolvedValue(diagWithCombinator(clauses))
    v.loadScanFile(INLINE_SCAN)
    v.selectSymbol('TEST')
    const w = mount(DetailSidebar)
    await flushPromises()
    const burstRow = w.findAll('.funnel-row').find(r => r.text().includes('burst'))
    expect(burstRow).toBeTruthy()
    await burstRow!.trigger('click')
    return w
  }

  it('单元格出 n/m(kind) 聚合 + 整体判定,不展开成树', async () => {
    const w = await mountExpandedBurst()
    const cell = w.findAll('.cell-clause').find(c => c.text().includes('(or)'))
    expect(cell).toBeTruthy()
    expect(cell!.text()).toContain('2/2(or)')
    expect(cell!.text()).toContain('✓')
    // 树内容不进单元格正文(只在 title 里)
    expect(cell!.text()).not.toContain('max_bar_vol_ratio')
  })

  it('title 用树线 ├ └ │ 逐层展开(与 K 线 tooltip 同款记号)', async () => {
    const w = await mountExpandedBurst()
    const title = w.find('.cell-clause [title]').attributes('title') ?? ''
    expect(title.split('\n')).toEqual([
      '├ distinct_pk: 4.000 >= 3 ✓',
      '└ and ✓',
      '  ├ max_bar_vol_ratio: 5.000 >= 3 ✓',
      '  └ not ✓',
      '    └ first_drought: 45.000 >= 999 ✗',
    ])
  })

  it('title 里组合子行不出 n/m 聚合', async () => {
    const w = await mountExpandedBurst()
    const title = w.find('.cell-clause [title]').attributes('title') ?? ''
    expect(title).not.toContain('2/2')
    expect(title).not.toContain('0/1')
  })

  it('顶层 not clause 的单元格聚合也不出 n/m', async () => {
    const w = await mountExpandedBurst(TOP_NOT_CLAUSES)
    const cell = w.findAll('.cell-clause').find(c => c.text().includes('(not)'))
    expect(cell).toBeTruthy()
    expect(cell!.text()).toContain('(not)')
    expect(cell!.text()).toContain('✓')
    expect(cell!.text()).not.toContain('0/1')
  })
})
