// Task 8 · focusHit / focusEvent(单入口 instance_id)/ clearFocus + autoFollowLevel 单元测。
// 与 spec §5「focusEvent 单入口:focusEvent(instanceId: string)」逐行对齐。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, HitDict, EventDict, SerializedPattern } from '../src/types'

// 基础 fixture:1 pattern · 2 nodes(bo/ta)· 1 edge · ta 3 实例(2 归属 1 无) · hits 2
function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: {
      pattern_id: 'p1',
      topology: {
        nodes: [
          { node_id: 'bo', render_grid: 'price', where_rules: [] },
          { node_id: 'ta', render_grid: 'time', where_rules: [] },
        ],
        edges: [{ src: 'bo', dst: 'ta', kind: 'TemporalEdge', rule: '', anchor_field: 'anchor_bo_id' }],
      },
      event_styles: {},
    } as any } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [
        { instance_id: 'bo_10#0', node_id: 'bo', instance_idx: 0, start_idx: 10, end_idx: 10, child_refs: {} },
        { instance_id: 'ta_12_15#0', node_id: 'ta', instance_idx: 0, start_idx: 12, end_idx: 15,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
        { instance_id: 'ta_20_22#0', node_id: 'ta', instance_idx: 1, start_idx: 20, end_idx: 22,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
        { instance_id: 'ta_30_32#0', node_id: 'ta', instance_idx: 2, start_idx: 30, end_idx: 32,
          anchor_bo_id: 'bo_10#0', child_refs: {} },
      ],
      hits: [
        { hit_id: 'm1', start_idx: 10, end_idx: 15, node_index: { ta: 'ta_12_15#0' }, children: ['bo_10#0', 'ta_12_15#0'] },
        { hit_id: 'm2', start_idx: 12, end_idx: 22, node_index: { ta: 'ta_20_22#0' }, children: ['bo_10#0', 'ta_20_22#0'] },
        // ta_30_32#0 不属于任何 hit(0 归属)
      ],
    } as any, summary: { hits: 2 } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusHit / focusEvent(单入口)/ clearFocus', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('focusHit("m1"):focusedHitId=m1 · 实例焦点清 · manual=null · candidates 清 · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')                  // 先 manual = {bo}
    view.toggleExpandedNode('ta')                  // 再加 ta → {bo, ta}(多展开)
    view.setCandidateHits(['m1', 'm2'])
    view.focusHit('m1')
    expect(view.focusedHitId).toBe('m1')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.manualExpandedNodes.size).toBe(0)  // focusHit → collapse all(trace 独占)
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.showTrace).toBe(true)
  })

  it('focusEvent 单入口:按 instance_id 直选(1 归属)→ focusedHitId + focusedInstanceId', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_12_15#0')
    expect(view.focusedHitId).toBe('m1')
    expect(view.focusedInstanceId).toBe('ta_12_15#0')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect(view.showTrace).toBe(false)
  })

  it('focusEvent 0 归属:ta_30_32#0 → selectedInstanceId 聚焦 · hit 不设', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_30_32#0')
    expect(view.focusedHitId).toBeNull()
    expect(view.selectedInstanceId).toBe('ta_30_32#0')
    expect(view.focusedInstanceId).toBeNull()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.markedEventIds.has('ta_30_32#0')).toBe(true)
  })

  it('focusEvent 0 归属(anchor 不在 node_index):bo_10#0 → 只聚焦实例(Task 5 契约延续)', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    // 归属判定只按 hit.node_index 精确引用;bo_10#0 是 anchor(仅经 anchor_field 反查、
    // 不在 node_index 中)→ 0 归属 → 只聚焦实例,不再弹待选择
    view.focusEvent('bo_10#0')
    expect(view.focusedHitId).toBeNull()
    expect(view.selectedInstanceId).toBe('bo_10#0')
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.pendingDisambigInstanceId).toBeNull()
    expect(view.markedEventIds.has('bo_10#0')).toBe(true) // 信息层聚焦实例
    expect(view.expandedNodeIds.has('bo')).toBe(true)    // focusEvent add → 含 bo
  })

  it('clearFocus:双清 + candidates 清', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusHit('m1')
    view.clearFocus()
    expect(view.focusedHitId).toBeNull()
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.showTrace).toBe(false)
  })

  it('level auto-follow:选 detected 实例 + level=in_hit → setLevel("detected")', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('in_hit')
    // ta_30_32#0 是 0 归属 → tier=detected(不在 inHitIds,若也不在 qualifiedIds 则 detected)
    view.focusEvent('ta_30_32#0')
    expect(view.level).toBe('detected')
  })

  it('level auto-follow:选 in_hit 实例 + level=in_hit → level 不动', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('in_hit')
    view.focusEvent('ta_12_15#0')                  // 1 归属 · in_hit
    expect(view.level).toBe('in_hit')
  })

  it('focusHit 不触发 level auto-follow', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('in_hit')
    view.focusHit('m1')
    expect(view.level).toBe('in_hit')
  })

  it('clearFocus 补丁: 一并清 shiftSelectedEvents', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setShiftSelectedEvents([{ instance_id: 'bo_10#0', node_id: 'BO', source: 'main' }])
    view.focusedInstanceId = 'ta_12_15#0'
    view.clearFocus()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.shiftSelectedEvents.length).toBe(0)      // shift 也被清
  })
})

