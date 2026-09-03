/**
 * Task 2 · anchorsOf 表 + findBoBar helper + DEBUG_ENABLED_NODES 单元测试
 *
 * 实例化契约(实例化重构后修正):
 * - 所有 tb 变体(node_id 恒为 'tb' 的容器/段/V1 + 子结构段键 tb_seg/tb_seg_v3)按
 *   锚点档位体系(2026-08-17)对齐:
 *   - tb_container(v4 容器,child_refs 非空)→ 3 项(entry/start/end);start/end 复用
 *     后端状态机埋点(端点由子段承担,前端菜单复用不产生后端双埋)
 *   - tb_seg(v4 子结构段,anchorsOf 直挂键)→ 2 项(start/end)
 *   - tb_seg_v3(v3 子结构段)→ 2 项(confirm/end);tb_segment(tb 键细分,历史段)同
 *   - tb_v1(V1 叶子)→ 3 项(entry/confirm/end),entry bar = findBoBar
 * - _default → [](防 "菜单显示但后端未埋 debug_break" 无声失败 · v2 D7)
 * - DEBUG_ENABLED_NODES 与 anchorsOf 硬耦合,单一 source of truth(v2 D8);
 *   实例化后值 = ['tb_seg','tb_seg_v3','tb'](子结构段键 + 容器/V1 键,方案 A)
 * - anchor_kind 词汇 = entry/start/end/confirm(v4 start 取代 confirm;V1/V3 仍 confirm)
 *
 * 【交错标注重构 · anchor_bo_id 真实语义】后端交错标注后 anchor_bo_id 在 detect 期即写入
 *  instance_id 形态('bo_30#0' / 'bo_30_33#0'),恒为 instance_id;findBoBar 单路径精确匹配。
 *  本文件 fixture 一律用 instance_id 形态 anchor_bo_id,events 列表须含匹配 bo。
 */
import { describe, it, expect } from 'vitest'
import { anchorsOf, findBoBar, tbAnchorProfile, DEBUG_ENABLED_NODES } from '../src/stores/view'

function mkTbEvent(overrides: Partial<any> = {}): any {
  return {
    instance_id: 'tb_1#0', node_id: 'tb',
    start_idx: 42, end_idx: 55,
    anchor_bo_id: 'bo_1#0',
    child_refs: {},
    ...overrides,
  }
}

function mkBoEvent(overrides: Partial<any> = {}): any {
  return {
    instance_id: 'bo_1#0', node_id: 'bo',
    start_idx: 30, end_idx: 30,
    ...overrides,
  }
}

describe('tbAnchorProfile(node_id 塌缩细分)', () => {
  it('child_refs 非空 → 容器(tb_container)', () => {
    const tb = mkTbEvent({ child_refs: { segments: ['tb_seg_1#0'] } })
    expect(tbAnchorProfile(tb, [tb])).toBe('tb_container')
  })

  it('child_refs 空 + 被某容器引用 → 子段(tb_segment)', () => {
    const tb = mkTbEvent({ child_refs: { segments: ['tb_seg_1#0'] } })
    const seg = mkTbEvent({ instance_id: 'tb_seg_1#0', start_idx: 44, end_idx: 50 })
    expect(tbAnchorProfile(seg, [tb, seg])).toBe('tb_segment')
  })

  it('child_refs 空 + 无人引用 → V1 叶子(tb_v1)', () => {
    const tb = mkTbEvent()
    expect(tbAnchorProfile(tb, [tb])).toBe('tb_v1')
  })
})

