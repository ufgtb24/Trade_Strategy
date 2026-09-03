// stores.focus-climb.spec.ts — focusEvent 子结构爬升契约(2026-08-16)
// 背景:match 成员 = 各 node 绑定实例(node_index 只含 burst/tb 容器),bo/tb_seg
// 子事件经容器 child_refs 挂靠、不是 match 成员——直接按 node_index 解析恒 0 归属,
// 点段/点 bo 只亮单点。爬升 = 经 child_refs 逆索引用父容器 instance_id 再解析,
// 0/1/≥2 三分支照走(≥2 前缀族消歧);邻居段高亮由 matchedIds 的 child_refs 闭包内建。
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import fs from 'node:fs'
import path from 'node:path'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile } from '../src/types'

// 深拷贝真实 scan 换 analysis(同 instance-id-acceptance.spec.ts 的 makeSharedFixture 模式)。
// 方案 A(2026-08-17):声明 children 的段 node_id/instance_id 直标子结构名
// (tb_seg_*);m-prefix/tb_40 链保留旧形态(node_id 'tb',未声明 app 的段)覆盖兼容。
function makeClimbFixture(): MultiScanResultFile {
  const base = JSON.parse(JSON.stringify(JSON.parse(
    fs.readFileSync(path.resolve(process.cwd(), 'tests/fixtures/apcx-instance-id-acceptance.json'), 'utf-8'),
  ))) as MultiScanResultFile
  const a = base.results[0].per_pattern['bb_v1'].analysis
  a.events = [
    { instance_id: 'bo_4#0', node_id: 'bo', start_idx: 4, end_idx: 4 },
    { instance_id: 'bo_5#0', node_id: 'bo', start_idx: 5, end_idx: 5 },
    { instance_id: 'bo_6#0', node_id: 'bo', start_idx: 6, end_idx: 6 },
    // 前缀族:整串 burst_4_6 与前缀 burst_4_5 共享 bo_4/bo_5
    { instance_id: 'burst_4_6#0', node_id: 'burst', start_idx: 4, end_idx: 6,
      child_refs: { members: ['bo_4#0', 'bo_5#0', 'bo_6#0'] } },
    { instance_id: 'burst_4_5#0', node_id: 'burst', start_idx: 4, end_idx: 5,
      child_refs: { members: ['bo_4#0', 'bo_5#0'] } },
    // m-full 链的 tb 容器(两段)与 m-prefix 链的 tb 容器(一段)
    { instance_id: 'tb_10_20#0', node_id: 'tb', start_idx: 10, end_idx: 20,
      child_refs: { segments: ['tb_seg_11#0', 'tb_seg_15_18#0'] } },
    { instance_id: 'tb_seg_11#0', node_id: 'tb_seg', start_idx: 11, end_idx: 11, child_refs: {} },
    { instance_id: 'tb_seg_15_18#0', node_id: 'tb_seg', start_idx: 15, end_idx: 18, child_refs: {} },
    { instance_id: 'tb_30_31#0', node_id: 'tb', start_idx: 30, end_idx: 31,
      child_refs: { segments: ['tb_30#0'] } },
    { instance_id: 'tb_30#0', node_id: 'tb', start_idx: 30, end_idx: 30, child_refs: {} },
    // 父容器不在任何 match 的段(0 归属回落)
    { instance_id: 'tb_40_41#0', node_id: 'tb', start_idx: 40, end_idx: 41,
      child_refs: { segments: ['tb_40#0'] } },
    { instance_id: 'tb_40#0', node_id: 'tb', start_idx: 40, end_idx: 40, child_refs: {} },
    // 非 match 的组成型组(新形态:段直标 tb_seg)——「一选全选」用例数据
    { instance_id: 'tb_50_52#0', node_id: 'tb', start_idx: 50, end_idx: 52,
      child_refs: { segments: ['tb_seg_50#0', 'tb_seg_51#0'] } },
    { instance_id: 'tb_seg_50#0', node_id: 'tb_seg', start_idx: 50, end_idx: 50, child_refs: {} },
    { instance_id: 'tb_seg_51#0', node_id: 'tb_seg', start_idx: 51, end_idx: 52, child_refs: {} },
    // 孤立 burst(无 match 归属):引用型无关 node,不应触发组展开
    { instance_id: 'burst_60_61#0', node_id: 'burst', start_idx: 60, end_idx: 61,
      child_refs: { members: ['bo_60#0'] } },
    { instance_id: 'bo_60#0', node_id: 'bo', start_idx: 60, end_idx: 60 },
  ] as any
  a.matches = [
    { match_id: 'm-full', start_idx: 4, end_idx: 20,
      node_index: { burst: 'burst_4_6#0', tb: 'tb_10_20#0' },
      children: ['burst_4_6#0', 'tb_10_20#0'] } as any,
    { match_id: 'm-prefix', start_idx: 4, end_idx: 31,
      node_index: { burst: 'burst_4_5#0', tb: 'tb_30_31#0' },
      children: ['burst_4_5#0', 'tb_30_31#0'] } as any,
  ]
  // 组成型判别数据源:topology.nodes 补 tb_seg 子结构条目(produced_by='tb' +
  // parent_refs;bb_v1 快照本身无 children 声明,手造供 compositionGroupIds 判别)
  const topo = base.per_pattern['bb_v1'].pattern_spec.topology
  topo.nodes = [...topo.nodes, { node_id: 'tb_seg', produced_by: 'tb',
    parent_refs: [['tb', 'segments']] } as any]
  return base
}

