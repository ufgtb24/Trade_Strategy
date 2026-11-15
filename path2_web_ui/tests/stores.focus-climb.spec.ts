// stores.focus-climb.spec.ts — focusEvent 子结构爬升契约
// 背景:hit 成员 = 各 node 绑定实例(node_index 只含 burst/tb 容器),bo/tb_seg
// 子事件经容器 child_refs 挂靠、不是 hit 成员——直接按 node_index 解析恒 0 归属。
// 爬升 = 经 child_refs 逆索引用父容器 instance_id 再解析「用到它的 hit」:点段 / 点 bo 选中的是这个 event,
// 用到它的 hit 是它牵出的;从它走进买点日、选中其中一次 hit 后,邻居段照常由这次 hit 的 child_refs 闭包内建。
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
    // 父容器不在任何 hit 的段(0 归属回落)
    { instance_id: 'tb_40_41#0', node_id: 'tb', start_idx: 40, end_idx: 41,
      child_refs: { segments: ['tb_40#0'] } },
    { instance_id: 'tb_40#0', node_id: 'tb', start_idx: 40, end_idx: 40, child_refs: {} },
    // 非 hit 的组成型组(新形态:段直标 tb_seg)——「一选全选」用例数据
    { instance_id: 'tb_50_52#0', node_id: 'tb', start_idx: 50, end_idx: 52,
      child_refs: { segments: ['tb_seg_50#0', 'tb_seg_51#0'] } },
    { instance_id: 'tb_seg_50#0', node_id: 'tb_seg', start_idx: 50, end_idx: 50, child_refs: {} },
    { instance_id: 'tb_seg_51#0', node_id: 'tb_seg', start_idx: 51, end_idx: 52, child_refs: {} },
    // 孤立 burst(无 hit 归属):引用型无关 node,不应触发组展开
    { instance_id: 'burst_60_61#0', node_id: 'burst', start_idx: 60, end_idx: 61,
      child_refs: { members: ['bo_60#0'] } },
    { instance_id: 'bo_60#0', node_id: 'bo', start_idx: 60, end_idx: 60 },
  ] as any
  a.hits = [
    { hit_id: 'm-full', start_idx: 4, end_idx: 20,
      node_index: { burst: 'burst_4_6#0', tb: 'tb_10_20#0' },
      children: ['burst_4_6#0', 'tb_10_20#0'] } as any,
    { hit_id: 'm-prefix', start_idx: 4, end_idx: 31,
      node_index: { burst: 'burst_4_5#0', tb: 'tb_30_31#0' },
      children: ['burst_4_5#0', 'tb_30_31#0'] } as any,
  ]
  // topology.nodes 补 tb_seg 子结构条目(produced_by='tb' + parent_refs;bb_v1 快照本身无 children 声明,手造)
  const topo = base.per_pattern['bb_v1'].pattern_spec.topology
  topo.nodes = [...topo.nodes, { node_id: 'tb_seg', produced_by: 'tb',
    parent_refs: [['tb', 'segments']] } as any]
  return base
}