describe('anchorsOf', () => {
  it('tb 容器(v4)→ 3 项(entry/start/end)· start/end 复用状态机埋点', () => {
    const tb = mkTbEvent({ child_refs: { segments: ['tb_seg_1#0'] } })
    const bo = mkBoEvent()
    const anchors = anchorsOf.tb(tb, [bo, tb])
    expect(anchors).toHaveLength(3)
    expect(anchors.map(a => a.key)).toEqual(['entry', 'start', 'end'])
  })

  it('tb 容器 entry bar = findBoBar(anchor_bo_id instance_id 直连, events)', () => {
    const tb = mkTbEvent({ anchor_bo_id: 'bo_1#0', child_refs: { segments: [] } })
    const bo = mkBoEvent({ instance_id: 'bo_1#0', start_idx: 30, end_idx: 33 })
    const anchors = anchorsOf.tb(tb, [bo, tb])
    const entry = anchors.find(a => a.key === 'entry')!
    expect(entry.bar).toBe(33)
    expect(entry.disabled).toBeFalsy()
  })

  it('tb 容器 entry disabled when anchor_bo_id 直连失败(bo 不在 events)', () => {
    const tb = mkTbEvent({ anchor_bo_id: 'bo_999#0', child_refs: { segments: [] } })
    const anchors = anchorsOf.tb(tb, [tb])  // events 里没有 instance_id bo_999#0 的 bo
    const entry = anchors.find(a => a.key === 'entry')!
    expect(entry.disabled).toBe(true)
    expect(entry.disabledReason).toContain('未找到 anchor bo event')
  })

  it('tb 子段(V2/V3)→ 2 项(confirm/end)· bar 直取 span 端点', () => {
    const tb = mkTbEvent({ child_refs: { segments: ['tb_seg_1#0'] } })
    const seg = mkTbEvent({ instance_id: 'tb_seg_1#0', start_idx: 44, end_idx: 50 })
    const anchors = anchorsOf.tb(seg, [tb, seg])
    expect(anchors).toHaveLength(2)
    expect(anchors.map(a => a.key)).toEqual(['confirm', 'end'])
    expect(anchors.find(a => a.key === 'confirm')!.bar).toBe(44)
    expect(anchors.find(a => a.key === 'end')!.bar).toBe(50)
  })

  it('tb V1 叶子 → 3 项(entry/confirm/end)', () => {
    const tbv1 = mkTbEvent({ instance_id: 'tb_v1_1#0', node_id: 'tb' })
    const bo = mkBoEvent()
    const anchors = anchorsOf.tb(tbv1, [bo, tbv1])
    expect(anchors).toHaveLength(3)
    expect(anchors.map(a => a.key)).toEqual(['entry', 'confirm', 'end'])
  })

  it('tb V1 entry bar = findBoBar(anchor_bo_id instance_id 直连)', () => {
    const tbv1 = mkTbEvent({ anchor_bo_id: 'bo_1#0' })
    const bo = mkBoEvent({ instance_id: 'bo_1#0', start_idx: 30, end_idx: 33 })
    const anchors = anchorsOf.tb(tbv1, [bo, tbv1])
    expect(anchors.find(a => a.key === 'entry')!.bar).toBe(33)
    expect(anchors.find(a => a.key === 'confirm')!.bar).toBe(42)
    expect(anchors.find(a => a.key === 'end')!.bar).toBe(55)
  })

  it('tb V1 entry disabled when anchor_bo_id 直连失败', () => {
    const tbv1 = mkTbEvent({ anchor_bo_id: 'bo_999#0' })
    const anchors = anchorsOf.tb(tbv1, [tbv1])
    const entry = anchors.find(a => a.key === 'entry')!
    expect(entry.disabled).toBe(true)
  })

  it('未埋点 node(node_id 不在 anchorsOf)→ _default []', () => {
    const trend = { instance_id: 't1#0', node_id: 'trend', start_idx: 10, end_idx: 20, child_refs: {} }
    expect((anchorsOf as any)[trend.node_id] ?? anchorsOf._default).toBe(anchorsOf._default)
    expect(anchorsOf._default(trend as any, [])).toEqual([])
  })
})

