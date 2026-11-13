// Task 8 · focusHit / focusEvent(单入口 instance_id)/ clearFocus 单元测。
// 规格变更(2026-11-05 队长裁定,不是放宽):聚焦不再自动降档(原 autoFollowLevel 已删),档位按钮只由用户点;
// 下面两条 level 用例相应改成「level 不动」。
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

  it('focusHit("m1"):focusedHitId=m1 · 实例焦点清 · manual=null · 细框清 · showTrace=true', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.toggleExpandedNode('bo')                  // 先 manual = {bo}
    view.toggleExpandedNode('ta')                  // 再加 ta → {bo, ta}(多展开)
    view.focusHit('m1')
    expect(view.focusedHitId).toBe('m1')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.manualExpandedNodes.size).toBe(0)  // focusHit → collapse all(trace 独占)
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.showTrace).toBe(true)
  })

  it('focusEvent 单入口:按 instance_id 只选中这个 event;用到它的那次 hit 画细框,不算选中', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.focusEvent('ta_12_15#0')
    // 点 event 选中的就是它;用到它的 hit 在它里面,要按键进去才选中
    expect(view.selPath).toEqual([{ kind: 'node', band: 'ta' }, { kind: 'event', instanceId: 'ta_12_15#0' }])
    expect(view.selectedInstanceId).toBe('ta_12_15#0')
    expect(view.focusedHitId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect([...view.candidateHitIds]).toEqual(['m1'])
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
    // 不在 node_index 中)→ 没有 hit 用到它 → 只聚焦实例
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

  it('聚焦不改档位:选 detected 实例 + level=in_hit → level 仍是 in_hit,实例照样选中', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('in_hit')
    // ta_30_32#0 是 0 归属 → tier=detected(不在 inHitIds,若也不在 qualifiedIds 则 detected)
    view.focusEvent('ta_30_32#0')
    expect(view.level).toBe('in_hit')
    expect(view.selectedInstanceId).toBe('ta_30_32#0')
  })

  it('聚焦不改档位:选 in_hit 实例 + level=in_hit → level 不动', () => {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('in_hit')
    view.focusEvent('ta_12_15#0')                  // 1 归属 · in_hit
    expect(view.level).toBe('in_hit')
  })

  it('focusHit 不改档位', () => {
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
// 点 event 一律只选中这个 event;用到它的 hit = hit.node_index 值(instance_id 字符串)精确引用它的那些,画细框。
// 被几次 hit 共用的实例:走进它的买点日、停在整天上时,它还在用(pendingDisambig),再往里才选中其中一次
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

  it('focusEvent 按 instance_id 认实例:同一跨度的两个实例各牵出自己那一次 hit', () => {
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
    expect(view.selectedInstanceId).toBe('tb_v1_293#0')
    expect([...view.candidateHitIds]).toEqual([m0.hit_id])  // 用到 #0 的是 hit A
    expect(view.focusedHitId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
    view.focusEvent('tb_v1_293#1')
    expect(view.selectedInstanceId).toBe('tb_v1_293#1')
    expect([...view.candidateHitIds]).toEqual([m1.hit_id])  // 用到 #1 的是 hit B
  })

  it('focusEvent 真共享:同一 instance_id 被两 hit 引用 → 两次都画细框、都不选中;走进它的买点日后那天叠着这两次', () => {
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
    expect(view.selectedInstanceId).toBe('tb_s#0')
    expect(view.candidateHitIds.size).toBe(2)
    expect(view.focusedHitId).toBeNull()
    // 这条 band 上只有它、只牵出一天:→ 进那一天;那天叠着两次,停在整天上,这个实例还在用
    view.stepPos(1)
    expect(view.selLast).toEqual({ kind: 'buy', day: 3 })
    expect(view.focusedHitId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBe('tb_s#0')
    expect(view.selDayHitIds).toEqual(['bb@0-3a', 'bb@0-3b'])
    view.stepStack(1)
    expect([view.focusedHitId, view.focusedInstanceId]).toEqual(['bb@0-3a', 'tb_s#0'])
    expect(view.pendingDisambigInstanceId).toBeNull()
  })
})