describe('view store — focusEvent 子结构爬升', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('点 tb_seg → 选中这一段,爬升认出容器所在的 hit(牵出、照常);走进去选中那次 hit 后,它的组成经 child_refs 闭包照常', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_15_18#0')
    // 点段选中的是这一段;用到它的 hit 经容器认出来,是它牵出的
    expect(view.selectedInstanceId).toBe('tb_seg_15_18#0')
    expect(view.focusedHitId).toBeNull()
    expect([...view.highlight.ledHits]).toEqual(['m-full'])
    // → 进到它的买点日(竖线在段的终点 18,那天就是买点日,只有这一次):选中这次 hit,这一段是实例焦点
    view.stepPos(1)
    expect(view.focusedHitId).toBe('m-full')
    expect(view.focusedInstanceId).toBe('tb_seg_15_18#0')
    expect(view.selectedInstanceId).toBeNull()
    // 邻居段 + 容器 + burst + bo 成员都照常(boundEvents 的 child_refs 闭包)
    for (const id of ['tb_seg_11#0', 'tb_seg_15_18#0', 'tb_10_20#0', 'burst_4_6#0', 'bo_4#0', 'bo_6#0']) {
      expect(view.highlight.appEvents.has(id), id).toBe(true)
    }
    // 前缀链的成员不照常(无污染)
    for (const id of ['tb_30#0', 'tb_30_31#0', 'burst_4_5#0']) {
      expect(view.highlight.appEvents.has(id), id).toBe(false)
    }
  })

  it('点唯一归属的 bo → 爬升 bo→burst 认出所在 hit(牵出);走进去选中的就是它', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('bo_6#0')   // 只被 burst_4_6 引用 → m-full
    expect(view.selectedInstanceId).toBe('bo_6#0')
    expect(view.focusedHitId).toBeNull()
    expect([...view.highlight.ledHits]).toEqual(['m-full'])
    view.stepPos(1)
    expect(view.focusedHitId).toBe('m-full')
    expect(view.focusedInstanceId).toBe('bo_6#0')
    expect([...view.highlight.under.events]).toEqual(['bo_6#0'])
  })

  it('点前缀族共享 bo(两父 burst 各有 hit、买点日不同)→ 两次都牵出、照常,不自动选', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('bo_4#0')   // burst_4_6(m-full) 与 burst_4_5(m-prefix) 共享
    expect(view.focusedHitId).toBeNull()
    expect(view.focusedInstanceId).toBeNull()
    expect(view.selectedInstanceId).toBe('bo_4#0')
    expect([...view.highlight.ledHits].sort()).toEqual(['m-full', 'm-prefix'])
  })

  it('父容器不在任何 hit、自己没有子事件 → 只选中它;app 那边不淡', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_40#0')
    expect(view.selectedInstanceId).toBe('tb_40#0')
    expect(view.focusedHitId).toBeNull()
    expect([view.highlight.ledHits.size, view.highlight.dimApp]).toEqual([0, false])
  })

  // ── 组成型「一选全选」已去掉:点子段不再顺带亮出它所属的容器与兄弟段(一个子段常被好多个容器共用,
  //    挑中的往往不在任何 hit 里、画不出来);要看就点那个容器。容器的组成是它的子事件(沿 child_refs 到底)。──

  it('点非 hit 组的段 → 只选中它,不顺带亮出容器;没有组成、没牵出 hit,app 那边不淡', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_51#0')
    expect(view.selectedInstanceId).toBe('tb_seg_51#0')
    expect(view.highlight.appEvents.has('tb_50_52#0')).toBe(false)
    expect(view.highlight.dimApp).toBe(false)
  })

  it('点非 hit 组的容器 → 它的子段照常(它的组成),别的组画淡', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_50_52#0')
    expect(view.highlight.dimApp).toBe(true)
    for (const id of ['tb_seg_50#0', 'tb_seg_51#0']) expect(view.highlight.appEvents.has(id), id).toBe(true)
    expect(view.highlight.appEvents.has('tb_seg_11#0')).toBe(false)
  })

  it('从 hit 组的段走进去、选中那次 hit → 照常的是这次 hit 的组成', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('tb_seg_15_18#0')
    view.stepPos(1)                     // 选中 m-full
    expect(view.focusedHitId).toBe('m-full')
    expect(view.selectedInstanceId).toBeNull()
    expect(view.highlight.appEvents.has('tb_seg_11#0')).toBe(true)
  })

  it('引用型 burst:它的成员 bo 是它的子事件,照常;旧形态段(没有子事件)只选中它', () => {
    const view = useViewStore()
    view.loadScanFile(makeClimbFixture())
    view.focusEvent('burst_60_61#0')
    expect(view.highlight.appEvents.has('bo_60#0')).toBe(true)
    view.focusEvent('tb_40#0')
    expect(view.highlight.dimApp).toBe(false)
  })
})