describe('V4 容器样例兼容(tb v4 状态机,2026-08-16)', () => {
  // ThrowbackEventV4 与 V2/V3 同构:child_slots={"segments": ...} → child_refs.segments
  // 非空;子段 ThrowbackSegmentV4 无 child_refs、被容器 segments 槽引用。方案 A
  // (2026-08-17):bottom_burst children 声明命名表把段直标 node_id='tb_seg',
  // anchorsOf 直挂键;容器仍 'tb' 走三档细分(tb_container)。后端埋点口径:
  // 容器 entry(per-burst attempt) + start/end(复用状态机埋点)、段 start(enter)/end(exit)。
  const bo = mkBoEvent()   // end_idx 30
  const tbV4 = mkTbEvent({
    instance_id: 'tb_c1#0', start_idx: 44, end_idx: 70,
    anchor_bo_id: 'bo_1#0',
    child_refs: { segments: ['tb_seg_a#0', 'tb_seg_b#0'] },
  })
  const segA = mkTbEvent({ instance_id: 'tb_seg_a#0', node_id: 'tb_seg', start_idx: 44, end_idx: 58, child_refs: {} })

  it('V4 容器 → tb_container → 3 项(entry/start/end):entry=findBoBar,start/end=容器端点', () => {
    expect(tbAnchorProfile(tbV4, [bo, tbV4, segA])).toBe('tb_container')
    const anchors = anchorsOf.tb(tbV4, [bo, tbV4, segA])
    expect(anchors.map(a => a.key)).toEqual(['entry', 'start', 'end'])
    expect(anchors[0].bar).toBe(30)
    expect(anchors[0].disabled).toBeFalsy()
    expect(anchors.find(a => a.key === 'start')!.bar).toBe(44)
    expect(anchors.find(a => a.key === 'end')!.bar).toBe(70)
  })

  it('V4 子段(node_id=tb_seg)→ anchorsOf.tb_seg 直挂 → start/end 取段端点', () => {
    const anchors = anchorsOf.tb_seg(segA, [bo, tbV4, segA])
    expect(anchors.map(a => a.key)).toEqual(['start', 'end'])
    expect(anchors.find(a => a.key === 'start')!.bar).toBe(44)
    expect(anchors.find(a => a.key === 'end')!.bar).toBe(58)
  })

  it('未声明 app 的段(node_id=tb)→ tb 键三档细分仍可达 tb_segment 锚', () => {
    // 未声明 children 的 app:段继承容器 node_id 'tb',靠被容器 child_refs 引用判段
    const legacySeg = mkTbEvent({ instance_id: 'tb_s#0', start_idx: 44, end_idx: 58, child_refs: {} })
    const legacyTb = mkTbEvent({ instance_id: 'tb_44_58#0', start_idx: 44, end_idx: 58,
      child_refs: { segments: ['tb_s#0'] } })
    expect(tbAnchorProfile(legacySeg, [legacyTb, legacySeg])).toBe('tb_segment')
    const anchors = anchorsOf.tb(legacySeg, [legacyTb, legacySeg])
    expect(anchors.map(a => a.key)).toEqual(['confirm', 'end'])
  })
})

describe('findBoBar', () => {
  it('精确匹配:返回同 instance_id bo.end_idx', () => {
    const bo = { instance_id: 'bo_30_77#0', node_id: 'bo', start_idx: 30, end_idx: 77 } as any
    expect(findBoBar('bo_30_77#0', [bo])).toBe(77)
  })

  it('单点 bo instance_id:bo_5#0 → end_idx 5', () => {
    const bo = { instance_id: 'bo_5#0', node_id: 'bo', start_idx: 5, end_idx: 5 } as any
    expect(findBoBar('bo_5#0', [bo])).toBe(5)
  })

  it('集合取首元素', () => {
    const bo = { instance_id: 'bo_30_33#0', node_id: 'bo', start_idx: 30, end_idx: 33 } as any
    expect(findBoBar(['bo_30_33#0', 'bo_31_33#0'], [bo])).toBe(33)
  })

  it('bo 不存在返 null', () => {
    expect(findBoBar('bo_999#0', [])).toBeNull()
    expect(findBoBar(['bo_999#0'], [])).toBeNull()
  })

  it('精确匹配(不看 node_id)', () => {
    const other = { instance_id: 'x#0', node_id: 'other', start_idx: 30, end_idx: 88 } as any
    expect(findBoBar('x#0', [other])).toBe(88)
  })
})

describe('DEBUG_ENABLED_NODES', () => {
  it('实例化后白名单 = 埋点 node_id 集:含 tb(node_id 恒一),不再含旧 class_id 键', () => {
    expect(DEBUG_ENABLED_NODES).toContain('tb')
    expect(DEBUG_ENABLED_NODES).toEqual(['tb_seg', 'tb_seg_v3', 'tb'])
  })

  it('不含 _default(v2 D8 硬耦合过滤)', () => {
    expect(DEBUG_ENABLED_NODES).not.toContain('_default')
  })
})