describe('view store — focusEvent 子结构爬升', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('点 tb_seg → 爬升到容器所在 match 直选;邻居段/成员经 child_refs 闭包进 group 高亮集', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_15_18#0')
    expect(view.focusedMatchId).toBe('m-full')
    expect(view.focusedInstanceId).toBe('tb_seg_15_18#0')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBeNull()
    // 邻居段 + 容器 + burst + bo 成员全进高亮集(matchedIds child_refs 闭包)
    for (const id of ['tb_seg_11#0', 'tb_seg_15_18#0', 'tb_10_20#0', 'burst_4_6#0', 'bo_4#0', 'bo_6#0']) {
      expect(view.highlightedEventIds.has(id), id).toBe(true)
    }
    // 前缀链的成员不进高亮集(无污染)
    for (const id of ['tb_30#0', 'tb_30_31#0', 'burst_4_5#0']) {
      expect(view.highlightedEventIds.has(id), id).toBe(false)
    }
  })

  it('点唯一归属的 bo → 爬升 bo→burst 直选所在 match', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('bo_6#0')   // 只被 burst_4_6 引用 → m-full
    expect(view.focusedMatchId).toBe('m-full')
    expect(view.focusedInstanceId).toBe('bo_6#0')
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('点前缀族共享 bo(两父 burst 各有 match)→ ≥2 归属弹候选消歧,不自动选', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('bo_4#0')   // burst_4_6(m-full) 与 burst_4_5(m-prefix) 共享
    expect(view.focusedMatchId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.pendingDisambigInstanceId).toBe('bo_4#0')
    expect(view.candidateMatchIds.has('m-full')).toBe(true)
    expect(view.candidateMatchIds.has('m-prefix')).toBe(true)
  })

  it('父容器不在任何 match → 维持 0 归属单点聚焦(行为与爬升前一致)', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_40#0')
    expect(view.selectedInstanceId).toBe('tb_40#0')
    expect(view.focusedMatchId).toBeNull()
    expect(view.highlightedEventIds.size).toBe(0)
  })

  // ── 组成型组「一选全选」(2026-08-17):0 归属非 match 组,点组内任一成员 →
  // 整组(容器+全部段)进 compositionGroupIds;match 存在时空集(match 闭包覆盖)。──

  it('点非 match 组的段 → 整组(容器+邻居段)进 compositionGroupIds', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_51#0')
    expect(view.selectedInstanceId).toBe('tb_seg_51#0')
    expect(view.compositionGroupIds.size).toBe(3)
    for (const id of ['tb_50_52#0', 'tb_seg_50#0', 'tb_seg_51#0']) {
      expect(view.compositionGroupIds.has(id), id).toBe(true)
    }
    // 不污染其他组
    expect(view.compositionGroupIds.has('tb_40_41#0')).toBe(false)
  })

  it('点非 match 组的容器 → 同一整组(与点段等价)', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_50_52#0')
    expect(view.compositionGroupIds.size).toBe(3)
    expect(view.compositionGroupIds.has('tb_seg_50#0')).toBe(true)
  })

  it('match 组点段 → compositionGroupIds 空,由 match 闭包覆盖(一选全选不叠加)', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_15_18#0')   // m-full 直选(1 归属)
    expect(view.selectedInstanceId).toBeNull()
    expect(view.compositionGroupIds.size).toBe(0)
    expect(view.highlightedEventIds.has('tb_seg_11#0')).toBe(true)   // match 闭包管组员
  })

  it('引用型/无关 node(孤立 burst、旧形态段)不触发组展开,维持单点', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('burst_60_61#0')   // 孤立 burst:无组成型子槽
    expect(view.compositionGroupIds.size).toBe(0)
    view.focusEvent('tb_40#0')        // 旧形态段(node_id 继承 'tb'):单点回落
    expect(view.compositionGroupIds).toEqual(new Set(['tb_40#0']))
  })
})
