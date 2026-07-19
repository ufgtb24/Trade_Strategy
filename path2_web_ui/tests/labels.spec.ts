// label(N 日前瞻收益)与缓冲窗:纯函数 + chart 选项。
import { describe, it, expect } from 'vitest'
import { windowOf, formatForwardReturn } from '../src/render/visible'

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
import type { Bar, MatchDict, Topology } from '../src/types'

describe('buildMarkerTooltipFormatter — ordinal consistency with packBrackets (Task 9 fix)', () => {
  it('marker 归属节 ordinal uses start_idx sort, not raw matches order', () => {
    const matches: MatchDict[] = [
      // 故意乱序(非 start_idx 升序):
      { event_id: 'm_late',  start_idx: 50, end_idx: 60, node_index: {}, children: ['eShared'], predicate_trace: null },
      { event_id: 'm_early', start_idx: 10, end_idx: 20, node_index: {}, children: ['eShared'], predicate_trace: null },
      { event_id: 'm_mid',   start_idx: 30, end_idx: 40, node_index: {}, children: ['eShared'], predicate_trace: null },
    ]
    const fmt = buildMarkerTooltipFormatter(undefined, undefined, { matches, candidateMatchIds: new Set() })
    const out = fmt({ data: { event_id: 'eShared' } })
    // start_idx 排序后: m_early=①, m_mid=②, m_late=③ → 三者都含 eShared
    expect(out).toContain('归属: match ① ② ③')
  })
})

// ─── 6. Match tooltip label on buildSubOption brackets series(chart.ts:1055+ buildMarkerTooltipFormatter,
//     恢复自 95f5554 版 labels.spec.ts「match tooltip label」describe,适配 buildSubOption 新签名)──
describe('buildSubOption — brackets series match tooltip label (Task 6 review fix group 6)', () => {
  const bars: Bar[] = [
    { date: '2025-01-01', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
    { date: '2025-01-02', o: 1, h: 1, l: 1, c: 1, v: 1, rv: 0 },
  ]
  const match: MatchDict = {
    event_id: 'm1', start_idx: 0, end_idx: 1, node_index: {}, children: [], predicate_trace: null,
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
      matches: [match],
      ...overrides,
    }
  }

  it('matchLabel(matchId) 返回 label → brackets tooltip = "Match: <label><br/>组成 (N events):" + composition', () => {
    const input = baseInput({ matchLabel: (id) => (id === 'm1' ? 'ret_20: +12.3%' : null) })
    const bundle = computeEventData(bars, [], [match], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [] })
    const opt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    expect(brackets.tooltip).toBeDefined()
    expect(brackets.tooltip.formatter({ data: { match_id: 'm1' } }))
      .toBe('Match: ret_20: +12.3%<br/>组成 (0 events):')
  })

  it('matchLabel(matchId)=null → brackets tooltip 仅 "组成 (N events):" + composition(无 Match 行)', () => {
    const input = baseInput({ matchLabel: () => null })
    const bundle = computeEventData(bars, [], [match], input)
    const subGeom = computeSubGeometry({ bracketLaneCount: 1, bandLaneCounts: [] })
    const opt: any = buildSubOption(bars, bundle, subGeom, input, 800)
    const brackets = opt.series.find((s: any) => s.name === 'brackets')
    expect(brackets.tooltip.formatter({ data: { match_id: 'm1' } })).toBe('组成 (0 events):')
  })
})