// ── Task 8(marker 实例绑定):focusEvent 单入口分级语义 ──────────────────────────
// 归属 = hit.node_index 值(instance_id 字符串)精确引用计数 0/1/≥2
//   0 → 只聚焦实例;1 → 直选 hit;≥2 → pendingDisambig(真共享实例)
function makeDualEntryFixture(events: EventDict[], hits: HitDict[]): MultiScanResultFile {
  const pattern: SerializedPattern = {
    pattern_id: 'p1',
    topology: {
      nodes: [
        { node_id: 'burst', render_grid: 'time', where_rules: [] },
        { node_id: 'tb', render_grid: 'time', where_rules: [] },
      ],
      edges: [],
    },
    event_styles: {},
  } as any
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: { pattern_spec: pattern } as any },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events, hits,
    } as any, summary: { hits: hits.length } } as any } } as any],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 } as any,
  } as any
}

describe('view store · focusEvent 单入口(Task 8 实例绑定)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('focusEvent 按 instance_id 直选分属实例(不再待选择)', () => {
    // APCX 形态:两 hit 的 node_index 分别引用 tb_v1_293#0/#1(各属一个 hit)
    const m0 = { hit_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#0', tb: 'tb_v1_293#0' },
                 children: ['burst_0_2#0', 'tb_v1_293#0'], predicate_trace: null } as HitDict
    const m1 = { hit_id: 'bb@0-3#burst:burst_0_2|tb:tb_v1_293b', start_idx: 0, end_idx: 3,
                 node_index: { burst: 'burst_0_2#1', tb: 'tb_v1_293#1' },
                 children: ['burst_0_2#0', 'tb_v1_293#0'], predicate_trace: null } as HitDict
    const events: EventDict[] = [
      { instance_id: 'tb_v1_293#0', node_id: 'tb', instance_idx: 0, start_idx: 12, end_idx: 15, child_refs: {} } as any,
      { instance_id: 'tb_v1_293#1', node_id: 'tb', instance_idx: 1, start_idx: 20, end_idx: 22, child_refs: {} } as any,
      { instance_id: 'burst_0_2#0', node_id: 'burst', instance_idx: 0, start_idx: 8, end_idx: 8, child_refs: {} } as any,
    ]
    const view = useViewStore()
    view.loadScanFile(makeDualEntryFixture(events, [m0, m1]))
    view.focusEvent('tb_v1_293#0')
    expect(view.focusedHitId).toBe(m0.hit_id)          // 直选 hit A
    expect(view.focusedInstanceId).toBe('tb_v1_293#0')
    expect(view.pendingDisambigInstanceId).toBeNull()       // 不再弹待选择
    view.focusEvent('tb_v1_293#1')
    expect(view.focusedHitId).toBe(m1.hit_id)          // 直选 hit B
  })

  it('focusEvent 真共享:同一 instance_id 被两 hit 引用 → 待选择', () => {
    const m0 = { hit_id: 'bb@0-3a', start_idx: 0, end_idx: 3,
                 node_index: { tb: 'tb_s#0' }, children: ['tb_s#0'], predicate_trace: null } as HitDict
    const m1 = { hit_id: 'bb@0-3b', start_idx: 0, end_idx: 3,
                 node_index: { tb: 'tb_s#0' }, children: ['tb_s#0'], predicate_trace: null } as HitDict
    const events: EventDict[] = [
      { instance_id: 'tb_s#0', node_id: 'tb', instance_idx: 0, start_idx: 12, end_idx: 15, child_refs: {} } as any,
    ]
    const view = useViewStore()
    view.loadScanFile(makeDualEntryFixture(events, [m0, m1]))
    view.focusEvent('tb_s#0')
    expect(view.pendingDisambigInstanceId).toBe('tb_s#0')
    expect(view.candidateHitIds.size).toBe(2)
    expect(view.focusedHitId).toBeNull()
  })
})
