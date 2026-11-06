// label(N 日前瞻收益)与缓冲窗:纯函数 + chart 选项。
import { describe, it, expect } from 'vitest'
import { windowOf, formatForwardReturn } from '../src/render/visible'
import { MONO } from '../src/render/fonts'

describe('windowOf', () => {
  it('缓冲扫描用 win_*', () => {
    expect(windowOf({ start_date: 'a', end_date: 'b', win_start: 'wa', win_end: 'wb' }))
      .toEqual({ start: 'wa', end: 'wb' })
  })
  it('win_start/win_end 存在时优先返回 win_*', () => {
    expect(windowOf({ start_date: 'a', end_date: 'b', win_start: 'wa2', win_end: 'wb2' }))
      .toEqual({ start: 'wa2', end: 'wb2' })
  })
})

describe('formatForwardReturn', () => {
  it('正值带 +,一位小数百分比', () => expect(formatForwardReturn(0.1234)).toBe('+12.3%'))
  it('负值', () => expect(formatForwardReturn(-0.05)).toBe('-5.0%'))
  it('null(尾部数据不足)→ —', () => expect(formatForwardReturn(null)).toBe('—'))
})

import { buildMarkerTooltipFormatter, computeEventData, buildSubOption } from '../src/render/chart'
import type { BandRenderInput } from '../src/render/chart'
import { computeSubGeometry } from '../src/render/subGeometry'
import type { Bar, HitDict, Topology } from '../src/types'

describe('buildMarkerTooltipFormatter — ordinal consistency with packBrackets (Task 9 fix)', () => {
  it('marker 归属节只报个数(bracket 折叠后一行几十次 hit,逐个圈号已无意义)', () => {
    const hits: HitDict[] = [
      // 故意乱序(非 start_idx 升序):
      { hit_id: 'm_late',  start_idx: 50, end_idx: 60, node_index: {}, children: ['eShared#0'], predicate_trace: null },
      { hit_id: 'm_early', start_idx: 10, end_idx: 20, node_index: {}, children: ['eShared#0'], predicate_trace: null },
      { hit_id: 'm_mid',   start_idx: 30, end_idx: 40, node_index: {}, children: ['eShared#0'], predicate_trace: null },
    ]
    const fmt = buildMarkerTooltipFormatter(undefined, undefined, { hits, candidateHitIds: new Set() })
    const out = fmt({ data: { instance_id: 'eShared#0' } })
    expect(out).toContain('in_hits: 3')
  })
})

// ─── 6. hit tooltip label on buildSubOption brackets series(chart.ts:1055+ buildMarkerTooltipFormatter,
//     恢复自 95f5554 版 labels.spec.ts「hit tooltip label」describe,适配 buildSubOption 新签名)──
describe('buildSubOption — brackets series hit tooltip label (Task 6 review fix group 6)', () => {
  const bars: Bar[] = [
    { date: '2025-01-01', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
    { date: '2025-01-02', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
  ]
  const hit: HitDict = {
    hit_id: 'm1', start_idx: 0, end_idx: 1, node_index: {}, children: [], predicate_trace: null,
  }
  function baseInput(overrides: Partial<BandRenderInput> = {}): BandRenderInput {
    return {
      topology: { nodes: [], edges: [] } as Topology,
      isolatedNodeIds: new Set(),
      tagList: [],
      level: 'detected',
      nodeColors: {},
      eventTier: () => 'detected',
      nodeOfEventByBand: () => null,
      bandKeyOf: () => '',
      hits: [hit],
      ...overrides,
    }
  }

  it('hitLabel(hitId) 返回 label → brackets tooltip = "hit: <label><br/>组成 (N events):" + composition', () => {
    const input = baseInput({ hitLabel: (id) => (id === 'm1' ? 'ret_20: +12.3%' : null) })
    const bundle = computeEventData(bars, [], [hit], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [] })
    const opt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    expect(brackets.tooltip).toBeDefined()
    expect(brackets.tooltip.formatter({ data: { hit_id: 'm1' } }))
      .toBe(`<span style='font-family:${MONO}'>hit: ret_20: +12.3%</span><br/>组成 (0 events):`)
  })

  it('hitLabel(hitId)=null → brackets tooltip 仅 "组成 (N events):" + composition(无 hit 行)', () => {
    const input = baseInput({ hitLabel: () => null })
    const bundle = computeEventData(bars, [], [hit], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [] })
    const opt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    expect(brackets.tooltip.formatter({ data: { hit_id: 'm1' } })).toBe('组成 (0 events):')
  })
})
