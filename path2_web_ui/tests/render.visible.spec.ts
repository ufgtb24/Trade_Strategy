import { describe, it, expect } from 'vitest'
import { matchedIds } from '../src/render/visible'
import type { EventDict, MatchDict, TopoEdge } from '../src/types'

// 共享 leaf 场景:两个 burst 共用同一 tb(leaf-reuse 多对一确认)。
// 实例化契约:anchor_bo_id 为 instance_id 字符串(单值标量,per-source 来源单值),
// tb 只记自己的来源 bo;共享 leaf 时各 burst 的 tb 是不同事件,不合并 anchor。
const BURST_S: EventDict = { instance_id: 'burst_0_1#0', node_id: 'burst', instance_idx: 0, start_idx: 0, end_idx: 1,
  child_refs: { members: ['bo_0#0'] } } as unknown as EventDict
const TB_SHARED: EventDict = { instance_id: 'tb_6_7#0', node_id: 'tb', instance_idx: 0, start_idx: 6, end_idx: 7,
  anchor_bo_id: 'bo_0#0', child_refs: {} } as unknown as EventDict
const BO_A: EventDict = { instance_id: 'bo_0#0', node_id: 'bo', instance_idx: 0, start_idx: 0, end_idx: 0, child_refs: {} } as unknown as EventDict
const BO_B: EventDict = { instance_id: 'bo_5#0', node_id: 'bo', instance_idx: 0, start_idx: 5, end_idx: 5, child_refs: {} } as unknown as EventDict
const EDGES: TopoEdge[] = [{ src: 'burst', dst: 'tb', kind: 'TemporalEdge', anchor_field: 'anchor_bo_id' }] as unknown as TopoEdge[]
const EVENTS: EventDict[] = [BURST_S, TB_SHARED, BO_A, BO_B]

const SHORT_MATCH: MatchDict = {
  match_id: 'p@0-7#burst:burst_0_1#0|tb:tb_6_7#0',
  start_idx: 0, end_idx: 7,
  node_index: { burst: 'burst_0_1#0', tb: 'tb_6_7#0' },
  children: ['burst_0_1#0', 'tb_6_7#0'],
} as unknown as MatchDict

describe('matchedIds 共享 leaf 高亮 vs 归属', () => {
  it('高亮(expandAnchor=false):选短 burst 时,tb 的 anchor 反查关闭,bo_b 不被拉进高亮', () => {
    const ids = matchedIds([SHORT_MATCH], EVENTS, EDGES, { expandAnchor: false })
    expect(ids.has('burst_0_1#0')).toBe(true)
    expect(ids.has('tb_6_7#0')).toBe(true)
    expect(ids.has('bo_0#0')).toBe(true)    // burst.members → 经 child_refs 展开
    expect(ids.has('bo_5#0')).toBe(false)   // 不在链路结构内,anchor 不反向污染
  })

  it('归属/tier(默认 expandAnchor=true):tb.anchor_bo_id(instance_id 标量)反查 bo_a 进集', () => {
    const ids = matchedIds([SHORT_MATCH], EVENTS, EDGES)
    expect(ids.has('bo_0#0')).toBe(true)
    expect(ids.has('bo_5#0')).toBe(false)   // 单值 anchor:bo_b 不是 tb 的来源,不进集
  })
})

describe('matchedIds anchor 值 instance_id 形态直连', () => {
  // 交错标注后 anchor_bo_id 在 detect 期即写 instance_id 形态('bo_5#0'),byId 直连命中即入集。
  const TB_ANCHOR: EventDict = { instance_id: 'tb_5_6#0', node_id: 'tb', instance_idx: 0, start_idx: 5, end_idx: 6,
    anchor_bo_id: 'bo_5#0', child_refs: {} } as unknown as EventDict
  const BO_ANCHOR: EventDict = { instance_id: 'bo_5#0', node_id: 'bo', instance_idx: 0, start_idx: 5, end_idx: 5,
    child_refs: {} } as unknown as EventDict
  const M: MatchDict = {
    match_id: 'm', start_idx: 0, end_idx: 6,
    node_index: { tb: 'tb_5_6#0' },
    children: ['tb_5_6#0'],
  } as unknown as MatchDict

  it('anchor_bo_id 为 instance_id 形态:byId 直连命中 bo,并入集', () => {
    const ids = matchedIds([M], [TB_ANCHOR, BO_ANCHOR], [{ src: 'burst', dst: 'tb', kind: 'TemporalEdge', anchor_field: 'anchor_bo_id' }] as unknown as TopoEdge[])
    expect(ids.has('tb_5_6#0')).toBe(true)
    expect(ids.has('bo_5#0')).toBe(true)   // ← byId 直连命中,bo 进集
  })

  it('expandAnchor=false 时不反查 anchor(高亮隔离),bo 不进集', () => {
    const ids = matchedIds([M], [TB_ANCHOR, BO_ANCHOR], [{ src: 'burst', dst: 'tb', kind: 'TemporalEdge', anchor_field: 'anchor_bo_id' }] as unknown as TopoEdge[], { expandAnchor: false })
    expect(ids.has('tb_5_6#0')).toBe(true)
    expect(ids.has('bo_5#0')).toBe(false)
  })
})
