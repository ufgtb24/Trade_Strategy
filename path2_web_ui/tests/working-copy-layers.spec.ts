// 层判定纯函数:materialize_keys → where 行号。monaco 接入在另一处(jsdom 不可 mount)。
import { describe, it, expect } from 'vitest'
import { materializeKeysByNode, whereLineNumbers } from '../src/components/workingCopyLayers'

const MK = {
  bo: ['total_window', 'min_side_bars', 'vol_baseline_period', 'peak_measure'],
  burst: ['gap_max', 'min_bos', 'vol_baseline_period'],
  tb: ['max_start_gap', 'max_window', 'atr_window', 'stop_confirm_bars'],
}

describe('materializeKeysByNode', () => {
  it('topology.nodes → { node_id: materialize_keys }', () => {
    const topology = { nodes: [
      { node_id: 'bo', where_rules: [], materialize_keys: ['total_window'] },
      { node_id: 'burst', where_rules: [], materialize_keys: ['gap_max'] },
    ], edges: [] }
    expect(materializeKeysByNode(topology)).toEqual({ bo: ['total_window'], burst: ['gap_max'] })
  })
  it('materialize_keys 缺失 → 空数组(防御旧数据)', () => {
    const topology = { nodes: [
      { node_id: 'bo', where_rules: [] },
    ], edges: [] }
    expect(materializeKeysByNode(topology)).toEqual({ bo: [] })
  })
})

describe('whereLineNumbers', () => {
  const yaml = [
    'bo:',
    '  total_window: 20',
    'burst:',
    '  gap_max: 8',
    '  min_bos: 2',
    '  first_drought_min: 20',
    '  distinct_pk_min: 3',
    '  vol_spike_min: 3',
    'tb:',
    '  max_start_gap: 7',
    'edges:',
    '  foo: bar',
  ].join('\n')
  it('返回 burst 内 where 键行号(0-based),跳过物化键与非 node section', () => {
    // first_drought_min(5) / distinct_pk_min(6) / vol_spike_min(7) 是 where;gap_max/min_bos 物化
    expect(whereLineNumbers(yaml, MK)).toEqual([5, 6, 7])
  })
  it('bo/tb 全物化 → 无 where 行', () => {
    const onlyBoTb = ['bo:', '  total_window: 20', 'tb:', '  max_start_gap: 7'].join('\n')
    expect(whereLineNumbers(onlyBoTb, MK)).toEqual([])
  })
  it('edges section(非 detector node)不被误标 where', () => {
    expect(whereLineNumbers(yaml, MK)).not.toContain(11) // edges 的 foo:bar 行
  })
  it('空 mkByNode → 无 where 行(防御)', () => {
    expect(whereLineNumbers(yaml, {})).toEqual([])
  })
  it('section 的 materialize_keys 为空 → 该 section 不标 where(旧 scan 防御)', () => {
    const mkBurstEmpty = { ...MK, burst: [] }
    const burstOnly = ['burst:', '  gap_max: 8', '  distinct_pk_min: 3'].join('\n')
    expect(whereLineNumbers(burstOnly, mkBurstEmpty)).toEqual([])
  })
})
